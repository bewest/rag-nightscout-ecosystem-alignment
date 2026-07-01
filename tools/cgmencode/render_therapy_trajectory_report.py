#!/usr/bin/env python3
"""Render a visual HTML report for the therapy-trajectory-state harness.

Builds (or loads) a cohort's labeled 72h-turn table
(``therapy_trajectory_state.build_cohort_trajectories``), generates the
standard figure set (``therapy_trajectory_figures.build_trajectory_figures``),
and writes a self-contained, portable HTML report (base64-embedded PNGs,
same clinical look-and-feel convention as the per-patient decision-support
reports) plus a JSON summary.

Usage:
    python -m tools.cgmencode.render_therapy_trajectory_report \
        --parquet-dir externals/ns-parquet/training \
        --patient-ids a b c d \
        --output reports/therapy-trajectory-state/report.html

    # Reuse an already-built cohort table instead of rebuilding it:
    python -m tools.cgmencode.render_therapy_trajectory_report \
        --turns-parquet externals/experiments/therapy-trajectory-state/turns.parquet
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .mlflow_utils import build_run_context, log_artifact, log_dict, start_run
from .production.therapy_trajectory_figures import build_trajectory_figures
from .production.therapy_trajectory_state import (
    DEFAULT_TURN_HOURS,
    build_cohort_trajectories,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET_DIR = ROOT / "externals" / "ns-parquet" / "training"
DEFAULT_OUTPUT = ROOT / "reports" / "therapy-trajectory-state" / "report.html"

_CSS = """
:root {
  --ink: #1f2933; --muted: #52606d; --line: #d9e2ec; --bg: #f5f7fa;
  --card: #ffffff; --brand: #1f6f78; --brand-deep: #14505a;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.55; font-size: 15px; }
.wrap { max-width: 900px; margin: 0 auto; padding: 0 20px 64px; }
header.report { background: linear-gradient(135deg, var(--brand) 0%, var(--brand-deep) 100%);
  color: #fff; padding: 28px 0; margin-bottom: 24px; }
header.report .wrap { padding-bottom: 0; }
header.report h1 { margin: 0 0 4px; font-size: 22px; font-weight: 650; }
header.report .meta { opacity: .85; font-size: 13px; }
h2 { font-size: 16px; letter-spacing: .02em; text-transform: uppercase;
  color: var(--brand-deep); border-bottom: 2px solid var(--line);
  padding-bottom: 6px; margin: 32px 0 14px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 18px 20px; margin: 14px 0; box-shadow: 0 1px 2px rgba(31,41,51,.04); }
.card.summary { border-left: 4px solid var(--brand); }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; background: #f0f4f8; }
tr:last-child td { border-bottom: none; }
.muted { color: var(--muted); }
figure.viz { margin: 14px 0 4px; }
figure.viz img { width: 100%; height: auto; border: 1px solid var(--line);
  border-radius: 8px; background: #fff; }
figure.viz figcaption { color: var(--muted); font-size: 12.5px; margin-top: 6px; }
"""


def _summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n_patients": 0, "n_turns": 0}
    reliable = df[df["data_completeness"] >= 0.5]
    return {
        "n_patients": int(df["patient_id"].nunique()),
        "n_turns": int(len(df)),
        "n_reliable_turns": int(len(reliable)),
        "state_counts": {str(k): int(v) for k, v in df["state"].value_counts().items()},
        "mean_tir_by_state": (
            reliable.groupby("state")["tir"].mean().round(1).to_dict()
            if not reliable.empty else {}
        ),
        "weekend_fraction_tir_corr": (
            round(float(reliable["tir"].corr(reliable["weekend_day_fraction"])), 3)
            if len(reliable) > 2 and reliable["weekend_day_fraction"].nunique() > 1 else None
        ),
        "n_physiology_available": int(df["physiology_available"].sum()),
        "saturation_level_counts": {
            str(k): int(v) for k, v in df["saturation_level"].value_counts().items()
        },
    }


def _render_html(summary: dict, figures: list, parquet_dir: str) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in summary.get("state_counts", {}).items()
    )
    figs_html = "".join(
        f'<figure class="viz"><img src="data:image/png;base64,{fig.png_base64}" '
        f'alt="{html.escape(fig.title)}">'
        f'<figcaption><strong>{html.escape(fig.title)}.</strong> '
        f'{html.escape(fig.caption)}</figcaption></figure>'
        for fig in figures
    )
    corr = summary.get("weekend_fraction_tir_corr")
    corr_str = f"{corr:.3f}" if corr is not None else "n/a (too few reliable turns)"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Therapy Trajectory State: Cohort Report</title>
<style>{_CSS}</style></head>
<body>
<header class="report"><div class="wrap">
  <h1>Per-Patient Therapy Trajectory State</h1>
  <div class="meta">Generated {generated} &middot; source: {html.escape(parquet_dir)}</div>
</div></header>
<div class="wrap">
  <div class="card summary">
    <h2>Cohort Summary</h2>
    <p>{summary.get('n_patients', 0)} patients, {summary.get('n_turns', 0)} turns
       (72h windows), {summary.get('n_reliable_turns', 0)} with sufficient data
       completeness to trust. Weekend-fraction vs TIR correlation: {corr_str}.</p>
    <table><tr><th>State</th><th>Turn count</th></tr>{rows}</table>
    <p class="muted">This is a rule-based, ADA-threshold, safety-first proxy label
    (Candidly's first pipeline stage), not a fitted state model. See
    <code>docs/60-research/state-aware-harness-parallels-2026-07-01.md</code> §6 for
    the design rationale and what would need to be true before attempting
    unsupervised state discovery.</p>
  </div>
  <h2>Figures</h2>
  {figs_html}
</div>
</body></html>"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parquet-dir", default=str(DEFAULT_PARQUET_DIR))
    parser.add_argument("--patient-ids", nargs="*", default=None)
    parser.add_argument("--turn-hours", type=float, default=DEFAULT_TURN_HOURS)
    parser.add_argument("--min-turns", type=int, default=4)
    parser.add_argument("--turns-parquet", default=None,
                         help="Reuse an already-built cohort table instead of rebuilding it.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--example-patient-ids", nargs="*", default=None,
                         help="Patients to render a timeline figure for (default: first 3).")
    args = parser.parse_args(argv)

    if args.turns_parquet:
        df = pd.read_parquet(args.turns_parquet)
        source_label = args.turns_parquet
    else:
        df = build_cohort_trajectories(
            args.parquet_dir, patient_ids=args.patient_ids,
            turn_hours=args.turn_hours, min_turns=args.min_turns,
        )
        source_label = args.parquet_dir

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = _summarize(df)
    figures = build_trajectory_figures(df, example_patient_ids=args.example_patient_ids)
    report_html = _render_html(summary, figures, source_label)
    output_path.write_text(report_html)
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"Report: {output_path}")
    print(f"Summary: {summary_path}")
    print(json.dumps(summary, indent=2))

    run_context = build_run_context(
        task_type="therapy-trajectory-state",
        result_type="cohort-report",
        artifact_role="report",
        patients_dir=source_label if Path(source_label).is_dir() else None,
        data_source="nightscout",
        experiment_family="state-aware-harness-parallels",
    )
    with start_run(
        run_name="therapy-trajectory-state-report",
        tags={"runner": "render_therapy_trajectory_report", **run_context["tags"]},
        params={"source": source_label, "n_figures": len(figures), **run_context["params"]},
    ):
        log_dict(summary, "therapy_trajectory_state/report_summary.json")
        log_artifact(output_path, artifact_path="therapy_trajectory_state")


if __name__ == "__main__":
    main()
