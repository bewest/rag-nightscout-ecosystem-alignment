"""Tests for report-figure contract and renderer embedding.

These exercise the figure data contract and how figures are embedded in
HTML/markdown WITHOUT requiring matplotlib (figures are constructed with
stub base64 payloads). The actual data->figure generation is tested in
test_clinical_decision_figures.py.
"""
from __future__ import annotations

import json

from cgmencode.production.clinical_decision_report import (
    build_clinical_decision_report,
    ReportFigure,
)
from cgmencode.production.clinical_decision_render import (
    render_html,
    render_markdown,
    render_deliverables,
)


def _glycemic():
    return {
        "tir": 0.62, "tbr_lt70": 0.047, "tbr_lt54": 0.016,
        "tar_gt180": 0.337, "tar_gt250": 0.12,
        "mean_mgdl": 162.0, "cv_pct": 43.4, "ea1c_gmi_pct": 7.19,
        "n_readings": 42859,
    }


# A 1x1 transparent PNG, base64 (valid data for embedding tests).
_STUB_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42m"
    "NkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _fig(section="insulin_sufficiency", filename="fig_demo.png"):
    return ReportFigure(
        section=section, title="Demo figure",
        caption="A demonstration figure.", filename=filename,
        png_base64=_STUB_PNG_B64, alt="demo")


class TestFigureContract:
    def test_builder_accepts_figures(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            figures=[_fig()])
        assert len(rep.figures) == 1

    def test_default_no_figures(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        assert rep.figures == []

    def test_to_dict_strips_base64(self):
        # report.json must not be bloated with base64 image payloads.
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            figures=[_fig()])
        d = rep.to_dict()
        assert d["figures"][0]["png_base64"] is None
        assert d["figures"][0]["filename"] == "fig_demo.png"
        # Still valid JSON and metadata preserved.
        json.loads(json.dumps(d))
        assert d["figures"][0]["caption"] == "A demonstration figure."


class TestHtmlEmbedding:
    def test_html_embeds_data_uri(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            figures=[_fig()])
        html = render_html(rep)
        assert "data:image/png;base64," in html
        assert _STUB_PNG_B64 in html

    def test_html_shows_caption(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            figures=[_fig()])
        html = render_html(rep)
        assert "A demonstration figure." in html

    def test_html_no_figure_section_when_empty(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        html = render_html(rep)
        assert "data:image/png;base64," not in html

    def test_figure_escaped_caption(self):
        f = ReportFigure(
            section="overview", title="T", caption="<x> & y",
            filename="f.png", png_base64=_STUB_PNG_B64)
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            figures=[f])
        html = render_html(rep)
        assert "&lt;x&gt; &amp; y" in html


class TestMarkdownEmbedding:
    def test_markdown_uses_rel_path(self):
        f = ReportFigure(
            section="overview", title="Daily profile",
            caption="cap", filename="fig.png",
            png_base64=_STUB_PNG_B64, rel_path="figures/fig.png")
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            figures=[f])
        md = render_markdown(rep)
        assert "figures/fig.png" in md
        assert "Daily profile" in md


class TestDeliverablesWithFigures:
    def test_html_self_contained_with_figures(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            figures=[_fig()])
        out = render_deliverables(rep)
        assert "data:image/png;base64," in out["clinical-decision-report.html"]
        # JSON stays lean.
        d = json.loads(out["report.json"])
        assert d["figures"][0]["png_base64"] is None
