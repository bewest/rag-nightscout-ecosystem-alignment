"""Writer-driven evaluator progress bookends from the durable `-completed` rows (read-only SQL).

A writer-driven evaluator loads tenants on demand, so its private inspection RPC refuses every
tenant it has not loaded yet (core lib/server/serve/evaluator-inspection.js selector check). Before
the first write of a restored fixture that is every tenant, so the RPC bookend cannot be taken.
The durable row is level-triggered and independent of evaluator memory: each bookend reads, in one
snapshot, every active tenant's generation and its `-completed` row (work_completed[1],
work_observed[1], output_restore_generation, pending mark), bound to the same contract digest the
writer-driven observer uses (m7-joined/accepted_inputs.writer_queries). A tenant the evaluator never
loaded reads the seed's completed version, so seed completions are never counted as new work.

The RPC midpoint remains a signal; the strict assessment here uses only the two SQL bookends.
"""
import hashlib
import json
import re
import time

import kube_adapter as k

SOURCE = 'sql-completed-v1'
FIELDS = ('generation', 'completed', 'observed', 'restoreGeneration', 'stateOK', 'pending')
# The writer's pending mark (ms) follows the six fields, with the database read time at the top level, so
# the end read gives coverage_verdict.py each owed tenant's oldest-input bound (lane R2).
PENDING_AT = len(FIELDS)
NAME = re.compile('[a-z][a-z0-9_]{0,62}')


def writer_driven(c):
    completion = c.get('completion') or {}
    return completion.get('kind') == 'evaluator-work-v2' and isinstance(completion.get('writerDriven'), dict)


def query(config):
    """One statement, one snapshot; a JSON document with the database identity and every active tenant."""
    import accepted_inputs as ai
    writer = config.get('writerDriven')
    k.need(isinstance(writer, dict) and config.get('kind') == 'evaluator-work-v2' and not config.get('native'),
           'PROGRESS_SQL_BINDING')
    consumer = config.get('consumer')
    k.need(isinstance(consumer, str) and re.fullmatch('evaluator-[A-Za-z0-9_-]{1,100}-completed', consumer),
           'PROGRESS_SQL_BINDING')
    names = {'checkpoint': config.get('checkpoint'), 'lifecycle': writer.get('lifecycle')}
    k.need(all(isinstance(v, str) and NAME.fullmatch(v) for v in names.values()), 'PROGRESS_SQL_BINDING')
    # Same digest as writer_queries: core's native lifecycle contract (typed-checkpoint.js).
    parts = [config['kind'], names['checkpoint'], consumer.removesuffix('-completed'), *ai.LIFECYCLE_CODEC]
    digest = hashlib.sha256(json.dumps(parts, separators=(',', ':')).encode()).hexdigest()
    return f"""SELECT json_build_object('identity', {ai.DB_IDENTITY},
  'readAtMs', floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint::text, 'tenants',
  (SELECT coalesce(json_object_agg(l.tenant_id, json_build_array(
      l.generation::text, o.work_completed[1]::text, o.work_observed[1]::text, o.output_restore_generation::text,
      coalesce(o.work_version = 2 AND o.contract_digest = '{digest}' AND o.work_enabled
               AND o.projection->0->>'kind' = 'evaluator-work-v2', false),
      o.work_pending_at IS NOT NULL, o.work_pending_at::text)), '{{}}'::json)
     FROM "{names['lifecycle']}".tenant_lifecycle_windows l
     LEFT JOIN "{names['checkpoint']}".tenant_consumer_checkpoint o
       ON o.tenant_id = l.tenant_id AND o.consumer = '{consumer}'
    WHERE l.phase = 'active'))::text;"""


def _int(value):
    return int(value) if isinstance(value, str) and re.fullmatch('-?[0-9]{1,19}', value) else None


def decode(raw, ids):
    """A bookend document: identity and the roster tenants' durable state. Shape problems refuse."""
    doc = json.loads(raw)
    k.need(isinstance(doc, dict) and isinstance(doc.get('tenants'), dict) and doc.get('identity') is not None,
           'PROGRESS_SQL_SHAPE', 'UNMEASURED')
    tenants = {}
    for tenant in ids:
        row = doc['tenants'].get(tenant)
        k.need(isinstance(row, list) and len(row) in (len(FIELDS), len(FIELDS) + 1), 'PROGRESS_SQL_COVERAGE', 'FAIL')
        generation, completed, observed, restore, state, pending = row[:len(FIELDS)]
        tenants[tenant] = {'generation': _int(generation), 'completed': _int(completed), 'observed': _int(observed),
                           'restoreGeneration': _int(restore), 'stateOK': state is True, 'pending': pending is True,
                           'pendingAt': _int(row[PENDING_AT]) if len(row) > PENDING_AT else None}
    return {'source': SOURCE, 'identity': doc['identity'], 'tenants': tenants, 'readAtMs': _int(doc.get('readAtMs')),
            'activeTenants': len(doc['tenants']), 'foreignActiveTenants': len(set(doc['tenants']) - set(ids))}


def capture(fetch, ids, raw_output=None, clock=time):
    """Run the bookend query through FETCH(query) -> bytes/str, retain the raw response first, then decode."""
    started = clock.monotonic()
    raw = fetch()
    raw = raw.encode() if isinstance(raw, str) else raw
    if raw_output is not None:
        raw_output.write_bytes(raw)
    value = decode(raw.decode(), ids)
    value.update(queries=1, bytes=len(raw), wallSeconds=round(clock.monotonic() - started, 3), observedAt=clock.time())
    return value


def assess(before, after, ids, midpoint=None):
    """Strict checks over the two durable bookends; the RPC midpoint, if present, is reported as a signal."""
    k.need(before.get('source') == SOURCE and after.get('source') == SOURCE, 'EVALUATOR_PROGRESS_BOOKENDS', 'UNMEASURED')
    k.need(before['identity'] == after['identity'], 'PROGRESS_SQL_DATABASE_CHANGED', 'FAIL')
    advanced = caught_up = pending = seeded = 0
    for tenant in ids:
        a, b = before['tenants'][tenant], after['tenants'][tenant]
        k.need(a['stateOK'] and b['stateOK'], 'PROGRESS_SQL_STATE', 'FAIL')
        k.need(a['generation'] is not None and a['generation'] == b['generation'], 'EVALUATOR_PROGRESS_RESET', 'FAIL')
        k.need(a['completed'] is None or (b['completed'] is not None and b['completed'] >= a['completed']),
               'EVALUATOR_PROGRESS_RESET', 'FAIL')
        moved = b['completed'] is not None and (a['completed'] is None or b['completed'] > a['completed'])
        if moved:
            # A completion made during the run must carry this generation; a seed row left untouched
            # by an evaluator that never loaded the tenant may carry the seed's restore generation.
            k.need(b['restoreGeneration'] == b['generation'], 'PROGRESS_SQL_FENCE', 'FAIL')
        seeded += a['completed'] is not None
        advanced += moved
        caught_up += b['completed'] is not None and b['observed'] is not None and b['completed'] >= b['observed'] and not b['pending']
        pending += b['pending']
    value = {'version': 1, 'source': SOURCE, 'phase': 'load', 'verdict': 'PASS', 'demandDriven': True,
             'tenants': len(ids), 'tenantsWithSeedCompletion': seeded, 'tenantsAdvanced': advanced,
             'tenantsCaughtUpAfter': caught_up, 'tenantsPendingAfter': pending,
             'queries': before['queries'] + after['queries'], 'responseBytes': before['bytes'] + after['bytes'],
             'collectorWallSeconds': before['wallSeconds'] + after['wallSeconds'],
             'scope': 'durable -completed rows at the load bookends (level-triggered); tenants advanced, not acquisition '
                      'counts; failed completions are not in the row and stay unmeasured here'}
    if midpoint is not None:
        value['midpointSignal'] = {'source': 'inspection-rpc', 'instances': len(midpoint.get('instances') or {}),
                                   'owners': len(midpoint.get('owners') or {})}
    return value
