"""Existing SQL calls only; honest request bounds instead of nominal QPS."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import adapter as a

class Timing(unittest.TestCase):
    def test_original_two_queries_and_failure_metadata_without_extra_reads(self):
        expected=["SELECT r.rolname,sum(s.calls),sum(s.total_exec_time) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid GROUP BY 1 ORDER BY 1;", "SELECT r.rolname,s.calls,s.total_exec_time,left(regexp_replace(s.query,'\\s+',' ','g'),500) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid ORDER BY total_exec_time DESC LIMIT 50;"]
        for failure in (False,True):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory()as scratch:
                d=Path(scratch);a.write(d/'owner.json',{});queries=[]
                def sql(_,text):
                    queries.append(text)
                    if failure and len(queries)==2:raise RuntimeError('PRIVATE_SQL_DETAILS')
                    return 'synthetic-role\t100\t10\n'
                with patch.object(a,'resources',return_value=[]),patch.object(a,'psql',side_effect=sql):
                    if failure:
                        with self.assertRaisesRegex(RuntimeError,'PRIVATE_SQL_DETAILS'):a.phase_snapshot(d,d,'before')
                    else:a.phase_snapshot(d,d,'before')
                self.assertEqual(queries,expected)
                meta=a.document(d/'before-sql-snapshot-timing.json');self.assertEqual(set(meta['reads']),{'pg-role','pg-statements'})
                for key,row in meta['reads'].items():
                    self.assertEqual(row['status'],'FAILED'if failure and key=='pg-statements'else'PASS')
                    self.assertLessEqual(row['monotonicStartedAtNs'],row['monotonicFinishedAtNs'])
                    self.assertTrue(all(type(row[k])is int for k in ('wallStartedAtNs','wallFinishedAtNs','monotonicStartedAtNs','monotonicFinishedAtNs')))
                self.assertNotIn('PRIVATE_SQL_DETAILS',json.dumps(meta))
    def windows(self):
        def frame(start,end):return {'version':1,'collectorOwner':'a'*32,'hostIdentity':'b'*64,'clockDomain':'collector-host-monotonic-v1','reads':{'pg-role':{'status':'PASS','monotonicStartedAtNs':start*10**9,'monotonicFinishedAtNs':end*10**9}}}
        return frame(1,3),frame(11,13)
    def test_rates_are_bracketed_not_120_second_guesses(self):
        before,after=self.windows();v=a.sql_counter_rate_bounds(before,after,100)
        self.assertEqual(v['elapsedLowerSeconds'],8);self.assertEqual(v['elapsedUpperSeconds'],12)
        self.assertEqual(v['minimumPerSecond'],100/12);self.assertEqual(v['maximumPerSecond'],100/8)
        self.assertNotEqual(v['minimumPerSecond'],100/120);self.assertNotIn('qps',v)
        with self.assertRaisesRegex(RuntimeError,'TIMING_REQUIRED'):a.sql_counter_rate_bounds({'nominalSeconds':120},{'nominalSeconds':120},100)
        with self.assertRaisesRegex(RuntimeError,'COUNTER_RESET'):a.sql_counter_rate_bounds(before,after,-1)
    def test_missing_failed_overlap_wrong_domain_and_bool_refuse(self):
        for change in [lambda a:a.clear(),lambda a:a.update(clockDomain='other'),lambda a:a.update(hostIdentity='c'*64),lambda a:a.update(collectorOwner='d'*32),lambda a:a['reads']['pg-role'].update(status='FAILED'),lambda a:a['reads']['pg-role'].update(monotonicStartedAtNs=2*10**9),lambda a:a['reads']['pg-role'].update(monotonicStartedAtNs=True)]:
            before,after=self.windows();change(after)
            with self.assertRaisesRegex(RuntimeError,'TIMING_REQUIRED'):a.sql_counter_rate_bounds(before,after,100)
    def test_nominal_rate_mutant_cannot_meet_actual_window_criterion(self):
        before,after=self.windows();correct=a.sql_counter_rate_bounds(before,after,100)
        bad={'elapsedLowerSeconds':120,'elapsedUpperSeconds':120,'minimumPerSecond':100/120,'maximumPerSecond':100/120}
        def invariant(value):self.assertEqual((value['elapsedLowerSeconds'],value['elapsedUpperSeconds']),(8,12))
        invariant(correct)
        with self.assertRaises(AssertionError):invariant(bad)
        invariant(a.sql_counter_rate_bounds(before,after,100))

if __name__=='__main__':unittest.main()
