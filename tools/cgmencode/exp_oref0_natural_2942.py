"""EXP-2942 - oref0 lineage as natural variation between algorithm vs selection.

After 8 candidates eliminated for the +21pp recovery gap (EXP-2937-2941),
remaining hypotheses are (a) unmeasured algorithmic channel, or
(b) patient self-selection.

oref0 (n=3) is a natural test:
- Same OpenAPS algorithm family as oref1 → if recovery looks like
  oref1, supports algorithm-family explanation.
- Different patient cohort than Loop or oref1 → if recovery looks like
  Loop_AB_ON, supports selection-bias hypothesis.
- oref0 lacks SMB-as-correction (the EXP-2937 hypothesised lever)
  but has autosens/dynamic-ISF.

Reuse EXP-2937 carb-isolated cohort. Add oref0 to the analysis.

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
OUT = REPO / "externals" / "experiments" / "exp-2942_summary.json"

RNG = np.random.default_rng(2942)
N_BOOT = 2000
HIGH = 180.0
WINDOW_MIN = 60
PRE_QUIET_MIN = 30
CARB_GUARD_MIN = 60

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}


def design_of(pid: str, lineage: str) -> str | None:
    if pid in OREF0_PATS:
        return "oref0"
    if lineage == "oref1 (modern)":
        return "oref1"
    if pid in LOOP_AB_ON:
        return "Loop_AB_ON"
    if pid in LOOP_AB_OFF:
        return "Loop_AB_OFF"
    return None


def boot_diff(a, b):
    if len(a) < 2 or len(b) < 2:
        return float("nan"), float("nan"), float("nan")
    ba = RNG.choice(a, (N_BOOT, len(a)), replace=True).mean(axis=1)
    bb = RNG.choice(b, (N_BOOT, len(b)), replace=True).mean(axis=1)
    d = ba - bb
    return float(a.mean() - b.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def main() -> None:
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    target_lin = ["Loop (iOS)", "oref1 (modern)", "oref0 (legacy)"]
    simp = simp[simp.lineage.isin(target_lin)]
    pid_to_lineage = dict(zip(simp.patient_id, simp.lineage))

    g = pd.read_parquet(GRID, columns=["patient_id", "time", "glucose", "carbs", "bolus_smb"])
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lineage[pid])
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True).copy()
        sub["bg_prev"] = sub["glucose"].shift(1)
        sub["bg_max_30"] = sub["glucose"].shift(1).rolling(window=PRE_QUIET_MIN // 5, min_periods=1).max()
        sub["carbs_60"] = sub["carbs"].shift(1).rolling(window=CARB_GUARD_MIN // 5, min_periods=1).sum()
        ents = sub[
            (sub["glucose"] > HIGH)
            & (sub["bg_prev"] <= HIGH)
            & (sub["bg_max_30"] <= HIGH)
            & (sub["carbs_60"].fillna(0) == 0)
        ].copy()
        idx_map = pd.Series(sub.index, index=sub["time"])
        n_cells = WINDOW_MIN // 5
        for _, ent in ents.iterrows():
            i0 = idx_map.get(ent["time"])
            if i0 is None:
                continue
            win = sub.iloc[i0:i0 + n_cells]
            if len(win) < n_cells or win["carbs"].fillna(0).sum() > 0:
                continue
            smb = win["bolus_smb"].fillna(0).values
            bg = win["glucose"].values
            rows.append({
                "patient_id": pid, "design": d,
                "smb_count": int((smb > 0).sum()),
                "smb_total": float(smb.sum()),
                "bg_start": float(bg[0]),
                "bg_peak": float(bg.max()),
                "decline": float((bg[0] - bg[-1]) / WINDOW_MIN),
                "recovered": bool(bg[-1] < HIGH),
            })

    ev = pd.DataFrame(rows)
    print(f"Total events: {len(ev):,}")
    print("Events by design:")
    print(ev.groupby("design").size())

    # Per-patient mean
    per_pat = ev.groupby(["patient_id", "design"]).agg(
        n_events=("recovered", "size"),
        smb_count=("smb_count", "mean"),
        smb_total=("smb_total", "mean"),
        decline=("decline", "mean"),
        recovered=("recovered", "mean"),
    ).reset_index()
    per_pat = per_pat[per_pat["n_events"] >= 5]

    print("\n=== Per-patient mean by design ===")
    summary = per_pat.groupby("design").agg(
        n_pat=("patient_id", "nunique"),
        events=("n_events", "mean"),
        smb_count=("smb_count", "mean"),
        smb_total=("smb_total", "mean"),
        decline=("decline", "mean"),
        recovered_pct=("recovered", lambda s: float(s.mean()) * 100),
    ).round(3)
    print(summary.to_string())

    print("\n=== Individual oref0 patients ===")
    print(per_pat[per_pat.design == "oref0"][["patient_id","n_events","smb_count","smb_total","decline","recovered"]].to_string(index=False))

    print("\n=== Bootstrap contrasts (recovered_pct) ===")
    contrasts = []
    designs = ["Loop_AB_OFF", "Loop_AB_ON", "oref0", "oref1"]
    for i, da in enumerate(designs):
        for db in designs[i+1:]:
            va = per_pat[per_pat.design == da]["recovered"].values
            vb = per_pat[per_pat.design == db]["recovered"].values
            diff, lo, hi = boot_diff(va, vb)
            sig = "*" if (lo > 0 or hi < 0) else " "
            print(f"  {da:12s} - {db:12s}: {diff:+.3f}  CI[{lo:+.3f}, {hi:+.3f}] {sig}")
            contrasts.append({"a": da, "b": db, "diff": diff, "ci_lo": lo, "ci_hi": hi,
                              "n_a": int(len(va)), "n_b": int(len(vb))})

    # Critical question: does oref0 cluster with oref1 (algorithm-family) or
    # with Loop_AB_ON (selection-bias / external)?
    print("\n=== Algorithm-family vs selection-bias diagnostic ===")
    oref0_v = per_pat[per_pat.design == "oref0"]["recovered"].values
    oref1_v = per_pat[per_pat.design == "oref1"]["recovered"].values
    loop_v = per_pat[per_pat.design == "Loop_AB_ON"]["recovered"].values
    if len(oref0_v) > 0:
        print(f"  oref0 mean recovery: {oref0_v.mean():.3f}")
        print(f"  oref1 mean recovery: {oref1_v.mean():.3f}")
        print(f"  Loop_AB_ON mean:     {loop_v.mean():.3f}")
        d_o0_o1 = abs(oref0_v.mean() - oref1_v.mean())
        d_o0_lp = abs(oref0_v.mean() - loop_v.mean())
        print(f"  |oref0 - oref1|:    {d_o0_o1:.3f}  (closer = algorithm-family)")
        print(f"  |oref0 - Loop_ON|:  {d_o0_lp:.3f}  (closer = selection-bias)")
        verdict = "ALGORITHM-FAMILY" if d_o0_o1 < d_o0_lp else "SELECTION-BIAS"
        print(f"  Verdict: {verdict}")

    out = {
        "scope": "oref0 lineage as natural test of algorithm-family vs selection-bias",
        "n_events": int(len(ev)),
        "by_design": summary.reset_index().to_dict(orient="records"),
        "per_pat_oref0": per_pat[per_pat.design == "oref0"].to_dict(orient="records"),
        "contrasts": contrasts,
        "verdict": verdict if len(oref0_v) > 0 else "insufficient",
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2942] {OUT}")


if __name__ == "__main__":
    main()
