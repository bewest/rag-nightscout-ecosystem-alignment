#!/usr/bin/env python3
"""EXP-1521 to EXP-1528: Therapy Settings Holdout Validation.

Validates therapy inference capabilities (basal, ISF, CR) by comparing
production pipeline assessments on training vs verification data splits.
Uses the 10-day holdout strategy from split-manifest.json.

Experiments:
    EXP-1521: Full-data baseline cohort assessment
    EXP-1522: Training-only vs verification-only grade stability
    EXP-1523: Per-patient flag agreement (train vs verify)
    EXP-1524: Overnight drift reproducibility (basal signal)
    EXP-1525: ISF ratio reproducibility across splits
    EXP-1526: Post-meal excursion reproducibility (CR signal)
    EXP-1527: Recommendation consistency (train vs verify)
    EXP-1528: Minimum data requirements sensitivity curve

Usage:
    PYTHONPATH=tools python tools/cgmencode/exp_holdout_validation_1521.py
    PYTHONPATH=tools python tools/cgmencode/exp_holdout_validation_1521.py -e 1521 1522
    PYTHONPATH=tools python tools/cgmencode/exp_holdout_validation_1521.py --summary
"""

import argparse
import json
import math
import numpy as np
import os
import sys
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from cgmencode.exp_metabolic_flux import load_patients as _load_patients
from cgmencode.production_therapy import (
    TherapyPipeline, TARGET_PROFILES, TherapyAssessment,
    compute_time_in_ranges, compute_overnight_drift,
    compute_max_excursion, compute_isf_ratio,
    compute_overcorrection_rate, assess_preconditions,
    DRIFT_THRESHOLD, EXCURSION_THRESHOLD,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PATIENTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                            'externals', 'ns-data', 'patients')
RESULTS_DIR = (Path(__file__).resolve().parent.parent.parent
               / 'externals' / 'experiments')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

STEPS_PER_HOUR = 12
STEPS_PER_DAY = 24 * STEPS_PER_HOUR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe(v):
    """Convert numpy types for JSON serialization."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v) if not (math.isnan(v) or math.isinf(v)) else 0.0
    if isinstance(v, np.ndarray):
        return [_safe(x) for x in v]
    if isinstance(v, dict):
        return {k: _safe(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_safe(x) for x in v]
    return v


def _save(exp_id: int, data: dict, elapsed: float):
    """Save experiment results."""
    data['elapsed_sec'] = round(elapsed, 1)
    path = RESULTS_DIR / f'exp-{exp_id}_therapy.json'
    with open(path, 'w') as f:
        json.dump(_safe(data), f, indent=2)
    print(f'  → saved {path.name}')


def load_split_patients(split: str = 'training'):
    """Load patients from a specific split (training or verification)."""
    split_dir = os.path.join(os.path.dirname(PATIENTS_DIR), split)
    if not os.path.isdir(split_dir):
        # Fall back to per-patient split directories
        return _load_patients_from_split(split)
    return _load_patients(split_dir)


def _load_patients_from_split(split: str):
    """Load per-patient split data from patients/{id}/{split}/ dirs."""
    patients = []
    patients_base = Path(PATIENTS_DIR)
    for pid_dir in sorted(patients_base.iterdir()):
        if not pid_dir.is_dir():
            continue
        split_dir = pid_dir / split
        if not split_dir.is_dir():
            continue
        # Load entries (glucose), treatments (insulin + carbs)
        entries_file = split_dir / 'entries.json'
        treatments_file = split_dir / 'treatments.json'
        if not entries_file.exists():
            continue
        patients.append({
            'name': pid_dir.name,
            'entries_path': str(entries_file),
            'treatments_path': str(treatments_file),
        })
    return patients


def build_arrays_from_json(entries_path, treatments_path, profile_path=None):
    """Build aligned 5-min step arrays from Nightscout JSON exports."""
    with open(entries_path) as f:
        entries = json.load(f)
    treatments = []
    if os.path.exists(treatments_path):
        with open(treatments_path) as f:
            treatments = json.load(f)

    if not entries:
        return None

    # Sort entries by date
    entries.sort(key=lambda e: e.get('date', 0))
    t_start = entries[0].get('date', 0)
    t_end = entries[-1].get('date', 0)
    if t_start == 0 or t_end == 0:
        return None

    duration_ms = t_end - t_start
    step_ms = 5 * 60 * 1000  # 5 minutes
    n_steps = int(duration_ms / step_ms) + 1
    if n_steps < 100:
        return None

    glucose = np.full(n_steps, np.nan)
    bolus = np.zeros(n_steps)
    carbs = np.zeros(n_steps)
    temp_rate = np.zeros(n_steps)

    for e in entries:
        t = e.get('date', 0) - t_start
        idx = int(t / step_ms)
        if 0 <= idx < n_steps and 'sgv' in e:
            sgv = e['sgv']
            if isinstance(sgv, (int, float)) and 39 < sgv < 401:
                glucose[idx] = sgv

    for tx in treatments:
        t = tx.get('date', tx.get('mills', 0))
        if isinstance(t, str):
            continue
        t = t - t_start if t > t_start else 0
        idx = int(t / step_ms)
        if 0 <= idx < n_steps:
            if tx.get('insulin') and float(tx['insulin']) > 0:
                bolus[idx] += float(tx['insulin'])
            if tx.get('carbs') and float(tx['carbs']) > 0:
                carbs[idx] += float(tx['carbs'])
            if tx.get('eventType') == 'Temp Basal' and tx.get('rate') is not None:
                dur_steps = int(float(tx.get('duration', 30)) / 5)
                rate = float(tx['rate'])
                for s in range(min(dur_steps, n_steps - idx)):
                    temp_rate[idx + s] = rate

    return {
        'glucose': glucose,
        'bolus': bolus,
        'carbs': carbs,
        'temp_rate': temp_rate,
        'n_steps': n_steps,
    }


def run_pipeline_on_split(split: str):
    """Run TherapyPipeline on a data split, return assessments dict."""
    pipeline = TherapyPipeline(profile=TARGET_PROFILES['ada'])
    patients_base = Path(PATIENTS_DIR)
    loaded = []

    for pid_dir in sorted(patients_base.iterdir()):
        if not pid_dir.is_dir():
            continue
        split_dir = pid_dir / split
        if not split_dir.is_dir():
            continue
        entries_path = split_dir / 'entries.json'
        treatments_path = split_dir / 'treatments.json'
        if not entries_path.exists():
            continue

        arrays = build_arrays_from_json(str(entries_path), str(treatments_path))
        if arrays is None or np.sum(~np.isnan(arrays['glucose'])) < 200:
            continue

        pipeline.load_arrays(
            pid_dir.name,
            arrays['glucose'], arrays['bolus'], arrays['carbs'],
            temp_rate=arrays['temp_rate'],
        )
        loaded.append(pid_dir.name)

    if not loaded:
        return {}, []

    assessments = {}
    for pid in loaded:
        try:
            assessments[pid] = pipeline.assess(pid)
        except Exception as e:
            print(f'  Warning: {pid}/{split} assessment failed: {e}')

    return assessments, loaded


def assessment_to_dict(a: TherapyAssessment) -> dict:
    """Extract key metrics from assessment for comparison."""
    return {
        'grade': a.grade.value,
        'v10_score': round(a.v10_score, 1),
        'tir': round(a.time_in_ranges.tir, 1),
        'tbr_total': round(a.time_in_ranges.total_tbr, 1),
        'cv': round(a.time_in_ranges.cv, 1),
        'overnight_drift': round(a.overnight_drift, 2),
        'max_excursion': round(a.max_excursion, 1),
        'isf_ratio': round(a.isf_ratio, 2),
        'basal_flag': a.flags.basal_flag,
        'cr_flag': a.flags.cr_flag,
        'cv_flag': a.flags.cv_flag,
        'tbr_flag': a.flags.tbr_flag,
        'n_hypo': a.n_hypo_episodes,
        'safety_tier': a.safety_tier.value,
        'n_recs': len(a.recommendations),
        'rec_actions': [r.action_text for r in a.recommendations],
        'preconditions': {
            'cgm_coverage': round(a.preconditions.cgm_coverage, 3),
            'insulin_coverage': round(a.preconditions.insulin_coverage, 3),
            'n_days': a.preconditions.n_days,
            'n_meals': a.preconditions.n_meals,
            'n_corrections': a.preconditions.n_corrections,
            'sufficient_for_triage': a.preconditions.sufficient_for_triage,
            'sufficient_for_full': a.preconditions.sufficient_for_full,
            'issues': a.preconditions.issues,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# Experiments
# ═══════════════════════════════════════════════════════════════════════════

EXPERIMENTS = {}


def register(exp_id):
    def decorator(fn):
        EXPERIMENTS[exp_id] = fn
        return fn
    return decorator


@register(1521)
def exp_1521_baseline_cohort():
    """EXP-1521: Full-data baseline cohort assessment."""
    t0 = time.time()
    pipeline = TherapyPipeline(profile=TARGET_PROFILES['ada'])
    patients = pipeline.load_patients(PATIENTS_DIR)
    assessments = pipeline.assess_all()

    per_patient = []
    for pid in sorted(assessments.keys()):
        a = assessments[pid]
        d = assessment_to_dict(a)
        d['patient'] = pid
        per_patient.append(d)

    grade_dist = defaultdict(int)
    for p in per_patient:
        grade_dist[p['grade']] += 1

    tirs = [p['tir'] for p in per_patient]
    cvs = [p['cv'] for p in per_patient]
    drifts = [p['overnight_drift'] for p in per_patient]
    excursions = [p['max_excursion'] for p in per_patient]
    isf_ratios = [p['isf_ratio'] for p in per_patient]

    result = {
        'name': 'EXP-1521: Full-data baseline cohort assessment',
        'n_patients': len(per_patient),
        'grade_distribution': dict(grade_dist),
        'population_metrics': {
            'mean_tir': round(np.mean(tirs), 1),
            'median_tir': round(np.median(tirs), 1),
            'mean_cv': round(np.mean(cvs), 1),
            'mean_overnight_drift': round(np.mean(np.abs(drifts)), 2),
            'mean_excursion': round(np.mean(excursions), 1),
            'mean_isf_ratio': round(np.mean(isf_ratios), 2),
        },
        'flag_rates': {
            'basal': sum(1 for p in per_patient if p['basal_flag']) / len(per_patient),
            'cr': sum(1 for p in per_patient if p['cr_flag']) / len(per_patient),
            'cv': sum(1 for p in per_patient if p['cv_flag']) / len(per_patient),
            'tbr': sum(1 for p in per_patient if p['tbr_flag']) / len(per_patient),
        },
        'per_patient': per_patient,
    }
    _save(1521, result, time.time() - t0)
    return result


@register(1522)
def exp_1522_train_verify_stability():
    """EXP-1522: Training-only vs verification-only grade stability."""
    t0 = time.time()

    print('  Loading training split...')
    train_assessments, train_pids = run_pipeline_on_split('training')
    print(f'  Training: {len(train_assessments)} patients assessed')

    print('  Loading verification split...')
    verify_assessments, verify_pids = run_pipeline_on_split('verification')
    print(f'  Verification: {len(verify_assessments)} patients assessed')

    common = sorted(set(train_assessments.keys()) & set(verify_assessments.keys()))
    per_patient = []
    grade_matches = 0
    score_deltas = []

    for pid in common:
        t = assessment_to_dict(train_assessments[pid])
        v = assessment_to_dict(verify_assessments[pid])
        grade_match = t['grade'] == v['grade']
        if grade_match:
            grade_matches += 1
        score_delta = v['v10_score'] - t['v10_score']
        score_deltas.append(score_delta)

        per_patient.append({
            'patient': pid,
            'train_grade': t['grade'],
            'verify_grade': v['grade'],
            'grade_stable': grade_match,
            'train_score': t['v10_score'],
            'verify_score': v['v10_score'],
            'score_delta': round(score_delta, 1),
            'train_tir': t['tir'],
            'verify_tir': v['tir'],
            'tir_delta': round(v['tir'] - t['tir'], 1),
            'train_cv': t['cv'],
            'verify_cv': v['cv'],
        })

    n = len(common)
    result = {
        'name': 'EXP-1522: Training vs verification grade stability',
        'n_patients': n,
        'grade_agreement': round(grade_matches / n * 100, 1) if n else 0,
        'mean_score_delta': round(np.mean(score_deltas), 1) if score_deltas else 0,
        'score_delta_std': round(np.std(score_deltas), 1) if score_deltas else 0,
        'per_patient': per_patient,
    }
    _save(1522, result, time.time() - t0)
    return result


@register(1523)
def exp_1523_flag_agreement():
    """EXP-1523: Per-patient flag agreement between splits."""
    t0 = time.time()

    train_assessments, _ = run_pipeline_on_split('training')
    verify_assessments, _ = run_pipeline_on_split('verification')
    common = sorted(set(train_assessments.keys()) & set(verify_assessments.keys()))

    flags = ['basal_flag', 'cr_flag', 'cv_flag', 'tbr_flag']
    per_patient = []
    flag_agreement = {f: 0 for f in flags}
    total = len(common)

    for pid in common:
        t = assessment_to_dict(train_assessments[pid])
        v = assessment_to_dict(verify_assessments[pid])
        matches = {}
        for f in flags:
            matches[f] = t[f] == v[f]
            if matches[f]:
                flag_agreement[f] += 1
        per_patient.append({
            'patient': pid,
            **{f'train_{f}': t[f] for f in flags},
            **{f'verify_{f}': v[f] for f in flags},
            **{f'{f}_stable': matches[f] for f in flags},
            'total_agreement': sum(matches.values()) / len(flags),
        })

    result = {
        'name': 'EXP-1523: Per-patient flag agreement (train vs verify)',
        'n_patients': total,
        'flag_agreement_rates': {f: round(flag_agreement[f] / total * 100, 1)
                                 for f in flags} if total else {},
        'overall_agreement': round(
            sum(flag_agreement.values()) / (total * len(flags)) * 100, 1
        ) if total else 0,
        'per_patient': per_patient,
    }
    _save(1523, result, time.time() - t0)
    return result


@register(1524)
def exp_1524_drift_reproducibility():
    """EXP-1524: Overnight drift reproducibility (basal signal)."""
    t0 = time.time()

    train_assessments, _ = run_pipeline_on_split('training')
    verify_assessments, _ = run_pipeline_on_split('verification')
    common = sorted(set(train_assessments.keys()) & set(verify_assessments.keys()))

    per_patient = []
    train_drifts = []
    verify_drifts = []

    for pid in common:
        td = train_assessments[pid].overnight_drift
        vd = verify_assessments[pid].overnight_drift
        train_drifts.append(td)
        verify_drifts.append(vd)
        same_direction = (td > 0 and vd > 0) or (td < 0 and vd < 0) or (abs(td) < 1 and abs(vd) < 1)
        per_patient.append({
            'patient': pid,
            'train_drift': round(td, 2),
            'verify_drift': round(vd, 2),
            'drift_delta': round(abs(td - vd), 2),
            'same_direction': same_direction,
            'train_flagged': abs(td) >= DRIFT_THRESHOLD,
            'verify_flagged': abs(vd) >= DRIFT_THRESHOLD,
            'flag_agrees': (abs(td) >= DRIFT_THRESHOLD) == (abs(vd) >= DRIFT_THRESHOLD),
        })

    if len(train_drifts) >= 3:
        corr = np.corrcoef(train_drifts, verify_drifts)[0, 1]
    else:
        corr = 0.0

    result = {
        'name': 'EXP-1524: Overnight drift reproducibility',
        'n_patients': len(common),
        'drift_correlation': round(corr, 3) if not np.isnan(corr) else 0.0,
        'mean_drift_delta': round(np.mean([p['drift_delta'] for p in per_patient]), 2),
        'direction_agreement': round(
            sum(1 for p in per_patient if p['same_direction']) / len(per_patient) * 100, 1
        ) if per_patient else 0,
        'flag_agreement': round(
            sum(1 for p in per_patient if p['flag_agrees']) / len(per_patient) * 100, 1
        ) if per_patient else 0,
        'per_patient': per_patient,
    }
    _save(1524, result, time.time() - t0)
    return result


@register(1525)
def exp_1525_isf_reproducibility():
    """EXP-1525: ISF ratio reproducibility across splits."""
    t0 = time.time()

    train_assessments, _ = run_pipeline_on_split('training')
    verify_assessments, _ = run_pipeline_on_split('verification')
    common = sorted(set(train_assessments.keys()) & set(verify_assessments.keys()))

    per_patient = []
    train_isf = []
    verify_isf = []

    for pid in common:
        t_isf = train_assessments[pid].isf_ratio
        v_isf = verify_assessments[pid].isf_ratio
        train_isf.append(t_isf)
        verify_isf.append(v_isf)
        per_patient.append({
            'patient': pid,
            'train_isf_ratio': round(t_isf, 2),
            'verify_isf_ratio': round(v_isf, 2),
            'isf_delta': round(abs(t_isf - v_isf), 2),
            'pct_change': round(abs(t_isf - v_isf) / max(t_isf, 0.01) * 100, 1),
        })

    if len(train_isf) >= 3:
        corr = np.corrcoef(train_isf, verify_isf)[0, 1]
    else:
        corr = 0.0

    result = {
        'name': 'EXP-1525: ISF ratio reproducibility',
        'n_patients': len(common),
        'isf_correlation': round(corr, 3) if not np.isnan(corr) else 0.0,
        'mean_pct_change': round(
            np.mean([p['pct_change'] for p in per_patient]), 1
        ) if per_patient else 0,
        'per_patient': per_patient,
    }
    _save(1525, result, time.time() - t0)
    return result


@register(1526)
def exp_1526_excursion_reproducibility():
    """EXP-1526: Post-meal excursion reproducibility (CR signal)."""
    t0 = time.time()

    train_assessments, _ = run_pipeline_on_split('training')
    verify_assessments, _ = run_pipeline_on_split('verification')
    common = sorted(set(train_assessments.keys()) & set(verify_assessments.keys()))

    per_patient = []
    train_exc = []
    verify_exc = []

    for pid in common:
        t_exc = train_assessments[pid].max_excursion
        v_exc = verify_assessments[pid].max_excursion
        train_exc.append(t_exc)
        verify_exc.append(v_exc)
        per_patient.append({
            'patient': pid,
            'train_excursion': round(t_exc, 1),
            'verify_excursion': round(v_exc, 1),
            'excursion_delta': round(abs(t_exc - v_exc), 1),
            'train_flagged': t_exc >= EXCURSION_THRESHOLD,
            'verify_flagged': v_exc >= EXCURSION_THRESHOLD,
            'flag_agrees': (t_exc >= EXCURSION_THRESHOLD) == (v_exc >= EXCURSION_THRESHOLD),
        })

    if len(train_exc) >= 3:
        corr = np.corrcoef(train_exc, verify_exc)[0, 1]
    else:
        corr = 0.0

    result = {
        'name': 'EXP-1526: Post-meal excursion reproducibility (CR)',
        'n_patients': len(common),
        'excursion_correlation': round(corr, 3) if not np.isnan(corr) else 0.0,
        'flag_agreement': round(
            sum(1 for p in per_patient if p['flag_agrees']) / len(per_patient) * 100, 1
        ) if per_patient else 0,
        'per_patient': per_patient,
    }
    _save(1526, result, time.time() - t0)
    return result


@register(1527)
def exp_1527_recommendation_consistency():
    """EXP-1527: Recommendation consistency (train vs verify)."""
    t0 = time.time()

    train_assessments, _ = run_pipeline_on_split('training')
    verify_assessments, _ = run_pipeline_on_split('verification')
    common = sorted(set(train_assessments.keys()) & set(verify_assessments.keys()))

    per_patient = []

    for pid in common:
        t_recs = set(r.action_text for r in train_assessments[pid].recommendations)
        v_recs = set(r.action_text for r in verify_assessments[pid].recommendations)
        intersection = t_recs & v_recs
        union = t_recs | v_recs
        jaccard = len(intersection) / len(union) if union else 1.0

        per_patient.append({
            'patient': pid,
            'train_recs': sorted(t_recs),
            'verify_recs': sorted(v_recs),
            'shared_recs': sorted(intersection),
            'jaccard_similarity': round(jaccard, 2),
            'n_train': len(t_recs),
            'n_verify': len(v_recs),
            'n_shared': len(intersection),
        })

    result = {
        'name': 'EXP-1527: Recommendation consistency',
        'n_patients': len(common),
        'mean_jaccard': round(
            np.mean([p['jaccard_similarity'] for p in per_patient]), 2
        ) if per_patient else 0,
        'pct_with_perfect_agreement': round(
            sum(1 for p in per_patient if p['jaccard_similarity'] == 1.0) / len(per_patient) * 100, 1
        ) if per_patient else 0,
        'per_patient': per_patient,
    }
    _save(1527, result, time.time() - t0)
    return result


@register(1528)
def exp_1528_minimum_data_sensitivity():
    """EXP-1528: Minimum data requirements sensitivity curve."""
    t0 = time.time()

    # Run full-data pipeline for reference
    pipeline_full = TherapyPipeline(profile=TARGET_PROFILES['ada'])
    full_patients = pipeline_full.load_patients(PATIENTS_DIR)
    full_assessments = pipeline_full.assess_all()

    fractions = [0.25, 0.50, 0.75, 1.0]
    per_fraction = []

    for frac in fractions:
        pipeline = TherapyPipeline(profile=TARGET_PROFILES['ada'])
        grade_matches = 0
        score_deltas = []
        n_assessed = 0

        for pid in sorted(full_assessments.keys()):
            p_data = pipeline_full._patients[pid]
            n = len(p_data['glucose'])
            n_keep = int(n * frac)
            if n_keep < 200:
                continue

            pipeline.load_arrays(
                pid,
                p_data['glucose'][:n_keep],
                p_data['bolus'][:n_keep],
                p_data['carbs'][:n_keep],
                temp_rate=p_data['temp_rate'][:n_keep],
                iob=p_data['iob'][:n_keep],
                cob=p_data['cob'][:n_keep],
            )
            try:
                a = pipeline.assess(pid)
                ref = full_assessments[pid]
                if a.grade == ref.grade:
                    grade_matches += 1
                score_deltas.append(a.v10_score - ref.v10_score)
                n_assessed += 1
            except Exception:
                pass

        per_fraction.append({
            'fraction': frac,
            'n_days_approx': round(frac * 180),
            'n_patients': n_assessed,
            'grade_agreement_pct': round(
                grade_matches / n_assessed * 100, 1
            ) if n_assessed else 0,
            'mean_score_delta': round(np.mean(score_deltas), 1) if score_deltas else 0,
            'score_delta_std': round(np.std(score_deltas), 1) if score_deltas else 0,
        })

    result = {
        'name': 'EXP-1528: Minimum data requirements sensitivity',
        'fractions_tested': fractions,
        'per_fraction': per_fraction,
    }
    _save(1528, result, time.time() - t0)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='EXP-1521–1528: Therapy holdout validation')
    parser.add_argument('-e', '--experiments', nargs='*', type=int,
                        help='Run specific experiments (default: all)')
    parser.add_argument('--summary', action='store_true',
                        help='Print summary of existing results')
    args = parser.parse_args()

    if args.summary:
        for eid in sorted(EXPERIMENTS.keys()):
            path = RESULTS_DIR / f'exp-{eid}_therapy.json'
            if path.exists():
                with open(path) as f:
                    d = json.load(f)
                print(f'EXP-{eid}: {d.get("name", "?")} '
                      f'({d.get("elapsed_sec", "?")}s)')
            else:
                print(f'EXP-{eid}: not yet run')
        return

    to_run = args.experiments or sorted(EXPERIMENTS.keys())

    for eid in to_run:
        if eid not in EXPERIMENTS:
            print(f'Unknown experiment: {eid}')
            continue
        print(f'Running EXP-{eid}...')
        try:
            EXPERIMENTS[eid]()
        except Exception as e:
            print(f'  ERROR: {e}')
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()
