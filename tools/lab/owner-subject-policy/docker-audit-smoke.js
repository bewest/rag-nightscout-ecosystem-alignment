'use strict';

// Run only after this lane's explicit coordinator slot release.
const fs = require('node:fs');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const root = process.env.NS_OWNER_AUDIT_SMOKE_ROOT;
const real = process.env.NS_OWNER_DOCKER_REAL;
if (!root || !real || !path.isAbsolute(root) || !path.isAbsolute(real)) throw new Error('Explicit private scratch root and Docker executable required');
const directory = fs.mkdtempSync(path.join(root, 'owner-audit-smoke-'));
fs.chmodSync(directory, 0o700);
const shim = path.join(__dirname, 'docker-audit.js');
const env = { ...process.env, NS_OWNER_DOCKER_AUDIT: directory, NS_OWNER_DOCKER_REAL: real };
const execute = (binary, args) => spawnSync(binary, args, { encoding: 'utf8', env, timeout: 30000 });
function success (result) {
  if (result.error || result.status !== 0) throw new Error('Owned Docker smoke command failed; private audit: ' + directory);
  return result.stdout.trim();
}
let id, removed = false;
try {
  const name = 'ns-owner-audit-smoke-' + randomBytes(8).toString('hex');
  id = success(execute(process.execPath, [shim, 'create', '--name', name, 'postgres:16']));
  if (!/^[a-f0-9]{64}$/.test(id)) throw new Error('Smoke did not return a full owned ID');
  const file = path.join(directory, id + '.json');
  const before = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (before.id !== id || !Array.isArray(before.volumeIds) || !before.volumeIds.length ||
      (fs.statSync(file).mode & 0o077) || (fs.statSync(directory).mode & 0o077)) throw new Error('Smoke audit identity/mount/privacy mismatch');
  const output = success(execute(process.execPath, [shim, 'rm', '-f', name]));
  if (output !== id) throw new Error('Smoke removal did not target the resolved immutable ID');
  removed = true;
  const after = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (after.containerRemoved !== true) throw new Error('Smoke removal was not recorded');
  for (const volume of before.volumeIds) {
    const result = execute(real, ['volume', 'inspect', volume]);
    const message = (result.stderr || '').trim();
    if (result.error || result.status !== 1 || ![
      'Error response from daemon: get ' + volume + ': no such volume', 'Error: No such volume: ' + volume
    ].includes(message)) throw new Error('Owned recorded volume absence not established; private audit: ' + directory);
  }
  console.log(JSON.stringify({ node: process.version, smoke: 'real Docker create/remove; database never started',
    ownedContainerRemoved: true, volumeCount: before.volumeIds.length, recordedVolumesAbsent: true, privateAudit: true }));
} finally {
  // Never infer ownership from a container name or a global volume listing.
  if (id && /^[a-f0-9]{64}$/.test(id) && !removed) {
    const cleanup = execute(real, ['rm', '-f', '-v', id]);
    if (cleanup.error || cleanup.status !== 0) console.error('Owned smoke cleanup needs private audit review: ' + directory);
  }
}
