const root = process.argv[2];
const ddata = require(root + '/lib/data/ddata')();
const BASE_T = 1750000000000;   // fixed epoch, no Date.now()
function mk(n, seed){
  const out=[]; let s = seed;
  const rnd = () => (s = (s*1103515245+12345) & 0x7fffffff) / 0x7fffffff;
  for(let i=0;i<n;i++){
    out.push({ _id:'7000000000000000'+String(100000+i),
      eventType: rnd()<0.08?'Profile Switch':'Temp Basal', profile: 'P'+(i%3),
      mills: BASE_T + i*300000 + Math.floor(rnd()*120000),
      duration: [15,30,45,60,90][Math.floor(rnd()*5)],
      absolute: 0.8+(i%10)/10 });
  }
  return out;
}
const t = mk(1200, 7);
const r = ddata.processDurations(JSON.parse(JSON.stringify(t)), true);
console.log(JSON.stringify(r));
