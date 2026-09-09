const WORK=process.env.MTBENCH_WORK||require('os').tmpdir()+'/mt-bench';require('fs').mkdirSync(WORK,{recursive:true});
const {mkTenant}=require('./gen');const v8=require('v8');const {DatabaseSync}=require('node:sqlite');const fs=require('fs');
const t=mkTenant();
const json=JSON.stringify(t); const v8buf=v8.serialize(t);
fs.writeFileSync(WORK+'/t.json',json); fs.writeFileSync(WORK+'/t.v8',v8buf);
// build sqlite tenant db (documents-as-JSON rows, the realistic port)
try{fs.unlinkSync(WORK+'/t.db')}catch{}
const db=new DatabaseSync(WORK+'/t.db');
db.exec("PRAGMA journal_mode=WAL; CREATE TABLE entries(id TEXT PRIMARY KEY, mills INTEGER, doc TEXT); CREATE INDEX ix_e ON entries(mills); CREATE TABLE treatments(id TEXT PRIMARY KEY, mills INTEGER, doc TEXT); CREATE TABLE devicestatus(id TEXT PRIMARY KEY, mills INTEGER, doc TEXT);");
function fill(tbl,arr){const st=db.prepare(`INSERT INTO ${tbl}(id,mills,doc) VALUES(?,?,?)`);arr.forEach((d,i)=>st.run(String(i),d.mills,JSON.stringify(d)));}
db.exec('BEGIN');fill('entries',t.sgvs);fill('treatments',t.treatments);fill('devicestatus',t.devicestatus);db.exec('COMMIT');
db.close();
function bench(name,fn,iters=50){fn();const s=process.hrtime.bigint();for(let i=0;i<iters;i++)fn();const e=process.hrtime.bigint();console.log(name.padEnd(46),(Number(e-s)/1e6/iters).toFixed(2)+' ms');}
const jsonBuf=fs.readFileSync(WORK+'/t.json');const v8b=fs.readFileSync(WORK+'/t.v8');
bench('JSON.parse snapshot (795KB, cache/redis path)',()=>JSON.parse(jsonBuf));
bench('v8.deserialize snapshot',()=>v8.deserialize(v8b));
bench('sqlite open + 3 range scans + JSON.parse rows',()=>{const d=new DatabaseSync(WORK+'/t.db',{readOnly:true});const q=(tb)=>d.prepare(`SELECT doc FROM ${tb} WHERE mills > ? ORDER BY mills DESC`).all(0).map(r=>JSON.parse(r.doc));const o={sgvs:q('entries'),treatments:q('treatments'),devicestatus:q('devicestatus')};d.close();return o;});
const dbOpen=new DatabaseSync(WORK+'/t.db',{readOnly:true});
const stmts={e:dbOpen.prepare('SELECT doc FROM entries WHERE mills > ? ORDER BY mills DESC'),t:dbOpen.prepare('SELECT doc FROM treatments WHERE mills > ? ORDER BY mills DESC'),d:dbOpen.prepare('SELECT doc FROM devicestatus WHERE mills > ? ORDER BY mills DESC')};
bench('sqlite warm handle + prepared + JSON.parse rows',()=>({sgvs:stmts.e.all(0).map(r=>JSON.parse(r.doc)),treatments:stmts.t.all(0).map(r=>JSON.parse(r.doc)),devicestatus:stmts.d.all(0).map(r=>JSON.parse(r.doc))}));
bench('sqlite warm handle, rows only (no JSON.parse)',()=>({a:stmts.e.all(0),b:stmts.t.all(0),c:stmts.d.all(0)}));
bench('structuredClone of live ddata',()=>structuredClone(t));
bench('current JSON clone (processRawDataForRuntime)',()=>JSON.parse(JSON.stringify(t)));
console.log('snapshot sizes: json',(json.length/1024|0)+'KB','v8',(v8buf.length/1024|0)+'KB','sqlite',(fs.statSync(WORK+'/t.db').size/1024|0)+'KB');
