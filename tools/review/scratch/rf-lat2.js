const http=require('http');const SEC=require('crypto').createHash('sha1').update(process.env.NS_HARNESS_SECRET||(()=>{throw new Error('set NS_HARNESS_SECRET')})()).digest('hex');
function get(port,path){return new Promise((res)=>{const t0=process.hrtime.bigint();
 const r=http.request({host:'127.0.0.1',port,path,method:'GET',headers:{'api-secret':SEC},agent:false},x=>{let n=0;x.on('data',c=>{n+=c.length});x.on('end',()=>{res(Number(process.hrtime.bigint()-t0)/1e6)})});r.end();});}
(async()=>{const P='/api/v1/entries.json?count=10';
 for(let i=0;i<100;i++){await get(1481,P);await get(1483,P);}
 const A=[],B=[];
 for(let i=0;i<400;i++){A.push(await get(1481,P));B.push(await get(1483,P));}
 const st=a=>{a=a.slice().sort((x,y)=>x-y);return `mean=${(a.reduce((x,y)=>x+y,0)/a.length).toFixed(3)} p50=${a[a.length>>1].toFixed(3)} min=${a[0].toFixed(3)}`};
 console.log('BASE  1481',st(A));console.log('CACHE 1483',st(B));
 const ma=A.slice().sort((x,y)=>x-y)[200], mb=B.slice().sort((x,y)=>x-y)[200];
 console.log('p50 ratio BASE/CACHE =',(ma/mb).toFixed(2));
})();
