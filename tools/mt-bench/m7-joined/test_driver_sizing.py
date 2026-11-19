"""Decision driver-sized-from-offer: the k6 scenario plan that workload.js renders (offline, node vm)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import adapter
import workload

JS = r'''
const fs=require('fs'),vm=require('vm');const [script,count,env]=process.argv.slice(1);
const context={__ENV:JSON.parse(env),exec:{scenario:{}},console:{log(){}},SharedArray:function(_,fn){return fn();},
  open:()=>JSON.stringify(Array.from({length:Number(count)},(_,id)=>({id}))),Counter:class{}};
const text=fs.readFileSync(script,'utf8').replace(/^import .*;$/gm,'').replace(/^export /gm,'');
console.log(JSON.stringify(vm.runInNewContext(text+'\noptions.scenarios',context)));
'''
SHAPES = 'w_sgv,w_devicestatus,w_treatments_v3,r_sgv,r_devicestatus,r_treatments,r_status'


class DriverSizing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.script = Path(self.tmp.name) / 'workload.js'
        workload.generate(adapter.ROOT, self.script)

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, tenants, headroom=None, **extra):
        env = {'ACCEL': '1', 'HOT_FACTOR': '1', 'DURATION': '600', 'SHAPES': SHAPES, **extra}
        if headroom is not None:
            env['DRIVER_HEADROOM'] = str(headroom)
        if 'OFFERED_RPS' not in env:
            env['M7_WORKLOAD_MIX'] = 'realistic-v1'
        result = subprocess.run(['node', '-e', JS, str(self.script), str(tenants), json.dumps(env)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)
        scenarios = json.loads(result.stdout)
        return (sum(s['preAllocatedVUs'] for s in scenarios.values()),
                sum(s['maxVUs'] for s in scenarios.values()), scenarios)

    def test_decision_totals_at_kubernetes_headroom(self):
        # Totals recorded with the decision (H=2), realistic-v1.
        self.assertEqual(self.plan(1000, 2)[:2], (14, 144))
        self.assertEqual(self.plan(10000, 2)[:2], (72, 1394))
        # The rendered per-operation plan, which differs slightly from the decision's arithmetic
        # (26 / 422 and 122 / 2,400): at 3,000 tenants three operations offer exactly 10 req/s.
        self.assertEqual(self.plan(3000, 2)[:2], (23, 419))
        self.assertEqual(self.plan(1000, 2, M7_WORKLOAD_SCALE=str(240 / (1000 * 50 / 3600)))[:2], (122, 2405))

    def test_each_operation_follows_the_formula_with_floors(self):
        pre, maximum, scenarios = self.plan(1000, 2)
        row = scenarios['w_treatments_v3']  # 0.56 req/s: the preallocation floor applies
        self.assertEqual((row['preAllocatedVUs'], row['maxVUs']), (2, 6))
        row = scenarios['w_sgv']  # 3.33 req/s
        self.assertEqual((row['preAllocatedVUs'], row['maxVUs']), (2, 34))

    def test_platform_default_and_override(self):
        local = self.plan(1000)[:2]  # unset: local Compose H=1.5
        self.assertEqual(local, self.plan(1000, 1.5)[:2])
        self.assertLess(local[1], self.plan(1000, 2)[1])
        for bad in ('0', '-1', 'NaN', 'x', '1000'):
            with self.assertRaisesRegex(RuntimeError, 'M7_DRIVER_HEADROOM_RANGE'):
                self.plan(1000, bad)

    def test_harnesses_pass_their_platform_default(self):
        sys.path.append(str(adapter.HERE.parent / 'kubernetes'))
        import workload_runtime
        import driver_accounting
        w = {'loadSeconds': 600, 'workloadMix': 'realistic-v1', 'logicalPollingClients': 16, 'probeEveryMs': 30000}
        env = workload_runtime.environment(w, {}, adapter.require)
        self.assertEqual(env['DRIVER_HEADROOM'], '2.0')
        self.assertEqual(workload_runtime.environment(w | {'driverHeadroom': 3}, {}, adapter.require)['DRIVER_HEADROOM'], '3.0')
        self.assertEqual(driver_accounting.headroom({}), 1.5)
        self.assertEqual(driver_accounting.headroom({'driverHeadroom': 2.5}), 2.5)


if __name__ == '__main__':
    unittest.main()
