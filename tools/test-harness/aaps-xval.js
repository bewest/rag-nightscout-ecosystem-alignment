#!/usr/bin/env node
'use strict';

/**
 * aaps-xval.js — Cross-validate oref0-js vs aaps-js on all TV-* vectors.
 *
 * Runs both adapters on each vector and compares eventualBG, rate, predictions.
 * Usage: node tools/test-harness/aaps-xval.js [--limit N]
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const vectorDir = path.resolve(__dirname, '../../conformance/t1pal/vectors/oref0-endtoend');
const oref0Adapter = path.resolve(__dirname, 'adapters/oref0-js/index.js');
const aapsAdapter = path.resolve(__dirname, 'adapters/aaps-js/index.js');

const limit = process.argv.includes('--limit') ?
  parseInt(process.argv[process.argv.indexOf('--limit') + 1]) : Infinity;

// Gather vectors
const vectors = fs.readdirSync(vectorDir)
  .filter(f => f.startsWith('TV-') && f.endsWith('.json'))
  .sort()
  .slice(0, limit);

function buildAdapterInput(v) {
  return {
    mode: 'execute',
    input: {
      clock: v.input.clock,
      glucoseStatus: {
        glucose: v.input.glucoseStatus.glucose,
        delta: v.input.glucoseStatus.delta,
        shortAvgDelta: v.input.glucoseStatus.short_avgdelta,
        longAvgDelta: v.input.glucoseStatus.long_avgdelta,
        timestamp: v.input.glucoseStatus.date,
        noise: v.input.glucoseStatus.noise || 0,
      },
      iob: {
        iob: v.input.iob.iob,
        basalIob: v.input.iob.basaliob,
        activity: v.input.iob.activity,
        iobWithZeroTemp: v.input.iob.iobWithZeroTemp,
      },
      profile: {
        basalRate: v.input.profile.current_basal,
        sensitivity: v.input.profile.sens,
        carbRatio: v.input.profile.carb_ratio,
        targetLow: v.input.profile.min_bg,
        targetHigh: v.input.profile.max_bg,
        maxBasal: v.input.profile.max_basal,
        maxIob: v.input.profile.max_iob,
        maxDailyBasal: v.input.profile.max_daily_basal,
        dia: v.input.profile.dia || 5,
        enableSMB: v.input.profile.enableSMB_always || false,
        enableUAM: v.input.profile.enableUAM || false,
        maxSMBBasalMinutes: v.input.profile.maxSMBBasalMinutes || 30,
        maxUAMSMBBasalMinutes: v.input.profile.maxUAMSMBBasalMinutes || 30,
        smbInterval: v.input.profile.SMBInterval || 3,
        bolusIncrement: v.input.profile.bolus_increment || 0.1,
        min5mCarbImpact: v.input.profile.min_5m_carbimpact || 8,
      },
      mealData: v.input.meal_data || {},
      currentTemp: {
        rate: (v.input.currenttemp || {}).rate || 0,
        duration: (v.input.currenttemp || {}).duration || 0,
      },
      autosensData: { ratio: (v.input.autosens_data || {}).ratio || 1.0 },
      microBolusAllowed: v.input.microBolusAllowed || false,
      flatBGsDetected: false,
    },
  };
}

function runAdapter(adapterPath, inputJson) {
  try {
    const result = execSync(
      `node ${adapterPath}`,
      { input: JSON.stringify(inputJson), timeout: 10000, stdio: ['pipe', 'pipe', 'pipe'] }
    );
    return JSON.parse(result.toString());
  } catch (err) {
    return { error: err.message };
  }
}

function curveMae(arr1, arr2) {
  if (!arr1 || !arr2 || arr1.length === 0 || arr2.length === 0) return null;
  const len = Math.min(arr1.length, arr2.length);
  let sum = 0;
  for (let i = 0; i < len; i++) sum += Math.abs(arr1[i] - arr2[i]);
  return sum / len;
}

// Run comparison
const results = [];
let eventualBGMatch = 0, eventualBGTotal = 0;
let rateExact = 0, rateClose = 0, rateTotal = 0;
let iobMaeSum = 0, iobMaeCount = 0;
let ztMaeSum = 0, ztMaeCount = 0;
let roundingDiffs = 0;

process.stderr.write(`Running ${vectors.length} vectors through oref0-js and aaps-js...\n`);

for (const file of vectors) {
  const v = JSON.parse(fs.readFileSync(path.join(vectorDir, file), 'utf8'));
  const input = buildAdapterInput(v);

  const oref0Out = runAdapter(oref0Adapter, input);
  const aapsOut = runAdapter(aapsAdapter, input);

  if (oref0Out.error || aapsOut.error) {
    results.push({ vector: file, error: oref0Out.error || aapsOut.error });
    continue;
  }

  const oEB = oref0Out.predictions.eventualBG;
  const aEB = aapsOut.predictions.eventualBG;
  const oRate = oref0Out.decision.rate;
  const aRate = aapsOut.decision.rate;

  // EventualBG comparison
  if (oEB != null && aEB != null) {
    eventualBGTotal++;
    if (oEB === aEB) eventualBGMatch++;
  }

  // Rate comparison
  if (oRate != null && aRate != null) {
    rateTotal++;
    if (oRate === aRate) rateExact++;
    else if (Math.abs(oRate - aRate) <= 0.5) rateClose++;

    // Detect pure rounding differences
    if (oRate !== aRate && Math.abs(oRate - aRate) < 0.05) roundingDiffs++;
  }

  // Prediction curves
  const iobMae = curveMae(oref0Out.predictions.iob, aapsOut.predictions.iob);
  if (iobMae != null) { iobMaeSum += iobMae; iobMaeCount++; }
  const ztMae = curveMae(oref0Out.predictions.zt, aapsOut.predictions.zt);
  if (ztMae != null) { ztMaeSum += ztMae; ztMaeCount++; }

  results.push({
    vector: file.replace(/TV-(\d+).*/, 'TV-$1'),
    eventualBG: { oref0: oEB, aaps: aEB, match: oEB === aEB },
    rate: { oref0: oRate, aaps: aRate, delta: oRate != null && aRate != null ? Math.round((aRate - oRate) * 100) / 100 : null },
    iobMae: iobMae != null ? Math.round(iobMae * 100) / 100 : null,
    ztMae: ztMae != null ? Math.round(ztMae * 100) / 100 : null,
  });
}

// Print summary
console.log('\n╔══════════════════════════════════════════════════════════╗');
console.log('║   oref0-JS vs AAPS-JS Cross-Validation Summary          ║');
console.log('╠══════════════════════════════════════════════════════════╣');
console.log(`║ EventualBG exact:  ${eventualBGMatch}/${eventualBGTotal} (${eventualBGTotal ? Math.round(100*eventualBGMatch/eventualBGTotal) : 0}%)`);
console.log(`║ Rate exact:        ${rateExact}/${rateTotal} (${rateTotal ? Math.round(100*rateExact/rateTotal) : 0}%)`);
console.log(`║ Rate ±0.5:         ${rateExact + rateClose}/${rateTotal} (${rateTotal ? Math.round(100*(rateExact+rateClose)/rateTotal) : 0}%)`);
console.log(`║ Rounding-only Δ:   ${roundingDiffs}/${rateTotal} (round_basal no-op effect)`);
console.log(`║ IOB curve MAE:     ${iobMaeCount ? (iobMaeSum/iobMaeCount).toFixed(3) : 'N/A'}`);
console.log(`║ ZT curve MAE:      ${ztMaeCount ? (ztMaeSum/ztMaeCount).toFixed(3) : 'N/A'}`);
console.log('╚══════════════════════════════════════════════════════════╝');

// Print rate mismatches
const mismatches = results.filter(r => r.rate && r.rate.oref0 != null && r.rate.aaps != null && r.rate.oref0 !== r.rate.aaps);
if (mismatches.length > 0) {
  console.log(`\nRate mismatches (${mismatches.length}):`);
  for (const m of mismatches.slice(0, 20)) {
    const delta = m.rate.delta > 0 ? `+${m.rate.delta}` : m.rate.delta;
    console.log(`  ${m.vector}: oref0=${m.rate.oref0} aaps=${m.rate.aaps} (Δ${delta})`);
  }
}

// Print eventualBG mismatches
const ebMismatches = results.filter(r => r.eventualBG && !r.eventualBG.match && r.eventualBG.oref0 != null);
if (ebMismatches.length > 0) {
  console.log(`\nEventualBG mismatches (${ebMismatches.length}):`);
  for (const m of ebMismatches.slice(0, 10)) {
    console.log(`  ${m.vector}: oref0=${m.eventualBG.oref0} aaps=${m.eventualBG.aaps}`);
  }
}

// Save full results
fs.writeFileSync('/tmp/aaps-xval-results.json', JSON.stringify(results, null, 2));
process.stderr.write(`\nFull results saved to /tmp/aaps-xval-results.json\n`);
