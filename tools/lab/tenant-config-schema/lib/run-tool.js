'use strict';
// One child process = one `nightscout migrate up|down` run with one tool, the
// shape a dispatcher in bin/nightscout.js would have. Used by compare.js.
//
//   node lib/run-tool.js <umzug-pg|pgm|umzug-mongo|migrate-mongo> <up|down> [options]
//     --dir D            migrations directory
//     --lock 1|0|wait    the tool's own locking (pgm: 1 = its default 'fail', wait = 'wait')
//     --crash-after NAME SIGKILL itself right after NAME's up returns (umzug arms)
//     --file-hash 1      migrate-mongo useFileHash
//     --lease-ms N       umzug-mongo lease length
//     --checkdrift 0     disable the umzug arms' checksum check
// Connection details arrive in CFGLAB_PG / CFGLAB_MONGO (JSON) from the
// harness, never from a file.

const [tool, cmd, ...rest] = process.argv.slice(2);
const opt = (k, d) => { const i = rest.indexOf('--' + k); return i >= 0 ? rest[i + 1] : d; };
const lock = opt('lock', '1');
const crashAfter = opt('crash-after', null);
const afterUp = crashAfter ? async (name) => { if (name === crashAfter) process.kill(process.pid, 'SIGKILL'); } : undefined;
const startedAt = Date.now();

async function main () {
  if (tool === 'umzug-pg' || tool === 'pgm') {
    const pg = JSON.parse(process.env.CFGLAB_PG);
    if (tool === 'umzug-pg') {
      const { Client } = require('pg');
      const m = require('./migrator');
      const client = new Client(pg);
      await client.connect();
      try {
        const o = { client, dir: opt('dir'), lock: lock !== '0', atomic: opt('atomic', '1') !== '0', checkDrift: opt('checkdrift', '1') !== '0', afterUp };
        return cmd === 'down' ? await m.migrateDown(o) : await m.migrateUp(o);
      } finally { await client.end().catch(() => {}); }
    }
    const { runner } = require('node-pg-migrate'); // ESM-only package, loaded through require(esm)
    const quiet = { info () {}, warn () {}, error () {}, debug () {} };
    const done = await runner({
      databaseUrl: pg,
      dir: opt('dir'),
      direction: cmd === 'down' ? 'down' : 'up',
      count: Infinity,
      migrationsTable: 'pgmigrations',
      noLock: lock === '0',
      advisoryLockMode: lock === 'wait' ? 'wait' : 'fail',
      logger: quiet,
      verbose: false
    });
    return done.map((m) => m.name);
  }

  const { MongoClient } = require('mongodb');
  const mc = JSON.parse(process.env.CFGLAB_MONGO);
  const client = new MongoClient(mc.url);
  await client.connect();
  const db = client.db(mc.db);
  try {
    if (tool === 'umzug-mongo') {
      const m = require('./mongo-migrator');
      const o = { dir: opt('dir'), lock: lock !== '0', leaseMs: Number(opt('lease-ms', '30000')), checkDrift: opt('checkdrift', '1') !== '0', afterUp };
      return cmd === 'down' ? await m.mongoDown(db, client, o) : await m.mongoUp(db, client, o);
    }
    const mm = (await import('migrate-mongo')).default;
    mm.config.set({
      mongodb: { url: mc.url, databaseName: mc.db, options: {} },
      migrationsDir: opt('dir'),
      changelogCollectionName: 'changelog',
      lockCollectionName: 'changelog_lock',
      lockTtl: lock === '0' ? 0 : 30,
      migrationFileExtension: '.js',
      useFileHash: opt('file-hash', '0') === '1',
      moduleSystem: 'commonjs'
    });
    if (cmd !== 'down') return await mm.up(db, client);
    const all = [];
    for (;;) { const d = await mm.down(db, client); if (!d.length) break; all.push(...d); }
    return all;
  } finally { await client.close().catch(() => {}); }
}

main().then((done) => {
  process.stdout.write(JSON.stringify({ ok: true, done, startedAt, endedAt: Date.now() }) + '\n');
  process.exit(0);
}, (e) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(e.message).split('\n')[0], startedAt, endedAt: Date.now() }) + '\n');
  process.exit(2);
});
