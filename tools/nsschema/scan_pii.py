"""scan_pii.py — find personal data in files that are committed to the repo.

``redact.py`` protects what the *census* emits. It cannot protect what was
committed before it existed, or what someone adds by hand: test fixtures
captured from live Nightscout sites, saved API responses, debugging dumps.

This applies the same policy in reverse — reads a JSON file, walks every
value, and reports anything the census would have refused to publish:

* a value under an identifying field name (the denylist and suffix rules)
* a value whose *shape* is personal (timestamps, clock times, timezones,
  reverse-DNS bundle identifiers, non-ASCII glyphs)
* long opaque tokens, which are credentials more often than not

It reports **paths and categories, never the values themselves** — a
report about a leak should not be a second copy of it. Use ``--count`` to
see how many distinct values each path holds.

Exit status is 1 when anything is found, so it can gate CI.

Usage::

    python3 -m nsschema.scan_pii tools/ns2parquet/fixtures/*.json
    python3 -m nsschema.scan_pii --count specs/fixtures/**/*.json
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import redact

# Opaque high-entropy strings: APNs device tokens, API keys, session ids.
_OPAQUE = re.compile(r"^[0-9a-fA-F]{32,}$|^[A-Za-z0-9_\-]{40,}$")

CATEGORIES = ("identifying-name", "personal-shape", "opaque-token")


def categorize(path: str, value: str):
    if redact.is_denied(path):
        return "identifying-name"
    if _OPAQUE.match(value):
        return "opaque-token"
    if redact.is_personal_shape(value):
        return "personal-shape"
    return None


def scan_document(doc, findings, prefix=""):
    if isinstance(doc, dict):
        for key, value in doc.items():
            scan_document(value, findings, f"{prefix}.{key}" if prefix else key)
    elif isinstance(doc, list):
        for item in doc:
            scan_document(item, findings, f"{prefix}[]")
    elif isinstance(doc, str) and doc:
        category = categorize(prefix, doc)
        if category:
            findings[(prefix, category)].add(doc)


def scan_file(path: Path):
    try:
        doc = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        return None, str(exc)
    findings = defaultdict(set)
    scan_document(doc, findings)
    return findings, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--count", action="store_true",
                    help="show how many distinct values each path holds")
    ap.add_argument("--category", action="append", choices=CATEGORIES,
                    help="report only these categories")
    args = ap.parse_args(argv)

    wanted = set(args.category or CATEGORIES)
    total = 0
    for path in args.paths:
        findings, error = scan_file(path)
        if error:
            print(f"{path}: unreadable ({error})", file=sys.stderr)
            continue
        rows = sorted((p, c, len(v)) for (p, c), v in findings.items() if c in wanted)
        if not rows:
            continue
        print(f"{path}")
        for field, category, n in rows:
            suffix = f"  ({n} distinct)" if args.count else ""
            print(f"    {category:17s} {field}{suffix}")
            total += 1
    if total:
        print(f"\n{total} field/category findings. Values are deliberately not "
              f"printed.", file=sys.stderr)
        return 1
    print("no personal data found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
