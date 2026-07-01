"""Unit tests for action_label_benchmark_figures.py."""
from __future__ import annotations

import pytest

matplotlib = pytest.importorskip("matplotlib")

from tools.cgmencode.production.action_label_benchmark_figures import (
    plot_action_label_benchmark,
)

_TWO_METHOD_SUMMARY = {
    "n_windows": 303,
    "n_patients": 27,
    "coverage_facts_loader": 0.327,
    "coverage_direct_advisor": 1.0,
    "n_both_covered": 99,
    "agreement_where_both_covered": 0.616,
    "persistence_facts_loader": 0.656,
    "persistence_direct_advisor": 0.729,
}

_SINGLE_METHOD_SUMMARY = {
    "n_windows": 135,
    "n_patients": 27,
    "coverage_direct_advisor": 1.0,
    "persistence_direct_advisor": 0.712,
}


def test_plot_two_method_benchmark_saves_file(tmp_path):
    out = tmp_path / "basal.png"
    result = plot_action_label_benchmark(
        _TWO_METHOD_SUMMARY, "Basal benchmark",
        "facts_loader", "direct_advisor", out,
    )
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0


def test_plot_single_method_benchmark_saves_file(tmp_path):
    out = tmp_path / "cr.png"
    result = plot_action_label_benchmark(
        _SINGLE_METHOD_SUMMARY, "CR benchmark",
        "direct_advisor", "", out, single_method=True,
    )
    assert result == out
    assert out.exists()


def test_plot_empty_summary_returns_none(tmp_path):
    out = tmp_path / "empty.png"
    result = plot_action_label_benchmark({"n_windows": 0}, "Empty", "a", "b", out)
    assert result is None
    assert not out.exists()


def test_plot_creates_parent_directories(tmp_path):
    out = tmp_path / "nested" / "dir" / "isf.png"
    result = plot_action_label_benchmark(
        _TWO_METHOD_SUMMARY, "ISF benchmark", "facts_loader", "direct_advisor", out,
    )
    assert result == out
    assert out.exists()
