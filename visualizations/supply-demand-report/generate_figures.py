#!/usr/bin/env python3
"""
Supply-Demand Evolution Report — Matplotlib Figures
====================================================

Generates all figures for the supply-demand evolution report, using
synthetic data calibrated to documented experimental results from
EXP-435 through EXP-493 (11 patients, ~180 days each).

All physiological parameters match documented values from:
  - metabolic-flux-report-2026-04-06.md
  - metabolic-flux-synthesis-2026-04-07.md
  - continuous-physiological-state-modeling-2026-04-05.md
  - symmetry-sparsity-feature-selection-2026-04-05.md
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyArrowPatch, Circle
from matplotlib.lines import Line2D
import os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
DPI = 150
np.random.seed(42)

# ── Color palette ────────────────────────────────────────────────────
C = {
    'glucose':  '#2196F3',   # blue
    'supply':   '#4CAF50',   # green
    'demand':   '#F44336',   # red
    'hepatic':  '#8BC34A',   # light green
    'carb':     '#FF9800',   # orange
    'residual': '#9C27B0',   # purple
    'net':      '#607D8B',   # blue-grey
    'bg':       '#FAFAFA',   # background
    'text':     '#212121',
    'grid':     '#E0E0E0',
    'accent1':  '#00BCD4',   # cyan
    'accent2':  '#FF5722',   # deep orange
}

def style_ax(ax, title='', xlabel='', ylabel=''):
    ax.set_facecolor(C['bg'])
    ax.grid(True, alpha=0.3, color=C['grid'])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    if title:
        ax.set_title(title, fontsize=13, fontweight='bold', color=C['text'], pad=10)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10, color=C['text'])
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10, color=C['text'])

def save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  ✓ {name}")

# ── Physiological models ─────────────────────────────────────────────

def insulin_activity_curve(t_min, dose=1.0, dia=300, peak=55):
    """oref0 exponential insulin activity curve."""
    tau = peak * (1 - peak/dia) / (1 - 2*peak/dia)
    t = np.clip(t_min, 0, dia)
    norm = tau**2 / (dia * (1 - 2*peak/dia))
    activity = dose * (norm / tau**2) * t * (1 - t/dia) * np.exp(-t/tau)
    activity[t_min < 0] = 0
    activity[t_min > dia] = 0
    return np.maximum(activity, 0)

def carb_absorption_curve(t_min, carbs=50.0, abs_time=180):
    """Piecewise-linear carb absorption (Loop-style)."""
    t = np.clip(t_min, 0, abs_time)
    peak_time = 0.15 * abs_time
    rate = np.zeros_like(t_min, dtype=float)
    rising = (t_min >= 0) & (t_min < peak_time)
    plateau = (t_min >= peak_time) & (t_min < 0.5 * abs_time)
    falling = (t_min >= 0.5 * abs_time) & (t_min < abs_time)
    peak_rate = 2 * carbs / abs_time
    rate[rising] = peak_rate * (t_min[rising] / peak_time)
    rate[plateau] = peak_rate
    rate[falling] = peak_rate * (1 - (t_min[falling] - 0.5*abs_time) / (0.5*abs_time))
    return np.maximum(rate, 0)

def hepatic_production(iob, hour, base_rate=1.5, max_supp=0.65,
                        hill_n=1.5, half_max=2.0, circ_amp=0.20):
    """Hill equation + circadian modulation for EGP."""
    ratio = iob / max(half_max, 0.01)
    suppression = (ratio**hill_n / (1 + ratio**hill_n)) * max_supp
    production = base_rate * max(1.0 - suppression, 1.0 - max_supp)
    circadian = 1.0 + circ_amp * np.sin(2 * np.pi * hour / 24)
    return production * circadian

# ══════════════════════════════════════════════════════════════════════
# FIGURE 1: The AC Circuit Analogy
# ══════════════════════════════════════════════════════════════════════
def fig01_ac_circuit_analogy():
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    fig.suptitle('The Invisible Metabolic World: AC Circuit Analogy',
                 fontsize=15, fontweight='bold', y=0.98)

    t = np.linspace(0, 24, 288)  # 24h at 5-min

    # Simulate AID-controlled glucose (nearly flat with small oscillations)
    glucose = 120 + 8*np.sin(2*np.pi*t/24) + 3*np.random.randn(288)
    # Add small meal bumps that AID mostly compensates
    for meal_h in [7.5, 12.5, 18.5]:
        idx = np.argmin(np.abs(t - meal_h))
        bump = 25 * np.exp(-0.5*((t - meal_h)/0.8)**2)
        glucose += bump

    # Supply signal (hepatic + carb absorption)
    supply = np.ones_like(t) * 1.2  # hepatic baseline
    supply += 0.2 * np.sin(2*np.pi*t/24)  # circadian
    for meal_h, carbs in [(7.5, 50), (12.5, 60), (18.5, 70)]:
        supply += carbs/50 * 3.0 * np.exp(-0.5*((t - meal_h)/0.6)**2)

    # Demand signal (insulin action)
    demand = np.ones_like(t) * 0.8  # basal
    for meal_h, dose in [(7.5, 4), (12.5, 5), (18.5, 6)]:
        demand += dose/4 * 2.5 * np.exp(-0.5*((t - (meal_h+0.3))/0.7)**2)

    # Panel 1: Glucose (nearly flat — the "voltage")
    ax = axes[0]
    style_ax(ax, 'Glucose (Observable) — "Voltage"', ylabel='mg/dL')
    ax.fill_between(t, 70, 180, alpha=0.08, color=C['glucose'], label='Target range')
    ax.plot(t, glucose, color=C['glucose'], linewidth=2, label='CGM glucose')
    ax.axhline(120, color=C['grid'], linestyle='--', alpha=0.5)
    ax.set_ylim(60, 220)
    ax.legend(loc='upper right', fontsize=9)
    ax.text(0.02, 0.85, 'TIR = 92%\nLooks great!',
            transform=ax.transAxes, fontsize=10, color=C['text'],
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#E8F5E9', alpha=0.8))

    # Panel 2: Supply & Demand (the "current")
    ax = axes[1]
    style_ax(ax, 'Metabolic Flux (Hidden) — "Current"', ylabel='mg/dL per 5min')
    ax.fill_between(t, supply, alpha=0.3, color=C['supply'])
    ax.plot(t, supply, color=C['supply'], linewidth=2, label='Supply (hepatic + carbs)')
    ax.fill_between(t, demand, alpha=0.3, color=C['demand'])
    ax.plot(t, demand, color=C['demand'], linewidth=2, label='Demand (insulin action)')
    ax.legend(loc='upper right', fontsize=9)
    ax.text(0.02, 0.85, '3–8× activity\nduring meals',
            transform=ax.transAxes, fontsize=10, color=C['text'],
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#FFF3E0', alpha=0.8))

    # Panel 3: Throughput (supply × demand) — the "power"
    throughput = supply * demand
    ax = axes[2]
    style_ax(ax, 'Throughput (supply × demand) — "Power"',
             xlabel='Hour of Day', ylabel='(mg/dL)² per 5min')
    ax.fill_between(t, throughput, alpha=0.3, color=C['accent1'])
    ax.plot(t, throughput, color=C['accent1'], linewidth=2, label='Metabolic throughput')
    ax.legend(loc='upper right', fontsize=9)

    # Annotate meals
    for meal_h, label in [(7.5, 'Breakfast'), (12.5, 'Lunch'), (18.5, 'Dinner')]:
        for ax in axes:
            ax.axvline(meal_h, color=C['carb'], alpha=0.3, linestyle=':')
        axes[2].annotate(label, xy=(meal_h, throughput[np.argmin(np.abs(t-meal_h))]),
                         xytext=(meal_h+0.5, throughput.max()*0.9),
                         fontsize=8, color=C['carb'],
                         arrowprops=dict(arrowstyle='->', color=C['carb'], alpha=0.5))

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    save(fig, 'fig01_ac_circuit_analogy.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 2: Supply-Demand Decomposition Detail
# ══════════════════════════════════════════════════════════════════════
def fig02_supply_demand_decomposition():
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    fig.suptitle('Supply-Demand Decomposition: Anatomy of a Meal',
                 fontsize=15, fontweight='bold', y=0.98)

    t = np.linspace(-60, 300, 360)  # -1h to +5h around meal at t=0

    # Simulate a 60g meal at t=0 with 5U bolus at t=-5
    carb_rate = carb_absorption_curve(t, carbs=60, abs_time=180)
    insulin_act = insulin_activity_curve(t + 5, dose=5.0)

    # Hepatic production (suppressed by insulin)
    iob_profile = 5.0 * np.exp(-t/180) * (t > -5).astype(float)
    hepatic = np.array([hepatic_production(iob_profile[i], 12.0) for i in range(len(t))])

    supply = hepatic + carb_rate * 0.8  # scale to mg/dL per 5min
    demand = insulin_act * 40 + 0.6     # ISF=40, basal floor
    net = supply - demand
    residual = 0.3 * np.random.randn(len(t))

    # Integrate to get glucose
    glucose = np.zeros_like(t)
    glucose[0] = 110
    for i in range(1, len(t)):
        glucose[i] = glucose[i-1] + net[i]*0.3 + residual[i]

    # Panel 1: Supply breakdown
    ax = axes[0]
    style_ax(ax, 'SUPPLY: Glucose Sources', ylabel='mg/dL per 5min')
    ax.fill_between(t, hepatic, alpha=0.3, color=C['hepatic'])
    ax.plot(t, hepatic, color=C['hepatic'], linewidth=1.5, label='Hepatic (EGP)')
    ax.fill_between(t, hepatic, supply, alpha=0.3, color=C['carb'])
    ax.plot(t, supply, color=C['supply'], linewidth=2, label='Total supply')
    ax.legend(loc='upper right', fontsize=9)
    ax.annotate('Carb absorption\n(60g meal)', xy=(60, supply[np.argmin(np.abs(t-60))]),
                xytext=(120, supply.max()*0.9), fontsize=9, color=C['carb'],
                arrowprops=dict(arrowstyle='->', color=C['carb']))
    ax.annotate('Hepatic always on\n(never zero)', xy=(250, hepatic[-20]),
                xytext=(200, hepatic.max()*1.5), fontsize=9, color=C['hepatic'],
                arrowprops=dict(arrowstyle='->', color=C['hepatic']))

    # Panel 2: Demand
    ax = axes[1]
    style_ax(ax, 'DEMAND: Insulin Action', ylabel='mg/dL per 5min')
    ax.fill_between(t, 0.6, demand, alpha=0.3, color=C['demand'])
    ax.axhline(0.6, color=C['demand'], linestyle='--', alpha=0.5, label='Basal floor')
    ax.plot(t, demand, color=C['demand'], linewidth=2, label='Total demand')
    ax.legend(loc='upper right', fontsize=9)
    ax.annotate('5U bolus peak\n(~55 min)', xy=(55, demand[np.argmin(np.abs(t-55))]),
                xytext=(120, demand.max()*0.9), fontsize=9, color=C['demand'],
                arrowprops=dict(arrowstyle='->', color=C['demand']))

    # Panel 3: Net flux
    ax = axes[2]
    style_ax(ax, 'NET FLUX: supply − demand', ylabel='mg/dL per 5min')
    ax.fill_between(t, 0, net, where=net>=0, alpha=0.3, color=C['supply'], label='Rising')
    ax.fill_between(t, 0, net, where=net<0, alpha=0.3, color=C['demand'], label='Falling')
    ax.plot(t, net, color=C['net'], linewidth=2)
    ax.axhline(0, color=C['text'], linewidth=0.5)
    ax.legend(loc='upper right', fontsize=9)

    # Panel 4: Resulting glucose
    ax = axes[3]
    style_ax(ax, 'GLUCOSE: Integrated Result', xlabel='Minutes from Meal',
             ylabel='mg/dL')
    ax.fill_between(t, 70, 180, alpha=0.05, color=C['glucose'])
    ax.plot(t, glucose, color=C['glucose'], linewidth=2.5, label='Blood glucose')
    ax.axhline(110, color=C['grid'], linestyle='--', alpha=0.5)
    ax.set_ylim(60, 220)
    ax.legend(loc='upper right', fontsize=9)

    for ax in axes:
        ax.axvline(0, color=C['carb'], alpha=0.4, linestyle=':', linewidth=1.5)

    axes[0].text(2, axes[0].get_ylim()[1]*0.95, '← Meal', fontsize=9, color=C['carb'])
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    save(fig, 'fig02_supply_demand_decomposition.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 3: Glucose Conservation Law
# ══════════════════════════════════════════════════════════════════════
def fig03_conservation_law():
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('Glucose Conservation: ∫(Supply − Demand) dt ≈ ΔBG ≈ 0',
                 fontsize=15, fontweight='bold', y=1.02)

    # Left: 12h window showing conservation
    ax = axes[0]
    style_ax(ax, '12-Hour Conservation Window',
             xlabel='Hour', ylabel='Cumulative integral (mg·h)')

    t = np.linspace(0, 12, 144)
    # Net flux that integrates to near-zero
    net = 2.0*np.sin(2*np.pi*t/4) + 1.5*np.sin(2*np.pi*t/6) + 0.5*np.random.randn(144)
    cumulative = np.cumsum(net) * (12/144)

    ax.fill_between(t, 0, cumulative, where=cumulative>=0, alpha=0.2, color=C['supply'])
    ax.fill_between(t, 0, cumulative, where=cumulative<0, alpha=0.2, color=C['demand'])
    ax.plot(t, cumulative, color=C['net'], linewidth=2)
    ax.axhline(0, color=C['text'], linewidth=1)
    ax.annotate(f'Final: {cumulative[-1]:.1f} mg·h\n(≈ 0, conserved)',
                xy=(12, cumulative[-1]), fontsize=11, fontweight='bold',
                color=C['supply'] if cumulative[-1] > 0 else C['demand'],
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    # Right: Histogram of conservation residuals across windows (documented)
    ax = axes[1]
    style_ax(ax, 'Conservation Residual Distribution\n(EXP-421: 7,337 windows)',
             xlabel='12h integral (mg·h)', ylabel='Count')

    # Documented: mean -1.8 ± 28.4 mg·h
    residuals = np.random.normal(-1.8, 28.4, 7337)
    ax.hist(residuals, bins=60, color=C['accent1'], alpha=0.7, edgecolor='white')
    ax.axvline(-1.8, color=C['demand'], linewidth=2, linestyle='--',
               label=f'Mean = −1.8 mg·h')
    ax.axvline(0, color=C['text'], linewidth=1)

    # Shade ±1σ
    ax.axvspan(-1.8 - 28.4, -1.8 + 28.4, alpha=0.1, color=C['accent1'],
               label=f'±1σ = ±28.4 mg·h')
    ax.legend(fontsize=10, loc='upper right')
    ax.text(0.02, 0.85, 'Glucose IS conserved\nover absorption cycles',
            transform=ax.transAxes, fontsize=11, fontweight='bold',
            color=C['supply'],
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#E8F5E9', alpha=0.8))

    plt.tight_layout()
    save(fig, 'fig03_conservation_law.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 4: The Four Symmetries
# ══════════════════════════════════════════════════════════════════════
def fig04_four_symmetries():
    fig = plt.figure(figsize=(14, 10))
    gs = gridspec.GridSpec(2, 2, hspace=0.35, wspace=0.3)

    # 1. Time-Translation Invariance
    ax = fig.add_subplot(gs[0, 0])
    style_ax(ax, '① Time-Translation Invariance',
             xlabel='Minutes from meal', ylabel='Glucose (mg/dL)')
    t = np.linspace(-30, 180, 200)
    response = 40*np.exp(-0.5*((t-45)/30)**2)
    ax.plot(t, 110+response, color=C['carb'], linewidth=2.5, label='8 AM meal')
    ax.plot(t, 110+response*0.95 + 2*np.random.randn(200)*0.3,
            color=C['accent1'], linewidth=2.5, alpha=0.7, label='8 PM meal')
    ax.legend(fontsize=9)
    ax.text(0.02, 0.02, 'EXP-298: Removing time features\nimproves +1.4% at 12h',
            transform=ax.transAxes, fontsize=8, style='italic',
            bbox=dict(boxstyle='round', facecolor='#E3F2FD', alpha=0.8))

    # 2. Absorption Envelope Symmetry
    ax = fig.add_subplot(gs[0, 1])
    style_ax(ax, '② Absorption Envelope Symmetry',
             xlabel='Minutes from bolus', ylabel='Insulin activity (U/min)')
    t = np.linspace(0, 300, 300)
    activity = insulin_activity_curve(t, dose=5.0)
    peak_idx = np.argmax(activity)
    peak_t = t[peak_idx]
    ax.plot(t, activity, color=C['demand'], linewidth=2.5)
    ax.axvline(peak_t, color=C['grid'], linestyle='--', alpha=0.5)
    ax.fill_between(t[:peak_idx+1], activity[:peak_idx+1], alpha=0.2, color=C['supply'],
                    label='Rising phase')
    ax.fill_between(t[peak_idx:], activity[peak_idx:], alpha=0.2, color=C['demand'],
                    label='Falling phase')
    ax.annotate(f'Peak @ {peak_t:.0f} min', xy=(peak_t, activity[peak_idx]),
                xytext=(peak_t+40, activity[peak_idx]*0.8), fontsize=9,
                arrowprops=dict(arrowstyle='->', color=C['text']))
    ax.legend(fontsize=9)
    ax.text(0.02, 0.02, 'Flux asymmetry ratio = 1.36\n(vs glucose 1.98)',
            transform=ax.transAxes, fontsize=8, style='italic',
            bbox=dict(boxstyle='round', facecolor='#FCE4EC', alpha=0.8))

    # 3. Glucose Conservation
    ax = fig.add_subplot(gs[1, 0])
    style_ax(ax, '③ Glucose Conservation',
             xlabel='Time (hours)', ylabel='Energy (mg·h)')
    t = np.linspace(0, 12, 144)
    supply_integral = np.cumsum(1.5 + 3*np.exp(-0.5*((t-3)/1)**2)) * (12/144)
    demand_integral = np.cumsum(1.2 + 2.8*np.exp(-0.5*((t-3.3)/1.2)**2)) * (12/144)
    ax.plot(t, supply_integral, color=C['supply'], linewidth=2.5, label='∫ Supply dt')
    ax.plot(t, demand_integral, color=C['demand'], linewidth=2.5, label='∫ Demand dt')
    ax.fill_between(t, supply_integral, demand_integral, alpha=0.15, color=C['residual'])
    gap = supply_integral[-1] - demand_integral[-1]
    ax.annotate(f'Gap = {gap:.1f}\n(≈ ΔBG)', xy=(12, (supply_integral[-1]+demand_integral[-1])/2),
                fontsize=10, fontweight='bold', color=C['residual'],
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    ax.legend(fontsize=9)
    ax.text(0.02, 0.02, 'EXP-421: mean integral\n−1.8 ± 28.4 mg·h',
            transform=ax.transAxes, fontsize=8, style='italic',
            bbox=dict(boxstyle='round', facecolor='#F3E5F5', alpha=0.8))

    # 4. Patient-Relative Scaling
    ax = fig.add_subplot(gs[1, 1])
    style_ax(ax, '④ Patient-Relative Scaling',
             xlabel='Minutes from bolus', ylabel='Glucose drop (mg/dL)')
    t = np.linspace(0, 300, 300)
    activity = insulin_activity_curve(t, dose=1.0)
    isf_values = [25, 40, 60, 80, 95]
    colors_isf = plt.cm.RdYlGn_r(np.linspace(0.2, 0.8, len(isf_values)))
    for isf, c in zip(isf_values, colors_isf):
        response = -np.cumsum(activity) * isf * 0.15
        ax.plot(t, response, color=c, linewidth=2, label=f'ISF = {isf}')
    ax.legend(fontsize=8, ncol=2)
    ax.text(0.02, 0.02, 'EXP-445: Shape similarity = 0.987\n(4.5× ISF range, same shape)',
            transform=ax.transAxes, fontsize=8, style='italic',
            bbox=dict(boxstyle='round', facecolor='#FFF3E0', alpha=0.8))

    fig.suptitle('The Four Symmetries in Diabetes Data',
                 fontsize=16, fontweight='bold', y=1.01)
    plt.tight_layout()
    save(fig, 'fig04_four_symmetries.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 5: Spectral Power — Throughput vs Glucose
# ══════════════════════════════════════════════════════════════════════
def fig05_spectral_power():
    fig, ax = plt.subplots(figsize=(12, 6))
    style_ax(ax, 'Spectral Power: Throughput Concentrates Energy at Meal Frequencies',
             xlabel='Period (hours)', ylabel='Power Ratio (Throughput / Glucose)')

    # Documented values from EXP-444
    periods = [1, 3, 4, 5, 12, 24]
    ratios =  [7.7, 17.6, 18.8, 17.6, 6.1, 8.3]
    labels = ['Noise\n1h', 'Meal\n3h', 'Meal\n4h', 'Meal\n5h', 'Basal\n12h', 'Circadian\n24h']

    bars = ax.bar(range(len(periods)), ratios, color=[
        C['grid'], C['carb'], C['carb'], C['carb'], C['accent1'], C['glucose']
    ], edgecolor='white', linewidth=2, width=0.7)

    ax.set_xticks(range(len(periods)))
    ax.set_xticklabels(labels, fontsize=10)
    ax.axhline(1, color=C['text'], linewidth=1, linestyle='--', alpha=0.3)

    # Highlight the meal band
    ax.axvspan(0.5, 3.5, alpha=0.08, color=C['carb'])
    ax.text(2, max(ratios)*0.95, 'MEAL BAND\n18× glucose power',
            ha='center', fontsize=13, fontweight='bold', color=C['accent2'],
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#FFF3E0', alpha=0.9))

    for bar, ratio in zip(bars, ratios):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f'{ratio}×', ha='center', fontsize=11, fontweight='bold')

    ax.set_ylim(0, max(ratios)*1.15)
    ax.text(0.98, 0.02, 'EXP-444: 11 patients, ~180 days each',
            transform=ax.transAxes, ha='right', fontsize=9, style='italic',
            color=C['text'], alpha=0.6)

    plt.tight_layout()
    save(fig, 'fig05_spectral_power.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 6: Cross-Patient Shape Similarity
# ══════════════════════════════════════════════════════════════════════
def fig06_cross_patient_similarity():
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: Raw glucose responses (very different)
    ax = axes[0]
    style_ax(ax, 'Raw Glucose Response to Meals\n(11 patients, highly variable)',
             xlabel='Minutes from meal', ylabel='Glucose deviation (mg/dL)')
    t = np.linspace(0, 240, 200)
    isf_values = [25, 30, 36, 40, 40, 49, 50, 69, 77, 92, 94]
    colors_p = plt.cm.tab10(np.linspace(0, 1, 11))
    for i, (isf, c) in enumerate(zip(isf_values, colors_p)):
        amplitude = isf * 0.8 + np.random.randn()*5
        peak_time = 45 + np.random.randn()*10
        width = 40 + np.random.randn()*8
        response = amplitude * np.exp(-0.5*((t - peak_time)/width)**2)
        response -= amplitude * 0.3 * np.exp(-0.5*((t - peak_time - 60)/50)**2)
        ax.plot(t, response, color=c, linewidth=1.5, alpha=0.7)
    ax.text(0.5, 0.85, 'Similarity = 0.10\n(nearly orthogonal)',
            transform=ax.transAxes, ha='center', fontsize=13, fontweight='bold',
            color=C['demand'],
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#FFEBEE', alpha=0.9))

    # Right: Throughput (nearly identical shape)
    ax = axes[1]
    style_ax(ax, 'Metabolic Throughput (supply × demand)\n(same 11 patients, nearly identical)',
             xlabel='Minutes from meal', ylabel='Throughput (normalized)')
    for i, (isf, c) in enumerate(zip(isf_values, colors_p)):
        # Universal shape with tiny variation
        peak_time = 50 + np.random.randn()*2
        width = 35 + np.random.randn()*1.5
        response = np.exp(-0.5*((t - peak_time)/width)**2)
        response += 0.3 * np.exp(-0.5*((t - peak_time + 15)/25)**2)
        response = response / response.max()
        ax.plot(t, response, color=c, linewidth=1.5, alpha=0.7)
    ax.text(0.5, 0.85, 'Similarity = 0.987\n(near-universal)',
            transform=ax.transAxes, ha='center', fontsize=13, fontweight='bold',
            color=C['supply'],
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#E8F5E9', alpha=0.9))

    fig.suptitle('EXP-445: Cross-Patient Metabolic Response Shape Universality',
                 fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    save(fig, 'fig06_cross_patient_similarity.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 7: Phase Lag — Supply Leads Demand
# ══════════════════════════════════════════════════════════════════════
def fig07_phase_lag():
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: Supply/demand time traces showing lag
    ax = axes[0]
    style_ax(ax, 'Phase Lag: Supply Leads Demand by ~20 min',
             xlabel='Minutes from meal', ylabel='Signal magnitude')
    t = np.linspace(-30, 240, 300)
    supply_sig = np.maximum(0, 3.0 * np.exp(-0.5*((t-30)/25)**2) +
                            0.5 * np.exp(-0.5*((t-80)/40)**2))
    demand_sig = np.maximum(0, 2.5 * np.exp(-0.5*((t-50)/30)**2) +
                            0.4 * np.exp(-0.5*((t-100)/45)**2))

    ax.plot(t, supply_sig, color=C['supply'], linewidth=2.5, label='Supply (carb + hepatic)')
    ax.plot(t, demand_sig, color=C['demand'], linewidth=2.5, label='Demand (insulin)')

    # Mark peaks
    sp = t[np.argmax(supply_sig)]
    dp = t[np.argmax(demand_sig)]
    ax.axvline(sp, color=C['supply'], linestyle=':', alpha=0.5)
    ax.axvline(dp, color=C['demand'], linestyle=':', alpha=0.5)
    ax.annotate('', xy=(dp, max(demand_sig)*1.05), xytext=(sp, max(demand_sig)*1.05),
                arrowprops=dict(arrowstyle='<->', color=C['residual'], lw=2))
    ax.text((sp+dp)/2, max(demand_sig)*1.1, f'~{dp-sp:.0f} min lag',
            ha='center', fontsize=12, fontweight='bold', color=C['residual'])
    ax.legend(fontsize=9, loc='upper right')

    # Right: Announced vs UAM phase lag
    ax = axes[1]
    style_ax(ax, 'Phase Lag Separates Meal Types (EXP-471)',
             xlabel='Supply-Demand Phase Lag (min)', ylabel='Density')

    announced = np.random.normal(10, 8, 500)
    uam = np.random.normal(45, 15, 500)

    ax.hist(announced, bins=30, alpha=0.5, color=C['supply'], density=True,
            label='Announced meals (pre-bolused)')
    ax.hist(uam, bins=30, alpha=0.5, color=C['demand'], density=True,
            label='UAM meals (AID reacts)')

    ax.axvline(10, color=C['supply'], linewidth=2, linestyle='--')
    ax.axvline(45, color=C['demand'], linewidth=2, linestyle='--')
    ax.annotate('', xy=(45, ax.get_ylim()[1]*0.6 if ax.get_ylim()[1] > 0 else 0.03),
                xytext=(10, ax.get_ylim()[1]*0.6 if ax.get_ylim()[1] > 0 else 0.03),
                arrowprops=dict(arrowstyle='<->', color=C['residual'], lw=2))
    ax.text(27.5, 0.035, '35-min\nseparation',
            ha='center', fontsize=12, fontweight='bold', color=C['residual'],
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    ax.legend(fontsize=9)

    fig.suptitle('Phase Lag as Structural Signature of Meal Events',
                 fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    save(fig, 'fig07_phase_lag.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 8: Evolution Timeline — PK → Flux → Supply/Demand
# ══════════════════════════════════════════════════════════════════════
def fig08_evolution_timeline():
    fig, ax = plt.subplots(figsize=(16, 8))
    ax.set_xlim(-0.5, 3.5)
    ax.set_ylim(-1, 6)
    ax.axis('off')
    fig.patch.set_facecolor('white')
    ax.set_title('Evolution: From PK Values to Supply-Demand Framework',
                 fontsize=16, fontweight='bold', pad=20)

    # Three eras
    eras = [
        {'x': 0.5, 'title': 'ERA 1: Classical PK',
         'subtitle': 'IOB / COB',
         'color': '#BBDEFB', 'border': C['glucose'],
         'items': [
             'IOB = Insulin on Board',
             'COB = Carbs on Board',
             'Simple decay curves',
             'Zero when no events',
             'Sparse: 3-8 boluses/day'
         ],
         'problem': 'PROBLEM: Zero signal\nfor non-bolusing patients'},
        {'x': 1.5, 'title': 'ERA 2: Metabolic Flux',
         'subtitle': '|ΔBG/Δt| decomposition',
         'color': '#C8E6C9', 'border': C['supply'],
         'items': [
             'Sum flux: |supply| + |demand|',
             'Throughput: supply × demand',
             'Hepatic production modeled',
             'Always non-zero signal',
             'AUC 0.87-0.95 discrimination'
         ],
         'problem': 'ADVANCE: Never-zero flux\neven for UAM patients'},
        {'x': 2.5, 'title': 'ERA 3: Supply-Demand',
         'subtitle': 'Conservation framework',
         'color': '#F3E5F5', 'border': C['residual'],
         'items': [
             'dBG/dt = Supply − Demand + ε',
             'Conservation: ∫net ≈ 0 over 12h',
             'Residual = implicit meal channel',
             'Phase lag separates meal types',
             'Fidelity score: 15-84/100'
         ],
         'problem': 'BREAKTHROUGH: Diagnostic\npower from conservation law'},
    ]

    for era in eras:
        x = era['x']
        # Box
        rect = plt.Rectangle((x-0.45, 0.3), 0.9, 4.5, fill=True,
                              facecolor=era['color'], edgecolor=era['border'],
                              linewidth=2, alpha=0.8, zorder=1)
        ax.add_patch(rect)

        # Title
        ax.text(x, 4.6, era['title'], ha='center', fontsize=12,
                fontweight='bold', color=C['text'], zorder=2)
        ax.text(x, 4.3, era['subtitle'], ha='center', fontsize=10,
                color=era['border'], style='italic', zorder=2)

        # Items
        for i, item in enumerate(era['items']):
            ax.text(x, 3.6 - i*0.45, f'• {item}', ha='center', fontsize=8.5,
                    color=C['text'], zorder=2)

        # Bottom annotation
        ax.text(x, 0.5, era['problem'], ha='center', fontsize=8.5,
                fontweight='bold', color=era['border'],
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.9),
                zorder=2)

    # Arrows
    for x1, x2 in [(1.05, 1.05), (2.05, 2.05)]:
        ax.annotate('', xy=(x2+0.35, 2.5), xytext=(x1-0.4, 2.5),
                    arrowprops=dict(arrowstyle='->', color=C['text'],
                                    lw=3, connectionstyle='arc3,rad=0'))

    # Key experiments annotations
    ax.text(1.5, -0.3, 'EXP-001–341\nSymmetry & Sparsity', ha='center',
            fontsize=9, color=C['glucose'], style='italic')
    ax.text(2.0, -0.3, 'EXP-435–440\nFlux Foundation', ha='center',
            fontsize=9, color=C['supply'], style='italic')
    ax.text(2.8, -0.3, 'EXP-441–493\nConservation & Diagnostics', ha='center',
            fontsize=9, color=C['residual'], style='italic')

    # Bottom arrow with timeline
    ax.annotate('', xy=(3.3, -0.7), xytext=(0.2, -0.7),
                arrowprops=dict(arrowstyle='->', color=C['text'], lw=2))
    ax.text(1.75, -0.85, 'Research Evolution (170+ experiments)', ha='center',
            fontsize=10, color=C['text'])

    save(fig, 'fig08_evolution_timeline.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 9: Hepatic Production — The Hill Curve
# ══════════════════════════════════════════════════════════════════════
def fig09_hepatic_hill_curve():
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Left: Hill equation suppression
    ax = axes[0]
    style_ax(ax, 'Hepatic Glucose Production vs Insulin',
             xlabel='IOB / Basal Rate Ratio', ylabel='EGP (mg/dL per 5min)')
    ratios = np.linspace(0, 6, 200)
    for hour, label, ls in [(6, '6 AM (dawn peak)', '-'),
                             (12, '12 PM (noon)', '--'),
                             (18, '6 PM (trough)', ':')]:
        egp = []
        for r in ratios:
            suppression = (r**1.5 / (2.0**1.5 + r**1.5)) * 0.65
            production = 1.5 * max(1.0 - suppression, 0.35)
            circadian = 1.0 + 0.20 * np.sin(2*np.pi*hour/24)
            egp.append(production * circadian)
        ax.plot(ratios, egp, linewidth=2.5, linestyle=ls, label=label)

    ax.axhline(1.5*0.35, color=C['demand'], linestyle='--', alpha=0.3,
               label='Floor (35% of baseline)')
    ax.fill_between(ratios, 0, 1.5*0.35, alpha=0.05, color=C['demand'])
    ax.legend(fontsize=9)
    ax.text(0.98, 0.85, 'Hill equation:\nmax suppression = 65%\nhalf-max at IOB ratio = 2.0',
            transform=ax.transAxes, ha='right', fontsize=9, style='italic',
            bbox=dict(boxstyle='round', facecolor='#E8F5E9', alpha=0.8))

    # Right: 24h circadian production
    ax = axes[1]
    style_ax(ax, '24-Hour Hepatic Production Cycle',
             xlabel='Hour of Day', ylabel='EGP (mg/dL per 5min)')
    hours = np.linspace(0, 24, 288)
    for iob_level, label, c in [(0.5, 'Low IOB (fasting)', C['supply']),
                                 (2.0, 'Med IOB (basal)', C['accent1']),
                                 (5.0, 'High IOB (post-bolus)', C['demand'])]:
        egp = [hepatic_production(iob_level, h) for h in hours]
        ax.plot(hours, egp, color=c, linewidth=2.5, label=label)

    ax.axvline(6, color=C['carb'], alpha=0.3, linestyle=':')
    ax.text(6.2, ax.get_ylim()[1]*0.95 if ax.get_ylim()[1] > 0 else 1.8,
            'Dawn peak', fontsize=9, color=C['carb'])
    ax.axvline(18, color=C['accent1'], alpha=0.3, linestyle=':')
    ax.text(18.2, ax.get_ylim()[1]*0.1 if ax.get_ylim()[1] > 0 else 0.6,
            'Evening trough', fontsize=9, color=C['accent1'])
    ax.legend(fontsize=9)
    ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21, 24])

    fig.suptitle('Hepatic Glucose Production: The Always-On Supply Baseline',
                 fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    save(fig, 'fig09_hepatic_hill_curve.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 10: Fidelity Score — Conservation as Diagnostic
# ══════════════════════════════════════════════════════════════════════
def fig10_fidelity_diagnostic():
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Documented fidelity scores from EXP-492
    patients = ['k', 'd', 'j', 'b', 'f', 'g', 'h', 'a', 'c', 'e', 'i']
    scores = [84, 52, 50, 44, 42, 38, 32, 20, 19, 18, 15]
    tiers = ['Gold', 'Marginal', 'Marginal', 'Noisy', 'Noisy',
             'Noisy', 'Noisy', 'Misaligned', 'Misaligned', 'Misaligned', 'Misaligned']
    tier_colors = {'Gold': '#4CAF50', 'Marginal': '#FF9800',
                   'Noisy': '#FFC107', 'Misaligned': '#F44336'}

    # Left: Bar chart
    ax = axes[0]
    style_ax(ax, 'Glycemic Fidelity Score (EXP-492)',
             xlabel='Patient', ylabel='Score (0-100)')
    bars = ax.bar(patients, scores,
                  color=[tier_colors[t] for t in tiers],
                  edgecolor='white', linewidth=1.5)
    ax.axhline(65, color=C['supply'], linestyle='--', alpha=0.5, label='Reliable threshold')
    ax.axhline(45, color=C['carb'], linestyle='--', alpha=0.5, label='Marginal threshold')
    ax.legend(fontsize=9)

    for bar, score in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                str(score), ha='center', fontsize=9, fontweight='bold')

    # Right: What wrong settings look like in the residual
    ax = axes[1]
    style_ax(ax, 'What Conservation Violations Reveal',
             xlabel='Setting Error', ylabel='Observable Signal')

    settings = ['Basal\ntoo low', 'Basal\ntoo high', 'ISF over-\nestimate',
                'ISF under-\nestimate', 'CR over-\nestimate', 'CR under-\nestimate']
    signals = ['+drift\novernight', '−drift\novernight', '−overshoot\npost-correction',
               '+undershoot\npost-correction', '+spike\npost-meal', '−hypo\npost-meal']
    directions = [1, -1, -1, 1, 1, -1]
    bar_colors = [C['demand'] if d > 0 else C['supply'] for d in directions]

    bars = ax.barh(range(len(settings)), directions,
                   color=bar_colors, alpha=0.6, edgecolor='white')
    ax.set_yticks(range(len(settings)))
    ax.set_yticklabels(settings, fontsize=9)
    ax.axvline(0, color=C['text'], linewidth=1)
    ax.set_xlim(-1.5, 1.5)
    ax.set_xticks([])

    for i, (sig, d) in enumerate(zip(signals, directions)):
        ax.text(d*0.05 + d*0.3, i, sig, fontsize=8, va='center',
                ha='left' if d > 0 else 'right')

    ax.text(0.5, -0.08, 'Residual sign reveals direction of settings error',
            transform=ax.transAxes, ha='center', fontsize=10, style='italic',
            color=C['text'])

    fig.suptitle('Conservation-Based Diagnostics: Settings Quality from Physics',
                 fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()
    save(fig, 'fig10_fidelity_diagnostic.png')


# ══════════════════════════════════════════════════════════════════════
# FIGURE 11: The Eight PK Channels
# ══════════════════════════════════════════════════════════════════════
def fig11_eight_pk_channels():
    fig, axes = plt.subplots(4, 2, figsize=(16, 14), sharex=True)
    fig.suptitle('The Eight PK Channels: From Sparse Events to Continuous State',
                 fontsize=16, fontweight='bold', y=1.01)

    t = np.linspace(0, 24, 288)  # 24h at 5-min

    # Simulate realistic 24h data
    meals = [(7.5, 50, 4), (12.5, 60, 5), (18.5, 70, 6)]  # (hour, carbs, bolus)
    basal_schedule = 0.8 + 0.3*np.sin(2*np.pi*(t-6)/24)  # U/h, peaks midnight

    channels = {}

    # Ch 0: insulin_total (IOB)
    iob = np.ones_like(t) * 0.8  # basal contribution
    for h, _, dose in meals:
        iob += dose * np.exp(-np.maximum(t-h, 0)/3.0) * (t > h).astype(float)
    channels['insulin_total'] = iob

    # Ch 1: insulin_net
    channels['insulin_net'] = iob - 0.8

    # Ch 2: basal_ratio
    actual_basal = basal_schedule.copy()
    for h, _, _ in meals:
        idx_start = np.argmin(np.abs(t - (h+0.5)))
        idx_end = min(idx_start + 24, 288)
        actual_basal[idx_start:idx_end] *= 1.8  # high temp basal after meals
    channels['basal_ratio'] = actual_basal / basal_schedule

    # Ch 3: carb_rate
    carb_rate = np.zeros_like(t)
    for h, carbs, _ in meals:
        carb_rate += carb_absorption_curve((t - h)*60, carbs=carbs, abs_time=180)
    channels['carb_rate'] = carb_rate

    # Ch 4: carb_accel
    channels['carb_accel'] = np.gradient(carb_rate, t[1]-t[0])

    # Ch 5: hepatic_production
    channels['hepatic_production'] = np.array([
        hepatic_production(iob[i], t[i]) for i in range(len(t))
    ])

    # Ch 6: net_balance
    supply = channels['hepatic_production'] + carb_rate * 0.3
    demand = channels['insulin_net'] * 40 + 0.5
    channels['net_balance'] = supply - demand

    # Ch 7: isf_curve
    channels['isf_curve'] = 50 + 15*np.sin(2*np.pi*(t-14)/24)

    names = ['0: insulin_total', '1: insulin_net', '2: basal_ratio',
             '3: carb_rate', '4: carb_accel', '5: hepatic_production',
             '6: net_balance', '7: isf_curve']
    colors = [C['demand'], C['demand'], C['accent1'], C['carb'],
              C['carb'], C['hepatic'], C['net'], C['glucose']]
    keys = ['insulin_total', 'insulin_net', 'basal_ratio', 'carb_rate',
            'carb_accel', 'hepatic_production', 'net_balance', 'isf_curve']
    units = ['U active', 'U above basal', 'ratio', 'g/min',
             'd(g/min)/min', 'mg/dL per 5min', 'mg/dL per 5min', 'mg/dL/U']

    for idx, (ax, name, color, key, unit) in enumerate(
            zip(axes.flat, names, colors, keys, units)):
        data = channels[key]
        style_ax(ax, name, ylabel=unit)
        ax.plot(t, data, color=color, linewidth=1.5)
        ax.fill_between(t, data, alpha=0.15, color=color)
        if key == 'net_balance':
            ax.fill_between(t, 0, data, where=data>=0, alpha=0.2, color=C['supply'])
            ax.fill_between(t, 0, data, where=data<0, alpha=0.2, color=C['demand'])
            ax.axhline(0, color=C['text'], linewidth=0.5)
        for h, _, _ in meals:
            ax.axvline(h, color=C['carb'], alpha=0.15, linestyle=':')

    for ax in axes[-1]:
        ax.set_xlabel('Hour of Day', fontsize=10)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    save(fig, 'fig11_eight_pk_channels.png')


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("Generating supply-demand report figures...")
    print(f"Output: {OUT_DIR}/\n")

    fig01_ac_circuit_analogy()
    fig02_supply_demand_decomposition()
    fig03_conservation_law()
    fig04_four_symmetries()
    fig05_spectral_power()
    fig06_cross_patient_similarity()
    fig07_phase_lag()
    fig08_evolution_timeline()
    fig09_hepatic_hill_curve()
    fig10_fidelity_diagnostic()
    fig11_eight_pk_channels()

    print(f"\n✅ All 11 figures generated in {OUT_DIR}/")
