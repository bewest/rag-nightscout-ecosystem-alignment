'use strict';
/*
 * Issue #8244 probe: do records written through API v1 appear in API v3
 * history (GET /api/v3/<collection>/history/<ms>)?
 *
 * Usage:
 *   node v1-writes-v3-history.js <cgm-remote-monitor tree with node_modules> <port> <mongodb uri>
 *   e.g. node v1-writes-v3-history.js ~/crm 17672 mongodb://127.0.0.1:27671/p8244_m
 *
 * Boots the tree's lib/server/server.js against the given MongoDB database
 * (which it drops first) with API_SECRET set and AUTH_DEFAULT_ROLES=denied,
 * creates an admin subject for a v3 token, notes a start time t0, writes
 * synthetic records, then asks v3 history for everything modified after t0.
 * The server is started in its own process group and killed by its PID.
 *
 * Arms (a v1 write; defect = absent from v3 history):
 *   treatments-v1    POST /api/v1/treatments
 *   entries-v1       POST /api/v1/entries
 *   devicestatus-v1  POST /api/v1/devicestatus
 *   treatments-v1put a treatment created through v3, then changed through
 *                    PUT /api/v1/treatments (the change should show in history)
 *   treatments-v1del a treatment created through v3, then deleted through
 *                    DELETE /api/v1/treatments/<id> (history should report it
 *                    as deleted, isValid false; v3's own DELETE does)
 * Controls, which must be present in history on every tree:
 *   <col>-v3         the same record written through POST /api/v3/<col>
 *   treatments-v3del a v3-created treatment deleted through v3 DELETE
 *   v1+srvModified   the treatments-v1 record after srvModified is set on it
 *                    directly in MongoDB: shows srvModified is the missing key
 * Also printed, not scored: whether a plain v3 search (GET /api/v3/<col>) finds
 * the v1 record (it should: the record exists, only history misses it), and
 * whether the stored v1 record has srvModified.
 * Liveness: /api/v1/status.json answers 200 before and after, and every write
 * answered 2xx.
 *
 * Exit status: 0 when every arm is present in history, 1 when any arm is
 * missing, 2 when a control is missing or liveness fails, 3 on a harness error.
 * No data leaves the machine.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const root = path.resolve(process.argv[2] || '.');
const port = Number(process.argv[3] || 17672);
const mongoUri = process.argv[4] || 'mongodb://127.0.0.1:27671/p8244';
const { MongoClient } = require(path.join(root, 'node_modules', 'mongodb'));

const SECRET = 'probe-secret-' + crypto.randomBytes(6).toString('hex');
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const BASE = `http://127.0.0.1:${port}`;
let server;
let ok2xx = true;

async function http (method, p, body, headers) {
  const r = await fetch(BASE + p, {
    method,
    headers: Object.assign({ 'content-type': 'application/json', 'api-secret': HASH }, headers || {}),
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  let json = null; try { json = await r.json(); } catch (e) { /* not json */ }
  return { status: r.status, json };
}
const check = (r, what) => { if (!(r.status >= 200 && r.status < 300)) { ok2xx = false; console.log('  write', what, 'answered', r.status, JSON.stringify(r.json)); } return r; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const result = (j) => (j && Array.isArray(j.result) ? j.result : Array.isArray(j) ? j : []);

async function boot () {
  const db = await MongoClient.connect(mongoUri);
  await db.db().dropDatabase();
  await db.close();
  server = spawn(process.execPath, ['lib/server/server.js'], {
    cwd: root, detached: true, stdio: ['ignore', 'ignore', 'ignore'],
    env: Object.assign({}, process.env, {
      MONGODB_URI: mongoUri, PORT: String(port), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true',
      NODE_ENV: 'production', API_SECRET: SECRET, AUTH_DEFAULT_ROLES: 'denied',
      ENABLE: 'careportal', DISPLAY_UNITS: 'mg/dl'
    })
  });
  for (let i = 0; i < 120; i++) {
    try { const r = await http('GET', '/api/v1/status.json'); if (r.status === 200) return; } catch (e) { /* booting */ }
    await sleep(500);
  }
  throw new Error('server did not answer on ' + BASE);
}

async function v3Token () {
  const name = 'probe' + Date.now();
  const c = await http('POST', '/api/v2/authorization/subjects', { name, roles: ['admin'] });
  if (c.status !== 200) throw new Error('subject create ' + c.status);
  for (let i = 0; i < 20; i++) {
    const l = await http('GET', '/api/v2/authorization/subjects');
    const s = (l.json || []).find((x) => x.name === name);
    if (s && s.accessToken) {
      const j = await http('GET', '/api/v2/authorization/request/' + s.accessToken);
      if (j.status === 200 && j.json && j.json.token) return j.json.token;
    }
    await sleep(250);
  }
  throw new Error('no v3 token');
}

async function main () {
  await boot();
  const v3 = { authorization: 'Bearer ' + (await v3Token()) };
  await sleep(1100);
  const t0 = Date.now();
  await sleep(50);
  const now = Date.now();
  const tag = (s) => 'probe-' + s;

  // v1 writes
  check(await http('POST', '/api/v1/treatments', { eventType: 'Carb Correction', created_at: new Date(now).toISOString(), carbs: 11, notes: tag('treatments-v1'), enteredBy: 'probe' }), 'treatments-v1');
  check(await http('POST', '/api/v1/entries', [{ type: 'sgv', sgv: 111, date: now, dateString: new Date(now).toISOString(), device: tag('entries-v1'), direction: 'Flat' }]), 'entries-v1');
  check(await http('POST', '/api/v1/devicestatus', { created_at: new Date(now).toISOString(), device: tag('devicestatus-v1'), uploaderBattery: 50 }), 'devicestatus-v1');

  // v3 controls
  check(await http('POST', '/api/v3/treatments', { eventType: 'Carb Correction', date: now + 1, utcOffset: 0, app: 'probe', device: 'probe', carbs: 12, notes: tag('treatments-v3') }, v3), 'treatments-v3');
  check(await http('POST', '/api/v3/entries', { type: 'sgv', sgv: 112, date: now + 1, utcOffset: 0, app: 'probe', device: tag('entries-v3'), direction: 'Flat' }, v3), 'entries-v3');
  check(await http('POST', '/api/v3/devicestatus', { date: now + 1, utcOffset: 0, app: 'probe', device: tag('devicestatus-v3'), uploaderBattery: 51 }, v3), 'devicestatus-v3');

  // v3-created treatments to change / delete. Created BEFORE t1; history is then asked from t1.
  const mk = async (s, ms) => {
    const r = check(await http('POST', '/api/v3/treatments', { eventType: 'Note', date: ms, utcOffset: 0, app: 'probe', device: 'probe', notes: tag(s) }, v3), s);
    return r.json && (r.json.identifier || (r.json.result && r.json.result.identifier));
  };
  const idPut = await mk('treatments-v1put', now + 2);
  const idDel = await mk('treatments-v1del', now + 3);
  const idV3Del = await mk('treatments-v3del', now + 4);
  await sleep(1100);
  const t1 = Date.now();
  await sleep(50);

  // v1 PUT: read the stored doc through v1 (as a v1 client would) and send it back changed
  const db = await MongoClient.connect(mongoUri);
  const tcol = db.db().collection('treatments');
  const putDoc = await tcol.findOne({ identifier: idPut });
  const v1view = result((await http('GET', '/api/v1/treatments.json?find[notes]=' + encodeURIComponent(tag('treatments-v1put')))).json);
  const body = Object.assign({}, v1view[0] || { _id: String(putDoc._id) }, { notes: tag('treatments-v1put') + ' changed' });
  delete body.srvModified; delete body.srvCreated; // a v1 client that does not know v3 fields
  check(await http('PUT', '/api/v1/treatments', body), 'treatments-v1put');
  const delDoc = await tcol.findOne({ identifier: idDel });
  check(await http('DELETE', '/api/v1/treatments/' + String(delDoc._id)), 'treatments-v1del');
  check(await http('DELETE', '/api/v3/treatments/' + idV3Del, undefined, v3), 'treatments-v3del');
  await sleep(300);

  const hist = {};
  for (const col of ['treatments', 'entries', 'devicestatus']) {
    const h = await http('GET', `/api/v3/${col}/history/${t0}?limit=1000`, undefined, v3);
    if (h.status !== 200) { console.log('history', col, h.status); ok2xx = false; }
    hist[col] = { t0: result(h.json) };
  }
  const h1 = await http('GET', `/api/v3/treatments/history/${t1}?limit=1000`, undefined, v3);
  hist.treatments.t1 = result(h1.json);
  const has = (list, s) => list.find((d) => (d.notes && String(d.notes).startsWith(tag(s))) || d.device === tag(s));

  const rows = [];
  for (const col of ['treatments', 'entries', 'devicestatus']) {
    const search = result((await http('GET', `/api/v3/${col}?limit=1000&sort$desc=date`, undefined, v3)).json);
    const storedV1 = await db.db().collection(col).findOne(col === 'treatments' ? { notes: tag(col + '-v1') } : { device: tag(col + '-v1') });
    rows.push({ name: col + '-v1', control: false, present: !!has(hist[col].t0, col + '-v1'),
      extra: `v3 search finds it: ${!!has(search, col + '-v1')}; stored srvModified: ${storedV1 ? !!storedV1.srvModified : 'not stored'}` });
    rows.push({ name: col + '-v3', control: true, present: !!has(hist[col].t0, col + '-v3'), extra: '' });
  }
  const put = has(hist.treatments.t1, 'treatments-v1put');
  const putStored = await tcol.findOne({ notes: tag('treatments-v1put') + ' changed' });
  rows.push({ name: 'treatments-v1put', control: false, present: !!(put && /changed$/.test(put.notes)),
    extra: `stored changed: ${!!putStored}; stored srvModified after: ${putStored ? putStored.srvModified : '-'} (before: ${putDoc.srvModified}); identifier kept: ${putStored ? putStored.identifier === idPut : '-'}` });
  const del = has(hist.treatments.t1, 'treatments-v1del');
  rows.push({ name: 'treatments-v1del', control: false, present: !!(del && del.isValid === false),
    extra: `still stored: ${!!(await tcol.findOne({ identifier: idDel }))}` });
  const v3del = has(hist.treatments.t1, 'treatments-v3del');
  rows.push({ name: 'treatments-v3del', control: true, present: !!(v3del && v3del.isValid === false), extra: '' });
  // Mechanism control: stamp srvModified on the v1 treatment by hand; it must then appear.
  await tcol.updateOne({ notes: tag('treatments-v1') }, { $set: { srvModified: Date.now() } });
  const hs = result((await http('GET', `/api/v3/treatments/history/${t0}?limit=1000`, undefined, v3)).json);
  rows.push({ name: 'v1+srvModified', control: true, present: !!has(hs, 'treatments-v1'), extra: 'the v1 treatment after setting srvModified in the database' });
  await db.close();

  let defect = false, badControl = false;
  for (const r of rows) {
    console.log(`${r.control ? 'control' : 'arm    '} ${r.name.padEnd(17)} in v3 history: ${r.present}${r.extra ? '  (' + r.extra + ')' : ''}`);
    if (r.control && !r.present) badControl = true;
    if (!r.control && !r.present) defect = true;
  }
  const live = await http('GET', '/api/v1/status.json');
  console.log('liveness after arms:', live.status, 'writes all 2xx:', ok2xx);
  if (live.status !== 200 || !ok2xx) badControl = true;
  return badControl ? 2 : defect ? 1 : 0;
}

main().then((code) => { console.log('exit', code); finish(code); })
  .catch((e) => { console.error('harness error:', e.stack || e.message); finish(3); });

function finish (code) {
  if (server && server.pid) { try { process.kill(-server.pid, 'SIGTERM'); } catch (e) { /* gone */ } }
  process.exit(code);
}
