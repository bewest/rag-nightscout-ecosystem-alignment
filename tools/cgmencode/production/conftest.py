"""Pytest configuration for production test suite.

Markers (applied via class-level ``pytestmark = pytest.mark.<name>``):
    unit         — 392 tests that do not invoke ``run_pipeline`` (~35 s total)
    integration  — 56 tests that exercise ``run_pipeline`` end-to-end (~112 s)

Usage:
    pytest -m unit        # Fast CI / inner-loop iteration (~35 s)
    pytest -m integration # Pipeline regressions only (~112 s)
    pytest                # Full suite (~150 s)

Coverage is enforced via the marker classification in test_production.py.
The boundary is whether the class imports ``cgmencode.production.pipeline``
helpers (run_pipeline / run_pipeline_batch). Add new test classes with
the appropriate ``pytestmark`` attribute right after the class signature.
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast tests (no pipeline)")
    config.addinivalue_line("markers", "integration: pipeline integration tests")
