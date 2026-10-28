'use strict';
// MIG-VV (maintainer, 2026-10-27): verify the provisional runner choice on MongoDB.
// umzug's MongoDB adapter (ledger + lease lock), and migrate-mongo as the
// comparison, on four targets:
//
//   8.0-standalone  cfgschema-mongo      127.0.0.1:27747 (round 2's server)
//   8.0-rs          cfgschema-mongo8-rs  127.0.0.1:27750-27752, replica set rs0
//   5.0-standalone  cfgschema-mongo5     127.0.0.1:27748 (dev's floor, 5.0.32)
//   5.0-rs          cfgschema-mongo5-rs  127.0.0.1:27753-27755, replica set rs0
//
// Each replica set is ONE container running three mongod processes on the host
// network, bound to 127.0.0.1 (mongo-rs/start-rs.sh).
//
// Rows, as compare.js: P1 up/down/up; P2 runner killed mid-migration after a
// non-idempotent step; P3 four at once (lock on, lock off); P3b one running plus
// three started during it; P4 drift. New: P2t and P7, the adapter with
// transactions; P6, a primary step-down while a migration is running.
// Every row carries a non-vacuity check; a row whose check fails is INVALID.
//
//   node mig-vv.js --secrets DIR [--only 8.0-rs,5.0-standalone] [--rows P1,P6]

const fs = require('node:fs');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const { MongoClient } = require('mongodb');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };
const SECRETS = opt('secrets');
if (!SECRETS || path.resolve(SECRETS).startsWith(path.resolve(__dirname, '..', '..', '..'))) {
  console.error('--secrets DIR (outside the repository) is required'); process.exit(2);
}
const ONLY = opt('only') ? opt('only').split(',') : null;
const ROWS = opt('rows') ? opt('rows').split(',') : null;
const J = (x) => JSON.stringify(x);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const TARGETS = [
  { name: '8.0-standalone', container: 'cfgschema-mongo', hosts: '127.0.0.1:27747', rs: false, published: 27747 },
  { name: '8.0-rs', container: 'cfgschema-mongo8-rs', hosts: '127.0.0.1:27750,127.0.0.1:27751,127.0.0.1:27752', rs: true },
  { name: '5.0-standalone', container: 'cfgschema-mongo5', hosts: '127.0.0.1:27748', rs: false, published: 27748 },
  { name: '5.0-rs', container: 'cfgschema-mongo5-rs', hosts: '127.0.0.1:27753,127.0.0.1:27754,127.0.0.1:27755', rs: true }
];
const ARMS = ['umzug-mongo', 'migrate-mongo'];

let pw; let scratch; let n = 0;
const urlFor = (t) => `mongodb://labroot:${encodeURIComponent(pw)}@${t.hosts}/?authSource=admin${t.rs ? '&replicaSet=rs0' : ''}`;

function assertContainer (t) {
  const out = execFileSync('docker', ['inspect', '-f', '{{.State.Running}} {{.HostConfig.NetworkMode}} {{json .NetworkSettings.Ports}} {{json .HostConfig.Ulimits}}', t.container], { encoding: 'utf8' });
  if (!out.startsWith('true ')) throw new Error(`${t.container} is not running`);
  if (!out.includes('"Hard":64000')) throw new Error(`${t.container} was not started with --ulimit nofile=64000:64000`);
  if (t.published && !out.includes(`"HostIp":"127.0.0.1","HostPort":"${t.published}"`)) throw new Error(`${t.container} not on 127.0.0.1:${t.published}`);
  if (t.rs && !out.includes(' host ')) throw new Error(`${t.container} is not on the host network`);
}

async function withClient (t, fn) {
  const c = new MongoClient(urlFor(t), { serverSelectionTimeoutMS: 30000 });
  await c.connect();
  try { return await fn(c); } finally { await c.close(); }
}

async function describe (t) {
  return withClient(t, async (c) => {
    const a = c.db('admin');
    const version = (await a.command({ buildInfo: 1 })).version;
    const hello = await a.command({ hello: 1 });
    if (t.rs && (!hello.setName || (hello.hosts || []).length !== 3)) throw new Error(`${t.name}: not a three-member replica set`);
    if (!t.rs && hello.setName) throw new Error(`${t.name}: expected standalone`);
    return { version, topology: t.rs ? `replica set ${hello.setName}, ${hello.hosts.length} members` : 'standalone', primary: hello.primary || null };
  });
}

async function fresh (t) {
  const db = `vv_${process.pid}_${n++}`;
  await withClient(t, async (c) => {
    await c.db(db).dropDatabase();
    await c.db(db).collection('entries').insertOne({ type: 'sgv', sgv: 120, date: Date.now() });
    await c.db(db).collection('profile').insertMany([{ name: 'a' }, { name: 'b' }]);
  });
  return { t, db, cfg: { url: urlFor(t), db } };
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

function run (tool, cmd, target, extra = [], env = {}) {
  const p = spawn(process.execPath, [path.join(__dirname, 'lib', 'run-tool.js'), tool, cmd, ...extra], {
    env: { ...process.env, ...env, CFGLAB_MONGO: J(target.cfg) }
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

async function state (target, tool) {
  return withClient(target.t, async (c) => {
    const db = c.db(target.db);
    const ledger = tool === 'migrate-mongo'
      ? (await db.collection('changelog').find({}).toArray()).map((d) => d.fileName)
      : (await db.collection('schema_migrations').find({}).toArray()).map((d) => d._id);
    const cv = (await db.listCollections({ name: 'config_versions' }).toArray()).length > 0;
    const seed = cv ? await db.collection('config_versions').countDocuments({ _id: 'seed' }) : 0;
    const cvIdx = cv ? (await db.collection('config_versions').indexes()).map((i) => i.name).filter((x) => x !== '_id_') : [];
    const lockCol = tool === 'migrate-mongo' ? 'changelog_lock' : 'schema_migrations_lock';
    const locks = await db.collection(lockCol).find({}).toArray();
    const entriesIdx = (await db.collection('entries').indexes()).map((i) => i.name).sort();
    const units = await db.collection('profile').countDocuments({ units: { $exists: true } });
    return { ledger, configVersions: cv, seedDocs: seed, configVersionsIndexes: cvIdx, lockDocs: locks.length, lockExpiresInS: locks[0] && locks[0].expiresAt ? Math.round((locks[0].expiresAt - Date.now()) / 1000) : null, entriesIndexes: entriesIdx, profileWithUnits: units };
  });
}
const short = (s) => String(s || '').replace(/vv_\d+_\d+/g, '…').slice(0, 170);

// --------------------------------------------------------------------- rows

async function P1 (t, tool) {
  const tg = await fresh(t); const dir = mongoDir();
  const before = await state(tg, tool);
  const up1 = await run(tool, 'up', tg, ['--dir', dir]);
  const down = await run(tool, 'down', tg, ['--dir', dir]);
  const after = await state(tg, tool);
  const up2 = await run(tool, 'up', tg, ['--dir', dir]);
  const clean = J(after.entriesIndexes) === J(before.entriesIndexes) && after.profileWithUnits === 0 && !after.configVersions && after.ledger.length === 0;
  return { sane: up1.ok && (up1.done || []).length === 3, outcome: `up ${up1.ok ? up1.done.length : 'FAILED ' + short(up1.error)}; down ${down.ok ? down.done.length : 'FAILED ' + short(down.error)}; after down ${clean ? 'equals the start' : 'DIFFERS ' + J(after)}; up again ${up2.ok ? up2.done.length : 'FAILED ' + short(up2.error)}` };
}

async function crashRun (tg, tool, extra) {
  const r = run(tool, 'up', tg, extra, { CFGLAB_CRASH_MID: '1' });
  const dl = Date.now() + 30000;
  while (Date.now() < dl && !r.output().includes('MIDSTEP')) await sleep(50);
  const during = r.output().includes('MIDSTEP');
  r.proc.kill('SIGKILL');
  const first = await r;
  return { during: during && first.signal === 'SIGKILL' };
}
async function rerunUntil (tool, tg, extra, env, re, limitMs) {
  const t0 = Date.now(); let r; let tries = 0;
  for (;;) {
    r = await run(tool, 'up', tg, extra, env); tries++;
    if (r.ok || !re.test(r.error || '') || Date.now() - t0 > limitMs) break;
    await sleep(5000);
  }
  return { r, tries, waitedS: Math.round((Date.now() - t0) / 1000), lastRunS: r.endedAt && r.startedAt ? Math.round((r.endedAt - r.startedAt) / 1000) : null };
}

async function P2 (t, tool, txn) {
  const tg = await fresh(t); const dir = mongoDir();
  const extra = ['--dir', dir, ...(tool === 'umzug-mongo' ? ['--lease-ms', '5000'] : []), ...(txn ? ['--txn', '1'] : [])];
  const k = await crashRun(tg, tool, extra);
  await sleep(500);
  const after = await state(tg, tool);
  const recorded = after.ledger.some((x) => x.includes('20261027000003'));
  const a = await rerunUntil(tool, tg, extra, {}, /lock is in place|lease|WriteConflict|LockTimeout|Unable to acquire|catalog changes|already exists/i, 150000);
  let b = null;
  if (!a.r.ok) b = await run(tool, 'up', tg, extra, { CFGLAB_IDEMPOTENT: '1' });
  const fin = await state(tg, tool);
  return {
    sane: k.during,
    outcome: `after the kill: seed ${after.seedDocs ? 'APPLIED' : 'not applied'}, migration ${recorded ? 'recorded' : 'NOT recorded'}, lock docs ${after.lockDocs}; ` +
      `re-run as written: ${a.r.ok ? 'completes' : 'FAILS: ' + short(a.r.error)}${a.tries > 1 ? ` (first ${a.tries - 1} attempt(s) refused, ~${a.waitedS} s)` : (a.lastRunS ? ` (took ~${a.lastRunS} s)` : '')}` +
      (b ? `; re-run with the step idempotent: ${b.ok ? 'completes' : 'FAILS: ' + short(b.error)}` : '') + `; final ledger ${fin.ledger.length}, seed ${fin.seedDocs}`
  };
}

async function P3 (t, tool, lock) {
  const tg = await fresh(t); const dir = mongoDir();
  const rs = await Promise.all([1, 2, 3, 4].map(() => run(tool, 'up', tg, ['--dir', dir, '--lock', lock, ...(tool === 'umzug-mongo' ? ['--lease-ms', '30000'] : [])], { CFGLAB_M1_SLEEP_MS: '1000' })));
  const overlap = Math.max(...rs.map((r) => r.startedAt || Infinity)) < Math.min(...rs.map((r) => r.endedAt || -Infinity));
  const st = await state(tg, tool);
  const dup = st.ledger.length - new Set(st.ledger).size;
  const errors = [...new Set(rs.filter((r) => !r.ok).map((r) => short(r.error || r.raw).slice(0, 110)))];
  return { sane: overlap, outcome: `${rs.filter((r) => r.ok).length}/4 ok; ledger ${st.ledger.length}${dup ? ` (${dup} DUPLICATE)` : ''}; applied ${J(rs.map((r) => (r.done || []).length))}${errors.length ? '; ' + errors.join(' | ') : ''}` };
}

async function P3b (t, tool) {
  const tg = await fresh(t); const dir = mongoDir();
  const extra = ['--dir', dir, '--lock', '1'];
  const first = run(tool, 'up', tg, extra, { CFGLAB_M1_SLEEP_MS: '2000' });
  await sleep(1000);
  const later = await Promise.all([1, 2, 3].map(() => run(tool, 'up', tg, extra, { CFGLAB_M1_SLEEP_MS: '2000' })));
  const f = await first;
  const st = await state(tg, tool);
  const dup = st.ledger.length - new Set(st.ledger).size;
  const errors = [...new Set(later.filter((r) => !r.ok).map((r) => short(r.error).slice(0, 90)))];
  return { sane: f.ok && later.every((r) => (r.startedAt || 0) < (f.endedAt || 0)), outcome: `later: ${later.filter((r) => r.ok).length}/3 ok, applied ${J(later.map((r) => (r.done || []).length))}; ledger ${st.ledger.length}${dup ? ` (${dup} DUPLICATE)` : ''}${errors.length ? '; ' + errors.join(' | ') : ''}` };
}

async function P4 (t, tool, fileHash) {
  const tg = await fresh(t); const dir = mongoDir();
  const fh = tool === 'migrate-mongo' ? ['--file-hash', fileHash ? '1' : '0'] : [];
  const up1 = await run(tool, 'up', tg, ['--dir', dir, ...fh]);
  const before = await state(tg, tool);
  fs.appendFileSync(path.join(dir, '20261027000002-profile-units-backfill.js'), '\n// edited after release\n');
  const up2 = await run(tool, 'up', tg, ['--dir', dir, ...fh]);
  const after = await state(tg, tool);
  let v;
  if (!up2.ok) v = /drift/.test(up2.error || '') ? 'DETECTED (refused)' : `failed otherwise: ${short(up2.error)}`;
  else if (!(up2.done || []).length) v = 'IGNORED';
  else v = `RE-RUN (ledger ${before.ledger.length} -> ${after.ledger.length})`;
  return { sane: up1.ok && (up1.done || []).length === 3, outcome: v };
}

// P7: can the adapter run a migration and its ledger record in one transaction?
async function P7 (t) {
  const out = {};
  for (const mode of ['transactional migrations only', 'every migration forced into a transaction']) {
    const tg = await fresh(t);
    const r = await run('umzug-mongo', 'up', tg, ['--dir', mongoDir(), '--txn', '1'], mode.startsWith('every') ? { CFGLAB_TXN_ALL: '1' } : {});
    const st = await state(tg, 'umzug-mongo');
    const txnRecorded = await withClient(t, async (c) => c.db(tg.db).collection('schema_migrations').countDocuments({ txn: true }));
    out[mode] = r.ok ? `completes; ${txnRecorded} of ${st.ledger.length} ledger records written inside the migration's transaction` : `FAILS: ${short(r.error)}`;
  }
  return { sane: true, outcome: Object.entries(out).map(([k, v]) => `${k}: ${v}`).join('; ') };
}

// P6: step the primary down while migration 3 is paused after its seed write.
async function P6 (t, tool, txn, writes) {
  const tg = await fresh(t); const dir = mongoDir();
  const before = await describe(t);
  const extra = ['--dir', dir, ...(tool === 'umzug-mongo' ? ['--lease-ms', '15000'] : []), ...(txn ? ['--txn', '1'] : [])];
  const mark = writes ? 'LOOPING' : 'PAUSED';
  const r = run(tool, 'up', tg, extra, writes ? { CFGLAB_WRITE_LOOP_MS: '6000' } : { CFGLAB_PAUSE_MS: '8000' });
  const dl = Date.now() + 30000;
  while (Date.now() < dl && !r.output().includes(mark)) await sleep(50);
  if (writes) await sleep(1500);
  const paused = r.output().includes(mark);
  let stepDown;
  try {
    await withClient(t, (c) => c.db('admin').command({ replSetStepDown: 30, secondaryCatchUpPeriodSecs: 5 }));
    stepDown = 'ok';
  } catch (e) { stepDown = `returned error (${short(e.message).slice(0, 60)})`; }
  // non-vacuity: the step-down must land while the migration is still in its pause or loop
  const stillRunning = !/LOOPCOUNT/.test(r.output()) && !/"ok":/.test(r.output());
  let after; const t0 = Date.now();
  for (;;) { try { after = await describe(t); if (after.primary && after.primary !== before.primary) break; } catch (e) { /* electing */ } if (Date.now() - t0 > 60000) break; await sleep(500); }
  const electedS = ((Date.now() - t0) / 1000).toFixed(1);
  const res = await r;
  const pausedTwice = (r.output().match(new RegExp(mark, 'g')) || []).length;
  const loopCounts = (r.output().match(/LOOPCOUNT (\d+)/g) || []).map((x) => Number(x.split(' ')[1]));
  const st = await state(tg, tool);
  const nStored = await withClient(t, async (c) => { const d = await c.db(tg.db).collection('config_versions').findOne({ _id: 'seed' }); return d ? d.n : null; });
  const re = res.ok ? null : await rerunUntil(tool, tg, ['--dir', dir, ...(tool === 'umzug-mongo' ? ['--lease-ms', '15000'] : [])], {}, /lock is in place|lease/i, 150000);
  let re2 = null;
  if (re && !re.r.ok) re2 = await run(tool, 'up', tg, ['--dir', dir], { CFGLAB_IDEMPOTENT: '1' });
  const fin = await state(tg, tool);
  // let the priority-2 member take the primary back before the next row
  const t1 = Date.now();
  for (;;) { try { const d = await describe(t); if (d.primary === before.primary) break; } catch (e) { /* electing */ } if (Date.now() - t1 > 90000) break; await sleep(1000); }
  return {
    sane: paused && stillRunning && after && after.primary !== before.primary,
    outcome: `primary ${before.primary} -> ${after && after.primary} (stepDown ${stepDown}; new primary seen after ~${electedS} s); ` +
      `runner ${res.ok ? `COMPLETED (${(res.done || []).length} applied${pausedTwice > 1 ? `; migration 3 ran ${pausedTwice} times: the transaction was retried` : ''})` : 'FAILED: ' + short(res.error)}; ` +
      (writes ? `writes in flight: runner counted ${J(loopCounts)} successful increments, the server holds n = ${nStored}${loopCounts.length && loopCounts[loopCounts.length - 1] === nStored ? ' (equal: none lost or doubled)' : ' (DIFFERENT)'}; ` : '') +
      `then: ledger ${st.ledger.length} (${st.ledger.some((x) => x.includes('000003')) ? 'with' : 'without'} migration 3), seed ${st.seedDocs}, index ${st.configVersionsIndexes.join(',') || 'none'}, lock docs ${st.lockDocs}${st.lockExpiresInS !== null ? ` (expires in ${st.lockExpiresInS} s)` : ''}` +
      (re ? `; re-run as written: ${re.r.ok ? 'completes' : 'FAILS: ' + short(re.r.error)}${re.tries > 1 ? ` (after ${re.tries - 1} refusal(s), ~${re.waitedS} s)` : ''}` : '') +
      (re2 ? `; re-run idempotent: ${re2.ok ? 'completes' : 'FAILS: ' + short(re2.error)}` : '') +
      `; final ledger ${fin.ledger.length}, seed ${fin.seedDocs}`
  };
}

// --------------------------------------------------------------------- main

(async () => {
  pw = fs.readFileSync(path.join(SECRETS, 'mongo-root-password'), 'utf8').trim();
  scratch = fs.mkdtempSync(path.join(SECRETS, 'vv-'));
  const rows = []; const servers = {};
  const want = (r) => !ROWS || ROWS.includes(r);
  for (const t of TARGETS) {
    if (ONLY && !ONLY.includes(t.name)) continue;
    assertContainer(t);
    servers[t.name] = await describe(t);
    console.log(`== ${t.name}: ${J(servers[t.name])}`);
    const rec = async (row, tool, variant, fn) => {
      assertContainer(t);
      let r;
      try { r = await fn(); } catch (e) { r = { sane: false, outcome: `HARNESS ERROR ${short(e.message)}` }; }
      const o = { target: t.name, row, tool, variant, valid: r.sane, outcome: r.sane ? r.outcome : `INVALID: ${r.outcome}` };
      rows.push(o);
      console.log(`${row.padEnd(4)} ${tool.padEnd(13)} ${(variant || '').padEnd(16)} ${o.outcome}`);
    };
    for (const tool of ARMS) {
      if (want('P1')) await rec('P1', tool, '', () => P1(t, tool));
      if (want('P2')) await rec('P2', tool, '', () => P2(t, tool, false));
      if (want('P3')) { await rec('P3', tool, 'lock on', () => P3(t, tool, '1')); await rec('P3', tool, 'lock off', () => P3(t, tool, '0')); }
      if (want('P3b')) await rec('P3b', tool, 'lock on', () => P3b(t, tool));
      if (want('P4')) {
        if (tool === 'migrate-mongo') { await rec('P4', tool, 'useFileHash off', () => P4(t, tool, false)); await rec('P4', tool, 'useFileHash on', () => P4(t, tool, true)); } else await rec('P4', tool, '', () => P4(t, tool));
      }
    }
    if (want('P7')) await rec('P7', 'umzug-mongo', 'transactions', () => P7(t));
    if (t.rs && want('P2t')) await rec('P2t', 'umzug-mongo', 'transactions', () => P2(t, 'umzug-mongo', true));
    if (t.rs && want('P6')) {
      await rec('P6', 'umzug-mongo', 'idle, no txn', () => P6(t, 'umzug-mongo', false, false));
      await rec('P6', 'umzug-mongo', 'idle, txn', () => P6(t, 'umzug-mongo', true, false));
      await rec('P6', 'migrate-mongo', 'idle', () => P6(t, 'migrate-mongo', false, false));
      await rec('P6w', 'umzug-mongo', 'writes, no txn', () => P6(t, 'umzug-mongo', false, true));
      await rec('P6w', 'umzug-mongo', 'writes, txn', () => P6(t, 'umzug-mongo', true, true));
      await rec('P6w', 'migrate-mongo', 'writes', () => P6(t, 'migrate-mongo', false, true));
    }
    await withClient(t, async (c) => {
      for (const d of (await c.db('admin').admin().listDatabases()).databases) if (d.name.startsWith(`vv_${process.pid}_`)) await c.db(d.name).dropDatabase();
    });
  }
  fs.rmSync(scratch, { recursive: true, force: true });
  if (!ONLY && !ROWS) fs.writeFileSync(path.join(__dirname, 'mig-vv-results.json'), JSON.stringify({ when: new Date().toISOString(), node: process.version, servers, rows }, null, 2) + '\n');
  process.exit(rows.every((r) => r.valid) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
