'use strict';
// Diagnostic completion retains the unchanged strict actual-browser acceptance oracle.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
module.exports=input=>{
 const raw=fs.readFileSync(path.join(input.directory,'actual-browser-diagnostics.json'));assert(raw.length<=65537,'BROWSER_DIAGNOSTIC_BOUND');const d=JSON.parse(raw);
 const file='tests/fixtures/realtime-preview/browser-diagnostics.js',actual=path.join(input.sourceDir,file);assert.equal(crypto.createHash('sha256').update(fs.readFileSync(actual)).digest('hex'),input.sourceFiles[file],'BROWSER_DIAGNOSTIC_SOURCE_HASH');const stages=require(actual).STAGES;
 assert.equal(d.version,1);assert.equal(d.status,'complete','DIAGNOSTIC_COMPLETION_REQUIRED');assert.equal(d.activeStage,'urgent-ui');assert(d.diagnostics.length<=128&&Number.isSafeInteger(d.droppedDiagnostics)&&d.droppedDiagnostics>=0);assert.equal(d.stages.length,10);
 for(let i=0;i<stages.length;i++){assert.equal(d.stages[2*i].stage,stages[i]);assert.equal(d.stages[2*i].edge,'before');assert.equal(d.stages[2*i+1].stage,stages[i]);assert.equal(d.stages[2*i+1].edge,'after');}
 for(const key of ['browser','executablePath','sha256'])assert.equal(d.browserRuntime[key],input.configuration.browserRuntime[key]);
 return require('./verify-browser.cjs')(input);
};
