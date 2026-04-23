"""EXP-2857 — TOD stability of audition bootstrap signals.

Stratifies the ISF-gap signal (EXP-2861, sourced from exp-2847
per-event corrections) by time-of-day block (night/morning/afternoon/
evening). For each patient × TOD with >=20 events, runs a per-block
bootstrap of the ISF gap percentage. Reports whether single-pool
bootstrap CI hides TOD heterogeneity.

EXP-2812 transitions are all bucketed to a single hour per patient,
so TOD stratification is only meaningful on the EXP-2847 per-event
corrections dataset.
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
N_BOOT = 300
RNG_SEED = 2857
MIN_EVENTS = 20  # per-TOD bucket
THR_UNDER = -0.10
THR_OVER = 0.30

TOD_BINS = [
    ("night",     0,  6),
    ("morning",   6, 12),
    ("afternoon", 12, 18),
    ("evening",   18, 24),
]


def _block(h: int) -> str:
    for name, lo, hi in TOD_BINS:
        if lo <= h < hi:
            return name
    return "night"


def _boot_isf(arr_obs: np.ndarray, arr_sched: np.ndarray,
              rng: np.random.Generator) -> dict:
    n = len(arr_obs)
    gaps = []
    for _ in range(N_BOOT):
        idx = rng.integers(0, n, size=n)
        obs = np.median(arr_obs[idx])
        sched = np.median(arr_sched[idx])
        if sched > 0:
            gaps.append((obs - sched) / sched)
    g = np.array(gaps)
    return {
        "boot_med_gap": float(g.mean()),
        "p_under": float(np.mean(g < THR_UNDER)),
        "p_over": float(np.mean(g > THR_OVER)),
        "ci_lo": float(np.quantile(g, 0.025)),
        "ci_hi": float(np.quantile(g, 0.975)),
    }


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    ev = pd.read_parquet(EVENTS).copy()
    # ISF observation requires a real correction (drop > 0 and bolus > 0).
    ev = ev[(ev["drop"] > 0) & (ev["bolus"] > 0) & (ev["sched_isf"] > 0)]
    ev["hour"] = pd.to_datetime(ev["time"]).dt.hour
    ev["tod"] = ev["hour"].apply(_block)

    rows = []
    for (pid, tod), g in ev.groupby(["patient_id", "tod"]):
        # EXP-2873 NaN guard: arr_obs/arr_sched must be NaN-free or boot
        # medians propagate NaN into the final quantile.
        gg = g.dropna(subset=["obs_isf", "sched_isf"])
        if len(gg) < MIN_EVENTS:
            continue
        boot = _boot_isf(gg["obs_isf"].to_numpy(),
                         gg["sched_isf"].to_numpy(), rng)
        rows.append({"patient_id": pid, "tod": tod, "n": len(gg), **boot})
    df = pd.DataFrame(rows)
    df.to_parquet(EXPDIR / "exp-2857_tod_isf_gap.parquet", index=False)

    # TOD agreement on the under-correction band.
    per_p = df.groupby("patient_id").agg(
        n_tod=("tod", "count"),
        min_p_under=("p_under", "min"),
        max_p_under=("p_under", "max"),
        min_p_over=("p_over", "min"),
        max_p_over=("p_over", "max"),
    )
    per_p["spread_under"] = per_p["max_p_under"] - per_p["min_p_under"]
    per_p["spread_over"] = per_p["max_p_over"] - per_p["min_p_over"]
    per_p["disagree_under"] = (
        (per_p["max_p_under"] >= 0.9) & (per_p["min_p_under"] < 0.1)
    ).astype(int)
    per_p["disagree_over"] = (
        (per_p["max_p_over"] >= 0.9) & (per_p["min_p_over"] < 0.1)
    ).astype(int)

    multi = per_p[per_p["n_tod"] >= 2]
    summary = {
        "exp": "EXP-2857",
        "method": (
            f"Per-patient TOD-stratified bootstrap (N={N_BOOT}) of ISF gap "
            f"(EXP-2847 per-event corrections); >= {MIN_EVENTS} events / TOD."
        ),
        "n_patient_tod_buckets": int(len(df)),
        "n_patients_total": int(per_p.shape[0]),
        "n_patients_multi_tod": int(multi.shape[0]),
        "median_spread_p_under": float(multi["spread_under"].median())
            if len(multi) else None,
        "median_spread_p_over": float(multi["spread_over"].median())
            if len(multi) else None,
        "max_spread_p_under": float(multi["spread_under"].max())
            if len(multi) else None,
        "explicit_disagree_under": int(per_p["disagree_under"].sum()),
        "explicit_disagree_over": int(per_p["disagree_over"].sum()),
        "tod_distribution": df["tod"].value_counts().to_dict(),
    }
    (EXPDIR / "exp-2857_summary.json").write_text(json.dumps(summary, indent=2))

    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(15, 5))
        tod_order = ["night", "morning", "afternoon", "evening"]
        for ax, p_col, title, thr_y in zip(
            axes,
            ["p_under", "p_over"],
            ["P(ISF under-correction) by TOD",
             "P(ISF over-correction) by TOD"],
            [THR_UNDER, THR_OVER],
        ):
            for pid, g in df.groupby("patient_id"):
                g = g.set_index("tod").reindex(tod_order)
                ax.plot(tod_order, g[p_col].to_numpy(),
                        marker="o", alpha=0.55, label=pid)
            ax.axhline(0.9, color="red", linestyle="--", alpha=0.6)
            ax.axhline(0.1, color="green", linestyle="--", alpha=0.6)
            ax.set_title(title)
            ax.set_ylabel("bootstrap probability")
            ax.set_ylim(-0.02, 1.02)
            ax.grid(alpha=0.3)
        fig.suptitle("EXP-2857: TOD stability of ISF-gap audition signal")
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2857_tod_stability.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
