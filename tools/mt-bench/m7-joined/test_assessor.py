"""The four product properties, red then green, on synthetic events and on retained packets.

Retained-packet controls replay copies of synthetic-data packets under
/mnt/data/nightscout-workspace/artifacts and skip when those are absent.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import assessor
import outcome_gate

A, B = 'synthetic-a', 'synthetic-b'
IDLE = [f'00000000-0000-4000-8000-{i:012d}' for i in range(900)]
ARTIFACTS = Path(os.environ.get('M7_RETAINED_ARTIFACTS', '/mnt/data/nightscout-workspace/artifacts'))
KUBE = ARTIFACTS/'reproducible-runs-20261119/kcap-repro-join-tiny-02/raw/kcap-repro-join-tiny-02/runtime/packet/load'
COMPOSE = ARTIFACTS/'reproducible-runs-20261119/seeded-tiny-02/session/observations/baseline/fixture/load'
WARM = ARTIFACTS/'generous-resources-campaign-20261118/warm-controls/point-05'


def ev(kind, tenant=A, key='1', writer='ordinary', **fields):
    base = {'event': kind, 'tenant': tenant, 'domain': 'entries', 'key': key, 'writer': writer}
    return {**base, **fields}


def run(tenant=A, key='1', ms=900):
    return [ev('accepted', tenant, key), ev('stored', tenant, key),
            ev('output', tenant, key, outputTenant=tenant, acceptedToOutputMaxMs=ms, atDrain='DURABLE'),
            {'event': 'frame', 'tenant': tenant, 'viewerTenant': tenant, 'key': key, 'acceptedToFrameMs': ms}]


READ = [{'event': 'readback', 'what': w, 'writer': 'ordinary'} for w in ('storage', 'output')] + [
    {'event': 'datastore', 'source': 'synthetic', 'healthy': True}]


def verdicts(result):
    return result['verdict'], {k: v['verdict'] for k, v in result['components'].items()}


class Properties(unittest.TestCase):
    def test_green(self):
        self.assertEqual(assessor.assess(run() + READ, [A])['verdict'], 'PASS')

    def test_late_input_fails_regardless_of_prior_activity(self):
        prior = run(key='0', ms=10)                       # earlier timely work for the same tenant
        late = run(key='1')[:2] + [ev('output', key='1', atDrain='DURABLE', acceptedToOutputMaxMs=125000, acceptedToOutputMinMs=120000)]
        result = assessor.assess(prior + late + READ, [A])
        self.assertEqual((result['verdict'], result['components']['clinical']['codes']), ('FAIL', ['CLINICAL_DEADLINE']))
        self.assertEqual(assessor.assess(prior + run(key='1', ms=119999) + READ, [A])['verdict'], 'PASS')
        proven = run(key='1')[:2] + [ev('output', key='1', atDrain='UNKNOWN', acceptedToOutputMinMs=120500)]
        self.assertEqual(assessor.assess(prior + proven + READ, [A])['verdict'], 'FAIL')
        unresolved = run(key='1')[:2] + [ev('output', key='1', atDrain='DURABLE', acceptedToOutputMaxMs=121000, acceptedToOutputMinMs=1000)]
        self.assertEqual(assessor.assess(prior + unresolved + READ, [A])['verdict'], 'UNMEASURED')

    def test_missing_output_at_drain_fails(self):
        events = run()[:2] + READ
        self.assertEqual(assessor.assess(events, [A])['components']['clinical']['codes'], ['CLINICAL_OUTPUT_MISSING_AT_DRAIN'])
        self.assertEqual(assessor.assess(run() + READ, [A])['verdict'], 'PASS')

    def test_nine_hundred_idle_tenants_do_not_change_the_verdict(self):
        for events in (run() + READ, run(ms=130000) + READ, run()[:2] + READ):
            small, large = assessor.assess(events, [A]), assessor.assess(events, [A, *IDLE])
            self.assertEqual(verdicts(small), verdicts(large))
            self.assertEqual(large['figures']['idleTenants'], 900)

    def test_missing_stored_row_fails(self):
        events = [e for e in run() if e['event'] != 'stored'] + READ
        result = assessor.assess(events, [A])
        self.assertEqual((result['verdict'], result['components']['storedWrites']['codes']), ('FAIL', ['ACCEPTED_WRITE_NOT_STORED']))
        self.assertEqual(assessor.assess(run() + READ, [A])['verdict'], 'PASS')
        unread = [e for e in run() + READ if e.get('what') != 'storage']
        self.assertEqual(assessor.assess(unread, [A])['components']['storedWrites']['verdict'], 'UNMEASURED')

    def test_cross_tenant_read_fails(self):
        base = run(A) + run(B, key='2') + READ
        for name, change in (('frame', lambda e: e['event'] == 'frame' and e['tenant'] == A and e.update(viewerTenant=B)),
                             ('output', lambda e: e['event'] == 'output' and e['tenant'] == A and e.update(outputTenant=B))):
            with self.subTest(name):
                events = copy.deepcopy(base)
                for e in events:
                    change(e)
                self.assertEqual(assessor.assess(events, [A, B])['components']['isolation']['verdict'], 'FAIL')
        access = base + [{'event': 'access', 'principal': A, 'target': B, 'allowed': True}]
        self.assertEqual(assessor.assess(access, [A, B])['components']['isolation']['codes'], ['CROSS_TENANT_ACCESS'])
        denied = base + [{'event': 'access', 'principal': A, 'target': B, 'allowed': False}]
        self.assertEqual(assessor.assess(denied, [A, B])['verdict'], 'PASS')

    def test_unhealthy_datastore_fails(self):
        events = run() + READ + [{'event': 'datastore', 'source': 'synthetic', 'healthy': False}]
        self.assertEqual(assessor.assess(events, [A])['components']['datastore']['verdict'], 'FAIL')

    def test_shape_mismatches_are_figures(self):
        events = run() + READ + [{'event': 'accepted'}, 'garbage', {'event': 'unknown-kind'}, None]
        result = assessor.assess(events, [A])
        self.assertEqual((result['verdict'], result['figures']['malformedEvents']), ('PASS', 4))


def replay(source, edit=lambda folder: None):
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)/'load'
        shutil.copytree(source, folder, ignore=shutil.ignore_patterns('*.log', '*.gz', 'catchup', 'oracle-input'))
        edit(folder)
        ids = [r['tenant'] for r in json.loads((source/'oracle-findings.json').read_text())['rows']]
        return assessor.judge(folder, ids)


def rewrite(path, change):
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


@unittest.skipUnless(KUBE.is_dir() and COMPOSE.is_dir(), 'retained synthetic packets not present')
class RetainedPackets(unittest.TestCase):
    """Old packets carry per-input timing for probe writes only; ordinary inputs stay UNMEASURED."""

    def baseline(self, source):
        result = replay(source)
        components = {k: v['verdict'] for k, v in result['components'].items()}
        self.assertEqual(components, {'storedWrites': 'PASS', 'clinical': 'UNMEASURED', 'isolation': 'PASS', 'datastore': 'PASS'})
        self.assertEqual(result['components']['clinical']['classifications'].get('LATE', 0), 0)
        return result

    def test_both_platforms_share_one_event_format(self):
        kinds = lambda folder: {e['event'] for e in assessor.collect(folder)[0]}
        self.assertTrue({'accepted', 'stored', 'output', 'datastore', 'readback'} <= kinds(KUBE) & kinds(COMPOSE))
        self.assertEqual(outcome_gate.judge_kubernetes_load(KUBE, [])['contract'], assessor.CONTRACT)

    def test_two_dropped_iterations_are_a_figure(self):
        base = self.baseline(KUBE)
        def drop(folder):
            rewrite(folder/'k6-summary.json', lambda v: v['metrics'].update(dropped_iterations={'count': 2}))
        dropped = replay(KUBE, drop)
        self.assertEqual(dropped['figures']['dropped_iterations'], 2)
        self.assertEqual(verdicts(dropped), verdicts(base))

    def test_missing_counter_files_are_figures(self):
        base = self.baseline(COMPOSE)
        gone = replay(COMPOSE, lambda folder: (folder/'k6-summary.json').unlink())
        self.assertIn('k6-summary.json', gone['figures']['missingFiles'])
        self.assertEqual(verdicts(gone), verdicts(base))

    def test_late_probe_input_fails_and_restores(self):
        for source in (KUBE, COMPOSE):
            with self.subTest(source.parts[-5]):
                self.baseline(source)
                def late(folder):
                    name = 'probe.json' if (folder/'probe.json').is_file() else 'clinical-witnesses-partial.json'
                    def change(doc):
                        witness = (doc.get('completedOutput') or doc)['witnesses'][-1]
                        witness['clinicalTiming']['acceptanceToCompletionLowerMs'] = 120001   # a read after the deadline found no output
                    rewrite(folder/name, change)
                result = replay(source, late)
                self.assertEqual(result['components']['clinical']['codes'][0], 'CLINICAL_DEADLINE')
                self.baseline(source)

    def test_missing_stored_row_fails_and_restores(self):
        self.baseline(KUBE)
        def lose(folder):
            rewrite(folder/'oracle-findings.json', lambda v: v['rows'][0].update(stored=v['rows'][0]['stored']-1))
        self.assertEqual(replay(KUBE, lose)['components']['storedWrites']['verdict'], 'FAIL')
        self.baseline(KUBE)

    def test_cross_tenant_frame_fails_and_restores(self):
        self.baseline(KUBE)
        def foreign(folder):
            def change(doc):
                witness = doc['completedOutput']['witnesses'][0]
                other = next(b['socket'] for b in doc['viewerBindings'] if b['tenant'] != witness['tenant'])
                witness['clientObservations'][0]['socket'] = other
            rewrite(folder/'probe.json', change)
        result = replay(KUBE, foreign)
        self.assertEqual(result['components']['isolation']['codes'], ['FOREIGN_FRAME'])
        self.baseline(KUBE)

    def test_cross_tenant_kubernetes_frame_fails_and_restores(self):
        base = self.baseline(KUBE)
        self.assertGreater(base['components']['isolation']['witnesses'], 33)
        def foreign(folder):
            def change(doc):
                stored = doc['completedOutput']['witnesses'][0]['storedId']
                owner = doc['completedOutput']['witnesses'][0]['tenant']
                row = next(r for r in doc['kubernetesFrames']['rows'] if r['tenant'] != owner)
                row['ids'].append(stored)
            rewrite(folder/'probe.json', change)
        self.assertEqual(replay(KUBE, foreign)['components']['isolation']['codes'], ['FOREIGN_FRAME'])
        self.baseline(KUBE)

    def test_nine_hundred_idle_tenants_on_a_retained_packet(self):
        base = self.baseline(KUBE)
        events, figures = assessor.collect(KUBE)
        ids = sorted({e['tenant'] for e in events if e.get('event') == 'accepted'})
        wide = assessor.assess(events, ids + IDLE, figures=figures)
        self.assertEqual(verdicts(wide), verdicts(base))
        self.assertEqual(wide['figures']['idleTenants'], 900)

    @unittest.skipUnless(WARM.is_dir(), 'warm-control packet not present')
    def test_warm_control_pre_warm_miss_now_fails(self):
        # point-05 accepted an input before the evaluator was warm; the retired
        # warm rule passed it. From acceptance it is 123 s: a FAIL.
        control = json.loads((WARM/'control-result.json').read_text())
        accepted = json.loads((WARM/'accepted.private.json').read_text())[0]
        witness = {'tenant': accepted['tenant'], 'date': accepted['date'], 'acceptedAt': accepted['acked'],
                   'clinicalTiming': control['preWarm']}
        events = assessor.probe_events({'witnesses': [witness]}, {}) + [
            {'event': 'readback', 'what': 'output', 'writer': 'probe'}]
        self.assertEqual(control['control'], 'PASS')
        self.assertEqual(assessor.assess(events, [accepted['tenant']])['components']['clinical']['codes'], ['CLINICAL_DEADLINE'])


if __name__ == '__main__':
    unittest.main()
