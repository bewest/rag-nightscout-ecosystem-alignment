#!/usr/bin/env python3
"""
EXP-2719: Extended Multi-Factor Waterfall — Systematic Subtraction Pipeline
=============================================================================

Instead of inventing ad-hoc ISF extraction (which EXP-2717/2717b/2718 showed
fails in closed-loop), this experiment EXTENDS the validated 5-stage waterfall
(EXP-2698) with additional subtraction stages and multiple time horizons.

The oref0 principle: don't try to DIVIDE (ISF = drop/dose, which is confounded).
Instead, SUBTRACT what you know at each stage. Measure what's LEFT (the residual).
If the residual shrinks, you correctly identified a confounding factor.
If the residual has structure, there's more to subtract.

Extended Waterfall Stages (each stage subtracts one confound):
  Stage 0: Raw observed BG drop (baseline)
  Stage 1: - Scheduled basal effect (maintenance insulin counterbalancing EGP)
  Stage 2: - Bolus + SMB BGI (oref0-style, existing infrastructure)
  Stage 3: - BG₀ proportional response (controller dosing confound)
  Stage 4: - EGP headwind (hepatic production opposing insulin)
  Stage 5: - Circadian variation (time-of-day effects)
  Stage 6: - Within-patient fixed effects (between-patient heterogeneity)
  Stage 7: - Autocorrelation (non-independent events, from EXP-2714)

At each stage we measure:
  - R² increment (variance explained by this factor)
  - Coefficient stability (does it match known physics?)
  - Residual structure (should become more like white noise)
  - Cross-validation (does subtraction generalize to holdout?)

Run at horizons: 1h, 2h, 3h, 4h, 6h to see how each factor's contribution
changes with timescale. This directly answers: which factors matter WHEN?

Causal frame: In T1D, insulin is the ONLY glucose-lowering mechanism.
Everything else either RAISES glucose (EGP) or MODULATES insulin effect
(glycogen state, circadian, exercise). The waterfall subtracts known
effects to isolate what's unexplained.
"""

from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from production.deconfounding import (
    BGISubtraction,
    ExperimentFilters,
    BOLUS_COEFF,
    SMB_COEFF,
    EXCESS_BASAL_COEFF,
    STEPS_PER_HOUR,
)

# ── Constants ────────────────────────────────────────────────────────

EXP_ID = "2719"
TITLE = "Extended Multi-Factor Waterfall — Systematic Subtraction Pipeline"

HORIZONS = [2, 4, 6]  # hours — key timescales (demand phase, mid, full DIA)
BG_FLOOR = 150.0

# EGP model (from metabolic_engine.py)
HILL_N = 1.5
HILL_K = 2.0
BASE_EGP = 1.5  # mg/dL per 5-min step
CIRCADIAN_AMP = 0.15

# Independence gap for autocorrelation correction
INDEPENDENCE_GAP_STEPS = 24  # 2 hours


# ── Helpers ──────────────────────────────────────────────────────────

@dataclass
class StageResult:
    """Result of one waterfall subtraction stage."""
    name: str
    r2: float
    n: int
    delta_r2: float
    residual_std: float
    coefficients: Dict[str, float] = field(default_factory=dict)
    interpretation: str = ""


def ols_r2(X: np.ndarray, y: np.ndarray, names: List[str]) -> Tuple[float, Dict[str, float]]:
    """OLS regression returning R² and coefficients."""
    mask = ~np.isnan(y)
    for j in range(X.shape[1]):
        mask &= ~np.isnan(X[:, j])
    X_c = X[mask]
    y_c = y[mask]
    n = len(y_c)
    if n < 30:
        return np.nan, {}

    X_aug = np.column_stack([X_c, np.ones(n)])
    try:
        b, _, _, _ = np.linalg.lstsq(X_aug, y_c, rcond=None)
    except np.linalg.LinAlgError:
        return np.nan, {}

    y_pred = X_aug @ b
    ss_res = np.sum((y_c - y_pred) ** 2)
    ss_tot = np.sum((y_c - y_c.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    coefs = {names[i]: float(b[i]) for i in range(len(names))}
    coefs["intercept"] = float(b[-1])
    return r2, coefs


def estimate_egp_per_step(iob: float, hour: float) -> float:
    """Hepatic glucose production (mg/dL per 5-min step)."""
    iob_safe = max(float(np.nan_to_num(iob, nan=0.0)), 0.0)
    if iob_safe > 0:
        suppression = iob_safe ** HILL_N / (iob_safe ** HILL_N + HILL_K ** HILL_N)
    else:
        suppression = 0.0
    egp_base = BASE_EGP * (1.0 - suppression)

    periods = [24.0, 12.0, 8.0, 6.0]
    amps = [CIRCADIAN_AMP, CIRCADIAN_AMP * 0.4, CIRCADIAN_AMP * 0.2, CIRCADIAN_AMP * 0.1]
    circadian = 1.0
    for amp, period in zip(amps, periods):
        circadian += amp * np.sin(2.0 * np.pi * (hour - 5.0) / period)
    return max(egp_base * circadian, 0.0)


# ── Event extraction with multi-horizon metrics ─────────────────────

def extract_events(grid: pd.DataFrame) -> pd.DataFrame:
    """Extract correction events with per-horizon insulin and BG metrics."""

    has_smb = "bolus_smb" in grid.columns
    has_net_basal = "net_basal" in grid.columns
    has_sched_basal = "scheduled_basal_rate" in grid.columns
    has_iob = "iob" in grid.columns
    has_isf = "scheduled_isf" in grid.columns
    has_controller = "controller" in grid.columns

    max_h_steps = int(max(HORIZONS) * STEPS_PER_HOUR)
    all_events = []

    for pid in sorted(grid["patient_id"].unique()):
        pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if len(pg) < max_h_steps + 2:
            continue

        glucose = pg["glucose"].values
        bolus = pg["bolus"].values
        smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
        net_basal = pg["net_basal"].values if has_net_basal else np.zeros(len(pg))
        sched_basal = pg["scheduled_basal_rate"].values if has_sched_basal else np.zeros(len(pg))
        iob = pg["iob"].values if has_iob else np.full(len(pg), np.nan)
        profile_isf = pg["scheduled_isf"].values if has_isf else np.full(len(pg), np.nan)
        controller = pg["controller"].iloc[0] if has_controller else "unknown"

        hours = np.zeros(len(pg))
        try:
            times = pd.to_datetime(pg["time"])
            hours = (times.dt.hour + times.dt.minute / 60.0).values
        except Exception:
            pass

        for i in range(len(pg) - max_h_steps):
            bg0 = glucose[i]
            if np.isnan(bg0) or bg0 < BG_FLOOR or bolus[i] < 0.1:
                continue

            # Carb-free check
            if "carbs" in pg.columns:
                c_start = max(0, i - STEPS_PER_HOUR)
                c_end = min(len(pg), i + 2 * STEPS_PER_HOUR)
                if np.nansum(pg["carbs"].values[c_start:c_end]) > 0:
                    continue

            event = {
                "patient_id": pid,
                "controller": controller,
                "idx": i,
                "bg0": bg0,
                "hour": float(hours[i]),
                "roc_start": float((glucose[i] - glucose[max(0, i - 3)]) / 3 * STEPS_PER_HOUR) if i >= 3 else 0.0,
                "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                "profile_isf": float(profile_isf[i]) if not np.isnan(profile_isf[i]) else np.nan,
                "user_bolus": float(bolus[i]),
            }

            for h in HORIZONS:
                h_steps = int(h * STEPS_PER_HOUR)
                end_idx = i + h_steps
                bg_end = glucose[end_idx]
                if np.isnan(bg_end):
                    continue

                hk = f"{h}h"

                # Raw BG drop (the thing we're trying to explain)
                observed_drop = bg0 - bg_end
                event[f"observed_drop_{hk}"] = float(observed_drop)

                # ── Factor 1: Scheduled basal effect ─────────────────
                # Maintenance insulin: sched_basal × ISF × fraction_absorbed
                sched_total = float(np.nansum(sched_basal[i:end_idx])) / STEPS_PER_HOUR
                isf_val = float(profile_isf[i]) if not np.isnan(profile_isf[i]) else 50.0
                # At steady state, basal exactly counterbalances EGP → net effect ≈ 0
                # But we track it for bookkeeping
                event[f"sched_basal_{hk}"] = sched_total
                event[f"basal_bgi_{hk}"] = sched_total * isf_val  # Expected BG lowering from basal

                # ── Factor 2: Correction insulin BGI ─────────────────
                # Excess insulin above basal: bolus + SMB + net_basal
                bolus_total = float(np.nansum(bolus[i:end_idx]))
                smb_total = float(np.nansum(smb[i:end_idx]))
                net_basal_total = float(np.nansum(net_basal[i:end_idx])) / STEPS_PER_HOUR
                excess_insulin = bolus_total + smb_total + net_basal_total

                # BGI = excess × coefficient (from EXP-2698)
                # Use channel-specific coefficients for accuracy
                bgi_bolus = bolus_total * abs(BOLUS_COEFF) / isf_val  # Convert to dose-equivalent
                bgi_smb = smb_total * abs(SMB_COEFF) / isf_val
                bgi_excess_basal = net_basal_total * abs(EXCESS_BASAL_COEFF) / isf_val
                # Simpler: use flat coefficient since all channels ≈ equal
                expected_drop_bgi = excess_insulin * isf_val

                event[f"excess_insulin_{hk}"] = excess_insulin
                event[f"expected_drop_bgi_{hk}"] = expected_drop_bgi

                # ── Factor 3: BG₀ proportional response ──────────────
                # The controller delivers more insulin when BG is higher
                # This creates a confound: bg0 → insulin → drop
                # We model this as: bg0_effect = α × (bg0 - 120)
                # (Coefficient will be fit from data)
                event[f"bg0_centered_{hk}"] = bg0 - 120.0

                # ── Factor 4: EGP headwind ───────────────────────────
                # Hepatic glucose production opposes insulin
                egp_total = 0.0
                for k in range(h_steps):
                    iob_k = float(iob[i + k]) if not np.isnan(iob[i + k]) else 0.0
                    hour_k = float(hours[i + k]) if i + k < len(hours) else hours[i]
                    egp_total += estimate_egp_per_step(iob_k, hour_k)
                event[f"egp_headwind_{hk}"] = egp_total

                # ── Factor 5: Circadian (hour block) ─────────────────
                # Already captured by hour, will use hour blocks in regression

                # ── Factor 6: IOB at start (prior insulin) ───────────
                # Already in event["iob_start"]

            all_events.append(event)

    return pd.DataFrame(all_events)


# ── Progressive subtraction waterfall ────────────────────────────────

def run_waterfall(df: pd.DataFrame, horizon: int) -> List[StageResult]:
    """Run 7-stage progressive subtraction waterfall at a given horizon."""

    hk = f"{horizon}h"
    drop_col = f"observed_drop_{hk}"
    if drop_col not in df.columns:
        return []

    valid = df.dropna(subset=[drop_col])
    y_raw = valid[drop_col].values
    n = len(valid)
    if n < 100:
        return []

    stages = []
    prev_r2 = 0.0
    residual = y_raw.copy()

    print(f"\n  === Waterfall at {hk} (N={n}) ===")

    # ── Stage 0: Baseline ────────────────────────────────────────
    baseline_std = float(np.std(y_raw))
    stages.append(StageResult(
        name="S0_raw_drop",
        r2=0.0,
        n=n,
        delta_r2=0.0,
        residual_std=baseline_std,
        interpretation=f"Raw BG drop: mean={np.mean(y_raw):.1f}, std={baseline_std:.1f}"
    ))
    print(f"    S0 raw:    R²=0.000, σ={baseline_std:.1f}")

    # ── Stage 1: Subtract excess insulin BGI ─────────────────────
    bgi_col = f"expected_drop_bgi_{hk}"
    if bgi_col in valid.columns:
        bgi_vals = valid[bgi_col].values
        bgi_vals = np.nan_to_num(bgi_vals, nan=0.0)
        residual_1 = y_raw - bgi_vals  # deviation = observed - expected

        # R² of BGI prediction
        ss_res = np.sum(residual_1 ** 2)
        ss_tot = np.sum((y_raw - y_raw.mean()) ** 2)
        r2_1 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        std_1 = float(np.std(residual_1))

        stages.append(StageResult(
            name="S1_subtract_bgi",
            r2=r2_1,
            n=n,
            delta_r2=r2_1 - prev_r2,
            residual_std=std_1,
            coefficients={"bgi_mean": float(np.mean(bgi_vals))},
            interpretation=f"Subtract BGI (excess insulin × ISF): Δ={r2_1 - prev_r2:+.4f}"
        ))
        print(f"    S1 -BGI:   R²={r2_1:.4f} (+{r2_1 - prev_r2:.4f}), σ={std_1:.1f}")
        residual = residual_1
        prev_r2 = r2_1
    else:
        residual_1 = residual

    # ── Stage 2: Subtract EGP headwind ───────────────────────────
    egp_col = f"egp_headwind_{hk}"
    if egp_col in valid.columns:
        egp_vals = valid[egp_col].values
        egp_vals = np.nan_to_num(egp_vals, nan=0.0)
        # EGP RAISES glucose, so it reduces the observed drop
        # deviation_2 = deviation_1 + egp (add back what EGP prevented)
        residual_2 = residual + egp_vals

        # But wait — to measure R², we need to ask: does accounting for EGP
        # reduce variance in the residual RELATIVE to the original drop?
        ss_res_2 = np.sum((y_raw - (valid[bgi_col].values - egp_vals)) ** 2) if bgi_col in valid.columns else np.sum(residual_2 ** 2)
        # Better approach: use regression to fit EGP coefficient optimally
        X_egp = np.column_stack([
            valid[f"excess_insulin_{hk}"].values if f"excess_insulin_{hk}" in valid.columns else np.zeros(n),
            egp_vals,
        ])
        r2_2, coefs_2 = ols_r2(X_egp, y_raw, ["excess_insulin", "egp_headwind"])
        std_2 = float(np.std(y_raw - X_egp @ np.array([coefs_2.get("excess_insulin", 0),
                                                          coefs_2.get("egp_headwind", 0)]))) if coefs_2 else float(np.std(residual_2))

        stages.append(StageResult(
            name="S2_subtract_egp",
            r2=r2_2 if not np.isnan(r2_2) else prev_r2,
            n=n,
            delta_r2=(r2_2 - prev_r2) if not np.isnan(r2_2) else 0.0,
            residual_std=std_2,
            coefficients=coefs_2,
            interpretation=f"Add EGP headwind: Δ={r2_2 - prev_r2:+.4f}" if not np.isnan(r2_2) else "EGP: no improvement"
        ))
        print(f"    S2 +EGP:   R²={r2_2:.4f} (+{r2_2 - prev_r2:+.4f}), σ={std_2:.1f}, "
              f"coefs: ins={coefs_2.get('excess_insulin', 0):.2f}, egp={coefs_2.get('egp_headwind', 0):.3f}")
        prev_r2 = r2_2 if not np.isnan(r2_2) else prev_r2

    # ── Stage 3: Add BG₀ (controller proportional dosing) ────────
    bg0_col = f"bg0_centered_{hk}"
    if bg0_col in valid.columns:
        X_3 = np.column_stack([
            valid[f"excess_insulin_{hk}"].values if f"excess_insulin_{hk}" in valid.columns else np.zeros(n),
            valid[egp_col].values if egp_col in valid.columns else np.zeros(n),
            valid[bg0_col].values,
        ])
        r2_3, coefs_3 = ols_r2(X_3, y_raw, ["excess_insulin", "egp_headwind", "bg0_centered"])

        stages.append(StageResult(
            name="S3_add_bg0",
            r2=r2_3 if not np.isnan(r2_3) else prev_r2,
            n=n,
            delta_r2=(r2_3 - prev_r2) if not np.isnan(r2_3) else 0.0,
            residual_std=0.0,
            coefficients=coefs_3,
            interpretation=f"Add BG₀ controller confound: Δ={r2_3 - prev_r2:+.4f}" if not np.isnan(r2_3) else "BG₀: no change"
        ))
        bg0_coef = coefs_3.get("bg0_centered", 0)
        print(f"    S3 +BG₀:   R²={r2_3:.4f} (+{r2_3 - prev_r2:+.4f}), "
              f"bg0_coef={bg0_coef:.4f} (1.0=pure regression to mean)")
        prev_r2 = r2_3 if not np.isnan(r2_3) else prev_r2

    # ── Stage 4: Add ROC + IOB (dynamic state) ───────────────────
    roc_available = "roc_start" in valid.columns
    iob_available = "iob_start" in valid.columns
    feature_names_4 = ["excess_insulin", "egp_headwind", "bg0_centered"]
    X_cols_4 = [
        valid[f"excess_insulin_{hk}"].values if f"excess_insulin_{hk}" in valid.columns else np.zeros(n),
        valid[egp_col].values if egp_col in valid.columns else np.zeros(n),
        valid[bg0_col].values if bg0_col in valid.columns else np.zeros(n),
    ]
    if roc_available:
        X_cols_4.append(valid["roc_start"].values)
        feature_names_4.append("roc_start")
    if iob_available:
        X_cols_4.append(valid["iob_start"].values)
        feature_names_4.append("iob_start")

    X_4 = np.column_stack(X_cols_4)
    r2_4, coefs_4 = ols_r2(X_4, y_raw, feature_names_4)

    stages.append(StageResult(
        name="S4_add_dynamic_state",
        r2=r2_4 if not np.isnan(r2_4) else prev_r2,
        n=n,
        delta_r2=(r2_4 - prev_r2) if not np.isnan(r2_4) else 0.0,
        residual_std=0.0,
        coefficients=coefs_4,
        interpretation=f"Add ROC + IOB: Δ={r2_4 - prev_r2:+.4f}" if not np.isnan(r2_4) else "No change"
    ))
    print(f"    S4 +state: R²={r2_4:.4f} (+{r2_4 - prev_r2:+.4f})")
    prev_r2 = r2_4 if not np.isnan(r2_4) else prev_r2

    # ── Stage 5: Circadian blocks (6 × 4h blocks) ────────────────
    if "hour" in valid.columns:
        block_size = 4  # 4-hour blocks
        hour_blocks = (valid["hour"].values // block_size).astype(int)
        # One-hot encode (drop first for identifiability)
        block_dummies = []
        block_names_extra = []
        for b in range(1, 6):
            block_dummies.append((hour_blocks == b).astype(float))
            block_names_extra.append(f"block_{b}")

        X_5 = np.column_stack(X_cols_4 + block_dummies)
        feature_names_5 = feature_names_4 + block_names_extra
        r2_5, coefs_5 = ols_r2(X_5, y_raw, feature_names_5)

        stages.append(StageResult(
            name="S5_add_circadian",
            r2=r2_5 if not np.isnan(r2_5) else prev_r2,
            n=n,
            delta_r2=(r2_5 - prev_r2) if not np.isnan(r2_5) else 0.0,
            residual_std=0.0,
            coefficients=coefs_5,
            interpretation=f"Add circadian blocks: Δ={r2_5 - prev_r2:+.4f}" if not np.isnan(r2_5) else "No change"
        ))
        print(f"    S5 +circ:  R²={r2_5:.4f} (+{r2_5 - prev_r2:+.4f})")
        prev_r2 = r2_5 if not np.isnan(r2_5) else prev_r2
    else:
        X_5, feature_names_5 = X_4, feature_names_4

    # ── Stage 6: Within-patient fixed effects ────────────────────
    if "patient_id" in valid.columns:
        patients = valid["patient_id"].unique()
        if len(patients) > 2:
            pat_dummies = []
            pat_names = []
            for p in patients[1:]:  # Drop first for identifiability
                pat_dummies.append((valid["patient_id"].values == p).astype(float))
                pat_names.append(f"pat_{p[:6]}")

            X_6 = np.column_stack(list(X_5.T if hasattr(X_5, 'T') and len(X_5.shape) > 1 else [X_5]) + pat_dummies)
            feature_names_6 = feature_names_5 + pat_names
            r2_6, coefs_6 = ols_r2(X_6, y_raw, feature_names_6)

            stages.append(StageResult(
                name="S6_within_patient_fe",
                r2=r2_6 if not np.isnan(r2_6) else prev_r2,
                n=n,
                delta_r2=(r2_6 - prev_r2) if not np.isnan(r2_6) else 0.0,
                residual_std=0.0,
                coefficients={k: v for k, v in (coefs_6 or {}).items() if not k.startswith("pat_")},
                interpretation=f"Within-patient FE: Δ={r2_6 - prev_r2:+.4f}" if not np.isnan(r2_6) else "No change"
            ))
            print(f"    S6 +FE:    R²={r2_6:.4f} (+{r2_6 - prev_r2:+.4f})")
            prev_r2 = r2_6 if not np.isnan(r2_6) else prev_r2

    # ── Stage 7: Independence correction (subsample) ─────────────
    independent = []
    for pid in valid["patient_id"].unique():
        pvf = valid[valid["patient_id"] == pid].sort_values("idx")
        last_idx = -999
        for _, row in pvf.iterrows():
            if row["idx"] - last_idx >= INDEPENDENCE_GAP_STEPS:
                independent.append(row)
                last_idx = row["idx"]

    if len(independent) > 100:
        idf = pd.DataFrame(independent)
        n_ind = len(idf)
        compression = n / n_ind

        # Re-run Stage 4 model on independent subset
        X_ind = np.column_stack([
            idf[f"excess_insulin_{hk}"].values if f"excess_insulin_{hk}" in idf.columns else np.zeros(n_ind),
            idf[egp_col].values if egp_col in idf.columns else np.zeros(n_ind),
            idf[bg0_col].values if bg0_col in idf.columns else np.zeros(n_ind),
        ])
        if roc_available:
            X_ind = np.column_stack([X_ind, idf["roc_start"].values])
        if iob_available:
            X_ind = np.column_stack([X_ind, idf["iob_start"].values])

        y_ind = idf[drop_col].values
        r2_ind, coefs_ind = ols_r2(X_ind, y_ind, feature_names_4)

        stages.append(StageResult(
            name="S7_independence_corrected",
            r2=r2_ind if not np.isnan(r2_ind) else 0.0,
            n=n_ind,
            delta_r2=0.0,
            residual_std=0.0,
            coefficients=coefs_ind,
            interpretation=(f"Independence: {n_ind} episodes ({compression:.1f}× compression). "
                           f"R²={r2_ind:.4f} vs full={prev_r2:.4f}")
        ))
        print(f"    S7 indep:  R²={r2_ind:.4f} (N={n_ind}, {compression:.1f}× compression)")

    return stages


# ── Cross-validation ────────────────────────────────────────────────

def cross_validate(df: pd.DataFrame, horizon: int) -> Dict:
    """70/30 holdout validation of the multi-factor model."""
    hk = f"{horizon}h"
    drop_col = f"observed_drop_{hk}"
    exc_col = f"excess_insulin_{hk}"
    egp_col = f"egp_headwind_{hk}"
    bg0_col = f"bg0_centered_{hk}"

    needed = [drop_col, exc_col, egp_col, bg0_col, "roc_start", "iob_start"]
    valid = df.dropna(subset=[c for c in needed if c in df.columns])
    if len(valid) < 100:
        return {}

    # Split by patient (not random) for proper generalization test
    patients = valid["patient_id"].unique()
    np.random.seed(42)
    np.random.shuffle(patients)
    split = int(0.7 * len(patients))
    train_pats = set(patients[:split])
    test_pats = set(patients[split:])

    train = valid[valid["patient_id"].isin(train_pats)]
    test = valid[valid["patient_id"].isin(test_pats)]

    if len(train) < 50 or len(test) < 50:
        return {}

    features = [exc_col, egp_col, bg0_col]
    if "roc_start" in valid.columns:
        features.append("roc_start")
    if "iob_start" in valid.columns:
        features.append("iob_start")

    X_train = train[features].values
    y_train = train[drop_col].values
    X_test = test[features].values
    y_test = test[drop_col].values

    # Fit on train
    X_aug = np.column_stack([X_train, np.ones(len(X_train))])
    try:
        b, _, _, _ = np.linalg.lstsq(X_aug, y_train, rcond=None)
    except Exception:
        return {}

    # Evaluate on test
    X_test_aug = np.column_stack([X_test, np.ones(len(X_test))])
    y_pred = X_test_aug @ b

    ss_res = np.sum((y_test - y_pred) ** 2)
    ss_tot = np.sum((y_test - y_test.mean()) ** 2)
    r2_test = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    mae_test = float(np.mean(np.abs(y_test - y_pred)))

    # Baseline: just mean
    mae_baseline = float(np.mean(np.abs(y_test - y_test.mean())))

    return {
        "r2_train": float(ols_r2(X_train, y_train, features)[0]),
        "r2_test": float(r2_test),
        "mae_test": mae_test,
        "mae_baseline": mae_baseline,
        "mae_reduction": float(1 - mae_test / mae_baseline) if mae_baseline > 0 else 0,
        "n_train": len(train),
        "n_test": len(test),
        "n_train_patients": len(train_pats),
        "n_test_patients": len(test_pats),
    }


# ── Main analysis ───────────────────────────────────────────────────

def main():
    print(f"{'=' * 70}")
    print(f"EXP-{EXP_ID}: {TITLE}")
    print(f"{'=' * 70}")

    data_path = Path(__file__).resolve().parent.parent.parent / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"\nLoading {data_path}...")
    grid = pd.read_parquet(data_path)
    print(f"  {grid.shape[0]} rows × {grid.shape[1]} cols, {grid['patient_id'].nunique()} patients")

    print(f"\nExtracting events...")
    df = extract_events(grid)
    print(f"  {len(df)} events, {df['patient_id'].nunique()} patients")

    # Run waterfall at each horizon
    all_waterfalls = {}
    for h in HORIZONS:
        stages = run_waterfall(df, h)
        all_waterfalls[f"{h}h"] = [{"name": s.name, "r2": s.r2, "delta_r2": s.delta_r2,
                                     "residual_std": s.residual_std, "n": s.n,
                                     "coefficients": s.coefficients,
                                     "interpretation": s.interpretation}
                                    for s in stages]

    # Cross-validation at each horizon
    print(f"\n  === Cross-Validation ===")
    cv_results = {}
    for h in HORIZONS:
        cv = cross_validate(df, h)
        cv_results[f"{h}h"] = cv
        if cv:
            print(f"    {h}h: R²(train)={cv['r2_train']:.4f}, R²(test)={cv['r2_test']:.4f}, "
                  f"MAE={cv['mae_test']:.1f} (baseline {cv['mae_baseline']:.1f}, "
                  f"reduction={cv['mae_reduction']:.1%})")

    # ── Summary: What does each factor contribute at each timescale? ──
    print(f"\n  === Factor Contribution Matrix ===")
    print(f"  {'Stage':<30} {'2h':>8} {'4h':>8} {'6h':>8}")
    print(f"  {'-' * 54}")

    stage_names = ["S1_subtract_bgi", "S2_subtract_egp", "S3_add_bg0",
                   "S4_add_dynamic_state", "S5_add_circadian", "S6_within_patient_fe"]
    for sname in stage_names:
        row = f"  {sname:<30}"
        for h in HORIZONS:
            hk = f"{h}h"
            stages = all_waterfalls.get(hk, [])
            match = [s for s in stages if s["name"] == sname]
            if match:
                row += f"  {match[0]['delta_r2']:+.4f}"
            else:
                row += f"  {'N/A':>7}"
        print(row)

    # ── Coefficient stability across horizons ────────────────────
    print(f"\n  === Coefficient Stability ===")
    key_coefs = ["excess_insulin", "egp_headwind", "bg0_centered", "roc_start", "iob_start"]
    for coef_name in key_coefs:
        row = f"  {coef_name:<20}"
        for h in HORIZONS:
            hk = f"{h}h"
            stages = all_waterfalls.get(hk, [])
            # Get from the most complete stage that has this coef
            for s in reversed(stages):
                if coef_name in s.get("coefficients", {}):
                    row += f"  {s['coefficients'][coef_name]:>8.3f}"
                    break
            else:
                row += f"  {'N/A':>8}"
        print(row)

    # ── Hypotheses ───────────────────────────────────────────────
    # H1: BGI subtraction is the single biggest lever at all horizons
    h1_pass = True
    for hk, stages in all_waterfalls.items():
        bgi_stage = [s for s in stages if s["name"] == "S1_subtract_bgi"]
        other_deltas = [s["delta_r2"] for s in stages
                        if s["name"] not in ("S0_raw_drop", "S1_subtract_bgi", "S7_independence_corrected")]
        if bgi_stage and other_deltas:
            if bgi_stage[0]["delta_r2"] < max(other_deltas):
                h1_pass = False

    # H2: EGP contribution grows with horizon
    egp_deltas = []
    for h in HORIZONS:
        hk = f"{h}h"
        stages = all_waterfalls.get(hk, [])
        egp = [s for s in stages if s["name"] == "S2_subtract_egp"]
        if egp:
            egp_deltas.append(egp[0]["delta_r2"])
    h2_pass = len(egp_deltas) >= 2 and egp_deltas[-1] > egp_deltas[0]

    # H3: BG₀ is a major confound (Δ > 0.05 at any horizon)
    bg0_deltas = []
    for h in HORIZONS:
        hk = f"{h}h"
        stages = all_waterfalls.get(hk, [])
        bg0 = [s for s in stages if s["name"] == "S3_add_bg0"]
        if bg0:
            bg0_deltas.append(bg0[0]["delta_r2"])
    h3_pass = any(d > 0.05 for d in bg0_deltas)

    # H4: Cross-validation generalizes (R²_test > 0.1)
    h4_pass = any(cv.get("r2_test", 0) > 0.1 for cv in cv_results.values())

    # H5: Independence correction doesn't destroy signal
    h5_pass = True
    for hk, stages in all_waterfalls.items():
        ind = [s for s in stages if s["name"] == "S7_independence_corrected"]
        full = [s for s in stages if s["name"] == "S4_add_dynamic_state"]
        if ind and full:
            if ind[0]["r2"] < full[0]["r2"] * 0.3:
                h5_pass = False

    hypotheses = {
        "H1_bgi_biggest_lever": h1_pass,
        "H2_egp_grows_with_horizon": h2_pass,
        "H3_bg0_major_confound": h3_pass,
        "H4_cross_validates": h4_pass,
        "H5_survives_independence": h5_pass,
    }

    n_pass = sum(hypotheses.values())
    print(f"\n  Hypotheses: {n_pass}/5 pass")
    for k, v in hypotheses.items():
        print(f"    {'✓' if v else '✗'} {k}")

    # ── Save results ─────────────────────────────────────────────
    metrics = {
        "n_events": len(df),
        "n_patients": df["patient_id"].nunique(),
        "waterfalls": all_waterfalls,
        "cross_validation": cv_results,
    }

    summary = (f"EXP-{EXP_ID}: {n_pass}/5 pass. N={len(df)} events, "
               f"{df['patient_id'].nunique()} patients. "
               f"Waterfall at {', '.join(f'{h}h' for h in HORIZONS)}.")

    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {summary}")
    print(f"{'=' * 70}")

    out_path = Path(__file__).resolve().parent.parent.parent / "externals" / "experiments" / f"exp-{EXP_ID}_extended_waterfall.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (bool, np.bool_)):
            return bool(obj)
        elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    with open(out_path, "w") as f:
        json.dump(clean({"exp_id": EXP_ID, "title": TITLE,
                         "hypotheses": hypotheses, "metrics": metrics,
                         "summary": summary}), f, indent=2)
    print(f"Saved: {out_path}")

    # ── Dashboard ────────────────────────────────────────────────
    create_dashboard(all_waterfalls, cv_results, hypotheses, metrics)

    return hypotheses, metrics


def create_dashboard(waterfalls, cv_results, hypotheses, metrics):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        return

    fig = plt.figure(figsize=(18, 12))
    fig.suptitle(f"EXP-{EXP_ID}: {TITLE}", fontsize=13, fontweight="bold")
    gs = GridSpec(2, 3, figure=fig, hspace=0.35, wspace=0.3)

    colors = {"2h": "steelblue", "4h": "coral", "6h": "darkgreen"}

    # Panel 1: R² waterfall by horizon (grouped bars)
    ax1 = fig.add_subplot(gs[0, 0])
    stage_names = ["S1_subtract_bgi", "S2_subtract_egp", "S3_add_bg0",
                   "S4_add_dynamic_state", "S5_add_circadian", "S6_within_patient_fe"]
    short_names = ["BGI", "EGP", "BG₀", "State", "Circadian", "Patient FE"]
    x = np.arange(len(stage_names))
    width = 0.25
    for idx, h in enumerate(HORIZONS):
        hk = f"{h}h"
        stages = waterfalls.get(hk, [])
        deltas = []
        for sn in stage_names:
            match = [s for s in stages if s["name"] == sn]
            deltas.append(match[0]["delta_r2"] if match else 0)
        ax1.bar(x + idx * width, deltas, width, label=f"{h}h", color=colors[hk])
    ax1.set_xticks(x + width)
    ax1.set_xticklabels(short_names, rotation=45, fontsize=8)
    ax1.set_ylabel("ΔR²")
    ax1.set_title("Factor Contribution (ΔR²) by Horizon")
    ax1.legend(fontsize=8)
    ax1.axhline(0, color="black", linewidth=0.5)

    # Panel 2: Cumulative R² by horizon
    ax2 = fig.add_subplot(gs[0, 1])
    for h in HORIZONS:
        hk = f"{h}h"
        stages = waterfalls.get(hk, [])
        r2_vals = [s["r2"] for s in stages if s["name"] != "S7_independence_corrected"]
        names = [s["name"].replace("S", "").split("_")[0] for s in stages if s["name"] != "S7_independence_corrected"]
        if r2_vals:
            ax2.plot(range(len(r2_vals)), r2_vals, "o-", color=colors[hk],
                     label=f"{h}h (final R²={r2_vals[-1]:.3f})")
    ax2.set_xlabel("Stage")
    ax2.set_ylabel("Cumulative R²")
    ax2.set_title("Cumulative Variance Explained")
    ax2.legend(fontsize=8)

    # Panel 3: Cross-validation
    ax3 = fig.add_subplot(gs[0, 2])
    if cv_results:
        horizons_cv = sorted(cv_results.keys())
        r2_train = [cv_results[h].get("r2_train", 0) for h in horizons_cv]
        r2_test = [cv_results[h].get("r2_test", 0) for h in horizons_cv]
        x = range(len(horizons_cv))
        ax3.bar([i - 0.15 for i in x], r2_train, 0.3, label="Train", color="steelblue", alpha=0.7)
        ax3.bar([i + 0.15 for i in x], r2_test, 0.3, label="Test", color="coral", alpha=0.7)
        ax3.set_xticks(list(x))
        ax3.set_xticklabels(horizons_cv)
        ax3.set_ylabel("R²")
        ax3.set_title("Cross-Validation (70/30 Patient Split)")
        ax3.legend(fontsize=8)

    # Panel 4: Coefficient stability
    ax4 = fig.add_subplot(gs[1, 0])
    key_coefs = ["excess_insulin", "bg0_centered"]
    for coef in key_coefs:
        vals = []
        for h in HORIZONS:
            hk = f"{h}h"
            stages = waterfalls.get(hk, [])
            for s in reversed(stages):
                if coef in s.get("coefficients", {}):
                    vals.append(s["coefficients"][coef])
                    break
            else:
                vals.append(np.nan)
        ax4.plot(range(len(HORIZONS)), vals, "o-", label=coef, linewidth=2)
    ax4.set_xticks(range(len(HORIZONS)))
    ax4.set_xticklabels([f"{h}h" for h in HORIZONS])
    ax4.set_ylabel("Coefficient")
    ax4.set_title("Coefficient Stability Across Horizons")
    ax4.legend(fontsize=8)
    ax4.axhline(0, color="black", linewidth=0.5)

    # Panel 5: MAE reduction
    ax5 = fig.add_subplot(gs[1, 1])
    if cv_results:
        horizons_cv = sorted(cv_results.keys())
        mae_base = [cv_results[h].get("mae_baseline", 0) for h in horizons_cv]
        mae_model = [cv_results[h].get("mae_test", 0) for h in horizons_cv]
        x = range(len(horizons_cv))
        ax5.bar([i - 0.15 for i in x], mae_base, 0.3, label="Baseline (mean)", color="lightcoral")
        ax5.bar([i + 0.15 for i in x], mae_model, 0.3, label="Model", color="darkgreen")
        ax5.set_xticks(list(x))
        ax5.set_xticklabels(horizons_cv)
        ax5.set_ylabel("MAE (mg/dL)")
        ax5.set_title("Holdout MAE: Model vs Baseline")
        ax5.legend(fontsize=8)

    # Panel 6: Summary
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    lines = [
        f"N = {metrics.get('n_events', 0)} events, {metrics.get('n_patients', 0)} patients",
        "",
        "The subtraction pipeline progressively removes",
        "known confounds. At each stage we measure how",
        "much variance was explained by that factor.",
        "",
        "Hypothesis Results:",
    ]
    for k, v in hypotheses.items():
        lines.append(f"  {'✓' if v else '✗'} {k}")

    ax6.text(0.05, 0.95, "\n".join(lines), transform=ax6.transAxes,
             fontsize=9, verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    out_dir = Path(__file__).resolve().parent.parent / "visualizations" / "extended-waterfall"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"exp-{EXP_ID}-dashboard.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Dashboard: {out_path}")


if __name__ == "__main__":
    main()
