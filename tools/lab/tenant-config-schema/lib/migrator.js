'use strict';
// The lab's migrations, run by umzug (the tool the migration-tooling plan
// recommends evaluating), with the three things umzug leaves to its caller:
//
//  1. ATOMICITY. Each migration's SQL and its ledger row commit in ONE
//     transaction, so a process killed mid-migration leaves neither. (umzug
//     calls storage.logMigration after up() returns, as a separate step; with
//     `atomic: false` the lab uses that split, and the crash test shows the gap.)
//  2. A LOCK. A session advisory lock held for the whole run, so several
//     processes starting at once apply each migration once.
//  3. DRIFT. A checksum per applied file; a file edited after it was applied
//     stops the run.
//
// Connection details come from the caller; nothing here reads or stores a password.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { Umzug } = require('umzug');

const MIGRATIONS_DIR = path.join(__dirname, '..', 'migrations');
const LOCK_KEY = 72730001; // arbitrary constant: "the platform schema's migration lock"
const LEDGER = `CREATE TABLE IF NOT EXISTS schema_migrations (
  name       text PRIMARY KEY,
  checksum   text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now())`;

function sha256 (text) { return crypto.createHash('sha256').update(text).digest('hex'); }

function listMigrations (dir = MIGRATIONS_DIR) {
  return fs.readdirSync(dir).filter((f) => /^\d{4}_.+\.up\.sql$/.test(f)).sort().map((f) => {
    const name = f.replace(/\.up\.sql$/, '');
    const up = fs.readFileSync(path.join(dir, f), 'utf8');
    const downPath = path.join(dir, `${name}.down.sql`);
    return { name, up, down: fs.existsSync(downPath) ? fs.readFileSync(downPath, 'utf8') : null, checksum: sha256(up) };
  });
}

// opts: { client (a connected pg.Client as the migration role), atomic, lock,
//         afterUp(name) hook for crash injection, dir, log }
function makeUmzug (opts) {
  const { client } = opts;
  const atomic = opts.atomic !== false;
  const files = listMigrations(opts.dir);
  const migrations = files.map((m) => ({
    name: m.name,
    async up () {
      if (atomic) {
        await client.query('BEGIN');
        try {
          await client.query(m.up);
          await client.query('INSERT INTO schema_migrations (name, checksum) VALUES ($1, $2)', [m.name, m.checksum]);
          if (opts.beforeCommit) await opts.beforeCommit(m.name);
          await client.query('COMMIT');
        } catch (e) { await client.query('ROLLBACK').catch(() => {}); throw e; }
      } else {
        await client.query(m.up); // one simple-protocol query: PostgreSQL runs it as one implicit transaction
      }
      if (opts.afterUp) await opts.afterUp(m.name);
    },
    async down () {
      if (!m.down) throw new Error(`${m.name} has no down migration`);
      await client.query('BEGIN');
      try {
        await client.query(m.down);
        await client.query('DELETE FROM schema_migrations WHERE name = $1', [m.name]);
        await client.query('COMMIT');
      } catch (e) { await client.query('ROLLBACK').catch(() => {}); throw e; }
    }
  }));
  return new Umzug({
    migrations,
    context: {},
    logger: opts.log ? console : undefined,
    storage: {
      async executed () {
        const r = await client.query('SELECT name FROM schema_migrations ORDER BY name');
        return r.rows.map((x) => x.name);
      },
      async logMigration ({ name }) {
        if (atomic) return; // already written inside the migration's transaction
        const m = files.find((f) => f.name === name);
        await client.query('INSERT INTO schema_migrations (name, checksum) VALUES ($1, $2)', [name, m.checksum]);
      },
      async unlogMigration () { /* done inside down()'s transaction */ }
    }
  });
}

async function withLock (client, lock, fn) {
  if (lock !== false) await client.query('SELECT pg_advisory_lock($1)', [LOCK_KEY]);
  try { return await fn(); } finally {
    if (lock !== false) await client.query('SELECT pg_advisory_unlock($1)', [LOCK_KEY]).catch(() => {});
  }
}

async function checkDrift (client, files) {
  const r = await client.query('SELECT name, checksum FROM schema_migrations');
  const drift = r.rows.filter((row) => {
    const f = files.find((x) => x.name === row.name);
    return !f || f.checksum !== row.checksum;
  }).map((row) => row.name);
  if (drift.length) throw new Error(`migration drift: ${drift.join(', ')} changed or vanished after being applied`);
}

// `nightscout migrate up` in miniature.
async function migrateUp (opts) {
  const { client } = opts;
  return withLock(client, opts.lock, async () => {
    await client.query(LEDGER);
    if (opts.checkDrift !== false) await checkDrift(client, listMigrations(opts.dir));
    const umzug = makeUmzug(opts);
    const done = await umzug.up(opts.to ? { to: opts.to } : undefined);
    return done.map((m) => m.name);
  });
}

async function migrateDown (opts) {
  const { client } = opts;
  return withLock(client, opts.lock, async () => {
    await client.query(LEDGER);
    const umzug = makeUmzug(opts);
    const done = await umzug.down({ to: opts.to === undefined ? 0 : opts.to });
    return done.map((m) => m.name);
  });
}

// What a hosted role does at start: refuse to serve on a schema that is behind
// (or ahead of) the code, instead of migrating it.
async function assertCurrent (client, dir) {
  const files = listMigrations(dir).map((f) => f.name);
  const r = await client.query("SELECT to_regclass('schema_migrations') IS NOT NULL AS present");
  const applied = r.rows[0].present ? (await client.query('SELECT name FROM schema_migrations ORDER BY name')).rows.map((x) => x.name) : [];
  const pending = files.filter((f) => !applied.includes(f));
  const unknown = applied.filter((a) => !files.includes(a));
  if (pending.length || unknown.length) {
    throw new Error(`schema not current: pending [${pending.join(', ')}], unknown to this release [${unknown.join(', ')}]; run \`nightscout migrate up\``);
  }
}

module.exports = { listMigrations, makeUmzug, migrateUp, migrateDown, assertCurrent, checkDrift, LOCK_KEY, MIGRATIONS_DIR };
