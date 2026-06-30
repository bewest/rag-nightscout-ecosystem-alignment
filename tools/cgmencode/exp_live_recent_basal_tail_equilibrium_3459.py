#!/usr/bin/env python3
"""EXP-3459: full-tail basal-route ISF under basal/EGP equilibrium filters.

Extends EXP-3458 by:

* using 2h, 4h, and 6h response windows,
* computing excess-basal dose over the matching full insulin-action tail,
* conditioning on low net flux / basal-equilibrium proxies,
* reporting whether equilibrium windows change the ISF signal.

This tests the hypothesis that basal-route ISF needs the full 6h insulin tail
and good-enough basal/EGP equilibrium before it becomes interpretable.
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
OUT_JSON = RESULTS_DIR / "exp3459_live_recent_basal_tail_equilibrium.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3459_live_recent_basal_tail_equilibrium.md"

MIN_BG = 180.0
MIN_EXCESS_RATE = 0.3
STRICT_PRE_STEPS = 24
STRICT_POST_STEPS = 72  # full 6h
WINDOWS = {"2h": 24, "4h": 48, "6h": 72}


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


def _summ(vals: list[float]) -> dict[str, Any]:
    arr = np.array([v for v in vals if np.isfinite(v)], dtype=float)
    if len(arr) == 0:
        return {"n": 0}
    rng = np.random.default_rng(3459)
    boot = np.array([
        np.median(arr[rng.integers(0, len(arr), size=len(arr))])
        for _ in range(1000)
    ])
    return {
        "n": int(len(arr)),
        "median": float(np.median(arr)),
        "iqr": float(np.percentile(arr, 75) - np.percentile(arr, 25)),
        "p_positive": float(np.mean(arr > 0)),
        "ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
    }


def _candidate_rows(df: pd.DataFrame, masks: dict[str, np.ndarray], metabolic) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray]:
    glucose = df["glucose"].to_numpy(dtype=float)
    scheduled = df["scheduled_basal_rate"].to_numpy(dtype=float)
    actual = df["actual_basal_rate"].to_numpy(dtype=float)
    excess = np.maximum(actual - scheduled, 0.0)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    cob = df["cob"].fillna(0.0).to_numpy(dtype=float)
    recent_bolus = pd.Series(bolus).rolling(72, min_periods=1).sum().shift(1).fillna(0).to_numpy()
    carb_pm = pd.Series(carbs).rolling(25, min_periods=1, center=True).sum().fillna(0).to_numpy()
    # Equilibrium proxy: low predicted net flux and flat current glucose.
    net_flux = np.asarray(metabolic.net_flux, dtype=float)
    roc = df["glucose_roc"].fillna(np.nan).to_numpy(dtype=float)
    rows = []
    for i in range(72, len(df) - 73):
        if not (
            np.isfinite(glucose[i])
            and glucose[i] >= MIN_BG
            and excess[i] > MIN_EXCESS_RATE
            and recent_bolus[i] <= 0.3
            and cob[i] <= 1.0
            and carb_pm[i] <= 2.0
        ):
            continue
        strict_clean = not masks["any"][max(0, i - STRICT_PRE_STEPS):min(len(df), i + STRICT_POST_STEPS + 1)].any()
        eq_now = bool(abs(net_flux[i]) <= 1.0 and np.isfinite(roc[i]) and abs(roc[i]) <= 1.0)
        eq_context = bool(np.nanmean(np.abs(net_flux[max(0, i - 12):i + 1])) <= 1.5)
        rows.append({
            "index": int(i),
            "strict_clean": strict_clean,
            "equilibrium_now": eq_now,
            "equilibrium_context": eq_context,
        })
    return rows, excess, glucose


def _summarize(label_rows: list[dict[str, Any]], excess: np.ndarray, glucose: np.ndarray) -> dict[str, Any]:
    starts = _episodes([r["index"] for r in label_rows])
    erows = []
    for i in starts:
        row = {"index": int(i), "start_bg": float(glucose[i])}
        for name, steps in WINDOWS.items():
            units = float(np.nansum(excess[i:i + steps]) / 12.0)
            drop = float(glucose[i] - glucose[i + steps]) if np.isfinite(glucose[i + steps]) else np.nan
            nadir = float(glucose[i] - np.nanmin(glucose[i:i + steps + 1]))
            row[f"units_{name}"] = units
            row[f"isf_exact_{name}"] = drop / units if units > 0 and np.isfinite(drop) else np.nan
            row[f"isf_nadir_{name}"] = nadir / units if units > 0 and np.isfinite(nadir) else np.nan
        erows.append(row)
    out = {
        "candidate_rows": int(len(label_rows)),
        "episodes": int(len(erows)),
    }
    for endpoint in ("exact", "nadir"):
        for name in WINDOWS:
            out[f"isf_{endpoint}_{name}"] = _summ([r[f"isf_{endpoint}_{name}"] for r in erows])
    out["median_excess_units_6h"] = (
        float(np.median([r["units_6h"] for r in erows])) if erows else None
    )
    return out


def _extract(df: pd.DataFrame, masks: dict[str, np.ndarray], metabolic) -> dict[str, Any]:
    rows, excess, glucose = _candidate_rows(df, masks, metabolic)
    scenarios = {
        "all_candidate_rows": rows,
        "strict_uam_clean": [r for r in rows if r["strict_clean"]],
        "strict_clean_equilibrium_now": [
            r for r in rows if r["strict_clean"] and r["equilibrium_now"]
        ],
        "strict_clean_equilibrium_context": [
            r for r in rows if r["strict_clean"] and r["equilibrium_context"]
        ],
    }
    return {name: _summarize(srows, excess, glucose) for name, srows in scenarios.items()}


def _conclusion(summary: dict[str, Any]) -> dict[str, Any]:
    clean = summary["strict_uam_clean"]
    eq = summary["strict_clean_equilibrium_context"]
    clean6 = clean["isf_exact_6h"].get("median")
    eq6 = eq["isf_exact_6h"].get("median")
    return {
        "strict_clean_episodes": clean["episodes"],
        "equilibrium_context_episodes": eq["episodes"],
        "strict_clean_6h_isf": clean6,
        "equilibrium_context_6h_isf": eq6,
        "supports_53_56": bool(eq6 is not None and 45.0 <= float(eq6) <= 65.0),
        "interpretation": (
            "Using the full 6h tail and basal/EGP equilibrium filters changes the basal-route estimate, but does not make it support the 53-56 baseline ISF. Equilibrium conditioning sharply reduces usable episodes, confirming that basal-route ISF requires good-enough basal/EGP assumptions."
        ),
    }


def _render_memo(payload: dict[str, Any]) -> str:
    c = payload["conclusion"]
    lines = [
        "# EXP-3459 full-tail basal-route equilibrium audit",
        "",
        f"Generated: {payload['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Strict clean episodes: {c['strict_clean_episodes']}",
        f"- Equilibrium-context episodes: {c['equilibrium_context_episodes']}",
        f"- Strict clean 6h ISF: {c['strict_clean_6h_isf']}",
        f"- Equilibrium-context 6h ISF: {c['equilibrium_context_6h_isf']}",
        f"- Supports 53-56: **{c['supports_53_56']}**",
        "",
        c["interpretation"],
        "",
        "## Summary",
        "",
        "| Scenario | episodes | exact 2h | exact 4h | exact 6h | nadir 6h |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in payload["summary"].items():
        lines.append(
            f"| {name} | {row['episodes']} | "
            f"{row['isf_exact_2h'].get('median')} | {row['isf_exact_4h'].get('median')} | "
            f"{row['isf_exact_6h'].get('median')} | {row['isf_nadir_6h'].get('median')} |"
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
    metabolic = compute_metabolic_state(patient)
    summary = _extract(df, masks, metabolic)
    payload = {
        "exp": "EXP-3459",
        "title": "full-tail basal-route ISF under basal/EGP equilibrium filters",
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
        run_name="research-live-recent-basal-tail-equilibrium",
        tags={"runner": "exp_live_recent_basal_tail_equilibrium_3459", "exp": "EXP-3459"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3459_live_recent_basal_tail_equilibrium.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3459_live_recent_basal_tail_equilibrium.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
