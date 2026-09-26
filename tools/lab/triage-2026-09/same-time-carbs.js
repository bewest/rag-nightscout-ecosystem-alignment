'use strict';
/*
 * Issue #8185 probe: do two carb entries recorded at the same time collapse
 * into one stored treatment?
 *
 * Usage:
 *   node same-time-carbs.js <cgm-remote-monitor tree with node_modules> <port> <mongodb uri> [--strict]
 *   e.g. node same-time-carbs.js ~/crm 17671 mongodb://127.0.0.1:27671/p8185_m
 *
 * Boots the tree's lib/server/server.js against the given MongoDB database
 * (which it drops first), writes synthetic carb treatments through each write
 * path, and counts what is stored by reading the collection with the driver.
 * The server is started in its own process group and killed by its PID.
 *
 * Arms (two carb entries with the SAME time, different carbs; each arm uses its
 * own time so arms cannot see each other):
 *   v1-single     two POST /api/v1/treatments, Loop's carb shape
 *                 (Carb Correction, created_at, syncIdentifier, no identifier)
 *   v1-array      one POST /api/v1/treatments with both in an array (bulkWrite)
 *   v1-careportal two POST /api/v1/treatments in the careportal's shape
 *                 (eventType Meal Bolus, created_at, enteredBy, no identifiers)
 *   v3-noid       two POST /api/v3/treatments, same date/device/eventType, no
 *                 identifier (the server computes one from device+date+eventType)
 *   v3-then-v1    a v3 carb (client identifier) then a v1 carb at the same
 *                 created_at and eventType (AAPS + careportal on one site)
 *   ws-dbAdd      two socket dbAdd, same created_at and eventType
 *   ws-similar    two socket dbAdd, 1 s apart, same carbs, different eventType
 * Controls, which must store 2 on every tree:
 *   v1-1s         the v1-single arm with the second entry 1 s later
 *   v1-identifier the v1-single arm with a distinct `identifier` on each entry
 *                 (shows the created_at + eventType fallback is the rule that
 *                 collapses them: identifier is tried first)
 *   v3-ids        the v3-noid arm with two distinct client identifiers
 *   ws-1s         two dbAdd 1 s apart with different carbs
 * Liveness: /api/v1/status.json answers 200 before and after the arms, and
 * every write answered 2xx (or a socket reply), so a count of 1 is the server's
 * choice, not a refused write.
 *
 * Exit status: 0 when every arm stores 2 (no collapse), 1 when any arm stores
 * fewer than 2 (v3-noid and ws-dbAdd are reported as known issues and not
 * counted, as the chosen BF-121 fix leaves them; `--strict` counts them), 2 when a control does not store 2 or liveness fails,
 * 3 on a harness error. No data leaves the machine.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const root = path.resolve(process.argv[2] || '.');
const port = Number(process.argv[3] || 17671);
const mongoUri = process.argv[4] || 'mongodb://127.0.0.1:27671/p8185';
const req = (m) => require(path.join(root, 'node_modules', m));
const { MongoClient } = req('mongodb');
const ioClient = req('socket.io-client');

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
    await new Promise((res) => setTimeout(res, 500));
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
    await new Promise((res) => setTimeout(res, 250));
  }
  throw new Error('no access token');
}

function socketAdd (docs) {
  return new Promise((resolve, reject) => {
    const s = ioClient(BASE, { transports: ['websocket'], reconnection: false });
    const timer = setTimeout(() => { s.close(); reject(new Error('socket timeout')); }, 10000);
    s.on('connect', () => {
      s.emit('authorize', { client: 'probe', secret: HASH, history: 1 }, (auth) => {
        if (!auth || !auth.write_treatment) { clearTimeout(timer); s.close(); return reject(new Error('socket not authorized')); }
        const replies = [];
        (async () => {
          for (const d of docs) {
            replies.push(await new Promise((r) => s.emit('dbAdd', { collection: 'treatments', data: d }, r)));
          }
          clearTimeout(timer); s.close(); resolve(replies);
        })().catch(reject);
      });
    });
    s.on('connect_error', (e) => { clearTimeout(timer); reject(e); });
  });
}

async function stored (col, t0, t1) {
  const db = await MongoClient.connect(mongoUri);
  const n = await db.db().collection('treatments').find({ created_at: { $gte: t0, $lte: t1 } }).toArray();
  await db.close();
  return n;
}

const iso = (ms) => new Date(ms).toISOString();
// The BF-121 fix the maintainer chose (option 3, 2026-09-26) changes API v1 and
// the socket's identity and similar matching, and adds amounts to the key for
// API v1 only. These two arms stay collapsed by design: they are reported, not
// hidden, and do not decide the exit status unless --strict is given.
const KNOWN = 'known issue (option 3 leaves AAPS paths unchanged)';
const strict = process.argv.includes('--strict');
let ok2xx = true;
const check = (r) => { if (!(r.status >= 200 && r.status < 300)) { ok2xx = false; console.log('  write answered', r.status, JSON.stringify(r.json)); } return r; };

async function main () {
  await boot();
  const token = await v3Token();
  const v3 = { authorization: 'Bearer ' + token };
  const t = Date.parse('2026-09-25T08:00:00.000Z');
  const slot = (i) => t + i * 3600e3;
  const loopCarb = (ms, carbs) => ({ eventType: 'Carb Correction', created_at: iso(ms), carbs, absorptionTime: 180,
    enteredBy: 'loop://iPhone', syncIdentifier: crypto.randomUUID() });
  const arms = {};

  arms['v1-single'] = { control: false, run: async (ms) => {
    check(await http('POST', '/api/v1/treatments', loopCarb(ms, 20)));
    check(await http('POST', '/api/v1/treatments', loopCarb(ms, 15)));
  } };
  arms['v1-array'] = { control: false, run: async (ms) => {
    check(await http('POST', '/api/v1/treatments', [loopCarb(ms, 20), loopCarb(ms, 15)]));
  } };
  arms['v1-careportal'] = { control: false, run: async (ms) => {
    for (const carbs of [20, 15]) {
      check(await http('POST', '/api/v1/treatments', { eventType: 'Meal Bolus', created_at: iso(ms), carbs, enteredBy: 'careportal' }));
    }
  } };
  arms['v3-noid'] = { control: false, known: KNOWN, run: async (ms) => {
    for (const carbs of [20, 15]) {
      check(await http('POST', '/api/v3/treatments', { eventType: 'Carb Correction', date: ms, utcOffset: 0, app: 'probe', device: 'probe', carbs }, v3));
    }
  } };
  arms['v3-then-v1'] = { control: false, run: async (ms) => {
    check(await http('POST', '/api/v3/treatments', { eventType: 'Carb Correction', date: ms, utcOffset: 0, app: 'probe', device: 'probe',
      identifier: crypto.randomUUID(), carbs: 20 }, v3));
    check(await http('POST', '/api/v1/treatments', { eventType: 'Carb Correction', created_at: iso(ms), carbs: 15, enteredBy: 'careportal' }));
  } };
  arms['ws-dbAdd'] = { control: false, known: KNOWN, run: async (ms) => {
    await socketAdd([{ eventType: 'Carb Correction', created_at: iso(ms), carbs: 20 }, { eventType: 'Carb Correction', created_at: iso(ms), carbs: 15 }]);
  } };
  arms['ws-similar'] = { control: false, run: async (ms) => {
    await socketAdd([{ eventType: 'Carb Correction', created_at: iso(ms), carbs: 20 }, { eventType: 'Meal Bolus', created_at: iso(ms + 1000), carbs: 20 }]);
  } };
  arms['v1-1s'] = { control: true, run: async (ms) => {
    check(await http('POST', '/api/v1/treatments', loopCarb(ms, 20)));
    check(await http('POST', '/api/v1/treatments', loopCarb(ms + 1000, 15)));
  } };
  arms['v1-identifier'] = { control: true, run: async (ms) => {
    for (const carbs of [20, 15]) {
      check(await http('POST', '/api/v1/treatments', Object.assign(loopCarb(ms, carbs), { identifier: crypto.randomUUID() })));
    }
  } };
  arms['v3-ids'] = { control: true, run: async (ms) => {
    for (const carbs of [20, 15]) {
      check(await http('POST', '/api/v3/treatments', { eventType: 'Carb Correction', date: ms, utcOffset: 0, app: 'probe', device: 'probe',
        identifier: crypto.randomUUID(), carbs }, v3));
    }
  } };
  arms['ws-1s'] = { control: true, run: async (ms) => {
    await socketAdd([{ eventType: 'Carb Correction', created_at: iso(ms), carbs: 20 }, { eventType: 'Carb Correction', created_at: iso(ms + 1000), carbs: 15 }]);
  } };

  let defect = false, badControl = false, knownOpen = 0, i = 0;
  for (const [name, arm] of Object.entries(arms)) {
    const ms = slot(i++);
    await arm.run(ms);
    await new Promise((r) => setTimeout(r, 300));
    const docs = await stored('treatments', iso(ms - 1), iso(ms + 5000));
    const n = docs.length;
    const carbs = docs.map((d) => d.carbs).join('+');
    const ids = docs.map((d) => (d.identifier ? 'identifier' : '-') + '/' + (d.srvModified ? 'srvModified' : '-')).join(' ');
    let verdict;
    if (arm.control) verdict = n === 2 ? 'ok' : 'CONTROL FAILED';
    else if (n >= 2) verdict = 'fixed';
    else if (arm.known && !strict) verdict = arm.known;
    else verdict = 'COLLAPSED';
    console.log(`${arm.control ? 'control' : 'arm    '} ${name.padEnd(14)} stored ${n} (carbs ${carbs || '-'}; ${ids}) -> ${verdict}`);
    if (arm.control && n !== 2) badControl = true;
    if (!arm.control && n < 2) {
      if (arm.known && !strict) knownOpen++;
      else defect = true;
    }
  }
  if (knownOpen) console.log(`known issues still collapsed: ${knownOpen} (not counted; --strict counts them)`);
  const live = await http('GET', '/api/v1/status.json');
  console.log('liveness after arms:', live.status, 'writes all 2xx:', ok2xx);
  if (live.status !== 200 || !ok2xx) badControl = true;
  return badControl ? 2 : defect ? 1 : 0;
}

main().then((code) => { console.log('exit', code); finish(code); })
  .catch((e) => { console.error('harness error:', e.message); finish(3); });

function finish (code) {
  if (server && server.pid) { try { process.kill(-server.pid, 'SIGTERM'); } catch (e) { /* gone */ } }
  process.exit(code);
}
