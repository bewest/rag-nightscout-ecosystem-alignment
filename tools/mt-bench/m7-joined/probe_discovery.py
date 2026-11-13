"""Env-gated observational additions to the generated, instrument-owned probe."""
from contract import require

def adapt(source):
    def change(old,new):
        nonlocal source
        require(source.count(old)==1,'M7_DISCOVERY_PROBE_ANCHOR_CHANGED');source=source.replace(old,new)
    change("const signalDir = path.dirname(args.signal);", "const signalDir = path.dirname(args.signal);\nconst discovery=process.env.M7_RUN_PURPOSE==='discovery';\nlet retainedOut;\nconst hardProgress=value=>value?.verdict==='FAIL'&&!['M7_EVALUATOR_PROGRESS_ERROR','M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE'].includes(value.code);\nconst typedCode=e=>/^M7_[A-Z_]+$/.test(e?.message||'')?e.message:'M7_PROBE_OBSERVATION_UNAVAILABLE';\nconst savePartial=()=>{if(discovery&&retainedOut)fs.writeFileSync(args.out,JSON.stringify(retainedOut)+'\\n');};")
    change("  const byTenant = {}; const writes = { ok: 0, failed: 0 };", "  const byTenant = {}; const writes = { ok: 0, failed: 0 };\n  const accounting=discovery?require('./probe-accounting.cjs').create({ids:tenants.map(t=>t.id),runId:args.runid,persist:value=>fs.writeFileSync(path.join(signalDir,'probe-accounting.json'),JSON.stringify(value)+'\\n')}):null;")
    change("    writers.push(request('POST', t,", "    const attempt=accounting?accounting.begin(t.id):null;\n    writers.push(request('POST', t,")
    change("      if (r.status === 200) { writes.ok++;", "      if(accounting)accounting.settle(attempt,r.status);\n      if (r.status === 200) { writes.ok++;")
    change("  await Promise.all(writers);", "  if(accounting)accounting.close();\n  await Promise.all(writers);")
    change("  const jwts = new Array(tenants.length);", "  retainedOut=out; if(discovery){out.runPurpose='discovery';savePartial();}\n  const jwts = new Array(tenants.length);")
    change("jwts[i] = await exchange(tenants[i]);", "try{jwts[i] = await exchange(tenants[i]);}catch(error){if(!discovery)throw error; (out.exchangeUnavailable||=[]).push({tenantIndex:i,code:'M7_EXCHANGE_UNAVAILABLE'});savePartial();}")
    change("{ open(i, jwts[i]); if (OPEN)", "{ if(!discovery||jwts[i])open(i, jwts[i]); if (OPEN)")
    change("if(out.prime.primed!==tenants.length*PER)throw", "if(!discovery&&out.prime.primed!==tenants.length*PER)throw")
    change("  log('prime', out.prime);", "  log('prime', out.prime);savePartial();")
    change("  log('window', { w2f:", "  savePartial();\n  log('window', { w2f:")
    change("        if(error||!value)return reject(Error(value.code||'M7_EVALUATOR_RECOVERY_UNAVAILABLE'));resolve(value);", "        if(error||!value){if(discovery&&!hardProgress(value))return resolve(value||{verdict:'UNMEASURED',code:'M7_EVALUATOR_RECOVERY_UNAVAILABLE'});return reject(Object.assign(Error(value?.code||'M7_EVALUATOR_RECOVERY_UNAVAILABLE'),{clinicalFailure:hardProgress(value)}));}if(discovery&&hardProgress(value))return reject(Object.assign(Error(value.code||'M7_EVALUATOR_PROGRESS_ERROR'),{clinicalFailure:true}));resolve(value);")
    # Preserve partial recovery even if custody/restart admission fails. Explicit
    # source/clinical FAIL remains a hard failure, never ordinary overload.
    change("const restartDone = require('./restart.cjs').restart({composeArgs,roles,at:r0}).then(value=>{restart.containerStarts=value.starts;return value.commandMs;});", "const restartDone = require('./restart.cjs').restart({composeArgs,roles,at:r0}).then(value=>{restart.containerStarts=value.starts;return value.commandMs;});\n    if(discovery)restartDone.catch(error=>{out.hardFailure={stage:'restart-custody',code:typedCode(error)};savePartial();});")
    change("    const restart = { restartIso, healthyMs: {}, firstServedMs: {} };", "    const restart = { restartIso, healthyMs: {}, firstServedMs: {} };if(discovery){out.restart=restart;savePartial();}")
    change("restartDone.then(ms => { restartCommandMs = ms; });", "restartDone.then(ms => { restartCommandMs = ms; },error=>{if(discovery){out.hardFailure={stage:'restart',code:typedCode(error)};savePartial();}});")
    change("      log('runtimeAcquisitionObservation',restart.runtimeAcquisitionObservation);\n    })();", "      log('runtimeAcquisitionObservation',restart.runtimeAcquisitionObservation);savePartial();\n    })();\n    if(discovery)gap.catch(error=>{restart.runtimeAcquisitionObservation={verdict:error.clinicalFailure?'FAIL':'UNMEASURED',code:typedCode(error)};if(error.clinicalFailure)out.hardFailure={stage:'runtime-recovery',code:typedCode(error)};savePartial();});")
    change("})().catch(e => { console.error('probe failed', e && e.stack); process.exit(1); });", "})().catch(e => {if(discovery){retainedOut=retainedOut||{};if(e.clinicalFailure)retainedOut.hardFailure={stage:'runtime-recovery',code:typedCode(e)};retainedOut.failure={code:typedCode(e),verdict:e.clinicalFailure?'FAIL':'UNMEASURED'};savePartial();} console.error('probe failed', discovery?typedCode(e):e && e.stack); process.exit(1); });")
    return source
