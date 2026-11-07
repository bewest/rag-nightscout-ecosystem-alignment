'use strict';
// RECORDED-EVIDENCE only. Replays committed synthetic observations against pinned
// physical oracles and reads app git objects; never runs DB, Docker or app jobs.
const fs=require('node:fs'),path=require('node:path');
const {REPO_ROOT,CRM,report}=require('./_gate');
const schema=require('./_m5-runtime-recorded/schema.cjs'),validate=require('./_m5-runtime-recorded/validate.cjs');
const args=process.argv.slice(2),option=name=>args.includes(name)?args[args.indexOf(name)+1]:null;
const bundle=path.join(REPO_ROOT,'reports/tenancy/m5-runtime-2026-11-07/postgres');
const findings=[];
try{
 const planFile=path.join(bundle,'plan.json'),plan=JSON.parse(fs.readFileSync(planFile)),file=option('--projection')||path.join(bundle,'projection.json');
 const value=JSON.parse(fs.readFileSync(file));schema.ensure(value.planSha256===schema.sha(fs.readFileSync(planFile)),'RECORDED_PLAN_HASH');
 const control=option('--control');
 if(control){
  if(control==='physical')value.phases.find(p=>p.id==='restored').observations.lifecycle.find(r=>r.phase==='preview-time-acquired').acquired.result.properties.bgnow.mean=222;
  else if(control==='missing-phase')value.phases=value.phases.filter(p=>p.id!=='notification-suppression');
  else if(control==='wrong-source')value.phases[0].head='0'.repeat(40);
  else if(control==='no-restoration')value.phases=value.phases.filter(p=>p.id!=='restored');
  else throw new Error('Unknown authored control');
  // Reach semantic predicates: deliberately rehash the corrupted private copy.
  value.projectionSha256=schema.documentHash(value);
 }
 const result=validate(value,plan,{repo:process.env.NS_M5_RECORDED_REPO||CRM,toolDir:path.join(__dirname,'_m5-runtime-recorded')});
 findings.push({ok:true,text:JSON.stringify(result)});
}catch(error){findings.push({ok:false,text:error.message});}
report('m5-runtime RECORDED-EVIDENCE (not fresh native execution)',findings);
