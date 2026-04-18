#!/usr/bin/env python3
"""EXP-2662: Patience Mode Controller Simulation (Capstone)

Combines wall detection (EXP-2660) with controller modification:
1. Real-time wall detection: IOB > 2× median AND glucose ROC > -5
2. Patience mode: when wall detected, cap additional boluses (SMBs)
3. Replay full patient histories estimating glucose trajectory changes
4. Measure: whole-patient TIR, hypo rate, time-in-hyper

This is NOT a full glucose simulation (we don't have a validated forward
simulator for this). Instead, we estimate the insulin saved during wall
episodes and the glucose impact using ISF-based accounting.

Hypotheses:
  H1: Patience mode reduces delayed hypo rate ≥30% (whole-patient)
  H2: Time-in-hyper increases ≤10% (patience trades resolution speed for safety)
  H3: Total insulin decreases ≥5% (less waste)
  H4: Net TIR (70-180) improves ≥2pp (hypo reduction > hyper increase)
"""
import argparse
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

DEFAULT_GRID = Path("externals/ns-parquet/training/grid.parquet")
OUT = Path("externals/experiments/exp-2662_patience_mode.json")
MIN_READINGS = 288 * 14  # 14 days at 5-min intervals


def compute_baseline_metrics(glucose):
    """Compute TIR, hypo, hyper from glucose array."""
    valid = glucose[~np.isnan(glucose)]
    if len(valid) == 0:
        return {"tir": 0, "hypo": 0, "hyper": 0, "n": 0}
    return {
        "tir": float(np.mean((valid >= 70) & (valid <= 180))),
        "hypo": float(np.mean(valid < 70)),
        "hyper": float(np.mean(valid > 180)),
        "severe_hypo": float(np.mean(valid < 54)),
        "n": int(len(valid)),
        "mean": float(np.mean(valid)),
    }


def detect_wall_realtime(iob, glucose_roc, median_iob, threshold_ratio=2.0,
                         roc_threshold=-5.0):
    """Real-time wall detection signal.

    Returns boolean array: True when controller is hitting suppression wall.
    """
    wall = np.zeros(len(iob), dtype=bool)
    for j in range(len(iob)):
        if np.isnan(iob[j]) or np.isnan(glucose_roc[j]):
            continue
        if iob[j] > threshold_ratio * max(median_iob, 0.1):
            if glucose_roc[j] > roc_threshold:
                wall[j] = True
    return wall


def simulate_patience_mode(pdf, median_iob, cap_ratio=1.5):
    """Simulate patience mode on full patient history.

    When wall is detected:
    - Cap IOB at cap_ratio × median (prevent additional SMBs)
    - Estimate glucose change from prevented insulin

    Returns modified glucose estimate and metrics.
    """
    glucose = pdf["glucose"].values.copy()
    iob = pdf["iob"].values.copy()
    glucose_roc = pdf["glucose_roc"].values if "glucose_roc" in pdf.columns else np.full(len(pdf), 0.0)
    bolus_smb = pdf["bolus_smb"].values if "bolus_smb" in pdf.columns else np.zeros(len(pdf))
    isf = pdf["scheduled_isf"].values if "scheduled_isf" in pdf.columns else np.full(len(pdf), 50.0)

    wall = detect_wall_realtime(iob, glucose_roc, median_iob)

    # Track insulin prevented and glucose impact
    insulin_prevented = np.zeros(len(pdf))
    glucose_modified = glucose.copy()

    # When wall detected, SMBs delivered in that period are "prevented"
    # The glucose impact of prevented insulin manifests 2-6h later
    for j in range(len(pdf)):
        if wall[j]:
            smb = bolus_smb[j] if not np.isnan(bolus_smb[j]) else 0
            if smb > 0:
                insulin_prevented[j] = smb
                # This insulin would have lowered glucose by smb × ISF
                # over the next 2-6h. By preventing it, glucose stays higher
                # in the near term but avoids delayed hypo
                patient_isf = isf[j] if not np.isnan(isf[j]) else 50
                glucose_impact = smb * patient_isf

                # Distribute the "prevented drop" over next 2-6h (24-72 steps)
                # This prevents delayed hypo
                for k in range(j + 24, min(j + 72, len(pdf))):
                    glucose_modified[k] += glucose_impact / 48  # spread evenly

    return glucose_modified, wall, insulin_prevented


def main():
    parser = argparse.ArgumentParser(description="EXP-2662: Patience Mode Controller Simulation")
    parser.add_argument("--parquet", type=Path, default=DEFAULT_GRID,
                        help="Path to grid.parquet (default: %(default)s)")
    args = parser.parse_args()

    print("=" * 70)
    print("EXP-2662: Patience Mode Controller Simulation (Capstone)")
    print(f"  Data: {args.parquet}")
    print("=" * 70)

    if not args.parquet.exists():
        print(f"ERROR: {args.parquet} not found", file=sys.stderr)
        sys.exit(1)

    df = pd.read_parquet(args.parquet)
    all_patients = sorted(df["patient_id"].unique())
    print(f"  Found {len(all_patients)} patients in dataset")

    has_controller = "controller" in df.columns
    results = {}

    for pid in all_patients:
        pdf = df[df["patient_id"] == pid].sort_values("time").copy()

        # Minimum data guard: require at least 14 days
        if len(pdf) < MIN_READINGS:
            print(f"  {pid}: skipped (only {len(pdf)} readings, need {MIN_READINGS})")
            continue

        if "iob" not in pdf.columns or pdf["iob"].isna().all():
            print(f"  {pid}: skipped (no IOB data)")
            continue

        glucose = pdf["glucose"].values
        iob = pdf["iob"].values
        median_iob = float(np.nanmedian(iob))

        # Baseline metrics
        baseline = compute_baseline_metrics(glucose)

        # Simulate patience mode
        glucose_mod, wall, insulin_prevented = simulate_patience_mode(pdf, median_iob)

        # Modified metrics
        modified = compute_baseline_metrics(glucose_mod)

        # Wall statistics
        wall_pct = float(np.mean(wall)) * 100
        total_prevented = float(np.nansum(insulin_prevented))
        total_delivered = float(np.nansum(pdf["bolus_smb"].values)) if "bolus_smb" in pdf.columns else 0
        prevented_pct = total_prevented / max(total_delivered, 0.01) * 100

        # Delayed hypo analysis: count hypo events following wall periods
        # Delayed hypo = BG < 70 within 2-6h of a wall period
        delayed_hypo_baseline = 0
        delayed_hypo_modified = 0
        for j in range(len(pdf)):
            if wall[j]:
                for k in range(j + 24, min(j + 72, len(pdf))):
                    if not np.isnan(glucose[k]) and glucose[k] < 70:
                        delayed_hypo_baseline += 1
                        break
                for k in range(j + 24, min(j + 72, len(pdf))):
                    if not np.isnan(glucose_mod[k]) and glucose_mod[k] < 70:
                        delayed_hypo_modified += 1
                        break

        wall_periods = int(np.sum(wall))

        tag = "[ODC]" if pid.startswith("odc") else "[NS] "
        if has_controller:
            ctrl = pdf["controller"].dropna().mode()
            ctrl_tag = str(ctrl.iloc[0]) if len(ctrl) > 0 else "unknown"
            tag = f"[{ctrl_tag}]"
        print(f"\n  {tag} {pid} (N={baseline['n']}, median IOB={median_iob:.1f}U):")
        print(f"    Wall periods: {wall_pct:.1f}% of time ({wall_periods} readings)")
        print(f"    SMBs prevented: {total_prevented:.1f}U ({prevented_pct:.0f}% of total SMBs)")
        print(f"    Baseline: TIR={baseline['tir']:.1%}, Hypo={baseline['hypo']:.1%}, "
              f"Hyper={baseline['hyper']:.1%}")
        print(f"    Patience: TIR={modified['tir']:.1%}, Hypo={modified['hypo']:.1%}, "
              f"Hyper={modified['hyper']:.1%}")
        tir_delta = (modified['tir'] - baseline['tir']) * 100
        hypo_delta = (modified['hypo'] - baseline['hypo']) * 100
        hyper_delta = (modified['hyper'] - baseline['hyper']) * 100
        print(f"    Deltas: ΔTIR={tir_delta:+.1f}pp, ΔHypo={hypo_delta:+.1f}pp, "
              f"ΔHyper={hyper_delta:+.1f}pp")
        if delayed_hypo_baseline > 0:
            reduction = (1 - delayed_hypo_modified / delayed_hypo_baseline) * 100
            print(f"    Delayed hypos: {delayed_hypo_baseline} → {delayed_hypo_modified} "
                  f"({reduction:+.0f}% reduction)")

        results[pid] = {
            "n_readings": baseline["n"],
            "median_iob": float(median_iob),
            "wall_pct": float(wall_pct),
            "smb_prevented_u": float(total_prevented),
            "smb_prevented_pct": float(prevented_pct),
            "baseline": baseline,
            "patience": modified,
            "tir_delta_pp": float(tir_delta),
            "hypo_delta_pp": float(hypo_delta),
            "hyper_delta_pp": float(hyper_delta),
            "delayed_hypo_baseline": delayed_hypo_baseline,
            "delayed_hypo_patience": delayed_hypo_modified,
        }
        if has_controller:
            ctrl = pdf["controller"].dropna().mode()
            results[pid]["controller"] = str(ctrl.iloc[0]) if len(ctrl) > 0 else "unknown"

    # Hypothesis testing
    print("\n" + "=" * 70)
    print("HYPOTHESIS TESTING")
    print("=" * 70)

    patients = list(results.values())

    # H1: Patience mode reduces delayed hypo rate ≥30%
    total_baseline_hypo = sum(p["delayed_hypo_baseline"] for p in patients)
    total_patience_hypo = sum(p["delayed_hypo_patience"] for p in patients)
    hypo_reduction = (1 - total_patience_hypo / max(total_baseline_hypo, 1)) * 100
    h1 = hypo_reduction >= 30
    print(f"\n  H1: Delayed hypo reduction ≥30%")
    print(f"      {total_baseline_hypo} → {total_patience_hypo} ({hypo_reduction:+.0f}%)")
    print(f"      → {'PASS' if h1 else 'FAIL'}")

    # H2: Time-in-hyper increases ≤10%
    hyper_increases = [p["hyper_delta_pp"] for p in patients]
    max_hyper_increase = max(hyper_increases)
    mean_hyper_increase = np.mean(hyper_increases)
    h2 = mean_hyper_increase <= 10
    hyper_str = [f'{h:+.1f}pp' for h in hyper_increases]
    print(f"\n  H2: Time-in-hyper increase ≤10pp")
    print(f"      Mean: {mean_hyper_increase:+.1f}pp, Max: {max_hyper_increase:+.1f}pp")
    print(f"      Per-patient: {hyper_str}")
    print(f"      → {'PASS' if h2 else 'FAIL'}")

    # H3: Total insulin decreases ≥5%
    prevented_pcts = [p["smb_prevented_pct"] for p in patients]
    mean_prevented = np.mean(prevented_pcts)
    h3 = mean_prevented >= 5
    prevented_str = [f'{p:.0f}%' for p in prevented_pcts]
    print(f"\n  H3: SMB insulin reduction ≥5%")
    print(f"      Mean: {mean_prevented:.0f}%, Per-patient: {prevented_str}")
    print(f"      → {'PASS' if h3 else 'FAIL'}")

    # H4: Net TIR improves ≥2pp
    tir_deltas = [p["tir_delta_pp"] for p in patients]
    mean_tir = np.mean(tir_deltas)
    h4 = mean_tir >= 2
    tir_str = [f'{t:+.1f}pp' for t in tir_deltas]
    print(f"\n  H4: Net TIR improvement ≥2pp")
    print(f"      Mean: {mean_tir:+.1f}pp, Per-patient: {tir_str}")
    print(f"      → {'PASS' if h4 else 'FAIL'}")

    # Summary table
    print("\n" + "=" * 70)
    print("PATIENCE MODE SUMMARY")
    print("=" * 70)
    print(f"  {'Patient':<20} {'Wall%':>6} {'ΔTIR':>7} {'ΔHypo':>7} {'ΔHyper':>7} {'SMB Saved':>9}")
    for pid, r in results.items():
        print(f"  {pid:<20} {r['wall_pct']:>5.1f}% {r['tir_delta_pp']:>+6.1f}pp "
              f"{r['hypo_delta_pp']:>+6.1f}pp {r['hyper_delta_pp']:>+6.1f}pp "
              f"{r['smb_prevented_pct']:>7.0f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {OUT}")


if __name__ == "__main__":
    main()
