"""Read the retained 10k scheduling trace with its actual budgets and plan."""
import json
from pathlib import Path
import sys
import unittest

import trace_bounds

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'm7-joined'))
PACKET = Path('/mnt/data/nightscout-workspace/artifacts/inc8898-20261122/k8s/w2/cases/r10k-w7-k20/runtime/packet/load')


class Bounds(unittest.TestCase):
    @unittest.skipUnless((PACKET / 'driver-plans.json').is_file(), 'retained r10k-w7-k20 packet not mounted')
    def test_retained_10k_trace_reconciles_under_the_planned_budgets(self):
        import driver_accounting as driver

        packet = json.loads((PACKET / 'driver-plans.json').read_text())
        manifest = packet['manifest']
        cadence = manifest['cadence']
        derived = trace_bounds.bound_plan(cadence, manifest['tenants'], manifest.get('provisionedTenants'),
                                          manifest['history'])
        cfg = driver.configuration(derived, cadence)
        self.assertEqual(cfg['maxTraceRows'], 8_500_000)
        self.assertEqual(cfg['maxTraceBytes'], 64 * 1024**2)
        self.assertEqual(driver.decoded_trace_bytes(cfg), 1024**3)
        self.assertEqual(driver.reduce_shard(PACKET, packet['plans'][0], cfg)['totals']['issued'], 288_597)


if __name__ == '__main__':
    unittest.main()
