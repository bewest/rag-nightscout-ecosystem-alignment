"""Paired synthetic SGV fixture. DATA writes happen before benchmark traffic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
import json
import math
import re
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


def validate(spec):
    if spec == BASELINE and type(spec['additionalSeedRows']) is int:
        return
    require(isinstance(spec, dict) and set(spec) == {'mode', 'anchorUnixMs'} and spec['mode'] == MODE,
            'UNSUPPORTED')
    anchor = spec['anchorUnixMs']
    require(type(anchor) is int and ROWS * STEP_MS <= anchor < 253402300800000
            and anchor % STEP_MS == 0, 'ANCHOR')


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


def post(port, tenant, rows, until):
    conn = HTTPConnection('127.0.0.1', port, timeout=remaining(until, 30))
    try:
        conn.request('POST', '/api/v1/entries?token=' + quote(tenant['token'], safe=''),
                     body=json.dumps(rows).encode(),
                     headers={'Host': tenant['host'], 'Content-Type': 'application/json'})
        response = conn.getresponse()
        require(200 <= response.status < 300, 'HTTP_' + str(response.status))
        response.read()
    finally:
        conn.close()


def run(spec, tenants, base, sql, until, window_seconds, *, verify_only=False, post_batch=post, now=time.time):
    validate(spec)
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
