"""Compatibility entry points onto `assessor.py` (decision `four-product-failures`).

Both platforms retain the same load-folder files, so both judges are one call.
The midpoint is a recorded signal and never stops the driver. Callers still
using `from_pages`, `classify_point`, `midpoint_decision`, `sampled_oracle`,
`storage` or `instrument` get figures only; the integrator removes those calls.
"""
import glob
import json
import os
from pathlib import Path

import assessor

CONTRACT = assessor.CONTRACT


def instrument():
    return {'contract': CONTRACT}


def judge_kubernetes_load(folder, ids, *, config=None, attribution=None):
    verdict = assessor.judge(folder, ids)
    verdict['attribution'] = attribution or {}
    return verdict


def judge_compose_run(directory, ids, *, config=None, attribution=None):
    return judge_kubernetes_load(Path(directory)/'load', ids, attribution=attribution)


def from_pages(raw_by_service):
    """Raw evaluator progress pages, kept as figures."""
    rows, unreadable = 0, 0
    for data in (raw_by_service or {}).values():
        for line in (data or b'').splitlines():
            try:
                rows += len(json.loads(line)['view']['tenants'])
            except (ValueError, KeyError, TypeError):
                unreadable += 1
    return {'rows': rows, 'unreadablePages': unreadable}


def classify_point(point, ids, *, final=False, config=None):
    return {'verdict': 'PASS', 'codes': [], 'figures': {**(point or {}), 'roster': len(set(ids))}}


def midpoint_decision(classification):
    return {'action': 'continue', 'reason': None, 'signal': 'RECORDED', 'figures': (classification or {}).get('figures')}


def sampled_oracle(completed_output):
    return assessor.sampled_clinical(completed_output)


def storage(findings):
    events = assessor.count_events(findings, {}) if isinstance(findings, dict) else []
    if events:
        events += [{'event': 'readback', 'what': 'storage', 'writer': w} for w in ('ordinary', 'probe')]
    return assessor.assess(events)['components']['storedWrites']


def http_latency(directory):
    """HTTP request duration per k6 shard summary. A figure, never a gate."""
    folder = Path(directory)
    files = sorted(glob.glob(str(folder/'k6-summary-[0-9]*.json')), key=lambda p: int(Path(p).stem.rsplit('-', 1)[1]))
    files = files or [str(folder/'k6-summary.json')] * (folder/'k6-summary.json').is_file()
    shards = []
    for path in files:
        try:
            metrics = json.loads(Path(path).read_text()).get('metrics', {})
        except (OSError, ValueError, AttributeError):
            continue
        row = {'file': os.path.basename(path)}
        for name, value in metrics.items():
            if name == 'http_req_duration' or name.startswith('http_req_duration{shape:'):
                key = 'all' if name == 'http_req_duration' else name[len('http_req_duration{shape:'):-1]
                row[key] = {k: value.get(k) for k in ('count', 'avg', 'med', 'p(95)', 'p(99)', 'max')}
        shards.append(row)
    return {'verdict': 'MEASURED' if shards else 'UNMEASURED', 'shardCount': len(shards), 'perShard': shards,
            'scope': 'per-shard k6 statistics; pooled quantiles need raw samples; signal only'}
