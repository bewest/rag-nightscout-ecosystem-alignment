"""EXP-2977 - Per-patient implicit `partialApplicationFactor` calibration (Loop).

Loop sizes SMB as `insulinReq * partialApplicationFactor`, where
the factor is either Constant (default 0.4) or sliding via the
`GlucoseBasedApplicationFactorStrategy` (0.2-0.8 from BG 90-200).
See:
  * externals/LoopWorkspace/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift:101-110
    (asPartialBolus = correction * partialApplicationFactor)
  * externals/LoopWorkspace/Loop/Loop/Models/GlucoseBasedApplicationFactorStrategy.swift:14-42
    (sliding scale by current BG)
  * externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift:1818-1855
    (strategy selection)

We can't read the factor directly but can ESTIMATE the implicit
factor per Loop_AB_ON patient from observed SMB-event sizes:

  est_factor(i) = bolus_smb[i] / proxy_insulinReq(i)

where proxy_insulinReq(i) approximates Loop's correction request:

  proxy_insulinReq(i) ~= clip( max(bg[i] - target, 0) / ISF_proxy
                              + projected_velocity_correction, 0, cap)

Lacking per-patient ISF, we use a relative proxy: normalize SMB
size by the patient's median rising-event SMB.  The resulting
DISTRIBUTION shape is what matters: bimodal across patients
(some flat ~0.4, some sliding 0.2-0.8 spread) would indicate GBAF
on/off across patients; uniform clustering would indicate a single
strategy.

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
OUT = REPO / "externals" / "experiments" / "exp-2977_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

PRE_NO_CARB = 24
VEL_WIN = 6
RISING_VEL = 0.5
TARGET_BG = 110.0  # generic Loop default suspendThreshold-adjacent; rough
ISF_PROXY = 50.0   # mg/dL/U  -- normalization constant; cancels out in
                   # per-patient relative comparisons


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
        if d != "Loop_AB_ON":
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        n = len(sub)
        for i in range(VEL_WIN, n - 1):
            if np.isnan(bg[i]) or smb[i] <= 0:
                continue
            if not (carbs_pre[i] == 0 and carbs[i] == 0):
                continue
            if bg[i] <= TARGET_BG:
                continue
            ys = bg[i - VEL_WIN:i + 1]
            if np.any(np.isnan(ys)):
                continue
            xs = np.arange(VEL_WIN + 1) * 5.0
            xm = xs.mean(); ym = ys.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            vel_pre = float(np.sum((xs - xm) * (ys - ym)) / denom)
            if vel_pre < 0:
                continue  # only correction events
            # Proxy correction-only insulin requirement (U):
            # bg-target / ISF + 30-min projected delta / ISF
            proj_delta = vel_pre * 30.0  # mg/dL projected ahead 30min
            req = max(bg[i] - TARGET_BG, 0) / ISF_PROXY + proj_delta / ISF_PROXY
            if req <= 0.05:
                continue
            est_factor = smb[i] / req
            events.append({"patient_id": pid, "bg": float(bg[i]),
                           "vel_pre": vel_pre, "smb": float(smb[i]),
                           "req_proxy_U": req, "est_factor": est_factor})

    df = pd.DataFrame(events)
    print(f"Loop_AB_ON SMB events analyzed: {len(df):,}")
    if not len(df):
        OUT.write_text(json.dumps({"error": "no events"}, indent=2))
        return

    print("\n=== Per-patient implicit factor distribution ===")
    pp_rows = []
    for pid, sub in df.groupby("patient_id"):
        if len(sub) < 20:
            continue
        # Trim extremes from ISF mismatch
        f = sub["est_factor"].clip(0, 3.0)
        med = float(f.median())
        q25, q75 = float(f.quantile(0.25)), float(f.quantile(0.75))
        iqr = q75 - q25
        # Slope of factor vs bg -- positive => GBAF-like sliding
        from scipy import stats
        if sub["bg"].std() > 0:
            sl, _, _, p, _ = stats.linregress(sub["bg"], f)
        else:
            sl, p = float("nan"), float("nan")
        # Classify
        if abs(sl) < 1e-4 and iqr < 0.15:
            cls = "Constant-like (~flat, narrow)"
        elif sl > 0 and p < 0.05:
            cls = "GBAF-like (factor rises with BG)"
        else:
            cls = "Mixed/inconclusive"
        pp_rows.append({"patient_id": pid, "n_events": int(len(sub)),
                        "factor_median": med, "factor_q25": q25, "factor_q75": q75,
                        "factor_iqr": iqr,
                        "factor_vs_bg_slope": float(sl),
                        "factor_vs_bg_p": float(p),
                        "classification": cls})
    pp = pd.DataFrame(pp_rows)
    print(pp.to_string(index=False))

    out = {
        "scope": "Per-patient implicit partialApplicationFactor calibration (Loop_AB_ON)",
        "caveat": ("est_factor uses ISF_PROXY=50 mg/dL/U; per-patient ISF "
                   "would shift absolute level but not relative shape across BG."),
        "code_refs": [
            "externals/LoopWorkspace/LoopAlgorithm/Sources/LoopAlgorithm/Insulin/DoseMath.swift:101-110",
            "externals/LoopWorkspace/Loop/Loop/Models/GlucoseBasedApplicationFactorStrategy.swift:14-42",
            "externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift:1818-1855",
        ],
        "per_patient": pp.to_dict(orient="records"),
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2977] {OUT}")


if __name__ == "__main__":
    main()
