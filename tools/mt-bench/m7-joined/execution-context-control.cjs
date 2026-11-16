'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict'),{inspect}=require('./execution-context.cjs');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'m7-context-control-'));
try{
 const core=path.join(temp,'core'),deps=path.join(temp,'dependencies'),peer=path.join(temp,'peer');
 for(const root of [core,deps,peer]){
  fs.mkdirSync(path.join(root,'node_modules/pg'),{recursive:true});
  fs.writeFileSync(path.join(root,'package.json'),'{}');fs.writeFileSync(path.join(root,'package-lock.json'),JSON.stringify({packages:{'node_modules/pg':{version:'1.0.0'}}}));
  fs.writeFileSync(path.join(root,'node_modules/pg/package.json'),'{"name":"pg","version":"1.0.0","main":"index.js"}');
  fs.writeFileSync(path.join(root,'node_modules/pg/index.js'),'module.exports={Pool:class{},Client:class{}};');
 }
 const modules=path.join(core,'node_modules');fs.rmSync(modules,{recursive:true});fs.symlinkSync(path.join(deps,'node_modules'),modules,'dir');
 assert.equal(inspect(core,path.join(deps,'node_modules'),['pg']).modules.pg.version,'1.0.0');
 assert.throws(()=>inspect(core,path.join(peer,'node_modules'),['pg']),/CONTEXT/);
 // Run in a fresh Node process so the red version cannot hide in require cache.
 const {spawnSync}=require('node:child_process');
 fs.writeFileSync(path.join(core,'package-lock.json'),JSON.stringify({packages:{'node_modules/pg':{version:'2.0.0'}}}));
 const result=spawnSync(process.execPath,['-e',`require(${JSON.stringify(require.resolve('./execution-context.cjs'))}).inspect(process.argv[1],process.argv[2],['pg'])`,core,path.join(deps,'node_modules')],{encoding:'utf8'});
 assert.notEqual(result.status,0);assert.match(result.stderr,/LOCK_VERSION/);
 fs.writeFileSync(path.join(core,'package-lock.json'),JSON.stringify({packages:{'node_modules/pg':{version:'1.0.0'}}}));
 assert.equal(inspect(core,path.join(deps,'node_modules'),['pg']).modules.pg.version,'1.0.0');
 console.log('GREEN owned dependency context; EXPECTED_RED peer context and lock version; RESTORED_GREEN; synthetic modules only');
}finally{fs.rmSync(temp,{recursive:true,force:true});}
