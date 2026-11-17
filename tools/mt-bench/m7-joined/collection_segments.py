"""Finite file-only collector receipts. Never substitutes for a semantic verdict."""
import contextlib
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from contract import require


def code(error):
    value=str(error)
    return value if re.fullmatch(r'M7_[A-Z_]+',value) else 'M7_COLLECTION_SEGMENT_REFUSED'


def publish(path,value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf8') as stream:
            os.chmod(temporary,0o600);json.dump(value,stream,allow_nan=False);stream.write('\n')
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


class Segments:
    """One bounded receipt per snapshot invocation; successful files stay in place."""
    def __init__(self,out,name,owner):
        require(re.fullmatch(r'[a-z][a-z0-9-]{0,63}',name) is not None,'M7_COLLECTION_SEGMENT_NAME')
        self.out,self.path=Path(out),Path(out)/(name+'-collection.json')
        self.value={'version':1,'kind':'m7-collection-segments','owner':owner.get('owner'),
            'hostIdentity':owner.get('hostIdentity'),'pair':owner.get('pair'),
            'imageId':owner.get('imageId'),'instrument':owner.get('instrument',{}).get('sha256'),
            'collectorPid':os.getpid(),'clockDomain':'collector-process-monotonic-v1',
            'scope':'completed file segments; not clinical, HTTP or capacity success','segments':[]}
    @contextlib.contextmanager
    def capture(self,kind,files):
        require(len(self.value['segments'])<16 and re.fullmatch(r'[a-z][a-z0-9-]{0,63}',kind) is not None,'M7_COLLECTION_SEGMENT_BOUND')
        row={'kind':kind,'status':'STARTED','wallStartedAtNs':time.time_ns(),'monotonicStartedAtNs':time.monotonic_ns()}
        self.value['segments'].append(row);publish(self.path,self.value)
        try:
            yield
            row['status']='CAPTURED'
        except BaseException as error:
            row.update(status='FAILED',code=code(error),failureType=type(error).__name__);raise
        finally:
            row.update(wallFinishedAtNs=time.time_ns(),monotonicFinishedAtNs=time.monotonic_ns())
            row['files']={}
            for name in files:
                path=self.out/name
                if path.is_file():
                    digest=hashlib.sha256()
                    with path.open('rb') as source:
                        for chunk in iter(lambda:source.read(65536),b''):digest.update(chunk)
                    row['files'][name]={'bytes':path.stat().st_size,'sha256':digest.hexdigest()}
            try:publish(self.path,self.value)
            except Exception:
                if row['status']=='CAPTURED':raise


def preflight(directory,manifest):
    """Exercise the actual collector output context before starting its actors."""
    d=Path(directory)
    required=['owner.json','env','frozen.compose.json','probe.js','restart.cjs','k6/workload.js',
        'tenants.private.json','dependencies/package.json','dependencies/package-lock.json']
    required.extend(manifest.get('probe',{}).get('recoveryHelpers',{}))
    require(all((d/name).is_file() for name in required),'M7_COLLECTION_COMPANION_REQUIRED')
    try:
        config=json.loads((d/'frozen.compose.json').read_text())
        require(isinstance(config,dict) and isinstance(config.get('services'),dict) and bool(config['services']),'M7_COLLECTION_CONFIG_FORMAT')
        owner=json.loads((d/'owner.json').read_text())
        require(all(owner.get(k)==manifest.get(k) for k in ('owner','pair','instrument')),'M7_COLLECTION_OWNER_SOURCE_CHANGED')
        require((d/'dependencies/node_modules').is_dir(),'M7_COLLECTION_DEPENDENCIES_REQUIRED')
        require(type(manifest.get('tenants')) is int and 1<=manifest['tenants']<=10000,'M7_COLLECTION_ACTOR_BOUND')
        temporary=d/('.collector-write-'+uuid.uuid4().hex)
        try:
            with temporary.open('xb') as stream:stream.write(b'synthetic collector preflight\n')
        finally:temporary.unlink(missing_ok=True)
    except (ValueError,TypeError):raise RuntimeError('M7_COLLECTION_CONFIG_FORMAT') from None
    return {'status':'CHECKED','scope':'actual JSON fixture files and output write; existing source/dependency/runtime checks remain required','companions':len(set(required))}
