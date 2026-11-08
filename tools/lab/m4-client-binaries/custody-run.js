'use strict';
// Fixed M4 entrypoint for the reviewed finite host supervisor. The parent owns
// the 600s active / shared 120s cleanup budget and post-supervisor closure.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),assert=require('node:assert/strict');
const {observe}=require('./custody-observer');
function run ({planFile,out,ref,repository,dependencies,spawn=cp.spawn,invoke}) {
  assert([planFile,out,repository,dependencies].every(path.isAbsolute) && /^[a-f0-9]{40}$/.test(ref),'M4_FIXED_PARENT_ARGUMENTS');
  const plan=JSON.parse(fs.readFileSync(planFile,'utf8'));
  assert(plan.dockerExecutable==='/usr/bin/docker' && path.isAbsolute(plan.dockerConfig),'M4_OBSERVER_ENDPOINT');
  assert(plan.applicationHead===ref && plan.activeSeconds===600 && plan.cleanupSeconds===120,'M4_FIXED_PARENT_BINDING');
  const directory=path.join(out,'custody');
  const read=invoke || (args=>{
    const result=cp.spawnSync(plan.dockerExecutable,['--host','unix:///run/docker.sock','--config',plan.dockerConfig,...args],
      {encoding:'utf8',timeout:8000,maxBuffer:2*1024*1024,env:{PATH:process.env.PATH,LANG:'C.UTF-8'}});
    assert(!result.error && result.status===0,'M4_OBSERVER_TRANSPORT');return result.stdout;
  });
  const observer=observe({plan,directory,invoke:read});
  const gate=path.resolve(__dirname,'../../queue/gates/m4-client-binaries.js');
  return new Promise((resolve,reject)=>{
    const child=spawn(process.execPath,[gate,'--ref',ref,'--clients','cgmsim,oref0'],{cwd:path.resolve(__dirname,'../../..'),stdio:'inherit',
      env:{...process.env,NS_M4_CUSTODY_PLAN:planFile,NS_M4_GATE_OUT:out,NS_M4_GATE_REPO:repository,NS_M4_GATE_DEPENDENCIES:dependencies,TZ:'UTC'}});
    let failure;
    const scan=()=>{try{observer.scan();}catch(error){failure=error;clearInterval(timer);child.kill('SIGTERM');}};
    const timer=setInterval(scan,10);
    child.once('error',error=>{clearInterval(timer);reject(error);});
    child.once('close',(status,signal)=>{clearInterval(timer);if(!failure)scan();
      if(failure)return reject(failure);if(signal)return reject(new Error('M4_GATE_INTERRUPTED'));resolve(status);
    });
  });
}
module.exports={run};
if(require.main===module){
  const args=process.argv.slice(2);assert(args.length===10 && ['--plan','--out','--ref','--repository','--dependencies'].every((key,i)=>args[i*2]===key),'M4_FIXED_USAGE');
  run({planFile:args[1],out:args[3],ref:args[5],repository:args[7],dependencies:args[9]}).then(status=>{process.exitCode=status;},error=>{console.error(error.message);process.exitCode=2;});
}
