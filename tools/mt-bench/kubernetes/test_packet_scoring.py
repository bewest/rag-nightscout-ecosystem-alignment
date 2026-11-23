"""Offline packet scoring (packet_scoring.py): series born after the load start, the le="30.0" bucket, early-stop windows,
viewer M3 bands. A fake query stands in for the retained TSDB; synthetic figures only."""
import gzip
import json
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path

import packet_scoring as ps

START, END = 1000.0, 2800.0


class Fake:
    """Instant queries over {(name, frozenset(labels)): [(t, v)]} with Prometheus's semantics for the four forms used."""

    def __init__(self, series):
        self.series = series

    def pick(self, selector):
        name = re.match(r'[a-z_]+', selector)[0]
        want = dict(re.findall(r'(\w+)="([^"]*)"', selector))
        return [(dict(k[1]), v) for k, v in self.series.items() if k[0] == name and all(dict(k[1]).get(a) == b for a, b in want.items())]

    def query(self, expr, at):
        m = re.fullmatch(r'(last_over_time|resets|increase)\((.*)\[(\d+)s\]\)', expr)
        fn, sel, w = (m[1], m[2], int(m[3])) if m else (None, expr, 0)
        rows = []
        for labels, samples in self.pick(sel):
            if fn:
                inside = [v for t, v in samples if at - w <= t <= at]
            else:
                inside = [v for t, v in samples if t <= at][-1:]
            if not inside:
                continue
            if fn == 'resets':
                value = sum(1 for a, b in zip(inside, inside[1:]) if b < a)
            elif fn == 'increase':
                value = sum(b - a if b >= a else b for a, b in zip(inside, inside[1:]))   # the first sample is the origin, never counted
            else:
                value = inside[-1]
            rows.append({'labels': labels, 'value': value})
        return rows


def counter(pod, *samples, name='c', **extra):
    return (name, frozenset({'pod': pod, **extra}.items())), list(samples)


class Delta(unittest.TestCase):
    def test_a_series_born_after_the_start_counts_from_zero(self):
        # evaluator-1's first sample (consumer passes, refusals, 5xx) lands after the load started: 7 is real growth.
        fake = Fake(dict([counter('e0', (500, 3), (1500, 10), (2800, 20)), counter('e1', (1500, 7), (2800, 12))]))
        rows = ps.counter_delta(fake.query, 'c', START, END)
        self.assertEqual(sum(r['value'] for r in rows), (20 - 3) + 12)
        self.assertEqual(ps.sum_by(rows, 'pod'), {'e0': 17, 'e1': 12})
        # the forms this replaces
        old_difference = sum(a['value'] - b['value'] for a in fake.query('c', END) for b in fake.query('c', START)
                             if a['labels'] == b['labels'])
        self.assertEqual(old_difference, 17, 'the vector difference dropped e1')
        self.assertEqual(sum(r['value'] for r in fake.query('increase(c[1801s])', END)), 10 + 5, 'increase dropped first samples')

    def test_every_series_born_late_is_a_figure_not_empty(self):
        fake = Fake(dict([counter('a', (1700, 4), (2700, 9), status_class='5xx'), counter('b', (1900, 2), (2700, 3), status_class='5xx')]))
        rows = ps.counter_delta(fake.query, 'c{status_class="5xx"}', START, END)
        self.assertEqual(ps.total(rows), 12)
        self.assertEqual(ps.total(ps.counter_delta(fake.query, 'missing', START, END)), None, 'no series is not zero')

    def test_a_reset_series_uses_increase(self):
        fake = Fake(dict([counter('a', (1100, 100), (1500, 5), (2700, 9))]))
        self.assertEqual(ps.total(ps.counter_delta(fake.query, 'c', START, END)), 5 + 4)


class Histogram(unittest.TestCase):
    def series(self, le_label):
        return dict([counter('a', (500, 1), (2700, 41), name='h_bucket', le='1.0'), counter('a', (500, 1), (2700, 91), name='h_bucket', le=le_label),
                     counter('a', (500, 1), (2700, 100), name='h_bucket', le='+Inf'),
                     counter('b', (1700, 10), (2700, 20), name='h_bucket', le='1.0'), counter('b', (1700, 10), (2700, 20), name='h_bucket', le=le_label),
                     counter('b', (1700, 10), (2700, 30), name='h_bucket', le='+Inf')])

    def test_over_30s_reads_the_bucket_whatever_the_label_spelling(self):
        for label in ('30', '30.0'):
            buckets = ps.histogram_delta(Fake(self.series(label)).query, 'h', START, END)
            self.assertEqual(buckets[math.inf], 99 + 30, label)
            self.assertEqual(ps.over_bound(buckets, 30), (99 + 30) - (90 + 20), label)
        self.assertIsNone(ps.over_bound({1.0: 3, math.inf: 5}, 30), 'no such bucket is unknown, not zero')

    def test_quantile_interpolates_like_prometheus(self):
        self.assertEqual(ps.histogram_quantile({1.0: 50, 2.0: 100, math.inf: 100}, 0.5), 1.0)
        self.assertEqual(ps.histogram_quantile({1.0: 50, 2.0: 100, math.inf: 100}, 0.75), 1.5)
        self.assertIsNone(ps.histogram_quantile({}, 0.5))


class Window(unittest.TestCase):
    def packet(self, d, **files):
        d = Path(d)
        with gzip.open(d / 'k6-scheduling.csv.gz', 'wt') as f:
            f.write('metric_name,timestamp,metric_value,scenario\n'
                    'vus,1000000,0,\nm7_driver_started,1010000,1,a\nm7_driver_started,1010500,1,b\niterations,2815000,1,a\n')
        (d / 'progress-stop.json').write_text(json.dumps({'readAtMs': 2830000}))
        for name, value in files.items():
            (d / name).write_text(json.dumps(value))
        return d

    def test_early_stop_window_comes_from_the_trace_and_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            load = self.packet(d, **{'driver-plans.json': {'manifest': {'cadence': {'loadSeconds': 1800}}}})
            w = ps.load_window(load)
            self.assertEqual((w['loadStartedAt'], w['loadEndedAt'], w['endedAt']), (1010.0, 2810.0, 2830.0))
            self.assertTrue(w['earlyStop'])
            self.assertIn('trace-derived', w['basis'])
            self.assertEqual(ps.end_read(load)[1], 'progress-stop.json')
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ps.load_window(self.packet(d))['loadEndedAt'], 2815.0, 'no manifest: the last trace row')

    def test_window_json_wins_and_a_packet_with_neither_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            load = self.packet(d, **{'window.json': {'loadStartedAt': 5, 'endedAt': 9}, 'progress-after.json': {'readAtMs': 9000}})
            self.assertEqual(ps.load_window(load)['basis'], 'window.json')
            self.assertEqual(ps.end_read(load)[1], 'progress-after.json')
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ps.load_window(d))
            self.assertEqual(ps.end_read(d), ({}, None))


class Bands(unittest.TestCase):
    def test_overall_percentiles_and_shares(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'm7-joined'))
        import latency_oracle as o
        lags = [500] * 90 + [5000] * 5 + [20000] * 3 + [40000] * 2
        rows = [{'lagMs': v} for v in lags]
        summary = {d: {'unmatched': 4 if d == 'entries' else 0, 'censored': 6 if d == 'entries' else 0, 'unviewed': 1} for d in o.DOMAINS}
        out = o.overall(summary, rows)
        self.assertEqual((out['p50Ms'], out['p95Ms'], out['p99Ms'], out['maxMs']), (500, 5000, 40000, 40000))
        self.assertEqual(out['bands']['4s']['within'], 90)
        self.assertEqual(out['bands']['10s']['within'], 95)
        self.assertEqual(out['bands']['30s'], {'within': 98, 'shareOfMatched': 0.98, 'shareOfViewedWrites': 0.8909})
        self.assertEqual(out['unviewed'], 3)
        self.assertIsNone(o.overall(summary, [])['p50Ms'])

    def test_a_packet_without_m3_latency_is_reduced_from_its_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            load = Path(d)
            (load / 'runid').write_text('r\n')
            accepted = lambda key, at: 'time="t" level=info msg=%s source=console\n' % json.dumps(json.dumps(
                {'event': 'm7-input-accepted', 'run': 'r', 'tenant': 'ta', 'domain': 'entries', 'key': key, 'requestToAcceptanceMs': 10, 'acceptedAtMs': at}))
            (load / 'k6.log').write_text(accepted('1000000', 5000) + accepted('1000001', 6000))
            frame = lambda at, key: json.dumps({'event': 'viewer-frame', 'version': 2, 'run': 'r', 'tenant': 'ta', 'socket': 0, 'atMs': at,
                                                'delta': False, 'keys': {'entries': [key], 'devicestatus': [], 'treatments': []}}) + '\n'
            (load / 'ledger').write_text('')
            (load / 'viewer-frames.jsonl').write_text(frame(5800, 1000000) + frame(20000, 1000001))
            out = ps.viewer_m3(load)['overall']
            self.assertEqual((out['matched'], out['p50Ms'], out['p99Ms']), (2, 800, 14000))
            self.assertEqual((out['bands']['4s']['within'], out['bands']['30s']['within']), (1, 2))
            (load / 'viewer-frames.jsonl').unlink()
            self.assertIsNone(ps.viewer_m3(load))


if __name__ == '__main__':
    unittest.main()
