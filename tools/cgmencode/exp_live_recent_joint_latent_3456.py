#!/usr/bin/env python3
"""EXP-3456: joint latent meal + insulin sensitivity grid.

Fits a simple joint model of glucose deltas:

    ΔBG ≈ intercept + meal_scale * inferred_meal_absorption
           - ISF * reconstructed_insulin_activity + decay_to_target

The experiment compares fixed ISF candidates (30, 40, 53.7, 56 plus TDD
priors) while fitting only the meal absorption scale and intercept on training
days. It then scores validation days. This tests whether a higher ISF can be
rescued by jointly lowering inferred meal sizes, or whether profile/lower ISF
explains the data better once hidden meals are represented.
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
from cgmencode.exp_live_recent_isf_proxy_ladder_3455 import _tdd_proxy
from cgmencode.exp_live_recent_uam_autosens_3454 import _reconstruct_activity
from cgmencode.mlflow_utils import log_dict, log_text, start_run
from cgmencode.production.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3456_live_recent_joint_latent.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3456_live_recent_joint_latent.md"

ISF_CANDIDATES = (27.6, 30.0, 40.0, 43.4, 53.7, 56.0)
CR_DEFAULT = 10.0
DECAY_TARGET = 120.0
DECAY_RATE = 0.005


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


def _meal_absorption_signal(n: int, meals, *, profile_isf: float, cr: float) -> np.ndarray:
    signal = np.zeros(n, dtype=float)
    # Gamma-like absorption over 4h, peak around 75 min.
    steps = 48
    t = (np.arange(steps, dtype=float) + 0.5) / 12.0
    theta = 0.625
    kernel = (t ** 2) * np.exp(-t / theta)
    kernel = kernel / max(float(kernel.sum()), 1e-12)
    for meal in meals:
        idx = int(getattr(meal, "index", -1))
        if idx < 0 or idx >= n:
            continue
        grams = float(getattr(meal, "estimated_carbs_g", 0.0) or 0.0)
        mgdl_total = grams * profile_isf / max(cr, 1.0)
        end = min(n, idx + steps)
        signal[idx:end] += mgdl_total * kernel[:end - idx]
    return signal


def _fit_linear(
    y: np.ndarray,
    meal: np.ndarray,
    insulin_effect: np.ndarray,
    train: np.ndarray,
    *,
    mode: str,
) -> dict[str, float | str]:
    # Candidate ISF already applied to insulin_effect. Fit intercept and a
    # meal scale. The unconstrained scale is useful diagnostically, but the
    # detector's grams already include insulin-covered glucose load, so very
    # low scales are expected and must not be over-interpreted as biology.
    target = y[train] + insulin_effect[train]
    if mode == "fixed_1_0":
        meal_scale = 1.0
        intercept = float(np.mean(target - meal_scale * meal[train]))
    elif mode.startswith("min_"):
        floor = float(mode.split("_", 1)[1])
        x = np.column_stack([np.ones(train.sum()), meal[train]])
        coef, *_ = np.linalg.lstsq(x, target, rcond=None)
        meal_scale = max(float(coef[1]), floor)
        intercept = float(np.mean(target - meal_scale * meal[train]))
    elif mode == "grid_0_5_1_5":
        best = None
        for scale in np.linspace(0.5, 1.5, 21):
            intercept = float(np.mean(target - scale * meal[train]))
            pred = intercept + scale * meal - insulin_effect
            score = _score(y, pred, train)
            candidate = (score.get("rmse", 1e9), float(scale), intercept)
            if best is None or candidate[0] < best[0]:
                best = candidate
        assert best is not None
        _, meal_scale, intercept = best
    else:
        x = np.column_stack([np.ones(train.sum()), meal[train]])
        coef, *_ = np.linalg.lstsq(x, target, rcond=None)
        intercept = float(coef[0])
        meal_scale = max(float(coef[1]), 0.0)
        mode = "unconstrained_nonnegative"
    return {"intercept": intercept, "meal_scale": meal_scale, "mode": mode}


def _score(y: np.ndarray, pred: np.ndarray, mask: np.ndarray) -> dict[str, float | int]:
    err = y[mask] - pred[mask]
    if len(err) == 0:
        return {"n": 0}
    ss_res = float(np.sum(err ** 2))
    yy = y[mask]
    ss_tot = float(np.sum((yy - np.mean(yy)) ** 2))
    return {
        "n": int(len(err)),
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "bias": float(np.mean(err)),
        "r2": float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0,
        "p95_abs_error": float(np.percentile(np.abs(err), 95)),
    }


def _run_grid(df: pd.DataFrame, result, profile_isf: float, cr: float) -> dict[str, Any]:
    glucose = df["glucose"].to_numpy(dtype=float)
    y = np.full(len(df), np.nan)
    y[1:] = glucose[1:] - glucose[:-1]
    valid = np.isfinite(y) & np.isfinite(glucose)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    if "bolus_smb" in df:
        bolus = bolus + df["bolus_smb"].fillna(0.0).to_numpy(dtype=float)
    basal = df["actual_basal_rate"].fillna(0.0).to_numpy(dtype=float)
    activity = _reconstruct_activity(bolus, basal, dia_hours=5.0)
    meals = list(getattr(getattr(result, "meal_history", None), "meals", None) or [])
    meal_signal = _meal_absorption_signal(len(df), meals, profile_isf=profile_isf, cr=cr)
    decay = (DECAY_TARGET - glucose) * DECAY_RATE

    days = pd.to_datetime(df["time"], utc=True).dt.floor("D")
    unique_days = np.array(sorted(days.dropna().unique()))
    split_idx = int(len(unique_days) * 0.7)
    train_days = set(unique_days[:split_idx])
    train = valid & days.isin(train_days).to_numpy()
    test = valid & (~days.isin(train_days)).to_numpy()

    modes = ("unconstrained", "min_0.5", "min_0.75", "fixed_1_0", "grid_0_5_1_5")
    mode_rows = {}
    for mode in modes:
        rows = []
        for isf in ISF_CANDIDATES:
            insulin_effect = activity * float(isf)
            fit = _fit_linear(y - decay, meal_signal, insulin_effect, train, mode=mode)
            pred = (
                float(fit["intercept"])
                + float(fit["meal_scale"]) * meal_signal
                - insulin_effect
                + decay
            )
            rows.append({
                "isf": float(isf),
                "fit": fit,
                "meal_median_g_after_scale": (
                    float(np.median([float(getattr(m, "estimated_carbs_g", 0.0) or 0.0) * float(fit["meal_scale"]) for m in meals]))
                    if meals else None
                ),
                "train": _score(y, pred, train),
                "test": _score(y, pred, test),
                "all": _score(y, pred, valid),
            })
        rows.sort(key=lambda r: (r["test"].get("rmse", 1e9), r["test"].get("mae", 1e9)))
        mode_rows[mode] = {"candidates": rows, "best": rows[0] if rows else None}
    rows = mode_rows["unconstrained"]["candidates"]
    return {
        "n_meals": int(len(meals)),
        "split": {
            "n_days": int(len(unique_days)),
            "n_train_days": int(len(train_days)),
            "n_test_days": int(len(unique_days) - len(train_days)),
        },
        "candidates": rows,
        "best": rows[0] if rows else None,
        "modes": mode_rows,
    }


def _conclusion(grid: dict[str, Any]) -> dict[str, Any]:
    modes = grid.get("modes") or {"unconstrained": grid}
    primary_mode = "min_0.5" if "min_0.5" in modes else "unconstrained"
    primary = modes[primary_mode]
    best = primary.get("best") or {}
    best_isf = best.get("isf")
    candidates = primary.get("candidates", [])
    by_isf = {float(r["isf"]): r for r in candidates}
    def rmse(isf):
        row = by_isf.get(float(isf))
        return row["test"].get("rmse") if row else None
    rmse_40 = rmse(40.0)
    rmse_537 = rmse(53.7)
    delta_537 = (rmse_537 - rmse_40) if rmse_537 is not None and rmse_40 is not None else None
    return {
        "primary_mode": primary_mode,
        "best_isf_by_validation_rmse": best_isf,
        "best_test_rmse": best.get("test", {}).get("rmse"),
        "rmse_40": rmse_40,
        "rmse_53_7": rmse_537,
        "rmse_53_7_minus_40": delta_537,
        "best_by_mode": {
            mode: ((block.get("best") or {}).get("isf"))
            for mode, block in modes.items()
        },
        "supports_53_56": bool(best_isf in (53.7, 56.0) and delta_537 is not None and delta_537 <= 0),
        "interpretation": (
            "Joint meal+insulin fit selects the higher ISF candidate on validation."
            if best_isf in (53.7, 56.0) else
            "Joint meal+insulin fit, including plausible meal-scale constraints, does not select the 53-56 baseline; meal scale adaptation alone is not enough to promote that ISF."
        ),
    }


def _render_memo(payload: dict[str, Any]) -> str:
    c = payload["conclusion"]
    lines = [
        "# EXP-3456 live-recent joint latent meal+insulin model",
        "",
        f"Generated: {payload['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- Primary mode: {c['primary_mode']}",
        f"- Best validation ISF: {c['best_isf_by_validation_rmse']}",
        f"- Supports 53-56: **{c['supports_53_56']}**",
        f"- RMSE 40: {c['rmse_40']}",
        f"- RMSE 53.7: {c['rmse_53_7']}",
        "",
        c["interpretation"],
        "",
        "## Candidates",
        "",
        "| ISF | meal scale | scaled median meal g | test RMSE | test MAE | test R2 |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    primary_mode = c["primary_mode"]
    for row in payload["grid"]["modes"][primary_mode]["candidates"]:
        lines.append(
            f"| {row['isf']:.1f} | {row['fit']['meal_scale']:.3f} | "
            f"{row['meal_median_g_after_scale'] if row['meal_median_g_after_scale'] is not None else 'n/a'} | "
            f"{row['test'].get('rmse', 0):.3f} | {row['test'].get('mae', 0):.3f} | "
            f"{row['test'].get('r2', 0):.4f} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_experiment(
    patient_id: str = "live-recent",
    parquet_dir: Path = DEFAULT_PARQUET_DIR,
    out_json: Path = OUT_JSON,
) -> dict[str, Any]:
    grid_df = pd.read_parquet(parquet_dir / "grid.parquet")
    df = grid_df[grid_df["patient_id"] == patient_id].copy()
    if df.empty:
        raise SystemExit(f"No rows for patient_id={patient_id!r}")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values("time").reset_index(drop=True)
    tz = _profile_timezone(parquet_dir, patient_id)
    profile = _make_profile(df, tz)
    patient = _make_patient(df, profile, patient_id)
    result = run_pipeline(patient)
    profile_isf = float(df["scheduled_isf"].dropna().median()) if "scheduled_isf" in df else 40.0
    cr = float(df["scheduled_cr"].dropna().median()) if "scheduled_cr" in df else CR_DEFAULT
    model_grid = _run_grid(df, result, profile_isf=profile_isf, cr=cr)
    payload = {
        "exp": "EXP-3456",
        "title": "live-recent joint latent meal+insulin model",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": tz,
        "profile_isf": profile_isf,
        "profile_cr": cr,
        "tdd_context": _tdd_proxy(df),
        "grid": model_grid,
        "conclusion": _conclusion(model_grid),
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
        run_name="research-live-recent-joint-latent",
        tags={"runner": "exp_live_recent_joint_latent_3456", "exp": "EXP-3456"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3456_live_recent_joint_latent.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3456_live_recent_joint_latent.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
