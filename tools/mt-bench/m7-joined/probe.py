"""Explicit adaptation of a tracked prior probe, never a serving-source mount."""
import hashlib
from pathlib import Path
from contract import DISCOVERY_MAX_WORKERS, require


def generate(root, target, *, serial_exchange=False):
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
    if(!Array.isArray(evaluatorServices)||!evaluatorServices.length||evaluatorServices.length>WORKER_LIMIT)throw Error('M7_EVALUATOR_PROGRESS_INSTANCE_BOUND');
    const recoveryObserve=spec=>new Promise((resolve,reject)=>{
      const child=execFile(process.env.M7_PROGRESS_PYTHON, [path.join(__dirname,'evaluator_recovery.py')], {encoding:'utf8',timeout:920000,maxBuffer:1048576},(error,stdout)=>{
        let value;try{value=JSON.parse(stdout);}catch{return reject(Error('M7_EVALUATOR_RECOVERY_UNAVAILABLE'));}
        if(error||!value)return reject(Error(value.code||'M7_EVALUATOR_RECOVERY_UNAVAILABLE'));resolve(value);
      });
      child.stdin.end(JSON.stringify({...spec,attribution:JSON.parse(process.env.M7_PROGRESS_ATTRIBUTION),composeArgs,services:evaluatorServices,ids:tenants.map(t=>t.id)}));
    });
    const recoveryBaseline=path.join(signalDir,'evaluator-recovery-baseline.private.json');
    const baselineObservation=await recoveryObserve({mode:'baseline',path:recoveryBaseline});
    const restartIso = new Date().toISOString(); const r0 = Date.now();'''.replace('WORKER_LIMIT',str(DISCOVERY_MAX_WORKERS)))
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
    setup_anchor="  const jwts = new Array(tenants.length);"
    require(source.count(setup_anchor)==1,'M7_PROBE_SETUP_ANCHOR_CHANGED')
    source=source.replace(setup_anchor,"""  const setupSeconds=Number(args.setupSeconds??300),setupStartedMono=performance.now();
  if(!Number.isSafeInteger(setupSeconds)||!Number.isSafeInteger(setupSeconds*1000)||setupSeconds<=0)throw Error('M7_PHASE_WINDOW_INVALID:setupSeconds');
"""+setup_anchor)
    setup_wait='Date.now() - t0 < 300000'
    require(source.count(setup_wait)==1,'M7_PROBE_SETUP_ANCHOR_CHANGED')
    # Retain the legacy default branch's literal for existing Kubernetes
    # materializers; an explicit clock includes exchanges before socket opens.
    source=source.replace(setup_wait,'(args.setupSeconds===undefined ? '+setup_wait+' : performance.now()-setupStartedMono<setupSeconds*1000)')
    source=source.replace("{ encoding: 'utf8', maxBuffer: 64 << 20 }", "{ encoding: 'utf8', timeout:5000, maxBuffer:64 << 20 }")
    # The first pgstream sample joins an actual stored marker, durable completion,
    # the evaluator-produced frame and already-connected client identity/content.
    source=source.replace("const { io } = require('socket.io-client');", "const { io } = require(process.env.M7_GENERATOR_ROOT?path.join(process.env.M7_GENERATOR_ROOT,'node_modules/socket.io-client'):'socket.io-client');")
    source=source.replace("const signalDir = path.dirname(args.signal);", "const completionSource=process.env.M7_COMPLETION_SOURCE?JSON.parse(process.env.M7_COMPLETION_SOURCE):null;\nconst completionOracle=completionSource?require('./completed-oracle.cjs'):null;const lag=require('./durable-lag.cjs');const oracleCost={queries:0,bytes:0,elapsedMs:0,missing:0,durablePendingPeak:0};\nconst signalDir = path.dirname(args.signal);")
    source=source.replace("const p = { sent: Date.now(),", "const p = { sentMono:performance.now(), sent: Date.now(),")
    source=source.replace("const e = { tenant: t.id,", "const e = { clientProofVersion:2, expectedSockets:sockets.flatMap((s,i)=>s.index===tenants.indexOf(t)?[i]:[]), date, sentMono:p.sentMono, tenant: t.id,")
    source=source.replace("    for (const sgv of frame?.sgvs || []) {", "    for (const sgv of frame?.sgvs || []) { const proof=pending.get(t.id+':'+sgv.mills);if(proof&&completionSource){proof.clientFrames??=new Map();if(!proof.clientFrames.has(s))proof.clientFrames.set(s,{atMono:performance.now(),socket:sockets.indexOf(s),connects:s.connects,transportId:s.socket.id,sgv:{_id:String(sgv._id),mills:sgv.mills,mgdl:sgv.mgdl}});}")
    source=source.replace("      if (open.length) {", """      if(open.length && completionSource){
        const ids=[...new Set(open.map(e=>e.tenant))];
        oracleCost.durablePendingPeak=Math.max(oracleCost.durablePendingPeak,open.filter(e=>e.acked!==null&&!e.durableObservation).length);
        const queryStart=performance.now();
        const raw=await psqlAsync(completionOracle.query(completionSource,ids,args.runid));
        const queryEnd=performance.now();oracleCost.queries++;oracleCost.bytes+=Buffer.byteLength(raw);oracleCost.elapsedMs+=queryEnd-queryStart;if(!raw)oracleCost.missing++;
        const rows=new Map(raw.split('\\n').filter(Boolean).map(line=>{const row=JSON.parse(line);return [row.tenant,row];}));
        for(const e of open){
          if(e.acked===null)continue;const row=rows.get(e.tenant);if(!row)continue;
          if(e.stamp===null)e.stamp=row.stamp;
          if(completionSource.native&&!e.nativeTarget){try{e.nativeTarget=require('./native-observation.cjs').snapshot(row,completionSource);}catch{}}
          const proof=pending.get(e.tenant+':'+e.date);
          const durable=completionOracle.assessDurable(row,e,completionSource);
          lag.observe(e,durable,queryStart,queryEnd);
          const result=completionOracle.assess(row,e,[...(proof?.clientFrames?.values()||[])],PER,completionSource);
          // The SQL read may cross the deadline after admission. Credit only
          // evidence returned within the same-process strict 120-second window.
          const withinDeadline=performance.now()-e.sentMono<120000;
          e.completion=withinDeadline?result:{...result,ready:false,code:'M7_COMPLETION_DEADLINE',assessedCode:result.code,...(result.clientFailure?{assessedClientFailure:result.clientFailure}:{})};
          if(e.completion.ready){e.evaluatedAt=Date.now();evalLatencies.push(e.evaluatedAt-e.sent);}
        }
      }else if (open.length) {""")
    source=source.replace("const e = { tenant: t.id, sent: p.sent,", "const e = { tenant: t.id, date, sent: p.sent,")
    source=source.replace("    await sleep(PROBE);", "    if(completionSource){const until=Date.now()+PROBE;while(Date.now()<until&&!fs.existsSync(path.join(signalDir,'.restart')))await sleep(Math.min(1000,until-Date.now()));}else await sleep(PROBE);")
    source=source.replace("  fs.writeFileSync(args.out, JSON.stringify(out, null, 2)", "  if(completionSource){oracleCost.observationEndMono=performance.now();out.durableOutputObservation=lag.summary(evalPending,pending,oracleCost);out.completedOutput={rosterTenants:tenants.length,witnessTenants:[...new Set(evalPending.map(e=>e.tenant))],witnessTenantCount:new Set(evalPending.map(e=>e.tenant)).size,verdict:evalPending.length>0&&evalPending.every(e=>e.completion?.ready)&&writes.failed===0?'PASS':'FAIL',witnesses:evalPending.map(e=>({tenant:e.tenant,date:e.date,stamp:e.stamp,requestStartedAt:e.sent,...e.completion})),probeCadenceMs:PROBE,scope:'sampled stored/output/client witnesses and selected BG-now mean; witnessTenants is the exercised subset, not all-roster clinical equivalence; uploader separate from ordinary k6 workload; any planned restart is qualified by its separate receipt'};for(const s of sockets)s.socket.close();}\n  fs.writeFileSync(args.out, JSON.stringify(out, null, 2)")
    source=source.replace("  while (!fs.existsSync(path.join(signalDir, '.restart'))) {", "  while (!fs.existsSync(path.join(signalDir, '.restart')) && (args.maxWrites===undefined || k<Number(args.maxWrites))) {")
    if serial_exchange:
        stock="async function exchange (t) {"
        require(source.count(stock)==1,'M7_SERIAL_EXCHANGE_STOCK_ANCHOR')
        source=source.replace(stock,"const serialStockExchange={attempts:0,retryAttempts:0,httpResponses:0,transportFailures:0,statuses:{}};\n"+stock)
        attempt="    const r = await request('GET', t, '/api/v2/authorization/request/' + encodeURIComponent(t.token), null, 60000);"
        require(source.count(attempt)==1,'M7_SERIAL_EXCHANGE_STOCK_ATTEMPT_ANCHOR')
        source=source.replace(attempt,attempt+"\n    serialStockExchange.attempts++;if(k>0)serialStockExchange.retryAttempts++;if(r.status>0)serialStockExchange.httpResponses++;else serialStockExchange.transportFailures++;serialStockExchange.statuses[r.status]=(serialStockExchange.statuses[r.status]||0)+1;")
        before="  const jwts = new Array(tenants.length);"
        require(source.count(before)==1,'M7_SERIAL_EXCHANGE_BEFORE_ANCHOR')
        source=source.replace(before, """  out.diagnosticOnly=true;
  const serialExchange=require('./serial-exchange-pair.cjs').createActor(args.serialExchangeBinding,args.serialExchangeBindingSha256);
  out.serialExchangeDiagnostic={selection:{tenants:64,phaseSeconds:120,requestSeconds:60},before:null,after:null,stockExchange:serialStockExchange};
  try{
    out.serialExchangeDiagnostic.before=await serialExchange.phase('before');
    if(out.serialExchangeDiagnostic.before.status!=='COMPLETED_64'){
      fs.writeFileSync(args.out,JSON.stringify(out,null,2)+'\\n');return;
    }
"""+before)
        release="  fs.writeFileSync(args.signal, String(Date.now()));"
        require(source.count(release)==1,'M7_SERIAL_EXCHANGE_AFTER_ANCHOR')
        source=source.replace(release,"""  out.serialExchangeDiagnostic.after=await serialExchange.phase('after');
  fs.writeFileSync(args.out,JSON.stringify(out,null,2)+'\\n');return;
"""+release)
        close="})().catch(e => {"
        require(source.count(close)==1,'M7_SERIAL_EXCHANGE_CLOSE_ANCHOR')
        source=source.replace(close,"""  }finally{
    let serialCleanupFailed=false;
    try{serialExchange.close();}catch(_){serialCleanupFailed=true;}
    for(const s of sockets){try{s.socket.close();}catch(_){serialCleanupFailed=true;}}
    try{agent.destroy();}catch(_){serialCleanupFailed=true;}
    try{plainAgent.destroy();}catch(_){serialCleanupFailed=true;}
    if(serialCleanupFailed)throw Error('M7_SERIAL_EXCHANGE_CLEANUP_FAILED');
  }
"""+close)
    # Quotient/remainder preserves tenant-major order for legacy per-tenant load.
    def viewers_change(old,new):
        nonlocal source
        require(source.count(old)==1,'M7_VIEWER_PROBE_ANCHOR_CHANGED')
        source=source.replace(old,new)
    viewers_change("tenants.length*PER", "TOTAL")
    viewers_change("const EVAL_TIMEOUT =", "const TOTAL=Number(args.clients??tenants.length*PER);if(!Number.isSafeInteger(TOTAL)||TOTAL<0||TOTAL>0xffffffff||!tenants.length||new Set(tenants.map(t=>t.id)).size!==tenants.length)throw Error('M7_VIEWER_TOTAL_RANGE');const viewers=tenants.map((_,i)=>Math.floor(TOTAL/tenants.length)+(i<TOTAL%tenants.length?1:0));\nconst EVAL_TIMEOUT =")
    viewers_change("k < PER;", "k < viewers[i];")
    viewers_change("jwts[i] = await exchange(tenants[i]);", "jwts[i] = viewers[i]?await exchange(tenants[i]):null;")
    viewers_change("expected: PER", "expected: viewers[i]")
    viewers_change("[...pending.values()].length * PER", "[...pending.values()].reduce((n,p)=>n+p.expected,0)")
    viewers_change("],PER,completionSource)", "],viewers[tenants.findIndex(t=>t.id===e.tenant)],completionSource)")
    viewers_change("out.completedOutput={rosterTenants", "out.completedOutput={clientFrames:{verdict:out.window.expectedFrames===0?'NOT_EXERCISED':evalPending.every(e=>e.completion?.ready)?'PASS':'UNMEASURED'},rosterTenants")
    viewers_change("  log('prime', out.prime);", "  out.viewerBindings=sockets.map((s,socket)=>({socket,tenant:tenants[s.index].id}));\n  log('prime', out.prime);")
    target = Path(target)
    target.write_text(source)
    helpers={}
    for name in ('evaluator_recovery.py','evaluator_progress.py','evaluator-progress.cjs','probe-accounting.cjs','completed-oracle.cjs','native-observation.cjs','client-delivery.cjs','durable-lag.cjs'):
        data=Path(__file__).with_name(name).read_bytes();target.with_name(name).write_bytes(data)
        helpers[name]=hashlib.sha256(data).hexdigest()
    if serial_exchange:
        data=Path(__file__).with_name('serial-exchange-pair.cjs').read_bytes();target.with_name('serial-exchange-pair.cjs').write_bytes(data)
        helpers['serial-exchange-pair.cjs']=hashlib.sha256(data).hexdigest()
    return {"baseline": str(baseline.relative_to(root)), "baselineSha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            "adaptedSha256": hashlib.sha256(target.read_bytes()).hexdigest(), "recoveryHelpers": helpers,
            "changes": ["actual explicit replica restart roster", "bounded v2 exact-instance fresh-owned-window recovery with changed runtime proof", "separate hot/cold tenant write-to-frame distributions", "reject failed or unobserved container restart"]}
