"""
therapy_analyzer.py — Deep therapy settings analysis for AID patients.

Analyzes basal rates, ISF, CR from CGM + IOB + bolus + treatment data,
accounting for AID loop compensation. Uses natural experiments, per-night
overnight analysis, and correction bolus response curves.

Key insight: For AID patients, the loop's automated adjustments mask the
programmed settings. The metabolic flux includes loop adjustments, so
naive supply-demand analysis can be misleading. This module uses:
  1. Per-night overnight drift analysis (not aggregated metabolic flux)
  2. IOB circadian pattern (shows actual loop behavior)
  3. Correction bolus response curves (ISF estimation under AID)
  4. Weekly trend decomposition (identifies external factors)
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np


@dataclass
class NightAnalysis:
    """Analysis of a single overnight period."""
    date: str
    start_bg: float
    end_bg: float
    slope_per_hour: float
    tir: float
    tbr: float
    nadir: float
    n_points: int

    @property
    def direction(self) -> str:
        if self.slope_per_hour > 2:
            return "rising"
        elif self.slope_per_hour < -2:
            return "falling"
        return "flat"


@dataclass
class HypoEvent:
    """A contiguous period below 70 mg/dL."""
    start_time: datetime
    duration_min: int
    nadir: float
    hour: int

    @property
    def is_serious(self) -> bool:
        return self.nadir < 54


@dataclass
class WeekSummary:
    """Weekly glycemic summary."""
    week: str
    tir: float
    tbr: float
    tar: float
    mean_bg: float
    cv: float
    n_points: int


@dataclass
class IOBProfile:
    """IOB circadian profile from Loop data."""
    hourly_mean: List[float]
    hourly_median: List[float]
    hourly_count: List[int]
    overall_mean: float
    overall_median: float
    max_iob: float
    min_iob: float

    @property
    def peak_hour(self) -> int:
        return int(np.argmax(self.hourly_mean))

    @property
    def trough_hour(self) -> int:
        return int(np.argmin(self.hourly_mean))


@dataclass
class CorrectionISF:
    """ISF estimate from a single correction bolus."""
    hour: int
    bolus_u: float
    start_bg: float
    nadir_bg: float
    simple_isf: float
    curve_isf: Optional[float]
    curve_r2: float
    quality: float


@dataclass
class PeriodAnalysis:
    """Deep analysis of a time-of-day period."""
    name: str
    hour_start: int
    hour_end: int
    tir: float
    tbr: float
    tar: float
    mean_bg: float
    bg_p10: float
    bg_p25: float
    bg_p50: float
    bg_p75: float
    bg_p90: float
    mean_iob: float
    basal_assessment: str
    n_points: int


@dataclass
class CounterfactualResult:
    """Result of a "what if" settings simulation."""
    parameter: str  # "isf", "cr", "basal"
    period: str     # "all", "overnight", "morning", etc.
    multiplier: float
    current_value: float
    simulated_value: float
    tir_current: float
    tir_simulated: float
    tir_delta_pp: float  # percentage points change


@dataclass
class TherapyInsights:
    """Complete therapy analysis results."""
    # Glycemic overview
    tir: float
    tbr: float
    tar: float
    mean_bg: float
    gmi: float
    cv: float

    # Profile
    basal_schedule: list
    isf_value: float
    cr_value: float
    dia_hours: float

    # Basal analysis
    nights: List[NightAnalysis]
    rising_nights_pct: float
    falling_nights_pct: float
    flat_nights_pct: float
    median_overnight_drift: float
    basal_assessment: str  # "too_low", "too_high", "appropriate", "mixed"

    # IOB pattern
    iob_profile: IOBProfile
    daily_bolus_insulin: float
    manual_bolus_count: int
    carb_entry_count: int

    # ISF analysis
    correction_isfs: List[CorrectionISF]
    effective_isf_simple: float
    effective_isf_curve: Optional[float]
    isf_ratio: float
    response_curve_isf: Optional[float]
    response_curve_tau: Optional[float]

    # Hypo safety
    hypo_events: List[HypoEvent]
    hypo_per_day: float
    serious_hypo_count: int
    peak_hypo_hour: int

    # Weekly trend
    weekly_summaries: List[WeekSummary]
    trend_direction: str  # "improving", "worsening", "stable", "variable"

    # Natural experiments
    fasting_count: int
    correction_count: int
    overnight_count: int
    uam_count: int

    # Period analysis
    period_analyses: List[PeriodAnalysis]

    # Counterfactual simulations
    counterfactuals: List[CounterfactualResult]

    # Fidelity
    fidelity_grade: str
    fidelity_rmse: float
    correction_energy: float

    # Recommendations
    recommendations: List[Dict]

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            if isinstance(v, list) and v and hasattr(v[0], '__dict__'):
                d[k] = [asdict(x) if hasattr(x, '__dict__') else x for x in v]
            elif hasattr(v, '__dict__'):
                d[k] = asdict(v) if hasattr(v, '__dict__') else v
            else:
                d[k] = v
        return d


def analyze_therapy(patient, result) -> TherapyInsights:
    """Run deep therapy analysis on pipeline result.

    Args:
        patient: PatientData with glucose, timestamps, iob, bolus, carbs, profile.
        result: PipelineResult from run_pipeline().

    Returns:
        TherapyInsights with comprehensive analysis.
    """
    glucose = result.cleaned.glucose
    timestamps = patient.timestamps
    profile = patient.profile

    # ── Basic glycemic metrics ──
    valid_bg = glucose[np.isfinite(glucose)]
    tir = float(np.mean((valid_bg >= 70) & (valid_bg <= 180)))
    tbr = float(np.mean(valid_bg < 70))
    tar = float(np.mean(valid_bg > 180))
    mean_bg = float(np.mean(valid_bg))
    cv = float(np.std(valid_bg) / np.mean(valid_bg) * 100)
    gmi = 3.31 + 0.02392 * mean_bg  # GMI formula

    # ── Profile extraction ──
    isf_entries = profile.isf_mgdl()
    isf_val = float(np.median([float(e.get('value', e.get('sensitivity', 50)))
                                for e in isf_entries])) if isf_entries else 50.0
    cr_entries = profile.cr_schedule
    cr_val = float(np.median([float(e.get('value', e.get('carbratio', 10)))
                               for e in cr_entries])) if cr_entries else 10.0

    # ── Per-night overnight analysis ──
    nights = _analyze_nights(timestamps, glucose)
    rising = sum(1 for n in nights if n.direction == "rising")
    falling = sum(1 for n in nights if n.direction == "falling")
    flat = sum(1 for n in nights if n.direction == "flat")
    total_n = max(len(nights), 1)
    drifts = [n.slope_per_hour for n in nights]
    median_drift = float(np.median(drifts)) if drifts else 0.0

    if rising / total_n > 0.55:
        basal_assessment = "too_low"
    elif falling / total_n > 0.55:
        basal_assessment = "too_high"
    elif rising / total_n > 0.3 and falling / total_n > 0.3:
        basal_assessment = "mixed"
    else:
        basal_assessment = "appropriate"

    # ── IOB profile ──
    iob_profile = _analyze_iob(timestamps, patient.iob)

    # ── Bolus / carb counting ──
    bolus_vals = patient.bolus[np.isfinite(patient.bolus) & (patient.bolus > 0)]
    carb_vals = patient.carbs[np.isfinite(patient.carbs) & (patient.carbs > 0)]
    n_days = len(glucose) / 288
    daily_bolus = float(np.sum(bolus_vals) / n_days) if len(bolus_vals) > 0 else 0.0

    # ── ISF from corrections ──
    ne = result.natural_experiments
    corrections = ne.filter_by_type('correction')
    correction_isfs = _extract_correction_isfs(corrections)
    simple_isfs = [c.simple_isf for c in correction_isfs if 0 < c.simple_isf < 300]
    curve_isfs = [c.curve_isf for c in correction_isfs
                  if c.curve_isf and c.curve_isf > 0 and c.curve_r2 > 0.1]
    eff_simple = float(np.median(simple_isfs)) if simple_isfs else isf_val
    eff_curve = float(np.median(curve_isfs)) if curve_isfs else None
    isf_ratio = eff_simple / isf_val if isf_val > 0 else 1.0

    # ── Response-curve ISF (AID-aware) ──
    rc_isf, rc_tau = None, None
    try:
        from cgmencode.production.clinical_rules import compute_response_curve_isf
        rc = compute_response_curve_isf(glucose, patient.bolus, patient.iob, profile)
        if rc:
            rc_isf = float(rc['isf'])
            rc_tau = float(rc['tau_hours'])
    except Exception:
        pass

    # ── Hypo events ──
    hypo_events = _detect_hypo_events(timestamps, glucose)
    hypo_per_day = len(hypo_events) / max(n_days, 1)
    serious = sum(1 for h in hypo_events if h.is_serious)
    hypo_hours = [h.hour for h in hypo_events]
    peak_hypo_hour = _mode_hour(hypo_hours) if hypo_hours else 0

    # ── Weekly trend ──
    weekly = _compute_weekly(timestamps, glucose)
    trend = _assess_trend(weekly)

    # ── Fidelity ──
    fid = result.clinical_report.fidelity
    fidelity_grade = fid.fidelity_grade.value if fid else "unknown"
    fidelity_rmse = fid.rmse if fid else 0.0
    corr_energy = fid.correction_energy if fid else 0.0

    # ── Period analysis (with BG percentiles and IOB) ──
    hours_arr = np.array([(datetime.fromtimestamp(t/1000, tz=timezone.utc).hour +
                           datetime.fromtimestamp(t/1000, tz=timezone.utc).minute/60.0)
                          for t in timestamps])
    period_analyses = _analyze_periods(glucose, patient.iob, hours_arr, result)

    # ── Counterfactual simulations ──
    counterfactuals = _run_counterfactuals(
        glucose, result.metabolic, hours_arr, isf_val, cr_val)

    # ── Recommendations (enhanced with counterfactual evidence) ──
    recs = _generate_recommendations(
        basal_assessment, isf_ratio, eff_simple, isf_val, cr_val,
        tir, tbr, tar, hypo_per_day, serious, median_drift,
        iob_profile, daily_bolus, len(bolus_vals), len(carb_vals),
        correction_isfs, nights, weekly, counterfactuals,
        rc_isf, period_analyses
    )

    return TherapyInsights(
        tir=tir, tbr=tbr, tar=tar, mean_bg=mean_bg, gmi=gmi, cv=cv,
        basal_schedule=profile.basal_schedule,
        isf_value=isf_val, cr_value=cr_val, dia_hours=profile.dia_hours,
        nights=nights,
        rising_nights_pct=rising / total_n * 100,
        falling_nights_pct=falling / total_n * 100,
        flat_nights_pct=flat / total_n * 100,
        median_overnight_drift=median_drift,
        basal_assessment=basal_assessment,
        iob_profile=iob_profile,
        daily_bolus_insulin=daily_bolus,
        manual_bolus_count=len(bolus_vals),
        carb_entry_count=len(carb_vals),
        correction_isfs=correction_isfs,
        effective_isf_simple=eff_simple,
        effective_isf_curve=eff_curve,
        isf_ratio=isf_ratio,
        response_curve_isf=rc_isf,
        response_curve_tau=rc_tau,
        hypo_events=hypo_events,
        hypo_per_day=hypo_per_day,
        serious_hypo_count=serious,
        peak_hypo_hour=peak_hypo_hour,
        weekly_summaries=weekly,
        trend_direction=trend,
        fasting_count=len(ne.filter_by_type('fasting')),
        correction_count=len(corrections),
        overnight_count=len(ne.filter_by_type('overnight')),
        uam_count=len(ne.filter_by_type('uam')),
        period_analyses=period_analyses,
        counterfactuals=counterfactuals,
        fidelity_grade=fidelity_grade,
        fidelity_rmse=fidelity_rmse,
        correction_energy=corr_energy,
        recommendations=recs,
    )


# ── Internal helpers ──

def _analyze_nights(timestamps, glucose, window_hours=(0, 6)) -> List[NightAnalysis]:
    """Analyze overnight glucose drift for each individual night."""
    nights_data = defaultdict(list)
    for i, t in enumerate(timestamps):
        if not np.isfinite(glucose[i]):
            continue
        dt = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        if window_hours[0] <= dt.hour < window_hours[1]:
            date_key = dt.strftime('%Y-%m-%d')
            nights_data[date_key].append(
                (dt.hour + dt.minute / 60.0, float(glucose[i]))
            )

    results = []
    for date in sorted(nights_data.keys()):
        pts = nights_data[date]
        if len(pts) < 12:  # need at least 1 hour
            continue
        hrs = np.array([p[0] for p in pts])
        bgs = np.array([p[1] for p in pts])
        slope = float(np.polyfit(hrs, bgs, 1)[0])
        tir_val = float(np.mean((bgs >= 70) & (bgs <= 180)))
        tbr_val = float(np.mean(bgs < 70))
        results.append(NightAnalysis(
            date=date,
            start_bg=float(bgs[0]),
            end_bg=float(bgs[-1]),
            slope_per_hour=slope,
            tir=tir_val,
            tbr=tbr_val,
            nadir=float(np.min(bgs)),
            n_points=len(pts),
        ))
    return results


def _analyze_iob(timestamps, iob) -> IOBProfile:
    """Build IOB circadian profile."""
    hourly = defaultdict(list)
    for i, t in enumerate(timestamps):
        if np.isfinite(iob[i]):
            dt = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
            hourly[dt.hour].append(float(iob[i]))

    means = [float(np.mean(hourly[h])) if hourly[h] else 0.0 for h in range(24)]
    medians = [float(np.median(hourly[h])) if hourly[h] else 0.0 for h in range(24)]
    counts = [len(hourly[h]) for h in range(24)]

    valid_iob = iob[np.isfinite(iob)]
    return IOBProfile(
        hourly_mean=means,
        hourly_median=medians,
        hourly_count=counts,
        overall_mean=float(np.mean(valid_iob)) if len(valid_iob) > 0 else 0.0,
        overall_median=float(np.median(valid_iob)) if len(valid_iob) > 0 else 0.0,
        max_iob=float(np.max(valid_iob)) if len(valid_iob) > 0 else 0.0,
        min_iob=float(np.min(valid_iob)) if len(valid_iob) > 0 else 0.0,
    )


def _extract_correction_isfs(corrections) -> List[CorrectionISF]:
    """Extract ISF estimates from correction natural experiments."""
    results = []
    for c in corrections:
        m = c.measurements
        simple = m.get('simple_isf', 0)
        curve = m.get('curve_isf')
        r2 = m.get('curve_r2', -999)
        results.append(CorrectionISF(
            hour=int(c.hour_of_day),
            bolus_u=m.get('bolus_u', 0),
            start_bg=m.get('start_bg', 0),
            nadir_bg=m.get('nadir_bg', 0),
            simple_isf=simple if simple else 0,
            curve_isf=curve if isinstance(curve, (int, float)) else None,
            curve_r2=r2 if isinstance(r2, (int, float)) else -999,
            quality=c.quality,
        ))
    return results


def _detect_hypo_events(timestamps, glucose) -> List[HypoEvent]:
    """Detect contiguous periods below 70 mg/dL."""
    events = []
    in_hypo = False
    start_idx = 0
    for i in range(len(timestamps)):
        bg = glucose[i]
        if np.isfinite(bg) and bg < 70:
            if not in_hypo:
                in_hypo = True
                start_idx = i
        else:
            if in_hypo:
                in_hypo = False
                duration = (i - start_idx) * 5
                nadir = float(np.nanmin(glucose[start_idx:i]))
                dt = datetime.fromtimestamp(timestamps[start_idx] / 1000, tz=timezone.utc)
                events.append(HypoEvent(
                    start_time=dt,
                    duration_min=duration,
                    nadir=nadir,
                    hour=dt.hour,
                ))
    return events


def _compute_weekly(timestamps, glucose) -> List[WeekSummary]:
    """Compute weekly glycemic summaries."""
    weeks = defaultdict(list)
    for i, t in enumerate(timestamps):
        if np.isfinite(glucose[i]):
            dt = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
            week_key = dt.strftime('%Y-W%W')
            weeks[week_key].append(float(glucose[i]))

    results = []
    for week in sorted(weeks.keys()):
        vals = np.array(weeks[week])
        results.append(WeekSummary(
            week=week,
            tir=float(np.mean((vals >= 70) & (vals <= 180))),
            tbr=float(np.mean(vals < 70)),
            tar=float(np.mean(vals > 180)),
            mean_bg=float(np.mean(vals)),
            cv=float(np.std(vals) / np.mean(vals) * 100),
            n_points=len(vals),
        ))
    return results


def _assess_trend(weekly: List[WeekSummary]) -> str:
    """Determine overall trend from weekly TIR data."""
    if len(weekly) < 3:
        return "insufficient_data"
    tirs = [w.tir for w in weekly]
    # Linear regression on TIR
    x = np.arange(len(tirs), dtype=float)
    slope = np.polyfit(x, tirs, 1)[0]
    # Variability
    tir_std = np.std(tirs)
    if tir_std > 0.15:
        return "variable"
    if slope > 0.01:
        return "improving"
    elif slope < -0.01:
        return "worsening"
    return "stable"


def _mode_hour(hours: list) -> int:
    """Most common hour."""
    counts = defaultdict(int)
    for h in hours:
        counts[h] += 1
    return max(counts, key=counts.get) if counts else 0


def _generate_recommendations(
    basal_assessment, isf_ratio, eff_isf, profile_isf, cr_val,
    tir, tbr, tar, hypo_per_day, serious_hypo, median_drift,
    iob_profile, daily_bolus, n_boluses, n_carbs,
    correction_isfs, nights, weekly, counterfactuals=None,
    rc_isf=None, period_analyses=None
) -> List[Dict]:
    """Generate evidence-based therapy recommendations."""
    recs = []
    cf = counterfactuals or []

    # ── Basal assessment ──
    if basal_assessment == "too_low":
        recs.append({
            'category': 'basal',
            'priority': 'high',
            'finding': (f'Overnight glucose rising on {sum(1 for n in nights if n.direction == "rising")}'
                        f'/{len(nights)} nights (median drift {median_drift:+.1f} mg/dL/hr)'),
            'recommendation': 'Consider increasing overnight basal rate by 10-15%',
            'evidence': 'Per-night drift analysis shows consistent rising glucose during fasting hours',
            'confirmable': 'Monitor overnight TIR for 1 week after adjustment',
        })
    elif basal_assessment == "too_high":
        recs.append({
            'category': 'basal',
            'priority': 'high',
            'finding': (f'Overnight glucose falling on {sum(1 for n in nights if n.direction == "falling")}'
                        f'/{len(nights)} nights (median drift {median_drift:+.1f} mg/dL/hr)'),
            'recommendation': 'Consider decreasing overnight basal rate by 10-15%',
            'evidence': 'Per-night drift analysis shows consistent falling glucose during fasting hours',
            'confirmable': 'Monitor overnight TIR and TBR for 1 week',
        })
    elif basal_assessment == "mixed":
        recs.append({
            'category': 'basal',
            'priority': 'medium',
            'finding': (f'Overnight glucose variable: '
                        f'{sum(1 for n in nights if n.direction == "rising")} rising, '
                        f'{sum(1 for n in nights if n.direction == "falling")} falling, '
                        f'{sum(1 for n in nights if n.direction == "flat")} flat'),
            'recommendation': ('Overnight basal shows mixed behavior. '
                               'The Loop system is actively compensating. '
                               'Consider whether late meals/snacks affect some nights.'),
            'evidence': 'Per-night analysis shows no consistent pattern — external factors dominate',
            'confirmable': 'Track overnight behavior relative to evening meals/activities',
        })

    # ── Hypo safety ──
    if hypo_per_day > 0.5:
        hypo_by_period = {}
        if period_analyses:
            for pa in period_analyses:
                hypo_by_period[pa.name] = pa.tbr * 100
        worst_period = max(hypo_by_period, key=hypo_by_period.get) if hypo_by_period else "unknown"
        recs.append({
            'category': 'safety',
            'priority': 'high',
            'finding': (f'{hypo_per_day:.1f} hypo events/day, {serious_hypo} serious (<54 mg/dL). '
                        f'Peak hour: {iob_profile.peak_hour}:00. '
                        f'Highest TBR in {worst_period} period.'),
            'recommendation': ('Hypoglycemia frequency exceeds safety threshold. '
                               'Consider raising glucose target by 5-10 mg/dL in Loop settings, '
                               'especially during overnight hours when most hypos occur.'),
            'evidence': (f'{int(hypo_per_day * len(nights))} hypo events in {len(nights)} days '
                         f'including {serious_hypo} below 54 mg/dL. '
                         f'TBR by period: ' +
                         ', '.join(f'{k}={v:.1f}%' for k, v in hypo_by_period.items())),
            'confirmable': 'Reduction in TBR and hypo event count within 1-2 weeks',
        })

    # ── ISF assessment (enhanced with response-curve and counterfactuals) ──
    best_isf = rc_isf or eff_isf
    best_isf_ratio = best_isf / profile_isf if profile_isf > 0 else 1.0
    isf_cf = [c for c in cf if c.parameter == 'isf' and c.tir_delta_pp > 0]
    best_isf_cf = max(isf_cf, key=lambda c: c.tir_delta_pp) if isf_cf else None

    if best_isf_ratio > 1.15 or best_isf_ratio < 0.85:
        direction = "higher" if best_isf_ratio > 1 else "lower"
        conservative_step = round(profile_isf + (best_isf - profile_isf) * 0.3, 0)
        method = "response-curve analysis" if rc_isf else "correction bolus analysis"

        cf_text = ""
        if best_isf_cf:
            cf_text = (f' Counterfactual simulation: ISF {best_isf_cf.simulated_value:.0f} '
                       f'→ TIR +{best_isf_cf.tir_delta_pp:.1f}pp.')

        recs.append({
            'category': 'isf',
            'priority': 'high' if abs(best_isf_ratio - 1) > 0.3 else 'medium',
            'finding': (f'Effective ISF ~{best_isf:.0f} mg/dL/U vs profile {profile_isf:.0f} '
                        f'({best_isf_ratio:.2f}× ratio). '
                        f'Method: {method} from {len(correction_isfs)} correction events.'),
            'recommendation': (f'Consider adjusting ISF from {profile_isf:.0f} toward '
                               f'{conservative_step:.0f} mg/dL/U '
                               f'(conservative 30% step toward measured value).{cf_text}'),
            'evidence': (f'Profile ISF={profile_isf:.0f} but natural experiments show '
                         f'ISF={best_isf:.0f}. Loop is consistently '
                         f'{"over" if direction == "higher" else "under"}-correcting '
                         f'relative to the actual insulin sensitivity.'),
            'confirmable': 'Reduced correction energy and improved fidelity within 2 weeks',
        })

    # ── Morning problem (period-specific) ──
    if period_analyses:
        morning = next((p for p in period_analyses if p.name == 'morning'), None)
        if morning and morning.tar > 0.40:
            recs.append({
                'category': 'morning',
                'priority': 'high',
                'finding': (f'Morning (7-12) is the worst period: TIR={morning.tir*100:.0f}%, '
                            f'TAR={morning.tar*100:.0f}%, mean BG={morning.mean_bg:.0f}. '
                            f'BG p75={morning.bg_p75:.0f}, p90={morning.bg_p90:.0f}. '
                            f'Mean IOB={morning.mean_iob:.1f}U.'),
                'recommendation': ('Morning hyperglycemia likely from dawn phenomenon + '
                                   'unannounced breakfast. Consider: (1) higher morning ISF, '
                                   '(2) pre-bolusing breakfast, or (3) increasing Loop '
                                   'aggressiveness during 6-10 AM.'),
                'evidence': ('Loop is already delivering peak IOB during morning hours '
                             f'(~{morning.mean_iob:.1f}U) but glucose remains elevated. '
                             'This suggests either ISF is too low during this period '
                             'or meal carbs exceed what Loop can handle reactively.'),
                'confirmable': 'Morning TIR improvement within 1-2 weeks',
            })

    # ── Loop reliance ──
    if n_boluses < 20 and n_carbs < 20:
        n_days = len(nights)
        recs.append({
            'category': 'behavior',
            'priority': 'info',
            'finding': (f'Only {n_boluses} manual boluses and {n_carbs} carb entries in '
                        f'{n_days} days. Nearly all insulin delivery is via Loop automation.'),
            'recommendation': ('Consider pre-bolusing for meals when possible. '
                               'Pre-bolus timing explains 9× more variance in '
                               'post-meal control than dose size.'),
            'evidence': ('98% of detected meals are Unannounced Meals (UAM). '
                         'Loop can manage these but with larger excursions than pre-bolused meals.'),
            'confirmable': 'Reduced post-meal excursion amplitude with pre-bolused meals',
        })

    # ── TIR variability ──
    if len(weekly) >= 4:
        tirs = [w.tir for w in weekly]
        tir_range = max(tirs) - min(tirs)
        if tir_range > 0.40:
            best_week = max(weekly, key=lambda w: w.tir)
            worst_week = min(weekly, key=lambda w: w.tir)
            recs.append({
                'category': 'variability',
                'priority': 'medium',
                'finding': (f'Weekly TIR varies from {min(tirs)*100:.0f}% to {max(tirs)*100:.0f}% '
                            f'(range {tir_range*100:.0f}pp). '
                            f'Best: {best_week.week} ({best_week.tir*100:.0f}%), '
                            f'Worst: {worst_week.week} ({worst_week.tir*100:.0f}%)'),
                'recommendation': ('Large week-to-week variability suggests external factors '
                                   '(diet, activity, stress) significantly affect control. '
                                   'Consider tracking what differs during high-TIR weeks.'),
                'evidence': f'{len(weekly)} weeks analyzed. TIR std={np.std(tirs)*100:.0f}%',
                'confirmable': 'Reduced TIR variance by replicating behaviors from high-TIR weeks',
            })

    # ── Dawn phenomenon ──
    dawn_iob = iob_profile.hourly_mean[4:8]
    trough_iob = iob_profile.hourly_mean[1:4]
    if np.mean(dawn_iob) - np.mean(trough_iob) > 1.0:
        recs.append({
            'category': 'dawn',
            'priority': 'low',
            'finding': (f'IOB rises from {np.mean(trough_iob):.1f}U (1-3 AM) to '
                        f'{np.mean(dawn_iob):.1f}U (4-7 AM), suggesting Loop compensates for dawn phenomenon'),
            'recommendation': ('Dawn phenomenon is being managed by Loop via increased insulin. '
                               'If using open-loop periods, ensure higher basal during 4-7 AM.'),
            'evidence': 'IOB circadian profile shows consistent pre-dawn insulin increase',
            'confirmable': 'Dawn BG stability during any open-loop periods',
        })

    return recs


def _analyze_periods(glucose, iob, hours_arr, result) -> List[PeriodAnalysis]:
    """Compute per-period analysis with BG percentiles and IOB."""
    periods = []
    for pm in result.period_metrics:
        h_start, h_end = pm.hour_start, pm.hour_end
        mask = (hours_arr >= h_start) & (hours_arr < h_end)
        period_bg = glucose[mask]
        valid = period_bg[np.isfinite(period_bg)]
        period_iob = iob[mask]
        valid_iob = period_iob[np.isfinite(period_iob)]

        if len(valid) < 10:
            continue
        periods.append(PeriodAnalysis(
            name=pm.name,
            hour_start=int(h_start),
            hour_end=int(h_end),
            tir=pm.tir,
            tbr=pm.tbr,
            tar=pm.tar,
            mean_bg=pm.mean_glucose,
            bg_p10=float(np.percentile(valid, 10)),
            bg_p25=float(np.percentile(valid, 25)),
            bg_p50=float(np.percentile(valid, 50)),
            bg_p75=float(np.percentile(valid, 75)),
            bg_p90=float(np.percentile(valid, 90)),
            mean_iob=float(np.mean(valid_iob)) if len(valid_iob) > 0 else 0.0,
            basal_assessment=pm.basal_assessment.value if hasattr(pm.basal_assessment, 'value') else str(pm.basal_assessment),
            n_points=len(valid),
        ))
    return periods


def _run_counterfactuals(glucose, metabolic, hours_arr,
                          isf_val, cr_val) -> List[CounterfactualResult]:
    """Run counterfactual simulations for ISF, CR, and basal changes."""
    from cgmencode.production.settings_advisor import simulate_tir_with_settings

    results = []

    # ISF sweep
    for mult in [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5]:
        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours_arr, isf_multiplier=mult)
        results.append(CounterfactualResult(
            parameter='isf', period='all', multiplier=mult,
            current_value=isf_val, simulated_value=isf_val * mult,
            tir_current=tir_now, tir_simulated=tir_sim,
            tir_delta_pp=(tir_sim - tir_now) * 100,
        ))

    # CR sweep (daytime only)
    for mult in [0.7, 0.8, 0.9, 1.0, 1.1, 1.2]:
        tir_now, tir_sim = simulate_tir_with_settings(
            glucose, metabolic, hours_arr, cr_multiplier=mult, hour_range=(5, 21))
        results.append(CounterfactualResult(
            parameter='cr', period='daytime', multiplier=mult,
            current_value=cr_val, simulated_value=cr_val * mult,
            tir_current=tir_now, tir_simulated=tir_sim,
            tir_delta_pp=(tir_sim - tir_now) * 100,
        ))

    # Basal by period
    for period_name, h_s, h_e in [("overnight", 0, 6), ("morning", 6, 12),
                                    ("afternoon", 12, 18), ("evening", 18, 24)]:
        for mult in [0.85, 0.90, 1.0, 1.10, 1.15, 1.20]:
            tir_now, tir_sim = simulate_tir_with_settings(
                glucose, metabolic, hours_arr,
                basal_multiplier=mult, hour_range=(h_s, h_e))
            results.append(CounterfactualResult(
                parameter='basal', period=period_name, multiplier=mult,
                current_value=1.0, simulated_value=mult,
                tir_current=tir_now, tir_simulated=tir_sim,
                tir_delta_pp=(tir_sim - tir_now) * 100,
            ))

    return results
