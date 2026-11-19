"""Read-only acceptance-to-durable coverage for the ordinary pgstream run.

Each HTTP ACK identifies one run-marked storage row. A native journal event
binds that row to an intake floor. A fenced durable completion at or beyond
that floor covers the input, including when the worker coalesces inputs.
"""
import contextvars
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time
from collections import Counter

KIND = 'accepted-input-drain-v1'
DEADLINE_MS = 120000
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
    receipt = native.get('receipt') or {}
    require(config.get('kind') == 'evaluator-work-v2' and native.get('kind') == 'compact-native-v1',
            'M7_INPUT_NATIVE_SOURCE_REQUIRED')
    canonical = json.dumps(native, sort_keys=True, separators=(',', ':')).encode()
    require(hashlib.sha256(canonical).hexdigest() == config['binding'].get('nativeConfigurationSha256'),
            'M7_INPUT_SOURCE_CHANGED', 'FAIL')
    consumer = native.get('inputConsumer', '')
    require(config.get('consumer') == consumer + '-completed' and config.get('entries') == 'nsdemo_entries',
            'M7_INPUT_SOURCE_CHANGED', 'FAIL')
    parts = ['evaluator-work-v2', config['checkpoint'], consumer,
             'canonical-maintenance-active-plus2-v1', 'positive-int8-complete-pair-max-4611686018427387902-v1']
    digest = receipt.get('contractDigest') if receipt else hashlib.sha256(
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


def read_acks(folder, run, ids, result):
    """Read confirmed HTTP responses from each writer, including partial probe evidence."""

    def add(tenant, domain, marker, key, duration):
        require(tenant in ids, 'M7_INPUT_FOREIGN_ACK', 'FAIL')
        require(domain in ('entries', 'devicestatus', 'treatments') and isinstance(key, str) and key and
                type(duration) in (float, int) and math.isfinite(duration) and duration >= 0,
                'M7_INPUT_ACK_SHAPE')
        identity = (tenant, domain, marker, key)
        require(identity not in result, 'M7_INPUT_DUPLICATE_ACK')
        result[identity] = duration

    logs = sorted(folder.glob('k6-shard-*.log')) or [folder/'k6.log']
    for path in logs:
        if not path.is_file():
            continue
        with path.open() as stream:
            for line in stream:
                if 'm7-input-accepted' not in line:
                    continue
                match = re.search(r'\bmsg=("(?:[^"\\]|\\.)*")', line)
                message = json.loads(match[1]) if match else json.loads(line)['msg']
                row = json.loads(message)
                require(row['event'] == 'm7-input-accepted' and row['run'] == run, 'M7_INPUT_RUN_BINDING')
                add(row['tenant'], row['domain'], run, row['key'], row['requestToAcceptanceMs'])

    for name in ('probe.json', 'clinical-witnesses-partial.json'):
        path = folder/name
        if path.is_file():
            doc = json.loads(path.read_text())
            completed = doc.get('completedOutput') if name == 'probe.json' else doc
            if not isinstance(completed, dict):
                continue
            for row in completed.get('witnesses', []):
                if row.get('acceptedAt') is not None:
                    add(row['tenant'], 'entries', run+'-probe', str(row['date']), row['requestToAcceptanceMs'])
            break

def reconcile(result, run, ids, storage):
    """Reconcile the ACK identities against the independently reduced write counts."""
    require(isinstance(storage, dict) and storage.get('verdict') == 'GREEN' and storage.get('uncertain') == 0,
            'M7_INPUT_STORAGE_UNMEASURED')
    rows = storage.get('rows') or []
    require(len(rows) == len(ids) and {r['tenant'] for r in rows} == ids, 'M7_INPUT_STORAGE_COVERAGE')
    counts = Counter((t, marker) for t, _, marker, _ in result)
    for row in rows:
        require(row.get('match') is True and row['probePending'] == row['probeUncertain'] == 0 and
                row['accepted'] == row['stored'] == counts[row['tenant'], run] and
                row['probeAccepted'] == row['probeStored'] == counts[row['tenant'], run+'-probe'],
                'M7_INPUT_ACK_COVERAGE')


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
        self.rounds = 0

    def capture(self, rows, start, end):
        """Times are observer monotonic seconds bracketing one PostgreSQL snapshot."""
        seen = set()
        for row in rows:
            tenant = row['tenant']
            require(tenant in self.ids, 'M7_INPUT_FOREIGN_STORAGE', 'FAIL')
            require(tenant not in seen, 'M7_INPUT_DUPLICATE_TENANT')
            seen.add(tenant)
            old = self.tenants.get(tenant)
            keys = {tuple(k) for k in row['inputs']}
            events = {tuple(k) for k in row['events']}
            require(len(keys) == len(row['inputs']), 'M7_INPUT_DUPLICATE_STORAGE')
            for domain, marker, key in keys | events:
                require(isinstance(key, str) and domain in ('entries', 'devicestatus', 'treatments') and
                        (marker == self.run or (marker == self.run+'-probe' and domain == 'entries')),
                        'M7_INPUT_SOURCE_KEY')
            require(events <= keys, 'M7_INPUT_FOREIGN_EVENT', 'FAIL')
            require(old is None or old['keys'] <= keys, 'M7_INPUT_STORED_ROW_LOST', 'FAIL')
            require(row['outputTenant'] in (tenant, None), 'M7_INPUT_FOREIGN_OUTPUT', 'FAIL')
            require(row['sourceOK'] is not False and row['stateOK'] is not False, 'M7_INPUT_SOURCE_FENCE', 'FAIL')
            if self.source is not None and row['identity'] is not None:
                require(row['identity'] == self.source, 'M7_INPUT_SOURCE_FENCE', 'FAIL')
            floor, completed = row['inputFloor'], row['completed']
            valid = row['sourceOK'] is True and type(floor) is int and floor >= 0
            if valid and old and old['floor'] is not None:
                require(row['generation'] == old['generation'] and floor >= old['floor'] and
                        row['tailHead'] >= old['head'] and row['tailBase'] >= old['base'] and
                        (old['completed'] is None or completed is not None and completed >= old['completed']),
                        'M7_INPUT_GENERATION_CHANGED', 'FAIL')
            if row['revision'] and row['outputOK'] is not True:
                require(row['outputTenant'] is not None, 'M7_INPUT_OUTPUT_UNMEASURED')
                raise EvidenceError('M7_INPUT_INVALID_OUTPUT', 'FAIL')
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
                if row['stateOK'] is not True:
                    continue
                if (item['upperFloor'] is not None and row['outputOK'] is True and
                        completed is not None and completed >= item['upperFloor']):
                    item['durableBy'] = end
                elif (row['revision'] == 0 or completed is None or
                      (item['absentFloor'] is not None and completed <= item['absentFloor'])):
                    item['pendingAt'] = start
            self.tenants[tenant] = {'keys': keys, 'generation': row['generation'],
                                    'floor': floor if valid else None, 'completed': completed, 'head': row['tailHead'], 'base': row['tailBase']}
        require(set(self.tenants) <= seen, 'M7_INPUT_STORED_ROW_LOST', 'FAIL')
        self.rounds += 1
        self.previous_start = start

    def assess(self, acks, drain_end):
        codes = set()
        rows = []
        if set(self.inputs) - set(acks):
            codes.add('M7_INPUT_STORAGE_ACK_MISMATCH')
        for identity, duration in sorted(acks.items()):
            item = self.inputs.get(identity, {})
            # Storage commits during the request. The ACK lies between the
            # previous absence and first visibility + measured request duration.
            observed = item.get('durableBy')
            pending = item.get('pendingAt')
            earliest = item.get('beforeStore')
            latest = item.get('storedBy')
            upper_ms = max(0, (observed-earliest)*1000) if observed is not None else None
            lower_ms = max(0, (pending-latest)*1000-duration) if pending is not None else None
            if observed is not None and observed <= drain_end:
                at_end = 'DURABLE'
            elif pending is not None and pending >= drain_end:
                at_end = 'MISSING'
            else:
                at_end = 'UNMEASURED'
            if lower_ms is not None and lower_ms >= DEADLINE_MS:
                status = 'LATE'
            elif at_end == 'MISSING':
                status = 'MISSING_AT_DRAIN'
            elif observed is not None and observed <= drain_end and upper_ms < DEADLINE_MS:
                status = 'ON_TIME'
            else:
                status = 'UNMEASURED'
            rows.append(dict(zip(('tenant', 'domain', 'marker', 'key'), identity),
                             status=status, endOfDrain=at_end, lowerMs=lower_ms, upperMs=upper_ms))
        counts = Counter(r['status'] for r in rows)
        if counts['LATE']:
            codes.add('M7_INPUT_DEADLINE')
        if counts['MISSING_AT_DRAIN']:
            codes.add('M7_INPUT_MISSING_AT_DRAIN')
        if counts['UNMEASURED'] or self.rounds == 0:
            codes.add('M7_INPUT_TIMING_UNMEASURED')
        verdict = 'FAIL' if counts['LATE'] or counts['MISSING_AT_DRAIN'] else 'UNMEASURED' if codes else 'PASS'
        return {'kind': KIND, 'verdict': verdict, 'codes': sorted(codes), 'acceptedInputs': len(acks),
                'classifications': dict(counts), 'endOfDrain': dict(Counter(r['endOfDrain'] for r in rows)),
                'inputs': rows, 'rounds': self.rounds,
                'deadlineMs': DEADLINE_MS, 'drainEndMonoSeconds': drain_end}


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

    def finish(self, out, *, drain_end, storage):
        self.close()
        acks = {}
        failures = []
        def attempted(fn, *args):
            try:
                fn(*args)
                return True
            except Exception as exc:
                failures.append(exc)
                return False

        decoded = attempted(read_acks, out, self.run, self.ids, acks)
        complete = attempted(reconcile, acks, self.run, self.ids, storage) and decoded
        if self.error:
            failures.append(self.error)
        while not self.error and (complete or acks):
            if not attempted(self.read):
                break
            value = self.coverage.assess(acks, drain_end)
            if value['endOfDrain'].get('DURABLE', 0) == len(acks) or self.coverage.previous_start >= drain_end:
                break
            time.sleep(min(3, max(0, drain_end-time.monotonic())))
        value = self.coverage.assess(acks, drain_end)
        for exc in failures:
            code = str(exc)
            code = code if re.fullmatch(r'(M7|K8S)_[A-Z0-9_]+', code) else 'M7_INPUT_COLLECTION_UNMEASURED'
            value['codes'].append(code)
            if getattr(exc, 'verdict', None) == 'FAIL':
                value['verdict'] = 'FAIL'
            elif value['verdict'] == 'PASS':
                value['verdict'] = 'UNMEASURED'
        value['codes'] = sorted(set(value['codes']))
        value['ackCoverage'] = 'COMPLETE' if complete else 'PARTIAL'
        value['reader'] = self.config.get('binding')
        value['runId'] = self.run
        (out/'evaluator-catchup.json').write_text(json.dumps(value, allow_nan=False)+'\n')
        return value
