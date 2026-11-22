"""M3: offline end-to-end latency oracle (lane mt-plannable-scale-20261121, E3).

After the run, join the load driver's accepted writes (the k6 `m7-input-accepted`
lines, with the driver clock's `acceptedAtMs`) to the first realtime `dataUpdate`
frame, on any viewer of that tenant, whose newest record of the write's domain
is at least the write's key (the probe's `--frameLedger` lines). The key is the
document's own `date` (entries, treatments) or `created_at` (devicestatus), and
the frame carries the same values, so the frame identifies the write without
an id. Nothing reads the database.

    lag = frame receipt (viewer clock) + offset - acceptance (driver clock)

where offset = driver clock - viewer clock, measured and passed in. Only tenants
with a viewer are joined; the rest are counted as unviewed. A write whose frame
never arrived is `unmatched`; it is `censored` if the ledger ends less than the
120 s deadline after its acceptance.

    python3 latency_oracle.py --k6 DIR --frames FILE --run RUNID [--offset-ms N] [--rows OUT.jsonl] > m3-latency.json
"""
import argparse
import bisect
import datetime
import json
import math
import re
import sys
from pathlib import Path

DEADLINE_MS = 120000
EDGES_MS = (1000, 30000, 120000)
DOMAINS = ('entries', 'devicestatus', 'treatments')


def key_ms(domain, key):
    if re.fullmatch(r'-?[0-9]{1,16}', key):
        return int(key)
    try:
        return int(datetime.datetime.fromisoformat(key.replace('Z', '+00:00')).timestamp() * 1000)
    except ValueError:
        return None


def accepted(paths, run):
    """Rows (tenant, domain, keyMs, acceptedAtMs, requestMs) and refusal counts."""
    rows, counts = [], {'lines': 0, 'malformed': 0, 'otherRun': 0, 'noAcceptanceTime': 0}
    for path in paths:
        with open(path, errors='replace') as stream:
            for line in stream:
                if 'm7-input-accepted' not in line:
                    continue
                counts['lines'] += 1
                try:
                    match = re.search(r'\bmsg=("(?:[^"\\]|\\.)*")', line)
                    row = json.loads(json.loads(match[1]) if match else json.loads(line)['msg'])
                except (ValueError, KeyError, TypeError):
                    counts['malformed'] += 1
                    continue
                if row.get('run') != run:
                    counts['otherRun'] += 1
                    continue
                at, domain = row.get('acceptedAtMs'), row.get('domain')
                key = key_ms(domain, str(row.get('key')))
                if domain not in DOMAINS or key is None or not isinstance(row.get('tenant'), str):
                    counts['malformed'] += 1
                    continue
                if type(at) is not int:
                    counts['noAcceptanceTime'] += 1
                    continue
                rows.append((row['tenant'], domain, key, at, row.get('requestToAcceptanceMs')))
    return rows, counts


def frames(path):
    by = {}
    with open(path) as stream:
        for line in stream:
            row = json.loads(line)
            if row.get('event') == 'viewer-frame':
                by.setdefault(row['tenant'], []).append(row)
    for rows in by.values():
        rows.sort(key=lambda r: r['atMs'])
    return by


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(p / 100 * len(s)) - 1))]


def join(writes, by_tenant, offset_ms=0):
    end = max((r['atMs'] for rows in by_tenant.values() for r in rows), default=None)
    out, rows = {d: {'lags': [], 'unmatched': 0, 'censored': 0, 'unviewed': 0} for d in DOMAINS}, []
    for tenant, domain, key, at, request in writes:
        series, bucket = by_tenant.get(tenant), out[domain]
        if not series:
            bucket['unviewed'] += 1
            continue
        times = [r['atMs'] for r in series]
        # Frames sent before the request started cannot reflect it (viewer clock).
        start = at - (request if isinstance(request, (int, float)) else 0) - offset_ms
        first = next((r for r in series[bisect.bisect_left(times, start):]
                      if r.get(domain) is not None and r[domain] >= key), None)
        if first is None:
            if end is None or end + offset_ms - at < DEADLINE_MS:
                bucket['censored'] += 1
            else:
                bucket['unmatched'] += 1
            continue
        lag = first['atMs'] + offset_ms - at
        bucket['lags'].append(lag)
        rows.append({'tenant': tenant, 'domain': domain, 'keyMs': key, 'acceptedAtMs': at, 'frameAtMs': first['atMs'], 'lagMs': lag})
    summary = {}
    for domain, b in out.items():
        lags = b['lags']
        summary[domain] = {'matched': len(lags), 'unmatched': b['unmatched'], 'censored': b['censored'], 'unviewed': b['unviewed'],
                           'p50Ms': pct(lags, 50), 'p95Ms': pct(lags, 95), 'p99Ms': pct(lags, 99), 'maxMs': max(lags) if lags else None,
                           'negative': sum(1 for v in lags if v < 0),
                           **{'within%dMs' % e: sum(1 for v in lags if v <= e) for e in EDGES_MS}}
    return summary, rows


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--k6', required=True, help='directory with k6.log or k6-shard-*.log')
    p.add_argument('--frames', required=True)
    p.add_argument('--run', required=True)
    p.add_argument('--offset-ms', type=int, default=0, help='driver clock minus viewer clock, measured')
    p.add_argument('--rows')
    a = p.parse_args(argv)
    folder = Path(a.k6)
    paths = sorted(folder.glob('k6-shard-*.log')) or [folder / 'k6.log']
    writes, counts = accepted([x for x in paths if x.is_file()], a.run)
    summary, rows = join(writes, frames(a.frames), a.offset_ms)
    if a.rows:
        with open(a.rows, 'x') as stream:
            for row in rows:
                stream.write(json.dumps(row) + '\n')
    json.dump({'version': 1, 'kind': 'm3-offline-latency-v1', 'runId': a.run, 'offsetMs': a.offset_ms,
               'offsetBasis': 'driver clock minus viewer clock; 0 means not measured or same host',
               'deadlineMs': DEADLINE_MS, 'driver': counts, 'domains': summary}, sys.stdout, indent=1)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
