"""Source-bound accepted-input and durable due-completion assessment.

Durable snapshots come from completed-oracle.progressSnapshot over the existing
trusted SQL query, not public-driver SQL or a completed inspection checkpoint.
Collect one snapshot before each of the three existing progress rounds. Retain
the exact reader/source binding and original rows/commands in private evidence.
The adapter selects this observer through its explicit idle/load contract flag.
"""
import evaluator_progress as p
import evaluator_idle as idle
import time
import math
import re

SOURCES=('clock','settings','policy','activity','lifecycle','bootstrap')
CONTRACT='received-input-v1'
ROUND_SECONDS=20
ROUND_BYTES=16777216


def revision(value):
    p.need(isinstance(value,str) and value.isascii() and value.isdecimal() and
           (value=='0' or not value.startswith('0')) and len(value)<=19 and
           int(value)<=9223372036854775807,'M7_OPPORTUNITY_REVISION')
    return int(value)


def durable_rows(captures,ids,binding):
    p.need(isinstance(captures,list) and len(captures)==3 and isinstance(binding,dict),'M7_OPPORTUNITY_CAPTURE')
    decoded=[]
    for capture in captures:
        p.need(isinstance(capture,dict) and set(capture)=={'kind','reader','rows'} and capture['kind']=='evaluator-durable-progress-v1','M7_OPPORTUNITY_CAPTURE')
        p.need(capture['reader']==binding,'M7_OPPORTUNITY_BINDING','FAIL')
        rows=capture['rows']
        p.need(isinstance(rows,list) and len(rows)==len(ids) and {r.get('tenant') for r in rows}==set(ids),'M7_OPPORTUNITY_COVERAGE')
        by_tenant={}
        for row in rows:
            p.need(set(row)-{'dueAt','completedAt'}=={'tenant','writerClock','observed','completed','outputRevision','restoreGeneration'},'M7_OPPORTUNITY_CAPTURE')
            for key in ('dueAt','completedAt'):
                if key in row:p.need(row[key] is None or p.integer(row[key]),'M7_OPPORTUNITY_TIME')
            revision(row['writerClock']);revision(row['outputRevision'])
            p.need(row['outputRevision']!='0' or row['completed']=={} and row['restoreGeneration'] is None,'M7_OPPORTUNITY_REVISION')
            if row['restoreGeneration'] is not None:p.need(revision(row['restoreGeneration'])>0,'M7_OPPORTUNITY_REVISION')
            for key in ('observed','completed'):
                p.need(isinstance(row[key],dict) and set(row[key])<=set(SOURCES),'M7_OPPORTUNITY_VECTOR')
                for value in row[key].values():revision(value)
            p.need(all(k in row['observed'] and revision(v)<=revision(row['observed'][k]) for k,v in row['completed'].items()),'M7_OPPORTUNITY_VECTOR')
            p.need('clock' not in row['observed'] or revision(row['observed']['clock'])<=revision(row['writerClock']),'M7_OPPORTUNITY_CLOCK')
            by_tenant[row['tenant']]=row
        decoded.append(by_tenant)
    for previous,current in zip(decoded,decoded[1:]):
        for tenant in ids:
            a,b=previous[tenant],current[tenant]
            p.need(a['restoreGeneration']==b['restoreGeneration'] or a['outputRevision']=='0' and a['restoreGeneration'] is None and revision(b['outputRevision'])>0,'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            p.need(revision(b['writerClock'])>=revision(a['writerClock']) and revision(b['outputRevision'])>=revision(a['outputRevision']),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            if a.get('completedAt') is not None and 'completedAt' in b:p.need(b['completedAt'] is not None and b['completedAt']>=a['completedAt'],'M7_EVALUATOR_PROGRESS_RESET','FAIL')
            for field in ('observed','completed'):
                p.need(all(k in b[field] and revision(b[field][k])>=revision(v) for k,v in a[field].items()),'M7_EVALUATOR_PROGRESS_RESET','FAIL')
    return decoded


def all_roster(rounds,ids,phase):
    # Re-decode to enforce every row's readiness/admission/health independently of
    # eligibility. Then run process/counter/foreign/reset/hidden-error checks.
    p.need(bool(rounds),'M7_EVALUATOR_PROGRESS_ROUNDS')
    decoded,actual_ids=p.decode_rounds(p.pack({'rounds':rounds}),len(ids),list(rounds[0]['instances']))
    p.need(actual_ids==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    for raw,current in zip(rounds,decoded):
        for tenant,owner in raw['owners'].items():
            normalized=current['owners'][tenant]
            p.need(all(owner.get(k)==v for k,v in normalized.items()),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    p.need(set(rounds[0]['owners'])==set(ids),'M7_EVALUATOR_PROGRESS_COVERAGE','FAIL')
    try:p.assess(rounds,ids,phase)
    except p.Refused as error:
        if str(error)!='M7_EVALUATOR_PROGRESS_NOT_OBSERVED':raise


def timer_outcome(rounds,tenant,captures=None):
    """A due checkpoint is discharged by a later atomic clinical completion.

    Cache generation, callback kind and output content revision are irrelevant.
    A subsequent deadline remains owed; it need not disappear altogether.
    """
    try:
        idle.clock_windows(rounds)
        end=max(v['end']['wallUs'] for v in rounds[-1]['readWindows'].values())/1000
        inspected=[r['owners'][tenant] for r in rounds]
        if captures is None or any(not {'dueAt','completedAt'}<=set(c[tenant]) for c in captures):
            return 'UNMEASURED' if any(r['dueAt'] is not None and r['dueAt']<=end for r in inspected) else 'NO_SAMPLED_TIMER_OPPORTUNITY'
        rows=[c[tenant] for c in captures];last=rows[-1]
        opportunities=[r for r in rows[:2] if r['dueAt'] is not None and r['dueAt']<=end]
        if not opportunities:
            return 'UNMEASURED' if last['dueAt'] is not None and last['dueAt']<=end else 'NO_SAMPLED_TIMER_OPPORTUNITY'
        return 'COMPLETED' if revision(last['outputRevision'])>0 and all(last['completedAt'] is not None and last['completedAt']>=r['dueAt'] and
            (r['completedAt'] is None or last['completedAt']>r['completedAt']) and
            (last['dueAt'] is None or last['dueAt']>r['dueAt']) for r in opportunities) else 'PENDING'
    except (p.Refused,KeyError):return 'UNMEASURED'


def assess(rounds,ids,phase,*,durable=None,binding=None):
    p.validate_ids(ids);all_roster(rounds,ids,phase)
    captures=durable_rows(durable,ids,binding) if durable is not None else None
    outcomes={};source_tenants={key:set() for key in SOURCES}
    observed=0;total_work=0;total_time=0
    for tenant in ids:
        a,b=rounds[0]['owners'][tenant],rounds[-1]['owners'][tenant]
        work=b['completedAcquisitions']-a['completedAcquisitions']+b['completedTimeCycles']-a['completedTimeCycles']
        time=b['completedTimeCycles']-a['completedTimeCycles'];observed+=work>0;total_work+=work;total_time+=time
        input_status='UNMEASURED';targets={};no_clock_advance=False
        if captures:
            first,last=captures[0][tenant],captures[-1][tenant]
            no_clock_advance=last['writerClock']==first['writerClock']
            for key,value in last['observed'].items():
                prior=first['observed'].get(key)
                if prior is None or revision(value)>revision(prior) or key not in first['completed'] or revision(first['completed'][key])<revision(prior):targets[key]=value
            if not no_clock_advance or 'clock' not in first['completed'] or revision(first['completed']['clock'])<revision(first['writerClock']):targets['clock']=last['writerClock']
            for key in targets:source_tenants[key].add(tenant)
            input_status=('COMPLETED' if all(key in last['completed'] and revision(last['completed'][key])>=revision(value) for key,value in targets.items()) else 'PENDING') if targets else 'NO_KNOWN_INPUT_OPPORTUNITY'
        timer=timer_outcome(rounds,tenant,captures)
        known=input_status in ('COMPLETED','PENDING') or timer in ('COMPLETED','PENDING')
        pending=input_status=='PENDING' or timer=='PENDING'
        no_known=input_status=='NO_KNOWN_INPUT_OPPORTUNITY' and timer=='NO_SAMPLED_TIMER_OPPORTUNITY'
        classification='KNOWN_PENDING' if pending else 'KNOWN_COMPLETED' if known else 'NO_KNOWN_OPPORTUNITY' if no_known else 'UNMEASURED'
        outcomes[tenant]={'classification':classification,'receivedInput':input_status,'inputTargets':targets,'timer':timer,
                          'completedWorkDelta':work,'completedTimeDelta':time,
                          'noOrdinaryClockAdvanceProven':no_clock_advance if captures else None}
    counts={key:sum(v['classification']==key for v in outcomes.values()) for key in ('KNOWN_COMPLETED','KNOWN_PENDING','NO_KNOWN_OPPORTUNITY','UNMEASURED')}
    eligible=counts['KNOWN_COMPLETED']+counts['KNOWN_PENDING']
    return {'kind':'evaluator-opportunity-assessment-v1','assessmentVersion':2,'phase':phase,
            'verdict':'PASS' if eligible and not counts['KNOWN_PENDING'] and not counts['UNMEASURED'] else 'UNMEASURED',
            'allRosterHealth':'PASS','tenants':len(ids),'eligibleTenants':eligible,'classifications':counts,'byTenant':outcomes,
            'inputSourceTenantCoverage':{k:len(v) for k,v in source_tenants.items()},
            'revisionCoverage':'exact final target revision per tenant/source in byTenant; intermediate revisions not continuously observed',
            'ordinaryWriteKindCoverage':'UNMEASURED; writer clock does not identify entries/treatments/devicestatus',
            'tenantsWithObservedWork':observed,'completedWorkDelta':total_work,'completedTimeDelta':total_time,
            'scope':'known received-input/due opportunities only; no-known is not proof of no input across every source; no per-write completion or clinical-equivalence claim',
            'workWindowSeconds':None,'workRate':'UNMEASURED; bookends may include setup; collectorWallSeconds is observer cost',
            'inspectionCollectorWallSeconds':sum(r['wallSeconds'] for r in rounds),
            'durableCollectorCost':'UNMEASURED; collection caller must retain SQL query/byte/time cost separately'}


def capture_windows(windows,count):
    p.need(isinstance(windows,list) and len(windows)==count,'M7_OPPORTUNITY_CAPTURE_WINDOWS')
    previous=None
    for row in windows:
        p.need(set(row)=={'startNs','durableEndNs','inspectionEndNs'} and all(type(v) is int and 0<=v<=9223372036854775807 for v in row.values()),'M7_OPPORTUNITY_CAPTURE_WINDOWS')
        p.need((previous is None or previous<=row['startNs']) and row['startNs']<=row['durableEndNs']<=row['inspectionEndNs'],'M7_OPPORTUNITY_CAPTURE_ORDER')
        previous=row['inspectionEndNs']


def collection_cost(value,windows,tenants):
    p.need(isinstance(value,dict) and set(value)=={'preparation','rounds','scope'},'M7_OPPORTUNITY_COST')
    prep=value['preparation'];costs=value['rounds']
    p.need(isinstance(prep,dict) and prep.get('nodeCalls')==1 and prep.get('sqlQueries')==0,'M7_OPPORTUNITY_COST')
    p.need(isinstance(costs,list) and len(costs)==3,'M7_OPPORTUNITY_COST')
    for row in [prep,*costs]:
        p.need(all(type(row.get(k)) in (int,float) and math.isfinite(row[k]) and row[k]>=0 for k in ('wallSeconds','observerProcessCpuSeconds')),'M7_OPPORTUNITY_COST')
    for cost,window in zip(costs,windows):
        p.need(cost.get('sqlQueries')==(tenants+63)//64 and cost.get('nodeCalls')==1,'M7_OPPORTUNITY_QUERY_BOUND')
        p.need(p.integer(cost.get('rawSqlBytes'),1) and cost['rawSqlBytes']<=ROUND_BYTES,'M7_OPPORTUNITY_BYTE_BOUND')
        p.need(cost['wallSeconds']<=(window['durableEndNs']-window['startNs'])/1e9 and cost['wallSeconds']<=ROUND_SECONDS+.1,'M7_OPPORTUNITY_COST')


class Observer(p.Observer):
    """Explicit idle/load caller. Three SQL-before-inspection captures, one clock."""
    def __init__(self,*args,durable_fetch,binding,preparation_cost,source_sha256,query_sha256):
        super().__init__(*args)
        p.need(self.phase in ('idle','load'),'M7_OPPORTUNITY_PHASE')
        self.durable_fetch,self.binding=durable_fetch,binding
        self.preparation_cost=preparation_cost;self.durable=[];self.windows=[];self.costs=[]
        self.source_sha256,self.query_sha256=source_sha256,query_sha256

    def observe(self):
        try:
            start=time.monotonic_ns();snapshot,cost=self.durable_fetch();end=time.monotonic_ns()
            self.durable.append(snapshot);self.costs.append(cost)
            row=idle.round_view(self.services,self.ids,self.fetch)
            self.rounds.append(row);self.windows.append({'startNs':start,'durableEndNs':end,'inspectionEndNs':time.monotonic_ns()})
        except Exception as error:
            self.failure=error
            if hasattr(error,'opportunityCost'):self.costs.append(error.opportunityCost)

    def payload(self,value):
        return {**value,'opportunityContract':CONTRACT,'durableBinding':self.binding,'durable':self.durable,'rounds':self.rounds,
                'durableSourceSha256':self.source_sha256,'durableQuerySha256':self.query_sha256,
                'captureWindows':self.windows,'durableCollectorCost':{'preparation':self.preparation_cost,'rounds':self.costs,
                    'scope':'observer and SQL command elapsed time; observer CPU excludes Node/PG child CPU; included in measured system workload'}}

    def failed(self,error,extra=None):
        code=str(error)
        if not code.startswith('M7_') or not all(c.isalnum() or c in '_:' for c in code):code='M7_OPPORTUNITY_COLLECTION_REFUSED'
        self.write(self.payload({'verdict':getattr(error,'verdict','UNMEASURED'),'phase':self.phase,'code':code,'failedCollection':getattr(error,'collection',None),**(extra or {})}))

    def finish(self):
        try:
            if self.failure:raise self.failure
            capture_windows(self.windows,3)
            p.need(sum(c['sqlQueries'] for c in self.costs)==3*((len(self.ids)+63)//64),'M7_OPPORTUNITY_QUERY_BOUND')
            p.need(sum(c['rawSqlBytes'] for c in self.costs)<=3*ROUND_BYTES,'M7_OPPORTUNITY_BYTE_BOUND')
            result=assess(self.rounds,self.ids,self.phase,durable=self.durable,binding=self.binding)
            collection_cost(self.payload(result)['durableCollectorCost'],self.windows,len(self.ids))
        except Exception as error:self.failed(error);raise
        self.result=self.payload(result);self.write(self.result)
        if result['verdict']!='PASS':raise p.Refused('M7_OPPORTUNITY_NOT_OBSERVED')

    def __exit__(self,kind,value,traceback):
        self.stop.set();self.thread.join(timeout=ROUND_SECONDS+25)
        if kind:
            try:self.failed(p.Refused('M7_EVALUATOR_PROGRESS_BODY_FAILED','FAIL'),{'interruptedBody':True,'bodyFailureType':type(value).__name__,'collectorStillRunning':self.thread.is_alive()})
            except Exception:self.publicationFailed=True
            return False
        if self.thread.is_alive():
            error=p.Refused('M7_EVALUATOR_PROGRESS_COLLECTOR_TIMEOUT');self.failed(error);raise error
        if self.failure:self.failed(self.failure);raise self.failure
        self.observe();self.finish()


def pack(value):
    return {**value,'kind':'evaluator-opportunity-phase-v1','columns':list(idle.COLUMNS),
            'rounds':[idle._pack_round(r) for r in value.get('rounds',[])]}


def verify(value,tenants,services,binding,*,source_sha256=None,query_sha256=None):
    p.need(value.get('kind')=='evaluator-opportunity-phase-v1' and value.get('opportunityContract')==CONTRACT and value.get('columns')==list(idle.COLUMNS),'M7_OPPORTUNITY_ARTIFACT')
    p.need(value.get('durableBinding')==binding,'M7_OPPORTUNITY_BINDING','FAIL')
    for key,expected in [('durableSourceSha256',source_sha256),('durableQuerySha256',query_sha256)]:
        p.need(isinstance(value.get(key),str) and re.fullmatch('[a-f0-9]{64}',value[key]) and (expected is None or value[key]==expected),'M7_OPPORTUNITY_BINDING','FAIL')
    rounds,ids=idle._decode(value,tenants,services);capture_windows(value.get('captureWindows'),3)
    collection_cost(value.get('durableCollectorCost'),value['captureWindows'],tenants)
    result=assess(rounds,sorted(ids),value.get('phase'),durable=value.get('durable'),binding=binding)
    p.need(all(value.get(k)==v for k,v in result.items() if k not in ('kind','durableCollectorCost')),'M7_OPPORTUNITY_ASSESSMENT')
    return result
