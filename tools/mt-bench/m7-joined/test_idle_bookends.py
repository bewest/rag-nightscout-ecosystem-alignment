"""Recording-only faults in the existing enabled-idle bookends."""
import contextlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import adapter as a
import evaluator_progress as p

class Bookends(unittest.TestCase):
    def exercise(self,phase_error=None,after_error=None,publication_error=False):
        root=tempfile.TemporaryDirectory();self.addCleanup(root.cleanup);d=Path(root.name);out=d/'idle';out.mkdir()
        a.write(d/'owner.json',{'synthetic':True});calls=[];query_count=0
        raw={'kind':'synthetic-idle-observation','verdict':'UNMEASURED' if phase_error else 'PASS','code':str(phase_error) if phase_error else None}
        @contextlib.contextmanager
        def sampling(*args):
            (out/'sampler.log').write_text('synthetic bounded sample\n')
            try:yield
            finally:a.write(out/'sampler.json',{'completed':True})
        @contextlib.contextmanager
        def observe(*args):
            try:yield types.SimpleNamespace(result={'verdict':'PASS'},complete_after_cost_window=lambda:None)
            finally:
                a.write(out/'evaluator-progress.json',raw)
                if phase_error:raise phase_error
        def sql(*args):
            nonlocal query_count
            query_count+=1
            if query_count==3 and after_error:raise after_error
            return 'synthetic-role\t1\t1\n'
        original_write=a.write
        def write(file,value):
            if publication_error and file.name=='after-snapshot-failure.json':raise OSError('PRIVATE_SYNTHETIC_NOT_PUBLISHED')
            return original_write(file,value)
        def command(cmd,*args,**kwargs):calls.append(cmd[:2]);return 'synthetic bounded cgroup/process observation\n'
        row={'Config':{'Labels':{'com.docker.compose.service':'evaluator'}},'Id':'owned-recording','Name':'owned-recording'}
        with patch.object(a,'resources',return_value=[row]),patch.object(a,'command',side_effect=command),patch.object(a,'psql',side_effect=sql),patch.object(a,'sampling',sampling),patch.object(a,'observe_progress',observe),patch.object(a.time,'sleep') as sleep,patch.object(a,'write',side_effect=write):
            caught=None
            try:result=a.enabled_idle(d,{},out,120)
            except BaseException as error:caught=error;result=None
        self.assertEqual(sleep.call_args.args,(120,),'originalphase duration only')
        return out,caught,result,query_count,calls,raw
    def test_pass_has_only_original_two_bookends_and_four_sql_queries(self):
        out,error,result,queries,calls,_=self.exercise()
        self.assertIsNone(error);self.assertEqual(result.result['verdict'],'PASS');self.assertEqual(queries,4);self.assertEqual(len(calls),4)
        self.assertTrue((out/'before-cgroups.json').is_file());self.assertTrue((out/'after-pg-statements.tsv').is_file());self.assertFalse((out/'after-snapshot-failure.json').exists())
    def test_observer_refusal_still_captures_existing_after_bookend(self):
        failure=p.Refused('M7_EVALUATOR_IDLE_TIME_NOT_OBSERVED')
        out,error,_,queries,_,raw=self.exercise(phase_error=failure)
        self.assertIs(error,failure);self.assertEqual(queries,4)
        self.assertEqual(a.document(out/'evaluator-progress.json'),raw)
        self.assertTrue((out/'sampler.json').is_file());self.assertTrue((out/'after-pg-statements.tsv').is_file())
    def test_after_failure_keeps_primary_and_reports_actual_partial_files(self):
        failure=p.Refused('M7_EVALUATOR_IDLE_TIME_NOT_OBSERVED');secondary=RuntimeError('PRIVATE_SYNTHETIC_SQL_OR_URL')
        out,error,_,queries,_,raw=self.exercise(phase_error=failure,after_error=secondary)
        self.assertIs(error,failure);self.assertEqual(queries,3)
        self.assertEqual(a.document(out/'evaluator-progress.json'),raw)
        for name in ['before-cgroups.json','before-pg-role.tsv','before-pg-statements.tsv','sampler.json']:self.assertTrue((out/name).is_file())
        diagnostic=a.document(out/'after-snapshot-failure.json');self.assertTrue(diagnostic['originalPhaseFailurePreserved']);self.assertEqual(diagnostic['partialFiles'],{'after-cgroups.json':True,'after-pg-role.tsv':False,'after-pg-statements.tsv':False})
        self.assertNotIn('PRIVATE_SYNTHETIC',json.dumps(diagnostic));self.assertLess(len(json.dumps(diagnostic)),512)
    def test_after_failure_without_primary_is_not_a_pass(self):
        secondary=RuntimeError('PRIVATE_SYNTHETIC_SQL_OR_URL');out,error,result,_,_,_=self.exercise(after_error=secondary)
        self.assertIs(error,secondary);self.assertIsNone(result);self.assertFalse(a.document(out/'after-snapshot-failure.json')['originalPhaseFailurePreserved'])
    def test_diagnostic_publication_failure_never_replaces_primary(self):
        failure=p.Refused('M7_EVALUATOR_IDLE_TIME_NOT_OBSERVED');out,error,_,_,_,_=self.exercise(phase_error=failure,after_error=RuntimeError('secondary'),publication_error=True)
        self.assertIs(error,failure);self.assertTrue(error.afterSnapshotFailure['publicationFailed']);self.assertFalse((out/'after-snapshot-failure.json').exists())

if __name__=='__main__':unittest.main()
