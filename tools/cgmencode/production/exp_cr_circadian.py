"""EXP-2536: Circadian CR Variation.

Tests whether carb ratio (CR) effectiveness varies by time of day,
analogous to the circadian ISF variation found in EXP-2271.
Examines dawn phenomenon effects on meal coverage, effective CR
by time block, and CR-ISF circadian correlation.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2536_cr_circadian.json'
STEPS_5MIN = 12   # 1 hour
STEPS_2H = 24     # 2 hours at 5-min intervals
STEPS_4H = 48     # 4 hours at 5-min intervals
MIN_CARBS = 10    # minimum carb threshold for reliable CR analysis

TIME_BLOCKS = {
    'breakfast':       (6, 10),
    'lunch':           (11, 14),
    'afternoon_snack': (14, 17),
    'dinner':          (17, 21),
    'late_night':      (21, 6),   # wraps around midnight
}

BLOCK_ORDER = ['breakfast', 'lunch', 'afternoon_snack', 'dinner', 'late_night']


def hour_to_block(hour):
    """Map an hour (0-23) to a time block name."""
    if 6 <= hour < 10:
        return 'breakfast'
    elif 10 <= hour < 14:
        return 'lunch'
    elif 14 <= hour < 17:
        return 'afternoon_snack'
    elif 17 <= hour < 21:
        return 'dinner'
    else:
        return 'late_night'


def extract_meals(df):
    """Extract announced meal events with glucose trajectories.

    A meal is defined as a row where carbs > 0. For each meal we capture
    the glucose trajectory over the next 4 hours to compute excursion metrics.
    """
    meals = []

    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        glucose = pdf['glucose'].values
        carbs = pdf['carbs'].values
        bolus = pdf['bolus'].values
        bolus_smb = pdf['bolus_smb'].values
        cob = pdf['cob'].values
        cr_sched = pdf['scheduled_cr'].values
        isf_sched = pdf['scheduled_isf'].values
        times = pdf['time'].values

        carb_idx = np.where(carbs > 0)[0]

        for idx in carb_idx:
            carb_amt = float(carbs[idx])
            if carb_amt < 1:
                continue

            # Need enough forward data for 4h trajectory
            if idx + STEPS_4H >= len(glucose):
                continue

            pre_bg = float(glucose[idx])
            if np.isnan(pre_bg):
                continue

            # Glucose trajectory: next 4 hours
            traj = glucose[idx:idx + STEPS_4H + 1]
            valid_count = np.sum(~np.isnan(traj))
            if valid_count < STEPS_2H:
                continue

            # Peak BG in 4h window
            traj_filled = pd.Series(traj).interpolate(limit=3).values
            peak_bg = float(np.nanmax(traj_filled))
            peak_idx = int(np.nanargmax(traj_filled))
            peak_time_min = peak_idx * 5

            # BG at +2h and +4h
            bg_2h = float(traj_filled[STEPS_2H]) if not np.isnan(traj_filled[STEPS_2H]) else np.nan
            bg_4h = float(traj_filled[STEPS_4H]) if not np.isnan(traj_filled[STEPS_4H]) else np.nan

            # Bolus: sum manual bolus in a ±15 min window around the carb entry
            window_lo = max(0, idx - 3)
            window_hi = min(len(bolus), idx + 4)
            meal_bolus = float(np.sum(bolus[window_lo:window_hi]))
            meal_smb = float(np.sum(bolus_smb[idx:idx + STEPS_2H]))

            # Check for overlapping meals (another carb entry within 2h)
            next_carbs = carbs[idx + 1:idx + STEPS_2H]
            overlapping = bool(np.any(next_carbs > 5))

            # Hour from timestamp
            ts = pd.Timestamp(times[idx])
            hour = ts.hour
            block = hour_to_block(hour)

            # TIR calculations at 2h and 4h windows
            traj_2h = traj_filled[1:STEPS_2H + 1]
            traj_4h = traj_filled[1:STEPS_4H + 1]
            tir_2h = float(np.mean((traj_2h >= 70) & (traj_2h <= 180))) if len(traj_2h) > 0 else np.nan
            tir_4h = float(np.mean((traj_4h >= 70) & (traj_4h <= 180))) if len(traj_4h) > 0 else np.nan

            meals.append({
                'patient_id': pid,
                'time': str(ts),
                'hour': hour,
                'block': block,
                'carbs': carb_amt,
                'bolus': meal_bolus,
                'smb_2h': meal_smb,
                'total_insulin': meal_bolus + meal_smb,
                'pre_bg': pre_bg,
                'peak_bg': peak_bg,
                'peak_time_min': peak_time_min,
                'bg_2h': bg_2h,
                'bg_4h': bg_4h,
                'excursion': peak_bg - pre_bg,
                'delta_2h': bg_2h - pre_bg if not np.isnan(bg_2h) else np.nan,
                'delta_4h': bg_4h - pre_bg if not np.isnan(bg_4h) else np.nan,
                'tir_2h': tir_2h,
                'tir_4h': tir_4h,
                'scheduled_cr': float(cr_sched[idx]),
                'scheduled_isf': float(isf_sched[idx]),
                'overlapping': overlapping,
                'cob_at_entry': float(cob[idx]),
            })

    return pd.DataFrame(meals)


def exp_2536a_meal_extraction(meals):
    """EXP-2536a: Meal extraction and time block distribution."""
    print("=== EXP-2536a: Meal Extraction by Time Block ===\n")

    results = {}

    # Overall stats
    print(f"Total announced meals (carbs > 0): {len(meals)}")
    big = meals[meals['carbs'] >= MIN_CARBS]
    print(f"Meals >= {MIN_CARBS}g carbs: {len(big)}")
    non_overlap = big[~big['overlapping']]
    print(f"Non-overlapping meals >= {MIN_CARBS}g: {len(non_overlap)}")
    with_bolus = non_overlap[non_overlap['bolus'] > 0]
    print(f"  ...with manual bolus: {len(with_bolus)}")

    results['total_meals'] = int(len(meals))
    results['meals_ge_10g'] = int(len(big))
    results['non_overlapping'] = int(len(non_overlap))
    results['with_bolus'] = int(len(with_bolus))

    # Per-block summary
    print(f"\n{'Block':<20} {'N':>5} {'N≥10g':>6} {'MeanCarbs':>10} {'MeanBolus':>10} {'MeanPreBG':>10}")
    print("-" * 65)
    block_stats = {}
    for block in BLOCK_ORDER:
        bm = meals[meals['block'] == block]
        bm_big = bm[bm['carbs'] >= MIN_CARBS]
        row = {
            'n_total': int(len(bm)),
            'n_ge_10g': int(len(bm_big)),
            'mean_carbs': round(float(bm_big['carbs'].mean()), 1) if len(bm_big) else 0,
            'mean_bolus': round(float(bm_big['bolus'].mean()), 2) if len(bm_big) else 0,
            'mean_pre_bg': round(float(bm_big['pre_bg'].mean()), 1) if len(bm_big) else 0,
        }
        block_stats[block] = row
        print(f"{block:<20} {row['n_total']:>5} {row['n_ge_10g']:>6} "
              f"{row['mean_carbs']:>10.1f} {row['mean_bolus']:>10.2f} {row['mean_pre_bg']:>10.1f}")

    results['by_block'] = block_stats
    return results


def exp_2536b_excursion_by_block(meals):
    """EXP-2536b: Post-meal excursion analysis by time block."""
    print("\n=== EXP-2536b: Per-Block Post-Meal Excursion ===\n")

    # Use non-overlapping meals >= MIN_CARBS
    m = meals[(meals['carbs'] >= MIN_CARBS) & (~meals['overlapping'])].copy()
    m['excursion_per_g'] = m['excursion'] / m['carbs']
    m['delta_4h_per_g'] = m['delta_4h'] / m['carbs']

    results = {}

    print(f"{'Block':<20} {'N':>5} {'Exc/g':>8} {'Δ4h/g':>8} {'PeakMin':>8} "
          f"{'TIR2h':>7} {'TIR4h':>7}")
    print("-" * 70)

    block_data = {}
    for block in BLOCK_ORDER:
        bm = m[m['block'] == block]
        if len(bm) < 5:
            print(f"{block:<20} {len(bm):>5}  (too few)")
            continue

        row = {
            'n': int(len(bm)),
            'excursion_per_g_mean': round(float(bm['excursion_per_g'].mean()), 2),
            'excursion_per_g_median': round(float(bm['excursion_per_g'].median()), 2),
            'excursion_per_g_std': round(float(bm['excursion_per_g'].std()), 2),
            'delta_4h_per_g_mean': round(float(bm['delta_4h_per_g'].mean()), 2),
            'delta_4h_per_g_median': round(float(bm['delta_4h_per_g'].median()), 2),
            'peak_time_min_mean': round(float(bm['peak_time_min'].mean()), 1),
            'tir_2h': round(float(bm['tir_2h'].mean()), 3),
            'tir_4h': round(float(bm['tir_4h'].mean()), 3),
            'mean_excursion': round(float(bm['excursion'].mean()), 1),
            'mean_carbs': round(float(bm['carbs'].mean()), 1),
        }
        block_data[block] = row
        print(f"{block:<20} {row['n']:>5} {row['excursion_per_g_mean']:>8.2f} "
              f"{row['delta_4h_per_g_mean']:>8.2f} {row['peak_time_min_mean']:>8.1f} "
              f"{row['tir_2h']:>7.1%} {row['tir_4h']:>7.1%}")

    results['by_block'] = block_data

    # Statistical test: Kruskal-Wallis across blocks
    groups = [m[m['block'] == b]['excursion_per_g'].dropna().values
              for b in BLOCK_ORDER if len(m[m['block'] == b]) >= 5]
    if len(groups) >= 2:
        H, p = stats.kruskal(*groups)
        results['kruskal_wallis'] = {'H': round(float(H), 3), 'p': round(float(p), 6)}
        print(f"\nKruskal-Wallis (excursion/g across blocks): H={H:.3f}, p={p:.4f}")

    # Pairwise: breakfast vs lunch (dawn phenomenon test)
    bfast = m[m['block'] == 'breakfast']['excursion_per_g'].dropna()
    lunch = m[m['block'] == 'lunch']['excursion_per_g'].dropna()
    if len(bfast) >= 5 and len(lunch) >= 5:
        U, p_bl = stats.mannwhitneyu(bfast, lunch, alternative='greater')
        results['breakfast_vs_lunch'] = {
            'U': round(float(U), 1),
            'p_one_sided': round(float(p_bl), 6),
            'breakfast_mean': round(float(bfast.mean()), 2),
            'lunch_mean': round(float(lunch.mean()), 2),
            'effect_size_r': round(float(U / (len(bfast) * len(lunch))), 3),
        }
        print(f"\nBreakfast vs Lunch (one-sided, H₁: breakfast > lunch):")
        print(f"  Breakfast excursion/g: {bfast.mean():.2f} ± {bfast.std():.2f}")
        print(f"  Lunch excursion/g:     {lunch.mean():.2f} ± {lunch.std():.2f}")
        print(f"  Mann-Whitney U={U:.0f}, p={p_bl:.4f}")

    # Breakfast vs dinner
    dinner = m[m['block'] == 'dinner']['excursion_per_g'].dropna()
    if len(bfast) >= 5 and len(dinner) >= 5:
        U_bd, p_bd = stats.mannwhitneyu(bfast, dinner, alternative='two-sided')
        results['breakfast_vs_dinner'] = {
            'U': round(float(U_bd), 1),
            'p_two_sided': round(float(p_bd), 6),
            'breakfast_mean': round(float(bfast.mean()), 2),
            'dinner_mean': round(float(dinner.mean()), 2),
        }
        print(f"\nBreakfast vs Dinner (two-sided):")
        print(f"  Dinner excursion/g:    {dinner.mean():.2f} ± {dinner.std():.2f}")
        print(f"  Mann-Whitney U={U_bd:.0f}, p={p_bd:.4f}")

    return results


def exp_2536c_effective_cr(meals):
    """EXP-2536c: Effective CR by time block."""
    print("\n=== EXP-2536c: Effective CR by Time Block ===\n")

    # Only meals with bolus and >= MIN_CARBS, non-overlapping
    m = meals[
        (meals['carbs'] >= MIN_CARBS)
        & (meals['bolus'] > 0.3)
        & (~meals['overlapping'])
    ].copy()
    m['effective_cr'] = m['carbs'] / m['bolus']
    m['cr_ratio'] = m['effective_cr'] / m['scheduled_cr']  # >1 = under-bolused, <1 = over-bolused

    results = {}

    print(f"Meals with bolus > 0.3U and ≥ {MIN_CARBS}g: {len(m)}")
    print(f"\n{'Block':<20} {'N':>5} {'EffCR':>7} {'SchedCR':>8} {'Ratio':>7} "
          f"{'OverBolus%':>10} {'UnderBolus%':>11}")
    print("-" * 75)

    block_data = {}
    for block in BLOCK_ORDER:
        bm = m[m['block'] == block]
        if len(bm) < 5:
            print(f"{block:<20} {len(bm):>5}  (too few)")
            continue

        over_pct = float((bm['cr_ratio'] < 0.8).mean() * 100)
        under_pct = float((bm['cr_ratio'] > 1.2).mean() * 100)

        row = {
            'n': int(len(bm)),
            'effective_cr_mean': round(float(bm['effective_cr'].mean()), 2),
            'effective_cr_median': round(float(bm['effective_cr'].median()), 2),
            'effective_cr_std': round(float(bm['effective_cr'].std()), 2),
            'scheduled_cr_mean': round(float(bm['scheduled_cr'].mean()), 2),
            'cr_ratio_mean': round(float(bm['cr_ratio'].mean()), 3),
            'cr_ratio_median': round(float(bm['cr_ratio'].median()), 3),
            'pct_over_bolused': round(over_pct, 1),
            'pct_under_bolused': round(under_pct, 1),
        }
        block_data[block] = row
        print(f"{block:<20} {row['n']:>5} {row['effective_cr_mean']:>7.2f} "
              f"{row['scheduled_cr_mean']:>8.2f} {row['cr_ratio_mean']:>7.3f} "
              f"{row['pct_over_bolused']:>10.1f} {row['pct_under_bolused']:>11.1f}")

    results['by_block'] = block_data

    # Does scheduled CR already vary by time block?
    print("\n--- Scheduled CR variation by block ---")
    sched_by_block = {}
    for block in BLOCK_ORDER:
        bm = m[m['block'] == block]
        if len(bm) < 5:
            continue
        sched_by_block[block] = {
            'mean': round(float(bm['scheduled_cr'].mean()), 2),
            'std': round(float(bm['scheduled_cr'].std()), 2),
            'min': round(float(bm['scheduled_cr'].min()), 2),
            'max': round(float(bm['scheduled_cr'].max()), 2),
        }
        print(f"  {block:<20}: CR = {sched_by_block[block]['mean']:.2f} "
              f"± {sched_by_block[block]['std']:.2f} "
              f"(range {sched_by_block[block]['min']:.1f}-{sched_by_block[block]['max']:.1f})")
    results['scheduled_cr_by_block'] = sched_by_block

    # Kruskal-Wallis on effective CR
    groups = [m[m['block'] == b]['effective_cr'].dropna().values
              for b in BLOCK_ORDER if len(m[m['block'] == b]) >= 5]
    if len(groups) >= 2:
        H, p = stats.kruskal(*groups)
        results['kruskal_wallis_effective_cr'] = {'H': round(float(H), 3), 'p': round(float(p), 6)}
        print(f"\nKruskal-Wallis (effective CR across blocks): H={H:.3f}, p={p:.4f}")

    # BG outcome by block: was the meal well-covered?
    print("\n--- BG outcome by block (delta_4h) ---")
    print(f"{'Block':<20} {'MeanΔ4h':>8} {'MedianΔ4h':>10} {'%InRange4h':>11}")
    print("-" * 55)
    outcome_data = {}
    for block in BLOCK_ORDER:
        bm = m[m['block'] == block]
        if len(bm) < 5:
            continue
        d4h = bm['delta_4h'].dropna()
        outcome_data[block] = {
            'mean_delta_4h': round(float(d4h.mean()), 1),
            'median_delta_4h': round(float(d4h.median()), 1),
            'tir_4h': round(float(bm['tir_4h'].mean()), 3),
        }
        print(f"{block:<20} {outcome_data[block]['mean_delta_4h']:>8.1f} "
              f"{outcome_data[block]['median_delta_4h']:>10.1f} "
              f"{outcome_data[block]['tir_4h']:>11.1%}")
    results['bg_outcome_by_block'] = outcome_data

    return results


def exp_2536d_cr_isf_correlation(meals, df):
    """EXP-2536d: CR vs ISF circadian correlation."""
    print("\n=== EXP-2536d: CR vs ISF Circadian Correlation ===\n")

    results = {}

    # 1. Scheduled profile correlation: does scheduled CR track scheduled ISF by hour?
    m = meals[(meals['carbs'] >= MIN_CARBS) & (~meals['overlapping'])].copy()
    m['hour_f'] = m['hour'].astype(float)

    # Hourly means of scheduled values
    hourly = m.groupby('hour').agg(
        cr_mean=('scheduled_cr', 'mean'),
        isf_mean=('scheduled_isf', 'mean'),
        n=('scheduled_cr', 'count'),
    ).reset_index()

    if len(hourly) >= 4:
        r_sched, p_sched = stats.spearmanr(hourly['cr_mean'], hourly['isf_mean'])
        results['scheduled_profile_correlation'] = {
            'spearman_r': round(float(r_sched), 4),
            'p': round(float(p_sched), 6),
            'interpretation': 'CR and ISF profiles are correlated' if p_sched < 0.05
                              else 'CR and ISF profiles are NOT significantly correlated',
        }
        print(f"Scheduled CR vs ISF by hour: r={r_sched:.4f}, p={p_sched:.4f}")
        print(f"  → {results['scheduled_profile_correlation']['interpretation']}")

    # 2. Effective insulin sensitivity: excursion per g per unit insulin
    bolused = m[m['bolus'] > 0.3].copy()
    bolused['excursion_per_g_per_u'] = bolused['excursion'] / (bolused['carbs'] * bolused['total_insulin'])

    print(f"\n--- Circadian pattern: excursion per gram per unit insulin ---")
    print(f"{'Block':<20} {'N':>5} {'Exc/g/U':>10} {'SchedISF':>9} {'SchedCR':>8}")
    print("-" * 55)
    circadian_data = {}
    for block in BLOCK_ORDER:
        bm = bolused[bolused['block'] == block]
        if len(bm) < 5:
            continue
        egpu = bm['excursion_per_g_per_u'].replace([np.inf, -np.inf], np.nan).dropna()
        circadian_data[block] = {
            'n': int(len(bm)),
            'excursion_per_g_per_u': round(float(egpu.mean()), 4),
            'scheduled_isf': round(float(bm['scheduled_isf'].mean()), 1),
            'scheduled_cr': round(float(bm['scheduled_cr'].mean()), 1),
        }
        print(f"{block:<20} {circadian_data[block]['n']:>5} "
              f"{circadian_data[block]['excursion_per_g_per_u']:>10.4f} "
              f"{circadian_data[block]['scheduled_isf']:>9.1f} "
              f"{circadian_data[block]['scheduled_cr']:>8.1f}")
    results['circadian_sensitivity'] = circadian_data

    # 3. Compute effective CR and effective ISF per hour from the full dataset
    # ISF: use correction-like events (bolus > 0, low COB, high BG)
    corr = df[
        (df['bolus'] > 0.3)
        & (df['cob'] < 3)
        & (df['glucose'] > 150)
    ].copy()
    corr['hour'] = corr['time'].dt.hour

    hourly_isf = []
    for pid in corr['patient_id'].unique():
        pdf = df[df['patient_id'] == pid].sort_values('time').reset_index(drop=True)
        glucose = pdf['glucose'].values
        bolus_arr = pdf['bolus'].values
        cob_arr = pdf['cob'].values
        times_arr = pdf['time'].values

        corr_idx = np.where((bolus_arr > 0.3) & (cob_arr < 3) & (glucose > 150))[0]
        for idx in corr_idx:
            if idx + STEPS_2H >= len(glucose) or idx < 1:
                continue
            bg_start = glucose[idx]
            bg_end = glucose[idx + STEPS_2H]
            if np.isnan(bg_start) or np.isnan(bg_end):
                continue
            # No other bolus in window
            if np.any(bolus_arr[idx + 1:idx + STEPS_2H] > 0.3):
                continue
            drop = bg_start - bg_end
            dose = bolus_arr[idx]
            if dose > 0 and drop > 0:
                hourly_isf.append({
                    'hour': int(pd.Timestamp(times_arr[idx]).hour),
                    'effective_isf': float(drop / dose),
                })

    if hourly_isf:
        isf_df = pd.DataFrame(hourly_isf)
        isf_hourly = isf_df.groupby('hour')['effective_isf'].mean()

        # Effective CR by hour
        bolused_h = bolused.copy()
        bolused_h['effective_cr'] = bolused_h['carbs'] / bolused_h['bolus']
        cr_hourly = bolused_h.groupby('hour')['effective_cr'].mean()

        # Merge and correlate
        merged = pd.DataFrame({
            'cr': cr_hourly,
            'isf': isf_hourly,
        }).dropna()

        if len(merged) >= 4:
            r_eff, p_eff = stats.spearmanr(merged['cr'], merged['isf'])
            results['effective_cr_isf_correlation'] = {
                'spearman_r': round(float(r_eff), 4),
                'p': round(float(p_eff), 6),
                'n_hours': int(len(merged)),
                'interpretation': (
                    'Effective CR and ISF are correlated → single insulin resistance factor may suffice'
                    if r_eff > 0.4 and p_eff < 0.05
                    else 'Effective CR and ISF show weak/no correlation → they vary independently'
                ),
            }
            print(f"\nEffective CR vs ISF by hour: r={r_eff:.4f}, p={p_eff:.4f}, n={len(merged)} hours")
            print(f"  → {results['effective_cr_isf_correlation']['interpretation']}")

            # Report the hourly values
            hourly_detail = {}
            for h in sorted(merged.index):
                hourly_detail[int(h)] = {
                    'effective_cr': round(float(merged.loc[h, 'cr']), 2),
                    'effective_isf': round(float(merged.loc[h, 'isf']), 1),
                }
            results['hourly_cr_isf'] = hourly_detail
    else:
        print("  No correction events found for ISF estimation.")

    return results


def exp_2536e_per_patient(meals):
    """EXP-2536e: Per-patient circadian CR patterns."""
    print("\n=== EXP-2536e: Per-Patient Circadian CR Patterns ===\n")

    m = meals[
        (meals['carbs'] >= MIN_CARBS)
        & (meals['bolus'] > 0.3)
        & (~meals['overlapping'])
    ].copy()
    m['effective_cr'] = m['carbs'] / m['bolus']

    results = {}
    patient_profiles = {}

    # Minimum meals per block to include a patient-block
    MIN_PER_BLOCK = 5

    print(f"{'Patient':<10} ", end='')
    for b in BLOCK_ORDER:
        print(f"{'CR_' + b[:4]:>10} ", end='')
    print(f"{'Range':>7} {'Ratio':>7} {'Pattern':>10}")
    print("-" * 85)

    patient_summaries = {}
    for pid in sorted(m['patient_id'].unique()):
        pm = m[m['patient_id'] == pid]

        profile = {}
        cr_values = []
        for block in BLOCK_ORDER:
            bm = pm[pm['block'] == block]
            if len(bm) >= MIN_PER_BLOCK:
                cr = float(bm['effective_cr'].median())
                profile[block] = {
                    'effective_cr_median': round(cr, 2),
                    'effective_cr_mean': round(float(bm['effective_cr'].mean()), 2),
                    'n': int(len(bm)),
                }
                cr_values.append(cr)
            else:
                profile[block] = None

        if len(cr_values) < 2:
            continue

        cr_range = max(cr_values) - min(cr_values)
        cr_ratio = max(cr_values) / min(cr_values) if min(cr_values) > 0 else float('inf')

        # Determine pattern: is breakfast the tightest CR?
        bfast_cr = profile.get('breakfast', {})
        if isinstance(bfast_cr, dict) and bfast_cr is not None:
            bfast_val = bfast_cr.get('effective_cr_median', None)
        else:
            bfast_val = None

        if bfast_val is not None and bfast_val == min(cr_values):
            pattern = 'dawn↓'
        elif bfast_val is not None and bfast_val == max(cr_values):
            pattern = 'dawn↑'
        else:
            pattern = 'mixed'

        patient_summaries[pid] = {
            'profile': profile,
            'cr_range': round(cr_range, 2),
            'cr_ratio': round(cr_ratio, 2),
            'pattern': pattern,
            'blocks_with_data': len(cr_values),
        }
        patient_profiles[pid] = profile

        # Print row
        print(f"{pid:<10} ", end='')
        for b in BLOCK_ORDER:
            if profile[b] is not None:
                print(f"{profile[b]['effective_cr_median']:>10.1f} ", end='')
            else:
                print(f"{'--':>10} ", end='')
        print(f"{cr_range:>7.1f} {cr_ratio:>7.2f} {pattern:>10}")

    results['patient_profiles'] = patient_summaries

    # Consistency analysis
    if patient_summaries:
        patterns = [v['pattern'] for v in patient_summaries.values()]
        ratios = [v['cr_ratio'] for v in patient_summaries.values()]
        results['consistency'] = {
            'n_patients': len(patient_summaries),
            'pattern_counts': {p: patterns.count(p) for p in set(patterns)},
            'mean_cr_ratio': round(float(np.mean(ratios)), 2),
            'median_cr_ratio': round(float(np.median(ratios)), 2),
            'cr_ratio_range': [round(float(min(ratios)), 2), round(float(max(ratios)), 2)],
        }

        print(f"\n--- Consistency Summary ---")
        print(f"Patients with enough data: {len(patient_summaries)}")
        print(f"Pattern distribution: {results['consistency']['pattern_counts']}")
        print(f"CR ratio (max/min block): mean={np.mean(ratios):.2f}, "
              f"median={np.median(ratios):.2f}, range={min(ratios):.2f}-{max(ratios):.2f}")

        # Population-level: is the breakfast CR consistently lower?
        bfast_ranks = []
        for pid, prof in patient_profiles.items():
            vals = [(b, prof[b]['effective_cr_median'])
                    for b in BLOCK_ORDER if prof[b] is not None]
            if len(vals) < 2:
                continue
            sorted_vals = sorted(vals, key=lambda x: x[1])
            rank = [b for b, _ in sorted_vals].index('breakfast') + 1 if any(b == 'breakfast' for b, _ in sorted_vals) else None
            if rank is not None:
                bfast_ranks.append(rank)

        if bfast_ranks:
            mean_rank = np.mean(bfast_ranks)
            n_blocks_avg = np.mean([v['blocks_with_data'] for v in patient_summaries.values()])
            expected_rank = (n_blocks_avg + 1) / 2
            results['breakfast_rank'] = {
                'mean_rank': round(float(mean_rank), 2),
                'expected_rank': round(float(expected_rank), 2),
                'n_patients': len(bfast_ranks),
                'interpretation': (
                    'Breakfast CR tends to be lower (tighter) than other blocks → dawn phenomenon'
                    if mean_rank < expected_rank - 0.3
                    else 'Breakfast CR rank is near expected → no clear dawn CR effect'
                ),
            }
            print(f"\nBreakfast CR rank: mean={mean_rank:.2f} "
                  f"(expected under null: {expected_rank:.2f})")
            print(f"  → {results['breakfast_rank']['interpretation']}")

    return results


def run_experiment():
    """Run all EXP-2536 sub-experiments."""
    print("=" * 70)
    print("EXP-2536: Circadian CR Variation")
    print("=" * 70)

    print("\nLoading data...")
    df = pd.read_parquet(PARQUET)
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    print("\nExtracting meal events...")
    meals = extract_meals(df)
    print(f"Found {len(meals)} announced meals from {meals['patient_id'].nunique()} patients")
    print(f"  Meals ≥ {MIN_CARBS}g: {(meals['carbs'] >= MIN_CARBS).sum()}")
    print(f"  With bolus > 0: {(meals['bolus'] > 0).sum()}")
    print(f"  Non-overlapping: {(~meals['overlapping']).sum()}")

    results = {
        'experiment': 'EXP-2536',
        'title': 'Circadian CR Variation',
        'description': (
            'Tests whether carb ratio effectiveness varies by time of day. '
            'Examines dawn phenomenon effects on meal coverage, effective CR '
            'per time block, and CR-ISF circadian correlation.'
        ),
        'n_meals': int(len(meals)),
        'n_patients': int(meals['patient_id'].nunique()),
        'min_carbs_threshold': MIN_CARBS,
    }

    print()
    results['exp_2536a'] = exp_2536a_meal_extraction(meals)
    results['exp_2536b'] = exp_2536b_excursion_by_block(meals)
    results['exp_2536c'] = exp_2536c_effective_cr(meals)
    results['exp_2536d'] = exp_2536d_cr_isf_correlation(meals, df)
    results['exp_2536e'] = exp_2536e_per_patient(meals)

    # Overall conclusions
    conclusions = []

    # From 2536b: excursion pattern
    if 'kruskal_wallis' in results['exp_2536b']:
        kw = results['exp_2536b']['kruskal_wallis']
        if kw['p'] < 0.05:
            conclusions.append(
                f"BG excursion per gram varies significantly by time block "
                f"(Kruskal-Wallis H={kw['H']:.1f}, p={kw['p']:.4f})"
            )
        else:
            conclusions.append(
                f"No significant variation in BG excursion per gram across time blocks "
                f"(p={kw['p']:.4f})"
            )

    # From 2536b: breakfast vs lunch
    if 'breakfast_vs_lunch' in results['exp_2536b']:
        bvl = results['exp_2536b']['breakfast_vs_lunch']
        if bvl['p_one_sided'] < 0.05:
            conclusions.append(
                f"Breakfast shows significantly larger excursion/g than lunch "
                f"({bvl['breakfast_mean']:.2f} vs {bvl['lunch_mean']:.2f}, "
                f"p={bvl['p_one_sided']:.4f}) → dawn phenomenon affects CR"
            )
        else:
            conclusions.append(
                f"No significant difference in excursion/g between breakfast and lunch "
                f"(p={bvl['p_one_sided']:.4f})"
            )

    # From 2536c: effective CR variation
    if 'kruskal_wallis_effective_cr' in results['exp_2536c']:
        kw = results['exp_2536c']['kruskal_wallis_effective_cr']
        if kw['p'] < 0.05:
            conclusions.append(
                f"Effective CR varies significantly by time block "
                f"(H={kw['H']:.1f}, p={kw['p']:.4f})"
            )

    # From 2536d: CR-ISF correlation
    if 'effective_cr_isf_correlation' in results['exp_2536d']:
        corr = results['exp_2536d']['effective_cr_isf_correlation']
        conclusions.append(corr['interpretation'])

    # From 2536e: consistency
    if 'consistency' in results['exp_2536e']:
        cons = results['exp_2536e']['consistency']
        conclusions.append(
            f"Per-patient CR circadian ratio (max/min): "
            f"mean={cons['mean_cr_ratio']:.2f}×, "
            f"median={cons['median_cr_ratio']:.2f}×"
        )

    results['conclusions'] = conclusions

    print("\n" + "=" * 70)
    print("CONCLUSIONS")
    print("=" * 70)
    for c in conclusions:
        print(f"  • {c}")

    # Save
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

    return results


if __name__ == '__main__':
    run_experiment()
