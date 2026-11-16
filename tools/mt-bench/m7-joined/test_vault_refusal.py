import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import vault_refusal as subject


HARNESS = r"""
const vm=require('node:vm'),crypto=require('node:crypto'),fs=require('node:fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const original='path "nsdemo_transit/decrypt/tenant-data-*" { capabilities = ["update"] }';
const ownerOriginal='path "nsdemo_transit/decrypt/tenant-data-*" { capabilities = ["update"] }';
let policies={nsdemo_api:original,'nsdemo_owner-credentials':ownerOriginal},apiWrites=0,ownerWrites=0;
const files={
 '/state/bootstrap/complete.json':JSON.stringify({version:2,registryMode:true,sourceCommit:'c'.repeat(40),deployCommit:'d'.repeat(40)}),
 '/state/bootstrap/layout.json':JSON.stringify({prefix:'nsdemo',mount:'nsdemo_transit'}),
 '/state/api/config.json':JSON.stringify({localDataAuthentication:'node',vault:{address:'https://vault:8200',mount:'nsdemo_transit',tokenFile:'/run/ns-config/vault-token'}}),
 '/state/tenant-admin/config.json':JSON.stringify({ownerCredentials:{vault:{address:'https://vault:8200',mount:'nsdemo_transit',tokenFile:'/run/ns-config/vault-token'}}}),
 '/state/bootstrap/vault-init.json':JSON.stringify({root_token:'synthetic-root'}),
 '/state/api/vault-token':'synthetic-api',
 '/state/tenant-admin/vault-token':'synthetic-owner',
 '/state/primer/config.json':JSON.stringify({apiOrigin:'http://api:1337',seed:[{id:'00000000-0000-4000-8000-000000000001'}]}),
 '/state/primer/tenants.json':JSON.stringify({version:1,tenants:[{id:'00000000-0000-4000-8000-000000000001',host:'a.example.test',dataToken:'synthetic-subject'}]})
};
const fakefs={readFileSync:p=>{if(!(p in files))throw Error('missing');return files[p];},
 existsSync:p=>p in files,lstatSync:p=>({isFile:()=>true,isSymbolicLink:()=>false,mode:0o100600}),
 writeFileSync:(p,text,options)=>{if(options.flag==='wx'&&p in files)throw Error('exists');files[p]=text;}};
const body=text=>({async *[Symbol.asyncIterator](){yield Buffer.from(text);},async cancel(){}});
const jwt='eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiJzeW50aGV0aWMifQ.c2lnbmF0dXJl';
const fakehttp={request(url,options,callback){
 const EventEmitter=require('node:events');const request=new EventEmitter();request.destroy=error=>request.emit('error',error);
 request.end=()=>queueMicrotask(()=>{
  const response=new EventEmitter();response.statusCode=url.pathname.startsWith('/api/v2/')?200:options.headers.Authorization==='Bearer '+jwt?200:(input.forgedAccepted?200:401);
  callback(response);response.emit('data',Buffer.from(url.pathname.startsWith('/api/v2/')?JSON.stringify({token:jwt}):'{}'));response.emit('end');
 });return request;
}};
async function fetch(url,options){
 const route=url.slice('https://vault:8200/v1/'.length);
 if(route==='sys/health')return {status:input.health||200,body:body('{}')};
 if(route.startsWith('sys/policies/acl/')){
  const name=route.slice('sys/policies/acl/'.length);
  if(options.method==='POST'){
   if(name==='nsdemo_owner-credentials')ownerWrites++;else apiWrites++;
   const next=JSON.parse(options.body).policy;
   if(input.restoreFails&&next===original&&apiWrites>1)return {status:500,body:body('{}')};
   policies[name]=next;
   if(input.ownerChanged&&apiWrites===1)policies['nsdemo_owner-credentials']='unexpected';
   return {status:204,body:body('')};
  }
  return {status:200,body:body(JSON.stringify({data:{policy:policies[name]}}))};
 }
 if(route.startsWith('nsdemo_transit/decrypt/tenant-data-')){
  const denied=policies.nsdemo_api.includes('["deny"]');
  return {status:denied?(input.refusalAbsent?200:403):(input.preexistingRefusal?403:400),body:body('{}')};
 }
 throw Error('unexpected-route');
}
(async()=>{
 const runs=[];
 for(const action of input.actions||['deny','check','restore','restore']){
  const process={argv:['node',action,input.wrongOwner&&action==='restore'?'e'.repeat(32):'a'.repeat(32),'own-fixture','c'.repeat(40),'d'.repeat(40)],exitCode:0};
  const logs=[],errors=[];
  await vm.runInNewContext(input.script,{require:n=>n==='node:fs'?fakefs:n==='node:http'?fakehttp:require(n),process,fetch,AbortSignal,Buffer,URL,console:{log:x=>logs.push(x),error:x=>errors.push(x)}});
  runs.push({action,code:process.exitCode,logs,errors});
 }
 console.log(JSON.stringify({runs,ownerWrites,apiWrites,restored:policies.nsdemo_api===original,ownerUnchanged:policies['nsdemo_owner-credentials']===ownerOriginal,
 originalRetained:'/state/bootstrap/m7-api-vault-policy.original.private.json' in files}));
})().catch(()=>process.exitCode=2);
"""


class NativeScriptTests(unittest.TestCase):
    def run_script(self, **scenario):
        node = shutil.which('node')
        self.assertIsNotNone(node)
        result = subprocess.run([node, '--max-old-space-size=128', '-e', HARNESS],
                                input=json.dumps({'script': subject.SCRIPT, **scenario}),
                                capture_output=True, text=True, timeout=10, check=True)
        return json.loads(result.stdout)

    def test_real_control_flow_denies_checks_and_restores_exact_policy_idempotently(self):
        result = self.run_script()
        self.assertEqual([x['code'] for x in result['runs']], [0, 0, 0, 0])
        self.assertTrue(result['restored'])
        self.assertTrue(result['originalRetained'])
        self.assertEqual(result['ownerWrites'], 0)
        self.assertTrue(result['ownerUnchanged'])
        denied = json.loads(result['runs'][0]['logs'][0])
        self.assertEqual(denied['transitStatus'], 403)
        self.assertTrue(denied['healthy'])

    def test_absent_native_refusal_fails_but_original_can_still_be_restored(self):
        result = self.run_script(refusalAbsent=True, actions=['deny', 'restore'])
        self.assertEqual(result['runs'][0]['errors'], ['M7_VAULT_CONTROL_TRANSIT_NOT_REFUSED'])
        self.assertEqual(result['runs'][1]['code'], 0)
        self.assertTrue(result['restored'])

    def test_preexisting_refusal_does_not_prove_control_or_mutate(self):
        result = self.run_script(preexistingRefusal=True, actions=['deny'])
        self.assertEqual(result['runs'][0]['errors'], ['M7_VAULT_CONTROL_BASELINE_TRANSIT'])
        self.assertEqual(result['apiWrites'], 0)

    def test_unhealthy_vault_is_not_permission_refusal(self):
        result = self.run_script(health=503, actions=['deny'])
        self.assertEqual(result['runs'][0]['errors'], ['M7_VAULT_CONTROL_HEALTH'])
        self.assertEqual(result['apiWrites'], 0)

    def test_restore_failure_is_not_reported_as_restored(self):
        result = self.run_script(restoreFails=True, actions=['deny', 'restore'])
        self.assertEqual(result['runs'][1]['errors'], ['M7_VAULT_CONTROL_POLICY_WRITE'])
        self.assertFalse(result['restored'])
        self.assertTrue(result['originalRetained'])

    def test_owner_policy_change_is_refused_without_writing_owner_policy(self):
        result = self.run_script(ownerChanged=True, actions=['deny'])
        self.assertEqual(result['runs'][0]['errors'], ['M7_VAULT_CONTROL_OWNER_POLICY_CHANGED'])
        self.assertEqual(result['ownerWrites'], 0)

    def test_wrong_fixture_cannot_restore(self):
        result = self.run_script(wrongOwner=True, actions=['deny', 'restore'])
        self.assertEqual(result['runs'][1]['errors'], ['M7_VAULT_CONTROL_ORIGINAL_BINDING'])
        self.assertFalse(result['restored'])

    def test_actual_auth_chain_uses_exchanged_jwt_and_refuses_corrupted_signature(self):
        result = self.run_script(actions=['deny', 'auth-check', 'restore'])
        self.assertEqual([x['code'] for x in result['runs']], [0, 0, 0])
        value = json.loads(result['runs'][1]['logs'][0])
        self.assertEqual((value['jwtExchangeStatus'], value['validJWTStatus'], value['forgedJWTStatus']), (200, 200, 401))
        self.assertTrue(result['restored'])

    def test_forged_signature_acceptance_fails_and_restoration_still_runs(self):
        result = self.run_script(forgedAccepted=True, actions=['deny', 'auth-check', 'restore'])
        self.assertEqual(result['runs'][1]['errors'], ['M7_VAULT_CONTROL_JWT_FORGERY_ACCEPTED'])
        self.assertEqual(result['runs'][2]['code'], 0)
        self.assertTrue(result['restored'])


class InvocationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.manifest = {'profile': 'pgstream-sample', 'runPurpose': 'discovery', 'replicas': 1,
                         'owner': 'a' * 32, 'project': 'own-fixture',
                         'pair': {'core': 'c' * 40, 'deploy': 'd' * 40}}

    def receipt(self, action):
        result = {'version': 1, 'action': action, 'owner': 'a' * 32, 'project': 'own-fixture',
                  'policy': 'nsdemo_api', 'ownerPolicy': 'nsdemo_owner-credentials',
                  'policySha256': '1' * 64, 'ownerPolicySha256': '2' * 64}
        result.update({'restored': True} if action == 'restore' else {'healthy': True, 'transitStatus': 403})
        return result

    def test_existing_bootstrap_seam_has_no_secret_argv_and_bounded_timeout(self):
        calls = []
        def invoke(args, **options):
            calls.append((args, options))
            return json.dumps(self.receipt('deny'))
        subject.apply(self.directory.name, self.manifest, 'deny', invoke)
        self.assertEqual(calls[0][0][:10], ['--profile', 'ops', 'run', '--pull', 'never', '--rm', '--no-deps', 'bootstrap', 'node', '-e'])
        self.assertEqual(calls[0][1], {'timeout': 60})
        self.assertNotIn('synthetic-api', ' '.join(calls[0][0]))

    def test_attached_or_non_discovery_fixture_refuses_before_dispatch(self):
        for change in ({'attached': True}, {'runPurpose': 'acceptance'}, {'owner': 'foreign'}, {'replicas': 2}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'SCOPE'):
                subject.apply(self.directory.name, {**self.manifest, **change}, 'deny', lambda *a, **k: self.fail('dispatched'))

    def test_forged_receipt_or_extra_payload_is_refused(self):
        for change in ({'owner': 'b' * 32}, {'transitStatus': 200}, {'healthy': False}, {'raw': 'must-not-pass'}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'RECEIPT'):
                subject.apply(self.directory.name, self.manifest, 'deny', lambda *a, **k: json.dumps({**self.receipt('deny'), **change}))


if __name__ == '__main__':
    unittest.main()
