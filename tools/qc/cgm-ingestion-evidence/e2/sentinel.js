'use strict';
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const levels = require(CRM+'/lib/levels');
const sa = require(CRM+'/lib/plugins/simplealarms.js')({levels, language:{translate:s=>s}});
const now = Date.parse('2026-09-15T12:00:00Z');
function sbxFor(mgdl){
  const fired=[];
  const e={mills: now-60000, mgdl};
  return {sbx:{
    time: now, lastSGVEntry:()=>e, scaleEntry:(x)=>x&&x.mgdl, scaleMgdl:(v)=>v,
    settings:{ alarmUrgentHigh:true, alarmHigh:true, alarmUrgentLow:true, alarmLow:true,
               thresholds:{bgHigh:260,bgTargetTop:180,bgLow:55,bgTargetBottom:80}, units:'mg/dl'},
    extendedSettings:{}, buildDefaultMessage:()=>'', notifications:{requestNotify:(n)=>fired.push(n.title)}
  }, fired};
}
for (const v of [55, 40, 39, 0]) {
  const {sbx, fired} = sbxFor(v);
  sa.checkNotifications(sbx);
  console.log(('lastSGVEntry.mgdl='+v).padEnd(24), 'alarms fired:', JSON.stringify(fired));
}
