"""Discovery can retain a recovery episode without promoting its failed cell."""
import copy
import inspect
import inspect
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import discovery as d
import adapter as a
import evaluator_idle as idle
import evaluator_progress as p
from test_evaluator_idle import Idle
from test_evaluator_opportunities import Opportunities, BINDING
from test_evaluator_progress import A, B


class Recovery(unittest.TestCase):
    def capture(self):
        rounds=Idle().rounds(due=None)
        for index,row in enumerate(rounds):
            row['owners'][A]['generation']=1 if index==0 else 2
            row['owners'][A]['failedCompletions']=0 if index==0 else 1
        return {**idle.pack({'rounds':rounds}), 'kind':'evaluator-opportunity-phase-v1',
                'phase':'load','code':'M7_EVALUATOR_PROGRESS_RESET','verdict':'FAIL',
                'failedCollection':None,'durableBinding':copy.deepcopy(BINDING),
                'attribution':copy.deepcopy(BINDING),
                'durable':Opportunities().captures(),
                'captureWindows':[{'startNs':i*10,'durableEndNs':i*10+1,'inspectionEndNs':i*10+2} for i in range(3)]}

    def test_recovery_preserves_failure_and_unknown_interval(self):
        value=self.capture();result=d.recovery_episode(value,[A,B],BINDING)
        self.assertEqual(result['strictVerdict'],'FAIL')
        self.assertIn('UNMEASURED',result['interval'])
        self.assertEqual(value['verdict'],'FAIL')

    def test_process_restore_counter_and_source_changes_still_refuse(self):
        def process(v):v['rounds'][1]['instances']['evaluator']['runtimeId']='99999999-9999-4999-8999-999999999999'
        def rewind(v):v['rounds'][-1]['rows'][0][3]=-1
        def restore(v):v['durable'][-1]['rows'][0]['restoreGeneration']='2'
        def source(v):v['durableBinding']['imageId']='sha256:'+'0'*64
        def health(v):v['rounds'][-1]['rows'][0][9]=False
        for break_it in (process,rewind,restore,source,health):
            value=self.capture();break_it(value)
            with self.assertRaises(Exception):d.recovery_episode(value,[A,B],BINDING)
        self.test_recovery_preserves_failure_and_unknown_interval()

    def test_actual_classifier_process_guard_red_restored(self):
        value=self.capture();value['rounds'][1]['instances']['evaluator']['runtimeId']='99999999-9999-4999-8999-999999999999'
        def criterion(fn):
            with self.assertRaisesRegex(RuntimeError,'PROCESS_REPLACED'):fn(value,[A,B],BINDING)
        criterion(d.recovery_episode)
        source=inspect.getsource(d.recovery_episode)
        guard="require(current['instances']==rounds[0]['instances'],'M7_DISCOVERY_PROCESS_REPLACED')"
        self.assertEqual(source.count(guard),1)
        namespace=dict(d.__dict__)
        exec(compile(source.replace(guard,'pass # removed identity fence'),d.__file__,'exec'),namespace)
        with self.assertRaises(AssertionError):criterion(namespace['recovery_episode'])
        criterion(d.recovery_episode)

    def test_record_continues_but_keeps_strict_fail_and_no_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'load').mkdir()
            a.write(root/'tenants.private.json',[{'id':A},{'id':B}])
            a.write(root/'load/evaluator-progress.json',self.capture())
            # Record construction needs profile identity; reuse its existing
            # fixture instead of inventing a passing campaign document.
            from test_discovery import Discovery
            fixture=Discovery();fixture.setUp();folder,m=fixture.setup()
            m['evaluatorOpportunities']='received-input-v1'
            m['pair']=BINDING['pair'];m['imageId']=BINDING['imageId'];m['instrument']={'sha256':BINDING['instrument']}
            try:
                record=d.Record(a,root,m)
                with patch.object(a,'assert_owned') as owned:
                    record.observe('load',lambda:(_ for _ in ()).throw(p.Refused('M7_EVALUATOR_PROGRESS_RESET','FAIL')))
                    owned.assert_called_once_with(m)
                self.assertFalse(record.value['hardFailures'])
                self.assertEqual(record.value['strictChecks']['load']['verdict'],'FAIL')
                self.assertFalse(record.value['strictChecks']['load']['hardFailure'])
                self.assertEqual(record.value['capacityAcceptance'],'NOT_GRANTED')
            finally:fixture.doCleanups()


if __name__=='__main__':unittest.main()
