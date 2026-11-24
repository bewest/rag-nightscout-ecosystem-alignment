"""Attach the exact released native runner in the fixture's inherited, finite cgroup."""
import datetime as dt,hashlib,json,os,re,socket,subprocess,sys,time
from pathlib import Path
from lifecycle_config import fixture_config
control=fixture_config(Path(sys.argv[1]))
d=Path(control['caseDirectory'])
runtime=d/'runtime'
point = sys.argv[3] if len(sys.argv) == 4 and sys.argv[2] == '--point' else None
if point is not None and (not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,30}', point) or point not in control['loadPoints']):
    raise ValueError('K8S_POINT_UNKNOWN')
source = d/'points'/point if point else d
live = runtime/'points'/point if point else runtime
if point:
    live.mkdir(mode=0o700, parents=True, exist_ok=False)
K=Path(__file__).resolve().parent
read=lambda f:json.loads(f.read_bytes())
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n');p.chmod(0o600)
def ref(p):return {'path':str(p),'sha256':sha(p)}
e=read(d/'environment.json');m=read(source/'intent.json');ns=e['namespace'];uid=read(runtime/'custody.json')['namespaceUid'];now=time.time()
dl=read(runtime/'deadlines.json');until=dt.datetime.fromisoformat(dl['workUntil']).timestamp()-5
os.umask(0o077)
base=source/'native-run-template.json' if point else Path(control['runTemplate']['path'])
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
        if label == 'load' and point and phase_actors.scored_failure(packet):
            return path
        detail=sorted(set(re.findall(r'\b(?:K8S_|M7_|PRIMER_)[A-Z_]{2,88}',path.read_text(errors='replace')[-2500:])))
        write(live/'attachment-refusal.json',{'stage':label,'exit':result.returncode,'codes':detail})
        raise RuntimeError('ATTACH_'+label)
    return path
HISTORY_READ_SECONDS=int(os.environ.get('K8S_HISTORY_READ_SECONDS','900'))
exp=[sys.executable,'-B',K/'experiment.py'];ad=[sys.executable,'-B',K/'adapter.py']
obj=read(runtime/'latest-edge.json');edge=obj['name'];edgeuid=obj['uid']
kub=[cfg['kubectl'],'--context',cfg['context'],'-n',ns]
def edge_id():return subprocess.check_output(kub+['get','pod',edge,'-o','jsonpath={.metadata.uid}'],timeout=12).decode()
assert edge_id()==edgeuid
forward_log=live/'forward.log';packet=live/'packet'; apiport=control.get('edgePort',8080)
forward=None
import edge_access
service=subprocess.check_output(kub+['get','service','edge','-o','jsonpath={.spec.clusterIP} {.spec.ports[0].port}'],timeout=12).decode().split()
direct=edge_access.base_url(cfg['context'],ns,int(service[1]),service[0])
try:
    if direct:
        # In-cluster controller: the edge Service, no port-forward (edge_access.py).
        write(live/'edge-access.json',{'mode':'service','baseUrl':direct,'podUid':edgeuid})
        cfg['baseUrl']=direct
    else:
        log=forward_log.open('xb');forward=subprocess.Popen(kub+['port-forward','--address','127.0.0.1','pod/'+edge,':'+str(apiport)],stdout=log,stderr=subprocess.STDOUT)
        begin=time.monotonic()
        while time.monotonic()-begin<22 and forward.poll() is None:
            match=re.search(r'Forwarding from 127\.0\.0\.1:(\d+) -> '+str(apiport),forward_log.read_text())
            if match:break
            time.sleep(.2)
        else:raise RuntimeError('EDGE_FORWARD_UNAVAILABLE')
        cfg['baseUrl']='http://127.0.0.1:'+match[1]
    assert edge_id()==edgeuid
    import fixture
    import kube_adapter as k
    private = runtime/'fixture'
    location = 'pod' if m['primerLocation'] == 'controller' else m['primerLocation']
    inventory = read(d/'inventory.json')
    primer = next(obj for obj in k.manifests(read(source/'render.json')) if k.key(obj) == 'Job/primer')
    held = read(runtime/'fixture-reader.json') if (runtime/'fixture-reader.json').exists() else None
    prior = None
    if point:
        import phase_actors
        import native_join
        k.need(m['profile']['workload'].get('pointId') == point, 'POINT_MARKER_CHANGED')
        api = fixture.runner(kub, until)
        claim = inventory['storage']['claims']['postgres']
        storage = phase_actors.storage_identity(api, ns, uid, e['runId'], claim)
        position = control['loadPoints'].index(point)
        if position:
            previous = control['loadPoints'][position-1]
            prior = read(runtime/'points'/previous/'phase-identity.json')
            k.need(prior['pointId'] == previous, 'POINT_PREDECESSOR_CHANGED')
            job, = (obj for obj in k.manifests(read(source/'render.json')) if k.key(obj) == native_join.JOB)
            job_uid = phase_actors.new_job(api, ns, e['runId'], storage, prior, job, until)
        else:
            job_uid = phase_actors.owned_uid(api, 'job', 'k6', e['runId'])
    roster = private/'data-roster.private.json'
    if prior:
        k.need(sha(roster) == prior['rosterSha256'], 'POINT_FIXTURE_ROSTER_CHANGED')
        tenants = read(roster)
        reuse = read(runtime/'fixture.json')['reuse']
    else:
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
            # The history readback scans every stored document (about 2 min at 10k tenants); it gets
            # its own limit inside the work deadline, not the adapter's 20 s observation default.
            result = k.postgres_read(client, pg['name'], cfg['roles']['postgres']['container'], query,
                                     timeout=max(1, min(HISTORY_READ_SECONDS, until - time.time())))
            if uid() != pg['uid']:
                raise RuntimeError('K8S_HISTORY_POSTGRES_CHANGED')
            return result
        write(live/'populated-history.json', prepare_history(m['profile']['history'], tenants, cfg['baseUrl'],
                                                            sql, until, 0))
        raise SystemExit(0)
    if control.get('fixture', {}).get('mode') == 'restore' and m['profile']['history'] != BASELINE:
        cfg['restoredHistory'] = True
        # Reuse runs no history census: the fixture record's import-time readback digest stands for it.
        record = read(Path(control['fixture']['directory'])/'fixture.json')
        assert record.get('history') == m['profile']['history'], 'RESTORED_HISTORY_SPEC_CHANGED'
        cfg['restoredFixture'] = {'catalog': control['fixture'].get('digest'), 'fixtureId': record.get('fixtureId'),
                                  'historyLogicalSha256': record.get('historyLogicalSha256'),
                                  'archiveSha256': (record.get('archive') or {}).get('sha256')}
    cfg['tenantsFile'] = str(roster)
    if not prior:
        write(roster, tenants)
        write(runtime/'fixture.json', {'location':location,'reuse':reuse,'tenants':len(tenants)})
    instance={'config':str(live/'input.json'),'inventory':str(d/'inventory.json'),'render':str(source/'render.json'),
              'binding':control['bindingDirectory']}
    write(live/'instance.json',instance)
    selected = control['candidate']
    pair = {'core':selected['coreCommit'], 'deploy':selected['deployCommit']}
    cfg['completion'] = fixture.completion(kub,cfg['roles'],pair,selected['appImageId'],k.instrument()['sha256'])
    write(live/'input.json',cfg)
    execute('prepare',exp+['prepare',source/'intent.json',live/'instance.json',packet])
    execute('observe',ad+['observe',packet])
    # Capture read-only SQL independently of optional client measurements.
    try:execute('sql',ad+['observe-sql',packet,live/'sql'],120)
    except RuntimeError:pass
    execute('access',ad+['access',packet],65)
    pre=read(source/'preflight.json');profile=m['profile']
    actor=cfg['driver']['hostId']
    assert actor==cfg['observer']['hostId']
    mode=cfg.get('resourceAccounting','limits-v1')
    assert mode in ('limits-v1','requests-v1') and pre['trialEnvelope'].get('resourceAccounting','limits-v1')==mode,'RESOURCE_ACCOUNTING_MISMATCH'
    grant={'version':1,'status':'RELEASED','existingCapacityOnly':True,'context':cfg['context'],**cfg['deadlines'],
           'resourceAccounting':mode,
           'preflight':ref(source/'preflight.json'),'experimentSha256':sha(source/'intent.json'),'placementMode':'scheduler',
           'fixtures':[{'runId':e['runId'],'namespace':ns,'namespaceUid':uid,'runSha256':sha(packet/'run.json')}]}
    write(live/'grant.json',grant)
    execute('load',exp+['run',packet,live/'grant.json',sha(live/'grant.json')],until-time.time())
    if point:
        record = read(packet/'load/native-load.json')
        marker = native_join.stage_runid(read(packet/'run.json'))
        k.need(record.get('capture') == 'CAPTURED' and record['process']['complete'] and
               (packet/'load/runid').read_text().strip() == record['runId'] == marker and
               record['namespaceUid'] == uid and record['jobUid'] == job_uid and
               record['inputSecretUid'] == phase_actors.owned_uid(api, 'secret', 'ns-k6-inputs', e['runId']),
               'POINT_NATIVE_CAPTURE_CHANGED')
        k.need(storage == phase_actors.storage_identity(api, ns, uid, e['runId'], claim), 'POINT_RESTORE_CHANGED')
        write(live/'phase-identity.json', {**storage, 'pointId':point, 'marker':marker, 'jobUid':job_uid,
            'inputSecretUid':record['inputSecretUid'], 'rosterSha256':sha(roster),
            'verdict':read(packet/'experiment/result.json')['verdict']})
except Exception as error:
    if point:
        # Subprocess errors can include private command arguments. Retain only the refusal code.
        code = str(error)
        write(live/'phase-failure.json', {'pointId': point, 'code': code if re.fullmatch(
            r'(?:K8S_|M7_|ATTACH_)[A-Za-z0-9_:-]+', code) else type(error).__name__})
    raise
finally:
    if forward and forward.poll() is None:
        forward.terminate()
        try:forward.wait(timeout=8)
        except subprocess.TimeoutExpired:forward.kill();forward.wait()
    if forward:write(live/'forward-closed.json',{'pid':forward.pid,'returncode':forward.returncode,'podUid':edgeuid})
