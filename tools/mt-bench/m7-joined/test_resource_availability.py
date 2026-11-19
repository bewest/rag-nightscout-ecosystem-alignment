"""Independent CPU/SQL survives an honestly incomplete resource census."""
import json
from pathlib import Path
import tempfile
import unittest

from reduce import measurements


class ResourceAvailability(unittest.TestCase):
    def fixture(self, root):
        for phase in ('idle-disabled', 'idle', 'load'):
            folder = root / phase
            folder.mkdir()
            for edge, at, cpu in [('before', 1, 1000000), ('after', 3, 2000000)]:
                value = {'at': at, 'serviceCoverage': {'status': 'MEASURED'}, 'roles': {
                    'api': {'id': 'same', 'cgroup': f'usage_usec {cpu}\n1024\nanon 512\n',
                            'processRssKiB': 'PID COMMAND RSS\n1 node 100'}}}
                (folder / (edge + '-cgroups.json')).write_text(json.dumps(value))
                (folder / (edge + '-pg-role.tsv')).write_text('api\t' + str(at) + '\t' + str(at * 10) + '\n')
            if phase != 'idle-disabled':
                (folder / 'docker-stats.tsv').write_text('t\tcontainer\tcpu_pct\tmem\n2\towned-api-1\t50%\t1MiB / 1GiB\n')
                (folder / 'pg-activity.tsv').write_text('t\trole\tstate\twait_event_type\twait_event\tn\n2\tapi\tidle\tClient\tClientRead\t1\n')
        shapes = ('w_sgv', 'w_devicestatus', 'w_treatments_v3', 'r_sgv', 'r_devicestatus', 'r_treatments', 'r_status')
        (root / 'load/k6-summary.json').write_text(json.dumps({'metrics': {
            'http_req_duration{shape:' + shape + '}': {'med': 1, 'p(95)': 2, 'p(99)': 3, 'count': 1} for shape in shapes}}))

    def reduce(self, root):
        return measurements(root, {'project': 'owned', 'tenants': 2})

    def test_identity_coverage_refusal_preserves_cpu_sql_and_optional_absence(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch);self.fixture(root)
            good = self.reduce(root)
            self.assertTrue(good['complete']);self.assertEqual(good['incompleteReasons'], [])
            row = good['windows']['load']['roles']['api']
            self.assertEqual(row['availability']['containerCpu']['status'], 'MEASURED')
            for key in ('memoryPeak', 'resourceLimits'):
                self.assertEqual(row['availability'][key]['status'], 'UNMEASURED')
                self.assertFalse(row['availability'][key]['required'])
            file = root / 'load/after-cgroups.json';original = file.read_text()
            broken = json.loads(original)
            broken['serviceCoverage'] = {'status': 'UNMEASURED', 'reason': 'M7_INSTANCE_RUNTIME_IDENTITY'}
            file.write_text(json.dumps(broken))
            value = self.reduce(root)
            self.assertFalse(value['complete'])
            self.assertEqual(len(value['incompleteReasons']), 1)
            reason = value['incompleteReasons'][0]
            self.assertEqual((reason['phase'], reason['criterion']), ('load', 'serviceCoverage'))
            self.assertEqual(reason['details']['after']['reason'], 'M7_INSTANCE_RUNTIME_IDENTITY')
            self.assertEqual(value['windows']['load']['roles']['api']['cpuCoresMean'], .5)
            self.assertEqual(value['windows']['load']['pgStatements']['api']['calls'], 2)
            file.write_text(original);self.assertTrue(self.reduce(root)['complete'])

    def test_missing_collector_keeps_independent_aggregate_and_bookends(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            self.fixture(root)
            for name in ('pg-activity.tsv', 'after-pg-role.tsv', 'after-cgroups.json', 'k6-summary.json'):
                with self.subTest(name=name):
                    path = root/'load'/name
                    data = path.read_bytes()
                    path.unlink()
                    result = self.reduce(root)
                    self.assertFalse(result['complete'])
                    load = result['windows']['load']
                    if name != 'after-cgroups.json':
                        self.assertEqual(load['roles']['api']['cpuCoresMean'], .5)
                    if name != 'after-pg-role.tsv':
                        self.assertEqual(load['pgStatements']['api']['calls'], 2)
                    self.assertEqual(result['windows']['idle']['roles']['api']['cpuCoresMean'], .5)
                    path.write_bytes(data)
                    self.assertTrue(self.reduce(root)['complete'])

    def test_distinct_required_gaps_are_named_then_restored(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch);self.fixture(root)
            file = root / 'load/after-cgroups.json';original = file.read_text()
            for mutate, criterion in [
                    (lambda row: row.pop('processRssKiB'), 'processRss'),
                    (lambda row: row.update(cgroup='usage_usec 1\n1024\nanon 512\n'), 'containerCpu'),
                    (lambda row: row.update(id='other-container'), 'containerCpu')]:
                broken = json.loads(original);mutate(broken['roles']['api']);file.write_text(json.dumps(broken))
                value = self.reduce(root);self.assertFalse(value['complete'])
                self.assertIn(criterion, [v['criterion'] for v in value['incompleteReasons']])
                self.assertEqual(value['windows']['load']['pgStatements']['api']['calls'], 2)
                file.write_text(original);self.assertTrue(self.reduce(root)['complete'])
            for name, header, criterion in [('docker-stats.tsv', 't\tcontainer\tcpu_pct\tmem\n', 'dockerStats'),
                                             ('pg-activity.tsv', 't\trole\tstate\twait_event_type\twait_event\tn\n', 'pgActivity')]:
                path = root / 'load' / name;saved = path.read_text();path.write_text(header)
                value = self.reduce(root);self.assertFalse(value['complete'])
                self.assertIn(criterion, [v['criterion'] for v in value['incompleteReasons']])
                self.assertEqual(value['windows']['load']['roles']['api']['cpuCoresMean'], .5)
                path.write_text(saved);self.assertTrue(self.reduce(root)['complete'])


if __name__ == '__main__':
    unittest.main()
