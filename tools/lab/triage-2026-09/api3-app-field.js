'use strict';
/*
 * BF-136 probe: can API v3 write to a treatment that was created through
 * API v1 (so it has no `app`, `device` or `isValid` field)?
 *
 * Usage:
 *   node api3-app-field.js <cgm-remote-monitor tree with node_modules> <port> <mongodb uri>
 *   e.g. node api3-app-field.js ~/crm 17922 mongodb://127.0.0.1:27921/p136
 *
 * Boots the tree's lib/server/server.js against the given MongoDB database
 * (which it drops first) with API_SECRET set and AUTH_DEFAULT_ROLES=denied,
 * creates an admin subject for a v3 token and writes synthetic records only.
 * The server is started in its own process group and killed by its PID.
 *
 * Arms (defect = the write is refused with 400):
 *   dedup-<a>-<b>   a careportal-shaped v1 treatment with <a> g, then an
 *                   AndroidAPS-shaped v3 POST (app, isValid true, no
 *                   identifier) with <b> g at the same time. AndroidAPS picks
 *                   eventType from the amount (< 12 g Carb Correction, else
 *                   Meal Bolus), and v3 deduplicates a treatment without
 *                   identifier on created_at + eventType. Printed: the status,
 *                   the message, and what is stored at that time afterwards
 *                   (how many records, whose carbs, whether the careportal
 *                   notes survive).
 *   put-noapp       v3 PUT to a v1 record without app       (400 is expected: v3 requires app)
 *   put-app         v3 PUT to a v1 record with app
 *   put-app-device  v3 PUT to a v1 record with app and device
 *   patch-carbs     v3 PATCH {carbs} to a v1 record
 *   patch-aaps      v3 PATCH {carbs, isValid: true, eventType} (the AndroidAPS update shape)
 *   patch-app       v3 PATCH {app} to a v1 record
 *   dedup-v1date    as dedup-20-20, with a v1 record that also carries date
 * Controls (must answer the same on every tree):
 *   v3 create 201; v3 PUT keeping app 200; v3 PATCH {carbs} 200;
 *   changing an existing app / device through PUT, PATCH or dedup POST 400;
 *   PATCH isValid false on a v1 record 400 (a delete needs DELETE);
 *   moving a v1 record's time (date other than its created_at) by PATCH or PUT 400;
 *   PATCH srvCreated on a v1 record 400; PATCH identifier on a v1 record 400.
 * Liveness: /api/v1/status.json answers 200 before and after.
 *
 * Exit status: 0 when every arm succeeds, 1 when any arm is refused, 2 when a
 * control answers otherwise or liveness fails, 3 on a harness error.
 * No data leaves the machine.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const root = path.resolve(process.argv[2] || '.');
const port = Number(process.argv[3] || 17922);
const mongoUri = process.argv[4] || 'mongodb://127.0.0.1:27921/p136';
const { MongoClient } = require(path.join(root, 'node_modules', 'mongodb'));

const SECRET = 'probe-secret-' + crypto.randomBytes(6).toString('hex');
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const BASE = `http://127.0.0.1:${port}`;
let server;

async function http (method, p, body, headers) {
  const r = await fetch(BASE + p, {
    method,
    headers: Object.assign({ 'content-type': 'application/json', 'api-secret': HASH }, headers || {}),
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  let json = null; try { json = await r.json(); } catch (e) { /* not json */ }
  return { status: r.status, json };
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const msg = (j) => (j && (j.message || (j.result && j.result.message))) || '';
const idOf = (j) => j && (j.identifier || (j.result && j.result.identifier));

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
  const db = await MongoClient.connect(mongoUri);
  const tcol = db.db().collection('treatments');
  const base = Date.now() - 3600 * 1000;
  let slot = 0;
  const nextT = () => base + (slot++) * 120000 + 123; // ms, as AndroidAPS sends
  const iso = (ms) => new Date(ms).toISOString();
  const evFor = (g) => (g < 12 ? 'Carb Correction' : 'Meal Bolus');
  let arms = 0, armsFailed = 0, controlsFailed = 0;

  const v1Carbs = async (T, g, extra) => {
    const r = await http('POST', '/api/v1/treatments', Object.assign({ eventType: evFor(g), created_at: iso(T), carbs: g, enteredBy: 'careportal-probe', notes: 'careportal ' + g + ' g' }, extra || {}));
    if (r.status !== 200) throw new Error('v1 create ' + r.status);
    const doc = await tcol.findOne({ created_at: iso(T) });
    return doc;
  };
  const arm = (name, r, extra) => {
    arms++;
    const pass = r.status >= 200 && r.status < 300;
    if (!pass) armsFailed++;
    console.log(`  ARM     ${pass ? 'ok  ' : 'FAIL'} ${name.padEnd(16)} ${r.status} ${msg(r.json)}${extra ? '  ' + extra : ''}`);
  };
  const control = (name, r, want) => {
    const pass = r.status === want;
    if (!pass) controlsFailed++;
    console.log(`  CONTROL ${pass ? 'ok  ' : 'FAIL'} ${name.padEnd(28)} ${r.status} (want ${want}) ${msg(r.json)}`);
  };

  // the shape of a v1 record as v3 sees it
  {
    const T = nextT();
    const d = await v1Carbs(T, 20);
    console.log('stored v1 record fields:', Object.keys(d).sort().join(','));
  }

  // dedup arms
  console.log('dedup: careportal v1 <a> g, then AndroidAPS-shaped v3 POST <b> g at the same time');
  for (const [a, b] of [[20, 20], [20, 30], [45, 60], [20, 5], [5, 5], [8, 10], [5, 20]]) {
    const T = nextT();
    await v1Carbs(T, a);
    const r = await http('POST', '/api/v3/treatments', {
      eventType: evFor(b), date: T, utcOffset: 0, app: 'AAPS', isValid: true, carbs: b, pumpId: 1000 + slot, pumpType: 'USER', pumpSerial: 'probe'
    }, v3);
    const after = await tcol.find({ $or: [{ created_at: iso(T) }, { date: T }] }).toArray();
    const summary = after.map((x) => `${x.eventType}/${x.carbs}g/${x.app ? 'app=' + x.app : 'no-app'}/${x.notes ? 'notes' : 'no-notes'}`).join(' + ');
    const dedup = r.json && r.json.isDeduplication ? 'dedup' : (r.status === 201 ? 'insert' : '-');
    arm(`dedup-${a}-${b}`, r, `${dedup}; stored: ${after.length} record(s) ${summary}`);
  }

  {
    // a v1 uploader that also sends date (the careportal does not)
    const T = nextT();
    await v1Carbs(T, 20, { date: T });
    const r = await http('POST', '/api/v3/treatments', { eventType: 'Meal Bolus', date: T, utcOffset: 0, app: 'AAPS', isValid: true, carbs: 20 }, v3);
    arm('dedup-v1date', r, r.json && r.json.isDeduplication ? 'dedup' : '');
  }

  // PUT / PATCH arms on v1-born records
  console.log('PUT / PATCH to a v1-born record');
  {
    const T = nextT(); const d = await v1Carbs(T, 20);
    const r = await http('PUT', '/api/v3/treatments/' + d._id, { eventType: 'Meal Bolus', date: T, utcOffset: 0, carbs: 25 }, v3);
    console.log(`  EXPECT  ${r.status === 400 ? 'ok  ' : '??  '} put-noapp        ${r.status} ${msg(r.json)} (v3 requires app on PUT)`);
  }
  for (const [name, extra] of [['put-app', { app: 'AAPS' }], ['put-app-device', { app: 'AAPS', device: 'probe-device' }]]) {
    const T = nextT(); const d = await v1Carbs(T, 20);
    const r = await http('PUT', '/api/v3/treatments/' + d._id, Object.assign({ eventType: 'Meal Bolus', date: T, utcOffset: 0, carbs: 25 }, extra), v3);
    const s = await tcol.findOne({ _id: d._id });
    arm(name, r, `stored carbs ${s && s.carbs} app ${s && s.app}`);
  }
  for (const [name, body] of [['patch-carbs', { carbs: 25 }], ['patch-aaps', { carbs: 25, isValid: true, eventType: 'Meal Bolus', identifier: null }], ['patch-app', { app: 'AAPS' }]]) {
    const T = nextT(); const d = await v1Carbs(T, 20);
    if (body.identifier === null) body.identifier = String(d._id);
    const r = await http('PATCH', '/api/v3/treatments/' + d._id, body, v3);
    const s = await tcol.findOne({ _id: d._id });
    arm(name, r, `stored carbs ${s && s.carbs} app ${s && s.app}`);
  }

  // controls
  console.log('controls');
  {
    const T = nextT();
    const c = await http('POST', '/api/v3/treatments', { eventType: 'Meal Bolus', date: T, utcOffset: 0, app: 'AAPS', device: 'dev-A', isValid: true, carbs: 20 }, v3);
    control('v3 create', c, 201);
    const id = idOf(c.json);
    control('v3 PUT same app', await http('PUT', '/api/v3/treatments/' + id, { eventType: 'Meal Bolus', date: T, utcOffset: 0, app: 'AAPS', device: 'dev-A', carbs: 21 }, v3), 200);
    control('v3 PATCH carbs', await http('PATCH', '/api/v3/treatments/' + id, { carbs: 22 }, v3), 200);
    control('v3 PUT other app', await http('PUT', '/api/v3/treatments/' + id, { eventType: 'Meal Bolus', date: T, utcOffset: 0, app: 'other', device: 'dev-A', carbs: 21 }, v3), 400);
    control('v3 PATCH other app', await http('PATCH', '/api/v3/treatments/' + id, { app: 'other' }, v3), 400);
    control('v3 PATCH other device', await http('PATCH', '/api/v3/treatments/' + id, { device: 'dev-B' }, v3), 400);
  }
  {
    const T = nextT(); await v1Carbs(T, 20, { app: 'someapp', date: T });
    control('dedup onto v1 app=someapp', await http('POST', '/api/v3/treatments', { eventType: 'Meal Bolus', date: T, utcOffset: 0, app: 'AAPS', carbs: 20 }, v3), 400);
  }
  {
    const T = nextT(); const d = await v1Carbs(T, 20, { device: 'dev-A' });
    control('PATCH other device on v1', await http('PATCH', '/api/v3/treatments/' + d._id, { device: 'dev-B' }, v3), 400);
  }
  {
    const T = nextT(); const d = await v1Carbs(T, 20);
    const before = JSON.stringify(await tcol.findOne({ _id: d._id }));
    control('PATCH isValid false on v1', await http('PATCH', '/api/v3/treatments/' + d._id, { isValid: false }, v3), 400);
    control('PATCH other date on v1', await http('PATCH', '/api/v3/treatments/' + d._id, { date: T + 60000 }, v3), 400);
    control('PUT other date on v1', await http('PUT', '/api/v3/treatments/' + d._id, { eventType: 'Meal Bolus', date: T + 60000, utcOffset: 0, app: 'AAPS', carbs: 20 }, v3), 400);
    control('PATCH srvCreated on v1', await http('PATCH', '/api/v3/treatments/' + d._id, { srvCreated: 1 }, v3), 400);
    control('PATCH identifier on v1', await http('PATCH', '/api/v3/treatments/' + d._id, { identifier: 'other-id' }, v3), 400);
    control('PATCH subject on v1', await http('PATCH', '/api/v3/treatments/' + d._id, { subject: 'someone' }, v3), 400);
    const untouched = JSON.stringify(await tcol.findOne({ _id: d._id })) === before;
    if (!untouched) controlsFailed++;
    console.log(`  CONTROL ${untouched ? 'ok  ' : 'FAIL'} v1 record unchanged by refused PATCHes`);
  }

  const live = await http('GET', '/api/v1/status.json');
  if (live.status !== 200) { controlsFailed++; console.log('  liveness after', live.status); }
  await db.close();
  console.log(`arms ${arms - armsFailed}/${arms} succeeded; controls failed ${controlsFailed}`);
  return controlsFailed ? 2 : (armsFailed ? 1 : 0);
}

main().then((c) => finish(c), (e) => { console.error('harness error:', e && e.stack || e); finish(3); });
function finish (code) {
  if (server && server.pid) { try { process.kill(-server.pid, 'SIGTERM'); } catch (e) { /* gone */ } }
  process.exit(code);
}
