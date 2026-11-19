"""Attach the exact released native runner in the fixture's inherited, finite cgroup."""
import datetime as dt,hashlib,json,os,re,socket,subprocess,sys,time
from pathlib import Path
from lifecycle_config import fixture_config
control=fixture_config(Path(sys.argv[1]))
d=Path(control['caseDirectory']); live=d/'runtime'
K=Path(__file__).resolve().parent
read=lambda f:json.loads(f.read_bytes())
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def ref(p):return {'path':str(p),'sha256':sha(p)}
e=read(d/'environment.json');m=read(d/'intent.json');ns=e['namespace'];uid=read(live/'custody.json')['namespaceUid'];now=time.time()
dl=read(live/'deadlines.json');until=dt.datetime.fromisoformat(dl['workUntil']).timestamp()-5
os.umask(0o077)
base=Path(control['runTemplate']['path'])
cfg=read(base)
for key in ('pins','completion','workload','ordinaryRosterTenants'):cfg.pop(key,None)
core=Path(control['coreRepository'])
cfg['driver']['coreRepository']=str(core)
k6=Path(control['k6'])
cfg['driver'].update(k6=str(k6),k6Sha256=sha(k6));cfg['readonlyGuard']=str(Path(control['readonlyGuard']))
cfg.update(context=e['context'],runId=e['runId'],namespace=ns,tenants=e['tenantCount'],deadlines={k:v.replace('+00:00','Z') for k,v in dl.items()},tenantsFile=str(live/'packet/primer/tenants.json'))
def execute(label,args,deadline=1800):
    path=live/(label+'.log')
    remaining=min(deadline,until-time.time())
    if remaining<=0:raise RuntimeError('ATTACH_WORK_DEADLINE')
    write(live/(label+'-command-bound.json'), {'requestedSeconds':deadline, 'effectiveSeconds':remaining,
          'originalWorkUntil':dl['workUntil'], 'safetyMarginSeconds':5})
    with path.open('xb') as f:
        result=subprocess.run([str(x) for x in args],stdout=f,stderr=subprocess.STDOUT,timeout=remaining)
    if result.returncode:
        detail=sorted(set(re.findall(r'\b(?:K8S_|M7_|PRIMER_)[A-Z_]{2,88}',path.read_text(errors='replace')[-2500:])))
        write(live/'attachment-refusal.json',{'stage':label,'exit':result.returncode,'codes':detail})
        raise RuntimeError('ATTACH_'+label)
    return path
def observe_selected_bootstrap(packet, runtime, namespace_uid, adapter_cmd, execute):
    pins = read(packet/'run.json')['pins']['candidate']
    helper = pins.get('runtimeBootstrapHelper')
    actual = read(runtime/'bootstrap-helper-readback.json')
    if actual.get('effectiveInstanceAcceptance') != pins['sourceAcceptance']:
        raise RuntimeError('K8S_BOOTSTRAP_ACCEPTANCE_CHANGED')
    if helper is None:
        if actual.get('mode') != 'embedded-image':
            raise RuntimeError('K8S_BOOTSTRAP_HELPER_UNDECLARED')
    else:
        if actual.get('mode') != 'diagnostic-overlay' or actual.get('sha256') != helper['sha256']:
            raise RuntimeError('K8S_BOOTSTRAP_HELPER_MISSING_OR_CHANGED')
        execute('bootstrap-map', adapter_cmd+['bootstrap-map', packet, namespace_uid])
    execute('observe', adapter_cmd+['observe', packet])
    execute('candidate-proof', adapter_cmd+['candidate-proof', packet])
    execute('policy', adapter_cmd+['policy', packet])

exp=[sys.executable,'-B',K/'experiment.py'];ad=[sys.executable,'-B',K/'adapter.py']
obj=read(live/'latest-edge.json');edge=obj['name'];edgeuid=obj['uid']
kub=[cfg['kubectl'],'--context',cfg['context'],'-n',ns]
def edge_id():return subprocess.check_output(kub+['get','pod',edge,'-o','jsonpath={.metadata.uid}'],timeout=12).decode()
assert edge_id()==edgeuid
forward_log=live/'forward.log';packet=live/'packet'; apiport=control.get('edgePort',8080)
forward=None
try:
    log=forward_log.open('xb');forward=subprocess.Popen(kub+['port-forward','--address','127.0.0.1','pod/'+edge,':'+str(apiport)],stdout=log,stderr=subprocess.STDOUT)
    begin=time.monotonic()
    while time.monotonic()-begin<22 and forward.poll() is None:
        match=re.search(r'Forwarding from 127\.0\.0\.1:(\d+) -> '+str(apiport),forward_log.read_text())
        if match:break
        time.sleep(.2)
    else:raise RuntimeError('EDGE_FORWARD_UNAVAILABLE')
    assert edge_id()==edgeuid
    cfg['baseUrl']='http://127.0.0.1:'+match[1]
    write(live/'input.json',cfg)
    instance={'config':str(live/'input.json'),'inventory':str(d/'inventory.json'),'render':str(d/'render.json'),
              'bindingReceipt':ref(Path(control['bindingDirectory'])/'binding.json'),'delivery':control['delivery'],
              'roleDocuments':{role:str(live/(role+'-config.private.json')) for role in ('evaluator','realtime')}}
    instance['roleDocuments']['nativeReceipt']=str(live/'native-receipt-source.private.json')
    if (live/'platform-verification.json').exists():
        instance['verificationProof']=ref(live/'platform-verification.json')
    if 'pgstreamNotifierAckTimeoutMs' in m:
        instance['producerAckReadback']=ref(live/'producer-ack-readback.json')
    if 'primerStorage' in m:
        instance['primerStorageReceipt']=ref(live/'primer-storage-published.json')
    write(live/'instance.json',instance)
    execute('prepare',exp+['prepare',d/'intent.json',live/'instance.json',packet,'--await-primer'])
    observe_selected_bootstrap(packet, live, uid, ad, execute)
    primer_args=[] if control.get('primerOptionsPreflight') else ['--concurrency',str(control['primerConcurrency'])]
    execute('prime',[sys.executable,'-B',K/'primer.py',packet,packet/'primer',*primer_args],
            until-time.time())
    assert read(packet/'primer/result.json')['verdict']=='OBSERVED'
    # Capture read-only SQL independently of optional client measurements.
    try:execute('sql',ad+['observe-sql',packet,live/'sql'],120)
    except RuntimeError:pass
    execute('access',ad+['access',packet],65)
    pre=read(d/'preflight.json');profile=m['profile']
    actor=cfg['driver']['hostId']
    assert actor==cfg['observer']['hostId']
    mode=cfg.get('resourceAccounting','limits-v1')
    assert mode in ('limits-v1','requests-v1') and pre['trialEnvelope'].get('resourceAccounting','limits-v1')==mode,'RESOURCE_ACCOUNTING_MISMATCH'
    grant={'version':1,'status':'RELEASED','existingCapacityOnly':True,'context':cfg['context'],**cfg['deadlines'],
           'resourceAccounting':mode,
           'preflight':ref(d/'preflight.json'),'experimentSha256':sha(d/'intent.json'),'placementMode':'scheduler',
           'fixtures':[{'runId':e['runId'],'namespace':ns,'namespaceUid':uid,'runSha256':sha(packet/'run.json')}]}
    write(live/'grant.json',grant)
    execute('load',exp+['run',packet,live/'grant.json',sha(live/'grant.json')],until-time.time())
finally:
    if forward and forward.poll() is None:
        forward.terminate()
        try:forward.wait(timeout=8)
        except subprocess.TimeoutExpired:forward.kill();forward.wait()
    if forward:write(live/'forward-closed.json',{'pid':forward.pid,'returncode':forward.returncode,'podUid':edgeuid})
