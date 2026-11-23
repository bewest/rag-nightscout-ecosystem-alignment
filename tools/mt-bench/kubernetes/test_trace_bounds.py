"""Scale-derived driver trace bounds, and the retained r10k-w7-k20 trace against the real trace_assess (skipped without it)."""
import json
import sys
import unittest
from pathlib import Path

import trace_bounds as tb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'm7-joined'))
PACKET = Path('/mnt/data/nightscout-workspace/artifacts/inc8898-20261122/k8s/w2/cases/r10k-w7-k20/runtime/packet/load')


class Bounds(unittest.TestCase):
    def test_the_10k_run_that_overran_gets_room(self):
        # offered.json: 165.2 req/s, plan 297,405 iterations over 1,800 s; measured 6,354,900 rows.
        b = tb.scaled_bounds(165.225, 1800)
        self.assertGreaterEqual(b['maxTraceRows'], 8000000)
        self.assertGreater(b['maxTraceRows'], 6354900)
        self.assertEqual(b['maxTraceRows'], 8500000)
        self.assertEqual(b['maxTraceBytes'], 64 * 1024 ** 2, 'not over 1,800 s')

    def test_longer_runs_get_128_mib(self):
        self.assertEqual(tb.scaled_bounds(165.225, 2400)['maxTraceBytes'], 128 * 1024 ** 2)
        self.assertEqual(tb.scaled_bounds(165.225, 1801)['maxTraceBytes'], 128 * 1024 ** 2)

    def test_small_scale_keeps_the_profile_value_and_the_base_is_not_edited(self):
        self.assertEqual(tb.scaled_bounds(16.5, 1800), {'maxTraceRows': 5000000, 'maxTraceBytes': 64 * 1024 ** 2})
        base = {'workload': {'driverPlan': {'maxTraceRows': 5000000, 'maxTraceBytes': 64 * 1024 ** 2}}}
        profile = json.loads(json.dumps(base))
        tb.apply(profile, 165.225, 2400)
        self.assertEqual(profile['workload']['driverPlan'], {'maxTraceRows': 11000000, 'maxTraceBytes': 128 * 1024 ** 2})
        self.assertEqual(base['workload']['driverPlan']['maxTraceRows'], 5000000)
        profile['workload']['driverPlan']['maxTraceRows'] = 9000000
        self.assertEqual(tb.scaled_bounds(165.225, 1800, 9000000)['maxTraceRows'], 9000000, 'never lowered below the profile')

    @unittest.skipUnless((PACKET / 'driver-plans.json').is_file(), 'retained r10k-w7-k20 packet not mounted')
    def test_trace_assess_refuses_the_1k_bound_and_passes_the_derived_one_on_the_retained_trace(self):
        import driver_accounting as da
        plans = json.loads((PACKET / 'driver-plans.json').read_text())
        cadence = plans['manifest']['cadence']
        derived = tb.scaled_bounds(165.225, cadence['loadSeconds'])
        def run(**bounds):
            cfg = da.configuration(dict(cadence['driverPlan'], **bounds), cadence)
            return da.reduce_shard(PACKET, plans['plans'][0], cfg)
        with self.assertRaisesRegex(RuntimeError, 'M7_DRIVER_TRACE_BOUND'):
            run(maxTraceRows=5000000, maxTraceBytes=64 * 1024 ** 2)
        self.assertEqual(run(**derived)['totals']['issued'], 288597, 'every row read and reconciled')


if __name__ == '__main__':
    unittest.main()
