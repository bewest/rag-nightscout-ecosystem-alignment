"""Actual fixed orchestration adapter. Unreachable before reviewed source join.

The CLI's model gate is deliberate; this code is not a new runtime permission.
All app effects use the shipped controller except the one declared negative kill
and exact-owned final emergency cleanup. No raw Compose worker up/restart or SQL.
"""
import copy,ipaddress,json,os,re,threading,time
from pathlib import Path
import clinical as D
C,O,G,P,EP,EI,ER=D.C,D.O,D.G,D.P,D.EP,D.EI,D.ER
need=G.need
class Host(C.Host):
    def __init__(self,plan,out):
        super().__init__(copy.deepcopy(plan),out);self.environment['NODE_PATH']=plan['hostDependencies']['nodePath'];self.lock=threading.RLock();self.ports=D.Ports(self,plan);self.producer=None;self.producerClosed=False;self.captures=0;self.rounds=0;self.coldProofs={};self.waitCalls=0;self.reservedProducerBytes=0;self.currentEndpoints={}
    def command(self,*args,**kwargs):
        with self.lock:return super().command(*args,**kwargs)
    def health(self,slot):
        row=self.service(slot);need(row['State']['Running'],'PROCESS_NOT_RUNNING')
        if slot=='feed-reader':
            C.save(self.out/'feed-source-liveness.private.json',{'cid':row['Id'],'startedAt':row['State']['StartedAt'],'source':self.p['source'],'imageId':row['Image'],'ready':'UNMEASURED','scope':'exact-source process liveness; downstream proof required separately'});return row
        test=self.p['topology']['healthTests'][slot];need(row['Config'].get('Healthcheck',{}).get('Test')==test and test[0]=='CMD','SOURCE_HEALTH_COMMAND')
        before=self.ports.claims(slot);row=self.healthy(slot)
        need(not any(x.split('=',1)[0]in('NODE_OPTIONS','NODE_PATH','LD_PRELOAD')and x.split('=',1)[-1]for x in row['Config'].get('Env',[])),'HEALTH_PRELOAD')
        self.command(['docker','exec',row['Id'],*test[1:]],seconds=10)
        need(bool(before)and before==self.ports.claims(slot),'HEALTH_CLAIM_CHANGED');return row
    def sample(self,warming=False,idle=False):
        need(self.rounds<self.p['maximumEvaluatorRounds'],'EVALUATOR_ROUND_BOUND');self.rounds+=1
        value=self.ports.idle_round()if idle else self.ports.round(warming=warming);C.save(self.out/('evaluator-%03d.private.json'%self.rounds),value);return value
    def wait_owned(self):
        errors=[];self.waitCalls+=1
        for attempt in range(12):
            need(time.monotonic()<self.deadline-self.p['cleanupReserveSeconds'],'READINESS_DEADLINE')
            try:
                value=self.sample(warming=True);need(all(x['completedAcquisitions']>0 for x in value['owners'].values()),'ACQUISITION_NOT_OBSERVED');return value
            except EP.Refused as error:
                errors.append({'code':str(error),'verdict':error.verdict,'collection':getattr(error,'collection',None)});C.save(self.out/('evaluator-readiness-%03d-%03d.private.json'%(self.waitCalls,attempt)),errors)
                if error.verdict=='FAIL':raise
            time.sleep(15)
        raise G.Refused('NATIVE_CLINICAL_ACQUISITION_NOT_OBSERVED')
    def three(self,phase,idle=False):
        rounds=[]
        for n in range(3):
            if n:time.sleep(15)
            rounds.append(self.sample(idle=idle))
        result=EP.assess(rounds,self.p['ids'],phase);C.save(self.out/(phase+'-successful-work-%03d.private.json'%self.rounds),{'result':result,'packed':EP.pack({'rounds':rounds})})
        if idle:
            safety=EI.assess(rounds,self.p['ids']);C.save(self.out/('idle-safety-%03d.private.json'%self.rounds),{'result':safety,'scope':'separate from mandatory successful TIME'} )
        return rounds
    def identity(self,slot):
        row=self.service(slot);return {'cid':row['Id'],'startedAt':row['State']['StartedAt'],'imageId':row['Image'],'source':self.p['source']}
    def endpoints(self,allow_stopped_api=False):
        endpoints={};network=None
        for slot,port in [('admin',self.p['topology']['adminPort']),('api',1337),('api-2',1337),('socket-edge',1343)]:
            row=self.service(slot)
            need(row['State']['Running']or allow_stopped_api and slot=='api','CLIENT_ENDPOINT_NOT_RUNNING')
            if not row['State']['Running']:
                old=self.currentEndpoints.get(slot);need(old and old['cid']==row['Id']and old['startedAt']==row['State']['StartedAt'],'CLIENT_OLD_ENDPOINT_CUSTODY');endpoints[slot]=old;continue
            peers=row.get('NetworkSettings',{}).get('Networks',{});selected=peers.get(self.p['project']+'_backend');need(selected and selected.get('IPAddress'),'CLIENT_BACKEND_NETWORK')
            ip=ipaddress.ip_address(selected['IPAddress']);need(ip in ipaddress.ip_network(self.p['backendSubnet']),'CLIENT_BACKEND_ADDRESS')
            if network is None:
                rows=json.loads(self.command(['docker','network','inspect',selected['NetworkID']]))
                need(len(rows)==1 and rows[0]['Id']==selected['NetworkID']and(rows[0].get('Labels')or{}).get('com.docker.compose.project')==self.p['project']and(rows[0].get('Labels')or{}).get('com.docker.compose.network')=='backend','CLIENT_NETWORK_CUSTODY');network=selected['NetworkID']
            need(selected['NetworkID']==network,'CLIENT_NETWORK_CHANGED')
            endpoints[slot]={'origin':'http://'+str(ip)+':'+str(port),'cid':row['Id'],'startedAt':row['State']['StartedAt']}
        self.currentEndpoints=endpoints
        C.save(self.out/('client-endpoints-%03d.private.json'%self.n),endpoints);return endpoints
    def start_producer(self):
        directory=self.out/'http-session';directory.mkdir(mode=0o700);custody=directory/'client-custody';custody.mkdir(mode=0o700)
        spec={'version':1,'kind':'native-clinical-http-client','nonce':self.p['nonce'],'source':self.p['source'],'ids':self.p['ids'],'runId':self.p['runId'],'sourceRoot':str(Path(self.p['base']).parent.parent),'primerConfig':str(Path(self.p['state'])/'primer/config.json'),'clientCustody':str(custody),'endpoints':self.endpoints(),'sourceHelpers':{name:C.sha(Path(self.p['base'])/name)for name in ('prime.js','connection-budget-files.js')},'hostNodeVersion':self.p['hostDependencies']['nodeVersion'],'maximumRequests':8192,'maximumSockets':16,'maximumHttpBytes':268435456,'maximumWallMs':1200000}
        need(self.n<self.p['maximumCommands']-self.p['cleanupReserveCommands'],'COMMAND_COUNT')
        need(self.p['maximumOutputBytes']-self.bytes-self.p['cleanupReserveOutputBytes']>=self.p['maximumProducerOutputBytes'],'PRODUCER_OUTPUT_RESERVATION')
        # Reserve the complete child output allowance before construction. Host
        # bytes report actual output after join; no concurrent over-allocation.
        self.n+=1;self.reservedProducerBytes=self.p['maximumProducerOutputBytes'];self.p['maximumOutputBytes']-=self.reservedProducerBytes
        remaining=int(self.deadline-time.monotonic()-self.p['cleanupReserveSeconds']-4);need(remaining>5,'PRODUCER_DEADLINE');producer_plan={**self.p,'maximumProducerSeconds':min(self.p['maximumProducerSeconds'],remaining)}
        self.producer=D.Producer(producer_plan,directory/'protocol',spec,{'PATH':str(Path(self.p['hostDependencies']['nodeBinary']).parent),'LANG':'C.UTF-8','NODE_PATH':self.p['hostDependencies']['nodePath']});self.producer.start();return self.producer
    def finish_producer(self):
        result=self.producer.close();self.producerClosed=True;self.bytes+=self.producer.result['bytes'];self.p['maximumOutputBytes']+=self.reservedProducerBytes;self.reservedProducerBytes=0;return result
    def capture(self,label):
        need(self.captures<self.p['maximumCollectorCalls'],'COLLECTOR_CALL_BOUND');self.captures+=1
        plan=C.read(Path(self.p['state'])/'connection-budget/plan.json');book=C.read(Path(self.p['state'])/'connection-budget/ledger.json');need(set(book['slots'])==set(self.p['slots'])and sum(x['state']=='ISSUED'for rows in book['slots'].values()for x in rows)<=12,'CAPTURE_GENERATION_BOUND')
        spec={'kind':'m7-tagged-admission-observation-v1','controllerCli':self.p['controllerCli'],'controllerCliSha256':self.p['controllerCliSha256'],'collectorSha256':self.p['collectorSha256'],'state':self.p['state'],'expected':{'kind':'m7-tagged-admission-observation-v1','source':self.p['source'],'imageId':self.p['imageId'],'project':self.p['project'],'workingDirectory':self.p['base'],'planSha256':plan['sha256']}}
        file=self.out/(label+'-capture-spec.private.json');C.save(file,spec);self.command(['python3',self.p['collector'],str(file),str(self.out/(label+'-capture'))],seconds=125)
    def stop_ack(self,slot,cold=False):
        self.ports.stop(slot)
        if cold and slot in self.p['coldLimits']:
            book=C.read(Path(self.p['state'])/'connection-budget/ledger.json');row=book['slots'][slot][-1];ack=C.read(Path(self.p['state'])/'connection-budget'/slot/'claims'/('ack-'+row['incarnation']+'.json'));self.coldProofs[row['incarnation']]={'service':slot,'incarnation':row['incarnation'],**G.cold_ack(ack,self.p['coldLimits'][slot])};C.save(self.out/('cold-high-water-'+slot+'-'+row['incarnation']+'.private.json'),self.coldProofs[row['incarnation']])
    def negative_refusal(self):
        # Qualify the storm incarnation's clean ACK before creating the one
        # deliberately uncertain generation. No cold evidence is inferred later.
        self.stop_ack('api-2',cold=True);self.ports.start('api-2');self.health('api-2');row=self.service('api-2');book=Path(self.p['state'])/'connection-budget/ledger.json';before=C.sha(book)
        self.command(['docker','kill','--signal','KILL',row['Id']]);stopped=self.inspect(row['Id'],'api-2');need(not stopped['State']['Running']and stopped['State']['ExitCode']==137,'NEGATIVE_KILL_NOT_OBSERVED')
        expected=self.p['negativeEvent']['expectedRefusal']
        need(self.n<self.p['maximumCommands']-self.p['cleanupReserveCommands'],'COMMAND_COUNT');self.n+=1
        remaining=self.deadline-time.monotonic()-self.p['cleanupReserveSeconds'];budget=self.p['maximumOutputBytes']-self.bytes-self.p['cleanupReserveOutputBytes'];need(remaining>5 and budget>=4096,'NEGATIVE_COMMAND_BUDGET');prior=self.uncertain;self.uncertain=True
        r=O.run(['node',self.p['controllerCli'],self.p['state'],'start','api-2'],self.environment,self.out/('%03d'%self.n),min(20,remaining-4),min(2097152,budget));self.bytes+=r['bytes'];C.save(self.out/('%03d-result.json'%self.n),r)
        raw=json.loads(Path(r['stderr']).read_text());need(r['returnCode']==1 and r['failure']is None and r['groupDrained']and raw=={'error':expected},'NEGATIVE_REFUSAL_UNKNOWN')
        same=self.service('api-2');need(same['Id']==row['Id']and not same['State']['Running']and before==C.sha(book),'NEGATIVE_CREDIT_OR_PROCESS_CHANGED')
        self.uncertain=prior # exact reviewed pre-worker-effect typed refusal only
        C.save(self.out/'finite-uncertain-refusal.private.json',{'expectedRefusal':expected,'oldCid':row['Id'],'ledgerUnchanged':True,'creditRetired':False,'scope':'one deliberately uncertain API2 incarnation; replacement refused before worker effect'})
    def cleanup_owned(self):
        self.cleanup=True;errors=[]
        if self.producer is not None and not self.producerClosed:
            try:self.producer.abort()
            except BaseException as error:self.uncertain=True;errors.append({'stage':'producer-cancel','error':str(error)})
        try:C.save(self.out/'root-cleanup-spec.private.json',{'kind':'m7-clinical-exact-owned-cleanup-v1','plan':self.p,'allocationAttempted':self.allocation_attempted,'images':self.images,'known':self.owned})
        except BaseException as error:errors.append({'stage':'cleanup-spec-publication','error':str(error)})
        if not self.allocation_attempted:
            C.save(self.out/'finally-no-allocation.json',{'allocationAttempted':False,'cleanupEffects':0,'errors':errors,'uncertainHostEffect':self.uncertain});need(not errors and not self.uncertain,'CLEANUP_UNCONFIRMED');return
        if not getattr(self,'skip_controller_cleanup',False):
            for slot in reversed(self.p['startOrder']):
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
                need(service in self.p['slots']+['postgres','vault','bootstrap'],'CLEANUP_FOREIGN_SERVICE');r=self.inspect(cid,service);rows.append(r)
            except Exception as e:errors.append({'stage':'inspect','cid':cid,'error':str(e)});continue
            try:self.command(['docker','logs','--tail','100',cid],5,allow_failure=True)
            except Exception as e:errors.append({'stage':'logs','cid':cid,'error':str(e)})
            try:
                if r['State']['Running']:
                    self.inspect(cid,service) # exact original StartedAt before effect
                    self.command(['docker','stop','--time','10',cid],15)
                after=self.inspect(cid,service);need(not after['State']['Running'],'CLEANUP_RUNNING');final.append(after)
            except Exception as e:errors.append({'stage':'stop-or-confirm','cid':cid,'error':str(e)});continue
        C.save(self.out/'finally-owned-inspection.private.json',rows)
        C.save(self.out/'finally-stopped.private.json',{'errors':errors,'uncertainHostEffect':self.uncertain,'rows':final,'knownAbsent':absent,'creditRetirement':'NEVER_INFERRED_FROM_CLEANUP','lateDaemonEffect':'UNCONFIRMED'if self.uncertain else'NO_HOST_COMMAND_UNCERTAINTY'})
        need(not errors and len(final)+len(absent)==len(candidates)and not self.uncertain,'CLEANUP_UNCONFIRMED')

def execute(plan,output):
    # Regeneration/feature admission precede Host construction and every Docker
    # effect. Editing a private JSON flag cannot authorize an old source pair.
    need(D.SOURCE_JOIN=='REVIEWED_FINAL_SOURCE'and plan.get('runtimeReady')is True,'FINAL_SOURCE_JOIN_REQUIRED_BEFORE_EFFECTS')
    need(D.prepare(plan['root'],plan['topology'])==plan,'PLAN_CHANGED')
    need(D.DEP.capture()==plan['hostDependencies'],'CLIENT_DEPENDENCY_CHANGED')
    h=Host(plan,output);events=[];result={'kind':plan['kind'],'nativeAcceptance':'UNMEASURED','driver':'INCOMPLETE','scope':plan['scope']}
    def event(name):events.append(name);C.save(h.out/('phase-events-%03d.private.json'%len(events)),list(events))
    def output_metadata():
        values={service:[G.cached_clinical(page['view'],plan['ids'])for page in pages]for service,pages in h.ports.latestClinical.items()}
        C.save(h.out/('evaluation-metadata-%03d.private.json'%h.rounds),values);return values
    def snapshot(slot):return h.identity(slot)
    def selected_pair(round):
        ordered=plan['ids'];a=ordered[0];b=next((x for x in ordered if round['owners'][x]['service']!=round['owners'][a]['service']),None);need(b is not None,'INDEPENDENT_EVALUATOR_OWNERS_NOT_OBSERVED');return a,b
    def realtime_slot(tenant):
        # Use the exact frozen routes/config; never derive participant IDs from
        # a service spelling. The source placement function owns shard hashing.
        script="const fs=require('node:fs'),P=require(process.argv[1]),v=JSON.parse(fs.readFileSync(process.argv[2]));const n=P.shard(process.argv[3],v.shardCount);process.stdout.write(JSON.stringify({worker:v.owners[n]}));"
        value=json.loads(h.command(['node','-e',script,str(Path(plan['root'])/'source/lib/realtime-placement'),str(Path(plan['state'])/'placement/routes.json'),tenant]))
        # Worker IDs map via the source-generated realtime operation rows.
        mapping=plan['topology'].get('realtimeWorkers');need(isinstance(mapping,dict)and value['worker']in mapping,'SOURCE_REALTIME_ALIAS_JOIN_REQUIRED');return mapping[value['worker']]
    def b_snapshot(tenant,round,socket):
        api=h.service('api-2');rt_slot=realtime_slot(tenant);rt=h.service(rt_slot);book=C.read(Path(plan['state'])/'connection-budget/ledger.json');owner=round['owners'][tenant]
        return {'apiCid':api['Id'],'apiIncarnation':book['slots']['api-2'][-1]['incarnation'],'evaluatorRuntimeId':owner['runtimeId'],'evaluatorGeneration':owner['generation'],'realtimeCid':rt['Id'],'realtimeIncarnation':book['slots'][rt_slot][-1]['incarnation'],'socketId':socket['socketId'],'completedTimeCycles':owner['completedTimeCycles'],'failedCompletions':owner['failedCompletions']}
    try:
        event('bootstrap');pre=P.read_host(plan,h.command);C.save(h.out/'host-preflight.private.json',pre)
        for file,digest in plan['config']['fileDigests'].items():need(C.sha(file)==digest,'PREPARED_FILE_CHANGED')
        for ref,service in [(C.PG_IMAGE,'postgres'),(C.VAULT,'vault'),(plan['imageId'],'app')]:
            rows=json.loads(h.command(['docker','image','inspect',ref]));need(len(rows)==1 and rows[0]['Os']=='linux'and rows[0]['Architecture']=='amd64','IMAGE_PLATFORM');h.images[service]=rows[0]['Id']
        need(h.images['app']==plan['imageId']and time.monotonic_ns()-pre['observedMonotonicNs']<5000000000,'PREFLIGHT_OR_IMAGE_CHANGED')
        h.allocation_attempted=True;h.compose('up','--no-deps','--no-build','--pull','never','-d','postgres','vault');h.healthy('postgres');h.healthy('vault');h.compose('--profile','ops','run','--rm','--no-deps','bootstrap',seconds=240);h.plan_view();h.controller('bind')
        event('start-all-eleven')
        for slot in plan['startOrder']:h.ports.start(slot)
        for slot in plan['startOrder']:h.health(slot)
        producer=h.start_producer();event('prime-http');prime=producer.phase('prime',seconds=900);need(prime['primed']==prime['provisioned']==16,'FULL_PRIME_COHORT')
        event('clinical-history-http');history=producer.phase('history',seconds=900);need(history['attempted']==history['accepted']==4608,'CLINICAL_HISTORY_INCOMPLETE');C.save(h.out/'synthetic-history.private.json',history)
        event('baseline-progress');baseline=h.wait_owned();h.three('load');output_metadata();event('snapshot-started');h.capture('started')
        cohort=[x['service']for x in plan['cohort']];before={s:snapshot(s)for s in cohort};event('stop-seven-with-acks')
        for slot in reversed(cohort):h.stop_ack(slot)
        event('start-cold-api2');h.ports.start('api-2');event('bind-cold-endpoints');producer.phase('rebind',{'endpoints':h.endpoints(allow_stopped_api=True)})
        event('start-first-touch-storm');storm_box={}
        def storm():
            try:storm_box['value']=producer.phase('storm',seconds=180)
            except BaseException as error:storm_box['error']=error
        thread=threading.Thread(target=storm,daemon=True);thread.start()
        event('start-other-six')
        for slot in cohort:
            if slot!='api-2':h.ports.start(slot)
        event('finish-storm');thread.join(timeout=185);need(not thread.is_alive()and'error'not in storm_box,'STORM_INCOMPLETE');storm=storm_box['value'];C.save(h.out/'first-touch-storm.private.json',storm)
        need(storm['warmingReplies']>0 and any(x['status']==200 for x in storm['results'])and any(x['frames']>0 for x in storm['socketResults']),'GENUINE_COLD_FIRST_TOUCH_NOT_OBSERVED')
        for slot in cohort:h.health(slot)
        cold_targets={slot:C.read(Path(plan['state'])/'connection-budget/ledger.json')['slots'][slot][-1]['incarnation']for slot in cohort if slot.startswith(('api','realtime','evaluator'))};C.save(h.out/'cold-targets.private.json',cold_targets)
        after={s:snapshot(s)for s in cohort};C.save(h.out/'cohort-restart.private.json',{'before':before,'after':after,'result':G.restarted(before,after,cohort)})
        event('fresh-recovery');first=h.wait_owned();time.sleep(15);second=h.sample();recovery=ER.assess(baseline,[first,second],plan['ids']);C.save(h.out/'fresh-recovery.private.json',{'result':recovery,'baseline':baseline,'rounds':[first,second]})
        # Rebind A as well now that every fresh cohort process exists.
        producer.phase('rebind',{'endpoints':h.endpoints()})
        event('successful-time');time_rounds=h.three('idle',idle=True);output_metadata();event('snapshot-restarted');h.capture('restarted')
        a,b=selected_pair(time_rounds[-1]);event('connect-A-B-stock-sockets');socket_rows=producer.phase('connect',{'tenants':[a,b]},seconds=45);socket_b=next(x for x in socket_rows if x['tenant']==b)
        feed_before=h.ports.feed();C.save(h.out/'feed-before.private.json',feed_before)
        event('marked-writes');writes=producer.phase('writes',seconds=180);need(writes['attempted']==writes['accepted']==64,'MARKED_WRITES_INCOMPLETE')
        event('clinical-http-available');clinical=producer.phase('clinical',seconds=120);C.save(h.out/'clinical-http.private.json',{'rows':clinical,'result':G.clinical_http(clinical,plan['ids'])})
        stable=h.sample();socket_before=producer.phase('socketState',{'tenant':b});need(socket_before['connected']and socket_before['connections']==1 and socket_before['errors']==0,'HEALTHY_B_INITIAL_SOCKET');before_b=b_snapshot(b,stable,socket_before)
        event('partial-api-stop-ack');old_api=snapshot('api');h.stop_ack('api',cold=True)
        event('healthy-B-during-outage');healthy=producer.phase('healthyB',{'tenant':b},seconds=60);need(all(x['readStatus']==200 and x['writeStatus']in(200,201)and x['ownFrameAfterWrite']and x['errors']==0 for x in healthy['rounds']),'HEALTHY_B_CONTINUITY')
        during=h.sample();output_metadata();socket_during=producer.phase('socketState',{'tenant':b});need(socket_during['connected']and socket_during['connections']==1 and socket_during['errors']==0,'HEALTHY_B_DURING_SOCKET');during_b={**b_snapshot(b,during,socket_during),**{k:healthy[k]for k in ('readStatus','writeStatus','ownFrameAfterWrite','foreignFrames')}}
        event('partial-api-start');h.ports.start('api');h.health('api');need(snapshot('api')['cid']!=old_api['cid'],'PARTIAL_RESTART_OLD_CID');producer.phase('rebind',{'endpoints':h.endpoints()})
        event('post-restart-progress');post=h.three('load');output_metadata();socket_after=producer.phase('socketState',{'tenant':b});need(socket_after['connected']and socket_after['connections']==1 and socket_after['errors']==0,'HEALTHY_B_FINAL_SOCKET');after_b=b_snapshot(b,post[-1],socket_after)
        healthy_value={'apiA':'api','apiB':'api-2','tenantA':a,'tenantB':b,'ownerA':stable['owners'][a]['service'],'ownerB':stable['owners'][b]['service'],'before':before_b,'during':during_b,'after':after_b,'stopAckBeforeOutageCommand':True,'outageReplyBeforeStart':True}
        C.save(h.out/'healthy-B.private.json',{'evidence':healthy_value,'result':G.healthy_b(healthy_value)})
        event('isolation');isolation=producer.phase('isolation',{'a':a,'b':b},seconds=60);C.save(h.out/'isolation.private.json',{'evidence':isolation,'result':G.isolation(isolation)})
        clinical_after=producer.phase('clinical',seconds=120);C.save(h.out/'clinical-http-after.private.json',{'rows':clinical_after,'result':G.clinical_http(clinical_after,plan['ids'])})
        feed_after=h.ports.feed();C.save(h.out/'feed-delivery.private.json',{'before':feed_before,'after':feed_after,'result':G.feed_delivery(feed_before,feed_after,plan['topology']['feedHeartbeatTimeoutMs'])})
        event('close-http-admissions');closed=h.finish_producer();need(D.DEP.capture()==plan['hostDependencies'],'CLIENT_DEPENDENCY_CHANGED')
        G.raw_http_ledgers(closed,h.producer.out)
        event('independent-stored-counts');h.ports.counts(G.selector(plan['ids'],plan['runId']),closed['ledgers']);event('snapshot-clinical');h.capture('clinical')
        event('finite-uncertain-credit-refusal');h.negative_refusal()
        event('normal-stops-with-acks')
        for slot in reversed(plan['startOrder']):
            if slot!='api-2':h.stop_ack(slot,cold=slot in('api','realtime','realtime-2','evaluator','evaluator-2'))
        need(all(inc in h.coldProofs for inc in cold_targets.values()),'COLD_TARGET_ACK_MISSING');need(h.coldProofs[cold_targets['api-2']]['observed']['peakQueued']>0,'SELECTED_COLD_QUEUE_NOT_EXERCISED')
        event('snapshot-retired-held');h.capture('retired-held')
        # Source d003 does not expose evaluator-specific clinical availability.
        # Even manually bypassing the source-join guard cannot relabel that gap.
        need(plan['topology'].get('diagnostics',{}).get('clinicalResults')=='clinical-result-v1','EVALUATOR_CACHED_BG_NOW_NO_INSTRUMENT')
        result.update(driver='PASS',nativeAcceptance='PASS')
    except BaseException as error:result.update(driver='FAIL',error=str(error))
    finally:
        try:event('finally-exact-owned-stop')
        except BaseException as error:result.update(driver='FAIL',eventPublicationError=str(error),nativeAcceptance='UNMEASURED')
        try:h.cleanup_owned()
        except BaseException as error:result.update(driver='FAIL',cleanupError=str(error),nativeAcceptance='UNMEASURED')
        try:C.save(h.out/'phase-events.private.json',list(events))
        except BaseException as error:result.update(driver='FAIL',eventPublicationError=str(error),nativeAcceptance='UNMEASURED')
        result.update(commands=h.n,outputBytes=h.bytes,uncertainHostEffect=h.uncertain);C.save(h.out/'result.private.json',result)
    return result
