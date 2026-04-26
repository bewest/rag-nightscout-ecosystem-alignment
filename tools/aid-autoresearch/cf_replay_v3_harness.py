#!/usr/bin/env python3
"""Autonomous cf-replay-v3 harness.

Sweeps the free cohort-level knobs of cf_replay_score_v3 over a small grid,
records every cell into a TSV, and reports the safety-passing winner.

This is the autoresearch loop that consumes the productionised v3 scorer.
The per-patient (T*, M*) layer is already pre-baked into the clamped
parquet (EXP-3017) and the imputed phenotype (EXP-3019), so the search
space here is intentionally small — these are the *cohort-level* meta-knobs
that remain free after Phase 5.

Search space (default grid):
  braking_gate   ∈ {0.05, 0.075, 0.10, 0.125, 0.15}
  braking_mode   ∈ {drop, m_unity}
  proxy          ∈ {carb_aware, worst_case}
  patient_source ∈ {raw, clamped}
  → 5 × 2 × 2 × 2 = 40 cells, plus baseline (M=1, T=0)

Outputs:
  externals/experiments/cf_replay_v3_harness_<timestamp>.tsv
  stdout JSON or pretty-printed table.

Trace: EXP-3015..3019 productionised; harness wraps cf_replay_score_v3.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCORER = REPO_ROOT / 'tools' / 'aid-autoresearch' / 'cf_replay_score_v3.py'
OUT_DIR = REPO_ROOT / 'externals' / 'experiments'

DEFAULT_GRID = {
    'braking_gate': [0.05, 0.075, 0.10, 0.125, 0.15],
    'braking_mode': ['drop', 'm_unity'],
    'proxy':        ['carb_aware', 'worst_case'],
    'per_patient_source': ['raw', 'clamped'],
}


def run_scorer(*, per_patient: bool, braking_gate: float | None,
               braking_mode: str, proxy: str, per_patient_source: str,
               safety_mode: str, smb_multiplier: float = 1.0,
               t_shift: float = 0.0) -> dict:
    cmd = [sys.executable, str(SCORER), '--json',
           '--proxy', proxy,
           '--safety-mode', safety_mode,
           '--smb-multiplier', str(smb_multiplier),
           '--t-shift', str(t_shift)]
    if per_patient:
        cmd += ['--per-patient',
                '--per-patient-source', per_patient_source]
    if braking_gate is not None:
        cmd += ['--braking-gate', str(braking_gate),
                '--braking-mode', braking_mode]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if not res.stdout.strip():
        return {'score': 0.0, 'safety_ok': False,
                'reason': f'scorer empty (stderr={res.stderr[:200]})',
                'returncode': res.returncode}
    try:
        d = json.loads(res.stdout)
        d['_returncode'] = res.returncode
        return d
    except json.JSONDecodeError as e:
        return {'score': 0.0, 'safety_ok': False,
                'reason': f'json decode failed: {e}',
                'stdout': res.stdout[:200]}


def harness(args) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    tsv_path = OUT_DIR / f'cf_replay_v3_harness_{ts}.tsv'

    cells: list[dict] = []

    # Baseline (cohort-uniform M=1, T=0)
    print('[0/?] baseline (M=1, T=0)…', file=sys.stderr)
    base = run_scorer(per_patient=False, braking_gate=None,
                      braking_mode='none', proxy='carb_aware',
                      per_patient_source='clamped',
                      safety_mode=args.safety_mode,
                      smb_multiplier=1.0, t_shift=0.0)
    cells.append({
        'cell': 'baseline',
        'braking_gate': None, 'braking_mode': 'none',
        'proxy': 'carb_aware', 'per_patient_source': 'n/a',
        'score': base.get('score'), 'safety_ok': base.get('safety_ok'),
        'cohort_safety_ok': base.get('cohort_safety_ok'),
        'stratified_safety_ok': base.get('stratified_safety_ok'),
        'n_used': (base.get('meta') or {}).get('n_events_used'),
        'n_dropped': (base.get('meta') or {}).get('n_dropped_braking'),
        'n_m_unity': (base.get('meta') or {}).get('n_m_unity'),
    })

    # Phase-2 uniform frontier reference
    print('[ref] uniform frontier (M=0.5, T=+30)…', file=sys.stderr)
    frontier = run_scorer(per_patient=False, braking_gate=None,
                          braking_mode='none', proxy='carb_aware',
                          per_patient_source='clamped',
                          safety_mode=args.safety_mode,
                          smb_multiplier=0.5, t_shift=30.0)
    cells.append({
        'cell': 'uniform_frontier',
        'braking_gate': None, 'braking_mode': 'none',
        'proxy': 'carb_aware', 'per_patient_source': 'n/a',
        'score': frontier.get('score'), 'safety_ok': frontier.get('safety_ok'),
        'cohort_safety_ok': frontier.get('cohort_safety_ok'),
        'stratified_safety_ok': frontier.get('stratified_safety_ok'),
        'n_used': (frontier.get('meta') or {}).get('n_events_used'),
        'n_dropped': (frontier.get('meta') or {}).get('n_dropped_braking'),
        'n_m_unity': (frontier.get('meta') or {}).get('n_m_unity'),
    })

    grid_keys = list(DEFAULT_GRID.keys())
    grid_vals = list(itertools.product(*[DEFAULT_GRID[k] for k in grid_keys]))
    total = len(grid_vals)
    for i, combo in enumerate(grid_vals, start=1):
        params = dict(zip(grid_keys, combo))
        label = ('g={braking_gate} mode={braking_mode} proxy={proxy} '
                 'src={per_patient_source}').format(**params)
        print(f'[{i}/{total}] {label}…', file=sys.stderr)
        r = run_scorer(per_patient=True,
                       braking_gate=params['braking_gate'],
                       braking_mode=params['braking_mode'],
                       proxy=params['proxy'],
                       per_patient_source=params['per_patient_source'],
                       safety_mode=args.safety_mode)
        cells.append({
            'cell': f'cell_{i:02d}',
            **params,
            'score': r.get('score'), 'safety_ok': r.get('safety_ok'),
            'cohort_safety_ok': r.get('cohort_safety_ok'),
            'stratified_safety_ok': r.get('stratified_safety_ok'),
            'n_used': (r.get('meta') or {}).get('n_events_used'),
            'n_dropped': (r.get('meta') or {}).get('n_dropped_braking'),
            'n_m_unity': (r.get('meta') or {}).get('n_m_unity'),
        })

    cols = ['cell', 'braking_gate', 'braking_mode', 'proxy',
            'per_patient_source', 'score', 'safety_ok',
            'cohort_safety_ok', 'stratified_safety_ok',
            'n_used', 'n_dropped', 'n_m_unity']
    with tsv_path.open('w') as f:
        f.write('\t'.join(cols) + '\n')
        for c in cells:
            f.write('\t'.join(str(c.get(k, '')) for k in cols) + '\n')

    safe_cells = [c for c in cells if c['safety_ok']]
    winner = max(safe_cells, key=lambda c: c['score'] or 0.0) if safe_cells else None

    return {
        'harness': 'cf-replay-v3',
        'safety_mode': args.safety_mode,
        'tsv': str(tsv_path),
        'n_cells': len(cells),
        'n_safe': len(safe_cells),
        'baseline_score': base.get('score'),
        'frontier_score': frontier.get('score'),
        'winner': winner,
        'cells': cells,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--safety-mode', choices=['cohort', 'stratified'],
                    default='stratified',
                    help='which safety gate to enforce (default stratified, EXP-3018)')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    out = harness(args)

    if args.json:
        print(json.dumps(out, indent=2, default=float))
        return

    print()
    print(f"=== cf-replay-v3 harness ({out['safety_mode']}) ===")
    print(f"cells={out['n_cells']}  safe={out['n_safe']}  "
          f"baseline={out['baseline_score']:.4f}  "
          f"frontier={out['frontier_score']:.4f}")
    if out['winner']:
        w = out['winner']
        print(f"WINNER: cell={w['cell']}  score={w['score']:.4f}  "
              f"safety_ok={w['safety_ok']}")
        print(f"  gate={w['braking_gate']}  mode={w['braking_mode']}  "
              f"proxy={w['proxy']}  src={w['per_patient_source']}  "
              f"n_used={w['n_used']}")
    else:
        print("WINNER: NONE (no cell passed safety gate)")
    print(f"TSV: {out['tsv']}")


if __name__ == '__main__':
    main()
