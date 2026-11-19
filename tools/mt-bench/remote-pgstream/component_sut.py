"""SUT-only selected snapshots/oracles for explicit remote component cases."""
raise ImportError('NOT-RUNNABLE: tools/mt-bench/remote-pgstream imports harness modules deleted on 2026-11-19; see tools/mt-bench/remote-pgstream/README.md')
import json,time
from pathlib import Path
from component_cases import need,phase_payload,selected,expected_clients,reduce_case

def snapshot(d,m,case,output):
 # One bounded selected EV request per process and one cached RT request; no roster scan.
 import adapter as a
 ids=[x['id']for x in selected(a.document(d/'tenants.private.json'))];records=[];evraw={};cfg=a.document(d/'frozen.compose.json')
 for role,spec in cfg['services'].items():
  command=spec.get('command',[]);kind=command[-1]if isinstance(command,list)and command else None
  if kind not in('evaluator','realtime'):continue
  need(sum(x['kind']==kind for x in records)<4,'INSTANCE_BOUND')
  start=time.monotonic_ns()
  if kind=='evaluator':raw=a.progress_fetch(d,role,ids,1,1048576);evraw[role]=raw
  else:raw=a.compose(d,'exec','-T',role,'node','-',input=(a.HERE/'realtime-costs.cjs').read_bytes(),timeout=10)
  end=time.monotonic_ns();need(len(raw.encode()if isinstance(raw,str)else raw)<=1048576,'SNAPSHOT_BOUND')
  records.append({'service':role,'kind':kind,'monotonicStartNs':start,'monotonicEndNs':end,'pages':[json.loads(line)for line in raw.splitlines()]})
 value={'case':phase_payload(case),'pair':m['pair'],'imageId':m['imageId'],'sampleIds':ids,'clockDomain':'SUT collector CLOCK_MONOTONIC request brackets; remote service ages remain native','records':records}
 a.write(output,value)
 import evaluator_progress
 value['progress']=evaluator_progress.round_view(list(evraw),ids,lambda service,*args:evraw[service])
 a.write(output,value);return value

def completed(d,m,case,maximum=120):
 # Existing oracle, with explicit bounded case cardinality and frozen APPLICATION database.
 import adapter as a
 probe=a.document(d/'load/probe.json');w=probe.get('clientWitnesses');full={x['id']for x in a.document(d/'tenants.private.json')};sample={x['id']for x in selected(a.document(d/'tenants.private.json'))}
 need(isinstance(w,list)and 1<=len(w)<=case['maxWrites']<=32 and all(x.get('tenant')in sample and isinstance(x.get('clients'),list)and len(x['clients'])<=case['viewers']for x in w),'CLIENT_WITNESS_BOUND')
 need(len({(x['tenant'],x['date'])for x in w})==len(w),'DUPLICATE_WITNESS')
 cfg=a.document(d/'completion-source.json');need(cfg['kind']=='evaluator-work-v2'and cfg['binding']['pair']==m['pair']and cfg['binding']['imageId']==m['imageId'],'COMPLETION_SOURCE')
 ids=sorted({x['tenant']for x in w});marker=(d/'load/runid').read_text().strip()
 script="const o=require(process.argv[1]);const s=JSON.parse(require('fs').readFileSync(0));console.log(JSON.stringify(s.mode==='query'?o.query(s.config,s.ids,s.marker):s.witnesses.map(w=>o.assess(s.rows.find(r=>r.tenant===w.tenant),w,w.clients,s.expected,s.config))));"
 def node(value):return json.loads(a.command(['node','-e',script,a.HERE/'completed-oracle.cjs'],input=json.dumps(value).encode()))
 query=node(dict(mode='query',config=cfg,ids=ids,marker=marker));deadline=time.monotonic()+maximum;stamps={};database=a.application_database(d)
 while True:
  rows=[json.loads(line)for line in a.psql(d,query,database).splitlines()if line]
  for row in rows:stamps.setdefault(row['tenant'],row['stamp'])
  witnesses=[{**x,'stamp':stamps.get(x['tenant'])}for x in w]
  assessed=node(dict(mode='assess',config=cfg,rows=rows,witnesses=witnesses,expected=case['viewers']))
  ok=len(w)==case['maxWrites']and all(x.get('acked')is True for x in w)and all(x.get('ready')is True for x in assessed)
  value={'verdict':'PASS'if ok else'UNMEASURED','case':phase_payload(case),'witnesses':assessed,'selectedTenantCount':len(ids),'rosterTenants':m['tenants'],'viewersPerTenant':case['viewers'],'databaseSource':'frozen Compose POSTGRES_DB','observer':'SUT-only batched16selected query AFTER steady bookend; no cross-host or per-write execution latency','clinicalScope':'existing stored-row/durable observed+completed/input/output/frame/BG-now/actual connected-client oracle; remaining properties unassessed','writeToEvaluationMs':'UNMEASURED'}
  a.write(d/'completed-output.json',value);a.write(d/'completed-output.private.json',{'rows':rows,'clientWitnesses':witnesses})
  if ok:return value
  hard={'M7_COMPLETION_READER_MISMATCH','M7_COMPLETION_TYPED_STATE','M7_COMPLETION_BG_NOW'}
  need(not any(x.get('code')in hard for x in assessed),'SEMANTIC_OUTPUT_REFUSAL')
  if time.monotonic()>=deadline:return value
  time.sleep(1)

def counts(d,m,case):
 import adapter as a
 from contract import oracle
 probe=a.document(d/'load/probe.json');witnesses=probe.get('clientWitnesses',[]);stored=a.stored(d,(d/'load/runid').read_text().strip());probes=a.document(d/'load/fanout.json')['probeWrites']['byTenant'];tenants=a.document(d/'tenants.private.json');known={x['id']for x in tenants};bounds=[]
 need(set(stored)<=known,'WRONG_STORED_TENANT')
 need(all(not v.get('probe',0)or tenant in {x['tenant']for x in witnesses}for tenant,v in stored.items()),'WRONG_PROBE_TENANT')
 for tenant in {x['tenant']for x in witnesses}:
  accepted=sum(x.get('acked')is True for x in witnesses if x['tenant']==tenant);uncertain=sum(x.get('acked')is not True for x in witnesses if x['tenant']==tenant);count=stored.get(tenant,{}).get('probe',0)
  need(accepted<=count<=accepted+uncertain,'WRONG_PROBE_COUNT_BOUND');bounds.append({'tenant':tenant,'accepted':accepted,'uncertainUpperBound':uncertain,'stored':count})
 uncertain=any(x['uncertainUpperBound']for x in bounds)
 if case['kind']=='rest':
  if uncertain:
   result=oracle(stored,a.document(d/'load/k6-summary.json')['metrics'],probes,tenants,strict=False,probes_known=False);a.write(d/'load/oracle.json',result)
  else:result=a.count_oracle(d,strict=False)
  need(result['verdict']!='RED','WRONG_STORED_DATA')
  if not uncertain and result.get('uncertain')==0 and all(x['accepted']>0 for x in result['rows']):a.oracle_control(d)
  else:a.write(d/'load/oracle-control.json',{'verdict':'UNMEASURED','reason':'partial ordinary or probe reconciliation'})
  return{**result,'probeConservativeBounds':bounds,'probeExact':not uncertain}
 # No invented k6 summary: existing count oracle is invoked explicitly with no ordinary scenarios.
 result=oracle(stored,{},probes,tenants,allow_empty=True,probes_known=not uncertain)
 need(result['verdict']!='RED','WRONG_STORED_DATA');return{**result,'probeConservativeBounds':bounds,'probeExact':not uncertain,'scope':'probe-only stored counts; failed acknowledgements are uncertain, not wrong-data or exact-reconciliation claims; ordinary scenario NOT_RUN'}
