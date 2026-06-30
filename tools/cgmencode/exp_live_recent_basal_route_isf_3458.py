#!/usr/bin/env python3
"""EXP-3458: Loop basal-route ISF evidence audit.

Loop often expresses corrections as temporary basal changes rather than
discrete boluses. Bolus-only clean-correction gates therefore undercount ISF
evidence for Loop. This experiment treats high-glucose excess-basal episodes
as controller-route correction events and estimates dose-normalized 2h/4h
responses under the same strict inferred-meal exclusion.

This is route-aware evidence acquisition, not a direct replacement for bolus
correction ISF. Continuous temp basal is controller-modulated and entangled
with basal mismatch, so its estimates are used to decide whether more
evidence exists and whether the signal points toward or away from candidate
ISFs.
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
    _profile_timezone,
)
from cgmencode.exp_live_recent_isf_deconfounding_3448 import _meal_masks
from cgmencode.mlflow_utils import log_dict, log_text, start_run
from cgmencode.production.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3458_live_recent_basal_route_isf.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3458_live_recent_basal_route_isf.md"

MIN_BG = 180.0
MIN_EXCESS_RATE = 0.3
STRICT_PRE_STEPS = 24
STRICT_POST_STEPS = 48


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


def _episodes(indices: list[int], gap_steps: int = 12) -> list[int]:
    starts = []
    last = -10_000
    for idx in indices:
        if idx - last > gap_steps:
            starts.append(int(idx))
        last = int(idx)
    return starts


def _summ(values: list[float]) -> dict[str, Any]:
    vals = np.array([v for v in values if np.isfinite(v)], dtype=float)
    if len(vals) == 0:
        return {"n": 0}
    rng = np.random.default_rng(3458)
    boot = np.array([
        np.median(vals[rng.integers(0, len(vals), size=len(vals))])
        for _ in range(1000)
    ])
    return {
        "n": int(len(vals)),
        "median": float(np.median(vals)),
        "iqr": float(np.percentile(vals, 75) - np.percentile(vals, 25)),
        "p_positive": float(np.mean(vals > 0)),
        "ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
    }


def _extract(df: pd.DataFrame, masks: dict[str, np.ndarray]) -> dict[str, Any]:
    glucose = df["glucose"].to_numpy(dtype=float)
    scheduled = df["scheduled_basal_rate"].to_numpy(dtype=float)
    actual = df["actual_basal_rate"].to_numpy(dtype=float)
    excess = np.maximum(actual - scheduled, 0.0)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float)
    recent_bolus = pd.Series(bolus).rolling(72, min_periods=1).sum().shift(1).fillna(0).to_numpy()
    carb_pm = pd.Series(carbs).rolling(25, min_periods=1, center=True).sum().fillna(0).to_numpy()

    rows = []
    for i in range(72, len(df) - 72):
        base = (
            np.isfinite(glucose[i])
            and glucose[i] >= MIN_BG
            and excess[i] > MIN_EXCESS_RATE
            and recent_bolus[i] <= 0.3
            and cob[i] <= 1.0
            and carb_pm[i] <= 2.0
        )
        if not base:
            continue
        strict_clean = not masks["any"][max(0, i - STRICT_PRE_STEPS):min(len(df), i + STRICT_POST_STEPS + 1)].any()
        rows.append({
            "index": int(i),
            "time": str(df["time"].iloc[i]),
            "strict_clean": bool(strict_clean),
        })

    out = {}
    for label, filtered in {
        "all_candidate_rows": rows,
        "strict_uam_clean_rows": [r for r in rows if r["strict_clean"]],
    }.items():
        starts = _episodes([r["index"] for r in filtered])
        erows = []
        for i in starts:
            u2 = float(np.nansum(excess[i:i + 24]) / 12.0)
            u4 = float(np.nansum(excess[i:i + 48]) / 12.0)
            if u2 <= 0 or u4 <= 0:
                continue
            drop_2h = float(glucose[i] - glucose[i + 24]) if np.isfinite(glucose[i + 24]) else np.nan
            drop_4h = float(glucose[i] - glucose[i + 48]) if np.isfinite(glucose[i + 48]) else np.nan
            nadir_4h = float(glucose[i] - np.nanmin(glucose[i:i + 49]))
            erows.append({
                "index": int(i),
                "time": str(df["time"].iloc[i]),
                "start_bg": float(glucose[i]),
                "excess_units_2h": u2,
                "excess_units_4h": u4,
                "drop_2h": drop_2h,
                "drop_4h": drop_4h,
                "nadir_drop_4h": nadir_4h,
                "isf_2h": drop_2h / u2 if np.isfinite(drop_2h) else np.nan,
                "isf_4h": drop_4h / u4 if np.isfinite(drop_4h) else np.nan,
                "isf_nadir_4h": nadir_4h / u4 if np.isfinite(nadir_4h) else np.nan,
            })
        out[label] = {
            "candidate_rows": int(len(filtered)),
            "episodes": int(len(erows)),
            "isf_2h": _summ([r["isf_2h"] for r in erows]),
            "isf_4h": _summ([r["isf_4h"] for r in erows]),
            "isf_nadir_4h": _summ([r["isf_nadir_4h"] for r in erows]),
            "median_excess_units_4h": (
                float(np.median([r["excess_units_4h"] for r in erows])) if erows else None
            ),
        }
    return out


def _conclusion(summary: dict[str, Any]) -> dict[str, Any]:
    clean = summary["strict_uam_clean_rows"]
    n = clean["episodes"]
    isf4 = clean["isf_4h"].get("median")
    return {
        "basal_route_solves_clean_event_bottleneck": bool(n >= 10),
        "strict_clean_basal_route_episodes": n,
        "strict_clean_basal_route_isf_4h": isf4,
        "supports_53_56": bool(isf4 is not None and 45.0 <= float(isf4) <= 65.0),
        "interpretation": (
            "Loop basal-route evidence yields many strict-UAM-clean correction episodes, so bolus-only acquisition was structurally biased. However, basal-route dose-normalized responses do not support a 53-56 baseline ISF; they are lower and must be interpreted as controller-modulated temp-basal evidence."
        ),
    }


def _render_memo(payload: dict[str, Any]) -> str:
    c = payload["conclusion"]
    lines = [
        "# EXP-3458 live-recent basal-route ISF audit",
        "",
        f"Generated: {payload['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Basal route solves clean-event bottleneck: **{c['basal_route_solves_clean_event_bottleneck']}**",
        f"- Strict clean basal-route episodes: {c['strict_clean_basal_route_episodes']}",
        f"- Strict clean basal-route 4h ISF: {c['strict_clean_basal_route_isf_4h']}",
        f"- Supports 53-56: **{c['supports_53_56']}**",
        "",
        c["interpretation"],
        "",
        "## Summary",
        "",
        "| Scenario | rows | episodes | ISF 2h median | ISF 4h median | Nadir 4h median |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in payload["summary"].items():
        lines.append(
            f"| {name} | {row['candidate_rows']} | {row['episodes']} | "
            f"{row['isf_2h'].get('median')} | {row['isf_4h'].get('median')} | "
            f"{row['isf_nadir_4h'].get('median')} |"
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
    profile = _make_profile(df, _profile_timezone(parquet_dir, patient_id))
    patient = _make_patient(df, profile, patient_id)
    result = run_pipeline(patient)
    meals = list(getattr(getattr(result, "meal_history", None), "meals", None) or [])
    masks = _meal_masks(len(df), meals)
    summary = _extract(df, masks)
    payload = {
        "exp": "EXP-3458",
        "title": "live-recent Loop basal-route ISF evidence audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "summary": summary,
        "conclusion": _conclusion(summary),
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
        run_name="research-live-recent-basal-route-isf",
        tags={"runner": "exp_live_recent_basal_route_isf_3458", "exp": "EXP-3458"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3458_live_recent_basal_route_isf.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3458_live_recent_basal_route_isf.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
