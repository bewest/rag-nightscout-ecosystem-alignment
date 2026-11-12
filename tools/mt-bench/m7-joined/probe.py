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
    start = source.index("    const gap = (async () => {")
    end = source.index("    // Edge after the role restart:", start)
    source = source[:start] + r'''    const gap = (async () => {
      const first = new Map(); const sample = { cadenceMs: 15000, calls: 0, bytes: 0, wallMs: 0, failures: 0 };
      const inspect = "require('./deploy/multitenant/load-env');const own=require('./lib/server/internal-api/listener-config').resolve(['evaluator'],process.env);require('./lib/server/internal-api/clients').evaluatorInspection(own.peer('evaluator',{maxBytes:16777216,timeoutMs:5000})).inspectEvaluator({}).then(value=>console.log(JSON.stringify(value))).catch(()=>{process.exitCode=1;});";
      while (Date.now() - r0 < EVAL_TIMEOUT) {
        if (restart.healthyMs.evaluator == null) { await sleep(1000); continue; }
        const before=Date.now(); const raw=await execAsync([...composeArgs,'exec','-T','evaluator','node','-e',inspect]);
        sample.calls++;sample.bytes+=Buffer.byteLength(raw);sample.wallMs+=Date.now()-before;
        let view;try{view=JSON.parse(raw);}catch{sample.failures++;}
        if(view && Array.isArray(view.tenants))for(const row of view.tenants)if(row.ready===true && row.cycles>0 && !first.has(row.tenant))first.set(row.tenant,Date.now()-r0);
        if(first.size>=tenants.length)break;
        await sleep(sample.cadenceMs);
      }
      const values=[...first.values()].sort((a,b)=>a-b);
      restart.runtimeAcquisitionObservation={source:'private evaluator-inspection ready && cycles>0 in restarted process; not a clinical-equivalence assertion',
        observed:first.size,expected:tenants.length,missing:tenants.length-first.size,maxObservedMs:values.at(-1)||null,sampling:sample};
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
    target = Path(target)
    target.write_text(source)
    return {"baseline": str(baseline.relative_to(root)), "baselineSha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            "adaptedSha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "changes": ["actual explicit replica restart roster", "replace lifecycle lease proxy with sparse runtime acquisition observation", "separate hot/cold tenant write-to-frame distributions"]}
