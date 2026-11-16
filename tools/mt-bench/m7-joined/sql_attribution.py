"""Attribute captured SQL to source-selected pgstream versus adapter roles."""
from urllib.parse import urlsplit, unquote
from contract import require

def identities(evaluator,environments):
    stream=evaluator.get('pgstream',{}).get('streamRole')
    require(isinstance(stream,str) and stream,'M7_PGSTREAM_SQL_IDENTITY')
    adapter=set()
    for env in environments:
        for value in env.values():
            if isinstance(value,str) and value.startswith(('postgres:','postgresql:')):
                role=unquote(urlsplit(value).username or '')
                require(role,'M7_ADAPTER_SQL_IDENTITY');adapter.add(role)
    require(adapter and stream not in adapter,'M7_SQL_SHARED_IDENTITY')
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
    require(set(roles)=={'pgstream','adapter'} and roles['pgstream'] and roles['adapter'] and not set(roles['pgstream'])&set(roles['adapter']),'M7_SQL_SHARED_IDENTITY')
    totals={kind:{'calls':0,'executionMs':0.0} for kind in roles}
    for key,value in after.items():
        initial=before.get(key,{'calls':0,'executionMs':0})
        delta={name:value[name]-initial[name] for name in value}
        require(all(v>=0 for v in delta.values()),'M7_SQL_COUNTER_RESET')
        for kind,selected in roles.items():
            if key[0] in selected:
                for name,value in delta.items():totals[kind][name]+=value
    require(all(key in after for key in before),'M7_SQL_STATEMENT_EVICTED')
    # A genuinely quiet role may have zero SQL. Its configured identity still
    # must exist on the database; the runner separately captures pg_roles.
    return {'status':'MEASURED','roles':roles,'totals':totals,'scope':'pg_stat_statements execution work, not PostgreSQL CPU; full private statements retained'}
