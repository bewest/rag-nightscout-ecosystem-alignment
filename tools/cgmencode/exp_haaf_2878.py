"""EXP-2878 — HAAF detection via hypo exposure vs counter-regulation.

Hypothesis: HAAF (hypoglycemia-associated autonomic failure) predicts that
patients with higher hypo exposure (more frequent / longer hypos) will show
WEAKER counter-regulation: lower EXP-2875 intercept and/or lower EXP-2877
beta_nadir slope.

Method:
  1. Per-patient hypo exposure metrics from grid.parquet:
     - hypo_fraction: fraction of 5-min cells with glucose<70
     - severe_fraction: fraction <55
     - n_hypo_events: events from EXP-2875 parquet (rescue-free hypos)
  2. Per-patient counter-reg signals from EXP-2877 per-patient parquet:
     - intercept (baseline response)
     - beta_nadir (dose-response slope)
  3. Spearman correlation with directional hypothesis test.

HAAF prediction: negative correlation on both signals.

Output: externals/experiments/exp-2878_haaf.parquet + _summary.json + figure.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

GRID = ROOT / "externals/ns-parquet/training/grid.parquet"
PP_2877 = ROOT / "externals/experiments/exp-2877_per_patient.parquet"
EV_2875 = ROOT / "externals/experiments/exp-2875_counter_regulation_events.parquet"

OUT_PARQUET = ROOT / "externals/experiments/exp-2878_haaf.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2878_haaf_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2878_haaf.png"


def build_exposure(grid: pd.DataFrame) -> pd.DataFrame:
    g = grid.dropna(subset=["glucose"]).copy()
    total = g.groupby("patient_id").size().rename("n_cells")
    hypo = (g[g.glucose < 70].groupby("patient_id").size().rename("n_hypo"))
    severe = (g[g.glucose < 55].groupby("patient_id").size().rename("n_severe"))
    df = pd.concat([total, hypo, severe], axis=1).fillna(0.0)
    df["hypo_fraction"] = df.n_hypo / df.n_cells
    df["severe_fraction"] = df.n_severe / df.n_cells
    df["hypo_hours"] = df.n_hypo * 5.0 / 60.0
    df["severe_hours"] = df.n_severe * 5.0 / 60.0
    return df


def main() -> None:
    print("Loading grid...")
    grid = pd.read_parquet(GRID, columns=["patient_id", "glucose"])
    print(f"  cells={len(grid):,} patients={grid.patient_id.nunique()}")

    print("Computing hypo exposure per patient...")
    exposure = build_exposure(grid)

    print("Loading EXP-2877 per-patient signals...")
    pp = pd.read_parquet(PP_2877).set_index("patient_id")

    print("Loading EXP-2875 event counts...")
    ev = pd.read_parquet(EV_2875)
    n_events = ev.groupby("patient_id").size().rename("n_rescue_free_events")
    total_rise_time = (
        ev.groupby("patient_id").duration_min.sum().rename("total_rise_minutes")
    )

    df = (
        pp.join(exposure, how="left")
        .join(n_events, how="left")
        .join(total_rise_time, how="left")
    )
    df = df.dropna(subset=["hypo_fraction", "intercept", "beta_nadir"])
    print(f"  merged n_patients={len(df)}")

    summary: dict = {
        "exp_id": "2878",
        "n_patients": int(len(df)),
        "correlations": {},
    }

    pairs = [
        ("hypo_fraction", "intercept"),
        ("hypo_fraction", "beta_nadir"),
        ("severe_fraction", "intercept"),
        ("severe_fraction", "beta_nadir"),
        ("n_hypo", "intercept"),
        ("n_hypo", "beta_nadir"),
    ]
    for x, y in pairs:
        vx = df[x].values
        vy = df[y].values
        rho, p = stats.spearmanr(vx, vy)
        pear_r, pear_p = stats.pearsonr(vx, vy)
        summary["correlations"][f"{x}_vs_{y}"] = {
            "spearman_rho": float(rho),
            "spearman_p": float(p),
            "pearson_r": float(pear_r),
            "pearson_p": float(pear_p),
        }
        print(f"  {x:20s} vs {y:10s}  rho={rho:+.3f} p={p:.3g}")

    df.to_parquet(OUT_PARQUET)

    # 6-panel figure
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    axes = axes.flatten()
    panel_specs = [
        ("hypo_fraction", "intercept", "Hypo fraction", "Counter-reg intercept"),
        ("severe_fraction", "intercept", "Severe-hypo fraction", "Counter-reg intercept"),
        ("n_hypo", "intercept", "Total hypo cells", "Counter-reg intercept"),
        ("hypo_fraction", "beta_nadir", "Hypo fraction", "β_nadir (dose-response)"),
        ("severe_fraction", "beta_nadir", "Severe-hypo fraction", "β_nadir"),
        ("n_hypo", "beta_nadir", "Total hypo cells", "β_nadir"),
    ]
    for ax, (x, y, xlabel, ylabel) in zip(axes, panel_specs):
        colors = df.controller.map(
            {"Loop": "tab:blue", "Trio": "tab:orange", "OpenAPS": "tab:green"}
        ).fillna("gray")
        ax.scatter(df[x], df[y], c=colors, s=60, alpha=0.8, edgecolor="k")
        rho = summary["correlations"][f"{x}_vs_{y}"]["spearman_rho"]
        p = summary["correlations"][f"{x}_vs_{y}"]["spearman_p"]
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(f"ρ={rho:+.2f} p={p:.2g}")
        ax.axhline(0, color="gray", lw=0.5)
        ax.grid(alpha=0.3)
    fig.suptitle(
        "EXP-2878 — HAAF: Hypo Exposure vs Counter-Regulation "
        f"(n={len(df)} patients)", fontsize=13
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)
    print(f"Saved figure: {OUT_FIG}")

    # Verdict logic: HAAF requires NEGATIVE correlations (more exposure -> weaker)
    # Use the strongest exposure signal (severe_fraction) against both targets.
    sev_int = summary["correlations"]["severe_fraction_vs_intercept"]
    sev_beta = summary["correlations"]["severe_fraction_vs_beta_nadir"]
    hf_int = summary["correlations"]["hypo_fraction_vs_intercept"]
    hf_beta = summary["correlations"]["hypo_fraction_vs_beta_nadir"]

    neg_count = sum(
        1 for c in (sev_int, sev_beta, hf_int, hf_beta)
        if c["spearman_rho"] < -0.2
    )
    sig_count = sum(
        1 for c in (sev_int, sev_beta, hf_int, hf_beta)
        if c["spearman_rho"] < 0 and c["spearman_p"] < 0.05
    )

    if sig_count >= 2:
        verdict = (
            f"HAAF DETECTED — {sig_count}/4 pairings show significant "
            f"negative correlation (exposure ↑ → counter-reg ↓). "
            "Supports hypoglycemia-associated autonomic failure."
        )
    elif neg_count >= 2:
        verdict = (
            f"WEAK HAAF SIGNAL — {neg_count}/4 pairings trend negative "
            f"(ρ<-0.2), {sig_count} significant. Directionally consistent "
            "with HAAF but underpowered at current cohort size."
        )
    elif neg_count == 0:
        verdict = (
            "NO HAAF SIGNAL — counter-regulation does not degrade with "
            "hypo exposure in this cohort. Alternative explanations: "
            "(a) AID minimizes exposure below HAAF threshold, "
            "(b) selection bias (survivor cohort), "
            "(c) HAAF requires longer cumulative exposure than observed."
        )
    else:
        verdict = (
            f"MIXED — {neg_count}/4 negative, {sig_count} significant; "
            "inconclusive."
        )

    summary["verdict"] = verdict
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"Saved summary: {OUT_SUMMARY}")
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
