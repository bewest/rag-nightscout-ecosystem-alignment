#!/usr/bin/env python3
"""EXP-2742: CR via Insulin-and-EGP Subtraction.

Previous CR extraction (EXP-2729) found profile CR is ~2× too high
(8.8 vs 4.9 g/U).  That extraction didn't properly subtract out the EGP
contribution during meals or the basal-EGP balance.  During a meal:
  - Carbs raise glucose        (SIGNAL we want)
  - Correction/bolus insulin   (CONFOUND — subtract)
  - Basal insulin              (CONFOUND — subtract)
  - EGP raises glucose         (CONFOUND — subtract, inflates apparent carb effect)

By properly subtracting insulin effects AND EGP, we get a cleaner per-gram
carb impact and potentially a CR closer to the profile value.

Predecessors: EXP-2729 (CR extraction), EXP-2740 (basal-EGP equilibrium)

Hypotheses:
  H1: Multi-factor CR is >30% closer to profile than naive CR
  H2: EGP subtraction shifts CR toward profile by >15%
  H3: Multi-factor CR has lower inter-event CV than naive
  H4: CR gap (profile/empirical) correlates with per-patient EGP (r>0.3)
  H5: After full subtraction, >50% of patients have CR within 50% of profile
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats

# ── Paths ────────────────────────────────────────────────────────────────────

GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
EGP_JSON = Path("externals/experiments/exp-2740_basal_egp_equilibrium.json")
EXP2729_JSON = Path("externals/experiments/exp-2729_carb_ratio.json")
RESULTS_DIR = Path("externals/experiments")
OUT_JSON = RESULTS_DIR / "exp-2742_cr_multifactor.json"
VIZ_DIR = Path("visualizations/cr-multifactor")

EXP_ID = "EXP-2742"
EXP_TITLE = "CR via Insulin-and-EGP Subtraction"

# ── Tuning constants ─────────────────────────────────────────────────────────

HORIZON_STEPS = 48          # 4 h at 5-min intervals
MIN_CARBS = 5.0             # minimum grams to qualify as meal
MIN_DOSE = 0.3              # minimum insulin (bolus + SMB) in window
MIN_GAP_STEPS = 48          # 4 h gap for independence
BOLUS_COEFF = -129.2        # channel coefficients (from EXP-2698)
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5
MEAN_COEFF = (BOLUS_COEFF + SMB_COEFF + EXCESS_BASAL_COEFF) / 3.0

MIN_CARB_IMPACT = 5.0       # minimum carb BG impact to avoid division instability
CR_FLOOR = 1.0              # physiological CR bounds
CR_CEIL = 60.0

# ── Helpers ──────────────────────────────────────────────────────────────────


def safe_float(v, default=0.0):
    """Convert to float, returning default for NaN/None."""
    if v is None:
        return default
    try:
        f = float(v)
        return default if np.isnan(f) else f
    except (TypeError, ValueError):
        return default


def safe_median(arr):
    """Median that handles empty or all-NaN arrays."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return np.nan
    return float(np.median(arr))


def gap_ratio(profile, empirical):
    """Compute relative gap: |profile - empirical| / profile.

    Returns NaN if profile <= 0.
    """
    if profile <= 0 or np.isnan(profile) or np.isnan(empirical):
        return np.nan
    return abs(profile - empirical) / profile


def gap_closure_pct(naive_gap, method_gap):
    """How much of the naive→profile gap was closed (%).

    100% = method matches profile exactly.
    Negative = method went further from profile.
    """
    if naive_gap <= 0 or np.isnan(naive_gap) or np.isnan(method_gap):
        return np.nan
    return 100.0 * (1.0 - method_gap / naive_gap)


# ── Data loading ─────────────────────────────────────────────────────────────


def load_data():
    """Load grid, manifest, EGP data, and identify patients with EGP."""
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]
    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()

    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)

    egp_data = json.loads(EGP_JSON.read_text())
    per_patient_egp = egp_data["per_patient_egp"]

    # Only keep patients that have EGP data
    egp_patients = set(per_patient_egp.keys())
    grid_egp = grid[grid["patient_id"].isin(egp_patients)].copy()

    print(f"  Grid rows (all qualified):  {len(grid):,}")
    print(f"  Grid rows (EGP patients):   {len(grid_egp):,}")
    print(f"  Patients with EGP data:     {len(egp_patients)}")
    print(f"  EGP patients: {sorted(egp_patients)}")

    return grid_egp, per_patient_egp, ctrl_map


# ── Meal-event extraction ────────────────────────────────────────────────────


def extract_meal_events(grid, per_patient_egp):
    """Identify meal events with 4-h outcome windows.

    For each event, compute all 5 CR methods inline.
    """
    events = []
    has_scheduled_cr = "scheduled_cr" in grid.columns
    has_scheduled_isf = "scheduled_isf" in grid.columns

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(
            drop=True
        )
        n = len(pg)
        if n < HORIZON_STEPS + 7:
            continue

        # Extract arrays
        glucose = pg["glucose"].values.astype(float)
        carbs = pg["carbs"].values.astype(float)
        carbs = np.where(np.isnan(carbs), 0.0, carbs)
        bolus = pg["bolus"].values.astype(float)
        bolus = np.where(np.isnan(bolus), 0.0, bolus)
        smb = pg["bolus_smb"].values.astype(float) if "bolus_smb" in pg.columns else np.zeros(n)
        smb = np.where(np.isnan(smb), 0.0, smb)
        net_basal = pg["net_basal"].values.astype(float) if "net_basal" in pg.columns else np.zeros(n)
        net_basal = np.where(np.isnan(net_basal), 0.0, net_basal)
        iob = pg["iob"].values.astype(float) if "iob" in pg.columns else np.zeros(n)
        iob = np.where(np.isnan(iob), 0.0, iob)
        sched_basal = pg["scheduled_basal_rate"].values.astype(float) if "scheduled_basal_rate" in pg.columns else np.zeros(n)
        sched_basal = np.where(np.isnan(sched_basal), 0.0, sched_basal)

        if has_scheduled_cr:
            sched_cr = pg["scheduled_cr"].values.astype(float)
            sched_cr = np.where(np.isnan(sched_cr), 0.0, sched_cr)
        else:
            sched_cr = np.zeros(n)

        if has_scheduled_isf:
            sched_isf = pg["scheduled_isf"].values.astype(float)
            sched_isf = np.where(np.isnan(sched_isf), 0.0, sched_isf)
        else:
            sched_isf = np.zeros(n)

        ctrl = pg["controller"].iloc[0] if "controller" in pg.columns else "unknown"
        times = pg["time"].values

        # Get per-patient EGP
        egp_info = per_patient_egp.get(pid, {})
        median_egp = safe_float(egp_info.get("median_egp", 0.0))
        circadian_egp = egp_info.get("circadian_egp", None)

        for i in range(6, n - HORIZON_STEPS):
            # 30-min window for carbs (i-6 .. i+6)
            lo = max(i - 6, 0)
            hi = min(i + 7, n)
            window_carbs = float(np.sum(carbs[lo:hi]))
            if window_carbs < MIN_CARBS:
                continue

            # Bolus in ±6 step window
            window_bolus = float(np.sum(bolus[lo:hi]))
            if window_bolus <= 0:
                continue

            bg0 = glucose[i]
            bg_end = glucose[i + HORIZON_STEPS]
            if np.isnan(bg0) or np.isnan(bg_end):
                continue

            # No second meal in [i+6 .. i+HORIZON_STEPS)
            future_carbs = float(np.sum(carbs[i + 6: i + HORIZON_STEPS]))
            if future_carbs >= MIN_CARBS:
                continue

            # ── 4-h aggregations ──
            bolus_4h = float(np.nansum(bolus[i: i + HORIZON_STEPS]))
            smb_4h = float(np.nansum(smb[i: i + HORIZON_STEPS]))
            # excess basal = net_basal (actual - scheduled) in U over the window
            excess_basal_4h = float(np.nansum(net_basal[i: i + HORIZON_STEPS])) / 12.0
            # Total basal insulin delivered (scheduled_basal_rate is U/hr, each step is 5 min)
            basal_insulin_4h = float(np.nansum(sched_basal[i: i + HORIZON_STEPS])) / 12.0
            # Correction insulin = bolus + SMB (no basal)
            correction_insulin_4h = bolus_4h + smb_4h
            # Total insulin (all channels)
            total_insulin_4h = bolus_4h + smb_4h + excess_basal_4h

            if total_insulin_4h < MIN_DOSE:
                continue

            glucose_rise_4h = bg_end - bg0
            hour = int(pd.Timestamp(times[i]).hour) if not pd.isna(times[i]) else 0

            # Get EGP rate for this hour
            if circadian_egp is not None and len(circadian_egp) == 24:
                egp_val = circadian_egp[hour]
                if egp_val is None or (isinstance(egp_val, float) and np.isnan(egp_val)):
                    egp_rate = median_egp
                else:
                    egp_rate = safe_float(egp_val, median_egp)
            else:
                egp_rate = median_egp

            # EGP contribution over 4h (48 steps × rate per step)
            egp_contribution_4h = egp_rate * HORIZON_STEPS

            # ISF for CR computation
            isf_val = float(np.median(sched_isf[lo:hi])) if has_scheduled_isf else 60.0
            if isf_val <= 0:
                isf_val = 60.0

            # Profile CR
            profile_cr_val = float(np.median(sched_cr[lo:hi])) if has_scheduled_cr else 0.0

            # ── METHOD 1: Naive CR ──
            # Total insulin BG impact (negative — lowers glucose)
            total_insulin_bg_impact = total_insulin_4h * MEAN_COEFF
            # Carb BG impact = observed rise - insulin impact
            # insulin impact is negative, so subtracting it ADDS to carb impact
            carb_bg_impact_naive = glucose_rise_4h - total_insulin_bg_impact
            if carb_bg_impact_naive < MIN_CARB_IMPACT:
                cr_naive = np.nan
            else:
                carb_sensitivity_naive = carb_bg_impact_naive / window_carbs
                cr_naive = isf_val / carb_sensitivity_naive

            # ── METHOD 2: EGP-subtracted CR ──
            # EGP raises glucose, so subtract it to isolate carb effect
            carb_bg_impact_egp = glucose_rise_4h - total_insulin_bg_impact - egp_contribution_4h
            if carb_bg_impact_egp < MIN_CARB_IMPACT:
                cr_egp = np.nan
            else:
                carb_sensitivity_egp = carb_bg_impact_egp / window_carbs
                cr_egp = isf_val / carb_sensitivity_egp

            # ── METHOD 3: Basal-subtracted CR ──
            # Only subtract correction insulin, not basal (basal ≈ EGP by design)
            correction_bg_impact = correction_insulin_4h * MEAN_COEFF
            carb_bg_impact_basal = glucose_rise_4h - correction_bg_impact
            if carb_bg_impact_basal < MIN_CARB_IMPACT:
                cr_basal = np.nan
            else:
                carb_sensitivity_basal = carb_bg_impact_basal / window_carbs
                cr_basal = isf_val / carb_sensitivity_basal

            # ── METHOD 4: Full multi-factor CR ──
            # glucose_rise = carb_effect + total_insulin_effect + EGP_effect
            # carb_effect = glucose_rise - total_insulin_effect - EGP_effect
            # total_insulin_effect is negative (lowers glucose), so:
            # carb_effect = glucose_rise - (negative number) - EGP
            #             = glucose_rise + |insulin_effect| - EGP
            # This is the same as Method 2 (EGP-subtracted) when using total insulin.
            # The TRUE multi-factor separates correction vs maintenance:
            # glucose_rise = carb_effect + correction_effect + (basal_effect + EGP_effect) + noise
            # The (basal_effect + EGP_effect) is the basal-EGP residual from EXP-2740
            # basal_effect = basal_insulin * COEFF (negative)
            # EGP_effect = EGP_rate * steps (positive)
            # net_maintenance = EGP_effect + basal_effect
            basal_bg_impact = basal_insulin_4h * EXCESS_BASAL_COEFF  # negative
            net_maintenance = egp_contribution_4h + basal_bg_impact  # EGP - |basal|
            carb_bg_impact_full = glucose_rise_4h - correction_bg_impact - net_maintenance
            if carb_bg_impact_full < MIN_CARB_IMPACT:
                cr_full = np.nan
            else:
                carb_sensitivity_full = carb_bg_impact_full / window_carbs
                cr_full = isf_val / carb_sensitivity_full

            # Clamp all CRs
            for cr_var in [cr_naive, cr_egp, cr_basal, cr_full]:
                pass  # clamping below in append

            events.append({
                "patient_id": pid,
                "controller": ctrl,
                "time_idx": i,
                "hour": hour,
                "bg0": bg0,
                "bg_end": bg_end,
                "glucose_rise_4h": glucose_rise_4h,
                "carbs": window_carbs,
                "bolus_4h": bolus_4h,
                "smb_4h": smb_4h,
                "excess_basal_4h": excess_basal_4h,
                "basal_insulin_4h": basal_insulin_4h,
                "correction_insulin_4h": correction_insulin_4h,
                "total_insulin_4h": total_insulin_4h,
                "iob_start": float(iob[i]),
                "isf": isf_val,
                "egp_rate": egp_rate,
                "egp_contribution_4h": egp_contribution_4h,
                "profile_cr": profile_cr_val,
                "carb_bg_impact_naive": carb_bg_impact_naive,
                "carb_bg_impact_egp": carb_bg_impact_egp,
                "carb_bg_impact_basal": carb_bg_impact_basal,
                "carb_bg_impact_full": carb_bg_impact_full,
                "cr_naive": float(np.clip(cr_naive, CR_FLOOR, CR_CEIL)) if np.isfinite(cr_naive) else np.nan,
                "cr_egp": float(np.clip(cr_egp, CR_FLOOR, CR_CEIL)) if np.isfinite(cr_egp) else np.nan,
                "cr_basal": float(np.clip(cr_basal, CR_FLOOR, CR_CEIL)) if np.isfinite(cr_basal) else np.nan,
                "cr_full": float(np.clip(cr_full, CR_FLOOR, CR_CEIL)) if np.isfinite(cr_full) else np.nan,
                "total_insulin_bg_impact": total_insulin_bg_impact,
                "correction_bg_impact": correction_bg_impact,
                "basal_bg_impact": basal_bg_impact,
                "net_maintenance": net_maintenance,
            })

    return pd.DataFrame(events)


# ── Independence filtering ───────────────────────────────────────────────────


def filter_independent(ev):
    """Keep only events with >= 4h gap from previous event (same patient)."""
    ev = ev.sort_values(["patient_id", "time_idx"]).copy()
    keep = []
    last_idx: dict[str, int] = {}

    for _, row in ev.iterrows():
        pid = row["patient_id"]
        tidx = row["time_idx"]
        if pid not in last_idx or (tidx - last_idx[pid]) >= MIN_GAP_STEPS:
            keep.append(True)
            last_idx[pid] = tidx
        else:
            keep.append(False)

    ev["independent"] = keep
    return ev


# ── Per-patient aggregation ──────────────────────────────────────────────────


def compute_patient_summaries(ev_indep, per_patient_egp):
    """Aggregate per-patient CR across all methods."""
    methods = ["cr_naive", "cr_egp", "cr_basal", "cr_full"]
    method_labels = {
        "cr_naive": "M1: Naive",
        "cr_egp": "M2: EGP-subtracted",
        "cr_basal": "M3: Basal-subtracted",
        "cr_full": "M4: Multi-factor",
    }

    records = []
    for pid in ev_indep["patient_id"].unique():
        pe = ev_indep[ev_indep["patient_id"] == pid]
        if len(pe) == 0:
            continue

        ctrl = pe["controller"].iloc[0]
        profile_cr_vals = pe["profile_cr"].values
        profile_cr = float(np.median(profile_cr_vals[profile_cr_vals > 0])) if np.any(profile_cr_vals > 0) else 0.0

        egp_info = per_patient_egp.get(pid, {})
        median_egp = safe_float(egp_info.get("median_egp", 0.0))

        rec = {
            "patient_id": pid,
            "controller": ctrl,
            "n_events": len(pe),
            "profile_cr": round(profile_cr, 2),
            "median_egp": round(median_egp, 4),
            "median_carbs": round(float(pe["carbs"].median()), 1),
            "median_glucose_rise": round(float(pe["glucose_rise_4h"].median()), 1),
        }

        for m in methods:
            valid = pe[m].dropna()
            if len(valid) == 0:
                rec[f"{m}_median"] = np.nan
                rec[f"{m}_iqr_lo"] = np.nan
                rec[f"{m}_iqr_hi"] = np.nan
                rec[f"{m}_cv"] = np.nan
                rec[f"{m}_n_valid"] = 0
                rec[f"{m}_gap_ratio"] = np.nan
            else:
                med = float(np.median(valid))
                q25 = float(np.percentile(valid, 25))
                q75 = float(np.percentile(valid, 75))
                cv = float(np.std(valid) / max(np.mean(valid), 1e-6))
                rec[f"{m}_median"] = round(med, 2)
                rec[f"{m}_iqr_lo"] = round(q25, 2)
                rec[f"{m}_iqr_hi"] = round(q75, 2)
                rec[f"{m}_cv"] = round(cv, 3)
                rec[f"{m}_n_valid"] = len(valid)
                rec[f"{m}_gap_ratio"] = round(gap_ratio(profile_cr, med), 3) if profile_cr > 0 else np.nan

        # Gap closure: how much each method closes the naive→profile gap
        naive_gap = rec.get("cr_naive_gap_ratio", np.nan)
        for m in methods[1:]:  # skip naive
            m_gap = rec.get(f"{m}_gap_ratio", np.nan)
            rec[f"{m}_gap_closure_pct"] = round(gap_closure_pct(naive_gap, m_gap), 1) if np.isfinite(naive_gap) and np.isfinite(m_gap) else np.nan

        records.append(rec)

    return pd.DataFrame(records)


# ── Hypothesis tests ─────────────────────────────────────────────────────────


def test_h1(pt_df):
    """H1: Multi-factor CR is >30% closer to profile than naive CR (gap ratio decreases)."""
    print("\n── H1: Multi-factor CR >30% closer to profile than naive ──")
    valid = pt_df.dropna(subset=["cr_naive_gap_ratio", "cr_full_gap_ratio"])
    valid = valid[valid["profile_cr"] > 0]
    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients with valid data")
        return {"h1_verdict": "SKIP", "detail": "insufficient data"}

    naive_gaps = valid["cr_naive_gap_ratio"].values
    full_gaps = valid["cr_full_gap_ratio"].values
    # Per-patient closure
    closures = []
    for ng, fg in zip(naive_gaps, full_gaps):
        if ng > 0:
            closures.append(100.0 * (1.0 - fg / ng))
        else:
            closures.append(np.nan)
    closures = np.array(closures)
    valid_closures = closures[np.isfinite(closures)]

    if len(valid_closures) == 0:
        print("  SKIP: no valid closure data")
        return {"h1_verdict": "SKIP", "detail": "no valid closures"}

    median_closure = float(np.median(valid_closures))
    mean_closure = float(np.mean(valid_closures))

    # Population-level gap comparison
    pop_naive_gap = float(np.median(naive_gaps))
    pop_full_gap = float(np.median(full_gaps))
    pop_closure = gap_closure_pct(pop_naive_gap, pop_full_gap)

    verdict = "PASS" if median_closure > 30.0 else "FAIL"
    print(f"  Median per-patient gap closure: {median_closure:.1f}%")
    print(f"  Population gap (naive):  {pop_naive_gap:.3f}")
    print(f"  Population gap (full):   {pop_full_gap:.3f}")
    print(f"  Population closure:      {pop_closure:.1f}%")
    print(f"  Threshold: >30% → {verdict}")

    return {
        "h1_verdict": verdict,
        "median_per_patient_closure_pct": round(median_closure, 1),
        "mean_per_patient_closure_pct": round(mean_closure, 1),
        "pop_naive_gap": round(pop_naive_gap, 3),
        "pop_full_gap": round(pop_full_gap, 3),
        "pop_closure_pct": round(safe_float(pop_closure), 1),
        "n_patients": len(valid_closures),
        "per_patient_closure": {str(pid): round(c, 1) for pid, c in zip(valid["patient_id"], closures) if np.isfinite(c)},
    }


def test_h2(pt_df):
    """H2: EGP subtraction shifts CR toward profile by >15%."""
    print("\n── H2: EGP subtraction shifts CR toward profile by >15% ──")
    valid = pt_df.dropna(subset=["cr_naive_gap_ratio", "cr_egp_gap_ratio"])
    valid = valid[valid["profile_cr"] > 0]
    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients with valid data")
        return {"h2_verdict": "SKIP", "detail": "insufficient data"}

    naive_gaps = valid["cr_naive_gap_ratio"].values
    egp_gaps = valid["cr_egp_gap_ratio"].values
    closures = []
    for ng, eg in zip(naive_gaps, egp_gaps):
        if ng > 0:
            closures.append(100.0 * (1.0 - eg / ng))
        else:
            closures.append(np.nan)
    closures = np.array(closures)
    valid_closures = closures[np.isfinite(closures)]

    if len(valid_closures) == 0:
        print("  SKIP: no valid closure data")
        return {"h2_verdict": "SKIP", "detail": "no valid closures"}

    median_closure = float(np.median(valid_closures))
    pop_naive_gap = float(np.median(naive_gaps))
    pop_egp_gap = float(np.median(egp_gaps))
    pop_closure = gap_closure_pct(pop_naive_gap, pop_egp_gap)

    verdict = "PASS" if median_closure > 15.0 else "FAIL"
    print(f"  Median per-patient EGP closure: {median_closure:.1f}%")
    print(f"  Pop gap naive→egp: {pop_naive_gap:.3f} → {pop_egp_gap:.3f}")
    print(f"  Pop closure: {pop_closure:.1f}%")
    print(f"  Threshold: >15% → {verdict}")

    # Also report how much CR shifted
    naive_medians = valid["cr_naive_median"].values
    egp_medians = valid["cr_egp_median"].values
    shift_pcts = 100.0 * (egp_medians - naive_medians) / np.maximum(np.abs(naive_medians), 1e-6)

    return {
        "h2_verdict": verdict,
        "median_per_patient_closure_pct": round(median_closure, 1),
        "pop_naive_gap": round(pop_naive_gap, 3),
        "pop_egp_gap": round(pop_egp_gap, 3),
        "pop_closure_pct": round(safe_float(pop_closure), 1),
        "median_cr_shift_pct": round(float(np.median(shift_pcts)), 1),
        "n_patients": len(valid_closures),
    }


def test_h3(pt_df):
    """H3: Multi-factor CR has lower inter-event CV than naive (>50% patients)."""
    print("\n── H3: Multi-factor CR has lower CV than naive ──")
    valid = pt_df.dropna(subset=["cr_naive_cv", "cr_full_cv"])
    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients")
        return {"h3_verdict": "SKIP", "detail": "insufficient data"}

    improved = valid["cr_full_cv"] < valid["cr_naive_cv"]
    n_imp = int(improved.sum())
    n_total = len(valid)
    pct = 100 * n_imp / max(n_total, 1)
    verdict = "PASS" if pct > 50 else "FAIL"
    print(f"  {n_imp}/{n_total} patients with lower CV ({pct:.1f}%) → {verdict}")
    print(f"  Median CV (naive):  {valid['cr_naive_cv'].median():.3f}")
    print(f"  Median CV (full):   {valid['cr_full_cv'].median():.3f}")

    return {
        "h3_verdict": verdict,
        "n_improved": n_imp,
        "n_total": n_total,
        "pct_improved": round(pct, 1),
        "median_cv_naive": round(float(valid["cr_naive_cv"].median()), 3),
        "median_cv_full": round(float(valid["cr_full_cv"].median()), 3),
        "median_cv_egp": round(float(valid["cr_egp_cv"].median()), 3) if "cr_egp_cv" in valid.columns else None,
        "median_cv_basal": round(float(valid["cr_basal_cv"].median()), 3) if "cr_basal_cv" in valid.columns else None,
    }


def test_h4(pt_df):
    """H4: CR gap correlates with per-patient EGP level (r > 0.3)."""
    print("\n── H4: CR gap correlates with EGP level (r > 0.3) ──")
    valid = pt_df.dropna(subset=["cr_naive_gap_ratio", "median_egp"])
    valid = valid[valid["profile_cr"] > 0]
    if len(valid) < 4:
        print("  SKIP: fewer than 4 patients")
        return {"h4_verdict": "SKIP", "detail": "insufficient data"}

    x = valid["median_egp"].values
    y = valid["cr_naive_gap_ratio"].values

    # Guard against constant values
    if np.std(x) < 1e-6 or np.std(y) < 1e-6:
        print("  SKIP: near-constant EGP or gap values")
        return {"h4_verdict": "SKIP", "detail": "constant values"}

    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    r = abs(r_value)
    verdict = "PASS" if r > 0.3 else "FAIL"
    print(f"  r = {r_value:.3f} (|r| = {r:.3f}), p = {p_value:.3e}")
    print(f"  slope = {slope:.4f}")
    print(f"  Threshold: |r| > 0.3 → {verdict}")

    return {
        "h4_verdict": verdict,
        "r_value": round(float(r_value), 4),
        "abs_r": round(r, 4),
        "p_value": float(p_value),
        "slope": round(float(slope), 4),
        "intercept": round(float(intercept), 4),
        "n_patients": len(valid),
    }


def test_h5(pt_df):
    """H5: After full subtraction, >50% of patients have CR within 50% of profile."""
    print("\n── H5: >50% of patients have multi-factor CR within 50% of profile ──")
    valid = pt_df.dropna(subset=["cr_full_median"])
    valid = valid[valid["profile_cr"] > 0]
    if len(valid) < 3:
        print("  SKIP: fewer than 3 patients")
        return {"h5_verdict": "SKIP", "detail": "insufficient data"}

    full_cr = valid["cr_full_median"].values
    profile_cr = valid["profile_cr"].values
    ratio = full_cr / profile_cr
    within_50 = (ratio >= 0.5) & (ratio <= 1.5)  # within 50% = ratio 0.5–1.5
    n_within = int(np.sum(within_50))
    n_total = len(valid)
    pct = 100 * n_within / max(n_total, 1)
    verdict = "PASS" if pct > 50 else "FAIL"

    # Also check naive for comparison
    naive_valid = pt_df.dropna(subset=["cr_naive_median"])
    naive_valid = naive_valid[naive_valid["profile_cr"] > 0]
    if len(naive_valid) > 0:
        naive_ratio = naive_valid["cr_naive_median"].values / naive_valid["profile_cr"].values
        naive_within = (naive_ratio >= 0.5) & (naive_ratio <= 1.5)
        naive_pct = 100 * np.sum(naive_within) / len(naive_valid)
    else:
        naive_pct = np.nan

    print(f"  {n_within}/{n_total} patients within 50% of profile ({pct:.1f}%) → {verdict}")
    print(f"  For comparison, naive: {safe_float(naive_pct, 0):.1f}% within 50%")
    print(f"  Median ratio (full/profile): {np.median(ratio):.2f}")

    return {
        "h5_verdict": verdict,
        "n_within_50pct": n_within,
        "n_total": n_total,
        "pct_within_50pct": round(pct, 1),
        "naive_pct_within_50pct": round(safe_float(naive_pct, 0), 1),
        "median_ratio_full_over_profile": round(float(np.median(ratio)), 3),
        "per_patient_ratio": {str(pid): round(float(r), 3) for pid, r in zip(valid["patient_id"], ratio)},
    }


# ── Visualization ────────────────────────────────────────────────────────────


def make_visualization(pt_df, ev_indep, h_results):
    """Create 2×3 panel visualization."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    method_colors = {
        "M1: Naive": "#e74c3c",
        "M2: EGP-sub": "#f39c12",
        "M3: Basal-sub": "#3498db",
        "M4: Multi-factor": "#2ecc71",
        "M5: Profile": "#9b59b6",
    }
    ctrl_colors = {
        "loop": "#1f77b4",
        "openaps": "#ff7f0e",
        "trio": "#2ca02c",
        "unknown": "#999999",
    }

    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    fig.suptitle(
        f"{EXP_ID}: {EXP_TITLE}",
        fontsize=16, fontweight="bold", y=0.98,
    )

    # ── Panel 1: CR method comparison (box plot) ─────────────────────────
    ax = axes[0, 0]
    method_cols = ["cr_naive_median", "cr_egp_median", "cr_basal_median", "cr_full_median", "profile_cr"]
    method_names = ["M1: Naive", "M2: EGP-sub", "M3: Basal-sub", "M4: Multi-factor", "M5: Profile"]
    box_data = []
    labels_used = []
    colors_used = []
    for col, name in zip(method_cols, method_names):
        vals = pt_df[col].dropna().values
        if len(vals) > 0:
            box_data.append(vals)
            labels_used.append(name)
            colors_used.append(method_colors.get(name, "#999999"))

    if box_data:
        bp = ax.boxplot(box_data, tick_labels=labels_used, patch_artist=True,
                        widths=0.6, showmeans=True,
                        meanprops=dict(marker="D", markerfacecolor="white",
                                       markeredgecolor="black", markersize=6))
        for patch, c in zip(bp["boxes"], colors_used):
            patch.set_facecolor(c)
            patch.set_alpha(0.6)
        ax.set_xticklabels(labels_used, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("CR (g/U)")
    ax.set_title("CR Method Comparison")
    ax.axhline(float(pt_df["profile_cr"].median()), color="#9b59b6", ls="--",
               lw=1, alpha=0.5, label="Median profile")
    ax.legend(fontsize=7)

    # ── Panel 2: Gap closure waterfall ───────────────────────────────────
    ax = axes[0, 1]
    valid_pt = pt_df.dropna(subset=["cr_naive_gap_ratio", "cr_full_gap_ratio"])
    valid_pt = valid_pt[valid_pt["profile_cr"] > 0]
    if len(valid_pt) > 0:
        pop_naive_gap = float(valid_pt["cr_naive_gap_ratio"].median())
        pop_egp_gap = float(valid_pt["cr_egp_gap_ratio"].median()) if "cr_egp_gap_ratio" in valid_pt.columns else pop_naive_gap
        pop_basal_gap = float(valid_pt["cr_basal_gap_ratio"].median()) if "cr_basal_gap_ratio" in valid_pt.columns else pop_naive_gap
        pop_full_gap = float(valid_pt["cr_full_gap_ratio"].median())

        stages = ["Naive Gap", "−EGP", "−Basal", "Full Method"]
        gaps = [pop_naive_gap, pop_egp_gap, pop_basal_gap, pop_full_gap]
        stage_colors = ["#e74c3c", "#f39c12", "#3498db", "#2ecc71"]

        bars = ax.bar(stages, gaps, color=stage_colors, edgecolor="k", linewidth=0.5, alpha=0.7)
        ax.set_ylabel("Gap Ratio (|profile − CR| / profile)")
        ax.set_title("Gap Closure by Method")
        ax.set_xticklabels(stages, rotation=20, ha="right", fontsize=9)

        for bar, val in zip(bars, gaps):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=8)
    else:
        ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center",
                transform=ax.transAxes)
        ax.set_title("Gap Closure by Method")

    # ── Panel 3: Per-patient CR ladder ───────────────────────────────────
    ax = axes[0, 2]
    if len(pt_df) > 0:
        sorted_pt = pt_df.sort_values("profile_cr", ascending=True)
        y_pos = np.arange(len(sorted_pt))
        short_pids = [str(p)[-6:] for p in sorted_pt["patient_id"]]

        # Plot each method as a marker
        marker_cfg = [
            ("cr_naive_median", "o", "#e74c3c", "M1: Naive"),
            ("cr_egp_median", "s", "#f39c12", "M2: EGP-sub"),
            ("cr_basal_median", "^", "#3498db", "M3: Basal-sub"),
            ("cr_full_median", "D", "#2ecc71", "M4: Multi-factor"),
            ("profile_cr", "*", "#9b59b6", "M5: Profile"),
        ]
        for col, marker, color, label in marker_cfg:
            vals = sorted_pt[col].values
            valid_mask = np.isfinite(vals)
            ax.scatter(vals[valid_mask], y_pos[valid_mask],
                       marker=marker, c=color, s=40, alpha=0.8,
                       edgecolors="k", linewidths=0.3, label=label, zorder=3)

        ax.set_yticks(y_pos)
        ax.set_yticklabels(short_pids, fontsize=7)
        ax.set_xlabel("CR (g/U)")
        ax.legend(fontsize=6, loc="lower right")
    ax.set_title("Per-Patient CR Ladder")

    # ── Panel 4: Precision (CV comparison) ───────────────────────────────
    ax = axes[1, 0]
    cv_cols = ["cr_naive_cv", "cr_egp_cv", "cr_basal_cv", "cr_full_cv"]
    cv_names = ["M1: Naive", "M2: EGP-sub", "M3: Basal-sub", "M4: Multi-factor"]
    cv_data = []
    cv_labels = []
    cv_colors = []
    for col, name in zip(cv_cols, cv_names):
        vals = pt_df[col].dropna().values
        if len(vals) > 0:
            cv_data.append(vals)
            cv_labels.append(name)
            cv_colors.append(method_colors.get(name, "#999999"))

    if cv_data:
        bp = ax.boxplot(cv_data, tick_labels=cv_labels, patch_artist=True,
                        widths=0.5, showmeans=True,
                        meanprops=dict(marker="D", markerfacecolor="white",
                                       markeredgecolor="black", markersize=5))
        for patch, c in zip(bp["boxes"], cv_colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.6)
        ax.set_xticklabels(cv_labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Coefficient of Variation")
    ax.set_title("Inter-Event CV by Method")

    # ── Panel 5: EGP level vs CR gap ─────────────────────────────────────
    ax = axes[1, 1]
    valid_h4 = pt_df.dropna(subset=["median_egp", "cr_naive_gap_ratio"])
    valid_h4 = valid_h4[valid_h4["profile_cr"] > 0]
    if len(valid_h4) >= 3:
        x = valid_h4["median_egp"].values
        y = valid_h4["cr_naive_gap_ratio"].values
        colors = [ctrl_colors.get(c, "#999999") for c in valid_h4["controller"]]
        ax.scatter(x, y, c=colors, s=50, alpha=0.8, edgecolors="k", linewidths=0.5, zorder=3)

        # Regression line if enough variation
        if np.std(x) > 1e-6 and np.std(y) > 1e-6:
            slope, intercept, r_value, p_value, _ = stats.linregress(x, y)
            x_line = np.linspace(np.min(x), np.max(x), 50)
            ax.plot(x_line, slope * x_line + intercept, "k--", lw=1, alpha=0.6)
            ax.text(0.05, 0.95, f"r={r_value:.3f}\np={p_value:.3f}",
                    transform=ax.transAxes, fontsize=9, va="top",
                    bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

        # Label each point
        for _, row in valid_h4.iterrows():
            ax.annotate(str(row["patient_id"])[-4:],
                        (row["median_egp"], row["cr_naive_gap_ratio"]),
                        fontsize=6, alpha=0.7,
                        xytext=(3, 3), textcoords="offset points")

        legend_handles = [
            Line2D([0], [0], marker="o", color="w", markerfacecolor=c,
                   markersize=7, label=lab)
            for lab, c in ctrl_colors.items()
            if lab in pt_df["controller"].values
        ]
        if legend_handles:
            ax.legend(handles=legend_handles, fontsize=7, loc="lower right")
    ax.set_xlabel("Median EGP (mg/dL per 5-min)")
    ax.set_ylabel("Naive CR Gap Ratio")
    ax.set_title("EGP Level vs CR Gap")

    # ── Panel 6: Meal size effect ────────────────────────────────────────
    ax = axes[1, 2]
    # Scatter: carbs vs CR per method (from event-level data)
    methods_ev = [("cr_naive", "#e74c3c", "Naive"),
                  ("cr_full", "#2ecc71", "Multi-factor")]
    for m_col, m_color, m_label in methods_ev:
        ev_valid = ev_indep.dropna(subset=[m_col])
        if len(ev_valid) > 0:
            # Subsample if too many points
            if len(ev_valid) > 500:
                ev_sample = ev_valid.sample(500, random_state=42)
            else:
                ev_sample = ev_valid
            ax.scatter(ev_sample["carbs"], ev_sample[m_col],
                       c=m_color, s=10, alpha=0.3, label=m_label)

    # Add LOESS-like binned means
    for m_col, m_color, m_label in methods_ev:
        ev_valid = ev_indep.dropna(subset=[m_col])
        if len(ev_valid) >= 10:
            bins = pd.cut(ev_valid["carbs"], bins=10)
            bin_means = ev_valid.groupby(bins, observed=True)[m_col].median()
            bin_centers = [(b.left + b.right) / 2 for b in bin_means.index]
            ax.plot(bin_centers, bin_means.values, color=m_color, lw=2,
                    marker="o", markersize=4)

    ax.set_xlabel("Meal Size (g carbs)")
    ax.set_ylabel("CR (g/U)")
    ax.set_title("Meal Size vs CR")
    ax.legend(fontsize=7)

    # Annotate hypothesis verdicts
    h_labels = ["H1", "H2", "H3", "H4", "H5"]
    for i, (key, ax_idx) in enumerate(zip(h_labels, [(0, 0), (0, 1), (1, 0), (1, 1), (0, 2)])):
        r, c = ax_idx
        if i < len(h_results):
            vkey = f"h{i+1}_verdict"
            v = h_results[i].get(vkey, "SKIP")
            color = "green" if v == "PASS" else ("red" if v == "FAIL" else "gray")
            axes[r, c].text(0.02, 0.98, f"{key}: {v}",
                            transform=axes[r, c].transAxes,
                            fontsize=9, va="top", fontweight="bold",
                            color=color,
                            bbox=dict(boxstyle="round,pad=0.2",
                                      facecolor="white", alpha=0.8))

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = VIZ_DIR / "cr_multifactor.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Visualization: {out_path}")
    return str(out_path)


# ── Main entry point ─────────────────────────────────────────────────────────


def main():
    print("=" * 72)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 72)

    # ── Load ──
    grid, per_patient_egp, ctrl_map = load_data()

    # ── Extract meal events ──
    print("\nExtracting meal events...")
    ev_all = extract_meal_events(grid, per_patient_egp)
    if len(ev_all) == 0:
        print("ERROR: No meal events extracted. Exiting.")
        sys.exit(1)

    # ── Independence filter ──
    ev_all = filter_independent(ev_all)
    ev_indep = ev_all[ev_all["independent"]].copy()
    n_all = len(ev_all)
    n_indep = len(ev_indep)
    print(f"  All meal events:         {n_all:,}")
    print(f"  Independent meal events: {n_indep:,} "
          f"({100 * n_indep / max(n_all, 1):.1f}%)")
    print(f"  Patients with events:    {ev_indep['patient_id'].nunique()}")

    # ── Check valid CR counts per method ──
    methods_ev = ["cr_naive", "cr_egp", "cr_basal", "cr_full"]
    print("\n  Valid events per method (independent):")
    for m in methods_ev:
        n_valid = ev_indep[m].notna().sum()
        print(f"    {m}: {n_valid:,} / {n_indep:,} ({100*n_valid/max(n_indep,1):.1f}%)")

    # ── Per-patient aggregation ──
    print("\nAggregating per patient...")
    pt_df = compute_patient_summaries(ev_indep, per_patient_egp)

    if len(pt_df) == 0:
        print("ERROR: No patients with meal events. Exiting.")
        sys.exit(1)

    # ── Print summary table ──
    print("\n" + "=" * 72)
    print("  PER-PATIENT CR COMPARISON (EGP-SUBTRACTED)")
    print("=" * 72)
    display_cols = [
        "patient_id", "n_events", "profile_cr",
        "cr_naive_median", "cr_egp_median", "cr_basal_median", "cr_full_median",
        "cr_naive_gap_ratio", "cr_full_gap_ratio",
    ]
    show_cols = [c for c in display_cols if c in pt_df.columns]
    with pd.option_context(
        "display.max_rows", None,
        "display.max_columns", None,
        "display.width", 220,
        "display.float_format", "{:.2f}".format,
    ):
        print(pt_df[show_cols].to_string(index=False))

    # ── Decomposition summary ──
    print("\n" + "=" * 72)
    print("  DECOMPOSITION SUMMARY (population medians)")
    print("=" * 72)
    for col, label in [
        ("cr_naive_median", "M1: Naive CR"),
        ("cr_egp_median", "M2: EGP-subtracted CR"),
        ("cr_basal_median", "M3: Basal-subtracted CR"),
        ("cr_full_median", "M4: Multi-factor CR"),
        ("profile_cr", "M5: Profile CR"),
    ]:
        vals = pt_df[col].dropna()
        if len(vals) > 0:
            print(f"  {label:30s}: median={np.median(vals):.2f}, "
                  f"IQR=[{np.percentile(vals,25):.2f}, {np.percentile(vals,75):.2f}]")

    # ── Hypothesis tests ──
    h1_res = test_h1(pt_df)
    h2_res = test_h2(pt_df)
    h3_res = test_h3(pt_df)
    h4_res = test_h4(pt_df)
    h5_res = test_h5(pt_df)

    h_results = [h1_res, h2_res, h3_res, h4_res, h5_res]
    verdicts = {
        "H1_multifactor_30pct_closer": h1_res.get("h1_verdict", "SKIP"),
        "H2_egp_15pct_shift": h2_res.get("h2_verdict", "SKIP"),
        "H3_multifactor_lower_cv": h3_res.get("h3_verdict", "SKIP"),
        "H4_egp_gap_correlation": h4_res.get("h4_verdict", "SKIP"),
        "H5_within_50pct_profile": h5_res.get("h5_verdict", "SKIP"),
    }
    print(f"\n{'='*72}")
    print("  VERDICT SUMMARY")
    print(f"{'='*72}")
    for k, v in verdicts.items():
        status = "✓" if v == "PASS" else ("✗" if v == "FAIL" else "—")
        print(f"  [{status}] {k}: {v}")

    # ── Visualization ──
    print("\nGenerating visualizations...")
    viz_path = make_visualization(pt_df, ev_indep, h_results)

    # ── EGP component analysis ──
    print("\n" + "=" * 72)
    print("  EGP COMPONENT ANALYSIS")
    print("=" * 72)
    for _, row in pt_df.iterrows():
        pid = str(row["patient_id"])
        egp = row["median_egp"]
        egp_4h = egp * HORIZON_STEPS
        prof = row["profile_cr"]
        naive = safe_float(row.get("cr_naive_median"), np.nan)
        full = safe_float(row.get("cr_full_median"), np.nan)
        shift = full - naive if np.isfinite(full) and np.isfinite(naive) else np.nan
        print(f"  {pid[-12:]:>12s}: EGP={egp:+.4f}/step → "
              f"4h_contribution={egp_4h:+.1f} mg/dL | "
              f"CR naive={naive:.1f} → full={full:.1f} "
              f"(Δ={shift:+.1f}) | profile={prof:.1f}")

    # ── Assemble & save results ──
    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "predecessors": ["EXP-2729", "EXP-2740"],
        "parameters": {
            "horizon_steps": HORIZON_STEPS,
            "min_carbs_g": MIN_CARBS,
            "min_dose_u": MIN_DOSE,
            "min_gap_steps": MIN_GAP_STEPS,
            "bolus_coeff": BOLUS_COEFF,
            "smb_coeff": SMB_COEFF,
            "excess_basal_coeff": EXCESS_BASAL_COEFF,
            "mean_coeff": MEAN_COEFF,
            "min_carb_bg_impact": MIN_CARB_IMPACT,
            "cr_floor": CR_FLOOR,
            "cr_ceil": CR_CEIL,
        },
        "data_summary": {
            "n_patients_with_egp": len(per_patient_egp),
            "n_patients_with_events": int(pt_df["patient_id"].nunique()),
            "n_meal_events_all": n_all,
            "n_meal_events_independent": n_indep,
            "retention_pct": round(100 * n_indep / max(n_all, 1), 1),
            "valid_events_per_method": {
                m: int(ev_indep[m].notna().sum()) for m in methods_ev
            },
        },
        "methods": {
            "M1_naive": "glucose_rise - total_insulin*coeff; CR = ISF / (carb_impact / carbs)",
            "M2_egp_subtracted": "glucose_rise - total_insulin*coeff - EGP*48; CR = ISF / (adj_impact / carbs)",
            "M3_basal_subtracted": "glucose_rise - correction_insulin*coeff; basal≈EGP cancel",
            "M4_multifactor": "glucose_rise - correction*coeff - (EGP*48 + basal*coeff); full decomposition",
            "M5_profile": "scheduled_cr from pump profile settings",
        },
        "population_summary": {
            "median_profile_cr": round(float(pt_df["profile_cr"].median()), 2),
            "median_naive_cr": round(float(pt_df["cr_naive_median"].median()), 2),
            "median_egp_cr": round(float(pt_df["cr_egp_median"].median()), 2),
            "median_basal_cr": round(float(pt_df["cr_basal_median"].median()), 2),
            "median_full_cr": round(float(pt_df["cr_full_median"].median()), 2),
            "median_naive_gap": round(float(pt_df["cr_naive_gap_ratio"].dropna().median()), 3)
                if pt_df["cr_naive_gap_ratio"].notna().any() else None,
            "median_full_gap": round(float(pt_df["cr_full_gap_ratio"].dropna().median()), 3)
                if pt_df["cr_full_gap_ratio"].notna().any() else None,
        },
        "hypotheses": {
            "H1_multifactor_30pct_closer": h1_res,
            "H2_egp_15pct_shift": h2_res,
            "H3_multifactor_lower_cv": h3_res,
            "H4_egp_gap_correlation": h4_res,
            "H5_within_50pct_profile": h5_res,
        },
        "verdict_summary": verdicts,
        "per_patient": pt_df.replace({np.nan: None}).to_dict(orient="records"),
        "visualization": str(viz_path),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved: {OUT_JSON}")
    print(f"Visualization:  {viz_path}")


if __name__ == "__main__":
    main()
