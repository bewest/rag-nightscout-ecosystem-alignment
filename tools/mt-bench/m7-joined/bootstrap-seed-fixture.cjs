'use strict';
// Real selected bootstrap emitter, synthetic protocol/files only. No network/SQL.
const fs=require('node:fs'),path=require('node:path');
const [core,out,sourceCommit,deployCommit]=process.argv.slice(2),plan=require(path.join(core,'deploy/multitenant/config'));
const layout=plan.layout(),roleURLs=Object.fromEntries(Object.keys(layout.roles).map(role=>[role,'postgres://'+layout.roles[role]+':synthetic@postgres:5432/nightscout_compose_test']));
const requests=[];
const writePrivate=(file,value)=>{fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});fs.writeFileSync(file,JSON.stringify(value),{mode:0o600,flag:'wx'});};
require(path.join(core,'deploy/multitenant/registry-bootstrap')).finish({
 options:{output:out,uid:process.getuid(),gid:process.getgid(),sourceCommit,deployCommit,vault:{origin:'https://vault:8200'}},
 request:async route=>{requests.push(route);return{auth:{client_token:'synthetic-test-token'}};},rootToken:'synthetic-root-token',layout,roleURLs,writePrivate
}).then(result=>{
 const seed=JSON.parse(fs.readFileSync(path.join(out,'primer/config.json')));
 const overlay=require(path.join(core,'deploy/multitenant/evaluator-workers')).compose(require(path.join(core,'deploy/multitenant/evaluator-workers')).selection(),path.join(core,'deploy/multitenant/compose.yaml'),plan.tenantIds().length);
 fs.writeFileSync(path.join(out,'source-evaluator-overlay.yaml'),overlay,{mode:0o600,flag:'wx'});
 console.log(JSON.stringify({result,seedCount:seed.seed.length,seedRowKeys:Object.keys(seed.seed[0]).sort(),requestsAreRecordingOnly:true,recordedProtocolRequests:requests.length}));
}).catch(e=>{console.error(e);process.exitCode=1;});
