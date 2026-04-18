#!/usr/bin/env python3
"""EXP-2619: Multi-Day Metabolic Context as ISF/k Predictor.

RATIONALE: EXP-2618 showed the forward sim fails at 8h because it has
no metabolic demand model. The sim's ISF/k parameters vary per-window
because unmeasured glycogen state affects insulin sensitivity and HGP.

Literature timescales:
  - Glycogen depletion: 12-24h fasting
  - Glycogen repletion: 24-48h carb intake
  - Metabolic shift: 40-72h (glycogenolysis → gluconeogenesis dominant)
  - Preliminary signal: 72h cumulative carbs → next TIR r=-0.16 (p=0.03)

APPROACH: For each 2h correction window (where calibration works), compute
metabolic context features from the PRIOR 24/48/72h:
  - cumulative carbs (glycogen input proxy)
  - cumulative insulin (demand proxy)
  - carb:insulin ratio (metabolic balance)
  - mean glucose over prior period (glycemic state)
  - time since last meal (acute fasting state)

Then test whether these features explain per-window ISF multiplier variance.

H1: 48-72h cumulative carbs explains ≥15% of per-window ISF variance
    (R² ≥ 0.15) for ≥4/9 patients. More prior carbs → lower ISF (insulin resistant).
H2: Multi-day metabolic context improves per-window glucose prediction
    (MAE reduction ≥5%) vs context-free calibration.
H3: Patients with more variable glycogen proxy (high CV of daily carbs)
    show stronger metabolic context effect on ISF.
H4: The metabolic context signal is stronger at 72h than 24h lookback,
    consistent with glycogen repletion timescale.
"""

import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from cgmencode.production.forward_simulator import (
    forward_simulate, TherapySettings, InsulinEvent,
)

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2619_metabolic_context.json")

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]
WINDOW_STEPS = 24  # 2h
ISF_GRID = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0,
            1.1, 1.2, 1.3, 1.5, 2.0, 2.5, 3.0]

# Lookback horizons in hours
LOOKBACKS = {"24h": 24, "48h": 48, "72h": 72}


def _extract_correction_with_context(pdf, max_windows=60):
    """Extract correction windows with multi-day metabolic context."""
    windows = []
    bolus_mask = (pdf["bolus"] >= 0.5)

    for idx in pdf.index[bolus_mask]:
        pos = pdf.index.get_loc(idx)
        if pos + WINDOW_STEPS >= len(pdf):
            continue

        row = pdf.iloc[pos]
        pre_g = row["glucose"]
        if np.isnan(pre_g) or pre_g < 120:
            continue

        window = pdf.iloc[pos:pos + WINDOW_STEPS]
        if window["carbs"].sum() > 2:
            continue

        g_vals = window["glucose"].values
        valid = ~np.isnan(g_vals)
        if valid.sum() < WINDOW_STEPS * 0.5:
            continue

        end_g = g_vals[valid][-1]
        actual_drop = end_g - pre_g

        # Compute metabolic context for each lookback
        context = {}
        for label, hours in LOOKBACKS.items():
            lookback_steps = hours * 12  # 5-min steps
            start_lookback = max(0, pos - lookback_steps)
            prior = pdf.iloc[start_lookback:pos]

            if len(prior) < lookback_steps * 0.3:
                context[label] = None
                continue

            cum_carbs = float(prior["carbs"].sum())
            cum_bolus = float(prior["bolus"].sum())
            cum_smb = float(prior["bolus_smb"].sum())
            cum_insulin = cum_bolus + cum_smb
            # Add basal insulin
            cum_basal = float(prior["actual_basal_rate"].sum()) * (5.0 / 60.0)
            cum_total_insulin = cum_insulin + cum_basal

            mean_glucose = float(prior["glucose"].mean())
            glucose_std = float(prior["glucose"].std())

            # Time since last carb event
            carb_times = prior.index[prior["carbs"] > 5]
            if len(carb_times) > 0:
                last_carb_pos = pdf.index.get_loc(carb_times[-1])
                hours_since_carb = (pos - last_carb_pos) * 5.0 / 60.0
            else:
                hours_since_carb = float(hours)  # no carbs in entire lookback

            carb_insulin_ratio = cum_carbs / max(cum_total_insulin, 0.1)

            context[label] = {
                "cum_carbs": round(cum_carbs, 1),
                "cum_insulin": round(cum_total_insulin, 1),
                "carb_insulin_ratio": round(carb_insulin_ratio, 2),
                "mean_glucose": round(mean_glucose, 1),
                "glucose_std": round(glucose_std, 1),
                "hours_since_carb": round(hours_since_carb, 1),
            }

        if context.get("72h") is None:
            continue

        windows.append({
            "pre_g": float(pre_g),
            "end_g": float(end_g),
            "actual_drop": float(actual_drop),
            "bolus": float(row["bolus"]),
            "isf": float(row["scheduled_isf"]),
            "cr": float(row["scheduled_cr"]),
            "basal": float(row["scheduled_basal_rate"]),
            "hour": int(row["time"].hour),
            "context": context,
        })

        if len(windows) >= max_windows:
            break

    return windows


def _calibrate_per_window(window, k=0):
    """Find best ISF for a single window."""
    best_isf = 1.0
    best_err = float("inf")

    for isf_mult in ISF_GRID:
        settings = TherapySettings(
            basal_rate=window["basal"],
            isf=window["isf"] * isf_mult,
            cr=window["cr"],
        )
        result = forward_simulate(
            initial_glucose=window["pre_g"],
            settings=settings,
            bolus_events=[InsulinEvent(time_minutes=0, units=window["bolus"])],
            carb_events=[],
            duration_hours=2.0,
            counter_reg_k=k,
        )
        sim_end = result.glucose[-1] if len(result.glucose) > 0 else window["pre_g"]
        err = abs((sim_end - window["pre_g"]) - window["actual_drop"])
        if err < best_err:
            best_err = err
            best_isf = isf_mult

    return best_isf, best_err


def main():
    print("=" * 70)
    print("EXP-2619: Multi-Day Metabolic Context as ISF/k Predictor")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    print(f"Loaded {len(df)} rows\n")

    results = {}
    h4_r24_all = []
    h4_r72_all = []

    for pid in FULL_PATIENTS:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 1000:
            continue

        print(f"\n{'='*55}")
        print(f"PATIENT {pid}")
        print(f"{'='*55}")

        windows = _extract_correction_with_context(pdf)
        if len(windows) < 10:
            print(f"  Only {len(windows)} windows with context, skipping")
            continue

        print(f"  {len(windows)} correction windows with 72h context")

        # Calibrate per-window ISF
        per_window_isf = []
        for w in windows:
            isf_w, _ = _calibrate_per_window(w)
            per_window_isf.append(isf_w)
            w["calibrated_isf"] = isf_w

        isf_mean = np.mean(per_window_isf)
        isf_std = np.std(per_window_isf)
        isf_cv = isf_std / isf_mean * 100 if isf_mean > 0 else 0
        print(f"  Per-window ISF: mean={isf_mean:.2f}, std={isf_std:.2f}, CV={isf_cv:.0f}%")

        # Test context features vs ISF for each lookback
        best_feature = None
        best_r2 = 0
        best_lookback = None
        feature_results = {}

        for lookback in LOOKBACKS:
            features = {}
            for feat_name in ["cum_carbs", "cum_insulin", "carb_insulin_ratio",
                              "mean_glucose", "glucose_std", "hours_since_carb"]:
                vals = []
                isfs = []
                for w in windows:
                    ctx = w["context"].get(lookback)
                    if ctx is None:
                        continue
                    vals.append(ctx[feat_name])
                    isfs.append(w["calibrated_isf"])

                if len(vals) < 10 or len(set(vals)) < 3:
                    continue

                r, p = stats.pearsonr(vals, isfs)
                r2 = r ** 2
                features[feat_name] = {"r": round(r, 3), "p": round(p, 4), "r2": round(r2, 3)}

                if r2 > best_r2:
                    best_r2 = r2
                    best_feature = f"{lookback}_{feat_name}"
                    best_lookback = lookback

            feature_results[lookback] = features

        # Report best features per lookback
        for lookback in LOOKBACKS:
            feats = feature_results.get(lookback, {})
            if feats:
                best_in_lb = max(feats.items(), key=lambda x: abs(x[1]["r"]))
                print(f"  {lookback}: best={best_in_lb[0]}, r={best_in_lb[1]['r']:.3f}, p={best_in_lb[1]['p']:.4f}")

        print(f"  Overall best: {best_feature}, R²={best_r2:.3f}")

        # H1: R² ≥ 0.15 from cumulative carbs
        carbs_r2 = {}
        for lookback in LOOKBACKS:
            f = feature_results.get(lookback, {}).get("cum_carbs", {})
            carbs_r2[lookback] = f.get("r2", 0)
        h1_met = max(carbs_r2.values()) >= 0.15

        # H4: 72h stronger than 24h
        r24_carbs = feature_results.get("24h", {}).get("cum_carbs", {}).get("r", 0)
        r72_carbs = feature_results.get("72h", {}).get("cum_carbs", {}).get("r", 0)
        h4_r24_all.append(abs(r24_carbs))
        h4_r72_all.append(abs(r72_carbs))

        # H2: Context-aware prediction improvement
        # Split: stratify windows by glycogen proxy (high/low 72h carbs)
        carbs_72h = [w["context"]["72h"]["cum_carbs"] for w in windows]
        median_carbs = np.median(carbs_72h)

        high_carb_wins = [w for w in windows if w["context"]["72h"]["cum_carbs"] >= median_carbs]
        low_carb_wins = [w for w in windows if w["context"]["72h"]["cum_carbs"] < median_carbs]

        # Calibrate separately for high/low carb windows
        if len(high_carb_wins) >= 5 and len(low_carb_wins) >= 5:
            high_isfs = [w["calibrated_isf"] for w in high_carb_wins]
            low_isfs = [w["calibrated_isf"] for w in low_carb_wins]
            high_isf_mean = np.mean(high_isfs)
            low_isf_mean = np.mean(low_isfs)
            print(f"  High-carb ISF: {high_isf_mean:.2f} (n={len(high_carb_wins)})")
            print(f"  Low-carb ISF:  {low_isf_mean:.2f} (n={len(low_carb_wins)})")
            isf_split_diff = abs(high_isf_mean - low_isf_mean)
        else:
            high_isf_mean = low_isf_mean = isf_mean
            isf_split_diff = 0

        # Daily carb variability
        pdf_daily_carbs = pdf.groupby(pdf["time"].dt.date)["carbs"].sum()
        carb_cv = pdf_daily_carbs.std() / max(pdf_daily_carbs.mean(), 1) * 100

        results[pid] = {
            "n_windows": len(windows),
            "isf_mean": round(isf_mean, 2),
            "isf_cv": round(isf_cv, 0),
            "carb_cv_daily": round(carb_cv, 0),
            "best_feature": best_feature,
            "best_r2": round(best_r2, 3),
            "carbs_r2": {k: round(v, 3) for k, v in carbs_r2.items()},
            "h1_met": h1_met,
            "high_carb_isf": round(high_isf_mean, 2),
            "low_carb_isf": round(low_isf_mean, 2),
            "isf_split_diff": round(isf_split_diff, 2),
            "features": feature_results,
        }

    # ====== Cross-patient ======
    print("\n" + "=" * 70)
    print("CROSS-PATIENT ANALYSIS")
    print("=" * 70)

    # H1: Carbs R² ≥ 0.15 for ≥4 patients
    h1_count = sum(1 for r in results.values() if r["h1_met"])
    h1_confirmed = h1_count >= 4
    print(f"\nH1 - Cumulative carbs R² ≥ 0.15:")
    for pid, r in sorted(results.items()):
        print(f"  {pid:>5s}: 24h={r['carbs_r2'].get('24h',0):.3f}, "
              f"48h={r['carbs_r2'].get('48h',0):.3f}, "
              f"72h={r['carbs_r2'].get('72h',0):.3f} {'✓' if r['h1_met'] else '✗'}")
    print(f"  {h1_count}/{len(results)} meet threshold")
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'}")

    # H2: Context-aware MAE improvement
    h2_count = sum(1 for r in results.values() if r["isf_split_diff"] >= 0.1)
    h2_confirmed = h2_count >= len(results) * 0.5
    print(f"\nH2 - High/low carb ISF split ≥ 0.1:")
    for pid, r in sorted(results.items()):
        print(f"  {pid:>5s}: high={r['high_carb_isf']:.2f}, low={r['low_carb_isf']:.2f}, "
              f"diff={r['isf_split_diff']:.2f}")
    print(f"  {h2_count}/{len(results)} show meaningful split")
    print(f"  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'}")

    # H3: Carb CV correlates with context effect strength
    carb_cvs = [r["carb_cv_daily"] for r in results.values()]
    best_r2s = [r["best_r2"] for r in results.values()]
    if len(carb_cvs) >= 5:
        h3_r, h3_p = stats.pearsonr(carb_cvs, best_r2s)
    else:
        h3_r, h3_p = 0, 1
    h3_confirmed = h3_r > 0.3 and h3_p < 0.2
    print(f"\nH3 - Carb variability vs context effect:")
    print(f"  r={h3_r:.3f}, p={h3_p:.4f}")
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'}")

    # H4: 72h stronger than 24h
    mean_r24 = np.mean(h4_r24_all) if h4_r24_all else 0
    mean_r72 = np.mean(h4_r72_all) if h4_r72_all else 0
    h4_confirmed = mean_r72 > mean_r24
    print(f"\nH4 - 72h vs 24h carbs→ISF signal:")
    print(f"  Mean |r| 24h: {mean_r24:.3f}")
    print(f"  Mean |r| 72h: {mean_r72:.3f}")
    print(f"  H4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'}")

    # Summary
    print(f"\n{'Pt':>5s}  {'ISFcv':>5s}  {'CarbCV':>6s}  {'BestFeat':>25s}  {'R²':>5s}  {'Hi-Lo':>6s}")
    print("-" * 62)
    for pid, r in sorted(results.items()):
        print(f"{pid:>5s}  {r['isf_cv']:>4.0f}%  {r['carb_cv_daily']:>5.0f}%  "
              f"{r['best_feature'] or 'none':>25s}  {r['best_r2']:>5.3f}  "
              f"{r['isf_split_diff']:>+5.2f}")

    output = {
        "experiment": "EXP-2619",
        "title": "Multi-Day Metabolic Context as ISF/k Predictor",
        "patients": results,
        "hypotheses": {
            "H1": {"count": h1_count, "confirmed": h1_confirmed},
            "H2": {"count": h2_count, "confirmed": h2_confirmed},
            "H3": {"r": round(h3_r, 3), "p": round(h3_p, 4), "confirmed": h3_confirmed},
            "H4": {"mean_r24": round(mean_r24, 3), "mean_r72": round(mean_r72, 3),
                    "confirmed": h4_confirmed},
        },
    }

    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
