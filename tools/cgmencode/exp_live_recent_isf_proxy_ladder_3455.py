#!/usr/bin/env python3
"""EXP-3455: live-recent ISF proxy ladder from TDD and meals.

This experiment complements correction-event ISF extraction with proxies that
do not depend on announced meals being complete:

* combined basal+bolus delivered TDD and 1800/1500/1400-rule ISF proxies,
* profile/scheduled TDD rule proxies,
* logged meal carb/bolus distribution,
* inferred meal-size distribution from the production detector,
* meal-size sensitivity under alternate ISF assumptions.

It answers whether meal/TDD proxies make the 53-56 mg/dL/U correction-
denominator signal more credible, or whether they point somewhere else.
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
from cgmencode.production.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "externals" / "experiments"
OUT_JSON = RESULTS_DIR / "exp3455_live_recent_isf_proxy_ladder.json"
OUT_MD = RESULTS_DIR / "autoresearch" / "exp3455_live_recent_isf_proxy_ladder.md"

ISF_ASSUMPTIONS = (30.0, 40.0, 53.7, 56.0)
RULES = (1400.0, 1500.0, 1700.0, 1800.0)


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


def _summary(vals) -> dict[str, Any]:
    arr = np.array([v for v in vals if v is not None and np.isfinite(v)], dtype=float)
    if len(arr) == 0:
        return {"n": 0}
    return {
        "n": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
    }


def _tdd_proxy(df: pd.DataFrame) -> dict[str, Any]:
    days = max((df["time"].max() - df["time"].min()).total_seconds() / 86400.0, 1.0)
    bolus_u = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    if "bolus_smb" in df:
        bolus_u = bolus_u + df["bolus_smb"].fillna(0.0).to_numpy(dtype=float)
    actual_basal_u = df["actual_basal_rate"].fillna(0.0).to_numpy(dtype=float) / 12.0
    scheduled_basal_u = df["scheduled_basal_rate"].fillna(0.0).to_numpy(dtype=float) / 12.0

    day = pd.to_datetime(df["time"], utc=True).dt.date
    daily = pd.DataFrame({
        "day": day,
        "bolus_u": bolus_u,
        "actual_basal_u": actual_basal_u,
        "scheduled_basal_u": scheduled_basal_u,
    }).groupby("day").sum()
    daily["actual_tdd"] = daily["bolus_u"] + daily["actual_basal_u"]
    daily["profile_tdd"] = daily["bolus_u"] + daily["scheduled_basal_u"]
    actual_tdd = _summary(daily["actual_tdd"])
    profile_tdd = _summary(daily["profile_tdd"])

    def rules(tdd):
        if not tdd or not np.isfinite(tdd) or tdd <= 0:
            return {}
        return {f"rule_{int(r)}": float(r / tdd) for r in RULES}

    return {
        "days": float(days),
        "daily_bolus_u": _summary(daily["bolus_u"]),
        "daily_actual_basal_u": _summary(daily["actual_basal_u"]),
        "daily_scheduled_basal_u": _summary(daily["scheduled_basal_u"]),
        "daily_actual_tdd": actual_tdd,
        "daily_profile_tdd": profile_tdd,
        "actual_tdd_rule_isf_from_median": rules(actual_tdd.get("median")),
        "profile_tdd_rule_isf_from_median": rules(profile_tdd.get("median")),
    }


def _logged_meals(df: pd.DataFrame) -> dict[str, Any]:
    carbs = df["carbs"].fillna(0.0).to_numpy(dtype=float)
    bolus = df["bolus"].fillna(0.0).to_numpy(dtype=float)
    glucose = df["glucose"].to_numpy(dtype=float)
    rows = []
    for i, cg in enumerate(carbs):
        if cg < 5.0:
            continue
        lo = max(0, i - 24)
        hi = min(len(df), i + 25)
        bolus_2h = float(np.nansum(bolus[lo:hi]))
        pre = float(glucose[i]) if np.isfinite(glucose[i]) else np.nan
        rows.append({
            "index": int(i),
            "time": str(df["time"].iloc[i]),
            "carbs_g": float(cg),
            "bolus_pm2h_u": bolus_2h,
            "implied_cr_g_per_u": float(cg / bolus_2h) if bolus_2h > 0.05 else None,
            "pre_glucose": pre if np.isfinite(pre) else None,
        })
    return {
        "n_logged_meals": int(len(rows)),
        "carbs_g": _summary([r["carbs_g"] for r in rows]),
        "bolus_pm2h_u": _summary([r["bolus_pm2h_u"] for r in rows]),
        "implied_cr_g_per_u": _summary([r["implied_cr_g_per_u"] for r in rows]),
        "high_bolus_meal_count": int(sum((r["bolus_pm2h_u"] or 0.0) >= 5.0 for r in rows)),
        "rows_preview": rows[:12],
    }


def _inferred_meals(result, profile_isf: float) -> dict[str, Any]:
    meals = list(getattr(getattr(result, "meal_history", None), "meals", None) or [])
    rows = []
    for meal in meals:
        support = (getattr(meal, "metadata", {}) or {}).get("hybrid_meal_support", {})
        base = float(getattr(meal, "estimated_carbs_g", 0.0) or 0.0)
        rows.append({
            "index": int(getattr(meal, "index", -1)),
            "timestamp_ms": float(getattr(meal, "timestamp_ms", 0.0) or 0.0),
            "estimated_carbs_g": base,
            "announced": bool(getattr(meal, "announced", False)),
            "confidence": float(getattr(meal, "confidence", 0.0) or 0.0),
            "hybrid_support": str(support.get("support_level", "unknown")),
            "hybrid_score": support.get("hybrid_score"),
        })
    by_support = {}
    for support in sorted({r["hybrid_support"] for r in rows}):
        group = [r for r in rows if r["hybrid_support"] == support]
        by_support[support] = {
            "n": int(len(group)),
            "estimated_carbs_g": _summary([r["estimated_carbs_g"] for r in group]),
        }
    sensitivity = {}
    # Production meal sizing scales approximately as CR/ISF, so alternate
    # ISF assumptions rescale grams by profile_isf / assumed_isf.
    for assumed_isf in ISF_ASSUMPTIONS:
        scale = profile_isf / assumed_isf if assumed_isf > 0 else 1.0
        sensitivity[f"isf_{assumed_isf:g}"] = _summary(
            [r["estimated_carbs_g"] * scale for r in rows]
        )
    return {
        "n_inferred_meals": int(len(rows)),
        "announced_count": int(sum(r["announced"] for r in rows)),
        "unannounced_count": int(sum(not r["announced"] for r in rows)),
        "estimated_carbs_g": _summary([r["estimated_carbs_g"] for r in rows]),
        "by_hybrid_support": by_support,
        "meal_size_sensitivity_by_isf": sensitivity,
    }


def _conclusion(tdd: dict[str, Any], logged: dict[str, Any], inferred: dict[str, Any]) -> dict[str, Any]:
    actual_rules = tdd.get("actual_tdd_rule_isf_from_median", {})
    profile_rules = tdd.get("profile_tdd_rule_isf_from_median", {})
    rule_1800_actual = actual_rules.get("rule_1800")
    rule_1800_profile = profile_rules.get("rule_1800")
    inferred_med = inferred.get("estimated_carbs_g", {}).get("median")
    logged_cr = logged.get("implied_cr_g_per_u", {}).get("median")
    supports_53 = bool(
        (rule_1800_actual and 45 <= rule_1800_actual <= 65)
        or (rule_1800_profile and 45 <= rule_1800_profile <= 65)
    )
    return {
        "tdd_rules_support_53_56": supports_53,
        "actual_tdd_1800_rule_isf": rule_1800_actual,
        "profile_tdd_1800_rule_isf": rule_1800_profile,
        "median_inferred_meal_g_profile_isf": inferred_med,
        "median_logged_implied_cr": logged_cr,
        "meal_proxy_isf_decision": (
            "Meal/TDD proxies are useful context but should not override the strict clean-correction ISF hold."
        ),
        "interpretation": [
            "Combined basal+bolus TDD rules provide an independent prior, not a patient-specific extraction.",
            "Logged meal boluses can be correction-contaminated when meals are sparse and high-BG driven.",
            "Inferred meal grams are sensitive to assumed ISF; using lower demand-phase ISF inflates meal size, while 53-56 lowers it.",
            "Meal-derived evidence can normalize UAM sizing, but should feed a joint latent meal+insulin model rather than directly set ISF.",
        ],
    }


def _render_memo(result: dict[str, Any]) -> str:
    c = result["conclusion"]
    tdd = result["tdd"]
    logged = result["logged_meals"]
    inferred = result["inferred_meals"]
    lines = [
        "# EXP-3455 live-recent ISF proxy ladder",
        "",
        f"Generated: {result['generated_at_utc']}",
        "",
        "## Conclusion",
        "",
        f"- TDD rules support 53-56: **{c['tdd_rules_support_53_56']}**",
        f"- Actual-TDD 1800 rule ISF: {c['actual_tdd_1800_rule_isf']}",
        f"- Profile-TDD 1800 rule ISF: {c['profile_tdd_1800_rule_isf']}",
        f"- Median inferred meal grams at profile ISF: {c['median_inferred_meal_g_profile_isf']}",
        f"- Median logged implied CR: {c['median_logged_implied_cr']}",
        "",
        c["meal_proxy_isf_decision"],
        "",
        "## TDD",
        "",
        f"- Actual TDD median: {tdd['daily_actual_tdd'].get('median'):.1f} U/day",
        f"- Profile TDD median: {tdd['daily_profile_tdd'].get('median'):.1f} U/day",
        f"- Actual TDD rules: {tdd['actual_tdd_rule_isf_from_median']}",
        f"- Profile TDD rules: {tdd['profile_tdd_rule_isf_from_median']}",
        "",
        "## Meals",
        "",
        f"- Logged meals: {logged['n_logged_meals']}",
        f"- Logged meal carbs median: {logged['carbs_g'].get('median')}",
        f"- Logged meal bolus ±2h median: {logged['bolus_pm2h_u'].get('median')}",
        f"- Inferred meals: {inferred['n_inferred_meals']}",
        f"- Inferred meal grams median: {inferred['estimated_carbs_g'].get('median')}",
        "",
        "## Interpretation",
        "",
    ]
    lines.extend(f"- {item}" for item in c["interpretation"])
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
    result = run_pipeline(patient)
    profile_isf = float(df["scheduled_isf"].dropna().median()) if "scheduled_isf" in df else 40.0
    tdd = _tdd_proxy(df)
    logged = _logged_meals(df)
    inferred = _inferred_meals(result, profile_isf)
    payload = {
        "exp": "EXP-3455",
        "title": "live-recent ISF proxy ladder from TDD and meals",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "patient_id": patient_id,
        "parquet_dir": str(parquet_dir),
        "profile_timezone": tz,
        "profile_isf": profile_isf,
        "tdd": tdd,
        "logged_meals": logged,
        "inferred_meals": inferred,
        "conclusion": _conclusion(tdd, logged, inferred),
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
        run_name="research-live-recent-isf-proxy-ladder",
        tags={"runner": "exp_live_recent_isf_proxy_ladder_3455", "exp": "EXP-3455"},
        params={"patient_id": args.patient_id, "parquet_dir": str(args.parquet_dir)},
    ):
        result = run_experiment(args.patient_id, args.parquet_dir, args.out_json)
        log_dict(result, "research/exp3455_live_recent_isf_proxy_ladder.json")
        if OUT_MD.exists():
            log_text(OUT_MD.read_text(), "research/exp3455_live_recent_isf_proxy_ladder.md")
    print(json.dumps(_jsonable(result["conclusion"]), indent=2))


if __name__ == "__main__":
    main()
