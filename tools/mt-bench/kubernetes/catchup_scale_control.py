#!/usr/bin/env python3
"""One owned, finite PostgreSQL fixture for progress transport differential controls.

No Kubernetes or application actor. Legacy progress SELECTs (64 tenants each)
and the one-SELECT compact transport read the same synthetic native state twice.
Raw rows stay outside Git. This measures local observer transport, not capacity.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

M7 = Path(__file__).resolve().parents[1] / 'm7-joined'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--node', required=True)
    parser.add_argument('--postgres-image', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', args.postgres_image):
        raise ValueError('PINNED_POSTGRES_IMAGE_REQUIRED')
    os.umask(0o077)
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    owner = uuid.uuid4().hex
    name = 'ns-catchup-scale-' + owner[:12]
    receipt = {'kind':'catchup-progress-transport-control-v1', 'owner':owner,
               'sourceHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=M7,text=True).strip(),
               'instrumentSha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                   [M7/'completed-oracle.cjs', M7/'native-observation.cjs', M7/'progress-transport.cjs']},
               'containerName':name, 'imageId':args.postgres_image, 'startedAt':time.time(),
               'scope':'local synthetic observer SQL/serialization only; Kubernetes transport, application, clinical and capacity UNMEASURED',
               'samples':[], 'controls':{}, 'cleanup':'UNMEASURED'}
    cid = None
    def save():
        (root/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    def run(argv, *, data=None, timeout=60, check=True):
        return subprocess.run(argv,input=data,capture_output=True,timeout=timeout,check=check)
    def node(script, value=None):
        return json.loads(run([args.node,'-e',script,str(M7)],
                            data=None if value is None else json.dumps(value).encode()).stdout)
    def sql(text, *, check=True):
        return run(['docker','exec','-i',cid,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','postgres','-d','synthetic_test'],
                   data=text.encode(),check=check)
    def quote(value):
        return "'"+json.dumps(value,separators=(',',':')).replace("'","''")+"'::jsonb"
    bridge = "const m=process.argv[1],o=require(m+'/completed-oracle.cjs'),t=require(m+'/progress-transport.cjs'),x=JSON.parse(require('fs').readFileSync(0));try{console.log(JSON.stringify(x.mode==='queries'?{old:x.batches.map(ids=>o.progressQuery(x.config,ids)),new:t.query(x.config,x.ids)}:x.mode==='compact'?t.snapshot(x.rows,x.config,x.ids):o.progressSnapshot(x.rows,x.config,x.ids)));}catch(e){console.log(JSON.stringify({refused:e.message}));}"
    try:
        cid = run(['docker','run','-d','--pull','never','--name',name,'--label','ns.catchup.scale='+owner,
                   '--network','none','--cpus','1','--memory','1g','--memory-swap','1g','--pids-limit','128',
                   '--tmpfs','/var/lib/postgresql/data:rw,size=536870912',
                   '-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=synthetic_test',
                   '--entrypoint','timeout',args.postgres_image,'--signal=TERM','--kill-after=10','300',
                   'docker-entrypoint.sh','postgres']).stdout.decode().strip()
        receipt['containerId']=cid;save()
        for _ in range(100):
            if sql('SELECT 1;',check=False).returncode==0:break
            time.sleep(.1)
        else:raise RuntimeError('OWNED_POSTGRES_NOT_READY')
        receipt['postgresVersion']=sql('SHOW server_version;').stdout.decode().strip()
        f=node("console.log(JSON.stringify(require(process.argv[1]+'/native-observation-fixture.cjs')))")
        c,r=f['config'],f['row'];t=r['typed']
        output={key:value for key,value in r['state']['output'].items() if key not in ('identity','contentDigest','outputRevision','restoreGeneration')}
        projection=[{'kind':'evaluator-work-v2','output':output}]
        source={'kind':'clinical-stream-v2','floor':2,'stream':r['native']['stream']}
        raw={'kind':'storage-events-v1','head':4,'base':2}
        ddl='''CREATE SCHEMA synthetic_clock; CREATE SCHEMA synthetic_checkpoint; CREATE SCHEMA synthetic_control;
CREATE TABLE synthetic_clock.tenant_write_clock(tenant_id uuid PRIMARY KEY,last_stamp bigint);
CREATE TABLE synthetic_control.tenant_lifecycle_windows(tenant_id uuid PRIMARY KEY,generation bigint,phase text);
CREATE TABLE synthetic_checkpoint.tenant_consumer_checkpoint(tenant_id uuid,consumer text,checkpoint bigint,contract_digest text,projection jsonb,work_version integer,work_observed bigint[],work_completed bigint[],output_identity text,output_digest text,output_revision bigint,output_restore_generation bigint,work_enabled boolean,work_due_at bigint,work_pending_at bigint,work_completed_at bigint,PRIMARY KEY(tenant_id,consumer));
CREATE TEMP TABLE roster AS SELECT (lpad(to_hex(n),8,'0')||'-1111-4111-8111-111111111111')::uuid AS tenant FROM generate_series(1,10000) n;
INSERT INTO synthetic_clock.tenant_write_clock SELECT tenant,9007199254740993 FROM roster;
INSERT INTO synthetic_control.tenant_lifecycle_windows SELECT tenant,1,'active' FROM roster;
'''
        ddl+=f"INSERT INTO synthetic_checkpoint.tenant_consumer_checkpoint(tenant_id,consumer,checkpoint,projection) SELECT tenant,'evaluator-sample',2,{quote([source,raw])} FROM roster;"
        ddl+=f"INSERT INTO synthetic_checkpoint.tenant_consumer_checkpoint SELECT tenant,'evaluator-sample-completed',2,'{t['contractDigest']}',jsonb_set({quote(projection)},'{{0,output,tenant}}',to_jsonb(tenant::text)),2,ARRAY[NULL,NULL,NULL,NULL,NULL,2]::bigint[],ARRAY[NULL,NULL,NULL,NULL,NULL,2]::bigint[],'{t['identity']}','{t['digest']}',1,1,true,NULL,NULL,9000 FROM roster;"
        ddl+="UPDATE synthetic_checkpoint.tenant_consumer_checkpoint SET projection=jsonb_set(projection,'{0,stream,source_identity}',jsonb_build_object('system_id',(pg_control_system()).system_identifier::text,'timeline',(pg_control_checkpoint()).timeline_id,'database',current_database(),'slot','synthetic_slot')) WHERE consumer='evaluator-sample'; ANALYZE;"
        (root/'fixture.sql').write_text(ddl);sql(ddl)
        fixtures={}
        for count in (1000,10000):
            ids=[f'{i:08x}-1111-4111-8111-111111111111' for i in range(1,count+1)]
            queries=node(bridge,{'mode':'queries','config':c,'ids':ids,'batches':[ids[i:i+64] for i in range(0,count,64)]})
            for repeat in (1,2):
                decoded={}
                for mode, selected in [('old',queries['old']),('compact',[queries['new']])]:
                    start,cpu=time.monotonic(),time.process_time();rows=[];size=0
                    rawfile=root/f'{count}-{repeat}-{mode}.private.jsonl'
                    with rawfile.open('xb') as stream:
                        for query in selected:
                            raw=sql('BEGIN READ ONLY; SET LOCAL statement_timeout=50000;'+query+'ROLLBACK;').stdout
                            stream.write(raw);size+=len(raw)
                            rows.extend(json.loads(line) for line in raw.splitlines() if line)
                    snapshot=node(bridge,{'mode':mode,'config':c,'ids':ids,'rows':rows})
                    if 'refused' in snapshot:raise RuntimeError(snapshot['refused'])
                    decoded[mode]=snapshot
                    receipt['samples'].append({'tenants':count,'repeat':repeat,'mode':mode,'sqlQueries':len(selected),
                        'rawSqlBytes':size,'snapshotBytes':len(json.dumps(snapshot,separators=(',',':')).encode()),
                        'wallSeconds':time.monotonic()-start,'observerProcessCpuSeconds':time.process_time()-cpu,
                        'cpuScope':'Python observer only; excludes PostgreSQL, Docker and Node children',
                        'snapshotSha256':hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                        'legacy16MiBCapExceeded':size>16777216})
                    save()
                assert decoded['old']==decoded['compact']
                fixtures[count]=(ids,decoded['compact'])
            # Actual SQL mutations each roll back. Both strict readers must
            # refuse the same defect and restore to the exact original snapshot.
            controls={
                'missing-row':"DELETE FROM synthetic_clock.tenant_write_clock WHERE tenant_id='"+ids[0]+"';",
                'foreign-native-source':"UPDATE synthetic_checkpoint.tenant_consumer_checkpoint SET projection=jsonb_set(projection,'{0,stream,source_identity,system_id}','\"2\"'::jsonb) WHERE consumer='evaluator-sample';",
                'generation-changed':"UPDATE synthetic_checkpoint.tenant_consumer_checkpoint SET projection=jsonb_set(projection,'{0,stream,generation}','\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb:1\"'::jsonb) WHERE consumer='evaluator-sample';",
                'restore-changed':"UPDATE synthetic_control.tenant_lifecycle_windows SET generation=2;",
                'typed-contract':"UPDATE synthetic_checkpoint.tenant_consumer_checkpoint SET contract_digest=repeat('0',64) WHERE consumer='evaluator-sample-completed';",
                'missing-native-state':"UPDATE synthetic_checkpoint.tenant_consumer_checkpoint SET projection=jsonb_set(projection,'{0,stream}','null'::jsonb) WHERE consumer='evaluator-sample';",
            }
            one=[ids[0]]
            q=node(bridge,{'mode':'queries','config':c,'ids':one,'batches':[one]})
            for label,mutation in controls.items():
                codes=[]
                for mode,query in [('old',q['old'][0]),('compact',q['new'])]:
                    raw=sql('BEGIN;'+mutation+query+'ROLLBACK;').stdout
                    result=node(bridge,{'mode':mode,'config':c,'ids':one,'rows':[json.loads(line) for line in raw.splitlines() if line]})
                    assert 'refused' in result,(label,mode)
                    codes.append(result['refused'])
                assert codes[0]==codes[1],(label,codes)
                restored=sql('BEGIN READ ONLY;'+q['new']+'ROLLBACK;').stdout
                result=node(bridge,{'mode':'compact','config':c,'ids':one,'rows':[json.loads(line) for line in restored.splitlines() if line]})
                assert result['rows'][0]==fixtures[count][1]['rows'][0]
                receipt['controls'][f'{count}-{label}']={'refusal':codes[0],'restored':True};save()
        # Preserve the unchanged Python assessor as the final boundary.
        import sys
        sys.path.insert(0,str(M7))
        import evaluator_catchup
        for count,(ids,snapshot) in fixtures.items():
            result=evaluator_catchup.assess(snapshot,snapshot,snapshot,ids,c['binding'])
            assert result['verdict']=='PASS' and result['classifications']['COMPLETED']==count
            assert result['writerIntakeCoverage']['verdict']=='UNMEASURED'
            receipt['controls'][f'{count}-assessor']={'verdict':result['verdict'],'completed':count,'writerIntakeCoverage':result['writerIntakeCoverage']['verdict']}
        refused=sql('BEGIN READ ONLY; DELETE FROM synthetic_clock.tenant_write_clock; ROLLBACK;',check=False)
        assert refused.returncode!=0 and b'read-only transaction' in refused.stderr
        receipt['controls']['read-only']={'refused':True};receipt['status']='PASS'
    finally:
        if cid:
            run(['docker','rm','-f','-v',cid],timeout=25,check=False)
        remaining=run(['docker','ps','-aq','--no-trunc','--filter','label=ns.catchup.scale='+owner]).stdout.splitlines()
        receipt.update(cleanup='ABSENT' if not remaining else 'PRESENT',endedAt=time.time());save()
        if remaining:raise RuntimeError('OWNED_CLEANUP_FAILED')
    print(json.dumps({'status':receipt['status'],'cleanup':receipt['cleanup'],'receipt':str(root/'receipt.json')}))


if __name__=='__main__':main()
