#!/usr/bin/env python3
"""
Accuracy Dashboard - Unified Verification Metrics

Aggregates results from verification tools to provide a single
accuracy report for the Nightscout Alignment Workspace.

Usage:
    python tools/accuracy_dashboard.py           # Human-readable
    python tools/accuracy_dashboard.py --json    # Machine-readable
    python tools/accuracy_dashboard.py --ci      # CI mode (exit code reflects status)

Implements: REQ-VERIFY-005 (Unified accuracy reporting)
"""

import subprocess
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# Tool configurations
TOOLS = {
    "refs": {
        "cmd": ["python3", "tools/verify_refs.py", "--json"],
        "description": "Reference validation (file paths, line anchors)",
        "key_metrics": ["total_refs", "valid", "refs_with_line_anchors", "line_anchors_valid"]
    },
    "coverage": {
        "cmd": ["python3", "tools/verify_coverage.py", "--json"],
        "description": "Requirement and gap coverage",
        "key_metrics": ["requirements.total", "requirements.full", "gaps.total", "gaps.addressed"]
    },
    "assertions": {
        "cmd": ["python3", "tools/verify_assertions.py", "--json"],
        "description": "Test assertion traceability",
        "key_metrics": ["total_assertions", "requirements_with_assertions", "gaps_with_assertions"]
    },
    "gap_freshness": {
        "cmd": ["python3", "tools/verify_gap_freshness.py", "--json"],
        "description": "Gap freshness (open vs addressed)",
        "key_metrics": ["total", "likely_open", "needs_review"]
    },
    "mapping_coverage": {
        "cmd": ["python3", "tools/verify_mapping_coverage.py", "--json"],
        "description": "Mapping document coverage",
        "key_metrics": ["total_files", "average_coverage"]
    }
}

# Thresholds for CI pass/fail
THRESHOLDS = {
    "refs_valid_pct": 80.0,      # % of refs that must be valid
    "line_anchors_valid_pct": 90.0,  # % of line anchors that must be valid
    "coverage_full_pct": 2.0,   # % of reqs with full coverage (realistic for early stage)
    "assertions_coverage_pct": 10.0  # % of reqs with assertions
}


def run_tool(name: str, config: dict) -> Optional[Dict[str, Any]]:
    """Run a verification tool and parse its JSON output."""
    import re
    try:
        result = subprocess.run(
            config["cmd"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # Extract JSON from output (tools may print progress before JSON)
        output = result.stdout
        json_start = output.find('{')
        if json_start == -1:
            return {"error": "No JSON in output", "raw": output[:500]}
        
        # Find matching closing brace for first JSON object
        json_str = output[json_start:]
        brace_count = 0
        end_pos = 0
        for i, char in enumerate(json_str):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i + 1
                    break
        
        if end_pos > 0:
            json_str = json_str[:end_pos]
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to extract just the summary section
            summary_match = re.search(r'"summary":\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', output)
            if summary_match:
                try:
                    summary = json.loads(summary_match.group(1))
                    return {"summary": summary}
                except:
                    pass
            return {"error": "JSON parse error", "raw": output[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "Timeout after 120s"}
    except Exception as e:
        return {"error": str(e)}


def get_nested(data: dict, path: str, default=None):
    """Get nested dictionary value by dot-separated path."""
    keys = path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def calculate_metrics(results: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate aggregate metrics from tool results."""
    metrics = {}
    
    # Refs metrics
    refs = results.get("refs", {})
    if "summary" in refs:
        s = refs["summary"]
        total = s.get("total_refs", 0)
        valid = s.get("valid", 0)
        line_total = s.get("refs_with_line_anchors", 0)
        line_valid = s.get("line_anchors_valid", 0)
        
        metrics["refs"] = {
            "total": total,
            "valid": valid,
            "valid_pct": round(valid / total * 100, 1) if total > 0 else 0,
            "line_anchors_total": line_total,
            "line_anchors_valid": line_valid,
            "line_anchors_valid_pct": round(line_valid / line_total * 100, 1) if line_total > 0 else 0
        }
    
    # Coverage metrics
    coverage = results.get("coverage", {})
    if "summary" in coverage:
        s = coverage["summary"]
        reqs = s.get("requirements", {})
        gaps = s.get("gaps", {})
        
        req_total = reqs.get("total", 0)
        req_full = reqs.get("full", 0)
        req_partial = reqs.get("partial", 0)
        
        metrics["coverage"] = {
            "requirements_total": req_total,
            "requirements_full": req_full,
            "requirements_partial": req_partial,
            "requirements_full_pct": round(req_full / req_total * 100, 1) if req_total > 0 else 0,
            "gaps_total": gaps.get("total", 0),
            "gaps_addressed": gaps.get("addressed", 0)
        }
    
    # Assertions metrics
    assertions = results.get("assertions", {})
    if "summary" in assertions:
        s = assertions["summary"]
        total_reqs = s.get("known_requirements", 0)
        reqs_with = s.get("requirements_with_assertions", 0)
        
        metrics["assertions"] = {
            "total_assertions": s.get("total_assertions", 0),
            "requirements_total": total_reqs,
            "requirements_with_assertions": reqs_with,
            "requirements_coverage_pct": round(reqs_with / total_reqs * 100, 1) if total_reqs > 0 else 0
        }
    
    # Gap freshness metrics
    freshness = results.get("gap_freshness", {})
    if "summary" in freshness:
        s = freshness["summary"]
        total = s.get("total", 0)
        likely_open = s.get("likely_open", 0)
        
        metrics["gap_freshness"] = {
            "total": total,
            "likely_open": likely_open,
            "needs_review": s.get("needs_review", 0),
            "open_pct": round(likely_open / total * 100, 1) if total > 0 else 0
        }
    
    # Mapping coverage metrics
    mapping = results.get("mapping_coverage", {})
    if "summary" in mapping:
        s = mapping["summary"]
        metrics["mapping"] = {
            "total_files": s.get("total_files", 0),
            "average_coverage": s.get("average_coverage", 0)
        }
    
    return metrics


def check_thresholds(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Check metrics against thresholds, return pass/fail status."""
    checks = {}
    all_passed = True
    
    # Refs valid percentage
    refs = metrics.get("refs", {})
    if refs:
        pct = refs.get("valid_pct", 0)
        passed = pct >= THRESHOLDS["refs_valid_pct"]
        checks["refs_valid"] = {
            "passed": passed,
            "value": pct,
            "threshold": THRESHOLDS["refs_valid_pct"],
            "message": f"Refs valid: {pct}% (threshold: {THRESHOLDS['refs_valid_pct']}%)"
        }
        if not passed:
            all_passed = False
        
        # Line anchors
        line_pct = refs.get("line_anchors_valid_pct", 0)
        passed = line_pct >= THRESHOLDS["line_anchors_valid_pct"]
        checks["line_anchors_valid"] = {
            "passed": passed,
            "value": line_pct,
            "threshold": THRESHOLDS["line_anchors_valid_pct"],
            "message": f"Line anchors valid: {line_pct}% (threshold: {THRESHOLDS['line_anchors_valid_pct']}%)"
        }
        if not passed:
            all_passed = False
    
    # Coverage full percentage
    coverage = metrics.get("coverage", {})
    if coverage:
        pct = coverage.get("requirements_full_pct", 0)
        passed = pct >= THRESHOLDS["coverage_full_pct"]
        checks["coverage_full"] = {
            "passed": passed,
            "value": pct,
            "threshold": THRESHOLDS["coverage_full_pct"],
            "message": f"Requirements fully covered: {pct}% (threshold: {THRESHOLDS['coverage_full_pct']}%)"
        }
        if not passed:
            all_passed = False
    
    # Assertions coverage
    assertions = metrics.get("assertions", {})
    if assertions:
        pct = assertions.get("requirements_coverage_pct", 0)
        passed = pct >= THRESHOLDS["assertions_coverage_pct"]
        checks["assertions_coverage"] = {
            "passed": passed,
            "value": pct,
            "threshold": THRESHOLDS["assertions_coverage_pct"],
            "message": f"Requirements with assertions: {pct}% (threshold: {THRESHOLDS['assertions_coverage_pct']}%)"
        }
        if not passed:
            all_passed = False
    
    return {
        "all_passed": all_passed,
        "checks": checks
    }


def format_human_readable(metrics: Dict[str, Any], status: Dict[str, Any]) -> str:
    """Format metrics as human-readable dashboard."""
    lines = []
    lines.append("=" * 60)
    lines.append("ACCURACY DASHBOARD - Nightscout Alignment Workspace")
    lines.append("=" * 60)
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    
    # Overall status
    if status["all_passed"]:
        lines.append("✅ OVERALL STATUS: PASSING")
    else:
        lines.append("❌ OVERALL STATUS: FAILING")
    lines.append("")
    
    # Refs section
    refs = metrics.get("refs", {})
    if refs:
        lines.append("📄 REFERENCES")
        lines.append(f"   Total: {refs['total']}")
        lines.append(f"   Valid: {refs['valid']} ({refs['valid_pct']}%)")
        lines.append(f"   Line anchors: {refs['line_anchors_valid']}/{refs['line_anchors_total']} ({refs['line_anchors_valid_pct']}%)")
        lines.append("")
    
    # Coverage section
    coverage = metrics.get("coverage", {})
    if coverage:
        lines.append("📊 COVERAGE")
        lines.append(f"   Requirements: {coverage['requirements_total']}")
        lines.append(f"   Full coverage: {coverage['requirements_full']} ({coverage['requirements_full_pct']}%)")
        lines.append(f"   Partial coverage: {coverage['requirements_partial']}")
        lines.append(f"   Gaps: {coverage['gaps_total']} ({coverage['gaps_addressed']} addressed)")
        lines.append("")
    
    # Assertions section
    assertions = metrics.get("assertions", {})
    if assertions:
        lines.append("🧪 ASSERTIONS")
        lines.append(f"   Total assertion groups: {assertions['total_assertions']}")
        lines.append(f"   Requirements with assertions: {assertions['requirements_with_assertions']} ({assertions['requirements_coverage_pct']}%)")
        lines.append("")
    
    # Gap freshness section
    freshness = metrics.get("gap_freshness", {})
    if freshness:
        lines.append("🔍 GAP FRESHNESS")
        lines.append(f"   Total gaps: {freshness['total']}")
        lines.append(f"   Likely open: {freshness['likely_open']} ({freshness['open_pct']}%)")
        lines.append(f"   Needs review: {freshness['needs_review']}")
        lines.append("")
    
    # Mapping section
    mapping = metrics.get("mapping", {})
    if mapping:
        lines.append("🗺️  MAPPING COVERAGE")
        lines.append(f"   Files: {mapping['total_files']}")
        lines.append(f"   Average coverage: {mapping['average_coverage']}%")
        lines.append("")
    
    # Threshold checks
    lines.append("-" * 60)
    lines.append("THRESHOLD CHECKS")
    lines.append("-" * 60)
    for name, check in status["checks"].items():
        icon = "✅" if check["passed"] else "❌"
        lines.append(f"   {icon} {check['message']}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Accuracy Dashboard")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--ci", action="store_true", help="CI mode (exit 1 if failing)")
    parser.add_argument("--quick", action="store_true", help="Skip slow tools")
    
    args = parser.parse_args()
    
    # Run tools
    results = {}
    tools_to_run = TOOLS.copy()
    
    if args.quick:
        # Skip slow tools in quick mode
        tools_to_run = {k: v for k, v in TOOLS.items() if k in ["refs", "assertions"]}
    
    for name, config in tools_to_run.items():
        if not args.json:
            print(f"Running {name}...", file=sys.stderr)
        results[name] = run_tool(name, config)
    
    # Calculate metrics
    metrics = calculate_metrics(results)
    
    # Check thresholds
    status = check_thresholds(metrics)
    
    # Output
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passing" if status["all_passed"] else "failing",
        "metrics": metrics,
        "thresholds": status,
        "raw_results": results
    }
    
    if args.json:
        print(json.dumps(output, indent=2, default=str))
    else:
        print(format_human_readable(metrics, status))
    
    # Exit code for CI
    if args.ci and not status["all_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
