"""Bounded selected clinical instrument; runtime waits for the coherent source join.

No command below allocates unless `run` passes the exact regenerated plan and the
source feature gate. `plan` and `dry-run` are file/model-only. The d003 anchor is
an implementation fixture, never the final clinical source qualification.
"""
import argparse,copy,hashlib,importlib.util,ipaddress,json,os,re,sys,tempfile,threading,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'native-admission'));sys.path.insert(0,str(HERE.parent/'m7-joined'))
import commissioning as C,producer_process as O,preflight as P
import evaluator_progress as EP,evaluator_idle as EI,evaluator_recovery as ER
import gates as G
import dependencies as DEP
need=G.need
# Final source/image pins are deliberately not guessed. d003 lacks observed
# cold peaks. The coordinator will repin the coherent reviewed source later.
SOURCE_JOIN='REQUIRED_BEFORE_RUNTIME'
STEPS=('bootstrap', 'start-all-eleven', 'prime-http', 'clinical-history-http', 'baseline-progress', 'snapshot-started', 'stop-seven-with-acks', 'start-cold-api2', 'bind-cold-endpoints', 'start-first-touch-storm', 'start-other-six', 'finish-storm', 'fresh-recovery', 'successful-time', 'snapshot-restarted', 'connect-A-B-stock-sockets', 'marked-writes', 'clinical-http-available', 'partial-api-stop-ack', 'healthy-B-during-outage', 'partial-api-start', 'post-restart-progress', 'isolation', 'close-http-admissions', 'independent-stored-counts', 'snapshot-clinical', 'finite-uncertain-credit-refusal', 'normal-stops-with-acks', 'snapshot-retired-held', 'finally-exact-owned-stop')

def actual_topology(root,dependencies):
    root=Path(root).resolve();file=root/'source-input.private.json';before=C.sha(file);input=C.read(file)
    need(input.get('sourceRoot')==str(root/'source'),'SOURCE_ROOT_CHANGED')
    scratch=Path(tempfile.mkdtemp(prefix='m7-clinical-source-admit-',dir='/tmp'));output=scratch/'topology.private.json'
    result=O.run([dependencies['nodeBinary'],str(HERE/'metadata.cjs'),str(file),str(output)],{'PATH':str(Path(dependencies['gitBinary']).parent)+os.pathsep+str(Path(dependencies['nodeBinary']).parent),'LANG':'C.UTF-8','NODE_PATH':dependencies['nodePath']},scratch/'owned-child',25,2097152)
    C.save(scratch/'result.private.json',result)
    need(result['returnCode']==0 and result['failure']is None and result['groupDrained']and C.sha(file)==before,'SOURCE_METADATA_REFUSED')
    return C.read(output)

def prepare(root,topology):
    base=C.prepare(root);dependencies=DEP.capture();need(topology==actual_topology(root,dependencies),'SOURCE_TOPOLOGY_CHANGED');G.roster(topology['tenantIds'])
    need(topology['source']==base['source']and len(topology['slots'])==11 and len(set(topology['slots']))==11,'SOURCE_TOPOLOGY')
    operations=topology['operations'];need(len(operations)==7 and len({x['participantId']for x in operations})==7 and len({x['service']for x in operations})==7 and all(x['service']in topology['slots']for x in operations),'SOURCE_PARTICIPANTS')
    order=['admin','feed-reader','api','api-2','realtime','realtime-2','evaluator','evaluator-2','tenant-admin','ui','socket-edge'];need(set(order)==set(topology['slots']),'SOURCE_START_ROSTER')
    profile=C.read(Path(root)/'profile-generation-final/profile.json');need(next(x for x in profile['slots']if x['processInstanceId']=='api-2')['maximumOutstandingGenerations']==1,'NEGATIVE_GENERATION_PROFILE')
    fresh=not any((Path(root)/'state'/name).exists()for name in ('bootstrap/complete.json','connection-budget/custody.json','connection-budget/ledger.json'))
    plan={**base,'freshPreparation':fresh,'hostDependencies':dependencies,'kind':'m7-selected-clinical-v1','runtimeSourceJoin':SOURCE_JOIN,'runtimeReady':fresh and SOURCE_JOIN=='REVIEWED_FINAL_SOURCE'and topology.get('coldObserved')is not None and topology.get('diagnostics')=={'clinicalResults':'clinical-result-v1','changeFeed':'change-feed-v1'},'slots':topology['slots'],'startOrder':order,'cohort':operations,'ids':topology['tenantIds'],'runId':'m7-native-'+base['nonce'][:24],
          'maximumSeconds':1800,'cleanupReserveSeconds':180,'maximumCommands':2048,'cleanupReserveCommands':256,'maximumOutputBytes':134217728,'cleanupReserveOutputBytes':33554432,
          'maximumCollectorCalls':8,'maximumCollectorCommands':120,'maximumCollectorRawInternalBytes':134217728,'maximumCollectorParentOutputBytes':16777216,
          'maximumEvaluatorExecs':96,'maximumEvaluatorResponseBytes':50331648,'maximumEvaluatorRounds':48,'maximumProducerSeconds':1200,'maximumProducerOutputBytes':4194304,
          'maximumHttpRequests':16384,'maximumHttpResponseBytes':268435456,'maximumMarkedRequests':8192,'maximumSockets':16,'maximumProtocolPhases':16,
          'coldLimits':{s['processInstanceId']:s['cold']for s in profile['slots']},'topology':topology,'steps':list(STEPS),
          'scope':'complete selected clinical driver; no capacity/SLO or production-profile recommendation; runtime source qualification pending',
          'negativeEvent':{'service':'api-2','event':'exact-CID SIGKILL after clinical admissions close','expectedRefusal':'CONNECTION_ADMISSION_GENERATIONS_EXHAUSTED','refund':'FORBIDDEN','maximumEvents':1},
          'clinicalFiles':{p.name:C.sha(p)for p in HERE.iterdir()if p.is_file()and p.suffix in('.py','.cjs','.md')},
          'reusedFiles':{name:C.sha(HERE.parent/'m7-joined'/name)for name in ('evaluator_progress.py','evaluator_idle.py','evaluator_recovery.py','probe-accounting.cjs')},
          'nativeAcceptance':'UNMEASURED'}
    return plan

class Ports:
    """Actual fixed metadata/count/controller glue over the bounded dcfe Host.

    A future coherent Runtime delegates command effects here. These methods are
    independently executable against recording command ports without a stack.
    """
    def __init__(self,host,plan):self.host=host;self.plan=plan;self.execs=0;self.bytes=0;self.latestClinical={};self.lock=threading.RLock()
    def claims(self,slot):
        directory=Path(self.plan['state'])/'connection-budget'/slot/'claims'
        return {p.name:(C.sha(p),p.stat().st_ino,p.stat().st_mode&0o777)for p in directory.glob('claim-*')}
    def evaluator(self,service,ids,queries,budget,diagnostics='clinical-result-v1'):
        need(service in {x['service']for x in self.plan['cohort']if x['roles']==['evaluator']}and ids==self.plan['ids']and queries==1,'EVALUATOR_SELECTOR')
        # Serialize host receipt accounting. The pure round assessor may request
        # two instances concurrently; this instrument has one exec lane.
        with self.lock:
            need(self.execs<self.plan['maximumEvaluatorExecs'],'EVALUATOR_EXEC_BOUND');self.execs+=1
            before=self.host.service(service);claims=self.claims(service);need(bool(claims),'EVALUATOR_CLAIM_MISSING')
            need(diagnostics in('clinical-result-v1','change-feed-v1'),'EVALUATOR_DIAGNOSTICS');spec={'ids':ids,'queryBudget':1,'byteBudget':min(budget,1048576),'diagnostics':diagnostics}
            code='globalThis.M7_NATIVE_FETCH_SPEC='+json.dumps(spec,separators=(',',':'))+';\n'+(HERE/'evaluator-fetch.cjs').read_text()
            need(len(code.encode())<=65536,'EVALUATOR_HELPER_BOUND')
            need(not any(x.split('=',1)[0]in ('NODE_OPTIONS','NODE_PATH','LD_PRELOAD')and x.split('=',1)[-1]for x in before['Config'].get('Env',[])),'EVALUATOR_PRELOAD')
            raw=self.host.command(['docker','exec',before['Id'],'node','-e',code],seconds=12)
            after=self.host.inspect(before['Id'],service);need(after['State']['StartedAt']==before['State']['StartedAt']and after['State']['Running']and claims==self.claims(service),'EVALUATOR_CLAIM_OR_IDENTITY_CHANGED')
            data=raw.encode();self.latestClinical[service]=[json.loads(line)for line in data.splitlines()];self.bytes+=len(data);need(len(data)<=spec['byteBudget']and self.bytes<=self.plan['maximumEvaluatorResponseBytes'],'EVALUATOR_BYTE_BOUND');return data
    def round(self,warming=False):
        services=[x['service']for x in self.plan['cohort']if x['roles']==['evaluator']]
        return EP.round_view(services,self.plan['ids'],self.evaluator,warming=warming)
    def idle_round(self):
        services=[x['service']for x in self.plan['cohort']if x['roles']==['evaluator']]
        return EI.round_view(services,self.plan['ids'],self.evaluator)
    def feed(self):
        services=[x['service']for x in self.plan['cohort']if x['roles']==['evaluator']];result={}
        for service in services:
            raw=self.evaluator(service,self.plan['ids'],1,1048576,diagnostics='change-feed-v1');pages=[json.loads(line)for line in raw.splitlines()];need(len(pages)==1,'FEED_PAGE_BOUND');result[service]=pages[0]['view']
        return result
    def counts(self,selected,ledgers):
        # Complete original roster is checked BEFORE writing a selector or
        # executing any count command. Batching can never imply foreign zero.
        need(selected==G.selector(self.plan['ids'],self.plan['runId']),'INCOMPLETE_SAME_MARKER_ROSTER')
        file=self.host.out/'stored-count-selector.private.json';C.save(file,selected)
        value=json.loads(self.host.command(['node',self.plan['controllerCli'],self.plan['state'],'stored-counts',str(file)],seconds=20))
        bound=C.read(Path(self.plan['state'])/'connection-budget/plan.json')
        expected={'source':self.plan['source'],'custody':{'project':self.plan['project'],'workingDirectory':self.plan['base'],'imageId':self.plan['imageId'],'source':self.plan['source']},'planSha256':bound['sha256']}
        C.save(self.host.out/'stored-count-observation.private.json',value);result=G.counts(expected,selected,value,ledgers);C.save(self.host.out/'stored-count-assessment.private.json',result);return result
    def stop(self,slot):
        need(slot in self.plan['slots'],'UNPLANNED_WORKER');result=self.host.controller('stop',slot);self.host.ack(slot);return result
    def start(self,slot):
        need(slot in self.plan['slots'],'UNPLANNED_WORKER');return self.host.controller('start',slot)

class Producer:
    """One WNOWAIT-supervised host child and finite private nonce/sequence IPC."""
    def __init__(self,plan,out,spec,environment):
        self.plan=plan;self.out=Path(out);self.out.mkdir(mode=0o700);self.n=0;self.result=None;self.error=None;self.cancelled=threading.Event()
        self.specFile=self.out/'client-spec.private.json';C.save(self.specFile,spec)
        # No HOME, NODE_OPTIONS, PG, Vault, worker config/ticket or controller
        # environment. NODE_PATH points only to the pinned existing client deps.
        allowed={'PATH','LANG','NODE_PATH'};need(set(environment)<=allowed,'PRODUCER_ENV');self.environment=environment
        def run():
            try:self.result=O.run([plan['hostDependencies']['nodeBinary'],str(HERE/'session.cjs'),str(self.specFile),str(self.out)],environment,self.out/'owned-child',plan['maximumProducerSeconds'],plan['maximumProducerOutputBytes'],cancel_event=self.cancelled);C.save(self.out/'owned-child-result.private.json',self.result)
            except BaseException as error:self.error=error
        self.thread=threading.Thread(target=run,daemon=True)
    def start(self):self.thread.start();self.wait_file('session-ready.json',15)
    def wait_file(self,name,seconds):
        deadline=time.monotonic()+seconds;file=self.out/name
        while not file.exists():
            need(self.thread.is_alive()and self.error is None and time.monotonic()<deadline,'PRODUCER_INCOMPLETE');time.sleep(.05)
        return C.read(file)
    def phase(self,action,args=None,seconds=60):
        need(self.n<self.plan['maximumProtocolPhases'],'PRODUCER_PHASE_BOUND');self.n+=1
        C.save(self.out/('phase-%04d.json'%self.n),{'nonce':self.plan['nonce'],'sequence':self.n,'action':action,'args':args or {}})
        value=self.wait_file('reply-%04d.json'%self.n,seconds)
        need(value.get('nonce')==self.plan['nonce']and value.get('sequence')==self.n and value.get('action')==action and value.get('outcome')=='OK','PRODUCER_PHASE_REFUSED');return value['value']
    def abort(self):
        self.cancelled.set();self.thread.join(timeout=5)
        need(not self.thread.is_alive()and self.error is None and isinstance(self.result,dict)and self.result.get('groupDrained')is True,'PRODUCER_CLEANUP_UNKNOWN')
    def close(self):
        value=self.phase('close',seconds=30);self.thread.join(timeout=5)
        need(not self.thread.is_alive()and self.error is None and self.result is not None and self.result['returnCode']==0 and self.result['failure']is None and self.result['groupDrained'],'PRODUCER_EXIT_UNKNOWN');return value

class Recording:
    """Protocol model, never acceptance. No Docker/HTTP/SQL/socket or source RPC."""
    def __init__(self,plan):self.plan=plan;self.events=[];self.live=set();self.retired=[]
    def event(self,step):
        need(step in STEPS,'UNKNOWN_STEP');self.events.append(step)
        if step=='start-all-eleven':self.live=set(self.plan['slots'])
        if step=='stop-seven-with-acks':self.live-=set(x['service']for x in self.plan['cohort'])
        if step=='start-cold-api2':self.live.add('api-2')
        if step=='start-other-six':self.live|=set(x['service']for x in self.plan['cohort'])
        if step=='partial-api-stop-ack':need('api-2'in self.live,'HEALTHY_B_NOT_LIVE');self.live.remove('api')
        if step=='healthy-B-during-outage':need('api'not in self.live and 'api-2'in self.live,'HEALTHY_B_NOT_DURING_OUTAGE')
        if step=='partial-api-start':self.live.add('api')
        if step=='normal-stops-with-acks':self.live.clear()
        if step=='finally-exact-owned-stop':self.live.clear()
        return {'step':step,'kind':'MODEL_ONLY'}
def dry_run(plan,output):
    need(plan['steps']==list(STEPS),'PROTOCOL_CHANGED');out=Path(output);out.mkdir(mode=0o700);model=Recording(plan)
    try:
        for step in plan['steps'][:-1]:model.event(step)
    finally:model.event('finally-exact-owned-stop')
    need(model.events==list(STEPS)and not model.live,'PROTOCOL_INCOMPLETE')
    value={'kind':'native-clinical-protocol-recording','result':'PASS','nativeAcceptance':'UNMEASURED','runtime':'NOT_RUN','events':model.events,'source':plan['source']};C.save(out/'recording.private.json',value);return value

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['plan','dry-run','run']);parser.add_argument('input',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--topology',type=Path);args=parser.parse_args()
    if args.operation=='plan':
        need(args.topology is not None,'SOURCE_TOPOLOGY_REQUIRED');value=prepare(args.input,C.read(args.topology));args.output.mkdir(mode=0o700);C.save(args.output/'clinical-plan.private.json',value);print('CLINICAL_MODEL_PREPARED_NO_LAUNCH_AUTHORITY')
    elif args.operation=='dry-run':print(json.dumps(dry_run(C.read(args.input),args.output)))
    else:
        plan=C.read(args.input);need(plan.get('runtimeReady')is True and plan.get('runtimeSourceJoin')=='REVIEWED_FINAL_SOURCE','FINAL_SOURCE_JOIN_REQUIRED_BEFORE_EFFECTS')
        need(SOURCE_JOIN=='REVIEWED_FINAL_SOURCE','FINAL_SOURCE_JOIN_REQUIRED_BEFORE_EFFECTS')
        import runtime
        result=runtime.execute(plan,args.output);print(json.dumps(result));sys.exit(0 if result.get('driver')=='PASS'else 1)
if __name__=='__main__':
    try:main()
    except Exception as error:print(json.dumps({'error':str(error),'nativeAcceptance':'UNMEASURED'}),file=sys.stderr);sys.exit(1)
