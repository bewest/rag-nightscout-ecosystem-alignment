#!/usr/bin/env python3
"""
Verify mapping documentation coverage against source code.

Checks that mapping docs cover fields actually used in source code,
and identifies any undocumented fields or stale documentation.

Usage:
    python tools/verify_mapping_coverage.py mapping/xdrip-android/nightscout-sync.md
    python tools/verify_mapping_coverage.py --all
    python tools/verify_mapping_coverage.py --sample 5
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent

# Mapping directory
MAPPING_DIR = PROJECT_ROOT / "mapping"

# Externals directory
EXTERNALS_DIR = PROJECT_ROOT / "externals"

# Map mapping directories to external repo paths
REPO_MAPPING = {
    "xdrip-android": "xDrip",
    "xdrip": "xDrip",
    "aaps": "AndroidAPS",
    "loop": "LoopWorkspace",
    "trio": "Trio",
    "cgm-remote-monitor": "cgm-remote-monitor",
    "nightscout": "cgm-remote-monitor",
    "oref0": "oref0",
    "openaps": "oref0",
    "diable": "DiaBLE",
    "xdrip4ios": "xdripswift",
    "nightscout-connect": "nightscout-connect",
    "nightscout-librelink-up": "nightscout-librelink-up",
    "share2nightscout-bridge": "share2nightscout-bridge",
    "tconnectsync": "tconnectsync",
    "nocturne": "Nocturne",
    "loopfollow": "LoopFollow",
    "loopcaregiver": "LoopCaregiver",
    "nightguard": "nightguard",
    "nightscout-reporter": "nightscout-reporter",
    "xdrip-js": "xdrip-js",
}

# Field patterns to extract from code
FIELD_PATTERNS = {
    "java": [
        r'\.put\s*\(\s*["\'](\w+)["\']',  # json.put("field", ...)
        r'@Column\s*\(\s*name\s*=\s*["\'](\w+)["\']',  # @Column(name = "field")
        r'@SerializedName\s*\(\s*["\'](\w+)["\']',  # @SerializedName("field")
    ],
    "kotlin": [
        r'@SerializedName\s*\(\s*["\'](\w+)["\']',
        r'val\s+(\w+)\s*:',  # val fieldName: Type
        r'var\s+(\w+)\s*:',  # var fieldName: Type
    ],
    "swift": [
        r'case\s+(\w+)\s*=\s*["\']',  # CodingKeys case field = "json_key"
        r'let\s+(\w+)\s*:',  # let fieldName: Type
        r'var\s+(\w+)\s*:',  # var fieldName: Type
    ],
    "javascript": [
        r'["\'](\w+)["\']\s*:',  # "field": value
        r'\.(\w+)\s*=',  # obj.field =
    ],
    "typescript": [
        r'["\'](\w+)["\']\s*:',
        r'(\w+)\s*:\s*\w+',  # field: Type
    ],
}

# Words to exclude (common noise)
NOISE_WORDS = {
    "the", "and", "for", "with", "from", "this", "that", "null", "true", "false",
    "type", "name", "value", "data", "json", "string", "number", "boolean",
    "get", "set", "new", "return", "import", "export", "class", "function",
    "if", "else", "switch", "case", "break", "continue", "while", "for",
    "public", "private", "protected", "static", "final", "const", "let", "var",
}


def find_mapping_files():
    """Find all mapping markdown files."""
    files = []
    for path in MAPPING_DIR.rglob("*.md"):
        # Skip templates and READMEs
        if path.name.startswith("_") or path.name == "README.md":
            continue
        # Skip cross-project (different structure)
        if "cross-project" in str(path):
            continue
        files.append(path)
    return sorted(files)


def extract_documented_fields(mapping_file):
    """Extract field names documented in a mapping file."""
    fields = set()
    
    with open(mapping_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Pattern 1: Backticked field names (e.g., `fieldName`)
    backtick_pattern = r'`([a-zA-Z_][a-zA-Z0-9_]*)`'
    for match in re.finditer(backtick_pattern, content):
        field = match.group(1)
        # Filter noise
        if field.lower() not in NOISE_WORDS and len(field) > 2:
            fields.add(field)
    
    # Pattern 2: Table rows with field names (| fieldName | ...)
    table_pattern = r'\|\s*`?([a-zA-Z_][a-zA-Z0-9_]*)`?\s*\|'
    for match in re.finditer(table_pattern, content):
        field = match.group(1)
        if field.lower() not in NOISE_WORDS and len(field) > 2:
            fields.add(field)
    
    # Pattern 3: JSON/code blocks with field names
    code_block_pattern = r'["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
    for match in re.finditer(code_block_pattern, content):
        field = match.group(1)
        if field.lower() not in NOISE_WORDS and len(field) > 2:
            fields.add(field)
    
    return fields


def get_repo_for_mapping(mapping_file):
    """Determine which external repo corresponds to a mapping file."""
    # Get the mapping directory name
    rel_path = mapping_file.relative_to(MAPPING_DIR)
    mapping_dir = rel_path.parts[0]
    
    # Look up in repo mapping
    repo_name = REPO_MAPPING.get(mapping_dir)
    if repo_name:
        repo_path = EXTERNALS_DIR / repo_name
        if repo_path.exists():
            return repo_path
    
    return None


def extract_source_fields(repo_path, sample_limit=50):
    """Extract field names from source code in a repo."""
    fields = set()
    
    if not repo_path or not repo_path.exists():
        return fields
    
    # Find relevant source files
    extensions = {".java", ".kt", ".swift", ".js", ".ts"}
    source_files = []
    
    for ext in extensions:
        for path in repo_path.rglob(f"*{ext}"):
            # Skip test files
            if "test" in str(path).lower():
                continue
            source_files.append(path)
    
    # Sample if too many files
    if len(source_files) > sample_limit:
        source_files = random.sample(source_files, sample_limit)
    
    for source_file in source_files:
        try:
            with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Determine language
            ext = source_file.suffix
            lang = {
                ".java": "java",
                ".kt": "kotlin",
                ".swift": "swift",
                ".js": "javascript",
                ".ts": "typescript",
            }.get(ext, "javascript")
            
            # Apply patterns
            for pattern in FIELD_PATTERNS.get(lang, []):
                for match in re.finditer(pattern, content):
                    field = match.group(1)
                    if field.lower() not in NOISE_WORDS and len(field) > 2:
                        fields.add(field)
        except Exception:
            continue
    
    return fields


def verify_field_in_source(field, repo_path):
    """Check if a field exists in source code using grep."""
    if not repo_path or not repo_path.exists():
        return False
    
    try:
        result = subprocess.run(
            ["grep", "-r", "-l", "--include=*.java", "--include=*.kt",
             "--include=*.swift", "--include=*.js", "--include=*.ts",
             field, str(repo_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def analyze_mapping_coverage(mapping_file):
    """Analyze coverage for a single mapping file."""
    result = {
        "file": str(mapping_file.relative_to(PROJECT_ROOT)),
        "documented_fields": 0,
        "verified_fields": 0,
        "coverage": 0.0,
        "verified": [],
        "unverified": [],
        "status": "UNKNOWN",
    }
    
    # Extract documented fields
    documented = extract_documented_fields(mapping_file)
    result["documented_fields"] = len(documented)
    
    if not documented:
        result["status"] = "NO_FIELDS"
        return result
    
    # Get corresponding repo
    repo_path = get_repo_for_mapping(mapping_file)
    
    if not repo_path:
        result["status"] = "NO_REPO"
        return result
    
    # Verify each field
    verified = []
    unverified = []
    
    for field in sorted(documented):
        if verify_field_in_source(field, repo_path):
            verified.append(field)
        else:
            unverified.append(field)
    
    result["verified_fields"] = len(verified)
    result["verified"] = verified[:10]  # Top 10 for display
    result["unverified"] = unverified[:10]  # Top 10 for display
    
    if len(documented) > 0:
        result["coverage"] = len(verified) / len(documented) * 100
    
    # Determine status
    if result["coverage"] >= 80:
        result["status"] = "GOOD"
    elif result["coverage"] >= 50:
        result["status"] = "NEEDS_REVIEW"
    else:
        result["status"] = "LOW_COVERAGE"
    
    return result


def print_result(result, verbose=False):
    """Print analysis result."""
    status_icons = {
        "GOOD": "🟢",
        "NEEDS_REVIEW": "🟡",
        "LOW_COVERAGE": "🔴",
        "NO_FIELDS": "⚪",
        "NO_REPO": "⚪",
        "UNKNOWN": "⚪",
    }
    
    icon = status_icons.get(result["status"], "⚪")
    
    print(f"\n{icon} {result['file']}")
    print(f"   Status: {result['status']}")
    print(f"   Coverage: {result['coverage']:.1f}% ({result['verified_fields']}/{result['documented_fields']} fields)")
    
    if verbose and result["unverified"]:
        print(f"   Unverified: {', '.join(result['unverified'][:5])}")
    if verbose and result["verified"]:
        print(f"   Verified: {', '.join(result['verified'][:5])}")


def main():
    parser = argparse.ArgumentParser(
        description="Verify mapping documentation coverage"
    )
    parser.add_argument(
        "mapping_file",
        nargs="?",
        help="Specific mapping file to check"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all mapping files"
    )
    parser.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="Check N random mapping files"
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducible sampling"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show field details"
    )
    
    args = parser.parse_args()
    
    if args.seed:
        random.seed(args.seed)
    
    # Determine files to check
    if args.mapping_file:
        path = Path(args.mapping_file)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        files = [path]
    elif args.all:
        files = find_mapping_files()
    elif args.sample:
        all_files = find_mapping_files()
        files = random.sample(all_files, min(args.sample, len(all_files)))
    else:
        # Default: sample 5
        all_files = find_mapping_files()
        files = random.sample(all_files, min(5, len(all_files)))
    
    # Check externals exist
    if not EXTERNALS_DIR.exists():
        print("Error: externals/ directory not found. Run 'make bootstrap' first.")
        sys.exit(1)
    
    print(f"Found {len(find_mapping_files())} mapping files in {MAPPING_DIR}")
    print(f"Checking {len(files)} file(s)...")
    
    results = []
    for f in files:
        if f.exists():
            result = analyze_mapping_coverage(f)
            results.append(result)
            if not args.json:
                print_result(result, args.verbose)
    
    # Summary
    if not args.json:
        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        
        good = sum(1 for r in results if r["status"] == "GOOD")
        needs_review = sum(1 for r in results if r["status"] == "NEEDS_REVIEW")
        low = sum(1 for r in results if r["status"] == "LOW_COVERAGE")
        other = len(results) - good - needs_review - low
        
        print(f"  🟢 Good (≥80%): {good}")
        print(f"  🟡 Needs review (50-79%): {needs_review}")
        print(f"  🔴 Low coverage (<50%): {low}")
        print(f"  ⚪ Other: {other}")
        
        # Calculate average coverage
        coverages = [r["coverage"] for r in results if r["status"] not in ("NO_FIELDS", "NO_REPO")]
        if coverages:
            avg = sum(coverages) / len(coverages)
            print(f"\n  Average coverage: {avg:.1f}%")
    else:
        print(json.dumps(results, indent=2))
    
    # Exit code based on average coverage
    coverages = [r["coverage"] for r in results if r["status"] not in ("NO_FIELDS", "NO_REPO")]
    if coverages:
        avg = sum(coverages) / len(coverages)
        sys.exit(0 if avg >= 60 else 1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
