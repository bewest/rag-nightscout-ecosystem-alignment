"""EXP-2864 — Bootstrap confidence on per-patient post-high envelope.

Generalizes EXP-2859/2861/2862/2863 bootstrap pattern to the fifth and
final naive-threshold audition signal: `post_high_mg_dl`. Computed
as median(post_mean_bg) − 110 (target) over post-transition windows
from EXP-2812. Naive flag fires when value > 25.
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
RNG_SEED = 2864
TARGET_MG_DL = 110.0
THRESH_HIGH = 25.0
MIN_EVENTS = 5


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    ev = pd.read_parquet(EVENTS).dropna(subset=["post_mean_bg"])

    rows = []
    for pid, g in ev.groupby("patient_id"):
        if len(g) < MIN_EVENTS:
            continue
        post = (g["post_mean_bg"].to_numpy() - TARGET_MG_DL)
        n = len(post)
        boot_meds = np.array([
            np.median(post[rng.integers(0, n, size=n)])
            for _ in range(N_BOOT)
        ])
        rows.append({
            "patient_id": pid,
            "n_transitions": int(n),
            "point_median_post_high": float(np.median(post)),
            "boot_median_mean": float(boot_meds.mean()),
            "boot_median_ci_lo": float(np.quantile(boot_meds, 0.025)),
            "boot_median_ci_hi": float(np.quantile(boot_meds, 0.975)),
            "p_post_high_envelope": float(np.mean(boot_meds > THRESH_HIGH)),
            "p_within_target": float(np.mean(boot_meds <= THRESH_HIGH)),
        })
    out = pd.DataFrame(rows)
    out.to_parquet(EXPDIR / "exp-2864_bootstrap_post_high.parquet", index=False)

    def _band(r):
        if r["p_post_high_envelope"] >= 0.9:
            return "confident_high"
        if r["p_within_target"] >= 0.9:
            return "confident_in_target"
        return "uncertain"

    def _naive(r):
        return "naive_high" if r["point_median_post_high"] > THRESH_HIGH else "naive_in_target"

    out["band"] = out.apply(_band, axis=1)
    out["naive_band"] = out.apply(_naive, axis=1)
    band_counts = out["band"].value_counts().to_dict()
    naive_counts = out["naive_band"].value_counts().to_dict()

    summary = {
        "exp": "EXP-2864",
        "method": (
            f"Per-patient event bootstrap (N={N_BOOT}) of "
            f"(post_mean_bg − {TARGET_MG_DL}) from EXP-2812; "
            f"P(envelope > {THRESH_HIGH} mg/dL)."
        ),
        "n_patients": int(len(out)),
        "threshold_mg_dl": THRESH_HIGH,
        "min_events_required": MIN_EVENTS,
        "bootstrap_band_counts": {str(k): int(v) for k, v in band_counts.items()},
        "naive_point_band_counts": {str(k): int(v) for k, v in naive_counts.items()},
        "median_n_transitions": int(out["n_transitions"].median()) if len(out) else 0,
        "median_ci_width_mg_dl": float(
            (out["boot_median_ci_hi"] - out["boot_median_ci_lo"]).median()
        ) if len(out) else None,
    }
    (EXPDIR / "exp-2864_summary.json").write_text(json.dumps(summary, indent=2))

    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        ax = axes[0]
        out_s = out.sort_values("point_median_post_high").reset_index(drop=True)
        y = np.arange(len(out_s))
        ax.errorbar(
            out_s["boot_median_mean"], y,
            xerr=[
                np.clip(out_s["boot_median_mean"] - out_s["boot_median_ci_lo"], 0, None),
                np.clip(out_s["boot_median_ci_hi"] - out_s["boot_median_mean"], 0, None),
            ],
            fmt="o", color="#4472C4", ecolor="grey", capsize=2, alpha=0.85,
        )
        ax.axvline(THRESH_HIGH, color="red", linestyle="--", label=f"high {THRESH_HIGH} mg/dL")
        ax.axvline(0, color="green", linestyle=":", label="target (110)")
        ax.set_xlabel("post-transition envelope above target (mg/dL, bootstrap 95% CI)")
        ax.set_ylabel("patient (sorted)")
        ax.set_title(f"Per-patient post-high envelope with bootstrap CI (n={len(out)})")
        ax.legend(fontsize=9)

        ax = axes[1]
        bands = ["confident_high", "confident_in_target", "uncertain"]
        bvals = [band_counts.get(b, 0) for b in bands]
        nvals = [naive_counts.get(k, 0) for k in
                 ["naive_high", "naive_in_target"]] + [0]
        x = np.arange(len(bands))
        w = 0.35
        ax.bar(x - w/2, nvals, w, label="naive (point)", color="#A0A0A0", edgecolor="black")
        ax.bar(x + w/2, bvals, w, label="bootstrap (P>=0.9)", color="#4472C4", edgecolor="black")
        ax.set_xticks(x)
        ax.set_xticklabels(["high", "in_target", "uncertain"])
        ax.set_ylabel("patient count")
        ax.set_title("Bootstrap vs naive")
        ax.legend(fontsize=9)

        fig.suptitle("EXP-2864: bootstrap-confidence post-high envelope", fontsize=12)
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2864_bootstrap_post_high.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
