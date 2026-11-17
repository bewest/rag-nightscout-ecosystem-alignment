"""Reduce retained k6 HTTP counters; no request payloads or inferred commit result."""
import math

SHAPES=('w_sgv','w_devicestatus','w_treatments_v3','r_sgv','r_devicestatus','r_treatments','r_status')
CATEGORIES=('http_expected','http_refused','http_unexpected','timeout','transport')


def assess(metrics):
    def count(key):
        value=metrics.get(key,{}).get('count',metrics.get(key,{}).get('values',{}).get('count',0))
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0 or int(value)!=value:
            raise ValueError('M7_HTTP_COUNT_INVALID')
        return int(value)
    def tagged(metric,shape,extra=''):
        return count(metric+'{http_shape:'+shape+extra+'}')
    result={'version':1,'kind':'m7-http-accounting','source':'k6-summary-counters','shapes':{},
            'storage':'UNMEASURED','clinical':'UNMEASURED','clientDelivery':'UNMEASURED',
            'limits':'HTTP status is observed; write commit and cause require an independent oracle. No mutation is retried.'}
    for shape in ('jwt_setup',*SHAPES):
        attempts=tagged('m7_http_attempts',shape)
        completed=tagged('m7_http_completed',shape)
        statuses={str(status):tagged('m7_http_completed',shape,',status:'+str(status)) for status in (0,*range(100,600))}
        categories={category:tagged('m7_http_completed',shape,',category:'+category) for category in CATEGORIES}
        outcomes={outcome:tagged('m7_http_write_outcome',shape,',outcome:'+outcome) for outcome in ('accepted','refused','uncertain')} if shape.startswith('w_') else None
        checks=[sum(statuses.values())==completed,sum(categories.values())==completed,completed<=attempts,
                statuses['0']==categories['timeout']+categories['transport'],
                sum(value for status,value in statuses.items() if 400<=int(status)<500)==categories['http_refused']]
        if outcomes is not None:checks.extend((sum(outcomes.values())==completed,outcomes['accepted']==categories['http_expected'],outcomes['refused']==categories['http_refused'],outcomes['uncertain']==categories['http_unexpected']+categories['timeout']+categories['transport']))
        reconciled=all(checks)
        result['shapes'][shape]={'attempts':attempts,'completed':completed,'pending':max(0,attempts-completed),
            'responses':completed-statuses['0'],'noResponse':statuses['0'],
            'statusCodes':{key:value for key,value in statuses.items() if value},'categories':categories,
            'writeOutcomes':outcomes,'reconciled':reconciled,
            'httpVerdict':'FAIL' if not reconciled or completed>categories['http_expected'] else 'UNMEASURED' if not attempts or attempts!=completed else 'PASS'}
    rows=list(result['shapes'].values());scenario=list(result['shapes'][shape] for shape in SHAPES)
    result['scenario']={'attempts':sum(row['attempts'] for row in scenario),'completed':sum(row['completed'] for row in scenario)}
    result['setup']=result['shapes']['jwt_setup']
    result['sourceCounts']={key:count(key) for key in ('scenario_request_attempts','scenario_http_responses','scenario_transport_failures','http_reqs','dropped_iterations')}
    # Native source counters are independently incremented by the existing code.
    # Missing source counters are not fabricated as proof of reconciliation.
    source=result['sourceCounts']
    result['sourceReconciliation']='UNMEASURED' if 'http_reqs' not in metrics or 'scenario_request_attempts' not in metrics else 'PASS' if (
        source['http_reqs']==sum(row['completed'] for row in rows)
        and source['scenario_request_attempts']==result['scenario']['attempts']
        and source['scenario_http_responses']==sum(row['responses'] for row in scenario)
        and source['scenario_transport_failures']==sum(row['noResponse'] for row in scenario)) else 'FAIL'
    result['httpVerdict']='FAIL' if any(row['httpVerdict']=='FAIL' for row in rows) or result['sourceReconciliation']=='FAIL' else 'UNMEASURED' if not result['scenario']['attempts'] or any(row['pending'] for row in rows) or result['sourceReconciliation']=='UNMEASURED' else 'PASS'
    result['offeredWorkVerdict']='FAIL' if source['dropped_iterations'] else 'UNMEASURED' if 'dropped_iterations' not in metrics else 'PASS'
    return result
