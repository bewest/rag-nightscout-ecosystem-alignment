"""EXP-2929 - PP TIR by Loop autobolus on/off vs oref1.

Synthesis EXP-2927 question: does Loop autobolus close any of
the 27 pp PP TIR gap, or is UAM/dynamic-ISF the binding lever?

Splits Loop into autobolus-OFF (n=2: a, f) and autobolus-ON
(n=5: c, d, e, g, i). Computes per-state TIR/TBR/TAR. Compares
to oref1.

Scope: design-feature characterisation. AID-author audience.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2929_summary.json"

RNG = np.random.default_rng(2929)
N_BOOT = 2000
TBR = 70
TAR = 180

LOOP_AUTOBOLUS_OFF = {"a", "f"}
LOOP_AUTOBOLUS_ON = {"c", "d", "e", "g", "i"}


def boot_mean_ci(values: np.ndarray) -> tuple[float, float]:
    if len(values) < 2:
        v = float(values[0]) if len(values) == 1 else float("nan")
        return v, v
    samples = RNG.choice(values, size=(N_BOOT, len(values)), replace=True).mean(axis=1)
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def main() -> None:
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    simp = simp[simp.lineage.isin(["Loop (iOS)", "oref1 (modern)"])]

    g = pd.read_parquet(GRID, columns=["patient_id", "glucose", "time_since_carb_min"])
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g["state"] = np.where(g.time_since_carb_min >= 300, "FASTED",
                          np.where(g.time_since_carb_min <= 180, "PP", "MID"))
    g = g[g.state != "MID"]

    rows = []
    for (pid, st), sub in g.groupby(["patient_id", "state"]):
        if len(sub) < 100:
            continue
        rows.append({
            "patient_id": pid, "state": st, "n_cells": len(sub),
            "tir": float(((sub.glucose >= TBR) & (sub.glucose <= TAR)).mean()) * 100,
            "tar": float((sub.glucose > TAR).mean()) * 100,
            "tbr": float((sub.glucose < TBR).mean()) * 100,
        })
    pat = pd.DataFrame(rows).merge(simp, on="patient_id")

    def design(pid, lin):
        if lin == "oref1 (modern)":
            return "oref1"
        if pid in LOOP_AUTOBOLUS_ON:
            return "Loop_AB_ON"
        if pid in LOOP_AUTOBOLUS_OFF:
            return "Loop_AB_OFF"
        return None

    pat["design"] = [design(p, l) for p, l in zip(pat.patient_id, pat.lineage)]
    pat = pat.dropna(subset=["design"])

    print("=== TIR/TAR/TBR by (design, state) ===")
    summary_rows = []
    for (d, st), sub in pat.groupby(["design", "state"]):
        tir = sub.tir.values
        tar = sub.tar.values
        tbr = sub.tbr.values
        tir_lo, tir_hi = boot_mean_ci(tir)
        summary_rows.append({
            "design": d, "state": st, "n": int(len(sub)),
            "tir_mean": float(tir.mean()),
            "tir_ci_lo": tir_lo, "tir_ci_hi": tir_hi,
            "tar_mean": float(tar.mean()),
            "tbr_mean": float(tbr.mean()),
        })
        print(f"  {d:12s} {st:7s}  n={len(sub)}  TIR={tir.mean():5.2f} CI[{tir_lo:5.2f},{tir_hi:5.2f}]  "
              f"TAR={tar.mean():5.2f}  TBR={tbr.mean():5.2f}")

    print("\n=== Pairwise gap to oref1 (oref1 - design, pp) ===")
    pairs = []
    oref1_pp = pat[(pat.design == "oref1") & (pat.state == "PP")]["tir"].values
    oref1_fa = pat[(pat.design == "oref1") & (pat.state == "FASTED")]["tir"].values
    for d in ["Loop_AB_OFF", "Loop_AB_ON"]:
        for st, ref in [("FASTED", oref1_fa), ("PP", oref1_pp)]:
            cmp_v = pat[(pat.design == d) & (pat.state == st)]["tir"].values
            if len(cmp_v) == 0:
                continue
            gap = float(ref.mean() - cmp_v.mean())
            if len(ref) >= 2 and len(cmp_v) >= 2:
                br = RNG.choice(ref, size=(N_BOOT, len(ref)), replace=True).mean(axis=1)
                bc = RNG.choice(cmp_v, size=(N_BOOT, len(cmp_v)), replace=True).mean(axis=1)
                gaps = br - bc
                ci_lo = float(np.percentile(gaps, 2.5))
                ci_hi = float(np.percentile(gaps, 97.5))
                sig = (ci_lo > 0) or (ci_hi < 0)
            else:
                ci_lo = ci_hi = float("nan"); sig = None
            pairs.append({"design_compared": d, "state": st,
                          "n_design": int(len(cmp_v)), "n_oref1": int(len(ref)),
                          "tir_gap_oref1_minus_design_pp": gap,
                          "ci_lo": ci_lo, "ci_hi": ci_hi, "sig": sig})
            print(f"  oref1 - {d:12s} {st:7s} = {gap:+5.2f}pp  CI=[{ci_lo:+.2f},{ci_hi:+.2f}]  "
                  f"n={len(cmp_v)},{len(ref)} sig={sig}")

    print("\n=== Within-Loop autobolus effect (ON vs OFF, pp) ===")
    within = []
    for st in ["FASTED", "PP"]:
        on_v = pat[(pat.design == "Loop_AB_ON") & (pat.state == st)]["tir"].values
        off_v = pat[(pat.design == "Loop_AB_OFF") & (pat.state == st)]["tir"].values
        if len(on_v) == 0 or len(off_v) == 0:
            continue
        eff = float(on_v.mean() - off_v.mean())
        if len(on_v) >= 2 and len(off_v) >= 2:
            bo = RNG.choice(on_v, size=(N_BOOT, len(on_v)), replace=True).mean(axis=1)
            bf = RNG.choice(off_v, size=(N_BOOT, len(off_v)), replace=True).mean(axis=1)
            d = bo - bf
            ci_lo, ci_hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
            sig = (ci_lo > 0) or (ci_hi < 0)
        else:
            ci_lo = ci_hi = float("nan"); sig = None
        within.append({"state": st, "tir_ON_minus_OFF_pp": eff,
                       "ci_lo": ci_lo, "ci_hi": ci_hi, "sig": sig,
                       "n_on": int(len(on_v)), "n_off": int(len(off_v))})
        print(f"  {st:7s}: ON-OFF = {eff:+5.2f}pp  CI=[{ci_lo:+.2f},{ci_hi:+.2f}]  "
              f"n_on={len(on_v)} n_off={len(off_v)} sig={sig}")

    out = {
        "scope": "PP TIR by Loop autobolus on/off vs oref1",
        "by_design_state": summary_rows,
        "pairs_oref1_minus_design": pairs,
        "within_loop_autobolus_effect": within,
        "patient_records": pat.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2929] {OUT}")


if __name__ == "__main__":
    main()
