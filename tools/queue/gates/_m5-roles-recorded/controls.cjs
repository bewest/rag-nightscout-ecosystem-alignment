'use strict';
// Offline sensitivity controls. Never modify committed observations or run DB.
const {ensure,canonical,sha,documentHash}=require('./schema.cjs');
const definitions={
 'missing-phase':{expected:'ROLE_EXACT_PHASE_COVERAGE',mutate:d=>d.phases.shift()},
 'no-restoration':{expected:'ROLE_EXACT_PHASE_COVERAGE',mutate:d=>{d.phases=d.phases.filter(p=>p.kind!=='restored');}},
 'wrong-source':{expected:'ROLE_PHASE_SOURCE',mutate:d=>{d.phases[0].head='0'.repeat(40);}},
 'forced-cleanup':{expected:'ROLE_PHASE_CLEANUP',mutate:d=>{d.phases[0].cleanup.forced=true;}},
 'retry-control-green':{expected:'INVALID_CONTROL_PHYSICAL_ORACLE',mutate:d=>{const r=at(d,'control-actual-retry-fresh-uuid','actual-consumer-handoff.json');r.retryPhysical.retry.id=r.retryPhysical.first.id;}},
 'cold-clear-control-green':{expected:'INVALID_CONTROL_PHYSICAL_ORACLE',mutate:d=>{const p=at(d,'control-omit-cold-control-clear-intent','actual-consumer-handoff.json').coldAckPhysical,e=p.producer.producer.effects.find(x=>x.payload.clear);p.rows.push({request_id:'ffffffff-ffff-4fff-8fff-ffffffffffff',origin:e.origin,payload:e.payload});}},
 'plugin-control-green':{expected:'INVALID_CONTROL_PHYSICAL_ORACLE',mutate:d=>{const r=at(d,'control-actual-plugin-admission','actual-plugin-ack.json');r.immediately=structuredClone(r.beforeOwner);}},
 'socket-epoch-control-green':{expected:'INVALID_CONTROL_PHYSICAL_ORACLE',mutate:d=>{at(d,'control-actual-socket-epoch','actual-socket-epoch.json').find(x=>x.kind==='main-reauthorization').protectedEvents=[];}},
 'config-epoch-control-green':{expected:'INVALID_CONTROL_PHYSICAL_ORACLE',mutate:d=>{at(d,'control-actual-config-epoch','actual-socket-epoch.json').find(x=>x.kind==='operator-tightening').protectedEvents=[];}},
 'storage-control-green':{expected:'INVALID_CONTROL_PHYSICAL_ORACLE',mutate:d=>{for(const c of at(d,'control-omit-storage-current-collection-filter','actual-storage-proof.json').STORAGE_CURRENT_COLLECTION_REVOKED.clients)c.events=[];}},
 'browser-ui':{expected:'ORDINARY_PHYSICAL_ORACLE_FAILED',mutate:d=>{at(d,'restored-joined-browser-consumer','actual-browser-consumer.json').result.urgentUi=false;}},
 'data-timestamp':{expected:'ORDINARY_PHYSICAL_ORACLE_FAILED',mutate:d=>{at(d,'restored-joined-data-parity','socket-data-physical-parity.json').find(x=>x.logical==='entries').mongoRaw[0].created_at='1970-01-01T00:00:00.000Z';}},
 'unknown-credential-field':{expected:'ROLE_UNREVIEWED_RAW_FIELD',mutate:d=>{at(d,'restored-joined-browser-consumer','actual-browser-consumer.json').accessToken='synthetic-refused-credential';}}
};
function at(doc,id,file){const p=doc.phases.find(x=>x.id===id);ensure(p,'CONTROL_PHASE_REQUIRED');return p.observations[file];}
function corrupt(original,id){const c=definitions[id];ensure(c,'Unknown authored role gate control');const d=structuredClone(original);c.mutate(d);
 // Rehash both projection layers to reach physical predicates, not hash alarms.
 for(const p of d.phases)for(const [file,value]of Object.entries(p.observations))p.provenance[file].projectedSha256=sha(canonical(value));
 d.projectionSha256=documentHash(d);return d;
}
module.exports={definitions,corrupt};
