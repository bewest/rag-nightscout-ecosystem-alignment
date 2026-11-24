// Capacity workload (k6), shared by the Compose and Kubernetes harnesses and compose-baseline/bench.sh.
// Synthetic data only. Every option is a plain environment parameter; nothing patches this file.
//
// One "cycle" is the 5-minute CGM cadence compressed by ACCEL (default 60: one cycle per 5 s).
// Per tenant per cycle, pinned to the shapes of shipping clients:
//   uploader (xDrip+/cgmsim)  POST /api/v1/entries          1 sgv          token= query
//   loop/oref0 uploader       POST /api/v1/devicestatus     1 loop status  token= query
//   AAPS-style uploader       POST /api/v3/treatments       1 temp basal   Bearer JWT
//   follower apps (polling)   GET  /api/v1/entries/sgv.json?count=1   x5 (one per real minute)
//                             GET  /api/v1/devicestatus.json?count=1  x1
//                             GET  /api/v1/treatments.json?count=10   x1
//                             GET  /api/v1/status.json                x1
// The hot tenant (index 0) carries HOT_FACTOR times every shape. SHAPES selects the shapes
// (default: no v3 treatments). v1 POST /api/v1/treatments is not used: the reference tenants
// do not enable careportal, so it answers 401 exactly as a single-tenant site without careportal does.
//
// The tenants file carries each tenant's JWT (`jwt`), exchanged once before k6 starts by
// tools/mt-bench/m7-joined/jwt_tenants.py. k6 loads the file once into a SharedArray and setup()
// returns nothing, so driver memory does not grow with roster x VUs.
//
// Environment: BASE_URL, TENANTS_FILE, RUN_ID, RUN_START, DURATION, ACCEL, HOT_FACTOR, SHAPES,
// OFFERED_RPS (optional total arrival rate), M7_WORKLOAD_MIX=realistic-v1 and M7_WORKLOAD_SCALE
// (optional sensor-cadence mix), DRIVER_HEADROOM (VU headroom factor H, default 1.5 for local
// Compose; harnesses pass 2 for Kubernetes and 3 for a remote generator), and M7_DRIVER_PLAN
// (optional scheduling plan read by m7-joined/k6-vu-driver.js).
//
// Every write carries RUN_ID (entries/devicestatus `device`, treatments `enteredBy`) and a
// timestamp unique within the run; each accepted write logs one `m7-input-accepted` event.
import http from 'k6/http';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';
import { SharedArray } from 'k6/data';

const BASE = __ENV.BASE_URL;
const RUN_ID = __ENV.RUN_ID;
const DURATION = Number(__ENV.DURATION || 120);
const ACCEL = Number(__ENV.ACCEL || 60);
const HOT = Number(__ENV.HOT_FACTOR || 10);
const TENANTS = new SharedArray('tenants', () => JSON.parse(open(__ENV.TENANTS_FILE)));
const CYCLE = 300 / ACCEL; // seconds per compressed 5-minute cycle
// One fixed origin for the whole run (every VU evaluates init code separately, so Date.now() here would
// differ per VU and let two VUs' timestamps collide, which the server's dedup then merges).
const START = Number(__ENV.RUN_START);

const writesOk = new Counter('writes_ok');
const writesUncertain = new Counter('writes_uncertain');
const writesRefused = new Counter('writes_refused');
// Documents, not requests: a looping-v2 v1 treatments POST carries an array (the stored-row oracle counts rows).
const writesOkDocuments = new Counter('writes_ok_documents');
const writesUncertainDocuments = new Counter('writes_uncertain_documents');
const responsesRefused = new Counter('responses_refused');
const scenarioAttempts = new Counter('scenario_request_attempts'), scenarioResponses = new Counter('scenario_http_responses'), scenarioTransport = new Counter('scenario_transport_failures');
// looping-v2 request shapes (bounded tag values; no tenant tag)
const LOOPING_REQUEST_SHAPES = ['ds_loop', 'ds_loop_extra', 'ds_trio_suggested', 'ds_trio_enacted', 'ds_aaps', 'ds_cgm_battery',
  'tx_loop_v1', 'tx_trio_v1', 'tx_aaps_v3', 'profile_loop_v1'];
const LOOPING_IDENTITIES = ['syncIdentifier', 'id', 'uuid', 'NSCLIENT_ID', 'identifier', '_id'];
const loopingRequests = new Counter('m7_looping_requests'), loopingDocuments = new Counter('m7_looping_documents'),
  loopingIdentityless = new Counter('m7_looping_identityless');
const httpAttempts = new Counter('m7_http_attempts'), httpCompleted = new Counter('m7_http_completed'), httpWriteOutcome = new Counter('m7_http_write_outcome');

if (!Number.isSafeInteger(HOT) || HOT < 1 || !TENANTS.length ||
    TENANTS.length - 1 + HOT > 0xffffffff) throw Error('M7_WORKLOAD_POPULATION_ARRAY_LIMIT');
if (!Number.isSafeInteger(DURATION) || DURATION < 1 || DURATION > 9223372036) {
  throw Error('M7_WORKLOAD_DURATION_TIME_UNIT');
}
// Weighted tenant wheel: slots 0..HOT-1 are tenant 0, then one slot per other tenant.
const weight = TENANTS.length - 1 + HOT;

const ALL_SHAPES = {
  w_sgv: 1, w_devicestatus: 1, w_treatments_v3: 1,
  r_sgv: 5, r_devicestatus: 1, r_treatments: 1, r_status: 1,
};
const SELECTED = (__ENV.SHAPES || 'w_sgv,w_devicestatus,r_sgv,r_devicestatus,r_treatments,r_status').split(',');
const shapes = Object.fromEntries(Object.entries(ALL_SHAPES).filter(([name]) => SELECTED.includes(name)));
const offered = __ENV.OFFERED_RPS === undefined ? null : Number(__ENV.OFFERED_RPS);
if (offered !== null && (!Number.isFinite(offered) || offered <= 0)) throw Error('M7_OFFERED_RPS_RANGE');
const ARRIVAL_CYCLE_MS = offered === null ? Math.round(CYCLE * 1000) : Math.round(Object.values(shapes).reduce((a, b) => a + b, 0) * weight * 1000 / offered);

const mix = __ENV.M7_WORKLOAD_MIX;
const workloadScale = __ENV.M7_WORKLOAD_SCALE === undefined ? 1 : Number(__ENV.M7_WORKLOAD_SCALE);
if (!Number.isFinite(workloadScale) || workloadScale <= 0 ||
    (__ENV.M7_WORKLOAD_SCALE !== undefined && mix !== 'realistic-v1')) throw Error('M7_WORKLOAD_SCALE_CONFIGURATION');
const driverPlan = __ENV.M7_DRIVER_PLAN ? JSON.parse(__ENV.M7_DRIVER_PLAN) : {};
const writeScale = driverPlan.writeRateScale === undefined ? 1 : driverPlan.writeRateScale;
if (!Number.isFinite(writeScale) || writeScale <= 0 ||
    (driverPlan.writeRateScale !== undefined && mix !== 'realistic-v1')) throw Error('M7_WORKLOAD_SCALE_CONFIGURATION');
// Sensor cadence of each shape for realistic-v1 (mirrors m7-joined/workload.py REALISTIC_CADENCE_MS).
const realisticCadenceMs = {"w_sgv": 300000, "w_devicestatus": 300000, "w_treatments_v3": 1800000, "r_sgv": 300000, "r_devicestatus": 900000, "r_treatments": 900000, "r_status": 900000};
if (mix !== undefined &&
    (mix !== 'realistic-v1' || offered !== null || ACCEL !== 1 || HOT !== 1 ||
     Object.keys(realisticCadenceMs).some(name => !shapes[name]))) {
  throw Error('M7_REALISTIC_MIX_CONFIGURATION');
}
// Driver shape looping-v1 (m7-joined/looping_driver.py, lane mt-plannable-scale-20261121 E3): writes
// shaped like the E1 looping fixture. Each tenant row carries loopKind from the seed's own role hash
// (null: CGM-only, SGV only); devicestatus bodies are the generator's documents; treatments post once
// per looping tenant every M7_LOOPING_TREATMENT_CYCLE_MS.
// Driver shape looping-v2 (the AID client model, m7-joined/looping_driver.py): per-controller devicestatus
// (Loop 1.35, Trio 2, AAPS 1 per cycle) and a battery status for CGM-only tenants, walked as a 20-cycle wheel
// of one request per iteration; treatments once per looping tenant per 400 s on the controllers' routes
// (Loop/Trio v1 arrays with syncIdentifier/id, AAPS v3 single documents); a Loop profile in 1 of 648 rounds.
const shape = __ENV.M7_DRIVER_SHAPE;
const looping = shape === 'looping-v1' || shape === 'looping-v2';
const v2 = shape === 'looping-v2';
if (shape !== undefined && (!looping || mix !== 'realistic-v1')) throw Error('M7_DRIVER_SHAPE_CONFIGURATION');
const LOOP = looping ? JSON.parse(__ENV.M7_LOOPING_TEMPLATES) : null;
const RULES = v2 ? JSON.parse(__ENV.M7_LOOPING_V2_RULES) : null;
const V2_KINDS = ['loop', 'aaps', 'trio'];
const LOOPERS = [];
if (looping) for (let i = 0; i < TENANTS.length; i++) {
  const kind = TENANTS[i].loopKind;
  if (kind === null) continue;
  if (typeof kind !== 'string' || !(v2 ? V2_KINDS.includes(kind) : Object.hasOwn(LOOP.documents, kind))) throw Error('M7_DRIVER_SHAPE_CONFIGURATION');
  LOOPERS.push(i);
}
const LOOP_TX_MS = looping ? Number(__ENV.M7_LOOPING_TREATMENT_CYCLE_MS) : null;
if (looping && (!LOOPERS.length || !Number.isSafeInteger(LOOP_TX_MS) || LOOP_TX_MS < 60000)) throw Error('M7_DRIVER_SHAPE_CONFIGURATION');
if (v2 && !(Number.isSafeInteger(RULES.dsPeriod) && RULES.dsPeriod >= 1 && RULES.loopExtra[1] === RULES.dsPeriod)) throw Error('M7_DRIVER_SHAPE_CONFIGURATION');
// looping-v2 devicestatus wheel: DS_PERIOD cycles, cycle-major, each tenant's posts adjacent in tenant order.
// An entry is tenant * 4 + post (Loop: 0 and, in 7 of 20 cycles, 1; Trio: 0 suggested, 1 enacted).
const loopExtra = (i, c) => (c * RULES.loopExtra[0] + i) % RULES.loopExtra[1] < RULES.loopExtra[0];
const DS_WHEEL = v2 ? new SharedArray('looping-v2-devicestatus-wheel', () => {
  const out = [];
  for (let c = 0; c < RULES.dsPeriod; c++) for (let i = 0; i < TENANTS.length; i++) {
    const kind = TENANTS[i].loopKind;
    const posts = kind === 'trio' ? 2 : kind === 'loop' && loopExtra(i, c) ? 2 : 1;
    for (let j = 0; j < posts; j++) out.push(i * 4 + j);
  }
  return out;
}) : null;
const LOOP_SHAPES = new Set(['w_devicestatus', 'w_treatments_v3']);
// Tenants a write shape addresses: every tenant, or the looping ones under looping-v1; under looping-v2
// devicestatus iterates the wheel's slots (every tenant) and treatments the looping tenants.
const population = name => (v2 && name === 'w_devicestatus' ? DS_WHEEL.length :
  looping && LOOP_SHAPES.has(name) ? LOOPERS.length : weight);
function cycleMs(name) {
  if (mix === undefined) return ARRIVAL_CYCLE_MS;
  if (looping && name === 'w_treatments_v3') return Math.round(LOOP_TX_MS / workloadScale / writeScale);
  if (v2 && name === 'w_devicestatus') return RULES.dsPeriod * Math.round(realisticCadenceMs[name] / workloadScale / writeScale);
  const interval = realisticCadenceMs[name] * shapes[name] / workloadScale;
  return Math.round(name.startsWith('w_') ? interval / writeScale : interval);
}
// k6 durations are Go int64 nanoseconds.
if (Object.keys(shapes).some(name => !Number.isSafeInteger(cycleMs(name)) || cycleMs(name) < 1 || cycleMs(name) > 9223372036854)) {
  throw Error('M7_OFFERED_RPS_TIME_UNIT');
}
// Decision driver-sized-from-offer: the only k6 VU sizing, used by every k6 path (Compose,
// the Kubernetes native driver and k6-vu-driver.js, which imports these scenarios).
// perSecond is one operation's offered requests/s; H is the platform headroom factor. A drop
// occurs only when server latency exceeds about 5 s x H at that rate. maxVUs are created
// only when latency requires them.
export function driverVUs (perSecond, headroom) {
  return { preAllocatedVUs: Math.max(2, Math.ceil(perSecond * 0.25 * headroom)),
           maxVUs: Math.max(4, Math.ceil(perSecond * 5 * headroom)) };
}
export const DRIVER_HEADROOM = __ENV.DRIVER_HEADROOM === undefined ? 1.5 : Number(__ENV.DRIVER_HEADROOM);
if (!Number.isFinite(DRIVER_HEADROOM) || DRIVER_HEADROOM <= 0 || DRIVER_HEADROOM > 100) throw Error('M7_DRIVER_HEADROOM_RANGE');
const scenarios = {};
for (const [name, perCycle] of Object.entries(shapes)) {
  const rate = perCycle * population(name); // iterations per cycle
  scenarios[name] = {
    executor: 'constant-arrival-rate', exec: name, rate, timeUnit: cycleMs(name) + 'ms',
    duration: DURATION + 's', ...driverVUs(rate * 1000 / cycleMs(name), DRIVER_HEADROOM),
    tags: { shape: name },
  };
}
// Zero-valued thresholds make every counter appear in the summary export, including zeros.
// No per-tenant tag or threshold: per-tenant figures come from the stored rows.
const thresholds = {writes_ok:['count>=0'],writes_uncertain:['count>=0'],writes_ok_documents:['count>=0'],writes_uncertain_documents:['count>=0'],writes_refused:['count>=0'],responses_refused:['count>=0'],
  scenario_request_attempts:['count>=0'],scenario_http_responses:['count>=0'],scenario_transport_failures:['count>=0'],dropped_iterations:['count>=0']};
// k6 reads options in its initial context; other VUs skip the threshold metadata.
// Undefined __VU supports the standalone payload fixtures.
if (typeof __VU === 'undefined' || __VU === 0) {
  httpAccountingThresholds(thresholds, Object.keys(shapes));
  for (const k of ['entries', 'devicestatus', 'treatments', ...(v2 ? ['profile'] : [])]) {
    thresholds[`writes_ok{kind:${k}}`] = ['count>=0']; thresholds[`writes_ok_documents{kind:${k}}`] = ['count>=0'];
  }
  if (v2) for (const name of LOOPING_REQUEST_SHAPES) for (const metric of ['m7_looping_requests', 'm7_looping_documents', 'm7_looping_identityless'])
    thresholds[`${metric}{request_shape:${name}}`] = ['count>=0'];
  for (const name of Object.keys(shapes)) thresholds[`http_req_duration{shape:${name}}`] = ['max>=0'];
  for (const name of Object.keys(shapes)) thresholds[`http_req_failed{shape:${name}}`] = ['rate>=0'];
}

export const options = {
  scenarios, thresholds, discardResponseBodies: true, noConnectionReuse: false,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
};

function pick () {
  if (exec.scenario.iterationInTest === 0) {
    console.log(JSON.stringify({ event: 'scenario-first-iteration', shape: exec.scenario.name, atMs: Date.now() }));
  }
  if (v2 && exec.scenario.name === 'w_devicestatus') {
    const e = DS_WHEEL[exec.scenario.iterationInTest % DS_WHEEL.length];
    const i = Math.floor(e / 4);
    return { i, t: TENANTS[i], post: e % 4 };
  }
  if (looping && LOOP_SHAPES.has(exec.scenario.name)) {
    const i = LOOPERS[exec.scenario.iterationInTest % LOOPERS.length];
    return { i, t: TENANTS[i] };
  }
  const r = exec.scenario.iterationInTest % weight;
  const i = r < HOT ? 0 : r - HOT + 1;
  return { i, t: TENANTS[i] };
}
const q = t => (t ? '&' : '?');
function get (t, path, name, responseType) {
  const httpShape = ({'GET v1 sgv count=1':'r_sgv','GET v1 devicestatus count=1':'r_devicestatus','GET v1 treatments count=10':'r_treatments','GET v1 status':'r_status'})[name];
  httpAttempts.add(1, {http_shape:httpShape});
  scenarioAttempts.add(1);
  const response = http.get(BASE + path + q(path.includes('?')) + 'token=' + t.token,
    { headers: { Host: t.host }, tags: { name }, timeout: '30s', ...(responseType === undefined ? {} : {responseType}) });
  recordHttp(httpShape, response, [200], false);
  (response.status > 0 ? scenarioResponses : scenarioTransport).add(1);
  if (response.status >= 400 && response.status < 500) responsesRefused.add(1);
  return response;
}
function write (t, kind, url, body, headers, okStatuses, name, requestShape) {
  const httpShape = ({entries:'w_sgv',devicestatus:'w_devicestatus',treatments:'w_treatments_v3',profile:'w_treatments_v3'})[kind];
  if (requestShape !== undefined) {
    const docs = Array.isArray(body) ? body : [body];
    loopingRequests.add(1, {request_shape: requestShape});
    loopingDocuments.add(docs.length, {request_shape: requestShape});
    // v1 treatments only: an API v3 create carries no identifier by design (the server computes it).
    const idless = requestShape === 'tx_loop_v1' || requestShape === 'tx_trio_v1' ?
      docs.filter(d => !LOOPING_IDENTITIES.some(k => d[k] !== undefined && d[k] !== null && d[k] !== '')).length : 0;
    loopingIdentityless.add(idless, {request_shape: requestShape});
  }
  httpAttempts.add(1, {http_shape:httpShape});
  scenarioAttempts.add(1);
  // The row becomes visible between this request starting and HTTP acceptance; the
  // collector uses this duration without comparing clocks across machines. One
  // millisecond covers the emitter clock's timestamp quantization.
  const inputStartedAt = Date.now();
  const res = http.post(url, JSON.stringify(body), { headers: Object.assign({ Host: t.host, 'Content-Type': 'application/json' }, headers),
    tags: { name }, timeout: '30s', responseCallback: http.expectedStatuses(...okStatuses) });
  recordHttp(httpShape, res, okStatuses, true);
  (res.status > 0 ? scenarioResponses : scenarioTransport).add(1);
  const tags = { kind };
  if (okStatuses.includes(res.status)) {
    const doc = Array.isArray(body) ? body[0] : body;
    // A profile is not an M3-observed domain (latency_oracle.DOMAINS); a v1 treatment without `date` is
    // keyed by its created_at, as the frame ledger reads it (mills).
    if (kind !== 'profile') console.log(JSON.stringify({event:'m7-input-accepted', run:RUN_ID, tenant:t.id, domain:kind,
      key:String(kind === 'devicestatus' ? doc.created_at : doc.date !== undefined ? doc.date : Date.parse(doc.created_at)),
      requestToAcceptanceMs:Date.now()-inputStartedAt+1,
      // M3 (offline latency oracle): the driver's own clock at acceptance.
      acceptedAtMs:Date.now()}));
    writesOk.add(1, tags);
    writesOkDocuments.add(Array.isArray(body) ? body.length : 1, tags);
  }
  else if (!(res.status >= 400 && res.status < 500)) { // may have committed
    writesUncertain.add(1, tags); writesUncertainDocuments.add(Array.isArray(body) ? body.length : 1, tags);
  }
  else writesRefused.add(1, tags);
  return res;
}

// The JWT exchange happened before k6 started; the markers keep the existing phase boundaries.
export function setup () {
  const atMs = Date.now();
  console.log(JSON.stringify({ event: 'jwt-setup-start', atMs, tenants: TENANTS.length, exchanges: 0 }));
  console.log(JSON.stringify({ event: 'jwt-setup-end', atMs: Date.now(), startedAtMs: atMs, tenants: TENANTS.length, exchanges: 0 }));
}

export function teardown () {
  console.log(JSON.stringify({ event: 'scenario-phase-end', atMs: Date.now() }));
}

// Current nominal arrival time, unique per scenario iteration.
const stamp = () => START + Math.floor(exec.scenario.iterationInTest * cycleMs(exec.scenario.name) / population(exec.scenario.name));
const iso = ms => new Date(ms).toISOString();

export function w_sgv () {
  const { t } = pick(); const ms = stamp();
  write(t, 'entries', BASE + '/api/v1/entries?token=' + t.token,
    [{ type: 'sgv', sgv: 80 + (ms % 120), date: ms, dateString: iso(ms), direction: 'Flat', delta: 1.2, filtered: 180000, unfiltered: 180000, rssi: 100, noise: 1, device: RUN_ID }],
    {}, [200], 'POST v1 entries');
}
export function w_devicestatus () {
  const { t, post } = pick(); const ms = stamp(); const at = iso(ms);
  if (v2) {
    const kind = t.loopKind === null ? 'cgm' : t.loopKind;
    const set = kind === 'loop' ? (post ? 'loop_extra' : 'loop') : kind === 'trio' ? (post ? 'trio_enacted' : 'trio_suggested') : kind;
    const docs = LOOP.devicestatus[set];
    const doc = JSON.parse(docs[Math.floor(exec.scenario.iterationInTest / TENANTS.length) % docs.length].split(LOOP.placeholder).join(at));
    doc.device = RUN_ID;
    return write(t, 'devicestatus', BASE + '/api/v1/devicestatus?token=' + t.token, [doc], {}, [200], 'POST v1 devicestatus',
      kind === 'cgm' ? 'ds_cgm_battery' : 'ds_' + set);
  }
  if (looping) {
    const docs = LOOP.documents[t.loopKind];
    const doc = JSON.parse(docs[Math.floor(exec.scenario.iterationInTest / LOOPERS.length) % docs.length].split(LOOP.placeholder).join(at));
    doc.device = RUN_ID;
    return write(t, 'devicestatus', BASE + '/api/v1/devicestatus?token=' + t.token, [doc], {}, [200], 'POST v1 devicestatus');
  }
  write(t, 'devicestatus', BASE + '/api/v1/devicestatus?token=' + t.token,
    [{ device: RUN_ID, created_at: at, uploader: { battery: 88 },
      loop: { name: 'Loop', version: '3.4', timestamp: at, iob: { timestamp: at, iob: 1.234 }, cob: { timestamp: at, cob: 12 },
        predicted: { startDate: at, values: Array.from({ length: 72 }, (_, k) => 120 + (k % 7)) }, recommendedBolus: 0,
        enacted: { rate: 0.75, duration: 30, timestamp: at, received: true } } }],
    {}, [200], 'POST v1 devicestatus');
}
// looping-v2 treatment slot k of tenant i (round = k / looping tenants): the controller's request.
function loopingTreatment (t, i, round, ms) {
  const at = iso(ms), R = RULES;
  const id = n => RUN_ID + '.' + i + '.' + round + '.' + n;
  const make = (name, n) => {
    const doc = JSON.parse(LOOP.treatments[name].split(LOOP.placeholder).join(at).split(LOOP.idPlaceholder).join(id(n)));
    doc.enteredBy = RUN_ID;
    return doc;
  };
  if (t.loopKind === 'loop') {
    if ((round + i * 37) % R.profileEvery === 0) {
      const doc = JSON.parse(LOOP.profile.loop.split(LOOP.placeholder).join(at));
      doc.mills = ms; doc.enteredBy = RUN_ID;
      return write(t, 'profile', BASE + '/api/v1/profile?token=' + t.token, doc, {}, [200], 'POST v1 profile', 'profile_loop_v1');
    }
    const docs = [make((round * 13 + i) % R.loopIdless === 0 ? 'loop_site_change' : 'loop_temp_basal', 0)];
    if ((round * 7 + i) % R.loopTwo === 0) docs.push(make('loop_bolus', 1));
    return write(t, 'treatments', BASE + '/api/v1/treatments?token=' + t.token, docs, {}, [200], 'POST v1 treatments', 'tx_loop_v1');
  }
  if (t.loopKind === 'trio') {
    const idless = ['trio_exercise', 'trio_temp_target', 'trio_note'][(round + i) % 3];
    const docs = [make((round * 13 + i) % R.trioIdless === 0 ? idless : 'trio_temp_basal', 0)];
    if ((round * 7 + i) % R.trioTwo === 0) docs.push(make('trio_smb', 1));
    return write(t, 'treatments', BASE + '/api/v1/treatments?token=' + t.token, docs, {}, [200], 'POST v1 treatments', 'tx_trio_v1');
  }
  const doc = make((round + i) % R.aapsSmb[1] < R.aapsSmb[0] ? 'aaps_smb' : 'aaps_temp_basal', 0);
  doc.date = ms; doc.pumpId = ms;
  return write(t, 'treatments', BASE + '/api/v3/treatments', doc, { Authorization: 'Bearer ' + t.jwt }, [200, 201],
    'POST v3 treatments', 'tx_aaps_v3');
}
export function w_treatments_v3 () {
  const { i, t } = pick(); const ms = stamp();
  if (v2) return loopingTreatment(t, i, Math.floor(exec.scenario.iterationInTest / LOOPERS.length), ms);
  write(t, 'treatments', BASE + '/api/v3/treatments',
    { eventType: 'Temp Basal', duration: 30, absolute: 0.8, rate: 0.8, date: ms, created_at: iso(ms), utcOffset: 0, app: 'bench', enteredBy: RUN_ID },
    { Authorization: 'Bearer ' + t.jwt }, [200, 201], 'POST v3 treatments');
}
export function r_sgv () { const { t } = pick(); get(t, '/api/v1/entries/sgv.json?count=1', 'GET v1 sgv count=1'); }
export function r_devicestatus () { const { t } = pick(); get(t, '/api/v1/devicestatus.json?count=1', 'GET v1 devicestatus count=1'); }
export function r_treatments () { const { t } = pick(); get(t, '/api/v1/treatments.json?count=10', 'GET v1 treatments count=10'); }
export function r_status () { const { t } = pick(); get(t, '/api/v1/status.json', 'GET v1 status'); }

// Bounded per-shape HTTP status and outcome counters. Never retain body, URL or error text.
function classifyHttp(response, expected, mutation) {
  const observed = response && response.status;
  const status = Number.isInteger(observed) && (observed === 0 || observed >= 100 && observed <= 599) ? observed : 0;
  // k6 error code 1050 is its request timeout observation. Other transport causes
  // remain unknown; status 5xx says nothing about whether a mutation committed.
  const category = status === 0 ? (response && response.error_code === 1050 ? 'timeout' : 'transport') :
    expected.includes(status) ? 'http_expected' : status >= 400 && status < 500 ? 'http_refused' : 'http_unexpected';
  const writeOutcome = !mutation ? null : category === 'http_expected' ? 'accepted' : category === 'http_refused' ? 'refused' : 'uncertain';
  return {status, category, writeOutcome};
}
function recordHttp(shape, response, expected, mutation) {
  const value = classifyHttp(response, expected, mutation);
  httpCompleted.add(1, {http_shape:shape, status:String(value.status), category:value.category});
  if (value.writeOutcome) httpWriteOutcome.add(1, {http_shape:shape, outcome:value.writeOutcome});
  return value;
}
function httpAccountingThresholds(thresholds, selected) {
  // Only called by the existing main-context metadata guard. One bounded metric,
  // no tenant cross product, no per-VU histogram/map, no per-request log.
  for (const shape of selected) {
    thresholds[`m7_http_attempts{http_shape:${shape}}`] = ['count>=0'];
    thresholds[`m7_http_completed{http_shape:${shape}}`] = ['count>=0'];
    for (const status of [0, ...Array.from({length:500}, (_, i) => i + 100)])
      thresholds[`m7_http_completed{http_shape:${shape},status:${status}}`] = ['count>=0'];
    for (const category of ['http_expected','http_refused','http_unexpected','timeout','transport'])
      thresholds[`m7_http_completed{http_shape:${shape},category:${category}}`] = ['count>=0'];
    if (shape.startsWith('w_')) for (const outcome of ['accepted','refused','uncertain'])
      thresholds[`m7_http_write_outcome{http_shape:${shape},outcome:${outcome}}`] = ['count>=0'];
  }
}
