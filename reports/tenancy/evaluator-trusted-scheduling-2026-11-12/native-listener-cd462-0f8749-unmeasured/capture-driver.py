"""Read-only native qualification driver; no stack ownership or lifecycle calls."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,'<alignment>/externals/work/alignment-m7-evaluator-progress-20261112/tools/mt-bench/m7-joined')
import evaluator_progress as p
HERE=Path(__file__).parent
HELPER=Path(p.__file__).with_name('evaluator-progress.cjs')

def save(path,value):
    path.write_bytes(json.dumps(value,separators=(',',':')).encode()+b'\n');path.chmod(0o600)

def inspect(spec):
    result={}
    for service,expected in spec['containers'].items():
        raw=subprocess.check_output(['docker','inspect','--format','{{json .Id}} {{json .Image}} {{json .State.StartedAt}} {{json .State.Running}} {{json .Config.Labels}}',expected['id']],timeout=10,text=True)
        decoder=json.JSONDecoder();values=[]
        while raw.strip():
            raw=raw.lstrip();value,end=decoder.raw_decode(raw);values.append(value);raw=raw[end:]
        cid,image,started,running,labels=values
        p.need(cid==expected['id'] and image==spec['imageId'] and started==expected['startedAt'] and running is True,'NATIVE_PROGRESS_CONTAINER_IDENTITY','FAIL')
        p.need(labels.get('com.docker.compose.project')==spec['project'] and labels.get('com.docker.compose.service')==service,'NATIVE_PROGRESS_INSTANCE_IDENTITY','FAIL')
        result[service]={'id':cid,'imageId':image,'startedAt':started,'project':spec['project'],'service':service}
    return result

def main(spec):
    p.need(spec['source']=='cd4629159809fb3cffbc6f57626f98f3ffdbdda7' and spec['binding']=='0f8749bc954812b9d384528da733680930e3b236','NATIVE_PROGRESS_SOURCE','FAIL')
    p.need(len(spec['containers'])==3 and spec['secondsBetween']==10,'NATIVE_PROGRESS_BOUND')
    services=sorted(spec['containers']);ids=sorted(spec['ids']);p.validate_ids(ids)
    p.need(len(ids)==2,'NATIVE_PROGRESS_BOUND')
    labels=json.loads(subprocess.check_output(['docker','image','inspect','--format','{{json .Config.Labels}}',spec['imageId']],text=True,timeout=10))
    p.need(labels.get('org.opencontainers.image.revision')==spec['source'] and labels.get('org.nightscout.deploy.revision')==spec['binding'],'NATIVE_PROGRESS_IMAGE_PAIR','FAIL')
    imagePair={k:labels[k] for k in ('org.opencontainers.image.revision','org.nightscout.deploy.revision')}
    before=inspect(spec);rounds=[];active=[0]
    def fetch(service,selected,queries,budget):
        prefix='const M7_PROGRESS_IDS='+json.dumps(selected)+';const M7_PROGRESS_QUERY_BUDGET='+str(queries)+';const M7_PROGRESS_BYTE_BUDGET='+str(budget)+';\n'
        started=time.monotonic()
        result=subprocess.run(['docker',*spec['composeArgs'],'exec','-T',service,'node','-'],input=(prefix+HELPER.read_text()).encode(),capture_output=True,timeout=20)
        raw=HERE/(str(active[0])+'-'+service+'.private.jsonl');raw.write_bytes(result.stdout);raw.chmod(0o600)
        save(HERE/(str(active[0])+'-'+service+'.command.json'),{'returncode':result.returncode,'bytes':len(result.stdout),'wallSeconds':time.monotonic()-started,'stderrSha256':hashlib.sha256(result.stderr).hexdigest()})
        p.need(result.returncode==0,'NATIVE_PROGRESS_COLLECTOR_UNAVAILABLE');return result.stdout
    started=time.monotonic();error=None
    try:
        for index in range(3):
            if index:time.sleep(10)
            active[0]=index;rounds.append(p.round_view(services,ids,fetch))
        result=p.assess(rounds,ids,'idle')
    except Exception as caught:
        error=caught;result={'verdict':getattr(caught,'verdict','UNMEASURED'),'code':str(caught)}
    after=inspect(spec);p.need(before==after,'NATIVE_PROGRESS_REPLACED','FAIL')
    packed=p.pack({**result,'rounds':rounds})
    if error is None:
        p.need(p.verify(packed,len(ids),services,'idle')==result,'NATIVE_PROGRESS_RECOMPUTATION','FAIL')
    evidence={'kind':'native-bounded-evaluator-listener-qualification','source':spec['source'],'binding':spec['binding'],'imageId':spec['imageId'],'containers':before,'imagePair':imagePair,'helperSha256':hashlib.sha256(HELPER.read_bytes()).hexdigest(),'secondsBetween':10,'elapsedSeconds':time.monotonic()-started,'scope':'short read-only native smoke, not pilot/capacity/restart/clinical acceptance','result':result,'proof':packed}
    save(HERE/'observation.private.json',evidence)
    file=HERE/'observation.private.json.gz';file.write_bytes(gzip.compress((HERE/'observation.private.json').read_bytes(),mtime=0));file.chmod(0o600)
    print(json.dumps({k:v for k,v in evidence.items() if k not in ('proof','containers')}))
    if error is not None:raise error

if __name__=='__main__':main(json.loads(Path(sys.argv[1]).read_text()))
