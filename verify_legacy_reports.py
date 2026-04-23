#!/usr/bin/env python3
"""Verify legacy research reports against backing data."""

import os
import re
import json
import glob
from pathlib import Path
from collections import defaultdict

# Reports to verify
REPORTS = [
    "alert-filtering-report.md",
    "autotune-uam-characterization-report.md",
    "capability-report-clinical-decision-support.md",
    "capability-report-data-quality.md",
    "capability-report-event-detection.md",
    "capability-report-glucose-forecasting.md",
    "capability-report-hypoglycemia-prediction.md",
    "capability-report-pattern-drift.md",
    "capability-report-realtime-operations.md",
    "capability-report-transfer-learning.md",
    "confidence-intervals-report.md",
    "digital-twin-forward-sim-report.md",
    "digital-twin-integrated-report.md",
    "digital-twin-milestone-1-2-report.md",
    "digital-twin-phase2-report.md",
    "event-aware-pipeline-integration-report.md",
    "fidelity-therapy-assessment-report.md",
    "gen2-baseline-report.md",
    "gen2-initial-experiences-report.md",
    "gen3-transition-report.md",
    "gen4-regularization-report.md",
    "hindcast-inference-report.md",
    "hindcast-model-capabilities-report.md",
    "isf-aid-feedback-report.md",
    "meal-response-clustering-report.md",
    "ml-experiment-progress-report.md",
    "mongodb-update-readiness-report.md",
    "multi-objective-validation-report.md",
    "natural-experiments-settings-optimization-report.md",
    "overnight-experiment-report-phase18.md",
    "settings-optimizer-productionization-report.md",
    "temporal-models-report.md",
]

REPORT_DIR = "/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/60-research"
EXPERIMENTS_DIR = "/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/experiments"

def extract_exp_ids(content):
    """Extract EXP-XXXX references from content."""
    pattern = r'EXP-(\d{3,4})'
    matches = re.findall(pattern, content)
    return [f"EXP-{m}" for m in matches]

def find_json_files(exp_id):
    """Find JSON files matching an EXP ID."""
    # Try multiple patterns
    exp_num = exp_id.replace("EXP-", "")
    
    patterns = [
        os.path.join(EXPERIMENTS_DIR, f"*{exp_num}*.json"),
        os.path.join(EXPERIMENTS_DIR, f"exp{exp_num}*.json"),
        os.path.join(EXPERIMENTS_DIR, f"experiment_{exp_num}*.json"),
    ]
    
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    
    return list(set(files))

def verify_report(report_name):
    """Verify a single report."""
    report_path = os.path.join(REPORT_DIR, report_name)
    
    verdict_info = {
        "report": report_name,
        "verdict": "PASS",
        "exp_ids": [],
        "json_found": False,
        "key_issues": [],
        "fixable": True,
    }
    
    try:
        with open(report_path, 'r') as f:
            content = f.read()
    except Exception as e:
        verdict_info["verdict"] = "REJECT"
        verdict_info["key_issues"].append(f"Cannot read report: {e}")
        verdict_info["fixable"] = False
        return verdict_info
    
    # Extract EXP IDs
    exp_ids = extract_exp_ids(content)
    verdict_info["exp_ids"] = list(set(exp_ids))
    
    # If no EXP IDs, mark as orphaned
    if not exp_ids:
        # Check if report has any numerical tables or claims requiring data
        if "patient" in content.lower() or "table" in content.lower():
            verdict_info["verdict"] = "NEEDS_FIX"
            verdict_info["key_issues"].append("No EXP IDs found but report contains patient/data tables")
            verdict_info["json_found"] = False
        else:
            # Pure conceptual report, no data verification needed
            verdict_info["json_found"] = False
        return verdict_info
    
    # Try to find JSON files for each EXP ID
    json_files_found = {}
    for exp_id in set(exp_ids):
        files = find_json_files(exp_id)
        if files:
            json_files_found[exp_id] = files
            verdict_info["json_found"] = True
    
    # If EXP IDs present but no JSON found, flag as orphaned
    if exp_ids and not json_files_found:
        verdict_info["verdict"] = "REJECT"
        verdict_info["key_issues"].append(f"References {len(set(exp_ids))} experiments but no JSON files found")
        verdict_info["fixable"] = False
        return verdict_info
    
    # Quick checks for common issues
    if "all patients" in content.lower() and len(set(exp_ids)) == 1:
        # Could be scope overstatement - check JSON
        exp_id = set(exp_ids)[0]
        if exp_id in json_files_found:
            json_file = json_files_found[exp_id][0]
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    # Check if it's actually all patients or subset
                    if isinstance(data, dict):
                        if "patient_count" in data and "total_patients" in data:
                            if data["patient_count"] < data["total_patients"]:
                                verdict_info["verdict"] = "NEEDS_FIX"
                                verdict_info["key_issues"].append(f"Scope issue: claims 'all patients' but {data['patient_count']} of {data['total_patients']} analyzed")
            except:
                pass
    
    return verdict_info

def main():
    """Main verification loop."""
    verified = []
    
    for report in sorted(REPORTS):
        print(f"Verifying {report}...")
        result = verify_report(report)
        verified.append(result)
    
    # Calculate summaries
    pass_count = sum(1 for r in verified if r["verdict"] == "PASS")
    needs_fix_count = sum(1 for r in verified if r["verdict"] == "NEEDS_FIX")
    reject_count = sum(1 for r in verified if r["verdict"] == "REJECT")
    
    # Categorize rejections
    error_cats = defaultdict(int)
    rejections = [r for r in verified if r["verdict"] == "REJECT"]
    for r in rejections:
        if not r["json_found"] and r["exp_ids"]:
            error_cats["orphaned_unverifiable"] += 1
        elif "Scope issue" in str(r["key_issues"]):
            error_cats["scope_issues"] += 1
        else:
            error_cats["other"] += 1
    
    # Build output
    output = {
        "total_reports": len(verified),
        "verified": verified,
        "summary": {
            "pass": pass_count,
            "needs_fix": needs_fix_count,
            "reject": reject_count,
            "error_categories": {
                "orphaned_unverifiable": error_cats.get("orphaned_unverifiable", 0),
                "fabrication": error_cats.get("fabrication", 0),
                "scope_issues": error_cats.get("scope_issues", 0),
                "method_mischaracterization": error_cats.get("method_mischaracterization", 0),
                "other": error_cats.get("other", 0),
            }
        },
        "top_5_rejections": [
            {"report": r["report"], "reason": r["key_issues"][0] if r["key_issues"] else "Unknown"}
            for r in sorted(rejections, key=lambda x: x["report"])[:5]
        ],
        "top_10_passes": [
            {"report": r["report"], "exp_ids": r["exp_ids"]}
            for r in sorted([r for r in verified if r["verdict"] == "PASS"], key=lambda x: x["report"])[:10]
        ]
    }
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
