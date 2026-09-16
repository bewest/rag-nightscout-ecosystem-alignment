'use strict';
const path = require('path');
const CRM = '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const NC  = '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect';

const legacy = require(path.join(CRM,'node_modules/minimed-connect-to-nightscout'));
const fixtures = require(path.join(CRM,'node_modules/minimed-connect-to-nightscout/test/_fixtures.js'));
const axios = require(path.join(CRM,'node_modules/axios'));

function mkConnect(file) {
  const src = require(file);
  const log = { debug(){}, error(){}, info(){}, warn(){} };
  return src({ carelinkRegion:'eu', carelinkUsername:'u', carelinkPassword:'p', countryCode:'gb', languageCode:'en' }, axios, log);
}
const cV14 = mkConnect(path.join(NC,'lib/sources/minimedcarelink/index.js'));
const cDev = mkConnect(path.join(CRM,'node_modules/nightscout-connect/lib/sources/minimedcarelink/index.js'));

function payload(over){ return fixtures.data(over || {}); }

function show(label, v){ console.log(label, JSON.stringify(v)); }

console.log('=== TZ =', process.env.TZ, ' MMCONNECT_SERVER =', process.env.MMCONNECT_SERVER);

// ---- A. legacy fixture, verbatim (no markers, no lastConduitDateTime) ----
console.log('\n--- A. legacy package own recorded payload shape ---');
const d = payload({ currentServerTime: Date.parse('2015-10-17T09:11:59Z'),
                    lastMedicalDeviceDataUpdateServerTime: Date.parse('2015-10-17T09:11:41Z') });
let L;
try { L = legacy.transform(d, 24); console.log('legacy ok: entries', L.entries.length, 'devicestatus', L.devicestatus.length); }
catch(e){ console.log('legacy THREW:', e.constructor.name, e.message); }

for (const [nm, impl] of [['v0.0.14', cV14], ['dev-pin(234d47c8)', cDev]]) {
  try { const C = impl.transformPayload(d, undefined);
        console.log(nm, 'ok: entries', C.entries.length, 'devicestatus', (C.devicestatus||[]).length, 'treatments', (C.treatments||[]).length);
  } catch(e){ console.log(nm, 'THREW:', e.constructor.name + ': ' + e.message); }
}

// ---- B. with markers added so connect can run ----
console.log('\n--- B. same payload + markers:[] so connect can run ---');
const d2 = payload({ markers: [],
                     currentServerTime: Date.parse('2015-10-17T09:11:59Z'),
                     lastMedicalDeviceDataUpdateServerTime: Date.parse('2015-10-17T09:11:41Z') });
const L2 = legacy.transform(JSON.parse(JSON.stringify(d2)), 24);
show('legacy  last entry ', L2.entries[L2.entries.length-1]);
show('legacy  devicestatus', L2.devicestatus[0]);
for (const [nm, impl] of [['v0.0.14', cV14], ['dev-pin', cDev]]) {
  const C = impl.transformPayload(JSON.parse(JSON.stringify(d2)), undefined);
  show(nm + ' n=' + C.entries.length + ' last entry ', C.entries[C.entries.length-1]);
  show(nm + ' devicestatus', (C.devicestatus||[])[0]);
}

// ---- C. gap sentinel sg:0 handling ----
console.log('\n--- C. CareLink gap sentinel sg:0 ---');
const sgs = [ fixtures.makeSG(0, 'Oct 17, 2015 09:00:00'),
              fixtures.makeSG(120, 'Oct 17, 2015 09:05:00'),
              fixtures.makeSG(0, 'Oct 17, 2015 09:10:00') ];
const d3 = payload({ sgs, markers: [], lastSG: sgs[2],
                     currentServerTime: Date.parse('2015-10-17T09:11:59Z'),
                     lastMedicalDeviceDataUpdateServerTime: Date.parse('2015-10-17T09:11:41Z') });
const L3 = legacy.transform(JSON.parse(JSON.stringify(d3)), 24);
console.log('legacy   sgvs:', L3.entries.map(e=>e.sgv));
for (const [nm, impl] of [['v0.0.14', cV14], ['dev-pin', cDev]]) {
  const C = impl.transformPayload(JSON.parse(JSON.stringify(d3)), undefined);
  console.log(nm.padEnd(9), 'sgvs:', C.entries.map(e=>e.sgv));
}

// ---- D. timestamp divergence, zone-less payload ----
console.log('\n--- D. absolute time assigned to one reading ---');
function oneReading(pumpOffsetHours) {
  const serverNow = Date.parse('2015-10-17T09:11:59Z');
  const pumpLocal = new Date(serverNow + pumpOffsetHours*3600e3);
  const fmt = (dt) => dt.toISOString().replace('T',' ').replace(/\..*/,'');
  const stamp = fmt(new Date(pumpLocal.getTime()-120e3));
  const sg = { sg: 120, datetime: stamp, version:1, timeChange:false, kind:'SG' };
  return payload({ sgs:[sg], lastSG: sg, markers: [],
                   sMedicalDeviceTime: fmt(pumpLocal),
                   currentServerTime: serverNow,
                   lastMedicalDeviceDataUpdateServerTime: serverNow - 18000 });
}
for (const off of [0, 2, -7, 5.5]) {
  const p = oneReading(off);
  let lt = null, err=null;
  try { lt = legacy.transform(JSON.parse(JSON.stringify(p)), 24).entries[0]; } catch(e){ err = e.message; }
  const c14 = cV14.transformPayload(JSON.parse(JSON.stringify(p)), undefined).entries[0];
  console.log(`pump UTC${off>=0?'+':''}${off}  legacy=${lt?lt.dateString:'THREW:'+err}  connect=${c14.dateString}  delta_h=${lt?((lt.date-c14.date)/3600e3).toFixed(2):'n/a'}`);
}
