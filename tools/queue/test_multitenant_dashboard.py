"""Focused validation for the derived dashboard and its acceptance overlay."""
import copy
import importlib.util
import json
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("dashboard", HERE / "multitenant_dashboard.py")
dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(dashboard.STATUS.read_text())
        self.queue = yaml.safe_load((dashboard.ROOT / "queue/work-queue.yaml").read_text())

    def test_queue_state_and_prerequisites_are_derived_not_overlay_claims(self):
        changed = copy.deepcopy(self.queue)
        item = next(i for i in changed["items"] if i["id"] == "TEN-LAB")
        item["state"] = "test-marker"
        item["blocks_on"] = ["MIG-VV"]
        text = dashboard.render(self.data, changed)
        row = next(line for line in text.splitlines() if '<a id="ten-lab">' in line)
        self.assertIn("test-marker", row)
        self.assertIn("MIG-VV (", row)
        self.assertNotIn("ST-PG (", row)

    def test_refuses_missing_queue_refs_cyclic_edges_and_broken_evidence(self):
        for mutate in [
            lambda d: d["work"][0].update(id="MISSING"),
            lambda d: d["milestones"][0].update(requires=["M1"]),
            lambda d: d["slices"][0].update(evidence="missing-document.md#capture"),
            lambda d: d["slices"][0].update(evidence=self.data["slices"][0]["evidence"].split("#")[0] + "#missing-anchor"),
            lambda d: d["slices"][0].update(stage="done"),
        ]:
            data = copy.deepcopy(self.data)
            mutate(data)
            with self.assertRaises(ValueError):
                dashboard.render(data, self.queue)

    def test_new_capture_can_link_its_report_without_extending_archived_journal(self):
        with tempfile.TemporaryDirectory(dir=dashboard.ROOT) as directory:
            capture = Path(directory) / "capture.md"
            capture.write_text("# Capture\n\n## Measured boundary\n")
            reference = os.path.relpath(capture, dashboard.STATUS.parent) + "#measured-boundary"
            data = copy.deepcopy(self.data)
            data["slices"][0]["evidence"] = reference
            text = dashboard.render(data, self.queue)
            self.assertIn("](" + reference + ")", text)

    def test_evidence_cannot_escape_the_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / "outside.md"
            capture.write_text("# Outside\n")
            data = copy.deepcopy(self.data)
            data["slices"][0]["evidence"] = os.path.relpath(capture, dashboard.STATUS.parent) + "#outside"
            with self.assertRaisesRegex(ValueError, "nonlocal evidence document"):
                dashboard.render(data, self.queue)

    def test_check_refuses_stale_view_and_accepts_regenerated_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dashboard.md"
            output.write_text("stale")
            with patch.object(dashboard, "OUTPUT", output), patch("sys.argv", ["dashboard", "--check"]):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    dashboard.main()
                self.assertEqual(failure.exception.code, 1)
                output.write_text(dashboard.render(self.data, self.queue))
                with contextlib.redirect_stdout(io.StringIO()):
                    dashboard.main()


if __name__ == "__main__":
    unittest.main()
