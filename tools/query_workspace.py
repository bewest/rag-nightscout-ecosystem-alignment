#!/usr/bin/env python3
"""
Workspace Query Tool - Interactive and automated query interface for documentation and tests.

Enables querying across:
- Requirements (REQ-XXX)
- Gaps (GAP-XXX)
- Assertions and test scenarios
- Mapping documents
- API specifications
- Code references

Usage:
    # Interactive mode
    python tools/query_workspace.py

    # Query by requirement ID
    python tools/query_workspace.py --req REQ-001

    # Query by gap ID
    python tools/query_workspace.py --gap GAP-SYNC-001

    # Search documentation
    python tools/query_workspace.py --search "authentication"

    # Find tests for a requirement
    python tools/query_workspace.py --tests-for REQ-001

    # Find coverage for a term
    python tools/query_workspace.py --term "basal"

    # JSON output
    python tools/query_workspace.py --req REQ-001 --json

Examples for AI agents:
    # What tests cover requirement REQ-001?
    python tools/query_workspace.py --tests-for REQ-001 --json

    # What documentation mentions "sync"?
    python tools/query_workspace.py --search "sync" --json

    # What gaps are related to authentication?
    python tools/query_workspace.py --search "authentication" --filter gaps --json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent
TRACEABILITY_DIR = WORKSPACE_ROOT / "traceability"
MAPPING_DIR = WORKSPACE_ROOT / "mapping"
SPECS_DIR = WORKSPACE_ROOT / "specs"
CONFORMANCE_DIR = WORKSPACE_ROOT / "conformance"
DOCS_DIR = WORKSPACE_ROOT / "docs"

REQ_PATTERN = re.compile(r'\b(REQ-\d{3})\b')
GAP_PATTERN = re.compile(r'\b(GAP-[A-Z]+-\d{3})\b')


def load_requirements():
    """Load all requirements from requirements.md."""
    requirements_file = TRACEABILITY_DIR / "requirements.md"
    requirements = {}
    
    if not requirements_file.exists():
        return requirements
    
    content = requirements_file.read_text(errors="ignore")
    current_req = None
    current_data = {}
    
    for line in content.split('\n'):
        req_match = re.match(r'^###\s+(REQ-\d{3}):\s*(.+)$', line)
        if req_match:
            if current_req:
                requirements[current_req] = current_data
            current_req = req_match.group(1)
            current_data = {
                "id": current_req,
                "title": req_match.group(2).strip(),
                "statement": "",
                "rationale": "",
                "scenarios": [],
                "verification": "",
                "references": []
            }
            continue
        
        if current_req:
            if line.startswith("**Statement**:"):
                current_data["statement"] = line.replace("**Statement**:", "").strip()
            elif line.startswith("**Rationale**:"):
                current_data["rationale"] = line.replace("**Rationale**:", "").strip()
            elif line.startswith("**Scenarios**:"):
                current_data["scenarios"] = line.replace("**Scenarios**:", "").strip().split(',')
            elif line.startswith("**Verification**:"):
                current_data["verification"] = line.replace("**Verification**:", "").strip()
    
    if current_req:
        requirements[current_req] = current_data
    
    return requirements


def load_gaps():
    """Load all gaps from gaps.md."""
    gaps_file = TRACEABILITY_DIR / "gaps.md"
    gaps = {}
    
    if not gaps_file.exists():
        return gaps
    
    content = gaps_file.read_text(errors="ignore")
    
    for match in re.finditer(r'^###\s+(GAP-[A-Z]+-\d{3}):\s*(.+)$', content, re.MULTILINE):
        gap_id = match.group(1)
        title = match.group(2).strip()
        gaps[gap_id] = {
            "id": gap_id,
            "title": title,
            "description": ""
        }
    
    return gaps


def load_assertions():
    """Load all assertions from conformance/assertions."""
    assertions = []
    assertions_dir = CONFORMANCE_DIR / "assertions"
    
    if not assertions_dir.exists():
        return assertions
    
    for yaml_file in assertions_dir.glob("*.yaml"):
        if yaml_file.name == "_template.yaml":
            continue
        
        content = yaml_file.read_text(errors="ignore")
        
        # Extract scenario name
        scenario_match = re.search(r'^scenario:\s*(.+)$', content, re.MULTILINE)
        scenario = scenario_match.group(1).strip() if scenario_match else yaml_file.stem
        
        # Extract assertion IDs
        assertion_ids = re.findall(r'^\s*-\s*id:\s*(.+)$', content, re.MULTILINE)
        
        # Extract requirements and gaps referenced
        reqs = REQ_PATTERN.findall(content)
        gaps = GAP_PATTERN.findall(content)
        
        assertions.append({
            "file": str(yaml_file.relative_to(WORKSPACE_ROOT)),
            "scenario": scenario,
            "assertion_ids": assertion_ids,
            "requirements": list(set(reqs)),
            "gaps": list(set(gaps))
        })
    
    return assertions


def search_documentation(query, filter_type=None):
    """Search across all documentation."""
    results = []
    
    # Define search paths
    search_dirs = [MAPPING_DIR, DOCS_DIR, TRACEABILITY_DIR]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        for md_file in search_dir.rglob("*.md"):
            content = md_file.read_text(errors="ignore")
            
            if query.lower() in content.lower():
                # Count occurrences
                count = content.lower().count(query.lower())
                
                # Extract context (lines containing the query)
                lines = content.split('\n')
                matching_lines = [line for line in lines if query.lower() in line.lower()]
                
                result = {
                    "file": str(md_file.relative_to(WORKSPACE_ROOT)),
                    "occurrences": count,
                    "context": matching_lines[:5]  # First 5 matches
                }
                
                # Apply filter
                if filter_type == "gaps" and "gaps" not in md_file.name.lower():
                    continue
                if filter_type == "requirements" and "requirements" not in md_file.name.lower():
                    continue
                if filter_type == "mapping" and "mapping" not in str(md_file):
                    continue
                
                results.append(result)
    
    return sorted(results, key=lambda x: x["occurrences"], reverse=True)


def find_tests_for_requirement(req_id):
    """Find all tests/assertions that cover a requirement."""
    assertions = load_assertions()
    
    results = []
    for assertion in assertions:
        if req_id in assertion["requirements"]:
            results.append({
                "scenario": assertion["scenario"],
                "file": assertion["file"],
                "assertions": assertion["assertion_ids"]
            })
    
    return results


def find_documentation_for_term(term):
    """Find all documentation mentioning a specific term."""
    return search_documentation(term)


def interactive_mode():
    """Run interactive query session."""
    print("=== Workspace Query Tool ===")
    print("\nCommands:")
    print("  req <ID>     - Query requirement")
    print("  gap <ID>     - Query gap")
    print("  search <term> - Search documentation")
    print("  tests <REQ>  - Find tests for requirement")
    print("  term <term>  - Find term usage")
    print("  list reqs    - List all requirements")
    print("  list gaps    - List all gaps")
    print("  quit         - Exit")
    print()
    
    requirements = load_requirements()
    gaps = load_gaps()
    
    while True:
        try:
            cmd = input("> ").strip()
            
            if not cmd:
                continue
            
            if cmd == "quit":
                break
            
            parts = cmd.split(maxsplit=1)
            action = parts[0]
            
            if action == "req" and len(parts) == 2:
                req_id = parts[1].upper()
                if req_id in requirements:
                    req = requirements[req_id]
                    print(f"\n{req_id}: {req['title']}")
                    print(f"Statement: {req['statement']}")
                    print(f"Rationale: {req['rationale']}")
                else:
                    print(f"Requirement {req_id} not found")
            
            elif action == "gap" and len(parts) == 2:
                gap_id = parts[1].upper()
                if gap_id in gaps:
                    gap = gaps[gap_id]
                    print(f"\n{gap_id}: {gap['title']}")
                    print(f"Description: {gap['description']}")
                else:
                    print(f"Gap {gap_id} not found")
            
            elif action == "search" and len(parts) == 2:
                results = search_documentation(parts[1])
                print(f"\nFound {len(results)} documents:")
                for r in results[:10]:
                    print(f"  - {r['file']} ({r['occurrences']} matches)")
            
            elif action == "tests" and len(parts) == 2:
                results = find_tests_for_requirement(parts[1].upper())
                print(f"\nFound {len(results)} test scenarios:")
                for r in results:
                    print(f"  - {r['scenario']} ({r['file']})")
            
            elif action == "term" and len(parts) == 2:
                results = find_documentation_for_term(parts[1])
                print(f"\nFound {len(results)} documents:")
                for r in results[:10]:
                    print(f"  - {r['file']} ({r['occurrences']} matches)")
            
            elif action == "list" and len(parts) == 2:
                if parts[1] == "reqs":
                    print(f"\n{len(requirements)} Requirements:")
                    for req_id, req in sorted(requirements.items()):
                        print(f"  {req_id}: {req['title']}")
                elif parts[1] == "gaps":
                    print(f"\n{len(gaps)} Gaps:")
                    for gap_id, gap in sorted(gaps.items()):
                        print(f"  {gap_id}: {gap['title']}")
            
            else:
                print("Unknown command. Type 'quit' to exit.")
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except EOFError:
            break


def main():
    parser = argparse.ArgumentParser(description="Query workspace documentation and tests")
    parser.add_argument("--req", help="Query specific requirement ID")
    parser.add_argument("--gap", help="Query specific gap ID")
    parser.add_argument("--search", help="Search documentation for term")
    parser.add_argument("--tests-for", help="Find tests covering a requirement")
    parser.add_argument("--term", help="Find documentation for a term")
    parser.add_argument("--filter", choices=["gaps", "requirements", "mapping"], help="Filter search results")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    # If no arguments, run interactive mode
    if not any([args.req, args.gap, args.search, args.tests_for, args.term]):
        interactive_mode()
        return
    
    result = None
    
    if args.req:
        requirements = load_requirements()
        result = requirements.get(args.req.upper())
    
    elif args.gap:
        gaps = load_gaps()
        result = gaps.get(args.gap.upper())
    
    elif args.search:
        result = search_documentation(args.search, args.filter)
    
    elif args.tests_for:
        result = find_tests_for_requirement(args.tests_for.upper())
    
    elif args.term:
        result = find_documentation_for_term(args.term)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if isinstance(result, dict):
            for key, value in result.items():
                print(f"{key}: {value}")
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    print(json.dumps(item, indent=2))
                else:
                    print(item)
        elif result is None:
            print("No results found")
        else:
            print(result)


if __name__ == "__main__":
    main()
