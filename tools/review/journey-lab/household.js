'use strict';
// household.js — a deterministic synthetic day-to-day for one looping person, used to backfill
// journey-lab sites (J2 sync, J6 reports). Contributor-facing; synthetic only; not medical advice.
//
// Phase 1 model (a toy, by design): glucose is base + dawn rise + meal bumps - insulin action + noise,
// with meals, boluses, temp basals, SMBs, and the occasional override / temp target / site change.
// It is shaped to make every report page non-empty and plausible-looking, not to be physiologically
// right. Phase 2 replaces `plan()` with the UVA/Padova + sensor model (cgmsim-lib LT1) driven by
// behaviour distributions fitted locally from the parquet stores (never committed).
//
// plan({ start, end, controller, seed, tz, therapy }) -> {
//   readings:[{t,sgv,direction}], meals:[{t,carbs,bolus}], smbs:[{t,units}], temps:[{t,rate,durationMin}],
//   status:[{t,bg,iob,cob,eventual,pred:[..],rate,durationMin,smb,reservoir,battery}],
//   overrides:[{t,name,durationMin}], targets:[{t,target,durationMin,name}], siteChanges:[t], sensorStarts:[t] }

const MIN = 60 * 1000;
const STEP = 5 * MIN;

function rng (seed) { // mulberry32
  let a = 0;
  for (const ch of String(seed)) a = (a * 31 + ch.charCodeAt(0)) >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

function localHour (t, tz) {
  const p = new Intl.DateTimeFormat('en-GB', { timeZone: tz, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(t));
  return Number(p.find(x => x.type === 'hour').value) + Number(p.find(x => x.type === 'minute').value) / 60;
}
function localMidnight (t, tz) { return Math.floor((t - localHour(t, tz) * 60 * MIN) / MIN) * MIN; }

const DEFAULT_THERAPY = { basal: 0.8, isf: 50, cr: 10, target: 105, dia: 6 };

// exponential-ish insulin activity; fraction of a dose still on board after m minutes
const iobLeft = (m, dia) => m <= 0 ? 1 : m >= dia * 60 ? 0 : Math.pow(1 - m / (dia * 60), 1.8);
// carbs absorbed linearly over 3 h, with a 15 min delay
const cobLeft = (m) => m <= 15 ? 1 : m >= 195 ? 0 : 1 - (m - 15) / 180;

function plan ({ start, end, controller = 'loop', seed = 'lab', tz = 'UTC', therapy = {} }) {
  const th = Object.assign({}, DEFAULT_THERAPY, therapy);
  const r = rng(seed + ':' + controller);
  start = Math.ceil(start / STEP) * STEP;
  const out = { readings: [], meals: [], smbs: [], temps: [], status: [], overrides: [], targets: [], siteChanges: [], sensorStarts: [] };

  // meals and events, day by day in local time
  for (let d = localMidnight(start, tz); d < end; d += 24 * 60 * MIN) {
    for (const [h, lo, hi] of [[7.2, 25, 55], [12.4, 35, 75], [18.8, 40, 90]]) {
      if (r() < 0.07) continue; // a skipped meal now and then
      const t = Math.round((d + (h + (r() - 0.5) * 1.5) * 60 * MIN) / STEP) * STEP;
      const carbs = Math.round(lo + r() * (hi - lo));
      const guess = carbs * (0.6 + r() * 0.8); // carb counting is rarely exact
      if (t >= start && t < end) out.meals.push({ t, carbs, bolus: Math.round(guess / th.cr * 20) / 20 });
    }
    if (r() < 0.45) { // afternoon snack, sometimes not bolused
      const t = Math.round((d + (15.5 + r() * 1.5) * 60 * MIN) / STEP) * STEP;
      const carbs = Math.round(10 + r() * 15);
      if (t >= start && t < end) out.meals.push({ t, carbs, bolus: r() < 0.5 ? 0 : Math.round(carbs / th.cr * 20) / 20 });
    }
    if (r() < 0.25) { // exercise in the evening: an override / temp target an hour before
      const t = Math.round((d + (17 + r()) * 60 * MIN) / STEP) * STEP;
      if (t >= start && t < end) {
        if (controller === 'loop') out.overrides.push({ t, name: 'Running', durationMin: 90 });
        else if (controller === 'trio') out.overrides.push({ t, name: 'Exercise', durationMin: 90 });
        out.targets.push({ t, target: 150, durationMin: 90, name: 'Activity' });
      }
    }
  }
  for (let t = start + Math.floor(r() * 3) * 24 * 60 * MIN + 10 * 60 * MIN; t < end; t += 3 * 24 * 60 * MIN) out.siteChanges.push(t);
  for (let t = start + Math.floor(r() * 10) * 24 * 60 * MIN + 9 * 60 * MIN; t < end; t += 10 * 24 * 60 * MIN) out.sensorStarts.push(t);

  // integrate glucose on a 5-minute grid
  let bg = th.target + 10; let lastTempAt = -Infinity;
  const doses = []; // {t, units}
  for (const m of out.meals) if (m.bolus > 0) doses.push({ t: m.t, units: m.bolus });
  let reservoir = 180; let battery = 100;
  const sensDay = {}; // day-to-day sensitivity: some days insulin works harder than others
  for (let t = start; t < end; t += STEP) {
    const h = localHour(t, tz);
    const dayKey = localMidnight(t, tz); if (!(dayKey in sensDay)) sensDay[dayKey] = 0.7 + r() * 0.75;
    const sf = sensDay[dayKey];
    const dawn = 22 * Math.exp(-Math.pow((h - 6.5) / 1.4, 2));
    // carb and insulin effect for this 5-minute step
    let carbFx = 0; let cob = 0;
    for (const m of out.meals) {
      const a = (t - m.t) / MIN; if (a < 0 || a > 200) continue;
      carbFx += m.carbs * (th.isf / th.cr) * (cobLeft(a) - cobLeft(a + 5)); cob += m.carbs * cobLeft(a);
    }
    let insFx = 0; let iob = 0;
    for (const d of doses) {
      const a = (t - d.t) / MIN; if (a < 0 || a > th.dia * 60) continue;
      insFx += d.units * th.isf * sf * (iobLeft(a, th.dia) - iobLeft(a + 5, th.dia)); iob += d.units * iobLeft(a, th.dia);
    }
    const drift = (th.target + dawn - bg) * 0.02;
    bg = bg + carbFx - insFx + drift + (r() - 0.5) * 4;
    bg = Math.max(42, Math.min(380, bg));
    const sgv = Math.round(bg);
    const prev = out.readings.length ? out.readings[out.readings.length - 1].sgv : sgv;
    const delta = sgv - prev;
    const direction = delta > 10 ? 'DoubleUp' : delta > 6 ? 'SingleUp' : delta > 2 ? 'FortyFiveUp' : delta < -10 ? 'DoubleDown' : delta < -6 ? 'SingleDown' : delta < -2 ? 'FortyFiveDown' : 'Flat';
    if (r() > 0.012) out.readings.push({ t, sgv, direction }); // a few gaps, like a real sensor

    // the controller's response
    const eventual = Math.round(sgv + (cob / th.cr) * th.isf * 0.5 - iob * th.isf);
    let rate = th.basal; let smb = 0;
    if (eventual > th.target + 30) rate = Math.min(th.basal * 3, th.basal + (eventual - th.target) / th.isf);
    if (eventual < th.target - 20) rate = 0;
    rate = Math.round(rate * 20) / 20;
    if (controller !== 'loop' && eventual > th.target + 40 && iob < 3 && r() < 0.5) {
      smb = Math.round(Math.min(1, (eventual - th.target) / th.isf / 2) * 10) / 10;
      if (smb >= 0.1) { out.smbs.push({ t, units: smb }); doses.push({ t, units: smb }); } else smb = 0;
    }
    if (rate !== th.basal && t - lastTempAt >= 30 * MIN) {
      out.temps.push({ t, rate, durationMin: 30 }); lastTempAt = t;
      doses.push({ t, units: (rate - th.basal) * 0.5 });
    }
    reservoir = Math.max(5, reservoir - th.basal / 12 - smb);
    if (out.siteChanges.some(s => s <= t && t - s < STEP)) reservoir = 180;
    battery = Math.max(20, battery - 0.03);
    const pred = []; for (let i = 0; i < 12; i++) pred.push(Math.round(sgv + (eventual - sgv) * (1 - Math.exp(-i / 6))));
    // Loop and Trio report every 5 min; AAPS more often (cadence noted from the corpus: ~2 min), kept at 5 here
    out.status.push({ t, bg: sgv, iob: Math.round(iob * 100) / 100, cob: Math.round(cob), eventual, pred, rate, durationMin: 30, smb, reservoir: Math.round(reservoir * 10) / 10, battery: Math.round(battery) });
  }
  return out;
}

module.exports = { plan, localHour, localMidnight, DEFAULT_THERAPY, MIN, STEP };

if (require.main === module) {
  const now = Date.now();
  const p = plan({ start: now - 14 * 24 * 60 * MIN, end: now, controller: process.argv[2] || 'trio', tz: process.env.LAB_TZ || 'UTC' });
  const sg = p.readings.map(x => x.sgv); const inR = sg.filter(v => v >= 70 && v <= 180).length / sg.length;
  console.log({ readings: sg.length, meals: p.meals.length, smbs: p.smbs.length, temps: p.temps.length, overrides: p.overrides.length,
    targets: p.targets.length, sites: p.siteChanges.length, sensors: p.sensorStarts.length,
    mean: Math.round(sg.reduce((a, b) => a + b, 0) / sg.length), min: Math.min(...sg), max: Math.max(...sg), tir: Math.round(inR * 100) + '%' });
}
