"""Generate a public-traffic-only variant of the exact joined stock probe."""
from pathlib import Path
import hashlib
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'm7-joined'))
from probe import generate as joined_generate

RECOVERY = r'''
  if (args.restart === '1') {
    fs.writeFileSync(path.join(signalDir, '.restart-ready'), 'ready');
    const until=Date.now()+120000;
    while(!fs.existsSync(path.join(signalDir,'.restart-begin'))) {
      if(Date.now()>until)throw Error('EXTERNAL_RESTART_NOT_RELEASED'); await sleep(50);
    }
    const r0=Date.now();const arms=new Map(sockets.map(s=>[s,{connects:s.connects,disconnectCount:s.disconnectCount}]));
    fs.writeFileSync(path.join(signalDir,'.restart-armed'),String(r0));
    const restart={restartIso:new Date(r0).toISOString(),firstServedMs:{},measurementClock:'generator wall clock; controller/SSH delay included'};
    let restartCommandMs=null;
    const commandDone=(async()=>{
      const deadline=Date.now()+150000;
      while(!fs.existsSync(path.join(signalDir,'.restart-command'))) {
        if(Date.now()>deadline)throw Error('EXTERNAL_RESTART_COMMAND_NOT_OBSERVED');await sleep(50);
      }
      const value=JSON.parse(fs.readFileSync(path.join(signalDir,'.restart-command'),'utf8'));
      if(value.status!=='PASS'||!Number.isFinite(value.commandMs)||value.commandMs<0)throw Error('EXTERNAL_RESTART_COMMAND_FAILED');
      restartCommandMs=value.commandMs;
    })();
    const pick=[...new Set([0,Math.floor(tenants.length/2),tenants.length-1])];
    const served=Promise.all(pick.map(async i=>{
      await sleep(500);const seen={};
      while(Date.now()-r0<EVAL_TIMEOUT) {
        const at=Date.now(),r=await new Promise(resolve=>{const req=http.get({host:base.hostname,port:base.port,path:'/api/v1/entries.json?count=1&token='+encodeURIComponent(tenants[i].token),headers:{host:tenants[i].host},agent:plainAgent,timeout:5000},res=>{res.resume();res.on('end',()=>resolve(res.statusCode));});req.on('timeout',()=>req.destroy());req.on('error',()=>resolve(0));});
        seen[r]=(seen[r]||0)+1;
        if(r===200&&restartCommandMs!==null){restart.firstServedMs[i]={ms:at-r0,statuses:seen};return;}
        await sleep(250);
      }
      restart.firstServedMs[i]={ms:null,statuses:seen};
    }));
    await commandDone;
    const recovered=()=>sockets.filter(s=>recoveredAfterRestart(s,arms.get(s),r0,restartCommandMs!==null)).length;
    while(Date.now()<r0+STOCK&&recovered()<sockets.length)await sleep(250);
    restart.stockRecovered=recovered();restart.stockAllRecoveredMs=restart.stockRecovered===sockets.length?Date.now()-r0:null;
    const r1=Date.now();retrying=true;for(const s of sockets)if(!s.connected)s.socket.connect();
    restart.retryAllRecoveredMs=null;
    while(Date.now()<r1+RECOVERY){if(recovered()===sockets.length){restart.retryAllRecoveredMs=Date.now()-r1;break;}await sleep(250);}
    restart.retryRecovered=recovered();restart.sockets=sockets.length;await commandDone;
    restart.restartCommandMs=restartCommandMs;restart.restartCommandClock='app-local duration, supplied by trusted controller';
    restart.reasons={...reasons};const sd={};
    for(const at of serverDisconnectAt)if(at>=r0){const b=Math.floor((at-r0)/5000)*5;sd[b]=(sd[b]||0)+1;}
    restart.serverDisconnectsBy5s=sd;restart.serverDisconnectsBeforeRestart=serverDisconnectAt.filter(at=>at<r0).length;
    for(const s of sockets)s.socket.close();await served;out.restart=restart;
  }
'''

def replace_once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError('EXTERNAL_PROBE_SOURCE_ANCHOR_CHANGED')
    return text.replace(before, after)

def generate(root, target):
    target = Path(target)
    with tempfile.TemporaryDirectory() as scratch:
        joined = Path(scratch) / 'probe.js'
        provenance = joined_generate(root, joined)
        source = joined.read_text()
    source = replace_once(source, "const { execFileSync, spawnSync, execFile } = require('node:child_process');", "const {recoveredAfterRestart}=require('./recovery.cjs');")
    source = replace_once(source, 'const s = { index, frames: [], connected: false, connects: 0, serverDisconnects: 0 };', 'const s = { index, frames: [], connected: false, connects: 0, serverDisconnects: 0, disconnectCount: 0, connectionFrames: [] };')
    source = replace_once(source, "s.connected = false; reasons[reason]", "s.connected = false; s.disconnectCount++; reasons[reason]")
    source = replace_once(source, 'const at = Date.now(); s.frames.push(at);', 'const at = Date.now(); s.frames.push(at); s.connectionFrames.push({at,connection:s.connects,disconnectCount:s.disconnectCount});')
    source = replace_once(source, 'p.latencies.push(at - p.sent);', 'p.latencies.push(performance.now() - p.sent);')
    source = replace_once(source, 'const p = { sent: Date.now(),', 'const p = { sent: performance.now(),')
    begin = source.index("const [project, envFile, ...composeFiles]")
    end = source.index('const sleep =', begin)
    source = source[:begin] + source[end:]
    begin = source.index('const psqlAsync =')
    end = source.index('const pct =', begin)
    source = source[:begin] + source[end:]
    begin = source.index('  const w0 = Date.now();')
    end = source.index('  const writers =', begin)
    source = source[:begin] + "  const w0 = Date.now(); const byTenant = {}; const writes = { ok: 0, failed: 0 };\n" + source[end:]
    source = replace_once(source, "    const e = { tenant: t.id, sent: p.sent, acked: null, stamp: null, evaluatedAt: null }; evalPending.push(e);", '')
    source = replace_once(source, ' e.acked = Date.now();', '')
    source = replace_once(source, ' e.evaluatedAt = -1;', '')
    source = replace_once(source, 'await sleep(10000); polling = false; await poller;', 'await sleep(10000);')
    source = replace_once(source, 'writeToEvaluationMs: stats(evalLatencies), evaluationMissedWithin120s: evalMissed.length,',
        "writeToEvaluationMs: {measurement:'UNMEASURED',reason:'Per-write SQL latency observer NOT_RUN; strict progress remains app-side; no cross-host latency inferred'},")
    begin = source.index("  if (args.restart === '1') {")
    end = source.index('  fs.writeFileSync(args.out,', begin)
    source = source[:begin] + RECOVERY + '\n' + source[end:]
    executable = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('//'))
    if any(token in executable for token in ('child_process', 'psqlAsync', 'composeArgs', 'recoveryObserve', 'execFile', 'docker')):

        raise RuntimeError('EXTERNAL_PROBE_PRIVATE_AUTHORITY_REMAINED')
    source = source.replace("(async () => {", "let lagExpected=Date.now()+1000;const lagTimer=setInterval(()=>{const at=Date.now();fs.appendFileSync(path.join(signalDir,'event-loop.jsonl'),JSON.stringify({at,lagMs:Math.max(0,at-lagExpected)})+'\\n');lagExpected=at+1000;},1000);lagTimer.unref();\n(async () => {",1)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.write_text(source)
    return {'baseJoined': provenance, 'adaptedSha256': hashlib.sha256(source.encode()).hexdigest(),
            'profile': 'joined-external-generator-v1', 'traffic': 'exact stock polling/authorization/frame/write paths',
            'writeToEvaluationMs': 'UNMEASURED', 'privateAuthority': False}
