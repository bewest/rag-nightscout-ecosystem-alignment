#!/usr/bin/env python3
"""
Known vs Unknown Dashboard - Project Health Summary

Generates an at-a-glance view of:
- Repos analyzed
- Gaps identified by category
- Requirements coverage
- Mapping completeness
- Confidence levels

Usage:
    python tools/known_unknown_dashboard.py [--json] [--markdown]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

# Directories
ROOT = Path(__file__).parent.parent
EXTERNALS = ROOT / "externals"
MAPPING = ROOT / "mapping"
TRACEABILITY = ROOT / "traceability"
DOCS = ROOT / "docs"
SPECS = ROOT / "specs" / "openapi"


def count_repos():
    """Count external repositories."""
    if not EXTERNALS.exists():
        return {"total": 0, "cloned": 0}
    repos = [d for d in EXTERNALS.iterdir() if d.is_dir() and not d.name.startswith('.')]
    return {"total": 22, "cloned": len(repos)}


def count_mappings():
    """Count mapping files per project."""
    mappings = {}
    if not MAPPING.exists():
        return mappings
    for proj_dir in MAPPING.iterdir():
        if proj_dir.is_dir():
            md_files = list(proj_dir.glob("*.md"))
            mappings[proj_dir.name] = len(md_files)
    return mappings


def count_gaps():
    """Count gaps by category from traceability files."""
    gaps = defaultdict(int)
    gap_pattern = re.compile(r'### (GAP-[A-Z]+-\d+)')
    
    if not TRACEABILITY.exists():
        return dict(gaps)
    
    for md_file in TRACEABILITY.glob("**/*.md"):
        try:
            content = md_file.read_text(errors='ignore')
            for match in gap_pattern.finditer(content):
                gap_id = match.group(1)
                # Extract category (e.g., GAP-SYNC from GAP-SYNC-001)
                parts = gap_id.split('-')
                if len(parts) >= 2:
                    category = f"GAP-{parts[1]}"
                    gaps[category] += 1
        except Exception:
            pass
    
    return dict(gaps)


def count_requirements():
    """Count requirements by category."""
    reqs = defaultdict(int)
    req_pattern = re.compile(r'### (REQ-[A-Z]*-?\d+)')
    
    if not TRACEABILITY.exists():
        return dict(reqs)
    
    for md_file in TRACEABILITY.glob("**/*.md"):
        try:
            content = md_file.read_text(errors='ignore')
            for match in req_pattern.finditer(content):
                req_id = match.group(1)
                parts = req_id.split('-')
                if len(parts) >= 2 and parts[1]:
                    category = f"REQ-{parts[1]}"
                else:
                    category = "REQ-GENERAL"
                reqs[category] += 1
        except Exception:
            pass
    
    return dict(reqs)


def count_deep_dives():
    """Count deep dive documents."""
    domain_docs = DOCS / "10-domain"
    if not domain_docs.exists():
        return 0
    return len(list(domain_docs.glob("*deep-dive*.md")))


def count_specs():
    """Count OpenAPI specifications."""
    if not SPECS.exists():
        return 0
    return len(list(SPECS.glob("*.yaml")))


def calculate_coverage(mappings):
    """Calculate coverage percentage based on mapping completeness."""
    # Target: 5 files per project (field-map, api-map, gaps, sync-patterns, README)
    target_per_project = 5
    total_target = len(mappings) * target_per_project
    total_actual = sum(mappings.values())
    if total_target == 0:
        return 0
    return round((total_actual / total_target) * 100, 1)


def calculate_confidence(data):
    """Calculate overall confidence level."""
    # Factors:
    # - Repos cloned vs total (20%)
    # - Mapping coverage (30%)
    # - Gap documentation (25%)
    # - Requirements (25%)
    
    repo_score = (data['repos']['cloned'] / max(data['repos']['total'], 1)) * 20
    mapping_score = data['coverage_pct'] * 0.3
    gap_score = min(sum(data['gaps'].values()) / 300, 1) * 25  # Target: 300 gaps
    req_score = min(sum(data['requirements'].values()) / 250, 1) * 25  # Target: 250 reqs
    
    total = repo_score + mapping_score + gap_score + req_score
    
    if total >= 80:
        return {"level": "HIGH", "score": round(total, 1)}
    elif total >= 50:
        return {"level": "MEDIUM", "score": round(total, 1)}
    else:
        return {"level": "LOW", "score": round(total, 1)}


def generate_dashboard():
    """Generate the complete dashboard data."""
    repos = count_repos()
    mappings = count_mappings()
    gaps = count_gaps()
    reqs = count_requirements()
    deep_dives = count_deep_dives()
    specs = count_specs()
    coverage = calculate_coverage(mappings)
    
    data = {
        "repos": repos,
        "mappings": mappings,
        "gaps": gaps,
        "requirements": reqs,
        "deep_dives": deep_dives,
        "specs": specs,
        "coverage_pct": coverage,
    }
    
    data["confidence"] = calculate_confidence(data)
    
    return data


def format_markdown(data):
    """Format dashboard as markdown."""
    lines = [
        "# Known vs Unknown Dashboard",
        "",
        f"**Generated**: {os.popen('date -Iseconds').read().strip()}",
        "",
        "## Summary",
        "",
        "| Metric | Value | Status |",
        "|--------|-------|--------|",
        f"| Repos Cloned | {data['repos']['cloned']}/{data['repos']['total']} | {'✅' if data['repos']['cloned'] >= 20 else '⚠️'} |",
        f"| Mapping Projects | {len(data['mappings'])} | {'✅' if len(data['mappings']) >= 15 else '⚠️'} |",
        f"| Gap Categories | {len(data['gaps'])} | {'✅' if len(data['gaps']) >= 10 else '⚠️'} |",
        f"| Total Gaps | {sum(data['gaps'].values())} | {'✅' if sum(data['gaps'].values()) >= 200 else '⚠️'} |",
        f"| Total Requirements | {sum(data['requirements'].values())} | {'✅' if sum(data['requirements'].values()) >= 200 else '⚠️'} |",
        f"| Deep Dives | {data['deep_dives']} | {'✅' if data['deep_dives'] >= 20 else '⚠️'} |",
        f"| OpenAPI Specs | {data['specs']} | {'✅' if data['specs'] >= 4 else '⚠️'} |",
        f"| Coverage | {data['coverage_pct']}% | {'✅' if data['coverage_pct'] >= 70 else '⚠️'} |",
        f"| **Confidence** | **{data['confidence']['level']}** ({data['confidence']['score']}%) | {'✅' if data['confidence']['level'] == 'HIGH' else '⚠️'} |",
        "",
        "## Gaps by Category",
        "",
        "| Category | Count |",
        "|----------|-------|",
    ]
    
    for cat, count in sorted(data['gaps'].items(), key=lambda x: -x[1])[:10]:
        lines.append(f"| {cat} | {count} |")
    
    lines.extend([
        "",
        "## Requirements by Category",
        "",
        "| Category | Count |",
        "|----------|-------|",
    ])
    
    for cat, count in sorted(data['requirements'].items(), key=lambda x: -x[1])[:10]:
        lines.append(f"| {cat} | {count} |")
    
    lines.extend([
        "",
        "## Mapping Coverage by Project",
        "",
        "| Project | Files | Status |",
        "|---------|-------|--------|",
    ])
    
    for proj, count in sorted(data['mappings'].items(), key=lambda x: -x[1]):
        status = "✅" if count >= 5 else "⚠️" if count >= 3 else "❌"
        lines.append(f"| {proj} | {count} | {status} |")
    
    lines.extend([
        "",
        "## Confidence Breakdown",
        "",
        "| Factor | Weight | Score |",
        "|--------|--------|-------|",
        f"| Repos cloned | 20% | {data['repos']['cloned']}/{data['repos']['total']} |",
        f"| Mapping coverage | 30% | {data['coverage_pct']}% |",
        f"| Gap documentation | 25% | {sum(data['gaps'].values())} gaps |",
        f"| Requirements | 25% | {sum(data['requirements'].values())} reqs |",
        "",
        "---",
        "",
        "*Dashboard generated by `tools/known_unknown_dashboard.py`*",
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Known vs Unknown Dashboard")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--markdown", action="store_true", help="Output as Markdown (default)")
    args = parser.parse_args()
    
    data = generate_dashboard()
    
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_markdown(data))


if __name__ == "__main__":
    main()
