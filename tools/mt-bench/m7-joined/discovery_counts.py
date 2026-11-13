"""Discovery-only count proof; strict acceptance keeps its original oracle."""
from contract import require

FIELDS={'attempts','accepted','uncertain','refused','pending'}

def integer(value):return type(value) is int and 0<=value<=100000

def probe_metadata(a,out,runid,expected):
    """Missing historic uncertainty is unknown, not zero or a positive violation."""
    fanout=out/'fanout.json';acks=None
    if fanout.is_file():
        require(not fanout.is_symlink() and fanout.stat().st_size<=4*1024*1024,'M7_PROBE_COUNTS_METADATA')
        raw=a.document(fanout)
        require(isinstance(raw,dict) and set(raw)=={'probeWrites'} and isinstance(raw['probeWrites'],dict) and set(raw['probeWrites'])=={'byTenant'},'M7_PROBE_COUNTS_METADATA')
        acks=raw['probeWrites']['byTenant']
        require(isinstance(acks,dict) and set(acks)<=expected and all(integer(n) for n in acks.values()),'M7_PROBE_COUNTS_METADATA')
    file=out/'probe-accounting.json'
    if not file.is_file():return None,acks
    require(not file.is_symlink() and file.stat().st_size<=4*1024*1024,'M7_PROBE_COUNTS_METADATA')
    value=a.document(file)
    require(isinstance(value,dict) and set(value)=={'version','kind','runId','roster','admissionsClosed','attempts','byTenant'},'M7_PROBE_COUNTS_METADATA')
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

def observe(a,d,out,runid,metrics):
    # Caller has revalidated ownership/source before the existing single SQL.
    tenants=a.document(d/'tenants.private.json');expected={r['id'] for r in tenants}
    findings={'verdict':'UNMEASURED','code':'M7_DISCOVERY_COUNTS_MISSING','failures':[],'failureCount':0,'probeCountProof':'UNMEASURED'}
    def fail(code):
        findings.update(verdict='RED',code=code)
        a.write(out/'oracle-findings.json',findings)
        error=RuntimeError(code);error.verdict='FAIL';error.oracleFindings=findings;raise error
    try:
        ledger,legacy=probe_metadata(a,out,runid,expected)
        values=a.stored(d,runid);a.write(out/'stored-counts.json',values)
        require(isinstance(values,dict) and set(values)<=expected,'M7_ORACLE_TENANT_SCOPE')
        missing=[];uncertain_total=0;all_uncertain=True;domains={k:0 for k in ('entries','devicestatus','treatments')};rows=[]
        complete=ledger is not None and ledger['admissionsClosed'] and all(r['pending']==0 for r in ledger['byTenant'].values())
        findings['probeCountProof']='KNOWN' if complete else 'UNMEASURED'
        findings['probeAccounting']={'version':2 if ledger else None,'admissionsClosed':ledger['admissionsClosed'] if ledger else None,'attempts':ledger['attempts'] if ledger else None,'pending':sum(r['pending'] for r in ledger['byTenant'].values()) if ledger else None}
        def violation(kind,tenant=None):
            findings['failureCount']+=1
            if len(findings['failures'])<64:findings['failures'].append({'kind':kind,**({'tenant':tenant} if tenant is not None else {})})
        for tenant in sorted(expected):
            value=values.get(tenant,{})
            require(isinstance(value,dict) and set(value)<=set(domains)|{'probe'} and all(type(n) is int and n>=0 for n in value.values()),'M7_ORACLE_COUNTS_INVALID')
            ok='writes_ok{tenant:'+tenant+'}';uncertain='writes_uncertain{tenant:'+tenant+'}'
            absent=[key for key in (ok,uncertain) if key not in metrics];missing+=absent
            accepted=a.metric(metrics,ok) if ok in metrics else None;ambiguous=a.metric(metrics,uncertain) if uncertain in metrics else None
            if ambiguous is not None:uncertain_total+=ambiguous
            else:all_uncertain=False
            stored=sum(value.get(kind,0) for kind in domains)
            if not absent and not accepted<=stored<=accepted+ambiguous:violation('workload-count-bound',tenant)
            probe=value.get('probe',0);pr=ledger['byTenant'].get(tenant,{k:0 for k in FIELDS}) if ledger else None
            if pr is not None:
                if not pr['accepted']<=probe<=pr['accepted']+pr['uncertain']+pr['pending']:violation('probe-count-bound',tenant)
            elif legacy is not None and probe<legacy.get(tenant,0):violation('probe-ack-missing',tenant)
            rows.append({'tenant':tenant,'accepted':accepted,'stored':stored,'uncertain':ambiguous,'probeStored':probe,'probeAccepted':pr['accepted'] if pr else legacy.get(tenant,0) if legacy is not None else None,'probeUncertain':pr['uncertain'] if pr else None,'probePending':pr['pending'] if pr else None,'probeRefused':pr['refused'] if pr else None,'match':not absent and complete and accepted<=stored<=accepted+ambiguous and pr['accepted']<=probe<=pr['accepted']+pr['uncertain']})
            for kind in domains:domains[kind]+=value.get(kind,0)
        for kind,count in domains.items():
            key='writes_ok{kind:'+kind+'}'
            if key not in metrics:missing.append(key)
            elif all_uncertain and not a.metric(metrics,key)<=count<=a.metric(metrics,key)+uncertain_total:violation('domain-count-bound:'+kind)
        # A present aggregate must equal all available tenant ACKs. Missing data
        # does not authorize fabricating zeros, even when the stored count is0.
        if not missing and 'writes_ok' in metrics and sum(r['accepted'] for r in rows)!=a.metric(metrics,'writes_ok'):violation('client-total-mismatch')
        findings.update(rows=rows,domains=domains,uncertain=uncertain_total,missingFieldCount=len(missing),missingFields=missing[:64])
        if findings['failureCount']:fail('M7_DISCOVERY_WRONG_DATA')
        if not missing and complete:findings.update(verdict='GREEN',code='M7_DISCOVERY_COUNTS_KNOWN')
        else:findings['code']='M7_DISCOVERY_ACK_METADATA_MISSING' if missing else 'M7_DISCOVERY_PROBE_COUNTS_UNMEASURED'
        a.write(out/'oracle-findings.json',findings)
        return findings,findings['verdict']=='GREEN'
    except Exception as error:
        if hasattr(error,'oracleFindings'):raise
        fail(str(error) if str(error).startswith('M7_') else 'M7_DISCOVERY_COUNT_INSTRUMENT_ERROR')
