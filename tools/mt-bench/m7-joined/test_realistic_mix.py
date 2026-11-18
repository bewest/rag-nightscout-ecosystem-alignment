import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import adapter
import discovery
import driver_shards
import workload


class RealisticMixTests(unittest.TestCase):
    def test_generated_scenarios_and_shard_cadence(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / 'workload.js'
            workload.generate(adapter.ROOT, script)
            # Only imports are mocked. k6 scenario options and tenant wheel are
            # evaluated from the actual generated source.
            inspect = r"""
const fs = require('fs'), vm = require('vm');
const [script, count, mix, offered] = process.argv.slice(1);
const env = {ACCEL: '1', HOT_FACTOR: '1', DURATION: '1800',
  SHAPES: 'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'};
if (mix !== '-') env.M7_WORKLOAD_MIX = mix;
if (offered !== '-') env.OFFERED_RPS = offered;
const context = {__ENV: env, SharedArray: function (_, fn) { return fn(); },
  open: () => JSON.stringify(Array.from({length: Number(count)}, (_, i) => ({id: i}))),
  Counter: class {}};
const source = fs.readFileSync(script, 'utf8').replace(/^import .*;$/gm, '').replace(/^export /gm, '');
console.log(JSON.stringify(vm.runInNewContext(source + '\noptions.scenarios;', context)));
"""
            def options(tenants, mix='realistic-v1', offered='-'):
                return json.loads(subprocess.check_output(
                    ['node', '-e', inspect, str(script), str(tenants), mix, offered], text=True))

            expected = {'w_sgv': 300000, 'w_devicestatus': 300000, 'w_treatments_v3': 1800000,
                        'r_sgv': 300000, 'r_devicestatus': 900000, 'r_treatments': 900000, 'r_status': 900000}
            for tenants in (1000, 10000):
                cadence = {'workloadMix': 'realistic-v1'}
                aggregate = {shape: 0 for shape in expected}
                for part in driver_shards.plan(tenants, 1, None, 8):
                    self.assertIsNone(part['offeredRps'])
                    for shape, row in options(part['tenants']).items():
                        unit_ms = int(row['timeUnit'].removesuffix('ms'))
                        self.assertEqual(unit_ms * part['tenants'] // row['rate'], expected[shape])
                        aggregate[shape] += 1000 * row['rate'] / unit_ms
                rates = adapter.rate_offer({'tenants': tenants, 'cadence': cadence})['scenarioRpsByShape']
                for shape, rate in rates.items():
                    self.assertAlmostEqual(aggregate[shape], rate)

            matched = options(1000, '-', '120')
            self.assertEqual(matched['r_sgv']['rate'], 5000)
            self.assertEqual(matched['w_treatments_v3']['rate'], 1000)
            self.assertEqual({row['timeUnit'] for row in matched.values()}, {'91667ms'})
            # Red: mixing an aggregate rate override with realistic-v1 would
            # silently change the fixed per-tenant load at one of the points.
            bad = subprocess.run(['node', '-e', inspect, str(script), '1000', 'realistic-v1', '120'],
                                 capture_output=True, text=True, check=False)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('M7_REALISTIC_MIX_CONFIGURATION', bad.stderr)
            self.assertEqual(options(1000)['w_treatments_v3']['timeUnit'], '1800000ms')

    def test_runner_passes_mix_through_existing_sharded_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'load').mkdir()
            (path / 'tenants.private.json').write_text(json.dumps([{'id': i} for i in range(1000)]))
            selection = SimpleNamespace(profile='pgstream-sample', run_purpose='discovery',
                                        workload_mix='realistic-v1', driver_shards=8, offered_rps=None)
            cadence = adapter.cadence_options(selection)
            manifest = {'cadence': cadence, 'project': 'local-fixture', 'port': 1, 'owner': 'a' * 32,
                        'settingsFingerprint': {'sha256': 'f' * 64}}
            command = discovery.k6_command(adapter, path, manifest, 'sha256:' + 'e' * 64, 'synthetic')
            self.assertIn('M7_WORKLOAD_MIX=realistic-v1', command)
            self.assertNotIn('OFFERED_RPS=', ' '.join(command))
            self.assertIn('k6-shard-7.log', command[-1])
            selection.offered_rps = 120
            with self.assertRaisesRegex(RuntimeError, 'M7_REALISTIC_MIX_CONFIGURATION'):
                adapter.cadence_options(selection)
