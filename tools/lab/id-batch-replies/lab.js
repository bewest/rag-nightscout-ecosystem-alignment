'use strict';
// ID-BATCH client-behaviour lab: what each uploader does with each candidate
// API v1 batch reply. Contributor-facing. Synthetic data only; never point it
// at a real site.
//
//   CRM_DIR=<proto/id-batch-replies worktree> IDB_MONGO=mongodb://127.0.0.1:27803 \
//     node tools/lab/id-batch-replies/lab.js [--out results/run.json]
//
// It boots the prototype build three times (WRITE_VALIDATION off, =reject,
// WRITE_IDENTIFIER=strict), each on its own database, and for every scenario
// x reply variant x client:
//   1. posts the client's batch to the real server, with the variant's opt-in
//      header (the harness plays a server whose default reply is that variant;
//      the client logic never sees the header),
//   2. hands the reply to the client's harness (clients.js, each rule cited
//      file:line) and re-sends what the client would re-send, for up to
//      CYCLES cycles,
//   3. reads MongoDB for how many records each sent item left (0, 1, 2+).
// nightscout-connect is run for real (connect-run.js), not modelled.
// The API secret is generated per run and never written out.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn, execFileSync } = require('child_process');
const { CLIENTS, POSTS, PINS } = require('./clients');

const CRM = process.env.CRM_DIR;
if (!CRM) throw new Error('CRM_DIR is required');
const MONGO = process.env.IDB_MONGO || 'mongodb://127.0.0.1:27803';
const CONNECT = process.env.CONNECT_DIR || path.resolve(__dirname, '../../../externals/nightscout-connect');
const CYCLES = 3;
const OUT = (() => { const i = process.argv.indexOf('--out'); return i > 0 ? process.argv[i + 1] : path.join(__dirname, 'results', 'run.json'); })();
const { MongoClient } = require(path.join(CRM, 'node_modules/mongodb'));
// Server logs and the transient connect spec (it holds the secret) stay out of the repo.
const LOGS = process.env.IDB_LOGS || path.join(require('os').tmpdir(), 'idb-lab');

const SECRET = crypto.randomBytes(18).toString('base64').replace(/[/+=]/g, '');
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const RUN = crypto.randomBytes(3).toString('hex');

const SERVERS = {
  off: { port: 3921, env: { } },
  reject: { port: 3922, env: { WRITE_VALIDATION: 'reject' } },
  strict: { port: 3923, env: { WRITE_IDENTIFIER: 'strict' } }
};

// ---------------------------------------------------------------- servers
const children = [];
async function boot (name) {
  const s = SERVERS[name];
  s.db = 'idb_' + name + '_' + RUN;
  s.url = 'http://127.0.0.1:' + s.port;
  const env = Object.assign({ PATH: process.env.PATH, HOME: process.env.HOME
    , MONGODB_URI: MONGO + '/' + s.db, API_SECRET: SECRET, PORT: String(s.port), HOSTNAME: '127.0.0.1'
    , INSECURE_USE_HTTP: 'true', AUTH_DEFAULT_ROLES: 'denied', DISPLAY_UNITS: 'mg/dl'
    , ENABLE: 'careportal devicestatus food', HEARTBEAT: '3600' }, s.env);
  fs.mkdirSync(LOGS, { recursive: true });
  s.log = path.join(LOGS, 'server-' + name + '.log');
  const out = fs.openSync(s.log, 'w');
  const child = spawn(process.execPath, ['lib/server/server.js'], { cwd: CRM, env, stdio: ['ignore', out, out] });
  children.push(child);
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch(s.url + '/api/v1/status.json', { headers: { 'api-secret': HASH } });
      if (r.status === 200) return;
    } catch { /* not up yet */ }
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error(name + ' did not come up; see ' + s.log);
}

async function post (server, coll, body, opts = {}) {
  const headers = Object.assign({ 'content-type': 'application/json', 'api-secret': HASH }, opts.headers || {});
  if (opts.token) delete headers['api-secret'];
  const q = [];
  if (opts.token) q.push('token=' + encodeURIComponent(opts.token));
  if (opts.query) q.push(opts.query);
  const url = SERVERS[server].url + '/api/v1/' + (opts.path || coll + '.json') + (q.length ? '?' + q.join('&') : '');
  const r = await fetch(url, { method: opts.method || 'POST', headers, body: JSON.stringify(body) });
  const text = await r.text();
  let parsed;
  try { parsed = JSON.parse(text); } catch { parsed = text; }
  return { status: r.status, headers: { warning: r.headers.get('warning'), 'content-type': r.headers.get('content-type') }
    , body: parsed, bytes: text.length };
}

let mongo;
async function stored (server, coll, tag) {
  return mongo.db(SERVERS[server].db).collection(coll).find({ idbTag: tag }).toArray();
}

// ---------------------------------------------------------------- records
// Times: every run gets its own 10-minute window, so no two runs share a
// record key. nightscout-connect runs are placed after all others (its
// bookmark starts at the newest stored record).
const BASE = Date.now() - 3 * 86400e3;
let windowNo = 0;
let connectNo = 0;
// Client runs 10 minutes apart; connect runs an hour apart, a day later, so a
// preBolus derived record (15 min after its item) never reaches the next run.
function nextWindow (connect) {
  if (connect) { connectNo++; return BASE + 86400e3 + connectNo * 3600e3; }
  windowNo++; return BASE + windowNo * 600e3;
}
const iso = ms => new Date(ms).toISOString();
const hex = () => crypto.randomBytes(12).toString('hex');

function carb (t0, tag, sec, extra) {
  return Object.assign({ eventType: 'Carb Correction', carbs: 10 + sec % 7, created_at: iso(t0 + sec * 1000)
    , enteredBy: 'idb-lab', idbTag: tag }, extra || {});
}
function badTT (t0, tag, sec) {
  return { eventType: 'Temporary Target', targetBottom: 150, targetTop: 100, units: 'mg/dl', duration: 60
    , created_at: iso(t0 + sec * 1000), enteredBy: 'idb-lab', idbTag: tag };
}
function sgv (t0, tag, sec, extra) {
  const ms = t0 + sec * 1000;
  return Object.assign({ type: 'sgv', sgv: 100 + sec % 50, date: ms, dateString: iso(ms), device: 'idb-lab', idbTag: tag }, extra || {});
}
function status (t0, tag, sec, extra) {
  return Object.assign({ device: 'idb-lab', created_at: iso(t0 + sec * 1000), uploader: { battery: 50 }, idbTag: tag }, extra || {});
}

// ---------------------------------------------------------------- scenarios
// make(t0, tagOf) returns { batch, seed?(), later? } ; tagOf(i) names item i.
const SCENARIOS = [
  { id: 'T-mixed', server: 'reject', coll: 'treatments'
    , what: 'WRITE_VALIDATION=reject; [carbs, Temporary Target with bottom > top, carbs]'
    , variants: [['today', null], ['slots', 'slots'], ['items', 'items'], ['207', 'slots; status=207']]
    , make: (t0, tag) => ({ batch: [carb(t0, tag(0), 0), badTT(t0, tag(1), 30), carb(t0, tag(2), 60)] }) },
  { id: 'T-allrefused', server: 'reject', coll: 'treatments'
    , what: 'WRITE_VALIDATION=reject; every item refused: [bad TT, bad TT]'
    , variants: [['today', null], ['slots', 'slots']]
    , make: (t0, tag) => ({ batch: [badTT(t0, tag(0), 0), badTT(t0, tag(1), 30)] }) },
  { id: 'T-prebolus', server: 'off', coll: 'treatments'
    , what: '[carbs with preBolus 15, carbs]; a late item 5 min after the first appears at cycle 2 (connect)'
    , variants: [['today', null], ['prebolus-keep', 'slots; prebolus=keep'], ['prebolus-omit', 'slots; prebolus=omit']]
    , make: (t0, tag) => ({ batch: [carb(t0, tag(0), 0, { preBolus: 15, carbs: 20 }), carb(t0, tag(1), 60)]
      , late: [carb(t0, tag(2), 300)] }) },
  { id: 'T-strict', server: 'strict', coll: 'treatments'
    , what: 'WRITE_IDENTIFIER=strict; [carbs with a valid identifier, carbs with identifier "undefined", carbs]'
    , variants: [['today', null], ['slots', 'slots']]
    , make: (t0, tag) => ({ batch: [carb(t0, tag(0), 0, { identifier: 'idb-' + tag(0) })
      , carb(t0, tag(1), 30, { identifier: 'undefined' }), carb(t0, tag(2), 60)] }) },
  { id: 'E-dupid', server: 'off', coll: 'entries'
    , what: 'a stored entry holds _id X; batch [sgv, sgv sent with _id X at another time, sgv]'
    , variants: [['today', null], ['dup-5xx', 'slots; duplicate-id=5xx'], ['dup-409', 'slots; duplicate-id=409']]
    , make: (t0, tag) => {
      const x = hex();
      // The seed sits 20 days earlier (+ the window's own offset), so it shares
      // no sysTime with any other run's entries.
      return { seed: async (server) => post(server, 'entries', [sgv(t0 - 20 * 86400e3, tag('seed'), 0, { _id: x })])
        , batch: [sgv(t0, tag(0), 0), sgv(t0, tag(1), 300, { _id: x }), sgv(t0, tag(2), 600)] };
    } },
  { id: 'E-sametime', server: 'off', coll: 'entries'
    , what: 'a stored entry at time t holds _id X; batch [sgv, sgv at t sent with another _id Y, sgv] (xDrip4iOS calibrations send _id)'
    , variants: [['today', null], ['dup-5xx', 'slots; duplicate-id=5xx'], ['dup-409', 'slots; duplicate-id=409']]
    , make: (t0, tag) => {
      const at = t0 - 20 * 86400e3;
      return { seed: async (server) => post(server, 'entries', [sgv(at, tag('seed'), 0, { _id: hex() })])
        , batch: [sgv(t0, tag(0), 0), Object.assign(sgv(at, tag(1), 0, { _id: hex() }), { sgv: 140 }), sgv(t0, tag(2), 600)] };
    } },
  { id: 'E-strict', server: 'strict', coll: 'entries'
    , what: 'WRITE_IDENTIFIER=strict; [sgv, sgv with identifier "null", sgv]'
    , variants: [['today', null], ['slots', 'slots']]
    , make: (t0, tag) => ({ batch: [sgv(t0, tag(0), 0), sgv(t0, tag(1), 300, { identifier: 'null' }), sgv(t0, tag(2), 600)] }) },
  { id: 'D-resend', server: 'off', coll: 'devicestatus'
    , what: 'a stored devicestatus re-sent with its _id beside a new one: the step answers the re-send refused "already stored"'
    , variants: [['today', null], ['ack-refused', 'slots; acknowledged=refused'], ['ack-word', 'slots; acknowledged=word']
      , ['ack-unchanged', 'slots; acknowledged=unchanged']]
    , make: (t0, tag) => {
      const first = status(t0, tag(0), 0, { _id: hex() });
      return { seed: async (server) => post(server, 'devicestatus', [Object.assign({}, first)])
        , batch: [Object.assign({}, first), status(t0, tag(1), 60)] };
    } },
  { id: 'D-badid', server: 'off', coll: 'devicestatus'
    , what: '[devicestatus, devicestatus with a non-hex _id, devicestatus]: today a whole-batch 400'
    , variants: [['today', null], ['slots', 'slots']]
    , make: (t0, tag) => ({ batch: [status(t0, tag(0), 0), status(t0, tag(1), 30, { _id: 'not-hex' }), status(t0, tag(2), 60)] }) }
];

// ---------------------------------------------------------------- run one
async function runClient (sc, variant, client) {
  const t0 = nextWindow(false);
  const tags = [];
  const tag = i => { const t = [sc.id, variant[0], client, RUN, i].join(':'); tags[i] = t; return t; };
  const made = sc.make(t0, tag);
  if (made.seed) await made.seed(sc.server);
  const sent = made.batch;
  let pending = sent.map(() => true);
  const marked = sent.map(() => false);
  const idKept = sent.map(() => 'n/a');
  let readsId = false;
  const cycles = [];
  let last;
  for (let c = 0; c < CYCLES && pending.some(Boolean); c++) {
    const idx = sent.map((d, i) => i).filter(i => pending[i]);
    const body = idx.map(i => JSON.parse(JSON.stringify(sent[i])));
    const reply = await post(sc.server, sc.coll, body, { headers: variant[1] ? { 'Nightscout-Write-Results': variant[1] } : {} });
    const h = CLIENTS[client](sc.coll, body, reply);
    last = { reply, h, idx };
    readsId = readsId || h.readsId;
    const next = sent.map(() => false);
    idx.forEach((i, k) => {
      next[i] = h.resend[k];
      if (h.marked[k]) marked[i] = true;
      if (h.readsId) idKept[i] = h.ids[k];
    });
    const code = reply.body && reply.body.description && reply.body.description.code;
    cycles.push({ status: reply.status, length: Array.isArray(reply.body) ? reply.body.length : null, ok: h.ok
      , errCode: code === undefined ? null : code, warning: reply.headers.warning
      , resent: idx.length, why: h.why });
    pending = next;
  }
  const items = [];
  for (let i = 0; i < sent.length; i++) {
    const docs = await stored(sc.server, sc.coll, tags[i]);
    const id = idKept[i];
    items.push({ i, stored: docs.length, marked: marked[i], pending: pending[i], idKept: id
      , idRight: typeof id === 'string' && id !== 'NA' ? docs.some(d => String(d._id) === id) : null });
  }
  return { cycles, items, retry: last.h.retry, readsId };
}

// nightscout-connect, for real: up to CYCLES record_batch() calls.
async function runConnect (sc, variant) {
  const t0 = nextWindow(true);
  const tags = [];
  const tag = i => { const t = [sc.id, variant[0], 'connect', RUN, i].join(':'); tags[i] = t; return t; };
  const made = sc.make(t0, tag);
  if (made.seed) await made.seed(sc.server);
  const cyc = [];
  for (let c = 0; c < CYCLES; c++) cyc.push(c === 0 ? made.batch : made.batch.concat(made.late || []));
  const spec = { connectDir: CONNECT, url: SERVERS[sc.server].url, apiSecret: SECRET, optIn: variant[1], collection: sc.coll, cycles: cyc };
  const specFile = path.join(LOGS, 'connect-spec.json');
  fs.writeFileSync(specFile, JSON.stringify(spec), { mode: 0o600 });
  let result;
  try {
    const out = execFileSync(process.execPath, [path.join(__dirname, 'connect-run.js'), specFile]
      , { env: Object.assign({}, process.env, { NODE_PATH: path.join(CRM, 'node_modules') }), encoding: 'utf8' });
    result = JSON.parse(out.trim().split('\n').pop());
  } finally {
    fs.unlinkSync(specFile);
  }
  const all = made.batch.concat(made.late || []);
  const items = [];
  for (let i = 0; i < all.length; i++) {
    const docs = await stored(sc.server, sc.coll, tags[i]);
    const sentTimes = (result.cycles || []).filter(c => c.sent.indexOf(tags[i]) >= 0).length;
    items.push({ i, stored: docs.length, sentTimes, late: i >= made.batch.length });
  }
  return { cycles: result.cycles, crash: result.crash, items };
}

// ---------------------------------------------------------------- (ii) opt-in forms
async function optInForms ( ) {
  const forms = [];
  const t0 = nextWindow(false);
  const mk = (n) => [carb(t0, 'ii:' + n + ':0:' + RUN, n * 70), badTT(t0, 'ii:' + n + ':1:' + RUN, n * 70 + 10)];
  const cases = [
    ['none', {}],
    ['header', { headers: { 'Nightscout-Write-Results': 'items' } }],
    ['query', { query: 'results=items' }],
    ['accept', { headers: { accept: 'application/vnd.nightscout.write-results+json' } }],
    ['accept-no-suffix-path', { headers: { accept: 'application/vnd.nightscout.write-results+json' }, path: 'treatments/' }],
    ['accept-with-json-too', { headers: { accept: 'application/json, application/vnd.nightscout.write-results+json;q=0.5' } }],
    ['header-no-suffix-path', { headers: { 'Nightscout-Write-Results': 'items' }, path: 'treatments/' }],
    ['header-malformed', { headers: { 'Nightscout-Write-Results': 'itemz' } }]
  ];
  for (let n = 0; n < cases.length; n++) {
    const [name, opts] = cases[n];
    const before = fs.readFileSync(SERVERS.reject.log, 'utf8').length;
    const r = await post('reject', 'treatments', mk(n), opts);
    const log = fs.readFileSync(SERVERS.reject.log, 'utf8').slice(before);
    const docs = await stored('reject', 'treatments', 'ii:' + n + ':0:' + RUN);
    forms.push({ name, status: r.status, contentType: r.headers['content-type'], warning: r.headers.warning
      , shape: Array.isArray(r.body) ? 'array[' + r.body.length + ']' : (r.body && r.body.items ? 'object{items[' + r.body.items.length + '],documents}' : typeof r.body)
      , storedFirst: docs.length, urlInServerLog: /results=items/.test(log) });
  }
  return forms;
}

// ---------------------------------------------------------------- profile (iii)
async function profilePermission ( ) {
  const s = SERVERS.off.url;
  const h = { 'content-type': 'application/json', 'api-secret': HASH };
  await fetch(s + '/api/v2/authorization/roles', { method: 'POST', headers: h
    , body: JSON.stringify({ name: 'idbprofilecreate', permissions: ['api:profile:create', 'api:profile:read'] }) });
  await fetch(s + '/api/v2/authorization/subjects', { method: 'POST', headers: h
    , body: JSON.stringify({ name: 'idb-uploader', roles: ['idbprofilecreate'] }) });
  const subjects = await (await fetch(s + '/api/v2/authorization/subjects', { headers: h })).json();
  const token = subjects.find(x => x.name === 'idb-uploader').accessToken;
  const out = [];
  for (const [name, optIn] of [['today', null], ['whole', 'slots; profile=whole'], ['per-item', 'slots; profile=per-item']]) {
    const t0 = nextWindow(false);
    const tagP = 'P:' + name + ':' + RUN; const tagQ = 'Q:' + name + ':' + RUN;
    const pid = hex();
    const p = { _id: pid, defaultProfile: 'Default', startDate: iso(t0), created_at: iso(t0), units: 'mg/dl', idbTag: tagP
      , store: { Default: { dia: 3, carbratio: [{ time: '00:00', value: 10 }], sens: [{ time: '00:00', value: 50 }]
        , basal: [{ time: '00:00', value: 1 }], target_low: [{ time: '00:00', value: 100 }], target_high: [{ time: '00:00', value: 120 }], units: 'mg/dl', timezone: 'UTC' } } };
    await post('off', 'profile', [p]);
    const changed = JSON.parse(JSON.stringify(p));
    changed.store.Default.dia = 4;
    const q = JSON.parse(JSON.stringify(p));
    delete q._id; q.idbTag = tagQ; q.startDate = iso(t0 + 60e3); q.created_at = iso(t0 + 60e3);
    const r = await post('off', 'profile', [changed, q], { token, headers: optIn ? { 'Nightscout-Write-Results': optIn } : {} });
    const storedP = await stored('off', 'profile', tagP);
    const storedQ = await stored('off', 'profile', tagQ);
    out.push({ name, status: r.status, body: Array.isArray(r.body) ? r.body.map(x => x.refused ? { refused: x.refused.status } : { _id: Boolean(x._id) }) : r.body
      , changedApplied: storedP.length === 1 && storedP[0].store.Default.dia === 4, newStored: storedQ.length });
  }
  return out;
}

// ---------------------------------------------------------------- main
async function main ( ) {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  mongo = await MongoClient.connect(MONGO, { appName: 'idb-lab', maxPoolSize: 4 });
  const crmHead = execFileSync('git', ['-C', CRM, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const crmDirty = execFileSync('git', ['-C', CRM, 'status', '--short', '--', 'lib'], { encoding: 'utf8' }).trim();
  for (const name of Object.keys(SERVERS)) await boot(name);
  const results = { meta: { crm: crmHead, crmDirty, mongod: (await mongo.db('admin').command({ buildInfo: 1 })).version
    , node: process.version, run: RUN, date: new Date().toISOString(), cycles: CYCLES, pins: PINS }, runs: [], connect: [] };
  try {
    for (const sc of SCENARIOS) {
      for (const variant of sc.variants) {
        for (const client of Object.keys(CLIENTS)) {
          const probe = CLIENTS[client](sc.coll, [], { status: 200, headers: {}, body: [] });
          if (probe.na || POSTS[client].indexOf(sc.coll) < 0) {
            results.runs.push({ scenario: sc.id, variant: variant[0], client, na: probe.na ? probe.why : 'does not post ' + sc.coll + ' as a v1 array' });
            continue;
          }
          const r = await runClient(sc, variant, client);
          results.runs.push(Object.assign({ scenario: sc.id, variant: variant[0], optIn: variant[1], client }, r));
        }
      }
    }
    for (const sc of SCENARIOS) {
      for (const variant of sc.variants) {
        if (variant[0] === 'items') continue;
        const r = await runConnect(sc, variant);
        results.connect.push(Object.assign({ scenario: sc.id, variant: variant[0], optIn: variant[1] }, r));
      }
    }
    results.optInForms = await optInForms();
    results.profile = await profilePermission();
  } finally {
    children.forEach(c => c.kill('SIGTERM'));
    for (const s of Object.values(SERVERS)) if (s.db) await mongo.db(s.db).dropDatabase().catch(() => {});
    await mongo.close();
  }
  results.scenarios = SCENARIOS.map(s => ({ id: s.id, server: s.server, coll: s.coll, what: s.what }));
  fs.writeFileSync(OUT, JSON.stringify(results, null, 1) + '\n');
  console.log('wrote ' + OUT + ': ' + results.runs.length + ' client runs, ' + results.connect.length + ' connect runs');
}

main().catch(err => { console.error(err); children.forEach(c => c.kill('SIGTERM')); process.exit(1); });
