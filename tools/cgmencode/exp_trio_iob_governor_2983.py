"""EXP-2983 - Trio IOB-stacking governor: hypo vs mean IOB at SMB emission.

Within Trio cohort (lineage='oref1 (modern)'), per-patient regression:
  hypo_rate ~ mean_IOB_at_emission

For each Trio patient compute:
  * mean IOB at the moment of SMB emission (no-carb, all bands)
  * 60-min hypo (<70) rate post-emission
Then visualize/regress across patients (Spearman) to identify
an "IOB ceiling" above which hypo rate jumps.

Cite: externals/Trio/ for `maxIOB` setting and `enableSMB_always`
policy that govern IOB stacking.

Scope: AID-author audience (IOB-ceiling guidance).
What this is NOT: a per-patient maxIOB recommendation; not a
clinical safety study (n_patients ≈ 9, observational).
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
SIMP = REPO / "externals" / "experiments" / "exp-2891_simpson_dose_response.parquet"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = REPO / "externals" / "experiments" / "exp-2983_summary.json"

PRE_NO_CARB = 24
POST_WIN = 12  # 60 min
HYPO_BG = 70.0


def main():
    simp = pd.read_parquet(SIMP, columns=["patient_id", "lineage"]).drop_duplicates("patient_id")
    trio_pats = set(simp[simp.lineage == "oref1 (modern)"].patient_id)

    cols = ["patient_id", "time", "glucose", "carbs", "bolus_smb", "iob"]
    g = pd.read_parquet(GRID, columns=cols)
    g = g[g.patient_id.isin(trio_pats)].dropna(subset=["glucose"])

    rows = []
    events_per_patient = {}
    for pid, sub in g.groupby("patient_id"):
        sub = sub.sort_values("time").reset_index(drop=True)
        bg = sub["glucose"].values
        smb = sub["bolus_smb"].fillna(0).values
        iob = sub["iob"].fillna(0).values
        carbs = sub["carbs"].fillna(0).values
        carbs_pre = sub["carbs"].fillna(0).shift(1).rolling(PRE_NO_CARB, min_periods=1).sum().fillna(0).values
        n = len(sub)
        ev_iob = []
        ev_hypo = []
        for i in range(0, n - POST_WIN):
            if np.isnan(bg[i]) or smb[i] <= 0:
                continue
            if not (carbs_pre[i] == 0 and carbs[i] == 0):
                continue
            post60 = bg[i + 1:i + 1 + POST_WIN]
            if np.any(np.isnan(post60)):
                continue
            ev_iob.append(float(iob[i]))
            ev_hypo.append(int(np.any(post60 < HYPO_BG)))
        if len(ev_iob) < 20:
            continue
        ev_iob = np.array(ev_iob); ev_hypo = np.array(ev_hypo)
        rows.append({
            "patient_id": pid,
            "n_events": int(len(ev_iob)),
            "mean_iob_U": float(ev_iob.mean()),
            "median_iob_U": float(np.median(ev_iob)),
            "p75_iob_U": float(np.percentile(ev_iob, 75)),
            "hypo_rate": float(ev_hypo.mean()),
        })
        events_per_patient[pid] = (ev_iob, ev_hypo)

    df = pd.DataFrame(rows).sort_values("mean_iob_U")
    print("=== Trio per-patient IOB-at-emission vs 60-min hypo rate ===")
    print(df.to_string(index=False))

    # Spearman across patients
    from scipy import stats
    if len(df) >= 4:
        sp = stats.spearmanr(df["mean_iob_U"], df["hypo_rate"])
        print(f"\nSpearman ρ(mean_iob, hypo_rate) = {sp.statistic:.3f} p={sp.pvalue:.3g}")
        sp_p75 = stats.spearmanr(df["p75_iob_U"], df["hypo_rate"])
        print(f"Spearman ρ(p75_iob,  hypo_rate) = {sp_p75.statistic:.3f} p={sp_p75.pvalue:.3g}")
    else:
        sp = sp_p75 = None

    # Pooled within-patient: bin events by IOB tertile, hypo rate per bin
    pool_rows = []
    for pid, (ev_iob, ev_hypo) in events_per_patient.items():
        try:
            q = np.quantile(ev_iob, [0.33, 0.67])
            bins = np.digitize(ev_iob, q)
            for b in (0, 1, 2):
                m = bins == b
                if m.sum() < 5:
                    continue
                pool_rows.append({
                    "patient_id": pid, "iob_tertile": int(b),
                    "n": int(m.sum()),
                    "mean_iob_U_bin": float(ev_iob[m].mean()),
                    "hypo_rate_bin": float(ev_hypo[m].mean()),
                })
        except Exception:
            continue
    pool = pd.DataFrame(pool_rows)
    print("\n=== Per-patient × IOB-tertile hypo rate (within-patient) ===")
    print(pool.to_string(index=False))

    # Cross-patient binned: pool all events into IOB bins
    all_iob = np.concatenate([ev_iob for ev_iob, _ in events_per_patient.values()]) if events_per_patient else np.array([])
    all_hypo = np.concatenate([ev_hypo for _, ev_hypo in events_per_patient.values()]) if events_per_patient else np.array([])
    band_rows = []
    if len(all_iob):
        edges = np.array([0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0])
        for lo, hi in zip(edges[:-1], edges[1:]):
            m = (all_iob >= lo) & (all_iob < hi)
            if m.sum() < 20:
                continue
            band_rows.append({
                "iob_lo": float(lo), "iob_hi": float(hi),
                "n_events": int(m.sum()),
                "hypo_rate": float(all_hypo[m].mean()),
            })
        bdf = pd.DataFrame(band_rows)
        print("\n=== Pooled across-Trio: hypo rate by IOB-at-emission band ===")
        print(bdf.to_string(index=False))

    out = {
        "scope": "Trio IOB-stacking governor",
        "per_patient": df.to_dict(orient="records"),
        "spearman_mean_iob_vs_hypo": {"rho": float(sp.statistic), "p": float(sp.pvalue)} if sp else None,
        "spearman_p75_iob_vs_hypo": {"rho": float(sp_p75.statistic), "p": float(sp_p75.pvalue)} if sp_p75 else None,
        "within_patient_iob_tertile": pool.to_dict(orient="records"),
        "pooled_iob_band": band_rows,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2983] {OUT}")


if __name__ == "__main__":
    main()
