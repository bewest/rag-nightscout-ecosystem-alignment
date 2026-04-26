#!/usr/bin/env python3
"""Smoke test for cf_replay_score_v3.py — three modes; assert score order + safety.

Runs the v3 scorer in (uniform-baseline, uniform-frontier, per-patient) modes
and asserts:
  * baseline (mult=1, T=0) FAILS safety gate (observed proxy is hypo-heavy)
  * frontier (mult=0.5, T=30) PASSES gate AND scores higher than baseline
  * per-patient + braking-gate PASSES gate

Used as a regression check after any change to the scorer or upstream parquets.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'tools' / 'aid-autoresearch' / 'cf_replay_score_v3.py'


def run(*args: str) -> dict:
    p = subprocess.run([sys.executable, str(SCRIPT), '--json', *args],
                       capture_output=True, text=True, cwd=ROOT)
    return json.loads(p.stdout)


def main() -> int:
    base = run('--smb-multiplier', '1.0', '--t-shift', '0')
    front = run('--smb-multiplier', '0.5', '--t-shift', '30')
    per_drop = run('--per-patient', '--braking-gate', '--braking-mode', 'drop')
    per_munity = run('--per-patient', '--braking-gate', '--braking-mode', 'm_unity')

    fails: list[str] = []
    if base['safety_ok']:
        fails.append('baseline (mult=1, T=0) unexpectedly passed safety gate')
    if not front['safety_ok']:
        fails.append(f'frontier (mult=0.5, T=30) failed safety: '
                     f'max_hypo={front["components"]["ascent_max_hypo_rate"]:.4f}')
    if front['score'] <= base['score']:
        fails.append(f'frontier score {front["score"]:.4f} not > '
                     f'baseline {base["score"]:.4f}')
    if not per_drop['safety_ok']:
        fails.append(f'per-patient drop mode failed safety: '
                     f'max_hypo={per_drop["components"]["ascent_max_hypo_rate"]:.4f}')
    if per_drop['meta']['n_dropped_braking'] == 0:
        fails.append('per-patient drop mode dropped zero events for braking gate '
                     '(phenotype parquet not loaded?)')
    if per_munity['meta']['n_m_unity'] == 0:
        fails.append('per-patient m_unity mode forced zero events to M=1.0 '
                     '(phenotype parquet not loaded?)')
    if per_munity['meta']['n_dropped_braking'] != 0:
        fails.append('m_unity mode unexpectedly dropped events')
    # m_unity safety NOT asserted: per EXP-3016 it intentionally reverts
    # high-braking patients to baseline-strength insulin which itself fails
    # the cohort-uniform safety gate. This is documented behaviour.

    print(f"baseline:    score={base['score']:.4f}  safety={base['safety_ok']}")
    print(f"frontier:    score={front['score']:.4f}  safety={front['safety_ok']}")
    print(f"per_drop:    score={per_drop['score']:.4f}  safety={per_drop['safety_ok']}  "
          f"used={per_drop['meta']['n_events_used']}/{per_drop['meta']['n_events_total']}")
    print(f"per_munity:  score={per_munity['score']:.4f}  safety={per_munity['safety_ok']}  "
          f"forced={per_munity['meta']['n_m_unity']} to M=1.0")

    if fails:
        for f in fails:
            print(f'  FAIL: {f}')
        return 1
    print('OK: all v3 smoke-test assertions pass.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
