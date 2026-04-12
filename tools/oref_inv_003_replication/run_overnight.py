#!/usr/bin/env python3
"""
Overnight full-data run: training (full SHAP) + verification set validation.

Runs EXP-2401 and EXP-2421 on both training and verification datasets
with full (unsampled) SHAP values to test temporal stability and
maximize statistical power.

Usage:
    PYTHONPATH=tools nohup python3 -m oref_inv_003_replication.run_overnight \
        2>&1 | tee overnight_run.log &

Estimated wall time: 12-18 hours on CPU.

Steps:
  1. EXP-2401 on training  (full SHAP, ~667K rows)   ~6-7h
  2. EXP-2401 on verification (full SHAP, ~400K rows) ~4-5h
  3. EXP-2421 on training  (50K interaction sample)    ~2-3h
  4. EXP-2421 on verification (50K interaction sample)  ~2-3h
  5. Comparison report: training vs verification stability

Progress is logged to stdout with timestamps, ETA, and memory usage.
"""

import json
import os
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _mem_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


TRAINING_PATH = "externals/ns-parquet/training"
VERIFICATION_PATH = "externals/ns-parquet/verification"
RESULTS_DIR = Path("externals/experiments")

STEPS = [
    {
        "name": "EXP-2401 training (full SHAP)",
        "module": "oref_inv_003_replication.exp_repl_2401",
        "args": [
            "--figures",
            "--data-path", TRAINING_PATH,
            "--shap-rows", "0",       # 0 = use ALL rows
            "--label", "full_train",
        ],
    },
    {
        "name": "EXP-2401 verification (full SHAP)",
        "module": "oref_inv_003_replication.exp_repl_2401",
        "args": [
            "--figures",
            "--data-path", VERIFICATION_PATH,
            "--shap-rows", "0",
            "--label", "verification",
        ],
    },
    {
        "name": "EXP-2421 training (50K interactions)",
        "module": "oref_inv_003_replication.exp_repl_2421",
        "args": [
            "--figures",
            "--data-path", TRAINING_PATH,
            "--shap-rows", "50000",
            "--label", "full_train",
        ],
    },
    {
        "name": "EXP-2421 verification (50K interactions)",
        "module": "oref_inv_003_replication.exp_repl_2421",
        "args": [
            "--figures",
            "--data-path", VERIFICATION_PATH,
            "--shap-rows", "50000",
            "--label", "verification",
        ],
    },
]


def run_step(step, step_num, total):
    """Run one experiment step as a subprocess, streaming output."""
    cmd = [
        sys.executable, "-m", step["module"],
        *step["args"],
    ]
    env = {**os.environ, "PYTHONPATH": "tools"}

    print(f"\n{'#' * 70}")
    print(f"# STEP {step_num}/{total}: {step['name']}")
    print(f"# Started: {_ts()}")
    print(f"# Command: {' '.join(cmd)}")
    print(f"{'#' * 70}\n")
    sys.stdout.flush()

    t0 = time.monotonic()
    proc = subprocess.run(
        cmd,
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    elapsed = time.monotonic() - t0
    h, m = int(elapsed // 3600), int((elapsed % 3600) // 60)

    status = "✅ SUCCESS" if proc.returncode == 0 else f"❌ FAILED (rc={proc.returncode})"
    print(f"\n{'─' * 70}")
    print(f"  {status}: {step['name']}  wall={h}h{m:02d}m")
    print(f"  Finished: {_ts()}")
    print(f"{'─' * 70}\n")
    sys.stdout.flush()

    return {
        "name": step["name"],
        "returncode": proc.returncode,
        "wall_time_s": round(elapsed, 1),
    }


def compare_results():
    """Compare training vs verification results for temporal stability."""
    print(f"\n{'#' * 70}")
    print(f"# STEP 5/5: Temporal Stability Comparison")
    print(f"# Started: {_ts()}")
    print(f"{'#' * 70}\n")

    try:
        import pandas as pd
        from scipy.stats import spearmanr

        # Load training and verification EXP-2401 results
        train_path = RESULTS_DIR / "exp_2401_replication_full_train.json"
        verify_path = RESULTS_DIR / "exp_2401_replication_verification.json"

        if not train_path.exists() or not verify_path.exists():
            print("  ⚠️  Missing result files, skipping comparison")
            return {"status": "skipped", "reason": "missing files"}

        with open(train_path) as f:
            train = json.load(f)
        with open(verify_path) as f:
            verify = json.load(f)

        report_lines = [
            "# Temporal Stability: Training vs Verification",
            "",
            f"**Generated**: {_ts()}",
            "",
            "## SHAP Feature Importance Stability",
            "",
            "| Target | Train→Verify ρ | p-value | Interpretation |",
            "|--------|----------------|---------|----------------|",
        ]

        stability = {}
        for target in ["hypo", "hyper"]:
            t_shap = train.get("exp_2401", {}).get("shap", {}).get(target, {})
            v_shap = verify.get("exp_2401", {}).get("shap", {}).get(target, {})

            if not t_shap or not v_shap:
                continue

            common = sorted(set(t_shap.keys()) & set(v_shap.keys()))
            t_vals = [t_shap[f] for f in common]
            v_vals = [v_shap[f] for f in common]

            rho, p = spearmanr(t_vals, v_vals)
            stability[target] = {"rho": round(rho, 4), "p": round(p, 6)}

            interp = ("Strong" if rho > 0.7 else
                      "Moderate" if rho > 0.4 else "Weak")
            report_lines.append(
                f"| {target} | {rho:.3f} | {p:.4f} | {interp} stability |"
            )
            print(f"  {target}: train↔verify ρ={rho:.3f} (p={p:.4f}) — "
                  f"{interp} stability")

        # Compare top-5 overlap
        report_lines.extend(["", "## Top-5 Feature Overlap", ""])
        for target in ["hypo", "hyper"]:
            t_shap = train.get("exp_2401", {}).get("shap", {}).get(target, {})
            v_shap = verify.get("exp_2401", {}).get("shap", {}).get(target, {})
            if not t_shap or not v_shap:
                continue
            t_top5 = set(sorted(t_shap, key=t_shap.get, reverse=True)[:5])
            v_top5 = set(sorted(v_shap, key=v_shap.get, reverse=True)[:5])
            overlap = t_top5 & v_top5
            report_lines.append(
                f"- **{target}**: {len(overlap)}/5 overlap — "
                f"train={sorted(t_top5)}, verify={sorted(v_top5)}"
            )
            stability[f"{target}_top5_overlap"] = len(overlap)
            print(f"  {target} top-5 overlap: {len(overlap)}/5")

        # Compare interaction results if available
        train_int = RESULTS_DIR / "exp_2421_cr_hour_full_train.json"
        verify_int = RESULTS_DIR / "exp_2421_cr_hour_verification.json"

        if train_int.exists() and verify_int.exists():
            with open(train_int) as f:
                t_int = json.load(f)
            with open(verify_int) as f:
                v_int = json.load(f)

            t_rank = t_int.get("exp_2421", {}).get("cr_hour_rank")
            v_rank = v_int.get("exp_2421", {}).get("cr_hour_rank")
            if t_rank and v_rank:
                report_lines.extend([
                    "", "## CR×hour Interaction Stability", "",
                    f"- Training: CR×hour rank #{t_rank}",
                    f"- Verification: CR×hour rank #{v_rank}",
                    f"- Stable: {'Yes' if abs(t_rank - v_rank) <= 3 else 'No'} "
                    f"(Δ={abs(t_rank - v_rank)})",
                ])
                stability["cr_hour_rank_train"] = t_rank
                stability["cr_hour_rank_verify"] = v_rank
                print(f"  CR×hour rank: train=#{t_rank}, verify=#{v_rank}")

        # Save stability report
        report_path = Path(
            "tools/oref_inv_003_replication/reports/temporal_stability_report.md"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(report_lines) + "\n")
        print(f"\n  Report: {report_path}")

        # Save stability JSON
        stab_path = RESULTS_DIR / "exp_temporal_stability.json"
        with open(stab_path, "w") as f:
            json.dump(stability, f, indent=2)
        print(f"  JSON: {stab_path}")

        return stability

    except Exception as e:
        print(f"  ❌ Comparison failed: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


def main():
    overall_start = time.monotonic()
    print(f"{'=' * 70}")
    print(f"  OVERNIGHT FULL-DATA RUN")
    print(f"  Started: {_ts()}")
    print(f"  Training: {TRAINING_PATH}")
    print(f"  Verification: {VERIFICATION_PATH}")
    print(f"  Steps: {len(STEPS) + 1} (4 experiments + 1 comparison)")
    print(f"{'=' * 70}")
    sys.stdout.flush()

    step_results = []
    for i, step in enumerate(STEPS, 1):
        result = run_step(step, i, len(STEPS) + 1)
        step_results.append(result)

        # Progress summary after each step
        wall_so_far = time.monotonic() - overall_start
        h, m = int(wall_so_far // 3600), int((wall_so_far % 3600) // 60)
        done = i
        remaining = len(STEPS) + 1 - done
        avg_per_step = wall_so_far / done
        eta = avg_per_step * remaining
        eta_h, eta_m = int(eta // 3600), int((eta % 3600) // 60)
        print(f"  📊 Progress: {done}/{len(STEPS)+1} steps  "
              f"elapsed={h}h{m:02d}m  ETA≈{eta_h}h{eta_m:02d}m")
        sys.stdout.flush()

        if result["returncode"] != 0:
            print(f"  ⚠️  Step failed — continuing with remaining steps")

    # Step 5: Comparison
    stability = compare_results()
    step_results.append({
        "name": "Temporal Stability Comparison",
        "returncode": 0,
        "stability": stability,
    })

    # Final summary
    overall_wall = time.monotonic() - overall_start
    h, m = int(overall_wall // 3600), int((overall_wall % 3600) // 60)
    print(f"\n{'=' * 70}")
    print(f"  OVERNIGHT RUN COMPLETE")
    print(f"  Finished: {_ts()}")
    print(f"  Total wall time: {h}h{m:02d}m")
    print(f"{'=' * 70}")
    print()

    for r in step_results:
        status = "✅" if r.get("returncode", 0) == 0 else "❌"
        wall = r.get("wall_time_s", 0)
        wh, wm = int(wall // 3600), int((wall % 3600) // 60)
        print(f"  {status} {r['name']}: {wh}h{wm:02d}m")

    # Save manifest
    manifest = {
        "started": _ts(),
        "total_wall_time_s": round(overall_wall, 1),
        "steps": step_results,
    }
    manifest_path = RESULTS_DIR / "overnight_run_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\n  Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
