#!/usr/bin/env python3
"""
EXP-2141–2148: Hypoglycemia Prevention & Production Monitoring

Bridge from research findings to production-ready hypo prevention
algorithms and therapy monitoring systems.

EXP-2141: Hypo prediction features — what predicts hypoglycemia 15/30/60 min ahead?
EXP-2142: Hypo context characterization — what precedes hypo events?
EXP-2143: Prevention simulation — retroactive context-aware guard evaluation
EXP-2144: Sublinear ISF validation — held-out validation of dose^(-α) model
EXP-2145: Combined intervention replay — all improvements applied together
EXP-2146: Drift detection algorithm — real-time ISF drift detector design
EXP-2147: Safety alerting system — threshold-based therapy review triggers
EXP-2148: Production readiness scorecard — data quality and confidence requirements

Depends on: exp_metabolic_441.py
"""

import json
import sys
import os
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from exp_metabolic_441 import load_patients, compute_supply_demand


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


PATIENT_DIR = 'externals/ns-data/patients/'
FIG_DIR = 'docs/60-research/figures'
EXP_DIR = 'externals/experiments'
MAKE_FIGS = '--figures' in sys.argv

if MAKE_FIGS:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    os.makedirs(FIG_DIR, exist_ok=True)

os.makedirs(EXP_DIR, exist_ok=True)

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 288

patients = load_patients(PATIENT_DIR)


def compute_tir_tbr_tar(glucose):
    g = glucose[~np.isnan(glucose)]
    if len(g) == 0:
        return 0, 0, 0
    return (float(np.mean((g >= 70) & (g <= 180))),
            float(np.mean(g < 70)),
            float(np.mean(g > 180)))


def get_profile_value(schedule, hour):
    """Get profile value for a given hour from list-of-dicts schedule."""
    if not schedule:
        return None
    sorted_sched = sorted(schedule, key=lambda x: x.get('timeAsSeconds', 0))
    result = sorted_sched[0].get('value', None)
    target_seconds = hour * 3600
    for entry in sorted_sched:
        if entry.get('timeAsSeconds', 0) <= target_seconds:
            result = entry.get('value', result)
    return result


# ── EXP-2141: Hypo Prediction Features ──────────────────────────────
def exp_2141_hypo_prediction():
    """What features predict hypoglycemia 15/30/60 minutes ahead?"""
    print("\n═══ EXP-2141: Hypo Prediction Features ═══")

    horizons = [3, 6, 12]  # 15min, 30min, 60min in 5-min steps
    horizon_labels = ['15min', '30min', '60min']
    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))

        patient_results = {}

        for hi, horizon in enumerate(horizons):
            # Build feature matrix at each step
            features_list = []
            labels = []

            for t in range(max(12, horizon), len(g) - horizon):
                if np.isnan(g[t]):
                    continue
                # Will glucose be <70 at t+horizon?
                future_g = g[t + horizon]
                if np.isnan(future_g):
                    continue

                label = 1 if future_g < 70 else 0

                # Features at time t
                current_g = g[t]
                # Rate of change (last 15 min)
                past_g = [g[t-i] for i in range(1, 4) if not np.isnan(g[t-i])]
                roc = (current_g - np.mean(past_g)) / len(past_g) if past_g else 0

                # Longer-term trend (last 30 min)
                past_30 = [g[t-i] for i in range(1, 7) if not np.isnan(g[t-i])]
                roc_30 = (current_g - np.mean(past_30)) / len(past_30) if past_30 else 0

                # IOB at time t
                current_iob = iob[t] if not np.isnan(iob[t]) else 0

                # Recent bolus (last 1h)
                recent_bolus = float(np.nansum(bolus[max(0, t-12):t]))

                # Recent carbs (last 1h)
                recent_carbs = float(np.nansum(carbs[max(0, t-12):t]))

                # Time of day (hour)
                hour = (t % STEPS_PER_DAY) / STEPS_PER_HOUR

                # Glucose level itself
                features_list.append([current_g, roc, roc_30, current_iob,
                                      recent_bolus, recent_carbs, hour])
                labels.append(label)

            if len(labels) < 100:
                continue

            features = np.array(features_list)
            labels = np.array(labels)

            # Compute feature correlations with hypo label
            feature_names = ['glucose', 'roc_15m', 'roc_30m', 'iob',
                             'bolus_1h', 'carbs_1h', 'hour']
            correlations = {}
            for fi, fname in enumerate(feature_names):
                valid = ~np.isnan(features[:, fi])
                if valid.sum() > 100:
                    r = np.corrcoef(features[valid, fi], labels[valid])[0, 1]
                    correlations[fname] = float(r) if not np.isnan(r) else 0
                else:
                    correlations[fname] = 0

            # Simple threshold-based prediction: glucose < threshold
            hypo_rate = float(np.mean(labels))
            best_threshold = 100
            best_f1 = 0
            for thresh in range(70, 150, 5):
                pred = (features[:, 0] < thresh).astype(int)
                tp = np.sum((pred == 1) & (labels == 1))
                fp = np.sum((pred == 1) & (labels == 0))
                fn = np.sum((pred == 0) & (labels == 1))
                precision = tp / (tp + fp) if (tp + fp) > 0 else 0
                recall = tp / (tp + fn) if (tp + fn) > 0 else 0
                f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
                if f1 > best_f1:
                    best_f1 = f1
                    best_threshold = thresh

            # Also test ROC+glucose combined
            # Simple: predict hypo if glucose < 100 AND falling
            combined_pred = ((features[:, 0] < 100) & (features[:, 1] < -1)).astype(int)
            tp_c = np.sum((combined_pred == 1) & (labels == 1))
            fp_c = np.sum((combined_pred == 1) & (labels == 0))
            fn_c = np.sum((combined_pred == 0) & (labels == 1))
            prec_c = tp_c / (tp_c + fp_c) if (tp_c + fp_c) > 0 else 0
            rec_c = tp_c / (tp_c + fn_c) if (tp_c + fn_c) > 0 else 0
            f1_c = 2 * prec_c * rec_c / (prec_c + rec_c) if (prec_c + rec_c) > 0 else 0

            patient_results[horizon_labels[hi]] = {
                'hypo_rate': hypo_rate,
                'correlations': correlations,
                'best_threshold': best_threshold,
                'best_threshold_f1': best_f1,
                'combined_f1': f1_c,
                'combined_precision': prec_c,
                'combined_recall': rec_c,
                'n_samples': len(labels)
            }

        if patient_results:
            all_results[name] = patient_results
            h30 = patient_results.get('30min', {})
            corrs = h30.get('correlations', {})
            top_feat = max(corrs, key=lambda k: abs(corrs[k])) if corrs else 'N/A'
            print(f"  {name}: hypo_rate={h30.get('hypo_rate', 0):.3f} "
                  f"best_f1={h30.get('best_threshold_f1', 0):.3f} "
                  f"combined_f1={h30.get('combined_f1', 0):.3f} "
                  f"top_feature={top_feat}(r={corrs.get(top_feat, 0):.3f})")

    # Save results
    with open(f'{EXP_DIR}/exp-2141_hypo_prediction.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        # Panel 1: Feature importance heatmap (correlations)
        patient_names = sorted(all_results.keys())
        feature_names = ['glucose', 'roc_15m', 'roc_30m', 'iob', 'bolus_1h', 'carbs_1h', 'hour']
        corr_matrix = np.zeros((len(patient_names), len(feature_names)))
        for pi, pn in enumerate(patient_names):
            corrs = all_results[pn].get('30min', {}).get('correlations', {})
            for fi, fn in enumerate(feature_names):
                corr_matrix[pi, fi] = corrs.get(fn, 0)

        im = axes[0].imshow(corr_matrix, cmap='RdBu_r', vmin=-0.3, vmax=0.3, aspect='auto')
        axes[0].set_xticks(range(len(feature_names)))
        axes[0].set_xticklabels(feature_names, rotation=45, ha='right', fontsize=8)
        axes[0].set_yticks(range(len(patient_names)))
        axes[0].set_yticklabels(patient_names, fontsize=8)
        axes[0].set_title('Feature-Hypo Correlation (30min)')
        plt.colorbar(im, ax=axes[0], shrink=0.8)

        # Panel 2: F1 by horizon
        for pn in patient_names:
            f1s = [all_results[pn].get(h, {}).get('best_threshold_f1', 0) for h in horizon_labels]
            axes[1].plot(horizon_labels, f1s, 'o-', alpha=0.5, label=pn)
        axes[1].set_xlabel('Prediction Horizon')
        axes[1].set_ylabel('Best F1 Score')
        axes[1].set_title('Hypo Prediction F1 by Horizon')
        axes[1].legend(fontsize=7, ncol=2)
        axes[1].set_ylim(0, 1)
        axes[1].grid(True, alpha=0.3)

        # Panel 3: Threshold vs Combined predictor
        thresh_f1 = [all_results[pn].get('30min', {}).get('best_threshold_f1', 0) for pn in patient_names]
        comb_f1 = [all_results[pn].get('30min', {}).get('combined_f1', 0) for pn in patient_names]
        x = np.arange(len(patient_names))
        axes[2].bar(x - 0.15, thresh_f1, 0.3, label='Glucose threshold', color='steelblue')
        axes[2].bar(x + 0.15, comb_f1, 0.3, label='Glucose + trend', color='coral')
        axes[2].set_xticks(x)
        axes[2].set_xticklabels(patient_names, fontsize=8)
        axes[2].set_ylabel('F1 Score (30min)')
        axes[2].set_title('Threshold vs Combined Predictor')
        axes[2].legend(fontsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/hypo-fig01-prediction.png', dpi=150)
        plt.close()
        print("  → Saved hypo-fig01-prediction.png")

    return all_results


# ── EXP-2142: Hypo Context Characterization ─────────────────────────
def exp_2142_hypo_context():
    """What happens in the 2 hours before hypoglycemia?"""
    print("\n═══ EXP-2142: Hypo Context Characterization ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))

        lookback = 24  # 2 hours = 24 steps
        hypo_events = []

        # Find hypo entry points (glucose crosses below 70)
        for t in range(lookback, len(g) - 1):
            if np.isnan(g[t]) or np.isnan(g[t-1]):
                continue
            if g[t] < 70 and g[t-1] >= 70:
                # This is a hypo entry
                pre_glucose = g[t-lookback:t]
                pre_iob = iob[t-lookback:t]
                pre_bolus = bolus[t-lookback:t]
                pre_carbs = carbs[t-lookback:t]

                if np.sum(np.isnan(pre_glucose)) > lookback * 0.3:
                    continue

                # Classify context
                had_bolus = float(np.nansum(pre_bolus)) > 0.5
                had_carbs = float(np.nansum(pre_carbs)) > 5
                high_iob = float(np.nanmean(pre_iob)) > 1.5
                was_falling = float(np.nanmean(np.diff(pre_glucose[-6:]))) < -2

                # Time of day
                hour = (t % STEPS_PER_DAY) / STEPS_PER_HOUR

                # Starting glucose (2h before)
                start_g = float(np.nanmean(pre_glucose[:3]))

                # How fast the drop was
                drop_rate = (start_g - g[t]) / (lookback / STEPS_PER_HOUR)

                # How deep the hypo goes
                post_window = min(t + 24, len(g))
                nadir = float(np.nanmin(g[t:post_window])) if post_window > t else g[t]

                # Recovery time (steps to get back above 70)
                recovery_steps = 0
                for rt in range(t, min(t + 72, len(g))):
                    if not np.isnan(g[rt]) and g[rt] >= 70:
                        recovery_steps = rt - t
                        break
                else:
                    recovery_steps = 72  # didn't recover in 6h

                # Classify the hypo type
                if had_bolus and had_carbs:
                    hypo_type = 'post_meal_over_bolus'
                elif had_bolus and not had_carbs:
                    hypo_type = 'correction_hypo'
                elif not had_bolus and high_iob:
                    hypo_type = 'insulin_tail'
                elif was_falling and not had_bolus:
                    hypo_type = 'unexplained_drop'
                else:
                    hypo_type = 'other'

                hypo_events.append({
                    'hour': float(hour),
                    'start_glucose': start_g,
                    'nadir': nadir,
                    'drop_rate': drop_rate,
                    'recovery_steps': recovery_steps,
                    'had_bolus': had_bolus,
                    'had_carbs': had_carbs,
                    'high_iob': high_iob,
                    'type': hypo_type
                })

        if not hypo_events:
            continue

        # Summarize
        types = {}
        for e in hypo_events:
            t = e['type']
            types[t] = types.get(t, 0) + 1

        median_nadir = float(np.median([e['nadir'] for e in hypo_events]))
        median_recovery = float(np.median([e['recovery_steps'] for e in hypo_events]))
        median_drop_rate = float(np.median([e['drop_rate'] for e in hypo_events]))

        # Hour distribution
        hours = [e['hour'] for e in hypo_events]
        hour_hist = np.histogram(hours, bins=np.arange(0, 25, 1))[0]

        all_results[name] = {
            'n_hypos': len(hypo_events),
            'types': types,
            'median_nadir': median_nadir,
            'median_recovery_min': median_recovery * 5,
            'median_drop_rate': median_drop_rate,
            'hour_distribution': hour_hist.tolist(),
            'events': hypo_events[:50]  # Keep first 50 for analysis
        }

        dominant_type = max(types, key=types.get)
        print(f"  {name}: {len(hypo_events)} hypos, dominant={dominant_type}"
              f"({types[dominant_type]}/{len(hypo_events)}), "
              f"nadir={median_nadir:.0f}, recovery={median_recovery*5:.0f}min")

    with open(f'{EXP_DIR}/exp-2142_hypo_context.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # Panel 1: Hypo type distribution stacked bar
        patient_names = sorted(all_results.keys())
        all_types = set()
        for pn in patient_names:
            all_types.update(all_results[pn]['types'].keys())
        all_types = sorted(all_types)

        bottom = np.zeros(len(patient_names))
        colors = plt.cm.Set2(np.linspace(0, 1, len(all_types)))
        for ti, tp in enumerate(all_types):
            vals = [all_results[pn]['types'].get(tp, 0) for pn in patient_names]
            axes[0, 0].bar(patient_names, vals, bottom=bottom, label=tp,
                           color=colors[ti], alpha=0.8)
            bottom += vals
        axes[0, 0].set_ylabel('Number of Hypo Events')
        axes[0, 0].set_title('Hypo Types by Patient')
        axes[0, 0].legend(fontsize=7, loc='upper right')
        axes[0, 0].tick_params(axis='x', labelsize=8)

        # Panel 2: Hour distribution (population)
        pop_hours = np.zeros(24)
        for pn in patient_names:
            h = all_results[pn]['hour_distribution']
            pop_hours[:len(h)] += h
        axes[0, 1].bar(range(24), pop_hours, color='steelblue', alpha=0.7)
        axes[0, 1].set_xlabel('Hour of Day')
        axes[0, 1].set_ylabel('Number of Hypos')
        axes[0, 1].set_title('Hypo Timing (Population)')
        axes[0, 1].set_xticks(range(0, 24, 3))
        axes[0, 1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Nadir vs recovery
        nadirs = [all_results[pn]['median_nadir'] for pn in patient_names]
        recoveries = [all_results[pn]['median_recovery_min'] for pn in patient_names]
        axes[1, 0].scatter(nadirs, recoveries, s=100, c='coral', edgecolors='black', zorder=3)
        for i, pn in enumerate(patient_names):
            axes[1, 0].annotate(pn, (nadirs[i], recoveries[i]),
                                textcoords="offset points", xytext=(5, 5), fontsize=8)
        axes[1, 0].set_xlabel('Median Nadir (mg/dL)')
        axes[1, 0].set_ylabel('Median Recovery Time (min)')
        axes[1, 0].set_title('Hypo Severity vs Recovery')
        axes[1, 0].axvline(x=54, color='red', linestyle='--', alpha=0.5, label='Severe (<54)')
        axes[1, 0].legend(fontsize=8)
        axes[1, 0].grid(True, alpha=0.3)

        # Panel 4: Drop rate distribution
        drop_rates = [all_results[pn]['median_drop_rate'] for pn in patient_names]
        n_hypos = [all_results[pn]['n_hypos'] for pn in patient_names]
        scatter = axes[1, 1].scatter(drop_rates, n_hypos, s=100,
                                     c='steelblue', edgecolors='black', zorder=3)
        for i, pn in enumerate(patient_names):
            axes[1, 1].annotate(pn, (drop_rates[i], n_hypos[i]),
                                textcoords="offset points", xytext=(5, 5), fontsize=8)
        axes[1, 1].set_xlabel('Median Drop Rate (mg/dL/hr)')
        axes[1, 1].set_ylabel('Total Hypo Events')
        axes[1, 1].set_title('Drop Rate vs Frequency')
        axes[1, 1].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/hypo-fig02-context.png', dpi=150)
        plt.close()
        print("  → Saved hypo-fig02-context.png")

    return all_results


# ── EXP-2143: Prevention Simulation ─────────────────────────────────
def exp_2143_prevention_simulation():
    """If we applied context-aware guard retroactively, how many hypos prevented?"""
    print("\n═══ EXP-2143: Prevention Simulation ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))

        # Find correction boluses (bolus with no carbs in ±30min)
        correction_boluses = []
        for t in range(6, len(g) - 36):
            if np.isnan(bolus[t]) or bolus[t] < 0.5:
                continue
            nearby_carbs = float(np.nansum(carbs[max(0, t-6):min(len(carbs), t+6)]))
            if nearby_carbs > 5:
                continue  # Meal bolus, skip
            correction_boluses.append(t)

        if len(correction_boluses) < 5:
            print(f"  {name}: insufficient corrections ({len(correction_boluses)})")
            continue

        # For each correction, check if it led to hypo within 3h
        total_corrections = len(correction_boluses)
        hypo_after_correction = 0
        guard_would_block = 0
        guard_prevented_hypo = 0
        guard_blocked_good = 0

        for t in correction_boluses:
            # Did it cause hypo?
            post = g[t:min(t + 36, len(g))]
            caused_hypo = bool(np.any(post < 70))
            if caused_hypo:
                hypo_after_correction += 1

            # Would guard have blocked it?
            current_iob = float(iob[t]) if not np.isnan(iob[t]) else 0
            recent_trend = float(np.nanmean(np.diff(g[max(0, t-6):t+1]))) if t > 0 else 0
            guard_blocks = current_iob > 1.5 or recent_trend < -2

            if guard_blocks:
                guard_would_block += 1
                if caused_hypo:
                    guard_prevented_hypo += 1
                else:
                    guard_blocked_good += 1

        # Also check: of the hypos NOT after corrections, how many are "unexplained"
        total_hypos = 0
        for t in range(1, len(g)):
            if not np.isnan(g[t]) and not np.isnan(g[t-1]):
                if g[t] < 70 and g[t-1] >= 70:
                    total_hypos += 1

        prevention_rate = guard_prevented_hypo / hypo_after_correction if hypo_after_correction > 0 else 0
        false_block_rate = guard_blocked_good / guard_would_block if guard_would_block > 0 else 0

        all_results[name] = {
            'total_corrections': total_corrections,
            'hypo_after_correction': hypo_after_correction,
            'correction_hypo_rate': hypo_after_correction / total_corrections if total_corrections > 0 else 0,
            'guard_would_block': guard_would_block,
            'guard_prevented_hypo': guard_prevented_hypo,
            'guard_blocked_good_correction': guard_blocked_good,
            'prevention_rate': prevention_rate,
            'false_block_rate': false_block_rate,
            'total_hypos': total_hypos,
            'fraction_correction_hypos': hypo_after_correction / total_hypos if total_hypos > 0 else 0
        }

        print(f"  {name}: {total_corrections} corrections, "
              f"{hypo_after_correction} led to hypo ({hypo_after_correction*100//max(1,total_corrections)}%), "
              f"guard blocks {guard_would_block}, "
              f"prevents {guard_prevented_hypo} hypos ({prevention_rate:.0%})")

    with open(f'{EXP_DIR}/exp-2143_prevention_sim.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: Correction outcomes (hypo vs safe)
        hypo_counts = [all_results[pn]['hypo_after_correction'] for pn in patient_names]
        safe_counts = [all_results[pn]['total_corrections'] - all_results[pn]['hypo_after_correction']
                       for pn in patient_names]
        x = np.arange(len(patient_names))
        axes[0].bar(x, safe_counts, label='Safe correction', color='steelblue', alpha=0.7)
        axes[0].bar(x, hypo_counts, bottom=safe_counts, label='Led to hypo', color='coral', alpha=0.7)
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_ylabel('Number of Corrections')
        axes[0].set_title('Correction Outcomes')
        axes[0].legend(fontsize=8)

        # Panel 2: Guard effect
        prevented = [all_results[pn]['guard_prevented_hypo'] for pn in patient_names]
        false_blocks = [all_results[pn]['guard_blocked_good_correction'] for pn in patient_names]
        axes[1].bar(x - 0.15, prevented, 0.3, label='Hypos prevented', color='green', alpha=0.7)
        axes[1].bar(x + 0.15, false_blocks, 0.3, label='Good corrections blocked', color='orange', alpha=0.7)
        axes[1].set_xticks(x)
        axes[1].set_xticklabels(patient_names, fontsize=8)
        axes[1].set_ylabel('Count')
        axes[1].set_title('Context-Aware Guard Effect')
        axes[1].legend(fontsize=8)

        # Panel 3: What fraction of all hypos come from corrections?
        frac = [all_results[pn]['fraction_correction_hypos'] for pn in patient_names]
        axes[2].bar(patient_names, [f * 100 for f in frac], color='coral', alpha=0.7)
        axes[2].set_ylabel('% of All Hypos from Corrections')
        axes[2].set_title('Correction-Caused Hypo Fraction')
        axes[2].axhline(y=50, color='red', linestyle='--', alpha=0.3)
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/hypo-fig03-prevention.png', dpi=150)
        plt.close()
        print("  → Saved hypo-fig03-prevention.png")

    return all_results


# ── EXP-2144: Sublinear ISF Validation ──────────────────────────────
def exp_2144_isf_validation():
    """Validate ISF(dose) = base × dose^(-α) on held-out correction windows."""
    print("\n═══ EXP-2144: Sublinear ISF Validation ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))

        # Find clean correction windows
        corrections = []
        for t in range(6, len(g) - 36):
            if np.isnan(bolus[t]) or bolus[t] < 0.5 or g[t] < 150:
                continue
            nearby_carbs = float(np.nansum(carbs[max(0, t-6):min(len(carbs), t+6)]))
            if nearby_carbs > 5:
                continue
            # Check no additional bolus in next 3h
            additional = float(np.nansum(bolus[t+1:min(t+36, len(bolus))]))
            if additional > 0.3:
                continue
            # Measure outcome: glucose change after 3h
            if t + 36 >= len(g) or np.isnan(g[t+36]):
                continue
            delta_g = g[t+36] - g[t]
            dose = float(bolus[t])
            isf_observed = -delta_g / dose  # Positive = glucose dropped per unit

            if abs(isf_observed) > 500:  # Outlier
                continue

            corrections.append({
                'dose': dose,
                'delta_g': float(delta_g),
                'isf_observed': isf_observed,
                'start_g': float(g[t])
            })

        if len(corrections) < 10:
            print(f"  {name}: insufficient corrections ({len(corrections)})")
            continue

        # Split into train/test
        np.random.seed(42)
        indices = np.random.permutation(len(corrections))
        split = len(corrections) // 2
        train_idx, test_idx = indices[:split], indices[split:]

        train = [corrections[i] for i in train_idx]
        test = [corrections[i] for i in test_idx]

        # Fit linear ISF (constant) on train
        train_isfs = [c['isf_observed'] for c in train]
        linear_isf = float(np.median(train_isfs))

        # Fit sublinear ISF(dose) = base × dose^(-α) on train
        # Log-linear regression: log(ISF) = log(base) - α × log(dose)
        train_doses = np.array([c['dose'] for c in train])
        train_isf_arr = np.array(train_isfs)

        # Filter positive ISFs for log
        pos_mask = train_isf_arr > 0
        if pos_mask.sum() < 5:
            print(f"  {name}: too few positive ISFs ({pos_mask.sum()})")
            continue

        log_dose = np.log(train_doses[pos_mask])
        log_isf = np.log(train_isf_arr[pos_mask])

        # Linear fit
        if len(log_dose) > 2:
            coeffs = np.polyfit(log_dose, log_isf, 1)
            alpha = -coeffs[0]
            base = np.exp(coeffs[1])
        else:
            alpha = 0.4
            base = linear_isf

        # Evaluate on test set
        test_doses = np.array([c['dose'] for c in test])
        test_isfs = np.array([c['isf_observed'] for c in test])
        test_deltas = np.array([c['delta_g'] for c in test])

        # Linear model predictions
        linear_pred = np.array([-linear_isf * c['dose'] for c in test])
        # Sublinear model predictions
        sublinear_pred = np.array([-base * (c['dose'] ** (1 - alpha)) for c in test])

        # RMSE
        linear_rmse = float(np.sqrt(np.mean((test_deltas - linear_pred) ** 2)))
        sublinear_rmse = float(np.sqrt(np.mean((test_deltas - sublinear_pred) ** 2)))

        improvement = (linear_rmse - sublinear_rmse) / linear_rmse * 100

        all_results[name] = {
            'n_corrections': len(corrections),
            'n_train': len(train),
            'n_test': len(test),
            'alpha': float(alpha),
            'base': float(base),
            'linear_isf': linear_isf,
            'linear_rmse': linear_rmse,
            'sublinear_rmse': sublinear_rmse,
            'improvement_pct': improvement
        }

        print(f"  {name}: α={alpha:.2f} base={base:.0f} "
              f"linear_RMSE={linear_rmse:.1f} sublinear_RMSE={sublinear_rmse:.1f} "
              f"improvement={improvement:+.1f}% ({len(corrections)} corrections)")

    with open(f'{EXP_DIR}/exp-2144_isf_validation.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())

        # Panel 1: RMSE comparison
        linear_rmse = [all_results[pn]['linear_rmse'] for pn in patient_names]
        sublinear_rmse = [all_results[pn]['sublinear_rmse'] for pn in patient_names]
        x = np.arange(len(patient_names))
        axes[0].bar(x - 0.15, linear_rmse, 0.3, label='Linear ISF', color='steelblue')
        axes[0].bar(x + 0.15, sublinear_rmse, 0.3, label='Sublinear ISF', color='coral')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_ylabel('RMSE (mg/dL)')
        axes[0].set_title('ISF Model RMSE (Held-out)')
        axes[0].legend(fontsize=8)
        axes[0].grid(True, alpha=0.3, axis='y')

        # Panel 2: Alpha values across patients
        alphas = [all_results[pn]['alpha'] for pn in patient_names]
        axes[1].bar(patient_names, alphas, color='green', alpha=0.7)
        axes[1].axhline(y=0.4, color='red', linestyle='--', alpha=0.5, label='α=0.4 (prior)')
        axes[1].set_ylabel('α (dose exponent)')
        axes[1].set_title('Sublinear Exponent by Patient')
        axes[1].legend(fontsize=8)
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Improvement percentage
        improvements = [all_results[pn]['improvement_pct'] for pn in patient_names]
        colors = ['green' if i > 0 else 'red' for i in improvements]
        axes[2].bar(patient_names, improvements, color=colors, alpha=0.7)
        axes[2].axhline(y=0, color='black', linewidth=0.5)
        axes[2].set_ylabel('RMSE Improvement (%)')
        axes[2].set_title('Sublinear vs Linear Improvement')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/hypo-fig04-isf-validation.png', dpi=150)
        plt.close()
        print("  → Saved hypo-fig04-isf-validation.png")

    return all_results


# ── EXP-2145: Combined Intervention Replay ──────────────────────────
def exp_2145_combined_replay():
    """Replay all corrections with sublinear ISF + context guard + meal CR."""
    print("\n═══ EXP-2145: Combined Intervention Replay ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values.copy()
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(g))
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))

        # Get profile ISF
        isf_schedule = df.attrs.get('isf_schedule', [])
        profile_isf = get_profile_value(isf_schedule, 12)
        if profile_isf is None or profile_isf == 0:
            profile_isf = 50
        if profile_isf < 15:
            profile_isf *= 18.0182

        # Simulate modified corrections
        original_hypos = 0
        modified_hypos = 0
        corrections_modified = 0
        corrections_blocked = 0
        total_corrections = 0

        for t in range(12, len(g) - 36):
            if np.isnan(bolus[t]) or bolus[t] < 0.5:
                continue

            nearby_carbs = float(np.nansum(carbs[max(0, t-6):min(len(carbs), t+6)]))
            if nearby_carbs > 5:
                continue

            total_corrections += 1
            dose = float(bolus[t])

            # Original outcome
            if t + 36 < len(g) and not np.isnan(g[t+36]):
                original_outcome = g[t+36]
                if original_outcome < 70:
                    original_hypos += 1

                # Context-aware guard check
                current_iob = float(iob[t]) if not np.isnan(iob[t]) else 0
                recent_trend = float(np.nanmean(np.diff(g[max(0, t-6):t+1])))

                if current_iob > 1.5 or recent_trend < -2:
                    # Guard blocks: assume no correction given
                    corrections_blocked += 1
                    # Modified outcome: glucose stays ~where it is (no correction)
                    modified_outcome = g[t]  # Approximate
                    if modified_outcome < 70:
                        modified_hypos += 1
                else:
                    # Correction allowed but with sublinear ISF
                    # Sublinear dose adjustment: dose × dose^(-0.4)
                    effective_dose = dose ** 0.6  # dose^(1-0.4)
                    reduction_ratio = effective_dose / dose
                    # Modified delta_g = original delta × reduction_ratio
                    original_delta = g[t+36] - g[t]
                    modified_delta = original_delta * reduction_ratio
                    modified_outcome = g[t] + modified_delta
                    corrections_modified += 1
                    if modified_outcome < 70:
                        modified_hypos += 1

        # TIR/TBR comparison
        tir_orig, tbr_orig, tar_orig = compute_tir_tbr_tar(g)
        n_days = len(g) / STEPS_PER_DAY

        all_results[name] = {
            'total_corrections': total_corrections,
            'corrections_blocked': corrections_blocked,
            'corrections_modified': corrections_modified,
            'original_hypos': original_hypos,
            'modified_hypos': modified_hypos,
            'hypo_reduction': (original_hypos - modified_hypos) / max(1, original_hypos),
            'block_rate': corrections_blocked / max(1, total_corrections),
            'tir': tir_orig,
            'tbr': tbr_orig
        }

        print(f"  {name}: {total_corrections} corrections, "
              f"blocked {corrections_blocked} ({corrections_blocked*100//max(1,total_corrections)}%), "
              f"hypos {original_hypos}→{modified_hypos} "
              f"({(original_hypos-modified_hypos)*100//max(1,original_hypos)}% reduction)")

    with open(f'{EXP_DIR}/exp-2145_combined_replay.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        patient_names = sorted(all_results.keys())
        x = np.arange(len(patient_names))

        # Panel 1: Hypo reduction
        orig = [all_results[pn]['original_hypos'] for pn in patient_names]
        mod = [all_results[pn]['modified_hypos'] for pn in patient_names]
        axes[0].bar(x - 0.15, orig, 0.3, label='Original', color='coral')
        axes[0].bar(x + 0.15, mod, 0.3, label='With guard + sublinear', color='steelblue')
        axes[0].set_xticks(x)
        axes[0].set_xticklabels(patient_names, fontsize=8)
        axes[0].set_ylabel('Post-Correction Hypos')
        axes[0].set_title('Hypo Events: Original vs Modified')
        axes[0].legend(fontsize=8)

        # Panel 2: Block rate and modification rate
        block = [all_results[pn]['block_rate'] * 100 for pn in patient_names]
        axes[1].bar(patient_names, block, color='orange', alpha=0.7)
        axes[1].set_ylabel('% Corrections Blocked by Guard')
        axes[1].set_title('Context-Aware Guard Block Rate')
        axes[1].tick_params(axis='x', labelsize=8)
        axes[1].grid(True, alpha=0.3, axis='y')

        # Panel 3: Hypo reduction percentage
        reduction = [all_results[pn]['hypo_reduction'] * 100 for pn in patient_names]
        colors = ['green' if r > 0 else 'red' for r in reduction]
        axes[2].bar(patient_names, reduction, color=colors, alpha=0.7)
        axes[2].set_ylabel('Hypo Reduction (%)')
        axes[2].set_title('Combined Intervention Effect')
        axes[2].tick_params(axis='x', labelsize=8)
        axes[2].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/hypo-fig05-replay.png', dpi=150)
        plt.close()
        print("  → Saved hypo-fig05-replay.png")

    return all_results


# ── EXP-2146: Drift Detection Algorithm ─────────────────────────────
def exp_2146_drift_detection():
    """Design and validate a real-time ISF drift detector."""
    print("\n═══ EXP-2146: Drift Detection Algorithm ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))

        # Compute rolling ISF estimate using 30-day windows
        window_days = 30
        window_steps = window_days * STEPS_PER_DAY
        step_days = 7
        step_steps = step_days * STEPS_PER_DAY

        rolling_isf = []
        rolling_times = []

        for start in range(0, len(g) - window_steps, step_steps):
            end = start + window_steps
            win_g = g[start:end]
            win_bolus = bolus[start:end]
            win_carbs = carbs[start:end]

            # Find corrections in this window
            isf_obs = []
            for t in range(6, len(win_g) - 36):
                if np.isnan(win_bolus[t]) or win_bolus[t] < 0.5 or np.isnan(win_g[t]) or win_g[t] < 150:
                    continue
                nearby_c = float(np.nansum(win_carbs[max(0, t-6):min(len(win_carbs), t+6)]))
                if nearby_c > 5:
                    continue
                additional = float(np.nansum(win_bolus[t+1:min(t+36, len(win_bolus))]))
                if additional > 0.3:
                    continue
                if t + 36 >= len(win_g) or np.isnan(win_g[t+36]):
                    continue
                delta_g = win_g[t+36] - win_g[t]
                dose = float(win_bolus[t])
                isf = -delta_g / dose
                if 0 < isf < 500:
                    isf_obs.append(isf)

            if len(isf_obs) >= 3:
                rolling_isf.append(float(np.median(isf_obs)))
                rolling_times.append(start / STEPS_PER_DAY)

        if len(rolling_isf) < 4:
            print(f"  {name}: insufficient windows ({len(rolling_isf)})")
            continue

        isf_arr = np.array(rolling_isf)
        time_arr = np.array(rolling_times)

        # Drift detection: compare each window to baseline (first 2 windows)
        baseline = np.mean(isf_arr[:2])
        drift_pct = ((isf_arr - baseline) / baseline * 100).tolist()

        # CUSUM detector
        target_shift = 0.15 * baseline  # 15% shift threshold
        cusum_pos = [0.0]
        cusum_neg = [0.0]
        alerts = []
        alert_threshold = 3 * target_shift

        for i in range(1, len(isf_arr)):
            diff = isf_arr[i] - baseline
            cusum_pos.append(max(0, cusum_pos[-1] + diff - target_shift / 2))
            cusum_neg.append(max(0, cusum_neg[-1] - diff - target_shift / 2))

            if cusum_pos[-1] > alert_threshold or cusum_neg[-1] > alert_threshold:
                alerts.append({
                    'day': float(time_arr[i]),
                    'isf': float(isf_arr[i]),
                    'drift_pct': float((isf_arr[i] - baseline) / baseline * 100),
                    'direction': 'increasing' if cusum_pos[-1] > alert_threshold else 'decreasing'
                })
                # Reset after alert
                cusum_pos[-1] = 0
                cusum_neg[-1] = 0

        # Overall trend
        if len(time_arr) > 2:
            slope = np.polyfit(time_arr, isf_arr, 1)[0]
            trend_pct_per_month = float(slope * 30 / baseline * 100)
        else:
            trend_pct_per_month = 0

        all_results[name] = {
            'n_windows': len(rolling_isf),
            'baseline_isf': float(baseline),
            'final_isf': float(isf_arr[-1]),
            'total_drift_pct': float((isf_arr[-1] - baseline) / baseline * 100),
            'trend_pct_per_month': trend_pct_per_month,
            'n_alerts': len(alerts),
            'alerts': alerts,
            'rolling_isf': rolling_isf,
            'rolling_days': time_arr.tolist(),
            'drift_pct': drift_pct,
            'cusum_pos': cusum_pos,
            'cusum_neg': cusum_neg
        }

        status = "ALERT" if alerts else "STABLE"
        print(f"  {name}: baseline={baseline:.0f} final={isf_arr[-1]:.0f} "
              f"drift={trend_pct_per_month:+.1f}%/mo "
              f"alerts={len(alerts)} [{status}]")

    with open(f'{EXP_DIR}/exp-2146_drift_detection.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        patient_names = sorted(all_results.keys())
        n_patients = len(patient_names)
        n_cols = 3
        n_rows = (n_patients + n_cols - 1) // n_cols

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
        axes = axes.flatten() if n_rows > 1 else [axes] if n_cols == 1 else axes.flatten()

        for pi, pn in enumerate(patient_names):
            ax = axes[pi]
            r = all_results[pn]
            days = r['rolling_days']
            isf = r['rolling_isf']

            ax.plot(days, isf, 'o-', color='steelblue', markersize=4, label='ISF')
            ax.axhline(y=r['baseline_isf'], color='gray', linestyle='--', alpha=0.5, label='Baseline')

            # Mark alerts
            for alert in r['alerts']:
                ax.axvline(x=alert['day'], color='red', alpha=0.3, linewidth=2)

            ax.set_title(f"Patient {pn} ({r['trend_pct_per_month']:+.1f}%/mo)", fontsize=10)
            ax.set_xlabel('Day', fontsize=8)
            ax.set_ylabel('Effective ISF', fontsize=8)
            ax.legend(fontsize=7)
            ax.grid(True, alpha=0.3)

        # Hide unused
        for pi in range(n_patients, len(axes)):
            axes[pi].set_visible(False)

        plt.suptitle('ISF Drift Detection (CUSUM)', fontsize=14, y=1.01)
        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/hypo-fig06-drift.png', dpi=150, bbox_inches='tight')
        plt.close()
        print("  → Saved hypo-fig06-drift.png")

    return all_results


# ── EXP-2147: Safety Alerting System ────────────────────────────────
def exp_2147_safety_alerting():
    """Design threshold-based therapy review triggers."""
    print("\n═══ EXP-2147: Safety Alerting System ═══")

    all_results = {}

    # Define alert thresholds
    thresholds = {
        'tbr_warning': 4.0,    # TBR > 4%
        'tbr_critical': 7.0,   # TBR > 7%
        'hypo_freq_warning': 3.0,    # >3 hypos/day
        'hypo_freq_critical': 5.0,   # >5 hypos/day
        'severe_hypo_any': True,     # Any severe hypo (<54)
        'isf_drift_warning': 20,     # ISF drift >20%
        'tir_declining_warning': 5,  # TIR declining >5pp/month
        'cv_warning': 36,            # CV > 36%
    }

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values

        # Compute weekly metrics
        weekly_metrics = []
        steps_per_week = STEPS_PER_DAY * 7

        for w_start in range(0, len(g) - steps_per_week, steps_per_week):
            w_end = w_start + steps_per_week
            w_g = g[w_start:w_end]
            valid = w_g[~np.isnan(w_g)]

            if len(valid) < steps_per_week * 0.5:
                continue

            tir = float(np.mean((valid >= 70) & (valid <= 180))) * 100
            tbr = float(np.mean(valid < 70)) * 100
            tar = float(np.mean(valid > 180)) * 100
            cv = float(np.std(valid) / np.mean(valid)) * 100 if np.mean(valid) > 0 else 0

            # Count hypo events
            hypo_count = 0
            for t in range(1, len(w_g)):
                if not np.isnan(w_g[t]) and not np.isnan(w_g[t-1]):
                    if w_g[t] < 70 and w_g[t-1] >= 70:
                        hypo_count += 1

            severe_count = 0
            for t in range(1, len(w_g)):
                if not np.isnan(w_g[t]) and not np.isnan(w_g[t-1]):
                    if w_g[t] < 54 and w_g[t-1] >= 54:
                        severe_count += 1

            weekly_metrics.append({
                'week': len(weekly_metrics),
                'tir': tir,
                'tbr': tbr,
                'tar': tar,
                'cv': cv,
                'hypos': hypo_count,
                'severe_hypos': severe_count,
                'hypos_per_day': hypo_count / 7
            })

        if not weekly_metrics:
            continue

        # Generate alerts
        alerts = []
        for wm in weekly_metrics:
            week_alerts = []

            if wm['tbr'] > thresholds['tbr_critical']:
                week_alerts.append({'type': 'TBR_CRITICAL', 'value': wm['tbr'],
                                    'threshold': thresholds['tbr_critical']})
            elif wm['tbr'] > thresholds['tbr_warning']:
                week_alerts.append({'type': 'TBR_WARNING', 'value': wm['tbr'],
                                    'threshold': thresholds['tbr_warning']})

            if wm['hypos_per_day'] > thresholds['hypo_freq_critical']:
                week_alerts.append({'type': 'HYPO_FREQ_CRITICAL',
                                    'value': wm['hypos_per_day'],
                                    'threshold': thresholds['hypo_freq_critical']})
            elif wm['hypos_per_day'] > thresholds['hypo_freq_warning']:
                week_alerts.append({'type': 'HYPO_FREQ_WARNING',
                                    'value': wm['hypos_per_day'],
                                    'threshold': thresholds['hypo_freq_warning']})

            if wm['severe_hypos'] > 0:
                week_alerts.append({'type': 'SEVERE_HYPO', 'value': wm['severe_hypos']})

            if wm['cv'] > thresholds['cv_warning']:
                week_alerts.append({'type': 'CV_HIGH', 'value': wm['cv'],
                                    'threshold': thresholds['cv_warning']})

            if week_alerts:
                alerts.append({'week': wm['week'], 'alerts': week_alerts})

        # TIR trend alert
        if len(weekly_metrics) >= 4:
            tirs = [wm['tir'] for wm in weekly_metrics]
            recent_4 = tirs[-4:]
            earlier_4 = tirs[:4]
            tir_trend = np.mean(recent_4) - np.mean(earlier_4)
            if tir_trend < -thresholds['tir_declining_warning']:
                alerts.append({'week': len(weekly_metrics) - 1,
                               'alerts': [{'type': 'TIR_DECLINING',
                                           'value': float(tir_trend)}]})
        else:
            tir_trend = 0

        # Summary
        total_alert_weeks = len([a for a in alerts if any(
            al['type'].endswith('CRITICAL') for al in a['alerts'])])
        warning_weeks = len([a for a in alerts if any(
            al['type'].endswith('WARNING') for al in a['alerts'])])
        severe_weeks = len([a for a in alerts if any(
            al['type'] == 'SEVERE_HYPO' for al in a['alerts'])])

        all_results[name] = {
            'n_weeks': len(weekly_metrics),
            'total_alerts': len(alerts),
            'critical_weeks': total_alert_weeks,
            'warning_weeks': warning_weeks,
            'severe_hypo_weeks': severe_weeks,
            'tir_trend': float(tir_trend),
            'weekly_metrics': weekly_metrics,
            'alerts': alerts[:20]  # Keep first 20
        }

        print(f"  {name}: {len(weekly_metrics)} weeks, "
              f"{len(alerts)} alert-weeks "
              f"({total_alert_weeks} critical, {severe_weeks} severe-hypo), "
              f"TIR trend={tir_trend:+.1f}pp")

    with open(f'{EXP_DIR}/exp-2147_safety_alerts.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        patient_names = sorted(all_results.keys())

        # Panel 1: Alert frequency by type
        alert_types = ['TBR_CRITICAL', 'TBR_WARNING', 'HYPO_FREQ_CRITICAL',
                       'HYPO_FREQ_WARNING', 'SEVERE_HYPO', 'CV_HIGH', 'TIR_DECLINING']
        type_counts = {at: [] for at in alert_types}
        for pn in patient_names:
            counts = {at: 0 for at in alert_types}
            for a in all_results[pn].get('alerts', []):
                for al in a.get('alerts', []):
                    if al['type'] in counts:
                        counts[al['type']] += 1
            for at in alert_types:
                type_counts[at].append(counts[at])

        bottom = np.zeros(len(patient_names))
        colors = plt.cm.Set1(np.linspace(0, 1, len(alert_types)))
        for ti, at in enumerate(alert_types):
            vals = type_counts[at]
            if sum(vals) > 0:
                axes[0, 0].bar(patient_names, vals, bottom=bottom, label=at.replace('_', ' '),
                               color=colors[ti], alpha=0.8)
                bottom += vals
        axes[0, 0].set_ylabel('Alert Weeks')
        axes[0, 0].set_title('Safety Alert Frequency')
        axes[0, 0].legend(fontsize=6, loc='upper right')
        axes[0, 0].tick_params(axis='x', labelsize=8)

        # Panel 2: Weekly TIR trends (select patients)
        highlight = ['d', 'i', 'a', 'k']  # Best, worst, declining, paradox
        for pn in highlight:
            if pn in all_results:
                wms = all_results[pn]['weekly_metrics']
                tirs = [wm['tir'] for wm in wms]
                axes[0, 1].plot(range(len(tirs)), tirs, 'o-', label=pn,
                                alpha=0.7, markersize=3)
        axes[0, 1].axhline(y=70, color='green', linestyle='--', alpha=0.3, label='TIR target')
        axes[0, 1].set_xlabel('Week')
        axes[0, 1].set_ylabel('TIR (%)')
        axes[0, 1].set_title('Weekly TIR Trends (Selected)')
        axes[0, 1].legend(fontsize=8)
        axes[0, 1].grid(True, alpha=0.3)

        # Panel 3: Weekly TBR trends (select patients)
        for pn in highlight:
            if pn in all_results:
                wms = all_results[pn]['weekly_metrics']
                tbrs = [wm['tbr'] for wm in wms]
                axes[1, 0].plot(range(len(tbrs)), tbrs, 'o-', label=pn,
                                alpha=0.7, markersize=3)
        axes[1, 0].axhline(y=4, color='orange', linestyle='--', alpha=0.3, label='Warning')
        axes[1, 0].axhline(y=7, color='red', linestyle='--', alpha=0.3, label='Critical')
        axes[1, 0].set_xlabel('Week')
        axes[1, 0].set_ylabel('TBR (%)')
        axes[1, 0].set_title('Weekly TBR Trends (Selected)')
        axes[1, 0].legend(fontsize=8)
        axes[1, 0].grid(True, alpha=0.3)

        # Panel 4: TIR trend summary
        trends = [all_results[pn].get('tir_trend', 0) for pn in patient_names]
        colors_t = ['green' if t > 0 else 'orange' if t > -5 else 'red' for t in trends]
        axes[1, 1].bar(patient_names, trends, color=colors_t, alpha=0.7)
        axes[1, 1].axhline(y=0, color='black', linewidth=0.5)
        axes[1, 1].axhline(y=-5, color='red', linestyle='--', alpha=0.3, label='Declining threshold')
        axes[1, 1].set_ylabel('TIR Change (pp)')
        axes[1, 1].set_title('TIR Trend (Recent vs Early)')
        axes[1, 1].legend(fontsize=8)
        axes[1, 1].tick_params(axis='x', labelsize=8)
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/hypo-fig07-alerts.png', dpi=150)
        plt.close()
        print("  → Saved hypo-fig07-alerts.png")

    return all_results


# ── EXP-2148: Production Readiness Scorecard ────────────────────────
def exp_2148_production_readiness():
    """What data quality and confidence thresholds are needed for production?"""
    print("\n═══ EXP-2148: Production Readiness Scorecard ═══")

    all_results = {}

    for p in patients:
        name = p['name']
        df = p['df']
        g = df['glucose'].values
        bolus = df['bolus'].values if 'bolus' in df.columns else np.zeros(len(g))
        carbs = df['carbs'].values if 'carbs' in df.columns else np.zeros(len(g))
        iob = df['iob'].values if 'iob' in df.columns else np.zeros(len(g))

        n_days = len(g) / STEPS_PER_DAY

        # Data quality metrics
        cgm_coverage = float(np.mean(~np.isnan(g))) * 100
        bolus_coverage = float(np.mean(~np.isnan(bolus) & (bolus >= 0)))
        iob_coverage = float(np.mean(~np.isnan(iob) & (iob >= 0)))

        # Correction window count (for ISF estimation confidence)
        n_corrections = 0
        correction_isfs = []
        for t in range(6, len(g) - 36):
            if np.isnan(bolus[t]) or bolus[t] < 0.5 or np.isnan(g[t]) or g[t] < 150:
                continue
            nearby_c = float(np.nansum(carbs[max(0, t-6):min(len(carbs), t+6)]))
            if nearby_c > 5:
                continue
            additional = float(np.nansum(bolus[t+1:min(t+36, len(bolus))]))
            if additional > 0.3:
                continue
            if t + 36 >= len(g) or np.isnan(g[t+36]):
                continue
            delta_g = g[t+36] - g[t]
            dose = float(bolus[t])
            isf = -delta_g / dose
            if 0 < isf < 500:
                correction_isfs.append(isf)
                n_corrections += 1

        # ISF confidence
        if n_corrections >= 20:
            isf_ci = 1.96 * np.std(correction_isfs) / np.sqrt(n_corrections)
            isf_confidence = 'HIGH'
        elif n_corrections >= 10:
            isf_ci = 1.96 * np.std(correction_isfs) / np.sqrt(n_corrections) if correction_isfs else 999
            isf_confidence = 'MEDIUM'
        elif n_corrections >= 3:
            isf_ci = 1.96 * np.std(correction_isfs) / np.sqrt(n_corrections) if correction_isfs else 999
            isf_confidence = 'LOW'
        else:
            isf_ci = 999
            isf_confidence = 'INSUFFICIENT'

        # Meal count (for CR estimation)
        n_meals = 0
        for t in range(len(carbs)):
            if not np.isnan(carbs[t]) and carbs[t] > 5:
                n_meals += 1

        if n_meals >= 60:
            cr_confidence = 'HIGH'
        elif n_meals >= 30:
            cr_confidence = 'MEDIUM'
        elif n_meals >= 10:
            cr_confidence = 'LOW'
        else:
            cr_confidence = 'INSUFFICIENT'

        # Overnight windows (for basal estimation)
        n_quiet_nights = 0
        for d in range(int(n_days)):
            midnight = d * STEPS_PER_DAY
            sixam = midnight + 6 * STEPS_PER_HOUR
            if sixam >= len(g):
                continue
            window_g = g[midnight:sixam]
            window_bolus = bolus[midnight:sixam]
            window_carbs = carbs[midnight:sixam]
            if (np.sum(np.isnan(window_g)) < len(window_g) * 0.3 and
                float(np.nansum(window_bolus)) < 0.3 and
                float(np.nansum(window_carbs)) < 5):
                n_quiet_nights += 1

        if n_quiet_nights >= 20:
            basal_confidence = 'HIGH'
        elif n_quiet_nights >= 10:
            basal_confidence = 'MEDIUM'
        elif n_quiet_nights >= 5:
            basal_confidence = 'LOW'
        else:
            basal_confidence = 'INSUFFICIENT'

        # Overall readiness
        confidences = [isf_confidence, cr_confidence, basal_confidence]
        if all(c in ('HIGH', 'MEDIUM') for c in confidences) and cgm_coverage > 70:
            readiness = 'READY'
        elif any(c == 'INSUFFICIENT' for c in confidences) or cgm_coverage < 50:
            readiness = 'NOT_READY'
        else:
            readiness = 'PARTIAL'

        # Minimum data needed
        days_for_isf = max(0, (20 - n_corrections) * 3)  # ~1 correction per 3 days
        days_for_cr = max(0, (60 - n_meals) * 2)  # ~1 meal per 2 days
        days_for_basal = max(0, (20 - n_quiet_nights) * 5)  # ~1 quiet night per 5 days

        all_results[name] = {
            'n_days': float(n_days),
            'cgm_coverage_pct': cgm_coverage,
            'n_corrections': n_corrections,
            'isf_confidence': isf_confidence,
            'isf_ci_95': float(isf_ci) if isf_ci < 999 else None,
            'n_meals': n_meals,
            'cr_confidence': cr_confidence,
            'n_quiet_nights': n_quiet_nights,
            'basal_confidence': basal_confidence,
            'readiness': readiness,
            'additional_days_needed': {
                'for_isf': days_for_isf,
                'for_cr': days_for_cr,
                'for_basal': days_for_basal,
                'maximum': max(days_for_isf, days_for_cr, days_for_basal)
            }
        }

        print(f"  {name}: [{readiness}] CGM={cgm_coverage:.0f}% "
              f"ISF={isf_confidence}({n_corrections}corr) "
              f"CR={cr_confidence}({n_meals}meals) "
              f"Basal={basal_confidence}({n_quiet_nights}nights)")

    with open(f'{EXP_DIR}/exp-2148_production_readiness.json', 'w') as f:
        json.dump(all_results, f, indent=2, cls=NumpyEncoder)

    if MAKE_FIGS and all_results:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        patient_names = sorted(all_results.keys())

        # Panel 1: Readiness heatmap
        conf_map = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1, 'INSUFFICIENT': 0}
        metrics = ['isf_confidence', 'cr_confidence', 'basal_confidence']
        metric_labels = ['ISF', 'CR', 'Basal']
        heat_data = np.zeros((len(patient_names), 3))
        for pi, pn in enumerate(patient_names):
            for mi, m in enumerate(metrics):
                heat_data[pi, mi] = conf_map.get(all_results[pn][m], 0)

        im = axes[0, 0].imshow(heat_data, cmap='RdYlGn', vmin=0, vmax=3, aspect='auto')
        axes[0, 0].set_xticks(range(3))
        axes[0, 0].set_xticklabels(metric_labels, fontsize=10)
        axes[0, 0].set_yticks(range(len(patient_names)))
        axes[0, 0].set_yticklabels(patient_names, fontsize=8)
        axes[0, 0].set_title('Estimation Confidence')
        # Add text
        for pi in range(len(patient_names)):
            for mi in range(3):
                pn = patient_names[pi]
                val = all_results[pn][metrics[mi]]
                axes[0, 0].text(mi, pi, val[0], ha='center', va='center', fontsize=8,
                                color='white' if heat_data[pi, mi] < 1.5 else 'black')
        plt.colorbar(im, ax=axes[0, 0], ticks=[0, 1, 2, 3],
                     format=lambda x, _: ['INSUF', 'LOW', 'MED', 'HIGH'][int(x)])

        # Panel 2: Data availability
        corrections = [all_results[pn]['n_corrections'] for pn in patient_names]
        meals = [all_results[pn]['n_meals'] for pn in patient_names]
        nights = [all_results[pn]['n_quiet_nights'] for pn in patient_names]
        x = np.arange(len(patient_names))
        w = 0.25
        axes[0, 1].bar(x - w, corrections, w, label='Corrections', color='steelblue')
        axes[0, 1].bar(x, meals, w, label='Meals', color='coral')
        axes[0, 1].bar(x + w, nights, w, label='Quiet nights', color='green')
        axes[0, 1].set_xticks(x)
        axes[0, 1].set_xticklabels(patient_names, fontsize=8)
        axes[0, 1].set_ylabel('Count')
        axes[0, 1].set_title('Data Availability for Estimation')
        axes[0, 1].legend(fontsize=8)
        axes[0, 1].set_yscale('log')
        axes[0, 1].grid(True, alpha=0.3, axis='y')

        # Panel 3: CGM coverage
        coverage = [all_results[pn]['cgm_coverage_pct'] for pn in patient_names]
        colors_cov = ['green' if c > 70 else 'orange' if c > 50 else 'red' for c in coverage]
        axes[1, 0].bar(patient_names, coverage, color=colors_cov, alpha=0.7)
        axes[1, 0].axhline(y=70, color='green', linestyle='--', alpha=0.3, label='70% threshold')
        axes[1, 0].set_ylabel('CGM Coverage (%)')
        axes[1, 0].set_title('CGM Data Coverage')
        axes[1, 0].legend(fontsize=8)
        axes[1, 0].tick_params(axis='x', labelsize=8)
        axes[1, 0].grid(True, alpha=0.3, axis='y')

        # Panel 4: Additional days needed
        add_isf = [all_results[pn]['additional_days_needed']['for_isf'] for pn in patient_names]
        add_cr = [all_results[pn]['additional_days_needed']['for_cr'] for pn in patient_names]
        add_basal = [all_results[pn]['additional_days_needed']['for_basal'] for pn in patient_names]
        axes[1, 1].bar(x - w, add_isf, w, label='For ISF', color='steelblue')
        axes[1, 1].bar(x, add_cr, w, label='For CR', color='coral')
        axes[1, 1].bar(x + w, add_basal, w, label='For Basal', color='green')
        axes[1, 1].set_xticks(x)
        axes[1, 1].set_xticklabels(patient_names, fontsize=8)
        axes[1, 1].set_ylabel('Additional Days Needed')
        axes[1, 1].set_title('Data Gap to Production Readiness')
        axes[1, 1].legend(fontsize=8)
        axes[1, 1].tick_params(axis='x', labelsize=8)
        axes[1, 1].grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        plt.savefig(f'{FIG_DIR}/hypo-fig08-readiness.png', dpi=150)
        plt.close()
        print("  → Saved hypo-fig08-readiness.png")

    return all_results


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 60)
    print("EXP-2141–2148: Hypoglycemia Prevention & Production Monitoring")
    print("=" * 60)

    r1 = exp_2141_hypo_prediction()
    r2 = exp_2142_hypo_context()
    r3 = exp_2143_prevention_simulation()
    r4 = exp_2144_isf_validation()
    r5 = exp_2145_combined_replay()
    r6 = exp_2146_drift_detection()
    r7 = exp_2147_safety_alerting()
    r8 = exp_2148_production_readiness()

    print("\n" + "=" * 60)
    n_complete = sum(1 for r in [r1, r2, r3, r4, r5, r6, r7, r8] if r)
    print(f"Results: {n_complete}/8 experiments completed")
    print(f"Figures saved to {FIG_DIR}/hypo-fig01–08")
    print("=" * 60)
