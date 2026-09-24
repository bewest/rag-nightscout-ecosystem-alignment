#!/usr/bin/env node
'use strict';
// Manual-check lab seeder. Synthetic data only; every value is a literal here.
// Usage: node seed.js <url> <scenario> [trigger]
// Reads the raw API secret from $LAB_SECRET_FILE and sends only its SHA-1.
const fs = require('fs');
const crypto = require('crypto');
const [URL_BASE, SCENARIO, ACTION = 'seed'] = process.argv.slice(2);
const SHA1 = crypto.createHash('sha1').update(fs.readFileSync(process.env.LAB_SECRET_FILE, 'utf8').trim()).digest('hex');
const MIN = 60 * 1000;
const DEVICE = 'synthetic://lab/manual';
const BY = 'lab-manual';

async function api (method, p, body) {
  const r = await fetch(URL_BASE + p, { method, headers: { 'api-secret': SHA1, 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await r.text();
  if (r.status >= 300) throw new Error(`${method} ${p} -> HTTP ${r.status} ${text.slice(0, 200)}`);
  try { return JSON.parse(text); } catch (e) { return text; }
}

const sched = v => [{ time: '00:00', timeAsSeconds: 0, value: String(v) }];
function profile (now) {
  const start = now - 2 * 24 * 60 * MIN;
  return [{ defaultProfile: 'Default', mills: String(start), startDate: new Date(start).toISOString(), units: 'mg/dl',
    enteredBy: BY, store: { Default: { dia: '5', carbs_hr: '20', delay: '20', timezone: 'UTC', units: 'mg/dl',
      basal: sched(0.8), sens: sched(50), carbratio: sched(10), target_low: sched(100), target_high: sched(120) } } }];
}
function readings (now, n, fn) {
  const out = [];
  for (let i = n; i >= 1; i--) {
    const t = now - i * 5 * MIN;
    out.push({ type: 'sgv', sgv: fn(n - i), direction: 'Flat', date: t, dateString: new Date(t).toISOString(), device: DEVICE });
  }
  return out;
}
async function subject (name, roles) {
  await api('POST', '/api/v2/authorization/subjects', { name, roles });
  const s = (await api('GET', '/api/v2/authorization/subjects')).find(x => x.name === name);
  return s.accessToken;
}
async function role (name, permissions) { await api('POST', '/api/v2/authorization/roles', { name, permissions }); }
const tx = (now, offsetMin, fields) => Object.assign({ created_at: new Date(now + offsetMin * MIN).toISOString(), enteredBy: BY }, fields);
const say = (k, v) => console.log(`  ${k.padEnd(14)} ${v}`);

const S = {
  // 1. RT-D3 drag. Same shapes as rt-d3-drag-browser.js, plus combos in the middle for the split drops.
  async drag (now) {
    await api('POST', '/api/v1/profile', profile(now));
    await api('POST', '/api/v1/entries', readings(now, 72, i => 110 + (i % 6) * 2));
    await api('POST', '/api/v1/treatments', [
      tx(now, -150, { eventType: 'Meal Bolus', carbs: 25, insulin: 2.5, notes: 'lab A split: top=move carbs, bottom=move insulin' }),
      tx(now, -110, { eventType: 'Meal Bolus', carbs: 20, insulin: 1, notes: 'lab B drag then CANCEL' }),
      tx(now, -80, { eventType: 'Meal Bolus', carbs: 30, insulin: 2, notes: 'lab C move left, accept' }),
      tx(now, -55, { eventType: 'Correction Bolus', insulin: 1.5, notes: 'lab D drag past LEFT edge' }),
      tx(now, -35, { eventType: 'Carb Correction', carbs: 15, notes: 'lab E move right, accept' }),
      tx(now, -10, { eventType: 'Carb Correction', carbs: 12, notes: 'lab F drag past RIGHT edge' }),
    ]);
    await role('lab-treatment-editor', ['*:*:read', 'api:treatments:*']);
    say('editor token', await subject('lab-editor', ['lab-treatment-editor']));
  },
  // 2. alarms on a login-required site
  async alarm (now) {
    await api('POST', '/api/v1/profile', profile(now));
    await api('POST', '/api/v1/entries', readings(now, 36, () => 105));
    say('readable token', await subject('lab-reader', ['readable']));
    say('status-only', await subject('lab-status-only', ['status-only']));
  },
  async 'alarm:warn' (now) { await api('POST', '/api/v1/entries', readings(now + 5 * MIN, 1, () => 70)); say('posted', '70 mg/dL (below BG_TARGET_BOTTOM=80, warning low)'); },
  async 'alarm:urgent' (now) { await api('POST', '/api/v1/entries', readings(now + 5 * MIN, 1, () => 45)); say('posted', '45 mg/dL (below BG_LOW=55, urgent low)'); },
  async 'alarm:normal' (now) { await api('POST', '/api/v1/entries', readings(now + 5 * MIN, 1, () => 105)); say('posted', '105 mg/dL (back in range)'); },
  // 3. BF-90: profile only, no glucose reading; the alarm comes from pump reservoir alerts
  async noreading (now) {
    await api('POST', '/api/v1/profile', profile(now));
  },
  async 'noreading:warn' (now) { await pump(now, 8); say('posted', 'pump reservoir 8 U (warning)'); },
  async 'noreading:urgent' (now) { await pump(now, 3); say('posted', 'pump reservoir 3 U (urgent)'); },
  async 'noreading:readings' (now) { await api('POST', '/api/v1/entries', readings(now, 12, () => 105)); say('posted', '12 readings at 105 (the control: now alarms should sound)'); },
  // 4. BF-69 quick picks. Plain foods interleaved, one hidden pick, one hide-after-use pick.
  async quickpick (now) {
    await api('POST', '/api/v1/profile', profile(now));
    await api('POST', '/api/v1/entries', readings(now, 12, () => 115));
    const item = (name, carbs, portions) => ({ name, carbs, portion: 1, portions, unit: 'g' });
    for (const f of [
      { type: 'food', name: 'lab-apple (plain food)', carbs: 12, portion: 1, unit: 'g', category: 'lab', subcategory: 'fruit' },
      { type: 'quickpick', name: 'lab-lunch', carbs: 70, position: 2, hidden: false, hideafteruse: false, foods: [item('rice', 35, 2)] },
      { type: 'quickpick', name: 'lab-hidden', carbs: 99, position: 0, hidden: true, hideafteruse: false, foods: [item('cake', 99, 1)] },
      { type: 'food', name: 'lab-bread (plain food)', carbs: 15, portion: 1, unit: 'g', category: 'lab', subcategory: 'grain' },
      { type: 'quickpick', name: 'lab-breakfast', carbs: 45, position: 1, hidden: false, hideafteruse: false, foods: [item('oats', 45, 1)] },
      { type: 'quickpick', name: 'lab-snack (hides after use)', carbs: 20, position: 3, hidden: false, hideafteruse: true, foods: [item('bar', 10, 2)] },
    ]) await api('POST', '/api/v1/food', f);
    await role('lab-wizard-role', ['*:*:read', 'api:treatments:create', 'api:food:*']);
    say('wizard token', await subject('lab-wizard', ['lab-wizard-role']));
  },
  async 'quickpick:late' () {
    await api('POST', '/api/v1/food', { type: 'quickpick', name: 'lab-late', carbs: 33, position: 4, hidden: false, hideafteruse: false,
      foods: [{ name: 'soup', carbs: 33, portion: 1, portions: 1, unit: 'g' }] });
    say('posted', 'quick pick lab-late (33 g)');
  },
  // 5a. empty site: no profile, no data (#8732 redirect-once, profile editor defaults warning)
  async empty () {},
  // 5b/6. an ordinary looping site: pills, sensor age with no sensor start, COB from device status
  async cob (now) {
    await api('POST', '/api/v1/profile', profile(now));
    await api('POST', '/api/v1/entries', readings(now, 72, i => 120 + Math.round(25 * Math.sin(i / 10))));
    await api('POST', '/api/v1/treatments', [
      tx(now, -60, { eventType: 'Meal Bolus', carbs: 40, insulin: 3, notes: 'lab carbs for the treatment-derived COB' }),
      tx(now, -3 * 24 * 60, { eventType: 'Site Change', notes: 'lab cannula age' }),
    ]);
    await S['cob:openaps'](now);
  },
  // AndroidAPS shape: suggested carries COB with no timestamp, enacted has neither (the 34e9b2da case)
  async 'cob:openaps' (now) {
    await api('POST', '/api/v1/devicestatus', [{ device: 'openaps://lab-phone', created_at: new Date(now).toISOString(),
      openaps: { suggested: { bg: 120, COB: 22, IOB: 1.1, reason: 'lab: synthetic' }, enacted: { bg: 120, rate: 0.8, duration: 30 },
        iob: { iob: 1.1, basaliob: 0.1, activity: 0.01, time: new Date(now).toISOString() } } }]);
    say('posted', 'devicestatus, AndroidAPS shape, COB 22 g in openaps.suggested (no timestamp)');
  },
  async 'cob:loop' (now) {
    await api('POST', '/api/v1/devicestatus', [{ device: 'loop://lab-iphone', created_at: new Date(now).toISOString(),
      loop: { cob: { cob: 18, timestamp: new Date(now).toISOString() }, iob: { iob: 0.9, timestamp: new Date(now).toISOString() },
        timestamp: new Date(now).toISOString(), name: 'Loop' } }]);
    say('posted', 'devicestatus, Loop shape, COB 18 g in loop.cob');
  },
};
async function pump (now, reservoir) {
  await api('POST', '/api/v1/devicestatus', [{ device: DEVICE, created_at: new Date(now).toISOString(),
    pump: { clock: new Date(now).toISOString(), reservoir, status: { status: 'normal', bolusing: false, suspended: false } } }]);
}

(async () => {
  const key = ACTION === 'seed' ? SCENARIO : `${SCENARIO}:${ACTION}`;
  if (!S[key]) { console.error(`no such step: ${key}\nsteps: ${Object.keys(S).join(' ')}`); process.exit(2); }
  await S[key](Date.now());
})().catch(e => { console.error(e.message); process.exit(1); });
