const http=require('http');const SEC=require('crypto').createHash('sha1').update(process.env.NS_HARNESS_SECRET||(()=>{throw new Error('set NS_HARNESS_SECRET')})()).digest('hex');
function get(port,path){return new Promise((res)=>{const t0=process.hrtime.bigint();
 const r=http.request({host:'127.0.0.1',port,path,method:'GET',headers:{'api-secret':SEC}},x=>{let n=0,b='';x.on('data',c=>{n+=c.length;b+=c});x.on('end',()=>{const t1=process.hrtime.bigint();res([Number(t1-t0)/1e6,x.statusCode,n,b])})});r.end();});}
(async()=>{const port=Number(process.argv[2]);const path=process.argv[3]||'/api/v1/entries.json?count=10';
 let r=await get(port,path); console.log('first:',r[0].toFixed(3),'ms http',r[1],'bytes',r[2],'ndocs',(()=>{try{return JSON.parse(r[3]).length}catch(e){return 'n/a'}})());
 for(let i=0;i<50;i++) await get(port,path); // warm
 const s=[];for(let i=0;i<300;i++){s.push((await get(port,path))[0]);}
 s.sort((a,b)=>a-b);
 const mean=s.reduce((a,b)=>a+b,0)/s.length;
 console.log(`port ${port} ${path}  n=300 mean=${mean.toFixed(3)}ms p50=${s[150].toFixed(3)} p95=${s[285].toFixed(3)} min=${s[0].toFixed(3)}`);
})();
