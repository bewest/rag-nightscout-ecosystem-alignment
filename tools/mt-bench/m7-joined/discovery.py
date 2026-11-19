"""Explicit observational load route. Never grants capacity acceptance."""
import json
import viewer_plan
import workload_inputs
import re
import subprocess
import sys
import time
import driver_vu_diagnostic
import phase_windows
from contract import require, SHA, OWNER, REPLICAS, UNACCEPTED_SCOPE, discovery_scope, check_discovery_scope, discovery_api_replicas

INCOMPLETE=frozenset(('M7_EVALUATOR_PROGRESS_NOT_OBSERVED','M7_RUNTIME_NOT_READY','M7_EVALUATOR_PROGRESS_UNAVAILABLE','M7_EVALUATOR_PROGRESS_COLLECTOR_TIMEOUT',
                      'M7_EVALUATOR_PROGRESS_QUERY_BOUND','M7_EVALUATOR_PROGRESS_BYTE_BOUND','M7_EVALUATOR_PROGRESS_BUDGET'))

def safe_code(error):
    text=str(error)
    return text if re.fullmatch(r'M7_[A-Z_]+(?::[a-zA-Z0-9_.-]+)?',text) else 'M7_DISCOVERY_INSTRUMENT_ERROR'

# Counter-only ambiguity lives in observer fields; actual errors stay hard.
SOFT_WORK_FAILURES=frozenset()

def incomplete(error):return str(error) in SOFT_WORK_FAILURES or (getattr(error,'verdict','UNMEASURED')!='FAIL' and str(error) in INCOMPLETE)

def check_discovery(value):
    require(value.get('kind') in ('m7-joined-discovery-cell','m7-joined-discovery') and value.get('version')==1 and value.get('runPurpose')=='discovery' and value.get('capacityAcceptance')=='NOT_GRANTED','M7_DISCOVERY_SHAPE')
    require(value.get('status') in ('MEASURED','PARTIAL'),'M7_DISCOVERY_STATUS')
    require(all(SHA.fullmatch(value.get('pair',{}).get(k,'')) for k in ('core','deploy')),'M7_DISCOVERY_SOURCE')
    require(re.fullmatch(r'sha256:[a-f0-9]{64}',value.get('imageId','')),'M7_DISCOVERY_IDENTITY')
    if value['kind']=='m7-joined-discovery':
        cells=value.get('cells');require(isinstance(cells,list) and 1<=len(cells)<=12,'M7_DISCOVERY_CELLS')
        roster=[]
        for row in cells:
            require(row.get('kind')=='m7-joined-discovery-cell','M7_DISCOVERY_CELL_KIND');check_discovery(row)
            require(all(row.get(k)==value.get(k) for k in ('pair','imageId')),'M7_DISCOVERY_MIXED_IDENTITY')
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
            require(all(type(oracle.get(k)) in (int,float) and oracle[k]>=0 for k in ('accepted','stored','uncertain')) and oracle['accepted']<=oracle['stored']<=oracle['accepted']+oracle['uncertain'],'M7_DISCOVERY_WRONG_DATA')
            for row in rows:
                require(type(row.get('stored')) is int and row['stored']>=0 and row.get('match') is True,'M7_DISCOVERY_WRONG_DATA')
                require(all(type(row.get(k)) is int and row[k]>=0 for k in ('probeAccepted','probeStored','probeUncertain','probeRefused','probePending')) and row['probePending']==0 and row['probeAccepted']<=row['probeStored']<=row['probeAccepted']+row['probeUncertain'],'M7_DISCOVERY_WRONG_DATA')
    if value.get('profile')=='pgstream-sample':
        check_discovery_scope(value)
        if value['status']=='MEASURED':
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
        self.value['artifacts']={str(file.relative_to(self.d)):self.a.digest(file) for folder in ('load',) for name in ('evaluator-progress.json','probe.json','k6-summary.json','http-accounting.json','after-cgroups.json','after-pg-role.tsv','after-pg-statements.tsv','stored-counts.json','oracle-findings.json','probe-accounting.json','fanout.json','demand-recovery.json','node-observation.json','k6-scheduling.csv.gz','driver-vu-assessment.json','host-load.tsv','pg-activity.tsv','pg-blockers.tsv') if (file:=self.d/folder/name).is_file()}
        self.value['collectionSegments']={str(file.relative_to(self.d)):self.a.digest(file) for folder in ('load',) for file in (self.d/folder).glob('*-collection.json') if file.is_file()}
        self.a.write(self.d/'summary.json',self.value)
    def failure(self,stage,error,hard=False):
        row={'verdict':getattr(error,'verdict','UNMEASURED'),'code':safe_code(error),'hardFailure':hard};self.value['strictChecks'][stage]=row
        if hard:self.value['hardFailures'].append({'stage':stage,'code':row['code']})
        self.save()
    def observe(self,stage,fn):
        try:
            result=fn()
            self.value['strictChecks'][stage]={'verdict':'UNMEASURED','code':'M7_EVALUATOR_AVAILABILITY_UNMEASURED','hardFailure':False} if stage=='readiness' and isinstance(result,dict) and result.get('verdict')=='UNMEASURED' else {'verdict':'PASS'};self.save();return result
        except Exception as error:
            allowed=incomplete(error)
            self.failure(stage,error,not allowed)
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
    record=Record(a,d,m)
    record.save()
    try:
        require(m.get('profile')!='fresh-image-diagnostic','M7_DIAGNOSTIC_CANNOT_RUN_CAPACITY')
        a.frozen(m,'run');a.quiet(d,m,'run-before',check_load=False);a.verify(d,m);a.image(m)
        record.value['ownershipVerified']=True;record.save()
        require((d/'deploy-before-host.json').is_file(),'M7_DEPLOY_QUIET_RECORD_REQUIRED')
        a.verify_generator(d,m)
        record.observe('readiness',lambda:a.readiness(d,m))
        k6_id=json.loads(a.command(['docker','image','inspect',k6_image]))[0]['Id'];a.write(d/'loadgen-image.json',{'k6':k6_id,'generator':m['generator']})
        if m['profile']=='pgstream-sample':completion,sql_roles=a.sample_preflight(d,m,k6_id,**({'oneoff':oneoff}if oneoff else{}))
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
                    raise
                record.save()
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
    for phase in ('load',):
        if (d/phase/'evaluator-progress.json').is_file():
            try:
                progress[phase] = a.progress_summary(d/phase)
            except Exception as error:
                progress[phase] = {'verdict': 'UNMEASURED', 'code': safe_code(error)}
    result['evaluatorProgress'] = progress
    out = d/'load'
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


def discovery_load(a,d,m,k6_id,record,oneoff=None):
    out=d/'load';out.mkdir();runid='m7-'+m['owner'][:12];(out/'runid').write_text(runid)
    completion = a.document(d/'completion-source.json') if m['profile']=='pgstream-sample' else {}
    with a.accepted_input_observation(d,m,runid,completion) as accepted:
        return run_load(a,d,m,k6_id,record,oneoff,out,runid,completion,accepted)


def run_load(a,d,m,k6_id,record,oneoff,out,runid,completion,accepted):
    spec=m['project']+'|'+str(d/'env')+'|'+str(d/'frozen.compose.json')
    env=a.runtime_env({'M7_GENERATOR_ROOT':str(d/'dependencies'),**({'M7_COMPLETION_SOURCE':json.dumps(completion)} if completion else {}),'M7_RUN_PURPOSE':'discovery','M7_RESTART_ROLES':json.dumps(m['restartRoles']),'M7_EVALUATOR_SERVICES':json.dumps(a.progress_services(d)),'M7_PROGRESS_PYTHON':a.sys.executable,'M7_PROGRESS_ATTRIBUTION':json.dumps(a.progress_attribution(m)),'STOCK_MS':'300000','RECOVERY_MS':'120000'})
    env.update(workload_inputs.probe_ledger_env(m['cadence']))
    a.psql(d,'SELECT pg_stat_statements_reset();');a.phase_snapshot(d,out,'before-prime')
    windows=phase_windows.start(m,time.monotonic_ns(),int(time.time()*1000))
    if windows:a.write(out/'phase-windows.json',windows)
    process=None;monitor=None;load_started=False;primed=False;probe_stopped=False
    try:
        with (out/'probe.log').open('wb') as probe_log,a.sampling(d,out):
            process=a.subprocess.Popen([m['generator']['tools']['node']['path'],str(d/'probe.js'),'--base','http://127.0.0.1:'+str(m['port']),'--tenants',str(d/'tenants.private.json'),'--compose',spec,'--runid',runid,'--clients',str(viewer_plan.total(m)),'--per',str(m['cadence'].get('socketsPerTenant',2)),*viewer_plan.setup_args(m['cadence']),'--window',str(m['cadence']['loadSeconds']),'--probeEvery',str(m['cadence'].get('probeEveryMs',3000)),'--restart','1' if m['cadence'].get('restart',True) else '0','--evalTimeout','900','--out',str(out/'probe.json'),'--signal',str(out/'.window')],env=env,stdout=probe_log,stderr=a.subprocess.STDOUT,start_new_session=True)
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
                    with (out/'k6.log').open('wb') as output:
                        def launch():
                            a.k6_tenants(d,m)
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
                            return (oneoff('k6-load',argv,file=output,timeout=timeout) if oneoff
                                    else a.command(argv,file=output,timeout=timeout))
                        record.process('k6',launch)
                        windows['drainStartedMonoNs']=time.monotonic_ns()
                        if accepted is not None or 'drainSeconds' in windows:
                            windows.setdefault('drainSeconds',1500)
                            a.write(out/'phase-windows.json',windows)
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
                try:rc=process.wait(timeout=drain)
                except a.subprocess.TimeoutExpired:rc=None
                record.value['processes']['probe']={'returncode':rc,'startedRecoveryAt':start,'endedAt':time.time(),'timeout':rc is None,'endMonoNs':time.monotonic_ns()};record.save()
            else:
                record.value['strictChecks']['recovery']={'verdict':'UNMEASURED','code':'M7_DISCOVERY_RECOVERY_NOT_STARTED'};record.save()
    finally:
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

    if accepted is not None:
        boundary = a.drain_boundary(windows,a._COMMAND_DEADLINE.get())
        accepted.finish(out, drain_end=boundary, storage=record.value.get('oracleFindings'))
        a.terminal_progress(d,m,out)
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
    if shards==1:return driver_vu_diagnostic.select_command(a,d,m,base)
    import driver_shards
    tenants=json.loads(k6_roster(d).read_text())
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
    return driver_shards.argv(base,image,rows,folder,driver=driver)


def k6_roster(d):
    """The roster k6 loads: with each tenant's JWT once exchanged (adapter.k6_tenants)."""
    roster=d/'load'/'k6-tenants.private.json'
    return roster if roster.is_file() else d/'tenants.private.json'


def k6_base(a,d,m,image,runid):
    return (['docker','run','--rm','--name',m['project']+'-k6','--label',OWNER+'='+m['owner'],'--label','com.docker.compose.project='+m['project'],'--label','com.docker.compose.service=k6','--network','host','-u',str(a.os.getuid())+':'+str(a.os.getgid()),'-v',str(d/'k6')+':/scripts:ro','-v',str(d/'load')+':/out','-v',str(k6_roster(d))+':/tenants.private.json:ro','-e','BASE_URL=http://127.0.0.1:'+str(m['port']),'-e','TENANTS_FILE=/tenants.private.json','-e','RUN_ID='+runid,'-e','RUN_START='+str(int(time.time()*1000)),'-e','DURATION='+str(m['cadence']['loadSeconds']),'-e','ACCEL='+str(m['cadence'].get('accel',1)),'-e','HOT_FACTOR='+str(m['cadence'].get('hotFactor',10)),*(['-e','OFFERED_RPS='+str(m['cadence']['offeredRps'])] if 'offeredRps' in m['cadence'] else []),*(['-e','M7_WORKLOAD_MIX='+m['cadence']['workloadMix']] if 'workloadMix' in m['cadence'] else []),*(['-e','M7_WORKLOAD_SCALE='+str(m['cadence']['workloadScale'])] if 'workloadScale' in m['cadence'] else []),'-e','SHAPES='+','.join(m['cadence'].get('driverPlan',{}).get('scenarios',driver_vu_diagnostic.SHAPES)),image,'run','--quiet','--summary-export','/out/k6-summary.json','/scripts/workload.js'])

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
