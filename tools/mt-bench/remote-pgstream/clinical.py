"""Reuse the existing selected clinical/output oracle on the SUT only."""
import json
import time
from protocol import need, write
import adapter as a

def completed(d, m, maximum=120):
    probe=a.document(d/'load/probe.json')
    witnesses=probe.get('clientWitnesses')
    need(isinstance(witnesses,list) and 1<=len(witnesses)<=4 and all(w.get('acked') is True for w in witnesses),'REMOTE_CLINICAL_CLIENT_WITNESS_REQUIRED')
    ids=sorted({w['tenant'] for w in witnesses})
    need(set(ids)<=set(row['id'] for row in a.document(d/'tenants.private.json')),'REMOTE_CLINICAL_TENANT_SCOPE')
    config=a.document(d/'completion-source.json')
    marker=(d/'load/runid').read_text().strip()
    script="const o=require(process.argv[1]);const s=JSON.parse(require('fs').readFileSync(0));console.log(JSON.stringify(s.mode==='query'?o.query(s.config,s.ids,s.marker):s.witnesses.map(w=>o.assess(s.rows.find(r=>r.tenant===w.tenant),w,w.clients,s.clients,s.config))));"
    def node(value):return json.loads(a.command(['node','-e',script,a.HERE/'completed-oracle.cjs'],input=json.dumps(value).encode()))
    query=node(dict(mode='query',config=config,ids=ids,marker=marker))
    deadline=time.monotonic()+maximum
    stamps={}
    while True:
        rows=[json.loads(line) for line in a.psql(d,query,a.application_database(d)).splitlines() if line]
        by_id={row['tenant']:row for row in rows}
        for tenant,row in by_id.items():
            if tenant not in stamps:stamps[tenant]=row['stamp']
        selected=[{**w,'stamp':stamps.get(w['tenant'])} for w in witnesses]
        assessed=node(dict(mode='assess',clients=m.get('cadence',{}).get('socketsPerTenant',2),rows=rows,witnesses=selected,config=config))
        evidence={'verdict':'PASS' if all(r.get('ready') is True for r in assessed) else 'UNMEASURED',
                  'scope':'selected stored marker, durable output/frame and BG-now mean/last plus actual already-connected clients; remaining clinical properties unassessed',
                  'observer':'SUT-only after steady SQL/cgroup bookend; no cross-host latency',
                  'witnesses':assessed,'selectedTenantCount':len(ids),'rosterTenants':m['tenants'],
                  'writeToEvaluationMs':'UNMEASURED','dueOpportunity':'UNMEASURED','reconnect':'UNMEASURED'}
        write(d/'completed-output.json',evidence)
        write(d/'completed-output.private.json',{'rows':rows,'clientWitnesses':selected})
        if evidence['verdict']=='PASS':return evidence
        need(time.monotonic()<deadline,'REMOTE_CLINICAL_COMPLETION_UNMEASURED')
        time.sleep(1)
