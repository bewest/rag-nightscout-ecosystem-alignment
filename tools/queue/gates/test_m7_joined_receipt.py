"""Synthetic ephemeral record controls; never writes a production PASS receipt."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import m7_joined_receipt as gate


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='m7-receipt-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.identity = {'pair': {'core': 'a' * 40, 'deploy': 'b' * 40},
                         'imageId': 'sha256:' + 'c' * 64, 'instrument': 'd' * 64}
        self.attribution = {'core': 'e' * 40, 'baseline': 'f' * 40, 'instrument': '1' * 64}
        self.expected = {'version': 1, 'kind': 'm7-joined-expectation', 'identity': self.identity,
                         'pending': {tier: {'count': 0, 'reason': ''} for tier in gate.TIERS + ('corpus',)},
                         'artifacts': {}, 'corpusCommand': 'multitenant',
                         'corpusSuites': ['tests/synthetic.integration.test.js'],
                         'criteria': {'clinical': self.spec('/identical', True)},
                         'controls': {'output': {phase: self.spec('/exit', code)
                                                for phase, code in [('baseline', 0), ('broken', 1), ('restored', 0)]}}}
        self.receipt = {'version': 1, 'kind': 'joined-acceptance', 'status': 'PASS', 'claims': ['acceptance'],
                        **copy.deepcopy(self.identity), 'tierLogs': {}, 'criteria': {}, 'controls': {}}
        self.campaign = {'scope': 'FROZEN_CORE_FUNCTIONAL_ACCEPTANCE_EXECUTION', 'status': 'passed', 'errors': [],
                         'source': {'coreCommit': 'a' * 40, 'deployCommit': 'b' * 40}, 'ownMongoCleanupVerified': True,
                         'fixtureResiduals': [], 'fixtureVolumeResiduals': [], 'commands': []}
        for tier in gate.TIERS:
            self.receipt['tierLogs'][tier] = self.artifact('logs/' + tier + '.txt', b'  12 passing (1s)\n')
            self.campaign['commands'].append({'id': tier, 'status': 'passed', 'returnCode': 0, 'stdout': 'logs/' + tier + '.txt'})
        self.campaign['commands'].append({'id': 'multitenant', 'status': 'passed', 'returnCode': 0})
        self.corpus = {'status': 0, 'remaining': [], 'suites': list(self.expected['corpusSuites']),
                       'result': {'status': 0, 'signal': None, 'passing': 10, 'pending': 0, 'failing': 0}}
        self.refresh_campaign()
        self.refresh_corpus()
        self.receipt['criteria']['clinical'] = self.proof('clinical.json', {'identical': True})
        self.receipt['controls']['output'] = {phase: self.proof(phase + '.json', {'exit': code})
                                               for phase, code in [('baseline', 0), ('broken', 1), ('restored', 0)]}

    def spec(self, pointer, value):
        return {'attribution': self.attribution, 'assertions': {pointer: value}}

    def artifact(self, name, data):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        file.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        self.expected['artifacts'][name] = digest
        return {'path': name, 'sha256': digest}

    def proof(self, name, data):
        return {'attribution': self.attribution, 'artifact': self.artifact(name, data)}

    def refresh_campaign(self):
        self.receipt['campaign'] = self.artifact('campaign.json', self.campaign)
        self.receipt['evidenceSha256'] = self.receipt['campaign']['sha256']

    def refresh_corpus(self):
        self.receipt['corpus'] = self.artifact('corpus.json', self.corpus)

    def check(self, scope='acceptance'):
        return gate.validate(self.expected, self.receipt, gate.Evidence(self.root), scope)

    def refuses(self, code, scope='acceptance'):
        with self.assertRaisesRegex((ValueError, RuntimeError), code):
            self.check(scope)

    def capacity(self):
        self.receipt['claims'].append('full-ladder')
        document = {'version': 1, 'kind': 'm7-joined-capacity', **self.identity, 'hostIdentity': '2' * 64, 'cells': []}
        for count in (1000, 3000, 5000, 10000):
            for replicas in (1, 2, 4):
                document['cells'].append({**self.identity, 'hostIdentity': '2' * 64, 'tenants': count, 'replicas': replicas,
                                          'profile': 'capacity', 'cadence': gate.campaign_contract().CADENCE['capacity'], 'verdict': 'PASS', 'measurements': self.measurements(),
                                          'correctness': [True, True, True], 'oracle': {'verdict': 'GREEN', 'uncertain': 0}})
        self.receipt['capacity'] = self.artifact('capacity.json', document)
        return document

    def measurements(self, profile='capacity'):
        return {'complete': True,
                'httpShapes': {str(i): {'count': 10, 'p50': 1, 'p95': 2, 'p99': 3} for i in range(7)},
                'windows': {phase: {'seconds': gate.campaign_contract().CADENCE[profile][phase + 'Seconds'], 'roles': {'api': {'sampleCount': 10, 'cpuCoresMean': 1.5}}}
                            for phase in ('idle', 'load')}}

    def milestone(self):
        full = self.capacity()
        self.receipt['claims'].remove('full-ladder')
        self.receipt.pop('capacity')
        self.receipt['claims'].append('capacity-milestone')
        self.expected['capacityMilestone'] = {'tenants': 3000, 'replicas': 4, 'profile': 'capacity', 'hostIdentity': '2' * 64,
            'comparisons': [{'tenants': 3000, 'replicas': n} for n in (1, 2, 4)]}
        cells = [c for c in full['cells'] if c['tenants'] == 3000]
        for c in cells:
            if c['replicas'] != 4:
                c['correctness'][2] = False
                c['verdict'] = 'FAIL'
        self.receipt['milestoneCells'] = [self.artifact('cell-' + str(c['replicas']) + '.json', c) for c in cells]
        return cells

    def scaling(self):
        self.milestone()
        self.receipt['claims'].extend(['api-scaling', 'scaling'])
        self.expected['scaling'] = {name: {'proof': self.spec('/kind', 'synthetic-measurement'), 'observations': [
            {'configuration': '/runs/' + str(i) + '/configuration', 'samples': '/runs/' + str(i) + '/samples',
             'metrics': {'/runs/' + str(i) + '/rate': 'synthetic effects/s'}} for i in range(2)]} for name in gate.COMPONENTS}
        self.receipt['scaling'] = {name: self.proof(name + '.json', {'kind': 'synthetic-measurement',
            'runs': [{'configuration': 1, 'samples': 10, 'rate': 1.5}, {'configuration': 2, 'samples': 10, 'rate': 2.5}]}) for name in gate.COMPONENTS}
        self.receipt['bindings'] = self.artifact('bindings.json', {'pair': self.identity['pair'], 'complete': True, 'entries': []})

    def test_acceptance_does_not_require_future_capacity(self):
        self.assertEqual(self.check()['verifiedClaims'], ['acceptance'])
        self.refuses('CLAIM_MISSING', 'full-ladder')

    def test_exact_earlier_clinical_attribution_is_allowed(self):
        self.assertNotEqual(self.attribution['core'], self.identity['pair']['core'])
        self.check()
        self.receipt['criteria']['clinical']['attribution'] = {'core': 'a' * 40}
        self.refuses('PROOF_ATTRIBUTION')

    def test_failed_unit_and_not_run_later_tiers_cannot_pass(self):
        self.campaign['status'] = 'failed'
        self.campaign['errors'] = [{'phase': 'execution', 'kind': 'Refused', 'message': 'COMMAND_FAILED_unit'}]
        self.campaign['commands'] = [{'id': 'unit', 'status': 'failed', 'returnCode': 29}]
        self.refresh_campaign()
        self.refuses('CAMPAIGN_INCOMPLETE')

    def test_missing_tier_refuses_even_with_top_level_pass(self):
        self.campaign['commands'] = [c for c in self.campaign['commands'] if c['id'] != 'browser']
        self.refresh_campaign()
        self.refuses('TIER_NOT_PASSED')

    def test_nonzero_tier_refuses_even_with_top_level_pass(self):
        self.campaign['commands'][0]['returnCode'] = 29
        self.refresh_campaign()
        self.refuses('TIER_NOT_PASSED')

    def test_diagnostic_is_never_full_proof(self):
        self.receipt['kind'] = 'joined-diagnostic'
        self.refuses('FULL_RECEIPT_REQUIRED')

    def test_each_global_identity_is_exact(self):
        for field in ('pair', 'imageId', 'instrument'):
            with self.subTest(field=field):
                original = self.receipt[field]
                if field == 'pair':
                    self.receipt[field] = {**original, 'core': '3' * 40}
                else:
                    self.receipt[field] = ('sha256:' if field == 'imageId' else '') + '3' * 64
                self.refuses('RECEIPT_IDENTITY')
                self.receipt[field] = original

    def test_wrong_campaign_source(self):
        self.campaign['source']['coreCommit'] = '3' * 40
        self.refresh_campaign()
        self.refuses('CAMPAIGN_SOURCE')

    def test_known_one_pending_is_explicit_and_preserved(self):
        self.receipt['tierLogs']['unit'] = self.artifact('logs/unit.txt', b'  12 passing (1s)\n  1 pending\n')
        self.refuses('PENDING_MISMATCH')
        self.expected['pending']['unit'] = {'count': 1, 'reason': 'synthetic explicitly retained exception'}
        self.check()
        self.expected['pending']['unit']['reason'] = ''
        self.refuses('PENDING_POLICY')

    def test_zero_or_failing_mocha_epilogue(self):
        for output in (b'  0 passing\n', b'  12 passing\n  1 failing\n'):
            self.receipt['tierLogs']['unit'] = self.artifact('logs/unit.txt', output)
            self.refuses('TIER_RESULT')

    def test_log_hash_and_command_path_binding(self):
        original = self.receipt['tierLogs']['unit']
        self.receipt['tierLogs']['unit'] = self.receipt['tierLogs']['browser']
        self.refuses('TIER_LOG_BINDING')
        self.receipt['tierLogs']['unit'] = original
        (self.root / 'logs/unit.txt').write_text('tamper')
        self.refuses('ARTIFACT_HASH')

    def test_corpus_must_have_executed_with_exact_suite_selection(self):
        self.campaign['commands'].pop()
        self.refresh_campaign()
        self.refuses('CORPUS_NOT_EXECUTED')
        self.campaign['commands'].append({'id': 'multitenant', 'status': 'passed', 'returnCode': 0})
        self.refresh_campaign()
        self.corpus['suites'] = []
        self.refresh_corpus()
        self.refuses('CORPUS_MISSING_SUITE')

    def test_corpus_failures_pending_and_cleanup_are_checked(self):
        for change, code in [({'failing': 1}, 'CORPUS_INCOMPLETE'), ({'passing': 0}, 'CORPUS_INCOMPLETE'), ({'pending': 1}, 'PENDING_MISMATCH')]:
            original = dict(self.corpus['result'])
            self.corpus['result'].update(change)
            self.refresh_corpus()
            self.refuses(code)
            self.corpus['result'] = original
        self.corpus['remaining'] = ['owned-resource-not-removed']
        self.refresh_corpus()
        self.refuses('CORPUS_INCOMPLETE')

    def test_required_criterion_and_control_cannot_be_omitted(self):
        for category in ('criteria', 'controls'):
            saved = self.receipt[category]
            self.receipt[category] = {}
            self.refuses('REQUIRED_PROOFS')
            self.receipt[category] = saved

    def test_control_has_real_red_and_restored_green(self):
        self.receipt['controls']['output']['broken'] = self.proof('broken.json', {'exit': 0})
        self.refuses('PROOF_ASSERTION')
        self.receipt['controls']['output']['broken'] = self.proof('broken.json', {'exit': 1})
        self.receipt['controls']['output'].pop('restored')
        self.refuses('CONTROL_PHASES')

    def test_control_policy_cannot_call_zero_red(self):
        self.expected['controls']['output']['broken'] = self.spec('/exit', 0)
        self.refuses('CONTROL_RED_REQUIRED')

    def test_literal_assertions_use_type_sensitive_values(self):
        self.receipt['controls']['output']['broken'] = self.proof('broken.json', {'exit': True})
        self.refuses('PROOF_ASSERTION')

    def test_capacity_has_actual_existing_contract_cells(self):
        self.capacity()
        self.check('full-ladder')

    def test_capacity_missing_api_four_or_cell_refuses(self):
        document = self.capacity()
        document['cells'] = [r for r in document['cells'] if r['replicas'] != 4]
        self.receipt['capacity'] = self.artifact('capacity.json', document)
        self.refuses('SUMMARY_MISSING_CELL', 'full-ladder')

    def test_capacity_wrong_identity_or_oracle_refuses(self):
        document = self.capacity()
        document['instrument'] = '3' * 64
        for row in document['cells']:
            row['instrument'] = '3' * 64
        self.receipt['capacity'] = self.artifact('capacity.json', document)
        self.refuses('CAPACITY_IDENTITY', 'full-ladder')
        document['instrument'] = self.identity['instrument']
        for row in document['cells']:
            row['instrument'] = self.identity['instrument']
        document['cells'][0]['oracle']['uncertain'] = 1
        document['cells'][0]['correctness'][1] = False
        document['cells'][0]['verdict'] = 'FAIL'
        self.receipt['capacity'] = self.artifact('capacity.json', document)
        self.refuses('SUMMARY_NONPASS_CELL', 'full-ladder')

    def test_declared_capacity_is_not_ignored_in_acceptance_mode(self):
        document = self.capacity()
        document['cells'] = []
        self.receipt['capacity'] = self.artifact('capacity.json', document)
        self.refuses('SUMMARY_MISSING_CELL')

    def test_three_thousand_on_four_api_does_not_require_one_api_or_ten_thousand_pass(self):
        cells = self.milestone()
        self.assertEqual([c['verdict'] for c in cells], ['FAIL', 'FAIL', 'PASS'])
        self.check('capacity-milestone')
        self.receipt['claims'].append('api-scaling')
        self.check('api-scaling')

    def test_claimed_milestone_cell_must_pass(self):
        cells = self.milestone()
        cells[-1]['verdict'] = 'FAIL'
        cells[-1]['correctness'][2] = False
        self.receipt['milestoneCells'][-1] = self.artifact('cell-4.json', cells[-1])
        self.refuses('CAPACITY_TARGET_NOT_PASSING', 'capacity-milestone')

    def test_missing_comparison_cell_or_api_replica_refuses(self):
        self.milestone()
        self.receipt['milestoneCells'].pop()
        self.refuses('MILESTONE_MISSING_CELL', 'capacity-milestone')
        self.receipt['claims'] = ['acceptance']
        self.milestone()
        self.receipt['claims'].append('api-scaling')
        self.expected['capacityMilestone']['comparisons'].pop(0)
        self.refuses('API_SCALING_COMPARISONS', 'api-scaling')

    def test_short_window_cannot_be_called_the_capacity_profile(self):
        cells = self.milestone()
        cells[-1]['measurements']['windows']['load']['seconds'] = 1
        self.receipt['milestoneCells'][-1] = self.artifact('cell-4.json', cells[-1])
        self.refuses('CAPACITY_NOT_MEASURED', 'capacity-milestone')

    def test_comparison_failure_must_retain_actual_assessment(self):
        cells = self.milestone()
        cells[0]['verdict'] = 'PASS'
        self.receipt['milestoneCells'][0] = self.artifact('cell-1.json', cells[0])
        self.refuses('CAPACITY_ASSESSMENT', 'capacity-milestone')

    def test_complete_boolean_without_real_metrics_does_not_claim_capacity(self):
        cells = self.milestone()
        cells[0]['measurements'] = {'complete': True}
        self.receipt['milestoneCells'][0] = self.artifact('cell-1.json', cells[0])
        self.refuses('CAPACITY_NOT_MEASURED', 'capacity-milestone')

    def test_pilot_remains_a_separate_small_scope(self):
        full = self.capacity()
        self.receipt['claims'].remove('full-ladder')
        self.receipt.pop('capacity')
        self.receipt['claims'].append('pilot')
        full['kind'] = 'm7-joined-remote-pilot'
        full['cells'] = []
        for count in (500, 750, 1000):
            full['cells'].append({**self.identity, 'hostIdentity': '2' * 64, 'tenants': count, 'replicas': 1,
                'profile': 'remote-pilot', 'cadence': gate.campaign_contract().CADENCE['remote-pilot'],
                'verdict': 'PASS', 'correctness': [True, True], 'oracle': {'verdict': 'GREEN', 'uncertain': 0},
                'measurements': self.measurements('remote-pilot')})
        self.receipt['pilot'] = self.artifact('pilot.json', full)
        for replicas in (1, 2, 4):
            self.expected['pilotReplicas'] = replicas
            for row in full['cells']:
                row['replicas'] = replicas
            self.receipt['pilot'] = self.artifact('pilot.json', full)
            self.check('pilot')
        self.expected['pilotReplicas'] = 2
        self.refuses('PILOT_MISSING_CELL', 'pilot')
        self.expected.pop('pilotReplicas')
        self.refuses('PILOT_REPLICA_PIN', 'pilot')
        self.refuses('CLAIM_MISSING', 'capacity-milestone')
        self.refuses('CLAIM_MISSING', 'scaling')

    def test_scaling_requires_every_component_and_explicit_bindings(self):
        self.scaling()
        self.check('scaling')
        saved = self.receipt['scaling'].pop('postgres')
        self.refuses('SCALING_COMPONENTS', 'scaling')
        self.receipt['scaling']['postgres'] = saved
        self.receipt['bindings'] = self.artifact('bindings.json', {'pair': self.identity['pair'], 'entries': []})
        self.refuses('BINDING_INVENTORY', 'scaling')

    def test_scaling_component_cannot_be_unmeasured(self):
        self.scaling()
        self.receipt['scaling']['evaluator'] = self.proof('evaluator.json', {'kind': 'synthetic-measurement',
            'runs': [{'configuration': 1, 'samples': 0, 'rate': 1.5}, {'configuration': 2, 'samples': 10, 'rate': 2.5}]})
        self.refuses('SCALING_UNMEASURED', 'scaling')

    def test_path_traversal_and_symlinks_refuse(self):
        self.receipt['campaign']['path'] = '../outside.json'
        self.expected['artifacts']['../outside.json'] = self.receipt['campaign']['sha256']
        self.refuses('ARTIFACT_PATH')
        self.receipt['campaign']['path'] = 'link.json'
        self.expected['artifacts']['link.json'] = self.receipt['campaign']['sha256']
        (self.root / 'link.json').symlink_to(self.root / 'campaign.json')
        self.refuses('ARTIFACT_SYMLINK')

    def test_expected_artifact_pin_cannot_be_replaced_by_receipt_rehash(self):
        ref = self.receipt['criteria']['clinical']['artifact']
        (self.root / ref['path']).write_text('{"identical":false}')
        ref['sha256'] = hashlib.sha256((self.root / ref['path']).read_bytes()).hexdigest()
        self.refuses('ARTIFACT_NOT_PINNED')

    def test_scaling_boolean_or_single_configuration_is_not_measurement(self):
        self.scaling()
        self.expected['scaling']['postgres']['observations'] = []
        self.refuses('SCALING_OBSERVATIONS', 'scaling')
        self.expected['scaling']['postgres']['observations'] = [
            {'configuration': '/runs/0/configuration', 'samples': '/runs/0/samples', 'metrics': {'/runs/0/rate': 'effects/s'}},
            {'configuration': '/runs/0/configuration', 'samples': '/runs/0/samples', 'metrics': {'/runs/0/rate': 'effects/s'}}]
        self.refuses('SCALING_DUPLICATE_CONFIGURATION', 'scaling')

    def test_explicit_missing_or_bad_json_cli_refuses_without_traceback(self):
        for raw in (b'{', b'{"claims":[{}]}', b'{"claims":["acceptance"]}'):
            file = self.root / 'bad.json'
            file.write_bytes(raw)
            result = subprocess.run([sys.executable, str(Path(gate.__file__)), '--expected', str(file), '--receipt', str(file)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(result.stdout.startswith('REFUSED '))
            self.assertEqual(result.stderr, '')

    def test_duplicate_json_keys_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
            gate.decode('{"status":"failed","status":"passed"}')
        with self.assertRaisesRegex(ValueError, 'JSON_CONSTANT'):
            gate.decode('{"value":1e999}')

    def test_missing_control_oracle_goes_red_when_validator_guard_is_ablated(self):
        expected = self.root / 'expected.json'
        receipt = self.root / 'receipt.json'
        expected.write_text(json.dumps(self.expected))
        self.receipt['controls'] = {}
        receipt.write_text(json.dumps(self.receipt))
        source = Path(gate.__file__).read_text()
        needle = "for category in ('criteria', 'controls'):"
        self.assertEqual(source.count(needle), 1)
        mutant = self.root / 'mutant.py'
        mutant.write_text(source.replace(needle, "for category in ('criteria',):"))

        def require_refusal(script):
            result = subprocess.run([sys.executable, str(script), '--expected', str(expected), '--receipt', str(receipt)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, 'MISSING_CONTROL_FALSE_PASS ' + result.stdout)
            self.assertIn('M7_REQUIRED_PROOFS', result.stdout)

        with self.assertRaisesRegex(AssertionError, 'MISSING_CONTROL_FALSE_PASS'):
            require_refusal(mutant)
        require_refusal(Path(gate.__file__))

    def test_full_ladder_cli_does_not_write_import_bytecode(self):
        self.capacity()
        expected = self.root / 'expected.json'
        receipt = self.root / 'receipt.json'
        expected.write_text(json.dumps(self.expected))
        receipt.write_text(json.dumps(self.receipt))
        script = self.root / 'tools/queue/gates/m7_joined_receipt.py'
        contract = self.root / 'tools/mt-bench/m7-joined/contract.py'
        script.parent.mkdir(parents=True)
        contract.parent.mkdir(parents=True)
        script.write_bytes(Path(gate.__file__).read_bytes())
        contract.write_bytes((Path(gate.__file__).resolve().parents[2] / 'mt-bench/m7-joined/contract.py').read_bytes())
        before = {str(f): f.read_bytes() for f in self.root.rglob('*') if f.is_file()}
        result = subprocess.run([sys.executable, str(script), '--expected', str(expected), '--receipt', str(receipt), '--scope', 'full-ladder'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({str(f): f.read_bytes() for f in self.root.rglob('*') if f.is_file()}, before)
        self.assertFalse(list(self.root.rglob('__pycache__')))

    def test_read_only_cli_green_red_then_restored(self):
        expected = self.root / 'expected.json'
        receipt = self.root / 'receipt.json'
        expected.write_text(json.dumps(self.expected))
        receipt.write_text(json.dumps(self.receipt))
        before = {str(f): f.read_bytes() for f in self.root.rglob('*') if f.is_file()}
        args = [sys.executable, str(Path(gate.__file__)), '--expected', str(expected), '--receipt', str(receipt)]
        good = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.receipt['controls'] = {}
        receipt.write_text(json.dumps(self.receipt))
        bad = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn('M7_REQUIRED_PROOFS', bad.stdout)
        receipt.write_bytes(before[str(receipt)])
        restored = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(restored.returncode, 0)
        self.assertEqual({str(f): f.read_bytes() for f in self.root.rglob('*') if f.is_file()}, before)


if __name__ == '__main__':
    unittest.main()
