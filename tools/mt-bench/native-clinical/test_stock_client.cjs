'use strict';
// Recording stock API ports: no sockets, DNS, HTTP or other resource calls.
const assert=require('node:assert/strict'),{EventEmitter}=require('node:events'),{create}=require('./client.cjs');
const ids=Array.from({length:16},(_,i)=>'00000000-0000-4000-8000-'+i.toString(16).padStart(12,'0'));
const Stock=require('/tmp/ns-m7-owned-dependencies-20261112/node_modules/socket.io-client');
const endpoint={origin:'http://10.250.228.2:1337',cid:'a'.repeat(64),startedAt:'synthetic'};
function spec(){return{version:1,kind:'native-clinical-http-client',ids,runId:'m7-native-'+'a'.repeat(16),nonce:'b'.repeat(32),endpoints:Object.fromEntries(['api','api-2','admin','socket-edge'].map(k=>[k,endpoint])),credentials:ids.map((id,i)=>({id,host:'t'+i+'.example.test',dataToken:'synthetic-'+i,rootHash:'root-'+i})),maximumRequests:8192,maximumSockets:16,maximumHttpBytes:268435456,maximumWallMs:1200000};}
function harness({laterPoint=false}={}){
 let clock=100000000,warming=true,postCount=0;const sockets=[],saved={};
 class Socket extends EventEmitter{
  constructor(index,options){super();this.index=index;this.options=options;this.id='recording-'+sockets.length;this.connected=true;this.io={engine:new EventEmitter()};sockets.push(this);queueMicrotask(()=>super.emit('connect'));}
  emit(name,value){if(name==='connect_error')return Stock.Socket.prototype.emit.call(this,name,value);if(name==='authorize'){
    if(value.secret!=='root-'+this.index){queueMicrotask(()=>{this.connected=false;super.emit('disconnect','io server disconnect');});}
    else queueMicrotask(()=>this.frame(Array.from({length:288},(_,i)=>({mgdl:210+this.index,mills:clock-(288-i)*300000}))));return true;
   }return super.emit(name,value);}
  frame(points){const frame={sgvs:points};this.io.engine.emit('packet',{type:'message',data:JSON.stringify(frame)});if(this.connected)super.emit('dataUpdate',frame);}
  close(){this.connected=false;}
 }
 const client=create(spec(),{persist:(k,v)=>saved[k]=JSON.parse(JSON.stringify(v)),now:()=>clock,delay:async ms=>{clock+=ms;await Promise.resolve();},io:(url,options)=>{assert.equal(options.reconnection,false);assert.equal(options.maxPayload,1048576);return new Socket(Number(new URL(url).hostname.match(/^t(\d+)/)[1]),options);},prime:{request:async(origin,route,options)=>{
  const index=Number(options.headers.host.match(/^t(\d+)/)[1]);if(options.headers['api-secret']!=='synthetic-'+index)return{status:403,body:{}};
  if(options.method==='POST'){postCount++;for(const socket of sockets)if(socket.connected&&socket.index===index&&route.endsWith('/entries'))socket.frame([{mgdl:options.body.sgv,mills:options.body.date+(laterPoint?1000:0)}]);return{status:201,body:{}};}
  if(warming){warming=false;return{status:503,body:{error:'TENANT_WARMING'}};}return{status:200,body:[]};
 }}});return{client,sockets,saved,get postCount(){return postCount;}};
}
(async()=>{
 const h=harness();const history=await h.client.history();assert.equal(history.accepted,4608);assert.equal(h.postCount,4608);assert.equal(h.saved['ledger-entries.json'].attempts,4608);
 const storm=await h.client.firstTouchStorm();assert.equal(storm.results.length,384);assert.equal(storm.warmingReplies,1);assert.equal(storm.socketResults.length,16);assert(storm.socketResults.every(x=>x.frames>0));
 await h.client.connect(ids[0]);await h.client.connect(ids[1]);const original=h.client.socketState(ids[1]).socketId;
 for(let n=0;n<3;n++){const value=await h.client.healthyB(ids[1]);assert.equal(value.ownFrameAfterWrite,true);assert.equal(value.socketId,original);assert.equal(value.connections,1);assert.equal(value.foreignFrames,0);}
 const isolated=await h.client.isolation(ids[0],ids[1]);assert.equal(isolated.crossAuthorizationRefused,true);assert.equal(isolated.socketConnectedBeforeRefusal,true);assert.equal(isolated.socketExplicitRefusal,true);assert.equal(isolated.positiveOwnFrame,true);assert.equal(isolated.foreignFrames,0);
 const closed=h.client.close();assert(closed.socketBytes>0);assert.equal(closed.socketBudgetRefused,false);assert(h.sockets.every(x=>!x.connected));
 const mutant=harness({laterPoint:true});await mutant.client.connect(ids[0]);const unrelated=await mutant.client.healthyB(ids[0]);assert.equal(unrelated.ownFrameAfterWrite,false,'later same-value point is not the acknowledged write');mutant.client.close();
 const bytes=harness();await bytes.client.connect(ids[0]);bytes.sockets[0].io.engine.emit('packet',{data:'x'.repeat(1048577)});assert.equal(bytes.client.socketState(ids[0]).connected,false);await assert.rejects(()=>bytes.client.write(ids[0],'entries'),/CLIENT_CLOSED_OR_DEADLINE/);assert.throws(()=>bytes.client.close(),/CLIENT_SOCKET_BYTE_BUDGET/);assert.equal(bytes.saved['socket-budget.json'].socketBudgetRefused,true);assert(bytes.sockets.every(x=>!x.connected));
 console.log(JSON.stringify({scope:'recording stock API only; no network/native acceptance',history:4608,stormRequests:384,stormSockets:16,fullDayFrameAccepted:true,exactDateAndLaterPointControl:true,threeHealthyBRounds:true,explicitIsolation:true,socketByteRefusal:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
