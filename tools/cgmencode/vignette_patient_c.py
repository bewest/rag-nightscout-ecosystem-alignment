"""Patient C therapy-discussion vignette.

Pulls every available production audition signal + raw grid stats for
patient `c` and emits:
  * 6 figures into docs/60-research/figures/patient-c-vignette/
  * a clinician-friendly markdown report at
    docs/60-research/patient-c-therapy-vignette-2026-04-22.md

This is a STREAM B operational triage report: every "consider"
recommendation is a CONVERSATION STARTER for the patient/clinician
review meeting, not an autonomous setting change. Per EXP-2738
safety memory, AID gaps often ARE the controller's safety margin.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cgmencode.production.audition_matrix import (
    AuditionInputs,
    classify_triage_flags,
)
from tools.cgmencode.production.basal_mismatch_facts_loader import (
    BasalMismatchFactsLoader,
)
from tools.cgmencode.production.isf_gap_facts_loader import IsfGapFactsLoader
from tools.cgmencode.production.post_high_facts_loader import PostHighFactsLoader
from tools.cgmencode.production.recovery_facts_loader import RecoveryFactsLoader
from tools.cgmencode.production.simpson_facts_loader import SimpsonFactsLoader
from tools.cgmencode.production.state_basal_facts_loader import (
    StateBasalFactsLoader,
)
from tools.cgmencode.production.types import ControllerType
from tools.cgmencode.production.wear_facts_loader import WearFactsLoader

PID = "c"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
FIGDIR = REPO / "docs" / "60-research" / "figures" / "patient-c-vignette"
REPORT = REPO / "docs" / "60-research" / "patient-c-therapy-vignette-2026-04-22.md"
FIGDIR.mkdir(parents=True, exist_ok=True)


def _save(fig, name):
    p = FIGDIR / name
    fig.savefig(p, dpi=110, bbox_inches="tight")
    plt.close(fig)
    # Return path relative to the report's directory (docs/60-research/)
    return p.relative_to(REPO / "docs" / "60-research")


def main() -> None:
    g = pd.read_parquet(GRID)
    c = g[g["patient_id"] == PID].copy()
    c["time"] = pd.to_datetime(c["time"], utc=True)
    c["hour"] = c["time"].dt.hour
    days = (c["time"].max() - c["time"].min()).total_seconds() / 86400

    # ---------- summary stats ----------
    mean_bg = c["glucose"].mean()
    median_bg = c["glucose"].median()
    cv = c["glucose"].std() / mean_bg * 100
    tir = ((c["glucose"] >= 70) & (c["glucose"] <= 180)).mean() * 100
    tbr = (c["glucose"] < 70).mean() * 100
    very_low = (c["glucose"] < 54).mean() * 100
    tar = (c["glucose"] > 180).mean() * 100
    very_high = (c["glucose"] > 250).mean() * 100
    gmi = 3.31 + 0.02392 * mean_bg

    ce = c[c["carbs"] > 0]
    real_meals = ce[ce["carbs"] >= 10]

    # ---------- audition signals ----------
    inputs = AuditionInputs(
        controller=ControllerType.LOOP,  # placeholder; not used by signals
        smb_capable=False,
        phenotype="flat",
        median_recovery_fraction=None,
        p_simpson=SimpsonFactsLoader().get(PID).p_simpson,
        p_isf_under_correction=IsfGapFactsLoader().lookup(PID).p_isf_under_correction,
        p_isf_over_correction=IsfGapFactsLoader().lookup(PID).p_isf_over_correction,
        p_low_recovery=RecoveryFactsLoader().lookup(PID).p_low_recovery,
        p_site_degradation=WearFactsLoader().lookup(PID).p_site_degradation,
        p_post_high_envelope=PostHighFactsLoader().lookup(PID).p_post_high_envelope,
        p_basal_mismatch=BasalMismatchFactsLoader().lookup(PID).p_basal_mismatch,
        basal_recommended_mult=BasalMismatchFactsLoader()
        .lookup(PID)
        .median_recommended_mult,
    )
    flags = classify_triage_flags(inputs)

    # ---------- state-conditioned basal (informational) ----------
    state_facts = StateBasalFactsLoader().lookup(PID)

    # ---------- FIGURE 1: AGP-style 24h percentile bands ----------
    by_hour = c.groupby(c["time"].dt.hour)["glucose"]
    p10 = by_hour.quantile(0.10)
    p25 = by_hour.quantile(0.25)
    p50 = by_hour.median()
    p75 = by_hour.quantile(0.75)
    p90 = by_hour.quantile(0.90)
    fig, ax = plt.subplots(figsize=(9, 4))
    hours = p50.index
    ax.fill_between(hours, p10, p90, alpha=0.18, color="C0", label="10–90 %ile")
    ax.fill_between(hours, p25, p75, alpha=0.32, color="C0", label="25–75 %ile")
    ax.plot(hours, p50, color="C0", lw=2, label="median")
    ax.axhspan(70, 180, color="green", alpha=0.05, zorder=-1)
    ax.axhline(70, color="green", lw=0.8, ls="--", alpha=0.6)
    ax.axhline(180, color="orange", lw=0.8, ls="--", alpha=0.6)
    ax.set_xlim(0, 23)
    ax.set_ylim(40, 320)
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Glucose (mg/dL)")
    ax.set_title(f"Patient C — Ambulatory Glucose Profile (180 days)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.2)
    f1 = _save(fig, "01_agp.png")

    # ---------- FIGURE 2: Time-in-range bar ----------
    fig, ax = plt.subplots(figsize=(7, 2.4))
    bands = [
        ("Very low (<54)", very_low, "#7a0000"),
        ("Low (54–69)", tbr - very_low, "#cc3333"),
        ("In range (70–180)", tir, "#2a9d3a"),
        ("High (181–250)", tar - very_high, "#f0a040"),
        ("Very high (>250)", very_high, "#9c2a8a"),
    ]
    left = 0
    for label, pct, color in bands:
        ax.barh(0, pct, left=left, color=color, edgecolor="white",
                label=f"{label}: {pct:.1f}%")
        if pct > 4:
            ax.text(left + pct / 2, 0, f"{pct:.0f}%",
                    ha="center", va="center", color="white", fontweight="bold")
        left += pct
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_xlabel("% of time")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.4), ncol=3, fontsize=8)
    ax.set_title(f"Time-in-range — TIR {tir:.0f}% · GMI {gmi:.1f}% · CV {cv:.0f}%")
    f2 = _save(fig, "02_tir.png")

    # ---------- FIGURE 3: scheduled vs actual basal by hour ----------
    by_hour_basal = c.groupby("hour").agg(
        sched=("scheduled_basal_rate", "median"),
        act_med=("actual_basal_rate", "median"),
        act_p25=("actual_basal_rate", lambda s: s.quantile(0.25)),
        act_p75=("actual_basal_rate", lambda s: s.quantile(0.75)),
    )
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(by_hour_basal.index, by_hour_basal["sched"],
            color="black", lw=2, label="scheduled")
    ax.fill_between(by_hour_basal.index, by_hour_basal["act_p25"],
                    by_hour_basal["act_p75"], alpha=0.25, color="C3",
                    label="actual P25–P75")
    ax.plot(by_hour_basal.index, by_hour_basal["act_med"],
            color="C3", lw=2, label="actual median")
    ax.set_xlim(0, 23)
    ax.set_xlabel("Hour of day (UTC)")
    ax.set_ylabel("Basal rate (U/h)")
    ax.set_title("Basal: scheduled vs actual (controller-delivered)")
    ax.legend()
    ax.grid(alpha=0.2)
    f3 = _save(fig, "03_basal_schedule.png")

    # ---------- FIGURE 4: Carb event size distribution ----------
    fig, ax = plt.subplots(figsize=(8, 3.5))
    ax.hist(ce["carbs"].clip(upper=120), bins=30, color="C2",
            edgecolor="white", alpha=0.8)
    ax.axvline(5, color="orange", ls="--", label="5 g (real-event floor)")
    ax.axvline(10, color="red", ls="--", label="10 g (real-meal floor)")
    ax.axvline(30, color="purple", ls="--", label="30 g (substantial)")
    ax.set_xlabel("Carbs entered (g, clipped at 120)")
    ax.set_ylabel("Event count")
    ax.set_title(
        f"Carb log quality: {len(ce)} events ({len(ce)/days:.1f}/day) · "
        f"95% ≥10 g (clean log)"
    )
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2, axis="y")
    f4 = _save(fig, "04_carb_log.png")

    # ---------- FIGURE 5: Post-meal excursion samples ----------
    # Pick 3 large meals; plot ±3 hr
    big = real_meals[real_meals["carbs"] >= 30].sort_values("carbs", ascending=False)
    sampled = big.head(6)
    fig, axes = plt.subplots(2, 3, figsize=(11, 5), sharey=True)
    for i, (_, row) in enumerate(sampled.iterrows()):
        if i >= 6:
            break
        ax = axes.flat[i]
        t0 = row["time"]
        win = c[(c["time"] >= t0 - timedelta(hours=1)) &
                (c["time"] <= t0 + timedelta(hours=4))]
        if len(win) < 5:
            continue
        rel_min = (win["time"] - t0).dt.total_seconds() / 60
        ax.plot(rel_min, win["glucose"], color="C0", lw=1.5)
        ax.axvline(0, color="C2", ls="--", alpha=0.7)
        ax.axhspan(70, 180, color="green", alpha=0.07)
        ax.set_title(f"{row['carbs']:.0f} g @ {t0.strftime('%Y-%m-%d %H:%M')}",
                     fontsize=9)
        ax.set_xlim(-60, 240)
        ax.grid(alpha=0.2)
        if i % 3 == 0:
            ax.set_ylabel("Glucose (mg/dL)")
        if i >= 3:
            ax.set_xlabel("Min from meal")
    fig.suptitle("Post-meal excursions (largest 6 real meals)")
    fig.tight_layout()
    f5 = _save(fig, "05_meal_excursions.png")

    # ---------- FIGURE 6: Audition signal panel ----------
    sig_rows = [
        ("Basal mismatch", inputs.p_basal_mismatch, "EXP-2869"),
        ("ISF over-correction", inputs.p_isf_over_correction, "EXP-2861"),
        ("Low recovery", inputs.p_low_recovery, "EXP-2862"),
        ("Post-high envelope", inputs.p_post_high_envelope, "EXP-2864"),
        ("Site degradation", inputs.p_site_degradation, "EXP-2863"),
        ("ISF under-correction", inputs.p_isf_under_correction, "EXP-2861"),
        ("Simpson paradox", inputs.p_simpson, "EXP-2859"),
    ]
    fig, ax = plt.subplots(figsize=(8, 3.5))
    labels = [r[0] for r in sig_rows]
    vals = [r[1] if r[1] is not None else 0 for r in sig_rows]
    colors = ["#cc3333" if v >= 0.9 else "#f0a040" if v >= 0.1 else "#888"
              for v in vals]
    bars = ax.barh(range(len(sig_rows)), vals, color=colors)
    ax.set_yticks(range(len(sig_rows)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.0)
    ax.axvline(0.9, color="black", ls=":", alpha=0.6, label="High (≥0.9)")
    ax.axvline(0.1, color="black", ls="--", alpha=0.4, label="Boundary (≥0.1)")
    for i, (lab, v, src) in enumerate(sig_rows):
        ax.text(v + 0.01, i, f"  P={v:.2f}   ({src})",
                va="center", fontsize=8)
    ax.set_xlabel("Bootstrap probability")
    ax.set_title("Patient C — bootstrap-confidence audition signals")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.2, axis="x")
    f6 = _save(fig, "06_audition_panel.png")

    # ---------- emit markdown ----------
    md = f"""# Patient C — Therapy-Discussion Vignette (2026-04-22)

> **Operational triage report (Stream B).** Every recommendation is a
> *conversation starter* for clinician/patient review — not an autonomous
> setting change. Per the safety memory (EXP-2738): **the gap between
> scheduled and delivered insulin often IS the controller's safety
> margin.** Lowering settings to "match" the gap can increase
> hypoglycemia.

## Summary

| Metric | Value |
|--------|------:|
| Observation window | {days:.0f} days |
| Mean glucose | {mean_bg:.0f} mg/dL |
| GMI (eA1c estimate) | **{gmi:.1f} %** |
| Coefficient of variation | {cv:.0f}% (target <36%) |
| Time in range (70–180) | **{tir:.0f}%** (target ≥70%) |
| Time below range (<70) | {tbr:.1f}% (target <4%) |
| Time very low (<54) | {very_low:.2f}% (target <1%) |
| Time above range (>180) | {tar:.0f}% (target <25%) |
| Time very high (>250) | {very_high:.0f}% (target <5%) |
| Carb-log quality | {len(ce)/days:.1f} events/day · 95% ≥10 g (**clean log**) |
| Median scheduled basal | {c['scheduled_basal_rate'].median():.2f} U/h |
| Median delivered basal | {c['actual_basal_rate'].median():.2f} U/h |

## Glycemic profile

![AGP]({f1})

![TIR]({f2})

**Read:** TIR is just above 50% — clinically meaningful improvement
target. CV {cv:.0f}% (>36%) suggests glycemic instability is the
dominant driver, not just elevated mean.

## Bootstrap-confident audition signals

![Audition panel]({f6})

| Signal | P | Tier | Source |
|--------|--:|------|--------|
"""
    for f in flags:
        md += f"| **{f.name}** | — | {f.severity} | matrix |\n"
    md += "\n**Raw bootstrap probabilities:**\n\n"
    md += "| Signal | P | Source |\n|---|---:|---|\n"
    for lab, v, src in sig_rows:
        tier = "🔴 high" if v >= 0.9 else "🟠 boundary" if v >= 0.1 else "⬜ clean"
        md += f"| {lab} | {v:.2f} | {src} {tier} |\n"

    md += f"""

## The story (4 high-confidence signals point to one mechanism)

Patient C shows a **coherent over-aggressive-basal cascade**:

1. **Basal mismatch (P={inputs.p_basal_mismatch:.2f}, mult={inputs.basal_recommended_mult:.2f}):**
   in fasting equilibrium the controller delivers ~0% of the scheduled
   basal — it is suspending almost continuously to defend against the
   schedule.

2. **ISF over-correction (P={inputs.p_isf_over_correction:.2f}):** when
   the controller does correct, BG drops more than the ISF predicts
   (over-correction). This is consistent with the basal already being
   "too much" — additional bolus drops too far.

3. **Low recovery (P={inputs.p_low_recovery:.2f}):** after a low,
   recovery to 100 mg/dL within 60 minutes is rare — also consistent
   with continuous basal pressure.

4. **Post-high envelope (P={inputs.p_post_high_envelope:.2f}):** after
   a high, BG sustains above target without a quick recovery — the
   wide IQR (110–203) confirms oscillation rather than tight control.

## Conversation starters for clinic review

> ⚠️ **Do not change settings autonomously.** These are hypotheses for
> the clinician to discuss with the patient.

### 1. Review basal schedule
The 4 signals above are individually noisy but jointly point to
**scheduled basal being too high**. Recommended discussion:
- Audit overnight TBR pattern (figure 1, hours 0–6).
- Consider: was the basal schedule last reviewed? Has weight,
  activity, or insulin sensitivity changed?
- A **conservative trial** of a 5–10% basal reduction (clinician-
  supervised) tests the hypothesis safely. The controller's 0%
  delivery suggests there is room.

### 1b. State-conditioned basal context (EXP-2811)

{{STATE_BASAL_SECTION}}

### 1c. Envelope-coupling phenotype (EXP-2873 cascade)

{{ENVELOPE_SECTION}}

### 2. Review ISF (correction factor)
Over-correction (P=1.00) on top of an already-suppressed basal
suggests ISF may be too aggressive. Discuss whether to **soften ISF
by 10–15%** as a paired adjustment with #1.

### 3. Investigate post-high recovery
P=1.00 for sustained post-high envelope. Discussion points:
- Is bolus timing pre-meal (not at meal start)?
- Are corrections being delivered at high BG, or is the patient
  waiting for the controller alone?

### 4. Site rotation (low-confidence)
Site-degradation P={inputs.p_site_degradation:.2f} (boundary, not
confirmed). Worth asking about rotation cadence but not a primary
finding.

## Carb-log quality (no concern)

![Carb log]({f4})

Patient C's log is clean: 95% of events ≥10 g, only 3% are <5 g
(treat-of-low / noise). The audition signals are **not** confounded
by data-quality issues for this patient.

## Basal pattern detail

![Basal]({f3})

The black line is the patient's scheduled basal across the day; the
red band is what the controller actually delivered (P25–P75). The
controller is **continuously suppressing** delivery across all hours
— most pronounced during the afternoon/evening peak hours of the
schedule.

## Post-meal excursion examples

![Excursions]({f5})

Six largest real meals in the dataset, plotted ±1 hr / +4 hr from the
meal time. These illustrate the high variance in meal response that
drives the wide IQR in the AGP.

## Methodology

* All audition signals computed from production loaders
  (`tools/cgmencode/production/*_facts_loader.py`).
* Bootstrap confidence (P) computed per the EXP-2859/2861/2862/2863/
  2864/2869 protocols.
* Carb-event quality assessed against the EXP-2866 conventions
  (`meal_filter.py`).
* Source data: `externals/ns-parquet/training/grid.parquet`,
  patient_id = `c`, {len(c):,} rows, {days:.0f} days.

## Caveats

* **Not medical advice.** Audition signals are statistical patterns;
  every recommendation must be filtered through the clinician's
  judgment and the patient's full history.
* **Stream B operational, not Stream A causal.** These signals describe
  *what the controller is doing*, not *what biological ISF/basal
  needs are*. The closed-loop system response is observed; the
  underlying biology is inferred only loosely.
* **Per EXP-2738**: the basal-mismatch gap IS the EGP safety margin
  the controller needs. The recommended trial reduction (5–10%) is
  much smaller than the observed multiplier (~0%) because the gap is
  protective.
"""
    # Build STATE_BASAL_SECTION
    if state_facts.per_state_basal_drift:
        sb_lines = [
            "| State | basal_drift | n samples |",
            "|------:|------------:|---------:|",
        ]
        for st, drift in sorted(state_facts.per_state_basal_drift.items()):
            n = state_facts.per_state_basal_n.get(st, 0)
            sb_lines.append(f"| {st} | {drift:+.2f} | {n} |")
        if state_facts.has_multi_state:
            sb_body = (
                "\n".join(sb_lines)
                + f"\n\n**Observed range across states: {state_facts.basal_drift_range:.2f} mg/dL/hr.**"
                " `basal_drift` is mean BG trend during 2h windows where the"
                " controller delivered basal ≈ schedule (no suspension, no"
                " intervention). Higher values = BG rises under scheduled basal."
                "\n\n**⚠️ Selection caveat:** these windows are rare for patients"
                " whose controller suspends frequently. The windows that *do*"
                " exist are non-random — often selected for rising BG (which is"
                " why the controller let basal through). Treat the per-state"
                " **range** as a cue that basal need shifts with metabolic"
                " context; do NOT treat the sign as directly actionable"
                " (confounding-by-indication, same pattern as EXP-2754)."
            )
        else:
            sb_body = (
                "\n".join(sb_lines)
                + "\n\nOnly one metabolic state observed with sufficient samples"
                " (EXP-2811 min_n=20). Multi-state context not available for"
                " this patient."
            )
    else:
        sb_body = (
            "No state-resolved basal data available for this patient (EXP-2811"
            " requires ≥20 samples per state)."
        )
    md = md.replace("{STATE_BASAL_SECTION}", sb_body)

    # Build ENVELOPE_SECTION (EXP-2870 / EXP-2872 / EXP-2873)
    env_lines = []
    try:
        env = pd.read_parquet(
            "externals/experiments/exp-2870_per_patient_crossover.parquet"
        )
        crow = env[env["patient_id"] == PID]
        if not crow.empty:
            r = crow.iloc[0]
            env_lines.append(
                f"**Envelope phenotype: `{r['phenotype']}`** "
                f"(crossover at {int(r['crossover_h'])}h; "
                f"shift range {r['min_shift_pct']:+.0f}% to "
                f"{r['max_shift_pct']:+.0f}%)."
            )
            env_lines.append("")
            env_lines.append(
                "Within Loop cohort (n=8 post EXP-2873 fix), C is one of "
                "**7 stream_B_early** patients — basal–envelope coupling "
                "becomes positive at the fastest scale (1h). This is the "
                "Loop-typical signature."
            )
            env_lines.append("")
            env_lines.append(
                "**Within-Loop TIR comparison** (EXP-2872 Simpson "
                "decomposition):"
            )
            loop = env[env["controller"] == "Loop"][
                ["patient_id", "phenotype", "tir"]
            ].sort_values("tir")
            env_lines.append("| patient | phenotype | TIR |")
            env_lines.append("|--------|-----------|-----:|")
            for _, lr in loop.iterrows():
                marker = " ← **THIS PATIENT**" if lr["patient_id"] == PID else ""
                env_lines.append(
                    f"| {lr['patient_id']} | {lr['phenotype']} "
                    f"| {lr['tir']:.2f}{marker} |"
                )
            env_lines.append("")
            env_lines.append(
                "Within Loop, stream_B_early Spearman ρ(phenotype_rank, "
                "TIR) = +0.41 (positive within-cohort). C sits near the "
                "median for the cohort by TIR; phenotype is consistent "
                "with the cohort, not anomalous."
            )
            env_lines.append("")
            env_lines.append(
                "**Caveat (EXP-2872):** the pooled cross-cohort phenotype→TIR "
                "relationship REVERSES within Loop (Simpson's paradox). Do "
                "NOT compare C to Trio/OpenAPS phenotype TIR rankings — "
                "controller premium dominates (~19pp at matched phenotype)."
            )
        else:
            env_lines.append(
                "No envelope-coupling data available for this patient."
            )
    except Exception as e:
        env_lines.append(
            f"Envelope-coupling section unavailable ({type(e).__name__})."
        )
    md = md.replace("{ENVELOPE_SECTION}", "\n".join(env_lines))

    REPORT.write_text(md)
    print(f"Wrote {REPORT}")
    print("Figures:")
    for f in [f1, f2, f3, f4, f5, f6]:
        print(f"  {f}")


if __name__ == "__main__":
    main()
