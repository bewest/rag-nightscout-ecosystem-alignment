#!/usr/bin/env python3
"""Static gate for DOCS-RECORD-IDENTITY.

Fails unless docs/10-domain/record-identity-reference.md exists, names both
pinned refs (15.0.8 and dev), and its summary table has a row for every
collection x path the queue item lists: entries, treatments, devicestatus,
profile and food, each over v1, API v3 and the socket.

A row counts when a markdown table line names the collection in its first cell
and the path (v1, v3, socket) in its second cell.

    python3 tools/qc/record-identity-doc-gate.py [path]
"""
import re
import sys

DOC = sys.argv[1] if len(sys.argv) > 1 else "docs/10-domain/record-identity-reference.md"
COLLECTIONS = ["entries", "treatments", "devicestatus", "profile", "food"]
PATHS = {"v1": r"\bv1\b", "v3": r"\bv3\b", "socket": r"\bsocket\b"}
REFS = [r"15\.0\.8", r"\bdev\b"]

try:
    text = open(DOC, encoding="utf-8").read()
except OSError as err:
    print(f"FAIL: {DOC}: {err}")
    sys.exit(1)

missing = []
for ref in REFS:
    if not re.search(ref, text):
        missing.append(f"ref {ref}")

rows = []
for line in text.splitlines():
    if not line.startswith("|"):
        continue
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) >= 2:
        rows.append((cells[0].lower(), cells[1].lower()))

for col in COLLECTIONS:
    for name, pat in PATHS.items():
        if not any(col in c0 and re.search(pat, c1) for c0, c1 in rows):
            missing.append(f"{col} x {name}")

if missing:
    print("FAIL: " + DOC + " lacks: " + ", ".join(missing))
    sys.exit(1)
print(f"PASS: {DOC} covers {len(COLLECTIONS)} collections x {len(PATHS)} paths and names 15.0.8 and dev")
