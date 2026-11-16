"""Owned-fixture Vault API policy control, using the existing bootstrap runner.

The caller admits exact container/namespace custody before every invocation and
keeps its original finite deadline. This module launches no process by itself.
Original policy bytes stay in the fixture's private state; public results contain
only fixed classifications, statuses and policy hashes.
"""
import json
from pathlib import Path
import re

SCRIPT = r"""'use strict';
const fs=require('node:fs'),crypto=require('node:crypto');
const [action,owner,project,core,deploy]=process.argv.slice(1);
const need=(condition,code)=>{if(!condition)throw new Error('M7_VAULT_CONTROL_'+code);};
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const read=name=>JSON.parse(fs.readFileSync('/state/'+name,'utf8'));
const original='/state/bootstrap/m7-api-vault-policy.original.private.json';
const deny='path "*" { capabilities = ["deny"] }';
async function main(){
 need(['deny','check','auth-check','restore'].includes(action)&&/^[a-f0-9]{32}$/.test(owner)&&/^[a-z0-9][a-z0-9_-]{0,62}$/.test(project)&&[core,deploy].every(x=>/^[a-f0-9]{40}$/.test(x)),'SCOPE');
 const complete=read('bootstrap/complete.json'),layout=read('bootstrap/layout.json');
 need(complete.version===2&&complete.registryMode===true&&complete.sourceCommit===core&&complete.deployCommit===deploy,'SOURCE');
 need(layout.prefix==='nsdemo'&&layout.mount==='nsdemo_transit','LAYOUT');
 const api=read('api/config.json'),credentials=read('tenant-admin/config.json').ownerCredentials;
 need(api.localDataAuthentication==='node'&&api.vault?.address==='https://vault:8200'&&api.vault.mount===layout.mount&&api.vault.tokenFile==='/run/ns-config/vault-token','API_CONFIG');
 need(credentials?.vault?.address===api.vault.address&&credentials.vault.mount===layout.mount&&credentials.vault.tokenFile==='/run/ns-config/vault-token','OWNER_CONFIG');
 const policy=layout.prefix+'_api',ownerPolicy=layout.prefix+'_owner-credentials';
 const root=read('bootstrap/vault-init.json').root_token;
 const apiToken=fs.readFileSync('/state/api/vault-token','utf8').trim();
 const ownerToken=fs.readFileSync('/state/tenant-admin/vault-token','utf8').trim();
 need(typeof root==='string'&&root.length>0&&apiToken.length>0&&ownerToken.length>0&&new Set([root,apiToken,ownerToken]).size===3,'TOKENS');
 const seed=read('primer/config.json').seed;
 need(Array.isArray(seed)&&seed.length>0&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(seed[0]?.id),'SEED');
 async function request(route,token,body){
  const response=await fetch('https://vault:8200/v1/'+route,{method:body===undefined?'GET':'POST',headers:{'X-Vault-Token':token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)}),redirect:'manual',signal:AbortSignal.timeout(2000)});
  return response;
 }
 async function status(route,token,body){const response=await request(route,token,body);await response.body?.cancel();return response.status;}
 async function getPolicy(name){
  const response=await request('sys/policies/acl/'+name,root);
  need(response.status===200,'POLICY_READ');
  let text='',bytes=0;
  for await(const part of response.body){bytes+=part.length;need(bytes<=65536,'POLICY_BOUND');text+=Buffer.from(part).toString('utf8');}
  const value=JSON.parse(text).data?.policy;need(typeof value==='string'&&Buffer.byteLength(value)<=32768,'POLICY_SHAPE');return value;
 }
 async function setPolicy(value){need(await status('sys/policies/acl/'+policy,root,{policy:value})===204,'POLICY_WRITE');}
 const health=()=>status('sys/health',root);
 // Deliberately malformed ciphertext exercises the real allowed transit route
 // without needing clinical data. Baseline400 differs from policy refusal403.
 const transit=()=>status(layout.mount+'/decrypt/tenant-data-'+seed[0].id,apiToken,{ciphertext:'m7-invalid-ciphertext'});
 let saved;
 if(action==='deny'){
  need(!fs.existsSync(original),'ALREADY_STARTED');
  need(await health()===200,'HEALTH');
  const before=await getPolicy(policy),ownerBefore=await getPolicy(ownerPolicy);
  need(before!==deny,'PREEXISTING_DENIAL');
  need(await transit()===400,'BASELINE_TRANSIT');
  saved={version:1,owner,project,core,deploy,policy,ownerPolicy,original:before,originalSha256:hash(before),ownerPolicySha256:hash(ownerBefore),deniedSha256:hash(deny)};
  fs.writeFileSync(original,JSON.stringify(saved)+'\n',{mode:0o600,flag:'wx'});
  await setPolicy(deny);
 }else{
  need(fs.existsSync(original),'ORIGINAL_MISSING');
  const stat=fs.lstatSync(original);need(stat.isFile()&&!stat.isSymbolicLink()&&(stat.mode&0o077)===0,'ORIGINAL_PRIVATE');
  saved=JSON.parse(fs.readFileSync(original,'utf8'));
 }
 need(saved.version===1&&saved.owner===owner&&saved.project===project&&saved.core===core&&saved.deploy===deploy&&saved.policy===policy&&saved.ownerPolicy===ownerPolicy&&hash(saved.original)===saved.originalSha256&&saved.deniedSha256===hash(deny),'ORIGINAL_BINDING');
 need(hash(await getPolicy(ownerPolicy))===saved.ownerPolicySha256,'OWNER_POLICY_CHANGED');
 const current=await getPolicy(policy);
 if(action==='restore'){
  need([saved.originalSha256,saved.deniedSha256].includes(hash(current)),'POLICY_CHANGED');
  await setPolicy(saved.original);
  need(hash(await getPolicy(policy))===saved.originalSha256,'RESTORE_HASH');
  need(hash(await getPolicy(ownerPolicy))===saved.ownerPolicySha256,'OWNER_POLICY_CHANGED');
  console.log(JSON.stringify({version:1,action,owner,project,policy,ownerPolicy,policySha256:saved.originalSha256,ownerPolicySha256:saved.ownerPolicySha256,restored:true}));return;
 }
 need(hash(current)===saved.deniedSha256,'DENIAL_CHANGED');
 need(await health()===200,'HEALTH');const transitStatus=await transit();need(transitStatus===403,'TRANSIT_NOT_REFUSED');
 const result={version:1,action,owner,project,policy,ownerPolicy,policySha256:saved.deniedSha256,ownerPolicySha256:saved.ownerPolicySha256,healthy:true,transitStatus};
 if(action==='auth-check'){
  const config=read('primer/config.json'),tenants=read('primer/tenants.json');
  const tenant=tenants?.tenants?.[0];
  need(config.apiOrigin==='http://api:1337'&&tenant?.id===seed[0].id&&typeof tenant.host==='string'&&/^[a-z0-9][a-z0-9.-]{0,252}$/.test(tenant.host)&&typeof tenant.dataToken==='string'&&tenant.dataToken.length>0&&tenant.dataToken.length<=4096,'AUTH_CUSTODY');
  const http=require('node:http');
  async function get(route,token){return new Promise((resolve,reject)=>{
   const req=http.request(new URL(route,config.apiOrigin),{method:'GET',headers:{Host:tenant.host,Accept:'application/json',...(token?{Authorization:'Bearer '+token}:{})},timeout:5000},res=>{
    const chunks=[];let bytes=0;
    res.on('data',part=>{bytes+=part.length;if(bytes>65536)req.destroy(new Error('M7_VAULT_CONTROL_AUTH_BYTES'));else chunks.push(part);});
    res.on('end',()=>resolve({status:res.statusCode,body:Buffer.concat(chunks).toString('utf8')}));
    res.on('error',()=>reject(new Error('M7_VAULT_CONTROL_AUTH_RESPONSE')));
   });
   req.on('timeout',()=>req.destroy(new Error('M7_VAULT_CONTROL_AUTH_TIMEOUT')));
   req.on('error',()=>reject(new Error('M7_VAULT_CONTROL_AUTH_REQUEST')));req.end();
  });}
  const exchange=await get('/api/v2/authorization/request/'+encodeURIComponent(tenant.dataToken));
  need(exchange.status===200,'JWT_EXCHANGE');const jwt=JSON.parse(exchange.body).token;
  need(typeof jwt==='string'&&jwt.length<=8192&&/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(jwt),'JWT_SHAPE');
  const parts=jwt.split('.'),signature=Buffer.from(parts[2],'base64url');need(signature.length>0,'JWT_SHAPE');signature[0]^=1;parts[2]=signature.toString('base64url');
  const valid=await get('/api/v3/entries?limit=1',jwt);need(valid.status===200,'JWT_VALID');
  const forged=await get('/api/v3/entries?limit=1',parts.join('.'));need([401,403].includes(forged.status),'JWT_FORGERY_ACCEPTED');
  Object.assign(result,{jwtExchangeStatus:exchange.status,validJWTStatus:valid.status,forgedJWTStatus:forged.status});
 }
 console.log(JSON.stringify(result));
}
main().catch(error=>{const code=/^M7_VAULT_CONTROL_[A-Z_]+$/.test(error?.message||'')?error.message:'M7_VAULT_CONTROL_FAILED';console.error(code);process.exitCode=1;});
"""


def apply(directory, manifest, action, invoke):
    """invoke(compose_argv, timeout=60)->stdout, with native custody admitted.

    Mark denial intent BEFORE this call: a failed deny can have changed policy.
    Finally restore while Vault is alive, including failed-deny cleanup. The
    original remains retained even after a successful, idempotent restoration.
    """
    if action not in ('deny', 'check', 'auth-check', 'restore'):
        raise ValueError('M7_VAULT_CONTROL_ACTION')
    if (manifest.get('attached') or manifest.get('profile') != 'pgstream-sample'
            or type(manifest.get('replicas')) is not int or manifest['replicas'] != 1
            or manifest.get('runPurpose') != 'discovery'
            or not re.fullmatch('[a-f0-9]{32}', manifest.get('owner', ''))
            or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,62}', manifest.get('project', ''))
            or any(not re.fullmatch('[a-f0-9]{40}', manifest.get('pair', {}).get(k, '')) for k in ('core', 'deploy'))):
        raise ValueError('M7_VAULT_CONTROL_SCOPE')
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError('M7_VAULT_CONTROL_DIRECTORY')
    args = ['--profile', 'ops', 'run', '--pull', 'never', '--rm', '--no-deps', 'bootstrap', 'node', '-e', SCRIPT,
            action, manifest['owner'], manifest['project'], manifest['pair']['core'], manifest['pair']['deploy']]
    raw = invoke(args, timeout=60)
    if not isinstance(raw, str) or len(raw.encode()) > 4096:
        raise ValueError('M7_VAULT_CONTROL_RECEIPT_BOUND')
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError('M7_VAULT_CONTROL_RECEIPT') from None
    expected = {'version', 'action', 'owner', 'project', 'policy', 'ownerPolicy', 'policySha256', 'ownerPolicySha256'}
    expected |= {'restored'} if action == 'restore' else {'healthy', 'transitStatus'}
    if action == 'auth-check':
        expected |= {'jwtExchangeStatus', 'validJWTStatus', 'forgedJWTStatus'}
    if (not isinstance(result, dict) or set(result) != expected
            or result['version'] != 1 or result['action'] != action
            or result['owner'] != manifest['owner'] or result['project'] != manifest['project']
            or result['policy'] != 'nsdemo_api' or result['ownerPolicy'] != 'nsdemo_owner-credentials'
            or any(not isinstance(result[k], str) or not re.fullmatch('[a-f0-9]{64}', result[k]) for k in ('policySha256', 'ownerPolicySha256'))
            or (result.get('restored') is not True if action == 'restore' else result.get('healthy') is not True or type(result.get('transitStatus')) is not int or result['transitStatus'] != 403)
            or (action == 'auth-check' and (result.get('jwtExchangeStatus') != 200 or result.get('validJWTStatus') != 200 or result.get('forgedJWTStatus') not in (401, 403)))):
        raise ValueError('M7_VAULT_CONTROL_RECEIPT')
    return result
