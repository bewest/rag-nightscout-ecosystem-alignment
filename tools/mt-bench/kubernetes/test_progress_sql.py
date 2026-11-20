"""Writer-driven load bookends from the durable -completed rows (progress_sql), not the inspection RPC."""
import copy
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_adapter import iso, A, B
from test_evaluator_slices import sliced
from test_progress_capture import Clock
import kube_adapter as k
import execute
import progress_sql

COMPLETION = {'kind': 'evaluator-work-v2', 'checkpoint': 'nsdemo_eval_checkpoint', 'clock': 'nsdemo_clock',
              'entries': 'nsdemo_entries', 'consumer': 'evaluator-compose-demo-completed',
              'writerDriven': {'lifecycle': 'nsdemo_control', 'devicestatus': 'nsdemo_devicestatus',
                               'treatments': 'nsdemo_treatments'}}
IDENTITY = ['7710399298984480817', 1, 'nightscout_compose_test']
SEED = 1795217323937   # the seed's completed write-clock version for both tenants


def doc(rows, identity=IDENTITY):
    """rows: tenant -> (generation, completed, observed, restoreGeneration, stateOK, pending) as the query emits."""
    return json.dumps({'identity': identity, 'tenants': {
        t: [None if v is None else str(v) for v in r[:4]] + list(r[4:]) for t, r in rows.items()}})


class Bookend(unittest.TestCase):
    """A tenant the lazily loading evaluator has not loaded must read the seed's completed version."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name); self.out = self.d/'load'; self.out.mkdir()
        self.c, inv, rendered, self.client = sliced(1)
        self.clock = Clock()
        self.c.update(tenants=2, tier='discovery', completion=copy.deepcopy(COMPLETION))
        self.c['deadlines'] = {'workUntil': iso(self.clock.now+7200), 'cleanupUntil': iso(self.clock.now+7800)}
        self.objects = k.validate(self.c, inv, rendered)
        self.baseline = k.observe(self.c, self.objects, self.client)
        self.roster = [{'id': t, 'token': 'synthetic', 'host': 'synthetic.test'} for t in (A, B)]
        self.sql = []

        def call(args, data=b'', **kwargs):
            text = data.decode()
            if 'psql' in args:
                self.sql.append(text)
                k.need(text.startswith('BEGIN READ ONLY;') and text.rstrip().endswith('ROLLBACK;'), 'NOT_READ_ONLY')
                # A loaded (A), B never loaded since the restore: its row still holds the seed version.
                return doc({A: (1, SEED, SEED, 1, True, False), B: (1, SEED, SEED, 1, True, False)}).encode()
            # The inspection RPC, as core evaluator-inspection.js: an unloaded tenant fails the selector.
            selected = json.loads(text.split(';', 1)[0].removeprefix('const M7_PROGRESS_IDS='))
            if B in selected:
                raise k.Refused('K8S_EXEC_FAILED')
            raise AssertionError('unexpected exec ' + ' '.join(args))
        self.client.call = Mock(side_effect=call)

    def bookend(self, name):
        # Before the fix the controller took this bookend with retained_progress (the RPC).
        take = getattr(execute, 'capture_bookend', execute.retained_progress)
        with patch.object(k.time, 'time', self.clock.time), patch.object(k, 'active_baseline', return_value=self.baseline), \
             patch.object(execute, 'roster', return_value=self.roster), \
             patch('clinical_sql.observe', return_value=('postgres-0', 'postgres'), create=True):
            return take(self.d, self.out, self.c, self.objects, self.client, name)

    def test_unloaded_tenant_bookend_reads_the_seed_completed_version(self):
        value = self.bookend('progress-before')
        failure = self.out/'progress-before-failure.json'
        self.assertIsNotNone(value, failure.read_text() if failure.exists() else 'no bookend')
        retained = k.document(self.out/'progress-before.json')
        self.assertEqual(retained['source'], 'sql-completed-v1')
        self.assertEqual(retained['tenants'][B]['completed'], SEED)   # not zero, not refused
        self.assertEqual(len(self.sql), 1)
        self.assertTrue((self.out/'progress-before.private.jsonl').is_file())

    def test_seed_completions_are_not_new_work(self):
        before = progress_sql.decode(doc({A: (1, SEED, SEED, 1, True, False), B: (1, SEED, SEED, 1, True, False)}), [A, B])
        after = progress_sql.decode(doc({A: (1, SEED+900, SEED+900, 1, True, False), B: (1, SEED, SEED, 1, True, False)}), [A, B])
        for v in (before, after):
            v.update(queries=1, bytes=10, wallSeconds=0.1)
        result = progress_sql.assess(before, after, [A, B])
        self.assertEqual((result['verdict'], result['tenantsAdvanced'], result['tenantsWithSeedCompletion']), ('PASS', 1, 2))
        self.assertEqual(result['tenantsCaughtUpAfter'], 2)


class Assessment(unittest.TestCase):
    def pair(self, before_rows, after_rows, after_identity=IDENTITY):
        before = progress_sql.decode(doc(before_rows), [A, B]); after = progress_sql.decode(doc(after_rows, after_identity), [A, B])
        for v in (before, after):
            v.update(queries=1, bytes=10, wallSeconds=0.1)
        return before, after

    def test_regress_reset_fence_and_database_change_fail(self):
        ok = (1, SEED, SEED, 1, True, False)
        cases = {
            'RESET': ({A: ok, B: ok}, {A: (1, SEED-1, SEED, 1, True, False), B: ok}),
            'RESET ': ({A: ok, B: ok}, {A: (2, SEED, SEED, 1, True, False), B: ok}),
            'FENCE': ({A: ok, B: ok}, {A: (1, SEED+5, SEED+5, 0, True, False), B: ok}),
            'STATE': ({A: ok, B: ok}, {A: (1, SEED, SEED, 1, False, False), B: ok}),
        }
        for code, (b, a) in cases.items():
            with self.subTest(code), self.assertRaisesRegex(k.Refused, code.strip()):
                progress_sql.assess(*self.pair(b, a), [A, B])
        with self.assertRaisesRegex(k.Refused, 'DATABASE_CHANGED'):
            progress_sql.assess(*self.pair({A: ok, B: ok}, {A: ok, B: ok}, ['other', 1, 'x']), [A, B])

    def test_untouched_seed_row_with_an_older_restore_generation_passes(self):
        # Restore moved the generation to 2; B was never loaded, so its seed row keeps restore generation 1.
        b, a = self.pair({A: (2, SEED, SEED, 1, True, False), B: (2, SEED, SEED, 1, True, False)},
                         {A: (2, SEED+7, SEED+7, 2, True, False), B: (2, SEED, SEED, 1, True, False)})
        self.assertEqual(progress_sql.assess(b, a, [A, B])['tenantsAdvanced'], 1)

    def test_missing_roster_tenant_is_a_coverage_failure(self):
        with self.assertRaisesRegex(k.Refused, 'COVERAGE'):
            progress_sql.decode(doc({A: (1, SEED, SEED, 1, True, False)}), [A, B])

    def test_execute_assessment_uses_sql_bookends_for_writer_driven(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            b, a = self.pair({A: (1, SEED, SEED, 1, True, False), B: (1, SEED, SEED, 1, True, False)},
                             {A: (1, SEED+3, SEED+3, 1, True, False), B: (1, SEED, SEED, 1, True, False)})
            k.write(out/'progress-before.json', b); k.write(out/'progress-after.json', a)
            result = execute.assess_progress(out, {'completion': COMPLETION}, [A, B])
            self.assertEqual((result['source'], result['tenantsAdvanced']), ('sql-completed-v1', 1))
            (out/'progress-after.json').unlink()
            with self.assertRaisesRegex(k.Refused, 'BOOKENDS'):
                execute.assess_progress(out, {'completion': COMPLETION}, [A, B])


class Query(unittest.TestCase):
    def test_digest_and_bindings_match_the_writer_observer(self):
        import accepted_inputs
        _, observer = accepted_inputs.writer_queries(COMPLETION, 'run-1')
        sql = progress_sql.query(COMPLETION)
        digest = re.search(r"contract_digest = '([a-f0-9]{64})'", observer)[1]
        self.assertIn("contract_digest = '%s'" % digest, sql)
        self.assertIn('"nsdemo_control".tenant_lifecycle_windows', sql)
        self.assertIn("o.consumer = 'evaluator-compose-demo-completed'", sql)
        self.assertNotRegex(sql.upper(), r'\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP)\b')
        for bad in ({**COMPLETION, 'checkpoint': 'x"; drop'}, {**COMPLETION, 'writerDriven': None}):
            with self.assertRaisesRegex(k.Refused, 'BINDING'):
                progress_sql.query(bad)

    def test_pgstream_completion_keeps_the_rpc_bookend(self):
        self.assertFalse(progress_sql.writer_driven({'completion': {'kind': 'evaluator-work-v2'}}))
        self.assertTrue(progress_sql.writer_driven({'completion': COMPLETION}))


if __name__ == '__main__':
    unittest.main()
