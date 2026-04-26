"""EXP-3014: Carb-absorption-aware trough proxy for cf-replay.

Replaces EXP-3010's worst-case trough (cf_peak − insulin·ISF·remaining-PK) with
a more realistic proxy that adds back BG rise from carb absorption during the
120-min look-ahead window.

Trough model:
    cf_trough = cf_peak
              − [kernel(t_peak+W) − kernel(t_peak)] · smb_cand · isf
              + bg_offset_from_carbs

where:
    cob_at_peak ≈ cob_start + carbs_during         (upper bound)
    absorbed_in_W = cob_at_peak · (W / DEFAULT_AT)  (linear, AT=180 min)
    bg_offset_from_carbs = absorbed_in_W · ISF_PER_G   (mg/dL)
    ISF_PER_G ≈ 4 mg/dL/g  (1800/450 rule, ISF/CR ratio)

EGP is omitted: in ascent context the rise is dominated by carb signal already
captured by cob_at_peak, and the 120-min window is short enough that the
1.5-2 mg/dL/min hepatic glucose production is largely offset by basal action.

Hypothesis: the (T=+30, M=0.5×) recommendation from EXP-3011 is robust to
carb-aware trough correction; the Δhypo magnitudes shrink but the sign and
per-controller rank-order survive.

Outputs
  externals/experiments/exp-3014_carb_aware.parquet
  externals/experiments/exp-3014_summary.json
  docs/60-research/figures/exp-3014_carb_aware.png
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
DOCS_FIG.mkdir(parents=True, exist_ok=True)

EVENTS = EXT / "exp-3007_ascent_events.parquet"
PROFILES = EXT / "exp-2881_profile_terms.parquet"

OUT_PARQUET = EXT / "exp-3014_carb_aware.parquet"
OUT_JSON = EXT / "exp-3014_summary.json"
OUT_FIG = DOCS_FIG / "exp-3014_carb_aware.png"

WINDOW_MIN = 120
HYPO_FLOOR = 70.0
HYPO_DELTA_GATE_PP = 1.0
DEFAULT_AT_MIN = 180.0  # absorption time, 3h
ISF_PER_G = 4.0  # mg/dL per gram, 1800/450 rule

# Same grid as EXP-3011.
T_GRID = [0, 5, 10, 15, 20, 30]
M_GRID = [0.5, 1.0, 1.5, 2.0, 3.0]


def cf_metrics(ev: pd.DataFrame, T: int, M: float, *, carb_aware: bool) -> pd.DataFrame:
    df = ev.copy()
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

    if carb_aware:
        cob_at_peak = (ev["cob_start"].fillna(0) + ev["carbs_during"].fillna(0)).to_numpy()
        absorbed_in_W = cob_at_peak * (WINDOW_MIN / DEFAULT_AT_MIN)
        bg_offset = absorbed_in_W * ISF_PER_G
        cand_trough = cand_trough + bg_offset

    df["cand_overshoot"] = (cand_peak >= 180.0).astype(float)
    df["cand_hypo"] = (cand_trough < HYPO_FLOOR).astype(float)
    df["cand_peak"] = cand_peak
    df["cand_trough"] = cand_trough
    return df


def evaluate_grid(ev: pd.DataFrame, *, carb_aware: bool) -> pd.DataFrame:
    rows = []
    for T in T_GRID:
        for M in M_GRID:
            mt = cf_metrics(ev, T, M, carb_aware=carb_aware)
            for ctrl, sub in mt.groupby("controller", dropna=False):
                rows.append({
                    "controller": str(ctrl),
                    "T_min": T,
                    "M_mult": M,
                    "n": int(len(sub)),
                    "cand_overshoot": float(sub["cand_overshoot"].mean()),
                    "cand_hypo": float(sub["cand_hypo"].mean()),
                })
    return pd.DataFrame(rows)


def recommend(grid: pd.DataFrame, ctrl: str) -> dict:
    sub = grid[grid["controller"] == ctrl].copy()
    bl = sub[(sub["T_min"] == 0) & (sub["M_mult"] == 1.0)].iloc[0]
    sub["delta_over_pp"] = (sub["cand_overshoot"] - bl["cand_overshoot"]) * 100
    sub["delta_hypo_pp"] = (sub["cand_hypo"] - bl["cand_hypo"]) * 100
    elig = sub[sub["delta_hypo_pp"] <= HYPO_DELTA_GATE_PP]
    rec = elig.sort_values("delta_over_pp").iloc[0]
    return {
        "controller": ctrl,
        "T_rec": int(rec["T_min"]),
        "M_rec": float(rec["M_mult"]),
        "delta_over_pp": float(rec["delta_over_pp"]),
        "delta_hypo_pp": float(rec["delta_hypo_pp"]),
        "baseline_overshoot": float(bl["cand_overshoot"]),
        "baseline_hypo": float(bl["cand_hypo"]),
    }


def main() -> None:
    ev = pd.read_parquet(EVENTS)
    profiles = pd.read_parquet(PROFILES) if PROFILES.exists() else None

    isf_map = {}
    if profiles is not None:
        for pid, sub in profiles.groupby("patient_id"):
            vals = sub.loc[sub["schedule_type"] == "isf", "value"].dropna()
            isf_map[pid] = float(vals.median()) if len(vals) else 50.0
    ev["isf_used"] = ev["patient_id"].map(isf_map).fillna(50.0)

    print(f"[EXP-3014] n_events={len(ev)}, controllers={ev['controller'].value_counts().to_dict()}")

    grid_naive = evaluate_grid(ev, carb_aware=False)
    grid_carb = evaluate_grid(ev, carb_aware=True)
    grid_naive["model"] = "naive (EXP-3010)"
    grid_carb["model"] = "carb_aware (EXP-3014)"
    out = pd.concat([grid_naive, grid_carb], ignore_index=True)
    out.to_parquet(OUT_PARQUET, index=False)

    print("\n=== Recommendation comparison (naive vs carb-aware) ===")
    summary = {"window_min": WINDOW_MIN, "default_at_min": DEFAULT_AT_MIN,
               "isf_per_g": ISF_PER_G, "by_controller": {}}
    print(f"{'controller':<10}  {'model':<22}  {'T*':>4}  {'M*':>5}  {'Δover':>8}  {'Δhypo':>8}")
    for ctrl in sorted(g for g in ev["controller"].dropna().unique()):
        for grid, label in [(grid_naive, "naive"), (grid_carb, "carb_aware")]:
            r = recommend(grid, ctrl)
            print(f"{ctrl:<10}  {label:<22}  {r['T_rec']:>4d}  {r['M_rec']:>5.1f}  "
                  f"{r['delta_over_pp']:+8.2f}  {r['delta_hypo_pp']:+8.2f}")
            summary["by_controller"].setdefault(ctrl, {})[label] = r

    # Visualisation: side-by-side per controller, model A vs model B.
    ctrls = sorted(g for g in ev["controller"].dropna().unique())
    fig, axes = plt.subplots(1, len(ctrls), figsize=(5 * len(ctrls), 5), sharey=True)
    if len(ctrls) == 1:
        axes = [axes]
    for ax, ctrl in zip(axes, ctrls):
        for grid, label, marker in [(grid_naive, "naive (worst-case)", "o"),
                                    (grid_carb, "carb-aware", "^")]:
            sub = grid[grid["controller"] == ctrl].copy()
            bl = sub[(sub["T_min"] == 0) & (sub["M_mult"] == 1.0)].iloc[0]
            sub["d_over"] = (sub["cand_overshoot"] - bl["cand_overshoot"]) * 100
            sub["d_hypo"] = (sub["cand_hypo"] - bl["cand_hypo"]) * 100
            ax.scatter(sub["d_hypo"], sub["d_over"], marker=marker, s=60,
                       alpha=0.7, label=label, edgecolor="k")
        ax.axvline(HYPO_DELTA_GATE_PP, color="red", linestyle="--", alpha=0.5)
        ax.axhline(0, color="k", linestyle=":", alpha=0.4)
        ax.axvline(0, color="k", linestyle=":", alpha=0.4)
        ax.set_title(ctrl)
        ax.set_xlabel("Δ hypo-rate (pp)")
        ax.set_ylabel("Δ overshoot rate (pp)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle("EXP-3014: Naive (worst-case) vs carb-aware trough proxy")
    fig.tight_layout()
    fig.savefig(OUT_FIG, dpi=130, bbox_inches="tight")
    print(f"\n  → {OUT_FIG}")

    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str))
    print(f"  → {OUT_JSON}")


if __name__ == "__main__":
    main()
