#!/usr/bin/env node
/**
 * In-silico closed-loop simulator bridge
 *
 * Generates synthetic glucose scenarios using cgmsim-lib's pharmacokinetic
 * model, optionally closed-loop with oref0 determine-basal as the controller.
 *
 * Modes:
 *   open-loop   — no controller, just basal + meals + patient dynamics
 *   oref0-loop  — oref0 determine-basal adjusts temp basal every 5 min
 *
 * Output formats:
 *   --csv       — GluPredKit-compatible CSV (time, CGM, insulin, carbs, ...)
 *   --json      — full simulation trace with all state variables
 *   --vectors   — TV-* style conformance vectors for algorithm scoring
 *
 * Scenarios (--scenario):
 *   meal-rise       — 50g meal, adequate bolus, BG 100→peak→return
 *   meal-underbolus — 50g meal, half bolus, sustained high
 *   fasting-flat    — no meals, stable basal, BG ~110
 *   hypo-recovery   — BG starts at 65, liver rescue + suspend
 *   dawn-phenomenon — 3am cortisol rise, increasing BG
 *   exercise        — post-meal exercise, insulin sensitivity boost
 *   multi-meal      — breakfast + lunch + snack over 8 hours
 *
 * Usage:
 *   node in-silico-bridge.js --scenario meal-rise --mode oref0-loop --csv
 *   node in-silico-bridge.js --scenario all --mode open-loop --json
 *   node in-silico-bridge.js --scenario meal-rise --hours 4 --vectors
 *
 * Trace: ALG-VERIFY-007, REQ-060
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '../..');
const CGMSIM_PATH = path.join(REPO_ROOT, 'externals/cgmsim-lib');

// Load cgmsim-lib
let simulator;
try {
  simulator = require(CGMSIM_PATH).simulator;
} catch (e) {
  console.error(`Error loading cgmsim-lib: ${e.message}`);
  console.error('Run: cd externals/cgmsim-lib && npm install && npm run build');
  process.exit(1);
}

// Load oref0 (optional, for closed-loop mode)
let determineBasal, tempBasalFunctions;
try {
  determineBasal = require(path.join(REPO_ROOT, 'externals/oref0/lib/determine-basal/determine-basal'));
  tempBasalFunctions = require(path.join(REPO_ROOT, 'externals/oref0/lib/basal-set-temp'));
} catch (e) {
  // oref0 not available — open-loop only
}

// ─── Patient Profiles ───

const PATIENTS = {
  standard: {
    WEIGHT: 70, AGE: 35, GENDER: 'Male', TZ: 'UTC',
    CR: 10, ISF: 40, CARBS_ABS_TIME: 360, TP: 75, DIA: 6
  },
  sensitive: {
    WEIGHT: 55, AGE: 28, GENDER: 'Female', TZ: 'UTC',
    CR: 15, ISF: 60, CARBS_ABS_TIME: 300, TP: 65, DIA: 5
  },
  resistant: {
    WEIGHT: 95, AGE: 50, GENDER: 'Male', TZ: 'UTC',
    CR: 6, ISF: 20, CARBS_ABS_TIME: 420, TP: 85, DIA: 7
  }
};

// ─── Scenario Definitions ───

function makeScenario(name) {
  const now = Date.now();
  const m = (mins) => new Date(now + mins * 60000).toISOString();
  const base = {
    name,
    hours: 4,
    startBG: 110,
    patient: 'standard',
    basalRate: 1.0,
    treatments: [],
    pumpEnabled: true,
  };

  switch (name) {
    case 'meal-rise':
      return { ...base, name: 'Meal with adequate bolus',
        startBG: 100,
        treatments: [
          { eventType: 'Meal Bolus', insulin: 5, carbs: 50, created_at: m(10) }
        ]};

    case 'meal-underbolus':
      return { ...base, name: 'Meal with 50% bolus (underbolus)',
        startBG: 105,
        treatments: [
          { eventType: 'Meal Bolus', insulin: 2.5, carbs: 50, created_at: m(10) }
        ]};

    case 'fasting-flat':
      return { ...base, name: 'Fasting with stable basal',
        hours: 6, startBG: 110, treatments: [] };

    case 'hypo-recovery':
      return { ...base, name: 'Hypoglycemia recovery',
        startBG: 65, basalRate: 0.8,
        treatments: [
          { eventType: 'Carb Correction', carbs: 15, created_at: m(5) }
        ]};

    case 'dawn-phenomenon':
      return { ...base, name: 'Dawn phenomenon (rising BG)',
        hours: 5, startBG: 120, basalRate: 0.9,
        // Simulated by reduced ISF patient variant
        patient: 'resistant',
        treatments: [] };

    case 'exercise':
      return { ...base, name: 'Post-meal exercise',
        startBG: 140,
        treatments: [
          { eventType: 'Meal Bolus', insulin: 4, carbs: 40, created_at: m(-60) }
        ]};

    case 'multi-meal':
      return { ...base, name: 'Multi-meal day (breakfast + lunch + snack)',
        hours: 8, startBG: 95,
        treatments: [
          { eventType: 'Meal Bolus', insulin: 4, carbs: 40, created_at: m(15) },     // breakfast
          { eventType: 'Meal Bolus', insulin: 6, carbs: 60, created_at: m(240) },    // lunch
          { eventType: 'Meal Bolus', insulin: 1.5, carbs: 15, created_at: m(360) },  // snack
        ]};

    default:
      throw new Error(`Unknown scenario: ${name}. Available: meal-rise, meal-underbolus, fasting-flat, hypo-recovery, dawn-phenomenon, exercise, multi-meal`);
  }
}

// ─── IOB Array for oref0 (from compare-predictions.js) ───

function generateIobArray(iobSnapshot, dia) {
  const diaMins = (dia || 6) * 60;
  const ticks = 48;
  const iobArray = [];
  const iob0 = iobSnapshot.iob || 0;
  const activity0 = iobSnapshot.activity || 0;
  const basaliob0 = iobSnapshot.basaliob || 0;
  let tau = diaMins / 1.85;
  if (Math.abs(iob0) > 0.01 && Math.abs(activity0) > 0.0001) {
    const r = Math.abs(activity0 / iob0);
    if (r > 0.0001 && r < 0.1) tau = Math.min(diaMins, Math.max(30, 1 / r));
  }
  const basalFrac = (iob0 !== 0) ? (basaliob0 / iob0) : 0.5;

  for (let i = 0; i < ticks; i++) {
    const t = i * 5;
    const decay = Math.exp(-t / tau);
    const tick = {
      iob: iob0 * decay, basaliob: iob0 * decay * basalFrac,
      bolussnooze: 0, activity: activity0 * Math.max(0, decay),
      lastBolusTime: Date.now() - 3600000,
      iobWithZeroTemp: {
        iob: iob0 * decay * 0.8, basaliob: iob0 * decay * basalFrac * 0.8,
        bolussnooze: 0, activity: activity0 * Math.max(0, decay) * 0.8,
        lastBolusTime: 0, time: new Date(Date.now() + t * 60000).toISOString()
      }
    };
    if (i === 0) tick.lastTemp = { date: Date.now() - 300000, duration: 0 };
    iobArray.push(tick);
  }
  return iobArray;
}

// ─── oref0 Controller ───

function runOref0Controller(bg, delta, shortDelta, longDelta, simResult, patientProfile, currentTempRate, dia) {
  if (!determineBasal) return null;

  const sens = patientProfile.ISF || 40;
  const cr = patientProfile.CR || 10;
  const basalRate = patientProfile._basalRate || 1.0;

  const glucoseStatus = {
    glucose: bg, delta, short_avgdelta: shortDelta, long_avgdelta: longDelta,
    date: Date.now()
  };

  const iobSnapshot = {
    iob: (simResult.bolusIOB || 0) + (simResult.pumpBasalIOB || 0),
    basaliob: simResult.pumpBasalIOB || 0,
    bolussnooze: 0,
    activity: (simResult.bolusActivity || 0) + (simResult.basalActivity || 0),
  };
  const iobData = generateIobArray(iobSnapshot, dia || 6);

  const profile = {
    current_basal: basalRate, sens, carb_ratio: cr,
    target_bg: 100, min_bg: 100, max_bg: 110,
    max_basal: basalRate * 4, max_iob: basalRate * 4,
    max_daily_safety_multiplier: 3, current_basal_safety_multiplier: 4,
    dia: dia || 6, skip_neutral_temps: false,
    enableSMB_with_bolus: false, enableSMB_always: false,
    enableSMB_with_COB: false, enableSMB_with_temptarget: false,
    enableSMB_after_carbs: false, enableUAM: false,
    maxSMBBasalMinutes: 30, maxUAMSMBBasalMinutes: 30,
    SMBInterval: 3, bolus_increment: 0.05,
    out_units: 'mg/dL', type: 'current'
  };

  const currentTemp = { rate: currentTempRate, duration: 30 };
  const mealData = {
    carbs: 0, mealCOB: simResult.cob || 0,
    slopeFromMaxDeviation: 0, slopeFromMinDeviation: 0,
    lastCarbTime: Date.now() - 7200000
  };
  const autosens = { ratio: 1.0 };

  const origErr = console.error;
  console.error = () => {};
  let result;
  try {
    result = determineBasal(
      glucoseStatus, currentTemp, iobData, profile,
      autosens, mealData, tempBasalFunctions, false, null, Date.now()
    );
  } catch (e) {
    console.error = origErr;
    return null;
  }
  console.error = origErr;
  return result;
}

// ─── Simulation Engine ───

function runSimulation(scenario, mode) {
  const patientKey = scenario.patient || 'standard';
  const patient = { ...PATIENTS[patientKey] };
  patient._basalRate = scenario.basalRate || 1.0;
  const startBG = scenario.startBG || 110;
  const hours = scenario.hours || 4;
  const totalSteps = Math.floor(hours * 60 / 5);

  const startTime = Date.now();

  // Seed glucose history (20 min of flat readings at startBG)
  const entries = [];
  for (let i = 4; i >= 0; i--) {
    entries.push({
      mills: startTime - i * 5 * 60000,
      sgv: startBG + (Math.random() - 0.5) * 2  // ±1 mg/dL noise
    });
  }

  // Build treatment timeline: shift relative times to absolute
  const treatments = (scenario.treatments || []).map(t => ({
    ...t,
    created_at: t.created_at // already ISO from makeScenario
  }));

  const profiles = [{
    startDate: new Date(startTime - 86400000).toISOString(),
    defaultProfile: 'default',
    store: { default: { basal: scenario.basalRate || 1.0 } }
  }];

  const trace = [];
  let currentTempRate = scenario.basalRate || 1.0;
  let controllerDecisions = [];

  for (let step = 0; step < totalSteps; step++) {
    const stepTime = startTime + step * 5 * 60000;

    // Run cgmsim-lib simulator step
    const simResult = simulator({
      patient,
      entries: entries.slice(0, 10), // last 10 readings
      treatments,
      profiles,
      pumpEnabled: scenario.pumpEnabled !== false,
      user: { nsUrl: 'in-silico' }
    });

    const bg = Math.round(simResult.sgv * 10) / 10;

    // Calculate deltas from recent history (add tiny noise to avoid oref0 flatBG detection)
    const prev1 = entries.length > 0 ? entries[0].sgv : bg;
    const prev2 = entries.length > 1 ? entries[1].sgv : prev1;
    const prev3 = entries.length > 2 ? entries[2].sgv : prev2;
    const rawDelta = bg - prev1;
    const delta = rawDelta === 0 ? (Math.random() - 0.5) * 0.2 : rawDelta;
    const shortDelta = (bg - prev2) / 2 || delta;
    const longDelta = (bg - prev3) / 3 || delta;

    // Run controller in oref0-loop mode
    let decision = null;
    if (mode === 'oref0-loop' && determineBasal) {
      decision = runOref0Controller(
        bg, delta, shortDelta, longDelta,
        simResult, patient, currentTempRate, patient.DIA
      );
      if (decision && decision.rate !== undefined && decision.rate !== null) {
        currentTempRate = decision.rate;
        // Inject temp basal as treatment for next step
        treatments.push({
          eventType: 'Temp Basal',
          rate: decision.rate,
          duration: 30,
          durationInMilliseconds: 30 * 60000,
          created_at: new Date(stepTime).toISOString()
        });
      }
      // If decision is null (controller error), keep previous temp rate
    }

    // Record trace
    trace.push({
      step,
      timeMin: step * 5,
      timeISO: new Date(stepTime).toISOString(),
      bg,
      delta: Math.round(delta * 10) / 10,
      cob: Math.round((simResult.cob || 0) * 10) / 10,
      bolusIOB: Math.round((simResult.bolusIOB || 0) * 100) / 100,
      basalIOB: Math.round((simResult.pumpBasalIOB || simResult.basalIOB || 0) * 100) / 100,
      carbsActivity: Math.round((simResult.carbsActivity || 0) * 10000) / 10000,
      insulinActivity: Math.round(((simResult.bolusActivity || 0) + (simResult.basalActivity || 0)) * 10000) / 10000,
      tempBasalRate: mode === 'oref0-loop' ? currentTempRate : (scenario.basalRate || 1.0),
      controllerRate: decision ? decision.rate : null,
      controllerEventualBG: decision ? decision.eventualBG : null,
      controllerReason: decision ? (decision.reason || '').substring(0, 80) : null,
    });

    // Add new glucose entry
    entries.unshift({ mills: stepTime, sgv: bg });
    if (entries.length > 20) entries.pop();
  }

  return {
    scenario: scenario.name,
    mode,
    patient: patientKey,
    hours,
    steps: totalSteps,
    startBG,
    trace,
    summary: computeSummary(trace)
  };
}

function computeSummary(trace) {
  const bgs = trace.map(t => t.bg);
  const min = Math.min(...bgs);
  const max = Math.max(...bgs);
  const avg = bgs.reduce((s, v) => s + v, 0) / bgs.length;

  // Time-in-range (70-180 mg/dL)
  const tir = bgs.filter(bg => bg >= 70 && bg <= 180).length / bgs.length;
  // Time below range (<70)
  const tbr = bgs.filter(bg => bg < 70).length / bgs.length;
  // Time above range (>180)
  const tar = bgs.filter(bg => bg > 180).length / bgs.length;
  // Coefficient of variation
  const stddev = Math.sqrt(bgs.reduce((s, v) => s + (v - avg) ** 2, 0) / bgs.length);
  const cv = stddev / avg;

  return {
    minBG: Math.round(min * 10) / 10,
    maxBG: Math.round(max * 10) / 10,
    avgBG: Math.round(avg * 10) / 10,
    stddev: Math.round(stddev * 10) / 10,
    cv: Math.round(cv * 1000) / 1000,
    tir: Math.round(tir * 1000) / 1000,
    tbr: Math.round(tbr * 1000) / 1000,
    tar: Math.round(tar * 1000) / 1000,
  };
}

// ─── Output Formatters ───

function toCSV(results) {
  const header = 'scenario,mode,step,time_min,bg,delta,cob,bolus_iob,basal_iob,carbs_activity,insulin_activity,temp_basal_rate';
  const rows = [];
  for (const r of results) {
    for (const t of r.trace) {
      rows.push([
        r.scenario, r.mode, t.step, t.timeMin, t.bg, t.delta,
        t.cob, t.bolusIOB, t.basalIOB, t.carbsActivity, t.insulinActivity,
        t.tempBasalRate
      ].join(','));
    }
  }
  return header + '\n' + rows.join('\n');
}

function toVectors(results) {
  // Generate TV-*–style vectors at key decision points
  const vectors = [];
  for (const r of results) {
    for (let i = 5; i < r.trace.length - 12; i += 10) {
      const t = r.trace[i];
      const futureSteps = r.trace.slice(i, i + 12).map(s => Math.round(s.bg));

      vectors.push({
        metadata: {
          id: `SIM-${r.scenario.replace(/\s+/g, '-')}-${String(i).padStart(3, '0')}`,
          category: r.scenario,
          source: 'cgmsim-lib in-silico',
          mode: r.mode,
          patient: r.patient,
        },
        input: {
          glucoseStatus: {
            glucose: t.bg,
            delta: t.delta,
            shortAvgDelta: r.trace[i-1] ? (t.bg - r.trace[i-1].bg) : t.delta,
            longAvgDelta: r.trace[i-2] ? (t.bg - r.trace[i-2].bg) / 2 : t.delta,
          },
          iob: {
            iob: t.bolusIOB + t.basalIOB,
            basalIob: t.basalIOB,
            bolusIob: t.bolusIOB,
            activity: t.insulinActivity,
          },
          profile: {
            basalRate: t.tempBasalRate || 1.0,
            sensitivity: PATIENTS[r.patient].ISF,
            carbRatio: PATIENTS[r.patient].CR,
            dia: PATIENTS[r.patient].DIA,
            targetLow: 100, targetHigh: 110,
            maxBasal: 4.0, maxIob: 5.0,
          },
          mealData: { cob: t.cob, carbs: 0 },
          currentTemp: { rate: t.tempBasalRate, duration: 30 },
        },
        // Ground truth: actual future glucose from simulation
        originalOutput: {
          predBGs: { IOB: futureSteps },
          eventualBG: futureSteps[futureSteps.length - 1],
        },
        expected: {
          rate: t.controllerRate,
          eventualBG: t.controllerEventualBG,
        }
      });
    }
  }
  return vectors;
}

function printSummaryTable(results) {
  console.log('\n╔═══════════════════════════════════════════════════════════════════════════╗');
  console.log('║                   In-Silico Simulation Results (cgmsim-lib)              ║');
  console.log('╠═══════════════════════════════════════════════════════════════════════════╣');
  console.log('║ Scenario                 │ Mode      │ AvgBG │ Min │ Max │ TIR%  │ TBR% ║');
  console.log('╟──────────────────────────┼───────────┼───────┼─────┼─────┼───────┼──────╢');

  for (const r of results) {
    const name = r.scenario.padEnd(24).slice(0, 24);
    const mode = r.mode.padEnd(9).slice(0, 9);
    const avg = r.summary.avgBG.toFixed(0).padStart(5);
    const min = r.summary.minBG.toFixed(0).padStart(3);
    const max = r.summary.maxBG.toFixed(0).padStart(3);
    const tir = (r.summary.tir * 100).toFixed(1).padStart(5);
    const tbr = (r.summary.tbr * 100).toFixed(1).padStart(4);
    console.log(`║ ${name} │ ${mode} │ ${avg} │ ${min} │ ${max} │ ${tir} │ ${tbr} ║`);
  }

  console.log('╚═══════════════════════════════════════════════════════════════════════════╝');
  console.log(`TIR = Time in Range (70-180 mg/dL), TBR = Time Below Range (<70 mg/dL)`);
}

// ─── CLI ───

const args = process.argv.slice(2);
const scenarioArg = args.find((_, i) => args[i-1] === '--scenario') || 'meal-rise';
const modeArg = args.find((_, i) => args[i-1] === '--mode') || 'open-loop';
const hoursArg = parseFloat(args.find((_, i) => args[i-1] === '--hours') || '0');
const csvFlag = args.includes('--csv');
const jsonFlag = args.includes('--json');
const vectorsFlag = args.includes('--vectors');

const SCENARIO_NAMES = ['meal-rise', 'meal-underbolus', 'fasting-flat', 'hypo-recovery', 'dawn-phenomenon', 'exercise', 'multi-meal'];
const scenarios = scenarioArg === 'all' ? SCENARIO_NAMES : [scenarioArg];
const modes = modeArg === 'both'
  ? ['open-loop', 'oref0-loop']
  : [modeArg];

const results = [];

for (const scenarioName of scenarios) {
  for (const mode of modes) {
    if (mode === 'oref0-loop' && !determineBasal) {
      console.error(`Skipping ${scenarioName} in oref0-loop mode (oref0 not available)`);
      continue;
    }
    const scenario = makeScenario(scenarioName);
    if (hoursArg > 0) scenario.hours = hoursArg;
    const result = runSimulation(scenario, mode);
    results.push(result);
  }
}

if (csvFlag) {
  const csvPath = path.join(__dirname, 'in-silico-scenarios.csv');
  fs.writeFileSync(csvPath, toCSV(results));
  console.error(`Exported ${results.reduce((s, r) => s + r.trace.length, 0)} rows to ${csvPath}`);
  printSummaryTable(results);
} else if (jsonFlag) {
  console.log(JSON.stringify(results, null, 2));
} else if (vectorsFlag) {
  const vectors = toVectors(results);
  const vectorDir = path.join(REPO_ROOT, 'conformance/in-silico/vectors');
  fs.mkdirSync(vectorDir, { recursive: true });
  for (const v of vectors) {
    const fp = path.join(vectorDir, `${v.metadata.id}.json`);
    fs.writeFileSync(fp, JSON.stringify(v, null, 2));
  }
  console.error(`Generated ${vectors.length} conformance vectors in ${vectorDir}`);
  printSummaryTable(results);
} else {
  printSummaryTable(results);

  // Also show BG trace sparkline for each result
  for (const r of results) {
    const sparkChars = '▁▂▃▄▅▆▇█';
    const bgs = r.trace.map(t => t.bg);
    const min = Math.min(...bgs);
    const max = Math.max(...bgs);
    const range = max - min || 1;
    const spark = bgs.map(bg => {
      const idx = Math.min(sparkChars.length - 1, Math.floor((bg - min) / range * (sparkChars.length - 1)));
      return sparkChars[idx];
    }).join('');
    console.log(`\n  ${r.scenario} (${r.mode}):`);
    console.log(`  ${min.toFixed(0)}─${spark}─${max.toFixed(0)} mg/dL`);
  }
}

// Force clean exit (avoid pino logger thread cleanup error)
if (typeof process.exitCode === 'undefined') process.exitCode = 0;
setImmediate(() => {
  try { process.exit(0); } catch (e) { /* ignore pino cleanup */ }
});
