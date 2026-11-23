#!/usr/bin/env python3
"""Plannable-scale points: one K input, slice ownership, connections and warm-up read back.

Lane mt-plannable-scale-20261121, workstream E5. Decisions: pg-connection-budget,
pg-connection-pooler-allowed, evaluator-k-planned-restart, stateful-evaluator-resident-window,
requests-typical-scheduler-decides.

    point     one K (1..32) sets evaluator K and realtime K (the same, up to realtime's bound of 8),
              2 api replicas, lab metrics, and optionally
              pools and the evaluator memory constants. The deploy binding renders from that input
              max_connections (connection budget), the evaluator memory request
              (base + per-resident x ceil(tenants / K)) and NS_EVALUATOR_RESIDENT_MAX (owned count).
    profile   a seed or traffic profile for N tenants on a named history fixture. The fixture
              mode is a parameter: E1's synthetic-history-looping-2d-v1 may land after this file.
              The fixture catalog key is K-free for writer-driven, so one 10k seed restores into
              every K (fixture_catalog.K_FREE_TRANSPORTS).
    ownership every roster tenant is owned exactly once by a live ordinal of each sliced role
              (sha256-modulo-v1, core lib/pool-membership/slice.js); a K that leaves a tenant
              unowned refuses.
    connections  offline, from the retained TSDB snapshot (postgres_exporter ns_activity_backends,
              already scraped; nothing new polls the database): client backends in use, peak and by
              application_name, against the rendered budget in inventory.json `connectionBudget`.
    warmup    offline, from the same snapshot: evaluator Pod start (process_start_time_seconds) to
              all owned tenants evaluated (a resident-tenants gauge reaching the owned count), and to
              the first alarm (tenant_notification_requests.created_at, read once after the run).

Labels: ownership and the formulas are read-derived from the render; connections and warm-up
are measured when a case supplies the snapshot, else UNMEASURED or NO-INSTRUMENT, never green.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import os
import math
from pathlib import Path
import re
import sys

# Evaluator K follows deploy evaluator-workers.js MAX_WORKERS (32 since deploy 9160d81); realtime keeps 1..8.
K_MAX = 32
REALTIME_K_MAX = 8
K_MAX_BY_ROLE = {'evaluator': K_MAX, 'realtime': REALTIME_K_MAX}
SLICED = ('evaluator', 'realtime')
UUID = re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
HISTORY_MODE = re.compile('synthetic-history-[a-z0-9-]{1,48}-v[0-9]{1,3}')
# E1's fixture key (BRIEF-mt-plannable-scale-20261121, row E1); a parameter, not a dependency.
LOOPING_2D = 'synthetic-history-looping-2d-v1'
# The AID client model's history (m7-joined/looping_history_v2.py): its own key; v1 stays the default seed.
LOOPING_2D_V2 = 'synthetic-history-looping-2d-v2'
LOOPING_MODES = (LOOPING_2D, LOOPING_2D_V2)
# The live writes on a looping fixture: looping-v2 (AID client model D1-D5) unless a profile asks for v1.
LOOPING_DRIVER_SHAPE = 'looping-v2'
# Evaluator memory: the binding's default model applies (deploy d8d325a: 1745 + 2.96 x residentMax MiB and the
# V8 heap ceiling from it). point() writes evaluatorMemory only when a refit is asked for.
# A gauge core does not export at 80972e7ae: residents.size per slice (evaluator-runtime.js:172).
RESIDENT_GAUGE = 'nightscout_evaluator_resident_tenants'


class Refused(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Refused('K8S_PLAN_' + code)


def deploy_binding(source=None):
    """The deploy tree the offline render checks read: NS_DEPLOY_BINDING, always explicit.

    There is no default path: a lane worktree left behind renders an old binding and the check then
    measures the wrong commit. For a ref rather than a checkout, archive it into scratch first
    (git -C <deploy> archive <ref> | tar -x -C <scratch>) and name the scratch directory."""
    source = os.environ if source is None else source
    raw = source.get('NS_DEPLOY_BINDING')
    need(isinstance(raw, str) and raw.startswith('/'), 'DEPLOY_BINDING_REQUIRED')
    root = Path(raw)
    need((root/'bindings/kubernetes/lib/ns/connection-budget.libsonnet').is_file(), 'DEPLOY_BINDING_INVALID')
    return root


def bucket(tenant, members):
    """core lib/pool-membership/slice.js bucket(): sha256(id) first 8 bytes, unsigned, mod members."""
    need(isinstance(tenant, str) and UUID.fullmatch(tenant), 'TENANT_ID')
    need(type(members) is int and 1 <= members <= 1024, 'MEMBERS')
    return int.from_bytes(hashlib.sha256(tenant.encode()).digest()[:8], 'big') % members


def point(k, *, realtime_k=None, api_replicas=2, pools=None, evaluator_memory=None, lab_metrics=True, role_env=None):
    """Binding input for one evaluator K; realtime takes the same K up to its own bound of 8 unless given."""
    need(type(k) is int and 1 <= k <= K_MAX, 'K')
    realtime_k = min(k, REALTIME_K_MAX) if realtime_k is None else realtime_k
    need(type(realtime_k) is int and 1 <= realtime_k <= REALTIME_K_MAX, 'REALTIME_K')
    need(type(api_replicas) is int and 1 <= api_replicas <= 16, 'API_REPLICAS')
    value = {'inputTransport': 'writer-driven', 'apiReplicas': api_replicas,
             'slices': {'evaluator': k, 'realtime': realtime_k}, 'labMetrics': {'enabled': bool(lab_metrics)}}
    if pools:
        need(set(pools) <= {'api', 'realtime', 'evaluator', 'operation', 'read'}, 'POOLS')
        value['pools'] = dict(pools)
    if evaluator_memory:
        need(set(evaluator_memory) <= {'baseMiB', 'perResidentMiB', 'heapHeadroom'}
             and evaluator_memory.get('baseMiB', 1) > 0 and evaluator_memory.get('perResidentMiB', 0) >= 0, 'EVALUATOR_MEMORY')
        value['evaluatorMemory'] = dict(evaluator_memory)
    if role_env:
        value['roleEnv'] = role_env
    return value


def profile(base, *, tenants, history_mode=LOOPING_2D, anchor_ms=None, name=None, work_seconds=None,
            driver_shape=LOOPING_DRIVER_SHAPE):
    """A profile for TENANTS on HISTORY_MODE, from BASE (an existing workload profile document)."""
    need(type(tenants) is int and 1 <= tenants <= 20000, 'TENANTS')
    need(isinstance(history_mode, str) and HISTORY_MODE.fullmatch(history_mode), 'HISTORY_MODE')
    value = copy.deepcopy(base)
    value['population'].update(provisionedTenants=tenants, ordinaryRosterTenants=tenants)
    history = dict(value.get('history') or {})
    history['mode'] = history_mode
    if anchor_ms is not None:
        need(type(anchor_ms) is int and anchor_ms > 0, 'ANCHOR')
        history['anchorUnixMs'] = anchor_ms
    value['history'] = history
    # E3: on a looping fixture the live writes take a looping shape (m7-joined/looping_driver.py);
    # looping-v2 (the AID client model) by default, looping-v1 on request.
    need(driver_shape in ('looping-v1', 'looping-v2'), 'DRIVER_SHAPE')
    if history_mode in LOOPING_MODES and value.get('workload', {}).get('workloadMix') == 'realistic-v1':
        value['workload']['driverShape'] = driver_shape
    value['name'] = name or 'n%d-%s' % (tenants, history_mode.removeprefix('synthetic-history-'))
    if work_seconds is not None:
        value['phases']['workSeconds'] = work_seconds
    value['basis'] = 'Plannable-scale profile (E5): %d tenants on %s.' % (tenants, history_mode)
    return value


def known_history(mode):
    """Whether the harness's history generator knows MODE yet (E1 adds the looping mode)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'m7-joined'))
    import populated_history
    return mode in getattr(populated_history, 'SHAPES', {}) or mode in getattr(populated_history, 'LOOPING_MODES', ())


def rendered_slices(inventory, role):
    """K and replicas of a sliced role from the render inventory; they must agree."""
    k = inventory['slices'][role]
    replicas = inventory['workloads'][role]['replicas']
    need(type(k) is int and 1 <= k <= K_MAX_BY_ROLE[role], 'K')
    return k, replicas


def ownership(roster, inventory, live=None):
    """Per sliced role: tenants per ordinal. Every tenant owned exactly once by a live ordinal, or refuse.

    LIVE maps a role to the ordinals actually serving (Ready Pods); default: every rendered replica."""
    roster = list(roster)
    need(roster and len(set(roster)) == len(roster), 'ROSTER')
    result = {}
    for role in SLICED:
        k, replicas = rendered_slices(inventory, role)
        ordinals = set(range(replicas)) if live is None or role not in live else set(live[role])
        owners = Counter(bucket(t, k) for t in roster)
        unowned = sum(n for ordinal, n in owners.items() if ordinal not in ordinals)
        need(replicas == k, 'REPLICAS_NOT_K_' + role.upper())
        need(unowned == 0, 'TENANT_UNOWNED_' + role.upper())
        need(sum(owners.values()) == len(roster), 'OWNED_TWICE_' + role.upper())
        result[role] = {'k': k, 'perOrdinal': [owners.get(i, 0) for i in range(k)],
                        'maxOwned': max(owners.values()), 'tenants': len(roster)}
    budget = inventory.get('connectionBudget')
    if budget:
        result['residentMax'] = budget['evaluator']['residentMax']
        # Read-derived: the rendered limit is ceil(N/K); hashing can put a few more on one slice.
        result['residentShortfall'] = max(0, result['evaluator']['maxOwned'] - budget['evaluator']['residentMax'])
    return result


CONNECTION_QUERIES = {
    'clientBackendsPeak': 'max_over_time(sum(ns_activity_backends{{backend_type="client backend"}})[{w}s:{step}s])',
    'clientBackendsEnd': 'sum(ns_activity_backends{{backend_type="client backend"}})',
    'byApplicationPeak': 'max_over_time(sum by (application_name) (ns_activity_backends{{backend_type="client backend"}})[{w}s:{step}s])',
    'maxConnectionsSetting': 'max(pg_settings_max_connections)',
}


def connections(figures, budget):
    """Measured client backends against the rendered budget (pure).

    Gate: peak in use <= pools + transient (the planned part). OVER_PLAN: above the plan but below
    max_connections - superuser; FAIL: at or above it (new connections would be refused)."""
    peak = (figures.get('clientBackendsPeak') or [{}])[0].get('value')
    if peak is None:
        return {'verdict': 'UNMEASURED', 'reason': 'no ns_activity_backends series (labMetrics off?)'}
    planned = budget['poolConnections'] + budget['transient']
    ceiling = budget['maxConnections'] - budget['superuserReserved']
    verdict = 'PASS' if peak <= planned else ('OVER_PLAN' if peak < ceiling else 'FAIL')
    setting = (figures.get('maxConnectionsSetting') or [{}])[0].get('value')
    by_app = {row['labels'].get('application_name', 'none'): row['value'] for row in figures.get('byApplicationPeak') or []}
    return {'verdict': verdict, 'peakClientBackends': peak, 'planned': planned, 'ceiling': ceiling,
            'budget': budget['budget'], 'maxConnections': budget['maxConnections'],
            'maxConnectionsLive': setting, 'settingMatches': None if setting is None else setting == budget['maxConnections'],
            'utilization': round(peak / planned, 3), 'peakByApplication': by_app,
            'label': 'measured (postgres_exporter scrape) against read-derived budget'}


WARMUP_QUERIES = {
    'podStart': 'process_start_time_seconds{{role="evaluator"}}',
    'residents': 'max by (pod, slice) (' + RESIDENT_GAUGE + ')',
}


def warmup(series, owned, first_alarm_ms=None, *, step_s):
    """Pod start -> all owned evaluated -> first alarm, per evaluator Pod (pure).

    SERIES: {'podStart': {pod: seconds}, 'residents': {pod: [(t_seconds, value), ...]}}; OWNED: {pod: n}."""
    if not series.get('podStart'):
        return {'verdict': 'UNMEASURED', 'reason': 'no evaluator process_start_time_seconds'}
    if not series.get('residents'):
        return {'verdict': 'NO-INSTRUMENT', 'reason': 'core exports no ' + RESIDENT_GAUGE + ' (residents.size); '
                'all-owned-evaluated cannot be timed without polling', 'podStart': series['podStart']}
    pods = {}
    for pod, start in sorted(series['podStart'].items()):
        samples = sorted(series['residents'].get(pod, []))
        need(pod in owned, 'WARMUP_OWNED_UNKNOWN')
        done = next((t for t, v in samples if v >= owned[pod]), None)
        row = {'podStart': start, 'owned': owned[pod], 'residentsMax': max((v for _, v in samples), default=0),
               'allEvaluatedSeconds': None if done is None else round(done - start, 3), 'resolutionSeconds': step_s}
        if first_alarm_ms is not None:
            row['firstAlarmSeconds'] = round(first_alarm_ms / 1000 - start, 3) if first_alarm_ms / 1000 >= start else None
        pods[pod] = row
    complete = all(r['allEvaluatedSeconds'] is not None for r in pods.values())
    return {'verdict': 'OBSERVED' if complete else 'INCOMPLETE', 'pods': pods,
            'maxAllEvaluatedSeconds': max((r['allEvaluatedSeconds'] or 0) for r in pods.values()) if complete else None,
            'label': 'measured (Prometheus scrape resolution)'}


FIRST_ALARM_SQL = """SELECT coalesce(min(r.created_at), -1)::text FROM (
  SELECT created_at FROM {schema}.tenant_notification_requests WHERE created_at >= {since}) r;"""


def first_alarm_query(schema, since_ms):
    need(re.fullmatch('[a-z][a-z0-9_]{0,62}', schema or ''), 'SCHEMA')
    need(type(since_ms) is int and since_ms >= 0, 'SINCE')
    return 'SELECT ' + FIRST_ALARM_SQL.split('SELECT ', 1)[1].format(schema=schema, since=since_ms)


def _range(server, expr, start, end, step):
    """{pod: [(t, v)]} from server.query_range (LocalPrometheus-like)."""
    out = {}
    for row in server.query_range(expr, start, end, step):
        out.setdefault(row['labels'].get('pod', ''), []).extend((float(t), float(v)) for t, v in row['values'])
    return out


def case_readback(case_dir, *, server_factory=None, owned=None, first_alarm_ms=None, step_s=15):
    """Connections and warm-up for one launched case, from its retained snapshot and inventory."""
    import case_observer as co
    case_dir = Path(case_dir)
    inventory = json.loads((case_dir/'inventory.json').read_text())
    budget = inventory.get('connectionBudget')
    need(budget, 'INVENTORY_HAS_NO_BUDGET')
    case = type('Case', (), {'d': case_dir})()
    points = co.point_ids(case_dir)
    def measure(point):
        return readback_point(case, budget, point, server_factory, owned, first_alarm_ms, step_s)
    if points:
        return {'points': [dict(pointId=point, **measure(point)) for point in points],
                'warmupBasis': 'evaluator process start through each point on the shared restore'}
    return measure(None)


def readback_point(case, budget, point, server_factory, owned, first_alarm_ms, step_s):
    import case_observer as co
    load = co.load_directory(case, point)
    receipt = co.read(load/'metrics-snapshot.json')
    _, start, end = co.window(case, point)
    if start is None and point is None:
        start, end = co.load_window(case)
    reason = None
    if not receipt or receipt.get('verdict') != 'OBSERVED':
        reason = 'no retained metrics snapshot'
    elif point is not None and start is None:
        reason = 'no retained load window'
    if reason:
        return {name: {'verdict': 'UNMEASURED', 'reason': reason} for name in ('connections', 'warmup')}
    need(start is not None and end > start, 'WINDOW')
    server = (server_factory or co.LocalPrometheus)(load/receipt['file'])
    try:
        w = max(1, int((end - start) / 1000))
        figures = {n: server.query(e.format(w=w, step=step_s), end / 1000) for n, e in CONNECTION_QUERIES.items()}
        starts = {r['labels'].get('pod', ''): r['value'] for r in server.query(WARMUP_QUERIES['podStart'].format(), end / 1000)}
        first = min(starts.values()) if starts else start / 1000
        residents = _range(server, WARMUP_QUERIES['residents'], first, end / 1000, step_s) if hasattr(server, 'query_range') else {}
    finally:
        server.close()
    return {'connections': connections(figures, budget),
            'warmup': warmup({'podStart': starts, 'residents': residents}, owned or {}, first_alarm_ms, step_s=step_s)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='command', required=True)
    p = sub.add_parser('point', help='binding input for one K')
    p.add_argument('k', type=int)
    p.add_argument('--realtime-k', type=int, help='realtime K (default min(K, 8))')
    p.add_argument('--api-replicas', type=int, default=2)
    p.add_argument('--base-mib', type=float)
    p.add_argument('--per-resident-mib', type=float)
    p.add_argument('--pools', type=json.loads, help='JSON, e.g. {"operation": 4}')
    p = sub.add_parser('profile', help='profile for N tenants on a history fixture')
    p.add_argument('base', type=Path)
    p.add_argument('--tenants', type=int, required=True)
    p.add_argument('--history-mode', default=LOOPING_2D)
    p.add_argument('--anchor-ms', type=int)
    p.add_argument('--name')
    p.add_argument('--work-seconds', type=int)
    p.add_argument('--driver-shape', default=LOOPING_DRIVER_SHAPE, choices=('looping-v1', 'looping-v2'))
    p = sub.add_parser('ownership', help='slice ownership of a roster under a rendered inventory')
    p.add_argument('inventory', type=Path)
    p.add_argument('roster', type=Path, help='JSON list of tenant ids, or {"tenants": [...]} ')
    p = sub.add_parser('readback', help='connections and warm-up per workload point for a launched case (offline)')
    p.add_argument('case', type=Path)
    p.add_argument('--first-alarm-ms', type=int)
    a = ap.parse_args(argv)
    if a.command == 'point':
        memory = {k: v for k, v in (('baseMiB', a.base_mib), ('perResidentMiB', a.per_resident_mib)) if v is not None}
        out = point(a.k, realtime_k=a.realtime_k, api_replicas=a.api_replicas, pools=a.pools, evaluator_memory=memory)
    elif a.command == 'profile':
        out = profile(json.loads(a.base.read_text()), tenants=a.tenants, history_mode=a.history_mode,
                      anchor_ms=a.anchor_ms, name=a.name, work_seconds=a.work_seconds, driver_shape=a.driver_shape)
        if not known_history(a.history_mode):
            print('warning: history mode %s is not in populated_history.SHAPES yet (E1 pending)' % a.history_mode, file=sys.stderr)
    elif a.command == 'ownership':
        roster = json.loads(a.roster.read_text())
        roster = roster['tenants'] if isinstance(roster, dict) else roster
        out = ownership(roster, json.loads(a.inventory.read_text()))
    else:
        inv = json.loads((a.case/'inventory.json').read_text())
        roster_file = a.case/'runtime/fixture/data-roster.private.json'
        owned = None
        if roster_file.is_file():
            roster = json.loads(roster_file.read_text())
            ids = [t if isinstance(t, str) else t.get('tenant') or t.get('id') for t in (roster.get('tenants') if isinstance(roster, dict) else roster)]
            own = ownership(ids, inv)['evaluator']['perOrdinal']
            owned = {'evaluator-%d' % i: n for i, n in enumerate(own)}
        out = case_readback(a.case, owned=owned, first_alarm_ms=a.first_alarm_ms)
    json.dump(out, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
