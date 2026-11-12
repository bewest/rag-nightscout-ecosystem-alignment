// Capacity-campaign copy of compose-baseline/k6/workload.js (k6). Synthetic data only.
// Differences: SHAPES selects the client shapes (default: CGM uploader, Loop devicestatus and the
// follower reads; no AAPS-style v3 treatments), and the JWT exchange runs only when v3 is selected.
//
// One "cycle" is the 5-minute CGM cadence compressed by ACCEL (default 60: one cycle per 5 s).
// Per tenant per cycle, pinned to the shapes of shipping clients:
//   uploader (xDrip+/cgmsim)  POST /api/v1/entries          1 sgv          token= query
//   loop/oref0 uploader       POST /api/v1/devicestatus     1 loop status  token= query
//   AAPS-style uploader       POST /api/v3/treatments       1 temp basal   Bearer JWT (exchanged once)
//   follower apps (polling)   GET  /api/v1/entries/sgv.json?count=1   x5 (one per real minute)
//                             GET  /api/v1/devicestatus.json?count=1  x1
//                             GET  /api/v1/treatments.json?count=10   x1
//                             GET  /api/v1/status.json                x1
// The hot tenant (index 0) carries HOT_FACTOR times every shape.
// v1 POST /api/v1/treatments is not used: the reference tenants do not enable careportal,
// so it answers 401 exactly as a single-tenant site without careportal does.
//
// Every write carries RUN_ID (entries/devicestatus `device`, treatments `enteredBy`) and a
// timestamp unique within the run, so the stored-count oracle can count it independently.
import http from 'k6/http';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';

const BASE = __ENV.BASE_URL;
const RUN_ID = __ENV.RUN_ID;
const DURATION = Number(__ENV.DURATION || 120);
const ACCEL = Number(__ENV.ACCEL || 60);
const HOT = Number(__ENV.HOT_FACTOR || 10);
const TENANTS = JSON.parse(open(__ENV.TENANTS_FILE));
const CYCLE = 300 / ACCEL; // seconds per compressed 5-minute cycle
// One fixed origin for the whole run (every VU evaluates init code separately, so Date.now() here would
// differ per VU and let two VUs' timestamps collide, which the server's dedup then merges).
const START = Number(__ENV.RUN_START); // writes are dated from here, one ms apart per scenario iteration

const writesOk = new Counter('writes_ok');
const writesUncertain = new Counter('writes_uncertain');
const writesRefused = new Counter('writes_refused');

// Weighted tenant wheel: the hot tenant appears HOT times.
const wheel = [];
TENANTS.forEach((t, i) => { for (let k = 0; k < (i === 0 ? HOT : 1); k++) wheel.push(i); });
const weight = wheel.length;

const ALL_SHAPES = {
  w_sgv: 1, w_devicestatus: 1, w_treatments_v3: 1,
  r_sgv: 5, r_devicestatus: 1, r_treatments: 1, r_status: 1,
};
const SELECTED = (__ENV.SHAPES || 'w_sgv,w_devicestatus,r_sgv,r_devicestatus,r_treatments,r_status').split(',');
const shapes = Object.fromEntries(Object.entries(ALL_SHAPES).filter(([name]) => SELECTED.includes(name)));
const scenarios = {};
for (const [name, perCycle] of Object.entries(shapes)) {
  const rate = perCycle * weight; // iterations per CYCLE seconds
  scenarios[name] = {
    executor: 'constant-arrival-rate', exec: name, rate, timeUnit: Math.round(CYCLE * 1000) + 'ms',
    duration: DURATION + 's', preAllocatedVUs: Math.min(400, Math.ceil(rate / CYCLE) * 2 + 5), maxVUs: 800,
    tags: { shape: name },
  };
}
const thresholds = {};
TENANTS.forEach(t => { thresholds[`writes_ok{tenant:${t.id}}`] = ['count>=0']; thresholds[`writes_uncertain{tenant:${t.id}}`] = ['count>=0']; });
for (const k of ['entries', 'devicestatus', 'treatments']) thresholds[`writes_ok{kind:${k}}`] = ['count>=0'];
for (const name of Object.keys(shapes)) thresholds[`http_req_duration{shape:${name}}`] = ['max>=0'];
for (const name of Object.keys(shapes)) thresholds[`http_req_failed{shape:${name}}`] = ['rate>=0'];

export const options = {
  scenarios, thresholds, discardResponseBodies: true, noConnectionReuse: false,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  setupTimeout: '300s',
};

function pick () {
  const i = wheel[exec.scenario.iterationInTest % weight];
  return { i, t: TENANTS[i] };
}
const q = t => (t ? '&' : '?');
function get (t, path, name) {
  return http.get(BASE + path + q(path.includes('?')) + 'token=' + t.token,
    { headers: { Host: t.host }, tags: { name }, timeout: '30s' });
}
function write (t, kind, url, body, headers, okStatuses, name) {
  const res = http.post(url, JSON.stringify(body), { headers: Object.assign({ Host: t.host, 'Content-Type': 'application/json' }, headers),
    tags: { name }, timeout: '30s', responseCallback: http.expectedStatuses(...okStatuses) });
  const tags = { tenant: t.id, kind };
  if (okStatuses.includes(res.status)) writesOk.add(1, tags);
  else if (res.status === 0 || res.status >= 500) writesUncertain.add(1, tags); // may have committed
  else writesRefused.add(1, tags);
  return res;
}

// JWT per tenant for the v3 shape: exchanged once in setup (the stock browser and AAPS-style clients
// exchange, then reuse until expiry).
export function setup () {
  if (!shapes.w_treatments_v3) return { jwts: [] };
  const jwts = TENANTS.map(t => {
    const res = http.get(BASE + '/api/v2/authorization/request/' + encodeURIComponent(t.token),
      { headers: { Host: t.host, Accept: 'application/json' }, tags: { name: 'exchange' }, responseType: 'text', timeout: '60s' });
    if (res.status !== 200) throw new Error('exchange refused ' + res.status);
    return JSON.parse(res.body).token;
  });
  return { jwts };
}

const stamp = () => START + exec.scenario.iterationInTest; // unique per scenario
const iso = ms => new Date(ms).toISOString();

export function w_sgv () {
  const { t } = pick(); const ms = stamp();
  write(t, 'entries', BASE + '/api/v1/entries?token=' + t.token,
    [{ type: 'sgv', sgv: 80 + (ms % 120), date: ms, dateString: iso(ms), direction: 'Flat', delta: 1.2, filtered: 180000, unfiltered: 180000, rssi: 100, noise: 1, device: RUN_ID }],
    {}, [200], 'POST v1 entries');
}
export function w_devicestatus () {
  const { t } = pick(); const ms = stamp(); const at = iso(ms);
  write(t, 'devicestatus', BASE + '/api/v1/devicestatus?token=' + t.token,
    [{ device: RUN_ID, created_at: at, uploader: { battery: 88 },
      loop: { name: 'Loop', version: '3.4', timestamp: at, iob: { timestamp: at, iob: 1.234 }, cob: { timestamp: at, cob: 12 },
        predicted: { startDate: at, values: Array.from({ length: 72 }, (_, k) => 120 + (k % 7)) }, recommendedBolus: 0,
        enacted: { rate: 0.75, duration: 30, timestamp: at, received: true } } }],
    {}, [200], 'POST v1 devicestatus');
}
export function w_treatments_v3 (data) {
  const { i, t } = pick(); const ms = stamp();
  write(t, 'treatments', BASE + '/api/v3/treatments',
    { eventType: 'Temp Basal', duration: 30, absolute: 0.8, rate: 0.8, date: ms, created_at: iso(ms), utcOffset: 0, app: 'bench', enteredBy: RUN_ID },
    { Authorization: 'Bearer ' + data.jwts[i] }, [200, 201], 'POST v3 treatments');
}
export function r_sgv () { const { t } = pick(); get(t, '/api/v1/entries/sgv.json?count=1', 'GET v1 sgv count=1'); }
export function r_devicestatus () { const { t } = pick(); get(t, '/api/v1/devicestatus.json?count=1', 'GET v1 devicestatus count=1'); }
export function r_treatments () { const { t } = pick(); get(t, '/api/v1/treatments.json?count=10', 'GET v1 treatments count=10'); }
export function r_status () { const { t } = pick(); get(t, '/api/v1/status.json', 'GET v1 status'); }
