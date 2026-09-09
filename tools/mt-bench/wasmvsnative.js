const WORK=process.env.MTBENCH_WORK||require('os').tmpdir()+'/mt-bench';require('fs').mkdirSync(WORK,{recursive:true});
const {mkTenant}=require('./gen');const fs=require('fs');
const t=mkTenant();
const rows={entries:t.sgvs,treatments:t.treatments,devicestatus:t.devicestatus};
function bench(name,fn,iters=30){fn();const s=process.hrtime.bigint();for(let i=0;i<iters;i++)fn();const e=process.hrtime.bigint();console.log(name.padEnd(50),(Number(e-s)/1e6/iters).toFixed(2)+' ms');}
(async()=>{
// native better-sqlite3
const BS=require('better-sqlite3');
try{fs.unlinkSync(WORK+'/bs.db')}catch{}
const nd=new BS(WORK+'/bs.db');
nd.exec("PRAGMA journal_mode=WAL; CREATE TABLE entries(id TEXT PRIMARY KEY,mills INTEGER,doc TEXT);CREATE TABLE treatments(id TEXT PRIMARY KEY,mills INTEGER,doc TEXT);CREATE TABLE devicestatus(id TEXT PRIMARY KEY,mills INTEGER,doc TEXT);");
for(const k of Object.keys(rows)){const st=nd.prepare(`INSERT INTO ${k}(id,mills,doc) VALUES(?,?,?)`);nd.transaction(()=>rows[k].forEach((d,i)=>st.run(String(i),d.mills,JSON.stringify(d))))();}
const ns={};for(const k of Object.keys(rows))ns[k]=nd.prepare(`SELECT doc FROM ${k} WHERE mills > ? ORDER BY mills DESC`);
bench('better-sqlite3 warm: 3 scans + JSON.parse',()=>Object.fromEntries(Object.keys(ns).map(k=>[k,ns[k].all(0).map(r=>JSON.parse(r.doc))])));
bench('better-sqlite3 warm: 3 scans, no parse',()=>Object.fromEntries(Object.keys(ns).map(k=>[k,ns[k].all(0)])));

// sqlite-wasm (in-memory / OPFS-less node usage)
const sqlite3InitModule=require('@sqlite.org/sqlite-wasm').default||require('@sqlite.org/sqlite-wasm');
const sqlite3=await sqlite3InitModule({print:()=>{},printErr:()=>{}});
const wd=new sqlite3.oo1.DB('/w.db','ct');
wd.exec("CREATE TABLE entries(id TEXT PRIMARY KEY,mills INTEGER,doc TEXT);CREATE TABLE treatments(id TEXT PRIMARY KEY,mills INTEGER,doc TEXT);CREATE TABLE devicestatus(id TEXT PRIMARY KEY,mills INTEGER,doc TEXT);");
wd.exec('BEGIN');
for(const k of Object.keys(rows)){const st=wd.prepare(`INSERT INTO ${k}(id,mills,doc) VALUES(?,?,?)`);for(const [i,d] of rows[k].entries()){st.bind([String(i),d.mills,JSON.stringify(d)]).stepReset();}st.finalize();}
wd.exec('COMMIT');
bench('sqlite-WASM warm: 3 scans + JSON.parse',()=>{const o={};for(const k of Object.keys(rows)){const a=[];wd.exec({sql:`SELECT doc FROM ${k} WHERE mills > 0 ORDER BY mills DESC`,rowMode:'array',callback:(r)=>{a.push(JSON.parse(r[0]))}});o[k]=a;}return o;});
bench('sqlite-WASM warm: 3 scans, no parse',()=>{const o={};for(const k of Object.keys(rows)){const a=[];wd.exec({sql:`SELECT doc FROM ${k} WHERE mills > 0 ORDER BY mills DESC`,rowMode:'array',callback:(r)=>{a.push(r[0])}});o[k]=a;}return o;});
console.log('sqlite-wasm version',sqlite3.version.libVersion);
})();
