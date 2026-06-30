#!/usr/bin/env python3
"""EXP-3450: natural experiment audit for live-recent morning basal.

EXP-3447/3449 support a cautious +10% 06:00-12:00 basal step. This audit asks
whether historical mornings where Loop already delivered at least that proposed
rate behaved safely compared with matched lower-delivery windows.

This is not causal proof: Loop adds basal in response to worse glucose states.
The audit therefore uses within-stratum comparisons by starting glucose and
time block, and it interprets results as safety/readiness evidence rather than
as a direct treatment-effect estimate.
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

from cgmencode.exp_live_recent_basal_replay_3449 import (
    DEFAULT_PARQUET_DIR,
    _make_patient,
    _make_profile,
    _meal_mask,
    _profile_timezone,
)
from cgmencode.mlflow_utils import log_dict, log_text, start_run
from cgmencode.production.metabolic_engine import _extract_hours
from cgmencode.production.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3450_live_recent_basal_natural.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3450_live_recent_basal_natural.md"

BLOCK = (6.0, 12.0)
STEP_PCT = 0.10
FUTURE_STEPS = 24  # 2h
ANCHOR_STEP = 6    # 30 min, reduces autocorrelation


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


def _window_metric(glucose: np.ndarray, i: int) -> dict[str, float | bool]:
    win = glucose[i:i + FUTURE_STEPS + 1]
    valid = win[np.isfinite(win)]
    if len(valid) == 0:
        return {}
    return {
        "future_min": float(np.min(valid)),
        "future_end": float(valid[-1]),
        "future_delta": float(valid[-1] - valid[0]),
        "future_low": bool(np.min(valid) < 70.0),
        "future_tir": float(np.mean((valid >= 70.0) & (valid <= 180.0))),
        "future_tar": float(np.mean(valid > 180.0)),
    }


def _build_rows(df: pd.DataFrame, meal_mask: np.ndarray, timezone_name: str) -> pd.DataFrame:
    profile_basal = float(df["scheduled_basal_rate"].dropna().median())
    proposed = profile_basal * (1.0 + STEP_PCT)
    ts = df["time"].astype("int64").to_numpy()
    hours = _extract_hours(ts, timezone_name)
    glucose = df["glucose"].to_numpy(dtype=float)
    actual = df["actual_basal_rate"].to_numpy(dtype=float)
    scheduled = df["scheduled_basal_rate"].to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    iob = df["iob"].fillna(0.0).to_numpy(dtype=float)
    rows = []
    for i in range(0, len(df) - FUTURE_STEPS - 1, ANCHOR_STEP):
        if not (BLOCK[0] <= hours[i] < BLOCK[1]):
            continue
        if not (np.isfinite(glucose[i]) and np.isfinite(actual[i]) and np.isfinite(scheduled[i])):
            continue
        if meal_mask[max(0, i - 12):min(len(df), i + FUTURE_STEPS + 1)].any():
            continue
        if cob[i] > 1.0:
            continue
        if np.nansum(bolus[max(0, i - 24):i + 1]) > 0.1:
            continue
        metrics = _window_metric(glucose, i)
        if not metrics:
            continue
        start_bg = float(glucose[i])
        bg_bin = int(np.floor(start_bg / 20.0) * 20)
        hour_bin = "06-08" if hours[i] < 8 else "08-10" if hours[i] < 10 else "10-12"
        rows.append({
            "index": int(i),
            "time": str(df["time"].iloc[i]),
            "hour": float(hours[i]),
            "hour_bin": hour_bin,
            "start_bg": start_bg,
            "bg_bin": bg_bin,
            "iob": float(iob[i]),
            "actual_basal": float(actual[i]),
            "scheduled_basal": float(scheduled[i]),
            "actual_over_scheduled": float(actual[i] / max(scheduled[i], 1e-6)),
            "delivered_at_or_above_proposed": bool(actual[i] >= proposed),
            **metrics,
        })
    return pd.DataFrame(rows)


def _summarize_group(rows: pd.DataFrame) -> dict[str, Any]:
    if rows.empty:
        return {"n": 0}
    return {
        "n": int(len(rows)),
        "median_start_bg": float(rows["start_bg"].median()),
        "median_iob": float(rows["iob"].median()),
        "median_actual_over_scheduled": float(rows["actual_over_scheduled"].median()),
        "future_low_rate": float(rows["future_low"].mean()),
        "future_tir": float(rows["future_tir"].mean()),
        "future_tar": float(rows["future_tar"].mean()),
        "median_future_delta": float(rows["future_delta"].median()),
    }


def _matched_effect(rows: pd.DataFrame, *, min_per_arm: int = 3) -> dict[str, Any]:
    strata = []
    for (bg_bin, hour_bin), g in rows.groupby(["bg_bin", "hour_bin"]):
        hi = g[g["delivered_at_or_above_proposed"]]
        lo = g[~g["delivered_at_or_above_proposed"]]
        if len(hi) < min_per_arm or len(lo) < min_per_arm:
            continue
        weight = min(len(hi), len(lo))
        strata.append({
            "bg_bin": int(bg_bin),
            "hour_bin": str(hour_bin),
            "n_high": int(len(hi)),
            "n_low": int(len(lo)),
            "weight": int(weight),
            "start_bg_diff": float(hi["start_bg"].mean() - lo["start_bg"].mean()),
            "iob_diff": float(hi["iob"].mean() - lo["iob"].mean()),
            "future_low_rate_diff": float(hi["future_low"].mean() - lo["future_low"].mean()),
            "future_tir_diff": float(hi["future_tir"].mean() - lo["future_tir"].mean()),
            "future_tar_diff": float(hi["future_tar"].mean() - lo["future_tar"].mean()),
            "future_delta_diff": float(hi["future_delta"].mean() - lo["future_delta"].mean()),
        })
    if not strata:
        return {"n_strata": 0, "strata": []}
    total_w = sum(s["weight"] for s in strata)

    def wmean(key: str) -> float:
        return float(sum(s[key] * s["weight"] for s in strata) / total_w)

    return {
        "n_strata": int(len(strata)),
        "matched_weight": int(total_w),
        "weighted_start_bg_diff": wmean("start_bg_diff"),
        "weighted_iob_diff": wmean("iob_diff"),
        "weighted_future_low_rate_diff": wmean("future_low_rate_diff"),
        "weighted_future_tir_diff": wmean("future_tir_diff"),
        "weighted_future_tar_diff": wmean("future_tar_diff"),
        "weighted_future_delta_diff_mgdl": wmean("future_delta_diff"),
        "strata": strata,
    }


def _conclusion(summary: dict[str, Any]) -> dict[str, Any]:
    matched = summary["matched"]
    high = summary["groups"]["delivered_at_or_above_proposed"]
    low_diff = matched.get("weighted_future_low_rate_diff")
    enough = matched.get("matched_weight", 0) >= 30
    no_low_penalty = bool(low_diff is not None and low_diff <= 0.01)
    return {
        "natural_experiment_supports_safety": bool(enough and no_low_penalty),
        "matched_weight": matched.get("matched_weight", 0),
        "matched_future_low_rate_diff": low_diff,
        "high_delivery_future_low_rate": high.get("future_low_rate"),
        "interpretation": (
            "Matched clean morning windows where Loop already delivered at least the proposed basal rate do not show higher near-term low risk, supporting the basal-first safety case."
            if enough and no_low_penalty else
            "Natural-experiment support is limited or mixed: high-delivery windows are globally low-risk, but matched low-start strata are not strong enough to relax prospective TBR monitoring."
        ),
        "isf_implication": (
            "This adds basal safety context but does not create baseline ISF evidence; ISF should still wait for post-step clean correction windows."
        ),
    }


def _render_memo(result: dict[str, Any]) -> str:
    c = result["conclusion"]
    m = result["summary"]["matched"]
    groups = result["summary"]["groups"]
    lines = [
        "# EXP-3450 live-recent morning basal natural experiment",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Natural-experiment supports safety: **{c['natural_experiment_supports_safety']}**",
        f"- Matched weight: {c['matched_weight']}",
        f"- Matched future-low-rate difference: {c['matched_future_low_rate_diff'] if c['matched_future_low_rate_diff'] is not None else 'n/a'}",
        "",
        c["interpretation"],
        "",
        c["isf_implication"],
        "",
        "## Group summaries",
        "",
        "| Group | n | median start BG | median actual/scheduled | future low rate | future TIR | future delta |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in groups.items():
        lines.append(
            f"| {name} | {row.get('n', 0)} | {row.get('median_start_bg', 0):.0f} | "
            f"{row.get('median_actual_over_scheduled', 0):.2f} | "
            f"{row.get('future_low_rate', 0)*100:.2f}% | "
            f"{row.get('future_tir', 0)*100:.1f}% | "
            f"{row.get('median_future_delta', 0):+.1f} |"
        )
    lines.extend([
        "",
        "## Matched comparison",
        "",
        f"- Matched strata: {m.get('n_strata', 0)}",
        f"- Weighted future-low-rate difference: {m.get('weighted_future_low_rate_diff')}",
        f"- Weighted future-TIR difference: {m.get('weighted_future_tir_diff')}",
        f"- Weighted future-delta difference: {m.get('weighted_future_delta_diff_mgdl')} mg/dL",
        "",
    ])
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
    profile = _make_profile(df, timezone_name)
    patient = _make_patient(df, profile, patient_id)
    pipeline = run_pipeline(patient)
    meals = list(getattr(getattr(pipeline, "meal_history", None), "meals", None) or [])
    rows = _build_rows(df, _meal_mask(len(df), meals), timezone_name)
    high = rows[rows["delivered_at_or_above_proposed"]]
    low = rows[~rows["delivered_at_or_above_proposed"]]
    summary = {
        "n_rows": int(len(rows)),
        "proposed_basal_rate": float(df["scheduled_basal_rate"].median() * (1.0 + STEP_PCT)),
        "groups": {
            "delivered_at_or_above_proposed": _summarize_group(high),
            "below_proposed": _summarize_group(low),
        },
        "matched": _matched_effect(rows),
    }
    result = {
        "exp": "EXP-3450",
        "title": "live-recent morning basal natural experiment",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": timezone_name,
        "block": {"start": BLOCK[0], "end": BLOCK[1], "step_pct": STEP_PCT},
        "summary": summary,
        "conclusion": _conclusion(summary),
    }
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
        run_name="research-live-recent-basal-natural",
        tags={"runner": "exp_live_recent_basal_natural_3450", "exp": "EXP-3450"},
        params={
            "patient_id": args.patient_id,
            "parquet_dir": str(args.parquet_dir),
            "block": f"{BLOCK[0]}-{BLOCK[1]}",
            "step_pct": STEP_PCT,
        },
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3450_live_recent_basal_natural.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3450_live_recent_basal_natural.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
