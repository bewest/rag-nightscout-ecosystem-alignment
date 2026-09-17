const tree=process.argv[2];
const ddata=require(tree+'/lib/data/ddata')();
function mk(n){const out=[];const t0=Date.parse('2026-09-10T00:00:00Z');
 for(let i=0;i<n;i++){
   out.push({_id:'t'+i,eventType:'Temp Basal',mills:t0+i*5*60*1000,duration:120,absolute:0.8,profile:'P'+(i%3)});
   if(i%7===0) out.push({_id:'p'+i,eventType:'Profile Switch',mills:t0+i*5*60*1000+90*1000,profile:'PS'+(i%4)});
 }
 return out;}
const a=mk(Number(process.argv[3]||200));
const r=ddata.processDurations(a,true);
const cut=r.filter(x=>x.cutting!==undefined).length, cby=r.filter(x=>x.cuttedby!==undefined).length;
console.log(tree.split('/').pop(),'n_out='+r.length,'withCutting='+cut,'withCuttedby='+cby,'sha='+require('crypto').createHash('sha1').update(JSON.stringify(r)).digest('hex').slice(0,12));
