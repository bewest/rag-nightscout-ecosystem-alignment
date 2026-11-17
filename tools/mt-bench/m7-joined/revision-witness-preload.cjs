'use strict';
// Explicit opt-in file config. Load before the canonical app entrypoint; app modules load lazily.
const fs=require('node:fs'),path=require('node:path'),witness=require('./revision-witness.cjs');
let active;
function start(){
 if(active)return active;
 const file=process.env.M7_REVISION_WITNESS_CONFIG;if(!file)return null;
 const bytes=fs.readFileSync(file);if(bytes.length>4096)throw Error('M7_REVISION_CONFIG_BOUND');
 const config=JSON.parse(bytes),{root,out,owner,source,targets,sourceFiles}=config;
 const files=['lib/pgstream/realtime-output.js','lib/server/realtime/runtime.js','lib/pgstream/typed-checkpoint.js','lib/pgstream/realtime-receipt.js','lib/pgstream/activity-scheduler.js'];
 if(!sourceFiles||Object.keys(sourceFiles).length!==files.length||files.some(file=>!(/^[a-f0-9]{64}$/.test(sourceFiles[file]))||require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')!==sourceFiles[file]))throw Error('M7_REVISION_SOURCE_BYTES');
 if(!path.isAbsolute(root)||!path.isAbsolute(out))throw Error('M7_REVISION_CONFIG_PATH');
 // Probe path and output permission before any substantive actors start.
 const capture=out+'.'+require('node:crypto').randomUUID()+'.json';
 const fd=fs.openSync(capture,'wx',0o600);fs.closeSync(fd);
 const tap=witness.create({owner,source,targets,persist:value=>{const temporary=capture+'.partial';fs.writeFileSync(temporary,JSON.stringify(value)+'\n',{mode:0o600});fs.renameSync(temporary,capture);}});
 const hook=witness.install({root,tap});active={tap,hook,out:capture};return active;
}
function attachClient(socket,tenant){const state=start();return state?witness.client({socket,tenant,tap:state.tap}):null;}
process.once('exit',()=>{if(active){try{fs.writeFileSync(active.out,JSON.stringify(active.tap.state())+'\n',{mode:0o600});}catch{/* Earlier segments stay retained; observer failure cannot change application exit. */}}});
start();module.exports={start,attachClient};
