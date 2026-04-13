#!/usr/bin/env python3
"""EXP-2653: Nyquist-Aware Multi-Scale Supply/Demand Balance.

MOTIVATION (Nyquist compliance):
  Insulin demand has DIA ≈ 6h → Nyquist minimum lookback = 12h
  Metabolic supply (EGP/glycogen) drifts over 48-72h → Nyquist min = 96-144h
  Our prior experiments used 4h blocks — sub-Nyquist for BOTH signals.

  EXP-2627 confirmed 48h ≈ 72h for carb windows, but that was tested in
  isolation. EXP-2628 found IOB@midnight 1.8× better than 48h carbs, but
  tested separately. Neither used Nyquist-correct windows for the signal
  it was measuring.

METHOD:
  For each patient-night, compute features at Nyquist-correct timescales:

  DEMAND side (insulin, fast):
    - iob_now:         IOB at observation start (instantaneous state)
    - insulin_6h:      total insulin delivered in prior 6h (1 DIA)
    - insulin_12h:     total insulin delivered in prior 12h (2× DIA, Nyquist)
    - basal_actual_6h: mean actual basal rate, prior 6h

  SUPPLY side (metabolic, slow):
    - carbs_24h:       total carbs in prior 24h (1 circadian cycle)
    - carbs_48h:       total carbs in prior 48h (Nyquist for metabolic drift)
    - carbs_96h:       total carbs in prior 96h (Nyquist for glycogen cycle)
    - net_energy_48h:  carbs_48h - (insulin_48h × CR) → energy balance proxy

  OBSERVATION: overnight drift over 8h window (00-08h)
    - 8h window captures ≥1 full DIA tail (Nyquist-compliant for insulin)
    - Drift measured as linear slope of glucose over 8h

HYPOTHESES:
  H1: Multi-scale model (demand + supply features) explains ≥25% of drift
      variance (vs ≤17% for IOB@midnight alone in EXP-2628)
  H2: Supply features add ≥5% incremental R² beyond demand features alone
  H3: The 48h metabolic lookback adds more than the 96h lookback
      (consistent with EXP-2627 showing 48h ≈ 72h)
  H4: Net energy balance (carbs - insulin×CR) is a better supply predictor
      than raw carbs (because it captures the metabolic BALANCE)
  H5: Per-patient optimal demand/supply weighting varies ≥2× across patients
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2653_nyquist_multiscale.json"

NS_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
ODC_FULL = ["odc-74077367", "odc-86025410", "odc-96254963"]
ALL_PATIENTS = NS_PATIENTS + ODC_FULL
STEPS_PER_HOUR = 12


def _compute_lookback(arr, idx, hours):
    """Sum values in the lookback window [idx - hours*SPH, idx)."""
    n_steps = int(hours * STEPS_PER_HOUR)
    start = max(0, idx - n_steps)
    window = arr[start:idx]
    return float(np.nansum(window))


def _compute_mean_lookback(arr, idx, hours):
    """Mean of values in the lookback window."""
    n_steps = int(hours * STEPS_PER_HOUR)
    start = max(0, idx - n_steps)
    window = arr[start:idx]
    valid = window[~np.isnan(window)]
    return float(np.nanmean(valid)) if len(valid) > 0 else np.nan


def _extract_overnight_multiscale(pdf):
    """Extract overnight windows with Nyquist-correct multi-scale features.

    Observation: 8h window (00:00-08:00) — Nyquist-compliant for 6h DIA.
    Demand lookback: 6h, 12h (Nyquist for DIA)
    Supply lookback: 24h, 48h, 96h (Nyquist for metabolic drift)
    """
    pdf = pdf.sort_values("time").reset_index(drop=True)
    t = pd.to_datetime(pdf["time"])
    pdf = pdf.assign(hour=t.dt.hour, date=t.dt.date)

    glucose = pdf["glucose"].values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    actual_basal = pdf["actual_basal_rate"].fillna(0).values.astype(np.float64)
    sched_basal = pdf["scheduled_basal_rate"].fillna(0).values.astype(np.float64)
    sched_cr = pdf["scheduled_cr"].fillna(0).values.astype(np.float64)

    # Total insulin delivery (bolus + basal per 5min)
    insulin_delivery = bolus + actual_basal / STEPS_PER_HOUR

    rows = []
    for date_val in sorted(pdf["date"].unique()):
        # Find midnight index for this date
        mask_midnight = (pdf["date"] == date_val) & (pdf["hour"] == 0)
        midnight_rows = pdf[mask_midnight]
        if len(midnight_rows) == 0:
            continue
        idx_midnight = midnight_rows.index[0]
        pos_midnight = pdf.index.get_loc(idx_midnight)

        # 8h observation window: 00:00 to 08:00
        obs_end = pos_midnight + 8 * STEPS_PER_HOUR
        if obs_end > len(pdf):
            continue

        obs_glucose = glucose[pos_midnight:obs_end]
        valid_mask = ~np.isnan(obs_glucose)
        n_valid = int(np.sum(valid_mask))
        if n_valid < 48:  # need ≥50% of 96 points (4h of valid data)
            continue

        # Skip if significant carbs or manual bolus during observation
        obs_carbs = float(np.nansum(carbs[pos_midnight:obs_end]))
        obs_bolus = float(np.nansum(bolus[pos_midnight:obs_end]))
        if obs_carbs > 5 or obs_bolus > 0.5:
            continue

        # Drift (mg/dL/hr) over 8h window
        valid_idx = np.where(valid_mask)[0]
        t_hrs = valid_idx.astype(float) / STEPS_PER_HOUR
        bg_valid = obs_glucose[valid_idx]
        if len(bg_valid) < 20:
            continue
        slope, intercept, r, p, se = stats.linregress(t_hrs, bg_valid)

        # Need sufficient lookback for 96h features
        if pos_midnight < 96 * STEPS_PER_HOUR:
            continue

        # === DEMAND features (insulin, fast timescale) ===
        iob_now = float(iob[pos_midnight])
        insulin_6h = _compute_lookback(insulin_delivery, pos_midnight, 6)
        insulin_12h = _compute_lookback(insulin_delivery, pos_midnight, 12)
        insulin_24h = _compute_lookback(insulin_delivery, pos_midnight, 24)
        insulin_48h = _compute_lookback(insulin_delivery, pos_midnight, 48)
        basal_actual_6h = _compute_mean_lookback(actual_basal, pos_midnight, 6)
        basal_sched = _compute_mean_lookback(sched_basal, pos_midnight, 6)

        # === SUPPLY features (metabolic, slow timescale) ===
        carbs_24h = _compute_lookback(carbs, pos_midnight, 24)
        carbs_48h = _compute_lookback(carbs, pos_midnight, 48)
        carbs_96h = _compute_lookback(carbs, pos_midnight, 96)

        # Net energy balance: carbs - insulin×CR (how much unmatched carb energy)
        cr_median = _compute_mean_lookback(sched_cr, pos_midnight, 6)
        if cr_median > 0 and not np.isnan(cr_median):
            net_energy_48h = carbs_48h - insulin_48h * cr_median
            net_energy_24h = carbs_24h - insulin_24h * cr_median
        else:
            net_energy_48h = np.nan
            net_energy_24h = np.nan

        # Mean glucose over prior 24h and 48h (metabolic state)
        mean_bg_24h = _compute_mean_lookback(glucose, pos_midnight, 24)
        mean_bg_48h = _compute_mean_lookback(glucose, pos_midnight, 48)

        rows.append({
            "date": str(date_val),
            "drift": float(slope),
            "mean_glucose": float(np.nanmean(obs_glucose)),
            "n_valid": n_valid,
            # Demand features
            "iob_now": iob_now,
            "insulin_6h": insulin_6h,
            "insulin_12h": insulin_12h,
            "basal_actual_6h": basal_actual_6h,
            "basal_sched": basal_sched,
            # Supply features
            "carbs_24h": carbs_24h,
            "carbs_48h": carbs_48h,
            "carbs_96h": carbs_96h,
            "net_energy_48h": net_energy_48h,
            "net_energy_24h": net_energy_24h,
            "mean_bg_24h": mean_bg_24h,
            "mean_bg_48h": mean_bg_48h,
        })

    return pd.DataFrame(rows)


def _fit_models(df, label=""):
    """Fit demand-only, supply-only, and combined models. Return R² comparison."""
    if len(df) < 15:
        return None

    y = df["drift"].values

    # Model 1: Demand only (IOB@midnight — our baseline from EXP-2628)
    X_demand_1 = df[["iob_now"]].values
    from numpy.linalg import lstsq
    def r2(X, y):
        X_aug = np.column_stack([X, np.ones(len(X))])
        beta, _, _, _ = lstsq(X_aug, y, rcond=None)
        pred = X_aug @ beta
        ss_res = np.sum((y - pred)**2)
        ss_tot = np.sum((y - y.mean())**2)
        if ss_tot == 0:
            return 0.0
        return float(1 - ss_res / ss_tot)

    # Model 2: Demand expanded (IOB + insulin_12h + basal_actual)
    demand_cols = ["iob_now", "insulin_12h", "basal_actual_6h"]
    valid_demand = df[demand_cols].dropna()
    if len(valid_demand) < 15:
        X_demand = df[["iob_now"]].values
        demand_r2 = r2(X_demand, y)
    else:
        idx = valid_demand.index
        X_demand = valid_demand.values
        demand_r2 = r2(X_demand, y[idx])

    # Model 3: Supply only (carbs_48h + mean_bg_48h)
    supply_cols = ["carbs_48h", "mean_bg_48h"]
    valid_supply = df[supply_cols].dropna()
    if len(valid_supply) < 15:
        supply_r2 = np.nan
    else:
        idx = valid_supply.index
        X_supply = valid_supply.values
        supply_r2 = r2(X_supply, y[idx])

    # Model 4: Net energy balance
    ne_cols = ["net_energy_48h"]
    valid_ne = df[ne_cols].dropna()
    if len(valid_ne) < 15:
        ne_r2 = np.nan
    else:
        idx = valid_ne.index
        ne_r2 = r2(valid_ne.values, y[idx])

    # Model 5: Combined (demand + supply)
    combined_cols = ["iob_now", "insulin_12h", "carbs_48h", "mean_bg_48h"]
    valid_combined = df[combined_cols].dropna()
    if len(valid_combined) < 15:
        combined_r2 = np.nan
    else:
        idx = valid_combined.index
        combined_r2 = r2(valid_combined.values, y[idx])

    # Model 6: Combined with net energy
    full_cols = ["iob_now", "insulin_12h", "carbs_48h", "net_energy_48h", "mean_bg_48h"]
    valid_full = df[full_cols].dropna()
    if len(valid_full) < 15:
        full_r2 = np.nan
    else:
        idx = valid_full.index
        full_r2 = r2(valid_full.values, y[idx])

    # Window sweep: does 96h add over 48h?
    carb_24_r2 = r2(df[["carbs_24h"]].values, y)
    carb_48_r2 = r2(df[["carbs_48h"]].values, y)
    carb_96_r2 = r2(df[["carbs_96h"]].values, y)

    # IOB alone
    iob_r2 = r2(df[["iob_now"]].values, y)

    return {
        "n_nights": len(df),
        "drift_mean": float(y.mean()),
        "drift_std": float(y.std()),
        # Individual predictors
        "iob_alone_r2": iob_r2,
        "carbs_24h_r2": carb_24_r2,
        "carbs_48h_r2": carb_48_r2,
        "carbs_96h_r2": carb_96_r2,
        "net_energy_r2": float(ne_r2) if not np.isnan(ne_r2) else None,
        # Models
        "demand_r2": demand_r2,
        "supply_r2": float(supply_r2) if not np.isnan(supply_r2) else None,
        "combined_r2": float(combined_r2) if not np.isnan(combined_r2) else None,
        "full_r2": float(full_r2) if not np.isnan(full_r2) else None,
        # Correlations
        "r_iob_drift": float(np.corrcoef(df["iob_now"].values, y)[0, 1]),
        "r_carbs48_drift": float(np.corrcoef(df["carbs_48h"].values, y)[0, 1]),
        "r_meanbg48_drift": float(np.corrcoef(df["mean_bg_48h"].values, y)[0, 1]),
    }


def main():
    print("=" * 70)
    print("EXP-2653: Nyquist-Aware Multi-Scale Supply/Demand Balance")
    print("=" * 70)

    df_all = pd.read_parquet(PARQUET)
    results = {}
    all_nights = []

    for pid in ALL_PATIENTS:
        pdf = df_all[df_all["patient_id"] == pid].copy()
        if len(pdf) < 200:
            continue

        nights = _extract_overnight_multiscale(pdf)
        if len(nights) < 10:
            print(f"\n  {pid}: insufficient nights ({len(nights)})")
            continue

        model = _fit_models(nights, pid)
        if model is None:
            continue

        prefix = "[ODC]" if pid.startswith("odc") else "[NS] "
        print(f"\n  {prefix} {pid} ({model['n_nights']} nights):")
        print(f"    Drift: {model['drift_mean']:+.1f} ± {model['drift_std']:.1f} mg/dL/hr")
        print(f"    Individual predictors:")
        print(f"      IOB@midnight  R²={model['iob_alone_r2']:.3f}  r={model['r_iob_drift']:+.3f}")
        print(f"      Carbs 24h     R²={model['carbs_24h_r2']:.3f}")
        print(f"      Carbs 48h     R²={model['carbs_48h_r2']:.3f}  r={model['r_carbs48_drift']:+.3f}")
        print(f"      Carbs 96h     R²={model['carbs_96h_r2']:.3f}")
        ne = model.get('net_energy_r2')
        print(f"      Net energy    R²={ne:.3f}" if ne is not None else "      Net energy    N/A")
        print(f"    Multi-variable models:")
        print(f"      Demand only   R²={model['demand_r2']:.3f}")
        sr = model.get('supply_r2')
        print(f"      Supply only   R²={sr:.3f}" if sr is not None else "      Supply only   N/A")
        cr = model.get('combined_r2')
        print(f"      Combined      R²={cr:.3f}" if cr is not None else "      Combined      N/A")
        fr = model.get('full_r2')
        print(f"      Full model    R²={fr:.3f}" if fr is not None else "      Full model    N/A")

        # Supply increment
        if cr is not None and not np.isnan(model['demand_r2']):
            incr = cr - model['demand_r2']
            print(f"    Supply increment: {incr:+.3f} R²")

        results[pid] = model
        nights["patient"] = pid
        all_nights.append(nights)

    # === Pooled analysis ===
    if all_nights:
        pooled = pd.concat(all_nights, ignore_index=True)
        pooled_model = _fit_models(pooled, "pooled")
        results["_pooled"] = pooled_model

        print(f"\n  POOLED ({pooled_model['n_nights']} nights across {len(all_nights)} patients):")
        print(f"    IOB@midnight  R²={pooled_model['iob_alone_r2']:.3f}")
        print(f"    Carbs 48h     R²={pooled_model['carbs_48h_r2']:.3f}")
        print(f"    Demand model  R²={pooled_model['demand_r2']:.3f}")
        sr = pooled_model.get('supply_r2')
        print(f"    Supply model  R²={sr:.3f}" if sr is not None else "    Supply model  N/A")
        cr = pooled_model.get('combined_r2')
        print(f"    Combined      R²={cr:.3f}" if cr is not None else "    Combined      N/A")

    # === Hypothesis testing ===
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    # H1: Combined R² ≥ 0.25
    combined_r2s = [r.get("combined_r2") for r in results.values()
                    if r.get("combined_r2") is not None and not isinstance(r.get("n_nights"), type(None))]
    valid_combined = [r for r in combined_r2s if r is not None and not np.isnan(r)]
    mean_combined = np.mean(valid_combined) if valid_combined else 0
    print(f"\n  H1: Multi-scale model R² ≥ 0.25 (mean across patients)")
    print(f"      Mean combined R² = {mean_combined:.3f}")
    h1 = mean_combined >= 0.25
    print(f"      → {'PASS' if h1 else 'FAIL'}")

    # H2: Supply adds ≥5% incremental R²
    increments = []
    for pid, r in results.items():
        if pid.startswith("_"):
            continue
        cr = r.get("combined_r2")
        dr = r.get("demand_r2")
        if cr is not None and dr is not None and not np.isnan(cr) and not np.isnan(dr):
            increments.append(cr - dr)
    mean_incr = np.mean(increments) if increments else 0
    print(f"\n  H2: Supply adds ≥0.05 incremental R²")
    print(f"      Mean increment = {mean_incr:+.3f}")
    print(f"      Per-patient: {[f'{x:+.3f}' for x in sorted(increments, reverse=True)]}")
    h2 = mean_incr >= 0.05
    print(f"      → {'PASS' if h2 else 'FAIL'}")

    # H3: 48h > 96h for carbs
    better_48 = 0
    total = 0
    for pid, r in results.items():
        if pid.startswith("_"):
            continue
        r48 = r.get("carbs_48h_r2", 0)
        r96 = r.get("carbs_96h_r2", 0)
        if not np.isnan(r48) and not np.isnan(r96):
            total += 1
            if r48 >= r96:
                better_48 += 1
    print(f"\n  H3: 48h carbs ≥ 96h carbs in R² (consistent with EXP-2627)")
    print(f"      48h better: {better_48}/{total}")
    h3 = better_48 > total / 2 if total > 0 else False
    print(f"      → {'PASS' if h3 else 'FAIL'}")

    # H4: Net energy > raw carbs
    better_ne = 0
    total_ne = 0
    for pid, r in results.items():
        if pid.startswith("_"):
            continue
        ne = r.get("net_energy_r2")
        c48 = r.get("carbs_48h_r2", 0)
        if ne is not None and not np.isnan(ne) and not np.isnan(c48):
            total_ne += 1
            if ne > c48:
                better_ne += 1
    print(f"\n  H4: Net energy balance better than raw carbs")
    print(f"      Net energy wins: {better_ne}/{total_ne}")
    h4 = better_ne > total_ne / 2 if total_ne > 0 else False
    print(f"      → {'PASS' if h4 else 'FAIL'}")

    # H5: Per-patient demand/supply weighting varies ≥2×
    demand_r2s = [r.get("demand_r2", 0) for pid, r in results.items() if not pid.startswith("_")]
    supply_r2s = [r.get("supply_r2") for pid, r in results.items() if not pid.startswith("_")]
    supply_r2s = [s for s in supply_r2s if s is not None and not np.isnan(s)]
    if demand_r2s and supply_r2s:
        ratios = []
        for pid, r in results.items():
            if pid.startswith("_"):
                continue
            d = r.get("demand_r2", 0)
            s = r.get("supply_r2")
            if s is not None and s > 0 and d > 0:
                ratios.append(d / s)
        if ratios:
            print(f"\n  H5: Demand/supply ratio varies ≥2× across patients")
            print(f"      Ratios: {[f'{x:.1f}' for x in sorted(ratios)]}")
            ratio_range = max(ratios) / min(ratios) if min(ratios) > 0 else float("inf")
            print(f"      Range: {ratio_range:.1f}×")
            h5 = ratio_range >= 2.0
            print(f"      → {'PASS' if h5 else 'FAIL'}")

    # Save results
    Path(OUTFILE).write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
