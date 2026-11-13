'use strict';
const assert=require('node:assert/strict'),{EventEmitter}=require('node:events');
const {create}=require('./client.cjs');const HTTP=require('./http-budget.cjs');
const ids=Array.from({length:16},(_,i)=>'00000000-0000-4000-8000-'+i.toString(16).padStart(12,'0'));
const endpoint={origin:'http://10.250.228.2:1337',cid:'a'.repeat(64),startedAt:'synthetic'};
const spec={version:1,kind:'native-clinical-http-client',ids,runId:'m7-native-'+'a'.repeat(16),nonce:'b'.repeat(32),endpoints:Object.fromEntries(['api','api-2','admin','socket-edge'].map(k=>[k,endpoint])),credentials:ids.map((id,i)=>({id,host:'t'+i+'.example.test',dataToken:'not-a-credential',rootHash:'not-a-hash'})),maximumRequests:8192,maximumSockets:16,maximumHttpBytes:268435456,maximumWallMs:1200000};
(async()=>{
 const saved={},calls=[];let pendingResolve;const c=create(spec,{prime:{request:async(origin,route,options)=>{calls.push({origin,route});assert(saved['ledger-entries.json'].byTenant[ids[0]].pending===1);return {status:201,body:{}};}},io(){throw Error('unexpected network constructor');},persist:(name,value)=>{saved[name]=JSON.parse(JSON.stringify(value));}});
 const r=await c.write(ids[0],'entries');assert.equal(r.status,201);assert.equal(saved['http-receipts-0001.json'][0].status,201);assert.equal(saved['ledger-entries.json'].byTenant[ids[0]].accepted,1);assert.equal(saved['ledger-entries.json'].byTenant[ids[0]].pending,0);c.close();assert.equal(saved['ledger-entries.json'].admissionsClosed,true);await assert.rejects(()=>c.write(ids[0],'entries'),/CLIENT_CLOSED/);assert.equal(calls.length,1);
 const http={request(){const req=new EventEmitter();req.destroy=()=>{};return req;}};const original=http.request,budget=HTTP.install(http,{maximumRequests:1,maximumResponseBytes:2});const request=http.request();const response=new EventEmitter();response.destroy=()=>{};request.emit('response',response);response.emit('data',Buffer.from('abc'));assert.equal(budget.snapshot().refused,true);assert.throws(()=>http.request(),/CLIENT_HTTP_BUDGET/);budget.restore();assert.equal(http.request,original);
 assert.throws(()=>create({...spec,ids:ids.slice(0,8)},{prime:{},io(){},persist(){}}),/CLIENT_ROSTER/);
 console.log(JSON.stringify({scope:'pure recording ports only; no HTTP/socket/network',write201PreservedAndAccepted:true,persistBeforeHTTP:true,closedAdmissionRefused:true,totalHTTPByteBoundRefused:true,completeRosterRefused:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
