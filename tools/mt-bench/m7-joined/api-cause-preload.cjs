'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),cause=require('./api-cause.cjs');
const FILES=Object.freeze(['lib/server/tenant-app/index.js','lib/server/serve/api-admission.js']);
let active;
function start(){
 if(active)return active;
 const file=process.env.M7_API_CAUSE_CONFIG;if(!file)return null;
 const bytes=fs.readFileSync(file);if(bytes.length>4096)throw Error('M7_API_CAUSE_CONFIG_BOUND');
 const config=JSON.parse(bytes),{root,out,owner,source,sourceFiles}=config;
 if(!path.isAbsolute(root)||!path.isAbsolute(out)||!sourceFiles||Object.keys(sourceFiles).sort().join(',')!==[...FILES].sort().join(','))throw Error('M7_API_CAUSE_CONFIG');
 for(const file of FILES)if(!/^[a-f0-9]{64}$/.test(sourceFiles[file])||crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')!==sourceFiles[file])throw Error('M7_API_CAUSE_SOURCE_BYTES');
 const capture=out+'.'+crypto.randomUUID()+'.json',fd=fs.openSync(capture,'wx',0o600);fs.closeSync(fd);
 const tap=cause.create({owner,source,sourceFiles,persist:value=>{const bytes=JSON.stringify(value)+'\n';if(Buffer.byteLength(bytes)>32768)throw Error('M7_API_CAUSE_CAPTURE_BOUND');const temporary=capture+'.partial';fs.writeFileSync(temporary,bytes,{mode:0o600});fs.renameSync(temporary,capture);}});
 const hook=cause.install({root,tap});active={tap,hook,out:capture};return active;
}
process.once('exit',()=>{if(active)try{fs.writeFileSync(active.out,JSON.stringify(active.tap.state())+'\n',{mode:0o600});}catch{}});
start();module.exports={start,FILES};
