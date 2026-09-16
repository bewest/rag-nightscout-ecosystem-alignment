// Repro 5: drive the CONNECT state machine with a simulated clock and a fake
// Dexcom. No network, no credentials. NC_ROOT selects which connect to load.
const NC = process.env.NC_ROOT;
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const {interpret} = require(CRM+'/node_modules/xstate');

// Minimal virtual clock implementing xstate's Clock interface.
function VirtualClock () {
  let now = 0, seq = 0; const timers = new Map();
  return {
    now: () => now,
    setTimeout (fn, ms) { const id = ++seq; timers.set(id, {at: now + (ms||0), fn}); return id; },
    clearTimeout (id) { timers.delete(id); },
    async increment (ms) {
      const target = now + ms;
      for (;;) {
        let next = null;
        for (const [id, t] of timers) if (t.at <= target && (next === null || t.at < timers.get(next).at)) next = id;
        if (next === null) break;
        const t = timers.get(next); timers.delete(next); now = t.at; t.fn();
        await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
      }
      now = target;
    }
  };
}

const builder = require(NC + '/lib/builder');
const dexcomshare = require(NC + '/lib/sources/dexcomshare');

const MIN = 60*1000;
function run (label, program, minutes) {
  const counts = {auth:0, login:0, glucose:0, other:0};
  const events = [];
  const fakeAxios = { create: () => ({ post: (path, body, cfg) => {
    let kind = /Authenticate/.test(path) ? 'auth' : /LoginPublisher/.test(path) ? 'login' : /LatestGlucose/.test(path) ? 'glucose' : 'other';
    counts[kind]++;
    const r = program(kind, counts, clock.now());
    if (r instanceof Error) return Promise.reject(r);
    return Promise.resolve({data: r});
  }})};
  const stored = [];
  const persister = (batch) => { stored.push(...(batch.entries||[])); return Promise.resolve(known()); };
  let lastEntryDate = new Date(Date.now() - 6*MIN);
  function known(){ return { entries: lastEntryDate }; }
  persister.gap_for = () => Promise.resolve(known());
  const log = { debug(){}, error(...a){ events.push('ERROR ' + a[0]); }, info(){}, warn(){} };

  const clock = VirtualClock();
  const make = builder({ output: persister, logger: log });
  const impl = dexcomshare({shareAccountName:'synthetic', sharePassword:'synthetic'}, fakeAxios, log);
  impl.generate_driver(make);
  const actor = interpret(make(), {clock});
  actor.start();
  actor.send({type:'START'});

  // advance in 1s ticks so promise microtasks interleave
  return (async () => {
    for (let t=0; t<minutes; t++) { await clock.increment(60*1000); }
    actor.stop();
    console.log(`\n### ${label}  (${minutes} simulated minutes)`);
    console.log('   vendor requests:', JSON.stringify(counts));
    console.log('   entries persisted:', stored.length);
    if (events.length) console.log('   logged errors:', events.length, '| first:', events[0]);
    console.log('   poller state after run: authentications=%s authorizations=%s auth_errors=%s authz_errors=%s',
      actor.getSnapshot().context.authentications, actor.getSnapshot().context.authorizations,
      actor.getSnapshot().context.authentication_errors, actor.getSnapshot().context.authorization_errors);
    return counts;
  })();
}

const SAMPLE = (n) => Array.from({length:n}, (_,i) => ({ WT:`/Date(${Date.now()- (n-i)*5*MIN})/`, ST:'/Date(0)/', DT:'/Date(0)/', Trend:4, Value:100+i }));

(async () => {
  console.log('connect under test:', NC);
  await run('A. happy path — is the session reused across cycles?',
    (kind) => kind==='auth' ? 'ACCT' : kind==='login' ? 'SESSION-1' : SAMPLE(1), 60);

  let glucoseCalls = 0;
  await run('B. session goes stale mid-poll (glucose 401 after the 3rd fetch) — does it recover without a restart?',
    (kind, c) => {
      if (kind==='auth') return 'ACCT';
      if (kind==='login') return 'SESSION-' + c.login;
      if (c.glucose > 3 && c.glucose <= 5) { const e=new Error('Request failed with status code 401'); e.response={status:401,data:{Code:'SessionIdNotFound'}}; return e; }
      return SAMPLE(1);
    }, 60);

  await run('C. wrong credentials — auth rejects forever',
    (kind) => { if (kind==='auth'){ const e=new Error('Request failed with status code 401'); e.response={status:401,data:{Code:'SSO_AuthenticateAccountNotFound'}}; return e;} return SAMPLE(1); }, 60);

  await run('D. vendor returns an unexpected shape (object, not array)',
    (kind) => kind==='auth' ? 'ACCT' : kind==='login' ? 'SESSION-1' : {Code:'MonitoringSessionNotActive', Message:'x'}, 30);

  await run('E. vendor returns the new G7-era object from Authenticate',
    (kind) => kind==='auth' ? {accountId:'ACCT-OBJ', name:'x'} : kind==='login' ? 'SESSION-1' : SAMPLE(1), 30);
})();
