import tempfile
import unittest
from pathlib import Path

import pg_waits


OWNER = 'a' * 32
HEAD = pg_waits.BLOCKER_HEADER + '\n'
ACTIVITY = ('t\trole\tstate\twait_event_type\twait_event\tn\n'
            '2\tnsdemo_api\tactive\tLock\ttransactionid\t1\n'
            '3\tnsdemo_api\tactive\tIO\tWALSync\t1\n')
SAMPLES = HEAD + (
    f'2\t{OWNER}\tsample\t1\t0\n'
    f'2\t{OWNER}\twait\tnsdemo_api\tactive\ttransactionid\t123\ttransactionid\tnsdemo_evaluator\t1\n'
    f'3\t{OWNER}\tsample\t0\t0\n')


class LockSamplingTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.path = Path(scratch.name)
        (self.path / 'host-load.tsv').write_text('t\tload1\n2\t0\n3\t0\n')
        (self.path / 'pg-activity.tsv').write_text(ACTIVITY)
        self.samples = self.path / 'pg-blockers.tsv'
        self.samples.write_text(SAMPLES)

    def reduce(self):
        return pg_waits.reduce_phase(self.path, OWNER, 1, 4,
                                     {'api': ('restRequests', ('nsdemo_api',))}, {'restRequests': 10})

    def test_measured_and_restored_after_meaningful_breaks(self):
        def check():
            value = self.reduce()
            blocker = value['blockerAttribution']
            self.assertEqual(value['activityStatus'], 'OBSERVED')
            self.assertEqual(value['causalAttribution'], 'UNMEASURED')
            self.assertEqual(value['waitDurationMs'], 'UNMEASURED')
            self.assertEqual(value['perUnit']['api']['sampledLockBackendObservationsPerUnit'], .1)
            self.assertEqual(blocker['status'], 'OBSERVED')
            self.assertEqual(blocker['roles'][0]['blockerRoles'], ['nsdemo_evaluator'])

        check()
        cases = (
            (HEAD + SAMPLES.splitlines(keepends=True)[-1], 'M7_PG_SAMPLE_TICK_OMITTED'),
            (''.join(line for line in SAMPLES.splitlines(keepends=True) if '\twait\t' not in line),
             'M7_PG_SAMPLE_WAIT_OMITTED'),
            (SAMPLES.replace(OWNER, 'b' * 32), 'M7_PG_SAMPLE_FOREIGN_OWNER'),
            (SAMPLES.replace('2\t', '2.5\t'), 'M7_PG_SAMPLE_FOREIGN_TICK'),
        )
        for broken, reason in cases:
            with self.subTest(reason=reason):
                self.samples.write_text(broken)
                self.assertEqual(self.reduce()['blockerAttribution'], {'status': 'UNMEASURED', 'reason': reason})
                with self.assertRaises(AssertionError):
                    check()
                self.samples.write_text(SAMPLES)
                check()

    def test_missing_activity_tick_and_unresolved_blocker_are_partial(self):
        self.samples.write_text(SAMPLES.replace('nsdemo_evaluator', 'unresolved'))
        value = self.reduce()
        self.assertEqual(value['blockerAttribution']['status'], 'PARTIAL')
        self.assertEqual(value['blockerAttribution']['unresolvedWaiterObservations'], 1)

        (self.path / 'pg-activity.tsv').write_text(ACTIVITY.replace('2\tnsdemo_api\tactive\tLock\ttransactionid\t1\n', ''))
        value = self.reduce()
        self.assertEqual(value['activityStatus'], 'PARTIAL')
        self.assertEqual(value['perUnit']['api']['sampledLockBackendObservationsPerUnit'], 'UNMEASURED')
        self.assertEqual(value['blockerAttribution']['status'], 'UNMEASURED')

    def test_fully_observed_zero_differs_from_legacy_without_blockers(self):
        (self.path / 'pg-activity.tsv').write_text(ACTIVITY.replace('Lock\ttransactionid', 'IO\tWALSync'))
        self.samples.write_text(HEAD + f'2\t{OWNER}\tsample\t0\t0\n3\t{OWNER}\tsample\t0\t0\n')
        self.assertEqual(self.reduce()['blockerAttribution']['status'], 'OBSERVED')
        self.assertEqual(self.reduce()['blockerAttribution']['roles'], [])
        self.samples.unlink()
        value = self.reduce()
        self.assertEqual(value['perUnit']['api']['sampledLockBackendObservationsPerUnit'], 0)
        self.assertEqual(value['blockerAttribution']['status'], 'UNMEASURED')
