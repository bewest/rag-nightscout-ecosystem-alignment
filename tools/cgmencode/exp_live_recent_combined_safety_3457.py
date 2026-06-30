#!/usr/bin/env python3
"""EXP-3457: live-recent combined basal + ISF safety stress.

EXP-3456 says a low ISF candidate can minimize a simple predictive RMSE, but
programming a lower ISF makes Loop correction dosing more aggressive through
both temp-basal and automatic-bolus paths. This experiment separates those
concepts by stress-testing additional insulin from:

1. the +10% 06:00-12:00 basal step, and
2. lower programmed ISF candidates (30 and 27.6 mg/dL/U),

under two correction-delivery assumptions:

* observed-corrections-only: scale only boluses that actually happened;
* clean-high-BG-opportunity: add one conservative correction per clean high-BG
  episode, separated by >=3h, to model what a more aggressive controller might
  attempt.

The output is a safety guardrail audit, not a controller simulator.
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

from cgmencode.exp_live_recent_basal_replay_3449 import DEFAULT_PARQUET_DIR
from cgmencode.exp_live_recent_uam_autosens_3454 import _rapid_activity_kernel
from cgmencode.mlflow_utils import log_dict, log_text, start_run


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3457_live_recent_combined_safety.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3457_live_recent_combined_safety.md"

CURRENT_ISF = 40.0
ISF_CANDIDATES = (30.0, 27.6)
TARGET_BG = 110.0
BASAL_BLOCK = (6.0, 12.0)
BASAL_STEP_PCT = 0.10


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


def _metrics(bg: np.ndarray, mask: np.ndarray | None = None) -> dict[str, float | int]:
    arr = np.asarray(bg, dtype=float)
    if mask is not None:
        arr = arr[mask]
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {"n": 0}
    return {
        "n": int(len(arr)),
        "tir": float(np.mean((arr >= 70) & (arr <= 180))),
        "tbr": float(np.mean(arr < 70)),
        "tbr54": float(np.mean(arr < 54)),
        "tar": float(np.mean(arr > 180)),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p90": float(np.percentile(arr, 90)),
    }


def _activity_effect(units: np.ndarray, isf: float) -> np.ndarray:
    kernel = _rapid_activity_kernel(5.0)
    return np.convolve(units, kernel, mode="full")[:len(units)] * isf


def _basal_units(df: pd.DataFrame, hours: np.ndarray, mode: str) -> np.ndarray:
    scheduled = df["scheduled_basal_rate"].fillna(0.0).to_numpy(dtype=float)
    actual = df["actual_basal_rate"].fillna(0.0).to_numpy(dtype=float)
    median_sched = float(np.nanmedian(scheduled[scheduled > 0]))
    extra_rate = median_sched * BASAL_STEP_PCT
    block = (hours >= BASAL_BLOCK[0]) & (hours < BASAL_BLOCK[1])
    units = np.zeros(len(df), dtype=float)
    if mode == "none" or mode == "controller_replacement":
        return units
    if mode == "half_additive":
        units[block] = extra_rate * 0.5 / 12.0
        return units
    if mode == "full_additive":
        units[block] = extra_rate / 12.0
        return units
    if mode == "floor_risk":
        new_sched = median_sched + extra_rate
        units[block] = np.maximum(new_sched - actual[block], 0.0) / 12.0
        return units
    raise ValueError(mode)


def _observed_correction_extra(df: pd.DataFrame, new_isf: float) -> np.ndarray:
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    glucose = df["glucose"].to_numpy(dtype=float)
    factor = CURRENT_ISF / new_isf - 1.0
    units = np.zeros(len(df), dtype=float)
    mask = (bolus > 0.1) & np.isfinite(glucose) & (glucose >= 150)
    units[mask] = bolus[mask] * factor
    return np.maximum(units, 0.0)


def _clean_high_bg_opportunity_extra(df: pd.DataFrame, new_isf: float) -> np.ndarray:
    glucose = df["glucose"].to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    units = np.zeros(len(df), dtype=float)
    last = -10_000
    for i in range(72, len(df) - 72):
        if i - last < 36:  # >=3h apart
            continue
        bg = glucose[i]
        if not np.isfinite(bg) or bg < 180:
            continue
        if np.nansum(bolus[max(0, i - 72):i + 1]) > 0.3:
            continue
        if cob[i] > 1.0 or np.nansum(carbs[max(0, i - 24):min(len(df), i + 49)]) > 2.0:
            continue
        # Extra correction from changing ISF setting, capped to a conservative
        # incremental dose so this remains a stress test, not a full controller.
        extra = max(bg - TARGET_BG, 0.0) * (1.0 / new_isf - 1.0 / CURRENT_ISF)
        units[i] = min(max(extra, 0.0), 1.0)
        last = i
    return units


def _simulate(df: pd.DataFrame, *, new_isf: float, basal_mode: str, correction_mode: str) -> dict[str, Any]:
    glucose = df["glucose"].to_numpy(dtype=float)
    ts = pd.to_datetime(df["time"], utc=True)
    # Fixed profile timezone used in live-recent artifacts.
    local = ts.dt.tz_convert("Etc/GMT+7")
    hours = local.dt.hour.to_numpy() + local.dt.minute.to_numpy() / 60.0
    block_mask = (hours >= BASAL_BLOCK[0]) & (hours < BASAL_BLOCK[1])

    basal_units = _basal_units(df, hours, basal_mode)
    if correction_mode == "none":
        corr_units = np.zeros(len(df), dtype=float)
    elif correction_mode == "observed_corrections_only":
        corr_units = _observed_correction_extra(df, new_isf)
    elif correction_mode == "clean_high_bg_opportunity":
        corr_units = _clean_high_bg_opportunity_extra(df, new_isf)
    else:
        raise ValueError(correction_mode)
    extra_units = basal_units + corr_units
    sim = np.clip(glucose - _activity_effect(extra_units, new_isf), 40, 400)
    base_block = _metrics(glucose, block_mask)
    sim_block = _metrics(sim, block_mask)
    base_all = _metrics(glucose)
    sim_all = _metrics(sim)
    return {
        "new_isf": new_isf,
        "basal_mode": basal_mode,
        "correction_mode": correction_mode,
        "extra_units_total": float(np.sum(extra_units)),
        "extra_units_per_day": float(np.sum(extra_units) / max((ts.max() - ts.min()).total_seconds() / 86400.0, 1.0)),
        "extra_correction_events": int(np.sum(corr_units > 0)),
        "overall": sim_all,
        "block": sim_block,
        "delta_overall_tbr_pp": float((sim_all["tbr"] - base_all["tbr"]) * 100.0),
        "delta_block_tbr_pp": float((sim_block["tbr"] - base_block["tbr"]) * 100.0),
        "delta_overall_tir_pp": float((sim_all["tir"] - base_all["tir"]) * 100.0),
        "delta_block_tir_pp": float((sim_block["tir"] - base_block["tir"]) * 100.0),
    }


def _conclusion(rows: list[dict[str, Any]]) -> dict[str, Any]:
    combined = [
        r for r in rows
        if r["new_isf"] in ISF_CANDIDATES
        and r["basal_mode"] in {"half_additive", "full_additive", "floor_risk"}
        and r["correction_mode"] != "none"
    ]
    unsafe = [
        r for r in combined
        if r["delta_overall_tbr_pp"] > 1.0 or r["overall"]["tbr"] >= 0.04
        or r["delta_block_tbr_pp"] > 1.0 or r["block"]["tbr"] >= 0.04
    ]
    return {
        "combine_basal_and_lower_isf_supported": False,
        "unsafe_or_guardrail_fail_count": int(len(unsafe)),
        "combined_scenarios_tested": int(len(combined)),
        "interpretation": (
            "The low-ISF validation signal is not enough to combine a lower programmed ISF with basal titration. In Loop, lower programmed ISF can increase both moderated temp basal and automatic bolus recommendations; this coarse stress test does not show a large TBR increase, but the dosing pathway is speculative and lacks clean correction-event evidence."
        ),
        "recommendation": (
            "Keep the basal-first single-parameter plan. Treat ISF 27-30 as a model signal requiring prospective clean correction evidence, not as a setting to combine with basal."
        ),
    }


def _render_memo(payload: dict[str, Any]) -> str:
    c = payload["conclusion"]
    lines = [
        "# EXP-3457 live-recent combined basal + ISF safety stress",
        "",
        f"Generated: {payload['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Combine basal and lower ISF supported: **{c['combine_basal_and_lower_isf_supported']}**",
        f"- Guardrail-failing combined scenarios: {c['unsafe_or_guardrail_fail_count']} / {c['combined_scenarios_tested']}",
        "",
        c["interpretation"],
        "",
        c["recommendation"],
        "",
        "## Scenario rows",
        "",
        "| ISF | Basal mode | Correction mode | Extra U/day | Overall TBR | ΔTBR pp | Block TBR | ΔBlock TBR pp |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        if row["correction_mode"] == "none" and row["basal_mode"] == "none":
            continue
        lines.append(
            f"| {row['new_isf']:.1f} | {row['basal_mode']} | {row['correction_mode']} | "
            f"{row['extra_units_per_day']:.3f} | {row['overall']['tbr']*100:.2f}% | "
            f"{row['delta_overall_tbr_pp']:+.2f} | {row['block']['tbr']*100:.2f}% | "
            f"{row['delta_block_tbr_pp']:+.2f} |"
        )
    lines.append("")
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
    rows = []
    for new_isf in ISF_CANDIDATES:
        for basal_mode in ("none", "controller_replacement", "half_additive", "full_additive", "floor_risk"):
            for corr_mode in ("none", "observed_corrections_only", "clean_high_bg_opportunity"):
                rows.append(_simulate(df, new_isf=new_isf, basal_mode=basal_mode, correction_mode=corr_mode))
    payload = {
        "exp": "EXP-3457",
        "title": "live-recent combined basal + ISF safety stress",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "rows": rows,
        "conclusion": _conclusion(rows),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(_jsonable(payload), indent=2, default=str))
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(_render_memo(payload))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", default="live-recent")
    parser.add_argument("--parquet-dir", type=Path, default=DEFAULT_PARQUET_DIR)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    args = parser.parse_args()
    with start_run(
        run_name="research-live-recent-combined-safety",
        tags={"runner": "exp_live_recent_combined_safety_3457", "exp": "EXP-3457"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3457_live_recent_combined_safety.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3457_live_recent_combined_safety.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
