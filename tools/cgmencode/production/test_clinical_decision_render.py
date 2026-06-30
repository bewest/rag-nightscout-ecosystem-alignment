"""Tests for clinical decision report renderers (markdown + split outputs)."""
from __future__ import annotations

import json

from cgmencode.production.types import (
    SettingsParameter, SettingsRecommendation,
)
from cgmencode.production.clinical_decision_policy import (
    ClinicalDecisionPolicy, OutputMode,
)
from cgmencode.production.clinical_decision_report import (
    build_clinical_decision_report,
)
from cgmencode.production.clinical_decision_render import (
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


def _rec(param, direction, current, suggested, delta, conf,
         affected=(0.0, 24.0)):
    return SettingsRecommendation(
        parameter=param, direction=direction,
        magnitude_pct=abs((suggested / current - 1.0) * 100) if current else 0,
        current_value=current, suggested_value=suggested,
        predicted_tir_delta=delta, affected_hours=affected,
        confidence=conf, evidence=f"evidence {param.value}",
        rationale=f"rationale {param.value}",
    )


class TestMarkdown:
    def test_renders_string(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        md = render_markdown(rep)
        assert isinstance(md, str) and md

    def test_contains_all_sections(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        md = render_markdown(rep)
        assert "Insulin sufficiency" in md
        assert "Basal" in md
        assert "ISF" in md
        assert "Carb ratio" in md
        assert "Overall justification" in md
        assert "Addenda" in md
        assert "2-week" in md or "Expected outcomes" in md

    def test_change_shows_practical_and_block(self):
        recs = [_rec(SettingsParameter.ISF, "increase", 50, 60, 4.0, 0.8,
                     affected=(0.0, 6.0))]
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=recs)
        md = render_markdown(rep)
        assert "00:00" in md or "0:00" in md or "0.0" in md  # time block
        assert "Practical" in md

    def test_reimbursement_section_when_enabled(self):
        policy = ClinicalDecisionPolicy(reimbursement_mode=True)
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            policy=policy, days_of_data=180.0)
        md = render_markdown(rep)
        assert "Reimbursement" in md
        assert "Agreed plan" in md

    def test_no_reimbursement_section_by_default(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        md = render_markdown(rep)
        assert "Reimbursement justification" not in md


class TestDeliverables:
    def test_consolidated_single_doc(self):
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[])
        out = render_deliverables(rep)
        # Consolidated: JSON + one markdown.
        assert set(out.keys()) >= {"report.json", "clinical-decision-report.md"}
        # Valid JSON.
        json.loads(out["report.json"])

    def test_split_mode_separates_reimbursement(self):
        policy = ClinicalDecisionPolicy(
            output_mode=OutputMode.SPLIT, reimbursement_mode=True)
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            policy=policy, days_of_data=180.0)
        out = render_deliverables(rep)
        assert "clinical-decision-report.md" in out
        assert "reimbursement-evidence.md" in out
        # Reimbursement content lives in the separate doc, not the clinician one.
        assert "Agreed plan" in out["reimbursement-evidence.md"]
        assert "Agreed plan" not in out["clinical-decision-report.md"]

    def test_split_without_reimbursement_has_no_reimbursement_doc(self):
        policy = ClinicalDecisionPolicy(output_mode=OutputMode.SPLIT)
        rep = build_clinical_decision_report(
            patient_id="c", glycemic=_glycemic(), settings_recs=[],
            policy=policy)
        out = render_deliverables(rep)
        assert "reimbursement-evidence.md" not in out
