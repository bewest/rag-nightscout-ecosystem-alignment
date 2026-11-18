import csv
import gzip
from pathlib import Path
import tempfile
import unittest

from latency import pooled_histogram


def trace(path, values):
    with gzip.open(path, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("metric_name", "metric_value", "scenario"))
        writer.writerow(("http_req_duration", "99999", ""))
        writer.writerows(("http_req_duration", value, "r_sgv") for value in values)
    return path


class PoolingTests(unittest.TestCase):
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
