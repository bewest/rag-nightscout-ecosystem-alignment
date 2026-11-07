'use strict';
const fs=require('node:fs'),path=require('node:path');
function refused(code,result,missing){const error=new Error(code);error.code=code;error.phaseResult=result;if(missing)error.missingPhysicalFiles=missing;return error;}
module.exports=function verdict({directory,result,control,configuration,requiredRaw,verify,sourceDir,sourceFiles}){
 const kind=control?'CONTROL':'ORDINARY';
 if(!result||!Number.isInteger(result.status)||result.spawnError||result.signal||result.timedOut||result.forcedKill||result.cancelled)throw refused('INVALID_'+kind+'_PROCESS_RESULT',result);
 // A real unsuccessful ordinary child precedes interpretation of its missing
 // success-only raw files. Preserve its result rather than hiding it as ENOENT.
 if(!control&&result.status!==0)throw refused('ACTUAL_ROLE_PHASE_FAILED',result);
 if(!Array.isArray(requiredRaw)||!requiredRaw.length||typeof verify!=='function')throw refused('INVALID_'+kind+'_VERIFIER_CONTRACT',result);
 const missing=requiredRaw.filter(name=>{const file=path.resolve(directory,name);if(!file.startsWith(path.resolve(directory)+path.sep))return true;try{const s=fs.lstatSync(file);return!s.isFile()||s.isSymbolicLink();}catch{return true;}});
 if(missing.length)throw refused('INVALID_'+kind+'_MISSING_PHYSICAL_RAW',result,missing);
 if(control&&result.status===0)throw refused('CONTROL_UNEXPECTED_GREEN',result);
 if(control&&result.status!==1)throw refused('INVALID_CONTROL_EXIT_STATUS',result);
 try{verify({directory,result,configuration,control,sourceDir,sourceFiles});}catch(error){throw refused(error.code==='ENOENT'?'INVALID_'+kind+'_MISSING_PHYSICAL_RAW':(control?'INVALID_CONTROL_PHYSICAL_ORACLE':'ORDINARY_PHYSICAL_ORACLE_FAILED'),result);}
 return{classification:control?'expected-physical-semantic-red':'ordinary-physical-pass',status:result.status};
};
