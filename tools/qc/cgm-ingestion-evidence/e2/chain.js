'use strict';
// BF-44 -> BF-41 chain, end to end through BOTH shipping modules.
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const NC ='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect';
const legacy = require(CRM+'/node_modules/minimed-connect-to-nightscout');
const axios  = require(CRM+'/node_modules/axios');
const csrc   = require(NC+'/lib/sources/minimedcarelink/index.js');
const timeagoInit = require(CRM+'/lib/plugins/timeago.js');
const levels = require(CRM+'/lib/levels');
const log = {debug(){},error(){},info(){},warn(){}};
const connect = csrc({carelinkRegion:'eu',carelinkUsername:'u',carelinkPassword:'p',countryCode:'gb'}, axios, log);
const timeago = timeagoInit({ language: {translate:(s)=>s}, levels });

// Payload: pump sits in UTC+2 (e.g. Berlin, summer); server clock is UTC.
// Reading happened 40 minutes ago in real time. Feed has therefore been dead
// for 40 minutes and the stale alarm SHOULD fire (warn at 15, urgent at 30).
const serverNow = Date.parse('2026-09-15T12:00:00Z');
const pumpOffsetH = Number(process.env.PUMP_OFFSET_H || 2);
const readingRealUTC = serverNow - 40*60*1000;
const fmt = (ms) => new Date(ms).toISOString().replace('T',' ').replace(/\..*/,'');
const ZONED = process.env.ZONED === '1';
const sg = ZONED
  ? { sg:120, datetime: new Date(readingRealUTC).toISOString(), kind:'SG', version:1 }
  : { sg: 120, datetime: fmt(readingRealUTC + pumpOffsetH*3600e3), kind:'SG', version:1 };
const payload = { sgs:[sg], lastSG:sg, lastSGTrend:'NONE', markers: [],
  medicalDeviceFamily:'PARADIGM', conduitBatteryLevel:90, medicalDeviceBatteryLevelPercent:90,
  sMedicalDeviceTime: fmt(serverNow + pumpOffsetH*3600e3),
  currentServerTime: serverNow,
  lastMedicalDeviceDataUpdateServerTime: serverNow - 30*1000 };

function sbxFor (entry) {
  return {
    time: serverNow,
    runtimeEnvironment: 'server',
    settings: { alarmTimeagoWarn:true, alarmTimeagoWarnMins:15, alarmTimeagoUrgent:true, alarmTimeagoUrgentMins:30 },
    extendedSettings: { enableAlerts: true },
    lastSGVEntry: () => entry,
    prepareDefaultLines: () => [],
    notifications: { requestNotify: (n) => sbxFor.fired.push(n.level) }
  };
}

function arm (name, entryDateMs) {
  sbxFor.fired = [];
  const entry = { mills: entryDateMs, mgdl: 120 };
  const sbx = sbxFor(entry);
  const status = timeago.checkStatus(sbx);
  timeago.checkNotifications(sbx);
  const browserAlarm = (sbx.settings.alarmTimeagoWarn && status==='warn') || (sbx.settings.alarmTimeagoUrgent && status==='urgent');
  const ageMin = ((serverNow - entryDateMs)/60000).toFixed(1);
  console.log(`${name.padEnd(28)} filed=${new Date(entryDateMs).toISOString()} age=${String(ageMin).padStart(6)}min  checkStatus=${status.padEnd(7)} browserAlarm=${browserAlarm}  pushAlarms=${JSON.stringify(sbxFor.fired)}`);
}

process.env.MMCONNECT_SERVER='EU';
let L=null, Lerr=null;
try { L = legacy.transform(JSON.parse(JSON.stringify(payload)), 24); } catch(e){ Lerr = e.constructor.name+': '+e.message; }
const C = connect.transformPayload(JSON.parse(JSON.stringify(payload)), undefined);
console.log('PUMP_OFFSET_H='+pumpOffsetH+'  ZONED='+(process.env.ZONED||'0'));
console.log('server clock (TZ='+process.env.TZ+'):', new Date(serverNow).toISOString(), ' true reading time:', new Date(readingRealUTC).toISOString());
console.log('feed has actually been dead for 40 minutes.\n');
arm('TRUTH (40 min stale)', readingRealUTC);
if (L && L.entries[0]) arm('LEGACY minimed-connect', L.entries[0].date); else console.log('LEGACY minimed-connect       THREW/EMPTY: '+(Lerr||'no entries'));
arm('CONNECT minimedcarelink', C.entries[0].date);
