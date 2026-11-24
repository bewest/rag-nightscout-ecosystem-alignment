import json
from pathlib import Path
import shutil
import tempfile
import unittest

import capacity_results as results
import coverage_verdict
from test_durable_m1 import A, B, C, bookend, run_rows, seeded


def write(path, value):
    path.write_text(json.dumps(value))


class CapacityPublication(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.load = Path(tmp.name) / 'raw' / 'load'
        self.root = Path(tmp.name) / 'retained'
        self.load.mkdir(parents=True)
        self.run = 'test-load'
        self.pod = '44444444-4444-4444-8444-444444444444'
        pins = {'instrument': 'test'}
        (self.load / 'runid').write_text(self.run)
        write(self.load / 'before.json', {'runId': 'test', 'namespace': {'uid': 'ns'}, 'pins': pins,
                                         'pods': {'e': {'workload': 'StatefulSet/evaluator'}}})
        write(self.load / 'native-load.json', {
            'kind': 'm7-kubernetes-k6-job-v1', 'podUid': self.pod, 'artifactSource': {'podUid': self.pod},
            'runId': self.run, 'fixtureRunId': 'test', 'namespaceUid': 'ns', 'pins': pins})
        write(self.load / 'window.json', {'runId': self.run, 'namespaceUid': 'ns', 'pins': pins,
                                          'loadStartedAt': 10, 'loadEndedAt': 20})
        write(self.load / 'progress-before.json', dict(bookend(seeded()), pins=pins))
        write(self.load / 'progress-after.json', dict(bookend(run_rows()), pins=pins))
        write(self.load / 'stored-counts.json', {A: {'entries': 1}, B: {'entries': 0}, C: {'entries': 0}})
        write(self.load / 'storage-readback.json', {
            'verdict': 'OBSERVED', 'runId': self.run, 'namespaceUid': 'ns', 'pins': pins,
            'countsSha256': results.fingerprint(self.load / 'stored-counts.json')['sha256']})
        write(self.load / 'k6-summary.json', {'metrics': {
            'writes_ok': {'count': 1}, 'writes_uncertain': {'count': 0}, 'http_reqs': {'count': 1}}})
        write(self.load / 'k6.log', {'msg': json.dumps({
            'event': 'm7-input-accepted', 'run': self.run, 'tenant': A, 'domain': 'entries',
            'key': '42', 'acceptedAtMs': 100, 'requestToAcceptanceMs': 5})})
        write(self.load / 'native-artifacts.json', {'kind': 'm7-native-artifacts-v1', 'runId': self.run,
              'exitCode': 0, 'files': {f: {'bytes': (self.load / f).stat().st_size} for f in results.WRITER_FILES}})
        write(self.load / 'viewer-frames.jsonl', {'event': 'viewer-frame', 'version': 2,
            'run': self.run, 'tenant': A, 'atMs': 110, 'keys': {'entries': [42], 'devicestatus': [], 'treatments': []}})

    def test_roundtrip_after_source_removal_and_corruption_control(self):
        publication = results.publish(self.load, self.root)
        self.assertEqual(publication['status'], 'complete')
        self.assertEqual(results.publish(self.load, self.root), publication)
        shutil.rmtree(self.load.parent)
        report = results.rescore(self.root)
        self.assertEqual(report['evaluatorDeadline']['verdict'], 'PASS')
        self.assertEqual(report['viewerDelivery']['domains']['entries']['maxMs'], 10)
        self.assertEqual(report['http']['sourceCounts']['http_reqs'], 1)
        self.assertEqual(report['http']['httpVerdict'], 'UNMEASURED')  # insufficient per-shape counters
        writer = self.root / self.run / self.pod / 'writer'
        alone = results.rescore(writer)
        self.assertEqual(alone['http'], report['http'])
        self.assertEqual(alone['evaluatorDeadline']['verdict'], 'UNMEASURED')
        receipt = results.read(writer / 'publication.json')
        write(writer / 'publication.json', dict(receipt, runId='different-load'))
        with self.assertRaisesRegex(ValueError, 'do not match'):
            results.rescore(self.root)
        write(writer / 'publication.json', receipt)
        (self.root / 'observer' / 'viewer-frames.jsonl').write_text('')
        with self.assertRaisesRegex(ValueError, 'differs from its receipt'):
            results.rescore(self.root)

    def test_storage_refusals_read_the_named_retained_load_stage_only(self):
        results.publish(self.load, self.root)
        self.assertEqual(results.rescore(self.root)['storageRefusals']['verdict'], 'UNMEASURED')
        retained = self.load.parent / 'retained-load'
        retained.mkdir()
        write(retained / 'window.json', {'loadStartedAt': 1000, 'loadEndedAt': 1600})
        write(retained / 'metrics-snapshot.json', {'verdict': 'OBSERVED', 'file': 'metrics-tsdb.tar', 'observedAt': 1660})
        labels = {'pod': 'api-a', 'role': 'api', 'code': 'STORAGE_TIMEOUT', 'phase': 'clock', 'route_class': 'entries_write'}
        seen = []

        class Local:
            def __init__(self, archive):
                seen.append(archive)

            def query(self, expr, at):
                return [{'labels': labels, 'value': 0 if at == 1000 else 4}] if not expr.startswith('resets(') else []

            def close(self):
                seen.append('closed')
        value = coverage_verdict.refusals_from_load(retained, local=Local)
        self.assertEqual((value['verdict'], value['byCode']['STORAGE_TIMEOUT'], value['startS'], value['endS']),
                         ('OBSERVED', 4, 1000, 1660))
        self.assertEqual(seen, [retained / 'metrics-tsdb.tar', 'closed'])

    def test_lost_viewer_and_tenant_do_not_score_green(self):
        write(self.load / 'probe-exit.json', {'code': 'K8S_PROBE_FAILED'})
        after = results.read(self.load / 'progress-after.json')
        del after['tenants'][B]
        write(self.load / 'progress-after.json', after)
        counts = results.read(self.load / 'stored-counts.json')
        del counts[B]  # tenant survives only in the starting population
        write(self.load / 'stored-counts.json', counts)
        storage = results.read(self.load / 'storage-readback.json')
        with self.assertRaisesRegex(ValueError, 'do not match the run receipt'):
            results.publish_observer(self.load, self.root)
        storage['countsSha256'] = results.fingerprint(self.load / 'stored-counts.json')['sha256']
        write(self.load / 'storage-readback.json', storage)
        self.assertEqual(results.publish(self.load, self.root)['status'], 'partial')
        report = results.rescore(self.root)
        self.assertEqual(report['viewerDelivery']['verdict'], 'UNMEASURED')
        self.assertEqual(report['evaluatorDeadline']['verdict'], 'UNMEASURED')
        self.assertIn('DURABLE_LAG_TENANT_MISSING', report['evaluatorDeadline']['unmeasured'])

    def test_summary_exposes_a_missing_accepted_event(self):
        path = self.load / 'k6-summary.json'
        summary = results.read(path)
        summary['metrics']['writes_ok{kind:entries}'] = {'count': 2}
        write(path, summary)
        manifest = results.read(self.load / 'native-artifacts.json')
        manifest['files'][path.name]['bytes'] = path.stat().st_size
        write(self.load / 'native-artifacts.json', manifest)
        # The writer publication itself refuses a summary that counts more accepted requests than
        # k6.log holds, so the run is scored as incomplete writer evidence before any viewer join.
        self.assertEqual(results.publish(self.load, self.root)['writer'], 'partial')
        writer = results.read(self.root / self.run / self.pod / 'writer' / 'publication.json')
        self.assertEqual(writer['problems'], {'k6.log': 'accepted-request-count-mismatch'})
        report = results.rescore(self.root)
        self.assertEqual(report['reason'], 'incomplete writer evidence')
        self.assertEqual(report['viewerDelivery']['verdict'], 'UNMEASURED')

    def test_controller_packet_can_rejoin_independent_volume_after_writer_capture_loss(self):
        results.publish(self.load, self.root)
        writer = self.root / self.run / self.pod / 'writer'
        (self.load / 'native-artifacts.json').unlink()
        recovered = self.root.parent / 'interrupted'
        self.assertEqual(results.publish(self.load, recovered)['writer'], 'unavailable')
        shutil.rmtree(self.load.parent)
        self.assertEqual(results.rescore(recovered, writer)['evaluatorDeadline']['verdict'], 'PASS')

    def test_partial_writer_is_retained_and_unmeasured(self):
        (self.load / 'k6-summary.json').unlink()
        self.assertEqual(results.publish(self.load, self.root)['status'], 'partial')
        self.assertEqual(results.rescore(self.root)['evaluatorDeadline']['verdict'], 'UNMEASURED')


if __name__ == '__main__':
    unittest.main()
