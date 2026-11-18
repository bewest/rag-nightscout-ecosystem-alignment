import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import driver_shards as ds

IMAGE = 'sha256:' + 'f' * 64
BASE = ['docker', 'run', '--rm', '--name', 'p-k6', '--label', 'o=1', '--label', 'com.docker.compose.project=p',
        '--label', 'com.docker.compose.service=k6', '--network', 'host', '-v', '/x:/scripts:ro',
        '-e', 'TENANTS_FILE=/tenants.private.json', '-e', 'HOT_FACTOR=4', '-e', 'OFFERED_RPS=180',
        '-e', 'SHAPES=a', IMAGE, 'run', '--quiet', '--summary-export', '/out/k6-summary.json', '/scripts/workload.js']


class DriverShards(unittest.TestCase):
    def test_plan_preserves_total_weight_and_rate(self):
        rows = ds.plan(10000, 4, 180.0, 8)
        self.assertEqual(sum(r['tenants'] for r in rows), 10000)
        self.assertEqual(sum(r['weight'] for r in rows), 10000 - 1 + 4)
        self.assertAlmostEqual(sum(r['offeredRps'] for r in rows), 180.0)
        self.assertEqual([r['hotFactor'] for r in rows], [4] + [1] * 7)
        # Equal arrival cycle across shards: rate per weight is constant.
        self.assertEqual(len({round(r['offeredRps'] / r['weight'], 12) for r in rows}), 1)

    def test_plan_refusals(self):
        for args in [(10, 1, 60.0, 1), (10, 1, 60.0, 17), (3, 1, 60.0, 4),
                     (1000,1,0,2),(1000,1,True,2),(1000,1,float('inf'),2),(1000,1,float('nan'),2),
                     (1000,1,5e-324,16)]:
            with self.assertRaises(RuntimeError):
                ds.plan(*args)

    def test_fractional_rates_preserve_aggregate_and_each_shards_weight(self):
        for rate in (.25,1,12000):
            rows=ds.plan(1000,4,rate,8)
            self.assertAlmostEqual(sum(r['offeredRps'] for r in rows),rate)
            self.assertTrue(all(r['offeredRps']>0 for r in rows))
            self.assertEqual(len({round(r['offeredRps']/r['weight'],12) for r in rows}),1)

    def test_argv_rewrites_only_roster_hot_and_rate(self):
        rows = ds.plan(1000, 4, 180.0, 4)
        argv = ds.argv(BASE, IMAGE, rows, '/fixture/k6-shards')
        self.assertEqual(argv[:9], BASE[:9])
        self.assertNotIn('TENANTS_FILE=/tenants.private.json', argv)
        self.assertNotIn('OFFERED_RPS=180', argv)
        self.assertIn('SHAPES=a', argv)
        self.assertEqual(argv[argv.index(IMAGE) - 2:argv.index(IMAGE)], ['--entrypoint', 'sh'])
        self.assertEqual(argv[-2], '-c')
        self.assertEqual(argv[-1].count('k6 run --quiet'), 4)
        with self.assertRaises(RuntimeError):
            ds.argv(BASE[:-1], IMAGE, rows, '/f')
        subprocess.run(['sh', '-n', '-c', argv[-1]], check=True)

    def test_merge_semantics(self):
        rows = ds.plan(4, 1, 2.0, 2)
        one = {'metrics': {'c': {'count': 3, 'rate': 1.0, 'thresholds': {'count>=0': False}},
                           'r': {'passes': 1, 'fails': 3, 'value': .25},
                           't': {'count': 2, 'avg': 10, 'min': 5, 'max': 15, 'med': 10, 'p(95)': 15},
                           'g': {'value': 2, 'min': 0, 'max': 5},
                           'only': {'count': 1, 'rate': .1}}}
        two = {'metrics': {'c': {'count': 7, 'rate': 2.0, 'thresholds': {'count>=0': True}},
                           'r': {'passes': 0, 'fails': 4, 'value': 0},
                           't': {'count': 6, 'avg': 30, 'min': 20, 'max': 40, 'med': 30, 'p(95)': 39},
                           'g': {'value': 1, 'min': 0, 'max': 3}}, 'setup_data': {'jwts': ['secret']}}
        merged = ds.merge([one, two], rows)
        m = merged['metrics']
        self.assertEqual(m['c'], {'count': 10, 'rate': 3.0, 'thresholds': {'count>=0': True}})
        self.assertEqual(m['r']['value'], 1 / 8)
        self.assertEqual((m['t']['count'], m['t']['min'], m['t']['max'], m['t']['avg'], m['t']['p(95)']), (8, 5, 40, 25.0, 39))
        self.assertEqual(merged['m7DriverShards']['quantileBounds']['t']['p(95)'], [15, 39])
        self.assertEqual(m['g']['max'], 8)
        self.assertEqual(m['only']['count'], 1)
        self.assertNotIn('setup_data', merged)
        with self.assertRaises(RuntimeError):
            ds.merge([one, {'metrics': {'c': {'value': 1}}}], rows)

    def test_interpolation_and_nonuniform_samples_do_not_establish_pooled_bound(self):
        # Generic linearly interpolated percentiles, NOT a k6 algorithm claim.
        # These authored populations disprove the former unconditional label.
        def percentile(values, fraction):
            values = sorted(values); rank = (len(values) - 1) * fraction
            lower = int(rank); upper = min(lower + 1, len(values) - 1)
            return values[lower] + (values[upper] - values[lower]) * (rank - lower)
        def verify_label(value, pooled):
            method = value['m7DriverShards']
            if method.get('pooledPercentiles') != 'UNMEASURED':
                self.assertGreaterEqual(value['metrics']['t']['p(95)'], pooled,
                                        'FALSE_POOLED_PERCENTILE_BOUND')
            self.assertEqual(method['pooledPercentiles'], 'UNMEASURED')
            self.assertEqual(method['percentileMethod'], 'largest-shard-statistic')
        for populations in ([[0, 100], [0, 100]], [[0, 100], [0, 0, 100]]):
            parts = [{'metrics': {'attempts': {'count': len(v), 'rate': 1.0},
                                 't': {'count': len(v), 'avg': sum(v) / len(v),
                                       'min': min(v), 'max': max(v), 'p(95)': percentile(v, .95)}}}
                     for v in populations]
            pooled = percentile(sum(populations, []), .95)
            self.assertEqual(pooled, 100)
            merged = ds.merge(parts, ds.plan(sum(map(len, populations)), 1, 20.0, 2))
            self.assertEqual(merged['metrics']['t']['p(95)'], 95)
            self.assertEqual(merged['metrics']['attempts']['count'], sum(map(len, populations)))
            self.assertAlmostEqual(merged['metrics']['t']['avg'], sum(sum(v) for v in populations) / sum(map(len, populations)))
            verify_label(merged, pooled)
            broken = copy.deepcopy(merged);broken['m7DriverShards']['pooledPercentiles'] = 'UPPER_BOUND'
            with self.assertRaisesRegex(AssertionError, 'FALSE_POOLED_PERCENTILE_BOUND'):
                verify_label(broken, pooled)
            verify_label(merged, pooled)

    def test_collect_merges_only_when_every_shard_succeeded(self):
        rows = ds.plan(4, 1, 2.0, 2)
        summary = {'metrics': {'c': {'count': 1, 'rate': 1}}}
        with tempfile.TemporaryDirectory() as out:
            out = Path(out)
            for i in (0, 1):
                (out / ('k6-summary-%d.json' % i)).write_text(json.dumps(summary))
            (out / 'k6-shard-0.rc').write_text('0\n')
            (out / 'k6-shard-1.rc').write_text('137\n')
            self.assertFalse(ds.collect(out, rows)['merged'])
            self.assertFalse((out / 'k6-summary.json').exists())
            (out / 'k6-shard-1.rc').write_text('0\n')
            (out / 'k6-shards.json').unlink()
            self.assertTrue(ds.collect(out, rows)['merged'])
            self.assertEqual(json.loads((out / 'k6-summary.json').read_text())['metrics']['c']['count'], 2)


if __name__ == '__main__':
    unittest.main()
