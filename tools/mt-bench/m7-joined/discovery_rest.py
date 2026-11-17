"""One explicit clinical stall may coexist with independently measured REST.

All roster, durable source/restore, clock, counter and collection fences still run.
This path can only publish clinical FAIL and capacity NOT_GRANTED.
"""
import evaluator_progress as p
import evaluator_idle as idle
import evaluator_opportunities as opportunities

CODE='EVALUATOR_CLINICAL_PROGRESS_STALLED'

def selected(m):return m.get('runPurpose')=='discovery' and m.get('profile')=='pgstream-sample' and m.get('evaluatorOpportunities')=='received-input-v1'

def result(value):return isinstance(value,dict) and value.get('verdict')=='FAIL' and value.get('clinicalVerdict')=='FAIL' and value.get('clinicalCode')==CODE and value.get('restCollectionPermitted') is True

def binding(m):return {**{key:m.get(key) for key in ('owner','pair','imageId')},'instrument':m.get('instrument',{}).get('sha256')}

def permitted(a,d,m):
    if not selected(m) or not (d/'runtime-readiness.json').is_file():return False
    value=a.document(d/'runtime-readiness.json')
    p.need(not result(value) or value.get('sourceBinding')==binding(m),'M7_OPPORTUNITY_BINDING','FAIL')
    return result(value)

def assess_rest(rounds,ids,phase,durable,binding):
    opportunities.all_roster(rounds,ids,phase,allow_clinical_stall=True)
    idle.clock_windows(rounds)
    for current in rounds:
        for rows in current['allRows'].values():
            for row in rows.values():
                if not row['admitted']:p.need(not any(idle.jobs(row['jobs']).values()),'M7_EVALUATOR_IDLE_FOREIGN_PENDING','FAIL')
    opportunities.durable_rows(durable,ids,binding)
    return {'version':p.POLICY['version'],'phase':phase,'policy':p.POLICY,'verdict':'FAIL','code':'M7_EVALUATOR_PROGRESS_ERROR','clinicalVerdict':'FAIL','clinicalCode':CODE,'restCollectionPermitted':True,'capacityAcceptance':'NOT_GRANTED','scope':'independent REST observations alongside an explicit clinical stall; no clinical or capacity acceptance'}
