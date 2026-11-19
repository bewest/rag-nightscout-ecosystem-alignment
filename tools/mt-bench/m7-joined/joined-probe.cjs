#!/usr/bin/env node
'use strict';
// Capacity-campaign socket and latency probe (Node; socket.io-client from a core checkout via NODE_PATH).
// Synthetic data only. Built from tools/mt-bench/realtime-perf/measure.js and perf-db's eval-gap.js.
//
// 1. Exchanges each tenant's data token for a JWT and opens PER stock-browser sockets per tenant
//    (polling, `authorize` with the JWT, no reconnect after a server-initiated disconnect),
//    staggered OPEN ms apart; waits for every socket's first frame (prime), then touches --signal.
// 2. Window (until <signal dir>/.restart exists): one probe sgv every PROBE ms, round robin over the
//    tenants (device <runid>-probe, counted by the stored-count oracle). For each probe write:
//      write->frame: POST sent to a dataUpdate frame carrying that sgv, per socket of the tenant;
//      write->evaluation: POST sent to the first 1 s poll (superuser psql in the postgres container)
//        where the evaluator's checkpoint for the tenant has reached the write clock's stamp read
//        after the POST was acknowledged. Resolution about 1 s.
// 3. Full restart: `docker compose restart api realtime evaluator tenant-admin` (timed), then
//      per role time to healthy; first served request for three tenants (250 ms);
//      evaluation gap (eval-gap.js definition): per tenant, the first evaluator window operation
//        by a post-restart evaluator backend that appears after the evaluator is healthy;
//      stock socket recovery: sockets connected again with a frame after the restart, within STOCK_MS;
//        then every dark socket reconnects at once (retry flood) until all recover or RECOVERY_MS.
//
//   probe.js --base URL --tenants FILE --compose SPEC --runid ID --per 2 --open 5 --window S
//            --probeEvery 3000 --restart 1 --evalTimeout 900 --out FILE --signal FILE
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { execFile } = require('node:child_process');
const { io } = require(process.env.M7_GENERATOR_ROOT?path.join(process.env.M7_GENERATOR_ROOT,'node_modules/socket.io-client'):'socket.io-client');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (i % 2 ? a : [...a, [v.replace(/^--/, ''), all[i + 1]]]), []));
const base = new URL(args.base);
const tenants = JSON.parse(fs.readFileSync(args.tenants, 'utf8'));
const PER = Number(args.per ?? 2), OPEN = Number(args.open ?? 5), PROBE = Number(args.probeEvery ?? 3000);
const TOTAL=Number(args.clients??tenants.length*PER);if(!Number.isSafeInteger(TOTAL)||TOTAL<0||TOTAL>0xffffffff||!tenants.length||new Set(tenants.map(t=>t.id)).size!==tenants.length)throw Error('M7_VIEWER_TOTAL_RANGE');const viewers=tenants.map((_,i)=>Math.floor(TOTAL/tenants.length)+(i<TOTAL%tenants.length?1:0));
const EVAL_TIMEOUT = Number(args.evalTimeout ?? 900) * 1000;
const STOCK = Number(process.env.STOCK_MS || 300000), RECOVERY = Number(process.env.RECOVERY_MS || 120000);
const completionSource=process.env.M7_COMPLETION_SOURCE?JSON.parse(process.env.M7_COMPLETION_SOURCE):null;
const completionOracle=completionSource?require('./completed-oracle.cjs'):null;const lag=require('./durable-lag.cjs');const timing=completionSource?require('./clinical-timing.cjs'):null;const oracleCost={queries:0,bytes:0,elapsedMs:0,missing:0,durablePendingPeak:0};
const signalDir = path.dirname(args.signal);
const discovery=process.env.M7_RUN_PURPOSE==='discovery';
const budget=discovery&&process.env.M7_PROBE_LEDGER!==undefined?JSON.parse(process.env.M7_PROBE_LEDGER):undefined;
const writeEvidence=(name,value)=>{
  const file=path.join(signalDir,name),data=JSON.stringify(value)+'\n';
  if(budget){
    if(Buffer.byteLength(data)>budget.maxBytes)throw Error('M7_PROBE_LEDGER_BYTE_BUDGET');
    fs.writeFileSync(file+'.new',data,{mode:0o600});fs.renameSync(file+'.new',file);
  }else fs.writeFileSync(file,data);
};
let retainedOut;
const hardProgress=value=>value?.verdict==='FAIL'&&!['M7_EVALUATOR_PROGRESS_ERROR','M7_EVALUATOR_PROGRESS_HIDDEN_FAILURE'].includes(value.code);
const typedCode=e=>/^M7_[A-Z_]+$/.test(e?.message||'')?e.message:'M7_PROBE_OBSERVATION_UNAVAILABLE';
const savePartial=()=>{if(discovery&&retainedOut)fs.writeFileSync(args.out,JSON.stringify(retainedOut)+'\n');};
const transport = require('./probe-transport.cjs')({args,fs,path,signalDir,execFile,process,discovery,completionSource});
const {psqlAsync,composeArgs} = transport;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const lookup = (hostname, options, cb) => (options && options.all) ? cb(null, [{ address: base.hostname, family: 4 }]) : cb(null, base.hostname, 4);
const agent = new http.Agent({ keepAlive: true, lookup, maxSockets: Infinity });
const plainAgent = new http.Agent({ keepAlive: false });
const pct = (arr, p) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.ceil(p / 100 * s.length) - 1)]; };
const stats = arr => ({ n: arr.length, p50: pct(arr, 50), p95: pct(arr, 95), p99: pct(arr, 99), max: arr.length ? Math.max(...arr) : null });
const log = (k, v) => console.log(new Date().toISOString() + ' ' + k + ' ' + JSON.stringify(v));

function request (method, t, p, body, timeout = 30000) {
  return new Promise(resolve => {
    const data = body ? JSON.stringify(body) : null;
    const requestStart=performance.now(); const req = http.request({ host: base.hostname, port: base.port, method, path: p, agent,
      headers: { host: t.host, accept: 'application/json', ...(data ? { 'content-type': 'application/json', 'content-length': Buffer.byteLength(data) } : {}) }, timeout },
    res => { const responseMono=performance.now(),responseAt=Date.now(); let b = ''; res.on('data', d => { b += d; }); res.on('end', () => resolve({ status: res.statusCode, body: b, responseMono, responseAt, requestStart })); });
    req.on('error', () => resolve({ status: 0 })); req.on('timeout', () => { req.destroy(); resolve({ status: 0 }); });
    req.end(data || undefined);
  });
}
async function exchange (t) {
  for (let k = 0; k < 5; k++) {
    const r = await request('GET', t, '/api/v2/authorization/request/' + encodeURIComponent(t.token), null, 60000);
    if (r.status === 200) return JSON.parse(r.body).token;
    await sleep(1000 * (k + 1));
  }
  throw new Error('exchange refused');
}

// Inlined into the generated local and Kubernetes probes. The same stock
// Socket.IO callbacks and authorization exchange remain responsible for frames.
async function primeViewers(out, selection) {
  const { opensPerSecond, stallSeconds, transport, scenario } = selection;
  if (!(Number.isFinite(opensPerSecond) && opensPerSecond > 0 &&
        Number.isSafeInteger(stallSeconds) && stallSeconds > 0 &&
        ['websocket-first', 'polling'].includes(transport) &&
        ['ordinary', 'simultaneous-reconnect'].includes(scenario)))
    throw Error('M7_VIEWER_SETUP_CONFIGURATION');
  delete out.args.open;  // Only the legacy actor uses the --open millisecond interval.
  const start = performance.now();
  let lastProgress = start, stopped = false, timer;
  const progress = out.viewerSetup = {
    ...selection, requested: TOTAL, exchanged: 0, opened: 0,
    initial: { connected: 0, firstFrames: 0, transports: {} },
    reconnect: null, elapsedMs: 0, status: 'RUNNING'
  };
  let epoch = progress.initial;
  const stallMs = stallSeconds * 1000;
  function check() {
    if (stopped || performance.now() - lastProgress >= stallMs)
      throw Error('M7_VIEWER_SETUP_STALLED');
  }
  function advanced() {
    const now = performance.now();
    if (stopped || now - lastProgress >= stallMs) return false;
    lastProgress = now;
    return true;
  }
  function observe(slot, counters) {
    let connected = false, received = false;
    slot.once('connect', () => {
      if (!advanced()) return;
      connected = true;
      counters.connected++;
    });
    slot.on('dataUpdate', function firstFrame() {
      if (received || !connected || !slot.connected || !advanced()) return;
      received = true;
      counters.firstFrames++;
      const name = slot.io.engine.transport.name;
      counters.transports[name] = (counters.transports[name] || 0) + 1;
      slot.off('dataUpdate', firstFrame);
    });
  }
  async function work() {
    const jwts = new Array(tenants.length);
    let nextTenant = 0;
    const x0 = performance.now();
    // Bound concurrent exchanges independently of the connection ramp.
    await Promise.all(Array.from({ length: Math.min(16, tenants.length) }, async () => {
      while (nextTenant < tenants.length) {
        check();
        const index = nextTenant++;
        if (viewers[index] === 0) continue;
        jwts[index] = await exchange(tenants[index]);
        if (!advanced()) throw Error('M7_VIEWER_SETUP_STALLED');
        progress.exchanged++;
      }
    }));
    out.exchangeMs = performance.now() - x0;
    let nextOpen = performance.now();
    for (let i = 0; i < tenants.length; i++) {
      for (let n = 0; n < viewers[i]; n++) {
        while (performance.now() < nextOpen) {
          check();
          await sleep(Math.min(2147483647, Math.ceil(nextOpen - performance.now())));
        }
        check();
        open(i, jwts[i]);
        observe(sockets.at(-1).socket, epoch);
        progress.opened++;
        // Never catch up a delayed scheduler by opening a burst.
        nextOpen = performance.now() + 1000 / opensPerSecond;
      }
    }
    async function waitForFrames() {
      while (epoch.firstFrames !== TOTAL || sockets.some(s => !s.connected)) {
        check();
        await sleep(Math.min(100, stallMs));
      }
      check();
    }
    await waitForFrames();
    if (scenario === 'simultaneous-reconnect') {
      if (!TOTAL) throw Error('M7_VIEWER_RECONNECT_EMPTY');
      epoch = progress.reconnect = { connected: 0, firstFrames: 0, transports: {} };
      for (const s of sockets) s.socket.disconnect();
      for (const s of sockets) observe(s.socket, epoch);
      for (const s of sockets) s.socket.connect();
      await waitForFrames();
    }
  }
  // Detect a stall even while the actor is waiting for a pending HTTP response.
  const expiry = new Promise((_, reject) => {
    function arm() {
      const left = lastProgress + stallMs - performance.now();
      if (left <= 0) reject(Error('M7_VIEWER_SETUP_STALLED'));
      else timer = setTimeout(arm, Math.min(2147483647, Math.ceil(left)));
    }
    arm();
  });
  try {
    await Promise.race([work(), expiry]);
    progress.status = 'COMPLETE';
  } catch (error) {
    progress.status = 'INCOMPLETE';
    progress.code = error.message === 'M7_VIEWER_SETUP_STALLED'
      ? error.message : 'M7_VIEWER_SETUP_INCOMPLETE';
    progress.reasons = { ...reasons };
    for (const s of sockets) s.socket.close();
    throw Error(progress.code);
  } finally {
    stopped = true;
    clearTimeout(timer);
    progress.elapsedMs = performance.now() - start;
    progress.lastProgressElapsedMs = lastProgress - start;
    savePartial();
  }
}

const viewerSetup = args.viewerSetup ? JSON.parse(args.viewerSetup) : null;
const sockets = [], reasons = {}, pending = new Map();
let retrying = false;
const serverDisconnectAt = []; // client-observed server-initiated disconnects (all phases), for the timeline
function open (index, jwt) {
  const t = tenants[index];
  const s = { index, frames: [], connected: false, connects: 0, serverDisconnects: 0 };
  s.socket = io('http://' + t.host + ':' + base.port, { transports: viewerSetup?.transport === 'websocket-first' ? ['websocket','polling'] : ['polling'], tryAllTransports: true, agent, reconnection: true, reconnectionDelay: 500, reconnectionDelayMax: 5000, timeout: 20000 });
  s.socket.on('connect', () => { s.connected = true; s.connects++; s.socket.emit('authorize', { client: 'web', token: jwt, history: 1, status: true }, () => {}); });
  s.socket.on('disconnect', reason => {
    s.connected = false; reasons[reason] = (reasons[reason] || 0) + 1;
    if (reason === 'io server disconnect') { s.serverDisconnects++; serverDisconnectAt.push(Date.now()); if (retrying) setTimeout(() => s.socket.connect(), 1000 + Math.random() * 4000); }
  });
  s.socket.on('connect_error', e => { reasons['connect_error:' + e.message] = (reasons['connect_error:' + e.message] || 0) + 1; });
  s.socket.on('dataUpdate', frame => {
    const at = Date.now(); s.frames.push(at);
    if (transport.frames) {
      const rows = frame?.sgvs || [], evidence = transport.frames;
      if (evidence.rows.length < 4096) {
        const ids = rows.slice(0,1024).map(value => String(value._id));
        evidence.rows.push({tenant:t.id,socket:sockets.indexOf(s),ids,at});
        if (ids.length !== rows.length) evidence.overflow = true;
      } else evidence.overflow = true;
    }
    for (const sgv of frame?.sgvs || []) { const proof=pending.get(t.id+':'+sgv.mills);if(proof&&completionSource){proof.clientFrames??=new Map();if(!proof.clientFrames.has(s))proof.clientFrames.set(s,{atMono:performance.now(),socket:sockets.indexOf(s),connects:s.connects,transportId:s.socket.id,sgv:{_id:String(sgv._id),mills:sgv.mills,mgdl:sgv.mgdl}});} const p = pending.get(t.id + ':' + sgv.mills); if (p && !p.seen.has(s)) { p.seen.add(s); p.latencies.push(at - p.sent); } }
  });
  sockets.push(s);
}

(async () => {
  const out = { args: { per: PER, open: OPEN, probeEveryMs: PROBE, tenants: tenants.length, stockMs: STOCK, recoveryMs: RECOVERY, evalTimeoutMs: EVAL_TIMEOUT } };
  retainedOut=out; if(discovery){out.runPurpose='discovery';savePartial();}
  const setupSeconds=Number(args.setupSeconds??300),setupStartedMono=performance.now();
  if(!Number.isSafeInteger(setupSeconds)||!Number.isSafeInteger(setupSeconds*1000)||setupSeconds<=0)throw Error('M7_PHASE_WINDOW_INVALID:setupSeconds');
  let t0 = Date.now();
  if (viewerSetup) { await primeViewers(out,viewerSetup); } else {
  const jwts = new Array(tenants.length);
  let next = 0; const x0 = Date.now();
  await Promise.all(Array.from({ length: 16 }, async () => { while (next < tenants.length) { const i = next++; try{jwts[i] = viewers[i]?await exchange(tenants[i]):null;}catch(error){if(!discovery)throw error; (out.exchangeUnavailable||=[]).push({tenantIndex:i,code:'M7_EXCHANGE_UNAVAILABLE'});savePartial();} } }));
  out.exchangeMs = Date.now() - x0;
  t0 = Date.now();
  for (let i = 0; i < tenants.length; i++) for (let k = 0; k < viewers[i]; k++) { if(!discovery||jwts[i])open(i, jwts[i]); if (OPEN) await sleep(OPEN); }
  while ((args.setupSeconds===undefined ? Date.now() - t0 < 300000 : performance.now()-setupStartedMono<setupSeconds*1000) && sockets.some(s => !s.frames.length && s.serverDisconnects === 0)) await sleep(250);
  }
  out.prime = { sockets: sockets.length, primed: sockets.filter(s => s.frames.length).length, dark: sockets.filter(s => !s.frames.length).length,
    serverDisconnected: sockets.filter(s => s.serverDisconnects).length, ms: Date.now() - t0, reasons: { ...reasons } };
  out.viewerBindings=sockets.map((s,socket)=>({socket,tenant:tenants[s.index].id}));
  log('prime', out.prime);savePartial();
  fs.writeFileSync(path.join(signalDir,'prime.json'),JSON.stringify(out.prime)); if(!discovery&&out.prime.primed!==TOTAL)throw new Error('M7_ESTABLISHED_SOCKETS_INCOMPLETE');
  fs.writeFileSync(args.signal, String(Date.now()));

  // Window: probe writes, write->frame and write->evaluation.
  const w0 = Date.now(); const evalPending = []; const evalLatencies = [], evalMissed = [];
  const byTenant = {}; const writes = { ok: 0, failed: 0 };
  const accounting=(discovery||process.env.M7_INPUT_ACCOUNTING==='1')?require('./probe-accounting.cjs').create({ids:tenants.map(t=>t.id),runId:args.runid,budget,persist:value=>writeEvidence('probe-accounting.json',value)}):null;
  let polling = true;
  const poller = (async () => {
    for (;;) {
      const open=evalPending.filter(e=>e.evaluatedAt===null &&
        (completionSource?timing.shouldPoll(e):Date.now()-e.sent<120000));
      if(!polling&&!open.length)break;
      if(open.length && completionSource){
        const ids=[...new Set(open.map(e=>e.tenant))];
        oracleCost.durablePendingPeak=Math.max(oracleCost.durablePendingPeak,open.filter(e=>e.acked!==null&&!e.durableObservation).length);
        const queryStart=performance.now();
        const query=completionOracle.query(completionSource,ids,args.runid);
        let raw;
        try { raw=await psqlAsync(query); }
        catch(error) {
          if(!discovery || error.message!=='M7_PROBE_SQL_OBSERVATION_UNAVAILABLE')throw error;
          out.sqlObserverFailure={verdict:'UNMEASURED',code:error.message};
          timing.checkpoint(signalDir,evalPending,pending);
          return;
        }
        const queryEnd=performance.now();oracleCost.queries++;oracleCost.bytes+=Buffer.byteLength(raw);oracleCost.elapsedMs+=queryEnd-queryStart;if(!raw)oracleCost.missing++;
        const rows=new Map(raw.split('\n').filter(Boolean).map(line=>{const row=JSON.parse(line);return [row.tenant,row];}));
        const foreign=[...rows.keys()].some(id=>!ids.includes(id));
        for(const e of open){
          if(foreign){e.hardClinical='M7_COMPLETION_FOREIGN_TENANT';continue;}
          e.lastQueryStartMono=queryStart;
          const row=rows.get(e.tenant);if(!row)continue;
          if(e.stamp===null)e.stamp=row.stamp;
          if(completionSource.native&&!e.nativeTarget){try{e.nativeTarget=require('./native-observation.cjs').snapshot(row,completionSource);}catch{}}
          const proof=pending.get(e.tenant+':'+e.date);
          const durable=completionOracle.assessDurable(row,e,completionSource);
          lag.observe(e,durable,queryStart,queryEnd);
          const result=completionOracle.assess(row,e,[...(proof?.clientFrames?.values()||[])],viewers[tenants.findIndex(t=>t.id===e.tenant)],completionSource);
          e.completion=result; if (transport.frames) e.rawRow=row;
          timing.observe(e,result,queryStart);
          if(e.completion.ready){e.evaluatedAt=Date.now();evalLatencies.push(e.evaluatedAt-e.sent);}
        }
        timing.checkpoint(signalDir,evalPending,pending);
      }else if (open.length) {
        const ids = [...new Set(open.map(e => e.tenant))].map(id => "'" + id + "'").join(',');
        const rows = await psqlAsync(`SELECT w.tenant_id, w.last_stamp, coalesce(c.checkpoint, -1) FROM nsdemo_clock.tenant_write_clock w LEFT JOIN nsdemo_eval_checkpoint.tenant_consumer_checkpoint c ON c.tenant_id = w.tenant_id AND c.consumer = 'evaluator-compose-demo' WHERE w.tenant_id IN (${ids})`);
        const now = Date.now(); const seen = new Map();
        for (const line of rows.split('\n').filter(Boolean)) { const [id, stamp, cp] = line.split('\t'); seen.set(id, { stamp: Number(stamp), cp: Number(cp) }); }
        for (const e of open) {
          const v = seen.get(e.tenant); if (!v || e.acked === null) continue;
          if (e.stamp === null) { if (now >= e.acked) e.stamp = v.stamp; else continue; }
          if (v.cp >= e.stamp) { e.evaluatedAt = now; evalLatencies.push(now - e.sent); }
        }
      }
      await sleep(1000);
    }
    for (const e of evalPending) if (e.evaluatedAt === null) evalMissed.push(e.tenant);
  })();
  const writers = []; let k = 0; const stride = tenants.length > 7 ? 7919 % tenants.length || 1 : 1;
  while (!out.sqlObserverFailure && !fs.existsSync(path.join(signalDir, '.restart')) && (args.maxWrites===undefined || k<Number(args.maxWrites))) {
    const i = (k * stride) % tenants.length; k++;
    const t = tenants[i]; const date = Date.now() - 60000 + (k % 1000);
    const p = { sentMono:performance.now(), sent: Date.now(), seen: new Set(), latencies: [], expected: viewers[i] };
    pending.set(t.id + ':' + date, p);
    const e = { clientProofVersion:3, expectedSockets:sockets.flatMap((s,i)=>s.index===tenants.indexOf(t)?[i]:[]), date, sentMono:p.sentMono, tenant: t.id, sent: p.sent, acked: null, stamp: null, evaluatedAt: null }; evalPending.push(e);
    const attempt=accounting?accounting.begin(t.id):null;
    writers.push(request('POST', t, '/api/v1/entries?token=' + encodeURIComponent(t.token),
      [{ type: 'sgv', sgv: 100 + (date % 50), date, dateString: new Date(date).toISOString(), direction: 'Flat', device: args.runid + '-probe' }]).then(r => {
      if(accounting)accounting.settle(attempt,r.status);
      if (r.status === 200) { writes.ok++; byTenant[t.id] = (byTenant[t.id] || 0) + 1; e.acked = r.responseAt; e.acceptedMono=r.responseMono; e.sentMono=r.requestStart; } else { writes.failed++; e.evaluatedAt = -1; }
    }));
    if(completionSource){const until=Date.now()+PROBE;while(Date.now()<until&&!fs.existsSync(path.join(signalDir,'.restart')))await sleep(Math.min(1000,until-Date.now()));}else await sleep(PROBE);
  }
  if(accounting)accounting.close();
  await Promise.all(writers); await sleep(10000); polling = false; await poller;
  const w1 = Date.now();
  const latencies = [...pending.values()].flatMap(p => p.latencies);
  const firstSocket = [...pending.values()].filter(p => p.latencies.length).map(p => Math.min(...p.latencies));
  out.window = { hotTenantWriteToFrameMs: stats([...pending].filter(([key])=>key.startsWith(tenants[0].id+':')).flatMap(([,value])=>value.latencies)), coldTenantWriteToFrameMs: stats([...pending].filter(([key])=>!key.startsWith(tenants[0].id+':')).flatMap(([,value])=>value.latencies)), ms: w1 - w0, writes, sockets: sockets.length, connectedAtEnd: sockets.filter(s => s.connected).length,
    serverDisconnectsInWindow: sockets.filter(s => s.serverDisconnects).length,
    writeToFrameMs: stats(latencies), writeToFirstFrameMs: stats(firstSocket), deliveredFrames: latencies.length,
    expectedFrames: [...pending.values()].reduce((n,p)=>n+p.expected,0),
    writeToEvaluationMs: stats(evalLatencies), evaluationMissedWithin120s: evalMissed.length, reasons: { ...reasons } };
  if(out.sqlObserverFailure)out.window.evaluationMissedWithin120s=null;
  savePartial();
  log('window', { w2f: out.window.writeToFrameMs, w2e: out.window.writeToEvaluationMs, delivered: out.window.deliveredFrames, expected: out.window.expectedFrames, writes });
  writeEvidence('fanout.json',{probeWrites:{byTenant}});

  if (args.restart === '1') {
    if(out.sqlObserverFailure){out.failure=out.sqlObserverFailure;} else {
    const evaluatorServices=JSON.parse(process.env.M7_EVALUATOR_SERVICES||'null');
    if(!Array.isArray(evaluatorServices)||!evaluatorServices.length||evaluatorServices.length>8)throw Error('M7_EVALUATOR_PROGRESS_INSTANCE_BOUND');
    const recoveryObserve=spec=>new Promise((resolve,reject)=>{
      const child=execFile(process.env.M7_PROGRESS_PYTHON, [path.join(__dirname,'evaluator_recovery.py')], {encoding:'utf8',timeout:920000,maxBuffer:1048576},(error,stdout)=>{
        let value;try{value=JSON.parse(stdout);}catch{return reject(Error('M7_EVALUATOR_RECOVERY_UNAVAILABLE'));}
        if(error||!value){if(discovery&&!hardProgress(value))return resolve(value||{verdict:'UNMEASURED',code:'M7_EVALUATOR_RECOVERY_UNAVAILABLE'});return reject(Object.assign(Error(value?.code||'M7_EVALUATOR_RECOVERY_UNAVAILABLE'),{clinicalFailure:hardProgress(value)}));}if(discovery&&hardProgress(value))return reject(Object.assign(Error(value.code||'M7_EVALUATOR_PROGRESS_ERROR'),{clinicalFailure:true}));resolve(value);
      });
      child.stdin.end(JSON.stringify({...spec,attribution:JSON.parse(process.env.M7_PROGRESS_ATTRIBUTION),composeArgs,services:evaluatorServices,ids:tenants.map(t=>t.id)}));
    });
    const recoveryBaseline=path.join(signalDir,'evaluator-recovery-baseline.private.json');
    const baselineObservation=await recoveryObserve({mode:'baseline',path:recoveryBaseline});
    const restartIso = new Date().toISOString(); const r0 = Date.now();
    fs.writeFileSync(path.join(signalDir, '.restart-at'), String(r0));
    const roles = JSON.parse(process.env.M7_RESTART_ROLES); if (!Array.isArray(roles) || !roles.length) throw new Error('M7_RESTART_ROLES_REQUIRED');
    const restartDone = require('./restart.cjs').restart({composeArgs,roles,at:r0}).then(value=>{restart.containerStarts=value.starts;return value.commandMs;});
    if(discovery)restartDone.catch(error=>{out.hardFailure={stage:'restart-custody',code:typedCode(error)};savePartial();});
    const restart = { restartIso, healthyMs: {}, firstServedMs: {} };if(discovery){out.restart=restart;savePartial();}
    let restartCommandMs = null; restartDone.then(ms => { restartCommandMs = ms; },error=>{if(discovery){out.hardFailure={stage:'restart',code:typedCode(error)};savePartial();}});
    // First served (3 tenants), every 250 ms, from the restart command's start.
    const pick = [...new Set([0, Math.floor(tenants.length / 2), tenants.length - 1])];
    const served = Promise.all(pick.map(async i => {
      await sleep(500); const seen = {};
      for (;;) {
        const at = Date.now();
        const r = await new Promise(resolve => { const req = http.get({ host: base.hostname, port: base.port, path: '/api/v1/entries.json?count=1&token=' + encodeURIComponent(tenants[i].token), headers: { host: tenants[i].host }, agent: plainAgent, timeout: 5000 }, res => { res.resume(); res.on('end', () => resolve(res.statusCode)); }); req.on('timeout', () => req.destroy()); req.on('error', () => resolve(0)); });
        seen[r] = (seen[r] || 0) + 1;
        if (r === 200 && restartCommandMs !== null) { restart.firstServedMs[i] = { ms: at - r0, statuses: seen }; return; }
        if (at - r0 > 900000) { restart.firstServedMs[i] = { ms: null, statuses: seen }; return; }
        await sleep(250);
      }
    }));
    // Role health and the evaluation gap (eval-gap.js), polled every second.
    const backends = new Set(), atReady = new Map(), first = new Map(); let evalReadyMs = null;
    // Role health: its own loop (250 ms), so the database polls below cannot delay it. Also records the
    // Docker healthcheck's own first passing run after the restart (Health.Log Start), the reference time.
    // (Before 2026-11-11 23:30Z this was polled inside the evaluation loop, one database round per pass.)
    restart.healthCheckPassMs = {}; const loopMs = [];
    const execAsync = argv => new Promise(resolve => transport.docker(argv, { encoding: 'utf8' }, (e, out) => resolve(e ? '' : out.trim())));
    const health = (async () => {
      const ids = {};
      while (Date.now() - r0 < EVAL_TIMEOUT && roles.some(role => restart.healthyMs[role] == null)) {
        const now = Date.now() - r0;
        if (restartCommandMs !== null) await Promise.all(roles.filter(role => restart.healthyMs[role] == null).map(async role => {
          ids[role] ||= await execAsync([...composeArgs, 'ps', '-q', role]);
          const raw = ids[role] ? await execAsync(['inspect', '--format', '{{.State.Status}} {{if .State.Health}}{{json .State.Health}}{{end}}', ids[role]]) : '';
          const sp = raw.indexOf(' '), status = sp < 0 ? raw : raw.slice(0, sp); let h = null; try { h = JSON.parse(raw.slice(sp + 1)); } catch {}
          if (status === 'running' && h && h.Status === 'healthy') {
            restart.healthyMs[role] = now;
            const pass = (h.Log || []).filter(e => e.ExitCode === 0 && Date.parse(e.Start) > r0).map(e => Date.parse(e.End) - r0).sort((a, b) => a - b)[0];
            restart.healthCheckPassMs[role] = pass ?? null;
          }
        }));
        await sleep(250);
      }
    })();
    const gap = (async () => {
      await restartDone;
      while(Date.now()-r0<EVAL_TIMEOUT && evaluatorServices.some(role=>restart.healthyMs[role]==null))await sleep(1000);
      restart.runtimeAcquisitionObservation=await recoveryObserve({mode:'recovery',baseline:recoveryBaseline,path:path.join(signalDir,'evaluator-recovery.private.json'),deadlineMs:r0+EVAL_TIMEOUT});
      restart.runtimeAcquisitionObservation.baselineObservation=baselineObservation;
      log('runtimeAcquisitionObservation',restart.runtimeAcquisitionObservation);savePartial();
    })();
    if(discovery)gap.catch(error=>{restart.runtimeAcquisitionObservation={verdict:error.clinicalFailure?'FAIL':'UNMEASURED',code:typedCode(error)};if(error.clinicalFailure)out.hardFailure={stage:'runtime-recovery',code:typedCode(error)};savePartial();});
    // Edge after the role restart: nginx resolves its upstreams once (deploy nginx.conf), and the
    // restarted roles may hold different backend addresses. Record what the edge answers, then,
    // with CAP_RESTART_EDGE=1 (labelled variant), restart nginx too.
    await restartDone;
    const edgeCodes = [];
    for (let k = 0; k < 3; k++) {
      await sleep(2000);
      edgeCodes.push(await new Promise(resolve => { const req = http.get({ host: base.hostname, port: base.port, path: '/api/v1/status.json', headers: { host: tenants[0].host }, agent: plainAgent, timeout: 5000 }, res => { res.resume(); res.on('end', () => resolve(res.statusCode)); }); req.on('timeout', () => req.destroy()); req.on('error', () => resolve(0)); }));
    }
    restart.edgeAfterRoleRestart = edgeCodes;
    if (process.env.CAP_RESTART_EDGE === '1') {
      // Asynchronous since 2026-11-11 23:35Z: a synchronous restart blocked this process's event loop for the
      // command's duration (about 11 s when nginx waits out open connections), delaying every other measurement.
      const e0 = Date.now(); await new Promise(resolve => transport.docker([...composeArgs, 'restart', 'nginx'], () => resolve()));
      restart.edgeRestarted = { atMs: e0 - r0, commandMs: Date.now() - e0, async: true };
    }
    log('edge', { codes: edgeCodes, restarted: restart.edgeRestarted || null });
    const recovered = () => sockets.filter(s => s.connected && s.frames.some(at => at > r0)).length;
    while (Date.now() < r0 + STOCK && recovered() < sockets.length) await sleep(250);
    restart.stockRecovered = recovered(); restart.stockAllRecoveredMs = restart.stockRecovered === sockets.length ? Date.now() - r0 : null;
    const r1 = Date.now(); retrying = !viewerSetup;
    if(viewerSetup) restart.retryPolicy = {opensPerSecond:viewerSetup.opensPerSecond};

    for (const s of sockets) {
      if (s.connected) continue;
      if (viewerSetup && Date.now() - r1 >= RECOVERY) break;
      s.socket.connect();
      if (viewerSetup) await sleep(Math.min(Math.ceil(1000/viewerSetup.opensPerSecond),
                                            Math.max(0,r1+RECOVERY-Date.now())));
    }
    restart.retryAllRecoveredMs = null;
    while (Date.now() < r1 + RECOVERY) { if (recovered() === sockets.length) { restart.retryAllRecoveredMs = Date.now() - r1; break; } await sleep(250); }
    restart.retryRecovered = recovered(); restart.sockets = sockets.length; restart.restartCommandMs = restartCommandMs;
    restart.reasons = { ...reasons };
    // Server-initiated disconnects after the restart command, counted per 5 s from it.
    const sd = {}; for (const at of serverDisconnectAt) if (at >= r0) { const b = Math.floor((at - r0) / 5000) * 5; sd[b] = (sd[b] || 0) + 1; }
    restart.serverDisconnectsBy5s = sd; restart.serverDisconnectsBeforeRestart = serverDisconnectAt.filter(at => at < r0).length;
    log('sockets', { restartCommandMs, stock: restart.stockRecovered + '/' + sockets.length, stockAllMs: restart.stockAllRecoveredMs, retry: restart.retryRecovered, retryAllMs: restart.retryAllRecoveredMs });
    for (const s of sockets) s.socket.close();
    await served; await gap; await health;
    out.restart = restart;
    }
  }
  if(completionSource){
    if (transport.frames) out.kubernetesFrames=transport.frames;
    oracleCost.observationEndMono=performance.now();
    for(const e of evalPending){
      const frames=[...(pending.get(e.tenant+':'+e.date)?.clientFrames?.values()||[])];
      e.clinicalTiming=timing.assess(e,frames);
      e.completion={...e.completion,ready:e.clinicalTiming.delivered,
        code:e.clinicalTiming.observationProblem,assessedCode:e.semantic?.code,clinicalTiming:e.clinicalTiming};
    }
    out.durableOutputObservation=lag.summary(evalPending,pending,oracleCost,timing);
    const clinicalTiming=timing.summary(evalPending);
    out.completedOutput={clientFrames:{verdict:out.window.expectedFrames===0?'NOT_EXERCISED':evalPending.every(e=>e.completion?.ready)?'PASS':'UNMEASURED'},rosterTenants:tenants.length,witnessTenants:[...new Set(evalPending.map(e=>e.tenant))],
      clinicalTiming,witnessTenantCount:new Set(evalPending.map(e=>e.tenant)).size,
      ...(out.sqlObserverFailure?{observerFailure:out.sqlObserverFailure}:{}),
      witnesses:evalPending.map(e=>({tenant:e.tenant,date:e.date,stamp:e.stamp,acceptedAt:e.acked,requestToAcceptanceMs:e.clinicalTiming.requestToAcceptanceMs,requestStartedAt:e.sent,
        ...(transport.frames ? {clientProofVersion:e.clientProofVersion,expectedSockets:e.expectedSockets,sentMono:e.sentMono,
          rawRow:e.rawRow,clientObservations:[...(pending.get(e.tenant+':'+e.date)?.clientFrames?.values()||[])]} : {}),...e.completion})),
      probeCadenceMs:PROBE,scope:'sampled stored/output/client witnesses and selected BG-now mean; witnessTenants is the exercised subset, not all-roster clinical equivalence; uploader separate from ordinary k6 workload; any planned restart is qualified by its separate receipt'};
    for(const s of sockets)s.socket.close();
  }
  fs.writeFileSync(args.out, JSON.stringify(out, null, 2) + '\n');
  process.exit(out.sqlObserverFailure && args.restart==='1' ? 1 : 0);
})().catch(e => {if(discovery){retainedOut=retainedOut||{};if(e.clinicalFailure)retainedOut.hardFailure={stage:'runtime-recovery',code:typedCode(e)};retainedOut.failure={code:typedCode(e),verdict:e.clinicalFailure?'FAIL':'UNMEASURED'};savePartial();} console.error('probe failed', discovery?typedCode(e):e && e.stack); process.exit(1); });
