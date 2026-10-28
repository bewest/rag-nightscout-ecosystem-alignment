'use strict';
// Child process for the migration-tooling tests: `nightscout migrate up` as a
// separate process, so the harness can start several at once or kill one.
// Connection details arrive in the CFGLAB_PG environment variable (JSON) from
// the harness; nothing is read from or written to disk.
//
//   node lib/run-migrate.js up|down [--dir D] [--atomic 0] [--lock 0]
//        [--crash-after NAME] [--checkdrift 0]
const { Client } = require('pg');
const m = require('./migrator');

const args = process.argv.slice(2);
const cmd = args[0];
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };

(async () => {
  const client = new Client(JSON.parse(process.env.CFGLAB_PG));
  await client.connect();
  const o = {
    client,
    dir: opt('dir', m.MIGRATIONS_DIR),
    atomic: opt('atomic', '1') !== '0',
    lock: opt('lock', '1') !== '0',
    checkDrift: opt('checkdrift', '1') !== '0'
  };
  const crashAfter = opt('crash-after', null);
  if (crashAfter) o.afterUp = async (name) => { if (name === crashAfter) process.kill(process.pid, 'SIGKILL'); };
  const done = cmd === 'down' ? await m.migrateDown(o) : await m.migrateUp(o);
  process.stdout.write(JSON.stringify({ ok: true, done }) + '\n');
  await client.end();
})().catch((e) => { process.stdout.write(JSON.stringify({ ok: false, error: e.message }) + '\n'); process.exit(2); });
