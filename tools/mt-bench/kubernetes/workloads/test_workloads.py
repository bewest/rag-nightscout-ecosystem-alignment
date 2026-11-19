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
        oversized = copy.deepcopy(config)
        oversized['driver']['resources']['millicpus'] = 10000
        with self.assertRaisesRegex(ValueError, 'K8S_LOAD_ACTOR_PLAN_EXCEEDS_PROFILE'):
            profiles.bind(p, oversized)
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
            self.assertIn(str(d / 'run.json'), value['inputs'])
            self.assertEqual(value['stored']['verdict'], 'UNMEASURED')
            self.assertEqual(value['selectedClinicalCoverage']['verdict'], 'UNMEASURED')
            self.assertEqual(value['delivered']['verdict'], 'UNMEASURED')

    def test_dropped_iteration_and_missing_counter_are_not_complete_offered_work(self):
        metrics = {'dropped_iterations': {'count': 0}}
        measured = reduction.http_accounting.assess(metrics)
        self.assertEqual(measured['offeredWorkVerdict'], 'UNMEASURED')
        self.assertEqual(measured['sourceCounts']['dropped_iterations'], 0)
        self.assertEqual(measured['sourceCounts']['scenario_request_attempts'], 'UNMEASURED')
        self.assertEqual(measured['sourceCounts']['http_reqs'], 'UNMEASURED')
        self.assertEqual(measured['scenario'], {'attempts':'UNMEASURED', 'completed':'UNMEASURED'})
        self.assertEqual(measured['shapes']['w_sgv']['responses'], 'UNMEASURED')
        metrics['dropped_iterations']['count'] = 1
        self.assertEqual(reduction.http_accounting.assess(metrics)['offeredWorkVerdict'], 'FAIL')
        metrics['dropped_iterations']['count'] = 0
        self.assertEqual(reduction.http_accounting.assess(metrics)['offeredWorkVerdict'], 'UNMEASURED')
        del metrics['dropped_iterations']
        self.assertEqual(reduction.http_accounting.assess(metrics)['offeredWorkVerdict'], 'UNMEASURED')

    def test_accepted_write_requires_witness_even_with_recorded_pass(self):
        ledger = {'byTenant': {'synthetic-a': {'accepted': 1}, 'synthetic-b': {'accepted': 1}}}
        p = {'completedOutput': {'verdict': 'PASS', 'witnesses': [
            {'tenant': 'synthetic-a', 'date': 1, 'ready': True},
            {'tenant': 'synthetic-b', 'date': 2, 'ready': True}]}}
        self.assertEqual(reduction.witness_coverage(p, ledger)['verdict'], 'PASS')
        broken = copy.deepcopy(p)
        broken['completedOutput']['witnesses'].pop()
        self.assertEqual(reduction.witness_coverage(broken, ledger)['code'], 'K8S_LOAD_WITNESS_COVERAGE')
        broken = copy.deepcopy(p)
        broken['completedOutput']['witnesses'][1] = copy.deepcopy(broken['completedOutput']['witnesses'][0])
        self.assertEqual(reduction.witness_coverage(broken, ledger)['verdict'], 'FAIL')
        self.assertEqual(reduction.witness_coverage(p, ledger)['verdict'], 'PASS')
        broken = copy.deepcopy(p)
        broken['completedOutput']['witnesses'].pop()
        self.assertEqual(reduction.witness_coverage(broken, ledger)['missingTenants'], ['synthetic-b'])
        late = copy.deepcopy(p)
        late['completedOutput']['witnesses'][0].update(ready=False, code='M7_COMPLETION_DEADLINE',
                                                       assessedCode='M7_COMPLETION_TYPED_STATE')
        detail = reduction.witness_coverage(late, ledger)
        self.assertEqual((detail['verdict'], detail['recordedReady']), ('FAIL', 1))
        self.assertEqual(detail['notReadyCodes'], {'M7_COMPLETION_DEADLINE': 1})
        self.assertEqual(detail['notReadyAssessedCodes'], {'M7_COMPLETION_TYPED_STATE': 1})

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


if __name__ == '__main__':
    unittest.main()
