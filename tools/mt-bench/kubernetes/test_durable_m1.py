"""Durable M1 from the work row (lane m1-durable): the before-load and after-drain SQL bookends feed R2's all-input
120 s verdict. Green case and red controls; synthetic tenants and figures only."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import coverage_verdict as cv
import progress_sql

A, B, C = ('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222',
           '33333333-3333-4333-8333-333333333333')
READ = 1795300000000
BOUNDS = [250, 500, 1000, 2000, 5000, 10000, 30000, 60000, 120000, None]
M7 = Path(__file__).resolve().parents[1] / 'm7-joined'


def lag(count=0, total=0, peak=0, buckets=None, over=0, negative=0):
    return {'count': count, 'sumMs': total, 'maxMs': peak, 'buckets': buckets or [0] * 10, 'over120s': over, 'negative': negative}


def seeded():
    # A restored fixture: the seed already counted observations before the run.
    return {t: lag(5, 2000, 900, [3, 1, 1, 0, 0, 0, 0, 0, 0, 0]) for t in (A, B, C)}


def run_rows(extra=None):
    """After drain: each tenant gained observations in the window; EXTRA overrides per tenant."""
    rows = {A: lag(15, 2000 + 4000, 900, [3, 9, 3, 0, 0, 0, 0, 0, 0, 0]),
            B: lag(9, 2000 + 3000, 1500, [3, 3, 1, 2, 0, 0, 0, 0, 0, 0]),
            C: lag(7, 2000 + 600, 900, [4, 2, 1, 0, 0, 0, 0, 0, 0, 0])}
    rows.update(extra or {})
    return rows


def bookend(lags, pending=None):
    tenants = {t: {'generation': 2, 'completed': 10, 'observed': 10, 'restoreGeneration': 2, 'stateOK': True,
                   'pending': bool(pending and t in pending), 'pendingAt': (pending or {}).get(t), 'lag': lags.get(t)}
               for t in (A, B, C)}
    for t, row in tenants.items():
        if row['lag'] is None:
            del row['lag']
    return {'source': 'sql-completed-v1', 'identity': ['1', 1, 'synthetic_test'], 'readAtMs': READ, 'tenants': tenants,
            'queries': 1, 'bytes': 1, 'wallSeconds': 0, 'durableLagBoundsMs': BOUNDS}


WRITES = {'accepted': 90, 'stored': 90, 'uncertain': 0, 'storedByTenant': {A: 30, B: 30, C: 30}}


def verdict(before, after, writes=WRITES, slices=2, **kw):
    ids = [A, B, C]
    durable = cv.m1_from_durable(before, after, ids, BOUNDS, slices)
    end = cv.end_from_bookend(after, ids)
    return cv.assess(None, end, writes, durable=durable, slices=slices, **{'clock_bound_ms': 50, **kw})


class DurableSource(unittest.TestCase):
    def test_green_differences_the_seed_away_and_reports_percentiles(self):
        value = verdict(bookend(seeded()), bookend(run_rows()))
        self.assertEqual(value['verdict'], 'PASS', value)
        self.assertEqual(value['figures']['m1Source'], 'durable-row')
        overall = value['figures']['durable']['overall']
        self.assertEqual(overall['count'], 10 + 4 + 2)
        self.assertEqual(overall['buckets'], [1, 11, 2, 2, 0, 0, 0, 0, 0, 0])
        self.assertEqual((overall['p50MsAtMost'], overall['p95MsAtMost'], overall['maxMsAtMost']), (500, 2000, 2000))
        self.assertEqual(sum(s['count'] for s in value['figures']['durable']['slices'].values()), 16)
        self.assertEqual(value['figures']['m1Observations'], 16)

    def test_red_an_observation_over_120s_fails(self):
        rows = run_rows({C: lag(8, 2600 + 130000, 130000, [4, 2, 1, 0, 0, 0, 0, 0, 0, 1], over=1)})
        value = verdict(bookend(seeded()), bookend(rows))
        self.assertEqual(value['verdict'], 'FAIL', value)
        self.assertIn('M1_OVER_DEADLINE', value['fail'])
        self.assertIsNone(value['figures']['durable']['overall']['maxMsAtMost'], '+inf bucket has no finite bound')

    def test_red_an_over_120s_observation_from_the_seed_is_not_counted(self):
        seed = seeded()
        seed[C] = lag(6, 2000 + 130000, 130000, [3, 1, 1, 0, 0, 0, 0, 0, 0, 1], over=1)
        rows = run_rows({C: lag(8, 2000 + 130000 + 600, 130000, [4, 2, 1, 0, 0, 0, 0, 0, 0, 1], over=1)})
        self.assertEqual(verdict(bookend(seed), bookend(rows))['verdict'], 'PASS')

    def test_red_missing_baseline_or_end_read_is_unmeasured_never_pass(self):
        value = verdict(None, bookend(run_rows()))
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertIn('DURABLE_LAG_BASELINE_MISSING', value['unmeasured'])
        # A baseline from an image without the counters (bookend rows without lag).
        value = verdict(bookend({}), bookend(run_rows()))
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertIn('DURABLE_LAG_BASELINE_MISSING', value['unmeasured'])
        value = verdict(bookend(seeded()), None)
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertIn('DURABLE_LAG_END_MISSING', value['unmeasured'])

    def test_red_a_tenant_absent_from_the_end_read_is_unmeasured(self):
        after = bookend(run_rows())
        del after['tenants'][B]
        value = verdict(bookend(seeded()), after)
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertIn('DURABLE_LAG_TENANT_MISSING', value['unmeasured'])
        after = bookend(run_rows())
        del after['tenants'][B]['lag']
        self.assertIn('DURABLE_LAG_TENANT_MISSING', verdict(bookend(seeded()), after)['unmeasured'])

    def test_red_a_reset_row_or_inconsistent_counters_are_unmeasured(self):
        value = verdict(bookend(seeded()), bookend(run_rows({A: lag(1, 100, 100, [1] + [0] * 9)})))
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertIn('DURABLE_LAG_RESET', value['unmeasured'])
        value = verdict(bookend(seeded()), bookend(run_rows({A: lag(16, 6000, 900, [3, 9, 3, 0, 0, 0, 0, 0, 0, 0])})))
        self.assertIn('DURABLE_LAG_INCONSISTENT', value['unmeasured'])
        after = bookend(run_rows())
        after['durableLagBoundsMs'] = [100] + BOUNDS[1:]
        self.assertIn('DURABLE_LAG_BOUNDS_CHANGED', cv.m1_from_durable(bookend(seeded()), after, [A, B, C],
                                                                        after['durableLagBoundsMs'])['unmeasured'])

    def test_red_a_tenant_cleared_after_run_writes_without_an_observation_is_unmeasured(self):
        value = verdict(bookend(seeded()), bookend(run_rows({C: seeded()[C]})))
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertIn('M1_TENANT_CLEARED_WITHOUT_OBSERVATION', value['unmeasured'])

    def test_end_pending_bookend_is_still_applied(self):
        value = verdict(bookend(seeded()), bookend(run_rows(), pending={C: READ - 121000}))
        self.assertEqual(value['verdict'], 'FAIL')
        self.assertIn('END_PENDING_OVER_DEADLINE', value['fail'])

    def test_near_deadline_band_needs_a_clock_bound(self):
        rows = run_rows({C: lag(8, 2600 + 90000, 90000, [4, 2, 1, 0, 0, 0, 0, 0, 1, 0])})
        value = verdict(bookend(seeded()), bookend(rows), clock_bound_ms=None)
        self.assertIn('CLOCK_BOUND_UNMEASURED_NEAR_DEADLINE', value['unmeasured'])
        self.assertEqual(value['figures']['m1NearDeadlineBand'], '60-120 s (durable buckets)')

    def test_prometheus_is_a_cross_check_not_a_gate(self):
        ids = [A, B, C]
        durable = cv.m1_from_durable(bookend(seeded()), bookend(run_rows()), ids, BOUNDS, 1)
        value = cv.assess({'series': {}}, cv.end_from_bookend(bookend(run_rows()), ids), WRITES, clock_bound_ms=50, slices=1,
                          durable=durable)
        self.assertEqual(value['verdict'], 'PASS', value)
        self.assertEqual(value['figures']['crossCheck']['prometheusUnmeasured'], ['M1_NOT_EXPORTED', 'M1_SLICE_MISSING'])

    def test_slice_of_matches_the_core_rule(self):
        # core lib/pool-membership/slice.js bucket(): sha256(tenant) first 8 bytes, unsigned, mod K.
        script = ("const {createHash}=require('node:crypto');const t=process.argv[1];"
                  "console.log(Number(createHash('sha256').update(t,'utf8').digest().readBigUInt64BE(0)%3n))")
        for tenant in (A, B, C):
            expected = int(subprocess.check_output(['node', '-e', script, tenant], timeout=10))
            self.assertEqual(cv.slice_of(tenant, 3), expected)


class Bookend(unittest.TestCase):
    COMPLETION = {'kind': 'evaluator-work-v2', 'checkpoint': 'nsdemo_eval_checkpoint', 'consumer': 'evaluator-compose-demo-completed',
                  'writerDriven': {'lifecycle': 'nsdemo_control'}}

    def test_query_reads_the_counters_only_on_an_image_that_has_them(self):
        self.assertNotIn('lag_count', progress_sql.query(self.COMPLETION))
        text = progress_sql.query({**self.COMPLETION, 'durableLag': {'boundsMs': BOUNDS}})
        for column in ('o.lag_count::text', 'o.lag_sum_ms::text', 'o.lag_max_ms::text', 'o.lag_buckets::text[]',
                       'o.lag_over_120s::text', 'o.lag_negative::text'):
            self.assertIn(column, text)
        with self.assertRaises(Exception):
            progress_sql.query({**self.COMPLETION, 'durableLag': {'boundsMs': [250, 120]}})

    def test_decode_reads_the_counters_and_old_rows(self):
        row = ['2', '10', '10', '2', True, False, None, '3', '700', '400', ['1', '2', '0', '0', '0', '0', '0', '0', '0', '0'], '0', '0']
        value = progress_sql.decode(json.dumps({'identity': ['1'], 'readAtMs': str(READ), 'tenants': {A: row}}), [A])
        self.assertEqual(value['tenants'][A]['lag'], lag(3, 700, 400, [1, 2] + [0] * 8))
        old = progress_sql.decode(json.dumps({'identity': ['1'], 'tenants': {A: row[:7]}}), [A])
        self.assertNotIn('lag', old['tenants'][A])
        bad = progress_sql.decode(json.dumps({'identity': ['1'], 'tenants': {A: row[:10] + [None] + row[11:]}}), [A])
        self.assertIsNone(bad['tenants'][A]['lag'])

    def test_from_case_uses_both_bookends_and_reads_a_generation_change_unmeasured(self):
        with tempfile.TemporaryDirectory() as d:
            load = Path(d)
            (load/'stored-counts.json').write_text(json.dumps({t: {'entries': 30} for t in (A, B, C)}))
            (load/'k6-summary.json').write_text(json.dumps({'metrics': {'writes_ok': {'count': 90}, 'writes_uncertain': {'count': 0}}}))
            (load/'progress-before.json').write_text(json.dumps(bookend(seeded())))
            (load/'progress-after.json').write_text(json.dumps(bookend(run_rows())))
            value = cv.from_case(load, slices=2, clock_bound_ms=50)
            self.assertEqual(value['verdict'], 'PASS', value)
            after = bookend(run_rows())
            after['tenants'][A]['generation'] = 3
            (load/'progress-after.json').write_text(json.dumps(after))
            value = cv.from_case(load, slices=2, clock_bound_ms=50)
            self.assertEqual(value['verdict'], 'UNMEASURED')
            self.assertIn('PROGRESS_BOOKEND_FAIL_K8S_EVALUATOR_PROGRESS_RESET', value['unmeasured'])


class Observer(unittest.TestCase):
    def test_polling_observer_is_off_by_default_on_a_durable_image_and_kept_as_a_switch(self):
        import execute
        durable = {'completion': {'durableLag': {'boundsMs': BOUNDS}}}
        self.assertEqual(execute.latency_observation({}, durable), 'offline-v1')
        self.assertEqual(execute.latency_observation({'latencyObservation': 'polling-sql-v1'}, durable), 'polling-sql-v1')
        self.assertEqual(execute.latency_observation({}, {'completion': {}}), 'polling-sql-v1', 'older images keep the default')


class ImageReport(unittest.TestCase):
    def test_settings_context_reports_the_bounds_only_when_the_image_has_them(self):
        script = (M7 / 'settings-context.cjs').read_text()
        probe = script.split('function projection')[0] + "console.log(JSON.stringify(durableLag(process.argv[1])));"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            run = lambda: json.loads(subprocess.check_output(['node', '-e', probe, str(root)], timeout=10))
            self.assertEqual(run(), {})
            (root/'lib/pgstream').mkdir(parents=True)
            (root/'lib/pgstream/completion-lag.js').write_text(
                "module.exports={BOUNDS_MS:[250,500,1000,2000,5000,10000,30000,60000,120000,Infinity]};")
            self.assertEqual(run(), {'durableLag': {'boundsMs': BOUNDS}})


if __name__ == '__main__':
    unittest.main()
