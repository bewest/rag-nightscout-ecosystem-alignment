#!/usr/bin/env node
'use strict';

// Per-campaign instrumentation, not a general Docker authorization boundary.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const ID = /^[a-f0-9]{64}$/;

function removal (args, identify, isOwned) {
  if (args[0] !== 'rm') return { args, ids: [] };
  const targets = args.slice(1).filter(arg => !arg.startsWith('-'));
  const flags = args.slice(1).filter(arg => arg.startsWith('-'));
  if (!targets.length || flags.some(flag => !/^-[fv]+$/.test(flag) && !['--force', '--volumes'].includes(flag))) {
    return { args, ids: [] };
  }
  const ids = targets.map(identify);
  if (!ids.every(isOwned)) return { args, ids: [] };
  return { args: ['rm', ...flags, '--volumes', ...ids], ids };
}

function main () {
  const real = process.env.NS_OWNER_DOCKER_REAL;
  const directory = process.env.NS_OWNER_DOCKER_AUDIT;
  if (!real || !path.isAbsolute(real) || fs.realpathSync(real) === fs.realpathSync(__filename) ||
      !directory || !path.isAbsolute(directory)) throw new Error('Explicit real Docker binary and private audit directory required');
  const stat = fs.statSync(directory);
  if (!stat.isDirectory() || (stat.mode & 0o077)) throw new Error('Audit directory must be private (0700)');
  const execute = args => spawnSync(real, args, { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
  const inspect = args => {
    const result = execute(args);
    if (result.error || result.status !== 0) throw new Error('Owned Docker audit inspection failed');
    return result.stdout.trim();
  };
  const file = id => {
    if (!ID.test(id)) throw new Error('Invalid container identity');
    return path.join(directory, id + '.json');
  };
  const record = data => {
    const target = file(data.id), temporary = target + '.' + process.pid + '.tmp';
    fs.writeFileSync(temporary, JSON.stringify(data) + '\n', { mode: 0o600 });
    fs.renameSync(temporary, target);
  };
  const identify = target => inspect(['inspect', '--format', '{{.Id}}', target]);
  const args = process.argv.slice(2);
  const selected = removal(args, identify, id => ID.test(id) && fs.existsSync(file(id)));
  const result = execute(selected.args);
  if (result.error) throw new Error('Docker invocation failed');
  if (result.status === 0 && ['create', 'run'].includes(args[0])) {
    const id = result.stdout.trim();
    if (ID.test(id)) {
      let data = { id, volumeIds: null, containerRemoved: false, inspectionPending: true };
      // Record only IDs and Mount volume names. Never capture args, env or URLs.
      try {
        record(data); // Preserve exact ownership before a subsequent inspect can fail.
        if (identify(id) !== id) throw new Error('Returned Docker identity mismatch');
        const volumeIds = JSON.parse(inspect(['inspect', '--format', '{{json .Mounts}}', id]))
          .filter(mount => mount.Type === 'volume').map(mount => mount.Name);
        data = { id, volumeIds, containerRemoved: false };
        record(data);
      } catch (error) {
        // The successful create/run output proves ownership of this exact ID.
        const cleanup = execute(['rm', '-f', '-v', id]);
        const removed = !cleanup.error && cleanup.status === 0;
        try { record({ ...data, auditFailed: true, containerRemoved: removed }); } catch {}
        if (cleanup.error || cleanup.status !== 0) {
          throw new Error('Audit failed and exact newly-created container cleanup failed: ' + id);
        }
        throw error;
      }
    } else if (!args.includes('--rm')) {
      throw new Error('Unrecorded Docker create/run output; detached test services required');
    }
  }
  if (result.status === 0) {
    for (const id of selected.ids) {
      const data = JSON.parse(fs.readFileSync(file(id), 'utf8'));
      record({ ...data, containerRemoved: true });
    }
  }
  process.stdout.write(result.stdout || '');
  process.stderr.write(result.stderr || '');
  process.exitCode = result.status === null ? 1 : result.status;
}

module.exports = { removal };
if (require.main === module) {
  try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
