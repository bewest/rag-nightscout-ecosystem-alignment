#!/usr/bin/env python3
"""EXP-2629: AID Compensation Cascade & IOB-Protective Illusion.

MOTIVATION: The observation that "high IOB protects against hypos" is a
statistical artifact of AID controller behavior. When glucose drops, the
controller withdraws insulin (cancels temp basals, withholds SMBs), which
causes IOB to decline. The declining IOB then correlates with glucose
recovery — but the causation is reversed: the AID's withdrawal caused
both the lower IOB and the glucose recovery.

This creates a ringing/resonance pattern:
  1. Glucose drops → AID withdraws insulin → IOB falls
  2. Glucose recovers (EGP + reduced demand) → AID resumes insulin
  3. New insulin acts → glucose drops again → AID withdraws again
  4. Repeat with decreasing amplitude (damped oscillation)

HYPOTHESES:
  H1: IOB drops ≥30% within 1h of glucose approaching hypo threshold (<80).
      (AID is actively withdrawing insulin)
  H2: Glucose-IOB cross-correlation shows IOB LAGGING glucose by 15-45min.
      (IOB responds to glucose, not the other way around)
  H3: ≥3 oscillation cycles are detectable in ≥30% of low-glucose events.
      (Ringing is a common controller artifact)
  H4: Hill-equation EGP recovery matches observed post-nadir glucose rise
      rate within 25% (validating EGP model against real dynamics).

APPROACH: Use correction bolus events AND natural low-glucose episodes
to separate supply-side (EGP) from demand-side (AID compensation).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats, signal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
RESULTS_DIR = Path("externals/experiments")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = RESULTS_DIR / "exp-2629_aid_compensation_cascade.json"

FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

STEPS_PER_HOUR = 12
DT_HOURS = 1.0 / STEPS_PER_HOUR  # 5 min in hours

# Hill EGP model params (from metabolic_engine.py)
HILL_N = 1.5
HILL_K = 2.0  # Units IOB
BASE_EGP_PER_STEP = 1.5  # mg/dL per 5-min step

# Insulin model params
DIA_HOURS = 6.0
PEAK_MIN = 75.0


def _hill_egp(iob):
    """Hill-equation EGP: production suppressed by IOB."""
    iob_safe = np.maximum(np.nan_to_num(iob, nan=0.0), 0.0)
    suppression = iob_safe ** HILL_N / (iob_safe ** HILL_N + HILL_K ** HILL_N)
    return BASE_EGP_PER_STEP * (1.0 - suppression)


def _iob_fraction(t_minutes):
    """IOB fraction remaining at time t. Loop/oref0/AAPS exponential model."""
    td = DIA_HOURS * 60.0
    tp = PEAK_MIN
    tau = tp * (1.0 - tp / td) / (1.0 - 2.0 * tp / td)
    a = 2.0 * tau / td
    S = 1.0 / (1.0 - a + (1.0 + a) * np.exp(-td / tau))
    t = np.clip(t_minutes, 0, td)
    absorbed = S * (1.0 - a) * (
        (np.power(t, 2) / (tau * td * (1.0 - a)) - t / tau - 1.0) *
        np.exp(-t / tau) + 1.0
    )
    return np.clip(1.0 - absorbed, 0, 1)


def _find_low_glucose_episodes(pdf, threshold=80, context_steps=36):
    """Find episodes where glucose approaches hypo range.

    Returns windows: 3h before to 3h after first crossing below threshold.
    """
    glucose = pdf["glucose"].values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    net_basal = pdf["net_basal"].fillna(0).values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    times = pd.to_datetime(pdf["time"])
    n = len(glucose)

    episodes = []
    i = context_steps
    while i < n - context_steps:
        if not np.isfinite(glucose[i]):
            i += 1
            continue

        # Detect crossing below threshold from above
        if glucose[i] <= threshold and (i == 0 or glucose[i - 1] > threshold or
                                        not np.isfinite(glucose[i - 1])):
            start = max(0, i - context_steps)
            end = min(n, i + context_steps)
            window_glucose = glucose[start:end]
            window_iob = iob[start:end]
            window_basal = net_basal[start:end]
            window_bolus = bolus[start:end]

            valid = np.isfinite(window_glucose).sum()
            if valid < context_steps:
                i += context_steps
                continue

            # Measure IOB change in the hour before crossing
            pre_iob = iob[max(0, i - STEPS_PER_HOUR):i]
            post_iob = iob[i:min(n, i + STEPS_PER_HOUR)]
            if len(pre_iob) >= 6 and len(post_iob) >= 6:
                iob_before = float(np.nanmean(pre_iob[:6]))
                iob_at_cross = float(np.nanmean(pre_iob[-3:]))
                iob_after = float(np.nanmean(post_iob[-6:]))
                iob_pct_drop = (iob_before - iob_at_cross) / max(iob_before, 0.01) * 100

                # Net basal in the window (negative = suspension/reduction)
                basal_pre = float(np.nanmean(net_basal[max(0, i - STEPS_PER_HOUR):i]))
                basal_post = float(np.nanmean(net_basal[i:min(n, i + STEPS_PER_HOUR)]))

                episodes.append({
                    "crossing_idx": int(i),
                    "timestamp": str(times.iloc[i]),
                    "glucose_at_cross": float(glucose[i]),
                    "iob_before": iob_before,
                    "iob_at_cross": iob_at_cross,
                    "iob_after": iob_after,
                    "iob_pct_drop": iob_pct_drop,
                    "net_basal_pre": basal_pre,
                    "net_basal_post": basal_post,
                    "window_glucose": window_glucose.tolist(),
                    "window_iob": window_iob.tolist(),
                    "window_basal": window_basal.tolist(),
                })

            # Skip ahead to avoid double-counting
            i += context_steps
        else:
            i += 1

    return episodes


def _compute_cross_correlation(glucose, iob, max_lag_steps=24):
    """Compute cross-correlation between glucose rate-of-change and IOB.

    Positive lag = IOB lags glucose (AID responding to glucose).
    Negative lag = IOB leads glucose (insulin driving glucose).
    """
    valid = np.isfinite(glucose) & np.isfinite(iob)
    if valid.sum() < 100:
        return None

    g = glucose.copy()
    g[~valid] = np.nan
    iob_clean = iob.copy()
    iob_clean[~valid] = np.nan

    # Rate of change (mg/dL per 5 min)
    glucose_roc = np.diff(g)
    iob_roc = np.diff(iob_clean)

    valid_roc = np.isfinite(glucose_roc) & np.isfinite(iob_roc)
    if valid_roc.sum() < 50:
        return None

    g_roc = glucose_roc[valid_roc]
    i_roc = iob_roc[valid_roc]

    # Normalize
    g_roc = (g_roc - np.mean(g_roc)) / (np.std(g_roc) + 1e-10)
    i_roc = (i_roc - np.mean(i_roc)) / (np.std(i_roc) + 1e-10)

    lags = range(-max_lag_steps, max_lag_steps + 1)
    correlations = []
    for lag in lags:
        if lag >= 0:
            c = np.corrcoef(g_roc[:len(g_roc) - lag], i_roc[lag:])[0, 1]
        else:
            c = np.corrcoef(g_roc[-lag:], i_roc[:len(i_roc) + lag])[0, 1]
        correlations.append(float(c) if np.isfinite(c) else 0.0)

    lag_array = np.array(list(lags))
    corr_array = np.array(correlations)
    peak_lag_idx = np.argmax(np.abs(corr_array))
    peak_lag_steps = int(lag_array[peak_lag_idx])
    peak_lag_minutes = peak_lag_steps * 5

    return {
        "lags_steps": [int(x) for x in lag_array],
        "lags_minutes": [int(x * 5) for x in lag_array],
        "correlations": correlations,
        "peak_lag_steps": peak_lag_steps,
        "peak_lag_minutes": peak_lag_minutes,
        "peak_correlation": float(corr_array[peak_lag_idx]),
    }


def _detect_oscillations(glucose, min_amplitude=5, min_period_steps=6):
    """Detect damped oscillation cycles in glucose near low episodes.

    Returns number of cycles and damping characteristics.
    """
    valid = np.isfinite(glucose)
    if valid.sum() < 12:
        return {"cycles": 0, "amplitudes": [], "periods": []}

    g = pd.Series(glucose).interpolate(limit=3).values
    g_smooth = pd.Series(g).rolling(3, center=True, min_periods=1).mean().values

    # Find local extrema
    maxima = signal.argrelextrema(g_smooth, np.greater, order=3)[0]
    minima = signal.argrelextrema(g_smooth, np.less, order=3)[0]

    if len(maxima) < 1 or len(minima) < 1:
        return {"cycles": 0, "amplitudes": [], "periods": []}

    # Merge and sort extrema
    all_extrema = np.sort(np.concatenate([maxima, minima]))
    if len(all_extrema) < 3:
        return {"cycles": 0, "amplitudes": [], "periods": []}

    amplitudes = []
    periods = []
    for j in range(len(all_extrema) - 1):
        amp = abs(g_smooth[all_extrema[j + 1]] - g_smooth[all_extrema[j]])
        period = all_extrema[j + 1] - all_extrema[j]
        if amp >= min_amplitude and period >= min_period_steps:
            amplitudes.append(float(amp))
            periods.append(int(period))

    cycles = len(amplitudes) // 2  # A full cycle = peak-to-trough-to-peak

    return {
        "cycles": cycles,
        "amplitudes": amplitudes,
        "periods": periods,
        "damping_ratio": float(amplitudes[-1] / amplitudes[0])
            if len(amplitudes) >= 2 else float("nan"),
    }


def _compare_hill_egp_to_recovery(events, pdf):
    """Compare Hill-equation predicted EGP recovery to actual glucose rise.

    For each low-glucose episode, compute:
    1. Actual recovery rate (observed glucose rise post-nadir)
    2. Hill-predicted EGP at the IOB level during recovery
    3. Ratio: tells us if Hill model matches reality
    """
    glucose = pdf["glucose"].values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)

    comparisons = []
    for ep in events:
        idx = ep["crossing_idx"]
        window_g = np.array(ep["window_glucose"])
        window_iob = np.array(ep["window_iob"])
        n_win = len(window_g)
        mid = n_win // 2  # crossing point

        # Find nadir in the window
        valid = np.isfinite(window_g)
        if valid.sum() < 6:
            continue
        nadir_idx = np.nanargmin(window_g[max(0, mid - 6):min(n_win, mid + 12)])
        nadir_idx += max(0, mid - 6)

        # Recovery: nadir to nadir + 1h (12 steps)
        rec_end = min(n_win, nadir_idx + STEPS_PER_HOUR)
        rec_g = window_g[nadir_idx:rec_end]
        rec_iob = window_iob[nadir_idx:rec_end]
        valid_rec = np.isfinite(rec_g)
        if valid_rec.sum() < 4:
            continue

        # Actual recovery rate (mg/dL per hour)
        t_hrs = np.arange(valid_rec.sum()) * DT_HOURS
        actual_slope = np.polyfit(t_hrs, rec_g[valid_rec], 1)[0]

        # Hill-predicted EGP at average recovery IOB
        mean_rec_iob = float(np.nanmean(rec_iob))
        hill_egp = float(_hill_egp(np.array([mean_rec_iob]))[0])
        hill_rate = hill_egp * STEPS_PER_HOUR  # mg/dL per hour

        comparisons.append({
            "actual_recovery_rate": float(actual_slope),
            "hill_predicted_rate": hill_rate,
            "ratio": float(actual_slope / hill_rate) if hill_rate > 0 else float("nan"),
            "iob_at_recovery": mean_rec_iob,
            "nadir_glucose": float(window_g[nadir_idx]) if np.isfinite(window_g[nadir_idx]) else None,
        })

    return comparisons


def _analyze_correction_cascade(pdf):
    """Analyze post-correction cascades: bolus → drop → AID withdraw → recover → repeat.

    Uses correction events (bolus, no carbs) to trace the full cascade.
    """
    glucose = pdf["glucose"].values.astype(np.float64)
    iob = pdf["iob"].fillna(0).values.astype(np.float64)
    bolus = pdf["bolus"].fillna(0).values.astype(np.float64)
    carbs = pdf["carbs"].fillna(0).values.astype(np.float64)
    net_basal = pdf["net_basal"].fillna(0).values.astype(np.float64)
    n = len(glucose)

    cascades = []

    for i in range(12, n - 72):
        if bolus[i] < 0.5:
            continue
        # No carbs ±1h
        if np.nansum(carbs[max(0, i - 12):min(n, i + 12)]) > 2.0:
            continue
        # No prior bolus 2h
        if np.nansum(bolus[max(0, i - 24):i]) > 0.1:
            continue
        # Pre-BG > 130
        pre_g = glucose[max(0, i - 6):i]
        if np.nanmean(pre_g) < 130 or not np.any(np.isfinite(pre_g)):
            continue

        # 6h post-correction window
        post_g = glucose[i:min(n, i + 72)]
        post_iob = iob[i:min(n, i + 72)]
        post_basal = net_basal[i:min(n, i + 72)]

        valid = np.isfinite(post_g)
        if valid.sum() < 36:
            continue

        # Detect oscillations in this window
        osc = _detect_oscillations(post_g)

        # AID response: track net_basal changes
        # Negative net_basal = AID is reducing/suspending
        basal_phases = []
        for t in range(0, len(post_basal), 6):
            chunk = post_basal[t:t + 6]
            basal_phases.append(float(np.nanmean(chunk)))

        cascades.append({
            "bolus_idx": int(i),
            "bolus_u": float(bolus[i]),
            "pre_bg": float(np.nanmean(pre_g)),
            "oscillations": osc,
            "post_glucose": [float(x) if np.isfinite(x) else None for x in post_g[:72]],
            "post_iob": [float(x) if np.isfinite(x) else None for x in post_iob[:72]],
            "post_basal_30min_avg": basal_phases,
        })

    return cascades


def main():
    print("=" * 70)
    print("EXP-2629: AID Compensation Cascade & IOB-Protective Illusion")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)
    df["time"] = pd.to_datetime(df["time"])
    all_results = {}

    pooled_iob_drops = []
    pooled_peak_lags = []
    pooled_oscillation_counts = []
    pooled_hill_ratios = []
    pooled_cascade_osc = []

    for pid in FULL_PATIENTS:
        print(f"\n{'='*50}")
        print(f"Patient {pid}")
        print(f"{'='*50}")

        pdf = df[df["patient_id"] == pid].sort_values("time").copy()
        if len(pdf) < 288:
            print(f"  Skipping: only {len(pdf)} rows")
            continue

        # 1. Find low-glucose episodes
        episodes = _find_low_glucose_episodes(pdf, threshold=80)
        print(f"  Low-glucose episodes (BG<80): {len(episodes)}")

        iob_drops = [e["iob_pct_drop"] for e in episodes if np.isfinite(e["iob_pct_drop"])]
        if iob_drops:
            print(f"  IOB drop before crossing: mean={np.mean(iob_drops):.1f}%, "
                  f"median={np.median(iob_drops):.1f}%")
            pooled_iob_drops.extend(iob_drops)

        # 2. Cross-correlation (glucose ROC → IOB ROC)
        xcorr = _compute_cross_correlation(
            pdf["glucose"].values.astype(np.float64),
            pdf["iob"].fillna(0).values.astype(np.float64),
        )
        if xcorr:
            print(f"  Cross-correlation peak lag: {xcorr['peak_lag_minutes']} min "
                  f"(r={xcorr['peak_correlation']:.3f})")
            pooled_peak_lags.append(xcorr["peak_lag_minutes"])

        # 3. Oscillation detection in low-glucose windows
        episode_osc = []
        for ep in episodes:
            osc = _detect_oscillations(np.array(ep["window_glucose"]))
            episode_osc.append(osc["cycles"])
            pooled_oscillation_counts.append(osc["cycles"])
        episodes_with_osc = sum(1 for c in episode_osc if c >= 3)
        pct_with_osc = episodes_with_osc / max(len(episodes), 1) * 100
        print(f"  Episodes with ≥3 oscillation cycles: {episodes_with_osc}/{len(episodes)} "
              f"({pct_with_osc:.0f}%)")

        # 4. Hill EGP vs actual recovery
        comparisons = _compare_hill_egp_to_recovery(episodes, pdf)
        ratios = [c["ratio"] for c in comparisons if np.isfinite(c["ratio"])]
        if ratios:
            print(f"  Hill vs actual recovery ratio: mean={np.mean(ratios):.2f}, "
                  f"median={np.median(ratios):.2f}")
            pooled_hill_ratios.extend(ratios)

        # 5. Correction cascade analysis
        cascades = _analyze_correction_cascade(pdf)
        cascade_osc_counts = [c["oscillations"]["cycles"] for c in cascades]
        pooled_cascade_osc.extend(cascade_osc_counts)
        print(f"  Correction cascades: {len(cascades)}, "
              f"mean oscillation cycles: {np.mean(cascade_osc_counts):.1f}" if cascade_osc_counts else
              f"  Correction cascades: {len(cascades)}")

        # Store per-patient (trim large arrays for JSON)
        all_results[pid] = {
            "n_low_episodes": len(episodes),
            "mean_iob_drop_pct": float(np.mean(iob_drops)) if iob_drops else None,
            "median_iob_drop_pct": float(np.median(iob_drops)) if iob_drops else None,
            "cross_correlation": {
                "peak_lag_minutes": xcorr["peak_lag_minutes"] if xcorr else None,
                "peak_correlation": xcorr["peak_correlation"] if xcorr else None,
            },
            "oscillation_pct_with_3plus": pct_with_osc,
            "n_correction_cascades": len(cascades),
            "cascade_mean_oscillations": float(np.mean(cascade_osc_counts)) if cascade_osc_counts else None,
            "hill_vs_actual_ratio": float(np.mean(ratios)) if ratios else None,
            # Store representative examples for visualization
            "example_episodes": episodes[:5],
            "example_cascades": cascades[:3],
            "hill_comparisons": comparisons[:10],
        }

    # Pooled results
    print("\n" + "=" * 70)
    print("POOLED RESULTS")
    print("=" * 70)

    h1_pass = np.median(pooled_iob_drops) >= 30 if pooled_iob_drops else False
    h2_lags = [l for l in pooled_peak_lags if l > 0]
    h2_pass = (len(h2_lags) / max(len(pooled_peak_lags), 1) > 0.5 and
               np.median(h2_lags) >= 15) if h2_lags else False
    h3_pass = (sum(1 for c in pooled_oscillation_counts if c >= 3) /
               max(len(pooled_oscillation_counts), 1) >= 0.30) if pooled_oscillation_counts else False
    h4_ratios_in_range = [r for r in pooled_hill_ratios if 0.75 <= r <= 1.25]
    h4_pass = len(h4_ratios_in_range) / max(len(pooled_hill_ratios), 1) >= 0.5 if pooled_hill_ratios else False

    print(f"\nH1 - IOB drops ≥30% before hypo crossing:")
    print(f"  Median IOB drop: {np.median(pooled_iob_drops):.1f}%")
    print(f"  Result: {'PASS' if h1_pass else 'FAIL'}")

    print(f"\nH2 - IOB lags glucose (positive lag 15-45 min):")
    print(f"  Peak lags: {pooled_peak_lags}")
    print(f"  Median positive lag: {np.median(h2_lags):.0f} min" if h2_lags else "  No positive lags")
    print(f"  Result: {'PASS' if h2_pass else 'FAIL'}")

    print(f"\nH3 - ≥3 oscillation cycles in ≥30% of episodes:")
    pct_osc = sum(1 for c in pooled_oscillation_counts if c >= 3) / max(len(pooled_oscillation_counts), 1) * 100
    print(f"  Episodes with ≥3 cycles: {pct_osc:.0f}%")
    print(f"  Result: {'PASS' if h3_pass else 'FAIL'}")

    print(f"\nH4 - Hill EGP matches recovery within 25%:")
    if pooled_hill_ratios:
        print(f"  Mean ratio (actual/Hill): {np.mean(pooled_hill_ratios):.2f}")
        print(f"  Median ratio: {np.median(pooled_hill_ratios):.2f}")
        print(f"  Within 25%: {len(h4_ratios_in_range)}/{len(pooled_hill_ratios)} "
              f"({len(h4_ratios_in_range)/len(pooled_hill_ratios)*100:.0f}%)")
    print(f"  Result: {'PASS' if h4_pass else 'FAIL'}")

    results = {
        "experiment": "EXP-2629",
        "title": "AID Compensation Cascade & IOB-Protective Illusion",
        "patients": FULL_PATIENTS,
        "per_patient": all_results,
        "pooled": {
            "n_total_low_episodes": len(pooled_iob_drops),
            "median_iob_drop_pct": float(np.median(pooled_iob_drops)) if pooled_iob_drops else None,
            "mean_iob_drop_pct": float(np.mean(pooled_iob_drops)) if pooled_iob_drops else None,
            "peak_lags_minutes": pooled_peak_lags,
            "median_peak_lag_minutes": float(np.median(pooled_peak_lags)) if pooled_peak_lags else None,
            "pct_episodes_3plus_oscillations": pct_osc,
            "hill_ratio_mean": float(np.mean(pooled_hill_ratios)) if pooled_hill_ratios else None,
            "hill_ratio_median": float(np.median(pooled_hill_ratios)) if pooled_hill_ratios else None,
            "correction_cascade_mean_osc": float(np.mean(pooled_cascade_osc)) if pooled_cascade_osc else None,
        },
        "hypotheses": {
            "H1": {
                "statement": "IOB drops ≥30% within 1h of glucose approaching hypo (<80)",
                "threshold": 30.0,
                "value": float(np.median(pooled_iob_drops)) if pooled_iob_drops else None,
                "result": "PASS" if h1_pass else "FAIL",
            },
            "H2": {
                "statement": "Glucose-IOB cross-correlation shows IOB lagging glucose by 15-45min",
                "threshold": "lag > 0, median 15-45 min",
                "value": float(np.median(h2_lags)) if h2_lags else None,
                "result": "PASS" if h2_pass else "FAIL",
            },
            "H3": {
                "statement": "≥3 oscillation cycles in ≥30% of low-glucose events",
                "threshold": 30.0,
                "value": pct_osc,
                "result": "PASS" if h3_pass else "FAIL",
            },
            "H4": {
                "statement": "Hill EGP matches recovery within 25%",
                "threshold": "0.75-1.25 ratio",
                "value": float(np.median(pooled_hill_ratios)) if pooled_hill_ratios else None,
                "result": "PASS" if h4_pass else "FAIL",
            },
        },
    }

    with open(OUTFILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
