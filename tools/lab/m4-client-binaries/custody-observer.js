'use strict';
// M4-specific durable receipt validation, not the broad full/browser schema.
const assert=require('node:assert/strict');
const {identity,baselineIdentity,volumeIdentity,digest,PROFILE}=require('./custody');
function admitCreated (entry, row, baseline) {
  assert(entry && entry.type==='created-identified' && entry.value && typeof entry.owner==='string','M4_CREATED_RECEIPT_REQUIRED');
  const record=entry.value;assert(/^[a-f0-9]{64}$/.test(record.id),'M4_CREATED_FULL_ID');
  assert(row.State && row.State.Status==='created' && row.State.Running===false && row.State.StartedAt.startsWith('0001-') && row.State.FinishedAt.startsWith('0001-'),'M4_CREATED_NOT_STOPPED');
  assert(!baseline.containers.includes(record.id) && row.Id===record.id && digest(identity(row))===digest(record.identity),'M4_CREATED_IDENTITY_MISMATCH');
  assert(record.volumes.every(v=>!baseline.volumes.includes(v.name)),'M4_BASELINE_VOLUME');
  return {owner:entry.owner,id:record.id,identity:digest(record.identity)};
}
function normalize (entries, {owner,baseline,supervisor,run} = {}) {
  assert(supervisor?.phase==='m4-clients' && supervisor.hostProcessesClosed===true && supervisor.directChildrenReaped===true &&
    supervisor.processAudit?.unknownAdopted?.length===0 && supervisor.processAudit.lastReadback?.readbackComplete===true &&
    supervisor.processAudit.freshReadbackWithinBudget===true && supervisor.processAudit.terminalReceiptFailures?.length===0 &&
    supervisor.processAudit.lastReadback.knownPresent?.length===0 && supervisor.processAudit.lastReadback.unknownAdopted?.length===0,
  'M4_HOST_CUSTODY_INCOMPLETE');
  assert(entries.length && entries[0].type==='namespace-absent' && entries[0].value.profile===PROFILE,'M4_NAMESPACE_RECEIPT_REQUIRED');
  const prefix='m4-'+owner.replace(/-/g,'').slice(0,12);
  const names=['postgres','mongo','vault'].map(kind=>prefix+'-'+kind).concat(Array.from({length:64},(_,i)=>prefix+'-client-'+String(i).padStart(3,'0')));
  assert(digest(entries[0].value.names)===digest(names) && entries[0].value.baseline===digest(baseline),'M4_NAMESPACE_BINDING');
  const uninspected=new Map(),created=new Map(),intent=new Set(),admitted=new Set(),starts=new Set(),removed=new Set(),volumeRemoved=new Set(),started=new Set(),exited=new Set();let closed=false;
  for(const [index,entry] of entries.entries()){
    assert(entry.sequence===index+1 && entry.owner===owner && !closed,'M4_JOURNAL_SEQUENCE');const r=entry.value;
    if(entry.type==='create-intent'){assert(names.includes(r.name) && !intent.has(r.name),'M4_DUPLICATE_INTENT');intent.add(r.name);}
    if(entry.type==='created-uninspected'){assert(intent.has(r.name) && /^[a-f0-9]{64}$/.test(r.id) && !baseline.containers.includes(r.id) && !uninspected.has(r.name),'M4_UNOWNED_CREATED_ID');uninspected.set(r.name,r.id);}
    if(entry.type==='created-identified'){assert(uninspected.get(r.name)===r.id && intent.has(r.name) && !created.has(r.id) && !baseline.containers.includes(r.id) && r.volumes.every(v=>!baseline.volumes.includes(v.name)),'M4_UNOWNED_IDENTIFIED_ID');created.set(r.id,r);}
    if(['start-intent','started','client-exited','remove-intent','container-absent'].includes(entry.type))assert(created.has(r.id),'M4_UNJOURNALED_EFFECT');
    if(entry.type==='observer-admitted'){assert(created.has(r.id) && r.identity===digest(created.get(r.id).identity),'M4_OBSERVER_RECEIPT_MISMATCH');admitted.add(r.id);}
    if(entry.type==='start-intent'){assert(admitted.has(r.id) && !starts.has(r.id) && !removed.has(r.id),'M4_UNOBSERVED_START');starts.add(r.id);}
    if(entry.type==='started'){assert(starts.has(r.id) && !started.has(r.id) && !removed.has(r.id),'M4_START_INTENT_REQUIRED');started.add(r.id);}
    if(entry.type==='client-exited'){assert(created.get(r.id).kind==='client' && starts.has(r.id) && !exited.has(r.id) && !removed.has(r.id) && Number.isInteger(r.exit),'M4_CLIENT_EXIT_MISSING');exited.add(r.id);}
    if(entry.type==='container-absent')removed.add(r.id);
    if(entry.type==='volume-absent')volumeRemoved.add(r.name);
    if(entry.type==='closed'){assert(intent.size===created.size && removed.size===created.size && [...created.values()].every(record=>record.volumes.every(v=>volumeRemoved.has(v.name))),'M4_UNCLOSED_CREATION');closed=true;}
  }
  assert(closed,'M4_CLEANUP_RECEIPT_REQUIRED');
  const staticKinds=[...created.values()].filter(r=>r.kind!=='client');assert(staticKinds.every(r=>['postgres','mongo','vault'].includes(r.kind)) && new Set(staticKinds.map(r=>r.kind)).size===staticKinds.length,'M4_STATIC_SERVICES');
  assert([...created.values()].filter(r=>r.kind==='client').length<=64,'M4_CLIENT_BOUND');
  if(run){assert(staticKinds.length===3 && [...created.values()].some(r=>r.kind==='client') && run.clients.slice().sort().join(',')==='cgmsim,oref0' && staticKinds.every(r=>started.has(r.id)) &&
    [...created.values()].filter(r=>r.kind==='client').every(r=>exited.has(r.id)),'M4_RUN_START_OR_EXIT_OMITTED');}
  return [...created.values()];
}
module.exports={admitCreated,normalize,baselineIdentity,volumeIdentity};

// The finite parent invokes this M4-specific observer independently of the lab.
// Only durable created-identified receipts authorize a fresh inspect; no names
// or later absence grant resource ownership. Inspect JSON never reaches disk.
function observe ({plan,directory,invoke,append}) {
  const fs=require('node:fs'),path=require('node:path');
  const seen=new Set();let sequence=0;
  const write=append || (entry=>durable(path.join(directory,'observer.jsonl'),JSON.stringify(entry)+'\n',true));
  function scan () {
    const file=path.join(directory,'custody.jsonl');if(!fs.existsSync(file))return;
    const text=fs.readFileSync(file,'utf8');assert(Buffer.byteLength(text)<=2*1024*1024,'M4_OBSERVER_JOURNAL_BOUND');
    const lines=text.split('\n');lines.pop();
    for(let index=sequence;index<lines.length;index++){
      const entry=JSON.parse(lines[index]);assert(entry.sequence===index+1 && entry.owner===plan.ownerUUID,'M4_OBSERVER_SEQUENCE');
      if(entry.type==='created-identified'){
        const r=entry.value;assert(/^[a-f0-9]{64}$/.test(r.id),'M4_CREATED_FULL_ID');assert(!seen.has(r.id),'M4_OBSERVER_DUPLICATE');
        const rows=JSON.parse(invoke(['inspect','--type','container',r.id]));assert(rows.length===1,'M4_OBSERVER_EXACT_INSPECT');
        const receipt=admitCreated(entry,rows[0],plan.baseline);
        for(const v of r.volumes){const values=JSON.parse(invoke(['volume','inspect',v.name]));assert(values.length===1 && digest(volumeIdentity(values[0]))===digest(v),'M4_OBSERVER_VOLUME_MISMATCH');}
        // A failed durable write prevents the receipt and therefore start.
        write({sequence:seen.size+1,type:'independently-identified',...receipt,volumes:r.volumes});
        durable(path.join(directory,'receipts',r.id+'.json'),JSON.stringify(receipt)+'\n',false);
        seen.add(r.id);
      }
      sequence=index+1;
    }
  }
  return Object.freeze({scan,identified:()=>[...seen]});
}
function durable (file,text,append) {
  const fs=require('node:fs');const fd=fs.openSync(file,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_NOFOLLOW|
    (append?fs.constants.O_APPEND:fs.constants.O_EXCL),0o600);
  try {const bytes=Buffer.from(text);assert.equal(fs.writeSync(fd,bytes),bytes.length);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
}
function inventory (invoke) {
  const ids={};
  for(const [kind,args,cap] of [['containers',['ps','-aq','--no-trunc'],256],['volumes',['volume','ls','-q'],1024],['networks',['network','ls','--no-trunc','-q'],64]]){
    const values=invoke(args).trim().split('\n').filter(Boolean);assert(values.length<=cap && new Set(values).size===values.length,'M4_BASELINE_CAP_OR_DUPLICATE');
    assert(values.every(v=>kind==='volumes'?/^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/.test(v):/^[a-f0-9]{64}$/.test(v)),'M4_BASELINE_FULL_ID');ids[kind]=values.sort();
  }return ids;
}
function baselineSnapshot (invoke) {
  const ids=inventory(invoke),identities={};
  for(const kind of ['containers','volumes','networks']){
    identities[kind]={};
    for(let offset=0;offset<ids[kind].length;offset+=32){
      const batch=ids[kind].slice(offset,offset+32),args=kind==='containers'?['inspect','--type','container',...batch]:[kind==='volumes'?'volume':'network','inspect',...batch];
      assert(Buffer.byteLength(args.join('\0'))<=131072,'M4_BASELINE_ARGV_BOUND');const rows=JSON.parse(invoke(args));
      const actual=rows.map(r=>kind==='volumes'?r.Name:r.Id);assert(actual.length===batch.length && new Set(actual).size===batch.length && digest(actual.slice().sort())===digest(batch),'M4_BASELINE_EXACT_BATCH');
      for(const row of rows){const key=kind==='volumes'?row.Name:row.Id;identities[kind][key]=kind==='containers'?baselineIdentity(row):kind==='volumes'?volumeIdentity(row):{id:row.Id,fingerprint:digest(row)};}
    }
  }
  return {ids,identities,endpointProfile:'stable-network-settings-v1'};
}
function verifyBaseline (invoke,expected) {
  assert(expected.endpointProfile==='stable-network-settings-v1','M4_BASELINE_PROFILE');const actual=baselineSnapshot(invoke);
  assert(digest(actual)===digest(expected),'M4_BASELINE_CHANGED');return actual;
}
module.exports.observe=observe;
module.exports.baselineSnapshot=baselineSnapshot;
module.exports.verifyBaseline=verifyBaseline;
