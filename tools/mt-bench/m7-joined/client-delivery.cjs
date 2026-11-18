"use strict";
// A viewer is a stable probe slot; transport incarnations may change. Actual
// stock-client callbacks retain content and the probe's monotonic clock.
function assess(clients, expected, doc, witness={}) {
 const no=code=>({ready:false,code});
 if(!Number.isInteger(expected)||expected<0||expected>80000||!Array.isArray(clients)||clients.length!==expected)return no('M7_CLIENT_COUNT');
 if(clients.some(c=>!c||!Number.isInteger(c.socket)||c.socket<0)||new Set(clients.map(c=>c.socket)).size!==expected)return no('M7_CLIENT_VIEWER');
 const strict=witness.clientProofVersion===2;
 if(strict){
  const slots=witness.expectedSockets;
  if(!Array.isArray(slots)||slots.length!==expected||new Set(slots).size!==expected||slots.some(x=>!Number.isInteger(x)||x<0)||clients.some(c=>!slots.includes(c.socket)))return no('M7_CLIENT_BINDING');
  if(!Number.isFinite(witness.sentMono)||witness.sentMono<0)return no('M7_CLIENT_CLOCK');
 }
 for(const c of clients){
  if(!Number.isSafeInteger(c.connects)||c.connects<1)return no('M7_CLIENT_INCARNATION');
  if(String(c.sgv?._id)!==doc._id||c.sgv?.mills!==doc.date||c.sgv?.mgdl!==doc.sgv)return no('M7_CLIENT_CONTENT');
  if(strict){
   if(typeof c.transportId!=='string'||c.transportId.length<1||c.transportId.length>256)return no('M7_CLIENT_INCARNATION');
   if(!Number.isFinite(c.atMono)||c.atMono<witness.sentMono)return no('M7_CLIENT_CLOCK');
   if(c.atMono-witness.sentMono>=120000)return no('M7_CLIENT_DEADLINE');
  }
 }
 return {ready:true,viewers:expected,reconnectedViewers:clients.filter(c=>c.connects>1).length,proof:strict?'exact-viewer-callback-v2':'legacy-content-only'};
}
module.exports={assess};
