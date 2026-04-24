"""Pytest configuration for production test suite.

Markers:
    unit         — fast tests, no `run_pipeline` (~30-60 s).
    integration  — full pipeline / waterfall regressions (~3-5 min).

Tests pick up a marker either by:
  1. Explicit class-level ``pytestmark = pytest.mark.<name>`` (preferred
     for the long heterogeneous ``test_production.py`` /
     ``test_audition_matrix.py`` files where unit and integration classes
     coexist), OR
  2. The filename-based default applied by ``pytest_collection_modifyitems``
     below: any test in a file listed in ``_INTEGRATION_FILES`` defaults
     to ``integration``; everything else without a marker defaults to
     ``unit``.

Usage:
    pytest -m unit          # Fast CI / inner-loop iteration
    pytest -m integration   # Pipeline regressions only
    pytest                  # Full suite

Add new test files / classes:
  * Pure unit tests → no marker required (filename default catches it).
  * New pipeline-style integration files → add the basename to
    ``_INTEGRATION_FILES`` below.
"""
import os

import pytest


# Files whose tests are always integration-class. Anything else without
# an explicit class-level pytestmark falls into the unit bucket.
_INTEGRATION_FILES = frozenset({
    "test_integration.py",
    "test_waterfall_integration.py",
})


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast tests (no pipeline)")
    config.addinivalue_line(
        "markers", "integration: pipeline integration tests")


def pytest_collection_modifyitems(config, items):
    """Apply default markers based on the test's source file.

    Skips items that already have an explicit unit/integration marker
    from a class-level ``pytestmark`` so the existing manual taxonomy
    in ``test_production.py`` continues to win.
    """
    for item in items:
        existing = {m.name for m in item.iter_markers()}
        if "unit" in existing or "integration" in existing:
            continue
        fname = os.path.basename(str(item.fspath))
        if fname in _INTEGRATION_FILES:
            item.add_marker(pytest.mark.integration)
        else:
            item.add_marker(pytest.mark.unit)
