"""Opt-in evaluator restart bracket during ordinary discovery demand.

The existing finite runner remains the execution/cleanup owner. Default load
observers retain their same-runtime hard stop. This mode uses separate runtime
and durable brackets and never treats transport acceptance as completion.
"""
import contextvars
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
import evaluator_progress as p
import evaluator_recovery as recovery
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


def verify_probe(probe,receipt):
    if receipt.get('faultExercised') is False:
        require(receipt.get('verdict')=='UNMEASURED' and 'restartStartedAtMs' not in receipt,'M7_DEMAND_RECOVERY_SKIP_RECEIPT')
        return {'verdict':'UNMEASURED','code':'M7_DEMAND_RECOVERY_NOT_EXERCISED','scope':'ordinary traffic continued; no restart/recovery claim'}
    require(probe.get('completedOutput',{}).get('verdict')=='PASS','M7_DEMAND_RECOVERY_OUTPUT_FAILED')
    witnesses=probe.get('completedOutput',{}).get('witnesses',[])
    viewed={row['tenant'] for row in probe.get('viewerBindings',[])}
    post=[w for w in witnesses if w.get('requestStartedAt',0)>receipt['restartEndedAtMs']+1000 and w.get('tenant') in viewed]
    require(post and all(w.get('ready') is True for w in post),'M7_DEMAND_RECOVERY_POST_OUTPUT_NOT_OBSERVED')
    require(probe.get('window',{}).get('deliveredFrames')==probe.get('window',{}).get('expectedFrames')
            and probe['window']['expectedFrames']>0,'M7_DEMAND_RECOVERY_POST_FRAME_NOT_OBSERVED')
    return {'verdict':'UNMEASURED' if receipt.get('verdict')=='UNMEASURED' else 'PASS','postOutputVerdict':'PASS','postRestartViewedWitnesses':len(post),'scope':'actual post-restart request/output/client witnesses; runtime recovery availability is separate and may remain UNMEASURED'}



def refusal_evidence(error):
    """Retain fixed observer evidence, never arbitrary exception text/output."""
    def bounded(value,depth=0):
        if depth>8:return {'omitted':'depth-bound'}
        if value is None or type(value) is bool:return value
        if type(value) is int:return value if abs(value)<=9223372036854775807 else {'omitted':'integer-bound'}
        if type(value) is float:return value if math.isfinite(value) else {'omitted':'nonfinite'}
        if isinstance(value,str):return value if len(value)<=256 else {'omitted':'string-bound','length':len(value)}
        if isinstance(value,dict):return {str(k)[:64]:bounded(v,depth+1) for k,v in list(value.items())[:64]}
        if isinstance(value,list):return [bounded(v,depth+1) for v in value[:64]]
        return {'omitted':'type-bound'}
    collection=getattr(error,'collection',None)
    evidence={'code':str(error) if re.fullmatch('M7_[A-Z_]+',str(error)) else 'M7_DEMAND_RECOVERY_OBSERVATION_UNAVAILABLE',
              'verdict':getattr(error,'verdict',None) if getattr(error,'verdict',None) in ('PASS','FAIL','UNMEASURED') else 'UNMEASURED'}
    if isinstance(collection,dict):
        evidence['collection']={key:bounded(collection[key]) for key in ('queries','bytes','wallSeconds','completeResponses','diagnostic') if key in collection}
    diagnostic=getattr(error,'diagnostic',None)
    if diagnostic is not None:evidence['diagnostic']=bounded(diagnostic)
    if len(json.dumps(evidence,allow_nan=False).encode())>16384:
        evidence={'code':evidence['code'],'verdict':evidence['verdict'],'evidence':'UNMEASURED_BOUND_EXCEEDED'}
    return evidence


def observational_baseline(error):
    """Unknown observation skips injection; known semantic failure still stops."""
    if not isinstance(error,p.Refused) or getattr(error,'verdict',None)!='UNMEASURED':return False
    if str(error) not in ('M7_EVALUATOR_PROGRESS_ERROR','M7_EVALUATOR_PROGRESS_UNAVAILABLE'):return False
    diagnostic=getattr(error,'diagnostic',None) or (getattr(error,'collection',{}) or {}).get('diagnostic')
    if isinstance(diagnostic,dict):
        row=diagnostic.get('failedRow',{})
        failed=row.get('progress',{}).get('failedCompletions') if isinstance(row.get('progress'),dict) else None
        if row.get('admitted') is False:raise p.Refused('M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
        if str(error)=='M7_EVALUATOR_PROGRESS_ERROR':
            # Only the decoder's existing explicit warming shape is ambiguous.
            return (diagnostic.get('warming') is True and type(failed) is int and failed>=0 and row.get('admitted') is True
                    and row.get('code') in ('EVALUATOR_STARTING','EVALUATOR_ACQUISITION_REQUIRED')
                    and row.get('alert') is None)
    return str(error)=='M7_EVALUATOR_PROGRESS_UNAVAILABLE'


def run(a,d,m,out,work,record,stop_load):
    validate(m)
    require(selected(m) is not None,'M7_DEMAND_RECOVERY_SELECTION')
    ids=sorted(row['id'] for row in a.document(d/'tenants.private.json'))
    services=a.progress_services(d)
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
            try:
                policy=p.capture_policy(m.get('cadence',{}).get('evaluatorProgressBudget'))
                baseline=p.round_view(services,ids,lambda service,chosen,q,b:a.progress_fetch(d,service,chosen,q,b),warming=True,allow_unavailable=True,policy=policy)
                if any(not row['ready'] for row in baseline['owners'].values()):
                    error=p.Refused('M7_EVALUATOR_PROGRESS_UNAVAILABLE');error.diagnostic={'availability':p.availability([baseline],ids)};raise error
                time.sleep(.25);live(future);bound()
                confirmed=p.round_view(services,ids,lambda service,chosen,q,b:a.progress_fetch(d,service,chosen,q,b),allow_unavailable=True,policy=policy)
                if any(not row['ready'] for row in confirmed['owners'].values()):
                    error=p.Refused('M7_EVALUATOR_PROGRESS_UNAVAILABLE');error.diagnostic={'availability':p.availability([confirmed],ids)};raise error
            except p.Refused as error:
                result['baselineObservation']=refusal_evidence(error)
                if not observational_baseline(error):raise
                result.update(verdict='UNMEASURED',code='M7_DEMAND_RECOVERY_BASELINE_UNMEASURED',faultExercised=False)
                a.write(out/'demand-recovery.json',result)
                future.result(timeout=a.remaining_seconds(max(1,until-time.time()-3)))
                require(abs((time.time()-wall_started)-(time.monotonic()-started))<.5,'M7_DEMAND_RECOVERY_CLOCK_CHANGED')
                result['ordinaryWindow']='ordinary load finished without fault injection; recovery remains UNMEASURED'
                record.value['demandRecovery']=result;record.save()
                return result
            a.write(out/'demand-recovery-baseline.private.json',baseline)
            result['baselineArtifact']='demand-recovery-baseline.private.json'
            # A cumulative historical count cannot identify its cause. Admit only
            # a healthy same-runtime bracket; uncredited attempts retain unknown cause.
            baseline_admission=p.stable_discovery_baseline(baseline,confirmed,ids)
            result['rejectedWorkBaseline']=baseline_admission
            a.write(out/'demand-recovery-confirmed-baseline.private.json',confirmed)
            # All rendered evaluator services, and no API/realtime/foreign role.
            require(services==a.progress_services(d),'M7_DEMAND_RECOVERY_ROLE_CHANGED')
            live(future);a.assert_owned(m)
            compose_args=a.compose_prefix(d)[1:]
            script="const x=JSON.parse(process.argv[1]);require(process.argv[2]).restart(x).then(v=>console.log(JSON.stringify(v))).catch(e=>{console.error(e.code);process.exit(1)});"
            result['faultExercised']=True
            result['restartStartedAtMs']=int(time.time()*1000)
            response=a.command([m['generator']['tools']['node']['path'],'-e',script,json.dumps({'composeArgs':compose_args,'roles':services,'at':result['restartStartedAtMs']}),a.HERE/'restart.cjs'],timeout=min(120,a.remaining_seconds(120)))
            result['restart']=json.loads(response);result['restartEndedAtMs']=int(time.time()*1000)
            require(set(result['restart'].get('starts',{}))==set(services),'M7_DEMAND_RECOVERY_ROLE_CHANGED')
            live(future);bound()
            proof=recovery.main({'discoveryUnclassifiedRejections':True,'mode':'recovery','ids':ids,'services':services,'composeArgs':compose_args,
                                 'baseline':str(out/'demand-recovery-baseline.private.json'),
                                 'path':str(out/'demand-recovery-runtime.private.json'),
                                 'deadlineMs':min(int(until*1000)-5000,result['restartEndedAtMs']+120000),
                                 'attribution':a.progress_attribution(m)})
            result['runtimeRecovery']=proof
            if proof.get('verdict')=='UNMEASURED' and proof.get('code') in ('M7_EVALUATOR_RECOVERY_NOT_OBSERVED','M7_EVALUATOR_PROGRESS_UNAVAILABLE'):
                # Unknown evaluator availability limits recovery claims, not the
                # unrelated finite REST workload. Keep durable fences enforced.
                future.result(timeout=a.remaining_seconds(max(1,until-time.time()-3)))
                result.update(verdict='UNMEASURED',code=proof['code'],ordinaryWindow='ordinary load finished; evaluator recovery availability remains UNMEASURED')
                record.value['demandRecovery']=result;record.save();return result
            if proof.get('verdict')!='PASS':raise p.Refused(proof.get('code','M7_DEMAND_RECOVERY_RUNTIME_NOT_OBSERVED'),proof.get('verdict','UNMEASURED'))
            live(future);bound()
            # Accepted inputs before and after the restart are judged by the
            # assessor (stored, and clinical output within the deadline).
            result['recoveryObservedAtMs']=int(time.time()*1000)
            result['ordinaryWindow']='active scenario marker observed before restart; load command still active after recovery'
            future.result(timeout=a.remaining_seconds(max(1,until-time.time()-3)))
            require(abs((time.time()-wall_started)-(time.monotonic()-started))<.5,'M7_DEMAND_RECOVERY_CLOCK_CHANGED')
            result['verdict']='PASS'
        except BaseException as error:
            result['refusal']=refusal_evidence(error)
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
