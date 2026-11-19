"""Execute an admitted instance; exact UID cleanup and first failure are retained.

Adapted from the retained staging controller; all local custody is explicit JSON.
"""
import base64, datetime as dt, hashlib, json, os, subprocess, sys, time, traceback
import signal
from contextlib import contextmanager
from pathlib import Path
from lifecycle_config import fixture_config, startup_preflight
import frozen
import primer_storage
import producer_startup
import application_topology
import candidate
import run_cleanup
import scheduling
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
assert e['runId']==d.name and ns.startswith('ns-synth-'),'INSTANCE_IDENTITY_CHANGED'
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
def command(argv,data=None,timeout=None,private=False):
    rem=cleanup-time.time() if cleaning else work-time.time()
    if not cleaning and phase_cutoff is not None:
        rem=min(rem,phase_cutoff-time.time())
    assert rem>0,'CUTOFF'
    if timeout is None:timeout=18 if cleaning else waits['commandSeconds']
    q=subprocess.run([str(x) for x in argv],input=data,capture_output=True,
                     timeout=ProgressWindow.read_seconds(min(timeout,rem)),env=env)
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
        if obj['kind']=='Job':
            # Jobs start when their stage is applied; the primer's deadline is the
            # remaining work window. No observer suspend/deadline patching.
            obj=dict(obj,spec=dict(obj['spec'],suspend=False))
            if obj['metadata']['name']=='primer':
                left=int(work-time.time())
                if left<=0:raise RuntimeError('PRIMER_WORK_DEADLINE')
                obj['spec']['activeDeadlineSeconds']=left
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

def provisioned_count(pod):
    # Read only the count from the source's atomic custody file, in the active
    # init container. Existing source images use the same checkpoint.
    if not any(c['name']=='primer' and 'running' in c['state']
               for c in pod.get('status',{}).get('initContainerStatuses', [])):
        return None
    script = """const fs=require('node:fs');
const path=(process.env.NS_PRIMER_STATE || '/run/ns-primer')+'/provisioned.json';
try {
  const rows=JSON.parse(fs.readFileSync(path));
  if (!Array.isArray(rows)) throw new Error('PRIMER_CHECKPOINT_INVALID');
  console.log(rows.length);
}
catch(e) { if(e.code!=='ENOENT')throw e; console.log(0); }"""
    return int(execpod(pod, 'primer', ['node', '-e', script]))


def ready(label,typ,timeout,convergence=None,primer_job=None):
    step('wait-'+typ)
    started=time.time()
    outer=min(work,phase_cutoff if phase_cutoff is not None else work)
    # The optional producer convergence scenario also selects a hard ceiling.
    until=min(outer, started+convergence['maxSeconds']) if convergence else outer
    progress=ProgressWindow(timeout, now=time.monotonic)
    checkpoint={'stallSeconds':timeout, 'startedAtEpochSeconds':started, 'workUntilEpochSeconds':outer}
    put('startup-window-'+typ+'.json',checkpoint)
    if primer_job is not None:
        checkpoint={'selectedSeconds':timeout, 'startedAtEpochSeconds':started, 'completedTenants':0,
                    'workUntilEpochSeconds':outer, 'jobUid':primer_job['metadata']['uid']}
        put('startup-window-primer.json',checkpoint)
        unavailable=False
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
                for pod in found:
                    if primer_job is not None:
                        controllers=[owner['uid'] for owner in pod['metadata'].get('ownerReferences',[]) if owner.get('controller')]
                        if controllers != [checkpoint['jobUid']]:
                            raise RuntimeError('PRIMER_JOB_OWNERSHIP_CHANGED')
                        try:
                            count=provisioned_count(pod)
                            if count is not None:
                                if not 0 <= count <= e['tenantCount']:
                                    raise RuntimeError('PRIMER_CHECKPOINT_INVALID')
                                unavailable=False
                                if progress.observe(count):
                                    checkpoint.update(completedTenants=count, lastProgressEpochSeconds=time.time())
                                    put('startup-window-primer.json',checkpoint)
                        except (RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
                            # A completed init container can disappear between status and
                            # exec. Recheck Pod readiness. Signals and custody errors escape.
                            if isinstance(error,RuntimeError) and str(error)!='PRIVATE_STEP_FAILED':
                                raise
                            unavailable=True
                    s=summary(pod);put('latest-'+typ+'.json',s)
                    if primer_job is None:
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
        if primer_job is not None:
            unavailable=True
    if any(p['placement'] == 'Unschedulable' for p in placements):
        raise RuntimeError('K8S_POD_UNSCHEDULABLE')
    if primer_job is not None and time.time()<outer:
        raise RuntimeError('PRIMER_PROVISION_PROGRESS_UNMEASURED' if unavailable else 'PRIMER_PROVISION_STALLED')
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
        ready(','.join(k+'='+v for k,v in sel.items()),nm,seconds,convergence)
def release_job(name):
    owned()
    return get('job', name)


def verify_database(job_uid, seconds):
    import kube_adapter as adapter
    with startup_window('platform-verify', seconds) as until:
        remaining = until-time.time()
        assert remaining > 1, 'SOURCE_VERIFICATION_JOB_DEADLINE'
        # Kubernetes owns Job progress. Read its terminal condition and the
        # selected Pod after the watch, with diagnostic time left in the run.
        try:
            command([tool/'kubectl','--context',ctx,'-n',ns,'wait','--for=condition=complete',
                     'job/verification','--timeout='+str(max(1,int(remaining)))+'s'], timeout=remaining, private=True)
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
    owned()
    job = get('job','verification')
    assert job['metadata']['uid']==job_uid, 'JOB_OWNERSHIP_CHANGED'
    condition = candidate.job_condition(job)
    witnesses = [p for p in pods('job-name=verification') if
                 adapter.controller(p)['uid']==job_uid and
                 p['metadata']['labels'].get('nightscout.org/run-id')==rid]
    if condition != 'Complete':
        failures = []
        for pod in witnesses:
            for container in summary(pod)['containers']:
                if container['state'].get('terminated',{}).get('exitCode',0)!=0:
                    failures.append(failure_codes(pod['metadata']['name'], container['name'], pod['metadata']['uid']))
        put('platform-failure.json', {'jobUid':job_uid,'condition':condition,'logs':failures})
        raise RuntimeError('SOURCE_PLATFORM_VERIFICATION_FAILED' if condition=='Failed' else 'SOURCE_VERIFICATION_JOB_DEADLINE')
    pod, = witnesses
    name, uid = pod['metadata']['name'], pod['metadata']['uid']
    done, = (row for row in pod['status']['containerStatuses'] if row['name']=='done')
    assert done['state'].get('terminated',{}).get('exitCode')==0, 'SOURCE_PLATFORM_VERIFICATION_FAILED'
    raw = command(rpc+['logs',name,'-n',ns,'-c','done','--limit-bytes=65536'],private=True)
    require_pod_uid(name,uid)
    source = read(Path(cfg['bindingDirectory'])/'bindings/kubernetes/assets/source-contract.json')
    config = {'namespace':ns, 'runId':rid, 'pins':{'candidate':source}}
    proof = candidate.verification_log(adapter,config,raw)
    put('platform-verification.json', {'jobUid':job_uid,'podUid':uid,'containerId':done['containerID'],'proof':proof})


def start_serving(split):
    if split:
        install('verification')
        verification = release_job('verification')
        step('platform verification')
        verify_database(verification['metadata']['uid'],
                        min(waits['platformVerifySeconds'], verification['spec']['activeDeadlineSeconds']))
        install('serving')
        workload_ready('serving')
    install('primer')
    pobj = release_job('primer')
    primer = ready('job-name=primer', 'primer', waits['primerReadySeconds'], primer_job=pobj)
    if not split:
        step('platform verification')
        # done runs source verification before writing the ready marker.
        with startup_window('platform-verify',waits['platformVerifySeconds']) as until:
            while time.time()<until:
                row=get('pod',primer['metadata']['name'])
                assert row['metadata']['uid']==primer['metadata']['uid']
                cons=row['status'].get('containerStatuses',[])
                if any(c['state'].get('terminated',{}).get('exitCode',0)!=0 for c in cons):
                    put('platform-failure.json',{'podUid':row['metadata']['uid'],'codes':failure_codes(row['metadata']['name'],'done',row['metadata']['uid'])['codes']})
                    raise RuntimeError('SOURCE_PLATFORM_VERIFICATION_FAILED')
                try:
                    execpod(primer,'done',['test','-s','/run/ns-primer/verified.json'])
                    break
                except RuntimeError:time.sleep(min(2,max(0,until-time.time())))
            else:raise RuntimeError('SOURCE_VERIFICATION_MARKER_DEADLINE')
        install('serving');workload_ready('serving')


def execpod(pod,container,args,seconds=None):
    uid=pod['metadata']['uid']; nm=pod['metadata']['name']
    owned();assert get('pod',nm)['metadata']['uid']==uid
    result=command([tool/'kubectl','--context',ctx,'-n',ns,'exec',nm,'-c',container,'--',*args],
                   timeout=waits['execSeconds'] if seconds is None else seconds,private=True)
    assert get('pod',nm)['metadata']['uid']==uid
    return result
pre=read(d/'preflight.json');assert pre['commissioning']=='PREFLIGHT_ONLY'
scheduler = cfg.get('schedulerPlacement', False)
assert pre['experiment']['renderSha256']==hashlib.sha256((d/'render.json').read_bytes()).hexdigest()
assert get('namespace',ns,False) is None
trust=objects('cluster-trust')[0]; tn=trust['metadata']['name']
assert tn==ns+'-vault-tokenreview' and trust['roleRef']['name']=='system:auth-delegator' and trust['subjects']==[{'kind':'ServiceAccount','name':'vault','namespace':ns}] and get('clusterrolebinding',tn,False) is None
if not scheduler:assert read(Path(cfg['cacheAbsence']['path']))['verifiedAt']
producer_policy=producer_startup.policy(intent['profile']['phases'].get('producerStartup'),e['workDeadlineSeconds'])
selected_source=frozen.source(intent)
if frozen.JOB_COMPLETE in selected_source:
    contract, = (row['data']['source-contract.json'] for row in objects('foundation')
                 if row['kind']=='ConfigMap' and row['metadata']['name']=='provision-scripts')
    receipt=(Path(cfg['bindingDirectory'])/'binding.json').resolve()
    if split:
        contract = (receipt.parent/'bindings/kubernetes/assets/source-contract.json').read_bytes()
    frozen.rendered_contract(intent,contract,{'path':str(receipt),'sha256':cfg['inputs'][str(receipt)]})
frozen.check_bootstrap_render(intent, [row for stage in
    startup_stages for row in objects(stage)])
primer_storage.check_render(selected_source, objects('primer'))
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
        command(['bash',secret_script,'seed',ns,'unused'],timeout=waits['secretSeedSeconds'],private=True)
    actual=get('configmap', frozen.HELPER_MAP)
    put('bootstrap-helper-readback.json',frozen.bootstrap_readback(selected_source,actual,uids,ns,rid))
    install('stores');workload_ready('stores')
    install('provision')
    provision=ready('job-name=provision','provision',waits['provisionReadySeconds'])
    step('owned role export')
    # Keep the two private configuration documents required for the completion oracle only.
    with startup_window('role-export',waits['roleExportSeconds']) as until:
        while time.time()<until:
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
            except RuntimeError:time.sleep(min(1,max(0,until-time.time())))
        else:raise RuntimeError('SOURCE_ROLE_EXPORT_NOT_READY')
        if frozen.PRIMER_STORAGE in selected_source:
            (live/'primer-config.private.json').write_bytes(execpod(provision,'done',['cat','/state/primer/config.json']))
        for role in ('evaluator','realtime'):
            (live/(role+'-config.private.json')).write_bytes(execpod(provision,'done',['cat','/state/'+role+'/config.json']))
        receipt_code=(Path(__file__).resolve().parent.parent/'m7-joined/native-receipt-source.cjs').read_text()+"\nconsole.log(JSON.stringify(module.exports.captureFiles('/opt/app','/state')));"
        (live/'native-receipt-source.private.json').write_bytes(execpod(provision,'done',['node','-e',receipt_code]))
    with startup_window('secret-publish',waits['secretPublishSeconds']):
        published=command(['bash',secret_script,'publish',ns,'unused'],timeout=waits['secretPublishSeconds'],private=True)
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
    start_serving(split)
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
    native_scope = 'ns-' + rid + '-native.scope'
    put('native-unit.json', {'unit': native_scope})
    command(['systemd-run','--user','--scope','--quiet','--unit='+native_scope,
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
            result=run_cleanup.cleanup(lambda argv:command(rpc+argv,timeout=min(150,max(1,cleanup-time.time()-2))).decode(),ns,rid)
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
