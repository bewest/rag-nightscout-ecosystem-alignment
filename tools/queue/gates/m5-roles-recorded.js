'use strict';
// Integration/recorded gate: requires existing source objects and lock-matched
// app dependencies. Never installs, fetches, boots an app or contacts services.
const fs=require('node:fs'),path=require('node:path');
const {REPO_ROOT,CRM,report}=require('./_gate');
const args=process.argv.slice(2),option=n=>args.includes(n)?args[args.indexOf(n)+1]:null;
const bundle=path.join(REPO_ROOT,'reports/tenancy/m5-runtime-2026-11-07/roles');
const findings=[];
try{
 const planBytes=fs.readFileSync(path.join(bundle,'plan.json')),plan=JSON.parse(planBytes);
 const repo=option('--repo')||process.env.NS_M5_RECORDED_REPO||CRM,deps=option('--deps')||process.env.NS_M5_RECORDED_DEPS;
 if(!deps||!fs.existsSync(path.join(deps,'mongodb/package.json')))throw new Error('NO-INSTRUMENT: explicit existing lock-matched app mongodb dependencies required');
 if(!plan.reviewed||plan.pending.length)throw new Error('NO-INSTRUMENT: final role capsule/projection review pending');
 const file=option('--projection')||path.join(bundle,'projection.json');
 let value=JSON.parse(fs.readFileSync(file));if(option('--control'))value=require('./_m5-roles-recorded/controls.cjs').corrupt(value,option('--control'));
 const result=require('./_m5-roles-recorded/validate.cjs')(value,plan,{repo,deps,planBytes});findings.push({ok:true,text:JSON.stringify(result)});
}catch(error){findings.push({ok:false,text:error.message});}
report('m5-roles RECORDED-EVIDENCE (not fresh native execution)',findings);
