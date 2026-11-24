"""Wait for the evaluators to catch up before viewer priming and load (lane nominal-ladder, 2026-11-23).

A restore of a fixture anchored hours earlier makes every tenant due at once; the nominal design requires roles ready
and caught up before load. Campaign lanel-c2-02 primed 13,000 viewers during a 32-evaluator catch-up wave (app nodes at
76-88 % CPU) and stalled (M7_VIEWER_SETUP_STALLED). This gate reads the evaluators' durable `-completed` work rows
(read-only SQL, one statement per sample) and returns once, for a sustained window:

  overdue   active tenants whose next due cycle (work_due_at) is more than `overdueGraceSeconds` in the past
  pending   active tenants carrying a writer pending mark (work_pending_at)
  over120s  the summed durable lag counter of completions later than 120 s (lag_over_120s)

overdue and pending stay at or below `toleranceTenants`, and over120s does not grow. The time from the gate's start to
the caught-up sample is reported as warm-up, scored apart. Settings (workload.catchupGate):
{windowSeconds 300, pollSeconds 30, deadlineSeconds 3600, overdueGraceSeconds 60, toleranceTenants 0}.
"""
import json
import re
import time

DEFAULTS = {'windowSeconds': 300, 'pollSeconds': 30, 'deadlineSeconds': 3600, 'overdueGraceSeconds': 60,
            'toleranceTenants': 0}
NAME = re.compile('[a-z][a-z0-9_]{0,62}')


class NotCaughtUp(RuntimeError):
    pass


def settings(value):
    if value is None:
        return None
    if value is True:
        value = {}
    if not (isinstance(value, dict) and set(value) <= set(DEFAULTS)
            and all(type(v) is int and v >= 0 for v in value.values())):
        raise ValueError('K8S_CATCHUP_GATE_SETTINGS')
    s = dict(DEFAULTS, **value)
    if not (s['pollSeconds'] >= 1 and s['windowSeconds'] >= s['pollSeconds'] and s['deadlineSeconds'] > s['windowSeconds']):
        raise ValueError('K8S_CATCHUP_GATE_SETTINGS')
    return s


def query(completion, grace_seconds):
    """One snapshot of the active tenants' evaluator work rows."""
    writer = completion.get('writerDriven') or {}
    consumer = completion.get('consumer')
    names = (completion.get('checkpoint'), writer.get('lifecycle'))
    if not (all(isinstance(n, str) and NAME.fullmatch(n) for n in names) and isinstance(consumer, str)
            and re.fullmatch('evaluator-[A-Za-z0-9_-]{1,100}-completed', consumer) and type(grace_seconds) is int):
        raise ValueError('K8S_CATCHUP_GATE_BINDING')
    checkpoint, lifecycle = names
    return f"""WITH now_ms AS (SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint AS t),
rows AS (SELECT o.work_due_at, o.work_pending_at, o.lag_over_120s, o.lag_count
   FROM "{lifecycle}".tenant_lifecycle_windows l
   JOIN "{checkpoint}".tenant_consumer_checkpoint o ON o.tenant_id = l.tenant_id AND o.consumer = '{consumer}'
  WHERE l.phase = 'active' AND o.work_enabled)
SELECT json_build_object('readAtMs', (SELECT t FROM now_ms)::text, 'tenants', count(*),
  'overdue', count(*) FILTER (WHERE work_due_at < (SELECT t FROM now_ms) - {grace_seconds * 1000}),
  'pending', count(*) FILTER (WHERE work_pending_at IS NOT NULL),
  'over120s', coalesce(sum(lag_over_120s), 0)::text, 'lagCount', coalesce(sum(lag_count), 0)::text)::text FROM rows;"""


def decode(raw):
    doc = json.loads(raw)
    out = {k: int(doc[k]) for k in ('readAtMs', 'tenants', 'overdue', 'pending', 'over120s', 'lagCount')}
    if out['tenants'] < 1:
        raise ValueError('K8S_CATCHUP_GATE_NO_TENANTS')
    return out


def caught_up(samples, s):
    """Index of the first sample that closes a window of `windowSeconds` in which every sample is at baseline and
    over120s did not grow; None if no such window yet."""
    start = None
    for i, x in enumerate(samples):
        quiet = x['overdue'] <= s['toleranceTenants'] and x['pending'] <= s['toleranceTenants']
        if not quiet or (start is not None and x['over120s'] != samples[start]['over120s']):
            start = i if quiet else None
            continue
        if start is None:
            start = i
        if x['readAtMs'] - samples[start]['readAtMs'] >= s['windowSeconds'] * 1000:
            return i
    return None


def wait(fetch, s, clock=time, log=None):
    """Sample until caught up (returns the record) or the deadline (raises NotCaughtUp with the record attached)."""
    began = clock.time()
    samples = []
    while True:
        samples.append(decode(fetch()))
        if log:
            log(samples[-1])
        done = caught_up(samples, s)
        if done is not None:
            return {'verdict': 'CAUGHT_UP', 'settings': s, 'startedAt': began, 'caughtUpAtMs': samples[done]['readAtMs'],
                    'warmupSeconds': round((samples[done]['readAtMs'] - samples[0]['readAtMs']) / 1000, 1),
                    'gateSeconds': round(clock.time() - began, 1), 'samples': samples}
        if clock.time() - began >= s['deadlineSeconds']:
            error = NotCaughtUp('K8S_CATCHUP_NOT_REACHED')
            error.record = {'verdict': 'UNMEASURED', 'code': 'K8S_CATCHUP_NOT_REACHED', 'settings': s, 'startedAt': began,
                            'samples': samples}
            raise error
        clock.sleep(s['pollSeconds'])
