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
cfg.update(context=e['context'],runId=e['runId'],namespace=ns,tenants=e['tenantCount'],deadlines={k:v.replace('+00:00','Z') for k,v in dl.items()})
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
    import fixture
    import kube_adapter as k
    private = live/'fixture'
    location = 'pod' if m['primerLocation'] == 'controller' else m['primerLocation']
    inventory = read(d/'inventory.json')
    primer = next(obj for obj in k.manifests(read(d/'render.json')) if k.key(obj) == 'Job/primer')
    held = read(live/'fixture-reader.json') if (live/'fixture-reader.json').exists() else None
    tenants, reuse = fixture.read_roster(kub, primer, inventory, private, cfg['tenants'], until, location, held)
    from populated_history import BASELINE, run as prepare_history
    if len(sys.argv) == 3 and sys.argv[2] == '--seed-history':
        pg = read(live/'latest-postgres.json')
        client = k.Client(cfg)
        def sql(query):
            def uid():
                return client.call(['get','pod',pg['name'],'-o','jsonpath={.metadata.uid}']).decode()
            if uid() != pg['uid']:
                raise RuntimeError('K8S_HISTORY_POSTGRES_CHANGED')
            result = k.postgres_read(client, pg['name'], cfg['roles']['postgres']['container'], query)
            if uid() != pg['uid']:
                raise RuntimeError('K8S_HISTORY_POSTGRES_CHANGED')
            return result
        write(live/'populated-history.json', prepare_history(m['profile']['history'], tenants, cfg['baseUrl'],
                                                            sql, until, 0))
        raise SystemExit(0)
    if control.get('fixture', {}).get('mode') == 'restore' and m['profile']['history'] != BASELINE:
        cfg['restoredHistory'] = True
    cfg['tenantsFile'] = str(private/'data-roster.private.json')
    write(Path(cfg['tenantsFile']), tenants)
    write(live/'fixture.json', {'location':location,'reuse':reuse,'tenants':len(tenants)})
    instance={'config':str(live/'input.json'),'inventory':str(d/'inventory.json'),'render':str(d/'render.json'),
              'binding':control['bindingDirectory']}
    write(live/'instance.json',instance)
    selected = control['candidate']
    pair = {'core':selected['coreCommit'], 'deploy':selected['deployCommit']}
    cfg['completion'] = fixture.completion(kub,cfg['roles'],pair,selected['appImageId'],k.instrument()['sha256'])
    write(live/'input.json',cfg)
    execute('prepare',exp+['prepare',d/'intent.json',live/'instance.json',packet])
    execute('observe',ad+['observe',packet])
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
