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
import random
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

# Random-search bounds (only applied to the continuous axis).
RANDOM_GATE_LOW = 0.04
RANDOM_GATE_HIGH = 0.30
# Refinement sweep: dense 1D scan of braking_gate around the grid winner.
REFINE_RADIUS = 0.05
REFINE_STEP = 0.01


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

    safe_cells = [c for c in cells if c['safety_ok']]

    # Optional refinement pass: dense 1D sweep of braking_gate around the
    # winner's (mode, proxy, src) cell, plus optional random search.
    if safe_cells and (args.refine or args.random_iterations > 0):
        winner_seed = max(safe_cells, key=lambda c: c['score'] or 0.0)
        seed_mode = winner_seed['braking_mode']
        seed_proxy = winner_seed['proxy']
        seed_src = winner_seed['per_patient_source']
        seed_gate = float(winner_seed['braking_gate'])
        print(f'[refine] seed cell: gate={seed_gate} mode={seed_mode} '
              f'proxy={seed_proxy} src={seed_src} score={winner_seed["score"]:.4f}',
              file=sys.stderr)

        if args.refine:
            n_steps = int(round(REFINE_RADIUS / REFINE_STEP))
            gates = sorted({
                round(max(RANDOM_GATE_LOW, min(RANDOM_GATE_HIGH,
                                               seed_gate + k * REFINE_STEP)), 4)
                for k in range(-n_steps, n_steps + 1)
            })
            for j, g in enumerate(gates, start=1):
                print(f'[refine {j}/{len(gates)}] gate={g} mode={seed_mode} '
                      f'proxy={seed_proxy} src={seed_src}…', file=sys.stderr)
                r = run_scorer(per_patient=True, braking_gate=g,
                               braking_mode=seed_mode, proxy=seed_proxy,
                               per_patient_source=seed_src,
                               safety_mode=args.safety_mode)
                cells.append({
                    'cell': f'refine_{j:02d}',
                    'braking_gate': g, 'braking_mode': seed_mode,
                    'proxy': seed_proxy, 'per_patient_source': seed_src,
                    'score': r.get('score'), 'safety_ok': r.get('safety_ok'),
                    'cohort_safety_ok': r.get('cohort_safety_ok'),
                    'stratified_safety_ok': r.get('stratified_safety_ok'),
                    'n_used': (r.get('meta') or {}).get('n_events_used'),
                    'n_dropped': (r.get('meta') or {}).get('n_dropped_braking'),
                    'n_m_unity': (r.get('meta') or {}).get('n_m_unity'),
                })

        if args.random_iterations > 0:
            rng = random.Random(args.random_seed)
            for j in range(1, args.random_iterations + 1):
                g = round(rng.uniform(RANDOM_GATE_LOW, RANDOM_GATE_HIGH), 4)
                # Sample categorical axes too — but only from values
                # observed to be safe in the grid (excludes worst_case).
                mode = rng.choice(['drop', 'm_unity'])
                src = rng.choice(['raw', 'clamped'])
                proxy = 'carb_aware'
                print(f'[rand {j}/{args.random_iterations}] gate={g} mode={mode} '
                      f'proxy={proxy} src={src}…', file=sys.stderr)
                r = run_scorer(per_patient=True, braking_gate=g,
                               braking_mode=mode, proxy=proxy,
                               per_patient_source=src,
                               safety_mode=args.safety_mode)
                cells.append({
                    'cell': f'rand_{j:02d}',
                    'braking_gate': g, 'braking_mode': mode,
                    'proxy': proxy, 'per_patient_source': src,
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
    # Total cohort size (from baseline cell which uses all events).
    n_total = next((c['n_used'] for c in cells if c['cell'] == 'baseline'), None)
    if n_total:
        retain_safe = [c for c in safe_cells
                       if (c['n_used'] or 0) / n_total >= args.min_retention]
    else:
        retain_safe = safe_cells
    raw_winner = max(safe_cells, key=lambda c: c['score'] or 0.0) if safe_cells else None
    winner = max(retain_safe, key=lambda c: c['score'] or 0.0) if retain_safe else raw_winner

    return {
        'harness': 'cf-replay-v3',
        'safety_mode': args.safety_mode,
        'tsv': str(tsv_path),
        'n_cells': len(cells),
        'n_safe': len(safe_cells),
        'n_total_cohort': n_total,
        'min_retention': args.min_retention,
        'baseline_score': base.get('score'),
        'frontier_score': frontier.get('score'),
        'winner': winner,
        'raw_winner': raw_winner,
        'cells': cells,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--safety-mode', choices=['cohort', 'stratified'],
                    default='stratified',
                    help='which safety gate to enforce (default stratified, EXP-3018)')
    ap.add_argument('--refine', action='store_true',
                    help='after grid, do a dense 1D sweep of braking_gate around the winner')
    ap.add_argument('--random-iterations', type=int, default=0,
                    help='additional random-search iterations after grid (default 0)')
    ap.add_argument('--random-seed', type=int, default=42)
    ap.add_argument('--min-retention', type=float, default=0.80,
                    help='minimum n_used/n_total ratio for the deployable winner '
                         'pick (default 0.80; the unconstrained winner is also '
                         'reported as raw_winner)')
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
        print(f"WINNER (≥{out['min_retention']:.0%} retention): cell={w['cell']}  "
              f"score={w['score']:.4f}  safety_ok={w['safety_ok']}")
        print(f"  gate={w['braking_gate']}  mode={w['braking_mode']}  "
              f"proxy={w['proxy']}  src={w['per_patient_source']}  "
              f"n_used={w['n_used']}")
    if out['raw_winner'] and (not out['winner']
                              or out['raw_winner']['cell'] != out['winner']['cell']):
        rw = out['raw_winner']
        print(f"RAW WINNER (no retention floor, may be selection-biased): "
              f"cell={rw['cell']}  score={rw['score']:.4f}  "
              f"n_used={rw['n_used']}/{out['n_total_cohort']}")
    if not out['winner']:
        print("WINNER: NONE (no cell passed safety gate)")
    print(f"TSV: {out['tsv']}")


if __name__ == '__main__':
    main()
