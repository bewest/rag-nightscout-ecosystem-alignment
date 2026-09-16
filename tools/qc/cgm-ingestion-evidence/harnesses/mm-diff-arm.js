// Arm B (MiniMed): differential transform oracle, legacy 1.5.8 vs nightscout-connect.
// Pump wall clock 14:00 local, true instant 12:00Z, offset +02:00 (CEST).
const legacy  = require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/minimed-connect-to-nightscout/transform.js');
const carelink= require('/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/nc/lib/sources/minimedcarelink');
const axios   = require('/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/nc/node_modules/axios');
const TRUE_UTC = Date.parse('2026-09-01T12:00:00.000Z');   // the real instant
const WALL     = '2026-09-01T14:00:00.000Z';               // pump wall clock, mislabelled Z

function payload(extra){
  return Object.assign({
    medicalDeviceFamily: 'MINIMED',
    currentServerTime: TRUE_UTC,
    lastMedicalDeviceDataUpdateServerTime: TRUE_UTC,
    sMedicalDeviceTime: WALL,
    medicalDeviceBatteryLevelPercent: 80, conduitBatteryLevel: 60,
    reservoirRemainingUnits: 100, activeInsulin: {amount: 1.2},
    sgs: [{kind:'SG', sg:123, datetime: WALL}],
    lastSG: {sg:123}, lastSGTrend: 'UP', markers: []
  }, extra||{});
}
function src(){ return carelink({carelinkRegion:'eu', carelinkUsername:'x', carelinkPassword:'y', countryCode:'de'}, axios); }
function run(label, extra, mmserver){
  process.env.MMCONNECT_SERVER = mmserver;
  const L = legacy(payload(extra), 10);
  const C = src().transformPayload(payload(extra), {});
  const lds = L.entries[0] && L.entries[0].dateString;
  const cds = C.entries[0] && C.entries[0].dateString;
  const agree = lds === cds;
  console.log(label.padEnd(56),
    '\n   legacy  ', lds,
    '\n   connect ', cds,
    '\n   =>', agree ? 'AGREE' : 'DIVERGE by ' + ((Date.parse(cds)-Date.parse(lds))/3600000) + ' h');
}
console.log('true instant of the reading:', new Date(TRUE_UTC).toISOString(), '\n');
run('ARM  pump at UTC+2, NO lastConduitDateTime', {}, 'EU');
run('CTRL pump at UTC+2, lastConduitDateTime +02:00', {lastConduitDateTime:'2026-09-01T14:00:00.000+02:00'}, 'EU');
run('CTRL pump at UTC+0 (the fixture case)', {sMedicalDeviceTime:'2026-09-01T12:00:00.000Z', sgs:[{kind:'SG',sg:123,datetime:'2026-09-01T12:00:00.000Z'}]}, 'EU');
run('ARM  GUARDIAN at UTC+2, no lastConduitDateTime', {medicalDeviceFamily:'GUARDIAN'}, 'EU');
