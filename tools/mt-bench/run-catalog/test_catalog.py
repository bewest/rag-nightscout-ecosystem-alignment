import copy
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest

from catalog import CatalogError, add, compare, list_records
from retained import project


SOURCE = {"core": "a" * 40, "deploy": "b" * 40}
TOOL = "c" * 64
IMAGE = "sha256:" + "d" * 64


def write(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(root):
    write(root, "result.json", {"status": "OBSERVED", "runtime": "REUSED"})
    write(root, "history.json", {"runtime": "REUSED", "previousObservations": []})
    write(root, "config.json", {"tier": "discovery", "secret": "SENSITIVE_FIXTURE_MARKER"})
    write(root, "fixture/owner.json", {
        "pair": SOURCE, "instrument": {"sha256": TOOL}, "imageId": IMAGE,
        "workload": {"adaptedSha256": "e" * 64},
        "runConfiguration": {"resources": {"profile": {"services": {"api": {"millicpus": 500}}}}},
        "hostIdentity": "f" * 64, "replicas": 1, "tenants": 8,
        "cadence": {"loadSeconds": 60, "offeredRps": 1},
    })
    write(root, "fixture/load-before-host.json", {"scope": "shared-host diagnostic", "load": [1]})
    write(root, "fixture/load/before-cgroups.json", {})
    write(root, "fixture/load/k6-summary.json", {"metrics": {"dropped_iterations": {"count": 0}}})
    write(root, "fixture/summary.json", {
        "pair": SOURCE, "instrument": TOOL, "imageId": IMAGE,
        "oracle": {"verdict": "GREEN"}, "ownershipVerified": True,
        "httpAccounting": {
            "scenario": {"attempts": 60, "completed": 60},
            "httpVerdict": "PASS", "offeredWorkVerdict": "PASS",
        },
        "measurements": {"windows": {"load": {"roles": {
            "api": {"cpuCoresMean": 0.2, "counterReset": False},
        }}}},
    })
    write(root, "fixture/load/probe.json", {"durableOutputObservation": {
        "witnesses": 2, "refused": 0, "pendingAccepted": 0,
        "matchedClientMs": {"n": 2, "p95": 19}, "durableUpperMs": {"n": 2, "p95": 540},
    }})


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.artifacts = Path(self.temp.name)
        self.index = self.artifacts / "capacity-index"
        self.run = self.artifacts / "lane" / "run"
        fixture(self.run)

    def test_concurrent_duplicates_publish_one_complete_record(self):
        with ProcessPoolExecutor(max_workers=4) as workers:
            calls = [workers.submit(add, self.artifacts, self.index, self.run) for _ in range(8)]
            rows = [call.result(timeout=10) for call in calls]
        self.assertTrue(all(rows[0] == row for row in rows[1:]))
        self.assertEqual(list_records(self.index), [rows[0]])
        self.assertNotIn("SENSITIVE_FIXTURE_MARKER", json.dumps(rows[0]))
        write(self.run, "result.json", {"status": "FAILED", "code": "M7_DIFFERENT_RESULT"})
        with self.assertRaisesRegex(CatalogError, "already has a different record"):
            add(self.artifacts, self.index, self.run)
        self.assertEqual(list_records(self.index), [rows[0]])

    def test_concurrent_distinct_runs_are_all_visible(self):
        dirs = [self.artifacts / "lane" / f"run-{index}" for index in range(4)]
        for path in dirs:
            fixture(path)
        with ProcessPoolExecutor(max_workers=4) as workers:
            calls = [workers.submit(add, self.artifacts, self.index, path) for path in dirs]
            rows = [call.result(timeout=10) for call in calls]
        self.assertEqual(list_records(self.index), rows)

    def test_malformed_summary_preserves_independent_probe_and_source(self):
        path = self.run / "fixture" / "summary.json"
        path.write_text('{"truncated"')
        row = add(self.artifacts, self.index, self.run)
        self.assertIn({"path": "fixture/summary.json", "code": "EVIDENCE_MALFORMED"}, row["issues"])
        self.assertEqual(row["signals"]["client.frame.p95"]["value"], 19)
        self.assertEqual(row["provenance"]["source"], SOURCE)
        self.assertEqual(row["oracles"]["stored"], "UNMEASURED")
        self.assertIsNone(row["work"]["issued"])
        self.assertEqual(row["work"]["dropped"], 0)

    def test_clinical_comes_from_runner_selected_clinical_when_probe_reports_timings_only(self):
        self.assertEqual(project(self.run, "run")["oracles"]["clinical"], "UNMEASURED")
        write(self.run, "result.json", {"status": "OBSERVED", "runtime": "REUSED",
                                        "partial": {"observations": {"selectedClinical": {"verdict": "PASS"}}}})
        self.assertEqual(project(self.run, "run")["oracles"]["clinical"], "PASS")
        write(self.run, "result.json", {"status": "OBSERVED", "runtime": "REUSED",
                                        "partial": {"observations": {"selectedClinical": {"verdict": "FAIL"}}}})
        self.assertEqual(project(self.run, "run")["oracles"]["clinical"], "FAIL")

    def test_startup_failure_is_retained_with_unknown_work(self):
        path = self.artifacts / "lane" / "startup"
        write(path, "result.json", {"status": "FAILED_PARTIAL", "phase": "deploy",
                                   "failure": {"code": "M7_RUNNER_DEPLOY_FAILED"}})
        write(path, "fixture/terminal-before-cleanup.json", {})
        row = add(self.artifacts, self.index, path)
        self.assertEqual(row["phase"], "DEPLOY")
        self.assertEqual(row["failureCode"], "M7_RUNNER_DEPLOY_FAILED")
        self.assertIn("fixture/terminal-before-cleanup.json", row["evidence"])
        self.assertIsNone(row["work"]["dropped"])
        self.assertIsNone(row["work"]["issued"])

    def test_kubernetes_startup_evidence_without_load_result(self):
        path = self.artifacts / "lane" / "kube-startup"
        write(path, "runtime/first-failure.json", {"code": "SOURCE_ROLE_EXPORT_POD_FAILED"})
        write(path, "runtime/absence.json", {"verifiedAt": "synthetic"})
        write(path, "inventory.json", {"sourceCommit": SOURCE["core"], "imageDeployCommit": SOURCE["deploy"],
                                       "candidateContract": {"imageConfigId": IMAGE}})
        write(path, "environment.json", {"sourceCommit": SOURCE["core"], "imageDeployCommit": SOURCE["deploy"],
                                         "trialPurpose": "scale-diagnostic", "tenantCount": 2})
        row = add(self.artifacts, self.index, path)
        self.assertEqual(row["producer"], "kubernetes")
        self.assertEqual(row["runStatus"], "FAILED")
        self.assertEqual(row["phase"], "STARTUP")
        self.assertEqual(row["failureCode"], "SOURCE_ROLE_EXPORT_POD_FAILED")
        self.assertEqual(row["oracles"]["cleanup"], "PASS")
        self.assertIsNone(row["work"]["issued"])
        self.assertEqual(row["provenance"]["source"], SOURCE)

    def test_kubernetes_terminal_case_includes_nested_packet_and_cleanup(self):
        path = self.artifacts / "lane" / "case"
        pins = {"pair": SOURCE, "instrument": TOOL, "appImageId": IMAGE}
        packet = "runtime/packet/"
        write(path, packet + "run.json", {"pins": pins, "tenants": 2, "roles": {"api": {}}, "tier": "smoke"})
        write(path, packet + "experiment/result.json", {"verdict": "OBSERVED"})
        write(path, packet + "load/result.json", {"pins": pins, "storedWrites": {"verdict": "PASS"}})
        write(path, "intent.json", {"profile": {"history": {"mode": "existing-provisioner-only"}}})
        write(path, "runtime/custody.json", {"namespaceUid": "synthetic"})
        write(path, "runtime/absence.json", {"verifiedAt": "synthetic"})
        row = add(self.artifacts, self.index, path)
        self.assertEqual(row["tier"], "smoke")
        self.assertEqual(row["runStatus"], "OBSERVED")
        self.assertEqual(row["oracles"]["stored"], "PASS")
        self.assertEqual(row["oracles"]["cleanup"], "PASS")
        self.assertEqual(row["history"]["runtime"], "FRESH")
        self.assertIn(packet + "load/result.json", row["evidence"])

    def test_interrupted_result_requires_explicit_partial_import(self):
        (self.run / "result.json").write_text("null")
        with self.assertRaisesRegex(CatalogError, "terminal status unavailable"):
            add(self.artifacts, self.index, self.run)
        row = add(self.artifacts, self.index, self.run, allow_partial=True)
        self.assertIsNone(row["runStatus"])
        self.assertEqual(row["oracles"]["stored"], "GREEN")

    def test_source_mismatch_inside_run_refuses_even_explicit_source_comparison(self):
        baseline = project(self.run, "baseline")
        path = self.run / "fixture" / "summary.json"
        altered = json.loads(path.read_text())
        altered["pair"]["core"] = "f" * 40
        write(self.run, "fixture/summary.json", altered)
        current = project(self.run, "wrong-source")
        self.assertIn({"path": "fixture/summary.json", "code": "PROVENANCE_MISMATCH"}, current["issues"])
        report = compare(current, baseline, source_change=True)
        self.assertIn("wrong-source has inconsistent provenance", report["reasons"])
        self.assertIsNone(report["signals"]["client.frame.p95"]["delta"])
        self.assertEqual(current["signals"]["client.frame.p95"]["value"], 19)

    def test_deliberate_source_and_image_change_requires_opt_in(self):
        baseline = project(self.run, "baseline")
        current = copy.deepcopy(baseline)
        current["id"] = "after"
        current["provenance"]["source"]["core"] = "f" * 40
        self.assertEqual(compare(current, baseline, source_change=True)["status"], "INCOMPATIBLE")
        current["provenance"]["image"] = "sha256:" + "0" * 64
        self.assertEqual(compare(current, baseline)["status"], "INCOMPATIBLE")
        self.assertEqual(compare(current, baseline, source_change=True)["status"], "COMPARABLE")

    def test_missing_metric_and_changed_denominator_leave_other_deltas_available(self):
        baseline = project(self.run, "baseline")
        (self.run / "fixture" / "load" / "probe.json").unlink()
        current = project(self.run, "current")
        current["signals"]["cpu.api.quota"]["denominator"] = "host CPU quota"
        report = compare(current, baseline)
        self.assertEqual(report["status"], "COMPARABLE")
        self.assertEqual(report["signals"]["client.frame.p95"]["status"], "UNMEASURED")
        self.assertEqual(report["signals"]["cpu.api.quota"]["status"], "DENOMINATOR_OR_SCOPE_MISMATCH")
        self.assertIsNone(report["signals"]["cpu.api.quota"]["delta"])
        self.assertEqual(report["oracles"]["current"]["stored"], "GREEN")


if __name__ == "__main__":
    unittest.main()
