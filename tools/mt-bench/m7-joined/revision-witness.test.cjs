'use strict';
const assert=require('node:assert/strict'),w=require('./revision-witness.cjs');
const tenant='11111111-1111-4111-8111-111111111111',owner='a'.repeat(32),source='b'.repeat(40),target={tenant,storedId:'synthetic-row-a'},socket=w.digest('socket-a'),payloadDigest=w.digest(['dataUpdate',{sgvs:[{_id:target.storedId}]}]);
function fixture(){let n=0n;const tap=w.create({owner,source,targets:[target],persist(){},clock:()=>++n});tap.record('acquisition',tenant,{outputRevision:'7',inputCheckpoint:'12'});tap.record('emit',tenant,{outputRevision:'7',socket,payloadDigest,fifo:1});tap.record('engine-arrival',tenant,{socket,payloadDigest,fifo:1,incarnation:1,transport:'polling'});tap.record('stock-callback',tenant,{socket,payloadDigest,fifo:1,incarnation:1,transport:'polling'});return tap.state();}
const pass=fixture();assert.equal(w.correlate([pass]).verdict,'PASS');
let controls=0;
function refuse(change){const state=structuredClone(pass);change(state);assert.equal(w.correlate([state]).verdict,'UNMEASURED');controls++;}
refuse(s=>{s.owner='c'.repeat(32);});refuse(s=>{s.source='c'.repeat(40);});refuse(s=>{s.clockDomain='wall-clock';});refuse(s=>{s.events[2].monoNs='wall-clock';});refuse(s=>{s.events[2].socket=w.digest('other');});refuse(s=>{s.events[1].outputRevision='8';});refuse(s=>{s.events[3].incarnation=2;});refuse(s=>{s.events.splice(2,1);});refuse(s=>{s.events.push(s.events[1]);});refuse(s=>{s.events[2].monoNs='9999999';});refuse(s=>{s.events.push(s.events[3]);});refuse(s=>{s.dropped=1;s.qualification='UNMEASURED';});
// Same input position does not collapse different output revisions or stored rows.
const duplicatePosition=fixture();duplicatePosition.events[0].inputCheckpoint='12';const unrelated={...duplicatePosition.events[0],storedId:'synthetic-row-b',outputRevision:'8'};duplicatePosition.events.unshift(unrelated);assert.equal(w.correlate([duplicatePosition]).joins[0].outputRevision,'7');
// Collection file order is irrelevant; timestamps/identity define ordering.
const shuffled=fixture();shuffled.events.reverse();assert.equal(w.correlate([shuffled]).verdict,'PASS');
// Independent clock origins may differ arbitrarily; only same-instance pairs are subtracted.
const a=fixture(),b=fixture();a.events=a.events.slice(0,2);b.instance='other';b.events=b.events.slice(2).map(e=>({...e,instance:'other',monoNs:String(BigInt(e.monoNs)+999999999n)}));const joined=w.correlate([a,b]);assert.equal(joined.verdict,'PASS');assert.equal(joined.joins[0].emitToEngine,'UNMEASURED_CROSS_PROCESS');
const saturated=w.create({owner,source,targets:[target],persist(){},maxEvents:1});saturated.record('acquisition',tenant,{});saturated.record('acquisition',tenant,{});assert.equal(saturated.state().qualification,'UNMEASURED');
const io=w.create({owner,source,targets:[target],persist(){throw Error('SECRET');}});io.record('acquisition',tenant,{});assert.equal(io.state().qualification,'UNMEASURED');assert(!JSON.stringify(io.state()).includes('SECRET'));
assert.equal(w.correlate([fixture()]).verdict,'PASS');console.log(JSON.stringify({status:'PASS',controls,restored:'PASS',scope:'pure correlation; native forwarding qualified separately'}));
