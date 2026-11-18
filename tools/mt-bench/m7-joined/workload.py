"""Hash-recorded adaptations to existing payload/shape functions, no source mount."""
import hashlib
import json
from pathlib import Path
from contract import require


REALISTIC_MIX = 'realistic-v1'
REALISTIC_CADENCE_MS = {
    'w_sgv': 300000,
    'w_devicestatus': 300000,
    'w_treatments_v3': 1800000,
    'r_sgv': 300000,
    'r_devicestatus': 900000,
    'r_treatments': 900000,
    'r_status': 900000,
}


def generate(root, target):
    baseline=Path(root)/'tools/mt-bench/capacity/k6/workload.js'
    source=baseline.read_text()
    old='const stamp = () => START + exec.scenario.iterationInTest;'
    require(source.count(old)==1,'M7_WORKLOAD_TIMESTAMP_ANCHOR_CHANGED')
    source=source.replace(old,'const stamp = () => START + Math.floor(exec.scenario.iterationInTest * cycleMs(exec.scenario.name) / weight);')
    anchor="const writesRefused = new Counter('writes_refused');"
    require(source.count(anchor)==1,'M7_WORKLOAD_REFUSAL_ANCHOR_CHANGED')
    source=source.replace(anchor,anchor+"\nconst responsesRefused = new Counter('responses_refused');")
    old_get="""  return http.get(BASE + path + q(path.includes('?')) + 'token=' + t.token,
    { headers: { Host: t.host }, tags: { name }, timeout: '30s' });"""
    require(source.count(old_get)==1,'M7_WORKLOAD_GET_ANCHOR_CHANGED')
    signature='function get (t, path, name) {'
    require(source.count(signature)==1,'M7_WORKLOAD_GET_SIGNATURE_CHANGED')
    source=source.replace(signature,'function get (t, path, name, responseType) {')
    source=source.replace(old_get,"""  const response = http.get(BASE + path + q(path.includes('?')) + 'token=' + t.token,
    { headers: { Host: t.host }, tags: { name }, timeout: '30s', ...(responseType === undefined ? {} : {responseType}) });
  if (response.status >= 400 && response.status < 500) responsesRefused.add(1);
  return response;""")
    arrival="const shapes = Object.fromEntries(Object.entries(ALL_SHAPES).filter(([name]) => SELECTED.includes(name)));"
    require(source.count(arrival)==1,'M7_WORKLOAD_ARRIVAL_ANCHOR_CHANGED')
    source=source.replace(arrival,arrival+"\nconst offered = __ENV.OFFERED_RPS === undefined ? null : Number(__ENV.OFFERED_RPS);\nif(offered !== null && (!Number.isFinite(offered) || offered < 1 || offered > 10000)) throw Error('M7_OFFERED_RPS_RANGE');\nconst ARRIVAL_CYCLE_MS = offered === null ? Math.round(CYCLE * 1000) : Math.round(Object.values(shapes).reduce((a,b)=>a+b,0)*weight*1000/offered);\nif(ARRIVAL_CYCLE_MS < 1) throw Error('M7_OFFERED_RPS_TIME_UNIT');")
    scenario_anchor = "const scenarios = {};"
    require(source.count(scenario_anchor) == 1, 'M7_WORKLOAD_SCENARIO_ANCHOR_CHANGED')
    source = source.replace(scenario_anchor, f"""
const mix = __ENV.M7_WORKLOAD_MIX;
const workloadScale = __ENV.M7_WORKLOAD_SCALE === undefined ? 1 : Number(__ENV.M7_WORKLOAD_SCALE);
if (!Number.isFinite(workloadScale) || workloadScale < 0.25 || workloadScale > 8 ||
    (__ENV.M7_WORKLOAD_SCALE !== undefined && mix !== '{REALISTIC_MIX}')) throw Error('M7_WORKLOAD_SCALE_CONFIGURATION');
const realisticCadenceMs = {json.dumps(REALISTIC_CADENCE_MS)};
if (mix !== undefined &&
    (mix !== '{REALISTIC_MIX}' || offered !== null || ACCEL !== 1 || HOT !== 1 ||
     Object.keys(realisticCadenceMs).some(name => !shapes[name]))) {{
  throw Error('M7_REALISTIC_MIX_CONFIGURATION');
}}
const cycleMs = name => mix === undefined ? ARRIVAL_CYCLE_MS : Math.round(realisticCadenceMs[name] * shapes[name] / workloadScale);
{scenario_anchor}""")
    source=source.replace("Math.round(CYCLE * 1000) + 'ms'","cycleMs(name) + 'ms'").replace("Math.ceil(rate / CYCLE)","Math.ceil(rate * 1000 / cycleMs(name))")
    source=source.replace("const responsesRefused = new Counter('responses_refused');", "const responsesRefused = new Counter('responses_refused');\nconst scenarioAttempts = new Counter('scenario_request_attempts'), scenarioResponses = new Counter('scenario_http_responses'), scenarioTransport = new Counter('scenario_transport_failures');")
    source=source.replace("  const response = http.get(BASE + path", "  scenarioAttempts.add(1);\n  const response = http.get(BASE + path")
    source=source.replace("  if (response.status >= 400", "  (response.status > 0 ? scenarioResponses : scenarioTransport).add(1);\n  if (response.status >= 400")
    source=source.replace("  const res = http.post(url,", "  scenarioAttempts.add(1);\n  const res = http.post(url,")
    source=source.replace("  const tags = { tenant: t.id, kind };", "  (res.status > 0 ? scenarioResponses : scenarioTransport).add(1);\n  const tags = { tenant: t.id, kind };")
    source=source.replace("const thresholds = {};", "const thresholds = {scenario_request_attempts:['count>=0'],scenario_http_responses:['count>=0'],scenario_transport_failures:['count>=0'],writes_refused:['count>=0'],responses_refused:['count>=0'],dropped_iterations:['count>=0']};")
    setup_anchor="""function exchangeResponse (res, tenantIndex, startedAtMs) {
  if (res.status !== 200) throw new Error('exchange refused ' + res.status);"""
    require(source.count(setup_anchor)==1,'M7_WORKLOAD_SETUP_ANCHOR_CHANGED')
    source=source.replace(setup_anchor,r"""function exchangeResponse (res, tenantIndex, startedAtMs) {
  if (res.status !== 200) {
    const finishedAtMs = Date.now();
    const allowed = ['AUTHORITY_UNAVAILABLE','TENANT_ACTIVITY_UNAVAILABLE','TENANT_WARMING','TENANT_UNAVAILABLE',
      'HUMAN_SESSION_UNAVAILABLE','ACCESS_AUTHORITY_UNAVAILABLE','ACCESS_AUTHORITY_INVALID','TENANT_SNAPSHOT_UNAVAILABLE',
      'TENANT_REFUSED','CREDENTIAL_REFUSED','TENANT_LEGACY_FORBIDDEN','AUTHORITY_FORBIDDEN'];
    let errorCode = null, bodyObservation = 'NOT_JSON';
    const headers = res.headers || {};
    const type = headers['Content-Type'] || headers['content-type'] || '';
    if (typeof res.body !== 'string' || res.body.length > 4096) bodyObservation = 'BODY_OUTSIDE_BOUND';
    else if (typeof type === 'string' && /^(application\/json|application\/problem\+json)(;|$)/i.test(type)) {
      try {
        const value = JSON.parse(res.body);
        if (value && typeof value === 'object' && allowed.includes(value.error)) { errorCode = value.error; bodyObservation = 'ALLOWLISTED_ERROR_CODE'; }
        else bodyObservation = 'UNRECOGNIZED_ERROR_CODE';
      } catch (_) { bodyObservation = 'INVALID_JSON'; }
    }
    const retry = headers['Retry-After'] || headers['retry-after'];
    const retryAfterSeconds = typeof retry === 'string' && /^[0-9]{1,3}$/.test(retry) && Number(retry) <= 300 ? Number(retry) : null;
    console.error('M7_SETUP_REFUSAL ' + JSON.stringify({phase:'jwt-setup',tenantIndex,requestOrdinal:tenantIndex+1,
      status:res.status,errorCode,bodyObservation,retryAfterSeconds,startedAtMs,finishedAtMs,elapsedMs:finishedAtMs-startedAtMs}));
    throw new Error('exchange refused ' + res.status);
  }""")
    accounting=(Path(__file__).parent/'http-accounting.cjs').read_text().split('// BEGIN_K6_HTTP_ACCOUNTING\n',1)[1].split('// END_K6_HTTP_ACCOUNTING',1)[0]
    source += "\n" + accounting + "\nconst httpAttempts = new Counter('m7_http_attempts'), httpCompleted = new Counter('m7_http_completed'), httpWriteOutcome = new Counter('m7_http_write_outcome');\n"
    def account(old,new):
        nonlocal source
        require(source.count(old)==1,'M7_WORKLOAD_HTTP_ACCOUNTING_ANCHOR_CHANGED')
        source=source.replace(old,new)
    account("  TENANTS.forEach(t => { thresholds[", "  httpAccountingThresholds(thresholds, Object.keys(shapes));\n  TENANTS.forEach(t => { thresholds[")
    account("  scenarioAttempts.add(1);\n  const response = http.get(BASE + path", "  const httpShape = ({'GET v1 sgv count=1':'r_sgv','GET v1 devicestatus count=1':'r_devicestatus','GET v1 treatments count=10':'r_treatments','GET v1 status':'r_status'})[name];\n  httpAttempts.add(1,{http_shape:httpShape});\n  scenarioAttempts.add(1);\n  const response = http.get(BASE + path")
    account("  (response.status > 0 ? scenarioResponses : scenarioTransport).add(1);", "  recordHttp(httpShape,response,[200],false);\n  (response.status > 0 ? scenarioResponses : scenarioTransport).add(1);")
    account("  scenarioAttempts.add(1);\n  const res = http.post(url,", "  const httpShape = ({entries:'w_sgv',devicestatus:'w_devicestatus',treatments:'w_treatments_v3'})[kind];\n  httpAttempts.add(1,{http_shape:httpShape});\n  scenarioAttempts.add(1);\n  const res = http.post(url,")
    account("  (res.status > 0 ? scenarioResponses : scenarioTransport).add(1);", "  recordHttp(httpShape,res,okStatuses,true);\n  (res.status > 0 ? scenarioResponses : scenarioTransport).add(1);")
    account("else if (res.status === 0 || res.status >= 500) writesUncertain.add(1, tags);", "else if (!(res.status >= 400 && res.status < 500)) writesUncertain.add(1, tags);")
    account("function exchangeRequest (t) {", "function exchangeRequest (t) {\n  httpAttempts.add(1,{http_shape:'jwt_setup'});")
    account("    for (let j = 0; j < requests.length; j++) {", "    // Settle the whole dispatched batch before the first JWT refusal aborts.\n    for (const response of responses) recordHttp('jwt_setup',response,[200],false);\n    for (let j = 0; j < requests.length; j++) {")
    helper=(Path(__file__).parent/'fingerprint.cjs').read_text()
    projection=helper[helper.index('function projection('):helper.index("const fs = require(")]
    source="import { sha256 } from 'k6/crypto';\n"+source
    source+= "\n"+projection+"\n"
    source+= "const fingerprintObserved = new Counter('settings_fingerprint_observed');\nconst fingerprintInvalid = new Counter('settings_fingerprint_invalid');\nconst fingerprintMismatch = new Counter('settings_fingerprint_mismatch');\n"
    old="export function r_status () { const { t } = pick(); get(t, '/api/v1/status.json', 'GET v1 status'); }"
    require(source.count(old)==1,'M7_WORKLOAD_STATUS_ANCHOR_CHANGED')
    source=source.replace(old,"""export function r_status () {
      const { t } = pick(); const response = get(t, '/api/v1/status.json', 'GET v1 status', 'text');
      if (response.status !== 200) return;
      try {
        if (typeof response.body !== 'string' || response.body.length > 131072 || !/^[a-f0-9]{64}$/.test(__ENV.SETTINGS_FINGERPRINT || '')) throw Error('invalid');
        const encoded = projection(JSON.parse(response.body));
        fingerprintObserved.add(1);
        if (sha256(encoded, 'hex') !== __ENV.SETTINGS_FINGERPRINT) fingerprintMismatch.add(1);
      } catch (_) { fingerprintInvalid.add(1); }
    }""")
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(source)
    return {'baseline':'tools/mt-bench/capacity/k6/workload.js','baselineSha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
            'adaptedSha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'changes':['exact bounded per-shape HTTP status and outcome counters, JWT setup separate, main-context-only histogram metadata; unexpected mutation responses remain uncertain','explicit optional scenario arrival rate with current-clock stamps and separate request-attempt/HTTP-response/transport counters','current nominal arrival timestamps with deterministic uniqueness','opt-in realistic-v1 per-shape cadence with equal tenant weights and bounded optional uniform rate bracket; scale1 preserves sensor cadence','explicit read 4xx counter blocks functional advancement','bounded allowlisted JWT setup refusal provenance without credentials, raw URL or response body; first refusal still aborts without retry','existing status GET retains text body for fixed whitelist fingerprint under global discard; no extra request']}
