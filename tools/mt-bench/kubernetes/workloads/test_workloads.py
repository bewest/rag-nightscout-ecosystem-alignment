"""Meaningful coverage controls for finite workload inputs and retained reductions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workloads import profile as profiles
from workloads import reduce as reduction


class Coverage(unittest.TestCase):
    def test_source_repin_is_not_silently_accepted(self):
        p = profiles.read(profiles.HERE / 'small.json')
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        stamp = lambda seconds: (now + timedelta(seconds=seconds)).isoformat().replace('+00:00', 'Z')
        config = {'tenants': 2, 'pins': {'pair': {k: p['referencePins'][k] for k in ('core', 'deploy')},
                   'bindingCommit': p['referencePins']['bindingCommit']},
                  'driver': {'resources': {'millicpus': 500, 'memoryBytes': 512 * 1024**2}},
                  'observer': {'resources': {'millicpus': 500, 'memoryBytes': 512 * 1024**2}},
                  'deadlines': {'workUntil': stamp(1800), 'cleanupUntil': stamp(2400)}}
        self.assertEqual(profiles.bind(p, config)['workload'], p['workload'])
        selected={'roundSeconds':90,'sqlMaxBytes':64*1024**2}
        p['workload']['drainObservation']=selected
        observer=copy.deepcopy(config);observer['workload']={'drainObservation':selected}
        self.assertEqual(profiles.bind(p,observer)['workload']['drainObservation'],selected)
        observer['workload']['drainObservation']={'roundSeconds':20}
        with self.assertRaisesRegex(ValueError,'K8S_LOAD_DRAIN_OBSERVATION_CHANGED'):
            profiles.bind(p,observer)
        observer['workload']['drainObservation']=selected
        self.assertEqual(profiles.bind(p,observer)['workload']['drainObservation'],selected)
        del p['workload']['drainObservation']
        smaller = copy.deepcopy(config)
        for role in ('driver', 'observer'):
            smaller[role]['resources'] = {'millicpus': 100, 'memoryBytes': 128 * 1024**2}
        self.assertEqual(profiles.bind(p, smaller)['workload'], p['workload'])
        identified = copy.deepcopy(config)
        identified['workload'] = {'pointId': 'tiny', 'hotFactor': 1}
        self.assertEqual(profiles.bind(p, identified)['workload'], {**p['workload'], 'pointId': 'tiny', 'hotFactor': 1})
        identified['workload']['hotFactor'] = 10
        with self.assertRaisesRegex(ValueError, 'K8S_LOAD_PROFILE_HOT_FACTOR'):
            profiles.bind(p, identified)
        with self.assertRaisesRegex(ValueError, 'K8S_LOAD_SOURCE_PROFILE_MISMATCH'):
            profiles.bind(p, {'pins': {'pair': {'core': 'a'*40, 'deploy': 'b'*40}, 'bindingCommit': 'c'*40}})
        self.assertEqual(profiles.bind(p, config)['workload'], p['workload'])

    def test_t_run_json_is_the_config_and_absent_oracles_stay_unmeasured(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            stage = d / 'load'
            stage.mkdir()
            config = {'pins': {'pair': {'core': 'a'*40, 'deploy': 'b'*40}}, 'tenantsFile': str(d / 'tenants.json')}
            profiles.write(d / 'run.json', config)
            profiles.write(d / 'tenants.json', [])
            value = reduction.reduce_stage(stage, d / 'out')
            self.assertEqual(value['source']['pins'], config['pins'])
            for name in ('storedWrites', 'clinical', 'isolation', 'datastore'):
                self.assertEqual(value['product']['components'][name]['verdict'], 'UNMEASURED')
            self.assertIn('k6-summary.json', value['product']['figures']['missingFiles'])

    def test_dropped_iteration_and_missing_counter_are_figures(self):
        metrics = {'dropped_iterations': {'count': 0}}
        measured = reduction.http_accounting.assess(metrics)
        self.assertNotIn('offeredWorkVerdict', measured)
        self.assertEqual(measured['sourceCounts']['dropped_iterations'], 0)
        self.assertEqual(measured['sourceCounts']['scenario_request_attempts'], 'UNMEASURED')
        self.assertEqual(measured['sourceCounts']['http_reqs'], 'UNMEASURED')
        self.assertEqual(measured['scenario'], {'attempts':'UNMEASURED', 'completed':'UNMEASURED'})
        self.assertEqual(measured['shapes']['w_sgv']['responses'], 'UNMEASURED')
        metrics['dropped_iterations']['count'] = 1
        self.assertEqual(reduction.http_accounting.assess(metrics)['droppedIterations'], 1)
        del metrics['dropped_iterations']
        self.assertEqual(reduction.http_accounting.assess(metrics)['droppedIterations'], 'UNMEASURED')

    def test_unsupported_skew_history_and_restart_refuse(self):
        p = profiles.read(profiles.HERE / 'small.json')
        profiles.validate(p)
        for change, code in ((lambda x: x['population'].update(hotFactor=10), 'ADAPTER_ROSTER_OR_HOT_FACTOR_UNSUPPORTED'),
                             (lambda x: x['history'].update(additionalSeedRows=10000), 'HISTORY_UNSUPPORTED'),
                             (lambda x: x['phases'].update(restart=True), 'RESTART_IS_SEPARATE_SCENARIO')):
            broken = copy.deepcopy(p)
            change(broken)
            with self.assertRaisesRegex(ValueError, 'K8S_LOAD_' + code):
                profiles.validate(broken)
            profiles.validate(p)

    def test_all_profile_inputs_generate_existing_workload_without_source_rewrite(self):
        for path in sorted(profiles.HERE.glob('*.json')):
            p = profiles.read(path)
            profiles.validate(p)
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp) / 'generated'
                profiles.dry(p, d)
                raw = profiles.read(d / 'dry.json')
                self.assertEqual(raw['environment']['SHAPES'], ','.join(reduction.http_accounting.SHAPES))
                self.assertEqual(raw['model']['nominalIngestionCadenceSeconds'], 300)
                self.assertEqual(raw['capacityAcceptance'], 'NOT_GRANTED')


class StockViewers(unittest.TestCase):
    class Plan:
        @staticmethod
        def mix_counts(mix, n):
            return [mix['perTenant']] * n

    def test_mix_total_replaces_the_declared_count_and_absence_is_unchanged(self):
        w = {'logicalPollingClients': 100}
        self.assertEqual(profiles.stock_viewers(w, 1000, self.Plan), 100)
        self.assertEqual(profiles.stock_viewers(dict(w, viewerSetup={'mix': {'perTenant': 3}}), 1000, self.Plan), 3000)

    def test_a_mix_without_the_planner_is_refused_not_ignored(self):
        with self.assertRaisesRegex(ValueError, 'VIEWER_MIX_UNSUPPORTED'):
            profiles.stock_viewers({'logicalPollingClients': 1, 'viewerSetup': {'mix': {}}}, 10, object())

    def test_real_planner_total_when_lane_e_is_joined(self):
        plan = profiles.workload_runtime.viewer_plan
        if not hasattr(plan, 'mix_counts'):
            self.skipTest('needs claude/fixture-realism-20261123 (viewer_plan.mix_counts)')
        mix = plan.MIX_PRESETS['followers-v1']
        self.assertEqual(profiles.stock_viewers({'logicalPollingClients': 1, 'viewerSetup': {'mix': mix}}, 1000), sum(plan.mix_counts(mix, 1000)))


if __name__ == '__main__':
    unittest.main()
