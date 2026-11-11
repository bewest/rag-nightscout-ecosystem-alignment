'use strict';

// Evaluator cost lane: what the total order's tie-break costs on each path.
// One synthetic tenant shape (24 h of readings and device status, 576 rows,
// as profile.cjs), the loader's sorted reads (readings date asc, device status
// created_at desc, newest 12 readings), N times each:
//   sql-today   postgres-projection-read without the tie-break
//   sql-total   the same with ORDER BY ..., ordinal, id_kind, _id
//   memory      the in-process reader (always in total order)
// Reports wall ms per read and, for SQL, server execution time from EXPLAIN ANALYZE.
//
//   CRM_ROOT=<crm tree> NS_TEST_POSTGRES_ADMIN_URI=<disposable *_test db> N=200 node tiebreak-bench.cjs
const path = require('node:path');
const ROOT = process.env.CRM_ROOT;
const req = p => require(path.join(ROOT, p));
const { Pool } = req('node_modules/pg');
const scope = req('lib/storage/tenant-scope');
const projectionRead = req('lib/storage/postgres-projection-read');
const environment = req('lib/server/tenant-app/environment');
const { fromMongo } = req('lib/storage/filter');
const TENANT = '7e7e7e7e-0000-4000-8000-00000000eca5';
const N = Number(process.env.N || 200), MIN = 60000, iso = ms => new Date(ms).toISOString();

(async () => {
  const pool = new Pool({ connectionString: process.env.NS_TEST_POSTGRES_ADMIN_URI, max: 1 });
  const env = environment({ settings: { enable: ['bgnow'] } });
  scope.setTenancyMode('multi');
  const now = Date.UTC(2026, 10, 11), entries = [], statuses = [];
  for (let at = now - 24 * 60 * MIN; at < now; at += 5 * MIN) {
    entries.push({ _id: 'sgv-' + at, type: 'sgv', sgv: 120, date: at, dateString: iso(at) });
    statuses.push({ _id: 'ds-' + at, created_at: iso(at), device: 'synthetic', uploader: { battery: 50 }, loop: { timestamp: iso(at), iob: { iob: 1 } } });
  }
  const reads = [['entries', entries, { date: { $gte: now - 2 * 24 * 60 * MIN } }, { date: 1 }, undefined],
    ['devicestatus', statuses, { created_at: { $gte: iso(now - 24 * 60 * MIN) } }, { created_at: -1 }, undefined],
    ['entries', entries, { type: 'sgv' }, { date: -1 }, 12]];
  const bounds = { maxRows: 10000, maxBytes: 1e8 };
  let explained = 0;
  const connection = { async query (text, values) {
    if (explained) { const r = await pool.query('EXPLAIN (ANALYZE, FORMAT JSON) ' + text, values); explained += r.rows[0]['QUERY PLAN'][0]['Execution Time']; }
    return pool.query(text, values);
  } };
  await scope.withTenant(TENANT, async () => {
    for (const [logical, docs, filter, sort, limit] of reads) {
      const prepared = projectionRead.prepare({ documents: docs, ordinals: docs.map((_, i) => i + 1), ...bounds, memory: true });
      const arms = {
        'sql-today': projectionRead({ tenant: TENANT, connection, logical, documents: docs, ...bounds, env }),
        'sql-total': projectionRead({ tenant: TENANT, connection, logical, prepared, ...bounds, env, totalOrder: true }),
        memory: projectionRead({ tenant: TENANT, connection, logical, prepared, ...bounds, env, memory: true, totalOrder: true })
      };
      const opts = { v1: true, sort, ...(limit ? { limit } : {}), options: { normalize: false } };
      const line = { read: logical + ' ' + JSON.stringify(sort) + (limit ? ' limit ' + limit : ''), rows: docs.length };
      for (const [name, store] of Object.entries(arms)) {
        for (let i = 0; i < 20; i++) await store.findFiltered(fromMongo(filter), opts);
        const t = process.hrtime.bigint();
        for (let i = 0; i < N; i++) await store.findFiltered(fromMongo(filter), opts);
        line[name + ' wallMs'] = +(Number(process.hrtime.bigint() - t) / 1e6 / N).toFixed(3);
        if (name !== 'memory') {
          explained = 1e-9;
          for (let i = 0; i < 50; i++) await store.findFiltered(fromMongo(filter), opts);
          line[name + ' execMs'] = +((explained - 1e-9) / 50).toFixed(3);
          explained = 0;
        }
      }
      process.stdout.write('TIEBREAK ' + JSON.stringify(line) + '\n');
    }
  });
  process.stdout.write('LOAD ' + require('node:os').loadavg().map(x => x.toFixed(2)).join(' ') + '\n');
  await pool.end();
})().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exit(1); });
