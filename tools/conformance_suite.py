#!/usr/bin/env python3
"""
Algorithm Conformance Suite Orchestrator

Runs all algorithm conformance runners and generates unified reports.

Usage:
    python tools/conformance_suite.py                    # Run all suites
    python tools/conformance_suite.py --runner oref0     # Run specific runner
    python tools/conformance_suite.py --ci               # CI mode (strict exit codes)
    python tools/conformance_suite.py --report-only      # Regenerate report from existing results

Runners:
    - oref0: JavaScript oref0 determine-basal (85 vectors)
    - aaps: Kotlin AAPS algorithm (not yet implemented)
    - loop: Swift Loop algorithm (not yet implemented)

Exit codes:
    0 - All tests pass (or --report-only)
    1 - Some tests failed
    2 - Configuration/runtime error
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).parent.parent
RUNNERS_DIR = WORKSPACE_ROOT / "conformance" / "runners"
RESULTS_DIR = WORKSPACE_ROOT / "conformance" / "results"
VECTORS_DIR = WORKSPACE_ROOT / "conformance" / "vectors"

# Runner configurations
RUNNERS = {
    "oref0": {
        "command": ["node", str(RUNNERS_DIR / "oref0-runner.js"), "--quiet"],
        "output": RESULTS_DIR / "oref0-results.json",
        "description": "oref0 determine-basal algorithm",
        "available": True,
    },
    "aaps": {
        "command": None,  # Not implemented
        "output": RESULTS_DIR / "aaps-results.json",
        "description": "AAPS algorithm variants",
        "available": False,
    },
    "loop": {
        "command": None,  # Not implemented
        "output": RESULTS_DIR / "loop-results.json",
        "description": "Loop algorithm",
        "available": False,
    },
}


def run_runner(name: str, config: dict, verbose: bool = False) -> dict | None:
    """Execute a conformance runner and return results."""
    if not config["available"]:
        print(f"  ⚠ {name}: Not yet implemented")
        return None
    
    command = config["command"]
    output_file = config["output"]
    
    print(f"  Running {name}...")
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=WORKSPACE_ROOT
        )
        
        if verbose and result.stdout:
            print(result.stdout)
        
        if result.returncode not in (0, 1):  # 0=pass, 1=some failures
            print(f"  ✗ {name}: Runner error (exit code {result.returncode})")
            if result.stderr:
                print(f"    {result.stderr[:200]}")
            return None
        
        # Load results
        if output_file.exists():
            with open(output_file) as f:
                return json.load(f)
        else:
            print(f"  ✗ {name}: No results file generated")
            return None
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ {name}: Timeout after 5 minutes")
        return None
    except Exception as e:
        print(f"  ✗ {name}: Error - {e}")
        return None


def load_existing_results(name: str, config: dict) -> dict | None:
    """Load existing results file without running."""
    output_file = config["output"]
    if output_file.exists():
        with open(output_file) as f:
            return json.load(f)
    return None


def aggregate_results(all_results: dict[str, dict]) -> dict:
    """Aggregate results from all runners into unified report."""
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runners": {},
        "totals": {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
        },
        "by_category": {},
    }
    
    for runner_name, results in all_results.items():
        if results is None:
            summary["runners"][runner_name] = {"status": "not_run"}
            continue
        
        # Extract summary from runner results
        runner_summary = results.get("summary", {})
        total = runner_summary.get("total", 0)
        passed = runner_summary.get("passed", 0)
        failed = runner_summary.get("failed", 0)
        
        summary["runners"][runner_name] = {
            "status": "completed",
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{(passed/total*100):.1f}%" if total > 0 else "N/A",
        }
        
        summary["totals"]["total_tests"] += total
        summary["totals"]["passed"] += passed
        summary["totals"]["failed"] += failed
        
        # Extract categories from runner results (oref0 format)
        categories = results.get("categories", {})
        for category, cat_data in categories.items():
            if category not in summary["by_category"]:
                summary["by_category"][category] = {"total": 0, "passed": 0, "failed": 0}
            
            cat_passed = cat_data.get("passed", 0)
            cat_failed = cat_data.get("failed", 0)
            summary["by_category"][category]["passed"] += cat_passed
            summary["by_category"][category]["failed"] += cat_failed
            summary["by_category"][category]["total"] += cat_passed + cat_failed
    
    # Calculate overall pass rate
    if summary["totals"]["total_tests"] > 0:
        summary["totals"]["pass_rate"] = f"{(summary['totals']['passed']/summary['totals']['total_tests']*100):.1f}%"
    else:
        summary["totals"]["pass_rate"] = "N/A"
    
    return summary


def generate_markdown_report(summary: dict) -> str:
    """Generate markdown report from aggregated results."""
    lines = [
        "# Algorithm Conformance Report",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Tests | {summary['totals']['total_tests']} |",
        f"| Passed | {summary['totals']['passed']} |",
        f"| Failed | {summary['totals']['failed']} |",
        f"| Pass Rate | {summary['totals']['pass_rate']} |",
        "",
        "## Runners",
        "",
        "| Runner | Status | Total | Passed | Failed | Pass Rate |",
        "|--------|--------|-------|--------|--------|-----------|",
    ]
    
    for runner_name, data in summary["runners"].items():
        if data.get("status") == "not_run":
            lines.append(f"| {runner_name} | ⚠ Not Run | - | - | - | - |")
        else:
            lines.append(
                f"| {runner_name} | ✓ Completed | "
                f"{data['total']} | {data['passed']} | {data['failed']} | {data['pass_rate']} |"
            )
    
    lines.extend(["", "## Results by Category", ""])
    
    if summary["by_category"]:
        lines.extend([
            "| Category | Total | Passed | Failed | Pass Rate |",
            "|----------|-------|--------|--------|-----------|",
        ])
        
        for category, data in sorted(summary["by_category"].items()):
            rate = f"{(data['passed']/data['total']*100):.0f}%" if data['total'] > 0 else "N/A"
            lines.append(
                f"| {category} | {data['total']} | {data['passed']} | {data['failed']} | {rate} |"
            )
    else:
        lines.append("No category breakdown available.")
    
    lines.extend([
        "",
        "## Failure Analysis",
        "",
    ])
    
    # Add failure breakdown if available
    if summary["totals"]["failed"] > 0:
        lines.append("See individual runner results for failure details:")
        lines.append("")
        for runner_name in summary["runners"]:
            lines.append(f"- `conformance/results/{runner_name}-results.json`")
    else:
        lines.append("**All tests passed!**")
    
    lines.extend([
        "",
        "---",
        "",
        "*Generated by `tools/conformance_suite.py`*",
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run algorithm conformance suite")
    parser.add_argument("--runner", choices=list(RUNNERS.keys()), help="Run specific runner only")
    parser.add_argument("--ci", action="store_true", help="CI mode (strict exit codes)")
    parser.add_argument("--report-only", action="store_true", help="Regenerate report from existing results")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Output JSON summary")
    args = parser.parse_args()
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Determine which runners to execute
    if args.runner:
        runners_to_run = {args.runner: RUNNERS[args.runner]}
    else:
        runners_to_run = RUNNERS
    
    print("Algorithm Conformance Suite")
    print("=" * 40)
    print()
    
    # Run or load results
    all_results: dict[str, Any] = {}
    
    for name, config in runners_to_run.items():
        if args.report_only:
            print(f"  Loading {name} results...")
            all_results[name] = load_existing_results(name, config)
        else:
            all_results[name] = run_runner(name, config, args.verbose)
    
    print()
    
    # Aggregate and report
    summary = aggregate_results(all_results)
    
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("Results Summary")
        print("-" * 40)
        print(f"Total: {summary['totals']['total_tests']} tests")
        print(f"Passed: {summary['totals']['passed']}")
        print(f"Failed: {summary['totals']['failed']}")
        print(f"Pass Rate: {summary['totals']['pass_rate']}")
    
    # Write reports
    json_report = RESULTS_DIR / "conformance-summary.json"
    with open(json_report, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote: {json_report}")
    
    md_report = RESULTS_DIR / "conformance-summary.md"
    with open(md_report, "w") as f:
        f.write(generate_markdown_report(summary))
    print(f"Wrote: {md_report}")
    
    # Exit code
    if args.ci and summary["totals"]["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
