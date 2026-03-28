#!/usr/bin/env node
/**
 * Multi-algorithm prediction comparison against captured predBGs
 *
 * Runs multiple prediction strategies against TV-* vectors and scores
 * each against the captured predBGs.IOB ground truth from real phone runs.
 *
 * Algorithms:
 *   1. persistence  — current BG held flat (zero-order hold)
 *   2. momentum     — linear extrapolation from current delta
 *   3. iob-momentum — momentum adjusted for IOB insulin activity
 *   4. oref0-synth  — full oref0 determine-basal with synthetic IOB array
 *   5. captured      — oracle (ground truth predBGs.IOB, should score ~0)
 *
 * Usage:
 *   node multi-algorithm-comparison.js              # summary table
 *   node multi-algorithm-comparison.js --json       # full JSON
 *   node multi-algorithm-comparison.js --csv        # export CSV
 *   node multi-algorithm-comparison.js --detail     # per-vector breakdown
 *
 * Trace: ALG-VERIFY-006, REQ-060
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '../..');
const VECTORS_DIR = path.join(REPO_ROOT, 'conformance/t1pal/vectors/oref0-endtoend');

// Load oref0 determine-basal
let determineBasal, tempBasalFunctions;
try {
  determineBasal = require(path.join(REPO_ROOT, 'externals/oref0/lib/determine-basal/determine-basal'));
  tempBasalFunctions = require(path.join(REPO_ROOT, 'externals/oref0/lib/basal-set-temp'));
} catch (e) {
  console.error('Warning: oref0 not available, oref0-synth algorithm disabled');
}

// ─── IOB Array Generator (from compare-predictions.js) ───

function generateIobArray(iobSnapshot, dia, currentTemp) {
  const diaMins = (dia || 4) * 60;
  const ticks = 48;
  const iobArray = [];
  const iob0 = iobSnapshot.iob || 0;
  const activity0 = iobSnapshot.activity || 0;
  const basaliob0 = iobSnapshot.basaliob || iobSnapshot.basalIob || 0;
  const iobZT0 = iobSnapshot.iobWithZeroTemp || {};
  const ztIob0 = iobZT0.iob != null ? iobZT0.iob : iob0;
  const ztActivity0 = iobZT0.activity != null ? iobZT0.activity : activity0;
  const ztBasaliob0 = iobZT0.basaliob != null ? iobZT0.basaliob : basaliob0;

  let tau = diaMins / 1.85;
  if (Math.abs(iob0) > 0.01 && Math.abs(activity0) > 0.0001) {
    const r = Math.abs(activity0 / iob0);
    if (r > 0.0001 && r < 0.1) tau = Math.min(diaMins, Math.max(30, 1 / r));
  }
  let tauZT = tau;
  if (Math.abs(ztIob0) > 0.01 && Math.abs(ztActivity0) > 0.0001) {
    const rZT = Math.abs(ztActivity0 / ztIob0);
    if (rZT > 0.0001 && rZT < 0.1) tauZT = Math.min(diaMins, Math.max(30, 1 / rZT));
  }
  const basalFrac = (iob0 !== 0) ? (basaliob0 / iob0) : 0.5;
  const ztBasalFrac = (ztIob0 !== 0) ? (ztBasaliob0 / ztIob0) : 0.5;

  for (let i = 0; i < ticks; i++) {
    const t = i * 5;
    const decay = Math.exp(-t / tau);
    const decayZT = Math.exp(-t / tauZT);
    const iobVal = iob0 * decay;
    const actVal = activity0 * decay;
    const ztIobVal = ztIob0 * decayZT;
    const ztActVal = ztActivity0 * decayZT;

    const tick = {
      iob: iobVal, basaliob: iobVal * basalFrac,
      bolussnooze: 0, activity: actVal,
      lastBolusTime: iobSnapshot.lastBolusTime || (Date.now() - 3600000),
      iobWithZeroTemp: {
        iob: ztIobVal, basaliob: ztIobVal * ztBasalFrac,
        bolussnooze: 0, activity: ztActVal,
        lastBolusTime: 0, time: new Date(Date.now() + t * 60000).toISOString()
      }
    };
    if (i === 0) {
      tick.lastTemp = {
        date: Date.now() - 300000,
        duration: currentTemp?.duration || 0,
        rate: currentTemp?.rate || 0
      };
    }
    iobArray.push(tick);
  }
  return iobArray;
}

// ─── Algorithm Implementations ───

/**
 * 1. Persistence: predict BG stays at current value
 */
function predictPersistence(vector, steps) {
  const bg = vector.input.glucoseStatus.glucose;
  return Array(steps).fill(Math.round(bg));
}

/**
 * 2. Momentum: linear extrapolation from current 5-min delta
 */
function predictMomentum(vector, steps) {
  const bg = vector.input.glucoseStatus.glucose;
  const delta = vector.input.glucoseStatus.delta || 0;
  const trajectory = [];
  for (let i = 0; i < steps; i++) {
    // Each step is 5 minutes, delta is per-5-min change
    // Use damped extrapolation: delta decays over time (trend doesn't persist forever)
    const dampFactor = Math.exp(-i * 0.03); // ~50% damping by step 23 (~2 hrs)
    trajectory.push(Math.round(bg + delta * (i + 1) * dampFactor));
  }
  return trajectory;
}

/**
 * 3. IOB-aware momentum: momentum adjusted for insulin-on-board effect
 *    Combines BG trend with expected insulin activity impact on glucose
 */
function predictIobMomentum(vector, steps) {
  const bg = vector.input.glucoseStatus.glucose;
  const delta = vector.input.glucoseStatus.delta || 0;
  const shortDelta = vector.input.glucoseStatus.shortAvgDelta || delta;
  const longDelta = vector.input.glucoseStatus.longAvgDelta || delta;
  const iob = vector.input.iob.iob || 0;
  const activity = vector.input.iob.activity || 0;
  const sens = vector.input.profile.sensitivity || vector.input.profile.sens || 50;
  const dia = vector.input.profile.dia || 4;
  const diaMins = dia * 60;
  const tau = diaMins / 1.85;

  // Weighted delta: blend short and long-term trends
  const weightedDelta = 0.5 * shortDelta + 0.3 * delta + 0.2 * longDelta;

  const trajectory = [];
  let cumBgEffect = 0;

  for (let i = 0; i < steps; i++) {
    const t = (i + 1) * 5; // minutes from now

    // BG momentum: damped trend extrapolation
    const dampFactor = Math.exp(-i * 0.04);
    const momentumBg = weightedDelta * (i + 1) * dampFactor;

    // IOB effect: insulin activity → BG impact via ISF
    // activity is change in IOB per minute; sens is mg/dL per unit
    const iobDecay = Math.exp(-t / tau);
    const iobAtT = iob * iobDecay;
    const iobConsumed = iob - iobAtT; // insulin absorbed so far
    const bgFromInsulin = -iobConsumed * sens; // negative IOB → BG rises

    const predicted = bg + momentumBg + bgFromInsulin;
    trajectory.push(Math.round(Math.max(39, predicted))); // floor at 39 mg/dL
  }
  return trajectory;
}

/**
 * 4. Weighted-delta: uses short/long avg delta blend, no IOB
 *    Tests if the trend averaging alone improves over raw momentum
 */
function predictWeightedDelta(vector, steps) {
  const bg = vector.input.glucoseStatus.glucose;
  const delta = vector.input.glucoseStatus.delta || 0;
  const shortDelta = vector.input.glucoseStatus.shortAvgDelta || delta;
  const longDelta = vector.input.glucoseStatus.longAvgDelta || delta;

  // Blend: recent trend weighted more, but long-term acts as anchor
  const blended = 0.4 * delta + 0.35 * shortDelta + 0.25 * longDelta;

  const trajectory = [];
  for (let i = 0; i < steps; i++) {
    const dampFactor = Math.exp(-i * 0.035);
    trajectory.push(Math.round(bg + blended * (i + 1) * dampFactor));
  }
  return trajectory;
}

/**
 * 5. oref0 with synthetic IOB array: full determine-basal prediction
 */
function predictOref0Synth(vector, steps) {
  if (!determineBasal) return null;

  const input = vector.input;
  const glucoseStatus = {
    glucose: input.glucoseStatus.glucose,
    delta: input.glucoseStatus.delta,
    short_avgdelta: input.glucoseStatus.shortAvgDelta != null
      ? input.glucoseStatus.shortAvgDelta : input.glucoseStatus.delta,
    long_avgdelta: input.glucoseStatus.longAvgDelta != null
      ? input.glucoseStatus.longAvgDelta : input.glucoseStatus.delta,
    date: Date.now()
  };
  const dia = input.profile.dia || 4;
  const currentTemp = input.currentTemp ? {
    rate: input.currentTemp.rate || 0, duration: input.currentTemp.duration || 0
  } : { rate: 0, duration: 0 };
  const iobSnapshot = {
    iob: input.iob.iob, basaliob: input.iob.basalIob || 0,
    bolussnooze: input.iob.bolusSnooze || 0,
    activity: input.iob.activity || 0,
    lastBolusTime: Date.now() - 60 * 60 * 1000,
    iobWithZeroTemp: input.iob.iobWithZeroTemp || undefined
  };
  const iobData = generateIobArray(iobSnapshot, dia, currentTemp);
  const p = input.profile;
  const profile = {
    current_basal: p.basalRate || p.currentBasal || 1.0,
    sens: p.sensitivity || 50, carb_ratio: p.carbRatio || 10,
    target_bg: ((p.targetLow || 100) + (p.targetHigh || 110)) / 2,
    min_bg: p.targetLow || 100, max_bg: p.targetHigh || 110,
    max_basal: p.maxBasal || 3.0, max_iob: p.maxIob || 5.0,
    max_daily_basal: p.maxDailyBasal || p.basalRate || p.currentBasal || 1.0,
    max_daily_safety_multiplier: p.maxDailySafetyMultiplier || 3,
    current_basal_safety_multiplier: p.currentBasalSafetyMultiplier || 4,
    dia, skip_neutral_temps: false,
    enableSMB_with_bolus: p.enableSMB || false,
    enableSMB_always: p.enableSMB || false,
    enableSMB_with_COB: p.enableSMB || false,
    enableSMB_with_temptarget: false, enableSMB_after_carbs: false,
    enableUAM: p.enableUAM || false,
    maxSMBBasalMinutes: p.maxSMBBasalMinutes || 30,
    maxUAMSMBBasalMinutes: p.maxUAMSMBBasalMinutes || 30,
    SMBInterval: p.smbInterval || 3, bolus_increment: 0.05,
    out_units: 'mg/dL', type: 'current'
  };
  const md = input.mealData || {};
  const mealData = {
    carbs: md.carbs || 0, mealCOB: md.mealCOB || md.cob || 0,
    slopeFromMaxDeviation: md.slopeFromMaxDeviation || 0,
    slopeFromMinDeviation: md.slopeFromMinDeviation || 0,
    lastCarbTime: md.lastCarbTime || (Date.now() - 2 * 60 * 60 * 1000)
  };
  const autosens = { ratio: (input.autosensData || input.autosens || {}).ratio || 1.0 };

  const origErr = console.error;
  console.error = () => {};
  let result;
  try {
    result = determineBasal(
      glucoseStatus, currentTemp, iobData, profile,
      autosens, mealData, tempBasalFunctions,
      false, null, Date.now()
    );
  } catch (e) {
    console.error = origErr;
    return null;
  }
  console.error = origErr;

  const pred = result?.predBGs?.IOB;
  if (!pred || pred.length === 0) return null;
  return pred.slice(0, steps);
}

/**
 * 6. Captured (oracle): use the actual predBGs as the prediction
 */
function predictCaptured(vector, steps) {
  const captured = vector.originalOutput?.predBGs?.IOB;
  if (!captured || captured.length === 0) return null;
  return captured.slice(0, steps);
}

// ─── Algorithm Registry ───

const ALGORITHMS = {
  'persistence':    { name: 'Persistence (zero-order)',    fn: predictPersistence,   simplicity: 1.0 },
  'momentum':       { name: 'Momentum (damped delta)',     fn: predictMomentum,      simplicity: 0.9 },
  'weighted-delta': { name: 'Weighted Delta (blend)',      fn: predictWeightedDelta, simplicity: 0.85 },
  'iob-momentum':   { name: 'IOB-Aware Momentum',         fn: predictIobMomentum,   simplicity: 0.7 },
  'oref0-synth':    { name: 'oref0 (synthetic IOB)',       fn: predictOref0Synth,    simplicity: 0.5 },
  'captured':       { name: 'Captured oref0 (oracle)',     fn: predictCaptured,      simplicity: 0.0 },
};

// ─── Metrics ───

function computeMetrics(predicted, groundTruth) {
  const minLen = Math.min(predicted.length, groundTruth.length);
  if (minLen === 0) return null;

  let sumAbsDiff = 0, sumSqDiff = 0, maxDiff = 0;
  let dirMatch = 0;

  for (let i = 0; i < minLen; i++) {
    const diff = predicted[i] - groundTruth[i];
    sumAbsDiff += Math.abs(diff);
    sumSqDiff += diff * diff;
    maxDiff = Math.max(maxDiff, Math.abs(diff));
  }
  for (let i = 1; i < minLen; i++) {
    const gtDir = Math.sign(groundTruth[i] - groundTruth[i - 1]);
    const predDir = Math.sign(predicted[i] - predicted[i - 1]);
    if (gtDir === predDir) dirMatch++;
  }

  return {
    mae: Math.round(sumAbsDiff / minLen * 10) / 10,
    rmse: Math.round(Math.sqrt(sumSqDiff / minLen) * 10) / 10,
    maxDiff: Math.round(maxDiff * 10) / 10,
    dirAgreement: minLen > 1 ? Math.round(dirMatch / (minLen - 1) * 1000) / 1000 : 0,
    overlap: minLen,
  };
}

// ─── Main ───

const args = process.argv.slice(2);
const jsonFlag = args.includes('--json');
const csvFlag = args.includes('--csv');
const detailFlag = args.includes('--detail');

const files = fs.readdirSync(VECTORS_DIR).filter(f => f.endsWith('.json')).sort();

// Accumulate results per algorithm
const algoResults = {};
for (const key of Object.keys(ALGORITHMS)) {
  algoResults[key] = {
    vectors: [], totalMae: 0, totalRmse: 0, totalDir: 0,
    good: 0, fair: 0, poor: 0, skip: 0, count: 0
  };
}

// Determine max trajectory steps from captured ground truth
const STEPS = 42; // typical captured trajectory length

for (const file of files) {
  const vector = JSON.parse(fs.readFileSync(path.join(VECTORS_DIR, file), 'utf8'));
  const id = vector.metadata?.id || path.basename(file, '.json');
  const groundTruth = vector.originalOutput?.predBGs?.IOB;

  if (!groundTruth || groundTruth.length === 0) {
    for (const key of Object.keys(ALGORITHMS)) {
      algoResults[key].skip++;
    }
    continue;
  }

  // Skip parametric variants (stale predBGs from base vector)
  if (vector.metadata?.parametricVariantOf || vector.metadata?.originalPredBGsStale) {
    for (const key of Object.keys(ALGORITHMS)) {
      algoResults[key].skip++;
    }
    continue;
  }

  for (const [key, algo] of Object.entries(ALGORITHMS)) {
    const predicted = algo.fn(vector, groundTruth.length);

    if (!predicted || predicted.length === 0) {
      algoResults[key].skip++;
      algoResults[key].vectors.push({ id, status: 'skip' });
      continue;
    }

    const metrics = computeMetrics(predicted, groundTruth);
    if (!metrics) {
      algoResults[key].skip++;
      algoResults[key].vectors.push({ id, status: 'skip' });
      continue;
    }

    const status = metrics.mae <= 15 ? 'good' : metrics.mae <= 30 ? 'fair' : 'poor';
    algoResults[key].vectors.push({ id, status, metrics, predicted: predicted.slice(0, 12), groundTruth: groundTruth.slice(0, 12) });
    algoResults[key].totalMae += metrics.mae;
    algoResults[key].totalRmse += metrics.rmse;
    algoResults[key].totalDir += metrics.dirAgreement;
    algoResults[key].count++;
    if (status === 'good') algoResults[key].good++;
    else if (status === 'fair') algoResults[key].fair++;
    else algoResults[key].poor++;
  }
}

// Compute summary per algorithm
const summary = {};
for (const [key, data] of Object.entries(algoResults)) {
  const n = data.count;
  summary[key] = {
    name: ALGORITHMS[key].name,
    simplicity: ALGORITHMS[key].simplicity,
    vectors: n,
    skipped: data.skip,
    good: data.good,
    fair: data.fair,
    poor: data.poor,
    avgMae: n > 0 ? Math.round(data.totalMae / n * 10) / 10 : null,
    avgRmse: n > 0 ? Math.round(data.totalRmse / n * 10) / 10 : null,
    avgDir: n > 0 ? Math.round(data.totalDir / n * 1000) / 1000 : null,
    quality: n > 0 ? Math.round((data.good / n * 1.0 + data.fair / n * 0.5) * 1000) / 1000 : 0,
  };
  // Composite score: same weights as algorithm_score.py v2
  // 40% trajectory MAE + 30% direction + 20% quality + 10% simplicity
  const s = summary[key];
  if (s.avgMae != null) {
    s.compositeScore = Math.round((
      0.40 * Math.max(0, 1 - s.avgMae / 50) +
      0.30 * (s.avgDir || 0) +
      0.20 * s.quality +
      0.10 * s.simplicity
    ) * 1000) / 1000;
  } else {
    s.compositeScore = 0;
  }
}

// ─── Output ───

if (jsonFlag) {
  console.log(JSON.stringify({ summary, detail: detailFlag ? algoResults : undefined }, null, 2));
} else if (csvFlag) {
  // Export all trajectories in wide format
  const csvLines = ['vector_id,step,ground_truth,' + Object.keys(ALGORITHMS).join(',')];
  for (const file of files) {
    const vector = JSON.parse(fs.readFileSync(path.join(VECTORS_DIR, file), 'utf8'));
    const id = vector.metadata?.id || path.basename(file, '.json');
    const gt = vector.originalOutput?.predBGs?.IOB;
    if (!gt || gt.length === 0) continue;

    const maxSteps = Math.min(gt.length, 12);
    // Get predictions from each algorithm
    const predictions = {};
    for (const [key, algo] of Object.entries(ALGORITHMS)) {
      const pred = algo.fn(vector, gt.length);
      predictions[key] = pred || [];
    }

    for (let i = 0; i < maxSteps; i++) {
      const vals = Object.keys(ALGORITHMS).map(k =>
        predictions[k][i] != null ? predictions[k][i] : ''
      ).join(',');
      csvLines.push(`${id},${(i+1)*5},${gt[i]},${vals}`);
    }
  }
  const csvPath = path.join(__dirname, 'multi-algorithm-comparison.csv');
  fs.writeFileSync(csvPath, csvLines.join('\n'));
  console.error(`Exported ${csvLines.length - 1} rows to ${csvPath}`);
  console.log(`Wrote ${csvPath}`);
} else {
  // Summary table
  console.log('\n╔══════════════════════════════════════════════════════════════════════════════════╗');
  console.log('║              Multi-Algorithm Prediction Comparison (vs captured predBGs)         ║');
  console.log('╠══════════════════════════════════════════════════════════════════════════════════╣');
  console.log('║ Algorithm             │ Score │ MAE   │ RMSE  │ Dir%  │ Good │ Fair │ Poor │ N  ║');
  console.log('╟───────────────────────┼───────┼───────┼───────┼───────┼──────┼──────┼──────┼────╢');

  // Sort by composite score descending
  const ranked = Object.entries(summary).sort((a, b) => b[1].compositeScore - a[1].compositeScore);

  for (const [key, s] of ranked) {
    const name = s.name.padEnd(21).slice(0, 21);
    const score = s.compositeScore != null ? s.compositeScore.toFixed(3) : ' N/A ';
    const mae = s.avgMae != null ? s.avgMae.toFixed(1).padStart(5) : '  N/A';
    const rmse = s.avgRmse != null ? s.avgRmse.toFixed(1).padStart(5) : '  N/A';
    const dir = s.avgDir != null ? (s.avgDir * 100).toFixed(1).padStart(5) : '  N/A';
    const good = String(s.good).padStart(4);
    const fair = String(s.fair).padStart(4);
    const poor = String(s.poor).padStart(4);
    const n = String(s.vectors).padStart(3);
    console.log(`║ ${name} │ ${score} │ ${mae} │ ${rmse} │ ${dir} │ ${good} │ ${fair} │ ${poor} │${n} ║`);
  }

  console.log('╚══════════════════════════════════════════════════════════════════════════════════╝');

  console.log(`\nTotal vectors: ${files.length}`);
  console.log(`Scoring: 40% trajectory MAE + 30% direction + 20% quality + 10% simplicity`);
  console.log(`MAE/RMSE in mg/dL, Dir% = directional agreement of trajectory slopes`);
  console.log(`Quality: good(MAE≤15)=1.0 + fair(MAE≤30)=0.5, normalized`);

  if (detailFlag) {
    console.log('\n── Per-vector detail (worst cases per algorithm) ──\n');
    for (const [key, data] of Object.entries(algoResults)) {
      const worst = data.vectors
        .filter(v => v.metrics)
        .sort((a, b) => b.metrics.mae - a.metrics.mae)
        .slice(0, 3);
      if (worst.length === 0) continue;
      console.log(`  ${ALGORITHMS[key].name}:`);
      for (const v of worst) {
        console.log(`    ${v.id}: MAE=${v.metrics.mae} RMSE=${v.metrics.rmse} dir=${(v.metrics.dirAgreement*100).toFixed(0)}%`);
      }
    }
  }
}
