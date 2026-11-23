"""Fixture realism (lane fixture-realism-20261123): per-tenant phase offsets, deeper history, viewer mix.

Each property has a control: the same measurement taken with the property removed goes red (here: asserted red).
"""
import collections
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import unittest
from unittest import mock

import fixture_catalog
import looping_history as v1
import looping_history_v2 as g
import populated_history as h
import viewer_plan

ANCHOR = 1_800_000_000_000 // h.STEP_MS * h.STEP_MS
# seed_requests digests of the DEFAULT v2 spec (deepHistoryTenants=2, 40 tenants) taken from the code before this lane:
# the default fixture must not change (same rows, same fixture key).
DEFAULT_DIGESTS = {0: '877701b04446aa15', 1: '46cac3ac41489a4b', 2: 'b01d59d890190233', 3: '0cf02139d1e808cd',
                   7: '2d6ea521a4967509', 11: 'fcf0d59aced40ead', 19: '77ea9c29f892c0da', 33: '5307bb5ccb685c45'}


def due_instants(spec, n):
    """The instant each tenant's next reading is due: its newest stored SGV plus one step."""
    return [v1.Tenant(spec, i, 'looping').stamp(v1.Tenant(spec, i, 'looping').n - 1) + h.STEP_MS for i in range(n)]


class DefaultUnchanged(unittest.TestCase):
    def test_default_rows_are_byte_identical_to_before(self):
        spec = g.default_spec(ANCHOR, deepHistoryTenants=2)
        make = g.tenant_factory(spec, 40)
        for i, want in DEFAULT_DIGESTS.items():
            got = hashlib.sha256(json.dumps(g.seed_requests(make(i)), sort_keys=True).encode()).hexdigest()[:16]
            self.assertEqual(got, want, i)

    def test_default_spec_has_no_optional_keys_and_a_distinct_key_per_option(self):
        base = g.default_spec(ANCHOR)
        self.assertFalse(set(g.OPTIONAL_KEYS) & set(base))
        keys = {fixture_catalog.digest(dict(spec)) for spec in
                [base] + [g.default_spec(ANCHOR, **p) for p in g.PRESETS.values()]}
        self.assertEqual(len(keys), 1 + len(g.PRESETS))


class PhaseOffsets(unittest.TestCase):
    def test_tenants_do_not_share_a_due_instant(self):
        n = 400
        shared = due_instants(g.default_spec(ANCHOR), n)
        spread = due_instants(g.default_spec(ANCHOR, phaseSpreadMs=299_000), n)
        self.assertEqual(len(set(shared)), 1)                         # control: the old fixture, one instant
        self.assertGreater(len(set(spread)), 0.95 * n)
        self.assertLessEqual(max(collections.Counter(spread).values()), 3)
        # every tenant's due instant stays within one grid step of the shared one, so cold-window rows stay inside it
        self.assertTrue(all(0 <= shared[0] - d < 299_000 for d in spread))

    def test_the_control_goes_red_when_the_phase_is_removed(self):
        spec = g.default_spec(ANCHOR, phaseSpreadMs=299_000)
        with mock.patch.object(v1, 'phase_ms', lambda spec, ordinal: 0):
            removed = due_instants(spec, 400)
        self.assertEqual(len(set(removed)), 1)                        # the property fails: all share one instant

    def test_phase_is_deterministic_and_moves_timestamps_only(self):
        spec = g.default_spec(ANCHOR, phaseSpreadMs=299_000)
        a, b = v1.Tenant(spec, 5, 'looping'), v1.Tenant(spec, 5, 'looping')
        self.assertEqual(a.phase, b.phase)
        self.assertEqual(a.stamp(a.n - 1), ANCHOR - a.phase)
        plain = v1.Tenant(g.default_spec(ANCHOR), 5, 'looping')
        # same clock-slot choices: the treatments' cycle positions and kinds are identical
        self.assertEqual([(c, k) for c, k, *_ in a.treatments], [(c, k) for c, k, *_ in plain.treatments])
        self.assertEqual(g.rows_per_tenant(spec), g.rows_per_tenant(g.default_spec(ANCHOR)))
        ex = a.expected()
        self.assertEqual(ex['entries'], 576)
        self.assertEqual(len(g.entries(a)), ex['entries'])

    def test_every_row_stays_at_or_before_the_anchor(self):
        spec = g.default_spec(ANCHOR, phaseSpreadMs=299_000)
        for i in range(30):
            t = g.tenant_factory(spec, 30)(i)
            self.assertLessEqual(max(e['date'] for e in g.entries(t)), ANCHOR)

    def test_option_validation(self):
        for bad in (0, -1, 300_000, 1.5, True):
            with self.assertRaises(ValueError):
                g.validate(g.default_spec(ANCHOR, phaseSpreadMs=bad))
        with self.assertRaises(ValueError):
            g.validate(dict(g.default_spec(ANCHOR), bogus=1))


class Depth(unittest.TestCase):
    def test_historyDays_sets_every_collection(self):
        for days in (14, 30):
            spec = g.default_spec(ANCHOR, historyDays=days)
            for i in range(12):
                role = 'cgm-only' if i % 4 == 0 else 'looping'
                t = g.Tenant(spec, i, role, profile=True)
                want = g.rows_per_tenant(spec, role, t.kind if role == 'looping' else None)
                self.assertEqual(want['entries'], days * 288)
                self.assertEqual(len(g.entries(t)), want['entries'])
                self.assertEqual(len(g.devicestatus(t)), want['devicestatus'])
                self.assertEqual(len(g.treatments(t)), want['treatments'])
                self.assertEqual(len(g.profiles(t)), want['profile'])

    def test_control_depth_is_not_ignored(self):
        two, fourteen = g.default_spec(ANCHOR), g.default_spec(ANCHOR, historyDays=14)
        self.assertEqual(g.rows_per_tenant(two, 'cgm-only')['entries'], 576)
        self.assertEqual(g.rows_per_tenant(fourteen, 'cgm-only')['entries'], 14 * 288)   # red if the option is ignored
        self.assertNotEqual(fixture_catalog.digest(two), fixture_catalog.digest(fourteen))

    def test_deep_role_keeps_its_own_depth_and_expected_matches_documents(self):
        spec = g.default_spec(ANCHOR, historyDays=14, deepHistoryTenants=1, deepHistoryDays=20)
        make = g.tenant_factory(spec, 10)
        roles = g.roles(spec, 10)
        for i in range(10):
            t = make(i)
            self.assertEqual(t.days, 20 if roles[i] == 'deep' else 14)
            self.assertEqual(t.expected()['entries'], len(g.entries(t)))

    def test_range(self):
        for bad in (2, 61, 14.0, '14'):
            with self.assertRaises(ValueError):
                g.validate(g.default_spec(ANCHOR, historyDays=bad))
        g.validate(g.default_spec(ANCHOR, historyDays=60))
        with self.assertRaises(ValueError):    # anchor must precede the first row
            g.validate(g.default_spec(60 * 288 * h.STEP_MS - h.STEP_MS, historyDays=60))


class ViewerMix(unittest.TestCase):
    MIX = viewer_plan.MIX_PRESETS['followers-v1']

    def m(self, tenants, mix=None):
        setup = {} if mix is None else {'mix': mix}
        return {'tenants': tenants, 'cadence': {'socketsPerTenant': 2, 'viewerSetup': setup}}

    def roster(self, n):
        return [{'id': f't{i}'} for i in range(n)]

    def test_counts_follow_the_declared_shares_exactly(self):
        n = 1000
        counts = viewer_plan.mix_counts(self.MIX, n)
        self.assertEqual(collections.Counter(counts), {0: 100, 1: 200, 2: 400, 4: 200, 8: 100})
        self.assertEqual(viewer_plan.mix_counts(self.MIX, n), counts)
        self.assertEqual(viewer_plan.total(self.m(n, self.MIX)), sum(counts))
        self.assertEqual(list(viewer_plan.counts(self.m(n, self.MIX), self.roster(n)).values()), counts)

    def test_default_workload_unchanged_without_a_mix(self):
        n = 7
        self.assertEqual(viewer_plan.total(self.m(n)), 14)
        self.assertEqual(set(viewer_plan.counts(self.m(n), self.roster(n)).values()), {2})
        s = viewer_plan.setup({'viewerSetup': {}})
        self.assertNotIn('mix', s)

    def test_control_without_a_mix_the_distribution_is_uniform(self):
        flat = list(viewer_plan.counts(self.m(1000), self.roster(1000)).values())
        self.assertEqual(len(set(flat)), 1)                            # red for the mix test if the mix is dropped
        self.assertGreater(len(set(viewer_plan.mix_counts(self.MIX, 1000))), 1)

    def test_validation(self):
        for bad in ({'seed': 1, 'shares': [[1, 50]]}, {'seed': 1, 'shares': []}, {'seed': 1, 'shares': [[-1, 100]]},
                    {'seed': 'x', 'shares': [[1, 100]]}, {'shares': [[1, 100]]}, {'seed': 1, 'shares': [[1, 100]], 'x': 1}):
            with self.assertRaises(RuntimeError):
                viewer_plan.setup({'viewerSetup': {'mix': bad}})

    def js(self, mix, n):
        src = pathlib.Path(__file__).with_name('joined-probe.cjs').read_text()
        fn = re.search(r'function mixCounts\(.*?\n', src).group(0)
        node = shutil.which('node')
        out = subprocess.run([node, '-e', fn + f'console.log(JSON.stringify(mixCounts({json.dumps(mix)},{n})))'],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_probe_and_plan_assign_the_same_sockets(self):
        for n in (1, 7, 100, 1001):
            self.assertEqual(self.js(self.MIX, n), viewer_plan.mix_counts(self.MIX, n), n)
        # control: a different seed gives a different assignment, so agreement above is not vacuous
        self.assertNotEqual(self.js(dict(self.MIX, seed=1), 1001), viewer_plan.mix_counts(self.MIX, 1001))


if __name__ == '__main__':
    unittest.main()
