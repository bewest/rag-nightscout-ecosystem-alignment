#!/usr/bin/env python3
"""
Check markdown image references in the alignment workspace.

This tool focuses specifically on embedded images in markdown files:
1. Markdown image syntax: ![alt](path)
2. HTML image tags: <img src="path">

It skips common third-party and generated trees so the output stays focused on
repository-authored reports and documentation.

Usage:
    python tools/check_markdown_images.py
    python tools/check_markdown_images.py docs/60-research
    python tools/check_markdown_images.py --json
"""

import argparse
import json
import re
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKIP_PATTERNS = (
    "externals",
    ".git",
    ".build",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "_generated",
    "_template",
)
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HTML_IMAGE_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
SKIP_LINK_PREFIXES = ("http://", "https://", "mailto:", "data:", "#")


def should_skip_path(path, skip_patterns=None):
    """Return True when a path should be excluded from scanning."""
    patterns = skip_patterns or DEFAULT_SKIP_PATTERNS
    path_str = str(path)
    return any(pattern in path_str for pattern in patterns)


def iter_markdown_files(root, skip_patterns=None):
    """Yield markdown files under root, excluding skipped paths."""
    for md_file in root.rglob("*.md"):
        if should_skip_path(md_file, skip_patterns):
            continue
        yield md_file


def find_image_links_in_file(filepath):
    """Return embedded image links in a markdown file."""
    findings = []
    try:
        content = filepath.read_text(errors="ignore")
    except OSError as exc:
        return [{"file": str(filepath), "line": 0, "link": "", "error": str(exc)}]

    for line_num, line in enumerate(content.splitlines(), start=1):
        for match in MARKDOWN_IMAGE_RE.finditer(line):
            findings.append(
                {
                    "file": filepath,
                    "line": line_num,
                    "link": match.group(2),
                    "alt": match.group(1),
                    "syntax": "markdown",
                }
            )
        for match in HTML_IMAGE_RE.finditer(line):
            findings.append(
                {
                    "file": filepath,
                    "line": line_num,
                    "link": match.group(1),
                    "alt": "",
                    "syntax": "html",
                }
            )
    return findings


def resolve_link_target(markdown_file, link_path, workspace_root):
    """Resolve a markdown image path to an absolute target path."""
    path_part = link_path.split("#", 1)[0]
    if not path_part:
        return None
    if path_part.startswith("/"):
        return (workspace_root / path_part.lstrip("/")).resolve()
    return (markdown_file.parent / path_part).resolve()


def audit_image_links(root, skip_patterns=None, workspace_root=None):
    """Audit embedded markdown images under root."""
    checked = 0
    missing = []
    workspace_root = workspace_root.resolve() if workspace_root else root.resolve()

    for md_file in iter_markdown_files(root, skip_patterns):
        for finding in find_image_links_in_file(md_file):
            if "error" in finding:
                missing.append(
                    {
                        "file": finding["file"],
                        "line": finding["line"],
                        "link": finding["link"],
                        "reason": finding["error"],
                    }
                )
                continue

            link_path = finding["link"]
            if link_path.startswith(SKIP_LINK_PREFIXES):
                continue

            checked += 1
            target = resolve_link_target(md_file, link_path, workspace_root)
            if target is None or not target.exists():
                missing.append(
                    {
                        "file": str(md_file),
                        "line": finding["line"],
                        "link": link_path,
                        "syntax": finding["syntax"],
                        "target": None if target is None else str(target),
                    }
                )

    return {"checked": checked, "missing": missing}


def parse_args():
    parser = argparse.ArgumentParser(description="Check markdown image references")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional paths to scan relative to the repository root",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output",
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Additional substring pattern to skip during scanning",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    scan_roots = [WORKSPACE_ROOT / path for path in args.paths] if args.paths else [WORKSPACE_ROOT]
    skip_patterns = DEFAULT_SKIP_PATTERNS + tuple(args.skip)

    total_checked = 0
    total_missing = []
    for scan_root in scan_roots:
        root = scan_root.resolve()
        if not root.exists():
            print(f"Missing scan root: {scan_root}", file=sys.stderr)
            return 2
        results = audit_image_links(root, skip_patterns=skip_patterns, workspace_root=WORKSPACE_ROOT)
        total_checked += results["checked"]
        total_missing.extend(results["missing"])

    if args.json:
        print(json.dumps({"checked": total_checked, "missing": total_missing}, indent=2))
    else:
        print("Checking markdown images...\n")
        print(f"Checked {total_checked} embedded image links")
        print(f"Missing {len(total_missing)} image targets\n")
        for item in total_missing:
            print(f"- {item['file']}:{item['line']}: {item['link']}")

    return 1 if total_missing else 0


if __name__ == "__main__":
    sys.exit(main())
