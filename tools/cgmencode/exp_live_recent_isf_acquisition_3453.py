#!/usr/bin/env python3
"""EXP-3453: live-recent clean ISF evidence acquisition audit.

After EXP-3452, no UAM-clean horizon could flip the ISF hold. This experiment
answers the follow-up operational question: what evidence is missing, why are
current correction events rejected, and what passive future evidence would be
enough to revisit the decision?
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
OUT_JSON = RESULTS_DIR / "exp3453_live_recent_isf_acquisition.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3453_live_recent_isf_acquisition.md"

STRICT_PRE_STEPS = 24   # 2h
STRICT_POST_STEPS = 48  # 4h
PRIOR_BOLUS_STEPS = 72  # 6h
MIN_DOSE_U = 0.5
MIN_BG = 180.0
MIN_EVENTS_TO_REOPEN = 10
TARGET_CI_WIDTH = 40.0


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


def _mask_any(mask: np.ndarray, index: int, before: int, after: int) -> bool:
    lo = max(0, index - before)
    hi = min(len(mask), index + after + 1)
    return bool(mask[lo:hi].any())


def _episode_count(indices: np.ndarray, gap_steps: int = 12) -> int:
    if len(indices) == 0:
        return 0
    count = 1
    last = int(indices[0])
    for idx in indices[1:]:
        idx = int(idx)
        if idx - last > gap_steps:
            count += 1
        last = idx
    return count


def _correction_candidates(df: pd.DataFrame, masks: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    glucose = df["glucose"].to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    if "bolus_smb" in df:
        bolus = bolus + df["bolus_smb"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float) if "cob" in df else np.zeros(len(df))
    rows = []
    for i in range(0, len(df) - 73):
        if bolus[i] < 0.05:
            continue
        row = {
            "index": int(i),
            "time": str(df["time"].iloc[i]),
            "dose": float(bolus[i]),
            "bg": float(glucose[i]) if np.isfinite(glucose[i]) else None,
            "full_6h": bool(i + 72 < len(df) and np.isfinite(glucose[i + 72])),
            "dose_ok": bool(bolus[i] >= MIN_DOSE_U),
            "bg_ok": bool(np.isfinite(glucose[i]) and glucose[i] >= MIN_BG),
            "prior_bolus_clean": bool(np.nansum(bolus[max(0, i - PRIOR_BOLUS_STEPS):i]) <= 0.3),
            "carb_clean": bool(
                np.nansum(carbs[max(0, i - 12):min(len(df), i + 13)]) <= 2.0
                and cob[i] <= 5.0
            ),
            "uam_clean": bool(not _mask_any(masks["any"], i, STRICT_PRE_STEPS, STRICT_POST_STEPS)),
        }
        row["strict_clean"] = all(
            row[k] for k in ("full_6h", "dose_ok", "bg_ok", "prior_bolus_clean", "carb_clean", "uam_clean")
        )
        if row["full_6h"] and row["dose_ok"] and row["bg_ok"]:
            drop_4h = float(glucose[i] - glucose[i + 48]) if np.isfinite(glucose[i + 48]) else np.nan
            row["isf_4h_exact"] = drop_4h / max(float(bolus[i]), 1e-6)
        rows.append(row)
    return rows


def _rejection_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    seq = rows
    steps = []
    for key, label in (
        ("full_6h", "full 6h glucose window"),
        ("dose_ok", "dose >= 0.5U"),
        ("bg_ok", "BG >= 180"),
        ("prior_bolus_clean", "no prior bolus within 6h"),
        ("carb_clean", "logged carb/COB clean"),
        ("uam_clean", "strict inferred-meal clean (-2h,+4h)"),
    ):
        before = len(seq)
        seq = [r for r in seq if r[key]]
        steps.append({
            "gate": label,
            "before": before,
            "after": len(seq),
            "rejected": before - len(seq),
        })
    independent = {
        "total_bolus_events": total,
        "strict_clean_events": int(sum(r["strict_clean"] for r in rows)),
        "failed_full_6h": int(sum(not r["full_6h"] for r in rows)),
        "failed_dose": int(sum(not r["dose_ok"] for r in rows)),
        "failed_bg": int(sum(not r["bg_ok"] for r in rows)),
        "failed_prior_bolus": int(sum(not r["prior_bolus_clean"] for r in rows)),
        "failed_carb": int(sum(not r["carb_clean"] for r in rows)),
        "failed_uam": int(sum(not r["uam_clean"] for r in rows)),
    }
    return {"sequential": steps, "independent": independent}


def _clean_high_bg_opportunities(df: pd.DataFrame, masks: dict[str, np.ndarray]) -> dict[str, Any]:
    glucose = df["glucose"].to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float) if "cob" in df else np.zeros(len(df))
    clean = np.zeros(len(df), dtype=bool)
    for i in range(0, len(df) - 73):
        if not (np.isfinite(glucose[i]) and glucose[i] >= MIN_BG):
            continue
        if np.nansum(bolus[max(0, i - PRIOR_BOLUS_STEPS):i]) > 0.3:
            continue
        if np.nansum(carbs[max(0, i - 12):min(len(df), i + 13)]) > 2.0 or cob[i] > 5.0:
            continue
        if _mask_any(masks["any"], i, STRICT_PRE_STEPS, STRICT_POST_STEPS):
            continue
        clean[i] = True
    idx = np.where(clean)[0]
    return {
        "clean_high_bg_rows": int(len(idx)),
        "clean_high_bg_hours": float(len(idx) * 5.0 / 60.0),
        "clean_high_bg_episodes": _episode_count(idx, gap_steps=12),
        "median_bg": float(np.nanmedian(glucose[idx])) if len(idx) else None,
    }


def _sample_size(rows: list[dict[str, Any]]) -> dict[str, Any]:
    vals = np.array([
        r.get("isf_4h_exact")
        for r in rows
        if r.get("isf_4h_exact") is not None and np.isfinite(r.get("isf_4h_exact"))
    ], dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) < 2:
        return {
            "basis": "insufficient observed events; use minimum-event rule",
            "recommended_min_events": MIN_EVENTS_TO_REOPEN,
        }
    robust_sd = float(np.subtract(*np.percentile(vals, [75, 25])) / 1.349)
    sd = float(np.std(vals, ddof=1))
    effective_sd = max(robust_sd, min(sd, 80.0))
    # Approximate 95% CI width of mean/median scale: 2*1.96*sd/sqrt(n).
    n_for_width = int(np.ceil((2.0 * 1.96 * effective_sd / TARGET_CI_WIDTH) ** 2))
    return {
        "basis": "logged-only 4h exact variability, capped for robustness",
        "observed_n": int(len(vals)),
        "observed_median_4h": float(np.median(vals)),
        "observed_iqr_4h": float(np.subtract(*np.percentile(vals, [75, 25]))),
        "observed_sd_4h": sd,
        "effective_sd_for_planning": effective_sd,
        "n_for_ci_width_40": n_for_width,
        "recommended_min_events": int(max(MIN_EVENTS_TO_REOPEN, n_for_width)),
    }


def _conclusion(rejection: dict[str, Any], opportunities: dict[str, Any], sample_size: dict[str, Any]) -> dict[str, Any]:
    strict_clean = rejection["independent"]["strict_clean_events"]
    promotion_events = sample_size["recommended_min_events"]
    return {
        "current_clean_isf_events": strict_clean,
        "future_clean_events_to_reopen_review": MIN_EVENTS_TO_REOPEN,
        "future_clean_events_for_precision_promotion": promotion_events,
        "clean_high_bg_episodes_without_clean_correction": opportunities["clean_high_bg_episodes"],
        "decision": (
            "Keep ISF on hold. Reopen analysis after a small passive strict-UAM-clean correction set, but do not promote baseline ISF until the estimate is precise or enough events accumulate."
        ),
        "future_evidence_contract": [
            "Correction bolus >=0.5U at BG >=180.",
            "No prior bolus in 6h.",
            "Logged carbs/COB clean around the correction.",
            "No inferred meal from 2h before through 4h after the correction.",
            "Compute paired 2h demand and 4h exact outcomes on the same events.",
            f"Reopen analysis at {MIN_EVENTS_TO_REOPEN} clean events; require about {promotion_events} events or tighter CI evidence before promoting baseline ISF.",
        ],
    }


def _render_memo(result: dict[str, Any]) -> str:
    c = result["conclusion"]
    lines = [
        "# EXP-3453 live-recent clean ISF evidence acquisition",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Current strict clean ISF events: {c['current_clean_isf_events']}",
        f"- Future clean events to reopen review: {c['future_clean_events_to_reopen_review']}",
        f"- Future clean events for precision promotion: {c['future_clean_events_for_precision_promotion']}",
        f"- Clean high-BG episodes without clean correction: {c['clean_high_bg_episodes_without_clean_correction']}",
        "",
        c["decision"],
        "",
        "## Sequential rejection funnel",
        "",
        "| Gate | Before | After | Rejected |",
        "|---|---:|---:|---:|",
    ]
    for row in result["rejection_summary"]["sequential"]:
        lines.append(f"| {row['gate']} | {row['before']} | {row['after']} | {row['rejected']} |")
    lines.extend(["", "## Future evidence contract", ""])
    lines.extend(f"- {item}" for item in c["future_evidence_contract"])
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
    rows = _correction_candidates(df, masks)
    rejection = _rejection_summary(rows)
    opportunities = _clean_high_bg_opportunities(df, masks)
    sample_size = _sample_size(rows)
    result = {
        "exp": "EXP-3453",
        "title": "live-recent clean ISF evidence acquisition audit",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": tz,
        "strict_rule": {
            "pre_uam_exclusion_hours": 2,
            "post_uam_exclusion_hours": 4,
            "prior_bolus_isolation_hours": 6,
            "min_dose_u": MIN_DOSE_U,
            "min_bg": MIN_BG,
        },
        "rejection_summary": rejection,
        "clean_high_bg_opportunities": opportunities,
        "sample_size": sample_size,
        "conclusion": _conclusion(rejection, opportunities, sample_size),
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
        run_name="research-live-recent-isf-acquisition",
        tags={"runner": "exp_live_recent_isf_acquisition_3453", "exp": "EXP-3453"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3453_live_recent_isf_acquisition.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3453_live_recent_isf_acquisition.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
