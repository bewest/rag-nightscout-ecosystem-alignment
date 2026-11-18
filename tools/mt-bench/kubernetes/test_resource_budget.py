"""Authored scheduling/limit/readback controls; no cluster effects."""
import copy
import unittest
from unittest.mock import patch
from test_adapter import fixture, k, execute as e
import test_matrix as matrix_tests
import resource_budget as r
import matrix


class ResourceBudget(unittest.TestCase):
    def requests_fixture(self):
        c, inv, rendered, client = fixture()
        c['resourceAccounting'] = inv['resourceAccounting'] = r.REQUESTS
        for obj in rendered:
            if obj['kind'] in k.WORKLOADS:
                for container in k.template(obj)['spec']['containers']:
                    container['resources'].pop('limits')
        return c, inv, rendered, client

    def test_optional_limits_require_explicit_matching_mode(self):
        c, inv, rendered, client = self.requests_fixture()
        k.validate(c, inv, rendered)
        inv.pop('resourceAccounting')
        with self.assertRaisesRegex(k.Refused, 'RESOURCE_ACCOUNTING_MISMATCH'):
            k.validate(c, inv, rendered)
        c.pop('resourceAccounting')
        with self.assertRaisesRegex(k.Refused, 'UNBUDGETED_CONTAINER'):
            k.validate(c, inv, rendered)
        c['resourceAccounting'] = inv['resourceAccounting'] = r.REQUESTS
        k.validate(c, inv, rendered)
        c['resourceAccounting'] = 'automatic'
        with self.assertRaisesRegex(k.Refused, 'RESOURCE_ACCOUNTING_UNSUPPORTED'):
            k.validate(c, inv, rendered)

    def test_requests_required_and_supplied_limits_checked(self):
        c, inv, rendered, _ = self.requests_fixture()
        container = k.template(rendered[1])['spec']['containers'][0]
        container['resources']['limits'] = {'memory': '128Mi'}
        k.validate(c, inv, rendered)
        container['resources']['limits']['cpu'] = '0.05'
        with self.assertRaisesRegex(k.Refused, 'LIMIT_BELOW_REQUEST'):
            k.validate(c, inv, rendered)
        container['resources']['limits']['cpu'] = '0.5'
        k.validate(c, inv, rendered)
        container['resources']['requests']['memory'] = '0.9'
        container['resources']['limits']['memory'] = '0.1'
        with self.assertRaisesRegex(k.Refused, 'LIMIT_BELOW_REQUEST'):
            k.validate(c, inv, rendered)
        container['resources']['limits']['memory'] = '1'
        k.validate(c, inv, rendered)
        container['resources']['requests'].pop('memory')
        with self.assertRaisesRegex(k.Refused, 'UNBUDGETED_CONTAINER'):
            k.validate(c, inv, rendered)

    def test_readback_accepts_kubernetes_resource_defaults_and_records_them(self):
        # LimitRange defaults, injected limits and canonical spellings are
        # enforced by Kubernetes; the readback records them and never refuses.
        c, inv, rendered, _ = self.requests_fixture()
        expected = k.template(rendered[1])['spec']
        for group, value in [('limits', {'cpu': '1'}), ('requests', {'cpu': '999m'})]:
            actual = copy.deepcopy(expected)
            actual['containers'][0]['resources'][group] = value
            projected, _ = k.admission_projection(expected, actual)
            self.assertTrue(k.subset(expected, projected))
            self.assertEqual(r.observed(actual)['containers'][actual['containers'][0]['name']][group], value)

    def test_normalized_or_defaulted_quantities_pass_with_raw_observations(self):
        c, inv, rendered, client = fixture()
        for obj in rendered:
            if obj['kind'] in k.WORKLOADS:
                for container in k.template(obj)['spec']['containers']:
                    container['resources'] = {
                        'requests': {'cpu': '0.1', 'memory': '0.0625Gi', 'ephemeral-storage': '0.0625Gi'},
                        'limits': {'cpu': '0.5', 'memory': '0.25Gi', 'ephemeral-storage': '0.125Gi'}}
        original_pods, original_objects = copy.deepcopy(client.pods), copy.deepcopy(client.objects)
        objects = k.validate(c, inv, rendered)
        result = k.observe(c, objects, client)
        self.assertEqual(result['pods']['cohort-0']['resources']['api']['requests'],
                         {'cpu': '100m', 'memory': '64Mi', 'ephemeral-storage': '64Mi'})
        self.assertEqual(client.pods, original_pods)
        self.assertEqual(client.objects, original_objects)
        for source in (client.objects['StatefulSet/cohort']['spec']['template']['spec'], client.pods[0]['spec']):
            source['containers'][0]['resources']['requests']['cpu'] = '101m'
            k.observe(c, objects, client)
            source['containers'][0]['resources']['requests']['cpu'] = '100m'
        client.pods[0]['spec']['overhead'] = {'cpu': '10m'}
        observed = k.observe(c, objects, client)['pods']['cohort-0']['observedResources']
        self.assertEqual(observed['overhead'], {'cpu': '10m'})

    def test_projection_keeps_the_rest_of_the_spec_compared(self):
        expected = {'containers': [{'name': 'api', 'image': 'a', 'resources': {
            'requests': {'cpu': '0.5', 'memory': '0.5Gi', 'ephemeral-storage': '1e6'}}}],
            'initContainers': [{'name': 'config', 'resources': {'requests': {'cpu': '0.001'}}, 'restartPolicy': 'Always'}]}
        actual = copy.deepcopy(expected)
        actual['containers'][0]['resources'] = {'requests': {'cpu': '500m'}, 'limits': {'cpu': '2'}}
        actual['overhead'] = {'cpu': '10m'}
        actual['resources'] = {'requests': {'cpu': '1'}}
        raw = copy.deepcopy(actual)
        projected, _ = k.admission_projection(expected, actual)
        self.assertTrue(k.subset(expected, projected))
        self.assertEqual(actual, raw)
        for mutate in (lambda x: x['containers'][0].update(image='b'),
                       lambda x: x['containers'][0].update(name='reordered'),
                       lambda x: x['initContainers'][0].update(restartPolicy='Never'),
                       lambda x: x['containers'].append({'name': 'injected'})):
            broken = copy.deepcopy(actual)
            mutate(broken)
            projected, _ = k.admission_projection(expected, broken)
            self.assertFalse(k.subset(expected, projected))

    def test_socket_cohort_and_other_replica_capability_have_distinct_refusals(self):
        c, inv, rendered, client = fixture()
        rendered[1]['spec']['replicas'] = 2
        with self.assertRaisesRegex(k.Refused, 'ONE_COHORT_REPLICA'):
            k.validate(c, inv, rendered)
        rendered[1]['spec']['replicas'] = 1
        rendered[2]['spec']['replicas'] = 2
        with self.assertRaisesRegex(k.Refused, 'WORKLOAD_REPLICA_CENSUS_UNSUPPORTED:StatefulSet/postgres'):
            k.validate(c, inv, rendered)
        rendered[2]['spec']['replicas'] = 1
        objects = k.validate(c, inv, rendered)
        client.objects['StatefulSet/postgres']['spec']['replicas'] = 2
        with self.assertRaisesRegex(k.Refused, 'WORKLOAD_REPLICA_CENSUS_UNSUPPORTED'):
            k.observe(c, objects, client)

    def test_quantity_forms_and_invalid_values(self):
        for value, cpu, expected in [('0.5', True, 500), ('500m', True, 500),
                                     ('0.5Gi', False, 536870912), ('1e3', False, 1000),
                                     ('250m', False, 1)]:
            self.assertEqual(r.quantity(value, cpu, k.need), expected)
        for value in ('NaN', 'Infinity', '-1', '1banana', '1e999999', True):
            with self.assertRaises(k.Refused):r.quantity(value, False, k.need)

    def test_phase_requests_count_sidecars_later_init_and_overhead(self):
        def container(name, cpu, mem, disk, sidecar=False):
            return {'name': name, 'resources': {'requests': {'cpu': cpu, 'memory': mem,
                    'ephemeral-storage': disk}}, **({'restartPolicy': 'Always'} if sidecar else {})}
        spec = {'containers': [container('app', '200m', '300Mi', '3Mi')],
                'initContainers': [container('sidecar', '100m', '100Mi', '1Mi', True),
                                   container('setup', '600m', '10Mi', '2Mi')],
                'overhead': {'cpu': '10m', 'memory': '1Mi', 'ephemeral-storage': '1Mi'}}
        self.assertEqual(r.pod_budget(spec, r.REQUESTS, k.need),
                         {'millicpus': 710, 'memoryBytes': 401 * 2**20, 'ephemeralBytes': 5 * 2**20})
        spec['resources'] = {'requests': {'memory': '1Gi'}}
        with self.assertRaisesRegex(k.Refused, 'POD_LEVEL_RESOURCE_ACCOUNTING_UNSUPPORTED'):
            r.pod_budget(spec, r.REQUESTS, k.need)

    def test_request_fit_is_not_rejected_by_larger_limits(self):
        fixture_case = matrix_tests.Matrix();fixture_case.setUp();self.addCleanup(fixture_case.doCleanups)
        case = fixture_case
        case.a['nodeCeilings']['synthetic-node']['millicpus'] = 1000
        case.release()
        with self.assertRaisesRegex(k.Refused, 'MATRIX_NODE_HEADROOM_EXCEEDED'):
            matrix.allocation(case.value, case.entries)
        case.a['resourceAccounting'] = case.value['resourceAccounting'] = r.REQUESTS
        preflight = case.root / 'preflight.json'
        k.write(preflight, {'offline':'PASS', 'commissioning':'PREFLIGHT_ONLY',
                            'trialEnvelope':{'resourceAccounting':r.REQUESTS}})
        case.a['preflight']['sha256'] = k.digest(preflight)
        for d, c, _, _ in case.entries:
            c['resourceAccounting'] = r.REQUESTS
            k.write(d / 'run.json', c)
        for row, (d, _, _, _) in zip(case.a['fixtures'], case.entries):
            row['runSha256'] = k.digest(d / 'run.json')
        case.release()
        _, accounting = matrix.allocation(case.value, case.entries)
        self.assertEqual(accounting['nodes']['synthetic-node']['millicpus'], 800)
        self.assertIn('not a hard usage bound', accounting['accounting'])
        with patch.object(k, 'load', side_effect=lambda path: next((d,c,o) for d,c,o,_ in case.entries if str(d)==path)):
            planned = e.matrix_plan(case.value)
        self.assertIn('aggregateRequests', planned)
        self.assertNotIn('conservativeAggregateLimits', planned)
        case.a['resourceAccounting'] = r.LIMITS;case.release()
        with self.assertRaisesRegex(k.Refused, 'RESOURCE_ACCOUNTING_MISMATCH'):
            matrix.allocation(case.value, case.entries)


if __name__ == '__main__':unittest.main()
