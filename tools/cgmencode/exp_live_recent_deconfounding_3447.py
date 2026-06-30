#!/usr/bin/env python3
"""EXP-3447: live-recent deconfounding and safety-gated action audit.

This experiment asks whether the live-recent report is too conservative, or
whether unannounced meals and Loop compensation still make parameter changes
unsafe. It runs 30/60/90 day windows, unions production inferred meals with
hybrid support metadata, and separates:

1. basal evidence that survives meal and bolus exclusions,
2. ISF evidence before and after inferred-meal exclusion,
3. CR readiness based on high-support inferred meals only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cgmencode.mlflow_utils import log_dict, log_text, start_run
from cgmencode.production.metabolic_engine import _extract_hours
from cgmencode.production.pipeline import run_pipeline
from cgmencode.production.types import (
    DetectedMeal,
    PatientData,
    PatientProfile,
    SettingsParameter,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET_DIR = ROOT / "externals" / "ns-parquet" / "live-recent"
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3447_live_recent_deconfounding.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3447_live_recent_deconfounding.md"

WINDOW_DAYS = (30, 60, 90)
BLOCKS = {
    "overnight": (0, 6),
    "morning": (6, 12),
    "afternoon": (12, 18),
    "evening": (18, 24),
}


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value


def _safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if np.isfinite(out) else default


def _profile_timezone(parquet_dir: Path, patient_id: str) -> str:
    profiles_path = parquet_dir / "profiles.parquet"
    if not profiles_path.exists():
        return "UTC"
    try:
        pdf = pd.read_parquet(profiles_path, columns=["patient_id", "timezone"])
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


def _subset_last_days(df: pd.DataFrame, days: int) -> pd.DataFrame:
    cutoff = df["time"].max() - pd.Timedelta(days=days)
    return df[df["time"] >= cutoff].copy().reset_index(drop=True)


def _glycemic(glucose: np.ndarray) -> dict[str, float | int]:
    g = glucose[np.isfinite(glucose)]
    if len(g) == 0:
        return {"n": 0}
    return {
        "n": int(len(g)),
        "tir": float(np.mean((g >= 70.0) & (g <= 180.0))),
        "tbr": float(np.mean(g < 70.0)),
        "tbr54": float(np.mean(g < 54.0)),
        "tar": float(np.mean(g > 180.0)),
        "mean_mgdl": float(np.mean(g)),
        "cv_pct": float(100.0 * np.std(g) / max(np.mean(g), 1.0)),
    }


def _meal_masks(n: int, meals: list[DetectedMeal]) -> dict[str, np.ndarray]:
    masks = {
        "any": np.zeros(n, dtype=bool),
        "strong": np.zeros(n, dtype=bool),
        "moderate_or_strong": np.zeros(n, dtype=bool),
    }
    for meal in meals:
        idx = int(meal.index)
        if idx < 0 or idx >= n:
            continue
        lo = max(0, idx - 24)       # 2 h before detector center
        hi = min(n, idx + 49)       # 4 h after detector center
        support = (meal.metadata or {}).get("hybrid_meal_support", {})
        level = str(support.get("support_level", "weak"))
        masks["any"][lo:hi] = True
        if level == "strong":
            masks["strong"][lo:hi] = True
        if level in {"strong", "moderate"}:
            masks["moderate_or_strong"][lo:hi] = True
    return masks


def _mask_summary(meals: list[DetectedMeal]) -> dict[str, Any]:
    levels = {"strong": 0, "moderate": 0, "weak": 0, "unknown": 0}
    carbs_by_level: dict[str, list[float]] = {k: [] for k in levels}
    announced = 0
    for meal in meals:
        support = (meal.metadata or {}).get("hybrid_meal_support", {})
        level = str(support.get("support_level", "unknown"))
        if level not in levels:
            level = "unknown"
        levels[level] += 1
        carbs_by_level[level].append(float(getattr(meal, "estimated_carbs_g", 0.0) or 0.0))
        if bool(getattr(meal, "announced", False)):
            announced += 1
    return {
        "n_meals": int(len(meals)),
        "announced": int(announced),
        "unannounced": int(len(meals) - announced),
        "support_counts": levels,
        "median_carbs_by_support": {
            k: (float(np.median(v)) if v else None)
            for k, v in carbs_by_level.items()
        },
    }


def _window_mask_around(mask: np.ndarray, index: int, before: int = 24, after: int = 48) -> bool:
    lo = max(0, index - before)
    hi = min(len(mask), index + after + 1)
    return bool(mask[lo:hi].any())


def _summarize_corrections(events: list[dict[str, Any]], scheduled_isf: float) -> dict[str, Any]:
    if not events:
        return {
            "n": 0,
            "median_obs_isf": None,
            "median_gap_pct": None,
            "p_profile_too_strong": None,
            "p_profile_too_weak": None,
            "hypo_rate_4h": None,
        }
    obs = np.array([e["obs_isf"] for e in events if np.isfinite(e["obs_isf"])], dtype=float)
    if len(obs) == 0:
        return {"n": len(events)}
    rng = np.random.default_rng(3447)
    n_boot = 400
    boot = np.array([
        np.median(obs[rng.integers(0, len(obs), size=len(obs))])
        for _ in range(n_boot)
    ])
    median_obs = float(np.median(obs))
    gap = 100.0 * (median_obs - scheduled_isf) / max(scheduled_isf, 1e-6)
    return {
        "n": int(len(events)),
        "median_obs_isf": median_obs,
        "median_gap_pct": float(gap),
        "boot_ci": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
        "p_profile_too_strong": float(np.mean(boot > scheduled_isf * 1.30)),
        "p_profile_too_weak": float(np.mean(boot < scheduled_isf * 0.70)),
        "hypo_rate_4h": float(np.mean([bool(e["went_below_70"]) for e in events])),
        "rebound_rate_4h": float(np.mean([bool(e["rebound"]) for e in events])),
        "median_dose_u": float(np.median([e["dose"] for e in events])),
        "median_drop_4h": float(np.median([e["drop_4h"] for e in events])),
    }


def _correction_audit(
    df: pd.DataFrame,
    meal_masks: dict[str, np.ndarray],
    scheduled_isf: float,
) -> dict[str, Any]:
    glucose = df["glucose"].to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    if "bolus_smb" in df:
        bolus = bolus + df["bolus_smb"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    events: list[dict[str, Any]] = []
    for i in range(len(df) - 48):
        dose = float(bolus[i])
        if dose < 0.5 or not np.isfinite(glucose[i]) or glucose[i] < 180.0:
            continue
        lo = max(0, i - 12)
        hi = min(len(df), i + 13)
        if float(np.nansum(carbs[lo:hi])) > 5.0:
            continue
        window = glucose[i:i + 49]
        if np.isfinite(window).sum() < 12:
            continue
        start = float(glucose[i])
        end = float(glucose[i + 48])
        nadir = float(np.nanmin(window))
        post_nadir = window[int(np.nanargmin(window)) + 1:]
        peak_after = float(np.nanmax(post_nadir)) if len(post_nadir) else nadir
        drop = start - end
        events.append({
            "index": i,
            "dose": dose,
            "drop_4h": drop,
            "obs_isf": drop / max(dose, 0.01),
            "went_below_70": bool(np.nanmin(window) < 70.0),
            "rebound": bool(peak_after - nadir > 30.0),
            "contaminated_any_inferred": _window_mask_around(meal_masks["any"], i),
            "contaminated_strong_hybrid": _window_mask_around(meal_masks["strong"], i),
            "contaminated_moderate_or_strong_hybrid": _window_mask_around(
                meal_masks["moderate_or_strong"], i
            ),
        })
    groups = {
        "naive_logged_only": events,
        "exclude_any_inferred": [
            e for e in events if not e["contaminated_any_inferred"]
        ],
        "exclude_strong_hybrid": [
            e for e in events if not e["contaminated_strong_hybrid"]
        ],
        "exclude_moderate_or_strong_hybrid": [
            e for e in events if not e["contaminated_moderate_or_strong_hybrid"]
        ],
    }
    summary = {
        name: _summarize_corrections(rows, scheduled_isf)
        for name, rows in groups.items()
    }
    summary["contamination"] = {
        "n_naive": int(len(events)),
        "n_any_inferred": int(sum(e["contaminated_any_inferred"] for e in events)),
        "n_strong_hybrid": int(sum(e["contaminated_strong_hybrid"] for e in events)),
        "n_moderate_or_strong_hybrid": int(
            sum(e["contaminated_moderate_or_strong_hybrid"] for e in events)
        ),
    }
    return summary


def _basal_block_audit(
    df: pd.DataFrame,
    hours: np.ndarray,
    meal_masks: dict[str, np.ndarray],
) -> dict[str, Any]:
    glucose = df["glucose"].to_numpy(dtype=float)
    scheduled = df["scheduled_basal_rate"].to_numpy(dtype=float)
    actual = df["actual_basal_rate"].to_numpy(dtype=float)
    ratio = actual / np.where(scheduled > 0, scheduled, np.nan)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float) if "cob" in df else np.zeros(len(df))
    iob = df["iob"].fillna(0.0).to_numpy(dtype=float) if "iob" in df else np.zeros(len(df))
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float) if "bolus" in df else np.zeros(len(df))
    roc = df["glucose_roc"].fillna(0.0).to_numpy(dtype=float) if "glucose_roc" in df else np.zeros(len(df))
    exercise = df["exercise_active"].fillna(False).astype(bool).to_numpy() if "exercise_active" in df else np.zeros(len(df), dtype=bool)
    override = df["override_active"].fillna(False).astype(bool).to_numpy() if "override_active" in df else np.zeros(len(df), dtype=bool)
    bolus_4h = pd.Series(bolus).rolling(48, min_periods=1).sum().to_numpy()
    clean = (
        np.isfinite(glucose)
        & np.isfinite(ratio)
        & (cob <= 1.0)
        & (iob <= 4.0)
        & (bolus_4h < 0.1)
        & (np.abs(roc) <= 1.0)
        & (~exercise)
        & (~override)
        & (~meal_masks["any"])
    )
    out: dict[str, Any] = {}
    for name, (lo, hi) in BLOCKS.items():
        if lo < hi:
            block = (hours >= lo) & (hours < hi)
        else:
            block = (hours >= lo) | (hours < hi)
        mask = clean & block
        n = int(mask.sum())
        if n < 50:
            out[name] = {"n_clean": n, "status": "insufficient"}
            continue
        g = glucose[mask]
        r = ratio[mask]
        out[name] = {
            "n_clean": n,
            "median_glucose": float(np.nanmedian(g)),
            "tir": float(np.mean((g >= 70.0) & (g <= 180.0))),
            "tbr": float(np.mean(g < 70.0)),
            "tar": float(np.mean(g > 180.0)),
            "median_actual_over_scheduled": float(np.nanmedian(r)),
            "p_loop_increasing_gt_115pct": float(np.mean(r > 1.15)),
            "p_loop_reducing_lt_85pct": float(np.mean(r < 0.85)),
            "safe_basal_increase_candidate": bool(
                np.nanmedian(r) > 1.10
                and np.mean(r > 1.15) >= 0.45
                and np.mean(g < 70.0) < 0.04
                and np.nanmedian(g) > 140.0
            ),
        }
    return out


def _settings_summary(result) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for rec in getattr(result, "settings_recs", None) or []:
        param = rec.parameter.value if hasattr(rec.parameter, "value") else str(rec.parameter)
        if param in out:
            old = out[param]
            if abs(float(rec.predicted_tir_delta)) <= abs(float(old.get("predicted_tir_delta", 0.0))):
                continue
        out[param] = {
            "direction": rec.direction,
            "current_value": rec.current_value,
            "suggested_value": rec.suggested_value,
            "magnitude_pct": rec.magnitude_pct,
            "predicted_tir_delta": rec.predicted_tir_delta,
            "confidence": rec.confidence,
            "evidence": rec.evidence,
            "affected_hours": rec.affected_hours,
        }
    for param in (SettingsParameter.BASAL_RATE, SettingsParameter.ISF, SettingsParameter.CR):
        key = param.value
        out.setdefault(key, None)
    return out


def _audit_window(df: pd.DataFrame, patient_id: str, timezone_name: str, days: int) -> dict[str, Any]:
    sub = _subset_last_days(df, days)
    profile = _make_profile(sub, timezone_name)
    patient = _make_patient(sub, profile, patient_id)
    result = run_pipeline(patient, skip_patterns=False)
    meals = list(getattr(getattr(result, "meal_history", None), "meals", None) or [])
    masks = _meal_masks(len(sub), meals)
    hours = _extract_hours(patient.timestamps, profile.timezone)
    glucose = sub["glucose"].to_numpy(dtype=float)
    clinical = getattr(result, "clinical_report", None)
    return {
        "days": days,
        "n_rows": int(len(sub)),
        "glycemic": _glycemic(glucose),
        "meal_support": _mask_summary(meals),
        "meal_logging_qc": _jsonable(getattr(result, "meal_logging_qc", None)),
        "settings": _settings_summary(result),
        "correction_audit": _correction_audit(
            sub, masks, _safe_float(sub["scheduled_isf"].median(), 40.0)
        ),
        "basal_block_audit": _basal_block_audit(sub, hours, masks),
        "loop_workload": _jsonable(getattr(result, "loop_workload", None)),
        "overnight_assessment": _jsonable(getattr(result, "overnight_assessment", None)),
        "clinical_effective_isf": getattr(clinical, "effective_isf", None),
        "clinical_profile_isf": getattr(clinical, "profile_isf", None),
        "warnings": list(getattr(result, "warnings", []) or []),
    }


def _evidence_conclusion(windows: list[dict[str, Any]]) -> dict[str, Any]:
    by_days = {int(w["days"]): w for w in windows}
    candidate_counts: dict[str, int] = {name: 0 for name in BLOCKS}
    latest_tbr_ok: dict[str, bool] = {}
    latest = by_days.get(30) or windows[0]
    for block in BLOCKS:
        for w in windows:
            b = (w.get("basal_block_audit") or {}).get(block) or {}
            if b.get("safe_basal_increase_candidate"):
                candidate_counts[block] += 1
        lb = (latest.get("basal_block_audit") or {}).get(block) or {}
        latest_tbr_ok[block] = bool(lb.get("tbr", 1.0) < 0.04)
    stable_basal_blocks = [
        block for block, count in candidate_counts.items()
        if count >= 2 and latest_tbr_ok.get(block, False)
    ]

    isf_clean = (by_days.get(90) or windows[-1])["correction_audit"]["exclude_any_inferred"]
    isf_contam = (by_days.get(90) or windows[-1])["correction_audit"]["contamination"]
    p_strong = isf_clean.get("p_profile_too_strong")
    p_weak = isf_clean.get("p_profile_too_weak")
    n_clean = int(isf_clean.get("n") or 0)

    return {
        "basal_less_conservative_candidate": bool(stable_basal_blocks),
        "stable_basal_blocks": stable_basal_blocks,
        "basal_candidate_rule": (
            "At least 2 of 3 windows have clean-block median actual/scheduled >1.10, "
            "p(actual>115%) >=0.45, TBR<4%, and median glucose >140."
        ),
        "basal_suggested_action": (
            "Consider a basal-only 10% practical step in stable blocks with two-week TBR guardrail."
            if stable_basal_blocks else
            "Do not relax basal gate yet; evidence is not stable across windows."
        ),
        "isf_should_not_strengthen": bool(n_clean < 10 or (p_weak is not None and p_weak < 0.7)),
        "isf_clean_correction_events": n_clean,
        "isf_clean_p_profile_too_strong": p_strong,
        "isf_clean_p_profile_too_weak": p_weak,
        "isf_contamination": isf_contam,
        "isf_suggested_action": (
            "Hold ISF strengthening. Clean correction sample is sparse and meal contamination is material."
            if n_clean < 10 else
            "Use clean correction bootstrap only; do not use logged-carb-only events for ISF direction."
        ),
        "cr_should_remain_gated": True,
        "cr_suggested_action": (
            "Use hybrid meal support as CR evidence metadata only until validated high-support windows "
            "show stable CR direction without announced-meal dependence."
        ),
    }


def _render_memo(result: dict[str, Any]) -> str:
    conclusion = result["conclusion"]
    lines = [
        "# EXP-3447 live-recent deconfounding audit",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Basal less-conservative candidate: **{conclusion['basal_less_conservative_candidate']}**",
        f"- Stable basal blocks: {', '.join(conclusion['stable_basal_blocks']) or 'none'}",
        f"- ISF should not be strengthened: **{conclusion['isf_should_not_strengthen']}**",
        f"- Clean correction events after inferred-meal exclusion: {conclusion['isf_clean_correction_events']}",
        f"- CR remains gated: **{conclusion['cr_should_remain_gated']}**",
        "",
        "## Window summary",
        "",
        "| Window | TIR | TBR | TAR | Meals | Strong hybrid | Basal rec conf | ISF rec conf | Clean corrections |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for w in result["windows"]:
        g = w["glycemic"]
        meal = w["meal_support"]
        settings = w["settings"]
        basal = settings.get("basal_rate") or {}
        isf = settings.get("isf") or {}
        corr = w["correction_audit"]["exclude_any_inferred"]
        lines.append(
            f"| {w['days']}d | {g['tir']*100:.1f}% | {g['tbr']*100:.2f}% | "
            f"{g['tar']*100:.1f}% | {meal['n_meals']} | "
            f"{meal['support_counts'].get('strong', 0)} | "
            f"{basal.get('confidence', 0) or 0:.2f} | "
            f"{isf.get('confidence', 0) or 0:.2f} | {corr.get('n', 0)} |"
        )
    lines.extend([
        "",
        "## Suggested safe policy implication",
        "",
        conclusion["basal_suggested_action"],
        "",
        conclusion["isf_suggested_action"],
        "",
        conclusion["cr_suggested_action"],
        "",
    ])
    return "\n".join(lines)


def run_experiment(
    patient_id: str = "live-recent",
    parquet_dir: Path = DEFAULT_PARQUET_DIR,
    out_json: Path = OUT_JSON,
) -> dict[str, Any]:
    grid_path = parquet_dir / "grid.parquet"
    df_all = pd.read_parquet(grid_path)
    df = df_all[df_all["patient_id"] == patient_id].copy()
    if df.empty:
        raise SystemExit(f"No rows for patient_id={patient_id!r} in {grid_path}")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    timezone_name = _profile_timezone(parquet_dir, patient_id)

    windows = [_audit_window(df, patient_id, timezone_name, days) for days in WINDOW_DAYS]
    result = {
        "exp": "EXP-3447",
        "title": "live-recent deconfounding and safety-gated action audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": timezone_name,
        "windows": windows,
        "conclusion": _evidence_conclusion(windows),
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(_jsonable(result), indent=2, default=str))
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    memo = _render_memo(result)
    OUT_MD.write_text(memo)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", default="live-recent")
    parser.add_argument("--parquet-dir", type=Path, default=DEFAULT_PARQUET_DIR)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    args = parser.parse_args()

    with start_run(
        run_name="research-live-recent-deconfounding",
        tags={"runner": "exp_live_recent_deconfounding_3447", "exp": "EXP-3447"},
        params={
            "patient_id": args.patient_id,
            "parquet_dir": str(args.parquet_dir),
            "windows_days": list(WINDOW_DAYS),
        },
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3447_live_recent_deconfounding.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3447_live_recent_deconfounding.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
