#!/usr/bin/env python3
"""EXP-3452: live-recent ISF horizon decision-robustness audit.

Question: would the default "hold ISF" decision change if we used a longer
timeline than the 0-2h demand phase?

This sweeps exact-time and nadir ISF estimates from 1h through 6h, compares
logged-only versus UAM-excluded correction windows, and applies explicit
promotion gates:

1. at least 5 qualifying correction events,
2. clean UAM exclusion,
3. median differs from profile by >=20%,
4. bootstrap probability in the same direction >=80%,
5. bootstrap CI width <=40 mg/dL/U.
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
OUT_JSON = RESULTS_DIR / "exp3452_live_recent_isf_decision_robustness.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3452_live_recent_isf_decision_robustness.md"

HORIZONS_H = (1, 2, 3, 4, 5, 6)
MIN_EVENTS = 5
MIN_GAP_PCT = 20.0
MIN_DIRECTION_PROB = 0.80
MAX_CI_WIDTH = 40.0


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


def _event_rows(df: pd.DataFrame, masks: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    glucose = df["glucose"].to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    if "bolus_smb" in df:
        bolus = bolus + df["bolus_smb"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float) if "cob" in df else np.zeros(len(df))
    rows = []
    for i in range(72, len(df) - max(HORIZONS_H) * 12 - 1):
        dose = float(bolus[i])
        if dose < 0.5 or not np.isfinite(glucose[i]) or glucose[i] < 120.0:
            continue
        if float(np.nansum(bolus[max(0, i - 72):i])) > 0.3:
            continue
        if float(np.nansum(carbs[max(0, i - 12):min(len(df), i + 13)])) > 2.0:
            continue
        if float(cob[i]) > 5.0:
            continue
        row: dict[str, Any] = {
            "index": int(i),
            "time": str(df["time"].iloc[i]),
            "dose": dose,
            "start_bg": float(glucose[i]),
            "uam_any_wide": _mask_any(masks["any"], i, 24, 48),
            "uam_strong_wide": _mask_any(masks["strong"], i, 24, 48),
            "uam_any_narrow": _mask_any(masks["any"], i, 12, 24),
        }
        for h in HORIZONS_H:
            end = i + h * 12
            if end < len(glucose) and np.isfinite(glucose[end]):
                row[f"exact_{h}h"] = (float(glucose[i]) - float(glucose[end])) / dose
            win = glucose[i + 12:min(len(glucose), end + 1)]
            if np.isfinite(win).sum() >= 6:
                row[f"nadir_{h}h"] = (float(glucose[i]) - float(np.nanmin(win))) / dose
        rows.append(row)
    return rows


def _bootstrap(values: list[float], profile_isf: float) -> dict[str, Any]:
    vals = np.array([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    # Retain negative values for robustness diagnostics, but decision rules
    # only consider finite medians and bootstrap direction probability.
    if len(vals) == 0:
        return {
            "n": 0,
            "median": None,
            "iqr": None,
            "ci95": None,
            "ci_width": None,
            "p_gt_profile_20pct": None,
            "p_lt_profile_20pct": None,
        }
    rng = np.random.default_rng(3452)
    boot = np.array([
        np.median(vals[rng.integers(0, len(vals), size=len(vals))])
        for _ in range(1000)
    ])
    ci = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
    return {
        "n": int(len(vals)),
        "median": float(np.median(vals)),
        "iqr": float(np.percentile(vals, 75) - np.percentile(vals, 25)),
        "ci95": ci,
        "ci_width": float(ci[1] - ci[0]),
        "p_gt_profile_20pct": float(np.mean(boot > profile_isf * 1.20)),
        "p_lt_profile_20pct": float(np.mean(boot < profile_isf * 0.80)),
    }


def _would_change(summary: dict[str, Any], profile_isf: float, *, clean_required: bool) -> dict[str, Any]:
    n = int(summary.get("n") or 0)
    med = summary.get("median")
    ci_width = summary.get("ci_width")
    if med is None:
        return {"would_change": False, "reason": "no_estimate"}
    gap_pct = abs(float(med) - profile_isf) / profile_isf * 100.0
    if n < MIN_EVENTS:
        return {"would_change": False, "reason": f"n {n} below {MIN_EVENTS}"}
    if clean_required and not summary.get("_is_clean", False):
        return {"would_change": False, "reason": "not UAM-clean"}
    if gap_pct < MIN_GAP_PCT:
        return {"would_change": False, "reason": f"gap {gap_pct:.1f}% below {MIN_GAP_PCT:.0f}%"}
    if ci_width is None or ci_width > MAX_CI_WIDTH:
        return {"would_change": False, "reason": f"CI width {ci_width} above {MAX_CI_WIDTH:.0f}"}
    p_dir = (
        summary.get("p_gt_profile_20pct")
        if med > profile_isf
        else summary.get("p_lt_profile_20pct")
    )
    if p_dir is None or p_dir < MIN_DIRECTION_PROB:
        return {"would_change": False, "reason": f"direction probability {p_dir} below {MIN_DIRECTION_PROB}"}
    return {
        "would_change": True,
        "direction": "increase" if med > profile_isf else "decrease",
        "reason": "passes robustness gates",
        "target": float(med),
    }


def _summaries(events: list[dict[str, Any]], profile_isf: float) -> dict[str, Any]:
    scenarios = {
        "logged_only": (events, False),
        "exclude_any_uam_wide": ([e for e in events if not e["uam_any_wide"]], True),
        "exclude_strong_uam_wide": ([e for e in events if not e["uam_strong_wide"]], True),
        "exclude_any_uam_narrow": ([e for e in events if not e["uam_any_narrow"]], True),
    }
    out = {}
    for scenario, (rows, clean) in scenarios.items():
        grid = {}
        for endpoint in ("exact", "nadir"):
            for h in HORIZONS_H:
                key = f"{endpoint}_{h}h"
                s = _bootstrap([r.get(key) for r in rows], profile_isf)
                s["_is_clean"] = clean
                s["decision"] = _would_change(s, profile_isf, clean_required=True)
                grid[key] = s
        out[scenario] = {
            "n_events": int(len(rows)),
            "n_uam_any_wide": int(sum(r["uam_any_wide"] for r in rows)),
            "horizons": grid,
        }
    return out


def _conclusion(summaries: dict[str, Any]) -> dict[str, Any]:
    all_decisions = []
    clean_decisions = []
    logged_flip_candidates = []
    for scenario, block in summaries.items():
        for key, row in block["horizons"].items():
            decision = row["decision"]
            if decision["would_change"]:
                all_decisions.append((scenario, key, decision, row))
                if scenario.startswith("exclude_"):
                    clean_decisions.append((scenario, key, decision, row))
            elif scenario == "logged_only" and row.get("n", 0) >= MIN_EVENTS:
                med = row.get("median")
                if med is not None and abs(float(med) - 40.0) / 40.0 >= 0.20:
                    logged_flip_candidates.append((key, row, decision["reason"]))
    best_logged = None
    if logged_flip_candidates:
        key, row, reason = min(
            logged_flip_candidates,
            key=lambda item: item[1].get("ci_width") if item[1].get("ci_width") is not None else 1e9,
        )
        best_logged = {
            "horizon": key,
            "median": row.get("median"),
            "ci95": row.get("ci95"),
            "ci_width": row.get("ci_width"),
            "reason_not_promoted": reason,
        }
    return {
        "default_hold_changes": bool(clean_decisions),
        "clean_gate_passers": [
            {"scenario": s, "horizon": h, "decision": d, "summary": r}
            for s, h, d, r in clean_decisions
        ],
        "best_logged_only_flip_candidate": best_logged,
        "interpretation": (
            "No UAM-clean horizon passes robustness gates, so the default hold decision does not change."
            if not clean_decisions else
            "At least one UAM-clean horizon passes robustness gates; ISF decision should be revisited."
        ),
    }


def _render_memo(result: dict[str, Any]) -> str:
    c = result["conclusion"]
    lines = [
        "# EXP-3452 live-recent ISF decision robustness",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Default hold changes: **{c['default_hold_changes']}**",
        f"- Interpretation: {c['interpretation']}",
        "",
    ]
    best = c.get("best_logged_only_flip_candidate")
    if best:
        lines.extend([
            "## Best logged-only flip candidate",
            "",
            f"- Horizon: {best['horizon']}",
            f"- Median: {best['median']:.1f}",
            f"- CI: {best['ci95'][0]:.1f}-{best['ci95'][1]:.1f}",
            f"- Reason not promoted: {best['reason_not_promoted']}",
            "",
        ])
    lines.extend([
        "## Horizon grid",
        "",
        "| Scenario | Endpoint | n | Median | CI width | Decision |",
        "|---|---|---:|---:|---:|---|",
    ])
    for scenario, block in result["summaries"].items():
        for key, row in block["horizons"].items():
            if not key.startswith("exact_"):
                continue
            med = row.get("median")
            med_txt = "n/a" if med is None else f"{med:.1f}"
            ciw = row.get("ci_width")
            ciw_txt = "n/a" if ciw is None else f"{ciw:.1f}"
            lines.append(
                f"| {scenario} | {key} | {row.get('n', 0)} | {med_txt} | "
                f"{ciw_txt} | {row['decision']['reason']} |"
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
    events = _event_rows(df, masks)
    profile_isf = _profile_isf(profile)
    summaries = _summaries(events, profile_isf)
    result = {
        "exp": "EXP-3452",
        "title": "live-recent ISF horizon decision robustness",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": tz,
        "profile_isf": profile_isf,
        "n_candidate_events": int(len(events)),
        "promotion_gates": {
            "min_events": MIN_EVENTS,
            "min_gap_pct": MIN_GAP_PCT,
            "min_direction_probability": MIN_DIRECTION_PROB,
            "max_ci_width": MAX_CI_WIDTH,
            "uam_clean_required": True,
        },
        "summaries": summaries,
        "conclusion": _conclusion(summaries),
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
        run_name="research-live-recent-isf-decision-robustness",
        tags={"runner": "exp_live_recent_isf_decision_robustness_3452", "exp": "EXP-3452"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3452_live_recent_isf_decision_robustness.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3452_live_recent_isf_decision_robustness.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
