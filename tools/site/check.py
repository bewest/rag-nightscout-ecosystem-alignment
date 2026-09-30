#!/usr/bin/env python3
"""Post-build gate for the static site (make site-check).

Fails unless:
  * the content scan (tools/site/scan.py) over build/site-src/ passes,
  * build/site/robots.txt exists and disallows everything, and
  * every HTML file under build/site/ carries
    <meta name="robots" content="noindex, nofollow"> inside <head>.
Names every failing page.
"""
import os
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "build" / "site"
META = re.compile(r'<meta\s+name=["\']robots["\']\s+content=["\']noindex,\s*nofollow["\']\s*/?>', re.I)


def main() -> int:
    if not OUT.is_dir():
        print(f"site-check: FAIL: {OUT} does not exist; run make site")
        return 1
    problems = []
    robots = OUT / "robots.txt"
    if not robots.is_file():
        problems.append("robots.txt missing")
    elif not re.search(r"^Disallow:\s*/\s*$", robots.read_text(), re.M):
        problems.append("robots.txt does not contain 'Disallow: /'")
    pages, missing = 0, []
    for root, _, files in os.walk(OUT):  # our build output, not the source tree
        for f in files:
            if not f.lower().endswith((".html", ".htm")):
                continue
            pages += 1
            p = Path(root) / f
            text = p.read_text(encoding="utf-8", errors="replace")
            head = text.split("</head>", 1)[0] if "</head>" in text else text[:20000]
            if not META.search(head):
                missing.append(str(p.relative_to(OUT)))
    if pages == 0:
        problems.append("no HTML pages found")
    for m in sorted(missing):
        print(f"site-check: no noindex meta: {m}")
    if missing:
        problems.append(f"{len(missing)} of {pages} HTML pages lack the noindex meta")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import scan
    if scan.report(scan.scan(), prefix="site-check scan") != 0:
        problems.append("content scan blocked (see lines above)")
    if problems:
        for p in problems:
            print(f"site-check: FAIL: {p}")
        return 1
    print(f"site-check: OK: noindex on {pages}/{pages} HTML pages; robots.txt disallows all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
