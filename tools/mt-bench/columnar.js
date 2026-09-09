const {mkTenant}=require('./gen');
const t=mkTenant();const N=t.sgvs.length;
const mills=new Float64Array(N),sgv=new Int32Array(N),delta=new Float32Array(N),dir=new Uint8Array(N);
t.sgvs.forEach((e,i)=>{mills[i]=e.mills;sgv[i]=e.sgv;delta[i]=e.delta;dir[i]=4;});
const blob=Buffer.concat([Buffer.from(mills.buffer),Buffer.from(sgv.buffer),Buffer.from(delta.buffer),Buffer.from(dir.buffer)]);
const jbuf=Buffer.from(JSON.stringify(t.sgvs));
function total(){const m=process.memoryUsage();return (m.heapUsed+m.external)/1048576;}
function measure(label,f,K){global.gc();const b=total();const keep=[];for(let i=0;i<K;i++)keep.push(f());global.gc();const a=total();console.log(label.padEnd(34),((a-b)).toFixed(1),'MB total =>',(((a-b)/K)*1024).toFixed(1),'KB/tenant');return keep;}
const K=200;
const A=measure('objects (JSON.parse)',()=>JSON.parse(jbuf),K);
const B=measure('columnar (typed arrays)',()=>{const c=Buffer.from(blob);return {m:new Float64Array(c.buffer,c.byteOffset,N),s:new Int32Array(c.buffer,c.byteOffset+N*8,N)};},K);
console.log('sanity: blob',(blob.length/1024).toFixed(1),'KB, json',(jbuf.length/1024).toFixed(1),'KB, live refs',A.length,B.length);
