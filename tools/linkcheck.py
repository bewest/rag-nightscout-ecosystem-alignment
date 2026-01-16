#!/usr/bin/env python3
"""
Link checker for the alignment workspace.

Verifies that:
1. All code references in docs/_includes/code-refs.md resolve to files in externals/
2. All internal markdown links are valid
3. Optionally verifies GitHub permalinks at pinned SHAs

Usage:
    python tools/linkcheck.py              # Check all refs
    python tools/linkcheck.py --verbose    # Show details
    python tools/linkcheck.py --remote     # Also check GitHub URLs
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    requests = None  # type: ignore
    HAS_REQUESTS = False

WORKSPACE_ROOT = Path(__file__).parent.parent
LOCKFILE = WORKSPACE_ROOT / "workspace.lock.json"
DOCS_DIR = WORKSPACE_ROOT / "docs"
CODE_REFS_FILE = WORKSPACE_ROOT / "docs" / "_includes" / "code-refs.md"


def load_lockfile():
    """Load and parse workspace.lock.json."""
    if not LOCKFILE.exists():
        return None
    with open(LOCKFILE) as f:
        return json.load(f)


def get_repo_aliases(lockfile_data):
    """Build a mapping of repo aliases to their config."""
    aliases = {}
    externals_dir = lockfile_data.get("externals_dir", "externals")
    for repo in lockfile_data.get("repos", []):
        alias = repo.get("alias", repo["name"])
        # Compute local_path consistently with bootstrap.py
        repo["_local_path"] = f"{externals_dir}/{repo['name']}"
        aliases[alias] = repo
    return aliases


def parse_code_ref(ref_string):
    """
    Parse a code reference like 'crm:lib/server/treatments.js#L10-L50'.
    Returns (alias, path, anchor) or None if invalid.
    
    Valid code refs must:
    - Start with a known alias pattern (lowercase, short)
    - Have a path that looks like a file path (contains / or .)
    - Not look like JSON key:value patterns
    """
    # Skip patterns that look like JSON or prose (has quotes, spaces after colon)
    if re.search(r':\s*["\'\[]', ref_string) or ' ' in ref_string:
        return None
    
    # Must have a path-like structure after the colon
    match = re.match(r'^([a-zA-Z][a-zA-Z0-9_-]{0,15}):([a-zA-Z0-9_./-]+)(?:#(.+))?$', ref_string)
    if match:
        path = match.group(2)
        # Path must look like a file path (has extension or directory)
        if '/' in path or '.' in path:
            return match.group(1), path, match.group(3)
    return None


def find_code_refs_in_file(filepath):
    """Extract all code references from a markdown file."""
    refs = []
    try:
        content = filepath.read_text()
        # Look for patterns like `crm:path/to/file.ts#L10-L50`
        pattern = r'`([a-zA-Z0-9_-]+:[^`]+)`'
        for match in re.finditer(pattern, content):
            ref = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            refs.append((ref, line_num))
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}")
    return refs


def find_markdown_links(filepath):
    """Find all internal markdown links in a file."""
    links = []
    try:
        content = filepath.read_text()
        # Match [text](path) but not [text](http...)
        pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        for match in re.finditer(pattern, content):
            link_text = match.group(1)
            link_path = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            
            # Skip external URLs
            if link_path.startswith(('http://', 'https://', 'mailto:')):
                continue
            
            # Skip anchors only
            if link_path.startswith('#'):
                continue
                
            links.append((link_path, line_num, link_text))
    except Exception as e:
        print(f"Warning: Could not read {filepath}: {e}")
    return links


def should_skip_file(filepath, skip_patterns=None):
    """Check if a file should be skipped during validation."""
    if skip_patterns is None:
        skip_patterns = [
            "externals",
            "_generated",
            "_template",
        ]
    filepath_str = str(filepath)
    return any(pattern in filepath_str for pattern in skip_patterns)


def check_code_refs(aliases, verbose=False):
    """Check all code references resolve to files."""
    errors = []
    checked = 0
    
    # Find all markdown files, excluding externals, generated, and templates
    md_files = list(WORKSPACE_ROOT.rglob("*.md"))
    md_files = [f for f in md_files if not should_skip_file(f)]
    
    for md_file in md_files:
        refs = find_code_refs_in_file(md_file)
        for ref, line_num in refs:
            parsed = parse_code_ref(ref)
            if not parsed:
                continue
            
            alias, path, anchor = parsed
            checked += 1
            
            if alias not in aliases:
                errors.append(f"{md_file}:{line_num}: Unknown repo alias '{alias}' in ref '{ref}'")
                continue
            
            repo = aliases[alias]
            local_path = WORKSPACE_ROOT / repo.get("_local_path", f"externals/{repo['name']}")
            full_path = local_path / path
            
            if not local_path.exists():
                if verbose:
                    print(f"  [skip] {ref} - repo not cloned")
                continue
            
            if not full_path.exists():
                errors.append(f"{md_file}:{line_num}: File not found: {full_path} (ref: {ref})")
            elif verbose:
                print(f"  [ok] {ref}")
    
    return errors, checked


def check_markdown_links(verbose=False):
    """Check all internal markdown links resolve."""
    errors = []
    checked = 0
    
    # Find all markdown files, excluding externals, generated, and templates
    md_files = list(WORKSPACE_ROOT.rglob("*.md"))
    md_files = [f for f in md_files if not should_skip_file(f)]
    
    for md_file in md_files:
        links = find_markdown_links(md_file)
        for link_path, line_num, link_text in links:
            checked += 1
            
            # Handle anchors
            path_part = link_path.split('#')[0] if '#' in link_path else link_path
            
            if not path_part:
                continue
            
            # Resolve relative to the file's directory
            if path_part.startswith('/'):
                target = WORKSPACE_ROOT / path_part.lstrip('/')
            else:
                target = md_file.parent / path_part
            
            target = target.resolve()
            
            if not target.exists():
                errors.append(f"{md_file}:{line_num}: Broken link: {link_path}")
            elif verbose:
                print(f"  [ok] {md_file.name}: {link_path}")
    
    return errors, checked


def check_remote_links(aliases, verbose=False):
    """Optionally check GitHub URLs are accessible."""
    if not HAS_REQUESTS or requests is None:
        print("Note: Install 'requests' to check remote URLs")
        return [], 0
    
    errors = []
    checked = 0
    
    for alias, repo in aliases.items():
        if not repo.get("sha"):
            continue
        
        url = repo["url"].replace(".git", "")
        sha = repo["sha"]
        test_url = f"{url}/tree/{sha}"
        
        try:
            checked += 1
            response = requests.head(test_url, timeout=5)
            if response.status_code != 200:
                errors.append(f"Remote URL not accessible: {test_url} (status: {response.status_code})")
            elif verbose:
                print(f"  [ok] {test_url}")
        except Exception as e:
            errors.append(f"Could not check {test_url}: {e}")
    
    return errors, checked


def main():
    parser = argparse.ArgumentParser(description="Check links and code references in the workspace")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show successful checks")
    parser.add_argument("--remote", action="store_true", help="Also check remote GitHub URLs")
    args = parser.parse_args()
    
    print("Checking workspace links...\n")
    
    lockfile = load_lockfile()
    if not lockfile:
        print("Warning: No workspace.lock.json found")
        aliases = {}
    else:
        aliases = get_repo_aliases(lockfile)
    
    total_errors = []
    total_checked = 0
    
    # Check code references
    print("Checking code references...")
    errors, checked = check_code_refs(aliases, args.verbose)
    total_errors.extend(errors)
    total_checked += checked
    print(f"  Checked {checked} code refs, {len(errors)} errors\n")
    
    # Check markdown links
    print("Checking markdown links...")
    errors, checked = check_markdown_links(args.verbose)
    total_errors.extend(errors)
    total_checked += checked
    print(f"  Checked {checked} links, {len(errors)} errors\n")
    
    # Optionally check remote URLs
    if args.remote:
        print("Checking remote URLs...")
        errors, checked = check_remote_links(aliases, args.verbose)
        total_errors.extend(errors)
        total_checked += checked
        print(f"  Checked {checked} URLs, {len(errors)} errors\n")
    
    # Summary
    print("-" * 50)
    if total_errors:
        print(f"\nFound {len(total_errors)} error(s):\n")
        for error in total_errors:
            print(f"  - {error}")
        return 1
    else:
        print(f"\nAll {total_checked} checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
