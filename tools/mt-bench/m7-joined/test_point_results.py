import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import point_results as points
import runner


class StandardPoint(unittest.TestCase):
    def test_public_compose_pre_entry_failure_and_collision(self):
        with TemporaryDirectory() as temp:
            case = Path(temp)/'point'
            with patch.object(sys, 'argv', ['runner.py', 'run', str(case/'missing.json'), str(case), '--standard-case']):
                with self.assertRaises(FileNotFoundError):
                    runner.main()
                self.assertEqual({p.name for p in case.iterdir()}, {'raw', 'result.json', 'cleanup.json'})
                self.assertEqual(points.read(case/'result.json')['status'], 'FAILED_PARTIAL')
                self.assertEqual(points.read(case/'cleanup.json')['status'], 'UNMEASURED')
                previously = (case/'result.json').read_bytes()
                with self.assertRaises(FileExistsError):
                    runner.main()
                self.assertEqual((case/'result.json').read_bytes(), previously)

    def test_failure_after_prepare_has_terminal_result(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/'point'
            def prepared(config, raw, one_shot):
                raw.mkdir()
                points.write(raw/'result.json', {'status':'PREPARED', 'phase':'prepare'})
                return raw
            with patch.object(sys, 'argv', ['runner.py', 'run', 'config', str(root), '--standard-case']), \
                 patch.object(runner, 'prepare', side_effect=prepared), \
                 patch.object(runner, 'execute', side_effect=RuntimeError('M7_RUNNER_WORK_DEADLINE')):
                with self.assertRaisesRegex(RuntimeError, 'WORK_DEADLINE'):
                    runner.main()
            self.assertEqual(points.read(root/'result.json')['status'], 'FAILED_PARTIAL')
            self.assertEqual(points.read(root/'result.json')['code'], 'M7_RUNNER_WORK_DEADLINE')

    def test_named_observation_memory_cleanup_and_missing_accounting(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/'raw'
            root.mkdir()
            value = points.publish_compose(root, {'memAvailableAtEntryBytes': 37}, {'status': 'DEFERRED_TO_SESSION_CLOSE'})
            self.assertEqual(value['memAvailableAtEntryBytes'], 37)
            self.assertEqual(value['measurements']['offeredWork'], 'UNMEASURED')
            self.assertEqual(value['cleanup']['status'], 'DEFERRED_TO_SESSION_CLOSE')
            self.assertFalse((root.parent/'result.json').exists())

    def test_comparison_uses_all_shards_and_time_weights_shorter_executors(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            load = root/'load'
            load.mkdir()
            points.write(root/'run.json', {'tenants': 30, 'ordinaryRosterTenants': 10})
            scenarios = {'read': {'perSecond': 4, 'durationSeconds': 10}, 'write': {'perSecond': 2, 'durationSeconds': 5}}
            shards = [{'plan': {'shardCount': 2, 'shardIndex': index, 'scenarios': scenarios},
                       'byScenario': {'read': {'steadyCompletions': 36}, 'write': {'steadyCompletions': 9}}}
                      for index in range(2)]
            summary = {'kind': 'm7-configured-driver-accounting', 'population': 10,
                       'cadence': {'loadSeconds': 10, 'logicalPollingClients': 0},
                       'configuration': {'scenarios': scenarios}, 'shards': shards,
                       'totals': {'offered': 100.0, 'steadyCompletions': 90, 'completed': 107, 'issued': 109}}
            latencies = {'verdict': 'MEASURED', 'perShard': [{'read': {'p(95)': 11}}, {'read': {'p(95)': 13}}]}
            for driver, path in [('driver-vu-assessment.json', 'outcome-gate.json'), ('driver-accounting.json', 'result.json')]:
                with self.subTest(driver=driver):
                    points.write(load/driver, summary)
                    points.write(load/path, {'httpLatencyAllShards': latencies})
                    report = points.load_report(load, {})
                    self.assertEqual([report[key] for key in ('provisionedTenants', 'ordinaryTenants', 'selectedViewers')], [30, 10, 0])
                    rate = report['ordinaryRate']
                    self.assertEqual([rate[k] for k in ('windowSeconds', 'targetRps', 'achievedRps')], [10, 10, 9])
                    self.assertEqual(report['httpLatencyAllShardsMs'], latencies)
                    (load/driver).unlink()
                    (load/path).unlink()
            points.write(load/'native-load.json', {'writerContinuity': 'UNMEASURED'})
            points.write(load/'driver-accounting.json', summary)
            points.write(load/'result.json', {'httpLatencyAllShards': latencies})
            report = points.load_report(load, {})
            self.assertEqual(report['ordinaryRate']['targetRps'], 10)
            self.assertEqual(report['ordinaryRate']['achievedRps'], 'UNMEASURED')
            self.assertEqual(report['httpLatencyAllShardsMs'], 'UNMEASURED')
            (load/'native-load.json').unlink()
            del summary['totals']['steadyCompletions']
            points.write(load/'driver-accounting.json', summary)
            self.assertEqual(points.load_report(load, {})['ordinaryRate']['achievedRps'], 'UNMEASURED')
            summary['kind'] = 'm7-configured-driver-partial'
            points.write(load/'driver-accounting.json', summary)
            rate = points.load_report(load, {})['ordinaryRate']
            self.assertEqual((rate['targetRps'], rate['achievedRps']), ('UNMEASURED', 'UNMEASURED'))

    def test_published_sparse_counters_and_export_lifetime(self):
        import http_accounting
        with TemporaryDirectory() as temp:
            load = Path(temp)
            http = http_accounting.assess({'dropped_iterations': {'count': 0}})
            summary = points.load_report(load, http)
            self.assertEqual(summary['offeredWork'], 'UNMEASURED')
            self.assertEqual(summary['counts']['dropped_iterations'], 0)
            self.assertEqual(summary['counts']['scenario_request_attempts'], 'UNMEASURED')
            old = {'offeredWorkVerdict':'PASS', 'sourceReconciliation':'UNMEASURED',
                   'sourceCounts':{'dropped_iterations':0, 'scenario_request_attempts':0}}
            historical = points.load_report(load, old)
            self.assertEqual(historical['offeredWork'], 'UNMEASURED')
            self.assertEqual(historical['counts']['scenario_request_attempts'], 'UNMEASURED')
            points.write(load/'k6-summary.json', {'metrics': {'dropped_iterations': {'count': 0}}})
            self.assertEqual(points.load_report(load, old)['counts'], http['sourceCounts'])
            origin = {'podUid':'before', 'writer':{'containerId':'original'}}
            final = {'podUid':'after', 'containerId':'replacement', 'complete':True}
            points.write(load/'native-load.json', {'writerContinuity':'UNMEASURED', 'artifactSource':origin, 'process':final})
            summary = points.load_report(load, http)
            self.assertEqual(summary['countsSource'], origin)
            self.assertEqual(summary['terminalWriter']['containerId'], 'replacement')
            self.assertEqual(summary['countScope'], 'exported writer only; whole-run counts unmeasured')

    def test_retained_reducer_product_failure_survives_live_gate_loss(self):
        with TemporaryDirectory() as temp:
            case = Path(temp)
            packet = case/'runtime'/'packet'
            experiment = packet/'experiment'
            experiment.mkdir(parents=True)
            gate = {'verdict': 'FAIL', 'components': {'sampledOracle': {'verdict':'FAIL', 'codes':['CLINICAL_LATE']}}}
            failure = {'code':'MISSING_OBSERVATION', 'verdict':'UNMEASURED'}
            points.write(experiment/'result.json', {'verdict':'UNMEASURED','firstFailure':failure,
                                                    'observations': {'outcomeGate':gate}})
            points.publish_native(case)
            result = points.read(case/'result.json')
            self.assertEqual(result['firstFailure'], failure)
            self.assertEqual(result['measurements']['outcomeGate'], 'FAIL')
            self.assertEqual(result['measurements']['components'], gate['components'])

    def test_native_failure_and_unconfirmed_host_unit(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/'point'
            case = root/'raw'/'point'
            runtime = case/'runtime'
            runtime.mkdir(parents=True)
            for name, value in [('first-failure', {'code': 'K8S_FAIL'}), ('absence', {'absent': True}),
                                ('native-unit', {'unit': 'ns-point-native.scope'})]:
                points.write(runtime/(name+'.json'), value)
            points.publish_native(case)
            self.assertEqual(points.read(root/'result.json')['firstFailure']['code'], 'K8S_FAIL')
            self.assertEqual(points.read(root/'cleanup.json')['status'], 'UNMEASURED')
            self.assertEqual(set(p.name for p in root.iterdir()), {'raw', 'cleanup.json', 'result.json'})
            with self.assertRaises(FileExistsError):
                points.publish_native(case)
