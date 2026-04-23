"""EXP-2938 - Correction events binned by BG velocity at entry.

EXP-2937 finding: Loop_AB_ON fires more SMBs faster than oref1 yet
recovers less, suggesting a SIZING gap (dose to BG+velocity vs dose
to IOB-shortfall vs forecast).

Direct test: bin correction events on BG velocity at entry (mg/dL/min
over the 30 min before crossing >180). If Loop's under-correction is
worse at high positive velocity (forecast model less responsive to
acceleration), then:
- low_vel  bin: small or no oref1-vs-Loop_AB_ON recovery gap
- high_vel bin: large oref1-vs-Loop_AB_ON recovery gap

Carry forward EXP-2937 isolation (no carbs ±60 min).

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
OUT = REPO / "externals" / "experiments" / "exp-2938_summary.json"

RNG = np.random.default_rng(2938)
N_BOOT = 2000
HIGH = 180.0
WINDOW_MIN = 60
PRE_QUIET_MIN = 30
CARB_GUARD_MIN = 60

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}


def design_of(pid: str, lineage: str) -> str | None:
    if lineage == "oref1 (modern)":
        return "oref1"
    if pid in LOOP_AB_ON:
        return "Loop_AB_ON"
    if pid in LOOP_AB_OFF:
        return "Loop_AB_OFF"
    return None


def main() -> None:
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    simp = simp[simp.lineage.isin(["Loop (iOS)", "oref1 (modern)"])]
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
        sub["bg_30_ago"] = sub["glucose"].shift(6)  # 30 min ago
        sub["bg_max_30"] = sub["glucose"].shift(1).rolling(window=PRE_QUIET_MIN // 5, min_periods=1).max()
        sub["carbs_60"] = sub["carbs"].shift(1).rolling(window=CARB_GUARD_MIN // 5, min_periods=1).sum()
        ents = sub[
            (sub["glucose"] > HIGH)
            & (sub["bg_prev"] <= HIGH)
            & (sub["bg_max_30"] <= HIGH)
            & (sub["carbs_60"].fillna(0) == 0)
            & sub["bg_30_ago"].notna()
        ].copy()
        ents["velocity_30"] = (ents["glucose"] - ents["bg_30_ago"]) / 30.0  # mg/dL/min

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
                "velocity_30": float(ent["velocity_30"]),
                "smb_count": int((smb > 0).sum()),
                "smb_total": float(smb.sum()),
                "decline": float((bg[0] - bg[-1]) / WINDOW_MIN),
                "recovered": bool(bg[-1] < HIGH),
                "bg_start": float(bg[0]),
            })

    if not rows:
        print("No events.")
        return
    ev = pd.DataFrame(rows)
    print(f"Total events: {len(ev):,}")

    # Velocity tertiles (global, on oref1+Loop combined)
    cuts = np.percentile(ev["velocity_30"], [33.33, 66.67])
    print(f"velocity_30 tertile cutpoints: low<={cuts[0]:.3f}, mid<={cuts[1]:.3f}, high>{cuts[1]:.3f}")
    ev["vel_bin"] = pd.cut(ev["velocity_30"], bins=[-np.inf, cuts[0], cuts[1], np.inf],
                           labels=["low_vel", "mid_vel", "high_vel"])

    # Per-patient mean within (design, vel_bin)
    per_pat = ev.groupby(["patient_id", "design", "vel_bin"], observed=True).agg(
        n_events=("velocity_30", "size"),
        smb_count=("smb_count", "mean"),
        smb_total=("smb_total", "mean"),
        decline=("decline", "mean"),
        recovered=("recovered", "mean"),
    ).reset_index()
    per_pat = per_pat[per_pat["n_events"] >= 3]

    print("\n=== Per (design, vel_bin) means ===")
    summary = per_pat.groupby(["design", "vel_bin"], observed=True).agg(
        n_pat=("patient_id", "nunique"),
        events=("n_events", "mean"),
        smb_count=("smb_count", "mean"),
        smb_total=("smb_total", "mean"),
        decline=("decline", "mean"),
        recovered_pct=("recovered", lambda s: float(s.mean()) * 100),
    ).round(2)
    print(summary.to_string())

    print("\n=== oref1 - Loop_AB_ON recovery gap by velocity ===")
    pairs = []
    for vb in ["low_vel", "mid_vel", "high_vel"]:
        oref_v = per_pat[(per_pat.design == "oref1") & (per_pat.vel_bin == vb)]["recovered"].values
        loop_v = per_pat[(per_pat.design == "Loop_AB_ON") & (per_pat.vel_bin == vb)]["recovered"].values
        if len(oref_v) < 2 or len(loop_v) < 2:
            continue
        diff = float(oref_v.mean() - loop_v.mean())
        ba = RNG.choice(oref_v, (N_BOOT, len(oref_v)), replace=True).mean(axis=1)
        bb = RNG.choice(loop_v, (N_BOOT, len(loop_v)), replace=True).mean(axis=1)
        d = ba - bb
        lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
        sig = "*" if (lo > 0 or hi < 0) else " "
        print(f"  {vb:9s}: gap = {diff:+.3f}  CI[{lo:+.3f}, {hi:+.3f}] {sig}  (n_oref1={len(oref_v)} n_loop={len(loop_v)})")
        pairs.append({"vel_bin": vb, "diff_recovered": diff, "ci_lo": lo, "ci_hi": hi,
                      "n_oref1": int(len(oref_v)), "n_loop_ab_on": int(len(loop_v))})

    print("\n=== Decline rate gap (oref1 - Loop_AB_ON) by velocity ===")
    decl_pairs = []
    for vb in ["low_vel", "mid_vel", "high_vel"]:
        oref_v = per_pat[(per_pat.design == "oref1") & (per_pat.vel_bin == vb)]["decline"].values
        loop_v = per_pat[(per_pat.design == "Loop_AB_ON") & (per_pat.vel_bin == vb)]["decline"].values
        if len(oref_v) < 2 or len(loop_v) < 2:
            continue
        diff = float(oref_v.mean() - loop_v.mean())
        ba = RNG.choice(oref_v, (N_BOOT, len(oref_v)), replace=True).mean(axis=1)
        bb = RNG.choice(loop_v, (N_BOOT, len(loop_v)), replace=True).mean(axis=1)
        d = ba - bb
        lo, hi = float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))
        sig = "*" if (lo > 0 or hi < 0) else " "
        print(f"  {vb:9s}: gap = {diff:+.3f}  CI[{lo:+.3f}, {hi:+.3f}] {sig}")
        decl_pairs.append({"vel_bin": vb, "diff_decline": diff, "ci_lo": lo, "ci_hi": hi})

    out = {
        "scope": "Correction events binned by BG velocity at entry (EXP-2937 sizing test)",
        "n_events": int(len(ev)),
        "vel_cutpoints": [float(cuts[0]), float(cuts[1])],
        "summary": summary.reset_index().to_dict(orient="records"),
        "recovery_gap_by_vel": pairs,
        "decline_gap_by_vel": decl_pairs,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2938] {OUT}")


if __name__ == "__main__":
    main()
