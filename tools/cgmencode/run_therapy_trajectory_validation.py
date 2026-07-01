#!/usr/bin/env python3
"""Run the predictive-signal validation ("AUC-proof") and controller-lineage
stratification steps against a built cohort trajectory table, and log the
results as a tracked MLflow evidence artifact.

Usage:
    python -m tools.cgmencode.run_therapy_trajectory_validation \
        --turns-parquet externals/experiments/therapy-trajectory-state/turns_full_cohort.parquet
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .mlflow_utils import build_run_context, log_dict, log_metrics, start_run
from .production.therapy_trajectory_predictive_validation import (
    compare_feature_sets,
    controller_stratified_summary,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TURNS_PARQUET = (
    ROOT / "externals" / "experiments" / "therapy-trajectory-state" / "turns_full_cohort.parquet"
)
DEFAULT_OUTPUT = (
    ROOT / "externals" / "experiments" / "therapy-trajectory-state"
    / "predictive_validation_summary.json"
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--turns-parquet", default=str(DEFAULT_TURNS_PARQUET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    df = pd.read_parquet(args.turns_parquet)

    feature_comparison = compare_feature_sets(df)
    controller_summary = controller_stratified_summary(df)
    summary = {
        "feature_comparison": feature_comparison,
        "controller_stratification": controller_summary,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))

    run_context = build_run_context(
        task_type="therapy-trajectory-state",
        result_type="predictive-validation",
        artifact_role="evidence",
        data_source="nightscout",
        experiment_family="state-aware-harness-parallels",
    )
    with start_run(
        run_name="therapy-trajectory-predictive-validation",
        tags={"runner": "run_therapy_trajectory_validation", **run_context["tags"]},
        params={"turns_parquet": args.turns_parquet, **run_context["params"]},
    ):
        metrics = {
            "auc_baseline": feature_comparison["baseline"]["auc_pooled"],
            "auc_full": feature_comparison["full"]["auc_pooled"],
            "delta_auc_from_physiology": feature_comparison["delta_auc_from_physiology_features"],
            "n_samples": feature_comparison["n_samples"],
            "n_groups": feature_comparison["n_groups"],
        }
        if controller_summary.get("n_patients_with_known_controller"):
            metrics["n_patients_with_known_controller"] = (
                controller_summary["n_patients_with_known_controller"]
            )
            metrics["controller_identity_within_patient_lift"] = (
                controller_summary.get("controller_identity_within_patient_lift")
            )
        log_metrics({k: v for k, v in metrics.items() if v is not None})
        log_dict(summary, "therapy_trajectory_state/predictive_validation_summary.json")


if __name__ == "__main__":
    main()
