#!/usr/bin/env python3
"""Render the results JSONL (one cell per line) into a SANITISED markdown matrix.

Sanitisation (this repo is public and the default-mode weakness is live on the
shipping release):
  * O1 shows the honest-client resolved address (a lab container address).
  * O2 shows only "protected" / "not protected" -- never the spoof value, the
    header name, or which alternate header family wins.
Full adversarial detail (spoof values, winning header families) lives only in the
private results directory.

Usage: analyze.py <results.jsonl> <out.md> <date> <dev_sha> <pr_sha>
"""
import json
import sys
from collections import defaultdict

CLIENT = "172.31.66.10"  # honest client container; correct O1 for a proxied cell


def load(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def o1_verdict(o1):
    if not o1:
        return "(no address)"
    # public table: show the honest client address, or "peer/other" if it is not
    # the real client (do not editorialise beyond correct / wrong-address).
    return o1 if o1 == CLIENT else o1


def main():
    src, out, date, dev_sha, pr_sha = sys.argv[1:6]
    rows = load(src)
    settings, topos = [], []
    grid = defaultdict(dict)
    for r in rows:
        t, s = r["topology"], r["trust_proxy"]
        if t not in topos:
            topos.append(t)
        if s not in settings:
            settings.append(s)
        grid[t][s] = r

    lines = []
    lines.append(f"# Proxy-trust lab results (SANITISED)\n")
    lines.append(f"Date: {date}  |  dev tree: `{dev_sha}`  |  PR tree: `{pr_sha}`\n")
    lines.append("O1 = resolved address for an honest client (correct = "
                 f"`{CLIENT}`). O2 = whether a caller-supplied forwarding header "
                 "can change the resolved address (protected = cannot).\n")
    lines.append("Adversarial recipes are NOT in this file; see the private results.\n")

    # O1 table
    lines.append("\n## O1 - resolved honest-client address\n")
    lines.append("| topology | " + " | ".join(f"TP={s}" for s in settings) + " |")
    lines.append("|" + "---|" * (len(settings) + 1))
    for t in topos:
        cells = []
        for s in settings:
            r = grid[t].get(s)
            cells.append(o1_verdict(r["o1_resolved"]) if r else "-")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")

    # O2 table
    lines.append("\n## O2 - resistance to a caller-supplied forwarding header\n")
    lines.append("| topology | " + " | ".join(f"TP={s}" for s in settings) + " |")
    lines.append("|" + "---|" * (len(settings) + 1))
    for t in topos:
        cells = []
        for s in settings:
            r = grid[t].get(s)
            if not r:
                cells.append("-")
            elif r["o2"] == "not-protected":
                cells.append("NOT protected")
            elif r["o2"] == "protected":
                cells.append("protected")
            else:
                cells.append(r["o2"])
        lines.append(f"| {t} | " + " | ".join(cells) + " |")

    with open(out, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"wrote {out} ({len(rows)} cells, {len(topos)} topologies x {len(settings)} settings)")


if __name__ == "__main__":
    main()
