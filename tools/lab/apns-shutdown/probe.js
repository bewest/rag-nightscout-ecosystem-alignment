'use strict';
/*
 * BF-134 probe: does every Loop remote command leave an APNs HTTP/2
 * connection open for the life of the Nightscout process?
 *
 * Usage: node probe.js <cgm-remote-monitor tree with node_modules>   (cwd = the tree)
 *        N=1,5,20 node probe.js <tree>        (command counts per arm; default 1,5,20)
 *
 * Runs the tree's own lib/server/loop.js sendNotification() against a local
 * fake APNs server (HTTP/2 over TLS on 127.0.0.1, answering 200 to every
 * push), by patching the tree's @parse/node-apn Provider address and port
 * the way PR #8419's test does. A fresh EC P-256 key is generated in-process
 * for the provider token; the TLS pair is the tree's test fixture.
 *
 * It counts the HTTP/2 sessions the fake server still has open after the
 * commands complete: server 'session' events minus session 'close' events.
 * It also counts the library's per-client heartbeat intervals still live
 * (global setInterval/clearInterval are wrapped before node-apn loads).
 *
 * Controls, which must behave on every tree (else exit 2):
 *   counter     one push on a directly built provider leaves 1 open session
 *               (the counter sees a leak when there is one)
 *   shutdown    ... and provider.shutdown() then brings it to 0 open and
 *               clears the heartbeat interval
 * Arms:
 *   N commands  N sequential "Temporary Override Cancel" remote commands
 *               through one loop instance, as the server does; all must
 *               complete without error. Open sessions are counted 300 ms
 *               after the last completion.
 * Informational (not in the exit status):
 *   goaway      the server sends GOAWAY and closes every session (as APNs may
 *               for an idle connection): open sessions afterwards, and how
 *               many heartbeat intervals outlive their sessions
 *   rejected-command  a remote bolus of 0 U, which loop.js refuses after the
 *               settings checks: is a provider (and its interval) still built?
 *   no-loop-env sendNotification with env.extendedSettings.loop undefined (a
 *               site without LOOP_* settings): does it throw before building
 *               a provider?
 *
 * Exit status: 0 when every arm leaves 0 open sessions, 1 when any arm leaves
 * one or more, 2 when a control misbehaves or a command fails (the probe
 * measures nothing). Nothing leaves 127.0.0.1; nothing is written.
 */
const path = require('path');
const fs = require('fs');
const http2 = require('http2');
const crypto = require('crypto');

const root = path.resolve(process.argv[2] || '.');
const counts = (process.env.N || '1,5,20').split(',').map(Number);

// Track intervals before node-apn creates any.
const liveIntervals = new Set();
const origSetInterval = global.setInterval;
const origClearInterval = global.clearInterval;
global.setInterval = function () {
  const t = origSetInterval.apply(this, arguments);
  liveIntervals.add(t);
  return t;
};
global.clearInterval = function (t) {
  liveIntervals.delete(t);
  return origClearInterval.apply(this, arguments);
};

const apn = require(path.join(root, 'node_modules/@parse/node-apn'));
const loopInit = require(path.join(root, 'lib/server/loop'));

function fixture (name) {
  for (const dir of ['tests/fixtures/api3', 'tests/fixtures']) {
    const p = path.join(root, dir, name);
    if (fs.existsSync(p)) return fs.readFileSync(p);
  }
  throw new Error('no TLS fixture ' + name);
}

const apnsKey = crypto.generateKeyPairSync('ec', { namedCurve: 'prime256v1' })
  .privateKey.export({ type: 'pkcs8', format: 'pem' });

const server = http2.createSecureServer({ key: fixture('localhost.key'), cert: fixture('localhost.crt') });
const serverSessions = new Set();
let opened = 0, closed = 0;
server.on('session', (s) => {
  opened++;
  serverSessions.add(s);
  s.on('close', () => { closed++; serverSessions.delete(s); });
});
server.on('stream', (stream) => {
  stream.on('data', () => {});
  stream.on('end', () => {
    stream.respond({ ':status': 200, 'content-type': 'application/json' });
    stream.end();
  });
});
const openSessions = () => opened - closed;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

let providersBuilt = 0;
function patch (port) {
  const Original = apn.Provider;
  apn.Provider = function PatchedProvider (options) {
    providersBuilt++;
    options.address = 'localhost';
    options.port = port;
    options.rejectUnauthorized = false;
    return new Original(options);
  };
  return Original;
}

function makeEnvCtx () {
  const env = { extendedSettings: { loop: { apnsKey, apnsKeyId: 'PROBEKEYID', developerTeamId: 'PROBETEAM1', pushServerEnvironment: 'development' } } };
  const ctx = { ddata: { profiles: [{ loopSettings: { deviceToken: 'probedevicetoken', bundleIdentifier: 'org.example.probe' } }] } };
  return { env, ctx };
}

function command (loop) {
  return new Promise((resolve, reject) => {
    loop.sendNotification({ eventType: 'Temporary Override Cancel' }, '127.0.0.1', (err) => err ? reject(new Error(String(err))) : resolve());
  });
}

async function resetServer () {
  for (const s of serverSessions) s.destroy();
  await wait(200);
}

async function main () {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  const Original = patch(port);
  console.log(`tree ${root}`);
  console.log(`node ${process.version}, @parse/node-apn ${require(path.join(root, 'node_modules/@parse/node-apn/package.json')).version}`);

  // Controls
  const iv0 = liveIntervals.size;
  const p = new apn.Provider({ token: { key: apnsKey, keyId: 'PROBEKEYID', teamId: 'PROBETEAM1' }, production: false });
  const note = new apn.Notification();
  note.alert = 'probe'; note.topic = 'org.example.probe';
  const res = await p.send(note, ['probedevicetoken']);
  await wait(300);
  const afterSend = openSessions();
  const ivAfterSend = liveIntervals.size - iv0;
  await new Promise((r) => p.shutdown(r));
  await wait(300);
  const afterShutdown = openSessions();
  const ivAfterShutdown = liveIntervals.size - iv0;
  console.log(`control counter: sent=${res.sent.length} open sessions after 1 push = ${afterSend} (want 1), heartbeat intervals = ${ivAfterSend} (want 1)`);
  console.log(`control shutdown: open sessions after provider.shutdown() = ${afterShutdown} (want 0), heartbeat intervals = ${ivAfterShutdown} (want 0)`);
  if (res.sent.length !== 1 || afterSend !== 1 || afterShutdown !== 0 || ivAfterSend !== 1 || ivAfterShutdown !== 0) {
    console.log('a control misbehaved; the arms below measure nothing');
    process.exit(2);
  }
  await resetServer();

  // Arms
  let leaked = false;
  for (const n of counts) {
    const { env, ctx } = makeEnvCtx();
    const loop = loopInit(env, ctx);
    const base = openSessions();
    const ivBase = liveIntervals.size;
    const built0 = providersBuilt;
    const sessions0 = opened;
    try {
      for (let i = 0; i < n; i++) await command(loop);
    } catch (e) {
      console.log(`arm N=${n}: a command failed: ${e.message}; the probe measures nothing`);
      process.exit(2);
    }
    await wait(300);
    const open = openSessions() - base;
    console.log(`arm N=${n}: providers built = ${providersBuilt - built0}, sessions opened = ${opened - sessions0}, still open = ${open}, heartbeat intervals live = ${liveIntervals.size - ivBase}`);
    if (open > 0) leaked = true;
    if (n === counts[counts.length - 1]) {
      // Informational: the server sends GOAWAY and closes, as APNs may on idle.
      const ivBefore = liveIntervals.size - ivBase;
      for (const s of serverSessions) { try { s.goaway(); } catch (e) { /* ignore */ } s.close(); }
      await wait(500);
      console.log(`info goaway after N=${n}: server sent GOAWAY+close; still open = ${openSessions() - base}, heartbeat intervals live = ${liveIntervals.size - ivBase} (were ${ivBefore})`);
    }
    await resetServer();
  }

  // Informational: a command loop.js rejects after its settings checks.
  {
    const { env, ctx } = makeEnvCtx();
    const loop = loopInit(env, ctx);
    const built0 = providersBuilt, ivBase = liveIntervals.size;
    let msg;
    await new Promise((resolve) => loop.sendNotification({ eventType: 'Remote Bolus Entry', remoteBolus: 0 }, '127.0.0.1', (err) => { msg = err; resolve(); }));
    console.log(`info rejected-command: completion(${JSON.stringify(msg)}); providers built = ${providersBuilt - built0}, heartbeat intervals live = ${liveIntervals.size - ivBase}`);
  }

  // Informational: no LOOP_* settings at all.
  {
    const built0 = providersBuilt;
    let outcome;
    try {
      const loop = loopInit({ extendedSettings: {} }, makeEnvCtx().ctx);
      await new Promise((resolve) => loop.sendNotification({ eventType: 'Temporary Override Cancel' }, '127.0.0.1', (err) => { outcome = 'completion(' + JSON.stringify(err) + ')'; resolve(); }));
    } catch (e) {
      outcome = 'threw ' + e.constructor.name + ': ' + e.message;
    }
    console.log(`info no-loop-env: ${outcome}; providers built = ${providersBuilt - built0}`);
  }

  apn.Provider = Original;
  server.close();
  process.exit(leaked ? 1 : 0);
}

main().catch((e) => { console.log('probe error: ' + (e && e.stack || e)); process.exit(2); });
