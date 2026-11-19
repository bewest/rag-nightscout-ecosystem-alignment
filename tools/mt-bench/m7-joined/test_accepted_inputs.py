"""Acceptance, intake and completion are three distinct observations."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import accepted_inputs as inputs
import outcome_gate as gate
from test_outcome_gate import A, row, page

RUN = 'synthetic-c1'
ENTRY = ('entries', RUN, '42')
SECOND = ('treatments', RUN, '42')
ACK = (A, *ENTRY)


def snapshot(*keys, floor=2, completed=2, events=None):
    events = list(keys) if events is None else events
    return dict(tenant=A, inputs=list(keys), events=events, latest=events[-1] if events else None,
                sourceOK=True, stateOK=True, outputOK=completed is not None, outputAbsent=False,
                inputFloor=floor, completed=completed, generation=1, revision=int(completed is not None),
                outputTenant=A if completed is not None else None, identity=None,
                tailHead=len(events), tailBase=0, snapshotPosition='0/0')


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
                self.assertEqual(c.assess({ACK:250}, 301)['codes'], ['M7_INPUT_DEADLINE'])
                restored = self.cover()
                restored.capture([pending], 1, 1.25)
                restored.capture([snapshot(ENTRY)], 3, 4)
                self.assertEqual(restored.assess({ACK:250}, 301)['verdict'], 'PASS')

    def test_no_completed_row_and_no_native_input(self):
        c = self.cover()
        pending = snapshot(ENTRY, completed=None, events=[])
        pending.update(sourceOK=None, stateOK=None, inputFloor=None, outputAbsent=True)
        c.capture([pending], 1, 2)
        c.capture([pending], 25, 26)
        self.assertEqual(c.assess({ACK:200}, 25)['codes'], ['M7_INPUT_MISSING_AT_DRAIN'])

    def test_second_input_same_tenant_draining_with_nine_hundred_idle(self):
        idle = [f'00000000-0000-4000-8000-{i:012d}' for i in range(900)]
        c = self.cover([A, *idle])
        c.capture([snapshot(ENTRY)], 0, 1)
        pending = snapshot(ENTRY, SECOND, floor=3, completed=2)
        c.capture([pending], 8, 9)
        acks = {ACK:15, (A, *SECOND):20}
        self.assertEqual(c.assess(acks, 10)['classifications'], {'ON_TIME':1, 'UNMEASURED':1})
        incomplete = copy.deepcopy(c)
        incomplete.capture([pending], 10, 11)
        self.assertEqual(incomplete.assess(acks, 10)['codes'], ['M7_INPUT_MISSING_AT_DRAIN'])
        c.capture([snapshot(ENTRY, SECOND, floor=3, completed=3)], 9, 10)
        result = c.assess(acks, 10)
        self.assertEqual(result['classifications'], {'ON_TIME':2})
        # Same input evidence through both outcome entry points.
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            load = folder/'load'
            load.mkdir()
            raw = load/'evaluator-progress-raw'
            raw.mkdir()
            pages = page([row(A), *(row(t, ready=False, code='EVALUATOR_ACQUISITION_REQUIRED') for t in idle)])
            for dest in (load/'progress-before.private.jsonl', load/'progress-after.private.jsonl',
                         raw/'load-00-evaluator.private.jsonl', raw/'drain-00-evaluator.private.jsonl'):
                dest.write_bytes(pages)
            storage = {'verdict':'GREEN', 'uncertain':0, 'rows':[{'tenant':A,'accepted':2,'probeAccepted':0},
                       *({'tenant':t,'accepted':0,'probeAccepted':0} for t in idle)]}
            (load/'oracle-findings.json').write_text(json.dumps(storage))
            probe = {'verdict':'PASS','clinicalTiming':{'contract':'clinical-deadline-from-acceptance-v1','witnesses':1},
                     'witnesses':[{'clinicalTiming':{'verdict':'PASS'}}]}
            (load/'probe.json').write_text(json.dumps({'completedOutput':probe}))
            for packet, expected in ((result,'PASS'), (incomplete.assess(acks,10),'FAIL'), (result,'PASS')):
                (load/'evaluator-catchup.json').write_text(json.dumps(packet))
                for actual in (gate.judge_compose_run(folder,[A,*idle]), gate.judge_kubernetes_load(load,[A,*idle])):
                    self.assertEqual(actual['verdict'], expected, actual['components'])

    def test_foreign_output_and_missing_storage_are_independent(self):
        c = self.cover()
        bad = snapshot(ENTRY)
        bad['outputTenant'] = 'other'
        with self.assertRaisesRegex(inputs.EvidenceError, 'FOREIGN_OUTPUT'):
            c.capture([bad], 1, 2)
        c.capture([snapshot(ENTRY)], 1, 2)
        self.assertEqual(c.assess({ACK:100}, 10)['verdict'], 'PASS')
        self.assertEqual(gate.storage({'verdict':'RED'})['verdict'], 'FAIL')

    def test_observation_loss_and_straddling_deadline_are_unmeasured(self):
        c = self.cover()
        c.capture([snapshot(ENTRY)], 119, 121)
        self.assertEqual(c.assess({ACK:200}, 200)['verdict'], 'UNMEASURED')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            count = {'verdict':'GREEN','uncertain':0,'rows':[{'tenant':A,'accepted':1,'stored':1,'match':True,
                     'probePending':0,'probeUncertain':0,'probeAccepted':0,'probeStored':0}]}
            with self.assertRaisesRegex(inputs.EvidenceError, 'ACK_COVERAGE'):
                inputs.reconcile({}, RUN, {A}, count)
            msg = json.dumps({'event':'m7-input-accepted','tenant':A,'domain':'entries','key':'42','run':RUN,
                              'requestToAcceptanceMs':18})
            log = p/'k6.log'
            for envelope in (json.dumps({'msg':msg}), 'time="t" level=info msg='+json.dumps(msg)+' source=console'):
                log.write_text(envelope+'\n')
                acks = {}
                inputs.read_acks(p, RUN, {A}, acks)
                inputs.reconcile(acks, RUN, {A}, count)
                self.assertEqual(acks, {ACK:18})


if __name__ == '__main__':
    unittest.main()
