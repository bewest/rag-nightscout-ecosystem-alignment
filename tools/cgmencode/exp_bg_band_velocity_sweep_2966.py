"""EXP-2966 - BG-band sweep of SMB-channel velocity-coupling.

Maps the "lever-3 surface": at what BG ranges does SMB-on-velocity
matter most for AID authors tuning triggering thresholds?

Bands: [70-100, 100-140, 140-180, 180-220, 220-260, 260-300]
Contexts:
  - PP: carbs >= 30 g announced at start, no carbs in prior 60 min.
  - no-carb: no carbs in prior 120 min.

For each (band, context, design), fit ins_60_smb ~ vel_30 with 95% CI.
At each window-entry index i, BG band is bg[i].

Scope: AID-author audience.
What this is NOT: per-patient therapy advice.
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2966_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

BANDS = [(70, 100), (100, 140), (140, 180), (180, 220), (220, 260), (260, 300)]


def design_of(pid, lin):
    if pid in OREF0_PATS:
        return "oref0"
    if lin == "oref1 (modern)":
        return "oref1"
    if pid in LOOP_AB_ON:
        return "Loop_AB_ON"
    if pid in LOOP_AB_OFF:
        return "Loop_AB_OFF"
    return None


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    pid_to_lin = dict(zip(simp.patient_id, simp.lineage))

    cols = ["patient_id", "time", "glucose", "carbs", "bolus", "bolus_smb",
            "actual_basal_rate", "scheduled_basal_rate"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)
    g["basal_excess"] = ((g["actual_basal_rate"].fillna(0) -
                          g["scheduled_basal_rate"].fillna(0)) * 5.0 / 60.0).clip(lower=0)

    VEL_WIN = 6
    INS_WIN = 12

    pp_rows = []  # PP context windows
    nc_rows = []  # no-carb context windows
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_12 = sub["carbs"].fillna(0).shift(1).rolling(12, min_periods=1).sum().fillna(0).values
        carbs_24 = sub["carbs"].fillna(0).shift(1).rolling(24, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        basal_x = sub["basal_excess"].values
        bolus = sub["bolus"].fillna(0).values
        n = len(sub)
        for i in range(1, n - INS_WIN):
            if np.isnan(bg[i]):
                continue
            j = i + VEL_WIN
            xs = np.arange(VEL_WIN + 1) * 5.0
            ys = bg[i:j + 1]
            if np.any(np.isnan(ys)):
                continue
            xm = xs.mean(); ym = ys.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            vel = float(np.sum((xs - xm) * (ys - ym)) / denom)
            row = {
                "patient_id": pid, "design": d, "bg_entry": float(bg[i]),
                "vel_30": vel,
                "ins_60_smb": float(smb[i:i + INS_WIN].sum()),
                "ins_60_basal_excess": float(basal_x[i:i + INS_WIN].sum()),
                "ins_60_bolus": float(bolus[i:i + INS_WIN].sum()),
            }
            # PP context
            if carbs[i] >= 30 and carbs_12[i] == 0:
                pp_rows.append(row)
            # no-carb context
            if carbs_24[i] == 0 and carbs[i] == 0:
                nc_rows.append(row)

    pp_ev = pd.DataFrame(pp_rows)
    nc_ev = pd.DataFrame(nc_rows)
    print(f"PP windows: {len(pp_ev):,}")
    print(f"no-carb windows: {len(nc_ev):,}")

    from scipy import stats

    def assign_band(bg):
        for lo, hi in BANDS:
            if lo <= bg < hi:
                return f"{lo}-{hi}"
        return None

    def sweep(ev, ctx_label):
        ev = ev.copy()
        ev["band"] = ev["bg_entry"].apply(assign_band)
        ev = ev.dropna(subset=["band"])
        results = []
        print(f"\n=== {ctx_label} context: SMB-channel slopes by band x design ===")
        for band in [f"{lo}-{hi}" for lo, hi in BANDS]:
            for design in ["Loop_AB_ON", "oref1", "Loop_AB_OFF", "oref0"]:
                sub = ev[(ev.band == band) & (ev.design == design)]
                if len(sub) < 30:
                    continue
                sl_smb, _, _, p_smb, se_smb = stats.linregress(sub["vel_30"], sub["ins_60_smb"])
                sl_bx, _, _, p_bx, se_bx = stats.linregress(sub["vel_30"], sub["ins_60_basal_excess"])
                row = {"context": ctx_label, "band": band, "design": design,
                       "n": int(len(sub)), "n_pat": int(sub.patient_id.nunique()),
                       "smb_slope": float(sl_smb), "smb_ci_lo": float(sl_smb - 1.96 * se_smb),
                       "smb_ci_hi": float(sl_smb + 1.96 * se_smb), "smb_p": float(p_smb),
                       "basal_x_slope": float(sl_bx), "basal_x_p": float(p_bx)}
                results.append(row)
                print(f"  {band:>8} {design:>12} n={len(sub):>4} "
                      f"SMB={sl_smb:+.4f} 95%CI [{sl_smb-1.96*se_smb:+.4f},{sl_smb+1.96*se_smb:+.4f}] "
                      f"basal_x={sl_bx:+.4f}")
        return results

    pp_results = sweep(pp_ev, "PP")
    nc_results = sweep(nc_ev, "no_carb")

    # find sweet-spot per design (max SMB slope across bands)
    print("\n=== Per-design sweet-spot bands (max SMB slope) ===")
    sweet = {}
    all_results = pp_results + nc_results
    if all_results:
        df = pd.DataFrame(all_results)
        for design in df["design"].unique():
            sub = df[df.design == design].copy()
            best = sub.loc[sub["smb_slope"].idxmax()]
            print(f"  {design}: ctx={best['context']} band={best['band']} "
                  f"SMB slope={best['smb_slope']:+.4f} (n={best['n']})")
            sweet[design] = {"context": best["context"], "band": best["band"],
                             "smb_slope": float(best["smb_slope"]),
                             "n": int(best["n"])}

    out = {
        "scope": "BG-band sweep of SMB-channel velocity-coupling",
        "bands": [f"{lo}-{hi}" for lo, hi in BANDS],
        "n_pp_events": int(len(pp_ev)),
        "n_no_carb_events": int(len(nc_ev)),
        "pp_results": pp_results,
        "no_carb_results": nc_results,
        "per_design_sweet_spot": sweet,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2966] {OUT}")


if __name__ == "__main__":
    main()
