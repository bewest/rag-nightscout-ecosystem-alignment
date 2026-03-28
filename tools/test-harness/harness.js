#!/usr/bin/env node
'use strict';

/**
 * Test Harness Orchestrator
 *
 * CLI entry point for the layered algorithm testing harness.
 *
 * Usage:
 *   node harness.js --layer <validate|equivalence|benchmark|research> [options]
 *
 * Layers:
 *   validate     (L0) — Validate vectors, adapters, input assembly
 *   equivalence  (L1) — Test same-algorithm cross-implementation equivalence
 *   benchmark    (L2) — Compare different algorithms on same vectors
 *   research     (L3) — R&D with agent effect injection
 *
 * Common options:
 *   --vectors <dir>     Path to vectors directory
 *   --adapters <dirs>   Comma-separated adapter directories
 *   --limit <n>         Max vectors to process
 *   --ids <ids>         Comma-separated vector IDs
 *   --json              Output as JSON (default: human-readable)
 *   --verbose           Include extra detail
 *
 * Layer 3 options:
 *   --agents <names>    Comma-separated agent presets (exercise, post-exercise, breakfast-boost, illness)
 */

const path = require('path');
const { runValidation } = require('./layers/validate');
const { runEquivalence } = require('./layers/equivalence');
const { runBenchmark } = require('./layers/benchmark');
const { runResearch, AGENT_PRESETS } = require('./layers/research');
const { formatReport, formatJSON } = require('./lib/report');

// ── Argument Parsing ────────────────────────────────────────────────

function parseArgs(argv) {
  const args = {
    layer: null,
    vectorDir: null,
    adapterDirs: [],
    limit: null,
    ids: null,
    json: false,
    verbose: false,
    agents: [],
  };

  const defaultVectorDir = path.resolve(__dirname, '../../conformance/t1pal/vectors/oref0-endtoend');
  const defaultAdapterDir = path.resolve(__dirname, 'adapters/oref0-js');

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    switch (arg) {
      case '--layer':
      case '-l':
        args.layer = argv[++i];
        break;
      case '--vectors':
      case '-v':
        args.vectorDir = path.resolve(argv[++i]);
        break;
      case '--adapters':
      case '-a':
        args.adapterDirs = argv[++i].split(',').map(d => path.resolve(d.trim()));
        break;
      case '--limit':
      case '-n':
        args.limit = parseInt(argv[++i], 10);
        break;
      case '--ids':
        args.ids = argv[++i].split(',').map(s => s.trim());
        break;
      case '--json':
        args.json = true;
        break;
      case '--verbose':
        args.verbose = true;
        break;
      case '--agents':
        args.agents = argv[++i].split(',').map(s => s.trim());
        break;
      case '--help':
      case '-h':
        printUsage();
        process.exit(0);
        break;
      default:
        // Positional: first unknown arg is the layer
        if (!args.layer && !arg.startsWith('-')) {
          args.layer = arg;
        }
    }
  }

  // Defaults
  if (!args.vectorDir) args.vectorDir = defaultVectorDir;
  if (args.adapterDirs.length === 0) args.adapterDirs = [defaultAdapterDir];

  return args;
}

function printUsage() {
  console.log(`
Test Harness — Layered Algorithm Testing for Nightscout AID Ecosystem

Usage: node harness.js --layer <layer> [options]

Layers:
  validate     (L0) Validate vectors, adapters, input assembly
  equivalence  (L1) Same-algorithm cross-implementation equivalence
  benchmark    (L2) Cross-algorithm comparison
  research     (L3) R&D with agent effect injection

Options:
  --vectors <dir>     Vector directory (default: conformance/t1pal/vectors/oref0-endtoend)
  --adapters <dirs>   Comma-separated adapter dirs (default: adapters/oref0-js)
  --limit <n>         Max vectors
  --ids <ids>         Specific vector IDs (comma-separated)
  --json              JSON output
  --verbose           Extra detail
  --agents <names>    Agent presets for L3: ${Object.keys(AGENT_PRESETS).join(', ')}

Examples:
  node harness.js --layer validate
  node harness.js --layer equivalence --limit 10
  node harness.js --layer equivalence --adapters adapters/oref0-js,adapters/t1pal-oref0-swift
  node harness.js --layer research --agents exercise --limit 5
`);
}

// ── Main ────────────────────────────────────────────────────────────

async function main() {
  const args = parseArgs(process.argv);

  if (!args.layer) {
    printUsage();
    process.exit(1);
  }

  let result;

  switch (args.layer) {
    case 'validate':
    case 'l0':
    case '0':
      result = await runValidation({
        vectorDir: args.vectorDir,
        adapterDirs: args.adapterDirs,
        verbose: args.verbose,
      });
      break;

    case 'equivalence':
    case 'equiv':
    case 'l1':
    case '1':
      result = await runEquivalence({
        vectorDir: args.vectorDir,
        adapterDirs: args.adapterDirs,
        tolerances: {},
        limit: args.limit,
        ids: args.ids,
        verbose: args.verbose,
      });
      break;

    case 'benchmark':
    case 'bench':
    case 'l2':
    case '2':
      result = await runBenchmark({
        vectorDir: args.vectorDir,
        adapterDirs: args.adapterDirs,
        limit: args.limit,
        ids: args.ids,
      });
      break;

    case 'research':
    case 'r&d':
    case 'l3':
    case '3':
      result = await runResearch({
        vectorDir: args.vectorDir,
        adapterDirs: args.adapterDirs,
        agents: args.agents,
        limit: args.limit,
        ids: args.ids,
      });
      break;

    default:
      console.error(`Unknown layer: ${args.layer}`);
      printUsage();
      process.exit(1);
  }

  // Output
  if (args.json) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    // Human-readable formatting
    if (result.error) {
      console.error(`Error: ${result.error}`);
      process.exit(1);
    }

    switch (args.layer) {
      case 'validate':
      case 'l0':
      case '0':
        formatValidationOutput(result);
        break;

      case 'equivalence':
      case 'equiv':
      case 'l1':
      case '1':
        formatEquivalenceOutput(result, args.verbose);
        break;

      case 'benchmark':
      case 'bench':
      case 'l2':
      case '2':
        formatBenchmarkOutput(result);
        break;

      case 'research':
      case 'r&d':
      case 'l3':
      case '3':
        formatResearchOutput(result);
        break;
    }
  }

  // Exit code: 0 if all passed, 1 if any failed
  const passed = result.pass !== false &&
    (result.summary?.passRate === undefined || result.summary.passRate > 0);
  process.exit(passed ? 0 : 1);
}

// ── Formatters ──────────────────────────────────────────────────────

function formatValidationOutput(result) {
  console.log('\n\x1b[1mLayer 0: Validation\x1b[0m');
  console.log('─'.repeat(60));

  if (result.vectors) {
    const v = result.vectors;
    console.log(`Vectors: ${v.total} loaded, ${v.schemaValid} valid, ${v.schemaInvalid} invalid`);
    console.log(`Categories: ${Object.entries(v.categories).map(([k, n]) => `${k}(${n})`).join(', ')}`);
  }

  for (const a of result.adapters || []) {
    const icon = a.healthy ? '\x1b[32m✓\x1b[0m' : '\x1b[31m✗\x1b[0m';
    console.log(`${icon} Adapter: ${a.name} ${a.healthy ? '' : `— ${a.error || a.describeResult?.error}`}`);
  }

  for (const ia of result.inputAssembly || []) {
    const icon = ia.valid ? '\x1b[32m✓\x1b[0m' : '\x1b[33m△\x1b[0m';
    const warnings = ia.warnings?.length ? ` (${ia.warnings.length} warnings)` : '';
    console.log(`  ${icon} Input assembly: ${ia.adapter} × ${ia.vectorId}${warnings}`);
  }

  const icon = result.pass ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m';
  console.log(`\nResult: ${icon}\n`);
}

function formatEquivalenceOutput(result, verbose) {
  console.log('\n\x1b[1mLayer 1: Equivalence Testing\x1b[0m');
  console.log('─'.repeat(60));
  console.log(`Mode: ${result.mode}`);
  console.log(`Adapters: ${result.adapters?.join(', ')}`);
  console.log(`Vectors: ${result.vectorCount}\n`);

  for (const vr of result.vectorResults || []) {
    const icon = vr.pass ? '\x1b[32m✓\x1b[0m' : '\x1b[31m✗\x1b[0m';
    const vid = (vr.vectorId || '???').padEnd(8);

    if (!vr.pass || verbose) {
      // Show details for failures (and all if verbose)
      const details = [];
      for (const [name, ar] of Object.entries(vr.adapterResults)) {
        if (ar.error) {
          details.push(`${name}: ERROR ${ar.error}`);
        } else if (ar.vsExpected) {
          const fails = ar.vsExpected.fields?.filter(f => !f.pass) || [];
          if (fails.length > 0) {
            details.push(fails.map(f =>
              `${f.field}: got ${f.valueA}, expected ${f.valueB} (Δ${f.absDiff})`
            ).join('; '));
          }
        }
      }
      console.log(`  ${icon} ${vid} ${details.join(' | ')}`);
    } else {
      console.log(`  ${icon} ${vid}`);
    }
  }

  const s = result.summary || {};
  const pct = ((s.passRate || 0) * 100).toFixed(1);
  const color = s.passRate === 1 ? '\x1b[32m' : '\x1b[31m';
  console.log(`\n${color}${s.passed}/${result.vectorCount} passed (${pct}%)\x1b[0m\n`);
}

function formatBenchmarkOutput(result) {
  console.log('\n\x1b[1mLayer 2: Algorithm Benchmarking\x1b[0m');
  console.log('─'.repeat(60));
  console.log(`Adapters: ${result.adapters?.map(a => `${a.name}(${a.algorithm})`).join(', ')}`);
  console.log(`Vectors: ${result.vectorCount}\n`);

  // Divergence matrix
  if (result.divergenceMatrix) {
    console.log('Divergence Matrix:');
    for (const [a, pairs] of Object.entries(result.divergenceMatrix)) {
      for (const [b, counts] of Object.entries(pairs)) {
        console.log(`  ${a} vs ${b}: none=${counts.none} minor=${counts.minor} mod=${counts.moderate} sig=${counts.significant} opp=${counts.opposite}`);
      }
    }
  }

  // Per-adapter stats
  if (result.adapterSummaries) {
    console.log('\nAdapter Statistics:');
    for (const [name, stats] of Object.entries(result.adapterSummaries)) {
      console.log(`  ${name}: ${stats.successCount} successful, ${stats.errorCount} errors`);
      if (stats.rateStats) {
        const r = stats.rateStats;
        console.log(`    Rate: min=${r.min} max=${r.max} mean=${r.mean} median=${r.median}`);
      }
    }
  }
  console.log('');
}

function formatResearchOutput(result) {
  console.log('\n\x1b[1mLayer 3: R&D Research\x1b[0m');
  console.log('─'.repeat(60));
  console.log(`Agents: ${result.experiment?.agents?.map(a => a.source).join(', ') || 'none'}`);
  console.log(`Vectors: ${result.experiment?.vectorCount}\n`);

  // Impact summaries
  for (const [key, stats] of Object.entries(result)) {
    if (!key.startsWith('impact_')) continue;
    const name = key.replace('impact_', '');
    console.log(`  ${name}:`);
    console.log(`    Avg rate change: ${stats.avgRateChange != null ? stats.avgRateChange.toFixed(3) + ' U/hr' : 'N/A'}`);
    console.log(`    Avg BG change:   ${stats.avgBGChange != null ? stats.avgBGChange.toFixed(1) + ' mg/dL' : 'N/A'}`);
    console.log(`    Vectors affected: ${stats.vectorsAffected}/${stats.totalVectors}`);
  }
  console.log('');
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
