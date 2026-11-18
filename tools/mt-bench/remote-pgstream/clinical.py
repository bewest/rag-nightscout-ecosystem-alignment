"""Reuse the existing selected clinical/output oracle on the SUT only."""
import json
import time
from protocol import need, write
import adapter as a

def completion_source(d,m):
    config=a.document(d/'completion-source.json')
    if m.get('remoteNativeObserver'):
        native=config.get('native')
        expected={'kind':'evaluator-work-v2','pair':m['pair'],'imageId':m['imageId'],
                  'instrument':m['instrument']['sha256']}
        need(isinstance(native,dict) and native.get('kind')=='compact-native-v1',
             'REMOTE_NATIVE_COMPLETION_SOURCE_REQUIRED')
        digest=a.hashlib.sha256(json.dumps(native,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        need(config.get('binding')=={**expected,'nativeConfigurationSha256':digest},
             'REMOTE_NATIVE_COMPLETION_BINDING')
    return config


def completed(d, m, maximum=120):
    from viewer_plan import counts
    roster=a.document(d/'tenants.private.json');assigned=counts(m,roster)
    bindings=[];expected_sockets={}
    for tenant,count in assigned.items():
        expected_sockets[tenant]=list(range(len(bindings),len(bindings)+count))
        for _ in range(count):bindings.append(tenant)
    probe=a.document(d/'load/probe.json')
    witnesses=probe.get('clientWitnesses')
    need(isinstance(witnesses,list) and 1<=len(witnesses)<=100000 and all(w.get('acked') is True for w in witnesses),'REMOTE_CLINICAL_CLIENT_WITNESS_REQUIRED')
    for w in witnesses:
        clients=w.get('clients');need(w.get('tenant') in assigned and isinstance(clients,list) and len(clients)==assigned[w['tenant']] and len({c.get('socket') for c in clients})==len(clients) and all(type(c.get('socket')) is int and 0<=c['socket']<len(bindings) and bindings[c['socket']]==w['tenant'] for c in clients),'REMOTE_CLINICAL_VIEWER_BINDING')
    ids=sorted({w['tenant'] for w in witnesses})
    need(set(ids)<=set(row['id'] for row in a.document(d/'tenants.private.json')),'REMOTE_CLINICAL_TENANT_SCOPE')
    config=completion_source(d,m)
    if m.get('remoteNativeObserver'):
        witnesses=[{**w,'expectedSockets':expected_sockets[w['tenant']],'clientProofVersion':2} for w in witnesses]
    marker=(d/'load/runid').read_text().strip()
    script="const o=require(process.argv[1]);const s=JSON.parse(require('fs').readFileSync(0));console.log(JSON.stringify(s.mode==='query'?o.query(s.config,s.ids,s.marker):s.witnesses.map(w=>o.assess(s.rows.find(r=>r.tenant===w.tenant),w,w.clients,s.expected[w.tenant],s.config))));"
    def node(value):return json.loads(a.command(['node','-e',script,a.HERE/'completed-oracle.cjs'],input=json.dumps(value).encode(),timeout=20))
    query=node(dict(mode='query',config=config,ids=ids,marker=marker))
    deadline=time.monotonic()+maximum
    stamps={}
    while True:
        until=time.time()+max(1,deadline-time.monotonic()) if m.get('remoteNativeObserver') else None
        with a.command_deadline(until):
            rows=[json.loads(line) for line in a.psql(d,query,a.application_database(d)).splitlines() if line]
        by_id={row['tenant']:row for row in rows}
        for tenant,row in by_id.items():
            if tenant not in stamps:stamps[tenant]=row['stamp']
        selected=[{**w,'stamp':stamps.get(w['tenant'])} for w in witnesses]
        assessed=node(dict(mode='assess',expected=assigned,rows=rows,witnesses=selected,config=config))
        evidence={'verdict':'PASS' if all(r.get('ready') is True for r in assessed) else 'UNMEASURED',
                  'scope':'selected stored marker, durable output/frame and BG-now mean/last plus actual already-connected clients; remaining clinical properties unassessed',
                  'observer':'SUT-only after steady SQL/cgroup bookend; no cross-host latency',
                  'clientFrames':{'verdict':('PASS' if all(r.get('ready') is True for r in assessed) else 'UNMEASURED') if any(assigned[w['tenant']] for w in witnesses) else 'NOT_EXERCISED'},'witnesses':assessed,'selectedTenantCount':len(ids),'rosterTenants':m['tenants'],
                  'writeToEvaluationMs':'UNMEASURED','dueOpportunity':'UNMEASURED','reconnect':'UNMEASURED'}
        write(d/'completed-output.json',evidence)
        write(d/'completed-output.private.json',{'rows':rows,'clientWitnesses':selected})
        if evidence['verdict']=='PASS':return evidence
        need(time.monotonic()<deadline,'REMOTE_CLINICAL_COMPLETION_UNMEASURED')
        time.sleep(1)
