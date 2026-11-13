'use strict';
// Smoke instrumentation only: execute the tracked k6 payload functions under
// deterministic HTTP/Counter mocks, then native smoke sends those payloads to
// its own tiny HTTP->PostgreSQL fixture. This does not simulate k6 scheduling.
const fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const exchanged=crypto.randomUUID();
const [sourceFile,tenantsFile]=process.argv.slice(2),calls=[];
const tenants=JSON.parse(fs.readFileSync(tenantsFile));
const context={sha256:value=>crypto.createHash('sha256').update(value).digest('hex'),calls,console:{log(){}},__ENV:{BASE_URL:'http://fixture.invalid',RUN_ID:'m7-smoke-run',DURATION:'1',ACCEL:'1',HOT_FACTOR:'1',TENANTS_FILE:tenantsFile,RUN_START:'1800000000000',SETTINGS_FINGERPRINT:process.env.M7_FIXTURE_FINGERPRINT,SHAPES:'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'},
  open:()=>JSON.stringify(tenants),exec:{scenario:{iterationInTest:0}},Counter:class{constructor(name){this.name=name;}add(value){calls.push({counter:this.name,value});}},
  http:{expectedStatuses:()=>()=>true,get(url,options){calls.push({method:'GET',url,options});return {status:process.env.M7_FIXTURE_REFUSE_READS==='1' && !url.includes('/authorization/request/')?403:200,body:url.includes('/status.json') && process.env.M7_FIXTURE_STATUS ? fs.readFileSync(process.env.M7_FIXTURE_STATUS,'utf8') : JSON.stringify({token:exchanged})};},post(url,body,options){calls.push({method:'POST',url,body:JSON.parse(body),options});return {status:200};}}};
vm.createContext(context);
let source=fs.readFileSync(sourceFile,'utf8').replace(/^import .*;$/gm,'').replace(/export (const|function) /g,'$1 ');
source+='\nconst fixtureData=setup();for(let index=0;index<TENANTS.length;index++){exec.scenario.iterationInTest=index;w_sgv();w_devicestatus();w_treatments_v3(fixtureData);r_sgv();r_devicestatus();r_treatments();r_status();}';
vm.runInContext(source,context,{timeout:2000});
process.stdout.write(JSON.stringify(calls));
