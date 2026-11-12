import pathlib,json,subprocess,sys,time,hashlib,os
H=pathlib.Path(__file__).parent;S=pathlib.Path('/tmp/ns-evaluator-binding-proof-20261112-guard');ROOT=pathlib.Path('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/alignment-d6-decisions-20261111');sys.path.insert(0,str(ROOT/'tools/mt-bench/m7-joined'));sys.dont_write_bytecode=True
import evaluator_progress as p
from barrier_process import execute
restart=json.loads((H/'restart-processes.private.json').read_text());rows=restart['after'];services={c['Config']['Labels']['com.docker.compose.service']:c for c in rows};tenants=json.loads((S/'primer/tenants.json').read_text())['tenants'];ids=sorted(t['id']for t in tenants)
def snapshot():
 cs=json.loads(subprocess.check_output(['docker','inspect',*[services[s]['Id']for s in ['api','api-2']]],text=True));return [{k:c[k]for k in ['Id','Image','Config']}|{'StartedAt':c['State']['StartedAt'],'Running':c['State']['Running']}for c in cs]
before=snapshot();targets=[{'service':s,'tenantOrdinal':i,'host':t['host'],'credential':t['dataToken']}for s in ['api','api-2']for i,t in enumerate(tenants)]
js="const fs=require('node:fs'),{validate,read}=require('./deploy/multitenant/fixtures/api-readiness-private.cjs'),{precondition}=require('./deploy/multitenant/fixtures/api-readiness-observation.cjs');let b='';process.stdin.on('data',c=>b+=c);process.stdin.on('end',async()=>{try{const x=validate(JSON.parse(b)),r=await precondition({targets:x.targets,read,timeoutMs:20000});console.log(JSON.stringify(r));if(!r.passed)process.exitCode=1}catch{console.log(JSON.stringify({passed:false,code:'READINESS_REFUSED'}));process.exitCode=1}});"
r=execute(['docker','exec','-i',services['api']['Id'],'node','-e',js],json.dumps({'targets':targets}),H)
identity={'before':before}
try:identity['after']=snapshot();identity['unchanged']=identity['after']==before
except Exception:identity.update(unchanged=False,error='API_IDENTITY_SNAPSHOT_UNAVAILABLE')
(H/'api-readiness-identities.private.json').write_text(json.dumps(identity,indent=2)+'\n')
assert r is not None and r.returncode==0,'API_READINESS_CHILD_REFUSED'
ready=json.loads(r.stdout);assert ready['passed'];assert identity['unchanged']
helper=(ROOT/'tools/mt-bench/m7-joined/evaluator-progress.cjs').read_text();rounds=[];end=time.monotonic()+60
while True:
 def fetch(service,selected,queries,budget):
  prefix='const M7_PROGRESS_IDS='+json.dumps(selected)+';const M7_PROGRESS_QUERY_BUDGET='+str(queries)+';const M7_PROGRESS_BYTE_BUDGET='+str(budget)+';\n'
  r=subprocess.run(['docker','exec','-i',services[service]['Id'],'node','-'],input=(prefix+helper).encode(),capture_output=True,timeout=10);assert r.returncode==0;return r.stdout
 try:
  v=p.round_view(['evaluator','evaluator-2','evaluator-3'],ids,fetch,warming=True);rounds.append({'observedAtMs':time.time_ns()//1000000,'owners':v['owners']})
  if len(v['owners'])==2 and all(t['completedAcquisitions']>0 for t in v['owners'].values()):break
 except p.Refused as error:
  rounds.append({'observedAtMs':time.time_ns()//1000000,'code':str(error),'verdict':error.verdict,'collection':getattr(error,'collection',None)})
  if error.verdict=='FAIL':raise
 assert time.monotonic()<end,'EVALUATOR_RESTART_READINESS_DEADLINE';time.sleep(.25)
(H/'evaluator-readiness.json').write_text(json.dumps(rounds,indent=2)+'\n');print(json.dumps({'ready':True,'apiTuples':4,'evaluatorOwners':2,'readinessRounds':len(rounds)}))
