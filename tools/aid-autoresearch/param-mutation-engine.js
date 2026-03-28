#!/usr/bin/env node
/**
 * Parameter Mutation Engine for oref0 Algorithm Scoring
 *
 * Searches the profile parameter space to find configurations that maximize
 * the composite score. Operates as a mutation layer between vector inputs
 * and oref0 determine-basal: the vector's profile provides the baseline,
 * and mutations apply relative adjustments.
 *
 * Strategies:
 *   - random: Uniform random sampling across parameter space
 *   - walk:   Random walk from current best (small perturbations)
 *   - grid:   Systematic grid search over priority-1 parameters
 *
 * Usage:
 *   node param-mutation-engine.js                    # 20 random iterations
 *   node param-mutation-engine.js --strategy walk --iterations 50
 *   node param-mutation-engine.js --strategy grid    # grid over P1 params
 *   node param-mutation-engine.js --json             # JSON output
 *   node param-mutation-engine.js --apply <file>     # apply best mutation to vectors and re-score
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '../..');
const determineBasal = require(path.join(REPO_ROOT, 'externals/oref0/lib/determine-basal/determine-basal'));
const tempBasalFunctions = require(path.join(REPO_ROOT, 'externals/oref0/lib/basal-set-temp'));

const VECTOR_DIR = path.join(REPO_ROOT, 'conformance/t1pal/vectors/oref0-endtoend');

// Tolerances (same as run-oref0-endtoend.js)
const TOL = { rate: 0.05, eventualBG: 10, insulinReq: 0.1, iob: 0.05 };

// ── Parameter Space Definition ──────────────────────────────────────────

const PARAM_SPACE = {
  // Priority 1: Core dosing (continuous)
  sens_factor:    { min: 0.7,  max: 1.5,  step: 0.05, default: 1.0, desc: 'ISF multiplier' },
  cr_factor:      { min: 0.7,  max: 1.5,  step: 0.05, default: 1.0, desc: 'Carb ratio multiplier' },
  basal_factor:   { min: 0.7,  max: 1.5,  step: 0.05, default: 1.0, desc: 'Basal rate multiplier' },
  max_basal:      { min: 1.0,  max: 6.0,  step: 0.5,  default: 3.0, desc: 'Max temp basal U/hr' },
  target_shift:   { min: -15,  max: 15,   step: 5,    default: 0,   desc: 'Target BG shift mg/dL' },

  // Priority 2: Safety limits & DIA
  max_iob:        { min: 2.0,  max: 10.0, step: 0.5,  default: 5.0, desc: 'Max IOB limit' },
  dia:            { min: 3.0,  max: 6.0,  step: 0.5,  default: 4.0, desc: 'Duration of insulin action' },

  // Priority 3: Feature flags (boolean → 0/1)
  enable_smb:     { min: 0,    max: 1,    step: 1,    default: 0,   desc: 'Enable SMB' },
  enable_uam:     { min: 0,    max: 1,    step: 1,    default: 0,   desc: 'Enable UAM' },

  // Priority 4: SMB tuning
  smb_minutes:    { min: 15,   max: 60,   step: 15,   default: 30,  desc: 'Max SMB basal minutes' },
};

// ── IOB Array Generator (same as run-oref0-endtoend.js) ─────────────────

function generateIobArray(iobSnapshot, dia, currentTemp) {
  const diaMins = (dia || 4) * 60;
  const ticks = 48;
  const iobArray = [];
  const iob0 = iobSnapshot.iob || 0;
  const activity0 = iobSnapshot.activity || 0;

  let tau = diaMins / 1.85;
  if (Math.abs(iob0) > 0.01 && Math.abs(activity0) > 0.0001) {
    const r = Math.abs(activity0 / iob0);
    if (r > 0.0001 && r < 0.1) tau = Math.min(diaMins, Math.max(30, 1 / r));
  }

  // Separate tau for iobWithZeroTemp if available
  const zwt = iobSnapshot.iobWithZeroTemp || {};
  const zwtIob0 = zwt.iob != null ? zwt.iob : iob0;
  const zwtAct0 = zwt.activity != null ? zwt.activity : activity0;
  let tauZwt = tau;
  if (Math.abs(zwtIob0) > 0.01 && Math.abs(zwtAct0) > 0.0001) {
    const rz = Math.abs(zwtAct0 / zwtIob0);
    if (rz > 0.0001 && rz < 0.1) tauZwt = Math.min(diaMins, Math.max(30, 1 / rz));
  }

  const tempRate = (currentTemp && currentTemp.duration > 0) ? currentTemp.rate : 0;

  for (let i = 0; i < ticks; i++) {
    const t = i * 5;
    const decay = Math.exp(-t / tau);
    const decayZwt = Math.exp(-t / tauZwt);
    const tick = {
      iob: iob0 * decay,
      basaliob: (iob0 * decay) * 0.5,
      bolussnooze: 0,
      activity: activity0 * decay,
      lastBolusTime: Date.now() - 3600000,
      iobWithZeroTemp: {
        iob: zwtIob0 * decayZwt,
        basaliob: (zwtIob0 * decayZwt) * 0.5,
        bolussnooze: 0,
        activity: zwtAct0 * decayZwt,
        lastBolusTime: 0,
        time: new Date(Date.now() + t * 60000).toISOString()
      }
    };
    if (i === 0) tick.lastTemp = { date: Date.now() - 300000, duration: 0, rate: 0 };
    iobArray.push(tick);
  }
  return iobArray;
}

// ── Vector Conversion with Mutation Overlay ─────────────────────────────

function vectorToOref0Inputs(vector, mutation) {
  const input = vector.input;
  const m = mutation || {};

  const glucoseStatus = {
    glucose: input.glucoseStatus.glucose,
    delta: input.glucoseStatus.delta,
    short_avgdelta: input.glucoseStatus.shortAvgDelta != null
      ? input.glucoseStatus.shortAvgDelta : input.glucoseStatus.delta,
    long_avgdelta: input.glucoseStatus.longAvgDelta != null
      ? input.glucoseStatus.longAvgDelta : input.glucoseStatus.delta,
    date: Date.now()
  };

  const p = input.profile;
  const dia = m.dia || p.dia || 4;

  const currentTemp = input.currentTemp ? {
    rate: input.currentTemp.rate || 0,
    duration: input.currentTemp.duration || 0
  } : { rate: 0, duration: 0 };

  const iobSnapshot = {
    iob: input.iob.iob,
    basaliob: input.iob.basalIob || 0,
    bolussnooze: input.iob.bolusSnooze || 0,
    activity: input.iob.activity || 0,
    lastBolusTime: Date.now() - 60 * 60 * 1000,
    iobWithZeroTemp: input.iob.iobWithZeroTemp || undefined
  };

  const iobData = generateIobArray(iobSnapshot, dia, currentTemp);

  const basalRate = (p.basalRate || p.currentBasal || 1.0) * (m.basal_factor || 1.0);
  const sens = (p.sensitivity || 50) * (m.sens_factor || 1.0);
  const cr = (p.carbRatio || 10) * (m.cr_factor || 1.0);
  const shift = m.target_shift || 0;
  const smbEnabled = m.enable_smb ? true : (p.enableSMB || false);

  const profile = {
    current_basal: basalRate,
    sens: sens,
    carb_ratio: cr,
    target_bg: ((p.targetLow || 100) + (p.targetHigh || 110)) / 2 + shift,
    min_bg: (p.targetLow || 100) + shift,
    max_bg: (p.targetHigh || 110) + shift,
    max_basal: m.max_basal || p.maxBasal || 3.0,
    max_iob: m.max_iob || p.maxIob || 5.0,
    max_daily_basal: (p.maxDailyBasal || p.basalRate || p.currentBasal || 1.0) * (m.basal_factor || 1.0),
    max_daily_safety_multiplier: p.maxDailySafetyMultiplier || 3,
    current_basal_safety_multiplier: p.currentBasalSafetyMultiplier || 4,
    dia: dia,
    skip_neutral_temps: false,
    enableSMB_with_bolus: smbEnabled,
    enableSMB_always: smbEnabled,
    enableSMB_with_COB: smbEnabled,
    enableSMB_with_temptarget: false,
    enableSMB_after_carbs: false,
    enableUAM: m.enable_uam ? true : (p.enableUAM || false),
    maxSMBBasalMinutes: m.smb_minutes || p.maxSMBBasalMinutes || 30,
    maxUAMSMBBasalMinutes: m.smb_minutes || p.maxUAMSMBBasalMinutes || 30,
    SMBInterval: p.smbInterval || 3,
    bolus_increment: 0.05,
    out_units: p.units || 'mg/dL',
    type: 'current'
  };

  const md = input.mealData || {};
  const mealData = {
    carbs: md.carbs || 0,
    mealCOB: md.mealCOB || md.cob || 0,
    slopeFromMaxDeviation: md.slopeFromMaxDeviation != null ? md.slopeFromMaxDeviation : 0,
    slopeFromMinDeviation: md.slopeFromMinDeviation != null ? md.slopeFromMinDeviation : 0,
    lastCarbTime: md.lastCarbTime || (Date.now() - 2 * 60 * 60 * 1000)
  };

  const ad = input.autosensData || input.autosens || {};
  const autosens = { ratio: ad.ratio || 1.0 };
  const microBolusAllowed = smbEnabled || input.microBolusAllowed || false;

  return { glucoseStatus, iobData, profile, currentTemp, mealData, autosens, microBolusAllowed };
}

// ── Scoring a Single Mutation ───────────────────────────────────────────

function loadVectors() {
  const files = fs.readdirSync(VECTOR_DIR).filter(f => f.endsWith('.json')).sort();
  const vectors = [];
  for (const file of files) {
    try {
      const v = JSON.parse(fs.readFileSync(path.join(VECTOR_DIR, file), 'utf8'));
      // Skip parametric variants
      if (v.metadata && v.metadata.parametricVariantOf) continue;
      vectors.push(v);
    } catch (e) { /* skip bad files */ }
  }
  return vectors;
}

function scoreMutation(vectors, mutation) {
  let pass = 0, fail = 0, crash = 0;
  let rateDiffs = [];
  let ebgDiffs = [];

  const origErr = console.error;
  console.error = () => {};

  for (const vector of vectors) {
    try {
      const { glucoseStatus, iobData, profile, currentTemp, mealData, autosens, microBolusAllowed } =
        vectorToOref0Inputs(vector, mutation);

      const result = determineBasal(
        glucoseStatus, currentTemp, iobData, profile,
        autosens, mealData, tempBasalFunctions,
        microBolusAllowed, null, Date.now()
      );

      if (result.error) { crash++; continue; }

      const expected = vector.expected || {};
      let ok = true;

      if (expected.rate != null && result.rate != null) {
        const d = Math.abs(result.rate - expected.rate);
        rateDiffs.push(d);
        if (d > TOL.rate) ok = false;
      }
      if (expected.eventualBG != null && result.eventualBG != null) {
        const d = Math.abs(result.eventualBG - expected.eventualBG);
        ebgDiffs.push(d);
        if (d > TOL.eventualBG) ok = false;
      }
      if (expected.rate != null && result.rate == null) ok = false;

      if (ok) pass++; else fail++;
    } catch (e) {
      crash++;
    }
  }

  console.error = origErr;

  const scored = pass + fail;
  const passRate = scored > 0 ? pass / scored : 0;
  const meanRateDiv = rateDiffs.length > 0
    ? rateDiffs.reduce((a, b) => a + b, 0) / rateDiffs.length : 1.0;
  const meanEbgDiv = ebgDiffs.length > 0
    ? ebgDiffs.reduce((a, b) => a + b, 0) / ebgDiffs.length : 50.0;

  // Quick composite: mirrors v3 weights but uses only e2e data
  const agreement = Math.max(0, 1 - meanRateDiv / 2.0);
  const ebgScore = Math.max(0, 1 - meanEbgDiv / 100.0);
  const quickScore = 0.40 * agreement + 0.35 * passRate + 0.25 * ebgScore;

  return {
    pass, fail, crash, scored, passRate,
    meanRateDiv: Math.round(meanRateDiv * 1000) / 1000,
    meanEbgDiv: Math.round(meanEbgDiv * 10) / 10,
    quickScore: Math.round(quickScore * 10000) / 10000
  };
}

// ── Mutation Generators ─────────────────────────────────────────────────

function randomMutation() {
  const m = {};
  for (const [key, spec] of Object.entries(PARAM_SPACE)) {
    const steps = Math.round((spec.max - spec.min) / spec.step);
    const pick = Math.floor(Math.random() * (steps + 1));
    m[key] = Math.round((spec.min + pick * spec.step) * 1000) / 1000;
  }
  return m;
}

function walkMutation(base, temperature) {
  const t = temperature || 0.15;
  const m = {};
  for (const [key, spec] of Object.entries(PARAM_SPACE)) {
    const baseVal = base[key] != null ? base[key] : spec.default;
    const range = spec.max - spec.min;
    const perturbation = (Math.random() - 0.5) * 2 * t * range;
    let newVal = baseVal + perturbation;
    // Snap to step grid
    newVal = Math.round((newVal - spec.min) / spec.step) * spec.step + spec.min;
    newVal = Math.max(spec.min, Math.min(spec.max, newVal));
    m[key] = Math.round(newVal * 1000) / 1000;
  }
  return m;
}

function* gridGenerator(keys) {
  // Grid search over specified keys only (others at default)
  keys = keys || ['sens_factor', 'cr_factor', 'basal_factor', 'max_basal', 'target_shift'];
  const specs = keys.map(k => ({ key: k, ...PARAM_SPACE[k] }));
  const dims = specs.map(s => Math.round((s.max - s.min) / s.step) + 1);
  const total = dims.reduce((a, b) => a * b, 1);

  for (let idx = 0; idx < total; idx++) {
    const m = {};
    // Set defaults for all params
    for (const [key, spec] of Object.entries(PARAM_SPACE)) {
      m[key] = spec.default;
    }
    // Compute multi-dimensional index
    let rem = idx;
    for (let d = specs.length - 1; d >= 0; d--) {
      const pos = rem % dims[d];
      rem = Math.floor(rem / dims[d]);
      m[specs[d].key] = Math.round((specs[d].min + pos * specs[d].step) * 1000) / 1000;
    }
    yield m;
  }
}

function defaultMutation() {
  const m = {};
  for (const [key, spec] of Object.entries(PARAM_SPACE)) {
    m[key] = spec.default;
  }
  return m;
}

// ── Main ────────────────────────────────────────────────────────────────

function main() {
  const args = process.argv.slice(2);
  const strategy = args.includes('--strategy')
    ? args[args.indexOf('--strategy') + 1] : 'walk';
  const iterations = args.includes('--iterations')
    ? parseInt(args[args.indexOf('--iterations') + 1]) : 30;
  const jsonFlag = args.includes('--json');
  const gridKeys = args.includes('--grid-keys')
    ? args[args.indexOf('--grid-keys') + 1].split(',') : null;

  // Load vectors once
  const vectors = loadVectors();
  if (!jsonFlag) {
    process.stderr.write(`Loaded ${vectors.length} vectors (parametric excluded)\n`);
  }

  // Score baseline (no mutation)
  const baseline = scoreMutation(vectors, defaultMutation());
  if (!jsonFlag) {
    process.stderr.write(`Baseline: ${baseline.pass}/${baseline.scored} pass, ` +
      `quickScore=${baseline.quickScore}, rateDiv=${baseline.meanRateDiv} U/hr\n`);
  }

  // Run search
  let best = { mutation: defaultMutation(), score: baseline };
  const history = [{ iteration: 0, mutation: defaultMutation(), score: baseline }];

  const startTime = Date.now();
  let evalCount = 0;

  if (strategy === 'grid') {
    const gen = gridGenerator(gridKeys || ['sens_factor', 'basal_factor', 'target_shift']);
    let maxIter = iterations;
    for (const m of gen) {
      if (evalCount >= maxIter) break;
      evalCount++;
      const s = scoreMutation(vectors, m);
      history.push({ iteration: evalCount, mutation: m, score: s });
      if (s.quickScore > best.score.quickScore) {
        best = { mutation: m, score: s };
        if (!jsonFlag) {
          process.stderr.write(`  [${evalCount}] NEW BEST: ${s.quickScore} ` +
            `(pass=${s.pass}/${s.scored}, rateDiv=${s.meanRateDiv})\n`);
        }
      }
    }
  } else if (strategy === 'random') {
    for (let i = 0; i < iterations; i++) {
      evalCount++;
      const m = randomMutation();
      const s = scoreMutation(vectors, m);
      history.push({ iteration: evalCount, mutation: m, score: s });
      if (s.quickScore > best.score.quickScore) {
        best = { mutation: m, score: s };
        if (!jsonFlag) {
          process.stderr.write(`  [${evalCount}] NEW BEST: ${s.quickScore} ` +
            `(pass=${s.pass}/${s.scored}, rateDiv=${s.meanRateDiv})\n`);
        }
      }
    }
  } else {
    // walk strategy: start from default, perturb
    let temperature = 0.2;
    const coolRate = 0.97;
    for (let i = 0; i < iterations; i++) {
      evalCount++;
      const m = walkMutation(best.mutation, temperature);
      const s = scoreMutation(vectors, m);
      history.push({ iteration: evalCount, mutation: m, score: s });
      if (s.quickScore > best.score.quickScore) {
        best = { mutation: m, score: s };
        if (!jsonFlag) {
          process.stderr.write(`  [${evalCount}] NEW BEST: ${s.quickScore} ` +
            `(pass=${s.pass}/${s.scored}, rateDiv=${s.meanRateDiv}, T=${temperature.toFixed(3)})\n`);
        }
      }
      temperature *= coolRate;
    }
  }

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

  // Format best mutation as readable diff from defaults
  const diffs = {};
  for (const [key, spec] of Object.entries(PARAM_SPACE)) {
    if (best.mutation[key] !== spec.default) {
      diffs[key] = { default: spec.default, best: best.mutation[key], desc: spec.desc };
    }
  }

  const output = {
    strategy,
    iterations: evalCount,
    elapsed_sec: parseFloat(elapsed),
    vectors_count: vectors.length,
    baseline: { quickScore: baseline.quickScore, pass: baseline.pass, scored: baseline.scored },
    best: {
      quickScore: best.score.quickScore,
      pass: best.score.pass,
      scored: best.score.scored,
      passRate: best.score.passRate,
      meanRateDiv: best.score.meanRateDiv,
      meanEbgDiv: best.score.meanEbgDiv,
      mutation: best.mutation,
      diffs_from_default: diffs
    },
    improvement: {
      quickScore_delta: Math.round((best.score.quickScore - baseline.quickScore) * 10000) / 10000,
      pass_delta: best.score.pass - baseline.pass,
      rateDiv_delta: Math.round((best.score.meanRateDiv - baseline.meanRateDiv) * 1000) / 1000
    }
  };

  if (jsonFlag) {
    console.log(JSON.stringify(output, null, 2));
  } else {
    console.log(`\nParameter Mutation Search (${strategy}, ${evalCount} evals, ${elapsed}s)`);
    console.log('='.repeat(60));
    console.log(`  Baseline:  quickScore=${baseline.quickScore}  pass=${baseline.pass}/${baseline.scored}`);
    console.log(`  Best:      quickScore=${best.score.quickScore}  pass=${best.score.pass}/${best.score.scored}`);
    console.log(`  Δ score:   ${output.improvement.quickScore_delta > 0 ? '+' : ''}${output.improvement.quickScore_delta}`);
    console.log(`  Δ pass:    ${output.improvement.pass_delta > 0 ? '+' : ''}${output.improvement.pass_delta}`);
    console.log(`  Rate div:  ${baseline.meanRateDiv} → ${best.score.meanRateDiv} U/hr`);
    console.log(`  eBG div:   ${baseline.meanEbgDiv} → ${best.score.meanEbgDiv} mg/dL`);

    if (Object.keys(diffs).length > 0) {
      console.log(`\n  Mutations from default:`);
      for (const [key, d] of Object.entries(diffs)) {
        console.log(`    ${key.padEnd(18)}: ${d.default} → ${d.best}  (${d.desc})`);
      }
    } else {
      console.log(`\n  No improvement found — baseline is optimal for this search.`);
    }
    console.log('='.repeat(60));
  }
}

main();
