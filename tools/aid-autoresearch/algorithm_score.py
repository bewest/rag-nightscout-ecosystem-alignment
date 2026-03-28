#!/usr/bin/env python3
"""
AID Algorithm Scoring Function.

Composite metric (0.0 to 1.0, higher is better) for evaluating AID algorithms
against t1pal conformance vectors. Adapted from t1pal AUTORESEARCH-AID-RECOMMENDATIONS §2.3.

Safety boundary violations are a hard gate → score = 0.0.

Supports two data sources:
  1. xval vectors (simplified boundary + unit tests) via validate_oref0.py
  2. End-to-end TV-* vectors (100 real captures) via run-oref0-endtoend.js

Usage:
    python3 tools/aid-autoresearch/algorithm_score.py --runner oref0
    python3 tools/aid-autoresearch/algorithm_score.py --runner oref0 --json
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


def compute_score(boundary_results, endtoend_results):
    """
    Compute composite AID algorithm score (0.0 to 1.0, higher is better).
    Returns 0.0 immediately if any safety boundary is violated.
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

    e2e_total = e2e_summary.get("total", 0)
    e2e_pass = e2e_summary.get("pass", 0)
    pass_rate = e2e_pass / max(e2e_total, 1)

    # Rate divergence (agreement metric)
    rate_diffs = []
    ebg_diffs = []
    for r in e2e_results:
        diffs = r.get("diffs", {})
        if "rate" in diffs and diffs["rate"].get("diff") is not None:
            rate_diffs.append(diffs["rate"]["diff"])
        if "eventualBG" in diffs and diffs["eventualBG"].get("diff") is not None:
            ebg_diffs.append(diffs["eventualBG"]["diff"])

    mean_rate_div = sum(rate_diffs) / max(len(rate_diffs), 1) if rate_diffs else 1.0
    mean_ebg_mae = sum(ebg_diffs) / max(len(ebg_diffs), 1) if ebg_diffs else 50.0

    MAX_DIVERGENCE = 2.0  # U/hr (scaled for synthetic IOB array limitation)
    MAX_MAE = 50.0        # mg/dL (eventualBG prediction)

    agreement = max(0, 1 - mean_rate_div / MAX_DIVERGENCE)
    prediction = max(0, 1 - mean_ebg_mae / MAX_MAE)

    # Simplicity bonus — baseline (1.0 = maximum simplicity)
    simplicity = 0.5

    score = (
        0.30 * agreement +      # Agreement with reference rate decisions
        0.30 * prediction +      # eventualBG prediction accuracy
        0.30 * pass_rate +       # Strict conformance pass rate
        0.10 * simplicity        # Simplicity bonus
    )

    return {
        "score": round(score, 6),
        "safety_ok": True,
        "components": {
            "agreement": round(agreement, 4),
            "prediction": round(prediction, 4),
            "pass_rate": round(pass_rate, 4),
            "simplicity": round(simplicity, 4),
            "mean_rate_div_u_hr": round(mean_rate_div, 4),
            "mean_ebg_mae_mgdl": round(mean_ebg_mae, 4),
            "boundary_pass": boundary_pass,
            "boundary_total": boundary_total,
            "e2e_pass": e2e_pass,
            "e2e_total": e2e_total,
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Score AID algorithm against conformance vectors")
    parser.add_argument("--runner", default="oref0", help="Algorithm runner name (oref0)")
    parser.add_argument("--vectors", default="conformance/t1pal", help="Path to conformance vectors")
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    args = parser.parse_args()

    print(f"Scoring {args.runner}...", file=sys.stderr)

    # Run both vector suites
    boundary_results = run_boundary_vectors(args.vectors)
    endtoend_results = run_endtoend_vectors()

    if boundary_results is None and endtoend_results is None:
        print("ERROR: Both runners produced no results", file=sys.stderr)
        sys.exit(1)

    score_result = compute_score(boundary_results, endtoend_results)

    if args.json:
        print(json.dumps(score_result, indent=2))
    else:
        s = score_result
        safety = "✅ PASS" if s["safety_ok"] else "❌ FAIL"
        print(f"\n{'='*50}")
        print(f"Algorithm Score: {s['score']:.4f} / 1.0000")
        print(f"Safety: {safety}")
        if s.get("reason"):
            print(f"  Reason: {s['reason']}")
        if s.get("components"):
            c = s["components"]
            print(f"  Agreement:     {c['agreement']:.4f} (rate div: {c.get('mean_rate_div_u_hr', 0):.4f} U/hr)")
            print(f"  Prediction:    {c['prediction']:.4f} (eBG MAE: {c.get('mean_ebg_mae_mgdl', 0):.1f} mg/dL)")
            print(f"  Conformance:   {c['pass_rate']:.4f} ({c.get('e2e_pass', 0)}/{c.get('e2e_total', 0)} vectors)")
            print(f"  Simplicity:    {c['simplicity']:.4f}")
            print(f"  Boundary:      {c['boundary_pass']}/{c['boundary_total']}")
        print(f"{'='*50}")


if __name__ == "__main__":
    main()
