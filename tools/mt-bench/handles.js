const WORK=process.env.MTBENCH_WORK||require('os').tmpdir()+'/mt-bench';require('fs').mkdirSync(WORK,{recursive:true});
const {mkTenant}=require('./gen');const BS=require('better-sqlite3');const fs=require('fs');
const dir=WORK+'/tenants';fs.rmSync(dir,{recursive:true,force:true});fs.mkdirSync(dir,{recursive:true});
const t=mkTenant();const K=parseInt(process.env.K||'1000');
console.log('creating',K,'tenant DBs...');
const s0=Date.now();
for(let i=0;i<K;i++){const d=new BS(`${dir}/t${i}.db`);d.pragma('journal_mode=WAL');
 d.exec("CREATE TABLE entries(id TEXT PRIMARY KEY,mills INTEGER,doc TEXT);");
 const st=d.prepare('INSERT INTO entries VALUES(?,?,?)');
 d.transaction(()=>t.sgvs.forEach((e,j)=>st.run(String(j),e.mills,JSON.stringify(e))))();d.close();}
console.log('created in',((Date.now()-s0)/1000).toFixed(1),'s; disk',(fs.readdirSync(dir).reduce((a,f)=>a+fs.statSync(dir+'/'+f).size,0)/1048576).toFixed(0),'MB');
// cold open + query latency
function pct(a,p){a=a.slice().sort((x,y)=>x-y);return a[Math.floor(a.length*p)];}
const lat=[];const open=[];
const m0=process.memoryUsage();
for(let i=0;i<K;i++){const a=process.hrtime.bigint();const d=new BS(`${dir}/t${i}.db`,{readonly:true});const b=process.hrtime.bigint();
  d.prepare('SELECT doc FROM entries WHERE mills > ? ORDER BY mills DESC').all(0);const c=process.hrtime.bigint();
  open.push(Number(b-a)/1e6);lat.push(Number(c-b)/1e6);d.close();}
console.log(`cold open  p50 ${pct(open,.5).toFixed(2)}ms p99 ${pct(open,.99).toFixed(2)}ms`);
console.log(`first query p50 ${pct(lat,.5).toFixed(2)}ms p99 ${pct(lat,.99).toFixed(2)}ms`);
// hold all handles open simultaneously
const held=[];let failed=null;
try{for(let i=0;i<K;i++)held.push(new BS(`${dir}/t${i}.db`,{readonly:true}));}catch(e){failed=e.message;}
const m1=process.memoryUsage();
console.log('simultaneously open handles:',held.length,failed?('FAILED: '+failed):'(no failure)');
console.log('RSS delta holding handles:',((m1.rss-m0.rss)/1048576).toFixed(1),'MB =>',(((m1.rss-m0.rss)/held.length)/1024).toFixed(1),'KB/open tenant');
held.forEach(h=>h.close());
