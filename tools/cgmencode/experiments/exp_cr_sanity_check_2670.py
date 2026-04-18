#!/usr/bin/env python3
"""
EXP-2670: CR Sanity-Check Contrast Visualization

PURPOSE: Help clinicians and patients build confidence in CR by showing how
estimated meal sizes change with different CR values. The key insight is that
carbs_estimated = |∫residual| × CR / ISF, so estimated carbs scale LINEARLY
with CR. By sweeping CR and comparing estimated meal profiles against the
patient's known eating patterns, the "right" CR is the one where detected
meals match anecdotal experience.

DESIGN:
  1. Detect all MEAL + UAM(meal subtype) windows via NE detector
  2. Group by meal period (breakfast 5-10, lunch 11-14, dinner 17-22, snack)
  3. For CR range [profile × 0.5 .. profile × 2.0], rescale estimated carbs
  4. Show: meal tally (CR-independent), size distributions per period per CR
  5. Highlight the CR where sizes best match typical real-world ranges

VALIDATION:
  - Meal tally must be CR-independent (detection doesn't change, only sizing)
  - At profile_CR, estimates should match production pipeline output
  - Rescaling: new_estimate = carbs_estimated × new_CR / profile_CR

PRIOR ART:
  - EXP-441/446: meal counting (2.0-2.2 meals/day via supply×demand)
  - EXP-486: dessert detection (18% of dinners, 123min hysteresis)
  - EXP-1341: carb estimation comparison (oref0 r=0.368, physics r=0.093)
  - EXP-1559: detection config sensitivity (90min hysteresis optimal)
  - EXP-2573: tiered CR optimization (small/medium/large meals)
"""

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'externals' / 'experiments'

# Meal period definitions (hour ranges)
MEAL_PERIODS = {
    'breakfast': (5, 10),
    'lunch': (11, 14),
    'dinner': (17, 22),
    'snack': (0, 5),    # late night / early morning
}

# Meal quality filters — real meals cause glucose to RISE.
# Overnight EGP / correction events have high demand but flat or falling
# glucose (AID is fighting them). These thresholds separate the two.
MIN_EXCURSION_MG_DL = 30   # ≥30 mg/dL rise in 2h post-peak
OVERNIGHT_MASK = (0, 5)     # Exclude 0-5h (hepatic EGP, not dietary)

# Dessert hysteresis: merge events within this window (min) after dinner
# into the dinner total. EXP-486 found 18% of dinners have dessert at
# mean gap 123 min. Patient c data shows median gap 170 min, so we
# extend to 180 min to capture the majority of dessert events.
DESSERT_MERGE_WINDOW_MIN = 180

# Typical meal size ranges (g) for face-validity check
# Based on dietitian training: 75g regimented meals, real-world variation
# Dinner range includes dessert (merged via hysteresis)
TYPICAL_RANGES = {
    'breakfast': (20, 60),
    'lunch': (40, 75),
    'dinner': (50, 200),
    'snack': (10, 30),
}

# CR multiplier sweep
CR_MULTIPLIERS = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.7, 2.0]


@dataclass
class MealEvent:
    """A detected meal with metadata for CR contrast analysis."""
    hour: float
    period: str
    carbs_estimated_g: float    # at profile CR
    excursion_mg_dl: float
    bolus_u: float
    pre_meal_bg: Optional[float]
    is_announced: bool
    quality: float
    source: str                 # 'MEAL' or 'UAM'
    start_idx: int = 0          # index in dataframe for temporal proximity


@dataclass
class CRContrastResult:
    """Result of CR contrast analysis for one patient."""
    patient_id: str
    profile_cr: float
    profile_isf: float
    n_meals: int
    meals_per_day: float
    by_period: Dict[str, int]
    cr_sweep: Dict[str, Dict[str, Dict]]  # cr_label -> period -> stats
    best_fit_cr_mult: float                # multiplier where sizes best match typical
    best_fit_cr_abs: float                 # absolute CR value
    plausibility_scores: Dict[str, float]  # cr_label -> plausibility score


def classify_meal_period(hour: float) -> str:
    """Assign a meal to a period based on hour of day."""
    for period, (lo, hi) in MEAL_PERIODS.items():
        if lo <= hour < hi:
            return period
    # Hours 10-11 → lunch, 14-17 → snack, 22-24 → snack
    if 10 <= hour < 11:
        return 'lunch'
    if 14 <= hour < 17:
        return 'snack'
    return 'snack'


def merge_desserts(events: List[MealEvent]) -> List[MealEvent]:
    """Merge dessert/snack events that follow dinner within hysteresis window.

    EXP-486 found ~18% of dinners have dessert, mean gap 123min.
    Patient c data shows median gap 170min.

    Uses start_idx proximity (in 5-min steps) for same-day matching,
    not hour-of-day which would incorrectly merge across days.
    """
    if not events:
        return events

    merge_steps = int(DESSERT_MERGE_WINDOW_MIN / 5)  # 180min / 5 = 36 steps
    dinners = [e for e in events if e.period == 'dinner']
    merged_ids = set()

    for dinner in dinners:
        for e in events:
            if id(e) in merged_ids or id(e) == id(dinner):
                continue
            if e.period != 'snack':
                continue
            # Check temporal proximity via start_idx (5-min steps)
            gap_steps = e.start_idx - dinner.start_idx
            if 0 < gap_steps <= merge_steps:
                dinner.carbs_estimated_g += e.carbs_estimated_g
                dinner.excursion_mg_dl = max(dinner.excursion_mg_dl, e.excursion_mg_dl)
                dinner.bolus_u += e.bolus_u
                merged_ids.add(id(e))

    return [e for e in events if id(e) not in merged_ids]


def extract_meal_events(census, profile_cr: float, min_quality: float = 0.5) -> List[MealEvent]:
    """Extract meal events from NE census for CR contrast analysis.

    Includes:
      - MEAL windows with carbs_estimated_g >= 10g
      - UAM windows with subtype='meal' and carbs_estimated_g >= 15g
    Higher thresholds than CR optimizer to focus on substantial meals
    that patients can verify against anecdotal experience.

    Applies dessert merge: events within DESSERT_MERGE_WINDOW_MIN of a
    dinner event are folded into that dinner (summing carbs), matching
    the EXP-486 finding that ~18% of dinners have dessert at ~123min gap.
    """
    events = []

    for exp in census.experiments:
        m = exp.measurements
        if exp.exp_type.value == 'meal':
            # Prefer residual-estimated carbs; fall back to entered carbs
            cg = m.get('carbs_estimated_g') or m.get('carbs_g', 0)
            if cg is None or cg < 10.0:
                continue
            if exp.quality < min_quality:
                continue
            events.append(MealEvent(
                hour=exp.hour_of_day,
                period=classify_meal_period(exp.hour_of_day),
                carbs_estimated_g=float(cg),
                excursion_mg_dl=m.get('excursion_mg_dl', 0),
                bolus_u=m.get('bolus_u', 0),
                pre_meal_bg=m.get('pre_meal_bg'),
                is_announced=m.get('is_announced', True),
                quality=exp.quality,
                source='MEAL',
                start_idx=exp.start_idx,
            ))
        elif exp.exp_type.value == 'uam':
            if m.get('subtype') != 'meal':
                continue
            cg = m.get('carbs_estimated_g')
            if cg is None or cg < 15.0:
                continue
            if exp.quality < min_quality:
                continue
            events.append(MealEvent(
                hour=exp.hour_of_day,
                period=classify_meal_period(exp.hour_of_day),
                carbs_estimated_g=cg,
                excursion_mg_dl=m.get('excursion_mg_dl', 0),
                bolus_u=m.get('bolus_u', 0),
                pre_meal_bg=m.get('pre_meal_bg'),
                is_announced=False,
                quality=exp.quality,
                source='UAM',
                start_idx=exp.start_idx,
            ))

    return merge_desserts(events)


def compute_period_stats(carbs_list: List[float]) -> Dict:
    """Compute statistics for a list of carb estimates."""
    if not carbs_list:
        return {'n': 0, 'median': None, 'mean': None, 'p25': None, 'p75': None,
                'min': None, 'max': None}
    arr = np.array(carbs_list)
    return {
        'n': len(arr),
        'median': round(float(np.median(arr)), 1),
        'mean': round(float(np.mean(arr)), 1),
        'p25': round(float(np.percentile(arr, 25)), 1),
        'p75': round(float(np.percentile(arr, 75)), 1),
        'min': round(float(np.min(arr)), 1),
        'max': round(float(np.max(arr)), 1),
    }


def plausibility_score(period_stats: Dict[str, Dict], typical: Dict[str, Tuple] = None) -> float:
    """Score how well estimated meal sizes match typical ranges.

    Returns 0-1 where 1 = all period medians fall within typical ranges.
    """
    if typical is None:
        typical = TYPICAL_RANGES
    score = 0.0
    n_scored = 0
    for period, (lo, hi) in typical.items():
        stats = period_stats.get(period, {})
        median = stats.get('median')
        if median is None:
            continue
        n_scored += 1
        if lo <= median <= hi:
            score += 1.0
        else:
            # Partial credit: distance from range as fraction
            if median < lo:
                score += max(0, 1.0 - (lo - median) / lo)
            else:
                score += max(0, 1.0 - (median - hi) / hi)
    return round(score / max(n_scored, 1), 3)


def cr_contrast_analysis(
    census,
    profile_cr: float,
    profile_isf: float,
    patient_id: str = 'unknown',
    days_analyzed: float = 1.0,
    min_quality: float = 0.3,
    cr_multipliers: List[float] = None,
) -> CRContrastResult:
    """Run CR contrast analysis on detected meal windows.

    Since carbs_estimated = |∫residual| × CR / ISF, and we want to show
    what meals look like at different CRs, we simply rescale:
        new_estimate = carbs_estimated × new_CR / profile_CR

    This is mathematically exact — no need to re-run detection.
    """
    if cr_multipliers is None:
        cr_multipliers = CR_MULTIPLIERS

    events = extract_meal_events(census, profile_cr, min_quality)

    # Meal tally (CR-independent)
    by_period = defaultdict(int)
    for e in events:
        by_period[e.period] += 1
    meals_per_day = len(events) / max(days_analyzed, 1)

    # CR sweep: rescale estimates at each multiplier
    cr_sweep = {}
    plausibility_scores = {}

    for mult in cr_multipliers:
        cr_label = f'{mult:.1f}x'
        cr_abs = profile_cr * mult

        period_carbs = defaultdict(list)
        for e in events:
            rescaled = e.carbs_estimated_g * mult  # linear rescaling
            period_carbs[e.period].append(rescaled)

        period_stats = {}
        for period in ['breakfast', 'lunch', 'dinner', 'snack']:
            period_stats[period] = compute_period_stats(period_carbs[period])

        cr_sweep[cr_label] = {
            'cr_absolute': round(cr_abs, 1),
            'cr_multiplier': mult,
            'periods': period_stats,
        }
        plausibility_scores[cr_label] = plausibility_score(period_stats)

    # Find best-fit CR
    best_label = max(plausibility_scores, key=plausibility_scores.get) if plausibility_scores else '1.0x'
    best_mult = cr_sweep[best_label]['cr_multiplier'] if best_label in cr_sweep else 1.0
    best_abs = profile_cr * best_mult

    return CRContrastResult(
        patient_id=patient_id,
        profile_cr=profile_cr,
        profile_isf=profile_isf,
        n_meals=len(events),
        meals_per_day=round(meals_per_day, 1),
        by_period=dict(by_period),
        cr_sweep=cr_sweep,
        best_fit_cr_mult=best_mult,
        best_fit_cr_abs=round(best_abs, 1),
        plausibility_scores=plausibility_scores,
    )


def format_contrast_table(result: CRContrastResult) -> str:
    """Format a human-readable CR contrast table for clinical use."""
    lines = []
    lines.append(f'CR Sanity Check — Patient {result.patient_id}')
    lines.append(f'Profile CR: {result.profile_cr}  ISF: {result.profile_isf}')
    lines.append(f'Meals detected: {result.n_meals} ({result.meals_per_day}/day)')
    lines.append(f'  breakfast={result.by_period.get("breakfast", 0)}, '
                 f'lunch={result.by_period.get("lunch", 0)}, '
                 f'dinner={result.by_period.get("dinner", 0)}, '
                 f'snack={result.by_period.get("snack", 0)}')
    lines.append('')

    # Header
    header = f'{"CR":>6s} {"Abs":>5s} | {"Breakfast":>12s} | {"Lunch":>12s} | {"Dinner":>12s} | {"Snack":>12s} | {"Fit":>5s}'
    lines.append(header)
    lines.append('-' * len(header))

    for label in sorted(result.cr_sweep.keys(), key=lambda x: result.cr_sweep[x]['cr_multiplier']):
        entry = result.cr_sweep[label]
        cr_abs = entry['cr_absolute']
        fit = result.plausibility_scores.get(label, 0)

        cells = [f'{label:>6s}', f'{cr_abs:5.1f}']
        for period in ['breakfast', 'lunch', 'dinner', 'snack']:
            stats = entry['periods'].get(period, {})
            med = stats.get('median')
            if med is not None:
                p25 = stats.get('p25', 0)
                p75 = stats.get('p75', 0)
                cells.append(f'{med:5.0f} [{p25:.0f}-{p75:.0f}]')
            else:
                cells.append(f'{"—":>12s}')

        marker = ' ◀ BEST' if label == f'{result.best_fit_cr_mult:.1f}x' else ''
        cells.append(f'{fit:5.3f}{marker}')
        lines.append(' | '.join(cells))

    lines.append('')
    lines.append(f'Best-fit CR: {result.best_fit_cr_abs} '
                 f'({result.best_fit_cr_mult:.1f}× profile)')
    lines.append('')
    lines.append('Typical meal ranges (g): '
                 'breakfast 20-60, lunch 40-75, dinner 50-200, snack 10-30')
    lines.append('The best-fit CR is where estimated meal sizes most closely '
                 'match typical real-world portions.')
    return '\n'.join(lines)


def generate_cr_contrast_figure(result: CRContrastResult, output_path: str = None):
    """Generate matplotlib figure showing CR contrast visualization.

    Panel layout:
      Top-left: Meal tally by period (bar chart, CR-independent)
      Top-right: Plausibility score vs CR (line, highlight best)
      Bottom: Meal size at 3 CR values (box plots per period)
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
    except ImportError:
        print('  matplotlib not available, skipping figure')
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'EXP-2670: CR Sanity Check — Patient {result.patient_id}',
                 fontsize=14, fontweight='bold')

    periods = ['breakfast', 'lunch', 'dinner', 'snack']
    period_colors = {'breakfast': '#FFB347', 'lunch': '#87CEEB',
                     'dinner': '#DDA0DD', 'snack': '#90EE90'}

    # Panel 1: Meal tally (CR-independent)
    ax1 = axes[0, 0]
    counts = [result.by_period.get(p, 0) for p in periods]
    bars = ax1.bar(periods, counts, color=[period_colors[p] for p in periods],
                   edgecolor='black', linewidth=0.5)
    ax1.set_ylabel('Count')
    ax1.set_title(f'Detected Meals: {result.n_meals} ({result.meals_per_day}/day)')
    for bar, count in zip(bars, counts):
        if count > 0:
            ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                     str(count), ha='center', va='bottom', fontsize=10)

    # Panel 2: Plausibility score vs CR
    ax2 = axes[0, 1]
    sorted_labels = sorted(result.cr_sweep.keys(),
                           key=lambda x: result.cr_sweep[x]['cr_multiplier'])
    cr_vals = [result.cr_sweep[l]['cr_absolute'] for l in sorted_labels]
    scores = [result.plausibility_scores.get(l, 0) for l in sorted_labels]
    ax2.plot(cr_vals, scores, 'o-', color='#4169E1', linewidth=2, markersize=6)
    best_idx = scores.index(max(scores)) if scores else 0
    ax2.plot(cr_vals[best_idx], scores[best_idx], '*', color='red',
             markersize=15, zorder=5, label=f'Best: CR={result.best_fit_cr_abs}')
    ax2.axvline(result.profile_cr, color='gray', linestyle='--', alpha=0.5,
                label=f'Profile: CR={result.profile_cr}')
    ax2.set_xlabel('Carb Ratio (g/U)')
    ax2.set_ylabel('Plausibility Score')
    ax2.set_title('Which CR Makes Meals Look Right?')
    ax2.legend(fontsize=9)
    ax2.set_ylim(0, 1.05)

    # Panel 3 & 4: Meal sizes at low/profile/high CR (3 panels merged)
    ax_bottom = fig.add_subplot(2, 1, 2)
    axes[1, 0].set_visible(False)
    axes[1, 1].set_visible(False)

    # Pick 3 CRs: low (0.7x), profile (1.0x), high (1.5x)
    display_mults = [0.7, 1.0, 1.5]
    display_labels = []
    display_data = {p: [] for p in periods}

    for mult in display_mults:
        label = f'{mult:.1f}x'
        if label not in result.cr_sweep:
            closest = min(result.cr_sweep.keys(),
                          key=lambda l: abs(result.cr_sweep[l]['cr_multiplier'] - mult))
            label = closest
        display_labels.append(label)
        entry = result.cr_sweep[label]
        for p in periods:
            stats = entry['periods'].get(p, {})
            display_data[p].append(stats)

    x_base = np.arange(len(periods))
    width = 0.25
    cr_colors = ['#FF6B6B', '#4ECDC4', '#45B7D1']

    for i, (label, color) in enumerate(zip(display_labels, cr_colors)):
        cr_abs = result.cr_sweep[label]['cr_absolute']
        medians = []
        lows = []
        highs = []
        for p in periods:
            stats = display_data[p][i]
            med = stats.get('median', 0) or 0
            p25 = stats.get('p25', 0) or 0
            p75 = stats.get('p75', 0) or 0
            medians.append(med)
            lows.append(med - p25)
            highs.append(p75 - med)

        ax_bottom.bar(x_base + i * width, medians, width,
                      yerr=[lows, highs], capsize=3,
                      color=color, edgecolor='black', linewidth=0.5,
                      label=f'CR={cr_abs:.0f} ({label})',
                      alpha=0.8)

    # Overlay typical ranges as shaded rectangles
    for j, p in enumerate(periods):
        lo, hi = TYPICAL_RANGES[p]
        rect = Rectangle((j - 0.15, lo), len(display_mults) * width + 0.1,
                          hi - lo, alpha=0.12, color='green', linewidth=0)
        ax_bottom.add_patch(rect)

    ax_bottom.set_xticks(x_base + width)
    ax_bottom.set_xticklabels([p.capitalize() for p in periods])
    ax_bottom.set_ylabel('Estimated Carbs (g)')
    ax_bottom.set_title('Meal Size Estimates at Different CRs (green = typical range)')
    ax_bottom.legend(fontsize=9, loc='upper left')
    ax_bottom.set_ylim(0, max(200, ax_bottom.get_ylim()[1]))

    plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f'  Saved figure: {output_path}')
    plt.close()


def main():
    """Run CR sanity check against NS patient cohort.

    Uses EXP-483 supply×demand throughput meal detector with
    precondition gating (READY days only), then estimates meal sizes
    via residual-integral method. This is the same approach that
    produces ~2.6 meals/day on READY days (population median).
    """
    t0 = time.time()
    print('=' * 70)
    print('EXP-2670: CR Sanity-Check Contrast Visualization')
    print('  Method: Supply×Demand throughput peaks (EXP-483)')
    print('  Sizing: Residual-integral carb estimation (EXP-748/753)')
    print('=' * 70)

    try:
        import pandas as pd
        from cgmencode.exp_metabolic_441 import compute_supply_demand
        from cgmencode.exp_refined_483 import (
            detect_meals_demand_weighted, assess_day_readiness
        )
        from cgmencode.production.natural_experiment_detector import (
            NaturalExperiment, NaturalExperimentType,
            NaturalExperimentCensus,
        )
    except ImportError as e:
        print(f'  Import error: {e}')
        print('  Run from project root with PYTHONPATH=tools')
        return

    NS_PATIENTS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k']
    df = pd.read_parquet('externals/ns-parquet/training/grid.parquet')

    all_results = {}

    for pid in NS_PATIENTS:
        print(f'\n  Patient {pid}:')
        pdf = df[df['patient_id'] == pid].copy()
        if len(pdf) < 288:
            print(f'    Skip: too few rows ({len(pdf)})')
            continue

        profile_cr = float(pdf['scheduled_cr'].median())
        profile_isf = float(pdf['scheduled_isf'].median())
        profile_basal = float(pdf['scheduled_basal_rate'].median())
        N = len(pdf)
        days = N / 288.0

        # Set datetime index + attrs for supply-demand computation
        pdf.index = pd.to_datetime(pdf['time'])
        pdf.attrs['cr_schedule'] = [{'value': profile_cr}]
        pdf.attrs['isf_schedule'] = [{'value': profile_isf}]
        pdf.attrs['basal_schedule'] = [{'value': profile_basal}]

        bg_col = 'glucose'
        bg = pdf[bg_col].values.astype(np.float64)

        # Compute supply×demand metabolic flux
        sd = compute_supply_demand(pdf, calibrate=True)

        # Detect meals via demand-weighted peaks
        peaks, dem_smooth = detect_meals_demand_weighted(pdf, None)

        # Compute residual for carb estimation
        dbg = np.zeros(N)
        valid = ~np.isnan(bg)
        dbg[1:] = np.where(valid[1:] & valid[:-1], bg[1:] - bg[:-1], 0)
        residual = dbg - sd['net']

        # READY-day gating: only peaks on days with good telemetry
        dates = pdf.index.date
        unique_dates = sorted(set(dates))
        ready_peaks = []
        for d in unique_dates:
            mask = dates == d
            idx = np.where(mask)[0]
            readiness = assess_day_readiness(bg[idx], sd['demand'][idx])
            if readiness['ready']:
                day_start, day_end = idx[0], idx[-1] + 1
                ready_peaks.extend(p for p in peaks if day_start <= p < day_end)

        print(f'    Raw peaks: {len(peaks)} ({len(peaks)/days:.1f}/day), '
              f'READY-gated: {len(ready_peaks)}')

        # Build NE census from demand peaks with carb estimation
        # Apply meal quality filters:
        #   1. Overnight mask: exclude 0-5h (hepatic EGP, not dietary)
        #   2. Glucose excursion ≥30 mg/dL: real meals cause BG to rise
        experiments = []
        n_overnight_masked = 0
        n_excursion_filtered = 0
        for p in ready_peaks:
            hour = pdf.index[p].hour + pdf.index[p].minute / 60.0

            # Filter 1: Overnight mask
            if OVERNIGHT_MASK[0] <= hour < OVERNIGHT_MASK[1]:
                n_overnight_masked += 1
                continue

            # Pre-meal BG
            pre_start = max(0, p - 6)
            pre_bg = float(np.nanmean(bg[pre_start:p])) if not np.all(np.isnan(bg[pre_start:p])) else 120.0

            # Post-meal window (2h = 24 steps for excursion check)
            end = min(N, p + 48)
            post_2h = bg[p:min(N, p + 24)]
            peak_bg = float(np.nanmax(post_2h)) if np.any(~np.isnan(post_2h)) else pre_bg
            excursion = peak_bg - pre_bg

            # Filter 2: Glucose excursion — real meals cause BG rise ≥30
            # Overnight EGP/correction events have high demand but flat BG
            if excursion < MIN_EXCURSION_MG_DL:
                n_excursion_filtered += 1
                continue

            # Extend for peak BG over full 4h window
            post_4h = bg[p:end]
            peak_bg_4h = float(np.nanmax(post_4h)) if np.any(~np.isnan(post_4h)) else peak_bg
            excursion_4h = peak_bg_4h - pre_bg

            # Residual-integral carb estimation
            r_end = min(N, end + 36)  # extend 3h for absorption tail
            resid_seg = residual[p:r_end]
            valid_resid = resid_seg[np.isfinite(resid_seg)]
            if len(valid_resid) > 6:
                resid_integral = float(np.sum(valid_resid))
                carbs_est = abs(resid_integral) * profile_cr / max(profile_isf, 1.0)
                carbs_est = round(max(0.0, carbs_est), 1)
            else:
                carbs_est = None

            # Bolus nearby (±15 min = ±3 steps)
            bolus_arr = np.nan_to_num(pdf['bolus'].values.astype(float), nan=0.0)
            bolus_window = bolus_arr[max(0, p - 3):min(N, p + 3)]
            meal_bolus = float(np.nansum(bolus_window))

            # Entered carbs nearby
            carbs_arr = np.nan_to_num(pdf['carbs'].values.astype(float), nan=0.0)
            carb_window = carbs_arr[max(0, p - 6):min(N, p + 6)]
            entered_carbs = float(np.nansum(carb_window))

            # Use best available carb estimate
            best_carbs = carbs_est if carbs_est and carbs_est > 3.0 else (
                entered_carbs if entered_carbs > 3.0 else None)
            if best_carbs is None or best_carbs < 5.0:
                continue

            experiments.append(NaturalExperiment(
                exp_type=NaturalExperimentType.MEAL,
                start_idx=p, end_idx=end,
                duration_minutes=(end - p) * 5,
                hour_of_day=hour,
                quality=0.8,
                measurements={
                    'carbs_estimated_g': best_carbs,
                    'carbs_entered_g': entered_carbs,
                    'excursion_mg_dl': round(excursion_4h, 1),
                    'bolus_u': round(meal_bolus, 2),
                    'pre_meal_bg': round(pre_bg, 1),
                    'peak_bg': round(peak_bg_4h, 1),
                    'is_announced': meal_bolus > 0.1 or entered_carbs > 3.0,
                },
            ))

        print(f'    Filtered: -{n_overnight_masked} overnight, '
              f'-{n_excursion_filtered} low-excursion (<{MIN_EXCURSION_MG_DL} mg/dL)')
        print(f'    Meals with carb estimates: {len(experiments)} '
              f'({len(experiments)/days:.1f}/day)')

        # Build census
        by_type = {'meal': len(experiments)}
        census = NaturalExperimentCensus(
            experiments=experiments,
            total_detected=len(experiments),
            by_type=by_type,
            quality_mean=0.8,
            days_analyzed=round(days, 1),
            per_day_rate=round(len(experiments) / max(days, 0.01), 1),
        )

        result = cr_contrast_analysis(
            census=census,
            profile_cr=profile_cr,
            profile_isf=profile_isf,
            patient_id=pid,
            days_analyzed=days,
        )

        print(format_contrast_table(result))
        all_results[pid] = asdict(result)

        # Generate per-patient figure
        fig_dir = Path('visualizations/cr-sanity-check')
        fig_dir.mkdir(parents=True, exist_ok=True)
        generate_cr_contrast_figure(
            result, str(fig_dir / f'fig_cr_contrast_{pid}.png'))

    # Population summary
    print('\n' + '=' * 70)
    print('Population Summary')
    print('=' * 70)
    for pid, r in all_results.items():
        print(f'  {pid}: profile CR={r["profile_cr"]:.0f}, '
              f'best-fit CR={r["best_fit_cr_abs"]}, '
              f'meals/day={r["meals_per_day"]}, '
              f'n={r["n_meals"]}')

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / 'exp-2670_cr_sanity_check.json'
    with open(out_path, 'w') as f:
        json.dump({
            'exp_id': 'EXP-2670',
            'purpose': 'CR sanity check via meal size contrast',
            'method': 'Supply×Demand throughput peaks (EXP-483) + '
                      'residual-integral carb estimation (EXP-748/753)',
            'gating': 'READY days only (CGM ≥70%, insulin ≥10%)',
            'typical_ranges': TYPICAL_RANGES,
            'cr_multipliers': CR_MULTIPLIERS,
            'patients': all_results,
        }, f, indent=2, default=str)
    print(f'\n  Saved: {out_path}')
    print(f'  Runtime: {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
