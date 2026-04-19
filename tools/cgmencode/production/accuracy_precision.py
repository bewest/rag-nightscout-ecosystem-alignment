"""
accuracy_precision.py — Distinguish and measure accuracy vs precision in settings extraction.

Scientific context:
    ACCURACY  = systematic bias: is the mean estimate correct?
        → ISF_extracted vs ISF_true: mean error (bias)
        → Controlled by: BGI subtraction, BG floor, event categorization

    PRECISION = random scatter: how reproducible is the estimate?
        → ISF_extracted confidence interval width
        → Controlled by: event count, patient phenotype, isolation quality

    These are INDEPENDENT dimensions. An extraction can be:
        - Accurate + precise: mean correct, tight CI (goal)
        - Accurate + imprecise: mean correct, wide CI (need more events)
        - Inaccurate + precise: consistent bias, tight CI (systematic error)
        - Inaccurate + imprecise: everything wrong (bad extraction)

    The deconfounding pipeline addresses ACCURACY (removing systematic bias).
    Event count and filtering address PRECISION (reducing random scatter).
    Patient phenotyping addresses BOTH (different patients need different models).

Usage:
    from production.accuracy_precision import AccuracyPrecisionReport

    report = AccuracyPrecisionReport(events, patient_isf_settings)
    results = report.run()
    report.print_report()

    # Per-patient accuracy/precision
    for pid, metrics in results["per_patient"].items():
        print(f"{pid}: bias={metrics['bias']:.1f}, CI_width={metrics['ci_width']:.1f}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


# ── Metrics ──────────────────────────────────────────────────────────

@dataclass
class AccuracyMetrics:
    """Accuracy (systematic bias) measurements."""
    mean_error: float          # bias: mean(extracted - setting)
    median_error: float
    rmse: float               # root mean squared error
    r2_vs_setting: float      # how much of extracted ISF is explained by settings
    n_patients: int
    n_events: int

    @property
    def bias_direction(self) -> str:
        if abs(self.mean_error) < 5:
            return "unbiased"
        return "over-estimates" if self.mean_error > 0 else "under-estimates"

    @property
    def accuracy_grade(self) -> str:
        """A-F grade based on absolute bias."""
        abs_bias = abs(self.mean_error)
        if abs_bias < 5:
            return "A"
        elif abs_bias < 15:
            return "B"
        elif abs_bias < 30:
            return "C"
        elif abs_bias < 50:
            return "D"
        return "F"


@dataclass
class PrecisionMetrics:
    """Precision (random scatter) measurements."""
    mean_ci_width: float       # average 95% CI width across patients
    median_ci_width: float
    mean_cv: float            # coefficient of variation of ISF within patient
    median_cv: float
    min_events_for_stable: int  # events needed for CI < 20 mg/dL/U
    frac_patients_stable: float  # fraction with CI < 20

    @property
    def precision_grade(self) -> str:
        """A-F grade based on CI width."""
        if self.median_ci_width < 10:
            return "A"
        elif self.median_ci_width < 20:
            return "B"
        elif self.median_ci_width < 40:
            return "C"
        elif self.median_ci_width < 60:
            return "D"
        return "F"


@dataclass
class PatientReport:
    """Per-patient accuracy + precision."""
    patient_id: str
    controller: str
    n_events: int
    isf_setting: float
    isf_extracted: float
    bias: float                 # extracted - setting
    ci_lower: float
    ci_upper: float
    ci_width: float
    cv: float                  # coefficient of variation
    accuracy_grade: str
    precision_grade: str

    @property
    def overall_grade(self) -> str:
        grades = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        avg = (grades.get(self.accuracy_grade, 0) + grades.get(self.precision_grade, 0)) / 2
        if avg >= 3.5:
            return "A"
        elif avg >= 2.5:
            return "B"
        elif avg >= 1.5:
            return "C"
        elif avg >= 0.5:
            return "D"
        return "F"


# ── Main Report ──────────────────────────────────────────────────────

class AccuracyPrecisionReport:
    """Measure accuracy and precision of settings extraction from deconfounded events.

    Takes events (output from BGISubtraction + EventCategorizer) and
    computes per-patient ISF extraction with accuracy/precision metrics.
    """

    def __init__(
        self,
        events: pd.DataFrame,
        bg_floor: float = 180.0,
        min_events: int = 10,
        confidence: float = 0.95,
    ):
        self.events = events
        self.bg_floor = bg_floor
        self.min_events = min_events
        self.confidence = confidence

        self.accuracy: Optional[AccuracyMetrics] = None
        self.precision: Optional[PrecisionMetrics] = None
        self.patients: Dict[str, PatientReport] = {}

    def run(self) -> Dict[str, Any]:
        """Compute accuracy and precision report."""
        ev = self.events

        # Filter to correction events with BG floor
        corrections = ev[
            (ev["category"] == "correction") &
            (ev["bg0"] >= self.bg_floor) &
            (ev["bolus_2h"] > 0.3)
        ].copy()

        if len(corrections) < self.min_events:
            return {"status": "SKIP", "reason": f"Only {len(corrections)} correction events"}

        # Compute effective ISF per event
        corrections["effective_isf"] = (
            corrections["observed_drop"] / corrections["bolus_2h"].clip(lower=0.1)
        )

        # Remove extreme outliers (sensor noise, misclassified events)
        valid = corrections[
            (corrections["effective_isf"] > 0) &
            (corrections["effective_isf"] < 300)
        ]

        # Per-patient extraction
        z = stats.norm.ppf(1 - (1 - self.confidence) / 2)
        patient_reports = []

        for pid in valid["patient_id"].unique():
            pv = valid[valid["patient_id"] == pid]
            if len(pv) < self.min_events:
                continue

            isf_vals = pv["effective_isf"].values
            n = len(isf_vals)
            mean_isf = float(np.mean(isf_vals))
            se = float(np.std(isf_vals, ddof=1) / np.sqrt(n))
            ci_lower = mean_isf - z * se
            ci_upper = mean_isf + z * se
            ci_width = ci_upper - ci_lower
            cv = float(np.std(isf_vals, ddof=1) / abs(mean_isf)) if abs(mean_isf) > 0.1 else np.inf

            isf_setting = float(pv["isf_used"].median())
            bias = mean_isf - isf_setting

            # Grade accuracy
            abs_bias = abs(bias)
            if abs_bias < 5:
                a_grade = "A"
            elif abs_bias < 15:
                a_grade = "B"
            elif abs_bias < 30:
                a_grade = "C"
            elif abs_bias < 50:
                a_grade = "D"
            else:
                a_grade = "F"

            # Grade precision
            if ci_width < 10:
                p_grade = "A"
            elif ci_width < 20:
                p_grade = "B"
            elif ci_width < 40:
                p_grade = "C"
            elif ci_width < 60:
                p_grade = "D"
            else:
                p_grade = "F"

            ctrl = pv["controller"].iloc[0] if "controller" in pv.columns else "unknown"

            pr = PatientReport(
                patient_id=pid,
                controller=ctrl,
                n_events=n,
                isf_setting=isf_setting,
                isf_extracted=mean_isf,
                bias=bias,
                ci_lower=ci_lower,
                ci_upper=ci_upper,
                ci_width=ci_width,
                cv=cv,
                accuracy_grade=a_grade,
                precision_grade=p_grade,
            )
            patient_reports.append(pr)
            self.patients[pid] = pr

        if not patient_reports:
            return {"status": "SKIP", "reason": "No patients with enough events"}

        # Aggregate accuracy metrics
        biases = [p.bias for p in patient_reports]
        self.accuracy = AccuracyMetrics(
            mean_error=float(np.mean(biases)),
            median_error=float(np.median(biases)),
            rmse=float(np.sqrt(np.mean(np.array(biases) ** 2))),
            r2_vs_setting=self._r2_vs_setting(patient_reports),
            n_patients=len(patient_reports),
            n_events=sum(p.n_events for p in patient_reports),
        )

        # Aggregate precision metrics
        ci_widths = [p.ci_width for p in patient_reports]
        cvs = [p.cv for p in patient_reports if np.isfinite(p.cv)]

        # Estimate minimum events for stability
        min_for_stable = self._min_events_for_ci(valid, target_ci=20.0)

        self.precision = PrecisionMetrics(
            mean_ci_width=float(np.mean(ci_widths)),
            median_ci_width=float(np.median(ci_widths)),
            mean_cv=float(np.mean(cvs)) if cvs else np.inf,
            median_cv=float(np.median(cvs)) if cvs else np.inf,
            min_events_for_stable=min_for_stable,
            frac_patients_stable=float(sum(1 for w in ci_widths if w < 20) / len(ci_widths)),
        )

        return self.to_dict()

    def _r2_vs_setting(self, reports: List[PatientReport]) -> float:
        """How well do settings predict extracted ISF?"""
        if len(reports) < 3:
            return np.nan
        settings = np.array([p.isf_setting for p in reports])
        extracted = np.array([p.isf_extracted for p in reports])
        ss_tot = np.sum((extracted - extracted.mean()) ** 2)
        ss_res = np.sum((extracted - settings) ** 2)
        return float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    def _min_events_for_ci(self, valid: pd.DataFrame, target_ci: float) -> int:
        """Estimate minimum events needed for CI < target width.

        Uses pooled SD to estimate: n = (2 * z * SD / target_ci)²
        """
        z = stats.norm.ppf(1 - (1 - self.confidence) / 2)
        pooled_sd = float(valid["effective_isf"].std())
        if pooled_sd < 0.1:
            return 1
        n_needed = int(np.ceil((2 * z * pooled_sd / target_ci) ** 2))
        return max(n_needed, 1)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        result: Dict[str, Any] = {}

        if self.accuracy:
            result["accuracy"] = {
                "mean_bias": round(self.accuracy.mean_error, 2),
                "median_bias": round(self.accuracy.median_error, 2),
                "rmse": round(self.accuracy.rmse, 2),
                "r2_vs_setting": round(self.accuracy.r2_vs_setting, 4),
                "grade": self.accuracy.accuracy_grade,
                "direction": self.accuracy.bias_direction,
                "n_patients": self.accuracy.n_patients,
                "n_events": self.accuracy.n_events,
            }

        if self.precision:
            result["precision"] = {
                "mean_ci_width": round(self.precision.mean_ci_width, 2),
                "median_ci_width": round(self.precision.median_ci_width, 2),
                "mean_cv": round(self.precision.mean_cv, 4),
                "median_cv": round(self.precision.median_cv, 4),
                "grade": self.precision.precision_grade,
                "min_events_for_stable": self.precision.min_events_for_stable,
                "frac_patients_stable": round(self.precision.frac_patients_stable, 3),
            }

        result["per_patient"] = {
            pid: {
                "controller": p.controller,
                "n": p.n_events,
                "isf_setting": round(p.isf_setting, 1),
                "isf_extracted": round(p.isf_extracted, 1),
                "bias": round(p.bias, 1),
                "ci_width": round(p.ci_width, 1),
                "cv": round(p.cv, 3),
                "accuracy": p.accuracy_grade,
                "precision": p.precision_grade,
                "overall": p.overall_grade,
            }
            for pid, p in self.patients.items()
        }

        # Identify which deconfounding stages affect accuracy vs precision
        result["methodology_notes"] = {
            "accuracy_controlled_by": [
                "BGI subtraction (removes insulin effect bias)",
                "BG floor >= 180 (removes misclassified meal bias)",
                "Event categorization (isolates correction-only events)",
                "Channel decomposition (subtracts SMB/basal bias)",
            ],
            "precision_controlled_by": [
                "Event count (more events → narrower CI)",
                "Isolation quality (cleaner events → lower variance)",
                "Patient phenotype (high-variability patients need more events)",
                "Horizon truncation (2h demand-phase reduces noise)",
            ],
        }

        return result

    def print_report(self):
        """Print human-readable accuracy/precision report."""
        if not self.accuracy or not self.precision:
            print("Run report first: report.run()")
            return

        a = self.accuracy
        p = self.precision

        print("\n" + "=" * 70)
        print("ACCURACY / PRECISION REPORT — ISF Extraction Quality")
        print("=" * 70)

        print(f"\n  ACCURACY (systematic bias)    Grade: {a.accuracy_grade}")
        print(f"    Mean bias:    {a.mean_error:+.1f} mg/dL/U ({a.bias_direction})")
        print(f"    Median bias:  {a.median_error:+.1f} mg/dL/U")
        print(f"    RMSE:         {a.rmse:.1f} mg/dL/U")
        print(f"    R² vs settings: {a.r2_vs_setting:.3f}")
        print(f"    N patients:   {a.n_patients}, N events: {a.n_events:,}")

        print(f"\n  PRECISION (random scatter)    Grade: {p.precision_grade}")
        print(f"    Mean 95% CI width:  {p.mean_ci_width:.1f} mg/dL/U")
        print(f"    Median 95% CI width: {p.median_ci_width:.1f} mg/dL/U")
        print(f"    Patients with CI<20: {p.frac_patients_stable:.0%}")
        print(f"    Events for CI<20:    ~{p.min_events_for_stable}")
        print(f"    Mean CV:             {p.mean_cv:.2f}")

        print(f"\n  PER-PATIENT:")
        print(f"    {'Patient':<12s} {'Ctrl':<8s} {'N':>5s} {'Setting':>8s} "
              f"{'Extract':>8s} {'Bias':>8s} {'CI':>8s} {'A':>3s} {'P':>3s} {'O':>3s}")
        print("    " + "-" * 72)
        for pid, pr in sorted(self.patients.items(), key=lambda x: -abs(x[1].bias)):
            print(f"    {pid:<12s} {pr.controller:<8s} {pr.n_events:>5d} "
                  f"{pr.isf_setting:>8.1f} {pr.isf_extracted:>8.1f} "
                  f"{pr.bias:>+8.1f} {pr.ci_width:>8.1f} "
                  f"{pr.accuracy_grade:>3s} {pr.precision_grade:>3s} {pr.overall_grade:>3s}")

        print("\n" + "=" * 70)
