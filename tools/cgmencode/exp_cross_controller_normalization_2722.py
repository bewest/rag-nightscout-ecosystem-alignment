#!/usr/bin/env python3
"""EXP-2722: Cross-Controller ISF Normalization

Uses the deconfounding pipeline to extract controller-independent ISF per patient.
Tests whether deconfounded ISF enables settings translation between Loop, Trio,
and AAPS/OpenAPS — critical for users switching controllers (e.g., Loop → Trio).

Background (prior experiments):
  EXP-2675: Cross-controller ISF differs (Loop median=7.3, Trio=4.7, OpenAPS=32.5)
  EXP-2710: Multi-factor R²=0.224 with patient, BG₀, dose, circadian, IOB, channels, glycogen
  EXP-2714: R²=0.173 survives on independent events
  EXP-2698: Channel coefficients: BOLUS=-129.2, SMB=-123.6, EXCESS_BASAL=-130.5

Hypothesis: controller type inflates/deflates observed ISF due to different
SMB usage patterns, basal modulation strategies, and bolus timing.  Deconfounding
should remove these controller artifacts, yielding "physiological ISF".

Normalization pipeline (4 levels):
  1. Raw ISF — median demand_isf per patient
  2. Channel-deconfounded — adjust observed drop by channel-specific coefficients
  3. BG₀-deconfounded — additionally residualize ISF on starting BG
  4. Full multi-factor — OLS removing BG₀, dose, IOB, circadian, channels

Hypotheses:
  H1: Controller eta² decreases >50% after full deconfounding
  H2: >50% of patients have deconfounded ISF closer to profile ISF
  H3: Patient partial eta² increases (physiology signal enhanced)
  H4: Deconfounded ISF enables cross-controller ISF prediction

Author: Copilot + bewest
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

# ── Constants ──
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("visualizations/cross-controller")
OUT_JSON = RESULTS_DIR / "exp-2722_cross_controller_normalization.json"

HORIZON_STEPS = 24       # 2 hours at 5-min intervals
BG_FLOOR = 180
MIN_DOSE = 0.3
CARB_HISTORY_STEPS = 48 * 12  # 48 hours at 5-min intervals

# EXP-2698 validated channel coefficients
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5
MEAN_COEFF = (BOLUS_COEFF + SMB_COEFF + EXCESS_BASAL_COEFF) / 3.0  # ≈ -127.77

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

CTRL_ORDER = ["loop", "trio", "openaps"]
CTRL_COLORS = {"loop": "#2196F3", "trio": "#4CAF50", "openaps": "#FF9800"}

EXP_ID = "EXP-2722"
EXP_TITLE = "Cross-Controller ISF Normalization"


# ── Data Loading ──

def load_data():
    """Load grid + devicestatus, map controllers, filter to qualified patients."""
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    if not pd.api.types.is_datetime64_any_dtype(grid["time"]):
        grid["time"] = pd.to_datetime(grid["time"], utc=True)
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    if "carbs" in grid.columns:
        grid["carbs_48h"] = grid.groupby("patient_id")["carbs"].transform(
            lambda x: x.rolling(CARB_HISTORY_STEPS, min_periods=1).sum()
        )
    else:
        grid["carbs_48h"] = 0.0
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


# ── Event Extraction ──

def extract_events(grid):
    """Extract correction events: BG≥180, carbs<5g, dose≥0.3U, 2h horizon."""
    print("Extracting correction events...")
    h = HORIZON_STEPS
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
    has_carbs_48h = "carbs_48h" in grid.columns
    events = []

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < h + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        carbs = pg["carbs"].values if has_carbs else np.zeros(len(pg))
        carbs_48h = pg["carbs_48h"].values if has_carbs_48h else np.zeros(len(pg))
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" in pg.columns:
            profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        else:
            continue

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]
            if np.isnan(bg0) or np.isnan(bg_end):
                continue
            if bg0 < BG_FLOOR:
                continue

            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            carbs_2h = float(np.nansum(carbs[i:i + h]))

            if carbs_2h > 5.0:
                continue

            total_insulin = bolus_2h + smb_2h + excess_basal_2h
            if total_insulin < MIN_DOSE:
                continue

            observed_drop = bg0 - bg_end
            demand_isf = observed_drop / total_insulin
            if demand_isf <= 0:
                continue

            # Channel decomposition effects
            channel_effect = (bolus_2h * BOLUS_COEFF
                              + smb_2h * SMB_COEFF
                              + excess_basal_2h * EXCESS_BASAL_COEFF)

            # Channel-deconfounded drop: remove channel-specific effects,
            # replace with average-channel effect
            deconf_drop = observed_drop - channel_effect + total_insulin * MEAN_COEFF
            deconf_isf_channel = deconf_drop / total_insulin

            try:
                ts = pd.Timestamp(pg["time"].iloc[i])
                hour = ts.hour
            except Exception:
                hour = 0
            block_idx = min(hour // 4, 5)

            c48 = float(carbs_48h[i]) if not np.isnan(carbs_48h[i]) else 0.0

            events.append({
                "patient_id": pid,
                "controller": ctrl,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "demand_isf": demand_isf,
                "channel_effect": channel_effect,
                "deconf_drop": deconf_drop,
                "deconf_isf_channel": deconf_isf_channel,
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "carbs_48h": c48,
                "profile_isf": profile_isf,
            })

    df = pd.DataFrame(events)
    if len(df) == 0:
        return df

    # Glycogen state classification (median split per patient)
    for pid in df["patient_id"].unique():
        mask = df["patient_id"] == pid
        med = df.loc[mask, "carbs_48h"].median()
        df.loc[mask, "glycogen_state"] = np.where(
            df.loc[mask, "carbs_48h"] >= med, "loaded", "depleted"
        )

    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients")
    return df


# ── Normalization Pipeline ──

def compute_normalized_isfs(events):
    """Compute 4 levels of ISF normalization per patient.

    Returns dict[patient_id] → {raw, channel_deconf, bg_deconf, full_deconf, profile_isf, controller}
    """
    print("\nComputing normalized ISFs...")
    patient_isfs = {}

    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 10:
            continue

        ctrl = pg["controller"].iloc[0]
        prof_isf = pg["profile_isf"].iloc[0]

        # Level 1: Raw ISF
        raw_median = float(np.median(pg["demand_isf"].values))

        # Level 2: Channel-deconfounded ISF
        chan_median = float(np.median(pg["deconf_isf_channel"].values))

        # Level 3: BG₀-deconfounded ISF (residualize ISF on BG₀)
        isf_vals = pg["deconf_isf_channel"].values.copy()
        bg0_vals = pg["bg0"].values.copy()
        if np.std(bg0_vals) > 1e-6 and np.std(isf_vals) > 1e-6:
            X_bg = np.column_stack([bg0_vals, np.ones(len(bg0_vals))])
            beta, _, _, _ = lstsq(X_bg, isf_vals, rcond=None)
            resid = isf_vals - X_bg @ beta
            bg_deconf_vals = resid + np.median(isf_vals)
            bg_deconf_median = float(np.median(bg_deconf_vals))
        else:
            bg_deconf_vals = isf_vals
            bg_deconf_median = chan_median

        # Level 4: Full multi-factor deconfounded ISF
        y = pg["demand_isf"].values.copy()
        block_dummies = pd.get_dummies(pg["block_idx"], prefix="b").values
        bolus_total = pg["bolus_2h"].values + pg["smb_2h"].values + pg["excess_basal_2h"].values
        bolus_frac = np.where(bolus_total > 1e-6,
                              pg["bolus_2h"].values / bolus_total, 0.0)
        smb_frac = np.where(bolus_total > 1e-6,
                            pg["smb_2h"].values / bolus_total, 0.0)

        X_full = np.column_stack([
            pg["bg0"].values,
            pg["total_insulin"].values,
            pg["iob_start"].values,
            block_dummies,
            bolus_frac,
            smb_frac,
        ])
        X_full_int = np.column_stack([X_full, np.ones(len(X_full))])
        if X_full_int.shape[0] > X_full_int.shape[1] and np.std(y) > 1e-6:
            beta_full, _, _, _ = lstsq(X_full_int, y, rcond=None)
            resid_full = y - X_full_int @ beta_full
            full_deconf_vals = resid_full + np.median(y)
            full_deconf_median = float(np.median(full_deconf_vals))
        else:
            full_deconf_vals = y
            full_deconf_median = raw_median

        patient_isfs[pid] = {
            "raw_median": raw_median,
            "channel_deconf_median": chan_median,
            "bg_deconf_median": bg_deconf_median,
            "full_deconf_median": full_deconf_median,
            "profile_isf": prof_isf,
            "controller": ctrl,
            "n_events": int(len(pg)),
            # Keep per-event arrays for variance analysis
            "_raw_vals": pg["demand_isf"].values,
            "_chan_vals": pg["deconf_isf_channel"].values,
            "_bg_vals": bg_deconf_vals,
            "_full_vals": full_deconf_vals,
        }

    print(f"  {len(patient_isfs)} patients with normalized ISFs")
    return patient_isfs


# ── Hypothesis Tests ──

def _eta_squared_controller(patient_isfs, level_key):
    """Compute eta² for controller grouping at a given normalization level."""
    groups = {}
    for pid, p in patient_isfs.items():
        ct = p["controller"]
        if ct not in CTRL_ORDER:
            continue
        groups.setdefault(ct, []).append(p[level_key])

    active = {ct: v for ct, v in groups.items() if len(v) >= 2}
    if len(active) < 2:
        return 0.0, active

    all_vals = [v for ct in CTRL_ORDER for v in active.get(ct, [])]
    grand_mean = np.mean(all_vals)
    ss_total = sum((v - grand_mean) ** 2 for v in all_vals)
    if ss_total < 1e-12:
        return 0.0, active

    ss_between = sum(
        len(active[ct]) * (np.mean(active[ct]) - grand_mean) ** 2
        for ct in active
    )
    return float(ss_between / ss_total), active


def test_h1_controller_variance(patient_isfs):
    """H1: Controller eta² decreases >50% after full deconfounding."""
    print("\n── H1: Controller variance reduction ──")

    levels = [
        ("raw_median", "Raw ISF"),
        ("channel_deconf_median", "Channel-deconfounded"),
        ("bg_deconf_median", "BG₀-deconfounded"),
        ("full_deconf_median", "Fully deconfounded"),
    ]

    eta_results = {}
    for key, label in levels:
        eta, groups = _eta_squared_controller(patient_isfs, key)
        eta_results[key] = eta
        n_groups = len(groups)
        per_ctrl = {ct: f"{np.median(v):.1f}" for ct, v in groups.items()}
        print(f"  {label:28s}: η²={eta:.4f}  ({n_groups} groups) medians={per_ctrl}")

    # Kruskal-Wallis at each level (event-level not patient-level for raw)
    raw_eta = eta_results["raw_median"]
    full_eta = eta_results["full_deconf_median"]
    if raw_eta > 1e-6:
        reduction_pct = 100 * (raw_eta - full_eta) / raw_eta
    else:
        reduction_pct = 0.0

    verdict = bool(reduction_pct > 50)
    print(f"\n  Raw η²:  {raw_eta:.4f}")
    print(f"  Full η²: {full_eta:.4f}")
    print(f"  Reduction: {reduction_pct:.1f}%")
    print(f"  H1 verdict: {'PASS' if verdict else 'FAIL'} (need >50% reduction)")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "eta_raw": round(raw_eta, 4),
        "eta_channel_deconf": round(eta_results["channel_deconf_median"], 4),
        "eta_bg_deconf": round(eta_results["bg_deconf_median"], 4),
        "eta_full_deconf": round(full_eta, 4),
        "reduction_pct": round(reduction_pct, 1),
    }


def test_h2_profile_proximity(patient_isfs):
    """H2: >50% of patients have deconfounded ISF closer to profile ISF."""
    print("\n── H2: Proximity to profile ISF ──")

    closer_count = 0
    total = 0
    per_patient = []

    for pid, p in sorted(patient_isfs.items()):
        prof = p["profile_isf"]
        if prof <= 0 or np.isnan(prof):
            continue

        raw_dist = abs(p["raw_median"] - prof)
        full_dist = abs(p["full_deconf_median"] - prof)
        is_closer = bool(full_dist < raw_dist)

        per_patient.append({
            "patient_id": pid,
            "controller": p["controller"],
            "profile_isf": round(prof, 1),
            "raw_median": round(p["raw_median"], 1),
            "full_deconf_median": round(p["full_deconf_median"], 1),
            "raw_distance": round(raw_dist, 1),
            "full_distance": round(full_dist, 1),
            "closer_after": is_closer,
        })

        total += 1
        if is_closer:
            closer_count += 1

    pct_closer = 100 * closer_count / max(total, 1)
    verdict = bool(pct_closer > 50)

    print(f"  Patients closer after deconfounding: {closer_count}/{total} ({pct_closer:.0f}%)")
    print(f"  H2 verdict: {'PASS' if verdict else 'FAIL'} (need >50%)")

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "n_closer": closer_count,
        "n_total": total,
        "pct_closer": round(pct_closer, 1),
        "per_patient": per_patient,
    }


def test_h3_patient_signal(events, patient_isfs):
    """H3: Patient partial eta² increases after deconfounding (physiology signal enhanced)."""
    print("\n── H3: Patient physiology signal ──")

    # Build event-level arrays for patients with known controllers
    ev = events[events["controller"].isin(CTRL_ORDER)].copy()
    if len(ev) < 100:
        return {"h3_verdict": "SKIP", "reason": "insufficient events in known controllers"}

    y_raw = ev["demand_isf"].values
    y_deconf = ev["deconf_isf_channel"].values

    # Patient dummies
    pat_dummies = pd.get_dummies(ev["patient_id"], prefix="p").values
    ctrl_dummies = pd.get_dummies(ev["controller"], prefix="c").values

    ss_tot_raw = np.sum((y_raw - y_raw.mean()) ** 2)
    ss_tot_deconf = np.sum((y_deconf - y_deconf.mean()) ** 2)

    if ss_tot_raw < 1e-12 or ss_tot_deconf < 1e-12:
        return {"h3_verdict": "SKIP", "reason": "no variance"}

    def partial_eta2(y, X_target, X_control, ss_tot):
        """Compute partial eta² for X_target controlling for X_control."""
        # Full model: y ~ X_target + X_control
        X_full = np.column_stack([X_target, X_control, np.ones(len(y))])
        beta_full, _, _, _ = lstsq(X_full, y, rcond=None)
        ss_res_full = np.sum((y - X_full @ beta_full) ** 2)

        # Reduced model: y ~ X_control only
        X_reduced = np.column_stack([X_control, np.ones(len(y))])
        beta_red, _, _, _ = lstsq(X_reduced, y, rcond=None)
        ss_res_reduced = np.sum((y - X_reduced @ beta_red) ** 2)

        # Partial eta² = (SS_reduced - SS_full) / SS_reduced
        if ss_res_reduced < 1e-12:
            return 0.0
        return float((ss_res_reduced - ss_res_full) / ss_res_reduced)

    # Patient partial eta² controlling for controller — raw ISF
    raw_patient_eta = partial_eta2(y_raw, pat_dummies, ctrl_dummies, ss_tot_raw)
    # Patient partial eta² controlling for controller — channel-deconfounded ISF
    deconf_patient_eta = partial_eta2(y_deconf, pat_dummies, ctrl_dummies, ss_tot_deconf)

    # Controller partial eta² controlling for patient
    raw_ctrl_eta = partial_eta2(y_raw, ctrl_dummies, pat_dummies, ss_tot_raw)
    deconf_ctrl_eta = partial_eta2(y_deconf, ctrl_dummies, pat_dummies, ss_tot_deconf)

    patient_increased = bool(deconf_patient_eta > raw_patient_eta)

    print(f"  Raw ISF:")
    print(f"    Patient partial η²:     {raw_patient_eta:.4f}")
    print(f"    Controller partial η²:  {raw_ctrl_eta:.4f}")
    print(f"  Channel-deconfounded ISF:")
    print(f"    Patient partial η²:     {deconf_patient_eta:.4f}")
    print(f"    Controller partial η²:  {deconf_ctrl_eta:.4f}")
    print(f"  Patient signal {'increased' if patient_increased else 'decreased'}")
    print(f"  H3 verdict: {'PASS' if patient_increased else 'FAIL'}")

    return {
        "h3_verdict": "PASS" if patient_increased else "FAIL",
        "raw_patient_partial_eta2": round(raw_patient_eta, 4),
        "raw_ctrl_partial_eta2": round(raw_ctrl_eta, 4),
        "deconf_patient_partial_eta2": round(deconf_patient_eta, 4),
        "deconf_ctrl_partial_eta2": round(deconf_ctrl_eta, 4),
        "patient_signal_increased": patient_increased,
    }


def test_h4_cross_controller_prediction(events, patient_isfs):
    """H4: Deconfounded ISF enables cross-controller ISF prediction.

    Strategy: leave-one-controller-out. For each controller C:
      - Train channel-mix model on events from OTHER controllers
      - Predict each patient in C's deconfounded ISF from their channel mix
      - Check if predicted ISF falls within observed range of C patients
    """
    print("\n── H4: Cross-controller prediction ──")

    ev = events[events["controller"].isin(CTRL_ORDER)].copy()
    if len(ev) < 100:
        return {"h4_verdict": "SKIP", "reason": "insufficient events"}

    # Build per-patient summary for prediction
    summaries = []
    for pid, p in patient_isfs.items():
        if p["controller"] not in CTRL_ORDER:
            continue
        pg = ev[ev["patient_id"] == pid]
        if len(pg) < 10:
            continue

        total = pg["bolus_2h"].values + pg["smb_2h"].values + pg["excess_basal_2h"].values
        safe_total = np.where(total > 1e-6, total, 1.0)
        summaries.append({
            "patient_id": pid,
            "controller": p["controller"],
            "full_deconf_median": p["full_deconf_median"],
            "raw_median": p["raw_median"],
            "bolus_frac": float(np.mean(pg["bolus_2h"].values / safe_total)),
            "smb_frac": float(np.mean(pg["smb_2h"].values / safe_total)),
            "basal_frac": float(np.mean(pg["excess_basal_2h"].values / safe_total)),
            "mean_bg0": float(pg["bg0"].mean()),
            "mean_dose": float(pg["total_insulin"].mean()),
        })

    if len(summaries) < 6:
        return {"h4_verdict": "SKIP", "reason": "too few patient summaries"}

    sum_df = pd.DataFrame(summaries)
    predictions = []
    n_in_range = 0
    n_total = 0

    for held_out_ctrl in CTRL_ORDER:
        test_mask = sum_df["controller"] == held_out_ctrl
        train_mask = ~test_mask
        if test_mask.sum() < 1 or train_mask.sum() < 3:
            continue

        train = sum_df[train_mask]
        test = sum_df[test_mask]

        # Train: predict full_deconf_median from channel mix + BG + dose
        y_train = train["full_deconf_median"].values
        X_train = np.column_stack([
            train["bolus_frac"].values,
            train["smb_frac"].values,
            train["mean_bg0"].values,
            train["mean_dose"].values,
            np.ones(len(train)),
        ])

        if np.std(y_train) < 1e-6:
            continue

        beta, _, _, _ = lstsq(X_train, y_train, rcond=None)

        # Predict on held-out controller
        X_test = np.column_stack([
            test["bolus_frac"].values,
            test["smb_frac"].values,
            test["mean_bg0"].values,
            test["mean_dose"].values,
            np.ones(len(test)),
        ])
        y_pred = X_test @ beta

        # Check if predictions fall within observed range of held-out controller
        actual_vals = test["full_deconf_median"].values
        obs_lo = float(np.percentile(actual_vals, 10)) if len(actual_vals) > 2 else float(np.min(actual_vals))
        obs_hi = float(np.percentile(actual_vals, 90)) if len(actual_vals) > 2 else float(np.max(actual_vals))

        for i in range(len(test)):
            pred_val = float(y_pred[i])
            actual_val = float(actual_vals[i])
            in_range = bool(obs_lo <= pred_val <= obs_hi)
            n_total += 1
            if in_range:
                n_in_range += 1

            predictions.append({
                "patient_id": test.iloc[i]["patient_id"],
                "held_out_ctrl": held_out_ctrl,
                "predicted_isf": round(pred_val, 1),
                "actual_isf": round(actual_val, 1),
                "obs_range": [round(obs_lo, 1), round(obs_hi, 1)],
                "in_range": in_range,
            })

        print(f"  {held_out_ctrl}: {len(test)} patients, "
              f"range=[{obs_lo:.1f}, {obs_hi:.1f}]")

    pct_in_range = 100 * n_in_range / max(n_total, 1)
    verdict = bool(pct_in_range > 50)

    print(f"  Predictions in range: {n_in_range}/{n_total} ({pct_in_range:.0f}%)")
    print(f"  H4 verdict: {'PASS' if verdict else 'FAIL'} (need >50% in range)")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "n_in_range": n_in_range,
        "n_total": n_total,
        "pct_in_range": round(pct_in_range, 1),
        "predictions": predictions,
    }


# ── Visualization ──

def make_visualization(events, patient_isfs, h1, h2, h3, h4):
    """Create 2×2 figure summarizing cross-controller normalization."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available, skipping visualization")
        return

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    # ── Panel 1: Grouped boxplot — ISF by controller at each normalization level ──
    ax = axes[0, 0]
    levels = ["raw_median", "channel_deconf_median", "bg_deconf_median", "full_deconf_median"]
    level_labels = ["Raw", "Channel\nDeconf", "BG₀\nDeconf", "Full\nDeconf"]
    n_levels = len(levels)
    n_ctrls = len(CTRL_ORDER)
    width = 0.25
    positions_base = np.arange(n_levels)

    for ci, ct in enumerate(CTRL_ORDER):
        vals_per_level = []
        for lev in levels:
            patient_vals = [p[lev] for p in patient_isfs.values()
                           if p["controller"] == ct and not np.isnan(p[lev])]
            vals_per_level.append(patient_vals if patient_vals else [0])

        pos = positions_base + (ci - 1) * width
        bp = ax.boxplot(vals_per_level, positions=pos, widths=width * 0.8,
                        patch_artist=True, showfliers=False)
        for patch in bp["boxes"]:
            patch.set_facecolor(CTRL_COLORS[ct])
            patch.set_alpha(0.7)
        for median_line in bp["medians"]:
            median_line.set_color("black")

    ax.set_xticks(positions_base)
    ax.set_xticklabels(level_labels, fontsize=9)
    ax.set_ylabel("ISF (mg/dL/U)")
    ax.set_title(f"ISF by Controller × Normalization Level")
    ax.legend(
        [plt.Rectangle((0, 0), 1, 1, fc=CTRL_COLORS[ct], alpha=0.7) for ct in CTRL_ORDER],
        [ct.upper() for ct in CTRL_ORDER], loc="upper right", fontsize=8
    )
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 2: Scatter — raw ISF vs deconfounded ISF, colored by controller ──
    ax = axes[0, 1]
    for pid, p in patient_isfs.items():
        ct = p["controller"]
        color = CTRL_COLORS.get(ct, "gray")
        ax.scatter(p["raw_median"], p["full_deconf_median"],
                   c=color, s=80, edgecolors="k", lw=0.5, zorder=3)
        label_txt = pid[-4:] if len(pid) > 4 else pid
        ax.annotate(label_txt, (p["raw_median"], p["full_deconf_median"]),
                    fontsize=5, xytext=(3, 3), textcoords="offset points")

    all_raw = [p["raw_median"] for p in patient_isfs.values()]
    all_deconf = [p["full_deconf_median"] for p in patient_isfs.values()]
    lo = min(min(all_raw), min(all_deconf)) * 0.9
    hi = max(max(all_raw), max(all_deconf)) * 1.1
    ax.plot([lo, hi], [lo, hi], "k--", alpha=0.3, label="1:1 line")
    ax.set_xlabel("Raw median ISF (mg/dL/U)")
    ax.set_ylabel("Fully deconfounded median ISF (mg/dL/U)")
    ax.set_title("Raw vs Deconfounded ISF per Patient")
    ax.legend(
        [plt.Rectangle((0, 0), 1, 1, fc=CTRL_COLORS[ct], alpha=0.7) for ct in CTRL_ORDER]
        + [plt.Line2D([0], [0], ls="--", c="k")],
        [ct.upper() for ct in CTRL_ORDER] + ["1:1"],
        loc="upper left", fontsize=8
    )
    ax.grid(alpha=0.3)

    # ── Panel 3: Bar chart — eta² at each deconfounding level ──
    ax = axes[1, 0]
    eta_labels = ["Raw", "Channel", "BG₀", "Full"]
    eta_vals = [
        h1.get("eta_raw", 0),
        h1.get("eta_channel_deconf", 0),
        h1.get("eta_bg_deconf", 0),
        h1.get("eta_full_deconf", 0),
    ]
    bar_colors = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71"]
    bars = ax.bar(eta_labels, eta_vals, color=bar_colors, alpha=0.8, edgecolor="k")
    for bar_item, val in zip(bars, eta_vals):
        ax.text(bar_item.get_x() + bar_item.get_width() / 2, val + 0.005,
                f"{val:.3f}", ha="center", fontsize=10)
    ax.set_ylabel("η² (controller)")
    ax.set_title(f"Controller η² by Normalization Level [{h1['h1_verdict']}]")
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 4: Heatmap — per-patient deconfounded ISF × controller ──
    ax = axes[1, 1]
    heatmap_data = []
    heatmap_labels = []
    heatmap_ctrls = []
    for pid in sorted(patient_isfs.keys()):
        p = patient_isfs[pid]
        if p["controller"] not in CTRL_ORDER:
            continue
        heatmap_data.append([
            p["raw_median"],
            p["channel_deconf_median"],
            p["bg_deconf_median"],
            p["full_deconf_median"],
        ])
        label_txt = pid[-6:] if len(pid) > 6 else pid
        heatmap_labels.append(f"{label_txt}\n({p['controller'][:1].upper()})")
        heatmap_ctrls.append(p["controller"])

    if heatmap_data:
        hm = np.array(heatmap_data)
        # Sort by controller then by full deconf ISF
        sort_key = [(CTRL_ORDER.index(c) if c in CTRL_ORDER else 99, heatmap_data[i][3])
                    for i, c in enumerate(heatmap_ctrls)]
        sort_idx = sorted(range(len(sort_key)), key=lambda k: sort_key[k])
        hm = hm[sort_idx]
        heatmap_labels = [heatmap_labels[i] for i in sort_idx]

        im = ax.imshow(hm.T, aspect="auto", cmap="RdYlGn_r", interpolation="nearest")
        ax.set_xticks(range(len(heatmap_labels)))
        ax.set_xticklabels(heatmap_labels, rotation=90, fontsize=6)
        ax.set_yticks(range(4))
        ax.set_yticklabels(["Raw", "Chan", "BG₀", "Full"], fontsize=9)
        plt.colorbar(im, ax=ax, label="ISF (mg/dL/U)", shrink=0.8)
    ax.set_title("Per-Patient ISF Convergence Heatmap")

    plt.tight_layout()
    out_path = VIZ_DIR / "cross_controller_norm.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"  Visualization: {out_path}")


# ── Main ──

def main():
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid = load_data()
    events = extract_events(grid)
    if len(events) < 100:
        print("ERROR: Too few events for analysis")
        sys.exit(1)

    patient_isfs = compute_normalized_isfs(events)

    h1 = test_h1_controller_variance(patient_isfs)
    h2 = test_h2_profile_proximity(patient_isfs)
    h3 = test_h3_patient_signal(events, patient_isfs)
    h4 = test_h4_cross_controller_prediction(events, patient_isfs)

    make_visualization(events, patient_isfs, h1, h2, h3, h4)

    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "normalization_levels": {
            "raw": "median demand_isf per patient",
            "channel_deconf": "channel-effect adjusted ISF",
            "bg_deconf": "additionally residualized on BG₀",
            "full_deconf": "OLS removing BG₀, dose, IOB, circadian, channels",
        },
        "channel_coefficients": {
            "bolus": BOLUS_COEFF,
            "smb": SMB_COEFF,
            "excess_basal": EXCESS_BASAL_COEFF,
            "mean": round(MEAN_COEFF, 2),
        },
        "per_patient": {
            pid: {k: v for k, v in p.items() if not k.startswith("_")}
            for pid, p in patient_isfs.items()
        },
        "hypotheses": {
            "H1_controller_variance": h1,
            "H2_profile_proximity": h2,
            "H3_patient_signal": h3,
            "H4_cross_controller_prediction": h4,
        },
        "verdict_summary": {
            "H1": h1["h1_verdict"],
            "H2": h2["h2_verdict"],
            "H3": h3["h3_verdict"],
            "H4": h4["h4_verdict"],
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults: {OUT_JSON}")
    print(f"\nVerdict: H1={h1['h1_verdict']} H2={h2['h2_verdict']} "
          f"H3={h3['h3_verdict']} H4={h4['h4_verdict']}")
    return results


if __name__ == "__main__":
    main()
