"""Explicit adaptation of a tracked prior probe, never a serving-source mount."""
import hashlib
from pathlib import Path
from contract import require


def generate(root, target):
    baseline = Path(root) / "tools/mt-bench/capacity/probe.js"
    source = baseline.read_text()
    old = "const roles = ['api', 'realtime', 'evaluator', 'tenant-admin'];"
    require(source.count(old) == 1, "M7_PROBE_ROLE_ANCHOR_CHANGED")
    source = source.replace(old, "const roles = JSON.parse(process.env.M7_RESTART_ROLES); if (!Array.isArray(roles) || !roles.length) throw new Error('M7_RESTART_ROLES_REQUIRED');")
    restart = "const restartDone = new Promise(resolve => execFile('docker', [...composeArgs, 'restart', ...roles], () => resolve(Date.now() - r0)));"
    require(source.count(restart)==1, "M7_PROBE_RESTART_ANCHOR_CHANGED")
    source = source.replace(restart, "const restartDone = require('./restart.cjs').restart({composeArgs,roles,at:r0}).then(value=>{restart.containerStarts=value.starts;return value.commandMs;});")
    before_restart = "    const restartIso = new Date().toISOString(); const r0 = Date.now();"
    require(source.count(before_restart)==1,"M7_PROBE_RESTART_TIME_ANCHOR_CHANGED")
    source=source.replace(before_restart,r'''    const evaluatorServices=JSON.parse(process.env.M7_EVALUATOR_SERVICES||'null');
    if(!Array.isArray(evaluatorServices)||!evaluatorServices.length||evaluatorServices.length>4)throw Error('M7_EVALUATOR_PROGRESS_INSTANCE_BOUND');
    const recoveryObserve=spec=>new Promise((resolve,reject)=>{
      const child=execFile(process.env.M7_PROGRESS_PYTHON, [path.join(__dirname,'evaluator_recovery.py')], {encoding:'utf8',timeout:920000,maxBuffer:1048576},(error,stdout)=>{
        let value;try{value=JSON.parse(stdout);}catch{return reject(Error('M7_EVALUATOR_RECOVERY_UNAVAILABLE'));}
        if(error||!value)return reject(Error(value.code||'M7_EVALUATOR_RECOVERY_UNAVAILABLE'));resolve(value);
      });
      child.stdin.end(JSON.stringify({...spec,attribution:JSON.parse(process.env.M7_PROGRESS_ATTRIBUTION),composeArgs,services:evaluatorServices,ids:tenants.map(t=>t.id)}));
    });
    const recoveryBaseline=path.join(signalDir,'evaluator-recovery-baseline.private.json');
    const baselineObservation=await recoveryObserve({mode:'baseline',path:recoveryBaseline});
    const restartIso = new Date().toISOString(); const r0 = Date.now();''')
    start = source.index("    const gap = (async () => {")
    end = source.index("    // Edge after the role restart:", start)
    source = source[:start] + r'''    const gap = (async () => {
      await restartDone;
      while(Date.now()-r0<EVAL_TIMEOUT && evaluatorServices.some(role=>restart.healthyMs[role]==null))await sleep(1000);
      restart.runtimeAcquisitionObservation=await recoveryObserve({mode:'recovery',baseline:recoveryBaseline,path:path.join(signalDir,'evaluator-recovery.private.json'),deadlineMs:r0+EVAL_TIMEOUT});
      restart.runtimeAcquisitionObservation.baselineObservation=baselineObservation;
      log('runtimeAcquisitionObservation',restart.runtimeAcquisitionObservation);
    })();
''' + source[end:]
    marker = "  out.window = { ms:"
    require(source.count(marker) == 1, "M7_PROBE_WINDOW_ANCHOR_CHANGED")
    source = source.replace(marker, "  out.window = { hotTenantWriteToFrameMs: stats([...pending].filter(([key])=>key.startsWith(tenants[0].id+':')).flatMap(([,value])=>value.latencies)), coldTenantWriteToFrameMs: stats([...pending].filter(([key])=>!key.startsWith(tenants[0].id+':')).flatMap(([,value])=>value.latencies)), ms:")
    prime = "  fs.writeFileSync(args.signal, String(Date.now()));"
    require(source.count(prime)==1, "M7_PROBE_PRIME_ANCHOR_CHANGED")
    source = source.replace(prime, "  fs.writeFileSync(path.join(signalDir,'prime.json'),JSON.stringify(out.prime)); if(out.prime.primed!==tenants.length*PER)throw new Error('M7_ESTABLISHED_SOCKETS_INCOMPLETE');\n" + prime)
    # A single shared probe container must not issue docker commands itself:
    # the runner supplies a narrowly scoped Docker CLI through a host process.
    # Probe executes on the host with npm dependencies from an owned extraction
    # of this exact image (runner records the image and dependency archive hash).
    from probe_discovery import adapt
    source=adapt(source)
    target = Path(target)
    target.write_text(source)
    helpers={}
    for name in ('evaluator_recovery.py','evaluator_progress.py','evaluator-progress.cjs'):
        data=Path(__file__).with_name(name).read_bytes();target.with_name(name).write_bytes(data)
        helpers[name]=hashlib.sha256(data).hexdigest()
    return {"baseline": str(baseline.relative_to(root)), "baselineSha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            "adaptedSha256": hashlib.sha256(target.read_bytes()).hexdigest(), "recoveryHelpers": helpers,
            "changes": ["actual explicit replica restart roster", "bounded v2 exact-instance fresh-owned-window recovery with changed runtime proof", "separate hot/cold tenant write-to-frame distributions", "reject failed or unobserved container restart"]}
