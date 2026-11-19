"""Explicit observational load route. Never grants capacity acceptance."""
import json
import viewer_plan
import workload_inputs
import re
import subprocess
import sys
import time
import discovery_rest
import evaluator_catchup
import driver_memory
import driver_vu_diagnostic
import node_observation
import phase_windows
from contract import require, SHA, OWNER, REPLICAS, UNACCEPTED_SCOPE, discovery_scope, check_discovery_scope, discovery_api_replicas

INCOMPLETE=frozenset(('M7_EVALUATOR_IDLE_JOB_PENDING','M7_EVALUATOR_IDLE_NEW_DEMAND','M7_EVALUATOR_IDLE_FINAL_COMPLETION_PENDING','M7_EVALUATOR_IDLE_TAIL_REQUIRED','M7_EVALUATOR_IDLE_TAIL_COMPLETION','M7_EVALUATOR_IDLE_TAIL_BODY','M7_EVALUATOR_IDLE_TAIL_JOB_PENDING','M7_EVALUATOR_IDLE_TAIL_DEADLINE','M7_EVALUATOR_IDLE_TAIL_OWNER_BOUND','M7_EVALUATOR_IDLE_TAIL_OPPORTUNITY','M7_EVALUATOR_IDLE_TIME_NOT_OBSERVED','M7_EVALUATOR_IDLE_UNCREDITED_WORK','M7_EVALUATOR_IDLE_UNATTRIBUTED_TIME','M7_EVALUATOR_PROGRESS_NOT_OBSERVED','M7_RUNTIME_NOT_READY','M7_EVALUATOR_PROGRESS_UNAVAILABLE','M7_EVALUATOR_PROGRESS_COLLECTOR_TIMEOUT'))
INCOMPLETE=INCOMPLETE|frozenset(('M7_OPPORTUNITY_NOT_OBSERVED','M7_OPPORTUNITY_DEADLINE','M7_OPPORTUNITY_BYTE_BOUND','M7_OPPORTUNITY_COVERAGE','M7_OPPORTUNITY_CAPTURE','M7_OPPORTUNITY_QUERY_BOUND'))
INCOMPLETE=INCOMPLETE|frozenset(('M7_EVALUATOR_PROGRESS_QUERY_BOUND','M7_EVALUATOR_PROGRESS_BYTE_BOUND','M7_EVALUATOR_PROGRESS_BUDGET'))

def safe_code(error):
    text=str(error)
    return text if re.fullmatch(r'M7_[A-Z_]+(?::[a-zA-Z0-9_.-]+)?',text) else 'M7_DISCOVERY_INSTRUMENT_ERROR'

# Counter-only ambiguity lives in observer fields; actual errors stay hard.
SOFT_WORK_FAILURES=frozenset()

def incomplete(error):return str(error) in SOFT_WORK_FAILURES or (getattr(error,'verdict','UNMEASURED')!='FAIL' and str(error) in INCOMPLETE)

def recovery_episode(value,ids,binding,*,budget=None):
    """Allow more discovery collection after a sampled local cache discard.

    This never clears the strict failure or certifies an unseen interval. Actual
    process replacement, counter rewind, foreign work and restore changes stop.
    """
    import evaluator_idle as idle
    import evaluator_progress as p
    import evaluator_opportunities as o
    p.validate_ids(ids)
    require(value.get('kind')=='evaluator-opportunity-phase-v1' and value.get('phase')=='load'
            and value.get('code')=='M7_EVALUATOR_PROGRESS_RESET' and value.get('verdict')=='FAIL'
            and value.get('failedCollection') is None,'M7_DISCOVERY_RECOVERY_SHAPE')
    require(value.get('durableBinding')==binding,'M7_DISCOVERY_RECOVERY_BINDING')
    policy=p.capture_policy(budget)
    require(value.get('capturePolicy',p.POLICY)==policy and value.get('attribution',{}).get('evaluatorProgressBudget')==budget,
            'M7_DISCOVERY_RECOVERY_BUDGET')
    require(all(value.get('attribution',{}).get(k)==binding[k] for k in ('pair','imageId','instrument')),'M7_DISCOVERY_RECOVERY_BINDING')
    require(all(value.get('attribution',{}).get(k)==binding[k] for k in ('pair','imageId','instrument')),'M7_DISCOVERY_RECOVERY_BINDING')
    services=list(value['rounds'][0]['instances']);rounds,actual=idle._decode(value,len(ids),services)
    require(len(rounds)==3 and actual==set(ids),'M7_DISCOVERY_RECOVERY_COVERAGE')
    require(sum(r['queries'] for r in rounds)<=policy['maxQueriesPerPhase']
            and sum(r['bytes'] for r in rounds)<=policy['maxBytesPerPhase'],'M7_DISCOVERY_RECOVERY_BUDGET')
    durable=o.durable_rows(value['durable'],ids,binding);o.capture_windows(value['captureWindows'],3)
    changes=[]
    for previous,current in zip(rounds,rounds[1:]):
        require(current['instances']==rounds[0]['instances'],'M7_DISCOVERY_PROCESS_REPLACED')
        for service,rows in previous['allRows'].items():
            for tenant,before in rows.items():
                after=current['allRows'][service][tenant]
                require(after['admitted']==before['admitted'],'M7_DISCOVERY_ADMISSION_CHANGED')
                require(all(after[k]>=before[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_DISCOVERY_COUNTER_REWOUND')
                if not before['admitted']:
                    require(after==before,'M7_DISCOVERY_FOREIGN_CHANGED')
                elif after['generation']!=before['generation']:
                    changes.append({'tenant':tenant,'before':before['generation'],'after':after['generation']})
    require(changes,'M7_DISCOVERY_NO_LOCAL_RECOVERY')
    for tenant in ids:
        require(durable[0][tenant]['restoreGeneration']==durable[-1][tenant]['restoreGeneration'],'M7_DISCOVERY_RESTORE_CHANGED')
    return {'kind':'local-runtime-recovery','changes':changes,'strictVerdict':'FAIL',
            'interval':'UNMEASURED between snapshots','scope':'continued bounded discovery; no correctness or capacity promotion'}

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
    require(re.fullmatch(r'[a-f0-9]{32}',value.get('owner','')) and value.get('ownershipVerified') is True,'M7_DISCOVERY_OWNERSHIP')
    api_ok=(discovery_api_replicas(value.get('replicas')) if value.get('profile')=='pgstream-sample'
            else type(value.get('replicas')) is int and value['replicas'] in REPLICAS)
    require(workload_inputs.tenants(value.get('tenants')) and api_ok,'M7_DISCOVERY_TOPOLOGY')
    require(isinstance(value.get('strictChecks'),dict) and isinstance(value.get('processes'),dict) and isinstance(value.get('hardFailures'),list),'M7_DISCOVERY_OBSERVATIONS')
    require(not value['hardFailures'],'M7_DISCOVERY_HARD_FAILURE')
    oracle=value.get('oracle')
    if oracle is not None:
        require(oracle.get('verdict')=='GREEN' and not oracle.get('failures'),'M7_DISCOVERY_WRONG_DATA')
        if 'rows' in oracle:
            rows=oracle['rows'];require(isinstance(rows,list) and len(rows)==value['tenants'] and len({r.get('tenant') for r in rows})==len(rows),'M7_DISCOVERY_COUNT_ROSTER')
            require(oracle.get('probeCountProof')=='KNOWN' and oracle.get('probeAccounting',{}).get('version')==2 and oracle['probeAccounting'].get('admissionsClosed') is True and oracle['probeAccounting'].get('pending')==0,'M7_DISCOVERY_PROBE_COUNTS_UNMEASURED')
            for row in rows:
                require(all(type(row.get(k)) in (int,float) and row[k]>=0 for k in ('accepted','stored','uncertain')) and row['accepted']<=row['stored']<=row['accepted']+row['uncertain'] and row.get('match') is True,'M7_DISCOVERY_WRONG_DATA')
                require(all(type(row.get(k)) is int and row[k]>=0 for k in ('probeAccepted','probeStored','probeUncertain','probeRefused','probePending')) and row['probePending']==0 and row['probeAccepted']<=row['probeStored']<=row['probeAccepted']+row['probeUncertain'],'M7_DISCOVERY_WRONG_DATA')
    if value.get('profile')=='pgstream-sample':
        check_discovery_scope(value)
        if value['status']=='MEASURED':
            require(not any('recoveryEpisode' in row for row in value['strictChecks'].values()),'M7_DISCOVERY_RECOVERED_CELL_NOT_ACCEPTED')
            require(value.get('completedOutput',{}).get('verdict')=='PASS' and value.get('oracleControl')=={'baseline':'GREEN','broken':'RED','restored':'GREEN'} and value.get('sqlAttribution'),'M7_DISCOVERY_SAMPLE_PROOF')
    probe=value.get('probe') or {};require(not probe.get('hardFailure') and not hard_recovery(probe.get('restart',{}).get('runtimeAcquisitionObservation',{})),'M7_DISCOVERY_HARD_FAILURE')
    for row in value['strictChecks'].values():
        require(isinstance(row,dict) and row.get('verdict') in ('PASS','FAIL','UNMEASURED'),'M7_DISCOVERY_CHECK_SHAPE')
        require(row.get('hardFailure') is not True,'M7_DISCOVERY_HARD_FAILURE')
    if value['status']=='MEASURED':require(value.get('measurements',{}).get('complete') is True and oracle is not None and value.get('probe') is not None and all(value['processes'].get(k,{}).get('returncode')==0 for k in ('k6','probe')),'M7_DISCOVERY_MISSING_MEASUREMENT')
    return True

class Record:
    def __init__(self,a,d,m):
        self.a,self.d,self.m=a,d,m
        self.value={'version':1,'kind':'m7-joined-discovery-cell','runPurpose':'discovery','status':'PARTIAL','capacityAcceptance':'NOT_GRANTED',**{k:m[k] for k in ('pair','hostIdentity','imageId','tenants','replicas','owner','profile','cadence')},'instrument':m['instrument']['sha256'],'profileSelection':m['profileSelection'],'coverage':{'fullNominalCgmCycle':m['cadence']['loadSeconds']>=300/m['cadence'].get('accel',1),'timerWitness':'UNMEASURED; observed progress is retained separately'},'ownershipVerified':False,'strictChecks':{},'processes':{},'hardFailures':[],'oracle':None,'probe':None,**(discovery_scope(m) if m['profile']=='pgstream-sample' else {}),**({'staticTopology':m['staticTopology']} if m.get('staticTopology') else {}),'performanceThresholds':'none; HTTP errors, drops, socket loss and recovery timeouts are observed outputs, not capacity SLOs'}
    def save(self):
        self.value['artifacts']={str(file.relative_to(self.d)):self.a.digest(file) for folder in ('idle','load') for name in ('evaluator-progress.json','probe.json','k6-summary.json','http-accounting.json','after-cgroups.json','after-pg-role.tsv','after-pg-statements.tsv','stored-counts.json','oracle-findings.json','probe-accounting.json','fanout.json','demand-recovery.json','node-observation.json','k6-scheduling.csv.gz','driver-vu-assessment.json',driver_memory.RESULT,driver_memory.SAMPLES,'host-load.tsv','pg-activity.tsv','pg-blockers.tsv') if (file:=self.d/folder/name).is_file()}
        preload = self.d/'preload-convergence/result.json'
        if preload.is_file():
            self.value['artifacts']['preload-convergence/result.json'] = self.a.digest(preload)
        self.value['collectionSegments']={str(file.relative_to(self.d)):self.a.digest(file) for folder in ('idle-disabled','idle','load') for file in (self.d/folder).glob('*-collection.json') if file.is_file()}
        self.a.write(self.d/'summary.json',self.value)
    def failure(self,stage,error,hard=False):
        row={'verdict':getattr(error,'verdict','UNMEASURED'),'code':safe_code(error),'hardFailure':hard};self.value['strictChecks'][stage]=row
        if hard:self.value['hardFailures'].append({'stage':stage,'code':row['code']})
        self.save()
    def observe(self,stage,fn):
        try:
            result=fn();finding=getattr(result,'result',result)
            if discovery_rest.result(finding):
                require(discovery_rest.selected(self.m),'M7_DISCOVERY_CLINICAL_CONTINUATION_SCOPE')
                self.value['strictChecks'][stage]={**{k:finding[k] for k in ('verdict','clinicalVerdict','clinicalCode','restCollectionPermitted')},'hardFailure':False}
                self.value['clinicalVerdict']='FAIL';self.value['capacityAcceptance']='NOT_GRANTED';self.save();return result
            self.value['strictChecks'][stage]={'verdict':'UNMEASURED','code':'M7_EVALUATOR_AVAILABILITY_UNMEASURED','hardFailure':False} if stage=='readiness' and isinstance(result,dict) and result.get('verdict')=='UNMEASURED' else {'verdict':'PASS'};self.save();return result
        except Exception as error:
            allowed=incomplete(error);partial=None
            episode=None
            if str(error)=='M7_EVALUATOR_PROGRESS_RESET' and stage=='load' and self.m.get('evaluatorOpportunities')=='received-input-v1':
                try:
                    ids=sorted(row['id'] for row in self.a.document(self.d/'tenants.private.json'))
                    binding={'kind':'evaluator-work-v2','pair':self.m['pair'],'imageId':self.m['imageId'],'instrument':self.m['instrument']['sha256']}
                    episode=recovery_episode(self.a.document(self.d/stage/'evaluator-progress.json'),ids,binding,
                                             budget=self.m.get('cadence',{}).get('evaluatorProgressBudget'))
                    self.a.assert_owned(self.m);allowed=True
                except Exception:
                    # The original refusal remains authoritative when this
                    # narrow evidence classification cannot be established.
                    pass
            if str(error)=='M7_EVALUATOR_PROGRESS_ROUNDS' and getattr(error,'verdict',None)=='UNMEASURED':
                try:partial=partial_progress(self.a,self.d,self.m,stage);allowed=True
                except Exception as invalid:
                    self.failure(stage,invalid,True);raise invalid from error
            self.failure(stage,error,not allowed)
            if episode is not None:
                self.value['strictChecks'][stage]['recoveryEpisode']=episode;self.save()
            if partial is not None:
                self.value['strictChecks'][stage]['partialObservation']=partial;self.save()
            if not allowed:raise
    def process(self,stage,fn):
        start=time.time();start_mono=time.monotonic_ns()
        try:
            result=fn();self.value['processes'][stage]={'returncode':0,'startedAt':start,'endedAt':time.time()};return result
        except (RuntimeError,subprocess.TimeoutExpired) as error:
            self.value['processes'][stage]={'returncode':getattr(error,'returncode',None),'startedAt':start,'endedAt':time.time(),'timeout':isinstance(error,subprocess.TimeoutExpired),'code':safe_code(error)}
            self.value['strictChecks'][stage]={'verdict':'UNMEASURED','code':'M7_DISCOVERY_PROCESS_INCOMPLETE'}
        finally:
            if stage in self.value['processes']:self.value['processes'][stage].update(startMonoNs=start_mono,endMonoNs=time.monotonic_ns())
            self.save()

def run_discovery(a,d,m,k6_image,oneoff=None):
    # The standalone driver has its own prospective declaration. Do not mutate
    # the original session's server profile or resource/cleanup ownership.
    with a.diagnostic_resources.discovery_driver(m) as allocation:
        if allocation is not None:a.write(d/'loadgen-resource-allocation.json',allocation)
        return _run_discovery(a,d,m,k6_image,oneoff)


def _run_discovery(a,d,m,k6_image,oneoff=None):
    record=Record(a,d,m)
    if driver_memory.selected(m):
        record.value['driverMemory'] = {'status':'UNMEASURED', 'reason':'driver-observation-not-retained'}
    record.save()
    try:
        require(m.get('profile')!='fresh-image-diagnostic','M7_DIAGNOSTIC_CANNOT_RUN_CAPACITY')
        require(not driver_memory.selected(m) or (oneoff is None and not m.get('attached')),
                'M7_DRIVER_MEMORY_LOCAL_FIXTURE_REQUIRED')
        a.frozen(m,'run');a.quiet(d,m,'run-before',check_load=False);a.verify(d,m);a.image(m)
        record.value['ownershipVerified']=True;record.save()
        require((d/'deploy-before-host.json').is_file(),'M7_DEPLOY_QUIET_RECORD_REQUIRED')
        a.verify_generator(d,m)
        if a.preload_convergence.selection(m):
            result = record.observe('preloadConvergence', lambda: a.preload_convergence.run(a,d,m))
            record.value['preloadConvergence'] = result
            record.save()
        # Fresh and unchanged: pre-load history never supplies this readiness result.
        record.observe('readiness',lambda:a.readiness(d,m))
        k6_id=json.loads(a.command(['docker','image','inspect',k6_image]))[0]['Id'];a.write(d/'loadgen-image.json',{'k6':k6_id,'generator':m['generator']})
        if m['profile']=='pgstream-sample':completion,sql_roles=a.sample_preflight(d,m,k6_id,**({'oneoff':oneoff}if oneoff else{}))
        out=d/'idle-disabled';out.mkdir();a.psql(d,'SELECT pg_stat_statements_reset();');a.phase_snapshot(d,out,'before')
        try:a.time.sleep(m['cadence'].get('warmupSeconds',60))
        finally:a.phase_snapshot(d,out,'after')
        out=d/'idle';out.mkdir();a.quiet(d,m,'idle-before',check_load=False);a.psql(d,'SELECT pg_stat_statements_reset();')
        record.observe('idle',lambda:a.enabled_idle(d,m,out,m['cadence']['idleSeconds']))
        if m.get('serialExchangeDiagnostic') is not None:
            serial_exchange_diagnostic(a,d,m,record)
            record.value.update(status='PARTIAL',diagnosticOnly=True,ordinaryTraffic='NOT_RUN',
                measurements={'complete':False,'code':'M7_SERIAL_EXCHANGE_DIAGNOSTIC_ONLY'})
            record.save();check_discovery(record.value);return record.value
        try:
            discovery_load(a,d,m,k6_id,record,**({'oneoff':oneoff}if oneoff else{}))
        finally:
            # File-only reductions also run on a hard stop. They never re-open
            # the fixture or replace the original load failure.
            record.value.update(retained_results(a, d, m, record.value))
            record.save()
        if m['profile']=='pgstream-sample':
            probe=record.value.get('probe')
            if probe:
                record.value['completedOutput']=probe.get('completedOutput', {'verdict':'UNMEASURED'})
                record.save()
                try:
                    record.value['sqlAttribution']=a.sample_results(d,probe,sql_roles)
                except Exception as error:
                    record.failure('sqlAttribution',error,True)
                    require(record.value['completedOutput']['verdict']=='PASS','M7_COMPLETED_OUTPUT_ORACLE')
                    raise
                record.save()
                if record.value['completedOutput'].get('clinicalTiming') and record.value['completedOutput']['verdict']=='UNMEASURED':
                    record.value['strictChecks']['sampledOracle']={'verdict':'UNMEASURED','code':'M7_CLINICAL_OBSERVATION_INCOMPLETE'}
                else:
                    require(record.value['completedOutput']['verdict']=='PASS','M7_COMPLETED_OUTPUT_ORACLE')
            counts=record.value.get('oracle')
            from discovery_counts import control_domain
            if control_domain(counts,m['tenants']) is not None:
                a.control(d,m);record.value['oracleControl']=a.document(d/'load/oracle-control.json')
            else:record.value['strictChecks']['oracleControl']={'verdict':'UNMEASURED','code':'M7_DISCOVERY_COUNTS_MISSING'}
        if not any('recoveryEpisode' in row for row in record.value['strictChecks'].values()) and record.value['measurements'].get('complete') and record.value['oracle'] is not None and record.value['probe'] is not None and (record.value['probe'].get('restart') is not None or m['profile']=='pgstream-sample' and record.value.get('completedOutput',{}).get('verdict')=='PASS' and record.value.get('oracleControl')=={'baseline':'GREEN','broken':'RED','restored':'GREEN'}) and all(record.value['processes'].get(k,{}).get('returncode')==0 for k in ('k6','probe')):record.value['status']='MEASURED'
        if record.value['hardFailures'] or any('recoveryEpisode' in row for row in record.value['strictChecks'].values()) or record.value.get('clinicalVerdict')=='FAIL':record.value['status']='PARTIAL'
        record.save();check_discovery(record.value);return record.value
    except Exception as error:
        record.value['status']='PARTIAL'
        if not any(row['code']==safe_code(error) for row in record.value['hardFailures']):record.failure('collection',error,True)
        record.save();raise

def retained_results(a, d, m, summary):
    """Read completed observations independently, including on a partial run."""
    from reduce import measurements
    from viewer_plan import check
    result = {}
    def read(key, fn):
        try:
            result[key] = fn()
        except Exception as error:
            result[key] = {'verdict': getattr(error, 'verdict', 'UNMEASURED'), 'code': safe_code(error)}

    read('measurements', lambda: measurements(d, m))
    result['measurements'].setdefault('complete', False)
    progress = {}
    for phase in ('idle', 'load'):
        if (d/phase/'evaluator-progress.json').is_file():
            try:
                progress[phase] = a.progress_summary(d/phase)
            except Exception as error:
                progress[phase] = {'verdict': 'UNMEASURED', 'code': safe_code(error)}
    result['evaluatorProgress'] = progress
    out = d/'load'
    if driver_memory.selected(m) and (out / driver_memory.RESULT).is_file():
        read('driverMemory', lambda: a.document(out / driver_memory.RESULT))
    probe = summary.get('probe') or {}
    if probe:
        result['completedOutput'] = probe.get('completedOutput', {'verdict':'UNMEASURED'})
    if not summary.get('viewerFrames') and probe.get('window') and (out/'fanout.json').is_file():
        def frames():
            try:
                return check(m, a.document(d/'tenants.private.json'), probe, a.document(out/'fanout.json')['probeWrites']['byTenant'])
            except RuntimeError as error:
                return {'verdict':'FAIL', 'code':safe_code(error)}
        read('viewerFrames', frames)
    return result


def serial_exchange_diagnostic(a,d,m,record):
    """Existing stock probe, selected paired exchange hooks, no ordinary load."""
    require(m.get('serialExchangeDiagnostic')==a.SERIAL_EXCHANGE_DIAGNOSTIC,'M7_SERIAL_EXCHANGE_DIAGNOSTIC_SCOPE')
    a.frozen(m,'run');a.verify(d,m);a.image(m);a.verify_generator(d,m);a.assert_owned(m)
    out=d/'load';out.mkdir();runid='m7-'+m['owner'][:12]
    spec=m['project']+'|'+str(d/'env')+'|'+str(d/'frozen.compose.json')
    completion=a.document(d/'completion-source.json')
    node=m['generator']['tools']['node']
    binding={'version':1,'kind':'pgstream-serial-exchange-pair-v1','selection':m['serialExchangeDiagnostic'],
             'owner':m['owner'],'pair':m['pair'],'imageId':m['imageId'],'instrument':m['instrument']['sha256'],
             'ownerFile':str(d/'owner.json'),'ownerSha256':a.digest(d/'owner.json'),
             'tenantsFile':str(d/'tenants.private.json'),'tenantsSha256':a.digest(d/'tenants.private.json'),
             'actorSha256':a.digest(d/'serial-exchange-pair.cjs'),'nodeExecutable':node['path'],'nodeSha256':node['sha256'],
             'baseUrl':'http://127.0.0.1:'+str(m['port']),'outputDirectory':str(out/'exchange-phases')}
    binding_path=out/'binding.private.json';a.write(binding_path,binding)
    env=a.runtime_env({'M7_GENERATOR_ROOT':str(d/'dependencies'),'M7_COMPLETION_SOURCE':json.dumps(completion),
        'M7_RUN_PURPOSE':'discovery','M7_RESTART_ROLES':json.dumps(m['restartRoles']),
        'M7_EVALUATOR_SERVICES':json.dumps(a.progress_services(d)),'M7_PROGRESS_PYTHON':a.sys.executable,
        'M7_PROGRESS_ATTRIBUTION':json.dumps(a.progress_attribution(m)),'STOCK_MS':'300000','RECOVERY_MS':'120000'})
    argv=[node['path'],str(d/'probe.js'),'--base',binding['baseUrl'],'--tenants',str(d/'tenants.private.json'),
          '--compose',spec,'--runid',runid,'--clients',str(viewer_plan.total(m)),'--per',str(m['cadence'].get('socketsPerTenant',2)),'--open','5','--window',str(m['cadence']['loadSeconds']),
          '--probeEvery',str(m['cadence'].get('probeEveryMs',3000)),'--restart','0','--evalTimeout','900',
          '--out',str(out/'probe.json'),'--signal',str(out/'.window'),
          '--serialExchangeBinding',str(binding_path),'--serialExchangeBindingSha256',a.digest(binding_path)]
    a.write(out/'launch.json',{'argv':argv,'diagnosticOnly':True,'serialExchangeDiagnostic':m['serialExchangeDiagnostic'],
            'bindingSha256':a.digest(binding_path),'ordinaryTraffic':'NOT_RUN','capacityAcceptance':'NOT_GRANTED'})
    process=None;monitor=None
    with (out/'probe.log').open('wb')as probe_log,a.sampling(d,out):
        a.phase_snapshot(d,out,'before')
        try:
            process=a.diagnostic_resources.popen(a.subprocess.Popen, argv,env=env,stdout=probe_log,stderr=a.subprocess.STDOUT,start_new_session=True)
            a.job_record(out/'probe-job.json',process,m['owner'],group=True)
            monitor=a.loadgen_process(d,process);monitor.__enter__()
            rc=process.wait(timeout=900)
            record.value['processes']['probe']={'returncode':rc,'diagnosticOnly':True};record.save()
            require(rc==0,'M7_SERIAL_EXCHANGE_DIAGNOSTIC_PROCESS_FAILED')
        finally:
            if process is not None:
                a.stop_job(out/'probe-job.json',m['owner']);process.wait(timeout=10)
            if monitor:monitor.__exit__(None,None,None)
            a.phase_snapshot(d,out,'after')
    require(not(out/'.window').exists() and not(out/'k6-summary.json').exists(),'M7_SERIAL_EXCHANGE_ORDINARY_TRAFFIC_RELEASED')
    probe=a.document(out/'probe.json')
    require(probe.get('diagnosticOnly') is True and isinstance(probe.get('serialExchangeDiagnostic'),dict),
            'M7_SERIAL_EXCHANGE_DIAGNOSTIC_RESULT')
    require(not probe.get('hardFailure') and not probe.get('failure'),'M7_SERIAL_EXCHANGE_DIAGNOSTIC_HARNESS_FAILURE')
    observed=probe['serialExchangeDiagnostic'];before=observed.get('before');after=observed.get('after')
    statuses=('COMPLETED_64','HTTP_REFUSED','TRANSPORT_FAILURE','PHASE_DEADLINE')
    require(isinstance(before,dict) and before.get('status') in statuses and
            (isinstance(after,dict) and after.get('status') in statuses if before['status']=='COMPLETED_64' else after is None),
            'M7_SERIAL_EXCHANGE_DIAGNOSTIC_PHASES')
    record.value['probe']=probe
    record.value['serialExchangeDiagnostic']={'selection':m['serialExchangeDiagnostic'],'before':before,'after':after,
         'priming':probe.get('prime'),'bindingSha256':a.digest(binding_path),'ordinaryTraffic':'NOT_RUN',
         'scope':'Matched Node64serial exchange phases around original stock-client setup; no full k6 setup or ordinary310second result'}
    record.value['strictChecks']['serialExchangeDiagnostic']={'verdict':'UNMEASURED','code':'M7_SERIAL_EXCHANGE_DIAGNOSTIC_ONLY','hardFailure':False}
    record.save()

def discovery_load(a,d,m,k6_id,record,oneoff=None):
    out=d/'load';out.mkdir();runid='m7-'+m['owner'][:12];(out/'runid').write_text(runid)
    spec=m['project']+'|'+str(d/'env')+'|'+str(d/'frozen.compose.json')
    completion=a.document(d/'completion-source.json') if m['profile']=='pgstream-sample' else {}
    env=a.runtime_env({'M7_GENERATOR_ROOT':str(d/'dependencies'),**({'M7_COMPLETION_SOURCE':json.dumps(completion)} if completion else {}),'M7_RUN_PURPOSE':'discovery','M7_RESTART_ROLES':json.dumps(m['restartRoles']),'M7_EVALUATOR_SERVICES':json.dumps(a.progress_services(d)),'M7_PROGRESS_PYTHON':a.sys.executable,'M7_PROGRESS_ATTRIBUTION':json.dumps(a.progress_attribution(m)),'STOCK_MS':'300000','RECOVERY_MS':'120000'})
    if completion: env['M7_CLINICAL_WARM_PATH'] = str(d / a.clinical_warm.FILE)
    env.update(workload_inputs.probe_ledger_env(m['cadence']))
    a.psql(d,'SELECT pg_stat_statements_reset();');a.phase_snapshot(d,out,'before-prime')
    windows=phase_windows.start(m,time.monotonic_ns(),int(time.time()*1000))
    if windows:a.write(out/'phase-windows.json',windows)
    process=None;monitor=None;load_started=False;primed=False;probe_stopped=False
    try:
        with (out/'probe.log').open('wb') as probe_log,a.sampling(d,out):
            process=a.diagnostic_resources.popen(a.subprocess.Popen, [m['generator']['tools']['node']['path'],str(d/'probe.js'),'--base','http://127.0.0.1:'+str(m['port']),'--tenants',str(d/'tenants.private.json'),'--compose',spec,'--runid',runid,'--clients',str(viewer_plan.total(m)),'--per',str(m['cadence'].get('socketsPerTenant',2)),*viewer_plan.setup_args(m['cadence']),'--window',str(m['cadence']['loadSeconds']),'--probeEvery',str(m['cadence'].get('probeEveryMs',3000)),'--restart','1' if m['cadence'].get('restart',True) else '0','--evalTimeout','900','--out',str(out/'probe.json'),'--signal',str(out/'.window')],env=env,stdout=probe_log,stderr=a.subprocess.STDOUT,start_new_session=True)
            a.job_record(out/'probe-job.json',process,m['owner'],group=True)
            deadline=a.time.monotonic()+a.remaining_seconds(float('inf'))
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
                    with node_observation.collect(a,d,m,out) as node, (out/'k6.log').open('wb') as output:
                        def launch():
                            argv=k6_command(a,d,m,k6_id,runid)
                            timeout=a.discovery_seconds(m,m['cadence']['loadSeconds']+600)
                            if 'setupSeconds' in windows:
                                # The k6 JWT window begins when its own actor launches.
                                windows['setupStartedMonoNs']=time.monotonic_ns()
                                setup=a.remaining_seconds(windows['setupSeconds'])
                                windows['setupUntilUnixMs']=int(time.time()*1000 + setup*1000)
                                a.write(out/'phase-windows.json',windows)
                                argv=phase_windows.k6_setup(argv,k6_id,setup,windows['setupUntilUnixMs'])
                                grace=max((row.get('gracefulStopSeconds',30) for row in m['cadence'].get('driverPlan',{}).get('scenarios',{}).values()),default=30)
                                timeout=a.remaining_seconds(setup+m['cadence']['loadSeconds']+grace+5)
                            if driver_memory.selected(m):
                                return driver_memory.launch(a,m,out,k6_id,argv,file=output,timeout=timeout)
                            return (oneoff('k6-load',argv,file=output,timeout=timeout) if oneoff
                                    else a.command(argv,file=output,timeout=timeout))
                        record.process('k6',launch)
                        if 'drainSeconds' in windows:
                            windows['drainStartedMonoNs']=time.monotonic_ns()
                            a.write(out/'phase-windows.json',windows)
                    if node is not None:
                        record.value['nodeObservation']=node;record.save()
                    if record.value['processes']['k6'].get('timeout'):stop_k6(a,m,record,oneoff=oneoff)
                    if m['cadence'].get('driverShards',1)>1:
                        import driver_shards
                        record.value['processes']['k6']['shards']=driver_shards.collect(out,json.loads((out/'k6-shard-plan.json').read_text())['shards']);record.save()
                if m.get('cadence',{}).get('restartDuringLoadAfterSeconds') is None:
                    record.observe('load',lambda:observed_load(a,d,m,out,work))
                else:
                    record.observe('load',lambda:observed_load(a,d,m,out,work,record=record,oneoff=oneoff))
            finally:
                primary=sys.exc_info()[1]
                retain_load(a,d,m,record)
                try:a.phase_snapshot(d,out,'after')
                except Exception as secondary:
                    record.failure('after-snapshot',secondary,True)
                    if primary is None and not getattr(secondary, 'snapshotObserverFailed', False):raise
            # Recheck owned custody before the existing bounded restart protocol.
            a.assert_owned(m)
            if 'drainSeconds' in windows:
                windows.setdefault('drainStartedMonoNs',time.monotonic_ns())
                a.write(out/'phase-windows.json',windows)
            if primed and not probe_stopped and process.poll() is None:
                (out/'.restart').touch();start=time.time()
                drain=(a.remaining_seconds(phase_windows.remaining(windows,'drain',time.monotonic_ns()))
                       if 'drainSeconds' in windows else a.discovery_seconds(m,1500))
                try:rc=a.clinical_warm.wait_compose(a,d,m,process,drain) if completion else process.wait(timeout=drain)
                except a.subprocess.TimeoutExpired:rc=None
                record.value['processes']['probe']={'returncode':rc,'startedRecoveryAt':start,'endedAt':time.time(),'timeout':rc is None,'endMonoNs':time.monotonic_ns()};record.save()
            else:
                record.value['strictChecks']['recovery']={'verdict':'UNMEASURED','code':'M7_DISCOVERY_RECOVERY_NOT_STARTED'};record.save()
    finally:
        if driver_memory.selected(m):
            driver_memory.retain(a,m,out,k6_id,runid)
        if process is not None:
            a.stop_job(out/'probe-job.json',m['owner']);process.wait(timeout=10)
            if 'probe' not in record.value['processes']:record.value['processes']['probe']={'returncode':process.returncode,'stoppedByRunner':True,'endMonoNs':time.monotonic_ns()};record.save()
        if monitor:monitor.__exit__(None,None,None)
        retain_load(a,d,m,record)
        if load_started:
            primary=sys.exc_info()[1]
            try:a.phase_snapshot(d,out,'after-reconnect')
            except Exception as secondary:
                record.failure('after-reconnect-snapshot',secondary,True)
                if primary is None and not getattr(secondary, 'snapshotObserverFailed', False):raise
        if (out/'probe.json').is_file():
            record.value['probe']=a.document(out/'probe.json');record.save()
            require(not record.value['probe'].get('hardFailure'),'M7_DISCOVERY_PROBE_HARD_FAILURE')
    if (out/'probe.json').is_file():
        record.value['probe']=a.document(out/'probe.json');record.save()
        require(not record.value['probe'].get('hardFailure'),'M7_DISCOVERY_PROBE_HARD_FAILURE')
        if m.get('cadence',{}).get('restartDuringLoadAfterSeconds') is not None:
            import demand_recovery
            receipt=a.document(out/'demand-recovery.json')
            result=demand_recovery.verify_probe(record.value['probe'],receipt)
            receipt['postRestartOutput']=result;a.write(out/'demand-recovery.json',receipt)
            record.value['demandRecovery']=receipt
            record.value['strictChecks']['demandRecovery']=result
        recovery=record.value['probe'].get('restart',{}).get('runtimeAcquisitionObservation',{})
        require(not hard_recovery(recovery),'M7_DISCOVERY_CLINICAL_FAILURE')
        if recovery:record.value['strictChecks']['recovery']={**{k:recovery[k] for k in ('verdict','code') if k in recovery},'hardFailure':False}
    # Publish completed HTTP/frame segments before later optional collection.
    retain_load(a,d,m,record)
    if m.get('evaluatorCatchup') is not None:evaluator_catchup.run(a,d,m,record)
    if (d/'tenants.private.json').is_file() or (out/'k6-summary.json').is_file():
        try:
            metrics = a.document(out/'k6-summary.json')['metrics'] if (out/'k6-summary.json').is_file() else {}
        except (OSError, ValueError, KeyError) as error:
            record.failure('httpCounters', error, True)
            metrics = {}
        record.value['rateOffer']=a.rate_offer(m)
        record.save()
        try:result,known=count_observation(a,d,out,runid,metrics,probe_ledger=m['cadence'].get('probeLedger'))
        except Exception as error:
            if hasattr(error,'oracleFindings'):
                record.value['oracleFindings']=error.oracleFindings
                record.value['countDiagnostics']={k:v for k,v in error.oracleFindings.items() if k in ('verdict','code','failures','failureCount','probeCountProof','probeAccounting','domains','missingFieldCount')}
                record.save()
            raise
        record.value['oracle']=result if known else None
        record.value['oracleFindings']=result
        record.value['countDiagnostics']={k:v for k,v in result.items() if k in ('verdict','code','failures','failureCount','probeCountProof','probeAccounting','domains','missingFieldCount')}
        record.save()
        if not known:record.value['strictChecks']['counts']={'verdict':'UNMEASURED','code':'M7_DISCOVERY_COUNTS_MISSING'}

    outcome_record(a,d,m,record)

    if (record.value.get('probe') or {}).get('window') and (out/'fanout.json').is_file():
        from viewer_plan import check
        record.value['viewerFrames']=check(m,a.document(d/'tenants.private.json'),record.value['probe'],a.document(out/'fanout.json')['probeWrites']['byTenant'])
        record.save()

    record.save()

def retain_load(a,d,m,record):
    """File-only: publish successful actors even when a later collector refuses."""
    out=d/'load'
    if m.get('apiCause'):
        try:
            result=a.api_cause.retain(d,m);record.value['apiCause']=result
            a.write(out/'api-cause-assessment.json',result)
        except Exception as error:
            record.value.setdefault('retentionFailures',{})['apiCause']={'verdict':'UNMEASURED','code':safe_code(error)}
    for name,key in (('k6-summary.json','metrics'),('probe.json','probe')):
        if not (out/name).is_file():continue
        try:
            value=a.document(out/name)
            if key=='metrics':
                metrics=value['metrics']
                from http_accounting import assess
                record.value['httpAccounting']=assess(metrics)
                a.write(out/'http-accounting.json',record.value['httpAccounting'])
                value={key:value for key,value in metrics.items() if key in ('http_reqs','http_req_failed','iterations','dropped_iterations','scenario_request_attempts','scenario_http_responses','scenario_transport_failures','writes_ok','writes_refused','writes_uncertain','responses_refused') or key.startswith('m7_http_')}
            record.value[key]=value
        except Exception as error:
            # The raw file remains retained; malformed optional reduction must
            # not replace a primary actor/observer failure in a finally block.
            record.value.setdefault('retentionFailures',{})[name]={'verdict':'UNMEASURED','code':safe_code(error)}
    if m.get('cadence',{}).get('driverVuDiagnostic'):
        try:
            result = driver_vu_diagnostic.retain(d, m)
            record.value['driverVuDiagnostic'] = result
            a.write(out/'driver-vu-assessment.json', result)
        except Exception as error:
            record.value.setdefault('retentionFailures', {})['driverVuDiagnostic'] = {'verdict':'UNMEASURED','code':safe_code(error)}
    record.save()


def observed_load(a,d,m,out,work,record=None,oneoff=None):
    import demand_recovery
    if demand_recovery.selected(m) is not None:
        require(record is not None,'M7_DEMAND_RECOVERY_RECORD_REQUIRED')
        return demand_recovery.run(a,d,m,out,work,record,lambda:stop_k6(a,m,record,oneoff))
    observer=a.observe_progress(d,m,out,'load')
    observer.on_hard_midpoint=lambda:hard_midpoint_stop(a,m,oneoff)
    try:observer.__enter__()
    except Exception as error:
        if not incomplete(error):raise
        work();raise
    else:
        try:work()
        except BaseException as error:
            observer.__exit__(type(error),error,error.__traceback__);raise
        else:observer.__exit__(None,None,None)
    return getattr(observer,'result',None)

def k6_command(a,d,m,image,runid):
    if m['cadence'].get('driverVuDiagnostic') == 'configured-v1':
        require(not m.get('remoteTransport'), 'M7_DRIVER_TARGET_UNSUPPORTED')
        driver_vu_diagnostic.expected_plans(m)
    base=k6_base(a,d,m,image,runid)
    shards=m['cadence'].get('driverShards',1)
    if shards==1:return a.bounded_k6_argv(driver_vu_diagnostic.select_command(a,d,m,base))
    import driver_shards
    tenants=json.loads((d/'tenants.private.json').read_text())
    rows=driver_shards.plan(len(tenants),m['cadence'].get('hotFactor',10),m['cadence'].get('offeredRps'),shards)
    folder=driver_shards.write_rosters(d/'k6-shards',tenants,rows)
    a.write(d/'load'/'k6-shard-plan.json',{'version':1,'shards':rows,'scope':'one admitted k6 container; contiguous roster slices; summed weight equals the unsharded plan'})
    driver = None
    if m['cadence'].get('driverVuDiagnostic') == 'configured-v1':
        # Stage through the same guarded single-process interface; shard argv keeps its limits.
        configured = driver_vu_diagnostic.select_command(a,d,m,base)
        driver = {'environment': [driver_vu_diagnostic.configured_environment(m,i) for i in range(shards)],
                  'observer': m['cadence']['driverPlan']['observer']}
        base = [*configured[:configured.index(image)], *base[base.index(image):]]
    return a.bounded_k6_argv(driver_shards.argv(base,image,rows,folder,driver=driver))


def k6_base(a,d,m,image,runid):
    return (['docker','run','--rm','--name',m['project']+'-k6','--label',OWNER+'='+m['owner'],'--label','com.docker.compose.project='+m['project'],'--label','com.docker.compose.service=k6','--network','host','-u',str(a.os.getuid())+':'+str(a.os.getgid()),'-v',str(d/'k6')+':/scripts:ro','-v',str(d/'load')+':/out','-v',str(d/'tenants.private.json')+':/tenants.private.json:ro','-e','BASE_URL=http://127.0.0.1:'+str(m['port']),'-e','TENANTS_FILE=/tenants.private.json','-e','RUN_ID='+runid,'-e','RUN_START='+str(int(time.time()*1000)),'-e','DURATION='+str(m['cadence']['loadSeconds']),'-e','ACCEL='+str(m['cadence'].get('accel',1)),'-e','HOT_FACTOR='+str(m['cadence'].get('hotFactor',10)),*(['-e','OFFERED_RPS='+str(m['cadence']['offeredRps'])] if 'offeredRps' in m['cadence'] else []),*(['-e','M7_WORKLOAD_MIX='+m['cadence']['workloadMix']] if 'workloadMix' in m['cadence'] else []),*(['-e','M7_WORKLOAD_SCALE='+str(m['cadence']['workloadScale'])] if 'workloadScale' in m['cadence'] else []),'-e',a.jwt_setup_env(m),'-e','SHAPES='+','.join(m['cadence'].get('driverPlan',{}).get('scenarios',driver_vu_diagnostic.SHAPES)),image,'run','--quiet','--summary-export','/out/k6-summary.json','/scripts/workload.js'])

def count_observation(a,d,out,runid,metrics,*,probe_ledger=None):
    from discovery_counts import observe
    return observe(a,d,out,runid,metrics,probe_ledger=probe_ledger)


def stop_k6(a,m,record,oneoff=None):
    """A timed-out Docker CLI is not proof its owned container stopped."""
    if oneoff is not None:
        oneoff.stop();record.value['processes']['k6']['ownedContainerStopCompleted']=True;record.save();return
    a.assert_owned(m)
    rows=[row for row in a.resources(m) if (row.get('Config',{}).get('Labels') or {}).get('com.docker.compose.service')=='k6']
    require(len(rows)<=1,'M7_DISCOVERY_LOADGEN_CUSTODY')
    for row in rows:
        a.owned(row,m['owner']);require(re.fullmatch(r'[a-f0-9]{64}',row.get('Id','')),'M7_DISCOVERY_LOADGEN_CUSTODY')
        a.command(['docker','stop','--time','10',row['Id']],timeout=20)
    record.value['processes']['k6']['ownedContainerStopCompleted']=True;record.save()


def hard_midpoint_stop(a,m,oneoff=None):
    """A hard outcome reason at the midpoint stops the owned driver early."""
    try:
        if oneoff is not None:oneoff.stop();return
        a.assert_owned(m)
        for row in a.resources(m):
            if (row.get('Config',{}).get('Labels') or {}).get('com.docker.compose.service')=='k6':
                a.owned(row,m['owner'])
                if re.fullmatch(r'[a-f0-9]{64}',row.get('Id','')):a.command(['docker','stop','--time','10',row['Id']],timeout=20)
    except Exception:pass  # The phase failure stays authoritative.


def outcome_record(a,d,m,record):
    """Outcome gate verdict from retained files; a FAIL is a hard failure."""
    import outcome_gate
    try:
        ids=sorted(row['id'] for row in a.document(d/'tenants.private.json'))
        value=outcome_gate.judge_compose_run(d,ids,attribution={'pair':m['pair'],'imageId':m['imageId'],'instrument':m['instrument']['sha256']})
    except Exception as error:
        # Missing inputs never become a pass, and never replace the run's own refusal.
        record.value['strictChecks']['outcomeGate']={'verdict':'UNMEASURED','code':'M7_OUTCOME_GATE_INPUT_UNAVAILABLE','errorType':type(error).__name__,'hardFailure':False}
        record.save();return None
    value['httpLatencyAllShards']=outcome_gate.http_latency(d/'load')
    a.write(d/'load'/'outcome-gate.json',value)
    row={'verdict':value['verdict'],'codes':sorted({c for x in value['components'].values() for c in x.get('codes',[])}),
         'hardFailure':value['verdict']=='FAIL','artifact':'load/outcome-gate.json','sha256':a.digest(d/'load'/'outcome-gate.json')}
    record.value['strictChecks']['outcomeGate']=row
    if row['hardFailure']:record.value['hardFailures'].append({'stage':'outcomeGate','code':'M7_OUTCOME_GATE_FAIL'})
    record.save();return value


def hard_recovery(value):return value.get('verdict')=='FAIL' and value.get('code') not in SOFT_WORK_FAILURES


def partial_progress(a,d,m,stage):
    """Only genuine, bounded 1/2-round current-source captures may continue."""
    import evaluator_idle as idle
    import evaluator_progress as progress
    need=progress.need
    need(stage in ('idle','load'),'M7_DISCOVERY_PARTIAL_PROGRESS_SCOPE')
    file=d/stage/'evaluator-progress.json'
    budget=m.get('cadence',{}).get('evaluatorProgressBudget')
    policy=progress.capture_policy(budget)
    max_retained=policy['maxBytesPerPhase'] if budget is not None else 16777216
    need(file.is_file() and not file.is_symlink() and file.stat().st_size<=max_retained,'M7_DISCOVERY_PARTIAL_PROGRESS_ARTIFACT')
    value=a.document(file);module=idle if stage=='idle' else progress
    retained_policy={**idle.POLICY,'workPolicy':policy} if stage=='idle' else policy
    kind=idle.ARTIFACT_KIND if stage=='idle' else 'evaluator-progress-phase-v2'
    need(value.get('kind')==kind and value.get('columns')==list(module.COLUMNS) and value.get('policy')==retained_policy and value.get('phase')==stage and value.get('verdict')=='UNMEASURED' and value.get('code')=='M7_EVALUATOR_PROGRESS_ROUNDS' and value.get('attribution')==a.progress_attribution(m),'M7_DISCOVERY_PARTIAL_PROGRESS_SCOPE')
    need(isinstance(value.get('rounds'),list) and 1<=len(value['rounds'])<=2,'M7_DISCOVERY_PARTIAL_PROGRESS_ROUNDS')
    services=a.progress_services(d);need(1<=len(services)<=progress.POLICY['maxInstances'],'M7_EVALUATOR_PROGRESS_INSTANCE_BOUND')
    decoded,ids=(idle._decode(value,m['tenants'],services) if stage=='idle' else progress.decode_rounds(value,m['tenants'],services))
    expected=[row['id'] for row in a.document(d/'tenants.private.json')];progress.validate_ids(expected)
    need(ids==set(expected),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    need(sum(r['queries'] for r in decoded)<=policy['maxQueriesPerPhase'] and sum(r['bytes'] for r in decoded)<=policy['maxBytesPerPhase'],'M7_EVALUATOR_PROGRESS_BUDGET')
    if stage=='idle':idle.clock_windows(decoded)
    # Check ALL available rounds, not only the first timing refusal. No absent
    # round, unselected interval or clock witness is manufactured.
    previous=decoded[0];failed_work=0
    for current in decoded:
        need(current['instances']==previous['instances'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
        for service,rows in previous['allRows'].items():
            for tenant,before in rows.items():
                after=current['allRows'][service][tenant]
                need(before['admitted']==after['admitted'] and all(after[k]>=before[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
                if not before['admitted']:
                    need(not after['ready'] and all(after[k]==before[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
                    if stage=='idle':need(not any(idle.jobs(after['jobs']).values()),'M7_EVALUATOR_IDLE_FOREIGN_PENDING','FAIL')
                else:failed_work+=after['failedCompletions']
        previous=current
    return {'rounds':len(decoded),'scope':'available snapshots only; missing phase observation remains UNMEASURED','workFailurePresent':failed_work>0,'loadClockProof':'not supplied by load source schema' if stage=='load' else 'captured idle brackets validated'}
