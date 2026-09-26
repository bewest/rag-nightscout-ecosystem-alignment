#!/usr/bin/env node
'use strict';
// journey.js — journey-lab step runner. Each step sends exactly what a real client sends (the
// request descriptors in clients.js, each cited to the client's source), prints one line per
// request, and keeps the ids it needs in $LAB_STATE/<name>.json. Contributor-facing; synthetic
// data only; not medical advice.
//
//   node journey.js <instance> <step> [args...]      (normally via lab.sh fire)
//   node journey.js <instance> help
//
// Env (set by lab.sh): LAB_URL, LAB_KIND (loop|trio|aaps), LAB_VARIANT (aaps: v3-34|v1-34|v3-40),
// LAB_UNITS (mg/dl|mmol), LAB_STATE, LAB_SECRET_FILE, LAB_TZ, LAB_MODULES (the tree's node_modules).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const C = require('./clients');
const H = require('./household');

const [NAME, STEP = 'help', ...ARGS] = process.argv.slice(2);
const URL_BASE = process.env.LAB_URL;
const KIND = process.env.LAB_KIND;
const VARIANT = process.env.LAB_VARIANT || 'v3-34';
const MMOL = /mmol/.test(process.env.LAB_UNITS || '');
const TZ = process.env.LAB_TZ || 'UTC';
const STATE_FILE = path.join(process.env.LAB_STATE || '.', NAME + '.json');
const SHA1 = crypto.createHash('sha1').update(fs.readFileSync(process.env.LAB_SECRET_FILE, 'utf8').trim()).digest('hex');
const MIN = 60 * 1000;

// ---------- state ----------
const st = fs.existsSync(STATE_FILE) ? JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')) : { n: 0, tokens: {}, open: {}, ids: {} };
const save = () => fs.writeFileSync(STATE_FILE, JSON.stringify(st, null, 1));
const nextId = (tag) => { st.n += 1; return `${NAME}:${tag}:${st.n}`; };

// ---------- therapy fixtures (test values, not guidance) ----------
const TH = MMOL
  ? { units: 'mmol', basal: [['00:00', 0.8], ['06:00', 0.95], ['22:00', 0.75]], sens: [['00:00', 2.8]], carbratio: [['00:00', 10], ['11:00', 12]], target: [['00:00', 5.5, 6.1]] }
  : { units: 'mg/dl', basal: [['00:00', 0.8], ['06:00', 0.95], ['22:00', 0.75]], sens: [['00:00', 50]], carbratio: [['00:00', 10], ['11:00', 12]], target: [['00:00', 100, 110]] };
const LOOP_PRESETS = [
  { name: 'Running', symbol: '🏃', durationMin: 90, targetRange: [150, 160], scale: 0.7 },
  { name: 'Sick day', symbol: '🤒', durationMin: 0, targetRange: [110, 120], scale: 1.2 },
];
const tzOffsetHours = () => { const d = new Date(); const l = new Date(d.toLocaleString('en-US', { timeZone: TZ })); const u = new Date(d.toLocaleString('en-US', { timeZone: 'UTC' })); return Math.round((l - u) / 3600000); };
const deviceToken = () => crypto.createHash('sha256').update('lab-apns:' + NAME).digest('hex'); // fake, per site

// ---------- transport ----------
async function jwt (name = 'app') {
  const tok = st.tokens[name];
  if (!tok) throw new Error(`no ${name} token yet: run the ${name === 'app' ? 'connect' : 'share'} step first`);
  st.jwts = st.jwts || {};
  const c = st.jwts[name]; if (c && c.exp * 1000 > Date.now() + 60000) return c.token;
  const r = await fetch(`${URL_BASE}/api/v2/authorization/request/${tok}`);
  if (r.status !== 200) throw new Error(`JWT exchange -> HTTP ${r.status}`);
  const j = await r.json(); st.jwts[name] = { token: j.token, exp: j.exp }; save(); return j.token;
}
let sock = null;
async function socket () {
  if (sock) return sock;
  const io = require(path.join(process.env.LAB_MODULES, 'socket.io-client'));
  sock = io(URL_BASE, { transports: ['websocket'], forceNew: true });
  await new Promise((resolve, reject) => { sock.on('connect', resolve); sock.on('connect_error', reject); });
  const auth = await new Promise(res => sock.emit('authorize', { client: 'android', secret: SHA1, history: 1 }, res));
  if (!auth || !auth.write) console.log('  ! socket authorize without write permission:', JSON.stringify(auth));
  return sock;
}
async function send (d, tokenName) {
  if (Array.isArray(d)) { const out = []; for (const x of d) out.push(await send(x, tokenName)); return out; }
  let status; let body;
  if (d.auth === 'socket') {
    const s = await socket();
    body = await new Promise(res => { const t = setTimeout(() => res({ timeout: true }), 10000); s.emit(d.socket.event, d.socket.data, (ack) => { clearTimeout(t); res(ack); }); });
    status = body && body.timeout ? 'no-ack' : 'ack';
  } else {
    const headers = { 'content-type': d.form ? 'application/x-www-form-urlencoded' : 'application/json' };
    let p = d.path;
    const tok = () => { const t = st.tokens[tokenName || 'follower']; if (!t) throw new Error(`no ${tokenName || 'follower'} token: run the share step first`); return t; };
    if (d.auth === 'secret') headers['api-secret'] = SHA1;
    if (d.auth === 'token-path') p = p.replace('<accessToken>', tok());
    if (d.auth === 'token-header') headers['api-secret'] = tok();
    if (d.auth === 'jwt') headers.authorization = 'Bearer ' + await jwt(tokenName || 'app');
    if (d.auth === 'token-query') p += (p.includes('?') ? '&' : '?') + 'token=' + tok();
    const payload = d.body === undefined ? undefined : d.form ? new URLSearchParams(Object.entries(d.body).map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)])).toString() : JSON.stringify(d.body);
    const r = await fetch(URL_BASE + p, { method: d.method, headers, body: payload });
    status = r.status; const text = await r.text(); try { body = JSON.parse(text); } catch (e) { body = text; }
  }
  const ok = status === 'ack' || (typeof status === 'number' && status < 300);
  const size = Array.isArray(body) ? ` [${body.length}]` : '';
  console.log(`  ${ok ? '✓' : '✗'} ${String(status).padEnd(6)} ${d.method || d.socket.event} ${(d.path || d.socket.collection).slice(0, 90)}${size}  — ${d.label}`);
  if (!ok) console.log('      ' + JSON.stringify(body).slice(0, 300));
  if (process.env.LAB_VERBOSE) { console.log('      body:', JSON.stringify(d.body || (d.socket && d.socket.data)).slice(0, 600)); console.log('      source:', d.source.join(' ; ')); }
  return { status, body, ok };
}
const say = (k, v) => console.log(`  ${k.padEnd(16)} ${v}`);
// the id the server gave a new record: v3 answers {identifier}, v1 answers [doc], the v1 socket acks [doc]
const createdId = (r) => { const b = r && r.body; if (!b) return {}; const x = Array.isArray(b) ? b[0] : (b.result || b); return { identifier: x && x.identifier, nsId: x && x._id }; };
const get = async (p) => (await send({ label: 'read', method: 'GET', path: p, auth: 'secret', source: ['lab'] })).body;
const verdict = (v, empty) => {
  if (empty) { console.log('  → the site has no profile yet: nothing to import, the app goes on to its own setup'); return; } console.log(`  → ${v.ok !== undefined ? (v.ok ? 'YES' : 'NO') : (v.accept ? 'ACCEPT' : 'IGNORE')}: ${v.reason}`); console.log(`    (emulated from ${v.source.join(' ; ')}; a real app is the proof — see the real-app track)`); };

// ---------- bulk backfill (household.js → client shapes) ----------
function batchV1 (descs) { // Loop and Trio post arrays to v1; merge consecutive POSTs to the same path, 500 at a time
  const out = [];
  descs = descs.flatMap(d => (Array.isArray(d.body) && d.body.length > 500)
    ? Array.from({ length: Math.ceil(d.body.length / 500) }, (_, i) => Object.assign({}, d, { body: d.body.slice(i * 500, i * 500 + 500) }))
    : [d]);
  for (const d of descs) {
    const last = out[out.length - 1];
    if (last && d.method === 'POST' && last.method === 'POST' && d.auth !== 'socket' && d.auth === last.auth && last.path === d.path && !d.path.startsWith('/api/v3') && Array.isArray(last.body) && last.body.length < 500) {
      last.body.push(...(Array.isArray(d.body) ? d.body : [d.body])); last.label = `backfill: ${last.body.length} records in one POST`;
    } else out.push(Object.assign({}, d, { body: Array.isArray(d.body) ? [...d.body] : (d.method === 'POST' && !d.path.startsWith('/api/v3') && d.auth !== 'socket' ? [d.body] : d.body), kind: d.label }));
  }
  return out;
}
async function pool (descs, n = 8) {
  let i = 0; let fails = 0; const quiet = descs.length > 40;
  const log = console.log; if (quiet) console.log = () => {};
  await Promise.all(Array.from({ length: n }, async () => { while (i < descs.length) { const d = descs[i++]; const r = await send(d); if (!r.ok) fails++; } }));
  console.log = log; if (quiet) say('sent', `${descs.length} requests, ${fails} failed`);
  return fails;
}
// Where the phone's glucose comes from: its own CGM (default), or Nightscout (CGM-first sites, and after
// remote-cgm / ns-cgm / ns-bg). When it is Nightscout, the phone uploads no readings of its own.
const cgmFromNightscout = () => process.env.LAB_CGM === 'connect' || st.cgmSource === 'nightscout';
function householdDescs (hours, endAt = Date.now()) {
  const p = H.plan({ start: endAt - hours * 60 * MIN, end: endAt, controller: KIND, seed: NAME, tz: TZ });
  if (cgmFromNightscout()) p.readings = [];
  const d = [];
  const iso = t => new Date(t).toISOString();
  if (KIND === 'loop') {
    if (p.readings.length) d.push(C.loop.entries({ readings: p.readings }));
    for (const m of p.meals) { d.push(C.loop.carbs({ now: m.t, grams: m.carbs, absorptionHours: 3 })); if (m.bolus) d.push(C.loop.bolus({ now: m.t, syncIdentifier: nextId('bolus'), units: m.bolus, automatic: false })); }
    for (const x of p.temps) d.push(C.loop.tempBasal({ now: x.t, syncIdentifier: nextId('temp'), rate: x.rate, durationMin: x.durationMin }));
    for (const o of p.overrides) d.push(C.loop.overrideStart({ now: o.t, uuid: C.uuid(nextId('ovr'), { upper: true }), reason: '🏃 ' + o.name, durationMin: o.durationMin, correctionRange: [150, 160], insulinNeedsScaleFactor: 0.7 }));
    for (const s of p.status) d.push(C.loop.devicestatus({ now: s.t, iob: s.iob, cob: s.cob, predicted: s.pred, enacted: { rate: s.rate, durationMin: 30, bolus: 0 }, override: null, reservoir: s.reservoir, battery: s.battery, deviceName: 'lab-iPhone' }));
  } else if (KIND === 'trio') {
    if (p.readings.length) d.push(C.trio.entries({ readings: p.readings }));
    for (const m of p.meals) { d.push(C.trio.carbs({ now: m.t, id: C.uuid(nextId('carb'), { upper: true }), grams: m.carbs })); if (m.bolus) d.push(C.trio.bolus({ now: m.t, id: C.uuid(nextId('bolus'), { upper: true }), units: m.bolus, smb: false })); }
    for (const x of p.smbs) d.push(C.trio.bolus({ now: x.t, id: C.uuid(nextId('smb'), { upper: true }), units: x.units, smb: true }));
    for (const x of p.temps) d.push(C.trio.tempBasal({ now: x.t, id: C.uuid(nextId('temp'), { upper: true }), rate: x.rate, durationMin: x.durationMin }));
    for (const o of p.overrides) d.push(C.trio.overrideStart({ now: o.t, name: o.name, durationMin: o.durationMin }));
    for (const s of p.status) d.push(C.trio.devicestatus({ now: s.t, iob: s.iob, cob: s.cob, bg: s.bg, eventualBG: s.eventual, predBGs: s.pred, rate: s.rate, durationMin: 30, smb: s.smb, reservoir: s.reservoir, battery: s.battery }));
  } else {
    const v = VARIANT;
    if (p.readings.length) d.push(C.aaps.entries({ variant: v, readings: p.readings }));
    for (const m of p.meals) { d.push(C.aaps.carbs({ variant: v, now: m.t, identifier: C.uuid(nextId('carb')), grams: m.carbs })); if (m.bolus) d.push(C.aaps.bolus({ variant: v, now: m.t, identifier: C.uuid(nextId('bolus')), units: m.bolus, smb: false })); }
    for (const x of p.smbs) d.push(C.aaps.bolus({ variant: v, now: x.t, identifier: C.uuid(nextId('smb')), units: x.units, smb: true }));
    for (const x of p.temps) d.push(C.aaps.tempBasal({ variant: v, now: x.t, identifier: C.uuid(nextId('temp')), rate: x.rate, durationMin: x.durationMin }));
    for (const x of p.targets) d.push(C.aaps.tempTargetStart({ variant: v, now: x.t, identifier: C.uuid(nextId('tt')), low: x.target, high: x.target, durationMin: x.durationMin, reason: x.name }));
    for (const s of p.status) d.push(C.aaps.devicestatus({ variant: v, now: s.t, iob: s.iob, cob: s.cob, bg: s.bg, eventualBG: s.eventual, predBGs: s.pred, rate: s.rate, durationMin: 30, smb: s.smb, reservoir: s.reservoir, battery: s.battery }));
  }
  // the person's own careportal entries: site changes and sensor starts (entered in Nightscout, v1, API secret)
  for (const t of p.siteChanges) d.push(C.careportal.treatment({ now: t, eventType: 'Site Change', fields: { notes: 'lab: synthetic' } }));
  for (const t of p.sensorStarts) d.push(C.careportal.treatment({ now: t, eventType: 'Sensor Start', fields: { notes: 'lab: synthetic' } }));
  save();
  return { descs: d.flat(), plan: p };
}
async function backfill (hours) {
  const { descs, plan } = householdDescs(hours);
  say('household', `${hours} h: ${plan.readings.length} readings, ${plan.meals.length} meals, ${plan.temps.length} temp basals, ${plan.smbs.length} SMBs, ${plan.status.length} device statuses`);
  const v1 = batchV1(descs.filter(x => x.auth !== 'socket' && !x.path.startsWith('/api/v3')));
  const rest = descs.filter(x => x.auth === 'socket' || x.path.startsWith('/api/v3'));
  let fails = 0; const log = console.log; const quiet = v1.length > 6;
  if (quiet) console.log = (...x) => { if (String(x[0]).includes('✗') || String(x[0]).startsWith('      ')) log(...x); };
  for (const b of v1) if (!(await send(b)).ok) fails++;
  console.log = log; if (quiet) say('sent', `${v1.length} batched requests, ${fails} failed`);
  if (rest.length) fails += await pool(rest, rest[0].auth === 'socket' ? 1 : 8);
  if (fails) throw new Error(`backfill: ${fails} request(s) failed`);
}

// ---------- read-back helpers used by status and the checks ----------
async function status () {
  const profiles = await get('/api/v1/profile.json?count=5');
  say('profiles', `${Array.isArray(profiles) ? profiles.length : '?'} shown (newest first)`);
  for (const p of (Array.isArray(profiles) ? profiles : [])) {
    const flags = [p.loopSettings ? 'loopSettings' : '', p.deviceToken ? 'top-level deviceToken' : '', p.app ? 'app=' + p.app : '', p.enteredBy ? 'by=' + p.enteredBy : ''].filter(Boolean).join(' ');
    say('', `${p.startDate}  default=${p.defaultProfile}  store=[${Object.keys(p.store || {}).join(', ')}]  units=${p.units || '-'}  ${flags}`);
  }
  const since = new Date(Date.now() - 48 * 60 * MIN).toISOString();
  const tx = await get(`/api/v1/treatments.json?find[created_at][$gte]=${since}&count=5000`);
  const by = {}; for (const t of (Array.isArray(tx) ? tx : [])) { const k = `${t.eventType} (${t.enteredBy || t.app || '-'})`; by[k] = (by[k] || 0) + 1; }
  say('treatments 48h', Object.keys(by).length ? '' : 'none');
  for (const k of Object.keys(by).sort()) say('', `${String(by[k]).padStart(5)}  ${k}`);
  const ds = await get('/api/v1/devicestatus.json?count=1');
  if (Array.isArray(ds) && ds[0]) say('devicestatus', `${ds[0].device || '-'}  keys=[${Object.keys(ds[0]).filter(k => !k.startsWith('_')).join(', ')}]  at ${ds[0].created_at || ds[0].mills || '?'}`);
  else say('devicestatus', 'none');
  const e = await get('/api/v1/entries.json?count=1');
  say('newest reading', Array.isArray(e) && e[0] ? `${e[0].sgv} mg/dL at ${new Date(e[0].date).toISOString()}${e[0].dateString ? '' : ' (no dateString: as the app sent it)'}` : 'none');
  const log = path.join(process.env.LAB_STATE, 'apns.jsonl');
  if (KIND === 'loop' && fs.existsSync(log)) {
    const mine = fs.readFileSync(log, 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse).filter(x => x.token === deviceToken());
    say('APNs pushes', `${mine.length} to this site's phone`);
    for (const x of mine.slice(-3)) say('', `${x.t}  ${JSON.stringify(x.payload).slice(0, 160)}`);
  }
}

// ---------- steps ----------
const now = () => Date.now();
const lastOpen = (k) => { const o = st.open[k]; if (!o) throw new Error(`nothing open for ${k}: start one first`); return o; };
const num = (v, d) => (v === undefined || v === '' ? d : Number(v));
const durArg = (v, d) => (v === 'indef' || v === 'indefinite' ? null : num(v, d));

// what the Profile Editor holds for a new site after the person fills it in (or leaves the placeholders:
// lib/client-core/profile-editor/default-profile.js), in the editor's own record shape
function editorRecord (placeholders) {
  const sch = (rows) => rows.map(([time, value]) => ({ time, value }));
  const store = placeholders
    ? { dia: 3, carbratio: [{ time: '00:00', value: 30 }], carbs_hr: 20, delay: 20, sens: [{ time: '00:00', value: 100 }], timezone: 'UTC', basal: [{ time: '00:00', value: 0.1 }], target_low: [{ time: '00:00', value: 0 }], target_high: [{ time: '00:00', value: 0 }] }
    : { dia: 5, carbratio: sch(TH.carbratio), carbs_hr: 20, delay: 20, sens: sch(TH.sens), timezone: TZ, basal: sch(TH.basal), target_low: TH.target.map(([time, lo]) => ({ time, value: lo })), target_high: TH.target.map(([time, , hi]) => ({ time, value: hi })) };
  store.units = MMOL ? 'mmol' : 'mg/dl';
  return { defaultProfile: 'Default', store: { Default: store } };
}

const arr = (b) => Array.isArray(b) ? b : (b && Array.isArray(b.result) ? b.result : []);
function showImport (v) {
  console.log(`  → ${v.ok ? 'IMPORT OFFERED' : 'NO IMPORT'}: ${v.reason}`);
  if (v.userMessage) say('app says', v.userMessage);
  if (v.imported) for (const [k, x] of Object.entries(v.imported)) say('  imported', `${k}: ${JSON.stringify(x).slice(0, 110)}`);
  for (const x of (v.notImported || [])) say('  not imported', x);
  for (const x of (v.losses || [])) say('  changed/lost', x);
  console.log(`    (emulated from ${v.source.slice(0, 4).join(' ; ')}${v.source.length > 4 ? ' …' : ''}; a real app is the proof)`);
}

const COMMON = {
  'cgm-status': ['where the site\'s readings came from: count by sender, newest, and any two readings at the same moment', async () => {
    const e = await get(`/api/v1/entries.json?find[date][$gte]=${now() - 48 * 60 * MIN}&count=2000`);
    const by = {}; const at = {};
    for (const x of (Array.isArray(e) ? e : [])) { by[x.device || '-'] = (by[x.device || '-'] || 0) + 1; at[x.date] = (at[x.date] || 0) + 1; }
    say('readings 48 h', Array.isArray(e) ? e.length : '?');
    for (const k of Object.keys(by)) say('', `${String(by[k]).padStart(5)}  from ${k}`);
    if (Array.isArray(e) && e[0]) say('newest', `${e[0].sgv} mg/dL ${e[0].direction || ''} at ${new Date(e[0].date).toISOString()} from ${e[0].device || '-'}${e[0].filtered !== undefined ? ' (has filtered/unfiltered)' : ''}`);
    const dup = Object.values(at).filter(n => n > 1).length; say('same moment', dup ? `${dup} timestamps have more than one reading` : 'none');
    say('phone CGM', cgmFromNightscout() ? 'Nightscout (the phone uploads no readings of its own)' : 'its own CGM');
  }],
  'cgm-pause': ['(CGM-first sites) the sensor stops reaching Dexcom Share: no new readings until cgm-resume', async () => {
    fs.writeFileSync(path.join(process.env.LAB_STATE, 'share-pause-' + NAME.replace(/-1508$/, '')), new Date().toISOString()); say('Share', 'paused: new readings withheld');
  }],
  'cgm-resume': ['(CGM-first sites) readings reach Share again; the connector backfills the gap at its next poll', async () => {
    fs.rmSync(path.join(process.env.LAB_STATE, 'share-pause-' + NAME.replace(/-1508$/, '')), { force: true }); say('Share', 'resumed');
  }],
  'editor-save': ['(automation of J1.B2: what the Profile Editor PUTs when the person saves a filled-in profile; do it by hand for the real check)', async () => {
    await send(C.careportal.profileEditorSave({ record: editorRecord(false), now: now(), units: MMOL ? 'mmol' : 'mg/dl' }));
  }],
  'editor-save-placeholders': ['(automation of the J1.B1 safety check: the same save with the placeholders left unchanged)', async () => {
    await send(C.careportal.profileEditorSave({ record: editorRecord(true), now: now(), units: MMOL ? 'mmol' : 'mg/dl' }));
  }],
  status: ['what the site holds now (profiles, 48 h of treatments by type and sender, newest device status, APNs pushes)', status],
  backfill: ['<hours=6>  what the app would have uploaded over the last N hours (readings, meals, doses, device status)', a => backfill(num(a[0], 6))],
  tick: ['one 5-minute cycle of the app now: a reading, device status, maybe a temp basal', async () => {
    const { descs } = householdDescs(0.09); for (const b of batchV1(descs)) await send(b);
  }],
  share: ['create the sharing tokens: follower (readable), caregiver (readable + careportal), careportal-only, status-only', async () => {
    const mk = async (name, roles) => {
      await send({ label: `subject ${name} [${roles}]`, method: 'POST', path: '/api/v2/authorization/subjects', body: { name, roles }, auth: 'secret', source: ['lib/authorization/endpoints.js (admin page Subjects)'] });
      const s = (await get('/api/v2/authorization/subjects')).find(x => x.name === name); return s.accessToken;
    };
    st.tokens.follower = await mk('lab-follower', ['readable']);
    st.tokens.caregiver = await mk('lab-caregiver', ['readable', 'careportal']);
    st.tokens.careportalOnly = await mk('lab-careportal-only', ['careportal']);
    st.tokens.statusOnly = await mk('lab-status-only', ['status-only']);
    save();
    for (const [k, v] of Object.entries(st.tokens)) if (k !== 'app') say(k, `${URL_BASE}/?token=${v}`);
  }],
  'share-check': ['what each sharing token can do: read readings, read treatments, add a Note (expected: follower reads only; caregiver reads + adds; careportal-only: BF-78)', async () => {
    const lab = ['lab: capability check'];
    for (const k of ['follower', 'caregiver', 'careportalOnly', 'statusOnly']) {
      if (!st.tokens[k]) continue;
      console.log(`  -- ${k}`);
      await send({ label: `${k}: read readings`, method: 'GET', path: '/api/v1/entries.json?count=1', auth: 'token-query', source: lab }, k);
      await send({ label: `${k}: read treatments`, method: 'GET', path: '/api/v1/treatments.json?count=1', auth: 'token-query', source: lab }, k);
      await send({ label: `${k}: add a Note (careportal)`, method: 'POST', path: '/api/v1/treatments/', body: { eventType: 'Note', notes: `lab: ${k} token`, enteredBy: k, created_at: new Date().toISOString() }, auth: 'token-query', source: lab }, k);
    }
  }],
  'follow-loopfollow': ['LoopFollow: set up with the API secret (makes its own readable subject), then poll with its token', async () => {
    const setup = await send(C.followers.loopFollowSetup());
    const s = (await get('/api/v2/authorization/subjects')).find(x => x.name === 'LoopFollow');
    if (s) { st.tokens.loopfollow = s.accessToken; save(); say('LoopFollow token', 'found (subject "LoopFollow")'); }
    await send(C.followers.loopFollowPoll({ now: now() }), 'loopfollow');
    return setup;
  }],
  'follow-nightguard': ['nightguard: follower token → JWT reads', async () => send(C.followers.nightguardPoll({ now: now() }), 'follower')],
  'follow-xdrip': ['xDrip+ follower: API-secret reads', async () => send(C.followers.xdripFollow({ now: now() }))],
  'follow-reporter': ['<days=14>  Nightscout Reporter: its per-day reads with ?token= (readable)', async a => {
    const days = num(a[0], 14); const mid = H.localMidnight(now(), TZ); const log = console.log; let bad = 0;
    for (let i = days; i >= 1; i--) {
      const rs = await send(C.followers.reporterDay({ dayStart: mid - i * 24 * 60 * MIN }), 'follower');
      bad += [].concat(rs).filter(x => !x.ok).length;
      if (i === days) { say('', '(first day shown; the rest run quietly)'); console.log = () => {}; }
    }
    console.log = log; say('reporter', `${days} days read, ${bad} failed requests`);
  }],
};

const LOOP = {
  'switch-to-trio': ['J1.G: the person moves this Loop site to Trio: Trio\'s import of Loop\'s profile, Trio\'s own profile upload, then a careportal Temporary Override (expected to fail: the newest profile has no loopSettings)', async () => {
    const r = await get('/api/v1/profile.json?count=1');
    console.log('  Trio onboarding import of the newest (Loop) profile:'); showImport(C.trio.importSummary(r));
    await send(C.trio.profileUpload({ now: now(), units: MMOL ? 'mmol' : 'mg/dl', schedules: TH, dia: 10, presets: [{ name: 'Exercise', durationMin: 60, targetRange: [140, 140], scale: 0.7 }], deviceToken: deviceToken() + '-trio', bundleIdentifier: 'org.lab.Trio', teamID: 'LABTEAM001', isAPNSProduction: false, timezone: TZ }));
    console.log('  careportal Temporary Override now:');
    await send(C.careportal.loopOverride({ reason: 'Running', reasonDisplay: 'Running', durationMin: 90 }));
  }],
  'remote-cgm': ['J1.E: Loop\'s CGM is set to "Nightscout Remote CGM": the setup check and a poll; from now on Loop uploads no readings of its own', async () => {
    const r = await send(C.loop.remoteCgmFetch({ now: now() }));
    st.cgmSource = 'nightscout'; save();
    say('readings seen', `${arr([].concat(r).pop().body).length} in the last hour (Loop polls every 10 s, fetching when its newest is over 4.5 min old)`);
    say('re-upload', 'none: Nightscout Remote CGM sets shouldSyncToRemoteService = false');
  }],
  restore: ['J1.D: new phone / reinstall: Loop onboarding offers "Settings Found" only for a Loop-made newest profile; shows what would be imported and what not; then the person reviews and saves (a new profile record)', async () => {
    const cur = await get('/api/v1/profile/current');
    const v = C.loop.importSummary(cur && typeof cur === 'object' ? cur : null); showImport(v);
    if (v.ok) await STEPS.onboard[1]([]);
  }],
  'add-later': ['J1.C: a Loop user who has looped for weeks adds the Nightscout service now (read from Loop\'s code: history is marked uploaded without being sent, and no profile goes up until a setting changes)', async () => {
    await send({ label: 'connection test (credentials entered after the service already exists)', method: 'GET', path: '/api/v1/experiments/test', auth: 'secret', source: ['NightscoutService@fe075ef NightscoutServiceKit/NightscoutService.swift:105-113'] });
    st.addedLater = now(); save();
    say('history sent', 'none: the upload that ran when the service was created had no credentials, reported success, and moved the anchors (read: NightscoutService.swift:198-201,241-244,277-280,318-321,330-333,361-364; RemoteDataServicesManager.swift:53-58,500-513)');
    say('profile sent', 'none until a therapy setting changes (settings-change) or push registration produces a new token');
    say('next', 'tick a few times: readings and doses arrive, but the site has no profile, so the page still redirects to the Profile Editor');
  }],
  connect: ['Loop settings → Services → Nightscout: the connection test, then onboarding offers "import settings" only if the newest profile is Loop-shaped', async () => {
    await send({ label: 'connection test', method: 'GET', path: '/api/v1/experiments/test', auth: 'secret', source: ['NightscoutKit NightscoutClient.swift (experiments/test)'] });
    const cur = await get('/api/v1/profile/current');
    verdict(C.loop.canImport(cur && typeof cur === 'object' ? cur : null), cur === null);
  }],
  onboard: ['Loop uploads its therapy settings after onboarding (POST /api/v1/profile, an array; loopSettings with override presets and this site\'s fake APNs token)', async () => {
    await send(C.loop.profileUpload({ now: now(), units: MMOL ? 'mmol/L' : 'mg/dL', schedules: TH, presets: LOOP_PRESETS, deviceToken: deviceToken(), bundleIdentifier: 'org.lab.Loop', isAPNSProduction: false, timezoneOffsetHours: tzOffsetHours() }));
  }],
  'settings-change': ['the person edits basal and adds a preset in Loop: a NEW profile record (Loop never updates in place)', async () => {
    const th = JSON.parse(JSON.stringify(TH)); th.basal[1][1] = 1.05;
    await send(C.loop.profileUpload({ now: now(), units: MMOL ? 'mmol/L' : 'mg/dL', schedules: th, presets: [...LOOP_PRESETS, { name: 'Movie night', symbol: '🍿', durationMin: 180, targetRange: [120, 130], scale: 0.9 }], deviceToken: deviceToken(), bundleIdentifier: 'org.lab.Loop', isAPNSProduction: false, timezoneOffsetHours: tzOffsetHours() }));
  }],
  'override-start': ['<preset=Running|Sick day|custom> <minutes|indef>  enable an override on the phone', async a => {
    const name = a[0] || 'Running'; const p = LOOP_PRESETS.find(x => x.name === name) || { name: 'Custom Override', symbol: '', durationMin: 60, targetRange: [130, 140], scale: 0.8 };
    const dur = a[1] !== undefined ? durArg(a[1], 60) : (p.durationMin || null);
    const o = { uuid: C.uuid(nextId('ovr'), { upper: true }), startedAt: now(), reason: p.symbol ? `${p.symbol} ${p.name}` : p.name, durationMin: dur, correctionRange: p.targetRange, insulinNeedsScaleFactor: p.scale };
    st.open.override = o; save();
    await send(C.loop.overrideStart(Object.assign({ now: o.startedAt }, o)));
  }],
  'override-end': ['end the running override early on the phone', async () => {
    const o = lastOpen('override'); await send(C.loop.overrideEnd(Object.assign({}, o, { endedAt: now() }))); st.open.lastOverride = o; delete st.open.override; save();
  }],
  'override-delete': ['delete the last override from Loop\'s history (DELETE /api/v1/treatments/<UPPER-UUID>)', async () => {
    const o = st.open.override || st.open.lastOverride; if (!o) throw new Error('no override to delete'); await send(C.loop.overrideDelete({ uuid: o.uuid }));
  }],
  carbs: ['<grams=30>  carbs entered on the phone', async a => {
    const r = await send(C.loop.carbs({ now: now(), grams: num(a[0], 30), absorptionHours: 3 }));
    const id = Array.isArray(r.body) && r.body[0] && r.body[0]._id; if (id) { st.ids.lastCarb = id; save(); say('_id', id); }
  }],
  'carb-edit': ['<grams=45>  edit the last carb entry on the phone (PUT with the cached _id)', async a => send(C.loop.carbEdit({ nsId: st.ids.lastCarb, now: now(), grams: num(a[0], 45), absorptionHours: 3 }))],
  'carb-delete': ['delete the last carb entry on the phone', async () => send(C.loop.carbDelete({ nsId: st.ids.lastCarb }))],
  bolus: ['<units=1.5>  a manual bolus on the phone', async a => send(C.loop.bolus({ now: now(), syncIdentifier: nextId('bolus'), units: num(a[0], 1.5), automatic: false }))],
  suspend: ['<minutes=30>  suspend the pump on the phone', async a => send(C.loop.suspend({ now: now(), syncIdentifier: nextId('susp'), durationMin: num(a[0], 30) }))],
  'caregiver-override': ['<preset=Running>  LoopCaregiver sends an override (API secret → /api/v2/notifications/loop → APNs)', async a => { await send(C.followers.loopCaregiverOverride({ now: now(), presetName: a[0] || 'Running', displayName: `🏃 ${a[0] || 'Running'}`, durationMin: 90 })); }],
  'caregiver-cancel': ['LoopCaregiver cancels the override', async () => send(C.followers.loopCaregiverCancel({ now: now() }))],
  'caregiver-carbs': ['<grams=20>  LoopCaregiver remote carbs (OTP is not checked by Nightscout, only by the phone)', async a => send(C.followers.loopCaregiverCarbs({ now: now(), grams: num(a[0], 20), absorptionH: 3, otp: '123456' }))],
  'site-override': ['<preset=Running>  (automation of the careportal form: what the web page posts for Temporary Override; do it by hand in the browser for the real check)', async a => {
    await send(C.careportal.loopOverride({ reason: a[0] || 'Running', reasonDisplay: a[0] || 'Running', durationMin: 90 }));
  }],
  apns: ['the pushes this site sent to "the phone" (the fake APNs log)', status],
};

const TRIO = {
  'ns-cgm': ['J1.E: Trio\'s CGM is "Nightscout": one fetch, then (with Upload Glucose on, the default) the re-upload of what it fetched; run it again to see the next cycle', async () => {
    const r = await send(C.trio.nsCgmFetch({ syncDate: st.trioSync || null }));
    const got = arr(r.body); st.cgmSource = 'nightscout';
    say('fetched', `${got.length} readings`);
    const d = got.length ? C.trio.reuploadFetched({ entries: got, syncDate: st.trioSync || null, existingDates: st.trioStored || [] }) : null;
    if (d && (!Array.isArray(d.body) || d.body.length)) await send(d); else say('re-upload', 'nothing new to send');
    if (got.length) { st.trioSync = new Date(Math.max(...got.map(x => x.date))).toISOString(); st.trioStored = [...new Set([...(st.trioStored || []), ...got.map(x => x.date)])].slice(-600); }
    save(); await COMMON['cgm-status'][1]([]);
  }],
  restore: ['J1.D: new phone / reinstall: Trio onboarding "Import" from the newest profile; shows what Trio would fill in and what it changes or loses', async () => {
    const r = await get('/api/v1/profile.json?count=1');
    showImport(C.trio.importSummary(r));
  }],
  'finish-onboarding': ['J1.A for Trio: onboarding completes (read from Trio\'s code: it does not upload the profile here; the first upload comes at the next cold launch or the first settings edit)', async () => {
    const r = await get('/api/v1/profile.json?count=1');
    say('site profiles', Array.isArray(r) ? `${r.length} (expected 0 until Trio relaunches or a setting is edited)` : '?');
    say('source', 'Trio@e41c9db37 Trio/Sources/Modules/Onboarding/View/OnboardingRootView.swift:812-815; TrioApp.swift:148-154,208-216; NightscoutManager.swift:869; BuildDetails.swift:102-116');
    say('next', '`onboard` = the upload at the next cold launch');
  }],
  'add-later': ['J1.C: an existing Trio user turns on upload now: Trio sends its profile and catches up at most the last 24 h (read: GlucoseStored+helper.swift:85-88, PumpEvent+helper.swift:132-139)', async () => {
    await send(C.trio.connect({ now: now() }));
    await STEPS.onboard[1]([]);
    await backfill(24);
  }],
  connect: ['Trio onboarding → Nightscout: posts a "Trio connected" note, then offers to import the profile named "default"', async () => {
    await send(C.trio.connect({ now: now() }));
    const r = await get('/api/v1/profile.json?count=1');
    verdict(C.trio.canImport(r), Array.isArray(r) && r.length === 0);
  }],
  onboard: ['Trio uploads its settings (POST /api/v1/profile.json, store "default", APNs fields at top level)', async () => {
    await send(C.trio.profileUpload({ now: now(), units: MMOL ? 'mmol' : 'mg/dl', schedules: TH, dia: 10, presets: [{ name: 'Exercise', durationMin: 60, targetRange: [140, 140], scale: 0.7 }], deviceToken: deviceToken(), bundleIdentifier: 'org.lab.Trio', teamID: 'LABTEAM001', isAPNSProduction: false, timezone: TZ }));
  }],
  'settings-change': ['the person edits basal in Trio: a NEW profile record', async () => {
    const th = JSON.parse(JSON.stringify(TH)); th.basal[1][1] = 1.05;
    await send(C.trio.profileUpload({ now: now(), units: MMOL ? 'mmol' : 'mg/dl', schedules: th, dia: 10, presets: [{ name: 'Exercise', durationMin: 60, targetRange: [140, 140], scale: 0.7 }, { name: 'Sick', durationMin: 0, targetRange: [110, 110], scale: 1.2 }], deviceToken: deviceToken(), bundleIdentifier: 'org.lab.Trio', teamID: 'LABTEAM001', isAPNSProduction: false, timezone: TZ }));
  }],
  'override-start': ['<name=Exercise> <minutes|indef>  enable an override in Trio (uploaded as eventType Exercise; indefinite = 43200 min)', async a => {
    const o = { name: a[0] || 'Exercise', startedAt: now(), durationMin: a[1] !== undefined ? durArg(a[1], 60) : 60 };
    st.open.override = o; save(); await send(C.trio.overrideStart(Object.assign({ now: o.startedAt }, o)));
  }],
  'override-end': ['end it early: Trio deletes by created_at + eventType, then re-posts the run with its real length', async () => {
    const o = lastOpen('override'); await send(C.trio.overrideEnd({ startedAt: o.startedAt, endedAt: now(), name: o.name, originalDurationMin: o.durationMin === null ? 43200 : o.durationMin })); delete st.open.override; save();
  }],
  'tt-start': ['<target=140> <minutes=60>  temp target in Trio', async a => {
    const o = { id: C.uuid(nextId('tt'), { upper: true }), startedAt: now(), target: num(a[0], MMOL ? 7.8 : 140), durationMin: num(a[1], 60), name: 'Activity' };
    st.open.tt = o; save(); await send(C.trio.tempTargetStart(Object.assign({ now: o.startedAt }, o)));
  }],
  'tt-end': ['cancel the temp target in Trio (a second record with the real duration)', async () => {
    const o = lastOpen('tt'); await send(C.trio.tempTargetEnd(Object.assign({}, o, { endedAt: now() }))); delete st.open.tt; save();
  }],
  carbs: ['<grams=30>', async a => { const id = C.uuid(nextId('carb'), { upper: true }); st.ids.lastCarb = id; save(); await send(C.trio.carbs({ now: now(), id, grams: num(a[0], 30) })); }],
  'carb-delete': ['delete the last carb entry in Trio (DELETE ?find[id][$eq]=<UUID>)', async () => send(C.trio.carbDelete({ id: st.ids.lastCarb }))],
  bolus: ['<units=1.5>', async a => send(C.trio.bolus({ now: now(), id: C.uuid(nextId('bolus'), { upper: true }), units: num(a[0], 1.5), smb: false }))],
  suspend: ['suspend (Trio uploads a Note "PumpSuspend")', async () => send(C.trio.suspend({ now: now(), id: C.uuid(nextId('susp'), { upper: true }) }))],
  resume: ['resume (Note "PumpResume")', async () => send(C.trio.resume({ now: now(), id: C.uuid(nextId('res'), { upper: true }) }))],
  downloads: ['with "Allow downloads" on: which carbs / temp targets entered in Nightscout Trio would pick up', async () => {
    const since = new Date(now() - 24 * 60 * MIN).toISOString();
    const r = await get(`/api/v1/treatments.json?find[created_at][$gte]=${since}&count=500`);
    const v = C.trio.downloads(r);
    say('would import', `${v.carbs.length} carbs, ${v.tempTargets.length} temp targets`);
    for (const x of v.tempTargets) say('  TT', JSON.stringify(x).slice(0, 140));
    for (const x of v.skipped.slice(0, 8)) say('  skipped', `${x.t}  ${x.why}`);
    console.log(`    (emulated from ${v.source.join(' ; ')})`);
  }],
};

const AAPS = {
  restore: ['J1.D: fresh install on a new phone connects to this site: the first-load reads, whether it takes the profile, and which treatments it keeps (default settings)', async () => {
    const descs = [].concat(C.aaps.firstLoad({ variant: VARIANT, now: now(), nsBgSource: false }));
    const rs = [].concat(await send(descs));
    const cur = await get('/api/v1/profile/current');
    verdict(C.aaps.acceptsProfile({ variant: VARIANT, nsProfileDoc: cur && typeof cur === 'object' ? cur : null, localLastChange: 0 }));
    const ti = descs.findIndex(x => /treatments/.test(x.path || ''));
    const tx = ti >= 0 ? arr(rs[ti].body) : [];
    const k = C.aaps.firstLoadKeeps({ variant: VARIANT, treatments: tx });
    say('treatments seen', tx.length); say('kept', `${k.kept.length} (default accept switches)`); say('dropped', k.dropped.length);
    if (VARIANT === 'v3-40') { const n = C.aaps.fullSyncNote({ variant: VARIANT }); say('to get them', 'Full sync: ' + n.text.slice(0, 160)); }
  }],
  'ns-bg': ['J1.E: AAPS BG source "NSClient BG": reads readings from the site; never uploads them back', async () => {
    const d = [].concat(C.aaps.firstLoad({ variant: VARIANT, now: now(), nsBgSource: true })).filter(x => /entries/.test(x.path || ''));
    for (const x of d) { const r = await send(x); say('readings seen', arr(r.body).length); }
    st.cgmSource = 'nightscout'; save(); say('re-upload', 'none: bgUploadEnabled is false when the source is NSClient BG');
  }],
  'client-bootstrap': ['J1.F: AAPSClient (the caregiver build) connects: same first load, but it accepts the profile and every treatment', async () => {
    const descs = [].concat(C.aaps.firstLoad({ variant: VARIANT, now: now(), nsBgSource: true }));
    const rs = [].concat(await send(descs));
    const idx = descs.findIndex(x => /treatments/.test(x.path || ''));
    const tx = idx >= 0 ? arr(rs[idx].body) : [];
    const k = C.aaps.firstLoadKeeps({ variant: VARIANT, treatments: tx, aapsClient: true });
    say('treatments seen', tx.length); say('kept', k.kept.length); say('dropped', `${k.dropped.length} ${k.dropped.slice(0, 3).map(x => x.eventType + ': ' + x.why).join('; ')}`);
  }],
  'full-sync': ['what Full sync does on this AAPS version, and what it would keep', async () => {
    const n = C.aaps.fullSyncNote({ variant: VARIANT }); say('Full sync', n.text); for (const x of (n.dialogs || [])) say('  dialog', typeof x === 'string' ? x : JSON.stringify(x));
  }],
  wizard: ['J1.A for AAPS: the setup wizard: save the local profile (uploaded as a profile record), then the required Profile Switch (a Profile Switch and an effective-switch Note, each carrying the full profile)', async () => {
    await STEPS.onboard[1]([]);
    await STEPS['ps-start'][1](['100', '0']);
  }],
  'add-later': ['<days=7>  J1.C: an AAPS user who has looped for months turns on NSClient: AAPS uploads every retained record one at a time (up to 186 days locally; about 290 device statuses a day), profile switches, then the profile store', async a => {
    const days = num(a[0], 7);
    say('volume', `${days} days here; a real phone with 186 days sends roughly ${Math.round(186 * 288 * 2 / 1000)}k requests`);
    await backfill(days * 24);
    await send(C.aaps.profileSwitch({ variant: VARIANT, now: now() - days * 24 * 60 * MIN, profileName: 'LabDay', percentage: 100, timeshiftH: 0, durationMin: 0, profileJson: aapsProfiles().LabDay }));
    await STEPS.onboard[1]([]);
  }],
  connect: ['AAPS → NSClient: v3 asks for an admin token; v1 uses the API secret over the socket', async () => {
    if (VARIANT.startsWith('v3')) {
      if (!st.tokens.app) {
        await send({ label: 'subject lab-aaps [admin] (the person makes it on the admin page, as AAPS asks)', method: 'POST', path: '/api/v2/authorization/subjects', body: { name: 'lab-aaps', roles: ['admin'] }, auth: 'secret', source: ['AndroidAPS plugins/sync strings.xml (admin token)'] });
        st.tokens.app = (await get('/api/v2/authorization/subjects')).find(x => x.name === 'lab-aaps').accessToken; save();
      }
      await jwt(); say('JWT', 'exchanged');
    } else { await socket(); say('socket', 'authorized'); }
    const cur = await get('/api/v1/profile/current');
    verdict(C.aaps.acceptsProfile({ variant: VARIANT, nsProfileDoc: cur && typeof cur === 'object' ? cur : null, localLastChange: st.ids.aapsLastChange || now() - 7 * 24 * 60 * MIN }), cur === null);
  }],
  onboard: ['AAPS uploads its local profile store (every local profile, the active one as default)', async () => {
    const t = now(); st.ids.aapsLastChange = t; save();
    await send(C.aaps.profileStore({ variant: VARIANT, now: t, units: MMOL ? 'mmol' : 'mg/dl', defaultProfile: 'LabDay', profiles: aapsProfiles() }));
  }],
  'settings-change': ['edit a profile in AAPS: a new store record', async () => {
    const ps = aapsProfiles(); ps.LabDay.basal[1][1] = 1.05; const t = now(); st.ids.aapsLastChange = t; save();
    await send(C.aaps.profileStore({ variant: VARIANT, now: t, units: MMOL ? 'mmol' : 'mg/dl', defaultProfile: 'LabDay', profiles: ps }));
  }],
  'ps-start': ['<percentage=120> <minutes=0 (0 = permanent)> <profile=LabDay>  profile switch in AAPS', async a => {
    const name = a[2] || 'LabDay'; const pct = num(a[0], 120);
    const o = { identifier: C.uuid(nextId('ps')), startedAt: now(), profileName: name, percentage: pct, timeshiftH: 0, durationMin: num(a[1], 0) };
    st.open.ps = o; save();
    await send(C.aaps.profileSwitch(Object.assign({ variant: VARIANT, now: o.startedAt, profileJson: aapsProfiles()[name] }, o)));
    await send(C.aaps.effectiveProfileSwitch({ variant: VARIANT, now: o.startedAt + 1000, identifier: C.uuid(nextId('eps')), profileName: name, profileJson: aapsProfiles()[name], percentage: pct }));
  }],
  'tt-start': ['<target=140 or 7.8> <minutes=60>  temp target in AAPS', async a => {
    const tgt = num(a[0], MMOL ? 7.8 : 140); const o = { startedAt: now(), low: tgt, high: tgt, durationMin: num(a[1], 60), reason: 'Activity' };
    const r = await send(C.aaps.tempTargetStart(Object.assign({ variant: VARIANT, now: o.startedAt }, o)));
    Object.assign(o, createdId(r)); st.open.tt = o; save(); say('stored as', JSON.stringify(createdId(r)));
  }],
  'tt-cancel': ['cancel it in AAPS (v3: PATCH the running record; v1: dbUpdate by _id)', async () => {
    const o = lastOpen('tt'); await send(C.aaps.tempTargetCancel({ variant: VARIANT, identifier: o.identifier, nsId: o.nsId, startedAt: o.startedAt, endedAt: now() })); st.open.lastTt = o; delete st.open.tt; save();
  }],
  carbs: ['<grams=30>', async a => { const r = await send(C.aaps.carbs({ variant: VARIANT, now: now(), grams: num(a[0], 30) })); st.ids.lastCarb = Object.assign(createdId(r), { record: { eventType: 'Carb Correction', carbs: num(a[0], 30), date: now() } }); save(); say('stored as', JSON.stringify(st.ids.lastCarb)); }],
  'carb-delete': ['invalidate the last carb entry in AAPS (v3: DELETE, the server soft-deletes; v1: dbUpdate isValid:false)', async () => send(C.aaps.remove(Object.assign({ variant: VARIANT, collection: 'treatments' }, st.ids.lastCarb)))],
  bolus: ['<units=1.5>', async a => send(C.aaps.bolus({ variant: VARIANT, now: now(), identifier: C.uuid(nextId('bolus')), units: num(a[0], 1.5), smb: false }))],
  'loop-off': ['<minutes=30>  AAPS running mode: disconnect / loop off (OpenAPS Offline)', async a => send(C.aaps.runningMode({ variant: VARIANT, now: now(), identifier: C.uuid(nextId('mode')), mode: 'DISCONNECTED_PUMP', durationMin: num(a[0], 30) }))],
  'accept-check': ['would AAPS take the profile / temp targets / profile switches now in Nightscout? (emulates the NSClient accept rules for this variant)', async () => {
    const cur = await get('/api/v1/profile/current');
    verdict(C.aaps.acceptsProfile({ variant: VARIANT, nsProfileDoc: cur && typeof cur === 'object' ? cur : null, localLastChange: st.ids.aapsLastChange || now() - 7 * 24 * 60 * MIN }));
    say('phone last change', st.ids.aapsLastChange ? new Date(st.ids.aapsLastChange).toISOString() + ' (the last profile this lab uploaded as AAPS)' : 'assumed a week ago (this phone never uploaded)');
    const since = new Date(now() - 24 * 60 * MIN).toISOString();
    const tx = await get(`/api/v1/treatments.json?find[created_at][$gte]=${since}&find[eventType][$in][]=Temporary%20Target&find[eventType][$in][]=Profile%20Switch&count=50`);
    for (const t of (Array.isArray(tx) ? tx : []).slice(0, 6)) { console.log(`  ${t.eventType} by ${t.enteredBy || '-'} at ${t.created_at}`); verdict(C.aaps.acceptsTreatment({ variant: VARIANT, treatment: t })); }
  }],
};
function aapsProfiles () {
  const base = { dia: 6, basal: TH.basal.map(x => [...x]), sens: TH.sens.map(x => [...x]), carbratio: TH.carbratio.map(x => [...x]), target: TH.target.map(x => [...x]), timezone: TZ };
  const weekend = JSON.parse(JSON.stringify(base)); weekend.basal = weekend.basal.map(([t, v]) => [t, Math.round(v * 0.9 * 100) / 100]);
  return { LabDay: base, LabWeekend: weekend };
}

const STEPS = Object.assign({}, COMMON, { loop: LOOP, trio: TRIO, aaps: AAPS }[KIND] || {});

(async () => {
  if (STEP === 'help' || !STEPS[STEP]) {
    if (STEP !== 'help') console.log(`no step "${STEP}" for ${NAME} (${KIND}${KIND === 'aaps' ? ' ' + VARIANT : ''})`);
    console.log(`steps for ${NAME} (${KIND}${KIND === 'aaps' ? ' ' + VARIANT : ''}):`);
    for (const [k, [h]] of Object.entries(STEPS)) console.log(`  ${k.padEnd(20)} ${h}`);
    process.exit(STEP === 'help' ? 0 : 2);
  }
  console.log(`[${NAME}] ${STEP} ${ARGS.join(' ')}`);
  await STEPS[STEP][1](ARGS);
  save();
  if (sock) sock.close();
})().catch(e => { console.error('  ✗ ' + e.message); if (sock) sock.close(); process.exit(1); });
