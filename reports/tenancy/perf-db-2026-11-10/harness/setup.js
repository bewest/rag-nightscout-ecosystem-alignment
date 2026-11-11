'use strict';
// Focused perf-db lab: disposable PostgreSQL 16 (ns-pdb-*), the deployment plan's
// catalogue and grants (as admin-lifecycle-fit applies them), N synthetic tenants.
// Usage: node setup.js <crm-tree> <container> <tenants>  -> prints JSON {urls, layout, locks}
// The printed JSON holds the disposable lab's generated credentials: keep it private.
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const tree = path.resolve(process.argv[2]);
const container = process.argv[3];
const N = Number(process.argv[4] || 2);
const { Client } = require(path.join(tree, 'node_modules/pg'));
const { run } = require(path.join(tree, 'lib/migrations/postgres'));
const plan = require(path.join(tree, 'deploy/multitenant/config'));
const IMAGE = process.env.LAB_PG_IMAGE || 'postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea';
const docker = (args, env) => execFileSync('docker', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], ...(env ? { env } : {}) }).trim();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const uuid = i => { const h = crypto.createHash('sha256').update('perf-db-tenant-' + i).digest('hex'); return h.slice(0, 8) + '-' + h.slice(8, 12) + '-4' + h.slice(13, 16) + '-8' + h.slice(17, 20) + '-' + h.slice(20, 32); };
(async () => {
  const password = crypto.randomBytes(24).toString('hex');
  docker(['run', '--name', container, '--label', 'nightscout.lab=perf-db', '-d', '-p', '127.0.0.1::5432', '-e', 'POSTGRES_USER=bootstrap', '-e', 'POSTGRES_PASSWORD',
    '-e', 'POSTGRES_DB=nightscout_pdb', IMAGE, '-c', 'shared_preload_libraries=pg_stat_statements', '-c', 'pg_stat_statements.track=all', '-c', 'max_connections=400'], { ...process.env, POSTGRES_PASSWORD: password });
  const port = docker(['port', container, '5432/tcp']).split(':').pop();
  const boot = 'postgres://bootstrap:' + password + '@127.0.0.1:' + port + '/nightscout_pdb';
  const asBoot = async (fn, uri = boot) => { const c = new Client({ connectionString: uri }); await c.connect(); try { return await fn(c); } finally { await c.end(); } };
  for (let i = 0; ; i++) { try { await asBoot(async () => {}); break; } catch (e) { if (i > 150) throw e; await sleep(200); } }
  await sleep(1500);
  for (let i = 0; ; i++) { try { await asBoot(async () => {}); break; } catch (e) { if (i > 150) throw e; await sleep(200); } }
  // pg_stat_statements in the postgres database only (creating it in the app database breaks admission).
  await asBoot(c => c.query('CREATE EXTENSION IF NOT EXISTS pg_stat_statements'), boot.replace(/\/nightscout_pdb$/, '/postgres'));
  const l = plan.layout('pdb'), ns = l.namespaces, q = plan.quote, urls = {};
  const locks = Array.from({ length: N }, (_, i) => ({ tenant: uuid(i), key: String(900001 + i) }));
  await asBoot(async admin => {
    await admin.query('REVOKE CREATE ON SCHEMA public FROM PUBLIC');
    await admin.query('REVOKE CREATE ON DATABASE "nightscout_pdb" FROM PUBLIC');
    await admin.query('CREATE ROLE ' + q(l.owner) + ' NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION');
    for (const [kind, name] of Object.entries(l.roles)) {
      const secret = crypto.randomBytes(24).toString('hex');
      await admin.query('CREATE ROLE ' + q(name) + " LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '" + secret + "'");
      const url = new URL(boot); url.username = name; url.password = secret; urls[kind] = url.toString();
    }
    for (const [kind, catalogue] of Object.entries(plan.catalogues())) {
      const namespace = ns[kind]; await admin.query('CREATE SCHEMA ' + q(namespace));
      await run('up', { direct: true, connectionString: boot, namespace, catalogue, statementTimeoutMs: 10000 });
      for (const row of (await admin.query('SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname=$1', [namespace])).rows) await admin.query('ALTER TABLE ' + q(namespace) + '.' + q(row.tablename) + ' OWNER TO ' + q(l.owner));
      for (const row of (await admin.query('SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=$1', [namespace])).rows) await admin.query('ALTER FUNCTION ' + q(namespace) + '.' + q(row.proname) + '() OWNER TO ' + q(l.owner));
      await admin.query('ALTER SCHEMA ' + q(namespace) + ' OWNER TO ' + q(l.owner));
    }
    for (const sql of plan.grants(l)) await admin.query(sql);
    for (const row of locks) await admin.query('INSERT INTO ' + q(ns.control) + ".tenant_lifecycle_windows(tenant_id,lock_key,phase,generation) VALUES($1,$2,'active',1)", [row.tenant, row.key]);
  });
  process.stdout.write(JSON.stringify({ container, boot, postgres: boot.replace(/\/nightscout_pdb$/, '/postgres'), urls, layout: l, locks }) + '\n');
})().catch(e => { console.error(e); process.exit(1); });
