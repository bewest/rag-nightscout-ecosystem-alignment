import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import adapter
import diagnostic_resources as resources
import runner
import tier_smoke
from test_run_configuration import config

sys.path.append(str(adapter.HERE.parent / 'kubernetes'))
import workload_runtime


class TierWorkflow(unittest.TestCase):
    def test_smoke_plan_reports_defaults_and_authored_values(self):
        value = config()
        value['tier'] = 'smoke'
        value['workSeconds'] = 300
        value['prepare'].pop('load-seconds')
        value['prepare'].pop('receipt')
        with patch.object(adapter, 'instrument', return_value={'sha256': value['helperInstrument']}):
            result = runner.tier_plan(value)
        self.assertEqual(result['defaultsApplied']['load-seconds'], 60)
        self.assertEqual(result['effective']['cadence']['loadSeconds'], 60)
        self.assertNotIn('tenants', result['defaultsApplied'])
        self.assertIn('tenants', result['authoredKeys'])
        self.assertEqual(result['sourceAdmission'], 'runner-materialized PENDING tuple')
        self.assertEqual(result['capacityAcceptance'], 'NOT_GRANTED')

    def test_tiered_dirty_or_wrong_image_refuse_before_seed_with_result(self):
        for finding in ('M7_SOURCE_CORE_DIRTY', 'M7_IMAGE_ID_CHANGED'):
            with self.subTest(finding=finding), tempfile.TemporaryDirectory() as area:
                root = Path(area)
                value = config()
                value['tier'] = 'discovery'
                path = root / 'config.json'
                adapter.write(path, value)
                out = root / 'observation'
                with patch.object(adapter, 'instrument', return_value={'sha256': value['helperInstrument']}), \
                     patch.object(runner, 'clean_source_preflight', side_effect=RuntimeError(finding)), \
                     patch.object(runner, 'stage') as effects, patch.object(runner, 'arm_window') as arm:
                    with self.assertRaisesRegex(RuntimeError, finding):
                        runner.prepare(path, out)
                effects.assert_not_called()
                arm.assert_not_called()
                result = adapter.document(out / 'result.json')
                self.assertEqual(result['phase'], 'source-input')
                self.assertEqual(result['code'], finding)

    def test_clean_input_fences_source_before_docker_and_checks_image(self):
        value = config()
        value['tier'] = 'discovery'
        with patch.object(adapter, 'instrument', return_value={'sha256': value['helperInstrument']}):
            _, argv = runner.validate_config(value)
        parsed = adapter.parser().parse_args(['prepare', '--directory', '/tmp/synthetic-tier', *argv])
        with patch.object(adapter, 'commit', side_effect=lambda _repo, sha: sha), \
             patch.object(adapter, 'git', side_effect=[parsed.core_commit, ' M tracked-file']), \
             patch.object(adapter, 'prepare_image_inputs') as image:
            with self.assertRaisesRegex(RuntimeError, 'SOURCE_CORE_DIRTY'):
                runner.clean_source_preflight(parsed)
            image.assert_not_called()
        with patch.object(adapter, 'commit', side_effect=lambda _repo, sha: sha), \
             patch.object(adapter, 'git', side_effect=[parsed.core_commit, '', parsed.deploy_commit, '']), \
             patch.object(adapter, 'prepare_image_inputs', side_effect=RuntimeError('M7_IMAGE_ID_CHANGED')):
            with self.assertRaisesRegex(RuntimeError, 'IMAGE_ID_CHANGED'):
                runner.clean_source_preflight(parsed)

    def test_acceptance_requires_frozen_receipt(self):
        value = config()
        value['tier'] = 'acceptance'
        value['prepare'].pop('receipt')
        with patch.object(adapter, 'instrument', return_value={'sha256': value['helperInstrument']}):
            with self.assertRaisesRegex(RuntimeError, 'FROZEN_ACCEPTANCE_REQUIRED'):
                runner.validate_config(value)

    def test_native_resource_mode_distinguishes_optional_service_caps(self):
        config_value = {'services': {'nginx': {}}}
        initial = copy.deepcopy(config_value)
        self.assertIs(resources.overlay(config_value, None), config_value)
        self.assertEqual(resources.compose_limit_mode(config_value, None), 'uncapped-services')
        self.assertEqual(config_value, initial)
        with self.assertRaisesRegex(RuntimeError, 'IMPLICIT_SERVICE_LIMIT:nginx'):
            resources.compose_limit_mode({'services': {'nginx': {'cpus': 2}}}, None)
        keys = (*resources.NATIVE_CPU_LIMITS, *resources.NATIVE_MEMORY_LIMITS)
        row = {'Id': 'synthetic', 'HostConfig': dict.fromkeys(keys, 0),
               'Config': {'Labels': {'com.docker.compose.service': 'nginx'}}}
        self.assertEqual(resources.uncapped_readback([row], config_value['services'])[0]['limits']['Memory'], 0)
        row['HostConfig']['Memory'] = 1024
        with self.assertRaisesRegex(RuntimeError, 'UNEXPECTED_NATIVE_SERVICE_LIMIT:nginx'):
            resources.uncapped_readback([row], config_value['services'])
        row['HostConfig']['Memory'] = 0
        self.assertEqual(len(resources.uncapped_readback([row], config_value['services'])), 1)

    def test_smoke_detects_one_extra_statement_per_cycle_and_keeps_timing_context(self):
        with tempfile.TemporaryDirectory() as area:
            root = Path(area)
            statement = {'status': 'MEASURED', 'value': 3, 'unit': 'statements/unit',
                         'denominator': 'completed evaluator work or time cycle',
                         'scope': 'load-window service and lifetime pg_stat_statements rows', 'population': 10}
            timing = {**statement, 'value': 4, 'unit': 'ms/unit'}
            statements_key = 'db.evaluator.statements'
            timing_key = 'db.evaluator.execution'
            original = {statements_key: statement, timing_key: timing}
            path = root / 'baseline.json'
            adapter.write(path, {'version': 1, 'signals': original, 'exactStatementSignals': [statements_key]})
            good = {'oracles': {'stored': 'GREEN', 'clinical': 'PASS', 'ownership': 'PASS',
                                'clientFrames': 'PASS'}, 'signals': copy.deepcopy(original)}
            with patch.object(tier_smoke, 'project', return_value=good):
                good['signals'][timing_key]['value'] = 6
                tier_smoke.assess(root, path)
                report = adapter.document(root / 'smoke.json')
                self.assertEqual(report['sqlDeltas'][timing_key]['relativeDelta'], 0.5)
                good['signals'][statements_key]['value'] = 4
                with self.assertRaisesRegex(RuntimeError, 'SMOKE_WITNESS_OR_STATEMENT_COUNT'):
                    tier_smoke.assess(root, path)
                report = adapter.document(root / 'smoke.json')
                self.assertEqual(report['sqlDeltas'][statements_key]['delta'], 1)
                good['signals'][statements_key]['value'] = 3
                tier_smoke.assess(root, path)

    def test_shared_workload_accepts_fractional_rate_and_sparse_slow_probe(self):
        value = config()
        value['prepare'].update({'offered-rps': 2.5, 'probe-every-ms': 600000,
                                 'logical-polling-clients': 0, 'hot-factor': 1,
                                 'setup-seconds': 900, 'drain-seconds': 600})
        value['workSeconds'] = 2200
        with patch.object(adapter, 'instrument', return_value={'sha256': value['helperInstrument']}):
            _, argv = runner.validate_config(value)
        args = adapter.parser().parse_args(['prepare', '--directory', '/tmp/plan-only', *argv])
        local = adapter.cadence_options(args)
        keys = ('loadSeconds', 'setupSeconds', 'drainSeconds', 'logicalPollingClients', 'hotFactor',
                'probeEveryMs', 'offeredRps')
        kube = {key: local[key] for key in keys}
        workload_runtime.validate(kube, adapter.require)
        self.assertEqual(workload_runtime.environment(kube, {}, adapter.require)['OFFERED_RPS'], '2.5')
        rate = adapter.rate_offer({'tenants': args.tenants, 'cadence': local})
        cycles, rates = workload_runtime.rates(kube, args.tenants)
        self.assertEqual(rate['arrivalCycleMs'], cycles['r_sgv'])
        self.assertAlmostEqual(rate['effectiveScenarioRps'], sum(rates.values()))
        with self.assertRaisesRegex(RuntimeError, 'WORKLOAD_PROBE_LEDGER_WINDOW'):
            workload_runtime.validate({**kube, 'loadSeconds': 120, 'probeEveryMs': 1}, adapter.require)
        args.load_seconds = 120
        args.probe_every_ms = 1
        with self.assertRaisesRegex(RuntimeError, 'M7_PROBE_LEDGER_WINDOW'):
            adapter.cadence_options(args)

    def test_phase_and_rate_inputs_report_representation_refusal(self):
        value = config()
        value['tier'] = 'discovery'
        for offered in (0.25, 12000):
            value['prepare'].update({'offered-rps': offered, 'logical-polling-clients': 0,
                                     'hot-factor': 1, 'probe-every-ms': 600000})
            with patch.object(adapter, 'instrument', return_value={'sha256': value['helperInstrument']}):
                _, argv = runner.validate_config(value)
            args = adapter.parser().parse_args(['prepare', '--directory', '/tmp/plan-only', *argv])
            local = adapter.cadence_options(args)
            kube = {key: local[key] for key in ('offeredRps', 'logicalPollingClients',
                                               'hotFactor', 'probeEveryMs', 'loadSeconds')}
            workload_runtime.validate(kube, adapter.require, args.tenants)
            self.assertEqual(workload_runtime.environment(kube, {}, adapter.require)['OFFERED_RPS'], str(float(offered)))
            for invalid in (1e-20, 1e20):
                with self.assertRaisesRegex(RuntimeError, 'WORKLOAD_OFFERED_TIME_UNIT'):
                    workload_runtime.validate({**kube, 'offeredRps': invalid}, adapter.require, args.tenants)
                args.offered_rps = invalid
                with self.assertRaisesRegex(RuntimeError, 'M7_OFFERED_RPS_TIME_UNIT'):
                    adapter.cadence_options(args)
