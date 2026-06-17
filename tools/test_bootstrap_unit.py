#!/usr/bin/env python3
"""
Unit tests for bootstrap.py repository refresh behavior.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import bootstrap  # noqa: E402


GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Copilot",
    "GIT_AUTHOR_EMAIL": "copilot@example.com",
    "GIT_COMMITTER_NAME": "Copilot",
    "GIT_COMMITTER_EMAIL": "copilot@example.com",
}


def run_git(args: list[str], cwd: Path) -> str:
    """Run git and return stdout."""
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, env=GIT_ENV).strip()


class TestBootstrapHelpers(unittest.TestCase):
    """Helper behavior that should remain stable across refreshes."""

    def test_preferred_tracking_ref_preserves_branch_metadata(self):
        repo = {
            "name": "demo",
            "ref": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "frozen_from": "main",
        }

        self.assertEqual(bootstrap.preferred_tracking_ref(repo), "main")
        changed = bootstrap.update_repo_pin(
            repo,
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        )

        self.assertTrue(changed)
        self.assertEqual(repo["ref"], "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
        self.assertEqual(repo["frozen_from"], "main")


class TestBootstrapRefresh(unittest.TestCase):
    """End-to-end refresh behavior against temporary git repositories."""

    def create_repo_pair(self, default_branch: str = "master") -> tuple[Path, Path, str, str]:
        temp_dir = Path(tempfile.mkdtemp())
        source = temp_dir / "source"
        externals = temp_dir / "externals"
        checkout = externals / "demo"

        run_git(["init", "-b", default_branch, str(source)], cwd=temp_dir)
        (source / "README.md").write_text("one\n")
        run_git(["add", "README.md"], cwd=source)
        run_git(["commit", "-m", "initial"], cwd=source)
        first_sha = run_git(["rev-parse", "HEAD"], cwd=source)

        (source / "README.md").write_text("two\n")
        run_git(["commit", "-am", "second"], cwd=source)
        second_sha = run_git(["rev-parse", "HEAD"], cwd=source)

        run_git(["clone", str(source), str(checkout)], cwd=temp_dir)
        run_git(["checkout", first_sha], cwd=checkout)

        return temp_dir, checkout, first_sha, second_sha

    def write_lockfile(self, root: Path, source: Path, ref: str, frozen_from: str) -> Path:
        lockfile = root / "workspace.lock.json"
        lockfile.write_text(json.dumps({
            "externals_dir": str(root / "externals"),
            "repos": [{
                "name": "demo",
                "url": str(source),
                "ref": ref,
                "frozen_from": frozen_from,
                "description": "demo repo",
            }],
        }, indent=2) + "\n")
        return lockfile

    def test_refresh_updates_detached_checkout_and_lockfile(self):
        root, checkout, first_sha, second_sha = self.create_repo_pair(default_branch="master")
        source = root / "source"
        lockfile = self.write_lockfile(root, source, first_sha, "master")

        result = bootstrap.cmd_refresh(SimpleNamespace(), lockfile)

        self.assertEqual(result, 0)
        self.assertEqual(run_git(["rev-parse", "HEAD"], cwd=checkout), second_sha)
        data = json.loads(lockfile.read_text())
        self.assertEqual(data["repos"][0]["ref"], second_sha)
        self.assertEqual(data["repos"][0]["frozen_from"], "master")

    def test_refresh_falls_back_to_origin_head_for_stale_branch_name(self):
        root, checkout, first_sha, second_sha = self.create_repo_pair(default_branch="master")
        source = root / "source"
        lockfile = self.write_lockfile(root, source, first_sha, "main")

        result = bootstrap.cmd_refresh(SimpleNamespace(), lockfile)

        self.assertEqual(result, 0)
        self.assertEqual(run_git(["rev-parse", "HEAD"], cwd=checkout), second_sha)
        data = json.loads(lockfile.read_text())
        self.assertEqual(data["repos"][0]["ref"], second_sha)
        self.assertEqual(data["repos"][0]["frozen_from"], "master")


if __name__ == "__main__":
    unittest.main(verbosity=2)
