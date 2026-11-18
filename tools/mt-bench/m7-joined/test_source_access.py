"""Actual source counter, private-client and no-reacquisition controls; no actors."""
import copy
import json
from pathlib import Path
import subprocess
import types
import unittest
from unittest import mock
import source_access as s

A = '11111111-1111-4111-8111-111111111111'
R = '22222222-2222-4222-8222-222222222222'
S = '33333333-3333-4333-8333-333333333333'
OWNER = 'a' * 32
BINDING = {'pair': {'core': 'b' * 40, 'deploy': 'c' * 40},
           'imageId': 'sha256:' + 'd' * 64, 'instrument': 'e' * 64, 'hostIdentity': 'f' * 64}


class Clock:
    def __init__(self): self.now = 1000000
    def __call__(self): self.now += 1000000; return self.now


def census(step=0):
    return {'snapshotAttempts': 3 + step, 'snapshotCompleted': 3 + step,
            'catalogueAttempts': 10, 'catalogueCompleted': 10,
            'dataAttempts': 12, 'dataCompleted': 12,
            'residentTenants': 2, 'residentEncodedBytes': 4096, 'evictions': 0}


class SourceAccess(unittest.TestCase):
    def setUp(self): self.clock = Clock(); self.calls = []

    def capture(self, values=None, *, runtime=None, services=None, fetch=None, **kwargs):
        services = services or ['evaluator']
        values = census() if values is None else values
        def read(service, ids, queries, budget, timeout):
            self.calls.append((service, ids, queries, budget, timeout))
            return json.dumps({'selected': ids, 'runtimeId': runtime or (R if services.index(service) == 0 else S),
                               'sourceAccess': values, 'observedAt': 1700000000000})
        return s.capture(fetch or read, [A], services, BINDING, OWNER,
                         monotonic_ns=self.clock, **kwargs)

    def pair(self): return self.capture(), self.capture()

    def assess(self, a, b, criterion='timer-only'): return s.assess(a, b, BINDING, OWNER, criterion=criterion)

    def test_timer_only_uses_actual_access_not_checkpoint_and_restores(self):
        a, b = self.pair(); self.assertEqual(self.assess(a, b)['verdict'], 'PASS')
        # An unchanged checkpoint cannot conceal a real source call. These
        # checkpoint values are deliberately outside the accessor contract.
        checkpoint_before = checkpoint_after = '42'
        broken = copy.deepcopy(b)
        broken['rows']['evaluator']['sourceAccess']['snapshotAttempts'] += 1
        broken['rows']['evaluator']['sourceAccess']['snapshotCompleted'] += 1
        self.assertEqual(checkpoint_before, checkpoint_after)
        result = self.assess(a, broken)
        self.assertEqual((result['verdict'], result['code']), ('FAIL', 'M7_SOURCE_ACCESS_DURING_TIMER'))
        self.assertEqual(result['totals']['snapshotAttempts'], 1)
        self.assertEqual(self.assess(a, b)['verdict'], 'PASS')

    def test_each_actual_query_category_independently_breaks_timer_criterion(self):
        a, b = self.pair()
        for category in s.CATEGORIES:
            broken = copy.deepcopy(b)
            for suffix in ('Attempts', 'Completed'):broken['rows']['evaluator']['sourceAccess'][category + suffix] += 1
            self.assertEqual(self.assess(a, broken)['verdict'], 'FAIL', category)
            self.assertEqual(self.assess(a, broken, 'acquisition')['verdict'], 'PASS', category)
            self.assertEqual(self.assess(a, b)['verdict'], 'PASS')

    def test_positive_acquisition_and_pending_without_completed_work(self):
        a = self.capture(); b = self.capture(census(1))
        result = self.assess(a, b, 'acquisition'); self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['totals']['snapshotAttempts'], 1)
        self.assertEqual(result['totals']['snapshotCompleted'], 1)
        pending = copy.deepcopy(b); pending['rows']['evaluator']['sourceAccess']['snapshotCompleted'] -= 1
        self.assertEqual(self.assess(a, pending, 'acquisition')['code'], 'M7_SOURCE_ACCESS_NOT_OBSERVED')
        self.assertEqual(self.assess(a, a, 'acquisition')['verdict'], 'UNMEASURED')
        self.assertIn('collectorCost', result); self.assertEqual(result['limits'], s.LIMITS)

    def test_missing_reset_wrong_runtime_source_owner_observer_clock_and_cost_refuse(self):
        a, b = self.pair()
        cases = [
            ('missing counter', lambda x: x['rows']['evaluator']['sourceAccess'].pop('dataAttempts'), 'COUNTERS', 'UNMEASURED'),
            ('counter reset', lambda x: x['rows']['evaluator']['sourceAccess'].update(snapshotAttempts=2, snapshotCompleted=2), 'RESET', 'FAIL'),
            ('wrong incarnation', lambda x: x['rows']['evaluator'].update(runtimeId=S), 'INCARNATION', 'UNMEASURED'),
            ('wrong source', lambda x: x['source']['pair'].update(core='0' * 40), 'BINDING', 'FAIL'),
            ('wrong owner', lambda x: x.update(owner='0' * 32), 'OWNER', 'FAIL'),
            ('wrong observer', lambda x: x.update(observerId=S), 'OBSERVER', 'UNMEASURED'),
            ('overlapping bracket', lambda x: x.update(readWindow=copy.deepcopy(a['readWindow'])), 'CLOCK', 'UNMEASURED'),
            ('missing cost', lambda x: x.pop('cost'), 'COST', 'UNMEASURED'),
            ('wrong limit', lambda x: x['limits'].update(queries=1000), 'LIMITS', 'UNMEASURED'),
            ('unbounded residency', lambda x: x['rows']['evaluator']['sourceAccess'].update(residentTenants=10001), 'RESIDENCY_BOUND', 'FAIL')]
        for label, change, code, verdict in cases:
            with self.subTest(label=label):
                broken = copy.deepcopy(b); change(broken); result = self.assess(a, broken)
                self.assertEqual(result['code'], 'M7_SOURCE_ACCESS_' + code)
                self.assertEqual(result['verdict'], verdict); self.assertEqual(self.assess(a, b)['verdict'], 'PASS')

    def test_malformed_counter_values_and_residency_refuse(self):
        for value in (-1, True, 1.5, float('nan'), float('inf'), 9007199254740992, '3'):
            bad = census(); bad['snapshotAttempts'] = value
            self.assertEqual(self.capture(bad)['code'], 'M7_SOURCE_ACCESS_COUNTERS')
        bad = census(); bad['snapshotCompleted'] = 4
        self.assertEqual(self.capture(bad)['code'], 'M7_SOURCE_ACCESS_COUNTERS')
        bad = census(); bad['residentEncodedBytes'] = 268435457
        self.assertEqual(self.capture(bad)['code'], 'M7_SOURCE_ACCESS_RESIDENCY_BOUND')
        bad = census(); bad['extra'] = 1
        self.assertEqual(self.capture(bad)['code'], 'M7_SOURCE_ACCESS_COUNTERS')

    def test_capture_retains_partial_service_and_attempted_cost(self):
        def fetch(service, ids, queries, budget, timeout):
            if service == 'evaluator-b':raise RuntimeError('secret-do-not-retain')
            return json.dumps({'selected': ids, 'runtimeId': R, 'sourceAccess': census(), 'observedAt': 1})
        value = self.capture(services=['evaluator-a', 'evaluator-b'], fetch=fetch)
        self.assertEqual(value['verdict'], 'UNMEASURED'); self.assertEqual(value['cost']['queries'], 2)
        self.assertEqual(list(value['rows']), ['evaluator-a']); self.assertGreater(value['cost']['responseBytes'], 0)
        self.assertNotIn('secret-do-not-retain', json.dumps(value))
        self.assertEqual(self.assess(value, value)['code'], 'M7_SOURCE_ACCESS_UNAVAILABLE')

    def test_source_and_selector_preflight_before_port_and_actual_byte_time_bounds(self):
        with mock.patch.dict(BINDING, instrument='bad'):
            with self.assertRaisesRegex(s.p.Refused, 'BINDING'):self.capture()
        self.assertEqual(self.calls, [])
        for ids in ([], [A] * 2, [A] * 129, ['not-a-uuid']):
            with self.assertRaisesRegex(s.p.Refused, 'SELECTOR'):
                s.capture(lambda *_: self.fail('port called'), ids, ['evaluator'], BINDING, OWNER)
        large = self.capture(fetch=lambda *_: b'x' * 1048577)
        self.assertEqual(large['code'], 'M7_SOURCE_ACCESS_BYTE_BOUND')
        def late(*args):
            self.clock.now += 21000000000
            return json.dumps({'selected': [A], 'runtimeId': R, 'sourceAccess': census(), 'observedAt': 1})
        value = self.capture(fetch=late); self.assertEqual(value['code'], 'M7_SOURCE_ACCESS_DEADLINE')
        self.assertIn('evaluator', value['rows'], 'completed segment survives later deadline refusal')

    def test_two_workers_are_separate_incarnations_and_residency_gauge_can_fall(self):
        a = self.capture(services=['evaluator-a', 'evaluator-b'])
        b = self.capture(services=['evaluator-a', 'evaluator-b'])
        # Real independent workers have distinct runtime ids. Both snapshots
        # must retain each service's own incarnation.
        a['rows']['evaluator-b']['runtimeId'] = b['rows']['evaluator-b']['runtimeId'] = S
        b['rows']['evaluator-b']['sourceAccess'].update(residentTenants=1, residentEncodedBytes=100, evictions=1)
        result = self.assess(a, b); self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['totals']['evictions'], 1)
        self.assertEqual(set(result['byService']), {'evaluator-a', 'evaluator-b'})

    def test_aliased_workers_refuse_and_source_capture_has_no_mutable_binding_alias(self):
        value = self.capture(services=['evaluator-a', 'evaluator-b'], runtime=R)
        self.assertEqual(value['verdict'], 'FAIL'); self.assertEqual(value['code'], 'M7_SOURCE_ACCESS_INSTANCE')
        self.assertEqual(list(value['rows']), ['evaluator-a'])
        a, b = self.pair()
        with mock.patch.dict(BINDING['pair'], core='0' * 40):
            self.assertNotEqual(a['source'], BINDING)
            self.assertNotEqual(b['source'], BINDING)
        self.assertEqual(self.assess(a, b)['verdict'], 'PASS')

    def test_actual_timer_predicate_ablation_makes_reacquisition_check_red(self):
        source = Path(s.__file__).read_text(); needle = "'FAIL' if attempts or completed else 'PASS'"
        self.assertEqual(source.count(needle), 1)
        broken = dict(s.__dict__); exec(compile(source.replace(needle, "'PASS'"), s.__file__, 'exec'), broken)
        a = self.capture(); b = self.capture(census(1))
        def criterion(api):self.assertEqual(api(a, b, BINDING, OWNER, criterion='timer-only')['verdict'], 'FAIL')
        criterion(s.assess)
        with self.assertRaises(AssertionError):criterion(broken['assess'])
        criterion(s.assess); self.assertEqual(self.assess(*self.pair())['verdict'], 'PASS')

    def test_collect_reuses_exact_existing_source_owner_and_compose_ports(self):
        calls = []
        def compose(directory, *argv, **kwargs):
            calls.append((directory, argv, kwargs)); text = kwargs['input'].decode()
            self.assertIn('const M7_SOURCE_IDS=' + json.dumps([A]), text)
            self.assertIn('diagnostics:"source-access-v1"', text)
            return json.dumps({'selected': [A], 'runtimeId': R, 'sourceAccess': census(), 'observedAt': 1})
        adapter = types.SimpleNamespace(assert_owned=mock.Mock(), verify=mock.Mock(), progress_services=lambda _: ['evaluator'], compose=compose)
        m = {**copy.deepcopy(BINDING), 'instrument': {'sha256': BINDING['instrument']}, 'owner': OWNER}
        value = s.collect(adapter, Path('/synthetic'), m, [A])
        self.assertEqual(value['verdict'], 'PASS')
        adapter.assert_owned.assert_called_once_with(m); adapter.verify.assert_called_once_with(Path('/synthetic'), m)
        self.assertEqual(calls[0][1], ('exec', '-T', 'evaluator', 'node', '-'))
        self.assertLessEqual(calls[0][2]['timeout'], 15)


PORT = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8'),mode=process.argv[2];
const ids=['11111111-1111-4111-8111-111111111111'],calls=[],stdout=[],stderr=[],timers=[];
let cleared=0;
const ctx={M7_SOURCE_IDS:mode==='bad-selector'?['bad']:ids,M7_SOURCE_QUERY_BUDGET:1,M7_SOURCE_BYTE_BUDGET:mode==='small-budget'?1:1048576,Date,Buffer,JSON,Set,Number,Object,Error,
 setTimeout(fn,ms){timers.push(ms);return 1;},clearTimeout(){cleared++;},
 process:{stdout:{write(s){stdout.push(s);return true;}},stderr:{write(s){stderr.push(s);}},exit(){throw Error('unexpected watchdog');}},
 require(name){calls.push(name);
  if(name==='./deploy/multitenant/service-environment')return{read:()=>({NS_SERVE_INTERNAL_SOCKET:'/synthetic/evaluator.sock',OTHER_SECRET:'must-not-forward'})};
  if(name==='./lib/server/internal-api/listener-config')return{resolve(roles,environment){assert.deepEqual([...roles],['evaluator']);assert.deepEqual(Object.keys(environment),['NS_SERVE_INTERNAL_SOCKET']);return{peer(role,bounds){assert.equal(role,'evaluator');assert.equal(bounds.maxBytes,1048576);assert.equal(bounds.timeoutMs,5000);return 'synthetic-peer';}};}};
  if(name==='./lib/server/internal-api/clients')return{evaluatorInspection(peer){assert.equal(peer,'synthetic-peer');return{async inspectEvaluator(request){assert.equal(JSON.stringify(request),JSON.stringify({tenants:ids,diagnostics:'source-access-v1'}));if(mode==='refused')throw Error('secret-internal-error');return{kind:'evaluator',runtimeId:'22222222-2222-4222-8222-222222222222',diagnostics:{sourceAccess:{snapshotAttempts:1,snapshotCompleted:1,catalogueAttempts:2,catalogueCompleted:2,dataAttempts:3,dataCompleted:3,residentTenants:1,residentEncodedBytes:1024,evictions:0}},clinicalOutput:{secret:'never-retained'}};}};}};
  throw Error('unexpected module '+name);
 }};
(async()=>{await vm.runInNewContext(source,ctx);if(mode==='positive'){assert.equal(stderr.length,0);assert.equal(stdout.length,1);const x=JSON.parse(stdout[0]);assert.equal(x.sourceAccess.dataAttempts,3);assert.deepEqual(Object.keys(x).sort(),['selected','runtimeId','sourceAccess','observedAt'].sort());assert.equal(cleared,1);assert.deepEqual(timers,[16000]);}else{assert.equal(ctx.process.exitCode,1);assert.deepEqual(stderr,['M7_SOURCE_ACCESS_UNAVAILABLE\n']);assert.equal(stdout.length,0);if(mode==='bad-selector')assert.equal(calls.length,0);}console.log('PRIVATE_SOURCE_PORT_'+mode+'_PASS');})().catch(e=>{console.error(e);process.exitCode=1;});
"""


class PrivateClient(unittest.TestCase):
    def test_actual_private_client_selector_limits_sanitized_failure_and_restoration(self):
        helper = Path(s.__file__).with_name('source-access.cjs')
        for mode in ('positive', 'bad-selector', 'small-budget', 'refused', 'positive'):
            with self.subTest(mode=mode):
                result = subprocess.run(['node', '-e', PORT, str(helper), mode], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PRIVATE_SOURCE_PORT_' + mode + '_PASS', result.stdout)


if __name__ == '__main__': unittest.main()
