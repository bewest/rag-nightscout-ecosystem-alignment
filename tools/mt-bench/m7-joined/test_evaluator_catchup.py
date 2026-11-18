import copy
import unittest
from unittest import mock
import evaluator_catchup as c
import evaluator_progress as p
from test_evaluator_opportunities import BINDING
import test_evaluator_opportunities as fixtures
from test_evaluator_progress import A, B


class Catchup(unittest.TestCase):
    def setUp(self):
        self.boundary = fixtures.Opportunities().captures()[-1]
        self.boundary['rows'][0]['observed']['clock'] = '10'
        self.boundary['rows'][0]['completed']['clock'] = '10'
        self.now = 3_000_000_000

    def assess(self, snapshot):
        return c.assess(self.boundary, self.boundary, snapshot, [A, B], BINDING)

    def clock(self): return self.now
    def sleep(self, seconds): self.now += int(seconds * 1e9)

    def observe(self, snapshots, **kwargs):
        iterator = iter(snapshots)
        def fetch(timeout):
            self.assertGreater(timeout, 0)
            self.now += 100_000_000
            return next(iterator), {'sqlQueries': 1, 'rawSqlBytes': 128, 'nodeCalls': 1}
        return c.observe(self.boundary, [A, B], BINDING, fetch,
                         writer_stopped_ns=1_000_000_000, boundary_window={'startNs': 2_000_000_000, 'endNs': 2_100_000_000},
                         monotonic_ns=self.clock, sleep=self.sleep, **kwargs)

    def completed(self):
        value = copy.deepcopy(self.boundary)
        value['rows'][0]['observed']['clock'] = '12'
        value['rows'][0]['completed']['clock'] = '12'
        return value

    def test_intake_then_completion_of_same_frozen_target_without_output_change(self):
        value = self.assess(self.boundary)
        self.assertEqual(value['byTenant'][A]['awaitingObserved'], ['clock'])
        observed = self.completed(); observed['rows'][0]['completed']['clock'] = '10'
        self.assertEqual(self.assess(observed)['byTenant'][A]['awaitingCompleted'], ['clock'])
        result = self.observe([observed, self.completed()])
        self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['byTenant'][A]['targets'], {'clock': '12'})
        self.assertEqual(result['completionBounds'][A], {'lowerNs': 3_000_000_000, 'upperNs': 8_200_000_000})
        self.assertEqual(result['drainAfterWriterJoinMs'][A], {'lower': 2000.0, 'upper': 7200.0})
        self.assertEqual(result['byTenant'][A]['outputRevision'], self.boundary['rows'][0]['outputRevision'])

    def test_initial_zero_target_without_completion_is_pending(self):
        for row in self.boundary['rows']:
            row.update(writerClock='0',observed={},completed={},outputRevision='0')
        result=self.assess(self.boundary)
        self.assertEqual(result['verdict'],'UNMEASURED')
        self.assertEqual(result['byTenant'][A]['pending'],{'clock':'0'})
        self.assertEqual(result['byTenant'][A]['awaitingObserved'],['clock'])
        self.boundary['rows'][0]['observed']={'bootstrap':'0'}
        result=self.assess(self.boundary)
        self.assertEqual(result['byTenant'][A]['pending'],{'bootstrap':'0','clock':'0'})

    def test_new_writer_or_metadata_never_moves_goalpost(self):
        for field in ('writerClock', 'metadata'):
            value = self.completed()
            if field == 'writerClock': value['rows'][0]['writerClock'] = '13'
            else: value['rows'][0]['observed']['settings'] = '2'
            result = self.observe([value])
            self.assertEqual(result['verdict'], 'FAIL')
            self.assertEqual(result['byTenant'][A]['status'], 'INPUT_CHANGED')
            self.assertEqual(result['byTenant'][A]['targets'], {'clock': '12'})

    def test_deadline_retains_pending_without_inventing_deadlock(self):
        result = self.observe([self.boundary] * 3, seconds=2, interval=1)
        self.assertEqual(result['verdict'], 'UNMEASURED')
        self.assertEqual(result['code'], 'M7_DRAIN_DEADLINE')
        self.assertEqual(len(result['captures']), 2)
        self.assertNotIn(A, result['completionBounds'])

    def test_restore_reset_coverage_and_binding_refuse_with_original_capture(self):
        cases = []
        for key, value in [('restoreGeneration', '1'), ('outputRevision', '1')]:
            item = self.completed(); item['rows'][0][key] = value; cases.append(item)
        item = self.completed(); item['rows'].pop(); cases.append(item)
        item = self.completed(); item['reader'] = {}; cases.append(item)
        for item in cases:
            result = self.observe([item])
            self.assertNotEqual(result['verdict'], 'PASS')
            self.assertEqual(result['captures'][0]['snapshot'], item)
            self.assertTrue(result['code'].startswith('M7_'))

    def test_query_budget_and_late_collection_cannot_earn_green(self):
        with mock.patch.dict(c.POLICY, maxQueries=0):
            result = self.observe([])
            self.assertEqual(result['code'], 'M7_DRAIN_QUERY_BOUND')
        def late(timeout):
            self.now += 2_000_000_000
            return self.completed(), {'sqlQueries': 1, 'rawSqlBytes': 128, 'nodeCalls': 1}
        result = c.observe(self.boundary, [A, B], BINDING, late, seconds=1, interval=1,
                           boundary_window={'startNs': 2_000_000_000, 'endNs': 2_100_000_000}, writer_stopped_ns=1_000_000_000,
                           monotonic_ns=self.clock, sleep=self.sleep)
        self.assertEqual(result['verdict'], 'UNMEASURED')
        self.assertEqual(result['code'], 'M7_DRAIN_DEADLINE')
        self.assertNotIn(A, result['completionBounds'])

    def test_boundary_cost_consumes_same_budget_and_reserve_precedes_fetch(self):
        cost = {'sqlQueries': 1, 'rawSqlBytes': 128, 'nodeCalls': 1}
        value = self.observe([self.completed()], initial_cost=cost)
        self.assertEqual(value['queries'], 2)
        self.assertEqual(value['responseBytes'], 256)
        self.assertEqual(value['rounds'], 2)
        with mock.patch.dict(c.POLICY, maxRounds=1):
            value = self.observe([], initial_cost=cost)
            self.assertEqual(value['rounds'], 1)
            self.assertEqual(value['captures'], [])
            self.assertEqual(value['code'], 'M7_DRAIN_QUERY_BOUND')
        self.now = 3_000_000_000
        with mock.patch.dict(c.POLICY, maxQueries=1):
            value = self.observe([], initial_cost=cost)
            self.assertEqual(value['queries'], 1)
            self.assertEqual(value['captures'], [])
            self.assertEqual(value['code'], 'M7_DRAIN_QUERY_BOUND')
        with mock.patch.dict(c.POLICY, maxBytes=128):
            value = self.observe([], initial_cost=cost)
            self.assertEqual(value['responseBytes'], 128)
            self.assertEqual(value['captures'], [])
            self.assertEqual(value['code'], 'M7_DRAIN_BYTE_BOUND')

    def test_configured_observation_can_pass_after_old_time_bound(self):
        value=self.observe([self.boundary,self.completed()],seconds=600,interval=130)
        self.assertEqual(value['verdict'],'PASS')
        self.assertEqual(value['observationSeconds'],600)
        self.assertGreater(value['endNs']-value['startNs'],120e9)
        for bad in (0,-1,float('inf'),float('nan'),True):
            with self.subTest(bad=bad),self.assertRaisesRegex(p.Refused,'M7_DRAIN_BOUND'):
                self.observe([],seconds=bad)

    def test_explicit_round_query_and_byte_budgets_allow_a_longer_capture(self):
        rows=[self.boundary]*18+[self.completed()]
        original=self.observe(rows,seconds=600,interval=1)
        self.assertEqual(original['verdict'],'UNMEASURED')
        self.assertEqual(original['code'],'M7_DRAIN_QUERY_BOUND')
        self.now=3_000_000_000
        policy={'maxRounds':40,'maxQueries':40,'maxBytes':1000000000,'roundSeconds':30}
        value=self.observe(rows,seconds=600,interval=1,policy=policy)
        self.assertEqual(value['verdict'],'PASS')
        self.assertEqual(value['rounds'],19)
        self.assertEqual(value['policy']['maxRounds'],40)
        self.now=3_000_000_000
        refused=self.observe(rows,seconds=600,interval=1,policy={**policy,'maxQueries':1})
        self.assertEqual(refused['verdict'],'UNMEASURED')
        self.assertEqual(refused['queries'],1)
        self.assertEqual(refused['code'],'M7_DRAIN_QUERY_BOUND')

    def test_changed_or_unknown_join_bracket_refuses(self):
        with self.assertRaisesRegex(p.Refused, 'WRITER_BOUNDARY'):
            c.observe(self.boundary, [A, B], BINDING, None,
                      boundary_window={'startNs': 0, 'endNs': 1}, writer_stopped_ns=2,
                      monotonic_ns=self.clock)

    def test_dropped_pending_and_moving_goalpost_controls_fail_then_restore(self):
        def criterion():
            self.assertEqual(self.assess(self.boundary)['byTenant'][A]['status'], 'PENDING')
        criterion()
        original = c.decode
        def drop_pending(*args):
            rows = copy.deepcopy(original(*args))
            rows[-1][A]['completed']['clock'] = rows[0][A]['writerClock']
            return rows
        with mock.patch.object(c, 'decode', side_effect=drop_pending):
            with self.assertRaises(AssertionError): criterion()
        criterion()
        changed = self.completed(); changed['rows'][0]['writerClock'] = '13'
        self.assertEqual(self.assess(changed)['verdict'], 'FAIL')


class NativeCatchup(unittest.TestCase):
    def setUp(self):self.boundary=fixtures.native_captures()[-1]
    def assess(self,current=None,**kwargs):
        return c.assess(self.boundary,self.boundary,current or self.boundary,[A,B],fixtures.NATIVE_BINDING,**kwargs)

    def test_native_floor_fixed_target_completion_can_keep_same_output_and_history_independent(self):
        self.boundary['rows'][0]['completed']['bootstrap']='3';self.boundary['rows'][0]['native']['completedInputFloor']='3'
        self.assertEqual(self.assess()['byTenant'][A]['status'],'PENDING')
        completed=copy.deepcopy(self.boundary);completed['rows'][0]['completed']['bootstrap']='4';completed['rows'][0]['native']['completedInputFloor']='4'
        completed['rows'][0]['writerClock']='0';completed['rows'][0]['native']['snapshotPosition']='0/0'
        result=self.assess(completed)
        self.assertEqual(result['verdict'],'PASS')
        self.assertEqual(result['byTenant'][A]['targets'],{'bootstrap':'4','settings':'1'})
        self.assertEqual(result['writerIntakeCoverage']['verdict'],'UNMEASURED')
        self.assertEqual(result['byTenant'][A]['outputRevision'],'2')

    def test_real_additional_floor_position_metadata_or_raw_work_invalidates_quiet_target(self):
        for change in ('floor','acceptedPosition','settings','raw'):
            current=copy.deepcopy(self.boundary);row=current['rows'][0]
            if change=='floor':row['native']['inputFloor']='5';row['observed']['bootstrap']='5'
            elif change=='acceptedPosition':row['native']['acceptedPosition']='0/99'
            elif change=='settings':row['observed']['settings']='2'
            else:row['native']['raw']['head']='5'
            result=self.assess(current)
            self.assertEqual(result['verdict'],'FAIL',change)
            self.assertEqual(result['byTenant'][A]['status'],'INPUT_CHANGED',change)
            self.assertEqual(result['byTenant'][A]['targets']['bootstrap'],'4')
        self.assertEqual(self.assess()['verdict'],'PASS')

    def test_pending_marker_and_owed_metadata_cannot_be_excluded_from_drained_result(self):
        for change in ('pendingAt','bootstrap','settings'):
            boundary=copy.deepcopy(self.boundary)
            if change=='pendingAt':self.boundary['rows'][0]['pendingAt']=1
            else:self.boundary['rows'][0]['completed'][change]='0'
            self.assertEqual(self.assess()['byTenant'][A]['status'],'PENDING',change)
            self.boundary=boundary
        self.assertEqual(self.assess()['verdict'],'PASS')

    def test_boundary_due_requires_actual_later_completion_and_observer_clock(self):
        self.boundary['rows'][0]['dueAt']=100001
        clocks=fixtures.Opportunities().rounds()
        args={'boundary_clock':clocks[0],'current_clock':clocks[-1]}
        self.assertEqual(self.assess()['classifications']['UNMEASURED'],1)
        self.assertEqual(self.assess(boundary_clock=clocks[0])['classifications']['UNMEASURED'],1)
        self.assertEqual(self.assess(**args)['byTenant'][A]['status'],'PENDING')
        completed=copy.deepcopy(self.boundary);completed['rows'][0].update(completedAt=200000,dueAt=999999)
        self.assertEqual(self.assess(completed,**args)['verdict'],'PASS')
        for bad in (90000,99999):
            completed['rows'][0]['completedAt']=bad
            self.assertEqual(self.assess(completed,**args)['byTenant'][A]['status'],'PENDING')
        clocks[-1]['readWindows']['evaluator']['end']['wallUs']+=1000000
        with self.assertRaisesRegex(p.Refused,'CLOCK'):self.assess(**args)

    def test_source_restore_generation_missing_binding_and_regressions_stay_refused(self):
        for mutate in (lambda r:r['native']['source'].update(timeline=2),lambda r:r['native'].update(generation='b'*32+':1'),
                       lambda r:r.update(restoreGeneration='2'),lambda r:r['native'].update(acceptedPosition='0/1'),
                       lambda r:r.pop('native')):
            current=copy.deepcopy(self.boundary);mutate(current['rows'][0])
            with self.assertRaises(p.Refused):self.assess(current)
        self.assertEqual(self.assess()['verdict'],'PASS')

    def test_native_pending_collector_retains_budgets_and_real_completion_brackets(self):
        self.boundary['rows'][0]['completed']['bootstrap']='3';self.boundary['rows'][0]['native']['completedInputFloor']='3'
        current=copy.deepcopy(self.boundary);current['rows'][0]['completed']['bootstrap']='4';current['rows'][0]['native']['completedInputFloor']='4'
        now=[3_000_000_000];cost={'sqlQueries':1,'rawSqlBytes':128,'nodeCalls':1}
        def fetch(timeout):now[0]+=100_000_000;return current,cost
        result=c.observe(self.boundary,[A,B],fixtures.NATIVE_BINDING,fetch,writer_stopped_ns=1_000_000_000,
                         boundary_window={'startNs':2_000_000_000,'endNs':2_100_000_000},initial_cost=cost,
                         monotonic_ns=lambda:now[0],sleep=lambda seconds:None)
        self.assertEqual(result['verdict'],'PASS');self.assertEqual(result['queries'],2);self.assertEqual(result['responseBytes'],256)
        self.assertEqual(result['completionBounds'][A],{'lowerNs':2_000_000_000,'upperNs':3_100_000_000})
        with mock.patch.dict(c.POLICY,maxQueries=1):
            result=c.observe(self.boundary,[A,B],fixtures.NATIVE_BINDING,fetch,writer_stopped_ns=1_000_000_000,
                             boundary_window={'startNs':2_000_000_000,'endNs':2_100_000_000},initial_cost=cost,monotonic_ns=lambda:now[0])
        self.assertEqual(result['code'],'M7_DRAIN_QUERY_BOUND');self.assertEqual(result['captures'],[])

    def test_missing_due_clock_stops_unmeasured_without_spending_or_invoking_fetch(self):
        self.boundary['rows'][0]['dueAt']=100001
        fetch=mock.Mock(side_effect=AssertionError('missing clock must not trigger more reads'))
        result=c.observe(self.boundary,[A,B],fixtures.NATIVE_BINDING,fetch,writer_stopped_ns=1_000_000_000,
                         boundary_window={'startNs':2_000_000_000,'endNs':2_100_000_000},
                         initial_cost={'sqlQueries':1,'rawSqlBytes':128,'nodeCalls':1},monotonic_ns=lambda:3_000_000_000)
        self.assertEqual(result['verdict'],'UNMEASURED');self.assertEqual(result['code'],'M7_DRAIN_DUE_CLOCK_REQUIRED')
        self.assertEqual(result['queries'],1);self.assertEqual(result['captures'],[]);fetch.assert_not_called()

    def test_omitting_actual_native_floor_or_changed_input_guards_turns_semantic_controls_red(self):
        self.boundary['rows'][0]['completed']['bootstrap']='3';self.boundary['rows'][0]['native']['completedInputFloor']='3'
        def pending():self.assertEqual(self.assess()['byTenant'][A]['status'],'PENDING')
        pending()
        with mock.patch.object(c.o,'pending_targets',return_value={}):
            with self.assertRaises(AssertionError):pending()
        pending()
        changed=copy.deepcopy(self.boundary);changed['rows'][0]['native']['acceptedPosition']='0/99'
        def quiet_guard(assess):self.assertEqual(assess(self.boundary,self.boundary,changed,[A,B],fixtures.NATIVE_BINDING)['verdict'],'FAIL')
        quiet_guard(c.assess)
        source=__import__('pathlib').Path(c.__file__).read_text()
        needle="y['acceptedPosition']!=x['acceptedPosition']"
        self.assertEqual(source.count(needle),1)
        mutant={'__name__':'owned_native_quiet_mutant'};exec(source.replace(needle,'False'),mutant)
        with self.assertRaises(AssertionError):quiet_guard(mutant['assess'])
        quiet_guard(c.assess)


if __name__ == '__main__': unittest.main()
