// Reproduces the two O(old x new) hot spots from cgm-remote-monitor and their Map-indexed fix.
// idMergePreferNew: lib/data/ddata.js:82-106 ; nsArrayTreatments: lib/data/calcdelta.js:15-76
const {mkTenant}=require('./gen');
const t=mkTenant();
const old=t.treatments, fresh=JSON.parse(JSON.stringify(t.treatments)).slice(0,3); // typical incremental: a few new docs
function bench(name,fn,iters=200){fn();const s=process.hrtime.bigint();for(let i=0;i<iters;i++)fn();const e=process.hrtime.bigint();console.log(name.padEnd(52),(Number(e-s)/1e6/iters).toFixed(3)+' ms');}

// --- current shape: nested scan
function idMergePreferNew(oldData,newData){
  const merged=JSON.parse(JSON.stringify(newData));
  for(const o of oldData){let found=false;
    for(const n of newData){ if((o._id&&n._id&&o._id===n._id)||(o.identifier&&n.identifier&&o.identifier===n.identifier)){found=true;break;} }
    if(!found) merged.push(o);}
  return merged;
}
// --- Map-indexed
function idMergeIndexed(oldData,newData){
  const keys=new Set();
  for(const n of newData){ if(n._id)keys.add('i:'+n._id); if(n.identifier)keys.add('d:'+n.identifier); }
  const merged=newData.slice();
  for(const o of oldData){ if(!((o._id&&keys.has('i:'+o._id))||(o.identifier&&keys.has('d:'+o.identifier)))) merged.push(o); }
  return merged;
}
bench('idMergePreferNew: nested scan (current shape)',()=>idMergePreferNew(old,fresh));
bench('idMergePreferNew: Map/Set indexed',()=>idMergeIndexed(old,fresh));

// delta: every new item scanned against every old item
const oldD=t.treatments, newD=t.treatments.map((x,i)=>i%50===0?{...x,insulin:1}:x);
function deltaNested(o,n){const out=[];for(const x of n){let m=null;for(const y of o){if(y._id===x._id){m=y;break;}}if(!m)out.push(x);else if(JSON.stringify(m)!==JSON.stringify(x))out.push({...x,action:'update'});}return out;}
function deltaIndexed(o,n){const ix=new Map();for(const y of o)ix.set(y._id,y);const out=[];for(const x of n){const m=ix.get(x._id);if(!m)out.push(x);else if(JSON.stringify(m)!==JSON.stringify(x))out.push({...x,action:'update'});}return out;}
bench('calcdelta treatments: nested scan',()=>deltaNested(oldD,newD),50);
bench('calcdelta treatments: Map indexed',()=>deltaIndexed(oldD,newD),50);

// scaling: what happens at 5000 treatments (heavy/long-history tenant)?
const big=Array.from({length:5000},(_,i)=>({_id:String(i).padStart(24,'0'),mills:i,eventType:'Bolus',insulin:1}));
const bigNew=big.map((x,i)=>i%100===0?{...x,insulin:2}:x);
bench('nested scan @5000 treatments',()=>deltaNested(big,bigNew),5);
bench('Map indexed @5000 treatments',()=>deltaIndexed(big,bigNew),5);
