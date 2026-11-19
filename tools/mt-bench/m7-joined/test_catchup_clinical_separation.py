"""Fixed targets remain measurable alongside a separately retained clinical FAIL."""
import copy
import json
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest import mock

import adapter as a
import discovery_counts
import evaluator_catchup as c
import evaluator_idle as idle
import evaluator_opportunities as o
import evaluator_progress as p
import test_discovery_rest as clinical
import test_evaluator_opportunities as durable
import test_evaluator_progress as progress

A, B = progress.A, progress.B


class ClinicalSeparation(unittest.TestCase):
    def exercise(self, module=c, *, broken=None, writer_live=False, probe_pending=False):
        original = clinical.RestAlongsideClinicalStall().artifact()
        self.assertEqual(o.verify(original, 2, ['evaluator'], durable.BINDING)['clinicalVerdict'], 'FAIL')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); output = directory/'load'; output.mkdir()
            a.write(output/'evaluator-progress.json', original)
            saved = (output/'evaluator-progress.json').read_bytes()
            (output/'runid').write_text('synthetic-run')
            manifest = {'profile': 'pgstream-sample', 'runPurpose': 'discovery', 'tenants': 2,
                        'completionContract': 'evaluator-work-v2', 'evaluatorOpportunities': o.CONTRACT,
                        'evaluatorCatchup': 'fixed-target-v1', 'cadence': {'restart': False}}
            stopped = time.monotonic_ns()
            load = {'verdict': 'FAIL', 'clinicalVerdict': 'FAIL', 'code': 'M7_EVALUATOR_PROGRESS_ERROR'}
            record = types.SimpleNamespace(value={'processes': {key: {'returncode': 0, 'endMonoNs': stopped}
                for key in ('k6', 'probe')}, 'strictChecks': {'load': copy.deepcopy(load)},
                'clinicalVerdict': 'FAIL', 'capacityAcceptance': 'NOT_GRANTED'}, save=lambda: None)
            if writer_live: record.value['processes']['probe']['returncode'] = None
            complete = durable.Opportunities().captures()[-1]
            boundary = copy.deepcopy(complete)
            boundary['rows'][0]['completed']['clock'] = '10'
            snapshots = iter([boundary, complete]); reads = []
            def collect(timeout):
                reads.append(timeout)
                snapshot = copy.deepcopy(next(snapshots))
                if broken == 'restore' and len(reads) == 2: snapshot['rows'][0]['restoreGeneration'] = '1'
                if broken == 'binding': snapshot['reader']['imageId'] = 'sha256:'+'0'*64
                return snapshot, {'sqlQueries': 1, 'rawSqlBytes': 128, 'nodeCalls': 1}
            collector = mock.Mock(side_effect=collect, binding=copy.deepcopy(durable.BINDING),
                preparation_cost={'nodeCalls': 1}, source_sha256='a'*64, query_sha256='b'*64)
            def rpc(*args, **kwargs):
                frame = clinical.RestAlongsideClinicalStall().frame()
                frame['observedAt'] = int(time.time()*1000)
                for row in frame['view']['tenants']:
                    row.update(dueAt=None, dueReason=None, jobs=dict.fromkeys(p.JOB_FLAGS, False))
                if broken == 'code': frame['view']['tenants'][0]['code'] = 'EVALUATOR_RESTORE_CHANGED'
                if broken == 'alert': frame['view']['tenants'][0]['evaluation']['alert'] = 'SYNTHETIC_ALERT'
                if broken == 'runtime': frame['view']['runtimeId'] = progress.S
                if broken == 'counter': frame['view']['tenants'][0]['progress']['completedAcquisitions'] = 0
                if broken == 'coverage': frame['view']['tenants'].pop()
                return json.dumps(frame)
            accounting = {'admissionsClosed': True, 'byTenant': {A: {'pending': int(probe_pending)}, B: {'pending': 0}}}
            observe = c.observe
            def tail(*args, **kwargs):
                kwargs['interval'] = .001
                return observe(*args, **kwargs)
            with mock.patch.object(a, 'progress_services', return_value=['evaluator']), \
                 mock.patch.object(a, 'progress_attribution', return_value={}), \
                 mock.patch.object(a, 'opportunity_collector', return_value=collector), \
                 mock.patch.object(a, 'progress_fetch', side_effect=rpc), \
                 mock.patch.object(discovery_counts, 'probe_metadata', return_value=(accounting, None)), \
                 mock.patch.object(module, 'observe', side_effect=tail):
                with a.command_deadline(time.time()+5): value = module.run(a, directory, manifest, record)
            self.assertEqual((output/'evaluator-progress.json').read_bytes(), saved)
            self.assertEqual(record.value['strictChecks']['load'], load)
            self.assertEqual(record.value['clinicalVerdict'], 'FAIL')
            self.assertEqual(record.value['capacityAcceptance'], 'NOT_GRANTED')
            self.assertEqual(value['originalLoadVerdict'], load)
            return value, reads

    def criterion(self, module=c):
        value, reads = self.exercise(module)
        self.assertEqual(value['verdict'], 'PASS', value.get('code'))
        self.assertEqual(len(reads), 2, 'both the boundary and later fixed-target snapshot are required')
        self.assertEqual(value['byTenant'][A]['targets'], {'clock': '12'})
        self.assertEqual(value['boundaryCost']['inspection']['rows'][0][idle.COLUMNS.index('ready')], False)
        return value

    def test_stalled_original_boundary_and_tail_keep_independent_clinical_fail(self):
        self.criterion()

    def test_each_clinical_decode_seam_is_required_red_then_restored(self):
        self.criterion()
        source = Path(c.__file__).read_text()
        seams = [line for line in source.splitlines() if 'allow_clinical_stall=True' in line]
        self.assertEqual(len(seams), 3)
        for seam in seams:
            broken = types.ModuleType('owned_strict_clinical_mutant')
            exec(compile(source.replace(seam, seam.replace('allow_clinical_stall=True', 'allow_clinical_stall=False')),
                         c.__file__, 'exec'), broken.__dict__)
            value, _ = self.exercise(broken)
            self.assertEqual(value['verdict'], 'FAIL')
            self.assertEqual(value['code'], 'M7_EVALUATOR_PROGRESS_ERROR')
        self.criterion()
        print('CATCHUP_CLINICAL_SEPARATION three strict-decoder controls RED; clinical FAIL retained; RESTORED_GREEN')

    def test_unrelated_errors_identity_counter_coverage_source_and_restore_still_refuse(self):
        for broken, code in [('code', 'ERROR'), ('alert', 'ERROR'), ('runtime', 'RESET'),
                             ('counter', 'RESET'), ('coverage', 'COVERAGE'),
                             ('binding', 'BINDING'), ('restore', 'RESET')]:
            with self.subTest(broken=broken):
                value, _ = self.exercise(broken=broken)
                self.assertEqual(value['verdict'], 'FAIL')
                self.assertIn(code, value['code'])
        self.criterion()

    def test_writer_join_and_probe_inventory_are_required_before_boundary(self):
        for options, code in [({'writer_live': True}, 'M7_DRAIN_WRITERS_NOT_JOINED'),
                              ({'probe_pending': True}, 'M7_DRAIN_PROBE_PENDING')]:
            value, reads = self.exercise(**options)
            self.assertEqual(value['code'], code)
            self.assertEqual(reads, [])


if __name__ == '__main__': unittest.main()
