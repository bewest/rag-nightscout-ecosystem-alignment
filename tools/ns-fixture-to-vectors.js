'use strict';
/**
 * ns-fixture-to-vectors.js
 *
 * Converts a Nightscout 90-day fixture dump (entries, treatments, devicestatus, profile)
 * into cross-validation test vectors compatible with the adapter protocol.
 *
 * Input:  Directory with entries.json, treatments.json, devicestatus.json, profile.json
 * Output: Test vectors in conformance/loop/vectors/ (one JSON per sampled decision point)
 *
 * Each vector contains:
 *   - glucoseStatus: current BG + deltas (computed from entries)
 *   - glucoseHistory: recent CGM readings (for Loop algorithm)
 *   - iob: from devicestatus.loop.iob
 *   - profile: from Nightscout profile store
 *   - doseHistory: temp basals + boluses from treatments
 *   - carbHistory: carb entries from treatments
 *   - expected: Loop's own predictions + enacted rate (ground truth)
 *
 * Usage:
 *   node ns-fixture-to-vectors.js <fixture-dir> [--output <dir>] [--sample N] [--min-gap M]
 */

const fs = require('fs');
const path = require('path');

// --- CLI args ---
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    fixtureDir: null,
    outputDir: 'conformance/loop/vectors',
    sample: 200,       // max vectors to generate
    minGapMin: 15,     // minimum minutes between sampled records
    diaHours: 6,       // dose history lookback
    glucoseMinutes: 60, // glucose history lookback
    verbose: false,
  };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--output') opts.outputDir = args[++i];
    else if (args[i] === '--sample') opts.sample = parseInt(args[++i]);
    else if (args[i] === '--min-gap') opts.minGapMin = parseInt(args[++i]);
    else if (args[i] === '--verbose' || args[i] === '-v') opts.verbose = true;
    else if (!opts.fixtureDir) opts.fixtureDir = args[i];
  }
  if (!opts.fixtureDir) {
    console.error('Usage: node ns-fixture-to-vectors.js <fixture-dir> [--output dir] [--sample N]');
    process.exit(1);
  }
  return opts;
}

// --- Load data ---
function loadFixtures(dir) {
  console.error(`Loading fixtures from ${dir}...`);
  const entries = JSON.parse(fs.readFileSync(path.join(dir, 'entries.json')));
  const treatments = JSON.parse(fs.readFileSync(path.join(dir, 'treatments.json')));
  const devicestatus = JSON.parse(fs.readFileSync(path.join(dir, 'devicestatus.json')));
  const profiles = JSON.parse(fs.readFileSync(path.join(dir, 'profile.json')));

  // Sort entries by date descending (newest first)
  entries.sort((a, b) => new Date(b.dateString || b.sysTime) - new Date(a.dateString || a.sysTime));
  // Sort treatments by timestamp descending
  treatments.sort((a, b) => new Date(b.timestamp || b.created_at) - new Date(a.timestamp || a.created_at));
  // Sort devicestatus by date descending
  devicestatus.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  console.error(`  ${entries.length} entries, ${treatments.length} treatments, ${devicestatus.length} devicestatus, ${profiles.length} profiles`);
  return { entries, treatments, devicestatus, profiles };
}

// --- Extract active profile at a given time ---
function getActiveProfile(profiles, atTime) {
  // Profiles sorted by startDate descending; find the one active at atTime
  const atMs = atTime.getTime();
  for (const p of profiles) {
    const pMs = p.mills || new Date(p.startDate || p.created_at).getTime();
    if (pMs <= atMs) {
      const storeName = p.defaultProfile || Object.keys(p.store || {})[0];
      const store = p.store?.[storeName];
      if (store) return { profile: p, store, loopSettings: p.loopSettings };
    }
  }
  return null;
}

// --- Compute glucose status from recent entries ---
function computeGlucoseStatus(entries, atTime, lookbackMin = 60) {
  const atMs = atTime.getTime();
  const recent = entries.filter(e => {
    const ems = new Date(e.dateString || e.sysTime).getTime();
    return ems <= atMs && ems >= atMs - lookbackMin * 60000;
  });

  if (recent.length < 3) return null;

  const current = recent[0];
  const bg = current.sgv;
  const bgTime = new Date(current.dateString || current.sysTime);

  // Delta: difference from ~5 min ago
  const prev5 = recent.find(e => {
    const age = (atMs - new Date(e.dateString || e.sysTime).getTime()) / 60000;
    return age >= 4 && age <= 7;
  });

  // Short avg delta: ~15 min
  const prev15 = recent.find(e => {
    const age = (atMs - new Date(e.dateString || e.sysTime).getTime()) / 60000;
    return age >= 13 && age <= 18;
  });

  // Long avg delta: ~45 min
  const prev45 = recent.find(e => {
    const age = (atMs - new Date(e.dateString || e.sysTime).getTime()) / 60000;
    return age >= 40 && age <= 50;
  });

  const delta = prev5 ? bg - prev5.sgv : 0;
  const shortAvgDelta = prev15 ? (bg - prev15.sgv) / 3 : delta;
  const longAvgDelta = prev45 ? (bg - prev45.sgv) / 9 : shortAvgDelta;

  return {
    glucose: bg,
    glucoseUnit: 'mg/dL',
    delta: round(delta, 2),
    shortAvgDelta: round(shortAvgDelta, 2),
    longAvgDelta: round(longAvgDelta, 2),
    timestamp: bgTime.toISOString(),
    noise: current.noise || 0,
    direction: current.direction || 'NONE',
  };
}

// --- Build glucose history array ---
function buildGlucoseHistory(entries, atTime, lookbackMin = 360) {
  const atMs = atTime.getTime();
  return entries
    .filter(e => {
      const ems = new Date(e.dateString || e.sysTime).getTime();
      return ems <= atMs && ems >= atMs - lookbackMin * 60000;
    })
    .map(e => ({
      glucose: e.sgv,
      timestamp: e.dateString || e.sysTime,
    }));
}

// --- Build dose history from treatments ---
function buildDoseHistory(treatments, atTime, lookbackHours = 6) {
  const atMs = atTime.getTime();
  const cutoff = atMs - lookbackHours * 3600000;
  const doses = [];

  for (const t of treatments) {
    const tMs = new Date(t.timestamp || t.created_at).getTime();
    if (tMs > atMs || tMs < cutoff) continue;

    if (t.eventType === 'Temp Basal') {
      doses.push({
        type: 'tempBasal',
        rate: t.rate || t.absolute,
        duration: t.duration || 30,
        startTime: t.timestamp || t.created_at,
        units: (t.rate || t.absolute || 0) * (t.duration || 30) / 60,
        insulinType: t.insulinType || 'Novolog',
      });
    } else if (t.insulin > 0) {
      doses.push({
        type: 'bolus',
        units: t.insulin,
        startTime: t.timestamp || t.created_at,
        duration: t.duration || 0,
        insulinType: t.insulinType || 'Novolog',
      });
    }
  }

  return doses;
}

// --- Build carb history from treatments ---
function buildCarbHistory(treatments, atTime, lookbackHours = 6) {
  const atMs = atTime.getTime();
  const cutoff = atMs - lookbackHours * 3600000;
  const carbs = [];

  for (const t of treatments) {
    const tMs = new Date(t.timestamp || t.created_at).getTime();
    if (tMs > atMs || tMs < cutoff) continue;

    if (t.eventType === 'Carb Correction' || (t.carbs && t.carbs > 0)) {
      carbs.push({
        carbs: t.carbs,
        timestamp: t.timestamp || t.created_at,
        absorptionTime: t.absorptionTime || 180,
      });
    }
  }

  return carbs;
}

// --- Build profile in adapter format ---
function buildAdapterProfile(store, loopSettings) {
  const basal = store.basal?.[0]?.value || 1.0;
  const sens = store.sens?.[0]?.value || 50;
  const cr = store.carbratio?.[0]?.value || 10;
  const targetLow = store.target_low?.[0]?.value || 100;
  const targetHigh = store.target_high?.[0]?.value || 120;
  const dia = store.dia || 6;
  const maxBasal = loopSettings?.maximumBasalRatePerHour || 4;
  const maxBolus = loopSettings?.maximumBolus || 10;
  const maxIob = 20; // Loop doesn't have a simple maxIOB setting like oref0

  return {
    basalRate: basal,
    sensitivity: sens,
    carbRatio: cr,
    targetLow,
    targetHigh,
    maxIob,
    maxBasal,
    dia,
    maxDailyBasal: basal,
    units: store.units || 'mg/dL',
    dosingStrategy: loopSettings?.dosingStrategy || 'tempBasalOnly',
    suspendThreshold: loopSettings?.minimumBGGuard,
    // Full basal schedule for dose annotation
    basalSchedule: store.basal?.map(b => ({
      startTime: b.timeAsSeconds || 0,
      rate: b.value,
    })),
  };
}

// --- Categorize vector based on conditions ---
function categorize(glucoseStatus, iob, cob, enacted) {
  const bg = glucoseStatus.glucose;
  const categories = [];

  if (bg < 70) categories.push('hypo');
  else if (bg < 90) categories.push('low-range');
  else if (bg <= 180) categories.push('in-range');
  else if (bg <= 250) categories.push('high');
  else categories.push('very-high');

  if (cob > 0) categories.push('meal-active');
  if (iob > 3) categories.push('high-iob');
  if (Math.abs(glucoseStatus.delta) > 15) categories.push('rapid-change');
  if (enacted?.rate === 0) categories.push('zero-temp');

  return categories.join(',');
}

// --- Sample diverse records ---
function sampleRecords(devicestatus, maxSamples, minGapMin) {
  const valid = devicestatus.filter(d =>
    d.loop?.predicted?.values?.length > 10 &&
    d.loop?.iob?.iob != null
  );

  if (valid.length <= maxSamples) return valid;

  // Stratified sampling: ensure diversity
  const sampled = [];
  let lastMs = 0;

  // First pass: ensure minimum gap
  for (const d of valid) {
    const ms = new Date(d.created_at).getTime();
    if (Math.abs(ms - lastMs) >= minGapMin * 60000 || sampled.length === 0) {
      sampled.push(d);
      lastMs = ms;
    }
    if (sampled.length >= maxSamples) break;
  }

  return sampled;
}

function round(n, places) {
  const f = Math.pow(10, places);
  return Math.round(n * f) / f;
}

// --- Main ---
function main() {
  const opts = parseArgs();
  const { entries, treatments, devicestatus, profiles } = loadFixtures(opts.fixtureDir);

  // Sort profiles by mills descending
  profiles.sort((a, b) => (b.mills || 0) - (a.mills || 0));

  // Sample records
  const sampled = sampleRecords(devicestatus, opts.sample, opts.minGapMin);
  console.error(`Sampled ${sampled.length} records (min gap ${opts.minGapMin}min)`);

  // Create output dir
  fs.mkdirSync(opts.outputDir, { recursive: true });

  let generated = 0;
  let skipped = 0;
  const stats = { inRange: 0, low: 0, high: 0, withMeal: 0, withBolus: 0 };

  for (let idx = 0; idx < sampled.length; idx++) {
    const rec = sampled[idx];
    const ts = new Date(rec.created_at);

    // Get active profile
    const profileData = getActiveProfile(profiles, ts);
    if (!profileData) { skipped++; continue; }

    // Compute glucose status
    const glucoseStatus = computeGlucoseStatus(entries, ts, opts.glucoseMinutes);
    if (!glucoseStatus) { skipped++; continue; }

    // Build context
    const glucoseHistory = buildGlucoseHistory(entries, ts, 360);
    const doseHistory = buildDoseHistory(treatments, ts, opts.diaHours);
    const carbHistory = buildCarbHistory(treatments, ts, opts.diaHours);
    const profile = buildAdapterProfile(profileData.store, profileData.loopSettings);

    // IOB/COB from Loop's own calculation
    const iob = rec.loop.iob?.iob || 0;
    const cob = rec.loop.cob?.cob || 0;

    // Ground truth: Loop's predictions and enacted rate
    const predicted = rec.loop.predicted;
    const enacted = rec.loop.enacted;
    const category = categorize(glucoseStatus, iob, cob, enacted);

    // Stats
    if (glucoseStatus.glucose <= 180 && glucoseStatus.glucose >= 70) stats.inRange++;
    else if (glucoseStatus.glucose < 70) stats.low++;
    else stats.high++;
    if (cob > 0) stats.withMeal++;
    if (doseHistory.some(d => d.type === 'bolus')) stats.withBolus++;

    const vectorId = `LV-${String(generated + 1).padStart(3, '0')}`;
    const vector = {
      version: '1.0.0',
      metadata: {
        id: vectorId,
        name: `Loop replay ${ts.toISOString().slice(0, 19).replace('T', ' ')}`,
        category,
        source: 'nightscout/90-day-history',
        description: `Real Loop decision point. BG ${glucoseStatus.glucose}, IOB ${round(iob, 2)}, COB ${round(cob, 1)}`,
        algorithm: 'Loop',
        loopVersion: rec.loop.version,
        device: rec.device,
      },
      input: {
        clock: ts.toISOString(),
        glucoseStatus,
        iob: {
          iob: round(iob, 4),
          basalIob: round(iob, 4),
          bolusIob: 0,
          activity: 0, // Loop doesn't report activity in NS devicestatus
          iobWithZeroTemp: {
            iob: round(iob, 4),
            basaliob: round(iob, 4),
            bolussnooze: 0,
            activity: 0,
            lastBolusTime: 0,
            time: ts.toISOString(),
          },
        },
        profile,
        mealData: {
          carbs: 0,
          cob: round(cob, 2),
        },
        currentTemp: enacted ? {
          rate: enacted.rate,
          duration: enacted.duration || 30,
        } : null,
        // Extension fields for full-fidelity mode
        glucoseHistory,
        doseHistory,
        carbHistory,
      },
      expected: {
        rate: enacted?.rate,
        duration: enacted?.duration,
        recommendedBolus: rec.loop.recommendedBolus,
        iob: round(iob, 2),
        cob: round(cob, 1),
      },
      groundTruth: {
        source: 'loop-devicestatus',
        predictions: predicted?.values || [],
        predictionStart: predicted?.startDate,
        loopVersion: rec.loop.version,
        enacted: enacted,
        override: rec.override,
      },
    };

    const filename = `${vectorId}-${ts.toISOString().slice(0, 10)}.json`;
    fs.writeFileSync(
      path.join(opts.outputDir, filename),
      JSON.stringify(vector, null, 2)
    );
    generated++;
  }

  console.error(`\nGenerated ${generated} vectors, skipped ${skipped}`);
  console.error(`Stats: ${stats.inRange} in-range, ${stats.low} low, ${stats.high} high, ${stats.withMeal} with-meal, ${stats.withBolus} with-bolus`);
  console.error(`Output: ${opts.outputDir}/`);

  // Print summary to stdout as JSON
  console.log(JSON.stringify({
    generated,
    skipped,
    stats,
    outputDir: opts.outputDir,
  }, null, 2));
}

main();
