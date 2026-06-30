"""clinical_decision_render.py — Renderers for the clinical decision report.

Produces audience-ready deliverables from a :class:`ClinicalDecisionReport`:

  * ``render_markdown`` — a single consolidated clinician-facing document.
  * ``render_reimbursement_markdown`` — the reimbursement evidence block.
  * ``render_deliverables`` — packages outputs per the report's policy:
      - consolidated (default): one JSON + one markdown (reimbursement, if
        enabled, is appended in-line).
      - split: separate clinician and reimbursement markdown documents so
        each audience receives only what it needs.

JSON is always emitted (``report.json``) as the canonical machine-readable
source of truth.
"""
from __future__ import annotations

import json
from typing import Dict, List

from .clinical_decision_report import (
    ClinicalDecisionReport, DomainRecommendation, DecisionMode,
)
from .clinical_decision_policy import OutputMode


def _fmt_block(block) -> str:
    if not block:
        return "all day"
    lo, hi = block
    return f"{int(lo):02d}:00–{int(hi):02d}:00"


def _domain_md(d: DomainRecommendation) -> List[str]:
    label = {"basal": "Basal", "isf": "ISF", "cr": "Carb ratio"}[d.domain]
    lines = [f"### {label}", ""]
    badge = "CHANGE" if d.mode == DecisionMode.CHANGE else "NO CHANGE"
    lines.append(f"**Decision:** {badge}  ")
    if d.mode == DecisionMode.NO_CHANGE and d.hold_reason.value != "none":
        lines.append(f"**Hold reason:** {d.hold_reason.value}  ")
    lines.append(f"**Summary:** {d.summary}")
    lines.append("")

    if d.mode == DecisionMode.CHANGE:
        lines += [
            "| Field | Value |",
            "|---|---|",
            f"| Current | {d.current_value:g} |",
            f"| Practical (implement now) | {d.practical_value:g} "
            f"({d.practical_change_pct:+.0f}%) |",
            f"| Time block | {_fmt_block(d.affected_time_block)} |",
            f"| Confidence | {d.confidence:.2f} |",
            "",
        ]

    lines.append(f"**Justification:** {d.justification}")
    lines.append("")

    if d.expected_outcomes:
        lines += [
            "**Expected outcomes (2-week):**",
            "",
            "| Metric | Baseline | Expected | Direction |",
            "|---|---|---|---|",
        ]
        for o in d.expected_outcomes:
            lines.append(
                f"| {o.metric} | {o.baseline:g}{o.unit} | "
                f"{o.expected_2wk:g}{o.unit} | {o.direction} |")
        lines.append("")

    lines.append(f"**Success criteria** (revisit in {d.follow_up.revisit_days} "
                 f"days):")
    for s in d.follow_up.success:
        lines.append(f"- {s}")
    lines.append("")
    lines.append("**Stop / escalate criteria:**")
    for s in d.follow_up.stop_escalate:
        lines.append(f"- {s}")
    lines.append("")
    return lines


def _reimbursement_lines(rep: ClinicalDecisionReport,
                         heading_level: str = "##") -> List[str]:
    rb = rep.reimbursement
    if rb is None:
        return []
    lines = [f"{heading_level} Reimbursement justification", ""]
    lines.append(f"**Data sufficiency:** {rb.data_sufficiency}")
    lines.append("")
    lines.append("**Risks reviewed:**")
    for r in rb.risks_reviewed:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("**Mitigations:**")
    for m in rb.mitigations:
        lines.append(f"- {m}")
    lines.append("")
    lines.append("**Alternatives discussed:**")
    for a in rb.alternatives_discussed:
        lines.append(f"- {a}")
    lines.append("")
    lines.append("**Patient-specific barriers:**")
    for b in rb.patient_barriers:
        lines.append(f"- {b}")
    lines.append("")
    lines.append(f"**Agreed plan:** {rb.agreed_plan}")
    lines.append("")
    lines.append(f"**Expected trajectory:** {rb.expected_trajectory}")
    lines.append("")
    lines.append(f"**Follow-up date:** {rb.follow_up_date}")
    lines.append("")
    return lines


def _core_lines(rep: ClinicalDecisionReport) -> List[str]:
    g = rep.glycemic_summary
    ins = rep.insulin_sufficiency
    lines = [
        f"# Clinical Decision Support — patient `{rep.patient_id}`",
        "",
        f"_Generated: {rep.generated_at_utc}_",
        "",
        "## Insulin sufficiency",
        "",
        ins.summary,
        "",
    ]
    if ins.main_risks:
        lines.append("**Main risks:**")
        for r in ins.main_risks:
            lines.append(f"- {r}")
        lines.append("")
    if ins.whats_working:
        lines.append("**What's working:**")
        for w in ins.whats_working:
            lines.append(f"- {w}")
        lines.append("")

    lines += ["## Recommendations", ""]
    lines += _domain_md(rep.basal)
    lines += _domain_md(rep.isf)
    lines += _domain_md(rep.cr)

    lines += ["## Overall justification", "", rep.overall_justification, ""]

    if rep.reboot.recommended:
        lines += ["## Settings reinitialization (reboot)", "",
                  rep.reboot.rationale, ""]

    lines += ["## Addenda", ""]
    for a in rep.addenda:
        lines.append(f"- {a}")
    lines.append("")
    return lines


def render_markdown(rep: ClinicalDecisionReport) -> str:
    """Render the consolidated clinician-facing markdown document.

    Reimbursement evidence (when enabled) is appended in-line so the
    consolidated deliverable is self-contained.
    """
    lines = _core_lines(rep)
    lines += _reimbursement_lines(rep, heading_level="##")
    return "\n".join(lines).rstrip() + "\n"


def render_reimbursement_markdown(rep: ClinicalDecisionReport) -> str:
    """Render a standalone reimbursement-evidence document."""
    header = [
        f"# Reimbursement Evidence — patient `{rep.patient_id}`",
        "",
        f"_Generated: {rep.generated_at_utc}_",
        "",
    ]
    return "\n".join(header + _reimbursement_lines(rep, heading_level="##")
                     ).rstrip() + "\n"


def render_deliverables(rep: ClinicalDecisionReport) -> Dict[str, str]:
    """Package deliverables according to the report's output policy.

    Returns a mapping of filename -> content. JSON is always present.
    Consolidated mode (default) emits one markdown; split mode separates
    the reimbursement evidence into its own document for a distinct
    audience.
    """
    out: Dict[str, str] = {
        "report.json": json.dumps(rep.to_dict(), indent=2),
    }

    output_mode = rep.policy.get("output_mode", OutputMode.CONSOLIDATED.value)
    has_reimbursement = rep.reimbursement is not None

    if output_mode == OutputMode.SPLIT.value:
        # Clinician doc without the inline reimbursement block.
        clinician = "\n".join(_core_lines(rep)).rstrip() + "\n"
        out["clinical-decision-report.md"] = clinician
        if has_reimbursement:
            out["reimbursement-evidence.md"] = render_reimbursement_markdown(
                rep)
    else:
        out["clinical-decision-report.md"] = render_markdown(rep)

    return out
