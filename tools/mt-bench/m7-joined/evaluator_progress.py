"""Bounded private evaluator completion observations; never triggers work."""
import json
import math
import re
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

UUID=re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
# One reader policy. Failed completions are judged by outcome_gate (decision
# outcome-evaluator-gate); the original strict-zero and earlier policy versions
# are not live. Retained runs re-reduce through outcome_rereduce.py.
POLICY={'version': 2, 'moduleVersion': 5, 'selectorRows': 128, 'maxTenants': 4294967295, 'maxInstances': 8, 'roundsPerPhase': 3, 'maxQueriesPerPhase': 1024, 'maxBytesPerPhase': 67108864, 'responseMaxBytes': 1048576, 'rpcTimeoutMs': 5000, 'roundDeadlineMs': 15000, 'idleWitness': 'successful-work-progression-not-clinical-proof', 'loadWitness': 'successful-work-progression', 'recoveryCadenceMs': 15000, 'recoveryTimeoutMs': 900000, 'recoveryMaxRounds': 60, 'readinessMaxQueries': 25600, 'readinessMaxBytes': 268435456, 'readinessMaxRounds': 80, 'deadlineClaim': False, 'workloadCohortChanged': False, 'dueState': 'captured-only-not-opportunity-assessed', 'cacheGeneration': 'disposable-not-process-identity'}  # The pinned Compose worker roster supports 1-8.
# Decision outcome-evaluator-gate: failed completions are judged by
# outcome_gate from raw typed reasons, not by a lifetime zero here.
OUTCOME_FAILURE_POLICY='outcome-evaluator-gate-v1'
def select_failure_policy(value):
    need(value in (None,OUTCOME_FAILURE_POLICY),'M7_EVALUATOR_FAILURE_POLICY');return OUTCOME_FAILURE_POLICY

class Refused(RuntimeError):
    def __init__(self,code,verdict='UNMEASURED'):
        super().__init__(code);self.verdict=verdict

def need(value,code,verdict='UNMEASURED'):
    if not value:raise Refused(code,verdict)

def integer(value,minimum=0):return type(value) is int and minimum<=value<=9007199254740991


def capture_policy(selected=None):
    if selected is None:
        return POLICY
    need(isinstance(selected,dict) and set(selected)=={'maxQueriesPerPhase','maxBytesPerPhase'} and
         all(integer(value,1) for value in selected.values()),'M7_EVALUATOR_PROGRESS_BUDGET_INPUT','FAIL')
    return {**POLICY,**selected}

def roster_policy(selected, count, instances):
    """Every selected RPC page can spend its own transport allowance."""
    policy = capture_policy(selected)
    queries = math.ceil(count / policy['selectorRows']) * instances * policy['roundsPerPhase']
    return {**policy, 'maxQueriesPerPhase':max(policy['maxQueriesPerPhase'], queries),
            'maxBytesPerPhase':max(policy['maxBytesPerPhase'], queries*(policy['responseMaxBytes']+8193))}


def due_fields(row):
    need('dueAt' in row and 'dueReason' in row,'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
    at,reason=row['dueAt'],row['dueReason']
    need(at is None or type(at) in (int,float) and math.isfinite(at) and at>=0,'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
    need(reason is None or isinstance(reason,str) and re.fullmatch(r'[a-z][a-z0-9:,_-]{0,127}',reason),'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
    need(at is not None or reason is None,'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
    return {'dueAt':at,'dueReason':reason}

def validate_ids(ids):
    need(isinstance(ids,list) and 1<=len(ids)<=POLICY['maxTenants'] and len(set(ids))==len(ids) and all(isinstance(v,str) and UUID.fullmatch(v) for v in ids),'M7_EVALUATOR_PROGRESS_TENANTS')

REFUSAL_ROW_MAX_BYTES=4096
_MISSING=object()

def _refusal_value(value,*,text=False,boolean=False):
    if value is _MISSING:return {'type':'missing'}
    if value is None:return None
    if boolean and type(value) is bool:return value
    if type(value) is int and abs(value)<=9007199254740991:return value
    if type(value) is float and math.isfinite(value) and abs(value)<=9007199254740991:return value
    if text and isinstance(value,str):
        return value if len(value)<=64 else {'value':value[:64],'truncated':True,'length':len(value)}
    return {'type':type(value).__name__}

def _refusal_row(row,service,runtime_id):
    # One private failed-row projection, never the raw RPC or clinical output.
    # Fixed fields and capped strings bound even malformed response evidence.
    progress=row.get('progress');evaluation=row.get('evaluation');jobs=row.get('jobs')
    value={'tenant':_refusal_value(row.get('tenant',_MISSING),text=True),
           'service':_refusal_value(service,text=True),'runtimeId':_refusal_value(runtime_id,text=True),
           **{k:_refusal_value(row.get(k,_MISSING),boolean=True) for k in ('admitted','ready')},
           'code':_refusal_value(row.get('code',_MISSING),text=True),
           'alert':_refusal_value(evaluation.get('alert',_MISSING) if isinstance(evaluation,dict) else _MISSING,text=True),
           'progress':{k:_refusal_value(progress.get(k,_MISSING)) for k in ('generation','completedAcquisitions','completedTimeCycles','failedCompletions','lastCompletedAgeMs')} if isinstance(progress,dict) else {'type':type(progress).__name__},
           'jobs':{k:_refusal_value(jobs.get(k,_MISSING),boolean=True) for k in ('running','booting','acquire','time','parentAcquire','parentTime')} if isinstance(jobs,dict) else {'type':type(jobs).__name__},
           'dueAt':_refusal_value(row.get('dueAt',_MISSING)),
           'dueReason':_refusal_value(row.get('dueReason',_MISSING),text=True)}
    # Defensive fail-closed evidence fallback must not replace the refusal.
    if len(json.dumps(value,allow_nan=False).encode())>REFUSAL_ROW_MAX_BYTES:
        return {'evidence':'UNMEASURED','code':'M7_REFUSAL_ROW_BOUND'}
    return value

def _round_view(services,ids,fetch,warming=False,allow_unavailable=False,allow_clinical_stall=False,*,policy=POLICY):
    """fetch(service,ids,query_budget,byte_budget) returns private JSONL bytes.

    The selected source roster sets the concurrent instance count. The source
    helper pages 128 per request; bounds apply across all instances.
    """
    validate_ids(ids);need(1<=len(services)<=POLICY['maxInstances'],'M7_EVALUATOR_PROGRESS_INSTANCE_BOUND')
    need(len(set(services))==len(services),'M7_EVALUATOR_PROGRESS_INSTANCE_BOUND')
    started=time.monotonic();max_queries=math.ceil(len(ids)/128)
    need(max_queries*len(services)*3<=policy['maxQueriesPerPhase'],'M7_EVALUATOR_PROGRESS_QUERY_BOUND')
    budget=policy['maxBytesPerPhase']//(3*len(services))
    need(budget>0,'M7_EVALUATOR_PROGRESS_BYTE_BOUND')
    with ThreadPoolExecutor(max_workers=len(services)) as executor:
        futures={service:executor.submit(fetch,service,ids,max_queries,budget) for service in services}
        raw={service:future.result() for service,future in futures.items()}
    identities={};owners={};all_rows={};bytes_seen=0;queries=0;known=set(ids)
    for instance_index,(service,data) in enumerate(raw.items()):
        if isinstance(data,str):data=data.encode()
        need(isinstance(data,bytes) and len(data)<=budget,'M7_EVALUATOR_PROGRESS_BYTE_BOUND')
        bytes_seen+=len(data);seen=set();runtime_id=None;ordinal=None;static_configuration=None;all_rows[service]={}
        for page_index,line in enumerate(data.splitlines()):
            queries+=1;need(len(line)<=POLICY['responseMaxBytes']+8192,'M7_EVALUATOR_PROGRESS_RESPONSE_BOUND')
            try:page=json.loads(line)
            except (ValueError,UnicodeError):raise Refused('M7_EVALUATOR_PROGRESS_RESPONSE')
            selected=page.get('selected');view=page.get('view',{});rows=view.get('tenants')
            need(isinstance(selected,list) and 1<=len(selected)<=128 and len(set(selected))==len(selected) and set(selected)<=known and not seen.intersection(selected),'M7_EVALUATOR_PROGRESS_SELECTOR')
            seen.update(selected)
            rid=view.get('runtimeId');position=view.get('configured',{}).get('ordinal')
            need(isinstance(rid,str) and UUID.fullmatch(rid) and integer(position),'M7_EVALUATOR_PROGRESS_CONTRACT')
            need(page.get('selfOrdinal')==position and page.get('selfMode')==view.get('configured',{}).get('mode'),'M7_EVALUATOR_PROGRESS_INSTANCE','FAIL')
            if page.get('selfMode')=='static':
                configured=view['configured']
                match=re.fullmatch(r'evaluator(?:-([2-8]))?',service)
                need(type(configured.get('count')) is int and type(page.get('selfCount')) is int
                     and configured['count']==len(services)==page['selfCount'] and match is not None
                     and position==int(match[1] or 1)-1 and position<len(services)
                     and configured.get('rule')=='sha256-modulo-v1' and 'leaseMs' in configured and configured['leaseMs'] is None
                     and 'observed' in view and view['observed'] is None
                     and type(view.get('gate',{}).get('members')) is int and view['gate']['members']==len(services),
                     'M7_EVALUATOR_STATIC_CONFIGURATION','FAIL')
                current_static={'count':configured['count'],'rule':configured['rule'],'observed':None}
                need(static_configuration is None or static_configuration==current_static,'M7_EVALUATOR_STATIC_CONFIGURATION','FAIL')
                static_configuration=current_static
            need(runtime_id is None or runtime_id==rid,'M7_EVALUATOR_PROGRESS_RESET','FAIL');runtime_id=rid
            need(ordinal is None or ordinal==position,'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL');ordinal=position
            need(view.get('kind')=='evaluator' and view.get('gate',{}).get('eligible') is True and view['gate'].get('reason') is None,'M7_EVALUATOR_PROGRESS_GATE','UNMEASURED' if warming else 'FAIL')
            need(isinstance(rows,list) and len(rows)==len(selected) and {row.get('tenant') for row in rows}==set(selected),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
            for row_index,row in enumerate(rows):
                def contract(valid,field,predicate,code='M7_EVALUATOR_PROGRESS_CONTRACT',verdict='UNMEASURED'):
                    if not valid:
                        error=Refused(code,verdict)
                        error.diagnostic={'predicate':predicate,'field':field,'instanceIndex':instance_index,'pageIndex':page_index,'rowIndex':row_index,'warming':warming,
                                          'failedRow':_refusal_row(row,service,runtime_id)}
                        raise error
                tenant=row['tenant'];progress=row.get('progress',{})
                contract(isinstance(progress,dict),'progress','OBJECT_REQUIRED')
                for field in ('generation','completedAcquisitions','completedTimeCycles','failedCompletions'):
                    contract(integer(progress.get(field)),field,'NONNEGATIVE_SAFE_INTEGER_REQUIRED')
                contract('lastCompletedAgeMs' in progress,'lastCompletedAgeMs','FIELD_REQUIRED')
                age=progress.get('lastCompletedAgeMs')
                contract(age is None or type(age) in (int,float) and math.isfinite(age) and age>=0,'lastCompletedAgeMs','NULL_OR_FINITE_NONNEGATIVE_REQUIRED')
                value={'service':service,'runtimeId':rid,'legacyCycles':row.get('cycles'),'admitted':row.get('admitted'),'ready':row.get('ready'),'code':row.get('code'),'alert':row.get('evaluation',{}).get('alert'),**{k:progress[k] for k in ('generation','completedAcquisitions','completedTimeCycles','failedCompletions','lastCompletedAgeMs')}}
                contract(integer(value['legacyCycles']),'cycles','NONNEGATIVE_SAFE_INTEGER_REQUIRED')
                for field in ('admitted','ready'):
                    contract(type(value[field]) is bool,field,'BOOLEAN_REQUIRED')
                value.update(due_fields(row));value['jobState']=row.get('jobs')
                if value['jobState'] is not None:
                    try:job_state(value['jobState'])
                    except Refused as error:
                        error.diagnostic={'field':'jobs','predicate':'SIX_FIXED_BOOLEAN_FLAGS_REQUIRED','failedRow':_refusal_row(row,service,runtime_id)}
                        raise
                all_rows[service][tenant]=value
                if not value['admitted']:
                    need(not value['ready'],'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL');continue
                need(tenant not in owners,'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
                warm_code=warming and value['code'] in ('EVALUATOR_STARTING','EVALUATOR_ACQUISITION_REQUIRED')
                stall=allow_clinical_stall and clinical_stall(value)
                for field,valid,predicate in (('ready',stall or value['ready'] or allow_unavailable and value['code'] is None and value['alert'] is None and job_state(value['jobState']),'OWNER_READY_REQUIRED'),('code',value['code'] is None or stall,'OWNER_CODE_NULL_REQUIRED'),('evaluation.alert',value['alert'] is None,'OWNER_ALERT_NULL_REQUIRED')):
                    contract(valid,field,predicate,'M7_EVALUATOR_PROGRESS_ERROR','UNMEASURED' if warm_code else 'FAIL')
                # A first admitted cycle can be ready before its operation-window
                # release has completed. It earns no credit yet; readiness must
                # still wait for completedAcquisitions > 0. Only that complete
                # zero-credit shape may have null age, and only during warming.
                first_release=(warming or allow_unavailable and value['jobState'] is not None) and all(value[k]==0 for k in ('completedAcquisitions','completedTimeCycles'))
                contract(age is not None or first_release,'lastCompletedAgeMs','COMPLETION_AGE_OR_FIRST_RELEASE_REQUIRED')
                owners[tenant]=value
        need(seen==known,'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        identities[service]={'runtimeId':runtime_id,'ordinal':ordinal,**({'static':static_configuration} if static_configuration else {})}
    need(len({v['runtimeId'] for v in identities.values()})==len(services) and len({v['ordinal'] for v in identities.values()})==len(services),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    need(set(owners)==known,'M7_EVALUATOR_PROGRESS_COVERAGE','UNMEASURED' if warming else 'FAIL')
    need(queries==max_queries*len(services),'M7_EVALUATOR_PROGRESS_QUERY_BOUND')
    return {'instances':identities,'owners':owners,'allRows':all_rows,'queries':queries,'bytes':bytes_seen,'wallSeconds':time.monotonic()-started}

def round_view(services,ids,fetch,warming=False,allow_unavailable=False,allow_clinical_stall=False,*,policy=POLICY):
    captured={};started=time.monotonic()
    def measured(service,*args):
        value=fetch(service,*args);captured[service]=value.encode() if isinstance(value,str) else value
        return value
    try:return _round_view(services,ids,measured,warming,allow_unavailable,allow_clinical_stall,policy=policy)
    except Refused as error:
        error.collection={'queries':sum(len(v.splitlines()) for v in captured.values() if isinstance(v,bytes)),
                          'bytes':sum(len(v) for v in captured.values() if isinstance(v,bytes)),
                          'wallSeconds':time.monotonic()-started,'completeResponses':len(captured)==len(services),
                          'diagnostic':getattr(error,'diagnostic',None)}
        raise


def assess(rounds,ids,phase,*,policy=POLICY,discovery_unclassified_rejections=False,failure_policy=None):
    failure_policy=select_failure_policy(failure_policy)
    need(phase in ('idle','load') and len(rounds)==3,'M7_EVALUATOR_PROGRESS_ROUNDS')
    need(sum(r['queries'] for r in rounds)<=policy['maxQueriesPerPhase'] and sum(r['bytes'] for r in rounds)<=policy['maxBytesPerPhase'],'M7_EVALUATOR_PROGRESS_BUDGET')
    first=rounds[0];minimum=None;time_tenants=0;failure_delta=0;work_delta=0;time_delta=0
    previous=first
    for current in rounds[1:]:
        need(current['instances']==first['instances'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
        need(set(current['owners'])==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        for tenant in ids:
            a=previous['owners'][tenant];b=current['owners'][tenant]
            need((a['service'],a['runtimeId'])==(b['service'],b['runtimeId']),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            need(all(b[k]>=a[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
        for service,rows in previous['allRows'].items():
            need(set(current['allRows'].get(service,{}))==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
            for tenant,a in rows.items():
                b=current['allRows'][service][tenant]
                need(a['admitted']==b['admitted'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
                if not a['admitted']:
                    need(not b['ready'] and all(a[k]==b[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
        previous=current
    for tenant in ids:
        a=first['owners'][tenant];b=rounds[-1]['owners'][tenant]
        failure_delta+=b['failedCompletions']-a['failedCompletions']
        work=b['completedAcquisitions']-a['completedAcquisitions']+b['completedTimeCycles']-a['completedTimeCycles'];delta=b['completedTimeCycles']-a['completedTimeCycles']
        need(work>0,'M7_EVALUATOR_PROGRESS_NOT_OBSERVED')
        minimum=work if minimum is None else min(minimum,work);work_delta+=work;time_delta+=delta;time_tenants+=delta>0
    judged={'failurePolicy':failure_policy,'lifetimeFailedCompletions':sum(rounds[-1]['owners'][t]['failedCompletions'] for t in ids)}
    return {**judged,'version':policy['version'],'phase':phase,'verdict':'PASS','policy':policy,'tenants':len(ids),'instances':first['instances'],'completedWorkDelta':work_delta,'completedTimeDelta':time_delta,'tenantsWithTimeProgress':time_tenants,'minimumCompletedWorkDelta':minimum,'failedCompletionDelta':failure_delta,'queries':sum(r['queries'] for r in rounds),'responseBytes':sum(r['bytes'] for r in rounds),'collectorWallSeconds':sum(r['wallSeconds'] for r in rounds),'scope':'bookend/midpoint successful work; failedCompletionDelta counts unclassified rejected attempts, including superseded windows, not clinical failures; no strict deadline or true cold load cohort claim' if discovery_unclassified_rejections else 'bookend/midpoint successful work; no strict deadline or true cold load cohort claim'}

def readiness_refusal(error):
    diagnostic=getattr(error,'diagnostic',None)
    return str(error)=='M7_EVALUATOR_PROGRESS_ERROR' and isinstance(diagnostic,dict) and diagnostic.get('field') in ('ready','code')


class Observer:
    def __init__(self,services,ids,fetch,seconds,phase,write,*,assessor=assess,policy=POLICY,midpoint_judge=None,signal_write=None,on_hard_midpoint=None):
        self.services,self.ids,self.seconds,self.phase,self.write=services,ids,seconds,phase,write
        self.assessor,self.policy=assessor,policy
        self.rounds=[];self.failure=None;self.stop=threading.Event()
        # Raw-first: keep each service's latest response bytes before decoding,
        # so a midpoint refusal can still be classified from the source rows.
        self.last_raw={};self.midpoint_judge=midpoint_judge;self.signal_write=signal_write
        self.on_hard_midpoint=on_hard_midpoint;self.midpoint_signal=None
        def retained(service,*args):
            value=fetch(service,*args);self.last_raw[service]=value;return value
        self.fetch=retained
    def midpoint(self):
        """Midpoint is a signal; only a hard outcome reason stops the driver."""
        self.last_raw={};self.observe()
        if self.midpoint_judge is None:return
        refusal=self.failure
        try:decision=self.midpoint_judge(dict(self.last_raw))
        except Exception as error:decision={'action':'continue','reason':'judge-error','signal':'UNMEASURED','judgeError':type(error).__name__}
        decision={**decision,'strictRefusal':None if refusal is None else {'code':str(refusal),'verdict':getattr(refusal,'verdict','UNMEASURED')}}
        self.midpoint_signal=decision
        if self.signal_write is not None:
            try:self.signal_write(decision)
            except Exception:decision['publicationFailed']=True
        if decision['action']=='stop':
            if refusal is None:self.failure=Refused('M7_OUTCOME_MIDPOINT_HARD','FAIL')
            if self.on_hard_midpoint is not None:self.on_hard_midpoint()
        elif refusal is not None and readiness_refusal(refusal):
            # Midpoint readiness is a recorded signal, not a phase failure. The
            # phase then has two strict rounds; the outcome gate judges from the
            # retained raw pages. Other strict refusals keep their verdict.
            self.failure=None
    def observe(self):
        try:self.rounds.append(round_view(self.services,self.ids,self.fetch,policy=self.policy))
        except Exception as error:self.failure=error
    def failed(self,error,extra=None):
        self.write({'version':self.policy['version'],'phase':self.phase,'verdict':getattr(error,'verdict','UNMEASURED'),'code':str(error),'policy':self.policy,'rounds':self.rounds,'failedCollection':getattr(error,'collection',None),**(extra or {})})
    def __enter__(self):
        self.observe()
        if self.failure:
            self.failed(self.failure);raise self.failure
        def midpoint():
            if not self.stop.wait(self.seconds/2):self.midpoint()
        self.thread=threading.Thread(target=midpoint,daemon=True);self.thread.start();return self
    def __exit__(self,kind,value,traceback):
        self.stop.set();self.thread.join(timeout=20)
        if kind:
            # Preserve bounded partial observations without replacing the body
            # exception (for example the actual k6 refusal/failure).
            try:self.failed(Refused('M7_EVALUATOR_PROGRESS_BODY_FAILED','FAIL'),{'interruptedBody':True,'bodyFailureType':type(value).__name__,'collectorFailure':str(self.failure) if self.failure else None,'collectorStillRunning':self.thread.is_alive()})
            except Exception:self.publicationFailed=True
            return False
        if self.thread.is_alive():
            error=Refused('M7_EVALUATOR_PROGRESS_COLLECTOR_TIMEOUT');self.failed(error);raise error
        if self.failure:
            self.failed(self.failure);raise self.failure
        self.observe()
        self.finish()

    def finish(self):
        try:
            if self.failure:raise self.failure
            extra={'failure_policy':self.failure_policy} if getattr(self,'failure_policy',None) else {}
            result=self.assessor(self.rounds,self.ids,self.phase,policy=self.policy,**extra)
        except Exception as error:
            self.failed(error);raise
        self.write({**result,'rounds':self.rounds});self.result=result


COLUMNS=('tenant','service','generation','completedAcquisitions','completedTimeCycles','failedCompletions','lastCompletedAgeMs','legacyCycles','admitted','ready','code','alert','dueAt','dueReason','jobState')

def pack(value):
    result={**value,'kind':'evaluator-progress-phase-v2','columns':list(COLUMNS),'rounds':[]}
    for raw in value.get('rounds',[]):
        result['rounds'].append({**{k:v for k,v in raw.items() if k not in ('owners','allRows')},'rows':[[tenant]+[row.get(key) if key=='jobState' else row[key] for key in COLUMNS[1:]] for service,values in sorted(raw['allRows'].items()) for tenant,row in sorted(values.items())]})
    return result


def verify(value,tenants,services,phase,*,budget=None):
    need(isinstance(value,dict),'M7_EVALUATOR_PROGRESS_PROOF')
    policy=value.get('policy')
    need(value.get('kind')=='evaluator-progress-phase-v2' and value.get('columns')==list(COLUMNS) and policy==(capture_policy(budget) if budget is not None else POLICY) and value.get('verdict')=='PASS','M7_EVALUATOR_PROGRESS_PROOF')
    need(1<=len(services)<=policy['maxInstances'],'M7_EVALUATOR_PROGRESS_INSTANCE_BOUND')
    need(type(tenants) is int and 1<=tenants<=policy['maxTenants'],'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    need(isinstance(value.get('rounds'),list) and len(value['rounds'])==3,'M7_EVALUATOR_PROGRESS_ROUNDS')
    decoded,ids=decode_rounds(value,tenants,services)
    result=assess(decoded,sorted(ids),phase,policy=policy,failure_policy=value.get('failurePolicy'))
    need({k:v for k,v in value.items() if k not in ('kind','columns','rounds','attribution')}==result,'M7_EVALUATOR_PROGRESS_ASSESSMENT')
    return result


def decode_rounds(value,tenants,services,*,allow_unavailable=False,allow_clinical_stall=False):
    columns=value.get('columns')
    need(columns==list(COLUMNS),'M7_EVALUATOR_PROGRESS_COLUMNS')
    if 'kind' in value:need(value['kind']=='evaluator-progress-phase-v2','M7_EVALUATOR_PROGRESS_COLUMNS')
    decoded=[];ids=None
    for raw in value['rounds']:
        need(isinstance(raw,dict) and isinstance(raw.get('instances'),dict) and set(raw['instances'])==set(services),'M7_EVALUATOR_PROGRESS_INSTANCE')
        need(len({r.get('runtimeId') for r in raw['instances'].values()})==len(services) and len({r.get('ordinal') for r in raw['instances'].values()})==len(services),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        need(all(isinstance(r.get('runtimeId'),str) and UUID.fullmatch(r['runtimeId']) and integer(r.get('ordinal')) for r in raw['instances'].values()),'M7_EVALUATOR_PROGRESS_CONTRACT')
        selected_static=value.get('attribution',{}).get('staticTopology')
        if selected_static or any('static' in row for row in raw['instances'].values()):
            count=len(services)
            need(not selected_static or selected_static=={'kind':'static-hash-v1','workers':count},'M7_EVALUATOR_STATIC_CONFIGURATION','FAIL')
            need(all(row.get('static')=={'count':count,'rule':'sha256-modulo-v1','observed':None} for row in raw['instances'].values()),'M7_EVALUATOR_STATIC_CONFIGURATION','FAIL')
        need(integer(raw.get('queries')) and integer(raw.get('bytes')) and type(raw.get('wallSeconds')) in (int,float) and math.isfinite(raw['wallSeconds']) and raw['wallSeconds']>=0,'M7_EVALUATOR_PROGRESS_OVERHEAD')
        owners={};all_rows={service:{} for service in services};rows=raw.get('rows')
        need(isinstance(rows,list) and len(rows)==tenants*len(services) and 1<=tenants<=POLICY['maxTenants'],'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        for packed in rows:
            need(isinstance(packed,list) and len(packed)==len(columns),'M7_EVALUATOR_PROGRESS_PROOF')
            row=dict(zip(columns,packed));tenant=row.pop('tenant');service=row['service']
            need(isinstance(tenant,str) and UUID.fullmatch(tenant) and service in all_rows and tenant not in all_rows[service],'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
            age=row['lastCompletedAgeMs']
            need(all(integer(row[k]) for k in ('generation','completedAcquisitions','completedTimeCycles','failedCompletions')) and (age is None or type(age) in (int,float) and math.isfinite(age) and age>=0),'M7_EVALUATOR_PROGRESS_CONTRACT')
            need(integer(row['legacyCycles']) and type(row['admitted']) is bool and type(row['ready']) is bool,'M7_EVALUATOR_PROGRESS_CONTRACT')
            due_fields(row)
            if row.get('jobState') is not None:job_state(row['jobState'])
            row['runtimeId']=raw['instances'][service]['runtimeId'];all_rows[service][tenant]=row
            if row['admitted']:
                stall=allow_clinical_stall and clinical_stall(row)
                need(tenant not in owners and (stall or row['ready'] or allow_unavailable and job_state(row.get('jobState'))) and (row['code'] is None or stall) and row['alert'] is None and (age is not None or allow_unavailable and row.get('jobState') is not None and row['completedAcquisitions']==row['completedTimeCycles']==0),'M7_EVALUATOR_PROGRESS_ERROR','FAIL')
                owners[tenant]=row
            else:need(not row['ready'],'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
        need(len(owners)==tenants and all(set(values)==set(owners) for values in all_rows.values()),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        need(ids is None or ids==set(owners),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL');ids=set(owners)
        need(raw['queries']==math.ceil(tenants/128)*len(services),'M7_EVALUATOR_PROGRESS_QUERY_BOUND')
        decoded.append({**raw,'owners':owners,'allRows':all_rows})
    return decoded,ids


def stable_discovery_baseline(first,last,ids,*,allow_clinical_stall=False):
    """Historical uncredited attempts may predate this healthy stable bracket."""
    decoded,actual=decode_rounds(pack({'rounds':[first,last,last]}),len(ids),list(first['instances']),allow_unavailable=True,allow_clinical_stall=allow_clinical_stall)
    need(actual==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    try:assess(decoded,ids,'load',discovery_unclassified_rejections=True)
    except Refused as error:
        if str(error)!='M7_EVALUATOR_PROGRESS_NOT_OBSERVED':raise
    return {'baselineUncreditedAttempts':sum(row['failedCompletions'] for row in first['owners'].values()),
            'uncreditedAttemptDelta':sum(last['owners'][tenant]['failedCompletions']-first['owners'][tenant]['failedCompletions'] for tenant in ids),
            'availability':availability([first,last],ids),
            'dependentRejectionCauseClaim':'UNMEASURED',
            'causeAttribution':'UNMEASURED','scope':'stable same-runtime bracket; explicit clinical stall remains FAIL alongside independent REST' if allow_clinical_stall else 'stable healthy same-runtime bracket; historical count does not establish a clinical failure or globally error-free execution'}


JOB_FLAGS=('running','booting','acquire','time','parentAcquire','parentTime')
def job_state(value):
    need(isinstance(value,dict) and set(value)==set(JOB_FLAGS) and all(type(v)is bool for v in value.values()),'M7_EVALUATOR_PROGRESS_CONTRACT','FAIL')
    return True

def availability(rounds,ids):
    counts={'READY':0,'BUSY':0,'BOOTING':0,'COLD_OR_UNOBSERVED':0,'FIRST_WINDOW_UNCONFIRMED':0}
    for point in rounds:
        for tenant in ids:
            row=point['owners'][tenant]
            if clinical_stall(row):reason='CLINICAL_STALL';counts.setdefault(reason,0)
            elif row['ready'] and row['completedAcquisitions']>0 and row['lastCompletedAgeMs'] is not None:reason='READY'
            else:
                job_state(row.get('jobState'));jobs=row['jobState']
                reason='BUSY' if jobs['running'] else 'BOOTING' if jobs['booting'] else 'COLD_OR_UNOBSERVED' if not row['ready'] else 'FIRST_WINDOW_UNCONFIRMED'
            counts[reason]+=1
    return {'verdict':'FAIL' if counts.get('CLINICAL_STALL') else 'PASS' if sum(counts.values())==counts['READY'] else 'UNMEASURED','sampledRows':sum(counts.values()),'classifications':counts,'scope':'availability only; busy/booting/cold causes are not proven benign; durable completion and client correctness are separate'}


def clinical_stall(row):
    """An explicit clinical stall remains FAIL whether its worker is busy or idle.

    Job flags describe an observation, not the clinical result. The separate
    discovery REST path retains this FAIL while collecting independent work.
    """
    # A source-reported stall can predate the first completed acquisition.
    # Completion counts and ages remain validated by the caller; they earn
    # no clinical credit merely because independent REST is observable.
    return row.get('admitted') is True and row.get('ready') is False and row.get('code')=='EVALUATOR_CLINICAL_PROGRESS_STALLED' and row.get('alert') is None and job_state(row.get('jobState'))
