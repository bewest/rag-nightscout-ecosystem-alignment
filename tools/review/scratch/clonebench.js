// Cost of ctx.cache.getData('entries') (deep clone) vs getDataRef (slice),
// at the 48h retention the entries cache actually holds.
function mkEntry(i){
  const t = Date.now() - i*300000;
  return { _id: (0x600000000000000000000000 + i).toString(16).padStart(24,'0'),
    device: 'xDrip-DexcomG6', date: t, dateString: new Date(t).toISOString(),
    sgv: 100 + (i%80), delta: 0.5, direction: 'Flat', type: 'sgv',
    filtered: 123456, unfiltered: 123456, rssi: 100, noise: 1,
    sysTime: new Date(t).toISOString(), utcOffset: -300, mills: t };
}
for (const n of [576, 1152, 2304]) {
  const arr = Array.from({length:n}, (_,i)=>mkEntry(i));
  // warm
  for(let k=0;k<20;k++){ JSON.parse(JSON.stringify(arr)); arr.slice(); }
  let t0=process.hrtime.bigint();
  for(let k=0;k<200;k++) JSON.parse(JSON.stringify(arr));
  let deep=Number(process.hrtime.bigint()-t0)/200/1e6;
  t0=process.hrtime.bigint();
  for(let k=0;k<200;k++) arr.slice();
  let ref=Number(process.hrtime.bigint()-t0)/200/1e6;
  console.log(`n=${n}  getData(deep clone)=${deep.toFixed(3)} ms   getDataRef(slice)=${ref.toFixed(4)} ms   ratio=${(deep/ref).toFixed(0)}x`);
}
