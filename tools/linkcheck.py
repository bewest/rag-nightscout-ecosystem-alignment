#!/usr/bin/env python3
"""
Link checker for the alignment workspace.

Verifies that:
1. Code references (`alias:path`) in tracked markdown resolve to files in
   externals/ (repos that are not cloned are skipped)
2. Internal markdown links in tracked markdown resolve to tracked files or
   directories; links into externals/<repo>/ must name a repo pinned in
   workspace.lock.json and are checked on disk only when that repo is cloned
3. Optionally verifies GitHub permalinks at pinned SHAs

Markdown files and link targets come from `git ls-files`, so a local run sees
what a CI checkout sees. Links inside fenced code blocks and inline code spans
are not links and are not checked. The site landing pages listed in
tools/site/landing.yaml are resolved from where the site publishes them.

Usage:
    python tools/linkcheck.py                   # Check all refs
    python tools/linkcheck.py --verbose         # Show details
    python tools/linkcheck.py --skip-code-refs  # Markdown links only (CI)
    python tools/linkcheck.py --remote          # Also check GitHub URLs
"""

import argparse
import json
import re
import subprocess
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
LANDING_FILE = WORKSPACE_ROOT / "tools" / "site" / "landing.yaml"

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
# no span across a blank line
INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)((?:(?!\n[ \t]*\n).)+?)(?<!`)\1(?!`)", re.S)


def tracked_files():
    """Repo-relative POSIX paths of tracked files, or None outside a git checkout."""
    try:
        out = subprocess.run(
            ["git", "-C", str(WORKSPACE_ROOT), "ls-files", "-z"],
            capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {p for p in out.decode().split("\0") if p}


def tracked_dirs(files):
    dirs = set()
    for f in files:
        parts = f.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/".join(parts[:i]))
    return dirs


def mask_code(text):
    """Blank out fenced code blocks and inline code spans, keeping newlines so
    line numbers stay right."""
    chars = list(text)
    pos, fence = 0, None
    for line in text.splitlines(keepends=True):
        m = FENCE_RE.match(line)
        inside = False
        if fence is None and m:
            fence, inside = m.group(1), True
        elif fence is not None:
            inside = True
            s = line.strip()
            if s.startswith(fence[0] * len(fence)) and set(s) <= {fence[0]}:
                fence = None
        if inside:
            for k in range(pos, pos + len(line)):
                if chars[k] != "\n":
                    chars[k] = " "
        pos += len(line)
    masked = "".join(chars)
    for m in INLINE_CODE_RE.finditer(masked):
        for k in range(m.start(), m.end()):
            if chars[k] != "\n":
                chars[k] = " "
    return "".join(chars)


def landing_publish_dirs():
    """Map landing-page source paths to the directory the site publishes them in."""
    if not LANDING_FILE.exists():
        return {}
    try:
        import yaml
    except ImportError:
        sys.exit(f"linkcheck: PyYAML is required to read {LANDING_FILE.relative_to(WORKSPACE_ROOT)}")
    cfg = yaml.safe_load(LANDING_FILE.read_text()) or {}
    out = {}
    if cfg.get("home"):
        out[cfg["home"]] = ""
    for section in cfg.get("sections", []):
        if section.get("index"):
            out[section["index"]] = section["dir"]
    return out


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
        # scheme://... is a URI, not alias:path
        if path.startswith('//'):
            return None
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
        content = mask_code(filepath.read_text())
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
            ".git",
            ".build",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "_generated",
            "_template",
        ]
    try:
        filepath_str = Path(filepath).resolve().relative_to(WORKSPACE_ROOT.resolve()).as_posix()
    except ValueError:
        filepath_str = str(filepath)
    return any(pattern in filepath_str for pattern in skip_patterns)


def markdown_files(tracked):
    """Markdown files to check: tracked ones when in git, else a filesystem walk."""
    if tracked is not None:
        files = [WORKSPACE_ROOT / p for p in sorted(tracked) if p.endswith(".md")]
    else:
        files = list(WORKSPACE_ROOT.rglob("*.md"))
    return [f for f in files if not should_skip_file(f)]


def check_code_refs(aliases, tracked, verbose=False):
    """Check all code references resolve to files."""
    errors = []
    checked = 0
    
    # Find all markdown files, excluding externals, generated, and templates
    md_files = markdown_files(tracked)
    
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


def check_markdown_links(lockfile_data, tracked, verbose=False):
    """Check all internal markdown links resolve."""
    errors = []
    checked = 0
    skipped_externals = 0

    root = WORKSPACE_ROOT.resolve()
    ext_dir = (lockfile_data or {}).get("externals_dir", "externals")
    pinned = {r["name"] for r in (lockfile_data or {}).get("repos", [])}
    tdirs = tracked_dirs(tracked) if tracked is not None else None
    publish_dir = landing_publish_dirs()

    def exists(rel):
        if tracked is None:
            return (root / rel).exists()
        return rel in tracked or rel in tdirs or rel == ""

    # Find all markdown files, excluding externals, generated, and templates
    md_files = markdown_files(tracked)

    for md_file in md_files:
        src = md_file.resolve().relative_to(root).as_posix()
        base = publish_dir.get(src, src.rsplit("/", 1)[0] if "/" in src else "")
        links = find_markdown_links(md_file)
        for link_path, line_num, link_text in links:
            checked += 1

            # Handle anchors
            path_part = link_path.split('#')[0] if '#' in link_path else link_path

            if not path_part:
                continue

            # Resolve relative to the file's directory (or its published directory)
            if path_part.startswith('/'):
                target = root / path_part.lstrip('/')
            else:
                target = root / base / path_part

            target = target.resolve()
            try:
                rel = target.relative_to(root).as_posix()
            except ValueError:
                errors.append(f"{md_file}:{line_num}: Broken link (outside the repository): {link_path}")
                continue
            if rel == ".":
                rel = ""

            if exists(rel):
                if verbose:
                    print(f"  [ok] {md_file.name}: {link_path}")
                continue

            if rel.startswith(ext_dir + "/"):
                name = rel[len(ext_dir) + 1:].split("/", 1)[0]
                if name not in pinned:
                    errors.append(f"{md_file}:{line_num}: Broken link (no repo '{name}' in workspace.lock.json): {link_path}")
                    continue
                clone = root / ext_dir / name
                if not clone.exists():
                    skipped_externals += 1
                    if verbose:
                        print(f"  [skip] {link_path} - repo not cloned")
                    continue
                if target.exists():
                    if verbose:
                        print(f"  [ok] {md_file.name}: {link_path}")
                    continue

            errors.append(f"{md_file}:{line_num}: Broken link: {link_path}")

    return errors, checked, skipped_externals


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
    parser.add_argument("--skip-code-refs", action="store_true",
                        help="Do not check alias:path code refs (they resolve only against cloned externals/)")
    args = parser.parse_args()
    
    print("Checking workspace links...\n")
    
    lockfile = load_lockfile()
    if not lockfile:
        print("Warning: No workspace.lock.json found")
        aliases = {}
    else:
        aliases = get_repo_aliases(lockfile)
    
    tracked = tracked_files()
    if tracked is None:
        print("Warning: not a git checkout; checking every file on disk\n")

    total_errors = []
    total_checked = 0
    
    # Check code references
    if args.skip_code_refs:
        print("Skipping code references (--skip-code-refs)\n")
    else:
        print("Checking code references...")
        errors, checked = check_code_refs(aliases, tracked, args.verbose)
        total_errors.extend(errors)
        total_checked += checked
        print(f"  Checked {checked} code refs, {len(errors)} errors\n")
    
    # Check markdown links
    print("Checking markdown links...")
    errors, checked, skipped = check_markdown_links(lockfile, tracked, args.verbose)
    total_errors.extend(errors)
    total_checked += checked
    print(f"  Checked {checked} links, {len(errors)} errors"
          f" ({skipped} into pinned externals not cloned here, not checked)\n")
    
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
