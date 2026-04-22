"""EXP-2865 — Multi-factor stratified basal extraction with bootstrap.

Question: can layered deconfounding (clean-fasting filter + EGP
subtraction + TOD stratification + bootstrap CI) produce more reliable
per-TOD basal recommendations than the prior point-estimate fasting-
drift methods (EXP-2745/2746/2780, all of which had H3/H4 forecasting
hypotheses fail)?

Method, in stratification order:

1. Filter to "clean fasting" 5-min rows:
   - cob == 0
   - time_since_carb_min >= 240  (no carb tail)
   - time_since_bolus_min >= 240 (no bolus tail)
   - exercise_active == False
   - override_active == False
2. Compute observed basal need per row:
        need = actual_basal_rate U/h  (controller-actual delivery)
   This already accounts for any controller suspension or augmentation.
3. Subtract EGP correction (per-patient personalized) from BG drift to
   detect rows where the controller is COMPENSATING, not steady-state.
   Only keep rows where |bg_roc| < 0.5 mg/dL/min ("equilibrium").
4. Stratify by TOD bucket (4 blocks).
5. Per (patient, TOD) with >= 30 rows, bootstrap median actual_basal.
6. Compare to scheduled_basal_rate per same (patient, TOD).
7. Flag patients where the bootstrap CI excludes scheduled rate
   (P(med != scheduled within 5%) >= 0.9).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"

N_BOOT = 300
RNG_SEED = 2865
MIN_ROWS_PER_TOD = 30
EQUILIBRIUM_ROC = 0.5  # mg/dL per minute
MISMATCH_TOL = 0.05    # 5% deviation from scheduled

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


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    df = pd.read_parquet(GRID, columns=[
        "patient_id", "time", "glucose", "cob",
        "time_since_carb_min", "time_since_bolus_min",
        "exercise_active", "override_active",
        "actual_basal_rate", "scheduled_basal_rate",
        "glucose_roc",
    ])
    n0 = len(df)

    # Layer 1: clean fasting.
    df = df[
        (df["cob"].fillna(0) == 0)
        & (df["time_since_carb_min"].fillna(1e9) >= 240)
        & (df["time_since_bolus_min"].fillna(1e9) >= 240)
        & (~df["exercise_active"].fillna(False).astype(bool))
        & (~df["override_active"].fillna(False).astype(bool))
        & df["actual_basal_rate"].notna()
        & df["scheduled_basal_rate"].notna()
    ]
    n1 = len(df)

    # Layer 2 (EGP-equilibrium): only keep near-flat rows; this is a
    # proxy for "EGP is balanced by basal" so the actual delivered
    # basal is the patient's true need at this TOD.
    df = df[df["glucose_roc"].abs() <= EQUILIBRIUM_ROC]
    n2 = len(df)

    df["hour"] = pd.to_datetime(df["time"]).dt.hour
    df["tod"] = df["hour"].apply(_block)

    rows = []
    for (pid, tod), g in df.groupby(["patient_id", "tod"]):
        if len(g) < MIN_ROWS_PER_TOD:
            continue
        actual = g["actual_basal_rate"].to_numpy()
        scheduled = float(g["scheduled_basal_rate"].median())
        n = len(actual)
        meds = np.array([
            np.median(actual[rng.integers(0, n, size=n)])
            for _ in range(N_BOOT)
        ])
        ci_lo, ci_hi = np.quantile(meds, [0.025, 0.975])
        # Mismatch fraction: bootstrap replicates that deviate
        # from scheduled by more than tol.
        if scheduled > 0:
            rel = np.abs(meds - scheduled) / scheduled
            p_mismatch = float(np.mean(rel > MISMATCH_TOL))
            recommended_mult = float(np.median(meds) / scheduled)
        else:
            p_mismatch = float("nan")
            recommended_mult = float("nan")
        rows.append({
            "patient_id": pid, "tod": tod, "n_rows": int(n),
            "scheduled_basal_rate": scheduled,
            "boot_med_actual_basal": float(np.median(meds)),
            "ci_lo": float(ci_lo), "ci_hi": float(ci_hi),
            "ci_width": float(ci_hi - ci_lo),
            "p_mismatch_5pct": p_mismatch,
            "recommended_basal_mult": recommended_mult,
        })
    out = pd.DataFrame(rows)
    out.to_parquet(EXPDIR / "exp-2865_per_patient_tod_basal.parquet", index=False)

    # Per-patient roll-up across TOD buckets.
    per_p = out.groupby("patient_id").agg(
        n_tod=("tod", "count"),
        any_high_mismatch=("p_mismatch_5pct", lambda s: int((s >= 0.9).sum())),
        max_mismatch_p=("p_mismatch_5pct", "max"),
        median_recommended_mult=("recommended_basal_mult", "median"),
        spread_recommended_mult=(
            "recommended_basal_mult", lambda s: float(s.max() - s.min())
        ),
    ).reset_index()
    per_p.to_parquet(EXPDIR / "exp-2865_per_patient_summary.parquet", index=False)

    # Cohort summary.
    summary = {
        "exp": "EXP-2865",
        "method": (
            "Clean-fasting + EGP-equilibrium + TOD-stratified bootstrap "
            f"(N={N_BOOT}); compares actual vs scheduled basal per TOD."
        ),
        "rows_total": int(n0),
        "rows_after_clean_fasting": int(n1),
        "rows_after_equilibrium": int(n2),
        "n_patient_tod_buckets": int(len(out)),
        "n_patients": int(per_p.shape[0]),
        "n_buckets_high_mismatch_p_ge_0_9": int((out["p_mismatch_5pct"] >= 0.9).sum()),
        "n_buckets_in_target_p_lt_0_1": int((out["p_mismatch_5pct"] < 0.1).sum()),
        "median_ci_width_U_per_h": float(out["ci_width"].median()) if len(out) else None,
        "median_recommended_mult_cohort": float(per_p["median_recommended_mult"].median())
            if len(per_p) else None,
        "n_patients_any_high_mismatch_tod": int((per_p["any_high_mismatch"] >= 1).sum()),
        "n_patients_with_4_tod": int((per_p["n_tod"] == 4).sum()),
    }
    (EXPDIR / "exp-2865_summary.json").write_text(json.dumps(summary, indent=2))

    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(15, 5))

        # Panel 1: per-(patient,TOD) scheduled vs actual with CI.
        ax = axes[0]
        out_s = out.sort_values(["patient_id", "tod"]).reset_index(drop=True)
        x = np.arange(len(out_s))
        ax.errorbar(
            x, out_s["boot_med_actual_basal"],
            yerr=[
                np.clip(out_s["boot_med_actual_basal"] - out_s["ci_lo"], 0, None),
                np.clip(out_s["ci_hi"] - out_s["boot_med_actual_basal"], 0, None),
            ],
            fmt="o", color="#4472C4", ecolor="grey", capsize=2, alpha=0.85,
            label="actual (bootstrap CI)",
        )
        ax.scatter(x, out_s["scheduled_basal_rate"], color="red", marker="x",
                   s=30, label="scheduled")
        ax.set_xlabel("(patient, TOD) bucket index")
        ax.set_ylabel("basal rate (U/h)")
        ax.set_title("Actual vs scheduled basal — per-TOD bootstrap")
        ax.legend(fontsize=9)

        # Panel 2: cohort recommended multiplier per TOD.
        ax = axes[1]
        tod_order = ["night", "morning", "afternoon", "evening"]
        for tod in tod_order:
            vals = out[out["tod"] == tod]["recommended_basal_mult"].dropna()
            ax.scatter([tod] * len(vals), vals, alpha=0.5)
        cohort_med = out.groupby("tod")["recommended_basal_mult"].median().reindex(tod_order)
        ax.plot(tod_order, cohort_med.to_numpy(), color="black",
                marker="s", label="cohort median")
        ax.axhline(1.0, color="red", linestyle="--", alpha=0.6,
                   label="profile (no change)")
        ax.set_ylabel("recommended_basal_mult (actual / scheduled)")
        ax.set_title("Per-TOD basal multiplier (across patients)")
        ax.legend(fontsize=9)

        fig.suptitle("EXP-2865: stratified-bootstrap basal extraction")
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2865_stratified_basal.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
