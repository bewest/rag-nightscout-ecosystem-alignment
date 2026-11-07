'use strict';
// One bounded recorded M5 package, two explicitly attributed measurements.
// No native execution or global/current application HEAD acceptance.
const fs=require('node:fs'),path=require('node:path');
const {REPO_ROOT,CRM,report}=require('./_gate');
const args=process.argv.slice(2),option=n=>args.includes(n)?args[args.indexOf(n)+1]:null;
const repo=option('--repo')||process.env.NS_M5_RECORDED_REPO||CRM,deps=option('--deps')||process.env.NS_M5_RECORDED_DEPS;
const findings=[];
for(const [name,tools]of [['postgres','_m5-runtime-recorded'],['roles','_m5-roles-recorded']]){
 try{
  const bundle=path.join(REPO_ROOT,'reports/tenancy/m5-runtime-2026-11-07',name),planFile=path.join(bundle,'plan.json'),validator=path.join(__dirname,tools,'validate.cjs');
  if(!fs.existsSync(planFile)||!fs.existsSync(validator))throw new Error('NO-INSTRUMENT: separate reviewed '+name+' record must be joined');
  const planBytes=fs.readFileSync(planFile),plan=JSON.parse(planBytes),file=path.join(bundle,'projection.json');
  if(name==='roles'&&(!deps||!fs.existsSync(path.join(deps,'mongodb/package.json'))))throw new Error('NO-INSTRUMENT: explicit installed app dependencies required');
  const result=require(validator)(JSON.parse(fs.readFileSync(file)),plan,{repo,deps,planBytes,toolDir:path.join(__dirname,tools)});findings.push({ok:true,text:name+': '+JSON.stringify(result)});
 }catch(error){findings.push({ok:false,text:name+': '+error.message});}
}
report('M5 bounded batch RECORDED-EVIDENCE (separate actual sources; not fresh execution)',findings);
