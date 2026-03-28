#!/usr/bin/env node
/**
 * End-to-end oref0 test vector runner
 *
 * Runs oref0 determine-basal directly (as library) against 100+ TV-* vectors
 * with real inputs and expected outputs from t1pal conformance suite.
 *
 * Usage:
 *   node run-oref0-endtoend.js                    # run all vectors, summary
 *   node run-oref0-endtoend.js --json             # full JSON output
 *   node run-oref0-endtoend.js --verbose          # per-vector detail
 *   node run-oref0-endtoend.js TV-086-*.json      # single vector
 *
 * Tolerances (from t1pal AUTORESEARCH-AID-RECOMMENDATIONS.md §2.3):
 *   rate:      0.05 U/hr
 *   eventualBG: 10.0 mg/dL
 *   insulinReq: 0.05 U
 *   IOB:        0.01 U
 *
 * Trace: ALG-VERIFY-002, REQ-030
 */

const fs = require('fs');
const path = require('path');

// oref0 library imports (relative to repo root)
const REPO_ROOT = path.resolve(__dirname, '../..');
const determineBasal = require(path.join(REPO_ROOT, 'externals/oref0/lib/determine-basal/determine-basal'));
const tempBasalFunctions = require(path.join(REPO_ROOT, 'externals/oref0/lib/basal-set-temp'));

const VECTORS_DIR = path.join(REPO_ROOT, 'conformance/t1pal/vectors/oref0-endtoend');

// Tolerances
const TOL = {
    rate: 0.05,        // U/hr
    eventualBG: 10.0,  // mg/dL
    insulinReq: 0.05,  // U
    iob: 0.01,         // U
    cob: 1.0           // g
};

/**
 * Generate a projected IOB array (48 ticks, 5-min intervals, 4 hours)
 * from a single IOB snapshot.
 *
 * Uses separate decay rates (tau) for the main IOB curve and iobWithZeroTemp.
 * oref0's determine-basal (line 576-577) uses both iobTick.activity and
 * iobTick.iobWithZeroTemp.activity at each prediction step — these must
 * diverge when a temp basal is active.
 */
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

    // Calibrate tau from activity/iob ratio when data is available
    let tau = diaMins / 1.85; // default ~130min for DIA=4h
    if (Math.abs(iob0) > 0.01 && Math.abs(activity0) > 0.0001) {
        const ratePerMin = Math.abs(activity0 / iob0);
        if (ratePerMin > 0.0001 && ratePerMin < 0.1) {
            tau = Math.min(diaMins, Math.max(30, 1 / ratePerMin));
        }
    }

    // Separate tau for zero-temp curve (may differ when temp basal is active)
    let tauZT = tau;
    if (Math.abs(ztIob0) > 0.01 && Math.abs(ztActivity0) > 0.0001) {
        const rZT = Math.abs(ztActivity0 / ztIob0);
        if (rZT > 0.0001 && rZT < 0.1) {
            tauZT = Math.min(diaMins, Math.max(30, 1 / rZT));
        }
    }

    const basalFrac = (iob0 !== 0) ? (basaliob0 / iob0) : 0.5;
    const ztBasalFrac = (ztIob0 !== 0) ? (ztBasaliob0 / ztIob0) : 0.5;

    for (let i = 0; i < ticks; i++) {
        const t = i * 5; // minutes from now
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
            lastBolusTime: iobSnapshot.lastBolusTime || (Date.now() - 3600000),
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

/**
 * Convert test vector input format to oref0 determine-basal parameters.
 * Adapted from t1pal run-oref0-vectors.js vectorToOref0Inputs().
 *
 * Key improvement: generates a 48-element IOB projection array so oref0's
 * prediction loop (minPredBG, ZT, COB, UAM curves) can function properly.
 */
function vectorToOref0Inputs(vector) {
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

    // Generate projected IOB array for prediction loop
    const iobData = generateIobArray(iobSnapshot, dia, currentTemp);

    const p = input.profile;
    const profile = {
        current_basal: p.basalRate || p.currentBasal || 1.0,
        sens: p.sensitivity || 50,
        carb_ratio: p.carbRatio || 10,
        target_bg: ((p.targetLow || 100) + (p.targetHigh || 110)) / 2,
        min_bg: p.targetLow || 100,
        max_bg: p.targetHigh || 110,
        max_basal: p.maxBasal || 3.0,
        max_iob: p.maxIob || 5.0,
        max_daily_basal: p.maxDailyBasal || p.basalRate || p.currentBasal || 1.0,
        max_daily_safety_multiplier: p.maxDailySafetyMultiplier || 3,
        current_basal_safety_multiplier: p.currentBasalSafetyMultiplier || 4,
        dia: p.dia || 4,
        skip_neutral_temps: false,
        enableSMB_with_bolus: p.enableSMB || false,
        enableSMB_always: p.enableSMB || false,
        enableSMB_with_COB: p.enableSMB || false,
        enableSMB_with_temptarget: false,
        enableSMB_after_carbs: false,
        enableUAM: p.enableUAM || false,
        maxSMBBasalMinutes: p.maxSMBBasalMinutes || 30,
        maxUAMSMBBasalMinutes: p.maxUAMSMBBasalMinutes || 30,
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

    const microBolusAllowed = input.microBolusAllowed || false;

    return { glucoseStatus, iobData, profile, currentTemp, mealData, autosens, microBolusAllowed };
}

/**
 * Run determine-basal on a single vector. Returns result + comparison.
 */
function runVector(vector) {
    const id = vector.metadata?.id || 'unknown';
    try {
        const { glucoseStatus, iobData, profile, currentTemp, mealData, autosens, microBolusAllowed } =
            vectorToOref0Inputs(vector);

        // Suppress stderr during execution
        const origErr = console.error;
        const stderrLines = [];
        console.error = (...args) => stderrLines.push(args.join(' '));

        const result = determineBasal(
            glucoseStatus, currentTemp, iobData, profile,
            autosens, mealData, tempBasalFunctions,
            microBolusAllowed, null, Date.now()
        );

        console.error = origErr;

        if (result.error) {
            return { id, status: 'error', error: result.error, debug: stderrLines.slice(0, 3) };
        }

        // Compare against expected
        const expected = vector.expected || {};
        const diffs = {};
        let pass = true;

        if (expected.rate != null && result.rate != null) {
            diffs.rate = { expected: expected.rate, actual: result.rate, diff: Math.abs(result.rate - expected.rate) };
            if (diffs.rate.diff > TOL.rate) pass = false;
        }
        if (expected.eventualBG != null && result.eventualBG != null) {
            diffs.eventualBG = { expected: expected.eventualBG, actual: result.eventualBG, diff: Math.abs(result.eventualBG - expected.eventualBG) };
            if (diffs.eventualBG.diff > TOL.eventualBG) pass = false;
        }
        if (expected.insulinReq != null && result.insulinReq != null) {
            diffs.insulinReq = { expected: expected.insulinReq, actual: result.insulinReq, diff: Math.abs(result.insulinReq - expected.insulinReq) };
            if (diffs.insulinReq.diff > TOL.insulinReq) pass = false;
        }
        if (expected.iob != null) {
            diffs.iob = { expected: expected.iob, actual: iobData_iob(vector), diff: Math.abs(expected.iob - iobData_iob(vector)) };
            if (diffs.iob.diff > TOL.iob) pass = false;
        }
        if (expected.duration != null && result.duration != null) {
            diffs.duration = { expected: expected.duration, actual: result.duration, match: result.duration === expected.duration };
            if (!diffs.duration.match) pass = false;
        }

        // If no rate expected and no rate returned, that's a "doing nothing" match
        if (expected.rate == null && result.rate == null) {
            // Both doing nothing — pass
        }
        // If expected has rate but result doesn't (or vice versa), flag mismatch
        if (expected.rate != null && result.rate == null) {
            diffs.rateMissing = { expected: expected.rate, actual: null };
            pass = false;
        }

        return {
            id,
            status: pass ? 'pass' : 'fail',
            category: vector.metadata?.category || 'unknown',
            result: {
                rate: result.rate,
                duration: result.duration,
                eventualBG: result.eventualBG,
                insulinReq: result.insulinReq,
                reason: result.reason
            },
            expected,
            diffs,
            debug: stderrLines.slice(0, 3)
        };
    } catch (error) {
        return { id, status: 'crash', error: error.message, stack: error.stack?.split('\n').slice(0, 3) };
    }
}

function iobData_iob(vector) {
    return vector.input?.iob?.iob || 0;
}

/**
 * Run all vectors in directory
 */
function runAll(dir) {
    const files = fs.readdirSync(dir)
        .filter(f => f.endsWith('.json'))
        .sort();

    const results = [];
    let pass = 0, fail = 0, error = 0, crash = 0, skipped = 0;

    for (const file of files) {
        const content = fs.readFileSync(path.join(dir, file), 'utf8');
        let vector;
        try {
            vector = JSON.parse(content);
        } catch (e) {
            results.push({ id: file, status: 'crash', error: 'JSON parse error' });
            crash++;
            continue;
        }

        // Skip parametric variants (stale expected outputs from base vector)
        if (vector.metadata?.parametricVariantOf || vector.metadata?.originalPredBGsStale) {
            skipped++;
            continue;
        }

        const r = runVector(vector);
        results.push(r);
        if (r.status === 'pass') pass++;
        else if (r.status === 'fail') fail++;
        else if (r.status === 'error') error++;
        else crash++;
    }

    // Compute tiered tolerance pass rates from results
    const tiers = [
        { name: 'strict', rateTol: 0.05, ebgTol: 10, irTol: 0.05 },
        { name: 'reasonable', rateTol: 0.5, ebgTol: 25, irTol: 0.5 },
        { name: 'lax', rateTol: 2.0, ebgTol: 50, irTol: 2.0 },
    ];
    const tierResults = {};
    for (const tier of tiers) {
        let tierPass = 0;
        for (const r of results) {
            if (r.status === 'crash' || r.status === 'error') continue;
            const d = r.diffs || {};
            let ok = true;
            if (d.rate && d.rate.diff > tier.rateTol) ok = false;
            if (d.eventualBG && d.eventualBG.diff > tier.ebgTol) ok = false;
            if (d.insulinReq && d.insulinReq.diff > tier.irTol) ok = false;
            if (d.rateMissing) ok = false;
            if (ok) tierPass++;
        }
        tierResults[tier.name] = { pass: tierPass, total: results.length,
            rate: results.length > 0 ? (tierPass / results.length * 100).toFixed(1) + '%' : '0%' };
    }

    return {
        summary: {
            total: files.length,
            scored: results.length,
            skipped,
            pass,
            fail,
            error,
            crash,
            passRate: results.length > 0 ? (pass / results.length * 100).toFixed(1) + '%' : '0%',
            tolerances: TOL,
            tiers: tierResults
        },
        results
    };
}

// --- Main ---
const args = process.argv.slice(2);
const jsonFlag = args.includes('--json');
const verboseFlag = args.includes('--verbose');
const cleanArgs = args.filter(a => !a.startsWith('--'));

if (cleanArgs.length > 0) {
    // Single vector
    const vectorPath = path.resolve(cleanArgs[0]);
    const vector = JSON.parse(fs.readFileSync(vectorPath, 'utf8'));
    const result = runVector(vector);
    console.log(JSON.stringify(result, null, 2));
} else {
    // All vectors
    const output = runAll(VECTORS_DIR);

    if (jsonFlag) {
        console.log(JSON.stringify(output, null, 2));
    } else {
        // Summary + failures
        const s = output.summary;
        console.log(`\noref0 End-to-End Validation (${s.total} vectors, ${s.skipped} parametric skipped)`);
        console.log('='.repeat(55));
        console.log(`  SCORED: ${s.scored}  (excl. ${s.skipped} parametric variants)`);
        console.log(`  PASS:   ${s.pass}`);
        console.log(`  FAIL:   ${s.fail}`);
        console.log(`  ERROR:  ${s.error}`);
        console.log(`  CRASH:  ${s.crash}`);
        console.log(`  Rate:   ${s.passRate}`);
        console.log(`\nTolerances: rate=${TOL.rate} U/hr, eventualBG=${TOL.eventualBG} mg/dL, insulinReq=${TOL.insulinReq} U`);

        // Tiered tolerance breakdown
        if (s.tiers) {
            console.log(`\nTiered Pass Rates:`);
            console.log(`  Strict   (rate≤0.05, eBG≤10, iR≤0.05): ${s.tiers.strict.rate}  (${s.tiers.strict.pass}/${s.tiers.strict.total})`);
            console.log(`  Reasonable (rate≤0.5, eBG≤25, iR≤0.5): ${s.tiers.reasonable.rate}  (${s.tiers.reasonable.pass}/${s.tiers.reasonable.total})`);
            console.log(`  Lax      (rate≤2.0, eBG≤50, iR≤2.0):   ${s.tiers.lax.rate}  (${s.tiers.lax.pass}/${s.tiers.lax.total})`);
        }

        // Show failures
        const failures = output.results.filter(r => r.status !== 'pass');
        if (failures.length > 0 && (verboseFlag || failures.length <= 20)) {
            console.log(`\nFailures/Errors:`);
            for (const f of failures) {
                if (f.status === 'crash' || f.status === 'error') {
                    console.log(`  ${f.id}: ${f.status} — ${f.error}`);
                } else {
                    const diffStrs = Object.entries(f.diffs || {})
                        .filter(([, v]) => v.diff > 0 || v.match === false || v.actual === null)
                        .map(([k, v]) => `${k}: exp=${v.expected} got=${v.actual}`)
                        .join(', ');
                    console.log(`  ${f.id}: FAIL — ${diffStrs}`);
                }
            }
        }

        // Show pass detail if verbose
        if (verboseFlag) {
            console.log(`\nPassed:`);
            for (const r of output.results.filter(r => r.status === 'pass')) {
                console.log(`  ${r.id}: rate=${r.result.rate} eventualBG=${r.result.eventualBG}`);
            }
        }
    }
}
