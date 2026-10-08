'use strict';
/*
 * Triage probe (BF-80): after failed logins from an address, how late does an
 * alarm reach a viewer on that same address over the /alarm socket?
 *
 * Usage:
 *   node tools/lab/triage-2026-09/bf80-alarm-delay.js <cgm-remote-monitor tree> <port> <readable|denied> <mongo url>
 *
 * Boots the tree's own lib/server/server.js as a child process with the
 * default failed-login delay (AUTH_FAIL_DELAY unset, 5000 ms per failure) and
 * TRUST_PROXY unset, so the client address is taken from X-Forwarded-For and
 * each case below gets an address of its own.
 *
 * Per case: N (=3) overlapping failed logins from the case's address (a wrong
 * `Authorization: Bearer` on /api/v1/entries), then a viewer on the same
 * address connects to /alarm and sends `subscribe`. 250 ms later a reading of
 * 40 mg/dL is uploaded with the correct secret from a separate address, which
 * raises an urgent low. Reported: subscribe ack time, `read`, and when the
 * urgent_alarm reached the viewer relative to the upload (null = not within
 * the 20 s window). An in-range reading then clears the alarm before the next
 * case.
 *
 * Cases (viewer's subscribe message):
 *   anon      { secret: null }          the web page with nobody signed in
 *   silent    connects, never subscribes
 *   badsecret { secret: <wrong hash> }
 *   jwt       { jwtToken: <valid JWT for a read-only subject> }
 *   control   anon on an address with no failures
 *
 * Environment: BF80_WINDOW_MS widens the 20 s window; BF80_CASES=a,b runs
 * only the named cases; BF80_SERVER_LOG=<file> keeps the server's output.
 *
 * Output: one JSON line per case on stdout. Exit 0 on completion, 3 on a
 * harness error. Nothing leaves the machine; the database is the one given.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const [tree, portArg, roles, mongo] = process.argv.slice(2);
if (!tree || !portArg || !roles || !mongo) {
  console.error('usage: bf80-alarm-delay.js <tree> <port> <readable|denied> <mongo url>');
  process.exit(3);
}
const root = path.resolve(tree);
const port = Number(portArg);
const base = `http://localhost:${port}`;
const io = require(path.join(root, 'node_modules/socket.io-client'));

const SECRET = 'probe-only-not-a-real-secret-0001';
const SECRET_HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const WRONG_HASH = crypto.createHash('sha1').update('wrong').digest('hex');
const N = 3;
const EMIT_AFTER = 250;
const WINDOW = Number(process.env.BF80_WINDOW_MS) || 20000;
const ONLY = process.env.BF80_CASES ? process.env.BF80_CASES.split(',') : null;
const UPLOADER = '198.51.100.250';

const sleep = ms => new Promise(r => setTimeout(r, ms));
let seq = 0;

function http (method, url, { headers = {}, body } = {}) {
  return fetch(base + url, {
    method
    , headers: Object.assign({ 'content-type': 'application/json' }, headers)
    , body: body ? JSON.stringify(body) : undefined
  }).then(async res => ({ status: res.status, body: await res.text() }));
}

function upload (sgv) {
  seq += 1;
  const date = Date.now();
  return http('POST', '/api/v1/entries', {
    headers: { 'api-secret': SECRET_HASH, 'X-Forwarded-For': UPLOADER }
    , body: [{ type: 'sgv', sgv, date, dateString: new Date(date).toISOString(), direction: 'Flat', device: 'bf80-probe' }]
  });
}

function boot () {
  const env = Object.assign({}, process.env, {
    CUSTOMCONNSTR_mongo: mongo
    , API_SECRET: SECRET
    , HOSTNAME: 'localhost'
    , INSECURE_USE_HTTP: 'true'
    , PORT: String(port)
    , NODE_ENV: 'production'
    , AUTH_DEFAULT_ROLES: roles
    , ENABLE: 'careportal simplealarms'
    , DISPLAY_UNITS: 'mg/dl'
  });
  delete env.AUTH_FAIL_DELAY;
  delete env.TRUST_PROXY;
  const child = spawn(process.execPath, ['lib/server/server.js'], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  // Server output goes to BF80_SERVER_LOG when set, else is discarded.
  const log = process.env.BF80_SERVER_LOG ? require('fs').createWriteStream(process.env.BF80_SERVER_LOG) : null;
  child.stdout.on('data', d => { if (log) { log.write(d); } });
  child.stderr.on('data', d => { if (log) { log.write(d); } });
  child.on('exit', (code, signal) => { if (log) { log.write(`\n[server exited code=${code} signal=${signal}]\n`); } });
  return child;
}

async function waitUp () {
  for (let i = 0; i < 120; i++) {
    try {
      const r = await http('GET', '/api/v1/status.json');
      if (r.status === 200 || r.status === 401) { return; }
    } catch (e) { /* not up yet */ }
    await sleep(500);
  }
  throw new Error('server did not come up');
}

async function readJwt () {
  const h = { 'api-secret': SECRET_HASH, 'X-Forwarded-For': UPLOADER };
  await http('POST', '/api/v2/authorization/roles', { headers: h, body: { name: 'bf80reader', permissions: ['api:*:read'], notes: '' } });
  await http('POST', '/api/v2/authorization/subjects', { headers: h, body: { name: 'bf80-viewer', roles: ['bf80reader'], notes: '' } });
  const subjects = JSON.parse((await http('GET', '/api/v2/authorization/subjects', { headers: h })).body);
  const subject = subjects.find(s => s.name === 'bf80-viewer');
  const r = await http('GET', `/api/v2/authorization/request/${subject.accessToken}`, { headers: { 'X-Forwarded-For': UPLOADER } });
  return JSON.parse(r.body).token;
}

async function fail (address) {
  const started = Date.now();
  await Promise.all(Array.from({ length: N }, () => http('GET', '/api/v1/entries.json?count=1', {
    headers: { Authorization: 'Bearer not-a-valid-jwt', 'X-Forwarded-For': address }
  })));
  return Date.now() - started;
}

async function runCase (name, address, message, jwt) {
  if (ONLY && !ONLY.includes(name)) { return; }
  const failMs = name === 'control' ? 0 : await fail(address);
  const socket = io(`${base}/alarm`, { transports: ['websocket'], forceNew: true, reconnection: false
    , extraHeaders: { 'X-Forwarded-For': address } });
  await new Promise((resolve, reject) => { socket.on('connect', resolve); socket.on('connect_error', reject); });

  let alarmAt = null;
  socket.on('urgent_alarm', () => { if (alarmAt === null) { alarmAt = Date.now(); } });

  const sent = Date.now();
  let ack = null;
  if (message) {
    const m = message === 'JWT' ? { jwtToken: jwt } : message;
    socket.emit('subscribe', m, data => { ack = { ms: Date.now() - sent, success: data && data.success, read: data && data.read }; });
  }
  await sleep(EMIT_AFTER);
  const uploadedAt = Date.now();
  await upload(40);
  const deadline = uploadedAt + WINDOW;
  while (Date.now() < deadline && (alarmAt === null || (message && ack === null))) { await sleep(50); }

  const out = { tree: path.basename(root), roles, case: name, failures: name === 'control' ? 0 : N, failMs
    , ack, alarmAfterUploadMs: alarmAt === null ? null : alarmAt - uploadedAt };
  console.log(JSON.stringify(out));
  socket.disconnect();

  // Clear the alarm, and let every delay from this case lapse, before the next.
  await upload(120);
  await sleep(N * 5000 + 2000);
}

(async function main () {
  const child = boot();
  process.on('exit', () => { try { child.kill('SIGTERM'); } catch (e) { /* gone */ } });
  try {
    await waitUp();
    await upload(120);
    await sleep(2000);
    const jwt = await readJwt();
    await runCase('control', '203.0.113.10', { secret: null });
    await runCase('anon', '203.0.113.11', { secret: null });
    await runCase('silent', '203.0.113.12', null);
    await runCase('badsecret', '203.0.113.13', { secret: WRONG_HASH });
    await runCase('jwt', '203.0.113.14', 'JWT', jwt);
  } catch (e) {
    console.error('harness error:', e);
    child.kill('SIGTERM');
    process.exit(3);
  }
  child.kill('SIGTERM');
  process.exit(0);
})();
