"""Diagnostic: compare logged-only vs inferred-meal-aware fasting masks
on cohort patients for the EGP/ISF/basal experiments.

Reports for each patient:
  - # fasting rows under each strategy (basal-EGP scope, EXP-2740)
  - # ISF correction events under each strategy (EXP-2739)
  - median ISF and EGP-equilibrium drift estimates
  - delta between strategies

Validates that the inferred-meal exclusion overlay materially affects
the downstream metrics, not just the row count.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from cgmencode.exp_basal_egp_equilibrium_2740 import (  # noqa: E402
    GRID,
    identify_fasting_mask as fasting_mask_2740,
)
from cgmencode.exp_egp_personalization_2739 import (  # noqa: E402
    extract_correction_events,
    POP_EGP,
)
from cgmencode.production.inferred_meals_facts_loader import (  # noqa: E402
    InferredMealsLoader,
)


def _patch_insulin_activity(pdf: pd.DataFrame) -> pd.DataFrame:
    """Cohort training grid lacks insulin_activity (devicestatus.iob.activity
    not populated). Stub it to 0 so the experiment masks don't reject every
    row; this isolates the contribution of the inferred-meal overlay."""
    pdf = pdf.copy()
    if "insulin_activity" in pdf.columns and not np.isfinite(pdf["insulin_activity"]).any():
        pdf["insulin_activity"] = 0.0
    return pdf


def diagnose_patient(pdf: pd.DataFrame, pid: str, loader: InferredMealsLoader) -> dict:
    facts = loader.lookup(pid)
    n_meals = len(facts.events) if facts.events is not None else 0
    if n_meals == 0:
        return {"pid": pid, "n_meals": 0, "skip": True}

    pdf = _patch_insulin_activity(pdf)

    # ── Fasting (EXP-2740) ────────────────────────────────────────────
    nl_f = int(fasting_mask_2740(pdf, patient_id=None, use_inferred_meals=False).sum())
    ni_f = int(fasting_mask_2740(pdf, patient_id=pid).sum())

    # ── ISF correction events (EXP-2739) ─────────────────────────────
    pop_l, _ = extract_correction_events(pdf, POP_EGP, patient_id=None,
                                          use_inferred_meals=False)
    pop_i, _ = extract_correction_events(pdf, POP_EGP, patient_id=pid)
    n_evt_l, n_evt_i = len(pop_l), len(pop_i)
    isf_l = float(np.nanmedian([e["isf"] for e in pop_l])) if pop_l else float("nan")
    isf_i = float(np.nanmedian([e["isf"] for e in pop_i])) if pop_i else float("nan")

    return {
        "pid": pid,
        "n_meals": n_meals,
        "fast_logged": nl_f,
        "fast_inferred": ni_f,
        "fast_excl_pct": (nl_f - ni_f) / max(nl_f, 1) * 100,
        "isf_evts_logged": n_evt_l,
        "isf_evts_inferred": n_evt_i,
        "isf_evts_excluded": n_evt_l - n_evt_i,
        "isf_med_logged": isf_l,
        "isf_med_inferred": isf_i,
        "isf_delta": isf_i - isf_l if np.isfinite(isf_l) and np.isfinite(isf_i) else float("nan"),
    }


def main() -> None:
    print(f"Loading cohort grid: {GRID}")
    df = pd.read_parquet(GRID)
    loader = InferredMealsLoader()
    known = list(loader.known_patients())
    print(f"  Cohort: {df['patient_id'].nunique()} patients; "
          f"InferredMeals cache: {len(known)} patients")

    pids = sorted(set(df["patient_id"].unique()) & set(known))
    if not pids:
        sample = sorted(df["patient_id"].unique())[:5]
        print(f"  No cohort overlap; computing on-the-fly for {sample}")
        for pid in sample:
            pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
            try:
                loader.compute_for(pid, pdf, cache=True)
            except Exception as exc:
                print(f"    compute_for({pid}) failed: {exc}")
        pids = sorted(set(df["patient_id"].unique()) & set(loader.known_patients()))

    print(f"  Diagnosing {len(pids)} patients\n")
    results = []
    for pid in pids:
        pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
        r = diagnose_patient(pdf, pid, loader)
        results.append(r)

    rdf = pd.DataFrame([r for r in results if not r.get("skip")])
    if rdf.empty:
        print("  No patients had any inferred meals.")
        return

    print(rdf.to_string(index=False, float_format=lambda v: f"{v:7.2f}"))
    print(f"\n  Median % fasting rows excluded: {rdf['fast_excl_pct'].median():.1f}%")
    print(f"  Median ISF events excluded:     "
          f"{rdf['isf_evts_excluded'].median():.0f} of "
          f"{rdf['isf_evts_logged'].median():.0f} "
          f"({rdf['isf_evts_excluded'].median() / max(rdf['isf_evts_logged'].median(),1) * 100:.1f}%)")
    isf_d = rdf["isf_delta"].dropna()
    if len(isf_d):
        print(f"  Median ISF delta (inferred − logged): "
              f"{isf_d.median():+.1f} mg/dL/U")


if __name__ == "__main__":
    main()


