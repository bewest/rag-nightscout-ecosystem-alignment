"""synthetic-history-looping-2d-v1: cadence, roles, profiles, determinism, own key and marker, seed readback.

Each property test has a red control: the same test run against a broken generator must fail."""
import collections
import copy
import hashlib
import json
import time
import unittest
import unittest.mock

import fixture_catalog
import looping_history as L
import populated_history as h

DAY = 86_400_000
BASE_KEY = dict(tenants=10, image='sha256:'+'a'*64, postgres_image='sha256:'+'b'*64,
                schema='migrations-tree:'+'c'*40, transport='writer-driven')


def docs(t):
    return dict(entries=L.entries(t), devicestatus=L.devicestatus(t), treatments=L.treatments(t), profile=L.profiles(t))


class Looping(unittest.TestCase):
    def setUp(self):
        self.anchor = int(time.time()*1000)//h.STEP_MS*h.STEP_MS - h.STEP_MS
        self.spec = L.default_spec(self.anchor)
        self.tenants = [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f'demo-{i:02d}.test',
                         'token': f'local /{i}'} for i in range(10)]
        self.store = {}
        self.calls = []

    # ------------------------------------------------------------- fake API and SQL
    def save(self, port, tenant, body, until, path='/api/v1/entries'):
        rows = body if isinstance(body, list) else [body]
        self.calls.append((tenant['id'], path, len(rows), len(json.dumps(body))))
        self.store.setdefault(tenant['id'], {}).setdefault(path, []).extend(copy.deepcopy(rows))

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
                out.append([tenant, len(t), len(json.dumps(t)), round(sum(r.get('insulin', 0) for r in t)*100),
                            sum(r.get('carbs', 0) for r in t)])
            elif '"nsdemo_profile"' in query and p:
                out.append([tenant, len(p), len(json.dumps(p))])
        return '\n'.join('\t'.join(map(str, r)) for r in out)

    def fixture(self, **changes):
        options = dict(spec=self.spec, tenants=self.tenants, base='http://127.0.0.1:8000',
                       sql=self.sql, until=None, window_seconds=300, post_batch=self.save)
        return h.run(**(options | changes))

    def red(self, test, *patches):
        """Measurement rule 3: the property test must fail (an assertion, not a crash) against a broken generator."""
        with unittest.mock.patch.multiple(L, **dict(patches)):
            with self.assertRaises(AssertionError):
                test()

    # ------------------------------------------------------------- properties
    def check_cadence(self):
        for role in ('looping', 'cgm-only'):
            t = L.Tenant(self.spec, 1, role)
            for name in ('entries', 'devicestatus'):
                rows = docs(t)[name]
                if role == 'cgm-only' and name == 'devicestatus':
                    self.assertEqual(rows, [])
                    continue
                stamps = [r['date'] if name == 'entries' else h_ms(r['created_at']) for r in rows]
                self.assertEqual(len(rows), 576)
                self.assertEqual(max(stamps), self.anchor)
                self.assertEqual({b - a for a, b in zip(stamps, stamps[1:])}, {300_000})
                self.assertLess(self.anchor - min(stamps), h.LOOKBACK_MS)

    def test_cadence_every_five_minutes(self):
        self.check_cadence()

    def test_red_cadence(self):
        class TenMinutes(L.Tenant):   # SGV and devicestatus every 10 min, ending at the anchor
            def stamp(self, index):
                return self.anchor - (self.n - 1 - index) * 600_000
        self.red(self.check_cadence, ('Tenant', TenMinutes))

    def check_treatments(self):
        for i in range(6):
            t = L.Tenant(self.spec, i, 'looping')
            tx = L.treatments(t)
            self.assertEqual(len(tx), 2 * L.LOOPING_TREATMENTS_PER_DAY)
            self.assertGreaterEqual(len(tx) / t.days, 100)
            kinds = collections.Counter(r['eventType'] for r in tx)
            self.assertEqual((kinds['Temp Basal'], kinds['Meal Bolus'], kinds['Carb Correction']), (288, 6, 2))
            self.assertEqual(sum(1 for r in tx if r['eventType'] == 'Correction Bolus'), 24)
            switches = {'loop': {'Temporary Override': 4}, 'aaps': {'Profile Switch': 2, 'Temporary Target': 2},
                        'trio': {'Profile Switch': 2, 'Temporary Target': 2}}[t.kind]
            self.assertEqual({k: kinds[k] for k in switches}, switches)
            # v1 treatments upsert on (created_at, eventType): every row must be its own key
            self.assertEqual(len({(r['created_at'], r['eventType']) for r in tx}), len(tx))
            iso = [r['created_at'] for r in tx]
            self.assertTrue(h._iso(t.first) <= min(iso) and max(iso) <= h._iso(self.anchor))
            for r in tx:
                if r['eventType'] == 'Profile Switch':
                    self.assertIn(r['profile'], L.profiles(t)[-1]['store'])
                    self.assertEqual(json.loads(r['profileJson']), L.profiles(t)[-1]['store'][r['profile']])

    def test_treatments_at_loop_cadence(self):
        self.check_treatments()

    def test_red_treatments(self):
        self.red(self.check_treatments, ('LOOPING_DAY', dict(L.LOOPING_DAY, tempBasal=40)))

    def check_profiles(self):
        t = L.Tenant(self.spec, 2, 'looping')
        p = L.profiles(t)
        self.assertEqual(len(p), 3)
        self.assertEqual(len({r['startDate'] for r in p}), 3)  # revisions, not copies
        self.assertNotEqual(p[0]['store'], p[-1]['store'])
        for doc in p:
            self.assertEqual(set(doc['store']), {'Default', 'Weekend', 'Exercise'})
            for one in doc['store'].values():
                self.assertEqual(len(one['basal']), 24)
                self.assertEqual([len(one[k]) for k in ('carbratio', 'sens', 'target_low', 'target_high')], [4, 4, 3, 3])
        deep = L.Tenant(L.default_spec(self.anchor, deepHistoryTenants=1, deepHistoryDays=92), 0, 'deep')
        self.assertEqual(len(L.profiles(deep)), 3 + 92 // 30)

    def test_profiles_with_revisions_and_full_schedules(self):
        self.check_profiles()

    def test_red_profiles(self):
        self.red(self.check_profiles, ('LOOPING_PROFILES', 1))

    def check_devicestatus_is_loop_sized(self):
        seen = set()
        for i in range(30):
            t = L.Tenant(self.spec, i, 'looping')
            ds = L.devicestatus(t)
            seen.add(t.kind)
            for d in ds[::50]:
                self.assertTrue(d['device'] in L.DS_DEVICES and 'pump' in d and 'uploader' in d)
                self.assertIn('loop' if t.kind == 'loop' else 'openaps', d)
                if t.kind == 'loop':
                    self.assertGreaterEqual(len(d['loop']['predicted']['values']), 48)
                    self.assertTrue({'iob', 'cob', 'automaticDoseRecommendation'} <= set(d['loop']))
                else:
                    s = d['openaps']['suggested']
                    self.assertTrue({'IOB', 'ZT', 'UAM'} <= set(s['predBGs']) and len(s['predBGs']['IOB']) == 48)
                    self.assertTrue({'iob', 'suggested'} <= set(d['openaps']) and 'COB' in s and 'reason' in s)
            enacted = sum(1 for d in ds if 'enacted' in d.get('openaps', d.get('loop', {})))
            self.assertEqual(enacted, 288)   # one per temp basal
            size = sum(len(json.dumps(d)) for d in ds) / len(ds)
            self.assertGreater(size, 1000 if t.kind == 'loop' else 2500)
        self.assertEqual(seen, set(L.KINDS))

    def test_devicestatus_is_loop_sized(self):
        self.check_devicestatus_is_loop_sized()

    def test_red_devicestatus(self):
        # the 2-day mode's small status in place of full loop documents
        small = lambda t, i, iso, enacted: dict(h.devicestatus_4w(t.anchor, t.ordinal, 1, L.DEVICE)[0],
                                                device=L.DS_PREFIX[t.kind] + L.DEVICE, created_at=iso)
        self.red(self.check_devicestatus_is_loop_sized, ('_loop', small), ('_oref', small))

    def check_cgm_only_fraction(self):
        for n, pct, cgm in ((10, 20, 2), (1000, 20, 200), (7, 50, 4), (10, 0, 0), (10, 100, 10)):
            spec = L.default_spec(self.anchor, cgmOnlyPercent=pct)
            self.assertEqual(L.roles(spec, n).count('cgm-only'), cgm)
        receipt = self.fixture()
        cgm_ids = {self.tenants_sorted()[i]['id'] for i, r in enumerate(L.roles(self.spec, 10)) if r == 'cgm-only'}
        self.assertEqual(len(cgm_ids), 2)
        for tenant in cgm_ids:
            self.assertNotIn('/api/v1/devicestatus', self.store[tenant])
        self.assertEqual(receipt['roles']['cgm-only']['tenants'], 2)
        self.assertEqual(receipt['roles']['cgm-only']['devicestatus']['rows'], 0)

    def tenants_sorted(self):
        return sorted(self.tenants, key=lambda row: row['host'])

    def test_cgm_only_fraction(self):
        self.check_cgm_only_fraction()

    def test_red_cgm_only_fraction(self):
        # a generator that ignores the option: every tenant loops
        self.red(self.check_cgm_only_fraction, ('roles', lambda spec, n: ['looping'] * n))
        # an option left out of the spec is refused, not defaulted (it is part of the fixture key)
        spec = dict(self.spec); spec.pop('cgmOnlyPercent')
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED'):
            h.validate(spec)

    def check_deterministic(self):
        def fingerprint(spec):
            return hashlib.sha256(json.dumps([docs(L.Tenant(spec, i, r)) for i, r in enumerate(L.roles(spec, 6))],
                                             sort_keys=True).encode()).hexdigest()
        self.assertEqual(fingerprint(self.spec), fingerprint(copy.deepcopy(self.spec)))
        self.assertNotEqual(fingerprint(self.spec), fingerprint(dict(self.spec, seed=self.spec['seed'] + 1)))

    def test_deterministic_from_the_seed(self):
        self.check_deterministic()

    def test_red_deterministic(self):
        import random as stdlib
        self.red(self.check_deterministic, ('random', unittest.mock.Mock(Random=lambda _: stdlib.Random())))

    def check_own_key_and_marker(self):
        h.validate(self.spec)
        specs = [{'mode': h.MODE, 'anchorUnixMs': self.anchor}, {'mode': h.MODE_4W, 'anchorUnixMs': self.anchor},
                 {'mode': h.MODE_2D, 'anchorUnixMs': self.anchor}, h.default_spec(h.MODE_LOOPING, self.anchor),
                 L.default_spec(self.anchor, cgmOnlyPercent=0), L.default_spec(self.anchor, deepHistoryTenants=2),
                 L.default_spec(self.anchor, seed=7)]
        keys = {fixture_catalog.digest(fixture_catalog.key(**BASE_KEY, history=s)) for s in specs}
        self.assertEqual(len(keys), len(specs))
        self.assertEqual(h.default_spec(h.MODE_LOOPING, self.anchor), self.spec)
        # its own row marker: readback never counts another mode's rows
        self.assertEqual(len({h.DEVICE, h.DEVICE_4W, h.DEVICE_2D, L.DEVICE}), 4)
        t = L.Tenant(self.spec, 0, 'looping')
        self.assertEqual({r['device'] for r in L.entries(t)}, {L.DEVICE})
        self.assertEqual({r['enteredBy'] for r in L.treatments(t) + L.profiles(t)}, {L.DEVICE})

    def test_own_fixture_key_and_marker(self):
        self.check_own_key_and_marker()

    def test_red_key_collision_with_2d(self):
        self.red(self.check_own_key_and_marker, ('DEVICE', h.DEVICE_2D))
        self.red(self.check_own_key_and_marker,
                 ('default_spec', lambda anchor, **_: {'mode': h.MODE_2D, 'anchorUnixMs': anchor}))

    def test_validation(self):
        for bad, code in ((dict(self.spec, anchorUnixMs=self.anchor + 1), 'ANCHOR'),
                          (dict(self.spec, cgmOnlyPercent=101), 'LOOPING_OPTIONS'),
                          (dict(self.spec, cgmOnlyPercent=0.2), 'LOOPING_OPTIONS'),
                          (dict(self.spec, deepHistoryDays=2), 'LOOPING_OPTIONS'),
                          (dict(self.spec, extra=1), 'UNSUPPORTED')):
            with self.assertRaisesRegex(ValueError, code):
                h.validate(bad)
        with self.assertRaisesRegex(ValueError, 'DEEP_EXCEEDS_LOOPING'):
            L.roles(L.default_spec(self.anchor, deepHistoryTenants=9), 10)
        self.assertEqual(h.rows_per_tenant(self.spec), {'entries': 576, 'devicestatus': 576, 'treatments': 324, 'profile': 3})

    # ------------------------------------------------------------- seed path
    def test_seed_readback_restore_and_refusals(self):
        spec = self.spec = L.default_spec(self.anchor, deepHistoryTenants=1, deepHistoryDays=35)
        receipt = self.fixture()
        roles = L.roles(spec, 10)
        self.assertEqual(collections.Counter(roles), {'looping': 7, 'cgm-only': 2, 'deep': 1})
        for i, tenant in enumerate(self.tenants_sorted()):
            want = L.rows_per_tenant(spec, roles[i])
            got = self.store[tenant['id']]
            self.assertEqual({k: len(got.get('/api/v1/' + k, [])) for k in want}, want)
        deep = receipt['roles']['deep']
        self.assertEqual((deep['entries']['rows'], deep['devicestatus']['rows'], deep['treatments']['rows'], deep['profile']['rows']),
                         (35 * 288, 35 * 288, 35 * 162, 4))
        self.assertEqual(receipt['seededBatches'], 10)
        # every request stays under the edge's 2 MB body limit and at most one day of rows
        self.assertLess(max(c[3] for c in self.calls), 2 * 1024 * 1024)
        self.assertLessEqual(max(c[2] for c in self.calls), 288)
        restored = self.fixture(verify_only=True, tenants=self.tenants[::-1])
        self.assertEqual((restored['logicalSha256'], restored['seededBatches']), (receipt['logicalSha256'], 0))
        self.assertNotIn('local /', json.dumps(receipt))
        healthy = copy.deepcopy(self.store)
        key = self.tenants_sorted()[roles.index('looping')]['id']
        for mutate in (lambda: self.store[key]['/api/v1/devicestatus'].pop(),
                       lambda: self.store[key]['/api/v1/treatments'][0].update(carbs=1),
                       lambda: self.store[key]['/api/v1/treatments'][3].update(insulin=0.35),
                       lambda: self.store[key]['/api/v1/entries'][5].update(sgv=999),
                       lambda: self.store[key].pop('/api/v1/profile'),
                       lambda: self.store.pop(key)):
            mutate()
            with self.assertRaisesRegex(ValueError, 'M7_HISTORY_'):
                self.fixture(verify_only=True)
            self.store = copy.deepcopy(healthy)
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_CLINICAL_WINDOW'):
            self.fixture(now=lambda: (self.anchor + h.MAX_STALE_4W_MS) / 1000, verify_only=True)

    def test_request_rate_is_derived_from_the_generator(self):
        rate = L.request_rate(self.spec, 1000)
        self.assertEqual((rate['looping'], rate['cgmOnly']), (800, 200))
        self.assertAlmostEqual(rate['writesPerSecond']['w_sgv'], 1000 / 300, places=2)
        self.assertAlmostEqual(rate['writesPerSecond']['w_devicestatus'], 800 / 300, places=2)
        cycles = rate['treatmentPostCyclesPerDay']['looping']
        self.assertTrue(144 <= cycles <= 162)
        # all CGM-only: no devicestatus, and fewer treatment posts
        none = L.request_rate(L.default_spec(self.anchor, cgmOnlyPercent=100), 1000)
        self.assertEqual(none['writesPerSecond']['w_devicestatus'], 0)
        self.assertLess(none['writes'], rate['writes'])


def h_ms(iso):
    from datetime import datetime
    return int(datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() * 1000)


if __name__ == '__main__':
    unittest.main()
