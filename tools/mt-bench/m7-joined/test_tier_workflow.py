import copy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import adapter
from contract import discovery_authorization
import diagnostic_resources as resources
import runner
import stream_topology as stream
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
        # The checkout's HEAD and working tree are not compared; the image is.
        with patch.object(adapter, 'commit', side_effect=lambda _repo, sha: sha), \
             patch.object(adapter, 'git', side_effect=AssertionError('no HEAD or status read')), \
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

    def test_uncapped_projection_removes_reference_cpu_and_memory_limits(self):
        config_value = {'services': {'evaluator': {'cpus': 1, 'mem_limit': '1073741824', 'deploy': {
            'resources': {'limits': {'memory': '1g', 'pids': 500}, 'reservations': {'cpus': '0.25'}}}}}}
        original = copy.deepcopy(config_value)
        projected, removed = resources.uncapped_compose(config_value)
        self.assertEqual(config_value, original)
        self.assertEqual(removed['evaluator'], ['cpus', 'mem_limit', 'deploy.resources.limits.memory',
                                               'deploy.resources.reservations.cpus'])
        self.assertEqual(projected['services']['evaluator']['deploy']['resources']['limits'], {'pids': 500})
        self.assertEqual(resources.compose_limit_mode(projected, None), 'uncapped-services')
        projected['services']['evaluator']['deploy']['resources']['reservations']['memory'] = '1g'
        with self.assertRaisesRegex(RuntimeError, 'IMPLICIT_SERVICE_LIMIT:evaluator'):
            resources.compose_limit_mode(projected, None)

    def test_ack_budget_is_receipt_bound_to_local_external_discovery(self):
        value = config()
        value['tier'] = 'discovery'
        options = value['prepare']
        options['pgstream-topology'] = stream.EXTERNAL
        options['pgstream-notifier-ack-timeout-ms'] = 10000
        with patch.object(adapter, 'instrument', return_value={'sha256': value['helperInstrument']}):
            plan = runner.tier_plan(value)
            effective = plan['effective']
            self.assertEqual(effective[stream.ACK_BUDGET], 10000)
            value['prepare']['pgstream-topology'] = stream.COLOCATED
            with self.assertRaisesRegex(RuntimeError, 'ACK_LOCAL_EXTERNAL_DISCOVERY_REQUIRED'):
                runner.tier_plan(value)
            value['prepare']['pgstream-topology'] = stream.EXTERNAL
            value['prepare']['pgstream-notifier-ack-timeout-ms'] = 0
            with self.assertRaisesRegex(RuntimeError, 'ACK_BUDGET_INVALID'):
                runner.tier_plan(value)
        with self.assertRaisesRegex(RuntimeError, 'ACK_BOUND_RECEIPT_REQUIRED'):
            discovery_authorization(effective, {'version': 1})

    def test_ack_budget_changes_only_source_notifier_timeout_and_checks_runtime_mount(self):
        with tempfile.TemporaryDirectory() as area:
            root = Path(area)
            wire = root/'state/pgstream/pgstream.yaml'
            mount = {'type': 'bind', 'read_only': True, 'target': '/run/ns-stream', 'source': str(wire.parent)}
            config_value = {'services': {'pgstream': {'volumes': [mount]}}}
            original = {'source': {'preserved': True}, 'target': {'webhooks': {'notifier': {
                'worker_count': 1, 'strict_mode': True, 'backoff': {'constant': {'max_retries': 1, 'interval': 50}},
                'client_timeout': 2000, 'transaction_batch': {'max_rows': 4000}}}}}
            adapter.write(wire, original)
            self.assertIsNone(stream.install_ack_budget(root, {}, config_value))
            self.assertEqual(json.loads(wire.read_text()), original)
            selected = {stream.ACK_BUDGET: 10000, 'pgstreamTopology': stream.EXTERNAL,
                        'runPurpose': 'discovery', 'profile': 'pgstream-sample'}
            recorded = stream.install_ack_budget(root, selected, config_value)
            selected['pgstreamNotifierAckWire'] = recorded
            self.assertEqual(recorded['sourceTimeoutMs'], 2000)
            self.assertEqual(recorded['effectiveTimeoutMs'], 10000)
            expected = copy.deepcopy(original)
            expected['target']['webhooks']['notifier']['client_timeout'] = 10000
            self.assertEqual(json.loads(wire.read_text()), expected)
            observed = {'Type': 'bind', 'RW': False, 'Source': str(wire.parent), 'Destination': '/run/ns-stream'}
            stream.verify_ack_budget(root, selected, [observed])
            with self.assertRaisesRegex(RuntimeError, 'ACK_SOURCE_DEFAULT_CHANGED'):
                stream.install_ack_budget(root, selected, config_value)
            with self.assertRaisesRegex(RuntimeError, 'ACK_WIRE_MOUNT'):
                stream.verify_ack_budget(root, selected, [{**observed, 'RW': True}])
            adapter.write(wire, original)
            with self.assertRaisesRegex(RuntimeError, 'ACK_WIRE_CHANGED'):
                stream.verify_ack_budget(root, selected, [observed])

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
