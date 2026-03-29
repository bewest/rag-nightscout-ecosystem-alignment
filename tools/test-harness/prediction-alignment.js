'use strict';

/**
 * Prediction Trajectory Alignment Harness
 *
 * Compares prediction arrays point-by-point across adapter implementations.
 * Isolates each of the 4 oref0 curves (IOB, COB, UAM, ZT) and the combined
 * Loop prediction to identify where implementations diverge.
 *
 * Usage:
 *   node prediction-alignment.js --adapters adapters/oref0-js,adapters/t1pal-oref0-swift \
 *                                --vectors ../../conformance/t1pal/vectors/oref0-endtoend/ \
 *                                [--limit 10] [--json] [--csv]
 */

const path = require('path');
const { loadAdapter, runVector } = require('./lib/adapter-protocol');
const { loadVectors, extractExpected } = require('./lib/vector-loader');

const TICK_INTERVAL_MIN = 5;
const HORIZON_TICKS = 48;

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    adapters: [], vectorDir: null, limit: 0,
    json: false, csv: false, verbose: false,
    includeGround: false, // compare against ground-truth from vector
    category: null, // filter vectors by category (e.g. 'basal-adjustment', 'synthetic')
    exclude: null,  // exclude vectors by category
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--adapters': opts.adapters = args[++i].split(',').map(a => a.trim()); break;
      case '--vectors': opts.vectorDir = args[++i]; break;
      case '--limit': opts.limit = parseInt(args[++i], 10); break;
      case '--json': opts.json = true; break;
      case '--csv': opts.csv = true; break;
      case '--verbose': opts.verbose = true; break;
      case '--ground-truth': opts.includeGround = true; break;
      case '--category': opts.category = args[++i]; break;
      case '--exclude-category': opts.exclude = args[++i]; break;
    }
  }

  if (opts.adapters.length < 1) {
    console.error('Error: --adapters requires at least 1 adapter path');
    console.error('  Use --ground-truth to compare against captured predBGs');
    process.exit(1);
  }

  if (!opts.vectorDir) {
    opts.vectorDir = path.resolve(__dirname, '../../conformance/t1pal/vectors/oref0-endtoend');
  }

  return opts;
}

/**
 * Align two prediction arrays for comparison.
 * Handles different lengths by padding shorter with last value.
 */
function alignArrays(a, b) {
  const maxLen = Math.max(a.length, b.length);
  const aligned = { a: [], b: [], compared: 0 };

  for (let i = 0; i < maxLen; i++) {
    aligned.a.push(i < a.length ? a[i] : a[a.length - 1]);
    aligned.b.push(i < b.length ? b[i] : b[b.length - 1]);
    aligned.compared++;
  }

  return aligned;
}

/**
 * Compute detailed statistics for a pair of aligned prediction arrays.
 */
function computeTrajectoryStats(a, b) {
  if (a.length === 0 || b.length === 0) return null;

  const n = Math.min(a.length, b.length);
  const deltas = [];
  let totalError = 0;
  let maxDelta = 0;
  let maxDeltaTick = 0;
  let rmse = 0;
  let divergenceOnset = null;

  for (let i = 0; i < n; i++) {
    const delta = a[i] - b[i];
    const absDelta = Math.abs(delta);
    deltas.push(delta);
    totalError += absDelta;
    rmse += delta * delta;

    if (absDelta > maxDelta) {
      maxDelta = absDelta;
      maxDeltaTick = i;
    }

    if (divergenceOnset === null && absDelta > 5.0) {
      divergenceOnset = i;
    }
  }

  const mae = round(totalError / n, 3);
  rmse = round(Math.sqrt(rmse / n), 3);

  // Trend: is the error growing or stable?
  let earlyMAE = 0, lateMAE = 0;
  const midpoint = Math.floor(n / 2);
  for (let i = 0; i < midpoint; i++) earlyMAE += Math.abs(deltas[i]);
  for (let i = midpoint; i < n; i++) lateMAE += Math.abs(deltas[i]);
  earlyMAE = midpoint > 0 ? round(earlyMAE / midpoint, 3) : 0;
  lateMAE = (n - midpoint) > 0 ? round(lateMAE / (n - midpoint), 3) : 0;

  const trend = lateMAE > earlyMAE * 1.5 ? 'growing' :
                lateMAE < earlyMAE * 0.5 ? 'shrinking' : 'stable';

  // Correlation
  const meanA = a.slice(0, n).reduce((s, v) => s + v, 0) / n;
  const meanB = b.slice(0, n).reduce((s, v) => s + v, 0) / n;
  let sumAB = 0, sumA2 = 0, sumB2 = 0;
  for (let i = 0; i < n; i++) {
    sumAB += (a[i] - meanA) * (b[i] - meanB);
    sumA2 += (a[i] - meanA) ** 2;
    sumB2 += (b[i] - meanB) ** 2;
  }
  const denom = Math.sqrt(sumA2 * sumB2);
  const correlation = denom > 0 ? round(sumAB / denom, 4) : null;

  // Endpoint delta (final prediction value)
  const endpointDelta = round(a[n - 1] - b[n - 1], 2);

  return {
    points: n,
    mae, rmse,
    maxDelta: round(maxDelta, 2),
    maxDeltaTick,
    maxDeltaTimeMin: maxDeltaTick * TICK_INTERVAL_MIN,
    divergenceOnsetTick: divergenceOnset,
    divergenceOnsetMin: divergenceOnset !== null ? divergenceOnset * TICK_INTERVAL_MIN : null,
    correlation,
    endpointDelta,
    trend,
    earlyMAE, lateMAE,
  };
}

/**
 * Compare predictions between adapter runs for a single vector.
 */
async function compareVectorPredictions(vector, adapters, opts) {
  const outputs = [];

  for (const adapter of adapters) {
    const result = await runVector(adapter, vector, { mode: 'execute' });
    outputs.push(result);
  }

  // Optionally include ground truth from vector
  if (opts.includeGround && vector.originalOutput?.predBGs) {
    const ground = vector.originalOutput.predBGs;
    outputs.push({
      adapter: '_ground-truth',
      output: {
        predictions: {
          iob: ground.IOB || ground.iob || [],
          zt: ground.ZT || ground.zt || [],
          cob: ground.COB || ground.cob || [],
          uam: ground.UAM || ground.uam || [],
        },
      },
      error: null,
    });
  }

  const comparisons = [];

  for (let i = 0; i < outputs.length; i++) {
    for (let j = i + 1; j < outputs.length; j++) {
      const a = outputs[i];
      const b = outputs[j];

      if (a.error || b.error) {
        comparisons.push({
          vectorId: vector.metadata?.id,
          pair: `${a.adapter} vs ${b.adapter}`,
          error: a.error || b.error,
        });
        continue;
      }

      const predsA = a.output?.predictions || {};
      const predsB = b.output?.predictions || {};
      const curveStats = {};
      let allPass = true;

      for (const curve of ['iob', 'zt', 'cob', 'uam']) {
        const arrA = predsA[curve] || [];
        const arrB = predsB[curve] || [];

        if (arrA.length === 0 && arrB.length === 0) continue;

        if (arrA.length === 0 || arrB.length === 0) {
          curveStats[curve] = {
            present: { a: arrA.length > 0, b: arrB.length > 0 },
            stats: null,
            pass: false,
          };
          allPass = false;
          continue;
        }

        const stats = computeTrajectoryStats(arrA, arrB);
        const pass = stats.mae <= 2.0 && stats.correlation !== null && stats.correlation >= 0.95;

        curveStats[curve] = { present: { a: true, b: true }, stats, pass };
        if (!pass) allPass = false;
      }

      // Decision-level comparison
      const decA = a.output?.decision || {};
      const decB = b.output?.decision || {};
      const decisionDelta = {
        rate: decA.rate != null && decB.rate != null ? round(decA.rate - decB.rate, 3) : null,
        smb: decA.smb != null && decB.smb != null ? round(decA.smb - decB.smb, 3) : null,
      };

      comparisons.push({
        vectorId: vector.metadata?.id,
        pair: `${a.adapter} vs ${b.adapter}`,
        pass: allPass,
        curves: curveStats,
        decision: decisionDelta,
        eventualBG: {
          a: predsA.eventualBG,
          b: predsB.eventualBG,
          delta: predsA.eventualBG != null && predsB.eventualBG != null
            ? round(predsA.eventualBG - predsB.eventualBG, 2) : null,
        },
      });
    }
  }

  return comparisons;
}

async function main() {
  const opts = parseArgs();

  const adapters = opts.adapters.map(a => loadAdapter(path.resolve(__dirname, a)));
  const vectors = loadVectors(opts.vectorDir, { limit: opts.limit, category: opts.category });
  const filtered = opts.exclude
    ? vectors.filter(v => v.metadata?.category !== opts.exclude)
    : vectors;

  if (!opts.json && !opts.csv) {
    console.log(`Prediction Trajectory Alignment`);
    console.log(`Adapters: ${adapters.map(a => a.manifest.name).join(', ')}${opts.includeGround ? ' + ground-truth' : ''}`);
    console.log(`Vectors: ${filtered.length}${opts.category ? ` (category: ${opts.category})` : ''}${opts.exclude ? ` (excluding: ${opts.exclude})` : ''}\n`);
  }

  const allComparisons = [];
  let passed = 0, failed = 0, errors = 0;

  for (const vector of filtered) {
    const comps = await compareVectorPredictions(vector, adapters, opts);
    allComparisons.push(...comps);

    for (const c of comps) {
      if (c.error) { errors++; continue; }
      if (c.pass) { passed++; } else { failed++; }

      if (!opts.json && !opts.csv) {
        const icon = c.pass ? '✓' : '✗';
        const parts = [];
        for (const [curve, data] of Object.entries(c.curves)) {
          if (data.stats) {
            parts.push(`${curve}:MAE=${data.stats.mae}`);
          }
        }
        if (opts.verbose || !c.pass) {
          console.log(`  ${icon} ${c.vectorId} (${c.pair}): ${parts.join(' ')}`);
          if (!c.pass && opts.verbose) {
            for (const [curve, data] of Object.entries(c.curves)) {
              if (data.stats && !data.pass) {
                const s = data.stats;
                console.log(`      ${curve}: MAE=${s.mae} RMSE=${s.rmse} maxΔ=${s.maxDelta}@${s.maxDeltaTimeMin}min r=${s.correlation} trend=${s.trend}`);
              }
            }
          }
        }
      }
    }
  }

  // Aggregate statistics per curve
  const curveAggregates = {};
  for (const curve of ['iob', 'zt', 'cob', 'uam']) {
    const relevant = allComparisons
      .filter(c => c.curves && c.curves[curve]?.stats)
      .map(c => c.curves[curve].stats);

    if (relevant.length === 0) continue;

    curveAggregates[curve] = {
      count: relevant.length,
      passRate: round(relevant.filter((_, i) =>
        allComparisons.filter(c => c.curves?.[curve]?.stats)[i] &&
        allComparisons.filter(c => c.curves?.[curve]?.pass)[0] !== undefined
      ).length / relevant.length, 3),
      avgMAE: round(relevant.reduce((s, r) => s + r.mae, 0) / relevant.length, 3),
      maxMAE: round(Math.max(...relevant.map(r => r.mae)), 3),
      avgCorrelation: round(
        relevant.filter(r => r.correlation !== null)
          .reduce((s, r) => s + r.correlation, 0) /
        relevant.filter(r => r.correlation !== null).length, 4),
      trendDistribution: {
        growing: relevant.filter(r => r.trend === 'growing').length,
        stable: relevant.filter(r => r.trend === 'stable').length,
        shrinking: relevant.filter(r => r.trend === 'shrinking').length,
      },
    };
  }

  const total = passed + failed + errors;
  const summary = {
    adapters: adapters.map(a => a.manifest.name),
    includesGroundTruth: opts.includeGround,
    vectors: filtered.length,
    comparisons: total,
    passed, failed, errors,
    convergence: total > 0 ? round(passed / total, 4) : 0,
    curveAggregates,
  };

  if (opts.csv) {
    console.log('vectorId,pair,curve,mae,rmse,maxDelta,maxDeltaMin,correlation,trend,pass');
    for (const c of allComparisons) {
      if (c.error) continue;
      for (const [curve, data] of Object.entries(c.curves)) {
        if (!data.stats) continue;
        const s = data.stats;
        console.log(`${c.vectorId},${c.pair},${curve},${s.mae},${s.rmse},${s.maxDelta},${s.maxDeltaTimeMin},${s.correlation},${s.trend},${data.pass}`);
      }
    }
  } else if (opts.json) {
    console.log(JSON.stringify({ summary, comparisons: allComparisons }, null, 2));
  } else {
    console.log(`\n${'─'.repeat(60)}`);
    console.log(`Prediction Alignment Summary`);
    console.log(`${'─'.repeat(60)}`);
    console.log(`  Passed: ${passed}/${total} (${(summary.convergence * 100).toFixed(1)}%)`);
    console.log(`  Failed: ${failed}  Errors: ${errors}\n`);

    for (const [curve, agg] of Object.entries(curveAggregates)) {
      console.log(`  ${curve.toUpperCase()} curve:`);
      console.log(`    Avg MAE: ${agg.avgMAE} mg/dL  Max MAE: ${agg.maxMAE} mg/dL`);
      console.log(`    Avg correlation: ${agg.avgCorrelation}`);
      console.log(`    Trend: ${agg.trendDistribution.growing} growing, ${agg.trendDistribution.stable} stable, ${agg.trendDistribution.shrinking} shrinking`);
    }
  }

  process.exit(failed + errors > 0 ? 1 : 0);
}

function round(n, places) {
  const factor = Math.pow(10, places);
  return Math.round(n * factor) / factor;
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(2);
});
