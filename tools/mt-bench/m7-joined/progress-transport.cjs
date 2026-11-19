'use strict';
// Progress-only wire representation. The clinical SELECT and both strict
// assessors remain in completed-oracle. Every independent progress predicate
// survives this positional projection; only constant reader metadata and JSON
// field names are omitted. The SQL is still one source-bound SELECT snapshot.
const oracle=require('./completed-oracle.cjs');
const TYPED=['version','contractDigest','observed','completed','identity','digest','revision','generation','enabled','arrayBounds','dueAt','completedAt','pendingAt','bodyMetadataAbsent'];
const STATE=['kind','observed','completed'];
const OUTPUT=['tenant','identity','contentDigest','outputRevision','restoreGeneration'];
const fail=()=>{throw Error('M7_OPPORTUNITY_TRANSPORT');};
function query(config,ids){
 const c=oracle.prepare(config),sql=oracle.progressQuery(c,ids);
 const fields=(base,keys)=>'jsonb_build_array('+keys.map(k=>base+"->'"+k+"'").join(',')+')';
 const typed=fields("r->'typed'",[...TYPED,...(c.native?['inputFloor']:[])]);
 const output="CASE WHEN jsonb_typeof(r->'state'->'output')='object' THEN "+fields("r->'state'->'output'",OUTPUT)+" ELSE r->'state'->'output' END";
 const state=fields("r->'state'",STATE).replace(/\)$/,','+output+')');
 return `SELECT jsonb_build_array(r->'tenant',r->'stamp',${typed},${state}${c.native?",r->'native'":''})::text FROM (SELECT body::jsonb AS r FROM (${sql.replace(/;$/, '')}) source(body)) progress;`;
}
function object(value,keys){
 if(!Array.isArray(value)||value.length!==keys.length)fail();
 return Object.fromEntries(keys.map((key,i)=>[key,value[i]]));
}
function snapshot(rows,config,ids){
 const c=oracle.prepare(config);
 if(!Array.isArray(rows))fail();
 const expanded=rows.map(value=>{
  if(!Array.isArray(value)||value.length!==(c.native?5:4))fail();
  const [tenant,stamp,typed,state,native]=value;
  if(!Array.isArray(state)||state.length!==4)fail();
  return {tenant,stamp,reader:c.binding,typed:object(typed,[...TYPED,...(c.native?['inputFloor']:[])]),
   state:{...object(state.slice(0,3),STATE),output:state[3]===null?null:object(state[3],OUTPUT)},
   ...(c.native?{native}:{})};
 });
 return oracle.progressSnapshot(expanded,c,ids);
}
module.exports={query,snapshot};
