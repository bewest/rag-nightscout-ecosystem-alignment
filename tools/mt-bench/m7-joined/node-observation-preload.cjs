'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { performance } = require('node:perf_hooks');
const { Session } = require('node:inspector');

const MAX_FILE_BYTES = 8 * 1024 * 1024;
const roles = new Set(['api', 'evaluator', 'realtime']);
const command = (session, name, params = {}) => new Promise((resolve, reject) => {
  session.post(name, params, (error, result) => error ? reject(error) : resolve(result));
});

function record(file, value) {
  const bytes = JSON.stringify(value);
  if (Buffer.byteLength(bytes) > MAX_FILE_BYTES) throw Error('M7_NODE_OBSERVATION_BYTES');
  fs.writeFileSync(file + '.partial', bytes, { flag: 'wx', mode: 0o600 });
  fs.renameSync(file + '.partial', file);
}

async function profile(directory, binding, intervalMs) {
  const session = new Session();
  session.connect(); // In-process inspector session. No debugger listener.
  const issuedAt = Date.now();
  try {
    await command(session, 'Profiler.enable');
    await command(session, 'Profiler.setSamplingInterval', { interval: 2000 });
    await command(session, 'Profiler.start');
    await new Promise(resolve => setTimeout(resolve, intervalMs));
    const { profile } = await command(session, 'Profiler.stop');
    record(directory + '/node-profile-' + binding.role + '.json',
      { ...binding, issuedAt, stoppedAt: Date.now(), profile });
  } finally {
    session.disconnect();
  }
}

function measure(directory, binding, { sampledMs, cadenceMs, cpuDelayMs, cpuDurationMs }) {
  const eluAtStart = performance.eventLoopUtilization();
  const startedAt = Date.now();
  const samples = [];
  let last = eluAtStart;
  const sample = () => {
    const next = performance.eventLoopUtilization();
    const { active, idle } = performance.eventLoopUtilization(next, last);
    samples.push({ at: Date.now(), active, idle });
    last = next;
  };
  const timer = setInterval(sample, cadenceMs);
  setTimeout(() => {
    profile(directory, binding, cpuDurationMs).catch(() => {
      // A missing profile is explicit in the host reduction. Do not change role behavior.
    });
  }, cpuDelayMs).unref();
  setTimeout(() => {
    clearInterval(timer);
    sample();
    try {
      const total = performance.eventLoopUtilization(last, eluAtStart);
      record(directory + '/node-elu-' + binding.role + '.json',
        { ...binding, startedAt, endedAt: samples.at(-1).at, total, samples });
    } catch { /* An absent capture remains unmeasured. */ }
  }, sampledMs).unref();
  timer.unref();
}

function marker(file, owner, now = Date.now()) {
  if (!fs.existsSync(file) || fs.statSync(file).size > 1024) return null;
  const value = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (value.owner !== owner || !/^[a-f0-9]{32}$/.test(value.nonce) || !/^[a-f0-9]{64}$/.test(value.cadenceSha256) ||
      !Number.isSafeInteger(value.ordinaryAt) || !Number.isSafeInteger(value.armedAt) ||
      value.ordinaryAt > value.armedAt || value.armedAt > now || now - value.ordinaryAt > 10000) return null;
  return value;
}

function diagnosticsState(config, root = process.cwd()) {
  const file = path.resolve(root, 'lib/diagnostics/m7.js');
  const loaded = require.cache[file];
  if (!loaded || typeof loaded.exports.enabled !== 'boolean') return { status: 'UNMEASURED', reason: 'M7_NODE_DIAGNOSTICS_NOT_LOADED' };
  const enabled = loaded.exports.enabled;
  const expected = config.diagnosticsMode === 'on';
  if (enabled !== expected || (process.env.NS_M7_DIAGNOSTICS === '1') !== expected)
    return { status: 'UNMEASURED', reason: 'M7_NODE_DIAGNOSTICS_SELECTION_MISMATCH' };
  return { status: 'VERIFIED', mode: config.diagnosticsMode, enabled,
    sourceSha256: createHash('sha256').update(fs.readFileSync(file)).digest('hex') };
}

function start(config) {
  const { owner, role, core, deploy, output, signal } = config;
  if (!/^[a-f0-9]{32}$/.test(owner) || !/^[a-f0-9]{40}$/.test(core) ||
      !/^[a-f0-9]{40}$/.test(deploy) || !roles.has(config.commandRole) || !new RegExp('^' + config.commandRole + '(?:-(?:[2-9]|1[0-6]))?$').test(role) ||
      config.commandRole !== process.argv[2] || !['off', 'on'].includes(config.diagnosticsMode) || output !== '/run/ns-ipc' ||
      signal !== '/run/ns-node-observe/signal.json') throw Error('M7_NODE_OBSERVATION_CONFIG');
  const observer = setInterval(() => {
    let issued;
    try { issued = marker(signal, owner); } catch { return; }
    if (!issued) return;
    clearInterval(observer);
    measure(output, { owner, role, core, deploy, nonce: issued.nonce, cadenceSha256: issued.cadenceSha256, node: process.version, pid: process.pid,
      birthMs: Math.floor(performance.timeOrigin), diagnosticsMode: config.diagnosticsMode, m7Diagnostics: diagnosticsState(config) },
    { sampledMs: 240000, cadenceMs: 1000, cpuDelayMs: 30000, cpuDurationMs: 30000 });
  }, 500);
  observer.unref();
}

const file = process.env.M7_NODE_OBSERVATION_CONFIG;
if (file) {
  if (fs.statSync(file).size > 1024) throw Error('M7_NODE_OBSERVATION_CONFIG');
  start(JSON.parse(fs.readFileSync(file, 'utf8')));
}
module.exports = { marker, measure, diagnosticsState };
