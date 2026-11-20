"""Per-ACK writer-driven evidence and negative controls through both platform verdicts."""
from pathlib import Path
import json
import tempfile
import unittest

import accepted_inputs as inputs
import assessor
import commissioning_context
import outcome_gate as gate
import sql_attribution


TENANT = '11111111-1111-4111-8111-111111111111'
RUN = 's4-synthetic'
SOURCE = ['12345', 1, 'synthetic_test']
BASE = {'identity': SOURCE, 'tenants': {TENANT: ['3', '100']}}
FIRST = ('entries', RUN, 'first')
SECOND = ('treatments', RUN, 'second')
THIRD = ('devicestatus', RUN, 'third')
ACKS = {(TENANT, *key): 250 for key in (FIRST, SECOND, THIRD)}


def observer():
    value = inputs.WriterCoverage(RUN, [TENANT], 0)
    value.prime(BASE)
    return value


def row(keys, evaluated, completed, observed):
    return {'tenant': TENANT, 'inputs': [list(key) + [stamp] for key, stamp in keys],
            'identity': SOURCE, 'generation': 3, 'phase': 'active', 'clock': 103,
            'evaluated': evaluated, 'completed': completed, 'observed': observed, 'stateOK': True,
            'outputTenant': TENANT, 'outputOK': True, 'outputAbsent': False}


class Writer(unittest.TestCase):
    def test_one_completion_coalesces_two_writes_and_a_later_write_waits(self):
        value = observer()
        first = [(FIRST, 101), (SECOND, 102)]
        value.capture([row(first, 100, 900, 910)], 1, 2)
        value.capture([row(first + [(THIRD, 103)], 102, 910, 920)], 5, 6)
        with tempfile.TemporaryDirectory() as tmp:
            load = Path(tmp)/'load'
            load.mkdir()
            def check(want):
                events = value.events(ACKS, 300)
                (load/'evaluator-catchup.json').write_text(json.dumps({'kind': inputs.KIND, 'events': events}))
                for result in (gate.judge_compose_run(tmp, [TENANT]), gate.judge_kubernetes_load(load, [TENANT])):
                    self.assertEqual(result['components']['clinical']['classifications'], want)
            check({'ON_TIME': 2, 'UNMEASURED': 1})
            value.capture([row(first + [(THIRD, 103)], 102, 910, 920)], 129, 130)
            check({'ON_TIME': 2, 'LATE': 1})
            recovered = observer()
            recovered.capture([row(first + [(THIRD, 103)], 103, 920, 920)], 1, 2)
            value = recovered
            check({'ON_TIME': 3})

    def test_no_coverage_from_mutable_pendings_or_later_lifecycle(self):
        for change in (dict(generation=4), dict(phase='suspended'), dict(identity=['other', 1, 'synthetic_test']),
                       dict(outputOK=False), dict(stateOK=False), dict(evaluated=103, completed=919, observed=920)):
            with self.subTest(change=change):
                value = observer()
                snap = row([(FIRST, 101)], 103, 920, 920)
                value.capture([dict(snap, **change)], 150, 151)
                item = value.inputs.get((TENANT, *FIRST), {})
                self.assertIsNone(item.get('durableBy'))
                self.assertIsNone(item.get('pendingAt'))

    def test_a_foreign_database_between_samples_cannot_shorten_the_latency_bound(self):
        value = observer()
        value.capture([{'identity': SOURCE, 'tenant': None}], 1, 2)
        value.capture([{'identity': ['other', 1, 'synthetic_test'], 'tenant': None}], 125, 126)
        self.assertFalse(any(e['event'] == 'readback' for e in value.events({(TENANT, *FIRST): 10}, 200)))
        value.capture([row([(FIRST, 101)], 103, 920, 920)], 129, 130)
        result = assessor.assess(value.events({(TENANT, *FIRST): 1}, 200), [TENANT])
        self.assertEqual(result['components']['clinical']['classifications'], {'UNMEASURED': 1})

    def test_pre_run_marker_invalid_stamp_and_ambiguous_key_are_unmeasured(self):
        for keys in ([(FIRST, 100)], [(FIRST, None)], [(FIRST, 101), (FIRST, 102)]):
            value = observer()
            value.capture([row(keys, 103, 920, 920)], 1, 2)
            result = assessor.assess(value.events({(TENANT, *FIRST): 1}, 3), [TENANT])
            self.assertEqual(result['components']['clinical']['classifications'], {'UNMEASURED': 1})

    def test_compose_writer_receives_sql_attribution_without_stream_identity(self):
        roles = commissioning_context.sql_logins({'inputTransport': 'writer-driven', 'sqlRoles': ['evaluator']},
                                                {'sqlRoles': ['realtime']})
        self.assertEqual(roles, {'adapter': ['evaluator', 'realtime']})
        self.assertEqual(sql_attribution.assess({}, {}, roles)['totals'], {'adapter': {'calls': 0, 'executionMs': 0}})


if __name__ == '__main__':
    unittest.main()
