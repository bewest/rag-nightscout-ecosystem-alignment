"""EXP-2940 - Within-window cumulative dose profile vs BG trajectory.

EXP-2939 narrowed the recovery mechanism to temporal-distribution
candidates. Direct test:
- For each correction event, compute cumulative SMB fraction at
  minutes [5, 10, 15, 20, 30, 45, 60].
- Compute time-to-BG-peak within window.
- Compare per-design profiles.

Hypothesis: Loop concentrates dose at front (10-20 min) while BG is
still rising; oref1 distributes dose later, aligned with peak.

Carry forward EXP-2937 carb-isolated cohort.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2940_summary.json"

RNG = np.random.default_rng(2940)
N_BOOT = 2000
HIGH = 180.0
WINDOW_MIN = 60
PRE_QUIET_MIN = 30
CARB_GUARD_MIN = 60
CHECKPOINTS = [5, 10, 15, 20, 30, 45, 60]

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
            smb = win["bolus_smb"].fillna(0).values
            bg = win["glucose"].values
            total = float(smb.sum())
            row = {
                "patient_id": pid, "design": d,
                "smb_total": total,
                "bg_start": float(bg[0]),
                "bg_peak": float(bg.max()),
                "time_to_bg_peak_min": int(np.argmax(bg)) * 5,
                "has_smb": total > 0,
            }
            # Cumulative SMB fraction at each checkpoint
            cum = np.cumsum(smb)
            for cp in CHECKPOINTS:
                idx = (cp // 5) - 1  # 5-min cells: cp=5 -> idx 0
                if idx < len(cum) and total > 0:
                    row[f"cum_frac_{cp}min"] = float(cum[idx] / total)
                else:
                    row[f"cum_frac_{cp}min"] = np.nan
            rows.append(row)

    ev = pd.DataFrame(rows)
    print(f"Total events: {len(ev):,}")
    print(f"Events with SMB delivery: {int(ev.has_smb.sum()):,}")

    # Restrict to events with SMBs for profile analysis
    evs = ev[ev.has_smb].copy()
    print(f"\nBy design (with SMB only):")
    print(evs.groupby("design").size())

    # Per-patient mean cumulative profile
    cp_cols = [f"cum_frac_{cp}min" for cp in CHECKPOINTS]
    per_pat = evs.groupby(["patient_id", "design"])[cp_cols + ["time_to_bg_peak_min", "smb_total"]].mean().reset_index()
    per_pat["n_events"] = evs.groupby(["patient_id", "design"]).size().values
    per_pat = per_pat[per_pat["n_events"] >= 5]

    print("\n=== Per-patient mean cumulative SMB fraction by design ===")
    summary = per_pat.groupby("design")[cp_cols + ["time_to_bg_peak_min", "smb_total"]].mean().round(3)
    summary["n_pat"] = per_pat.groupby("design").size()
    print(summary.to_string())

    # Bootstrap contrast oref1 - Loop_AB_ON at each checkpoint
    print("\n=== oref1 - Loop_AB_ON cum-fraction gap at each checkpoint ===")
    print("(Negative = oref1 distributes more dose later)")
    contrasts = []
    for cp in CHECKPOINTS:
        col = f"cum_frac_{cp}min"
        ov = per_pat[per_pat.design == "oref1"][col].dropna().values
        lv = per_pat[per_pat.design == "Loop_AB_ON"][col].dropna().values
        diff, lo, hi = boot_diff(ov, lv)
        sig = "*" if (lo > 0 or hi < 0) else " "
        print(f"  {cp:2d}min: oref1={ov.mean():.3f} loop={lv.mean():.3f} gap={diff:+.3f} CI[{lo:+.3f}, {hi:+.3f}] {sig}")
        contrasts.append({"checkpoint_min": cp, "oref1_frac": float(ov.mean()), "loop_frac": float(lv.mean()),
                          "diff": diff, "ci_lo": lo, "ci_hi": hi})

    print("\n=== Time-to-BG-peak by design (per-patient mean) ===")
    for d in ["Loop_AB_OFF", "Loop_AB_ON", "oref1"]:
        v = per_pat[per_pat.design == d]["time_to_bg_peak_min"].dropna().values
        if len(v) == 0:
            continue
        print(f"  {d:12s}: mean = {v.mean():.1f} min  (n={len(v)})")

    out = {
        "scope": "Within-window cumulative dose profile vs BG trajectory (EXP-2939 follow-up)",
        "n_events_with_smb": int(evs.shape[0]),
        "by_design": summary.reset_index().to_dict(orient="records"),
        "checkpoint_contrasts": contrasts,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2940] {OUT}")


if __name__ == "__main__":
    main()
