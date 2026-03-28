#!/usr/bin/env python3
"""
AID Algorithm Scoring Function.

Composite metric (0.0 to 1.0, higher is better) for evaluating AID algorithms
against t1pal conformance vectors. Adapted from t1pal AUTORESEARCH-AID-RECOMMENDATIONS §2.3.

Safety boundary violations are a hard gate → score = 0.0.

Supports three data sources:
  1. xval vectors (safety boundary + unit tests) via validate_oref0.py
  2. End-to-end TV-* vectors (100 real captures) via run-oref0-endtoend.js
  3. Prediction trajectory comparison (captured vs reconstructed) via compare-predictions.js

The prediction comparison uses originalOutput.predBGs from TV-* vectors as
ground truth — these are the actual glucose trajectories the phone algorithm
produced, not our synthetic IOB reconstruction.

Usage:
    python3 tools/aid-autoresearch/algorithm_score.py --runner oref0
    python3 tools/aid-autoresearch/algorithm_score.py --runner oref0 --json

Trace: ALG-SCORE-001, REQ-060
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime, timezone


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_boundary_vectors(vectors_dir):
    """Run safety boundary vectors via validate_oref0.py."""
    runner_path = os.path.join(REPO_ROOT, "tools", "aid-autoresearch", "validate_oref0.py")
    result = subprocess.run(
        [sys.executable, runner_path, "--vectors", vectors_dir, "--json"],
        capture_output=True, text=True, timeout=300
    )
    output = result.stdout
    lines = output.split('\n')
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('{') and '"boundary"' in output[output.index(stripped):]:
            try:
                return json.loads('\n'.join(lines[i:]))
            except json.JSONDecodeError:
                pass
    return None


def run_endtoend_vectors():
    """Run end-to-end TV-* vectors via run-oref0-endtoend.js."""
    runner_path = os.path.join(REPO_ROOT, "tools", "aid-autoresearch", "run-oref0-endtoend.js")
    result = subprocess.run(
        ["node", runner_path, "--json"],
        capture_output=True, text=True, timeout=300
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def run_prediction_comparison():
    """Run trajectory comparison: captured predBGs vs reconstructed."""
    runner_path = os.path.join(REPO_ROOT, "tools", "aid-autoresearch", "compare-predictions.js")
    result = subprocess.run(
        ["node", runner_path, "--json"],
        capture_output=True, text=True, timeout=300
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def compute_score(boundary_results, endtoend_results, prediction_results=None):
    """
    Compute composite AID algorithm score (0.0 to 1.0, higher is better).
    Returns 0.0 immediately if any safety boundary is violated.

    Updated scoring (v2) incorporates prediction trajectory quality:
      25% decision agreement (rate divergence)
      25% prediction trajectory MAE (captured vs reconstructed predBGs)
      25% strict conformance pass rate
      15% trajectory direction agreement
      10% simplicity bonus
    """
    # --- Safety gate from boundary vectors ---
    b_summary = boundary_results.get("summary", {}) if boundary_results else {}
    boundary_pass = b_summary.get("boundary_pass", 0)
    boundary_total = b_summary.get("boundary_total", 1)
    safety_ok = b_summary.get("safety_ok", False)

    if not safety_ok:
        return {
            "score": 0.0,
            "safety_ok": False,
            "reason": f"Safety boundary failure: {boundary_pass}/{boundary_total}",
            "components": {}
        }

    # --- End-to-end scoring from TV-* vectors ---
    e2e = endtoend_results or {}
    e2e_summary = e2e.get("summary", {})
    e2e_results = e2e.get("results", [])

    e2e_total = e2e_summary.get("scored", e2e_summary.get("total", 0))
    e2e_pass = e2e_summary.get("pass", 0)
    e2e_skipped = e2e_summary.get("skipped", 0)
    pass_rate = e2e_pass / max(e2e_total, 1)

    # Rate divergence (decision agreement metric)
    rate_diffs = []
    for r in e2e_results:
        diffs = r.get("diffs", {})
        if "rate" in diffs and diffs["rate"].get("diff") is not None:
            rate_diffs.append(diffs["rate"]["diff"])

    mean_rate_div = sum(rate_diffs) / max(len(rate_diffs), 1) if rate_diffs else 1.0
    MAX_DIVERGENCE = 2.0  # U/hr
    agreement = max(0, 1 - mean_rate_div / MAX_DIVERGENCE)

    # --- Prediction trajectory scoring (NEW: from captured predBGs) ---
    pred = prediction_results or {}
    pred_summary = pred.get("summary", {})

    # Use trajectory MAE from compare-predictions.js
    avg_traj_mae = pred_summary.get("avgMae", 50.0) or 50.0
    avg_dir_agreement = pred_summary.get("avgDirAgreement", 0.5) or 0.5
    quality_score = pred_summary.get("qualityScore", 0.0) or 0.0

    MAX_TRAJ_MAE = 50.0  # mg/dL (trajectory prediction)
    prediction = max(0, 1 - avg_traj_mae / MAX_TRAJ_MAE)

    # Simplicity bonus — baseline oref0 (deterministic, interpretable)
    simplicity = 0.5

    # Composite with trajectory-aware weights
    score = (
        0.25 * agreement +          # Decision agreement (rate divergence)
        0.25 * prediction +          # Trajectory MAE (captured vs reconstructed)
        0.25 * pass_rate +           # Strict conformance pass rate
        0.15 * avg_dir_agreement +   # Trajectory direction agreement
        0.10 * simplicity            # Simplicity bonus
    )

    return {
        "score": round(score, 6),
        "safety_ok": True,
        "components": {
            "agreement": round(agreement, 4),
            "prediction": round(prediction, 4),
            "pass_rate": round(pass_rate, 4),
            "dir_agreement": round(avg_dir_agreement, 4),
            "simplicity": round(simplicity, 4),
            "mean_rate_div_u_hr": round(mean_rate_div, 4),
            "avg_traj_mae_mgdl": round(avg_traj_mae, 1),
            "quality_score": round(quality_score, 4),
            "boundary_pass": boundary_pass,
            "boundary_total": boundary_total,
            "e2e_pass": e2e_pass,
            "e2e_total": e2e_total,
            "e2e_skipped": e2e_skipped,
            "tiers": e2e_summary.get("tiers", {}),
            "pred_good": pred_summary.get("good", 0),
            "pred_fair": pred_summary.get("fair", 0),
            "pred_poor": pred_summary.get("poor", 0),
        }
    }


def append_results_tsv(score_result):
    """Append score to results.tsv tracking file."""
    tsv_path = os.path.join(REPO_ROOT, "tools", "aid-autoresearch", "results.tsv")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Get current git commit
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        commit = "unknown"

    s = score_result
    c = s.get("components", {})
    line = (
        f"{now}\t{commit}\t{s['score']:.4f}\t"
        f"{'PASS' if s['safety_ok'] else 'FAIL'}\t"
        f"{c.get('pass_rate', 0):.2f}\t"
        f"{c.get('avg_traj_mae_mgdl', 0):.1f}\t"
        f"{c.get('dir_agreement', 0):.3f}\t"
        f"active\tv2 scoring with captured predBGs trajectories"
    )

    with open(tsv_path, "a") as f:
        f.write(line + "\n")


def main():
    parser = argparse.ArgumentParser(description="Score AID algorithm against conformance vectors")
    parser.add_argument("--runner", default="oref0", help="Algorithm runner name (oref0)")
    parser.add_argument("--vectors", default="conformance/t1pal", help="Path to conformance vectors")
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    parser.add_argument("--no-record", action="store_true", help="Skip appending to results.tsv")
    args = parser.parse_args()

    print(f"Scoring {args.runner} (v2 with trajectory comparison)...", file=sys.stderr)

    # Run all three vector suites
    boundary_results = run_boundary_vectors(args.vectors)
    endtoend_results = run_endtoend_vectors()
    prediction_results = run_prediction_comparison()

    if boundary_results is None and endtoend_results is None:
        print("ERROR: Both runners produced no results", file=sys.stderr)
        sys.exit(1)

    score_result = compute_score(boundary_results, endtoend_results, prediction_results)

    if not args.no_record:
        append_results_tsv(score_result)

    if args.json:
        print(json.dumps(score_result, indent=2))
    else:
        s = score_result
        safety = "✅ PASS" if s["safety_ok"] else "❌ FAIL"
        print(f"\n{'='*55}")
        print(f"  Algorithm Score:   {s['score']:.4f} / 1.0000")
        print(f"  Safety:            {safety}")
        if s.get("reason"):
            print(f"  Reason:            {s['reason']}")
        if s.get("components"):
            c = s["components"]
            print(f"  ─────────────────────────────────────────")
            print(f"  Agreement:         {c['agreement']:.4f}  (rate div: {c.get('mean_rate_div_u_hr', 0):.3f} U/hr)")
            print(f"  Trajectory MAE:    {c['prediction']:.4f}  (avg: {c.get('avg_traj_mae_mgdl', 0):.1f} mg/dL)")
            print(f"  Conformance:       {c['pass_rate']:.4f}  ({c.get('e2e_pass', 0)}/{c.get('e2e_total', 0)} strict, {c.get('e2e_skipped', 0)} skipped)")
            print(f"  Direction:         {c['dir_agreement']:.4f}  (trajectory slope agreement)")
            print(f"  Simplicity:        {c['simplicity']:.4f}")
            print(f"  ─────────────────────────────────────────")
            print(f"  Boundary:          {c['boundary_pass']}/{c['boundary_total']}")
            print(f"  Predictions:       {c.get('pred_good', 0)} good / {c.get('pred_fair', 0)} fair / {c.get('pred_poor', 0)} poor")
            print(f"  Quality:           {c.get('quality_score', 0):.4f}")
            tiers = c.get("tiers", {})
            if tiers:
                print(f"  ─────────────────────────────────────────")
                print(f"  Tier: strict       {tiers.get('strict', {}).get('rate', 'N/A')}")
                print(f"  Tier: reasonable   {tiers.get('reasonable', {}).get('rate', 'N/A')}")
                print(f"  Tier: lax          {tiers.get('lax', {}).get('rate', 'N/A')}")
        print(f"{'='*55}")


if __name__ == "__main__":
    main()
