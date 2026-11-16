'use strict';
// Actual generated selector + actual client writer, using captured discovery env.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{const source=fs.readFileSync(process.argv[2],'utf8'),env=JSON.parse(process.argv[3]),signalDir=path.resolve(process.argv[4]);
 const start=source.indexOf('const clinicalTimeline=discovery&&');assert(start>=0);const end=source.indexOf('\n',start);const code=source.slice(start,end);let exit;
 const context={discovery:true,signalDir,JSON,process:{env,once(name,fn){assert.equal(name,'exit');exit=fn;}},require(name){assert.equal(name,'./clinical-timeline-client.cjs');return require(name);}};vm.runInNewContext(code+'\nglobalThis.tap=clinicalTimeline;',context);
 if(!context.tap){console.log(JSON.stringify({active:false,scope:'actual generated selector, absent discovery env'}));return;}
 const ids=JSON.parse(env.M7_CLINICAL_TIMELINE_IDS);context.tap.record('writer-ack',ids[0],{date:2,sent:1,acked:3});context.tap.record('first-matching-frame',ids[0],{date:2,sent:1,received:4});while(context.tap.status().pending)await new Promise(r=>setImmediate(r));exit();
 assert.equal(JSON.parse(fs.readFileSync(path.join(signalDir,'clinical-client-1.json'))).phase,'writer-ack');assert.equal(JSON.parse(fs.readFileSync(path.join(signalDir,'clinical-client-2.json'))).phase,'first-matching-frame');console.log(JSON.stringify({active:true,rows:context.tap.status().written,scope:'actual generated selector/client writer with captured discovery Popen environment'}));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
