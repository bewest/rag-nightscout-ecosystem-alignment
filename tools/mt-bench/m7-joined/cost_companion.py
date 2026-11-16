"""Companion cost snapshots for a newly pinned instrument; never backfills old runs."""
import hashlib
import json
import re
import time
from contract import require

SQL="""SELECT json_build_object('version',1,
'statsReset',(SELECT stats_reset::text FROM pg_stat_statements_info),
'dealloc',(SELECT dealloc FROM pg_stat_statements_info),
'statements',(SELECT coalesce(json_agg(json_build_object(
'role',r.rolname,'queryid',s.queryid::text,'dbid',s.dbid::text,
'queryHex',encode(convert_to(s.query,'UTF8'),'hex'),
'calls',s.calls,'rows',s.rows,'walBytes',to_jsonb(s)->'wal_bytes',
'walAvailable',to_jsonb(s)?'wal_bytes','toplevel',to_jsonb(s)->'toplevel')), '[]'::json)
FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid),
'databases',(SELECT coalesce(json_agg(json_build_object('dbid',datid::text,
'name',datname,'commits',xact_commit,'rollbacks',xact_rollback,
'statsReset',stats_reset::text)), '[]'::json) FROM pg_stat_database WHERE datid<>0));"""


def integer(v):return type(v)is int and v>=0

def validate(v):
    require(type(v.get('version'))is int and v['version']==1,'M7_COST_VERSION')
    require(isinstance(v.get('statsReset'),str) and bool(v['statsReset']) and integer(v.get('dealloc')),'M7_COST_RESET_PROVENANCE')
    require(isinstance(v.get('statements'),list) and len(v['statements'])<=100000 and isinstance(v.get('databases'),list),'M7_COST_ROSTER')
    keys=set()
    for s in v['statements']:
        require(all(isinstance(s.get(k),str) and s[k] for k in ('role','queryid','dbid','queryHex')),'M7_COST_STATEMENT_IDENTITY')
        try:raw=bytes.fromhex(s['queryHex']);raw.decode('utf8')
        except (ValueError,UnicodeError):raise RuntimeError('M7_COST_QUERY_ENCODING')
        require(integer(s.get('calls')) and integer(s.get('rows')),'M7_COST_COUNTER')
        require(type(s.get('walAvailable'))is bool,'M7_COST_CAPABILITY')
        require(integer(s.get('walBytes')) if s['walAvailable'] else s.get('walBytes')is None,'M7_COST_WAL_COUNTER')
        require(s.get('toplevel')is None or type(s['toplevel'])is bool,'M7_COST_TOPLEVEL')
        key=(s['role'],s['queryid'],s['dbid'],s.get('toplevel'),s['queryHex'])
        require(key not in keys,'M7_COST_DUPLICATE_STATEMENT');keys.add(key)
    dbs=set()
    for d in v['databases']:
        require(isinstance(d.get('dbid'),str) and d['dbid'] not in dbs and isinstance(d.get('name'),str),'M7_COST_DATABASE_IDENTITY');dbs.add(d['dbid'])
        require(integer(d.get('commits')) and integer(d.get('rollbacks')) and (d.get('statsReset')is None or isinstance(d['statsReset'],str)),'M7_COST_DATABASE_COUNTER')
    return v


def capture(out,name,owner,query):
    start=time.monotonic_ns()
    result={'version':1,'collectorOwner':owner.get('owner'),'hostIdentity':owner.get('hostIdentity'),
            'pair':owner.get('pair'),'imageId':owner.get('imageId'),
            'scope':'pgss statement rows/WAL; database transactions are shared and collector-inclusive; no SQL wire bytes or round trips'}
    try:
        raw=query(SQL)
        require(len(raw.encode('utf8'))<=67108864,'M7_COST_RESPONSE_BOUND')
        value=validate(json.loads(raw))
        result.update(status='MEASURED',snapshot=value)
    except Exception as error:
        result.update(status='NO-INSTRUMENT',reason='M7_COST_SNAPSHOT_UNAVAILABLE',failureType=type(error).__name__)
    result['request']={'monotonicStartedAtNs':start,'monotonicFinishedAtNs':time.monotonic_ns()}
    path=out/(name+'-pg-costs.json')
    path.write_text(json.dumps(result,indent=2)+'\n');path.chmod(0o600)
    return result


def assess(before,after):
    if before.get('status')!='MEASURED' or after.get('status')!='MEASURED':return {'status':'NO-INSTRUMENT','reason':'M7_COST_BOOKEND_UNAVAILABLE'}
    for k in ('collectorOwner','hostIdentity','pair','imageId'):
        require(before.get(k)is not None and before[k]==after.get(k),'M7_COST_OWNER_SOURCE_CHANGED')
    require(isinstance(before['collectorOwner'],str) and re.fullmatch('[a-f0-9]{32}',before['collectorOwner']) and isinstance(before['hostIdentity'],str) and re.fullmatch('[a-f0-9]{64}',before['hostIdentity']),'M7_COST_OWNER_SOURCE_CHANGED')
    require(isinstance(before['pair'],dict) and set(before['pair'])=={'core','deploy'} and all(isinstance(v,str) and re.fullmatch('[a-f0-9]{40}',v) for v in before['pair'].values()) and isinstance(before['imageId'],str) and re.fullmatch('sha256:[a-f0-9]{64}',before['imageId']),'M7_COST_OWNER_SOURCE_CHANGED')
    a,b=validate(before['snapshot']),validate(after['snapshot'])
    require(a['statsReset']==b['statsReset'] and a['dealloc']==b['dealloc'],'M7_COST_RESET_OR_EVICTION')
    x,y=before['request'],after['request'];points=[x['monotonicStartedAtNs'],x['monotonicFinishedAtNs'],y['monotonicStartedAtNs'],y['monotonicFinishedAtNs']]
    require(all(integer(p) for p in points) and points[0]<=points[1]<points[2]<=points[3],'M7_COST_TIMING')
    key=lambda s:(s['role'],s['queryid'],s['dbid'],s.get('toplevel'),s['queryHex'])
    old={key(s):s for s in a['statements']};new={key(s):s for s in b['statements']}
    require(set(old)<=set(new),'M7_COST_STATEMENT_EVICTED')
    rows=[];totals={}
    for k,s in new.items():
        prev=old.get(k,{'calls':0,'rows':0,'walBytes':0,'walAvailable':s['walAvailable']})
        require(prev['walAvailable']==s['walAvailable'],'M7_COST_CAPABILITY_CHANGED')
        delta={n:s[n]-prev[n] for n in ('calls','rows')}
        if s['walAvailable']:delta['walBytes']=s['walBytes']-prev['walBytes']
        require(all(v>=0 for v in delta.values()),'M7_COST_COUNTER_RESET')
        delta['walBytes']=delta.get('walBytes')
        rows.append({'role':s['role'],'queryid':s['queryid'],'dbid':s['dbid'],'toplevel':s.get('toplevel'),'sqlSha256':hashlib.sha256(bytes.fromhex(s['queryHex'])).hexdigest(),**delta})
        t=totals.setdefault(s['role'],{'calls':0,'rows':0,'walBytes':0,'walStatus':'MEASURED'})
        for n in ('calls','rows'):t[n]+=delta[n]
        if delta['walBytes']is None:t.update(walStatus='NO-INSTRUMENT',walBytes=None)
        elif t['walBytes']is not None:t['walBytes']+=delta['walBytes']
    dbold={d['dbid']:d for d in a['databases']};dbnew={d['dbid']:d for d in b['databases']}
    require(dbold.keys()==dbnew.keys(),'M7_COST_DATABASE_ROSTER_CHANGED')
    dbs=[]
    for k,d in dbnew.items():
        prev=dbold[k];require(d['statsReset']==prev['statsReset'] and d['name']==prev['name'],'M7_COST_DATABASE_RESET')
        delta={n:d[n]-prev[n] for n in ('commits','rollbacks')};require(all(v>=0 for v in delta.values()),'M7_COST_DATABASE_RESET')
        dbs.append({'dbid':k,'name':d['name'],**delta})
    return {'status':'MEASURED','statements':rows,'byRole':totals,'databaseTransactions':dbs,
            'elapsedBoundsSeconds':{'lower':(points[2]-points[1])/1e9,'upper':(points[3]-points[0])/1e9},
            'transactionScope':'shared database; includes collector transactions; not per-role commits',
            'wireBytes':'NO-INSTRUMENT','wireRoundTrips':'NO-INSTRUMENT'}
