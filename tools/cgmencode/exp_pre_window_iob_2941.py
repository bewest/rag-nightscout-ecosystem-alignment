"""EXP-2941 - Pre-window IOB proxy and recovery prediction.

EXP-2940 narrowed the recovery mechanism to PRE-WINDOW state.
Direct test: compute prior_smb_3h (sum of SMB units delivered in
the 3 hours before the correction window opens) as IOB proxy.

Tests:
1. Does oref1 enter correction windows with higher prior_smb_3h
   than Loop?
2. Within a design, does higher prior_smb_3h predict better recovery?
3. Does conditioning on prior_smb_3h tertile collapse the recovery
   gap (Guard #8 application)?

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
OUT = REPO / "externals" / "experiments" / "exp-2941_summary.json"

RNG = np.random.default_rng(2941)
N_BOOT = 2000
HIGH = 180.0
WINDOW_MIN = 60
PRE_QUIET_MIN = 30
PRIOR_WIN_MIN = 180  # 3 hours
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

    n_prior = PRIOR_WIN_MIN // 5  # 36 cells
    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lineage[pid])
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True).copy()
        sub["bg_prev"] = sub["glucose"].shift(1)
        sub["bg_max_30"] = sub["glucose"].shift(1).rolling(window=PRE_QUIET_MIN // 5, min_periods=1).max()
        sub["carbs_60"] = sub["carbs"].shift(1).rolling(window=CARB_GUARD_MIN // 5, min_periods=1).sum()
        sub["prior_smb_3h"] = sub["bolus_smb"].shift(1).rolling(window=n_prior, min_periods=1).sum()
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
                "prior_smb_3h": float(ent["prior_smb_3h"]) if pd.notna(ent["prior_smb_3h"]) else 0.0,
                "smb_total_in_window": float(smb.sum()),
                "bg_start": float(bg[0]),
                "decline": float((bg[0] - bg[-1]) / WINDOW_MIN),
                "recovered": bool(bg[-1] < HIGH),
            })

    ev = pd.DataFrame(rows)
    print(f"Total events: {len(ev):,}")

    # 1. Per-design distribution of prior_smb_3h
    print("\n=== Pre-window IOB-proxy by design (per-event) ===")
    for d in ["Loop_AB_OFF", "Loop_AB_ON", "oref1"]:
        sub = ev[ev.design == d]["prior_smb_3h"].values
        print(f"  {d:12s}: n={len(sub)} mean={sub.mean():.3f}U median={np.median(sub):.3f}U "
              f"q25={np.percentile(sub,25):.3f} q75={np.percentile(sub,75):.3f}")

    # Bootstrap on per-patient mean prior_smb_3h
    per_pat_mean = ev.groupby(["patient_id", "design"])["prior_smb_3h"].mean().reset_index()
    print("\n=== Per-patient mean prior_smb_3h ===")
    for d in ["Loop_AB_OFF", "Loop_AB_ON", "oref1"]:
        v = per_pat_mean[per_pat_mean.design == d]["prior_smb_3h"].values
        print(f"  {d:12s}: n_pat={len(v)} mean={v.mean():.3f}U")
    ov = per_pat_mean[per_pat_mean.design == "oref1"]["prior_smb_3h"].values
    lv = per_pat_mean[per_pat_mean.design == "Loop_AB_ON"]["prior_smb_3h"].values
    diff, lo, hi = boot_diff(ov, lv)
    print(f"  oref1 - Loop_AB_ON: {diff:+.3f}U  CI[{lo:+.3f}, {hi:+.3f}]")

    # 2. Within-design: does prior_smb_3h predict recovery?
    print("\n=== Within-design: prior_smb_3h tertile -> recovery_pct ===")
    for d in ["Loop_AB_ON", "oref1"]:
        sub = ev[ev.design == d].copy()
        if len(sub) < 30:
            continue
        cuts = np.percentile(sub["prior_smb_3h"], [33.33, 66.67])
        sub["prior_bin"] = pd.cut(sub["prior_smb_3h"], bins=[-np.inf, cuts[0], cuts[1], np.inf],
                                   labels=["low", "mid", "high"])
        per = sub.groupby("prior_bin", observed=True).agg(n=("recovered", "size"),
                                                           rec_pct=("recovered", lambda s: float(s.mean())*100),
                                                           mean_prior=("prior_smb_3h", "mean")).round(2)
        print(f"  {d}:")
        print(per.to_string())

    # 3. Recovery gap conditioned on global prior_smb_3h tertile (Guard #8)
    print("\n=== Recovery gap conditioned on global prior_smb_3h tertile ===")
    cuts_global = np.percentile(ev["prior_smb_3h"], [33.33, 66.67])
    ev["prior_bin_g"] = pd.cut(ev["prior_smb_3h"], bins=[-np.inf, cuts_global[0], cuts_global[1], np.inf],
                                labels=["low_prior", "mid_prior", "high_prior"])
    print(f"  Global prior_smb_3h tertiles: low<={cuts_global[0]:.2f}, mid<={cuts_global[1]:.2f}, high>{cuts_global[1]:.2f}")
    pp = ev.groupby(["patient_id", "design", "prior_bin_g"], observed=True)["recovered"].mean().reset_index()
    pp_n = ev.groupby(["patient_id", "design", "prior_bin_g"], observed=True).size().rename("n").reset_index()
    pp = pp.merge(pp_n, on=["patient_id", "design", "prior_bin_g"])
    pp = pp[pp["n"] >= 3]
    contrasts = []
    for pb in ["low_prior", "mid_prior", "high_prior"]:
        ov = pp[(pp.design == "oref1") & (pp.prior_bin_g == pb)]["recovered"].values
        lv = pp[(pp.design == "Loop_AB_ON") & (pp.prior_bin_g == pb)]["recovered"].values
        diff, lo, hi = boot_diff(ov, lv)
        sig = "*" if (lo > 0 or hi < 0) else " "
        print(f"  {pb:11s}: gap = {diff:+.3f}  CI[{lo:+.3f}, {hi:+.3f}] {sig}  (n_oref1={len(ov)} n_loop={len(lv)})")
        contrasts.append({"prior_bin": pb, "gap": diff, "ci_lo": lo, "ci_hi": hi,
                          "n_oref1": int(len(ov)), "n_loop": int(len(lv))})

    # Distribution of events across prior_bins by design
    print("\n=== Cell distribution by design × prior_bin (% of design events) ===")
    dist = (ev.groupby(["design", "prior_bin_g"], observed=True).size()
            / ev.groupby("design").size() * 100).unstack(fill_value=0).round(1)
    print(dist)

    out = {
        "scope": "Pre-window IOB proxy (prior_smb_3h) test of pre-window state mechanism",
        "n_events": int(len(ev)),
        "per_pat_prior_smb_3h": per_pat_mean.to_dict(orient="records"),
        "global_tertiles": [float(cuts_global[0]), float(cuts_global[1])],
        "recovery_gap_by_prior_bin": contrasts,
        "design_prior_distribution": dist.to_dict(),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2941] {OUT}")


if __name__ == "__main__":
    main()
