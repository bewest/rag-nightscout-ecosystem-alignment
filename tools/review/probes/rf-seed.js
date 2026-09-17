const http=require('http');
const SEC=require('crypto').createHash('sha1').update(process.env.NS_HARNESS_SECRET||(()=>{throw new Error('set NS_HARNESS_SECRET')})()).digest('hex');
function post(port,path,body){return new Promise((res,rej)=>{const d=JSON.stringify(body);
 const r=http.request({host:'127.0.0.1',port,path,method:'POST',headers:{'Content-Type':'application/json','Content-Length':Buffer.byteLength(d),'api-secret':SEC}},x=>{let b='';x.on('data',c=>b+=c);x.on('end',()=>res([x.statusCode,b.length]))});r.on('error',rej);r.write(d);r.end();});}
(async()=>{
 const port=Number(process.argv[2]);
 const now=Date.now(); const N=1152; const e=[];
 for(let i=0;i<N;i++){const t=now-(N-i)*5*60*1000;
  e.push({type:'sgv',sgv:Math.round(120+40*Math.sin(i/24)),date:t,dateString:new Date(t).toISOString(),device:'synthetic://refute',direction:'Flat'});}
 console.log('entries',await post(port,'/api/v1/entries.json',e));
 const tr=[];
 for(let i=0;i<300;i++){const t=now-(300-i)*10*60*1000;
  tr.push({eventType:'Temp Basal',created_at:new Date(t).toISOString(),absolute:0.8,duration:30,enteredBy:'synthetic://refute'});}
 console.log('treat',await post(port,'/api/v1/treatments.json',tr));
 const prof=[{defaultProfile:'Default',startDate:'2026-01-01T00:00:00.000Z',mills:1767225600000,units:'mg/dl',store:{Default:{dia:'5',carbratio:[{time:'00:00',value:'10',timeAsSeconds:0}],sens:[{time:'00:00',value:'50',timeAsSeconds:0}],basal:[{time:'00:00',value:'0.8',timeAsSeconds:0}],target_low:[{time:'00:00',value:'100',timeAsSeconds:0}],target_high:[{time:'00:00',value:'120',timeAsSeconds:0}],timezone:'UTC',startDate:'1970-01-01T00:00:00.000Z',carbs_hr:'20',delay:'20'}}}];
 console.log('profile',await post(port,'/api/v1/profile',prof));
})();
