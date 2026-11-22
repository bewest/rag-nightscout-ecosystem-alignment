"""Paired synthetic SGV fixture. DATA writes happen before benchmark traffic."""
from concurrent.futures import ThreadPoolExecutor
import collections
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
import json
import math
import os
import re
import sys
from threading import Event
import time
from urllib.parse import quote, urlsplit


BASELINE = {'mode': 'existing-provisioner-only', 'additionalSeedRows': 0, 'retention': 'UNMEASURED'}
MODE = 'synthetic-sgv-6h-v1'
# Underscores cannot collide with the Kubernetes DNS run ID or Compose m7-<owner> marker.
DEVICE = 's4_history_fixture_v1'
ROWS = 72
STEP_MS = 300_000
# Nightscout dataloader.rawQuery('entries') uses TWO_DAYS for a cold working set.
LOOKBACK_MS = 48 * 3_600_000
FIELDS = ('date', 'sgv', 'type', 'device', 'direction', 'dateString')


def require(ok, code):
    if not ok:
        raise ValueError('M7_HISTORY_' + code)


def _looping(mode=None):
    """The looping generator for a mode: v1 (looping_history) or v2 (looping_history_v2); loaded on first use."""
    if mode == MODE_LOOPING_V2:
        import looping_history_v2
        return looping_history_v2
    import looping_history  # imports this module
    return looping_history


def is_looping(spec):
    return isinstance(spec, dict) and spec.get('mode') in LOOPING_MODES


def default_spec(mode, anchor):
    """The spec a mode name and anchor stand for (the looping modes fill their seeded defaults)."""
    return _looping(mode).default_spec(anchor) if mode in LOOPING_MODES else dict(mode=mode, anchorUnixMs=anchor)


def validate(spec):
    if spec == BASELINE and type(spec['additionalSeedRows']) is int:
        return
    if is_looping(spec):
        return _looping(spec['mode']).validate(spec)
    require(isinstance(spec, dict) and set(spec) == {'mode', 'anchorUnixMs'} and spec['mode'] in (MODE,) + tuple(SHAPES),
            'UNSUPPORTED')
    anchor = spec['anchorUnixMs']
    rows = ROWS if spec['mode'] == MODE else SHAPES[spec['mode']][0] * 288
    require(type(anchor) is int and rows * STEP_MS <= anchor < 253402300800000
            and anchor % STEP_MS == 0, 'ANCHOR')


def rows_per_tenant(spec):
    """Stored rows per tenant by collection for a populated-history spec (looping: a looping tenant)."""
    if is_looping(spec):
        return _looping(spec['mode']).rows_per_tenant(spec)
    if spec.get('mode') in SHAPES:
        days = SHAPES[spec['mode']][0]
        return dict(entries=days*288, devicestatus=days*288, treatments=days*TREATMENTS_PER_DAY, profile=1)
    return dict(entries=ROWS)


def entries(anchor, ordinal):
    result = []
    for index in range(ROWS):
        stamp = anchor - (ROWS - 1 - index) * STEP_MS
        iso = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).isoformat(timespec='milliseconds')
        # A smooth triangular series, phase-shifted by synthetic tenant ordinal.
        phase = (index + ordinal) % 40
        result.append(dict(type='sgv', device=DEVICE, direction='Flat', sgv=100+min(phase, 40-phase),
                           date=stamp, dateString=iso.replace('+00:00', 'Z')))
    return result


def digest(rows):
    body = '|'.join(','.join(str(row[k]) for k in FIELDS) for row in rows)
    return hashlib.md5(body.encode()).hexdigest()


def census(sql, at, horizon):
    fields = " || ',' || ".join(f"(doc->>'{k}')" for k in FIELDS)
    raw = sql(f"""SELECT tenant_id::text, count(*), sum(pg_column_size(doc)),
        count(*) FILTER (WHERE jsonb_typeof(doc->'date') = 'number' AND jsonb_typeof(doc->'sgv') = 'number'
           AND (doc->'isValid') IS DISTINCT FROM 'false'::jsonb
           AND (doc->>'date')::bigint BETWEEN {at+horizon-LOOKBACK_MS} AND {at}),
        md5(string_agg({fields}, '|' ORDER BY (doc->>'date')::bigint))
        FROM nsdemo_entries.entries WHERE doc->>'device'='{DEVICE}' GROUP BY tenant_id;""")
    measured = {}
    for line in raw.splitlines():
        tenant, rows, size, active, checksum = line.split('\t')
        measured[tenant] = dict(rows=int(rows), storedDocBytes=int(size), activeRows=int(active), md5=checksum)
    return measured


def remaining(until, maximum):
    limit = min(maximum, until - time.time()) if until is not None else maximum
    require(limit > 0, 'DEADLINE')
    return limit


def post(port, tenant, rows, until, path='/api/v1/entries'):
    # Retries only refusals that precede processing (429/503 admission, connection refused):
    # a lost ACK is never retried, so a non-idempotent devicestatus batch cannot be doubled.
    for attempt in range(6):
        conn = HTTPConnection('127.0.0.1', port, timeout=remaining(until, 120 if path != '/api/v1/entries' or len(rows) > ROWS else 30))
        try:
            try:
                conn.connect()
            except ConnectionRefusedError:
                if attempt == 5: raise
                time.sleep(2 ** attempt); continue
            conn.request('POST', path + '?token=' + quote(tenant['token'], safe=''),
                         body=json.dumps(rows).encode(),
                         headers={'Host': tenant['host'], 'Content-Type': 'application/json'})
            response = conn.getresponse()
            if 200 <= response.status < 300:
                response.read()
                return
            # Response bodies and tenant URLs can contain private data. Record only known codes and paths.
            try:
                body = json.loads(response.read(4096))
            except (ValueError, UnicodeError):
                body = None
            code = body.get('error') if isinstance(body, dict) else None
            if code not in ('STORAGE_TIMEOUT', 'STORAGE_BUSY', 'STORAGE_UNAVAILABLE'):
                code = 'UNKNOWN'
            route = path if path in ('/api/v1/entries', '/api/v1/devicestatus', '/api/v1/treatments', '/api/v1/profile') else 'UNKNOWN'
            failure = f'HTTP_{response.status} {route} {code} rows={len(rows) if isinstance(rows, list) else 1} attempt={attempt+1}'
            print('M7_HISTORY_' + failure, file=sys.stderr, flush=True)
            if response.status in (429, 503) and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            raise ValueError('M7_HISTORY_' + failure)
        finally:
            conn.close()


def run(spec, tenants, base, sql, until, window_seconds, *, verify_only=False, post_batch=post, now=time.time):
    validate(spec)
    if is_looping(spec):
        return _looping(spec['mode']).run(spec, tenants, base, sql, until, window_seconds, verify_only=verify_only,
                              post_batch=post_batch, now=now)
    if spec != BASELINE and spec['mode'] in SHAPES:
        return run_4w(spec, tenants, base, sql, until, window_seconds, verify_only=verify_only,
                      post_batch=post_batch, now=now)
    require(spec != BASELINE and tenants and type(window_seconds) is int and window_seconds >= 0, 'INPUT')
    require(re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', base), 'EDGE')
    port = urlsplit(base).port
    require(port and len({row['id'] for row in tenants}) == len(tenants)
            and len({row['host'] for row in tenants}) == len(tenants), 'ROSTER')
    anchor = spec['anchorUnixMs']
    roster = sorted(tenants, key=lambda row: row['host'])
    expected = {tenant['id']: digest(entries(anchor, i)) for i, tenant in enumerate(roster)}

    def inspect():
        at = int(now() * 1000)
        # Finite arms must remain eligible through their outer work deadline, including startup.
        horizon = max(window_seconds*1000, math.ceil(until*1000)-at if until is not None else 0)
        require(anchor <= at and at+horizon-LOOKBACK_MS <= anchor-(ROWS-1)*STEP_MS, 'OUTSIDE_CLINICAL_WINDOW')
        measured = census(sql, at, horizon)
        require(measured.keys() <= expected.keys(), 'FOREIGN_TENANT')
        for tenant, row in measured.items():
            require(row['rows'] == row['activeRows'] == ROWS and row['storedDocBytes'] > 0
                    and row['md5'] == expected[tenant], 'READBACK_MISMATCH')
        return at, measured

    at, measured = inspect()
    missing = [(i, tenant) for i, tenant in enumerate(roster) if tenant['id'] not in measured]
    if missing:
        require(not verify_only, 'RESTORED_ROWS_MISSING')
        # v1 entry upserts select (sysTime, type). Protect existing primer and previous run rows.
        times = ','.join("'" + r['dateString'] + "'" for r in entries(anchor, 0))
        collisions = sql(f"""SELECT DISTINCT tenant_id::text FROM nsdemo_entries.entries
            WHERE doc->>'type'='sgv' AND doc->>'device' IS DISTINCT FROM '{DEVICE}'
              AND doc->>'sysTime' IN ({times});""").splitlines()
        require(set(collisions).isdisjoint(tenant['id'] for _, tenant in missing), 'UPSERT_KEY_IN_USE')
        # A lost ACK or partial batch is resolved by readback on the next attempt.
        # Never append to an incomplete or mismatched tenant.
        failed = Event()
        def seed(item):
            if failed.is_set():
                return
            i, tenant = item
            try:
                post_batch(port, tenant, entries(anchor, i), until)
            except Exception:
                failed.set()
                raise
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(seed, missing))
        at, measured = inspect()
    require(measured.keys() == expected.keys(), 'ROWS_MISSING')
    logical = hashlib.sha256()
    per_tenant = []
    for i, tenant in enumerate(roster):
        value = measured[tenant['id']]
        logical.update(f"{tenant['host']}:{value['md5']}\n".encode())
        per_tenant.append(dict(ordinal=i, **value))
    return dict(version=1, history=spec, observedUnixMs=at, anchorAgeMs=at-anchor,
                eligibilityThroughUnixMs=max(at+window_seconds*1000, math.ceil(until*1000) if until else 0),
                measuredWindowSeconds=window_seconds, coldEntriesLookbackMs=LOOKBACK_MS,
                rowsPerTenant=ROWS, seededBatches=len(missing), logicalSha256=logical.hexdigest(),
                rows=sum(r['rows'] for r in per_tenant), activeRows=sum(r['activeRows'] for r in per_tenant),
                storedDocBytes=sum(r['storedDocBytes'] for r in per_tenant), tenants=per_tenant)


def window(workload):
    return sum(workload.get(key, default) for key, default in
               (('setupSeconds', 310), ('loadSeconds', 0), ('drainSeconds', 120)))


def check_snapshot(spec, manifest):
    require(manifest.get('history', BASELINE) == spec, 'SNAPSHOT_MISMATCH')


# ---------------------------------------------------------------------------------------------
# synthetic-history-4w-v1: four weeks per tenant, written through the API like the 6 h mode.
#   entries       28 d of 5-minute SGV (8,064 rows)
#   devicestatus  every 5 minutes (8,064 rows), an OpenAPS-shaped status with pump and uploader
#   treatments    8 per day (224 rows): three meal boluses with carbs, one correction, four temp basals
#   profile       one profile document
# Every row carries the fixture marker; readback counts each collection per tenant and checks
# order-independent numeric sums the generator fixes, plus the same SGV md5 as the 6 h mode.
MODE_4W = 'synthetic-history-4w-v1'
DEVICE_4W = 's4_history_fixture_4w_v1'
DAYS_4W = 28
SGV_4W = DAYS_4W * 288
DS_4W = SGV_4W
TREATMENTS_PER_DAY = 8
TREATMENTS_4W = DAYS_4W * TREATMENTS_PER_DAY
SGV_BATCH = 288           # one day per request (short requests: the edge proxy_read_timeout is 60 s)
DS_BATCH = 288            # one day per request
WORKERS_4W = 16
# The fixture ends at its anchor; the evaluator's 48 h window must still hold at least half
# history at the end of the run (the run's own writes fill the rest).
MAX_STALE_4W_MS = 24 * 3_600_000

# synthetic-history-2d-v1: the same generator over two days, the evaluator's cold window
# (LOOKBACK_MS): 576 SGV, 576 devicestatus, 16 treatments, one profile per tenant. Its own
# marker, so its readback never counts another mode's rows, and its own fixture-catalog key.
MODE_2D = 'synthetic-history-2d-v1'
DEVICE_2D = 's4_history_fixture_2d_v1'
DAYS_2D = 2
SHAPES = {MODE_4W: (DAYS_4W, DEVICE_4W), MODE_2D: (DAYS_2D, DEVICE_2D)}  # mode -> (days, marker)

# synthetic-history-looping-2d-v1 (looping_history.py): a closed-loop population over the same 2-day
# window, seeded, with CGM-only and deep-history tenants. Its own marker and fixture-catalog key.
MODE_LOOPING = 'synthetic-history-looping-2d-v1'
# synthetic-history-looping-2d-v2 (looping_history_v2.py): sized per controller from the AID client model.
MODE_LOOPING_V2 = 'synthetic-history-looping-2d-v2'
LOOPING_MODES = (MODE_LOOPING, MODE_LOOPING_V2)


def seed_limits(environ=os.environ):
    """Seed concurrency and rows per request. Operator knobs for a write path that times out under load;
    they change how rows are sent, never which rows, so they are not part of the fixture key."""
    workers = int(environ.get('S4_HISTORY_SEED_WORKERS', WORKERS_4W))
    batch = int(environ.get('S4_HISTORY_SEED_BATCH', SGV_BATCH))
    require(1 <= workers <= 64 and 1 <= batch <= SGV_BATCH, 'SEED_LIMITS')
    return workers, batch


def _iso(stamp):
    return datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def _sgv_4w(stamp, ordinal):
    day = 2 * math.pi * (stamp % 86_400_000) / 86_400_000
    fast = 2 * math.pi * (stamp % 11_160_000) / 11_160_000
    return int(max(40, min(400, round(130 + 45 * math.sin(day + ordinal * 0.37) + 20 * math.sin(fast + ordinal)))))


def entries_4w(anchor, ordinal, days=DAYS_4W, device=DEVICE_4W):
    out = []
    n = days * 288
    for index in range(n):
        stamp = anchor - (n - 1 - index) * STEP_MS
        out.append(dict(type='sgv', device=device, direction='Flat', sgv=_sgv_4w(stamp, ordinal),
                        date=stamp, dateString=_iso(stamp)))
    return out


def devicestatus_4w(anchor, ordinal, days=DAYS_4W, device=DEVICE_4W):
    out = []
    n = days * 288
    for index in range(n):
        stamp = anchor - (n - 1 - index) * STEP_MS
        iso = _iso(stamp); bg = _sgv_4w(stamp, ordinal); iob = round(((index + ordinal) % 60) / 20, 2)
        out.append({'device': 'openaps://' + device, 'created_at': iso,
                    'uploader': {'battery': 40 + (index + ordinal) % 60},
                    'pump': {'clock': iso, 'reservoir': round(200 - (index % 864) * 0.2, 1),
                             'battery': {'percent': 50 + index % 50}, 'status': {'status': 'normal', 'bolusing': False}},
                    'openaps': {'iob': {'iob': iob, 'basaliob': round(iob / 3, 2), 'activity': round(iob / 100, 4), 'time': iso},
                                'suggested': {'bg': bg, 'eventualBG': bg + 5, 'temp': 'absolute', 'rate': 0.8, 'duration': 30,
                                              'reason': 'synthetic history', 'timestamp': iso}}})
    return out


# (minute of day, eventType, insulin, carbs, rate) — eight per day
_DAY = ((450, 'Meal Bolus', 5.0, 45), (750, 'Meal Bolus', 6.0, 60), (1110, 'Meal Bolus', 7.0, 70),
        (900, 'Correction Bolus', 1.0, None), (120, 'Temp Basal', None, None), (600, 'Temp Basal', None, None),
        (960, 'Temp Basal', None, None), (1320, 'Temp Basal', None, None))


def treatments_4w(anchor, ordinal, days=DAYS_4W, device=DEVICE_4W):
    out = []
    first_day = anchor - anchor % 86_400_000 - (days - 1) * 86_400_000
    for day in range(days):
        for slot, (minute, kind, insulin, carbs) in enumerate(_DAY):
            stamp = first_day + day * 86_400_000 + minute * 60_000 + (ordinal % 6) * STEP_MS
            if stamp > anchor:
                stamp -= days * 86_400_000  # wrap the last day's later slots to before the first day
            doc = {'eventType': kind, 'created_at': _iso(stamp), 'enteredBy': device}
            if insulin is not None:
                doc['insulin'] = insulin
            if carbs is not None:
                doc['carbs'] = carbs
            if kind == 'Temp Basal':
                doc.update(duration=30, absolute=round(0.4 + 0.1 * ((day + slot + ordinal) % 8), 1))
            out.append(doc)
    return out


def profile_4w(anchor, days=DAYS_4W, device=DEVICE_4W):
    start = _iso(anchor - days * 288 * STEP_MS)
    sched = lambda v: [{'time': '00:00', 'value': v, 'timeAsSeconds': 0}]
    return {'defaultProfile': 'S4History', 'startDate': start, 'created_at': start,
            'units': 'mg/dl', 'enteredBy': device,
            'store': {'S4History': {'dia': 4, 'carbratio': sched(10), 'sens': sched(50), 'basal': sched(0.8),
                                    'target_low': sched(100), 'target_high': sched(120), 'units': 'mg/dl',
                                    'timezone': 'UTC', 'delay': 20, 'startDate': '1970-01-01T00:00:00.000Z'}}}


def expected_4w(anchor, ordinal, days=DAYS_4W, device=DEVICE_4W):
    """Readback values the API must preserve: counts and order-independent numeric sums."""
    e = entries_4w(anchor, ordinal, days, device); d = devicestatus_4w(anchor, ordinal, days, device)
    t = treatments_4w(anchor, ordinal, days, device)
    return dict(entries=len(e), entriesMd5=digest(e), devicestatus=len(d),
                dsBattery=sum(r['uploader']['battery'] for r in d), treatments=len(t),
                insulinX10=round(sum(r.get('insulin', 0) for r in t) * 10), carbs=sum(r.get('carbs', 0) for r in t),
                profile=1)


def _tables(sql):
    raw = sql("""SELECT c.relname, n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p') AND n.nspname LIKE 'nsdemo%' AND c.relname IN ('entries','devicestatus','treatments','profile');""")
    found = {}
    for line in raw.splitlines():
        rel, nsp = line.split('\t')
        require(rel not in found, 'TABLE_AMBIGUOUS')
        found[rel] = '"' + nsp + '"."' + rel + '"'
    require(set(found) == {'entries', 'devicestatus', 'treatments', 'profile'}, 'TABLES')
    return found


def census_4w(sql, tables, at, horizon, device=DEVICE_4W):
    fields = " || ',' || ".join(f"(doc->>'{k}')" for k in FIELDS)
    measured = collections.defaultdict(dict)
    for line in sql(f"""SELECT tenant_id::text, count(*), sum(pg_column_size(doc)),
        count(*) FILTER (WHERE jsonb_typeof(doc->'date') = 'number'
           AND (doc->>'date')::bigint BETWEEN {at+horizon-LOOKBACK_MS} AND {at}),
        md5(string_agg({fields}, '|' ORDER BY (doc->>'date')::bigint))
        FROM {tables['entries']} WHERE doc->>'device'='{device}' GROUP BY tenant_id;""").splitlines():
        tenant, rows, size, active, checksum = line.split('\t')
        measured[tenant].update(entries=int(rows), entriesBytes=int(size), activeRows=int(active), entriesMd5=checksum)
    for line in sql(f"""SELECT tenant_id::text, count(*), sum(pg_column_size(doc)), sum((doc->'uploader'->>'battery')::bigint)
        FROM {tables['devicestatus']} WHERE doc->>'device'='openaps://{device}' GROUP BY tenant_id;""").splitlines():
        tenant, rows, size, battery = line.split('\t')
        measured[tenant].update(devicestatus=int(rows), devicestatusBytes=int(size), dsBattery=int(battery))
    for line in sql(f"""SELECT tenant_id::text, count(*), sum(pg_column_size(doc)),
        round(coalesce(sum((doc->>'insulin')::numeric),0)*10), coalesce(sum((doc->>'carbs')::numeric),0)
        FROM {tables['treatments']} WHERE doc->>'enteredBy'='{device}' GROUP BY tenant_id;""").splitlines():
        tenant, rows, size, insulin, carbs = line.split('\t')
        measured[tenant].update(treatments=int(rows), treatmentsBytes=int(size), insulinX10=int(float(insulin)), carbs=int(float(carbs)))
    for line in sql(f"""SELECT tenant_id::text, count(*) FROM {tables['profile']}
        WHERE doc->>'enteredBy'='{device}' GROUP BY tenant_id;""").splitlines():
        tenant, rows = line.split('\t')
        measured[tenant]['profile'] = int(rows)
    return dict(measured)


CHECKED_4W = ('entries', 'entriesMd5', 'devicestatus', 'dsBattery', 'treatments', 'insulinX10', 'carbs', 'profile')


def run_4w(spec, tenants, base, sql, until, window_seconds, *, verify_only=False, post_batch=post, now=time.time):
    require(tenants and type(window_seconds) is int and window_seconds >= 0, 'INPUT')
    require(re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', base), 'EDGE')
    port = urlsplit(base).port
    require(port and len({row['id'] for row in tenants}) == len(tenants)
            and len({row['host'] for row in tenants}) == len(tenants), 'ROSTER')
    anchor = spec['anchorUnixMs']
    days, device = SHAPES[spec['mode']]
    workers, batch = seed_limits()
    roster = sorted(tenants, key=lambda row: row['host'])
    expected = {tenant['id']: expected_4w(anchor, i, days, device) for i, tenant in enumerate(roster)}
    tables = _tables(sql)

    def inspect():
        at = int(now() * 1000)
        horizon = max(window_seconds*1000, math.ceil(until*1000)-at if until is not None else 0)
        require(anchor <= at and at + horizon - anchor <= MAX_STALE_4W_MS, 'OUTSIDE_CLINICAL_WINDOW')
        measured = census_4w(sql, tables, at, horizon, device)
        require(measured.keys() <= expected.keys(), 'FOREIGN_TENANT')
        return at, measured

    def complete(tenant, value):
        return all(value.get(k) == expected[tenant][k] for k in CHECKED_4W)

    at, measured = inspect()
    partial = [t for t, v in measured.items() if not complete(t, v)]
    require(not partial, 'READBACK_MISMATCH')  # never append to an incomplete or mismatched tenant
    missing = [(i, tenant) for i, tenant in enumerate(roster) if tenant['id'] not in measured]
    if missing:
        require(not verify_only, 'RESTORED_ROWS_MISSING')
        ids = ','.join("'" + t['id'] + "'" for _, t in missing)
        oldest = anchor - (days * 288 - 1) * STEP_MS
        collisions = sql(f"""SELECT DISTINCT tenant_id::text FROM {tables['entries']}
            WHERE tenant_id::text IN ({ids}) AND doc->>'type'='sgv' AND doc->>'device' IS DISTINCT FROM '{device}'
              AND jsonb_typeof(doc->'date')='number' AND (doc->>'date')::bigint BETWEEN {oldest} AND {anchor};""").splitlines()
        require(not collisions, 'UPSERT_KEY_IN_USE')
        failed = Event()
        def seed(item):
            if failed.is_set():
                return
            i, tenant = item
            try:
                e = entries_4w(anchor, i, days, device)
                for k in range(0, len(e), batch):
                    post_batch(port, tenant, e[k:k+batch], until, path='/api/v1/entries')
                d = devicestatus_4w(anchor, i, days, device)
                for k in range(0, len(d), batch):
                    post_batch(port, tenant, d[k:k+batch], until, path='/api/v1/devicestatus')
                post_batch(port, tenant, treatments_4w(anchor, i, days, device), until, path='/api/v1/treatments')
                post_batch(port, tenant, profile_4w(anchor, days, device), until, path='/api/v1/profile')
            except Exception:
                failed.set()
                raise
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(seed, missing))
        at, measured = inspect()
    require(measured.keys() == expected.keys(), 'ROWS_MISSING')
    for tenant, value in measured.items():
        require(complete(tenant, value), 'READBACK_MISMATCH')
    logical = hashlib.sha256()
    per_tenant = []
    for i, tenant in enumerate(roster):
        value = measured[tenant['id']]
        logical.update((tenant['host'] + ':' + json.dumps({k: value[k] for k in CHECKED_4W}, sort_keys=True) + '\n').encode())
        per_tenant.append(dict(ordinal=i, **value))
    total = lambda k: sum(r.get(k, 0) for r in per_tenant)
    return dict(version=1, history=spec, observedUnixMs=at, anchorAgeMs=at-anchor,
                eligibilityThroughUnixMs=max(at+window_seconds*1000, math.ceil(until*1000) if until else 0),
                measuredWindowSeconds=window_seconds, coldEntriesLookbackMs=LOOKBACK_MS,
                rowsPerTenant=rows_per_tenant(spec), seededBatches=len(missing), logicalSha256=logical.hexdigest(),
                rows=total('entries'), activeRows=total('activeRows'), storedDocBytes=total('entriesBytes'),
                collections={k: dict(rows=total(k), storedDocBytes=total(k + 'Bytes')) for k in ('entries', 'devicestatus', 'treatments')},
                tenants=per_tenant)
