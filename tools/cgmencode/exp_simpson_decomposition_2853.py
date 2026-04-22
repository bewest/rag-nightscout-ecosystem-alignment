"""EXP-2853 — Simpson-style decomposition: β_fast vs β_slow per patient.

Refines EXP-2852 by replacing percent-of-baseline normalization with
direct per-patient OLS slopes at two timescales:

  β_fast  = OLS(basal_t, glucose_t) at 5-min resolution
  β_slow  = OLS(<basal>_W, <glucose>_W) at 48h non-overlapping window means

If sign(β_fast) ≠ sign(β_slow): Simpson's paradox is present — the
within-window relationship has opposite sign from the between-window
relationship. This is the canonical confounding-by-feedback
signature: at 5-min, controller responds to glucose (reactive,
β_fast < 0 expected); at 48h, demand drives both (structural,
β_slow > 0 expected).

We also compute β_total at 5-min as the population OLS (== β_fast),
then express the variance partition:

  Var(glucose) = Var_within_window(glucose) + Var_between_window(glucose)

so a patient's observed slope partitions cleanly.

Charter B compliant. β_slow is operational — it describes how the
controller's measured delivery covaries with multi-day glucose state,
not metabolic biology.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"


def per_patient_decomposition(g: pd.DataFrame, window_h: int = 48) -> dict:
    """Compute β_fast (5-min) and β_slow (window-mean) for one patient."""
    g = g.sort_values("time").reset_index(drop=True)
    x = g["glucose"].to_numpy()
    y = g["actual_basal_rate"].to_numpy()

    if len(g) < 24 * 12 * 7:
        return {}

    fast = stats.linregress(x, y)

    # Window-mean aggregation
    win_size = window_h * 12  # 5-min steps
    n_full = len(g) // win_size
    if n_full < 4:
        return {}
    g_trim = g.iloc[: n_full * win_size]
    bg_w = g_trim["glucose"].to_numpy().reshape(n_full, win_size).mean(axis=1)
    ba_w = g_trim["actual_basal_rate"].to_numpy().reshape(n_full, win_size).mean(axis=1)
    if np.std(bg_w) < 1e-3 or np.std(ba_w) < 1e-6:
        return {}
    slow = stats.linregress(bg_w, ba_w)

    # Variance partition (informational)
    var_total = float(np.var(x))
    var_between = float(np.var(np.repeat(bg_w, win_size)[: len(x)]))
    var_within = max(0.0, var_total - var_between)
    frac_within = var_within / var_total if var_total > 0 else np.nan

    # Patient mean-basal scale for normalized magnitudes
    mean_basal = float(np.mean(y))

    # Convert slopes to "U/h per 50 mg/dL" — interpretable scale
    fast_uph_per_50 = float(fast.slope * 50)
    slow_uph_per_50 = float(slow.slope * 50)
    fast_pct = (
        100.0 * fast_uph_per_50 / mean_basal if mean_basal > 0 else np.nan
    )
    slow_pct = (
        100.0 * slow_uph_per_50 / mean_basal if mean_basal > 0 else np.nan
    )

    simpson = bool(
        np.sign(fast.slope) != np.sign(slow.slope)
        and abs(fast.slope) > 1e-6
        and abs(slow.slope) > 1e-6
    )

    return {
        "n_samples": int(len(g)),
        "n_windows": int(n_full),
        "mean_basal_uph": mean_basal,
        "beta_fast_uph_per_mgdl": float(fast.slope),
        "beta_fast_pvalue": float(fast.pvalue),
        "beta_slow_uph_per_mgdl": float(slow.slope),
        "beta_slow_pvalue": float(slow.pvalue),
        "beta_fast_uph_per_50mgdl": fast_uph_per_50,
        "beta_slow_uph_per_50mgdl": slow_uph_per_50,
        "beta_fast_pct_of_mean": fast_pct,
        "beta_slow_pct_of_mean": slow_pct,
        "frac_variance_within_window": float(frac_within),
        "simpson_paradox": simpson,
    }


def main() -> None:
    cols = ["patient_id", "time", "glucose", "actual_basal_rate"]
    df = pd.read_parquet(GRID, columns=cols).dropna(
        subset=["glucose", "actual_basal_rate"]
    )

    rows = []
    for pid, g in df.groupby("patient_id", sort=False):
        d = per_patient_decomposition(g, window_h=48)
        if not d:
            continue
        d["patient_id"] = pid
        rows.append(d)

    out = pd.DataFrame(rows)
    out_path = EXPDIR / "exp-2853_simpson_decomposition.parquet"
    out.to_parquet(out_path, index=False)

    # Cohort summary
    n = len(out)
    n_simpson = int(out["simpson_paradox"].sum())
    n_fast_neg = int((out["beta_fast_uph_per_mgdl"] < 0).sum())
    n_slow_pos = int((out["beta_slow_uph_per_mgdl"] > 0).sum())
    summary = {
        "exp": "EXP-2853",
        "method": (
            "Per-patient OLS slopes: β_fast = OLS(basal_t, glucose_t) at 5-min; "
            "β_slow = OLS(<basal>_W, <glucose>_W) at 48h window means. "
            "Simpson's paradox = sign(β_fast) ≠ sign(β_slow)."
        ),
        "n_patients": n,
        "n_simpson_paradox": n_simpson,
        "frac_simpson_paradox": float(n_simpson / n) if n else 0.0,
        "n_fast_negative_reactive": n_fast_neg,
        "n_slow_positive_structural": n_slow_pos,
        "median_beta_fast_uph_per_50mgdl": float(
            out["beta_fast_uph_per_50mgdl"].median()
        ),
        "median_beta_slow_uph_per_50mgdl": float(
            out["beta_slow_uph_per_50mgdl"].median()
        ),
        "median_beta_fast_pct_of_mean": float(
            out["beta_fast_pct_of_mean"].median()
        ),
        "median_beta_slow_pct_of_mean": float(
            out["beta_slow_pct_of_mean"].median()
        ),
        "median_frac_within_variance": float(
            out["frac_variance_within_window"].median()
        ),
        "interpretation_keys": [
            "n_simpson_paradox tells us how many patients have reactive vs "
            "structural sign mismatch — these are the deconfounding-relevant ones",
            "median_beta_fast (per 50 mg/dL) is the typical reactive amplitude in U/h",
            "median_beta_slow (per 50 mg/dL) is the typical structural amplitude in U/h",
            "frac_variance_within reveals how much of the glucose signal lives at fast scales",
        ],
    }
    out_json = EXPDIR / "exp-2853_summary.json"
    out_json.write_text(json.dumps(summary, indent=2))

    # Visualization
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

        ax = axes[0]
        ax.scatter(
            out["beta_fast_uph_per_50mgdl"],
            out["beta_slow_uph_per_50mgdl"],
            s=60,
            c=["#C0504D" if s else "#4472C4" for s in out["simpson_paradox"]],
            edgecolor="black",
            alpha=0.8,
        )
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.axvline(0, color="gray", linewidth=0.5)
        # quadrant labels
        lim = max(
            out["beta_fast_uph_per_50mgdl"].abs().max(),
            out["beta_slow_uph_per_50mgdl"].abs().max(),
        ) * 1.2
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.text(lim * 0.6, lim * 0.85, "STRUCTURAL+\n(reactive+ too)",
                fontsize=8, alpha=0.7)
        ax.text(-lim * 0.95, lim * 0.85, "STRUCTURAL+\n(reactive- = Simpson)",
                fontsize=8, alpha=0.7, color="#C0504D")
        ax.text(-lim * 0.95, -lim * 0.95, "STRUCTURAL-\n(reactive- too)",
                fontsize=8, alpha=0.7)
        ax.text(lim * 0.6, -lim * 0.95, "STRUCTURAL-\n(reactive+ = Simpson)",
                fontsize=8, alpha=0.7, color="#C0504D")
        ax.set_xlabel("β_fast (U/h per +50 mg/dL) — REACTIVE arrow")
        ax.set_ylabel("β_slow (U/h per +50 mg/dL) — STRUCTURAL arrow")
        ax.set_title(
            f"Simpson decomposition — {n_simpson}/{n} patients show sign mismatch"
        )

        ax = axes[1]
        # Histogram comparing magnitudes
        bins = np.linspace(-0.6, 0.6, 25)
        ax.hist(
            out["beta_fast_uph_per_50mgdl"], bins=bins, alpha=0.5,
            color="#4472C4", label=f"β_fast (median {out['beta_fast_uph_per_50mgdl'].median():+.3f})",
        )
        ax.hist(
            out["beta_slow_uph_per_50mgdl"], bins=bins, alpha=0.5,
            color="#ED7D31", label=f"β_slow (median {out['beta_slow_uph_per_50mgdl'].median():+.3f})",
        )
        ax.axvline(0, color="black", linewidth=0.5)
        ax.set_xlabel("β (U/h per +50 mg/dL)")
        ax.set_ylabel("Patient count")
        ax.set_title("Distribution of reactive vs structural slopes")
        ax.legend(fontsize=9)

        fig.suptitle(
            "EXP-2853: per-patient β_fast (5-min reactive) vs β_slow (48h structural)",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2853_simpson_decomposition.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
