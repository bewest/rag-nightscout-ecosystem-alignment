'use strict';
/*
 * BF-143 probe: does an identical re-send of a treatment keep the stored
 * record's `_id` and `srvCreated` (PR #8781)?
 *
 * Usage:
 *   node retry-keeps-srvcreated.js <port> <mongodb uri> <label>=<tree> [<label>=<tree> ...]
 *   e.g. node retry-keeps-srvcreated.js 17995 mongodb://127.0.0.1:27995/r3_143_test \
 *          before=~/crm-ff93fa94 after=~/crm-ce7d754a
 *
 * For each tree (with node_modules): drops the database, boots
 * lib/server/server.js with API_SECRET set and AUTH_DEFAULT_ROLES=denied, and
 * writes synthetic treatments only. The server runs in its own process group
 * and is killed by its PID.
 *
 * Each arm writes one treatment, reads the stored document with the driver,
 * waits 20 ms, re-sends it by the arm's path and reads it again. Columns:
 * records stored at that created_at after the re-send, whether `_id` is the
 * same, whether `srvCreated` is the same (or absent both times), and whether
 * `srvModified` moved.
 *
 * Arms (no identity = none of syncIdentifier, id, uuid, NSCLIENT_ID,
 * identifier):
 *   R1 v1 POST single, no identity, carbs; re-POST identical single
 *   R2 same, re-POST as a one-item array (batch path)
 *   R3 same, re-POST inside a two-item array beside a new treatment
 *   R4 v1 POST single, no identity, carbs + insulin; re-POST identical
 *   R5 v1 POST single with uuid; re-POST identical (control)
 *   R6 v1 POST single with identifier; re-POST identical (control)
 *   R7 v1 POST, then v1 PUT the stored document as read back by v1 GET
 *   R8 v1 POST, then v1 PUT without srvCreated/srvModified (a v1 client that
 *      does not know them)
 *   R9 socket dbAdd, no identity; identical dbAdd re-send
 *
 * Verdict: FAIL when an R1-R4 or R7-R9 arm changes `_id` or `srvCreated` or
 * stores a second record; CTRL when R5/R6 does. Exit 0 when nothing fails, 1
 * on a FAIL, 2 on a CTRL, 3 on a harness error. No data leaves the machine.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const port = Number(process.argv[2] || 17995);
const mongoUri = process.argv[3] || 'mongodb://127.0.0.1:27995/r3_143_test';
const trees = process.argv.slice(4).map((a) => {
  const i = a.indexOf('=');
  return { label: a.slice(0, i), root: path.resolve(a.slice(i + 1)) };
});
if (trees.length === 0) { console.error('give at least one <label>=<tree>'); process.exit(3); }

const BASE = `http://127.0.0.1:${port}`;
const iso = (ms) => new Date(ms).toISOString();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function harness (root) {
  const req = (m) => require(path.join(root, 'node_modules', m));
  const { MongoClient } = req('mongodb');
  const ioClient = req('socket.io-client');
  const SECRET = 'probe-secret-' + crypto.randomBytes(6).toString('hex');
  const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
  const h = { server: null };

  h.http = async function (method, p, body) {
    const r = await fetch(BASE + p, {
      method,
      headers: { 'content-type': 'application/json', 'api-secret': HASH },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    let json = null; try { json = await r.json(); } catch (e) { /* not json */ }
    if (!(r.status >= 200 && r.status < 300)) throw new Error(method + ' ' + p + ' ' + r.status + ' ' + JSON.stringify(json));
    return { status: r.status, json };
  };
  h.boot = async function () {
    const db = await MongoClient.connect(mongoUri);
    await db.db().dropDatabase();
    await db.close();
    h.server = spawn(process.execPath, ['lib/server/server.js'], {
      cwd: root, detached: true, stdio: ['ignore', 'ignore', 'ignore'],
      env: Object.assign({}, process.env, {
        MONGODB_URI: mongoUri, PORT: String(port), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true',
        NODE_ENV: 'production', API_SECRET: SECRET, AUTH_DEFAULT_ROLES: 'denied',
        ENABLE: 'careportal', DISPLAY_UNITS: 'mg/dl'
      })
    });
    for (let i = 0; i < 120; i++) {
      try { const r = await fetch(BASE + '/api/v1/status.json', { headers: { 'api-secret': HASH } }); if (r.status === 200) return; } catch (e) { /* booting */ }
      await sleep(500);
    }
    throw new Error('server did not answer on ' + BASE);
  };
  h.stop = function () {
    if (h.server && h.server.pid) { try { process.kill(-h.server.pid, 'SIGTERM'); } catch (e) { /* gone */ } }
  };
  h.socketAdd = function (doc) {
    return new Promise((resolve, reject) => {
      const s = ioClient(BASE, { transports: ['websocket'], reconnection: false });
      const timer = setTimeout(() => { s.close(); reject(new Error('socket timeout')); }, 10000);
      s.on('connect', () => {
        s.emit('authorize', { client: 'probe', secret: HASH, history: 1 }, (auth) => {
          if (!auth || !auth.write_treatment) { clearTimeout(timer); s.close(); return reject(new Error('socket not authorized')); }
          s.emit('dbAdd', { collection: 'treatments', data: doc }, (reply) => { clearTimeout(timer); s.close(); resolve(reply); });
        });
      });
      s.on('connect_error', (e) => { clearTimeout(timer); reject(e); });
    });
  };
  h.at = async function (T) {
    const db = await MongoClient.connect(mongoUri);
    const docs = await db.db().collection('treatments').find({ created_at: iso(T) }).toArray();
    await db.close();
    return docs;
  };
  return h;
}

async function runTree (tree) {
  const h = harness(tree.root);
  const out = { fail: 0, ctrl: 0 };
  try {
    await h.boot();
    const now = Date.now();
    let slot = 0;
    const nextT = () => now - 3 * 3600 * 1000 + (slot++) * 60000;
    const base = (T, extra) => Object.assign({ eventType: 'Carb Correction', created_at: iso(T), carbs: 20, enteredBy: 'probe' }, extra || {});

    const arms = [
      ['R1', 'v1 POST single, no identity; re-POST single', false, async (T) => {
        await h.http('POST', '/api/v1/treatments', base(T)); return () => h.http('POST', '/api/v1/treatments', base(T));
      }],
      ['R2', 'v1 POST single, no identity; re-POST [one]', false, async (T) => {
        await h.http('POST', '/api/v1/treatments', base(T)); return () => h.http('POST', '/api/v1/treatments', [base(T)]);
      }],
      ['R3', 'v1 POST single, no identity; re-POST [it, new]', false, async (T) => {
        await h.http('POST', '/api/v1/treatments', base(T));
        return () => h.http('POST', '/api/v1/treatments', [base(T), base(T + 1000, { carbs: 5 })]);
      }],
      ['R4', 'v1 POST carbs+insulin, no identity; re-POST', false, async (T) => {
        const b = base(T, { eventType: 'Meal Bolus', insulin: 2 });
        await h.http('POST', '/api/v1/treatments', b); return () => h.http('POST', '/api/v1/treatments', b);
      }],
      ['R5', 'v1 POST with uuid; re-POST (control)', true, async (T) => {
        const b = base(T, { uuid: crypto.randomUUID() });
        await h.http('POST', '/api/v1/treatments', b); return () => h.http('POST', '/api/v1/treatments', b);
      }],
      ['R6', 'v1 POST with identifier; re-POST (control)', true, async (T) => {
        const b = base(T, { identifier: crypto.randomUUID() });
        await h.http('POST', '/api/v1/treatments', b); return () => h.http('POST', '/api/v1/treatments', b);
      }],
      ['R7', 'v1 POST; v1 PUT the document v1 GET returns', false, async (T) => {
        await h.http('POST', '/api/v1/treatments', base(T));
        const g = await h.http('GET', '/api/v1/treatments.json?count=1000');
        const doc = g.json.find((x) => x.created_at === iso(T));
        return () => h.http('PUT', '/api/v1/treatments', doc);
      }],
      ['R8', 'v1 POST; v1 PUT without srvCreated/srvModified', false, async (T) => {
        await h.http('POST', '/api/v1/treatments', base(T));
        const g = await h.http('GET', '/api/v1/treatments.json?count=1000');
        const doc = Object.assign({}, g.json.find((x) => x.created_at === iso(T)));
        delete doc.srvCreated; delete doc.srvModified;
        return () => h.http('PUT', '/api/v1/treatments', doc);
      }],
      ['R9', 'socket dbAdd, no identity; identical re-send', false, async (T) => {
        await h.socketAdd(base(T)); return () => h.socketAdd(base(T));
      }]
    ];

    for (const [id, name, control, arm] of arms) {
      const T = nextT();
      const resend = await arm(T);
      const [a] = await h.at(T);
      await sleep(20);
      await resend();
      const docs = await h.at(T);
      const b = docs.find((d) => String(d._id) === String(a._id)) || docs[0];
      const sameId = docs.length === 1 && String(b._id) === String(a._id);
      const sameCreated = b.srvCreated === a.srvCreated;
      const bad = docs.length !== 1 || !sameId || !sameCreated;
      let verdict = 'ok  ';
      if (bad && control) { verdict = 'CTRL'; out.ctrl++; }
      if (bad && !control) { verdict = 'FAIL'; out.fail++; }
      const created = a.srvCreated === undefined ? 'absent' : (sameCreated ? 'kept' : `${a.srvCreated} -> ${b.srvCreated} (+${b.srvCreated - a.srvCreated} ms)`);
      const modified = a.srvModified === undefined && b.srvModified === undefined ? 'absent' : (b.srvModified > a.srvModified ? 'moved' : 'same');
      console.log(`  ${verdict} ${id} ${name.padEnd(48)} | records ${docs.length} | _id ${sameId ? 'kept' : 'CHANGED'} | srvCreated ${created} | srvModified ${modified}`);
    }
  } finally {
    h.stop();
  }
  await sleep(1000);
  return out;
}

(async () => {
  let code = 0;
  for (const tree of trees) {
    console.log(`${tree.label} (${tree.root})`);
    try {
      const r = await runTree(tree);
      if (r.fail) code = Math.max(code, 1);
      if (r.ctrl) code = Math.max(code, 2);
    } catch (e) {
      console.log('  harness error:', e.message);
      code = 3;
    }
  }
  process.exit(code);
})();
