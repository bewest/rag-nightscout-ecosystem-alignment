'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const binding=path.resolve(process.argv[2]),state=path.resolve(process.argv[3]),{verdict}=require(path.join(binding,'bindings/compose/multitenant/fixtures/clinical-effect-oracle.cjs'));
const data=JSON.parse(fs.readFileSync(path.join(state,'artifacts/clinical-dedup-classification.json'))),causes=JSON.parse(fs.readFileSync(path.join(state,'artifacts/clinical-origin-cause-match.json')));
const rows=data.clinicalWindow.map(row=>({...row,clear:row.kind==='clear',effectDigest:row.payloadDigest}));
const [a,b]=['11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222'],first=[a,b].map(tenant=>rows.filter(row=>row.tenant===tenant).sort((x,y)=>x.created-y.created)[0]);
function input(after){return{a,b,first,after,deadlines:new Map(first.map(row=>[row.tenant,row.created+60000])),now:Math.max(...rows.map(row=>row.created))+1500,fanout:new Map([a,b].map(tenant=>[tenant,after.filter(row=>row.tenant===tenant).map(row=>row.effectDigest)]))};}
assert.throws(()=>verdict(input(rows)),/A_IDENTICAL_EFFECT_MUST_NOT_REPEAT_EARLY/);
const duplicateIds=new Set(causes.flatMap(row=>row.matchedRequests.map(match=>match.request))),counterfactual=rows.filter(row=>!duplicateIds.has(row.request));assert.equal(verdict(input(counterfactual)).acceptedNormals,3);
console.log(JSON.stringify({originalTypedRows:'rejected-identical-A-early-effect',removedOnlyExactRepeatNullOrigins:duplicateIds.size,counterfactualTypedRows:'accepted-three-intentional-effects',scope:'metadata-only oracle counterfactual; synthetic fanout digest projection, not runtime acceptance'}));
