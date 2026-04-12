#!/usr/bin/env python3
"""EXP-2587: TIR-Based Counter-Regulation k Prediction.

Hypotheses:
  H1: Patient TIR (and other glucose metrics) can predict optimal k
      with MAE < 1.0 (sufficient for population-level calibration)
  H2: A simple linear model (k = a × TIR + b) captures the relationship
      found in EXP-2582 (r=-0.64 between TIR and k)
  H3: Adding glucose variability metrics (CV, time below range)
      improves k prediction beyond TIR alone

Design:
  Collect per-patient features:
    - TIR (70-180), time below range (<70), time above range (>180)
    - Glucose CV, mean, median, SD
    - Correction frequency, bolus frequency
    - A1C estimate
  Fit linear/polynomial models to predict optimal k.
  Leave-one-out cross-validation.

  If confirmed, productionize as fallback k estimation when
  < MIN_CORRECTIONS available for direct calibration.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2587_k_prediction.json")

# Known optimal k from EXP-2582 and EXP-2584
PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "h": 0.0, "i": 3.0, "j": 0.0, "k": 0.0,
    "odc-74077367": 2.5, "odc-86025410": 0.5, "odc-96254963": 2.0,
}


def _compute_features(pdf: pd.DataFrame) -> dict:
    """Compute glucose and behavioral features for a patient."""
    g_all = pdf["glucose"].values
    g = g_all[~np.isnan(g_all)]
    if len(g) < 100:
        return {}

    tir = float(np.mean((g >= 70) & (g <= 180)))
    tbr = float(np.mean(g < 70))
    tar = float(np.mean(g > 180))
    mean_g = float(np.mean(g))
    sd_g = float(np.std(g))
    cv_g = sd_g / mean_g if mean_g > 0 else 0
    median_g = float(np.median(g))
    a1c = (mean_g + 46.7) / 28.7

    # Correction frequency (use aligned arrays)
    bolus = pdf["bolus"].fillna(0).values
    carbs = pdf["carbs"].fillna(0).values
    corr_mask = (bolus > 0.5) & (~np.isnan(g_all)) & (g_all > 150) & (carbs < 1.0)
    n_corrections = int(np.sum(corr_mask))
    n_boluses = int(np.sum(bolus > 0.1))
    n_days = max(1, pdf["time"].dt.date.nunique())
    corr_per_day = n_corrections / n_days
    bolus_per_day = n_boluses / n_days

    # Glucose dynamics
    roc = np.diff(g)
    mean_abs_roc = float(np.mean(np.abs(roc))) if len(roc) > 0 else 0
    pct_below_70 = float(np.mean(g < 70))
    pct_above_250 = float(np.mean(g > 250))

    return {
        "tir": round(tir, 3),
        "tbr": round(tbr, 3),
        "tar": round(tar, 3),
        "mean_glucose": round(mean_g, 1),
        "sd_glucose": round(sd_g, 1),
        "cv_glucose": round(cv_g, 3),
        "median_glucose": round(median_g, 1),
        "a1c_est": round(a1c, 2),
        "corr_per_day": round(corr_per_day, 2),
        "bolus_per_day": round(bolus_per_day, 2),
        "mean_abs_roc": round(mean_abs_roc, 2),
        "pct_below_70": round(pct_below_70, 3),
        "pct_above_250": round(pct_above_250, 3),
        "n_days": n_days,
    }


def _linear_predict(feature_vals, target_vals, leave_out_idx):
    """Simple leave-one-out linear regression prediction."""
    train_x = np.delete(feature_vals, leave_out_idx)
    train_y = np.delete(target_vals, leave_out_idx)
    if len(train_x) < 3:
        return float('nan')
    # y = a*x + b
    a, b = np.polyfit(train_x, train_y, 1)
    test_x = feature_vals[leave_out_idx]
    return float(a * test_x + b)


def _multi_linear_predict(feature_matrix, target_vals, leave_out_idx):
    """Leave-one-out multi-feature linear regression."""
    n = len(target_vals)
    train_mask = np.ones(n, dtype=bool)
    train_mask[leave_out_idx] = False
    X_train = feature_matrix[train_mask]
    y_train = target_vals[train_mask]
    X_test = feature_matrix[leave_out_idx:leave_out_idx+1]

    # Add intercept
    X_train_i = np.column_stack([X_train, np.ones(len(X_train))])
    X_test_i = np.column_stack([X_test, np.ones(1)])

    try:
        coeffs, _, _, _ = np.linalg.lstsq(X_train_i, y_train, rcond=None)
        return float(X_test_i @ coeffs)
    except Exception:
        return float('nan')


def run():
    df = pd.read_parquet(PARQUET)
    results = {"experiment": "EXP-2587", "patients": {}}

    # Collect features for all patients with known k
    patient_features = {}
    for pid in sorted(PATIENT_K.keys()):
        pdf = df[df["patient_id"] == pid]
        if len(pdf) == 0:
            continue
        feats = _compute_features(pdf)
        if feats:
            feats["optimal_k"] = PATIENT_K[pid]
            patient_features[pid] = feats

    print(f"Patients with features: {len(patient_features)}")

    # Print feature summary
    print(f"\n{'Patient':<20} {'TIR':>6} {'CV':>6} {'TBR':>6} {'TAR':>6} {'k':>4}")
    for pid, f in patient_features.items():
        print(f"{pid:<20} {f['tir']:>6.3f} {f['cv_glucose']:>6.3f} "
              f"{f['tbr']:>6.3f} {f['tar']:>6.3f} {f['optimal_k']:>4.1f}")

    pids = list(patient_features.keys())
    features_list = [patient_features[p] for p in pids]
    k_vals = np.array([f["optimal_k"] for f in features_list])

    # H1/H2: Single-feature prediction
    print(f"\n{'='*60}")
    print("SINGLE-FEATURE LOO PREDICTION")

    feature_names = ["tir", "cv_glucose", "tbr", "tar", "mean_glucose",
                     "corr_per_day", "mean_abs_roc", "pct_above_250"]

    single_results = {}
    for fname in feature_names:
        fvals = np.array([f[fname] for f in features_list])
        predictions = []
        for i in range(len(pids)):
            pred = _linear_predict(fvals, k_vals, i)
            predictions.append(pred)

        predictions = np.array(predictions)
        valid = ~np.isnan(predictions)
        if valid.sum() > 0:
            mae = float(np.mean(np.abs(predictions[valid] - k_vals[valid])))
            corr = float(np.corrcoef(fvals, k_vals)[0, 1])
            print(f"  {fname:<20}: LOO MAE={mae:.2f}, corr={corr:.3f}")
            single_results[fname] = {"mae": round(mae, 2), "correlation": round(corr, 3)}

    # H3: Multi-feature prediction
    print(f"\n{'='*60}")
    print("MULTI-FEATURE LOO PREDICTION")

    # Best single features + combinations
    combos = [
        ("tir_only", ["tir"]),
        ("tir+cv", ["tir", "cv_glucose"]),
        ("tir+tar+tbr", ["tir", "tar", "tbr"]),
        ("tir+cv+corr_freq", ["tir", "cv_glucose", "corr_per_day"]),
        ("all_glucose", ["tir", "cv_glucose", "tbr", "tar", "mean_abs_roc"]),
    ]

    multi_results = {}
    for combo_name, fnames in combos:
        feat_matrix = np.column_stack([
            np.array([f[fn] for f in features_list]) for fn in fnames
        ])
        predictions = []
        for i in range(len(pids)):
            pred = _multi_linear_predict(feat_matrix, k_vals, i)
            predictions.append(pred)

        predictions = np.array(predictions)
        valid = ~np.isnan(predictions)
        if valid.sum() > 0:
            mae = float(np.mean(np.abs(predictions[valid] - k_vals[valid])))
            # Clip negative predictions to 0
            clipped = np.clip(predictions[valid], 0, 10)
            mae_clipped = float(np.mean(np.abs(clipped - k_vals[valid])))
            print(f"  {combo_name:<25}: LOO MAE={mae:.2f} (clipped={mae_clipped:.2f})")
            multi_results[combo_name] = {
                "features": fnames,
                "mae": round(mae, 2),
                "mae_clipped": round(mae_clipped, 2),
            }

    # Practical fallback: population median k
    median_k = float(np.median(k_vals))
    pop_mae = float(np.mean(np.abs(k_vals - median_k)))
    print(f"\n  Population median k={median_k:.1f}: MAE={pop_mae:.2f}")

    # Print LOO predictions vs actual for best model
    print(f"\n{'='*60}")
    print("LOO PREDICTIONS (tir+cv model)")
    feat_matrix = np.column_stack([
        np.array([f["tir"] for f in features_list]),
        np.array([f["cv_glucose"] for f in features_list]),
    ])
    for i, pid in enumerate(pids):
        pred = _multi_linear_predict(feat_matrix, k_vals, i)
        pred_clipped = max(0, min(10, pred))
        actual = k_vals[i]
        error = abs(pred_clipped - actual)
        print(f"  {pid:<20}: predicted={pred_clipped:.1f}, actual={actual:.1f}, error={error:.1f}")

    results["patient_features"] = patient_features
    results["single_feature_prediction"] = single_results
    results["multi_feature_prediction"] = multi_results
    results["population_baseline"] = {"median_k": median_k, "mae": round(pop_mae, 2)}

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    run()
