#!/usr/bin/env python3
"""
Verify 167 research reports from Apr 1-14, 2026.
Checks for common errors: fabrication, attribution, counting, methods, scope.
"""

import json
import re
import os
import glob
from pathlib import Path
from collections import defaultdict

# Color codes for terminal output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'

class ReportVerifier:
    def __init__(self):
        self.reports = []
        self.results = {
            'PASS': [],
            'NEEDS_FIX': [],
            'REJECT': []
        }
        self.errors_by_category = defaultdict(list)
        self.experiments_cache = {}
        
    def find_reports(self):
        """Find all reports matching Apr 1-14 pattern."""
        patterns = [
            'docs/60-research/*report*-2026-04-0[1-9].md',
            'docs/60-research/*report*-2026-04-1[0-4].md'
        ]
        reports = []
        for pattern in patterns:
            reports.extend(sorted(glob.glob(pattern)))
        self.reports = sorted(set(reports))
        return self.reports
    
    def extract_exp_ids(self, content):
        """Extract EXP-NNNN IDs from report content."""
        # Look for EXP-NNNN pattern in headers and references
        matches = re.findall(r'EXP-(\d+)', content)
        return sorted(set(matches))
    
    def load_experiment(self, exp_num):
        """Load experiment JSON by ID."""
        if exp_num in self.experiments_cache:
            return self.experiments_cache[exp_num]
        
        # Try different patterns
        patterns = [
            f'externals/experiments/exp-{exp_num}_*.json',
            f'externals/experiments/{exp_num}_*.json',
        ]
        
        for pattern in patterns:
            files = glob.glob(pattern)
            if files:
                try:
                    with open(files[0], 'r') as f:
                        data = json.load(f)
                        self.experiments_cache[exp_num] = (files[0], data)
                        return self.experiments_cache[exp_num]
                except Exception as e:
                    pass
        
        return None, None
    
    def extract_statistics(self, content):
        """Extract numerical claims from report content."""
        stats = {}
        
        # Look for common patterns
        patterns = {
            'n_patients': r'(?:N\s*=\s*|patients\s*[:=]?\s*|n_patients\s*=\s*)(\d+)',
            'n_events': r'(?:events?\s*[:=]?\s*|n_events\s*=\s*)(\d+)',
            'percentage': r'(\d+(?:\.\d+)?)\s*%',
            'p_value': r'p\s*[<>=]\s*([\d.]+)',
            'mean_std': r'(\d+(?:\.\d+)?)\s*\(\s*±\s*([\d.]+)\s*\)',
        }
        
        for key, pattern in patterns.items():
            matches = re.findall(pattern, content)
            if matches:
                stats[key] = matches
        
        return stats
    
    def check_all_patients_claim(self, content):
        """Check if 'all patients' is claimed but not qualified."""
        all_patients_claims = re.findall(
            r'(all\s+patients|all\s+(?:\d+)\s+patients)',
            content, re.IGNORECASE
        )
        
        if all_patients_claims:
            # Check if there's exclusion criteria mentioned nearby
            exclusion_patterns = [
                r'(?:excluded|excluded)',
                r'(?:inclusion|exclusion)\s+criteria',
                r'(?:\d+)\s+(?:patients?|subjects?)\s+(?:excluded|removed|omitted)',
            ]
            
            for pattern in exclusion_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return 'QUALIFIED'  # Properly qualified
            
            return 'UNQUALIFIED'  # Potentially misleading
        
        return 'NONE'
    
    def verify_report(self, report_path, idx):
        """Verify a single report."""
        try:
            with open(report_path, 'r') as f:
                content = f.read()
        except Exception as e:
            self.results['REJECT'].append({
                'file': report_path,
                'reason': f'Cannot read file: {e}'
            })
            self.errors_by_category['FILE_READ'].append(report_path)
            return 'REJECT'
        
        filename = Path(report_path).name
        verdict = 'PASS'
        issues = []
        
        # 1. Extract and validate EXP IDs
        exp_ids = self.extract_exp_ids(content)
        if not exp_ids:
            issues.append('No EXP IDs found in header')
            self.errors_by_category['MISSING_EXP'].append(filename)
            verdict = 'NEEDS_FIX'
        else:
            # Validate that experiments exist
            for exp_id in exp_ids:
                exp_path, exp_data = self.load_experiment(exp_id)
                if not exp_data:
                    issues.append(f'EXP-{exp_id} JSON not found')
                    self.errors_by_category['EXP_ATTRIBUTION'].append(filename)
                    verdict = 'NEEDS_FIX'
        
        # 2. Check for "all patients" claims without qualification
        patients_check = self.check_all_patients_claim(content)
        if patients_check == 'UNQUALIFIED':
            issues.append('Unqualified "all patients" claim without exclusion disclosure')
            self.errors_by_category['SCOPE_DISCLOSURE'].append(filename)
            verdict = 'NEEDS_FIX'
        
        # 3. Extract statistics to spot-check
        stats = self.extract_statistics(content)
        
        # 4. Check for suspicious numerical patterns
        if 'n_patients' in stats:
            n_vals = [int(float(v)) for v in stats['n_patients']]
            if len(set(n_vals)) > 1:
                # Multiple different N values - check consistency
                if max(n_vals) == min(n_vals) + 1:
                    issues.append('Off-by-one pattern in N values (possible counting error)')
                    self.errors_by_category['COUNTING'].append(filename)
                    verdict = 'NEEDS_FIX'
        
        # 5. Check for fabricated tables (look for suspiciously round numbers)
        table_pattern = r'\|[\s\d\.\-\+]+\|'
        tables = re.findall(table_pattern, content)
        if tables:
            for table in tables:
                # Check if all numbers are round (suspicious pattern)
                nums = re.findall(r'\d+(?:\.\d+)?', table)
                if len(nums) > 3:
                    non_zero_decimals = [n for n in nums if '.' in n and not n.endswith('.0')]
                    if len(non_zero_decimals) == 0 and len(nums) > 5:
                        # All round numbers - might indicate fabrication
                        issues.append('Table with all round numbers (potential fabrication)')
                        self.errors_by_category['FABRICATION'].append(filename)
                        verdict = 'NEEDS_FIX'
        
        # 6. Check for method descriptions that might not match source code
        method_patterns = [
            r'(?:algorithm|method).*?(?:implements?|uses?|applies?)',
            r'(?:we\s+)?(?:used|applied|performed)',
        ]
        method_mentions = 0
        for pattern in method_patterns:
            method_mentions += len(re.findall(pattern, content, re.IGNORECASE))
        
        # If many method mentions but no code references, might be an issue
        code_refs = len(re.findall(r'(?:`.*?\.(?:py|java|kt|swift)`|externals/)', content))
        if method_mentions > 3 and code_refs == 0:
            issues.append('Multiple method descriptions without code references')
            self.errors_by_category['METHOD_MISMATCH'].append(filename)
            # This is moderate severity
            if verdict == 'PASS':
                verdict = 'NEEDS_FIX'
        
        # Store result
        result_entry = {
            'file': filename,
            'idx': idx,
            'exp_ids': exp_ids,
            'issues': issues,
            'stats': stats,
        }
        
        self.results[verdict].append(result_entry)
        return verdict
    
    def run(self):
        """Run verification on all reports."""
        reports = self.find_reports()
        print(f"Found {len(reports)} reports")
        print(f"Starting verification...\n")
        
        for idx, report in enumerate(reports, 1):
            verdict = self.verify_report(report, idx)
            
            # Show progress every 20 reports
            if idx % 20 == 0:
                print(f"  Progress: {idx}/{len(reports)} ({verdict})")
        
        return self.generate_report()
    
    def generate_report(self):
        """Generate final verification report."""
        total = len(self.results['PASS']) + len(self.results['NEEDS_FIX']) + len(self.results['REJECT'])
        
        report = []
        report.append("## Summary")
        report.append(f"- Total verified: {total}/167")
        report.append(f"- Pass: {len(self.results['PASS'])}")
        report.append(f"- Needs fix: {len(self.results['NEEDS_FIX'])}")
        report.append(f"- Reject: {len(self.results['REJECT'])}")
        report.append("")
        
        # Error breakdown
        report.append("## Errors by Category")
        for category in sorted(self.errors_by_category.keys()):
            count = len(self.errors_by_category[category])
            report.append(f"- {category}: {count} found")
        report.append("")
        
        # High priority rejections
        if self.results['REJECT']:
            report.append("## High-Priority Rejections")
            for item in self.results['REJECT'][:5]:
                report.append(f"### {item['file']}")
                report.append(f"Reason: {item['reason']}")
            report.append("")
        
        # Sample pass reports
        if self.results['PASS']:
            report.append("## Sample Pass Reports (first 10)")
            for item in self.results['PASS'][:10]:
                exp_str = ', '.join([f"EXP-{e}" for e in item['exp_ids']])
                report.append(f"- {item['file']} ({exp_str})")
            report.append("")
        
        # Sample needs-fix reports (by severity)
        if self.results['NEEDS_FIX']:
            report.append("## Sample Needs-Fix Reports (first 10)")
            for item in self.results['NEEDS_FIX'][:10]:
                exp_str = ', '.join([f"EXP-{e}" for e in item['exp_ids']])
                issues_str = '; '.join(item['issues'][:2]) if item['issues'] else 'Unknown'
                report.append(f"- {item['file']} ({exp_str})")
                report.append(f"  Issues: {issues_str}")
            report.append("")
        
        return '\n'.join(report)


if __name__ == '__main__':
    verifier = ReportVerifier()
    report = verifier.run()
    print("\n" + "="*80)
    print(report)
    print("="*80)
    
    # Save to file
    with open('VERIFICATION-BATCH3-RESULTS.md', 'w') as f:
        f.write(report)
    print("\nResults saved to VERIFICATION-BATCH3-RESULTS.md")
