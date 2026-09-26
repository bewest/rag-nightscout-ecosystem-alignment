'use strict';
/*
 * BF-144 probe: after a large v1 batch and a restart, does API v3 history
 * still return a record written after a cursor the reader already holds
 * (PR #8781)?
 *
 * Usage:
 *   node history-clock-restart.js <port> <mongodb uri> <batch size> <label>=<tree> [<label>=<tree> ...]
 *   e.g. node history-clock-restart.js 17996 mongodb://127.0.0.1:27995/r3_144_test 60000 \
 *          before=~/crm-ff93fa94 after=~/crm-ce7d754a
 *
 * For each tree (with node_modules): drops the database, boots
 * lib/server/server.js with API_SECRET set and AUTH_DEFAULT_ROLES=denied, and
 * writes synthetic sgv entries only. The server runs in its own process group
 * and is killed by its PID.
 *
 * Steps, per tree:
 *   1. v1 POST /api/v1/entries with <batch size> entries, in back-to-back
 *      requests of 10,000 (the v1 per-request maximum).
 *      Printed: the largest stored srvModified minus wall time right after the
 *      response (the clock lead, ms).
 *   2. Read GET /api/v3/entries/history/<cursor>?limit=1000 from cursor 946684800000 (2000-01-01; 0 is refused) until
 *      a page is empty, taking the ETag of each page as the next cursor (as
 *      AndroidAPS NSClientV3 does). Printed: pages, records, final cursor.
 *   3. Stop the process (SIGTERM to its group), start it again on the same
 *      database.
 *   4. Create one entry through v3 POST /api/v3/entries and one through v1
 *      POST /api/v1/entries. Printed: each one's stored srvModified, the
 *      cursor, and wall time minus the cursor at the write (negative = the
 *      write happened while wall time was still behind the cursor).
 *   5. Read history from the saved cursor. Printed: which of the two new
 *      records it returns.
 * The arm is only meaningful while step 4 happens before wall time reaches
 * the cursor; the probe says so when it does not (make the batch larger).
 *
 * Exit 0 when every meaningful arm returns both new records, 1 when any
 * misses one, 2 when an arm was not meaningful, 3 on a harness error. No data
 * leaves the machine.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const port = Number(process.argv[2] || 17996);
const mongoUri = process.argv[3] || 'mongodb://127.0.0.1:27995/r3_144_test';
const N = Number(process.argv[4] || 60000);
const trees = process.argv.slice(5).map((a) => {
  const i = a.indexOf('=');
  return { label: a.slice(0, i), root: path.resolve(a.slice(i + 1)) };
});
if (trees.length === 0) { console.error('give at least one <label>=<tree>'); process.exit(3); }

const BASE = `http://127.0.0.1:${port}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function harness (root) {
  const req = (m) => require(path.join(root, 'node_modules', m));
  const { MongoClient } = req('mongodb');
  const SECRET = 'probe-secret-' + crypto.randomBytes(6).toString('hex');
  const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
  const h = { server: null };

  h.http = async function (method, p, body, headers) {
    const r = await fetch(BASE + p, {
      method,
      headers: Object.assign({ 'content-type': 'application/json', 'api-secret': HASH }, headers || {}),
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    let json = null; try { json = await r.json(); } catch (e) { /* not json */ }
    if (!(r.status >= 200 && r.status < 300)) throw new Error(method + ' ' + p + ' ' + r.status + ' ' + JSON.stringify(json));
    return { status: r.status, json, etag: r.headers.get('etag') };
  };
  h.drop = async function () {
    const db = await MongoClient.connect(mongoUri);
    await db.db().dropDatabase();
    await db.close();
  };
  h.start = async function () {
    const t0 = Date.now();
    h.server = spawn(process.execPath, ['lib/server/server.js'], {
      cwd: root, detached: true, stdio: ['ignore', 'ignore', 'ignore'],
      env: Object.assign({}, process.env, {
        MONGODB_URI: mongoUri, PORT: String(port), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true',
        NODE_ENV: 'production', API_SECRET: SECRET, AUTH_DEFAULT_ROLES: 'denied',
        ENABLE: 'careportal', DISPLAY_UNITS: 'mg/dl'
      })
    });
    for (let i = 0; i < 240; i++) {
      try { const r = await fetch(BASE + '/api/v1/status.json', { headers: { 'api-secret': HASH } }); if (r.status === 200) return Date.now() - t0; } catch (e) { /* booting */ }
      await sleep(250);
    }
    throw new Error('server did not answer on ' + BASE);
  };
  h.stop = async function () {
    if (h.server && h.server.pid) { try { process.kill(-h.server.pid, 'SIGTERM'); } catch (e) { /* gone */ } }
    for (let i = 0; i < 40; i++) {
      try { await fetch(BASE + '/api/v1/status.json'); } catch (e) { return; }
      await sleep(250);
    }
    try { process.kill(-h.server.pid, 'SIGKILL'); } catch (e) { /* gone */ }
  };
  h.v3Token = async function () {
    const name = 'probe' + Date.now();
    await h.http('POST', '/api/v2/authorization/subjects', { name, roles: ['admin'] });
    for (let i = 0; i < 20; i++) {
      const l = await h.http('GET', '/api/v2/authorization/subjects');
      const s = (l.json || []).find((x) => x.name === name);
      if (s && s.accessToken) {
        const j = await h.http('GET', '/api/v2/authorization/request/' + s.accessToken);
        if (j.json && j.json.token) return j.json.token;
      }
      await sleep(250);
    }
    throw new Error('no access token');
  };
  h.maxSrvModified = async function () {
    const db = await MongoClient.connect(mongoUri);
    const d = await db.db().collection('entries').find({ srvModified: { $type: 'number' } }).sort({ srvModified: -1 }).limit(1).toArray();
    await db.close();
    return d[0] && d[0].srvModified;
  };
  h.entryBy = async function (q) {
    const db = await MongoClient.connect(mongoUri);
    const d = await db.db().collection('entries').findOne(q);
    await db.close();
    return d;
  };
  return h;
}

const etagValue = (e) => { const m = /"(\d+)"/.exec(e || ''); return m ? Number(m[1]) : null; };

async function readHistory (h, auth, cursor) {
  let pages = 0, records = 0;
  const seen = [];
  for (;;) {
    const r = await h.http('GET', `/api/v3/entries/history/${cursor}?limit=1000`, undefined, auth);
    const rows = (r.json && r.json.result) || r.json || [];
    if (!Array.isArray(rows) || rows.length === 0) break;
    pages++; records += rows.length;
    rows.forEach((x) => seen.push(x));
    const next = etagValue(r.etag);
    if (next === null || next <= cursor) throw new Error('history page without a later ETag');
    cursor = next;
  }
  return { pages, records, cursor, seen };
}

async function runTree (tree) {
  const h = harness(tree.root);
  let restarted = false;
  try {
    await h.drop();
    const boot1 = await h.start();
    let auth = { authorization: 'Bearer ' + (await h.v3Token()) };
    const now = Date.now();
    const batch = [];
    for (let i = 0; i < N; i++) {
      const d = now - 7 * 24 * 3600 * 1000 + i * 5000;
      batch.push({ type: 'sgv', sgv: 80 + (i % 120), date: d, dateString: new Date(d).toISOString(), device: 'probe-batch' });
    }
    const tPost = Date.now();
    for (let i = 0; i < batch.length; i += 10000) await h.http('POST', '/api/v1/entries', batch.slice(i, i + 10000));
    const tDone = Date.now();
    const maxMod = await h.maxSrvModified();
    const lead = maxMod === undefined ? null : maxMod - tDone;
    console.log(`  boot ${boot1} ms | v1 POST ${N} entries (${Math.ceil(N / 10000)} requests) in ${tDone - tPost} ms | max srvModified ${maxMod} | lead over wall time ${lead} ms`);

    const hist = await readHistory(h, auth, 946684800000); // 2000-01-01; 0 is refused as a cursor
    console.log(`  history read: ${hist.pages} pages, ${hist.records} records, cursor ${hist.cursor} (wall time minus cursor ${Date.now() - hist.cursor} ms)`);
    const cursor = hist.cursor;

    await h.stop();
    const boot2 = await h.start();
    restarted = true;
    auth = { authorization: 'Bearer ' + (await h.v3Token()) };

    const tag = crypto.randomBytes(4).toString('hex');
    const d3 = Date.now();
    const w3 = Date.now();
    await h.http('POST', '/api/v3/entries', { type: 'sgv', sgv: 111, date: d3, app: 'probe', device: 'probe-v3-' + tag }, auth);
    const w1 = Date.now();
    await h.http('POST', '/api/v1/entries', [{ type: 'sgv', sgv: 112, date: d3 + 1000, dateString: new Date(d3 + 1000).toISOString(), device: 'probe-v1-' + tag }]);
    const e3 = await h.entryBy({ device: 'probe-v3-' + tag });
    const e1 = await h.entryBy({ device: 'probe-v1-' + tag });
    const meaningful = w3 < cursor;
    console.log(`  restart boot ${boot2} ms | v3 write at wall-cursor ${w3 - cursor} ms, srvModified ${e3 && e3.srvModified} (${e3 && e3.srvModified > cursor ? 'above' : 'NOT above'} cursor)`
      + ` | v1 write at wall-cursor ${w1 - cursor} ms, srvModified ${e1 && e1.srvModified} (${e1 && e1.srvModified > cursor ? 'above' : 'NOT above'} cursor)`);

    const after = await readHistory(h, auth, cursor);
    const got3 = after.seen.some((x) => x.device === 'probe-v3-' + tag);
    const got1 = after.seen.some((x) => x.device === 'probe-v1-' + tag);
    const ok = got3 && got1;
    const verdict = !meaningful ? 'N/M ' : (ok ? 'ok  ' : 'FAIL');
    console.log(`  ${verdict} history from cursor ${cursor}: ${after.records} records | v3 record ${got3 ? 'returned' : 'MISSING'} | v1 record ${got1 ? 'returned' : 'MISSING'}`
      + (meaningful ? '' : ' | not meaningful: the write came after wall time passed the cursor'));
    return !meaningful ? 2 : (ok ? 0 : 1);
  } finally {
    await h.stop();
    void restarted;
  }
}

(async () => {
  let code = 0;
  for (const tree of trees) {
    console.log(`${tree.label} (${tree.root})`);
    try {
      const r = await runTree(tree);
      if (r === 1) code = 1;
      else if (r === 2 && code === 0) code = 2;
    } catch (e) {
      console.log('  harness error:', e.message);
      code = 3;
    }
  }
  process.exit(code);
})();
