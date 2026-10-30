'use strict';
// Part 1: does a v1 delete-by-query on treatments empty all three caches?
//
// Boots cgm-remote-monitor in-process (as lib/server/server.js does, without
// the websocket) against a seeded synthetic database, then runs four actions
// and profiles (MongoDB profiler level 2) the reload each one triggers:
//   warm-reload          bus 'data-received' with nothing changed (baseline)
//   delete-by-id         DELETE /api/v1/treatments/<id>  (per-record path)
//   delete-by-query      DELETE /api/v1/treatments/?find[eventType]=Note (3 records)
//   warm-reload-after    baseline again, once the caches have refilled
//   delete-by-query-none DELETE /api/v1/treatments/?find[eventType]=cv-lab-none (0 records)
//
//   CRM_DIR=<tree> MONGODB_URI=mongodb://127.0.0.1:27801/cvp1 node overflush.js [--control] [--out file]
//
// --control: exit 1 when a treatments delete-by-query empties the entries or
// devicestatus cache, or makes the next reload a long load for them.
// API_SECRET is generated here and never written out.

const fs = require('fs');
const path = require('path');
const C = require('./common');

const args = process.argv.slice(2);
const CONTROL = args.includes('--control');
const OUT = args.includes('--out') ? path.resolve(args[args.indexOf('--out') + 1]) : null;
const uri = process.env.MONGODB_URI;
if (!uri) throw new Error('MONGODB_URI is required');

const secret = C.newSecret();
Object.assign(process.env, {
  API_SECRET: secret, HEARTBEAT: '3600', AUTH_DEFAULT_ROLES: 'denied', INSECURE_USE_HTTP: 'true'
  , DISPLAY_UNITS: 'mg/dl', TZ: 'UTC', ENABLE: 'careportal basal iob cob devicestatus openaps pump'
  , ALARM_HIGH: 'off', ALARM_LOW: 'off', ALARM_URGENT_HIGH: 'off', ALARM_URGENT_LOW: 'off'
  , ALARM_TIMEAGO_WARN: 'off', ALARM_TIMEAGO_URGENT: 'off'
});
process.chdir(C.CRM_DIR);

function sizes (ctx) {
  return { treatments: ctx.cache.treatments.length, devicestatus: ctx.cache.devicestatus.length, entries: ctx.cache.entries.length
    , generations: { treatments: ctx.cache.getRemovalGeneration('treatments'), devicestatus: ctx.cache.getRemovalGeneration('devicestatus'), entries: ctx.cache.getRemovalGeneration('entries') } };
}

function findGte (o) {
  if (!o || typeof o !== 'object') return undefined;
  if (Object.prototype.hasOwnProperty.call(o, '$gte')) return o.$gte;
  for (const k of Object.keys(o)) { const v = findGte(o[k]); if (v !== undefined) return v; }
  return undefined;
}

async function profileStart (db) {
  await db.command({ profile: 0 });
  await db.collection('system.profile').drop().catch(() => {});
  await db.createCollection('system.profile', { capped: true, size: 256 * 1024 * 1024 });
  await db.command({ profile: 2 });
}

async function profileRead (db, since) {
  await db.command({ profile: 0 });
  const docs = await db.collection('system.profile').find({ ts: { $gte: new Date(since) }, appName: { $ne: 'cv-probe' } }).toArray();
  const byNs = {};
  const queries = [];
  for (const d of docs) {
    const ns = d.ns.split('.').slice(1).join('.');
    const k = ns + ' ' + d.op;
    byNs[k] = byNs[k] || { ops: 0, nreturned: 0, responseLength: 0 };
    byNs[k].ops += 1;
    byNs[k].nreturned += d.nreturned || 0;
    byNs[k].responseLength += d.responseLength || 0;
    if (d.op === 'query' && ['entries', 'treatments', 'devicestatus'].includes(ns)) {
      const gte = findGte(d.command && d.command.filter);
      const t = typeof gte === 'number' ? gte : (gte ? Date.parse(gte) : NaN);
      queries.push({ ns, windowHours: Number.isFinite(t) ? +((since - t) / C.HOUR).toFixed(2) : null
        , limit: d.command && d.command.limit, nreturned: d.nreturned, responseLength: d.responseLength });
    }
  }
  const totals = Object.values(byNs).reduce((a, v) => ({ ops: a.ops + v.ops, nreturned: a.nreturned + v.nreturned, responseLength: a.responseLength + v.responseLength }), { ops: 0, nreturned: 0, responseLength: 0 });
  return { totals, byNs, queries };
}

function waitLoaded (ctx, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('no data-loaded within ' + ms + ' ms')), ms);
    ctx.bus.once('data-loaded', () => { clearTimeout(timer); resolve(); });
  });
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function main () {
  const now = Date.now();
  const seeded = await C.seed(uri, now);
  const probe = await C.MongoClient.connect(uri, { appName: 'cv-probe' });
  const db = probe.db();
  // Three Notes for the delete-by-query, within the last 6 hours.
  await db.collection('treatments').insertMany([1, 2, 3].map(h => ({ eventType: 'Note', notes: 'cv-lab', enteredBy: 'cv-lab', created_at: new Date(now - h * C.HOUR).toISOString() })));
  seeded.treatments += 3;
  const serverVersion = (await db.admin().serverInfo()).version;

  const env = require(path.join(C.CRM_DIR, 'lib/server/env'))();
  const language = require(path.join(C.CRM_DIR, 'lib/language'))();
  language.set(env.settings.language);
  language.loadLocalization(fs);

  const ctx = await new Promise(resolve => require(path.join(C.CRM_DIR, 'lib/server/bootevent'))(env, language).boot(resolve));
  if (ctx.bootErrors && ctx.bootErrors.length) throw new Error('boot errors: ' + JSON.stringify(ctx.bootErrors));
  const app = require(path.join(C.CRM_DIR, 'lib/server/app'))(env, ctx);
  const server = await new Promise(resolve => { const s = app.listen(0, '127.0.0.1', () => resolve(s)); });
  const base = 'http://127.0.0.1:' + server.address().port;
  const headers = { 'api-secret': C.secretHash(secret) };

  for (let i = 0; i < 100 && ctx.runtimeState !== 'loaded'; i++) await sleep(100);
  await sleep(2000);
  const afterBoot = sizes(ctx);

  const anyId = (await db.collection('treatments').findOne({ eventType: 'Correction Bolus' }, { sort: { created_at: -1 } }))._id.toHexString();

  const actions = [
    ['warm-reload', async () => { ctx.bus.emit('data-received'); return null; }]
    , ['delete-by-id', async () => (await fetch(base + '/api/v1/treatments/' + anyId, { method: 'DELETE', headers })).status]
    , ['delete-by-query', async () => (await fetch(base + '/api/v1/treatments/?find[eventType]=Note', { method: 'DELETE', headers })).status]
    , ['warm-reload-after', async () => { ctx.bus.emit('data-received'); return null; }]
    , ['delete-by-query-none', async () => (await fetch(base + '/api/v1/treatments/?find[eventType]=cv-lab-none', { method: 'DELETE', headers })).status]
  ];

  const results = [];
  for (const [name, act] of actions) {
    const before = sizes(ctx);
    await profileStart(db);
    const since = Date.now();
    let loads = 0; const count = () => { loads += 1; };
    ctx.bus.on('data-loaded', count);
    const loaded = waitLoaded(ctx, 30000);
    const status = await act();
    const immediately = sizes(ctx);
    await loaded;
    await sleep(1500);
    ctx.bus.removeListener('data-loaded', count);
    const afterReload = sizes(ctx);
    const profile = await profileRead(db, since);
    results.push({ action: name, httpStatus: status, before, immediately, afterReload, loads, profile });
  }

  // Scope check for the treatments delete-by-query.
  const q = results.find(r => r.action === 'delete-by-query');
  const failures = [];
  for (const col of ['entries', 'devicestatus']) {
    if (q.immediately[col] < q.before[col]) failures.push(`${col} cache emptied by a treatments delete-by-query: before ${q.before[col]}, after ${q.immediately[col]}`);
    if (q.immediately.generations[col] !== q.before.generations[col]) failures.push(`${col} removal generation bumped by a treatments delete-by-query: ${q.before.generations[col]} -> ${q.immediately.generations[col]}`);
    const long = q.profile.queries.filter(x => x.ns === col && x.windowHours != null && x.windowHours > 1);
    if (long.length) failures.push(`${col} reloaded with a long load after a treatments delete-by-query: window ${long.map(x => x.windowHours).join(',')} h`);
  }

  const crmHead = require('child_process').execSync('git rev-parse HEAD', { cwd: C.CRM_DIR }).toString().trim();
  const crmDiff = require('child_process').execSync('git diff --stat', { cwd: C.CRM_DIR }).toString().trim();
  const out = { at: new Date().toISOString(), crmHead, crmDiff: crmDiff || '(none)', node: process.version, serverVersion, uri: uri.replace(/\/\/.*@/, '//'), seeded, afterBoot, results, scopeCheck: failures.length ? 'FAIL' : 'PASS', failures };
  if (OUT) fs.writeFileSync(OUT, JSON.stringify(out, null, 2) + '\n');

  console.log(`crm ${crmHead.slice(0, 8)} diff: ${crmDiff ? crmDiff.split('\n').pop() : 'none'} | mongo ${serverVersion} | node ${process.version}`);
  console.log('after boot', JSON.stringify(afterBoot));
  for (const r of results) {
    const main = r.profile.queries.map(x => `${x.ns}:${x.windowHours}h/${x.nreturned}`).join(' ');
    console.log(`${r.action.padEnd(21)} http=${r.httpStatus} loads=${r.loads} before=${r.before.treatments}/${r.before.devicestatus}/${r.before.entries} immediately=${r.immediately.treatments}/${r.immediately.devicestatus}/${r.immediately.entries} after=${r.afterReload.treatments}/${r.afterReload.devicestatus}/${r.afterReload.entries} ops=${r.profile.totals.ops} docs=${r.profile.totals.nreturned} bytes=${r.profile.totals.responseLength} | ${main}`);
  }
  console.log('scope check:', out.scopeCheck);
  for (const f of failures) console.log('  FAIL: ' + f);

  ctx.bus.teardown();
  server.close();
  await probe.close();
  setTimeout(() => process.exit(CONTROL && failures.length ? 1 : 0), 500);
}

main().catch(err => { console.error(err); process.exit(2); });
