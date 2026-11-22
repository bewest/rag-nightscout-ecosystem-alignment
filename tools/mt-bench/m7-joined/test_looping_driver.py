"""Driver shape looping-v1: the generated k6 workload evaluated in node with only k6 imports mocked."""
import json
import random
import subprocess
import tempfile
import unittest
from pathlib import Path

import adapter
import looping_driver
import looping_history
import workload

SPEC = looping_history.default_spec(1_763_683_200_000)
INSPECT = r"""
const fs = require('fs'), vm = require('vm');
const [script, tenantsFile, envJson, calls] = process.argv.slice(1);
const env = Object.assign({ACCEL: '1', HOT_FACTOR: '1', DURATION: '1800', RUN_ID: 'run-x', RUN_START: '1763683200000',
  BASE_URL: 'http://api.test', M7_WORKLOAD_MIX: 'realistic-v1',
  SHAPES: 'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'}, JSON.parse(envJson));
const posts = [];
const scenario = {name: '', iterationInTest: 0, startTime: 0};
class Counter { add () {} }
const http = {post: (url, body) => { posts.push({url, body}); return {status: 200}; }, get: () => ({status: 200}),
  expectedStatuses: () => null};
const context = {__ENV: env, SharedArray: function (_, fn) { return fn(); }, open: () => fs.readFileSync(tenantsFile, 'utf8'),
  Counter, http, exec: {scenario}, console: {log () {}}};
const source = fs.readFileSync(script, 'utf8').replace(/^import .*;$/gm, '').replace(/^export /gm, '');
const run = vm.runInNewContext(source + '\n({options, w_devicestatus, w_treatments_v3, w_sgv});', context);
for (const [name, n] of JSON.parse(calls)) for (let i = 0; i < n; i++) { scenario.name = name; scenario.iterationInTest = i; run[name](); }
console.log(JSON.stringify({scenarios: run.options.scenarios, posts}));
"""


def roster(n):
    rows = [{'id': '%08d-0000-4000-8000-000000000000' % i, 'host': 't%05d.test' % i, 'token': 'synthetic'} for i in range(n)]
    random.Random(7).shuffle(rows)  # roster order is not host order
    return rows


class LoopingDriver(unittest.TestCase):
    def evaluate(self, tenants, env, calls=()):
        with tempfile.TemporaryDirectory() as d:
            script, path = Path(d) / 'workload.js', Path(d) / 'tenants.json'
            workload.generate(adapter.ROOT, script)
            path.write_text(json.dumps(tenants))
            result = subprocess.run(['node', '-e', INSPECT, str(script), str(path), json.dumps(env), json.dumps(list(calls))],
                                    capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads(result.stdout)

    def test_roles_follow_the_seed_in_host_order(self):
        rows = roster(50)
        annotated = looping_driver.annotate(SPEC, rows, rows)
        roles = looping_history.roles(SPEC, 50)
        for row in annotated:
            i = int(row['host'][1:6])
            self.assertEqual(row['loopKind'] is None, roles[i] == 'cgm-only', row['host'])
            if row['loopKind']:
                self.assertEqual(row['loopKind'], looping_history.kind(SPEC, i))
        self.assertEqual(sum(r['loopKind'] is None for r in annotated), 10)

    def test_scenarios_bodies_and_rate(self):
        rows = looping_driver.annotate(SPEC, roster(1000), roster(1000))
        looping = [r for r in rows if r['loopKind']]
        out = self.evaluate(rows, looping_driver.environment(), [('w_devicestatus', looping_driver.ROTATION * len(looping)), ('w_treatments_v3', 3), ('w_sgv', 2)])
        s = out['scenarios']
        unit = {k: int(v['timeUnit'].removesuffix('ms')) for k, v in s.items()}
        self.assertEqual((s['w_devicestatus']['rate'], unit['w_devicestatus']), (len(looping), 300000))
        self.assertEqual((s['w_treatments_v3']['rate'], unit['w_treatments_v3']), (len(looping), looping_driver.treatment_cycle_ms()))
        self.assertEqual(s['w_sgv']['rate'], 1000)
        total = sum(1000 * v['rate'] / unit[k] for k, v in s.items())
        self.assertAlmostEqual(total, 14.08, delta=0.02)  # E1: 14.09 with CGM-only treatments (0.009) not driven
        ds = [p for p in out['posts'] if '/devicestatus' in p['url']]
        hosts = {r['token'] for r in looping}
        bodies = [json.loads(p['body'])[0] for p in ds]
        self.assertTrue(all(b['device'] == 'run-x' for b in bodies))
        self.assertFalse(any(looping_driver.PLACEHOLDER in p['body'] for p in ds))
        self.assertTrue(all(b['created_at'] != looping_driver.PLACEHOLDER for b in bodies))
        mean = sum(len(p['body']) for p in ds) / len(ds)
        docs, _ = looping_driver.templates()
        expected = sum(sum(map(len, docs[r['loopKind']])) / len(docs[r['loopKind']]) for r in looping) / len(looping)
        self.assertAlmostEqual(mean, expected - 40, delta=15, msg='LOOP_SIZED_BODIES')  # device: run id (5 B) for the fixture marker (about 45 B), plus brackets
        self.assertGreater(mean, 1500)  # realistic-v1 body: about 760 bytes
        self.assertEqual(len({b['created_at'] for b in bodies}), len(bodies))
        self.assertTrue(hosts)

    def test_devicestatus_never_reaches_cgm_only_tenants(self):
        rows = looping_driver.annotate(SPEC, roster(20), roster(20))
        cgm = {r['token'] + r['host'] for r in rows if r['loopKind'] is None}
        tokens = {}
        for i, r in enumerate(rows):
            r['token'] = 'tok%02d' % i
            tokens[r['token']] = r['loopKind']
        out = self.evaluate(rows, looping_driver.environment(), [('w_devicestatus', 40), ('w_treatments_v3', 40), ('w_sgv', 20)])
        touched = lambda kind: {p['url'].split('token=')[1] for p in out['posts'] if kind in p['url'] and 'token=' in p['url']}
        self.assertTrue(cgm)
        self.assertTrue(all(tokens[t] is not None for t in touched('/devicestatus')), 'DEVICESTATUS_TO_CGM_ONLY')
        self.assertEqual(len(touched('/entries')), 20)

    def test_refusals(self):
        rows = roster(10)
        for bad_rows, env in ((rows, looping_driver.environment()),                      # roles missing
                              (looping_driver.annotate(SPEC, rows, rows), {**looping_driver.environment(), 'M7_DRIVER_PLAN': '{}'}),
                              (looping_driver.annotate(SPEC, rows, rows), {**looping_driver.environment(), 'M7_DRIVER_SHAPE': 'other'})):
            with self.assertRaises(RuntimeError) as caught:
                self.evaluate(bad_rows, env)
            self.assertIn('M7_DRIVER_SHAPE_CONFIGURATION', str(caught.exception))

    def test_default_is_unchanged(self):
        rows = roster(100)
        s = self.evaluate(rows, {})['scenarios']
        self.assertEqual((s['w_devicestatus']['rate'], s['w_treatments_v3']['timeUnit']), (100, '1800000ms'))


if __name__ == '__main__':
    unittest.main()
