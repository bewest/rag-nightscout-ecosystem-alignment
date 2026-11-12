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
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(source)
    return {'baseline':'tools/mt-bench/capacity/k6/workload.js','baselineSha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
            'adaptedSha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'changes':['current nominal arrival timestamps with deterministic uniqueness','explicit read 4xx counter blocks functional advancement']}
