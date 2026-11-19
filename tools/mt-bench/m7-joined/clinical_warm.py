"""Record the first independently observed evaluator warmth, using existing RPC reads."""
from pathlib import Path
import json
import os
import threading
import time

FILE = 'clinical-warm.private.json'
CONTRACT = 'clinical-deadline-from-warm-v1'
_LOCK = threading.Lock()


def now_ms():
    # Same Linux workstation CLOCK_MONOTONIC as the Node probe's process.hrtime.
    return time.monotonic_ns() / 1e6


def start(path, origin, label):
    # A fresh run directory owns this file. Record the invocation before effects.
    with Path(path).open('x') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump({'contract': CONTRACT, 'originMonoMs': origin, 'origin': label,
                   'rounds': 0, 'byTenant': {}}, stream)


def record(path, raw, services, ids, start_ms, end_ms, *, terminal=False):
    """Only complete, identity-checked rounds establish an owner observation.

    Zero lifetime acquisitions brackets the first possible qualified warm state.
    A later unready row with positive credit cannot prove it was never warm.
    """
    import preload_convergence
    path = Path(path)
    try:
        point = preload_convergence.inspect_pages(raw, services, ids, judge_health=False)
    except (ValueError, KeyError, RuntimeError, TypeError, AttributeError):
        return  # The ordinary reader retains its own refusal.
    with _LOCK:
        state = json.loads(path.read_text()) if path.exists() else {
            'contract': CONTRACT, 'originMonoMs': start_ms, 'origin': 'first evaluator inspection', 'rounds': 0, 'byTenant': {}}
        state['rounds'] += 1
        for tenant, owner in point['owners'].items():
            identity = [owner['service'], point['identities'][owner['service']]['runtimeId'], owner['generation']]
            count = owner['completedAcquisitions']
            row = state['byTenant'].setdefault(tenant, {
                'identity': identity, 'warmByMs': None, 'coldThroughMs': None, 'beforeTerminal': False})
            # The component generation can advance inside one evaluator process.
            # Its lifetime counters and the first qualified warm observation
            # belong to the tenant on that owner, across those forward steps.
            previous = row['identity']
            if previous[:2] != identity[:2] or identity[2] < previous[2] or count < row.get('acquisitions', 0):
                row['sourceChanged'] = True
            if not row.get('sourceChanged'):
                row['identity'] = identity
                if row['warmByMs'] is None:
                    if count == 0:
                        row['coldThroughMs'] = start_ms
                    elif owner['ready'] and owner['alert'] is None and owner['code'] is None and owner['lastCompletedAgeMs'] is not None:
                        row['warmByMs'] = end_ms
            row.update(acquisitions=count, terminal=terminal, lastObservationMs=end_ms,
                       beforeTerminal=row['beforeTerminal'] or not terminal)
        publish(path, state)


def publish(path, state):
    temp = path.with_suffix('.new')
    with temp.open('w') as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(state, output, separators=(',', ':'), allow_nan=False)
    temp.replace(path)


def end_drain(path, last_attempt_ms):
    # A SQL or RPC refusal on the final attempt cannot promote an earlier
    # cold sample to a terminal one. A deadline can leave warmth unmeasured.
    with _LOCK:
        if not path.is_file():
            return
        state = json.loads(path.read_text())
        for row in state['byTenant'].values():
            row['terminal'] = row['lastObservationMs'] >= last_attempt_ms
        publish(path, state)


def observing(fetch, path, services, ids, *, terminal=False):
    """Tee one complete set of parallel service replies; issue no additional RPC."""
    lock = threading.Lock()
    sequences, rounds = {}, {}
    def read(service, *args, **kwargs):
        start = now_ms()
        with lock:
            index = sequences.get(service, 0)
            sequences[service] = index + 1
        try:
            raw = fetch(service, *args, **kwargs)
        except BaseException:
            with lock:
                rounds.pop(index, None)
            raise
        with lock:
            for old in list(rounds):
                if old < index:
                    del rounds[old]
            batch = rounds.setdefault(index, {})
            batch[service] = (start, raw)
            if set(batch) == set(services):
                record(path, {s: r for s, (_, r) in batch.items()}, services, ids,
                       min(t for t, _ in batch.values()), now_ms(), terminal=terminal)
                del rounds[index]
        return raw
    return read


def coverage(path, ids):
    try:
        state = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        state = {}
    start = state.get('originMonoMs')
    rows, counts = {}, {'WARM': 0, 'NEVER_WARM': 0, 'UNMEASURED': 0}
    for tenant in ids:
        row = (state.get('byTenant') or {}).get(tenant, {})
        status = 'UNMEASURED'
        if state.get('contract') == CONTRACT and not row.get('sourceChanged'):
            if row.get('warmByMs') is not None:
                status = 'WARM'
            elif row.get('terminal') is True and row.get('beforeTerminal') and row.get('acquisitions') == 0:
                status = 'NEVER_WARM'
        counts[status] += 1
        rows[tenant] = {'status': status,
                        'warmAfterMs': row['coldThroughMs'] - start if row.get('coldThroughMs') is not None else None,
                        'warmByMs': row['warmByMs'] - start if status == 'WARM' else None}
    verdict = 'FAIL' if counts['NEVER_WARM'] else 'UNMEASURED' if counts['UNMEASURED'] or not rows else 'PASS'
    return {'verdict': verdict, 'codes': [] if verdict == 'PASS' else [
            'M7_TENANT_NEVER_WARM' if verdict == 'FAIL' else 'M7_TENANT_WARM_UNMEASURED'],
            'coverage': counts, 'byTenant': rows, 'rounds': state.get('rounds', 0),
            'originMonoMs': start, 'origin': state.get('origin'),
            'scope': 'elapsed from origin; warmAfterMs is the latest proven cold lower bound, warmByMs is the first qualified warm upper bound; a null lower bound is left-censored'}


def wait_for_probe(process, seconds, out, capture, *, wait=None):
    """Refresh existing evaluator inspection during a cold probe tail.

    The caller supplies its original remaining drain/work budget. The marker
    exists only while an accepted witness needs an independent warm read.
    """
    import subprocess
    until = now_ms() + seconds * 1000
    with (out/'clinical-tail-clock.json').open('x') as stream:
        json.dump({'untilMonoMs': until}, stream)
    wait = wait or process.wait
    next_read, count = 0, 0
    while True:
        remaining = (until - now_ms()) / 1000
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, seconds)
        try:
            return wait(min(.5, remaining))
        except subprocess.TimeoutExpired:
            pass
        if (out/'clinical-tail-needs-warm').is_file() and now_ms() >= next_read:
            start_ms = now_ms()
            try:
                cost = capture(count, (until - start_ms) / 1000)
            except Exception as error:
                cost = {'status': 'UNMEASURED', 'errorType': type(error).__name__}
            with (out/'clinical-tail-inspections.jsonl').open('a') as stream:
                stream.write(json.dumps({'startMonoMs': start_ms, 'endMonoMs': now_ms(), **cost}) + '\n')
            count += 1
            next_read = now_ms() + 1000


def wait_compose(adapter, directory, manifest, process, seconds):
    import evaluator_progress
    ids = sorted(row['id'] for row in adapter.document(directory/'tenants.private.json'))
    services = adapter.progress_services(directory)
    policy = evaluator_progress.capture_policy(manifest.get('cadence', {}).get('evaluatorProgressBudget'))
    def capture(index, left):
        cutoff = now_ms() + 1000 * left
        def fetch(service, *args):
            remaining = (cutoff - now_ms()) / 1000
            evaluator_progress.need(remaining > 0, 'M7_CLINICAL_TAIL_EXPIRED')
            return adapter.progress_fetch(directory, service, *args, timeout=min(20, remaining))
        read = observing(fetch, directory/FILE, services, ids)
        try:
            result = evaluator_progress.round_view(services, ids, read, warming=True,
                                                   allow_unavailable=True, policy=policy)
            return {key: result[key] for key in ('queries','bytes','wallSeconds')}
        except evaluator_progress.Refused as error:
            return {**getattr(error, 'collection', {}), 'status': error.verdict, 'code': str(error)}
    return wait_for_probe(process, seconds, directory/'load', capture)
