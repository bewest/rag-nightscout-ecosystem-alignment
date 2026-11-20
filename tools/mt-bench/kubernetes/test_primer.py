"""Verify the host invocation preserves its original Pod, finite Job cutoff and private DATA projection."""
import asyncio
import json
import time
from pathlib import Path
import subprocess
import sys
import unittest

import primer


class PrimeEntry(unittest.TestCase):
    def test_fresh_cli_keeps_kubernetes_roster_separate_from_m7_adapter(self):
        here = Path(__file__).resolve().parent
        code = """
import sys
from pathlib import Path
site = Path(sys.argv[1])
sys.path[:0] = [str(site.parent/'m7-joined'), str(site)]
import adapter as m7
import primer
import experiment
assert Path(m7.__file__).parent.name == 'm7-joined'
assert Path(primer.k.__file__).parent == site
assert primer.k is experiment.k is experiment.execute.k
try:
    primer.require_roster(Path('/synthetic/packet'), {'primerOutput': None}, {})
except primer.k.Refused as error:
    assert str(error) == 'K8S_PRIMER_RECEIPT_REQUIRED'
else:
    raise AssertionError('Missing primer receipt did not fail')
"""
        subprocess.run([sys.executable, '-B', '-c', code, str(here)], check=True, capture_output=True)
        for entrypoint in ('experiment.py', 'adapter.py'):
            subprocess.run([sys.executable, '-B', str(here/entrypoint), '--help'], check=True, capture_output=True)

    def test_transport_budget_renews_on_durable_counts_only(self):
        def run(events, stall, work):
            lines = ['import time']
            for delay, frame in events:
                lines += [f'time.sleep({delay!r})', f'print({json.dumps(frame)!r}, flush=True)']
            return asyncio.run(primer.run_actor([sys.executable, '-c', '\n'.join(lines)],
                                                 time.time()+work, stall, 4, result))
        done = {'state':'synthetic-tenants-usable', 'tenants':4}
        advances = [(0, {'checkpoint':0})] + [(.16, {'checkpoint':i}) for i in range(1,5)]
        result = {}
        self.assertEqual(run(advances + [(0, done)], .4, 5), (done, 0))
        self.assertEqual(result['completedTenants'], 4)
        with self.assertRaisesRegex(primer.k.Refused, 'PRIMER_STALLED'):
            run(advances[:2] + [(.12, {'checkpoint':1})]*5, .4, 5)
        self.assertEqual(result['completedTenants'], 1)
        with self.assertRaisesRegex(primer.k.Refused, 'PRIMER_DEADLINE'):
            run(advances, 3, .4)
