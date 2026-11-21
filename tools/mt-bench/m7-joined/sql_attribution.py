"""Attribute captured SQL to the writer-driven evaluator and realtime logins."""
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


def statements(path):
    rows={}
    for line in path.read_text().splitlines():
        role,calls,ms,queryid,dbid,text=line.split('\t')
        key=(role,queryid,dbid,text)
        require(key not in rows,'M7_SQL_DUPLICATE_STATEMENT')
        rows[key]={'calls':int(calls),'executionMs':float(ms)}
    return rows

def assess(before,after,roles):
    require(set(roles)=={'adapter'},'M7_SQL_SHARED_IDENTITY')
    require(all(isinstance(values,list) and all(isinstance(role,str) and role for role in values) and len(values)==len(set(values)) for values in roles.values()),'M7_SQL_SHARED_IDENTITY')
    flattened=[role for values in roles.values() for role in values]
    require(len(flattened)==len(set(flattened)) and roles['adapter'],'M7_SQL_SHARED_IDENTITY')
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
    return {'status':'MEASURED','roles':roles,'totals':totals,'roleTotals':raw,
            'unattributedRoles':sorted(set(raw)-set(flattened)),
            'scope':'Writer-driven evaluator and realtime SQL logins; other role totals retained separately.'}
