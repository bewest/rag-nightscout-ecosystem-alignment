"""Declared total stock viewers, assigned in roster order; no runtime authority."""
import hashlib
import json

from contract import require
import workload_inputs

def setup(cadence, need=require):
    selected = cadence.get('viewerSetup', {})
    need(isinstance(selected, dict) and set(selected) <=
         {'opensPerSecond', 'transport', 'scenario', 'stallSeconds', 'mix'}, 'M7_VIEWER_SETUP_FIELDS')
    if 'mix' in selected:
        check_mix(selected['mix'])
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


# Optional per-tenant viewer mix (followers, several devices): viewerSetup.mix =
#   {'seed': int, 'shares': [[sockets, percent], ...]}   percents are integers summing to 100
# Tenants are ranked by sha256(seed:index:viewers); the first round(n*p/100) ranks take the first share's socket
# count, and so on (the last share takes the remainder). Absent: the declared total spread evenly, unchanged.
# capacity/probe and m7-joined/joined-probe.cjs mirror this rule (test_viewer_mix.py proves they agree).
MIX_PRESETS = {
    'followers-v1': {'seed': 20261123, 'shares': [[0, 10], [1, 20], [2, 40], [4, 20], [8, 10]]},  # mean 2.6
}

def check_mix(mix):
    require(isinstance(mix,dict) and set(mix)=={'seed','shares'} and type(mix['seed']) is int and 0<=mix['seed']<2**63,'M7_VIEWER_MIX')
    shares=mix['shares']
    require(isinstance(shares,list) and 1<=len(shares)<=16 and all(isinstance(r,list) and len(r)==2 and all(type(v) is int for v in r)
        and 0<=r[0]<=64 and 0<=r[1]<=100 for r in shares) and sum(r[1] for r in shares)==100,'M7_VIEWER_MIX_SHARES')

def mix_counts(mix,n):
    """Sockets per tenant index 0..n-1 under a viewer mix (deterministic from the mix and n)."""
    check_mix(mix);require(type(n) is int and n>0,'M7_VIEWER_ROSTER')
    rank=sorted(range(n),key=lambda i:hashlib.sha256(f"{mix['seed']}:{i}:viewers".encode()).hexdigest())
    out=[0]*n;start=0;done=0
    for k,(sockets,percent) in enumerate(mix['shares']):
        done+=percent;end=n if k==len(mix['shares'])-1 else (n*done+50)//100
        for i in rank[start:end]:out[i]=sockets
        start=end
    return out

def mix_of(m):
    return m.get('cadence',{}).get('viewerSetup',{}).get('mix')

def total(m):
    cadence=m.get('cadence',{})
    if mix_of(m) is not None:return sum(mix_counts(mix_of(m),m['tenants']))
    value=cadence.get('logicalPollingClients',cadence.get('socketsPerTenant',2)*m['tenants'])
    require(workload_inputs.polling_clients(value),'M7_VIEWER_TOTAL_RANGE')
    return value

def counts(m,roster):
    ids=[row['id'] for row in roster]
    require(len(ids)==m['tenants'] and len(set(ids))==len(ids) and bool(ids),'M7_VIEWER_ROSTER')
    if mix_of(m) is not None:return dict(zip(ids,mix_counts(mix_of(m),len(ids))))
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
