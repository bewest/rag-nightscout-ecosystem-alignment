'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { safeCode } = require('./api-cause.cjs');

const SOURCE = 'lib/server/serve/tenant-startup.js';
const MAX_EVENTS = 32;
const EXTRA_MESSAGES = Object.freeze({
  'Query read timeout': 'PG_QUERY_READ_TIMEOUT',
  'timeout expired': 'PG_CONNECT_TIMEOUT',
  'incomplete preview root preparation': 'PREVIEW_ROOT_PREPARATION_INCOMPLETE'
});
const STARTUP_CODES = new Set(['TENANT_WARM_FAILED', 'TENANT_COLD_BEYOND_BOUND', 'TENANT_ACTIVITY_DEFERRED']);

function originCode(error) {
  if (!Object.getOwnPropertyDescriptor(error || {}, 'code')) {
    const message = Object.getOwnPropertyDescriptor(error || {}, 'message')?.value;
    if (typeof message === 'string' && Object.hasOwn(EXTRA_MESSAGES, message)) return EXTRA_MESSAGES[message];
  }
  return safeCode(error);
}

function attach(target, publish, armed, now = Date.now, observe = () => {}) {
  const descriptor = Object.getOwnPropertyDescriptor(target, 'create');
  if (!descriptor?.writable || typeof descriptor.value !== 'function') throw Error('M7_API_WARM_EXPORT');
  const create = function (tenants, operationWindow, initialize, options) {
    // Keep only classified initializer failures in RAM, indexed by the same
    // internal tenant key the startup component uses. No identifier is emitted.
    const failed = new Map();
    const observedInit = function (tenant) {
      const reject = error => {
        if (failed.has(tenant) || failed.size < 10000) failed.set(tenant, originCode(error));
      };
      let result;
      try { result = Reflect.apply(initialize, this, arguments); }
      catch (error) { try { reject(error); } catch {} throw error; }
      if (result instanceof Promise) {
        try { Promise.prototype.then.call(result, () => failed.delete(tenant), error => {
          try { reject(error); } catch {}
        }); } catch {}
      }
      return result;
    };
    const startup = Reflect.apply(descriptor.value, this, [tenants, operationWindow, observedInit, options]);
    observe(startup);
    let count = 0;
    const admit = function (tenant, req) {
      const result = Reflect.apply(startup.admit, startup, arguments);
      if (result instanceof Promise) {
        try { Promise.prototype.then.call(result, undefined, error => {
          try {
            if (safeCode(error) !== 'TENANT_UNAVAILABLE' || req?.method !== 'GET' ||
                req.path !== '/api/v2/authorization/roles' || !armed()) return;
            // Record the actual typed refusal and same-tenant health before the
            // error returns to HTTP. Keep only fixed outcome symbols.
            const atMs = now();
            const alerts = count < MAX_EVENTS ? startup.health().alerts.filter(
              row => row.tenant === tenant && row.code === 'TENANT_WARM_FAILED') : [];
            const cause = alerts.length === 1 ? alerts[0].cause : undefined;
            const healthCause = STARTUP_CODES.has(cause) ? cause : safeCode({ code: cause });
            const initializerCause = failed.get(tenant) || 'UNMEASURED';
            count++;
            req.res.once('finish', () => {
              try {
                publish({ atMs, responseAtMs: now(), status: req.res.statusCode,
                  healthCause, initializerCause, overflow: count > MAX_EVENTS });
              } catch {}
            });
          } catch {}
        }); } catch {}
      }
      return result;
    };
    return Object.freeze({ ...startup, admit });
  };
  Object.defineProperty(target, 'create', { ...descriptor, value: create });
  return () => Object.defineProperty(target, 'create', descriptor);
}

function startupSample(startups) {
  const memory = process.memoryUsage();
  const limit = file => { try { const value=fs.readFileSync(file,'utf8').trim();return value==='max' ? 'max' : /^[0-9]+$/.test(value) ? value : null; } catch { return null; } };
  return {atMs:Date.now(),heapUsed:memory.heapUsed,rss:memory.rss,
    heapSizeLimit:require('node:v8').getHeapStatistics().heap_size_limit,
    cgroupMemoryMax:limit('/sys/fs/cgroup/memory.max'),cgroupMemoryCurrent:limit('/sys/fs/cgroup/memory.current'),
    components:startups.map(startup => {
      const health=startup.health(),row={readiness:health.readiness,ready:health.ready===true};
      for(const key of ['configured','warming','cold','queued','deferred','failed']) if(Number.isSafeInteger(health[key])&&health[key]>=0) row[key]=health[key];
      if(Number.isSafeInteger(row.configured)&&['warming','cold','deferred','failed'].every(key=>Number.isSafeInteger(row[key]))) {
        const initialized=row.configured-row.warming-row.cold-(row.queued||0)-row.deferred-row.failed;
        if(initialized>=0)row.initialized=initialized;
      }
      return row;
    })};
}

function run() {
  const file = process.env.M7_API_WARM_CONFIG;
  if (!file) return;
  const bytes = fs.readFileSync(file);
  if (bytes.length > 4096 || process.argv[2] !== 'api') throw Error('M7_API_WARM_CONFIG');
  const config = JSON.parse(bytes);
  const source = path.join('/opt/app',SOURCE);
  const digest = crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex');
  if (config.sourceSha256 !== digest || !/^[a-f0-9]{32}$/.test(config.owner)) throw Error('M7_API_WARM_SOURCE');
  const output = '/run/ns-api-warm-out';
  const events = [];
  const armed = () => {
    try {
      const signal = fs.readFileSync(output+'/prime-stage.json');
      if (signal.length > 512) return false;
      const phase = JSON.parse(signal);
      return phase.owner === config.owner && Number.isSafeInteger(phase.fromMs) && Date.now() >= phase.fromMs
        && Date.now() - phase.fromMs <= 1800000;
    } catch { return false; }
  };
  function publish(event) {
    if (events.length < MAX_EVENTS) events.push(event);
    const data = JSON.stringify({ ...config, events, overflow: event.overflow, pid: process.pid })+'\n';
    const temp = output+'/captures.partial';
    fs.writeFileSync(temp, data, { mode:0o600 });
    fs.renameSync(temp,output+'/captures.json');
  }
  if (config.startupObservation) {
    const startups = [], samples = [], first = [];
    let sampleCount = 0;
    function capture() {
      try {
        const row = startupSample(startups);
        sampleCount++;
        if (first.length < 2) first.push(row);
        samples.push(row);if (samples.length > 64) samples.shift();
        const temp = output+'/startup-samples.partial';
        fs.writeFileSync(temp,JSON.stringify({...config,pid:process.pid,sampleCount,first,samples})+'\n',{mode:0o600});
        fs.renameSync(temp,output+'/startup-samples.json');
      } catch { /* observer failure never changes application behavior */ }
    }
    capture();
    const timer = setInterval(capture,1000);timer.unref();
    attach(require(source),publish,armed,Date.now,startup => { startups.push(startup);capture(); });
  } else attach(require(source), publish, armed);
}

run();
module.exports = { attach, originCode, startupSample };
