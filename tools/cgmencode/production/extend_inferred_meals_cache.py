"""Productionize inferred-meal cache for the full cohort.

Iterates the training grid and runs the production InferredMealsLoader.compute_for
for every patient that doesn't yet have a cached parquet. Idempotent: skips
patients with an existing cache file.

Output: externals/experiments/inferred_meals_<patient>.parquet (gitignored).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from tools.cgmencode.production.inferred_meals_facts_loader import (
    InferredMealsLoader,
)


def main() -> int:
    grid_path = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
    if not grid_path.exists():
        print(f"missing grid: {grid_path}", file=sys.stderr)
        return 1
    print(f"loading {grid_path}")
    grid = pd.read_parquet(grid_path)
    pids = sorted(grid["patient_id"].unique())
    print(f"cohort N = {len(pids)}")

    loader = InferredMealsLoader()
    cached = set(loader.known_patients())
    print(f"already cached: {sorted(cached)}")

    todo = [p for p in pids if p not in cached]
    print(f"to compute: {len(todo)} patient(s)")

    summary_rows = []
    for i, pid in enumerate(todo, 1):
        sub = grid[grid["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        if sub.empty:
            print(f"[{i}/{len(todo)}] {pid}: empty grid, skipping")
            continue
        t0 = time.time()
        try:
            facts = loader.compute_for(pid, sub)
        except Exception as exc:
            print(f"[{i}/{len(todo)}] {pid}: ERROR {exc!r}")
            summary_rows.append({"patient_id": pid, "n_events": -1,
                                 "elapsed_s": time.time() - t0,
                                 "error": repr(exc)})
            continue
        elapsed = time.time() - t0
        print(f"[{i}/{len(todo)}] {pid}: {facts.n_events} events ({elapsed:.1f}s)")
        summary_rows.append({"patient_id": pid, "n_events": facts.n_events,
                             "elapsed_s": elapsed, "error": ""})

    # Print final inventory
    loader = InferredMealsLoader()  # fresh, re-scan disk
    print()
    print("Final cache inventory:")
    for p in sorted(loader.known_patients()):
        f = loader.lookup(p)
        n_logged = int((grid[grid["patient_id"] == p]["carbs"].fillna(0) > 0).sum())
        sev = (f.n_events / (f.n_events + n_logged)) if (f.n_events + n_logged) else 0.0
        print(f"  {p:24s}  inferred={f.n_events:5d}  logged={n_logged:5d}  severity={sev:.3f}")

    if summary_rows:
        out = REPO / "externals" / "experiments" / "inferred_meals_cohort_extension.csv"
        pd.DataFrame(summary_rows).to_csv(out, index=False)
        print(f"\nSummary written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
