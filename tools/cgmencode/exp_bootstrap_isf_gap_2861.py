"""EXP-2861 — Bootstrap confidence on per-patient ISF gap.

Generalizes EXP-2859's bootstrap-confidence-replaces-boolean pattern
to the ISF gap signal (EXP-2847). Per-patient bootstrap resample of
correction events; quantify P(under_correction) and P(over_correction)
for use in audition severity gating.

Audition currently fires:
  - isf_under_correction when isf_gap_pct < -10
  - isf_over_correction  when isf_gap_pct > +30

These thresholds applied to a single point estimate are noisy when
N(corrections) is small. Bootstrap gives explicit per-patient
confidence in each direction.

Charter B compliant.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"

EVENTS = EXPDIR / "exp-2847_correction_events.parquet"

N_BOOT = 500
RNG_SEED = 2861
THRESH_UNDER = -10.0
THRESH_OVER = +30.0
MIN_EVENTS = 20


def isf_gap_pct(row_obs, row_sched):
    if row_sched <= 0:
        return np.nan
    return 100.0 * (row_obs - row_sched) / row_sched


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    ev = pd.read_parquet(EVENTS)
    # Filter to events with non-zero drop and bolus to get meaningful ISF
    ev = ev[(ev["drop"] > 0) & (ev["bolus"] > 0) & (ev["sched_isf"] > 0)]
    ev["gap_pct"] = 100.0 * (ev["obs_isf"] - ev["sched_isf"]) / ev["sched_isf"]

    rows = []
    for pid, g in ev.groupby("patient_id"):
        if len(g) < MIN_EVENTS:
            continue
        gaps = g["gap_pct"].to_numpy()
        gaps = gaps[~np.isnan(gaps)]
        n = len(gaps)
        if n < MIN_EVENTS:
            continue
        # Point estimate
        point_med = float(np.median(gaps))
        # Bootstrap medians
        boot_meds = np.array([
            np.median(gaps[rng.integers(0, n, size=n)])
            for _ in range(N_BOOT)
        ])
        rows.append({
            "patient_id": pid,
            "n_events": int(n),
            "point_median_gap_pct": point_med,
            "boot_median_mean": float(boot_meds.mean()),
            "boot_median_ci_lo": float(np.quantile(boot_meds, 0.025)),
            "boot_median_ci_hi": float(np.quantile(boot_meds, 0.975)),
            "p_under_correction": float(np.mean(boot_meds < THRESH_UNDER)),
            "p_over_correction": float(np.mean(boot_meds > THRESH_OVER)),
            "p_within_band": float(np.mean(
                (boot_meds >= THRESH_UNDER) & (boot_meds <= THRESH_OVER)
            )),
        })
    out = pd.DataFrame(rows)
    out.to_parquet(EXPDIR / "exp-2861_bootstrap_isf_gap.parquet", index=False)

    # Categorize each patient
    def _band(r):
        if r["p_under_correction"] >= 0.9:
            return "confident_under"
        if r["p_over_correction"] >= 0.9:
            return "confident_over"
        if r["p_within_band"] >= 0.9:
            return "confident_neutral"
        return "uncertain"

    out["band"] = out.apply(_band, axis=1)
    band_counts = out["band"].value_counts().to_dict()

    # Compare to point-estimate naive classification
    def _naive(r):
        if r["point_median_gap_pct"] < THRESH_UNDER:
            return "naive_under"
        if r["point_median_gap_pct"] > THRESH_OVER:
            return "naive_over"
        return "naive_neutral"

    out["naive_band"] = out.apply(_naive, axis=1)
    naive_counts = out["naive_band"].value_counts().to_dict()

    summary = {
        "exp": "EXP-2861",
        "method": (
            f"Per-patient bootstrap (N={N_BOOT}) of correction events from "
            "EXP-2847; bootstrap medians of isf_gap_pct quantify "
            "P(under_correction<-10%) and P(over_correction>+30%)."
        ),
        "n_patients": int(len(out)),
        "thresholds": {"under_pct": THRESH_UNDER, "over_pct": THRESH_OVER},
        "min_events_required": MIN_EVENTS,
        "bootstrap_band_counts": {str(k): int(v) for k, v in band_counts.items()},
        "naive_point_band_counts": {str(k): int(v) for k, v in naive_counts.items()},
        "median_n_events": int(out["n_events"].median()) if len(out) else 0,
        "median_ci_width_pct": float(
            (out["boot_median_ci_hi"] - out["boot_median_ci_lo"]).median()
        ) if len(out) else None,
        "interpretation": [
            "P(under_correction)>=0.9 → confident under-correction; emit medium severity.",
            "P(over_correction)>=0.9 → confident over-correction; emit medium severity.",
            "P(within_band)>=0.9 → confident neutral; suppress flag.",
            "Otherwise → uncertain; emit low severity (acknowledge ambiguity).",
        ],
    }
    (EXPDIR / "exp-2861_summary.json").write_text(json.dumps(summary, indent=2))

    # Visualization
    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        # Histogram of point medians and bootstrap CI as horizontal bar
        out_sorted = out.sort_values("point_median_gap_pct").reset_index(drop=True)
        y = np.arange(len(out_sorted))
        ax.errorbar(
            out_sorted["boot_median_mean"], y,
            xerr=[out_sorted["boot_median_mean"] - out_sorted["boot_median_ci_lo"],
                  out_sorted["boot_median_ci_hi"] - out_sorted["boot_median_mean"]],
            fmt="o", color="#4472C4", ecolor="grey", capsize=2, alpha=0.85,
        )
        ax.axvline(THRESH_UNDER, color="orange", linestyle="--",
                   label=f"under {THRESH_UNDER}%")
        ax.axvline(THRESH_OVER, color="red", linestyle="--",
                   label=f"over {THRESH_OVER}%")
        ax.axvline(0, color="black", linewidth=0.5)
        ax.set_xlabel("ISF gap % (median, bootstrap 95% CI)")
        ax.set_ylabel("patient (sorted by point median)")
        ax.set_title(f"Per-patient ISF gap with bootstrap CI (n={len(out)})")
        ax.legend(fontsize=9)

        ax = axes[1]
        # Stacked bar chart: bootstrap vs naive
        bands = ["confident_under", "confident_over", "confident_neutral", "uncertain"]
        bvals = [band_counts.get(b, 0) for b in bands]
        nvals_map = {"naive_under": "confident_under",
                     "naive_over": "confident_over",
                     "naive_neutral": "confident_neutral"}
        nvals = [naive_counts.get(k, 0) for k in
                 ["naive_under", "naive_over", "naive_neutral"]] + [0]
        x = np.arange(len(bands))
        w = 0.35
        ax.bar(x - w/2, nvals, w, label="naive (point estimate)",
               color="#A0A0A0", edgecolor="black")
        ax.bar(x + w/2, bvals, w, label="bootstrap (P>=0.9)",
               color="#4472C4", edgecolor="black")
        ax.set_xticks(x)
        ax.set_xticklabels(["under", "over", "neutral", "uncertain"])
        ax.set_ylabel("patient count")
        ax.set_title("Bootstrap vs naive classification")
        ax.legend(fontsize=9)

        fig.suptitle(
            "EXP-2861: bootstrap-confidence ISF gap — generalizes EXP-2859 pattern",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2861_bootstrap_isf_gap.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
