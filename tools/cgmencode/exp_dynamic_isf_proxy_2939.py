"""EXP-2939 - Dynamic-ISF proxy test for the EXP-2937/2938 sizing lever.

EXP-2938 refuted velocity-sizing as the mechanism but confirmed a
constant +21 pp recovery gap. Candidate refined lever: dynamic-ISF /
autosens — a multiplier on the correction sensitivity that scales
with metabolic resistance state.

Direct test: bin correction events by starting BG (the natural input
to dynamic-ISF). If oref1 uses dynamic-ISF, its correction dose per
mg/dL-above-target should grow nonlinearly with bg_start (more
amplification at higher BG). Loop's correction is sized on linear
target deviation; its dose-per-mgdl should be flat or slightly
declining (because IOB-shortfall caps).

Metric: SMB_total_U_per_50mgdl_above_180 by (design, bg_start_tertile).
Also: recovery probability by bg_start (does oref1's edge grow with
starting hyperglycemia?).

Reuse EXP-2937 isolation (carb-guard 60 min, 30-min quiet pre-window).

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
OUT = REPO / "externals" / "experiments" / "exp-2939_summary.json"

RNG = np.random.default_rng(2939)
N_BOOT = 2000
HIGH = 180.0
TARGET = 100.0
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


def boot_diff(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    if len(a) < 2 or len(b) < 2:
        return float("nan"), float("nan"), float("nan")
    ba = RNG.choice(a, (N_BOOT, len(a)), replace=True).mean(axis=1)
    bb = RNG.choice(b, (N_BOOT, len(b)), replace=True).mean(axis=1)
    d = ba - bb
    return float(a.mean() - b.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


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
            # Track peak BG within window (for dose response analysis)
            bg = win["glucose"].values
            smb = win["bolus_smb"].fillna(0).values
            bg_peak = float(bg.max())
            rows.append({
                "patient_id": pid, "design": d,
                "bg_start": float(bg[0]),
                "bg_peak": bg_peak,
                "smb_total": float(smb.sum()),
                "smb_count": int((smb > 0).sum()),
                "decline": float((bg[0] - bg[-1]) / WINDOW_MIN),
                "recovered": bool(bg[-1] < HIGH),
            })

    ev = pd.DataFrame(rows)
    print(f"Total events: {len(ev):,}")

    # Use peak BG (the BG the controller actually saw and reacted to over the window)
    cuts = np.percentile(ev["bg_peak"], [33.33, 66.67])
    print(f"bg_peak tertiles: low<={cuts[0]:.0f}, mid<={cuts[1]:.0f}, high>{cuts[1]:.0f}")
    ev["bg_bin"] = pd.cut(ev["bg_peak"], bins=[-np.inf, cuts[0], cuts[1], np.inf],
                          labels=["low_bg", "mid_bg", "high_bg"])
    # Dose response metric: U per 50 mg/dL above target
    ev["above_target"] = ev["bg_peak"] - TARGET
    ev["dose_per_50mgdl"] = ev["smb_total"] / (ev["above_target"] / 50.0)

    per_pat = ev.groupby(["patient_id", "design", "bg_bin"], observed=True).agg(
        n_events=("bg_start", "size"),
        bg_peak=("bg_peak", "mean"),
        smb_total=("smb_total", "mean"),
        dose_per_50=("dose_per_50mgdl", "mean"),
        recovered=("recovered", "mean"),
    ).reset_index()
    per_pat = per_pat[per_pat["n_events"] >= 3]

    print("\n=== Per (design, bg_bin) — per-patient mean ===")
    summary = per_pat.groupby(["design", "bg_bin"], observed=True).agg(
        n_pat=("patient_id", "nunique"),
        events=("n_events", "mean"),
        bg_peak=("bg_peak", "mean"),
        smb_total_u=("smb_total", "mean"),
        dose_per_50mgdl=("dose_per_50", "mean"),
        recovered_pct=("recovered", lambda s: float(s.mean()) * 100),
    ).round(3)
    print(summary.to_string())

    # KEY TEST: dose_per_50mgdl scaling with bg_bin
    print("\n=== Dose-per-50mgdl scaling test (within-design slope across bg_bins) ===")
    print("If dynamic-ISF amplifies, dose_per_50 should INCREASE with bg_bin in oref1.")
    print("If linear-ISF, dose_per_50 should be flat or DECREASE in Loop.")
    for d in ["oref1", "Loop_AB_ON"]:
        sub = summary.xs(d, level="design")
        print(f"  {d}:")
        for bg_bin in sub.index:
            print(f"    {bg_bin}: dose/50={sub.loc[bg_bin,'dose_per_50mgdl']:.3f} U  recovered={sub.loc[bg_bin,'recovered_pct']:.1f}%")

    # Recovery gap by bg_bin
    print("\n=== oref1 - Loop_AB_ON recovery gap by bg_bin ===")
    pairs = []
    for bb in ["low_bg", "mid_bg", "high_bg"]:
        ov = per_pat[(per_pat.design == "oref1") & (per_pat.bg_bin == bb)]["recovered"].values
        lv = per_pat[(per_pat.design == "Loop_AB_ON") & (per_pat.bg_bin == bb)]["recovered"].values
        diff, lo, hi = boot_diff(ov, lv)
        sig = "*" if (lo > 0 or hi < 0) else " "
        print(f"  {bb:7s}: gap = {diff:+.3f}  CI[{lo:+.3f}, {hi:+.3f}] {sig}  (n_oref1={len(ov)}, n_loop={len(lv)})")
        pairs.append({"bg_bin": bb, "diff_recovered": diff, "ci_lo": lo, "ci_hi": hi,
                      "n_oref1": int(len(ov)), "n_loop_ab_on": int(len(lv))})

    # Dose-per-50 gap by bg_bin
    print("\n=== oref1 - Loop_AB_ON dose-per-50 gap by bg_bin ===")
    dose_pairs = []
    for bb in ["low_bg", "mid_bg", "high_bg"]:
        ov = per_pat[(per_pat.design == "oref1") & (per_pat.bg_bin == bb)]["dose_per_50"].values
        lv = per_pat[(per_pat.design == "Loop_AB_ON") & (per_pat.bg_bin == bb)]["dose_per_50"].values
        diff, lo, hi = boot_diff(ov, lv)
        sig = "*" if (lo > 0 or hi < 0) else " "
        print(f"  {bb:7s}: dose-per-50 gap = {diff:+.3f}  CI[{lo:+.3f}, {hi:+.3f}] {sig}")
        dose_pairs.append({"bg_bin": bb, "diff_dose_per_50": diff, "ci_lo": lo, "ci_hi": hi})

    out = {
        "scope": "Dynamic-ISF proxy test via dose-per-50mgdl scaling with peak BG (EXP-2937/2938 follow-up)",
        "n_events": int(len(ev)),
        "bg_peak_tertiles": [float(cuts[0]), float(cuts[1])],
        "summary": summary.reset_index().to_dict(orient="records"),
        "recovery_gap_by_bg_bin": pairs,
        "dose_per_50_gap_by_bg_bin": dose_pairs,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2939] {OUT}")


if __name__ == "__main__":
    main()
