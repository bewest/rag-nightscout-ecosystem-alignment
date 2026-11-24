"""The populated-history step on a restored fixture (lane R10k, #8898 round, 2026-11-22).

On reuse the step read every tenant back with a scan of every stored row; at 10k tenants (about
17.6M rows) on a freshly restored volume it outlived its 900 s limit, K8S_OBSERVATION_LOST failed the
case before load (w5-10k-k20). A restored case now runs no census: its identity is the fixture record's
import-time readback digest; only the anchor's clinical window is checked. The full census stays an
operator opt-in (K8S_RESTORED_HISTORY_CENSUS=full).
Synthetic tenants and a fake SQL only; no kube, cloud or Docker."""
import copy
import json
import re
import time
import unittest
import unittest.mock

import kube_adapter as k
import execute
import experiment
import looping_history_v2 as V2
import populated_history as h

STEP = h.STEP_MS


class Store:
    """Fake API store and the census SQL over it. `slow` refuses any census that reads every tenant,
    the way the 900 s kubectl exec limit did at 10k."""

    def __init__(self):
        self.docs = {}
        self.queries = []
        self.slow = False

    def save(self, port, tenant, body, until, path='/api/v1/entries'):
        rows = body if isinstance(body, list) else [body]
        self.docs.setdefault(tenant['id'], {}).setdefault(path, []).extend(copy.deepcopy(rows))

    def sql(self, query):
        self.queries.append(query)
        if 'FROM pg_class' in query:
            return '\n'.join(f'{t}\tnsdemo_{t}' for t in ('entries', 'devicestatus', 'treatments', 'profile'))
        if query.startswith('SELECT DISTINCT'):
            return ''
        if 'GROUP BY tenant_id' in query and self.slow:
            raise k.Refused('K8S_OBSERVATION_LOST', 'UNMEASURED')
        out = []
        for tenant, paths in self.docs.items():
            e = paths.get('/api/v1/entries', []); d = paths.get('/api/v1/devicestatus', [])
            t = paths.get('/api/v1/treatments', []); p = paths.get('/api/v1/profile', [])
            if '"nsdemo_entries"."entries"' in query and e:
                out.append([tenant, len(e), len(json.dumps(e)), len(e), h.digest(sorted(e, key=lambda r: r['date']))])
            elif '"nsdemo_devicestatus"' in query and d:
                out.append([tenant, len(d), len(json.dumps(d)), sum(r['uploader']['battery'] for r in d)])
            elif '"nsdemo_treatments"' in query and t:
                out.append([tenant, len(t), len(json.dumps(t)), round(sum(r.get('insulin', 0) for r in t)*100),
                            sum(r.get('carbs', 0) for r in t)])
            elif '"nsdemo_profile"' in query and p:
                out.append([tenant, len(p), len(json.dumps(p))])
        return '\n'.join('\t'.join(map(str, r)) for r in out)


class RestoredHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        anchor = int(time.time()*1000)//STEP*STEP - STEP
        cls.spec = V2.default_spec(anchor, deepHistoryTenants=0)
        cls.tenants = [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f'demo-{i:02d}.test', 'token': f'local /{i}'}
                       for i in range(12)]
        cls.seeded = Store()
        cls.digest = h.run(cls.spec, cls.tenants, 'http://127.0.0.1:8000', cls.seeded.sql, None, 300,
                           post_batch=cls.seeded.save)['logicalSha256']

    def setUp(self):
        self.store = Store()
        self.store.docs = copy.deepcopy(self.seeded.docs)
        until = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 3600))
        self.c = {'history': self.spec, 'restoredHistory': True, 'baseUrl': 'http://127.0.0.1:8000',
                  'deadlines': {'workUntil': until}, 'workload': {'loadSeconds': 1800}}
        self.limits = []

    def receipt(self):
        def sql(d, c, objects, query, client=None, timeout=None):
            self.limits.append(timeout)
            return self.store.sql(query)
        with unittest.mock.patch.object(k, 'sql', sql), \
                unittest.mock.patch.object(execute, 'roster', return_value=self.tenants):
            return experiment.history_receipt(None, self.c, None, None)

    def identity(self):
        self.c['restoredFixture'] = {'catalog': 'f' * 16, 'fixtureId': 'synthetic', 'historyLogicalSha256': self.digest,
                                     'archiveSha256': 'a' * 64}

    def test_long_census_on_reuse_does_not_fail_the_case(self):
        # w5-10k-k20: the full census never returns in time. Reuse does not run it.
        self.store.slow = True
        self.identity()
        receipt = self.receipt()
        self.assertEqual(receipt['readback'], 'NOT_RUN_ON_REUSE')
        self.assertEqual(self.store.queries, [])
        self.assertEqual(receipt['logicalSha256'], self.digest)
        self.assertEqual(receipt['logicalSha256Source'], 'import-time readback (fixture record)')
        self.assertEqual(receipt['seededBatches'], 0)

    def test_reuse_without_a_fixture_record_says_so(self):
        receipt = self.receipt()
        self.assertIsNone(receipt['logicalSha256'])
        self.assertEqual(receipt['logicalSha256Source'], 'UNRECORDED')

    def test_stale_anchor_still_refuses_on_reuse(self):
        self.c['deadlines']['workUntil'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 2 * 86400))
        with self.assertRaisesRegex(ValueError, 'M7_HISTORY_OUTSIDE_CLINICAL_WINDOW'):
            self.receipt()

    def test_opt_in_full_census_reads_every_tenant(self):
        self.identity()
        with unittest.mock.patch.dict(experiment.os.environ, {'K8S_RESTORED_HISTORY_CENSUS': 'full'}):
            receipt = self.receipt()
        self.assertEqual(receipt['logicalSha256'], self.digest)
        self.assertTrue([q for q in self.store.queries if 'GROUP BY tenant_id' in q])
        # Red control: a changed row is still refused by the opt-in readback.
        self.store.queries.clear()
        self.store.docs[self.tenants[0]['id']]['/api/v1/entries'][0]['sgv'] += 1
        with unittest.mock.patch.dict(experiment.os.environ, {'K8S_RESTORED_HISTORY_CENSUS': 'full'}):
            with self.assertRaisesRegex(ValueError, 'M7_HISTORY_READBACK_MISMATCH'):
                self.receipt()

    def test_seeded_case_keeps_the_full_readback(self):
        self.c['restoredHistory'] = False
        receipt = self.receipt()
        self.assertEqual(receipt['logicalSha256'], self.digest)
        self.assertTrue([q for q in self.store.queries if 'GROUP BY tenant_id' in q])
        self.assertTrue(all(t > 60 for t in self.limits), self.limits)


if __name__ == '__main__':
    unittest.main()
