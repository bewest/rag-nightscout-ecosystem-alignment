"""Actual final reducer: idle counter deltas never bypass native outcome checks."""
import copy
from contextlib import ExitStack
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import execute
import kube_adapter as k
import test_evaluator_progress as fixtures
A, B, S = fixtures.A, fixtures.B, fixtures.S


class IdleProgressOutcome(unittest.TestCase):
    def rounds(self, idle=True):
        fixture = fixtures.Progress()
        def transform(frame):
            if idle:
                row = frame['view']['tenants'][1]
                row.update(cycles=1, dueAt=9000000000000, dueReason='sgv-recent-10')
                row['progress'].update(completedAcquisitions=1, completedTimeCycles=0)
            return frame
        return [fixture.round(i, transform) for i in range(3)]

    def assess(self, rounds, outcome='PASS', missing_midpoint=False, clinical='PASS'):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        d = Path(temporary.name); out = d/'load'; out.mkdir()
        c = {'pins':{}, 'workload':{'logicalPollingClients':0}}
        for name, point in zip(('before','midpoint','after'), rounds):
            if name=='midpoint' and missing_midpoint: continue
            k.write(out/f'progress-{name}.json',point)
        (out/'runid').write_text('synthetic-idle-load')
        k.write(out/'probe.json',{'window':{}, 'completedOutput':{'witnesses':[{}]}})
        k.write(out/'probe-accounting.json', {'version':2, 'kind':'m7-discovery-probe-accounting',
            'runId':'synthetic-idle-load', 'roster':[A,B], 'admissionsClosed':True, 'attempts':0, 'byTenant':{}})
        k.write(out/'fanout.json',{'probeWrites':{'byTenant':{}}})
        with ExitStack() as stack:
            for target,name,value in (
                (execute,'completion',None),
                (execute,'roster',[{'id':A},{'id':B}]),
                (k,'stored',{}),
                (execute,'accepted_writes',{'verdict':'GREEN','uncertain':0}),

                (execute,'load_checks',{'http':{'httpVerdict':'PASS'}}),
                (k.viewer_plan,'check',{'verdict':'PASS'}),
            ):stack.enter_context(patch.object(target,name,return_value=value))

            judge=stack.enter_context(patch('outcome_gate.judge_kubernetes_load',return_value={
                'verdict':outcome,'instrument':{'contract':'authored-outcome-control'},
                'components':{'catchup':{'verdict':outcome,'codes':[]}}}))
            if outcome != 'PASS':
                with self.assertRaisesRegex(k.Refused,'OUTCOME_GATE_' + outcome):
                    execute.assess_stage(d,out,c,{},None)
                result=k.document(out/'result.json')
            elif clinical == 'UNMEASURED':
                with self.assertRaisesRegex(k.Refused, 'CLINICAL_WITNESS_COVERAGE'):
                    execute.assess_stage(d,out,c,{},None)
                result = k.document(out/'result.json')
            else:result=execute.assess_stage(d,out,c,{},None)
            self.assertEqual(judge.call_count,1)
            return result

    def test_idle_tenant_requires_only_counter_stability(self):
        rounds=self.rounds(); saved=copy.deepcopy(rounds)
        value=self.assess(rounds)
        progress=value['evaluatorProgress']
        self.assertEqual(progress['verdict'],'PASS')
        self.assertEqual(progress['counterStability'],'PASS')
        self.assertEqual(progress['minimumCompletedWorkDelta'],0)
        self.assertEqual(progress['completedWorkDelta'],4)
        self.assertEqual(value['outcomeGate']['verdict'],'PASS')
        self.assertEqual(rounds,saved,'idle completion credit was invented')

    def test_missing_strict_midpoint_uses_actual_bookend_cost(self):
        rounds=self.rounds(); value=self.assess(rounds,missing_midpoint=True)['evaluatorProgress']
        self.assertEqual(value['observedRounds'],2)
        self.assertEqual(value['queries'],rounds[0]['queries']+rounds[-1]['queries'])
        self.assertEqual(value['responseBytes'],rounds[0]['bytes']+rounds[-1]['bytes'])

    def test_runtime_reset_still_refuses_before_outcome(self):
        rounds=self.rounds();rounds[1]['instances']['evaluator']['runtimeId']=S
        with self.assertRaisesRegex(k.evaluator_progress.Refused,'PROGRESS_RESET'):
            self.assess(rounds)

    def test_counter_reset_still_refuses_before_outcome(self):
        rounds=self.rounds();rounds[-1]['owners'][B]['completedAcquisitions']=0
        with self.assertRaisesRegex(k.evaluator_progress.Refused,'PROGRESS_RESET'):
            self.assess(rounds)

    def test_foreign_counter_still_refuses_before_outcome(self):
        rounds=self.rounds()
        for point in rounds:
            foreign=copy.deepcopy(point['allRows']['evaluator'])
            for row in foreign.values():row.update(admitted=False,ready=False)
            point['allRows']['foreign-evaluator']=foreign
        rounds[-1]['allRows']['foreign-evaluator'][B]['completedAcquisitions']+=1
        with self.assertRaisesRegex(k.evaluator_progress.Refused,'PROGRESS_FOREIGN'):
            self.assess(rounds)

    def test_observed_per_tenant_work_keeps_original_pass(self):
        self.assertEqual(self.assess(self.rounds(idle=False))['evaluatorProgress']['verdict'],'PASS')


if __name__=='__main__':unittest.main()
