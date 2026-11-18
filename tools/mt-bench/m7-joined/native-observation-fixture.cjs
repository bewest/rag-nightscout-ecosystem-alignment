"use strict";
const {createHash}=require('node:crypto'),oracle=require('./completed-oracle.cjs');
const tenant='11111111-1111-4111-8111-111111111111',doc={_id:'synthetic-native',date:123456789,sgv:123},sgv={_id:doc._id,mills:doc.date,mgdl:doc.sgv};
const evaluator={pgstream:{generation:'a'.repeat(32),slot:'synthetic_slot',recovery:{connectionEnv:'NS_SYNTHETIC_SOURCE'}},consumer:'evaluator-sample',trustedWorker:{activity:'synthetic_control'},postgres:{namespaces:{clock:'synthetic_clock',checkpoint:'synthetic_checkpoint',entries:'synthetic_entries'}}};
const realtime={completedOutput:{namespace:'synthetic_checkpoint',consumer:'evaluator-sample'}};
const binding={kind:'evaluator-work-v2',pair:{core:'1'.repeat(40),deploy:'2'.repeat(40)},imageId:'sha256:'+'3'.repeat(64),instrument:'4'.repeat(64)};
const config=oracle.source(evaluator,realtime,binding),source={system_id:'12345',timeline:1,database:'synthetic_test',slot:'synthetic_slot'};
const witness={tenant,date:doc.date,stamp:'9007199254740993',clientProofVersion:2,sentMono:10,expectedSockets:[7,9]};
const clients=[7,9].map(socket=>({socket,connects:2,transportId:'transport-'+socket,atMono:20,sgv}));
const map={bootstrap:'2'},vector=[null,null,null,null,null,'2'];
const row={tenant,stamp:witness.stamp,reader:config.binding,stored:[doc],native:{kind:'clinical-stream-v2',compact:true,inputFloor:'2',persistedFloor:'2',currentRestore:'1',phase:'active',stream:{source_identity:source,generation:'a'.repeat(32)+':1',snapshot_position:'0/100',accepted_position:'0/200'},actualSource:source,raw:{kind:'storage-events-v1',head:'4',base:'2'}},
 typed:{version:2,contractDigest:createHash('sha256').update(JSON.stringify(['evaluator-work-v2','synthetic_checkpoint','evaluator-sample'])).digest('hex'),observed:vector,completed:vector,identity:'5'.repeat(64),digest:'6'.repeat(64),revision:'1',generation:'1',inputFloor:'2',enabled:true,arrayBounds:true,bodyMetadataAbsent:true,pendingAt:null,dueAt:'10000',completedAt:'9000'},
 state:{kind:'evaluator-work-v2',observed:map,completed:map,output:{tenant,identity:'5'.repeat(64),contentDigest:'6'.repeat(64),outputRevision:1,restoreGeneration:'1',inputCheckpoint:1,result:{checkpoint:1,properties:{bgnow:{mean:123,last:123,mills:doc.date,sgvs:[sgv]}}},frame:{sgvs:[sgv]}}}};
module.exports={config,row,witness,clients,evaluator,realtime,binding};
