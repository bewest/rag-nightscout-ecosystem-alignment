"""Reads whose size or cost grows with tenants, viewers or load seconds (INC-E, 2026-11-22).
Synthetic replies only; no kube, cloud or Docker."""
from pathlib import Path
import re
import tempfile
import unittest
import unittest.mock

import kube_adapter as k
from test_adapter import fixture

HERE = Path(__file__).resolve().parent


class ScaleReads(unittest.TestCase):
    def setUp(self):
        self.c, self.inv, self.render, self.client = fixture()
        self.objects = k.validate(self.c, self.inv, self.render)

    def packet(self, name):
        d = Path(name)
        k.write(d/'run.json', self.c)
        k.write(d/'observation.initial.json', k.observe(self.c, self.objects, self.client))
        return d

    def test_probe_output_over_the_configuration_bound_is_read(self):
        with tempfile.TemporaryDirectory() as name:
            probe = Path(name)/'probe.json'
            # 33 MiB: over the 32 MiB configuration bound, the size class of 100 viewers x 1,800 s.
            probe.write_text('{"window":{"startedAt":1},"kubernetesFrames":{"overflow":false,"rows":[]}}' + ' ' * (33 * 1024 * 1024))
            with self.assertRaisesRegex(k.Refused, 'K8S_INPUT_FILE'):
                k.document(probe)
            self.assertEqual(k.probe_document(probe)['window'], {'startedAt': 1})
            # The probe bound is still a bound.
            with unittest.mock.patch.object(k, 'PROBE_MAX_BYTES', 1024):
                with self.assertRaisesRegex(k.Refused, 'K8S_INPUT_FILE'):
                    k.probe_document(probe)
        for source in ('execute.py', 'matrix.py'):
            self.assertIsNone(re.search(r"k\.document\([^)\n]*probe\.json", (HERE/source).read_text()),
                              source + ' reads probe.json under the configuration bound')

    def test_seed_census_past_its_limit_keeps_the_epoch_observation(self):
        with tempfile.TemporaryDirectory() as name:
            d = self.packet(name)
            reads = []
            def call(argv, **kw):
                query = kw['data'].decode()
                reads.append((query, kw.get('timeout')))
                if 'synthetic-compose-demo' in query:
                    # The count ran past its limit (statement_timeout or the client limit).
                    raise k.Refused('K8S_OBSERVATION_LOST', 'UNMEASURED')
                return b'7000000000000000001\t1\tnightscout_compose_test\n'
            self.client.call = call
            observed = k.observe_sql(d, self.c, self.objects, d/'independent', self.client)
            self.assertEqual(observed['verdict'], 'OBSERVED')
            self.assertEqual(observed['nativeSource'], {'system_id': '7000000000000000001', 'timeline': 1, 'database': 'nightscout_compose_test'})
            self.assertEqual((observed['seedCensus'], observed['seedCensusCode'], observed['storedRows'], observed['storedTenants']),
                             ('UNMEASURED', 'K8S_SEED_CENSUS_BOUND', 'UNMEASURED', 'UNMEASURED'))
            self.assertEqual(k.document(d/'independent/result.json'), observed)
            # The epoch read touches no tenant table; the seed count carries its own server-side limit.
            epoch, seed = reads
            self.assertNotIn('nsdemo_entries', epoch[0])
            self.assertIn('SET LOCAL statement_timeout=%d;' % (k.SEED_CENSUS_SECONDS * 1000), seed[0])
            self.assertLessEqual(seed[1], 20)

    def test_seed_census_does_not_absorb_another_refusal(self):
        with tempfile.TemporaryDirectory() as name:
            d = self.packet(name)
            def call(argv, **kw):
                if 'synthetic-compose-demo' in kw['data'].decode():
                    raise k.Refused('K8S_WORK_DEADLINE', 'UNMEASURED')
                return b'1\t1\tnightscout_compose_test\n'
            self.client.call = call
            with self.assertRaisesRegex(k.Refused, 'K8S_WORK_DEADLINE'):
                k.observe_sql(d, self.c, self.objects, d/'independent', self.client)

    def test_run_marker_census_has_the_table_read_limit(self):
        with tempfile.TemporaryDirectory() as name:
            d = self.packet(name)
            limits = []
            def call(argv, **kw):
                limits.append(kw.get('timeout'))
                return b''
            self.client.call = call
            self.assertEqual(k.stored(d, self.c, self.objects, 'synthetic-run', self.client), {})
            # Four full-table counts: not the 20 s observation default, and inside the work deadline.
            self.assertEqual(len(limits), 1)
            self.assertIsNotNone(limits[0], 'RUN_MARKER_CENSUS_UNDER_OBSERVATION_DEFAULT')
            self.assertTrue(20 < limits[0] <= k.deadline(self.c) + 1, limits[0])
            with unittest.mock.patch.dict(k.os.environ, {'K8S_HISTORY_READ_SECONDS': '30'}):
                self.assertEqual(k.table_read_seconds(self.c), 30)


if __name__ == '__main__':
    unittest.main()
