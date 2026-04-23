"""EXP-2937 - Sustained-high recovery mechanism decomposition.

EXP-2934 established that within high_lag (BG was >154 mg/dL 1h ago),
oref1 holds 64.26 % TIR vs Loop_AB_ON 46.60 % vs Loop_AB_OFF 34.45 %.
This is the recovery mechanism — what does the controller DO during
sustained-high windows that produces the gap?

For each design, find sustained-high entries (BG crossing >180 from
below, with the prior 30 min <180), then characterise the next 60 min:
- Total insulin delivered (SMB + basal sum)
- SMB count, mean SMB size
- First-SMB latency
- Rate of decline (mg/dL/min)
- Probability of returning to <180 within 60 min

This isolates the *correction loop* behaviour from meal/PP context.

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
OUT = REPO / "externals" / "experiments" / "exp-2937_summary.json"

RNG = np.random.default_rng(2937)
N_BOOT = 2000
HIGH = 180.0
WINDOW_MIN = 60
PRE_QUIET_MIN = 30
CARB_GUARD_MIN = 60  # exclude entries within 60 min of carbs to isolate correction-only

LOOP_AB_OFF = {"a", "f"}
LOOP_AB_ON = {"c", "d", "e", "g", "i"}


def find_entries(group: pd.DataFrame) -> pd.DataFrame:
    """Cross-from-below into >180, with prior 30 min <180 and no carbs in last 60 min."""
    g = group.sort_values("time").reset_index(drop=True).copy()
    g["bg_prev"] = g["glucose"].shift(1)
    g["bg_max_30"] = g["glucose"].shift(1).rolling(window=PRE_QUIET_MIN // 5, min_periods=1).max()
    g["carbs_60"] = g["carbs"].shift(1).rolling(window=CARB_GUARD_MIN // 5, min_periods=1).sum()
    crossings = g[
        (g["glucose"] > HIGH)
        & (g["bg_prev"] <= HIGH)
        & (g["bg_max_30"] <= HIGH)
        & (g["carbs_60"].fillna(0) == 0)
    ].copy()
    return crossings


def characterise(group: pd.DataFrame, entries: pd.DataFrame) -> list[dict]:
    g = group.sort_values("time").reset_index(drop=True)
    g_idx = pd.Series(g.index, index=g["time"])
    out = []
    n_cells = WINDOW_MIN // 5
    for _, ent in entries.iterrows():
        i0 = g_idx.get(ent["time"])
        if i0 is None:
            continue
        win = g.iloc[i0:i0 + n_cells]
        if len(win) < n_cells:
            continue
        # Carbs in window? exclude (don't conflate meal handling)
        if win["carbs"].fillna(0).sum() > 0:
            continue
        smb = win["bolus_smb"].fillna(0).values
        smb_count = int((smb > 0).sum())
        smb_total = float(smb.sum())
        smb_first_idx = int(np.argmax(smb > 0)) if smb_count > 0 else -1
        first_latency = (smb_first_idx * 5) if smb_count > 0 else np.nan
        bg = win["glucose"].values
        bg_end = float(bg[-1])
        decline = float((bg[0] - bg_end) / WINDOW_MIN)  # mg/dL/min
        recovered = bool(bg_end < HIGH)
        out.append({
            "smb_count": smb_count,
            "smb_total_u": smb_total,
            "smb_mean_u": smb_total / smb_count if smb_count else np.nan,
            "first_smb_latency_min": first_latency,
            "bg_start": float(bg[0]),
            "bg_end": bg_end,
            "decline_rate_mgdl_per_min": decline,
            "recovered": recovered,
        })
    return out


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

    rows = []
    for pid, sub in g.groupby("patient_id"):
        d = design_of(pid, pid_to_lineage[pid])
        if d is None:
            continue
        ents = find_entries(sub)
        chars = characterise(sub, ents)
        for c in chars:
            c["patient_id"] = pid
            c["design"] = d
            rows.append(c)

    if not rows:
        print("No correction events found.")
        return
    ev = pd.DataFrame(rows)
    print(f"Total isolated sustained-high entries: {len(ev):,}")
    print(f"By design:")
    print(ev.groupby("design").size())

    # Per-design summary (per-patient first to avoid event-count weighting)
    per_pat = ev.groupby(["patient_id", "design"]).agg(
        n_events=("smb_count", "size"),
        smb_count=("smb_count", "mean"),
        smb_total=("smb_total_u", "mean"),
        smb_mean=("smb_mean_u", "mean"),
        first_lat=("first_smb_latency_min", "mean"),
        decline=("decline_rate_mgdl_per_min", "mean"),
        recovered=("recovered", "mean"),
    ).reset_index()
    per_pat = per_pat[per_pat["n_events"] >= 5]  # need enough events per patient
    print(f"\nPatients with >=5 events: {len(per_pat)}")

    print("\n=== Per-patient mean per design ===")
    summary = per_pat.groupby("design").agg(
        n_pat=("patient_id", "nunique"),
        events_per_pat=("n_events", "mean"),
        smb_count=("smb_count", "mean"),
        smb_total_u=("smb_total", "mean"),
        smb_mean_u=("smb_mean", "mean"),
        first_lat_min=("first_lat", "mean"),
        decline_mgdl_min=("decline", "mean"),
        recovered_pct=("recovered", lambda s: float(s.mean()) * 100),
    ).round(2)
    print(summary.to_string())

    # Bootstrap CIs on key contrasts
    def boot_diff(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
        if len(a) < 2 or len(b) < 2:
            return float("nan"), float("nan"), float("nan")
        ba = RNG.choice(a, (N_BOOT, len(a)), replace=True).mean(axis=1)
        bb = RNG.choice(b, (N_BOOT, len(b)), replace=True).mean(axis=1)
        d = ba - bb
        return float(a.mean() - b.mean()), float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))

    print("\n=== Bootstrap contrasts (oref1 - design) ===")
    contrasts = []
    for metric in ["smb_count", "smb_total", "first_lat", "decline", "recovered"]:
        oref_v = per_pat[per_pat.design == "oref1"][metric].dropna().values
        for d in ["Loop_AB_ON", "Loop_AB_OFF"]:
            cmp_v = per_pat[per_pat.design == d][metric].dropna().values
            if len(cmp_v) == 0:
                continue
            diff, lo, hi = boot_diff(oref_v, cmp_v)
            sig = "*" if (lo > 0 or hi < 0) else " "
            print(f"  {metric:12s} oref1 - {d:12s}: {diff:+8.3f}  CI[{lo:+.3f}, {hi:+.3f}] {sig}")
            contrasts.append({"metric": metric, "vs": d, "diff": diff, "ci_lo": lo, "ci_hi": hi,
                              "n_oref1": int(len(oref_v)), "n_design": int(len(cmp_v))})

    out = {
        "scope": "Sustained-high correction-only recovery mechanism by design (EXP-2934 follow-up)",
        "n_events_total": int(len(ev)),
        "events_by_design": ev.groupby("design").size().to_dict(),
        "summary": summary.reset_index().to_dict(orient="records"),
        "contrasts": contrasts,
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[exp-2937] {OUT}")


if __name__ == "__main__":
    main()
