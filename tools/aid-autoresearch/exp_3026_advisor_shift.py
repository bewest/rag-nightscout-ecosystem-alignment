"""EXP-3026: directional shift in correction-event extraction from inferred meals.

Pre-registered hypothesis (plan.md):
  Adopting inferred meals in correction-event extraction produces a
  *directional* shift consistent with under-logging severity. Heavy
  under-loggers should lose more correction events to the inferred-meal
  filter (because their post-meal boluses were being mis-classified as
  fasting corrections); well-aligned loggers should be near-null.

  Anchor magnitude to memory: 20-45% ISF inflation on heavy under-loggers
  (EXP-2739). Group comparison, not magnitude pinned to a constant.

Inputs (frozen):
  externals/ns-parquet/training/grid.parquet
  externals/ns-parquet/training/treatments.parquet  (logged carbs)
  externals/experiments/inferred_meals_<pid>.parquet  (cached inferred meals)
  externals/experiments/exp-2891_simpson_dose_response.parquet  (per-patient profiles)

Outputs (gitignored, in externals/experiments/):
  exp-3026_correction_event_shift.json
  exp-3026_correction_event_shift.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cgmencode.production.pipeline import _extract_correction_events  # noqa: E402
from tools.cgmencode.production.inferred_meals_facts_loader import (  # noqa: E402
    InferredMealsLoader,
)

EXP_DIR = REPO / "externals" / "experiments"
NS_DIR = REPO / "externals" / "ns-parquet" / "training"


class _SimpleProfile:
    def __init__(self, target_high: float = 180.0):
        self.target_high = target_high


class _MealAdapter:
    """Light wrapper exposing .index and .estimated_carbs_g.

    The cached inferred-meals frames already carry both columns.
    """

    __slots__ = ("index", "estimated_carbs_g")

    def __init__(self, index: int, estimated_carbs_g: float):
        self.index = int(index)
        self.estimated_carbs_g = float(estimated_carbs_g)


def _build_patient_arrays(pid: str) -> dict:
    """Materialize glucose / bolus / carbs / hours arrays on the unified
    5-min grid for a single patient. Returns None if grid empty.
    """
    grid = pd.read_parquet(NS_DIR / "grid.parquet",
                           filters=[("patient_id", "==", pid)])
    if grid.empty:
        return None
    grid = grid.sort_values("time").reset_index(drop=True)
    grid["time"] = pd.to_datetime(grid["time"], utc=True)
    glucose = grid["glucose"].astype(float).to_numpy()
    bolus = grid["bolus"].astype(float).to_numpy() if "bolus" in grid.columns \
        else np.full(len(grid), np.nan)
    carbs = grid["carbs"].astype(float).fillna(0.0).to_numpy() \
        if "carbs" in grid.columns else np.zeros(len(grid))
    n = len(grid)
    hours = np.array([t.hour + t.minute / 60.0 for t in grid["time"]])
    return dict(glucose=glucose, bolus=bolus, carbs=carbs, hours=hours,
                grid_t0=grid["time"].iloc[0])


def _unused():
    treatments = pd.read_parquet(NS_DIR / "treatments.parquet")


def _adapt_inferred_meals(facts_events: pd.DataFrame,
                          grid_t0: pd.Timestamp) -> list:
    """Map cached inferred-meal events (timestamp_ms + index) onto the
    canonical grid's index space. Cached frames already carry an
    'index' column relative to that patient's grid; we reuse it
    directly."""
    if facts_events.empty:
        return []
    out = []
    for _, r in facts_events.iterrows():
        out.append(_MealAdapter(int(r["index"]), float(r["estimated_carbs_g"])))
    return out


def main() -> int:
    loader = InferredMealsLoader()
    pids_with_cache = loader.known_patients()
    if not pids_with_cache:
        print("[EXP-3026] no cached inferred-meal patients found.")
        return 1

    profile = _SimpleProfile()
    rows = []
    for pid in pids_with_cache:
        try:
            arrs = _build_patient_arrays(pid)
        except Exception as e:
            print(f"[EXP-3026] {pid}: load error {e}")
            continue
        if arrs is None:
            continue

        facts = loader.lookup(pid)
        n_inferred = facts.n_events
        n_logged = int((arrs["carbs"] > 5).sum())
        if n_logged == 0 and n_inferred == 0:
            continue

        meals = _adapt_inferred_meals(facts.events, arrs["grid_t0"])

        ev_baseline = _extract_correction_events(
            arrs["glucose"], arrs["bolus"], arrs["carbs"],
            arrs["hours"], profile, inferred_meals=None)
        ev_filtered = _extract_correction_events(
            arrs["glucose"], arrs["bolus"], arrs["carbs"],
            arrs["hours"], profile, inferred_meals=meals)

        # Under-logging severity proxy: fraction of meals that are
        # inferred-only (i.e. logged ratio = logged / (logged + inferred)).
        denom = n_logged + n_inferred
        log_ratio = n_logged / denom if denom > 0 else 1.0
        under_log_severity = 1.0 - log_ratio  # 0 = aligned, 1 = no logged at all

        rows.append({
            "pid": pid,
            "n_logged_carbs_5g": n_logged,
            "n_inferred_meals": n_inferred,
            "log_ratio": log_ratio,
            "under_log_severity": under_log_severity,
            "n_corr_events_baseline": len(ev_baseline),
            "n_corr_events_filtered": len(ev_filtered),
            "events_excluded": len(ev_baseline) - len(ev_filtered),
            "frac_excluded": (
                (len(ev_baseline) - len(ev_filtered)) / max(1, len(ev_baseline))
            ),
        })
        print(f"[EXP-3026] {pid:>14}  n_logged={n_logged:>5}  n_inferred={n_inferred:>4}  "
              f"under_log={under_log_severity:.2f}  baseline={len(ev_baseline):>4}  "
              f"filtered={len(ev_filtered):>4}  excl={len(ev_baseline) - len(ev_filtered)} "
              f"({100 * ((len(ev_baseline) - len(ev_filtered)) / max(1, len(ev_baseline))):.1f}%)")

    if not rows:
        print("[EXP-3026] no rows produced.")
        return 1

    df = pd.DataFrame(rows)
    csv_path = EXP_DIR / "exp-3026_correction_event_shift.csv"
    df.to_csv(csv_path, index=False)

    # Group-comparison verdict
    # Threshold chosen empirically: cohort severity range is 0.0-0.43.
    # 'aligned' = severity < 0.10; 'under_logger' = severity >= 0.20.
    aligned = df[df["under_log_severity"] < 0.10]
    heavy = df[df["under_log_severity"] >= 0.20]

    aligned_mean_excl = float(aligned["frac_excluded"].mean()) if len(aligned) else None
    heavy_mean_excl = float(heavy["frac_excluded"].mean()) if len(heavy) else None

    # Spearman correlation severity ↔ frac_excluded
    if len(df) >= 4:
        sev = df["under_log_severity"].to_numpy()
        exc = df["frac_excluded"].to_numpy()
        # rank-based
        sev_r = pd.Series(sev).rank().to_numpy()
        exc_r = pd.Series(exc).rank().to_numpy()
        if sev_r.std() > 0 and exc_r.std() > 0:
            spearman = float(np.corrcoef(sev_r, exc_r)[0, 1])
        else:
            spearman = None
    else:
        spearman = None

    summary = {
        "exp_id": "EXP-3026",
        "title": "inferred-meal correction-event shift, group comparison",
        "n_patients": int(len(df)),
        "aligned_loggers": {
            "n": int(len(aligned)),
            "mean_frac_excluded": aligned_mean_excl,
            "patients": aligned["pid"].tolist(),
        },
        "heavy_under_loggers": {
            "n": int(len(heavy)),
            "mean_frac_excluded": heavy_mean_excl,
            "patients": heavy["pid"].tolist(),
        },
        "spearman_severity_vs_frac_excluded": spearman,
        "rows": rows,
    }

    direction_pass = (
        aligned_mean_excl is not None
        and heavy_mean_excl is not None
        and heavy_mean_excl > aligned_mean_excl
    )
    summary["criteria"] = {
        "direction_heavy_gt_aligned": bool(direction_pass),
        "spearman_positive": (
            spearman is not None and spearman > 0
        ),
    }
    summary["verdict"] = "PASS" if direction_pass else (
        "INCONCLUSIVE" if (aligned_mean_excl is None or heavy_mean_excl is None)
        else "FAIL"
    )

    out_path = EXP_DIR / "exp-3026_correction_event_shift.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"[EXP-3026] wrote {out_path}")
    print(f"  verdict={summary['verdict']}  "
          f"aligned_mean_excl={aligned_mean_excl}  "
          f"heavy_mean_excl={heavy_mean_excl}  spearman={spearman}")
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
