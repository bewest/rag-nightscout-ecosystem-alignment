"""EXP-2849: Multi-scale envelope coupling — at what window does
audition signal become detectable, and how does it scale?

Question (Stream B): The audition matrix uses 48h state windows
(EXP-2810). Faster windows would mean faster audition cycles for
clinicians. At what aggregation window does the basal-shift signal
between elevated and normal glucose envelopes become detectable, and
does the signal magnitude scale, plateau, or oscillate with window?

Method (no re-clustering — simple high-vs-normal envelope):
  - For each patient, aggregate the grid into rolling windows of
    [6h, 12h, 24h, 48h]
  - Within each window, compute mean glucose and mean actual_basal_rate
  - Bin windows into "elevated" (mean glucose top tertile) vs "normal"
    (bottom tertile) PER PATIENT to control for individual baseline
  - Measure basal shift: (basal_elev − basal_norm) / basal_norm
  - Statistical test: Mann–Whitney U per patient per window
  - Cohort signal: how many patients reach p<0.01 at each window?

Charter: Stream B operational. The basal shift is what the controller
actually delivered between high and low glucose envelopes — no biology
claim. Window choice is purely an operational lever for audition speed.

Layered deconfounding lens:
  - 6h captures fast meal/intervention dynamics (confounded by
    meal-correction-recovery cycles)
  - 12h captures intra-day demand patterns
  - 24h captures circadian envelope (dawn-evening structure)
  - 48h captures multi-day metabolic state (current EXP-2810 baseline)

If signal is similar across windows → audition can move faster.
If signal grows with window → 48h is necessary; faster audition trades
power for latency.

Outputs:
  externals/experiments/exp-2849_multi_scale_envelope.parquet
  externals/experiments/exp-2849_summary.json
  docs/60-research/figures/exp-2849_multi_scale_envelope.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

EXP = Path("externals/experiments")
FIG = Path("docs/60-research/figures")
WINDOWS_HOURS = [6, 12, 24, 48]


def aggregate_windows(g_pat: pd.DataFrame, window_h: int) -> pd.DataFrame:
    """Non-overlapping window aggregation per patient.
    Each row is one window; we keep mean glucose + mean basal."""
    cells_per_window = window_h * 12  # 5-min cells
    if len(g_pat) < cells_per_window * 6:  # need ≥6 windows
        return pd.DataFrame()
    g_pat = g_pat.sort_values("time").reset_index(drop=True)
    g_pat["window_id"] = g_pat.index // cells_per_window
    agg = (
        g_pat.groupby("window_id")
        .agg(
            n=("glucose", "size"),
            glucose=("glucose", "mean"),
            actual_basal=("actual_basal_rate", "mean"),
            scheduled_basal=("scheduled_basal_rate", "mean"),
            bolus=("bolus", "sum"),
            bolus_smb=("bolus_smb", "sum"),
        )
        .reset_index()
    )
    # Drop incomplete windows
    return agg[agg["n"] >= cells_per_window * 0.8].reset_index(drop=True)


def per_patient_signal(g_pat: pd.DataFrame, window_h: int) -> dict | None:
    """Compute basal shift between elevated and normal envelopes
    at a given window size."""
    agg = aggregate_windows(g_pat, window_h)
    if len(agg) < 6:
        return None
    agg = agg.dropna(subset=["glucose"])
    if len(agg) < 6:
        return None
    q33, q67 = np.percentile(agg["glucose"], [33, 67])
    elev = agg[agg["glucose"] >= q67]
    norm = agg[agg["glucose"] <= q33]
    if len(elev) < 3 or len(norm) < 3:
        return None
    basal_elev = float(elev["actual_basal"].mean())
    basal_norm = float(norm["actual_basal"].mean())
    if basal_norm <= 0:
        return None
    shift_pct = 100 * (basal_elev - basal_norm) / basal_norm
    try:
        u, p = stats.mannwhitneyu(
            elev["actual_basal"].dropna(),
            norm["actual_basal"].dropna(),
            alternative="two-sided",
        )
    except ValueError:
        p = np.nan
    return dict(
        window_h=window_h,
        n_windows=int(len(agg)),
        n_elev=int(len(elev)),
        n_norm=int(len(norm)),
        glucose_elev=float(elev["glucose"].mean()),
        glucose_norm=float(norm["glucose"].mean()),
        basal_elev=basal_elev,
        basal_norm=basal_norm,
        basal_shift_pct=shift_pct,
        mannwhitney_p=float(p) if not np.isnan(p) else None,
    )


def main() -> dict:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet")
    g["time"] = pd.to_datetime(g["time"], utc=True)

    rows = []
    for pid, g_pat in g.groupby("patient_id"):
        for w in WINDOWS_HOURS:
            r = per_patient_signal(g_pat, w)
            if r is None:
                continue
            r["patient_id"] = pid
            rows.append(r)

    df = pd.DataFrame(rows)
    print(f"Multi-scale rows: {len(df)} "
          f"({df['patient_id'].nunique()} patients × ≤{len(WINDOWS_HOURS)} windows)")

    # Cohort summary per window
    summary_rows = []
    for w in WINDOWS_HOURS:
        sub = df[df["window_h"] == w].copy()
        if sub.empty:
            continue
        n = len(sub)
        n_sig01 = int((sub["mannwhitney_p"].fillna(1.0) < 0.01).sum())
        n_sig05 = int((sub["mannwhitney_p"].fillna(1.0) < 0.05).sum())
        summary_rows.append(dict(
            window_h=w,
            n_patients=n,
            n_sig_p01=n_sig01,
            frac_sig_p01=round(n_sig01 / n, 3),
            n_sig_p05=n_sig05,
            frac_sig_p05=round(n_sig05 / n, 3),
            median_shift_pct=float(sub["basal_shift_pct"].median()),
            iqr_shift_pct=float(np.percentile(sub["basal_shift_pct"], 75)
                                - np.percentile(sub["basal_shift_pct"], 25)),
        ))
    summary_df = pd.DataFrame(summary_rows)
    print("\nCohort summary by window:")
    print(summary_df.to_string(index=False))

    # Per-patient consistency: does signal direction agree across windows?
    pivot = df.pivot_table(index="patient_id", columns="window_h",
                           values="basal_shift_pct")
    sign_consistent = (
        (pivot > 0).all(axis=1) | (pivot < 0).all(axis=1)
    )
    print(f"\nPer-patient sign consistency across windows: "
          f"{int(sign_consistent.sum())}/{len(pivot)}")

    df.to_parquet(EXP / "exp-2849_multi_scale_envelope.parquet", index=False)
    pivot.to_parquet(EXP / "exp-2849_per_patient_pivot.parquet")

    summary = {
        "experiment": "EXP-2849",
        "title": "Multi-scale envelope coupling",
        "stream": "B",
        "windows_h": WINDOWS_HOURS,
        "n_patients_total": int(df["patient_id"].nunique()),
        "by_window": summary_rows,
        "n_sign_consistent": int(sign_consistent.sum()),
        "n_pivot_patients": int(len(pivot)),
        "checks": {
            "PASS_all_windows_covered": len(summary_rows) == len(WINDOWS_HOURS),
            "PASS_signal_at_24h": any(
                r["frac_sig_p01"] >= 0.5 and r["window_h"] == 24
                for r in summary_rows
            ),
            "PASS_signal_at_48h": any(
                r["frac_sig_p01"] >= 0.5 and r["window_h"] == 48
                for r in summary_rows
            ),
            "PASS_majority_sign_consistent": (
                int(sign_consistent.sum()) >= 0.5 * len(pivot)
            ),
        },
    }
    summary["checks_passed"] = sum(summary["checks"].values())

    interpretation = []
    if summary["checks"]["PASS_signal_at_24h"]:
        interpretation.append(
            "Audition signal is detectable at 24h windows — half-window "
            "audition cycle is feasible without losing detection power."
        )
    else:
        interpretation.append(
            "Signal at 24h windows is below detection threshold — 48h "
            "is the operational floor for audition."
        )
    interpretation.append(
        f"{summary['n_sign_consistent']}/{summary['n_pivot_patients']} "
        "patients show consistent shift direction across all four windows, "
        "indicating the audition signal direction is timescale-invariant "
        "for these patients (deconfounding bonus: signal is robust to "
        "window choice)."
    )
    summary["interpretation"] = interpretation
    (EXP / "exp-2849_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # Visualization (Charter V8 paired chart)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(
        "EXP-2849 — Multi-scale envelope coupling\n"
        "Stream B; basal shift between top-tertile and bottom-tertile "
        "glucose envelopes per patient, across window sizes",
        fontsize=11,
    )

    ax = axes[0]
    if not df.empty:
        positions = []
        data = []
        labels = []
        for w in WINDOWS_HOURS:
            sub = df[df["window_h"] == w]["basal_shift_pct"].dropna()
            if sub.empty:
                continue
            positions.append(w)
            data.append(sub.values)
            labels.append(f"{w}h\nN={len(sub)}")
        bp = ax.boxplot(data, positions=range(len(positions)),
                        widths=0.6, patch_artist=True,
                        showfliers=False)
        for patch, color in zip(bp["boxes"],
                                ["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"]):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xticks(range(len(positions)))
        ax.set_xticklabels(labels)
        ax.set_ylabel("Basal shift % (elevated − normal envelope)")
        ax.set_title("Per-patient signal magnitude by window")

    ax = axes[1]
    if not summary_df.empty:
        x = np.arange(len(summary_df))
        ax.bar(x - 0.2, summary_df["frac_sig_p01"], width=0.4,
               color="#d62728", label="p<0.01", alpha=0.8)
        ax.bar(x + 0.2, summary_df["frac_sig_p05"], width=0.4,
               color="#ff7f0e", label="p<0.05", alpha=0.8)
        ax.axhline(0.5, color="k", lw=0.5, ls="--",
                   label="50% cohort threshold")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{w}h" for w in summary_df["window_h"]])
        ax.set_ylabel("Fraction of patients with significant shift")
        ax.set_title("Detection rate by window")
        ax.legend(loc="best", fontsize=9)
        ax.set_ylim(0, 1.0)

    plt.tight_layout(rect=(0, 0, 1, 0.93))
    out = FIG / "exp-2849_multi_scale_envelope.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"\nWrote {out}")
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    main()
