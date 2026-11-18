#!/usr/bin/env python3
"""Focused PostgreSQL proof of the actual compact-native observer SELECT.
Synthetic schema only; no application or connector acceptance is implied.
"""
import argparse,hashlib,json,re,shutil,subprocess,time,uuid
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--node',required=True);p.add_argument('--postgres-image',required=True);a=p.parse_args()
 if not re.fullmatch(r'(?:[a-z0-9./_-]+@)?sha256:[a-f0-9]{64}',a.postgres_image):raise ValueError('PINNED_POSTGRES_IMAGE_REQUIRED')
 root=Path(a.output).resolve();root.mkdir(parents=True,exist_ok=False);frozen=root/'instrument';frozen.mkdir()
 for n in ['completed-oracle.cjs','native-observation.cjs','client-delivery.cjs','native-observation-fixture.cjs']:
  shutil.copyfile(Path(__file__).with_name(n),frozen/n)
 def run(args,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=kw.pop('timeout',20),**kw).stdout
 def node(script,value=None):return run([a.node,'-e',script,str(frozen)],input=None if value is None else json.dumps(value))
 fixture=json.loads(node("const d=process.argv[1];console.log(JSON.stringify(require(d+'/native-observation-fixture.cjs')));"))
 query=json.loads(node("const d=process.argv[1],f=require(d+'/native-observation-fixture.cjs'),o=require(d+'/completed-oracle.cjs');console.log(JSON.stringify({clinical:o.query(f.config,[f.row.tenant],'synthetic-native'),progress:o.progressQuery(f.config,[f.row.tenant])}));"))
 for n,q in query.items():(root/(n+'.sql')).write_text(q+'\n')
 owner=uuid.uuid4().hex;name='ns-mtqual-native-'+owner[:12];cid=None
 receipt={'kind':'focused-native-observer-sql-v1','owner':owner,'containerName':name,'startedAt':time.time(),'instrument':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in frozen.iterdir()},'appAcceptance':'UNMEASURED','controls':{},'cleanup':'UNMEASURED'}
 def save():(root/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 def sql(q):return run(['docker','exec','-i',cid,'psql','-X','-q','-At','-U','postgres','-d','synthetic_test','-v','ON_ERROR_STOP=1'],input=q)
 quote=lambda x:"'"+json.dumps(x,separators=(',',':')).replace("'","''")+"'::jsonb"
 try:
  receipt['imageId']=run(['docker','image','inspect',a.postgres_image,'--format','{{.Id}}']).strip();save()
  # Container-local timeout is independent of this controller. No network,
  # host port, persistent volume or provider resource is created.
  cid=run(['docker','run','-d','--pull','never','--name',name,'--label','ns.mtqual.native='+owner,'--network','none','--cpus','1','--memory','1g','--memory-swap','1g','--pids-limit','128','--tmpfs','/var/lib/postgresql/data:rw,size=268435456','-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=synthetic_test','--entrypoint','timeout',a.postgres_image,'--signal=TERM','--kill-after=10','180','docker-entrypoint.sh','postgres']).strip();receipt['containerId']=cid;save()
  for _ in range(100):
   try:sql('SELECT 1;');break
   except subprocess.CalledProcessError:time.sleep(.1)
  else:raise RuntimeError('OWNED_POSTGRES_NOT_READY')
  r=fixture['row'];output=dict(r['state']['output'])
  for k in ['identity','contentDigest','outputRevision','restoreGeneration']:output.pop(k,None)
  input_state={'kind':'clinical-stream-v2','ready':False,'floor':2,'deleted':0,'stream':r['native']['stream']}
  raw={'kind':'storage-events-v1','head':4,'base':2,'events':[],'last':None,'keys':[]}
  ddl='''CREATE SCHEMA synthetic_clock;CREATE SCHEMA synthetic_checkpoint;CREATE SCHEMA synthetic_entries;CREATE SCHEMA synthetic_control;
CREATE TABLE synthetic_clock.tenant_write_clock(tenant_id uuid PRIMARY KEY,last_stamp bigint);
CREATE TABLE synthetic_checkpoint.tenant_consumer_checkpoint(tenant_id uuid,consumer text,checkpoint bigint,contract_digest text,projection jsonb,work_version integer,work_observed bigint[],work_completed bigint[],output_identity text,output_digest text,output_revision bigint,output_restore_generation bigint,work_enabled boolean,work_due_at bigint,work_pending_at bigint,work_completed_at bigint,PRIMARY KEY(tenant_id,consumer));
CREATE TABLE synthetic_entries.entries(tenant_id uuid,doc jsonb);
CREATE TABLE synthetic_control.tenant_lifecycle_windows(tenant_id uuid PRIMARY KEY,generation bigint,phase text);
'''
  tenant=r['tenant'];digest=r['typed']['contractDigest'];t=r['typed']
  ddl+=f"INSERT INTO synthetic_clock.tenant_write_clock VALUES('{tenant}',{r['stamp']});INSERT INTO synthetic_control.tenant_lifecycle_windows VALUES('{tenant}',1,'active');"
  ddl+=f"INSERT INTO synthetic_checkpoint.tenant_consumer_checkpoint(tenant_id,consumer,checkpoint,projection) VALUES('{tenant}','evaluator-sample',2,{quote([input_state,raw])});"
  ddl+=f"INSERT INTO synthetic_checkpoint.tenant_consumer_checkpoint VALUES('{tenant}','evaluator-sample-completed',2,'{digest}',{quote([{'kind':'evaluator-work-v2','output':output}])},2,ARRAY[NULL,NULL,NULL,NULL,NULL,2]::bigint[],ARRAY[NULL,NULL,NULL,NULL,NULL,2]::bigint[],'{t['identity']}','{t['digest']}',1,1,true,10000,NULL,9000);"
  doc={**r['stored'][0],'device':'synthetic-native-probe'};ddl+=f"INSERT INTO synthetic_entries.entries VALUES('{tenant}',{quote(doc)});"
  ddl+="UPDATE synthetic_checkpoint.tenant_consumer_checkpoint SET projection=jsonb_set(projection,'{0,stream,source_identity}',jsonb_build_object('system_id',(pg_control_system()).system_identifier::text,'timeline',(pg_control_checkpoint()).timeline_id,'database',current_database(),'slot','synthetic_slot')) WHERE consumer='evaluator-sample';"
  (root/'fixture.sql').write_text(ddl+'\n');sql(ddl)
  script="const d=process.argv[1],f=require(d+'/native-observation-fixture.cjs'),o=require(d+'/completed-oracle.cjs');let b='';process.stdin.on('data',x=>b+=x);process.stdin.on('end',()=>console.log(JSON.stringify(o.assess(JSON.parse(b),f.witness,f.clients,2,f.config))));"
  def assess(label,before='',after=''):
   raw=sql('BEGIN;'+before+'SET LOCAL statement_timeout=5000;'+query['clinical']+after+'ROLLBACK;');row=json.loads(raw.strip());(root/(label+'-row.json')).write_text(json.dumps(row,indent=2)+'\n');result=json.loads(node(script,row));receipt['controls'][label]=result;save();return result
  assert assess('normal')['ready'] is True
  bad=assess('wrong-source',"UPDATE synthetic_checkpoint.tenant_consumer_checkpoint SET projection=jsonb_set(projection,'{0,stream,source_identity,system_id}','\"2\"'::jsonb) WHERE consumer='evaluator-sample';")
  assert bad['code']=='M7_COMPLETION_NATIVE_SOURCE'
  assert assess('source-restored')['ready'] is True
  bad=assess('missing-marker','DELETE FROM synthetic_entries.entries;');assert bad['code']=='M7_COMPLETION_STORED'
  assert assess('marker-restored')['ready'] is True
  progress=json.loads(sql('BEGIN READ ONLY;SET LOCAL statement_timeout=5000;'+query['progress']+'ROLLBACK;').strip())
  metadata=json.loads(node("const d=process.argv[1],f=require(d+'/native-observation-fixture.cjs'),o=require(d+'/completed-oracle.cjs');let b='';process.stdin.on('data',x=>b+=x);process.stdin.on('end',()=>console.log(JSON.stringify(o.progressSnapshot([JSON.parse(b)],f.config,[f.row.tenant]))));",progress))
  assert metadata['rows'][0]['native']['inputFloor']=='2';assert metadata['rows'][0]['native']['raw']['head']=='4';assert metadata['rows'][0]['pendingAt'] is None
  (root/'progress.json').write_text(json.dumps(metadata,indent=2)+'\n');receipt['status']='FOCUSED_CONTROL_COMPLETE'
 finally:
  if cid:subprocess.run(['docker','rm','-f','-v',cid],capture_output=True,text=True,timeout=25)
  active=run(['docker','ps','-aq','--no-trunc','--filter','label=ns.mtqual.native='+owner]).splitlines()
  receipt['cleanup']='ABSENT' if not active else 'PRESENT';receipt['endedAt']=time.time();save()
  if active:raise RuntimeError('OWNED_CONTAINER_CLEANUP_FAILED')
 print(json.dumps({'status':receipt.get('status','FAILED'),'cleanup':receipt['cleanup'],'receipt':str(root/'receipt.json')}))
if __name__=='__main__':main()
