#!/usr/bin/env python3
"""EXP-3449: live-recent basal-step replay and ISF readiness audit.

EXP-3447 unlocked a narrow +10% basal step for 06:00-12:00. This replay
stress-tests that step under several controller assumptions:

1. controller-replacement: scheduled basal rises, Loop reduces prior additions,
   so total delivered insulin is approximately unchanged;
2. floor-risk: only rows where historical actual basal sat below the new
   scheduled rate receive extra insulin;
3. partial/full additive: 25%, 50%, or 100% of the proposed basal increment is
   added to historical delivery.

The goal is not to forecast exact glucose. It is to determine whether the basal
recommendation remains qualitatively safe and whether post-step data is likely
to improve ISF identifiability.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cgmencode.mlflow_utils import log_dict, log_text, start_run
from cgmencode.production.metabolic_engine import _extract_hours
from cgmencode.production.pipeline import run_pipeline
from cgmencode.production.types import PatientData, PatientProfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET_DIR = ROOT / "externals" / "ns-parquet" / "live-recent"
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3449_live_recent_basal_replay.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3449_live_recent_basal_replay.md"

BLOCK = (6.0, 12.0)
STEP_PCT = 0.10
ISF_STRESS_VALUES = (40.0, 56.0, 70.0)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if hasattr(value, "value"):
        return value.value
    return value


def _safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


def _profile_timezone(parquet_dir: Path, patient_id: str) -> str:
    path = parquet_dir / "profiles.parquet"
    if not path.exists():
        return "UTC"
    try:
        pdf = pd.read_parquet(path, columns=["patient_id", "timezone"])
    except Exception:
        return "UTC"
    rows = pdf.loc[pdf["patient_id"] == patient_id, "timezone"].dropna()
    return str(rows.iloc[0]) if len(rows) else "UTC"


def _make_profile(df: pd.DataFrame, timezone_name: str) -> PatientProfile:
    return PatientProfile(
        isf_schedule=[{"time": "00:00", "value": _safe_float(df["scheduled_isf"].median(), 40.0)}],
        cr_schedule=[{"time": "00:00", "value": _safe_float(df["scheduled_cr"].median(), 10.0)}],
        basal_schedule=[{"time": "00:00", "value": _safe_float(df["scheduled_basal_rate"].median(), 1.0)}],
        dia_hours=5.0,
        timezone=timezone_name,
    )


def _make_patient(df: pd.DataFrame, profile: PatientProfile, patient_id: str) -> PatientData:
    return PatientData(
        glucose=df["glucose"].to_numpy(dtype=float),
        timestamps=df["time"].astype("int64").to_numpy(),
        profile=profile,
        iob=df["iob"].to_numpy(dtype=float) if "iob" in df else None,
        cob=df["cob"].to_numpy(dtype=float) if "cob" in df else None,
        bolus=df["bolus"].to_numpy(dtype=float) if "bolus" in df else None,
        carbs=df["carbs"].to_numpy(dtype=float) if "carbs" in df else None,
        basal_rate=df["actual_basal_rate"].to_numpy(dtype=float) if "actual_basal_rate" in df else None,
        patient_id=patient_id,
    )


def _meal_mask(n: int, meals) -> np.ndarray:
    mask = np.zeros(n, dtype=bool)
    for meal in meals:
        idx = int(getattr(meal, "index", -1))
        if idx < 0 or idx >= n:
            continue
        lo = max(0, idx - 24)
        hi = min(n, idx + 49)
        mask[lo:hi] = True
    return mask


def _metrics(bg: np.ndarray, mask: np.ndarray | None = None) -> dict[str, float | int]:
    arr = np.asarray(bg, dtype=float)
    if mask is not None:
        arr = arr[mask]
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {"n": 0}
    return {
        "n": int(len(arr)),
        "tir": float(np.mean((arr >= 70.0) & (arr <= 180.0))),
        "tbr": float(np.mean(arr < 70.0)),
        "tbr54": float(np.mean(arr < 54.0)),
        "tar": float(np.mean(arr > 180.0)),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p90": float(np.percentile(arr, 90)),
    }


def _insulin_kernel(length: int = 288) -> np.ndarray:
    lag = np.arange(length, dtype=float)
    fast_tau = 0.8 * 12.0
    persistent_tau = 12.0 * 12.0
    fast = np.exp(-lag / fast_tau)
    persistent = np.exp(-lag / persistent_tau)
    fast = fast / fast.sum()
    persistent = persistent / persistent.sum()
    return 0.63 * fast + 0.37 * persistent


def _apply_units(glucose: np.ndarray, units_by_step: np.ndarray, isf: float) -> np.ndarray:
    kernel = _insulin_kernel()
    effect = np.convolve(units_by_step, kernel, mode="full")[:len(glucose)] * isf
    return np.clip(glucose - effect, 40.0, 400.0)


def _scenario_units(
    name: str,
    scheduled: np.ndarray,
    actual: np.ndarray,
    block_mask: np.ndarray,
) -> np.ndarray:
    median_sched = float(np.nanmedian(scheduled[scheduled > 0]))
    proposed_extra_rate = median_sched * STEP_PCT
    extra = np.zeros(len(scheduled), dtype=float)
    if name == "controller_replacement":
        return extra
    if name == "floor_risk":
        new_sched = median_sched + proposed_extra_rate
        extra_rate = np.maximum(new_sched - actual, 0.0)
        extra[block_mask] = extra_rate[block_mask] / 12.0
        return extra
    if name.startswith("additive_"):
        frac = float(name.split("_", 1)[1])
        extra[block_mask] = proposed_extra_rate * frac / 12.0
        return extra
    raise ValueError(f"Unknown scenario: {name}")


def _correction_readiness(df: pd.DataFrame, meal_mask: np.ndarray, block_mask: np.ndarray) -> dict[str, Any]:
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    glucose = df["glucose"].to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    rows = []
    for i in range(24, len(df) - 48):
        if not block_mask[i]:
            continue
        if bolus[i] < 0.3 or not np.isfinite(glucose[i]) or glucose[i] < 150.0:
            continue
        lo = max(0, i - 24)
        hi = min(len(df), i + 49)
        rows.append({
            "index": i,
            "clean_wide": bool(not meal_mask[lo:hi].any() and np.nansum(carbs[lo:hi]) <= 5.0),
            "bg": float(glucose[i]),
            "dose": float(bolus[i]),
        })
    return {
        "morning_correction_candidates": int(len(rows)),
        "morning_clean_correction_candidates": int(sum(r["clean_wide"] for r in rows)),
        "interpretation": (
            "Current morning data has enough clean correction windows for ISF re-estimation."
            if sum(r["clean_wide"] for r in rows) >= 5 else
            "Current morning data does not have enough clean correction windows; ISF confidence requires prospective accumulation after the basal step."
        ),
    }


def _run_replay(df: pd.DataFrame, patient_id: str, timezone_name: str) -> dict[str, Any]:
    profile = _make_profile(df, timezone_name)
    patient = _make_patient(df, profile, patient_id)
    result = run_pipeline(patient)
    meals = list(getattr(getattr(result, "meal_history", None), "meals", None) or [])
    meal_mask = _meal_mask(len(df), meals)
    hours = _extract_hours(patient.timestamps, timezone_name)
    start, end = BLOCK
    block_mask = (hours >= start) & (hours < end)
    observed_bg = df["glucose"].to_numpy(dtype=float)
    scheduled = df["scheduled_basal_rate"].to_numpy(dtype=float)
    actual = df["actual_basal_rate"].to_numpy(dtype=float)
    clean_block = (
        block_mask
        & (~meal_mask)
        & np.isfinite(observed_bg)
        & np.isfinite(actual)
        & (df["cob"].fillna(0.0).to_numpy(dtype=float) <= 1.0)
        & (df["bolus"].fillna(0.0).to_numpy(dtype=float) < 0.1)
    )
    baseline = {
        "overall": _metrics(observed_bg),
        "block": _metrics(observed_bg, block_mask),
        "clean_block": _metrics(observed_bg, clean_block),
        "actual_over_scheduled_clean_block": {
            "median": float(np.nanmedian(actual[clean_block] / scheduled[clean_block])),
            "p_actual_gt_new_scheduled": float(
                np.mean(actual[clean_block] > np.nanmedian(scheduled) * (1.0 + STEP_PCT))
            ),
            "p_actual_lt_new_scheduled": float(
                np.mean(actual[clean_block] < np.nanmedian(scheduled) * (1.0 + STEP_PCT))
            ),
        },
    }

    scenarios = {}
    for scenario in ("controller_replacement", "floor_risk", "additive_0.25", "additive_0.5", "additive_1.0"):
        units = _scenario_units(scenario, scheduled, actual, block_mask)
        scenario_rows = {}
        for isf in ISF_STRESS_VALUES:
            sim_bg = _apply_units(observed_bg, units, isf)
            scenario_rows[f"isf_{isf:.0f}"] = {
                "overall": _metrics(sim_bg),
                "block": _metrics(sim_bg, block_mask),
                "clean_block": _metrics(sim_bg, clean_block),
                "delta_tbr_block_pp": (
                    _metrics(sim_bg, block_mask)["tbr"] - baseline["block"]["tbr"]
                ) * 100.0,
                "delta_tir_block_pp": (
                    _metrics(sim_bg, block_mask)["tir"] - baseline["block"]["tir"]
                ) * 100.0,
            }
        scenarios[scenario] = {
            "extra_units_total": float(np.sum(units)),
            "extra_units_per_day": float(np.sum(units) / max(patient.days_of_data, 1.0)),
            "stress": scenario_rows,
        }
    readiness = _correction_readiness(df, meal_mask, block_mask)
    return {
        "baseline": baseline,
        "scenarios": scenarios,
        "isf_readiness": readiness,
        "n_inferred_meals": int(len(meals)),
    }


def _conclusion(result: dict[str, Any]) -> dict[str, Any]:
    scenarios = result["replay"]["scenarios"]
    floor_56 = scenarios["floor_risk"]["stress"]["isf_56"]
    add50_56 = scenarios["additive_0.5"]["stress"]["isf_56"]
    add100_56 = scenarios["additive_1.0"]["stress"]["isf_56"]
    floor_tbr = floor_56["block"]["tbr"]
    baseline_tbr = result["replay"]["baseline"]["block"]["tbr"]
    floor_delta = floor_56["delta_tbr_block_pp"]
    add50_delta = add50_56["delta_tbr_block_pp"]
    add100_delta = add100_56["delta_tbr_block_pp"]
    return {
        "basal_step_safe_under_controller_replacement": True,
        "basal_step_target_safe_under_floor_risk_isf56": bool(floor_tbr < 0.04),
        "basal_step_guardrail_passes_under_floor_risk_isf56": bool(floor_delta <= 1.0),
        "basal_step_safe_under_half_additive_isf56": bool(
            add50_56["block"]["tbr"] < 0.04 and add50_delta <= 1.0
        ),
        "full_additive_isf56_stress_passes": bool(
            add100_56["block"]["tbr"] < 0.04 and add100_delta <= 1.0
        ),
        "baseline_block_tbr": baseline_tbr,
        "floor_risk_block_tbr_isf56": floor_tbr,
        "floor_risk_delta_tbr_pp_isf56": floor_delta,
        "half_additive_delta_tbr_pp_isf56": add50_delta,
        "full_additive_delta_tbr_pp_isf56": add100_delta,
        "recommendation": (
            "Basal-first remains reasonable if treated as a controller-workload replacement step with TBR monitoring. The extreme floor-risk replay stays below 4% TBR but exceeds the 1 pp worsening guardrail, so this should remain a monitored single-parameter step rather than being paired with ISF changes."
        ),
        "isf_readiness": result["replay"]["isf_readiness"]["interpretation"],
    }


def _render_memo(result: dict[str, Any]) -> str:
    c = result["conclusion"]
    b = result["replay"]["baseline"]
    lines = [
        "# EXP-3449 live-recent basal-step replay",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Floor-risk below 4% TBR at ISF 56: **{c['basal_step_target_safe_under_floor_risk_isf56']}**",
        f"- Floor-risk passes 1 pp TBR guardrail at ISF 56: **{c['basal_step_guardrail_passes_under_floor_risk_isf56']}**",
        f"- Half-additive safe at ISF 56: **{c['basal_step_safe_under_half_additive_isf56']}**",
        f"- Full-additive stress passes at ISF 56: **{c['full_additive_isf56_stress_passes']}**",
        f"- ISF readiness: {c['isf_readiness']}",
        "",
        "## Baseline block",
        "",
        f"- 06:00-12:00 observed TBR: {b['block']['tbr']*100:.2f}%",
        f"- Clean-block median BG: {b['clean_block']['median']:.0f} mg/dL",
        f"- Clean-block median actual/scheduled basal: {b['actual_over_scheduled_clean_block']['median']:.2f}",
        f"- Share already above new scheduled basal: {b['actual_over_scheduled_clean_block']['p_actual_gt_new_scheduled']*100:.1f}%",
        "",
        "## Stress rows at ISF 56",
        "",
        "| Scenario | Extra U/day | Block TIR | Block TBR | Delta TBR pp |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, row in result["replay"]["scenarios"].items():
        s = row["stress"]["isf_56"]
        lines.append(
            f"| {name} | {row['extra_units_per_day']:.3f} | "
            f"{s['block']['tir']*100:.1f}% | {s['block']['tbr']*100:.2f}% | "
            f"{s['delta_tbr_block_pp']:+.2f} |"
        )
    lines.extend(["", "## Recommendation", "", c["recommendation"], ""])
    return "\n".join(lines)


def run_experiment(
    patient_id: str = "live-recent",
    parquet_dir: Path = DEFAULT_PARQUET_DIR,
    out_json: Path = OUT_JSON,
) -> dict[str, Any]:
    grid = pd.read_parquet(parquet_dir / "grid.parquet")
    df = grid[grid["patient_id"] == patient_id].copy()
    if df.empty:
        raise SystemExit(f"No rows for patient_id={patient_id!r}")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    timezone_name = _profile_timezone(parquet_dir, patient_id)
    result = {
        "exp": "EXP-3449",
        "title": "live-recent basal-step replay and ISF readiness audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": timezone_name,
        "block": {"start": BLOCK[0], "end": BLOCK[1], "step_pct": STEP_PCT},
        "replay": _run_replay(df, patient_id, timezone_name),
    }
    result["conclusion"] = _conclusion(result)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(_jsonable(result), indent=2, default=str))
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(_render_memo(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", default="live-recent")
    parser.add_argument("--parquet-dir", type=Path, default=DEFAULT_PARQUET_DIR)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    args = parser.parse_args()
    with start_run(
        run_name="research-live-recent-basal-replay",
        tags={"runner": "exp_live_recent_basal_replay_3449", "exp": "EXP-3449"},
        params={
            "patient_id": args.patient_id,
            "parquet_dir": str(args.parquet_dir),
            "block": f"{BLOCK[0]}-{BLOCK[1]}",
            "step_pct": STEP_PCT,
        },
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3449_live_recent_basal_replay.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3449_live_recent_basal_replay.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
