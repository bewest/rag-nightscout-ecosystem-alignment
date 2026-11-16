'use strict';
// Same Node actor for the two receipt-selected, bounded serial exchange phases.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const http = require('node:http');
const { performance } = require('node:perf_hooks');
const SELECTION = Object.freeze({ tenants: 64, phaseSeconds: 120, requestSeconds: 60 });
const ALLOWED = Object.freeze(['AUTHORITY_UNAVAILABLE','TENANT_ACTIVITY_UNAVAILABLE','TENANT_WARMING','TENANT_UNAVAILABLE',
  'HUMAN_SESSION_UNAVAILABLE','ACCESS_AUTHORITY_UNAVAILABLE','ACCESS_AUTHORITY_INVALID','TENANT_SNAPSHOT_UNAVAILABLE',
  'TENANT_REFUSED','CREDENTIAL_REFUSED','TENANT_LEGACY_FORBIDDEN','AUTHORITY_FORBIDDEN']);
const fail = code => { throw Error(code); };
const need = (value, code) => { if (!value) fail(code); };
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const fileHash = file => { try { return hash(fs.readFileSync(file)); } catch (_) { fail('M7_SERIAL_EXCHANGE_FILE_UNAVAILABLE'); } };
const json = file => { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (_) { fail('M7_SERIAL_EXCHANGE_JSON_INVALID'); } };
const equal = require('node:util').isDeepStrictEqual;
function safeResponse(response) {
  const headers = response.headers || {};
  const retry = headers['retry-after'] ?? headers['Retry-After'];
  const retryAfterSeconds = typeof retry === 'string' && /^[0-9]{1,3}$/.test(retry) && Number(retry) <= 300 ? Number(retry) : null;
  if (response.status === 200) return { errorCode: null, bodyObservation: 'SUCCESS_BODY_DISCARDED', retryAfterSeconds };
  let errorCode = null, bodyObservation = 'NOT_JSON';
  const type = headers['content-type'] ?? headers['Content-Type'] ?? '';
  if (response.oversize || typeof response.body !== 'string' || Buffer.byteLength(response.body) > 4096) bodyObservation = 'BODY_OUTSIDE_BOUND';
  else if (typeof type === 'string' && /^(application\/json|application\/problem\+json)(;|$)/i.test(type)) {
    try {
      const value = JSON.parse(response.body);
      if (value && typeof value === 'object' && ALLOWED.includes(value.error)) { errorCode = value.error; bodyObservation = 'ALLOWLISTED_ERROR_CODE'; }
      else bodyObservation = 'UNRECOGNIZED_ERROR_CODE';
    } catch (_) { bodyObservation = 'INVALID_JSON'; }
  }
  return { errorCode, bodyObservation, retryAfterSeconds };
}
function requestOnce(options, timeoutMs, agent) {
  return new Promise(resolve => {
    let done = false, timer;
    const finish = value => { if (!done) { done = true; clearTimeout(timer); resolve(value); } };
    let req;
    try {
      req = http.request({ ...options, agent }, res => {
        let body = '', bytes = 0, oversize = false;
        res.on('data', chunk => {
          // A successful JWT is never retained, parsed, returned or logged.
          if (res.statusCode === 200) return;
          bytes += chunk.length;
          if (bytes <= 4096) body += chunk.toString('utf8');
          else { oversize = true; body = ''; }
        });
        res.on('end', () => finish({ status: res.statusCode, headers: res.headers, body, oversize }));
        res.on('error', () => finish({ status: 0, transport: 'RESPONSE_TRANSPORT_ERROR' }));
      });
      req.on('error', () => finish({ status: 0, transport: 'REQUEST_TRANSPORT_ERROR' }));
      timer = setTimeout(() => { finish({ status: 0, transport: 'REQUEST_TIMEOUT' }); req.destroy(); }, timeoutMs);
      req.end();
    } catch (_) { finish({ status: 0, transport: 'REQUEST_TRANSPORT_ERROR' }); }
  });
}
function createActor(bindingPath, bindingSha256, injected = {}) {
  need(path.isAbsolute(bindingPath) && /^[a-f0-9]{64}$/.test(bindingSha256), 'M7_SERIAL_EXCHANGE_BINDING_ARGUMENT');
  need(fileHash(bindingPath) === bindingSha256, 'M7_SERIAL_EXCHANGE_BINDING_CHANGED');
  const b = json(bindingPath);
  need(b.version === 1 && b.kind === 'pgstream-serial-exchange-pair-v1' && equal(b.selection, SELECTION), 'M7_SERIAL_EXCHANGE_SELECTION');
  let base;try { base = new URL(b.baseUrl); } catch (_) { fail('M7_SERIAL_EXCHANGE_LOOPBACK'); }
  need(base.protocol === 'http:' && base.hostname === '127.0.0.1' && /^\d+$/.test(base.port) && Number(base.port) >= 1024 && !base.username && !base.password && base.pathname === '/' && !base.search && !base.hash, 'M7_SERIAL_EXCHANGE_LOOPBACK');
  for (const name of ['ownerFile','tenantsFile','outputDirectory']) need(path.isAbsolute(b[name]), 'M7_SERIAL_EXCHANGE_INPUT_PATH');
  const clock = injected.clock || Date.now, monotonic = injected.monotonic || (() => performance.now());
  const agent = injected.agent || new http.Agent({ keepAlive: true, maxSockets: 1, maxFreeSockets: 1 });
  const request = injected.request || ((options, timeout) => requestOnce(options, timeout, agent));
  const persist = injected.persist || ((phase, value) => { fs.mkdirSync(b.outputDirectory, { recursive: true, mode: 0o700 }); fs.writeFileSync(path.join(b.outputDirectory, phase + '.json'), JSON.stringify(value, null, 2) + '\n', { flag: 'wx', mode: 0o600 }); });
  const phases = [];
  function inputs() {
    need(fileHash(bindingPath) === bindingSha256 && fileHash(b.ownerFile) === b.ownerSha256 && fileHash(b.tenantsFile) === b.tenantsSha256, 'M7_SERIAL_EXCHANGE_INPUT_CHANGED');
    need(fileHash(__filename) === b.actorSha256 && fs.realpathSync(process.execPath) === fs.realpathSync(b.nodeExecutable) && fileHash(process.execPath) === b.nodeSha256, 'M7_SERIAL_EXCHANGE_ACTOR_CHANGED');
    const owner = json(b.ownerFile);
    need(owner.owner === b.owner && equal(owner.pair, b.pair) && owner.imageId === b.imageId && owner.instrument.sha256 === b.instrument && owner.tenants === 3000 && equal(owner.serialExchangeDiagnostic, SELECTION), 'M7_SERIAL_EXCHANGE_SOURCE_BINDING');
    const tenants = json(b.tenantsFile);
    need(Array.isArray(tenants) && tenants.length === 3000 && tenants.every(t => typeof t.id === 'string' && typeof t.host === 'string' && t.host.length > 0 && !/[\r\n]/.test(t.host) && typeof t.token === 'string' && t.token.length > 0), 'M7_SERIAL_EXCHANGE_COHORT');
    return tenants;
  }
  inputs();
  return {
    async phase(phase) {
      need((phase === 'before' && phases.length === 0) || (phase === 'after' && phases.length === 1 && phases[0] === 'before'), 'M7_SERIAL_EXCHANGE_PHASE_ORDER');
      const tenants = inputs(), startedAtMs = clock(), began = monotonic();
      const result = { kind: b.kind, version: 1, phase, selection: SELECTION, bindingSha256, owner: b.owner, pair: b.pair, imageId: b.imageId, instrument: b.instrument,
        actor: { pid: process.pid, nodeSha256: b.nodeSha256, actorSha256: b.actorSha256, concurrency: 1, retries: 0, keepAlive: true, maxSockets: 1 },
        method: 'GET', routeTemplate: '/api/v2/authorization/request/{data-token}', startedAtMs, requests: [], status: 'PHASE_DEADLINE' };
      for (let tenantIndex = 0; tenantIndex < SELECTION.tenants; tenantIndex++) {
        const remaining = SELECTION.phaseSeconds * 1000 - (monotonic() - began);
        if (remaining <= 0) break;
        const t = tenants[tenantIndex], requestStartedAtMs = clock(), requestBegan = monotonic(), timeoutMs = Math.min(SELECTION.requestSeconds * 1000, remaining);
        let response;
        try { response = await request({ hostname: base.hostname, port: base.port, method: 'GET', path: '/api/v2/authorization/request/' + encodeURIComponent(t.token), headers: { Host: t.host, Accept: 'application/json' } }, timeoutMs); }
        catch (_) { response = { status: 0, transport: 'REQUEST_TRANSPORT_ERROR' }; }
        const status = Number.isInteger(response.status) && response.status >= 0 && response.status <= 599 ? response.status : 0;
        const safe = status > 0 ? safeResponse({ ...response, status }) : { errorCode: null, bodyObservation: 'NO_HTTP_RESPONSE', retryAfterSeconds: null };
        const transport = ['REQUEST_TIMEOUT','REQUEST_TRANSPORT_ERROR','RESPONSE_TRANSPORT_ERROR'].includes(response.transport) ? response.transport : status === 0 ? 'REQUEST_TRANSPORT_ERROR' : null;
        result.requests.push({ tenantIndex, requestOrdinal: tenantIndex + 1, tenantHash: hash(t.id), status, ...safe, transport, retryCount: 0, requestStartedAtMs, finishedAtMs: clock(), elapsedMs: monotonic() - requestBegan, timeoutMs });
        if (status !== 200) { result.status = status === 0 ? (transport === 'REQUEST_TIMEOUT' && timeoutMs < 60000 ? 'PHASE_DEADLINE' : 'TRANSPORT_FAILURE') : 'HTTP_REFUSED'; break; }
        if (tenantIndex === SELECTION.tenants - 1) result.status = 'COMPLETED_64';
      }
      result.finishedAtMs = clock(); result.elapsedMs = monotonic() - began;
      phases.push(phase); persist(phase, result);
      return result;
    },
    close() { agent.destroy(); }
  };
}
module.exports = { SELECTION, ALLOWED, safeResponse, createActor, requestOnce };
