"""Offline latency observation (lane mt-plannable-scale-20261121, E3): profile switch and the after-run M3 join."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'm7-joined'))
import execute
import workload_runtime
from test_latency_oracle import k6_line, frame  # noqa: E402


def need(ok, code):
    if not ok:
        raise AssertionError(code)


class OfflineLatency(unittest.TestCase):
    def test_capacity_profiles_select_offline_and_smoke_keeps_polling(self):
        root = Path(__file__).resolve().parent / 'workloads'
        for name in ('realistic-500', 'realistic-1000', 'realistic-3000'):
            self.assertEqual(json.loads((root / (name + '.json')).read_text())['workload'].get('latencyObservation'), 'offline-v1', name)
        for name in ('small', 'stress-discovery', 'representative-mix'):
            self.assertNotIn('latencyObservation', json.loads((root / (name + '.json')).read_text())['workload'], name)

    def test_setting_values(self):
        base = {'loadSeconds': 60, 'offeredRps': 1, 'logicalPollingClients': 1, 'probeEveryMs': 1000}
        for value in ('polling-sql-v1', 'offline-v1'):
            workload_runtime.validate({**base, 'latencyObservation': value}, need)
        with self.assertRaises(AssertionError):
            workload_runtime.validate({**base, 'latencyObservation': 'live'}, need)

    def test_after_run_join_and_missing_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / 'k6.log').write_text(k6_line('tenant-a', 'entries', '1000000', 5000, run='r'))
            (out / 'viewer-frames.jsonl').write_text(frame('tenant-a', 5900, entries=1000000))
            observer = execute.OfflineLatency('r')
            observer.start(); observer.finish(out, drain_end=0); observer.close()
            doc = json.loads((out / 'm3-latency.json').read_text())
            self.assertEqual(doc['domains']['entries']['p50Ms'], 900)
            self.assertFalse(json.loads((out / 'latency-observation.json').read_text())['liveSqlObserver'])
        with tempfile.TemporaryDirectory() as d:
            execute.offline_latency_oracle(Path(d), 'r')
            self.assertEqual(json.loads((Path(d) / 'm3-latency.json').read_text())['code'], 'K8S_M3_FRAME_LEDGER_MISSING')


if __name__ == '__main__':
    unittest.main()
