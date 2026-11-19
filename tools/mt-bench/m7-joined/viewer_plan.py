"""Declared total stock viewers, assigned in roster order; no runtime authority."""
import json

from contract import require
import workload_inputs

def setup(cadence, need=require):
    selected = cadence.get('viewerSetup', {})
    need(isinstance(selected, dict) and set(selected) <=
         {'opensPerSecond', 'transport', 'scenario', 'stallSeconds'}, 'M7_VIEWER_SETUP_FIELDS')
    # The 50/s default also has a stock admission control. The prior 300 s
    # prime window becomes a no-progress interval independent of population.
    settings = {'opensPerSecond': 50, 'transport': 'websocket-first', 'scenario': 'ordinary',
                'stallSeconds': 300, **selected}
    need(workload_inputs.offered_rate(settings['opensPerSecond']), 'M7_VIEWER_OPEN_RATE')
    need(workload_inputs.seconds(settings['stallSeconds']), 'M7_VIEWER_STALL_SECONDS')
    need(settings['transport'] in ('websocket-first', 'polling'), 'M7_VIEWER_TRANSPORT')
    need(settings['scenario'] in ('ordinary', 'simultaneous-reconnect'), 'M7_VIEWER_SCENARIO')
    if settings['scenario'] == 'simultaneous-reconnect':
        need(cadence.get('logicalPollingClients') != 0, 'M7_VIEWER_RECONNECT_EMPTY')
    return settings


def setup_args(cadence):
    return ['--viewerSetup', json.dumps(setup(cadence), separators=(',', ':'))]


def stage_cadence(cadence, ordinary):
    if ordinary:
        return cadence
    # Commission and recovery exercise the transport used by the shipping UI.
    return {**cadence, 'viewerSetup': {**cadence.get('viewerSetup', {}),
                                      'transport': 'polling', 'scenario': 'ordinary'}}


def total(m):
    cadence=m.get('cadence',{})
    value=cadence.get('logicalPollingClients',cadence.get('socketsPerTenant',2)*m['tenants'])
    require(workload_inputs.polling_clients(value),'M7_VIEWER_TOTAL_RANGE')
    return value

def counts(m,roster):
    ids=[row['id'] for row in roster]
    require(len(ids)==m['tenants'] and len(set(ids))==len(ids) and bool(ids),'M7_VIEWER_ROSTER')
    n=total(m);return {tenant:n//len(ids)+(i<n%len(ids)) for i,tenant in enumerate(ids)}

def check(m,roster,probe,by_tenant):
    """Use declared roster/total and independent accepted-write accounting."""
    assigned=counts(m,roster);n=total(m)
    bindings=[]
    for tenant,count in assigned.items():
        for _ in range(count):bindings.append({'socket':len(bindings),'tenant':tenant})
    actual=probe.get('viewerBindings')
    require(isinstance(actual,list) and all(isinstance(row,dict) and set(row)=={'socket','tenant'} and type(row['socket']) is int for row in actual) and actual==bindings,'M7_VIEWER_BINDINGS')
    window=probe.get('window',{});prime=probe.get('prime',{})
    require(all(type(row.get(key)) is int for row,key in [(prime,'sockets'),(prime,'primed'),(window,'sockets'),(window,'connectedAtEnd')]) and prime.get('sockets')==n and prime.get('primed')==n and window.get('sockets')==n and window.get('connectedAtEnd')==n,'M7_VIEWER_COUNTS')
    require(isinstance(by_tenant,dict) and set(by_tenant)<=set(assigned) and all(type(v) is int and v>=0 for v in by_tenant.values()),'M7_VIEWER_WRITE_ROSTER')
    writes=window.get('writes',{})
    require(type(writes.get('failed')) is int and type(writes.get('ok')) is int and writes.get('failed')==0 and writes.get('ok')==sum(by_tenant.values()),'M7_VIEWER_WRITE_COUNTS')
    expected=sum(count*assigned[tenant] for tenant,count in by_tenant.items())
    require(type(window.get('expectedFrames')) is int and window['expectedFrames']==expected and type(window.get('deliveredFrames')) is int and window['deliveredFrames']==expected,'M7_VIEWER_FRAMES')
    scenario = probe.get('viewerSetup', {})
    return {'verdict':'PASS' if expected else 'NOT_EXERCISED',
            **{key:scenario[key] for key in ('scenario','transport') if key in scenario},
            'logicalPollingClients':n,'expectedFrames':expected,'scope':'declared viewer bindings and accepted probe writes; stored/output/authority checked separately'}
