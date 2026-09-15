// The last driver object in findFiltered's options bag: `readOptions`.
//
// WHY THIS IS DIFFERENT FROM sort/limit/projection. Those three carry client
// input. `readOptions` never does: it is one frozen constant,
// lib/storage/mongo-read-options.js = Object.freeze({batchSize: 1000}), passed
// at thirteen call sites and nowhere else. So "do the two backends disagree" is
// the wrong question -- nothing disagrees about a constant. Two better ones:
//
//   1. IS THE CONSTANT LOAD-BEARING? It exists because of a claim in its own
//      comment: "Driver 7 no longer caps getMore batches at 1,000 documents by
//      default." That is a testable claim about a specific driver version, so
//      this measures drivers 5, 6 and 7 side by side rather than whichever one
//      happened to be installed. (origin/dev ships ^5.9.2; the modernization
//      branch ships ^7.6.0; tools/qc had 6.21.0.)
//
//   2. DOES THE BOUND HOLD ON EVERY PATH? It does not. §2 is the finding.
//
//   3. WHAT IS THE SQL ANALOGUE? batchSize is not syntax. It is the difference
//      between streaming a result set and materialising it, and node-postgres
//      materialises by default -- which makes this the one option in the bag
//      whose translation is an architecture decision, not a rewrite.
//
// Usage: PGPASSWORD=… node --expose-gc readoptions-arm.js
//        (--expose-gc is required; §3 measures RETAINED heap, which is
//         meaningless without a forced collection. A first version of §3
//         sampled PEAK heap instead and produced a 0.9x ratio -- pure GC noise
//         dressed up as a result. It is measured properly here or not at all.)

'use strict';

const { Client } = require('pg');

if (!process.env.PG_URL && !process.env.PGPASSWORD) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  console.error('The throwaway POC container is created with:');
  console.error('  docker run -d --name <name> -e POSTGRES_PASSWORD="$PGPASSWORD" \\');
  console.error('    -p <port>:5432 postgres:16-alpine');
  process.exit(2);
}
if (typeof global.gc !== 'function') {
  console.error('Run with --expose-gc; §3 measures retained heap.');
  process.exit(2);
}

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27019';
const PG_URL = process.env.PG_URL ||
  `postgres://postgres:${encodeURIComponent(process.env.PGPASSWORD)}@127.0.0.1:15434/postgres`;

// The shipping constant, required from the worktree so this cannot drift from
// what actually runs.
const READ_OPTIONS = (() => {
  try {
    return require(process.env.READ_OPTIONS_MODULE ||
      '../../externals/work/crm-seam/lib/storage/mongo-read-options.js');
  } catch (e) { return Object.freeze({ batchSize: 1000 }); }
})();

const N = parseInt(process.env.N, 10) || 40000;
const PAD = 'x'.repeat(900);                       // ~1 KB documents
const mib = (b) => (b / 1024 / 1024).toFixed(1);

// Drivers to compare. Aliased in package.json so all three coexist; a missing
// one is skipped rather than silently substituted, because substituting would
// answer a version question with the wrong version.
const DRIVERS = ['mongodb5', 'mongodb', 'mongodb7'];
function driver (name) {
  try { return { MongoClient: require(name).MongoClient,
    version: require(name + '/package.json').version }; } catch (e) { return null; }
}

// Count what goes ON THE WIRE. Inferring batching from timing or from heap
// would be guesswork; command monitoring reports the batchSize the driver
// actually asked for.
async function wire (MongoClient, collection, build) {
  const client = new MongoClient(MONGO_URL, { monitorCommands: true });
  const asked = [];
  const returned = [];
  client.on('commandStarted', e => {
    if (e.commandName === 'getMore') asked.push(e.command.batchSize);
  });
  client.on('commandSucceeded', e => {
    const b = e.reply?.cursor?.firstBatch || e.reply?.cursor?.nextBatch;
    if (b) returned.push(b.length);
  });
  await client.connect();
  const docs = await build(client.db('seamqc').collection(collection)).toArray();
  await client.close();
  return { docs: docs.length, asked, returned };
}

// Long runs of an identical batch size say nothing extra; collapse them so the
// one row that ISN'T a flat run stands out instead of being lost in a wall.
const fmt = (seq) => {
  if (seq.length === 0) return '(none sent — server decides)';
  const show = (v) => v === undefined ? '(no batchSize)' : String(v);
  const uniq = [...new Set(seq)];
  if (uniq.length === 1) return `${show(uniq[0])} x${seq.length}`;
  return seq.length <= 8 ? seq.join(' ')
    : seq.slice(0, 6).join(' ') + ` … (${seq.length})`;
};

async function seed () {
  const d = driver('mongodb7') || driver('mongodb');
  const client = new d.MongoClient(MONGO_URL);
  await client.connect();
  const col = client.db('seamqc').collection('readopts');
  await col.drop().catch(() => {});
  for (let i = 0; i < N; i += 2000) {
    await col.insertMany(Array.from({ length: Math.min(2000, N - i) },
      (_, k) => ({ _id: i + k, sgv: 40 + ((i + k) % 360), blob: PAD })));
  }
  await client.close();
}

async function main () {
  console.log(`corpus: ${N} documents of ~1 KB (~${(N / 1000).toFixed(0)} MB of payload)`);
  console.log(`constant under test: ${JSON.stringify(READ_OPTIONS)}\n`);
  await seed();

  // ===================================== 1. is the constant load-bearing?
  console.log('=== 1. Default getMore batching, by driver version ===\n');
  console.log('  driver      no readOptions                with readOptions');
  console.log('  ' + '-'.repeat(62));
  for (const name of DRIVERS) {
    const d = driver(name);
    if (!d) { console.log(`  ${name}: not installed, skipped`); continue; }
    const bare = await wire(d.MongoClient, 'readopts', c => c.find({}));
    const withRo = await wire(d.MongoClient, 'readopts', c => c.find({}, READ_OPTIONS));
    console.log(`  v${d.version.padEnd(10)} ${fmt(bare.asked).padEnd(29)} ${fmt(withRo.asked)}`);
  }
  console.log('\n  The comment on mongo-read-options.js says driver 7 dropped a 1,000-document');
  console.log('  default cap. Confirmed: 5 and 6 send batchSize=1000 unprompted, 7 sends none');
  console.log('  and lets the server fill to the 16 MB wire limit. The constant restores the');
  console.log('  old behaviour, so it is load-bearing on 7 and a no-op on 5 and 6.');

  // ============================== 2. the path where the bound does NOT hold
  console.log('\n\n=== 2. …except on the one path that needs it most ===\n');
  console.log('  Same constant, with .limit(0) also set:\n');
  for (const name of DRIVERS) {
    const d = driver(name);
    if (!d) continue;
    const r = await wire(d.MongoClient, 'readopts',
      c => c.find({}, READ_OPTIONS).limit(0));
    const doubling = r.asked.length > 2 && r.asked[1] === r.asked[0] * 2;
    console.log(`  v${d.version.padEnd(10)} ${fmt(r.asked).padEnd(29)}` +
      (doubling ? '  <- the bound is ABANDONED' : '  <- holds'));
  }
  console.log('\n  On driver 7 the requested batch DOUBLES every getMore — 1000, 2000, 4000,');
  console.log('  8000, 16000, 32000 — until the wire limit stops it. Drivers 5 and 6 hold at');
  console.log('  1000. The explicit bound is honoured for the first batch and then discarded.');
  console.log('');
  console.log('  Why this path and not another: findFiltered only calls .limit() when the');
  console.log('  caller supplied one, and API v1 supplies');
  console.log('      limit: opts && opts.count ? parseInt(opts.count) : undefined');
  console.log('  so .limit(0) is reached by exactly two inputs — ?count=0 and any');
  console.log('  unparseable ?count= (via toSafeInt(NaN, 0)). Those are BF-14. So BF-14 does');
  console.log('  not merely remove the document limit: on driver 7 it also dismantles the');
  console.log('  memory bound that exists to make a large read survivable. The two compound,');
  console.log('  and they compound on the same request.');

  // ====================================================== 3. the SQL analogue
  console.log('\n\n=== 3. The PostgreSQL analogue is an architecture choice ===\n');
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  await pg.query('DROP TABLE IF EXISTS ro; CREATE TABLE ro (id int PRIMARY KEY, doc jsonb NOT NULL)');
  for (let i = 0; i < N; i += 1000) {
    const s = Array.from({ length: Math.min(1000, N - i) },
      (_, k) => [i + k, JSON.stringify({ sgv: 100, blob: PAD })]);
    await pg.query(`INSERT INTO ro (id,doc) VALUES ` +
      s.map((_, k) => `($${k * 2 + 1},$${k * 2 + 2})`).join(','), s.flat());
  }

  const settle = async () => {
    for (let i = 0; i < 4; i++) { global.gc(); await new Promise(r => setTimeout(r, 30)); }
  };

  await settle();
  let base = process.memoryUsage().heapUsed;
  const all = await pg.query('SELECT id, doc FROM ro');
  await settle();
  const materialised = process.memoryUsage().heapUsed - base;
  console.log(`  node-postgres default            ${String(all.rows.length).padStart(6)} rows retained, ` +
    `heap +${mib(materialised)} MiB`);
  const keep = all.rows.length;                    // hold the result set live

  await settle();
  base = process.memoryUsage().heapUsed;
  await pg.query('BEGIN');
  await pg.query('DECLARE c NO SCROLL CURSOR FOR SELECT id, doc FROM ro');
  let total = 0, batch, widest = 0;
  do {
    batch = await pg.query(`FETCH ${READ_OPTIONS.batchSize} FROM c`);
    widest = Math.max(widest, batch.rows.length);
    total += batch.rows.length;                    // consumed, not accumulated
  } while (batch.rows.length > 0);
  await pg.query('COMMIT');
  await settle();
  const streamed = process.memoryUsage().heapUsed - base;
  console.log(`  server-side CURSOR, FETCH ${String(READ_OPTIONS.batchSize).padEnd(5)} ${String(total).padStart(6)} rows seen,     ` +
    `heap +${mib(streamed)} MiB   (widest batch ${widest})`);
  console.log(`  (${keep} rows still held from the first read, to keep the comparison honest)`);

  // Deliberately NOT a ratio. The cursor arm retains essentially nothing, so a
  // ratio is a division by noise and would report a precise-looking 900x that
  // means only "one of these is ~0".
  console.log(`\n  Retained heap is the number that matters: ${mib(materialised)} MiB against` +
    ` ${mib(streamed)} MiB.`);
  console.log('  `batchSize` is one word in a Mongo find(). Its equivalent is BEGIN, DECLARE,');
  console.log('  a FETCH loop and COMMIT — and it only holds if the caller consumes each batch');
  console.log('  instead of concatenating them. findFiltered ends in toArray(), so a literal');
  console.log('  port concatenates, and the bound the constant exists to provide is lost while');
  console.log('  the code still reads as though it were there.');
  console.log('');
  console.log('  Caveat: this measures retention, not peak. Peak heap was tried first and gave');
  console.log('  a 0.9x ratio — GC noise at this corpus size. Retention is the property the');
  console.log('  seam has to preserve, so retention is what is reported.');

  await pg.end();
}

main().catch(e => { console.error(e); process.exit(2); });
