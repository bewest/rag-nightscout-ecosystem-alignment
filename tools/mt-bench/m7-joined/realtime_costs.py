"""Strict cached inspection companion; never treats runtime counts as detector polls."""
import json,re,time
from contract import DISCOVERY_MAX_WORKERS, require
COUNTERS=('ticks','refreshes','detected','detectFailures')
DELIVERY_COUNTERS=('received','completed','retries','workQueries','metadataUpdates','metadataRows')
DELIVERY_FIELDS=(*DELIVERY_COUNTERS,'maxMetadataBatch')
UUID=re.compile('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
def number(v):return type(v)is int and 0<=v<=9007199254740991

def parse(v):
    require(v.get('kind')=='realtime' and isinstance(v.get('processIncarnation'),str) and UUID.fullmatch(v['processIncarnation']),'M7_REALTIME_COST_IDENTITY')
    s=v.get('stats')
    if not isinstance(s,dict):return {'status':'NO-INSTRUMENT','reason':'M7_REALTIME_COST_UNSUPPORTED_SOURCE'}
    require({'version','available','runtime','detector','watchedCount'}<=set(s)<= {'version','available','runtime','detector','watchedCount','delivery'} and type(s['version'])is int and s['version']==1 and type(s['available'])is bool,'M7_REALTIME_COST_SHAPE')
    delivery=s.get('delivery')
    if delivery is not None:require(isinstance(delivery,dict) and set(delivery)==set(DELIVERY_FIELDS) and all(number(delivery[k]) for k in DELIVERY_FIELDS) and delivery['maxMetadataBatch']<=64,'M7_REALTIME_COST_DELIVERY')
    d=s['detector'];require(isinstance(d,dict) and set(d)=={'available','polls','failures'} and type(d['available'])is bool,'M7_REALTIME_COST_DETECTOR')
    if d['available']:require(number(d['polls']) and number(d['failures']),'M7_REALTIME_COST_COUNTER')
    else:require(d['polls']is None and d['failures']is None,'M7_REALTIME_COST_UNAVAILABLE_NOT_ZERO')
    if not s['available']:
        require(s['runtime']is None and s['watchedCount']is None,'M7_REALTIME_COST_UNAVAILABLE_NOT_ZERO')
        return {'status':'NO-INSTRUMENT','reason':'M7_REALTIME_COST_UNAVAILABLE'}
    require(isinstance(s['runtime'],dict) and set(s['runtime'])==set(COUNTERS) and all(number(s['runtime'][k]) for k in COUNTERS),'M7_REALTIME_COST_COUNTER')
    require(number(s['watchedCount']),'M7_REALTIME_COST_WATCHED_BOUND')
    if v.get('phase')!='booted' or v.get('ownerAvailable')is not True:return {'status':'NO-INSTRUMENT','reason':'M7_REALTIME_COST_OWNER_UNAVAILABLE'}
    return {'status':'MEASURED','processIncarnation':v['processIncarnation'],'stats':s}

def capture(out,name,owner,services,fetch):
    require(len(services)<=DISCOVERY_MAX_WORKERS and len(set(services))==len(services),'M7_REALTIME_COST_INSTANCE_BOUND')
    result={'version':1,**{k:owner.get(k) for k in ('owner','hostIdentity','pair','imageId')},'scope':'cached private RPC only; watchedCount is a gauge, no tenant scan; runtime detected is not detector polls','services':{}}
    for service in services:
        start=time.monotonic_ns()
        try:
            raw=fetch(service);require(len(raw.encode('utf8'))<=8192,'M7_REALTIME_COST_RESPONSE_BOUND')
            row=parse(json.loads(raw))
        except Exception as error:row={'status':'NO-INSTRUMENT','reason':'M7_REALTIME_COST_UNAVAILABLE','failureType':type(error).__name__}
        row['request']={'monotonicStartedAtNs':start,'monotonicFinishedAtNs':time.monotonic_ns()};result['services'][service]=row
    result['status']='MEASURED' if services and all(r['status']=='MEASURED' for r in result['services'].values()) else 'NO-INSTRUMENT'
    path=out/(name+'-realtime-costs.json');path.write_text(json.dumps(result,indent=2)+'\n');path.chmod(0o600)
    return result

def assess(before,after):
    if before.get('status')!='MEASURED' or after.get('status')!='MEASURED':return {'status':'NO-INSTRUMENT','reason':'M7_REALTIME_COST_BOOKEND_UNAVAILABLE'}
    require(before.get('version')==after.get('version')==1,'M7_REALTIME_COST_VERSION')
    for k in ('owner','hostIdentity','pair','imageId'):require(before.get(k)is not None and before[k]==after.get(k),'M7_REALTIME_COST_SOURCE_OWNER_CHANGED')
    require(isinstance(before['owner'],str) and re.fullmatch('[a-f0-9]{32}',before['owner']) and isinstance(before['hostIdentity'],str) and re.fullmatch('[a-f0-9]{64}',before['hostIdentity']),'M7_REALTIME_COST_SOURCE_OWNER_CHANGED')
    require(isinstance(before['pair'],dict) and set(before['pair'])=={'core','deploy'} and all(isinstance(v,str) and re.fullmatch('[a-f0-9]{40}',v) for v in before['pair'].values()) and isinstance(before['imageId'],str) and re.fullmatch('sha256:[a-f0-9]{64}',before['imageId']),'M7_REALTIME_COST_SOURCE_OWNER_CHANGED')
    require(before['services'] and before['services'].keys()==after['services'].keys(),'M7_REALTIME_COST_ROSTER_CHANGED')
    rows={}
    for service,a in before['services'].items():
        b=after['services'][service]
        for value in (a,b):require(parse({'kind':'realtime','processIncarnation':value['processIncarnation'],'phase':'booted','ownerAvailable':True,'stats':value['stats']})['status']=='MEASURED','M7_REALTIME_COST_SHAPE')
        require(a['processIncarnation']==b['processIncarnation'],'M7_REALTIME_COST_PROCESS_CHANGED')
        x,y=a['request'],b['request'];points=[x['monotonicStartedAtNs'],x['monotonicFinishedAtNs'],y['monotonicStartedAtNs'],y['monotonicFinishedAtNs']]
        require(all(number(p) for p in points) and points[0]<=points[1]<points[2]<=points[3],'M7_REALTIME_COST_TIMING')
        delta={k:b['stats']['runtime'][k]-a['stats']['runtime'][k] for k in COUNTERS};require(all(v>=0 for v in delta.values()),'M7_REALTIME_COST_RESET')
        da,db=a['stats']['detector'],b['stats']['detector'];require(da['available']==db['available'],'M7_REALTIME_COST_CAPABILITY_CHANGED')
        detector={'status':'NO-INSTRUMENT'}
        if da['available']:
            detector={'status':'MEASURED',**{k:db[k]-da[k] for k in ('polls','failures')}};require(all(detector[k]>=0 for k in ('polls','failures')),'M7_REALTIME_COST_RESET')
        xa,xb=a['stats'].get('delivery'),b['stats'].get('delivery');delivery={'status':'NO-INSTRUMENT','reason':'M7_REALTIME_COST_DELIVERY_UNAVAILABLE'}
        if xa is not None and xb is not None:
            delivery={'status':'MEASURED','counterDelta':{k:xb[k]-xa[k] for k in DELIVERY_COUNTERS},'maxMetadataBatch':{'before':xa['maxMetadataBatch'],'after':xb['maxMetadataBatch'],'scope':'process high-water gauge; not a window batch-size average'}}
            require(all(value>=0 for value in delivery['counterDelta'].values()) and xb['maxMetadataBatch']>=xa['maxMetadataBatch'],'M7_REALTIME_COST_RESET')
        rows[service]={'deliveryDelta':delivery,'processIncarnation':a['processIncarnation'],'runtimeDelta':delta,'detectorDelta':detector,'watchedCount':{'before':a['stats']['watchedCount'],'after':b['stats']['watchedCount'],'scope':'bookend gauge, not continuous viewer maximum or integral'},'elapsedBoundsSeconds':{'lower':(points[2]-points[1])/1e9,'upper':(points[3]-points[0])/1e9}}
    return {'status':'MEASURED','services':rows,'scope':'same process cached counter deltas; runtime detected is batch calls, not detector poll count; no inferred output revisions or strict deadlines'}
