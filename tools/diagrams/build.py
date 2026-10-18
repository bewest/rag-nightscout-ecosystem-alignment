#!/usr/bin/env python3
"""Generate the figures drawn from data under docs/30-design/platform/diagrams/.

  build.py [-o OUTDIR] [--check]

Each module's build() returns {file name: SVG text}. --check regenerates in memory and exits 1,
naming each figure, when a committed SVG differs or is missing.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import active_state_rules  # noqa: E402
import end_encoding  # noqa: E402
import hub_active_state  # noqa: E402
from svgkit import OUT  # noqa: E402

MODULES = [hub_active_state, end_encoding, active_state_rules]


def generate():
    figs = {}
    for m in MODULES:
        for name, text in m.build().items():
            if name in figs:
                raise SystemExit(f"two modules write {name}")
            figs[name] = text
    return dict(sorted(figs.items()))


def stale(outdir):
    return [n for n, t in generate().items()
            if not (outdir / n).exists() or (outdir / n).read_text() != t]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--outdir", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        bad = stale(a.outdir)
        for n in bad:
            print(f"stale: {a.outdir / n} (run make diagrams-svg)")
        sys.exit(1 if bad else 0)
    a.outdir.mkdir(parents=True, exist_ok=True)
    for n, t in generate().items():
        (a.outdir / n).write_text(t)
        print(a.outdir / n)


if __name__ == "__main__":
    main()
