"""Hash-recorded adaptations to existing payload/shape functions, no source mount."""
import hashlib
from pathlib import Path
from contract import require


def generate(root, target):
    baseline=Path(root)/'tools/mt-bench/capacity/k6/workload.js'
    source=baseline.read_text()
    old='const stamp = () => START + exec.scenario.iterationInTest;'
    require(source.count(old)==1,'M7_WORKLOAD_TIMESTAMP_ANCHOR_CHANGED')
    source=source.replace(old,'const stamp = () => START + Math.floor(exec.scenario.iterationInTest * ARRIVAL_CYCLE_MS / weight);')
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
    source=source.replace("Math.round(CYCLE * 1000) + 'ms'","ARRIVAL_CYCLE_MS + 'ms'").replace("Math.ceil(rate / CYCLE)","Math.ceil(rate * 1000 / ARRIVAL_CYCLE_MS)")
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
            'changes':['explicit optional scenario arrival rate with current-clock stamps and separate request-attempt/HTTP-response/transport counters','current nominal arrival timestamps with deterministic uniqueness','explicit read 4xx counter blocks functional advancement','bounded allowlisted JWT setup refusal provenance without credentials, raw URL or response body; first refusal still aborts without retry','existing status GET retains text body for fixed whitelist fingerprint under global discard; no extra request']}
