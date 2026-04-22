"""EXP-2862 — Bootstrap confidence on per-patient median recovery fraction.

Generalizes EXP-2859/2861 bootstrap-confidence pattern to the
state-transition recovery signal (EXP-2812).

Audition currently emits `flat_low_recovery` (HIGH severity) when
median_recovery_fraction < 0.4 and phenotype=flat. Single-point
median over (typically) ~13 transitions per patient is noisy; we
quantify P(low recovery) per patient via event bootstrap.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"

EVENTS = EXPDIR / "exp-2812_pre_post_transitions.parquet"

N_BOOT = 500
RNG_SEED = 2862
THRESH_LOW = 0.4
THRESH_HIGH = 0.7
MIN_EVENTS = 5


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    ev = pd.read_parquet(EVENTS)
    ev = ev[ev["recovery_fraction_3w"].notna()]

    rows = []
    for pid, g in ev.groupby("patient_id"):
        if len(g) < MIN_EVENTS:
            continue
        recs = g["recovery_fraction_3w"].to_numpy()
        n = len(recs)
        boot_meds = np.array([
            np.median(recs[rng.integers(0, n, size=n)])
            for _ in range(N_BOOT)
        ])
        rows.append({
            "patient_id": pid,
            "controller": g["controller"].iloc[0],
            "n_transitions": int(n),
            "point_median_recovery": float(np.median(recs)),
            "boot_median_mean": float(boot_meds.mean()),
            "boot_median_ci_lo": float(np.quantile(boot_meds, 0.025)),
            "boot_median_ci_hi": float(np.quantile(boot_meds, 0.975)),
            "p_low_recovery": float(np.mean(boot_meds < THRESH_LOW)),
            "p_high_recovery": float(np.mean(boot_meds > THRESH_HIGH)),
            "p_within_band": float(np.mean(
                (boot_meds >= THRESH_LOW) & (boot_meds <= THRESH_HIGH)
            )),
        })
    out = pd.DataFrame(rows)
    out.to_parquet(EXPDIR / "exp-2862_bootstrap_recovery.parquet", index=False)

    def _band(r):
        if r["p_low_recovery"] >= 0.9:
            return "confident_low"
        if r["p_high_recovery"] >= 0.9:
            return "confident_high"
        if r["p_within_band"] >= 0.9:
            return "confident_neutral"
        return "uncertain"

    def _naive(r):
        m = r["point_median_recovery"]
        if m < THRESH_LOW:
            return "naive_low"
        if m > THRESH_HIGH:
            return "naive_high"
        return "naive_neutral"

    out["band"] = out.apply(_band, axis=1)
    out["naive_band"] = out.apply(_naive, axis=1)
    band_counts = out["band"].value_counts().to_dict()
    naive_counts = out["naive_band"].value_counts().to_dict()

    summary = {
        "exp": "EXP-2862",
        "method": (
            f"Per-patient event bootstrap (N={N_BOOT}) of "
            "recovery_fraction_3w from EXP-2812 pre_post_transitions; "
            f"P(low<{THRESH_LOW}) and P(high>{THRESH_HIGH})."
        ),
        "n_patients": int(len(out)),
        "thresholds": {"low": THRESH_LOW, "high": THRESH_HIGH},
        "min_events_required": MIN_EVENTS,
        "bootstrap_band_counts": {str(k): int(v) for k, v in band_counts.items()},
        "naive_point_band_counts": {str(k): int(v) for k, v in naive_counts.items()},
        "median_n_transitions": int(out["n_transitions"].median()) if len(out) else 0,
        "median_ci_width": float(
            (out["boot_median_ci_hi"] - out["boot_median_ci_lo"]).median()
        ) if len(out) else None,
        "patient_b_p_low": (
            float(out[out["patient_id"] == "b"]["p_low_recovery"].iloc[0])
            if (out["patient_id"] == "b").any() else None
        ),
    }
    (EXPDIR / "exp-2862_summary.json").write_text(json.dumps(summary, indent=2))

    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        ax = axes[0]
        out_s = out.sort_values("point_median_recovery").reset_index(drop=True)
        y = np.arange(len(out_s))
        ax.errorbar(
            out_s["boot_median_mean"], y,
            xerr=[
                np.clip(out_s["boot_median_mean"] - out_s["boot_median_ci_lo"], 0, None),
                np.clip(out_s["boot_median_ci_hi"] - out_s["boot_median_mean"], 0, None),
            ],
            fmt="o", color="#4472C4", ecolor="grey", capsize=2, alpha=0.85,
        )
        ax.axvline(THRESH_LOW, color="orange", linestyle="--", label=f"low {THRESH_LOW}")
        ax.axvline(THRESH_HIGH, color="green", linestyle="--", label=f"high {THRESH_HIGH}")
        ax.set_xlabel("median recovery_fraction_3w (bootstrap 95% CI)")
        ax.set_ylabel("patient (sorted)")
        ax.set_title(f"Per-patient recovery fraction with bootstrap CI (n={len(out)})")
        ax.legend(fontsize=9)

        ax = axes[1]
        bands = ["confident_low", "confident_high", "confident_neutral", "uncertain"]
        bvals = [band_counts.get(b, 0) for b in bands]
        nvals = [naive_counts.get(k, 0) for k in
                 ["naive_low", "naive_high", "naive_neutral"]] + [0]
        x = np.arange(len(bands))
        w = 0.35
        ax.bar(x - w/2, nvals, w, label="naive (point estimate)",
               color="#A0A0A0", edgecolor="black")
        ax.bar(x + w/2, bvals, w, label="bootstrap (P>=0.9)",
               color="#4472C4", edgecolor="black")
        ax.set_xticks(x)
        ax.set_xticklabels(["low", "high", "neutral", "uncertain"])
        ax.set_ylabel("patient count")
        ax.set_title("Bootstrap vs naive classification")
        ax.legend(fontsize=9)

        fig.suptitle(
            "EXP-2862: bootstrap-confidence recovery fraction — generalizes EXP-2859 pattern",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2862_bootstrap_recovery.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
