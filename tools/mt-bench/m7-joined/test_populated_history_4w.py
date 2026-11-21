"""synthetic-history-4w-v1: row counts per collection, readback, its own fixture-catalog key."""
import copy
import json
import time
import unittest

import fixture_catalog
import populated_history as h

DAY = 86_400_000


class FourWeeks(unittest.TestCase):
    def setUp(self):
        self.anchor = int(time.time()*1000)//h.STEP_MS*h.STEP_MS - h.STEP_MS
        self.spec = {'mode': h.MODE_4W, 'anchorUnixMs': self.anchor}
        self.tenants = [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f'demo-{i}.test',
                         'token': f'local /{i}'} for i in range(2)]
        self.store = {}  # tenant -> path -> docs
        self.calls = []

    def save(self, port, tenant, docs, until, path='/api/v1/entries'):
        self.calls.append((tenant['id'], path, len(docs) if isinstance(docs, list) else 1))
        self.store.setdefault(tenant['id'], {}).setdefault(path, []).extend(docs if isinstance(docs, list) else [docs])

    def sql(self, query):
        if 'FROM pg_class' in query:
            return '\n'.join(f'{t}\tnsdemo_{t}' for t in ('entries', 'devicestatus', 'treatments', 'profile'))
        if query.startswith('SELECT DISTINCT'):
            return ''
        out = []
        for tenant, paths in self.store.items():
            e = paths.get('/api/v1/entries', []); d = paths.get('/api/v1/devicestatus', [])
            t = paths.get('/api/v1/treatments', []); p = paths.get('/api/v1/profile', [])
            if '"nsdemo_entries"."entries"' in query and e:
                out.append([tenant, len(e), len(json.dumps(e)), len(e), h.digest(sorted(e, key=lambda r: r['date']))])
            elif '"nsdemo_devicestatus"' in query and d:
                out.append([tenant, len(d), len(json.dumps(d)), sum(r['uploader']['battery'] for r in d)])
            elif '"nsdemo_treatments"' in query and t:
                out.append([tenant, len(t), len(json.dumps(t)), round(sum(r.get('insulin', 0) for r in t)*10),
                            sum(r.get('carbs', 0) for r in t)])
            elif '"nsdemo_profile"' in query and p:
                out.append([tenant, len(p)])
        return '\n'.join('\t'.join(map(str, r)) for r in out)

    def fixture(self, **changes):
        options = dict(spec=self.spec, tenants=self.tenants, base='http://127.0.0.1:8000',
                       sql=self.sql, until=None, window_seconds=300, post_batch=self.save)
        return h.run(**(options | changes))

    def test_row_counts_per_collection(self):
        receipt = self.fixture()
        self.assertEqual(h.rows_per_tenant(self.spec),
                         {'entries': 4*7*288, 'devicestatus': 4*7*288, 'treatments': 28*8, 'profile': 1})
        for tenant in self.tenants:
            paths = self.store[tenant['id']]
            self.assertEqual({k: len(v) for k, v in paths.items()},
                             {'/api/v1/entries': 8064, '/api/v1/devicestatus': 8064, '/api/v1/treatments': 224,
                              '/api/v1/profile': 1})
            e = paths['/api/v1/entries']
            self.assertEqual(max(r['date'] for r in e), self.anchor)
            self.assertEqual(self.anchor - min(r['date'] for r in e), (8064 - 1) * h.STEP_MS)
            self.assertEqual(len({r['date'] for r in e}), 8064)
            t = paths['/api/v1/treatments']
            self.assertEqual(len({(r['created_at'], r['eventType']) for r in t}), 224)
            self.assertTrue(all(r['created_at'] <= h._iso(self.anchor) for r in t))
            kinds = [r['eventType'] for r in t]
            self.assertEqual((kinds.count('Meal Bolus'), kinds.count('Correction Bolus'), kinds.count('Temp Basal')),
                             (84, 28, 112))
        # batches stay under the edge's 2 MB body limit
        self.assertEqual(sorted({(p, n) for _, p, n in self.calls}),
                         [('/api/v1/devicestatus', 1008), ('/api/v1/entries', 2016), ('/api/v1/profile', 1),
                          ('/api/v1/treatments', 224)])
        self.assertLess(len(json.dumps(h.devicestatus_4w(self.anchor, 0)[:h.DS_BATCH])), 2*1024*1024)
        self.assertEqual((receipt['rows'], receipt['collections']['devicestatus']['rows'],
                          receipt['collections']['treatments']['rows'], receipt['seededBatches']), (16128, 16128, 448, 2))
        restored = self.fixture(verify_only=True, tenants=self.tenants[::-1])
        self.assertEqual((restored['logicalSha256'], restored['seededBatches']), (receipt['logicalSha256'], 0))
        self.assertNotIn('local /', json.dumps(receipt))

    def test_refuses_partial_corrupt_and_stale(self):
        self.fixture()
        healthy = copy.deepcopy(self.store)
        key = self.tenants[0]['id']
        for mutate in (lambda: self.store[key]['/api/v1/devicestatus'].pop(),
                       lambda: self.store[key]['/api/v1/treatments'][0].update(carbs=1),
                       lambda: self.store[key]['/api/v1/entries'][5].update(sgv=999),
                       lambda: self.store[key].pop('/api/v1/profile'),
                       lambda: self.store.pop(key)):
            mutate()
            with self.assertRaisesRegex(ValueError, 'M7_HISTORY_'):
                self.fixture(verify_only=True)
            self.store = copy.deepcopy(healthy)
        for clock in (self.anchor/1000 - 1, (self.anchor + h.MAX_STALE_4W_MS)/1000):
            with self.assertRaisesRegex(ValueError, 'OUTSIDE_CLINICAL_WINDOW'):
                self.fixture(now=lambda: clock, verify_only=True)
        self.assertEqual(self.fixture(verify_only=True)['seededBatches'], 0)

    def test_own_fixture_key_and_validation(self):
        h.validate(self.spec)
        base = dict(tenants=1000, image='sha256:'+'a'*64, postgres_image='sha256:'+'b'*64,
                    schema='migrations-tree:'+'c'*40, transport='writer-driven')
        k6h = fixture_catalog.digest(fixture_catalog.key(**base, history={'mode': h.MODE, 'anchorUnixMs': self.anchor}))
        k4w = fixture_catalog.digest(fixture_catalog.key(**base, history=self.spec))
        self.assertNotEqual(k6h, k4w)
        with self.assertRaisesRegex(ValueError, 'ANCHOR'):
            h.validate(dict(self.spec, anchorUnixMs=self.anchor + 1))
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED'):
            h.validate(dict(self.spec, mode='synthetic-history-5w-v1'))


if __name__ == '__main__':
    unittest.main()
