#!/usr/bin/env python3
"""Build labeled per-patient therapy-trajectory turns for a cohort.

Concrete build step from the state-aware-harness parallel analysis in
``docs/60-research/state-aware-harness-parallels-2026-07-01.md``: walks
each patient's real longitudinal grid in fixed 72h turns, computes
continuous emission features (glycemic, activity, flux/EGP, saturation,
glycogen-loading proxy, site wear) plus a cheap rule-based ADA-threshold
outcome label, and writes the result as a tracked MLflow evidence
artifact (a parquet table, not a promoted recommendation).

Usage:
    python -m tools.cgmencode.run_therapy_trajectory_state \
        --parquet-dir externals/ns-parquet/training \
        --output externals/experiments/therapy-trajectory-state/training.parquet

    # Restrict to specific patients:
    python -m tools.cgmencode.run_therapy_trajectory_state --patient-ids a b c
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .mlflow_utils import (
    build_run_context,
    log_dict,
    log_metrics,
    log_artifact,
    start_run,
)
from .production.therapy_trajectory_state import (
    DEFAULT_TURN_HOURS,
    build_cohort_trajectories,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET_DIR = ROOT / "externals" / "ns-parquet" / "training"
DEFAULT_OUTPUT = (
    ROOT / "externals" / "experiments" / "therapy-trajectory-state" / "turns.parquet"
)


def _summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"n_patients": 0, "n_turns": 0, "state_counts": {}}
    state_counts = df["state"].value_counts().to_dict()
    reliable = df[df["data_completeness"] >= 0.5]
    by_state_tir = (
        reliable.groupby("state")["tir"].mean().round(1).to_dict()
        if not reliable.empty else {}
    )
    weekend_corr = None
    if len(reliable) > 2 and reliable["weekend_day_fraction"].nunique() > 1:
        weekend_corr = round(
            float(reliable["tir"].corr(reliable["weekend_day_fraction"])), 3
        )
    return {
        "n_patients": int(df["patient_id"].nunique()),
        "n_turns": int(len(df)),
        "state_counts": {str(k): int(v) for k, v in state_counts.items()},
        "mean_tir_by_state": by_state_tir,
        "tir_vs_weekend_fraction_corr": weekend_corr,
        "n_physiology_available": int(df["physiology_available"].sum()),
        "saturation_level_counts": {
            str(k): int(v) for k, v in df["saturation_level"].value_counts().items()
        },
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parquet-dir", default=str(DEFAULT_PARQUET_DIR))
    parser.add_argument("--patient-ids", nargs="*", default=None)
    parser.add_argument("--turn-hours", type=float, default=DEFAULT_TURN_HOURS)
    parser.add_argument("--min-turns", type=int, default=4)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    parquet_dir = Path(args.parquet_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    run_context = build_run_context(
        task_type="therapy-trajectory-state",
        result_type="labeled-turn-table",
        artifact_role="evidence",
        patients_dir=str(parquet_dir),
        data_source="nightscout",
        split_strategy="sequential-fixed-window",
        split_details={"turn_hours": args.turn_hours},
        experiment_family="state-aware-harness-parallels",
    )
    with start_run(
        run_name="therapy-trajectory-state",
        tags={"runner": "run_therapy_trajectory_state", **run_context["tags"]},
        params={
            "parquet_dir": str(parquet_dir),
            "turn_hours": args.turn_hours,
            "min_turns": args.min_turns,
            **run_context["params"],
        },
    ):
        print(f"Building trajectories from {parquet_dir} (turn_hours={args.turn_hours}) ...")
        df = build_cohort_trajectories(
            parquet_dir, patient_ids=args.patient_ids,
            turn_hours=args.turn_hours, min_turns=args.min_turns,
        )
        df.to_parquet(output_path)
        print(f"Wrote {len(df)} turns for {df['patient_id'].nunique() if not df.empty else 0} "
              f"patients -> {output_path}")

        summary = _summarize(df)
        print(json.dumps(summary, indent=2))

        log_metrics({
            "n_patients": summary["n_patients"],
            "n_turns": summary["n_turns"],
            "n_physiology_available": summary["n_physiology_available"],
        })
        log_dict(summary, "therapy_trajectory_state/summary.json")
        log_dict(run_context["manifest"], "metadata/run_context.json")
        log_artifact(output_path, artifact_path="therapy_trajectory_state")


if __name__ == "__main__":
    main()
