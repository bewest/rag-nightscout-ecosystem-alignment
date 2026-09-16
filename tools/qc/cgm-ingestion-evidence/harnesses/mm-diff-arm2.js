const legacy  = require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/minimed-connect-to-nightscout/transform.js');
const NC='/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/nc';
const carelink= require(NC+'/lib/sources/minimedcarelink');
const axios   = require(NC+'/node_modules/axios');
console.log = ()=>{};
const TRUE_UTC = Date.parse('2026-09-01T12:00:00.000Z');
function payload(wall, extra){
  return Object.assign({ medicalDeviceFamily:'MINIMED', currentServerTime:TRUE_UTC,
    lastMedicalDeviceDataUpdateServerTime:TRUE_UTC, sMedicalDeviceTime:wall,
    medicalDeviceBatteryLevelPercent:80, conduitBatteryLevel:60, reservoirRemainingUnits:100,
    activeInsulin:{amount:1.2}, sgs:[{kind:'SG',sg:123,datetime:wall}],
    lastSG:{sg:123}, lastSGTrend:'UP', markers:[] }, extra||{});
}
function src(){ return carelink({carelinkRegion:'eu',carelinkUsername:'x',carelinkPassword:'y',countryCode:'de'}, axios); }
const rows=[];
for (const [label, offH, wall, extra] of [
  ['ARM  UTC+2  (Berlin, CEST), no lastConduitDateTime',  2, '2026-09-01T14:00:00.000Z', {}],
  ['ARM  UTC-7  (US Pacific),   no lastConduitDateTime', -7, '2026-09-01T05:00:00.000Z', {}],
  ['ARM  UTC+5:30 rounds to +6 in legacy guess',        5.5, '2026-09-01T17:30:00.000Z', {}],
  ['CTRL UTC+0  (the shipped golden fixture)',            0, '2026-09-01T12:00:00.000Z', {}],
  ['CTRL UTC+2 WITH lastConduitDateTime +02:00',          2, '2026-09-01T14:00:00.000Z', {lastConduitDateTime:'2026-09-01T14:00:00.000+02:00'}],
]) {
  process.env.MMCONNECT_SERVER='EU';
  const L = legacy(payload(wall, extra), 10);
  const C = src().transformPayload(payload(wall, extra), {});
  const le=L.entries[0].dateString, ce=C.entries[0].dateString;
  const lc=L.devicestatus[0].pump.clock, cc=C.devicestatus[0].pump.clock;
  rows.push([label, le, ce, (Date.parse(ce)-Date.parse(le))/3600000, lc, cc, (Date.parse(cc)-Date.parse(lc))/3600000]);
}
process.stdout.write('\n');
for (const r of rows){
  process.stdout.write(r[0]+'\n');
  process.stdout.write('    entry dateString  legacy='+r[1]+'  connect='+r[2]+'   delta='+r[3]+'h '+(r[3]===0?'AGREE':'DIVERGE')+'\n');
  process.stdout.write('    pump.clock        legacy='+r[4]+'  connect='+r[5]+'   delta='+r[6]+'h '+(r[6]===0?'AGREE':'DIVERGE')+'\n\n');
}
