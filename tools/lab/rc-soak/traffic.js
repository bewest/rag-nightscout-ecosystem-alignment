#!/usr/bin/env node
'use strict';
/*
 * traffic.js - one synthetic Nightscout "household" sent identically to every
 * arm. Each operation is sent to all arms at the same moment (in parallel),
 * the replies are normalised and compared, and one line per operation goes to
 * requests.jsonl. Writes that an arm acknowledges go to ledger.jsonl, so the
 * analyser can check every acknowledged write is in that arm's database.
 *
 * Every value is generated here. Nothing comes from a real person's data.
 * Every record carries `soakKey`, a lab-only field, so records can be matched
 * across arms without relying on either build's ids or dedup keys.
 *
 * Environment:
 *   RUN          run directory (requests.jsonl, ledger.jsonl, diffs.jsonl,
 *                socket-<arm>.jsonl, state.json, traffic.log)
 *   ARMS         comma list name=httpBase|socketBase|secretFile
 *                (httpBase may be a fault proxy; socketBase is the server)
 *   MODULES      node_modules dir that has socket.io-client
 *   SIM_HOURS    simulated span; DURATION_MIN real minutes (compressed mode)
 *   REALTIME=1   real-time mode: one CGM tick every 5 min for HOURS hours
 *   FOLLOW_PER_TICK  follower polls per CGM tick (default 1 compressed, 5 real)
 *
 * Simulated time ends at real time: in compressed mode the run backfills the
 * simulated span so its last tick lands on "now", and nothing is ever written
 * with a future timestamp.
 *
 * Schedule, by CGM tick n (one tick = 5 simulated minutes):
 *   CGM (xDrip-like)  sgv every tick, client _id on even ticks; re-send of the
 *                     last 3 readings when n%6==5; mbg when n%72==36
 *   Loop / Trio       devicestatus every tick (Loop shape even, Trio/openaps
 *                     shape odd), re-sent when n%50==25; Temp Basal even n;
 *                     Correction Bolus n%12==3; Carb Correction n%36==9;
 *                     Temporary Override n%72==40; Temp Target n%24==15;
 *                     oref0 temp basal n%6==4; last 2 treatments re-sent n%10==7
 *   AndroidAPS (v3)   Temp Basal create n%4==1 (re-sent n%16==9), SMB n%12==7,
 *                     PUT n%8==3, soft DELETE n%48==23, devicestatus n%6==2
 *   edits/deletes     v1 PUT n%24==20, v1 DELETE treatment n%24==22,
 *                     socket dbUpdate n%24==21 (tb n-17), socket dbRemove n%48==45 (tb n-15),
 *                     v1 DELETE entry n%72==60
 *                     v1 DELETE devicestatus n%72==30
 *   profile           tick 0 and n%288==144; Loop remote command n%144==100
 *   page load         n%12==11 and at the end: a new socket per arm records the
 *                     full dataUpdate a newly opened web page is sent
 *   followers         LoopFollow, nightguard, oref0 count=1?..., GluPredKit
 *                     count=0 windows, AAPS v3 reads, status/properties
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const RUN = process.env.RUN;
fs.writeFileSync(path.join(RUN, 'pid-traffic'), String(process.pid));
const io = require(path.join(process.env.MODULES, 'socket.io-client'));
const ARMS = process.env.ARMS.split(',').map((spec) => {
  const [name, rest] = spec.split('=');
  const [base, sock, secretFile] = rest.split('|');
  const secret = fs.readFileSync(secretFile, 'utf8').trim();
  return { name, base, sock, hash: crypto.createHash('sha1').update(secret).digest('hex'),
    ids: new Map(), docs: new Map(), retry: [], lastSgv: null, jwt: null, jwtAt: 0, follower: null };
});

const P = 300000;
const REAL = process.env.REALTIME === '1';
const N = REAL ? Math.round(Number(process.env.HOURS || 24) * 12) : Math.round(Number(process.env.SIM_HOURS || 72) * 12);
const REAL_TICK = REAL ? P : (Number(process.env.DURATION_MIN || 45) * 60000) / N;
const FOLLOW = Number(process.env.FOLLOW_PER_TICK || (REAL ? 5 : 1));
const realStart = Date.now() + 5000;
const simStart = Math.floor((realStart + N * REAL_TICK - N * P) / P) * P;
const simAt = (n) => simStart + n * P + 7000; // readings land 7 s after the boundary
const iso = (ms) => new Date(ms).toISOString();

const out = (f, o) => fs.appendFileSync(path.join(RUN, f), JSON.stringify(o) + '\n');
const note = (m) => fs.appendFileSync(path.join(RUN, 'traffic.log'), new Date().toISOString() + ' ' + m + '\n');
const md5 = (s) => crypto.createHash('md5').update(s).digest('hex');
const hexId = (k) => md5('id:' + k).slice(0, 24);
const uuid = (k) => { const h = md5('uuid:' + k); return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20, 32)}`; };
const CLIENT_IDS = new Set(); // hex _id and identifiers the client chose; kept when normalising
const num = (k, lo, hi, dp) => { const x = parseInt(md5('n:' + k).slice(0, 8), 16) / 0xffffffff; return Number((lo + x * (hi - lo)).toFixed(dp || 0)); };

// ---- synthetic glucose (the connector-soak writer's two waves plus bounded noise)
function sgvAt (ms) {
  const h = ms / 3600000;
  const noise = (parseInt(md5(String(ms)).slice(0, 4), 16) % 11) - 5;
  return Math.round(140 + 55 * Math.sin(2 * Math.PI * h / 7) + 20 * Math.sin(2 * Math.PI * h / 2.3) + noise);
}
function direction (d) {
  if (d > 15) return 'DoubleUp'; if (d > 10) return 'SingleUp'; if (d > 5) return 'FortyFiveUp';
  if (d < -15) return 'DoubleDown'; if (d < -10) return 'SingleDown'; if (d < -5) return 'FortyFiveDown';
  return 'Flat';
}

// ---- HTTP
async function req (arm, method, p, body, headers) {
  const t0 = Date.now();
  try {
    const r = await fetch(arm.base + p, { method, headers: { 'content-type': 'application/json', ...(headers || {}) },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(30000) });
    const text = await r.text();
    let j; try { j = JSON.parse(text); } catch (e) { /* not JSON */ }
    return { st: r.status, ms: Date.now() - t0, j, text, dep: r.headers.get('deprecation') || '' };
  } catch (err) {
    return { st: 0, ms: Date.now() - t0, err: (err.cause && err.cause.code) || err.name || 'ERR', text: '', dep: '' };
  }
}
const SEC = (arm) => ({ 'api-secret': arm.hash });
async function jwt (arm) {
  if (arm.jwt && Date.now() - arm.jwtAt < 30 * 60000) return arm.jwt;
  const r = await req(arm, 'GET', '/api/v2/authorization/request/' + arm.aapsToken);
  if (r.st === 200 && r.j && r.j.token) { arm.jwt = r.j.token; arm.jwtAt = Date.now(); }
  return arm.jwt;
}
const V3 = async (arm) => ({ authorization: 'Bearer ' + await jwt(arm) });

async function subjects (arm) {
  const want = [['soak-follower', ['readable']], ['soak-aaps', ['admin']]];
  let list = (await req(arm, 'GET', '/api/v2/authorization/subjects', undefined, SEC(arm))).j || [];
  for (const [name, roles] of want) {
    if (!list.find((s) => s.name === name)) await req(arm, 'POST', '/api/v2/authorization/subjects', { name, roles }, SEC(arm));
  }
  list = (await req(arm, 'GET', '/api/v2/authorization/subjects', undefined, SEC(arm))).j || [];
  arm.follower = list.find((s) => s.name === 'soak-follower').accessToken;
  arm.aapsToken = list.find((s) => s.name === 'soak-aaps').accessToken;
  if (!arm.follower || !arm.aapsToken || !await jwt(arm)) throw new Error('arm ' + arm.name + ': could not set up subjects');
  // the server reloads subjects asynchronously: wait until the follower token reads
  for (let i = 0; i < 30; i++) {
    if ((await req(arm, 'GET', '/api/v1/entries.json?count=1&token=' + arm.follower)).st === 200) return;
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error('arm ' + arm.name + ': follower token never accepted');
}

// ---- normalisation and comparison
const DROP = new Set(['srvModified', 'srvCreated', 'lastModified']); // server clock, differs by ms between arms
const KEYS_ONLY = /^(status|nightguard\.properties|aaps\.lastModified)/;
function norm (v, arm) {
  if (Array.isArray(v)) return v.map((x) => norm(x, arm));
  if (v && typeof v === 'object') {
    const o = {};
    for (const k of Object.keys(v).sort()) if (!DROP.has(k)) o[k] = norm(v[k], arm);
    return o;
  }
  if (typeof v === 'string') {
    if (CLIENT_IDS.has(v) || CLIENT_IDS.has(v.toLowerCase())) return v;
    if (/^[0-9a-f]{24}$/i.test(v)) return '<oid>';
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)) return '<uuid>';
    if (v.includes(arm.hash)) return v.split(arm.hash).join('<hash>');
  }
  return v;
}
function keysOf (v, p, acc) {
  if (v && typeof v === 'object') {
    for (const k of Object.keys(v)) { const q = p + (Array.isArray(v) ? '[*]' : '.' + k); acc.add(q); keysOf(v[k], q, acc); }
  }
  return acc;
}
function diffPaths (a, b, p, acc) {
  if (acc.length >= 12) return acc;
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) acc.push(p + '.length');
    for (let i = 0; i < Math.min(a.length, b.length); i++) diffPaths(a[i], b[i], p + '[*]', acc);
    return acc;
  }
  if (a && b && typeof a === 'object' && typeof b === 'object' && !Array.isArray(a) && !Array.isArray(b)) {
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
      if (!(k in a)) acc.push(p + '.' + k + ' (only B)'); else if (!(k in b)) acc.push(p + '.' + k + ' (only A)');
      else diffPaths(a[k], b[k], p + '.' + k, acc);
    }
    return acc;
  }
  if (JSON.stringify(a) !== JSON.stringify(b)) acc.push(p || '.');
  return acc;
}
const diffCount = new Map();
function compare (label, rs) {
  if (rs.length < 2 || rs.every((r) => !r)) return null;
  if (rs.some((r) => !r)) {
    const sig = label + ' | skipped on ' + ARMS.filter((a, i) => !rs[i]).map((a) => a.name).join(',') + ' (no _id from its reply)';
    diffCount.set(sig, (diffCount.get(sig) || 0) + 1);
    return sig;
  }
  const [ra, rb] = rs;
  const view = (r, arm) => {
    const body = r.j !== undefined ? r.j : r.text.slice(0, 300);
    return KEYS_ONLY.test(label) ? [...keysOf(body, '', new Set())].sort() : norm(body, arm);
  };
  const va = view(ra, ARMS[0]); const vb = view(rb, ARMS[1]);
  const paths = [];
  if (ra.st !== rb.st) paths.push('status ' + ra.st + '->' + rb.st);
  if (ra.dep !== rb.dep) paths.push('header Deprecation "' + ra.dep + '"->"' + rb.dep + '"');
  if (ra.st === rb.st && KEYS_ONLY.test(label)) {
    // volatile values: compare the key sets only, and name the keys that differ
    const sa = new Set(va); const sb = new Set(vb);
    const oa = va.filter((k) => !sb.has(k)); const ob = vb.filter((k) => !sa.has(k));
    if (oa.length) paths.push('keys only A: ' + oa.slice(0, 8).join(' '));
    if (ob.length) paths.push('keys only B: ' + ob.slice(0, 8).join(' '));
  } else if (ra.st === rb.st) diffPaths(va, vb, '', paths);
  if (!paths.length) return null;
  const sig = label + ' | ' + [...new Set(paths.map((x) => x.replace(/\[\*\]/g, '[]')))].slice(0, 6).join(', ');
  const c = (diffCount.get(sig) || 0) + 1; diffCount.set(sig, c);
  if (KEYS_ONLY.test(label) && c <= 5 && ra.j && rb.j && typeof ra.j === 'object') {
    // key sets differ: keep the values under each differing top-level key, so the difference can be read
    const tops = [...new Set(paths.map((x) => (x.match(/\.([^.[\s]+)/) || [])[1]).filter(Boolean))];
    out('diffs-values.jsonl', { t: new Date().toISOString(), n: tickN, label, sig, values: Object.fromEntries(tops.map((k) => [k, { a: norm(ra.j[k], ARMS[0]), b: norm(rb.j[k], ARMS[1]) }])) });
  }
  if (c <= 3) out('diffs.jsonl', { t: new Date().toISOString(), label, sig, st: [ra.st, rb.st], a: JSON.stringify(va).slice(0, 1500), b: JSON.stringify(vb).slice(0, 1500) });
  return sig;
}

// ---- operations
let tickN = 0;
async function op (label, spec, opts) {
  opts = opts || {};
  const specs = await Promise.all(ARMS.map((arm) => spec(arm)));
  const rs = await Promise.all(ARMS.map((arm, i) => specs[i] ? req(arm, specs[i].method, specs[i].path, specs[i].body, specs[i].headers) : null));
  let sig = opts.compare === false ? null : compare(label, rs);
  if (sig && KEYS_ONLY.test(label) && !opts.write) {
    // these answers come from each server's in-memory copy of the data, which reloads a
    // moment after a write; ask again once, 3 s later, before calling it a difference
    await new Promise((r) => setTimeout(r, 3000));
    const again = await Promise.all(ARMS.map((arm, i) => specs[i] ? req(arm, specs[i].method, specs[i].path, specs[i].body, specs[i].headers) : null));
    if (!compare(label + ' (re-asked)', again)) sig = 'transient: ' + sig;
  }
  out('requests.jsonl', { t: new Date().toISOString(), n: tickN, label, r: rs.map((r) => r ? [r.st, r.ms, r.err || '', r.dep ? 1 : 0] : null), ...(sig ? { sig } : {}) });
  ARMS.forEach((arm, i) => {
    const r = rs[i]; if (!r) return;
    if (opts.write) {
      if (r.st >= 200 && r.st < 300) { ack(arm, opts.write, r); if (opts.after) opts.after(arm, r); }
      else if (r.st === 0 || r.st >= 500) arm.retry.push({ label, spec: specs[i], write: opts.write, after: opts.after, tries: 1 });
    } else if (opts.after && r.st >= 200 && r.st < 300) opts.after(arm, r);
  });
  return rs;
}
function ack (arm, w, r) {
  for (const x of [].concat(w)) out('ledger.jsonl', { arm: arm.name, act: x.act || 'ack', coll: x.coll, key: x.key, n: tickN, t: new Date().toISOString() });
  // remember each stored document's _id, from the reply, by soakKey
  const rows = Array.isArray(r.j) ? r.j : (r.j && r.j.result ? [r.j.result] : (r.j ? [r.j] : []));
  for (const d of rows) if (d && d.soakKey && d._id) arm.ids.set(d.soakKey, String(d._id));
}
async function drainRetries (arm) {
  const q = arm.retry.splice(0);
  for (const job of q) {
    const r = await req(arm, job.spec.method, job.spec.path, job.spec.body, job.spec.headers);
    out('requests.jsonl', { t: new Date().toISOString(), n: tickN, label: 'retry:' + job.label, arm: arm.name, r: [[r.st, r.ms, r.err || '', 0]] });
    if (r.st >= 200 && r.st < 300) { ack(arm, job.write, r); if (job.after) job.after(arm, r); } else if (r.st === 0 || r.st >= 500) { job.tries += 1; arm.retry.push(job); }
  }
}

// ---- record shapes
function sgvDoc (n, withId) {
  const t = simAt(n); const v = sgvAt(t); const key = 'sgv-' + n;
  const d = { soakKey: key, device: 'xDrip-DexcomG6', date: t, dateString: iso(t), sysTime: iso(t), sgv: v,
    delta: Number((v - sgvAt(t - P)).toFixed(3)), direction: direction(v - sgvAt(t - P)), type: 'sgv',
    filtered: v * 1000, unfiltered: v * 1000 + 350, rssi: 100, noise: 1, utcOffset: 0 };
  if (withId) { d._id = hexId(key); CLIENT_IDS.add(d._id); }
  return d;
}
function loopStatus (n) {
  const t = simAt(n) + 40000; const bg = sgvAt(simAt(n));
  return { soakKey: 'ds-' + n, device: 'loop://iPhone', created_at: iso(t),
    pump: { clock: iso(t), pumpID: 'SYNTH01', manufacturer: 'Synthetic', model: 'Synth', reservoir: Number((200 - (n % 400) * 0.45).toFixed(2)), battery: { percent: 80 - (n % 50) }, suspended: false, bolusing: false, secondsFromGMT: 0 },
    uploader: { name: 'iPhone', timestamp: iso(t), battery: 100 - (n % 70) },
    loop: { name: 'Loop', version: '3.4.0', timestamp: iso(t),
      iob: { iob: num('iob' + n, 0, 4, 2), basaliob: num('biob' + n, -0.5, 1.5, 2), timestamp: iso(t) },
      cob: { cob: num('cob' + n, 0, 60, 1), timestamp: iso(t) },
      predicted: { startDate: iso(t), values: Array.from({ length: 12 }, (_, i) => bg + i * 2 - 10) },
      enacted: { rate: num('er' + n, 0, 2.5, 2), duration: 30, timestamp: iso(t), received: true, bolusVolume: 0 },
      recommendedBolus: 0 },
    override: { active: false, timestamp: iso(t) } };
}
function trioStatus (n) {
  const t = simAt(n) + 40000; const bg = sgvAt(simAt(n));
  return { soakKey: 'ds-' + n, device: 'Trio', created_at: iso(t),
    openaps: { iob: { iob: num('iob' + n, 0, 4, 2), basaliob: num('biob' + n, -0.5, 1.5, 2), activity: 0.01, time: iso(t) },
      suggested: { bg, temp: 'absolute', rate: num('sr' + n, 0, 2.5, 2), duration: 30, COB: num('cob' + n, 0, 60, 0), IOB: num('iob' + n, 0, 4, 2), eventualBG: bg - 8, reason: 'synthetic', timestamp: iso(t), predBGs: { IOB: Array.from({ length: 12 }, (_, i) => bg - i) } },
      enacted: { bg, rate: num('sr' + n, 0, 2.5, 2), duration: 30, received: true, timestamp: iso(t) } },
    pump: { clock: iso(t), reservoir: Number((180 - (n % 360) * 0.5).toFixed(1)), battery: { percent: 75 }, status: { status: 'normal', bolusing: false, suspended: false, timestamp: iso(t) } },
    uploader: { batteryVoltage: 3.9, battery: 90 - (n % 60) } };
}
function v1Treatments (n) {
  const t = simAt(n); const out2 = [];
  if (n % 2 === 0) out2.push({ soakKey: 'tb-' + n, eventType: 'Temp Basal', created_at: iso(t + 2000), rate: num('tb' + n, 0, 2.5, 2), absolute: num('tb' + n, 0, 2.5, 2), duration: 30, temp: 'absolute', enteredBy: 'loop://iPhone', syncIdentifier: md5('tbs' + n) });
  if (n % 12 === 3) out2.push({ soakKey: 'bolus-' + n, eventType: 'Correction Bolus', created_at: iso(t + 3000), insulin: num('bo' + n, 0.2, 3, 2), programmed: num('bo' + n, 0.2, 3, 2), type: 'normal', unabsorbed: 0, enteredBy: 'loop://iPhone', syncIdentifier: md5('bos' + n) });
  if (n % 36 === 9) out2.push({ soakKey: 'carb-' + n, eventType: 'Carb Correction', created_at: iso(t + 4000), carbs: num('ca' + n, 10, 70, 0), absorptionTime: 180, foodType: 'synthetic', enteredBy: 'loop://iPhone', syncIdentifier: md5('cas' + n) });
  if (n % 72 === 40) out2.push({ soakKey: 'ovr-' + n, eventType: 'Temporary Override', created_at: iso(t + 5000), reason: 'Exercise', correctionRange: [140, 160], insulinNeedsScaleFactor: 0.8, duration: 60, durationType: 'finite', enteredBy: 'loop://iPhone' });
  if (n % 24 === 15) out2.push({ soakKey: 'tt-' + n, eventType: 'Temporary Target', created_at: iso(t + 6000), targetTop: 140, targetBottom: 140, units: 'mg/dl', duration: 60, reason: 'Activity', enteredBy: 'Trio' });
  if (n % 6 === 4) out2.push({ soakKey: 'oref-' + n, eventType: 'Temp Basal', created_at: iso(t + 8000), rate: num('or' + n, 0, 2, 2), absolute: num('or' + n, 0, 2, 2), duration: 30, temp: 'absolute', enteredBy: 'openaps://medtronic/522' });
  return out2;
}
function aapsTb (n) {
  const key = 'aaps-tb-' + n; const id = uuid(key); CLIENT_IDS.add(id);
  return { soakKey: key, identifier: id, date: simAt(n) + 11000, utcOffset: 0, app: 'AndroidAPS', device: 'AndroidAPS-DanaRS', eventType: 'Temp Basal', isValid: true,
    rate: num('at' + n, 0, 2, 2), absolute: num('at' + n, 0, 2, 2), duration: 30, durationInMilliseconds: 1800000, type: 'NORMAL', pumpId: 100000 + n, pumpType: 'DANA_RS', pumpSerial: 'SYNTH0001' };
}
function aapsSmb (n) {
  const key = 'aaps-smb-' + n; const id = uuid(key); CLIENT_IDS.add(id);
  return { soakKey: key, identifier: id, date: simAt(n) + 13000, utcOffset: 0, app: 'AndroidAPS', device: 'AndroidAPS-DanaRS', eventType: 'Correction Bolus', isValid: true,
    insulin: num('sm' + n, 0.1, 1, 2), type: 'SMB', isBasalInsulin: false, pumpId: 200000 + n, pumpType: 'DANA_RS', pumpSerial: 'SYNTH0001' };
}
function aapsStatus (n) {
  const key = 'aaps-ds-' + n; const id = uuid(key); CLIENT_IDS.add(id); const t = simAt(n) + 17000;
  return { soakKey: key, identifier: id, date: t, created_at: iso(t), utcOffset: 0, app: 'AndroidAPS', device: 'openaps://AndroidAPS', uploaderBattery: 60 + (n % 40), isCharging: false,
    pump: { clock: iso(t), reservoir: 120, battery: { percent: 70 }, status: { status: 'normal', timestamp: iso(t) } },
    openaps: { iob: { iob: num('aiob' + n, 0, 3, 2), basaliob: 0.1, time: iso(t) }, suggested: { bg: sgvAt(simAt(n)), eventualBG: sgvAt(simAt(n)) - 5, reason: 'synthetic', timestamp: iso(t) } },
    configuration: { insulin: 5, sensitivity: 2, smbAlgorithm: 'SMB' } };
}
function profileDoc (n) {
  const t = simAt(n); const sched = (v) => [{ time: '00:00', value: v, timeAsSeconds: 0 }];
  return { soakKey: 'profile-' + n, defaultProfile: 'Default', startDate: iso(t), created_at: iso(t), mills: t, units: 'mg/dl', enteredBy: 'Loop',
    store: { Default: { dia: 6, carbratio: sched(10 + (n % 3)), sens: sched(45), basal: [{ time: '00:00', value: 0.8, timeAsSeconds: 0 }, { time: '06:00', value: 1.0, timeAsSeconds: 21600 }],
      target_low: sched(100), target_high: sched(110), units: 'mg/dl', timezone: 'UTC', delay: 20, startDate: '1970-01-01T00:00:00.000Z' } } };
}

// ---- sockets: a web follower (token) that records dataUpdate, and an editor (secret)
function followerSocket (arm) {
  const s = io(arm.sock, { transports: ['websocket'], reconnection: true, reconnectionDelay: 1000, forceNew: true });
  const f = 'socket-' + arm.name + '.jsonl';
  // as the web client does: exchange the access token for a JWT, send the JWT as `token`
  s.on('connect', async () => {
    out(f, { t: new Date().toISOString(), ev: 'connect' });
    const r = await req(arm, 'GET', '/api/v2/authorization/request/' + arm.follower);
    s.emit('authorize', { client: 'web', token: r.j && r.j.token, history: 48 }, (a) => out(f, { t: new Date().toISOString(), ev: 'authorized', read: Boolean(a && a.read) }));
  });
  s.on('disconnect', (why) => {
    out(f, { t: new Date().toISOString(), ev: 'disconnect', why });
    // socket.io does not reconnect after a server-side disconnect; the web client reloads, so do the same
    if (why === 'io server disconnect' && !stopping) setTimeout(() => s.connect(), 30000);
  });
  s.on('dataUpdate', (d) => {
    out(f, { t: new Date().toISOString(), ev: 'dataUpdate', delta: Boolean(d.delta),
      sgv: (d.sgvs || []).map((x) => x.mills), tr: (d.treatments || []).map((x) => x.soakKey).filter(Boolean),
      ds: (d.devicestatus || []).map((x) => x.soakKey).filter(Boolean) });
  });
  arm.fsock = s;
}
function editorSocket (arm) {
  return new Promise((resolve) => {
    const s = io(arm.sock, { transports: ['websocket'], reconnection: true, forceNew: true });
    s.on('connect', () => s.emit('authorize', { client: 'web', secret: arm.hash, history: 1 }, () => { arm.esock = s; resolve(); }));
    setTimeout(resolve, 10000);
  });
}
function emit (arm, ev, data) {
  const t0 = Date.now();
  return new Promise((resolve) => {
    if (!arm.esock || !arm.esock.connected) return resolve({ st: 0, ms: 0, err: 'no-socket', text: '', dep: '' });
    const to = setTimeout(() => resolve({ st: 0, ms: Date.now() - t0, err: 'NO-ACK', text: '', dep: '' }), 10000);
    arm.esock.emit(ev, data, (a) => { clearTimeout(to); resolve({ st: 200, ms: Date.now() - t0, j: a, text: '', dep: '' }); });
  });
}
async function sockOp (label, ev, dataFn, write) {
  const datas = ARMS.map((arm) => dataFn(arm));
  const rs = await Promise.all(ARMS.map((arm, i) => datas[i] ? emit(arm, ev, datas[i]) : null));
  const sig = compare(label, rs);
  out('requests.jsonl', { t: new Date().toISOString(), n: tickN, label, r: rs.map((r) => r ? [r.st, r.ms, r.err || '', 0] : null), ...(sig ? { sig } : {}) });
  ARMS.forEach((arm, i) => { if (rs[i] && rs[i].st === 200 && write) out('ledger.jsonl', { arm: arm.name, act: write.act, coll: write.coll, key: write.key, n: tickN, t: new Date().toISOString() }); });
}

// A page opened now: a new socket, authorized, and the full dataUpdate it is sent first.
function pageLoad (arm, n) {
  return new Promise((resolve) => {
    const s = io(arm.sock, { transports: ['websocket'], forceNew: true, reconnection: false });
    const done = (row) => { clearTimeout(to); s.close(); out('pageload-' + arm.name + '.jsonl', { t: new Date().toISOString(), n, ...row }); resolve(); };
    const to = setTimeout(() => done({ error: 'no dataUpdate' }), 15000);
    s.on('connect', async () => {
      const r = await req(arm, 'GET', '/api/v2/authorization/request/' + arm.follower);
      s.emit('authorize', { client: 'web', token: r.j && r.j.token, history: 48 });
    });
    s.once('dataUpdate', (d) => done({ sgv: (d.sgvs || []).map((x) => x.mills), tr: (d.treatments || []).map((x) => x.soakKey).filter(Boolean),
      ds: (d.devicestatus || []).map((x) => x.soakKey).filter(Boolean) }));
  });
}

// ---- one CGM tick
const lastPosted = [];
let lastDs = null; let lastAaps = null;
async function writes (n) {
  const t = simAt(n);
  // CGM
  const e = sgvDoc(n, n % 2 === 0);
  const docs = [e]; if (n % 72 === 36) docs.push({ soakKey: 'mbg-' + n, device: 'xDrip-DexcomG6', type: 'mbg', mbg: sgvAt(t) + 4, date: t + 3000, dateString: iso(t + 3000), utcOffset: 0 });
  await op(e._id ? 'cgm.post+id' : 'cgm.post', (arm) => ({ method: 'POST', path: '/api/v1/entries', body: docs, headers: SEC(arm) }),
    { write: docs.map((d) => ({ coll: 'entries', key: d.soakKey })), after: (arm) => { arm.lastSgv = t; } });
  if (n % 6 === 5 && n >= 3) {
    const re = [n - 2, n - 1, n].map((k) => sgvDoc(k, k % 2 === 0));
    await op('cgm.resend3', (arm) => ({ method: 'POST', path: '/api/v1/entries', body: re, headers: SEC(arm) }), { write: re.map((d) => ({ coll: 'entries', key: d.soakKey, act: 'resend' })) });
  }
  // Loop / Trio devicestatus
  const ds = n % 2 === 0 ? loopStatus(n) : trioStatus(n);
  await op(n % 2 === 0 ? 'loop.devicestatus' : 'trio.devicestatus', (arm) => ({ method: 'POST', path: '/api/v1/devicestatus', body: [ds], headers: SEC(arm) }), { write: { coll: 'devicestatus', key: ds.soakKey } });
  if (n % 50 === 25 && lastDs) { const d0 = lastDs; await op('loop.devicestatus.resend', (arm) => ({ method: 'POST', path: '/api/v1/devicestatus', body: [d0], headers: SEC(arm) }), { write: { coll: 'devicestatus', key: d0.soakKey, act: 'resend' } }); }
  lastDs = ds;
  // v1 treatments
  for (const tr of v1Treatments(n)) {
    const lbl = tr.enteredBy.startsWith('openaps') ? 'oref0.upload' : (tr.enteredBy === 'Trio' ? 'trio.treatment' : 'loop.treatment') + '.' + tr.eventType.replace(/ /g, '');
    await op(lbl, (arm) => ({ method: 'POST', path: tr.enteredBy.startsWith('openaps') ? '/api/v1/treatments.json' : '/api/v1/treatments', body: [tr], headers: SEC(arm) }), { write: { coll: 'treatments', key: tr.soakKey } });
    lastPosted.push(tr); if (lastPosted.length > 2) lastPosted.shift();
  }
  if (n % 10 === 7 && lastPosted.length) { const re = lastPosted.slice(); await op('loop.treatment.resend2', (arm) => ({ method: 'POST', path: '/api/v1/treatments', body: re, headers: SEC(arm) }), { write: re.map((d) => ({ coll: 'treatments', key: d.soakKey, act: 'resend' })) }); }
  // AndroidAPS v3
  if (n % 4 === 1) { const d = aapsTb(n); lastAaps = d; await op('aaps.v3.create.TempBasal', async (arm) => ({ method: 'POST', path: '/api/v3/treatments', body: d, headers: await V3(arm) }), { write: { coll: 'treatments', key: d.soakKey } }); }
  if (n % 16 === 9 && lastAaps) { const d = lastAaps; await op('aaps.v3.create.resend', async (arm) => ({ method: 'POST', path: '/api/v3/treatments', body: d, headers: await V3(arm) }), { write: { coll: 'treatments', key: d.soakKey, act: 'resend' } }); }
  if (n % 12 === 7) { const d = aapsSmb(n); await op('aaps.v3.create.SMB', async (arm) => ({ method: 'POST', path: '/api/v3/treatments', body: d, headers: await V3(arm) }), { write: { coll: 'treatments', key: d.soakKey } }); }
  if (n % 8 === 3 && n >= 6) {
    const k = n - 2; // n%8==3, so k%4==1: the AAPS temp basal created two ticks ago, ended early
    { const d = { ...aapsTb(k), duration: 12, durationInMilliseconds: 720000 }; await op('aaps.v3.put.TempBasal', async (arm) => ({ method: 'PUT', path: '/api/v3/treatments/' + d.identifier, body: d, headers: await V3(arm) }), { write: { coll: 'treatments', key: d.soakKey, act: 'update' } }); }
  }
  if (n % 48 === 23) { const d = aapsTb(n - 10); await op('aaps.v3.delete', async (arm) => ({ method: 'DELETE', path: '/api/v3/treatments/' + d.identifier, headers: await V3(arm) }), { write: { coll: 'treatments', key: d.soakKey, act: 'softdel' } }); }
  if (n % 6 === 2) { const d = aapsStatus(n); await op('aaps.v3.create.devicestatus', async (arm) => ({ method: 'POST', path: '/api/v3/devicestatus', body: d, headers: await V3(arm) }), { write: { coll: 'devicestatus', key: d.soakKey } }); }
  // edits and deletes by _id: each arm uses the _id its own reply gave
  const byId = (key, fn) => (arm) => { const id = arm.ids.get(key); return id ? fn(arm, id) : null; };
  if (n % 24 === 20) {
    const lastCarb = n - ((n - 9) % 36 + 36) % 36; const key = lastCarb >= 9 ? 'carb-' + lastCarb : 'tb-' + (n - 12);
    const base = v1Treatments(Number(key.split('-')[1])).find((x) => x.soakKey === key);
    if (base) await op('careportal.v1.put', byId(key, (arm, id) => ({ method: 'PUT', path: '/api/v1/treatments', body: { ...base, _id: id, notes: 'edited ' + n }, headers: SEC(arm) })), { write: { coll: 'treatments', key, act: 'update' } });
  }
  if (n % 24 === 22) { const key = 'tb-' + (n - 20); await op('careportal.v1.delete.treatment', byId(key, (arm, id) => ({ method: 'DELETE', path: '/api/v1/treatments/' + id, headers: SEC(arm) })), { write: { coll: 'treatments', key, act: 'delete' } }); }
  if (n % 24 === 21) { const key = 'tb-' + (n - 17); await sockOp('web.socket.dbUpdate', 'dbUpdate', (arm) => arm.ids.get(key) ? { collection: 'treatments', _id: arm.ids.get(key), data: { notes: 'ws edit ' + n } } : null, { coll: 'treatments', key, act: 'update' }); }
  if (n % 48 === 45) { const key = 'tb-' + (n - 15); await sockOp('web.socket.dbRemove', 'dbRemove', (arm) => arm.ids.get(key) ? { collection: 'treatments', _id: arm.ids.get(key) } : null, { coll: 'treatments', key, act: 'delete' }); }
  if (n % 72 === 30) { const key = 'ds-' + (n - 5); await op('careportal.v1.delete.devicestatus', byId(key, (arm, id) => ({ method: 'DELETE', path: '/api/v1/devicestatus/' + id, headers: SEC(arm) })), { write: { coll: 'devicestatus', key, act: 'delete' } }); }
  if (n % 72 === 60) { const key = 'sgv-' + (n - 31); await op('v1.delete.entry', byId(key, (arm, id) => ({ method: 'DELETE', path: '/api/v1/entries/' + id, headers: SEC(arm) })), { write: { coll: 'entries', key, act: 'delete' } }); }
  // profile, Loop remote command
  if (n === 0 || n % 288 === 144) { const p = profileDoc(n); await op('loop.profile.post', (arm) => ({ method: 'POST', path: '/api/v1/profile', body: p, headers: SEC(arm) }), { write: { coll: 'profile', key: p.soakKey } }); }
  if (n % 144 === 100) await op('loop.remote.override', (arm) => ({ method: 'POST', path: '/api/v2/notifications/loop', body: { eventType: 'Temporary Override', reason: 'Exercise', reasonDisplay: 'Exercise', duration: 60, notes: 'soak', enteredBy: 'caregiver' }, headers: SEC(arm) }));
}
async function reads (n, sub) {
  const now = simAt(n) + Math.round(sub * P / FOLLOW) + 60000;
  const tok = (arm) => 'token=' + arm.follower;
  const get = (label, p) => op(label, (arm) => ({ method: 'GET', path: p(arm) }));
  await get('loopfollow.entries288', (arm) => '/api/v1/entries.json?count=288&' + tok(arm));
  await get('loopfollow.devicestatus1', (arm) => '/api/v1/devicestatus.json?count=1&' + tok(arm));
  await get('loopfollow.treatments6h', (arm) => '/api/v1/treatments.json?find[created_at][$gte]=' + iso(now - 6 * 3600000) + '&' + tok(arm));
  await get('nightguard.entries2h', (arm) => '/api/v1/entries.json?find[date][$gt]=' + (now - 2 * 3600000) + '&count=40&' + tok(arm));
  await get('follower.treatments.count50', (arm) => '/api/v1/treatments.json?count=50&' + tok(arm));
  if (sub === 0) {
    if (n % 12 === 0) await get('loopfollow.profile.current', (arm) => '/api/v1/profile/current.json?' + tok(arm));
    if (n % 3 === 0) await get('nightguard.properties', (arm) => '/api/v2/properties?' + tok(arm));
    if (n % 12 === 6) await op('status.json', (arm) => ({ method: 'GET', path: '/api/v1/status.json', headers: SEC(arm) }));
    const oq = '/api/v1/treatments.json?find[enteredBy]=/openaps:\\/\\//';
    if (n % 3 === 0) await op('oref0.latest.count1?hash', (arm) => ({ method: 'GET', path: oq + '&count=1?' + arm.hash, headers: SEC(arm) }));
    if (n % 3 === 1) await get('oref0.latest.count1?token', (arm) => oq + '&count=1?' + tok(arm) + '&' + tok(arm));
    if (n % 3 === 2) await op('oref0.latest.count1 (control)', (arm) => ({ method: 'GET', path: oq + '&count=1', headers: SEC(arm) }));
    if (n % 24 === 0) {
      const lo = iso(now - 24 * 3600000); const hi = iso(now);
      await op('glupredkit.count0.treatments', (arm) => ({ method: 'GET', path: `/api/v1/treatments.json?count=0&find[created_at][$gte]=${lo}&find[created_at][$lte]=${hi}`, headers: SEC(arm) }));
      await op('glupredkit.count0.sgv', (arm) => ({ method: 'GET', path: `/api/v1/entries/sgv.json?count=0&find[dateString][$gte]=${lo}&find[dateString][$lte]=${hi}`, headers: SEC(arm) }));
      await op('glupredkit.count0.profile', (arm) => ({ method: 'GET', path: `/api/v1/profile?count=0&find%5Bcreated_at%5D%5B%24gte%5D=${lo}&find%5Bcreated_at%5D%5B%24lte%5D=${hi}`, headers: SEC(arm) }));
      await op('glupredkit.count0.devicestatus', (arm) => ({ method: 'GET', path: `/api/v1/devicestatus.json?count=0&find[created_at][$gte]=${lo}&find[created_at][$lte]=${hi}`, headers: SEC(arm) }));
    }
    if (n % 48 === 12) await op('count0.nowindow.entries', (arm) => ({ method: 'GET', path: '/api/v1/entries.json?count=0', headers: SEC(arm) }));
    if (n % 2 === 0) {
      await op('aaps.v3.treatments.recent', async (arm) => ({ method: 'GET', path: '/api/v3/treatments?limit=50&sort$desc=date&date$gte=' + (now - 3 * 3600000), headers: await V3(arm) }));
      await op('aaps.lastModified', async (arm) => ({ method: 'GET', path: '/api/v3/lastModified', headers: await V3(arm) }));
    }
  }
}

let stopping = false;
let wake = null; // resolves the current wait between ticks, so a stop does not wait for the next tick
const sleepUntil = (ms) => new Promise((r) => { const t = setTimeout(r, ms); wake = () => { clearTimeout(t); r(); }; });
const stop = (why) => { stopping = true; note(why + ': stopping'); if (wake) wake(); };
process.on('SIGTERM', () => stop('SIGTERM'));
process.on('SIGINT', () => stop('SIGINT'));

(async () => {
  for (const arm of ARMS) await subjects(arm);
  for (const arm of ARMS) { followerSocket(arm); await editorSocket(arm); }
  note(`start mode=${REAL ? 'realtime' : 'compressed'} ticks=${N} realTickMs=${Math.round(REAL_TICK)} simStart=${iso(simStart)} simEnd=${iso(simAt(N - 1))} arms=${ARMS.map((a) => a.name + '@' + a.base).join(',')}`);
  fs.writeFileSync(path.join(RUN, 'traffic.json'), JSON.stringify({ harness: 3, mode: REAL ? 'realtime' : 'compressed', ticks: N, realTickMs: REAL_TICK, followPerTick: FOLLOW, realStart: iso(realStart), simStart: iso(simStart), simEnd: iso(simAt(N - 1)), arms: ARMS.map((a) => ({ name: a.name, base: a.base, sock: a.sock })) }, null, 1));
  let late = 0;
  for (let n = 0; n < N && !stopping; n++) {
    tickN = n;
    for (let sub = 0; sub < FOLLOW && !stopping; sub++) {
      const due = realStart + n * REAL_TICK + sub * REAL_TICK / FOLLOW;
      const wait = due - Date.now();
      if (wait > 0) await sleepUntil(wait); else if (sub === 0 && wait < -REAL_TICK) late += 1;
      if (stopping) break;
      if (sub === 0) { for (const arm of ARMS) await drainRetries(arm); await writes(n); }
      await reads(n, sub);
      if (sub === 0 && n % 12 === 11) await Promise.all(ARMS.map((arm) => pageLoad(arm, n)));
    }
    fs.writeFileSync(path.join(RUN, 'state.json'), JSON.stringify({ t: new Date().toISOString(), n, N, simNow: iso(simAt(n)), lastSgv: Object.fromEntries(ARMS.map((a) => [a.name, a.lastSgv])), retryQueue: Object.fromEntries(ARMS.map((a) => [a.name, a.retry.length])), lateTicks: late }));
  }
  // last chance for queued writes, then leave the sockets a moment to deliver (skipped on a stop:
  // the servers may already be going down)
  for (let i = 0; i < 10 && !stopping && ARMS.some((a) => a.retry.length); i++) { for (const arm of ARMS) await drainRetries(arm); await new Promise((r) => setTimeout(r, 3000)); }
  if (!stopping) {
    await new Promise((r) => setTimeout(r, 15000));
    await Promise.all(ARMS.map((arm) => pageLoad(arm, N)));
  }
  fs.writeFileSync(path.join(RUN, 'done.json'), JSON.stringify({ t: new Date().toISOString(), ticks_run: tickN + 1, N, stopped_early: stopping, lateTicks: late, retry_left: Object.fromEntries(ARMS.map((a) => [a.name, a.retry.length])), diff_signatures: diffCount.size }));
  note('done');
  for (const arm of ARMS) { arm.fsock && arm.fsock.close(); arm.esock && arm.esock.close(); }
  process.exit(0);
})().catch((err) => { note('traffic stopped: ' + (err && err.stack)); process.exit(1); });
