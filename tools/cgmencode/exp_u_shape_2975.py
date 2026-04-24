"""EXP-2975 - Formal U-shape test of SMB-slope vs BG band.

EXP-2966 hinted at a U-shape: SMB-on-velocity slope minimum near
target (100-140 mg/dL), higher at low-target and at very-high
edges. Formally test by:
  1. Fitting per-(BG-band) SMB slope at the cell level (no-carb).
  2. Regressing those band slopes on band-midpoint with a quadratic:
     slope ~ a + b * BG + c * BG^2
  3. Reporting `c` with 95% CI; `c > 0` is the U-shape signature.
Per design (Loop_AB_ON, oref1).

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
OUT = REPO / "externals" / "experiments" / "exp-2975_summary.json"

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}
OREF0_PATS = {"odc-74077367", "odc-86025410", "odc-96254963"}

BANDS = [(70, 100), (100, 140), (140, 180), (180, 220), (220, 260), (260, 300)]
PRE_NO_CARB = 24
VEL_WIN = 6
INS_WIN = 12


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

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lin.get(pid, ""))
        if d is None:
            continue
        sub = sub.sort_values("time").reset_index(drop=True)
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        n = len(sub)
        for i in range(0, n - INS_WIN):
            if np.isnan(bg[i]):
                continue
            if not (carbs_pre[i] == 0 and carbs[i] == 0):
                continue
            j = i + VEL_WIN
            ys = bg[i:j + 1]
            if np.any(np.isnan(ys)):
                continue
            xs = np.arange(VEL_WIN + 1) * 5.0
            xm = xs.mean(); ym = ys.mean()
            denom = float(np.sum((xs - xm) ** 2))
            if denom <= 0:
                continue
            vel = float(np.sum((xs - xm) * (ys - ym)) / denom)
            rows.append({"design": d, "bg_entry": float(bg[i]), "vel_30": vel,
                         "ins_60_smb": float(smb[i:i + INS_WIN].sum())})

    ev = pd.DataFrame(rows)
    print(f"Total no-carb windows: {len(ev):,}")

    def assign_band(bg):
        for lo, hi in BANDS:
            if lo <= bg < hi:
                return (lo + hi) / 2.0
        return None

    ev["band_mid"] = ev["bg_entry"].apply(assign_band)
    ev = ev.dropna(subset=["band_mid"])

    from scipy import stats

    band_rows = []
    for d in ["Loop_AB_ON", "oref1", "Loop_AB_OFF", "oref0"]:
        for lo, hi in BANDS:
            mid = (lo + hi) / 2.0
            sub = ev[(ev.design == d) & (ev.band_mid == mid)]
            if len(sub) < 30:
                continue
            sl, _, _, p, se = stats.linregress(sub["vel_30"], sub["ins_60_smb"])
            band_rows.append({"design": d, "band_mid": mid,
                              "n": int(len(sub)),
                              "smb_slope": float(sl),
                              "smb_slope_se": float(se),
                              "smb_slope_p": float(p)})
    bdf = pd.DataFrame(band_rows)
    print("\n=== Per-band SMB slopes (no-carb) ===")
    print(bdf.to_string(index=False))

    print("\n=== Quadratic U-shape fit: slope ~ a + b*bg + c*bg^2 ===")
    quad = []
    for d in ["Loop_AB_ON", "oref1"]:
        sub = bdf[bdf.design == d]
        if len(sub) < 4:
            continue
        x = sub["band_mid"].values.astype(float)
        y = sub["smb_slope"].values.astype(float)
        # OLS with x, x^2 design matrix; weights = 1 / SE^2
        w = 1.0 / np.maximum(sub["smb_slope_se"].values.astype(float) ** 2, 1e-12)
        X = np.column_stack([np.ones_like(x), x, x * x])
        W = np.diag(w)
        XtWX = X.T @ W @ X
        XtWy = X.T @ W @ y
        beta = np.linalg.solve(XtWX, XtWy)
        cov = np.linalg.inv(XtWX)
        se = np.sqrt(np.diag(cov))
        a, b, c = beta
        a_se, b_se, c_se = se
        # U-shape vertex (minimum) at -b/(2c)
        vertex = -b / (2 * c) if c != 0 else float("nan")
        z = c / c_se if c_se > 0 else float("nan")
        # 2-sided p-value from normal approx
        from math import erf, sqrt
        p_c = 2 * (1 - 0.5 * (1 + erf(abs(z) / np.sqrt(2)))) if np.isfinite(z) else float("nan")
        print(f"  {d}: c={c:+.6e} +/- {c_se:.2e}  z={z:+.2f}  p={p_c:.3g}  "
              f"vertex_BG={vertex:.1f} mg/dL  (b={b:+.4e}, a={a:+.4f})")
        quad.append({"design": d,
                     "a": float(a), "a_se": float(a_se),
                     "b": float(b), "b_se": float(b_se),
                     "c": float(c), "c_se": float(c_se),
                     "c_z": float(z), "c_p_two_sided": float(p_c),
                     "vertex_BG": float(vertex)})

    out = {
        "scope": "Quadratic U-shape test of SMB-slope vs BG band (no-carb)",
        "bands": [(lo, hi) for lo, hi in BANDS],
        "per_band_slopes": band_rows,
        "quadratic_fit": quad,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2975] {OUT}")


if __name__ == "__main__":
    main()
