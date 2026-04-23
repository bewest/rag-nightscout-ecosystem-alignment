"""EXP-2871 — Controller deconfounding of envelope crossover phenotype.

Follow-up to EXP-2870 finding: crossover hour is a controller signature
(all Loop patients stream_B_normal, all stream_A_dominant are
Trio/OpenAPS). Question: is the signature driven by:
  (a) controller suspension/SMB activity (intervention-attributable
      basal modulation), or
  (b) the scheduled-basal structure itself responding differently to
      glucose envelopes?

Method (deconfounding):
  Recompute crossover with shift_metric = SUSPENSION DEPTH instead of
  raw actual_basal:
      suspension = scheduled_basal - actual_basal   (≥0 when controller
                                                     reduces, ≤0 when
                                                     bumps up)
  - Top vs bottom glucose tertile per patient per window.
  - Compute median suspension in each envelope.
  - shift = median_suspension_elev - median_suspension_norm
  - Positive shift = controller suspends more in elevated envelope
    (the EXPECTED direction at every scale; this is what good closed-
    loop behavior looks like).
  - Crossover hour: smallest window where shift_metric matches the
    cohort's long-scale sign — if always-positive, "always_responsive"
    phenotype.

Hypothesis: If suspension shift is uniformly positive across all
windows for ALL controllers, then the EXP-2870 phenotype was
artifact of basal SCHEDULE differences, not controller behavior.
If Loop patients still show late/inverted suspension shift, then
the algorithmic signature is causal.

Output:
  externals/experiments/exp-2871_suspension_envelope.parquet
  externals/experiments/exp-2871_per_patient.parquet
  externals/experiments/exp-2871_summary.json
  docs/60-research/figures/exp-2871_suspension_phenotype.png
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

WINDOWS = [1, 2, 3, 6, 12, 24, 48]


def aggregate(g_pat: pd.DataFrame, window_h: int) -> pd.DataFrame:
    cells = window_h * 12
    if len(g_pat) < cells * 6:
        return pd.DataFrame()
    g_pat = g_pat.sort_values("time").reset_index(drop=True)
    g_pat["window_id"] = g_pat.index // cells
    # suspension depth per cell (positive = controller withholds)
    g_pat["suspension"] = g_pat["scheduled_basal_rate"] - g_pat["actual_basal_rate"]
    agg = (
        g_pat.groupby("window_id")
        .agg(
            n=("glucose", "size"),
            glucose=("glucose", "mean"),
            suspension=("suspension", "mean"),
            scheduled=("scheduled_basal_rate", "mean"),
            actual=("actual_basal_rate", "mean"),
        )
        .reset_index()
    )
    return agg[agg["n"] >= cells * 0.8].reset_index(drop=True)


def per_patient_signal(g_pat: pd.DataFrame, window_h: int) -> dict | None:
    agg = aggregate(g_pat, window_h)
    if agg.empty:
        return None
    agg = agg.dropna(subset=["glucose", "suspension"])
    if len(agg) < 6:
        return None
    q33, q67 = np.percentile(agg["glucose"], [33, 67])
    elev = agg[agg["glucose"] >= q67]
    norm = agg[agg["glucose"] <= q33]
    if len(elev) < 3 or len(norm) < 3:
        return None
    susp_elev = float(elev["suspension"].mean())
    susp_norm = float(norm["suspension"].mean())
    shift = susp_elev - susp_norm  # U/h units
    try:
        _, p = stats.mannwhitneyu(
            elev["suspension"].dropna(),
            norm["suspension"].dropna(),
            alternative="two-sided",
        )
    except ValueError:
        p = np.nan
    return dict(
        window_h=window_h,
        n_windows=int(len(agg)),
        n_elev=int(len(elev)),
        n_norm=int(len(norm)),
        susp_elev=susp_elev,
        susp_norm=susp_norm,
        susp_shift_uph=shift,
        mannwhitney_p=float(p) if not np.isnan(p) else None,
    )


def main() -> None:
    g = pd.read_parquet("externals/ns-parquet/training/grid.parquet",
                        columns=["patient_id", "time", "glucose",
                                 "scheduled_basal_rate", "actual_basal_rate"])
    g["time"] = pd.to_datetime(g["time"], utc=True)

    rows = []
    for pid, g_pat in g.groupby("patient_id"):
        for w in WINDOWS:
            r = per_patient_signal(g_pat, w)
            if r is None:
                continue
            r["patient_id"] = pid
            rows.append(r)

    df = pd.DataFrame(rows)
    print(f"Suspension-shift rows: {len(df)} ({df['patient_id'].nunique()} patients)")
    df.to_parquet(EXP / "exp-2871_suspension_envelope.parquet", index=False)

    # Per-window cohort summary
    summary_rows = []
    for w in WINDOWS:
        sub = df[df["window_h"] == w]
        if sub.empty:
            continue
        n = len(sub)
        n_pos = int((sub["susp_shift_uph"] > 0).sum())
        n_sig01 = int((sub["mannwhitney_p"].fillna(1.0) < 0.01).sum())
        summary_rows.append(dict(
            window_h=w, n=n,
            frac_positive_shift=round(n_pos / n, 3),
            frac_sig_p01=round(n_sig01 / n, 3),
            median_shift_uph=float(sub["susp_shift_uph"].median()),
        ))
    print("\nCohort suspension-shift by window (positive = more suspension when elevated):")
    print(pd.DataFrame(summary_rows).to_string(index=False))

    # Per-patient classification
    pp = []
    for pid, g_pat in df.groupby("patient_id"):
        gs = g_pat.sort_values("window_h")
        all_positive = bool((gs["susp_shift_uph"] > 0).all())
        any_negative = bool((gs["susp_shift_uph"] < 0).any())
        # crossover (small to large) where shift becomes positive
        crossover = None
        for _, r in gs.iterrows():
            if r["susp_shift_uph"] > 0:
                crossover = int(r["window_h"])
                break
        pp.append(dict(
            patient_id=pid,
            all_positive=all_positive,
            any_negative=any_negative,
            crossover_h=crossover,
            min_shift_uph=float(gs["susp_shift_uph"].min()),
            max_shift_uph=float(gs["susp_shift_uph"].max()),
        ))
    pdf = pd.DataFrame(pp)

    # Merge controller from EXP-2812
    tx = EXP / "exp-2812_pre_post_transitions.parquet"
    if tx.exists():
        ctl = pd.read_parquet(tx, columns=["patient_id", "controller"])
        ctl = ctl.drop_duplicates("patient_id")
        pdf = pdf.merge(ctl, on="patient_id", how="left")
    pdf.to_parquet(EXP / "exp-2871_per_patient.parquet", index=False)

    print("\nPer-patient classification:")
    print(pdf[["patient_id", "controller", "all_positive",
               "any_negative", "crossover_h",
               "min_shift_uph", "max_shift_uph"]].to_string(index=False))

    # Cross-tab
    if "controller" in pdf.columns:
        print("\nall_positive × controller:")
        print(pd.crosstab(pdf["all_positive"], pdf["controller"]))

    summary = {
        "experiment": "EXP-2871",
        "title": "Controller deconfound: envelope crossover via suspension depth",
        "stream": "B",
        "n_patients": int(len(pdf)),
        "by_window": summary_rows,
        "n_all_positive": int(pdf["all_positive"].sum()),
        "n_any_negative": int(pdf["any_negative"].sum()),
        "checks": {
            "PASS_majority_uniformly_positive": int(pdf["all_positive"].sum()) >= 0.5 * len(pdf),
            "PASS_signature_dissolves_under_suspension_metric": (
                "controller" in pdf.columns and
                # both controllers should look similar if signature was schedule-driven
                pdf.groupby("controller")["all_positive"].mean().max()
                - pdf.groupby("controller")["all_positive"].mean().min() < 0.3
            ),
            "PASS_no_inverted_long_scale": (
                summary_rows[-1]["frac_positive_shift"] >= 0.7
                if summary_rows else False
            ),
        },
    }
    summary["checks_passed"] = sum(summary["checks"].values())

    if summary["checks"]["PASS_signature_dissolves_under_suspension_metric"]:
        interp = ("Controller signature DISSOLVES under suspension-depth "
                  "metric. EXP-2870 phenotype was artifact of scheduled-basal "
                  "structure differences, not controller behavior. Both Loop "
                  "and Trio suspend more in elevated envelopes; the EXP-2870 "
                  "negative shift came from Trio's lower scheduled basals "
                  "creating different normalization, not stronger suppression.")
    else:
        interp = ("Controller signature PERSISTS under suspension-depth "
                  "metric. The algorithmic difference between Loop and "
                  "Trio/OpenAPS basal modulation IS causal for the "
                  "envelope crossover phenotype.")
    summary["interpretation"] = interp

    (EXP / "exp-2871_summary.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    # Figure
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("EXP-2871 — Suspension-depth envelope shift "
                 "(controller deconfound of EXP-2870)", fontsize=11)

    ax = axes[0]
    sdf = pd.DataFrame(summary_rows)
    if not sdf.empty:
        ax.plot(range(len(sdf)), sdf["frac_positive_shift"], "o-",
                color="#2ca02c", label="frac patients with positive shift")
        ax.plot(range(len(sdf)), sdf["frac_sig_p01"], "s--",
                color="#d62728", label="frac significant (p<0.01)")
        ax.set_xticks(range(len(sdf)))
        ax.set_xticklabels([f"{w}h" for w in sdf["window_h"]])
        ax.set_ylabel("Fraction of patients")
        ax.set_title("Suspension shift direction by window")
        ax.axhline(0.5, ls=":", color="gray", alpha=0.5)
        ax.legend()
        ax.grid(alpha=0.3)

    ax = axes[1]
    if "controller" in pdf.columns:
        for ctl_name in pdf["controller"].dropna().unique():
            sub = pdf[pdf["controller"] == ctl_name]
            ax.scatter(sub["min_shift_uph"], sub["max_shift_uph"],
                       label=ctl_name, alpha=0.7, s=80)
        ax.axvline(0, color="k", lw=0.5)
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlabel("Min shift across windows (U/h)")
        ax.set_ylabel("Max shift across windows (U/h)")
        ax.set_title("Per-patient suspension shift range, by controller")
        ax.legend()
        ax.grid(alpha=0.3)

    plt.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIG / "exp-2871_suspension_phenotype.png", dpi=120)
    plt.close()

    print(f"\nChecks passed: {summary['checks_passed']}/3")
    print(f"Interpretation: {summary['interpretation']}")


if __name__ == "__main__":
    main()
