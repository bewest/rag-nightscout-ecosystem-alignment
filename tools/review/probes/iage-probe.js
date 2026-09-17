const path=process.argv[2];
const moment=require(path+'/node_modules/moment');
const levels=require(path+'/lib/levels');
const iage=require(path+'/lib/plugins/insulinage.js')({moment:moment,language:{translate:s=>s},levels:levels});
const NOW=Date.now();
for (const h of [40,48,60,71,72,72.5,73,80,100]) {
  const sbx={time:NOW,extendedSettings:{enableAlerts:true},
    data:{insulinchangeTreatments:[{mills:NOW-h*3600*1000}]},
    properties:{}, notifications:{requestNotify:()=>{}}};
  const info=iage.findLatestTimeChange(sbx);
  console.log(`  age_requested=${h}h  computed_age=${info.age}  level=${info.level}  notification=${info.notification?JSON.stringify(info.notification.title):'NONE'}`);
}
