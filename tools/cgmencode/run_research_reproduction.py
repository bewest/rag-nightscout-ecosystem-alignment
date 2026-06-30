#!/usr/bin/env python3
"""Run selected standalone diabetes research scripts under MLflow.

This wrapper is for experiments that predate the main cgmencode MLflow
integration and are still valuable for physiological interpretation,
PK relationships, and EGP proxy exploration.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mlflow_utils import log_artifact, log_dict, log_text, start_run

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ResearchCase:
    key: str
    title: str
    description: str
    command: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()


CASES: dict[str, ResearchCase] = {
    'aid-compensation-egp': ResearchCase(
        key='aid-compensation-egp',
        title='AID compensation cascade and Hill-EGP proxy audit',
        description='Tests whether AID compensation and Hill-style EGP explain low-glucose recovery dynamics.',
        command=('python3', 'tools/cgmencode/exp_aid_compensation_2629.py'),
        artifact_paths=('externals/experiments/exp-2629_aid_compensation_cascade.json',),
    ),
    'product-flux-hepatic': ResearchCase(
        key='product-flux-hepatic',
        title='Product flux with hepatic baseline',
        description='Compares hepatic-aware supply×demand flux against sum-style flux representations.',
        command=('python3', 'tools/cgmencode/exp_metabolic_441.py', '--experiment', '441'),
        artifact_paths=('externals/experiments/exp441_product_flux_hepatic.json',),
    ),
    'tdd-normalization': ResearchCase(
        key='tdd-normalization',
        title='TDD normalization and 1800-rule comparison',
        description='Evaluates TDD-scaled PK channels and the 1800-rule as a cross-patient PK normalization proxy.',
        command=('python3', 'tools/cgmencode/exp_metabolic_441.py', '--experiment', '442'),
        artifact_paths=('externals/experiments/exp442_tdd_normalization.json',),
    ),
    'throughput-balance': ResearchCase(
        key='throughput-balance',
        title='Throughput and balance dual-channel discrimination',
        description='Tests whether throughput and supply-demand balance outperform glucose-only signals at different horizons.',
        command=('python3', 'tools/cgmencode/exp_metabolic_441.py', '--experiment', '443'),
        artifact_paths=('externals/experiments/exp443_throughput_balance.json',),
    ),
    'settings-adequacy': ResearchCase(
        key='settings-adequacy',
        title='Settings adequacy and basal-period decomposition',
        description='Explores whether flux-derived scores predict future TIR and where basal settings are misaligned across the day.',
        command=('python3', 'tools/cgmencode/exp_autoresearch_581.py', '--experiments', '581,582', '--detail', '--save'),
        artifact_paths=(
            'externals/experiments/exp581_score_predicts_future_tir.json',
            'externals/experiments/exp582_per-period_basal_decomposition.json',
        ),
        env=(('PYTHONPATH', 'tools'),),
    ),
    'correction-taxonomy': ResearchCase(
        key='correction-taxonomy',
        title='Correction event taxonomy',
        description='Classifies correction responses by speed, failure mode, and overcorrection risk to support intervention design.',
        command=('python3', 'tools/cgmencode/exp_autoresearch_581.py', '--experiments', '583', '--detail', '--save'),
        artifact_paths=('externals/experiments/exp583_correction_event_taxonomy.json',),
        env=(('PYTHONPATH', 'tools'),),
    ),
    'biweekly-settings': ResearchCase(
        key='biweekly-settings',
        title='Biweekly settings tracking',
        description='Tracks settings adequacy at a 2-week resolution to distinguish drift and instability from broad monthly trends.',
        command=('python3', 'tools/cgmencode/exp_autoresearch_581.py', '--experiments', '584', '--detail', '--save'),
        artifact_paths=('externals/experiments/exp584_biweekly_settings_tracking.json',),
        env=(('PYTHONPATH', 'tools'),),
    ),
    'hybrid-meal-detector': ResearchCase(
        key='hybrid-meal-detector',
        title='Hybrid UAM and throughput meal detector',
        description='Benchmarks a leave-one-patient-out hybrid detector that combines short-horizon rise features with throughput, balance, and controller-context features.',
        command=('python3', 'tools/cgmencode/exp_hybrid_meal_detector_3446.py'),
        artifact_paths=('externals/experiments/exp3446_hybrid_meal_detector.json',),
    ),
    'live-recent-deconfounding': ResearchCase(
        key='live-recent-deconfounding',
        title='Live-recent deconfounding and safety-gated action audit',
        description='Compares 30/60/90 day live-recent windows after excluding inferred and hybrid-supported meal contamination from basal and ISF evidence.',
        command=('python3', 'tools/cgmencode/exp_live_recent_deconfounding_3447.py'),
        artifact_paths=(
            'externals/experiments/exp3447_live_recent_deconfounding.json',
            'externals/experiments/autoresearch/exp3447_live_recent_deconfounding.md',
        ),
    ),
    'live-recent-isf-deconfounding': ResearchCase(
        key='live-recent-isf-deconfounding',
        title='Live-recent ISF deconfounding sensitivity audit',
        description='Tests whether observed correction-denominator ISF around 54-56 survives inferred-meal and controller deconfounding strongly enough for a baseline ISF change.',
        command=('python3', 'tools/cgmencode/exp_live_recent_isf_deconfounding_3448.py'),
        artifact_paths=(
            'externals/experiments/exp3448_live_recent_isf_deconfounding.json',
            'externals/experiments/autoresearch/exp3448_live_recent_isf_deconfounding.md',
        ),
    ),
    'live-recent-basal-replay': ResearchCase(
        key='live-recent-basal-replay',
        title='Live-recent basal step replay and ISF readiness audit',
        description='Stress-tests the +10% 06:00-12:00 basal step under controller-replacement and additive counterfactual assumptions, then assesses ISF readiness.',
        command=('python3', 'tools/cgmencode/exp_live_recent_basal_replay_3449.py'),
        artifact_paths=(
            'externals/experiments/exp3449_live_recent_basal_replay.json',
            'externals/experiments/autoresearch/exp3449_live_recent_basal_replay.md',
        ),
    ),
    'live-recent-basal-natural': ResearchCase(
        key='live-recent-basal-natural',
        title='Live-recent morning basal natural experiment',
        description='Compares clean matched morning windows where Loop already delivered at least the proposed basal rate against lower-delivery windows.',
        command=('python3', 'tools/cgmencode/exp_live_recent_basal_natural_3450.py'),
        artifact_paths=(
            'externals/experiments/exp3450_live_recent_basal_natural.json',
            'externals/experiments/autoresearch/exp3450_live_recent_basal_natural.md',
        ),
    ),
    'live-recent-isf-ladder': ResearchCase(
        key='live-recent-isf-ladder',
        title='Live-recent ISF decomposition ladder',
        description='Reconciles scheduled, apparent, demand-phase, correction-denominator, UAM-filtered, and dose-shaping ISF-like values for live-recent.',
        command=('python3', 'tools/cgmencode/exp_live_recent_isf_ladder_3451.py'),
        artifact_paths=(
            'externals/experiments/exp3451_live_recent_isf_ladder.json',
            'externals/experiments/autoresearch/exp3451_live_recent_isf_ladder.md',
        ),
    ),
    'live-recent-isf-decision-robustness': ResearchCase(
        key='live-recent-isf-decision-robustness',
        title='Live-recent ISF horizon decision robustness',
        description='Sweeps exact and nadir ISF horizons from 1h to 6h to test whether any UAM-clean estimate would flip the default hold decision.',
        command=('python3', 'tools/cgmencode/exp_live_recent_isf_decision_robustness_3452.py'),
        artifact_paths=(
            'externals/experiments/exp3452_live_recent_isf_decision_robustness.json',
            'externals/experiments/autoresearch/exp3452_live_recent_isf_decision_robustness.md',
        ),
    ),
}


def _run_case(case: ResearchCase) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(dict(case.env))
    started = time.time()
    proc = subprocess.run(
        case.command,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    duration = time.time() - started
    artifacts = []
    for rel_path in case.artifact_paths:
        path = ROOT / rel_path
        if path.exists():
            artifacts.append(rel_path)
    return {
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
        'duration_seconds': duration,
        'artifacts_found': artifacts,
    }


def run_case(key: str) -> dict[str, Any]:
    if key not in CASES:
        raise KeyError(f'Unknown research case: {key}')
    case = CASES[key]
    with start_run(
        run_name=f'research-{case.key}',
        tags={'runner': 'run_research_reproduction', 'research_case': case.key},
        params={
            'research_case': case.key,
            'title': case.title,
            'description': case.description,
            'command': list(case.command),
            'artifact_paths': list(case.artifact_paths),
        },
    ):
        result = _run_case(case)
        log_dict(
            {
                'case': case.key,
                'title': case.title,
                'description': case.description,
                'returncode': result['returncode'],
                'duration_seconds': result['duration_seconds'],
                'artifacts_found': result['artifacts_found'],
            },
            f'research/{case.key}_summary.json',
        )
        log_text(result['stdout'], f'research/{case.key}_stdout.txt')
        if result['stderr']:
            log_text(result['stderr'], f'research/{case.key}_stderr.txt')
        for rel_path in case.artifact_paths:
            artifact = ROOT / rel_path
            if artifact.exists():
                log_artifact(artifact, artifact_path='research-artifacts')
        return {
            'case': case,
            **result,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=sorted(CASES.keys()))
    args = parser.parse_args()
    result = run_case(args.case)
    sys.stdout.write(result['stdout'])
    if result['stderr']:
        sys.stderr.write(result['stderr'])
    if result['returncode'] != 0:
        raise SystemExit(result['returncode'])


if __name__ == '__main__':
    main()
