"""All-input 120 s coverage verdict (coverage_verdict.py): green case and red controls. Synthetic figures only."""
import copy
import json
import unittest

import coverage_verdict as cv
import progress_sql

A, B, C = ('11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222',
           '33333333-3333-4333-8333-333333333333')
READ = 1795300000000
BOOKEND_S = READ / 1000


def series(slice_='0', start=(10, 10, 10, 0), end=(50, 50, 50, 0), resets=0, last=BOOKEND_S + 15):
    name = json.dumps({'pod': 'evaluator-' + slice_, 'role': 'evaluator', 'slice': slice_}, sort_keys=True)
    fields = ('count', 'le120', 'le90', 'unobserved')
    return name, {'start': dict(zip(fields, start)), 'end': dict(zip(fields, end)), 'resets': resets, 'lastSampleS': last}


def green():
    m1 = {'bookendS': BOOKEND_S, 'series': dict([series('0'), series('1')])}
    end = {'readAtMs': READ, 'tenants': {t: {'pending': False, 'pendingAt': None} for t in (A, B, C)}}
    writes = {'accepted': 90, 'stored': 90, 'uncertain': 0, 'storedByTenant': {A: 30, B: 30, C: 30}}
    return m1, end, writes


class Verdict(unittest.TestCase):
    def run_assess(self, m1, end, writes, **kw):
        return cv.assess(m1, end, writes, **{'clock_bound_ms': 50, 'slices': 2, **kw})

    def test_green_passes(self):
        value = self.run_assess(*green())
        self.assertEqual(value['verdict'], 'PASS', value)
        self.assertEqual(value['figures']['m1Observations'], 80)

    def test_red_injected_completion_over_deadline_fails(self):
        m1, end, writes = green()
        name, s = series('1', end=(51, 50, 50, 0))
        m1['series'][name] = s
        value = self.run_assess(m1, end, writes)
        self.assertEqual(value['verdict'], 'FAIL')
        self.assertIn('M1_OVER_DEADLINE', value['fail'])
        self.assertEqual(value['figures']['m1Above120s'], 1)

    def test_over_deadline_before_the_run_is_not_counted(self):
        m1, end, writes = green()
        name, s = series('1', start=(11, 10, 10, 0), end=(51, 50, 50, 0))
        m1['series'][name] = s
        self.assertEqual(self.run_assess(m1, end, writes)['verdict'], 'PASS')

    def test_red_end_pending_older_than_deadline_fails(self):
        m1, end, writes = green()
        end['tenants'][C] = {'pending': True, 'pendingAt': READ - 121000}
        value = self.run_assess(m1, end, writes)
        self.assertEqual(value['verdict'], 'FAIL')
        self.assertIn('END_PENDING_OVER_DEADLINE', value['fail'])

    def test_young_end_pending_is_censored_unless_the_drain_covered_the_deadline(self):
        m1, end, writes = green()
        end['tenants'][C] = {'pending': True, 'pendingAt': READ - 30000}
        value = self.run_assess(m1, end, writes, last_accepted_ms=READ - 60000)
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertIn('CENSORED_PENDING', value['unmeasured'])
        value = self.run_assess(m1, end, writes, last_accepted_ms=READ - 125000)
        self.assertEqual(value['verdict'], 'FAIL')
        self.assertIn('END_PENDING_AFTER_FULL_DRAIN', value['fail'])

    def test_red_dropped_observation_paths_never_pass(self):
        # (a) a completion whose commit outcome is unknown was counted, not observed
        m1, end, writes = green()
        name, s = series('1', end=(50, 50, 50, 1))
        m1['series'][name] = s
        self.assertIn('COMPLETION_UNOBSERVED', self.run_assess(m1, end, writes)['unmeasured'])
        # (b) a path that clears the mark without observing: fewer observations than cleared tenants
        m1, end, writes = green()
        m1['series'] = dict([series('0', end=(11, 11, 11, 0)), series('1', end=(11, 11, 11, 0))])
        value = self.run_assess(m1, end, writes)
        self.assertNotEqual(value['verdict'], 'PASS')
        self.assertIn('M1_OBSERVATIONS_BELOW_COVERED_TENANTS', value['unmeasured'])
        # (c) one slice exports nothing
        m1, end, writes = green()
        m1['series'] = dict([series('0')])
        self.assertIn('M1_SLICE_MISSING', self.run_assess(m1, end, writes)['unmeasured'])
        # (d) no M1 export at all, or the counter missing on an old image
        m1, end, writes = green()
        self.assertIn('M1_NOT_EXPORTED', self.run_assess({'series': {}}, end, writes)['unmeasured'])
        name, s = series('1'); s['end']['unobserved'] = None; m1['series'][name] = s
        self.assertIn('UNOBSERVED_COUNTER_NOT_EXPORTED', self.run_assess(m1, end, writes)['unmeasured'])

    def test_lost_observations_never_pass(self):
        for change, code in ((dict(resets=1), 'M1_SERIES_RESET'), (dict(last=BOOKEND_S - 1), 'M1_LAST_SCRAPE_BEFORE_END_READ'),
                             (dict(start=(None, None, None, None)), 'M1_SERIES_STARTED_DURING_RUN')):
            m1, end, writes = green()
            name, s = series('1', **change)
            m1['series'][name] = s
            value = self.run_assess(m1, end, writes)
            self.assertEqual(value['verdict'], 'UNMEASURED', code)
            self.assertIn(code, value['unmeasured'])

    def test_accepted_must_equal_stored(self):
        for change in ({'stored': 89}, {'uncertain': 1}):
            m1, end, writes = green()
            writes.update(change)
            self.assertIn('ACCEPTED_NOT_STORED', self.run_assess(m1, end, writes)['unmeasured'])

    def test_clock_margin_near_the_deadline(self):
        m1, end, writes = green()
        name, s = series('1', end=(51, 51, 50, 0))
        m1['series'][name] = s
        self.assertIn('CLOCK_BOUND_UNMEASURED_NEAR_DEADLINE', self.run_assess(m1, end, writes, clock_bound_ms=None)['unmeasured'])
        self.assertIn('CLOCK_MARGIN', self.run_assess(m1, end, writes, clock_bound_ms=50)['unmeasured'])
        self.assertEqual(self.run_assess(m1, end, writes, clock_bound_ms=0)['verdict'], 'PASS')

    def test_progress_bookend_must_pass(self):
        self.assertIn('PROGRESS_BOOKEND_FAIL', self.run_assess(*green(), progress_verdict='FAIL')['unmeasured'])


class Inputs(unittest.TestCase):
    def test_m1_from_prometheus_reads_start_end_resets_and_last_sample(self):
        labels = {'pod': 'evaluator-0', 'role': 'evaluator', 'slice': '0'}
        calls = []

        def query(expr, at):
            calls.append((expr, at))
            value = {'count': 10, 'le120': 10, 'le90': 9, 'unobserved': 0} if at == 100 else {'count': 40, 'le120': 39, 'le90': 30, 'unobserved': 0}
            if expr.startswith('resets('):
                return [{'labels': labels, 'value': 0}]
            if expr.startswith('timestamp('):
                return [{'labels': labels, 'value': 500}]
            key = 'le120' if 'le="120"' in expr else 'le90' if 'le="90"' in expr else 'unobserved' if 'unobserved' in expr else 'count'
            return [{'labels': {**labels, **({'le': '120'} if key == 'le120' else {})}, 'value': value[key]}]
        m1 = cv.m1_from_prometheus(query, 100, 400, 390)
        (only,) = m1['series'].values()
        self.assertEqual(only['start']['count'], 10)
        self.assertEqual(only['end']['le120'], 39)
        self.assertEqual(only['lastSampleS'], 500)
        self.assertTrue(any(expr == 'resets(' + cv.COUNT + '[301s])' for expr, _ in calls))
        value = cv.assess(m1, {'readAtMs': 390000, 'tenants': {A: {'pending': False}}},
                          {'accepted': 5, 'stored': 5, 'uncertain': 0, 'storedByTenant': {A: 5}}, clock_bound_ms=0, slices=1)
        self.assertEqual(value['verdict'], 'FAIL')  # one observation above 120 s during the run

    def test_end_read_from_the_progress_bookend(self):
        raw = json.dumps({'identity': ['1', 1, 'synthetic_test'], 'readAtMs': str(READ), 'tenants': {
            A: ['1', '5', '5', '1', True, False, None], B: ['1', '5', '6', '1', True, True, str(READ - 200000)]}})
        bookend = progress_sql.decode(raw, [A, B])
        self.assertEqual(bookend['readAtMs'], READ)
        end = cv.end_from_bookend(bookend, [A, B])
        self.assertEqual(end['tenants'][B], {'pending': True, 'pendingAt': READ - 200000})
        m1, _, writes = green()
        writes['storedByTenant'] = {A: 1, B: 1}
        self.assertIn('END_PENDING_OVER_DEADLINE', cv.assess(m1, end, writes, clock_bound_ms=0, slices=2)['fail'])

    def test_a_bookend_without_the_pending_mark_reads_unmeasured(self):
        raw = json.dumps({'identity': ['1', 1, 'synthetic_test'], 'tenants': {A: ['1', '5', '6', '1', True, True]}})
        end = cv.end_from_bookend(progress_sql.decode(raw, [A]), [A])
        m1, _, writes = green()
        value = cv.assess(m1, end, {**writes, 'storedByTenant': {A: 1}}, clock_bound_ms=0, slices=2)
        self.assertEqual(value['verdict'], 'UNMEASURED')
        self.assertIn('END_READ_MISSING', value['unmeasured'])

    def test_the_bookend_query_selects_the_mark_and_the_read_time(self):
        completion = {'kind': 'evaluator-work-v2', 'checkpoint': 'nsdemo_eval_checkpoint', 'consumer': 'evaluator-compose-demo-completed',
                      'writerDriven': {'lifecycle': 'nsdemo_control'}}
        text = progress_sql.query(completion)
        self.assertIn('o.work_pending_at::text', text)
        self.assertIn("'readAtMs', floor(extract(epoch FROM clock_timestamp()) * 1000)", text)


class Case(unittest.TestCase):
    """from_case joins the retained load-stage records; a fake local Prometheus stands in for the snapshot."""

    def write_case(self, d, above=0, pending_age=None):
        import pathlib
        load = pathlib.Path(d)
        tenants = {A: {'pending': False, 'pendingAt': None}, B: {'pending': pending_age is not None,
                   'pendingAt': None if pending_age is None else READ - pending_age}}
        (load/'progress-after.json').write_text(json.dumps({'source': 'sql-completed-v1', 'readAtMs': READ, 'tenants': tenants}))
        (load/'stored-counts.json').write_text(json.dumps({A: {'entries': 3, 'devicestatus': 3}, B: {'entries': 2, 'probe': 1}}))
        (load/'k6-summary.json').write_text(json.dumps({'metrics': {'writes_ok': {'count': 8}, 'writes_uncertain': {'count': 0}}}))
        (load/'window.json').write_text(json.dumps({'loadStartedAt': BOOKEND_S - 1800}))
        (load/'metrics-snapshot.json').write_text(json.dumps({'verdict': 'OBSERVED', 'file': 'metrics-tsdb.tar', 'observedAt': BOOKEND_S + 60}))
        labels = {'pod': 'evaluator-0', 'role': 'evaluator', 'slice': '0'}

        class Local:
            def __init__(self, archive):
                self.closed = False

            def query(self, expr, at):
                late = at > BOOKEND_S - 1800
                if expr.startswith('resets('):
                    return [{'labels': labels, 'value': 0}]
                if expr.startswith('timestamp('):
                    return [{'labels': labels, 'value': BOOKEND_S + 30}]
                count = 20 if late else 0
                value = count - (above if late else 0) if 'le="120"' in expr or 'le="90"' in expr else 0 if 'unobserved' in expr else count
                return [{'labels': labels, 'value': value}]

            def close(self):
                self.closed = True
        return load, Local

    def test_green_case_passes_and_red_cases_do_not(self):
        import tempfile
        for above, age, verdict in ((0, None, 'PASS'), (1, None, 'FAIL'), (0, 130000, 'FAIL'), (0, 20000, 'UNMEASURED')):
            with tempfile.TemporaryDirectory() as d:
                load, local = self.write_case(d, above, age)
                value = cv.from_case(load, slices=1, clock_bound_ms=0, local=local)
                self.assertEqual(value['verdict'], verdict, (above, age, value))

    def test_early_stop_packet_is_accepted_explicitly(self):
        """No window.json and no progress-after.json (the run stopped on a harness bound): progress-stop.json is the end
        read and the window comes from the scheduling trace. The result says both; a trace-less packet stays UNMEASURED."""
        import gzip, tempfile
        with tempfile.TemporaryDirectory() as d:
            load, local = self.write_case(d)
            start_ms = int((BOOKEND_S - 1800) * 1000)
            (load/'progress-after.json').rename(load/'progress-stop.json')
            (load/'window.json').unlink()
            with gzip.open(load/'k6-scheduling.csv.gz', 'wt') as f:
                f.write('metric_name,timestamp,metric_value,scenario\n')
                f.write('m7_driver_started,%d,1.0,w\n' % start_ms)
                f.write('iterations,%d,1.0,w\n' % (start_ms + 1800000))
            value = cv.from_case(load, slices=1, clock_bound_ms=0, local=local)
            self.assertEqual(value['verdict'], 'PASS', value)
            self.assertEqual(value['inputs']['endRead'], 'progress-stop.json')
            self.assertTrue(value['inputs']['earlyStop'])
            self.assertIn('trace-derived', value['inputs']['windowBasis'])
            self.assertEqual(value['inputs']['loadStartedAt'], start_ms / 1000)
            (load/'k6-scheduling.csv.gz').unlink()
            value = cv.from_case(load, slices=1, clock_bound_ms=0, local=local)
            self.assertEqual(value['storageRefusals']['verdict'], 'UNMEASURED')

    def test_missing_snapshot_reads_unmeasured(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            load, local = self.write_case(d)
            (load/'metrics-snapshot.json').unlink()
            value = cv.from_case(load, slices=1, clock_bound_ms=0, local=local)
            self.assertEqual(value['verdict'], 'UNMEASURED')
            self.assertIn('M1_NOT_EXPORTED', value['unmeasured'])



class Refusals(unittest.TestCase):
    """api 503 storage refusals per code from the retained snapshot (core nightscout_storage_refusals_total)."""

    START, END = BOOKEND_S - 1800, BOOKEND_S + 60

    def labels(self, pod, code, phase, route='entries_write'):
        return {'__name__': cv.REFUSALS, 'pod': pod, 'role': 'api', 'code': code, 'phase': phase, 'route_class': route}

    def query(self, start_rows, end_rows, resets=(), grown=()):
        calls = []

        def query(expr, at):
            calls.append((expr, at))
            if expr.startswith('resets('):
                return [{'labels': {k: v for k, v in l.items() if k != '__name__'}, 'value': n} for l, n in resets]
            if expr.startswith('increase('):
                return [{'labels': {k: v for k, v in l.items() if k != '__name__'}, 'value': n} for l, n in grown]
            if expr.startswith('last_over_time('):
                return [{'labels': {k: v for k, v in l.items() if k != '__name__'}, 'value': n} for l, n in end_rows]
            return [{'labels': l, 'value': n} for l, n in start_rows]
        return query, calls

    def test_counts_per_code_phase_and_route_class_over_the_load_window(self):
        clock = self.labels('api-a', 'STORAGE_TIMEOUT', 'clock')
        statement = self.labels('api-a', 'STORAGE_TIMEOUT', 'statement')
        busy = self.labels('api-b', 'STORAGE_BUSY', 'checkout', 'treatments_write')
        late = self.labels('api-c', 'STORAGE_BUSY', 'checkout')  # a Pod that started during the load
        idle = self.labels('api-a', 'STORAGE_UNAVAILABLE', 'none', 'other_write')
        query, calls = self.query([(clock, 3), (statement, 0), (busy, 1), (idle, 0)],
                                  [(clock, 10), (statement, 2), (busy, 4), (late, 5), (idle, 0)])
        value = cv.refusals_from_prometheus(query, self.START, self.END)
        self.assertEqual(value['verdict'], 'OBSERVED')
        self.assertEqual(value['byCode'], {'STORAGE_BUSY': 8, 'STORAGE_TIMEOUT': 9, 'STORAGE_UNAVAILABLE': 0})
        self.assertEqual(value['byCodePhase'], {'STORAGE_BUSY/checkout': 8, 'STORAGE_TIMEOUT/clock': 7,
                                                'STORAGE_TIMEOUT/statement': 2, 'STORAGE_UNAVAILABLE/none': 0})
        self.assertEqual(value['byCodeRouteClass'], {'STORAGE_BUSY/entries_write': 5, 'STORAGE_BUSY/treatments_write': 3,
                                                     'STORAGE_TIMEOUT/entries_write': 9, 'STORAGE_UNAVAILABLE/other_write': 0})
        self.assertEqual(value['resetSeries'], 0)
        self.assertEqual({at for _, at in calls if _.startswith(cv.REFUSALS)}, {self.START})
        self.assertTrue(all('[1861s]' in expr for expr, _ in calls if not expr.startswith(cv.REFUSALS)))

    def test_a_series_that_reset_uses_increase_and_is_flagged(self):
        clock = self.labels('api-a', 'STORAGE_TIMEOUT', 'clock')
        query, _ = self.query([(clock, 30)], [(clock, 2)], resets=[(clock, 1)], grown=[(clock, 6.5)])
        value = cv.refusals_from_prometheus(query, self.START, self.END)
        self.assertEqual((value['byCode']['STORAGE_TIMEOUT'], value['resetSeries']), (6.5, 1))

    def test_no_series_reads_no_instrument_never_zero(self):
        query, _ = self.query([], [])
        value = cv.refusals_from_prometheus(query, self.START, self.END)
        self.assertEqual(value['verdict'], 'NO-INSTRUMENT')
        self.assertNotIn('byCode', value)

    def test_from_case_reports_refusals_beside_the_verdict_and_unmeasured_without_a_snapshot(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            load, local = Case().write_case(d)
            value = cv.from_case(load, slices=1, clock_bound_ms=0, local=local)
            self.assertEqual(value['verdict'], 'PASS')
            self.assertIn(value['storageRefusals']['verdict'], ('OBSERVED', 'NO-INSTRUMENT'))
            (load/'metrics-snapshot.json').unlink()
            value = cv.from_case(load, slices=1, clock_bound_ms=0, local=local)
            self.assertEqual(value['storageRefusals']['verdict'], 'UNMEASURED')


if __name__ == '__main__':
    unittest.main()
