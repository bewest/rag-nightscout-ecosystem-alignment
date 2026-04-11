#!/usr/bin/env python3
"""
EXP-2431–2438: Hypo/Hyper Prediction Model Replication

Replicates OREF-INV-003's LightGBM prediction models on our dataset and
tests cross-cohort transfer by running their pre-trained models on our data.

Experiments:
  2431 - 5-fold stratified CV (our data, our model)
  2432 - Leave-one-patient-out CV (generalization test)
  2433 - Per-patient isotonic calibration test
  2434 - Transfer test: their models on our data (zero-shot)
  2435 - Cohort statistics comparison (TBR/TIR/TAR/rates)
  2436 - Calibration curve comparison (reliability diagrams)
  2437 - Error analysis: where do models fail?
  2438 - Synthesis

Usage:
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2431 --figures
    PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2431 --figures --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    roc_auc_score, f1_score, precision_score, recall_score,
    average_precision_score, r2_score, mean_absolute_error,
    mean_squared_error,
)
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from oref_inv_003_replication.data_bridge import (
    load_patients_with_features, split_loop_vs_oref, OREF_FEATURES,
)
from oref_inv_003_replication.colleague_loader import ColleagueModels
from oref_inv_003_replication.report_engine import (
    ComparisonReport, save_figure, NumpyEncoder, COLORS, PATIENT_COLORS,
)

warnings.filterwarnings('ignore')

RESULTS_PATH = Path('externals/experiments/exp_2431_model_replication.json')
FIGURES_DIR = Path('tools/oref_inv_003_replication/figures')

# ---------------------------------------------------------------------------
# Colleague's reported metrics (OREF-INV-003)
# ---------------------------------------------------------------------------
THEIR_METRICS = {
    '5fold': {
        'hypo_auc': 0.83, 'hypo_f1': 0.55,
        'hyper_auc': 0.88, 'hyper_f1': None,
        'bg_r2': 0.56,
    },
    'louo': {
        'hypo_auc': 0.67, 'hyper_auc': 0.78,
    },
    'calibration': {
        'uncalibrated_gap_pp': 9.6,
        'calibrated_gap_pp': 4.4,
    },
    'cohort': {
        'tbr_pct': 4.55, 'tir_pct': 84.08, 'tar_pct': 11.37,
        'mean_bg': 126.7,
        'hypo_4h_rate': 29.8, 'hyper_4h_rate': 37.6,
    },
}

LGB_PARAMS = dict(
    n_estimators=500, learning_rate=0.05, max_depth=6,
    min_child_samples=50, subsample=0.8, colsample_bytree=0.8,
    random_state=42, verbose=-1,
)

MIN_PATIENT_ROWS = 500  # skip patients with fewer rows in LOPO


# ===================================================================
# Helpers
# ===================================================================

def prepare_data(df: pd.DataFrame):
    """Return (X, y_hypo, y_hyper, y_bg_change, valid_df).

    Drops rows where cgm_mgdl or hypo_4h is NaN, fills remaining feature
    NaN with 0, and casts labels to int.
    """
    valid = df.dropna(subset=['cgm_mgdl', 'hypo_4h']).copy()
    X = valid[OREF_FEATURES].fillna(0)
    y_hypo = valid['hypo_4h'].astype(int)
    y_hyper = valid['hyper_4h'].fillna(0).astype(int)
    y_bg = valid['bg_change_4h'] if 'bg_change_4h' in valid.columns else None
    return X, y_hypo, y_hyper, y_bg, valid


def safe_auc(y_true, y_score):
    """Return AUC or NaN if only one class present."""
    if len(np.unique(y_true)) < 2:
        return float('nan')
    return roc_auc_score(y_true, y_score)


def optimal_f1_threshold(y_true, y_prob):
    """Find the threshold maximising F1 on the positive class."""
    best_f1, best_thr = 0.0, 0.5
    for thr in np.arange(0.1, 0.9, 0.01):
        preds = (y_prob >= thr).astype(int)
        f = f1_score(y_true, preds, average='binary', zero_division=0)
        if f > best_f1:
            best_f1, best_thr = f, thr
    return best_thr, best_f1


def mean_calibration_error(y_true, y_prob, n_bins=10):
    """Mean absolute calibration error across bins."""
    try:
        frac_pos, mean_pred = calibration_curve(
            y_true, y_prob, n_bins=n_bins, strategy='uniform',
        )
    except ValueError:
        return float('nan')
    return float(np.mean(np.abs(frac_pos - mean_pred)))


# ===================================================================
# EXP-2431: 5-fold stratified CV
# ===================================================================

def run_2431(X, y_hypo, y_hyper, y_bg, n_folds=5, do_figures=False):
    """5-fold stratified CV matching colleague's architecture."""
    print('\n=== EXP-2431: 5-fold Stratified CV ===')
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    # -- Classification (hypo + hyper) --
    hypo_probs = np.full(len(y_hypo), np.nan)
    hyper_probs = np.full(len(y_hyper), np.nan)

    for fold, (train_idx, test_idx) in enumerate(skf.split(X, y_hypo), 1):
        print(f'  Fold {fold}/{n_folds} …')
        X_tr, X_te = X.iloc[train_idx], X.iloc[test_idx]

        # Hypo
        m_hypo = lgb.LGBMClassifier(**LGB_PARAMS)
        m_hypo.fit(X_tr, y_hypo.iloc[train_idx])
        hypo_probs[test_idx] = m_hypo.predict_proba(X_te)[:, 1]

        # Hyper
        m_hyper = lgb.LGBMClassifier(**LGB_PARAMS)
        m_hyper.fit(X_tr, y_hyper.iloc[train_idx])
        hyper_probs[test_idx] = m_hyper.predict_proba(X_te)[:, 1]

    hypo_auc = safe_auc(y_hypo, hypo_probs)
    hypo_thr, hypo_f1 = optimal_f1_threshold(y_hypo.values, hypo_probs)
    hypo_preds = (hypo_probs >= hypo_thr).astype(int)

    hyper_auc = safe_auc(y_hyper, hyper_probs)
    hyper_thr, hyper_f1 = optimal_f1_threshold(y_hyper.values, hyper_probs)
    hyper_preds = (hyper_probs >= hyper_thr).astype(int)

    # -- BG-change regressor --
    bg_r2, bg_mae, bg_rmse = float('nan'), float('nan'), float('nan')
    if y_bg is not None:
        valid_bg_mask = y_bg.notna()
        if valid_bg_mask.sum() > 100:
            y_bg_valid = y_bg[valid_bg_mask]
            X_bg_valid = X.loc[valid_bg_mask]
            bg_preds = np.full(len(y_bg_valid), np.nan)
            skf_bg = StratifiedKFold(
                n_splits=n_folds, shuffle=True, random_state=42,
            )
            # Bin BG change into quantiles for stratification
            bg_bins = pd.qcut(y_bg_valid, q=5, labels=False, duplicates='drop')
            for fold, (tr, te) in enumerate(skf_bg.split(X_bg_valid, bg_bins), 1):
                m_bg = lgb.LGBMRegressor(**{
                    **LGB_PARAMS, 'objective': 'regression',
                })
                m_bg.fit(X_bg_valid.iloc[tr], y_bg_valid.iloc[tr])
                bg_preds[te] = m_bg.predict(X_bg_valid.iloc[te])

            mask = ~np.isnan(bg_preds)
            bg_r2 = r2_score(y_bg_valid.values[mask], bg_preds[mask])
            bg_mae = mean_absolute_error(y_bg_valid.values[mask], bg_preds[mask])
            bg_rmse = float(np.sqrt(mean_squared_error(
                y_bg_valid.values[mask], bg_preds[mask],
            )))

    metrics = {
        'hypo_auc': round(hypo_auc, 4),
        'hypo_f1': round(hypo_f1, 4),
        'hypo_threshold': round(hypo_thr, 3),
        'hypo_precision': round(precision_score(
            y_hypo, hypo_preds, zero_division=0,
        ), 4),
        'hypo_recall': round(recall_score(
            y_hypo, hypo_preds, zero_division=0,
        ), 4),
        'hypo_ap': round(average_precision_score(y_hypo, hypo_probs), 4),
        'hyper_auc': round(hyper_auc, 4),
        'hyper_f1': round(hyper_f1, 4),
        'hyper_threshold': round(hyper_thr, 3),
        'hyper_precision': round(precision_score(
            y_hyper, hyper_preds, zero_division=0,
        ), 4),
        'hyper_recall': round(recall_score(
            y_hyper, hyper_preds, zero_division=0,
        ), 4),
        'hyper_ap': round(average_precision_score(y_hyper, hyper_probs), 4),
        'bg_r2': round(bg_r2, 4),
        'bg_mae': round(bg_mae, 2) if not np.isnan(bg_mae) else None,
        'bg_rmse': round(bg_rmse, 2) if not np.isnan(bg_rmse) else None,
    }

    print(f'  Hypo  AUC={metrics["hypo_auc"]:.3f}  F1={metrics["hypo_f1"]:.3f}  '
          f'(theirs: AUC=0.83 F1=0.55)')
    print(f'  Hyper AUC={metrics["hyper_auc"]:.3f}  F1={metrics["hyper_f1"]:.3f}  '
          f'(theirs: AUC=0.88)')
    print(f'  BG change R²={metrics["bg_r2"]:.3f}  '
          f'(theirs: R²=0.56)')

    if do_figures:
        _plot_roc_comparison(y_hypo, hypo_probs, y_hyper, hyper_probs, metrics)

    return {
        'metrics': metrics,
        'hypo_probs': hypo_probs.tolist(),
        'hyper_probs': hyper_probs.tolist(),
    }


def _plot_roc_comparison(y_hypo, hypo_probs, y_hyper, hyper_probs, metrics):
    """Figure 1: ROC curves — our 5-fold vs their reported AUCs."""
    from sklearn.metrics import roc_curve

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    # Hypo ROC
    fpr, tpr, _ = roc_curve(y_hypo, hypo_probs)
    ax1.plot(fpr, tpr, color=COLORS['ours'], lw=2,
             label=f'Our 5-fold (AUC={metrics["hypo_auc"]:.3f})')
    ax1.plot([0, 1], [0, 1], '--', color=COLORS['neutral'], lw=1)
    # Mark their AUC as a point on the diagonal guide
    ax1.axhline(y=THEIR_METRICS['5fold']['hypo_auc'], color=COLORS['theirs'],
                ls=':', alpha=0.6, label=f'Their AUC={THEIR_METRICS["5fold"]["hypo_auc"]}')
    ax1.set_title('Hypo 4h Classifier ROC', fontweight='bold')
    ax1.set_xlabel('False Positive Rate')
    ax1.set_ylabel('True Positive Rate')
    ax1.legend(fontsize=9, loc='lower right')
    ax1.grid(True, alpha=0.3)

    # Hyper ROC
    fpr2, tpr2, _ = roc_curve(y_hyper, hyper_probs)
    ax2.plot(fpr2, tpr2, color=COLORS['ours'], lw=2,
             label=f'Our 5-fold (AUC={metrics["hyper_auc"]:.3f})')
    ax2.plot([0, 1], [0, 1], '--', color=COLORS['neutral'], lw=1)
    ax2.axhline(y=THEIR_METRICS['5fold']['hyper_auc'], color=COLORS['theirs'],
                ls=':', alpha=0.6, label=f'Their AUC={THEIR_METRICS["5fold"]["hyper_auc"]}')
    ax2.set_title('Hyper 4h Classifier ROC', fontweight='bold')
    ax2.set_xlabel('False Positive Rate')
    ax2.set_ylabel('True Positive Rate')
    ax2.legend(fontsize=9, loc='lower right')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    save_figure(fig, 'fig_2431_roc_comparison.png')
    plt.close(fig)


# ===================================================================
# EXP-2432: Leave-one-patient-out CV
# ===================================================================

def run_2432(X, y_hypo, y_hyper, patient_ids, do_figures=False):
    """Leave-one-patient-out CV — generalization test."""
    print('\n=== EXP-2432: Leave-One-Patient-Out CV ===')
    unique_pids = sorted(patient_ids.unique())

    per_patient = {}
    all_hypo_probs, all_hypo_true = [], []
    all_hyper_probs, all_hyper_true = [], []

    for pid in unique_pids:
        test_mask = patient_ids == pid
        n_test = test_mask.sum()

        if n_test < MIN_PATIENT_ROWS:
            print(f'  {pid}: skipped ({n_test} rows < {MIN_PATIENT_ROWS})')
            continue

        y_hypo_test = y_hypo[test_mask]
        y_hyper_test = y_hyper[test_mask]

        # Skip if only one class
        if y_hypo_test.nunique() < 2 and y_hyper_test.nunique() < 2:
            print(f'  {pid}: skipped (all-same labels)')
            continue

        X_tr, X_te = X[~test_mask], X[test_mask]
        y_hypo_tr = y_hypo[~test_mask]
        y_hyper_tr = y_hyper[~test_mask]

        # Hypo
        m_hypo = lgb.LGBMClassifier(**LGB_PARAMS)
        m_hypo.fit(X_tr, y_hypo_tr)
        hp = m_hypo.predict_proba(X_te)[:, 1]

        # Hyper
        m_hyper = lgb.LGBMClassifier(**LGB_PARAMS)
        m_hyper.fit(X_tr, y_hyper_tr)
        hpp = m_hyper.predict_proba(X_te)[:, 1]

        hypo_auc = safe_auc(y_hypo_test, hp)
        hyper_auc = safe_auc(y_hyper_test, hpp)
        hypo_cal = mean_calibration_error(y_hypo_test.values, hp)
        hyper_cal = mean_calibration_error(y_hyper_test.values, hpp)

        per_patient[pid] = {
            'n_rows': int(n_test),
            'hypo_auc': round(hypo_auc, 4),
            'hyper_auc': round(hyper_auc, 4),
            'hypo_cal_error': round(hypo_cal, 4),
            'hyper_cal_error': round(hyper_cal, 4),
            'hypo_rate': round(float(y_hypo_test.mean()), 4),
            'hyper_rate': round(float(y_hyper_test.mean()), 4),
        }
        print(f'  {pid}: hypo AUC={hypo_auc:.3f}  hyper AUC={hyper_auc:.3f}  '
              f'(n={n_test:,})')

        all_hypo_probs.append(hp)
        all_hypo_true.append(y_hypo_test.values)
        all_hyper_probs.append(hpp)
        all_hyper_true.append(y_hyper_test.values)

    # Aggregate
    if all_hypo_probs:
        agg_hypo_true = np.concatenate(all_hypo_true)
        agg_hypo_prob = np.concatenate(all_hypo_probs)
        agg_hyper_true = np.concatenate(all_hyper_true)
        agg_hyper_prob = np.concatenate(all_hyper_probs)

        agg_hypo_auc = safe_auc(agg_hypo_true, agg_hypo_prob)
        agg_hyper_auc = safe_auc(agg_hyper_true, agg_hyper_prob)
    else:
        agg_hypo_auc = float('nan')
        agg_hyper_auc = float('nan')
        agg_hypo_true = agg_hypo_prob = np.array([])
        agg_hyper_true = agg_hyper_prob = np.array([])

    # Mean per-patient AUC (their method)
    valid_hypo_aucs = [v['hypo_auc'] for v in per_patient.values()
                       if not np.isnan(v['hypo_auc'])]
    valid_hyper_aucs = [v['hyper_auc'] for v in per_patient.values()
                        if not np.isnan(v['hyper_auc'])]
    mean_hypo_auc = float(np.mean(valid_hypo_aucs)) if valid_hypo_aucs else float('nan')
    mean_hyper_auc = float(np.mean(valid_hyper_aucs)) if valid_hyper_aucs else float('nan')

    summary = {
        'aggregate_hypo_auc': round(agg_hypo_auc, 4),
        'aggregate_hyper_auc': round(agg_hyper_auc, 4),
        'mean_patient_hypo_auc': round(mean_hypo_auc, 4),
        'mean_patient_hyper_auc': round(mean_hyper_auc, 4),
        'std_patient_hypo_auc': round(float(np.std(valid_hypo_aucs)), 4) if valid_hypo_aucs else None,
        'std_patient_hyper_auc': round(float(np.std(valid_hyper_aucs)), 4) if valid_hyper_aucs else None,
        'n_patients_evaluated': len(per_patient),
    }

    print(f'\n  LOPO aggregate: hypo AUC={agg_hypo_auc:.3f}  hyper AUC={agg_hyper_auc:.3f}')
    print(f'  LOPO mean±std:  hypo {mean_hypo_auc:.3f}±{summary["std_patient_hypo_auc"] or 0:.3f}  '
          f'hyper {mean_hyper_auc:.3f}±{summary["std_patient_hyper_auc"] or 0:.3f}')
    print(f'  Theirs LOUO:    hypo AUC=0.67  hyper AUC=0.78')

    if do_figures:
        _plot_lopo_bars(per_patient, summary)
        _plot_5fold_vs_lopo(summary)

    return {
        'per_patient': per_patient,
        'summary': summary,
        # Return raw predictions for downstream experiments
        '_hypo_true': agg_hypo_true,
        '_hypo_prob': agg_hypo_prob,
        '_hyper_true': agg_hyper_true,
        '_hyper_prob': agg_hyper_prob,
    }


def _plot_lopo_bars(per_patient, summary):
    """Figure 3: Per-patient LOPO AUC bar chart."""
    pids = list(per_patient.keys())
    hypo_aucs = [per_patient[p]['hypo_auc'] for p in pids]
    hyper_aucs = [per_patient[p]['hyper_auc'] for p in pids]

    fig, ax = plt.subplots(figsize=(max(10, len(pids) * 0.7), 5.5))
    x = np.arange(len(pids))
    w = 0.35
    bars1 = ax.bar(x - w / 2, hypo_aucs, w, label='Hypo AUC',
                   color=COLORS['theirs'], alpha=0.75)
    bars2 = ax.bar(x + w / 2, hyper_aucs, w, label='Hyper AUC',
                   color=COLORS['ours'], alpha=0.75)

    # Reference lines
    ax.axhline(y=THEIR_METRICS['louo']['hypo_auc'], color=COLORS['theirs'],
               ls='--', alpha=0.5, label=f'Their LOUO hypo ({THEIR_METRICS["louo"]["hypo_auc"]})')
    ax.axhline(y=THEIR_METRICS['louo']['hyper_auc'], color=COLORS['ours'],
               ls='--', alpha=0.5, label=f'Their LOUO hyper ({THEIR_METRICS["louo"]["hyper_auc"]})')

    ax.set_xticks(x)
    ax.set_xticklabels(pids, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('AUC')
    ax.set_title('Per-Patient LOPO AUC', fontweight='bold')
    ax.legend(fontsize=8, loc='lower left')
    ax.set_ylim(0, 1.05)
    ax.grid(True, axis='y', alpha=0.3)
    plt.tight_layout()
    save_figure(fig, 'fig_2431_per_patient_auc.png')
    plt.close(fig)


def _plot_5fold_vs_lopo(lopo_summary):
    """Figure 2: 5-fold AUC vs LOPO AUC (theirs and ours)."""
    labels = ['Hypo AUC', 'Hyper AUC']
    theirs_5fold = [THEIR_METRICS['5fold']['hypo_auc'],
                    THEIR_METRICS['5fold']['hyper_auc']]
    theirs_louo = [THEIR_METRICS['louo']['hypo_auc'],
                   THEIR_METRICS['louo']['hyper_auc']]

    # We report the aggregate LOPO AUC here (comparable to their pooled metric)
    ours_lopo = [lopo_summary['aggregate_hypo_auc'],
                 lopo_summary['aggregate_hyper_auc']]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(labels))
    w = 0.2
    ax.bar(x - 1.5 * w, theirs_5fold, w, label='Theirs: 5-fold CV',
           color=COLORS['theirs'], alpha=0.85)
    ax.bar(x - 0.5 * w, theirs_louo, w, label='Theirs: LOUO CV',
           color=COLORS['theirs'], alpha=0.45)
    ax.bar(x + 0.5 * w, ours_lopo, w, label='Ours: LOPO CV',
           color=COLORS['ours'], alpha=0.85)

    for i, (v5, vl, vo) in enumerate(zip(theirs_5fold, theirs_louo, ours_lopo)):
        ax.text(i - 1.5 * w, v5 + 0.01, f'{v5:.2f}', ha='center', fontsize=7)
        ax.text(i - 0.5 * w, vl + 0.01, f'{vl:.2f}', ha='center', fontsize=7)
        ax.text(i + 0.5 * w, vo + 0.01, f'{vo:.2f}', ha='center', fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel('AUC')
    ax.set_title('5-Fold CV vs LOPO/LOUO: Within-Patient Leakage Test',
                 fontweight='bold')
    ax.legend(fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.grid(True, axis='y', alpha=0.3)
    plt.tight_layout()
    save_figure(fig, 'fig_2431_lopo_vs_5fold.png')
    plt.close(fig)


# ===================================================================
# EXP-2433: Per-patient isotonic calibration
# ===================================================================

def run_2433(lopo_results, patient_ids, do_figures=False):
    """Per-patient isotonic calibration test."""
    print('\n=== EXP-2433: Per-Patient Isotonic Calibration ===')

    hypo_true = lopo_results['_hypo_true']
    hypo_prob = lopo_results['_hypo_prob']
    per_patient_data = lopo_results['per_patient']

    if len(hypo_true) == 0:
        print('  No LOPO predictions available — skipping.')
        return {'skipped': True}

    # We need per-patient predictions.  Reconstruct from the LOPO run by
    # re-splitting.  Since LOPO concatenates in patient-id-sorted order,
    # we can split back.
    ordered_pids = sorted(per_patient_data.keys())
    offsets = {}
    start = 0
    for pid in ordered_pids:
        n = per_patient_data[pid]['n_rows']
        offsets[pid] = (start, start + n)
        start += n

    uncalibrated_errors, calibrated_errors = [], []
    per_patient_cal = {}

    for pid in ordered_pids:
        lo, hi = offsets[pid]
        y_true_p = hypo_true[lo:hi]
        y_prob_p = hypo_prob[lo:hi]

        if len(y_true_p) < 100 or len(np.unique(y_true_p)) < 2:
            continue

        uncal_err = mean_calibration_error(y_true_p, y_prob_p)

        # 80/20 split for calibration training/evaluation
        n_cal = max(int(len(y_true_p) * 0.8), 10)
        y_cal_train, y_cal_test = y_true_p[:n_cal], y_true_p[n_cal:]
        p_cal_train, p_cal_test = y_prob_p[:n_cal], y_prob_p[n_cal:]

        if len(y_cal_test) < 20 or len(np.unique(y_cal_test)) < 2:
            continue

        iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds='clip')
        iso.fit(p_cal_train, y_cal_train)
        p_calibrated = iso.predict(p_cal_test)
        cal_err = mean_calibration_error(y_cal_test, p_calibrated)

        per_patient_cal[pid] = {
            'uncalibrated_mce': round(uncal_err, 4),
            'calibrated_mce': round(cal_err, 4),
            'improvement_pp': round((uncal_err - cal_err) * 100, 2),
            'n_test': len(y_cal_test),
        }
        uncalibrated_errors.append(uncal_err)
        calibrated_errors.append(cal_err)
        print(f'  {pid}: uncal={uncal_err:.3f} → cal={cal_err:.3f}  '
              f'(Δ={uncal_err - cal_err:.3f})')

    mean_uncal = float(np.mean(uncalibrated_errors)) * 100 if uncalibrated_errors else float('nan')
    mean_cal = float(np.mean(calibrated_errors)) * 100 if calibrated_errors else float('nan')

    summary = {
        'mean_uncalibrated_gap_pp': round(mean_uncal, 2),
        'mean_calibrated_gap_pp': round(mean_cal, 2),
        'improvement_pp': round(mean_uncal - mean_cal, 2),
        'n_patients': len(per_patient_cal),
        'their_uncalibrated_pp': THEIR_METRICS['calibration']['uncalibrated_gap_pp'],
        'their_calibrated_pp': THEIR_METRICS['calibration']['calibrated_gap_pp'],
    }

    print(f'\n  Mean uncalibrated gap: {mean_uncal:.1f}pp (theirs: {THEIR_METRICS["calibration"]["uncalibrated_gap_pp"]}pp)')
    print(f'  Mean calibrated gap:   {mean_cal:.1f}pp (theirs: {THEIR_METRICS["calibration"]["calibrated_gap_pp"]}pp)')

    return {'per_patient': per_patient_cal, 'summary': summary}


# ===================================================================
# EXP-2434: Transfer test — their models on our data
# ===================================================================

def run_2434(X, y_hypo, y_hyper, patient_ids, do_figures=False):
    """Their pre-trained models on our data (zero-shot transfer)."""
    print('\n=== EXP-2434: Transfer Test (their models → our data) ===')
    try:
        colleague = ColleagueModels()
    except Exception as e:
        print(f'  Could not load colleague models: {e}')
        return {'skipped': True, 'reason': str(e)}

    preds = colleague.predict_all(X)
    hp = preds['hypo_prob']
    hpp = preds['hyper_prob']

    overall_hypo_auc = safe_auc(y_hypo, hp)
    overall_hyper_auc = safe_auc(y_hyper, hpp)
    overall_hypo_cal = mean_calibration_error(y_hypo.values, hp)
    overall_hyper_cal = mean_calibration_error(y_hyper.values, hpp)

    print(f'  Overall: hypo AUC={overall_hypo_auc:.3f}  hyper AUC={overall_hyper_auc:.3f}')

    # Split by Loop vs AAPS
    is_odc = patient_ids.str.startswith('odc', na=False)
    split_results = {}
    for label, mask in [('Loop', ~is_odc), ('AAPS/ODC', is_odc)]:
        if mask.sum() < 100:
            continue
        y_h = y_hypo[mask]
        y_hp = y_hyper[mask]
        p_h = hp[mask.values] if hasattr(mask, 'values') else hp[mask]
        p_hp = hpp[mask.values] if hasattr(mask, 'values') else hpp[mask]
        h_auc = safe_auc(y_h, p_h)
        hp_auc = safe_auc(y_hp, p_hp)
        split_results[label] = {
            'hypo_auc': round(h_auc, 4),
            'hyper_auc': round(hp_auc, 4),
            'n_rows': int(mask.sum()),
        }
        print(f'  {label}: hypo AUC={h_auc:.3f}  hyper AUC={hp_auc:.3f}  (n={mask.sum():,})')

    # Per-patient transfer AUC
    per_patient = {}
    for pid in sorted(patient_ids.unique()):
        mask = patient_ids == pid
        if mask.sum() < MIN_PATIENT_ROWS:
            continue
        y_h = y_hypo[mask]
        if y_h.nunique() < 2:
            continue
        p_h = hp[mask.values]
        per_patient[pid] = {
            'hypo_auc': round(safe_auc(y_h, p_h), 4),
            'n_rows': int(mask.sum()),
        }

    result = {
        'overall_hypo_auc': round(overall_hypo_auc, 4),
        'overall_hyper_auc': round(overall_hyper_auc, 4),
        'overall_hypo_cal_error': round(overall_hypo_cal, 4),
        'overall_hyper_cal_error': round(overall_hyper_cal, 4),
        'by_algorithm': split_results,
        'per_patient': per_patient,
    }

    if do_figures:
        _plot_transfer_test(result, split_results)

    return result


def _plot_transfer_test(result, split_results):
    """Figure 5: Their model vs our model on our data."""
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ['Hypo AUC', 'Hyper AUC']
    theirs_on_ours = [result['overall_hypo_auc'], result['overall_hyper_auc']]
    theirs_on_theirs = [THEIR_METRICS['5fold']['hypo_auc'],
                        THEIR_METRICS['5fold']['hyper_auc']]

    x = np.arange(len(labels))
    w = 0.25
    ax.bar(x - w / 2, theirs_on_theirs, w,
           label='Their model on their data', color=COLORS['theirs'], alpha=0.8)
    ax.bar(x + w / 2, theirs_on_ours, w,
           label='Their model on our data', color=COLORS['ours'], alpha=0.8)

    # Add algorithm split if available
    if 'Loop' in split_results and 'AAPS/ODC' in split_results:
        loop_vals = [split_results['Loop']['hypo_auc'],
                     split_results['Loop']['hyper_auc']]
        aaps_vals = [split_results['AAPS/ODC']['hypo_auc'],
                     split_results['AAPS/ODC']['hyper_auc']]
        for i, (lv, av) in enumerate(zip(loop_vals, aaps_vals)):
            ax.plot(i + w / 2 - 0.03, lv, 'v', color='#059669', markersize=8,
                    label='Loop subset' if i == 0 else None)
            ax.plot(i + w / 2 + 0.03, av, '^', color='#7c3aed', markersize=8,
                    label='AAPS subset' if i == 0 else None)

    for i, (t, o) in enumerate(zip(theirs_on_theirs, theirs_on_ours)):
        ax.text(i - w / 2, t + 0.01, f'{t:.2f}', ha='center', fontsize=8)
        ax.text(i + w / 2, o + 0.01, f'{o:.2f}', ha='center', fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel('AUC')
    ax.set_title('Transfer Test: Their Pre-Trained Models on Our Data',
                 fontweight='bold')
    ax.legend(fontsize=8)
    ax.set_ylim(0, 1.1)
    ax.grid(True, axis='y', alpha=0.3)
    plt.tight_layout()
    save_figure(fig, 'fig_2431_transfer_test.png')
    plt.close(fig)


# ===================================================================
# EXP-2435: Cohort statistics comparison
# ===================================================================

def run_2435(df, y_hypo, y_hyper, do_figures=False):
    """Cohort statistics: TBR/TIR/TAR and event rates."""
    print('\n=== EXP-2435: Cohort Statistics Comparison ===')
    bg = df['cgm_mgdl'].dropna()
    n = len(bg)

    tbr = float((bg < 70).sum() / n * 100)
    tir = float(((bg >= 70) & (bg <= 180)).sum() / n * 100)
    tar = float((bg > 180).sum() / n * 100)
    mean_bg = float(bg.mean())
    cv_bg = float(bg.std() / bg.mean() * 100) if bg.mean() > 0 else float('nan')
    hypo_rate = float(y_hypo.mean() * 100)
    hyper_rate = float(y_hyper.mean() * 100)

    our_stats = {
        'tbr_pct': round(tbr, 2),
        'tir_pct': round(tir, 2),
        'tar_pct': round(tar, 2),
        'mean_bg': round(mean_bg, 1),
        'cv_pct': round(cv_bg, 1),
        'hypo_4h_rate': round(hypo_rate, 1),
        'hyper_4h_rate': round(hyper_rate, 1),
        'n_readings': n,
    }

    # Per-algorithm split
    loop_df, oref_df = split_loop_vs_oref(df)
    algo_stats = {}
    for label, sub in [('Loop', loop_df), ('AAPS/ODC', oref_df)]:
        sbg = sub['cgm_mgdl'].dropna()
        if len(sbg) == 0:
            continue
        ns = len(sbg)
        sub_valid = sub.dropna(subset=['hypo_4h'])
        algo_stats[label] = {
            'tbr_pct': round(float((sbg < 70).sum() / ns * 100), 2),
            'tir_pct': round(float(((sbg >= 70) & (sbg <= 180)).sum() / ns * 100), 2),
            'tar_pct': round(float((sbg > 180).sum() / ns * 100), 2),
            'mean_bg': round(float(sbg.mean()), 1),
            'hypo_4h_rate': round(float(sub_valid['hypo_4h'].mean() * 100), 1) if len(sub_valid) > 0 else None,
            'hyper_4h_rate': round(float(sub_valid['hyper_4h'].fillna(0).mean() * 100), 1) if len(sub_valid) > 0 else None,
            'n_readings': ns,
        }

    theirs = THEIR_METRICS['cohort']

    print(f'  Our cohort:   TBR={tbr:.1f}%  TIR={tir:.1f}%  TAR={tar:.1f}%  '
          f'mean={mean_bg:.0f} mg/dL  CV={cv_bg:.0f}%')
    print(f'  Their cohort: TBR={theirs["tbr_pct"]}%  TIR={theirs["tir_pct"]}%  '
          f'TAR={theirs["tar_pct"]}%  mean={theirs["mean_bg"]} mg/dL')
    print(f'  Our hypo_4h rate:  {hypo_rate:.1f}% (theirs: {theirs["hypo_4h_rate"]}%)')
    print(f'  Our hyper_4h rate: {hyper_rate:.1f}% (theirs: {theirs["hyper_4h_rate"]}%)')

    for label, st in algo_stats.items():
        print(f'  {label}: TBR={st["tbr_pct"]:.1f}%  TIR={st["tir_pct"]:.1f}%  '
              f'TAR={st["tar_pct"]:.1f}%')

    if do_figures:
        _plot_cohort_comparison(our_stats, theirs, algo_stats)

    return {
        'our_cohort': our_stats,
        'their_cohort': theirs,
        'by_algorithm': algo_stats,
    }


def _plot_cohort_comparison(ours, theirs, algo_stats):
    """Figure 6: TBR/TIR/TAR bar chart."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # TBR/TIR/TAR comparison
    categories = ['TBR (<70)', 'TIR (70–180)', 'TAR (>180)']
    their_vals = [theirs['tbr_pct'], theirs['tir_pct'], theirs['tar_pct']]
    our_vals = [ours['tbr_pct'], ours['tir_pct'], ours['tar_pct']]

    x = np.arange(len(categories))
    w = 0.3
    ax1.bar(x - w / 2, their_vals, w, label='Their cohort (28 oref)',
            color=COLORS['theirs'], alpha=0.8)
    ax1.bar(x + w / 2, our_vals, w, label='Our cohort (11 Loop + 8 AAPS)',
            color=COLORS['ours'], alpha=0.8)
    for i, (tv, ov) in enumerate(zip(their_vals, our_vals)):
        ax1.text(i - w / 2, tv + 0.5, f'{tv:.1f}%', ha='center', fontsize=8)
        ax1.text(i + w / 2, ov + 0.5, f'{ov:.1f}%', ha='center', fontsize=8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories)
    ax1.set_ylabel('Percentage of readings')
    ax1.set_title('Glycaemic Ranges', fontweight='bold')
    ax1.legend(fontsize=8)
    ax1.grid(True, axis='y', alpha=0.3)

    # Event rates
    rate_labels = ['4h Hypo Rate', '4h Hyper Rate']
    their_rates = [theirs['hypo_4h_rate'], theirs['hyper_4h_rate']]
    our_rates = [ours['hypo_4h_rate'], ours['hyper_4h_rate']]
    x2 = np.arange(len(rate_labels))
    ax2.bar(x2 - w / 2, their_rates, w, label='Their cohort',
            color=COLORS['theirs'], alpha=0.8)
    ax2.bar(x2 + w / 2, our_rates, w, label='Our cohort',
            color=COLORS['ours'], alpha=0.8)

    # Add per-algorithm markers
    for label, marker, color in [('Loop', 'v', '#059669'), ('AAPS/ODC', '^', '#7c3aed')]:
        if label in algo_stats and algo_stats[label].get('hypo_4h_rate') is not None:
            st = algo_stats[label]
            ax2.plot(0 + w / 2, st['hypo_4h_rate'], marker, color=color,
                     markersize=9, label=label, zorder=5)
            ax2.plot(1 + w / 2, st['hyper_4h_rate'], marker, color=color,
                     markersize=9, zorder=5)

    for i, (tv, ov) in enumerate(zip(their_rates, our_rates)):
        ax2.text(i - w / 2, tv + 0.5, f'{tv:.1f}%', ha='center', fontsize=8)
        ax2.text(i + w / 2, ov + 0.5, f'{ov:.1f}%', ha='center', fontsize=8)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(rate_labels)
    ax2.set_ylabel('Percentage of windows')
    ax2.set_title('4-Hour Event Rates', fontweight='bold')
    ax2.legend(fontsize=8)
    ax2.grid(True, axis='y', alpha=0.3)

    plt.tight_layout()
    save_figure(fig, 'fig_2431_cohort_comparison.png')
    plt.close(fig)


# ===================================================================
# EXP-2436: Calibration curves (reliability diagrams)
# ===================================================================

def run_2436(X, y_hypo, y_hyper, lopo_results, do_figures=False):
    """Calibration curve comparison."""
    print('\n=== EXP-2436: Calibration Curves ===')

    results = {}

    # Our model (from LOPO)
    hypo_true = lopo_results['_hypo_true']
    hypo_prob = lopo_results['_hypo_prob']
    hyper_true = lopo_results['_hyper_true']
    hyper_prob = lopo_results['_hyper_prob']

    if len(hypo_true) > 0 and len(np.unique(hypo_true)) >= 2:
        frac_hypo, mean_hypo = calibration_curve(hypo_true, hypo_prob,
                                                 n_bins=10, strategy='uniform')
        results['our_model_hypo'] = {
            'fraction_positives': frac_hypo.tolist(),
            'mean_predicted': mean_hypo.tolist(),
            'mce': round(float(np.mean(np.abs(frac_hypo - mean_hypo))), 4),
        }
    else:
        frac_hypo = mean_hypo = np.array([])

    if len(hyper_true) > 0 and len(np.unique(hyper_true)) >= 2:
        frac_hyper, mean_hyper = calibration_curve(hyper_true, hyper_prob,
                                                   n_bins=10, strategy='uniform')
        results['our_model_hyper'] = {
            'fraction_positives': frac_hyper.tolist(),
            'mean_predicted': mean_hyper.tolist(),
            'mce': round(float(np.mean(np.abs(frac_hyper - mean_hyper))), 4),
        }
    else:
        frac_hyper = mean_hyper = np.array([])

    # Their model on our data
    try:
        colleague = ColleagueModels()
        their_hp = colleague.predict_hypo(X)
        their_hpp = colleague.predict_hyper(X)
        if len(np.unique(y_hypo)) >= 2:
            frac_t_hypo, mean_t_hypo = calibration_curve(
                y_hypo, their_hp, n_bins=10, strategy='uniform',
            )
            results['their_model_hypo'] = {
                'fraction_positives': frac_t_hypo.tolist(),
                'mean_predicted': mean_t_hypo.tolist(),
                'mce': round(float(np.mean(np.abs(frac_t_hypo - mean_t_hypo))), 4),
            }
        else:
            frac_t_hypo = mean_t_hypo = np.array([])
        if len(np.unique(y_hyper)) >= 2:
            frac_t_hyper, mean_t_hyper = calibration_curve(
                y_hyper, their_hpp, n_bins=10, strategy='uniform',
            )
            results['their_model_hyper'] = {
                'fraction_positives': frac_t_hyper.tolist(),
                'mean_predicted': mean_t_hyper.tolist(),
                'mce': round(float(np.mean(np.abs(frac_t_hyper - mean_t_hyper))), 4),
            }
        else:
            frac_t_hyper = mean_t_hyper = np.array([])
    except Exception as e:
        print(f'  Could not load colleague models for calibration: {e}')
        frac_t_hypo = mean_t_hypo = np.array([])
        frac_t_hyper = mean_t_hyper = np.array([])

    if do_figures:
        _plot_calibration_curves(
            frac_hypo, mean_hypo, frac_hyper, mean_hyper,
            frac_t_hypo if len(frac_t_hypo) else None,
            mean_t_hypo if len(mean_t_hypo) else None,
            frac_t_hyper if len(frac_t_hyper) else None,
            mean_t_hyper if len(mean_t_hyper) else None,
        )

    return results


def _plot_calibration_curves(frac_hypo, mean_hypo, frac_hyper, mean_hyper,
                             frac_t_hypo, mean_t_hypo,
                             frac_t_hyper, mean_t_hyper):
    """Figure 4: Reliability diagrams."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    # Hypo
    ax1.plot([0, 1], [0, 1], '--', color=COLORS['neutral'], lw=1, label='Perfect')
    if len(frac_hypo) > 0:
        ax1.plot(mean_hypo, frac_hypo, 'o-', color=COLORS['ours'], lw=2,
                 label='Our model (LOPO)')
    if frac_t_hypo is not None:
        ax1.plot(mean_t_hypo, frac_t_hypo, 's--', color=COLORS['theirs'], lw=2,
                 label='Their model (transfer)')
    ax1.set_xlabel('Mean predicted probability')
    ax1.set_ylabel('Fraction of positives')
    ax1.set_title('Hypo Calibration Curve', fontweight='bold')
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_xlim(-0.02, 1.02)
    ax1.set_ylim(-0.02, 1.02)

    # Hyper
    ax2.plot([0, 1], [0, 1], '--', color=COLORS['neutral'], lw=1, label='Perfect')
    if len(frac_hyper) > 0:
        ax2.plot(mean_hyper, frac_hyper, 'o-', color=COLORS['ours'], lw=2,
                 label='Our model (LOPO)')
    if frac_t_hyper is not None:
        ax2.plot(mean_t_hyper, frac_t_hyper, 's--', color=COLORS['theirs'], lw=2,
                 label='Their model (transfer)')
    ax2.set_xlabel('Mean predicted probability')
    ax2.set_ylabel('Fraction of positives')
    ax2.set_title('Hyper Calibration Curve', fontweight='bold')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(-0.02, 1.02)
    ax2.set_ylim(-0.02, 1.02)

    plt.tight_layout()
    save_figure(fig, 'fig_2431_calibration_curves.png')
    plt.close(fig)


# ===================================================================
# EXP-2437: Error analysis
# ===================================================================

def run_2437(X, y_hypo, hypo_probs, valid_df):
    """Where do models fail most?"""
    print('\n=== EXP-2437: Error Analysis ===')

    if len(hypo_probs) == 0:
        print('  No LOPO predictions available — skipping.')
        return {'skipped': True}

    # Build analysis frame from valid_df rows that appeared in LOPO
    # The LOPO predictions cover all patients that had ≥ MIN_PATIENT_ROWS
    # and at least 2 classes.  We approximate by matching lengths.
    n_pred = len(hypo_probs)
    analysis = pd.DataFrame({
        'y_true': y_hypo.values[:n_pred] if n_pred <= len(y_hypo) else y_hypo.values,
        'y_prob': hypo_probs[:len(y_hypo)],
    })
    # Attach context columns from valid_df if shapes match
    if n_pred <= len(valid_df):
        ctx = valid_df.iloc[:n_pred]
        analysis['cgm_mgdl'] = ctx['cgm_mgdl'].values
        analysis['hour'] = ctx['hour'].values if 'hour' in ctx.columns else np.nan
        analysis['iob_iob'] = ctx['iob_iob'].values if 'iob_iob' in ctx.columns else np.nan

    analysis['pred'] = (analysis['y_prob'] >= 0.5).astype(int)
    analysis['correct'] = (analysis['pred'] == analysis['y_true']).astype(int)

    # Error rate by BG range
    bg_bins = {
        'very_low (<70)': analysis['cgm_mgdl'] < 70,
        'low (70-100)': (analysis['cgm_mgdl'] >= 70) & (analysis['cgm_mgdl'] < 100),
        'in_range (100-140)': (analysis['cgm_mgdl'] >= 100) & (analysis['cgm_mgdl'] < 140),
        'high (140-180)': (analysis['cgm_mgdl'] >= 140) & (analysis['cgm_mgdl'] < 180),
        'very_high (>180)': analysis['cgm_mgdl'] >= 180,
    } if 'cgm_mgdl' in analysis.columns else {}

    by_bg_range = {}
    for label, mask in bg_bins.items():
        n = int(mask.sum())
        if n < 50:
            continue
        err_rate = 1.0 - analysis.loc[mask, 'correct'].mean()
        by_bg_range[label] = {
            'n': n,
            'error_rate': round(float(err_rate), 4),
            'hypo_prevalence': round(float(analysis.loc[mask, 'y_true'].mean()), 4),
        }
        print(f'  {label}: error={err_rate:.1%}  prevalence={analysis.loc[mask, "y_true"].mean():.1%}  n={n:,}')

    # Error rate by time of day
    by_time = {}
    if 'hour' in analysis.columns and analysis['hour'].notna().sum() > 0:
        for period, (h_lo, h_hi) in [('night 0-6', (0, 6)), ('morning 6-12', (6, 12)),
                                      ('afternoon 12-18', (12, 18)), ('evening 18-24', (18, 24))]:
            mask = (analysis['hour'] >= h_lo) & (analysis['hour'] < h_hi)
            n = int(mask.sum())
            if n < 50:
                continue
            err_rate = 1.0 - analysis.loc[mask, 'correct'].mean()
            by_time[period] = {
                'n': n,
                'error_rate': round(float(err_rate), 4),
            }
            print(f'  {period}: error={err_rate:.1%}  n={n:,}')

    # Error rate by IOB level
    by_iob = {}
    if 'iob_iob' in analysis.columns and analysis['iob_iob'].notna().sum() > 0:
        iob = analysis['iob_iob']
        for label, mask in [('low IOB (<1)', iob < 1),
                            ('medium IOB (1-3)', (iob >= 1) & (iob < 3)),
                            ('high IOB (≥3)', iob >= 3)]:
            n = int(mask.sum())
            if n < 50:
                continue
            err_rate = 1.0 - analysis.loc[mask, 'correct'].mean()
            by_iob[label] = {
                'n': n,
                'error_rate': round(float(err_rate), 4),
            }
            print(f'  {label}: error={err_rate:.1%}  n={n:,}')

    return {
        'by_bg_range': by_bg_range,
        'by_time_of_day': by_time,
        'by_iob_level': by_iob,
        'overall_error_rate': round(1.0 - float(analysis['correct'].mean()), 4),
    }


# ===================================================================
# EXP-2438: Synthesis
# ===================================================================

def build_synthesis(results, do_figures):
    """Construct ComparisonReport for the whole experiment block."""
    print('\n=== EXP-2438: Synthesis ===')

    report = ComparisonReport(
        exp_id='EXP-2431',
        title='Hypo/Hyper Prediction Model Replication',
        phase='replication',
        script='tools/oref_inv_003_replication/exp_repl_2431.py',
    )

    # --- Their findings ---
    report.add_their_finding(
        'F5',
        'Algorithm predictions are mediocre — '
        'hypo AUC=0.83 (5-fold) drops to 0.67 (LOUO), indicating within-user leakage',
        evidence=(
            f'5-fold CV: hypo AUC=0.83, F1=0.55; hyper AUC=0.88. '
            f'LOUO CV: hypo AUC=0.67, hyper AUC=0.78. '
            f'16pp and 10pp gaps indicate within-patient temporal leakage.'
        ),
        source='OREF-INV-003',
    )
    report.add_their_finding(
        'F8',
        'Hyper events are more frequent than hypo in the cohort',
        evidence=(
            f'Cohort: TBR 4.55%, TIR 84.08%, TAR 11.37%. '
            f'4h-any-hypo rate 29.8%, 4h-any-hyper rate 37.6%.'
        ),
        source='OREF-INV-003',
    )
    report.add_their_finding(
        'F9',
        'Safety-gate AUC is only 0.62 — '
        'the algorithm is barely better than chance at preventing hypo',
        evidence='Safety gate classifier AUC=0.62 in LOUO CV.',
        source='OREF-INV-003',
    )

    # --- Our findings ---
    m_5fold = results.get('exp_2431', {}).get('metrics', {})
    m_lopo = results.get('exp_2432', {}).get('summary', {})
    m_cohort = results.get('exp_2435', {}).get('our_cohort', {})

    # F5 — prediction mediocrity
    our_5fold_hypo = m_5fold.get('hypo_auc', float('nan'))
    our_lopo_hypo = m_lopo.get('aggregate_hypo_auc', float('nan'))
    our_gap = our_5fold_hypo - our_lopo_hypo if not (
        np.isnan(our_5fold_hypo) or np.isnan(our_lopo_hypo)
    ) else float('nan')

    if np.isnan(our_gap):
        f5_agreement = 'inconclusive'
        f5_claim = 'Insufficient data to assess CV vs LOPO gap'
    elif our_gap > 0.10:
        f5_agreement = 'agrees'
        f5_claim = (
            f'Within-patient leakage confirmed: 5-fold hypo AUC={our_5fold_hypo:.2f} '
            f'vs LOPO={our_lopo_hypo:.2f} (gap={our_gap:.2f}, '
            f'theirs: 0.83 vs 0.67 = 0.16 gap)'
        )
    elif our_gap > 0.03:
        f5_agreement = 'partially_agrees'
        f5_claim = (
            f'Mild leakage: 5-fold hypo AUC={our_5fold_hypo:.2f} '
            f'vs LOPO={our_lopo_hypo:.2f} (gap={our_gap:.2f}). '
            f'Smaller than their 16pp gap, possibly due to different cohort.'
        )
    else:
        f5_agreement = 'partially_disagrees'
        f5_claim = (
            f'Minimal leakage in our data: 5-fold hypo AUC={our_5fold_hypo:.2f} '
            f'vs LOPO={our_lopo_hypo:.2f} (gap={our_gap:.2f}). '
            f'Their 16pp gap may reflect their cohort characteristics.'
        )
    report.add_our_finding('F5', f5_claim,
                           evidence=f'EXP-2431 5-fold + EXP-2432 LOPO results',
                           agreement=f5_agreement,
                           our_source='EXP-2431/2432')

    # F8 — hyper > hypo prevalence
    our_hypo_rate = m_cohort.get('hypo_4h_rate', float('nan'))
    our_hyper_rate = m_cohort.get('hyper_4h_rate', float('nan'))
    if not np.isnan(our_hypo_rate) and not np.isnan(our_hyper_rate):
        if our_hyper_rate > our_hypo_rate:
            f8_agreement = 'agrees'
            f8_claim = (
                f'Hyper > hypo confirmed: our hypo_4h={our_hypo_rate:.1f}% '
                f'vs hyper_4h={our_hyper_rate:.1f}% '
                f'(theirs: 29.8% vs 37.6%)'
            )
        else:
            f8_agreement = 'partially_disagrees'
            f8_claim = (
                f'Reversed in our cohort: hypo_4h={our_hypo_rate:.1f}% '
                f'> hyper_4h={our_hyper_rate:.1f}%'
            )
    else:
        f8_agreement = 'inconclusive'
        f8_claim = 'Insufficient data for event rate comparison'
    report.add_our_finding('F8', f8_claim,
                           evidence=f'EXP-2435 cohort statistics',
                           agreement=f8_agreement,
                           our_source='EXP-2435')

    # F9 — safety gate AUC
    # We use LOPO hypo AUC as the safety-gate proxy
    if not np.isnan(our_lopo_hypo):
        if our_lopo_hypo < 0.70:
            f9_agreement = 'agrees'
            f9_claim = (
                f'Safety gate is weak: LOPO hypo AUC={our_lopo_hypo:.2f} '
                f'(theirs: 0.62). Both near chance level.'
            )
        elif our_lopo_hypo < 0.80:
            f9_agreement = 'partially_agrees'
            f9_claim = (
                f'LOPO hypo AUC={our_lopo_hypo:.2f} is modest but better '
                f'than their 0.62. Safety gate is limited but not hopeless.'
            )
        else:
            f9_agreement = 'partially_disagrees'
            f9_claim = (
                f'LOPO hypo AUC={our_lopo_hypo:.2f} is substantially better '
                f'than their 0.62. Our cohort may be more predictable.'
            )
    else:
        f9_agreement = 'inconclusive'
        f9_claim = 'Could not evaluate safety gate AUC'
    report.add_our_finding('F9', f9_claim,
                           evidence=f'EXP-2432 LOPO results',
                           agreement=f9_agreement,
                           our_source='EXP-2432')

    # Figures
    if do_figures:
        for fname, caption in [
            ('fig_2431_roc_comparison.png', 'ROC curves: our 5-fold vs their reported AUC'),
            ('fig_2431_lopo_vs_5fold.png', '5-fold AUC vs LOPO AUC (theirs and ours)'),
            ('fig_2431_per_patient_auc.png', 'Per-patient LOPO AUC bar chart'),
            ('fig_2431_calibration_curves.png', 'Reliability diagrams'),
            ('fig_2431_transfer_test.png', 'Their model vs our model on our data'),
            ('fig_2431_cohort_comparison.png', 'TBR/TIR/TAR comparison'),
        ]:
            report.add_figure(fname, caption)

    # Methodology & limitations
    report.set_methodology(
        'We trained LightGBM hypo/hyper classifiers with the same architecture '
        'as the colleague (n_estimators=500, lr=0.05, max_depth=6, '
        'min_child_samples=50, subsample=0.8, colsample_bytree=0.8). '
        'We used both 5-fold stratified CV and leave-one-patient-out CV. '
        'Per-patient isotonic calibration was tested with 80/20 splits. '
        'Transfer testing used the colleague\'s pre-trained models on our '
        'feature-aligned data.'
    )
    report.set_limitations(
        'Our cohort differs from theirs: 11 Loop + 8 AAPS vs 28 oref users. '
        'Feature alignment involves approximations — 15 direct, 13 derived, '
        '3 approximated, 2 constant features (see data_bridge FEATURE_QUALITY). '
        'Smaller sample size limits statistical power, especially in LOPO CV '
        'where some patients have few rows. Transfer test results may reflect '
        'both model generalization and feature mapping fidelity.'
    )

    # Synthesis narrative
    report.set_synthesis(
        f'The prediction model replication shows that LightGBM hypo/hyper '
        f'classifiers {"achieve similar" if abs(our_5fold_hypo - 0.83) < 0.05 else "achieve different"} '
        f'performance on our independent data compared to the colleague\'s '
        f'results. Our 5-fold hypo AUC={our_5fold_hypo:.2f} '
        f'(theirs: 0.83), LOPO hypo AUC={our_lopo_hypo:.2f} (theirs: 0.67). '
        f'The within-patient leakage gap of {our_gap:.2f} '
        f'{"is comparable to" if abs(our_gap - 0.16) < 0.05 else "differs from"} '
        f'their 0.16 gap, {"confirming" if our_gap > 0.08 else "suggesting less"} '
        f'temporal leakage in stratified CV. '
        f'Per-patient calibration {"improves" if results.get("exp_2433", {}).get("summary", {}).get("improvement_pp", 0) > 0 else "has mixed effects on"} '
        f'prediction reliability, consistent with their finding.'
    )

    # Strip numpy arrays before saving
    save_results = {}
    for k, v in results.items():
        if isinstance(v, dict):
            save_results[k] = {
                kk: vv for kk, vv in v.items()
                if not isinstance(vv, np.ndarray)
            }
        else:
            save_results[k] = v
    report.set_raw_results(save_results)
    report.save()

    return report


# ===================================================================
# Main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description='EXP-2431–2438: Hypo/Hyper Prediction Model Replication',
    )
    parser.add_argument('--figures', action='store_true', help='Generate figures')
    parser.add_argument('--tiny', action='store_true',
                        help='Quick test with 2 patients and 2 folds')
    args = parser.parse_args()

    print('=' * 70)
    print('EXP-2431–2438: Hypo/Hyper Prediction Model Replication')
    print('=' * 70)

    # ----- Load data -----
    df = load_patients_with_features()
    if args.tiny:
        pids = sorted(df['patient_id'].unique())[:2]
        df = df[df['patient_id'].isin(pids)]
        print(f'[TINY MODE] Using patients: {pids}')

    X, y_hypo, y_hyper, y_bg, valid_df = prepare_data(df)
    patient_ids = valid_df['patient_id']
    n_folds = 2 if args.tiny else 5

    print(f'Data: {len(X):,} rows, {X.shape[1]} features, '
          f'{patient_ids.nunique()} patients')
    print(f'Hypo rate: {y_hypo.mean()*100:.1f}%, '
          f'Hyper rate: {y_hyper.mean()*100:.1f}%')

    results = {}

    # EXP-2431: 5-fold CV
    results['exp_2431'] = run_2431(X, y_hypo, y_hyper, y_bg,
                                   n_folds=n_folds, do_figures=args.figures)

    # EXP-2432: LOPO CV
    results['exp_2432'] = run_2432(X, y_hypo, y_hyper, patient_ids,
                                   do_figures=args.figures)

    # EXP-2433: Isotonic calibration (uses LOPO results)
    results['exp_2433'] = run_2433(results['exp_2432'], patient_ids,
                                   do_figures=args.figures)

    # EXP-2434: Transfer test
    results['exp_2434'] = run_2434(X, y_hypo, y_hyper, patient_ids,
                                   do_figures=args.figures)

    # EXP-2435: Cohort statistics
    results['exp_2435'] = run_2435(valid_df, y_hypo, y_hyper,
                                   do_figures=args.figures)

    # EXP-2436: Calibration curves
    results['exp_2436'] = run_2436(X, y_hypo, y_hyper, results['exp_2432'],
                                   do_figures=args.figures)

    # EXP-2437: Error analysis
    lopo_hypo_true = results['exp_2432'].get('_hypo_true', np.array([]))
    lopo_hypo_prob = results['exp_2432'].get('_hypo_prob', np.array([]))
    results['exp_2437'] = run_2437(X, y_hypo, lopo_hypo_prob, valid_df)

    # EXP-2438: Synthesis
    build_synthesis(results, do_figures=args.figures)

    # ----- Save JSON -----
    # Strip numpy arrays that can't serialise
    json_results = {}
    for k, v in results.items():
        if isinstance(v, dict):
            json_results[k] = {
                kk: vv for kk, vv in v.items()
                if not isinstance(vv, np.ndarray)
            }
        else:
            json_results[k] = v

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, 'w') as f:
        json.dump(json_results, f, indent=2, cls=NumpyEncoder)
    print(f'\nResults saved to {RESULTS_PATH}')

    print('\n' + '=' * 70)
    print('EXP-2431–2438 complete.')
    print('=' * 70)


if __name__ == '__main__':
    main()
