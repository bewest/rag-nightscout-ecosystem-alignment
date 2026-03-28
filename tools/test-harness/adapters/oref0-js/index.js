'use strict';

/**
 * oref0-js adapter: translates adapter protocol I/O to/from oref0 determine-basal.
 *
 * Reads JSON from stdin, writes JSON to stdout.
 * Supports modes: execute, validate-input, describe.
 */

const oref0Path = process.env.OREF0_PATH || '../../../../externals/oref0';
let determineBasal, tempBasalFunctions;

try {
  determineBasal = require(`${oref0Path}/lib/determine-basal/determine-basal`);
  tempBasalFunctions = require(`${oref0Path}/lib/basal-set-temp`);
} catch (err) {
  // Will fail gracefully in describe mode
}

// ── Input Translation ──────────────────────────────────────────────

/**
 * Generate a 48-element IOB projection array from a snapshot.
 * oref0 determine-basal needs this for prediction trajectory calculation.
 *
 * Each element represents a 5-minute tick with exponentially decaying IOB.
 * tau = DIA_minutes / 1.85 (approximation of the exponential decay constant)
 */
function generateIobArray(iobSnapshot, dia, currentTemp) {
  const DIA_MINUTES = (dia || 5) * 60;
  const TICKS = 48;
  const TICK_MINUTES = 5;
  const tau = DIA_MINUTES / 1.85;

  const iob0 = iobSnapshot.iob || 0;
  const basalIob0 = iobSnapshot.basalIob || iobSnapshot.basaliob || 0;
  const activity0 = iobSnapshot.activity || 0;

  const ztIob = iobSnapshot.iobWithZeroTemp || {};
  const ztIob0 = ztIob.iob ?? iob0;
  const ztActivity0 = ztIob.activity ?? activity0;

  const arr = [];

  for (let i = 0; i < TICKS; i++) {
    const t = i * TICK_MINUTES;
    const decay = Math.exp(-t / tau);

    const iobVal = iob0 * decay;
    const basalIobVal = basalIob0 * decay;
    const activityVal = activity0 * decay;

    const ztIobVal = ztIob0 * decay;
    const ztActivityVal = ztActivity0 * decay;

    const tick = {
      iob: round(iobVal, 4),
      basaliob: round(basalIobVal, 4),
      bolussnooze: 0,
      activity: round(activityVal, 6),
      lastBolusTime: iobSnapshot.lastBolusTime || 0,
      iobWithZeroTemp: {
        iob: round(ztIobVal, 4),
        basaliob: round(ztIobVal, 4),
        bolussnooze: 0,
        activity: round(ztActivityVal, 6),
        lastBolusTime: 0,
        time: new Date().toISOString(),
      },
    };

    if (i === 0 && currentTemp) {
      tick.lastTemp = {
        date: new Date().toISOString(),
        duration: currentTemp.duration || 0,
        rate: currentTemp.rate || 0,
      };
    }

    arr.push(tick);
  }

  return arr;
}

/**
 * Translate adapter protocol input → oref0 native input.
 * This is the critical translation layer that must be independently testable.
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
    enableSMB_with_bolus: prof.enableSMB || false,
    enableSMB_always: prof.enableSMB || false,
    enableSMB_with_COB: prof.enableSMB || false,
    enableSMB_with_temptarget: false,
    enableSMB_after_carbs: false,
    enableUAM: prof.enableUAM || false,
    maxSMBBasalMinutes: prof.maxSMBBasalMinutes || 30,
    maxUAMSMBBasalMinutes: prof.maxUAMSMBBasalMinutes || 30,
    SMBInterval: prof.smbInterval || 3,
    bolus_increment: 0.05,
    out_units: prof.units || 'mg/dL',
    type: 'current',
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

  return {
    glucoseStatus,
    currentTemp,
    iobData,
    profile,
    autosensData,
    mealData,
    microBolusAllowed,
    reservoirData: null,
    currentTime: new Date(adapterInput.clock || Date.now()),
  };
}

// ── Output Translation ──────────────────────────────────────────────

/**
 * Translate oref0 native output → adapter protocol output.
 */
function translateOutput(nativeOutput, nativeInput, elapsedMs) {
  const predBGs = nativeOutput.predBGs || {};

  return {
    algorithm: {
      name: 'oref0-js',
      version: getOref0Version(),
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
    },
  };
}

function getOref0Version() {
  try {
    const pkg = require(`${oref0Path}/package.json`);
    return pkg.version || '0.0.0';
  } catch {
    return '0.0.0';
  }
}

// ── Mode Handlers ───────────────────────────────────────────────────

function handleExecute(adapterInput, verbose) {
  if (!determineBasal) {
    return { error: `Cannot load oref0 from ${oref0Path}` };
  }

  const nativeInput = translateInput(adapterInput);
  const startMs = Date.now();

  try {
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
      nativeInput.currentTime
    );

    const elapsedMs = Date.now() - startMs;
    const output = translateOutput(nativeOutput, nativeInput, elapsedMs);

    if (verbose) {
      output.metadata.nativeInput = nativeInput;
      output.metadata.nativeOutput = nativeOutput;
    }

    return output;
  } catch (err) {
    return {
      error: err.message,
      stack: err.stack,
      algorithm: { name: 'oref0-js', version: getOref0Version() },
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
  if (nativeInput.iobData.length < 48) {
    warnings.push(`IOB array has ${nativeInput.iobData.length} elements, expected 48`);
  }

  return {
    valid: warnings.length === 0,
    nativeInput,
    warnings,
    fieldMapping: {
      'adapter.glucoseStatus.glucose': 'oref0.glucose_status.glucose',
      'adapter.iob.iob': 'oref0.iob_data[0].iob (+ 47 projected ticks)',
      'adapter.profile.sensitivity': 'oref0.profile.sens',
      'adapter.profile.carbRatio': 'oref0.profile.carb_ratio',
      'adapter.profile.basalRate': 'oref0.profile.current_basal',
      'adapter.profile.targetLow': 'oref0.profile.min_bg',
      'adapter.profile.targetHigh': 'oref0.profile.max_bg',
      'adapter.mealData.cob': 'oref0.meal_data.mealCOB',
    },
  };
}

function handleDescribe() {
  return {
    name: 'oref0-js',
    algorithm: 'oref0',
    version: getOref0Version(),
    language: 'javascript',
    capabilities: {
      predictions: true,
      smb: true,
      effectModifiers: false,
      inputValidation: true,
    },
    inputFields: [
      'glucoseStatus', 'iob', 'profile', 'mealData',
      'currentTemp', 'autosensData', 'microBolusAllowed',
    ],
    outputFields: [
      'rate', 'duration', 'eventualBG', 'minPredBG',
      'insulinReq', 'predBGs', 'reason',
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
