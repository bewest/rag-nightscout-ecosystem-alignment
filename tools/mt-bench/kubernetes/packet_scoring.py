"""Offline scoring of a retained load packet (lane harness-reliability, 2026-11-23).

One home for the figures the round's scoring scripts (w2/measure.py, extra.py) and coverage_verdict share:

  * counter_delta     per-series growth between the load start and the end that counts a series born after the start
                      from 0. The old forms dropped it: `X @ end - X @ start` matches series by label and discards a
                      series absent at the start; `increase(X[w])` ignores the first sample of a series born inside the
                      window. Both undercount at K >= 2 (an evaluator whose first consumer pass lands after load start)
                      and read `{}`/null when every series is born late (api 5xx, consumer refusals).
  * histogram_delta   the same for a histogram's buckets, keyed by the numeric `le` (the exporter writes "30.0").
  * load_window       window.json, or, for an early-stop packet, a window read from the driver's scheduling trace.
  * end_read          progress-after.json, or progress-stop.json taken when the run stopped early.
  * viewer_m3         M3 (accepted write -> delivered viewer frame): p50/p95/p99 and the share under the 4/10/30 s bands
                      (latency_oracle.overall), for a packet with no m3-latency.json.

QUERY is `query(expr, at_seconds) -> [{'labels': {...}, 'value': float|None}]`, the shape of
case_observer.LocalPrometheus.query.
"""
import csv
import gzip
import json
import math
from pathlib import Path


def _read(path):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, ValueError):
        return None


def _key(labels):
    return tuple(sorted((k, v) for k, v in labels.items() if k != '__name__'))


def _by_series(rows):
    return {_key(r['labels']): r['value'] for r in rows if r.get('value') is not None}


def counter_delta(query, selector, start_s, end_s):
    """[{'labels', 'value'}] per series: the last sample at or before END_S minus the sample at START_S, a series absent
    at the start counting from 0. A series that reset inside the window uses increase(), which is exact across a reset.
    A series with no sample at the end is omitted."""
    w = max(1, int(math.ceil(end_s - start_s)) + 1)
    end = _by_series(query('last_over_time(%s[%ds])' % (selector, w), end_s))
    start = _by_series(query(selector, start_s))
    resets = _by_series(query('resets(%s[%ds])' % (selector, w), end_s))
    grown = _by_series(query('increase(%s[%ds])' % (selector, w), end_s))
    rows = []
    for key, value in end.items():
        delta = (grown.get(key) or 0) if resets.get(key) else value - (start.get(key) or 0)
        rows.append({'labels': dict(key), 'value': delta})
    return rows


def total(rows):
    """Sum of a counter_delta result, or None when no series exists (an image without the metric is not zero)."""
    return sum(r['value'] for r in rows) if rows else None


def sum_by(rows, label):
    out = {}
    for r in rows:
        k = r['labels'].get(label, '')
        out[k] = out.get(k, 0) + r['value']
    return out


def histogram_delta(query, metric, start_s, end_s, selector=''):
    """{le(float): cumulative count} summed over series, from counter_delta of METRIC_bucket."""
    buckets = {}
    for r in counter_delta(query, metric + '_bucket' + selector, start_s, end_s):
        le = float(str(r['labels'].get('le', '+Inf')).replace('+Inf', 'inf'))
        buckets[le] = buckets.get(le, 0) + r['value']
    return dict(sorted(buckets.items()))


def histogram_quantile(buckets, q):
    """Prometheus histogram_quantile over {le: cumulative count}."""
    if not buckets or math.inf not in buckets or buckets[math.inf] <= 0:
        return None
    rank, count = q * buckets[math.inf], buckets[math.inf]
    prev_le, prev_n = 0.0, 0.0
    for le, n in buckets.items():
        if n >= rank:
            if le == math.inf:
                return prev_le
            return prev_le + (le - prev_le) * (rank - prev_n) / (n - prev_n) if n > prev_n else le
        prev_le, prev_n = le, n
    return prev_le


def over_bound(buckets, bound):
    """Observations above BOUND (seconds): +Inf minus the bucket whose numeric le equals BOUND, so "30" and "30.0" agree.
    None when the histogram has no such bucket."""
    if math.inf not in buckets:
        return None
    for le, n in buckets.items():
        if le == float(bound):
            return buckets[math.inf] - n
    return None


def trace_window(trace, load_seconds=None):
    """(first m7_driver_started, end) in seconds from a k6 scheduling trace. The end is the start plus LOAD_SECONDS when
    given, else the last timestamp in the trace."""
    first = last = None
    with gzip.open(trace, 'rt', newline='') as source:
        for row in csv.DictReader(source):
            try:
                at = int(row['timestamp'])
            except (KeyError, ValueError):
                continue
            last = at if last is None or at > last else last
            if row.get('metric_name') == 'm7_driver_started' and (first is None or at < first):
                first = at
    if first is None:
        return None
    return first / 1000, (first / 1000 + load_seconds) if load_seconds else last / 1000


def load_window(load):
    """The load window of a retained load stage. window.json when the run reached it. Otherwise an early-stop packet
    (progress-stop.json present) reads its window explicitly from the scheduling trace: the load starts at the first
    m7_driver_started row, lasts the manifest's loadSeconds (driver-plans.json) or to the last trace row, and the end read
    is the stop read. The result says so (`basis`); a figure from such a window is read-derived. None when neither exists."""
    load = Path(load)
    window = _read(load / 'window.json')
    if window and window.get('loadStartedAt'):
        return {**window, 'basis': 'window.json'}
    stop, trace = _read(load / 'progress-stop.json'), load / 'k6-scheduling.csv.gz'
    if not stop or not trace.is_file() or not stop.get('readAtMs'):
        return None
    plans = _read(load / 'driver-plans.json') or {}
    seconds = ((plans.get('manifest') or {}).get('cadence') or {}).get('loadSeconds')
    found = trace_window(trace, seconds if isinstance(seconds, int) else None)
    if not found:
        return None
    return {'loadStartedAt': found[0], 'loadEndedAt': found[1], 'endedAt': stop['readAtMs'] / 1000,
            'basis': 'early-stop: trace-derived load window, progress-stop.json end read', 'earlyStop': True}


def end_read(load):
    """(document, file name) of the end read: progress-after.json, else progress-stop.json from an early stop."""
    load = Path(load)
    for name in ('progress-after.json', 'progress-stop.json'):
        doc = _read(load / name)
        if doc:
            return doc, name
    return {}, None


def viewer_m3(load, run=None, offset_ms=0):
    """M3 (accepted write -> delivered viewer frame) from a retained load stage that has k6.log and viewer-frames.jsonl but
    no m3-latency.json (an early stop). Same oracle as the after-run join. {'domains', 'overall'}; None without a ledger."""
    import sys
    load = Path(load)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'm7-joined'))
    import latency_oracle
    if not (load / 'viewer-frames.jsonl').is_file():
        return None
    run = run or (load / 'runid').read_text().strip()
    paths = sorted(load.glob('k6-shard-*.log')) or [load / 'k6.log']
    writes, counts = latency_oracle.accepted([p for p in paths if p.is_file()], run)
    summary, rows = latency_oracle.join(writes, latency_oracle.frames(load / 'viewer-frames.jsonl', run), offset_ms)
    return {'run': run, 'offsetMs': offset_ms, 'driver': counts, 'domains': summary, 'overall': latency_oracle.overall(summary, rows)}
