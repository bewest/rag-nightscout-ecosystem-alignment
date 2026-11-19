"""The live collector emits acceptance, storage and output events; assessor.py judges them."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import accepted_inputs as inputs
import assessor
import outcome_gate as gate

A = '11111111-1111-4111-8111-111111111111'
RUN = 'synthetic-c1'
ENTRY = ('entries', RUN, '42')
SECOND = ('treatments', RUN, '42')
ACK = (A, *ENTRY)


def snapshot(*keys, floor=2, completed=2, events=None):
    events = list(keys) if events is None else events
    return dict(tenant=A, inputs=list(keys), events=events, latest=events[-1] if events else None,
                sourceOK=True, stateOK=True, outputOK=completed is not None, outputAbsent=completed is None,
                inputFloor=floor, completed=completed, generation=1, revision=int(completed is not None),
                outputTenant=A if completed is not None else None, identity=None,
                tailHead=len(events), tailBase=0, snapshotPosition='0/0')


def judged(coverage, acks, end, ids=(A,)):
    return assessor.assess(coverage.events(acks, end), ids)


class Acceptance(unittest.TestCase):
    def cover(self, roster=(A,)):
        c = inputs.Coverage(RUN, roster, 0)
        c.before_writes_lsn = 256
        return c

    def test_deadline_from_ack_with_and_without_prior_output(self):
        for previous in (None, 1):
            with self.subTest(previous=previous):
                c = self.cover()
                pending = snapshot(ENTRY, completed=previous)
                c.capture([pending], 1, 1.25)
                c.capture([pending], 121.5, 122)
                self.assertEqual(judged(c, {ACK: 250}, 301)['components']['clinical']['codes'], ['CLINICAL_DEADLINE'])
                restored = self.cover()
                restored.capture([pending], 1, 1.25)
                restored.capture([snapshot(ENTRY)], 3, 4)
                self.assertEqual(judged(restored, {ACK: 250}, 301)['verdict'], 'PASS')

    def test_no_completed_row_and_no_native_input(self):
        c = self.cover()
        pending = snapshot(ENTRY, completed=None, events=[])
        pending.update(sourceOK=None, stateOK=None, inputFloor=None, outputAbsent=True)
        c.capture([pending], 1, 2)
        c.capture([pending], 25, 26)
        self.assertEqual(judged(c, {ACK: 200}, 25)['components']['clinical']['codes'], ['CLINICAL_OUTPUT_MISSING_AT_DRAIN'])

    def test_second_input_same_tenant_draining_with_nine_hundred_idle(self):
        idle = [f'00000000-0000-4000-8000-{i:012d}' for i in range(900)]
        c = self.cover([A, *idle])
        c.capture([snapshot(ENTRY)], 0, 1)
        pending = snapshot(ENTRY, SECOND, floor=3, completed=2)
        c.capture([pending], 8, 9)
        acks = {ACK: 15, (A, *SECOND): 20}
        self.assertEqual(judged(c, acks, 10)['components']['clinical']['classifications'], {'ON_TIME': 1, 'UNMEASURED': 1})
        incomplete = copy.deepcopy(c)
        incomplete.capture([pending], 10, 11)
        self.assertEqual(judged(incomplete, acks, 10)['verdict'], 'FAIL')
        c.capture([snapshot(ENTRY, SECOND, floor=3, completed=3)], 9, 10)
        self.assertEqual(judged(c, acks, 10, [A, *idle])['components']['clinical']['classifications'], {'ON_TIME': 2})
        # The same events through both platform entry points, with 900 idle tenants.
        with tempfile.TemporaryDirectory() as tmp:
            load = Path(tmp)/'load'
            load.mkdir()
            for coverage, expected in ((c, 'PASS'), (incomplete, 'FAIL'), (c, 'PASS')):
                (load/'evaluator-catchup.json').write_text(json.dumps({'kind': inputs.KIND, 'events': coverage.events(acks, 10)}))
                for actual in (gate.judge_compose_run(tmp, [A, *idle]), gate.judge_kubernetes_load(load, [A, *idle])):
                    self.assertEqual(actual['verdict'], expected, actual['components'])
                    self.assertEqual(actual['figures']['idleTenants'], 900)

    def test_foreign_output_lost_row_and_foreign_storage_are_events_not_exceptions(self):
        c = self.cover()
        bad = snapshot(ENTRY)
        bad['outputTenant'] = 'other'
        c.capture([bad], 1, 2)
        self.assertEqual(judged(c, {ACK: 100}, 10)['components']['isolation']['codes'], ['FOREIGN_OUTPUT'])
        lost = self.cover()
        lost.capture([snapshot(ENTRY)], 1, 2)
        lost.capture([], 3, 4)                     # the stored row disappeared
        self.assertEqual(judged(lost, {ACK: 100}, 10)['components']['storedWrites']['codes'], ['ACCEPTED_WRITE_NOT_STORED'])
        foreign = self.cover()
        foreign.capture([snapshot(ENTRY), dict(snapshot(ENTRY), tenant='not-in-roster')], 1, 2)
        self.assertEqual(judged(foreign, {ACK: 100}, 10)['components']['isolation']['codes'], ['FOREIGN_STORED_ROW'])
        clean = self.cover()
        clean.capture([snapshot(ENTRY)], 1, 2)
        self.assertEqual(judged(clean, {ACK: 100}, 10)['verdict'], 'PASS')

    def test_observation_loss_and_straddling_deadline_are_unmeasured(self):
        c = self.cover()
        c.capture([snapshot(ENTRY)], 119, 121)
        self.assertEqual(judged(c, {ACK: 200}, 200)['verdict'], 'UNMEASURED')
        self.assertEqual(judged(self.cover(), {ACK: 200}, 200)['components']['storedWrites']['verdict'], 'UNMEASURED')

    def test_ack_envelopes_and_unreadable_lines(self):
        msg = json.dumps({'event': 'm7-input-accepted', 'tenant': A, 'domain': 'entries', 'key': '42', 'run': RUN,
                          'requestToAcceptanceMs': 18})
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp)/'k6.log'
            for envelope in (json.dumps({'msg': msg}), 'time="t" level=info msg='+json.dumps(msg)+' source=console'):
                log.write_text(envelope+'\nm7-input-accepted not json\n')
                acks = {}
                self.assertEqual(inputs.read_acks(Path(tmp), RUN, acks), 1)
                self.assertEqual(acks, {ACK: 18})


if __name__ == '__main__':
    unittest.main()
