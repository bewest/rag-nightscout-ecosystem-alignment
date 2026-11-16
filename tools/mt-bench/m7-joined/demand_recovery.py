"""Opt-in evaluator restart bracket during ordinary discovery demand.

The existing finite runner remains the execution/cleanup owner. Default load
observers retain their same-runtime hard stop. This mode uses separate runtime
and durable brackets and never treats transport acceptance as completion.
"""
import contextvars
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
import evaluator_progress as p
import evaluator_recovery as recovery
import evaluator_opportunities as opportunities
from contract import require


def selected(m):
    return (m or {}).get('cadence',{}).get('restartDuringLoadAfterSeconds')


def validate(m):
    delay=selected(m)
    if delay is None:return
    require(m.get('profile')=='pgstream-sample' and m.get('runPurpose')=='discovery'
            and m.get('completionContract')=='evaluator-work-v2','M7_DEMAND_RECOVERY_SCOPE')
    require(type(delay) is int and 1<=delay and delay+60<=m['cadence']['loadSeconds']
            and m['cadence'].get('probeEveryMs',300000)<=1000,'M7_DEMAND_RECOVERY_WINDOW')


def active_marker(path):
    """A setup exchange is not ordinary demand; bound raw log reads."""
    if not path.exists():return None
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-65536))
        text=stream.read(65536).decode(errors='replace')
    events=[]
    for line in text.splitlines():
        match=re.search(r'msg="((?:[^"\\]|\\.)*)"',line)
        if not match:continue
        try:event=json.loads(json.loads('"'+match.group(1)+'"'))
        except (ValueError,TypeError):continue
        if event.get('event')=='scenario-first-iteration' and type(event.get('atMs')) is int:events.append(event['atMs'])
    return min(events) if events else None


def validate_authority(value,ids):
    require(isinstance(value,list) and len(value)==len(ids)
            and {v.get('tenant') for v in value}==set(ids),'M7_DEMAND_RECOVERY_AUTHORITY_COVERAGE')
    for row in value:
        require(set(row)=={'tenant','state','phase','generation','claim','artifact'}
                and row['state']==row['phase']=='active'
                and isinstance(row['generation'],str) and row['generation'].isdecimal()
                and int(row['generation'])>0,'M7_DEMAND_RECOVERY_AUTHORITY')
    return sorted(value,key=lambda row:row['tenant'])


def authority(a,d,ids):
    # This mode is the existing unselected nsdemo fixture only. Namespace and
    # authority shape are independently read from the owned rendered layout.
    layout=a.document(d/'state/bootstrap/layout.json')
    namespaces=layout.get('namespaces',{})
    require(namespaces.get('control')=='nsdemo_control' and namespaces.get('registry')=='nsdemo_registry',
            'M7_DEMAND_RECOVERY_AUTHORITY_LAYOUT')
    p.validate_ids(ids)
    values=','.join("'"+tenant+"'::uuid" for tenant in ids)
    sql="SELECT json_build_object('tenant',r.tenant_id::text,'state',r.state,'phase',w.phase,'generation',w.generation::text,'claim',w.claim_id::text,'artifact',w.artifact_digest) FROM nsdemo_registry.tenant_registry r JOIN nsdemo_control.tenant_lifecycle_windows w USING(tenant_id) WHERE r.tenant_id IN ("+values+") ORDER BY r.tenant_id;"
    return validate_authority([json.loads(line) for line in a.psql(d,sql,a.application_database(d)).splitlines() if line],ids)


def assess_bracket(before,after,ids,binding,authority_before,authority_after):
    require(validate_authority(authority_before,ids)==validate_authority(authority_after,ids),
            'M7_DEMAND_RECOVERY_AUTHORITY_CHANGED')
    rows=opportunities.durable_rows([before,after,after],ids,binding)
    require(all(rows[0][tenant]['restoreGeneration'] is not None
                and rows[0][tenant]['restoreGeneration']==rows[-1][tenant]['restoreGeneration'] for tenant in ids),
            'M7_DEMAND_RECOVERY_RESTORE_CHANGED')
    for tenant in ids:
        first,last=rows[0][tenant],rows[-1][tenant]
        targets={**first['observed'],'clock':first['writerClock']}
        require(all(key in last['completed'] and opportunities.revision(last['completed'][key])>=opportunities.revision(value)
                    for key,value in targets.items()),'M7_DEMAND_RECOVERY_ACCEPTED_TARGET_PENDING')
    return {'verdict':'PASS','tenants':len(ids),'scope':'stable sampled authority/restore, monotone durable positions and pre-restart targets clinically completed; no per-write clinical equivalence'}


def verify_probe(probe,receipt):
    require(probe.get('completedOutput',{}).get('verdict')=='PASS','M7_DEMAND_RECOVERY_OUTPUT_FAILED')
    witnesses=probe.get('completedOutput',{}).get('witnesses',[])
    viewed={row['tenant'] for row in probe.get('viewerBindings',[])}
    post=[w for w in witnesses if w.get('requestStartedAt',0)>receipt['restartEndedAtMs']+1000 and w.get('tenant') in viewed]
    require(post and all(w.get('ready') is True for w in post),'M7_DEMAND_RECOVERY_POST_OUTPUT_NOT_OBSERVED')
    require(probe.get('window',{}).get('deliveredFrames')==probe.get('window',{}).get('expectedFrames')
            and probe['window']['expectedFrames']>0,'M7_DEMAND_RECOVERY_POST_FRAME_NOT_OBSERVED')
    return {'verdict':'PASS','postRestartViewedWitnesses':len(post),'scope':'actual post-restart request/output/client witnesses; sparse subset only'}


def run(a,d,m,out,work,record,stop_load):
    validate(m)
    require(selected(m) is not None,'M7_DEMAND_RECOVERY_SELECTION')
    ids=sorted(row['id'] for row in a.document(d/'tenants.private.json'))
    services=a.progress_services(d)
    collector=a.opportunity_collector(d,m,ids)
    result={'kind':'evaluator-under-demand-recovery-v1','verdict':'UNMEASURED','roles':services,
            'source':a.progress_attribution(m),'delaySeconds':selected(m),'ordinaryWindow':'UNMEASURED'}
    a.write(out/'demand-recovery.json',result)
    until=a._COMMAND_DEADLINE.get()
    require(until is not None,'M7_DEMAND_RECOVERY_FINITE_WINDOW')
    context=contextvars.copy_context()
    started=time.monotonic();wall_started=time.time()
    scenario_start=None
    def live(future):
        require(not future.done(),'M7_DEMAND_RECOVERY_DEMAND_ENDED')
        if scenario_start is not None:require(time.time()*1000<scenario_start+m['cadence']['loadSeconds']*1000,'M7_DEMAND_RECOVERY_SCENARIO_ENDED')
    def bound():require(time.time()<until-5,'M7_DEMAND_RECOVERY_DEADLINE')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(context.run,work)
        try:
            while not active_marker(out/'k6.log'):
                live(future);bound();time.sleep(.1)
            scenario_start=active_marker(out/'k6.log')
            active=time.monotonic();result['scenarioStartedAtMs']=scenario_start;result['scenarioObservedAtMs']=int(time.time()*1000)
            while time.monotonic()-active<selected(m):live(future);bound();time.sleep(.1)
            live(future);bound();a.assert_owned(m)
            auth_before=authority(a,d,ids);before,cost_before=collector()
            result['captures']={'before':before,'authorityBefore':auth_before,'costBefore':cost_before}
            a.write(out/'demand-recovery.json',result)
            baseline=p.round_view(services,ids,lambda service,chosen,q,b:a.progress_fetch(d,service,chosen,q,b))
            a.write(out/'demand-recovery-baseline.private.json',baseline)
            # All rendered evaluator services, and no API/realtime/foreign role.
            require(services==a.progress_services(d),'M7_DEMAND_RECOVERY_ROLE_CHANGED')
            live(future);a.assert_owned(m)
            restart_argv=a.orchestration_binding.fixture_argv(d,['restart',*services])
            a.orchestration_binding.fixture_mutation_preflight(d,restart_argv,a.command)
            compose_args=a.orchestration_binding.fixture_argv(d,[])[1:]
            script="const x=JSON.parse(process.argv[1]);require(process.argv[2]).restart(x).then(v=>console.log(JSON.stringify(v))).catch(e=>{console.error(e.code);process.exit(1)});"
            result['restartStartedAtMs']=int(time.time()*1000)
            response=a.command([m['generator']['tools']['node']['path'],'-e',script,json.dumps({'composeArgs':compose_args,'roles':services,'at':result['restartStartedAtMs']}),a.HERE/'restart.cjs'],timeout=min(120,a.remaining_seconds(120)))
            result['restart']=json.loads(response);result['restartEndedAtMs']=int(time.time()*1000)
            require(set(result['restart'].get('starts',{}))==set(services),'M7_DEMAND_RECOVERY_ROLE_CHANGED')
            live(future);bound()
            proof=recovery.main({'mode':'recovery','ids':ids,'services':services,'composeArgs':compose_args,
                                 'baseline':str(out/'demand-recovery-baseline.private.json'),
                                 'path':str(out/'demand-recovery-runtime.private.json'),
                                 'deadlineMs':min(int(until*1000)-5000,result['restartEndedAtMs']+120000),
                                 'attribution':a.progress_attribution(m)})
            result['runtimeRecovery']=proof
            if proof.get('verdict')!='PASS':raise p.Refused(proof.get('code','M7_DEMAND_RECOVERY_RUNTIME_NOT_OBSERVED'),proof.get('verdict','UNMEASURED'))
            live(future);bound()
            after,cost_after=collector();auth_after=authority(a,d,ids)
            result['durableBracket']=assess_bracket(before,after,ids,collector.binding,auth_before,auth_after)
            result['captures']={'before':before,'after':after,'authorityBefore':auth_before,'authorityAfter':auth_after,
                                'costBefore':cost_before,'costAfter':cost_after}
            result['recoveryObservedAtMs']=int(time.time()*1000)
            result['ordinaryWindow']='active scenario marker observed before restart; load command still active after recovery'
            future.result(timeout=a.remaining_seconds(max(1,until-time.time()-3)))
            require(abs((time.time()-wall_started)-(time.monotonic()-started))<.5,'M7_DEMAND_RECOVERY_CLOCK_CHANGED')
            result['verdict']='PASS'
        except BaseException as error:
            result.update(verdict='FAIL',code=str(error) if re.fullmatch('M7_[A-Z_]+',str(error)) else 'M7_DEMAND_RECOVERY_INSTRUMENT_ERROR')
            if not future.done():
                record.value.setdefault('processes',{}).setdefault('k6',{})
                result['loadStopRequested']=True
                try:stop_load();result['loadStopCompleted']=True
                except Exception:result['loadStopCompleted']=False
            try:future.result(timeout=a.remaining_seconds(max(1,until-time.time()-2)))
            except BaseException:pass
            raise
        finally:a.write(out/'demand-recovery.json',result)
    record.value['demandRecovery']=result;record.save()
