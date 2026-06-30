"""Tests for the clinical decision figure generator (matplotlib)."""
from __future__ import annotations

import base64

import numpy as np
import pytest

mpl = pytest.importorskip("matplotlib")

from cgmencode.production.clinical_decision_report import ReportFigure
from cgmencode.production.clinical_decision_figures import (
    build_clinical_figures,
    DomainContext,
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


def _synthetic_with_events(n_days=21):
    """Synthetic trace with correction boluses and meals for domain figs."""
    steps = n_days * 288
    rng = np.random.default_rng(1)
    hours = (np.arange(steps) % 288) / 12.0
    glucose = (150
               + 30 * np.sin(2 * np.pi * (hours - 4) / 24.0)
               + rng.normal(0, 15, steps))
    bolus = np.zeros(steps)
    carbs = np.zeros(steps)
    # Meals at ~8h, 13h, 19h each day with boluses.
    for day in range(n_days):
        base = day * 288
        for meal_h, g in ((8, 45.0), (13, 60.0), (19, 50.0)):
            idx = base + meal_h * 12
            if idx + 48 < steps:
                carbs[idx] = g
                bolus[idx] = g / 10.0
                glucose[idx:idx + 18] += np.linspace(0, 70, 18)  # excursion
        # A correction bolus mid-afternoon when high.
        cidx = base + 16 * 12
        if cidx + 24 < steps:
            glucose[cidx] = 230.0
            bolus[cidx] = 3.0
            glucose[cidx + 6:cidx + 24] -= np.linspace(0, 90, 18)
    glucose = np.clip(glucose, 40, 360)
    return glucose, hours, bolus, carbs


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


class TestDomainFigures:
    def test_cr_excursion_figure_generated(self):
        g, h, b, c = _synthetic_with_events()
        ctx = {"cr": DomainContext(
            domain="cr", current=10.0, theoretical=8.0,
            direction="decrease")}
        figs = build_clinical_figures(
            glucose=g, hours=h, bolus=b, carbs=c, domains=ctx)
        cr_figs = [f for f in figs if f.section == "cr"]
        assert cr_figs
        assert _is_png_b64(cr_figs[0].png_base64)

    def test_cr_excursion_caption_mentions_direction(self):
        g, h, b, c = _synthetic_with_events()
        ctx = {"cr": DomainContext(
            domain="cr", current=10.0, theoretical=8.0,
            direction="decrease")}
        figs = build_clinical_figures(
            glucose=g, hours=h, bolus=b, carbs=c, domains=ctx)
        cr = [f for f in figs if f.section == "cr"][0]
        assert "8" in cr.caption  # theoretical target referenced

    def test_no_cr_figure_without_meals(self):
        g, h = _synthetic()
        figs = build_clinical_figures(
            glucose=g, hours=h, bolus=None, carbs=None)
        assert not [f for f in figs if f.section == "cr"]


class TestFigureFromFile:
    def test_attaches_existing_png(self, tmp_path):
        from cgmencode.production.clinical_decision_figures import (
            figure_from_file,
        )
        # Write a minimal valid PNG.
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42m"
            "NkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
        p = tmp_path / "03_isf_reconciliation.png"
        p.write_bytes(png)
        fig = figure_from_file(
            str(p), section="isf", title="ISF reconciliation",
            caption="Profile vs observed ISF.")
        assert isinstance(fig, ReportFigure)
        assert fig.section == "isf"
        assert _is_png_b64(fig.png_base64)
        assert fig.filename == "03_isf_reconciliation.png"

    def test_missing_file_returns_none(self):
        from cgmencode.production.clinical_decision_figures import (
            figure_from_file,
        )
        assert figure_from_file(
            "/nonexistent/x.png", section="isf", title="t",
            caption="c") is None

