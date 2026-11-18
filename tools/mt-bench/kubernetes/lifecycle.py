"""Execute an admitted instance; exact UID cleanup and first failure are retained.

Adapted from the retained staging controller; all local custody is explicit JSON.
"""
import base64, datetime as dt, hashlib, json, os, subprocess, sys, time, traceback
import signal
from pathlib import Path
from lifecycle_config import fixture_config
import frozen
import primer_storage
import producer_startup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "m7-joined"))
from auto_catalog import auto_catalog
cfg=fixture_config(Path(sys.argv[1]))
d=Path(cfg['caseDirectory']); inst=Path(cfg['instrumentDirectory']); tool=Path(cfg['toolsDirectory'])
read=lambda p:json.loads(p.read_bytes())
os.umask(0o077);sys.dont_write_bytecode=True
e=read(d/'environment.json'); ns=e['namespace'];ctx=e['context'];rid=e['runId']
assert e['runId']==d.name and ns.startswith('ns-synth-'),'INSTANCE_IDENTITY_CHANGED'
live=d/'runtime';live.mkdir(mode=0o700,exist_ok=True);assert not any(live.iterdir()),'ENTERED_OUTPUT_EXISTS'
def put(n,obj):(live/n).write_text(json.dumps(obj,indent=2)+'\n')
def timestamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def command(argv,data=None,timeout=18,private=False):
    rem=cleanup-time.time() if cleaning else work-time.time()
    assert rem>0,'CUTOFF'
    q=subprocess.run([str(x) for x in argv],input=data,capture_output=True,timeout=min(timeout,rem),env=env)
    if q.returncode:
        import re
        codes=sorted(set(re.findall(rb'\b(?:K8S_|M7_|PRIMER_|BOOTSTRAP_|PLATFORM_|VAULT_|EVALUATOR_)[A-Z0-9_]{2,90}\b',q.stderr+q.stdout)))
        put('last-command-error.json',{'program':Path(str(argv[0])).name,'returncode':q.returncode,'codes':[x.decode() for x in codes]})
        raise RuntimeError('PRIVATE_STEP_FAILED' if private else 'STAGE_COMMAND_FAILED')
    return q.stdout
env={**os.environ,'PATH':str(tool)+':'+os.environ['PATH'],'TMPDIR':str(live),'NS_KUBE_CONTEXT':ctx,'NS_RUN_ID':rid,'RO_NO_LOG':'1','PYTHONDONTWRITEBYTECODE':'1'}
rpc=[tool/'kubectl','--context',ctx,'--request-timeout=14s']
start=time.time();work=start+e['workDeadlineSeconds'];cleanup=start+e['cleanupDeadlineSeconds'];cleaning=False
def k(args,body=None,private=False):return command(rpc+args,json.dumps(body).encode() if body else None,private=private)
def get(kind,name,local=True):
    b=k(['get',kind,name,*(['-n',ns] if local else []),'--ignore-not-found','-o','json'])
    return json.loads(b) if b.strip() else None
def create(obj):
    return json.loads(k(['create','-f','-','-o','json'],obj))
def deluid(path,uid):
    k(['delete','--raw',path,'-f','-'],{'apiVersion':'v1','kind':'DeleteOptions','propagationPolicy':'Foreground','preconditions':{'uid':uid}})
def absent(kind,name,local):
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        if get(kind,name,local) is None:return
        time.sleep(2)
    raise RuntimeError('ABSENCE_UNCONFIRMED_'+kind)
def owned():
    cur=get('namespace',ns,False)
    assert cur and cur['metadata']['uid']==nsuid and cur['metadata']['labels']['nightscout.org/run-id']==rid
def objects(stage):return read(d/'stages'/f'{stage}.json')['items']
def step(stage):
    global current
    current=stage
    events.append({'stage':stage,'time':timestamp()});put('stages.json',events)
def install(stage):
    step(stage);owned()
    for obj in objects(stage):
        assert obj['metadata']['namespace']==ns
        made=create(obj)
        uids.append({'kind':made['kind'],'name':made['metadata']['name'],'uid':made['metadata']['uid']})
        put('created.json',uids)
def pods(label):
    return json.loads(k(['get','pods','-n',ns,'-l',label,'-o','json']))['items']
def summary(pod):
    sts=pod.get('status',{})
    return {'name':pod['metadata']['name'],'uid':pod['metadata']['uid'],'node':pod['spec'].get('nodeName'),'phase':sts.get('phase'),
            'resources':[{k:v.get(k) for k in ('name','resources')} for v in pod['spec'].get('initContainers',[])+pod['spec'].get('containers',[])],
            'containers':[{k:c.get(k) for k in ('name','imageID','restartCount','ready')}|{'state':c.get('state',{}),'previousTermination':c.get('lastState',{}).get('terminated')} for c in sts.get('initContainerStatuses',[])+sts.get('containerStatuses',[])]}
def failure_codes(pod,container,uid,previous=False):
    owned()
    require_pod_uid(pod,uid)
    args=['logs',pod,'-n',ns,'-c',container,'--tail=60']
    if previous:args.append('--previous')
    try:
        output=command(rpc+args,private=True)
        observed={'status':'CAPTURED','codes':producer_startup.log_codes(output)}
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        observed={'status':'UNMEASURED','codes':[]}
    require_pod_uid(pod,uid)
    return observed

def require_pod_uid(name,uid):
    row=get('pod',name)
    if row is None or row['metadata']['uid']!=uid:
        raise RuntimeError('POD_OWNERSHIP_CHANGED')

def ready(label,typ,timeout,convergence=None):
    step('wait-'+typ)
    until=min(time.time()+timeout,work)
    stable=producer_startup.StableReady(convergence['stableReadySeconds'] if convergence else 0)
    failures={}
    while time.time()<until:
        owned()
        found=pods(label)
        if any(x['metadata']['labels'].get('nightscout.org/run-id')!=rid for x in found):raise RuntimeError('FOREIGN_POD')
        ready_pod=None
        identity=None
        for pod in found:
            s=summary(pod);put('latest-'+typ+'.json',s)
            for v in s['containers']:
                disposition=producer_startup.disposition(v,convergence)
                if disposition is None:
                    continue
                key=(s['uid'],v['name'],v['restartCount'],disposition)
                if key not in failures:
                    current=failure_codes(s['name'],v['name'],s['uid'])
                    previous=(failure_codes(s['name'],v['name'],s['uid'],previous=True)
                              if v['previousTermination'] else {'status':'NOT_EXERCISED','codes':[]})
                    codes=sorted(set(current['codes']+previous['codes']))
                    hard=disposition=='HARD' or bool(producer_startup.TERMINAL_CODES.intersection(codes))
                    finding={'pod':s['name'],'uid':s['uid'],'failed':[{'container':v['name'],
                             'codes':codes,'state':v['state'],'priorTermination':v['previousTermination'],
                             'restartCount':v['restartCount'],'currentLog':current,'previousLog':previous}],
                             'disposition':'HARD' if hard else 'RETRY','at':timestamp()}
                    failures[key]=finding
                    if len(failures)==1:put('failure-'+typ+'.json',finding)
                    put('startup-attempts-'+typ+'.json',list(failures.values()))
                if failures[key]['disposition']=='HARD':
                    raise RuntimeError('STARTUP_CONTAINER_FAILED_'+typ)
            if any(x.get('type')=='Ready' and x.get('status')=='True' for x in pod.get('status',{}).get('conditions',[])):
                ready_pod=pod
                identity=(s['uid'],tuple((v['name'],v['restartCount']) for v in s['containers']))
        if stable.observe(identity,time.monotonic()):
            if convergence:
                put('startup-convergence-'+typ+'.json',{'verdict':'READY','uid':identity[0],
                    'effectivePolicy':convergence,'observedStableSeconds':time.monotonic()-stable.started,
                    'recordedFailures':len(failures)})
            return ready_pod
        time.sleep(2)
    raise RuntimeError('READY_DEADLINE_'+typ)

def workload_ready(stage):
    for obj in objects(stage):
        nm=obj['metadata']['name']; sel=obj['spec']['selector']['matchLabels']
        convergence=producer_policy if nm=='pgstream' else None
        ready(','.join(k+'='+v for k,v in sel.items()),nm,
              convergence['maxSeconds'] if convergence else 300,convergence)
def execpod(pod,container,args,seconds=35):
    uid=pod['metadata']['uid']; nm=pod['metadata']['name']
    owned();assert get('pod',nm)['metadata']['uid']==uid
    result=command([tool/'kubectl','--context',ctx,'-n',ns,'exec',nm,'-c',container,'--',*args],timeout=seconds,private=True)
    assert get('pod',nm)['metadata']['uid']==uid
    return result
raw=Path(cfg['snapshotDirectory']);src=read(raw/'capture.json')
assert dt.datetime.now(dt.timezone.utc).timestamp()-dt.datetime.fromisoformat(src['capturedAt']).timestamp()<300,'REFRESH_BEFORE_ENTRY'
pre=read(d/'preflight.json');assert pre['commissioning']=='PREFLIGHT_ONLY'
selected=pre['trialEnvelope']['placementEnvelopes']
if len(selected)>1:assert all(v['trialFits'] for v in pre['workers'])
else:
    ordered=[n['metadata']['name'] for n in read(raw/'nodes.json')['items']]
    assert pre['workers'][ordered.index(e['targetNode'])]['trialFits']
assert pre['experiment']['renderSha256']==hashlib.sha256((d/'render.json').read_bytes()).hexdigest()
assert get('namespace',ns,False) is None
trust=objects('cluster-trust')[0]; tn=trust['metadata']['name']
assert tn==ns+'-vault-tokenreview' and trust['roleRef']['name']=='system:auth-delegator' and trust['subjects']==[{'kind':'ServiceAccount','name':'vault','namespace':ns}] and get('clusterrolebinding',tn,False) is None
assert read(Path(cfg['cacheAbsence']['path']))['verifiedAt']
intent=read(d/'intent.json')
producer_policy=producer_startup.policy(intent['profile']['phases'].get('producerStartup'),e['workDeadlineSeconds'])
selected_source=frozen.source(intent)
frozen.check_bootstrap_render(intent, [row for stage in
    ('foundation','stores','provision','private-admin','primer','serving') for row in objects(stage)])
primer_storage.check_render(selected_source, objects('primer'))
nsuid=trustuid=None;events=[];uids=[];current='create-namespace'
def interrupted(signum, frame):raise RuntimeError('CONTROLLER_SIGNAL_'+str(signum))
signal.signal(signal.SIGTERM,interrupted)
put('deadlines.json',{'workUntil':dt.datetime.fromtimestamp(work,dt.timezone.utc).isoformat(),'cleanupUntil':dt.datetime.fromtimestamp(cleanup,dt.timezone.utc).isoformat()})
try:
    node=create(objects('namespace')[0]);nsuid=node['metadata']['uid'];put('custody.json',{'namespace':ns,'namespaceUid':nsuid})
    owned();node=create(trust);trustuid=node['metadata']['uid'];put('custody.json',{'namespace':ns,'namespaceUid':nsuid,'trustName':tn,'trustUid':trustuid})
    install('foundation')
    # All private application/DB containers are cache-only in these final, hashed stages.
    for stage in ('stores','provision','private-admin','primer','serving'):
        for obj in objects(stage):
            spec=obj['spec']['template']['spec']
            for actor in spec.get('initContainers',[])+spec.get('containers',[]):
                if actor['image'] in (e['images']['app'],e['images']['postgres']):assert actor['imagePullPolicy']=='Never'
    # The owner may select its existing short-lived read-only pull credential.
    # Cache-only private image execution requires no registry operation here.
    if cfg.get('pullSecretCommand'):
        pull=command(cfg['pullSecretCommand'],private=True)
        command(rpc+['create','secret','generic',e['imagePullSecret'],'-n',ns,'--type=kubernetes.io/dockerconfigjson','--from-file=.dockerconfigjson=/dev/stdin','-o','name'],pull,private=True)
        del pull
    step('seed stores')
    secret_script=Path(cfg['bindingDirectory'])/'bindings/kubernetes/scripts/secrets.sh'
    command(['bash',secret_script,'seed',ns,'unused'],timeout=90,private=True)
    actual=get('configmap', frozen.HELPER_MAP)
    put('bootstrap-helper-readback.json',frozen.bootstrap_readback(selected_source,actual,uids,ns,rid))
    install('stores');workload_ready('stores')
    install('provision')
    provision=ready('job-name=provision','provision',e['provisionDeadlineSeconds'])
    step('owned role export')
    # Keep the two private configuration documents required for the completion oracle only.
    until=time.monotonic()+70
    while time.monotonic()<until:
        row=get('pod',provision['metadata']['name']);assert row['metadata']['uid']==provision['metadata']['uid']
        put('latest-role-export.json',summary(row))
        if row.get('status',{}).get('phase')=='Failed':
            owned()
            uid=row['metadata']['uid']
            assert get('pod',row['metadata']['name'])['metadata']['uid']==uid
            codes=failure_codes(row['metadata']['name'],'done',uid)['codes']
            assert get('pod',row['metadata']['name'])['metadata']['uid']==uid
            put('failure-role-export.json',{'podUid':uid,'container':'done','codes':codes,'classification':'CAPTURED' if codes else 'UNCLASSIFIED'})
            raise RuntimeError('SOURCE_ROLE_EXPORT_POD_FAILED')
        try:execpod(provision,'done',['test','-f','/state/.ready']);break
        except RuntimeError:time.sleep(1)
    else:raise RuntimeError('SOURCE_ROLE_EXPORT_NOT_READY')
    (live/'primer-config.private.json').write_bytes(execpod(provision,'done',['cat','/state/primer/config.json']))
    for role in ('evaluator','realtime'):
        (live/(role+'-config.private.json')).write_bytes(execpod(provision,'done',['cat','/state/'+role+'/config.json']))
    published=command(['bash',secret_script,'publish',ns,'unused'],timeout=185,private=True)
    if frozen.PRIMER_STORAGE in selected_source:
        storage_receipt=json.loads(published.splitlines()[0])
        selected_storage=selected_source[frozen.PRIMER_STORAGE]
        primer_storage.verify_receipt(selected_storage, storage_receipt)
        config=live/'primer-config.private.json'
        assert storage_receipt['configSha256']==hashlib.sha256(config.read_bytes()).hexdigest() and storage_receipt['configBytes']==config.stat().st_size, 'K8S_PRIMER_STORAGE_PUBLISH_CHANGED'
        put('primer-storage-published.json',storage_receipt)
    ack_wire=None
    if frozen.ACK_BUDGET in selected_source:
        ack_wire=json.loads(published.splitlines()[-2])
        assert ack_wire['effectiveTimeoutMs']==selected_source[frozen.ACK_BUDGET], 'K8S_PGSTREAM_ACK_PUBLISH_CHANGED'
        put('producer-ack-published.json',ack_wire)
    install('private-admin');workload_ready('private-admin')
    install('primer');pobj=get('job','primer')
    assert pobj['spec']['suspend'] is True
    k(['patch','job','primer','-n',ns,'--type=json','-p',json.dumps([{'op':'test','path':'/metadata/uid','value':pobj['metadata']['uid']},{'op':'test','path':'/spec/suspend','value':True},{'op':'replace','path':'/spec/suspend','value':False}])])
    primer=ready('job-name=primer','primer',min(e['provisionDeadlineSeconds'],3600))
    step('platform verification')
    # done runs source verification before writing the ready marker.
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        row=get('pod',primer['metadata']['name'])
        assert row['metadata']['uid']==primer['metadata']['uid']
        cons=row['status'].get('containerStatuses',[])
        if any(c['state'].get('terminated',{}).get('exitCode',0)!=0 for c in cons):
            put('platform-failure.json',{'podUid':row['metadata']['uid'],'codes':failure_codes(row['metadata']['name'],'done',row['metadata']['uid'])['codes']})
            raise RuntimeError('SOURCE_PLATFORM_VERIFICATION_FAILED')
        try:
            execpod(primer,'done',['test','-s','/run/ns-primer/verified.json'])
            break
        except RuntimeError:time.sleep(2)
    else:raise RuntimeError('SOURCE_VERIFICATION_MARKER_DEADLINE')
    install('serving');workload_ready('serving')
    if ack_wire is not None:
        latest=read(live/'latest-pgstream.json')
        pod=get('pod',latest['name']);assert pod['metadata']['uid']==latest['uid'], 'POD_OWNERSHIP_CHANGED'
        container=next(row for row in pod['status']['containerStatuses'] if row['name']=='pgstream' and row['ready'])
        wire='/run/ns-stream/pgstream.yaml'
        actual=execpod(pod,'pgstream',['sha256sum',wire]).decode().strip().split()
        current=get('pod',latest['name'])
        assert any(row['name']=='pgstream' and row['containerID']==container['containerID'] and row['ready']
                   for row in current['status']['containerStatuses']), 'K8S_PGSTREAM_ACK_CONTAINER_CHANGED'
        assert actual==[ack_wire['effectiveWireSha256'],wire], 'K8S_PGSTREAM_ACK_WIRE_CHANGED'
        put('producer-ack-readback.json',{**ack_wire,'runId':rid,'namespace':ns,'namespaceUid':nsuid,
                                        'podUid':latest['uid'],'containerId':container['containerID']})
    step('attach released runtime')
    limits=cfg['nativeLimits']
    command(['systemd-run','--user','--scope','--quiet','--unit=ns-'+rid+'-native',
             '-p','CPUQuota='+str(limits['millicpus']/10)+'%',
             '-p','MemoryMax='+str(limits['memoryBytes']),'-p','MemorySwapMax=0',
             '-p','RuntimeMaxSec='+str(max(1,int(work-time.time())-6)),
             sys.executable,'-B',Path(__file__).with_name('attach.py'),str(Path(sys.argv[1]).resolve())],
            timeout=int(work-time.time())-3)

except Exception as exc:
    if current in ('wait-primer','platform verification'):
        try:
            adm=pods('nightscout.org/run-id='+rid)
            pod=next(x for x in adm if any(c['name']=='admin' for c in x['spec']['containers']))
            observer=(Path(cfg['observerScript'])).read_text()
            observed=json.loads(execpod(pod,'admin',['node','-e',observer]))
            put('admin-classification.json',{k:observed[k] for k in ('status','reason','targetRole','checkPhase','causeCode') if k in observed})
        except Exception as audit:put('admin-observation-refusal.json',{'status':'UNMEASURED','error':str(audit)[:120]})
    put('first-failure.json',{'stage':current,'code':str(exc)[:500],'time':timestamp()})
    raise
finally:
    # Capture every surviving init/steady termination before exact owned cleanup.
    try:
        owned()
        put('terminal-pods.json',[summary(p) for p in pods('nightscout.org/run-id='+rid)])
    except Exception:put('terminal-pods-unavailable.json',{'status':'UNMEASURED'})
    cleaning=True
    cleanup_errors=[]
    if trustuid:
        try:
            t=get('clusterrolebinding',tn,False)
            if t:
                assert t['metadata']['uid']==trustuid and t['subjects']==trust['subjects'],'TRUST_OWNERSHIP_CHANGED'
                deluid('/apis/rbac.authorization.k8s.io/v1/clusterrolebindings/'+tn,trustuid)
            absent('clusterrolebinding',tn,False)
        except Exception as error:cleanup_errors.append({'scope':'trust','code':type(error).__name__})
    if nsuid:
        try:
            cur=get('namespace',ns,False)
            if cur:
                owned();deluid('/api/v1/namespaces/'+ns,nsuid)
            absent('namespace',ns,False)
        except Exception as error:cleanup_errors.append({'scope':'namespace','code':type(error).__name__})
    if cleanup_errors:
        put('cleanup-failure.json',{'verdict':'UNMEASURED','failures':cleanup_errors})
    else:
        put('absence.json',{'namespace':ns,'namespaceUid':nsuid,'trustUid':trustuid,'verifiedAt':timestamp()})
    auto_catalog(d, lambda path, value: path.write_text(json.dumps(value, indent=2) + '\n'))
    if cleanup_errors:
        raise RuntimeError('OWNED_CLEANUP_UNCONFIRMED')
