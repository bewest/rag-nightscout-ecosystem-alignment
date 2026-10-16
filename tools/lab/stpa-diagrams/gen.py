#!/usr/bin/env python3
"""Emit one diagram source per tool variant from a tool-neutral input.

  gen.py <input.yaml> <outdir> [--mutate]

Every variant draws the same nodes and edges; each uses the layout hints its tool offers
(dot: rank=same, ports, dir=back; PlantUML: arrow directions and hidden links; Mermaid and
D2: declaration order only, plus D2's grid). `--mutate` adds the input's `mutation` edges.

Two controls are written as finished SVG, with geometry chosen here rather than by a tool:
  control-grid.svg    every node at its (column, level); loop pairs offset left/right
  control-random.svg  seeded random positions, straight edges
"""
import json
import random
import sys
from pathlib import Path

import yaml

KINDS = {
    "control": {"color": "#1f5fa8", "style": "solid"},
    "feedback": {"color": "#b5541b", "style": "dashed"},
    "data": {"color": "#666666", "style": "dotted"},
    "disturbance": {"color": "#888888", "style": "dotted"},
}
SHADED = {"process", "hub"}


def load(path, mutate):
    m = yaml.safe_load(Path(path).read_text())
    m.setdefault("groups", [])
    edges = list(m["edges"]) + (list(m.get("mutation", [])) if mutate else [])
    for k, e in enumerate(edges):
        e["k"] = k
    m["edges"] = edges
    m["byid"] = {n["id"]: n for n in m["nodes"]}
    # declaration order: top to bottom, left to right
    m["nodes"] = sorted(m["nodes"], key=lambda n: (n["level"], n["column"]))
    return m


def loop_pairs(m):
    """Unordered node pairs joined by both a control edge and a feedback edge."""
    ctl = {(e["from"], e["to"]) for e in m["edges"] if e["kind"] == "control"}
    fb = {(e["from"], e["to"]) for e in m["edges"] if e["kind"] == "feedback"}
    return {frozenset(p) for p in ctl if (p[1], p[0]) in fb}


def levels(m):
    out = {}
    for n in m["nodes"]:
        out.setdefault(n["level"], []).append(n)
    return out


# ---------------------------------------------------------------- Graphviz

def emit_dot(m, ortho=False):
    pairs = loop_pairs(m)
    L = []
    L.append("digraph G {")
    L.append('  graph [rankdir=TB, newrank=true, nodesep=0.5, ranksep=0.65, bgcolor="transparent", '
             f'splines={"ortho" if ortho else "spline"}, fontname="Helvetica"];')
    L.append('  node [shape=box, style="rounded", fontname="Helvetica", fontsize=11, margin="0.15,0.08"];')
    L.append('  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7];')
    for n in m["nodes"]:
        if n.get("group"):
            continue
        L.append("  " + dot_node(n))
    for g in m["groups"]:
        L.append(f'  subgraph cluster_{g["id"]} {{ label="{g["label"]}"; style="dashed"; color="#999999";')
        for n in m["nodes"]:
            if n.get("group") == g["id"]:
                L.append("    " + dot_node(n))
        L.append("  }")
    for lv, ns in sorted(levels(m).items()):
        ids = [n["id"] for n in ns]
        L.append(f'  {{ rank=same; {"; ".join(ids)}; }}')
        for a, b in zip(ids, ids[1:]):
            L.append(f"  {a} -> {b} [style=invis];")
    for e in m["edges"]:
        L.append("  " + dot_edge(m, e, pairs, ortho))
    L.append("}")
    return "\n".join(L) + "\n"


def dot_node(n):
    fill = ', style="rounded,filled", fillcolor="#e8e8e8"' if n["kind"] in SHADED else ""
    lab = n["label"].replace("\n", "\\n")
    return f'{n["id"]} [id="n_{n["id"]}", label="{lab}"{fill}];'


def dot_edge(m, e, pairs, ortho):
    a, b = e["from"], e["to"]
    la, lb = m["byid"][a]["level"], m["byid"][b]["level"]
    k = KINDS[e["kind"]]
    lab = e["label"].replace("\n", "\\n")
    attrs = [f'id="e_{e["k"]}"', f'color="{k["color"]}"', f'fontcolor="{k["color"]}"', f'style={k["style"]}',
             f'{"xlabel" if ortho else "label"}="{lab}"']
    up = la > lb
    if up:
        # write upward edges top-down and draw them backwards, so ranks come from the hierarchy
        a, b = b, a
        attrs.append("dir=back")
    if frozenset((e["from"], e["to"])) in pairs:
        # STPA convention: control down the left, feedback up the right
        if e["kind"] == "control":
            attrs += ["tailport=sw", "headport=nw"]
        elif e["kind"] == "feedback":
            attrs += ["tailport=se", "headport=ne"]
    if la == lb:
        attrs.append("constraint=false")
    return f'{a} -> {b} [{", ".join(attrs)}];'


# ---------------------------------------------------------------- D2

def d2_path(m, nid):
    g = m["byid"][nid].get("group")
    return f"{g}.{nid}" if g else nid


def d2_str(s):
    return '"' + s.replace('"', '\\"').replace("\n", "\\n") + '"'


def emit_d2(m, grid=False):
    L = ["direction: down", ""]
    L.append("classes: {")
    for name, k in KINDS.items():
        dash = {"solid": 0, "dashed": 4, "dotted": 2}[k["style"]]
        L.append(f"  {name}: {{ style: {{ stroke: \"{k['color']}\"; font-color: \"{k['color']}\"; "
                 f"stroke-dash: {dash} }} }}")
    L.append("  shaded: { style: { fill: \"#e8e8e8\" } }")
    L.append("  plain: { style: { fill: \"#ffffff\" } }")
    L.append("}")
    L.append("")
    if grid:
        # grid: one cell per (level, column); containers are dropped because a grid cell holds one shape
        lv = sorted({n["level"] for n in m["nodes"]})
        cols = sorted({n["column"] for n in m["nodes"]})
        at = {(n["level"], n["column"]): n for n in m["nodes"]}
        L.append(f"grid-rows: {len(lv)}")
        L.append(f"grid-columns: {len(cols)}")
        L.append("grid-gap: 60")
        for r in lv:
            for c in cols:
                n = at.get((r, c))
                if n:
                    L.append(f'{n["id"]}: {d2_str(n["label"])} {{ class: {"shaded" if n["kind"] in SHADED else "plain"} }}')
                else:
                    L.append(f"_cell_{r}_{c}: \"\" {{ style.opacity: 0 }}")
        L.append("")
        for e in m["edges"]:
            L.append(f'{e["from"]} -> {e["to"]}: {d2_str(e["label"])} {{ class: {e["kind"]} }}')
        return "\n".join(L) + "\n"
    for n in m["nodes"]:
        if not n.get("group"):
            L.append(f'{n["id"]}: {d2_str(n["label"])} {{ class: {"shaded" if n["kind"] in SHADED else "plain"} }}')
    for g in m["groups"]:
        L.append(f'{g["id"]}: {d2_str(g["label"])} {{')
        L.append('  style: { stroke-dash: 4; fill: "transparent" }')
        for n in m["nodes"]:
            if n.get("group") == g["id"]:
                L.append(f'  {n["id"]}: {d2_str(n["label"])} {{ class: {"shaded" if n["kind"] in SHADED else "plain"} }}')
        L.append("}")
    L.append("")
    for e in m["edges"]:
        L.append(f'{d2_path(m, e["from"])} -> {d2_path(m, e["to"])}: {d2_str(e["label"])} {{ class: {e["kind"]} }}')
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- Mermaid

def emit_mermaid(m, layout):
    L = ["---", "config:", f"  layout: {layout}", "  flowchart:", "    curve: basis", "---", "flowchart TB"]
    for n in m["nodes"]:
        if not n.get("group"):
            L.append("  " + mmd_node(n))
    for g in m["groups"]:
        L.append(f'  subgraph {g["id"]}["{g["label"]}"]')
        for n in m["nodes"]:
            if n.get("group") == g["id"]:
                L.append("    " + mmd_node(n))
        L.append("  end")
    arrows = {"solid": "-->", "dashed": "-.->", "dotted": "-.->"}
    for e in m["edges"]:
        lab = e["label"].replace("\n", "<br/>")
        L.append(f'  {e["from"]} e{e["k"]}@{arrows[KINDS[e["kind"]]["style"]]}|"{lab}"| {e["to"]}')
    for e in m["edges"]:
        k = KINDS[e["kind"]]
        L.append(f'  linkStyle {e["k"]} stroke:{k["color"]},color:{k["color"]}')
    L.append("  classDef shaded fill:#e8e8e8,stroke:#333")
    L.append("  classDef plain fill:#ffffff,stroke:#333")
    for n in m["nodes"]:
        L.append(f'  class {n["id"]} {"shaded" if n["kind"] in SHADED else "plain"}')
    return "\n".join(L) + "\n"


def mmd_node(n):
    return f'{n["id"]}("{n["label"].replace(chr(10), "<br/>")}")'


# ---------------------------------------------------------------- PlantUML

def emit_puml(m):
    L = ["@startuml", "skinparam backgroundColor transparent", "skinparam defaultFontName Helvetica",
         "skinparam rectangle {", "  RoundCorner 10", "  BackgroundColor white", "}", "skinparam ArrowFontSize 9", ""]
    for n in m["nodes"]:
        if not n.get("group"):
            L.append(puml_node(n))
    for g in m["groups"]:
        L.append(f'package "{g["label"]}" as {g["id"]} {{')
        for n in m["nodes"]:
            if n.get("group") == g["id"]:
                L.append("  " + puml_node(n))
        L.append("}")
    L.append("")
    for lv, ns in sorted(levels(m).items()):
        for a, b in zip(ns, ns[1:]):
            L.append(f'{a["id"]} -[hidden]right- {b["id"]}')
    for e in m["edges"]:
        la, lb = m["byid"][e["from"]]["level"], m["byid"][e["to"]]["level"]
        d = "down" if la < lb else "up" if la > lb else "right"
        k = KINDS[e["kind"]]
        st = {"solid": "", "dashed": ",dashed", "dotted": ",dotted"}[k["style"]]
        lab = e["label"].replace("\n", "\\n")
        m.setdefault("puml_lines", {})[len(L)] = e["k"]  # PlantUML's data-source-line is 0-based
        L.append(f'{e["from"]} -[{k["color"]}{st}]{d}-> {e["to"]} : <color:{k["color"]}>{lab}')
    L.append("@enduml")
    return "\n".join(L) + "\n"


def puml_node(n):
    fill = " #e8e8e8" if n["kind"] in SHADED else ""
    return f'rectangle "{n["label"].replace(chr(10), chr(92) + "n")}" as {n["id"]}{fill}'


# ---------------------------------------------------------------- controls

BW, BH = 170, 46


def svg_controls(m, positions, offset_pairs):
    """Draw nodes at the given centres and straight edges; loop pairs split left/right if asked."""
    pairs = loop_pairs(m)
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    W, H = max(xs) + BW, max(ys) + BH + 20
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
           f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="Helvetica" font-size="11">']
    out.append('<defs><marker id="a" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" '
               'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>')
    for n in m["nodes"]:
        x, y = positions[n["id"]]
        fill = "#e8e8e8" if n["kind"] in SHADED else "#ffffff"
        out.append(f'<g class="node" data-id="{n["id"]}"><rect x="{x - BW/2:.1f}" y="{y - BH/2:.1f}" width="{BW}" '
                   f'height="{BH}" rx="8" fill="{fill}" stroke="#333"/>')
        for i, line in enumerate(n["label"].split("\n")):
            out.append(f'<text x="{x:.1f}" y="{y - 4 + i*13:.1f}" text-anchor="middle">{line}</text>')
        out.append("</g>")
    for e in m["edges"]:
        (x1, y1), (x2, y2) = positions[e["from"]], positions[e["to"]]
        dx = 0
        if offset_pairs and frozenset((e["from"], e["to"])) in pairs:
            dx = -30 if e["kind"] == "control" else 30
        sy1 = y1 + (BH/2 if y2 > y1 else -BH/2 if y2 < y1 else 0)
        sy2 = y2 - (BH/2 if y2 > y1 else -BH/2 if y2 < y1 else 0)
        sx1 = x1 + dx + (0 if y1 != y2 else (BW/2 if x2 > x1 else -BW/2))
        sx2 = x2 + dx + (0 if y1 != y2 else (-BW/2 if x2 > x1 else BW/2))
        k = KINDS[e["kind"]]
        dash = {"solid": "", "dashed": ' stroke-dasharray="6 4"', "dotted": ' stroke-dasharray="2 3"'}[k["style"]]
        out.append(f'<path class="edge" data-k="{e["k"]}" d="M{sx1:.1f},{sy1:.1f} L{sx2:.1f},{sy2:.1f}" '
                   f'stroke="{k["color"]}" fill="none"{dash} marker-end="url(#a)"/>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def grid_positions(m):
    cols = sorted({n["column"] for n in m["nodes"]})
    return {n["id"]: (BW/2 + 20 + cols.index(n["column"]) * (BW + 60), BH/2 + 20 + n["level"] * (BH + 70))
            for n in m["nodes"]}


def random_positions(m, seed):
    rnd = random.Random(seed)
    g = grid_positions(m)
    W = max(p[0] for p in g.values())
    H = max(p[1] for p in g.values())
    pos = {nid: (BW/2 + rnd.uniform(0, W), BH/2 + rnd.uniform(0, H)) for nid in g}
    # make one collision certain: the last node is drawn 6 px from the first
    ids = list(pos)
    pos[ids[-1]] = (pos[ids[0]][0] + 6, pos[ids[0]][1] + 6)
    return pos


def main():
    src, outdir = sys.argv[1], Path(sys.argv[2])
    mutate = "--mutate" in sys.argv
    m = load(src, mutate)
    outdir.mkdir(parents=True, exist_ok=True)
    files = {
        "dot-spline.dot": emit_dot(m),
        "dot-ortho.dot": emit_dot(m, ortho=True),
        "d2-dagre.d2": emit_d2(m),
        "d2-elk.d2": emit_d2(m),
        "d2-grid.d2": emit_d2(m, grid=True),
        "mermaid-dagre.mmd": emit_mermaid(m, "dagre"),
        "mermaid-elk.mmd": emit_mermaid(m, "elk"),
        "plantuml.puml": emit_puml(m),
        "control-grid.svg": svg_controls(m, grid_positions(m), offset_pairs=True),
        "control-random.svg": svg_controls(m, random_positions(m, 7), offset_pairs=False),
    }
    for name, text in files.items():
        (outdir / name).write_text(text)
    # the model the measurement reads: ids, levels, columns, groups, edges with their k
    (outdir / "model.json").write_text(json.dumps(
        {"title": m["title"], "nodes": m["nodes"], "groups": m["groups"], "edges": m["edges"],
         "loop_pairs": [sorted(p) for p in loop_pairs(m)], "puml_lines": m["puml_lines"]}, indent=1))


if __name__ == "__main__":
    main()
