"""Actual deferred idle observer cannot settle before original metric AFTER."""
import contextlib
import copy
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import adapter as a
import evaluator_idle as idle
import evaluator_progress as p
import test_idle_tail as fixtures
from test_evaluator_progress import A,B

class TailBookends(unittest.TestCase):
    def exercise(self,after_failure=False,tail_failure=False,original_failure=False):
        with tempfile.TemporaryDirectory()as scratch:
            d=Path(scratch);out=d/'idle';out.mkdir();events=[];publications=[];f=fixtures.Tail();rounds=f.rounds();point=f.point()
            if original_failure:rounds[1]['owners'][A]['jobs']['running']=True
            class Recorded(idle.Observer):
                def __enter__(self):
                    self.rounds=rounds[:2];self.thread=types.SimpleNamespace(join=lambda **kw:None,is_alive=lambda:False);return self
                def observe(self):self.rounds.append(rounds[-1])
            observer=Recorded(['evaluator'],[A,B],None,120,'idle',publications.append,tail_fetch=lambda *args:None)
            @contextlib.contextmanager
            def sampling(*args):yield
            def bookend(d,out,name):
                events.append(name)
                if name=='after'and after_failure:raise RuntimeError('AFTER_REFUSED')
            def tail(*args):
                events.append('tail');self.assertEqual(events[-2],'after')
                if tail_failure:raise p.Refused('TAIL_POINT_REFUSED')
                __import__('time').sleep(.005);point['round']['wallSeconds']=0
                for v in point['round']['readWindows'].values():v['end']={k:n+1000 for k,n in v['start'].items()};v['observedAt']=[int(v['start']['wallUs']/1000)]
                return point['round']
            with patch.object(a,'phase_snapshot',side_effect=bookend),patch.object(a,'sampling',sampling),patch.object(a,'observe_progress',return_value=observer),patch.object(a.time,'sleep') as sleep,patch.object(idle,'round_view',side_effect=tail):
                # Patch of sharedtime.sleep also touches the tail's tiny controlled wait;
                # keep a minimum mocked duration through its real clock field below.
                original=idle.time.monotonic;clock=[0.]
                def measured_tail(*args):
                    value=tail(*args);clock[0]+=.01;return value
                with patch.object(idle.time,'monotonic',side_effect=lambda:clock[0]),patch.object(idle,'round_view',side_effect=measured_tail):
                    error=None
                    try:a.enabled_idle(d,{},out,120)
                    except Exception as e:error=e
                self.assertEqual(sleep.call_args_list[0].args,(120,),'original phase duration remains fixed')
            return events,publications,error
    def test_tail_only_after_successful_after_and_never_added_to_main_counts(self):
        events,values,error=self.exercise();self.assertIsNone(error);self.assertEqual(events,['before','after','tail']);self.assertEqual(values[0]['verdict'],'UNMEASURED');self.assertEqual(values[-1]['verdict'],'PASS');self.assertEqual(values[-1]['completedTimeDelta'],0)
    def test_after_failure_suppresses_tail_and_cannot_publish_pass(self):
        events,values,error=self.exercise(after_failure=True);self.assertRegex(str(error),'AFTER_REFUSED');self.assertEqual(events,['before','after']);self.assertTrue(all(v['verdict']!='PASS'for v in values))
    def test_tail_failure_retains_partial_original_rounds(self):
        events,values,error=self.exercise(tail_failure=True);self.assertRegex(str(error),'TAIL_POINT_REFUSED');self.assertEqual(events,['before','after','tail']);self.assertEqual(len(values[-1]['rounds']),3);self.assertEqual(values[-1]['verdict'],'UNMEASURED')
    def test_original_busy_failure_has_after_but_no_point_exception(self):
        events,values,error=self.exercise(original_failure=True);self.assertRegex(str(error),'JOB_PENDING');self.assertEqual(events,['before','after']);self.assertTrue(all(v['verdict']!='PASS'for v in values))

if __name__=='__main__':unittest.main()
