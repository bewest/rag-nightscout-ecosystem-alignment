'use strict';
// Run configuration, the configuration store and the audit log.
// The store stands in for the platform database (tenants, members, operator
// policy, owner values). It is one JSON file in the run's scratch directory;
// the harness is sequential, so there is no locking.
const fs = require('fs');
const path = require('path');

function loadRun (runDir) {
  const run = JSON.parse(fs.readFileSync(path.join(runDir, 'run.json'), 'utf8'));
  run.runDir = runDir;
  run.has = (b) => run.breaks.includes(b);
  return run;
}

// Read a key file. Each role reads only the files it would hold in a real
// deployment; the comment at each call site names why it holds it.
function key (runDir, name) {
  return fs.readFileSync(path.join(runDir, 'keys', name));
}

const storePath = (runDir) => path.join(runDir, 'store.json');

function load (runDir) {
  try { return JSON.parse(fs.readFileSync(storePath(runDir), 'utf8')); } catch (e) {
    return { tenants: {}, policy: {}, owner: {}, pruneOffers: {} };
  }
}

function save (runDir, s) {
  const p = storePath(runDir);
  fs.writeFileSync(p + '.tmp', JSON.stringify(s, null, 2));
  fs.renameSync(p + '.tmp', p);
}

// actor: { kind: 'human'|'service'|'operator-plane'|'none', id, onBehalfOf, verifiedBy }
function audit (runDir, component, entry) {
  const line = JSON.stringify(Object.assign({ ts: new Date().toISOString(), component }, entry));
  fs.appendFileSync(path.join(runDir, 'audit.jsonl'), line + '\n');
}

function readAudit (runDir) {
  try {
    return fs.readFileSync(path.join(runDir, 'audit.jsonl'), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse);
  } catch (e) { return []; }
}

module.exports = { loadRun, key, load, save, audit, readAudit };
