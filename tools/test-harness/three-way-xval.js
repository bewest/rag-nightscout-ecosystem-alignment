#!/usr/bin/env node
'use strict';

/**
 * three-way-xval.js — 3-way cross-validation: oref0-js vs aaps-js vs t1pal-swift
 *
 * Runs all three oref0 implementations on each TV-* vector and compares:
 * - EventualBG agreement across all pairs
 * - Rate agreement (exact and ±0.5)
 * - Prediction curve MAE for each pair
 *
 * Usage: node three-way-xval.js [--count N] [--verbose]
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const vectorDir = path.resolve(__dirname, '../../conformance/t1pal/vectors/oref0-endtoend');
const adapters = {
  'oref0-js': path.resolve(__dirname, 'adapters/oref0-js/index.js'),
  'aaps-js': path.resolve(__dirname, 'adapters/aaps-js/index.js'),
};

// Find Swift adapter binary
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

/**
 * Build adapter-protocol input from a vector.
 * Vectors already use the adapter-contract field names (camelCase).
 * Each adapter internally translates to its native format.
 */
function buildAdapterInput(v) {
  const vi = v.input;
  return {
    mode: 'execute',
    algorithm: 'oref0',
    input: {
      clock: vi.glucoseStatus?.timestamp || new Date().toISOString(),
      glucoseStatus: vi.glucoseStatus || {},
      iob: vi.iob || { iob: 0 },
      profile: vi.profile || {},
      mealData: vi.mealData || {},
      currentTemp: vi.currentTemp || {},
      autosensData: vi.autosensData || { ratio: 1.0 },
      microBolusAllowed: vi.microBolusAllowed || false,
      flatBGsDetected: vi.flatBGsDetected || false,
    },
  };
}

function runNode(adapterPath, inputJson) {
  try {
    const result = execSync(`node ${adapterPath}`, {
      input: JSON.stringify(inputJson),
      timeout: 10000,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return JSON.parse(result.toString());
  } catch (err) {
    return { error: err.stderr ? err.stderr.toString().slice(0, 200) : err.message };
  }
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

function curveMae(a, b) {
  if (!a || !b || !a.length || !b.length) return null;
  const len = Math.min(a.length, b.length);
  let sum = 0;
  for (let i = 0; i < len; i++) sum += Math.abs(a[i] - b[i]);
  return sum / len;
}

// Pair tracking
const pairs = {
  'js↔aaps':  { ebMatch: 0, ebTotal: 0, rateExact: 0, rateClose: 0, rateTotal: 0, iobMae: [], ztMae: [] },
  'js↔swift': { ebMatch: 0, ebTotal: 0, rateExact: 0, rateClose: 0, rateTotal: 0, iobMae: [], ztMae: [] },
  'aaps↔swift': { ebMatch: 0, ebTotal: 0, rateExact: 0, rateClose: 0, rateTotal: 0, iobMae: [], ztMae: [] },
};

const results = [];
let errors = 0;

process.stderr.write(`Running ${vectors.length} vectors through 3 adapters...\n`);

for (let i = 0; i < vectors.length; i++) {
  const file = vectors[i];
  const vid = file.replace(/TV-(\d+).*/, 'TV-$1');
  process.stderr.write(`\r  [${i+1}/${vectors.length}] ${vid}`);

  const v = JSON.parse(fs.readFileSync(path.join(vectorDir, file), 'utf8'));
  const input = buildAdapterInput(v);

  const out = {
    'oref0-js': runNode(adapters['oref0-js'], input),
    'aaps-js': runNode(adapters['aaps-js'], input),
    't1pal-swift': runSwift(input),
  };

  if (out['oref0-js'].error || out['aaps-js'].error || out['t1pal-swift'].error) {
    errors++;
    if (verbose) {
      const errs = Object.entries(out).filter(([,o]) => o.error).map(([k,o]) => `${k}: ${o.error}`);
      process.stderr.write(` — ERROR: ${errs.join('; ')}\n`);
    }
    continue;
  }

  // Extract values
  const eb = {
    js: out['oref0-js'].predictions?.eventualBG,
    aaps: out['aaps-js'].predictions?.eventualBG,
    swift: out['t1pal-swift'].predictions?.eventualBG,
  };
  const rate = {
    js: out['oref0-js'].decision?.rate,
    aaps: out['aaps-js'].decision?.rate,
    swift: out['t1pal-swift'].decision?.rate,
  };
  const pred = {
    js: out['oref0-js'].predictions,
    aaps: out['aaps-js'].predictions,
    swift: out['t1pal-swift'].predictions,
  };

  // Compare all pairs
  function comparePair(key, ebA, ebB, rateA, rateB, predA, predB) {
    const p = pairs[key];
    if (ebA != null && ebB != null) {
      p.ebTotal++;
      if (ebA === ebB) p.ebMatch++;
    }
    if (rateA != null && rateB != null) {
      p.rateTotal++;
      if (rateA === rateB) p.rateExact++;
      else if (Math.abs(rateA - rateB) <= 0.5) p.rateClose++;
    }
    const iob = curveMae(predA?.iob, predB?.iob);
    if (iob != null) p.iobMae.push(iob);
    const zt = curveMae(predA?.zt, predB?.zt);
    if (zt != null) p.ztMae.push(zt);
  }

  comparePair('js↔aaps', eb.js, eb.aaps, rate.js, rate.aaps, pred.js, pred.aaps);
  comparePair('js↔swift', eb.js, eb.swift, rate.js, rate.swift, pred.js, pred.swift);
  comparePair('aaps↔swift', eb.aaps, eb.swift, rate.aaps, rate.swift, pred.aaps, pred.swift);

  results.push({ vector: vid, eb, rate });
}

process.stderr.write('\n\n');

// Summary table
function avg(arr) { return arr.length ? arr.reduce((a,b) => a+b, 0) / arr.length : null; }
function pct(n, d) { return d ? `${Math.round(100*n/d)}%` : 'N/A'; }

console.log('┌──────────────────────────────────────────────────────────────────────────┐');
console.log('│   3-Way oref0 Cross-Validation: oref0-JS vs AAPS-JS vs t1pal-Swift     │');
console.log('├──────────────┬──────────────┬──────────────┬──────────────┬──────────────┤');
console.log('│ Metric       │  js↔aaps     │  js↔swift    │ aaps↔swift   │  Note        │');
console.log('├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤');

for (const [key, p] of Object.entries(pairs)) {
  // only print once per row with all 3 columns
}

// EventualBG row
const ebRow = Object.values(pairs).map(p =>
  `${p.ebMatch}/${p.ebTotal} (${pct(p.ebMatch, p.ebTotal)})`.padEnd(12)
);
console.log(`│ EventualBG   │ ${ebRow[0]} │ ${ebRow[1]} │ ${ebRow[2]} │              │`);

// Rate exact row
const reRow = Object.values(pairs).map(p =>
  `${p.rateExact}/${p.rateTotal} (${pct(p.rateExact, p.rateTotal)})`.padEnd(12)
);
console.log(`│ Rate exact   │ ${reRow[0]} │ ${reRow[1]} │ ${reRow[2]} │              │`);

// Rate ±0.5 row
const rcRow = Object.values(pairs).map(p =>
  `${p.rateExact+p.rateClose}/${p.rateTotal} (${pct(p.rateExact+p.rateClose, p.rateTotal)})`.padEnd(12)
);
console.log(`│ Rate ±0.5    │ ${rcRow[0]} │ ${rcRow[1]} │ ${rcRow[2]} │              │`);

// IOB MAE row
const iobRow = Object.values(pairs).map(p => {
  const v = avg(p.iobMae);
  return (v != null ? v.toFixed(3) : 'N/A').padEnd(12);
});
console.log(`│ IOB MAE      │ ${iobRow[0]} │ ${iobRow[1]} │ ${iobRow[2]} │ mg/dL        │`);

// ZT MAE row
const ztRow = Object.values(pairs).map(p => {
  const v = avg(p.ztMae);
  return (v != null ? v.toFixed(3) : 'N/A').padEnd(12);
});
console.log(`│ ZT MAE       │ ${ztRow[0]} │ ${ztRow[1]} │ ${ztRow[2]} │ mg/dL        │`);

console.log('├──────────────┴──────────────┴──────────────┴──────────────┴──────────────┤');
console.log(`│ Vectors: ${vectors.length}   Errors: ${errors}`.padEnd(75) + '│');
console.log('└──────────────────────────────────────────────────────────────────────────┘');

// Vectors where all 3 disagree on eventualBG
const tripleDisagree = results.filter(r =>
  r.eb.js != null && r.eb.aaps != null && r.eb.swift != null &&
  !(r.eb.js === r.eb.aaps && r.eb.aaps === r.eb.swift)
);
if (tripleDisagree.length > 0) {
  console.log(`\nEventualBG divergence (${tripleDisagree.length} vectors):`);
  for (const r of tripleDisagree.slice(0, 15)) {
    const jsAaps = r.eb.js === r.eb.aaps ? '≡' : `Δ${r.eb.aaps - r.eb.js}`;
    const jsSwift = r.eb.js === r.eb.swift ? '≡' : `Δ${r.eb.swift - r.eb.js}`;
    console.log(`  ${r.vector}: js=${r.eb.js} aaps=${r.eb.aaps}(${jsAaps}) swift=${r.eb.swift}(${jsSwift})`);
  }
}

// Vectors where rate differs across implementations
const rateDiverge = results.filter(r =>
  r.rate.js != null && r.rate.aaps != null && r.rate.swift != null &&
  !(r.rate.js === r.rate.aaps && r.rate.aaps === r.rate.swift)
);
if (rateDiverge.length > 0 && verbose) {
  console.log(`\nRate divergence (${rateDiverge.length} vectors):`);
  for (const r of rateDiverge.slice(0, 15)) {
    console.log(`  ${r.vector}: js=${r.rate.js} aaps=${r.rate.aaps} swift=${r.rate.swift}`);
  }
}

// Save results
const output = { summary: pairs, vectors: results, errors };
fs.writeFileSync('/tmp/three-way-xval-results.json', JSON.stringify(output, null, 2));
process.stderr.write(`Results saved to /tmp/three-way-xval-results.json\n`);
