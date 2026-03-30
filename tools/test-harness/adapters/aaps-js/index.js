'use strict';

/**
 * AAPS-JS adapter: runs AAPS's modified oref0 determine-basal.js through Node.js.
 *
 * AAPS ships a modified version of oref0's determine-basal.js that differs from
 * upstream in several ways:
 *   - round_basal is a no-op (returns input unchanged)
 *   - flatBGsDetected is passed as 11th parameter
 *   - aCOBpredBGs (accelerated COB) prediction curve added
 *   - Removed high_bg SMB enablement
 *   - process.stderr.write → console.log for some outputs
 *   - Simplified reason string format
 *
 * Reads JSON from stdin, writes JSON to stdout.
 * Supports modes: execute, validate-input, describe.
 */

const path = require('path');
const Module = require('module');

const aapsPath = process.env.AAPS_PATH || '../../../../externals/AndroidAPS';
const assetsPath = path.resolve(__dirname, aapsPath, 'app/src/androidTest/assets');

// AAPS mocks round_basal as identity (DetermineBasalAdapterSMBJS.kt:117)
// We intercept require() calls for 'round-basal' or '../round-basal' to provide this mock.
const originalResolve = Module._resolveFilename;
Module._resolveFilename = function(request, parent, ...args) {
  if (request.endsWith('round-basal')) {
    return path.resolve(__dirname, 'round-basal-mock.js');
  }
  return originalResolve.call(this, request, parent, ...args);
};

// AAPS's JS uses console.log for diagnostic output (upstream uses process.stderr.write).
// Redirect console.log to stderr so it doesn't mix with JSON on stdout.
const originalLog = console.log;
console.log = (...args) => process.stderr.write(args.join(' ') + '\n');

let determineBasal, tempBasalFunctions;

try {
  determineBasal = require(path.resolve(assetsPath, 'OpenAPSSMB/determine-basal'));
  tempBasalFunctions = require(path.resolve(assetsPath, 'OpenAPSSMB/basal-set-temp'));
} catch (err) {
  // Will fail gracefully in describe mode
}

// ── Input Translation ──────────────────────────────────────────────

/**
 * Generate a 48-element IOB projection array from a snapshot.
 * Same logic as oref0-js adapter — AAPS also expects this array format.
 */
function generateIobArray(iobSnapshot, dia, currentTemp) {
  const DIA_MINUTES = (dia || 5) * 60;
  const TICKS = 48;
  const tau = DIA_MINUTES / 1.85;

  const iob0 = iobSnapshot.iob || 0;
  const basalIob0 = iobSnapshot.basalIob || 0;
  const activity0 = iobSnapshot.activity || 0;
  const iobZT0 = iobSnapshot.iobWithZeroTemp || {};

  const arr = [];
  for (let i = 0; i < TICKS; i++) {
    const t = i * 5;
    const decay = Math.exp(-t / tau);

    const tick = {
      iob: round(iob0 * decay, 3),
      basaliob: round(basalIob0 * decay, 3),
      activity: round(activity0 * decay, 5),
      time: t,
    };

    // iobWithZeroTemp: IOB projection if basal were zeroed from now
    const iobZTval = (typeof iobZT0 === 'object') ? (iobZT0.iob || iob0) : (iobZT0 || iob0);
    const actZTval = (typeof iobZT0 === 'object') ? (iobZT0.activity || activity0) : activity0;

    let ztIob = iobZTval * decay;
    let ztActivity = actZTval * decay;

    // Subtract future scheduled basal contribution for ZT projection
    if (currentTemp && currentTemp.rate > 0 && currentTemp.duration > 0) {
      const basalRate = currentTemp.rate;
      const remainMin = Math.max(0, currentTemp.duration - t);
      if (remainMin > 0) {
        const basalContrib = (basalRate / 60) * Math.min(5, remainMin);
        ztIob -= basalContrib * decay * 0.5;
      }
    }

    tick.iobWithZeroTemp = {
      iob: round(ztIob, 3),
      activity: round(ztActivity, 5),
    };

    arr.push(tick);
  }

  return arr;
}

/**
 * Translate adapter protocol input → AAPS native input.
 * Key difference from oref0-js: adds flatBGsDetected, different profile fields.
 */
function translateInput(adapterInput) {
  const gs = adapterInput.glucoseStatus || {};
  const iob = adapterInput.iob || {};
  const prof = adapterInput.profile || {};
  const meal = adapterInput.mealData || {};
  const temp = adapterInput.currentTemp || {};
  const autosens = adapterInput.autosensData || {};

  const basalRate = prof.basalRate || 1.0;

  const glucoseStatus = {
    glucose: gs.glucose,
    delta: gs.delta || 0,
    short_avgdelta: gs.shortAvgDelta ?? gs.delta ?? 0,
    long_avgdelta: gs.longAvgDelta ?? gs.delta ?? 0,
    date: gs.timestamp ? new Date(gs.timestamp).getTime() : Date.now(),
    noise: gs.noise || 0,
  };

  const currentTemp = {
    rate: temp.rate || 0,
    duration: temp.duration || 0,
    temp: 'absolute',
  };

  const iobData = generateIobArray(iob, prof.dia, temp);

  const profile = {
    current_basal: basalRate,
    sens: prof.sensitivity || 50,
    carb_ratio: prof.carbRatio || 10,
    target_bg: ((prof.targetLow || 100) + (prof.targetHigh || 100)) / 2,
    min_bg: prof.targetLow || 100,
    max_bg: prof.targetHigh || 100,
    max_basal: prof.maxBasal || 3.0,
    max_iob: prof.maxIob || 5.0,
    max_daily_basal: prof.maxDailyBasal || basalRate,
    max_daily_safety_multiplier: 3,
    current_basal_safety_multiplier: 4,
    dia: prof.dia || 5,
    skip_neutral_temps: false,
    // AAPS profile fields
    enableSMB_with_bolus: prof.enableSMB || false,
    enableSMB_always: prof.enableSMB || false,
    enableSMB_with_COB: prof.enableSMB || false,
    enableSMB_with_temptarget: false,
    enableSMB_after_carbs: false,
    enableUAM: prof.enableUAM || false,
    maxSMBBasalMinutes: prof.maxSMBBasalMinutes || 30,
    maxUAMSMBBasalMinutes: prof.maxUAMSMBBasalMinutes || 30,
    SMBInterval: prof.smbInterval || 3,
    bolus_increment: prof.bolusIncrement || 0.1,
    remainingCarbsCap: 90,
    carbsReqThreshold: 1,
    out_units: prof.units || 'mg/dL',
    type: 'current',
    min_5m_carbimpact: prof.min5mCarbImpact || 8,
    // AAPS extended fields (not used in standard mode)
    variable_sens: 0,
    insulinDivisor: 0,
    TDD: 0,
  };

  const autosensData = {
    ratio: autosens.ratio || 1.0,
  };

  const mealData = {
    carbs: meal.carbs || 0,
    mealCOB: meal.cob ?? meal.mealCOB ?? 0,
    slopeFromMaxDeviation: meal.slopeFromMaxDeviation ?? 0,
    slopeFromMinDeviation: meal.slopeFromMinDeviation ?? 0,
    lastCarbTime: meal.lastCarbTime || (Date.now() - 2 * 60 * 60 * 1000),
  };

  const microBolusAllowed = adapterInput.microBolusAllowed || false;
  const flatBGsDetected = adapterInput.flatBGsDetected || false;

  return {
    glucoseStatus,
    currentTemp,
    iobData,
    profile,
    autosensData,
    mealData,
    microBolusAllowed,
    reservoirData: null,
    currentTime: new Date(adapterInput.clock || Date.now()).getTime(),
    flatBGsDetected,
  };
}

// ── Output Translation ──────────────────────────────────────────────

function translateOutput(nativeOutput, nativeInput, elapsedMs) {
  const predBGs = nativeOutput.predBGs || {};

  return {
    algorithm: {
      name: 'aaps-js',
      version: '0.1.0-aaps',
    },
    decision: {
      rate: nativeOutput.rate ?? null,
      duration: nativeOutput.duration ?? null,
      smb: nativeOutput.units ?? null,
      reason: nativeOutput.reason || '',
    },
    predictions: {
      eventualBG: nativeOutput.eventualBG ?? null,
      minPredBG: nativeOutput.minPredBG ?? null,
      iob: predBGs.IOB || [],
      zt: predBGs.ZT || [],
      cob: predBGs.COB || [],
      uam: predBGs.UAM || [],
      acob: predBGs.aCOB || [],  // AAPS-specific: accelerated COB
    },
    state: {
      iob: nativeOutput.IOB ?? null,
      cob: nativeOutput.COB ?? null,
      bg: nativeOutput.bg ?? null,
      tick: nativeOutput.tick || '',
      insulinReq: nativeOutput.insulinReq ?? null,
      sensitivityRatio: nativeOutput.sensitivityRatio ?? null,
    },
    metadata: {
      executionTimeMs: elapsedMs,
      warnings: [],
      nativeOutput: nativeOutput,
    },
  };
}

// ── Mode Handlers ───────────────────────────────────────────────────

function handleExecute(adapterInput, verbose) {
  if (!determineBasal) {
    return { error: `Cannot load AAPS determine-basal from ${assetsPath}` };
  }

  const nativeInput = translateInput(adapterInput);
  const startMs = Date.now();

  try {
    // AAPS calls determine_basal with 11 parameters (adds flatBGsDetected)
    const nativeOutput = determineBasal(
      nativeInput.glucoseStatus,
      nativeInput.currentTemp,
      nativeInput.iobData,
      nativeInput.profile,
      nativeInput.autosensData,
      nativeInput.mealData,
      tempBasalFunctions,
      nativeInput.microBolusAllowed,
      nativeInput.reservoirData,
      nativeInput.currentTime,
      nativeInput.flatBGsDetected    // 11th param: AAPS-specific
    );

    const elapsedMs = Date.now() - startMs;
    const output = translateOutput(nativeOutput, nativeInput, elapsedMs);

    if (verbose) {
      output.metadata.nativeInput = nativeInput;
    }

    return output;
  } catch (err) {
    return {
      error: err.message,
      stack: err.stack,
      algorithm: { name: 'aaps-js', version: '0.1.0-aaps' },
    };
  }
}

function handleValidateInput(adapterInput) {
  const nativeInput = translateInput(adapterInput);
  const warnings = [];

  if (!nativeInput.glucoseStatus.glucose) {
    warnings.push('Missing glucose reading');
  }
  if (nativeInput.profile.max_daily_basal <= 0) {
    warnings.push('max_daily_basal <= 0, rate capping may fail (NaN)');
  }

  return {
    valid: warnings.length === 0,
    nativeInput,
    warnings,
    fieldMapping: {
      'adapter.glucoseStatus.glucose': 'aaps.glucose_status.glucose',
      'adapter.iob.iob': 'aaps.iob_data[0].iob (+ 47 projected ticks)',
      'adapter.profile.sensitivity': 'aaps.profile.sens',
      'adapter.profile.carbRatio': 'aaps.profile.carb_ratio',
      'adapter.profile.basalRate': 'aaps.profile.current_basal',
      'adapter.flatBGsDetected': 'aaps.flatBGsDetected (11th param)',
    },
  };
}

function handleDescribe() {
  return {
    name: 'aaps-js',
    algorithm: 'oref0-aaps',
    version: '0.1.0-aaps',
    language: 'javascript',
    capabilities: {
      predictions: true,
      smb: true,
      acob: true,
      effectModifiers: false,
      inputValidation: true,
    },
    differences_from_upstream: [
      'round_basal is identity function (no pump-precision rounding)',
      'flatBGsDetected parameter replaces inline tooflat computation',
      'aCOBpredBGs (accelerated COB) prediction curve added',
      'Removed high_bg SMB enablement feature',
      'Simplified reason string format',
      'sensitivityRatio safety guard removed for low targets',
      'bolus_increment always from profile (no 0.1 default)',
    ],
  };
}

// ── Main ────────────────────────────────────────────────────────────

function main() {
  let rawInput = '';

  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => { rawInput += chunk; });
  process.stdin.on('end', () => {
    let request;
    try {
      request = JSON.parse(rawInput);
    } catch (err) {
      process.stdout.write(JSON.stringify({ error: `Invalid JSON input: ${err.message}` }));
      process.exit(1);
    }

    const mode = request.mode || 'execute';
    const verbose = request.verbose || false;
    let result;

    switch (mode) {
      case 'execute':
        result = handleExecute(request.input, verbose);
        break;
      case 'validate-input':
        result = handleValidateInput(request.input);
        break;
      case 'describe':
        result = handleDescribe();
        break;
      default:
        result = { error: `Unknown mode: ${mode}` };
    }

    process.stdout.write(JSON.stringify(result));
  });
}

function round(n, places) {
  const factor = Math.pow(10, places);
  return Math.round(n * factor) / factor;
}

main();
