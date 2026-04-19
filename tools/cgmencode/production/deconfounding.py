"""
deconfounding.py — Composable deconfounding strategies for observational AID experiments.

Research basis:
  EXP-2698: BGI subtraction adds +0.418 R² (0.350 → 0.768)
  EXP-2698: Category-specific models reach R²=0.839 for corrections
  EXP-2698: All insulin channels have ~equal per-unit effect (-124 to -131 mg/dL/U)
  EXP-2695: Propensity score matching recovers bolus effect from confounded data
  EXP-2680: BG≥180 floor reduces negative ISF from 57% to 10%

Design philosophy:
  - SUBTRACTION over exclusion: estimate the effect of SMBs/temp basals and subtract,
    rather than excluding events. This preserves data for Trio/SMB patients.
  - COMPOSABLE: strategies are independent and chainable. Pick what fits your hypothesis.
  - VALIDATED DEFAULTS: coefficients from EXP-2698 (N=506,198 events, 21 patients).

Usage:
    from production.deconfounding import (
        BGISubtraction, ChannelDecomposition, EventCategorizer,
        IsolationFilter, ExperimentFilters, ValidationChecks,
    )

    # Approach A: Subtract what you know (oref0-style)
    bgi = BGISubtraction()
    events = bgi.compute_deviations(grid_df, patient_isf)

    # Approach B: Exclude confounded events (traditional)
    filt = IsolationFilter(ExperimentFilters(bg_floor=180, isolation_hours=2))
    clean = filt.apply(grid_df)

    # Approach C: Combine — subtract then filter
    events = bgi.compute_deviations(grid_df, patient_isf)
    events = EventCategorizer().categorize(events)
    corrections = events[events["category"] == "correction"]

    # Validate the extraction
    ValidationChecks.dose_independence(corrections, dose_col="bolus_2h", outcome_col="deviation")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


# ── Constants from EXP-2698 (N=506,198 events, 21 patients) ─────────

# Per-unit deviation coefficients by insulin channel (correction events).
# All three channels have nearly identical per-unit effect.
BOLUS_COEFF = -129.2     # mg/dL deviation per unit bolus
SMB_COEFF = -123.6        # mg/dL deviation per unit SMB
EXCESS_BASAL_COEFF = -130.5  # mg/dL deviation per unit excess basal

# Default horizons (in 5-minute steps)
STEPS_PER_HOUR = 12
DEFAULT_HORIZON_STEPS = 24   # 2 hours (demand phase)

# BG floor from EXP-2677/2680: reduces negative ISF from 57% to 10%
DEFAULT_BG_FLOOR = 180.0


# ── Filter Specification ─────────────────────────────────────────────

@dataclass
class ExperimentFilters:
    """Declarative filter specification for observational experiments.

    Encodes domain knowledge about what makes a clean analysis window.
    Agents use this as a configuration object rather than reasoning
    about each filter individually.

    Presets available via class methods: .correction(), .meal(), .permissive()
    """
    bg_floor: float = 0.0
    bg_ceiling: Optional[float] = None
    isolation_hours: float = 0.0
    min_dose: float = 0.0
    max_carbs_in_window: Optional[float] = None
    carb_window_hours: Tuple[float, float] = (-1.0, 2.0)
    require_carb_free: bool = False
    min_quality: float = 0.0
    horizon_hours: float = 2.0
    min_events: int = 30

    @classmethod
    def correction(cls) -> "ExperimentFilters":
        """Strict filters for ISF extraction (EXP-2680 validated)."""
        return cls(
            bg_floor=180.0,
            isolation_hours=2.0,
            min_dose=0.3,
            require_carb_free=True,
            carb_window_hours=(-1.0, 2.0),
            min_quality=0.7,
            horizon_hours=2.0,
            min_events=30,
        )

    @classmethod
    def meal(cls) -> "ExperimentFilters":
        """Filters for CR extraction (meal windows)."""
        return cls(
            bg_floor=0.0,
            isolation_hours=0.0,
            min_dose=0.0,
            max_carbs_in_window=None,  # carbs required, not excluded
            require_carb_free=False,
            min_quality=0.7,
            horizon_hours=3.0,
            min_events=30,
        )

    @classmethod
    def permissive(cls) -> "ExperimentFilters":
        """Minimal filtering — use with subtraction-based deconfounding."""
        return cls(
            bg_floor=120.0,
            isolation_hours=0.0,
            min_dose=0.0,
            require_carb_free=False,
            min_quality=0.0,
            horizon_hours=2.0,
            min_events=30,
        )

    @classmethod
    def basal(cls) -> "ExperimentFilters":
        """Filters for basal extraction (fasting/overnight windows)."""
        return cls(
            bg_floor=0.0,
            isolation_hours=3.0,
            min_dose=0.0,
            require_carb_free=True,
            carb_window_hours=(-3.0, 3.0),
            min_quality=0.7,
            horizon_hours=3.0,
            min_events=20,
        )


# ── BGI Subtraction (oref0's core insight) ───────────────────────────

class BGISubtraction:
    """Subtract expected insulin effect to compute deviation.

    oref0 formula: BGI = -IOB_activity × ISF × 5
    Our approximation: expected_drop = total_excess_insulin × ISF

    After subtraction, deviation = observed_drop - expected_drop.
    This removes the dominant confound (known insulin action) and makes
    residual analysis tractable (EXP-2698: +0.418 R²).
    """

    def __init__(self, horizon_steps: int = DEFAULT_HORIZON_STEPS):
        self.horizon_steps = horizon_steps

    def compute_deviations(
        self,
        grid: pd.DataFrame,
        patient_isf: Optional[Dict[str, float]] = None,
    ) -> pd.DataFrame:
        """Compute deviation for every valid point in the grid.

        Args:
            grid: DataFrame with columns: patient_id, time, glucose, bolus,
                  iob, scheduled_isf, scheduled_basal_rate,
                  and optionally bolus_smb, net_basal.
            patient_isf: Optional per-patient ISF override dict.

        Returns:
            DataFrame of events with columns: patient_id, time, bg0, bg_end,
            observed_drop, expected_drop, deviation, bolus_2h, smb_2h,
            excess_basal_2h, excess_insulin, iob_start, roc_start, carbs_2h,
            hour, controller.
        """
        h = self.horizon_steps
        events = []

        has_smb = "bolus_smb" in grid.columns
        has_net_basal = "net_basal" in grid.columns
        has_sched_basal = "scheduled_basal_rate" in grid.columns
        has_carbs = "carbs" in grid.columns
        has_controller = "controller" in grid.columns

        for pid in grid["patient_id"].unique():
            pg = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
            if len(pg) < h + 2:
                continue

            glucose = pg["glucose"].values
            bolus = pg["bolus"].values
            iob = pg["iob"].values if "iob" in pg.columns else np.full(len(pg), np.nan)
            smb = pg["bolus_smb"].values if has_smb else np.zeros(len(pg))
            net_basal = pg["net_basal"].values if has_net_basal else np.full(len(pg), np.nan)
            sched_basal = pg["scheduled_basal_rate"].values if has_sched_basal else np.full(len(pg), np.nan)
            carbs = pg["carbs"].values if has_carbs else np.zeros(len(pg))
            times = pg["time"].values

            # Get ISF for this patient
            if patient_isf and pid in patient_isf:
                isf_val = patient_isf[pid]
            elif "scheduled_isf" in pg.columns:
                isf_val = np.nanmedian(pg["scheduled_isf"].values)
            else:
                continue  # can't compute BGI without ISF

            ctrl = pg["controller"].iloc[0] if has_controller else "unknown"

            for i in range(1, len(pg) - h):
                bg0 = glucose[i]
                bg_end = glucose[i + h]
                if np.isnan(bg0) or np.isnan(bg_end):
                    continue

                # Accumulate insulin over horizon window
                bolus_2h = float(np.nansum(bolus[i:i + h]))
                smb_2h = float(np.nansum(smb[i:i + h]))

                # Excess basal = actual - scheduled (in units over 2h)
                if has_net_basal:
                    excess_basal_2h = float(np.nansum(net_basal[i:i + h])) / STEPS_PER_HOUR
                elif has_sched_basal:
                    actual = float(np.nansum(bolus[i:i + h])) + float(np.nansum(smb[i:i + h]))
                    scheduled_total = float(np.nansum(sched_basal[i:i + h])) / STEPS_PER_HOUR
                    excess_basal_2h = 0.0  # can't compute without net_basal
                else:
                    excess_basal_2h = 0.0

                excess_insulin = bolus_2h + smb_2h + excess_basal_2h
                expected_drop = excess_insulin * isf_val

                observed_drop = bg0 - bg_end
                deviation = observed_drop - expected_drop

                # Rate of change at start (mg/dL per 5min)
                roc_start = float(glucose[i] - glucose[i - 1]) if i > 0 and not np.isnan(glucose[i - 1]) else 0.0

                carbs_2h = float(np.nansum(carbs[i:i + h]))

                try:
                    ts = pd.Timestamp(times[i])
                    hour = ts.hour
                except Exception:
                    hour = 0

                events.append({
                    "patient_id": pid,
                    "time": times[i],
                    "bg0": bg0,
                    "bg_end": bg_end,
                    "observed_drop": observed_drop,
                    "expected_drop": expected_drop,
                    "deviation": deviation,
                    "bolus_2h": bolus_2h,
                    "smb_2h": smb_2h,
                    "excess_basal_2h": excess_basal_2h,
                    "excess_insulin": excess_insulin,
                    "iob_start": float(iob[i]) if not np.isnan(iob[i]) else 0.0,
                    "roc_start": roc_start,
                    "carbs_2h": carbs_2h,
                    "hour": hour,
                    "controller": ctrl,
                    "isf_used": isf_val,
                })

        return pd.DataFrame(events)


# ── Channel Decomposition ────────────────────────────────────────────

class ChannelDecomposition:
    """Estimate and subtract individual insulin channel effects.

    Instead of excluding events with SMB contamination (which loses most
    Trio/OpenAPS data), estimate each channel's contribution using
    EXP-2698 validated coefficients and subtract them.

    This enables analyzing the RESIDUAL after accounting for all
    known insulin channels — the residual captures EGP, carbs, stress,
    sensor noise, and other unmeasured factors.
    """

    def __init__(
        self,
        bolus_coeff: float = BOLUS_COEFF,
        smb_coeff: float = SMB_COEFF,
        basal_coeff: float = EXCESS_BASAL_COEFF,
    ):
        self.bolus_coeff = bolus_coeff
        self.smb_coeff = smb_coeff
        self.basal_coeff = basal_coeff

    def decompose(self, events: pd.DataFrame) -> pd.DataFrame:
        """Add per-channel estimated effects and channel-subtracted residuals.

        Adds columns:
            est_bolus_effect: estimated deviation from bolus alone
            est_smb_effect: estimated deviation from SMBs alone
            est_basal_effect: estimated deviation from excess basal alone
            residual_no_bolus: deviation after subtracting bolus effect
            residual_no_smb: deviation after subtracting SMB effect
            residual_no_controller: deviation after subtracting SMB + excess basal
            residual_all_channels: deviation after subtracting all insulin channels
        """
        df = events.copy()

        df["est_bolus_effect"] = df["bolus_2h"] * self.bolus_coeff
        df["est_smb_effect"] = df["smb_2h"] * self.smb_coeff
        df["est_basal_effect"] = df["excess_basal_2h"] * self.basal_coeff

        # Subtract individual channels
        df["residual_no_bolus"] = df["deviation"] - df["est_bolus_effect"]
        df["residual_no_smb"] = df["deviation"] - df["est_smb_effect"]
        df["residual_no_controller"] = (
            df["deviation"] - df["est_smb_effect"] - df["est_basal_effect"]
        )
        df["residual_all_channels"] = (
            df["deviation"]
            - df["est_bolus_effect"]
            - df["est_smb_effect"]
            - df["est_basal_effect"]
        )

        return df


# ── Event Categorization (oref0's 4-bucket system) ──────────────────

class EventCategory(str, Enum):
    CORRECTION = "correction"
    MEAL = "meal"
    UAM = "uam"
    BASAL = "basal"
    MIXED = "mixed"


class EventCategorizer:
    """Classify events into categories for category-specific analysis.

    EXP-2698 showed category-specific models dramatically outperform
    pooled models (correction: 0.839 vs pooled: 0.768).
    """

    def __init__(
        self,
        min_carbs: float = 5.0,
        min_bolus: float = 0.3,
        min_uam_deviation: float = 5.0,
        min_controller_action: float = 0.1,
    ):
        self.min_carbs = min_carbs
        self.min_bolus = min_bolus
        self.min_uam_deviation = min_uam_deviation
        self.min_controller_action = min_controller_action

    def categorize(self, events: pd.DataFrame) -> pd.DataFrame:
        """Add 'category' column to events DataFrame."""
        df = events.copy()

        def _classify(row):
            has_carbs = row.get("carbs_2h", 0) > self.min_carbs
            has_bolus = row.get("bolus_2h", 0) > self.min_bolus
            has_controller = (
                abs(row.get("excess_basal_2h", 0)) > self.min_controller_action
                or row.get("smb_2h", 0) > self.min_controller_action
            )

            if has_carbs:
                return EventCategory.MEAL.value
            elif has_bolus:
                return EventCategory.CORRECTION.value
            elif not has_controller and row.get("smb_2h", 0) < self.min_controller_action:
                return EventCategory.BASAL.value
            elif row.get("deviation", 0) > self.min_uam_deviation and not has_carbs:
                return EventCategory.UAM.value
            else:
                return EventCategory.MIXED.value

        df["category"] = df.apply(_classify, axis=1)
        return df


# ── Isolation Filter (traditional exclusion-based) ───────────────────

class IsolationFilter:
    """Traditional exclusion-based filtering for clean analysis windows.

    Use when you need the cleanest possible events (e.g., ISF extraction)
    and can afford to lose event count. For situations where subtraction-
    based deconfounding is preferred, use BGISubtraction + ChannelDecomposition.
    """

    def __init__(self, filters: ExperimentFilters):
        self.filters = filters

    def apply(
        self,
        grid: pd.DataFrame,
        return_mask: bool = False,
    ) -> pd.DataFrame:
        """Apply exclusion filters to grid data.

        Returns filtered DataFrame (or boolean mask if return_mask=True).
        """
        f = self.filters
        h = int(f.horizon_hours * STEPS_PER_HOUR)
        mask = pd.Series(True, index=grid.index)

        # BG floor
        if f.bg_floor > 0:
            mask &= grid["glucose"] >= f.bg_floor

        # BG ceiling
        if f.bg_ceiling is not None:
            mask &= grid["glucose"] <= f.bg_ceiling

        # Min dose
        if f.min_dose > 0 and "bolus" in grid.columns:
            mask &= grid["bolus"] >= f.min_dose

        # Carb-free window (per-patient rolling check)
        if f.require_carb_free and "carbs" in grid.columns:
            pre_steps = int(abs(f.carb_window_hours[0]) * STEPS_PER_HOUR)
            post_steps = int(f.carb_window_hours[1] * STEPS_PER_HOUR)
            carb_sum = grid["carbs"].rolling(
                window=pre_steps + post_steps, min_periods=1, center=True
            ).sum()
            mask &= carb_sum <= (f.max_carbs_in_window or 0.0)

        # Prior bolus isolation (rolling check)
        if f.isolation_hours > 0 and "bolus" in grid.columns:
            iso_steps = int(f.isolation_hours * STEPS_PER_HOUR)
            # Check for prior boluses (excluding current point)
            prior_bolus = grid["bolus"].shift(1).rolling(
                window=iso_steps, min_periods=1
            ).sum()
            mask &= prior_bolus <= 0.0

        if return_mask:
            return mask
        return grid[mask].copy()


# ── Validation Checks ────────────────────────────────────────────────

class ValidationChecks:
    """Automatic validation for experiment quality.

    Run these after event extraction to catch insufficient filtering
    BEFORE producing misleading results. EXP-2677's 57% negative ISF
    would have been caught by dose_independence().
    """

    @staticmethod
    def dose_independence(
        events: pd.DataFrame,
        dose_col: str = "bolus_2h",
        outcome_col: str = "deviation",
        threshold: float = 0.3,
    ) -> Dict:
        """Check that outcome is approximately dose-independent.

        A dose-dependent outcome (|r| > threshold) suggests confounding
        by dose size — the extraction may be measuring pharmacokinetics
        rather than physiology.

        Returns dict with r, p, pass/fail, and recommendation.
        """
        valid = events[[dose_col, outcome_col]].dropna()
        valid = valid[valid[dose_col] > 0]
        if len(valid) < 10:
            return {"status": "SKIP", "reason": f"Only {len(valid)} events with dose > 0"}

        log_dose = np.log(valid[dose_col].values + 0.01)
        outcome = valid[outcome_col].values
        r, p = stats.spearmanr(log_dose, outcome)

        passed = abs(r) < threshold
        return {
            "status": "PASS" if passed else "FAIL",
            "r": float(r),
            "p": float(p),
            "threshold": threshold,
            "n": len(valid),
            "recommendation": (
                "Extraction is dose-independent ✓"
                if passed
                else f"|r|={abs(r):.3f} > {threshold}: outcome is dose-dependent. "
                     f"Consider BG floor ≥180 or demand-phase truncation."
            ),
        }

    @staticmethod
    def event_count(
        events: pd.DataFrame,
        min_events: int = 30,
        group_col: Optional[str] = None,
    ) -> Dict:
        """Check sufficient event count (overall or per-group).

        Returns dict with counts, pass/fail, and recommendation.
        """
        if group_col and group_col in events.columns:
            counts = events.groupby(group_col).size().to_dict()
            min_count = min(counts.values()) if counts else 0
            passed = min_count >= min_events
            return {
                "status": "PASS" if passed else "FAIL",
                "counts": counts,
                "min_count": int(min_count),
                "threshold": min_events,
                "recommendation": (
                    f"All groups have ≥{min_events} events ✓"
                    if passed
                    else f"Some groups have <{min_events} events. "
                         f"Consider relaxing filters or merging small groups."
                ),
            }
        else:
            n = len(events)
            passed = n >= min_events
            return {
                "status": "PASS" if passed else "FAIL",
                "n": n,
                "threshold": min_events,
                "recommendation": (
                    f"N={n} events ≥ {min_events} ✓"
                    if passed
                    else f"Only {n} events < {min_events}. Relax filters."
                ),
            }

    @staticmethod
    def covariate_balance(
        treated: pd.DataFrame,
        control: pd.DataFrame,
        covariates: List[str],
        threshold: float = 0.1,
    ) -> Dict:
        """Check covariate balance between treated/control groups (for PSM).

        Standardized mean difference (SMD) < threshold for all covariates.
        """
        results = {}
        all_pass = True
        for cov in covariates:
            if cov not in treated.columns or cov not in control.columns:
                continue
            t_vals = treated[cov].dropna().values
            c_vals = control[cov].dropna().values
            if len(t_vals) < 2 or len(c_vals) < 2:
                continue
            pooled_sd = np.sqrt((np.var(t_vals) + np.var(c_vals)) / 2)
            if pooled_sd < 1e-10:
                smd = 0.0
            else:
                smd = abs(np.mean(t_vals) - np.mean(c_vals)) / pooled_sd
            passed = smd < threshold
            if not passed:
                all_pass = False
            results[cov] = {"smd": float(smd), "pass": passed}

        return {
            "status": "PASS" if all_pass else "FAIL",
            "covariates": results,
            "threshold": threshold,
        }

    @staticmethod
    def pre_trend(
        events: pd.DataFrame,
        pre_col: str = "roc_start",
        outcome_col: str = "deviation",
        threshold: float = 0.2,
    ) -> Dict:
        """Falsification test: pre-event trajectory should NOT predict outcome.

        If pre-trend strongly predicts post-event outcome, the events are
        confounded by momentum rather than isolated treatment effects.
        """
        valid = events[[pre_col, outcome_col]].dropna()
        if len(valid) < 10:
            return {"status": "SKIP", "reason": f"Only {len(valid)} events"}

        r, p = stats.spearmanr(valid[pre_col], valid[outcome_col])
        passed = abs(r) < threshold
        return {
            "status": "PASS" if passed else "WARN",
            "r": float(r),
            "p": float(p),
            "threshold": threshold,
            "recommendation": (
                "Pre-trend does not predict outcome ✓"
                if passed
                else f"|r|={abs(r):.3f}: pre-trend predicts outcome. "
                     f"Events may be confounded by glucose momentum."
            ),
        }

    @staticmethod
    def run_all(
        events: pd.DataFrame,
        filters: Optional[ExperimentFilters] = None,
    ) -> Dict:
        """Run all validation checks and return combined report."""
        report = {}
        report["event_count"] = ValidationChecks.event_count(
            events,
            min_events=filters.min_events if filters else 30,
        )
        if "bolus_2h" in events.columns and "deviation" in events.columns:
            report["dose_independence"] = ValidationChecks.dose_independence(events)
        if "roc_start" in events.columns and "deviation" in events.columns:
            report["pre_trend"] = ValidationChecks.pre_trend(events)

        # Per-patient event count
        if "patient_id" in events.columns:
            report["per_patient_count"] = ValidationChecks.event_count(
                events, min_events=10, group_col="patient_id"
            )

        all_pass = all(
            v.get("status") in ("PASS", "SKIP")
            for v in report.values()
        )
        report["overall"] = "PASS" if all_pass else "REVIEW"
        return report
