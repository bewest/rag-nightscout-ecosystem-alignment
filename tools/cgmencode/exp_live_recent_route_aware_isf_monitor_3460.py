#!/usr/bin/env python3
"""EXP-3460: live-recent route-aware ISF evidence monitor.

This turns the one-off ISF audits into a recurring evidence monitor. Loop can
express correction intent through either discrete boluses or excess temp basal,
so the monitor tracks both routes across 2h/4h/6h horizons while keeping the
routes separate:

* bolus corrections remain the closest evidence for baseline ISF promotion,
* basal-route episodes are abundant but controller-modulated, so they are used
  as acquisition and directionality context rather than bolus-equivalent ISF.

The monitor is designed to be rerun after prospective basal-first titration
windows (7/14/21 days) and across larger windows (30/60/90/full history).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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
OUT_JSON = RESULTS_DIR / "exp3460_live_recent_route_aware_isf_monitor.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3460_live_recent_route_aware_isf_monitor.md"

WINDOWS_DAYS = (30, 60, 90)
HORIZONS = {"2h": 24, "4h": 48, "6h": 72}
MIN_BG = 180.0
MIN_BOLUS_U = 0.5
MIN_EXCESS_RATE_U_H = 0.3
PRIOR_BOLUS_STEPS = 72
STRICT_PRE_STEPS = 24
STRICT_POST_STEPS = 72
MIN_CLEAN_EVENTS_TO_REOPEN = 10
TARGET_CI_WIDTH = 40.0
BASELINE_PROMOTION_MIN_EVENTS = 57
PROFILE_GAP_PCT = 20.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
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


def _episodes(indices: Iterable[int], gap_steps: int = 12) -> list[int]:
    starts: list[int] = []
    last = -10_000
    for idx in sorted(int(i) for i in indices):
        if idx - last > gap_steps:
            starts.append(idx)
        last = idx
    return starts


def _summary(values: Iterable[float], profile_isf: float, seed: int) -> dict[str, Any]:
    vals = np.array([v for v in values if v is not None and np.isfinite(v)], dtype=float)
    if len(vals) == 0:
        return {
            "n": 0,
            "median": None,
            "iqr": None,
            "ci95": None,
            "ci_width": None,
            "p_gt_profile_20pct": None,
            "p_lt_profile_20pct": None,
            "p_near_53_56": None,
        }
    rng = np.random.default_rng(seed)
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
        "p_near_53_56": float(np.mean((boot >= 53.0) & (boot <= 56.0))),
    }


def _bolus_events(df: pd.DataFrame, masks: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    glucose = df["glucose"].to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    if "bolus_smb" in df:
        bolus = bolus + df["bolus_smb"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float) if "cob" in df else np.zeros(len(df))

    rows: list[dict[str, Any]] = []
    for i in range(PRIOR_BOLUS_STEPS, len(df) - max(HORIZONS.values()) - 1):
        dose = float(bolus[i])
        if dose < MIN_BOLUS_U or not np.isfinite(glucose[i]) or glucose[i] < MIN_BG:
            continue
        carb_clean = (
            float(np.nansum(carbs[max(0, i - 12):min(len(df), i + 13)])) <= 2.0
            and float(cob[i]) <= 5.0
        )
        prior_bolus_clean = float(np.nansum(bolus[max(0, i - PRIOR_BOLUS_STEPS):i])) <= 0.3
        strict_uam_clean = not _mask_any(masks["any"], i, STRICT_PRE_STEPS, STRICT_POST_STEPS)
        row: dict[str, Any] = {
            "index": int(i),
            "time": df["time"].iloc[i],
            "dose_u": dose,
            "start_bg": float(glucose[i]),
            "prior_bolus_clean": bool(prior_bolus_clean),
            "carb_clean": bool(carb_clean),
            "strict_uam_clean_6h": bool(strict_uam_clean),
            "strict_clean": bool(prior_bolus_clean and carb_clean and strict_uam_clean),
        }
        for label, steps in HORIZONS.items():
            units = dose
            end = i + steps
            drop = float(glucose[i] - glucose[end]) if np.isfinite(glucose[end]) else np.nan
            win = glucose[i:min(len(glucose), end + 1)]
            nadir = float(glucose[i] - np.nanmin(win)) if np.isfinite(win).sum() >= 6 else np.nan
            row[f"isf_exact_{label}"] = drop / units if units > 0 and np.isfinite(drop) else np.nan
            row[f"isf_nadir_{label}"] = nadir / units if units > 0 and np.isfinite(nadir) else np.nan
        rows.append(row)
    return rows


def _basal_route_events(
    df: pd.DataFrame,
    masks: dict[str, np.ndarray],
    metabolic,
) -> list[dict[str, Any]]:
    glucose = df["glucose"].to_numpy(dtype=float)
    scheduled = df["scheduled_basal_rate"].fillna(0.0).to_numpy(dtype=float)
    actual = df["actual_basal_rate"].fillna(0.0).to_numpy(dtype=float)
    excess = np.maximum(actual - scheduled, 0.0)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    if "bolus_smb" in df:
        bolus = bolus + df["bolus_smb"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float) if "cob" in df else np.zeros(len(df))
    net_flux = np.asarray(metabolic.net_flux, dtype=float)
    roc = df["glucose_roc"].fillna(np.nan).to_numpy(dtype=float)

    candidate_indices: list[int] = []
    row_flags: dict[int, dict[str, Any]] = {}
    for i in range(PRIOR_BOLUS_STEPS, len(df) - max(HORIZONS.values()) - 1):
        if not (
            np.isfinite(glucose[i])
            and glucose[i] >= MIN_BG
            and excess[i] > MIN_EXCESS_RATE_U_H
            and float(np.nansum(bolus[max(0, i - PRIOR_BOLUS_STEPS):i])) <= 0.3
            and float(np.nansum(carbs[max(0, i - 12):min(len(df), i + 13)])) <= 2.0
            and float(cob[i]) <= 1.0
        ):
            continue
        candidate_indices.append(i)
        row_flags[i] = {
            "strict_uam_clean_6h": not _mask_any(masks["any"], i, STRICT_PRE_STEPS, STRICT_POST_STEPS),
            "equilibrium_now": bool(abs(net_flux[i]) <= 1.0 and np.isfinite(roc[i]) and abs(roc[i]) <= 1.0),
            "equilibrium_context": bool(np.nanmean(np.abs(net_flux[max(0, i - 12):i + 1])) <= 1.5),
        }

    rows: list[dict[str, Any]] = []
    for i in _episodes(candidate_indices):
        flags = row_flags[i]
        row: dict[str, Any] = {
            "index": int(i),
            "time": df["time"].iloc[i],
            "start_bg": float(glucose[i]),
            "strict_clean": bool(flags["strict_uam_clean_6h"]),
            "equilibrium_now": bool(flags["equilibrium_now"]),
            "equilibrium_context": bool(flags["equilibrium_context"]),
        }
        for label, steps in HORIZONS.items():
            units = float(np.nansum(excess[i:i + steps]) / 12.0)
            end = i + steps
            drop = float(glucose[i] - glucose[end]) if np.isfinite(glucose[end]) else np.nan
            win = glucose[i:min(len(glucose), end + 1)]
            nadir = float(glucose[i] - np.nanmin(win)) if np.isfinite(win).sum() >= 6 else np.nan
            row[f"excess_units_{label}"] = units
            row[f"isf_exact_{label}"] = drop / units if units > 0 and np.isfinite(drop) else np.nan
            row[f"isf_nadir_{label}"] = nadir / units if units > 0 and np.isfinite(nadir) else np.nan
        rows.append(row)
    return rows


def _route_summary(rows: list[dict[str, Any]], profile_isf: float, seed: int) -> dict[str, Any]:
    out: dict[str, Any] = {"events": int(len(rows))}
    for endpoint in ("exact", "nadir"):
        for label in HORIZONS:
            key = f"isf_{endpoint}_{label}"
            out[key] = _summary([r.get(key) for r in rows], profile_isf, seed)
    if rows and "excess_units_6h" in rows[0]:
        out["median_excess_units_6h"] = float(np.median([r["excess_units_6h"] for r in rows]))
    return out


def _promotable_baseline_isf(summary: dict[str, Any], profile_isf: float) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for endpoint in ("exact", "nadir"):
        for label in ("4h", "6h"):
            row = summary.get(f"isf_{endpoint}_{label}", {})
            n = int(row.get("n") or 0)
            med = row.get("median")
            ci_width = row.get("ci_width")
            if med is None or ci_width is None:
                continue
            gap_pct = abs(float(med) - profile_isf) / profile_isf * 100.0
            p_dir = row.get("p_gt_profile_20pct") if med > profile_isf else row.get("p_lt_profile_20pct")
            candidate = {
                "endpoint": endpoint,
                "horizon": label,
                "n": n,
                "median": med,
                "ci_width": ci_width,
                "gap_pct": gap_pct,
                "direction_probability": p_dir,
            }
            if best is None or (n, -ci_width) > (best["n"], -best["ci_width"]):
                best = candidate
    if best is None:
        return {"promote": False, "reason": "no baseline bolus estimate"}
    if best["n"] < BASELINE_PROMOTION_MIN_EVENTS:
        return {"promote": False, "reason": f"n {best['n']} below {BASELINE_PROMOTION_MIN_EVENTS}", "best": best}
    if best["gap_pct"] < PROFILE_GAP_PCT:
        return {"promote": False, "reason": f"gap {best['gap_pct']:.1f}% below {PROFILE_GAP_PCT:.0f}%", "best": best}
    if best["ci_width"] > TARGET_CI_WIDTH:
        return {"promote": False, "reason": f"CI width {best['ci_width']:.1f} above {TARGET_CI_WIDTH:.0f}", "best": best}
    if best["direction_probability"] is None or best["direction_probability"] < 0.80:
        return {"promote": False, "reason": "direction probability below 0.80", "best": best}
    return {"promote": True, "reason": "passes baseline bolus gates", "best": best}


def _windowed_summary(
    bolus_rows: list[dict[str, Any]],
    basal_rows: list[dict[str, Any]],
    profile_isf: float,
    end_time: pd.Timestamp,
    days: int | None,
) -> dict[str, Any]:
    start_time = None if days is None else end_time - pd.Timedelta(days=days)

    def in_window(row: dict[str, Any]) -> bool:
        t = pd.Timestamp(row["time"])
        return start_time is None or t >= start_time

    bolus = [r for r in bolus_rows if in_window(r)]
    bolus_strict = [r for r in bolus if r["strict_clean"]]
    basal = [r for r in basal_rows if in_window(r)]
    basal_strict = [r for r in basal if r["strict_clean"]]
    basal_eq = [r for r in basal_strict if r["equilibrium_context"]]

    label = "full_history" if days is None else f"{days}d"
    bolus_summary = {
        "all_qualified": _route_summary(bolus, profile_isf, 3460),
        "strict_uam_clean": _route_summary(bolus_strict, profile_isf, 3461),
    }
    basal_summary = {
        "all_qualified": _route_summary(basal, profile_isf, 3462),
        "strict_uam_clean": _route_summary(basal_strict, profile_isf, 3463),
        "strict_clean_equilibrium_context": _route_summary(basal_eq, profile_isf, 3464),
    }
    promotion = _promotable_baseline_isf(bolus_summary["strict_uam_clean"], profile_isf)
    return {
        "label": label,
        "start_time": start_time,
        "end_time": end_time,
        "bolus_route": bolus_summary,
        "basal_route": basal_summary,
        "route_status": {
            "bolus_clean_events": bolus_summary["strict_uam_clean"]["events"],
            "bolus_reopen_ready": bolus_summary["strict_uam_clean"]["events"] >= MIN_CLEAN_EVENTS_TO_REOPEN,
            "bolus_baseline_promotion": promotion,
            "basal_clean_episodes": basal_summary["strict_uam_clean"]["events"],
            "basal_equilibrium_episodes": basal_summary["strict_clean_equilibrium_context"]["events"],
            "basal_route_context_ready": basal_summary["strict_uam_clean"]["events"] >= MIN_CLEAN_EVENTS_TO_REOPEN,
        },
    }


def _conclusion(window_summaries: list[dict[str, Any]], profile_isf: float) -> dict[str, Any]:
    full = window_summaries[-1]
    status = full["route_status"]
    bolus6 = full["bolus_route"]["strict_uam_clean"]["isf_exact_6h"].get("median")
    basal6 = full["basal_route"]["strict_clean_equilibrium_context"]["isf_exact_6h"].get("median")
    promotion = status["bolus_baseline_promotion"]
    return {
        "profile_isf": profile_isf,
        "baseline_isf_change_supported": bool(promotion["promote"]),
        "baseline_isf_gate_reason": promotion["reason"],
        "bolus_clean_events_full_history": status["bolus_clean_events"],
        "bolus_reopen_ready": status["bolus_reopen_ready"],
        "basal_clean_episodes_full_history": status["basal_clean_episodes"],
        "basal_equilibrium_episodes_full_history": status["basal_equilibrium_episodes"],
        "basal_route_context_ready": status["basal_route_context_ready"],
        "bolus_strict_exact_6h": bolus6,
        "basal_equilibrium_exact_6h": basal6,
        "decision": (
            "Hold ISF. Basal-route evidence is useful for monitoring Loop correction workload, but baseline ISF promotion still requires clean bolus-route convergence or a validated route-equivalence model."
            if not promotion["promote"]
            else "Reopen ISF for clinician review; strict clean bolus-route evidence passes the baseline promotion gate."
        ),
        "future_monitor_contract": [
            "Rerun after 7, 14, and 21 days of any basal-first change.",
            "Track bolus correction and excess-temp-basal correction routes separately.",
            "Keep inferred-meal exclusion at 2h before through 6h after for full-tail ISF monitoring.",
            f"Reopen baseline ISF review at {MIN_CLEAN_EVENTS_TO_REOPEN} strict clean bolus events.",
            f"Do not promote baseline ISF before about {BASELINE_PROMOTION_MIN_EVENTS} strict clean bolus events or equivalent tight-CI evidence.",
            "Use basal-route estimates as controller workload and directionality context until cross-route equivalence is validated.",
        ],
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _render_memo(result: dict[str, Any]) -> str:
    c = result["conclusion"]
    lines = [
        "# EXP-3460 live-recent route-aware ISF monitor",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Baseline ISF change supported: **{c['baseline_isf_change_supported']}**",
        f"- Gate reason: {c['baseline_isf_gate_reason']}",
        f"- Bolus strict-clean events, full history: {c['bolus_clean_events_full_history']}",
        f"- Basal-route strict-clean episodes, full history: {c['basal_clean_episodes_full_history']}",
        f"- Basal-route equilibrium episodes, full history: {c['basal_equilibrium_episodes_full_history']}",
        "",
        c["decision"],
        "",
        "## Window summary",
        "",
        "| Window | Bolus clean events | Bolus exact 6h | Basal clean episodes | Basal eq episodes | Basal eq exact 6h | ISF action |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["window_summaries"]:
        bolus_clean = row["bolus_route"]["strict_uam_clean"]
        basal_clean = row["basal_route"]["strict_uam_clean"]
        basal_eq = row["basal_route"]["strict_clean_equilibrium_context"]
        lines.append(
            f"| {row['label']} | {bolus_clean['events']} | "
            f"{_fmt(bolus_clean['isf_exact_6h'].get('median'))} | "
            f"{basal_clean['events']} | {basal_eq['events']} | "
            f"{_fmt(basal_eq['isf_exact_6h'].get('median'))} | "
            f"{row['route_status']['bolus_baseline_promotion']['reason']} |"
        )
    lines.extend(["", "## Future monitor contract", ""])
    lines.extend(f"- {item}" for item in c["future_monitor_contract"])
    lines.append("")
    return "\n".join(lines)


def run_experiment(
    patient_id: str = "live-recent",
    parquet_dir: Path = DEFAULT_PARQUET_DIR,
    out_json: Path = OUT_JSON,
    out_md: Path = OUT_MD,
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
    metabolic = compute_metabolic_state(patient)
    profile_isf = _profile_isf(profile)

    bolus_rows = _bolus_events(df, masks)
    basal_rows = _basal_route_events(df, masks, metabolic)
    end_time = pd.Timestamp(df["time"].max())
    windows = list(WINDOWS_DAYS) + [None]
    window_summaries = [
        _windowed_summary(bolus_rows, basal_rows, profile_isf, end_time, days)
        for days in windows
    ]
    result = {
        "exp": "EXP-3460",
        "title": "live-recent route-aware ISF evidence monitor",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": tz,
        "profile_isf": profile_isf,
        "monitor_rules": {
            "routes": ["bolus_correction", "loop_excess_temp_basal"],
            "horizons_hours": [2, 4, 6],
            "min_bg": MIN_BG,
            "min_bolus_u": MIN_BOLUS_U,
            "min_excess_rate_u_h": MIN_EXCESS_RATE_U_H,
            "prior_bolus_isolation_hours": 6,
            "strict_uam_exclusion": "2h before through 6h after",
            "reopen_clean_bolus_events": MIN_CLEAN_EVENTS_TO_REOPEN,
            "baseline_promotion_min_events": BASELINE_PROMOTION_MIN_EVENTS,
            "target_ci_width_mgdl_per_u": TARGET_CI_WIDTH,
        },
        "route_event_counts": {
            "bolus_qualified_events": len(bolus_rows),
            "bolus_strict_clean_events": int(sum(r["strict_clean"] for r in bolus_rows)),
            "basal_route_qualified_episodes": len(basal_rows),
            "basal_route_strict_clean_episodes": int(sum(r["strict_clean"] for r in basal_rows)),
            "basal_route_equilibrium_context_episodes": int(
                sum(r["strict_clean"] and r["equilibrium_context"] for r in basal_rows)
            ),
        },
        "window_summaries": window_summaries,
        "conclusion": _conclusion(window_summaries, profile_isf),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(_jsonable(result), indent=2, default=str))
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_render_memo(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patient-id", default="live-recent")
    parser.add_argument("--parquet-dir", type=Path, default=DEFAULT_PARQUET_DIR)
    parser.add_argument("--out-json", type=Path, default=OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    args = parser.parse_args()
    with start_run(
        run_name="research-live-recent-route-aware-isf-monitor",
        tags={"runner": "exp_live_recent_route_aware_isf_monitor_3460", "exp": "EXP-3460"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json, args.out_md)
        log_dict(result, "research/exp3460_live_recent_route_aware_isf_monitor.json")
        if args.out_md.exists():
            log_text(args.out_md.read_text(), "research/exp3460_live_recent_route_aware_isf_monitor.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
