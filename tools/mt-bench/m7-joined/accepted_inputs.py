"""Read-only live collector: accepted, stored and output events for every input.

Each HTTP ACK identifies one run-marked storage row. A native journal event
binds that row to an intake floor. A fenced durable completion at or beyond
that floor covers the input, including when the worker coalesces inputs.
It emits the raw events of `assessor.py`; the assessor alone judges them.
"""
import contextvars
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from collections import Counter

KIND = 'accepted-input-events-v2'
HERE = Path(__file__).resolve().parent


class EvidenceError(ValueError):
    def __init__(self, code, verdict='UNMEASURED'):
        super().__init__(code)
        self.verdict = verdict


def require(condition, code, verdict='UNMEASURED'):
    if not condition:
        raise EvidenceError(code, verdict)


def query(config, run):
    native = config.get('native') or {}
    require(config.get('kind') == 'evaluator-work-v2' and native.get('kind') == 'compact-native-v1',
            'M7_INPUT_NATIVE_SOURCE_REQUIRED')
    consumer = native.get('inputConsumer', '')
    # The product's work-contract digest selects rows; older captures predate receipts.
    parts = ['evaluator-work-v2', config.get('checkpoint'), consumer,
             'canonical-maintenance-active-plus2-v1', 'positive-int8-complete-pair-max-4611686018427387902-v1']
    digest = (native.get('receipt') or {}).get('contractDigest') or hashlib.sha256(
        json.dumps(parts, separators=(',', ':')).encode()).hexdigest()
    sql = (HERE/'accepted-inputs.sql').read_text()
    for name, value, pattern in (
            ('run', run, r'[a-z0-9-]{1,100}'), ('generation', native.get('generation'), r'[a-f0-9]{32}'),
            ('digest', digest, r'[a-f0-9]{64}'), ('consumer', consumer, r'evaluator-[a-zA-Z0-9_-]{1,100}'),
            ('slot', native.get('slot'), r'[a-z][a-z0-9_]{0,62}'),
            ('checkpoint', config.get('checkpoint'), r'[a-z][a-z0-9_]{0,62}'),
            ('lifecycle', native.get('lifecycle'), r'[a-z][a-z0-9_]{0,62}')):
        require(isinstance(value, str) and re.fullmatch(pattern, value), 'M7_INPUT_SOURCE_BINDING')
        sql = sql.replace('@' + name + '@', value)
    return sql


def read_acks(folder, run, result):
    """Confirmed HTTP responses from each writer, including partial probe evidence.

    Returns the number of lines or witnesses that could not be read."""
    bad = 0
    def add(tenant, domain, marker, key, duration):
        if not (isinstance(tenant, str) and domain in ('entries', 'devicestatus', 'treatments')
                and isinstance(key, str) and key and type(duration) in (float, int) and duration >= 0):
            return 1
        result[(tenant, domain, marker, key)] = duration
        return 0

    for path in sorted(folder.glob('k6-shard-*.log')) or [folder/'k6.log']:
        if not path.is_file():
            continue
        with path.open(errors='replace') as stream:
            for line in stream:
                if 'm7-input-accepted' not in line:
                    continue
                try:
                    match = re.search(r'\bmsg=("(?:[^"\\]|\\.)*")', line)
                    row = json.loads(json.loads(match[1]) if match else json.loads(line)['msg'])
                    bad += add(row['tenant'], row['domain'], run, str(row['key']), row['requestToAcceptanceMs']) \
                        if row.get('run') == run else 0
                except (ValueError, KeyError, TypeError):
                    bad += 1

    for name in ('probe.json', 'clinical-witnesses-partial.json'):
        try:
            doc = json.loads((folder/name).read_text())
        except (OSError, ValueError):
            continue
        completed = doc.get('completedOutput') if name == 'probe.json' else doc
        if not isinstance(completed, dict):
            continue
        for row in completed.get('witnesses') or []:
            if isinstance(row, dict) and row.get('acceptedAt') is not None:
                bad += add(row.get('tenant'), 'entries', run+'-probe', str(row.get('date')), row.get('requestToAcceptanceMs'))
        break
    return bad


def wal_position(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-fA-F0-9]{1,8}/[a-fA-F0-9]{1,8}', value),
            'M7_INPUT_SOURCE_POSITION')
    hi, lo = value.split('/')
    return int(hi, 16) << 32 | int(lo, 16)


class Coverage:
    def __init__(self, run, ids, started, source=None):
        self.source = source
        self.before_writes_lsn = None
        self.run, self.ids = run, set(ids)
        self.previous_start = started
        self.inputs = {}
        self.tenants = {}
        self.stored = {}            # tenant -> keys in the latest snapshot
        self.foreign_output = {}    # tenant -> another tenant's output seen in its checkpoint
        self.figures = Counter()
        self.rounds = 0

    def capture(self, rows, start, end):
        """Times are observer monotonic seconds bracketing one PostgreSQL snapshot.

        Shape and fence problems never raise: the row is skipped and counted."""
        seen, stored = set(), {}
        for row in rows:
            try:
                tenant = row['tenant']
                keys = {tuple(k) for k in row['inputs']}
                events = {tuple(k) for k in row['events']}
            except (KeyError, TypeError):
                self.figures['malformedRows'] += 1
                continue
            if tenant in seen:
                self.figures['duplicateTenantRows'] += 1
                continue
            seen.add(tenant)
            stored[tenant] = keys
            if tenant not in self.ids:
                continue                       # stored under a tenant outside the roster: isolation
            if row.get('outputTenant') not in (tenant, None):
                self.foreign_output[tenant] = row['outputTenant']
            old = self.tenants.get(tenant)
            floor, completed = row.get('inputFloor'), row.get('completed')
            valid = row.get('sourceOK') is True and type(floor) is int and floor >= 0
            fenced = (row.get('sourceOK') is False or row.get('stateOK') is False
                      or self.source is not None and row.get('identity') not in (None, self.source)
                      or valid and old and old['floor'] is not None and not (
                          row.get('generation') == old['generation'] and floor >= old['floor'] and
                          row['tailHead'] >= old['head'] and row['tailBase'] >= old['base'] and
                          (old['completed'] is None or completed is not None and completed >= old['completed'])))
            if fenced:
                # Restore fencing: output from another source or generation never covers an input.
                self.figures['fenceRejectedRows'] += 1
                continue
            for key in keys:
                item = self.inputs.setdefault((tenant, *key), {
                    'beforeStore': self.previous_start, 'storedBy': end, 'upperFloor': None,
                    'absentFloor': None, 'durableBy': None, 'pendingAt': None})
                if row['outputAbsent']:
                    item['pendingAt'] = start
                if item['durableBy'] is not None or not valid:
                    continue
                # With an unbroken journal, absence proves this event has yet
                # to enter the stream. An evicted tail supplies no negative.
                intact = row['tailBase'] == 0 or (old is not None and key not in old['keys']
                                                  and row['tailBase'] <= old['head'])
                # A later recovery snapshot could already have included the
                # source row. Only pre-write snapshot coverage proves absence.
                snapshot = row['snapshotPosition']
                before_snapshot = (self.before_writes_lsn is not None and snapshot is not None and
                                   wal_position(snapshot) <= self.before_writes_lsn)
                if key not in events and item['upperFloor'] is None and intact and before_snapshot:
                    item['absentFloor'] = floor
                    item['pendingAt'] = start
                if key in events and item['upperFloor'] is None:
                    item['upperFloor'] = floor
                if row['latest'] is not None and tuple(row['latest']) == key:
                    # The tail head belongs to the current native commit and
                    # follows the recovery snapshot. Its floor is exact.
                    item['absentFloor'] = floor-1
                if row.get('revision') and row['outputTenant'] == tenant and row['outputOK'] is False:
                    item['pendingAt'] = start    # an output failing its own checks proves no valid output yet
                    continue
                if row['stateOK'] is not True or row['outputTenant'] != tenant or row['outputOK'] is not True:
                    continue
                if item['upperFloor'] is not None and completed is not None and completed >= item['upperFloor']:
                    item['durableBy'] = end
                elif completed is None or (item['absentFloor'] is not None and completed <= item['absentFloor']):
                    item['pendingAt'] = start
            self.tenants[tenant] = {'keys': keys, 'generation': row.get('generation'),
                                    'floor': floor if valid else None, 'completed': completed, 'head': row['tailHead'], 'base': row['tailBase']}
        self.stored = stored
        self.rounds += 1
        self.previous_start = start

    def events(self, acks, drain_end, *, through_drain=True):
        """Raw events (see assessor.py) for every acknowledged input."""
        writer = lambda marker: 'probe' if marker == self.run+'-probe' else 'ordinary'
        events = []
        for (tenant, domain, marker, key), duration in sorted(acks.items()):
            item = self.inputs.get((tenant, domain, marker, key), {})
            # Storage commits during the request. The ACK lies between the
            # previous absence and first visibility + measured request duration.
            observed, pending = item.get('durableBy'), item.get('pendingAt')
            upper_ms = max(0, (observed-item['beforeStore'])*1000) if observed is not None else None
            lower_ms = max(0, (pending-item['storedBy'])*1000-duration) if pending is not None else None
            at_drain = ('DURABLE' if observed is not None and observed <= drain_end else
                        'MISSING' if pending is not None and pending >= drain_end else 'UNKNOWN')
            base = {'tenant': tenant, 'domain': domain, 'key': key, 'writer': writer(marker)}
            events.append({'event': 'accepted', **base, 'requestMs': duration})
            events.append({'event': 'output', **base, 'atDrain': at_drain, 'acceptedToOutputMinMs': lower_ms,
                           'acceptedToOutputMaxMs': upper_ms if at_drain == 'DURABLE' else None,
                           'outputTenant': self.foreign_output.get(tenant, tenant if at_drain == 'DURABLE' else None)})
        for tenant, keys in sorted(self.stored.items()):
            for domain, marker, key in sorted(keys):
                events.append({'event': 'stored', 'tenant': tenant, 'domain': domain, 'key': key, 'writer': writer(marker)})
        if self.rounds:
            events.append({'event': 'datastore', 'source': 'sql-observer', 'healthy': True})
            for what in ('storage',) + (('output',) if through_drain else ()):
                events += [{'event': 'readback', 'what': what, 'writer': w} for w in ('ordinary', 'probe')]
        return events


class Observer:
    def __init__(self, *, config, run_id, ids, fetch):
        self.config, self.run, self.ids, self.fetch = config, run_id, set(ids), fetch
        self.stop = threading.Event()
        self.thread = None
        self.error = None

    def start(self):
        selection = ((self.config.get('native') or {}).get('receipt') or {}).get('selection') or {}
        self.coverage = Coverage(self.run, self.ids, time.monotonic(), selection.get('binding', {}).get('source'))
        try:
            self.sql = query(self.config, self.run)
            self.coverage.before_writes_lsn = wal_position(json.loads(
                self.fetch("SELECT to_json(pg_current_wal_insert_lsn()::text)::text;", 20)))
        except Exception as exc:
            self.error = exc
            return self
        def sample():
            try:
                while not self.stop.is_set():
                    self.read()
                    self.stop.wait(3)
            except Exception as exc:
                self.error = exc
        self.thread = threading.Thread(target=contextvars.copy_context().run, args=(sample,), daemon=True)
        self.thread.start()
        return self

    def read(self):
        start = time.monotonic()
        raw = self.fetch(self.sql, 20)
        end = time.monotonic()
        self.coverage.capture((json.loads(line) for line in raw.splitlines() if line.strip()), start, end)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join()

    def durable(self, acks):
        return all((self.coverage.inputs.get(a) or {}).get('durableBy') is not None for a in acks)

    def finish(self, out, *, drain_end, storage=None):
        """Write the raw events; `storage` is accepted for callers and unused."""
        self.close()
        acks = {}
        unread = read_acks(out, self.run, acks)
        errors = [self.error] if self.error else []
        while not self.error and acks and self.coverage.previous_start < drain_end:
            try:
                self.read()
            except Exception as exc:
                errors.append(exc)
                break
            if self.durable(acks):
                break
            time.sleep(min(3, max(0, drain_end-time.monotonic())))
        through = not errors and (self.coverage.previous_start >= drain_end or self.durable(acks))
        codes = sorted({str(e) if re.fullmatch(r'(M7|K8S)_[A-Z0-9_]+', str(e)) else 'M7_INPUT_COLLECTION_UNMEASURED'
                        for e in errors})
        value = {'kind': KIND, 'runId': self.run, 'events': self.coverage.events(acks, drain_end, through_drain=through),
                 'figures': {**self.coverage.figures, 'rounds': self.coverage.rounds, 'unreadAckLines': unread,
                             'collectionErrors': codes, 'drainEndMonoSeconds': drain_end}}
        (out/'evaluator-catchup.json').write_text(json.dumps(value, allow_nan=False)+'\n')
        return value
