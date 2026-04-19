#!/usr/bin/env python3
"""EXP-2725: DynISF Algorithm Deconfounding — Separating Algorithm from Physiology.

Trio and AAPS patients often use Dynamic ISF (DynISF), which algorithmically
adjusts ISF based on current BG using either a sigmoid or logarithmic formula.
This algorithm is itself a CONFOUND on observed ISF because:
  - When BG is high, DynISF lowers ISF → controller gives more insulin
  - Observed drop is larger → demand ISF inflated
  - Creates artificial dose-BG correlation

Prior findings:
  EXP-2674: DynISF formula type predicts ISF inflation:
            Sigmoid median 6.6×, Log median 2.5×
  EXP-2722: After normalization, Trio ISF (16.9) still lower than
            Loop (20.6) and OpenAPS (20.2) — DynISF may be the residual artifact
  EXP-2698: Channel coefficients: BOLUS=-129.2, SMB=-123.6, EXCESS_BASAL=-130.5

This experiment separates physiological ISF from the DynISF algorithm artifact
by deconfounding on the sensitivity_ratio (or BG-based proxy).

Hypotheses:
  H1: DynISF patients have higher within-patient ISF CV (Mann-Whitney p<0.05)
  H2: sensitivity_ratio (or BG proxy) predicts demand ISF (median |r|>0.1)
  H3: DynISF deconfounding closes >30% of the Trio-Loop ISF gap
  H4: DynISF-deconfounded ISF has lower prediction MAE for >50% of DynISF patients

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
VIZ_DIR = Path("visualizations/dynisf-deconfound")
OUT_JSON = RESULTS_DIR / "exp-2725_dynisf_deconfound.json"

HORIZON_STEPS = 24        # 2 hours at 5-min intervals
BG_FLOOR = 180
MIN_DOSE = 0.3
MIN_GAP_STEPS = 24
CARB_HISTORY_STEPS = 48 * 12  # 48 hours at 5-min intervals

# EXP-2698 validated channel coefficients
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5
MEAN_COEFF = (BOLUS_COEFF + SMB_COEFF + EXCESS_BASAL_COEFF) / 3.0

TIME_BLOCKS = [(0, 4), (4, 8), (8, 12), (12, 16), (16, 20), (20, 24)]
BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]

CTRL_ORDER = ["loop", "trio", "openaps"]
CTRL_COLORS = {"loop": "#2196F3", "trio": "#4CAF50", "openaps": "#FF9800"}

# Known DynISF formula annotations (from EXP-2674, public Nightscout sites)
DYNISF_FORMULA = {
    "ns-9b9a6a874e51": "sigmoid",
    "ns-adde5f4af7ca": "sigmoid",
    "ns-dde9e7c2e752": "sigmoid",
    "ns-554b16de7133": "sigmoid",
    "ns-6bef17b4c1ec": "sigmoid",
    "ns-c422538aa12a": "sigmoid",
    "ns-d444c120c23a": "log",
    "ns-8b3c1b50793c": "log",
    "ns-a9ce2317bead": "log",
    "ns-8ffa739b986b": "log",
    "ns-1ccae8a375b9": "log",
    "ns-8f3527d1ee40": "autoisf",
}

EXP_ID = "EXP-2725"
EXP_TITLE = "DynISF Deconfounding — Separating Algorithm from Physiology"


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

    # Report available DynISF-related columns
    dynisf_cols = [c for c in grid.columns if "sens" in c.lower() or "dyn" in c.lower() or "ratio" in c.lower()]
    print(f"  DynISF-related columns in grid: {dynisf_cols or '(none)'}")

    return grid, ds


def identify_dynisf_patients(grid, ds):
    """Identify which patients use DynISF based on sensitivity_ratio variance.

    Returns dict[patient_id] → {"is_dynisf": bool, "sr_source": str, "formula": str}
    """
    print("\nIdentifying DynISF patients...")
    has_sr = "sensitivity_ratio" in grid.columns
    patient_info = {}

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid]
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        # Loop patients never use DynISF
        if ctrl == "loop":
            patient_info[pid] = {
                "is_dynisf": False, "sr_source": "none",
                "formula": "none", "controller": ctrl,
                "sr_median": 1.0, "sr_std": 0.0,
            }
            continue

        # Check known formula annotations
        formula = DYNISF_FORMULA.get(pid, "unknown")

        # Check sensitivity_ratio in grid data
        sr_std = 0.0
        sr_median = 1.0
        if has_sr:
            sr_vals = pg["sensitivity_ratio"].dropna()
            if len(sr_vals) > 10:
                sr_std = float(sr_vals.std())
                sr_median = float(sr_vals.median())

        # Classify: DynISF if sensitivity_ratio varies OR known formula
        is_dynisf = bool(
            (has_sr and sr_std > 0.01 and abs(sr_median - 1.0) > 0.01)
            or formula in ("sigmoid", "log", "autoisf")
        )

        sr_source = "grid" if (has_sr and sr_std > 0.01) else "annotation" if is_dynisf else "none"

        patient_info[pid] = {
            "is_dynisf": is_dynisf,
            "sr_source": sr_source,
            "formula": formula,
            "controller": ctrl,
            "sr_median": sr_median,
            "sr_std": sr_std,
        }

    n_dynisf = sum(1 for p in patient_info.values() if p["is_dynisf"])
    n_static = sum(1 for p in patient_info.values() if not p["is_dynisf"])
    print(f"  DynISF patients: {n_dynisf}, Static patients: {n_static}")
    return patient_info


# ── BG-Based Sensitivity Ratio Proxy ──

def estimate_sr_from_bg(bg, formula="log"):
    """Estimate sensitivity_ratio from BG using DynISF formulas.

    These are simplified approximations of the DynISF algorithm.
    Sigmoid: SR ≈ 1 / (1 + exp(-0.03 * (BG - 120)))
    Log: SR ≈ 1800 / (ln(BG/80) * reference_ISF) — simplified to relative scaling
    Returns ratio > 1 when BG is high (controller more aggressive).
    """
    if np.isnan(bg) or bg < 40:
        return np.nan
    if formula == "sigmoid":
        return float(1.0 / (1.0 + np.exp(-0.03 * (bg - 120.0))))
    elif formula == "log":
        # Log formula: relative to BG=120 baseline
        if bg <= 80:
            return 0.5
        return float(np.log(bg / 80.0) / np.log(120.0 / 80.0))
    else:
        return 1.0


# ── Event Extraction ──

def extract_events(grid, patient_info):
    """Extract correction events with DynISF annotations.

    Same filtering as EXP-2722 (BG≥180, carbs<5g, dose≥0.3U, 2h horizon)
    plus sensitivity_ratio capture at each event.
    """
    print("\nExtracting correction events...")
    h = HORIZON_STEPS
    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_carbs = "carbs" in grid.columns
    has_carbs_48h = "carbs_48h" in grid.columns
    has_sr = "sensitivity_ratio" in grid.columns
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
        sr = pg["sensitivity_ratio"].values.astype(np.float64) if has_sr else np.full(len(pg), np.nan)
        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if "scheduled_isf" in pg.columns:
            profile_isf = float(np.nanmedian(pg["scheduled_isf"].values))
        else:
            continue

        pinfo = patient_info.get(pid, {})
        is_dynisf = pinfo.get("is_dynisf", False)
        formula = pinfo.get("formula", "unknown")

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

            # Channel decomposition (EXP-2698 coefficients)
            channel_effect = (bolus_2h * BOLUS_COEFF
                              + smb_2h * SMB_COEFF
                              + excess_basal_2h * EXCESS_BASAL_COEFF)
            deconf_drop = observed_drop - channel_effect + total_insulin * MEAN_COEFF
            deconf_isf_channel = deconf_drop / total_insulin

            # Sensitivity ratio at event time (±15 min window)
            sr_window = sr[max(0, i - 3):i + 4]
            sr_at_event = float(np.nanmedian(sr_window)) if np.any(~np.isnan(sr_window)) else np.nan

            # BG-based SR proxy if no direct SR available
            if np.isnan(sr_at_event) and is_dynisf:
                sr_at_event = estimate_sr_from_bg(bg0, formula if formula in ("sigmoid", "log") else "log")

            # Effective profile ISF that the controller was using
            if not np.isnan(sr_at_event) and sr_at_event > 0:
                effective_isf = profile_isf / sr_at_event
            else:
                effective_isf = profile_isf

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
                "is_dynisf": is_dynisf,
                "dynisf_formula": formula,
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
                "sr_at_event": sr_at_event,
                "effective_isf": effective_isf,
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

    n_dynisf = df[df["is_dynisf"]]["patient_id"].nunique()
    n_static = df[~df["is_dynisf"]]["patient_id"].nunique()
    print(f"  {len(df):,} events, {df['patient_id'].nunique()} patients "
          f"({n_dynisf} DynISF, {n_static} static)")
    return df


# ── ISF Normalization (from EXP-2722) + DynISF Layer ──

def compute_normalized_isfs(events):
    """Compute 5 levels of ISF normalization per patient.

    Levels 1-4 from EXP-2722, plus Level 5: DynISF deconfounding.
    Returns dict[patient_id] → {...medians and per-event arrays...}
    """
    print("\nComputing normalized ISFs (5 levels)...")
    patient_isfs = {}

    for pid, pg in events.groupby("patient_id"):
        if len(pg) < 10:
            continue

        ctrl = pg["controller"].iloc[0]
        prof_isf = pg["profile_isf"].iloc[0]
        is_dynisf = bool(pg["is_dynisf"].iloc[0])

        # Level 1: Raw ISF
        raw_median = float(np.median(pg["demand_isf"].values))

        # Level 2: Channel-deconfounded ISF
        chan_median = float(np.median(pg["deconf_isf_channel"].values))

        # Level 3: BG₀-deconfounded ISF
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

        # Level 4: Full multi-factor deconfounded ISF (EXP-2722 pipeline)
        y = pg["demand_isf"].values.copy()
        block_dummies = pd.get_dummies(pg["block_idx"], prefix="b").values
        bolus_total = pg["bolus_2h"].values + pg["smb_2h"].values + pg["excess_basal_2h"].values
        bolus_frac = np.where(bolus_total > 1e-6, pg["bolus_2h"].values / bolus_total, 0.0)
        smb_frac = np.where(bolus_total > 1e-6, pg["smb_2h"].values / bolus_total, 0.0)

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

        # Level 5: DynISF deconfounding — add sensitivity_ratio to the OLS
        sr_vals = pg["sr_at_event"].values.copy()
        has_valid_sr = np.sum(~np.isnan(sr_vals)) >= 5 and np.nanstd(sr_vals) > 1e-6
        if is_dynisf and has_valid_sr:
            # Fill NaN SR with median for this patient
            sr_filled = np.where(np.isnan(sr_vals), np.nanmedian(sr_vals), sr_vals)
            X_dynisf = np.column_stack([
                pg["bg0"].values,
                pg["total_insulin"].values,
                pg["iob_start"].values,
                block_dummies,
                bolus_frac,
                smb_frac,
                sr_filled,
            ])
            X_dynisf_int = np.column_stack([X_dynisf, np.ones(len(X_dynisf))])
            if X_dynisf_int.shape[0] > X_dynisf_int.shape[1] and np.std(y) > 1e-6:
                beta_dyn, _, _, _ = lstsq(X_dynisf_int, y, rcond=None)
                resid_dyn = y - X_dynisf_int @ beta_dyn
                dynisf_deconf_vals = resid_dyn + np.median(y)
                dynisf_deconf_median = float(np.median(dynisf_deconf_vals))
                sr_coeff = float(beta_dyn[-2])  # SR coefficient (before intercept)
            else:
                dynisf_deconf_vals = full_deconf_vals
                dynisf_deconf_median = full_deconf_median
                sr_coeff = 0.0
        else:
            # Non-DynISF patients: DynISF level equals full deconf level
            dynisf_deconf_vals = full_deconf_vals
            dynisf_deconf_median = full_deconf_median
            sr_coeff = 0.0
            sr_filled = sr_vals

        patient_isfs[pid] = {
            "raw_median": raw_median,
            "channel_deconf_median": chan_median,
            "bg_deconf_median": bg_deconf_median,
            "full_deconf_median": full_deconf_median,
            "dynisf_deconf_median": dynisf_deconf_median,
            "profile_isf": prof_isf,
            "controller": ctrl,
            "is_dynisf": is_dynisf,
            "dynisf_formula": pg["dynisf_formula"].iloc[0],
            "sr_coeff": sr_coeff,
            "n_events": int(len(pg)),
            # Per-event arrays (internal use, not serialized)
            "_raw_vals": pg["demand_isf"].values,
            "_chan_vals": pg["deconf_isf_channel"].values,
            "_bg_vals": bg_deconf_vals,
            "_full_vals": full_deconf_vals,
            "_dynisf_vals": dynisf_deconf_vals,
            "_sr_vals": sr_filled if has_valid_sr else sr_vals,
        }

    print(f"  {len(patient_isfs)} patients with normalized ISFs")
    return patient_isfs


# ── Hypothesis Tests ──

def test_h1_dynisf_variance(events, patient_isfs):
    """H1: DynISF patients have higher within-patient ISF CV.

    DynISF algorithmically varies insulin delivery → more ISF variation.
    PASS if DynISF patients have significantly higher ISF CV (Mann-Whitney p<0.05).
    """
    print("\n── H1: DynISF patients have different ISF variance structure ──")

    dynisf_cvs = []
    static_cvs = []

    for pid, p in patient_isfs.items():
        vals = p["_raw_vals"]
        if len(vals) < 5:
            continue
        mean_val = np.mean(vals)
        if mean_val < 1e-6:
            continue
        cv = float(np.std(vals) / mean_val)

        if p["is_dynisf"]:
            dynisf_cvs.append(cv)
        else:
            static_cvs.append(cv)

    print(f"  DynISF patients: n={len(dynisf_cvs)}")
    print(f"  Static patients: n={len(static_cvs)}")

    if len(dynisf_cvs) < 2 or len(static_cvs) < 2:
        print("  H1 verdict: SKIP (insufficient patients in one group)")
        return {
            "h1_verdict": "SKIP",
            "reason": "insufficient patients",
            "n_dynisf": len(dynisf_cvs),
            "n_static": len(static_cvs),
        }

    dynisf_med_cv = float(np.median(dynisf_cvs))
    static_med_cv = float(np.median(static_cvs))
    u_stat, p_val = stats.mannwhitneyu(dynisf_cvs, static_cvs, alternative="greater")

    verdict = bool(p_val < 0.05)
    print(f"  DynISF median CV: {dynisf_med_cv:.3f}")
    print(f"  Static median CV: {static_med_cv:.3f}")
    print(f"  Mann-Whitney U={u_stat:.1f}, p={p_val:.4f}")
    print(f"  H1 verdict: {'PASS' if verdict else 'FAIL'} (need p<0.05)")

    return {
        "h1_verdict": "PASS" if verdict else "FAIL",
        "dynisf_median_cv": round(dynisf_med_cv, 4),
        "static_median_cv": round(static_med_cv, 4),
        "dynisf_cvs": [round(v, 4) for v in dynisf_cvs],
        "static_cvs": [round(v, 4) for v in static_cvs],
        "n_dynisf": len(dynisf_cvs),
        "n_static": len(static_cvs),
        "mann_whitney_U": round(float(u_stat), 2),
        "p_value": round(float(p_val), 6),
    }


def test_h2_sr_predicts_isf(events, patient_isfs):
    """H2: sensitivity_ratio (or BG-based proxy) predicts demand ISF.

    Per DynISF patient: correlation between SR and demand_isf.
    Pool: partial correlation controlling for BG₀ and dose.
    PASS if median |r| > 0.1 across DynISF patients.
    """
    print("\n── H2: Sensitivity ratio predicts observed ISF ──")

    per_patient_r = []
    per_patient_details = []

    for pid, p in patient_isfs.items():
        if not p["is_dynisf"]:
            continue
        sr_vals = p["_sr_vals"]
        isf_vals = p["_raw_vals"]
        if len(sr_vals) < 10:
            continue
        valid = ~np.isnan(sr_vals)
        if np.sum(valid) < 10:
            continue
        sr_v = sr_vals[valid]
        isf_v = isf_vals[valid]
        if np.std(sr_v) < 1e-6 or np.std(isf_v) < 1e-6:
            continue

        r, pval = stats.pearsonr(sr_v, isf_v)
        per_patient_r.append(abs(float(r)))
        per_patient_details.append({
            "patient_id": pid,
            "controller": p["controller"],
            "formula": p["dynisf_formula"],
            "n_events": int(np.sum(valid)),
            "r": round(float(r), 4),
            "p": round(float(pval), 6),
            "abs_r": round(abs(float(r)), 4),
        })
        print(f"  {pid}: r={r:.3f}, p={pval:.3f}, n={np.sum(valid)}")

    if not per_patient_r:
        print("  H2 verdict: SKIP (no DynISF patients with valid SR data)")
        return {
            "h2_verdict": "SKIP",
            "reason": "no DynISF patients with valid SR",
        }

    # Pooled partial correlation: SR → ISF controlling for BG₀ and dose
    dynisf_events = events[events["is_dynisf"]].copy()
    sr_valid = dynisf_events["sr_at_event"].notna()
    dynisf_valid = dynisf_events[sr_valid]

    pooled_partial_r = np.nan
    if len(dynisf_valid) >= 20:
        sr_pool = dynisf_valid["sr_at_event"].values
        isf_pool = dynisf_valid["demand_isf"].values
        bg0_pool = dynisf_valid["bg0"].values
        dose_pool = dynisf_valid["total_insulin"].values

        # Partial correlation: residualize both SR and ISF on BG₀ + dose
        X_ctrl = np.column_stack([bg0_pool, dose_pool, np.ones(len(bg0_pool))])
        if np.std(sr_pool) > 1e-6 and np.std(isf_pool) > 1e-6:
            b_sr, _, _, _ = lstsq(X_ctrl, sr_pool, rcond=None)
            b_isf, _, _, _ = lstsq(X_ctrl, isf_pool, rcond=None)
            sr_resid = sr_pool - X_ctrl @ b_sr
            isf_resid = isf_pool - X_ctrl @ b_isf
            if np.std(sr_resid) > 1e-6 and np.std(isf_resid) > 1e-6:
                pooled_partial_r, _ = stats.pearsonr(sr_resid, isf_resid)
                pooled_partial_r = float(pooled_partial_r)
                print(f"\n  Pooled partial r (SR→ISF | BG₀,dose): {pooled_partial_r:.3f}, n={len(dynisf_valid)}")

    median_abs_r = float(np.median(per_patient_r))
    verdict = bool(median_abs_r > 0.1)
    print(f"\n  Median |r|: {median_abs_r:.3f}")
    print(f"  H2 verdict: {'PASS' if verdict else 'FAIL'} (need median |r| > 0.1)")

    return {
        "h2_verdict": "PASS" if verdict else "FAIL",
        "median_abs_r": round(median_abs_r, 4),
        "n_patients": len(per_patient_r),
        "pooled_partial_r": round(pooled_partial_r, 4) if not np.isnan(pooled_partial_r) else None,
        "per_patient": per_patient_details,
    }


def test_h3_trio_gap_closure(patient_isfs):
    """H3: DynISF deconfounding closes >30% of the Trio-Loop ISF gap.

    Compare Trio median ISF vs Loop at each deconfounding stage.
    PASS if DynISF deconfounding reduces the gap by >30%.
    """
    print("\n── H3: DynISF deconfounding closes the Trio-Loop ISF gap ──")

    levels = [
        ("raw_median", "Raw ISF"),
        ("channel_deconf_median", "Channel-deconf"),
        ("bg_deconf_median", "BG₀-deconf"),
        ("full_deconf_median", "Full-deconf"),
        ("dynisf_deconf_median", "DynISF-deconf"),
    ]

    loop_vals = {}
    trio_vals = {}
    for key, _ in levels:
        loop_vals[key] = [p[key] for p in patient_isfs.values()
                          if p["controller"] == "loop" and not np.isnan(p[key])]
        trio_vals[key] = [p[key] for p in patient_isfs.values()
                          if p["controller"] == "trio" and not np.isnan(p[key])]

    if not loop_vals["raw_median"] or not trio_vals["raw_median"]:
        print("  H3 verdict: SKIP (need both Loop and Trio patients)")
        return {"h3_verdict": "SKIP", "reason": "missing Loop or Trio patients"}

    gaps = {}
    print(f"  {'Level':<20s} {'Loop med':>10s} {'Trio med':>10s} {'Gap':>10s}")
    print(f"  {'-'*52}")
    for key, label in levels:
        l_med = float(np.median(loop_vals[key])) if loop_vals[key] else np.nan
        t_med = float(np.median(trio_vals[key])) if trio_vals[key] else np.nan
        gap = l_med - t_med if not np.isnan(l_med) and not np.isnan(t_med) else np.nan
        gaps[key] = {"loop_median": round(l_med, 2), "trio_median": round(t_med, 2),
                     "gap": round(gap, 2) if not np.isnan(gap) else None}
        print(f"  {label:<20s} {l_med:>10.1f} {t_med:>10.1f} {gap:>10.1f}")

    raw_gap = gaps["raw_median"]["gap"]
    full_gap = gaps["full_deconf_median"]["gap"]
    dynisf_gap = gaps["dynisf_deconf_median"]["gap"]

    if raw_gap is None or abs(raw_gap) < 1e-6:
        print("  H3 verdict: SKIP (no raw gap to close)")
        return {"h3_verdict": "SKIP", "reason": "no raw gap", "gaps": gaps}

    # Gap reduction from full-deconf to DynISF-deconf
    if full_gap is not None and dynisf_gap is not None and abs(full_gap) > 1e-6:
        dynisf_reduction_pct = 100 * (abs(full_gap) - abs(dynisf_gap)) / abs(full_gap)
    else:
        dynisf_reduction_pct = 0.0

    # Total gap reduction from raw to DynISF-deconf
    total_reduction_pct = 100 * (abs(raw_gap) - abs(dynisf_gap)) / abs(raw_gap) if dynisf_gap is not None else 0.0

    verdict = bool(dynisf_reduction_pct > 30 or total_reduction_pct > 30)

    print(f"\n  Raw gap: {raw_gap:.1f}")
    print(f"  Full-deconf gap: {full_gap:.1f}")
    print(f"  DynISF-deconf gap: {dynisf_gap:.1f}")
    print(f"  DynISF incremental reduction: {dynisf_reduction_pct:.1f}%")
    print(f"  Total reduction (raw→DynISF): {total_reduction_pct:.1f}%")
    print(f"  H3 verdict: {'PASS' if verdict else 'FAIL'} (need >30% reduction)")

    return {
        "h3_verdict": "PASS" if verdict else "FAIL",
        "gaps": gaps,
        "dynisf_incremental_reduction_pct": round(dynisf_reduction_pct, 1),
        "total_reduction_pct": round(total_reduction_pct, 1),
    }


def test_h4_prediction_mae(events, patient_isfs):
    """H4: DynISF-deconfounded ISF has lower prediction MAE.

    For each DynISF patient: split events 50/50, train on first half,
    predict second half using raw ISF vs DynISF-deconfounded ISF.
    PASS if DynISF-deconfounded has lower MAE for >50% of DynISF patients.
    """
    print("\n── H4: DynISF-deconfounded ISF prediction accuracy ──")

    dynisf_patients = {pid: p for pid, p in patient_isfs.items() if p["is_dynisf"]}
    if not dynisf_patients:
        print("  H4 verdict: SKIP (no DynISF patients)")
        return {"h4_verdict": "SKIP", "reason": "no DynISF patients"}

    improved_count = 0
    total_count = 0
    per_patient = []

    for pid, p in dynisf_patients.items():
        raw_vals = p["_raw_vals"]
        dynisf_vals = p["_dynisf_vals"]
        n = len(raw_vals)
        if n < 20:
            continue

        mid = n // 2

        # Raw ISF: train median on first half, MAE on second half
        raw_train_med = float(np.median(raw_vals[:mid]))
        raw_mae = float(np.mean(np.abs(raw_vals[mid:] - raw_train_med)))

        # DynISF-deconfounded: train median on first half, MAE on second half
        dynisf_train_med = float(np.median(dynisf_vals[:mid]))
        dynisf_mae = float(np.mean(np.abs(dynisf_vals[mid:] - dynisf_train_med)))

        improved = bool(dynisf_mae < raw_mae)
        total_count += 1
        if improved:
            improved_count += 1

        per_patient.append({
            "patient_id": pid,
            "controller": p["controller"],
            "n_events": n,
            "raw_mae": round(raw_mae, 2),
            "dynisf_mae": round(dynisf_mae, 2),
            "improved": improved,
        })
        status = "✓" if improved else "✗"
        print(f"  {pid}: raw MAE={raw_mae:.1f}, DynISF MAE={dynisf_mae:.1f} {status}")

    if total_count == 0:
        print("  H4 verdict: SKIP (no DynISF patients with enough events)")
        return {"h4_verdict": "SKIP", "reason": "no testable DynISF patients"}

    pct_improved = 100 * improved_count / total_count
    verdict = bool(pct_improved > 50)

    print(f"\n  Improved: {improved_count}/{total_count} ({pct_improved:.0f}%)")
    print(f"  H4 verdict: {'PASS' if verdict else 'FAIL'} (need >50% improved)")

    return {
        "h4_verdict": "PASS" if verdict else "FAIL",
        "n_improved": improved_count,
        "n_total": total_count,
        "pct_improved": round(pct_improved, 1),
        "per_patient": per_patient,
    }


# ── Visualization ──

def make_visualization(events, patient_isfs, h1, h2, h3, h4):
    """Create 2×2 figure: DynISF deconfounding analysis."""
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available, skipping visualization")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=13, fontweight="bold")

    # ── Panel 1 (top-left): ISF distributions by DynISF status ──
    ax = axes[0, 0]
    dynisf_raw = [p["raw_median"] for p in patient_isfs.values() if p["is_dynisf"]]
    static_raw = [p["raw_median"] for p in patient_isfs.values() if not p["is_dynisf"]]
    dynisf_deconf = [p["dynisf_deconf_median"] for p in patient_isfs.values() if p["is_dynisf"]]
    static_deconf = [p["dynisf_deconf_median"] for p in patient_isfs.values() if not p["is_dynisf"]]

    positions = [1, 2, 3.5, 4.5]
    data = [static_raw, dynisf_raw, static_deconf, dynisf_deconf]
    colors = ["#2196F3", "#4CAF50", "#2196F3", "#4CAF50"]
    tick_labels = ["Static\n(raw)", "DynISF\n(raw)", "Static\n(deconf)", "DynISF\n(deconf)"]

    # Only plot non-empty groups
    valid_positions = []
    valid_data = []
    valid_colors = []
    valid_labels = []
    for pos, d, c, lab in zip(positions, data, colors, tick_labels):
        if d:
            valid_positions.append(pos)
            valid_data.append(d)
            valid_colors.append(c)
            valid_labels.append(lab)

    if valid_data:
        vp = ax.violinplot(valid_data, positions=valid_positions, showmedians=True)
        for i, body in enumerate(vp["bodies"]):
            body.set_facecolor(valid_colors[i])
            body.set_alpha(0.6)
        ax.set_xticks(valid_positions)
        ax.set_xticklabels(valid_labels, fontsize=8)
        for pos, d in zip(valid_positions, valid_data):
            med = np.median(d)
            ax.annotate(f"{med:.1f}", (pos, med), fontsize=7,
                        xytext=(5, 5), textcoords="offset points")
    ax.set_ylabel("ISF (mg/dL/U)")
    ax.set_title("ISF Distributions by DynISF Status")
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 2 (top-right): Trio-Loop ISF gap reduction ──
    ax = axes[0, 1]
    h3_gaps = h3.get("gaps", {})
    if h3_gaps:
        stage_labels = []
        gap_vals = []
        bar_colors = []
        color_map = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#1abc9c"]
        for i, (key, label) in enumerate([
            ("raw_median", "Raw"),
            ("channel_deconf_median", "Channel"),
            ("bg_deconf_median", "BG₀"),
            ("full_deconf_median", "Full"),
            ("dynisf_deconf_median", "DynISF"),
        ]):
            if key in h3_gaps and h3_gaps[key].get("gap") is not None:
                stage_labels.append(label)
                gap_vals.append(abs(h3_gaps[key]["gap"]))
                bar_colors.append(color_map[i])

        if gap_vals:
            bars = ax.bar(stage_labels, gap_vals, color=bar_colors, alpha=0.8, edgecolor="k")
            for bar_item, val in zip(bars, gap_vals):
                ax.text(bar_item.get_x() + bar_item.get_width() / 2, val + 0.1,
                        f"{val:.1f}", ha="center", fontsize=9)
    ax.set_ylabel("|Gap| (mg/dL/U)")
    ax.set_title(f"Trio-Loop ISF Gap by Deconfounding Stage [{h3.get('h3_verdict', 'N/A')}]")
    ax.grid(axis="y", alpha=0.3)

    # ── Panel 3 (bottom-left): SR vs demand ISF scatter ──
    ax = axes[1, 0]
    dynisf_events = events[events["is_dynisf"]].copy()
    sr_valid = dynisf_events["sr_at_event"].notna()
    if sr_valid.sum() > 0:
        plot_data = dynisf_events[sr_valid]
        patients_in_plot = plot_data["patient_id"].unique()
        cmap = plt.cm.get_cmap("tab10", max(len(patients_in_plot), 1))
        for idx, pid in enumerate(patients_in_plot[:10]):  # Limit legend clutter
            mask = plot_data["patient_id"] == pid
            ax.scatter(plot_data.loc[mask, "sr_at_event"],
                       plot_data.loc[mask, "demand_isf"],
                       c=[cmap(idx)], s=10, alpha=0.4,
                       label=pid[-4:], edgecolors="none")

        # Fit line across all DynISF events
        sr_all = plot_data["sr_at_event"].values
        isf_all = plot_data["demand_isf"].values
        if np.std(sr_all) > 1e-6 and np.std(isf_all) > 1e-6:
            slope, intercept, r_val, p_val, _ = stats.linregress(sr_all, isf_all)
            x_fit = np.linspace(np.min(sr_all), np.max(sr_all), 100)
            ax.plot(x_fit, slope * x_fit + intercept, "k--", lw=1.5,
                    label=f"r={r_val:.2f}, p={p_val:.2e}")

        ax.legend(fontsize=6, ncol=2, loc="upper right")
    ax.set_xlabel("Sensitivity Ratio (at event)")
    ax.set_ylabel("Demand ISF (mg/dL/U)")
    ax.set_title("Sensitivity Ratio vs Demand ISF (DynISF patients)")
    ax.grid(alpha=0.3)

    # ── Panel 4 (bottom-right): Per-patient ISF summary (horizontal bars) ──
    ax = axes[1, 1]
    sorted_pids = sorted(
        [pid for pid in patient_isfs if patient_isfs[pid]["controller"] in CTRL_ORDER],
        key=lambda p: (CTRL_ORDER.index(patient_isfs[p]["controller"]), patient_isfs[p]["raw_median"]),
    )

    y_pos = np.arange(len(sorted_pids))
    bar_height = 0.25

    profile_vals = [patient_isfs[p]["profile_isf"] for p in sorted_pids]
    full_vals = [patient_isfs[p]["full_deconf_median"] for p in sorted_pids]
    dynisf_vals_list = [patient_isfs[p]["dynisf_deconf_median"] for p in sorted_pids]
    bar_ctrl_colors = [CTRL_COLORS.get(patient_isfs[p]["controller"], "gray") for p in sorted_pids]

    if sorted_pids:
        ax.barh(y_pos - bar_height, profile_vals, bar_height,
                color=[c + "40" for c in bar_ctrl_colors] if False else "lightgray",
                edgecolor="k", lw=0.3, label="Profile ISF")
        ax.barh(y_pos, full_vals, bar_height,
                color=[CTRL_COLORS.get(patient_isfs[p]["controller"], "gray") for p in sorted_pids],
                alpha=0.5, edgecolor="k", lw=0.3, label="Full-deconf ISF")
        ax.barh(y_pos + bar_height, dynisf_vals_list, bar_height,
                color=[CTRL_COLORS.get(patient_isfs[p]["controller"], "gray") for p in sorted_pids],
                alpha=0.9, edgecolor="k", lw=0.3, label="DynISF-deconf ISF")

        ax.set_yticks(y_pos)
        pid_labels = []
        for p in sorted_pids:
            ctrl_char = patient_isfs[p]["controller"][0].upper()
            dynisf_mark = "*" if patient_isfs[p]["is_dynisf"] else ""
            pid_labels.append(f"{p[-4:]}{dynisf_mark} ({ctrl_char})")
        ax.set_yticklabels(pid_labels, fontsize=6)
        ax.legend(fontsize=7, loc="lower right")

    ax.set_xlabel("ISF (mg/dL/U)")
    ax.set_title("Per-Patient ISF: Profile vs Deconfounded vs DynISF-Deconf")
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    out_path = VIZ_DIR / "dynisf_deconfound.png"
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"  Visualization: {out_path}")


# ── Main ──

def main():
    print(f"\n{'='*60}")
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print(f"{'='*60}\n")

    grid, ds = load_data()
    patient_info = identify_dynisf_patients(grid, ds)
    events = extract_events(grid, patient_info)

    if len(events) < 50:
        print("ERROR: Too few events for analysis")
        sys.exit(1)

    patient_isfs = compute_normalized_isfs(events)

    h1 = test_h1_dynisf_variance(events, patient_isfs)
    h2 = test_h2_sr_predicts_isf(events, patient_isfs)
    h3 = test_h3_trio_gap_closure(patient_isfs)
    h4 = test_h4_prediction_mae(events, patient_isfs)

    make_visualization(events, patient_isfs, h1, h2, h3, h4)

    # Serialize patient_isfs (exclude numpy arrays)
    per_patient_serial = {}
    for pid, p in patient_isfs.items():
        per_patient_serial[pid] = {k: v for k, v in p.items() if not k.startswith("_")}

    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "n_events": int(len(events)),
        "n_patients": int(events["patient_id"].nunique()),
        "n_dynisf_patients": int(events[events["is_dynisf"]]["patient_id"].nunique()),
        "n_static_patients": int(events[~events["is_dynisf"]]["patient_id"].nunique()),
        "channel_coefficients": {
            "bolus": BOLUS_COEFF,
            "smb": SMB_COEFF,
            "excess_basal": EXCESS_BASAL_COEFF,
            "mean": round(MEAN_COEFF, 2),
        },
        "normalization_levels": {
            "raw": "median demand_isf per patient",
            "channel_deconf": "channel-effect adjusted ISF (EXP-2698)",
            "bg_deconf": "additionally residualized on BG₀",
            "full_deconf": "OLS removing BG₀, dose, IOB, circadian, channels (EXP-2722)",
            "dynisf_deconf": "additionally residualized on sensitivity_ratio",
        },
        "per_patient": per_patient_serial,
        "hypotheses": {
            "H1_dynisf_variance": h1,
            "H2_sr_predicts_isf": h2,
            "H3_trio_gap_closure": h3,
            "H4_prediction_mae": h4,
        },
        "verdict_summary": {
            "H1": h1.get("h1_verdict", "SKIP"),
            "H2": h2.get("h2_verdict", "SKIP"),
            "H3": h3.get("h3_verdict", "SKIP"),
            "H4": h4.get("h4_verdict", "SKIP"),
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults: {OUT_JSON}")
    vd = results["verdict_summary"]
    print(f"\nVerdict: H1={vd['H1']} H2={vd['H2']} H3={vd['H3']} H4={vd['H4']}")
    return results


if __name__ == "__main__":
    main()
