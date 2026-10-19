#!/usr/bin/env python3
"""Projects and outside events by year, drawn from history/timeline.yaml.

  history_timeline.py [-o OUTDIR] [--check]

Writes <OUTDIR>/history-timeline.svg (default OUTDIR: docs/00-overview/observations/diagrams/).
--check regenerates in memory and exits 1 when the committed file differs or is missing.

One row per dated row of docs/00-overview/observations/HISTORY.md, grouped in lanes: a circle is a
first commit or a repository's creation, a diamond an event outside the projects (hosting plans,
regulatory decisions). Tinted bands are HISTORY.md's sections. Same card, font, text measure and
num() as tools/diagrams/svgkit.py, so the output is byte-stable.
"""
import argparse
import sys
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "diagrams"))
from svgkit import FAINT, FS, FS_SMALL, FS_TITLE, INK, MUTED, RULE, W, BLUE, ORANGE, line, num, svg, text  # noqa: E402

DATA = HERE / "history" / "timeline.yaml"
OUT = REPO / "docs" / "00-overview" / "observations" / "diagrams"
NAME = "history-timeline.svg"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

X0, X1, LO, HI = 196, 704, 2013, 2027
ROW, LANE, TOP = 20, 28, 112


def day(s):
    """A HISTORY date cell (YYYY-MM-DD or YYYY-MM) as a date; a month alone sits mid-month."""
    p = [int(v) for v in str(s).split("-")]
    return date(p[0], p[1], p[2] if len(p) > 2 else 15)


def x(s):
    d = day(s)
    t = d.year + (d.timetuple().tm_yday - 1) / 365.25
    return X0 + (t - LO) * (X1 - X0) / (HI - LO)


def words(s):
    d = day(s)
    return f"{MONTHS[d.month - 1]} {d.year}"


def figure(data):
    lanes = [ln["id"] for ln in data["lanes"]]
    rows = sorted(data["rows"], key=lambda r: (lanes.index(r["lane"]), str(r["date"])))
    ys, y = {}, TOP
    heads = {}
    for ln in lanes:
        heads[ln] = y
        y += LANE + 4
        for r in (r for r in rows if r["lane"] == ln):
            ys[r["key"]] = y
            y += ROW
        y += 8
    bottom = y
    b = [text(16, 26, "Projects and outside events by year, 2013–2026", FS_TITLE, weight="bold"),
         text(16, 46, "Circle: first commit or repository created. Diamond: an event outside the projects.",
              FS_SMALL, MUTED),
         text(16, 64, "Bands are the sections of the chronology (HISTORY.md §1–§4).", FS_SMALL, MUTED)]
    for i, s in enumerate(data["sections"]):
        a, z = x(s["start"]), min(x(s["end"]), X1)
        if i % 2 == 0:
            b.append(f'<rect x="{num(a)}" y="76" width="{num(z - a)}" height="{num(bottom - 76)}" fill="{FAINT}"/>')
        b.append(text((a + z) / 2, 90, s["label"], FS_SMALL, INK, "middle", "bold"))
    for yr in range(LO, HI):
        b.append(line(x(f"{yr}-01-01"), 96, x(f"{yr}-01-01"), bottom, RULE, 0.6))
        b.append(text(x(f"{yr}-07-01"), 108, str(yr), FS_SMALL, MUTED, "middle"))
    b.append(line(X0, 112, X1, 112, MUTED, 1))
    for ln in data["lanes"]:
        b.append(text(16, heads[ln["id"]] + 12, ln["label"].upper(), FS_SMALL, BLUE if ln["id"] == "hub" else MUTED, weight="bold"))
    for r in rows:
        cx, cy = x(r["date"]), ys[r["key"]]
        b.append(text(16, cy + 4, r["label"], FS))
        c = BLUE if r["lane"] == "hub" else ORANGE if r["lane"] == "out" else MUTED
        if r["lane"] == "out":
            b.append(f'<path d="M{num(cx)},{num(cy - 5.5)} L{num(cx + 5.5)},{num(cy)} L{num(cx)},{num(cy + 5.5)} '
                     f'L{num(cx - 5.5)},{num(cy)} Z" fill="{c}"/>')
        else:
            b.append(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="4.5" fill="{c}"/>')
        late = cx > 640
        b.append(text(cx - 9 if late else cx + 9, cy + 4, words(r["date"]), FS_SMALL, MUTED, "end" if late else "start"))
    per = {ln["label"]: sum(r["lane"] == ln["id"] for r in rows) for ln in data["lanes"]}
    desc = (f"{len(rows)} dated rows of the Nightscout ecosystem chronology, {min(str(r['date']) for r in rows)[:4]}"
            f" to {max(str(r['date']) for r in rows)[:4]}, in five lanes: "
            + "; ".join(f"{k} {v}" for k, v in per.items()) + ". Each row is one row of HISTORY.md.")
    return svg(W, bottom + 16, "Projects and outside events by year, 2013–2026", desc, b)


def build(data_path=DATA):
    return {NAME: figure(yaml.safe_load(Path(data_path).read_text()))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--outdir", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    figs = build()
    if a.check:
        bad = [n for n, t in figs.items() if not (a.outdir / n).exists() or (a.outdir / n).read_text() != t]
        for n in bad:
            print(f"stale: {a.outdir / n} (run make history-timeline)")
        sys.exit(1 if bad else 0)
    a.outdir.mkdir(parents=True, exist_ok=True)
    for n, t in figs.items():
        (a.outdir / n).write_text(t)
        print(a.outdir / n)


if __name__ == "__main__":
    main()
