"""EXP-3030 — LOPO robustness check for the EXP-3028 carb-aware refit.

EXP-3028 reported a +0.0082 verification-stripe lift over EXP-3025-FIX
(0.6660 vs 0.6577) by re-fitting per-patient (T*, M*) under the same
carb-aware proxy used by the scorer. Because the lift comes from a
table that *changes per-patient recommendations* (unlike EXP-3027-FIX,
which only adds conservatism), it cannot ship without first
demonstrating that no single patient is carrying the lift.

This experiment mirrors EXP-3025-LOPO: leave-one-patient-out on the
verification stripe at gate=0.10, but using EXP-3028's carb-aware
per-patient table instead of EXP-3017's clamped table.

PASS criteria:
  (a) every LOPO split keeps stratified safety;
  (b) every split keeps composite delta >= 0.5 * full-cohort delta;
  (c) full-cohort delta >= EXP-3017-clamped delta (no regression).

Outputs (gitignored):
  externals/experiments/exp-3030_lopo_results.json
  externals/experiments/exp-3030_lopo_results.csv
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
CARB_AWARE_REC = EXP_DIR / "exp-3028_per_patient_carb_aware.parquet"
CLAMPED_REC = EXP_DIR / "exp-3017_per_patient_clamped.parquet"

GATE = 0.10
KW = dict(
    multiplier=1.0,
    t_shift=0.0,
    per_patient=True,
    proxy="carb_aware",
    braking_mode="drop",
    per_patient_source="clamped",  # we monkeypatch what 'clamped' points to
    safety_mode="stratified",
    phenotype_source="imputed",
)


def _evaluate(events_path: Path, profiles, rec_path: Path) -> dict:
    """Evaluate with `rec_path` swapped in as the 'clamped' source.

    The scorer reads `PER_PATIENT_REC_CLAMPED` at module level (not at
    call time), so we monkey-patch the module attribute around the call.
    """
    saved = scorer.PER_PATIENT_REC_CLAMPED
    try:
        scorer.PER_PATIENT_REC_CLAMPED = rec_path
        cand = scorer.ascent_score_v3(profiles, braking_gate=GATE,
                                      events_path=events_path, **KW)
        base = scorer.ascent_score_v3(
            profiles, multiplier=1.0, t_shift=0.0, per_patient=False,
            proxy="carb_aware", braking_gate=None, braking_mode="recommended",
            per_patient_source="raw", safety_mode="stratified",
            phenotype_source="imputed", events_path=events_path,
        )
    finally:
        scorer.PER_PATIENT_REC_CLAMPED = saved

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
    for p in (VERIF_EVENTS, CARB_AWARE_REC, CLAMPED_REC):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1

    _ev, _ph, profiles = replay.load_inputs()
    full = pd.read_parquet(VERIF_EVENTS)
    pids = sorted(full["patient_id"].unique())
    print(f"verif: {len(full)} events, {len(pids)} patients")

    full_clamped = _evaluate(VERIF_EVENTS, profiles, CLAMPED_REC)
    full_carb = _evaluate(VERIF_EVENTS, profiles, CARB_AWARE_REC)
    print(f"\nFULL clamped (EXP-3017)   delta={full_clamped['delta']:+.4f}  "
          f"safety_ok={full_clamped['safety_ok']}")
    print(f"FULL carb-aware (EXP-3028) delta={full_carb['delta']:+.4f}  "
          f"safety_ok={full_carb['safety_ok']}  "
          f"lift={full_carb['delta']-full_clamped['delta']:+.4f}")
    composite_floor = 0.5 * full_carb["delta"]

    rows = []
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for i, pid in enumerate(pids, 1):
            sub = full[full["patient_id"] != pid]
            tmp_path = tdp / f"verif_lopo_{i}.parquet"
            sub.to_parquet(tmp_path, index=False)
            res = _evaluate(tmp_path, profiles, CARB_AWARE_REC)
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
    df.to_csv(EXP_DIR / "exp-3030_lopo_results.csv", index=False)

    deltas = df["delta"].to_numpy()
    summary = {
        "exp_id": "EXP-3030",
        "gate": GATE,
        "rec_table": str(CARB_AWARE_REC.relative_to(REPO)),
        "n_splits": len(df),
        "full_cohort_carb_aware": full_carb,
        "full_cohort_clamped_baseline": full_clamped,
        "composite_floor": composite_floor,
        "delta_mean": float(np.mean(deltas)),
        "delta_std": float(np.std(deltas, ddof=1)) if len(deltas) > 1 else 0.0,
        "delta_min": float(np.min(deltas)),
        "delta_max": float(np.max(deltas)),
        "all_safety_ok": bool(df["safety_ok"].all()),
        "all_passes_floor": bool(df["passes_floor"].all()),
        "no_regression_vs_clamped": bool(
            full_carb["delta"] >= full_clamped["delta"]),
        "n_safety_fail": int((~df["safety_ok"]).sum()),
        "n_floor_fail": int((~df["passes_floor"]).sum()),
        "safety_fail_pids": df.loc[~df["safety_ok"], "left_out"].tolist(),
        "floor_fail_pids": df.loc[~df["passes_floor"], "left_out"].tolist(),
    }
    summary["verdict"] = "PASS" if (
        summary["all_safety_ok"]
        and summary["all_passes_floor"]
        and summary["no_regression_vs_clamped"]
    ) else "FAIL"
    out = EXP_DIR / "exp-3030_lopo_results.json"
    out.write_text(json.dumps(summary, indent=2))

    print()
    print(f"[EXP-3030] verdict={summary['verdict']}")
    print(f"  delta mean={summary['delta_mean']:+.4f}  "
          f"std={summary['delta_std']:.4f}  "
          f"min={summary['delta_min']:+.4f}  max={summary['delta_max']:+.4f}")
    print(f"  safety_ok all? {summary['all_safety_ok']}  "
          f"({summary['n_safety_fail']} fails: {summary['safety_fail_pids']})")
    print(f"  passes_floor all? {summary['all_passes_floor']}  "
          f"({summary['n_floor_fail']} fails: {summary['floor_fail_pids']})")
    print(f"  no regression vs clamped? "
          f"{summary['no_regression_vs_clamped']}")
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
