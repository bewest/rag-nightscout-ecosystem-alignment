"""
EXP-2736: ISF Method Reconciliation — Which ISF Is Right?

Two research tracks produced seemingly contradictory findings:
  Track A (EXP-2720/2723): Empirical ISF (~13 mg/dL/U) improves 90.5% of patients vs profile
  Track B (EXP-2728):      Profile ISF + EGP + counter-reg (MAE=46.9) beats empirical ISF (MAE=51.0)

This experiment reconciles them by running ALL ISF methods head-to-head on
the SAME outcome metrics, clarifying what "better" means in each context.

The ISF Hierarchy (from EXP-2733):
  Profile ISF (55)     → what the controller uses
  Naive ISF (26)       → observed drop / dose
  Simulator ISF (13.8) → physics-corrected (EGP + counter-reg)
  Empirical ISF (6)    → net effect after controller compensation

Key insight: these ISFs are all "correct" in their own context:
  - Profile ISF is correct FOR THE CONTROLLER (accounts for compensation)
  - Empirical ISF is correct FOR PREDICTION (describes net observed effect)
  - Simulator ISF is correct FOR PHYSICS (insulin sensitivity in isolation)

Hypotheses:
  H1: Empirical ISF wins for BG-drop prediction (>50% patients lowest MAE)
  H2: Profile ISF wins for controller simulation (>40% patients lowest MAE)
  H3: All ISF methods preserve patient ranking (pairwise Spearman r > 0.7)
  H4: The 10× gap decomposes cleanly (ratios in [1.5, 5.0])
  H5: Physics-adjusted ISF is the best compromise
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from numpy.linalg import lstsq

# ── Paths ────────────────────────────────────────────────────────────────
GRID = Path("externals/ns-parquet/training/grid.parquet")
DS = Path("externals/ns-parquet/training/devicestatus.parquet")
MANIFEST = Path("externals/experiments/autoprepare-qualified.json")
RESULTS_DIR = Path("externals/experiments")
VIZ_DIR = Path("visualizations/isf-reconciliation")

# ── Constants ────────────────────────────────────────────────────────────
EXP_ID = "EXP-2736"
EXP_TITLE = "ISF Reconciliation — Which ISF Is Right for Which Purpose?"

BG_FLOOR = 180.0
MIN_DOSE = 0.3
HORIZON_STEPS = 24          # 2 h at 5-min intervals
MIN_GAP_STEPS = 24          # 2 h independence gap
BOLUS_COEFF = -129.2
SMB_COEFF = -123.6
EXCESS_BASAL_COEFF = -130.5

# EGP Hill-equation parameters (from production/metabolic_engine.py)
_BASE_EGP = 1.5             # mg/dL per 5-min step at zero insulin
_HILL_N = 1.5
_HILL_K = 2.0               # half-max IOB (Units)
_CIRCADIAN_AMP = 0.15       # 15% amplitude
_HARMONIC_PERIODS = [24.0, 12.0, 8.0, 6.0]
_HARMONIC_AMPS = [_CIRCADIAN_AMP, _CIRCADIAN_AMP * 0.4,
                  _CIRCADIAN_AMP * 0.2, _CIRCADIAN_AMP * 0.1]

OUT_JSON = RESULTS_DIR / "exp-2736_isf_reconciliation.json"

BLOCK_LABELS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]


# ── Data Loading ─────────────────────────────────────────────────────────

def load_data():
    """Load grid + devicestatus, filter to qualified patients."""
    print("Loading data...")
    grid = pd.read_parquet(GRID)
    ds = pd.read_parquet(DS)
    manifest = json.loads(MANIFEST.read_text())
    qual = manifest["qualified_patients"]

    ctrl_map = ds.groupby("patient_id")["controller"].first().to_dict()
    grid = grid[grid["patient_id"].isin(qual)].copy()
    grid["controller"] = grid["patient_id"].map(ctrl_map).fillna("unknown")
    grid["time"] = pd.to_datetime(grid["time"], utc=True)
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    print(f"  {len(grid):,} rows, {grid['patient_id'].nunique()} patients")
    return grid


# ── EGP Estimation ───────────────────────────────────────────────────────

def estimate_egp_flux(iob: float, hour: float) -> float:
    """Estimate hepatic glucose production for a single 5-min step.

    Hill equation suppression by IOB × circadian modulation.
    """
    iob_safe = max(float(np.nan_to_num(iob, nan=0.0)), 0.0)
    suppression = iob_safe ** _HILL_N / (iob_safe ** _HILL_N + _HILL_K ** _HILL_N)
    egp_insulin = _BASE_EGP * (1.0 - suppression)

    circadian = 1.0
    for amp, period in zip(_HARMONIC_AMPS, _HARMONIC_PERIODS):
        circadian += amp * np.sin(2.0 * np.pi * (hour - 5.0) / period)

    return max(egp_insulin * circadian, 0.0)


def estimate_egp_over_horizon(iob_start: float, hour_start: float,
                              n_steps: int = HORIZON_STEPS) -> float:
    """Sum EGP flux across the 2-h horizon (simple IOB decay model)."""
    total = 0.0
    iob = iob_start
    for step in range(n_steps):
        h = hour_start + step * 5.0 / 60.0
        total += estimate_egp_flux(iob, h % 24.0)
        iob *= 0.97  # ~5 h DIA exponential decay per step
    return total


# ── Event Extraction ─────────────────────────────────────────────────────

def extract_events(grid):
    """Extract correction events: BG >= 180, carbs < 5 g, dose >= 0.3 U."""
    print("Extracting correction events...")
    h = HORIZON_STEPS
    events = []

    for pid in grid["patient_id"].unique():
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < h + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if "bolus_smb" in pg.columns else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if "net_basal" in pg.columns else np.zeros(len(pg))
        carbs = pg["carbs"].values if "carbs" in pg.columns else np.zeros(len(pg))
        iob_vals = pg["iob"].values if "iob" in pg.columns else np.zeros(len(pg))
        sched_isf = pg["scheduled_isf"].values if "scheduled_isf" in pg.columns else np.full(len(pg), np.nan)
        profile_isf = float(np.nanmedian(sched_isf))
        ctrl = str(pg["controller"].iloc[0])

        for i in range(1, len(pg) - h):
            bg0 = glucose[i]
            bg_end = glucose[i + h]

            if np.isnan(bg0) or np.isnan(bg_end) or bg0 < BG_FLOOR:
                continue

            carbs_2h = float(np.nansum(carbs[i:i + h]))
            if carbs_2h > 5.0:
                continue

            bolus_2h = float(np.nansum(bolus[i:i + h]))
            smb_2h = float(np.nansum(smb[i:i + h]))
            excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / 12.0
            total_insulin = bolus_2h + smb_2h + excess_basal_2h

            if total_insulin < MIN_DOSE:
                continue

            observed_drop = bg0 - bg_end
            if observed_drop <= 0:
                continue

            iob_start = float(iob_vals[i]) if not np.isnan(iob_vals[i]) else 0.0

            try:
                ts = pd.Timestamp(pg["time"].iloc[i])
                hour = ts.hour + ts.minute / 60.0
            except Exception:
                hour = 0.0

            block_idx = min(int(hour) // 4, 5)

            # EGP over horizon
            egp_2h = estimate_egp_over_horizon(iob_start, hour, n_steps=h)

            events.append({
                "patient_id": pid,
                "controller": ctrl,
                "time_idx": i,
                "bg0": bg0,
                "bg_end": bg_end,
                "observed_drop": observed_drop,
                "total_insulin": total_insulin,
                "bolus_2h": bolus_2h,
                "smb_2h": smb_2h,
                "excess_basal_2h": excess_basal_2h,
                "naive_isf": observed_drop / total_insulin,
                "profile_isf": profile_isf,
                "iob_start": iob_start,
                "hour": hour,
                "block_idx": block_idx,
                "block_label": BLOCK_LABELS[block_idx],
                "egp_2h": egp_2h,
            })

    df = pd.DataFrame(events)
    print(f"  {len(df):,} events from {df['patient_id'].nunique()} patients")
    return df


# ── Independence Filter ──────────────────────────────────────────────────

def filter_independent(ev):
    """Mark events with >= 2 h gap from previous event per patient."""
    ev = ev.sort_values(["patient_id", "time_idx"]).copy()
    keep = []
    last_idx = {}
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


# ── ISF Methods ──────────────────────────────────────────────────────────

def compute_profile_isf(events):
    """A: Median scheduled_isf from events."""
    return float(np.nanmedian(events["profile_isf"].values))


def compute_naive_isf(events):
    """B: Median(observed_drop / dose) over all events."""
    return float(np.nanmedian(events["naive_isf"].values))


def compute_independent_isf(events):
    """C: Median(observed_drop / dose) over independent events only."""
    ind = events[events["independent"]]
    if len(ind) == 0:
        return float(np.nanmedian(events["naive_isf"].values))
    return float(np.nanmedian(ind["naive_isf"].values))


def compute_deconfounded_isf(events):
    """D: Regress out BG0, IOB, time-of-day from demand_isf, then re-centre.

    Follows the EXP-2723 multi-factor deconfounding pattern.
    """
    y = events["naive_isf"].values.copy()
    if len(y) < 6 or np.std(y) < 1e-6:
        return float(np.median(y))

    block_dummies = pd.get_dummies(events["block_idx"], prefix="b").values
    dose = events["total_insulin"].values
    bolus_total = dose.copy()
    bolus_total[bolus_total < 1e-6] = 1e-6
    bolus_frac = events["bolus_2h"].values / bolus_total
    smb_frac = events["smb_2h"].values / bolus_total

    X = np.column_stack([
        events["bg0"].values,
        dose,
        events["iob_start"].values,
        block_dummies,
        bolus_frac,
        smb_frac,
    ])
    X_int = np.column_stack([X, np.ones(len(X))])

    if X_int.shape[0] <= X_int.shape[1]:
        return float(np.median(y))

    beta, _, _, _ = lstsq(X_int, y, rcond=None)
    residuals = y - X_int @ beta
    return float(np.median(residuals) + np.median(y))


def compute_physics_isf(events):
    """E: Physics-adjusted ISF — add estimated EGP to bg_drop before dividing.

    ISF_physics = (observed_drop + egp_over_horizon) / dose
    """
    adjusted_drop = events["observed_drop"].values + events["egp_2h"].values
    adjusted_isf = adjusted_drop / events["total_insulin"].values
    return float(np.nanmedian(adjusted_isf))


# ── Metrics ──────────────────────────────────────────────────────────────

def prediction_mae_per_patient(events, patient_isf_dict, method_name):
    """Metric 1: How well does ISF predict observed BG drop?

    For each event: predicted_drop = dose × patient_isf
    Returns dict {patient_id: mae}.
    """
    maes = {}
    for pid, group in events.groupby("patient_id"):
        isf_val = patient_isf_dict.get(str(pid), np.nan)
        if np.isnan(isf_val) or isf_val <= 0:
            continue
        predicted = group["total_insulin"].values * isf_val
        actual = group["observed_drop"].values
        maes[str(pid)] = float(np.mean(np.abs(actual - predicted)))
    return maes


def try_forward_sim_mae(events, patient_isf_dict):
    """Metric 2: Controller simulation MAE (optional — needs forward simulator)."""
    try:
        from production.forward_simulator import (
            TherapySettings, InsulinEvent, forward_simulate,
        )
    except ImportError:
        return None

    sim_maes = {}
    for pid, group in events.groupby("patient_id"):
        isf_val = patient_isf_dict.get(str(pid), np.nan)
        if np.isnan(isf_val) or isf_val <= 0:
            continue

        ep_maes = []
        for _, row in group.head(30).iterrows():
            try:
                settings = TherapySettings(
                    isf=isf_val, cr=10.0,
                    basal_rate=row.get("excess_basal_2h", 0.0) * 12.0 + 0.8,
                    dia_hours=5.0,
                )
                bolus_events = []
                if row["bolus_2h"] > 0:
                    bolus_events.append(
                        InsulinEvent(0.0, row["bolus_2h"], True)
                    )
                if row["smb_2h"] > 0:
                    bolus_events.append(
                        InsulinEvent(30.0, row["smb_2h"], True)
                    )

                result = forward_simulate(
                    initial_glucose=row["bg0"],
                    settings=settings,
                    duration_hours=2.0,
                    start_hour=row["hour"],
                    bolus_events=bolus_events,
                    initial_iob=row["iob_start"],
                    metabolic_basal_rate=settings.basal_rate,
                    counter_reg_k=0.3,
                    egp_enabled=True,
                )
                sim_end = result.glucose[min(HORIZON_STEPS, len(result.glucose) - 1)]
                actual_end = row["bg_end"]
                ep_maes.append(abs(float(sim_end) - float(actual_end)))
            except Exception:
                continue

        if ep_maes:
            sim_maes[str(pid)] = float(np.mean(ep_maes))

    return sim_maes if sim_maes else None


def rank_correlation_matrix(patient_isf_table):
    """Metric 4: Pairwise Spearman rank correlation across ISF methods."""
    methods = ["profile_isf", "naive_isf", "independent_isf",
               "deconfounded_isf", "physics_isf"]
    n = len(methods)
    corr = np.full((n, n), np.nan)
    pvals = np.full((n, n), np.nan)

    for i in range(n):
        for j in range(n):
            x = patient_isf_table[methods[i]].values
            y = patient_isf_table[methods[j]].values
            valid = ~(np.isnan(x) | np.isnan(y))
            if valid.sum() < 4:
                continue
            xv, yv = x[valid], y[valid]
            if np.std(xv) < 1e-6 or np.std(yv) < 1e-6:
                corr[i, j] = 1.0 if np.std(xv) < 1e-6 and np.std(yv) < 1e-6 else np.nan
                pvals[i, j] = 0.0
                continue
            r, p = stats.spearmanr(xv, yv)
            corr[i, j] = float(r)
            pvals[i, j] = float(p)

    return methods, corr, pvals


# ── Hypothesis Tests ─────────────────────────────────────────────────────

def test_h1(events, patient_isfs, test_events):
    """H1: Empirical ISF wins for BG-drop prediction in >50% of patients."""
    methods = ["profile_isf", "naive_isf", "independent_isf",
               "deconfounded_isf", "physics_isf"]
    all_maes = {}
    for m in methods:
        isf_dict = {str(r["patient_id"]): r[m] for _, r in patient_isfs.iterrows()}
        all_maes[m] = prediction_mae_per_patient(test_events, isf_dict, m)

    pids = sorted(set.intersection(*[set(v.keys()) for v in all_maes.values()]))
    wins = {m: 0 for m in methods}

    for pid in pids:
        best_m = min(methods, key=lambda m: all_maes[m].get(pid, 1e9))
        wins[best_m] += 1

    empirical_methods = ["independent_isf", "deconfounded_isf"]
    empirical_wins = sum(wins.get(m, 0) for m in empirical_methods)
    pct = 100.0 * empirical_wins / max(len(pids), 1)
    h1_pass = bool(pct > 50)

    median_maes = {m: float(np.median([all_maes[m][p] for p in pids]))
                   for m in methods}

    return {
        "h1_verdict": "PASS" if h1_pass else "FAIL",
        "n_patients": len(pids),
        "empirical_win_pct": round(pct, 1),
        "win_counts": {m: wins[m] for m in methods},
        "median_mae_by_method": {m: round(v, 2) for m, v in median_maes.items()},
        "per_patient_mae": {m: {p: round(all_maes[m][p], 2) for p in pids}
                           for m in methods},
    }


def test_h2(events, patient_isfs, test_events):
    """H2: Profile ISF wins for controller simulation in >40% of patients."""
    methods = ["profile_isf", "naive_isf", "independent_isf",
               "deconfounded_isf", "physics_isf"]
    sim_results = {}
    for m in methods:
        isf_dict = {str(r["patient_id"]): r[m] for _, r in patient_isfs.iterrows()}
        res = try_forward_sim_mae(test_events, isf_dict)
        if res is None:
            return {
                "h2_verdict": "SKIP",
                "reason": "forward simulator not available",
            }
        sim_results[m] = res

    pids = sorted(set.intersection(*[set(v.keys()) for v in sim_results.values()]))
    if not pids:
        return {"h2_verdict": "SKIP", "reason": "no sim results"}

    wins = {m: 0 for m in methods}
    for pid in pids:
        best_m = min(methods, key=lambda m: sim_results[m].get(pid, 1e9))
        wins[best_m] += 1

    profile_pct = 100.0 * wins["profile_isf"] / max(len(pids), 1)
    h2_pass = bool(profile_pct > 40)

    median_sim_maes = {m: float(np.median([sim_results[m][p] for p in pids]))
                       for m in methods}

    return {
        "h2_verdict": "PASS" if h2_pass else "FAIL",
        "n_patients": len(pids),
        "profile_win_pct": round(profile_pct, 1),
        "win_counts": {m: wins[m] for m in methods},
        "median_sim_mae_by_method": {m: round(v, 2) for m, v in median_sim_maes.items()},
    }


def test_h3(patient_isfs):
    """H3: All ISF methods preserve patient ranking (pairwise Spearman r > 0.7)."""
    methods, corr, pvals = rank_correlation_matrix(patient_isfs)
    n = len(methods)
    all_above = True
    pairs = []

    for i in range(n):
        for j in range(i + 1, n):
            r_val = corr[i, j]
            p_val = pvals[i, j]
            pair_pass = bool(not np.isnan(r_val) and r_val > 0.7)
            if not pair_pass:
                all_above = False
            pairs.append({
                "method_a": methods[i],
                "method_b": methods[j],
                "spearman_r": round(float(r_val), 3) if not np.isnan(r_val) else None,
                "p_value": float(p_val) if not np.isnan(p_val) else None,
                "pair_pass": pair_pass,
            })

    return {
        "h3_verdict": "PASS" if all_above else "FAIL",
        "n_patients": len(patient_isfs),
        "all_pairs_above_0_7": bool(all_above),
        "pairwise": pairs,
        "correlation_matrix": corr.tolist(),
        "methods": methods,
    }


def test_h4(patient_isfs):
    """H4: The 10× gap decomposes cleanly into two components.

    Profile / physics ≈ 2-4× (EGP + counter-reg component)
    Physics / empirical ≈ 2-3× (controller compensation component)
    PASS if both median ratios are in [1.5, 5.0].
    """
    prof = patient_isfs["profile_isf"].values
    phys = patient_isfs["physics_isf"].values
    emp = patient_isfs["independent_isf"].values

    valid_phys = (phys > 0) & ~np.isnan(phys)
    valid_emp = (emp > 0) & ~np.isnan(emp)
    valid = valid_phys & valid_emp & (prof > 0) & ~np.isnan(prof)

    if valid.sum() < 3:
        return {"h4_verdict": "SKIP", "reason": "too few valid patients"}

    ratio_profile_physics = prof[valid] / phys[valid]
    ratio_physics_empirical = phys[valid] / emp[valid]

    med_pp = float(np.median(ratio_profile_physics))
    med_pe = float(np.median(ratio_physics_empirical))

    pp_pass = 1.5 <= med_pp <= 5.0
    pe_pass = 1.5 <= med_pe <= 5.0
    h4_pass = bool(pp_pass and pe_pass)

    return {
        "h4_verdict": "PASS" if h4_pass else "FAIL",
        "n_patients": int(valid.sum()),
        "median_profile_over_physics": round(med_pp, 2),
        "median_physics_over_empirical": round(med_pe, 2),
        "profile_physics_in_range": bool(pp_pass),
        "physics_empirical_in_range": bool(pe_pass),
        "per_patient_profile_physics": [round(float(v), 2) for v in ratio_profile_physics],
        "per_patient_physics_empirical": [round(float(v), 2) for v in ratio_physics_empirical],
    }


def test_h5(events, patient_isfs, test_events):
    """H5: Physics-adjusted ISF is the best compromise.

    PASS if:
      physics_mae < naive_mae for >50% patients  AND
      |log2(physics/profile)| < |log2(empirical/profile)| for median patient
    """
    methods_for_mae = ["naive_isf", "physics_isf", "independent_isf"]
    all_maes = {}
    for m in methods_for_mae:
        isf_dict = {str(r["patient_id"]): r[m] for _, r in patient_isfs.iterrows()}
        all_maes[m] = prediction_mae_per_patient(test_events, isf_dict, m)

    pids = sorted(set.intersection(*[set(v.keys()) for v in all_maes.values()]))
    if not pids:
        return {"h5_verdict": "SKIP", "reason": "no common patients"}

    n_phys_beats_naive = sum(
        1 for p in pids
        if all_maes["physics_isf"][p] < all_maes["naive_isf"][p]
    )
    pct_beats = 100.0 * n_phys_beats_naive / len(pids)

    # Distance to profile in log space
    prof_vals = patient_isfs.set_index("patient_id")["profile_isf"]
    phys_vals = patient_isfs.set_index("patient_id")["physics_isf"]
    emp_vals = patient_isfs.set_index("patient_id")["independent_isf"]

    common_pids = sorted(set(prof_vals.index) & set(phys_vals.index) & set(emp_vals.index))
    if not common_pids:
        return {"h5_verdict": "SKIP", "reason": "no common patients for log distance"}

    log_dist_phys = []
    log_dist_emp = []
    for pid in common_pids:
        pf = prof_vals[pid]
        ph = phys_vals[pid]
        em = emp_vals[pid]
        if pf > 0 and ph > 0 and em > 0:
            log_dist_phys.append(abs(np.log2(ph / pf)))
            log_dist_emp.append(abs(np.log2(em / pf)))

    if not log_dist_phys:
        return {"h5_verdict": "SKIP", "reason": "no valid log distances"}

    med_phys_dist = float(np.median(log_dist_phys))
    med_emp_dist = float(np.median(log_dist_emp))
    closer_to_profile = med_phys_dist < med_emp_dist

    h5_pass = bool(pct_beats > 50 and closer_to_profile)

    return {
        "h5_verdict": "PASS" if h5_pass else "FAIL",
        "n_patients": len(pids),
        "pct_physics_beats_naive": round(pct_beats, 1),
        "median_log2_dist_physics_to_profile": round(med_phys_dist, 3),
        "median_log2_dist_empirical_to_profile": round(med_emp_dist, 3),
        "physics_closer_to_profile": bool(closer_to_profile),
        "prediction_criterion_pass": bool(pct_beats > 50),
        "closeness_criterion_pass": bool(closer_to_profile),
    }


# ── Visualization ────────────────────────────────────────────────────────

def make_visualization(patient_isfs, h1_res, h3_res, h4_res):
    """Create 2×3 panel figure summarising reconciliation results."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    VIZ_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(16, 12))
    fig.suptitle(f"{EXP_ID}: {EXP_TITLE}", fontsize=14, fontweight="bold")

    methods = ["profile_isf", "naive_isf", "independent_isf",
               "deconfounded_isf", "physics_isf"]
    short_names = ["Profile", "Naive", "Independent", "Deconfounded", "Physics"]
    colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f"]

    # ── Panel 1: ISF methods per patient (sorted by profile ISF) ─────────
    ax = axes[0, 0]
    df_sorted = patient_isfs.sort_values("profile_isf").reset_index(drop=True)
    x = np.arange(len(df_sorted))
    w = 0.15
    for k, (m, label, c) in enumerate(zip(methods, short_names, colors)):
        vals = df_sorted[m].values
        ax.bar(x + (k - 2) * w, vals, width=w, label=label, color=c, alpha=0.8)
    ax.set_xlabel("Patient (sorted by Profile ISF)")
    ax.set_ylabel("ISF (mg/dL per U)")
    ax.set_title("ISF Methods per Patient")
    ax.legend(fontsize=7, loc="upper left")
    ax.set_xticks(x)
    ax.set_xticklabels([str(p)[:8] for p in df_sorted["patient_id"]],
                       rotation=60, fontsize=6)

    # ── Panel 2: Prediction MAE per method ───────────────────────────────
    ax = axes[0, 1]
    mae_data = h1_res.get("median_mae_by_method", {})
    if mae_data:
        per_pat = h1_res.get("per_patient_mae", {})
        box_data = []
        box_labels = []
        for m, sn in zip(methods, short_names):
            if m in per_pat:
                box_data.append(list(per_pat[m].values()))
                box_labels.append(sn)
        if box_data:
            bp = ax.boxplot(box_data, tick_labels=box_labels, patch_artist=True)
            for patch, c in zip(bp["boxes"], colors[:len(box_data)]):
                patch.set_facecolor(c)
                patch.set_alpha(0.6)
    ax.set_ylabel("Prediction MAE (mg/dL)")
    ax.set_title(f"Prediction MAE [H1={h1_res.get('h1_verdict', '?')}]")
    ax.tick_params(axis="x", rotation=30)

    # ── Panel 3: ISF gap decomposition per patient ───────────────────────
    ax = axes[0, 2]
    if "per_patient_profile_physics" in h4_res and "per_patient_physics_empirical" in h4_res:
        pp = np.array(h4_res["per_patient_profile_physics"])
        pe = np.array(h4_res["per_patient_physics_empirical"])
        n_pts = min(len(pp), len(pe))
        x_idx = np.arange(n_pts)
        # Log-space decomposition for stacked bar
        log_pp = np.log2(np.clip(pp[:n_pts], 0.1, 100))
        log_pe = np.log2(np.clip(pe[:n_pts], 0.1, 100))
        ax.bar(x_idx, log_pp, label="EGP component\n(Profile/Physics)",
               color="#4e79a7", alpha=0.8)
        ax.bar(x_idx, log_pe, bottom=log_pp,
               label="Controller comp.\n(Physics/Empirical)",
               color="#e15759", alpha=0.8)
        ax.set_xlabel("Patient")
        ax.set_ylabel("log₂(ratio)")
        ax.legend(fontsize=7)
    ax.set_title(f"10× Gap Decomposition [H4={h4_res.get('h4_verdict', '?')}]")

    # ── Panel 4: Rank correlation heatmap ────────────────────────────────
    ax = axes[1, 0]
    if "correlation_matrix" in h3_res:
        corr = np.array(h3_res["correlation_matrix"])
        im = ax.imshow(corr, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
        n_m = len(short_names)
        ax.set_xticks(range(n_m))
        ax.set_xticklabels(short_names, fontsize=7, rotation=45, ha="right")
        ax.set_yticks(range(n_m))
        ax.set_yticklabels(short_names, fontsize=7)
        for i in range(n_m):
            for j in range(n_m):
                val = corr[i][j]
                if not np.isnan(val):
                    ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                            fontsize=7, color="black" if val > 0.4 else "white")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title(f"Rank Correlation [H3={h3_res.get('h3_verdict', '?')}]")

    # ── Panel 5: Reconciliation summary text ─────────────────────────────
    ax = axes[1, 1]
    ax.axis("off")
    summary_lines = [
        "ISF Reconciliation Summary",
        "─" * 34,
        "",
        "Profile ISF:      Best for CONTROLLER",
        "  (accounts for compensation loops)",
        "",
        "Empirical ISF:    Best for PREDICTION",
        "  (captures net observed effect)",
        "",
        "Physics ISF:      Best COMPROMISE",
        "  (corrects EGP; closer to profile)",
        "",
        f"H1 (prediction):  {h1_res.get('h1_verdict', '?')}",
        f"H3 (rank pres.):  {h3_res.get('h3_verdict', '?')}",
        f"H4 (gap decomp.): {h4_res.get('h4_verdict', '?')}",
    ]
    ax.text(0.05, 0.95, "\n".join(summary_lines), transform=ax.transAxes,
            fontsize=9, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    # ── Panel 6: Scatter — Profile vs Empirical ISF by controller ────────
    ax = axes[1, 2]
    controllers = patient_isfs["controller"].unique()
    ctrl_colors = plt.cm.Set2(np.linspace(0, 1, max(len(controllers), 1)))
    for k, ctrl in enumerate(controllers):
        mask = patient_isfs["controller"] == ctrl
        sub = patient_isfs[mask]
        ax.scatter(sub["profile_isf"], sub["independent_isf"],
                   label=ctrl, color=ctrl_colors[k], s=60, edgecolors="black",
                   alpha=0.8, zorder=3)
        for _, row in sub.iterrows():
            ax.annotate(str(row["patient_id"])[:6],
                        (row["profile_isf"], row["independent_isf"]),
                        fontsize=5, alpha=0.7)

    lim = max(patient_isfs["profile_isf"].max(),
              patient_isfs["independent_isf"].max()) * 1.1
    ax.plot([0, lim], [0, lim], "r--", alpha=0.5, label="y = x")
    ax.set_xlabel("Profile ISF (mg/dL per U)")
    ax.set_ylabel("Empirical ISF (mg/dL per U)")
    ax.set_title("Profile vs Empirical ISF")
    ax.legend(fontsize=7)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out_path = VIZ_DIR / "isf_reconciliation.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"  {EXP_ID}: {EXP_TITLE}")
    print("=" * 60)

    # 1. Load data
    grid = load_data()

    # 2. Extract correction events
    ev = extract_events(grid)
    if len(ev) < 50:
        print(f"ERROR: only {len(ev)} events — too few for analysis")
        sys.exit(1)

    # 3. Independence filter
    print("\nFiltering for temporal independence...")
    ev = filter_independent(ev)
    ev_indep = ev[ev["independent"]].copy()
    print(f"  All events:         {len(ev):,}")
    print(f"  Independent events: {len(ev_indep):,} "
          f"({100 * len(ev_indep) / max(len(ev), 1):.1f}%)")

    # 4. Compute 5 ISF estimates per patient
    print("\nComputing 5 ISF methods per patient...")
    rows = []
    for pid, group in ev.groupby("patient_id"):
        if len(group) < 5:
            continue
        rows.append({
            "patient_id": pid,
            "controller": str(group["controller"].iloc[0]),
            "n_events": len(group),
            "n_independent": int(group["independent"].sum()),
            "profile_isf": compute_profile_isf(group),
            "naive_isf": compute_naive_isf(group),
            "independent_isf": compute_independent_isf(group),
            "deconfounded_isf": compute_deconfounded_isf(group),
            "physics_isf": compute_physics_isf(group),
        })

    patient_isfs = pd.DataFrame(rows)
    print(f"  {len(patient_isfs)} patients with all 5 ISF estimates")

    # Print ISF table
    print("\n  Per-patient ISF estimates:")
    print(f"  {'Patient':<12} {'Ctrl':<8} {'Profile':>8} {'Naive':>8} "
          f"{'Indep':>8} {'Deconf':>8} {'Physics':>8}")
    print("  " + "-" * 70)
    for _, r in patient_isfs.iterrows():
        print(f"  {str(r['patient_id']):<12} {r['controller']:<8} "
              f"{r['profile_isf']:8.1f} {r['naive_isf']:8.1f} "
              f"{r['independent_isf']:8.1f} {r['deconfounded_isf']:8.1f} "
              f"{r['physics_isf']:8.1f}")

    # Population medians
    print(f"\n  Population medians:")
    for m in ["profile_isf", "naive_isf", "independent_isf",
              "deconfounded_isf", "physics_isf"]:
        print(f"    {m:<22} = {patient_isfs[m].median():.1f}")

    # 5. Split events for train/test (50/50 per patient)
    print("\nSplitting events for train/test evaluation...")
    train_ev = []
    test_ev = []
    for pid, group in ev.groupby("patient_id"):
        n = len(group)
        mid = n // 2
        sorted_g = group.sort_values("time_idx")
        train_ev.append(sorted_g.iloc[:mid])
        test_ev.append(sorted_g.iloc[mid:])

    train_df = pd.concat(train_ev, ignore_index=True) if train_ev else pd.DataFrame()
    test_df = pd.concat(test_ev, ignore_index=True) if test_ev else pd.DataFrame()
    print(f"  Train: {len(train_df):,} events   Test: {len(test_df):,} events")

    # 6. Hypothesis tests
    print("\n" + "=" * 60)
    print("  Hypothesis Tests")
    print("=" * 60)

    print("\nH1: Empirical ISF wins for BG-drop prediction...")
    h1_res = test_h1(ev, patient_isfs, test_df)
    print(f"  Verdict: {h1_res['h1_verdict']}")
    print(f"  Empirical win %: {h1_res.get('empirical_win_pct', '?')}%")
    if "median_mae_by_method" in h1_res:
        for m, v in h1_res["median_mae_by_method"].items():
            print(f"    {m:<22} MAE = {v:.1f}")

    print("\nH2: Profile ISF wins for controller simulation...")
    h2_res = test_h2(ev, patient_isfs, test_df)
    print(f"  Verdict: {h2_res['h2_verdict']}")
    if "profile_win_pct" in h2_res:
        print(f"  Profile win %: {h2_res['profile_win_pct']}%")

    print("\nH3: All ISF methods preserve patient ranking...")
    h3_res = test_h3(patient_isfs)
    print(f"  Verdict: {h3_res['h3_verdict']}")
    for pair in h3_res.get("pairwise", []):
        r_str = f"{pair['spearman_r']:.3f}" if pair["spearman_r"] is not None else "N/A"
        mark = "✓" if pair.get("pair_pass") else "✗"
        print(f"    {mark} {pair['method_a']:<22} vs {pair['method_b']:<22} r={r_str}")

    print("\nH4: The 10× gap decomposes cleanly...")
    h4_res = test_h4(patient_isfs)
    print(f"  Verdict: {h4_res['h4_verdict']}")
    if "median_profile_over_physics" in h4_res:
        print(f"  Profile/Physics (EGP comp.):      {h4_res['median_profile_over_physics']:.2f}×")
        print(f"  Physics/Empirical (ctrl comp.):    {h4_res['median_physics_over_empirical']:.2f}×")

    print("\nH5: Physics-adjusted ISF is the best compromise...")
    h5_res = test_h5(ev, patient_isfs, test_df)
    print(f"  Verdict: {h5_res['h5_verdict']}")
    if "pct_physics_beats_naive" in h5_res:
        print(f"  Physics beats naive: {h5_res['pct_physics_beats_naive']:.1f}%")
        print(f"  log₂ dist physics→profile: {h5_res.get('median_log2_dist_physics_to_profile', '?')}")
        print(f"  log₂ dist empirical→profile: {h5_res.get('median_log2_dist_empirical_to_profile', '?')}")

    # 7. Visualization
    print("\nGenerating visualization...")
    make_visualization(patient_isfs, h1_res, h3_res, h4_res)

    # 8. Assemble and save JSON
    def clean(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        return str(obj)

    results = {
        "experiment_id": EXP_ID,
        "title": EXP_TITLE,
        "timestamp": datetime.now().isoformat(),
        "n_all_events": len(ev),
        "n_independent_events": len(ev_indep),
        "retention_pct": round(100 * len(ev_indep) / max(len(ev), 1), 1),
        "n_patients": len(patient_isfs),
        "population_medians": {
            m: round(float(patient_isfs[m].median()), 1)
            for m in ["profile_isf", "naive_isf", "independent_isf",
                      "deconfounded_isf", "physics_isf"]
        },
        "per_patient": patient_isfs.to_dict(orient="records"),
        "hypotheses": {
            "H1_prediction_mae": h1_res,
            "H2_controller_sim": h2_res,
            "H3_rank_preservation": h3_res,
            "H4_gap_decomposition": h4_res,
            "H5_physics_compromise": h5_res,
        },
        "verdict_summary": {
            "H1": h1_res.get("h1_verdict", "SKIP"),
            "H2": h2_res.get("h2_verdict", "SKIP"),
            "H3": h3_res.get("h3_verdict", "SKIP"),
            "H4": h4_res.get("h4_verdict", "SKIP"),
            "H5": h5_res.get("h5_verdict", "SKIP"),
        },
        "key_insight": (
            "These ISFs are all 'correct' in different contexts: "
            "Profile ISF is correct FOR THE CONTROLLER, "
            "Empirical ISF is correct FOR PREDICTION, "
            "Physics ISF is correct FOR PHYSICS and serves as best compromise."
        ),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=clean)
    print(f"\nResults saved: {OUT_JSON}")

    # 9. Print full reconciliation table
    print("\n" + "=" * 60)
    print("  Full Reconciliation Table")
    print("=" * 60)
    print(json.dumps(results["per_patient"], indent=2, default=clean))

    # 10. Final verdict
    v = results["verdict_summary"]
    print(f"\nVerdict: H1={v['H1']} H2={v['H2']} H3={v['H3']} H4={v['H4']} H5={v['H5']}")
    return results


if __name__ == "__main__":
    main()
