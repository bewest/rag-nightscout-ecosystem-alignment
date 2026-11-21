import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main_thread  # noqa: E402
import smoke  # noqa: E402
import statement_phase as sp  # noqa: E402

E, L, O, S = 'nsdemo_evaluator', 'nsdemo_lifetime_evaluator', 'nsdemo_outbox', 'nsdemo_suppression'
ROWS = [  # role, text, calls before, calls after
    (E, 'BEGIN ISOLATION LEVEL READ COMMITTED', 10, 50),
    (E, 'COMMIT', 10, 50),
    (E, 'SELECT set_config($1,$2,true)', 0, 30),
    (E, 'SELECT lock_key::text AS lock_key,generation::text AS generation,phase FROM t WHERE x', 0, 20),
    (E, 'SELECT tenant_id::text AS tenant,contract_digest,work_version,work_observed FROM t', 0, 10),
    (E, 'SELECT a.tenant_id::text AS tenant,a.version::text AS activity_version FROM a', 0, 10),
    (E, 'SELECT x,output_identity,output_digest,output_revision FROM c FOR UPDATE', 0, 10),
    (L, 'COMMIT', 0, 15),
    (O, 'SELECT anything FROM outbox', 0, 40),
    (S, 'SELECT has_table_privilege($1)', 0, 5),
    (E, 'SELECT something_new()', 0, 10),
    ('nsdemo_api', 'INSERT INTO entries', 0, 999),
    ('nsdemo_lifetime_api', 'COMMIT', 11, 12),
]


def tsv(rows, which):
    return ''.join(f'{r}\t{(b if which == 0 else a)}\t{float(b if which == 0 else a)}\t{i}\t1\t{t.encode().hex()}\n'
                   for i, (r, t, b, a) in enumerate(rows))


def point(root, rows=ROWS, http=8, probe=2):
    load = root / 'fixture' / 'load'
    load.mkdir(parents=True)
    (load / 'before-pg-statements.tsv').write_text(tsv(rows, 0))
    (load / 'after-pg-statements.tsv').write_text(tsv(rows, 1))
    for name, t in (('before', 1_000_000_000), ('after', 61_000_000_000)):
        reads = {k: {'status': 'PASS', 'monotonicStartedAtNs': t + i * 10, 'monotonicFinishedAtNs': t + i * 10 + 5,
                     'wallStartedAtNs': 1, 'wallFinishedAtNs': 2} for i, k in enumerate(('pg-role', 'pg-statements'))}
        (load / f'{name}-sql-snapshot-timing.json').write_text(json.dumps({'clockDomain': 'collector-host-monotonic-v1', 'reads': reads}))
    result = {'partial': {'observations': {'http': {'shapes': {
        'w_sgv': {'writeOutcomes': {'accepted': http - 1}}, 'w_treatments_v3': {'writeOutcomes': {'accepted': 1}},
        'r_sgv': {'writeOutcomes': None}}}, 'storedWrites': {'probeStored': probe}}}}
    (root / 'result.json').write_text(json.dumps(result))
    return root


class StatementPhase(unittest.TestCase):
    def test_roles_phases_and_per_write(self):
        with tempfile.TemporaryDirectory() as d:
            r = sp.reduce_point(point(Path(d)))
        self.assertEqual(r['acceptedWrites']['total'], 10)
        self.assertEqual(r['total']['calls'], 40 + 40 + 30 + 20 + 10 + 10 + 10 + 15 + 40 + 5 + 10)
        self.assertEqual(r['phases']['txn-control']['perWrite'], 8.0)
        self.assertEqual(r['phases']['fences']['perWrite'], 3.0)
        self.assertEqual(r['phases']['receipt']['perWrite'], 2.0)
        self.assertEqual(r['phases']['settings']['perWrite'], 1.0)
        self.assertEqual(r['phases']['observe']['perWrite'], 1.5)
        self.assertEqual(r['phases']['consumers']['perWrite'], 4.5)
        self.assertEqual(r['phases']['unattributed']['calls'], 10)
        self.assertNotIn('nsdemo_api', r['roles'])
        self.assertEqual(r['api'], {'calls': 1000, 'ms': 1000.0, 'perWrite': 100.0, 'msPerWrite': 100.0})
        self.assertEqual(r['windowSeconds'], 60.0)

    def test_negative_control_empty_rules_attributes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            r = sp.reduce_point(point(Path(d)), rules=[])
        self.assertEqual(list(r['phases']), ['unattributed'])
        self.assertEqual(r['attributedShare'], 0.0)

    def test_eviction_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            p = point(Path(d))
            after = p / 'fixture/load/after-pg-statements.tsv'
            after.write_text(''.join(after.read_text().splitlines(True)[1:]))
            with self.assertRaises(Exception):
                sp.reduce_point(p)

    def test_campaign_layout(self):
        with tempfile.TemporaryDirectory() as d:
            case = Path(d) / 'case'
            point(case)
            (case / 'raw').mkdir()
            (case / 'fixture').rename(case / 'raw' / 'fixture')
            self.assertEqual(sp.reduce_point(Path(d))['acceptedWrites']['total'], 10)


def ticks(path, cid='c1', start=0, n=70, main_per_s=50, other_per_s=10, hz=100):
    with open(path, 'w') as f:
        f.write(json.dumps({'kind': 'attach', 'container': cid, 'clkTck': hz, 'clkTckOrigin': 'read', 'monoNs': start}) + '\n')
        for i in range(n):
            f.write(json.dumps({'kind': 'tick', 'container': cid, 'monoNs': start + i * 10**9, 'procs': {
                '7': {'main': i * main_per_s, 'proc': i * (main_per_s + other_per_s), 'cmd': 'node entrypoint.js evaluator'},
                '1': {'main': i, 'proc': i, 'cmd': 'node entrypoint.js'}}}) + '\n')


class MainThread(unittest.TestCase):
    def test_interpolates_window_and_picks_busiest(self):
        with tempfile.TemporaryDirectory() as d:
            ticks(Path(d) / 's.jsonl')
            r = main_thread.reduce(Path(d) / 's.jsonl', (int(1.5e9), int(61.5e9)), 100)
        self.assertEqual(r['status'], 'MEASURED')
        self.assertEqual(r['pid'], '7')
        self.assertAlmostEqual(r['mainThreadSeconds'], 30.0)
        self.assertAlmostEqual(r['mainThreadBusyShare'], 0.5)
        self.assertAlmostEqual(r['mainThreadMsPerWrite'], 300.0)
        self.assertAlmostEqual(r['processMsPerWrite'], 360.0)

    def test_uncovered_window_is_unmeasured(self):
        with tempfile.TemporaryDirectory() as d:
            ticks(Path(d) / 's.jsonl', n=10)
            r = main_thread.reduce(Path(d) / 's.jsonl', (int(1.5e9), int(61.5e9)), 100)
        self.assertEqual(r['status'], 'UNMEASURED')

    def test_container_restart_in_window_is_unmeasured(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 's.jsonl'
            ticks(p)
            ticks(Path(d) / 'b.jsonl', cid='c2', start=30 * 10**9, n=40)
            p.write_text(p.read_text() + (Path(d) / 'b.jsonl').read_text())
            r = main_thread.reduce(p, (int(1.5e9), int(61.5e9)), 100)
        self.assertEqual(r['reason'], 'CONTAINER_CHANGED_IN_WINDOW')

    def test_two_slices_require_both_windows_and_sum_fleet_cost(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'run'
            paths = main_thread.sample_paths(root, 2)
            window = (int(1.5e9), int(61.5e9))
            ticks(paths['evaluator'])
            partial = main_thread.reduce_services(root, 2, window, 100)
            self.assertEqual(partial['status'], 'UNMEASURED')
            self.assertEqual(partial['byService']['evaluator']['status'], 'MEASURED')
            ticks(paths['evaluator-2'], cid='c2', main_per_s=25)
            result = main_thread.reduce_services(root, 2, window, 100)
            self.assertEqual(result['mainThreadMsPerWrite'], 450)
            self.assertEqual(result['mainThreadBusyShare'], .375)


class SmokeConfiguration(unittest.TestCase):
    def test_transport_defaults_and_worker_override(self):
        args = ('core', 'deploy', '/core', '/deploy', 'project', smoke.WORKLOAD)
        with patch.object(smoke, 'free_subnets', return_value=('backend', 'edge')):
            writer = smoke.config(*args)['prepare']
            one = smoke.config(*args, workers=1)['prepare']
        self.assertEqual((writer['input-transport'], writer['replicas'], writer['static-workers']), ('writer-driven', 2, 2))
        self.assertNotIn('pgstream-topology', writer)
        self.assertEqual((one['replicas'], one['static-workers']), (2, 1))



class Compare(unittest.TestCase):
    def test_comparison_is_a_figure_not_a_gate(self):
        s = {'candidate': {'core': 'a'}, 'workload': {'tenants': 16},
             'statementsPerWrite': {'total': 40.0, 'byRole': {E: 30.0}, 'byPhase': {'fences': 2.0}},
             'executionMsPerWrite': {'total': 1.0}, 'mainThread': {'mainThreadMsPerWrite': 2.0}}
        b = {'candidate': {'core': 'b'}, 'workload': {'tenants': 16},
             'statementsPerWrite': {'total': 160.0, 'byRole': {E: 100.0}, 'byPhase': {'fences': 30.0, 'txn-control': 40.0}},
             'executionMsPerWrite': {'total': 3.0}, 'mainThread': {'mainThreadMsPerWrite': 4.0}}
        c = smoke.compare(s, b)
        self.assertFalse(c['gate'])
        self.assertTrue(c['workloadMatches'])
        self.assertEqual(c['figures']['statementsPerWrite.total'], {'observed': 40.0, 'baseline': 160.0, 'delta': -120.0, 'ratio': 0.25})
        self.assertIsNone(c['figures']['statementsPerWrite.byPhase.txn-control']['observed'])
        self.assertEqual(c['figures']['mainThreadMsPerWrite']['ratio'], 0.5)


if __name__ == '__main__':
    unittest.main()
