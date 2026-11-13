"""Commission only: real entrypoint/health/normal retirement, never clinical acceptance.

prepare/dry-run are host-file/model-only. run allocates the exact reviewed project;
its use requires the coordinator's separate authorization. No implicit retries.
"""
import argparse,hashlib,json,os,re,sys,time
from pathlib import Path
import owned_process as O,preflight as P
CORE='074eab44ee75b9175c951b6a8add3df3e9554af7';DEPLOY='3d13c63bc404397d6daee501c152288b12d5931d'
IMAGE='sha256:32b7f3eabc915d7eaa939cd06a2d1277a162ec86cff04b1b6c65ad33c15a3a4f'
QUALIFICATION='7f1a2716ae5b88678c76bbcc000c90e1d553ade65b38cc1cd6542e7b10e6675e'
COLLECTOR='356c7dfdaadc885ab5b42f887748e18017d0e8f69fc23017b1b16773bd151e66'
ROLES=['admin','api','api-2'];PG_IMAGE='sha256:81bd698b4594e751a3269e4dcd3e03a4a0ec0daf7b72e7aa1abd43cce9887542'
VAULT='hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2'
def need(value,code):
    if not value:raise RuntimeError(code)
def sha(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()
def read(file):
    fd=os.open(file,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        import stat
        meta=os.fstat(fd);need(stat.S_ISREG(meta.st_mode)and not meta.st_mode&0o077 and meta.st_size<=1048576,'PRIVATE_INPUT');data=os.read(fd,1048577);need(len(data)<=1048576,'PRIVATE_INPUT');return json.loads(data)
    finally:os.close(fd)
def save(file,value):
    with open(file,'x',opener=lambda p,f:os.open(p,f,0o600))as out:json.dump(value,out,indent=2);out.write('\n')
def prepare(root):
    root=Path(root).resolve();i=read(root/'source-input.private.json');q=read(root/'image-build/qualification.json');report=read(root/'profile-generation-final/source-profile.private.json');config=read(root/'state/connection-budget/controller-config.json');profile=read(root/'state/connection-budget/profile.json')
    source={'coreCommit':CORE,'deployCommit':DEPLOY};need(all(x==source for x in [i['source'],report['source'],config['source'],profile['source'],{k:q['source'][k]for k in source}]),'SOURCE_PIN')
    need(q['authorization']=='BUILD_QUALIFIED_NOT_LAUNCH_AUTHORIZATION'and q['imageId']==IMAGE and sha(root/'image-build/qualification.json')==QUALIFICATION,'BUILD_QUALIFICATION')
    need(config['project']=='ns-admission-'+i['nonce']and config['image']==q['imageTag'],'PREPARED_PROJECT_IMAGE')
    need(profile['resource']['serverMaximum']==report['derivedMaximum']and len(profile['slots'])==11,'DECLARED_PROFILE')
    expected_env={'NS_API_REPLICAS':'2','NS_REALTIME_WORKERS':'2','NS_REALTIME_SHARDS':'4','NS_EVALUATOR_WORKERS':'2','NS_DEMO_TENANTS':'16','NS_TENANT_STARTUP_CONCURRENCY':'4','NS_TENANT_READINESS':'serve','NS_OPERATION_LEASE_SESSIONS':'4'}
    need(report['selectedEnvironment']==expected_env and report['derivedMaximum']==314,'DECLARED_ENV_CHANGED')
    expected_profile=json.loads(json.dumps(report['profile']));expected_profile['resource']['serverMaximum']=report['derivedMaximum'];need(expected_profile==profile,'PROFILE_CHANGED')
    need(report['generatorSha256']==sha(Path(__file__).with_name('profile.cjs')),'PROFILE_GENERATOR_CHANGED')
    env=dict(line.split('=',1)for line in (root/'source/deploy/multitenant/.env').read_text().splitlines()if line)
    need(env['NS_DEMO_STATE']==str(root/'state')and env['NS_DEMO_PROJECT']==config['project'],'PREPARED_ENV')
    for file,digest in config['fileDigests'].items():need(sha(file)==digest,'PREPARED_FILE_CHANGED')
    collector=Path(__file__).resolve().parent.parent/'tagged-admission';files={n:sha(collector/n)for n in ('tagged_admission.py','tagged_capture.py','test_tagged_admission.py','test_tagged_capture.py','tagged-admission.md')};fingerprint=hashlib.sha256(json.dumps({'kind':'m7-tagged-admission-observation-v1','files':files},sort_keys=True,separators=(',',':')).encode()).hexdigest();need(fingerprint==COLLECTOR,'COLLECTOR_PIN')
    base=root/'source/deploy/multitenant';cli=base/'connection-budget-cli.js'
    network=re.search(r'\nnetworks:\n  backend:\n    ipam:\n      config:\n        - subnet: ([0-9./]+)\n  edge:\n    ipam:\n      config:\n        - subnet: ([0-9./]+)\n\Z',(root/'state/compose.replicas.yaml').read_text());need(network is not None and env['NS_DEMO_BIND']=='127.0.0.1','PREPARED_NETWORK_BIND');backend,edge=network.groups();P.subnet(backend);P.subnet(edge)
    return {'kind':'m7-admission-commissioning-v1','source':source,'nonce':i['nonce'],'root':str(root),'state':str(root/'state'),'base':str(base),'project':config['project'],'imageId':q['imageId'],'imageTag':q['imageTag'],'qualificationFile':str(root/'image-build/qualification.json'),'qualificationSha256':sha(root/'image-build/qualification.json'),'controllerCli':str(cli),'controllerCliSha256':sha(cli),'collector':str(collector/'tagged_capture.py'),'collectorSha256':COLLECTOR,'config':config,'selectedEnvironment':report['selectedEnvironment'],'backendSubnet':backend,'edgeSubnet':edge,'port':int(env['NS_DEMO_PORT']),'maximumBackendEndpoints':len(profile['slots'])+4,'maximumEdgeEndpoints':1,'workers':ROLES,'maximumSeconds':900,'cleanupReserveSeconds':90,'maximumCommands':384,'cleanupReserveCommands':64,'maximumOutputBytes':33554432,'cleanupReserveOutputBytes':8388608,'maximumCollectorCalls':3,'maximumCollectorCommands':15,'maximumCollectorRawInternalBytes':50331648,'maximumCollectorParentOutputBytes':6291456,'episodeFiles':{name:sha(Path(__file__).with_name(name))for name in ('commissioning.py','owned_process.py','preflight.py','profile.cjs','recording.py','cleanup.py')},'nativeAcceptance':'UNMEASURED','scope':'commissioning wiring/health/normal retirement only; no tenant/data provisioning, cold/storm, healthy-B, TIME, isolation or stored-count oracle','commands':[['infrastructure-up',['postgres','vault']],['infrastructure-health',[]],['bootstrap-once',[]],['controller-bind',[]],['controller-start',['admin','api','api-2']],['actual-health-existing-claims',[]],['tagged-capture',['started']],['controller-stop',['api']],['verify-ack-retired',['api']],['controller-start',['api']],['actual-health-existing-claims',['api']],['tagged-capture',['restarted']],['controller-stop',['api','api-2','admin']],['verify-ack-retired',['api','api-2','admin']],['tagged-capture',['retired']],['finally-capture-exact-owned-stop',[]]]}
class Host:
    def __init__(self,plan,output):
        self.p=plan;self.out=Path(output);self.out.mkdir(mode=0o700);self.n=0;self.bytes=0;self.deadline=time.monotonic()+plan['maximumSeconds'];self.cleanup=False;self.uncertain=False;self.allocation_attempted=False;self.owned={};self.images={'postgres':PG_IMAGE};self.environment={k:os.environ[k]for k in ['PATH','HOME','USER','LANG']if k in os.environ};self.environment.update(plan['selectedEnvironment']);self.environment['NS_DEMO_IMAGE']=plan['imageId'];self.environment['NODE_PATH']='/tmp/ns-api-final-acceptance-20261112/deps/node_modules'
    def command(self,args,seconds=30,allow_failure=False):
        need(self.n<(self.p['maximumCommands']if self.cleanup else self.p['maximumCommands']-self.p['cleanupReserveCommands']),'COMMAND_COUNT');self.n+=1;remaining=self.deadline-time.monotonic()-(0 if self.cleanup else self.p['cleanupReserveSeconds']);need(remaining>5,'EPISODE_DEADLINE');budget=self.p['maximumOutputBytes']-self.bytes-(0 if self.cleanup else self.p['cleanupReserveOutputBytes']);need(budget>=4096,'EPISODE_OUTPUT_BOUND')
        prior_uncertainty=self.uncertain;self.uncertain=True # sticky while execution/receipt is unresolved
        r=O.run(args,self.environment,self.out/('%03d'%self.n),min(seconds,remaining-4),min(2097152,budget));self.bytes+=r['bytes']
        failed=r['failure']is not None or r['returnCode']!=0
        save(self.out/('%03d-result.json'%self.n),r)
        self.uncertain=prior_uncertainty or failed
        if not allow_failure:need(r['failure']is None and r['returnCode']==0,'COMMAND_FAILED')
        return Path(r['stdout']).read_text()if r['returnCode']==0 and not r['failure']else None
    def compose(self,*args,**kwargs):
        c=self.p['config'];
        for file,digest in c['fileDigests'].items():need(sha(file)==digest,'PREPARED_FILE_CHANGED')
        return self.command(['docker','compose','--project-directory',self.p['base'],'--project-name',self.p['project'],'--env-file',str(Path(self.p['base'])/'.env'),*[x for f in c['composeFiles']for x in ['-f',f]],*args],**kwargs)
    def inspect(self,cid,service):
        rows=json.loads(self.command(['docker','inspect',cid]));need(len(rows)==1,'INSPECT_BOUND');r=rows[0];l=r['Config'].get('Labels')or{};need(r['Id']==cid and l.get('com.docker.compose.project')==self.p['project']and l.get('com.docker.compose.project.working_dir')==self.p['base']and l.get('com.docker.compose.service')==service,'CONTAINER_CUSTODY');need(r['Image']==self.images.get(service,self.p['imageId']),'CONTAINER_IMAGE');identity=(service,r['State']['StartedAt'],r['Image']);need(cid not in self.owned or self.owned[cid]==identity,'CONTAINER_STARTEDAT_CHANGED');self.owned[cid]=identity;return r
    def service(self,service):
        ids=self.compose('ps','-a','-q',service).split();need(len(ids)==1 and re.fullmatch('[a-f0-9]{64}',ids[0]),'SERVICE_ROSTER');return self.inspect(ids[0],service)
    def healthy(self,service):
        first=self.service(service);deadline=min(self.deadline-90,time.monotonic()+90)
        while True:
            r=self.inspect(first['Id'],service);need(r['State']['StartedAt']==first['State']['StartedAt']and r['State']['Running'],'HEALTH_PROCESS_CHANGED');status=r['State'].get('Health',{}).get('Status')
            if status=='healthy'and time.monotonic()<=deadline:return r
            need(status in ('starting','unhealthy')and time.monotonic()<deadline,'HEALTH_NOT_READY');time.sleep(2)
    def controller(self,op,slot=None,seconds=60):
        value=json.loads(self.command(['node',self.p['controllerCli'],self.p['state'],op,*([slot]if slot else[])],seconds));need(value.get('state')=={'bind':'BOUND','start':'STARTED','stop':'QUIESCED_RETIRED'}[op]and(op=='bind'or value.get('processInstanceId')==slot),'CONTROLLER_RESULT')
        if op=='bind':
            custody=read(Path(self.p['state'])/'connection-budget/custody.json');need(custody.get('expected')=={'project':self.p['project'],'workingDirectory':self.p['base'],'imageId':self.p['imageId'],'source':self.p['source']},'BOUND_CUSTODY_MISMATCH')
        return value
    def capture(self,label):
        plan=read(Path(self.p['state'])/'connection-budget/plan.json');book=read(Path(self.p['state'])/'connection-budget/ledger.json');need(all(sid in ROLES or not any(r['state']!='RETIRED'for r in rows)for sid,rows in book['slots'].items())and sum(r['state']!='RETIRED'for rows in book['slots'].values()for r in rows)<=3,'COMMISSION_UNPLANNED_GENERATION');need(plan['source']==self.p['source'],'BOUND_PLAN_SOURCE');spec={'kind':'m7-tagged-admission-observation-v1','controllerCli':self.p['controllerCli'],'controllerCliSha256':self.p['controllerCliSha256'],'collectorSha256':self.p['collectorSha256'],'state':self.p['state'],'expected':{'kind':'m7-tagged-admission-observation-v1','source':self.p['source'],'imageId':self.p['imageId'],'project':self.p['project'],'workingDirectory':self.p['base'],'planSha256':plan['sha256']}};file=self.out/(label+'-capture-spec.private.json');save(file,spec);self.command(['python3',self.p['collector'],str(file),str(self.out/(label+'-capture'))],125)
    def ack(self,slot):
        plan=read(Path(self.p['state'])/'connection-budget/plan.json');book=read(Path(self.p['state'])/'connection-budget/ledger.json');row=book['slots'][slot][-1];ack=read(Path(self.p['state'])/'connection-budget'/slot/'claims'/('ack-'+row['incarnation']+'.json'));need(row['state']=='RETIRED'and ack['incarnation']==row['incarnation']and ack['nonce']==row['nonce']and ack['source']==self.p['source']and ack['planSha256']==plan['sha256']and ack['constructorsFrozen']is True and ack['pendingConnects']==ack['liveConnections']==0 and ack['unconfirmedCleanup']is False and ack['cleanShutdown']is True and sorted(ack['tags'])==sorted(row['tags']),'ACK_RETIREMENT');save(self.out/(slot+'-'+row['incarnation']+'-ack.private.json'),ack)
    def explicit_health(self,slot):
        claims=Path(self.p['state'])/'connection-budget'/slot/'claims'
        before={file.name:sha(file)for file in claims.glob('claim-*')};r=self.healthy(slot)
        need(not any(x.split('=',1)[0]in ('NODE_OPTIONS','NODE_PATH','LD_PRELOAD','NS_ENV_FILE')and x.split('=',1)[-1]for x in r['Config'].get('Env',[])),'HEALTH_PRELOAD_ENV')
        self.command(['docker','exec',r['Id'],'node','deploy/multitenant/health.js','api'if slot.startswith('api')else slot])
        after={file.name:sha(file)for file in claims.glob('claim-*')};need(before==after and len(before)>0,'HEALTH_TICKET_CLAIM_CHANGED')

    def cleanup_owned(self):
        self.cleanup=True;errors=[]
        save(self.out/'root-cleanup-spec.private.json',{'kind':'m7-commission-exact-owned-cleanup-v1','plan':self.p,'allocationAttempted':self.allocation_attempted,'images':self.images,'known':self.owned})
        if not self.allocation_attempted:
            save(self.out/'finally-no-allocation.json',{'allocationAttempted':False,'cleanupEffects':0});return
        if not getattr(self,'skip_controller_cleanup',False):
            for slot in reversed(ROLES):
                try:
                    ids=self.compose('ps','-a','-q',slot).split()
                    if ids and self.inspect(ids[0],slot)['State']['Running']:self.controller('stop',slot,seconds=15)
                except Exception as e:errors.append({'stage':'controller-stop','service':slot,'error':str(e)})
        candidates=set(self.owned)
        try:candidates.update(self.command(['docker','ps','-aq','--no-trunc','--filter','label=com.docker.compose.project='+self.p['project']]).split())
        except Exception as e:errors.append({'stage':'discover','error':str(e)})
        all_ids=None
        try:
            all_ids=set(self.command(['docker','ps','-aq','--no-trunc'],5).split());need(len(all_ids)<=512 and all(re.fullmatch('[a-f0-9]{64}',cid)for cid in all_ids),'CLEANUP_ROSTER_BOUND')
        except Exception as e:errors.append({'stage':'full-roster','error':str(e)});all_ids=None
        rows=[];final=[];absent=[]
        for cid in sorted(candidates):
            try:
                need(re.fullmatch('[a-f0-9]{64}',cid),'CLEANUP_CID')
                if cid in self.owned and all_ids is not None and cid not in all_ids:
                    absent.append({'cid':cid,'originalIdentity':self.owned[cid],'proof':'SUCCESSFUL_BOUNDED_FULL_DOCKER_ROSTER_ABSENCE','creditRetirement':'NOT_GRANTED'});continue
                raw=json.loads(self.command(['docker','inspect',cid],5))[0];service=(raw['Config'].get('Labels')or{}).get('com.docker.compose.service')
                need(service in ROLES+['postgres','vault','bootstrap'],'CLEANUP_FOREIGN_SERVICE');r=self.inspect(cid,service);rows.append(r)
            except Exception as e:errors.append({'stage':'inspect','cid':cid,'error':str(e)});continue
            try:self.command(['docker','logs','--tail','100',cid],5,allow_failure=True)
            except Exception as e:errors.append({'stage':'logs','cid':cid,'error':str(e)})
            try:
                if r['State']['Running']:
                    self.inspect(cid,service) # exact original StartedAt before effect
                    self.command(['docker','stop','--time','10',cid],15)
                after=self.inspect(cid,service);need(not after['State']['Running'],'CLEANUP_RUNNING');final.append(after)
            except Exception as e:errors.append({'stage':'stop-or-confirm','cid':cid,'error':str(e)});continue
        save(self.out/'finally-owned-inspection.private.json',rows)
        save(self.out/'finally-stopped.private.json',{'errors':errors,'uncertainHostEffect':self.uncertain,'rows':final,'knownAbsent':absent,'creditRetirement':'NEVER_INFERRED_FROM_CLEANUP','lateDaemonEffect':'UNCONFIRMED'if self.uncertain else'NO_HOST_COMMAND_UNCERTAINTY'})
        need(not errors and len(final)+len(absent)==len(candidates)and not self.uncertain,'CLEANUP_UNCONFIRMED')

def execute(plan,output,host_type=Host):
    need(plan==prepare(plan['root']),'PLAN_CHANGED')
    h=host_type(plan,output);recording=host_type is not Host;result={'kind':plan['kind'],'nativeAcceptance':'UNMEASURED','commissioning':'NOT_RUN','scope':plan['scope']};save(h.out/'plan.private.json',plan)
    try:
        pre=P.read_host(plan,h.command);save(h.out/'host-preflight.private.json',pre)
        for file,digest in plan['config']['fileDigests'].items():need(sha(file)==digest,'PREPARED_FILES_CHANGED')
        need(sha(plan['controllerCli'])==plan['controllerCliSha256']and sha(plan['qualificationFile'])==plan['qualificationSha256'],'SOURCE_OR_QUALIFICATION_CHANGED')
        for ref,service in [(PG_IMAGE,'postgres'),(VAULT,'vault'),(plan['imageId'],'app')]:
            rows=json.loads(h.command(['docker','image','inspect',ref]));need(len(rows)==1 and rows[0]['Os']=='linux'and rows[0]['Architecture']=='amd64','IMAGE_PLATFORM');h.images[service]=rows[0]['Id']
        need(h.images['app']==plan['imageId'],'APP_IMAGE');need(time.monotonic_ns()-pre['observedMonotonicNs']<5000000000,'PREFLIGHT_EXPIRED')
        h.allocation_attempted=True
        h.compose('up','--no-deps','--no-build','--pull','never','-d','postgres','vault');h.healthy('postgres');h.healthy('vault');h.compose('--profile','ops','run','--rm','--no-deps','bootstrap',seconds=240);h.controller('bind')
        for slot in ROLES:h.controller('start',slot);h.explicit_health(slot)
        h.capture('started');h.controller('stop','api');h.ack('api');h.controller('start','api');h.explicit_health('api');h.capture('restarted')
        for slot in reversed(ROLES):h.controller('stop',slot);h.ack(slot)
        h.capture('retired');result['commissioning']='NOT_RUN'if recording else'PASS';result['dryRun']='PASS'if recording else'NOT_APPLICABLE'
    except Exception as e:result.update(commissioning='FAIL',error=str(e))
    finally:
        try:h.cleanup_owned()
        except Exception as e:result.update(commissioning='FAIL',cleanupError=str(e))
        result.update(commands=h.n,outputBytes=h.bytes,uncertainHostEffect=h.uncertain);save(h.out/'result.private.json',result)
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['prepare','preflight','dry-run','run']);parser.add_argument('input',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    try:
        if args.operation=='prepare':args.output.mkdir(mode=0o700);save(args.output/'commission-plan.private.json',prepare(args.input));print('COMMISSIONING_PLAN_PREPARED_NOT_LAUNCH_AUTHORIZATION')
        elif args.operation=='preflight':
            plan=read(args.input);need(plan==prepare(plan['root']),'PLAN_CHANGED');h=Host(plan,args.output);save(h.out/'host-preflight.private.json',P.read_host(plan,h.command));print('READ_ONLY_PREFLIGHT_NO_ALLOCATION')
        elif args.operation=='dry-run':
            from recording import RecordingHost
            result=execute(read(args.input),args.output,RecordingHost);print(json.dumps(result));sys.exit(0 if result.get('dryRun')=='PASS'else 1)
        else:result=execute(read(args.input),args.output);print(json.dumps({k:v for k,v in result.items()if k not in ('scope',)}));sys.exit(0 if result['commissioning']=='PASS' else 1)
    except Exception as error:print(json.dumps({'error':str(error),'nativeAcceptance':'UNMEASURED'}),file=sys.stderr);sys.exit(1)
