"use strict";
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),o=require('./client-delivery.cjs');
const doc={_id:'synthetic-id',date:1,sgv:123},witness={clientProofVersion:2,expectedSockets:[7,9],sentMono:10};
const clients=[7,9].map(socket=>({socket,connects:1,transportId:'synthetic-'+socket,atMono:20,sgv:{_id:doc._id,mills:doc.date,mgdl:doc.sgv}}));
const green=()=>assert.equal(o.assess(clients,2,doc,witness).ready,true);
test('actual content on each expected viewer can arrive after reconnect',()=>{
 green();const reconnected=clients.map(c=>({...c,connects:2,transportId:c.transportId+'-new'}));
 assert.deepEqual(o.assess(reconnected,2,doc,witness),{ready:true,viewers:2,reconnectedViewers:2,proof:'exact-viewer-callback-v2'});green();
});
for(const [label,change,code] of [
 ['missing viewer',c=>c.pop(),'COUNT'],['duplicate viewer',c=>c[1].socket=7,'VIEWER'],['foreign viewer',c=>c[1].socket=8,'BINDING'],
 ['wrong stored identity',c=>c[1].sgv._id='other','CONTENT'],['wrong glucose',c=>c[1].sgv.mgdl=124,'CONTENT'],['wrong time',c=>c[1].sgv.mills=2,'CONTENT'],
 ['missing incarnation',c=>delete c[1].transportId,'INCARNATION'],['never connected',c=>c[1].connects=0,'INCARNATION'],
 ['callback before request',c=>c[1].atMono=9,'CLOCK'],['missing monotonic clock',c=>delete c[1].atMono,'CLOCK']
])test(label+' refuses; restoration passes',()=>{const bad=structuredClone(clients);change(bad);assert.equal(o.assess(bad,2,doc,witness).code,'M7_CLIENT_'+code);green();});
test('a late callback is a timing, judged by assessor.py, not refused here',()=>{
 const late=structuredClone(clients);late[1].atMono=500000;assert.equal(o.assess(late,2,doc,witness).ready,true);
});
test('meaningful content-validator ablation makes wrong-content criterion fail',()=>{
 const source=fs.readFileSync(require.resolve('./client-delivery.cjs'),'utf8');
 const target="c.sgv?.mgdl!==doc.sgv";assert.equal(source.split(target).length,2);
 const mod={exports:{}};Function('module',source.replace(target,'false'))(mod);
 const bad=structuredClone(clients);bad[1].sgv.mgdl=999;
 const rejects=api=>assert.equal(api.assess(bad,2,doc,witness).code,'M7_CLIENT_CONTENT');
 rejects(o);assert.throws(()=>rejects(mod.exports),assert.AssertionError);rejects(o);green();
});
