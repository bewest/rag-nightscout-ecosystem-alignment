'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const net = require('node:net');
const crypto = require('node:crypto');
const { commission, diagnostic } = require('./primer.cjs');

const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

test('unknown message and code are withheld; internal transport and scope remain classified', () => {
  assert.deepEqual(diagnostic(Object.assign(new Error('private-canary'), {code:'PRIVATE_CANARY'})), {error:'PRIMER_UNCLASSIFIED',errorClass:'Error'});
  assert.deepEqual(diagnostic(new Error('SOCKET_IPC_UNAVAILABLE')), {error:'SOCKET_IPC_UNAVAILABLE',requestClass:'internal-ownership',notReady:false});
  assert.deepEqual(diagnostic(new Error('EVALUATOR_SCOPE_UNSAFE')), {error:'EVALUATOR_SCOPE_UNSAFE'});
});

// The source primer is one bulk admin call per batch with a bootstrap block
// (one-call-usable-provisioning); it sends no DATA request.
test('selected primer provisions usable tenants with one bulk admin call, sends no DATA request, and refuses a roster without a credential', {skip: !process.env.K8S_TEST_PRIMER_APP}, async () => {
  const app = process.env.K8S_TEST_PRIMER_APP;
  const demo = require(path.join(app, 'deploy/multitenant/demo-tenants.js'));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'k8s-source-primer-'));
  const config = {version:1, ownerConsumer:'test-owner', adminOrigin:'http://admin:1342', apiOrigin:'http://api:1337'};
  fs.writeFileSync(path.join(dir,'config.json'), JSON.stringify(config), {mode:0o600});
  const fixture = {namespace:'test-primer', runId:'test-run'};
  const env = {NS_FIXTURE_NAMESPACE:fixture.namespace, NS_FIXTURE_RUN_ID:fixture.runId};
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
  const original = http.Agent.prototype.createConnection;
  http.Agent.prototype.createConnection = function (options, cb) { return net.createConnection({...options, host:'127.0.0.1', port:server.address().port}, cb); };
  const args = count => ['--verified-serving', fixture.namespace, fixture.runId, String(Date.now()+60000), String(count), '4', String(count)];
  try {
    const result = await commission({app, dir, env, args:args(3)});
    assert.deepEqual(result, {state:'synthetic-tenants-usable', tenants:3});
    assert.equal(batches, 1); assert.equal(data, 0);
    const roster = JSON.parse(fs.readFileSync(path.join(dir,'tenants.json')));
    assert.deepEqual(roster.tenants.map(row => row.id), demo.tenantIds(3));
    assert.ok(roster.tenants.every(row => row.dataToken && row.jwt && Number.isSafeInteger(row.jwtExpiresAt) && row.ownerSubject));
    assert.ok(!fs.existsSync(path.join(dir,'provisioned.json')) && !fs.existsSync(path.join(dir,'primed.json')));
    // A completed roster sends nothing on retry.
    assert.deepEqual(await commission({app, dir, env, args:args(3)}), {state:'synthetic-tenants-usable', tenants:3});
    assert.equal(batches, 1);
    // A result without a credential is not usable.
    fs.rmSync(path.join(dir,'tenants.json')); behavior = 'no-credential';
    assert.deepEqual(await commission({app, dir, env, args:args(3)}), {error:'PRIMER_CREDENTIAL_NOT_RETURNED'});
    await assert.rejects(commission({app, dir, env:{...env, NS_FIXTURE_RUN_ID:'other'}, args:args(3)}), {code:'K8S_PRIMER_FIXTURE_CHANGED'});
  } finally {
    http.Agent.prototype.createConnection = original;
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(dir, {recursive:true, force:true});
  }
});
