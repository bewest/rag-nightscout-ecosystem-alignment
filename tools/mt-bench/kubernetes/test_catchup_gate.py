import json
import unittest
from pathlib import Path

import catchup_gate as g

S = g.settings({'windowSeconds': 300, 'pollSeconds': 30, 'deadlineSeconds': 1200})


def row(t, overdue=0, pending=0, over=0, count=0, tenants=1000):
    return {'readAtMs': t * 1000, 'tenants': tenants, 'overdue': overdue, 'pending': pending, 'over120s': over,
            'lagCount': count}


class Clock:
    def __init__(self):
        self.t = 0.0

    def time(self):
        return self.t

    def sleep(self, s):
        self.t += s


class CatchupGate(unittest.TestCase):
    def test_wave_then_quiet_window(self):
        rows = [row(0, overdue=9000, pending=4000, over=10), row(60, overdue=3000, over=40), row(120, over=55),
                row(180, over=55), row(300, over=55), row(420, over=55)]
        self.assertEqual(g.caught_up(rows, S), 5)          # 120 s .. 420 s at baseline, over120s flat

    def test_late_completions_reset_the_window(self):
        rows = [row(0), row(200), row(250, over=1), row(400, over=1), row(500, over=1)]
        self.assertIsNone(g.caught_up(rows, S))            # window restarts at 250 s; 500-250 < 300
        self.assertEqual(g.caught_up(rows + [row(560, over=1)], S), 5)

    def test_overdue_or_pending_above_tolerance_is_not_caught_up(self):
        self.assertIsNone(g.caught_up([row(t, overdue=1) for t in range(0, 900, 60)], S))
        self.assertIsNone(g.caught_up([row(t, pending=2) for t in range(0, 900, 60)], S))
        tolerant = dict(S, toleranceTenants=2)
        self.assertIsNotNone(g.caught_up([row(t, pending=2) for t in range(0, 900, 60)], tolerant))

    def test_wait_reports_warmup_and_refuses_at_the_deadline(self):
        clock = Clock()
        series = iter([row(0, overdue=500)] + [row(30 * i) for i in range(1, 40)])
        def fetch():
            return json.dumps({k: str(v) for k, v in next(series).items()})
        result = g.wait(fetch, S, clock)
        self.assertEqual(result['verdict'], 'CAUGHT_UP')
        self.assertEqual(result['warmupSeconds'], 330.0)
        clock = Clock()
        def busy():
            return json.dumps({k: str(v) for k, v in row(int(clock.t), overdue=7).items()})
        with self.assertRaises(g.NotCaughtUp) as caught:
            g.wait(busy, S, clock)
        self.assertEqual(caught.exception.record['code'], 'K8S_CATCHUP_NOT_REACHED')

    def test_settings_and_binding_refusals(self):
        self.assertIsNone(g.settings(None))
        self.assertEqual(g.settings(True)['windowSeconds'], 300)
        for bad in ({'windowSeconds': 10, 'pollSeconds': 30}, {'other': 1}, {'deadlineSeconds': 100}):
            with self.assertRaises(ValueError):
                g.settings(bad)
        with self.assertRaises(ValueError):
            g.query({'checkpoint': 'x;', 'consumer': 'evaluator-a-completed', 'writerDriven': {'lifecycle': 'l'}}, 60)
        sql = g.query({'checkpoint': 'nsdemo_eval_checkpoint', 'consumer': 'evaluator-x-completed',
                       'writerDriven': {'lifecycle': 'nsdemo_lifecycle'}}, 60)
        self.assertIn('work_due_at < (SELECT t FROM now_ms) - 60000', sql)

    def test_execute_gates_viewer_priming(self):
        text = Path(g.__file__).with_name('execute.py').read_text()
        self.assertIn('catchup_gate.wait(', text)
        self.assertLess(text.index('catchup_gate.wait('), text.index("str(d / 'probe.cjs')"))
        # The gate's stage function must not shadow the `catchup` module (execute.py imports it for catchup.observer).
        import execute
        self.assertTrue(hasattr(execute.catchup, 'observer'))
        self.assertNotIn('\ndef catchup(', text)


if __name__ == '__main__':
    unittest.main()


class GateBeforeAccess(unittest.TestCase):
    """Round 2 (2026-11-24): the access witness runs after the catch-up gate reports CAUGHT_UP (lanel-c4-02/03 timed out
    the witness during the 10k post-restore catch-up), and the load stage reuses that record as its warm-up."""

    def test_attach_runs_the_gate_before_access(self):
        text = Path(g.__file__).with_name('attach.py').read_text()
        self.assertIn("execute('catchup'", text)
        self.assertLess(text.index("execute('catchup'"), text.index("execute('access'"))

    def test_adapter_has_a_catchup_command(self):
        text = Path(g.__file__).with_name('adapter.py').read_text()
        self.assertIn("'catchup'", text)
        self.assertIn('gate_before_access(', text)

    def test_load_stage_reuses_the_pre_access_record(self):
        import tempfile
        import execute
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); out = d / 'load'; out.mkdir()
            record = {'verdict': 'CAUGHT_UP', 'warmupSeconds': 412.0, 'caughtUpAtMs': 1, 'samples': []}
            (d / 'catchup-gate.json').write_text(json.dumps(record))
            got = execute.wait_for_catchup(d, out, {'completion': {}}, None, None, {'windowSeconds': 300})
            self.assertEqual(got['warmupSeconds'], 412.0)
            self.assertEqual(got['gatedBefore'], 'access')
            self.assertEqual(json.loads((out / 'catchup.json').read_text())['gatedBefore'], 'access')
