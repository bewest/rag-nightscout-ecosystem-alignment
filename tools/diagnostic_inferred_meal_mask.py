"""Diagnostic: compare logged-only vs inferred-meal-aware fasting masks
on cohort patients for the EGP-equilibrium experiment (EXP-2740).

Reports # of fasting rows retained, EGP-proxy median, and the delta
between the two mask strategies.  Validates the size of the under-logger
correction without re-running the full cohort.
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
    identify_fasting_mask,
    compute_fasting_decomposition,
)
from cgmencode.production.inferred_meals_facts_loader import (  # noqa: E402
    InferredMealsLoader,
)


def diagnose_patient(pdf: pd.DataFrame, pid: str, loader: InferredMealsLoader) -> dict:
    facts = loader.lookup(pid)
    n_meals = len(facts.events) if facts.events is not None else 0
    if n_meals == 0:
        return {"pid": pid, "n_meals": 0, "skip": True}

    # Skip the experiment's strict insulin_activity gate (which depends on
    # device-status payloads not always present in cohort grids) so we can
    # isolate the contribution of the inferred-meal exclusion overlay.
    pdf = pdf.copy()
    if "insulin_activity" in pdf.columns and not np.isfinite(pdf["insulin_activity"]).any():
        pdf["insulin_activity"] = 0.0

    mask_l = identify_fasting_mask(pdf, patient_id=None, use_inferred_meals=False)
    mask_i = identify_fasting_mask(pdf, patient_id=pid)
    nl, ni = int(mask_l.sum()), int(mask_i.sum())

    return {
        "pid": pid,
        "n_meals": n_meals,
        "n_fasting_logged": nl,
        "n_fasting_inferred": ni,
        "excluded": nl - ni,
        "pct_excluded": (nl - ni) / max(nl, 1) * 100,
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
        # Auto-populate cache for a small representative sample of cohort
        # patients so the diagnostic actually exercises the patches.
        sample = sorted(df["patient_id"].unique())[:5]
        print(f"  No cohort overlap with cache; computing on-the-fly for "
              f"{len(sample)} patients: {sample}")
        for pid in sample:
            pdf = df[df["patient_id"] == pid].sort_values("time").reset_index(drop=True)
            if "time" in pdf.columns and pd.api.types.is_datetime64_any_dtype(pdf["time"]):
                pass
            else:
                pdf = pdf.assign(time=pd.to_datetime(pdf["time"], utc=True))
            try:
                loader.compute_for(pid, pdf, cache=True)
            except Exception as exc:
                print(f"    compute_for({pid}) failed: {exc}")
        pids = sorted(set(df["patient_id"].unique()) & set(loader.known_patients()))
        print(f"  After auto-populate: {len(pids)} patients with inferred meals\n")

    print(f"  Overlap: {len(pids)} patients\n")
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
    print(f"\n  Median % fasting rows excluded: {rdf['pct_excluded'].median():.1f}%")


if __name__ == "__main__":
    main()

