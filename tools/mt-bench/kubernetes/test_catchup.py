"""Kubernetes all-tenant catch-up: inert fixtures and break-it controls.

No kubectl, node, cluster or entered run is touched. The guarded calls
(`observe`, `selected_pod`, `postgres_read`, pod exec) and the pinned node
reader are replaced by synthetic stand-ins that return the shapes the real
ones return. The evaluator_catchup assessor and the outcome gate are real.
"""
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import kube_adapter as k
import catchup
import evaluator_progress as p
import outcome_gate as g
from test_adapter import A, B, fixture
from test_preload import page

IDS = sorted([A, B])
NS = {'uid':'namespace-uid'}


def durable(stuck):
    """Legacy (non-native) durable rows: B's accepted clock is not yet completed when stuck."""
    rows = []
    for tenant in IDS:
        done = '3' if stuck and tenant == B else '5'
        rows.append({'tenant':tenant, 'writerClock':'5', 'observed':{'clock':'5'}, 'completed':{'clock':done},
                     'outputRevision':'1', 'restoreGeneration':'1'})
    return rows


class Fake:
    """Stand-ins with the real call shapes; records what reached the node reader."""
    def __init__(self, stuck=False, sql_error=False):
        self.stuck, self.sql_error, self.snapshots = stuck, sql_error, 0

    def inspection(self, *args, **kwargs):
        # The real helper stamps each page with Date.now() inside the call.
        return (json.dumps({**page(), 'observedAt':int(time.time() * 1000)}) + '\n').encode()

    def node(self, argv, *, input, capture_output, timeout):
        value = json.loads(input)
        if value['mode'] == 'queries':
            out = ['SELECT synthetic_progress(%d)' % i for i, _ in enumerate(value['batches'])]
        else:
            self.snapshots += 1
            out = {'kind':'evaluator-durable-progress-v1', 'reader':value['config']['binding'], 'rows':value['rows']}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out).encode())

    def postgres_read(self, client, pod, container, query):
        if self.sql_error:
            raise RuntimeError('synthetic transport loss')
        return ''.join(json.dumps(row) + '\n' for row in durable(self.stuck))


class Catchup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def stage(self, fake, *, accounting=True, joined_ago=200, drain=4, module=catchup):
        d = Path(self.tmp.name) / ('run-%d' % len(list(Path(self.tmp.name).iterdir())))
        out = d / 'load'
        out.mkdir(parents=True)
        c, _, _, _ = fixture()
        binding = {'kind':'evaluator-work-v2', 'pair':c['pins']['pair'], 'imageId':c['pins']['appImageId'],
                   'instrument':c['pins']['instrument']}
        c.update(tenants=2, completion={'kind':'evaluator-work-v2', 'binding':binding},
                 workload={'drainSeconds':drain, 'drainObservation':{'intervalSeconds':1}})
        c['driver'] = {**c.get('driver', {}), 'node':'/inert/node'}
        (out / 'runid').write_text('synthetic-run')
        if accounting:
            k.write(out / 'probe-accounting.json', {'version':2, 'kind':'m7-discovery-probe-accounting', 'runId':'synthetic-run',
                    'roster':IDS, 'admissionsClosed':True, 'attempts':2,
                    'byTenant':{t:{'attempts':1, 'accepted':1, 'refused':0, 'uncertain':0, 'pending':0} for t in IDS}})
        reference = p.round_view(['evaluator'], IDS, fake.inspection)
        k.write(out / 'progress-before.json', reference)
        client = SimpleNamespace(call=fake.inspection)
        collector = lambda *a: module.Collector(*a, run=fake.node)
        with patch.object(k, 'active_baseline', return_value={}), \
             patch.object(k, 'observe', return_value={'namespace':NS, 'pods':{}}), \
             patch.object(k, 'selected_pod', return_value=('pod', 'container')), \
             patch.object(k, 'postgres_read', side_effect=fake.postgres_read):
            value = module.run(d, out, c, {}, client, IDS, writers_joined_ns=time.monotonic_ns() - joined_ago * 10**9,
                               drain_started=time.time(), collector=collector)
        return out, value

    def gate(self, out):
        return g.catchup(k.document(out / 'evaluator-catchup.json'), IDS)

    def test_completed_tenants_pass_from_the_storage_floor(self):
        out, value = self.stage(Fake(), joined_ago=5)
        self.assertEqual(value['verdict'], 'PASS', value.get('code'))
        self.assertEqual(value['classifications']['COMPLETED'], 2)
        self.assertEqual(self.gate(out)['verdict'], 'PASS')

    def test_stuck_tenant_fails(self):
        out, value = self.stage(Fake(stuck=True))
        self.assertEqual(value['byTenant'][B]['status'], 'PENDING')
        gate = self.gate(out)
        self.assertEqual(gate['verdict'], 'FAIL')
        self.assertIn('M7_OUTCOME_CATCHUP_STUCK', gate['codes'])

    def test_missing_capture_is_unmeasured(self):
        out, value = self.stage(Fake(sql_error=True))
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertNotIn('byTenant', value)
        self.assertEqual(self.gate(out)['verdict'], 'UNMEASURED')
        out, value = self.stage(Fake(), accounting=False)
        self.assertEqual((value['verdict'], value['code']), ('UNMEASURED', 'M7_DRAIN_PROBE_PENDING'))
        self.assertEqual(g.catchup(None, IDS)['verdict'], 'UNMEASURED')

    def test_raw_storage_and_inspection_are_written_before_decode(self):
        out, _ = self.stage(Fake(), joined_ago=5)
        sql = out / 'catchup' / 'round-0000-sql.private.jsonl'
        self.assertEqual([json.loads(line)['tenant'] for line in sql.read_text().splitlines()], IDS)
        self.assertEqual(sql.stat().st_mode & 0o777, 0o600)
        self.assertTrue((out / 'catchup' / 'round-0000-inspection.private.jsonl').is_file())

    def test_drain_window_and_work_deadline_bound_the_collector(self):
        out, value = self.stage(Fake(), drain=0)
        self.assertEqual((value['verdict'], value['code']), ('UNMEASURED', 'M7_DRAIN_DEADLINE'))
        self.assertFalse((out / 'catchup').exists(), 'no read before the window check')


# ------------------------------------------------------------ break-it controls

def ablated(module, needle, replacement):
    source = Path(module.__file__).read_text()
    if source.count(needle) != 1:
        raise AssertionError('control needle not unique: ' + needle)
    clone = types.ModuleType(module.__name__)
    clone.__file__ = module.__file__
    exec(compile(source.replace(needle, replacement), module.__name__ + '_ablation', 'exec'), clone.__dict__)
    return clone


class BreakIt(unittest.TestCase):
    def check(self, name, criterion, *, module=None, shared=None):
        """green on the real code, red on the ablation, green after restore."""
        self.assertTrue(criterion(catchup), name + ': not green before')
        if shared is not None:
            import evaluator_catchup
            with patch.dict(sys.modules, {'evaluator_catchup':shared}):
                red = criterion(catchup)
        else:
            red = criterion(module)
        self.assertFalse(red, name + ': stayed green when the branch was removed')
        self.assertTrue(criterion(catchup), name + ': not green after restore')
        print('RED_RESTORED k8s-catchup ' + name)

    def run_case(self, module, **kwargs):
        case = Catchup('test_stuck_tenant_fails')
        case.setUp()
        try:
            return case.stage(kwargs.pop('fake'), module=module, **kwargs), case
        finally:
            pass

    def test_stuck_tenant_control(self):
        import evaluator_catchup
        def criterion(module):
            (out, _), case = self.run_case(module, fake=Fake(stuck=True))
            try:
                return case.gate(out)['verdict'] == 'FAIL'
            finally:
                case.tmp.cleanup()
        broken = ablated(evaluator_catchup, "        blocked=bool(pending) or", "        blocked=False and")
        self.check('stuck-tenant-fails', criterion, shared=broken)

    def test_missing_capture_control(self):
        def criterion(module):
            (out, value), case = self.run_case(module, fake=Fake(sql_error=True))
            try:
                return value['verdict'] == 'UNMEASURED'
            finally:
                case.tmp.cleanup()
        broken = ablated(catchup, "        value.update(verdict='UNMEASURED', code=safe, errorType=type(error).__name__)",
                         "        value.update(verdict='PASS', code=None)")
        self.check('missing-capture-unmeasured', criterion, module=broken)

    def test_raw_first_control(self):
        def criterion(module):
            (out, _), case = self.run_case(module, fake=Fake(), joined_ago=5)
            try:
                sql = out / 'catchup' / 'round-0000-sql.private.jsonl'
                return sql.is_file() and sql.stat().st_size > 0
            finally:
                case.tmp.cleanup()
        broken = ablated(catchup, "                stream.write(data)\n", "")
        self.check('raw-storage-first', criterion, module=broken)

    def test_storage_basis_control(self):
        """The floor must come from storage: dropping the SQL rows cannot pass."""
        def criterion(module):
            (out, value), case = self.run_case(module, fake=Fake(), joined_ago=5)
            try:
                return value['verdict'] == 'PASS'
            finally:
                case.tmp.cleanup()
        self.assertTrue(criterion(catchup))
        broken = ablated(catchup, "                rows.extend(json.loads(line) for line in raw.splitlines() if line)\n", "")
        self.check('storage-floor-required', lambda m: criterion(m), module=broken)


if __name__ == '__main__':
    unittest.main()
