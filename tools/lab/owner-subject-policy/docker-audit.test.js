'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { removal } = require('./docker-audit');
const a = 'a'.repeat(64), b = 'b'.repeat(64);
const identify = name => ({ ours: a, peer: b })[name];
const owned = id => id === a;
test('adds volume cleanup only for a positively identified owned container', () => {
  assert.deepEqual(removal(['rm', '-f', 'ours'], identify, owned),
    { args: ['rm', '-f', '--volumes', a], ids: [a] });
});
test('does not widen removal of unknown or mixed-ownership targets', () => {
  for (const args of [['rm', '-f', 'peer'], ['rm', '-f', 'ours', 'peer']]) {
    assert.deepEqual(removal(args, identify, owned), { args, ids: [] });
  }
});
test('uses current ID rather than a reused name', () => {
  const args = ['rm', '-f', 'ours'];
  assert.deepEqual(removal(args, () => b, owned), { args, ids: [] });
});
test('leaves commands and unsupported flag parsing unchanged', () => {
  for (const args of [['volume', 'rm', 'anything'], ['rm', '--', 'ours'], ['rm', '--link', 'ours'], ['inspect', 'ours']]) {
    assert.deepEqual(removal(args, () => { throw new Error('must not inspect'); }, owned), { args, ids: [] });
  }
});
test('does not turn inspection failure into ownership', () => {
  assert.throws(() => removal(['rm', '-f', 'ours'], () => { throw new Error('unavailable'); }, owned), /unavailable/);
});

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const shim = path.join(__dirname, 'docker-audit.js');
function fakeCampaign (mode, action) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'owner-audit-fake-'));
  const directory = path.join(root, 'audit'), state = path.join(root, 'state.json'), binary = path.join(root, 'docker-real');
  fs.mkdirSync(directory, { mode: 0o700 });
  fs.writeFileSync(binary, `#!/usr/bin/env node
const fs=require('node:fs');
const file=process.env.NS_FAKE_DOCKER_STATE, mode=process.env.NS_FAKE_MODE;
const a='a'.repeat(64), b='b'.repeat(64), args=process.argv.slice(2);
const s=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{calls:[]};
s.calls.push(args);
let output='', status=0;
if(args[0]==='create') {
  if(mode==='createfail') status=125; else {s.created=true;output=a;}
} else if(args[0]==='inspect') {
  if(['inspectfail','compensatefail'].includes(mode)) status=1;
  else if(args[2]==='{{.Id}}') {
    output=args[3]==='peer'?b:a;
    if(args[3]==='ours') s.nameReused=true;
  } else output=JSON.stringify([{Type:'volume',Name:'volume-own',Source:'/private/host/path'}, {Type:'bind',Source:'/private/other'}]);
} else if(args[0]==='rm') {
  if(mode==='compensatefail') status=1;
  else {s.ownedRemoved=args.includes(a);s.peerRemoved=args.includes('ours')&&s.nameReused;}
}
fs.writeFileSync(file,JSON.stringify(s));
process.stdout.write(output);process.exitCode=status;
`, { mode: 0o700 });
  const invoke = args => spawnSync(process.execPath, [shim, ...args], { encoding: 'utf8',
    env: { ...process.env, NS_OWNER_DOCKER_REAL: binary, NS_OWNER_DOCKER_AUDIT: directory,
      NS_FAKE_DOCKER_STATE: state, NS_FAKE_MODE: mode, NS_SYNTHETIC_SECRET: 'must-never-be-recorded' } });
  try { action({ invoke, readState: () => JSON.parse(fs.readFileSync(state, 'utf8')),
    readAudit: () => JSON.parse(fs.readFileSync(path.join(directory, a + '.json'), 'utf8')), directory }); }
  finally { fs.rmSync(root, { recursive: true, force: true }); }
}
test('actual wrapper audits IDs only and removes by ID after name reuse at the fake backend', () => {
  fakeCampaign('reuse', ({ invoke, readState, readAudit }) => {
    const created = invoke(['create', '--name', 'ours', 'synthetic-image']);
    assert.equal(created.status, 0, JSON.stringify(created));
    assert.deepEqual(readAudit(), { id: a, volumeIds: ['volume-own'], containerRemoved: false });
    assert.equal(invoke(['rm', '-f', 'ours']).status, 0);
    assert.equal(readState().ownedRemoved, true); assert.equal(readState().peerRemoved, false);
    assert.equal(readAudit().containerRemoved, true);
    assert.equal(JSON.stringify(readAudit()).includes('private'), false);
    assert.equal(JSON.stringify(readAudit()).includes('must-never-be-recorded'), false);
  });
});
test('actual wrapper retains exact returned ownership when inspect and compensation both fail', () => {
  fakeCampaign('compensatefail', ({ invoke, readAudit }) => {
    const result = invoke(['create', '--name', 'ours', 'synthetic-image']);
    assert.equal(result.status, 1); assert.ok(result.stderr.includes(a), result.stderr);
    assert.deepEqual(readAudit(), { id: a, volumeIds: null, containerRemoved: false,
      inspectionPending: true, auditFailed: true });
  });
});
test('actual wrapper records successful compensation after inspection failure', () => {
  fakeCampaign('inspectfail', ({ invoke, readAudit, readState }) => {
    assert.equal(invoke(['create', '--name', 'ours', 'synthetic-image']).status, 1);
    assert.equal(readState().ownedRemoved, true); assert.equal(readAudit().containerRemoved, true);
    assert.equal(readAudit().auditFailed, true);
  });
});
test('actual wrapper forwards failed create and makes no ownership claim', () => {
  fakeCampaign('createfail', ({ invoke, directory, readState }) => {
    assert.equal(invoke(['create', '--name', 'ours', 'synthetic-image']).status, 125);
    assert.deepEqual(fs.readdirSync(directory), []);
    assert.equal(readState().calls.some(call => call[0] === 'rm'), false);
  });
});
