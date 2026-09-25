'use strict';
/*
 * _oid-cell.js — run named tools/lab/object-id probes against ONE build and
 * return the cells. Shared by the bfq-1NN-oid-cell.js gates.
 *
 * A build is a worktree of cgm-remote-monitor with `npm ci` done. The helper:
 *
 *   1. checks the worktree: node_modules present, lib/ clean, and HEAD equal to
 *      --ref when one is given (a gate must not measure a tree it did not mean);
 *   2. starts its own mongod in docker (fresh, so no earlier state leaks in)
 *      and reads the server version back;
 *   3. starts the build's server with a generated API secret, the lab's
 *      settings (AUTH_DEFAULT_ROLES=readable), and waits for status 200;
 *   4. runs tools/lab/object-id/probes.js with OID_PROBES=<the probes asked>;
 *   5. stops that server (by the pid listening on its port, and only if it is
 *      lib/server/server.js) and removes the container, whatever happened.
 *
 * Setup failures print CONTROL-INVALID and exit 90, so a control that cannot
 * be measured is never read as a control that went red (tools/queue/vacuity.py
 * reports CONTROL-ERROR for it). Nothing is written into the worktree: the
 * server writes only to its database, and the logs and secret live in a
 * temporary directory that is removed at the end.
 *
 * Environment:
 *   OID_GATE_MONGO_PORT   host port for the gate's mongod (default 27191)
 *   OID_GATE_PORT         port for the build's server (default 3991)
 *   OID_MONGO_IMAGE       default mongo:7
 *   OID_NODE              Node version for `n exec` (default 22.23.2)
 *   OID_GATE_CONTAINER    container name prefix (default oid-gate)
 *
 * Synthetic data only; the probes seed their own records. Contributor-facing.
 */

const { execFileSync, spawnSync } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { REPO_ROOT, CRM } = require('./_gate');

const PROBES = path.join(REPO_ROOT, 'tools', 'lab', 'object-id', 'probes.js');

function invalid (msg) {
  console.log('CONTROL-INVALID: ' + msg + ' NOTHING WAS MEASURED.');
  process.exit(90);
}

function args () {
  const a = process.argv.slice(2);
  const get = k => (a.includes(k) ? a[a.indexOf(k) + 1] : undefined);
  const build = get('--build');
  if (!build) invalid('usage: --build <worktree> [--ref <commit-ish>]');
  return { build: path.resolve(REPO_ROOT, build), ref: get('--ref') };
}

function sh (cmd, argv, opts) {
  return execFileSync(cmd, argv, Object.assign({ encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }, opts || {})).trim();
}

function portBusy (port) {
  const r = spawnSync('ss', ['-ltnH', 'sport = :' + port], { encoding: 'utf8' });
  return (r.stdout || '').trim() !== '';
}

function listener (port) {
  const r = spawnSync('ss', ['-ltnpH', 'sport = :' + port], { encoding: 'utf8' });
  const m = /pid=(\d+)/.exec(r.stdout || '');
  return m ? Number(m[1]) : null;
}

function sleep (ms) { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms); }

function httpStatus (url) {
  const r = spawnSync('curl', ['-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '3', url], { encoding: 'utf8' });
  return (r.stdout || '').trim();
}

/*
 * runCells({ build, ref }, probes) -> { head, mongod, cells }
 */
function runCells (opts, probes) {
  const build = opts.build;
  if (!fs.existsSync(path.join(build, 'lib', 'server', 'server.js'))) invalid(build + ' is not a cgm-remote-monitor worktree.');
  if (!fs.existsSync(path.join(build, 'node_modules', 'mongodb'))) invalid(build + ' has no node_modules (npm ci not done).');
  let head;
  try { head = sh('git', ['-C', build, 'rev-parse', 'HEAD']); } catch (e) { invalid('cannot read HEAD of ' + build + '.'); }
  if (opts.ref) {
    let want;
    try { want = sh('git', ['-C', CRM, 'rev-parse', opts.ref + '^{commit}']); } catch (e) { invalid('ref ' + opts.ref + ' does not resolve in ' + CRM + '.'); }
    if (want !== head) invalid(build + ' is at ' + head.slice(0, 8) + ', not ' + opts.ref + ' (' + want.slice(0, 8) + ').');
  }
  const dirty = sh('git', ['-C', build, 'status', '--porcelain', '--', 'lib']);
  if (dirty) invalid(build + ' has local changes under lib/: ' + dirty.split('\n')[0]);

  const mport = Number(process.env.OID_GATE_MONGO_PORT || 27191);
  const port = Number(process.env.OID_GATE_PORT || 3991);
  const image = process.env.OID_MONGO_IMAGE || 'mongo:7';
  const node = process.env.OID_NODE || '22.23.2';
  if (portBusy(mport)) invalid('mongo port ' + mport + ' is in use.');
  if (portBusy(port)) invalid('server port ' + port + ' is in use.');

  const name = (process.env.OID_GATE_CONTAINER || 'oid-gate') + '-' + process.pid + '-' + crypto.randomBytes(3).toString('hex');
  const state = fs.mkdtempSync(path.join(os.tmpdir(), 'oid-gate-'));
  const secret = crypto.randomBytes(18).toString('base64').replace(/[/+=]/g, '');
  fs.writeFileSync(path.join(state, 'secret'), secret, { mode: 0o600 });
  let serverPid = null;
  let container = false;

  const cleanup = () => {
    const pid = serverPid || listener(port);
    if (pid) {
      try {
        const cmd = fs.readFileSync('/proc/' + pid + '/cmdline', 'utf8').replace(/\0/g, ' ');
        if (cmd.includes('lib/server/server.js')) process.kill(pid, 'SIGTERM');
      } catch (e) { /* already gone */ }
    }
    if (container) spawnSync('docker', ['rm', '-f', name], { stdio: 'ignore' });
    fs.rmSync(state, { recursive: true, force: true });
  };

  try {
    try {
      sh('docker', ['run', '-d', '--name', name, '--ulimit', 'nofile=64000:64000', '-p', '127.0.0.1:' + mport + ':27017', image]);
      container = true;
    } catch (e) { throw new Error('docker run failed: ' + (e.stderr || e.message).split('\n')[0]); }
    if (sh('docker', ['inspect', '-f', '{{.State.Running}}', name]) !== 'true') throw new Error('container ' + name + ' is not running');

    // Ping mongod and read its version with the build's own driver.
    const ping = "const {MongoClient}=require(process.argv[1]);MongoClient.connect(process.argv[2],{serverSelectionTimeoutMS:2000}).then(async c=>{console.log((await c.db('admin').admin().serverInfo()).version);await c.close()}).catch(()=>process.exit(1))";
    let mongod = null;
    for (let i = 0; i < 40 && !mongod; i++) {
      const r = spawnSync('n', ['exec', node, 'node', '-e', ping, path.join(build, 'node_modules', 'mongodb'), 'mongodb://127.0.0.1:' + mport], { encoding: 'utf8' });
      if (r.status === 0 && r.stdout.trim()) mongod = r.stdout.trim().split('\n').pop(); else sleep(1000);
    }
    if (!mongod) throw new Error('mongod on ' + mport + ' did not answer');

    const env = {
      PATH: process.env.PATH, HOME: process.env.HOME, N_PREFIX: process.env.N_PREFIX || '',
      MONGODB_URI: 'mongodb://127.0.0.1:' + mport + '/oidlab_gate', API_SECRET: secret, PORT: String(port),
      HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true', AUTH_DEFAULT_ROLES: 'readable', DISPLAY_UNITS: 'mg/dl',
      ENABLE: 'careportal basal iob cob devicestatus profile'
    };
    const log = fs.openSync(path.join(state, 'server.log'), 'w');
    const child = require('child_process').spawn('setsid', ['n', 'exec', node, 'node', 'lib/server/server.js'],
      { cwd: build, env, detached: true, stdio: ['ignore', log, log] });
    child.unref();
    let up = false;
    for (let i = 0; i < 120 && !up; i++) {
      if (httpStatus('http://127.0.0.1:' + port + '/api/v1/status.json') === '200') up = true; else sleep(1000);
    }
    if (!up) throw new Error('server did not answer on ' + port + ': ' + fs.readFileSync(path.join(state, 'server.log'), 'utf8').split('\n').slice(-5).join(' | '));
    serverPid = listener(port);

    const r = spawnSync('n', ['exec', node, 'node', PROBES, 'gate', build, String(port)], {
      encoding: 'utf8', maxBuffer: 16 * 1024 * 1024,
      env: Object.assign({}, process.env, { OID_STATE: state, OID_MONGO_PORT: String(mport), OID_PROBES: probes.join(',') })
    });
    if (r.status !== 0) throw new Error('probes.js failed: ' + (r.stderr || '').split('\n').slice(0, 3).join(' | '));
    let out;
    try { out = JSON.parse(r.stdout.slice(r.stdout.indexOf('{'))); } catch (e) { throw new Error('probes.js output is not JSON'); }
    return { head: head.slice(0, 8), mongod, cells: out.cells };
  } catch (e) {
    cleanup();
    invalid(e.message);
  } finally {
    cleanup();
  }
}

/*
 * cellFindings(res, expect, controls) -> [{ok, text}]
 * `controls` are cells every build must answer the same way; if one does not,
 * the harness is broken and the run is CONTROL-INVALID rather than red.
 */
function cellFindings (res, expect, controls, label) {
  const findings = [];
  const liveness = ['P-ID-0 liveness before', 'P-ID-0 liveness after'];
  for (const k of liveness) {
    if (res.cells[k] !== '200') invalid(label + ' ' + res.head + ': ' + k + ' is ' + res.cells[k] + ', so the server was not answering.');
  }
  for (const [k, v] of Object.entries(controls)) {
    if (res.cells[k] !== v) invalid(label + ' ' + res.head + ': control cell "' + k + '" is "' + res.cells[k] + '", expected "' + v + '" on every build.');
    findings.push({ ok: true, text: 'CONTROL ' + k + ' = ' + v });
  }
  findings.push({ ok: true, text: 'build ' + res.head + ', mongod ' + res.mongod + ', liveness 200 before and after' });
  // An expected value is a string (the whole cell) or a RegExp (the property
  // the fix owns, when later fixes may legitimately change the rest of the cell).
  for (const [k, v] of Object.entries(expect)) {
    const got = res.cells[k];
    const ok = v instanceof RegExp ? v.test(String(got)) : got === v;
    const want = v instanceof RegExp ? 'a cell matching ' + v : '"' + v + '"';
    findings.push({ ok, text: (ok ? '' : label + ' PRESENT: ') + k + ' = "' + got + '"' + (ok ? '' : ' (fixed build answers ' + want + ')') });
  }
  return findings;
}

module.exports = { args, runCells, cellFindings, invalid };
