"""Bounded private evaluator completion observations; never triggers work."""
import json
import math
import re
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

UUID=re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
LEGACY_POLICY={'version':1,'moduleVersion':2,'selectorRows':128,'maxTenants':10000,'maxInstances':4,
        'roundsPerPhase':3,'maxQueriesPerPhase':1024,'maxBytesPerPhase':67108864,
        'responseMaxBytes':1048576,'rpcTimeoutMs':5000,'roundDeadlineMs':15000,
        'idleWitness':'successful-time-only-completion','loadWitness':'successful-work-progression',
        'recoveryCadenceMs':15000,'recoveryTimeoutMs':900000,'recoveryMaxRounds':60,'readinessMaxQueries':25600,'readinessMaxBytes':268435456,'readinessMaxRounds':80,'deadlineClaim':False,'workloadCohortChanged':False}
POLICY={**LEGACY_POLICY,'version':2,'dueState':'captured-only-not-opportunity-assessed'}

class Refused(RuntimeError):
    def __init__(self,code,verdict='UNMEASURED'):
        super().__init__(code);self.verdict=verdict

def need(value,code,verdict='UNMEASURED'):
    if not value:raise Refused(code,verdict)

def integer(value,minimum=0):return type(value) is int and minimum<=value<=9007199254740991

def due_fields(row):
    need('dueAt' in row and 'dueReason' in row,'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
    at,reason=row['dueAt'],row['dueReason']
    need(at is None or type(at) in (int,float) and math.isfinite(at) and at>=0,'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
    need(reason is None or isinstance(reason,str) and re.fullmatch(r'[a-z][a-z0-9:,_-]{0,127}',reason),'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
    need(at is not None or reason is None,'M7_EVALUATOR_PROGRESS_DUE_CONTRACT')
    return {'dueAt':at,'dueReason':reason}

def validate_ids(ids):
    need(isinstance(ids,list) and 1<=len(ids)<=POLICY['maxTenants'] and len(set(ids))==len(ids) and all(isinstance(v,str) and UUID.fullmatch(v) for v in ids),'M7_EVALUATOR_PROGRESS_TENANTS')

def _round_view(services,ids,fetch,warming=False):
    """fetch(service,ids,query_budget,byte_budget) returns private JSONL bytes.

    At most four actual instance execs run concurrently. The source helper
    pages128 per request; bounds apply before decoding and across all instances.
    """
    validate_ids(ids);need(1<=len(services)<=POLICY['maxInstances'],'M7_EVALUATOR_PROGRESS_INSTANCE_BOUND')
    need(len(set(services))==len(services),'M7_EVALUATOR_PROGRESS_INSTANCE_BOUND')
    started=time.monotonic();max_queries=math.ceil(len(ids)/128)
    need(max_queries*len(services)*3<=POLICY['maxQueriesPerPhase'],'M7_EVALUATOR_PROGRESS_QUERY_BOUND')
    budget=POLICY['maxBytesPerPhase']//(3*len(services))
    with ThreadPoolExecutor(max_workers=len(services)) as executor:
        futures={service:executor.submit(fetch,service,ids,max_queries,budget) for service in services}
        raw={service:future.result() for service,future in futures.items()}
    identities={};owners={};all_rows={};bytes_seen=0;queries=0;known=set(ids)
    for instance_index,(service,data) in enumerate(raw.items()):
        if isinstance(data,str):data=data.encode()
        need(isinstance(data,bytes) and len(data)<=budget,'M7_EVALUATOR_PROGRESS_BYTE_BOUND')
        bytes_seen+=len(data);seen=set();runtime_id=None;ordinal=None;all_rows[service]={}
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
            need(runtime_id is None or runtime_id==rid,'M7_EVALUATOR_PROGRESS_RESET','FAIL');runtime_id=rid
            need(ordinal is None or ordinal==position,'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL');ordinal=position
            need(view.get('kind')=='evaluator' and view.get('gate',{}).get('eligible') is True and view['gate'].get('reason') is None,'M7_EVALUATOR_PROGRESS_GATE','UNMEASURED' if warming else 'FAIL')
            need(isinstance(rows,list) and len(rows)==len(selected) and {row.get('tenant') for row in rows}==set(selected),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
            for row_index,row in enumerate(rows):
                def contract(valid,field,predicate,code='M7_EVALUATOR_PROGRESS_CONTRACT',verdict='UNMEASURED'):
                    if not valid:
                        error=Refused(code,verdict)
                        error.diagnostic={'predicate':predicate,'field':field,'instanceIndex':instance_index,'pageIndex':page_index,'rowIndex':row_index,'warming':warming}
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
                value.update(due_fields(row))
                all_rows[service][tenant]=value
                if not value['admitted']:
                    need(not value['ready'],'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL');continue
                need(tenant not in owners,'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
                warm_code=warming and value['code'] in ('EVALUATOR_STARTING','EVALUATOR_ACQUISITION_REQUIRED')
                for field,valid,predicate in (('ready',value['ready'],'OWNER_READY_REQUIRED'),('code',value['code'] is None,'OWNER_CODE_NULL_REQUIRED'),('evaluation.alert',value['alert'] is None,'OWNER_ALERT_NULL_REQUIRED')):
                    contract(valid,field,predicate,'M7_EVALUATOR_PROGRESS_ERROR','UNMEASURED' if warm_code else 'FAIL')
                # A first admitted cycle can be ready before its operation-window
                # release has completed. It earns no credit yet; readiness must
                # still wait for completedAcquisitions > 0. Only that complete
                # zero-credit shape may have null age, and only during warming.
                first_release=warming and all(value[k]==0 for k in ('completedAcquisitions','completedTimeCycles','failedCompletions'))
                contract(age is not None or first_release,'lastCompletedAgeMs','COMPLETION_AGE_OR_FIRST_RELEASE_REQUIRED')
                owners[tenant]=value
        need(seen==known,'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        identities[service]={'runtimeId':runtime_id,'ordinal':ordinal}
    need(len({v['runtimeId'] for v in identities.values()})==len(services) and len({v['ordinal'] for v in identities.values()})==len(services),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    need(set(owners)==known,'M7_EVALUATOR_PROGRESS_COVERAGE','UNMEASURED' if warming else 'FAIL')
    need(queries==max_queries*len(services),'M7_EVALUATOR_PROGRESS_QUERY_BOUND')
    return {'instances':identities,'owners':owners,'allRows':all_rows,'queries':queries,'bytes':bytes_seen,'wallSeconds':time.monotonic()-started}

def round_view(services,ids,fetch,warming=False):
    captured={};started=time.monotonic()
    def measured(service,*args):
        value=fetch(service,*args);captured[service]=value.encode() if isinstance(value,str) else value
        return value
    try:return _round_view(services,ids,measured,warming)
    except Refused as error:
        error.collection={'queries':sum(len(v.splitlines()) for v in captured.values() if isinstance(v,bytes)),
                          'bytes':sum(len(v) for v in captured.values() if isinstance(v,bytes)),
                          'wallSeconds':time.monotonic()-started,'completeResponses':len(captured)==len(services),
                          'diagnostic':getattr(error,'diagnostic',None)}
        raise


def assess(rounds,ids,phase,*,policy=POLICY):
    need(phase in ('idle','load') and len(rounds)==3,'M7_EVALUATOR_PROGRESS_ROUNDS')
    need(sum(r['queries'] for r in rounds)<=POLICY['maxQueriesPerPhase'] and sum(r['bytes'] for r in rounds)<=POLICY['maxBytesPerPhase'],'M7_EVALUATOR_PROGRESS_BUDGET')
    first=rounds[0];minimum=None;time_tenants=0;failure_delta=0;work_delta=0;time_delta=0
    previous=first
    for current in rounds[1:]:
        need(current['instances']==first['instances'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
        need(set(current['owners'])==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        for tenant in ids:
            a=previous['owners'][tenant];b=current['owners'][tenant]
            need((a['service'],a['runtimeId'],a['generation'])==(b['service'],b['runtimeId'],b['generation']),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            need(all(b[k]>=a[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions')),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            need(b['failedCompletions']==a['failedCompletions'],'M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE','FAIL')
        for service,rows in previous['allRows'].items():
            need(set(current['allRows'].get(service,{}))==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
            for tenant,a in rows.items():
                b=current['allRows'][service][tenant]
                need(a['admitted']==b['admitted'] and a['generation']==b['generation'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
                if not a['admitted']:
                    need(not b['ready'] and all(a[k]==b[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
        previous=current
    for tenant in ids:
        a=first['owners'][tenant];b=rounds[-1]['owners'][tenant]
        need(a['failedCompletions']==0,'M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE','FAIL')
        work=b['completedAcquisitions']-a['completedAcquisitions']+b['completedTimeCycles']-a['completedTimeCycles'];delta=b['completedTimeCycles']-a['completedTimeCycles']
        need(work>0 and (phase!='idle' or delta>0),'M7_EVALUATOR_PROGRESS_NOT_OBSERVED')
        minimum=work if minimum is None else min(minimum,work);work_delta+=work;time_delta+=delta;time_tenants+=delta>0
    return {'version':policy['version'],'phase':phase,'verdict':'PASS','policy':policy,'tenants':len(ids),'instances':first['instances'],'completedWorkDelta':work_delta,'completedTimeDelta':time_delta,'tenantsWithTimeProgress':time_tenants,'minimumCompletedWorkDelta':minimum,'failedCompletionDelta':failure_delta,'queries':sum(r['queries'] for r in rounds),'responseBytes':sum(r['bytes'] for r in rounds),'collectorWallSeconds':sum(r['wallSeconds'] for r in rounds),'scope':'bookend/midpoint successful work; no strict deadline or true cold load cohort claim'}

class Observer:
    def __init__(self,services,ids,fetch,seconds,phase,write,*,assessor=assess,policy=POLICY):
        self.services,self.ids,self.fetch,self.seconds,self.phase,self.write=services,ids,fetch,seconds,phase,write
        self.assessor,self.policy=assessor,policy
        self.rounds=[];self.failure=None;self.stop=threading.Event()
    def observe(self):
        try:self.rounds.append(round_view(self.services,self.ids,self.fetch))
        except Exception as error:self.failure=error
    def failed(self,error,extra=None):
        self.write({'version':self.policy['version'],'phase':self.phase,'verdict':getattr(error,'verdict','UNMEASURED'),'code':str(error),'policy':self.policy,'rounds':self.rounds,'failedCollection':getattr(error,'collection',None),**(extra or {})})
    def __enter__(self):
        self.observe()
        if self.failure:
            self.failed(self.failure);raise self.failure
        def midpoint():
            if not self.stop.wait(self.seconds/2):self.observe()
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
        try:
            if self.failure:raise self.failure
            result=self.assessor(self.rounds,self.ids,self.phase)
        except Exception as error:
            self.failed(error);raise
        self.write({**result,'rounds':self.rounds});self.result=result


LEGACY_COLUMNS=('tenant','service','generation','completedAcquisitions','completedTimeCycles','failedCompletions','lastCompletedAgeMs','legacyCycles','admitted','ready','code','alert')
COLUMNS=LEGACY_COLUMNS+('dueAt','dueReason')

def pack(value):
    result={**value,'kind':'evaluator-progress-phase-v2','columns':list(COLUMNS),'rounds':[]}
    for raw in value.get('rounds',[]):
        result['rounds'].append({**{k:v for k,v in raw.items() if k not in ('owners','allRows')},'rows':[[tenant]+[row[key] for key in COLUMNS[1:]] for service,values in sorted(raw['allRows'].items()) for tenant,row in sorted(values.items())]})
    return result


def verify(value,tenants,services,phase):
    need(isinstance(value,dict),'M7_EVALUATOR_PROGRESS_PROOF')
    legacy=value.get('kind')=='evaluator-progress-phase-v1'
    policy=LEGACY_POLICY if legacy else POLICY
    columns=LEGACY_COLUMNS if legacy else COLUMNS
    need(value.get('kind')==('evaluator-progress-phase-v1' if legacy else 'evaluator-progress-phase-v2') and value.get('columns')==list(columns) and value.get('policy')==policy and value.get('verdict')=='PASS','M7_EVALUATOR_PROGRESS_PROOF')
    need(isinstance(value.get('rounds'),list) and len(value['rounds'])==3,'M7_EVALUATOR_PROGRESS_ROUNDS')
    decoded,ids=decode_rounds(value,tenants,services)
    result=assess(decoded,sorted(ids),phase,policy=policy)
    need({k:v for k,v in value.items() if k not in ('kind','columns','rounds','attribution')}==result,'M7_EVALUATOR_PROGRESS_ASSESSMENT')
    return result


def decode_rounds(value,tenants,services):
    columns=value.get('columns')
    need(columns in (list(LEGACY_COLUMNS),list(COLUMNS)),'M7_EVALUATOR_PROGRESS_COLUMNS')
    legacy=columns==list(LEGACY_COLUMNS)
    if 'kind' in value:need(value['kind']==('evaluator-progress-phase-v1' if legacy else 'evaluator-progress-phase-v2'),'M7_EVALUATOR_PROGRESS_COLUMNS')
    decoded=[];ids=None
    for raw in value['rounds']:
        need(isinstance(raw,dict) and isinstance(raw.get('instances'),dict) and set(raw['instances'])==set(services),'M7_EVALUATOR_PROGRESS_INSTANCE')
        need(len({r.get('runtimeId') for r in raw['instances'].values()})==len(services) and len({r.get('ordinal') for r in raw['instances'].values()})==len(services),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        need(all(isinstance(r.get('runtimeId'),str) and UUID.fullmatch(r['runtimeId']) and integer(r.get('ordinal')) for r in raw['instances'].values()),'M7_EVALUATOR_PROGRESS_CONTRACT')
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
            if not legacy:due_fields(row)
            row['runtimeId']=raw['instances'][service]['runtimeId'];all_rows[service][tenant]=row
            if row['admitted']:
                need(tenant not in owners and row['ready'] and row['code'] is None and row['alert'] is None and age is not None,'M7_EVALUATOR_PROGRESS_ERROR','FAIL')
                owners[tenant]=row
            else:need(not row['ready'],'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
        need(len(owners)==tenants and all(set(values)==set(owners) for values in all_rows.values()),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        need(ids is None or ids==set(owners),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL');ids=set(owners)
        need(raw['queries']==math.ceil(tenants/128)*len(services),'M7_EVALUATOR_PROGRESS_QUERY_BOUND')
        decoded.append({**raw,'owners':owners,'allRows':all_rows})
    return decoded,ids
