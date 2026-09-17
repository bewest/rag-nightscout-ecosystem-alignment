const root = process.argv[2];
const levels = require(root + '/lib/levels');
const ctx = { moment: require(root + '/node_modules/moment'),
              language: { translate: (s)=>s }, levels: levels };
const iage = require(root + '/lib/plugins/insulinage')(ctx);
const now = Date.now();
function sbxAt(hoursAgo, minutesExtra, enableAlerts){
  return {
    time: now,
    data: { insulinchangeTreatments: [ { mills: now - (hoursAgo*3600000) - (minutesExtra*60000) } ] },
    extendedSettings: enableAlerts ? { enableAlerts: true } : { },
    properties: {}, notifications: { requestNotify: ()=>{} }
  };
}
const names = {0:'NONE',1:'LOW',2:'INFO',5:'WARN',7:'URGENT'};
for (const [h,m] of [[43,0],[44,0],[48,0],[71,0],[72,5],[80,0],[100,0]]) {
  const r = iage.findLatestTimeChange(sbxAt(h,m,true));
  console.log(`${root.split('/').pop()}  age=${r.age}h  level=${r.level} (${names[r.level]||r.level})  notification=${r.notification ? r.notification.message : 'none'}`);
}
