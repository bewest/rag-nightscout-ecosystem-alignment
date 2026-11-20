"""Execute an admitted instance; exact UID cleanup and first failure are retained.

Adapted from the retained staging controller; all local custody is explicit JSON.
"""
import base64, datetime as dt, hashlib, json, os, subprocess, sys, time, traceback
import signal
from contextlib import contextmanager
from pathlib import Path
from lifecycle_config import fixture_config, startup_preflight
import frozen
import producer_startup
import application_topology
import candidate
import run_cleanup
import scheduling
import fixture_copy
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "m7-joined"))
from auto_catalog import auto_catalog
import point_results
from primer_progress import ProgressWindow
cfg=fixture_config(Path(sys.argv[1]))
d=Path(cfg['caseDirectory']); tool=Path(cfg['toolsDirectory'])
read=lambda p:json.loads(p.read_bytes())
os.umask(0o077);sys.dont_write_bytecode=True
e=read(d/'environment.json'); ns=e['namespace'];ctx=e['context'];rid=e['runId']
intent=read(d/'intent.json')
startup=cfg.get('startupWindowPreflight') or startup_preflight(intent,e,[])
waits=startup['selectedSeconds']
assert e['runId']==d.name,'INSTANCE_IDENTITY_CHANGED'
live=d/'runtime';live.mkdir(mode=0o700,exist_ok=True);assert not any(live.iterdir()),'ENTERED_OUTPUT_EXISTS'
def put(n,obj):(live/n).write_text(json.dumps(obj,indent=2)+'\n')
def timestamp():return dt.datetime.now(dt.timezone.utc).isoformat()
entry_memory = point_results.available_memory()

# Once this case has acquired its empty output directory, refusals before the
# namespace create also need a terminal result. The entered lifecycle below
# installs its own exception/cleanup path before making any mutation.
def unentered_failure(kind, error, trace):
    import re
    try:
        code = str(error)
        put('first-failure.json', {'stage':'pre-entry', 'time':timestamp(),
            'code':code if re.fullmatch(r'[A-Z0-9_]{1,120}', code) else kind.__name__})
        point_results.publish_native(d, mem_available_at_entry_bytes=entry_memory)
    finally:
        sys.__excepthook__(kind, error, trace)
sys.excepthook = unentered_failure
def command(argv,data=None,timeout=None,private=False,environment=None):
    rem=cleanup-time.time() if cleaning else work-time.time()
    if not cleaning and phase_cutoff is not None:
        rem=min(rem,phase_cutoff-time.time())
    assert rem>0,'CUTOFF'
    if timeout is None:timeout=18 if cleaning else waits['commandSeconds']
    q=subprocess.run([str(x) for x in argv],input=data,capture_output=True,
                     timeout=ProgressWindow.read_seconds(min(timeout,rem)),env=environment or env)
    if q.returncode:
        import re
        codes=sorted(set(re.findall(rb'\b(?:K8S_|M7_|PRIMER_|BOOTSTRAP_|PLATFORM_|VAULT_|EVALUATOR_)[A-Z0-9_]{2,90}\b',q.stderr+q.stdout)))
        error = {'program':Path(str(argv[0])).name,'returncode':q.returncode,'codes':[x.decode() for x in codes]}
        if cfg.get('schedulerPlacement') and not private:
            error['stderr'] = q.stderr[-1500:].decode(errors='replace')
        put('last-command-error.json',error)
        raise RuntimeError('PRIVATE_STEP_FAILED' if private else 'STAGE_COMMAND_FAILED')
    return q.stdout
env={**os.environ,'PATH':str(tool)+':'+os.environ['PATH'],'TMPDIR':str(live),'NS_KUBE_CONTEXT':ctx,'NS_RUN_ID':rid,'RO_NO_LOG':'1','PYTHONDONTWRITEBYTECODE':'1'}
env.pop('RO_OWNED_WORKER_VIEW', None)
rpc=[tool/'kubectl','--context',ctx,'--request-timeout='+str(waits['requestSeconds'])+'s']
start=time.time();work=start+e['workDeadlineSeconds'];cleanup=start+e['cleanupDeadlineSeconds'];cleaning=False
phase_cutoff=None

@contextmanager
def startup_window(name, seconds):
    global phase_cutoff
    previous=phase_cutoff
    started=time.time()
    phase_cutoff=min(started+seconds,work,previous if previous is not None else work)
    try:
        put('startup-window-'+name+'.json',{'selectedSeconds':seconds,'startedAtEpochSeconds':started,
            'effectiveDeadlineEpochSeconds':phase_cutoff,'effectiveWindowSeconds':max(0,phase_cutoff-started)})
        yield phase_cutoff
    finally:
        phase_cutoff=previous

def k(args,body=None,private=False):return command(rpc+args,json.dumps(body).encode() if body else None,private=private)
def get(kind,name,local=True):
    b=k(['get',kind,name,*(['-n',ns] if local else []),'--ignore-not-found','-o','json'])
    return json.loads(b) if b.strip() else None
def create(obj):
    return json.loads(k(['create','-f','-','-o','json'],obj))
def owned():
    cur=get('namespace',ns,False)
    assert cur and cur['metadata']['uid']==nsuid and cur['metadata']['labels']['nightscout.org/run-id']==rid
def objects(stage):return read(d/'stages'/f'{stage}.json')['items']
split = 'verification' in read(d/'inventory.json').get('workloads', {})
startup_stages = ('foundation','stores','provision','private-admin','primer','serving') + (('verification',) if split else ())
def step(stage):
    global current
    current=stage
    events.append({'stage':stage,'time':timestamp(),'monoMs':time.monotonic_ns()/1e6});put('stages.json',events)
def install(stage):
    step(stage);owned()
    for obj in objects(stage):
        assert obj['metadata']['namespace']==ns
        if obj['kind']=='Job' and obj['metadata']['name']=='primer' and intent['primerLocation']=='claim':
            obj=dict(obj,spec=dict(obj['spec'],suspend=False))
        made=create(obj)
        uids.append({'kind':made['kind'],'name':made['metadata']['name'],'uid':made['metadata']['uid']})
        put('created.json',uids)
def pods(label):
    return json.loads(k(['get','pods','-n',ns,'-l',label,'-o','json']))['items']
def summary(pod):
    sts=pod.get('status',{})
    record = {'name':pod['metadata']['name'],'uid':pod['metadata']['uid'],'node':pod['spec'].get('nodeName'),'phase':sts.get('phase'),
            'resources':[{k:v.get(k) for k in ('name','resources')} for v in pod['spec'].get('initContainers',[])+pod['spec'].get('containers',[])],
            'containers':[{k:c.get(k) for k in ('name','imageID','restartCount','ready')}|{'state':c.get('state',{}),'previousTermination':c.get('lastState',{}).get('terminated')} for c in sts.get('initContainerStatuses',[])+sts.get('containerStatuses',[])]}
    if cfg.get('schedulerPlacement'):
        record['createdAt'] = pod['metadata'].get('creationTimestamp')
        record['scheduled'] = next((row for row in sts.get('conditions', ())
                                    if row['type'] == 'PodScheduled'), None)
    return record
def failure_codes(pod,container,uid,previous=False):
    owned()
    require_pod_uid(pod,uid)
    limit=65536
    args=['logs',pod,'-n',ns,'-c',container,'--tail=60','--limit-bytes='+str(limit)]
    if previous:args.append('--previous')
    output=None
    try:
        output=command(rpc+args,private=True)
        observed={'status':'CAPTURED','codes':producer_startup.log_codes(output)}
        diagnostics = producer_startup.role_diagnostics(output)
        if diagnostics:
            observed['roleDiagnostics'] = diagnostics
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        observed={'status':'UNMEASURED','codes':[]}
    require_pod_uid(pod,uid)
    if output is not None:
        retained=output[-limit:]
        digest=hashlib.sha256(retained).hexdigest()
        identity=hashlib.sha256((uid+'\0'+container+'\0'+str(previous)).encode()).hexdigest()[:16]
        path=live/('failed-container-'+identity+'-'+digest+'.private.log')
        try:
            if path.exists():
                assert path.read_bytes()==retained,'FAILED_CONTAINER_CAPTURE_CHANGED'
            else:
                with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
                    stream.write(retained)
            observed['privateLog']={'status':'CAPTURED','path':str(path),'bytes':len(retained),
                'sha256':digest,'responseBytes':len(output),'responseSha256':hashlib.sha256(output).hexdigest(),
                'responseTruncated':len(output)>limit,'tailLines':60,'byteLimit':limit}
        except OSError as error:
            observed['privateLog']={'status':'UNMEASURED','code':type(error).__name__}
    return observed

def require_pod_uid(name,uid):
    row=get('pod',name)
    if row is None or row['metadata']['uid']!=uid:
        raise RuntimeError('POD_OWNERSHIP_CHANGED')

def ready(label,typ,timeout,convergence=None,want=1):
    step('wait-'+typ)
    started=time.time()
    outer=min(work,phase_cutoff if phase_cutoff is not None else work)
    # The optional producer convergence scenario also selects a hard ceiling.
    until=min(outer, started+convergence['maxSeconds']) if convergence else outer
    progress=ProgressWindow(timeout, now=time.monotonic)
    checkpoint={'stallSeconds':timeout, 'startedAtEpochSeconds':started, 'workUntilEpochSeconds':outer}
    put('startup-window-'+typ+'.json',checkpoint)
    stable=producer_startup.StableReady(convergence['stableReadySeconds'] if convergence else 0)
    failures={}
    placements = []
    try:
        with progress.bound_reads():
            while time.time()<until and progress.remaining()>0:
                owned()
                found=pods(label)
                if any(x['metadata']['labels'].get('nightscout.org/run-id')!=rid for x in found):raise RuntimeError('FOREIGN_POD')
                placements = [scheduling.outcome(p) for p in found]
                if found:
                    put('placement-'+typ+'.json', placements)
                ready_pod=None
                identity=None
                ready_ids=[]
                for pod in found:
                    s=summary(pod);put('latest-'+typ+'.json',s)
                    # Admission, scheduling and per-container startup/ready transitions
                    # are finite milestones. Restarts and repeated RPCs earn no credit.
                    status = pod.get('status', {})
                    count = producer_startup.milestones(status)
                    if progress.observe(count):
                        checkpoint.update(milestones=count, lastProgressEpochSeconds=time.time())
                        put('startup-window-'+typ+'.json',checkpoint)
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
                        ready_ids.append(identity)
                if want>1:
                    # Every replica (evaluator slices) must be Ready, not just one.
                    identity=producer_startup.replica_identity(ready_ids,want)
                if stable.observe(identity,time.monotonic()) and time.time()<until and progress.remaining()>0:
                    if convergence:
                        put('startup-convergence-'+typ+'.json',{'verdict':'READY','uid':identity[0],
                            'effectivePolicy':convergence,'observedStableSeconds':time.monotonic()-stable.started,
                            'recordedFailures':len(failures)})
                    return ready_pod
                delay=min(2,max(0,until-time.time()))
                time.sleep(min(delay,timeout/2,progress.remaining()))
    except subprocess.TimeoutExpired:
        if progress.remaining()>0 and time.time()<until:
            raise
    if any(p['placement'] == 'Unschedulable' for p in placements):
        raise RuntimeError('K8S_POD_UNSCHEDULABLE')
    if application_topology.readiness_signal(intent,typ,frozen.require) and time.time()<work:
        # The serving workload's readiness window elapsed inside the run's work window.
        # Readiness is a signal under readiness-serve-then-warm: record it, continue.
        put('readiness-signal-'+typ+'.json',{'verdict':'UNMEASURED','reason':'READINESS_STALLED',
            'waitedSeconds':round(time.time()-started,3)})
        return None
    raise RuntimeError(('READINESS_STALLED_' if time.time()<until else 'READY_DEADLINE_')+typ)

def workload_ready(stage):
    for obj in objects(stage):
        nm=obj['metadata']['name']; sel=obj['spec']['selector']['matchLabels']
        convergence=producer_policy if nm=='pgstream' else None
        timeout=waits['cohortReadySeconds'] if application_topology.serving_workload(intent,stage,obj,frozen.require) else waits['workloadReadySeconds']
        seconds=convergence['maxSeconds'] if convergence else timeout
        if stage=='stores' and nm=='vault':
            # The bootstrap Job initializes and unseals Vault. The headless
            # bootstrap Service routes to the Pod before its Ready condition.
            probe=obj['spec']['template']['spec']['containers'][0].get('readinessProbe',{})
            if probe.get('httpGet',{}).get('path')=='/v1/sys/health?uninitcode=200':
                continue
        ready(','.join(k+'='+v for k,v in sel.items()),nm,seconds,convergence,obj['spec'].get('replicas',1))
def wait_job(name, seconds):
    owned()
    with startup_window(name, seconds) as until:
        while time.time() < until:
            state = candidate.job_condition(get('job', name) or {})
            if state == 'Complete':
                return
            if state == 'Failed':
                raise RuntimeError('K8S_JOB_FAILED_' + name.upper())
            time.sleep(min(1, max(0, until-time.time())))
    raise RuntimeError('K8S_JOB_DEADLINE_' + name.upper())


def execpod(pod,container,args,seconds=None):
    uid=pod['metadata']['uid']; nm=pod['metadata']['name']
    owned();assert get('pod',nm)['metadata']['uid']==uid
    result=command([tool/'kubectl','--context',ctx,'-n',ns,'exec',nm,'-c',container,'--',*args],
                   timeout=waits['execSeconds'] if seconds is None else seconds,private=True)
    assert get('pod',nm)['metadata']['uid']==uid
    return result
pre=read(d/'preflight.json');assert pre['commissioning']=='PREFLIGHT_ONLY'
reuse=cfg.get('fixture')
scheduler = cfg.get('schedulerPlacement', False)
assert get('namespace',ns,False) is None
trust=objects('cluster-trust')[0]; tn=trust['metadata']['name']
assert tn==ns+'-vault-tokenreview' and trust['roleRef']['name']=='system:auth-delegator' and trust['subjects']==[{'kind':'ServiceAccount','name':'vault','namespace':ns}] and get('clusterrolebinding',tn,False) is None
if not scheduler:assert read(Path(cfg['cacheAbsence']['path']))['verifiedAt']
producer_policy=producer_startup.policy(intent['profile']['phases'].get('producerStartup'),e['workDeadlineSeconds'])
selected_source=frozen.source(intent)
nsuid=trustuid=None;events=[];uids=[];current='create-namespace'
def interrupted(signum, frame):raise RuntimeError('CONTROLLER_SIGNAL_'+str(signum))
signal.signal(signal.SIGTERM,interrupted)
put('deadlines.json',{'workUntil':dt.datetime.fromtimestamp(work,dt.timezone.utc).isoformat(),'cleanupUntil':dt.datetime.fromtimestamp(cleanup,dt.timezone.utc).isoformat()})
sys.excepthook = sys.__excepthook__
try:
    node=create(objects('namespace')[0]);nsuid=node['metadata']['uid'];put('custody.json',{'namespace':ns,'namespaceUid':nsuid})
    owned();node=create(trust);trustuid=node['metadata']['uid'];put('custody.json',{'namespace':ns,'namespaceUid':nsuid,'trustName':tn,'trustUid':trustuid})
    install('foundation')
    # Legacy fixtures expect prewarmed images. Scheduler fixtures leave the
    # digest-pinned image pull policy to Kubernetes and the authored manifest.
    if not scheduler:
        for stage in startup_stages[1:]:
            for obj in objects(stage):
                spec=obj['spec']['template']['spec']
                for actor in spec.get('initContainers',[])+spec.get('containers',[]):
                    if actor['image'] in (e['images']['app'],e['images']['postgres']):
                        assert actor['imagePullPolicy']=='Never'
    if cfg.get('pullSecretCommand'):
        pull=command(cfg['pullSecretCommand'],private=True)
        command(rpc+['create','secret','generic',e['imagePullSecret'],'-n',ns,'--type=kubernetes.io/dockerconfigjson','--from-file=.dockerconfigjson=/dev/stdin','-o','name'],pull,private=True)
        del pull
    step('seed stores')
    secret_script=Path(cfg['bindingDirectory'])/'bindings/kubernetes/scripts/secrets.sh'
    with startup_window('secret-seed',waits['secretSeedSeconds']):
        if reuse and reuse['mode']=='restore':
            # The copied PostgreSQL, Vault and roster need the Secrets they were seeded with.
            fixture_copy.import_secrets(lambda a,b=None:k(a,b,private=True),ns,rid,reuse['directory'])
        else:
            # The seed renders pgstream's receivers for the binding's evaluator K (inventory
            # seed.environment, K>1 only); an inherited NS_EVALUATOR_WORKERS never reaches it.
            seed_env={key:value for key,value in env.items() if key!='NS_EVALUATOR_WORKERS'}
            seed_env.update(fixture_copy.seed_environment(read(d/'inventory.json')))
            command(['bash',secret_script,'seed',ns,e['images']['app']],timeout=waits['secretSeedSeconds'],private=True,
                    environment=seed_env)
    if reuse:
        step('fixture claims');owned()
        uids.extend(fixture_copy.create(k,ns,objects('fixture-claims')));put('created.json',uids)
    install('stores')
    install('provision')
    # Vault becomes Ready after the provision Job initializes it. The app
    # roles can then start independently of synthetic tenant creation.
    step('provision')
    wait_job('provision', waits['provisionReadySeconds'])
    workload_ready('stores')
    install('private-admin')
    install('serving')
    workload_ready('private-admin')
    workload_ready('serving')
    install('primer')
    if intent['primerLocation']=='claim':
        wait_job('primer', waits['primerReadySeconds'])
    if reuse and reuse['mode']=='seed':
        # A seed run ends here: stop every writer, snapshot the four claims, keep the Secrets.
        step('stop writers');owned()
        fixture_copy.quiesce(k,ns,rid,work)
        step('capture fixture');owned()
        put('fixture-capture.json',fixture_copy.capture(k,ns,rid,reuse,read(d/'stages/fixture-snapshots.json'),
            {'tenants':e['tenantCount'],'appImage':e['images']['app'],'postgresImage':e['images']['postgres'],
             'coreCommit':cfg['candidate']['coreCommit'],'deployCommit':cfg['candidate']['deployCommit'],
             'alignmentCommit':cfg['alignmentCommit'],
             **fixture_copy.slices_record(read(d/'inventory.json'))},work))
        step('fixture captured')
        raise SystemExit(0)
    step('attach released runtime')
    limits=cfg['nativeLimits']
    native_scope = 'ns-' + rid + '-native.scope'
    put('native-unit.json', {'unit': native_scope})
    command(['systemd-run','--user','--scope','--quiet','--unit='+native_scope,
             '-p','CPUQuota='+str(limits['millicpus']/10)+'%',
             '-p','MemoryMax='+str(limits['memoryBytes']),'-p','MemorySwapMax=0',
             '-p','RuntimeMaxSec='+str(max(1,int(work-time.time())-6)),
             sys.executable,'-B',Path(__file__).with_name('attach.py'),str(Path(sys.argv[1]).resolve())],
            timeout=int(work-time.time())-3)

except Exception as exc:
    failure={'stage':current,'code':str(exc)[:500],'time':timestamp()}
    try:
        owned()
        vault, = [pod for pod in pods('nightscout.org/run-id='+rid)
                  if any(c['name']=='vault' for c in pod['spec']['containers'])]
        # Ask Vault itself over verified TLS. Status overrides let its CLI
        # expose initialized/sealed separately even when normal health is 503.
        raw=execpod(vault,'vault',['env','VAULT_MAX_RETRIES=0','vault','read','-format=json',
            '-address=https://vault-bootstrap:8200','-ca-cert=/run/ns-ca/ca.crt','sys/health',
            'sealedcode=200','uninitcode=200'],seconds=4)
        state=json.loads(raw)
        if producer_startup.vault_sealed(state):
            failure['stopReason']='VAULT_SEALED'
    except (OSError, RuntimeError, AssertionError, ValueError, subprocess.SubprocessError):
        pass
    put('first-failure.json',failure)
    raise
finally:
    # Capture every surviving init/steady termination before exact owned cleanup.
    try:
        owned()
        put('terminal-pods.json',[summary(p) for p in pods('nightscout.org/run-id='+rid)])
    except Exception:put('terminal-pods-unavailable.json',{'status':'UNMEASURED'})
    cleaning=True
    rpc=[tool/'kubectl','--context',ctx,'--request-timeout=170s']  # `delete --wait` holds one request
    cleanup_errors=[]
    try:
        if nsuid and current != 'create-namespace':
            owned()
            remaining_pods = pods('nightscout.org/run-id='+rid)
            rows = [scheduling.outcome(pod) for pod in remaining_pods]
            for pod, row in zip(remaining_pods, rows):
                if row['placement'] == 'Unschedulable':
                    events = json.loads(k(['get','events','-n',ns,'--field-selector',
                                           'involvedObject.uid='+row['uid']+',reason=FailedScheduling','-o','json']))
                    row['events'] = scheduling.failed_events(pod, events)
            put('scheduling.json', rows)
    except (OSError, RuntimeError, ValueError, AssertionError, subprocess.SubprocessError) as error:
        put('scheduling-unavailable.json', {'status':'UNMEASURED','reason':type(error).__name__})
    if nsuid or trustuid:
        try:
            result=run_cleanup.cleanup(lambda argv:command(rpc+argv,timeout=min(150,max(1,cleanup-time.time()-2))).decode(),ns,rid,
                                       scoped=run_cleanup.FIXTURE_SCOPED if reuse else run_cleanup.CLUSTER_SCOPED)
            put('absence.json',{**result,'namespaceUid':nsuid,'trustUid':trustuid,'verifiedAt':timestamp()})
        except run_cleanup.CleanupFailed as error:cleanup_errors.append({'scope':'absence','code':'K8S_CLEANUP_LEFTOVER','leftovers':error.leftovers})
        except Exception as error:cleanup_errors.append({'scope':'cleanup','code':type(error).__name__})
    if (live/'native-unit.json').exists():
        try:
            observed = subprocess.run(['systemctl', '--user', 'show', native_scope,
                '--property=LoadState', '--property=ActiveState'], env=env, capture_output=True,
                text=True, timeout=min(5, max(1, cleanup-time.time())))
            states = dict(line.split('=', 1) for line in observed.stdout.splitlines() if '=' in line)
            absent = (observed.returncode in (0, 4) and states.get('LoadState') == 'not-found'
                      or observed.returncode == 0 and states.get('ActiveState') == 'inactive')
            put('native-unit-absence.json', {'unit': native_scope, 'absent': absent, **states})
            if not absent:
                cleanup_errors.append({'scope':'native-host-unit', 'code':'K8S_NATIVE_UNIT_ABSENCE_UNCONFIRMED'})
        except (OSError, subprocess.SubprocessError) as error:
            cleanup_errors.append({'scope':'native-host-unit','code':type(error).__name__})
    if cleanup_errors:
        put('cleanup-failure.json',{'verdict':'FAIL' if any(x['scope']=='absence' for x in cleanup_errors) else 'UNMEASURED','failures':cleanup_errors})
    point_results.publish_native(d, mem_available_at_entry_bytes=entry_memory)
    auto_catalog(d, lambda path, value: path.write_text(json.dumps(value, indent=2) + '\n'))
    if cleanup_errors:
        raise RuntimeError('OWNED_CLEANUP_UNCONFIRMED')
