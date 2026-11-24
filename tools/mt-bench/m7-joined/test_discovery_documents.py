"""Row-unit write accounting: looping-v2 sends treatment arrays, so requests undercount stored rows.

Reproduced on the cluster (d-smoke-k8-on, 2026-11-21): 59 accepted treatment requests carried 63
documents; 63 rows were stored; the request-unit count oracle read WRONG_DATA and the coverage
verdict read ACCEPTED_NOT_STORED. Synthetic metrics here; no database.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kubernetes'))
from discovery_counts import accepted_documents
import coverage_verdict


def k6(**counts):
    return {key: {'count': value} for key, value in counts.items()}


SMOKE = {  # the d-smoke-k8-on summary, reduced to the counters that matter
    'writes_ok': 273, 'writes_uncertain': 0, 'writes_refused': 0,
    'writes_ok{kind:entries}': 97, 'writes_ok{kind:devicestatus}': 117, 'writes_ok{kind:treatments}': 59,
    'm7_looping_requests{request_shape:ds_loop}': 42, 'm7_looping_requests{request_shape:ds_loop_extra}': 15,
    'm7_looping_requests{request_shape:ds_trio_suggested}': 6, 'm7_looping_requests{request_shape:ds_trio_enacted}': 6,
    'm7_looping_requests{request_shape:ds_aaps}': 30, 'm7_looping_requests{request_shape:ds_cgm_battery}': 18,
    'm7_looping_requests{request_shape:tx_loop_v1}': 31, 'm7_looping_requests{request_shape:tx_trio_v1}': 4,
    'm7_looping_requests{request_shape:tx_aaps_v3}': 24, 'm7_looping_requests{request_shape:profile_loop_v1}': 0,
    'm7_looping_documents{request_shape:ds_loop}': 42, 'm7_looping_documents{request_shape:ds_loop_extra}': 15,
    'm7_looping_documents{request_shape:ds_trio_suggested}': 6, 'm7_looping_documents{request_shape:ds_trio_enacted}': 6,
    'm7_looping_documents{request_shape:ds_aaps}': 30, 'm7_looping_documents{request_shape:ds_cgm_battery}': 18,
    'm7_looping_documents{request_shape:tx_loop_v1}': 34, 'm7_looping_documents{request_shape:tx_trio_v1}': 5,
    'm7_looping_documents{request_shape:tx_aaps_v3}': 24, 'm7_looping_documents{request_shape:profile_loop_v1}': 0,
}


class Documents(unittest.TestCase):
    def test_document_counters_win(self):
        m = k6(writes_ok=10, writes_uncertain=1, writes_ok_documents=14, writes_uncertain_documents=3,
               **{'writes_ok_documents{kind:entries}': 4, 'writes_ok_documents{kind:devicestatus}': 4,
                  'writes_ok_documents{kind:treatments}': 6})
        self.assertEqual(accepted_documents(m)['accepted'], 14)
        self.assertEqual(accepted_documents(m)['uncertain'], 3)

    def test_fallback_from_attempted_documents_when_every_attempt_accepted(self):
        d = accepted_documents(k6(**SMOKE))
        self.assertEqual(d['byKind'], {'entries': 97, 'devicestatus': 117, 'treatments': 63})
        self.assertEqual(d['accepted'], 277)

    def test_fallback_refused_when_any_attempt_was_not_accepted(self):
        for change in ({'writes_uncertain': 1}, {'writes_refused': 2}, {'writes_ok{kind:treatments}': 58}):
            with self.subTest(change=change):
                self.assertIsNone(accepted_documents(k6(**{**SMOKE, **change})))

    def test_request_shape_without_documents_is_unknown(self):
        self.assertIsNone(accepted_documents(k6(writes_ok=5, writes_uncertain=0)))

    def _case(self, metrics, stored_treatments):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        load = Path(tmp.name)
        (load / 'k6-summary.json').write_text(json.dumps({'metrics': metrics}))
        (load / 'stored-counts.json').write_text(json.dumps({'t': {'entries': 97, 'devicestatus': 117,
                                                                    'treatments': stored_treatments}}))
        return coverage_verdict.from_case(load)

    def test_coverage_counts_rows_not_requests(self):
        # Green: stored rows equal accepted documents, so the accepted/stored check does not fire.
        self.assertNotIn('ACCEPTED_NOT_STORED', self._case(k6(**SMOKE), 63)['unmeasured'])
        # Red: one row missing still reads not stored.
        self.assertIn('ACCEPTED_NOT_STORED', self._case(k6(**SMOKE), 62)['unmeasured'])

    def test_red_control_request_units_misread_a_correct_run(self):
        # The pre-fix accounting (requests) on the same correct run: the check fires.
        metrics = {k: v for k, v in k6(**SMOKE).items() if not k.startswith('m7_looping_documents')}
        self.assertIn('ACCEPTED_NOT_STORED', self._case(metrics, 63)['unmeasured'])


if __name__ == '__main__':
    unittest.main()
