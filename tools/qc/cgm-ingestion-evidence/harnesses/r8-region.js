// Repro 8: connect's own region selection surface.
const NC='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official/node_modules/nightscout-connect';
const src=require(NC+'/lib/sources/dexcomshare.js');
const seen=[];
const fakeAxios={create:(cfg)=>{ seen.push(cfg.baseURL); return {post:()=>Promise.resolve({data:[]})}; }};
const log={debug(){},error(){}};
const cases=[{},{shareRegion:'us'},{shareRegion:'ous'},{shareRegion:'eu'},{shareRegion:'EU'},{shareRegion:'OUS'},
             {shareRegion:'jp'},{shareServer:'share.dexcom.jp'},{shareServer:'US'},{shareRegion:'ous',shareServer:'share2.dexcom.com'}];
console.log('CONNECT_SHARE_* input'.padEnd(46), 'resulting axios baseURL');
for(const c of cases){ seen.length=0; src(Object.assign({shareAccountName:'a',sharePassword:'b'},c), fakeAxios, log);
  console.log(JSON.stringify(c).padEnd(46), seen[0]); }
console.log('\nvalidate() accepts a bogus region without complaint:',
  JSON.stringify(src.validate({shareAccountName:'a',sharePassword:'b',shareRegion:'eu'})));
