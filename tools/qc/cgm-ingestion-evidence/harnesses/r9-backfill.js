// Repro 9: what each side asks the vendor for after a gap of N minutes.
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const NC=CRM+'/node_modules/nightscout-connect';
const src=require(NC+'/lib/sources/dexcomshare.js');
const MIN=60000;
let captured;
const fakeAxios={create:()=>({post:(p,b,cfg)=>{ if(/LatestGlucose/.test(p)) captured=cfg.params; return Promise.resolve({data:[]}); }})};
const impl=src({shareAccountName:'a',sharePassword:'b'},fakeAxios,{debug(){},error(){}});

// legacy: bridge.js recomputes these from module-level mostRecentRecord
function legacyParams(gapMin, bridgeMinutes){
  const mostRecent = Date.now() - gapMin*MIN;
  const minutes = parseInt((Date.now()-mostRecent)/MIN);
  const maxCount = parseInt((minutes/5)+1);
  return {minutes, maxCount};
}
console.log('gap since last reading | LEGACY asks            | CONNECT asks');
for (const gap of [5, 15, 60, 6*60, 24*60, 3*24*60, 30*24*60]) {
  impl.dataFromSesssion('SESSION', {entries: new Date(Date.now()-gap*MIN)});
  const L=legacyParams(gap);
  console.log(String(gap+' min').padStart(22), '|',
    `minutes=${String(L.minutes).padEnd(6)} maxCount=${String(L.maxCount).padEnd(6)}`.padEnd(24), '|',
    `minutes=${String(captured.minutes).padEnd(6)} maxCount=${String(captured.maxCount).padEnd(6)}`);
}
console.log('\nAT STARTUP, before any reading has been seen:');
console.log('  LEGACY: mostRecentRecord = now - BRIDGE_MINUTES (default 1440) -> asks for minutes=1440 maxCount=289, regardless of what the database already holds.');
console.log('  CONNECT: last_known comes from the database via the internal output gap_for(); it is clamped to at most 2 days.');
console.log('\nDexcom Share itself caps maxCount at 288; neither side clamps its own request (read-derived).');
