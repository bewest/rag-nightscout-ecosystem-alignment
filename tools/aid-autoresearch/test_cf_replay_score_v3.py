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
    per = run('--per-patient', '--braking-gate')

    fails: list[str] = []
    if base['safety_ok']:
        fails.append('baseline (mult=1, T=0) unexpectedly passed safety gate')
    if not front['safety_ok']:
        fails.append(f'frontier (mult=0.5, T=30) failed safety: '
                     f'max_hypo={front["components"]["ascent_max_hypo_rate"]:.4f}')
    if front['score'] <= base['score']:
        fails.append(f'frontier score {front["score"]:.4f} not > '
                     f'baseline {base["score"]:.4f}')
    if not per['safety_ok']:
        fails.append(f'per-patient mode failed safety: '
                     f'max_hypo={per["components"]["ascent_max_hypo_rate"]:.4f}')
    if per['meta']['n_dropped_braking'] == 0:
        fails.append('per-patient mode dropped zero events for braking gate '
                     '(phenotype parquet not loaded?)')

    print(f"baseline:    score={base['score']:.4f}  safety={base['safety_ok']}")
    print(f"frontier:    score={front['score']:.4f}  safety={front['safety_ok']}")
    print(f"per_patient: score={per['score']:.4f}  safety={per['safety_ok']}  "
          f"events_used={per['meta']['n_events_used']}/{per['meta']['n_events_total']}")

    if fails:
        for f in fails:
            print(f'  FAIL: {f}')
        return 1
    print('OK: all v3 smoke-test assertions pass.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
