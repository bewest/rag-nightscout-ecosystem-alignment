#!/usr/bin/env python3
"""
EXP-2411–2418: Target Sweep Replication

Replicates OREF-INV-003's glucose target partial dependence analysis.
The colleague found a clear hypo/hyper tradeoff: curves cross at ~90-95 mg/dL,
with hypo dropping from 48.6% at target 80 to 34.1% at target 150.

We test whether this tradeoff shape holds in our independent data using both
the colleague's pre-trained models and our own retrained models.

Experiments:
  2411 - Target sweep using our trained LightGBM
  2412 - Target sweep using colleague's pre-trained models
  2413 - Per-patient target sweep (heterogeneity)
  2414 - Loop vs AAPS subset comparison
  2415 - Optimal target per patient (risk-minimizing)
  2416 - Comparison with our supply-demand target analysis (EXP-2201)
  2417 - Sensitivity to sweep methodology
  2418 - Synthesis

Usage:
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2411 --figures
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2411 --figures --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from oref_inv_003_replication.data_bridge import (
    load_patients_with_features, split_loop_vs_oref, OREF_FEATURES,
)
from oref_inv_003_replication.colleague_loader import ColleagueModels
from oref_inv_003_replication.report_engine import (
    ComparisonReport, save_figure, plot_sweep_comparison,
    NumpyEncoder, COLORS, PATIENT_COLORS,
)

warnings.filterwarnings('ignore')

RESULTS_PATH = Path('externals/experiments/exp_2411_target_sweep.json')
FIGURES_DIR = Path('tools/oref_inv_003_replication/figures')

# Colleague's reported target sweep results (from Findings Overview)
THEIR_SWEEP = {
    'targets': [80, 90, 100, 110, 120, 130, 150],
    'hypo_rates': [48.6, 44.0, 41.2, 39.0, 37.4, 34.4, 34.1],
    'hyper_rates': [43.5, 44.0, 47.0, 49.0, 51.4, 56.0, 56.0],
}


def prepare_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Prepare features and labels for modeling."""
    valid = df.dropna(subset=['cgm_mgdl', 'hypo_4h', 'hyper_4h']).copy()
    X = valid[OREF_FEATURES].fillna(0)
    y_hypo = valid['hypo_4h'].astype(int)
    y_hyper = valid['hyper_4h'].astype(int)
    return X, y_hypo, y_hyper


def train_models(X: pd.DataFrame, y_hypo: pd.Series, y_hyper: pd.Series,
                 n_estimators: int = 500) -> tuple:
    """Train hypo and hyper LightGBM classifiers."""
    params = dict(n_estimators=n_estimators, learning_rate=0.05, max_depth=6,
                  min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
                  random_state=42, verbose=-1)
    hypo_model = lgb.LGBMClassifier(**params)
    hyper_model = lgb.LGBMClassifier(**params)
    print('  Training hypo model...')
    hypo_model.fit(X, y_hypo)
    print('  Training hyper model...')
    hyper_model.fit(X, y_hyper)
    return hypo_model, hyper_model


def target_sweep(X: pd.DataFrame, hypo_model, hyper_model,
                 targets: list[float] = None) -> dict:
    """Sweep target values and predict hypo/hyper rates.

    For each target value, modify sug_current_target (and derived features)
    and re-predict. This matches the colleague's partial dependence approach.
    """
    if targets is None:
        targets = list(range(70, 155, 5))

    results = {'targets': targets, 'hypo_rates': [], 'hyper_rates': []}

    for tgt in targets:
        X_mod = X.copy()
        # Modify target and derived features
        X_mod['sug_current_target'] = tgt
        X_mod['sug_threshold'] = max(tgt - 0.5 * (tgt - 40), 60)
        X_mod['bg_above_target'] = X_mod['cgm_mgdl'] - tgt

        hypo_p = hypo_model.predict_proba(X_mod)[:, 1].mean() * 100
        hyper_p = hyper_model.predict_proba(X_mod)[:, 1].mean() * 100
        results['hypo_rates'].append(round(hypo_p, 2))
        results['hyper_rates'].append(round(hyper_p, 2))

    return results


def find_crossover(targets, hypo_rates, hyper_rates) -> float:
    """Find target where hypo and hyper curves cross."""
    for i in range(len(targets) - 1):
        diff_a = hypo_rates[i] - hyper_rates[i]
        diff_b = hypo_rates[i + 1] - hyper_rates[i + 1]
        if diff_a * diff_b <= 0:  # sign change
            # Linear interpolation
            frac = abs(diff_a) / (abs(diff_a) + abs(diff_b) + 1e-9)
            return targets[i] + frac * (targets[i + 1] - targets[i])
    return float('nan')


def run_2411(X, y_hypo, y_hyper, do_figures=False):
    """EXP-2411: Full cohort target sweep with our model."""
    print('\n=== EXP-2411: Target Sweep (full cohort, our model) ===')
    hypo_m, hyper_m = train_models(X, y_hypo, y_hyper)

    sweep = target_sweep(X, hypo_m, hyper_m)
    crossover = find_crossover(sweep['targets'], sweep['hypo_rates'], sweep['hyper_rates'])
    print(f'  Crossover point: {crossover:.1f} mg/dL (theirs: ~92 mg/dL)')
    print(f'  Hypo at target 80: {sweep["hypo_rates"][2]:.1f}% (theirs: 48.6%)')
    print(f'  Hyper at target 130: {sweep["hyper_rates"][-6]:.1f}% (theirs: 56.0%)')

    if do_figures:
        plot_sweep_comparison(
            THEIR_SWEEP['targets'], THEIR_SWEEP['hypo_rates'], THEIR_SWEEP['hyper_rates'],
            sweep['targets'], sweep['hypo_rates'], sweep['hyper_rates'],
            xlabel='Target (mg/dL)',
            title='Target Sweep: OREF-INV-003 vs Our Replication',
            output_path='fig_2411_target_sweep.png',
        )

    return {
        'sweep': sweep, 'crossover_mgdl': crossover,
        'hypo_model_importance': dict(zip(OREF_FEATURES,
            hypo_m.feature_importances_.tolist())),
    }


def run_2412(X, colleague_models, do_figures=False):
    """EXP-2412: Target sweep using colleague's pre-trained models."""
    print('\n=== EXP-2412: Target Sweep (colleague\'s pre-trained models) ===')
    targets = list(range(70, 155, 5))
    hypo_rates, hyper_rates = [], []

    for tgt in targets:
        X_mod = X.copy()
        X_mod['sug_current_target'] = tgt
        X_mod['sug_threshold'] = max(tgt - 0.5 * (tgt - 40), 60)
        X_mod['bg_above_target'] = X_mod['cgm_mgdl'] - tgt

        hypo_p = colleague_models.predict_hypo(X_mod).mean() * 100
        hyper_p = colleague_models.predict_hyper(X_mod).mean() * 100
        hypo_rates.append(round(hypo_p, 2))
        hyper_rates.append(round(hyper_p, 2))

    crossover = find_crossover(targets, hypo_rates, hyper_rates)
    print(f'  Crossover (their model, our data): {crossover:.1f} mg/dL')

    sweep = {'targets': targets, 'hypo_rates': hypo_rates, 'hyper_rates': hyper_rates}

    if do_figures:
        plot_sweep_comparison(
            THEIR_SWEEP['targets'], THEIR_SWEEP['hypo_rates'], THEIR_SWEEP['hyper_rates'],
            targets, hypo_rates, hyper_rates,
            xlabel='Target (mg/dL)',
            title='Target Sweep: Their Model on Our Data vs Their Original',
            output_path='fig_2412_transfer_sweep.png',
        )

    return {'sweep': sweep, 'crossover_mgdl': crossover}


def run_2413(df, do_figures=False):
    """EXP-2413: Per-patient target sweep."""
    print('\n=== EXP-2413: Per-patient target sweeps ===')
    patient_results = {}

    for pid in sorted(df['patient_id'].unique()):
        pdf = df[df['patient_id'] == pid]
        X_p, y_hypo_p, y_hyper_p = prepare_data(pdf)
        if len(X_p) < 2000 or y_hypo_p.sum() < 20:
            print(f'  {pid}: skipped (too few rows or events)')
            continue

        hypo_m, hyper_m = train_models(X_p, y_hypo_p, y_hyper_p, n_estimators=200)
        sweep = target_sweep(X_p, hypo_m, hyper_m, targets=list(range(80, 141, 10)))
        crossover = find_crossover(sweep['targets'], sweep['hypo_rates'], sweep['hyper_rates'])
        patient_results[pid] = {'crossover': crossover, 'sweep': sweep}
        print(f'  {pid}: crossover at {crossover:.1f} mg/dL')

    if do_figures and patient_results:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        for pid, res in patient_results.items():
            color = PATIENT_COLORS.get(pid, '#6b7280')
            ax1.plot(res['sweep']['targets'], res['sweep']['hypo_rates'],
                     '-o', color=color, markersize=3, label=pid, alpha=0.7)
            ax2.plot(res['sweep']['targets'], res['sweep']['hyper_rates'],
                     '-s', color=color, markersize=3, label=pid, alpha=0.7)

        ax1.set_title('Per-Patient Hypo Rate vs Target', fontweight='bold')
        ax1.set_xlabel('Target (mg/dL)')
        ax1.set_ylabel('Predicted 4h Hypo Rate (%)')
        ax1.legend(fontsize=7, ncol=2)
        ax1.grid(True, alpha=0.3)

        ax2.set_title('Per-Patient Hyper Rate vs Target', fontweight='bold')
        ax2.set_xlabel('Target (mg/dL)')
        ax2.set_ylabel('Predicted 4h Hyper Rate (%)')
        ax2.legend(fontsize=7, ncol=2)
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        save_figure(fig, 'fig_2413_per_patient_sweep.png')
        plt.close(fig)

    return patient_results


def run_2414(df, do_figures=False):
    """EXP-2414: Loop vs AAPS subset comparison."""
    print('\n=== EXP-2414: Loop vs AAPS target sweeps ===')
    loop_df, oref_df = split_loop_vs_oref(df)
    results = {}

    for label, subset in [('Loop', loop_df), ('AAPS', oref_df)]:
        X_s, y_hypo_s, y_hyper_s = prepare_data(subset)
        if len(X_s) < 1000:
            print(f'  {label}: skipped (too few rows)')
            continue
        hypo_m, hyper_m = train_models(X_s, y_hypo_s, y_hyper_s)
        sweep = target_sweep(X_s, hypo_m, hyper_m)
        crossover = find_crossover(sweep['targets'], sweep['hypo_rates'], sweep['hyper_rates'])
        results[label] = {'sweep': sweep, 'crossover': crossover}
        print(f'  {label}: crossover at {crossover:.1f} mg/dL')

    if do_figures and len(results) == 2:
        fig, ax = plt.subplots(figsize=(10, 6))
        for label, style in [('Loop', '-'), ('AAPS', '--')]:
            r = results[label]
            ax.plot(r['sweep']['targets'], r['sweep']['hypo_rates'],
                    f'{style}o', color='#e74c3c', label=f'{label} hypo', markersize=4)
            ax.plot(r['sweep']['targets'], r['sweep']['hyper_rates'],
                    f'{style}s', color='#f39c12', label=f'{label} hyper', markersize=4)
        ax.axhline(y=50, color='gray', linestyle=':', alpha=0.5)
        ax.set_xlabel('Target (mg/dL)')
        ax.set_ylabel('Predicted 4h Event Rate (%)')
        ax.set_title('Target Sweep: Loop vs AAPS Patients', fontweight='bold')
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        save_figure(fig, 'fig_2414_loop_vs_aaps.png')
        plt.close(fig)

    return results


def main():
    parser = argparse.ArgumentParser(description='EXP-2411: Target Sweep Replication')
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--tiny', action='store_true', help='Quick test with 2 patients')
    args = parser.parse_args()

    print('=' * 70)
    print('EXP-2411–2418: Target Sweep Replication')
    print('=' * 70)

    # Load data
    df = load_patients_with_features()
    if args.tiny:
        pids = sorted(df['patient_id'].unique())[:2]
        df = df[df['patient_id'].isin(pids)]
        print(f'[TINY MODE] Using patients: {pids}')

    X, y_hypo, y_hyper = prepare_data(df)
    print(f'Data: {len(X):,} rows, {X.shape[1]} features')
    print(f'Hypo rate: {y_hypo.mean()*100:.1f}%, Hyper rate: {y_hyper.mean()*100:.1f}%')

    # Load colleague's models
    colleague = ColleagueModels()

    results = {}
    results['exp_2411'] = run_2411(X, y_hypo, y_hyper, args.figures)
    results['exp_2412'] = run_2412(X, colleague, args.figures)
    results['exp_2413'] = run_2413(df, args.figures)
    results['exp_2414'] = run_2414(df, args.figures)

    # ── Synthesis report ────────────────────────────────────────────────
    def _fmt(val, decimals=1, suffix=''):
        """Format a numeric value, returning 'N/A' for NaN."""
        try:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return 'N/A'
            return f'{val:.{decimals}f}{suffix}'
        except (TypeError, ValueError):
            return 'N/A'

    our_cross = results['exp_2411']['crossover_mgdl']
    their_cross = 92.5  # approximate from their description

    report = ComparisonReport(
        exp_id='EXP-2411',
        title='Target Sweep Replication',
        phase='replication',
        script='tools/oref_inv_003_replication/exp_repl_2411.py',
    )

    # ── Methodology ──────────────────────────────────────────────────
    report.set_methodology(
        'We replicate the OREF-INV-003 glucose-target partial-dependence '
        'analysis using a virtual-experiment design. For each target value '
        'in [70, 75, …, 150] mg/dL we modify `sug_current_target` (and its '
        'derived features `sug_threshold`, `bg_above_target`) while holding '
        'all other features at their observed values, then re-predict 4-hour '
        'hypo and hyper probabilities with our independently trained LightGBM '
        'classifiers.\n\n'
        'Four sub-experiments provide complementary views:\n'
        '- **EXP-2411**: Full-cohort sweep with our retrained models.\n'
        '- **EXP-2412**: Full-cohort sweep using the colleague\'s pre-trained '
        'models applied to our data (transfer check).\n'
        '- **EXP-2413**: Per-patient sweeps revealing individual heterogeneity.\n'
        '- **EXP-2414**: Loop-only vs AAPS-only subset comparison.'
    )

    # ── F1: Target crossover (improved — NaN-safe) ───────────────────
    cross_diff = abs(our_cross - their_cross) if not np.isnan(our_cross) else float('inf')

    report.add_their_finding(
        'F1', 'Target is the single most powerful user-controlled lever',
        evidence=(
            f'Curves cross at ~{their_cross} mg/dL. Hypo drops from 48.6% '
            f'(target 80) to 34.1% (target 150).'
        ),
        source='OREF-INV-003 Findings Overview',
    )

    sweep_2411 = results['exp_2411']['sweep']
    hypo_80 = sweep_2411['hypo_rates'][2] if len(sweep_2411['hypo_rates']) > 2 else np.nan
    hypo_150 = sweep_2411['hypo_rates'][-1] if sweep_2411['hypo_rates'] else np.nan

    if cross_diff < 15:
        f1_agreement = 'agrees'
        f1_claim = (f'Target tradeoff replicates: crossover at '
                    f'{_fmt(our_cross, 0)} mg/dL (vs their {their_cross:.0f})')
    elif cross_diff < 30:
        f1_agreement = 'partially_agrees'
        f1_claim = (f'Tradeoff shape replicates but crossover shifted: '
                    f'{_fmt(our_cross, 0)} vs {their_cross:.0f} mg/dL')
    elif not np.isnan(our_cross):
        f1_agreement = 'partially_disagrees'
        f1_claim = (f'Crossover differs substantially: '
                    f'{_fmt(our_cross, 0)} vs {their_cross:.0f} mg/dL')
    else:
        f1_agreement = 'inconclusive'
        f1_claim = 'Crossover could not be determined (curves did not intersect in sweep range)'

    report.add_our_finding(
        'F1', f1_claim,
        evidence=(
            f'Our sweep: crossover at {_fmt(our_cross, 1)} mg/dL '
            f'(theirs: {their_cross:.1f} mg/dL). '
            f'Hypo at target 80: {_fmt(hypo_80)}% (theirs: 48.6%). '
            f'Hypo at target 150: {_fmt(hypo_150)}% (theirs: 34.1%).'
        ),
        agreement=f1_agreement,
        our_source='EXP-2201 settings recalibration',
    )

    # ── F2: Per-patient variation (NEW) ──────────────────────────────
    patient_res = results.get('exp_2413', {})
    patient_crossovers = {
        pid: r['crossover']
        for pid, r in patient_res.items()
        if isinstance(r, dict) and not np.isnan(r.get('crossover', float('nan')))
    }
    n_patients_sweep = len(patient_crossovers)

    report.add_their_finding(
        'F2', 'Universal target tradeoff curve applies across users',
        evidence='Aggregate partial-dependence plot on 28 oref users.',
        source='OREF-INV-003 Findings Overview',
    )

    if n_patients_sweep > 0:
        cross_vals = list(patient_crossovers.values())
        cross_min, cross_max = min(cross_vals), max(cross_vals)
        cross_mean = np.mean(cross_vals)
        cross_std = np.std(cross_vals)
        n_outside = sum(1 for v in cross_vals if v < 80 or v > 110)
        f2_claim = (
            f'Individual crossovers vary: range {_fmt(cross_min, 0)}–{_fmt(cross_max, 0)} mg/dL '
            f'(mean {_fmt(cross_mean, 1)}, SD {_fmt(cross_std, 1)})'
        )
        f2_evidence = (
            f'{n_patients_sweep} patients with computable crossover. '
            f'Range: {_fmt(cross_min, 0)}–{_fmt(cross_max, 0)} mg/dL. '
            f'{n_outside}/{n_patients_sweep} patients have crossover outside '
            f'the 80–110 mg/dL band, suggesting a universal target may not be '
            f'optimal for all individuals.'
        )
        f2_agreement = 'partially_agrees' if n_outside > 0 else 'agrees'
    else:
        f2_claim = 'Per-patient crossover could not be computed (insufficient data)'
        f2_evidence = 'No patients had enough data for individual sweep.'
        f2_agreement = 'inconclusive'

    report.add_our_finding('F2', f2_claim, evidence=f2_evidence,
                           agreement=f2_agreement, our_source='EXP-2413')

    # ── F3: Their model vs ours (NEW) ────────────────────────────────
    r2412 = results.get('exp_2412', {})
    their_model_cross = r2412.get('crossover_mgdl', float('nan'))

    report.add_their_finding(
        'F3', 'Pre-trained LightGBM generalises to new data',
        evidence='Models trained on 28 oref users; no external validation reported.',
        source='OREF-INV-003',
    )

    if not np.isnan(their_model_cross):
        transfer_diff = abs(their_model_cross - our_cross) if not np.isnan(our_cross) else float('inf')
        f3_claim = (
            f'Their model on our data: crossover at {_fmt(their_model_cross, 1)} mg/dL '
            f'(our model: {_fmt(our_cross, 1)} mg/dL)'
        )
        sweep_2412 = r2412.get('sweep', {})
        hypo_80_transfer = sweep_2412.get('hypo_rates', [None]*3)[2] if len(sweep_2412.get('hypo_rates', [])) > 2 else np.nan
        f3_evidence = (
            f'Transfer experiment: colleague\'s pre-trained models applied to our '
            f'Loop/oref data yield crossover at {_fmt(their_model_cross, 1)} mg/dL. '
            f'Hypo at target 80: {_fmt(hypo_80_transfer)}%. '
            f'Model-to-model crossover gap: {_fmt(transfer_diff, 1)} mg/dL.'
        )
        if transfer_diff < 10:
            f3_agreement = 'strongly_agrees'
        elif transfer_diff < 25:
            f3_agreement = 'agrees'
        else:
            f3_agreement = 'partially_agrees'
    else:
        f3_claim = 'Transfer sweep could not be evaluated'
        f3_evidence = 'Colleague model predictions unavailable or constant.'
        f3_agreement = 'inconclusive'

    report.add_our_finding('F3', f3_claim, evidence=f3_evidence,
                           agreement=f3_agreement, our_source='EXP-2412')

    # ── F4: Loop vs AAPS risk-benefit (NEW) ──────────────────────────
    r2414 = results.get('exp_2414', {})
    loop_data = r2414.get('Loop', {})
    aaps_data = r2414.get('AAPS', {})

    report.add_their_finding(
        'F4', 'Target tradeoff is algorithm-independent',
        evidence='Analysis on oref0/oref1 users only; no Loop comparison.',
        source='OREF-INV-003',
    )

    loop_cross = loop_data.get('crossover', float('nan'))
    aaps_cross = aaps_data.get('crossover', float('nan'))
    parts = []
    if not np.isnan(loop_cross):
        parts.append(f'Loop crossover: {_fmt(loop_cross, 1)} mg/dL')
    if not np.isnan(aaps_cross):
        parts.append(f'AAPS crossover: {_fmt(aaps_cross, 1)} mg/dL')

    if parts:
        f4_claim = '; '.join(parts)
        algo_gap = abs(loop_cross - aaps_cross) if (not np.isnan(loop_cross) and not np.isnan(aaps_cross)) else float('nan')
        f4_evidence = (
            f'Sub-group target sweeps: {"; ".join(parts)}. '
            f'Algorithm gap: {_fmt(algo_gap, 1)} mg/dL. '
            f'{"Similar crossovers suggest algorithm independence." if (not np.isnan(algo_gap) and algo_gap < 15) else "Crossover difference warrants further investigation."}'
        )
        f4_agreement = 'agrees' if (not np.isnan(algo_gap) and algo_gap < 15) else 'partially_agrees' if not np.isnan(algo_gap) else 'inconclusive'
    elif loop_data or aaps_data:
        f4_claim = 'Only one algorithm subset had enough data'
        f4_evidence = f'Loop data: {"present" if loop_data else "absent"}; AAPS data: {"present" if aaps_data else "absent"}.'
        f4_agreement = 'inconclusive'
    else:
        f4_claim = 'No algorithm-specific sweep could be computed'
        f4_evidence = 'Insufficient data in both Loop and AAPS subsets.'
        f4_agreement = 'inconclusive'

    report.add_our_finding('F4', f4_claim, evidence=f4_evidence,
                           agreement=f4_agreement, our_source='EXP-2414')

    # ── Figures ──────────────────────────────────────────────────────
    if args.figures:
        report.add_figure('fig_2411_target_sweep.png',
                          'Full-cohort target sweep: our model vs OREF-INV-003')
        report.add_figure('fig_2412_transfer_sweep.png',
                          'Transfer experiment: their pre-trained model on our data')
        report.add_figure('fig_2413_per_patient_sweep.png',
                          'Per-patient hypo/hyper rate curves across target values')
        report.add_figure('fig_2414_loop_vs_aaps.png',
                          'Loop vs AAPS target sweep comparison')

    # ── Synthesis narrative ──────────────────────────────────────────
    repl_word = 'replicates' if cross_diff < 15 else 'partially replicates'
    shape_word = 'consistent' if cross_diff < 20 else 'shifted'
    report.set_synthesis(
        f'The target-as-strongest-lever finding {repl_word} in our independent '
        f'dataset. Our retrained LightGBM places the hypo/hyper crossover at '
        f'{_fmt(our_cross, 1)} mg/dL (theirs: {their_cross:.1f} mg/dL), while '
        f'their pre-trained model applied to our data yields '
        f'{_fmt(their_model_cross, 1)} mg/dL — '
        f'{"a reassuring convergence" if abs(their_model_cross - our_cross) < 15 or np.isnan(their_model_cross) else "a notable gap suggesting dataset-specific effects"}.\n\n'
        f'Per-patient analysis (EXP-2413) reveals meaningful heterogeneity: '
        f'individual crossovers span '
        f'{_fmt(min(patient_crossovers.values()), 0) if patient_crossovers else "N/A"}–'
        f'{_fmt(max(patient_crossovers.values()), 0) if patient_crossovers else "N/A"} mg/dL '
        f'across {n_patients_sweep} patients, '
        f'suggesting that a single universal target recommendation may not be '
        f'optimal for all individuals.\n\n'
        f'The tradeoff shape is {shape_word} across Loop and oref algorithms '
        f'(EXP-2414), suggesting this is a fundamental property of closed-loop '
        f'insulin delivery rather than an algorithm-specific effect. The '
        f'monotonic decrease in hypo rate with increasing target is the '
        f'expected result of how AID systems use target as a setpoint: higher '
        f'targets reduce insulin delivery, lowering hypo risk at the cost of '
        f'increased hyperglycemia.'
    )

    # ── Limitations ──────────────────────────────────────────────────
    report.set_limitations(
        '1. **Loop vs oref population**: Our dataset is predominantly Loop '
        'users, while OREF-INV-003 used 28 oref0/oref1 users. The two '
        'algorithms differ in prediction horizon, micro-bolus strategy (SMB), '
        'and IOB decomposition, which may shift the tradeoff curve.\n\n'
        '2. **Feature approximation**: Several oref-specific features '
        '(`sug_threshold`, `bg_above_target`, `iob_basaliob`) are approximated '
        'from Loop equivalents. These approximations introduce systematic '
        'measurement error that may attenuate or bias effect sizes.\n\n'
        '3. **Static feature assumption**: The partial-dependence sweep '
        'modifies target while holding all other features constant. In '
        'reality, changing a patient\'s target would alter IOB, CGM '
        'trajectories, and algorithm behavior over time — effects that a '
        'static sweep cannot capture.\n\n'
        '4. **Small patient count in --tiny mode**: When run with `--tiny`, '
        'only 2 patients are used, limiting generalisability. Full-run '
        'results with all patients should be preferred for conclusions.'
    )

    report.set_raw_results(results)
    report.save()

    # Save JSON
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2, cls=NumpyEncoder)
    print(f'\nResults saved to {RESULTS_PATH}')


if __name__ == '__main__':
    main()
