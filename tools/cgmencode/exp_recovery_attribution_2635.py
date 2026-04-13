#!/usr/bin/env python3
"""EXP-2635: Recovery Attribution via Natural Experiments

BUILDS ON:
  - EXP-2624: Nadir at ~3.5h, recovery slope ~16.8 mg/dL/hr
  - EXP-2627: 48h carb window optimal for metabolic state
  - EXP-2628: Autosens CV=8.8% vs per-window ISF CV=69.4%
  - EXP-2634: Model comparison (which model wins?)

QUESTION: Use natural variation in conditions to attribute recovery:
  - TIME OF DAY: If EGP, recovery should follow circadian rhythm (dawn effect)
  - IOB LEVEL: If IOB-decay, recovery rate should track dIOB/dt
  - 48h CARB LOAD: If glycogen matters, high-carb days should have faster recovery
  - CORRECTION SIZE: Does bolus magnitude predict recovery rate?

METHODOLOGY: EXACT EXP-2624 correction detection. Then stratify events by
conditions and compare recovery slopes within each stratum.

HYPOTHESES:
  H1: Overnight (0-6h) corrections recover SLOWER than daytime (8-20h)
      Rationale: If EGP circadian is real, dawn EGP boost (5AM peak) should
      accelerate overnight recovery. If NOT real, overnight should be slower
      (no meals, less counter-regulation).
  H2: Recovery rate correlates with IOB decay rate (r > 0.3)
      Rationale: If recovery = IOB wearing off, then faster IOB decay → faster
      glucose rise. Uses validated 6h DIA to compute dIOB/dt at nadir.
  H3: 48h carb load predicts recovery rate (r > 0.15)
      Rationale: 48h carb window is validated as metabolic state proxy.
      Higher glycogen stores → more substrate for EGP → faster recovery.
  H4: Bolus size does NOT predict recovery rate (|r| < 0.15)
      Rationale: If recovery is physiological (EGP/mean-reversion), it shouldn't
      depend on bolus size. If it DOES, that implies insulin-dependent mechanism.
"""
import json, os, sys
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as sp_stats

ROOT = Path(__file__).resolve().parents[2]
PARQUET = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
OUT = ROOT / "externals" / "experiments" / "exp-2635_recovery_attribution.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

STEPS_PER_HOUR = 12
MIN_BOLUS_U = 0.5
MAX_CARBS_WINDOW_G = 2.0
PRE_WINDOW_STEPS = 6
POST_WINDOW_STEPS = 72
NADIR_SEARCH_STEPS = 48
RECOVERY_FIT_STEPS = 24
MIN_DROP_MGDL = 10
STACKING_WINDOW = 24  # 2h — filters SMBs

# Validated DIA model
DIA_MIN = 360
PEAK_MIN = 75


def _exponential_iob(t_min, dia=DIA_MIN, peak=PEAK_MIN):
    """Fraction of insulin remaining at time t."""
    if t_min <= 0:
        return 1.0
    if t_min >= dia:
        return 0.0
    tau = peak * (1 - peak / dia) / (1 - 2 * peak / dia)
    a = 2 * tau / dia
    S = 1 / (1 - a + (1 + a) * np.exp(-dia / tau))
    iob_frac = 1 - S * (1 - a) * (
        (t_min**2 / (tau * dia * (1 - a)) - t_min / tau - 1) * np.exp(-t_min / tau) + 1
    )
    return max(0, min(1, iob_frac))


def _compute_48h_carbs(pdf, idx):
    """Sum carbs in 48h window before index (validated EXP-2627)."""
    carbs = pdf["carbs"].fillna(0).values
    # 48h = 576 steps
    window_start = max(0, idx - 576)
    return float(np.nansum(carbs[window_start:idx]))


def _compute_iob_decay_rate(bolus_u, nadir_idx):
    """dIOB/dt at nadir (U/hr), using validated 6h DIA."""
    t_nadir = nadir_idx * 5  # minutes from bolus
    dt = 5  # minutes
    iob_before = bolus_u * _exponential_iob(t_nadir - dt)
    iob_after = bolus_u * _exponential_iob(t_nadir + dt)
    decay_rate = (iob_before - iob_after) / (2 * dt / 60)  # U/hr
    return float(decay_rate)


def _extract_corrections(pdf):
    """EXACT EXP-2624 methodology — see EXP-2634 for details."""
    glucose = pdf["glucose"].values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    times = pd.to_datetime(pdf["time"])
    n = len(glucose)
    events = []

    for i in range(PRE_WINDOW_STEPS, n - POST_WINDOW_STEPS):
        if bolus[i] < MIN_BOLUS_U:
            continue
        carb_window = carbs[max(0, i - 12):min(n, i + 12)]
        if np.nansum(carb_window) > MAX_CARBS_WINDOW_G:
            continue
        prior_bolus = bolus[max(0, i - STACKING_WINDOW):i]
        if np.nansum(prior_bolus) > 0.1:
            continue

        pre_window = glucose[i - PRE_WINDOW_STEPS:i]
        valid_pre = ~np.isnan(pre_window)
        if valid_pre.sum() < 3:
            continue
        pre_bg = float(np.nanmean(pre_window))
        if pre_bg < 120:
            continue

        post = glucose[i:i + POST_WINDOW_STEPS].copy()
        valid_post = ~np.isnan(post)
        if valid_post.sum() < POST_WINDOW_STEPS // 2:
            continue

        smoothed = pd.Series(post).rolling(3, center=True, min_periods=1).mean().values
        nadir_search = smoothed[:NADIR_SEARCH_STEPS]
        if (~np.isnan(nadir_search)).sum() < 6:
            continue
        nadir_idx = int(np.nanargmin(nadir_search))
        nadir_bg = float(nadir_search[nadir_idx])
        drop = pre_bg - nadir_bg
        if drop < MIN_DROP_MGDL:
            continue

        # Recovery slope
        rec_start = nadir_idx
        rec_end = min(nadir_idx + RECOVERY_FIT_STEPS, len(post))
        recovery = post[rec_start:rec_end]
        valid_rec = ~np.isnan(recovery)
        if valid_rec.sum() < 6:
            continue
        x_rec = np.arange(valid_rec.sum()) * 5 / 60
        y_rec = recovery[valid_rec]
        slope, intercept, r, p, se = sp_stats.linregress(x_rec, y_rec)

        hour_of_day = float(times.iloc[i].hour + times.iloc[i].minute / 60)
        carbs_48h = _compute_48h_carbs(pdf, i)
        iob_decay_rate = _compute_iob_decay_rate(bolus[i], nadir_idx)

        events.append({
            "index": i,
            "hour_of_day": hour_of_day,
            "pre_bg": pre_bg,
            "nadir_bg": nadir_bg,
            "nadir_hours": nadir_idx * 5 / 60,
            "drop_mgdl": drop,
            "bolus_u": float(bolus[i]),
            "iob_at_bolus": float(iob[i]),
            "recovery_slope": float(slope),  # mg/dL/hr
            "recovery_r2": float(r**2),
            "carbs_48h": carbs_48h,
            "iob_decay_rate": iob_decay_rate,
            "is_overnight": 0 <= hour_of_day < 6 or hour_of_day >= 22,
            "is_daytime": 8 <= hour_of_day < 20,
        })

    return events


def run():
    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values(["patient_id", "time"]).reset_index(drop=True)

    all_events = []
    per_patient = {}

    for pid in FULL_PATIENTS:
        dp = df[df["patient_id"] == pid].copy().reset_index(drop=True)
        if len(dp) == 0:
            continue
        events = _extract_corrections(dp)
        for ev in events:
            ev["patient_id"] = pid
        all_events.extend(events)
        days = max(1, (dp["time"].max() - dp["time"].min()).days)
        per_patient[pid] = {
            "n_events": len(events),
            "events_per_day": len(events) / days,
            "mean_recovery": float(np.mean([e["recovery_slope"] for e in events])) if events else np.nan,
        }
        print(f"  Patient {pid}: {len(events)} corrections ({len(events)/days:.1f}/day), "
              f"recovery = {per_patient[pid]['mean_recovery']:.1f} mg/dL/hr")

    print(f"\nTotal: {len(all_events)} corrections")

    # === Attribution Analysis ===
    print("\n=== HYPOTHESIS TESTS ===\n")

    # H1: Overnight vs daytime recovery
    overnight = [e["recovery_slope"] for e in all_events if e["is_overnight"]]
    daytime = [e["recovery_slope"] for e in all_events if e["is_daytime"]]
    if len(overnight) >= 5 and len(daytime) >= 5:
        t_stat, p_val = sp_stats.ttest_ind(overnight, daytime)
        h1_pass = np.mean(overnight) < np.mean(daytime)  # overnight SLOWER
        print(f"H1: Overnight vs daytime recovery")
        print(f"    Overnight: {np.mean(overnight):.1f} ± {np.std(overnight):.1f} mg/dL/hr (n={len(overnight)})")
        print(f"    Daytime:   {np.mean(daytime):.1f} ± {np.std(daytime):.1f} mg/dL/hr (n={len(daytime)})")
        print(f"    t = {t_stat:.2f}, p = {p_val:.4f}")
        print(f"    → {'PASS' if h1_pass else 'FAIL'} (overnight {'slower' if h1_pass else 'faster'})")
    else:
        h1_pass = False
        t_stat, p_val = np.nan, np.nan
        print(f"H1: Insufficient data (overnight={len(overnight)}, daytime={len(daytime)})")

    # H2: Recovery rate vs IOB decay rate
    decay_rates = [e["iob_decay_rate"] for e in all_events if not np.isnan(e["iob_decay_rate"])]
    rec_slopes = [e["recovery_slope"] for e in all_events if not np.isnan(e["iob_decay_rate"])]
    if len(decay_rates) >= 10:
        r_iob, p_iob = sp_stats.pearsonr(decay_rates, rec_slopes)
        h2_pass = r_iob > 0.3
        print(f"\nH2: Recovery rate vs IOB decay rate")
        print(f"    r = {r_iob:.3f}, p = {p_iob:.4f}, n = {len(decay_rates)}")
        print(f"    → {'PASS' if h2_pass else 'FAIL'}")
    else:
        r_iob, p_iob = np.nan, np.nan
        h2_pass = False

    # H3: 48h carb load vs recovery rate
    carbs_48 = [e["carbs_48h"] for e in all_events if not np.isnan(e["carbs_48h"])]
    rec_for_carbs = [e["recovery_slope"] for e in all_events if not np.isnan(e["carbs_48h"])]
    if len(carbs_48) >= 10:
        r_carb, p_carb = sp_stats.pearsonr(carbs_48, rec_for_carbs)
        h3_pass = r_carb > 0.15
        print(f"\nH3: 48h carb load vs recovery rate")
        print(f"    r = {r_carb:.3f}, p = {p_carb:.4f}, n = {len(carbs_48)}")
        print(f"    Mean 48h carbs = {np.mean(carbs_48):.0f}g")
        print(f"    → {'PASS' if h3_pass else 'FAIL'}")
    else:
        r_carb, p_carb = np.nan, np.nan
        h3_pass = False

    # H4: Bolus size does NOT predict recovery (|r| < 0.15)
    boluses = [e["bolus_u"] for e in all_events]
    rec_all = [e["recovery_slope"] for e in all_events]
    if len(boluses) >= 10:
        r_bolus, p_bolus = sp_stats.pearsonr(boluses, rec_all)
        h4_pass = abs(r_bolus) < 0.15
        print(f"\nH4: Bolus size vs recovery rate")
        print(f"    r = {r_bolus:.3f}, p = {p_bolus:.4f}, n = {len(boluses)}")
        print(f"    → {'PASS' if h4_pass else 'FAIL'} (|r| {'<' if h4_pass else '≥'} 0.15)")
    else:
        r_bolus, p_bolus = np.nan, np.nan
        h4_pass = False

    # === Time-of-day breakdown ===
    print("\n=== RECOVERY BY TIME OF DAY ===")
    for label, hours in [("Night 0-6", (0, 6)), ("Morning 6-10", (6, 10)),
                          ("Midday 10-14", (10, 14)), ("Afternoon 14-18", (14, 18)),
                          ("Evening 18-22", (18, 22)), ("Late 22-24", (22, 24))]:
        subset = [e["recovery_slope"] for e in all_events
                  if hours[0] <= e["hour_of_day"] < hours[1]]
        if subset:
            print(f"  {label}: {np.mean(subset):.1f} ± {np.std(subset):.1f} mg/dL/hr (n={len(subset)})")

    summary = {
        "experiment": "EXP-2635",
        "title": "Recovery Attribution via Natural Experiments",
        "methodology": "EXP-2624 exact + 48h carb context + IOB decay rate",
        "n_events": len(all_events),
        "n_patients": sum(1 for v in per_patient.values() if v["n_events"] > 0),
        "validated_priors": {
            "DIA": "6h (EXP-2541)", "48h_carbs": "optimal (EXP-2627)",
            "nadir": "~3.5h (EXP-2624)", "autosens_cv": "8.8% (EXP-2628)",
        },
        "hypotheses": {
            "H1": {
                "statement": "Overnight recovery slower than daytime",
                "result": "PASS" if h1_pass else "FAIL",
                "overnight_mean": float(np.mean(overnight)) if overnight else None,
                "daytime_mean": float(np.mean(daytime)) if daytime else None,
                "p_value": float(p_val) if not np.isnan(p_val) else None,
            },
            "H2": {
                "statement": "Recovery correlates with IOB decay rate (r > 0.3)",
                "result": "PASS" if h2_pass else "FAIL",
                "r": float(r_iob) if not np.isnan(r_iob) else None,
                "p_value": float(p_iob) if not np.isnan(p_iob) else None,
            },
            "H3": {
                "statement": "48h carb load predicts recovery (r > 0.15)",
                "result": "PASS" if h3_pass else "FAIL",
                "r": float(r_carb) if not np.isnan(r_carb) else None,
                "p_value": float(p_carb) if not np.isnan(p_carb) else None,
            },
            "H4": {
                "statement": "Bolus size does NOT predict recovery (|r| < 0.15)",
                "result": "PASS" if h4_pass else "FAIL",
                "r": float(r_bolus) if not np.isnan(r_bolus) else None,
                "p_value": float(p_bolus) if not np.isnan(p_bolus) else None,
            },
        },
        "per_patient": per_patient,
    }

    os.makedirs(OUT.parent, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nResults → {OUT}")


if __name__ == "__main__":
    run()
