"""Pool retained k6 scenario timing samples on a 1 ms histogram."""

from collections import Counter
import math
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / 'm7-joined'))
import trace_files
from trace_files import TraceBound

MAX_MS = 120_000
MAX_TRACE_BYTES = 64 * 1024 * 1024


def budgets(plan=None):
    if plan is not None and not isinstance(plan, dict):
        raise ValueError('invalid driver trace plan')
    authored = plan or {}
    default_bytes = MAX_TRACE_BYTES if plan is None else trace_files.MAX_TRACE_BYTES
    cfg = dict(authored, maxTraceBytes=authored.get('maxTraceBytes', default_bytes),
               maxTraceRows=authored.get('maxTraceRows', trace_files.MAX_TRACE_ROWS))
    trace_files.validate(cfg, minimum_compressed=1)
    return cfg


def shard_histogram(path, expected, cfg):
    histogram = Counter()
    actual = Counter()
    with trace_files.reader(path, cfg) as (columns, rows):
        if not {"metric_name", "metric_value", "scenario"} <= set(columns or []):
            raise ValueError("missing k6 trace columns")
        for row in rows:
            if row["metric_name"] != "http_req_duration" or row["scenario"] == "":
                continue
            scenario = row["scenario"]
            actual[scenario] += 1
            if actual[scenario] > expected.get(scenario, 0):
                raise ValueError("extra scenario latency samples")
            value = float(row["metric_value"])
            if not math.isfinite(value) or value < 0:
                raise ValueError("invalid latency sample")
            histogram[min(math.ceil(value), MAX_MS + 1)] += 1
    if actual != Counter(expected):
        raise ValueError("missing scenario latency samples")
    return histogram


def pooled_histogram(shards, plan=None):
    cfg = budgets(plan)
    histogram = Counter()
    for path, expected in shards:
        histogram.update(shard_histogram(path, expected, cfg))
    n = sum(histogram.values())
    rank = (95 * n + 99) // 100
    for upper in sorted(histogram):
        rank -= histogram[upper]
        if rank <= 0:
            if upper > MAX_MS:
                raise ValueError("p95 in histogram overflow bucket")
            return upper, n
    return None, 0
