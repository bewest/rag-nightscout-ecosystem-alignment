"""EXP-2982 - Loop overshoot-governor counterfactual (patient i).

For patient `i`'s rising 70-100 SMB events, simulate
counterfactual outcomes when Loop's `partialApplicationFactor`
(PAF) is reduced.  Cap dose at fractions {1.0, 0.8, 0.6, 0.4, 0.2}
of observed SMB.  Project resulting BG trajectory using a
linear ISF * (delivered - counterfactual) correction added to
the observed post-event trajectory:

    bg_cf(t) = bg_obs(t) + ISF_per_U * (D_obs - D_cf) * activity(t)

where activity(t) is a triangular/Bateman approximation of
insulin-action (peak 75 min, DIA 360 min).  This is a
**rough** projection — it does not re-run the full Loop
simulator, only the marginal counterfactual relative to
observed.  Useful to bracket the trade-off curve.

Outputs per cap:
  * mean projected overshoot rate (>180 within 60 min)
  * mean projected delta-TTT (min vs observed)

Identifies the cap that minimizes projected overshoot while
keeping projected TTT within +5 min of observed.

Cite: externals/LoopWorkspace/LoopAlgorithm/ for PAF clamps
(applicationFactor / partialApplicationFactor in Loop's
recommendation logic).

Scope: AID-author audience.
What this is NOT: a full Loop simulator; not a clinical
recommendation; the linear projection ignores feedback
(IOB-aware cancellation, basal modulation, sensor noise).
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2982_summary.json"

PATIENT = "i"
BAND_LO, BAND_HI = 70.0, 100.0
PRE_NO_CARB = 24
VEL_WIN = 6
RISING_VEL = 0.5
HORIZON = 24            # 120 min
POST_WIN = 12           # 60 min
TARGET_BG = 100.0
TARGET_SUSTAIN = 6
OVERSHOOT_BG = 180.0

# ── Insulin action (Bateman / fiasp-ish) ─────────────────────────────────
PEAK_MIN = 75.0
DIA_MIN = 360.0
DT_MIN = 5.0
ISF_PER_U = 50.0  # mg/dL per U; conservative Loop adult default

CAPS = [1.0, 0.8, 0.6, 0.4, 0.2]


def insulin_activity(t_min: float) -> float:
    """Normalized insulin activity (∫=1 over [0,DIA])."""
    if t_min <= 0 or t_min >= DIA_MIN:
        return 0.0
    if t_min <= PEAK_MIN:
        return t_min / PEAK_MIN
    return max(0.0, 1.0 - (t_min - PEAK_MIN) / (DIA_MIN - PEAK_MIN))


def main():
    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb"]
    g = pd.read_parquet(GRID, columns=cols)
    sub = g[g.patient_id == PATIENT].dropna(subset=["glucose"]).sort_values("time").reset_index(drop=True)
    bg = sub["glucose"].values
    smb = sub["bolus_smb"].fillna(0).values
    carbs = sub["carbs"].fillna(0).values
    carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
    n = len(sub)

    # Pre-compute integrated activity at offsets 0..HORIZON*DT
    offsets = np.arange(HORIZON + 1) * DT_MIN
    integ_act = np.array([insulin_activity(t) for t in offsets]).cumsum()
    # Normalize to ∫_full = 1 over DIA
    full_offsets = np.arange(int(DIA_MIN / DT_MIN) + 1) * DT_MIN
    full_integ = np.array([insulin_activity(t) for t in full_offsets]).sum() * DT_MIN
    # cumulative fractional area at each offset:
    cum_frac = np.array([sum(insulin_activity(tt) for tt in np.arange(0, t + DT_MIN, DT_MIN))
                         * DT_MIN / full_integ for t in offsets])

    events = []
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
        vel = float(np.sum((xs - xm) * (ys_pre - ym)) / denom)
        if vel <= RISING_VEL:
            continue
        ys_post = bg[i:i + HORIZON + 1]
        if np.any(np.isnan(ys_post)):
            continue
        events.append({"D_obs": float(smb[i]), "ys_post": ys_post})

    print(f"Patient {PATIENT}: qualifying events = {len(events)}")
    if not events:
        OUT.write_text(json.dumps({"error": "no events"}, indent=2))
        return

    rows = []
    for cap in CAPS:
        os_count = 0
        ttt_obs_list = []
        ttt_cf_list = []
        n_cens_obs = 0
        n_cens_cf = 0
        for ev in events:
            D = ev["D_obs"]
            D_cf = D * cap
            delta_drop = ISF_PER_U * (D - D_cf) * cum_frac  # mg/dL added back to obs at each offset
            ys_cf = ev["ys_post"] + delta_drop  # cap < 1 => smaller dose => higher BG
            # TTT obs
            ttt_o = None
            for k in range(1, HORIZON - TARGET_SUSTAIN + 1):
                seg = ev["ys_post"][k:k + TARGET_SUSTAIN]
                if np.all(seg > TARGET_BG):
                    ttt_o = k * DT_MIN
                    break
            if ttt_o is None:
                n_cens_obs += 1
            else:
                ttt_obs_list.append(ttt_o)
            # TTT cf
            ttt_c = None
            for k in range(1, HORIZON - TARGET_SUSTAIN + 1):
                seg = ys_cf[k:k + TARGET_SUSTAIN]
                if np.all(seg > TARGET_BG):
                    ttt_c = k * DT_MIN
                    break
            if ttt_c is None:
                n_cens_cf += 1
            else:
                ttt_cf_list.append(ttt_c)
            # Overshoot in cf within 60 min
            post60 = ys_cf[1:1 + POST_WIN]
            if np.any(post60 > OVERSHOOT_BG):
                os_count += 1

        os_rate = os_count / len(events)
        ttt_obs_med = float(np.median(ttt_obs_list)) if ttt_obs_list else float("nan")
        ttt_cf_med = float(np.median(ttt_cf_list)) if ttt_cf_list else float("nan")
        delta_ttt = ttt_cf_med - ttt_obs_med if ttt_obs_list and ttt_cf_list else float("nan")
        rows.append({
            "cap_fraction": cap,
            "projected_overshoot_180_60min_rate": os_rate,
            "projected_ttt_median_min_obs": ttt_obs_med,
            "projected_ttt_median_min_cf": ttt_cf_med,
            "projected_delta_ttt_min": delta_ttt,
            "ttt_censor_rate_obs": n_cens_obs / len(events),
            "ttt_censor_rate_cf": n_cens_cf / len(events),
        })

    df = pd.DataFrame(rows)
    print("\n=== Counterfactual cap sweep (patient i, n_events="
          f"{len(events)}) ===")
    print(df.to_string(index=False))

    # Recommended cap: smallest projected_overshoot with delta_ttt <= 5 min
    valid = df[(df["projected_delta_ttt_min"] <= 5.0)]
    if len(valid):
        rec = valid.sort_values("projected_overshoot_180_60min_rate").iloc[0]
        print(f"\nRecommended cap (≤+5 min TTT): {rec['cap_fraction']:.2f} "
              f"projected_overshoot={rec['projected_overshoot_180_60min_rate']:.3f} "
              f"delta_ttt={rec['projected_delta_ttt_min']:.1f} min")
    else:
        print("\nNo cap satisfies ≤+5 min TTT constraint.")

    out = {
        "scope": "Counterfactual PAF cap sweep, patient i, rising 70-100",
        "params": {"PEAK_MIN": PEAK_MIN, "DIA_MIN": DIA_MIN,
                   "ISF_PER_U_mg_per_dl": ISF_PER_U},
        "n_events": len(events),
        "sweep": rows,
        "recommendation_note": "smallest cap with projected_delta_ttt_min ≤ 5 min",
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2982] {OUT}")


if __name__ == "__main__":
    main()
