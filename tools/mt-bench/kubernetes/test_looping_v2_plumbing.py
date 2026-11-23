"""looping-v2 (AID client model) through the Kubernetes harness inputs: profile default, rates, validation."""
import copy
import unittest

import kube_adapter  # noqa: F401  (puts m7-joined on the path)
import plannable as p
import workload_runtime as runtime
import looping_driver
import looping_history
import looping_history_v2
from workloads import profile
import driver_accounting


def need(ok, code):
    if not ok:
        raise ValueError(code)


class LoopingV2(unittest.TestCase):
    BASE = {'version': 1, 'kind': 'k8s-m7-workload-profile', 'name': 'b', 'basis': 'x',
            'history': {'mode': 'synthetic-history-2d-v1', 'anchorUnixMs': 1}, 'phases': {'workSeconds': 7200},
            'workload': {'workloadMix': 'realistic-v1', 'loadSeconds': 1800},
            'population': {'hotFactor': 1, 'provisionedTenants': 1000, 'ordinaryRosterTenants': 1000}}

    def test_profile_defaults_to_looping_v2_on_either_looping_fixture(self):
        for mode in (p.LOOPING_2D, p.LOOPING_2D_V2):
            v = p.profile(copy.deepcopy(self.BASE), tenants=1000, history_mode=mode)
            self.assertEqual(v['workload']['driverShape'], 'looping-v2', mode)
            self.assertTrue(p.known_history(mode))
        v = p.profile(copy.deepcopy(self.BASE), tenants=1000, driver_shape='looping-v1')
        self.assertEqual(v['workload']['driverShape'], 'looping-v1')
        # v1 stays the default seed (tonight's 10k seed); v2 is its own key, chosen explicitly
        self.assertEqual(p.profile(copy.deepcopy(self.BASE), tenants=10)['history']['mode'], p.LOOPING_2D)
        with self.assertRaises(p.Refused):
            p.profile(copy.deepcopy(self.BASE), tenants=10, driver_shape='looping-v3')
        self.assertNotIn('driverShape', p.profile(copy.deepcopy(self.BASE), tenants=10,
                                                  history_mode='synthetic-history-2d-v1')['workload'])

    def test_rates_follow_the_driver(self):
        for spec in (looping_history.default_spec(1_763_683_200_000), looping_history_v2.default_spec(1_763_683_200_000)):
            w = {'workloadMix': 'realistic-v1', 'driverShape': 'looping-v2', 'loadSeconds': 1800}
            cycles, offer = runtime.rates(w, 1000, spec)
            want = looping_driver.offered(spec, 1000)['scenarios']
            for name, value in offer.items():
                self.assertAlmostEqual(value, want[name], places=3, msg=name)
            self.assertAlmostEqual(sum(offer.values()), 16.53, delta=0.05)
            w1 = dict(w, driverShape='looping-v1')
            self.assertLess(sum(runtime.rates(w1, 1000, looping_history.default_spec(1_763_683_200_000))[1].values()), 14.2)

    def test_validation_and_environment(self):
        w = {'workloadMix': 'realistic-v1', 'driverShape': 'looping-v2', 'loadSeconds': 1800, 'logicalPollingClients': 0,
             'probeEveryMs': 300000}
        env = runtime.environment(w, {}, need)
        self.assertEqual(env['M7_DRIVER_SHAPE'], 'looping-v2')
        self.assertIn('M7_LOOPING_V2_RULES', env)
        self.assertFalse(any(k.startswith('M7_BACKLOG') for k in env))
        with self.assertRaisesRegex(ValueError, 'WORKLOAD_DRIVER_SHAPE'):
            runtime.validate(dict(w, driverShape='looping-backlog-v1'), need)

    def test_active_prefix_uses_client_kinds_from_the_whole_seed(self):
        base = profile.read(profile.HERE / 'realistic-1000.json')
        base['history'] = looping_driver.reference_spec_v2()
        base['population'].update(provisionedTenants=100, ordinaryRosterTenants=100)
        traffic = base['workload']
        traffic.update(driverShape='looping-v2', viewerSetup={'mix': runtime.viewer_plan.MIX_PRESETS['followers-v1']},
                       driverPlan={'version': 1, 'observer': 'scheduling-v1',
                                   'scenarios': {name: {} for name in runtime.SHAPES}})
        phase = profile.active_profile(base, 47, 'partial')
        self.assertEqual(phase['history'], base['history'])
        self.assertEqual(base['population']['ordinaryRosterTenants'], 100)
        self.assertEqual(phase['workload']['pointId'], 'partial')
        explained = profile.describe(phase)
        config = dict(tenants=100, ordinaryRosterTenants=47, history=base['history'], workload=phase['workload'],
                      roles=['api'], pins=dict(pair={}, appImageId='test', instrument='test'))
        full = [{'host': f't-{i:03}.test', 'id': str(i)} for i in reversed(range(100))]
        selected = runtime.ordinary_roster(config, full, need)
        self.assertEqual([row['id'] for row in selected], [str(i) for i in range(47)])
        self.assertEqual(runtime.viewer_roster(config, full, need), selected)
        self.assertEqual(explained['stockViewers'], sum(runtime.viewer_plan.mix_counts(traffic['viewerSetup']['mix'], 47)))
        seeded = looping_driver.annotate(base['history'], full, selected)
        kinds = [row['loopKind'] for row in seeded]
        expected = {'w_treatments_v3': 47 - kinds.count(None),
                    'w_devicestatus': 20 * 47 + 7 * kinds.count('loop') + 20 * kinds.count('trio')}
        plan, = driver_accounting.expected_plans(runtime.driver_manifest(config))
        for shape, count in expected.items():
            self.assertEqual(plan['scenarios'][shape]['rate'], count)
            self.assertEqual(explained['shapeRequestsPerSecond'][shape], plan['scenarios'][shape]['perSecond'])


if __name__ == '__main__':
    unittest.main()
