"""Hash-recorded adaptations to existing payload/shape functions, no source mount."""
import hashlib
from pathlib import Path
from contract import require


def generate(root, target):
    baseline=Path(root)/'tools/mt-bench/capacity/k6/workload.js'
    source=baseline.read_text()
    old='const stamp = () => START + exec.scenario.iterationInTest;'
    require(source.count(old)==1,'M7_WORKLOAD_TIMESTAMP_ANCHOR_CHANGED')
    source=source.replace(old,'const stamp = () => START + Math.floor(exec.scenario.iterationInTest * CYCLE * 1000 / weight);')
    anchor="const writesRefused = new Counter('writes_refused');"
    require(source.count(anchor)==1,'M7_WORKLOAD_REFUSAL_ANCHOR_CHANGED')
    source=source.replace(anchor,anchor+"\nconst responsesRefused = new Counter('responses_refused');")
    old_get="""  return http.get(BASE + path + q(path.includes('?')) + 'token=' + t.token,
    { headers: { Host: t.host }, tags: { name }, timeout: '30s' });"""
    require(source.count(old_get)==1,'M7_WORKLOAD_GET_ANCHOR_CHANGED')
    source=source.replace(old_get,"""  const response = http.get(BASE + path + q(path.includes('?')) + 'token=' + t.token,
    { headers: { Host: t.host }, tags: { name }, timeout: '30s' });
  if (response.status >= 400 && response.status < 500) responsesRefused.add(1);
  return response;""")
    helper=(Path(__file__).parent/'fingerprint.cjs').read_text()
    projection=helper[helper.index('function projection('):helper.index("const fs = require(")]
    source="import { sha256 } from 'k6/crypto';\n"+source
    source+= "\n"+projection+"\n"
    source+= "const fingerprintObserved = new Counter('settings_fingerprint_observed');\nconst fingerprintInvalid = new Counter('settings_fingerprint_invalid');\nconst fingerprintMismatch = new Counter('settings_fingerprint_mismatch');\n"
    old="export function r_status () { const { t } = pick(); get(t, '/api/v1/status.json', 'GET v1 status'); }"
    require(source.count(old)==1,'M7_WORKLOAD_STATUS_ANCHOR_CHANGED')
    source=source.replace(old,"""export function r_status () {
      const { t } = pick(); const response = get(t, '/api/v1/status.json', 'GET v1 status');
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
            'changes':['current nominal arrival timestamps with deterministic uniqueness','explicit read 4xx counter blocks functional advancement','existing status response fixed whitelist fingerprint; no extra request']}
