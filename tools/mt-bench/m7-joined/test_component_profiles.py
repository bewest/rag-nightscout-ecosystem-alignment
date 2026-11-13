"""Pure capability checks. No serving, Docker, capacity or runtime-limit claim."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import types
import unittest

import component_profiles as cp

HERE = Path(__file__).parent


def selection():
    return {'version': 1, 'apiReplicas': 1,
            'realtime': {'mode': 'standalone', 'workers': 1, 'shards': 16},
            'evaluator': {'mode': 'standalone', 'workers': 1},
            'secrets': {'mode': 'vault-server', 'agent': {'tokenTtlSeconds': 3600, 'tokenMaxTtlSeconds': 86400,
                         'policySha256': 'a' * 64, 'secretIdTtlSeconds': 0, 'secretIdNumUses': 0}},
            'resources': {r: {'mode': 'finite', 'cpuNano': 1000000000, 'memoryBytes': 536870912} for r in cp.CLASSES}}


def context():
    return {'coreCommit': '1' * 40, 'deployCommit': '2' * 40, 'instrumentSha256': '3' * 64,
            'hostIdentitySha256': '4' * 64, 'sourcePlanSha256': '5' * 64, 'settingsFingerprintSha256': '6' * 64,
            'diagnostics': {'mode': 'off', 'intervalMs': 5000},
            'custody': {'kind': 'paired-compose-plan-v1', 'sha256': '7' * 64}}


def compose(s):
    """Independent synthetic resolved shipping shape, not source admission."""
    services = {
        'postgres': {'command': ['postgres', '-c', 'wal_level=logical']},
        'vault': {'command': ['vault', 'server', '-config=/vault/config/demo.hcl']},
        'nginx': {},
        'ui': {'command': ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/ui.js']},
        'bootstrap': {'command': ['node', 'deploy/multitenant/bootstrap.js'], 'profiles': ['ops']},
        'primer': {'command': ['node', 'deploy/multitenant/prime.js', 'provision'], 'profiles': ['ops']},
        'placement-operator': {'command': ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/placement-control.js'], 'profiles': ['ops']},
        'demo': {'command': ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/demo.js'], 'profiles': ['ops']}}
    for role, count in [('api', s['apiReplicas']), ('realtime', s['realtime']['workers']), ('evaluator', s['evaluator']['workers']), ('admin', 1), ('feed-reader', 1), ('tenant-admin', 1)]:
        for n in range(1, count + 1):
            name = role if n == 1 else role + '-' + str(n)
            services[name] = {'command': ['node', 'deploy/multitenant/entrypoint.js', role]}
    if s['realtime']['mode'] == 'fixed':
        services['socket-edge'] = {'command': ['node', '-r', './deploy/multitenant/load-env.js', 'deploy/multitenant/socket-edge.js']}
    if s['secrets']['mode'] == 'vault-agent':
        services['vault-agent'] = {'command': ['vault', 'agent', '-config=/vault/config/agent.hcl'], 'volumes': [
            {'type': 'bind', 'source': '/owned/state/vault-agent/sink', 'target': '/run/ns-vault', 'read_only': False}]}
        services['vault-agent-bootstrap'] = {'command': ['node', '/run/ns-overlay/vault-agent-bootstrap.js', 'provision'], 'profiles': ['ops']}
        for n in range(1, s['apiReplicas'] + 1):
            name = 'api' if n == 1 else 'api-' + str(n)
            services[name]['volumes'] = [{'type': 'bind', 'source': '/owned/state/vault-agent/sink', 'target': '/run/ns-vault', 'read_only': True}]
    return {'services': services}


class Profiles(unittest.TestCase):
    def refused(self, fn, code=None):
        with self.assertRaises(cp.Refused) as caught:
            fn()
        if code:
            self.assertEqual(str(caught.exception), 'M7_COMPONENT_' + code)

    def test_all_27_worker_shapes_including_fixed_one(self):
        for a in (1, 2, 4):
            for r in (1, 2, 4):
                for e in (1, 2, 4):
                    s = selection(); s['apiReplicas'] = a
                    s['realtime'].update(mode='fixed', workers=r, shards=1)
                    s['evaluator'].update(mode='fixed', workers=e)
                    inv = cp.exact_role_inventory(s, compose(s))
                    self.assertEqual(sum(role == 'api' for role in inv['serving'].values()), a)
                    self.assertEqual(sum(role == 'realtime' for role in inv['serving'].values()), r)
                    self.assertEqual(sum(role == 'evaluator' for role in inv['serving'].values()), e)
                    self.assertIn('socket-edge', inv['serving'])
                    self.assertEqual(inv['oneShot'], ['bootstrap', 'demo', 'placement-operator', 'primer'])

    def test_environment_has_no_ambient_default_or_agent_enable(self):
        s = selection()
        self.assertEqual(cp.prepare_environment(s), {'NS_API_REPLICAS': '1'})
        s['realtime'].update(mode='fixed', workers=2, shards=4096)
        s['evaluator'].update(mode='fixed', workers=4)
        s['secrets']['mode'] = 'vault-agent'
        self.assertEqual(cp.prepare_environment(s), {'NS_API_REPLICAS': '1', 'NS_REALTIME_WORKERS': '2', 'NS_REALTIME_SHARDS': '4096', 'NS_EVALUATOR_WORKERS': '4'})

    def test_missing_unknown_and_unsupported_selection(self):
        for field in selection():
            s = selection(); del s[field]; self.refused(lambda: cp.validate_selection(s))
        s = selection(); s['automaticFailover'] = True; self.refused(lambda: cp.validate_selection(s))
        s = selection(); s['resources']['feed-reader'] = {'mode': 'unlimited'}; self.refused(lambda: cp.validate_selection(s))
        s = selection(); s['evaluator']['ordinal'] = 0; self.refused(lambda: cp.validate_selection(s))

    def test_bad_counts_shards_and_standalone(self):
        for value in (True, 0, 3, 5, 16, '2', None):
            s = selection(); s['apiReplicas'] = value; self.refused(lambda: cp.validate_selection(s))
        for value in (None, False, 0, 4097, '16'):
            s = selection(); s['realtime']['shards'] = value; self.refused(lambda: cp.validate_selection(s))
        s = selection(); s['evaluator']['workers'] = 2; self.refused(lambda: cp.validate_selection(s), 'STANDALONE_COUNT')

    def test_bad_finite_and_unlimited_limits(self):
        for field, values in [('cpuNano', [False, 0, -1, 9999999, 128000000001, float('inf'), '1']), ('memoryBytes', [False, 0, 16777215, 1099511627777, 1.5])]:
            for value in values:
                s = selection(); s['resources']['postgres'][field] = value; self.refused(lambda: cp.validate_selection(s))
        s = selection(); s['resources']['postgres'] = {'mode': 'unlimited', 'cpuNano': 0}; self.refused(lambda: cp.validate_selection(s))
        s = selection(); s['resources']['postgres']['environment'] = {}; self.refused(lambda: cp.validate_selection(s))

    def test_agent_lifetime_and_policy_shape(self):
        for field, value in [('tokenTtlSeconds', 0), ('tokenMaxTtlSeconds', 1), ('policySha256', 'x' * 64), ('secretIdTtlSeconds', 86400), ('secretIdNumUses', True)]:
            s = selection(); s['secrets']['agent'][field] = value; self.refused(lambda: cp.validate_selection(s))

    def test_omitted_api4_and_idle_worker_refuse(self):
        s = selection(); s['apiReplicas'] = 4; s['realtime'].update(mode='fixed', workers=4, shards=1)
        for name in ('api-4', 'realtime-4'):
            c = compose(s); del c['services'][name]
            self.refused(lambda: cp.exact_role_inventory(s, c), 'ROSTER_MISMATCH')

    def test_foreign_service_wrong_role_and_oneshot_profile_refuse(self):
        s = selection(); c = compose(s); c['services']['surprise'] = {}
        self.refused(lambda: cp.exact_role_inventory(s, c), 'ROSTER_MISMATCH')
        c = compose(s); c['services']['api']['command'][-1] = 'evaluator'
        self.refused(lambda: cp.exact_role_inventory(s, c), 'ROLE_COMMAND')
        c = compose(s); del c['services']['primer']['profiles']
        self.refused(lambda: cp.exact_role_inventory(s, c), 'SERVICE_PROFILE')

    def test_agent_server_are_distinct_and_all_api_sinks_required(self):
        s = selection(); s['apiReplicas'] = 4; s['secrets']['mode'] = 'vault-agent'
        inv = cp.exact_role_inventory(s, compose(s))
        self.assertEqual(inv['serving']['vault'], 'vault-server')
        self.assertEqual(inv['serving']['vault-agent'], 'vault-agent')
        self.assertIn('vault-agent-bootstrap', inv['oneShot'])
        c = compose(s); del c['services']['api-4']['volumes']
        self.refused(lambda: cp.exact_role_inventory(s, c), 'SINK_CUSTODY')
        s['secrets']['mode'] = 'vault-server'; self.refused(lambda: cp.exact_role_inventory(s, c), 'ROSTER_MISMATCH')

    def test_sink_custody_refuses_rw_api_ancillary_wrong_source_subpath(self):
        s = selection(); s['secrets']['mode'] = 'vault-agent'
        for name, change in [('api', {'read_only': False}), ('api', {'source': '/other'}), ('api', {'target': '/run/ns-vault/token'}), ('api', {'type': 'volume'})]:
            c = compose(s); c['services'][name]['volumes'][0].update(change)
            self.refused(lambda: cp.exact_role_inventory(s, c), 'SINK_CUSTODY')
        c = compose(s); c['services']['placement-operator']['volumes'] = copy.deepcopy(c['services']['api']['volumes'])
        self.refused(lambda: cp.exact_role_inventory(s, c), 'SINK_CUSTODY')
        c = compose(selection()); c['services']['ui']['volumes'] = [{'target': '/run/ns-vault', 'source': '/any'}]
        self.refused(lambda: cp.exact_role_inventory(selection(), c), 'SINK_CUSTODY')

    def test_overlay_is_resource_only_stable_and_preserves_ancillaries(self):
        s = selection(); s['apiReplicas'] = 4; s['secrets']['mode'] = 'vault-agent'
        s['resources']['api']['cpuNano'] = 1234567890
        before = copy.deepcopy(s); out = cp.resource_overlay(s)
        self.assertEqual(s, before)
        self.assertEqual(out['services']['api-4'], {'cpus': '1.23456789', 'mem_limit': 536870912})
        self.assertEqual(out['services']['vault-agent'], out['services']['vault'])
        self.assertNotIn('feed-reader', out['services'])
        self.assertNotIn('placement-operator', out['services'])
        self.assertTrue(all(set(row) == {'cpus', 'mem_limit'} for row in out['services'].values()))
        self.assertEqual(out, cp.resource_overlay(json.loads(json.dumps(s))))

    def test_explicit_unlimited_never_becomes_a_finite_measurement(self):
        s = selection(); s['resources']['postgres'] = {'mode': 'unlimited'}
        self.assertEqual(cp.resource_overlay(s)['services']['postgres'], {'cpus': '0', 'mem_limit': 0})
        self.assertEqual(cp.profile_identity(s, context())['runtimeProof'], 'UNMEASURED')
        t = copy.deepcopy(s); t['resources']['postgres'] = selection()['resources']['postgres']
        self.refused(lambda: cp.compare_profiles(cp.profile_identity(s, context()), cp.profile_identity(t, context()), 'resources.postgres.cpuNano', context()))

    def test_identity_canonical_and_independent(self):
        s, c = selection(), context(); p = cp.profile_identity(s, c)
        self.assertEqual(p, cp.profile_identity(json.loads(json.dumps(s)), c))
        self.assertEqual(p, cp.validate_identity(p, c))
        s['apiReplicas'] = 4; c['coreCommit'] = 'f' * 40
        self.assertEqual(p['selection']['apiReplicas'], 1)
        self.assertEqual(p['context']['coreCommit'], '1' * 40)

    def test_context_source_and_custody_mismatch_refuse(self):
        c = context(); p = cp.profile_identity(selection(), c)
        for field in ('coreCommit', 'deployCommit', 'instrumentSha256', 'hostIdentitySha256', 'sourcePlanSha256', 'settingsFingerprintSha256'):
            wrong = copy.deepcopy(c); wrong[field] = 'f' * len(wrong[field])
            self.refused(lambda: cp.validate_identity(p, wrong), 'IDENTITY_MISMATCH')
        for bad in ({'kind': 'arbitrary-mounts', 'sha256': '7' * 64}, {'kind': 'paired-compose-plan-v1'}):
            wrong = context(); wrong['custody'] = bad; self.refused(lambda: cp.profile_identity(selection(), wrong))
        wrong = context(); wrong['extra'] = 'ignored'; self.refused(lambda: cp.profile_identity(selection(), wrong))

    def test_identity_derived_row_tamper_even_rehashed_refuse(self):
        p = cp.profile_identity(selection(), context())
        for field in ('inventory', 'resourceOverlay'):
            wrong = copy.deepcopy(p)
            if field == 'inventory': wrong[field]['serving']['foreign'] = 'api'
            else: wrong[field]['services']['api']['cpus'] = '200'
            wrong['sha256'] = cp.hashed({k: v for k, v in wrong.items() if k != 'sha256'})
            self.refused(lambda: cp.validate_identity(wrong, context()), 'IDENTITY_MISMATCH')

    def test_worker_count_comparison_derives_only_unchanged_policy(self):
        for axis in ('apiReplicas', 'realtime.workers', 'evaluator.workers'):
            a = selection(); a['realtime']['mode'] = 'fixed'; a['evaluator']['mode'] = 'fixed'
            b = copy.deepcopy(a)
            if '.' in axis: role, field = axis.split('.'); b[role][field] = 4
            else: b[axis] = 4
            verdict = cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), axis, context())
            self.assertEqual(verdict['runtimeProof'], 'UNMEASURED')
            b['resources']['api']['memoryBytes'] *= 2
            self.refused(lambda: cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), axis, context()), 'COMPARISON_SECOND_AXIS_OR_UNCHANGED')

    def test_mode_comparisons_and_shard_axis_remain_explicit(self):
        for role in ('realtime', 'evaluator', 'secrets'):
            a = selection(); b = copy.deepcopy(a); b[role]['mode'] = 'vault-agent' if role == 'secrets' else 'fixed'
            result = cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), role + '.mode', context())
            self.assertEqual(result['axis'], role + '.mode')
        a = selection(); b = copy.deepcopy(a); b['realtime']['mode'] = 'fixed'; b['realtime']['workers'] = 2
        self.refused(lambda: cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), 'realtime.mode', context()))

    def test_one_resource_scalar_and_second_field_refusal(self):
        a = selection(); b = copy.deepcopy(a); b['resources']['postgres']['cpuNano'] *= 2
        axis = 'resources.postgres.cpuNano'
        cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), axis, context())
        b['resources']['postgres']['memoryBytes'] *= 2
        self.refused(lambda: cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), axis, context()), 'COMPARISON_SECOND_AXIS_OR_UNCHANGED')
        a['resources']['postgres'] = {'mode': 'unlimited'}
        self.refused(lambda: cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(a, context()), axis, context()))

    def test_comparison_unknown_axis_unchanged_and_inactive_resource_refuse(self):
        p = cp.profile_identity(selection(), context())
        for axis in ('automaticFailover', 'resources', 'secrets.agent.tokenTtlSeconds', 'apiReplicas'):
            self.refused(lambda: cp.compare_profiles(p, p, axis, context()))
        a = selection(); b = copy.deepcopy(a); b['resources']['vault-agent']['cpuNano'] *= 2
        self.refused(lambda: cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), 'resources.vault-agent.cpuNano', context()), 'FINITE_RESOURCE_REQUIRED')

    def test_identity_strict_json_types_and_consumed_shard_axis(self):
        p = cp.profile_identity(selection(), context())
        p['version'] = True
        self.refused(lambda: cp.validate_identity(p, context()), 'IDENTITY_MISMATCH')
        p = cp.profile_identity(selection(), context()); p['context']['diagnostics']['intervalMs'] = 5000.0
        self.refused(lambda: cp.validate_identity(p, context()), 'IDENTITY_MISMATCH')
        a = selection(); b = copy.deepcopy(a); b['realtime']['shards'] = 32
        self.refused(lambda: cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), 'realtime.shards', context()), 'FIXED_SHARDS_REQUIRED')
        a['realtime']['mode'] = b['realtime']['mode'] = 'fixed'
        cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), 'realtime.shards', context())

    def test_document_bound_nonfinite_and_schema_closed(self):
        s = selection(); s['huge'] = 'x' * 65536; self.refused(lambda: cp.validate_selection(s), 'DOCUMENT_BOUND')
        schema = json.loads((HERE / 'component-profile.schema.json').read_text())
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']), set(selection()))
        self.assertEqual(set(schema['properties']['resources']['required']), set(cp.CLASSES))


class MeaningfulControls(unittest.TestCase):
    """Compile isolated in-memory ablations; production source never changes."""
    def mutant(self, old, new):
        source = (HERE / 'component_profiles.py').read_text()
        self.assertEqual(source.count(old), 1)
        module = types.ModuleType('isolated_component_mutant')
        exec(compile(source.replace(old, new), str(HERE / 'component_profiles.py') + ':control', 'exec'), module.__dict__)
        return module

    def test_api4_omission_red_then_restored(self):
        s = selection(); s['apiReplicas'] = 4
        m = self.mutant("range(1, count + 1)", "range(1, (min(count, 2) if role == 'api' else count) + 1)")
        with self.assertRaises(m.Refused) as red: m.exact_role_inventory(s, compose(s))
        self.assertIn('ROSTER_MISMATCH', str(red.exception))
        self.assertIn('api-4', cp.exact_role_inventory(s, compose(s))['serving'])

    def test_idle_worker_omission_red_then_restored(self):
        s = selection(); s['realtime'].update(mode='fixed', workers=4, shards=1)
        m = self.mutant("('realtime', s['realtime']['workers'])", "('realtime', min(s['realtime']['workers'], s['realtime']['shards']))")
        with self.assertRaises(m.Refused): m.exact_role_inventory(s, compose(s))
        self.assertIn('realtime-4', cp.exact_role_inventory(s, compose(s))['serving'])

    def test_agent_server_conflation_red_then_restored(self):
        s = selection(); s['secrets']['mode'] = 'vault-agent'
        m = self.mutant("serving['vault-agent'] = 'vault-agent'", "serving['vault-agent'] = 'vault-server'")
        with self.assertRaises(m.Refused) as red: m.exact_role_inventory(s, compose(s))
        self.assertIn('ROLE_COMMAND', str(red.exception))
        self.assertEqual(cp.exact_role_inventory(s, compose(s))['serving']['vault-agent'], 'vault-agent')

    def test_second_axis_bypass_is_detected_then_restored(self):
        a = selection(); b = copy.deepcopy(a); b['apiReplicas'] = 2; b['resources']['api']['cpuNano'] *= 2
        m = self.mutant("changed == {axis}", "axis in changed")
        m.compare_profiles(m.profile_identity(a, context()), m.profile_identity(b, context()), 'apiReplicas', context())
        with self.assertRaises(cp.Refused): cp.compare_profiles(cp.profile_identity(a, context()), cp.profile_identity(b, context()), 'apiReplicas', context())


if __name__ == '__main__':
    import sys
    # Deliberately broken source is compiled in memory; no checkout mutation.
    if len(sys.argv) == 3 and sys.argv[1] == '--control':
        controls = {
            'api4': ("range(1, count + 1)", "range(1, (min(count, 2) if role == 'api' else count) + 1)", 'test_all_27_worker_shapes_including_fixed_one'),
            'idle': ("('realtime', s['realtime']['workers'])", "('realtime', min(s['realtime']['workers'], s['realtime']['shards']))", 'test_all_27_worker_shapes_including_fixed_one'),
            'agent': ("serving['vault-agent'] = 'vault-agent'", "serving['vault-agent'] = 'vault-server'", 'test_agent_server_are_distinct_and_all_api_sinks_required'),
            'second-axis': ("changed == {axis}", "axis in changed", 'test_one_resource_scalar_and_second_field_refusal'),
            'limits': ("need(integer(budget['memoryBytes'], 16777216, 1099511627776), 'MEMORY_BOUND')", "need(True, 'MEMORY_BOUND')", 'test_bad_finite_and_unlimited_limits'),
            'identity': ("need(canonical(value) == canonical(expected), 'IDENTITY_MISMATCH')", "need(True, 'IDENTITY_MISMATCH')", 'test_context_source_and_custody_mismatch_refuse'),
        }
        if sys.argv[2] not in controls: raise SystemExit('unsupported control')
        old, new, test = controls[sys.argv[2]]
        source = (HERE / 'component_profiles.py').read_text()
        if source.count(old) != 1: raise SystemExit('control anchor mismatch')
        module = types.ModuleType('isolated_component_mutant')
        exec(compile(source.replace(old, new), str(HERE / 'component_profiles.py') + ':control', 'exec'), module.__dict__)
        cp = module
        print(json.dumps({'control': sys.argv[2], 'sourceSha256': hashlib.sha256(source.encode()).hexdigest(), 'inMemoryOnly': True}), flush=True)
        unittest.main(argv=[sys.argv[0], 'Profiles.' + test], verbosity=2)
    else:
        unittest.main()
