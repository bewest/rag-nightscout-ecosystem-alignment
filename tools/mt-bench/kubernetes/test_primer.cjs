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

test('selected primer reaches both Service origins, uses DATA credentials, classifies lost ownership RPC and preserves an uncertain entry', {skip: !process.env.K8S_TEST_PRIMER_APP && !process.env.K8S_TEST_PRIMER_CONTRACT}, async () => {
  const app = process.env.K8S_TEST_PRIMER_APP, contractFile = process.env.K8S_TEST_PRIMER_CONTRACT;
  assert.ok(app && contractFile, 'provide the exact selected image source tree and binding contract');
  const contract = JSON.parse(fs.readFileSync(contractFile));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'k8s-source-primer-'));
  const write = (file, value) => fs.writeFileSync(path.join(dir,file), JSON.stringify(value), {mode:0o600});
  const id = '10000000-0000-4000-8000-000000000001', host = 'tenant.example.test';
  const data = crypto.randomUUID(), management = crypto.randomUUID(), root = crypto.randomUUID();
  const fixture = {namespace:'test-primer',runId:'test-run'};
  const proof = Object.fromEntries(['coreCommit','deployCommit','diagnosticSha256'].map(k=>[k,contract[k]]));
  write('verified.json', {...proof,fixture,credentialBoundary:'admin-private-api'});
  const config = {version:1, seed:[{id,hosts:[host]}],ownerConsumer:'test-owner',adminOrigin:'http://admin:1342',apiOrigin:'http://api:1337'};
  write('config.json', config);
  write('provisioned.json', [{id,hosts:[host],rootSecret:root}]);
  let behavior = 'partial-rpc', entries = 0, calls = 0;
  const seen = new Set();
  const server = http.createServer(async (req,res) => {
    for await (const ignored of req) { /* drain the source request */ }
    calls++;
    let body, status = 200;
    if (req.url === '/api/v2/authorization/roles' && behavior === 'hold') return;
    if (req.url === '/api/v2/authorization/roles') body = [{name:'demo'}];
    else if (req.url === '/api/v2/authorization/subjects') body = [{name:'Synthetic demo uploader',_id:'uploader',accessToken:data},{name:'Synthetic demo owner',_id:'owner'}];
    else if (req.url === '/ownership/list') {
      if (behavior === 'partial-rpc') {status = 503; body = {error:'private-canary'};}
      else body = {outcome:'listed',owners:[{principal:'owner',consumer:'test-owner'}]};
    } else if (req.url.endsWith('/management-sessions')) body = {token:management,expiresAt:2000000000};
    else if (req.url === '/api/v1/entries') {
      assert.equal(req.headers['api-secret'],data);
      entries++;
      if (behavior === 'lose-entry') {res.destroy();return;}
      body = [];
    } else {status=404;body={};}
    res.writeHead(status, {'content-type':'application/json'}); res.end(JSON.stringify(body));
  });
  const original = http.Agent.prototype.createConnection;
  try {
    await new Promise((resolve,reject) => server.once('error',reject).listen(0,'127.0.0.1',resolve));
    // Connect both service addresses to the synthetic loopback server. Routing,
    // request bodies, credentials and replies still traverse real source HTTP.
    http.Agent.prototype.createConnection = function(options, callback) {
      assert.ok(['admin','api'].includes(options.host)); seen.add(options.host);
      return net.createConnection({...options,host:'127.0.0.1',port:server.address().port}, callback);
    };
    const env = {NS_FIXTURE_NAMESPACE:fixture.namespace,NS_FIXTURE_RUN_ID:fixture.runId};
    const options = contract.primerOptions || {};
    const args = [fixture.namespace,fixture.runId,sha(fs.readFileSync(contractFile)),sha(fs.readFileSync(path.join(dir,'verified.json'))),String(Date.now()+30000),'1',
      String(options.concurrency ?? 1), ...(options.maxTenants === undefined ? [] : [String(options.maxTenants)])];
    const run = (overrides={}) => commission({app,dir,contractFile,env,args,...overrides});
    await assert.rejects(run({env:{...env,NS_FIXTURE_RUN_ID:'other'}}), {code:'K8S_PRIMER_FIXTURE_CHANGED'});
    await assert.rejects(run({args:[...args.slice(0,4),'1',...args.slice(5)]}), {code:'K8S_PRIMER_DEADLINE'});
    await assert.rejects(run({args:[args[0],args[1],'0'.repeat(64),...args.slice(3)]}), {code:'K8S_PRIMER_FIXTURE_CHANGED'});
    if (contract.primerOptions) {
      const changed = [...args]; changed[6] = '2';
      await assert.rejects(run({args:changed}), {code:'K8S_PRIMER_OPTIONS_CHANGED'});
      changed[6] = args[6]; changed[7] = '9007199254740992';
      await assert.rejects(run({args:changed}), {code:'K8S_PRIMER_OPTIONS_CHANGED'});
      const legacy = {...contract}; delete legacy.primerOptionProtocol;
      const legacyFile = path.join(dir, 'without-source-protocol.json');
      fs.writeFileSync(legacyFile,JSON.stringify(legacy),{mode:0o600});
      const unproved = [...args]; unproved[2] = sha(fs.readFileSync(legacyFile));
      if (Number(args[6])>32 || Number(args[7])>10000)
        await assert.rejects(run({contractFile:legacyFile,args:unproved}), {code:'K8S_PRIMER_OPTION_SOURCE_UNSUPPORTED'});
      assert.equal(calls,0);
      assert.equal(fs.existsSync(path.join(dir,'prime.lock')),false);
    }
    write('config.json',{...config,adminOrigin:'http://127.0.0.1:1342'});
    await assert.rejects(run(), {code:'PRIMER_ORIGIN_INVALID'}); write('config.json',config);
    assert.equal(calls,0);
    write('prime.lock',{nonce:'other'}); assert.equal((await run()).error,'PRIMER_STATE_IN_USE');
    fs.unlinkSync(path.join(dir,'prime.lock')); assert.equal(calls,0);
    assert.deepEqual(await run(), {error:'SOCKET_IPC_UNAVAILABLE',requestClass:'internal-ownership',notReady:false});
    behavior = 'normal';
    assert.deepEqual(await run(), {state:'synthetic-data-primed',tenants:1});
    const roster = JSON.parse(fs.readFileSync(path.join(dir,'tenants.json')));
    assert.equal(roster.tenants[0].dataToken,data); assert.notEqual(roster.tenants[0].managementToken,data);
    const good = JSON.stringify(roster);
    roster.tenants[0].dataToken=management;write('tenants.json',roster);
    assert.equal((await run()).error,'K8S_PRIMER_ROSTER_CHANGED');
    fs.writeFileSync(path.join(dir,'tenants.json'),good);
    assert.equal((await run()).tenants,1); assert.equal(entries,1); assert.deepEqual([...seen].sort(),['admin','api']);
    fs.unlinkSync(path.join(dir,'tenants.json'));fs.unlinkSync(path.join(dir,'primed.json'));
    behavior='lose-entry'; assert.equal((await run()).error,'PRIMER_CONNECTION_FAILED');
    const before=calls;assert.equal((await run()).error,'PRIMER_ENTRY_OUTCOME_UNCERTAIN');assert.equal(calls,before);assert.equal(entries,2);
    // Simulate a fresh owned state with a held, admitted call. Only fixture
    // setup clears the previous test's journal. The runtime never does this.
    fs.unlinkSync(path.join(dir,'entry-requests.json')); behavior='hold';
    const childArgs = [...args]; childArgs[4] = String(Date.now()+1000);
    const { spawn } = require('node:child_process');
    const childCode = `const http=require('node:http'),net=require('node:net');
      http.Agent.prototype.createConnection=function(options,cb){return net.createConnection({...options,host:'127.0.0.1',port:${server.address().port}},cb)};
      require(${JSON.stringify(require.resolve('./primer.cjs'))}).commission(${JSON.stringify({app,dir,env,contractFile,args:childArgs})})
        .then(result=>console.log(JSON.stringify(result)))`;
    const child = spawn(process.execPath,['-e',childCode],{stdio:['ignore','pipe','pipe']});
    let stdout='';child.stdout.on('data',chunk=>{stdout+=chunk;});
    const exit = await new Promise((resolve,reject)=>{child.once('error',reject);child.once('close',resolve);});
    assert.equal(exit,124);assert.deepEqual(JSON.parse(stdout),{error:'K8S_PRIMER_DEADLINE'});
    assert.ok(fs.existsSync(path.join(dir,'prime.lock')));assert.equal(entries,2);
  } finally {
    http.Agent.prototype.createConnection=original;
    server.closeAllConnections();
    await new Promise(resolve=>server.close(resolve));
    fs.rmSync(dir,{recursive:true,force:true});
  }
});
