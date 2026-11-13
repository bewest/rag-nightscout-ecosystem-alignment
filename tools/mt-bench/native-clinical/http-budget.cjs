'use strict';
// Observational bounds for the trusted HTTP-only child, including source-primer
// lexical request functions. Restore only the exact wrapper this module owns.
function install(http,{maximumRequests=16384,maximumResponseBytes=268435456}={}){
 const original=http.request;let requests=0,responseBytes=0,refused=false;
 const fail=()=>Object.assign(Error('CLIENT_HTTP_BUDGET'),{code:'CLIENT_HTTP_BUDGET'});
 function request(...args){
  if(refused||++requests>maximumRequests){refused=true;throw fail();}
  const req=original.apply(this,args);
  req.on('response',response=>response.on('data',chunk=>{
   responseBytes+=Buffer.byteLength(chunk);
   if(responseBytes>maximumResponseBytes){refused=true;response.destroy(fail());req.destroy(fail());}
  }));
  return req;
 }
 http.request=request;
 return {snapshot:()=>({requests,responseBytes,refused,maximumRequests,maximumResponseBytes}),restore(){if(http.request!==request)throw Error('CLIENT_HTTP_WRAPPER_CHANGED');http.request=original;}};
}
module.exports={install};
