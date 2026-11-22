'use strict';
// Storage-path history loader. Synthetic data only.
//
// Runs inside the application image (cwd /opt/app), in an api container of a
// disposable deployment, with that container's own environment. It boots the
// api role exactly as `nightscout multitenant api` does (lib/server/serve
// start: configuration, operation window, readiness, write clock with the
// writer-driven pending binding and its post-commit hint), on loopback
// ephemeral listeners that nothing calls, and captures the tenant domain
// services it builds. Each batch is then written through the shipping v1
// domain function the POST handler calls (ctx.<collection>.create), inside
// the same registry record, operation window and tenant scope a request
// holds. It skips the edge, HTTP parsing, REST admission and credential
// verification; storage, normalisation, server dates, the write clock, the
// pending mark, ordinals and every trigger are the product's own.
//
// stdin: NDJSON, one batch per line: {"t": tenant, "c": collection, "d": [docs]}.
// A tenant's batches are contiguous and applied in order; up to WORKERS
// tenants run at once. stdout: NDJSON progress, then {"done": {...}}.
// Never prints a document, tenant id or credential.

const path = require('node:path');
const readline = require('node:readline');
const { EventEmitter } = require('node:events');

const APP = process.env.NS_LOADER_APP || '/opt/app';
const WORKERS = Number(process.env.NS_LOADER_WORKERS || 8);
const PROGRESS_MS = Number(process.env.NS_LOADER_PROGRESS_MS || 10000);
const COLLECTIONS = new Set(['entries', 'devicestatus', 'treatments', 'profile']);

function out (value) { process.stdout.write(JSON.stringify(value) + '\n'); }
function fail (code, error) {
  out({ error: code, detail: error ? String(error.code || error.name || 'Error') : undefined,
    // Configuration refusals name settings, never values; storage errors carry no documents.
    message: error && /CONFIG|LISTENER|CAPTURE/.test(String(error.code)) ? String(error.message).slice(0, 300) : undefined });
  process.exit(2);
}
const lib = name => require(path.join(APP, 'lib', name));

// Capture the domain services and the config the api builds, without changing them. Installed
// before preview-api is first required, which binds './preview-domains' at load.
let captured = null;
function interceptDomains () {
  const domainsPath = require.resolve(path.join(APP, 'lib/server/serve/preview-domains'));
  const real = require(domainsPath);
  require.cache[domainsPath].exports = async function capture (args) {
    const domains = await real(args);
    captured = { domains, config: args.config, connection: args.connection };
    return domains;
  };
}

async function boot () {
  const source = { ...process.env,
    // Loopback listeners of its own that nothing calls (the container's api holds 1337/7001).
    API_HOSTNAME: '127.0.0.1', API_PORT: process.env.NS_LOADER_API_PORT || '18337',
    NS_SERVE_INTERNAL_HOST: '127.0.0.1', NS_SERVE_INTERNAL_PORT: process.env.NS_LOADER_INTERNAL_PORT || '17001',
    NS_SERVE_INTERNAL_SOCKET: '', NS_API_INTERNAL_URL: 'http://127.0.0.1:' + (process.env.NS_LOADER_INTERNAL_PORT || '17001'),
    NS_API_REST_CONCURRENCY: '', NS_API_REST_QUEUE: '', NS_METRICS: 'false', NS_M7_DIAGNOSTICS: '0' };
  lib('server/runtime-policy')();
  const multitenant = lib('cli/commands/multitenant');
  const loaded = multitenant.configure(['api'], source);
  const env = { HOSTNAME: '127.0.0.1', PORT: 0 };
  const running = await lib('server/serve').start(['api'], env, undefined, source, loaded);
  if (!captured) throw Object.assign(new Error('domain services not captured'), { code: 'LOADER_CAPTURE' });
  // generationScope, when the role has an operation lease: the api's createTenantApp receives it as
  // operationWindow. serve/index keeps it private, so read it back from the connection module's
  // installed window through the tenant app's own dependency: the preview-api boot was given it.
  return { running, ...captured, window: captureWindow.value };
}

// serve/index passes the operation window to preview-api.boot; capture it there too.
const captureWindow = { value: undefined };
function interceptApiBoot () {
  const apiPath = require.resolve(path.join(APP, 'lib/server/serve/preview-api'));
  const api = require(apiPath);
  const boot = api.boot;
  require.cache[apiPath].exports = { ...api, boot: (config, options = {}) => {
    captureWindow.value = options.operationWindow;
    return boot(config, options);
  } };
}

async function main () {
  process.chdir(APP);
  // Product log lines go to stderr; stdout carries only this loader's NDJSON.
  for (const level of ['log', 'info', 'debug']) console[level] = (...args) => console.error(...args);
  interceptDomains();
  interceptApiBoot();
  let state;
  try { state = await boot(); } catch (error) { return fail('LOADER_BOOT', error); }
  const { domains, config, window, running } = state;
  const scope = lib('storage/tenant-scope');
  const purifier = lib('server/purifier');
  const createData = lib('data/ddata');
  const createLegacy = lib('server/tenant-app/legacy-domains');
  const validation = lib('server/write-validation');
  const legacyNames = domains.legacyNames;
  for (const name of COLLECTIONS) if (!legacyNames.includes(name)) return fail('LOADER_DOMAIN_NOT_SERVED');
  const EMPTY = Object.freeze([]);
  const EMPTY_CACHE = Object.freeze({ entries: EMPTY, treatments: EMPTY, devicestatus: EMPTY, getDataRef: () => [] });

  const totals = { rows: 0, batches: 0, tenants: 0, byCollection: {} };
  const started = Date.now();

  // One tenant: the request's bindings, then each batch through the domain's create.
  function inTenant (tenant, fn) {
    const body = () => scope.withTenant(tenant, fn);
    const windowed = window ? () => window.run(tenant, body) : body;
    return config.runRegistryTenant ? config.runRegistryTenant(tenant, windowed) : windowed();
  }
  // The refusals the api answers 503 (Retry-After) because nothing committed, plus the lifecycle
  // scope refusal a withdrawn admission raises (datastore probe lost under load): the HTTP seed resends
  // those, so the loader resends the batch as sent (a fresh copy: create() mutates its documents).
  const RETRYABLE = new Set(['STORAGE_TIMEOUT', 'STORAGE_BUSY', 'STORAGE_UNAVAILABLE', 'TENANT_ACTIVITY_UNAVAILABLE',
    'LIFECYCLE_WINDOW_SUSPENDED', 'LIFECYCLE_WINDOW_SCOPE_INVALID', 'API_TENANT_BUILD_OVERLOADED', 'TENANT_WARMING']);
  const ATTEMPTS = Number(process.env.NS_LOADER_ATTEMPTS || 8);
  const retryCodes = {};
  async function loadTenant (tenant, batches) {
    let next = 0, attempt = 0;
    while (next < batches.length) {
      try {
        await inTenant(tenant, async () => {
          const service = await domains.prepareTenant(tenant);
          // The raw POST path's request frame (preview-domains legacyRouter): a private bus, an empty
          // raw cache and a lazy ddata; the storage ports are the tenant's own.
          const ctx = { storagePorts: service.storagePorts, purifier: purifier({}, {}), bus: new EventEmitter(),
            cache: EMPTY_CACHE, ddata: createData() };
          const graph = createLegacy({ env: service.env, ctx, domains: legacyNames });
          for (; next < batches.length; next++) {
            const { c, d } = batches[next];
            const docs = structuredClone(d);
            if (c === 'treatments' || c === 'profile') docs.forEach(doc => ctx.purifier.purifyObject(doc)); // handler step
            const created = await new Promise((resolve, reject) => {
              const done = (err, result) => err ? reject(err) : resolve(result || []);
              if (c === 'profile') graph.context.profile.create(docs, done, { canUpdate: true });
              else graph.context[c].create(docs, done);
            });
            const refused = created.filter(slot => validation.isRefusal(slot)).length;
            if (refused) throw Object.assign(new Error('refused'), { code: 'LOADER_REFUSED_' + c.toUpperCase() });
            totals.rows += docs.length; totals.batches += 1;
            totals.byCollection[c] = (totals.byCollection[c] || 0) + docs.length;
            attempt = 0;
          }
        });
      } catch (error) {
        const code = error && (error.code || error.cause?.code);
        if (!RETRYABLE.has(code) || ++attempt >= ATTEMPTS) throw error;
        retryCodes[code] = (retryCodes[code] || 0) + 1;
        await new Promise(resolve => setTimeout(resolve, Math.min(15000, 500 * 2 ** attempt)));
      }
    }
    totals.tenants += 1;
  }

  const active = new Set();
  let failure = null;
  const timer = setInterval(() => out({ progress: { ...totals, seconds: (Date.now() - started) / 1000 } }), PROGRESS_MS);
  function launch (tenant, batches) {
    const p = loadTenant(tenant, batches).catch(error => { failure = failure || error; }).finally(() => active.delete(p));
    active.add(p);
  }
  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  let current = null, pending = [];
  for await (const line of rl) {
    if (failure) break;
    if (!line) continue;
    let batch;
    try { batch = JSON.parse(line); } catch { failure = Object.assign(new Error('bad line'), { code: 'LOADER_INPUT' }); break; }
    if (typeof batch.t !== 'string' || !COLLECTIONS.has(batch.c) || !Array.isArray(batch.d) || !batch.d.length) {
      failure = Object.assign(new Error('bad batch'), { code: 'LOADER_INPUT' }); break;
    }
    if (batch.t !== current) {
      if (current !== null) {
        while (active.size >= WORKERS && !failure) await Promise.race(active);
        launch(current, pending);
      }
      current = batch.t; pending = [];
    }
    pending.push(batch);
  }
  if (!failure && current !== null) launch(current, pending);
  await Promise.allSettled([...active]);
  while (active.size) await Promise.allSettled([...active]);
  clearInterval(timer);
  const seconds = (Date.now() - started) / 1000;
  try { await running.stop(); } catch { /* the process exits below */ }
  if (failure) return fail(failure.code && /^[A-Z_]+$/.test(failure.code) ? failure.code : 'LOADER_WRITE', failure);
  out({ done: { ...totals, seconds, rowsPerSecond: Math.round(totals.rows / Math.max(seconds, 0.001)), workers: WORKERS, retries: retryCodes,
    bindings: { operationWindow: !!window, registry: !!config.runRegistryTenant, writerDriven: !!config.writerDriven,
      activityGate: !!config.activity, writeClock: !!config.writeClock } } });
  process.exit(0);
}

main().catch(error => fail('LOADER_INTERNAL', error));
