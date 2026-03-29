'use strict';

/**
 * Autonomous Convergence Loop
 *
 * Repeatedly runs vectors through all adapters, identifies divergence,
 * isolates the source, and reports a convergence score trend.
 *
 * This is the orchestrator that connects:
 *   - vector-loader (test data)
 *   - adapter-protocol (execution)
 *   - output-comparator (comparison)
 *   - iob-isolation (component analysis)
 *
 * Usage:
 *   node convergence-loop.js --adapters adapters/oref0-js,adapters/t1pal-oref0-swift \
 *                            --vectors ../../conformance/t1pal/vectors/oref0-endtoend/ \
 *                            [--max-iterations 10] [--target-convergence 0.95] [--json]
 */

const path = require('path');
const fs = require('fs');
const { loadAdapter, runVector } = require('./lib/adapter-protocol');
const { loadVectors, extractExpected } = require('./lib/vector-loader');
const { compareOutputs, comparePredictions, DEFAULT_TOLERANCES, DIVERGENCE_LEVELS } = require('./lib/output-comparator');

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    adapters: [],
    vectorDir: null,
    maxIterations: 1,
    targetConvergence: 0.95,
    limit: 0,
    json: false,
    verbose: false,
    reportDir: null,
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--adapters': opts.adapters = args[++i].split(',').map(a => a.trim()); break;
      case '--vectors': opts.vectorDir = args[++i]; break;
      case '--max-iterations': opts.maxIterations = parseInt(args[++i], 10); break;
      case '--target-convergence': opts.targetConvergence = parseFloat(args[++i]); break;
      case '--limit': opts.limit = parseInt(args[++i], 10); break;
      case '--json': opts.json = true; break;
      case '--verbose': opts.verbose = true; break;
      case '--report-dir': opts.reportDir = args[++i]; break;
    }
  }

  if (opts.adapters.length < 2) {
    console.error('Error: --adapters requires at least 2 adapter paths');
    process.exit(1);
  }

  if (!opts.vectorDir) {
    opts.vectorDir = path.resolve(__dirname, '../../conformance/t1pal/vectors/oref0-endtoend');
  }

  return opts;
}

/**
 * Run a single convergence iteration: execute all vectors through all adapters,
 * compare pairwise, classify divergence.
 */
async function runIteration(vectors, adapters, opts) {
  const results = [];
  const divergenceMap = {}; // vectorId → { component, level, details }

  for (const vector of vectors) {
    const vectorId = vector.metadata?.id || 'unknown';
    const outputs = [];

    // Execute through each adapter
    for (const adapter of adapters) {
      const result = await runVector(adapter, vector, { mode: 'execute' });
      outputs.push(result);
    }

    // Compare each pair
    for (let i = 0; i < outputs.length; i++) {
      for (let j = i + 1; j < outputs.length; j++) {
        const a = outputs[i];
        const b = outputs[j];

        if (a.error || b.error) {
          results.push({
            vectorId,
            pair: `${a.adapter} vs ${b.adapter}`,
            pass: false,
            error: a.error || b.error,
          });
          continue;
        }

        const comparison = compareOutputs(a.output, b.output);
        const isolation = isolateDivergenceSource(a.output, b.output, comparison);

        results.push({
          vectorId,
          pair: `${a.adapter} vs ${b.adapter}`,
          pass: comparison.pass,
          divergenceLevel: comparison.summary.worstDivergence,
          isolation,
          fieldDetails: comparison.fields.filter(f => !f.pass),
          predictionDetails: comparison.predictions,
        });

        if (!comparison.pass) {
          divergenceMap[vectorId] = divergenceMap[vectorId] || [];
          divergenceMap[vectorId].push({
            pair: `${a.adapter} vs ${b.adapter}`,
            component: isolation.primarySource,
            level: comparison.summary.worstDivergence,
            details: isolation,
          });
        }
      }
    }
  }

  // Compute convergence metrics
  const total = results.filter(r => !r.error).length;
  const passed = results.filter(r => r.pass).length;
  const errors = results.filter(r => r.error).length;

  const convergence = computeConvergenceMetrics(results);
  const hotspots = identifyHotspots(divergenceMap);

  return {
    total,
    passed,
    failed: total - passed,
    errors,
    convergence,
    hotspots,
    divergenceMap,
    results,
  };
}

/**
 * Isolate which component (IOB, predictions, decision, safety) is the
 * primary source of divergence.
 */
function isolateDivergenceSource(outputA, outputB, comparison) {
  const sources = {
    iob: false,
    predictions: false,
    decision: false,
    safety: false,
  };

  // Check IOB state divergence
  const iobField = comparison.fields.find(f => f.field === 'iob');
  if (iobField && !iobField.pass) {
    sources.iob = true;
  }

  // Check prediction divergence
  if (comparison.predictions && !comparison.predictions.pass) {
    sources.predictions = true;
  }

  // Check decision divergence
  const rateField = comparison.fields.find(f => f.field === 'rate');
  if (rateField && !rateField.pass) {
    sources.decision = true;
  }

  // Check safety divergence (opposite rate directions)
  if (rateField && rateField.divergence === DIVERGENCE_LEVELS.OPPOSITE) {
    sources.safety = true;
  }

  // Determine primary source (cascade: IOB → predictions → decision → safety)
  let primarySource = 'unknown';
  if (sources.iob) primarySource = 'iob';
  else if (sources.predictions) primarySource = 'predictions';
  else if (sources.decision) primarySource = 'decision';
  else if (sources.safety) primarySource = 'safety';

  return { sources, primarySource };
}

/**
 * Compute multi-dimensional convergence metrics.
 */
function computeConvergenceMetrics(results) {
  const valid = results.filter(r => !r.error);
  const total = valid.length;
  if (total === 0) return { overall: 0, byComponent: {}, byLevel: {} };

  // Overall
  const overall = round(valid.filter(r => r.pass).length / total, 4);

  // By isolation component
  const byComponent = {};
  for (const source of ['iob', 'predictions', 'decision', 'safety']) {
    const relevant = valid.filter(r => r.isolation?.sources?.[source]);
    byComponent[source] = {
      divergent: relevant.length,
      rate: total > 0 ? round(1 - relevant.length / total, 4) : 1,
    };
  }

  // By divergence level
  const byLevel = {};
  for (const level of Object.values(DIVERGENCE_LEVELS)) {
    byLevel[level] = valid.filter(r => r.divergenceLevel === level).length;
  }

  return { overall, byComponent, byLevel };
}

/**
 * Identify the most common divergence patterns (hotspots).
 */
function identifyHotspots(divergenceMap) {
  const componentCounts = {};
  const vectorsByComponent = {};

  for (const [vectorId, divergences] of Object.entries(divergenceMap)) {
    for (const d of divergences) {
      componentCounts[d.component] = (componentCounts[d.component] || 0) + 1;
      if (!vectorsByComponent[d.component]) vectorsByComponent[d.component] = [];
      vectorsByComponent[d.component].push(vectorId);
    }
  }

  return Object.entries(componentCounts)
    .sort(([, a], [, b]) => b - a)
    .map(([component, count]) => ({
      component,
      count,
      vectors: [...new Set(vectorsByComponent[component])].slice(0, 5),
    }));
}

/**
 * Generate a convergence report for the iteration.
 */
function generateReport(iteration, iterationResult, adapters) {
  const { convergence, hotspots, total, passed, failed, errors } = iterationResult;

  const lines = [
    `## Iteration ${iteration}`,
    ``,
    `**Adapters**: ${adapters.map(a => a.manifest.name).join(', ')}`,
    `**Vectors**: ${total + errors} | **Comparisons**: ${total}`,
    `**Passed**: ${passed} | **Failed**: ${failed} | **Errors**: ${errors}`,
    `**Overall Convergence**: ${(convergence.overall * 100).toFixed(1)}%`,
    ``,
    `### Convergence by Component`,
    ``,
    `| Component | Convergence | Divergent Count |`,
    `|-----------|-------------|-----------------|`,
  ];

  for (const [comp, data] of Object.entries(convergence.byComponent)) {
    lines.push(`| ${comp} | ${(data.rate * 100).toFixed(1)}% | ${data.divergent} |`);
  }

  lines.push('', `### Divergence Distribution`, '', `| Level | Count |`, `|-------|-------|`);
  for (const [level, count] of Object.entries(convergence.byLevel)) {
    if (count > 0) lines.push(`| ${level} | ${count} |`);
  }

  if (hotspots.length > 0) {
    lines.push('', `### Hotspots`, '');
    for (const h of hotspots) {
      lines.push(`- **${h.component}** (${h.count} vectors): ${h.vectors.join(', ')}`);
    }
  }

  return lines.join('\n');
}

async function main() {
  const opts = parseArgs();

  const adapters = opts.adapters.map(a => loadAdapter(path.resolve(__dirname, a)));
  const vectors = loadVectors(opts.vectorDir, { limit: opts.limit });

  if (!opts.json) {
    console.log(`Autonomous Convergence Loop`);
    console.log(`Adapters: ${adapters.map(a => a.manifest.name).join(', ')}`);
    console.log(`Vectors: ${vectors.length}`);
    console.log(`Target convergence: ${(opts.targetConvergence * 100).toFixed(0)}%`);
    console.log(`Max iterations: ${opts.maxIterations}\n`);
  }

  const history = [];

  for (let iteration = 1; iteration <= opts.maxIterations; iteration++) {
    if (!opts.json) {
      console.log(`${'═'.repeat(60)}`);
      console.log(`Iteration ${iteration}/${opts.maxIterations}`);
      console.log(`${'═'.repeat(60)}`);
    }

    const result = await runIteration(vectors, adapters, opts);
    history.push({
      iteration,
      convergence: result.convergence.overall,
      passed: result.passed,
      failed: result.failed,
      errors: result.errors,
      hotspots: result.hotspots,
      byComponent: result.convergence.byComponent,
    });

    if (!opts.json) {
      console.log(`\n  Convergence: ${(result.convergence.overall * 100).toFixed(1)}%`);
      console.log(`  Passed: ${result.passed}/${result.total}`);

      if (result.hotspots.length > 0) {
        console.log(`  Primary divergence sources:`);
        for (const h of result.hotspots.slice(0, 3)) {
          console.log(`    ${h.component}: ${h.count} vectors`);
        }
      }
    }

    // Save report if report-dir specified
    if (opts.reportDir) {
      if (!fs.existsSync(opts.reportDir)) fs.mkdirSync(opts.reportDir, { recursive: true });
      const reportPath = path.join(opts.reportDir, `iteration-${iteration}.md`);
      fs.writeFileSync(reportPath, generateReport(iteration, result, adapters));
      const jsonPath = path.join(opts.reportDir, `iteration-${iteration}.json`);
      fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2));
    }

    // Check if target convergence reached
    if (result.convergence.overall >= opts.targetConvergence) {
      if (!opts.json) {
        console.log(`\n✓ Target convergence ${(opts.targetConvergence * 100).toFixed(0)}% reached!`);
      }
      break;
    }

    // For multi-iteration: the loop would normally feed divergent cases
    // back through a diagnostic pipeline. In this version, we re-run
    // the same vectors to measure stability.
    if (iteration < opts.maxIterations && !opts.json) {
      console.log(`  → ${(opts.targetConvergence * 100).toFixed(0)}% not yet reached, continuing...\n`);
    }
  }

  // Convergence trend
  const trend = history.length >= 2
    ? history[history.length - 1].convergence - history[0].convergence
    : 0;

  const summary = {
    adapters: adapters.map(a => a.manifest.name),
    vectors: vectors.length,
    iterations: history.length,
    targetConvergence: opts.targetConvergence,
    finalConvergence: history[history.length - 1]?.convergence || 0,
    trend: round(trend, 4),
    converged: (history[history.length - 1]?.convergence || 0) >= opts.targetConvergence,
    history,
  };

  if (opts.json) {
    console.log(JSON.stringify(summary, null, 2));
  } else {
    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Convergence Summary`);
    console.log(`${'─'.repeat(60)}`);
    console.log(`  Final: ${(summary.finalConvergence * 100).toFixed(1)}%`);
    console.log(`  Target: ${(summary.targetConvergence * 100).toFixed(0)}%`);
    console.log(`  Trend: ${trend >= 0 ? '+' : ''}${(trend * 100).toFixed(1)}% over ${history.length} iterations`);
    console.log(`  Status: ${summary.converged ? '✓ CONVERGED' : '✗ NOT YET CONVERGED'}`);
  }

  process.exit(summary.converged ? 0 : 1);
}

function round(n, places) {
  const factor = Math.pow(10, places);
  return Math.round(n * factor) / factor;
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(2);
});
