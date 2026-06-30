#!/usr/bin/env python3
"""EXP-3451: live-recent ISF decomposition ladder.

The live-recent report can show several ISF-like numbers at once:
scheduled/profile ISF, response-curve apparent ISF, demand-phase ISF,
correction-denominator ISF, dose-shaping ISF, and UAM-filtered correction
estimates. This experiment makes the ladder explicit so reviewers can see
which values are explanatory, which are actionable, and which are too
confounded for baseline settings.
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
from cgmencode.mlflow_utils import log_dict, log_text, start_run
from cgmencode.production.clinical_rules import (
    compute_demand_isf,
    compute_response_curve_isf,
)
from cgmencode.production.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3451_live_recent_isf_ladder.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3451_live_recent_isf_ladder.md"


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


def _safe_load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _profile_isf(profile) -> float:
    vals = [e.get("value", e.get("sensitivity", 40.0)) for e in profile.isf_mgdl()]
    return float(np.median([float(v) for v in vals])) if vals else 40.0


def _entry(
    *,
    name: str,
    value: float | None,
    method: str,
    role: str,
    usable_as_baseline: bool,
    confidence: str,
    n: int | None,
    confounds: list[str],
    interpretation: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "value_mgdl_per_u": value,
        "method": method,
        "role": role,
        "usable_as_baseline_target": usable_as_baseline,
        "confidence": confidence,
        "n": n,
        "confounds": confounds,
        "interpretation": interpretation,
    }


def _build_ladder(df: pd.DataFrame, patient_id: str, timezone_name: str) -> dict[str, Any]:
    profile = _make_profile(df, timezone_name)
    patient = _make_patient(df, profile, patient_id)
    result = run_pipeline(patient)
    profile_val = _profile_isf(profile)
    dual = compute_demand_isf(
        patient.glucose,
        patient.bolus,
        profile,
        carbs=patient.carbs,
    )
    rc = compute_response_curve_isf(
        patient.glucose,
        patient.bolus,
        basal_rate=patient.basal_rate,
        profile=profile,
        inferred_meal_indices=np.array([
            int(m.index)
            for m in (getattr(getattr(result, "meal_history", None), "meals", None) or [])
        ], dtype=int),
    )

    facts = _safe_load_json(RESULTS_DIR / "exp3448_live_recent_isf_deconfounding.json")
    current_facts = _safe_load_json(ROOT / "reports" / "live-recent-analysis" / "facts.json")
    controller = (current_facts.get("facts_loaders") or {}).get("controller_dynamics_EXP_2753") or {}
    logged_only = ((facts.get("scenarios") or {}).get("logged_only_bg180_bolus05") or {}).get("isf_end") or {}
    clean_wide = ((facts.get("scenarios") or {}).get("exclude_any_uam_wide") or {}).get("isf_end") or {}
    controller_sub = ((facts.get("scenarios") or {}).get("logged_only_bg180_bolus05") or {}).get("isf_controller_subtracted") or {}
    dose_shaping = None
    for rec in getattr(result, "settings_recs", None) or []:
        text = f"{getattr(rec, 'evidence', '')} {getattr(rec, 'rationale', '')}"
        if "EXP-2511" in text or "non-linearity" in text:
            dose_shaping = rec
            break

    ladder = [
        _entry(
            name="scheduled_profile",
            value=profile_val,
            method="Nightscout/Loop profile scheduled ISF",
            role="current controller operating setting",
            usable_as_baseline=True,
            confidence="configured",
            n=None,
            confounds=[],
            interpretation="The current programmed correction factor: expected mg/dL drop per 1U in the controller model.",
        ),
        _entry(
            name="response_curve_apparent",
            value=round(float(rc["isf"]), 1) if rc and "isf" in rc else getattr(getattr(result, "clinical_report", None), "effective_isf", None),
            method="response-curve fit to post-bolus glucose",
            role="AID-inflated apparent effect",
            usable_as_baseline=False,
            confidence="low" if not rc else "apparent",
            n=int(rc.get("n_corrections", 0)) if rc else None,
            confounds=["AID basal compensation", "EGP suppression", "meal/UAM contamination risk"],
            interpretation="A curve-fit apparent ISF. Useful for showing total system effect, not a baseline schedule target.",
        ),
        _entry(
            name="demand_phase",
            value=dual.demand_isf if dual else None,
            method="0-2h post-correction drop divided by dose",
            role="candidate physiological/demand-phase target",
            usable_as_baseline=bool(dual and dual.confidence in {"medium", "high"}),
            confidence=dual.confidence if dual else "missing",
            n=dual.n_corrections if dual else 0,
            confounds=["small correction sample", "prior-bolus isolation fallback", "residual UAM risk"],
            interpretation=(
                "Closest current estimate to early insulin demand, but live-recent confidence is low, so it should be held rather than implemented."
                if dual else "Insufficient correction events for demand-phase ISF."
            ),
        ),
        _entry(
            name="demand_apparent_nadir",
            value=dual.apparent_isf if dual else None,
            method="nadir/full-drop ISF on the same demand-phase events",
            role="late/full effect within selected correction events",
            usable_as_baseline=False,
            confidence=dual.confidence if dual else "missing",
            n=dual.n_corrections if dual else 0,
            confounds=["AID compensation", "EGP suppression", "late rebound/nadir timing"],
            interpretation="This is the apparent inflated number in the report. It is deliberately labeled not-target.",
        ),
        _entry(
            name="correction_denominator",
            value=controller.get("isf_corr_denom_median"),
            method="EXP-2753 correction-denominator median",
            role="controller-aware explanatory operating signal",
            usable_as_baseline=False,
            confidence="very_low_live_recent" if controller.get("n_events", 0) < 10 else "cohort_supported",
            n=controller.get("n_events"),
            confounds=["only correction denominator", "controller basal contribution", "UAM not fully excluded"],
            interpretation="This is the ~53.7 value. It is plausible and clinically interesting, but live-recent has too few clean events to promote it.",
        ),
        _entry(
            name="logged_only_correction_denominator",
            value=logged_only.get("median"),
            method="EXP-3448 logged-only correction denominator",
            role="sensitivity check for the ~53.7 signal",
            usable_as_baseline=False,
            confidence="low",
            n=logged_only.get("n"),
            confounds=["all qualifying windows overlap inferred/hybrid meal windows"],
            interpretation="Replicates the ~52-56 signal, but all events fail UAM exclusion.",
        ),
        _entry(
            name="uam_excluded_correction_denominator",
            value=clean_wide.get("median"),
            method="EXP-3448 correction denominator after wide inferred-meal exclusion",
            role="clean-event baseline-ISF evidence",
            usable_as_baseline=False,
            confidence="none",
            n=clean_wide.get("n"),
            confounds=["no clean events"],
            interpretation="The decisive missing piece: after UAM exclusion, live-recent has zero clean correction events.",
        ),
        _entry(
            name="controller_subtracted",
            value=controller_sub.get("median"),
            method="EXP-3448 subtract Loop basal contribution using profile ISF",
            role="attribution stress test",
            usable_as_baseline=False,
            confidence="unstable",
            n=controller_sub.get("n"),
            confounds=["single event", "model-dependent controller subtraction"],
            interpretation="Shows attribution is unstable: subtracting controller basal can swing the estimate below profile.",
        ),
    ]
    if dose_shaping is not None:
        ladder.append(_entry(
            name="dose_shaping_typical_large_correction",
            value=float(dose_shaping.suggested_value),
            method="EXP-2511 dose non-linearity at typical large correction dose",
            role="split-dose / dose-shaping guidance",
            usable_as_baseline=False,
            confidence="advisory",
            n=None,
            confounds=["dose-conditional", "not a basal schedule target"],
            interpretation="Explains why large corrections underperform. It should guide split dosing or patience, not baseline ISF.",
        ))

    return {
        "dual_phase": {
            "demand_isf": dual.demand_isf if dual else None,
            "apparent_isf": dual.apparent_isf if dual else None,
            "inflation_ratio": dual.inflation_ratio if dual else None,
            "n_corrections": dual.n_corrections if dual else 0,
            "confidence": dual.confidence if dual else None,
            "ci": [dual.demand_ci_low, dual.demand_ci_high] if dual else None,
            "isolation_h": dual.isolation_h if dual else None,
        },
        "controller_dynamics": controller,
        "ladder": ladder,
        "conclusion": {
            "why_numbers_differ": [
                "40 is the programmed controller setting.",
                "88 is a late/full apparent effect on selected events and includes AID compensation/EGP suppression.",
                "30 is early 0-2h demand-phase effect, but live-recent confidence is low.",
                "53.7 is correction-denominator evidence from sparse correction windows, and it fails clean UAM exclusion in EXP-3448.",
            ],
            "best_current_action": "Do not change baseline ISF yet. Continue basal-first monitored titration and collect post-step clean correction windows.",
            "next_disambiguation": [
                "After the basal step, require correction events with no inferred meal from -2h to +4h.",
                "Track 0-2h demand drop and 1-5h apparent/nadir drop on the same events.",
                "Separate controller-replacement basal from additive insulin in the correction window.",
                "Promote ISF only if demand-phase and UAM-clean correction-denominator estimates converge with enough events and TBR guardrails pass.",
            ],
        },
    }


def _render_memo(result: dict[str, Any]) -> str:
    lines = [
        "# EXP-3451 live-recent ISF decomposition ladder",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Ladder",
        "",
        "| Name | Value | Role | Baseline target? | Confidence | n |",
        "|---|---:|---|---|---|---:|",
    ]
    for row in result["ladder"]:
        val = row["value_mgdl_per_u"]
        val_txt = "n/a" if val is None else f"{float(val):.1f}"
        n = row["n"]
        n_txt = "" if n is None else str(n)
        lines.append(
            f"| {row['name']} | {val_txt} | {row['role']} | "
            f"{row['usable_as_baseline_target']} | {row['confidence']} | {n_txt} |"
        )
    lines.extend(["", "## Why they differ", ""])
    lines.extend(f"- {item}" for item in result["conclusion"]["why_numbers_differ"])
    lines.extend(["", "## Current decision", "", result["conclusion"]["best_current_action"], ""])
    lines.extend(["## Next disambiguation", ""])
    lines.extend(f"- {item}" for item in result["conclusion"]["next_disambiguation"])
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
    ladder = _build_ladder(df, patient_id, timezone_name)
    result = {
        "exp": "EXP-3451",
        "title": "live-recent ISF decomposition ladder",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": timezone_name,
        **ladder,
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
        run_name="research-live-recent-isf-ladder",
        tags={"runner": "exp_live_recent_isf_ladder_3451", "exp": "EXP-3451"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3451_live_recent_isf_ladder.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3451_live_recent_isf_ladder.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
