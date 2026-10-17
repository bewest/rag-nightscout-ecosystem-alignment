#!/usr/bin/env python3
"""results/metrics.json -> results/metrics.md: a totals table, the control checks, per-diagram tables.

  report.py results/metrics.json > results/metrics.md

Columns:
  bends      mean total turning per edge, in right angles (a straight line 0, an L 1, a Z 2; a spline
             counts its curvature)
  axis       share of all edge length running horizontal or vertical (within 3 degrees); sampling at
             2 px puts the corners of an orthogonal route just under 1.0 (control-grid: 0.993-0.997)
  cross      edge crossings away from nodes          overlap  edge pairs drawn on top of each other
  through    edge passes through a node it does not touch
  lbl/line   label text runs lying over any edge line / all text runs outside nodes
  lbl/lbl    text runs overlapping other text runs
  loops      control-feedback pairs: control left of feedback / both straight vertical / parallel at a
             constant separation (same number of bends, separation varying by <= max(8 px, half its median))
  grid       levels and columns whose node centres spread by more than 2 px / levels and columns with 2+ nodes
  area       drawing area per node, viewBox units squared (Graphviz: points; others: px; 1:1 at these sizes)
"""
import json
import sys
from collections import defaultdict

ORDER = ["dot-spline", "grid", "grid-z", "neato-ortho", "elk", "avoid", "control-grid", "control-random"]


def frac(rows, key):
    a = sum(r[key][0] for r in rows)
    b = sum(r[key][1] for r in rows)
    return f"{a}/{b}"


def main(path):
    rows = [r for r in json.load(open(path)) if "found" in r]
    bad = [r for r in rows if r["found"]["missing_nodes"] or r["found"]["missing_edges"]]
    ok = [r for r in rows if r not in bad]
    by = defaultdict(list)
    for r in ok:
        by[r["variant"]].append(r)
    dias = sorted({r["diagram"] for r in rows})
    print(f"# Metrics, all {len(dias)} inputs\n")
    print("Columns:\n\n```" + __doc__.split("Columns:")[1] + "```\n")
    print("Totals over every input (bends, axis and area: mean of the per-diagram values).\n")
    print("| variant | bends | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left | loops straight | loops parallel | grid misaligned | area/node |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for v in ORDER:
        R = by[v]
        if not R:
            continue
        mean = lambda k: sum(r[k] for r in R) / len(R)
        print(f"| `{v}` | {mean('bends_mean'):.2f} | {mean('axis_share'):.3f} | {sum(r['crossings'] for r in R)} | "
              f"{sum(r['edge_overlaps'] for r in R)} | {sum(r['edges_through_nodes'] for r in R)} | "
              f"{frac(R, 'label_over_line')} | {sum(r['label_collisions'] for r in R)} | {frac(R, 'loops_control_left')} | "
              f"{frac(R, 'loops_straight')} | {frac(R, 'loops_parallel')} | {frac(R, 'grid_misaligned')} | "
              f"{mean('area_per_node'):.0f} |")
    if bad:
        print("\nNot scored (nodes or edges not identified): " + ", ".join(f'{r["diagram"]}/{r["variant"]}' for r in bad))
    # controls: each metric must be worse on control-random than on control-grid on every input
    print("\n## Controls\n")
    print("A metric is shown to discriminate when `control-random` scores worse than `control-grid` on every "
          "input. `bends check` is the largest gap between the measured turning of a `control-grid` edge "
          "and the bend count it was constructed with.\n")
    cg = {r["diagram"]: r for r in by["control-grid"]}
    cr = {r["diagram"]: r for r in by["control-random"]}
    checks = [("bends", lambda r: r["bends_mean"], 1), ("axis", lambda r: r["axis_share"], -1),
              ("crossings", lambda r: r["crossings"], 1), ("overlaps", lambda r: r["edge_overlaps"], 1),
              ("through", lambda r: r["edges_through_nodes"], 1), ("lbl/line", lambda r: r["label_over_line"][0], 1),
              ("lbl/lbl", lambda r: r["label_collisions"], 1), ("loops left", lambda r: r["loops_control_left"][0], -1),
              ("loops straight", lambda r: r["loops_straight"][0], -1), ("loops parallel", lambda r: r["loops_parallel"][0], -1),
              ("grid dev", lambda r: r["grid_max_dev"], 1)]
    print("| metric | random worse on | random equal on | random better on |")
    print("|---|---|---|---|")
    for name, f, sign in checks:
        w = [d for d in cg if sign * (f(cr[d]) - f(cg[d])) > 0]
        e = [d for d in cg if f(cr[d]) == f(cg[d])]
        b = [d for d in cg if sign * (f(cr[d]) - f(cg[d])) < 0]
        print(f"| {name} | {len(w)}/{len(cg)} | {', '.join(e) or '—'} | {', '.join(b) or '—'} |")
    print(f"\nbends check, max error over all inputs: {max(r['bends_check_max_err'] for r in cg.values())}\n")
    # per diagram
    print("## Per diagram\n")
    for d in dias:
        print(f"### {d}\n")
        print("| variant | bends (max) | axis | cross | overlap | through | lbl/line | lbl/lbl | loops left / straight / parallel | grid | size |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for v in ORDER:
            r = next((r for r in ok if r["diagram"] == d and r["variant"] == v), None)
            if not r:
                continue
            L = r["loops_control_left"][1]
            print(f"| `{v}` | {r['bends_mean']:.2f} ({r['bends_max']:.1f}) | {r['axis_share']:.3f} | {r['crossings']} | "
                  f"{r['edge_overlaps']} | {r['edges_through_nodes']} | {r['label_over_line'][0]}/{r['label_over_line'][1]} | "
                  f"{r['label_collisions']} | {r['loops_control_left'][0]} / {r['loops_straight'][0]} / {r['loops_parallel'][0]} of {L} | "
                  f"{r['grid_misaligned'][0]}/{r['grid_misaligned'][1]} | {r['width']}×{r['height']} |")
        print()


if __name__ == "__main__":
    main(sys.argv[1])
