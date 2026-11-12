// PATH-ONLY REDACTED DERIVATIVE, NOT ANOTHER EXECUTION. Original SHA256: 2e605729b9a40baa1626b95851ca832a3b65839171ab335a0ba040a4065068c8
'use strict';
const fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),assert=require('node:assert/strict');
const root='<CORE_SOURCE>',dependencies=fs.realpathSync('<DEPENDENCY_NODE_MODULES>'),resolved=new Set(),original=Module._resolveFilename;
Module._resolveFilename=function(request,parent,...rest){const found=original.call(this,request,parent,...rest);if(!Module.isBuiltin(found)){const actual=fs.realpathSync(found);if(!(actual.startsWith(root+'/')||actual.startsWith(dependencies+'/')))throw Error('UNAUTHORIZED_MODULE_RESOLUTION:'+actual);resolved.add(actual);}return found;};
const clock=require(root+'/tests/lib/views-replay/clock'),environment=require(root+'/lib/server/tenant-app/environment'),evaluator=require(root+'/lib/data/tenant-projection-evaluator');
require(root+'/lib/storage/tenant-scope').setTenancyMode('multi');
const observations=[],at=Date.UTC(2026,10,12,12);let reads=0;
async function run(value){
 const catalogue=require(root+'/lib/tenant-settings/catalogue');const effective=Object.fromEntries(Object.entries(catalogue.DEFAULTS).map(([key,value])=>[key,{value}]));const env=environment({settings:catalogue.project(effective)});assert.deepEqual(env.settings.enable,environment({settings:{}}).settings.enable);const document={_id:'synthetic-reading-'+(value===123?0:1),type:'sgv',sgv:value,date:at-1000,dateString:new Date(at-1000).toISOString(),direction:'Flat',device:'synthetic-compose-demo',srvModified:at};
 const replay={async reconcile(){reads++;return {checkpoint:at,rows:[{domain:'entries',document}]};}};
 const component=evaluator({tenant:'11111111-1111-4111-8111-111111111111',replay,connection:{async query(){throw Error('NO_SQL_PERMITTED')}},env,language:require(root+'/lib/language')(),dbstats:async()=>({dataSize:0,indexSize:0}),maxRows:10,maxBytes:1048576});
 for(const delta of [0,60000,180000,480000,598999,599000,599001]){
  const instant=at+delta;clock.pin(instant);const result=delta===0?await component.evaluate({at:instant}):await component.evaluateTime({at:instant});
  observations.push({sgv:value,deltaMs:delta,result,dueInMs:result.due.dueAt===null?null:result.due.dueAt-instant});
  if(delta===0){assert.equal(result.properties.bgnow.mean,value);assert.equal(result.due.dueAt-at,599000);assert.equal(result.due.reason,'sgv-recent-10');assert.deepEqual(result.due.slow,[]);assert.deepEqual(result.requested,[]);}
 }
 component.close();
}
clock.install();Promise.resolve().then(async()=>{try{await run(123);await run(177);assert.equal(reads,2);const result={kind:'PURE_ACTUAL_CLINICAL_PROJECTION_AND_NEXT_DUE',coreCommit:'47b43b6246ce7f94f1f1f0d01830495a78b28add',localNode:process.version,localKernel:require('node:os').release(),settingsPreparation:'actual catalogue.DEFAULTS -> catalogue.project -> environment; enable equal registry blank-settings environment',syntheticAt:at,readAcquisitions:reads,sqlCalls:0,observations,dependencyResolutionPaths:[...resolved].sort(),dependencyRoot:dependencies,sourceOverlay:root,limitations:'No server/runtime scheduler/SQL/containers; evaluateTime called explicitly at selected synthetic instants, not evidence of naturally scheduled TIME completion. Historical authorized exact-lock dependencies, no new install.'};fs.writeFileSync(path.join(__dirname,'full-projection-defaults-confirmed.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});console.log(JSON.stringify({cases:observations.length,acquisitions:reads,initial:observations.filter(x=>x.deltaMs===0).map(x=>({sgv:x.sgv,due:x.result.due,dueInMs:x.dueInMs,requested:x.result.requested})),dependencyFiles:resolved.size}));}finally{clock.uninstall();}}).catch(error=>{console.error(error.stack);process.exitCode=1;});
