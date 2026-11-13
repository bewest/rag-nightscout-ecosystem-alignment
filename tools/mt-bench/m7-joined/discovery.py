"""Explicit observational load route. Never grants capacity acceptance."""
import json
import re
import subprocess
import time
from contract import require, SHA, OWNER

INCOMPLETE=frozenset(('M7_EVALUATOR_IDLE_JOB_PENDING','M7_EVALUATOR_IDLE_NEW_DEMAND','M7_EVALUATOR_IDLE_FINAL_COMPLETION_PENDING','M7_EVALUATOR_IDLE_TAIL_REQUIRED','M7_EVALUATOR_IDLE_TAIL_COMPLETION','M7_EVALUATOR_IDLE_TAIL_BODY','M7_EVALUATOR_IDLE_TAIL_JOB_PENDING','M7_EVALUATOR_IDLE_TAIL_DEADLINE','M7_EVALUATOR_IDLE_TAIL_OWNER_BOUND','M7_EVALUATOR_IDLE_TAIL_OPPORTUNITY','M7_EVALUATOR_IDLE_TIME_NOT_OBSERVED','M7_EVALUATOR_IDLE_UNCREDITED_WORK','M7_EVALUATOR_IDLE_UNATTRIBUTED_TIME','M7_EVALUATOR_PROGRESS_NOT_OBSERVED','M7_RUNTIME_NOT_READY','M7_EVALUATOR_PROGRESS_UNAVAILABLE','M7_EVALUATOR_PROGRESS_COLLECTOR_TIMEOUT'))

def safe_code(error):
    text=str(error)
    return text if re.fullmatch(r'M7_[A-Z_]+(?::[a-zA-Z0-9_.-]+)?',text) else 'M7_DISCOVERY_INSTRUMENT_ERROR'

SOFT_WORK_FAILURES=frozenset(('M7_EVALUATOR_PROGRESS_ERROR','M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE'))

def incomplete(error):return str(error) in SOFT_WORK_FAILURES or (getattr(error,'verdict','UNMEASURED')!='FAIL' and str(error) in INCOMPLETE)

def check_discovery(value):
    require(value.get('kind') in ('m7-joined-discovery-cell','m7-joined-discovery') and value.get('version')==1 and value.get('runPurpose')=='discovery' and value.get('capacityAcceptance')=='NOT_GRANTED','M7_DISCOVERY_SHAPE')
    require(value.get('status') in ('MEASURED','PARTIAL'),'M7_DISCOVERY_STATUS')
    require(all(SHA.fullmatch(value.get('pair',{}).get(k,'')) for k in ('core','deploy')),'M7_DISCOVERY_SOURCE')
    require(re.fullmatch(r'[a-f0-9]{64}',value.get('instrument','')) and re.fullmatch(r'[a-f0-9]{64}',value.get('hostIdentity','')) and re.fullmatch(r'sha256:[a-f0-9]{64}',value.get('imageId','')),'M7_DISCOVERY_IDENTITY')
    from profile_provenance import check_identity
    chosen=check_identity(value.get('profileSelection'))
    if value['kind']=='m7-joined-discovery':
        cells=value.get('cells');require(isinstance(cells,list) and 1<=len(cells)<=12,'M7_DISCOVERY_CELLS')
        roster=[]
        for row in cells:
            require(row.get('kind')=='m7-joined-discovery-cell','M7_DISCOVERY_CELL_KIND');check_discovery(row)
            require(all(row.get(k)==value.get(k) for k in ('pair','instrument','hostIdentity','imageId','profileSelection')),'M7_DISCOVERY_MIXED_IDENTITY')
            roster.append((row['tenants'],row['replicas']))
        require(len(set(roster))==len(roster),'M7_DISCOVERY_DUPLICATE_CELL')
        if value['status']=='MEASURED':require(all(row['status']=='MEASURED' for row in cells),'M7_DISCOVERY_MISSING_MEASUREMENT')
        return True
    declared=value.get('settingsFingerprint',{})
    require(declared.get('sha256')==chosen['settings']['sha256'] and declared.get('sourceCommit')==value['pair']['core'] and chosen['settings']['sourceCommit']==value['pair']['core'],'M7_DISCOVERY_DECLARED_SETTINGS')
    require(re.fullmatch(r'[a-f0-9]{32}',value.get('owner','')) and value.get('ownershipVerified') is True,'M7_DISCOVERY_OWNERSHIP')
    require(type(value.get('tenants')) is int and 1<=value['tenants']<=10000 and value.get('replicas') in (1,2,4),'M7_DISCOVERY_TOPOLOGY')
    require(isinstance(value.get('strictChecks'),dict) and isinstance(value.get('processes'),dict) and isinstance(value.get('hardFailures'),list),'M7_DISCOVERY_OBSERVATIONS')
    require(not value['hardFailures'],'M7_DISCOVERY_HARD_FAILURE')
    oracle=value.get('oracle')
    if oracle is not None:
        require(oracle.get('verdict')=='GREEN' and not oracle.get('failures'),'M7_DISCOVERY_WRONG_DATA')
        if 'rows' in oracle:
            rows=oracle['rows'];require(isinstance(rows,list) and len(rows)==value['tenants'] and len({r.get('tenant') for r in rows})==len(rows),'M7_DISCOVERY_COUNT_ROSTER')
            for row in rows:
                require(all(type(row.get(k)) in (int,float) and row[k]>=0 for k in ('accepted','stored','uncertain')) and row['accepted']<=row['stored']<=row['accepted']+row['uncertain'] and row.get('match') is True,'M7_DISCOVERY_WRONG_DATA')
    probe=value.get('probe') or {};require(not probe.get('hardFailure') and not hard_recovery(probe.get('restart',{}).get('runtimeAcquisitionObservation',{})),'M7_DISCOVERY_HARD_FAILURE')
    for row in value['strictChecks'].values():
        require(isinstance(row,dict) and row.get('verdict') in ('PASS','FAIL','UNMEASURED'),'M7_DISCOVERY_CHECK_SHAPE')
        require(row.get('hardFailure') is not True,'M7_DISCOVERY_HARD_FAILURE')
    if value['status']=='MEASURED':require(value.get('measurements',{}).get('complete') is True and oracle is not None and value.get('probe') is not None and all(value['processes'].get(k,{}).get('returncode')==0 for k in ('k6','probe')),'M7_DISCOVERY_MISSING_MEASUREMENT')
    return True

class Record:
    def __init__(self,a,d,m):
        self.a,self.d,self.m=a,d,m
        self.value={'version':1,'kind':'m7-joined-discovery-cell','runPurpose':'discovery','status':'PARTIAL','capacityAcceptance':'NOT_GRANTED',**{k:m[k] for k in ('pair','hostIdentity','imageId','tenants','replicas','owner','profile','cadence')},'instrument':m['instrument']['sha256'],'profileSelection':m['profileSelection'],'settingsFingerprint':m['settingsFingerprint'],'ownershipVerified':False,'strictChecks':{},'processes':{},'hardFailures':[],'oracle':None,'probe':None,'performanceThresholds':'none; HTTP errors, drops, socket loss and recovery timeouts are observed outputs, not capacity SLOs'}
    def save(self):
        self.value['artifacts']={str(file.relative_to(self.d)):self.a.digest(file) for folder in ('idle','load') for name in ('evaluator-progress.json','probe.json','k6-summary.json','after-cgroups.json','after-pg-role.tsv','after-pg-statements.tsv') if (file:=self.d/folder/name).is_file()}
        self.a.write(self.d/'summary.json',self.value)
    def failure(self,stage,error,hard=False):
        row={'verdict':getattr(error,'verdict','UNMEASURED'),'code':safe_code(error),'hardFailure':hard};self.value['strictChecks'][stage]=row
        if hard:self.value['hardFailures'].append({'stage':stage,'code':row['code']})
        self.save()
    def observe(self,stage,fn):
        try:
            result=fn();self.value['strictChecks'][stage]={'verdict':'PASS'};self.save();return result
        except Exception as error:
            allowed=incomplete(error);partial=None
            if str(error)=='M7_EVALUATOR_PROGRESS_ROUNDS' and getattr(error,'verdict',None)=='UNMEASURED':
                try:partial=partial_progress(self.a,self.d,self.m,stage);allowed=True
                except Exception as invalid:
                    self.failure(stage,invalid,True);raise invalid from error
            self.failure(stage,error,not allowed)
            if partial is not None:
                self.value['strictChecks'][stage]['partialObservation']=partial;self.save()
            if not allowed:raise
    def process(self,stage,fn):
        start=time.time()
        try:
            result=fn();self.value['processes'][stage]={'returncode':0,'startedAt':start,'endedAt':time.time()};return result
        except (RuntimeError,subprocess.TimeoutExpired) as error:
            self.value['processes'][stage]={'returncode':getattr(error,'returncode',None),'startedAt':start,'endedAt':time.time(),'timeout':isinstance(error,subprocess.TimeoutExpired),'code':safe_code(error)}
            self.value['strictChecks'][stage]={'verdict':'UNMEASURED','code':'M7_DISCOVERY_PROCESS_INCOMPLETE'}
        finally:self.save()

def run_discovery(a,d,m,k6_image):
    record=Record(a,d,m);record.save()
    try:
        require(m.get('profile')!='fresh-image-diagnostic','M7_DIAGNOSTIC_CANNOT_RUN_CAPACITY')
        a.frozen(m,'run');a.quiet(d,m,'run-before',check_load=False);a.verify(d,m);a.image(m)
        record.value['ownershipVerified']=True;record.save()
        require((d/'deploy-before-host.json').is_file(),'M7_DEPLOY_QUIET_RECORD_REQUIRED')
        a.verify_generator(d,m);record.observe('readiness',lambda:a.readiness(d,m))
        k6_id=json.loads(a.command(['docker','image','inspect',k6_image]))[0]['Id'];a.write(d/'loadgen-image.json',{'k6':k6_id,'generator':m['generator']})
        out=d/'idle-disabled';out.mkdir();a.psql(d,'SELECT pg_stat_statements_reset();');a.phase_snapshot(d,out,'before')
        try:a.time.sleep(60)
        finally:a.phase_snapshot(d,out,'after')
        out=d/'idle';out.mkdir();a.quiet(d,m,'idle-before',check_load=False);a.psql(d,'SELECT pg_stat_statements_reset();')
        record.observe('idle',lambda:a.enabled_idle(d,m,out,m['cadence']['idleSeconds']))
        discovery_load(a,d,m,k6_id,record)
        for phase in ('idle','load'):
            if (d/phase/'evaluator-progress.json').is_file():record.value.setdefault('evaluatorProgress',{})[phase]=a.progress_summary(d/phase)
        from reduce import measurements
        try:record.value['measurements']=measurements(d,m)
        except Exception as error:record.value['measurements']={'complete':False,'code':safe_code(error)}
        # Independent owned counts and resource reduction remain observable
        # before classifying the already recorded fingerprint finding.
        record.save()
        require(record.value.get('settingsFingerprintObservation',{}).get('verdict')!='FAIL','M7_FUNCTIONAL_SETTINGS_FINGERPRINT')
        if record.value.get('settingsFingerprintObservation',{}).get('verdict')=='PASS' and record.value['measurements'].get('complete') and record.value['oracle'] is not None and record.value['probe'] is not None and record.value['probe'].get('restart') is not None and all(record.value['processes'].get(k,{}).get('returncode')==0 for k in ('k6','probe')):record.value['status']='MEASURED'
        record.save();check_discovery(record.value);return record.value
    except Exception as error:
        if not record.value['hardFailures']:record.failure('collection',error,True)
        record.save();raise

def discovery_load(a,d,m,k6_id,record):
    out=d/'load';out.mkdir();runid='m7-'+m['owner'][:12];(out/'runid').write_text(runid)
    spec=m['project']+'|'+str(d/'env')+'|'+str(d/'frozen.compose.json')
    env=a.runtime_env({'NODE_PATH':str(d/'dependencies/node_modules'),'M7_RUN_PURPOSE':'discovery','M7_RESTART_ROLES':json.dumps(m['restartRoles']),'M7_EVALUATOR_SERVICES':json.dumps(a.progress_services(d)),'M7_PROGRESS_PYTHON':a.sys.executable,'M7_PROGRESS_ATTRIBUTION':json.dumps(a.progress_attribution(m)),'STOCK_MS':'300000','RECOVERY_MS':'120000'})
    a.psql(d,'SELECT pg_stat_statements_reset();');a.phase_snapshot(d,out,'before-prime')
    process=None;monitor=None;load_started=False;primed=False;probe_stopped=False
    try:
        with (out/'probe.log').open('wb') as probe_log,a.sampling(d,out):
            process=a.subprocess.Popen([m['generator']['tools']['node']['path'],str(d/'probe.js'),'--base','http://127.0.0.1:'+str(m['port']),'--tenants',str(d/'tenants.private.json'),'--compose',spec,'--runid',runid,'--per','2','--open','5','--window',str(m['cadence']['loadSeconds']),'--probeEvery','3000','--restart','1','--evalTimeout','900','--out',str(out/'probe.json'),'--signal',str(out/'.window')],env=env,stdout=probe_log,stderr=a.subprocess.STDOUT,start_new_session=True)
            a.job_record(out/'probe-job.json',process,m['owner'],group=True);deadline=a.time.monotonic()+600
            while not (out/'.window').is_file() and process.poll() is None and a.time.monotonic()<deadline:a.time.sleep(1)
            primed=(out/'.window').is_file()
            if (out/'probe.json').is_file():
                record.value['probe']=a.document(out/'probe.json');record.save()
                require(not record.value['probe'].get('hardFailure'),'M7_DISCOVERY_PROBE_HARD_FAILURE')
            if not primed:
                record.value['strictChecks']['prime']={'verdict':'UNMEASURED','code':'M7_PROBE_NOT_PRIMED'}
                a.stop_job(out/'probe-job.json',m['owner']);process.wait(timeout=10);probe_stopped=True
                record.value['processes']['probe']={'returncode':process.returncode,'stoppedByRunner':True,'primeComplete':False};record.save()
            a.quiet(d,m,'load-before',check_load=False);a.phase_snapshot(d,out,'after-prime');a.psql(d,'SELECT pg_stat_statements_reset();');a.phase_snapshot(d,out,'before');load_started=True
            monitor=a.loadgen_process(d,process);monitor.__enter__()
            try:
                def work():
                    with (out/'k6.log').open('wb') as output:record.process('k6',lambda:a.command(k6_command(a,d,m,k6_id,runid),file=output,timeout=m['cadence']['loadSeconds']+600))
                    if record.value['processes']['k6'].get('timeout'):stop_k6(a,m,record)
                record.observe('load',lambda:observed_load(a,d,m,out,work))
            finally:a.phase_snapshot(d,out,'after')
            # Recheck owned custody before the existing bounded restart protocol.
            a.assert_owned(m)
            if primed and not probe_stopped and process.poll() is None:
                (out/'.restart').touch();start=time.time()
                try:rc=process.wait(timeout=1500)
                except a.subprocess.TimeoutExpired:rc=None
                record.value['processes']['probe']={'returncode':rc,'startedRecoveryAt':start,'endedAt':time.time(),'timeout':rc is None};record.save()
            else:
                record.value['strictChecks']['recovery']={'verdict':'UNMEASURED','code':'M7_DISCOVERY_RECOVERY_NOT_STARTED'};record.save()
    finally:
        if process is not None:
            a.stop_job(out/'probe-job.json',m['owner']);process.wait(timeout=10)
            if 'probe' not in record.value['processes']:record.value['processes']['probe']={'returncode':process.returncode,'stoppedByRunner':True};record.save()
        if monitor:monitor.__exit__(None,None,None)
        if load_started:a.phase_snapshot(d,out,'after-reconnect')
        if (out/'probe.json').is_file():
            record.value['probe']=a.document(out/'probe.json');record.save()
            require(not record.value['probe'].get('hardFailure'),'M7_DISCOVERY_PROBE_HARD_FAILURE')
    if (out/'probe.json').is_file():
        record.value['probe']=a.document(out/'probe.json');record.save()
        require(not record.value['probe'].get('hardFailure'),'M7_DISCOVERY_PROBE_HARD_FAILURE')
        recovery=record.value['probe'].get('restart',{}).get('runtimeAcquisitionObservation',{})
        require(not hard_recovery(recovery),'M7_DISCOVERY_CLINICAL_FAILURE')
        if recovery:record.value['strictChecks']['recovery']={**{k:recovery[k] for k in ('verdict','code') if k in recovery},'hardFailure':False}
    if (out/'k6-summary.json').is_file():
        metrics=a.document(out/'k6-summary.json')['metrics'];record.value['metrics']={key:metrics[key] for key in ('http_reqs','http_req_failed','dropped_iterations','writes_ok','writes_refused','writes_uncertain','responses_refused') if key in metrics}
        fingerprint=a.profile_provenance.fingerprint_check(metrics);record.value['settingsFingerprintObservation']=fingerprint;record.save()
        result,known=count_observation(a,d,out,runid,metrics)
        record.value['oracle']=result if known else None
        record.value['oracleFindings']=result;record.save()
        if not known:record.value['strictChecks']['counts']={'verdict':'UNMEASURED','code':'M7_DISCOVERY_COUNTS_MISSING'}

    record.save()

def observed_load(a,d,m,out,work):
    observer=a.observe_progress(d,m,out,'load')
    try:observer.__enter__()
    except Exception as error:
        if not incomplete(error):raise
        work();raise
    else:
        try:work()
        except BaseException as error:
            observer.__exit__(type(error),error,error.__traceback__);raise
        else:observer.__exit__(None,None,None)

def k6_command(a,d,m,image,runid):
    return ['docker','run','--rm','--name',m['project']+'-k6','--label',OWNER+'='+m['owner'],'--label','com.docker.compose.project='+m['project'],'--label','com.docker.compose.service=k6','--network','host','-u',str(a.os.getuid())+':'+str(a.os.getgid()),'-v',str(d/'k6')+':/scripts:ro','-v',str(d/'load')+':/out','-v',str(d/'tenants.private.json')+':/tenants.private.json:ro','-e','BASE_URL=http://127.0.0.1:'+str(m['port']),'-e','TENANTS_FILE=/tenants.private.json','-e','RUN_ID='+runid,'-e','SETTINGS_FINGERPRINT='+m['settingsFingerprint']['sha256'],'-e','RUN_START='+str(int(time.time()*1000)),'-e','DURATION='+str(m['cadence']['loadSeconds']),'-e','ACCEL=1','-e','HOT_FACTOR=10','-e','SHAPES=w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status',image,'run','--quiet','--summary-export','/out/k6-summary.json','/scripts/workload.js']


def count_observation(a,d,out,runid,metrics):
    """Reuse the one stored-count query; missing ack metadata is never zero."""
    tenants=a.document(d/'tenants.private.json');expected={r['id'] for r in tenants};values=a.stored(d,runid);a.write(out/'stored-counts.json',values)
    known_probes=(out/'fanout.json').is_file();probes=a.document(out/'fanout.json')['probeWrites']['byTenant'] if known_probes else {}
    require(set(values)<=expected and set(probes)<=expected,'M7_ORACLE_TENANT_SCOPE')
    missing=[];uncertain_total=0;all_uncertain=True;domains={k:0 for k in ('entries','devicestatus','treatments')}
    for tenant in sorted(expected):
        row=values.get(tenant,{})
        require(set(row)<=set(domains)|{'probe'} and all(type(v) is int and v>=0 for v in row.values()),'M7_ORACLE_COUNTS_INVALID')
        ok='writes_ok{tenant:'+tenant+'}';uncertain='writes_uncertain{tenant:'+tenant+'}'
        absent=[key for key in (ok,uncertain) if key not in metrics];missing+=absent
        if uncertain in metrics:uncertain_total+=a.metric(metrics,uncertain)
        else:all_uncertain=False
        if not absent:
            accepted=a.metric(metrics,ok);ambiguous=a.metric(metrics,uncertain);stored=sum(row.get(kind,0) for kind in domains)
            require(accepted<=stored<=accepted+ambiguous,'M7_DISCOVERY_WRONG_DATA')
        if known_probes:require(row.get('probe',0)==probes.get(tenant,0),'M7_DISCOVERY_WRONG_DATA')
        for kind in domains:domains[kind]+=row.get(kind,0)
    for kind,count in domains.items():
        key='writes_ok{kind:'+kind+'}'
        if key not in metrics:missing.append(key)
        elif all_uncertain:require(a.metric(metrics,key)<=count<=a.metric(metrics,key)+uncertain_total,'M7_DISCOVERY_WRONG_DATA')
    if missing:return {'verdict':'UNMEASURED','code':'M7_DISCOVERY_ACK_METADATA_MISSING','missingFieldCount':len(missing),'missingFields':missing[:64],'probeCountProof':'KNOWN' if known_probes else 'UNMEASURED'},False
    derived={**metrics}
    if 'writes_ok' not in derived:derived['writes_ok']={'count':sum(a.metric(metrics,'writes_ok{tenant:'+tenant+'}') for tenant in expected)}
    result=a.oracle(values,derived,probes,tenants,strict=False,allow_empty=True,probes_known=known_probes)
    require(result['verdict']=='GREEN','M7_DISCOVERY_WRONG_DATA');return result,True


def stop_k6(a,m,record):
    """A timed-out Docker CLI is not proof its owned container stopped."""
    a.assert_owned(m)
    rows=[row for row in a.resources(m) if (row.get('Config',{}).get('Labels') or {}).get('com.docker.compose.service')=='k6']
    require(len(rows)<=1,'M7_DISCOVERY_LOADGEN_CUSTODY')
    for row in rows:
        a.owned(row,m['owner']);require(re.fullmatch(r'[a-f0-9]{64}',row.get('Id','')),'M7_DISCOVERY_LOADGEN_CUSTODY')
        a.command(['docker','stop','--time','10',row['Id']],timeout=20)
    record.value['processes']['k6']['ownedContainerStopCompleted']=True;record.save()


def hard_recovery(value):return value.get('verdict')=='FAIL' and value.get('code') not in SOFT_WORK_FAILURES


def partial_progress(a,d,m,stage):
    """Only genuine, bounded 1/2-round current-source captures may continue."""
    import evaluator_idle as idle
    import evaluator_progress as progress
    need=progress.need
    need(stage in ('idle','load'),'M7_DISCOVERY_PARTIAL_PROGRESS_SCOPE')
    file=d/stage/'evaluator-progress.json'
    need(file.is_file() and not file.is_symlink() and file.stat().st_size<=16777216,'M7_DISCOVERY_PARTIAL_PROGRESS_ARTIFACT')
    value=a.document(file);module=idle if stage=='idle' else progress
    kind=idle.ARTIFACT_KIND if stage=='idle' else 'evaluator-progress-phase-v2'
    need(value.get('kind')==kind and value.get('columns')==list(module.COLUMNS) and value.get('policy')==module.POLICY and value.get('phase')==stage and value.get('verdict')=='UNMEASURED' and value.get('code')=='M7_EVALUATOR_PROGRESS_ROUNDS' and value.get('attribution')==a.progress_attribution(m),'M7_DISCOVERY_PARTIAL_PROGRESS_SCOPE')
    need(isinstance(value.get('rounds'),list) and 1<=len(value['rounds'])<=2,'M7_DISCOVERY_PARTIAL_PROGRESS_ROUNDS')
    services=a.progress_services(d);need(1<=len(services)<=progress.POLICY['maxInstances'],'M7_EVALUATOR_PROGRESS_INSTANCE_BOUND')
    decoded,ids=(idle._decode(value,m['tenants'],services) if stage=='idle' else progress.decode_rounds(value,m['tenants'],services))
    expected=[row['id'] for row in a.document(d/'tenants.private.json')];progress.validate_ids(expected)
    need(ids==set(expected),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    need(sum(r['queries'] for r in decoded)<=progress.POLICY['maxQueriesPerPhase'] and sum(r['bytes'] for r in decoded)<=progress.POLICY['maxBytesPerPhase'],'M7_EVALUATOR_PROGRESS_BUDGET')
    if stage=='idle':idle.clock_windows(decoded)
    # Check ALL available rounds, not only the first timing refusal. No absent
    # round, unselected interval or clock witness is manufactured.
    previous=decoded[0];failed_work=0
    for current in decoded:
        need(current['instances']==previous['instances'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
        for service,rows in previous['allRows'].items():
            for tenant,before in rows.items():
                after=current['allRows'][service][tenant]
                need((before['admitted'],before['generation'])==(after['admitted'],after['generation']) and all(after[k]>=before[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
                if not before['admitted']:
                    need(not after['ready'] and all(after[k]==before[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
                    if stage=='idle':need(not any(idle.jobs(after['jobs']).values()),'M7_EVALUATOR_IDLE_FOREIGN_PENDING','FAIL')
                else:failed_work+=after['failedCompletions']
        previous=current
    return {'rounds':len(decoded),'scope':'available snapshots only; missing phase observation remains UNMEASURED','workFailurePresent':failed_work>0,'loadClockProof':'not supplied by load source schema' if stage=='load' else 'captured idle brackets validated'}
