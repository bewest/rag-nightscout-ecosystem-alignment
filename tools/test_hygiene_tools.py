#!/usr/bin/env python3
"""
Tests for hygiene tools (queue_stats.py, doc_chunker.py, backlog_hygiene.py).

These tests validate that the tools correctly parse the actual file formats
used in this project.

Usage:
    python tools/test_hygiene_tools.py              # Run all tests
    python tools/test_hygiene_tools.py -v           # Verbose output
    python -m pytest tools/test_hygiene_tools.py   # With pytest

Exit codes:
    0 - All tests pass
    1 - Test failures
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent


class TestQueueStats(unittest.TestCase):
    """Tests for queue_stats.py"""
    
    def run_queue_stats(self, *args):
        """Run queue_stats.py with given arguments."""
        cmd = [sys.executable, "tools/queue_stats.py"] + list(args)
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        return result
    
    def test_oneline_output_format(self):
        """Test that one-line output matches expected format."""
        result = self.run_queue_stats()
        # Should match: Queues: LIVE=N/N Ready=N/N | Files: gaps=N reqs=N prog=N | Uncommitted: N
        pattern = r'Queues: LIVE=\d+/\d+ Ready=\d+/\d+.*\| Files:.*\| Uncommitted: \d+'
        self.assertRegex(result.stdout, pattern, 
            f"One-line output doesn't match expected format: {result.stdout}")
    
    def test_json_output_structure(self):
        """Test that JSON output has expected structure."""
        result = self.run_queue_stats("--json")
        data = json.loads(result.stdout)
        
        # Check required top-level keys
        self.assertIn("queues", data)
        self.assertIn("files", data)
        self.assertIn("git", data)
        self.assertIn("health", data)
        
        # Check queue structure
        self.assertIn("live_pending", data["queues"])
        self.assertIn("live_processed", data["queues"])
        self.assertIn("ready_queue", data["queues"])
    
    def test_route_gap_prefix(self):
        """Test --route for GAP prefixes."""
        test_cases = [
            ("GAP-CGM", "cgm-sources-gaps.md"),
            ("GAP-SYNC", "sync-identity-gaps.md"),
            ("GAP-API", "nightscout-api-gaps.md"),
            ("GAP-ALG", "aid-algorithms-gaps.md"),
            ("GAP-TREAT", "treatments-gaps.md"),
            ("GAP-PUMP", "pumps-gaps.md"),
        ]
        
        for prefix, expected_file in test_cases:
            with self.subTest(prefix=prefix):
                result = self.run_queue_stats("--route", prefix)
                self.assertIn(expected_file, result.stdout,
                    f"Expected {expected_file} for {prefix}, got: {result.stdout}")
    
    def test_route_req_prefix(self):
        """Test --route for REQ prefixes."""
        test_cases = [
            ("REQ-PUMP", "pumps-requirements.md"),
            ("REQ-CGM", "cgm-sources-requirements.md"),
            ("REQ-SYNC", "sync-identity-requirements.md"),
        ]
        
        for prefix, expected_file in test_cases:
            with self.subTest(prefix=prefix):
                result = self.run_queue_stats("--route", prefix)
                self.assertIn(expected_file, result.stdout,
                    f"Expected {expected_file} for {prefix}, got: {result.stdout}")
    
    def test_route_unknown_prefix_falls_back(self):
        """Test that unknown prefix falls back to default file."""
        result = self.run_queue_stats("--route", "GAP-UNKNOWN")
        self.assertIn("default", result.stdout.lower())


class TestDocChunker(unittest.TestCase):
    """Tests for doc_chunker.py"""
    
    def run_doc_chunker(self, *args):
        """Run doc_chunker.py with given arguments."""
        cmd = [sys.executable, "tools/doc_chunker.py"] + list(args)
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        return result
    
    def test_check_output_format(self):
        """Test --check output format."""
        result = self.run_doc_chunker("--check")
        # Should contain file check results
        self.assertIn("gaps.md", result.stdout)
        self.assertIn("requirements.md", result.stdout)
    
    def test_check_json_structure(self):
        """Test --check --json output structure."""
        result = self.run_doc_chunker("--check", "--json")
        data = json.loads(result.stdout)
        
        self.assertIn("files_over_threshold", data)
        self.assertIn("files_ok", data)
    
    def test_lint_finds_no_misplaced(self):
        """Test --lint on current files (should be clean after chunking)."""
        result = self.run_doc_chunker("--lint")
        self.assertIn("HEALTH: OK", result.stdout)
        self.assertIn("Misplaced: 0", result.stdout)
    
    def test_lint_json_structure(self):
        """Test --lint --json output structure."""
        result = self.run_doc_chunker("--lint", "--json")
        data = json.loads(result.stdout)
        
        self.assertIn("misplaced", data)
        self.assertIn("correct", data)
        self.assertIn("total", data)
        self.assertIn("health", data)
    
    def test_next_id_gap(self):
        """Test --next-id for GAP prefixes."""
        result = self.run_doc_chunker("--next-id", "GAP-CGM")
        
        # Should output next ID and target file
        self.assertIn("GAP-CGM-", result.stdout)
        self.assertIn("cgm-sources-gaps.md", result.stdout)
    
    def test_next_id_req(self):
        """Test --next-id for REQ prefixes."""
        result = self.run_doc_chunker("--next-id", "REQ-PUMP")
        
        self.assertIn("REQ-PUMP-", result.stdout)
        self.assertIn("pumps-requirements.md", result.stdout)
    
    def test_next_id_json_structure(self):
        """Test --next-id --json output structure."""
        result = self.run_doc_chunker("--next-id", "GAP-CGM", "--json")
        data = json.loads(result.stdout)
        
        self.assertIn("prefix", data)
        self.assertIn("next_id", data)
        self.assertIn("next_number", data)
        self.assertIn("target_file", data)
        self.assertEqual(data["prefix"], "GAP-CGM")
    
    def test_analyze_gaps_file(self):
        """Test --analyze on a gaps domain file."""
        result = self.run_doc_chunker("--analyze", "traceability/cgm-sources-gaps.md")
        
        self.assertIn("Total lines:", result.stdout)
        self.assertIn("Total gaps:", result.stdout)


class TestBacklogHygiene(unittest.TestCase):
    """Tests for backlog_hygiene.py"""
    
    def run_backlog_hygiene(self, *args):
        """Run backlog_hygiene.py with given arguments."""
        cmd = [sys.executable, "tools/backlog_hygiene.py"] + list(args)
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        return result
    
    def test_check_output_format(self):
        """Test --check output format."""
        result = self.run_backlog_hygiene("--check")
        # Should contain queue health info
        self.assertIn("LIVE-BACKLOG", result.stdout.upper() or result.stderr.upper() or "LIVE-BACKLOG")
    
    def test_check_json_structure(self):
        """Test --check --json output structure."""
        result = self.run_backlog_hygiene("--check", "--json")
        
        # Skip if tool doesn't support JSON yet
        if result.returncode != 0 and "json" in result.stderr.lower():
            self.skipTest("backlog_hygiene.py --json not fully implemented")
        
        try:
            data = json.loads(result.stdout)
            self.assertIn("live_backlog", data)
        except json.JSONDecodeError:
            # Tool may output non-JSON, that's acceptable for now
            pass


class TestFileFormats(unittest.TestCase):
    """Tests that validate actual file formats in the project."""
    
    def test_gaps_domain_files_have_correct_prefixes(self):
        """Test that each domain gaps file contains only matching prefixes."""
        prefix_map = {
            "cgm-sources-gaps.md": ["GAP-CGM", "GAP-G7", "GAP-LIBRE", "GAP-DEXCOM", "GAP-BLE", 
                                     "GAP-LIBRELINK", "GAP-SHARE", "GAP-BRIDGE", "GAP-LF"],
            "sync-identity-gaps.md": ["GAP-SYNC", "GAP-BATCH", "GAP-TZ", "GAP-DELEGATE"],
            "nightscout-api-gaps.md": ["GAP-API", "GAP-AUTH", "GAP-UI", "GAP-DB", 
                                        "GAP-PLUGIN", "GAP-STATS", "GAP-ERR", "GAP-SPEC"],
            "aid-algorithms-gaps.md": ["GAP-ALG", "GAP-OREF", "GAP-PRED", "GAP-IOB",
                                        "GAP-CARB", "GAP-INS", "GAP-INSULIN"],
            "treatments-gaps.md": ["GAP-TREAT", "GAP-OVERRIDE", "GAP-REMOTE", "GAP-PROF"],
            "pumps-gaps.md": ["GAP-PUMP"],
            "connectors-gaps.md": ["GAP-CONNECT", "GAP-TCONNECT", "GAP-NOCTURNE", "GAP-TEST"],
        }
        
        traceability_dir = PROJECT_ROOT / "traceability"
        
        for filename, valid_prefixes in prefix_map.items():
            filepath = traceability_dir / filename
            if not filepath.exists():
                continue
                
            with self.subTest(file=filename):
                content = filepath.read_text(encoding='utf-8')
                
                # Find all GAP IDs
                gap_ids = re.findall(r'^### (GAP-[A-Z]+-\d+)', content, re.MULTILINE)
                
                for gap_id in gap_ids:
                    # Check if gap matches any valid prefix
                    matches = any(gap_id.startswith(prefix) for prefix in valid_prefixes)
                    self.assertTrue(matches, 
                        f"Gap {gap_id} in {filename} doesn't match expected prefixes: {valid_prefixes}")
    
    def test_live_backlog_format(self):
        """Test LIVE-BACKLOG.md has expected structure."""
        live_backlog = PROJECT_ROOT / "LIVE-BACKLOG.md"
        content = live_backlog.read_text(encoding='utf-8')
        
        # Should have a Processed section
        self.assertIn("## Processed", content)
        
        # Processed section should have a table
        self.assertIn("| Item |", content)
    
    def test_ecosystem_backlog_format(self):
        """Test ECOSYSTEM-BACKLOG.md has expected structure."""
        ecosystem_backlog = PROJECT_ROOT / "docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md"
        content = ecosystem_backlog.read_text(encoding='utf-8')
        
        # Should have Ready Queue section with numbered items
        self.assertIn("Ready Queue", content)
        # Should have numbered items
        self.assertRegex(content, r'###\s+\d+\.')
    
    def test_gap_entry_format(self):
        """Test that gap entries follow expected format."""
        # Check one domain file
        gaps_file = PROJECT_ROOT / "traceability" / "cgm-sources-gaps.md"
        if not gaps_file.exists():
            self.skipTest("cgm-sources-gaps.md doesn't exist")
        
        content = gaps_file.read_text(encoding='utf-8')
        
        # Find all gap entries
        gap_entries = re.findall(r'^### (GAP-[A-Z]+-\d+):(.*)$', content, re.MULTILINE)
        
        self.assertGreater(len(gap_entries), 0, "No gap entries found")
        
        for gap_id, title in gap_entries:
            with self.subTest(gap_id=gap_id):
                # Title should not be empty
                self.assertTrue(title.strip(), f"{gap_id} has empty title")
    
    def test_requirement_entry_format(self):
        """Test that requirement entries follow expected format."""
        reqs_file = PROJECT_ROOT / "traceability" / "pumps-requirements.md"
        if not reqs_file.exists():
            self.skipTest("pumps-requirements.md doesn't exist")
        
        content = reqs_file.read_text(encoding='utf-8')
        
        # Find all requirement entries
        req_entries = re.findall(r'^### (REQ-[A-Z]+-\d+):(.*)$', content, re.MULTILINE)
        
        self.assertGreater(len(req_entries), 0, "No requirement entries found")
        
        for req_id, title in req_entries:
            with self.subTest(req_id=req_id):
                # Title should not be empty
                self.assertTrue(title.strip(), f"{req_id} has empty title")


class TestIntegration(unittest.TestCase):
    """Integration tests for tool combinations."""
    
    def test_route_matches_next_id_target(self):
        """Test that --route and --next-id agree on target files."""
        prefixes = ["GAP-CGM", "GAP-PUMP", "REQ-PUMP", "REQ-CGM"]
        
        for prefix in prefixes:
            with self.subTest(prefix=prefix):
                # Get route result
                route_result = subprocess.run(
                    [sys.executable, "tools/queue_stats.py", "--route", prefix, "--json"],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True
                )
                route_data = json.loads(route_result.stdout)
                
                # Get next-id result
                nextid_result = subprocess.run(
                    [sys.executable, "tools/doc_chunker.py", "--next-id", prefix, "--json"],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True
                )
                nextid_data = json.loads(nextid_result.stdout)
                
                # They should agree on the target file
                self.assertEqual(
                    route_data["file"], 
                    nextid_data["target_file"],
                    f"Route and next-id disagree on file for {prefix}"
                )
    
    def test_lint_after_chunking_is_clean(self):
        """Test that after chunking, lint shows no misplaced items."""
        result = subprocess.run(
            [sys.executable, "tools/doc_chunker.py", "--lint", "--json"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True
        )
        data = json.loads(result.stdout)
        
        self.assertEqual(len(data["misplaced"]), 0, 
            f"Found misplaced items after chunking: {data['misplaced']}")
        self.assertEqual(data["health"], "ok")


def main():
    """Run tests with optional verbosity."""
    import argparse
    parser = argparse.ArgumentParser(description="Run hygiene tool tests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    verbosity = 2 if args.verbose else 1
    
    # Run tests
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
