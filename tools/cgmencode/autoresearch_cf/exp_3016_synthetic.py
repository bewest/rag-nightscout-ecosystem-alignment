"""EXP-3016: phenotype-conditional synthetic ascent generator.

Builds a stratified bootstrap-with-jitter sampler that produces synthetic
ascent events conditional on a braking_ratio stratum, then validates by
running the EXP-3011 bivariate (T, M) frontier on synthetic cohorts and
checking that:

  * Low-braking strata (≤0.10) recover the (T=+30, M=0.5×) Pareto optimum.
  * High-braking strata (>0.10) produce no Pareto improvement (recommendation
    collapses to T=0, M≈1).

Method
------
1. Join EXP-3007 ascent events with EXP-2886 phenotype (n=14,415 with braking).
2. Bin events into 3 strata: low (≤0.05), mid (0.05–0.10), high (>0.10).
3. For each synthetic cohort: sample N=2,000 events with replacement from the
   stratum pool, then add multiplicative log-normal jitter (σ=0.10) to numeric
   features (smb_during, peak_delta, iob_start, cob_start, carbs_during,
   duration_min). bg_peak is recomputed from bg_start + jittered peak_delta.
4. Run the EXP-3011 evaluator (with EXP-3014 carb-aware proxy) on each
   synthetic cohort and report (T*, M*, Δoversht, Δhypo).

Outputs
  externals/experiments/exp-3016_synthetic_frontier.parquet
  externals/experiments/exp-3016_summary.json
  docs/60-research/figures/exp-3016_synthetic_frontier.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tools.cgmencode.autoresearch_cf.exp_3009_timing_axis import kernel_at

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT / "externals" / "experiments"
DOCS_FIG = ROOT / "docs" / "60-research" / "figures"

EVENTS = EXT / "exp-3007_ascent_events.parquet"
PHENOTYPE = EXT / "exp-2886_phenotype.parquet"

OUT_PARQUET = EXT / "exp-3016_synthetic_frontier.parquet"
OUT_JSON = EXT / "exp-3016_summary.json"
OUT_FIG = DOCS_FIG / "exp-3016_synthetic_frontier.png"

WINDOW_MIN = 120
HYPO_FLOOR = 70.0
HYPO_DELTA_GATE_PP = 1.0
DEFAULT_AT_MIN = 180.0
ISF_PER_G = 4.0
JITTER_SIGMA = 0.10
N_SYNTH = 2000

T_GRID = [0, 5, 10, 15, 20, 30]
M_GRID = [0.5, 1.0, 1.5, 2.0, 3.0]

STRATA = {
    "low_braking_<=0.05":   (-0.01, 0.05),
    "mid_braking_0.05-0.10": (0.05, 0.10),
    "high_braking_>0.10":   (0.10, 1.00),
}

NUMERIC_COLS = ["duration_min", "peak_delta", "smb_during",
                "iob_start", "cob_start", "carbs_during"]


def jittered_bootstrap(pool: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    idx = rng.integers(0, len(pool), size=n)
    syn = pool.iloc[idx].reset_index(drop=True).copy()
    for col in NUMERIC_COLS:
        if col in syn.columns:
            jitter = rng.lognormal(mean=0.0, sigma=JITTER_SIGMA, size=n)
            syn[col] = (syn[col].fillna(0).to_numpy() * jitter).clip(min=0)
    syn["bg_peak"] = syn["bg_start"].fillna(120) + syn["peak_delta"]
    syn["isf_used"] = 50.0
    return syn


def cf_eval(ev: pd.DataFrame, T: float, M: float) -> pd.DataFrame:
    smb_obs = ev["smb_during"].fillna(0).to_numpy()
    smb_cand = smb_obs * M
    isf = ev["isf_used"].to_numpy()
    half = ev["duration_min"].to_numpy() / 2.0
    eff_off = np.minimum(T, ev["duration_min"].to_numpy())
    t_peak = half + eff_off

    drop_at_peak = smb_cand * kernel_at(t_peak) * isf
    drop_at_peak_baseline = smb_obs * kernel_at(half) * isf
    cand_peak = ev["bg_peak"].to_numpy() - (drop_at_peak - drop_at_peak_baseline)

    extra_post = (kernel_at(t_peak + WINDOW_MIN) - kernel_at(t_peak)) * smb_cand * isf
    cand_trough = cand_peak - extra_post

    cob_at_peak = (ev["cob_start"].fillna(0) + ev["carbs_during"].fillna(0)).to_numpy()
    bg_offset = cob_at_peak * (WINDOW_MIN / DEFAULT_AT_MIN) * ISF_PER_G
    cand_trough = cand_trough + bg_offset

    return pd.DataFrame({
        "cand_overshoot": (cand_peak >= 180.0).astype(float),
        "cand_hypo": (cand_trough < HYPO_FLOOR).astype(float),
    })


def evaluate_grid(syn: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for T in T_GRID:
        for M in M_GRID:
            res = cf_eval(syn, T, M)
            rows.append({
                "T_min": T, "M_mult": M,
                "cand_overshoot": float(res["cand_overshoot"].mean()),
                "cand_hypo": float(res["cand_hypo"].mean()),
                "n": int(len(syn)),
            })
    return pd.DataFrame(rows)


def recommend(grid: pd.DataFrame) -> dict:
    bl = grid[(grid["T_min"] == 0) & (grid["M_mult"] == 1.0)].iloc[0]
    g = grid.copy()
    g["delta_over_pp"] = (g["cand_overshoot"] - bl["cand_overshoot"]) * 100
    g["delta_hypo_pp"] = (g["cand_hypo"] - bl["cand_hypo"]) * 100
    elig = g[g["delta_hypo_pp"] <= HYPO_DELTA_GATE_PP].sort_values("delta_over_pp")
    rec = elig.iloc[0]
    return {
        "T_rec": int(rec["T_min"]),
        "M_rec": float(rec["M_mult"]),
        "delta_over_pp": float(rec["delta_over_pp"]),
        "delta_hypo_pp": float(rec["delta_hypo_pp"]),
        "baseline_overshoot": float(bl["cand_overshoot"]),
        "baseline_hypo": float(bl["cand_hypo"]),
    }


def main() -> None:
    rng = np.random.default_rng(42)
    ev = pd.read_parquet(EVENTS)
    ph = pd.read_parquet(PHENOTYPE)[["patient_id", "braking_ratio"]]
    df = ev.merge(ph, on="patient_id", how="inner")
    df = df.dropna(subset=["braking_ratio"])
    print(f"[EXP-3016] {len(df)} events with braking_ratio attached")

    rows = []
    grids = {}
    for label, (lo, hi) in STRATA.items():
        pool = df[(df["braking_ratio"] > lo) & (df["braking_ratio"] <= hi)].copy()
        if len(pool) < 100:
            print(f"  skip {label}: only {len(pool)} pool events")
            continue
        syn = jittered_bootstrap(pool, N_SYNTH, rng)
        grid = evaluate_grid(syn)
        grid["stratum"] = label
        grids[label] = grid
        rec = recommend(grid)
        rec["stratum"] = label
        rec["n_pool"] = int(len(pool))
        rec["n_synthetic"] = N_SYNTH
        rec["mean_smb_during"] = float(syn["smb_during"].mean())
        rec["mean_cob_start"] = float(syn["cob_start"].mean())
        rows.append(rec)
        print(f"  {label:<28} pool={len(pool):>5}  T*={rec['T_rec']:>2d}  "
              f"M*={rec['M_rec']:.1f}  Δover={rec['delta_over_pp']:+5.2f}pp  "
              f"Δhypo={rec['delta_hypo_pp']:+5.2f}pp")

    summary = {"N_synthetic": N_SYNTH, "jitter_sigma": JITTER_SIGMA,
               "by_stratum": rows}

    pd.concat(grids.values(), ignore_index=True).to_parquet(OUT_PARQUET, index=False)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))

    # Plot: per-stratum (Δhypo, Δover) grids.
    fig, axes = plt.subplots(1, len(grids), figsize=(5.2 * len(grids), 5),
                             sharey=True)
    if len(grids) == 1:
        axes = [axes]
    for ax, (label, grid) in zip(axes, grids.items()):
        bl = grid[(grid["T_min"] == 0) & (grid["M_mult"] == 1.0)].iloc[0]
        g = grid.copy()
        g["d_over"] = (g["cand_overshoot"] - bl["cand_overshoot"]) * 100
        g["d_hypo"] = (g["cand_hypo"] - bl["cand_hypo"]) * 100
        sc = ax.scatter(g["d_hypo"], g["d_over"], c=g["T_min"], cmap="viridis",
                        s=80, alpha=0.85, edgecolor="k")
        for _, r in g.iterrows():
            ax.annotate(f"({int(r['T_min'])},{r['M_mult']:.1f})",
                        (r["d_hypo"], r["d_over"]), fontsize=6, alpha=0.6)
        ax.axvline(HYPO_DELTA_GATE_PP, color="red", linestyle="--", alpha=0.5)
        ax.axhline(0, color="k", linestyle=":", alpha=0.4)
        ax.axvline(0, color="k", linestyle=":", alpha=0.4)
        ax.set_title(label)
        ax.set_xlabel("Δ hypo-rate (pp)")
        ax.set_ylabel("Δ overshoot rate (pp)")
        ax.grid(alpha=0.3)
    fig.colorbar(sc, ax=axes[-1], label="T (min earlier)")
    fig.suptitle(f"EXP-3016: synthetic cohort frontier by braking stratum (N={N_SYNTH} each)")
    fig.tight_layout()
    fig.savefig(OUT_FIG, dpi=130, bbox_inches="tight")
    print(f"  → {OUT_FIG}")
    print(f"  → {OUT_JSON}")
    print(f"  → {OUT_PARQUET}")


if __name__ == "__main__":
    main()
