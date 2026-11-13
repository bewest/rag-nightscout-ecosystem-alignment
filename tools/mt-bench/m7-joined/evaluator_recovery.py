"""Bounded, read-only post-restart owned-window acquisition observation."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import evaluator_progress as p


def assess(baseline, rounds, ids,*,policy=p.POLICY):
    p.need(len(rounds)==2,'M7_EVALUATOR_RECOVERY_NOT_OBSERVED')
    first,last=rounds
    p.need(set(first['instances'])==set(baseline['instances']),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    p.need(all(first['instances'][s]['ordinal']==baseline['instances'][s]['ordinal'] for s in first['instances']),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    p.need(all(first['instances'][s]['runtimeId']!=baseline['instances'][s]['runtimeId'] for s in first['instances']),'M7_EVALUATOR_RECOVERY_OLD_RUNTIME','FAIL')
    # Reuse the exact stability, coverage, hidden-error and foreign-work checks.
    # A recovery witness requires acquisition in the new runtime; it does not
    # require time progression or a new acquisition between sparse samples.
    p.need(first['instances']==last['instances'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
    for tenant in ids:
        a,b=first['owners'][tenant],last['owners'][tenant]
        p.need((a['service'],a['generation'])==(b['service'],b['generation']),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
        p.need(a['failedCompletions']==b['failedCompletions']==0,'M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE','FAIL')
        p.need(a['completedAcquisitions']>0 and b['completedAcquisitions']>=a['completedAcquisitions'] and b['completedTimeCycles']>=a['completedTimeCycles'],'M7_EVALUATOR_RECOVERY_NOT_OBSERVED')
    for service,rows in first['allRows'].items():
        for tenant,a in rows.items():
            b=last['allRows'][service][tenant]
            p.need((a['admitted'],a['generation'])==(b['admitted'],b['generation']),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            if not a['admitted']:
                p.need(all(a[k]==b[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
    return {'version':policy['version'],'verdict':'PASS','observed':len(ids),'expected':len(ids),'missing':0,'instances':last['instances'],'source':'successful fresh owned acquisition in changed runtime, stable exact-instance coverage; no clinical-equivalence or deadline claim'}



def verify(value,tenants,services):
    legacy=value.get('kind')=='evaluator-recovery-v1';policy=p.LEGACY_POLICY if legacy else p.POLICY
    columns=p.LEGACY_COLUMNS if legacy else p.COLUMNS
    p.need(value.get('kind')==('evaluator-recovery-v1' if legacy else 'evaluator-recovery-v2') and value.get('policy')==policy and value.get('columns')==list(columns),'M7_EVALUATOR_RECOVERY_PROOF')
    baseline,ids=p.decode_rounds({'rounds':value.get('baseline'),'columns':value.get('columns')},tenants,services)
    rounds,other=p.decode_rounds({'rounds':value.get('rounds'),'columns':value.get('columns')},tenants,services)
    p.need(len(baseline)==1 and ids==other,'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    result=assess(baseline[0],rounds,sorted(ids),policy=policy);recorded=value.get('result',{})
    p.need({k:v for k,v in recorded.items() if k!='sampling'}==result,'M7_EVALUATOR_RECOVERY_ASSESSMENT')
    sample=recorded.get('sampling',{})
    p.need(sample.get('cadenceMs')==15000 and p.integer(sample.get('queries'),1) and sample['queries']<=p.POLICY['readinessMaxQueries'] and p.integer(sample.get('bytes'),1) and sample['bytes']<=p.POLICY['readinessMaxBytes'],'M7_EVALUATOR_RECOVERY_BUDGET')
    p.need(isinstance(value.get('errors'),list) and len(value['errors'])<=60 and all(e.get('verdict')=='UNMEASURED' for e in value['errors']),'M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE','FAIL')
    p.need(all(type(sample.get(k)) in (int,float) and math.isfinite(sample[k]) and sample[k]>=0 for k in ('wallSeconds','elapsedSeconds')),'M7_EVALUATOR_RECOVERY_OVERHEAD')
    p.need(sample['queries']>=sum(r['queries'] for r in rounds) and sample['bytes']>=sum(r['bytes'] for r in rounds),'M7_EVALUATOR_RECOVERY_OVERHEAD')
    p.need(sample.get('failures')==len(value['errors']),'M7_EVALUATOR_RECOVERY_ASSESSMENT')
    return recorded

def main(spec):
    ids=spec['ids'];p.validate_ids(ids);services=spec['services']
    helper=Path(__file__).with_name('evaluator-progress.cjs').read_text()
    def fetch(service,selected,queries,budget):
        prefix='const M7_PROGRESS_IDS='+json.dumps(selected)+';const M7_PROGRESS_QUERY_BUDGET='+str(queries)+';const M7_PROGRESS_BYTE_BUDGET='+str(budget)+';\n'
        result=subprocess.run(['docker',*spec['composeArgs'],'exec','-T',service,'node','-'],input=(prefix+helper).encode(),capture_output=True,timeout=20)
        p.need(result.returncode==0,'M7_EVALUATOR_PROGRESS_UNAVAILABLE');return result.stdout
    path=Path(spec['path']);path.parent.mkdir(parents=True,exist_ok=True)
    if spec['mode']=='baseline':
        value=p.round_view(services,ids,fetch);path.write_text(json.dumps(value,separators=(',',':')));os.chmod(path,0o600)
        return {'version':p.POLICY['version'],'instances':value['instances'],'queries':value['queries'],'bytes':value['bytes'],'wallSeconds':value['wallSeconds']}
    baseline=json.loads(Path(spec['baseline']).read_text());rounds=[];errors=[];queries=0;bytes_seen=0;wall=0;result=None;started=time.monotonic()
    try:
        for attempt in range(60):
            if time.time()*1000>=spec['deadlineMs']:break
            try:
                value=p.round_view(services,ids,fetch,warming=True)
                rounds=(rounds+[value])[-2:];queries+=value['queries'];bytes_seen+=value['bytes'];wall+=value['wallSeconds']
                p.need(queries<=p.POLICY['readinessMaxQueries'] and bytes_seen<=p.POLICY['readinessMaxBytes'],'M7_EVALUATOR_RECOVERY_BUDGET')
                if len(rounds)==2:
                    result=assess(baseline,rounds,ids);break
            except p.Refused as error:
                errors.append({'code':str(error),'verdict':error.verdict,'collection':getattr(error,'collection',None)})
                if getattr(error,'collection',None):
                    queries+=error.collection['queries'];bytes_seen+=error.collection['bytes'];wall+=error.collection['wallSeconds']
                if error.verdict=='FAIL':raise
                p.need(queries<=p.POLICY['readinessMaxQueries'] and bytes_seen<=p.POLICY['readinessMaxBytes'],'M7_EVALUATOR_RECOVERY_BUDGET')
            remaining=spec['deadlineMs']/1000-time.time()
            if remaining>0:time.sleep(min(15,remaining))
        p.need(result is not None,'M7_EVALUATOR_RECOVERY_NOT_OBSERVED')
    except Exception as error:
        result={'version':p.POLICY['version'],'verdict':getattr(error,'verdict','UNMEASURED'),'code':str(error),'observed':0,'expected':len(ids),'missing':len(ids)}
    result['sampling']={'cadenceMs':15000,'queries':queries,'bytes':bytes_seen,'wallSeconds':wall,'elapsedSeconds':time.monotonic()-started,'failures':len(errors)}
    evidence={'kind':'evaluator-recovery-v2','attribution':spec['attribution'],'policy':p.POLICY,'columns':list(p.COLUMNS),'result':dict(result),'errors':errors,'baseline':p.pack({'rounds':[baseline]})['rounds'],'rounds':p.pack({'rounds':rounds})['rounds']}
    publishing=time.monotonic();cpu=time.process_time()
    raw=json.dumps(evidence,separators=(',',':')).encode();p.need(len(raw)<=16777216,'M7_EVALUATOR_RECOVERY_ARTIFACT_BOUND')
    path.write_bytes(raw);os.chmod(path,0o600);compressed=gzip.compress(raw,mtime=0);Path(str(path)+'.gz').write_bytes(compressed);os.chmod(str(path)+'.gz',0o600)
    cost=Path(str(path)+'.publication.json');cost.write_text(json.dumps({'wallSeconds':time.monotonic()-publishing,'processCpuSeconds':time.process_time()-cpu,'rawBytes':len(raw),'gzipBytes':len(compressed),'scope':'serialization, gzip and primary-file writes; sidecar publication excluded'}));os.chmod(cost,0o600)
    result['evidence']={'rawSha256':hashlib.sha256(raw).hexdigest(),'gzipSha256':hashlib.sha256(compressed).hexdigest()}
    return result

if __name__=='__main__':
    try:print(json.dumps(main(json.load(sys.stdin)),separators=(',',':')))
    except Exception as error:
        print(json.dumps({'version':p.POLICY['version'],'verdict':getattr(error,'verdict','UNMEASURED'),'code':str(error),'missing':None}));sys.exit(1)
