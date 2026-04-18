"""
EXP-2533: Meal-PD Interaction Features for Glucose Forecasting

Hypothesis: Interaction terms (PD_feature × context_feature) capture conditional
pharmacodynamics that generalizes temporally, because the interaction encodes WHEN
the mechanism matters, not just that it exists.

Builds on EXP-2531/2532 findings that standalone PD features have near-zero
predictive power at h60 under temporal CV. The key insight is that a large insulin
dose has different effects depending on meal context (correction+carb coverage vs
standalone correction).

Sub-experiments:
  2533a — Temporal CV comparison: Ridge/GBM × base/+interactions
  2533b — Ablation: add interactions one at a time
  2533c — Conditional analysis: high-meal vs low-meal patient subgroups
"""

import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    from sklearn.ensemble import GradientBoostingRegressor
    HAS_LGB = False

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]
DATA_PATH = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT_PATH = ROOT / "externals" / "experiments" / "exp-2533_meal_pd_interaction.json"

HORIZONS = {"h12": 12, "h30": 30, "h60": 60}  # 5-min steps
N_SPLITS = 5

# Column mapping (task names → actual parquet columns)
COL_MAP = {
    "sgv": "glucose",
    "bgi": "glucose_roc",
    "iob": "iob",
    "cob": "cob",
    "net_flux": "net_basal",
    "bolus": "bolus",
    "micro_bolus": "bolus_smb",
    "isf": "scheduled_isf",
    "cr": "scheduled_cr",
}

BASE_FEATURES = ["glucose", "iob", "cob", "net_basal", "glucose_roc"]

INTERACTION_NAMES = [
    "iob_persistent_x_fasting",
    "iob_persistent_x_overnight",
    "bolus_powerlaw_x_meal_prox",
    "bolus_powerlaw_x_fasting",
    "bg_distance_x_meal_prox",
    "bg_distance_x_high_iob",
]


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def engineer_features(pdf: pd.DataFrame) -> pd.DataFrame:
    """Build context, PD, and interaction features for a single patient."""
    df = pdf.sort_values("time").copy()

    # --- Context features ---
    df["meal_proximity"] = (df["cob"] > 0).astype(np.float32)

    # fasting_state: cob == 0 AND no bolus in last 2h (24 × 5-min steps)
    bolus_2h = df["bolus"].rolling(24, min_periods=1).sum()
    df["fasting_state"] = ((df["cob"] == 0) & (bolus_2h == 0)).astype(np.float32)

    # overnight: hour in [0, 6]
    hour = df["time"].dt.hour
    df["overnight"] = ((hour >= 0) & (hour <= 6)).astype(np.float32)

    # high_iob: iob > patient median
    med_iob = df["iob"].median()
    df["high_iob"] = (df["iob"] > med_iob).astype(np.float32)

    # --- PD features ---
    # iob_persistent: rolling 12h (144 steps) sum of bolus
    df["iob_persistent"] = (
        df["bolus"].rolling(144, min_periods=1).sum().astype(np.float32)
    )

    # bolus_powerlaw: rolling 4h (48 steps) sum of bolus^0.1
    bolus_pow = np.power(df["bolus"].clip(lower=0).values + 1e-9, 0.1)
    df["bolus_powerlaw"] = (
        pd.Series(bolus_pow, index=df.index)
        .rolling(48, min_periods=1)
        .sum()
        .astype(np.float32)
    )

    # bg_distance: (glucose - patient_median) / patient_std  (z-score)
    med_g = df["glucose"].median()
    std_g = df["glucose"].std()
    if std_g < 1.0:
        std_g = 1.0
    df["bg_distance"] = ((df["glucose"] - med_g) / std_g).astype(np.float32)

    # --- Interaction terms ---
    df["iob_persistent_x_fasting"] = (
        df["iob_persistent"] * df["fasting_state"]
    ).astype(np.float32)
    df["iob_persistent_x_overnight"] = (
        df["iob_persistent"] * df["overnight"]
    ).astype(np.float32)
    df["bolus_powerlaw_x_meal_prox"] = (
        df["bolus_powerlaw"] * df["meal_proximity"]
    ).astype(np.float32)
    df["bolus_powerlaw_x_fasting"] = (
        df["bolus_powerlaw"] * df["fasting_state"]
    ).astype(np.float32)
    df["bg_distance_x_meal_prox"] = (
        df["bg_distance"] * df["meal_proximity"]
    ).astype(np.float32)
    df["bg_distance_x_high_iob"] = (
        df["bg_distance"] * df["high_iob"]
    ).astype(np.float32)

    return df


# ---------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------

def make_ridge():
    return Ridge(alpha=1.0)


def make_gbm():
    if HAS_LGB:
        return lgb.LGBMRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.1,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            verbose=-1,
            n_jobs=1,
        )
    return GradientBoostingRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.1,
        min_samples_leaf=20,
        subsample=0.8,
    )


# ---------------------------------------------------------------------------
# Temporal CV evaluation
# ---------------------------------------------------------------------------

def temporal_cv(df: pd.DataFrame, features: list[str], target: str,
                model_fn, n_splits: int = N_SPLITS) -> dict:
    """Run temporal CV (TimeSeriesSplit). Returns per-fold R² and MAE."""
    X = df[features].values
    y = df[target].values

    mask = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    X, y = X[mask], y[mask]

    if len(y) < n_splits * 50:
        return {"r2": float("nan"), "mae": float("nan"), "n_samples": int(len(y)),
                "fold_r2": [], "fold_mae": []}

    tscv = TimeSeriesSplit(n_splits=n_splits)
    fold_r2, fold_mae = [], []
    for train_idx, test_idx in tscv.split(X):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]

        model = model_fn()
        model.fit(X_tr, y_tr)
        y_hat = model.predict(X_te)

        r2 = r2_score(y_te, y_hat) if len(y_te) > 1 else float("nan")
        mae = mean_absolute_error(y_te, y_hat) if len(y_te) > 1 else float("nan")
        fold_r2.append(round(float(r2), 6))
        fold_mae.append(round(float(mae), 4))

    return {
        "r2": round(float(np.nanmean(fold_r2)), 6),
        "mae": round(float(np.nanmean(fold_mae)), 4),
        "n_samples": int(len(y)),
        "fold_r2": fold_r2,
        "fold_mae": fold_mae,
    }


# ---------------------------------------------------------------------------
# EXP-2533a: Temporal CV comparison
# ---------------------------------------------------------------------------

def run_2533a(patients: dict[str, pd.DataFrame]) -> dict:
    """Compare 4 configs: {Ridge, GBM} × {base, +interactions}."""
    interaction_features = BASE_FEATURES + INTERACTION_NAMES

    configs = {
        "ridge_base": (BASE_FEATURES, make_ridge),
        "ridge_interactions": (interaction_features, make_ridge),
        "gbm_base": (BASE_FEATURES, make_gbm),
        "gbm_interactions": (interaction_features, make_gbm),
    }

    results: dict = {}
    for hz_name, hz_steps in HORIZONS.items():
        hz_results: dict = {}
        for pid, pdf in patients.items():
            target_col = f"target_{hz_name}"
            pdf[target_col] = pdf["glucose"].shift(-hz_steps)

            patient_res: dict = {}
            for cfg_name, (feats, model_fn) in configs.items():
                patient_res[cfg_name] = temporal_cv(pdf, feats, target_col, model_fn)

            # Deltas: interaction improvement over same-model base
            for model_type in ("ridge", "gbm"):
                base_r2 = patient_res[f"{model_type}_base"]["r2"]
                int_r2 = patient_res[f"{model_type}_interactions"]["r2"]
                patient_res[f"{model_type}_delta_r2"] = (
                    round(int_r2 - base_r2, 6)
                    if np.isfinite(base_r2) and np.isfinite(int_r2)
                    else float("nan")
                )

            hz_results[pid] = patient_res
        results[hz_name] = hz_results

    # Aggregate across patients
    summary: dict = {}
    for hz_name in HORIZONS:
        hz_summary: dict = {}
        for cfg_name in configs:
            r2_vals = [
                results[hz_name][pid][cfg_name]["r2"]
                for pid in patients
                if np.isfinite(results[hz_name][pid][cfg_name]["r2"])
            ]
            mae_vals = [
                results[hz_name][pid][cfg_name]["mae"]
                for pid in patients
                if np.isfinite(results[hz_name][pid][cfg_name]["mae"])
            ]
            hz_summary[cfg_name] = {
                "mean_r2": round(float(np.mean(r2_vals)), 6) if r2_vals else None,
                "median_r2": round(float(np.median(r2_vals)), 6) if r2_vals else None,
                "std_r2": round(float(np.std(r2_vals)), 6) if r2_vals else None,
                "mean_mae": round(float(np.mean(mae_vals)), 4) if mae_vals else None,
                "n_patients": len(r2_vals),
            }
        for model_type in ("ridge", "gbm"):
            deltas = [
                results[hz_name][pid][f"{model_type}_delta_r2"]
                for pid in patients
                if np.isfinite(results[hz_name][pid].get(f"{model_type}_delta_r2", float("nan")))
            ]
            hz_summary[f"{model_type}_delta"] = {
                "mean_delta_r2": round(float(np.mean(deltas)), 6) if deltas else None,
                "median_delta_r2": round(float(np.median(deltas)), 6) if deltas else None,
                "positive_pct": round(sum(1 for d in deltas if d > 0) / max(len(deltas), 1), 4),
                "n_patients": len(deltas),
            }
        summary[hz_name] = hz_summary

    return {"per_patient": results, "summary": summary}


# ---------------------------------------------------------------------------
# EXP-2533b: Ablation — add interactions one at a time
# ---------------------------------------------------------------------------

def run_2533b(patients: dict[str, pd.DataFrame]) -> dict:
    """Add each interaction individually to the base set."""
    results: dict = {}
    for hz_name, hz_steps in HORIZONS.items():
        hz_results: dict = {}
        for pid, pdf in patients.items():
            target_col = f"target_{hz_name}"
            pdf[target_col] = pdf["glucose"].shift(-hz_steps)

            # Baseline GBM
            base_res = temporal_cv(pdf, BASE_FEATURES, target_col, make_gbm)

            feature_deltas: dict = {}
            for int_name in INTERACTION_NAMES:
                aug_features = BASE_FEATURES + [int_name]
                aug_res = temporal_cv(pdf, aug_features, target_col, make_gbm)
                delta = (
                    round(aug_res["r2"] - base_res["r2"], 6)
                    if np.isfinite(base_res["r2"]) and np.isfinite(aug_res["r2"])
                    else float("nan")
                )
                feature_deltas[int_name] = {
                    "augmented_r2": aug_res["r2"],
                    "marginal_r2": delta,
                }

            hz_results[pid] = {
                "baseline_r2": base_res["r2"],
                "interactions": feature_deltas,
            }
        results[hz_name] = hz_results

    # Aggregate: per interaction term, mean marginal R² across patients
    summary: dict = {}
    for hz_name in HORIZONS:
        hz_summary: dict = {}
        for int_name in INTERACTION_NAMES:
            marginals = [
                results[hz_name][pid]["interactions"][int_name]["marginal_r2"]
                for pid in patients
                if np.isfinite(
                    results[hz_name][pid]["interactions"][int_name]["marginal_r2"]
                )
            ]
            hz_summary[int_name] = {
                "mean_marginal_r2": round(float(np.mean(marginals)), 6) if marginals else None,
                "median_marginal_r2": round(float(np.median(marginals)), 6) if marginals else None,
                "positive_pct": round(sum(1 for m in marginals if m > 0) / max(len(marginals), 1), 4),
                "n_patients": len(marginals),
            }
        summary[hz_name] = hz_summary

    # Rank interactions by mean marginal R² at each horizon
    rankings: dict = {}
    for hz_name in HORIZONS:
        ranked = sorted(
            summary[hz_name].items(),
            key=lambda x: x[1]["mean_marginal_r2"] if x[1]["mean_marginal_r2"] is not None else -999,
            reverse=True,
        )
        rankings[hz_name] = [{"feature": k, **v} for k, v in ranked]

    return {"per_patient": results, "summary": summary, "rankings": rankings}


# ---------------------------------------------------------------------------
# EXP-2533c: Conditional analysis — high-meal vs low-meal subgroups
# ---------------------------------------------------------------------------

def run_2533c(patients: dict[str, pd.DataFrame]) -> dict:
    """Split patients by meal frequency, test if interactions help more
    for patients with irregular meal patterns."""
    # Compute meal frequency per patient: fraction of rows with cob > 0
    meal_fracs: dict = {}
    for pid, pdf in patients.items():
        meal_fracs[pid] = float((pdf["cob"] > 0).mean())

    median_meal_frac = float(np.median(list(meal_fracs.values())))

    high_meal_pids = [p for p, f in meal_fracs.items() if f >= median_meal_frac]
    low_meal_pids = [p for p, f in meal_fracs.items() if f < median_meal_frac]

    interaction_features = BASE_FEATURES + INTERACTION_NAMES

    subgroup_results: dict = {}
    for group_name, pids in [("high_meal", high_meal_pids), ("low_meal", low_meal_pids)]:
        group_res: dict = {}
        for hz_name, hz_steps in HORIZONS.items():
            base_r2s, int_r2s, deltas = [], [], []
            for pid in pids:
                pdf = patients[pid]
                target_col = f"target_{hz_name}"
                pdf[target_col] = pdf["glucose"].shift(-hz_steps)

                base_res = temporal_cv(pdf, BASE_FEATURES, target_col, make_gbm)
                int_res = temporal_cv(pdf, interaction_features, target_col, make_gbm)

                if np.isfinite(base_res["r2"]) and np.isfinite(int_res["r2"]):
                    base_r2s.append(base_res["r2"])
                    int_r2s.append(int_res["r2"])
                    deltas.append(int_res["r2"] - base_res["r2"])

            group_res[hz_name] = {
                "n_patients": len(pids),
                "mean_base_r2": round(float(np.mean(base_r2s)), 6) if base_r2s else None,
                "mean_interaction_r2": round(float(np.mean(int_r2s)), 6) if int_r2s else None,
                "mean_delta_r2": round(float(np.mean(deltas)), 6) if deltas else None,
                "median_delta_r2": round(float(np.median(deltas)), 6) if deltas else None,
                "positive_pct": round(sum(1 for d in deltas if d > 0) / max(len(deltas), 1), 4),
            }
        subgroup_results[group_name] = group_res

    return {
        "median_meal_fraction": round(median_meal_frac, 4),
        "meal_fractions": {p: round(f, 4) for p, f in meal_fracs.items()},
        "high_meal_patients": high_meal_pids,
        "low_meal_patients": low_meal_pids,
        "subgroups": subgroup_results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_experiment() -> dict:
    t0 = time.time()
    print("EXP-2533: Meal-PD Interaction Features for Glucose Forecasting")
    print(f"  Data: {DATA_PATH}")
    print(f"  LightGBM available: {HAS_LGB}")

    # Load data
    needed_cols = [
        "patient_id", "time", "glucose", "iob", "cob", "net_basal",
        "bolus", "bolus_smb", "glucose_roc", "scheduled_isf", "scheduled_cr",
    ]
    df = pd.read_parquet(DATA_PATH, columns=needed_cols)
    df = df.dropna(subset=["glucose"]).reset_index(drop=True)
    print(f"  Loaded {len(df):,} rows, {df['patient_id'].nunique()} patients")

    # Engineer features per patient
    patients: dict[str, pd.DataFrame] = {}
    for pid, grp in df.groupby("patient_id"):
        if len(grp) < 500:
            print(f"  Skipping {pid}: only {len(grp)} rows")
            continue
        patients[str(pid)] = engineer_features(grp)
    print(f"  Engineered features for {len(patients)} patients")

    # --- Sub-experiments ---
    print("\n--- EXP-2533a: Temporal CV Comparison ---")
    res_a = run_2533a(patients)
    for hz in HORIZONS:
        s = res_a["summary"][hz]
        print(f"  {hz}:")
        for cfg in ("ridge_base", "ridge_interactions", "gbm_base", "gbm_interactions"):
            r2 = s[cfg]["mean_r2"]
            print(f"    {cfg:25s}  R²={r2}")
        for mt in ("ridge", "gbm"):
            d = s[f"{mt}_delta"]
            print(f"    {mt}_delta: mean={d['mean_delta_r2']}, "
                  f"positive={d['positive_pct']:.0%}")

    print("\n--- EXP-2533b: Ablation ---")
    res_b = run_2533b(patients)
    for hz in HORIZONS:
        print(f"  {hz} ranking:")
        for rank_item in res_b["rankings"][hz]:
            print(f"    {rank_item['feature']:35s}  "
                  f"marginal_r2={rank_item['mean_marginal_r2']}")

    print("\n--- EXP-2533c: Conditional (meal subgroups) ---")
    res_c = run_2533c(patients)
    for group_name in ("high_meal", "low_meal"):
        print(f"  {group_name} (n={res_c['subgroups'][group_name]['h60']['n_patients']}):")
        for hz in HORIZONS:
            sg = res_c["subgroups"][group_name][hz]
            print(f"    {hz}: base_r2={sg['mean_base_r2']}, "
                  f"int_r2={sg['mean_interaction_r2']}, "
                  f"delta={sg['mean_delta_r2']}")

    elapsed = round(time.time() - t0, 2)

    # Determine pass/fail: interactions help at any horizon for GBM
    gbm_deltas = [
        res_a["summary"][hz]["gbm_delta"]["mean_delta_r2"]
        for hz in HORIZONS
        if res_a["summary"][hz]["gbm_delta"]["mean_delta_r2"] is not None
    ]
    any_positive = any(d > 0 for d in gbm_deltas)
    status = "pass" if any_positive else "fail"

    result = {
        "experiment": "EXP-2533",
        "name": "Meal-PD Interaction Features for Glucose Forecasting",
        "status": status,
        "hypothesis": (
            "Interaction terms (PD × context) capture conditional pharmacodynamics "
            "that generalizes under temporal CV, encoding WHEN mechanisms matter."
        ),
        "config": {
            "data_path": str(DATA_PATH),
            "horizons": HORIZONS,
            "n_splits": N_SPLITS,
            "cv_method": "TimeSeriesSplit (temporal, no shuffling)",
            "base_features": BASE_FEATURES,
            "interaction_features": INTERACTION_NAMES,
            "models": {
                "ridge": "Ridge(alpha=1.0)",
                "gbm": f"LightGBM(n_est=200,depth=5)" if HAS_LGB else "sklearn.GBM(n_est=200,depth=5)",
            },
            "n_patients": len(patients),
            "patient_ids": sorted(patients.keys()),
        },
        "results": {
            "exp_2533a_comparison": res_a["summary"],
            "exp_2533b_ablation": {
                "summary": res_b["summary"],
                "rankings": res_b["rankings"],
            },
            "exp_2533c_conditional": {
                "median_meal_fraction": res_c["median_meal_fraction"],
                "subgroups": res_c["subgroups"],
                "high_meal_patients": res_c["high_meal_patients"],
                "low_meal_patients": res_c["low_meal_patients"],
            },
        },
        "per_patient_detail": {
            "exp_2533a": res_a["per_patient"],
            "exp_2533b": res_b["per_patient"],
            "exp_2533c_meal_fractions": res_c["meal_fractions"],
        },
        "elapsed_seconds": elapsed,
    }

    print(f"\nStatus: {status}")
    print(f"Elapsed: {elapsed}s")
    return result


def main():
    result = run_experiment()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"Results saved to {OUT_PATH}")


if __name__ == "__main__":
    main()
