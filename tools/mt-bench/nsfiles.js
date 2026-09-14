// EXP-MT-040b — where database-per-tenant (§6.7's A') actually breaks
//
// §6.7 states the ceiling on A' as a namespace count rather than a data volume:
// under WiredTiger every collection and every index is its own file with its own
// cache metadata, and Nightscout declares 35 secondary indexes across six
// collections. It then says "where A' actually breaks is an experiment, not an
// opinion", guesses N* in the low thousands, and leaves it unrun.
//
// This runs it. The first attempt at EXP-MT-026 ran it by accident: mongod took a
// FATAL ASSERTION at 50 tenant databases against Docker's default 1024 file
// descriptors, having opened 2,404 WiredTiger files. That is the failure mode
// worth knowing about — not slow, not degraded, a hard crash of the whole cluster,
// which in database-per-tenant means every tenant, not the one being added.
//
// So the interesting quantities are files-per-tenant (fixed by the index set) and
// what mongod's resident memory does as namespace count grows, since WiredTiger
// holds per-file cache metadata whether or not the file has data in it. Documents
// are deliberately NOT inserted: this isolates the namespace cost from the data
// cost, and it is what makes probing to thousands of tenants affordable.
//
// Usage:
//   node nsfiles.js [maxTenants] [step]
//
// LIMIT: one mongod in a container on a laptop. The fd ceiling found here is a
// property of the ulimit, which an operator sets; what transfers is
// files-per-tenant, the RSS slope, and the shape of the failure.

'use strict';

const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');

const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');
const { MongoClient } = require(path.join(NS_ROOT, 'node_modules/mongodb'));

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27099/?directConnection=true';
const CONTAINER = process.env.MONGO_CONTAINER || 'nsbench-mongo';
const PREFIX = 'nsfiles_t';
const MAX = parseInt(process.argv[2], 10) || 500;
const STEP = parseInt(process.argv[3], 10) || 100;

// Same index set as dbloop.js, from lib/server/*.js indexedFields.
const INDEXES = {
  entries: ['date', 'type', 'sgv', 'mbg', 'sysTime', 'dateString', 'identifier',
    { type: 1, date: -1, dateString: 1 }, { date: -1, identifier: -1, created_at: -1 }],
  treatments: ['created_at', 'eventType', 'insulin', 'carbs', 'glucose', 'enteredBy',
    'boluscalc.foods._id', 'notes', 'NSCLIENT_ID', 'percent', 'absolute', 'duration',
    'identifier', { eventType: 1, duration: 1, created_at: 1 },
    { eventType: 1, created_at: -1, identifier: -1, date: -1 }],
  devicestatus: ['created_at', 'NSCLIENT_ID', { created_at: -1, identifier: -1, date: -1 }],
  profile: ['startDate', 'created_at', 'NSCLIENT_ID', { startDate: -1, _id: -1 }],
  food: ['type', 'position', 'hidden'],
  activity: ['created_at']
};

function inContainer (cmd) {
  try { return execFileSync('docker', ['exec', CONTAINER, 'sh', '-c', cmd],
    { encoding: 'utf8', timeout: 30000 }).trim(); } catch (e) { return null; }
}
function wtFiles () { const v = inContainer('ls /data/db/*.wt 2>/dev/null | wc -l'); return v ? +v : null; }
function mongodRssMb () {
  const v = inContainer("grep VmRSS /proc/1/status | awk '{print $2}'");
  return v ? +(v / 1024).toFixed(1) : null;
}
function openFds () { const v = inContainer('ls /proc/1/fd 2>/dev/null | wc -l'); return v ? +v : null; }

async function main () {
  const client = new MongoClient(MONGO_URL, { maxPoolSize: 20, serverSelectionTimeoutMS: 10000 });
  await client.connect();
  console.log(`probing namespace cost to ${MAX} tenant databases, step ${STEP}`);
  console.log(`fd limit in container: ${inContainer('cat /proc/1/limits | grep "Max open files" | awk \'{print $4}\'')}`);

  const base = { files: wtFiles(), rss: mongodRssMb(), fds: openFds() };
  console.log(`baseline: ${base.files} wt files, mongod RSS ${base.rss} MB, ${base.fds} open fds\n`);

  const rows = [];
  let created = 0;
  for (let target = STEP; target <= MAX; target += STEP) {
    const t0 = Date.now();
    for (; created < target; created++) {
      const db = client.db(`${PREFIX}${created}`);
      for (const [col, specs] of Object.entries(INDEXES)) {
        for (const spec of specs) {
          await db.collection(col).createIndex(typeof spec === 'string' ? { [spec]: 1 } : spec);
        }
      }
    }
    const createMs = Date.now() - t0;

    // A read against an arbitrary tenant, to see whether namespace count moves
    // query latency once the working set is only metadata.
    const probe = [];
    for (let i = 0; i < 60; i++) {
      const s = process.hrtime.bigint();
      await client.db(`${PREFIX}${i % created}`).collection('entries')
        .find({}).sort({ date: -1 }).limit(10).toArray();
      probe.push(Number(process.hrtime.bigint() - s) / 1e6);
    }
    probe.sort((a, b) => a - b);

    const row = { tenants: created, wtFiles: wtFiles(), mongodRssMb: mongodRssMb(),
      openFds: openFds(), createMsPerTenant: +(createMs / STEP).toFixed(1),
      probeP50_ms: +probe[30].toFixed(3), probeP99_ms: +probe[59].toFixed(3) };
    row.filesPerTenant = row.wtFiles ? +((row.wtFiles - base.files) / created).toFixed(1) : null;
    rows.push(row);
    console.log(`  ${String(created).padStart(5)} tenants   ${String(row.wtFiles).padStart(6)} files ` +
      `(${row.filesPerTenant}/tenant)   RSS ${String(row.mongodRssMb).padStart(6)} MB   ` +
      `fds ${String(row.openFds).padStart(5)}   read ${row.probeP50_ms.toFixed(2)} p50 / ${row.probeP99_ms.toFixed(2)} p99 ms   ` +
      `${row.createMsPerTenant} ms/tenant to create`);
  }

  // Extrapolate the two quantities that transfer off this machine.
  const last = rows[rows.length - 1];
  const fpt = last.filesPerTenant;
  const rssSlope = (last.mongodRssMb - base.rss) / last.tenants;
  console.log(`\n  files/tenant ${fpt}  ->  1,000 tenants = ${(fpt * 1000).toLocaleString()} files, ` +
    `10,000 = ${(fpt * 10000).toLocaleString()}`);
  console.log(`  mongod RSS slope ${(rssSlope * 1024).toFixed(0)} KB/tenant of pure namespace metadata ` +
    `-> ${(rssSlope * 10000 / 1024).toFixed(1)} GB at 10,000 tenants`);
  console.log(`  MongoDB's own production recommendation is nofile 64000, which at ` +
    `${fpt} files/tenant is ~${Math.floor(64000 / fpt).toLocaleString()} tenant databases.`);

  const out = { date: new Date().toISOString(), baseline: base, rows,
    filesPerTenant: fpt, rssKbPerTenant: +(rssSlope * 1024).toFixed(0),
    tenantsAt64kFds: Math.floor(64000 / fpt) };
  fs.writeFileSync(path.join(__dirname, 'results', 'exp-mt-040b.json'), JSON.stringify(out, null, 2));
  console.log(`\n  cleaning up ${created} probe databases`);
  for (let i = 0; i < created; i++) await client.db(`${PREFIX}${i}`).dropDatabase();
  await client.close();
}

main().catch(e => { console.error(e.message); process.exit(1); });
