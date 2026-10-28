'use strict';
// Migration-tool comparison (maintainer, 2026-10-27): umzug and node-pg-migrate
// on PostgreSQL; umzug (project ledger + lease lock) and migrate-mongo on
// MongoDB. Same properties for every arm:
//
//   P1 up, down to zero, up again
//   P2 runner killed mid-migration: committed-but-unrecorded or not; re-run
//   P3 four runners at once, with and without the tool's own locking
//   P4 an applied migration file edited: detected, ignored or re-run
//   P5 callable as a library from a CommonJS `nightscout migrate` dispatcher
//
// Every measurement carries its own non-vacuity check (the kill landed during
// the migration; the four runs overlapped; the edited file had been applied),
// and a measurement whose check fails is reported INVALID, not as a result.
//
//   node compare.js --secrets DIR [--pg-port 5447] [--mongo-port 27747] [--only P1,P3]

const fs = require('node:fs');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { MongoClient } = require('mongodb');
const { Lab, assertContainerRunning } = require('./lib/db');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };
const SECRETS = opt('secrets');
const PG_PORT = Number(opt('pg-port', '5447'));
const MONGO_PORT = Number(opt('mongo-port', '27747'));
const ONLY = opt('only') ? opt('only').split(',') : null;
if (!SECRETS || path.resolve(SECRETS).startsWith(path.resolve(__dirname, '..', '..', '..'))) {
  console.error('--secrets DIR (outside the repository) is required'); process.exit(2);
}
const J = (x) => JSON.stringify(x);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function assertMongoRunning () {
  const out = execFileSync('docker', ['inspect', '-f', '{{.State.Running}} {{json .NetworkSettings.Ports}} {{json .HostConfig.Ulimits}}', 'cfgschema-mongo'], { encoding: 'utf8' });
  if (!out.startsWith('true ')) throw new Error('cfgschema-mongo is not running');
  if (!out.includes(`"HostIp":"127.0.0.1","HostPort":"${MONGO_PORT}"`)) throw new Error(`cfgschema-mongo not on 127.0.0.1:${MONGO_PORT}`);
  if (!out.includes('"Hard":64000')) throw new Error('cfgschema-mongo was not started with --ulimit nofile=64000:64000');
}

let lab; let mongoUrl; let mongo; let scratch; let n = 0;

// ------------------------------------------------------------ fixtures

function pgDirFor (tool, edit) {
  const dir = fs.mkdtempSync(path.join(scratch, `${tool}-`));
  const src = path.join(__dirname, 'migrations');
  const names = fs.readdirSync(src).filter((f) => f.endsWith('.up.sql')).map((f) => f.replace('.up.sql', '')).sort();
  for (const name of names) {
    let up = fs.readFileSync(path.join(src, `${name}.up.sql`), 'utf8');
    const down = fs.readFileSync(path.join(src, `${name}.down.sql`), 'utf8');
    if (edit && edit.up) up = edit.up(name, up);
    if (tool === 'pgm') {
      fs.writeFileSync(path.join(dir, `${name}.sql`), `-- Up Migration\n${up}\n-- Down Migration\n${down}`);
    } else {
      fs.writeFileSync(path.join(dir, `${name}.up.sql`), up);
      fs.writeFileSync(path.join(dir, `${name}.down.sql`), down);
    }
  }
  return dir;
}
function mongoDir (edit) {
  const dir = fs.mkdtempSync(path.join(scratch, 'mongo-'));
  const src = path.join(__dirname, 'mongo-migrations');
  for (const f of fs.readdirSync(src)) {
    let body = fs.readFileSync(path.join(src, f), 'utf8');
    if (edit) body = edit(f, body);
    fs.writeFileSync(path.join(dir, f), body);
  }
  return dir;
}

async function freshPg () {
  const db = `cmp_${process.pid}_${n++}`;
  await lab.createDb(db);
  return { db, cfg: { host: '127.0.0.1', port: PG_PORT, user: 'cfg_owner', password: lab.passwords.cfg_owner, database: db } };
}
async function freshMongo () {
  const db = `cmp_${process.pid}_${n++}`;
  await mongo.db(db).dropDatabase();
  await mongo.db(db).collection('entries').insertOne({ type: 'sgv', sgv: 120, date: Date.now() });
  await mongo.db(db).collection('profile').insertMany([{ name: 'a' }, { name: 'b' }]);
  return { db, cfg: { url: mongoUrl, db } };
}

function run (tool, cmd, target, extra = [], env = {}) {
  const p = spawn(process.execPath, [path.join(__dirname, 'lib', 'run-tool.js'), tool, cmd, ...extra], {
    env: { ...process.env, ...env, [tool.endsWith('mongo') ? 'CFGLAB_MONGO' : 'CFGLAB_PG']: J(target.cfg) }
  });
  let out = '';
  p.stdout.on('data', (d) => { out += d; });
  p.stderr.on('data', (d) => { out += d; });
  const done = new Promise((resolve) => p.on('exit', (code, signal) => {
    const last = out.trim().split('\n').filter((l) => l.startsWith('{')).pop();
    let res = {};
    try { res = last ? JSON.parse(last) : {}; } catch (e) { res = {}; }
    resolve({ code, signal, ...res, raw: out.trim().slice(-300) });
  }));
  done.proc = p;
  done.output = () => out;
  return done;
}

async function pgState (target, tool) {
  return lab.super(target.db, async (c) => {
    const ledgerTable = tool === 'pgm' ? 'pgmigrations' : 'schema_migrations';
    const has = (await c.query('SELECT to_regclass($1) IS NOT NULL AS p', [`public.${ledgerTable}`])).rows[0].p;
    const ledger = has ? (await c.query(`SELECT name FROM ${ledgerTable} ORDER BY name`)).rows.map((r) => r.name) : [];
    const objects = (await c.query(`
      SELECT count(*)::int AS n FROM (
        SELECT relname FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
         WHERE ns.nspname = 'public' AND relkind IN ('r','v','S','i') AND relname NOT LIKE 'schema_migrations%' AND relname NOT LIKE 'pgmigrations%'
        UNION ALL SELECT proname FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace WHERE ns.nspname = 'public') x`)).rows[0].n;
    const policy = (await c.query("SELECT to_regclass('public.deployment_policy') IS NOT NULL AS p")).rows[0].p;
    return { ledger, objects, policyTable: policy };
  });
}
async function mongoState (target, tool) {
  const db = mongo.db(target.db);
  const ledger = tool === 'migrate-mongo'
    ? (await db.collection('changelog').find({}).toArray()).map((d) => d.fileName)
    : (await db.collection('schema_migrations').find({}).toArray()).map((d) => d._id);
  const idx = (await db.collection('entries').indexes()).map((i) => i.name).sort();
  const units = await db.collection('profile').countDocuments({ units: { $exists: true } });
  const cv = (await db.listCollections({ name: 'config_versions' }).toArray()).length > 0;
  const seed = cv ? await db.collection('config_versions').countDocuments({ _id: 'seed' }) : 0;
  const lockDocs = await db.collection(tool === 'migrate-mongo' ? 'changelog_lock' : 'schema_migrations_lock').countDocuments({});
  return { ledger, entriesIndexes: idx, profileWithUnits: units, configVersions: cv, seedDocs: seed, lockDocs };
}
const state = (backend, target, tool) => (backend === 'pg' ? pgState(target, tool) : mongoState(target, tool));

// ------------------------------------------------------------ properties

const ARMS = [
  { tool: 'umzug-pg', backend: 'pg', locks: ['1', '0'] },
  { tool: 'pgm', backend: 'pg', locks: ['1', 'wait', '0'] },
  { tool: 'umzug-mongo', backend: 'mongo', locks: ['1', '0'] },
  { tool: 'migrate-mongo', backend: 'mongo', locks: ['1', '0'] }
];
const LOCK_LABEL = { 1: 'tool lock on (default)', wait: "lock mode 'wait'", 0: 'lock off' };

async function P1 (arm) {
  const t = arm.backend === 'pg' ? await freshPg() : await freshMongo();
  const dir = arm.backend === 'pg' ? pgDirFor(arm.tool) : mongoDir();
  const before = await state(arm.backend, t, arm.tool);
  const up1 = await run(arm.tool, 'up', t, ['--dir', dir]);
  const mid = await state(arm.backend, t, arm.tool);
  const down = await run(arm.tool, 'down', t, ['--dir', dir]);
  const after = await state(arm.backend, t, arm.tool);
  const up2 = await run(arm.tool, 'up', t, ['--dir', dir]);
  const sane = up1.ok && (up1.done || []).length > 0;
  let clean;
  if (arm.backend === 'pg') clean = after.objects === before.objects && after.ledger.length === 0;
  else clean = J(after.entriesIndexes) === J(before.entriesIndexes) && after.profileWithUnits === 0 && !after.configVersions && after.ledger.length === 0;
  return {
    sane,
    outcome: `up ${up1.ok ? (up1.done || []).length : 'FAILED ' + up1.error}; down ${down.ok ? (down.done || []).length : 'FAILED ' + down.error}; ` +
      `state after down ${clean ? 'equals the starting state' : 'DIFFERS: ' + J(after)}; up again ${up2.ok ? (up2.done || []).length : 'FAILED ' + up2.error}`,
    data: { before, mid, after, up1, down, up2 }
  };
}

async function P2 (arm) {
  const t = arm.backend === 'pg' ? await freshPg() : await freshMongo();
  let killedDuring = false; let after; let first; const reruns = [];
  if (arm.backend === 'pg') {
    const dir = pgDirFor(arm.tool, { up: (name, up) => (name === '0005_policy' ? up + '\nSELECT pg_sleep(5);\n' : up) });
    const r = run(arm.tool, 'up', t, ['--dir', dir]);
    const sleeping = async () => (await lab.super(t.db, (c) => c.query("SELECT 1 FROM pg_stat_activity WHERE wait_event = 'PgSleep' AND datname = $1", [t.db]))).rowCount > 0;
    const dl = Date.now() + 20000;
    while (Date.now() < dl && !(await sleeping())) await sleep(100);
    killedDuring = await sleeping();
    const killedAt = Date.now();
    r.proc.kill('SIGKILL'); first = await r;
    while (await sleeping()) await sleep(100);
    await sleep(300);
    after = await pgState(t, arm.tool);
    after.orphanMs = Date.now() - killedAt;
    const re = await run(arm.tool, 'up', t, ['--dir', pgDirFor(arm.tool)]);
    reruns.push({ what: 're-run', ok: re.ok, error: re.error || null, applied: (re.done || []).length });
    const consistent = after.ledger.includes('0005_policy') === after.policyTable;
    return {
      sane: killedDuring && first.signal === 'SIGKILL',
      outcome: `after the kill (orphaned server session ran ~${(after.orphanMs / 1000).toFixed(1)} s): ledger ${after.ledger.length} rows, 0005 table ${after.policyTable ? 'present' : 'absent'} -> ` +
        `${consistent ? 'consistent (applied+recorded, or neither)' : 'COMMITTED BUT UNRECORDED'}; re-run ${re.ok ? 'completes' : 'FAILS: ' + re.error}`,
      data: { after, reruns }
    };
  }
  // MongoDB: kill between the two steps of migration 3
  const dir = mongoDir();
  const extra = arm.tool === 'umzug-mongo' ? ['--dir', dir, '--lease-ms', '5000'] : ['--dir', dir];
  const r = run(arm.tool, 'up', t, extra, { CFGLAB_CRASH_MID: '1' });
  const dl = Date.now() + 20000;
  while (Date.now() < dl && !r.output().includes('MIDSTEP')) await sleep(50);
  killedDuring = r.output().includes('MIDSTEP');
  r.proc.kill('SIGKILL'); first = await r;
  after = await mongoState(t, arm.tool);
  const recorded = after.ledger.some((x) => x.includes('20261027000003'));
  // re-run as written (non-idempotent step 1), measuring any wait on a stale lock
  const t0 = Date.now(); let re; let tries = 0;
  for (;;) {
    re = await run(arm.tool, 'up', t, extra);
    tries++;
    if (re.ok || !/lock is in place|lease/.test(re.error || '') || Date.now() - t0 > 150000) break;
    await sleep(5000);
  }
  reruns.push({ what: 're-run, migration as written', ok: re.ok, error: re.error || null, tries, waitedS: Math.round((Date.now() - t0) / 1000), lastRunS: re.endedAt && re.startedAt ? Math.round((re.endedAt - re.startedAt) / 1000) : null });
  const re2 = await run(arm.tool, 'up', t, extra, { CFGLAB_IDEMPOTENT: '1' });
  reruns.push({ what: 're-run, step guarded to be idempotent', ok: re2.ok, error: re2.error || null });
  const fin = await mongoState(t, arm.tool);
  return {
    sane: killedDuring && first.signal === 'SIGKILL',
    outcome: `after the kill: the seed step ${after.seedDocs ? 'APPLIED' : 'not applied'}, migration ${recorded ? 'recorded' : 'NOT recorded'}, lock docs left ${after.lockDocs}; ` +
      `re-run as written: ${re.ok ? 'completes' : 'FAILS: ' + re.error}${tries > 1 ? ` (first ${tries - 1} attempt(s) refused by the stale lock, ~${reruns[0].waitedS} s)` : ''}${tries === 1 && reruns[0].lastRunS ? ` (that run took ~${reruns[0].lastRunS} s)` : ''}; ` +
      `re-run with the step made idempotent: ${re2.ok ? 'completes' : 'FAILS: ' + re2.error}; final ledger ${fin.ledger.length}`,
    data: { after, reruns, fin }
  };
}

async function P3 (arm, lockMode) {
  const t = arm.backend === 'pg' ? await freshPg() : await freshMongo();
  const env = {};
  let dir;
  if (arm.backend === 'pg') dir = pgDirFor(arm.tool, { up: (name, up) => (name === '0001_platform_base' ? 'SELECT pg_sleep(1);\n' + up : up) });
  else { dir = mongoDir(); env.CFGLAB_M1_SLEEP_MS = '1000'; }
  const extra = ['--dir', dir, '--lock', lockMode];
  if (arm.tool === 'umzug-mongo') extra.push('--lease-ms', '30000');
  const rs = await Promise.all([1, 2, 3, 4].map(() => run(arm.tool, 'up', t, extra, env)));
  const overlap = Math.max(...rs.map((r) => r.startedAt || Infinity)) < Math.min(...rs.map((r) => r.endedAt || -Infinity));
  const st = await state(arm.backend, t, arm.tool);
  const ok = rs.filter((r) => r.ok).length;
  const errors = [...new Set(rs.filter((r) => !r.ok).map((r) => (r.error || r.raw).replace(/[0-9a-f]{24}|cmp_\d+_\d+/g, '…').slice(0, 140)))];
  const ledgerDup = st.ledger.length - new Set(st.ledger).size;
  return {
    sane: overlap,
    outcome: `${ok}/4 exit ok; ledger ${st.ledger.length} rows (${new Set(st.ledger).size} distinct${ledgerDup ? `, ${ledgerDup} DUPLICATE` : ''}); applied per process ${J(rs.map((r) => (r.done || []).length))}` +
      (errors.length ? `; errors: ${errors.join(' | ')}` : ''),
    data: { results: rs.map((r) => ({ ok: r.ok, n: (r.done || []).length, error: r.error || null })), state: st }
  };
}

// One runner first; three more once it is inside migration 1. A lock that works
// at all must turn these away or make them wait; this separates "the lock is
// racy" (P3) from "the lock does nothing".
async function P3b (arm, lockMode) {
  const t = arm.backend === 'pg' ? await freshPg() : await freshMongo();
  const env = {}; let dir;
  if (arm.backend === 'pg') dir = pgDirFor(arm.tool, { up: (name, up) => (name === '0001_platform_base' ? 'SELECT pg_sleep(2);\n' + up : up) });
  else { dir = mongoDir(); env.CFGLAB_M1_SLEEP_MS = '2000'; }
  const extra = ['--dir', dir, '--lock', lockMode];
  const first = run(arm.tool, 'up', t, extra, env);
  await sleep(1000);
  const later = await Promise.all([1, 2, 3].map(() => run(arm.tool, 'up', t, extra, env)));
  const f = await first;
  const rs = [f, ...later];
  const overlap = later.every((r) => (r.startedAt || 0) < (f.endedAt || 0));
  const st = await state(arm.backend, t, arm.tool);
  const errors = [...new Set(rs.filter((r) => !r.ok).map((r) => (r.error || r.raw).replace(/[0-9a-f]{24}|cmp_\d+_\d+/g, '…').slice(0, 120)))];
  const dup = st.ledger.length - new Set(st.ledger).size;
  return {
    sane: overlap && f.ok,
    outcome: `later runners: ${later.filter((r) => r.ok).length}/3 exit ok, applied ${J(later.map((r) => (r.done || []).length))}; ledger ${st.ledger.length} rows${dup ? ` (${dup} DUPLICATE)` : ''}` + (errors.length ? `; errors: ${errors.join(' | ')}` : ''),
    data: { results: rs.map((r) => ({ ok: r.ok, n: (r.done || []).length, error: r.error || null })), state: st }
  };
}

async function P4 (arm, fileHash) {
  const t = arm.backend === 'pg' ? await freshPg() : await freshMongo();
  const fh = arm.tool === 'migrate-mongo' ? ['--file-hash', fileHash ? '1' : '0'] : [];
  let dir;
  if (arm.backend === 'pg') dir = pgDirFor(arm.tool); else dir = mongoDir();
  const up1 = await run(arm.tool, 'up', t, ['--dir', dir, ...fh]);
  const before = await state(arm.backend, t, arm.tool);
  let edited;
  if (arm.backend === 'pg') {
    edited = path.join(dir, arm.tool === 'pgm' ? '0004_catalogue_seed.sql' : '0004_catalogue_seed.up.sql');
    if (arm.tool === 'pgm') {
      const s = fs.readFileSync(edited, 'utf8');
      fs.writeFileSync(edited, s.replace('-- Down Migration', "UPDATE config_setting SET note = 'edited after release' WHERE key = 'SHOW_SECONDS';\n-- Down Migration"));
    } else fs.appendFileSync(edited, "\nUPDATE config_setting SET note = 'edited after release' WHERE key = 'SHOW_SECONDS';\n");
  } else {
    edited = path.join(dir, '20261027000002-profile-units-backfill.js');
    fs.appendFileSync(edited, '\n// edited after release\n');
  }
  const up2 = await run(arm.tool, 'up', t, ['--dir', dir, ...fh]);
  const after = await state(arm.backend, t, arm.tool);
  let verdict;
  if (!up2.ok) verdict = /drift/.test(up2.error || '') ? `DETECTED: refused (${up2.error})` : `failed otherwise: ${up2.error}`;
  else if ((up2.done || []).length === 0) verdict = 'IGNORED: run succeeds, applies nothing, says nothing';
  else verdict = `RE-RUN: the edited migration was applied again (${J(up2.done)}); ledger ${before.ledger.length} -> ${after.ledger.length} rows`;
  return { sane: up1.ok && (up1.done || []).length > 0, outcome: verdict, data: { up1: (up1.done || []).length, up2 } };
}

function P5 () {
  // Probed in a fresh CommonJS process, as bin/nightscout.js would load them.
  const probe = `
    const out = {};
    try { const u = require('umzug'); out.umzug = typeof u.Umzug === 'function' ? 'require() ok; class Umzug; pending()/executed() for status' : 'unexpected'; } catch (e) { out.umzug = 'require failed: ' + e.message; }
    try { const p = require('node-pg-migrate'); out.pgm = typeof p.runner === 'function' ? 'require() ok (ESM package via require(esm) on Node ' + process.version + '); runner({direction,count,dryRun})' : 'no runner'; } catch (e) { out.pgm = 'require failed: ' + e.code + ' ' + e.message.split('\\n')[0]; }
    (async () => {
      try { const m = require('migrate-mongo'); const up = await m.up; out.mmRequire = 'require() returns a Proxy whose properties are promises (await m.up -> ' + typeof up + ')'; } catch (e) { out.mmRequire = 'require failed: ' + e.message; }
      try { const m = (await import('migrate-mongo')).default; out.mm = 'import() ok; config.set() without a config file; up/down/status(db, client)'; } catch (e) { out.mm = 'import failed: ' + e.message; }
      console.log(JSON.stringify(out));
    })();`;
  const out = JSON.parse(execFileSync(process.execPath, ['-e', probe], { cwd: __dirname, encoding: 'utf8' }).trim().split('\n').pop());
  return out;
}

// ------------------------------------------------------------ main

(async () => {
  assertContainerRunning(PG_PORT);
  assertMongoRunning();
  scratch = fs.mkdtempSync(path.join(SECRETS, 'cmp-'));
  lab = new Lab({ port: PG_PORT, secretsDir: SECRETS });
  await lab.init();
  const mpw = fs.readFileSync(path.join(SECRETS, 'mongo-root-password'), 'utf8').trim();
  mongoUrl = `mongodb://labroot:${encodeURIComponent(mpw)}@127.0.0.1:${MONGO_PORT}/?authSource=admin`;
  mongo = new MongoClient(mongoUrl);
  await mongo.connect();
  const server = {
    postgres: (await lab.super('postgres', (c) => c.query('SHOW server_version'))).rows[0].server_version,
    mongodb: (await mongo.db('admin').command({ buildInfo: 1 })).version,
    mongoTopology: (await mongo.db('admin').command({ hello: 1 })).setName ? 'replica set' : 'standalone',
    node: process.version,
    versions: Object.fromEntries(['umzug', 'node-pg-migrate', 'migrate-mongo', 'mongodb', 'pg'].map((p) => [p, require(`./node_modules/${p}/package.json`).version]))
  };
  console.log(J(server));
  const rows = [];
  const want = (p) => !ONLY || ONLY.includes(p);
  const record = (prop, arm, variant, r) => {
    const row = { prop, tool: arm.tool, backend: arm.backend, variant, valid: r.sane, outcome: r.sane ? r.outcome : `INVALID (non-vacuity check failed): ${r.outcome}`, data: r.data };
    rows.push(row);
    console.log(`${prop} ${arm.tool.padEnd(13)} ${(variant || '').padEnd(22)} ${row.outcome}`);
  };
  for (const arm of ARMS) {
    if (want('P1')) record('P1', arm, '', await P1(arm));
    if (want('P2')) record('P2', arm, '', await P2(arm));
    if (want('P3')) for (const l of arm.locks) record('P3', arm, LOCK_LABEL[l], await P3(arm, l));
    if (want('P3b')) for (const l of arm.locks) record('P3b', arm, LOCK_LABEL[l], await P3b(arm, l));
    if (want('P4')) {
      if (arm.tool === 'migrate-mongo') { record('P4', arm, 'useFileHash false', await P4(arm, false)); record('P4', arm, 'useFileHash true', await P4(arm, true)); } else record('P4', arm, '', await P4(arm));
    }
  }
  const p5 = want('P5') ? P5() : null;
  if (p5) console.log('P5', J(p5));
  await mongo.close();
  fs.rmSync(scratch, { recursive: true, force: true });
  if (!ONLY) fs.writeFileSync(path.join(__dirname, 'compare-results.json'), JSON.stringify({ when: new Date().toISOString(), server, rows, p5 }, null, 2) + '\n');
  // drop the comparison databases this run created
  const dbs = (await lab.super('postgres', (c) => c.query("SELECT datname FROM pg_database WHERE datname LIKE $1", [`cmp_${process.pid}_%`]))).rows;
  for (const d of dbs) await lab.dropDb(d.datname);
  const m2 = new MongoClient(mongoUrl); await m2.connect();
  for (const d of (await m2.db('admin').admin().listDatabases()).databases) if (d.name.startsWith(`cmp_${process.pid}_`)) await m2.db(d.name).dropDatabase();
  await m2.close();
  process.exit(rows.every((r) => r.valid) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
