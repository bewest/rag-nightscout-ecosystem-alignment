import csv
import gzip
from pathlib import Path
import tempfile
import unittest

from latency import pooled_histogram
from retained import Evidence, pooled_signal
from unittest.mock import patch


def trace(path, values):
    with gzip.open(path, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("metric_name", "metric_value", "scenario"))
        writer.writerow(("http_req_duration", "99999", ""))
        writer.writerows(("http_req_duration", value, "r_sgv") for value in values)
    return path


class PoolingTests(unittest.TestCase):
    def test_catalog_uses_each_shards_retained_trace_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            files = [trace(root / f"k6-scheduling-{index}.csv.gz", [10] * 2) for index in range(2)]
            sizes = [path.stat().st_size for path in files]
            decoded = [len(gzip.decompress(path.read_bytes())) for path in files]
            driver = {"shards": [{"plan": {"observer": "scheduling-v1", "shardIndex": index},
                                  "byScenario": {"r_sgv": {"completed": 2}}} for index in range(2)]}
            plan = {"maxTraceBytes": max(sizes), "maxDecodedTraceBytes": max(decoded), "maxTraceRows": 3}
            configured = {"driverShards": 2, "driverPlan": plan}
            # Force the legacy total-file ceiling below the sum without producing large fixtures.
            with patch("latency.MAX_TRACE_BYTES", max(sizes)):
                evidence = Evidence(root)
                self.assertEqual(pooled_signal(evidence, driver, configured, ".")[:2], (10, 4))
                self.assertEqual(evidence.issues, [])
            for key in plan:
                with self.subTest(key=key):
                    changed = dict(configured, driverPlan=plan | {key: plan[key] - 1})
                    evidence = Evidence(root)
                    self.assertIsNone(pooled_signal(evidence, driver, changed, "."))
                    self.assertEqual(evidence.issues[0]["code"], "LATENCY_TRACE_BUDGET")

    def test_pool_weights_samples_instead_of_averaging_shard_p95(self):
        with tempfile.TemporaryDirectory() as temp:
            fast = trace(Path(temp) / "fast.csv.gz", [9.2] * 96)
            slow = trace(Path(temp) / "slow.csv.gz", [1000.0] * 4)
            shards = [(fast, {"r_sgv": 96}), (slow, {"r_sgv": 4})]
            self.assertEqual(pooled_histogram(shards), (10, 100))
            per_shard = [pooled_histogram([shard])[0] for shard in shards]
            self.assertEqual(per_shard, [10, 1000])
            self.assertNotEqual(sum(per_shard) / len(per_shard), 10)
            with self.assertRaisesRegex(ValueError, "missing scenario latency samples"):
                pooled_histogram([(fast, {"r_sgv": 97}), shards[1]])
