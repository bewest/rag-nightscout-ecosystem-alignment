// Network-restored backlog (D6 of the AID client model, lane mt-plannable-scale-20261121). Synthetic data only.
// A separate scenario, never part of the steady looping-v2 load: each selected tenant replays a 12 h gap the
// way its controller does when the network returns (read-derived, artifacts aid-model/RESULTS.md section 1):
//   AAPS  ~400 API v3 single-document POSTs back to back, in AAPS's type order (SGV, boluses, carbs, temp
//         basals, temp target, devicestatus), 10 ms apart (NSClientV3Plugin.kt:747-749)
//   Loop  10 v1 array POSTs of 25-50 KB: 144 SGV in one, ~120 doses in one, ~195 statuses in 8 of 25;
//         the three types fire together (a batch), then the remaining statuses in order
//   Trio  5 v1 POSTs: SGV in chunks of 100, treatments in chunks of 100, and only the latest devicestatus;
//         the pipelines run side by side, each serialized
// One VU per selected tenant, one iteration (per-vu-iterations): the burst lands at once, as after an outage.
// Environment: BASE_URL, TENANTS_FILE (rows with loopKind, as looping-v2), RUN_ID, RUN_START (the end of the
// gap), M7_BACKLOG_TENANTS (JSON tenant indices), M7_LOOPING_TEMPLATES (looping_driver.templates_v2),
// M7_BACKLOG_GAP_CYCLES (144), M7_BACKLOG_MAX_SECONDS.
import http from 'k6/http';
import exec from 'k6/execution';
import { sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { SharedArray } from 'k6/data';

const BASE = __ENV.BASE_URL;
const RUN_ID = __ENV.RUN_ID;
const END = Number(__ENV.RUN_START);
const TENANTS = new SharedArray('tenants', () => JSON.parse(open(__ENV.TENANTS_FILE)));
const SELECTED = JSON.parse(__ENV.M7_BACKLOG_TENANTS);
const LOOP = JSON.parse(__ENV.M7_LOOPING_TEMPLATES);
const GAP = Number(__ENV.M7_BACKLOG_GAP_CYCLES || 144);
const MAX_SECONDS = Number(__ENV.M7_BACKLOG_MAX_SECONDS || 900);
const STEP = 300000;
const KINDS = ['loop', 'aaps', 'trio'];
if (!Array.isArray(SELECTED) || !SELECTED.length || !Number.isSafeInteger(END) || !Number.isSafeInteger(GAP) || GAP < 1 ||
    SELECTED.some(i => !Number.isSafeInteger(i) || i < 0 || i >= TENANTS.length || !KINDS.includes(TENANTS[i].loopKind))) {
  throw Error('M7_BACKLOG_CONFIGURATION');
}
export const BACKLOG_SHAPES = ['aaps_v3_entries', 'aaps_v3_treatments', 'aaps_v3_devicestatus', 'loop_v1_entries',
  'loop_v1_treatments', 'loop_v1_devicestatus', 'trio_v1_entries', 'trio_v1_treatments', 'trio_v1_devicestatus'];
const requests = new Counter('m7_backlog_requests'), documents = new Counter('m7_backlog_documents');
const bodyBytes = new Counter('m7_backlog_body_bytes'), outcomes = new Counter('m7_backlog_outcome');
const thresholds = {};
for (const s of BACKLOG_SHAPES) {
  for (const m of ['m7_backlog_requests', 'm7_backlog_documents', 'm7_backlog_body_bytes']) thresholds[`${m}{backlog_shape:${s}}`] = ['count>=0'];
  for (const o of ['accepted', 'refused', 'uncertain']) thresholds[`m7_backlog_outcome{backlog_shape:${s},outcome:${o}}`] = ['count>=0'];
}
export const options = {
  scenarios: {backlog: {executor: 'per-vu-iterations', vus: SELECTED.length, iterations: 1, maxDuration: MAX_SECONDS + 's',
    exec: 'backlog'}},
  thresholds, discardResponseBodies: true,
};

const iso = ms => new Date(ms).toISOString();
// The gap ends at RUN_START; a per-tenant offset keeps its rows off the fixture's and the steady load's grid.
const times = i => Array.from({length: GAP}, (_, k) => END - (GAP - 1 - k) * STEP + 1000 + (i % 250) * 7);
const fill = (text, ms, id) => text.split(LOOP.placeholder).join(iso(ms)).split(LOOP.idPlaceholder).join(id);
const sgv = (ms, k) => ({type: 'sgv', sgv: 90 + (k * 7) % 120, date: ms, dateString: iso(ms), direction: 'Flat', device: RUN_ID,
  noise: 1, filtered: 150000, unfiltered: 150000, rssi: 100, utcOffset: 0});

function classify (res, ok) {
  return ok.includes(res.status) ? 'accepted' : res.status >= 400 && res.status < 500 ? 'refused' : 'uncertain';
}
function request (shape, url, body, headers, ok) {
  const text = JSON.stringify(body);
  requests.add(1, {backlog_shape: shape});
  documents.add(Array.isArray(body) ? body.length : 1, {backlog_shape: shape});
  bodyBytes.add(text.length, {backlog_shape: shape});
  return {method: 'POST', url, body: text, params: {headers: Object.assign({'Content-Type': 'application/json'}, headers),
    tags: {name: 'backlog ' + shape}, timeout: '60s'}, shape, ok};
}
function send (reqs) {
  const out = reqs.length === 1 ? [http.request(reqs[0].method, reqs[0].url, reqs[0].body, reqs[0].params)] : http.batch(reqs);
  out.forEach((res, k) => outcomes.add(1, {backlog_shape: reqs[k].shape, outcome: classify(res, reqs[k].ok)}));
}
const chunks = (rows, n) => Array.from({length: Math.ceil(rows.length / n)}, (_, k) => rows.slice(k * n, k * n + n));

// Treatments over the gap, at the client model's per-controller rates (Temp Basal on about 0.78/0.61/0.51 of
// cycles for Loop/Trio/AAPS, SMB on 0.17/0.21 for Trio/AAPS), deterministic per tenant.
function doses (kind, i, ts) {
  const out = [];
  const tb = {loop: 226, trio: 176, aaps: 147}[kind], smb = {loop: 0, trio: 50, aaps: 60}[kind];
  ts.forEach((ms, k) => {
    const h = (k * 2654435761 + i * 97) >>> 0;
    if (h % 288 < tb) out.push([kind + '_temp_basal', ms]);
    if ((h >>> 9) % 288 < smb) out.push([kind === 'loop' ? 'loop_bolus' : kind + '_smb', ms + 500]);
  });
  return out;
}
function treatment (name, ms, id) {
  const doc = JSON.parse(fill(LOOP.treatments[name], ms, id));
  doc.enteredBy = RUN_ID;
  return doc;
}
function status (set, ms, k) {
  const docs = LOOP.devicestatus[set];
  const doc = JSON.parse(fill(docs[k % docs.length], ms, ''));
  doc.device = RUN_ID;
  return doc;
}

export function backlog () {
  const i = SELECTED[exec.vu.idInTest - 1];
  const t = TENANTS[i], kind = t.loopKind, ts = times(i);
  const v1 = path => BASE + '/api/v1/' + path + '?token=' + t.token;
  const id = n => RUN_ID + '.backlog.' + i + '.' + n;
  const tx = doses(kind, i, ts).map(([name, ms], n) => treatment(name, ms, id(n)));
  if (kind === 'aaps') {
    // One document per request, in AAPS's type order, 10 ms apart; v3 needs `date` and `app`.
    const v3 = (shape, path, doc) => send([request(shape, BASE + '/api/v3/' + path, Object.assign(doc, {app: 'AAPS'}),
      {Authorization: 'Bearer ' + t.jwt}, [200, 201])]);
    ts.forEach((ms, k) => { v3('aaps_v3_entries', 'entries', sgv(ms, k)); sleep(0.01); });
    // boluses (SMB) before temp basals (DataSyncSelectorV3.kt:104-119)
    const ordered = tx.filter(d => d.eventType !== 'Temp Basal').concat(tx.filter(d => d.eventType === 'Temp Basal'));
    ordered.forEach(doc => { doc.date = Date.parse(doc.created_at); doc.pumpId = doc.date; v3('aaps_v3_treatments', 'treatments', doc); sleep(0.01); });
    ts.forEach((ms, k) => { const doc = status('aaps', ms, k); doc.date = ms; v3('aaps_v3_devicestatus', 'devicestatus', doc); sleep(0.01); });
    return;
  }
  if (kind === 'loop') {
    // Statuses: 1.35 per cycle (a second one 1 s later in 7 of every 20 cycles), 25 per POST.
    const statuses = [];
    ts.forEach((ms, k) => {
      statuses.push(status('loop', ms, k));
      if ((k * 7 + i) % 20 < 7) statuses.push(status('loop_extra', ms + 1000, k));
    });
    const parts = chunks(statuses, 25);
    send([request('loop_v1_entries', v1('entries'), ts.map(sgv), {}, [200]),
          request('loop_v1_treatments', v1('treatments'), tx, {}, [200]),
          request('loop_v1_devicestatus', v1('devicestatus'), parts[0], {}, [200])]);
    parts.slice(1).forEach(p => send([request('loop_v1_devicestatus', v1('devicestatus'), p, {}, [200])]));
    return;
  }
  // Trio: chunks of 100 per pipeline (last 24 h only; a 12 h gap is all of it), only the latest status.
  const sgvParts = chunks(ts.map(sgv), 100), txParts = chunks(tx, 100);
  const first = [request('trio_v1_devicestatus', v1('devicestatus'), status('trio_enacted', ts[ts.length - 1], 0), {}, [200])];
  if (sgvParts.length) first.unshift(request('trio_v1_entries', v1('entries'), sgvParts[0], {}, [200]));
  if (txParts.length) first.unshift(request('trio_v1_treatments', v1('treatments'), txParts[0], {}, [200]));
  send(first);
  for (let k = 1; k < Math.max(sgvParts.length, txParts.length); k++) {
    const wave = [];
    if (k < sgvParts.length) wave.push(request('trio_v1_entries', v1('entries'), sgvParts[k], {}, [200]));
    if (k < txParts.length) wave.push(request('trio_v1_treatments', v1('treatments'), txParts[k], {}, [200]));
    send(wave);
  }
}
