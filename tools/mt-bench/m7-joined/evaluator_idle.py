"""Idle safety is absence of observed evaluator demand, never a work witness."""
import copy
import json
import time
import evaluator_progress as p

FLAGS=('running','booting','acquire','time','parentAcquire','parentTime')
POLICY={'version':1,'kind':'evaluator-idle-safety','moduleVersion':2,
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

def assess(rounds,ids,phase='idle'):
    p.need(phase=='idle','M7_EVALUATOR_IDLE_PHASE');stability(rounds,ids);clock=clock_windows(rounds)
    final_end=max(v['end']['wallUs'] for v in rounds[-1]['readWindows'].values())/1000
    final_start=min(v['start']['wallUs'] for v in rounds[-1]['readWindows'].values())/1000
    outcomes={};completed=0
    for tenant in ids:
        first=rounds[0]['owners'][tenant];last=rounds[-1]['owners'][tenant]
        delta=last['completedTimeCycles']-first['completedTimeCycles'];completed+=delta
        rows=[r['owners'][tenant] for r in rounds]
        p.need(all(not any(jobs(row['jobs']).values()) for row in rows),'M7_EVALUATOR_IDLE_JOB_PENDING')
        opportunities=[i for i,row in enumerate(rows) if row['dueAt'] is not None and row['dueAt']<=final_end]
        if opportunities:
            # A later future due cannot erase an earlier observed opportunity.
            for i in opportunities:
                p.need(i<2 and rows[i]['dueAt']<=final_start and last['completedTimeCycles']>rows[i]['completedTimeCycles'],'M7_EVALUATOR_IDLE_TIME_NOT_OBSERVED')
            outcomes[tenant]={'classification':'TIME_EXERCISED','completedTimeDelta':delta}
        else:
            p.need(delta==0,'M7_EVALUATOR_IDLE_UNATTRIBUTED_TIME')
            p.need(last['legacyCycles']==first['legacyCycles'],'M7_EVALUATOR_IDLE_UNCREDITED_WORK')
            outcomes[tenant]={'classification':'TIME_NOT_EXERCISED','completedTimeDelta':0,'meaning':'NO_EVALUATOR_TIME_DEMAND','scheduledState':'NO_TIMER_DECLARED' if last['dueAt'] is None else 'FUTURE_DUE'}
    return {'version':1,'phase':'idle','verdict':'PASS','policy':POLICY,'scope':'sampled evaluator idle safety; not a work witness or active-alarm capacity',
            'tenants':len(ids),'instances':rounds[0]['instances'],'classifications':{key:sum(row.get('classification')==key or row.get('scheduledState')==key for row in outcomes.values()) for key in ('TIME_EXERCISED','TIME_NOT_EXERCISED','NO_TIMER_DECLARED','FUTURE_DUE')},'completedTimeDelta':completed,
            'timeWitness':False,'clockGuard':clock,'queries':sum(r['queries'] for r in rounds),'responseBytes':sum(r['bytes'] for r in rounds),
            'collectorWallSeconds':sum(r['wallSeconds'] for r in rounds)}

def pack(value):
    result={**value,'kind':'evaluator-idle-safety-v1','columns':list(COLUMNS),'rounds':[]}
    for raw in value.get('rounds',[]):
        result['rounds'].append({**{k:v for k,v in raw.items() if k not in ('owners','allRows')},'rows':[[tenant]+[(sum((1<<i) for i,flag in enumerate(FLAGS) if row['jobs'][flag]) if key=='jobs' else row[key]) for key in COLUMNS[1:]] for service,values in sorted(raw['allRows'].items()) for tenant,row in sorted(values.items())]})
    return result

def verify(value,tenants,services,phase='idle'):
    p.need(value.get('kind')=='evaluator-idle-safety-v1' and value.get('columns')==list(COLUMNS) and value.get('policy')==POLICY and value.get('verdict')=='PASS','M7_EVALUATOR_IDLE_VERSION')
    base=copy.deepcopy(value);base['kind']='evaluator-progress-phase-v2';base['columns']=list(p.COLUMNS)
    for raw in base['rounds']:raw['rows']=[row[:-1] for row in raw['rows']]
    rounds,ids=p.decode_rounds(base,tenants,services)
    for source,current in zip(value['rounds'],rounds):
        for row in source['rows']:
            flags=row[-1];p.need(type(flags) is int and 0<=flags<1<<len(FLAGS),'M7_EVALUATOR_IDLE_JOBS')
            current['allRows'][row[1]][row[0]]['jobs']={flag:bool(flags & (1<<i)) for i,flag in enumerate(FLAGS)}
    result=assess(rounds,sorted(ids),phase)
    p.need({k:v for k,v in value.items() if k not in ('kind','columns','rounds','attribution')}==result,'M7_EVALUATOR_IDLE_ASSESSMENT')
    return result

class Observer(p.Observer):
    def __init__(self,*args):
        super().__init__(*args,assessor=assess,policy=POLICY)
    def observe(self):
        try:self.rounds.append(round_view(self.services,self.ids,self.fetch))
        except Exception as error:self.failure=error
