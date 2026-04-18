"""EXP-2540: Loop Aggression Tuning Analysis.

Investigates the paradox found in EXP-2538:
  - Too timid for highs: 65.9% of >250 excursions under-treated
  - Too aggressive for lows: loop-caused hypos from late reduction
  - Loop suspends 50% of the time overall

Analyzes how loop aggression maps to glucose level, identifies
optimal aggression curves, and tests simple threshold rules.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

PARQUET = 'externals/ns-parquet/training/grid.parquet'
OUTPUT = 'externals/experiments/exp-2540_loop_aggression.json'

STEPS_1H = 12
STEPS_2H = 24
STEPS_3H = 36
STEPS_4H = 48
STEPS_30M = 6

HYPO_THRESHOLD = 70
TARGET_LOW = 70
TARGET_HIGH = 180
GLUCOSE_BINS = list(range(50, 350, 10))


def load_data():
    df = pd.read_parquet(PARQUET)
    df = df.sort_values(['patient_id', 'time']).reset_index(drop=True)
    return df


def compute_aggression(df):
    """Compute per-row aggression score.

    Aggression captures how hard insulin is pushing glucose down:
      - net_basal above scheduled = delivering extra insulin
      - bolus_smb > 0 = super micro bolus active
      - loop_enacted_bolus > 0 = loop-initiated bolus

    Score: normalised excess insulin delivery relative to basal.
    """
    basal_excess = (df['actual_basal_rate'].fillna(0)
                    - df['scheduled_basal_rate'].fillna(0))
    smb = df['bolus_smb'].fillna(0)
    enacted_bolus = df['loop_enacted_bolus'].fillna(0)

    # Convert per-interval: basal excess is U/hr, scale to per-5min
    basal_excess_5m = basal_excess / 12.0

    # Aggression = total extra insulin delivered per 5 min
    df = df.copy()
    df['aggression'] = basal_excess_5m + smb + enacted_bolus
    df['aggression_basal'] = basal_excess_5m
    df['aggression_smb'] = smb
    df['aggression_bolus'] = enacted_bolus

    # Suspension indicator
    df['is_suspended'] = (df['actual_basal_rate'].fillna(0) == 0).astype(int)

    return df


def glucose_bin(glucose, bin_size=10):
    return int(np.floor(glucose / bin_size) * bin_size)


def future_glucose(df, steps):
    """Get glucose N steps ahead within same patient."""
    return df.groupby('patient_id')['glucose'].shift(-steps)


def future_min_glucose(df, steps):
    """Get minimum glucose in next N steps within same patient."""
    result = pd.Series(np.nan, index=df.index)
    for pid, grp in df.groupby('patient_id'):
        g = grp['glucose'].values
        mins = np.full(len(g), np.nan)
        for i in range(len(g) - 1):
            end = min(i + steps + 1, len(g))
            window = g[i+1:end]
            valid = window[~np.isnan(window)]
            if len(valid) > 0:
                mins[i] = np.nanmin(valid)
        result.loc[grp.index] = mins
    return result


def exp_2540a_aggression_vs_glucose(df):
    """How does loop aggression map to current glucose level?

    Expectation: aggression should be proportional to glucose-above-target.
    Reality (EXP-2538): loop is too timid at high glucose, too aggressive near target.
    """
    print("\n=== EXP-2540a: Aggression vs Glucose Level ===")
    valid = df[df['glucose'].notna()].copy()
    valid['glucose_bin'] = valid['glucose'].apply(lambda x: glucose_bin(x, 10))

    bins = valid.groupby('glucose_bin').agg(
        n=('aggression', 'size'),
        mean_aggression=('aggression', 'mean'),
        median_aggression=('aggression', 'median'),
        p25_aggression=('aggression', lambda x: np.percentile(x, 25)),
        p75_aggression=('aggression', lambda x: np.percentile(x, 75)),
        smb_rate=('aggression_smb', lambda x: (x > 0).mean()),
        mean_smb_dose=('aggression_smb', lambda x: x[x > 0].mean() if (x > 0).any() else 0),
        suspend_rate=('is_suspended', 'mean'),
        mean_iob=('iob', 'mean'),
    ).reset_index()

    bins = bins[bins['n'] >= 100]

    # Key metrics
    high_bins = bins[bins['glucose_bin'] >= 200]
    target_bins = bins[(bins['glucose_bin'] >= 80) & (bins['glucose_bin'] <= 150)]
    low_bins = bins[bins['glucose_bin'] <= 80]

    # Is aggression proportional?
    from scipy import stats
    corr_data = bins[bins['glucose_bin'] >= 100]
    if len(corr_data) >= 5:
        slope, intercept, r, p, se = stats.linregress(
            corr_data['glucose_bin'], corr_data['mean_aggression'])
        linearity = {'slope': float(slope), 'intercept': float(intercept),
                     'r_squared': float(r**2), 'p_value': float(p)}
    else:
        linearity = {'error': 'insufficient data'}

    # Ideal vs actual: aggression should be ~0 at target, positive above, negative below
    target_mid = 110  # typical target
    ideal_slope = 0.01  # hypothetical: 0.01 U/5min per mg/dL above target

    result = {
        'aggression_by_glucose_bin': bins.to_dict('records'),
        'linearity_above_100': linearity,
        'summary': {
            'high_glucose_200plus': {
                'mean_aggression': float(high_bins['mean_aggression'].mean()) if len(high_bins) else None,
                'smb_rate': float(high_bins['smb_rate'].mean()) if len(high_bins) else None,
                'suspend_rate': float(high_bins['suspend_rate'].mean()) if len(high_bins) else None,
            },
            'in_target_80_150': {
                'mean_aggression': float(target_bins['mean_aggression'].mean()) if len(target_bins) else None,
                'smb_rate': float(target_bins['smb_rate'].mean()) if len(target_bins) else None,
                'suspend_rate': float(target_bins['suspend_rate'].mean()) if len(target_bins) else None,
            },
            'low_glucose_sub80': {
                'mean_aggression': float(low_bins['mean_aggression'].mean()) if len(low_bins) else None,
                'smb_rate': float(low_bins['smb_rate'].mean()) if len(low_bins) else None,
                'suspend_rate': float(low_bins['suspend_rate'].mean()) if len(low_bins) else None,
            },
        },
        'paradox_evidence': {},
    }

    # Quantify the paradox — ratio of aggression to glucose distance from target
    # A well-calibrated loop should show much higher aggression at 200+ than at 80-150
    if len(high_bins) and len(target_bins):
        high_mean = float(high_bins['mean_aggression'].mean())
        target_mean = float(target_bins['mean_aggression'].mean())
        aggression_ratio = high_mean / max(target_mean, 0.001)

        # Also check the slope: aggression per mg/dL above target
        # glucose 200+ is ~100 mg/dL above target mid (110), target range ~0-40 above
        # So aggression should be proportional to distance
        glucose_dist_high = 200 - 110  # ~90 mg/dL above target
        glucose_dist_target = 115 - 110  # ~5 mg/dL above target
        expected_ratio = glucose_dist_high / max(glucose_dist_target, 1)  # ~18x

        result['paradox_evidence']['high_vs_target_aggression_ratio'] = aggression_ratio
        result['paradox_evidence']['expected_proportional_ratio'] = float(expected_ratio)
        result['paradox_evidence']['high_mean_aggression'] = high_mean
        result['paradox_evidence']['target_mean_aggression'] = target_mean
        result['paradox_evidence']['smb_rate_at_200plus'] = float(high_bins['smb_rate'].mean())
        result['paradox_evidence']['suspend_rate_at_200plus'] = float(high_bins['suspend_rate'].mean())

        # The paradox: aggression ratio is far below what proportional response requires
        # AND the loop still suspends 40%+ of the time even at glucose>200
        paradox_confirmed = (aggression_ratio < expected_ratio * 0.5
                             or float(high_bins['suspend_rate'].mean()) > 0.20)
        result['paradox_evidence']['interpretation'] = (
            f"PARADOX CONFIRMED: aggression ratio {aggression_ratio:.1f}x vs "
            f"expected {expected_ratio:.0f}x proportional; "
            f"suspend rate {float(high_bins['suspend_rate'].mean()):.1%} even at glucose>200"
            if paradox_confirmed
            else f"Aggression scales reasonably: {aggression_ratio:.1f}x ratio")

    for k, v in result['summary'].items():
        print(f"  {k}: aggression={v.get('mean_aggression', 'N/A'):.4f}, "
              f"smb_rate={v.get('smb_rate', 'N/A'):.3f}, "
              f"suspend={v.get('suspend_rate', 'N/A'):.3f}")
    if 'interpretation' in result.get('paradox_evidence', {}):
        print(f"  → {result['paradox_evidence']['interpretation']}")

    return result


def exp_2540b_optimal_aggression(df):
    """For each glucose bin, what aggression minimises hypo risk + time-above-range?

    Uses observational data: within each glucose bin, compare outcomes
    when aggression was high vs low (natural variation).
    """
    print("\n=== EXP-2540b: Optimal Aggression Curve ===")
    valid = df[df['glucose'].notna()].copy()
    valid['glucose_bin'] = valid['glucose'].apply(lambda x: glucose_bin(x, 10))
    valid['glucose_2h'] = future_glucose(df, STEPS_2H).reindex(valid.index)
    valid['glucose_4h'] = future_glucose(df, STEPS_4H).reindex(valid.index)

    # Pre-compute future min glucose (expensive but necessary)
    print("  Computing future min glucose (4h window)...")
    valid['min_glucose_4h'] = future_min_glucose(df, STEPS_4H).reindex(valid.index)

    valid['hypo_4h'] = (valid['min_glucose_4h'] < HYPO_THRESHOLD).astype(int)
    valid['in_range_2h'] = ((valid['glucose_2h'] >= TARGET_LOW) &
                            (valid['glucose_2h'] <= TARGET_HIGH)).astype(int)

    bins_result = []
    for gbin in range(60, 310, 10):
        chunk = valid[valid['glucose_bin'] == gbin]
        if len(chunk) < 200:
            continue

        # Split into aggression tertiles
        tertiles = chunk['aggression'].quantile([0.33, 0.67])
        low_agg = chunk[chunk['aggression'] <= tertiles.iloc[0]]
        mid_agg = chunk[(chunk['aggression'] > tertiles.iloc[0]) &
                        (chunk['aggression'] <= tertiles.iloc[1])]
        high_agg = chunk[chunk['aggression'] > tertiles.iloc[1]]

        entry = {
            'glucose_bin': gbin,
            'n': int(len(chunk)),
            'mean_aggression': float(chunk['aggression'].mean()),
            'mean_glucose_2h': float(chunk['glucose_2h'].mean()) if chunk['glucose_2h'].notna().any() else None,
            'hypo_rate_4h': float(chunk['hypo_4h'].mean()) if chunk['hypo_4h'].notna().any() else None,
            'in_range_2h_pct': float(chunk['in_range_2h'].mean() * 100) if chunk['in_range_2h'].notna().any() else None,
        }

        for label, subset in [('low_agg', low_agg), ('mid_agg', mid_agg), ('high_agg', high_agg)]:
            if len(subset) < 30:
                continue
            entry[f'{label}_n'] = int(len(subset))
            entry[f'{label}_mean_aggression'] = float(subset['aggression'].mean())
            entry[f'{label}_glucose_2h'] = float(subset['glucose_2h'].mean()) if subset['glucose_2h'].notna().any() else None
            entry[f'{label}_hypo_rate_4h'] = float(subset['hypo_4h'].mean()) if subset['hypo_4h'].notna().any() else None
            entry[f'{label}_in_range_2h_pct'] = float(subset['in_range_2h'].mean() * 100) if subset['in_range_2h'].notna().any() else None

        bins_result.append(entry)

    # Find the sweet spot for each bin — use context-appropriate scoring
    # At low glucose, penalise hypo heavily; at high glucose, penalise time-above-range
    optimal_aggression = []
    for entry in bins_result:
        gbin = entry['glucose_bin']
        best_label = None
        best_score = float('inf')

        # Adaptive weights: hypo penalty decreases with glucose level,
        # hyperglycemia penalty increases
        if gbin < 100:
            hypo_weight = 5.0
            hyper_weight = 0.5
        elif gbin < 150:
            hypo_weight = 3.0
            hyper_weight = 1.0
        elif gbin < 200:
            hypo_weight = 1.5
            hyper_weight = 2.0
        else:
            hypo_weight = 1.0
            hyper_weight = 3.0

        for label in ['low_agg', 'mid_agg', 'high_agg']:
            hypo = entry.get(f'{label}_hypo_rate_4h')
            ir = entry.get(f'{label}_in_range_2h_pct')
            g2h = entry.get(f'{label}_glucose_2h')
            if hypo is not None and ir is not None:
                # Penalise hypo risk and time-out-of-range with adaptive weights
                score = hypo * hypo_weight + (1.0 - ir / 100.0) * hyper_weight
                if score < best_score:
                    best_score = score
                    best_label = label
        if best_label:
            optimal_aggression.append({
                'glucose_bin': entry['glucose_bin'],
                'optimal_tertile': best_label,
                'optimal_aggression': entry.get(f'{best_label}_mean_aggression'),
                'hypo_rate': entry.get(f'{best_label}_hypo_rate_4h'),
                'in_range_pct': entry.get(f'{best_label}_in_range_2h_pct'),
            })

    # Summary: where is high aggression optimal, where is low?
    high_opt = [o for o in optimal_aggression if o['optimal_tertile'] == 'high_agg']
    low_opt = [o for o in optimal_aggression if o['optimal_tertile'] == 'low_agg']
    mid_opt = [o for o in optimal_aggression if o['optimal_tertile'] == 'mid_agg']

    print(f"  Bins where HIGH aggression is optimal: "
          f"{[o['glucose_bin'] for o in high_opt]}")
    print(f"  Bins where LOW aggression is optimal: "
          f"{[o['glucose_bin'] for o in low_opt]}")

    # Compute what the data actually shows about aggression effectiveness
    # at high glucose vs low glucose
    above_200 = [e for e in bins_result if e['glucose_bin'] >= 200]
    below_130 = [e for e in bins_result if e['glucose_bin'] <= 130 and e['glucose_bin'] >= 70]

    effectiveness = {}
    for label, subset in [('above_200', above_200), ('below_130', below_130)]:
        if not subset:
            continue
        hi_hypo = [e.get('high_agg_hypo_rate_4h', 0) for e in subset if e.get('high_agg_hypo_rate_4h') is not None]
        lo_hypo = [e.get('low_agg_hypo_rate_4h', 0) for e in subset if e.get('low_agg_hypo_rate_4h') is not None]
        hi_ir = [e.get('high_agg_in_range_2h_pct', 0) for e in subset if e.get('high_agg_in_range_2h_pct') is not None]
        lo_ir = [e.get('low_agg_in_range_2h_pct', 0) for e in subset if e.get('low_agg_in_range_2h_pct') is not None]
        effectiveness[label] = {
            'high_agg_mean_hypo': float(np.mean(hi_hypo)) if hi_hypo else None,
            'low_agg_mean_hypo': float(np.mean(lo_hypo)) if lo_hypo else None,
            'high_agg_mean_in_range': float(np.mean(hi_ir)) if hi_ir else None,
            'low_agg_mean_in_range': float(np.mean(lo_ir)) if lo_ir else None,
        }

    # Determine if the transition point (where low → high becomes optimal) exists
    transition = None
    for o in sorted(optimal_aggression, key=lambda x: x['glucose_bin']):
        if o['optimal_tertile'] in ('low_agg',) and o['glucose_bin'] >= 150:
            if transition is None:
                transition = o['glucose_bin']

    result = {
        'bins': bins_result,
        'optimal_aggression_curve': optimal_aggression,
        'effectiveness_by_range': effectiveness,
        'summary': {
            'high_aggression_optimal_bins': [o['glucose_bin'] for o in high_opt],
            'low_aggression_optimal_bins': [o['glucose_bin'] for o in low_opt],
            'mid_aggression_optimal_bins': [o['glucose_bin'] for o in mid_opt],
            'transition_to_low_agg': transition,
            'caveat': ('Selection bias likely: high aggression at low glucose correlates '
                       'with recently-high-now-falling trajectories; low aggression at '
                       'high glucose may reflect already-treated or meal-related scenarios'),
            'interpretation': (
                f"High aggression optimal at glucose<{transition or 170}, "
                f"low/mid optimal above — BUT confounded by glucose trajectory"
            ),
        },
    }
    return result


def exp_2540c_overcorrection(df):
    """Analyze loop-caused hypos: what was glucose when aggressive dosing started?

    Identifies episodes where the loop was aggressive and hypo followed,
    then characterizes the aggression trajectory.
    """
    print("\n=== EXP-2540c: Over-Correction Patterns ===")
    valid = df[df['glucose'].notna()].copy()
    roc = valid['glucose_roc'].fillna(0)

    events = []
    for pid, grp in valid.groupby('patient_id'):
        g = grp['glucose'].values
        agg = grp['aggression'].values
        roc_vals = grp['glucose_roc'].fillna(0).values
        iob_vals = grp['iob'].fillna(0).values
        smb_vals = grp['aggression_smb'].values
        idx_list = grp.index.values
        times = grp['time'].values

        n = len(g)
        i = 0
        while i < n - STEPS_4H:
            # Find hypo events
            if g[i] < HYPO_THRESHOLD and not np.isnan(g[i]):
                # Look back up to 4h for aggressive dosing
                lookback = max(0, i - STEPS_4H)
                window_agg = agg[lookback:i]
                window_g = g[lookback:i]
                window_roc = roc_vals[lookback:i]

                # Was there meaningful aggression before this hypo?
                aggressive_mask = window_agg > 0.05  # >0.05 U/5min extra
                if aggressive_mask.sum() < 3:
                    i += 1
                    continue

                # Find when aggressive dosing started
                agg_indices = np.where(aggressive_mask)[0]
                first_agg = agg_indices[0]
                abs_first_agg = lookback + first_agg

                # Glucose when aggression started
                start_glucose = g[abs_first_agg] if not np.isnan(g[abs_first_agg]) else None

                # Was glucose already falling when aggression continued?
                # Find last aggressive action
                last_agg = agg_indices[-1]
                abs_last_agg = lookback + last_agg
                last_agg_glucose = g[abs_last_agg] if not np.isnan(g[abs_last_agg]) else None

                # Rate of fall during aggressive period
                agg_period_roc = window_roc[first_agg:last_agg+1]
                mean_fall_rate = float(np.mean(agg_period_roc)) if len(agg_period_roc) else 0

                # When did loop finally reduce?
                # Look for first non-aggressive step after aggression
                reduce_idx = None
                reduce_glucose = None
                for j in range(abs_last_agg + 1, i):
                    if agg[j] <= 0:
                        reduce_idx = j
                        reduce_glucose = g[j] if not np.isnan(g[j]) else None
                        break

                events.append({
                    'patient_id': pid,
                    'hypo_glucose': float(g[i]),
                    'start_glucose': float(start_glucose) if start_glucose else None,
                    'last_agg_glucose': float(last_agg_glucose) if last_agg_glucose else None,
                    'reduce_glucose': float(reduce_glucose) if reduce_glucose else None,
                    'mean_fall_rate': float(mean_fall_rate),
                    'aggression_duration_min': int((last_agg - first_agg + 1) * 5),
                    'total_extra_insulin': float(np.sum(window_agg[aggressive_mask])),
                    'max_aggression': float(np.max(window_agg)),
                    'iob_at_start': float(iob_vals[abs_first_agg]),
                    'iob_at_hypo': float(iob_vals[i]),
                    'smbs_during': int(np.sum(smb_vals[lookback:i] > 0)),
                    'lead_time_min': int((i - abs_first_agg) * 5),
                })

                i += STEPS_1H  # skip ahead to avoid counting same event
            else:
                i += 1

    events_df = pd.DataFrame(events) if events else pd.DataFrame()

    if len(events_df) == 0:
        print("  No over-correction events found")
        return {'events': [], 'summary': {'n_events': 0}}

    print(f"  Found {len(events_df)} over-correction hypo events")

    # Characterise
    summary = {
        'n_events': int(len(events_df)),
        'start_glucose': {
            'mean': float(events_df['start_glucose'].mean()),
            'median': float(events_df['start_glucose'].median()),
            'p25': float(events_df['start_glucose'].quantile(0.25)),
            'p75': float(events_df['start_glucose'].quantile(0.75)),
        },
        'last_agg_glucose': {
            'mean': float(events_df['last_agg_glucose'].dropna().mean()),
            'median': float(events_df['last_agg_glucose'].dropna().median()),
        },
        'reduce_glucose': {
            'mean': float(events_df['reduce_glucose'].dropna().mean()) if events_df['reduce_glucose'].notna().any() else None,
            'median': float(events_df['reduce_glucose'].dropna().median()) if events_df['reduce_glucose'].notna().any() else None,
        },
        'mean_fall_rate_during_agg': float(events_df['mean_fall_rate'].mean()),
        'mean_aggression_duration_min': float(events_df['aggression_duration_min'].mean()),
        'mean_total_extra_insulin': float(events_df['total_extra_insulin'].mean()),
        'mean_lead_time_min': float(events_df['lead_time_min'].mean()),
    }

    # Derive threshold rule
    # "If glucose < Y and falling at > X mg/dL/5min, reduce aggression"
    # Find the glucose level at which aggression should have stopped
    if events_df['last_agg_glucose'].notna().any():
        p75_last_agg = float(events_df['last_agg_glucose'].dropna().quantile(0.75))
        p25_fall_rate = float(events_df['mean_fall_rate'].quantile(0.25))
        summary['proposed_reduction_rule'] = {
            'glucose_threshold': round(p75_last_agg),
            'fall_rate_threshold': round(p25_fall_rate, 1),
            'rule': (f"IF glucose < {round(p75_last_agg)} AND "
                     f"falling > {abs(round(p25_fall_rate, 1))} mg/dL/5min → reduce aggression"),
        }
        print(f"  Proposed rule: {summary['proposed_reduction_rule']['rule']}")

    # Bin start_glucose to show distribution
    if 'start_glucose' in events_df.columns:
        start_bins = events_df['start_glucose'].dropna().apply(
            lambda x: glucose_bin(x, 20)).value_counts().sort_index()
        summary['start_glucose_distribution'] = {
            str(k): int(v) for k, v in start_bins.items()
        }

    for k in ['start_glucose', 'last_agg_glucose', 'reduce_glucose']:
        v = summary.get(k, {})
        if isinstance(v, dict) and 'mean' in v:
            print(f"  {k}: mean={v['mean']:.0f}, median={v['median']:.0f}")

    return {
        'summary': summary,
        'sample_events': events_df.head(50).to_dict('records') if len(events_df) > 0 else [],
    }


def exp_2540d_undertreatment(df):
    """Analyze under-treated high excursions: why didn't the loop give SMBs?

    Finds excursions >250 mg/dL and characterises what the loop was doing.
    """
    print("\n=== EXP-2540d: Under-Treatment Patterns ===")
    valid = df[df['glucose'].notna()].copy()

    events = []
    for pid, grp in valid.groupby('patient_id'):
        g = grp['glucose'].values
        smb_vals = grp['aggression_smb'].values
        basal_excess = grp['aggression_basal'].values
        cob_vals = grp['cob'].fillna(0).values
        iob_vals = grp['iob'].fillna(0).values
        bolus_vals = grp['bolus'].fillna(0).values
        suspended = grp['is_suspended'].values
        enacted_rate = grp['loop_enacted_rate'].fillna(0).values
        actual_rate = grp['actual_basal_rate'].fillna(0).values
        sched_rate = grp['scheduled_basal_rate'].fillna(0).values
        idx_list = grp.index.values

        n = len(g)
        i = 0
        while i < n - STEPS_3H:
            if g[i] >= 250 and not np.isnan(g[i]):
                # Excursion start: look at 3h window from this point
                end = min(i + STEPS_3H, n)

                # Count SMBs in this window
                window_smbs = smb_vals[i:end]
                n_smbs = int(np.sum(window_smbs > 0))
                total_smb_dose = float(np.sum(window_smbs))

                # What was the loop doing?
                window_basal_excess = basal_excess[i:end]
                window_suspended = suspended[i:end]
                window_bolus = bolus_vals[i:end]
                window_cob = cob_vals[i:end]
                window_iob = iob_vals[i:end]

                # Was it high-temping but not SMBing?
                high_temp_pct = float(np.mean(window_basal_excess > 0)) * 100
                suspend_pct = float(np.mean(window_suspended)) * 100

                # Time to return to <180
                time_to_target = None
                for j in range(i+1, end):
                    if g[j] < TARGET_HIGH and not np.isnan(g[j]):
                        time_to_target = (j - i) * 5
                        break

                # Peak glucose in window
                valid_g = g[i:end]
                valid_mask = ~np.isnan(valid_g)
                peak = float(np.max(valid_g[valid_mask])) if valid_mask.any() else float(g[i])

                events.append({
                    'patient_id': pid,
                    'start_glucose': float(g[i]),
                    'peak_glucose': peak,
                    'n_smbs': n_smbs,
                    'total_smb_dose': total_smb_dose,
                    'any_bolus': bool(np.any(window_bolus > 0.1)),
                    'total_bolus': float(np.sum(window_bolus)),
                    'high_temp_pct': high_temp_pct,
                    'suspend_pct': suspend_pct,
                    'mean_basal_excess': float(np.mean(window_basal_excess)),
                    'mean_cob': float(np.mean(window_cob)),
                    'max_cob': float(np.max(window_cob)),
                    'mean_iob': float(np.mean(window_iob)),
                    'max_iob': float(np.max(window_iob)),
                    'time_to_target_min': time_to_target,
                })

                # Skip to end of this excursion to avoid overlap
                # Advance until glucose drops below 200 or end of window
                while i < end and g[i] >= 200 and not np.isnan(g[i]):
                    i += 1
            else:
                i += 1

    events_df = pd.DataFrame(events) if events else pd.DataFrame()

    if len(events_df) == 0:
        print("  No excursion events found")
        return {'events': [], 'summary': {'n_events': 0}}

    print(f"  Found {len(events_df)} high excursion events (>=250)")

    # Split into treated vs untreated
    untreated = events_df[events_df['n_smbs'] == 0]
    treated = events_df[events_df['n_smbs'] > 0]

    summary = {
        'n_excursions': int(len(events_df)),
        'n_untreated': int(len(untreated)),
        'pct_untreated': float(len(untreated) / max(len(events_df), 1) * 100),
        'n_treated_with_smb': int(len(treated)),
    }

    if len(untreated) > 0:
        summary['untreated'] = {
            'mean_peak_glucose': float(untreated['peak_glucose'].mean()),
            'high_temp_pct': float(untreated['high_temp_pct'].mean()),
            'suspend_pct': float(untreated['suspend_pct'].mean()),
            'mean_basal_excess': float(untreated['mean_basal_excess'].mean()),
            'meal_in_progress_pct': float((untreated['mean_cob'] > 5).mean() * 100),
            'high_iob_pct': float((untreated['max_iob'] > 5).mean() * 100),
            'any_manual_bolus_pct': float(untreated['any_bolus'].mean() * 100),
            'mean_time_to_target_min': float(
                untreated['time_to_target_min'].dropna().mean()
            ) if untreated['time_to_target_min'].notna().any() else None,
            'pct_never_returned': float(
                untreated['time_to_target_min'].isna().mean() * 100),
        }

    if len(treated) > 0:
        summary['treated_with_smb'] = {
            'mean_peak_glucose': float(treated['peak_glucose'].mean()),
            'mean_n_smbs': float(treated['n_smbs'].mean()),
            'mean_smb_dose': float(treated['total_smb_dose'].mean()),
            'mean_time_to_target_min': float(
                treated['time_to_target_min'].dropna().mean()
            ) if treated['time_to_target_min'].notna().any() else None,
            'pct_never_returned': float(
                treated['time_to_target_min'].isna().mean() * 100),
        }

    # Compare treated vs untreated outcomes
    if len(treated) > 0 and len(untreated) > 0:
        t_ttt = treated['time_to_target_min'].dropna()
        u_ttt = untreated['time_to_target_min'].dropna()
        if len(t_ttt) > 10 and len(u_ttt) > 10:
            from scipy.stats import mannwhitneyu
            stat, p = mannwhitneyu(t_ttt, u_ttt, alternative='less')
            summary['smb_effectiveness'] = {
                'treated_mean_ttt_min': float(t_ttt.mean()),
                'untreated_mean_ttt_min': float(u_ttt.mean()),
                'time_saved_min': float(u_ttt.mean() - t_ttt.mean()),
                'mann_whitney_p': float(p),
                'significant': bool(p < 0.05),
            }
            print(f"  SMBs save {u_ttt.mean() - t_ttt.mean():.0f} min return-to-target "
                  f"(p={p:.4f})")

    # Why weren't SMBs given?
    if len(untreated) > 0:
        summary['untreated_reasons'] = {
            'meal_in_progress': float((untreated['mean_cob'] > 5).mean() * 100),
            'high_iob_possible_limit': float((untreated['max_iob'] > 5).mean() * 100),
            'loop_was_high_temping': float((untreated['high_temp_pct'] > 50).mean() * 100),
            'loop_was_suspended': float((untreated['suspend_pct'] > 50).mean() * 100),
            'manual_bolus_given': float(untreated['any_bolus'].mean() * 100),
        }
        print(f"  Untreated reasons: {summary['untreated_reasons']}")

    return {
        'summary': summary,
        'sample_events': events_df.head(30).to_dict('records'),
    }


def exp_2540e_threshold_rules(df):
    """Test simple threshold rules counterfactually.

    Rule 1 (hypo prevention): if glucose < 120 AND falling > 2 mg/dL/5min → suspend
    Rule 2 (hyper treatment): if glucose > 200 AND no SMB in 30min AND cob < 10 → SMB
    """
    print("\n=== EXP-2540e: Simple Threshold Rules ===")
    valid = df[df['glucose'].notna()].copy()
    roc = valid['glucose_roc'].fillna(0)

    # Pre-compute future outcomes needed by all rules
    print("  Computing future outcomes...")
    valid['min_glucose_2h'] = future_min_glucose(df, STEPS_2H).reindex(valid.index)
    valid['hypo_2h'] = (valid['min_glucose_2h'] < HYPO_THRESHOLD).astype(int)
    valid['glucose_2h'] = future_glucose(df, STEPS_2H).reindex(valid.index)
    valid['hyper_2h'] = (valid['glucose_2h'] > TARGET_HIGH).astype(int)

    # --- Rule 1: Hypo prevention ---
    # Key insight: comparing suspended vs aggressive at glucose<120 & falling>2 has
    # selection bias — the loop suspends BECAUSE glucose is already critically low.
    # Instead, compare: same glucose/roc conditions, does MORE vs LESS insulin in
    # the preceding 30 min predict worse outcomes?
    print("  Testing Rule 1: Hypo prevention (suspend if glucose<120 & falling>2)")

    rule1_condition = (valid['glucose'] < 120) & (roc < -2.0)
    rule1_applies = rule1_condition & valid['glucose'].notna()

    # Look at insulin delivered in this interval
    rule1_intervals = valid[rule1_applies].copy()

    if len(rule1_intervals) > 100:
        # Split by whether any positive aggression (insulin still being delivered)
        still_dosing = rule1_intervals['aggression'] > 0.02  # still delivering insulin
        not_dosing = ~still_dosing

        rule1_dosing_hypo = float(rule1_intervals.loc[still_dosing, 'hypo_2h'].mean()) if still_dosing.sum() > 0 else None
        rule1_nodosing_hypo = float(rule1_intervals.loc[not_dosing, 'hypo_2h'].mean()) if not_dosing.sum() > 0 else None

        # The key question: of those still dosing, how many LATER went hypo
        # vs those where dosing was already stopped?
        # Also track glucose_2h to see hyperglycemia cost of suspension
        rule1_dosing_g2h = float(rule1_intervals.loc[still_dosing, 'glucose_2h'].mean()) if still_dosing.sum() > 0 and rule1_intervals.loc[still_dosing, 'glucose_2h'].notna().any() else None
        rule1_nodosing_g2h = float(rule1_intervals.loc[not_dosing, 'glucose_2h'].mean()) if not_dosing.sum() > 0 and rule1_intervals.loc[not_dosing, 'glucose_2h'].notna().any() else None
    else:
        rule1_dosing_hypo = None
        rule1_nodosing_hypo = None
        rule1_dosing_g2h = None
        rule1_nodosing_g2h = None

    # Also test broader condition: glucose < 130 AND any negative roc
    rule1b_condition = (valid['glucose'] < 130) & (roc < -1.0)
    rule1b_intervals = valid[rule1b_condition].copy()
    rule1b_dosing = rule1b_intervals['aggression'] > 0.02
    rule1b_dosing_hypo = float(rule1b_intervals.loc[rule1b_dosing, 'hypo_2h'].mean()) if rule1b_dosing.sum() > 10 else None
    rule1b_nodosing_hypo = float(rule1b_intervals.loc[~rule1b_dosing, 'hypo_2h'].mean()) if (~rule1b_dosing).sum() > 10 else None

    rule1_result = {
        'condition': 'glucose < 120 AND glucose_roc < -2.0',
        'action': 'suspend insulin',
        'n_intervals_rule_applies': int(rule1_applies.sum()),
        'n_still_dosing': int(still_dosing.sum()) if len(rule1_intervals) > 100 else 0,
        'n_not_dosing': int(not_dosing.sum()) if len(rule1_intervals) > 100 else 0,
        'still_dosing_hypo_rate': rule1_dosing_hypo,
        'not_dosing_hypo_rate': rule1_nodosing_hypo,
        'still_dosing_glucose_2h': rule1_dosing_g2h,
        'not_dosing_glucose_2h': rule1_nodosing_g2h,
        'interpretation': None,
        'broader_rule': {
            'condition': 'glucose < 130 AND glucose_roc < -1.0',
            'n_intervals': int(rule1b_condition.sum()),
            'dosing_hypo_rate': rule1b_dosing_hypo,
            'not_dosing_hypo_rate': rule1b_nodosing_hypo,
        },
    }

    if rule1_dosing_hypo is not None and rule1_nodosing_hypo is not None:
        delta = rule1_dosing_hypo - rule1_nodosing_hypo
        n_preventable = delta * still_dosing.sum() if delta > 0 else 0
        rule1_result['excess_hypo_from_dosing'] = float(delta)
        rule1_result['estimated_preventable_hypos'] = float(n_preventable)
        rule1_result['interpretation'] = (
            f"Dosing at glucose<120 & falling>2: hypo rate {rule1_dosing_hypo:.3f} "
            f"vs not-dosing {rule1_nodosing_hypo:.3f} "
            f"({'HIGHER' if delta > 0 else 'LOWER'} by {abs(delta):.3f})"
        )
        print(f"    Still dosing hypo rate: {rule1_dosing_hypo:.3f}")
        print(f"    Not dosing hypo rate: {rule1_nodosing_hypo:.3f}")
        print(f"    Excess from dosing: {delta:.3f}, preventable: {n_preventable:.0f}")

    # --- Rule 2: Hyper treatment ---
    print("  Testing Rule 2: Hyper treatment (SMB if glucose>200 & no recent SMB & low COB)")

    # Natural experiment approach: at glucose>200 with low COB, compare intervals
    # where an SMB was given in the NEXT 30 min vs intervals where no SMB came.
    # This tests: "when the loop chose to SMB here, was the outcome better?"

    # Check for SMB in next 30 min (forward-looking)
    valid['smb_next_30m'] = False
    for pid, grp in valid.groupby('patient_id'):
        smb_col = grp['aggression_smb'].values
        fwd = np.zeros(len(smb_col), dtype=bool)
        for i in range(len(smb_col)):
            end = min(i + STEPS_30M + 1, len(smb_col))
            fwd[i] = np.any(smb_col[i:end] > 0)
        valid.loc[grp.index, 'smb_next_30m'] = fwd

    # Also check for recent SMB in the prior window (to exclude already-being-treated)
    valid['recent_smb'] = False
    for pid, grp in valid.groupby('patient_id'):
        smb_col = grp['aggression_smb'].values
        recent = np.zeros(len(smb_col), dtype=bool)
        for i in range(len(smb_col)):
            start = max(0, i - STEPS_30M)
            recent[i] = np.any(smb_col[start:i] > 0)
        valid.loc[grp.index, 'recent_smb'] = recent

    rule2_base = ((valid['glucose'] > 200)
                  & (~valid['recent_smb'])
                  & (valid['cob'].fillna(0) < 10))

    rule2_smb_came = rule2_base & valid['smb_next_30m']
    rule2_no_smb = rule2_base & (~valid['smb_next_30m'])

    # Time to return to range
    valid['time_to_range'] = pd.Series(np.nan, index=valid.index)
    for pid, grp in valid.groupby('patient_id'):
        g = grp['glucose'].values
        ttr = np.full(len(g), np.nan)
        for i in range(len(g)):
            if g[i] > TARGET_HIGH:
                for j in range(i+1, min(i + STEPS_4H, len(g))):
                    if not np.isnan(g[j]) and g[j] <= TARGET_HIGH:
                        ttr[i] = (j - i) * 5
                        break
        valid.loc[grp.index, 'time_to_range'] = ttr

    smb_ttr = valid.loc[rule2_smb_came, 'time_to_range'].dropna()
    no_smb_ttr = valid.loc[rule2_no_smb, 'time_to_range'].dropna()

    rule2_result = {
        'condition': 'glucose > 200 AND no SMB in prior 30min AND cob < 10',
        'action': 'deliver SMB',
        'n_intervals_rule_applies': int(rule2_base.sum()),
        'n_smb_followed': int(rule2_smb_came.sum()),
        'n_no_smb_followed': int(rule2_no_smb.sum()),
    }

    if len(smb_ttr) > 10 and len(no_smb_ttr) > 10:
        rule2_result['with_smb_mean_ttr_min'] = float(smb_ttr.mean())
        rule2_result['without_smb_mean_ttr_min'] = float(no_smb_ttr.mean())
        rule2_result['time_saved_min'] = float(no_smb_ttr.mean() - smb_ttr.mean())

        # Hypo risk comparison
        smb_hypo = float(valid.loc[rule2_smb_came, 'hypo_2h'].mean())
        no_smb_hypo = float(valid.loc[rule2_no_smb, 'hypo_2h'].mean())
        rule2_result['with_smb_hypo_rate'] = smb_hypo
        rule2_result['without_smb_hypo_rate'] = no_smb_hypo
        rule2_result['additional_hypo_risk'] = float(smb_hypo - no_smb_hypo)

        # Also compare starting glucose to check for selection bias
        smb_start_g = float(valid.loc[rule2_smb_came, 'glucose'].mean())
        no_smb_start_g = float(valid.loc[rule2_no_smb, 'glucose'].mean())
        rule2_result['selection_bias_check'] = {
            'mean_glucose_with_smb': smb_start_g,
            'mean_glucose_without_smb': no_smb_start_g,
            'delta': float(smb_start_g - no_smb_start_g),
        }

        print(f"    Intervals with SMB within 30min: {rule2_smb_came.sum()}")
        print(f"    Intervals without SMB: {rule2_no_smb.sum()}")
        print(f"    Mean TTR with SMB: {smb_ttr.mean():.0f} min")
        print(f"    Mean TTR without SMB: {no_smb_ttr.mean():.0f} min")
        print(f"    Time saved: {no_smb_ttr.mean() - smb_ttr.mean():.0f} min")
        print(f"    Additional hypo risk: {smb_hypo - no_smb_hypo:.4f}")
        print(f"    Selection bias: SMB group glucose {smb_start_g:.0f} vs "
              f"no-SMB {no_smb_start_g:.0f}")
    else:
        print(f"    Insufficient data: SMB group={len(smb_ttr)}, no-SMB={len(no_smb_ttr)}")

    # --- Rule 3: Combined rule ---
    # Test a glucose-adaptive threshold
    rule3_levels = [
        {'glucose_min': 80, 'glucose_max': 120, 'roc_threshold': -1.5, 'action': 'reduce'},
        {'glucose_min': 120, 'glucose_max': 180, 'roc_threshold': -3.0, 'action': 'reduce'},
        {'glucose_min': 180, 'glucose_max': 250, 'roc_threshold': None, 'action': 'increase'},
        {'glucose_min': 250, 'glucose_max': 400, 'roc_threshold': None, 'action': 'max_increase'},
    ]

    rule3_result = {
        'description': 'Glucose-adaptive aggression thresholds',
        'levels': [],
    }

    for level in rule3_levels:
        mask = ((valid['glucose'] >= level['glucose_min'])
                & (valid['glucose'] < level['glucose_max']))
        if mask.sum() < 100:
            continue

        subset = valid[mask]
        entry = {
            'glucose_range': f"{level['glucose_min']}-{level['glucose_max']}",
            'recommended_action': level['action'],
            'n_intervals': int(mask.sum()),
            'current_mean_aggression': float(subset['aggression'].mean()),
            'current_hypo_rate_2h': float(subset['hypo_2h'].mean()),
            'current_hyper_rate_2h': float(subset['hyper_2h'].mean()),
            'current_smb_rate': float((subset['aggression_smb'] > 0).mean()),
        }

        if level['roc_threshold'] is not None:
            falling_fast = subset['glucose_roc'].fillna(0) < level['roc_threshold']
            if falling_fast.sum() > 0:
                entry['n_falling_fast'] = int(falling_fast.sum())
                entry['falling_fast_hypo_rate'] = float(
                    subset.loc[falling_fast, 'hypo_2h'].mean())
                entry['not_falling_hypo_rate'] = float(
                    subset.loc[~falling_fast, 'hypo_2h'].mean())

        rule3_result['levels'].append(entry)

    result = {
        'rule1_hypo_prevention': rule1_result,
        'rule2_hyper_treatment': rule2_result,
        'rule3_adaptive_thresholds': rule3_result,
    }

    return result


def synthesize_conclusions(results):
    """Derive actionable conclusions from all sub-experiments."""
    conclusions = []

    # From 2540a
    a = results.get('exp_2540a', {})
    paradox = a.get('paradox_evidence', {})
    if paradox.get('interpretation'):
        conclusions.append(paradox['interpretation'])

    hi = a.get('summary', {}).get('high_glucose_200plus', {})
    lo = a.get('summary', {}).get('low_glucose_sub80', {})
    if hi.get('smb_rate') is not None and lo.get('suspend_rate') is not None:
        conclusions.append(
            f"At glucose>200: SMB rate only {hi['smb_rate']:.1%}, "
            f"suspend rate {hi['suspend_rate']:.1%}")
        conclusions.append(
            f"At glucose<80: suspend rate only {lo['suspend_rate']:.1%}")

    # From 2540b
    b = results.get('exp_2540b', {}).get('summary', {})
    if b.get('interpretation'):
        conclusions.append(f"Optimal curve: {b['interpretation']}")

    # From 2540c
    c = results.get('exp_2540c', {}).get('summary', {})
    if c.get('proposed_reduction_rule', {}).get('rule'):
        conclusions.append(f"Over-correction rule: {c['proposed_reduction_rule']['rule']}")
    if c.get('n_events'):
        sg = c.get('start_glucose', {})
        conclusions.append(
            f"Over-corrections start at mean glucose {sg.get('mean', 0):.0f} "
            f"(median {sg.get('median', 0):.0f})")

    # From 2540d
    d = results.get('exp_2540d', {}).get('summary', {})
    if d.get('smb_effectiveness', {}).get('time_saved_min'):
        conclusions.append(
            f"SMBs save {d['smb_effectiveness']['time_saved_min']:.0f} min TTR "
            f"(p={d['smb_effectiveness']['mann_whitney_p']:.4f})")
    if d.get('untreated_reasons'):
        reasons = d['untreated_reasons']
        top_reason = max(reasons.items(), key=lambda x: x[1])
        conclusions.append(
            f"Top reason for no SMB at >250: {top_reason[0]} ({top_reason[1]:.1f}%)")

    # From 2540e
    e = results.get('exp_2540e', {})
    r1 = e.get('rule1_hypo_prevention', {})
    if r1.get('interpretation'):
        conclusions.append(f"Hypo rule: {r1['interpretation']}")
    if r1.get('estimated_preventable_hypos') and r1['estimated_preventable_hypos'] > 0:
        conclusions.append(
            f"Hypo prevention rule could prevent ~{r1['estimated_preventable_hypos']:.0f} "
            f"hypo events")
    r2 = e.get('rule2_hyper_treatment', {})
    if r2.get('time_saved_min'):
        conclusions.append(
            f"Hyper treatment rule saves {r2['time_saved_min']:.0f} min TTR "
            f"with {r2.get('additional_hypo_risk', 0):.3f} additional hypo risk")

    return conclusions


def run_experiment():
    """Run all EXP-2540 sub-experiments."""
    print("=" * 60)
    print("EXP-2540: Loop Aggression Tuning Analysis")
    print("=" * 60)

    print("\nLoading data...")
    df = load_data()
    print(f"Loaded {len(df)} rows, {df['patient_id'].nunique()} patients")

    print("Computing aggression scores...")
    df = compute_aggression(df)
    print(f"Mean aggression: {df['aggression'].mean():.4f} U/5min")
    print(f"SMB rate: {(df['aggression_smb'] > 0).mean():.3f}")
    print(f"Suspension rate: {df['is_suspended'].mean():.3f}")

    results = {
        'experiment': 'EXP-2540',
        'title': 'Loop Aggression Tuning Analysis',
        'n_rows': int(len(df)),
        'n_patients': int(df['patient_id'].nunique()),
        'aggression_baseline': {
            'mean': float(df['aggression'].mean()),
            'median': float(df['aggression'].median()),
            'p95': float(df['aggression'].quantile(0.95)),
            'smb_rate': float((df['aggression_smb'] > 0).mean()),
            'suspension_rate': float(df['is_suspended'].mean()),
        },
    }

    results['exp_2540a'] = exp_2540a_aggression_vs_glucose(df)
    results['exp_2540b'] = exp_2540b_optimal_aggression(df)
    results['exp_2540c'] = exp_2540c_overcorrection(df)
    results['exp_2540d'] = exp_2540d_undertreatment(df)
    results['exp_2540e'] = exp_2540e_threshold_rules(df)

    results['conclusions'] = synthesize_conclusions(results)

    print("\n" + "=" * 60)
    print("CONCLUSIONS")
    print("=" * 60)
    for i, c in enumerate(results['conclusions'], 1):
        print(f"  {i}. {c}")

    # Save
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTPUT}")

    return results


if __name__ == '__main__':
    run_experiment()
