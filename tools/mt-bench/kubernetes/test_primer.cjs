'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { execFile } = require('node:child_process');
const crypto = require('node:crypto');
const { diagnostic } = require('./primer.cjs');

test('unknown message and code are withheld; internal transport and scope remain classified', () => {
  assert.deepEqual(diagnostic(Object.assign(new Error('private-canary'), {code:'PRIVATE_CANARY'})), {error:'PRIMER_UNCLASSIFIED',errorClass:'Error'});
  assert.deepEqual(diagnostic(new Error('SOCKET_IPC_UNAVAILABLE')), {error:'SOCKET_IPC_UNAVAILABLE',requestClass:'internal-ownership',notReady:false});
  assert.deepEqual(diagnostic(new Error('EVALUATOR_SCOPE_UNSAFE')), {error:'EVALUATOR_SCOPE_UNSAFE'});
});

// The deploy primer Job runs the source primer directly (one-call-usable-provisioning):
// `prime.js provision --tenant-count N --concurrency C`, config read from NS_PRIMER_CONFIG
// (/run/ns-primer/config.json) and the roster written to NS_PRIMER_STATE (/run/ns-client).
// One bulk admin call per batch; it sends no DATA request.
test('deploy primer command provisions usable tenants with one bulk admin call, sends no DATA request, and refuses a roster without a credential', {skip: !process.env.K8S_TEST_PRIMER_APP}, async () => {
  const app = process.env.K8S_TEST_PRIMER_APP;
  const demo = require(path.join(app, 'deploy/multitenant/demo-tenants.js'));
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'k8s-source-primer-'));
  const configDir = path.join(root, 'ns-primer'), state = path.join(root, 'ns-client');
  fs.mkdirSync(configDir); fs.mkdirSync(state);
  let behavior = 'usable', batches = 0, data = 0;
  const server = http.createServer(async (req,res) => {
    let raw = ''; for await (const chunk of req) raw += chunk;
    if (req.url !== '/v1/tenants/batch') { data++; res.writeHead(404); return res.end('{}'); }
    batches++;
    const body = JSON.parse(raw);
    const results = body.tenants.map(t => {
      assert.ok(t.bootstrap && t.bootstrap.owner.consumer === 'test-owner' && t.bootstrap.subject.role.permissions.length);
      return {id:t.id, outcome:'created', rootSecret:crypto.randomBytes(24).toString('hex'),
        bootstrap: behavior === 'usable' ? {ownerSubject:crypto.randomUUID().replaceAll('-',''), subject:crypto.randomUUID().replaceAll('-',''),
          accessToken:'synthetic-' + crypto.randomBytes(8).toString('hex'), jwt:'synthetic.jwt.' + t.id, jwtExpiresAt:Math.floor(Date.now()/1000)+28800}
          : {ownerSubject:'o', subject:'s'}};
    });
    res.writeHead(200, {'content-type':'application/json'}); res.end(JSON.stringify({results}));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const config = {version:1, ownerConsumer:'test-owner', adminOrigin:`http://127.0.0.1:${server.address().port}/`};
  fs.writeFileSync(path.join(configDir,'config.json'), JSON.stringify(config), {mode:0o600});
  const run = count => new Promise(resolve => execFile(process.execPath,
    [path.join(app, 'deploy/multitenant/prime.js'), 'provision', '--tenant-count', String(count), '--concurrency', '4'],
    {env:{...process.env, NS_PRIMER_STATE:state, NS_PRIMER_CONFIG:path.join(configDir,'config.json')}, timeout:60000},
    (error, stdout, stderr) => resolve({code:error ? error.code : 0, stdout, stderr})));
  const last = text => JSON.parse(text.trim().split('\n').pop());
  try {
    let outcome = await run(3);
    assert.equal(outcome.code, 0);
    assert.deepEqual(last(outcome.stdout), {state:'synthetic-tenants-usable', tenants:3});
    assert.equal(batches, 1); assert.equal(data, 0);
    const roster = JSON.parse(fs.readFileSync(path.join(state,'tenants.json')));
    assert.deepEqual(roster.tenants.map(row => row.id), demo.tenantIds(3));
    assert.ok(roster.tenants.every(row => row.dataToken && row.jwt && Number.isSafeInteger(row.jwtExpiresAt) && row.ownerSubject));
    assert.ok(!fs.existsSync(path.join(configDir,'tenants.json')));
    assert.ok(!fs.existsSync(path.join(state,'provisioned.json')) && !fs.existsSync(path.join(state,'primed.json')));
    // A completed roster sends nothing on retry.
    outcome = await run(3);
    assert.deepEqual(last(outcome.stdout), {state:'synthetic-tenants-usable', tenants:3});
    assert.equal(batches, 1);
    // A result without a credential is not usable.
    fs.rmSync(path.join(state,'tenants.json')); behavior = 'no-credential';
    outcome = await run(3);
    assert.equal(outcome.code, 1);
    assert.deepEqual(last(outcome.stderr), {error:'PRIMER_CREDENTIAL_NOT_RETURNED', tenants:3});
    assert.ok(!fs.existsSync(path.join(state,'tenants.json')) || JSON.parse(fs.readFileSync(path.join(state,'tenants.json'))).tenants.length === 0);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(root, {recursive:true, force:true});
  }
});
