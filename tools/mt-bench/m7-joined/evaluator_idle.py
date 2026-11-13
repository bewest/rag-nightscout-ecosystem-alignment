"""Idle safety is absence of observed evaluator demand, never a work witness."""
import copy
import math
import json
import time
import evaluator_progress as p

# moduleVersion identifies this idle assessor; strictWorkPolicy still pins the
# unchanged source inspection/work protocol. The packed row schema stays v1.
FLAGS=('running','booting','acquire','time','parentAcquire','parentTime')
ARTIFACT_KIND='evaluator-idle-safety-v2'
TAIL_POLICY={'maxOwners':128,'maxRounds':1,'deadlineMs':5000,'scope':'point completion after original cost bookends; no global tail quiescence'}
POLICY={'version':2,'kind':'evaluator-idle-safety','moduleVersion':4,'completionTail':TAIL_POLICY,
        'strictWorkPolicy':p.POLICY,'meaning':'NO_EVALUATOR_TIME_DEMAND or observed successful time work',
        'quietMeaning':'TIME_NOT_EXERCISED','clockGuard':'common-bracketed-realtime-minus-monotonic-offset',
        'jobEncoding':'six-fixed-clinical-flags-bitmask-v1','newClinicalDemand':'UNMEASURED','explicitNullDue':'NO_TIMER_DECLARED_WITH_COMPLETE_JOB_OBSERVATION','missingDue':'UNMEASURED','nativeTimeWitnessRequired':True,
        'deadlineClaim':False,'continuousQuiescenceClaim':False}
COLUMNS=p.COLUMNS+('jobs',)

def stamp():
    before=time.monotonic_ns()//1000
    wall=time.time_ns()//1000
    after=time.monotonic_ns()//1000
    return {'wallUs':wall,'monoBeforeUs':before,'monoAfterUs':after}

def jobs(value):
    p.need(isinstance(value,dict) and set(value)==set(FLAGS) and all(type(value[k]) is bool for k in FLAGS),'M7_EVALUATOR_IDLE_JOBS')
    return value

def clock_windows(rounds):
    lower=None;upper=None;previous_end=None
    for current in rounds:
        windows=current.get('readWindows')
        p.need(isinstance(windows,dict) and set(windows)==set(current['instances']),'M7_EVALUATOR_IDLE_CLOCK')
        starts=[];ends=[]
        for window in windows.values():
            p.need(isinstance(window,dict) and set(window)=={'start','end','observedAt'},'M7_EVALUATOR_IDLE_CLOCK')
            for key in ('start','end'):
                s=window[key]
                p.need(isinstance(s,dict) and set(s)=={'wallUs','monoBeforeUs','monoAfterUs'} and all(p.integer(v) for v in s.values()) and s['monoBeforeUs']<=s['monoAfterUs'],'M7_EVALUATOR_IDLE_CLOCK')
                low=s['wallUs']-s['monoAfterUs']-1;high=s['wallUs']-s['monoBeforeUs']+1
                lower=low if lower is None else max(lower,low);upper=high if upper is None else min(upper,high)
            a,b=window['start'],window['end']
            p.need(a['monoAfterUs']<=b['monoBeforeUs'] and a['wallUs']<=b['wallUs'],'M7_EVALUATOR_IDLE_CLOCK')
            seen=window['observedAt']
            p.need(isinstance(seen,list) and bool(seen) and all(p.integer(v) and a['wallUs']<=v*1000+999 and v*1000<=b['wallUs'] for v in seen),'M7_EVALUATOR_IDLE_CLOCK')
            starts.append(a['monoBeforeUs']);ends.append(b['monoAfterUs'])
        p.need(previous_end is None or previous_end<=min(starts),'M7_EVALUATOR_IDLE_CLOCK')
        previous_end=max(ends)
    p.need(lower is not None and lower<=upper,'M7_EVALUATOR_IDLE_CLOCK')
    return {'offsetLowerUs':lower,'offsetUpperUs':upper}

def round_view(services,ids,fetch):
    captured={};windows={};started=time.monotonic()
    def measured(service,*args):
        a=stamp();raw=fetch(service,*args);b=stamp()
        raw=raw.encode() if isinstance(raw,str) else raw;captured[service]=raw
        windows[service]={'start':a,'end':b,'observedAt':[]};return raw
    value=p.round_view(services,ids,measured)
    for service,raw in captured.items():
        for line in raw.splitlines():
            page=json.loads(line);windows[service]['observedAt'].append(page.get('observedAt'))
            for row in page['view']['tenants']:
                value['allRows'][service][row['tenant']]['jobs']=copy.deepcopy(jobs(row.get('jobs')))
    value['readWindows']=windows;value['wallSeconds']=time.monotonic()-started
    clock_windows([value]);return value

def stability(rounds,ids):
    p.need(len(rounds)==3,'M7_EVALUATOR_PROGRESS_ROUNDS')
    p.need(sum(r['queries'] for r in rounds)<=p.POLICY['maxQueriesPerPhase'] and sum(r['bytes'] for r in rounds)<=p.POLICY['maxBytesPerPhase'],'M7_EVALUATOR_PROGRESS_BUDGET')
    first=rounds[0];previous=first
    for current in rounds:
        p.need(current['instances']==first['instances'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
        p.need(set(current['owners'])==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
        for service,rows in previous['allRows'].items():
            p.need(set(current['allRows'].get(service,{}))==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
            for tenant,a in rows.items():
                b=current['allRows'][service][tenant];jobs(b.get('jobs'));p.due_fields(b)
                p.need((a['admitted'],a['generation'])==(b['admitted'],b['generation']),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
                if not a['admitted']:
                    p.need(not any(jobs(b['jobs']).values()),'M7_EVALUATOR_IDLE_FOREIGN_PENDING')
                    p.need(not b['ready'] and all(a[k]==b[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
        for tenant in ids:
            a=previous['owners'][tenant];b=current['owners'][tenant]
            p.need((a['service'],a['runtimeId'],a['generation'])==(b['service'],b['runtimeId'],b['generation']),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            p.need(b['ready'] and b['code'] is None and b['alert'] is None and b['completedAcquisitions']>0,'M7_EVALUATOR_PROGRESS_ERROR','FAIL')
            p.need(b['failedCompletions']==0,'M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE','FAIL')
            p.need(b['completedTimeCycles']>=a['completedTimeCycles'] and b['legacyCycles']>=a['legacyCycles'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            p.need(b['completedAcquisitions']>=a['completedAcquisitions'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            p.need(b['completedAcquisitions']==first['owners'][tenant]['completedAcquisitions'],'M7_EVALUATOR_IDLE_NEW_DEMAND')
        previous=current

def final_obligations(rounds,ids):
    """Validate the original global window before selecting any point tail."""
    stability(rounds,ids);clock_windows(rounds)
    end=max(v['end']['wallUs'] for v in rounds[-1]['readWindows'].values())/1000
    pending=[]
    for tenant in ids:
        rows=[r['owners'][tenant] for r in rounds];first,last=rows[0],rows[-1]
        p.need(all(not any(jobs(row['jobs']).values()) for row in rows[:2]),'M7_EVALUATOR_IDLE_JOB_PENDING')
        opportunities=[i for i,row in enumerate(rows) if row['dueAt'] is not None and row['dueAt']<=end]
        delta=last['completedTimeCycles']-first['completedTimeCycles']
        if any(jobs(last['jobs']).values()):
            p.need(last['jobs']=={flag:flag=='running' for flag in FLAGS},'M7_EVALUATOR_IDLE_JOB_PENDING')
            p.need(bool(opportunities) and all(i<2 for i in opportunities),'M7_EVALUATOR_IDLE_TAIL_OPPORTUNITY')
            # Exactly one body has not yet received release credit. No new body
            # may run between this final observation and its tail credit.
            p.need(last['legacyCycles']-first['legacyCycles']==delta+1,'M7_EVALUATOR_IDLE_TAIL_BODY')
            pending.append(tenant)
        elif opportunities:
            for i in opportunities:
                p.need(i<2 and last['completedTimeCycles']>rows[i]['completedTimeCycles'],'M7_EVALUATOR_IDLE_TIME_NOT_OBSERVED')
        else:
            p.need(delta==0,'M7_EVALUATOR_IDLE_UNATTRIBUTED_TIME')
            p.need(last['legacyCycles']==first['legacyCycles'],'M7_EVALUATOR_IDLE_UNCREDITED_WORK')
    p.need(len(pending)<=TAIL_POLICY['maxOwners'],'M7_EVALUATOR_IDLE_TAIL_OWNER_BOUND')
    return sorted(pending)

def validate_tail(rounds,ids,tail,pending):
    p.need(isinstance(tail,dict) and set(tail)=={'selected','round','elapsedSeconds'},'M7_EVALUATOR_IDLE_TAIL_REQUIRED')
    p.need(tail['selected']==pending and 1<=len(pending)<=TAIL_POLICY['maxOwners'],'M7_EVALUATOR_IDLE_TAIL_COVERAGE')
    elapsed=tail['elapsedSeconds']
    p.need(type(elapsed) in (int,float) and math.isfinite(elapsed) and 0<=elapsed<=TAIL_POLICY['deadlineMs']/1000,'M7_EVALUATOR_IDLE_TAIL_DEADLINE')
    point=tail['round'];last=rounds[-1]
    p.need(point['instances']==last['instances'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
    p.need(set(point['owners'])==set(pending) and set(point['allRows'])==set(last['allRows']),'M7_EVALUATOR_IDLE_TAIL_COVERAGE','FAIL')
    p.need(point['queries']==len(point['instances']),'M7_EVALUATOR_IDLE_TAIL_QUERY_BOUND')
    p.need(sum(r['queries']for r in rounds)+point['queries']<=p.POLICY['maxQueriesPerPhase'] and sum(r['bytes']for r in rounds)+point['bytes']<=p.POLICY['maxBytesPerPhase'],'M7_EVALUATOR_PROGRESS_BUDGET')
    clock_windows(rounds+[point])
    windows=point['readWindows'].values()
    span=(max(v['end']['monoAfterUs']for v in windows)-min(v['start']['monoBeforeUs']for v in point['readWindows'].values()))/1e6
    p.need(span<=elapsed and point['wallSeconds']<=elapsed,'M7_EVALUATOR_IDLE_TAIL_DEADLINE')
    for service,selected in point['allRows'].items():
        p.need(set(selected)==set(pending),'M7_EVALUATOR_IDLE_TAIL_COVERAGE','FAIL')
        for tenant,b in selected.items():
            a=last['allRows'][service][tenant];jobs(b.get('jobs'));p.due_fields(b)
            p.need((a['admitted'],a['generation'],a['runtimeId'])==(b['admitted'],b['generation'],b['runtimeId']),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            p.need(not any(b['jobs'].values()),'M7_EVALUATOR_IDLE_TAIL_JOB_PENDING')
            if not a['admitted']:
                p.need(not b['ready'] and all(a[k]==b[k] for k in ('completedAcquisitions','completedTimeCycles','failedCompletions','legacyCycles')),'M7_EVALUATOR_PROGRESS_FOREIGN','FAIL')
            else:
                p.need(b['ready'] and b['code'] is None and b['alert'] is None and b['failedCompletions']==a['failedCompletions']==0,'M7_EVALUATOR_PROGRESS_ERROR','FAIL')
                p.need(b['service']==a['service'] and b['completedAcquisitions']==a['completedAcquisitions'],'M7_EVALUATOR_IDLE_NEW_DEMAND')
                p.need(b['completedTimeCycles']==a['completedTimeCycles']+1 and b['legacyCycles']==a['legacyCycles'],'M7_EVALUATOR_IDLE_TAIL_COMPLETION')
    return point

def assess(rounds,ids,phase='idle',*,tail=None):
    p.need(phase=='idle','M7_EVALUATOR_IDLE_PHASE')
    pending=final_obligations(rounds,ids);clock=clock_windows(rounds)
    if pending:point=validate_tail(rounds,ids,tail,pending)
    else:p.need(tail is None,'M7_EVALUATOR_IDLE_TAIL_UNEXPECTED');point=None
    outcomes={};completed=0
    end=max(v['end']['wallUs']for v in rounds[-1]['readWindows'].values())/1000
    for tenant in ids:
        first,last=rounds[0]['owners'][tenant],rounds[-1]['owners'][tenant]
        delta=last['completedTimeCycles']-first['completedTimeCycles'];completed+=delta
        if tenant in pending:outcomes[tenant]={'classification':'TIME_COMPLETED_AFTER_WINDOW'}
        elif any(r['owners'][tenant]['dueAt'] is not None and r['owners'][tenant]['dueAt']<=end for r in rounds):outcomes[tenant]={'classification':'TIME_EXERCISED'}
        else:outcomes[tenant]={'classification':'TIME_NOT_EXERCISED','scheduledState':'NO_TIMER_DECLARED'if last['dueAt']is None else'FUTURE_DUE'}
    return {'version':2,'phase':'idle','verdict':'PASS','policy':POLICY,'scope':'sampled idle safety; selected post-window completion is not measured throughput or global tail quiescence',
            'tenants':len(ids),'instances':rounds[0]['instances'],'classifications':{key:sum(row.get('classification')==key or row.get('scheduledState')==key for row in outcomes.values()) for key in ('TIME_EXERCISED','TIME_COMPLETED_AFTER_WINDOW','TIME_NOT_EXERCISED','NO_TIMER_DECLARED','FUTURE_DUE')},
            'completedTimeDelta':completed,'timeWitness':False,'clockGuard':clock,'queries':sum(r['queries']for r in rounds),'responseBytes':sum(r['bytes']for r in rounds),'collectorWallSeconds':sum(r['wallSeconds']for r in rounds),
            'completionTail':None if point is None else {'selected':pending,'completedTimeDelta':len(pending),'queries':point['queries'],'responseBytes':point['bytes'],'collectorWallSeconds':point['wallSeconds'],'elapsedSeconds':tail['elapsedSeconds'],'clockGuard':clock_windows(rounds+[point]),'costScope':'outside original metric window; selected owners only; no global tail quiescence'}}

def _pack_round(raw):
    return {**{k:v for k,v in raw.items()if k not in ('owners','allRows')},'rows':[[tenant]+[(sum((1<<i)for i,flag in enumerate(FLAGS)if row['jobs'][flag])if key=='jobs'else row[key])for key in COLUMNS[1:]]for service,values in sorted(raw['allRows'].items())for tenant,row in sorted(values.items())]}

def pack(value):
    result={**value,'kind':ARTIFACT_KIND,'columns':list(COLUMNS),'rounds':[_pack_round(r)for r in value.get('rounds',[])]}
    if value.get('tailRound')is not None:result['tailRound']={**value['tailRound'],'round':_pack_round(value['tailRound']['round'])}
    return result

def _decode(value,tenants,services):
    p.need(isinstance(value,dict) and isinstance(value.get('rounds'),list) and all(isinstance(r,dict) and isinstance(r.get('rows'),list) and all(isinstance(row,list) and len(row)==len(COLUMNS)for row in r['rows'])for r in value['rounds']),'M7_EVALUATOR_IDLE_TAIL_COVERAGE')
    base=copy.deepcopy(value);base['kind']='evaluator-progress-phase-v2';base['columns']=list(p.COLUMNS)
    for raw in base['rounds']:raw['rows']=[row[:-1]for row in raw['rows']]
    rounds,ids=p.decode_rounds(base,tenants,services)
    for source,current in zip(value['rounds'],rounds):
        for row in source['rows']:
            flags=row[-1];p.need(type(flags)is int and 0<=flags<1<<len(FLAGS),'M7_EVALUATOR_IDLE_JOBS')
            current['allRows'][row[1]][row[0]]['jobs']={flag:bool(flags&(1<<i))for i,flag in enumerate(FLAGS)}
    return rounds,ids

def verify(value,tenants,services,phase='idle'):
    p.need(isinstance(value,dict) and value.get('kind')==ARTIFACT_KIND and value.get('columns')==list(COLUMNS) and value.get('policy')==POLICY and value.get('verdict')=='PASS','M7_EVALUATOR_IDLE_VERSION')
    rounds,ids=_decode(value,tenants,services);tail=value.get('tailRound')
    if tail is not None:
        p.need(isinstance(tail,dict) and set(tail)=={'selected','round','elapsedSeconds'} and isinstance(tail['selected'],list) and 1<=len(tail['selected'])<=TAIL_POLICY['maxOwners'],'M7_EVALUATOR_IDLE_TAIL_COVERAGE')
        points,selected=_decode({'rounds':[tail['round']]},len(tail['selected']),services)
        p.need(set(tail['selected'])==selected,'M7_EVALUATOR_IDLE_TAIL_COVERAGE');tail={**tail,'round':points[0]}
    result=assess(rounds,sorted(ids),phase,tail=tail)
    p.need({k:v for k,v in value.items()if k not in ('kind','columns','rounds','attribution','tailRound')}==result,'M7_EVALUATOR_IDLE_ASSESSMENT')
    return result

class Observer(p.Observer):
    def __init__(self,*args,tail_fetch=None):
        super().__init__(*args,assessor=assess,policy=POLICY);self.tail_fetch=tail_fetch;self.pending=[];self.tail=None
    def observe(self):
        try:self.rounds.append(round_view(self.services,self.ids,self.fetch))
        except Exception as error:self.failure=error
    def finish(self):
        try:
            if self.failure:raise self.failure
            self.pending=final_obligations(self.rounds,self.ids)
        except Exception as error:self.failed(error);raise
        if self.pending:
            # Persist a nonterminal original-window observation; no tail may run
            # until the adapter has captured AFTER metric bookends successfully.
            self.failed(p.Refused('M7_EVALUATOR_IDLE_FINAL_COMPLETION_PENDING'))
        else:super().finish()
    def complete_after_cost_window(self):
        if not self.pending:return
        started=time.monotonic();deadline=started+TAIL_POLICY['deadlineMs']/1000
        services=self.services;queries=sum(r['queries']for r in self.rounds);used=sum(r['bytes']for r in self.rounds)
        try:
            p.need(self.tail_fetch is not None and queries+len(services)<=p.POLICY['maxQueriesPerPhase'],'M7_EVALUATOR_PROGRESS_BUDGET')
            budget=min(p.POLICY['responseMaxBytes']+8192,(p.POLICY['maxBytesPerPhase']-used)//len(services));p.need(budget>0,'M7_EVALUATOR_PROGRESS_BUDGET')
            def fetch(service,selected,unused_queries,unused_budget):
                remaining=deadline-time.monotonic();p.need(remaining>0,'M7_EVALUATOR_IDLE_TAIL_DEADLINE')
                return self.tail_fetch(service,selected,1,budget,min(remaining,p.POLICY['rpcTimeoutMs']/1000))
            point=round_view(services,self.pending,fetch);elapsed=time.monotonic()-started
            self.tail={'selected':self.pending,'round':point,'elapsedSeconds':elapsed}
            result=assess(self.rounds,self.ids,self.phase,tail=self.tail)
            p.need(time.monotonic()<=deadline,'M7_EVALUATOR_IDLE_TAIL_DEADLINE')
        except Exception as error:
            self.failed(error,{'tailRound':self.tail,'tailAttempted':True,'tailElapsedSeconds':time.monotonic()-started,'tailCollection':getattr(error,'collection',None)});raise
        self.write({**result,'rounds':self.rounds,'tailRound':self.tail});self.result=result
