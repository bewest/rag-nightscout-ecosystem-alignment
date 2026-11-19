"""Discovery-only count proof; strict acceptance keeps its original oracle."""
import math
from contract import require
from workload_inputs import DEFAULT_PROBE_LEDGER, probe_ledger as valid_probe_ledger

FIELDS={'attempts','accepted','uncertain','refused','pending'}

def counter(metrics,key):
    """A missing count is unknown; only finite nonnegative integer counters exist."""
    if key not in metrics:return None
    row=metrics[key]
    require(isinstance(row,dict),'M7_DISCOVERY_COUNTER_INVALID')
    if 'values' in row:
        row=row['values'];require(isinstance(row,dict),'M7_DISCOVERY_COUNTER_INVALID')
    if 'count' not in row:return None
    value=row['count']
    require(type(value) in (int,float) and 0<=value<=9007199254740991 and math.isfinite(value) and int(value)==value,'M7_DISCOVERY_COUNTER_INVALID')
    return int(value)

def probe_metadata(a,out,runid,expected,*,probe_ledger=None):
    """Missing historic uncertainty is unknown, not zero or a positive violation."""
    require(probe_ledger is None or valid_probe_ledger(probe_ledger),'M7_PROBE_LEDGER_BUDGET')
    budget=DEFAULT_PROBE_LEDGER if probe_ledger is None else probe_ledger
    def integer(value):return type(value) is int and 0<=value<=budget['maxWrites']
    fanout=out/'fanout.json';acks=None
    if fanout.is_file():
        require(not fanout.is_symlink() and fanout.stat().st_size<=budget['maxBytes'],'M7_PROBE_COUNTS_METADATA')
        raw=a.document(fanout)
        require(isinstance(raw,dict) and set(raw)=={'probeWrites'} and isinstance(raw['probeWrites'],dict) and set(raw['probeWrites'])=={'byTenant'},'M7_PROBE_COUNTS_METADATA')
        acks=raw['probeWrites']['byTenant']
        require(isinstance(acks,dict) and set(acks)<=expected and all(integer(n) for n in acks.values()),'M7_PROBE_COUNTS_METADATA')
    file=out/'probe-accounting.json'
    if not file.is_file():return None,acks
    require(not file.is_symlink() and file.stat().st_size<=budget['maxBytes'],'M7_PROBE_COUNTS_METADATA')
    value=a.document(file)
    fields={'version','kind','runId','roster','admissionsClosed','attempts','byTenant'}
    if probe_ledger is not None:fields.add('budget')
    require(isinstance(value,dict) and set(value)==fields and value.get('budget')==probe_ledger,'M7_PROBE_COUNTS_METADATA')
    require(value['version']==2 and value['kind']=='m7-discovery-probe-accounting' and value['runId']==runid,'M7_PROBE_COUNTS_METADATA')
    roster=value['roster'];rows=value['byTenant']
    require(isinstance(roster,list) and len(roster)==len(expected) and all(type(t) is str for t in roster) and set(roster)==expected,'M7_PROBE_COUNTS_ROSTER')
    require(type(value['admissionsClosed']) is bool and integer(value['attempts']) and isinstance(rows,dict) and set(rows)<=expected,'M7_PROBE_COUNTS_METADATA')
    for tenant,row in rows.items():
        require(isinstance(row,dict) and set(row)==FIELDS and all(integer(n) for n in row.values()),'M7_PROBE_COUNTS_METADATA')
        require(row['attempts']>0 and row['attempts']==sum(row[k] for k in FIELDS-{'attempts'}),'M7_PROBE_COUNTS_ATTEMPTS')
    require(value['attempts']==sum(row['attempts'] for row in rows.values()),'M7_PROBE_COUNTS_ATTEMPTS')
    if acks is not None:
        require(all(acks.get(t,0)==rows.get(t,{}).get('accepted',0) for t in expected),'M7_PROBE_COUNTS_ACK_MISMATCH')
    return value,acks

def observe(a,d,out,runid,metrics,*,probe_ledger=None,ordinary_ids=None):
    # Caller has revalidated ownership/source before the existing single SQL.
    findings={'verdict':'UNMEASURED','code':'M7_DISCOVERY_COUNTS_MISSING','failures':[],'failureCount':0,'probeCountProof':'UNMEASURED'}
    def fail(code):
        findings.update(verdict='RED',code=code)
        a.write(out/'oracle-findings.json',findings)
        error=RuntimeError(code);error.verdict='FAIL';error.oracleFindings=findings;raise error
    try:
        tenants = a.document(d/'tenants.private.json')
        expected = {row['id'] for row in tenants}
        require(expected and len(expected) == len(tenants), 'M7_ORACLE_TENANT_SCOPE')
        ordinary = expected if ordinary_ids is None else set(ordinary_ids)
        require(ordinary and ordinary <= expected and (ordinary_ids is None or len(ordinary) == len(ordinary_ids)),
                'M7_DISCOVERY_ORDINARY_ROSTER')
        ledger,legacy=probe_metadata(a,out,runid,expected,probe_ledger=probe_ledger)
        require(isinstance(metrics,dict),'M7_DISCOVERY_COUNTER_INVALID')
        domains = dict.fromkeys(('entries', 'devicestatus', 'treatments'), 0)
        # k6 counts writes per kind and in total, never per tenant; the per-tenant
        # figure is the stored row count. Each accepted input is judged by the assessor.
        required = ['writes_ok', 'writes_uncertain', *(f'writes_ok{{kind:{kind}}}' for kind in domains)]
        counts = {key: counter(metrics, key) for key in required}
        # Validate malformed present counters before opening the SQL client.
        values=a.stored(d,runid);a.write(out/'stored-counts.json',values)
        require(isinstance(values,dict) and set(values)<=expected,'M7_ORACLE_TENANT_SCOPE')
        missing=[key for key,value in counts.items() if value is None];rows=[];ordinary_stored=0
        complete=ledger is not None and ledger['admissionsClosed'] and all(r['pending']==0 for r in ledger['byTenant'].values())
        findings['probeCountProof']='KNOWN' if complete else 'UNMEASURED'
        findings['probeAccounting']={'version':2 if ledger else None,'admissionsClosed':ledger['admissionsClosed'] if ledger else None,'attempts':ledger['attempts'] if ledger else None,'pending':sum(r['pending'] for r in ledger['byTenant'].values()) if ledger else None}
        if probe_ledger is not None:findings['probeAccounting']['budget']=probe_ledger
        def violation(kind,tenant=None):
            findings['failureCount']+=1
            if len(findings['failures'])<64:findings['failures'].append({'kind':kind,**({'tenant':tenant} if tenant is not None else {})})
        for tenant in sorted(expected):
            value=values.get(tenant,{})
            require(isinstance(value,dict) and set(value)<=set(domains)|{'probe'} and all(type(n) is int and n>=0 for n in value.values()),'M7_ORACLE_COUNTS_INVALID')
            stored=sum(value.get(kind,0) for kind in domains)
            # No ordinary writes are expected on an inactive tenant.
            if tenant in ordinary:ordinary_stored+=stored
            elif stored:violation('unselected-workload-write', tenant)
            probe=value.get('probe',0);pr=ledger['byTenant'].get(tenant,{k:0 for k in FIELDS}) if ledger else None
            if pr is not None:
                if not pr['accepted']<=probe<=pr['accepted']+pr['uncertain']+pr['pending']:violation('probe-count-bound',tenant)
            elif legacy is not None and probe<legacy.get(tenant,0):violation('probe-ack-missing',tenant)
            rows.append({
                'tenant': tenant, 'ordinarySelected': tenant in ordinary, 'stored': stored,
                'probeStored': probe,
                'probeAccepted': pr['accepted'] if pr else legacy.get(tenant, 0) if legacy is not None else None,
                'probeUncertain': pr['uncertain'] if pr else None,
                'probePending': pr['pending'] if pr else None,
                'probeRefused': pr['refused'] if pr else None,
                'match': complete and (tenant in ordinary or stored == 0)
                         and pr['accepted'] <= probe <= pr['accepted'] + pr['uncertain'],
            })
            for kind in domains:domains[kind]+=value.get(kind,0)
        accepted,uncertain=counts['writes_ok'],counts['writes_uncertain']
        if accepted is not None and uncertain is not None:
            if not accepted<=ordinary_stored<=accepted+uncertain:violation('workload-count-bound')
            for kind,count in domains.items():
                key='writes_ok{kind:'+kind+'}'
                if counts[key] is not None and not counts[key]<=count<=counts[key]+uncertain:violation('domain-count-bound:'+kind)
        findings.update(rows=rows,domains=domains,accepted=accepted,stored=ordinary_stored,uncertain=uncertain,missingFieldCount=len(missing),missingFields=missing[:64])
        if findings['failureCount']:fail('M7_DISCOVERY_WRONG_DATA')
        if not missing and complete:findings.update(verdict='GREEN',code='M7_DISCOVERY_COUNTS_KNOWN')
        else:findings['code']='M7_DISCOVERY_ACK_METADATA_MISSING' if missing else 'M7_DISCOVERY_PROBE_COUNTS_UNMEASURED'
        a.write(out/'oracle-findings.json',findings)
        return findings,findings['verdict']=='GREEN'
    except Exception as error:
        if hasattr(error,'oracleFindings'):raise
        fail(str(error) if str(error).startswith('M7_') else 'M7_DISCOVERY_COUNT_INSTRUMENT_ERROR')


def control_domain(findings, tenant_count):
    """A sparse exact cohort can witness loss without every tenant writing.

    Uncertain or missing ACKs cannot establish a one-row corruption control.
    Return only a fixed SQL domain with a positive ordinary-write witness.
    """
    if not isinstance(findings,dict) or findings.get('verdict')!='GREEN':return None
    if findings.get('failureCount')!=0 or findings.get('failures')!=[] or findings.get('missingFieldCount')!=0:return None
    accounting=findings.get('probeAccounting',{})
    if findings.get('probeCountProof')!='KNOWN' or accounting.get('version')!=2 or accounting.get('admissionsClosed') is not True or accounting.get('pending')!=0:return None
    rows=findings.get('rows')
    if not isinstance(rows,list) or len(rows)!=tenant_count or not rows:return None
    if any(not isinstance(row,dict) or not isinstance(row.get('tenant'),str) for row in rows):return None
    if len({row['tenant'] for row in rows})!=len(rows):return None
    for row in rows:
        if any(type(row.get(k)) is not int or row[k]<0 for k in ('stored','probeStored','probeAccepted','probeUncertain','probePending')):return None
        if row.get('match') is not True:return None
        if row['probeUncertain']!=0 or row['probePending']!=0 or row['probeAccepted']!=row['probeStored']:return None
    total=findings.get('accepted')
    domains=findings.get('domains')
    if type(total) is not int or total<=0 or findings.get('uncertain')!=0 or findings.get('stored')!=total or not isinstance(domains,dict) or set(domains)!={'entries','devicestatus','treatments'}:return None
    if any(type(n) is not int or n<0 for n in domains.values()) or sum(domains.values())!=total:return None
    return next(kind for kind in ('entries','devicestatus','treatments') if domains[kind]>0)
