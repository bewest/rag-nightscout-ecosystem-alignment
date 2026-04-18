"""Pytest configuration for production test suite.

Markers:
    unit: Fast tests that don't call run_pipeline (~35s total)
    integration: Tests that call run_pipeline (~160s total)

Usage:
    pytest -m unit        # Fast iteration (35s)
    pytest -m integration # Pipeline tests only (~160s)
    pytest                # All tests (~196s)
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: fast tests (no pipeline)")
    config.addinivalue_line("markers", "integration: pipeline integration tests")
