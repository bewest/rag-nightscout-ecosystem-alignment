#!/usr/bin/env python3
import re
import json
import glob
from pathlib import Path

def find_experiment_json(exp_id):
    """Find JSON file for experiment ID"""
    # Extract numeric part
    num = exp_id.replace('exp-', '').replace('exp', '').split('-')[0]
    
    patterns = [
        f"externals/experiments/{exp_id}.json",
        f"externals/experiments/{exp_id}_*.json",
        f"externals/experiments/exp-{num}*.json",
        f"externals/experiments/exp{num}*.json",
        f"externals/experiments/EXP-{num}.json",
    ]
    
    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            return files[0]
    return None

def extract_numbers(content):
    """Extract all floating point and integer numbers from text"""
    return re.findall(r'[\d.]+', content)

def extract_table_rows(content):
    """Extract table-like content with patient identifiers"""
    # Look for patterns like "Patient A: value" or "a:" followed by numbers
    rows = re.findall(r'(?:Patient\s+)?([a-zA-Z0-9_]+)[\s:]*[\|\-]?\s*([\d.]+(?:\s*±\s*[\d.]+)?)', content)
    return rows

def load_json_safe(json_path):
    """Load JSON safely"""
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except:
        return None

def cross_check_numbers(report_content, json_data, exp_id):
    """Check if report numbers match JSON data"""
    issues = []
    
    if not json_data:
        return issues
    
    # Extract numbers from both
    report_nums = extract_numbers(report_content[:5000])  # First 5000 chars
    
    # Check if JSON has numerical data
    json_str = json.dumps(json_data)
    json_nums = set(extract_numbers(json_str))
    
    # Spot check: if report mentions specific numbers, verify they exist in JSON
    # Look for patterns like "R² = 0.485" or "MAE = 23.34"
    metrics = re.findall(r'(?:R²|R2|r2|MAE|mae|RMSE|rmse)\s*=?\s*([\d.]+)', report_content)
    
    for metric_val in metrics[:3]:  # Check first 3 metrics
        if metric_val not in json_nums:
            issues.append(f"Report claims metric value {metric_val} not found in JSON data")
    
    # Check for "all patients" claims
    if 'all patients' in report_content.lower():
        if isinstance(json_data, dict) and 'per_patient' in json_data:
            patients = json_data['per_patient']
            if isinstance(patients, dict):
                # Check if there are excluded patients mentioned
                if len(patients) < 11 and 'excluded' not in report_content.lower():
                    issues.append(f"Claims all patients but JSON shows {len(patients)} patients")
    
    return issues

def verify_report_detailed(report_path):
    """Deep verification of a single report"""
    result = {
        'file': report_path.name,
        'exp_id': None,
        'status': 'UNKNOWN',
        'issues': []
    }
    
    try:
        with open(report_path, 'r') as f:
            content = f.read()
        
        # Extract primary EXP ID
        match = re.search(r'(?:EXP|exp)-?(\d+)', content)
        if match:
            result['exp_id'] = f"exp-{match.group(1)}"
        else:
            result['status'] = 'REJECT'
            result['issues'].append('No EXP ID found')
            return result
        
        # Find JSON file
        json_path = find_experiment_json(result['exp_id'])
        json_data = None
        
        if json_path:
            json_data = load_json_safe(json_path)
            if not json_data:
                result['issues'].append(f"JSON file exists but cannot be parsed: {json_path}")
            else:
                # Cross-check numbers
                check_issues = cross_check_numbers(content, json_data, result['exp_id'])
                result['issues'].extend(check_issues)
        else:
            result['issues'].append(f'No JSON file found for {result['exp_id']}')
        
        # Red flag checks
        if 'all patients' in content.lower() and 'excluded' not in content.lower():
            if 'n=' not in content and 'patients' in content.lower():
                result['issues'].append('Claims "all patients" without clear sample size')
        
        if re.search(r'negative\s+(?:improvement|effect|gain|benefit)', content, re.IGNORECASE):
            result['issues'].append('Suspicious phrase: "negative improvement"')
        
        # Determine status
        if not result['issues']:
            result['status'] = 'PASS'
        elif len(result['issues']) == 1 and 'Cannot be parsed' in result['issues'][0]:
            result['status'] = 'PASS'  # JSON file issue, not report issue
        elif len(result['issues']) <= 2:
            result['status'] = 'NEEDS FIX'
        else:
            result['status'] = 'REJECT'
            
    except Exception as e:
        result['status'] = 'REJECT'
        result['issues'].append(f'Exception: {str(e)[:50]}')
    
    return result

# Main
if __name__ == '__main__':
    report_dir = Path('docs/60-research')
    reports = [
        'therapy-actionable-recommendations-report-2026-04-10.md',
        'therapy-advanced-analytics-report-2026-04-10.md',
        'therapy-advanced-report-2026-04-10.md',
        'therapy-aid-diagnostics-report-2026-04-10.md',
        'therapy-assessment-deconfounded-report-2026-04-10.md',
        'therapy-clinical-decision-support-report-2026-04-10.md',
        'therapy-clinical-translation-report-2026-04-10.md',
        'therapy-comprehensive-campaign-report-2026-04-10.md',
        'therapy-deployment-readiness-report-2026-04-10.md',
        'therapy-detection-report-2026-04-10.md',
        'therapy-dia-multiblock-report-2026-04-10.md',
        'therapy-extended-horizons-report-2026-04-10.md',
        'therapy-intervention-stability-report-2026-04-10.md',
        'therapy-isf-deconfounding-report-2026-04-10.md',
        'therapy-operationalization-report-2026-04-10.md',
        'therapy-optimization-report-2026-04-10.md',
        'therapy-pipeline-validation-report-2026-04-10.md',
        'therapy-practical-implementation-report-2026-04-10.md',
        'therapy-production-pipeline-report-2026-04-10.md',
        'therapy-profiles-report-2026-04-10.md',
        'therapy-synthesis-report-2026-04-10.md',
        'therapy-tbr-safety-report-2026-04-10.md',
        'therapy-uam-aware-report-2026-04-10.md',
        'transfer-learning-and-window-asymmetry-report-2026-04-10.md',
        'uam-morning-optimization-report-2026-04-10.md',
        'uniform-averaging-features-report-2026-04-10.md',
        'variability-decomposition-report-2026-04-10.md',
        'window-optimization-and-limits-report-2026-04-10.md',
        'winner-stacking-production-report-2026-04-10.md',
    ]
    
    results = []
    for report in reports:
        report_path = report_dir / report
        if report_path.exists():
            result = verify_report_detailed(report_path)
            results.append(result)
    
    # Print formatted output
    print("\nDETAILED VERIFICATION RESULTS")
    print("=" * 100)
    
    for i, r in enumerate(results, 1):
        print(f"\n{i:2d}. {r['file']}")
        print(f"    Status: {r['status']:12s} | EXP: {r['exp_id']}")
        if r['issues']:
            for issue in r['issues']:
                print(f"    - {issue}")
    
    # Summary
    stats = {'PASS': 0, 'NEEDS FIX': 0, 'REJECT': 0, 'UNKNOWN': 0}
    for r in results:
        stats[r['status']] += 1
    
    print("\n" + "=" * 100)
    print(f"SUMMARY: Pass={stats['PASS']} | Needs Fix={stats['NEEDS FIX']} | Reject={stats['REJECT']} | Unknown={stats['UNKNOWN']}")

