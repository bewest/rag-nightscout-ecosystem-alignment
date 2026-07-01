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

import html as _html
import json
from typing import Dict, List

from .clinical_decision_report import (
    ClinicalDecisionReport, DomainRecommendation, DecisionMode, ReportFigure,
)
from .clinical_decision_policy import OutputMode


def _fmt_block(block) -> str:
    if not block:
        return "all day"
    lo, hi = block
    return f"{int(lo):02d}:00–{int(hi):02d}:00"


def _section_figs(rep: ClinicalDecisionReport,
                  *sections: str) -> List[ReportFigure]:
    want = set(sections)
    return [f for f in rep.figures if f.section in want]


def _figs_md(figs: List[ReportFigure]) -> List[str]:
    lines: List[str] = []
    for f in figs:
        src = f.rel_path or (
            f"data:image/png;base64,{f.png_base64}" if f.png_base64 else "")
        if not src:
            continue
        lines.append(f"**{f.title}**")
        lines.append("")
        lines.append(f"![{f.alt or f.title}]({src})")
        if f.caption:
            lines.append("")
            lines.append(f"_{f.caption}_")
        lines.append("")
    return lines


def _domain_md(d: DomainRecommendation,
               figs: Optional[List[ReportFigure]] = None) -> List[str]:
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

    if figs:
        lines += _figs_md(figs)

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

    overview_figs = _section_figs(rep, "insulin_sufficiency", "overview")
    if overview_figs:
        lines += _figs_md(overview_figs)

    lines += ["## Recommendations", ""]
    lines += _domain_md(rep.basal, _section_figs(rep, "basal"))
    lines += _domain_md(rep.isf, _section_figs(rep, "isf"))
    lines += _domain_md(rep.cr, _section_figs(rep, "cr"))

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
    Consolidated mode (default) emits one markdown + one HTML document;
    split mode separates the reimbursement evidence into its own
    markdown + HTML documents for a distinct audience.
    """
    out: Dict[str, str] = {
        "report.json": json.dumps(rep.to_dict(), indent=2),
    }

    output_mode = rep.policy.get("output_mode", OutputMode.CONSOLIDATED.value)
    has_reimbursement = rep.reimbursement is not None

    if output_mode == OutputMode.SPLIT.value:
        # Clinician doc without the inline reimbursement block.
        out["clinical-decision-report.md"] = (
            "\n".join(_core_lines(rep)).rstrip() + "\n")
        out["clinical-decision-report.html"] = render_html(
            rep, include_reimbursement=False)
        if has_reimbursement:
            out["reimbursement-evidence.md"] = render_reimbursement_markdown(
                rep)
            out["reimbursement-evidence.html"] = render_reimbursement_html(rep)
    else:
        out["clinical-decision-report.md"] = render_markdown(rep)
        out["clinical-decision-report.html"] = render_html(
            rep, include_reimbursement=True)

    return out


# ── HTML rendering (clinical look & feel) ─────────────────────────────

# Calm clinical palette: slate/teal ink on white, restrained accents.
_HTML_CSS = """
:root {
  --ink: #1f2933;
  --muted: #52606d;
  --line: #d9e2ec;
  --bg: #f5f7fa;
  --card: #ffffff;
  --brand: #1f6f78;        /* deep teal */
  --brand-deep: #14505a;
  --accent: #2b6cb0;       /* clinical blue */
  --ok: #2f855a;           /* green */
  --ok-bg: #e6f4ea;
  --warn: #b7791f;         /* amber */
  --warn-bg: #fdf3e2;
  --risk: #9b2c2c;         /* clinical red */
  --risk-bg: #fdeaea;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    Helvetica, Arial, sans-serif;
  line-height: 1.55; font-size: 15px;
}
.wrap { max-width: 880px; margin: 0 auto; padding: 0 20px 64px; }
header.report {
  background: linear-gradient(135deg, var(--brand) 0%, var(--brand-deep) 100%);
  color: #fff; padding: 28px 0; margin-bottom: 24px;
}
header.report .wrap { padding-bottom: 0; }
header.report h1 { margin: 0 0 4px; font-size: 22px; font-weight: 650; }
header.report .meta { opacity: .85; font-size: 13px; }
h2 {
  font-size: 16px; letter-spacing: .02em; text-transform: uppercase;
  color: var(--brand-deep); border-bottom: 2px solid var(--line);
  padding-bottom: 6px; margin: 32px 0 14px;
}
h3 { font-size: 16px; margin: 0 0 2px; color: var(--ink); }
.card {
  background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 18px 20px; margin: 14px 0;
  box-shadow: 0 1px 2px rgba(31,41,51,.04);
}
.card.domain { border-left: 4px solid var(--accent); }
.summary-card { border-left: 4px solid var(--brand); }
.badge {
  display: inline-block; font-size: 11px; font-weight: 700;
  letter-spacing: .04em; text-transform: uppercase;
  padding: 3px 10px; border-radius: 999px; vertical-align: middle;
}
.badge.change { background: var(--warn-bg); color: var(--warn); }
.badge.nochange { background: var(--ok-bg); color: var(--ok); }
.kv { color: var(--muted); font-size: 13px; margin: 2px 0 0; }
table {
  border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px;
}
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; background: #f0f4f8; }
tr:last-child td { border-bottom: none; }
ul.crit { margin: 6px 0 0; padding-left: 18px; }
ul.crit li { margin: 3px 0; }
.cols { display: flex; gap: 18px; flex-wrap: wrap; }
.cols > div { flex: 1 1 280px; }
.panel { border-radius: 8px; padding: 12px 14px; }
.panel.risk { background: var(--risk-bg); }
.panel.ok { background: var(--ok-bg); }
.panel h4 { margin: 0 0 6px; font-size: 13px; text-transform: uppercase;
  letter-spacing: .03em; }
.panel.risk h4 { color: var(--risk); }
.panel.ok h4 { color: var(--ok); }
.callout {
  background: var(--warn-bg); border: 1px solid #f0d8a8;
  border-radius: 8px; padding: 14px 16px; margin: 14px 0;
}
.callout h3 { color: var(--warn); }
.muted { color: var(--muted); }
.justify { margin: 8px 0 0; }
figure.viz { margin: 14px 0 4px; }
figure.viz img { width: 100%; height: auto; border: 1px solid var(--line);
  border-radius: 8px; background: #fff; }
figure.viz figcaption { color: var(--muted); font-size: 12.5px;
  margin-top: 6px; }
.viz-title { font-size: 13px; font-weight: 600; color: var(--brand-deep);
  margin: 16px 0 4px; }
footer.report { color: var(--muted); font-size: 12px; margin-top: 40px;
  text-align: center; }

/* ── Print / PDF ──────────────────────────────────────────────── */
@page {
  size: A4;
  margin: 14mm 12mm;
}
@media print {
  :root { }
  body {
    background: #fff;
    font-size: 11.5pt;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .wrap { max-width: none; padding: 0; }
  /* Preserve the clinical palette (header band, badges, panels) in PDF. */
  header.report, .badge, .panel, figure.viz img, table th,
  .callout {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  header.report { padding: 16px 0; }
  /* Keep semantic blocks intact across page boundaries. */
  .card, figure.viz, table, .panel, .callout, h2, h3 {
    break-inside: avoid;
    page-break-inside: avoid;
  }
  h2, h3 { break-after: avoid; page-break-after: avoid; }
  .card { box-shadow: none; }
  a { color: inherit; text-decoration: none; }
  footer.report { margin-top: 18px; }
}
""".strip()


def _e(text) -> str:
    """HTML-escape any value."""
    return _html.escape(str(text), quote=True)


def _domain_html(d: DomainRecommendation,
                 figs: Optional[List[ReportFigure]] = None) -> str:
    label = {"basal": "Basal", "isf": "ISF", "cr": "Carb ratio"}[d.domain]
    is_change = d.mode == DecisionMode.CHANGE
    badge = ('<span class="badge change">Change</span>' if is_change
             else '<span class="badge nochange">No change</span>')
    parts = [f'<div class="card domain"><h3>{_e(label)} {badge}</h3>']

    if (not is_change) and d.hold_reason.value != "none":
        parts.append(
            f'<p class="kv">Hold reason: {_e(d.hold_reason.value)}</p>')
    parts.append(f'<p class="justify">{_e(d.summary)}</p>')

    if is_change:
        block = _fmt_block(d.affected_time_block)
        parts.append(
            '<table><tr><th>Field</th><th>Value</th></tr>'
            f'<tr><td>Current</td><td>{_e(_num(d.current_value))}</td></tr>'
            f'<tr><td>Practical (implement now)</td><td>'
            f'{_e(_num(d.practical_value))} '
            f'({d.practical_change_pct:+.0f}%)</td></tr>'
            f'<tr><td>Time block</td><td>{_e(block)}</td></tr>'
            f'<tr><td>Confidence</td><td>{d.confidence:.2f}</td></tr>'
            '</table>')

    parts.append(
        f'<p class="justify"><strong>Justification.</strong> '
        f'{_e(d.justification)}</p>')

    if d.expected_outcomes:
        rows = "".join(
            f"<tr><td>{_e(o.metric)}</td>"
            f"<td>{_e(_num(o.baseline))}{_e(o.unit)}</td>"
            f"<td>{_e(_num(o.expected_2wk))}{_e(o.unit)}</td>"
            f"<td>{_e(o.direction)}</td></tr>"
            for o in d.expected_outcomes)
        parts.append(
            '<p class="kv">Expected outcomes (2-week)</p>'
            '<table><tr><th>Metric</th><th>Baseline</th>'
            '<th>Expected</th><th>Direction</th></tr>'
            f'{rows}</table>')

    if figs:
        parts.append(_figs_html(figs))

    succ = "".join(f"<li>{_e(s)}</li>" for s in d.follow_up.success)
    stop = "".join(f"<li>{_e(s)}</li>" for s in d.follow_up.stop_escalate)
    parts.append(
        f'<p class="kv">Success criteria (revisit in '
        f'{d.follow_up.revisit_days} days)</p>'
        f'<ul class="crit">{succ}</ul>'
        '<p class="kv">Stop / escalate criteria</p>'
        f'<ul class="crit">{stop}</ul>')

    parts.append("</div>")
    return "".join(parts)


def _figs_html(figs: List[ReportFigure]) -> str:
    out = []
    for f in figs:
        if f.png_base64:
            src = f"data:image/png;base64,{f.png_base64}"
        elif f.rel_path:
            src = _e(f.rel_path)
        else:
            continue
        out.append(
            '<figure class="viz">'
            f'<div class="viz-title">{_e(f.title)}</div>'
            f'<img src="{src}" alt="{_e(f.alt or f.title)}">'
            + (f'<figcaption>{_e(f.caption)}</figcaption>' if f.caption else "")
            + '</figure>')
    return "".join(out)


def _num(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return v


def _reimbursement_html_section(rep: ClinicalDecisionReport) -> str:
    rb = rep.reimbursement
    if rb is None:
        return ""

    def _list(items):
        return '<ul class="crit">' + "".join(
            f"<li>{_e(i)}</li>" for i in items) + "</ul>"

    return (
        '<h2>Reimbursement justification</h2>'
        '<div class="card">'
        f'<p><strong>Data sufficiency.</strong> {_e(rb.data_sufficiency)}</p>'
        '<p class="kv">Risks reviewed</p>' + _list(rb.risks_reviewed) +
        '<p class="kv">Mitigations</p>' + _list(rb.mitigations) +
        '<p class="kv">Alternatives discussed</p>'
        + _list(rb.alternatives_discussed) +
        '<p class="kv">Patient-specific barriers</p>'
        + _list(rb.patient_barriers) +
        f'<p class="justify"><strong>Agreed plan.</strong> '
        f'{_e(rb.agreed_plan)}</p>'
        f'<p class="justify"><strong>Expected trajectory.</strong> '
        f'{_e(rb.expected_trajectory)}</p>'
        f'<p class="justify"><strong>Follow-up date.</strong> '
        f'{_e(rb.follow_up_date)}</p>'
        '</div>')


def _html_document(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, '
        'initial-scale=1">'
        f"<title>{_e(title)}</title>"
        f"<style>{_HTML_CSS}</style>"
        f"</head><body>{body}"
        '<footer class="report"><div class="wrap">Decision support is '
        'advisory only and does not replace clinical judgement.</div>'
        "</footer></body></html>\n")


def render_html(rep: ClinicalDecisionReport,
                include_reimbursement: bool = True) -> str:
    """Render a clinical-look HTML document for the decision report.

    Uses a calm clinical palette (teal/slate ink, restrained accents),
    card-based layout, and clear decision badges. All dynamic text is
    HTML-escaped.
    """
    ins = rep.insulin_sufficiency

    risks = "".join(f"<li>{_e(r)}</li>" for r in ins.main_risks)
    working = "".join(f"<li>{_e(w)}</li>" for w in ins.whats_working)
    risk_panel = (
        f'<div class="panel risk"><h4>Main risks</h4>'
        f'<ul class="crit">{risks}</ul></div>' if ins.main_risks else "")
    working_panel = (
        f'<div class="panel ok"><h4>What\'s working</h4>'
        f'<ul class="crit">{working}</ul></div>' if ins.whats_working else "")

    reboot_html = ""
    if rep.reboot.recommended:
        reboot_html = (
            '<div class="callout"><h3>Settings reinitialization (reboot)</h3>'
            f'<p>{_e(rep.reboot.rationale)}</p></div>')

    addenda = "".join(f"<li>{_e(a)}</li>" for a in rep.addenda)

    reimb = (_reimbursement_html_section(rep)
             if include_reimbursement else "")

    overview_figs = _figs_html(
        _section_figs(rep, "insulin_sufficiency", "overview"))

    body = (
        '<header class="report"><div class="wrap">'
        f'<h1>Clinical Decision Support — patient {_e(rep.patient_id)}</h1>'
        f'<div class="meta">Generated {_e(rep.generated_at_utc)}</div>'
        '</div></header>'
        '<div class="wrap">'
        '<h2>Insulin sufficiency</h2>'
        f'<div class="card summary-card"><p>{_e(ins.summary)}</p>'
        f'<div class="cols">{risk_panel}{working_panel}</div></div>'
        f'{overview_figs}'
        '<h2>Recommendations</h2>'
        f'{_domain_html(rep.basal, _section_figs(rep, "basal"))}'
        f'{_domain_html(rep.isf, _section_figs(rep, "isf"))}'
        f'{_domain_html(rep.cr, _section_figs(rep, "cr"))}'
        '<h2>Overall justification</h2>'
        f'<div class="card"><p>{_e(rep.overall_justification)}</p></div>'
        f'{reboot_html}'
        '<h2>Addenda</h2>'
        f'<div class="card"><ul class="crit">{addenda}</ul></div>'
        f'{reimb}'
        '</div>')

    return _html_document(
        f"Clinical Decision Support — {rep.patient_id}", body)


def render_reimbursement_html(rep: ClinicalDecisionReport) -> str:
    """Render a standalone reimbursement-evidence HTML document."""
    body = (
        '<header class="report"><div class="wrap">'
        f'<h1>Reimbursement Evidence — patient {_e(rep.patient_id)}</h1>'
        f'<div class="meta">Generated {_e(rep.generated_at_utc)}</div>'
        '</div></header>'
        f'<div class="wrap">{_reimbursement_html_section(rep)}</div>')
    return _html_document(
        f"Reimbursement Evidence — {rep.patient_id}", body)

