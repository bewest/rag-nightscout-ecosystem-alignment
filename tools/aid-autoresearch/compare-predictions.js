#!/usr/bin/env node
/**
 * Multi-algorithm prediction comparison using captured predBGs
 *
 * Uses the REAL predicted glucose trajectories from originalOutput.predBGs
 * in TV-* vectors (captured from actual phone runs) as ground truth,
 * then compares against our synthetic IOB reconstruction.
 *
 * This measures how well our IOB array synthesis reproduces the actual
 * oref0 predictions that the real algorithm generated.
 *
 * Also extracts prediction trajectories in GluPredKit-compatible format
 * for multi-algorithm benchmarking.
 *
 * Usage:
 *   node compare-predictions.js                # summary
 *   node compare-predictions.js --json         # full JSON
 *   node compare-predictions.js --export-csv   # GluPredKit CSV
 *
 * Trace: ALG-VERIFY-005, REQ-060
 */

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '../..');
const determineBasal = require(path.join(REPO_ROOT, 'externals/oref0/lib/determine-basal/determine-basal'));
const tempBasalFunctions = require(path.join(REPO_ROOT, 'externals/oref0/lib/basal-set-temp'));

const VECTORS_DIR = path.join(REPO_ROOT, 'conformance/t1pal/vectors/oref0-endtoend');

// Re-use IOB array generation from run-oref0-endtoend.js
function generateIobArray(iobSnapshot, dia) {
    const diaMins = (dia || 4) * 60;
    const ticks = 48;
    const iobArray = [];
    const iob0 = iobSnapshot.iob || 0;
    const activity0 = iobSnapshot.activity || 0;
    const basaliob0 = iobSnapshot.basaliob || iobSnapshot.basalIob || 0;
    const iobZT0 = iobSnapshot.iobWithZeroTemp || {
        iob: iob0, basaliob: basaliob0, bolussnooze: 0,
        activity: activity0, lastBolusTime: 0
    };
    let tau = diaMins / 1.85;
    if (Math.abs(iob0) > 0.01 && Math.abs(activity0) > 0.0001) {
        const r = Math.abs(activity0 / iob0);
        if (r > 0.0001 && r < 0.1) tau = Math.min(diaMins, Math.max(30, 1 / r));
    }
    const basalFrac = (iob0 !== 0) ? (basaliob0 / iob0) : 0.5;

    for (let i = 0; i < ticks; i++) {
        const t = i * 5;
        const decay = Math.exp(-t / tau);
        const iobVal = iob0 * decay;
        const actVal = activity0 * Math.max(0, decay);
        const ztIob = (iobZT0.iob || iob0) * decay;
        const ztAct = (iobZT0.activity || activity0) * Math.max(0, decay);

        const tick = {
            iob: iobVal, basaliob: iobVal * basalFrac,
            bolussnooze: 0, activity: actVal,
            lastBolusTime: iobSnapshot.lastBolusTime || (Date.now() - 3600000),
            iobWithZeroTemp: {
                iob: ztIob, basaliob: ztIob * basalFrac,
                bolussnooze: 0, activity: ztAct,
                lastBolusTime: 0, time: new Date(Date.now() + t * 60000).toISOString()
            }
        };
        if (i === 0) tick.lastTemp = { date: Date.now() - 300000, duration: 0 };
        iobArray.push(tick);
    }
    return iobArray;
}

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
    const iobSnapshot = {
        iob: input.iob.iob, basaliob: input.iob.basalIob || 0,
        bolussnooze: input.iob.bolusSnooze || 0,
        activity: input.iob.activity || 0,
        lastBolusTime: Date.now() - 60 * 60 * 1000,
        iobWithZeroTemp: input.iob.iobWithZeroTemp || undefined
    };
    const iobData = generateIobArray(iobSnapshot, dia);
    const p = input.profile;
    const profile = {
        current_basal: p.basalRate || p.currentBasal || 1.0,
        sens: p.sensitivity || 50, carb_ratio: p.carbRatio || 10,
        target_bg: ((p.targetLow || 100) + (p.targetHigh || 110)) / 2,
        min_bg: p.targetLow || 100, max_bg: p.targetHigh || 110,
        max_basal: p.maxBasal || 3.0, max_iob: p.maxIob || 5.0,
        max_daily_safety_multiplier: 3, current_basal_safety_multiplier: 4,
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
    const currentTemp = input.currentTemp ? {
        rate: input.currentTemp.rate || 0, duration: input.currentTemp.duration || 0
    } : { rate: 0, duration: 0 };
    const md = input.mealData || {};
    const mealData = {
        carbs: md.carbs || 0, mealCOB: md.mealCOB || md.cob || 0,
        slopeFromMaxDeviation: md.slopeFromMaxDeviation || 0,
        slopeFromMinDeviation: md.slopeFromMinDeviation || 0,
        lastCarbTime: md.lastCarbTime || (Date.now() - 2 * 60 * 60 * 1000)
    };
    const autosens = { ratio: (input.autosensData || input.autosens || {}).ratio || 1.0 };
    return { glucoseStatus, iobData, profile, currentTemp, mealData, autosens };
}

/**
 * Compare captured predBGs (ground truth) with our synthetic reconstruction.
 */
function compareVector(vector) {
    const id = vector.metadata?.id || 'unknown';
    const captured = vector.originalOutput?.predBGs?.IOB;

    if (!captured || captured.length === 0) {
        return { id, status: 'skip', reason: 'no captured predBGs.IOB' };
    }

    // Run oref0 with synthetic IOB array
    const origErr = console.error;
    console.error = () => {};
    let result;
    try {
        const { glucoseStatus, iobData, profile, currentTemp, mealData, autosens } =
            vectorToOref0Inputs(vector);
        result = determineBasal(
            glucoseStatus, currentTemp, iobData, profile,
            autosens, mealData, tempBasalFunctions,
            false, null, Date.now()
        );
    } catch (e) {
        console.error = origErr;
        return { id, status: 'error', error: e.message };
    }
    console.error = origErr;

    const reconstructed = result?.predBGs?.IOB || [];
    if (reconstructed.length === 0) {
        return {
            id, status: 'no-pred',
            captured: { length: captured.length, first: captured[0], last: captured[captured.length - 1] },
            decision: { rate: result?.rate, eventualBG: result?.eventualBG }
        };
    }

    // Compare trajectories
    const minLen = Math.min(captured.length, reconstructed.length);
    let sumAbsDiff = 0, sumSqDiff = 0, maxDiff = 0;
    const diffs = [];

    for (let i = 0; i < minLen; i++) {
        const diff = reconstructed[i] - captured[i];
        sumAbsDiff += Math.abs(diff);
        sumSqDiff += diff * diff;
        maxDiff = Math.max(maxDiff, Math.abs(diff));
        diffs.push(diff);
    }

    const mae = sumAbsDiff / minLen;
    const rmse = Math.sqrt(sumSqDiff / minLen);

    // Direction agreement at each step
    let dirMatch = 0;
    for (let i = 1; i < minLen; i++) {
        const capDir = Math.sign(captured[i] - captured[i - 1]);
        const recDir = Math.sign(reconstructed[i] - reconstructed[i - 1]);
        if (capDir === recDir) dirMatch++;
    }
    const dirAgreement = minLen > 1 ? dirMatch / (minLen - 1) : 0;

    return {
        id,
        status: mae <= 15 ? 'good' : mae <= 30 ? 'fair' : 'poor',
        metrics: {
            mae: Math.round(mae * 10) / 10,
            rmse: Math.round(rmse * 10) / 10,
            maxDiff: Math.round(maxDiff * 10) / 10,
            dirAgreement: Math.round(dirAgreement * 1000) / 1000,
            overlap: minLen,
            capturedLen: captured.length,
            reconstructedLen: reconstructed.length
        },
        trajectory: {
            captured: captured.slice(0, 12),
            reconstructed: reconstructed.slice(0, 12)
        }
    };
}

// --- Main ---
const args = process.argv.slice(2);
const jsonFlag = args.includes('--json');
const exportCsv = args.includes('--export-csv');

const files = fs.readdirSync(VECTORS_DIR).filter(f => f.endsWith('.json')).sort();
const results = [];

let good = 0, fair = 0, poor = 0, skip = 0, noPred = 0, errors = 0;
let totalMae = 0, totalRmse = 0, totalDir = 0, metricsCount = 0;

for (const file of files) {
    const vector = JSON.parse(fs.readFileSync(path.join(VECTORS_DIR, file), 'utf8'));
    const r = compareVector(vector);
    results.push(r);

    if (r.status === 'good') { good++; totalMae += r.metrics.mae; totalRmse += r.metrics.rmse; totalDir += r.metrics.dirAgreement; metricsCount++; }
    else if (r.status === 'fair') { fair++; totalMae += r.metrics.mae; totalRmse += r.metrics.rmse; totalDir += r.metrics.dirAgreement; metricsCount++; }
    else if (r.status === 'poor') { poor++; totalMae += r.metrics.mae; totalRmse += r.metrics.rmse; totalDir += r.metrics.dirAgreement; metricsCount++; }
    else if (r.status === 'skip') skip++;
    else if (r.status === 'no-pred') noPred++;
    else errors++;
}

const summary = {
    total: files.length,
    good, fair, poor, skip, noPred, errors,
    avgMae: metricsCount > 0 ? Math.round(totalMae / metricsCount * 10) / 10 : null,
    avgRmse: metricsCount > 0 ? Math.round(totalRmse / metricsCount * 10) / 10 : null,
    avgDirAgreement: metricsCount > 0 ? Math.round(totalDir / metricsCount * 1000) / 1000 : null,
    qualityScore: metricsCount > 0 ?
        Math.round((good / metricsCount * 1.0 + fair / metricsCount * 0.5) * 1000) / 1000 : 0
};

if (exportCsv) {
    // Export captured predictions in GluPredKit-compatible CSV format
    const csvLines = ['vector_id,step,captured_bg,reconstructed_bg,glucose,category'];
    for (const r of results) {
        if (!r.trajectory) continue;
        const vector = JSON.parse(fs.readFileSync(path.join(VECTORS_DIR,
            files.find(f => f.includes(r.id)) || ''), 'utf8'));
        const bg = vector.input?.glucoseStatus?.glucose || 0;
        const cat = vector.metadata?.category || 'unknown';

        for (let i = 0; i < Math.min(r.trajectory.captured.length, 12); i++) {
            csvLines.push(`${r.id},${(i+1)*5},${r.trajectory.captured[i]},${r.trajectory.reconstructed[i]},${bg},${cat}`);
        }
    }
    const csvPath = path.join(__dirname, 'prediction-comparison.csv');
    fs.writeFileSync(csvPath, csvLines.join('\n'));
    console.error(`Exported ${csvLines.length - 1} rows to ${csvPath}`);
}

if (jsonFlag) {
    console.log(JSON.stringify({ summary, results }, null, 2));
} else {
    console.log(`\nPrediction Trajectory Comparison: Captured vs Reconstructed`);
    console.log('='.repeat(60));
    console.log(`  Total vectors:    ${summary.total}`);
    console.log(`  Good (MAE≤15):    ${summary.good}`);
    console.log(`  Fair (MAE≤30):    ${summary.fair}`);
    console.log(`  Poor (MAE>30):    ${summary.poor}`);
    console.log(`  Skipped:          ${summary.skip + summary.noPred + summary.errors}`);
    console.log(`\n  Avg MAE:          ${summary.avgMae} mg/dL`);
    console.log(`  Avg RMSE:         ${summary.avgRmse} mg/dL`);
    console.log(`  Avg Dir Agreement: ${(summary.avgDirAgreement * 100).toFixed(1)}%`);
    console.log(`  Quality Score:    ${summary.qualityScore}`);

    // Show worst cases
    const ranked = results
        .filter(r => r.metrics)
        .sort((a, b) => b.metrics.mae - a.metrics.mae);
    if (ranked.length > 0) {
        console.log(`\n  Worst 5 (highest MAE):`);
        for (const r of ranked.slice(0, 5)) {
            console.log(`    ${r.id}: MAE=${r.metrics.mae} RMSE=${r.metrics.rmse} dir=${(r.metrics.dirAgreement*100).toFixed(0)}%`);
        }
        console.log(`\n  Best 5 (lowest MAE):`);
        for (const r of ranked.slice(-5).reverse()) {
            console.log(`    ${r.id}: MAE=${r.metrics.mae} RMSE=${r.metrics.rmse} dir=${(r.metrics.dirAgreement*100).toFixed(0)}%`);
        }
    }
}
