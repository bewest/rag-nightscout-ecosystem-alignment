"""Exact source-access census over the existing bounded private inspection port.

This does not infer acquisition from checkpoints or output revisions. The caller
owns source/image preflight and current-effect qualification. collect() reuses
that caller's existing ownership/source checks and Compose execution boundary.
"""
import json
import math
from pathlib import Path
import re
import time
import uuid
import evaluator_progress as p
from contract import DISCOVERY_MAX_WORKERS

KIND = 'evaluator-source-access-v1'
CATEGORIES = ('snapshot', 'catalogue', 'data')
COUNTERS = tuple(category + suffix for category in CATEGORIES for suffix in ('Attempts', 'Completed'))
FIELDS = set(COUNTERS) | {'residentTenants', 'residentEncodedBytes', 'evictions'}
PREVIOUS_LIMITS = {'maxInstances': 4, 'selectorRows': 128, 'queries': 4,
          'responseBytes': 1048576, 'totalBytes': 4194304, 'seconds': 20,
          'residentTenants': 10000, 'residentEncodedBytes': 268435456}
LIMITS = {**PREVIOUS_LIMITS, 'maxInstances':DISCOVERY_MAX_WORKERS, 'queries':DISCOVERY_MAX_WORKERS}
_OBSERVER = str(uuid.uuid4())


def binding(value):
    p.need(isinstance(value, dict) and set(value) == {'pair', 'imageId', 'instrument', 'hostIdentity'}, 'M7_SOURCE_ACCESS_BINDING', 'FAIL')
    pair = value['pair']
    p.need(isinstance(pair, dict) and set(pair) == {'core', 'deploy'} and all(isinstance(x, str) and re.fullmatch(r'[a-f0-9]{40}', x) for x in pair.values()), 'M7_SOURCE_ACCESS_BINDING', 'FAIL')
    p.need(isinstance(value['imageId'], str) and re.fullmatch(r'sha256:[a-f0-9]{64}', value['imageId']) and all(isinstance(value[k], str) and re.fullmatch(r'[a-f0-9]{64}', value[k]) for k in ('instrument', 'hostIdentity')), 'M7_SOURCE_ACCESS_BINDING', 'FAIL')
    return value


def owner(value):
    p.need(isinstance(value, str) and re.fullmatch(r'[a-f0-9]{32}', value), 'M7_SOURCE_ACCESS_OWNER', 'FAIL')


def counters(value):
    p.need(isinstance(value, dict) and set(value) == FIELDS and all(p.integer(x) for x in value.values()), 'M7_SOURCE_ACCESS_COUNTERS')
    p.need(all(value[k + 'Completed'] <= value[k + 'Attempts'] for k in CATEGORIES), 'M7_SOURCE_ACCESS_COUNTERS')
    p.need(value['residentTenants'] <= LIMITS['residentTenants'] and value['residentEncodedBytes'] <= LIMITS['residentEncodedBytes'], 'M7_SOURCE_ACCESS_RESIDENCY_BOUND', 'FAIL')
    return dict(value)


def selector(ids, services):
    p.need(isinstance(ids, list) and 1 <= len(ids) <= LIMITS['selectorRows'] and len(set(ids)) == len(ids) and all(isinstance(x, str) and p.UUID.fullmatch(x) for x in ids), 'M7_SOURCE_ACCESS_SELECTOR')
    p.need(isinstance(services, list) and 1 <= len(services) <= LIMITS['maxInstances'] and len(set(services)) == len(services) and all(isinstance(x, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,62}', x) for x in services), 'M7_SOURCE_ACCESS_SERVICES')


def capture(fetch, ids, services, source, owned, *, seconds=20, observer_id=_OBSERVER,
            monotonic_ns=time.monotonic_ns, cpu=time.process_time):
    """fetch(service, ids, queries, bytes, timeout) is the existing private port.

    Retain partial completed service reads and actual cost after a later refusal.
    Each selected read returns runtime-wide counters, not a per-tenant census.
    """
    binding(source); owner(owned); selector(ids, services)
    p.need(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= LIMITS['seconds'], 'M7_SOURCE_ACCESS_DEADLINE')
    p.need(isinstance(observer_id, str) and p.UUID.fullmatch(observer_id), 'M7_SOURCE_ACCESS_OBSERVER')
    started = monotonic_ns(); process = cpu(); deadline = started + int(seconds * 1e9)
    rows = {}; used_bytes = 0; queries = 0; code = None; verdict = 'PASS'
    try:
        for service in services:
            remaining = (deadline - monotonic_ns()) / 1e9
            p.need(remaining > 0, 'M7_SOURCE_ACCESS_DEADLINE')
            queries += 1
            raw = fetch(service, ids, 1, LIMITS['responseBytes'], min(remaining, 15))
            p.need(isinstance(raw, (str, bytes)), 'M7_SOURCE_ACCESS_RESPONSE')
            raw = raw.encode() if isinstance(raw, str) else raw
            used_bytes += len(raw)
            p.need(len(raw) <= LIMITS['responseBytes'] and used_bytes <= LIMITS['totalBytes'], 'M7_SOURCE_ACCESS_BYTE_BOUND')
            value = json.loads(raw)
            p.need(isinstance(value, dict) and set(value) == {'selected', 'runtimeId', 'sourceAccess', 'observedAt'} and value['selected'] == ids, 'M7_SOURCE_ACCESS_RESPONSE')
            p.need(isinstance(value['runtimeId'], str) and p.UUID.fullmatch(value['runtimeId']), 'M7_SOURCE_ACCESS_RUNTIME')
            p.need(p.integer(value['observedAt']), 'M7_SOURCE_ACCESS_CLOCK')
            value['sourceAccess'] = counters(value['sourceAccess'])
            p.need(value['runtimeId'] not in {row['runtimeId'] for row in rows.values()}, 'M7_SOURCE_ACCESS_INSTANCE', 'FAIL')
            rows[service] = value
            p.need(monotonic_ns() <= deadline, 'M7_SOURCE_ACCESS_DEADLINE')
    except p.Refused as error:
        verdict = error.verdict; code = str(error)
    except Exception:
        verdict = 'UNMEASURED'; code = 'M7_SOURCE_ACCESS_UNAVAILABLE'
    ended = monotonic_ns()
    return {'kind': KIND, 'source': json.loads(json.dumps(source)), 'owner': owned, 'observerId': observer_id,
            'selected': list(ids), 'services': list(services), 'rows': rows,
            'verdict': verdict, 'code': code, 'clock': 'single observer time.monotonic_ns',
            'readWindow': {'startNs': started, 'endNs': ended}, 'limits': dict(LIMITS),
            'cost': {'queries': queries, 'responseBytes': used_bytes,
                     'wallSeconds': (ended - started) / 1e9, 'observerProcessCpuSeconds': cpu() - process},
            'scope': 'runtime-wide actual source access; selected tenant inspection only; no output/clinical/authority qualification'}


def _decode(value, source, owned):
    p.need(isinstance(value, dict) and value.get('kind') == KIND, 'M7_SOURCE_ACCESS_CAPTURE')
    p.need(value.get('source') == source, 'M7_SOURCE_ACCESS_BINDING', 'FAIL')
    p.need(value.get('owner') == owned, 'M7_SOURCE_ACCESS_OWNER', 'FAIL')
    p.need(value.get('verdict') == 'PASS', value.get('code') or 'M7_SOURCE_ACCESS_PARTIAL', value.get('verdict') if value.get('verdict') in ('FAIL', 'UNMEASURED') else 'UNMEASURED')
    selector(value['selected'], value['services'])
    limits=value.get('limits')
    p.need(limits in (PREVIOUS_LIMITS,LIMITS) and len(value['services'])<=limits['queries'] and
           value.get('clock') == 'single observer time.monotonic_ns', 'M7_SOURCE_ACCESS_LIMITS')
    window = value.get('readWindow', {})
    p.need(set(window) == {'startNs', 'endNs'} and all(type(x) is int and x >= 0 for x in window.values()) and window['startNs'] <= window['endNs'] and window['endNs'] - window['startNs'] <= LIMITS['seconds'] * 1e9, 'M7_SOURCE_ACCESS_CLOCK')
    cost = value.get('cost', {})
    p.need(set(cost) == {'queries', 'responseBytes', 'wallSeconds', 'observerProcessCpuSeconds'} and cost['queries'] == len(value['services']) and p.integer(cost['responseBytes'], 1) and cost['responseBytes'] <= LIMITS['totalBytes'] and all(type(cost[k]) in (int, float) and math.isfinite(cost[k]) and cost[k] >= 0 for k in ('wallSeconds', 'observerProcessCpuSeconds')) and abs(cost['wallSeconds'] - (window['endNs'] - window['startNs']) / 1e9) < 1e-9, 'M7_SOURCE_ACCESS_COST')
    p.need(isinstance(value.get('rows'), dict) and set(value['rows']) == set(value['services']), 'M7_SOURCE_ACCESS_COVERAGE')
    p.need(len({row.get('runtimeId') for row in value['rows'].values() if isinstance(row, dict)}) == len(value['services']), 'M7_SOURCE_ACCESS_INSTANCE', 'FAIL')
    for row in value['rows'].values():
        p.need(isinstance(row, dict) and set(row) == {'selected', 'runtimeId', 'sourceAccess', 'observedAt'} and row['selected'] == value['selected'], 'M7_SOURCE_ACCESS_RESPONSE')
        p.need(isinstance(row['runtimeId'], str) and p.UUID.fullmatch(row['runtimeId']) and p.integer(row['observedAt']), 'M7_SOURCE_ACCESS_RUNTIME')
        counters(row['sourceAccess'])
    return value


def assess(before, after, source, owned, *, criterion):
    """Compare exact process incarnations; never subtract checkpoint revisions."""
    try:
        binding(source); owner(owned)
        p.need(criterion in ('timer-only', 'acquisition'), 'M7_SOURCE_ACCESS_CRITERION')
        a = _decode(before, source, owned); b = _decode(after, source, owned)
        p.need(a['limits']==b['limits'], 'M7_SOURCE_ACCESS_LIMITS')
        p.need(a['observerId'] == b['observerId'] and isinstance(a['observerId'], str) and p.UUID.fullmatch(a['observerId']) and a['services'] == b['services'] and a['selected'] == b['selected'], 'M7_SOURCE_ACCESS_OBSERVER')
        p.need(a['readWindow']['endNs'] <= b['readWindow']['startNs'], 'M7_SOURCE_ACCESS_CLOCK')
        deltas = {}; totals = dict.fromkeys(COUNTERS + ('evictions',), 0)
        for service in a['services']:
            first = a['rows'][service]; last = b['rows'][service]
            p.need(first['runtimeId'] == last['runtimeId'], 'M7_SOURCE_ACCESS_INCARNATION')
            x = first['sourceAccess']; y = last['sourceAccess']
            p.need(all(y[k] >= x[k] for k in COUNTERS + ('evictions',)), 'M7_SOURCE_ACCESS_RESET', 'FAIL')
            delta = {k: y[k] - x[k] for k in COUNTERS + ('evictions',)}
            deltas[service] = {'runtimeId': first['runtimeId'], 'delta': delta,
                               'residencyBefore': {k: x[k] for k in ('residentTenants', 'residentEncodedBytes')},
                               'residencyAfter': {k: y[k] for k in ('residentTenants', 'residentEncodedBytes')}}
            for key in totals:totals[key] += delta[key]
        attempts = sum(totals[k + 'Attempts'] for k in CATEGORIES)
        completed = sum(totals[k + 'Completed'] for k in CATEGORIES)
        if criterion == 'timer-only':
            verdict = 'FAIL' if attempts or completed else 'PASS'
            code = 'M7_SOURCE_ACCESS_DURING_TIMER' if verdict == 'FAIL' else None
        else:
            verdict = 'PASS' if attempts > 0 and completed > 0 else 'UNMEASURED'
            code = None if verdict == 'PASS' else 'M7_SOURCE_ACCESS_NOT_OBSERVED'
        return {'kind': KIND, 'criterion': criterion, 'verdict': verdict, 'code': code,
                'source': source, 'owner': owned, 'byService': deltas, 'totals': totals,
                'collectorCost': {'before': a['cost'], 'after': b['cost']}, 'limits': a['limits'],
                'scope': 'actual source-access census only; timer occurrence/output/clinical completion require their independent witness'}
    except p.Refused as error:
        return {'kind': KIND, 'criterion': criterion, 'verdict': error.verdict, 'code': str(error)}
    except Exception:
        return {'kind': KIND, 'criterion': criterion, 'verdict': 'UNMEASURED', 'code': 'M7_SOURCE_ACCESS_CAPTURE'}


def collect(a, directory, manifest, ids, *, services=None, seconds=20):
    """Optional integration seam; no adapter/probe mutation or new connection."""
    a.assert_owned(manifest); a.verify(directory, manifest)
    services = a.progress_services(directory) if services is None else services
    source = {'pair': manifest['pair'], 'imageId': manifest['imageId'],
              'instrument': manifest['instrument']['sha256'], 'hostIdentity': manifest['hostIdentity']}
    script = Path(__file__).with_name('source-access.cjs').read_text()
    def fetch(service, selected, queries, budget, timeout):
        prefix = 'const M7_SOURCE_IDS=' + json.dumps(selected) + ';const M7_SOURCE_QUERY_BUDGET=' + str(queries) + ';const M7_SOURCE_BYTE_BUDGET=' + str(budget) + ';\n'
        return a.compose(directory, 'exec', '-T', service, 'node', '-', input=(prefix + script).encode(), timeout=timeout)
    return capture(fetch, ids, services, source, manifest['owner'], seconds=seconds)
