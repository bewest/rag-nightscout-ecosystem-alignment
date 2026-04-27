"""EXP-3025-LOPO — Leave-one-patient-out robustness check for gate=0.10.

EXP-3025-FIX recommended gate=0.10 as the new headline. The verification
stripe has now been touched twice (EXP-3025 + EXP-3025-FIX), so the
holdout's status is partially compromised. This experiment provides an
independent robustness signal that does not consume any new calendar
holdout: leave-one-patient-out (LOPO).

For each patient p in the cohort, drop p from the verification stripe
events and re-evaluate stratified safety + composite delta at gate=0.10.
PASS if all splits keep:
  (a) verif_safety_ok == True
  (b) verif composite delta >= 0.5 * full-cohort verif composite delta

Outputs (gitignored):
  externals/experiments/exp-3025-lopo_results.json
  externals/experiments/exp-3025-lopo_results.csv
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

SCORER_PATH = REPO / "tools" / "aid-autoresearch" / "cf_replay_score_v3.py"
_spec = importlib.util.spec_from_file_location("cf_replay_score_v3", SCORER_PATH)
scorer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scorer)

from tools.cgmencode.autoresearch_cf import replay  # noqa: E402

EXP_DIR = REPO / "externals" / "experiments"
VERIF_EVENTS = EXP_DIR / "exp-3007_ascent_events__verification.parquet"

GATE = 0.10
KW = dict(
    multiplier=1.0,
    t_shift=0.0,
    per_patient=True,
    proxy="carb_aware",
    braking_mode="drop",
    per_patient_source="clamped",
    safety_mode="stratified",
    phenotype_source="imputed",
)


def _evaluate(events_path: Path, profiles) -> dict:
    cand = scorer.ascent_score_v3(profiles, braking_gate=GATE,
                                   events_path=events_path, **KW)
    base = scorer.ascent_score_v3(
        profiles, multiplier=1.0, t_shift=0.0, per_patient=False,
        proxy="carb_aware", braking_gate=None, braking_mode="recommended",
        per_patient_source="raw", safety_mode="stratified",
        phenotype_source="imputed", events_path=events_path,
    )
    safety_ok = all(r["passes"] for r in cand.get("per_stratum", []))
    return {
        "delta": cand["ascent_score"] - base["ascent_score"],
        "cand_score": cand["ascent_score"],
        "base_score": base["ascent_score"],
        "max_hypo": cand["max_hypo_rate"],
        "safety_ok": safety_ok,
        "n_dropped_braking": cand["meta"]["n_dropped_braking"],
        "per_stratum": cand.get("per_stratum", []),
    }


def main() -> int:
    if not VERIF_EVENTS.exists():
        print(f"missing {VERIF_EVENTS}", file=sys.stderr)
        return 1

    _ev, _ph, profiles = replay.load_inputs()
    full = pd.read_parquet(VERIF_EVENTS)
    pids = sorted(full["patient_id"].unique())
    print(f"verif: {len(full)} events, {len(pids)} patients")

    # Full-cohort baseline at gate=0.10
    full_eval = _evaluate(VERIF_EVENTS, profiles)
    print(f"\nFULL  delta={full_eval['delta']:+.4f}  "
          f"safety_ok={full_eval['safety_ok']}  "
          f"max_hypo={full_eval['max_hypo']:.4f}")
    composite_floor = 0.5 * full_eval["delta"]

    rows = []
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for i, pid in enumerate(pids, 1):
            sub = full[full["patient_id"] != pid]
            tmp_path = tdp / f"verif_lopo_{i}.parquet"
            sub.to_parquet(tmp_path, index=False)
            res = _evaluate(tmp_path, profiles)
            rows.append({
                "left_out": pid,
                "n_events_remaining": int(len(sub)),
                "delta": res["delta"],
                "max_hypo": res["max_hypo"],
                "safety_ok": res["safety_ok"],
                "n_dropped_braking": res["n_dropped_braking"],
                "passes_floor": res["delta"] >= composite_floor,
            })
            print(f"[{i:>2}/{len(pids)}] -{pid:<24}  "
                  f"delta={res['delta']:+.4f}  "
                  f"safe={res['safety_ok']}  "
                  f"floor={'ok' if rows[-1]['passes_floor'] else 'NO'}")

    df = pd.DataFrame(rows)
    df.to_csv(EXP_DIR / "exp-3025-lopo_results.csv", index=False)

    deltas = df["delta"].to_numpy()
    summary = {
        "exp_id": "EXP-3025-LOPO",
        "gate": GATE,
        "n_splits": len(df),
        "full_cohort": full_eval,
        "composite_floor": composite_floor,
        "delta_mean": float(np.mean(deltas)),
        "delta_std": float(np.std(deltas, ddof=1)) if len(deltas) > 1 else 0.0,
        "delta_min": float(np.min(deltas)),
        "delta_max": float(np.max(deltas)),
        "all_safety_ok": bool(df["safety_ok"].all()),
        "all_passes_floor": bool(df["passes_floor"].all()),
        "n_safety_fail": int((~df["safety_ok"]).sum()),
        "n_floor_fail": int((~df["passes_floor"]).sum()),
        "safety_fail_pids": df.loc[~df["safety_ok"], "left_out"].tolist(),
        "floor_fail_pids": df.loc[~df["passes_floor"], "left_out"].tolist(),
    }
    summary["verdict"] = "PASS" if (
        summary["all_safety_ok"] and summary["all_passes_floor"]
    ) else "FAIL"
    out = EXP_DIR / "exp-3025-lopo_results.json"
    out.write_text(json.dumps(summary, indent=2))

    print()
    print(f"[EXP-3025-LOPO] verdict={summary['verdict']}")
    print(f"  delta mean={summary['delta_mean']:+.4f}  "
          f"std={summary['delta_std']:.4f}  "
          f"min={summary['delta_min']:+.4f}  max={summary['delta_max']:+.4f}")
    print(f"  safety_ok all? {summary['all_safety_ok']}  "
          f"({summary['n_safety_fail']} fails: {summary['safety_fail_pids']})")
    print(f"  passes_floor all? {summary['all_passes_floor']}  "
          f"({summary['n_floor_fail']} fails: {summary['floor_fail_pids']})")
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
