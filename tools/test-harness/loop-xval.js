#!/usr/bin/env node
'use strict';

/**
 * loop-xval.js — Loop cross-validation:
 *   Loop-Community vs Loop-Tidepool vs oref0 (all via t1pal-swift adapter)
 *
 * Tests whether the two Loop variants produce identical outputs,
 * and documents how Loop differs from oref0 on the same inputs.
 *
 * Usage: node loop-xval.js [--count N] [--verbose]
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const vectorDir = path.resolve(__dirname, '../../conformance/t1pal/vectors/oref0-endtoend');

const swiftBin = [
  path.resolve(__dirname, '../t1pal-adapter-cli/.build/release/T1PalAdapterCLI'),
  path.resolve(__dirname, '../t1pal-adapter-cli/.build/debug/T1PalAdapterCLI'),
].find(p => fs.existsSync(p));

if (!swiftBin) {
  console.error('ERROR: Swift adapter not built. Run: cd tools/t1pal-adapter-cli && swift build -c release');
  process.exit(1);
}

const limit = process.argv.includes('--count') ?
  parseInt(process.argv[process.argv.indexOf('--count') + 1]) : Infinity;
const verbose = process.argv.includes('--verbose');

const vectors = fs.readdirSync(vectorDir)
  .filter(f => f.startsWith('TV-') && f.endsWith('.json'))
  .sort()
  .slice(0, limit);

const ALGORITHMS = ['Loop', 'Loop-Tidepool', 'oref0'];

function buildInput(v, algorithm) {
  const vi = v.input;
  return {
    mode: 'execute',
    algorithm,
    input: {
      clock: vi.glucoseStatus?.timestamp || new Date().toISOString(),
      glucoseStatus: vi.glucoseStatus || {},
      iob: vi.iob || { iob: 0 },
      profile: vi.profile || {},
      mealData: vi.mealData || {},
      currentTemp: vi.currentTemp || {},
      autosensData: vi.autosensData || { ratio: 1.0 },
      microBolusAllowed: vi.microBolusAllowed || false,
    },
  };
}

function runSwift(inputJson) {
  try {
    const result = execSync(swiftBin, {
      input: JSON.stringify(inputJson),
      timeout: 15000,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return JSON.parse(result.toString());
  } catch (err) {
    return { error: err.stderr ? err.stderr.toString().slice(0, 200) : err.message };
  }
}

// Tracking
const pairs = {
  'LC↔LT': { ebMatch: 0, ebTotal: 0, rateExact: 0, rateClose: 0, rateTotal: 0, ebDiffs: [] },
  'LC↔oref0': { ebMatch: 0, ebTotal: 0, rateExact: 0, rateClose: 0, rateTotal: 0, ebDiffs: [] },
  'LT↔oref0': { ebMatch: 0, ebTotal: 0, rateExact: 0, rateClose: 0, rateTotal: 0, ebDiffs: [] },
};

const results = [];
let errors = 0;

process.stderr.write(`Running ${vectors.length} vectors through Loop-Community, Loop-Tidepool, oref0...\n`);

for (let i = 0; i < vectors.length; i++) {
  const file = vectors[i];
  const vid = file.replace(/TV-(\d+).*/, 'TV-$1');
  process.stderr.write(`\r  [${i+1}/${vectors.length}] ${vid}`);

  const v = JSON.parse(fs.readFileSync(path.join(vectorDir, file), 'utf8'));

  const out = {};
  for (const algo of ALGORITHMS) {
    out[algo] = runSwift(buildInput(v, algo));
  }

  const anyError = ALGORITHMS.some(a => out[a].error);
  if (anyError) {
    errors++;
    if (verbose) {
      const errs = ALGORITHMS.filter(a => out[a].error).map(a => `${a}: ${out[a].error}`);
      process.stderr.write(` — ERROR: ${errs.join('; ')}\n`);
    }
    continue;
  }

  const eb = {
    LC: out['Loop'].predictions?.eventualBG,
    LT: out['Loop-Tidepool'].predictions?.eventualBG,
    oref0: out['oref0'].predictions?.eventualBG,
  };
  const rate = {
    LC: out['Loop'].decision?.rate,
    LT: out['Loop-Tidepool'].decision?.rate,
    oref0: out['oref0'].decision?.rate,
  };

  function comparePair(key, ebA, ebB, rateA, rateB) {
    const p = pairs[key];
    if (ebA != null && ebB != null) {
      p.ebTotal++;
      if (Math.abs(ebA - ebB) < 0.01) p.ebMatch++;
      else p.ebDiffs.push(Math.round(ebA - ebB));
    }
    if (rateA != null && rateB != null) {
      p.rateTotal++;
      if (Math.abs(rateA - rateB) < 0.001) p.rateExact++;
      else if (Math.abs(rateA - rateB) <= 0.5) p.rateClose++;
    }
  }

  comparePair('LC↔LT', eb.LC, eb.LT, rate.LC, rate.LT);
  comparePair('LC↔oref0', eb.LC, eb.oref0, rate.LC, rate.oref0);
  comparePair('LT↔oref0', eb.LT, eb.oref0, rate.LT, rate.oref0);

  results.push({ vector: vid, eb, rate });
}

process.stderr.write('\n\n');

// Summary
function pct(n, d) { return d ? `${Math.round(100*n/d)}%` : 'N/A'; }

console.log('┌─────────────────────────────────────────────────────────────────────────────┐');
console.log('│   Loop Cross-Validation: Loop-Community vs Loop-Tidepool vs oref0          │');
console.log('├──────────────┬──────────────┬──────────────┬──────────────┬────────────────┤');
console.log('│ Metric       │  LC↔LT       │  LC↔oref0    │  LT↔oref0    │ Note           │');
console.log('├──────────────┼──────────────┼──────────────┼──────────────┼────────────────┤');

const row = (label, fn, note) => {
  const cells = ['LC↔LT', 'LC↔oref0', 'LT↔oref0'].map(k => fn(pairs[k]).padEnd(12));
  console.log(`│ ${label.padEnd(12)} │ ${cells[0]} │ ${cells[1]} │ ${cells[2]} │ ${(note||'').padEnd(14)} │`);
};

row('EventualBG', p => `${p.ebMatch}/${p.ebTotal} (${pct(p.ebMatch, p.ebTotal)})`, '');
row('Rate exact', p => `${p.rateExact}/${p.rateTotal} (${pct(p.rateExact, p.rateTotal)})`, '');
row('Rate ±0.5', p => `${p.rateExact+p.rateClose}/${p.rateTotal} (${pct(p.rateExact+p.rateClose, p.rateTotal)})`, '');

// Avg eventualBG difference for cross-algorithm pairs
row('eBG avg Δ', p => {
  if (!p.ebDiffs.length) return '0';
  const avg = p.ebDiffs.reduce((a,b)=>a+b,0)/p.ebDiffs.length;
  return `${avg > 0 ? '+' : ''}${Math.round(avg)} mg/dL`;
}, 'mean diff');

console.log('├──────────────┴──────────────┴──────────────┴──────────────┴────────────────┤');
console.log(`│ Vectors: ${vectors.length}   Errors: ${errors}`.padEnd(78) + '│');
console.log('└─────────────────────────────────────────────────────────────────────────────┘');

// Show interesting divergence
if (verbose) {
  const divergent = results.filter(r =>
    r.rate.LC != null && r.rate.oref0 != null &&
    Math.abs(r.rate.LC - r.rate.oref0) > 0.1
  );
  if (divergent.length > 0) {
    console.log(`\nLoop vs oref0 rate divergence (${divergent.length} vectors):`);
    for (const r of divergent.slice(0, 15)) {
      console.log(`  ${r.vector}: Loop=${r.rate.LC?.toFixed(2)} oref0=${r.rate.oref0?.toFixed(2)} (eBG: ${Math.round(r.eb.LC||0)} vs ${Math.round(r.eb.oref0||0)})`);
    }
  }
}

// Save results
const output = { summary: pairs, vectors: results, errors };
fs.writeFileSync('/tmp/loop-xval-results.json', JSON.stringify(output, null, 2));
process.stderr.write(`Results saved to /tmp/loop-xval-results.json\n`);
