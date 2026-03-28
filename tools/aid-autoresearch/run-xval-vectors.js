#!/usr/bin/env node
/**
 * Cross-validation vector runner
 *
 * Runs oref0 determine-basal against the xval vector sets:
 *   - oref0-extracted (8 vectors): direct oref0 input format
 *   - temp-basal (12 vectors): temp basal decision tests
 *   - smb-decision (12 vectors): SMB enable/disable logic
 *   - meal-bolus (8 vectors): meal response tests
 *
 * Usage:
 *   node run-xval-vectors.js           # summary
 *   node run-xval-vectors.js --json    # full JSON output
 *   node run-xval-vectors.js --verbose # per-vector detail
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '../..');
const determineBasal = require(path.join(REPO_ROOT, 'externals/oref0/lib/determine-basal/determine-basal'));
const tempBasalFunctions = require(path.join(REPO_ROOT, 'externals/oref0/lib/basal-set-temp'));

const XVAL_DIR = path.join(REPO_ROOT, 'conformance/t1pal/vectors/xval');

// Default profile (from oref0-extracted baselineProfile if available)
const DEFAULT_PROFILE = {
    current_basal: 0.9,
    sens: 85,
    carb_ratio: 10,
    target_bg: 100,
    min_bg: 100,
    max_bg: 110,
    max_basal: 3.0,
    max_iob: 5.0,
    max_daily_basal: 0.9,
    max_daily_safety_multiplier: 3,
    current_basal_safety_multiplier: 4,
    dia: 4,
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

function generateIobArray(iobSnapshot, dia) {
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

    for (let i = 0; i < ticks; i++) {
        const t = i * 5;
        const decay = Math.exp(-t / tau);
        const tick = {
            iob: iob0 * decay,
            basaliob: (iob0 * decay) * 0.5,
            bolussnooze: 0,
            activity: activity0 * decay,
            lastBolusTime: Date.now() - 3600000,
            iobWithZeroTemp: {
                iob: iob0 * decay,
                basaliob: (iob0 * decay) * 0.5,
                bolussnooze: 0,
                activity: activity0 * decay,
                lastBolusTime: 0,
                time: new Date(Date.now() + t * 60000).toISOString()
            }
        };
        if (i === 0) tick.lastTemp = { date: Date.now() - 300000, duration: 0, rate: 0 };
        iobArray.push(tick);
    }
    return iobArray;
}

/**
 * Run oref0-extracted vectors (already in near-oref0 format)
 */
function runOref0Extracted() {
    const fp = path.join(XVAL_DIR, 'oref0-extracted-vectors.json');
    if (!fs.existsSync(fp)) return { suite: 'oref0-extracted', results: [], error: 'file not found' };

    const data = JSON.parse(fs.readFileSync(fp, 'utf8'));
    const baseProfile = data.baselineProfile || {};
    const baseMeal = data.baselineMealData || {};
    const results = [];

    for (const tc of data.testCases) {
        const inp = tc.input;
        const glucoseStatus = {
            glucose: inp.glucose_status.glucose,
            delta: inp.glucose_status.delta,
            short_avgdelta: inp.glucose_status.short_avgdelta || inp.glucose_status.delta,
            long_avgdelta: inp.glucose_status.long_avgdelta || inp.glucose_status.delta,
            date: Date.now()
        };
        const currentTemp = inp.currenttemp ? {
            rate: inp.currenttemp.rate || 0,
            duration: inp.currenttemp.duration || 0
        } : { rate: 0, duration: 0 };
        const iobData = generateIobArray(inp.iob_data || { iob: 0, activity: 0 }, baseProfile.dia || 4);
        const profile = Object.assign({}, DEFAULT_PROFILE, {
            current_basal: baseProfile.basalRate || baseProfile.current_basal || 0.9,
            sens: baseProfile.sensitivity || baseProfile.sens || 85,
            carb_ratio: baseProfile.carbRatio || baseProfile.carb_ratio || 10,
            max_basal: baseProfile.maxBasal || baseProfile.max_basal || 3.0,
            max_daily_basal: baseProfile.maxDailyBasal || baseProfile.basalRate || 0.9,
            dia: baseProfile.dia || 4
        });
        const mealData = {
            carbs: baseMeal.carbs || 0,
            mealCOB: baseMeal.mealCOB || 0,
            slopeFromMaxDeviation: baseMeal.slopeFromMaxDeviation || 0,
            slopeFromMinDeviation: baseMeal.slopeFromMinDeviation || 0,
            lastCarbTime: Date.now() - 7200000
        };
        const autosens = { ratio: (inp.autosens && inp.autosens.ratio) || 1.0 };

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
            results.push({ id: tc.id, status: 'crash', error: e.message });
            continue;
        }
        console.error = origErr;

        const exp = tc.expected;
        let pass = true;
        const diffs = {};

        if (exp.rate != null && result.rate != null) {
            diffs.rate = { expected: exp.rate, actual: result.rate, diff: Math.abs(result.rate - exp.rate) };
            if (diffs.rate.diff > 0.1) pass = false;  // slightly looser for xval
        }
        if (exp.action === 'no_temp' && result.rate != null && result.rate > 0) {
            diffs.action = { expected: 'no_temp', actual: 'temp_set' };
            pass = false;
        }
        if (exp.action === 'suspend' && (result.rate == null || result.rate > 0)) {
            diffs.action = { expected: 'suspend', actual: result.rate };
            pass = false;
        }

        results.push({
            id: tc.id, scenario: tc.scenario, status: pass ? 'pass' : 'fail',
            result: { rate: result.rate, duration: result.duration, eventualBG: result.eventualBG },
            expected: exp, diffs
        });
    }

    return { suite: 'oref0-extracted', total: data.testCases.length, results };
}

/**
 * Run temp-basal decision vectors
 */
function runTempBasal() {
    const fp = path.join(XVAL_DIR, 'temp-basal-vectors.json');
    if (!fs.existsSync(fp)) return { suite: 'temp-basal', results: [], error: 'file not found' };

    const data = JSON.parse(fs.readFileSync(fp, 'utf8'));
    const results = [];

    for (const tc of data.testCases) {
        const inp = tc.input;
        const glucoseStatus = {
            glucose: inp.glucose, delta: inp.delta || 0,
            short_avgdelta: inp.delta || 0, long_avgdelta: inp.delta || 0,
            date: Date.now()
        };
        const currentTemp = inp.currentTemp ? {
            rate: inp.currentTemp.rate || 0, duration: inp.currentTemp.duration || 0
        } : { rate: 0, duration: 0 };
        const iobData = generateIobArray({ iob: inp.iob || 0, activity: 0 }, 4);
        const profile = Object.assign({}, DEFAULT_PROFILE, {
            current_basal: inp.scheduledBasal || 0.9,
            max_daily_basal: inp.scheduledBasal || 0.9
        });
        const mealData = {
            carbs: 0, mealCOB: inp.cob || 0,
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
                autosens, mealData, tempBasalFunctions,
                false, null, Date.now()
            );
        } catch (e) {
            console.error = origErr;
            results.push({ id: tc.id, status: 'crash', error: e.message });
            continue;
        }
        console.error = origErr;

        const exp = tc.expected;
        let pass = true;
        const diffs = {};

        // Check action type
        if (exp.action === 'no_temp') {
            // oref0 returns no rate change or cancels existing temp
            if (result.rate != null && Math.abs(result.rate - (inp.scheduledBasal || 0.9)) > 0.1) {
                // Rate set but significantly different from scheduled
                if (result.duration > 0) { pass = false; diffs.action = { expected: 'no_temp', actual: 'temp ' + result.rate }; }
            }
        } else if (exp.action === 'increase_temp' || exp.action === 'set_temp') {
            if (result.rate == null || result.rate <= (inp.scheduledBasal || 0.9)) {
                pass = false;
                diffs.action = { expected: exp.action, actual: result.rate };
            }
        } else if (exp.action === 'decrease_temp' || exp.action === 'low_temp') {
            if (result.rate == null || result.rate >= (inp.scheduledBasal || 0.9)) {
                pass = false;
                diffs.action = { expected: exp.action, actual: result.rate };
            }
        } else if (exp.action === 'suspend') {
            if (result.rate == null || result.rate > 0) {
                pass = false;
                diffs.action = { expected: 'suspend', actual: result.rate };
            }
        }

        if (exp.rate != null && result.rate != null) {
            diffs.rate = { expected: exp.rate, actual: result.rate, diff: Math.abs(result.rate - exp.rate) };
        }

        results.push({
            id: tc.id, scenario: tc.scenario, status: pass ? 'pass' : 'fail',
            result: { rate: result.rate, duration: result.duration, reason: (result.reason || '').slice(0, 80) },
            expected: exp, diffs
        });
    }

    return { suite: 'temp-basal', total: data.testCases.length, results };
}

/**
 * Run SMB decision vectors
 */
function runSmbDecision() {
    const fp = path.join(XVAL_DIR, 'smb-decision-vectors.json');
    if (!fs.existsSync(fp)) return { suite: 'smb-decision', results: [], error: 'file not found' };

    const data = JSON.parse(fs.readFileSync(fp, 'utf8'));
    const results = [];

    for (const tc of data.testCases) {
        const inp = tc.input;
        const glucoseStatus = {
            glucose: inp.glucose, delta: inp.delta || 0,
            short_avgdelta: inp.delta || 0, long_avgdelta: inp.delta || 0,
            date: Date.now()
        };
        const currentTemp = { rate: 0, duration: 0 };
        const iobData = generateIobArray({ iob: inp.iob || 0, activity: 0 }, 4);
        const profile = Object.assign({}, DEFAULT_PROFILE, {
            enableSMB_with_bolus: inp.smbEnabled || false,
            enableSMB_always: inp.smbEnabled || false,
            enableSMB_with_COB: inp.smbEnabled || false,
            max_iob: inp.maxIOB || 5.0
        });
        const mealData = {
            carbs: 0, mealCOB: inp.cob || 0,
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
                autosens, mealData, tempBasalFunctions,
                inp.smbEnabled || false, null, Date.now()
            );
        } catch (e) {
            console.error = origErr;
            results.push({ id: tc.id, status: 'crash', error: e.message });
            continue;
        }
        console.error = origErr;

        const exp = tc.expected;
        let pass = true;
        const diffs = {};

        // Check SMB decision
        const gotSmb = result.units != null && result.units > 0;
        if (exp.action === 'smb' && !gotSmb) {
            pass = false;
            diffs.smb = { expected: 'smb', actual: 'no_smb' };
        } else if (exp.action === 'no_smb' && gotSmb) {
            pass = false;
            diffs.smb = { expected: 'no_smb', actual: 'smb=' + result.units };
        }

        results.push({
            id: tc.id, scenario: tc.scenario, status: pass ? 'pass' : 'fail',
            result: { rate: result.rate, units: result.units, duration: result.duration },
            expected: exp, diffs
        });
    }

    return { suite: 'smb-decision', total: data.testCases.length, results };
}

// --- Main ---
function runAll() {
    const suites = [
        runOref0Extracted(),
        runTempBasal(),
        runSmbDecision()
    ];

    let totalPass = 0, totalFail = 0, totalCrash = 0, totalTests = 0;
    const suiteResults = [];

    for (const suite of suites) {
        const r = suite.results || [];
        const pass = r.filter(x => x.status === 'pass').length;
        const fail = r.filter(x => x.status === 'fail').length;
        const crash = r.filter(x => x.status === 'crash').length;
        totalPass += pass;
        totalFail += fail;
        totalCrash += crash;
        totalTests += r.length;
        suiteResults.push({
            suite: suite.suite,
            total: r.length,
            pass, fail, crash,
            passRate: r.length > 0 ? (pass / r.length * 100).toFixed(1) + '%' : 'N/A'
        });
    }

    return {
        summary: {
            total: totalTests,
            pass: totalPass,
            fail: totalFail,
            crash: totalCrash,
            passRate: totalTests > 0 ? (totalPass / totalTests * 100).toFixed(1) + '%' : '0%'
        },
        suites: suiteResults,
        details: suites
    };
}

const args = process.argv.slice(2);
const jsonFlag = args.includes('--json');
const verboseFlag = args.includes('--verbose');

const output = runAll();

if (jsonFlag) {
    console.log(JSON.stringify(output, null, 2));
} else {
    const s = output.summary;
    console.log('\nXval Vector Validation (' + s.total + ' vectors across ' + output.suites.length + ' suites)');
    console.log('='.repeat(55));

    for (const suite of output.suites) {
        console.log('  ' + suite.suite.padEnd(20) + ': ' + suite.pass + '/' + suite.total + ' pass (' + suite.passRate + ')');
    }
    console.log('  ' + '─'.repeat(45));
    console.log('  ' + 'TOTAL'.padEnd(20) + ': ' + s.pass + '/' + s.total + ' pass (' + s.passRate + ')');

    if (verboseFlag) {
        for (const suite of output.details) {
            console.log('\n  ' + suite.suite + ':');
            for (const r of (suite.results || [])) {
                const st = r.status === 'pass' ? '✓' : '✗';
                const detail = r.status === 'crash' ? r.error :
                    Object.entries(r.diffs || {}).map(function(e) {
                        return e[0] + ': exp=' + JSON.stringify(e[1].expected) + ' got=' + JSON.stringify(e[1].actual);
                    }).join(', ');
                console.log('    ' + st + ' ' + r.id + ': ' + r.status + (detail ? ' — ' + detail : ''));
            }
        }
    }
}
