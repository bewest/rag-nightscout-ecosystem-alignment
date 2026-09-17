const tree=process.argv[2];
const ddata=require(tree+'/lib/data/ddata')();
function mk(n){const out=[];const t0=Date.parse('2026-09-10T00:00:00Z');
 for(let i=0;i<n;i++){out.push({_id:'t'+i,eventType:'Temp Basal',mills:t0+i*5*60*1000,duration:30,absolute:0.8});}
 return out;}
const a=mk(Number(process.argv[3]||500));
const r=ddata.processDurations(a,false);
const cut=r.filter(x=>x.cutting!==undefined).length, cby=r.filter(x=>x.cuttedby!==undefined).length;
console.log(tree.split('/').pop(), 'n_out='+r.length, 'withCutting='+cut, 'withCuttedby='+cby, 'sha='+require('crypto').createHash('sha1').update(JSON.stringify(r)).digest('hex').slice(0,12));
