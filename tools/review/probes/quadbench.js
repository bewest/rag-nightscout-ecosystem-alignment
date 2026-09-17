// usage: node quadbench.js <repo-root>
const root = process.argv[2];
const ddata = require(root + '/lib/data/ddata')();
const calcDelta = require(root + '/lib/data/calcdelta');
function mkTreatments(n){
  const base = Date.now() - n*300000;
  const out=[];
  for(let i=0;i<n;i++){
    out.push({ _id:'7000000000000000'+String(100000+i),
      eventType:'Temp Basal', mills: base+i*300000, duration: 30, absolute: 0.8+ (i%10)/10,
      enteredBy:'openaps://AndroidAPS' });
  }
  return out;
}
for (const n of [500, 2000, 5000]) {
  const t = mkTreatments(n);
  let t0=process.hrtime.bigint();
  ddata.processDurations(JSON.parse(JSON.stringify(t)), false);
  const pd = Number(process.hrtime.bigint()-t0)/1e6;

  const oldD = {treatments: JSON.parse(JSON.stringify(t)), sgvs:[], mbgs:[], cals:[], food:[], devicestatus:[], profiles:[], activity:[]};
  const newD = {treatments: JSON.parse(JSON.stringify(t)), sgvs:[], mbgs:[], cals:[], food:[], devicestatus:[], profiles:[], activity:[]};
  newD.treatments[n-1] = Object.assign({}, newD.treatments[n-1], {absolute: 9.9});
  t0=process.hrtime.bigint();
  const d = calcDelta(oldD, newD);
  const cd = Number(process.hrtime.bigint()-t0)/1e6;
  console.log(`${root.split('/').pop()}  n=${n}  processDurations=${pd.toFixed(1)} ms  calcDelta=${cd.toFixed(1)} ms  deltaTreatments=${(d.treatments||[]).length}`);
}
