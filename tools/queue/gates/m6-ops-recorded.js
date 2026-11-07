'use strict';
// Reads recorded synthetic evidence and pinned app objects only. No services.
const fs=require('node:fs'),path=require('node:path'),{REPO_ROOT,CRM,report}=require('./_gate');
const s=require('./_m6-ops-recorded/schema.cjs'),validate=require('./_m6-ops-recorded/validate.cjs');
const arg=name=>{const i=process.argv.indexOf(name);return i<0?null:process.argv[i+1];},findings=[];
try{const home=path.join(REPO_ROOT,'reports/tenancy/m6-ops-2026-11-07/postgres'),planBytes=fs.readFileSync(path.join(home,'plan.json')),plan=JSON.parse(planBytes),value=JSON.parse(fs.readFileSync(arg('--projection')||path.join(home,'projection.json')));s.ensure(value.planSha256===s.sha(planBytes),'M6_PLAN_HASH');const control=arg('--control');
 const changeRows=(stage,name,table,mutate)=>{const e=value.phases.find(p=>p.id===stage).observations.find(o=>o.phase===name),frame=structuredClone(value.dictionaries.frames[e.value.frame]),rows=structuredClone(value.dictionaries.rowSets[frame[table].rows]);mutate(rows);const rh=s.sha(s.canonical(rows));value.dictionaries.rowSets[rh]=rows;frame[table].rows=rh;const fh=s.sha(s.canonical(frame));value.dictionaries.frames[fh]=frame;e.value.frame=fh;};
 if(control){if(control==='physical'){const phase=value.phases.find(p=>p.id==='final'),frame=phase.observations.find(e=>e.phase==='C1-restored-before-verdict').value.frame,table=value.dictionaries.frames[frame]['entries.entries'],rows=structuredClone(value.dictionaries.rowSets[table.rows]);rows[0].doc.sgv=222;const h=s.sha(s.canonical(rows));value.dictionaries.rowSets[h]=rows;const changed=structuredClone(value.dictionaries.frames[frame]);changed['entries.entries'].rows=h;const ref=s.sha(s.canonical(changed));value.dictionaries.frames[ref]=changed;phase.observations.find(e=>e.phase==='C1-restored-before-verdict').value.frame=ref;}
 else if(control==='ordinal')changeRows('final','C1-restored-before-verdict','entries.entries',rows=>{rows[0].insertion_ordinal='999';});
 else if(control==='denial-null')value.phases.find(p=>p.id==='final').observations.find(e=>e.phase==='actual-role-statement').value.count=0;
 else if(control==='denial-code')value.phases.find(p=>p.id==='final').observations.find(e=>e.phase==='actual-role-statement').value.code=null;
 else if(control==='control-row')value.phases.find(p=>p.id==='ordinary-inheritance-red').observations.find(e=>e.phase==='C5-inheritance-effects-before-verdict').value.childAfter.push({tenant_id:'11111111-1111-4111-8111-111111111111',descendant_only:'controlled'});
 else if(control==='secret-material')changeRows('initial','C1-source-before-verdict','secrets.secret_records',rows=>{rows[0].ciphertext='must-remain-opaque';});
 else if(control==='missing-control')value.phases=value.phases.filter(p=>p.id!=='ordinary-inheritance-red');
 else if(control==='wrong-source')value.nativeHead='0'.repeat(40);
 else if(control==='no-restoration')value.phases=value.phases.filter(p=>p.id!=='final');
 else if(control==='audit-non-zombie')value.births.find(b=>plan.births[b.id].terminalException).driver.state='S';
 else if(control==='coordinated-command'){const b=value.births.find(b=>!plan.births[b.id].terminalException);b.driver.commandSha256=b.independent.commandSha256='f'.repeat(64);}
 else if(control==='overclaim')value.scope.wholeM6Acceptance=true;
 else if(control==='private-path')value.dictionaries.rowSets[Object.keys(value.dictionaries.rowSets)[0]][0].privatePath='/tmp/private-capture';
 else throw Error('Unknown authored control');value.projectionSha256=s.documentHash(value);}
 findings.push({ok:true,text:JSON.stringify(validate(value,plan,{repo:process.env.NS_M6_OPS_RECORDED_REPO||CRM,toolDir:path.join(__dirname,'_m6-ops-recorded')}))});
}catch(error){findings.push({ok:false,text:error.message});}report('m6-ops RECORDED-EVIDENCE (no fresh native execution)',findings);
