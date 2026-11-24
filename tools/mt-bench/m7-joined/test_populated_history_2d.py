"""synthetic-history-2d-v1: two days (the evaluator's cold window), own marker and fixture-catalog key."""
import copy
import json
import unittest
import unittest.mock

import fixture_catalog
import populated_history as h
import test_populated_history_4w as four_weeks


class TwoDays(four_weeks.FourWeeks):
    def setUp(self):
        super().setUp()
        self.spec = {'mode': h.MODE_2D, 'anchorUnixMs': self.anchor}

    # The inherited four-week assertions do not apply to this mode.
    test_row_counts_per_collection = None
    test_refuses_partial_corrupt_and_stale = None
    test_own_fixture_key_and_validation = None

    def test_two_day_rows_fit_the_evaluator_window(self):
        receipt = self.fixture()
        self.assertEqual(h.rows_per_tenant(self.spec),
                         {'entries': 576, 'devicestatus': 576, 'treatments': 16, 'profile': 1})
        for tenant in self.tenants:
            paths = self.store[tenant['id']]
            self.assertEqual({k: len(v) for k, v in paths.items()},
                             {'/api/v1/entries': 576, '/api/v1/devicestatus': 576, '/api/v1/treatments': 16,
                              '/api/v1/profile': 1})
            e = paths['/api/v1/entries']
            self.assertEqual(max(r['date'] for r in e), self.anchor)
            # every SGV row lies inside the evaluator's 48 h cold lookback at the anchor
            self.assertLess(self.anchor - min(r['date'] for r in e), h.LOOKBACK_MS)
            self.assertEqual(len({r['date'] for r in e}), 576)
            self.assertEqual({r['device'] for r in e}, {h.DEVICE_2D})
            self.assertEqual({r['device'] for r in paths['/api/v1/devicestatus']}, {'openaps://' + h.DEVICE_2D})
            t = paths['/api/v1/treatments']
            self.assertEqual({r['enteredBy'] for r in t} | {paths['/api/v1/profile'][0]['enteredBy']}, {h.DEVICE_2D})
            self.assertEqual(len({(r['created_at'], r['eventType']) for r in t}), 16)
            self.assertTrue(all(r['created_at'] <= h._iso(self.anchor) for r in t))
        self.assertEqual(sorted({(p, n) for _, p, n in self.calls}),
                         [('/api/v1/devicestatus', 288), ('/api/v1/entries', 288), ('/api/v1/profile', 1),
                          ('/api/v1/treatments', 16)])
        self.assertEqual((receipt['rows'], receipt['collections']['devicestatus']['rows'],
                          receipt['collections']['treatments']['rows'], receipt['seededBatches']), (1152, 1152, 32, 2))
        restored = self.fixture(verify_only=True, tenants=self.tenants[::-1])
        self.assertEqual((restored['logicalSha256'], restored['seededBatches']), (receipt['logicalSha256'], 0))

    def test_refuses_partial_and_stale(self):
        self.fixture()
        healthy = copy.deepcopy(self.store)
        key = self.tenants[0]['id']
        for mutate in (lambda: self.store[key]['/api/v1/devicestatus'].pop(),
                       lambda: self.store[key]['/api/v1/entries'][5].update(sgv=999),
                       lambda: self.store.pop(key)):
            mutate()
            with self.assertRaisesRegex(ValueError, 'M7_HISTORY_'):
                self.fixture(verify_only=True)
            self.store = copy.deepcopy(healthy)
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_CLINICAL_WINDOW'):
            self.fixture(now=lambda: (self.anchor + h.MAX_STALE_4W_MS) / 1000, verify_only=True)

    def test_own_fixture_key(self):
        h.validate(self.spec)
        base = dict(tenants=1000, image='sha256:'+'a'*64, postgres_image='sha256:'+'b'*64,
                    schema='migrations-tree:'+'c'*40, transport='writer-driven')
        keys = {fixture_catalog.digest(fixture_catalog.key(**base, history={'mode': m, 'anchorUnixMs': self.anchor}))
                for m in (h.MODE, h.MODE_4W, h.MODE_2D)}
        self.assertEqual(len(keys), 3)
        with self.assertRaisesRegex(ValueError, 'ANCHOR'):
            h.validate(dict(self.spec, anchorUnixMs=self.anchor + 1))

    def test_four_week_output_unchanged_by_the_parameters(self):
        # The default arguments are the four-week shape; a 2 d call is a strict suffix of its SGV series.
        a, i = self.anchor, 3
        self.assertEqual(h.entries_4w(a, i), h.entries_4w(a, i, h.DAYS_4W, h.DEVICE_4W))
        self.assertEqual(len(h.entries_4w(a, i)), h.SGV_4W)
        self.assertEqual([r['sgv'] for r in h.entries_4w(a, i)[-576:]], [r['sgv'] for r in h.entries_4w(a, i, 2, h.DEVICE_2D)])
        self.assertEqual(h.expected_4w(a, i)['treatments'], h.TREATMENTS_4W)
        self.assertEqual(json.dumps(h.profile_4w(a)), json.dumps(h.profile_4w(a, h.DAYS_4W, h.DEVICE_4W)))

    def test_seed_limits_change_requests_not_rows(self):
        self.assertEqual(h.seed_limits({}), (h.WORKERS_4W, 288))
        self.assertEqual(h.seed_limits({'S4_HISTORY_SEED_WORKERS': '4', 'S4_HISTORY_SEED_BATCH': '96'}), (4, 96))
        for bad in ({'S4_HISTORY_SEED_WORKERS': '0'}, {'S4_HISTORY_SEED_BATCH': '289'}):
            with self.assertRaisesRegex(ValueError, 'SEED_LIMITS'):
                h.seed_limits(bad)
        whole = self.fixture()
        self.store, self.calls = {}, []
        with unittest.mock.patch.dict('os.environ', {'S4_HISTORY_SEED_BATCH': '96', 'S4_HISTORY_SEED_WORKERS': '2'}):
            small = self.fixture()
        self.assertEqual(sorted({(p, n) for _, p, n in self.calls if p in ('/api/v1/entries', '/api/v1/devicestatus')}),
                         [('/api/v1/devicestatus', 96), ('/api/v1/entries', 96)])
        self.assertEqual(small['logicalSha256'], whole['logicalSha256'])


if __name__ == '__main__':
    unittest.main()
