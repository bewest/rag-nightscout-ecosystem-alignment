"""Attribute captured SQL to source-selected pgstream versus adapter roles."""
from urllib.parse import urlsplit, unquote
from contract import require

def _postgres_identity(value):
    """Return role and database endpoint; never retain a URI or credentials."""
    try:
        parsed=urlsplit(value)
        role=unquote(parsed.username or '')
        endpoint=(parsed.hostname.lower(),parsed.port or 5432,unquote(parsed.path[1:]))
    except (ValueError,AttributeError,TypeError):
        raise RuntimeError('M7_ADAPTER_SQL_IDENTITY') from None
    require(role and endpoint[0] and endpoint[2],'M7_ADAPTER_SQL_IDENTITY')
    return role,endpoint


def identities(evaluator,environments):
    stream=evaluator.get('pgstream',{}).get('streamRole')
    require(isinstance(stream,str) and stream,'M7_PGSTREAM_SQL_IDENTITY')
    environments=list(environments)
    require(environments and all(isinstance(env,dict) for env in environments),'M7_ADAPTER_SQL_IDENTITY')
    adapter=set();references=[]
    for index,env in enumerate(environments):
        for name,value in env.items():
            if isinstance(value,str) and value.startswith(('postgres:','postgresql:')):
                role,_=_postgres_identity(value)
                adapter.add(role)
                if role==stream:references.append((index,name))
    require(adapter,'M7_ADAPTER_SQL_IDENTITY')
    recovery=evaluator.get('pgstream',{}).get('recovery')
    if recovery is not None:
        # The first environment is the evaluator's source-selected environment.
        # Native recovery deliberately borrows the pgstream role on that database.
        import re
        selected=recovery.get('connectionEnv') if isinstance(recovery,dict) else None
        require(isinstance(selected,str) and re.fullmatch('[A-Z][A-Z0-9_]{0,127}',selected),'M7_SQL_RECOVERY_IDENTITY')
        base=evaluator.get('postgres',{}).get('connectionEnv')
        require(isinstance(base,str) and base!=selected and selected in environments[0] and base in environments[0],'M7_SQL_RECOVERY_IDENTITY')
        recovery_role,recovery_endpoint=_postgres_identity(environments[0][selected])
        base_role,base_endpoint=_postgres_identity(environments[0][base])
        require(recovery_role==stream and base_role!=stream and recovery_endpoint==base_endpoint,'M7_SQL_RECOVERY_IDENTITY')
        require(references==[(0,selected)],'M7_SQL_SHARED_IDENTITY')
        return {'pgstream':[],'adapter':sorted(adapter-{stream}),'shared':[stream]}
    require(stream not in adapter,'M7_SQL_SHARED_IDENTITY')
    return {'pgstream':[stream],'adapter':sorted(adapter)}

def statements(path):
    rows={}
    for line in path.read_text().splitlines():
        role,calls,ms,queryid,dbid,text=line.split('\t')
        key=(role,queryid,dbid,text)
        require(key not in rows,'M7_SQL_DUPLICATE_STATEMENT')
        rows[key]={'calls':int(calls),'executionMs':float(ms)}
    return rows

def assess(before,after,roles):
    legacy=set(roles)=={'pgstream','adapter'}
    shared=set(roles)=={'pgstream','adapter','shared'}
    require(legacy or shared,'M7_SQL_SHARED_IDENTITY')
    require(all(isinstance(values,list) and all(isinstance(role,str) and role for role in values) and len(values)==len(set(values)) for values in roles.values()),'M7_SQL_SHARED_IDENTITY')
    flattened=[role for values in roles.values() for role in values]
    require(len(flattened)==len(set(flattened)) and roles['adapter'],'M7_SQL_SHARED_IDENTITY')
    require(bool(roles['pgstream']) if legacy else roles['pgstream']==[] and len(roles['shared'])==1,'M7_SQL_SHARED_IDENTITY')
    totals={kind:{'calls':0,'executionMs':0.0} for kind in roles}
    raw={}
    for key,value in after.items():
        initial=before.get(key,{'calls':0,'executionMs':0})
        delta={name:value[name]-initial[name] for name in value}
        require(all(v>=0 for v in delta.values()),'M7_SQL_COUNTER_RESET')
        cell=raw.setdefault(key[0],{'calls':0,'executionMs':0.0})
        for name,amount in delta.items():cell[name]+=amount
        for kind,selected in roles.items():
            if key[0] in selected:
                for name,amount in delta.items():totals[kind][name]+=amount
    require(all(key in after for key in before),'M7_SQL_STATEMENT_EVICTED')
    # A genuinely quiet configured role may have zero SQL; the runner separately
    # checks role existence. No role means unavailable attribution, not zero actor work.
    if legacy:
        return {'status':'MEASURED','roles':roles,'totals':totals,'scope':'pg_stat_statements execution work, not PostgreSQL CPU; full private statements retained'}
    totals['pgstream']={'status':'UNMEASURED','code':'M7_SQL_NO_EXCLUSIVE_IDENTITY','calls':None,'executionMs':None}
    return {'status':'MEASURED','roles':roles,'totals':totals,
            'roleTotals':{role:raw[role] for role in sorted(raw)},
            'unattributedRoles':sorted(set(raw)-set(flattened)),
            'processAttribution':{'status':'UNMEASURED','code':'M7_SQL_SHARED_PROCESS_IDENTITY',
                'sharedRoles':list(roles['shared']),
                'scope':'Shared-role SQL cannot be split between native pgstream and adapter recovery processes. Empty exclusive buckets do not establish zero actor work.'},
            'scope':'Disjoint exclusive/shared pg_stat_statements role buckets; shared SQL counted once, actual per-role execution retained. SQL execution sums are not PostgreSQL CPU or a process-cost split; full private statements retained'}
