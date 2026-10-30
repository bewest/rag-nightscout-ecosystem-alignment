'use strict';
// Part 2: replay a single-tenant site's traffic against one running arm and
// measure it per hour. Real time by default (SCALE=1): the run.sh driver runs
// every arm in parallel, so no part of the server's own timing (heartbeat,
// debounce, the dataloader's 15-minute incremental window) is compressed.
//
// Env: CRM_DIR (driver + socket.io-client come from it), BASE (server URL),
//      SECRET_FILE, MONGODB_URI, METRICS (the preload's jsonl), OUT (results
//      jsonl), ARM (label), EXPECT (cache|bypass), HOURS (default 3),
//      SCALE (time compression, default 1; >1 only for smoke tests).
// Synthetic data only. The secret is read from SECRET_FILE and never written.

const fs = require('fs');
const path = require('path');
const C = require('./common');
const { io } = require(path.join(C.CRM_DIR, 'node_modules/socket.io-client'));
const BSON = require(path.join(C.CRM_DIR, 'node_modules/bson'));

const BASE = process.env.BASE;
const SECRET = fs.readFileSync(process.env.SECRET_FILE, 'utf8').trim();
const HASH = C.secretHash(SECRET);
const ARM = process.env.ARM || 'arm';
const EXPECT = process.env.EXPECT;
const HOURS = +(process.env.HOURS || 3);
const SCALE = +(process.env.SCALE || 1);
const OUT = process.env.OUT;
const METRICS = process.env.METRICS;
const SIM_MIN = C.MIN / SCALE;
const SIM_HOUR = C.HOUR / SCALE;

const requests = [];
function log (rec) { fs.appendFileSync(OUT, JSON.stringify(rec) + '\n'); }

async function call (cls, name, method, url, body, headers) {
  const t = Date.now();
  const h0 = process.hrtime.bigint();
  let status = 0; let bytes = 0; let err = null;
  try {
    const res = await fetch(BASE + url, { method, headers: Object.assign({ 'content-type': 'application/json' }, headers), body: body ? JSON.stringify(body) : undefined });
    status = res.status;
    bytes = (await res.arrayBuffer()).byteLength;
  } catch (e) { err = String(e && e.message || e); }
  const ms = Number(process.hrtime.bigint() - h0) / 1e6;
  const rec = { kind: 'req', t, cls, name, method, status, bytes, ms, err };
  requests.push(rec);
  log(rec);
  return rec;
}

const v1 = { 'api-secret': HASH };
let jwt = null;
const v3 = () => ({ authorization: 'Bearer ' + jwt });

async function getJwt () {
  const name = 'cv-uploader';
  let r = await fetch(BASE + '/api/v2/authorization/subjects', { method: 'POST', headers: Object.assign({ 'content-type': 'application/json' }, v1), body: JSON.stringify({ name, roles: ['admin'] }) });
  if (r.status >= 300) throw new Error('subject create ' + r.status);
  r = await fetch(BASE + '/api/v2/authorization/subjects', { headers: v1 });
  const subj = (await r.json()).find(s => s.name === name);
  r = await fetch(BASE + '/api/v2/authorization/request/' + subj.accessToken);
  return (await r.json()).token;
}

async function serverSample (db, label) {
  const c = await C.serverCounters(db);
  // The sample's own reply leaves through network.bytesOut: subtract it later.
  const reply = await db.admin().command({ serverStatus: 1 });
  // Two serverStatus replies per sample (the counters read and this one).
  c.sampleReplyBytes = 2 * BSON.calculateObjectSize(reply);
  c.label = label;
  let m = null;
  try {
    const lines = fs.readFileSync(METRICS, 'utf8').trim().split('\n');
    m = JSON.parse(lines[lines.length - 1]);
  } catch (e) { m = null; }
  c.preload = m;
  log(Object.assign({ kind: 'sample' }, c));
  return c;
}

// Control: with the cache, a follower's simple GET is served from memory; with
// the bypass it reaches MongoDB. Red if the arm does not behave as declared.
async function bypassCheck (db) {
  const before = (await C.serverCounters(db)).opcounters.query;
  for (let i = 0; i < 20; i++) await call('check', 'check-entries-sgv', 'GET', '/api/v1/entries/sgv.json?count=1', null, v1);
  for (let i = 0; i < 20; i++) await call('check', 'check-devicestatus', 'GET', '/api/v1/devicestatus.json?count=1', null, v1);
  const after = (await C.serverCounters(db)).opcounters.query;
  const q = after - before;
  const ok = EXPECT === 'cache' ? q < 10 : q >= 40;
  const msg = `bypass check (${ARM}, expect ${EXPECT}): 40 simple v1 GETs caused ${q} MongoDB queries: ` + (ok ? 'PASS' : (EXPECT === 'cache' ? 'FAIL: expected them served from memory' : 'FAIL: expected every one to read MongoDB'));
  log({ kind: 'check', t: Date.now(), queries: q, ok, msg });
  console.log(msg);
  return ok;
}

function every (ms, offset, fn, timers) {
  const t = setTimeout(function first () {
    fn();
    timers.push(setInterval(fn, ms));
  }, offset);
  timers.push(t);
}

async function main () {
  const client = await C.MongoClient.connect(process.env.MONGODB_URI, { appName: 'cv-probe', maxPoolSize: 1 });
  const db = client.db();
  jwt = await getJwt();
  const ok = await bypassCheck(db);
  if (process.argv.includes('--check-only')) { await client.close(); process.exit(ok ? 0 : 1); }
  if (!ok) { await client.close(); process.exit(1); }

  // The website: one socket, authorized with the secret, as the browser client does.
  let socketUpdates = 0; let socketBytes = 0;
  const socket = io(BASE, { transports: ['websocket'] });
  socket.on('connect', () => socket.emit('authorize', { client: 'web', secret: HASH, history: 48 }, () => {}));
  socket.on('dataUpdate', (d) => { socketUpdates += 1; socketBytes += Buffer.byteLength(JSON.stringify(d)); });

  const t0 = Date.now();
  await serverSample(db, 'h0');
  const timers = [];
  let tick = 0;

  // Uploader: an entry and a devicestatus every 5 min; devicestatus alternates v1 and v3.
  every(5 * SIM_MIN, 5 * 1000 / SCALE, async function upload () {
    const t = Date.now();
    const n = tick++;
    await call('post', 'v1-entries', 'POST', '/api/v1/entries', [C.entry(t)], v1);
    const ds = C.devicestatus(t);
    if (n % 2 === 0) await call('post', 'v1-devicestatus', 'POST', '/api/v1/devicestatus', ds, v1);
    else await call('post', 'v3-devicestatus', 'POST', '/api/v3/devicestatus', Object.assign(ds, { date: t, app: 'cv-lab' }), v3());
  }, timers);

  // Occasional treatments: one every 40 min, alternating v1 and v3.
  let txn = 0;
  every(40 * SIM_MIN, 7 * SIM_MIN, async function treat () {
    const t = Date.now();
    const doc = C.treatment(t, txn);
    if (txn++ % 2 === 0) await call('post', 'v1-treatments', 'POST', '/api/v1/treatments', doc, v1);
    else await call('post', 'v3-treatments', 'POST', '/api/v3/treatments', Object.assign(doc, { date: t, app: 'cv-lab' }), v3());
  }, timers);

  // Follower 1: latest reading every minute (watch-face style).
  every(SIM_MIN, 11 * 1000 / SCALE, () => call('get', 'f1-entries-sgv-1', 'GET', '/api/v1/entries/sgv.json?count=1', null, v1), timers);

  // Follower 2: every 5 min, a day of readings plus latest devicestatus and treatments, simple queries.
  every(5 * SIM_MIN, 37 * 1000 / SCALE, async () => {
    await call('get', 'f2-entries-sgv-288', 'GET', '/api/v1/entries/sgv.json?count=288', null, v1);
    await call('get', 'f2-devicestatus-1', 'GET', '/api/v1/devicestatus.json?count=1', null, v1);
    await call('get', 'f2-treatments-10', 'GET', '/api/v1/treatments.json?count=10', null, v1);
  }, timers);

  // Follower 3: every 5 min, time-bounded queries (find[...]), which the cache never serves.
  every(5 * SIM_MIN, 97 * 1000 / SCALE, async () => {
    const since = Date.now() - 24 * C.HOUR;
    await call('get', 'f3-entries-find-24h', 'GET', '/api/v1/entries.json?count=300&find[date][$gte]=' + since, null, v1);
    await call('get', 'f3-treatments-find-24h', 'GET', '/api/v1/treatments.json?find[created_at][$gte]=' + encodeURIComponent(new Date(since).toISOString()), null, v1);
    await call('get', 'f3-devicestatus-2', 'GET', '/api/v1/devicestatus.json?count=2', null, v1);
  }, timers);

  for (let h = 1; h <= HOURS; h++) {
    await new Promise(r => setTimeout(r, t0 + h * SIM_HOUR - Date.now()));
    const s = await serverSample(db, 'h' + h);
    log({ kind: 'socket', t: Date.now(), hour: h, updates: socketUpdates, bytes: socketBytes, connected: socket.connected });
    console.log(`${ARM} hour ${h} done: ${requests.length} requests, socket updates ${socketUpdates}, connections ${s.connections}`);
  }
  timers.forEach(t => { clearTimeout(t); clearInterval(t); });
  socket.close();
  await client.close();
  setTimeout(() => process.exit(0), 200);
}

main().catch(err => { console.error(err); process.exit(2); });
