#!/usr/bin/env python3
"""
Unit tests for hygiene tools with synthetic test fixtures.

These tests validate the parsing logic in isolation using mock data,
independent of actual project files.

Usage:
    python tools/test_hygiene_tools_unit.py              # Run all tests
    python tools/test_hygiene_tools_unit.py -v           # Verbose output
    python -m pytest tools/test_hygiene_tools_unit.py   # With pytest

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
from unittest.mock import patch, MagicMock

# Get project root and add tools to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))


# =============================================================================
# Unit Tests for queue_stats.py parsing logic
# =============================================================================

class TestQueueStatsParsing(unittest.TestCase):
    """Unit tests for queue_stats.py parsing functions."""
    
    def test_parse_live_backlog_pending_bullets(self):
        """Test counting pending bullet points before ## Processed."""
        content = """# LIVE-BACKLOG

Human requests go here.

* First pending item
* Second pending item
* Third pending item

## Processed

| Item | Priority | Status | Date |
|------|----------|--------|------|
| Done item | P1 | ✅ | 2026-01-28 |
"""
        # Simulate the parsing logic
        match = re.search(r'^(.*?)^## Processed', content, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        header_section = match.group(1)
        count = len(re.findall(r'^\s*\* ', header_section, re.MULTILINE))
        self.assertEqual(count, 3)
    
    def test_parse_live_backlog_no_pending(self):
        """Test counting when no pending items exist."""
        content = """# LIVE-BACKLOG

## Processed

| Item | Priority | Status | Date |
|------|----------|--------|------|
| Done item | P1 | ✅ | 2026-01-28 |
"""
        match = re.search(r'^(.*?)^## Processed', content, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        header_section = match.group(1)
        count = len(re.findall(r'^\s*\* ', header_section, re.MULTILINE))
        self.assertEqual(count, 0)
    
    def test_parse_processed_table_rows(self):
        """Test counting processed table rows."""
        content = """## Processed

| Item | Priority | Status | Date |
|------|----------|--------|------|
| Item 1 | P1 | ✅ | 2026-01-28 |
| Item 2 | P2 | ✅ | 2026-01-27 |
| Item 3 | P0 | → Queued | 2026-01-26 |

## Other Section
"""
        match = re.search(r'^## Processed\s*\n(.*?)(?=^##|\Z)', content, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        table_section = match.group(1)
        rows = re.findall(r'^\|[^-].*\|$', table_section, re.MULTILINE)
        count = max(0, len(rows) - 1)  # Subtract header
        self.assertEqual(count, 3)
    
    def test_parse_ready_queue_numbered_items(self):
        """Test counting Ready Queue numbered items."""
        content = """# ECOSYSTEM-BACKLOG

## Ready Queue (5-10 items)

### 1. First task
Description here.

### 2. Second task
More description.

### 3. Third task
Even more.

## Backlog
"""
        match = re.search(r'^## Ready Queue.*?\n(.*?)(?=^## |\Z)', content, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        queue_section = match.group(1)
        count = len(re.findall(r'^### \d+\.', queue_section, re.MULTILINE))
        self.assertEqual(count, 3)
    
    def test_parse_ready_queue_empty(self):
        """Test Ready Queue with no items."""
        content = """# ECOSYSTEM-BACKLOG

## Ready Queue (5-10 items)

*Queue is empty*

## Backlog
"""
        match = re.search(r'^## Ready Queue.*?\n(.*?)(?=^## |\Z)', content, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        queue_section = match.group(1)
        count = len(re.findall(r'^### \d+\.', queue_section, re.MULTILINE))
        self.assertEqual(count, 0)


class TestQueueStatsRouting(unittest.TestCase):
    """Unit tests for queue_stats.py --route logic."""
    
    def test_route_gap_prefixes(self):
        """Test GAP prefix to domain mapping."""
        # Import the route function
        from queue_stats import route_prefix
        
        test_cases = [
            ("GAP-CGM", "cgm-sources", True),
            ("GAP-CGM-001", "cgm-sources", True),
            ("GAP-G7", "cgm-sources", True),
            ("GAP-LIBRE", "cgm-sources", True),
            ("GAP-SYNC", "sync-identity", True),
            ("GAP-BATCH", "sync-identity", True),
            ("GAP-API", "nightscout-api", True),
            ("GAP-AUTH", "nightscout-api", True),
            ("GAP-ALG", "aid-algorithms", True),
            ("GAP-TREAT", "treatments", True),
            ("GAP-PUMP", "pumps", True),
            ("GAP-UNKNOWN", "other", False),
        ]
        
        for prefix, expected_domain, should_find in test_cases:
            with self.subTest(prefix=prefix):
                result = route_prefix(prefix)
                self.assertEqual(result["found"], should_find)
                if should_find:
                    self.assertEqual(result["domain"], expected_domain)
    
    def test_route_req_prefixes(self):
        """Test REQ prefix to domain mapping."""
        from queue_stats import route_prefix
        
        test_cases = [
            ("REQ-PUMP", "pumps-requirements.md"),
            ("REQ-CGM", "cgm-sources-requirements.md"),
            ("REQ-SYNC", "sync-identity-requirements.md"),
        ]
        
        for prefix, expected_file in test_cases:
            with self.subTest(prefix=prefix):
                result = route_prefix(prefix)
                self.assertIn(expected_file, result["file"])
    
    def test_route_invalid_prefix(self):
        """Test invalid prefix handling."""
        from queue_stats import route_prefix
        
        result = route_prefix("INVALID-123")
        self.assertFalse(result["found"])
        self.assertIn("error", result)


# =============================================================================
# Unit Tests for doc_chunker.py parsing logic
# =============================================================================

class TestDocChunkerGapParsing(unittest.TestCase):
    """Unit tests for doc_chunker.py gap parsing."""
    
    def test_parse_gap_entries(self):
        """Test parsing GAP entries from content."""
        content = """# Gaps

### GAP-CGM-001: First gap title

Description of first gap.

**Impact**: Something.

---

### GAP-CGM-002: Second gap

Another description.

---

### GAP-SYNC-001: Sync gap

Different domain.
"""
        pattern = r'^### (GAP-[A-Z]+-\d+):?\s*(.*)$'
        matches = re.findall(pattern, content, re.MULTILINE)
        
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0][0], "GAP-CGM-001")
        self.assertEqual(matches[0][1], "First gap title")
        self.assertEqual(matches[1][0], "GAP-CGM-002")
        self.assertEqual(matches[2][0], "GAP-SYNC-001")
    
    def test_parse_gap_full_content(self):
        """Test extracting full gap content including body."""
        content = """### GAP-CGM-001: Test Gap

**Description**: This is a test.

**Impact**: Testing.

---

### GAP-CGM-002: Another Gap
"""
        pattern = r'^(### GAP-[A-Z]+-\d+:.+?)(?=^### GAP-|\Z)'
        matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
        
        self.assertEqual(len(matches), 2)
        self.assertIn("Description", matches[0])
        self.assertIn("Impact", matches[0])
    
    def test_gap_domain_mapping(self):
        """Test mapping GAP IDs to domains."""
        from doc_chunker import GAP_DOMAIN_MAP
        
        # Verify key prefixes exist
        self.assertIn("cgm-sources", GAP_DOMAIN_MAP)
        self.assertIn("sync-identity", GAP_DOMAIN_MAP)
        self.assertIn("nightscout-api", GAP_DOMAIN_MAP)
        
        # Verify CGM prefixes
        self.assertIn("GAP-CGM", GAP_DOMAIN_MAP["cgm-sources"])
        self.assertIn("GAP-G7", GAP_DOMAIN_MAP["cgm-sources"])
        self.assertIn("GAP-LIBRE", GAP_DOMAIN_MAP["cgm-sources"])


class TestDocChunkerReqParsing(unittest.TestCase):
    """Unit tests for doc_chunker.py requirement parsing."""
    
    def test_parse_req_entries(self):
        """Test parsing REQ entries from content."""
        content = """# Requirements

### REQ-PUMP-001: First requirement

Statement here.

---

### REQ-PUMP-002: Second requirement

Another statement.

---

### REQ-CGM-001: CGM requirement

Different domain.
"""
        pattern = r'^### (REQ-[A-Z]+-\d+):?\s*(.*)$'
        matches = re.findall(pattern, content, re.MULTILINE)
        
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0][0], "REQ-PUMP-001")
        self.assertEqual(matches[1][0], "REQ-PUMP-002")
        self.assertEqual(matches[2][0], "REQ-CGM-001")
    
    def test_req_prefix_groups(self):
        """Test REQ prefix groupings."""
        from doc_chunker import REQ_PREFIX_GROUPS
        
        # Verify key groups exist
        self.assertIn("cgm-sources", REQ_PREFIX_GROUPS)
        self.assertIn("pumps", REQ_PREFIX_GROUPS)
        self.assertIn("treatments", REQ_PREFIX_GROUPS)
        
        # Verify pump prefix
        self.assertIn("pump", REQ_PREFIX_GROUPS["pumps"])


class TestDocChunkerNextId(unittest.TestCase):
    """Unit tests for doc_chunker.py --next-id logic."""
    
    def test_next_id_increments(self):
        """Test that next ID is max + 1."""
        from doc_chunker import get_next_id
        
        # This test runs against real files
        result = get_next_id("GAP-CGM")
        
        self.assertIn("next_id", result)
        self.assertIn("next_number", result)
        self.assertIn("target_file", result)
        
        # Next number should be > 0
        self.assertGreater(result["next_number"], 0)
        
        # ID should match format
        self.assertRegex(result["next_id"], r"GAP-CGM-\d{3}")
    
    def test_next_id_target_file(self):
        """Test that target file matches domain."""
        from doc_chunker import get_next_id
        
        test_cases = [
            ("GAP-CGM", "cgm-sources-gaps.md"),
            ("GAP-SYNC", "sync-identity-gaps.md"),
            ("REQ-PUMP", "pumps-requirements.md"),
        ]
        
        for prefix, expected_file in test_cases:
            with self.subTest(prefix=prefix):
                result = get_next_id(prefix)
                self.assertIn(expected_file, result["target_file"])


class TestDocChunkerLint(unittest.TestCase):
    """Unit tests for doc_chunker.py --lint logic."""
    
    def test_lint_detects_misplaced_gap(self):
        """Test that lint would detect a misplaced gap."""
        # Simulate checking if GAP-SYNC-001 is in cgm-sources-gaps.md
        gap_id = "GAP-SYNC-001"
        file_domain = "cgm-sources"
        
        from doc_chunker import GAP_DOMAIN_MAP
        
        # Find correct domain for this gap
        correct_domain = None
        for domain, prefixes in GAP_DOMAIN_MAP.items():
            for prefix in prefixes:
                if gap_id.startswith(prefix):
                    correct_domain = domain
                    break
        
        # SYNC gaps should NOT be in cgm-sources
        self.assertEqual(correct_domain, "sync-identity")
        self.assertNotEqual(correct_domain, file_domain)
    
    def test_lint_accepts_correct_placement(self):
        """Test that lint accepts correctly placed gaps."""
        gap_id = "GAP-CGM-001"
        file_domain = "cgm-sources"
        
        from doc_chunker import GAP_DOMAIN_MAP
        
        correct_domain = None
        for domain, prefixes in GAP_DOMAIN_MAP.items():
            for prefix in prefixes:
                if gap_id.startswith(prefix):
                    correct_domain = domain
                    break
        
        self.assertEqual(correct_domain, file_domain)


# =============================================================================
# Unit Tests for Progress File Parsing
# =============================================================================

class TestProgressParsing(unittest.TestCase):
    """Unit tests for progress.md parsing."""
    
    def test_parse_progress_entries(self):
        """Test parsing progress entries with dates."""
        content = """# Progress

### Component A (2026-01-28)

Did some work.

| Deliverable | Location |
|-------------|----------|
| Doc | docs/a.md |

---

### Component B (2026-01-27)

More work.

---

### Component C (2026-01-15)

Earlier work.
"""
        pattern = r'^### (.+?)\s*\((\d{4}-\d{2}-\d{2})\)$'
        matches = re.findall(pattern, content, re.MULTILINE)
        
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0][0], "Component A")
        self.assertEqual(matches[0][1], "2026-01-28")
        self.assertEqual(matches[1][1], "2026-01-27")
    
    def test_group_by_month(self):
        """Test grouping progress entries by month."""
        entries = [
            ("A", "2026-01-28"),
            ("B", "2026-01-15"),
            ("C", "2025-12-20"),
            ("D", "2025-12-10"),
        ]
        
        by_month = {}
        for title, date in entries:
            month = date[:7]
            if month not in by_month:
                by_month[month] = []
            by_month[month].append(title)
        
        self.assertEqual(len(by_month["2026-01"]), 2)
        self.assertEqual(len(by_month["2025-12"]), 2)


# =============================================================================
# Unit Tests with Temp Files
# =============================================================================

class TestWithTempFiles(unittest.TestCase):
    """Unit tests using temporary files."""
    
    def setUp(self):
        """Create temp directory for test files."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
    
    def tearDown(self):
        """Clean up temp directory."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_count_lines_empty_file(self):
        """Test counting lines in empty file."""
        empty_file = Path(self.temp_dir) / "empty.md"
        empty_file.write_text("")
        
        count = sum(1 for _ in open(empty_file))
        self.assertEqual(count, 0)
    
    def test_count_lines_with_content(self):
        """Test counting lines in file with content."""
        test_file = Path(self.temp_dir) / "test.md"
        test_file.write_text("line 1\nline 2\nline 3\n")
        
        count = sum(1 for _ in open(test_file))
        self.assertEqual(count, 3)
    
    def test_parse_gaps_from_temp_file(self):
        """Test parsing gaps from a temp file."""
        gaps_file = Path(self.temp_dir) / "gaps.md"
        gaps_file.write_text("""# Test Gaps

### GAP-TEST-001: Test gap one

Description.

---

### GAP-TEST-002: Test gap two

Another.
""")
        
        content = gaps_file.read_text()
        pattern = r'^### (GAP-[A-Z]+-\d+)'
        matches = re.findall(pattern, content, re.MULTILINE)
        
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0], "GAP-TEST-001")
        self.assertEqual(matches[1], "GAP-TEST-002")


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""
    
    def test_gap_id_with_long_number(self):
        """Test parsing GAP ID with 4+ digit number."""
        content = "### GAP-CGM-1234: Long numbered gap"
        pattern = r'^### (GAP-[A-Z]+-\d+):?\s*(.*)$'
        match = re.search(pattern, content, re.MULTILINE)
        
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "GAP-CGM-1234")
    
    def test_gap_title_with_colon(self):
        """Test parsing GAP with colon in title."""
        content = "### GAP-API-001: API Error: 500 handling"
        pattern = r'^### (GAP-[A-Z]+-\d+):?\s*(.*)$'
        match = re.search(pattern, content, re.MULTILINE)
        
        self.assertIsNotNone(match)
        self.assertEqual(match.group(2), "API Error: 500 handling")
    
    def test_gap_without_colon_separator(self):
        """Test parsing GAP without colon after ID."""
        content = "### GAP-CGM-001 Gap without colon"
        pattern = r'^### (GAP-[A-Z]+-\d+):?\s*(.*)$'
        match = re.search(pattern, content, re.MULTILINE)
        
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "GAP-CGM-001")
    
    def test_malformed_gap_id_rejected(self):
        """Test that malformed GAP IDs are not matched."""
        bad_content = [
            "### GAP-123: Missing prefix",
            "### GAP-cgm-001: Lowercase prefix",
            "### GAP-CGM: Missing number",
            "### GAP CGM 001: Spaces instead of dashes",
        ]
        
        pattern = r'^### (GAP-[A-Z]+-\d+):?\s*(.*)$'
        
        for content in bad_content:
            with self.subTest(content=content):
                match = re.search(pattern, content, re.MULTILINE)
                self.assertIsNone(match, f"Should not match: {content}")
    
    def test_empty_processed_table(self):
        """Test handling empty processed table."""
        content = """## Processed

| Item | Priority | Status | Date |
|------|----------|--------|------|

## Next Section
"""
        match = re.search(r'^## Processed\s*\n(.*?)(?=^##|\Z)', content, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        table_section = match.group(1)
        rows = re.findall(r'^\|[^-].*\|$', table_section, re.MULTILINE)
        count = max(0, len(rows) - 1)
        self.assertEqual(count, 0)
    
    def test_unicode_in_titles(self):
        """Test handling Unicode characters in titles."""
        content = "### GAP-UI-001: Missing emoji support 🔥"
        pattern = r'^### (GAP-[A-Z]+-\d+):?\s*(.*)$'
        match = re.search(pattern, content, re.MULTILINE)
        
        self.assertIsNotNone(match)
        self.assertIn("🔥", match.group(2))


def main():
    """Run tests with optional verbosity."""
    import argparse
    parser = argparse.ArgumentParser(description="Run hygiene tool unit tests")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    verbosity = 2 if args.verbose else 1
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
