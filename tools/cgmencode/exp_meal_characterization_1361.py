#!/usr/bin/env python3
"""EXP-1361: Meal Peak Detection, Characterization & Template Analysis.

Detects meals via physics residual (F1=0.939), centers on glucose peak,
extracts multi-channel windows, and builds aligned meal templates.

Analysis components:
  1. Peak-centered meal detection and feature extraction
  2. Phase-of-day periodicity analysis per patient
  3. Aligned meal templates (median + IQR envelope) by meal window
  4. Cross-patient template comparison
  5. Visualizations: phase histograms, aligned overlays, template envelopes

Uses unique filename to avoid collision with concurrent agents.
"""

import sys, os, json, time, warnings
import numpy as np

warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients
from cgmencode.exp_metabolic_441 import compute_supply_demand
from cgmencode.exp_meal_periodicity_1101 import detect_meals_from_physics

PATIENTS_DIR = os.path.join(os.path.dirname(__file__),
                            '..', '..', 'externals', 'ns-data', 'patients')
OUT_DIR = os.path.join(os.path.dirname(__file__),
                       '..', '..', 'externals', 'experiments')
VIZ_DIR = os.path.join(os.path.dirname(__file__),
                       '..', '..', 'visualizations', 'meal-characterization')

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288
DT_MIN = 5  # minutes per step

# Window around peak: -30 min to +3h = 42 steps total
PRE_PEAK_STEPS = 6   # 30 min before peak
POST_PEAK_STEPS = 36  # 3h after peak
WINDOW_LEN = PRE_PEAK_STEPS + 1 + POST_PEAK_STEPS  # 43 steps

# Meal window definitions
MEAL_WINDOWS = {
    'breakfast': (5.0, 10.0),
    'lunch': (10.0, 14.0),
    'dinner': (17.0, 21.0),
}

# Patient therapy settings
PATIENT_SETTINGS = {
    'a': {'isf': 49, 'cr': 4},
    'b': {'isf': 95, 'cr': 12},
    'c': {'isf': 75, 'cr': 4},
    'd': {'isf': 40, 'cr': 14},
    'e': {'isf': 33, 'cr': 3},
    'f': {'isf': 20, 'cr': 5},
    'g': {'isf': 65, 'cr': 8},
    'h': {'isf': 90, 'cr': 10},
    'i': {'isf': 50, 'cr': 8},
    'j': {'isf': 40, 'cr': 6},
    'k': {'isf': 25, 'cr': 10},
}


def classify_window(hour):
    for name, (lo, hi) in MEAL_WINDOWS.items():
        if lo <= hour < hi:
            return name
    return 'snack'


def find_peak_in_window(glucose, detect_idx, max_search=24):
    """Find glucose peak within max_search steps after detection."""
    n = len(glucose)
    end = min(n, detect_idx + max_search)
    window = glucose[detect_idx:end]
    valid = ~np.isnan(window)
    if valid.sum() == 0:
        return detect_idx
    peak_offset = np.nanargmax(window)
    return detect_idx + peak_offset


def extract_meal_window(arr, peak_idx, pre=PRE_PEAK_STEPS, post=POST_PEAK_STEPS):
    """Extract a fixed-size window centered on peak, NaN-padded at edges."""
    n = len(arr)
    total = pre + 1 + post
    result = np.full(total, np.nan)
    src_start = peak_idx - pre
    src_end = peak_idx + post + 1
    dst_start = 0
    dst_end = total

    if src_start < 0:
        dst_start = -src_start
        src_start = 0
    if src_end > n:
        dst_end = total - (src_end - n)
        src_end = n

    chunk = arr[src_start:src_end]
    result[dst_start:dst_start + len(chunk)] = chunk
    return result


def compute_meal_features(glucose_win, supply_win, demand_win, net_win,
                          residual_win, iob_win, pre_steps=PRE_PEAK_STEPS):
    """Compute per-meal features from windowed signals."""
    peak_idx = pre_steps  # center of window
    pre_bg = np.nanmean(glucose_win[:pre_steps]) if pre_steps > 0 else np.nan
    peak_bg = glucose_win[peak_idx] if not np.isnan(glucose_win[peak_idx]) else np.nan
    excursion = peak_bg - pre_bg if not (np.isnan(peak_bg) or np.isnan(pre_bg)) else np.nan

    # Rise rate: mean glucose change per 5 min during rise phase
    rise_phase = glucose_win[:peak_idx + 1]
    valid_rise = rise_phase[~np.isnan(rise_phase)]
    if len(valid_rise) > 1:
        rise_rate = float(np.mean(np.diff(valid_rise)))
    else:
        rise_rate = np.nan

    # Recovery: how far glucose falls from peak in next 2h
    recovery_end = min(len(glucose_win), peak_idx + 24)
    post_min = np.nanmin(glucose_win[peak_idx:recovery_end]) if recovery_end > peak_idx else np.nan
    recovery = peak_bg - post_min if not (np.isnan(peak_bg) or np.isnan(post_min)) else np.nan

    # Duration: time from start of rise to recovery to pre_bg level (steps)
    duration_steps = np.nan
    if not np.isnan(pre_bg):
        post_peak = glucose_win[peak_idx:]
        below = np.where(post_peak <= pre_bg + 5)[0]  # within 5 mg/dL of baseline
        if len(below) > 0:
            duration_steps = float(peak_idx + below[0])

    # Residual integral (positive only, in window)
    pos_resid = np.clip(np.nan_to_num(residual_win, nan=0), 0, None)
    resid_integral = float(np.sum(pos_resid))

    # Supply/demand features
    peak_supply = float(np.nanmax(supply_win)) if np.any(~np.isnan(supply_win)) else np.nan
    peak_demand = float(np.nanmax(demand_win)) if np.any(~np.isnan(demand_win)) else np.nan
    mean_net = float(np.nanmean(net_win)) if np.any(~np.isnan(net_win)) else np.nan

    # IOB at detection
    iob_at_detect = float(iob_win[0]) if not np.isnan(iob_win[0]) else np.nan

    return {
        'pre_bg': round(float(pre_bg), 1) if not np.isnan(pre_bg) else None,
        'peak_bg': round(float(peak_bg), 1) if not np.isnan(peak_bg) else None,
        'excursion': round(float(excursion), 1) if not np.isnan(excursion) else None,
        'rise_rate': round(float(rise_rate), 2) if not np.isnan(rise_rate) else None,
        'recovery': round(float(recovery), 1) if not np.isnan(recovery) else None,
        'duration_steps': int(duration_steps) if not np.isnan(duration_steps) else None,
        'duration_min': int(duration_steps * DT_MIN) if not np.isnan(duration_steps) else None,
        'resid_integral': round(float(resid_integral), 2),
        'peak_supply': round(float(peak_supply), 2) if not np.isnan(peak_supply) else None,
        'peak_demand': round(float(peak_demand), 2) if not np.isnan(peak_demand) else None,
        'mean_net': round(float(mean_net), 2) if not np.isnan(mean_net) else None,
        'iob_at_detect': round(float(iob_at_detect), 2) if not np.isnan(iob_at_detect) else None,
    }


def estimate_carbs(excursion, resid_integral, isf, cr):
    """Estimate carbs via excursion and physics residual methods."""
    c_excursion = round(excursion * cr / isf, 1) if excursion and excursion > 0 else None
    c_physics = round(resid_integral * cr / isf, 1) if resid_integral > 0 else 0.0
    return c_excursion, c_physics


# ─── MAIN ANALYSIS ───────────────────────────────────────────────────

def run_analysis(patients):
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(VIZ_DIR, exist_ok=True)

    all_meal_records = []
    per_patient_summary = []

    # Collect aligned windows for template building
    # Key: (patient, meal_window) → list of glucose windows
    template_windows = {}

    for p in patients:
        name = p['name']
        df = p['df']
        pk = p['pk']
        settings = PATIENT_SETTINGS.get(name, {'isf': 50, 'cr': 8})
        isf, cr = settings['isf'], settings['cr']

        glucose = df['glucose'].values.astype(float)
        iob = df['iob'].values.astype(float)
        carbs_col = df['carbs'].values.astype(float)
        n = len(glucose)
        n_days = n / STEPS_PER_DAY

        # Supply-demand decomposition
        sd = compute_supply_demand(df, pk_array=pk)
        net_flux = sd['net']
        supply = sd['supply']
        demand = sd['demand']

        # Compute residual
        dg = np.diff(glucose, prepend=glucose[0])
        residual = dg - net_flux

        # Detect meals via physics
        raw_meals = detect_meals_from_physics(df, sd, threshold_sigma=2.0, merge_gap_steps=12)

        patient_meals = []
        for m in raw_meals:
            detect_idx = m['index']

            # Find actual glucose peak
            peak_idx = find_peak_in_window(glucose, detect_idx, max_search=24)

            # Extract aligned windows
            g_win = extract_meal_window(glucose, peak_idx)
            s_win = extract_meal_window(supply, peak_idx)
            d_win = extract_meal_window(demand, peak_idx)
            n_win = extract_meal_window(net_flux, peak_idx)
            r_win = extract_meal_window(residual, peak_idx)
            i_win = extract_meal_window(iob, peak_idx)

            # Hour of day at peak
            hour = (peak_idx % STEPS_PER_DAY) * DT_MIN / 60.0
            window = classify_window(hour)

            # Check announced
            announced = m.get('announced', False)
            # Also check entered carbs near peak
            cs = max(0, peak_idx - 12)
            ce = min(n, peak_idx + 6)
            entered = float(np.nansum(carbs_col[cs:ce]))
            if entered > 0:
                announced = True

            # Features
            feats = compute_meal_features(g_win, s_win, d_win, n_win, r_win, i_win)

            # Carb estimates
            c_exc, c_phys = estimate_carbs(
                feats['excursion'], feats['resid_integral'], isf, cr)

            rec = {
                'patient': name,
                'detect_idx': int(detect_idx),
                'peak_idx': int(peak_idx),
                'peak_offset': int(peak_idx - detect_idx),
                'hour': round(hour, 1),
                'window': window,
                'day_index': int(peak_idx // STEPS_PER_DAY),
                'announced': announced,
                'entered_carbs': round(entered, 1),
                'carbs_excursion': c_exc,
                'carbs_physics': c_phys,
                **feats,
            }
            patient_meals.append(rec)

            # Store aligned glucose window for templates
            key = (name, window)
            if key not in template_windows:
                template_windows[key] = []
            template_windows[key].append(g_win)

            # Population template
            pop_key = ('_population', window)
            if pop_key not in template_windows:
                template_windows[pop_key] = []
            template_windows[pop_key].append(g_win - (feats['pre_bg'] or 0))

        all_meal_records.extend(patient_meals)

        # Per-patient summary
        n_meals = len(patient_meals)
        n_announced = sum(1 for m in patient_meals if m['announced'])
        hours = [m['hour'] for m in patient_meals]
        excursions = [m['excursion'] for m in patient_meals if m['excursion'] is not None]

        # Phase-of-day histogram (24 bins, 1h each)
        hour_hist, _ = np.histogram(hours, bins=np.arange(25))

        # Find dominant meal times (peaks in histogram)
        from scipy.signal import find_peaks as scipy_find_peaks
        peaks_idx, props = scipy_find_peaks(hour_hist.astype(float), height=2, distance=2)
        dominant_hours = sorted(peaks_idx.tolist())

        # Meal window counts
        window_counts = {}
        for w in ['breakfast', 'lunch', 'dinner', 'snack']:
            wc = [m for m in patient_meals if m['window'] == w]
            window_counts[w] = {
                'n': len(wc),
                'n_uam': sum(1 for m in wc if not m['announced']),
                'pct_uam': round(100 * sum(1 for m in wc if not m['announced']) / max(len(wc), 1), 1),
                'median_excursion': round(float(np.median([m['excursion'] for m in wc if m['excursion'] is not None])), 1) if any(m['excursion'] is not None for m in wc) else None,
                'median_physics_carbs': round(float(np.median([m['carbs_physics'] for m in wc if m['carbs_physics'] is not None])), 1) if any(m['carbs_physics'] is not None for m in wc) else None,
            }

        psummary = {
            'patient': name,
            'n_meals': n_meals,
            'n_days': round(n_days, 1),
            'meals_per_day': round(n_meals / max(n_days, 1), 1),
            'n_announced': n_announced,
            'n_uam': n_meals - n_announced,
            'pct_uam': round(100 * (n_meals - n_announced) / max(n_meals, 1), 1),
            'median_excursion': round(float(np.median(excursions)), 1) if excursions else None,
            'mean_excursion': round(float(np.mean(excursions)), 1) if excursions else None,
            'hour_histogram': hour_hist.tolist(),
            'dominant_hours': dominant_hours,
            'window_counts': window_counts,
            'isf': isf,
            'cr': cr,
        }
        per_patient_summary.append(psummary)

        print(f"Patient {name}: {n_meals} meals ({psummary['meals_per_day']}/day), "
              f"{psummary['pct_uam']}% UAM, median excursion {psummary['median_excursion']} mg/dL")
        print(f"  Dominant hours: {dominant_hours}")
        for w in ['breakfast', 'lunch', 'dinner', 'snack']:
            wc = window_counts[w]
            print(f"  {w:12s}: n={wc['n']:>3d}, {wc['pct_uam']:4.0f}% UAM, "
                  f"excursion={wc['median_excursion']}mg, carbs={wc['median_physics_carbs']}g")

    # ─── TEMPLATE ANALYSIS ────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("MEAL TEMPLATE ANALYSIS")

    templates = {}
    for key, windows_list in template_windows.items():
        patient, window = key
        arr = np.array(windows_list)  # (n_meals, WINDOW_LEN)
        n_m = arr.shape[0]
        if n_m < 5:
            continue

        median_curve = np.nanmedian(arr, axis=0)
        p25_curve = np.nanpercentile(arr, 25, axis=0)
        p75_curve = np.nanpercentile(arr, 75, axis=0)
        mean_curve = np.nanmean(arr, axis=0)

        templates[f"{patient}_{window}"] = {
            'patient': patient,
            'window': window,
            'n_meals': n_m,
            'median': median_curve.tolist(),
            'p25': p25_curve.tolist(),
            'p75': p75_curve.tolist(),
            'mean': mean_curve.tolist(),
        }

    # Population templates (baseline-subtracted)
    print("\nPopulation templates (baseline-subtracted, centered on peak):")
    for w in ['breakfast', 'lunch', 'dinner', 'snack']:
        key = f"_population_{w}"
        if key in templates:
            t = templates[key]
            peak_val = t['median'][PRE_PEAK_STEPS]
            print(f"  {w:12s}: n={t['n_meals']:>4d}, median peak rise={peak_val:+.1f} mg/dL, "
                  f"IQR=[{t['p25'][PRE_PEAK_STEPS]:+.1f}, {t['p75'][PRE_PEAK_STEPS]:+.1f}]")

    # ─── PHASE-OF-DAY ANALYSIS ────────────────────────────────────────
    print(f"\n{'='*70}")
    print("PHASE-OF-DAY PERIODICITY")

    all_hours = [m['hour'] for m in all_meal_records]
    pop_hist, _ = np.histogram(all_hours, bins=np.arange(25))
    print(f"\nPopulation meal frequency by hour (n={len(all_meal_records)}):")
    for h in range(24):
        bar = '█' * int(pop_hist[h] / max(pop_hist.max(), 1) * 40)
        print(f"  {h:02d}:00  {pop_hist[h]:>4d}  {bar}")

    # Per-patient phase clustering
    print("\nPer-patient dominant meal phases:")
    for ps in per_patient_summary:
        dh = ps['dominant_hours']
        print(f"  {ps['patient']}: {dh} ({len(dh)} clusters)")

    # ─── VISUALIZATIONS ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("GENERATING VISUALIZATIONS...")

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec

        time_axis = np.arange(WINDOW_LEN) * DT_MIN - PRE_PEAK_STEPS * DT_MIN  # minutes relative to peak

        # ── Fig 1: Population phase-of-day histogram ──────────────────
        fig, axes = plt.subplots(3, 4, figsize=(20, 12), sharey=False)
        fig.suptitle('Meal Timing by Phase of Day (Physics Detector, 2σ)', fontsize=14)

        for idx, ps in enumerate(per_patient_summary):
            ax = axes[idx // 4, idx % 4]
            hist = ps['hour_histogram']
            colors = []
            for h in range(24):
                w = classify_window(h)
                colors.append({'breakfast': '#FF9800', 'lunch': '#4CAF50',
                              'dinner': '#2196F3', 'snack': '#9E9E9E'}[w])
            ax.bar(range(24), hist, color=colors, alpha=0.8)
            ax.set_title(f"Patient {ps['patient']} ({ps['n_meals']} meals)")
            ax.set_xlabel('Hour of day')
            ax.set_ylabel('Count')
            ax.set_xticks([0, 6, 12, 18, 24])
            for dh in ps['dominant_hours']:
                ax.axvline(dh, color='red', alpha=0.3, ls='--')

        # Remove unused subplot
        if len(per_patient_summary) < 12:
            axes[2, 3].axis('off')

        plt.tight_layout()
        path1 = os.path.join(VIZ_DIR, 'fig1_phase_of_day_histograms.png')
        fig.savefig(path1, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {path1}")

        # ── Fig 2: Population aligned meal templates by window ────────
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Aligned Meal Templates (centered on glucose peak, baseline-subtracted)', fontsize=13)

        for idx, w in enumerate(['breakfast', 'lunch', 'dinner', 'snack']):
            ax = axes[idx // 2, idx % 2]
            key = f"_population_{w}"
            if key in templates:
                t = templates[key]
                ax.fill_between(time_axis, t['p25'], t['p75'], alpha=0.3, color='C0', label='IQR')
                ax.plot(time_axis, t['median'], 'C0-', lw=2, label=f"Median (n={t['n_meals']})")
                ax.plot(time_axis, t['mean'], 'C1--', lw=1, alpha=0.7, label='Mean')
                ax.axhline(0, color='gray', ls=':', alpha=0.5)
                ax.axvline(0, color='red', ls='--', alpha=0.5, label='Peak')
            ax.set_title(f"{w.title()} meals")
            ax.set_xlabel('Minutes relative to peak')
            ax.set_ylabel('ΔGlucose (mg/dL)')
            ax.legend(fontsize=8)
            ax.set_xlim(time_axis[0], time_axis[-1])

        plt.tight_layout()
        path2 = os.path.join(VIZ_DIR, 'fig2_population_meal_templates.png')
        fig.savefig(path2, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {path2}")

        # ── Fig 3: Per-patient meal overlays for dinner ───────────────
        fig, axes = plt.subplots(3, 4, figsize=(20, 12))
        fig.suptitle('Individual Dinner Meals Overlaid (glucose, peak-centered)', fontsize=14)

        for idx, ps in enumerate(per_patient_summary):
            ax = axes[idx // 4, idx % 4]
            key = f"{ps['patient']}_dinner"
            if key in templates:
                t = templates[key]
                n_show = min(t['n_meals'], 50)
                # Get individual windows
                wins = template_windows.get((ps['patient'], 'dinner'), [])
                for i, win in enumerate(wins[:n_show]):
                    ax.plot(time_axis, win, alpha=0.1, color='C0', lw=0.5)
                ax.plot(time_axis, t['median'], 'C1-', lw=2, label='Median')
                ax.fill_between(time_axis, t['p25'], t['p75'], alpha=0.2, color='C1')
            ax.set_title(f"Patient {ps['patient']}")
            ax.axvline(0, color='red', ls='--', alpha=0.3)
            ax.set_xlabel('Min from peak')
            ax.set_ylabel('Glucose (mg/dL)')

        if len(per_patient_summary) < 12:
            axes[2, 3].axis('off')

        plt.tight_layout()
        path3 = os.path.join(VIZ_DIR, 'fig3_dinner_overlays.png')
        fig.savefig(path3, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {path3}")

        # ── Fig 4: Cross-patient template comparison ──────────────────
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Cross-Patient Meal Templates by Window (median glucose)', fontsize=13)

        colors_pat = plt.cm.tab10(np.linspace(0, 1, 11))
        for idx, w in enumerate(['breakfast', 'lunch', 'dinner', 'snack']):
            ax = axes[idx // 2, idx % 2]
            for pi, ps in enumerate(per_patient_summary):
                key = f"{ps['patient']}_{w}"
                if key in templates:
                    t = templates[key]
                    if t['n_meals'] >= 10:
                        # Baseline-subtract for comparison
                        med = np.array(t['median'])
                        baseline = np.nanmean(med[:PRE_PEAK_STEPS])
                        ax.plot(time_axis, med - baseline, color=colors_pat[pi],
                                lw=1.5, label=f"{ps['patient']} (n={t['n_meals']})", alpha=0.8)
            ax.set_title(f"{w.title()}")
            ax.set_xlabel('Minutes relative to peak')
            ax.set_ylabel('ΔGlucose (mg/dL)')
            ax.axhline(0, color='gray', ls=':', alpha=0.5)
            ax.axvline(0, color='red', ls='--', alpha=0.3)
            ax.legend(fontsize=7, ncol=2)

        plt.tight_layout()
        path4 = os.path.join(VIZ_DIR, 'fig4_cross_patient_templates.png')
        fig.savefig(path4, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {path4}")

        # ── Fig 5: Carb estimate distributions by method ──────────────
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.suptitle('Carb Estimate Distributions (Physics Residual vs Excursion)', fontsize=13)

        physics_carbs = [m['carbs_physics'] for m in all_meal_records
                        if m['carbs_physics'] is not None and m['carbs_physics'] > 0]
        excursion_carbs = [m['carbs_excursion'] for m in all_meal_records
                          if m['carbs_excursion'] is not None and m['carbs_excursion'] > 0]

        ax = axes[0]
        ax.hist(physics_carbs, bins=50, range=(0, 100), alpha=0.7, color='C0', label='Physics')
        ax.hist(excursion_carbs, bins=50, range=(0, 100), alpha=0.5, color='C1', label='Excursion')
        ax.set_xlabel('Estimated carbs (g)')
        ax.set_ylabel('Count')
        ax.set_title('All meals')
        ax.legend()

        # Announced vs UAM
        ax = axes[1]
        phys_ann = [m['carbs_physics'] for m in all_meal_records
                    if m['announced'] and m['carbs_physics'] and m['carbs_physics'] > 0]
        phys_uam = [m['carbs_physics'] for m in all_meal_records
                    if not m['announced'] and m['carbs_physics'] and m['carbs_physics'] > 0]
        ax.hist(phys_ann, bins=50, range=(0, 100), alpha=0.7, color='C2', label=f'Announced (n={len(phys_ann)})')
        ax.hist(phys_uam, bins=50, range=(0, 100), alpha=0.5, color='C3', label=f'UAM (n={len(phys_uam)})')
        ax.set_xlabel('Estimated carbs (g)')
        ax.set_ylabel('Count')
        ax.set_title('Physics carbs: Announced vs UAM')
        ax.legend()

        plt.tight_layout()
        path5 = os.path.join(VIZ_DIR, 'fig5_carb_distributions.png')
        fig.savefig(path5, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {path5}")

        # ── Fig 6: Excursion vs rise rate scatter by window ───────────
        fig, ax = plt.subplots(figsize=(10, 7))
        window_colors = {'breakfast': '#FF9800', 'lunch': '#4CAF50',
                        'dinner': '#2196F3', 'snack': '#9E9E9E'}
        for w in ['breakfast', 'lunch', 'dinner', 'snack']:
            exc = [m['excursion'] for m in all_meal_records
                   if m['window'] == w and m['excursion'] is not None and m['rise_rate'] is not None]
            rr = [m['rise_rate'] for m in all_meal_records
                  if m['window'] == w and m['excursion'] is not None and m['rise_rate'] is not None]
            ax.scatter(rr, exc, alpha=0.15, s=10, color=window_colors[w], label=f'{w} (n={len(exc)})')
        ax.set_xlabel('Rise rate (mg/dL per 5 min)')
        ax.set_ylabel('Excursion (mg/dL)')
        ax.set_title('Meal Rise Rate vs Excursion by Window')
        ax.legend()
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 200)

        plt.tight_layout()
        path6 = os.path.join(VIZ_DIR, 'fig6_rise_rate_vs_excursion.png')
        fig.savefig(path6, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {path6}")

    except ImportError as e:
        print(f"  Skipping visualizations: {e}")

    # ─── SAVE RESULTS ─────────────────────────────────────────────────
    elapsed = time.time() - t0

    # Summary
    n_total = len(all_meal_records)
    n_uam = sum(1 for m in all_meal_records if not m['announced'])
    result = {
        'name': 'EXP-1361: Meal Peak Detection, Characterization & Templates',
        'n_patients': len(patients),
        'n_meals': n_total,
        'n_announced': n_total - n_uam,
        'n_uam': n_uam,
        'pct_uam': round(100 * n_uam / max(n_total, 1), 1),
        'per_patient': per_patient_summary,
        'population_hour_histogram': pop_hist.tolist(),
        'elapsed_sec': round(elapsed, 1),
    }

    summary_path = os.path.join(OUT_DIR, 'exp-1361_meal_characterization.json')
    with open(summary_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved summary: {summary_path}")

    # Detail (per-meal records, without full windows to keep size manageable)
    detail_path = os.path.join(OUT_DIR, 'exp-1361_meal_characterization_detail.json')
    with open(detail_path, 'w') as f:
        json.dump({'name': 'EXP-1361 detail', 'meals': all_meal_records}, f, indent=2, default=str)
    print(f"Saved detail: {detail_path}")

    # Templates (separate file, larger)
    template_path = os.path.join(OUT_DIR, 'exp-1361_meal_templates.json')
    with open(template_path, 'w') as f:
        json.dump(templates, f, indent=2, default=str)
    print(f"Saved templates: {template_path}")

    print(f"\nTotal elapsed: {elapsed:.1f}s")
    return result


if __name__ == '__main__':
    patients = load_patients(PATIENTS_DIR)
    run_analysis(patients)
