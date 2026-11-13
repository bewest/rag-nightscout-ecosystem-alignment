"""Read-only native qualification driver; no stack ownership or lifecycle calls."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,'<alignment>/externals/work/alignment-d6-decisions-20261111/tools/mt-bench/m7-joined')
import evaluator_progress as p
FINAL_ROOT=Path('<alignment>/externals/work/alignment-d6-decisions-20261111')
INSTRUMENT_COMMIT='4ddea55301c3d1f95faf25e15a80051bbb122e8b'
INSTRUMENT_SHA='157d7038c3b5a196e95c766b5777e6686bd1d59a37e3e5772ede4eea2daf6970'
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
    manifest=json.loads((HERE/'instrument-manifest.json').read_text())
    p.need(manifest['commit']==INSTRUMENT_COMMIT and manifest['sha256']==INSTRUMENT_SHA and len(manifest['files'])==35,'NATIVE_FINAL_INSTRUMENT_PIN','FAIL')
    p.need(subprocess.check_output(['git','-C',str(FINAL_ROOT),'rev-parse','HEAD'],text=True).strip()==INSTRUMENT_COMMIT,'NATIVE_FINAL_INSTRUMENT_HEAD','FAIL')
    p.need(all(hashlib.sha256((FINAL_ROOT/name).read_bytes()).hexdigest()==sha for name,sha in manifest['files'].items()),'NATIVE_FINAL_INSTRUMENT_BYTES','FAIL')
    p.need(hashlib.sha256(Path(spec['ownedPairFile']).read_bytes()).hexdigest()==spec['ownedPairSha256'] and p.UUID.fullmatch(spec['nonce']),'NATIVE_FRESH_NONCE_PIN','FAIL')
    p.need(spec['source']=='47b43b6246ce7f94f1f1f0d01830495a78b28add' and spec['binding']=='be95214a6cae427e1898b0ca6ce39825163ee291','NATIVE_PROGRESS_SOURCE','FAIL')
    p.need(len(spec['containers'])==3 and spec['secondsBetween']==10,'NATIVE_PROGRESS_BOUND')
    services=sorted(spec['containers']);ids=sorted(spec['ids']);p.validate_ids(ids)
    p.need(len(ids)==2,'NATIVE_PROGRESS_BOUND')
    labels=json.loads(subprocess.check_output(['docker','image','inspect','--format','{{json .Config.Labels}}',spec['imageId']],text=True,timeout=10))
    p.need(labels.get('org.opencontainers.image.revision')==spec['source'] and labels.get('org.nightscout.deploy.revision')==spec['binding'],'NATIVE_PROGRESS_IMAGE_PAIR','FAIL')
    imagePair={k:labels[k] for k in ('org.opencontainers.image.revision','org.nightscout.deploy.revision')}
    before=inspect(spec);rounds=[];active=[0];sample_windows={}
    def fetch(service,selected,queries,budget):
        prefix='const M7_PROGRESS_IDS='+json.dumps(selected)+';const M7_PROGRESS_QUERY_BUDGET='+str(queries)+';const M7_PROGRESS_BYTE_BUDGET='+str(budget)+';\n'
        started=time.monotonic();read_started=time.time_ns()//1000000
        result=subprocess.run(['docker',*spec['composeArgs'],'exec','-T',service,'node','-'],input=(prefix+HELPER.read_text()).encode(),capture_output=True,timeout=20)
        read_ended=time.time_ns()//1000000
        sample_windows[service]={'readStartedAtMs':read_started,'readEndedAtMs':read_ended,'helperObservedAtMs':[json.loads(line).get('observedAt') for line in result.stdout.splitlines()]}
        raw=HERE/(str(active[0])+'-'+service+'.private.jsonl');raw.write_bytes(result.stdout);raw.chmod(0o600)
        save(HERE/(str(active[0])+'-'+service+'.command.json'),{**sample_windows[service],'returncode':result.returncode,'bytes':len(result.stdout),'wallSeconds':time.monotonic()-started,'stderrSha256':hashlib.sha256(result.stderr).hexdigest()})
        p.need(result.returncode==0,'NATIVE_PROGRESS_COLLECTOR_UNAVAILABLE');return result.stdout
    started=time.monotonic();error=None
    try:
        for index in range(3):
            if index:time.sleep(10)
            active[0]=index;sample_windows.clear();round_started=time.time_ns()//1000000;view=p.round_view(services,ids,fetch);view.update(readStartedAtMs=round_started,readEndedAtMs=time.time_ns()//1000000,sampleWindows=dict(sample_windows));rounds.append(view)
        result=p.assess(rounds,ids,'idle')
    except Exception as caught:
        error=caught;result={'verdict':getattr(caught,'verdict','UNMEASURED'),'code':str(caught)}
    after=inspect(spec);p.need(before==after,'NATIVE_PROGRESS_REPLACED','FAIL')
    packed=p.pack({'version':p.POLICY['version'],'phase':'idle','policy':p.POLICY,**result,'rounds':rounds})
    if error is None:
        p.need(p.verify(packed,len(ids),services,'idle')==result,'NATIVE_PROGRESS_RECOMPUTATION','FAIL')
    evidence={'kind':'native-bounded-evaluator-due-listener-qualification','instrumentCommit':INSTRUMENT_COMMIT,'instrumentSha256':INSTRUMENT_SHA,'nonce':spec['nonce'],'ownedPairSha256':spec['ownedPairSha256'],'source':spec['source'],'binding':spec['binding'],'imageId':spec['imageId'],'containers':before,'imagePair':imagePair,'helperSha256':hashlib.sha256(HELPER.read_bytes()).hexdigest(),'secondsBetween':10,'elapsedSeconds':time.monotonic()-started,'scope':'short read-only native smoke, not pilot/capacity/restart/clinical acceptance','result':result,'proof':packed}
    save(HERE/'observation.private.json',evidence)
    file=HERE/'observation.private.json.gz';file.write_bytes(gzip.compress((HERE/'observation.private.json').read_bytes(),mtime=0));file.chmod(0o600)
    print(json.dumps({k:v for k,v in evidence.items() if k not in ('proof','containers')}))
    if error is not None:raise error

if __name__=='__main__':main(json.loads(Path(sys.argv[1]).read_text()))
