#!/usr/bin/env python3
"""
Generate all figures for the Top 5 Campaign Insights report.

Uses tools.cgmencode.report_viz shared module and reads experiment
JSON files for accurate data.

Usage:
    source .venv/bin/activate
    python visualizations/top5-insights-report/generate_figures.py
"""

import json
import sys
from pathlib import Path

# Add repo root for imports
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools.cgmencode.report_viz import (
    plot_r2_waterfall,
    plot_horizon_routing_heatmap,
    plot_aid_loop_behavior,
    plot_patient_heterogeneity,
    plot_residual_ceiling,
)

OUT_DIR = Path(__file__).parent
EXP_DIR = REPO_ROOT / 'externals' / 'experiments'


def load_json(path):
    with open(path) as f:
        return json.load(f)


def fig01_r2_waterfall():
    """Insight 1: Physics + preprocessing delivers 52% R² improvement."""
    d700 = load_json(REPO_ROOT / 'exp-700_exp-700_grand_summary.json')

    stages = {
        'Raw CGM\nbaseline': d700['mean_r2_v0'],
        'Spike\ncleaning': d700['mean_r2_v1'],
        '+ Dawn basal\nconditioning': d700['mean_r2_v2'],
    }

    # Add later milestones from known experiment results
    d950 = load_json(EXP_DIR / 'exp_exp_950_campaign_grand_finale.json')
    stages['+ PK features\n(39 channels)'] = d950['results']['grand_base_r2']
    stages['+ CV stacking\n(EXP-950)'] = d950['results']['grand_stacked_r2']

    d963 = load_json(EXP_DIR / 'exp_exp_963_regime_+_interactions_+_poly.json')
    stages['+ Regime ×\ninteractions'] = d963['results']['triple_r2']

    # Per-patient data for scatter
    per_patient = {}
    for p in d700['per_patient']:
        pid = p['patient']
        per_patient[pid] = {
            'Raw CGM\nbaseline': p['r2_v0_baseline'],
            'Spike\ncleaning': p['r2_v1_spike_cleaned'],
            '+ Dawn basal\nconditioning': p['r2_v2_cleaned_dawn'],
        }

    plot_r2_waterfall(stages, per_patient,
                      str(OUT_DIR / 'fig01_r2_waterfall.png'))
    print('✓ fig01_r2_waterfall.png')


def fig02_horizon_routing():
    """Insight 2: Production champion routing across all horizons."""
    d619 = load_json(EXP_DIR / 'exp619_composite_champion.json')

    # Compute mean MAE across patients for each window × horizon
    window_data = {}
    for w_name, w_results in d619['window_results'].items():
        per_patient = w_results['per_patient']
        # Collect all horizons present
        all_horizons = set()
        for pm in per_patient.values():
            all_horizons.update(k for k in pm.keys() if k.startswith('h'))
        all_horizons = sorted(all_horizons, key=lambda h: int(h[1:]))

        mean_maes = {}
        for h in all_horizons:
            vals = [pm[h] for pm in per_patient.values() if h in pm]
            if vals:
                mean_maes[h] = round(sum(vals) / len(vals), 1)
        window_data[w_name] = mean_maes

    plot_horizon_routing_heatmap(window_data,
                                 str(OUT_DIR / 'fig02_horizon_routing.png'))
    print('✓ fig02_horizon_routing.png')


def fig03_aid_loop():
    """Insight 3: AID loops almost never idle — basal rates are wrong."""
    d981 = load_json(EXP_DIR / 'exp_exp_981_loop_aggressiveness_score.json')
    d985 = load_json(EXP_DIR / 'exp_exp_985_settings_stability_windows.json')

    # Build drift lookup from EXP-985
    drift_lookup = {}
    for p in d985['results']['per_patient']:
        drift_lookup[p['patient']] = {
            'drift': p.get('mean_drift_when_stable'),
            'assessment': p.get('true_basal_assessment', ''),
        }

    loop_data = []
    for p in d981['results']['per_patient']:
        pid = p['patient']
        entry = {
            'patient': pid,
            'pct_suspended': p['pct_suspended'],
            'pct_high_temp': p['pct_high_temp'],
            'pct_nominal': p['pct_nominal'],
        }
        # Add drift from EXP-985
        d985_info = drift_lookup.get(pid, {})
        entry['drift'] = d985_info.get('drift')
        entry['assessment'] = d985_info.get('assessment', '')
        loop_data.append(entry)

    plot_aid_loop_behavior(loop_data,
                           str(OUT_DIR / 'fig03_aid_loop.png'))
    print('✓ fig03_aid_loop.png')


def fig04_patient_heterogeneity():
    """Insight 4: Patient heterogeneity — ISF predicts difficulty."""
    d619 = load_json(EXP_DIR / 'exp619_composite_champion.json')
    d1033 = load_json(EXP_DIR / 'exp-1033_patient_h_deep_dive.json')

    # ISF values from composite champion report
    isf_values = {
        'a': 49, 'b': 94, 'c': 77, 'd': 40, 'e': 36,
        'f': 21, 'g': 69, 'h': 92, 'i': 50, 'j': 40, 'k': 25,
    }

    patient_data = []
    w48 = d619['window_results']['w48']['per_patient']
    for pid in sorted(w48.keys()):
        pm = w48[pid]
        missing = d1033['results']['per_patient'].get(pid, {}).get('missing_rate', 0)
        mean_bg = d1033['results']['per_patient'].get(pid, {}).get('glucose_mean', 150)
        patient_data.append({
            'patient': pid,
            'isf': isf_values.get(pid, 50),
            'h60_mae': pm['h60'],
            'h120_mae': pm['h120'],
            'missing_rate': missing,
            'mean_bg': mean_bg,
        })

    plot_patient_heterogeneity(patient_data,
                                str(OUT_DIR / 'fig04_patient_scatter.png'))
    print('✓ fig04_patient_scatter.png')


def fig05_residual_ceiling():
    """Insight 5: SOTA progression and the oracle ceiling."""
    milestones = [
        ('Glucose-only AR(4)', 0.200),
        ('+ Supply/demand decomposition', 0.465),
        ('+ Forward sums + shapes', 0.533),
        ('+ PK derivatives (39 features)', 0.556),
        ('+ CV stacking (EXP-950)', 0.577),
        ('+ Regime × interactions (EXP-963)', 0.585),
    ]

    stages_data = {
        'milestones': milestones,
        'ceiling': 0.613,
    }

    plot_residual_ceiling(stages_data,
                          str(OUT_DIR / 'fig05_sota_ceiling.png'))
    print('✓ fig05_sota_ceiling.png')


if __name__ == '__main__':
    print(f'Output directory: {OUT_DIR}')
    print(f'Experiment directory: {EXP_DIR}')
    print()

    fig01_r2_waterfall()
    fig02_horizon_routing()
    fig03_aid_loop()
    fig04_patient_heterogeneity()
    fig05_residual_ceiling()

    print(f'\nAll figures saved to {OUT_DIR}/')
