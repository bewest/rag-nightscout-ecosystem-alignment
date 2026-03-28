#!/usr/bin/env node
/**
 * oref0 Batch Glucose Predictor for GluPredKit Integration
 *
 * Reads JSON array of prediction requests on stdin, runs oref0 determine-basal
 * for each, and outputs JSON array of predicted glucose trajectories.
 *
 * Input format (JSON array on stdin):
 * [
 *   {
 *     "glucose": [145, 143, 140, ...],  // newest-first, 5-min intervals
 *     "insulin": [0.1, 0, 0.05, ...],   // bolus amounts per 5-min interval (oldest-first)
 *     "basal": [0.8, 0.8, ...],         // basal U/hr per 5-min interval (oldest-first)
 *     "carbs": [0, 0, 15, ...],         // carb grams per 5-min interval (oldest-first)
 *     "profile": {
 *       "isf": 50, "cr": 10, "basal": 0.8, "target_bg": 110,
 *       "dia": 4, "max_basal": 3, "max_iob": 5
 *     },
 *     "prediction_horizon": 60           // minutes
 *   }, ...
 * ]
 *
 * Output: JSON array of predicted glucose trajectories (5-min intervals).
 * [
 *   [143, 141, 139, 137, ...],  // prediction_horizon/5 values
 *   ...
 * ]
 *
 * Trace: ALG-VERIFY-003, REQ-060
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '../..');
const determineBasal = require(path.join(REPO_ROOT, 'externals/oref0/lib/determine-basal/determine-basal'));
const tempBasalFunctions = require(path.join(REPO_ROOT, 'externals/oref0/lib/basal-set-temp'));

/**
 * Calculate IOB from a series of insulin doses using exponential activity model.
 * Based on oref0/lib/iob/calculate.js Walsh exponential curves.
 */
function calculateIobFromHistory(insulinDoses, basalRates, diaHours) {
    const diaMins = diaHours * 60;
    let totalIob = 0;
    let totalActivity = 0;
    let totalBasalIob = 0;

    // insulinDoses[i] = bolus units delivered i*5 minutes ago
    // basalRates[i] = basal U/hr at i*5 minutes ago
    for (let i = 0; i < insulinDoses.length; i++) {
        const minutesAgo = i * 5;
        if (minutesAgo >= diaMins) continue;

        // Bolus IOB
        const bolusDose = insulinDoses[i] || 0;
        if (bolusDose > 0) {
            const { iob, activity } = insulinOnBoard(bolusDose, minutesAgo, diaMins);
            totalIob += iob;
            totalActivity += activity;
        }

        // Basal IOB (convert U/hr to units delivered in 5 min)
        const basalRate = basalRates[i] || 0;
        const basalDose = basalRate * (5 / 60);
        if (basalDose > 0) {
            const { iob, activity } = insulinOnBoard(basalDose, minutesAgo, diaMins);
            totalIob += iob;
            totalActivity += activity;
            totalBasalIob += iob;
        }
    }

    return { iob: totalIob, activity: totalActivity, basaliob: totalBasalIob };
}

/**
 * Walsh exponential insulin activity curve.
 * Returns remaining IOB and current activity for a single dose.
 */
function insulinOnBoard(dose, minutesAgo, diaMins) {
    if (minutesAgo < 0 || minutesAgo >= diaMins) return { iob: 0, activity: 0 };

    const peak = diaMins * 0.375; // ~90min for DIA=4h
    const t = minutesAgo;

    // Bilinear exponential model (simplified Walsh)
    let iobFraction;
    if (t <= peak) {
        iobFraction = 1 - (0.5 * (t / peak) * (t / peak));
    } else {
        const remaining = (diaMins - t) / (diaMins - peak);
        iobFraction = 0.5 * remaining * remaining;
    }
    iobFraction = Math.max(0, Math.min(1, iobFraction));

    const iob = dose * iobFraction;
    // Activity is the derivative of insulin absorbed (negative derivative of IOB)
    const dt = 1; // 1-minute resolution
    let nextFraction;
    if ((t + dt) <= peak) {
        nextFraction = 1 - (0.5 * ((t + dt) / peak) * ((t + dt) / peak));
    } else if ((t + dt) >= diaMins) {
        nextFraction = 0;
    } else {
        const remaining = (diaMins - (t + dt)) / (diaMins - peak);
        nextFraction = 0.5 * remaining * remaining;
    }
    nextFraction = Math.max(0, Math.min(1, nextFraction));
    const activity = dose * (iobFraction - nextFraction); // units absorbed per minute

    return { iob, activity };
}

/**
 * Generate a 48-tick IOB projection array from current IOB state.
 * Used by oref0's prediction loop (determine-basal.js:574-643).
 */
function generateIobArray(iobState, diaHours, scheduledBasal) {
    const diaMins = diaHours * 60;
    const ticks = 48;
    const iobArray = [];

    const iob0 = iobState.iob;
    const activity0 = iobState.activity;
    const basaliob0 = iobState.basaliob;
    const iobZT0 = iobState.iobWithZeroTemp || {};
    const ztIob0 = iobZT0.iob != null ? iobZT0.iob : iob0;
    const ztActivity0 = iobZT0.activity != null ? iobZT0.activity : activity0;
    const ztBasaliob0 = iobZT0.basaliob != null ? iobZT0.basaliob : basaliob0;

    let tau = diaMins / 1.85;
    if (Math.abs(iob0) > 0.01 && Math.abs(activity0) > 0.0001) {
        const ratePerMin = Math.abs(activity0 / iob0);
        if (ratePerMin > 0.0001 && ratePerMin < 0.1) {
            tau = Math.min(diaMins, Math.max(30, 1 / ratePerMin));
        }
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
            iob: iobVal,
            basaliob: iobVal * basalFrac,
            bolussnooze: 0,
            activity: actVal,
            lastBolusTime: iobState.lastBolusTime || (Date.now() - 3600000),
            iobWithZeroTemp: {
                iob: ztIobVal,
                basaliob: ztIobVal * ztBasalFrac,
                bolussnooze: 0,
                activity: ztActVal,
                lastBolusTime: 0,
                time: new Date(Date.now() + t * 60000).toISOString()
            }
        };

        if (i === 0) {
            tick.lastTemp = { date: Date.now() - 300000, duration: 0 };
        }

        iobArray.push(tick);
    }

    return iobArray;
}

/**
 * Calculate glucoseStatus from glucose history array (newest-first).
 */
function calcGlucoseStatus(glucose) {
    if (!glucose || glucose.length < 2) {
        return { glucose: glucose[0] || 100, delta: 0, short_avgdelta: 0, long_avgdelta: 0, date: Date.now() };
    }

    const current = glucose[0];
    const delta = current - glucose[1];

    // Short avg delta: avg of last 3 deltas (15 min)
    let shortSum = 0, shortN = 0;
    for (let i = 0; i < Math.min(3, glucose.length - 1); i++) {
        shortSum += (glucose[i] - glucose[i + 1]);
        shortN++;
    }
    const short_avgdelta = shortN > 0 ? shortSum / shortN : delta;

    // Long avg delta: avg of last 6 deltas (30 min)
    let longSum = 0, longN = 0;
    for (let i = 0; i < Math.min(6, glucose.length - 1); i++) {
        longSum += (glucose[i] - glucose[i + 1]);
        longN++;
    }
    const long_avgdelta = longN > 0 ? longSum / longN : delta;

    return { glucose: current, delta, short_avgdelta, long_avgdelta, date: Date.now() };
}

/**
 * Calculate COB from carb history using linear decay model.
 */
function calcMealData(carbs, carbAbsorptionMinutes) {
    let mealCOB = 0;
    const absorptionRate = carbAbsorptionMinutes || 180; // 3-hour default

    // carbs[i] = grams at i*5 minutes ago (oldest-first)
    for (let i = 0; i < carbs.length; i++) {
        const g = carbs[i] || 0;
        if (g <= 0) continue;
        const minutesAgo = i * 5;
        const absorbed = Math.min(g, g * (minutesAgo / absorptionRate));
        mealCOB += Math.max(0, g - absorbed);
    }

    return {
        carbs: 0,
        mealCOB,
        slopeFromMaxDeviation: 0,
        slopeFromMinDeviation: 0,
        lastCarbTime: Date.now() - 2 * 60 * 60 * 1000
    };
}

/**
 * Process a single prediction request and return glucose trajectory.
 */
function predict(request) {
    const {
        glucose,
        insulin = [],
        basal = [],
        carbs = [],
        profile: profileSettings,
        prediction_horizon = 60
    } = request;

    const dia = profileSettings.dia || 4;
    const nSteps = Math.floor(prediction_horizon / 5);

    // Calculate current state from history
    const glucoseStatus = calcGlucoseStatus(glucose);

    // Calculate IOB from insulin + basal history
    const iobState = calculateIobFromHistory(insulin, basal, dia);

    // Generate projected IOB array
    const iobData = generateIobArray(iobState, dia, profileSettings.basal || 0.8);

    // Build profile
    const profile = {
        current_basal: profileSettings.basal || 0.8,
        sens: profileSettings.isf || 50,
        carb_ratio: profileSettings.cr || 10,
        target_bg: profileSettings.target_bg || 110,
        min_bg: profileSettings.target_bg ? profileSettings.target_bg - 5 : 100,
        max_bg: profileSettings.target_bg ? profileSettings.target_bg + 5 : 115,
        max_basal: profileSettings.max_basal || 3.0,
        max_iob: profileSettings.max_iob || 5.0,
        max_daily_basal: profileSettings.max_daily_basal || profileSettings.basal || 1.0,
        max_daily_safety_multiplier: profileSettings.max_daily_safety_multiplier || 3,
        current_basal_safety_multiplier: profileSettings.current_basal_safety_multiplier || 4,
        dia: dia,
        skip_neutral_temps: false,
        enableSMB_with_bolus: false,
        enableSMB_always: false,
        enableSMB_with_COB: false,
        enableSMB_with_temptarget: false,
        enableSMB_after_carbs: false,
        enableUAM: false,
        maxSMBBasalMinutes: 30,
        maxUAMSMBBasalMinutes: 30,
        SMBInterval: 3,
        bolus_increment: 0.05,
        out_units: 'mg/dL',
        type: 'current'
    };

    const currentTemp = { rate: 0, duration: 0 };
    const mealData = calcMealData(carbs, 180);
    const autosens = { ratio: 1.0 };

    // Suppress console.error during execution
    const origErr = console.error;
    console.error = () => {};

    let result;
    try {
        result = determineBasal(
            glucoseStatus, currentTemp, iobData, profile,
            autosens, mealData, tempBasalFunctions,
            false, null, Date.now()
        );
    } finally {
        console.error = origErr;
    }

    // Extract prediction trajectory from predBGs
    let trajectory = [];

    if (result && result.predBGs) {
        // Prefer IOB curve (primary prediction assuming current treatment continues)
        const curves = ['IOB', 'ZT', 'COB', 'UAM'];
        for (const curve of curves) {
            if (result.predBGs[curve] && result.predBGs[curve].length >= nSteps) {
                trajectory = result.predBGs[curve].slice(0, nSteps);
                break;
            }
        }
    }

    // Fallback: if no predBGs, use eventualBG with linear interpolation
    if (trajectory.length < nSteps) {
        const currentBG = glucoseStatus.glucose;
        const eventualBG = (result && result.eventualBG) || currentBG;
        trajectory = [];
        for (let i = 0; i < nSteps; i++) {
            const frac = (i + 1) / nSteps;
            trajectory.push(Math.round(currentBG + (eventualBG - currentBG) * frac));
        }
    }

    return trajectory;
}

// --- Main: read stdin, process, write stdout ---
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
    try {
        const requests = JSON.parse(input);
        if (!Array.isArray(requests)) {
            process.stderr.write('Error: input must be a JSON array\n');
            process.exit(1);
        }

        const results = requests.map((req, i) => {
            try {
                return predict(req);
            } catch (e) {
                process.stderr.write(`Error on request ${i}: ${e.message}\n`);
                // Return flat prediction as fallback
                const bg = (req.glucose && req.glucose[0]) || 100;
                const n = Math.floor((req.prediction_horizon || 60) / 5);
                return Array(n).fill(bg);
            }
        });

        process.stdout.write(JSON.stringify(results));
    } catch (e) {
        process.stderr.write(`JSON parse error: ${e.message}\n`);
        process.exit(1);
    }
});
