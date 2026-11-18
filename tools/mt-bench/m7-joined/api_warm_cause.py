"""Read a bounded same-tenant startup cause during an owned primer stage."""
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sys
import shutil
import time
import profile_provenance

from contract import OWNER, require

MODE = 'warm-v1'
STARTUP_MODE = 'startup-v1'
DEST = '/run/ns-api-warm'
OUT = '/run/ns-api-warm-out'
HELPERS = ('api-warm-cause-preload.cjs', 'api-cause.cjs')
SOURCE = 'lib/server/serve/tenant-startup.js'
BUILD = Path(__file__).resolve().parent
COMMAND = ['node','--require',f'{DEST}/{HELPERS[0]}','deploy/multitenant/entrypoint.js','api']
REFUSAL = {'error':'PRIMER_DATA_API_REFUSED_503','requestClass':'roles-ready','responseError':'TENANT_UNAVAILABLE'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def option(args):
    mode = getattr(args, 'api_warm_cause', 'off')
    if mode == 'off':
        return {}
    require(mode in (MODE,STARTUP_MODE) and args.profile == 'pgstream-sample' and args.run_purpose == 'discovery'
            and (args.tenants==10000 if mode==MODE else 1<=args.tenants<=10000) and args.replicas == 1
            and args.pgstream_topology == 'external-service-v1'
            and getattr(args,'api_cause_observation','off') == 'off'
            and getattr(args,'node_observation','off') == 'off', 'M7_API_WARM_SCOPE')
    return {'apiWarmCauseMode':mode}


def install(config, directory, manifest, mode):
    if mode == 'off':
        return
    d = Path(directory)
    helper = d / 'state/api-warm'
    helper.mkdir(mode=0o700)
    (d / 'state/api-warm-out').mkdir(mode=0o700)
    for name in HELPERS:
        (helper/name).write_bytes((BUILD/name).read_bytes())
    binding = {'owner':manifest['owner'], 'pair':manifest['pair'], 'sourceSha256':sha(d/'core'/SOURCE)}
    if mode==STARTUP_MODE:binding['startupObservation']=True
    (helper/'config.json').write_text(json.dumps(binding)+'\n')
    api = config['services']['api']
    require(api['command']==['node','deploy/multitenant/entrypoint.js','api']
            and not api.get('entrypoint') and not api.get('environment',{}).get('NODE_OPTIONS'),
            'M7_API_WARM_COMMAND')
    api['command'] = COMMAND
    api.setdefault('environment',{})['M7_API_WARM_CONFIG'] = DEST+'/config.json'
    api.setdefault('volumes',[]).extend([
        {'type':'bind','source':str(d/'state/api-warm'),'target':DEST,'read_only':True},
        # Compose's canonical JSON omits the default writable mode.
        {'type':'bind','source':str(d/'state/api-warm-out'),'target':OUT},
    ])
    manifest['apiWarmCause'] = {'mode':mode,'helpers':{name:sha(helper/name) for name in HELPERS},
                                'configSha256':sha(helper/'config.json'), 'binding':binding}
    verify(config,d,manifest)


def verify(config,d,manifest):
    record = manifest.get('apiWarmCause')
    observed = set()
    for role, spec in config['services'].items():
        if DEST+'/'+HELPERS[0] in (spec.get('command') or []) or (
                'M7_API_WARM_CONFIG' in (spec.get('environment') or {})) or any(
                    v.get('target') in (DEST, OUT) for v in spec.get('volumes',[])):
            observed.add(role)
    if not record:
        require(not observed,'M7_API_WARM_UNBOUND')
        return
    require(not manifest.get('attached') and manifest['profile']=='pgstream-sample'
            and manifest['runPurpose']=='discovery'
            and (manifest['tenants']==10000 if record['mode']==MODE else 1<=manifest['tenants']<=10000)
            and record['mode'] in (MODE,STARTUP_MODE) and observed=={'api'},'M7_API_WARM_SCOPE')
    spec = config['services']['api']
    require(spec.get('command')==COMMAND and not spec.get('entrypoint')
            and not spec.get('environment',{}).get('NODE_OPTIONS')
            and spec['environment'].get('M7_API_WARM_CONFIG')==DEST+'/config.json','M7_API_WARM_COMMAND')
    for subdir, target, read_only in (('api-warm',DEST,True),('api-warm-out',OUT,False)):
        mounts = [v for v in spec.get('volumes',[]) if v.get('target')==target]
        require(len(mounts)==1 and mounts[0].get('type')=='bind'
                and mounts[0].get('source')==str(d/'state'/subdir)
                and mounts[0].get('read_only',False) is read_only
                and ('read_only' in mounts[0]) is read_only, 'M7_API_WARM_MOUNT')
    helper = d/'state/api-warm'
    configuration = helper/'config.json'
    require(set(record['helpers'])==set(HELPERS) and
            all(record['helpers'][name]==sha(helper/name)==sha(BUILD/name) for name in HELPERS)
            and sha(configuration)==record['configSha256'],'M7_API_WARM_HELPER')
    require(json.loads(configuration.read_text())==record['binding']=={
        'owner':manifest['owner'],'pair':manifest['pair'],'sourceSha256':sha(d/'core'/SOURCE),
        **({'startupObservation':True} if record['mode']==STARTUP_MODE else {})},
        'M7_API_WARM_BINDING')


def api_birth(a, manifest):
    rows = [row for row in a.resources(manifest, all_containers=False)
            if row['Config']['Labels'].get('com.docker.compose.service')=='api']
    require(len(rows)==1,'M7_API_WARM_RUNTIME')
    row, = rows
    require(row['Config']['Labels'].get(OWNER)==manifest['owner'] and row['Image']==manifest['imageId']
            and row['Config']['Cmd']==COMMAND and row['State']['Running'],'M7_API_WARM_RUNTIME')
    return {'id':row['Id'],'startedAt':row['State']['StartedAt'],'pid':row['State']['Pid']}


def exact_refusal(path):
    if not path.is_file():
        return False
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-8192))
        for line in stream.read(8192).splitlines():
            try: value = json.loads(line)
            except (ValueError, UnicodeError): continue
            if value==REFUSAL:
                return True
    return False


def assess(value, binding, start, end):
    require(all(value.get(k)==v for k,v in binding.items()) and type(value['pid']) is int
            and value['pid']>0, 'M7_API_WARM_FOREIGN')
    events = value['events']
    require(1<=len(events)<=32 and value['overflow'] is False,'M7_API_WARM_COVERAGE')
    for row in events:
        require(set(row)=={'atMs','responseAtMs','status','healthCause','initializerCause','overflow'}
                and all(type(row[k]) is int for k in ('atMs','responseAtMs','status'))
                and start<=row['atMs']<=row['responseAtMs']<=end and row['status']==503
                and row['overflow'] is False
                and all(re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',row[k])
                        for k in ('healthCause','initializerCause')),'M7_API_WARM_EVENT')
    causes = Counter((row['healthCause'],row['initializerCause']) for row in events)
    status = 'MEASURED' if len(causes)==1 and any(code not in ('UNMEASURED','UNCLASSIFIED','TENANT_WARM_FAILED')
              for code in next(iter(causes))) else 'PARTIAL'
    return {'status':status,'observedResponses':len(events),
            'causes':[{'healthCause':k[0],'initializerCause':k[1],'responses':n}
                      for k,n in sorted(causes.items())],
            'correlation': 'same-stage and same classified cause on every matching API response'
                if len(causes)==1 else 'same-stage responses have different causes; terminal primer response ambiguous'}


@contextmanager
def observe(a,d,manifest):
    record = manifest.get('apiWarmCause')
    if not record:
        yield
        return
    folder = d/'state/api-warm-out'
    birth = api_birth(a,manifest)
    start = int(time.time()*1000)
    with (folder/'prime-stage.json').open('x') as signal:
        json.dump({'owner':manifest['owner'],'fromMs':start},signal)
    try:
        yield
    finally:
        primary = sys.exc_info()[1]
        end = int(time.time()*1000)
        result = {'status':'UNMEASURED','code':'M7_API_WARM_PRIMER_REFUSAL_NOT_OBSERVED',
                  'pair':manifest['pair'],'imageId':manifest['imageId'],
                  'instrument':manifest['instrument']['sha256'],'beforeCleanup':True,
                  'stageStartMs':start,'stageEndMs':end,'runtime':birth,
                  'primerExitedWithError':primary is not None}
        try:
            if exact_refusal(d/'prime.log'):
                result['primerRefusal'] = REFUSAL
                require(api_birth(a,manifest)==birth,'M7_API_WARM_RUNTIME_CHANGED')
                capture = folder/'captures.json'
                require(capture.is_file() and not capture.is_symlink() and
                        0<capture.stat().st_size<=16384,'M7_API_WARM_FILE')
                outcome = assess(json.loads(capture.read_text()),record['binding'],start,end)
                result.update(outcome,captureSha256=sha(capture),code='M7_API_WARM_CORRELATED')
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            code = str(error)
            result['code'] = code if re.fullmatch(r'M7_[A-Z_]+',code) else 'M7_API_WARM_CAPTURE'
        if record['mode']==STARTUP_MODE:
            try:collect_startup(a,d,manifest,birth,start,end,primary is not None)
            except Exception:result['startupCaptureCode']='M7_STARTUP_CAPTURE_WRITE_FAILED'
        with (d/'api-warm-cause.json').open('x') as out:
            json.dump(result,out,indent=2)
            out.write('\n')


def collect_startup(a,d,manifest,birth,start,end,failed):
    """A bounded pre-cleanup bookend; never changes the primer's verdict."""
    value={'status':'UNMEASURED','beforeCleanup':True,'stageStartMs':start,'stageEndMs':end,
           'primerFailed':failed,'pair':manifest['pair'],'instrument':manifest['instrument']['sha256'],
           'runtime':birth,'scope':'API startup and primer; no clinical recovery or steady-load verdict'}
    try:
        rows=[row for row in a.resources(manifest) if row['Id']==birth['id']]
        require(len(rows)==1 and rows[0]['State']['StartedAt']==birth['startedAt']
                and rows[0]['Config']['Labels'].get(OWNER)==manifest['owner']
                and rows[0]['Image']==manifest['imageId'],'M7_API_WARM_RUNTIME_CHANGED')
        row,=rows
        value['process']={k:row['State'].get(k) for k in ('Running','ExitCode','OOMKilled','StartedAt','FinishedAt')}
        value['containerMemoryLimitBytes']=row.get('HostConfig',{}).get('Memory')
        health=row['State'].get('Health',{})
        value['containerHealth']={k:health.get(k) for k in ('Status','FailingStreak')}
        if failed:
            logs=profile_provenance.capture_logs(d/'startup-role-logs',{'services':{'api':{}}},
                lambda role:['docker','logs','--timestamps','--tail','100',birth['id']],seconds=2,per_role=16384,total=16384)
            a.write(d/'startup-role-logs/manifest.json',logs)
            value['failureLogManifestSha256']=sha(d/'startup-role-logs/manifest.json')
        capture=d/'state/api-warm-out/startup-samples.json'
        require(capture.is_file() and not capture.is_symlink() and 0<capture.stat().st_size<=262144,'M7_STARTUP_SAMPLES_REQUIRED')
        data=json.loads(capture.read_text())
        require(all(data.get(k)==v for k,v in manifest['apiWarmCause']['binding'].items())
                and type(data.get('pid')) is int and data['pid']>0,'M7_STARTUP_SAMPLES_FOREIGN')
        require(type(data.get('sampleCount')) is int and data['sampleCount']>0 and 1<=len(data['samples'])<=64,'M7_STARTUP_SAMPLES_BOUND')
        for sample in data['samples']:
            require(type(sample.get('atMs')) is int and sample['atMs']<=end and sample['atMs']>=start-3600000
                    and all(type(sample.get(k)) is int and sample[k]>0 for k in ('heapUsed','rss','heapSizeLimit')),
                    'M7_STARTUP_SAMPLES_INVALID')
        require(start-2000<=data['samples'][-1]['atMs']<=end and end-data['samples'][-1]['atMs']<=10000,
                'M7_STARTUP_SAMPLES_STALE')
        retained=d/'startup-samples.private.json'
        if retained.exists():require(retained.read_bytes()==capture.read_bytes(),'M7_STARTUP_CAPTURE_EXISTS')
        else:shutil.copyfile(capture,retained);retained.chmod(0o600)
        value.update(status='CAPTURED',samplesSha256=sha(retained),samplesFile=retained.name,sampleCount=data['sampleCount'],
                     first=data['first'],last=data['samples'][-1])
    except (RuntimeError,OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        code=str(error)
        value['code']=code if re.fullmatch(r'M7_[A-Z_]+',code) else 'M7_STARTUP_CAPTURE_FAILED'
    events=[]
    log=d/'prime.log'
    if log.is_file():
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-16384))
            for line in stream.read(16384).splitlines():
                try:event=json.loads(line)
                except (ValueError,UnicodeError):continue
                if type(event) is not dict:continue
                if event.get('phase')=='primer' and event.get('event') in ('first-useful-response','completed'):
                    events.append({k:event[k] for k in ('phase','event','requestClass','status','atMs','tenants') if k in event})
                elif re.fullmatch(r'PRIMER_[A-Z0-9_]+',str(event.get('error',''))):
                    value['primerFailure']={k:event[k] for k in ('error','requestClass','connectionCause','responseError')
                        if isinstance(event.get(k),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',event[k])}
    value['primerEvents']=events[:2]
    a.write(d/'startup-primer-boundary.json',value)
