"""EXP-2979 - Outcome linkage: Loop magnitude lever vs oref1 frequency lever.

The most clinically meaningful follow-up to the EXP-2972/2973
mechanism decomposition: do Loop's larger-but-fewer SMBs and
oref1's smaller-but-more-frequent SMBs produce DIFFERENT
post-event outcomes in the rising-stratum 70-100 sweet spot?

For each qualifying SMB-firing event (BG in [70,100), rising
velocity > 0.5 mg/dL/min, no-carb), measure:
  * time_to_target_min : minutes until BG > 100 sustained 30 min
  * overshoot_180     : 1 if BG exceeds 180 within 60 min
  * hypo_70           : 1 if BG drops below 70 within 60 min

Per-patient + pooled.  Compare Loop_AB_ON vs oref1.

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
OUT = REPO / "externals" / "experiments" / "exp-2979_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

BAND_LO, BAND_HI = 70.0, 100.0
PRE_NO_CARB = 24
VEL_WIN = 6
RISING_VEL = 0.5  # mg/dL/min
HORIZON = 24      # 120 min lookahead
TARGET_BG = 100.0
TARGET_SUSTAIN = 6  # 30 min sustained > 100
OVERSHOOT_BG = 180.0
HYPO_BG = 70.0
POST_WIN = 12  # 60 min for overshoot/hypo


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

    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(set(simp.patient_id))].dropna(subset=["glucose"])
    g = g.sort_values(["patient_id", "time"]).reset_index(drop=True)

    events = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d not in ("Loop_AB_ON", "oref1"):
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        n = len(sub)

        # Compute pre-window velocity at each i
        for i in range(VEL_WIN, n - HORIZON):
            if np.isnan(bg[i]) or smb[i] <= 0:
                continue
            if not (BAND_LO <= bg[i] < BAND_HI):
                continue
            if not (carbs_pre[i] == 0 and carbs[i] == 0):
                continue
            ys_pre = bg[i - VEL_WIN:i + 1]
            if np.any(np.isnan(ys_pre)):
                continue
            xs = np.arange(VEL_WIN + 1) * 5.0
            xm = xs.mean(); ym = ys_pre.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            vel_pre = float(np.sum((xs - xm) * (ys_pre - ym)) / denom)
            if vel_pre <= RISING_VEL:
                continue

            # Lookahead window
            ys_post = bg[i:i + HORIZON + 1]
            if np.any(np.isnan(ys_post)):
                continue

            # Time to target: first index k where bg[i+k..i+k+TARGET_SUSTAIN] all > TARGET_BG
            ttt = None
            for k in range(1, HORIZON - TARGET_SUSTAIN + 1):
                seg = bg[i + k:i + k + TARGET_SUSTAIN]
                if np.any(np.isnan(seg)):
                    break
                if np.all(seg > TARGET_BG):
                    ttt = k * 5.0
                    break

            # Overshoot/hypo within 60 min
            post60 = bg[i + 1:i + 1 + POST_WIN]
            overshoot = int(np.any(post60 > OVERSHOOT_BG))
            hypo = int(np.any(post60 < HYPO_BG))

            events.append({"patient_id": pid, "design": d,
                           "smb_dose_U": float(smb[i]),
                           "vel_pre": vel_pre,
                           "ttt_min": ttt if ttt is not None else float("nan"),
                           "ttt_censored": int(ttt is None),
                           "overshoot_180": overshoot,
                           "hypo_70": hypo})

    df = pd.DataFrame(events)
    print(f"Total qualifying SMB events: {len(df):,}")
    if not len(df):
        OUT.write_text(json.dumps({"error": "no events"}, indent=2))
        return

    print("\n=== Pooled per-design outcomes ===")
    pooled = []
    for d, sub in df.groupby("design"):
        n = len(sub)
        ttt_obs = sub.dropna(subset=["ttt_min"])["ttt_min"]
        cens = float(sub["ttt_censored"].mean())
        os_rate = float(sub["overshoot_180"].mean())
        hy_rate = float(sub["hypo_70"].mean())
        smb_med = float(sub["smb_dose_U"].median())
        print(f"  {d:>12} n={n:>5} smb_med={smb_med:.3f}U "
              f"ttt_med={ttt_obs.median():.0f}min(censor={cens:.2f}) "
              f"overshoot180_60min={os_rate:.3f} hypo70_60min={hy_rate:.3f}")
        pooled.append({"design": d, "n_events": n,
                       "smb_dose_median_U": smb_med,
                       "ttt_median_min": float(ttt_obs.median()) if len(ttt_obs) else float("nan"),
                       "ttt_mean_min": float(ttt_obs.mean()) if len(ttt_obs) else float("nan"),
                       "ttt_censor_rate": cens,
                       "overshoot_180_60min_rate": os_rate,
                       "hypo_70_60min_rate": hy_rate})

    print("\n=== Per-patient outcomes ===")
    # Also report event counts BEFORE threshold (transparency)
    counts_all = df.groupby(["patient_id", "design"]).size().reset_index(name="n_events_all")
    print("\n=== Event counts per patient (pre-threshold) ===")
    print(counts_all.to_string(index=False))

    pp_rows = []
    for (pid, d), sub in df.groupby(["patient_id", "design"]):
        n = len(sub)
        if n < 3:
            continue
        ttt_obs = sub.dropna(subset=["ttt_min"])["ttt_min"]
        pp_rows.append({"patient_id": pid, "design": d, "n_events": n,
                        "smb_dose_median_U": float(sub["smb_dose_U"].median()),
                        "ttt_median_min": float(ttt_obs.median()) if len(ttt_obs) else float("nan"),
                        "ttt_censor_rate": float(sub["ttt_censored"].mean()),
                        "overshoot_180_60min_rate": float(sub["overshoot_180"].mean()),
                        "hypo_70_60min_rate": float(sub["hypo_70"].mean())})
    pp = pd.DataFrame(pp_rows)
    if len(pp):
        print(pp.sort_values(["design", "patient_id"]).to_string(index=False))

    from scipy import stats
    print("\n=== MWU Loop_AB_ON vs oref1 (per-patient summary metrics) ===")
    mwu_out = {}
    for col in ["ttt_median_min", "overshoot_180_60min_rate", "hypo_70_60min_rate", "smb_dose_median_U"]:
        a = pp[pp.design == "Loop_AB_ON"][col].dropna().values
        b = pp[pp.design == "oref1"][col].dropna().values
        if len(a) >= 3 and len(b) >= 3:
            mw = stats.mannwhitneyu(a, b, alternative="two-sided")
            print(f"  {col:>30}: Loop n={len(a)} med={np.median(a):.3f} | "
                  f"oref1 n={len(b)} med={np.median(b):.3f} | U={mw.statistic:.1f} p={mw.pvalue:.4g}")
            mwu_out[col] = {"loop_n": len(a), "loop_median": float(np.median(a)),
                            "oref1_n": len(b), "oref1_median": float(np.median(b)),
                            "U": float(mw.statistic), "p_two_sided": float(mw.pvalue)}

    out = {
        "scope": "Outcome linkage: Loop magnitude vs oref1 frequency lever in 70-100 rising sweet spot",
        "filters": {"bg_band": [BAND_LO, BAND_HI], "rising_vel_min_mg_per_min": RISING_VEL,
                    "no_carb_min": PRE_NO_CARB * 5,
                    "target_sustain_min": TARGET_SUSTAIN * 5,
                    "overshoot_BG": OVERSHOOT_BG, "hypo_BG": HYPO_BG},
        "n_events_total": int(len(df)),
        "pooled": pooled,
        "per_patient": pp.to_dict(orient="records"),
        "mwu": mwu_out,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2979] {OUT}")


if __name__ == "__main__":
    main()
