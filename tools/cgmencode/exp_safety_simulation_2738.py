#!/usr/bin/env python3
"""EXP-2738: Forward Simulation Safety Validation.

SCIENTIFIC QUESTION:
  Do extracted settings improve TIR (Time in Range) without increasing TBR
  (Time Below Range)? This is the critical safety validation — extracted
  settings must not increase hypoglycemia risk.

CONTEXT:
  Prior experiments extracted per-patient settings:
    - ISF: empirical ISF from independent correction events (EXP-2720/2723)
           — typically 2-10× lower than profile
    - CR: from meal deconfounding (EXP-2729) — typically ~2× lower than profile
    - Basal: EGP-aware drift optimization (EXP-2735) — EGP accounts for 92%

METHOD — Counterfactual BGI Residual:
  For each patient we compute the difference in Blood Glucose Impact (BGI)
  between profile settings and extracted settings, then cumulate that delta
  within 6-hour windows to produce a counterfactual glucose trace.

  1. Extract empirical ISF from high-BG correction episodes (validated method).
  2. For each 6h window of actual glucose data:
       bgi_profile   = -insulin_activity * scheduled_isf
       bgi_extracted  = -insulin_activity * empirical_isf
       delta_bgi     = bgi_extracted - bgi_profile
       counterfactual = actual_glucose + cumsum(delta_bgi) within window
  3. Measure TIR / TBR / TAR on both trajectories.
  4. Compare across patients and controller types.

HYPOTHESES:
  H1: Extracted settings improve TIR by >5 pp vs profile (benefit).
  H2: TBR does NOT increase (≤ +1 pp) with extracted settings (SAFETY).
  H3: TAR decreases by >5 pp — most improvement from reducing highs.
  H4: ≥80% of patients show individual TIR improvement.
  H5: Controller type affects safety margin — some are more robust.

SAFETY GUARDS:
  - 6h window resets prevent cumulative drift.
  - ISF ratio capped at [0.3×, 3.0×] profile to prevent extreme extrapolation.
  - Counterfactual glucose clamped to [30, 500] mg/dL physiological range.
  - Minimum 5 correction episodes required for per-patient ISF extraction.

REFERENCES: EXP-2720, EXP-2723, EXP-2729, EXP-2735
"""

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Paths ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
GRID = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
DS_PATH = ROOT / "externals" / "ns-parquet" / "training" / "devicestatus.parquet"
MANIFEST = ROOT / "externals" / "experiments" / "autoprepare-qualified.json"
RESULTS_DIR = ROOT / "externals" / "experiments"
VIZ_DIR = ROOT / "visualizations" / "safety-simulation"

EXP_ID = 2738
TITLE = "Forward Simulation Safety Validation"

# ── Constants ────────────────────────────────────────────────────────
TIR_LOW = 70.0          # mg/dL — hypo threshold
TIR_HIGH = 180.0        # mg/dL — hyper threshold
STEP_MIN = 5.0          # grid cadence
STEPS_PER_HOUR = 12     # 60/5
WINDOW_HOURS = 6        # counterfactual window duration
WINDOW_STEPS = WINDOW_HOURS * STEPS_PER_HOUR  # 72 steps per window
ISF_RATIO_MIN = 0.3     # minimum allowed ISF ratio (extracted / profile)
ISF_RATIO_MAX = 3.0     # maximum allowed ISF ratio
BG_CLAMP_LOW = 30.0     # physiological floor
BG_CLAMP_HIGH = 500.0   # physiological ceiling
MIN_EPISODES = 5        # minimum correction episodes per patient
MIN_PATIENT_ROWS = 288  # minimum rows (1 day) for patient inclusion

# ISF extraction parameters
BG_FLOOR = 150          # minimum starting BG for correction episode
MIN_DOSE = 0.3          # minimum bolus dose (U)
ISOLATION_STEPS = 24    # 2h independence between episodes
EPISODE_HORIZON = 24    # 2h forward horizon for BG drop
MAX_EPISODES_PER_PATIENT = 200

# Regression coefficients from validated model (EXP-2720)
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5


# ═══════════════════════════════════════════════════════════════════════
#  DATA LOADING
# ═══════════════════════════════════════════════════════════════════════

def load_data():
    """Load grid, devicestatus, and manifest; filter to qualified patients."""
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    manifest = json.loads(MANIFEST.read_text())
    qualified = manifest.get("qualified_patients", [])
    grid = grid[grid["patient_id"].isin(qualified)].copy()

    # Map controller from devicestatus
    ds = pd.read_parquet(DS_PATH, columns=["patient_id", "controller"])
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")

    # Ensure time column is datetime
    grid["time"] = pd.to_datetime(grid["time"], errors="coerce")
    grid = grid.dropna(subset=["time"]).sort_values(["patient_id", "time"])

    n_pts = grid["patient_id"].nunique()
    ctrl_counts = grid.groupby("controller")["patient_id"].nunique()
    ctrl_str = ", ".join(f"{c}={n}" for c, n in ctrl_counts.items())
    print(f"  Loaded {len(grid):,} rows, {n_pts} patients ({ctrl_str})")
    return grid, qualified


# ═══════════════════════════════════════════════════════════════════════
#  ISF EXTRACTION — Independent Correction Episodes
# ═══════════════════════════════════════════════════════════════════════

def extract_empirical_isf(grid):
    """Extract per-patient empirical ISF from independent correction episodes.

    Method: identify high-BG episodes with a bolus correction, no carbs within
    ±1h, and ≥2h isolation from other boluses. Compute ISF = bg_drop / dose
    over 2h horizon. Report median ISF per patient.

    Returns dict: patient_id → {empirical_isf, profile_isf, n_episodes, isf_ratio, ...}
    """
    print("\n── ISF Extraction ─────────────────────────────────────")
    has_smb = "bolus_smb" in grid.columns
    has_carbs = "carbs" in grid.columns
    has_ia = "insulin_activity" in grid.columns

    patient_settings = {}

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < MIN_PATIENT_ROWS:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        carbs_col = pg["carbs"].values if has_carbs else np.zeros(len(pg))
        sched_isf = pg["scheduled_isf"].values if "scheduled_isf" in pg.columns else None
        sched_cr = pg["scheduled_cr"].values if "scheduled_cr" in pg.columns else None
        ia = pg["insulin_activity"].values if has_ia else None
        controller = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"

        if sched_isf is None:
            continue
        profile_isf = float(np.nanmedian(sched_isf))
        if profile_isf <= 0 or np.isnan(profile_isf):
            continue
        profile_cr = float(np.nanmedian(sched_cr)) if sched_cr is not None else np.nan

        # Extract independent correction episodes
        episode_isfs = []
        last_used = -ISOLATION_STEPS

        for i in range(1, len(pg) - EPISODE_HORIZON):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR:
                continue

            # Bolus at this step
            dose = float(bolus[i])
            smb_dose = float(smb[i]) if has_smb else 0.0
            total_dose = dose + smb_dose
            if total_dose < MIN_DOSE:
                continue

            # No carbs in [-1h, +2h]
            carb_start = max(0, i - STEPS_PER_HOUR)
            carb_end = min(len(carbs_col), i + EPISODE_HORIZON)
            carb_window = float(np.nansum(carbs_col[carb_start:carb_end]))
            if carb_window > 1.0:
                continue

            # Independence from prior events
            if i - last_used < ISOLATION_STEPS:
                continue

            # No additional boluses in [+1, +2h]
            future_bolus = float(np.nansum(bolus[i + 1:i + EPISODE_HORIZON]))
            future_smb = float(np.nansum(smb[i + 1:i + EPISODE_HORIZON])) if has_smb else 0.0
            if future_bolus + future_smb > 0.1:
                continue

            # Compute 2h BG drop
            end_idx = min(i + EPISODE_HORIZON, len(glucose) - 1)
            bg_end = glucose[end_idx]
            if np.isnan(bg_end):
                # Try closest non-NaN in last 3 steps
                for j in range(end_idx - 3, end_idx + 1):
                    if 0 <= j < len(glucose) and not np.isnan(glucose[j]):
                        bg_end = glucose[j]
                        break
            if np.isnan(bg_end):
                continue

            bg_drop = bg0 - bg_end
            if bg_drop < 5:
                continue  # no meaningful drop

            ep_isf = bg_drop / total_dose
            if ep_isf < 2 or ep_isf > 500:
                continue  # physiologically implausible

            episode_isfs.append(ep_isf)
            last_used = i

            if len(episode_isfs) >= MAX_EPISODES_PER_PATIENT:
                break

        if len(episode_isfs) < MIN_EPISODES:
            continue

        empirical_isf = float(np.median(episode_isfs))
        isf_ratio_raw = profile_isf / empirical_isf

        # Cap ISF ratio to safety bounds
        isf_ratio = np.clip(isf_ratio_raw, ISF_RATIO_MIN, ISF_RATIO_MAX)
        capped_empirical_isf = profile_isf / isf_ratio

        patient_settings[pid] = {
            "empirical_isf": empirical_isf,
            "capped_isf": float(capped_empirical_isf),
            "profile_isf": profile_isf,
            "profile_cr": float(profile_cr) if not np.isnan(profile_cr) else None,
            "isf_ratio_raw": float(isf_ratio_raw),
            "isf_ratio": float(isf_ratio),
            "n_episodes": len(episode_isfs),
            "isf_cv": float(np.std(episode_isfs) / np.mean(episode_isfs))
                       if np.mean(episode_isfs) > 0 else np.nan,
            "controller": controller,
        }

    print(f"  Extracted ISF for {len(patient_settings)} patients")
    for pid, s in sorted(patient_settings.items()):
        print(f"    {pid:>20s}: profile={s['profile_isf']:.1f}, "
              f"empirical={s['empirical_isf']:.1f}, "
              f"ratio={s['isf_ratio']:.2f}, "
              f"n={s['n_episodes']}, controller={s['controller']}")
    return patient_settings


# ═══════════════════════════════════════════════════════════════════════
#  COUNTERFACTUAL SIMULATION — Windowed BGI Residual
# ═══════════════════════════════════════════════════════════════════════

def compute_counterfactual(grid, patient_settings):
    """Compute counterfactual glucose traces using BGI residual method.

    For each 6h window:
      1. bgi_profile   = -insulin_activity × scheduled_isf
      2. bgi_extracted  = -insulin_activity × capped_empirical_isf
      3. delta_bgi      = bgi_extracted - bgi_profile
      4. counterfactual = actual_glucose + cumsum(delta_bgi)
      5. Clamp to [30, 500] mg/dL

    Falls back to bolus-based BGI estimation when insulin_activity is NaN.

    Returns DataFrame with columns: patient_id, time, glucose_actual,
    glucose_counterfactual, controller, window_id.
    """
    print("\n── Counterfactual Simulation ───────────────────────────")
    has_ia = "insulin_activity" in grid.columns
    results = []

    for pid, settings in sorted(patient_settings.items()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < WINDOW_STEPS:
            continue

        glucose = pg["glucose"].values.astype(np.float64)
        sched_isf = pg["scheduled_isf"].values.astype(np.float64) \
            if "scheduled_isf" in pg.columns else np.full(len(pg), settings["profile_isf"])

        # Insulin activity: use column if available, else estimate from bolus/IOB
        if has_ia:
            ia = pg["insulin_activity"].values.astype(np.float64)
        else:
            ia = np.full(len(pg), np.nan)

        # Bolus-based fallback for missing insulin_activity
        bolus = pg["bolus"].values.astype(np.float64)
        smb = pg["bolus_smb"].values.astype(np.float64) \
            if "bolus_smb" in pg.columns else np.zeros(len(pg))

        capped_isf = settings["capped_isf"]
        controller = settings["controller"]

        # Process in 6h non-overlapping windows
        n_windows = len(pg) // WINDOW_STEPS
        for w in range(n_windows):
            start = w * WINDOW_STEPS
            end = start + WINDOW_STEPS
            win_glucose = glucose[start:end].copy()
            win_isf = sched_isf[start:end].copy()
            win_ia = ia[start:end].copy()
            win_bolus = bolus[start:end].copy()
            win_smb = smb[start:end].copy()
            win_time = pg["time"].iloc[start:end].values

            # Skip windows with too many NaN glucose values
            valid_mask = ~np.isnan(win_glucose)
            if valid_mask.sum() < WINDOW_STEPS * 0.5:
                continue

            # Interpolate NaN glucose for continuous trace
            if not valid_mask.all():
                indices = np.arange(WINDOW_STEPS)
                win_glucose = np.interp(indices, indices[valid_mask],
                                        win_glucose[valid_mask])

            # Compute BGI per step using insulin_activity
            # When insulin_activity is available, it represents the instantaneous
            # insulin effect rate (U/hr). BGI = -activity × ISF gives mg/dL change.
            # insulin_activity is already in U/hr; for 5-min step: effect = activity × (5/60) × ISF
            step_fraction = STEP_MIN / 60.0  # 5min in hours

            bgi_profile = np.zeros(WINDOW_STEPS)
            bgi_extracted = np.zeros(WINDOW_STEPS)

            for t in range(WINDOW_STEPS):
                ia_val = win_ia[t]
                isf_val = win_isf[t]
                if np.isnan(isf_val) or isf_val <= 0:
                    isf_val = settings["profile_isf"]

                if not np.isnan(ia_val) and ia_val != 0:
                    # BGI from insulin activity
                    bgi_p = -ia_val * step_fraction * isf_val
                    bgi_e = -ia_val * step_fraction * capped_isf
                else:
                    # Fallback: estimate from bolus events
                    # Simple exponential decay model: peak activity at ~75min
                    b = win_bolus[t] + win_smb[t]
                    if b > 0:
                        # Distribute bolus effect over ~2h (24 steps)
                        remaining = min(WINDOW_STEPS - t, 24)
                        for dt in range(remaining):
                            # Triangular activity profile peaking at ~60min
                            peak_step = 12
                            if dt <= peak_step:
                                weight = dt / peak_step
                            else:
                                weight = max(0, 1.0 - (dt - peak_step) / (remaining - peak_step))
                            weight_norm = weight * (2.0 / remaining)  # normalize
                            act = b * weight_norm * step_fraction
                            if t + dt < WINDOW_STEPS:
                                bgi_profile[t + dt] += -act * isf_val
                                bgi_extracted[t + dt] += -act * capped_isf
                    continue  # already added to arrays
                bgi_profile[t] = bgi_p
                bgi_extracted[t] = bgi_e

            # Delta BGI and cumulative effect
            delta_bgi = bgi_extracted - bgi_profile  # per-step difference
            cumulative_delta = np.cumsum(delta_bgi)

            # Counterfactual glucose
            counterfactual = win_glucose + cumulative_delta
            counterfactual = np.clip(counterfactual, BG_CLAMP_LOW, BG_CLAMP_HIGH)

            for t in range(WINDOW_STEPS):
                results.append({
                    "patient_id": pid,
                    "time": win_time[t],
                    "glucose_actual": float(win_glucose[t]),
                    "glucose_counterfactual": float(counterfactual[t]),
                    "controller": controller,
                    "window_id": f"{pid}_w{w}",
                    "delta_bgi_step": float(delta_bgi[t]),
                    "cumulative_delta": float(cumulative_delta[t]),
                })

    df = pd.DataFrame(results)
    print(f"  Generated {len(df):,} counterfactual rows for "
          f"{df['patient_id'].nunique()} patients, "
          f"{df['window_id'].nunique()} windows")
    return df


# ═══════════════════════════════════════════════════════════════════════
#  GLYCEMIC METRICS
# ═══════════════════════════════════════════════════════════════════════

def compute_glycemic_metrics(glucose_series):
    """Compute TIR, TBR, TAR, mean, CV from a glucose series (mg/dL).

    Returns dict with percentages (0-100 scale).
    """
    valid = glucose_series[~np.isnan(glucose_series)]
    if len(valid) == 0:
        return {"tir": np.nan, "tbr": np.nan, "tar": np.nan,
                "mean_bg": np.nan, "cv": np.nan, "n_readings": 0}

    tir = float(np.mean((valid >= TIR_LOW) & (valid <= TIR_HIGH))) * 100
    tbr = float(np.mean(valid < TIR_LOW)) * 100
    tar = float(np.mean(valid > TIR_HIGH)) * 100
    mean_bg = float(np.mean(valid))
    std_bg = float(np.std(valid))
    cv = (std_bg / mean_bg * 100) if mean_bg > 0 else np.nan

    return {"tir": tir, "tbr": tbr, "tar": tar,
            "mean_bg": mean_bg, "cv": cv, "n_readings": len(valid)}


def compute_patient_metrics(cf_df, patient_settings):
    """Compute per-patient and aggregate glycemic metrics.

    Returns per_patient (list of dicts), aggregate (dict).
    """
    print("\n── Glycemic Metrics ────────────────────────────────────")
    per_patient = []

    for pid in sorted(cf_df["patient_id"].unique()):
        pdf = cf_df[cf_df["patient_id"] == pid]
        actual = pdf["glucose_actual"].values
        counterfactual = pdf["glucose_counterfactual"].values

        m_actual = compute_glycemic_metrics(actual)
        m_cf = compute_glycemic_metrics(counterfactual)

        settings = patient_settings.get(pid, {})
        row = {
            "patient_id": pid,
            "controller": settings.get("controller", "unknown"),
            "n_readings": m_actual["n_readings"],
            "n_windows": pdf["window_id"].nunique(),
            # Actual metrics
            "tir_actual": m_actual["tir"],
            "tbr_actual": m_actual["tbr"],
            "tar_actual": m_actual["tar"],
            "mean_bg_actual": m_actual["mean_bg"],
            "cv_actual": m_actual["cv"],
            # Counterfactual metrics
            "tir_cf": m_cf["tir"],
            "tbr_cf": m_cf["tbr"],
            "tar_cf": m_cf["tar"],
            "mean_bg_cf": m_cf["mean_bg"],
            "cv_cf": m_cf["cv"],
            # Deltas
            "tir_delta": m_cf["tir"] - m_actual["tir"],
            "tbr_delta": m_cf["tbr"] - m_actual["tbr"],
            "tar_delta": m_cf["tar"] - m_actual["tar"],
            "mean_bg_delta": m_cf["mean_bg"] - m_actual["mean_bg"],
            # Settings
            "profile_isf": settings.get("profile_isf", np.nan),
            "empirical_isf": settings.get("empirical_isf", np.nan),
            "capped_isf": settings.get("capped_isf", np.nan),
            "isf_ratio": settings.get("isf_ratio", np.nan),
            "n_episodes": settings.get("n_episodes", 0),
        }
        per_patient.append(row)

    pdf = pd.DataFrame(per_patient)

    # Print per-patient summary
    print(f"\n  {'Patient':>20s} | {'TIR Δ':>7s} | {'TBR Δ':>7s} | "
          f"{'TAR Δ':>7s} | {'ISF ratio':>9s} | {'Ctrl':>7s}")
    print(f"  {'─' * 20}─┼─{'─' * 7}─┼─{'─' * 7}─┼─"
          f"{'─' * 7}─┼─{'─' * 9}─┼─{'─' * 7}")
    for _, r in pdf.sort_values("tir_delta", ascending=False).iterrows():
        flag = " ⚠" if r["tbr_delta"] > 1.0 else ""
        print(f"  {r['patient_id']:>20s} | {r['tir_delta']:+7.2f} | "
              f"{r['tbr_delta']:+7.2f} | {r['tar_delta']:+7.2f} | "
              f"{r['isf_ratio']:9.2f} | {r['controller']:>7s}{flag}")

    # Aggregate
    aggregate = {
        "n_patients": len(pdf),
        "tir_actual_mean": float(pdf["tir_actual"].mean()),
        "tir_cf_mean": float(pdf["tir_cf"].mean()),
        "tir_delta_mean": float(pdf["tir_delta"].mean()),
        "tir_delta_median": float(pdf["tir_delta"].median()),
        "tbr_actual_mean": float(pdf["tbr_actual"].mean()),
        "tbr_cf_mean": float(pdf["tbr_cf"].mean()),
        "tbr_delta_mean": float(pdf["tbr_delta"].mean()),
        "tbr_delta_max": float(pdf["tbr_delta"].max()),
        "tar_actual_mean": float(pdf["tar_actual"].mean()),
        "tar_cf_mean": float(pdf["tar_cf"].mean()),
        "tar_delta_mean": float(pdf["tar_delta"].mean()),
        "pct_tir_improved": float((pdf["tir_delta"] > 0).mean() * 100),
        "pct_tbr_safe": float((pdf["tbr_delta"] <= 1.0).mean() * 100),
        "pct_tar_reduced": float((pdf["tar_delta"] < 0).mean() * 100),
    }

    print(f"\n  Aggregate:")
    print(f"    TIR: {aggregate['tir_actual_mean']:.1f}% → "
          f"{aggregate['tir_cf_mean']:.1f}% "
          f"(Δ = {aggregate['tir_delta_mean']:+.1f} pp)")
    print(f"    TBR: {aggregate['tbr_actual_mean']:.1f}% → "
          f"{aggregate['tbr_cf_mean']:.1f}% "
          f"(Δ = {aggregate['tbr_delta_mean']:+.1f} pp, "
          f"max = {aggregate['tbr_delta_max']:+.1f} pp)")
    print(f"    TAR: {aggregate['tar_actual_mean']:.1f}% → "
          f"{aggregate['tar_cf_mean']:.1f}% "
          f"(Δ = {aggregate['tar_delta_mean']:+.1f} pp)")
    print(f"    Patients w/ TIR improvement: "
          f"{aggregate['pct_tir_improved']:.0f}%")
    print(f"    Patients w/ safe TBR (≤+1pp): "
          f"{aggregate['pct_tbr_safe']:.0f}%")

    return per_patient, aggregate


# ═══════════════════════════════════════════════════════════════════════
#  HYPOTHESIS TESTING
# ═══════════════════════════════════════════════════════════════════════

def test_hypotheses(per_patient, aggregate, cf_df):
    """Test all five hypotheses with statistical rigor.

    Returns dict of hypothesis results with verdicts.
    """
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)
    pdf = pd.DataFrame(per_patient)
    results = {}

    # ── H1: TIR improves by >5pp ────────────────────────────────────
    print("\n─── H1: Extracted settings improve TIR by >5 pp ───────")
    tir_delta = pdf["tir_delta"].values
    mean_delta = float(np.mean(tir_delta))
    median_delta = float(np.median(tir_delta))
    if len(tir_delta) > 2 and np.std(tir_delta) > 1e-6:
        t_stat, p_val = stats.ttest_1samp(tir_delta, 0)
        p_val = float(p_val)
        t_stat = float(t_stat)
    else:
        t_stat, p_val = np.nan, np.nan

    h1_pass = bool(mean_delta > 5.0 and (np.isnan(p_val) or p_val < 0.05))
    verdict = "SUPPORTED ✓" if h1_pass else "NOT SUPPORTED ✗"
    print(f"  Mean TIR delta: {mean_delta:+.2f} pp")
    print(f"  Median TIR delta: {median_delta:+.2f} pp")
    print(f"  One-sample t-test: t={t_stat:.3f}, p={p_val:.4f}")
    print(f"  Verdict: {verdict}")
    results["H1"] = {
        "description": "TIR improves by >5 pp",
        "mean_delta": mean_delta,
        "median_delta": median_delta,
        "t_stat": t_stat if not np.isnan(t_stat) else None,
        "p_value": p_val if not np.isnan(p_val) else None,
        "threshold": 5.0,
        "pass": h1_pass,
        "verdict": verdict,
    }

    # ── H2: TBR does NOT increase (≤ +1pp) — SAFETY ────────────────
    print("\n─── H2: TBR does NOT increase (≤ +1 pp) — SAFETY ─────")
    tbr_delta = pdf["tbr_delta"].values
    mean_tbr_delta = float(np.mean(tbr_delta))
    max_tbr_delta = float(np.max(tbr_delta))
    pct_safe = float((tbr_delta <= 1.0).mean() * 100)

    # Non-inferiority test: is mean TBR delta ≤ 1pp?
    # Test H0: mean(tbr_delta) > 1 vs H1: mean(tbr_delta) ≤ 1
    if len(tbr_delta) > 2 and np.std(tbr_delta) > 1e-6:
        t_stat_tbr, p_val_tbr = stats.ttest_1samp(tbr_delta, 1.0)
        # One-sided: we want to show mean ≤ 1, so p is halved for left tail
        p_one_sided = float(p_val_tbr) / 2.0 if float(t_stat_tbr) < 0 else 1.0 - float(p_val_tbr) / 2.0
    else:
        t_stat_tbr, p_one_sided = np.nan, np.nan

    h2_pass = bool(mean_tbr_delta <= 1.0 and pct_safe >= 80.0)
    verdict = "SAFE ✓" if h2_pass else "SAFETY CONCERN ✗"
    print(f"  Mean TBR delta: {mean_tbr_delta:+.2f} pp")
    print(f"  Max TBR delta: {max_tbr_delta:+.2f} pp")
    print(f"  Patients with safe TBR (≤+1pp): {pct_safe:.0f}%")
    print(f"  Non-inferiority p (one-sided): {p_one_sided:.4f}")
    print(f"  *** Verdict: {verdict} ***")
    results["H2_SAFETY"] = {
        "description": "TBR does NOT increase (≤ +1 pp) — SAFETY CRITICAL",
        "mean_delta": mean_tbr_delta,
        "max_delta": max_tbr_delta,
        "pct_safe": pct_safe,
        "p_one_sided": p_one_sided if not np.isnan(p_one_sided) else None,
        "threshold": 1.0,
        "pass": h2_pass,
        "verdict": verdict,
    }

    # ── H3: TAR decreases by >5pp ──────────────────────────────────
    print("\n─── H3: TAR decreases by >5 pp ────────────────────────")
    tar_delta = pdf["tar_delta"].values
    mean_tar_delta = float(np.mean(tar_delta))
    median_tar_delta = float(np.median(tar_delta))
    if len(tar_delta) > 2 and np.std(tar_delta) > 1e-6:
        t_stat_tar, p_val_tar = stats.ttest_1samp(tar_delta, 0)
        p_val_tar = float(p_val_tar)
    else:
        t_stat_tar, p_val_tar = np.nan, np.nan

    # TAR decrease means delta < 0, so checking mean < -5
    h3_pass = bool(mean_tar_delta < -5.0 and (np.isnan(p_val_tar) or p_val_tar < 0.05))
    verdict = "SUPPORTED ✓" if h3_pass else "NOT SUPPORTED ✗"
    print(f"  Mean TAR delta: {mean_tar_delta:+.2f} pp")
    print(f"  Median TAR delta: {median_tar_delta:+.2f} pp")
    print(f"  T-test: t={t_stat_tar:.3f}, p={p_val_tar:.4f}")
    print(f"  Verdict: {verdict}")
    results["H3"] = {
        "description": "TAR decreases by >5 pp",
        "mean_delta": mean_tar_delta,
        "median_delta": median_tar_delta,
        "t_stat": float(t_stat_tar) if not np.isnan(t_stat_tar) else None,
        "p_value": float(p_val_tar) if not np.isnan(p_val_tar) else None,
        "threshold": -5.0,
        "pass": h3_pass,
        "verdict": verdict,
    }

    # ── H4: ≥80% of patients show TIR improvement ──────────────────
    print("\n─── H4: ≥80% of patients show TIR improvement ────────")
    pct_improved = float((pdf["tir_delta"] > 0).mean() * 100)
    n_improved = int((pdf["tir_delta"] > 0).sum())
    n_total = len(pdf)

    # Binomial test: is the proportion > 80%?
    if n_total > 0:
        binom_p = float(stats.binom_test(n_improved, n_total, 0.8,
                                          alternative="greater")) \
            if hasattr(stats, "binom_test") else np.nan
        # scipy >= 1.7 deprecates binom_test; use binomtest
        if np.isnan(binom_p):
            try:
                binom_result = stats.binomtest(n_improved, n_total, 0.8,
                                                alternative="greater")
                binom_p = float(binom_result.pvalue)
            except Exception:
                binom_p = np.nan
    else:
        binom_p = np.nan

    h4_pass = bool(pct_improved >= 80.0)
    verdict = "SUPPORTED ✓" if h4_pass else "NOT SUPPORTED ✗"
    print(f"  Patients with TIR improvement: {n_improved}/{n_total} "
          f"({pct_improved:.1f}%)")
    print(f"  Binomial test (p > 0.8): p={binom_p:.4f}")
    print(f"  Verdict: {verdict}")
    results["H4"] = {
        "description": "≥80% of patients show TIR improvement",
        "pct_improved": pct_improved,
        "n_improved": n_improved,
        "n_total": n_total,
        "binomial_p": binom_p if not np.isnan(binom_p) else None,
        "threshold": 80.0,
        "pass": h4_pass,
        "verdict": verdict,
    }

    # ── H5: Controller type affects safety margin ───────────────────
    print("\n─── H5: Controller type affects safety margin ─────────")
    ctrl_groups = {}
    for _, r in pdf.iterrows():
        ctrl = r["controller"]
        if ctrl not in ctrl_groups:
            ctrl_groups[ctrl] = {"tir_delta": [], "tbr_delta": [], "tar_delta": []}
        ctrl_groups[ctrl]["tir_delta"].append(r["tir_delta"])
        ctrl_groups[ctrl]["tbr_delta"].append(r["tbr_delta"])
        ctrl_groups[ctrl]["tar_delta"].append(r["tar_delta"])

    print(f"\n  {'Controller':>12s} | {'N':>3s} | {'TIR Δ':>8s} | "
          f"{'TBR Δ':>8s} | {'TAR Δ':>8s} | {'Safe%':>6s}")
    print(f"  {'─' * 12}─┼─{'─' * 3}─┼─{'─' * 8}─┼─"
          f"{'─' * 8}─┼─{'─' * 8}─┼─{'─' * 6}")
    ctrl_summary = {}
    for ctrl in sorted(ctrl_groups.keys()):
        g = ctrl_groups[ctrl]
        n = len(g["tir_delta"])
        tir_m = float(np.mean(g["tir_delta"]))
        tbr_m = float(np.mean(g["tbr_delta"]))
        tar_m = float(np.mean(g["tar_delta"]))
        safe_pct = float(np.mean(np.array(g["tbr_delta"]) <= 1.0) * 100)
        print(f"  {ctrl:>12s} | {n:>3d} | {tir_m:+8.2f} | "
              f"{tbr_m:+8.2f} | {tar_m:+8.2f} | {safe_pct:5.0f}%")
        ctrl_summary[ctrl] = {
            "n": n,
            "tir_delta_mean": tir_m,
            "tbr_delta_mean": tbr_m,
            "tar_delta_mean": tar_m,
            "pct_safe": safe_pct,
        }

    # Kruskal-Wallis test for controller effect on TBR delta
    groups_tbr = [np.array(ctrl_groups[c]["tbr_delta"])
                  for c in ctrl_groups if len(ctrl_groups[c]["tbr_delta"]) >= 2]
    if len(groups_tbr) >= 2:
        try:
            h_stat, kw_p = stats.kruskal(*groups_tbr)
            h_stat, kw_p = float(h_stat), float(kw_p)
        except Exception:
            h_stat, kw_p = np.nan, np.nan
    else:
        h_stat, kw_p = np.nan, np.nan

    h5_pass = bool(not np.isnan(kw_p) and kw_p < 0.05) if len(groups_tbr) >= 2 else False
    verdict = "SUPPORTED ✓" if h5_pass else "NOT SUPPORTED ✗"
    print(f"\n  Kruskal-Wallis (TBR delta by controller): H={h_stat:.3f}, "
          f"p={kw_p:.4f}")
    print(f"  Verdict: {verdict}")
    results["H5"] = {
        "description": "Controller type affects safety margin",
        "controller_summary": ctrl_summary,
        "kruskal_wallis_H": h_stat if not np.isnan(h_stat) else None,
        "kruskal_wallis_p": kw_p if not np.isnan(kw_p) else None,
        "pass": h5_pass,
        "verdict": verdict,
    }

    return results


# ═══════════════════════════════════════════════════════════════════════
#  VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════

def create_visualizations(per_patient, aggregate, cf_df, hypothesis_results):
    """Create 2×3 panel visualization for safety simulation results."""
    print("\n── Creating Visualizations ─────────────────────────────")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    pdf = pd.DataFrame(per_patient).sort_values("tir_delta", ascending=False)

    fig = plt.figure(figsize=(22, 14))
    gs = gridspec.GridSpec(2, 3, hspace=0.35, wspace=0.30,
                           left=0.06, right=0.96, top=0.92, bottom=0.08)

    # ── Panel 1: TIR comparison — paired bar chart ──────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    patients = pdf["patient_id"].values
    x = np.arange(len(patients))
    width = 0.35
    bars_actual = ax1.bar(x - width / 2, pdf["tir_actual"].values, width,
                          label="Profile (actual)", color="#5b9bd5", alpha=0.8)
    bars_cf = ax1.bar(x + width / 2, pdf["tir_cf"].values, width,
                      label="Extracted (counterfactual)", color="#70ad47", alpha=0.8)
    ax1.set_xlabel("Patient")
    ax1.set_ylabel("Time in Range (%)")
    ax1.set_title("TIR: Profile vs Extracted Settings", fontweight="bold")
    ax1.set_xticks(x)
    # Shorten patient IDs for display
    short_ids = [p[:8] + "…" if len(p) > 8 else p for p in patients]
    ax1.set_xticklabels(short_ids, rotation=45, ha="right", fontsize=7)
    ax1.legend(fontsize=8, loc="lower left")
    ax1.axhline(y=70, color="gray", linestyle="--", alpha=0.5, label="70% target")
    ax1.set_ylim(0, 100)

    # ── Panel 2: TBR safety scatter ─────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    tbr_actual = pdf["tbr_actual"].values
    tbr_cf = pdf["tbr_cf"].values
    controllers = pdf["controller"].values
    ctrl_colors = {"loop": "#5b9bd5", "trio": "#ed7d31", "openaps": "#70ad47",
                   "unknown": "#808080"}
    for ctrl in np.unique(controllers):
        mask = controllers == ctrl
        ax2.scatter(tbr_actual[mask], tbr_cf[mask], c=ctrl_colors.get(ctrl, "#808080"),
                    label=ctrl, s=80, alpha=0.8, edgecolors="black", linewidths=0.5)

    # Reference lines
    max_tbr = max(np.max(tbr_actual), np.max(tbr_cf), 5) * 1.2
    ax2.plot([0, max_tbr], [0, max_tbr], "k--", alpha=0.5, label="y=x (no change)")
    ax2.plot([0, max_tbr], [1, max_tbr + 1], "r--", alpha=0.3,
             label="+1pp threshold")
    # Red zone: where TBR increases
    ax2.fill_between([0, max_tbr], [1, max_tbr + 1], [max_tbr * 2, max_tbr * 2],
                     color="red", alpha=0.05)
    ax2.set_xlabel("TBR Actual (%)")
    ax2.set_ylabel("TBR Counterfactual (%)")
    ax2.set_title("TBR Safety Check (below y=x is BETTER)", fontweight="bold")
    ax2.legend(fontsize=7)
    ax2.set_xlim(-0.5, max(max_tbr, 5))
    ax2.set_ylim(-0.5, max(max_tbr, 5))

    # ── Panel 3: TAR reduction bar chart ────────────────────────────
    ax3 = fig.add_subplot(gs[0, 2])
    tar_delta = pdf["tar_delta"].values
    colors_tar = ["#70ad47" if d < 0 else "#c00000" for d in tar_delta]
    ax3.bar(x, tar_delta, color=colors_tar, alpha=0.8)
    ax3.axhline(y=0, color="black", linewidth=0.8)
    ax3.axhline(y=-5, color="green", linestyle="--", alpha=0.5,
                label="-5pp threshold (H3)")
    ax3.set_xlabel("Patient")
    ax3.set_ylabel("TAR Change (pp)")
    ax3.set_title("TAR Reduction per Patient", fontweight="bold")
    ax3.set_xticks(x)
    ax3.set_xticklabels(short_ids, rotation=45, ha="right", fontsize=7)
    ax3.legend(fontsize=8)

    # ── Panel 4: Counterfactual glucose example trace ───────────────
    ax4 = fig.add_subplot(gs[1, 0])

    # Pick a representative patient (median TIR improvement)
    pdf_sorted = pdf.sort_values("tir_delta")
    median_idx = len(pdf_sorted) // 2
    rep_pid = pdf_sorted.iloc[median_idx]["patient_id"]

    rep_data = cf_df[cf_df["patient_id"] == rep_pid].copy()
    rep_data = rep_data.sort_values("time")
    # Show up to 3 days (864 steps)
    max_show = min(len(rep_data), 864)
    rep_show = rep_data.iloc[:max_show]

    hours = np.arange(max_show) * 5 / 60.0  # hours from start
    ax4.plot(hours, rep_show["glucose_actual"].values, color="#5b9bd5",
             alpha=0.7, linewidth=1.0, label="Actual (profile)")
    ax4.plot(hours, rep_show["glucose_counterfactual"].values, color="#70ad47",
             alpha=0.7, linewidth=1.0, label="Counterfactual (extracted)")
    ax4.axhline(y=TIR_LOW, color="red", linestyle=":", alpha=0.5)
    ax4.axhline(y=TIR_HIGH, color="orange", linestyle=":", alpha=0.5)
    ax4.fill_between(hours, TIR_LOW, TIR_HIGH, color="green", alpha=0.05)
    ax4.set_xlabel("Hours")
    ax4.set_ylabel("Glucose (mg/dL)")
    ax4.set_title(f"Glucose Trace: {rep_pid[:12]} "
                  f"(TIR Δ={pdf_sorted.iloc[median_idx]['tir_delta']:+.1f}pp)",
                  fontweight="bold")
    ax4.legend(fontsize=8)
    ax4.set_ylim(40, 400)

    # ── Panel 5: Improvement by controller type ─────────────────────
    ax5 = fig.add_subplot(gs[1, 1])
    ctrl_list = sorted(pdf["controller"].unique())
    positions = []
    bp_data_tir = []
    bp_data_tbr = []
    bp_labels = []

    for i, ctrl in enumerate(ctrl_list):
        mask = pdf["controller"] == ctrl
        bp_data_tir.append(pdf.loc[mask, "tir_delta"].values)
        bp_data_tbr.append(pdf.loc[mask, "tbr_delta"].values)
        bp_labels.append(ctrl)
        positions.append(i)

    if bp_data_tir:
        bp1 = ax5.boxplot(bp_data_tir, positions=np.array(positions) - 0.15,
                          widths=0.25, patch_artist=True,
                          tick_labels=[""] * len(ctrl_list))
        for patch in bp1["boxes"]:
            patch.set_facecolor("#5b9bd5")
            patch.set_alpha(0.7)
        bp2 = ax5.boxplot(bp_data_tbr, positions=np.array(positions) + 0.15,
                          widths=0.25, patch_artist=True,
                          tick_labels=[""] * len(ctrl_list))
        for patch in bp2["boxes"]:
            patch.set_facecolor("#ed7d31")
            patch.set_alpha(0.7)

        ax5.set_xticks(positions)
        ax5.set_xticklabels(bp_labels, fontsize=10)
    ax5.axhline(y=0, color="black", linewidth=0.8)
    ax5.axhline(y=1, color="red", linestyle="--", alpha=0.5,
                label="TBR safety limit (+1pp)")

    # Manual legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor="#5b9bd5", alpha=0.7, label="TIR Δ"),
                       Patch(facecolor="#ed7d31", alpha=0.7, label="TBR Δ")]
    ax5.legend(handles=legend_elements, fontsize=8, loc="upper right")
    ax5.set_ylabel("Change (pp)")
    ax5.set_title("Improvement by Controller Type", fontweight="bold")

    # ── Panel 6: Safety summary — stacked bar ──────────────────────
    ax6 = fig.add_subplot(gs[1, 2])

    categories = ["TIR", "TBR", "TAR"]
    improved = []
    unchanged = []
    worsened = []

    # TIR: improved = delta > 1, unchanged = |delta| ≤ 1, worsened = delta < -1
    tir_d = pdf["tir_delta"].values
    improved.append(float((tir_d > 1).sum()))
    unchanged.append(float((np.abs(tir_d) <= 1).sum()))
    worsened.append(float((tir_d < -1).sum()))

    # TBR: improved = delta < -0.5 (less hypo), worsened = delta > 1 (more hypo)
    tbr_d = pdf["tbr_delta"].values
    improved.append(float((tbr_d < -0.5).sum()))
    unchanged.append(float((np.abs(tbr_d) <= 0.5).sum()))
    worsened.append(float((tbr_d > 0.5).sum()))

    # TAR: improved = delta < -1 (less hyper), worsened = delta > 1 (more hyper)
    tar_d = pdf["tar_delta"].values
    improved.append(float((tar_d < -1).sum()))
    unchanged.append(float((np.abs(tar_d) <= 1).sum()))
    worsened.append(float((tar_d > 1).sum()))

    x_cat = np.arange(len(categories))
    width_cat = 0.6
    ax6.bar(x_cat, improved, width_cat, label="Improved", color="#70ad47",
            alpha=0.8)
    ax6.bar(x_cat, unchanged, width_cat, bottom=improved,
            label="Unchanged (±1pp)", color="#ffc000", alpha=0.8)
    bottoms = [improved[i] + unchanged[i] for i in range(len(categories))]
    ax6.bar(x_cat, worsened, width_cat, bottom=bottoms,
            label="Worsened", color="#c00000", alpha=0.8)
    ax6.set_xticks(x_cat)
    ax6.set_xticklabels(categories, fontsize=11)
    ax6.set_ylabel("Number of Patients")
    ax6.set_title("Safety Summary: Patient Outcomes", fontweight="bold")
    ax6.legend(fontsize=8)

    # ── Suptitle ────────────────────────────────────────────────────
    h2_verdict = hypothesis_results.get("H2_SAFETY", {}).get("verdict", "?")
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}\n"
                 f"N={len(pdf)} patients | "
                 f"TIR Δ={aggregate['tir_delta_mean']:+.1f}pp | "
                 f"TBR Δ={aggregate['tbr_delta_mean']:+.1f}pp | "
                 f"Safety: {h2_verdict}",
                 fontsize=14, fontweight="bold", y=0.98)

    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    out_path = VIZ_DIR / "safety_simulation.png"
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved visualization → {out_path}")
    return str(out_path)


# ═══════════════════════════════════════════════════════════════════════
#  ADDITIONAL ANALYSES
# ═══════════════════════════════════════════════════════════════════════

def analyze_dose_response(per_patient):
    """Check if ISF ratio magnitude predicts TIR improvement (dose-response)."""
    print("\n── Dose-Response Analysis ──────────────────────────────")
    pdf = pd.DataFrame(per_patient)

    isf_ratio = pdf["isf_ratio"].values
    tir_delta = pdf["tir_delta"].values
    tbr_delta = pdf["tbr_delta"].values

    valid = ~(np.isnan(isf_ratio) | np.isnan(tir_delta))
    if valid.sum() < 5:
        print("  Insufficient data for dose-response analysis")
        return {}

    r_isf_tir, p_isf_tir = stats.spearmanr(isf_ratio[valid], tir_delta[valid])
    r_isf_tbr, p_isf_tbr = stats.spearmanr(isf_ratio[valid], tbr_delta[valid])

    print(f"  ISF ratio vs TIR delta: ρ={r_isf_tir:.3f}, p={p_isf_tir:.4f}")
    print(f"  ISF ratio vs TBR delta: ρ={r_isf_tbr:.3f}, p={p_isf_tbr:.4f}")

    # Check if larger ISF corrections (ratio further from 1) are riskier
    high_ratio = isf_ratio > np.median(isf_ratio)
    if high_ratio.sum() > 2 and (~high_ratio).sum() > 2:
        tbr_high = tbr_delta[high_ratio]
        tbr_low = tbr_delta[~high_ratio]
        if np.std(tbr_high) > 1e-6 or np.std(tbr_low) > 1e-6:
            u_stat, u_p = stats.mannwhitneyu(tbr_high, tbr_low,
                                              alternative="two-sided")
            print(f"  TBR delta (high vs low ISF ratio): U={u_stat:.1f}, "
                  f"p={u_p:.4f}")
            print(f"    High ratio group mean TBR Δ: {np.mean(tbr_high):+.2f}")
            print(f"    Low ratio group mean TBR Δ: {np.mean(tbr_low):+.2f}")
        else:
            u_stat, u_p = np.nan, np.nan
    else:
        u_stat, u_p = np.nan, np.nan

    return {
        "isf_ratio_vs_tir": {
            "spearman_r": float(r_isf_tir),
            "p_value": float(p_isf_tir),
        },
        "isf_ratio_vs_tbr": {
            "spearman_r": float(r_isf_tbr),
            "p_value": float(p_isf_tbr),
        },
    }


def analyze_temporal_safety(cf_df):
    """Check if counterfactual safety varies by time of day."""
    print("\n── Temporal Safety Analysis ────────────────────────────")
    cf_df = cf_df.copy()
    try:
        cf_df["hour"] = pd.to_datetime(cf_df["time"]).dt.hour
    except Exception:
        print("  Could not parse time column; skipping temporal analysis")
        return {}

    # Group into 4 periods: night (0-6), morning (6-12), afternoon (12-18), evening (18-24)
    def period(h):
        if h < 6:
            return "night (0-6)"
        elif h < 12:
            return "morning (6-12)"
        elif h < 18:
            return "afternoon (12-18)"
        else:
            return "evening (18-24)"

    cf_df["period"] = cf_df["hour"].apply(period)

    results = {}
    for p in ["night (0-6)", "morning (6-12)", "afternoon (12-18)", "evening (18-24)"]:
        mask = cf_df["period"] == p
        if mask.sum() < 100:
            continue
        actual = cf_df.loc[mask, "glucose_actual"].values
        counter = cf_df.loc[mask, "glucose_counterfactual"].values

        tbr_actual = float(np.mean(actual < TIR_LOW) * 100)
        tbr_cf = float(np.mean(counter < TIR_LOW) * 100)
        tir_actual = float(np.mean((actual >= TIR_LOW) & (actual <= TIR_HIGH)) * 100)
        tir_cf = float(np.mean((counter >= TIR_LOW) & (counter <= TIR_HIGH)) * 100)

        results[p] = {
            "n_readings": int(mask.sum()),
            "tir_actual": tir_actual,
            "tir_cf": tir_cf,
            "tir_delta": tir_cf - tir_actual,
            "tbr_actual": tbr_actual,
            "tbr_cf": tbr_cf,
            "tbr_delta": tbr_cf - tbr_actual,
        }

        flag = " ⚠" if (tbr_cf - tbr_actual) > 1.0 else ""
        print(f"  {p:>20s}: TIR {tir_actual:.1f}→{tir_cf:.1f} "
              f"(Δ{tir_cf - tir_actual:+.1f}), "
              f"TBR {tbr_actual:.1f}→{tbr_cf:.1f} "
              f"(Δ{tbr_cf - tbr_actual:+.1f}){flag}")

    return results


def analyze_window_stability(cf_df):
    """Analyze stability of counterfactual results across 6h windows."""
    print("\n── Window Stability Analysis ───────────────────────────")
    win_stats = []

    for wid in cf_df["window_id"].unique():
        wdf = cf_df[cf_df["window_id"] == wid]
        if len(wdf) < WINDOW_STEPS * 0.5:
            continue

        actual = wdf["glucose_actual"].values
        counter = wdf["glucose_counterfactual"].values
        cum_delta = wdf["cumulative_delta"].values

        max_abs_delta = float(np.max(np.abs(cum_delta)))
        end_delta = float(cum_delta[-1]) if len(cum_delta) > 0 else 0.0
        tbr_actual = float(np.mean(actual < TIR_LOW) * 100)
        tbr_cf = float(np.mean(counter < TIR_LOW) * 100)

        win_stats.append({
            "window_id": wid,
            "max_abs_delta": max_abs_delta,
            "end_delta": end_delta,
            "tbr_delta": tbr_cf - tbr_actual,
        })

    if not win_stats:
        print("  No valid windows for stability analysis")
        return {}

    wsdf = pd.DataFrame(win_stats)
    max_delta_p50 = float(wsdf["max_abs_delta"].median())
    max_delta_p95 = float(wsdf["max_abs_delta"].quantile(0.95))
    end_delta_std = float(wsdf["end_delta"].std())

    print(f"  Windows analyzed: {len(wsdf)}")
    print(f"  Max |cumulative delta| — median: {max_delta_p50:.1f} mg/dL, "
          f"P95: {max_delta_p95:.1f} mg/dL")
    print(f"  End-of-window delta SD: {end_delta_std:.1f} mg/dL")

    # Flag windows where cumulative delta exceeds 100 mg/dL
    extreme = (wsdf["max_abs_delta"] > 100).sum()
    print(f"  Windows with |delta| > 100 mg/dL: {extreme}/{len(wsdf)} "
          f"({extreme / len(wsdf) * 100:.1f}%)")

    return {
        "n_windows": len(wsdf),
        "max_abs_delta_median": max_delta_p50,
        "max_abs_delta_p95": max_delta_p95,
        "end_delta_std": end_delta_std,
        "extreme_windows_pct": float(extreme / len(wsdf) * 100) if len(wsdf) > 0 else 0,
    }


# ═══════════════════════════════════════════════════════════════════════
#  RESULTS SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════

def save_results(per_patient, aggregate, hypothesis_results,
                 dose_response, temporal, window_stability, viz_path):
    """Save all results to JSON."""
    # Convert numpy types for JSON serialization
    def clean(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            val = float(obj)
            return val if not np.isnan(val) else None
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [clean(v) for v in obj]
        return obj

    output = {
        "experiment": f"EXP-{EXP_ID}",
        "title": TITLE,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "method": "Counterfactual BGI residual with 6h windowed accumulation",
        "parameters": {
            "window_hours": WINDOW_HOURS,
            "isf_ratio_bounds": [ISF_RATIO_MIN, ISF_RATIO_MAX],
            "bg_clamp": [BG_CLAMP_LOW, BG_CLAMP_HIGH],
            "min_episodes": MIN_EPISODES,
            "bg_floor": BG_FLOOR,
            "isolation_hours": ISOLATION_STEPS / STEPS_PER_HOUR,
        },
        "aggregate": clean(aggregate),
        "hypotheses": clean(hypothesis_results),
        "per_patient": clean(per_patient),
        "dose_response": clean(dose_response),
        "temporal_safety": clean(temporal),
        "window_stability": clean(window_stability),
        "visualization": str(viz_path),
        "safety_summary": {
            "overall_safe": bool(
                hypothesis_results.get("H2_SAFETY", {}).get("pass", False)),
            "mean_tbr_delta": clean(aggregate.get("tbr_delta_mean")),
            "max_tbr_delta": clean(aggregate.get("tbr_delta_max")),
            "pct_patients_safe": clean(aggregate.get("pct_tbr_safe")),
            "recommendation": (
                "SAFE: Extracted settings can be used — TBR does not increase"
                if hypothesis_results.get("H2_SAFETY", {}).get("pass", False)
                else "CAUTION: Extracted settings may increase hypoglycemia — "
                     "review per-patient TBR before use"
            ),
        },
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"exp-{EXP_ID}_safety_simulation.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Saved results → {out_path}")
    return str(out_path)


# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    # ── Step 1: Load data ────────────────────────────────────────────
    grid, qualified = load_data()

    # ── Step 2: Extract per-patient ISF ──────────────────────────────
    patient_settings = extract_empirical_isf(grid)
    if len(patient_settings) < 3:
        print("\nERROR: Too few patients with valid ISF extraction")
        sys.exit(1)

    # ── Step 3: Counterfactual simulation ────────────────────────────
    cf_df = compute_counterfactual(grid, patient_settings)
    if len(cf_df) == 0:
        print("\nERROR: No counterfactual data generated")
        sys.exit(1)

    # ── Step 4: Compute glycemic metrics ─────────────────────────────
    per_patient, aggregate = compute_patient_metrics(cf_df, patient_settings)

    # ── Step 5: Hypothesis testing ───────────────────────────────────
    hypothesis_results = test_hypotheses(per_patient, aggregate, cf_df)

    # ── Step 6: Additional analyses ──────────────────────────────────
    dose_response = analyze_dose_response(per_patient)
    temporal = analyze_temporal_safety(cf_df)
    window_stability = analyze_window_stability(cf_df)

    # ── Step 7: Visualization ────────────────────────────────────────
    viz_path = create_visualizations(per_patient, aggregate, cf_df,
                                     hypothesis_results)

    # ── Step 8: Save results ─────────────────────────────────────────
    json_path = save_results(per_patient, aggregate, hypothesis_results,
                             dose_response, temporal, window_stability, viz_path)

    # ── Final Summary ────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"\n  Patients analyzed: {aggregate['n_patients']}")
    print(f"  TIR: {aggregate['tir_actual_mean']:.1f}% → "
          f"{aggregate['tir_cf_mean']:.1f}% "
          f"(Δ = {aggregate['tir_delta_mean']:+.1f} pp)")
    print(f"  TBR: {aggregate['tbr_actual_mean']:.1f}% → "
          f"{aggregate['tbr_cf_mean']:.1f}% "
          f"(Δ = {aggregate['tbr_delta_mean']:+.1f} pp)")
    print(f"  TAR: {aggregate['tar_actual_mean']:.1f}% → "
          f"{aggregate['tar_cf_mean']:.1f}% "
          f"(Δ = {aggregate['tar_delta_mean']:+.1f} pp)")

    print(f"\n  HYPOTHESIS VERDICTS:")
    for k, v in sorted(hypothesis_results.items()):
        marker = "✓" if v.get("pass") else "✗"
        print(f"    [{marker}] {k}: {v['description']} — {v['verdict']}")

    safety = hypothesis_results.get("H2_SAFETY", {})
    print(f"\n  {'★' * 50}")
    if safety.get("pass"):
        print(f"  ★  SAFETY VERDICT: PASSED                          ★")
        print(f"  ★  Extracted settings are safe to use.              ★")
    else:
        print(f"  ★  SAFETY VERDICT: REVIEW REQUIRED                 ★")
        print(f"  ★  Check per-patient TBR before using settings.     ★")
    print(f"  {'★' * 50}")

    print(f"\n  Results: {json_path}")
    print(f"  Visualization: {viz_path}")
    print(f"\nDone.")


if __name__ == "__main__":
    main()
