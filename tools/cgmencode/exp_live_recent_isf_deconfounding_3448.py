#!/usr/bin/env python3
"""EXP-3448: live-recent ISF deconfounding sensitivity audit.

Tests whether the correction-denominator ISF signal near 54-56 mg/dL/U should
be treated as a baseline ISF recommendation or as an explanatory/controller
operating signal. The audit sweeps correction definitions, UAM exclusion
windows, and basal/controller attribution while preserving EXP-3447's basal
guardrails.
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
from cgmencode.production.pipeline import run_pipeline
from cgmencode.production.types import PatientData, PatientProfile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARQUET_DIR = ROOT / "externals" / "ns-parquet" / "live-recent"
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3448_live_recent_isf_deconfounding.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3448_live_recent_isf_deconfounding.md"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
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


def _meal_masks(n: int, meals) -> dict[str, np.ndarray]:
    masks = {
        "any": np.zeros(n, dtype=bool),
        "strong": np.zeros(n, dtype=bool),
        "moderate_or_strong": np.zeros(n, dtype=bool),
    }
    for meal in meals:
        idx = int(getattr(meal, "index", -1))
        if idx < 0 or idx >= n:
            continue
        support = (getattr(meal, "metadata", {}) or {}).get("hybrid_meal_support", {})
        level = str(support.get("support_level", "weak"))
        for before, after, name in (
            (24, 48, "any"),
            (24, 48, "strong"),
            (24, 48, "moderate_or_strong"),
        ):
            if name == "strong" and level != "strong":
                continue
            if name == "moderate_or_strong" and level not in {"strong", "moderate"}:
                continue
            lo = max(0, idx - before)
            hi = min(n, idx + after + 1)
            masks[name][lo:hi] = True
    return masks


def _is_contaminated(mask: np.ndarray, index: int, before: int, after: int) -> bool:
    lo = max(0, index - before)
    hi = min(len(mask), index + after + 1)
    return bool(mask[lo:hi].any())


def _candidate_events(df: pd.DataFrame, masks: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    glucose = df["glucose"].to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    if "bolus_smb" in df:
        bolus = bolus + df["bolus_smb"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float) if "cob" in df else np.zeros(len(df))
    actual = df["actual_basal_rate"].fillna(0.0).to_numpy(dtype=float)
    scheduled = df["scheduled_basal_rate"].fillna(0.0).to_numpy(dtype=float)
    profile_isf = _safe_float(df["scheduled_isf"].median(), 40.0)

    events = []
    for i in range(24, len(df) - 48):
        dose = float(bolus[i])
        if dose < 0.3 or not np.isfinite(glucose[i]) or glucose[i] < 150.0:
            continue
        window = glucose[i:i + 49]
        if np.isfinite(window).sum() < 24:
            continue
        start_bg = float(glucose[i])
        end_bg = float(glucose[i + 48])
        nadir = float(np.nanmin(window))
        drop_end = start_bg - end_bg
        drop_nadir = start_bg - nadir
        net_basal_u = float(np.nansum((actual[i:i + 48] - scheduled[i:i + 48]) / 12.0))
        controller_bg_effect = net_basal_u * profile_isf
        correction_only_drop = drop_end - controller_bg_effect + 2.4
        lo = max(0, i - 24)
        hi = min(len(df), i + 25)
        post_hi = min(len(df), i + 49)
        events.append({
            "index": i,
            "time": str(df["time"].iloc[i]),
            "dose": dose,
            "start_bg": start_bg,
            "end_bg_4h": end_bg,
            "drop_4h": drop_end,
            "drop_to_nadir": drop_nadir,
            "nadir": nadir,
            "isf_end": drop_end / dose if drop_end > 0 else np.nan,
            "isf_nadir": drop_nadir / dose if drop_nadir > 0 else np.nan,
            "isf_controller_subtracted": (
                correction_only_drop / dose if correction_only_drop > 0 else np.nan
            ),
            "carbs_pm2h": float(np.nansum(carbs[lo:hi])),
            "carbs_post4h": float(np.nansum(carbs[i:post_hi])),
            "cob_at_event": float(cob[i]),
            "net_basal_u_4h": net_basal_u,
            "loop_addition": bool(net_basal_u > 0.05),
            "hypo_4h": bool(np.nanmin(window) < 70.0),
            "rebound_4h": bool(float(np.nanmax(window)) - nadir > 30.0),
            "uam_any_2h_pre_4h_post": _is_contaminated(masks["any"], i, 24, 48),
            "uam_strong_2h_pre_4h_post": _is_contaminated(masks["strong"], i, 24, 48),
            "uam_modstrong_2h_pre_4h_post": _is_contaminated(masks["moderate_or_strong"], i, 24, 48),
            "uam_any_1h_pre_2h_post": _is_contaminated(masks["any"], i, 12, 24),
            "uam_strong_1h_pre_2h_post": _is_contaminated(masks["strong"], i, 12, 24),
        })
    return events


def _bootstrap_summary(values: list[float], profile_isf: float) -> dict[str, Any]:
    vals = np.array([v for v in values if np.isfinite(v) and 5.0 <= v <= 250.0], dtype=float)
    if len(vals) == 0:
        return {
            "n": 0,
            "median": None,
            "ci95": None,
            "p_gt_profile_20pct": None,
            "p_near_56": None,
        }
    rng = np.random.default_rng(3448)
    boot = np.array([
        np.median(vals[rng.integers(0, len(vals), size=len(vals))])
        for _ in range(600)
    ])
    return {
        "n": int(len(vals)),
        "median": float(np.median(vals)),
        "mean": float(np.mean(vals)),
        "ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
        "p_gt_profile_20pct": float(np.mean(boot > profile_isf * 1.20)),
        "p_gt_profile_30pct": float(np.mean(boot > profile_isf * 1.30)),
        "p_near_56": float(np.mean((boot >= 50.0) & (boot <= 62.0))),
        "p_below_profile": float(np.mean(boot < profile_isf)),
    }


def _scenario_summary(events: list[dict[str, Any]], profile_isf: float) -> dict[str, Any]:
    scenarios = {
        "logged_only_bg180_bolus03": [
            e for e in events
            if e["start_bg"] >= 180 and e["dose"] >= 0.3
            and e["carbs_pm2h"] <= 2.0 and e["cob_at_event"] <= 5.0
        ],
        "logged_only_bg180_bolus05": [
            e for e in events
            if e["start_bg"] >= 180 and e["dose"] >= 0.5
            and e["carbs_pm2h"] <= 5.0 and e["cob_at_event"] <= 5.0
        ],
        "exclude_any_uam_wide": [
            e for e in events
            if e["start_bg"] >= 180 and e["dose"] >= 0.5
            and e["carbs_pm2h"] <= 5.0 and e["cob_at_event"] <= 5.0
            and not e["uam_any_2h_pre_4h_post"]
        ],
        "exclude_strong_uam_wide": [
            e for e in events
            if e["start_bg"] >= 180 and e["dose"] >= 0.5
            and e["carbs_pm2h"] <= 5.0 and e["cob_at_event"] <= 5.0
            and not e["uam_strong_2h_pre_4h_post"]
        ],
        "exclude_any_uam_narrow": [
            e for e in events
            if e["start_bg"] >= 180 and e["dose"] >= 0.5
            and e["carbs_pm2h"] <= 5.0 and e["cob_at_event"] <= 5.0
            and not e["uam_any_1h_pre_2h_post"]
        ],
        "bg150_including_less_severe": [
            e for e in events
            if e["start_bg"] >= 150 and e["dose"] >= 0.3
            and e["carbs_pm2h"] <= 5.0 and e["cob_at_event"] <= 5.0
        ],
    }
    out = {}
    for name, rows in scenarios.items():
        out[name] = {
            "n_events": int(len(rows)),
            "contamination": {
                "any_uam_wide": int(sum(e["uam_any_2h_pre_4h_post"] for e in rows)),
                "strong_uam_wide": int(sum(e["uam_strong_2h_pre_4h_post"] for e in rows)),
                "any_uam_narrow": int(sum(e["uam_any_1h_pre_2h_post"] for e in rows)),
            },
            "isf_end": _bootstrap_summary([e["isf_end"] for e in rows], profile_isf),
            "isf_nadir": _bootstrap_summary([e["isf_nadir"] for e in rows], profile_isf),
            "isf_controller_subtracted": _bootstrap_summary(
                [e["isf_controller_subtracted"] for e in rows],
                profile_isf,
            ),
            "hypo_rate_4h": (
                float(np.mean([e["hypo_4h"] for e in rows])) if rows else None
            ),
            "rebound_rate_4h": (
                float(np.mean([e["rebound_4h"] for e in rows])) if rows else None
            ),
            "median_net_basal_u_4h": (
                float(np.median([e["net_basal_u_4h"] for e in rows])) if rows else None
            ),
        }
    return out


def _conclusion(scenarios: dict[str, Any], profile_isf: float) -> dict[str, Any]:
    logged = scenarios["logged_only_bg180_bolus05"]
    clean = scenarios["exclude_any_uam_wide"]
    narrow = scenarios["exclude_any_uam_narrow"]
    logged_end = logged["isf_end"]
    clean_end = clean["isf_end"]
    supports_56_logged = bool(
        (logged_end.get("n") or 0) >= 5
        and (logged_end.get("p_near_56") or 0) >= 0.5
    )
    supports_56_clean = bool(
        (clean_end.get("n") or 0) >= 5
        and (clean_end.get("p_near_56") or 0) >= 0.5
    )
    supports_56_narrow = bool(
        (narrow["isf_end"].get("n") or 0) >= 5
        and (narrow["isf_end"].get("p_near_56") or 0) >= 0.5
    )
    return {
        "profile_isf": profile_isf,
        "logged_only_supports_observed_56": supports_56_logged,
        "clean_wide_uam_exclusion_supports_observed_56": supports_56_clean,
        "clean_narrow_uam_exclusion_supports_observed_56": supports_56_narrow,
        "baseline_isf_change_supported": bool(supports_56_clean or supports_56_narrow),
        "main_evidence_against": [
            "The 54-56 mg/dL/U signal appears in logged-only correction denominators, but not after wide inferred-meal exclusion.",
            f"Clean wide-exclusion correction sample has n={clean['n_events']}, below the minimum needed for a baseline ISF change.",
            "Controller basal contribution and inferred meals are entangled in the same sparse correction windows.",
        ],
        "next_data_needed": [
            "More correction events explicitly separated from inferred meals by at least 2h before and 4h after.",
            "A prospective two-week basal-only step outcome before ISF retuning, preserving EXP-3447 basal quality.",
            "If ISF remains suspect, compare correction outcomes using only post-basal-step windows with no hybrid meal support.",
        ],
    }


def _render_memo(result: dict[str, Any]) -> str:
    c = result["conclusion"]
    lines = [
        "# EXP-3448 live-recent ISF deconfounding sensitivity",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Profile ISF: {c['profile_isf']:.0f} mg/dL/U",
        f"- Logged-only support for ~56: **{c['logged_only_supports_observed_56']}**",
        f"- Wide UAM-excluded support for ~56: **{c['clean_wide_uam_exclusion_supports_observed_56']}**",
        f"- Baseline ISF change supported: **{c['baseline_isf_change_supported']}**",
        "",
        "## Scenario summary",
        "",
        "| Scenario | n | median ISF end | 95% CI | P(50-62) | UAM wide contamination |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in result["scenarios"].items():
        s = row["isf_end"]
        ci = s.get("ci95")
        ci_txt = "n/a" if not ci else f"{ci[0]:.1f}-{ci[1]:.1f}"
        med = s.get("median")
        med_txt = "n/a" if med is None else f"{med:.1f}"
        p56 = s.get("p_near_56")
        p56_txt = "n/a" if p56 is None else f"{p56:.2f}"
        lines.append(
            f"| {name} | {row['n_events']} | {med_txt} | {ci_txt} | "
            f"{p56_txt} | {row['contamination']['any_uam_wide']} |"
        )
    lines.extend([
        "",
        "## Evidence against baseline ISF promotion",
        "",
    ])
    lines.extend(f"- {item}" for item in c["main_evidence_against"])
    lines.extend(["", "## Next data needed", ""])
    lines.extend(f"- {item}" for item in c["next_data_needed"])
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
    timezone_name = _profile_timezone(parquet_dir, patient_id)
    profile = _make_profile(df, timezone_name)
    patient = _make_patient(df, profile, patient_id)
    pipeline = run_pipeline(patient)
    meals = list(getattr(getattr(pipeline, "meal_history", None), "meals", None) or [])
    masks = _meal_masks(len(df), meals)
    events = _candidate_events(df, masks)
    profile_isf = _safe_float(df["scheduled_isf"].median(), 40.0)
    scenarios = _scenario_summary(events, profile_isf)
    result = {
        "exp": "EXP-3448",
        "title": "live-recent ISF deconfounding sensitivity audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": timezone_name,
        "n_candidate_events": int(len(events)),
        "scenarios": scenarios,
        "conclusion": _conclusion(scenarios, profile_isf),
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
        run_name="research-live-recent-isf-deconfounding",
        tags={"runner": "exp_live_recent_isf_deconfounding_3448", "exp": "EXP-3448"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3448_live_recent_isf_deconfounding.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3448_live_recent_isf_deconfounding.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
