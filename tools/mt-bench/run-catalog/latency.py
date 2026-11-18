"""Pool retained k6 scenario timing samples on a 1 ms histogram."""

from collections import Counter
import csv
import gzip
import math

MAX_MS = 120_000
MAX_TRACE_BYTES = 64 * 1024 * 1024


def shard_histogram(path, expected):
    histogram = Counter()
    actual = Counter()
    with gzip.open(path, "rt", newline="") as source:
        reader = csv.DictReader(source)
        if not {"metric_name", "metric_value", "scenario"} <= set(reader.fieldnames or []):
            raise ValueError("missing k6 trace columns")
        for row in reader:
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


def pooled_histogram(shards):
    histogram = Counter()
    for path, expected in shards:
        histogram.update(shard_histogram(path, expected))
    n = sum(histogram.values())
    rank = (95 * n + 99) // 100
    for upper in sorted(histogram):
        rank -= histogram[upper]
        if rank <= 0:
            if upper > MAX_MS:
                raise ValueError("p95 in histogram overflow bucket")
            return upper, n
    return None, 0
