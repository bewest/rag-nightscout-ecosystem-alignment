#!/usr/bin/env node
/**
 * uva_replay.js — Run UVA/Padova ODE model on real Nightscout treatment history.
 *
 * Replays the patient's actual insulin/carb events through the full 14-state
 * UVA/Padova metabolic model to produce physics-based glucose predictions
 * at each 5-minute grid point. Output is consumed by physics_model.py
 * for residual computation.
 *
 * Usage:
 *   node tools/cgmencode/uva_replay.js \
 *     --data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history \
 *     --output externals/experiments/uva_predictions.json
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '../..');
const CGMSIM_PATH = path.join(REPO_ROOT, 'externals/cgmsim-lib');

// Load UVA/Padova model
let UvaPadovaModel, SolverRK;
try {
  UvaPadovaModel = require(path.join(CGMSIM_PATH, 'dist/lt1/core/models/UvaPadova_T1DMS'));
  SolverRK = require(path.join(CGMSIM_PATH, 'dist/lt1/core/solvers/SolverRK1_2'));
} catch (e) {
  console.error(`Error loading cgmsim-lib: ${e.message}`);
  console.error('Run: cd externals/cgmsim-lib && npm install && npm run build');
  process.exit(1);
}

// Parse CLI args
const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i].replace(/^--/, '');
  args[key] = process.argv[i + 1];
}

const dataPath = args.data;
const outputPath = args.output || 'externals/experiments/uva_predictions.json';

if (!dataPath) {
  console.error('Usage: node uva_replay.js --data PATH [--output PATH]');
  process.exit(1);
}

// Load Nightscout JSON
console.log(`Loading data from ${dataPath}...`);
const entries = JSON.parse(fs.readFileSync(path.join(dataPath, 'entries.json')));
const treatments = JSON.parse(fs.readFileSync(path.join(dataPath, 'treatments.json')));
const profiles = JSON.parse(fs.readFileSync(path.join(dataPath, 'profile.json')));

// Extract patient params from profile
const store = profiles[0]?.store?.Default || {};
const ISF = store.sens?.[0]?.value || 40;
const CR = store.carbratio?.[0]?.value || 10;
const DIA = store.dia || 6;
const basalSchedule = store.basal || [{ timeAsSeconds: 0, value: 1.0 }];

// Get weight from profile or default
const WEIGHT = 70;  // Default; Nightscout profiles don't always include weight

console.log(`  Patient: ISF=${ISF}, CR=${CR}, DIA=${DIA}h, weight=${WEIGHT}kg`);
console.log(`  Basal schedule: ${basalSchedule.map(b => `${b.time}→${b.value}`).join(', ')}`);

// Build sorted treatment list with absolute timestamps
const txList = treatments
  .filter(t => t.created_at)
  .map(t => ({
    ...t,
    absTime: new Date(t.created_at).getTime(),
  }))
  .sort((a, b) => a.absTime - b.absTime);

console.log(`  Treatments: ${txList.length} total`);

// Find time range from entries
const sgvEntries = entries
  .filter(e => e.type === 'sgv' && e.sgv > 0)
  .map(e => ({ sgv: e.sgv, time: e.date || new Date(e.dateString).getTime() }))
  .sort((a, b) => a.time - b.time);

const startTime = Math.floor(sgvEntries[0].time / 300000) * 300000;  // Align to 5-min
const endTime = Math.ceil(sgvEntries[sgvEntries.length - 1].time / 300000) * 300000;
const totalSteps = Math.floor((endTime - startTime) / 300000);

console.log(`  Time range: ${new Date(startTime).toISOString()} to ${new Date(endTime).toISOString()}`);
console.log(`  Total 5-min steps: ${totalSteps}`);

// Build SGV lookup for initial BG
const sgvMap = new Map();
for (const e of sgvEntries) {
  const rounded = Math.round(e.time / 300000) * 300000;
  sgvMap.set(rounded, e.sgv);
}

// Get initial BG
const firstBG = sgvMap.get(startTime) || sgvEntries[0].sgv || 110;

// Get basal rate at a given time of day
function getScheduledBasal(timeMs) {
  const d = new Date(timeMs);
  const secOfDay = d.getUTCHours() * 3600 + d.getUTCMinutes() * 60 + d.getUTCSeconds();
  let rate = basalSchedule[0].value;
  for (const entry of basalSchedule) {
    if ((entry.timeAsSeconds || 0) <= secOfDay) {
      rate = entry.value;
    }
  }
  return rate;
}

// Build treatment lookup for each minute
function getInputAtMinute(minuteTime) {
  let iir = getScheduledBasal(minuteTime);  // Default: scheduled basal (U/hr)
  let bolus = 0;
  let carbs = 0;
  let meal = 0;

  for (const t of txList) {
    const msSince = minuteTime - t.absTime;
    const minSince = msSince / 60000;

    if (minSince < -5) break;  // Future treatments (sorted list optimization)
    if (minSince < 0) continue;

    // Bolus: deliver in the minute it was given
    if ((t.insulin || 0) > 0 && minSince >= 0 && minSince < 1) {
      bolus += t.insulin;
    }

    // Carbs: spread over 15 minutes
    if ((t.carbs || 0) > 0 && minSince >= 0 && minSince < 15) {
      carbs += t.carbs / 15;
      if (minSince < 1) meal += t.carbs;
    }

    // Temp basal: override iir during duration
    if (t.eventType === 'Temp Basal' && t.rate !== undefined) {
      const durMin = t.duration || 30;
      if (minSince >= 0 && minSince < durMin) {
        iir = t.rate;
      }
    }
  }

  // Convert bolus to equivalent U/hr for 1-minute step
  iir += bolus * 60;

  return { iir, carbs, meal, exercise: 0 };
}

// Initialize UVA/Padova patient
console.log(`\nRunning UVA/Padova simulation (${totalSteps} steps)...`);
const patient = new UvaPadovaModel.default({ Gpeq: firstBG, BW: WEIGHT });
const solver = new SolverRK.default();

// Align start to whole minute
const alignedStart = Math.floor(startTime / 60000) * 60000;
patient.reset(new Date(alignedStart), 42, solver);

const predictions = [];
let lastPct = -1;
const t0 = Date.now();

for (let step = 0; step < totalSteps; step++) {
  const stepTime = startTime + step * 300000;  // 5-min steps

  // Step patient forward 5 minutes (5 × 1-minute ODE integration)
  for (let m = 0; m < 5; m++) {
    const minuteTime = stepTime + m * 60000;
    try {
      const input = getInputAtMinute(minuteTime);
      patient.update(new Date(minuteTime), () => input);
    } catch (e) {
      // ODE can diverge with extreme inputs; reset and continue
      if (step > 0 && predictions.length > 0) {
        const lastPred = predictions[predictions.length - 1].predicted_bg;
        patient.reset(new Date(minuteTime), 42, solver);
        // Re-initialize at last known state
      }
    }
  }

  // Get predicted glucose
  const output = patient.getOutput();
  let predBG = output.Gp;
  predBG = Math.max(40, Math.min(400, Math.round(predBG * 10) / 10));

  // Get actual glucose if available
  const actualBG = sgvMap.get(stepTime) || null;

  predictions.push({
    time: stepTime,
    timeISO: new Date(stepTime).toISOString(),
    predicted_bg: predBG,
    actual_bg: actualBG,
  });

  // Progress
  const pct = Math.floor(step / totalSteps * 100);
  if (pct % 10 === 0 && pct !== lastPct) {
    lastPct = pct;
    const elapsed = (Date.now() - t0) / 1000;
    process.stderr.write(`  ${pct}% (${elapsed.toFixed(1)}s)\n`);
  }
}

const elapsed = (Date.now() - t0) / 1000;
console.log(`  Done: ${predictions.length} predictions in ${elapsed.toFixed(1)}s`);

// Compute quick stats
const withActual = predictions.filter(p => p.actual_bg !== null);
if (withActual.length > 0) {
  const errors = withActual.map(p => Math.abs(p.predicted_bg - p.actual_bg));
  const mae = errors.reduce((a, b) => a + b, 0) / errors.length;
  const rmse = Math.sqrt(errors.map(e => e * e).reduce((a, b) => a + b, 0) / errors.length);
  console.log(`  Physics-only MAE: ${mae.toFixed(2)} mg/dL (${withActual.length} points with actual BG)`);
  console.log(`  Physics-only RMSE: ${rmse.toFixed(2)} mg/dL`);
}

// Save output
const result = {
  metadata: {
    model: 'UVA/Padova T1DMS (cgmsim-lib)',
    patient: { ISF, CR, DIA, WEIGHT, basal: basalSchedule },
    data_path: dataPath,
    time_range: {
      start: new Date(startTime).toISOString(),
      end: new Date(endTime).toISOString(),
    },
    total_steps: totalSteps,
    elapsed_seconds: elapsed,
  },
  predictions,
};

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, JSON.stringify(result));
console.log(`  Saved to ${outputPath} (${(fs.statSync(outputPath).size / 1024 / 1024).toFixed(1)} MB)`);
