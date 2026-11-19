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
from test_adapter import A, B, fixture, iso
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
            self.batches = value['batches']
            out = ['SELECT synthetic_progress(%d)' % i for i, _ in enumerate(value['batches'])]
        else:
            self.snapshots += 1
            out = {'kind':'evaluator-durable-progress-v1', 'reader':value['config']['binding'], 'rows':value['rows']}
        return SimpleNamespace(returncode=0, stdout=json.dumps(out).encode())

    def postgres_read(self, client, pod, container, query, **kwargs):
        if self.sql_error:
            raise RuntimeError('synthetic transport loss')
        return ''.join(json.dumps(row) + '\n' for row in durable(self.stuck))


class Catchup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def stage(self, fake, *, accounting=True, joined_ago=200, drain=4, round_seconds=None,
              work_seconds=None, sql_max_bytes=None, module=catchup):
        d = Path(self.tmp.name) / ('run-%d' % len(list(Path(self.tmp.name).iterdir())))
        out = d / 'load'
        out.mkdir(parents=True)
        c, _, _, _ = fixture()
        binding = {'kind':'evaluator-work-v2', 'pair':c['pins']['pair'], 'imageId':c['pins']['appImageId'],
                   'instrument':c['pins']['instrument']}
        c.update(tenants=2, completion={'kind':'evaluator-work-v2', 'binding':binding},
                 workload={'drainSeconds':drain, 'drainObservation':{'intervalSeconds':1}})
        if round_seconds is not None:
            c['workload']['drainObservation']['roundSeconds'] = round_seconds
        if sql_max_bytes is not None:
            c['workload']['drainObservation']['sqlMaxBytes'] = sql_max_bytes
        if work_seconds is not None:
            c['deadlines']['workUntil'] = iso(time.time() + work_seconds)
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

    def timed_stage(self, *, round_seconds=60, drain=60, work_seconds=120, module=catchup, advancing=False):
        """A real collector round with 25 synthetic seconds of SQL transport."""
        import evaluator_catchup as shared
        clock = SimpleNamespace(wall=time.time(), mono=time.monotonic())
        fake = Fake()
        read = fake.postgres_read
        def postgres_read(*args, **kwargs):
            raw = read(*args, **kwargs)
            if advancing:
                for line in raw.splitlines(keepends=True):
                    clock.wall += 12.5
                    clock.mono += 12.5
                    kwargs['rows'].feed(line.encode())
            else:
                clock.wall += 25
                clock.mono += 25
            return raw
        fake.postgres_read = postgres_read
        observe = shared.observe
        def bounded_observe(*args, **kwargs):
            return observe(*args, **kwargs, monotonic_ns=lambda:int(clock.mono * 10**9),
                           sleep=lambda _:self.fail('completed capture must not sleep'))
        with patch.object(time, 'time', side_effect=lambda:clock.wall), \
             patch.object(time, 'time_ns', side_effect=lambda:int(clock.wall * 10**9)), \
             patch.object(time, 'monotonic', side_effect=lambda:clock.mono), \
             patch.object(time, 'monotonic_ns', side_effect=lambda:int(clock.mono * 10**9)), \
             patch.object(time, 'sleep', side_effect=AssertionError('inert capture must not sleep')), \
             patch.object(shared, 'observe', side_effect=bounded_observe):
            return self.stage(fake, joined_ago=5, drain=drain, round_seconds=round_seconds,
                              work_seconds=work_seconds, module=module)

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

    def test_configured_long_round_reaches_storage_and_outcome_gate(self):
        out, value = self.timed_stage()
        self.assertEqual(value['verdict'], 'PASS', value.get('code'))
        self.assertEqual(value['observationWindow']['collectorPolicy']['roundSeconds'], 60)
        self.assertEqual(value['boundaryCost']['wallSeconds'], 25)
        self.assertEqual(value['observationWindow']['selectedClinicalDeadlineSeconds'], 120)
        self.assertEqual(self.gate(out)['verdict'], 'PASS')

    def test_advancing_rows_outlive_one_inactivity_window(self):
        out, value = self.timed_stage(round_seconds=20, advancing=True)
        self.assertEqual(self.gate(out)['verdict'], 'PASS', value['code'])
        self.assertEqual(value['boundaryCost']['wallSeconds'],25)
        self.assertEqual(value['boundaryCost']['maxInactivitySeconds'],12.5)
        out, value = self.timed_stage(round_seconds=20, advancing=True, work_seconds=21)
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertNotEqual(self.gate(out)['verdict'], 'PASS')

    def test_shorter_selected_round_still_refuses_slow_collection(self):
        out, value = self.timed_stage(round_seconds=20)
        self.assertEqual((value['verdict'], value['code']),
                         ('UNMEASURED', 'M7_OPPORTUNITY_DEADLINE'))
        self.assertEqual(value['observationWindow']['collectorPolicy']['roundSeconds'], 20)
        self.assertTrue((out / 'catchup' / 'round-0000-sql.private.jsonl').is_file())

    def test_long_selected_round_cannot_extend_outer_drain_or_work_window(self):
        for limits in ({'drain':10}, {'work_seconds':10}):
            with self.subTest(**limits):
                _, value = self.timed_stage(**limits)
                self.assertEqual((value['verdict'], value['code']),
                                 ('UNMEASURED', 'K8S_CATCHUP_ROUND_DEADLINE'))
                self.assertAlmostEqual(value['observationWindow']['effectiveSeconds'], 10, places=5)
                self.assertEqual(value['observationWindow']['collectorPolicy']['roundSeconds'], 60)
                self.assertEqual(value['observationWindow']['selectedClinicalDeadlineSeconds'], 120)

    def test_sql_byte_budget_can_extend_default_and_still_refuses_oversized_response(self):
        fake = Fake()
        read = fake.postgres_read
        fake.postgres_read = lambda *a,**kw:' ' * (17 * 1024 * 1024) + read(*a,**kw)
        _, refused = self.stage(fake, joined_ago=5)
        self.assertEqual((refused['verdict'],refused['code']),('UNMEASURED','M7_OPPORTUNITY_BYTE_BOUND'))
        _, restored = self.stage(fake, joined_ago=5, sql_max_bytes=32*1024*1024)
        self.assertEqual(restored['verdict'],'PASS',restored.get('code'))
        self.assertGreater(restored['boundaryCost']['rawSqlBytes'],16*1024*1024)
        self.assertEqual(restored['boundaryCost']['sqlQueries'],1)

    def timed_inspection_stage(self, module=catchup):
        # Fast SQL followed by slow inspection was formerly credited beyond
        # roundSeconds. Keep real storage/due/health decoding in the path.
        fake = Fake();read = fake.inspection;calls = [0]
        clock = SimpleNamespace(wall=time.time(),mono=time.monotonic())
        def inspection(*a,**kw):
            calls[0]+=1
            if calls[0]>1:clock.wall+=25;clock.mono+=25
            return read(*a,**kw)
        fake.inspection = inspection
        with patch.object(time,'time',side_effect=lambda:clock.wall), \
             patch.object(time,'time_ns',side_effect=lambda:int(clock.wall*1e9)), \
             patch.object(time,'monotonic',side_effect=lambda:clock.mono), \
             patch.object(time,'monotonic_ns',side_effect=lambda:int(clock.mono*1e9)):
            return self.stage(fake,joined_ago=5,drain=60,round_seconds=20,module=module)

    def test_inspection_and_final_census_cannot_overrun_round(self):
        out,value = self.timed_inspection_stage()
        self.assertEqual((value['verdict'],value['code']),('UNMEASURED','M7_OPPORTUNITY_DEADLINE'))
        self.assertEqual(value['refusedCapture']['cost']['wallSeconds'],25)
        self.assertTrue((out/'catchup/round-0000-inspection.private.jsonl').is_file())

    def test_runtime_foreign_ownership_and_missing_jobs_refuse(self):
        import copy
        for label,change in [('runtime',lambda x:x['view'].update(runtimeId='55555555-5555-4555-8555-555555555555')),
                             ('foreign',lambda x:x['view']['tenants'][0].update(admitted=False)),
                             ('jobs',lambda x:x['view']['tenants'][0].pop('jobs'))]:
            with self.subTest(label=label):
                fake=Fake();calls=[0]
                def inspection(*a,**kw):
                    value=copy.deepcopy(page());calls[0]+=1
                    if calls[0]>1:change(value)
                    return (json.dumps({**value,'observedAt':int(time.time()*1000)})+'\n').encode()
                fake.inspection=inspection
                _,value=self.stage(fake,joined_ago=5)
                self.assertNotEqual(value['verdict'],'PASS',label)
        _,restored=self.stage(Fake(),joined_ago=5)
        self.assertEqual(restored['verdict'],'PASS')

    def test_disposable_cache_generation_change_keeps_existing_semantics(self):
        fake=Fake();calls=[0]
        def inspection(*a,**kw):
            calls[0]+=1
            value=page(generation=calls[0])
            return (json.dumps({**value,'observedAt':int(time.time()*1000)})+'\n').encode()
        fake.inspection=inspection
        _,value=self.stage(fake,joined_ago=5)
        self.assertEqual(value['verdict'],'PASS',value.get('code'))


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

    def test_configured_round_budget_control(self):
        broken = ablated(catchup, '        deadline = time.monotonic() + timeout\n',
                         '        deadline = time.monotonic() + min(timeout, self.o.ROUND_SECONDS)\n')
        def criterion(module):
            case = Catchup('test_configured_long_round_reaches_storage_and_outcome_gate')
            case.setUp()
            try:
                _, value = case.timed_stage(module=module)
                if module is broken:
                    self.assertEqual((value['verdict'], value['code']),
                                     ('UNMEASURED', 'K8S_CATCHUP_ROUND_DEADLINE'))
                    self.assertEqual(value['observationWindow']['collectorPolicy']['roundSeconds'], 60)
                return value['verdict'] == 'PASS'
            finally:
                case.tmp.cleanup()
        self.check('configured-round-budget', criterion, module=broken)

    def test_inspection_inactivity_control(self):
        import observation_rows
        def criterion(module):
            case = Catchup('test_inspection_and_final_census_cannot_overrun_round')
            case.setUp()
            try:
                _, value = case.timed_inspection_stage(module)
                return value['code'] == 'M7_OPPORTUNITY_DEADLINE'
            finally:
                case.tmp.cleanup()
        self.assertTrue(criterion(catchup))
        with patch.object(observation_rows.Rows, 'check', return_value=60):
            self.assertFalse(criterion(catchup))
        self.assertTrue(criterion(catchup))

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
        broken = ablated(catchup, "                    stream.write(data)\n", "")
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
