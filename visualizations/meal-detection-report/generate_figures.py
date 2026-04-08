#!/usr/bin/env python3
"""Generate figures for the Meal Detection via Supply × Demand report.

Produces 12 matplotlib figures illustrating how throughput (supply × demand)
enables meal detection even for 100% UAM patients.  Synthetic data is
calibrated to documented experimental results from EXP-441 through EXP-488.

Imports pharmacokinetic models directly from tools/cgmencode/continuous_pk.py
to guarantee figures always match the source of truth.
"""

import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from scipy.signal import find_peaks
import os

# ── import PK models from the codebase (source of truth) ───────────────
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from tools.cgmencode.continuous_pk import (
    _build_activity_kernel,
    _build_carb_kernel,
    _convolve_doses_with_kernel,
    _insulin_activity_at_t,
    _carb_absorption_rate_at_t,
    compute_hepatic_production,
)

OUT = os.path.dirname(os.path.abspath(__file__))
np.random.seed(42)

# ── colour palette ──────────────────────────────────────────────────────
C_SUPPLY  = '#2ecc71'   # green
C_DEMAND  = '#e74c3c'   # red
C_PRODUCT = '#9b59b6'   # purple
C_GLUCOSE = '#3498db'   # blue
C_HEPATIC = '#e67e22'   # orange
C_RESIDUAL = '#1abc9c'  # teal
C_CARB    = '#f1c40f'   # yellow
C_AC      = '#e74c3c'   # red
C_DC      = '#95a5a6'   # grey

DPI = 150

# ── PK parameters (continuous_pk.py defaults) ───────────────────────────
DIA_HOURS = 5.0          # Duration of Insulin Action (hours)
PEAK_MIN  = 55.0         # Time to peak insulin activity (minutes)
CARB_ABS_HOURS = 3.0     # Carb absorption time (hours)
INTERVAL_MIN   = 5       # Grid interval (minutes)
STEPS_PER_DAY  = 288     # 24h / 5min

# Pre-compute kernels once (reused by all figures)
_INSULIN_KERNEL = _build_activity_kernel(DIA_HOURS, PEAK_MIN, INTERVAL_MIN)
_CARB_KERNEL    = _build_carb_kernel(CARB_ABS_HOURS, INTERVAL_MIN)

# ═══════════════════════════════════════════════════════════════════════
# Thin wrappers around continuous_pk for synthetic data generation
# ═══════════════════════════════════════════════════════════════════════

_DIA_MIN = DIA_HOURS * 60
_ABS_MIN = CARB_ABS_HOURS * 60


def insulin_curve(t_min, dose=1.0):
    """Vectorized insulin activity at arbitrary time resolution.

    Calls continuous_pk._insulin_activity_at_t per point.
    Use for relative-time figures (phase lag, dessert detection).
    """
    return np.array([_insulin_activity_at_t(float(ti), dose, _DIA_MIN, PEAK_MIN)
                     for ti in t_min])


def carb_curve(t_min, carbs=50.0):
    """Vectorized carb absorption at arbitrary time resolution.

    Calls continuous_pk._carb_absorption_rate_at_t per point.
    """
    return np.array([_carb_absorption_rate_at_t(float(ti), carbs, _ABS_MIN)
                     for ti in t_min])

def make_insulin_activity(hours, boluses, isf=40, basal_rate=0.0):
    """Compute insulin demand signal from a list of (hour, dose) boluses.

    Returns demand in mg/dL per 5-min step (activity × ISF × interval).
    Optionally includes a steady-state basal contribution.
    """
    N = len(hours)
    bolus_arr = np.zeros(N)
    for bol_hr, bol_u in boluses:
        idx = int(round(bol_hr * 60 / INTERVAL_MIN))
        if 0 <= idx < N:
            bolus_arr[idx] += bol_u
    bolus_activity = _convolve_doses_with_kernel(bolus_arr, _INSULIN_KERNEL)

    basal_activity = np.zeros(N)
    if basal_rate > 0:
        micro_dose = basal_rate * INTERVAL_MIN / 60.0  # U per 5min
        basal_arr = np.full(N, micro_dose)
        basal_activity = _convolve_doses_with_kernel(basal_arr, _INSULIN_KERNEL)

    total_activity = bolus_activity + basal_activity
    return total_activity * INTERVAL_MIN * isf  # U/min × min × mg/dL/U → mg/dL per step


def make_carb_supply(hours, meals, isf=40, cr=10):
    """Compute carb supply signal from a list of (hour, grams) meals.

    Returns supply in mg/dL per 5-min step (rate × ISF/CR × interval).
    """
    N = len(hours)
    carb_arr = np.zeros(N)
    for meal_hr, meal_g in meals:
        idx = int(round(meal_hr * 60 / INTERVAL_MIN))
        if 0 <= idx < N:
            carb_arr[idx] += meal_g
    rate = _convolve_doses_with_kernel(carb_arr, _CARB_KERNEL)
    return rate * INTERVAL_MIN * (isf / max(cr, 1.0))  # g/min × min × (mg/dL)/g → mg/dL per step


def make_hepatic(hours, iob=None):
    """Hepatic glucose production using compute_hepatic_production().

    If iob is None, uses a reasonable default (steady-state ~0.5U).
    Returns mg/dL per 5-min step.
    """
    if iob is None:
        iob = np.full(len(hours), 0.5)
    return compute_hepatic_production(iob, hours, weight_kg=70.0)


def simulate_day(meals, boluses, hours, basal_rate=1.0, isf=40, cr=10):
    """Simulate a full day of supply, demand, glucose for visualization.

    Uses the real PK models from continuous_pk.py and keeps glucose
    near-flat (AID premise).
    """
    N = len(hours)

    hep = make_hepatic(hours)
    carb_sup = make_carb_supply(hours, meals, isf=isf, cr=cr)
    supply = hep + carb_sup

    demand = make_insulin_activity(hours, boluses, isf=isf, basal_rate=basal_rate)
    # Add hepatic baseline so demand ≈ supply at steady state
    demand += hep

    # Glucose: AID keeps glucose near-flat despite active flux underneath.
    target = 115
    glucose = np.full(N, float(target))
    t_min = hours * 60
    for meal_hr, meal_g in meals:
        t_rel = t_min - meal_hr * 60
        bump = np.where(t_rel > 0,
                        (meal_g / 20) * (t_rel / 20) * np.exp(1 - t_rel / 20),
                        0.0)
        glucose += bump
    noise = np.cumsum(np.random.normal(0, 0.15, N))
    noise -= np.linspace(noise[0], noise[-1], N)
    glucose += noise
    glucose = np.clip(glucose, 60, 250)

    net = supply - demand
    return supply, demand, hep, carb_sup, glucose, net


# ═══════════════════════════════════════════════════════════════════════
# Figure 1: The Throughput Concept — Supply × Demand amplifies meals
# ═══════════════════════════════════════════════════════════════════════

def fig01_throughput_concept():
    hours = np.linspace(0, 24, 288)
    meals = [(8, 60), (12.5, 45), (18.5, 70)]
    boluses = [(7.9, 5), (12.4, 4), (18.3, 6)]
    supply, demand, hep, carb_sup, glucose, net = simulate_day(
        meals, boluses, hours)

    product = supply * demand
    product_norm = product / np.max(product) * np.max(supply)

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)

    # Panel 1: Glucose — flat under AID
    ax = axes[0]
    ax.plot(hours, glucose, color=C_GLUCOSE, linewidth=2)
    ax.axhspan(70, 180, alpha=0.08, color='green')
    ax.set_ylabel('Glucose\n(mg/dL)', fontsize=11)
    ax.set_title('The Hidden Metabolic World: Flat Glucose Masks Active Flux',
                 fontsize=13, fontweight='bold')
    ax.set_ylim(60, 260)
    for mh, mg in meals:
        ax.axvline(mh, color=C_CARB, alpha=0.3, linestyle='--')
        ax.annotate(f'{mg}g', (mh, 250), fontsize=8, color=C_CARB, ha='center')

    # Panel 2: Supply and Demand — the hidden flux
    ax = axes[1]
    ax.fill_between(hours, supply, alpha=0.25, color=C_SUPPLY)
    ax.plot(hours, supply, color=C_SUPPLY, linewidth=2, label='Supply')
    ax.fill_between(hours, demand, alpha=0.25, color=C_DEMAND)
    ax.plot(hours, demand, color=C_DEMAND, linewidth=2, label='Demand')
    ax.plot(hours, hep, color=C_HEPATIC, linewidth=1, linestyle='--',
            label='Hepatic (DC)')
    ax.set_ylabel('Flux\n(mg/dL per 5min)', fontsize=11)
    ax.legend(loc='upper left', fontsize=9)

    # Panel 3: Product = throughput
    ax = axes[2]
    ax.fill_between(hours, product, alpha=0.3, color=C_PRODUCT)
    ax.plot(hours, product, color=C_PRODUCT, linewidth=2,
            label='Throughput = S × D')
    # Mark detected peaks
    peaks, props = find_peaks(product, prominence=np.max(product)*0.15,
                              distance=20)
    ax.plot(hours[peaks], product[peaks], 'v', color='black', markersize=10,
            label=f'{len(peaks)} meals detected')
    ax.set_ylabel('Throughput\n(S × D)', fontsize=11)
    ax.set_xlabel('Hour of Day', fontsize=11)
    ax.legend(loc='upper left', fontsize=9)

    for ax in axes:
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig01_throughput_concept.png'), dpi=DPI)
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 2: Spectral Power — 18× at meal frequencies
# ═══════════════════════════════════════════════════════════════════════

def fig02_spectral_power():
    bands = ['Noise\n(1h)', 'Basal\n(12h)', 'Circadian\n(24h)', 'Meal\n(3-5h)']
    glucose_power = [1.0, 1.0, 1.0, 1.0]
    throughput_power = [7.7, 6.1, 8.3, 18.2]

    x = np.arange(len(bands))
    w = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - w/2, glucose_power, w, label='Glucose',
                   color=C_GLUCOSE, alpha=0.8)
    bars2 = ax.bar(x + w/2, throughput_power, w, label='Throughput (S×D)',
                   color=C_PRODUCT, alpha=0.8)

    # Annotate the ratio
    for i, (g, t) in enumerate(zip(glucose_power, throughput_power)):
        ax.annotate(f'{t/g:.1f}×', (x[i] + w/2, t + 0.4),
                    ha='center', fontsize=12, fontweight='bold',
                    color=C_PRODUCT)

    ax.set_ylabel('Relative Spectral Power', fontsize=12)
    ax.set_title('Throughput Concentrates 18× More Power at Meal Frequencies\n'
                 '(EXP-444: FFT of 11-patient cohort)',
                 fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(bands, fontsize=11)
    ax.legend(fontsize=11)
    ax.set_ylim(0, 22)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig02_spectral_power.png'), dpi=DPI)
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 3: The Adjustment Journey — from raw to 2 meals/day
# ═══════════════════════════════════════════════════════════════════════

def fig03_adjustment_journey():
    stages = [
        'Raw Glucose\nPeaks',
        'Sum Flux\n|S-D|',
        'Hepatic\nDetrending',
        'Day-Local\nThresholds',
        'Precondition\nGating',
        'FINAL:\n2.0/day'
    ]
    # Documented progression of meals/day detected for live-split
    events = [5.6, 2.2, 2.5, 2.1, 2.0, 2.0]
    recall = [None, 82, 85, 89, 96, 96]

    fig, ax1 = plt.subplots(figsize=(12, 6))

    colors = ['#e74c3c', '#f39c12', '#f1c40f', '#2ecc71', '#27ae60', '#1a8a4a']
    bars = ax1.bar(range(len(stages)), events, color=colors, alpha=0.85,
                   edgecolor='white', linewidth=2)

    # Target line
    ax1.axhline(2.0, color='black', linestyle='--', linewidth=1.5,
                label='Expected: 2 meals/day')
    ax1.axhspan(1.8, 2.2, alpha=0.1, color='green')

    ax1.set_ylabel('Detected Events per Day', fontsize=12, color='#2c3e50')
    ax1.set_xticks(range(len(stages)))
    ax1.set_xticklabels(stages, fontsize=10)
    ax1.set_ylim(0, 7)
    ax1.set_title('The Journey to 2 Meals/Day: Progressive Refinement\n'
                  '(Live-Split Patient, 100% UAM, 0.12 boluses/day)',
                  fontsize=13, fontweight='bold')
    ax1.legend(loc='upper right', fontsize=10)

    # Add recall on secondary axis
    ax2 = ax1.twinx()
    recall_clean = [r if r is not None else 0 for r in recall]
    recall_x = [i for i, r in enumerate(recall) if r is not None]
    recall_y = [r for r in recall if r is not None]
    ax2.plot(recall_x, recall_y, 's-', color='#8e44ad', markersize=8,
             linewidth=2, label='Detection Rate (%)')
    ax2.set_ylabel('Detection Rate (%)', fontsize=12, color='#8e44ad')
    ax2.set_ylim(60, 105)
    ax2.legend(loc='upper center', fontsize=10)

    # Annotate events/day on bars
    for i, (v, bar) in enumerate(zip(events, bars)):
        ax1.text(i, v + 0.15, f'{v:.1f}', ha='center', fontsize=11,
                 fontweight='bold', color=colors[i])

    # Arrow showing improvement direction
    ax1.annotate('', xy=(5, 2.0), xytext=(0, 5.6),
                 arrowprops=dict(arrowstyle='->', color='grey', lw=2,
                                 connectionstyle='arc3,rad=0.3'))
    ax1.text(2.5, 4.8, 'Progressive\nrefinement', fontsize=10,
             ha='center', color='grey', style='italic')

    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig03_adjustment_journey.png'), dpi=DPI)
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 4: Detection Method Comparison — 4 methods on live-split
# ═══════════════════════════════════════════════════════════════════════

def fig04_method_comparison():
    methods = ['sum_flux', 'demand_only', 'residual', 'glucose_deriv']
    events_day = [2.2, 2.1, 6.2, 5.6]
    median_events = [2.0, 2.0, 7.0, 6.0]
    days_ge2 = [75, 70, 84, 84]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Panel 1: Mean events/day
    colors = [C_SUPPLY, C_DEMAND, C_RESIDUAL, C_GLUCOSE]
    ax = axes[0]
    bars = ax.bar(methods, events_day, color=colors, alpha=0.8, edgecolor='white')
    ax.axhline(2.0, color='black', linestyle='--', label='Expected (2/day)')
    ax.axhspan(1.5, 2.5, alpha=0.1, color='green')
    ax.set_ylabel('Events per Day (mean)', fontsize=11)
    ax.set_title('Mean Detection Rate', fontsize=12, fontweight='bold')
    ax.legend(fontsize=9)
    ax.set_ylim(0, 8)
    for i, v in enumerate(events_day):
        ax.text(i, v + 0.15, f'{v:.1f}', ha='center', fontsize=10,
                fontweight='bold')

    # Panel 2: Median events/day
    ax = axes[1]
    ax.bar(methods, median_events, color=colors, alpha=0.8, edgecolor='white')
    ax.axhline(2.0, color='black', linestyle='--')
    ax.axhspan(1.5, 2.5, alpha=0.1, color='green')
    ax.set_ylabel('Events per Day (median)', fontsize=11)
    ax.set_title('Median Detection Rate', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 8)
    for i, v in enumerate(median_events):
        ax.text(i, v + 0.15, f'{v:.0f}', ha='center', fontsize=10,
                fontweight='bold')

    # Panel 3: % days with ≥2 events
    ax = axes[2]
    ax.bar(methods, days_ge2, color=colors, alpha=0.8, edgecolor='white')
    ax.set_ylabel('Days with ≥2 Events (%)', fontsize=11)
    ax.set_title('Coverage Rate', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 100)
    for i, v in enumerate(days_ge2):
        ax.text(i, v + 1.5, f'{v}%', ha='center', fontsize=10,
                fontweight='bold')

    for ax in axes:
        ax.set_xticklabels(methods, rotation=15, fontsize=9)

    fig.suptitle('Live-Split Patient (100% UAM): Method Comparison (EXP-481)',
                 fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig04_method_comparison.png'), dpi=DPI,
                bbox_inches='tight')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 5: AC/DC Decomposition — basal vs meal insulin
# ═══════════════════════════════════════════════════════════════════════

def fig05_ac_dc_decomposition():
    hours = np.linspace(0, 24, STEPS_PER_DAY)
    # DC component: fasting-period demand baseline (hepatic equilibrium)
    # The 9.1× ratio from EXP-474 is meal-demand / fasting-demand
    dc = make_hepatic(hours)

    # AC component: meal boluses (the signal we detect)
    meal_times = [8, 12.5, 18.5]
    meal_doses = [6, 5, 7]
    boluses = list(zip(meal_times, meal_doses))
    ac = make_insulin_activity(hours, boluses, isf=40, basal_rate=0.0)

    total_demand = dc + ac

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # Panel 1: Full demand with AC/DC decomposition
    ax = axes[0]
    ax.fill_between(hours, dc, alpha=0.3, color=C_DC, label='DC (basal)')
    ax.fill_between(hours, dc, total_demand, alpha=0.3, color=C_AC,
                    label='AC (meal + correction)')
    ax.plot(hours, total_demand, color='black', linewidth=1.5,
            label='Total Demand')
    ax.set_ylabel('Demand\n(mg/dL per 5min)', fontsize=11)
    ax.set_title('AC/DC Insulin Decomposition: The Meal Signal\n'
                 '(EXP-474: 9.1× meal/fasting AC ratio)',
                 fontsize=13, fontweight='bold')
    ax.legend(loc='upper left', fontsize=10)
    for mh in meal_times:
        ax.axvline(mh, color=C_CARB, alpha=0.3, linestyle='--')

    # Panel 2: AC/DC ratio
    ax = axes[1]
    ac_ratio = ac / (np.maximum(dc, 0.01))
    ax.fill_between(hours, ac_ratio, alpha=0.3, color=C_AC)
    ax.plot(hours, ac_ratio, color=C_AC, linewidth=2)
    ax.axhline(1.0, color='grey', linestyle='--', alpha=0.5)
    ax.set_ylabel('AC/DC Ratio', fontsize=11)
    ax.set_xlabel('Hour of Day', fontsize=11)
    # Annotate peaks
    peaks, _ = find_peaks(ac_ratio, height=1.0, distance=20)
    for p in peaks:
        ax.annotate(f'{ac_ratio[p]:.1f}×', (hours[p], ac_ratio[p] + 0.3),
                    ha='center', fontsize=10, fontweight='bold', color=C_AC)

    # Shade meal vs fasting regions
    for mh in meal_times:
        ax.axvspan(mh - 0.5, mh + 2, alpha=0.08, color=C_CARB)

    for ax in axes:
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig05_ac_dc_decomposition.png'), dpi=DPI)
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 6: Phase Lag — supply peaks before demand
# ═══════════════════════════════════════════════════════════════════════

def fig06_phase_lag():
    t = np.linspace(-30, 240, 300)  # minutes relative to meal

    # Common carb absorption curve (supply component)
    carb_s = carb_curve(t, carbs=50)
    hep_const = compute_hepatic_production(np.full(len(t), 0.5),
                                           np.full(len(t), 12.0))

    # Announced meal: bolus given 15 min before eating
    t_bol_ann = t + 15  # bolus was 15 min before meal
    bolus_act_ann = insulin_curve(t_bol_ann, dose=5) * 40  # × ISF
    supply_ann = carb_s * 4 + hep_const
    demand_ann = bolus_act_ann + hep_const * 0.8

    # UAM meal: no bolus, AID reacts ~30 min after carb absorption starts
    supply_uam = carb_s * 4 + hep_const
    t_react = t - 30  # AID starts reacting 30 min after meal
    demand_uam = insulin_curve(t_react, dose=4) * 40
    demand_uam += hep_const * 0.8

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, supply, demand, title, note in [
        (axes[0], supply_ann, demand_ann,
         'Announced Meal\n(bolus precedes carbs)', None),
        (axes[1], supply_uam, demand_uam,
         'Unannounced Meal (UAM)\n(AID reacts after glucose rises)',
         '35-min gap\n= UAM classifier\nfeature (EXP-471)'),
    ]:
        ax.plot(t, supply, color=C_SUPPLY, linewidth=2, label='Supply')
        ax.plot(t, demand, color=C_DEMAND, linewidth=2, label='Demand')
        s_peak = t[np.argmax(supply)]
        d_peak = t[np.argmax(demand)]
        ax.axvline(s_peak, color=C_SUPPLY, linestyle=':', alpha=0.5)
        ax.axvline(d_peak, color=C_DEMAND, linestyle=':', alpha=0.5)
        lag = d_peak - s_peak
        y_arrow = max(np.max(demand), np.max(supply)) * 0.55
        ax.annotate('', xy=(d_peak, y_arrow), xytext=(s_peak, y_arrow),
                    arrowprops=dict(arrowstyle='<->', color='black', lw=2))
        ax.text((s_peak + d_peak) / 2, y_arrow * 1.08,
                f'{lag:.0f} min', ha='center', fontsize=12, fontweight='bold')
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_ylabel('Flux (mg/dL per 5min)', fontsize=11)
        ax.set_xlabel('Minutes from Meal', fontsize=11)
        ax.legend(fontsize=10)
        if note:
            ax.text(140, np.max(demand) * 0.45, note,
                    fontsize=10, color='#8e44ad', ha='center',
                    bbox=dict(boxstyle='round', facecolor='#f3e5f5',
                              alpha=0.8))

    fig.suptitle('Phase Lag: Supply Peaks Before Demand (EXP-466)',
                 fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig06_phase_lag.png'), dpi=DPI,
                bbox_inches='tight')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 7: Precondition Gating — READY vs all days
# ═══════════════════════════════════════════════════════════════════════

def fig07_precondition_gating():
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Panel 1: Day status breakdown
    ax = axes[0]
    statuses = ['READY\n(50)', 'CGM Gap\n(7)', 'INS Gap\n(1)', 'Both Gap\n(3)']
    counts = [50, 7, 1, 3]
    colors = ['#27ae60', '#e74c3c', '#f39c12', '#95a5a6']
    wedges, texts, autotexts = ax.pie(counts, labels=statuses, colors=colors,
                                      autopct='%1.0f%%', startangle=90,
                                      textprops={'fontsize': 10})
    for at in autotexts:
        at.set_fontweight('bold')
    ax.set_title('Day Readiness (61 Calendar Days)\n'
                 'Preconditions: CGM ≥70% + Insulin ≥10%',
                 fontsize=11, fontweight='bold')

    # Panel 2: Before/After gating
    ax = axes[1]
    metrics = ['Events/day\n(mean)', 'Detection\nRate', 'Days\n2-3 meals']
    all_days = [2.2, 82, 59]
    ready_days = [2.6, 96, 72]
    x = np.arange(len(metrics))
    w = 0.35
    ax.bar(x - w/2, all_days, w, label='All 61 days', color='#bdc3c7',
           alpha=0.9, edgecolor='white')
    ax.bar(x + w/2, ready_days, w, label='50 READY days', color='#27ae60',
           alpha=0.9, edgecolor='white')

    for i in range(len(metrics)):
        ax.text(x[i] - w/2, all_days[i] + 1.5, f'{all_days[i]}',
                ha='center', fontsize=11, fontweight='bold', color='#7f8c8d')
        ax.text(x[i] + w/2, ready_days[i] + 1.5, f'{ready_days[i]}',
                ha='center', fontsize=11, fontweight='bold', color='#27ae60')

    # Improvement annotations
    for i in range(len(metrics)):
        diff = ready_days[i] - all_days[i]
        pct = '+' if diff > 0 else ''
        ax.annotate(f'{pct}{diff}', xy=(x[i], max(all_days[i], ready_days[i]) + 5),
                    fontsize=10, ha='center', color='#8e44ad', fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylabel('Value', fontsize=11)
    ax.set_title('Impact of Precondition Gating (EXP-483)',
                 fontsize=11, fontweight='bold')
    ax.legend(fontsize=10)
    ax.set_ylim(0, 110)

    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig07_precondition_gating.png'), dpi=DPI)
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 8: Live-Split Day — simulated detection on UAM patient
# ═══════════════════════════════════════════════════════════════════════

def fig08_live_split_day():
    """Simulate a realistic UAM patient day with AID-only insulin."""
    hours = np.linspace(0, 24, STEPS_PER_DAY)

    # Patient profile: ISF=40, CR=10, DIA=5h, basal~1.8 U/hr
    isf = 40
    basal_rate = 1.8  # U/hr

    # Two meals: lunch ~12h, dinner ~18h (no breakfast, no boluses)
    meal_carbs = [(12, 55), (18.5, 65)]

    # Hepatic production
    hep = make_hepatic(hours)

    # Carb absorption (unannounced)
    carb_sup = make_carb_supply(hours, meal_carbs, isf=isf, cr=10)
    supply = hep + carb_sup

    # AID-driven demand: baseline matches hepatic (steady state)
    # plus reactive SMBs after glucose rises from meals
    smb_boluses = []
    for mh, _mg in meal_carbs:
        for smb_offset in range(0, 120, 15):
            smb_hr = mh + (25 + smb_offset) / 60.0
            smb_boluses.append((smb_hr, 0.3))
    demand = make_insulin_activity(hours, smb_boluses, isf=isf, basal_rate=basal_rate)
    demand += hep  # baseline matches hepatic

    # Product (throughput)
    product = supply * demand

    # Glucose with AID feedback (keeps glucose in range)
    target = 155  # this patient runs a bit high (TIR 65%)
    glucose = np.zeros(STEPS_PER_DAY)
    glucose[0] = target + np.random.normal(0, 3)
    for i in range(1, STEPS_PER_DAY):
        net = supply[i] - demand[i]
        feedback = 0.10 * (glucose[i-1] - target)
        glucose[i] = glucose[i-1] + (net - feedback) * 0.15 + np.random.normal(0, 0.8)
    glucose = np.clip(glucose, 60, 350)

    # Detect peaks in demand
    from scipy.ndimage import uniform_filter1d
    dem_smooth = uniform_filter1d(demand, size=6)
    peaks, props = find_peaks(dem_smooth,
                              height=np.percentile(dem_smooth[dem_smooth>0], 50),
                              prominence=np.percentile(dem_smooth[dem_smooth>0], 30)*0.3,
                              distance=18)
    # Filter overnight
    peaks = peaks[(hours[peaks] >= 5) | (dem_smooth[peaks] > 2 * np.median(dem_smooth))]

    fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)

    # Panel 1: Glucose
    ax = axes[0]
    ax.plot(hours, glucose, color=C_GLUCOSE, linewidth=1.5)
    ax.axhspan(70, 180, alpha=0.08, color='green')
    ax.set_ylabel('BG (mg/dL)', fontsize=11)
    ax.set_title('Simulated UAM Patient Day: 0 Boluses, 2 Meals\n'
                 '(Calibrated to live-split: ISF=40, basal=1.8 U/hr, TIR ~65%)',
                 fontsize=13, fontweight='bold')
    ax.set_ylim(60, 300)
    for mh, mg in meal_carbs:
        ax.axvline(mh, color=C_CARB, alpha=0.3, linestyle='--')
        ax.annotate(f'{mg}g (UAM)', (mh, 280), fontsize=9, color=C_CARB,
                    ha='center')

    # Panel 2: Supply (hepatic only visible, carbs invisible to model)
    ax = axes[1]
    ax.fill_between(hours, hep, alpha=0.3, color=C_HEPATIC,
                    label='Hepatic (known)')
    ax.fill_between(hours, hep, supply, alpha=0.2, color=C_CARB,
                    label='UAM carbs (invisible)')
    ax.plot(hours, supply, color=C_SUPPLY, linewidth=1.5)
    ax.set_ylabel('Supply\n(mg/dL/5min)', fontsize=11)
    ax.legend(fontsize=9)

    # Panel 3: Demand (AID-driven SMBs)
    ax = axes[2]
    ax.fill_between(hours, demand, alpha=0.3, color=C_DEMAND)
    ax.plot(hours, dem_smooth, color=C_DEMAND, linewidth=2,
            label='Demand (smoothed)')
    ax.plot(hours[peaks], dem_smooth[peaks], 'v', color='black', markersize=12,
            label=f'{len(peaks)} meals detected', zorder=5)
    ax.set_ylabel('Demand\n(mg/dL/5min)', fontsize=11)
    ax.legend(fontsize=9)
    # Annotate peaks
    for p in peaks:
        ax.annotate(f'{hours[p]:.0f}h', (hours[p], dem_smooth[p] + 0.2),
                    fontsize=9, ha='center', fontweight='bold')

    # Panel 4: Throughput (product)
    ax = axes[3]
    ax.fill_between(hours, product, alpha=0.3, color=C_PRODUCT)
    ax.plot(hours, product, color=C_PRODUCT, linewidth=2)
    prod_peaks, _ = find_peaks(product, prominence=np.max(product)*0.15,
                               distance=18)
    ax.plot(hours[prod_peaks], product[prod_peaks], 'v', color='black',
            markersize=10)
    ax.set_ylabel('Throughput\n(S × D)', fontsize=11)
    ax.set_xlabel('Hour of Day', fontsize=11)

    for ax in axes:
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig08_live_split_day.png'), dpi=DPI)
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 9: Residual Decomposition — what the model misses
# ═══════════════════════════════════════════════════════════════════════

def fig09_residual_decomposition():
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Panel 1: Variance decomposition pie
    ax = axes[0]
    components = ['Meal\n(25%)', 'Dawn\n(13%)', 'Exercise\n(6%)', 'Noise\n(53%)']
    sizes = [25, 13, 6, 53]  # 3% not shown - rounding
    colors_pie = [C_CARB, C_HEPATIC, '#2ecc71', '#95a5a6']
    explode = (0.08, 0.03, 0, 0)
    wedges, texts, autotexts = ax.pie(sizes, labels=components, colors=colors_pie,
                                      autopct='%1.0f%%', startangle=90,
                                      explode=explode,
                                      textprops={'fontsize': 10})
    for at in autotexts:
        at.set_fontweight('bold')
    ax.set_title('Conservation Residual Decomposition\n'
                 '(EXP-488: Live-Split Patient)',
                 fontsize=11, fontweight='bold')

    # Panel 2: Mean residual by component
    ax = axes[1]
    comp_names = ['Meal', 'Dawn', 'Exercise', 'Noise']
    mean_resid = [3.77, 2.49, 0.82, 1.70]
    pos_pct = [74, 56, 46, 50]
    colors_bar = [C_CARB, C_HEPATIC, '#2ecc71', '#95a5a6']

    bars = ax.bar(comp_names, mean_resid, color=colors_bar, alpha=0.85,
                  edgecolor='white', linewidth=2)
    ax.set_ylabel('Mean Residual (mg/dL)', fontsize=11)
    ax.set_title('Residual Direction by Component', fontsize=11,
                 fontweight='bold')

    # Annotate with positive %
    for i, (v, p) in enumerate(zip(mean_resid, pos_pct)):
        ax.text(i, v + 0.12, f'+{v:.1f}\n({p}% ↑)', ha='center',
                fontsize=10, fontweight='bold')

    ax.axhline(0, color='black', linewidth=0.5)
    ax.text(0, 4.3, '74% positive = unmodeled\ncarb absorption',
            fontsize=9, color='#8e44ad', ha='center',
            bbox=dict(boxstyle='round', facecolor='#f3e5f5', alpha=0.8))

    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig09_residual_decomposition.png'), dpi=DPI)
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 10: Dessert Detection — double-peak pattern
# ═══════════════════════════════════════════════════════════════════════

def fig10_dessert_detection():
    t = np.linspace(0, 360, 360)  # 6 hours in minutes

    # Dinner at t=0, dessert at t=123 min (using real PK model)
    dinner_demand = insulin_curve(t, dose=6) * 40 + 1.2
    dessert_demand = insulin_curve(t - 123, dose=2.5) * 40
    total = dinner_demand + dessert_demand

    dinner_carb = carb_curve(t, carbs=65) * 4
    dessert_carb = carb_curve(t - 123, carbs=30) * 4
    total_supply = dinner_carb + dessert_carb + 1.0

    product = total_supply * total

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

    ax = axes[0]
    ax.plot(t, total_supply, color=C_SUPPLY, linewidth=2, label='Supply')
    ax.plot(t, total, color=C_DEMAND, linewidth=2, label='Demand')
    ax.axvline(0, color=C_CARB, linestyle='--', alpha=0.5, label='Dinner')
    ax.axvline(123, color='#8e44ad', linestyle='--', alpha=0.5,
               label='Dessert (+123 min)')
    ax.set_ylabel('Flux (mg/dL/5min)', fontsize=11)
    ax.set_title('Dessert Detection: Double-Peak Pattern (EXP-486)\n'
                 '18% of dinners, 123 min mean gap',
                 fontsize=13, fontweight='bold')
    ax.legend(fontsize=10, loc='upper right')
    ax.annotate('Dinner\npeak', (25, np.max(dinner_carb)*0.8), fontsize=9,
                ha='center')
    ax.annotate('Dessert\npeak', (148, np.max(dessert_demand)*0.6 + 2),
                fontsize=9, ha='center', color='#8e44ad')

    ax = axes[1]
    ax.fill_between(t, product, alpha=0.3, color=C_PRODUCT)
    ax.plot(t, product, color=C_PRODUCT, linewidth=2, label='Throughput')
    peaks, _ = find_peaks(product, prominence=np.max(product)*0.1, distance=30)
    ax.plot(t[peaks], product[peaks], 'v', color='black', markersize=12)
    ax.set_ylabel('Throughput (S × D)', fontsize=11)
    ax.set_xlabel('Minutes After Dinner', fontsize=11)
    ax.legend(fontsize=10)

    if len(peaks) >= 2:
        gap = t[peaks[1]] - t[peaks[0]]
        ax.annotate('', xy=(t[peaks[1]], product[peaks[1]]*0.6),
                    xytext=(t[peaks[0]], product[peaks[0]]*0.6),
                    arrowprops=dict(arrowstyle='<->', color='black', lw=2))
        ax.text((t[peaks[0]]+t[peaks[1]])/2, product[peaks[0]]*0.65,
                f'{gap:.0f} min gap', ha='center', fontsize=11,
                fontweight='bold')

    for ax in axes:
        ax.set_xlim(-20, 360)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig10_dessert_detection.png'), dpi=DPI)
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 11: Graceful Degradation — the bolusing spectrum
# ═══════════════════════════════════════════════════════════════════════

def fig11_graceful_degradation():
    fig, ax = plt.subplots(figsize=(14, 6))

    # Bolusing spectrum
    categories = ['Traditional\nBoluser', 'SMB-Dominant\n(7/11 patients)',
                  'Near-100% UAM\n(live-split)']
    uam_frac = [25, 86, 100]

    # Stacked bar: supply channel composition
    explicit_supply = [80, 30, 0]
    residual_supply = [10, 50, 75]
    hepatic_only = [10, 20, 25]

    x = np.arange(len(categories))
    w = 0.5

    ax.bar(x, explicit_supply, w, label='Explicit Carb Supply',
           color=C_CARB, alpha=0.85)
    ax.bar(x, residual_supply, w, bottom=explicit_supply,
           label='Residual (implicit carbs)', color=C_RESIDUAL, alpha=0.85)
    ax.bar(x, hepatic_only, w,
           bottom=[e+r for e, r in zip(explicit_supply, residual_supply)],
           label='Hepatic Only', color=C_HEPATIC, alpha=0.85)

    ax.set_ylabel('Supply Channel Composition (%)', fontsize=12)
    ax.set_title('Graceful Degradation: Framework Adapts to Missing Data\n'
                 'Supply channel shifts from explicit → implicit as carb data disappears',
                 fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=11)
    ax.legend(fontsize=10, loc='upper right')
    ax.set_ylim(0, 115)

    # Add UAM fraction labels
    for i, u in enumerate(uam_frac):
        ax.text(i, 105, f'UAM: {u}%', ha='center', fontsize=11,
                fontweight='bold', color='#8e44ad')

    # Best detection method annotations
    best = ['sum_flux\n(76% recall)', 'residual\n(65% recall)',
            'demand_only\n(2.0/day)']
    for i, b in enumerate(best):
        ax.text(i, -8, b, ha='center', fontsize=9, color='#2c3e50',
                fontweight='bold')

    ax.text(-0.5, -15, 'Best Method →', fontsize=9, color='grey',
            style='italic')

    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig11_graceful_degradation.png'), dpi=DPI,
                bbox_inches='tight')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Figure 12: Daily Distribution Histogram — how many meals per day?
# ═══════════════════════════════════════════════════════════════════════

def fig12_daily_distribution():
    """Histogram of daily meal counts for sum_flux detector."""
    # Simulated distribution calibrated to EXP-481 results
    # sum_flux: mean 2.2, std 1.3, median 2.0, 75% days ≥2
    np.random.seed(123)
    # Generate realistic counts: mix of Poisson(2) with some 0s from gaps
    n_ready = 50
    n_gap = 11
    ready_counts = np.random.poisson(2.0, n_ready)
    ready_counts = np.clip(ready_counts, 0, 6)
    gap_counts = np.zeros(n_gap, dtype=int)
    gap_counts[:2] = [0, 0]
    gap_counts[2:5] = [1, 1, 0]
    gap_counts[5:] = np.random.poisson(1.0, 6)
    gap_counts = np.clip(gap_counts, 0, 3)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Panel 1: All days
    ax = axes[0]
    all_counts = np.concatenate([ready_counts, gap_counts])
    bins = np.arange(-0.5, 8.5, 1)
    ax.hist(all_counts, bins=bins, color='#bdc3c7', edgecolor='white',
            alpha=0.9, rwidth=0.85)
    ax.axvline(np.mean(all_counts), color=C_DEMAND, linewidth=2,
               linestyle='--', label=f'Mean: {np.mean(all_counts):.1f}')
    ax.axvline(np.median(all_counts), color=C_PRODUCT, linewidth=2,
               linestyle='-', label=f'Median: {np.median(all_counts):.0f}')
    ax.set_xlabel('Meals Detected per Day', fontsize=11)
    ax.set_ylabel('Number of Days', fontsize=11)
    ax.set_title('All 61 Days', fontsize=12, fontweight='bold')
    ax.legend(fontsize=10)
    ax.set_xlim(-0.5, 7.5)

    # Panel 2: READY days only
    ax = axes[1]
    ax.hist(ready_counts, bins=bins, color='#27ae60', edgecolor='white',
            alpha=0.9, rwidth=0.85)
    ax.axvline(np.mean(ready_counts), color=C_DEMAND, linewidth=2,
               linestyle='--', label=f'Mean: {np.mean(ready_counts):.1f}')
    ax.axvline(np.median(ready_counts), color=C_PRODUCT, linewidth=2,
               linestyle='-', label=f'Median: {np.median(ready_counts):.0f}')
    ax.set_xlabel('Meals Detected per Day', fontsize=11)
    ax.set_title('50 READY Days (≥70% CGM + ≥10% insulin)',
                 fontsize=12, fontweight='bold')
    ax.legend(fontsize=10)
    ax.set_xlim(-0.5, 7.5)

    # Shade target zone
    for ax in axes:
        ax.axvspan(1.5, 3.5, alpha=0.08, color='green')
        ax.text(2.5, ax.get_ylim()[1]*0.85, 'Target\n(2-3)', fontsize=9,
                ha='center', color='#27ae60', fontweight='bold')

    fig.suptitle('Daily Meal Count Distribution — sum_flux Detector (EXP-481/483)',
                 fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUT, 'fig12_daily_distribution.png'), dpi=DPI,
                bbox_inches='tight')
    plt.close()


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('Generating meal detection figures...')

    generators = [
        ('fig01', fig01_throughput_concept),
        ('fig02', fig02_spectral_power),
        ('fig03', fig03_adjustment_journey),
        ('fig04', fig04_method_comparison),
        ('fig05', fig05_ac_dc_decomposition),
        ('fig06', fig06_phase_lag),
        ('fig07', fig07_precondition_gating),
        ('fig08', fig08_live_split_day),
        ('fig09', fig09_residual_decomposition),
        ('fig10', fig10_dessert_detection),
        ('fig11', fig11_graceful_degradation),
        ('fig12', fig12_daily_distribution),
    ]

    for name, func in generators:
        print(f'  {name}...', end=' ', flush=True)
        func()
        print('✓')

    print(f'\nDone — 12 figures saved to {OUT}/')
