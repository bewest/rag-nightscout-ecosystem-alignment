'use strict';

// Loaded only into archived Mocha. Capture only the fixture's exact generated name.
const fs = require('node:fs');
const cp = require('node:child_process');
const original = cp.execFileSync;
const destination = process.env.NS_GATE_DOCKER_AUDIT;
const records = [];
function save () { fs.writeFileSync(destination, JSON.stringify(records), { mode: 0o600 }); }
cp.execFileSync = function (command, args, options) {
  let owned;
  if (command === 'docker' && args[0] === 'rm') {
    owned = records.find(record => args.includes(record.container));
    if (owned) {
      owned.volumeIds = JSON.parse(original('docker', ['inspect', '--format', '{{json .Mounts}}', owned.container],
        { encoding: 'utf8', stdio: 'pipe' })).filter(mount => mount.Type === 'volume').map(mount => mount.Name);
      save();
    }
  }
  const result = original(command, args, options);
  if (command === 'docker' && args[0] === 'run') {
    const name = args[args.indexOf('--name') + 1];
    if (/^ns-tenant-authority-pg-[0-9a-f]{16}$/.test(name) ||
        process.env.NS_OWNER_GATE_PROOF && /^ns-preview-replicas-(pg|vault)-[0-9a-f]{16}$/.test(name)) {
      records.push({ container: name, volumeIds: null }); save();
    }
  }
  if (owned) { owned.containerRemoved = true; save(); }
  return result;
};
