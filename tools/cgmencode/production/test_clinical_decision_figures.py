"""Tests for the clinical decision figure generator (matplotlib)."""
from __future__ import annotations

import base64

import numpy as np
import pytest

mpl = pytest.importorskip("matplotlib")

from cgmencode.production.clinical_decision_report import ReportFigure
from cgmencode.production.clinical_decision_figures import (
    build_clinical_figures,
)


def _synthetic(n_days=14):
    """A synthetic 5-min glucose trace with a diurnal pattern."""
    steps = n_days * 288
    t = np.arange(steps)
    hours = (t % 288) / 12.0
    # Baseline 140 + diurnal swing + noise; some lows/highs.
    glucose = (140
               + 35 * np.sin(2 * np.pi * (hours - 4) / 24.0)
               + np.random.default_rng(0).normal(0, 18, steps))
    glucose = np.clip(glucose, 40, 350)
    return glucose, hours


def _is_png_b64(s: str) -> bool:
    raw = base64.b64decode(s)
    return raw[:8] == b"\x89PNG\r\n\x1a\n"


class TestFigureGeneration:
    def test_returns_report_figures(self):
        g, h = _synthetic()
        figs = build_clinical_figures(glucose=g, hours=h)
        assert figs
        assert all(isinstance(f, ReportFigure) for f in figs)

    def test_figures_have_valid_png(self):
        g, h = _synthetic()
        figs = build_clinical_figures(glucose=g, hours=h)
        for f in figs:
            assert f.png_base64
            assert _is_png_b64(f.png_base64)

    def test_sections_present(self):
        g, h = _synthetic()
        figs = build_clinical_figures(glucose=g, hours=h)
        sections = {f.section for f in figs}
        assert "insulin_sufficiency" in sections   # TIR distribution
        assert "overview" in sections              # AGP
        assert "basal" in sections                 # overnight

    def test_each_figure_has_caption_and_filename(self):
        g, h = _synthetic()
        figs = build_clinical_figures(glucose=g, hours=h)
        for f in figs:
            assert f.caption
            assert f.filename.endswith(".png")

    def test_tir_bar_works_without_hours(self):
        g, _ = _synthetic()
        figs = build_clinical_figures(glucose=g, hours=None)
        sections = {f.section for f in figs}
        # TIR distribution needs no hours; AGP/overnight need hours.
        assert "insulin_sufficiency" in sections
        assert "overview" not in sections

    def test_handles_short_array_gracefully(self):
        g = np.array([120.0, 130.0, 110.0])
        figs = build_clinical_figures(glucose=g, hours=None)
        # Should not raise; may produce just the TIR bar or nothing.
        assert isinstance(figs, list)

    def test_handles_all_nan(self):
        g = np.full(288, np.nan)
        figs = build_clinical_figures(glucose=g, hours=None)
        assert isinstance(figs, list)
