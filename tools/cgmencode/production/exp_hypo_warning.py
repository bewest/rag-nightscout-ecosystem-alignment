#!/usr/bin/env python3
"""
exp_hypo_warning.py — Hypo Early Warning Signals (EXP-2539)

Builds early-warning detectors for hypoglycemia (glucose < 70 mg/dL) that
operate 30-60 minutes ahead — well before the 5-min median reduction lead
time found in EXP-2538.

Experiments:
  EXP-2539a: Pre-hypo feature divergence analysis
  EXP-2539b: Hypo prediction models (logistic regression + GBM)
  EXP-2539c: IOB-to-glucose ratio heuristic
  EXP-2539d: Trajectory-based kinematic warning
  EXP-2539e: Per-patient variation in predictability

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_hypo_warning.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_hypo_warning.py --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[3]
VIZ_DIR = ROOT / "visualizations" / "hypo-warning"
RESULTS_DIR = ROOT / "externals" / "experiments"

# ── constants ────────────────────────────────────────────────────────────────
STEPS_PER_5MIN = 1
STEP_MINUTES = 5
HYPO_THRESHOLD = 70
CONTROL_LO, CONTROL_HI = 80, 120

HORIZONS_STEPS = {
    "5min": 1,
    "15min": 3,
    "30min": 6,
    "45min": 9,
    "60min": 12,
}

FEATURE_LOOKBACK = {
    "-5min": 1,
    "-15min": 3,
    "-30min": 6,
    "-45min": 9,
    "-60min": 12,
}

STEPS_4H = 48


# ── data loading ─────────────────────────────────────────────────────────────
def load_data(tiny: bool = False) -> pd.DataFrame:
    if tiny:
        path = ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"Loading {path}...")
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df.sort_values(["patient_id", "time"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute / 60.0
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients")
    print(f"  Glucose non-null: {df['glucose'].notna().sum():,}")
    print(f"  Hypo readings (glucose<{HYPO_THRESHOLD}): "
          f"{(df['glucose'] < HYPO_THRESHOLD).sum():,}\n")
    return df


# ── helpers ──────────────────────────────────────────────────────────────────
def add_future_min_glucose(df: pd.DataFrame) -> pd.DataFrame:
    """Add column: minimum glucose in next 1h (12 steps)."""
    df["glucose_min_1h"] = np.nan
    for pid in df["patient_id"].unique():
        idx = df.index[df["patient_id"] == pid]
        g = df.loc[idx, "glucose"].values
        n = len(g)
        g_min = np.full(n, np.nan)
        for i in range(n - 1):
            end = min(i + HORIZONS_STEPS["60min"] + 1, n)
            window = g[i + 1:end]
            valid = window[~np.isnan(window)]
            if len(valid) > 0:
                g_min[i] = np.nanmin(valid)
        df.loc[idx, "glucose_min_1h"] = g_min
    return df


def identify_hypo_events(df: pd.DataFrame) -> list[dict]:
    """Find de-duplicated hypo events (first entry below 70 with 30-min gap)."""
    events = []
    for pid in df["patient_id"].unique():
        pdf = df[df["patient_id"] == pid]
        gluc = pdf["glucose"].values
        idx_arr = pdf.index.values
        times = pdf["time"].values

        hypo_positions = np.where(~np.isnan(gluc) & (gluc < HYPO_THRESHOLD))[0]
        last = -999
        for pos in hypo_positions:
            if pos - last >= 6:  # 30-min dedup
                events.append({
                    "patient_id": pid,
                    "pos": pos,  # position within patient's data
                    "idx": idx_arr[pos],
                    "glucose": float(gluc[pos]),
                    "time": pd.Timestamp(times[pos]),
                    "n_total": len(idx_arr),
                })
                last = pos
    return events


def extract_features_at_offset(df_patient: pd.DataFrame, hypo_pos: int,
                                offset_steps: int) -> dict | None:
    """Extract features at a given offset before the hypo event."""
    target_pos = hypo_pos - offset_steps
    if target_pos < 0:
        return None

    row = df_patient.iloc[target_pos]
    g = row.get("glucose")
    if pd.isna(g):
        return None

    return {
        "glucose": float(g),
        "glucose_roc": float(row["glucose_roc"]) if not pd.isna(row["glucose_roc"]) else None,
        "glucose_accel": float(row["glucose_accel"]) if not pd.isna(row["glucose_accel"]) else None,
        "iob": float(row["iob"]),
        "cob": float(row["cob"]),
        "net_basal": float(row["net_basal"]),
        "hour": float(row["hour"]),
        "scheduled_isf": float(row["scheduled_isf"]),
        "bolus": float(row["bolus"]),
        "bolus_smb": float(row["bolus_smb"]),
    }


def compute_iob_rate(df_patient: pd.DataFrame, pos: int) -> float | None:
    """IOB rate of change at a position (IOB[t] - IOB[t-1])."""
    if pos < 1:
        return None
    iob_now = df_patient.iloc[pos]["iob"]
    iob_prev = df_patient.iloc[pos - 1]["iob"]
    if pd.isna(iob_now) or pd.isna(iob_prev):
        return None
    return float(iob_now - iob_prev)


# ── EXP-2539a: Pre-hypo feature divergence ──────────────────────────────────
def exp_2539a(df: pd.DataFrame) -> dict:
    """Compare feature trajectories before hypo vs matched non-hypo controls."""
    print("=" * 70)
    print("EXP-2539a: Pre-Hypo Feature Divergence Analysis")
    print("=" * 70)

    hypo_events = identify_hypo_events(df)
    print(f"  De-duplicated hypo events: {len(hypo_events)}")

    # For each hypo event, extract features at offsets
    offsets = [1, 3, 6, 9, 12]  # -5, -15, -30, -45, -60 min
    offset_labels = ["-5min", "-15min", "-30min", "-45min", "-60min"]

    hypo_features = {label: [] for label in offset_labels}
    control_features = {label: [] for label in offset_labels}

    patient_dfs = {pid: df[df["patient_id"] == pid] for pid in df["patient_id"].unique()}

    # Extract hypo features
    for ev in hypo_events:
        pdf = patient_dfs[ev["patient_id"]]
        for off, label in zip(offsets, offset_labels):
            feats = extract_features_at_offset(pdf, ev["pos"], off)
            if feats is not None:
                feats["iob_rate"] = compute_iob_rate(pdf, ev["pos"] - off)
                hypo_features[label].append(feats)

    # Find control windows: glucose in 80-120, same patient, no hypo in next 4h
    print("  Finding matched non-hypo controls...")
    np.random.seed(42)
    for pid, pdf in patient_dfs.items():
        gluc = pdf["glucose"].values
        n = len(gluc)
        hours = pdf["hour"].values

        # Find positions with glucose in control range
        for i in range(12, n - STEPS_4H):
            g = gluc[i]
            if pd.isna(g) or g < CONTROL_LO or g > CONTROL_HI:
                continue

            # Check no hypo in next 4h
            future = gluc[i + 1:min(i + STEPS_4H + 1, n)]
            valid_future = future[~np.isnan(future)]
            if len(valid_future) == 0:
                continue
            if np.any(valid_future < HYPO_THRESHOLD):
                continue

            # Subsample: take ~1 in 20 to balance counts
            if np.random.random() > 0.05:
                continue

            for off, label in zip(offsets, offset_labels):
                # Use the current position as the "event" and look back
                feats = extract_features_at_offset(pdf, i, off)
                if feats is not None:
                    feats["iob_rate"] = compute_iob_rate(pdf, i - off)
                    control_features[label].append(feats)

    # Compute divergence statistics
    results = {"hypo_event_count": len(hypo_events), "divergence": {}}
    feature_names = ["glucose", "glucose_roc", "glucose_accel", "iob", "cob",
                     "net_basal", "iob_rate"]

    print(f"\n  {'Feature':<18} {'Offset':<8} {'Hypo mean':>10} {'Ctrl mean':>10} "
          f"{'Diff':>8} {'p_approx':>10}")
    print("  " + "-" * 72)

    for feat_name in feature_names:
        results["divergence"][feat_name] = {}
        for label in offset_labels:
            h_vals = [f[feat_name] for f in hypo_features[label]
                      if f.get(feat_name) is not None]
            c_vals = [f[feat_name] for f in control_features[label]
                      if f.get(feat_name) is not None]

            if len(h_vals) < 20 or len(c_vals) < 20:
                continue

            h_mean = float(np.mean(h_vals))
            c_mean = float(np.mean(c_vals))
            h_std = float(np.std(h_vals))
            c_std = float(np.std(c_vals))

            # Cohen's d effect size
            pooled_std = np.sqrt((h_std**2 + c_std**2) / 2)
            cohens_d = (h_mean - c_mean) / pooled_std if pooled_std > 0 else 0

            # Approximate z-test p-value
            se = np.sqrt(h_std**2 / len(h_vals) + c_std**2 / len(c_vals))
            z = abs(h_mean - c_mean) / se if se > 0 else 0
            from scipy import stats as _stats
            p_val = 2 * (1 - _stats.norm.cdf(z))

            results["divergence"][feat_name][label] = {
                "hypo_mean": round(h_mean, 4),
                "control_mean": round(c_mean, 4),
                "hypo_n": len(h_vals),
                "control_n": len(c_vals),
                "cohens_d": round(cohens_d, 4),
                "p_value": round(p_val, 6),
            }

            print(f"  {feat_name:<18} {label:<8} {h_mean:>10.3f} {c_mean:>10.3f} "
                  f"{h_mean - c_mean:>+8.3f} {p_val:>10.6f}")

    # Identify earliest divergence point (furthest from event)
    earliest = {}
    for feat_name in feature_names:
        if feat_name not in results["divergence"]:
            continue
        for label in reversed(offset_labels):
            entry = results["divergence"][feat_name].get(label)
            if entry and abs(entry["cohens_d"]) > 0.3 and entry["p_value"] < 0.01:
                earliest[feat_name] = label
                break

    results["earliest_significant_divergence"] = earliest
    print(f"\n  Earliest significant divergence (|d|>0.3, p<0.01):")
    for feat, t in sorted(earliest.items()):
        print(f"    {feat}: {t}")

    return results


# ── EXP-2539b: Hypo prediction models ───────────────────────────────────────
def exp_2539b(df: pd.DataFrame) -> dict:
    """Logistic regression + GBM to predict hypo within 60 min."""
    print("\n" + "=" * 70)
    print("EXP-2539b: Hypo Prediction Models (Logistic Reg + GBM)")
    print("=" * 70)

    # Build prediction dataset
    mask = (
        df["glucose"].notna() &
        df["glucose_roc"].notna() &
        df["glucose_accel"].notna() &
        df["glucose_min_1h"].notna()
    )
    pred_df = df[mask].copy()

    pred_df["target"] = (pred_df["glucose_min_1h"] < HYPO_THRESHOLD).astype(int)

    feature_cols = ["glucose", "glucose_roc", "glucose_accel", "iob", "cob",
                    "net_basal", "hour"]
    # Add ISF-based feature
    pred_df["iob_isf_ratio"] = pred_df["iob"] * pred_df["scheduled_isf"] / (
        pred_df["glucose"].clip(lower=HYPO_THRESHOLD + 1) - HYPO_THRESHOLD
    )
    feature_cols.append("iob_isf_ratio")

    print(f"  Prediction dataset: {len(pred_df):,} rows")
    print(f"  Positive rate (hypo within 1h): "
          f"{pred_df['target'].mean()*100:.2f}%")

    X = pred_df[feature_cols].values
    y = pred_df["target"].values
    times = pred_df["time"].values

    # Handle any remaining NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=10.0, neginf=-10.0)

    # Temporal CV: split by time, no shuffling
    sorted_idx = np.argsort(times)
    X, y, times = X[sorted_idx], y[sorted_idx], times[sorted_idx]

    n = len(X)
    n_folds = 5
    fold_size = n // n_folds

    results = {"models": {}}

    for model_name, model_cls, model_kwargs in [
        ("logistic_regression", LogisticRegression,
         {"max_iter": 1000, "class_weight": "balanced", "solver": "lbfgs"}),
        ("gradient_boosting", GradientBoostingClassifier,
         {"n_estimators": 200, "max_depth": 4, "subsample": 0.8,
          "learning_rate": 0.1, "random_state": 42}),
    ]:
        print(f"\n  Training {model_name}...")
        fold_aucs = []
        fold_precisions = []
        fold_recalls = []
        all_preds = []
        all_true = []
        all_glucs = []

        for fold in range(n_folds):
            # Last fold is always test
            test_start = fold * fold_size
            test_end = (fold + 1) * fold_size if fold < n_folds - 1 else n

            # Train on all data before test fold (temporal)
            if fold == 0:
                continue  # no training data for first fold
            train_end = test_start

            X_train, y_train = X[:train_end], y[:train_end]
            X_test, y_test = X[test_start:test_end], y[test_start:test_end]

            if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
                continue

            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_test_s = scaler.transform(X_test)

            model = model_cls(**model_kwargs)

            # For GBM, handle class imbalance with sample weights
            if model_name == "gradient_boosting":
                pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
                sample_weight = np.where(y_train == 1, pos_weight, 1.0)
                model.fit(X_train_s, y_train, sample_weight=sample_weight)
            else:
                model.fit(X_train_s, y_train)

            y_prob = model.predict_proba(X_test_s)[:, 1]

            auc = roc_auc_score(y_test, y_prob)
            fold_aucs.append(auc)

            # At threshold that gives ~80% recall
            thresholds = np.percentile(y_prob, np.arange(0, 100, 5))
            best_thresh = 0.5
            for t in thresholds:
                y_pred_t = (y_prob >= t).astype(int)
                if y_pred_t.sum() > 0 and y_test.sum() > 0:
                    rec = recall_score(y_test, y_pred_t, zero_division=0)
                    if rec >= 0.75:
                        best_thresh = t
                        break

            y_pred = (y_prob >= best_thresh).astype(int)
            prec = precision_score(y_test, y_pred, zero_division=0)
            rec = recall_score(y_test, y_pred, zero_division=0)
            fold_precisions.append(prec)
            fold_recalls.append(rec)

            all_preds.extend(y_prob.tolist())
            all_true.extend(y_test.tolist())
            # glucose values for lead time analysis
            all_glucs.extend(X[test_start:test_end, 0].tolist())

            print(f"    Fold {fold}: AUC={auc:.4f}, P={prec:.3f}, R={rec:.3f} "
                  f"(n_train={len(y_train)}, n_test={len(y_test)}, "
                  f"pos_rate={y_test.mean()*100:.1f}%)")

        if not fold_aucs:
            results["models"][model_name] = {"error": "insufficient data"}
            continue

        mean_auc = float(np.mean(fold_aucs))
        std_auc = float(np.std(fold_aucs))
        mean_prec = float(np.mean(fold_precisions))
        mean_rec = float(np.mean(fold_recalls))

        # Feature importance for GBM (from last fold)
        feat_importance = None
        if model_name == "gradient_boosting" and hasattr(model, "feature_importances_"):
            feat_importance = {
                feat_name: round(float(imp), 4)
                for feat_name, imp in zip(feature_cols, model.feature_importances_)
            }
            print(f"\n    Feature importance:")
            for fn, imp in sorted(feat_importance.items(), key=lambda x: -x[1]):
                print(f"      {fn:<20} {imp:.4f}")

        # Lead time analysis: for true positives, how early can we detect?
        all_preds_arr = np.array(all_preds)
        all_true_arr = np.array(all_true)
        all_glucs_arr = np.array(all_glucs)

        # Bin by current glucose level to see detection at different stages
        lead_time_bins = {}
        for g_lo, g_hi, label in [(70, 90, "70-90"), (90, 110, "90-110"),
                                   (110, 140, "110-140"), (140, 180, "140-180"),
                                   (180, 400, "180+")]:
            g_mask = (all_glucs_arr >= g_lo) & (all_glucs_arr < g_hi)
            if g_mask.sum() < 50:
                continue
            pos_mask = g_mask & (all_true_arr == 1)
            if pos_mask.sum() < 10:
                lead_time_bins[label] = {
                    "n_total": int(g_mask.sum()),
                    "n_positive": int(pos_mask.sum()),
                    "detection_rate": None,
                }
                continue

            # Detection rate at 0.5 threshold
            detected = all_preds_arr[pos_mask] >= 0.5
            lead_time_bins[label] = {
                "n_total": int(g_mask.sum()),
                "n_positive": int(pos_mask.sum()),
                "detection_rate": round(float(detected.mean()), 4),
            }

        results["models"][model_name] = {
            "mean_auc": round(mean_auc, 4),
            "std_auc": round(std_auc, 4),
            "mean_precision": round(mean_prec, 4),
            "mean_recall": round(mean_rec, 4),
            "fold_aucs": [round(a, 4) for a in fold_aucs],
            "feature_importance": feat_importance,
            "detection_by_glucose_range": lead_time_bins,
        }

        print(f"\n  {model_name} summary: AUC={mean_auc:.4f}±{std_auc:.4f}, "
              f"P={mean_prec:.3f}, R={mean_rec:.3f}")

    results["feature_columns"] = feature_cols
    results["target"] = "glucose_min_1h < 70"
    results["cv_method"] = "temporal_5fold"
    return results


# ── EXP-2539c: IOB-to-glucose ratio heuristic ───────────────────────────────
def exp_2539c(df: pd.DataFrame) -> dict:
    """Test heuristic: hypo_risk = iob × isf / (sgv - 70)."""
    print("\n" + "=" * 70)
    print("EXP-2539c: IOB-to-Glucose Ratio Heuristic")
    print("=" * 70)

    mask = df["glucose"].notna() & df["glucose_min_1h"].notna()
    hdf = df[mask].copy()

    # Compute heuristic: iob × isf / (glucose - 70)
    # Clip glucose to avoid division by zero / negative
    denom = (hdf["glucose"] - HYPO_THRESHOLD).clip(lower=1.0)
    hdf["hypo_risk_ratio"] = hdf["iob"] * hdf["scheduled_isf"] / denom

    hdf["actual_hypo"] = (hdf["glucose_min_1h"] < HYPO_THRESHOLD).astype(int)

    print(f"  Dataset: {len(hdf):,} rows, "
          f"hypo rate: {hdf['actual_hypo'].mean()*100:.2f}%")

    results = {"thresholds": {}}

    # Test different thresholds
    print(f"\n  {'Threshold':>10} {'Precision':>10} {'Recall':>10} {'F1':>8} "
          f"{'FPR':>8} {'Flagged%':>9}")
    print("  " + "-" * 60)

    for thresh in [0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0]:
        predicted = (hdf["hypo_risk_ratio"] >= thresh).astype(int)
        tp = int(((predicted == 1) & (hdf["actual_hypo"] == 1)).sum())
        fp = int(((predicted == 1) & (hdf["actual_hypo"] == 0)).sum())
        fn = int(((predicted == 0) & (hdf["actual_hypo"] == 1)).sum())
        tn = int(((predicted == 0) & (hdf["actual_hypo"] == 0)).sum())

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        flagged = (tp + fp) / len(hdf)

        results["thresholds"][str(thresh)] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "fpr": round(fpr, 4),
            "flagged_pct": round(flagged * 100, 2),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        }

        print(f"  {thresh:>10.1f} {prec:>10.4f} {rec:>10.4f} {f1:>8.4f} "
              f"{fpr:>8.4f} {flagged*100:>8.2f}%")

    # AUC of the raw ratio as a continuous score
    if len(np.unique(hdf["actual_hypo"])) == 2:
        ratio_vals = hdf["hypo_risk_ratio"].clip(upper=50).values
        ratio_vals = np.nan_to_num(ratio_vals, nan=0.0)
        auc = roc_auc_score(hdf["actual_hypo"].values, ratio_vals)
        results["continuous_auc"] = round(auc, 4)
        print(f"\n  Continuous AUC (ratio as score): {auc:.4f}")

    # By glucose range: how well does it work when glucose is still normal?
    print(f"\n  Detection by current glucose level:")
    glucose_range_results = {}
    for g_lo, g_hi, label in [(70, 90, "70-90"), (90, 110, "90-110"),
                               (110, 140, "110-140"), (140, 180, "140-180")]:
        g_mask = (hdf["glucose"] >= g_lo) & (hdf["glucose"] < g_hi)
        if g_mask.sum() < 100:
            continue
        subset = hdf[g_mask]
        pos_n = int(subset["actual_hypo"].sum())
        if pos_n < 10:
            continue

        # At threshold 1.0
        pred = (subset["hypo_risk_ratio"] >= 1.0).astype(int)
        tp = int(((pred == 1) & (subset["actual_hypo"] == 1)).sum())
        fn = int(((pred == 0) & (subset["actual_hypo"] == 1)).sum())
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0

        fp = int(((pred == 1) & (subset["actual_hypo"] == 0)).sum())
        tn = int(((pred == 0) & (subset["actual_hypo"] == 0)).sum())
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

        glucose_range_results[label] = {
            "n_total": int(g_mask.sum()),
            "n_hypo": pos_n,
            "recall_at_1.0": round(rec, 4),
            "fpr_at_1.0": round(fpr, 4),
        }
        print(f"    {label}: n={g_mask.sum():,}, hypo={pos_n}, "
              f"recall={rec:.3f}, FPR={fpr:.3f}")

    results["by_glucose_range"] = glucose_range_results
    return results


# ── EXP-2539d: Trajectory-based kinematic warning ───────────────────────────
def exp_2539d(df: pd.DataFrame) -> dict:
    """Extrapolate glucose using kinematic equations."""
    print("\n" + "=" * 70)
    print("EXP-2539d: Trajectory-Based Kinematic Warning")
    print("=" * 70)

    mask = (
        df["glucose"].notna() &
        df["glucose_roc"].notna() &
        df["glucose_accel"].notna() &
        df["glucose_min_1h"].notna()
    )
    tdf = df[mask].copy()
    tdf["actual_hypo"] = (tdf["glucose_min_1h"] < HYPO_THRESHOLD).astype(int)

    print(f"  Dataset: {len(tdf):,} rows, "
          f"hypo rate: {tdf['actual_hypo'].mean()*100:.2f}%")

    # Predict glucose at different horizons
    # predicted_sgv = sgv + dsgv/dt × horizon + 0.5 × d²sgv/dt² × horizon²
    # Note: glucose_roc is per 5 min, glucose_accel is per 5 min²
    results = {"horizons": {}}

    print(f"\n  {'Horizon':>10} {'AUC':>8} {'Prec':>8} {'Recall':>8} {'FPR':>8}")
    print("  " + "-" * 50)

    for label, steps in [("15min", 3), ("30min", 6), ("45min", 9), ("60min", 12)]:
        # Extrapolate: glucose_roc is already per 5-min step
        predicted_g = (
            tdf["glucose"].values +
            tdf["glucose_roc"].values * steps +
            0.5 * tdf["glucose_accel"].values * steps**2
        )

        # Predict hypo if extrapolated glucose < 70
        pred_hypo = (predicted_g < HYPO_THRESHOLD).astype(int)

        tp = int(((pred_hypo == 1) & (tdf["actual_hypo"].values == 1)).sum())
        fp = int(((pred_hypo == 1) & (tdf["actual_hypo"].values == 0)).sum())
        fn = int(((pred_hypo == 0) & (tdf["actual_hypo"].values == 1)).sum())
        tn = int(((pred_hypo == 0) & (tdf["actual_hypo"].values == 0)).sum())

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

        # AUC using negative predicted glucose as continuous score
        # (lower predicted = more likely hypo)
        if len(np.unique(tdf["actual_hypo"])) == 2:
            auc = roc_auc_score(tdf["actual_hypo"].values, -predicted_g)
        else:
            auc = float("nan")

        results["horizons"][label] = {
            "auc": round(auc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "fpr": round(fpr, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        }

        print(f"  {label:>10} {auc:>8.4f} {prec:>8.4f} {rec:>8.4f} {fpr:>8.4f}")

    # Compare: combined heuristic (kinematic + IOB ratio)
    print("\n  Combined: kinematic + IOB ratio")
    denom = (tdf["glucose"] - HYPO_THRESHOLD).clip(lower=1.0)
    iob_risk = tdf["iob"].values * tdf["scheduled_isf"].values / denom.values

    for label, steps in [("30min", 6), ("60min", 12)]:
        predicted_g = (
            tdf["glucose"].values +
            tdf["glucose_roc"].values * steps +
            0.5 * tdf["glucose_accel"].values * steps**2
        )

        # Combined score: both kinematic and IOB suggest hypo
        combined_pred = ((predicted_g < HYPO_THRESHOLD) | (iob_risk > 1.0)).astype(int)

        tp = int(((combined_pred == 1) & (tdf["actual_hypo"].values == 1)).sum())
        fp = int(((combined_pred == 1) & (tdf["actual_hypo"].values == 0)).sum())
        fn = int(((combined_pred == 0) & (tdf["actual_hypo"].values == 1)).sum())
        tn = int(((combined_pred == 0) & (tdf["actual_hypo"].values == 0)).sum())

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0

        # AUC on combined continuous score
        combined_score = -predicted_g + iob_risk * 30  # weighted combo
        combined_score = np.nan_to_num(combined_score, nan=0.0)
        if len(np.unique(tdf["actual_hypo"])) == 2:
            auc = roc_auc_score(tdf["actual_hypo"].values, combined_score)
        else:
            auc = float("nan")

        key = f"combined_{label}"
        results["horizons"][key] = {
            "auc": round(auc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "fpr": round(fpr, 4),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "method": "kinematic_OR_iob_ratio",
        }

        print(f"  combined_{label:>5}: AUC={auc:.4f}, P={prec:.4f}, "
              f"R={rec:.4f}, FPR={fpr:.4f}")

    return results


# ── EXP-2539e: Per-patient variation ─────────────────────────────────────────
def exp_2539e(df: pd.DataFrame) -> dict:
    """Per-patient AUC for the best model approach."""
    print("\n" + "=" * 70)
    print("EXP-2539e: Per-Patient Variation in Hypo Predictability")
    print("=" * 70)

    results = {"patients": {}}

    mask = (
        df["glucose"].notna() &
        df["glucose_roc"].notna() &
        df["glucose_accel"].notna() &
        df["glucose_min_1h"].notna()
    )

    feature_cols = ["glucose", "glucose_roc", "glucose_accel", "iob", "cob",
                    "net_basal", "hour"]

    for pid in sorted(df["patient_id"].unique()):
        pdf = df[(df["patient_id"] == pid) & mask]
        if len(pdf) < 200:
            continue

        pdf = pdf.copy()
        pdf["target"] = (pdf["glucose_min_1h"] < HYPO_THRESHOLD).astype(int)

        n_hypo = int(pdf["target"].sum())
        hypo_rate = float(pdf["target"].mean())

        if n_hypo < 10 or len(np.unique(pdf["target"])) < 2:
            results["patients"][pid] = {
                "n_rows": len(pdf),
                "n_hypo_events": n_hypo,
                "hypo_rate": round(hypo_rate * 100, 2),
                "note": "insufficient hypo events for evaluation",
            }
            continue

        X = pdf[feature_cols].values
        y = pdf["target"].values
        X = np.nan_to_num(X, nan=0.0, posinf=10.0, neginf=-10.0)

        # Add IOB-ISF ratio
        denom = (pdf["glucose"] - HYPO_THRESHOLD).clip(lower=1.0).values
        iob_ratio = pdf["iob"].values * pdf["scheduled_isf"].values / denom
        iob_ratio = np.nan_to_num(iob_ratio, nan=0.0, posinf=10.0)
        X = np.column_stack([X, iob_ratio])

        # Simple temporal split: first 70% train, last 30% test
        split = int(0.7 * len(X))
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            results["patients"][pid] = {
                "n_rows": len(pdf),
                "n_hypo_events": n_hypo,
                "hypo_rate": round(hypo_rate * 100, 2),
                "note": "class imbalance prevents evaluation",
            }
            continue

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # GBM per patient
        pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
        sample_weight = np.where(y_train == 1, pos_weight, 1.0)

        model = GradientBoostingClassifier(
            n_estimators=100, max_depth=3, subsample=0.8,
            learning_rate=0.1, random_state=42
        )
        model.fit(X_train_s, y_train, sample_weight=sample_weight)
        y_prob = model.predict_proba(X_test_s)[:, 1]

        auc = roc_auc_score(y_test, y_prob)

        # Also test IOB ratio heuristic per patient
        iob_ratio_test = X_test[:, -1]
        iob_auc = roc_auc_score(y_test, iob_ratio_test)

        # Also test kinematic at 30min
        g = X_test[:, 0]
        roc_val = X_test[:, 1]
        accel = X_test[:, 2]
        pred_30 = g + roc_val * 6 + 0.5 * accel * 36
        kin_auc = roc_auc_score(y_test, -pred_30)

        # Patient characteristics
        patient_gluc = pdf["glucose"].dropna()
        patient_iob = pdf["iob"]

        results["patients"][pid] = {
            "n_rows": int(len(pdf)),
            "n_hypo_events": n_hypo,
            "hypo_rate": round(hypo_rate * 100, 2),
            "gbm_auc": round(float(auc), 4),
            "iob_ratio_auc": round(float(iob_auc), 4),
            "kinematic_30min_auc": round(float(kin_auc), 4),
            "mean_glucose": round(float(patient_gluc.mean()), 1),
            "std_glucose": round(float(patient_gluc.std()), 1),
            "cv_pct": round(float(100 * patient_gluc.std() / patient_gluc.mean()), 1),
            "mean_iob": round(float(patient_iob.mean()), 3),
            "controller": "ODC" if pid.startswith("odc") else "NS",
        }

        print(f"  {pid:<20} GBM={auc:.3f}  IOB_ratio={iob_auc:.3f}  "
              f"Kinematic={kin_auc:.3f}  hypo_rate={hypo_rate*100:.1f}%  "
              f"CV={100*patient_gluc.std()/patient_gluc.mean():.1f}%")

    # Summary statistics
    evaluated = {k: v for k, v in results["patients"].items() if "gbm_auc" in v}
    if evaluated:
        gbm_aucs = [v["gbm_auc"] for v in evaluated.values()]
        iob_aucs = [v["iob_ratio_auc"] for v in evaluated.values()]
        kin_aucs = [v["kinematic_30min_auc"] for v in evaluated.values()]

        results["summary"] = {
            "n_patients_evaluated": len(evaluated),
            "gbm_auc_mean": round(float(np.mean(gbm_aucs)), 4),
            "gbm_auc_std": round(float(np.std(gbm_aucs)), 4),
            "gbm_auc_min": round(float(np.min(gbm_aucs)), 4),
            "gbm_auc_max": round(float(np.max(gbm_aucs)), 4),
            "iob_ratio_auc_mean": round(float(np.mean(iob_aucs)), 4),
            "kinematic_30min_auc_mean": round(float(np.mean(kin_aucs)), 4),
            "best_method_per_patient": {
                pid: max(
                    [("gbm", v["gbm_auc"]),
                     ("iob_ratio", v["iob_ratio_auc"]),
                     ("kinematic", v["kinematic_30min_auc"])],
                    key=lambda x: x[1]
                )[0]
                for pid, v in evaluated.items()
            },
        }

        # Correlation between predictability and patient characteristics
        cvs = [v["cv_pct"] for v in evaluated.values()]
        corr_cv_auc = float(np.corrcoef(cvs, gbm_aucs)[0, 1]) if len(cvs) > 2 else None
        results["summary"]["correlation_cv_vs_auc"] = (
            round(corr_cv_auc, 4) if corr_cv_auc is not None else None
        )

        print(f"\n  Summary:")
        print(f"    GBM AUC: {np.mean(gbm_aucs):.4f} ± {np.std(gbm_aucs):.4f} "
              f"(range {np.min(gbm_aucs):.3f}–{np.max(gbm_aucs):.3f})")
        print(f"    IOB ratio AUC: {np.mean(iob_aucs):.4f}")
        print(f"    Kinematic AUC: {np.mean(kin_aucs):.4f}")
        if corr_cv_auc is not None:
            print(f"    Correlation(CV%, GBM AUC): {corr_cv_auc:.3f}")

    return results


# ── visualization ────────────────────────────────────────────────────────────
def generate_visualizations(r_a: dict, r_b: dict, r_c: dict,
                            r_d: dict, r_e: dict) -> None:
    """Generate ASCII/text visualizations for key findings."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("EXP-2539: Hypo Early Warning Signals — Visualization Summary")
    lines.append("=" * 70)

    # 1. Feature divergence timeline
    lines.append("\n1. Feature Divergence Timeline (Cohen's d)")
    lines.append("-" * 50)
    if "divergence" in r_a:
        for feat in ["glucose", "glucose_roc", "iob", "iob_rate"]:
            if feat in r_a["divergence"]:
                vals = r_a["divergence"][feat]
                line = f"  {feat:<18}"
                for offset in ["-60min", "-45min", "-30min", "-15min", "-5min"]:
                    if offset in vals:
                        d = vals[offset]["cohens_d"]
                        bar = "█" * min(int(abs(d) * 10), 20)
                        line += f" {d:>+6.2f}{bar}"
                    else:
                        line += "       —"
                lines.append(line)

    # 2. Model comparison
    lines.append("\n2. Model AUC Comparison")
    lines.append("-" * 50)
    if "models" in r_b:
        for name, data in r_b["models"].items():
            if "mean_auc" in data:
                auc = data["mean_auc"]
                bar = "█" * int(auc * 40)
                lines.append(f"  {name:<25} AUC={auc:.4f} {bar}")

    # 3. IOB ratio performance
    lines.append("\n3. IOB Ratio Heuristic (threshold scan)")
    lines.append("-" * 50)
    if "thresholds" in r_c:
        for thresh, data in sorted(r_c["thresholds"].items(), key=lambda x: float(x[0])):
            prec = data["precision"]
            rec = data["recall"]
            lines.append(f"  thresh={float(thresh):>4.1f}  P={prec:.3f}  R={rec:.3f}  "
                         f"FPR={data['fpr']:.3f}")

    # 4. Kinematic horizon comparison
    lines.append("\n4. Kinematic Prediction by Horizon")
    lines.append("-" * 50)
    if "horizons" in r_d:
        for horizon, data in r_d["horizons"].items():
            auc = data.get("auc", 0)
            lines.append(f"  {horizon:<15} AUC={auc:.4f}  P={data['precision']:.3f}  "
                         f"R={data['recall']:.3f}")

    # 5. Per-patient AUC
    lines.append("\n5. Per-Patient GBM AUC")
    lines.append("-" * 50)
    if "patients" in r_e:
        for pid, data in sorted(r_e["patients"].items()):
            if "gbm_auc" in data:
                auc = data["gbm_auc"]
                bar = "█" * int(auc * 30)
                lines.append(f"  {pid:<20} {auc:.3f} {bar}")

    viz_text = "\n".join(lines)
    viz_path = VIZ_DIR / "summary.txt"
    with open(viz_path, "w") as f:
        f.write(viz_text)
    print(f"\n  Visualization saved to {viz_path}")


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="EXP-2539: Hypo Early Warning Signals")
    parser.add_argument("--tiny", action="store_true",
                        help="Use tiny dataset for quick testing")
    args = parser.parse_args()

    df = load_data(tiny=args.tiny)

    # Compute future glucose min within 1h
    print("Computing minimum glucose in next 60 min...")
    df = add_future_min_glucose(df)
    valid = df["glucose_min_1h"].notna().sum()
    hypo_target = (df["glucose_min_1h"] < HYPO_THRESHOLD).sum()
    print(f"  Valid rows with future min: {valid:,}")
    print(f"  Rows with hypo in next 1h: {hypo_target:,} "
          f"({100*hypo_target/valid:.2f}%)\n")

    # Run sub-experiments
    r_a = exp_2539a(df)
    r_b = exp_2539b(df)
    r_c = exp_2539c(df)
    r_d = exp_2539d(df)
    r_e = exp_2539e(df)

    # Generate visualizations
    print("\nGenerating visualizations...")
    generate_visualizations(r_a, r_b, r_c, r_d, r_e)

    # Compile overall summary
    summary = {
        "key_question": "Can we detect hypo risk with AUC > 0.85 at 30-min lead time?",
        "baseline": "Current loop median reduction lead time: 5 min (EXP-2538)",
    }

    # Extract best AUCs
    best_auc = 0
    best_method = "none"
    if "models" in r_b:
        for name, data in r_b["models"].items():
            if "mean_auc" in data and data["mean_auc"] > best_auc:
                best_auc = data["mean_auc"]
                best_method = name
    if "continuous_auc" in r_c:
        if r_c["continuous_auc"] > best_auc:
            best_auc = r_c["continuous_auc"]
            best_method = "iob_ratio_heuristic"
    for horizon, data in r_d.get("horizons", {}).items():
        if "auc" in data and data["auc"] > best_auc:
            best_auc = data["auc"]
            best_method = f"kinematic_{horizon}"

    summary["best_auc"] = best_auc
    summary["best_method"] = best_method
    summary["target_met"] = best_auc > 0.85

    # Save results
    all_results = {
        "experiment": "EXP-2539",
        "title": "Hypo Early Warning Signals",
        "summary": summary,
        "sub_experiments": {
            "exp_2539a_feature_divergence": r_a,
            "exp_2539b_prediction_models": r_b,
            "exp_2539c_iob_ratio_heuristic": r_c,
            "exp_2539d_trajectory_kinematic": r_d,
            "exp_2539e_per_patient_variation": r_e,
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "exp-2539_hypo_warning.json"
    with open(out_path, "w") as f:
        def convert(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.floating, np.float64, np.float32)):
                return float(obj)
            if isinstance(obj, (np.integer, np.int64, np.int32)):
                return int(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            raise TypeError(f"Cannot serialize {type(obj)}")
        json.dump(all_results, f, indent=2, default=convert)

    print(f"\n{'='*70}")
    print(f"Results saved to {out_path}")
    print(f"Best AUC: {best_auc:.4f} ({best_method})")
    print(f"Target (AUC > 0.85): {'✓ MET' if best_auc > 0.85 else '✗ NOT MET'}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
