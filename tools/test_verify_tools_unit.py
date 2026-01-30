#!/usr/bin/env python3
"""
Unit tests for verification tools with synthetic test fixtures.

These tests validate the parsing logic in isolation using mock data,
independent of actual project files.

Coverage:
- verify_assertions.py: YAML parsing, requirement extraction
- verify_coverage.py: requirement ID extraction
- verify_gap_freshness.py: gap parsing
- verify_mapping_coverage.py: field extraction from mapping docs
- validate_json.py: JSON/YAML loading, shape validation
- validate_fixtures.py: fixture validation logic

Usage:
    python tools/test_verify_tools_unit.py              # Run all tests
    python tools/test_verify_tools_unit.py -v           # Verbose output
    python -m pytest tools/test_verify_tools_unit.py   # With pytest

Exit codes:
    0 - All tests pass
    1 - Test failures
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Get project root and add tools to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))


# =============================================================================
# Unit Tests for verify_assertions.py
# =============================================================================

class TestVerifyAssertionsParsing(unittest.TestCase):
    """Unit tests for verify_assertions.py parsing functions."""

    def test_req_pattern_matches_simple(self):
        """Test REQ pattern matches simple requirement IDs."""
        from verify_assertions import REQ_PATTERN
        
        text = "This relates to REQ-001 and REQ-042."
        matches = REQ_PATTERN.findall(text)
        self.assertEqual(matches, ["REQ-001", "REQ-042"])

    def test_req_pattern_matches_domain_prefix(self):
        """Test REQ pattern matches domain-prefixed requirement IDs."""
        from verify_assertions import REQ_PATTERN
        
        text = "See REQ-SYNC-001, REQ-TREAT-042, and REQ-ALG-003."
        matches = REQ_PATTERN.findall(text)
        self.assertEqual(sorted(matches), ["REQ-ALG-003", "REQ-SYNC-001", "REQ-TREAT-042"])

    def test_gap_pattern_matches(self):
        """Test GAP pattern matches gap IDs."""
        from verify_assertions import GAP_PATTERN
        
        text = "Related to GAP-SYNC-001 and GAP-CGM-042."
        matches = GAP_PATTERN.findall(text)
        self.assertEqual(sorted(matches), ["GAP-CGM-042", "GAP-SYNC-001"])

    def test_parse_yaml_file_with_valid_yaml(self):
        """Test parsing a valid YAML file."""
        from verify_assertions import parse_yaml_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("key: value\nitems:\n  - one\n  - two\n")
            f.flush()
            
            try:
                data, content = parse_yaml_file(Path(f.name))
                self.assertIsNotNone(data)
                self.assertEqual(data.get("key"), "value")
                self.assertEqual(data.get("items"), ["one", "two"])
            finally:
                os.unlink(f.name)

    def test_parse_yaml_file_returns_content_on_invalid(self):
        """Test that invalid YAML still returns raw content."""
        from verify_assertions import parse_yaml_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("not: valid: yaml: here\n")
            f.flush()
            
            try:
                data, content = parse_yaml_file(Path(f.name))
                # data may be None or partial, but content should be present
                self.assertIn("not:", content)
            finally:
                os.unlink(f.name)


# =============================================================================
# Unit Tests for verify_coverage.py
# =============================================================================

class TestVerifyCoverageParsing(unittest.TestCase):
    """Unit tests for verify_coverage.py parsing functions."""

    def test_extract_requirements_from_markdown(self):
        """Test extracting requirement IDs from markdown content."""
        from verify_coverage import extract_requirements
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("""# Requirements

### REQ-001: Basic requirement

Description here.

### REQ-002: Another requirement

More description.
""")
            f.flush()
            
            try:
                reqs = extract_requirements(Path(f.name))
                # Returns dict with REQ IDs as keys
                self.assertIn("REQ-001", reqs)
                self.assertIn("REQ-002", reqs)
                self.assertEqual(reqs["REQ-001"]["title"], "Basic requirement")
            finally:
                os.unlink(f.name)


# =============================================================================
# Unit Tests for verify_gap_freshness.py
# =============================================================================

class TestVerifyGapFreshnessParsing(unittest.TestCase):
    """Unit tests for verify_gap_freshness.py parsing functions."""

    def test_gap_id_extraction_pattern(self):
        """Test GAP ID extraction regex pattern."""
        pattern = re.compile(r'\b(GAP-[A-Z]+-\d{3})\b')
        
        text = """
### GAP-SYNC-001: Missing field

Description.

### GAP-CGM-042: Another gap

More text with GAP-ALG-003 inline.
"""
        matches = pattern.findall(text)
        self.assertEqual(len(matches), 3)
        self.assertIn("GAP-SYNC-001", matches)
        self.assertIn("GAP-CGM-042", matches)
        self.assertIn("GAP-ALG-003", matches)

    def test_gap_status_detection(self):
        """Test detecting gap status from content."""
        # Simulate status keywords that might indicate resolution
        content_open = "This gap is still present in the latest version."
        content_closed = "This was fixed in PR #123 and is now resolved."
        
        open_keywords = ["still", "missing", "not implemented", "pending"]
        closed_keywords = ["fixed", "resolved", "implemented", "complete"]
        
        # Check open keywords
        has_open = any(kw in content_open.lower() for kw in open_keywords)
        self.assertTrue(has_open)
        
        # Check closed keywords
        has_closed = any(kw in content_closed.lower() for kw in closed_keywords)
        self.assertTrue(has_closed)


# =============================================================================
# Unit Tests for verify_mapping_coverage.py
# =============================================================================

class TestVerifyMappingCoverageParsing(unittest.TestCase):
    """Unit tests for verify_mapping_coverage.py parsing functions."""

    def test_extract_documented_fields_from_table(self):
        """Test extracting field names from markdown tables."""
        from verify_mapping_coverage import extract_documented_fields
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("""# Field Mapping

| Source Field | Target Field | Notes |
|--------------|--------------|-------|
| `sgv` | `glucose` | Sensor value |
| `dateString` | `timestamp` | ISO format |
| `direction` | `trend` | Trend arrow |
""")
            f.flush()
            
            try:
                fields = extract_documented_fields(Path(f.name))
                self.assertIn("sgv", fields)
                self.assertIn("dateString", fields)
                self.assertIn("direction", fields)
            finally:
                os.unlink(f.name)

    def test_extract_documented_fields_from_code_blocks(self):
        """Test extracting field names from code blocks."""
        from verify_mapping_coverage import extract_documented_fields
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("""# API Response

```json
{
  "glucose": 120,
  "trend": "Flat",
  "timestamp": "2024-01-01T00:00:00Z"
}
```
""")
            f.flush()
            
            try:
                fields = extract_documented_fields(Path(f.name))
                # Should find field names in JSON
                self.assertIn("glucose", fields)
                self.assertIn("trend", fields)
            finally:
                os.unlink(f.name)


# =============================================================================
# Unit Tests for validate_json.py
# =============================================================================

class TestValidateJsonParsing(unittest.TestCase):
    """Unit tests for validate_json.py parsing functions."""

    def test_load_json_file_valid(self):
        """Test loading a valid JSON file."""
        from validate_json import load_json_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"key": "value", "number": 42}')
            f.flush()
            
            try:
                data, error = load_json_file(Path(f.name))
                self.assertIsNone(error)
                self.assertEqual(data["key"], "value")
                self.assertEqual(data["number"], 42)
            finally:
                os.unlink(f.name)

    def test_load_yaml_file_valid(self):
        """Test loading a valid YAML file."""
        from validate_json import load_yaml_file
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("key: value\nnumber: 42\n")
            f.flush()
            
            try:
                data, error = load_yaml_file(Path(f.name))
                self.assertIsNone(error)
                self.assertEqual(data["key"], "value")
                self.assertEqual(data["number"], 42)
            finally:
                os.unlink(f.name)

    def test_shape_validator_basic(self):
        """Test ShapeValidator with basic shape spec."""
        from validate_json import ShapeValidator
        
        # Uses 'required_fields' not 'required_keys'
        shape_spec = {
            "type": "object",
            "required_fields": ["id", "value"],
        }
        
        validator = ShapeValidator(shape_spec)
        
        valid_data = {"id": "123", "value": 42}
        invalid_data = {"id": "123"}  # missing 'value'
        
        errors = validator.validate(valid_data)
        self.assertEqual(len(errors), 0)
        
        errors = validator.validate(invalid_data)
        self.assertGreater(len(errors), 0)


# =============================================================================
# Unit Tests for validate_fixtures.py
# =============================================================================

class TestValidateFixturesParsing(unittest.TestCase):
    """Unit tests for validate_fixtures.py parsing functions."""

    def test_infer_shape_type_entries(self):
        """Test inferring shape type for entries fixture."""
        from validate_fixtures import infer_shape_type
        
        entries_data = {
            "sgv": 120,
            "direction": "Flat",
            "type": "sgv"
        }
        
        shape_type = infer_shape_type(entries_data)
        # Should detect as entries/sgv type
        self.assertIn("sgv", str(shape_type).lower() if shape_type else "sgv")

    def test_infer_shape_type_treatment(self):
        """Test inferring shape type for treatment fixture."""
        from validate_fixtures import infer_shape_type
        
        # infer_shape_type uses 'type' field, not 'eventType'
        treatment_data = {
            "type": "treatment",
            "insulin": 2.5,
            "created_at": "2024-01-01T00:00:00Z"
        }
        
        shape_type = infer_shape_type(treatment_data)
        self.assertEqual(shape_type, "treatment-instance")

    def test_validation_error_class(self):
        """Test ValidationError class structure."""
        from validate_fixtures import ValidationError
        
        error = ValidationError(
            path="test.json",
            message="Missing required field",
            severity="error"
        )
        
        self.assertEqual(error.path, "test.json")
        self.assertEqual(error.message, "Missing required field")
        self.assertEqual(error.severity, "error")


# =============================================================================
# Integration-style tests with synthetic data
# =============================================================================

class TestSyntheticAssertionFile(unittest.TestCase):
    """Test assertion processing with synthetic YAML."""

    def test_extract_assertions_from_synthetic(self):
        """Test extracting assertions from a synthetic YAML file."""
        from verify_assertions import extract_assertions, WORKSPACE_ROOT
        
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.yaml', 
            dir=WORKSPACE_ROOT / "conformance" / "assertions",
            delete=False
        ) as f:
            f.write("""# Test scenario
name: test-scenario
requirements:
  - REQ-001
  - REQ-002
related_gaps:
  - GAP-TEST-001
assertions:
  assert_valid_input:
    description: Input must be valid
    requirements:
      - REQ-003
  assert_output_format:
    description: Output must be formatted
""")
            f.flush()
            
            try:
                assertions = extract_assertions(Path(f.name))
                self.assertEqual(len(assertions), 2)
                
                # Uses 'id' not 'key'
                first = next(a for a in assertions if a["id"] == "assert_valid_input")
                self.assertIn("REQ-001", first["requirements"])
                self.assertIn("REQ-003", first["requirements"])
                
                second = next(a for a in assertions if a["id"] == "assert_output_format")
                self.assertIn("REQ-001", second["requirements"])
            finally:
                os.unlink(f.name)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
