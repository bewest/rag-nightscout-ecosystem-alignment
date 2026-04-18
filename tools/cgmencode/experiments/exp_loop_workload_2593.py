#!/usr/bin/env python3
"""EXP-2593: Loop Workload as Settings Quality Metric.

The closed-loop AID system constantly adjusts basal rates to compensate
for settings that don't match physiology. The AMOUNT of adjustment is
a direct indicator of settings quality:
  - Perfect settings → loop delivers scheduled basal → low workload
  - Poor settings → loop constantly suspends/amplifies → high workload

Hypotheses:
  H1: Loop workload (std of net_basal / scheduled_basal ratio) correlates
      inversely with TIR (r < -0.5). Well-tuned patients need less loop work.
  H2: Directional workload (% time loop ADDS vs CUTS basal) reveals
      systematic settings errors. Consistently adding = basal too low,
      consistently cutting = basal too high.
  H3: Loop workload varies by time-of-day (circadian pattern), with
      higher workload during dawn (03-07) indicating dawn phenomenon
      not addressed by settings.
  H4: Workload metrics predict per-patient k (counter-regulation need).
      Patients where loop fights more to prevent lows have higher k.

Design:
  For each FULL telemetry patient:
    1. Compute hourly loop workload metrics:
       - Basal ratio: actual_basal / scheduled_basal
       - Suspension fraction: % time actual ≈ 0
       - Override magnitude: mean |actual - scheduled| / scheduled
       - Directional bias: mean(actual - scheduled) / scheduled (signed)
    2. Compute daily aggregates and circadian profiles
    3. Correlate with TIR, counter-reg k, and advisory recommendations
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PARQUET = Path("externals/ns-parquet/training/grid.parquet")
OUTFILE = Path("externals/experiments/exp-2593_loop_workload.json")

# FULL telemetry patients only (need actual_basal + scheduled_basal)
FULL_PATIENTS = ["a", "b", "c", "d", "e", "f", "g", "i", "k"]

# Per-patient k from EXP-2582
PATIENT_K = {
    "a": 2.0, "b": 3.0, "c": 7.0, "d": 1.5, "e": 1.5,
    "f": 1.0, "g": 1.0, "i": 3.0, "k": 0.0,
}

# ODC patients with FULL telemetry
ODC_PATIENTS = [
    "odc-74077367", "odc-86025410", "odc-96254963",
    "odc-10076963", "odc-91587879", "odc-87289563", "odc-95771020",
]


def compute_workload_metrics(pdf):
    """Compute loop workload metrics for a patient dataframe.

    Returns dict of metrics.
    """
    # Need actual_basal and scheduled_basal
    has_basal = (
        pdf["actual_basal_rate"].notna() &
        pdf["scheduled_basal_rate"].notna() &
        (pdf["scheduled_basal_rate"] > 0)
    )
    bdf = pdf[has_basal].copy()

    if len(bdf) < 100:
        return None

    sched = bdf["scheduled_basal_rate"].values
    actual = bdf["actual_basal_rate"].values
    glucose = bdf["glucose"].values

    # Basic ratio
    ratio = actual / sched  # 1.0 = no adjustment
    net = actual - sched    # positive = adding, negative = cutting

    # Overall workload
    suspension_frac = float(np.mean(actual < 0.01))  # near-zero actual
    override_magnitude = float(np.mean(np.abs(net) / sched))
    directional_bias = float(np.mean(net / sched))  # signed
    ratio_std = float(np.std(ratio))
    ratio_mean = float(np.mean(ratio))

    # Time adding vs cutting
    adding_frac = float(np.mean(net > 0.05))
    cutting_frac = float(np.mean(net < -0.05))
    neutral_frac = float(np.mean(np.abs(net) <= 0.05))

    # TIR
    valid_g = glucose[~np.isnan(glucose)]
    tir = float(np.mean((valid_g >= 70) & (valid_g <= 180))) if len(valid_g) > 0 else float("nan")
    tbr = float(np.mean(valid_g < 70)) if len(valid_g) > 0 else float("nan")
    tar = float(np.mean(valid_g > 180)) if len(valid_g) > 0 else float("nan")

    # Circadian workload profile (hourly)
    bdf_t = bdf.copy()
    bdf_t["hour"] = pd.to_datetime(bdf_t["time"]).dt.hour
    hourly = bdf_t.groupby("hour").agg(
        mean_ratio=("actual_basal_rate", lambda x: np.mean(x / bdf_t.loc[x.index, "scheduled_basal_rate"])),
        suspension_frac=("actual_basal_rate", lambda x: np.mean(x < 0.01)),
        n_rows=("actual_basal_rate", "count"),
    ).reset_index()

    # Dawn workload (03-07)
    dawn = hourly[hourly["hour"].between(3, 6)]
    day = hourly[hourly["hour"].between(8, 20)]
    night = hourly[hourly["hour"].isin([22, 23, 0, 1, 2])]

    dawn_suspension = float(dawn["suspension_frac"].mean()) if len(dawn) > 0 else float("nan")
    day_suspension = float(day["suspension_frac"].mean()) if len(day) > 0 else float("nan")
    night_suspension = float(night["suspension_frac"].mean()) if len(night) > 0 else float("nan")

    dawn_ratio = float(dawn["mean_ratio"].mean()) if len(dawn) > 0 else float("nan")
    day_ratio = float(day["mean_ratio"].mean()) if len(day) > 0 else float("nan")
    night_ratio = float(night["mean_ratio"].mean()) if len(night) > 0 else float("nan")

    # Workload composite score (higher = more loop work needed)
    # Combines ratio variability + suspension + override magnitude
    workload_score = ratio_std * 0.4 + suspension_frac * 0.3 + override_magnitude * 0.3

    return {
        "n_rows": int(len(bdf)),
        "tir": tir,
        "tbr": tbr,
        "tar": tar,
        # Workload metrics
        "ratio_mean": ratio_mean,
        "ratio_std": ratio_std,
        "suspension_frac": suspension_frac,
        "override_magnitude": override_magnitude,
        "directional_bias": directional_bias,
        "adding_frac": adding_frac,
        "cutting_frac": cutting_frac,
        "neutral_frac": neutral_frac,
        "workload_score": workload_score,
        # Circadian
        "dawn_suspension": dawn_suspension,
        "day_suspension": day_suspension,
        "night_suspension": night_suspension,
        "dawn_ratio": dawn_ratio,
        "day_ratio": day_ratio,
        "night_ratio": night_ratio,
        # Hourly profile (for visualization)
        "hourly_profile": hourly.to_dict(orient="records"),
    }


def main():
    print("=" * 70)
    print("EXP-2593: Loop Workload as Settings Quality Metric")
    print("=" * 70)

    df = pd.read_parquet(PARQUET)

    all_patients = FULL_PATIENTS + [p for p in ODC_PATIENTS if p in df["patient_id"].unique()]
    results = {}

    for pid in all_patients:
        pdf = df[df["patient_id"] == pid]
        if pdf.empty:
            continue

        metrics = compute_workload_metrics(pdf)
        if metrics is None:
            print(f"  {pid}: insufficient basal data")
            continue

        metrics["patient_id"] = pid
        metrics["k"] = PATIENT_K.get(pid, float("nan"))
        results[pid] = metrics

        print(f"  {pid}: TIR={metrics['tir']:.1%} workload={metrics['workload_score']:.3f} "
              f"suspend={metrics['suspension_frac']:.1%} bias={metrics['directional_bias']:+.2f} "
              f"add={metrics['adding_frac']:.1%} cut={metrics['cutting_frac']:.1%}")

    if not results:
        print("No results")
        return

    sdf = pd.DataFrame(list(results.values()))
    from scipy import stats

    # ===== H1: Workload vs TIR =====
    print(f"\n{'=' * 70}")
    print("H1: Loop workload inversely correlates with TIR")
    print(f"{'=' * 70}")

    valid_h1 = sdf.dropna(subset=["workload_score", "tir"])
    r_work_tir, p_work_tir = stats.spearmanr(valid_h1["workload_score"], valid_h1["tir"])
    print(f"  Workload score vs TIR: r={r_work_tir:.3f}, p={p_work_tir:.3f}")

    r_susp_tir, p_susp_tir = stats.spearmanr(valid_h1["suspension_frac"], valid_h1["tir"])
    print(f"  Suspension frac vs TIR: r={r_susp_tir:.3f}, p={p_susp_tir:.3f}")

    r_override_tir, p_override_tir = stats.spearmanr(valid_h1["override_magnitude"], valid_h1["tir"])
    print(f"  Override magnitude vs TIR: r={r_override_tir:.3f}, p={p_override_tir:.3f}")

    r_std_tir, p_std_tir = stats.spearmanr(valid_h1["ratio_std"], valid_h1["tir"])
    print(f"  Ratio std vs TIR: r={r_std_tir:.3f}, p={p_std_tir:.3f}")

    h1_confirmed = r_work_tir < -0.5
    print(f"  H1 {'CONFIRMED' if h1_confirmed else 'NOT CONFIRMED'} (threshold: r < -0.5)")

    # Additional: workload vs TBR
    r_work_tbr, _ = stats.spearmanr(valid_h1["workload_score"], valid_h1["tbr"])
    r_work_tar, _ = stats.spearmanr(valid_h1["workload_score"], valid_h1["tar"])
    print(f"  Workload vs TBR: r={r_work_tbr:.3f}")
    print(f"  Workload vs TAR: r={r_work_tar:.3f}")

    # ===== H2: Directional bias reveals settings errors =====
    print(f"\n{'=' * 70}")
    print("H2: Directional workload reveals systematic settings errors")
    print(f"{'=' * 70}")

    print(f"\n  {'Patient':<12} {'Bias':>8} {'Adding':>8} {'Cutting':>8} {'TIR':>8} {'Interpretation'}")
    print(f"  {'-'*65}")
    for _, r in sdf.iterrows():
        bias = r["directional_bias"]
        if bias > 0.1:
            interp = "BASAL TOO LOW (loop adds)"
        elif bias < -0.1:
            interp = "BASAL TOO HIGH (loop cuts)"
        else:
            interp = "BASAL ADEQUATE"
        print(f"  {r['patient_id']:<12} {bias:>+8.2f} {r['adding_frac']:>8.1%} "
              f"{r['cutting_frac']:>8.1%} {r['tir']:>8.1%} {interp}")

    # Bias vs TIR
    r_bias_tir, p_bias_tir = stats.spearmanr(sdf["directional_bias"], sdf["tir"])
    print(f"\n  Directional bias vs TIR: r={r_bias_tir:.3f}, p={p_bias_tir:.3f}")

    # Check if extreme bias (either direction) hurts TIR
    sdf["abs_bias"] = sdf["directional_bias"].abs()
    r_abs_tir, p_abs_tir = stats.spearmanr(sdf["abs_bias"], sdf["tir"])
    print(f"  |Bias| vs TIR: r={r_abs_tir:.3f}, p={p_abs_tir:.3f}")

    # Count consistent patterns
    basal_low = sdf[sdf["directional_bias"] > 0.1]
    basal_high = sdf[sdf["directional_bias"] < -0.1]
    basal_ok = sdf[sdf["directional_bias"].abs() <= 0.1]
    print(f"\n  Basal too low: {len(basal_low)} patients (avg TIR={basal_low['tir'].mean():.1%})")
    print(f"  Basal too high: {len(basal_high)} patients (avg TIR={basal_high['tir'].mean():.1%})")
    print(f"  Basal adequate: {len(basal_ok)} patients (avg TIR={basal_ok['tir'].mean():.1%})")

    h2_confirmed = len(basal_low) > 0 and len(basal_high) > 0  # both patterns exist
    print(f"\n  H2 {'CONFIRMED' if h2_confirmed else 'NOT CONFIRMED'} "
          f"(both over/under-basal patterns found)")

    # ===== H3: Circadian workload =====
    print(f"\n{'=' * 70}")
    print("H3: Dawn workload higher than daytime (dawn phenomenon)")
    print(f"{'=' * 70}")

    print(f"\n  {'Patient':<12} {'Dawn Susp':>10} {'Day Susp':>10} {'Night Susp':>10} "
          f"{'Dawn Ratio':>10} {'Day Ratio':>10}")
    print(f"  {'-'*65}")
    dawn_higher = 0
    for _, r in sdf.iterrows():
        dawn_s = r["dawn_suspension"]
        day_s = r["day_suspension"]
        night_s = r["night_suspension"]
        dawn_r = r["dawn_ratio"]
        day_r = r["day_ratio"]
        marker = " ←DAWN" if dawn_s > day_s * 1.5 else ""
        print(f"  {r['patient_id']:<12} {dawn_s:>10.1%} {day_s:>10.1%} {night_s:>10.1%} "
              f"{dawn_r:>10.2f} {day_r:>10.2f}{marker}")
        if dawn_s > day_s * 1.5:
            dawn_higher += 1

    dawn_suspensions = sdf["dawn_suspension"].values
    day_suspensions = sdf["day_suspension"].values
    t_stat, p_dawn = stats.wilcoxon(dawn_suspensions, day_suspensions, alternative="greater")
    print(f"\n  Wilcoxon dawn > day suspension: T={t_stat:.1f}, p={p_dawn:.3f}")
    print(f"  Patients with dawn > 1.5× day: {dawn_higher}/{len(sdf)}")

    h3_confirmed = p_dawn < 0.05 and dawn_higher >= len(sdf) * 0.4
    print(f"  H3 {'CONFIRMED' if h3_confirmed else 'NOT CONFIRMED'} "
          f"(need p<0.05 and ≥40% of patients)")

    # ===== H4: Workload predicts counter-reg k =====
    print(f"\n{'=' * 70}")
    print("H4: Workload metrics predict counter-regulation k")
    print(f"{'=' * 70}")

    valid_k = sdf.dropna(subset=["k"])
    valid_k = valid_k[valid_k["k"] > -1]  # has a k value

    if len(valid_k) >= 4:
        r_work_k, p_work_k = stats.spearmanr(valid_k["workload_score"], valid_k["k"])
        r_susp_k, p_susp_k = stats.spearmanr(valid_k["suspension_frac"], valid_k["k"])
        r_cut_k, p_cut_k = stats.spearmanr(valid_k["cutting_frac"], valid_k["k"])
        r_bias_k, p_bias_k = stats.spearmanr(valid_k["directional_bias"], valid_k["k"])

        print(f"  Workload score vs k: r={r_work_k:.3f}, p={p_work_k:.3f}")
        print(f"  Suspension frac vs k: r={r_susp_k:.3f}, p={p_susp_k:.3f}")
        print(f"  Cutting frac vs k: r={r_cut_k:.3f}, p={p_cut_k:.3f}")
        print(f"  Directional bias vs k: r={r_bias_k:.3f}, p={p_bias_k:.3f}")

        h4_confirmed = abs(r_work_k) > 0.5 or abs(r_susp_k) > 0.5 or abs(r_cut_k) > 0.5
        print(f"  H4 {'CONFIRMED' if h4_confirmed else 'NOT CONFIRMED'} "
              f"(need any |r| > 0.5)")
    else:
        h4_confirmed = False
        print("  Insufficient patients with k values")

    # ===== Summary and composite score =====
    print(f"\n{'=' * 70}")
    print("WORKLOAD COMPOSITE ANALYSIS")
    print(f"{'=' * 70}")

    sdf_sorted = sdf.sort_values("workload_score", ascending=False)
    print(f"\n  {'Patient':<12} {'Workload':>8} {'TIR':>8} {'Susp%':>8} {'Bias':>8} "
          f"{'Classify'}")
    print(f"  {'-'*65}")
    for _, r in sdf_sorted.iterrows():
        wl = r["workload_score"]
        if wl > 0.5:
            cls = "HIGH WORKLOAD"
        elif wl > 0.3:
            cls = "MODERATE"
        else:
            cls = "LOW (good)"
        print(f"  {r['patient_id']:<12} {wl:>8.3f} {r['tir']:>8.1%} "
              f"{r['suspension_frac']:>8.1%} {r['directional_bias']:>+8.2f} {cls}")

    # Save results
    output = {
        "experiment": "EXP-2593",
        "title": "Loop Workload as Settings Quality Metric",
        "h1_confirmed": h1_confirmed,
        "h2_confirmed": h2_confirmed,
        "h3_confirmed": h3_confirmed,
        "h4_confirmed": h4_confirmed,
        "correlations": {
            "workload_vs_tir": {"r": r_work_tir, "p": p_work_tir},
            "suspension_vs_tir": {"r": r_susp_tir, "p": p_susp_tir},
        },
        "summary": sdf.drop(columns=["hourly_profile"], errors="ignore").to_dict(orient="records"),
    }
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTFILE, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {OUTFILE}")


if __name__ == "__main__":
    main()
