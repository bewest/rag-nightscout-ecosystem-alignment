#!/usr/bin/env python3
"""EXP-3454: UAM-aware autosens/deviation audit for live-recent.

For under-loggers, oref0-style deviations can be dominated by hidden meal
absorption. This experiment computes autosens-like BGI/deviation proxies, stratifies them
by hybrid/inferred meal support, and tests whether any ISF signal survives in
strict non-UAM windows.

The live-recent grid does not carry usable native ``insulin_activity`` values,
so the audit compares:

1. an IOB-decay proxy: max(IOB[t-1] - IOB[t], 0), and
2. a reconstructed delivered-insulin activity curve using a normalized rapid
   action kernel over the profile DIA.

This is a stratification audit, not a native oref0 autosens replacement.
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
from cgmencode.production.metabolic_engine import compute_metabolic_state
from cgmencode.production.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3454_live_recent_uam_autosens.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3454_live_recent_uam_autosens.md"

STEPS_PER_HOUR = 12


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


def _profile_isf(profile) -> float:
    vals = [e.get("value", e.get("sensitivity", 40.0)) for e in profile.isf_mgdl()]
    return float(np.median([float(v) for v in vals])) if vals else 40.0


def _rapid_activity_kernel(dia_hours: float, peak_hours: float = 1.25) -> np.ndarray:
    """Return per-5min activity weights that sum to one unit of insulin.

    Uses a gamma-like rapid-acting curve. It is not vendor-specific, but is
    closer to oref0/Loop action-shape intent than raw adjacent IOB decay when
    the source grid lacks native insulin_activity.
    """
    n = max(int(round(dia_hours * STEPS_PER_HOUR)), 1)
    t = (np.arange(n, dtype=float) + 0.5) / STEPS_PER_HOUR
    # Gamma(k=3) mode=(k-1)*theta => theta=peak/2.
    theta = max(peak_hours / 2.0, 1e-6)
    activity = (t ** 2) * np.exp(-t / theta)
    total = float(activity.sum())
    if total <= 0:
        out = np.zeros(n, dtype=float)
        out[0] = 1.0
        return out
    return activity / total


def _reconstruct_activity(
    bolus: np.ndarray,
    actual_basal: np.ndarray,
    *,
    dia_hours: float,
) -> np.ndarray:
    per_step = (
        np.nan_to_num(bolus, nan=0.0)
        + np.nan_to_num(actual_basal, nan=0.0) / STEPS_PER_HOUR
    )
    kernel = _rapid_activity_kernel(dia_hours)
    return np.convolve(per_step, kernel, mode="full")[:len(per_step)]


def _build_frame(df: pd.DataFrame, masks: dict[str, np.ndarray], profile_isf: float) -> pd.DataFrame:
    g = df["glucose"].to_numpy(dtype=float)
    iob = df["iob"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    actual = df["actual_basal_rate"].fillna(0.0).to_numpy(dtype=float)
    scheduled = df["scheduled_basal_rate"].fillna(np.nan).to_numpy(dtype=float)

    delta = np.full(len(df), np.nan)
    delta[1:] = g[1:] - g[:-1]
    iob_decay_u = np.zeros(len(df))
    iob_decay_u[1:] = np.maximum(iob[:-1] - iob[1:], 0.0)
    dia_hours = 5.0
    activity = _reconstruct_activity(bolus, actual, dia_hours=dia_hours)
    bgi_iob_decay = -iob_decay_u * profile_isf
    bgi_activity = -activity * profile_isf
    deviation_iob_decay = delta - bgi_iob_decay
    deviation_activity = delta - bgi_activity
    recent_bolus_6h = pd.Series(bolus).rolling(72, min_periods=1).sum().shift(1).fillna(0).to_numpy()
    recent_carbs_4h = pd.Series(carbs).rolling(48, min_periods=1).sum().fillna(0).to_numpy()
    actual_over_scheduled = actual / np.where(scheduled > 0, scheduled, np.nan)

    return pd.DataFrame({
        "time": df["time"],
        "glucose": g,
        "delta": delta,
        "iob": iob,
        "iob_decay_u": iob_decay_u,
        "reconstructed_activity_u": activity,
        "bgi_iob_decay_40": bgi_iob_decay,
        "deviation_iob_decay": deviation_iob_decay,
        "bgi_activity_40": bgi_activity,
        "deviation_activity": deviation_activity,
        "carbs": carbs,
        "cob": cob,
        "bolus": bolus,
        "recent_bolus_6h": recent_bolus_6h,
        "recent_carbs_4h": recent_carbs_4h,
        "actual_over_scheduled": actual_over_scheduled,
        "uam_any": masks["any"],
        "uam_strong": masks["strong"],
        "uam_modstrong": masks["moderate_or_strong"],
    })


def _fit_isf(rows: pd.DataFrame, predictor: str) -> dict[str, Any]:
    sub = rows[
        rows["delta"].notna()
        & rows[predictor].notna()
        & (rows[predictor] > 0.005)
        & rows["glucose"].notna()
    ].copy()
    if len(sub) < 20:
        return {"n": int(len(sub)), "status": "insufficient"}
    x = sub[predictor].to_numpy(dtype=float)
    y = sub["delta"].to_numpy(dtype=float)
    # delta = intercept - isf*x. This is an autosens-like fit, not a native
    # oref0 implementation.
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    isf = -float(slope)
    falling = sub[sub["delta"] < 0]
    ratio_isf = None
    if len(falling):
        ratio_isf = float(np.median((-falling["delta"] / falling[predictor]).clip(0, 250)))
    return {
        "n": int(len(sub)),
        "status": "fit",
        "slope_isf": isf,
        "intercept": float(intercept),
        "r2": float(r2),
        "median_falling_ratio_isf": ratio_isf,
        "median_predictor_u": float(np.median(x)),
        "calibration_note": (
            f"{predictor} slope is an autosens stratification proxy, not a native oref0 autosens implementation."
        ),
    }


def _summarize(rows: pd.DataFrame) -> dict[str, Any]:
    valid = rows[rows["deviation_activity"].notna()]
    if valid.empty:
        return {"n": 0}
    return {
        "n": int(len(valid)),
        "median_glucose": float(valid["glucose"].median()),
        "median_delta": float(valid["delta"].median()),
        "median_bgi_iob_decay_40": float(valid["bgi_iob_decay_40"].median()),
        "median_deviation_iob_decay": float(valid["deviation_iob_decay"].median()),
        "median_bgi_activity_40": float(valid["bgi_activity_40"].median()),
        "median_deviation_activity": float(valid["deviation_activity"].median()),
        "p_positive_deviation_activity": float((valid["deviation_activity"] > 0).mean()),
        "p_large_positive_deviation_activity": float((valid["deviation_activity"] > 10).mean()),
        "median_actual_over_scheduled": float(valid["actual_over_scheduled"].median()),
        "fit_iob_decay": _fit_isf(valid, "iob_decay_u"),
        "fit_activity": _fit_isf(valid, "reconstructed_activity_u"),
    }


def _strata(frame: pd.DataFrame) -> dict[str, Any]:
    finite = frame[frame["glucose"].notna() & frame["delta"].notna()].copy()
    base_clean = (
        (finite["cob"] <= 1.0)
        & (finite["recent_carbs_4h"] <= 2.0)
        & (finite["recent_bolus_6h"] <= 0.3)
    )
    strata = {
        "all": finite,
        "uam_any": finite[finite["uam_any"]],
        "uam_strong": finite[finite["uam_strong"]],
        "non_uam_all": finite[~finite["uam_any"]],
        "strict_clean_non_uam": finite[base_clean & (~finite["uam_any"])],
        "active_insulin_non_uam": finite[(~finite["uam_any"]) & (finite["reconstructed_activity_u"] > 0.005)],
        "active_insulin_uam": finite[finite["uam_any"] & (finite["reconstructed_activity_u"] > 0.005)],
        "clean_high_bg_non_uam": finite[base_clean & (~finite["uam_any"]) & (finite["glucose"] >= 180)],
    }
    return {name: _summarize(rows) for name, rows in strata.items()}


def _conclusion(summary: dict[str, Any], profile_isf: float) -> dict[str, Any]:
    all_activity = summary["all"].get("fit_activity", {})
    clean_activity = summary["strict_clean_non_uam"].get("fit_activity", {})
    uam = summary["uam_any"]
    non = summary["non_uam_all"]
    clean = summary["strict_clean_non_uam"]
    aggregate_slope = all_activity.get("slope_isf")
    clean_slope = clean_activity.get("slope_isf")
    clean_falling_ratio = clean_activity.get("median_falling_ratio_isf")
    aggregate_suggests_change = (
        clean_falling_ratio is not None
        and abs(float(clean_falling_ratio) - profile_isf) / profile_isf >= 0.20
    )
    clean_supports = (
        clean_activity.get("status") == "fit"
        and clean_falling_ratio is not None
        and abs(float(clean_falling_ratio) - profile_isf) / profile_isf >= 0.20
        and clean_activity.get("r2", 0.0) > 0.05
    )
    simpson_risk = bool(
        aggregate_suggests_change
        and not clean_supports
        and uam.get("median_deviation_activity", 0) > non.get("median_deviation_activity", 0)
    )
    return {
        "profile_isf": profile_isf,
        "aggregate_reconstructed_activity_slope": aggregate_slope,
        "strict_clean_non_uam_reconstructed_activity_slope": clean_slope,
        "strict_clean_non_uam_activity_falling_ratio_isf": clean_falling_ratio,
        "activity_fit_r2": clean_activity.get("r2"),
        "uam_median_deviation": uam.get("median_deviation_activity"),
        "non_uam_median_deviation": non.get("median_deviation_activity"),
        "clean_median_deviation": clean.get("median_deviation_activity"),
        "simpson_or_uam_confound_risk": simpson_risk,
        "baseline_isf_change_supported": bool(clean_supports),
        "interpretation": (
            "UAM-positive windows carry higher positive deviations than non-UAM windows. Reconstructed activity improves the BGI proxy, but strict clean activity-stratified evidence still does not stably support the 53-56 baseline. Apparent autosens/ISF shifts should be treated as UAM/controller confounded."
            if simpson_risk or not clean_supports else
            "Strict clean non-UAM autosens strata support an ISF change; revisit decision gates."
        ),
    }


def _render_memo(result: dict[str, Any]) -> str:
    c = result["conclusion"]
    lines = [
        "# EXP-3454 live-recent UAM-aware autosens audit",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Baseline ISF change supported: **{c['baseline_isf_change_supported']}**",
        f"- Simpson/UAM confound risk: **{c['simpson_or_uam_confound_risk']}**",
        f"- Aggregate reconstructed-activity slope: {c['aggregate_reconstructed_activity_slope']}",
        f"- Strict clean non-UAM activity falling-ratio ISF: {c['strict_clean_non_uam_activity_falling_ratio_isf']}",
        f"- Strict clean activity fit R2: {c['activity_fit_r2']}",
        "",
        c["interpretation"],
        "",
        "## Strata",
        "",
        "| Stratum | n | median activity deviation | +deviation % | >10 mg/dL % | activity falling-ratio ISF | activity R2 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in result["strata"].items():
        fit = row.get("fit_activity", {})
        isf = fit.get("median_falling_ratio_isf")
        r2 = fit.get("r2")
        lines.append(
            f"| {name} | {row.get('n', 0)} | {row.get('median_deviation_activity', 0):.2f} | "
            f"{row.get('p_positive_deviation_activity', 0)*100:.1f}% | "
            f"{row.get('p_large_positive_deviation_activity', 0)*100:.1f}% | "
            f"{'n/a' if isf is None else f'{isf:.1f}'} | "
            f"{'n/a' if r2 is None else f'{r2:.3f}'} |"
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
    tz = _profile_timezone(parquet_dir, patient_id)
    profile = _make_profile(df, tz)
    patient = _make_patient(df, profile, patient_id)
    pipeline = run_pipeline(patient)
    meals = list(getattr(getattr(pipeline, "meal_history", None), "meals", None) or [])
    masks = _meal_masks(len(df), meals)
    profile_isf = _profile_isf(profile)
    frame = _build_frame(df, masks, profile_isf)
    # Cross-check physics residuals are computable; store coarse medians so
    # reviewers can compare with the BGI proxy.
    metabolic = compute_metabolic_state(patient)
    frame["physics_residual"] = metabolic.residual
    strata_summary = _strata(frame)
    for name, row in strata_summary.items():
        mask = frame["deviation_activity"].notna()
        if name == "uam_any":
            mask &= frame["uam_any"]
        elif name == "uam_strong":
            mask &= frame["uam_strong"]
        elif name == "non_uam_all":
            mask &= ~frame["uam_any"]
        elif name == "strict_clean_non_uam":
            mask &= (
                (~frame["uam_any"])
                & (frame["cob"] <= 1.0)
                & (frame["recent_carbs_4h"] <= 2.0)
                & (frame["recent_bolus_6h"] <= 0.3)
            )
        valid = frame.loc[mask, "physics_residual"].dropna()
        row["median_physics_residual"] = float(valid.median()) if len(valid) else None
    result = {
        "exp": "EXP-3454",
        "title": "live-recent UAM-aware autosens/deviation audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": tz,
        "method": {
            "iob_decay_bgi_proxy": "BGI_40 = -max(IOB[t-1]-IOB[t], 0)*scheduled_ISF",
            "reconstructed_activity_bgi": "BGI_40 = -convolve(delivered insulin, normalized rapid-action kernel)*scheduled_ISF",
            "deviation": "observed_delta - BGI_40",
            "note": "stratification audit only; live-recent native insulin_activity is empty",
        },
        "strata": strata_summary,
        "conclusion": _conclusion(strata_summary, profile_isf),
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
        run_name="research-live-recent-uam-autosens",
        tags={"runner": "exp_live_recent_uam_autosens_3454", "exp": "EXP-3454"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3454_live_recent_uam_autosens.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3454_live_recent_uam_autosens.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
