#!/usr/bin/env node
'use strict';
/*
 * probe-v3-late-mills.js - BF-146 (and BF-133): does a treatment or device
 * status written through API v3 with a time in the past take part in what the
 * server computes from memory, as the same record written through API v1 does?
 *
 *   node probe-v3-late-mills.js <cgm-remote-monitor tree with node_modules> <port> <mongodb uri>
 *   e.g. node probe-v3-late-mills.js externals/work/crm-rc-018-soak 17950 mongodb://127.0.0.1:27958/p146_test
 *
 * Boots the tree's lib/server/server.js against the given MongoDB database
 * (which it drops first; the database name must contain "test") with
 * API_SECRET set, AUTH_DEFAULT_ROLES=denied and ENABLE=careportal iob cob.
 * Creates an admin subject for a v3 token and writes synthetic records only.
 * The server runs in its own process group and is stopped by its PID.
 *
 * Mechanism: the v1 write paths add `mills` to a record before it enters the
 * server's in-memory cache; before BF-146's fix the v3 path did not. Once the
 * cache holds 20 or more records of a kind, the dataloader refetches only the
 * last 15 minutes from MongoDB, so a record dated earlier than that stays in
 * memory as the copy without `mills`. The IOB and COB plugins count only a
 * treatment whose `mills` is before the time asked about, and the in-memory
 * GET /api/v1/devicestatus sorts by `mills`.
 *
 * Setup: a profile, and 24 v1 notes dated 2 h ago, so the treatments cache is
 * past the dataloader's full-load threshold. No device status carries IOB or
 * COB, so /api/v2/properties reports the treatment-based values.
 *
 * Arms (defect = the arm fails):
 *   iob-v3-late   a v3 bolus of 1 U dated 40 min ago raises the server's IOB
 *   cob-v3-late   v3 carbs of 30 g dated 40 min ago give a COB above 0
 *   ds-v3-late    after 24 v1 device statuses dated 60 to 37 min ago, a v3
 *                 device status dated 20 min ago is first in the default
 *                 GET /api/v1/devicestatus.json (served from memory)
 * Controls (must pass on every tree):
 *   iob-v1-late   a v1 bolus of 1 U dated 41 min ago raises the IOB
 *   iob-v3-now    a v3 bolus of 1 U dated 1 min ago raises the IOB
 *   ds-v1-late    a v1 device status dated 19 min ago is then first
 *   liveness      /api/v1/status.json answers 200 before and after
 * Printed only: cob.lastCarbs after the v3 carbs, and the IOB, COB and device
 * status order after a server restart (every record then comes from MongoDB).
 *
 * Exit status: 0 when every arm passes, 1 when an arm fails, 2 when a control
 * fails, 3 on a harness error. No data leaves the machine.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const root = path.resolve(process.argv[2] || '.');
const port = Number(process.argv[3] || 17950);
const mongoUri = process.argv[4] || 'mongodb://127.0.0.1:27958/p146_test';
if (!/test/.test(new URL(mongoUri).pathname)) { console.log('the database name must contain "test"'); process.exit(3); }
const { MongoClient } = require(path.join(root, 'node_modules', 'mongodb'));

const SECRET = 'probe-secret-' + crypto.randomBytes(6).toString('hex');
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const BASE = `http://127.0.0.1:${port}`;
const MIN = 60000;
const RELOAD_WAIT = 3000; // a write's reload is debounced, with data promised within 5 s
let server;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function http (method, p, body, headers) {
  const r = await fetch(BASE + p, {
    method,
    headers: Object.assign({ 'content-type': 'application/json', 'api-secret': HASH }, headers || {}),
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  let json = null; try { json = await r.json(); } catch (e) { /* not json */ }
  return { status: r.status, json };
}

async function start () {
  server = spawn(process.execPath, ['lib/server/server.js'], {
    cwd: root, detached: true, stdio: ['ignore', 'ignore', 'ignore'],
    env: Object.assign({}, process.env, {
      MONGODB_URI: mongoUri, PORT: String(port), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true',
      NODE_ENV: 'production', API_SECRET: SECRET, AUTH_DEFAULT_ROLES: 'denied',
      ENABLE: 'careportal iob cob', DISPLAY_UNITS: 'mg/dl', TZ: 'UTC'
    })
  });
  for (let i = 0; i < 120; i++) {
    try { if ((await http('GET', '/api/v1/status.json')).status === 200) return; } catch (e) { /* not up */ }
    await sleep(500);
  }
  throw new Error('server did not answer');
}
async function stop () { try { process.kill(-server.pid, 'SIGTERM'); } catch (e) { /* gone */ } await sleep(1500); }

async function v3token () {
  const name = 'probe146' + Date.now();
  await http('POST', '/api/v2/authorization/subjects', { name, roles: ['admin'] });
  for (let i = 0; i < 20; i++) {
    const l = await http('GET', '/api/v2/authorization/subjects');
    const s = (l.json || []).find((x) => x.name === name);
    if (s && s.accessToken) {
      const j = await http('GET', '/api/v2/authorization/request/' + s.accessToken);
      if (j.json && j.json.token) return j.json.token;
    }
    await sleep(250);
  }
  throw new Error('no v3 token');
}

async function props () {
  await sleep(RELOAD_WAIT);
  const j = (await http('GET', '/api/v2/properties/iob,cob')).json || {};
  const iob = j.iob && typeof j.iob.iob === 'number' ? j.iob.iob : 0;
  const cob = j.cob && typeof j.cob.cob === 'number' ? j.cob.cob : 0;
  const last = j.cob && j.cob.lastCarbs ? j.cob.lastCarbs.notes || null : null;
  return { iob, cob, last, iobSource: j.iob && j.iob.source };
}
async function dsOrder () {
  await sleep(RELOAD_WAIT);
  const r = await http('GET', '/api/v1/devicestatus.json');
  return (r.json || []).map((d) => d.device);
}

(async () => {
  const results = [];
  const record = (kind, name, ok, detail) => { results.push({ kind, name, ok }); console.log(`${kind.padEnd(7)} ${name.padEnd(12)} ${ok ? 'PASS' : 'FAIL'}  ${detail}`); };

  const c = await MongoClient.connect(mongoUri); await c.db().dropDatabase(); await c.close();
  await start();
  const live0 = (await http('GET', '/api/v1/status.json')).status;
  const V3 = { authorization: 'Bearer ' + await v3token() };
  const now = Date.now();
  const iso = (ms) => new Date(ms).toISOString();
  const v3 = (col, mAgo, extra) => http('POST', '/api/v3/' + col, Object.assign({ identifier: crypto.randomUUID(), date: now - mAgo * MIN, utcOffset: 0, device: 'probe146', app: 'AAPS', isValid: true }, extra), V3);
  const v1 = (col, docs) => http('POST', '/api/v1/' + col, docs);

  const prof = { defaultProfile: 'Default', startDate: iso(now - 864e5), mills: now - 864e5, units: 'mg/dl', store: { Default: { dia: 3, carbratio: [{ time: '00:00', value: 10 }], carbs_hr: 30, delay: 20, sens: [{ time: '00:00', value: 50 }], basal: [{ time: '00:00', value: 1 }], target_low: [{ time: '00:00', value: 100 }], target_high: [{ time: '00:00', value: 120 }], timezone: 'UTC', units: 'mg/dl' } } };
  const setup = [(await v1('profile', prof)).status];
  const notes = []; for (let i = 0; i < 24; i++) notes.push({ eventType: 'Note', notes: 'probe146 filler ' + i, created_at: iso(now - (120 + i) * MIN), enteredBy: 'probe146' });
  setup.push((await v1('treatments', notes)).status);
  let p = await props();
  console.log(`setup   profile ${setup[0]}, 24 v1 notes ${setup[1]}; IOB ${p.iob} COB ${p.cob} (iob source ${p.iobSource || '-'})`);
  if (setup.some((s) => s !== 200)) throw new Error('setup writes refused: ' + setup.join(','));

  let before = p.iob;
  let r = await v3('treatments', 40, { eventType: 'Correction Bolus', insulin: 1, type: 'SMB', notes: 'probe146 v3 bolus -40' });
  p = await props();
  record('arm', 'iob-v3-late', r.status === 201 && p.iob - before > 0.3, `v3 1 U dated 40 min ago: ${r.status}; IOB ${before} -> ${p.iob}`);

  r = await v3('treatments', 40, { eventType: 'Carb Correction', carbs: 30, notes: 'probe146 v3 carbs -40' });
  p = await props();
  record('arm', 'cob-v3-late', r.status === 201 && p.cob > 0, `v3 30 g dated 40 min ago: ${r.status}; COB ${p.cob}`);
  console.log(`printed cob.lastCarbs: ${p.last === null ? '(none)' : p.last}`);

  before = p.iob;
  r = await v1('treatments', [{ eventType: 'Correction Bolus', insulin: 1, created_at: iso(now - 41 * MIN), enteredBy: 'probe146', notes: 'probe146 v1 bolus -41' }]);
  p = await props();
  record('control', 'iob-v1-late', r.status === 200 && p.iob - before > 0.3, `v1 1 U dated 41 min ago: ${r.status}; IOB ${before} -> ${p.iob}`);

  before = p.iob;
  r = await v3('treatments', 1, { eventType: 'Correction Bolus', insulin: 1, type: 'SMB', notes: 'probe146 v3 bolus -1' });
  p = await props();
  record('control', 'iob-v3-now', r.status === 201 && p.iob - before > 0.3, `v3 1 U dated 1 min ago: ${r.status}; IOB ${before} -> ${p.iob}`);

  const statuses = []; for (let i = 0; i < 24; i++) statuses.push({ device: 'probe146-v1-' + i, created_at: iso(now - (60 - i) * MIN), pump: { reservoir: 100 } });
  r = await v1('devicestatus', statuses);
  let order = await dsOrder();
  console.log(`setup   24 v1 device statuses dated 60 to 37 min ago: ${r.status}; default v1 read starts ${order.slice(0, 2).join(', ')}`);
  r = await v3('devicestatus', 20, { device: 'probe146-v3-late', pump: { reservoir: 90 } });
  order = await dsOrder();
  const at3 = order.indexOf('probe146-v3-late');
  record('arm', 'ds-v3-late', r.status === 201 && at3 === 0, `v3 status dated 20 min ago: ${r.status}; place in default v1 read ${at3 < 0 ? 'absent' : at3} of ${order.length}; first ${order[0]}`);
  r = await v1('devicestatus', [{ device: 'probe146-v1-late', created_at: iso(now - 19 * MIN), pump: { reservoir: 95 } }]);
  order = await dsOrder();
  record('control', 'ds-v1-late', r.status === 200 && order[0] === 'probe146-v1-late', `v1 status dated 19 min ago: ${r.status}; first ${order[0]}; the v3 status at ${order.indexOf('probe146-v3-late')}`);

  await stop(); await start();
  p = await props(); order = await dsOrder();
  console.log(`printed after a server restart: IOB ${p.iob} COB ${p.cob}; lastCarbs ${p.last === null ? '(none)' : p.last}; device status read starts ${order.slice(0, 2).join(', ')}`);
  const live1 = (await http('GET', '/api/v1/status.json')).status;
  record('control', 'liveness', live0 === 200 && live1 === 200, `status.json ${live0} before, ${live1} after`);
  await stop();

  const armFail = results.filter((x) => x.kind === 'arm' && !x.ok).map((x) => x.name);
  const ctlFail = results.filter((x) => x.kind === 'control' && !x.ok).map((x) => x.name);
  const code = ctlFail.length ? 2 : armFail.length ? 1 : 0;
  console.log(`result  arms failing: ${armFail.join(', ') || 'none'}; controls failing: ${ctlFail.join(', ') || 'none'}; exit ${code}`);
  process.exit(code);
})().catch(async (e) => { console.log('ERROR', e.message); if (server) await stop(); process.exit(3); });
