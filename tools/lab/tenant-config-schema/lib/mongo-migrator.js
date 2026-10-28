'use strict';
// umzug on MongoDB, with the pieces umzug leaves to its caller:
//
//  1. A LEDGER: collection `schema_migrations`, one document per applied
//     migration, `_id` = name (so a duplicate cannot be recorded), with a
//     checksum of the file.
//  2. A LEASE LOCK: one document `_id: 'lock'` in `schema_migrations_lock` with
//     an owner and an expiry the holder renews. MongoDB has no session-scoped
//     lock that dies with the client, so a holder that is killed leaves the
//     lease behind; anyone may take it over once it has expired.
//  3. DRIFT: a file whose checksum differs from the ledger stops the run.
//
// There is no atomicity between a step and its ledger entry on a standalone
// server, which has no multi-document transactions: steps must be idempotent.
//
//  4. TRANSACTIONS (opts.txn, MIG-VV): on a replica set, a migration that
//     exports `transactional: true` runs inside session.withTransaction(),
//     together with its ledger record, receiving the session as opts.session.
//     A migration that is not transactional (an index on an existing
//     collection) runs as before. CFGLAB_TXN_ALL=1 (opts.txnAll) forces every
//     migration into a transaction, to measure which are refused.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { Umzug } = require('umzug');

const MONGO_MIGRATIONS_DIR = path.join(__dirname, '..', 'mongo-migrations');

function listMongoMigrations (dir = MONGO_MIGRATIONS_DIR) {
  return fs.readdirSync(dir).filter((f) => /^\d+-.+\.js$/.test(f)).sort().map((f) => ({
    name: f.replace(/\.js$/, ''),
    file: path.join(dir, f),
    checksum: crypto.createHash('sha256').update(fs.readFileSync(path.join(dir, f))).digest('hex')
  }));
}

async function acquireLease (db, opts) {
  const col = db.collection('schema_migrations_lock');
  const owner = `${process.pid}-${crypto.randomBytes(4).toString('hex')}`;
  const ttl = opts.leaseMs || 30000;
  const deadline = Date.now() + (opts.waitMs || 60000);
  for (;;) {
    const now = new Date();
    try {
      await col.insertOne({ _id: 'lock', owner, expiresAt: new Date(now.getTime() + ttl) });
      break;
    } catch (e) {
      if (e.code !== 11000) throw e;
      const took = await col.findOneAndUpdate(
        { _id: 'lock', expiresAt: { $lt: now } },
        { $set: { owner, expiresAt: new Date(now.getTime() + ttl) } },
        { returnDocument: 'after' });
      if (took) break;
    }
    if (Date.now() > deadline) throw new Error('could not take the migration lease before the deadline');
    await new Promise((r) => setTimeout(r, 200));
  }
  const renew = setInterval(() => {
    col.updateOne({ _id: 'lock', owner }, { $set: { expiresAt: new Date(Date.now() + ttl) } }).catch(() => {});
  }, Math.max(500, Math.floor(ttl / 3)));
  renew.unref();
  return async () => { clearInterval(renew); await col.deleteOne({ _id: 'lock', owner }); };
}

function makeUmzug (db, client, opts) {
  const files = listMongoMigrations(opts.dir);
  const ledger = db.collection('schema_migrations');
  const loggedInTxn = new Set();
  return new Umzug({
    migrations: files.map((m) => ({
      name: m.name,
      up: async () => {
        const mod = require(m.file);
        if (opts.txn && (mod.transactional === true || opts.txnAll)) {
          const session = client.startSession();
          try {
            await session.withTransaction(async () => {
              await mod.up(db, client, { session });
              await ledger.insertOne({ _id: m.name, checksum: m.checksum, appliedAt: new Date(), txn: true }, { session });
            });
          } finally { await session.endSession(); }
          loggedInTxn.add(m.name);
        } else {
          await mod.up(db, client, {});
        }
        if (opts.afterUp) await opts.afterUp(m.name);
      },
      down: async () => require(m.file).down(db, client)
    })),
    context: {},
    logger: undefined,
    storage: {
      executed: async () => (await ledger.find({}).sort({ _id: 1 }).toArray()).map((d) => d._id),
      logMigration: async ({ name }) => {
        if (loggedInTxn.has(name)) return; // recorded inside the migration's transaction
        const m = files.find((f) => f.name === name);
        await ledger.insertOne({ _id: name, checksum: m.checksum, appliedAt: new Date() });
      },
      unlogMigration: async ({ name }) => { await ledger.deleteOne({ _id: name }); }
    }
  });
}

async function run (db, client, opts, fn) {
  const release = opts.lock === false ? null : await acquireLease(db, opts);
  try { return await fn(); } finally { if (release) await release(); }
}

async function mongoUp (db, client, opts = {}) {
  return run(db, client, opts, async () => {
    if (opts.checkDrift !== false) {
      const files = listMongoMigrations(opts.dir);
      const applied = await db.collection('schema_migrations').find({}).toArray();
      const drift = applied.filter((a) => { const f = files.find((x) => x.name === a._id); return !f || f.checksum !== a.checksum; });
      if (drift.length) throw new Error(`migration drift: ${drift.map((d) => d._id).join(', ')} changed or vanished after being applied`);
    }
    return (await makeUmzug(db, client, opts).up()).map((m) => m.name);
  });
}

async function mongoDown (db, client, opts = {}) {
  return run(db, client, opts, async () => (await makeUmzug(db, client, opts).down({ to: 0 })).map((m) => m.name));
}

module.exports = { listMongoMigrations, mongoUp, mongoDown, acquireLease, MONGO_MIGRATIONS_DIR };
