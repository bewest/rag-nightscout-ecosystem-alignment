import copy
import unittest
from unittest import mock
import evaluator_opportunities as o
import evaluator_progress as p
import test_evaluator_idle as idle_fixtures
from test_evaluator_progress import A,B

BINDING={'kind':'evaluator-work-v2','pair':{'core':'1'*40,'deploy':'2'*40},'imageId':'sha256:'+'3'*64,'instrument':'4'*64}


class Opportunities(unittest.TestCase):
    def rounds(self):return idle_fixtures.Idle().rounds(due=None)

    def captures(self):
        def row(tenant,clock):return {'tenant':tenant,'writerClock':str(clock),'observed':{'clock':str(clock)},'completed':{'clock':str(clock)},'outputRevision':str(clock),'restoreGeneration':None}
        return [{'kind':'evaluator-durable-progress-v1','reader':copy.deepcopy(BINDING),'rows':[row(A,10+i),row(B,10)]} for i in range(3)]

    def assess(self,rounds=None,captures=None):
        return o.assess(rounds or self.rounds(),[A,B],'load',durable=captures if captures is not None else self.captures(),binding=BINDING)

    def completed_criterion(self):
        result=self.assess()
        self.assertEqual(result['verdict'],'PASS')
        self.assertEqual(result['eligibleTenants'],1)
        self.assertEqual(result['classifications'],{'KNOWN_COMPLETED':1,'KNOWN_PENDING':0,'NO_KNOWN_OPPORTUNITY':1,'UNMEASURED':0})
        return result

    def test_input_proof_qualifies_one_tenant_and_healthy_untouched_tenant_is_not_required_to_work(self):
        value=self.completed_criterion()
        self.assertEqual(value['tenantsWithObservedWork'],0,'durable and inspection intervals are not one-to-one credit')
        self.assertEqual(value['inputSourceTenantCoverage']['clock'],1)
        self.assertTrue(value['byTenant'][B]['noOrdinaryClockAdvanceProven'])
        self.assertEqual(value['workRate'].split(';')[0],'UNMEASURED')
        with self.assertRaisesRegex(p.Refused,'NOT_OBSERVED'):p.assess(self.rounds(),[A,B],'load')

    def test_initial_partial_and_zero_targets_remain_pending_without_fabricated_floors(self):
        for observed in ({},{'clock':'0'},{'bootstrap':'0'}):
            captures=self.captures()
            for capture in captures:
                capture['rows'][0].update(writerClock='0',observed=dict(observed),completed={},outputRevision='0')
            result=self.assess(captures=captures)
            self.assertEqual(result['verdict'],'UNMEASURED')
            self.assertEqual(result['byTenant'][A]['receivedInput'],'PENDING')
            self.assertEqual(result['byTenant'][A]['inputTargets']['clock'],'0')
            self.assertEqual(captures[-1]['rows'][0]['completed'],{})
        captures=self.captures()
        for capture in captures:capture['rows'][0]['completed']={'settings':'0'};capture['rows'][0]['observed']['settings']='0'
        self.assertEqual(self.assess(captures=captures)['byTenant'][A]['receivedInput'],'PENDING')

    def test_first_completion_can_install_generation_but_subsequent_changes_still_fail(self):
        captures=self.captures()
        captures[0]['rows'][0].update(completed={},outputRevision='0')
        for capture in captures[1:]:capture['rows'][0]['restoreGeneration']='7'
        self.assertEqual(self.assess(captures=captures)['verdict'],'PASS')
        captures[-1]['rows'][0]['restoreGeneration']='8'
        with self.assertRaisesRegex(p.Refused,'RESET'):self.assess(captures=captures)
        for changes in ({'completed':{'clock':'10'}},{'restoreGeneration':'7'}):
            captures=self.captures();captures[0]['rows'][0].update(completed={},outputRevision='0');captures[0]['rows'][0].update(changes)
            with self.assertRaisesRegex(p.Refused,'REVISION'):self.assess(captures=captures)

    def test_stale_completion_is_not_credit_even_when_unrelated_counter_work_increases(self):
        captures=self.captures()
        captures[-1]['rows'][0]['completed']['clock']='11'
        rounds=self.rounds()
        for i,r in enumerate(rounds):r['owners'][A].update(completedAcquisitions=1+i,legacyCycles=1+i)
        value=self.assess(rounds,captures)
        self.assertEqual(value['verdict'],'UNMEASURED')
        self.assertEqual(value['byTenant'][A]['classification'],'KNOWN_PENDING')
        self.assertEqual(value['byTenant'][A]['inputTargets']['clock'],'12')
        self.completed_criterion()

    def test_missed_intake_stays_pending_from_independent_writer_even_when_observed_vector_does_not_advance(self):
        captures=self.captures()
        for capture in captures:
            capture['rows'][0]['observed']['clock']='10'
            capture['rows'][0]['completed']['clock']='10'
        value=self.assess(captures=captures)
        self.assertEqual(value['byTenant'][A]['inputTargets'],{'clock':'12'})
        self.assertEqual(value['byTenant'][A]['receivedInput'],'PENDING')
        self.assertEqual(value['verdict'],'UNMEASURED')

    def test_missing_capture_or_actual_eligible_tenant_is_not_synthesized_from_counter(self):
        for captures in [self.captures()[:2],self.captures()]:
            if len(captures)==3:captures[1]['rows'].pop(0)
            with self.assertRaises(p.Refused) as caught:self.assess(captures=captures)
            self.assertEqual(caught.exception.verdict,'UNMEASURED')
        value=o.assess(self.rounds(),[A,B],'load')
        self.assertEqual(value['verdict'],'UNMEASURED');self.assertEqual(value['classifications']['UNMEASURED'],2)

    def test_all_roster_health_failures_and_resets_survive_opportunity_exclusion(self):
        for key,value,code in [('failedCompletions',1,'HIDDEN_FAILURE'),('ready',False,'PROGRESS_ERROR'),('code','REFUSED','PROGRESS_ERROR')]:
            rounds=self.rounds();rounds[1]['owners'][B][key]=value
            with self.assertRaisesRegex(p.Refused,code) as caught:self.assess(rounds)
            self.assertEqual(caught.exception.verdict,'FAIL')
        captures=self.captures();captures[-1]['rows'][0]['writerClock']='9'
        with self.assertRaisesRegex(p.Refused,'CLOCK'):self.assess(captures=captures)

    def test_due_completion_uses_durable_checkpoint_and_keeps_later_due(self):
        rounds=self.rounds();rounds[0]['owners'][B].update(dueAt=100001,dueReason='sgv-recent-10')
        captures=self.captures()
        for capture in captures:
            for row in capture['rows']:row.update(dueAt=None,completedAt=90000)
        captures[0]['rows'][1]['dueAt']=100001
        self.assertEqual(self.assess(rounds,captures)['byTenant'][B]['timer'],'PENDING')
        # Cache recreation classifies the due run as acquisition. Neither output
        # revision/content nor the ordinary input clock must change for TIME work.
        rounds[-1]['owners'][B].update(generation=99,completedAcquisitions=2,legacyCycles=2)
        captures[-1]['rows'][1].update(completedAt=200000,dueAt=999999)
        value=self.assess(rounds,captures)
        self.assertEqual(value['byTenant'][B]['timer'],'COMPLETED')
        self.assertEqual(value['verdict'],'PASS')
        captures[-1]['rows'][1]['dueAt']=100001
        self.assertEqual(self.assess(rounds,captures)['byTenant'][B]['timer'],'PENDING')
        captures[-1]['rows'][1]['dueAt']=None
        self.assertEqual(self.assess(rounds,captures)['byTenant'][B]['timer'],'COMPLETED')
        captures[-1]['rows'][1]['completedAt']=99999
        self.assertEqual(self.assess(rounds,captures)['byTenant'][B]['timer'],'PENDING')
        self.assertEqual(self.assess(rounds)['byTenant'][B]['timer'],'UNMEASURED')
        del rounds[0]['readWindows']
        self.assertEqual(self.assess(rounds,captures)['byTenant'][B]['timer'],'UNMEASURED')

    def test_durable_completion_rewind_and_restore_change_still_refuse(self):
        for value in (None,89999):
            captures=self.captures()
            for capture in captures:
                for row in capture['rows']:row.update(dueAt=None,completedAt=90000)
            captures[-1]['rows'][0]['completedAt']=value
            with self.assertRaisesRegex(p.Refused,'RESET'):self.assess(captures=captures)

    def test_observed_metadata_revision_is_independent_of_ordinary_kind_coverage(self):
        captures=self.captures()
        for i,capture in enumerate(captures):
            row=capture['rows'][1];row['observed']['settings']=str(4+i);row['completed']['settings']=str(4+i)
        value=self.assess(captures=captures)
        self.assertEqual(value['inputSourceTenantCoverage']['settings'],1)
        self.assertTrue(value['ordinaryWriteKindCoverage'].startswith('UNMEASURED'))
        self.assertEqual(value['eligibleTenants'],2)

    def test_break_actual_revision_validator_makes_stale_completion_criterion_red_then_restore(self):
        def criterion():
            captures=self.captures();captures[-1]['rows'][0]['completed']['clock']='11'
            self.assertEqual(self.assess(captures=captures)['byTenant'][A]['classification'],'KNOWN_PENDING')
        criterion()
        real=o.durable_rows
        def omit_pending(*args):
            captures=real(*args);captures[-1][A]['completed']['clock']=captures[-1][A]['writerClock'];return captures
        with mock.patch.object(o,'durable_rows',side_effect=omit_pending):
            with self.assertRaises(AssertionError):criterion()
        criterion();self.completed_criterion()

    def test_revision_precision_binding_coverage_and_restore_generation_refuse(self):
        for mutate,code in [
            (lambda c:c[0]['rows'][0].update(writerClock=10),'REVISION'),
            (lambda c:c[0]['rows'][0].update(writerClock='9223372036854775808'),'REVISION'),
            (lambda c:c[1]['reader']['pair'].update(core='5'*40),'BINDING'),
            (lambda c:c[-1]['rows'][0].update(restoreGeneration='1'),'RESET')]:
            captures=self.captures();mutate(captures)
            with self.assertRaisesRegex(p.Refused,code):self.assess(captures=captures)


if __name__=='__main__':unittest.main()
