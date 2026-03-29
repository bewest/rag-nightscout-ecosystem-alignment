'use strict';

/**
 * IOB Curve Isolation Harness
 *
 * Compares ONLY the IOB calculation across adapter implementations.
 * IOB divergence is the #1 source of cross-implementation differences.
 *
 * Usage:
 *   node iob-isolation.js --adapters adapters/oref0-js,adapters/t1pal-oref0-swift \
 *                         --vectors ../../conformance/t1pal/vectors/oref0-endtoend/ \
 *                         [--limit 10] [--json] [--verbose]
 */

const path = require('path');
const { loadAdapter, runVector } = require('./lib/adapter-protocol');
const { loadVectors } = require('./lib/vector-loader');
const { DEFAULT_TOLERANCES, DIVERGENCE_LEVELS } = require('./lib/output-comparator');

const IOB_TOLERANCE = 0.01;         // U — tight tolerance for IOB curve points
const ACTIVITY_TOLERANCE = 0.001;   // U/hr — insulin activity
const PREDICTION_MAE_TOLERANCE = 2.0; // mg/dL — per-trajectory tolerance

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = { adapters: [], vectorDir: null, limit: 0, json: false, verbose: false, category: null, exclude: null };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--adapters':
        opts.adapters = args[++i].split(',').map(a => a.trim());
        break;
      case '--vectors':
        opts.vectorDir = args[++i];
        break;
      case '--limit':
        opts.limit = parseInt(args[++i], 10);
        break;
      case '--json':
        opts.json = true;
        break;
      case '--verbose':
        opts.verbose = true;
        break;
      case '--category':
        opts.category = args[++i];
        break;
      case '--exclude-category':
        opts.exclude = args[++i];
        break;
    }
  }

  if (opts.adapters.length < 2) {
    console.error('Error: --adapters requires at least 2 comma-separated adapter paths');
    console.error('Usage: node iob-isolation.js --adapters a1,a2 --vectors ./vectors/');
    process.exit(1);
  }

  if (!opts.vectorDir) {
    // Default to the t1pal endtoend vectors
    opts.vectorDir = path.resolve(__dirname, '../../conformance/t1pal/vectors/oref0-endtoend');
  }

  return opts;
}

/**
 * Compare IOB prediction curves point-by-point between two adapter outputs.
 * Returns detailed per-tick analysis.
 */
function compareIOBCurves(outputA, outputB) {
  const predsA = outputA?.predictions || {};
  const predsB = outputB?.predictions || {};

  const results = {};

  for (const curve of ['iob', 'zt', 'cob', 'uam']) {
    const a = predsA[curve] || [];
    const b = predsB[curve] || [];

    if (a.length === 0 && b.length === 0) continue;

    const minLen = Math.min(a.length, b.length);
    const maxLen = Math.max(a.length, b.length);
    const diffs = [];
    let totalError = 0;
    let maxDelta = 0;
    let maxDeltaTick = 0;
    let divergenceOnsetTick = null;

    for (let i = 0; i < minLen; i++) {
      const delta = Math.abs(a[i] - b[i]);
      diffs.push({ tick: i, a: a[i], b: b[i], delta: round(delta, 3) });
      totalError += delta;

      if (delta > maxDelta) {
        maxDelta = delta;
        maxDeltaTick = i;
      }

      if (divergenceOnsetTick === null && delta > PREDICTION_MAE_TOLERANCE) {
        divergenceOnsetTick = i;
      }
    }

    const mae = minLen > 0 ? round(totalError / minLen, 3) : null;

    // Compute correlation coefficient
    let correlation = null;
    if (minLen >= 3) {
      const meanA = a.slice(0, minLen).reduce((s, v) => s + v, 0) / minLen;
      const meanB = b.slice(0, minLen).reduce((s, v) => s + v, 0) / minLen;
      let sumAB = 0, sumA2 = 0, sumB2 = 0;
      for (let i = 0; i < minLen; i++) {
        const da = a[i] - meanA;
        const db = b[i] - meanB;
        sumAB += da * db;
        sumA2 += da * da;
        sumB2 += db * db;
      }
      const denom = Math.sqrt(sumA2 * sumB2);
      correlation = denom > 0 ? round(sumAB / denom, 4) : null;
    }

    results[curve] = {
      lengthA: a.length,
      lengthB: b.length,
      compared: minLen,
      mae,
      maxDelta: round(maxDelta, 3),
      maxDeltaTick,
      divergenceOnsetTick,
      correlation,
      pass: mae !== null && mae <= PREDICTION_MAE_TOLERANCE,
      diffs: diffs.length <= 48 ? diffs : undefined, // Only include if reasonable size
    };
  }

  return results;
}

/**
 * Compare IOB state values (scalar IOB, activity, basalIOB) between outputs.
 */
function compareIOBState(outputA, outputB) {
  const stateA = outputA?.state || {};
  const stateB = outputB?.state || {};

  const fields = [];

  for (const [field, tolerance] of [['iob', IOB_TOLERANCE], ['cob', 1.0]]) {
    const a = stateA[field];
    const b = stateB[field];
    if (a == null && b == null) continue;

    const absDiff = (a != null && b != null) ? Math.abs(a - b) : null;
    fields.push({
      field,
      a, b,
      absDiff: absDiff !== null ? round(absDiff, 4) : null,
      tolerance,
      pass: absDiff !== null ? absDiff <= tolerance : false,
    });
  }

  return fields;
}

/**
 * Compare eventualBG and minPredBG between outputs.
 */
function comparePredictionEndpoints(outputA, outputB) {
  const predsA = outputA?.predictions || {};
  const predsB = outputB?.predictions || {};

  const fields = [];

  for (const [field, tolerance] of [['eventualBG', 10.0], ['minPredBG', 10.0]]) {
    const a = predsA[field];
    const b = predsB[field];
    if (a == null && b == null) continue;

    const absDiff = (a != null && b != null) ? Math.abs(a - b) : null;
    fields.push({
      field,
      a, b,
      absDiff: absDiff !== null ? round(absDiff, 2) : null,
      tolerance,
      pass: absDiff !== null ? absDiff <= tolerance : false,
    });
  }

  return fields;
}

/**
 * Run IOB isolation comparison for a single vector across all adapters.
 */
async function isolateVector(vector, adapters, opts) {
  const results = [];

  // Execute vector through each adapter
  const outputs = [];
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
          pair: `${a.adapter} vs ${b.adapter}`,
          vectorId: vector.metadata?.id,
          error: a.error || b.error,
          curves: {},
          state: [],
          endpoints: [],
        });
        continue;
      }

      const curves = compareIOBCurves(a.output, b.output);
      const state = compareIOBState(a.output, b.output);
      const endpoints = comparePredictionEndpoints(a.output, b.output);

      const allCurvesPassed = Object.values(curves).every(c => c.pass);
      const allStatePassed = state.every(s => s.pass);
      const allEndpointsPassed = endpoints.every(e => e.pass);

      results.push({
        pair: `${a.adapter} vs ${b.adapter}`,
        vectorId: vector.metadata?.id,
        pass: allCurvesPassed && allStatePassed && allEndpointsPassed,
        curves,
        state,
        endpoints,
        executionMs: { a: a.elapsedMs, b: b.elapsedMs },
      });
    }
  }

  return results;
}

async function main() {
  const opts = parseArgs();

  // Load adapters
  const adapters = opts.adapters.map(a => {
    const adapterPath = path.resolve(__dirname, a);
    return loadAdapter(adapterPath);
  });

  if (!opts.json) {
    console.log(`IOB Curve Isolation Harness`);
    console.log(`Adapters: ${adapters.map(a => a.manifest.name).join(', ')}`);
    console.log(`Vector dir: ${opts.vectorDir}`);
  }

  // Load vectors
  let vectors = loadVectors(opts.vectorDir, { limit: opts.limit, category: opts.category });
  if (opts.exclude) {
    vectors = vectors.filter(v => v.metadata?.category !== opts.exclude);
  }
  if (!opts.json) {
    console.log(`Vectors loaded: ${vectors.length}\n`);
  }

  // Run isolation for each vector
  const allResults = [];
  let totalPassed = 0;
  let totalFailed = 0;
  let totalErrors = 0;

  for (const vector of vectors) {
    const pairResults = await isolateVector(vector, adapters, opts);
    allResults.push(...pairResults);

    for (const r of pairResults) {
      if (r.error) {
        totalErrors++;
        if (!opts.json) console.log(`  ✗ ${r.vectorId}: ERROR - ${r.error}`);
      } else if (r.pass) {
        totalPassed++;
        if (!opts.json && opts.verbose) console.log(`  ✓ ${r.vectorId}: PASS`);
      } else {
        totalFailed++;
        if (!opts.json) {
          console.log(`  ✗ ${r.vectorId}: FAIL (${r.pair})`);
          // Show which curves diverged
          for (const [curve, data] of Object.entries(r.curves)) {
            if (!data.pass) {
              console.log(`      ${curve}: MAE=${data.mae} maxΔ=${data.maxDelta} onset=tick${data.divergenceOnsetTick}`);
            }
          }
          for (const s of r.state.filter(s => !s.pass)) {
            console.log(`      ${s.field}: Δ=${s.absDiff} (tol=${s.tolerance})`);
          }
        }
      }
    }
  }

  // Compute convergence scores
  const total = totalPassed + totalFailed + totalErrors;
  const convergence = {
    overall: total > 0 ? round(totalPassed / total, 4) : 0,
    iob: computeCurveConvergence(allResults, 'iob'),
    zt: computeCurveConvergence(allResults, 'zt'),
    cob: computeCurveConvergence(allResults, 'cob'),
    uam: computeCurveConvergence(allResults, 'uam'),
  };

  const summary = {
    adapters: adapters.map(a => a.manifest.name),
    vectors: vectors.length,
    comparisons: total,
    passed: totalPassed,
    failed: totalFailed,
    errors: totalErrors,
    convergence,
    worstVectors: findWorstVectors(allResults, 5),
  };

  if (opts.json) {
    console.log(JSON.stringify({ summary, results: allResults }, null, 2));
  } else {
    console.log(`\n${'─'.repeat(60)}`);
    console.log(`IOB Isolation Summary`);
    console.log(`${'─'.repeat(60)}`);
    console.log(`  Passed: ${totalPassed}/${total} (${(convergence.overall * 100).toFixed(1)}%)`);
    console.log(`  Failed: ${totalFailed}  Errors: ${totalErrors}`);
    console.log(`\n  Convergence by curve:`);
    for (const [curve, score] of Object.entries(convergence)) {
      if (curve === 'overall') continue;
      if (score !== null) {
        console.log(`    ${curve}: ${(score * 100).toFixed(1)}%`);
      }
    }
    if (summary.worstVectors.length > 0) {
      console.log(`\n  Worst vectors:`);
      for (const w of summary.worstVectors) {
        console.log(`    ${w.vectorId}: avgMAE=${w.avgMAE}`);
      }
    }
  }

  process.exit(totalFailed + totalErrors > 0 ? 1 : 0);
}

function computeCurveConvergence(results, curveName) {
  const relevant = results.filter(r => r.curves && r.curves[curveName]);
  if (relevant.length === 0) return null;
  const passed = relevant.filter(r => r.curves[curveName].pass).length;
  return round(passed / relevant.length, 4);
}

function findWorstVectors(results, n) {
  return results
    .filter(r => !r.pass && !r.error)
    .map(r => {
      const maes = Object.values(r.curves)
        .filter(c => c.mae !== null)
        .map(c => c.mae);
      const avgMAE = maes.length > 0 ? round(maes.reduce((a, b) => a + b, 0) / maes.length, 2) : 0;
      return { vectorId: r.vectorId, pair: r.pair, avgMAE };
    })
    .sort((a, b) => b.avgMAE - a.avgMAE)
    .slice(0, n);
}

function round(n, places) {
  const factor = Math.pow(10, places);
  return Math.round(n * factor) / factor;
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(2);
});
