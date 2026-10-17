#!/usr/bin/env python3
"""Render the organisational control-structure diagrams from their YAML inputs with Graphviz.

  render.py [input.yaml ...]     (default: every inputs/*.yaml)

Writes <outdir>/<name>.svg, one <outdir>/<name>--<view>.svg per entry in the input's `views`,
and <outdir>/legend.svg, where outdir is given by `OUT` below.

Zoom: a node with `zoom: Z2` carries a "zoom: Z2" line, meaning the drawing named Z2 opens that
box up. Views: a view names the stakeholders it is drawn for (`focus`); their nodes, the edges
touching them and the nodes at the other end keep their colour and everything else is greyed.
A view is the same graph with only colours changed, so every view keeps the base layout.
The layout levers are the ones tools/lab/stpa-diagrams measured as holding an STPA structure:
rank=same per level, invisible edges for column order, dir=back for upward edges, and compass
ports so that control runs down the left and feedback up the right of each loop.

Each drawing sits on its own light card, so it reads the same on GitHub and on the site in
either colour scheme.
"""
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
# The Graphviz renderer published until 2026-10-17 (then tools/structure-diagrams/render.py),
# kept as the lab's baseline. It no longer writes into docs/.
OUT = HERE / "results" / "baseline"

EDGE = {
    "control": {"color": "#1f5fa8", "style": "solid"},
    "feedback": {"color": "#b5541b", "style": "dashed"},
    "funding": {"color": "#2e7d32", "style": "bold"},
    "data": {"color": "#555555", "style": "dotted"},
}
NODE = {
    "authority": "#dfe7f2",
    "entity": "#e3f0e3",
    "org": "#ffffff",
    "commons": "#f3e7d3",
    "human": "#ffffff",
    "process": "#e8e8e8",
}


def esc(s):
    return s.replace('"', '\\"').replace("\n", "\\n")


def load(path):
    m = yaml.safe_load(Path(path).read_text())
    m.setdefault("groups", [])
    m["byid"] = {n["id"]: n for n in m["nodes"]}
    m["nodes"] = sorted(m["nodes"], key=lambda n: (n["level"], n["column"]))
    return m


def loop_pairs(m):
    ctl = {(e["from"], e["to"]) for e in m["edges"] if e["kind"] == "control"}
    fb = {(e["from"], e["to"]) for e in m["edges"] if e["kind"] == "feedback"}
    return {frozenset(p) for p in ctl if (p[1], p[0]) in fb}


GREY = "#c8c8c8"


def node(n, lit=True):
    proposed = n.get("status") == "proposed"
    style = "rounded,filled" + (",dashed" if proposed else "")
    lab = esc(n["label"] + ("\n(proposed)" if proposed else "") + (f'\n[zoom: {n["zoom"]}]' if n.get("zoom") else ""))
    colours = (f'fillcolor="{NODE[n["kind"]]}"' if lit else
               f'fillcolor="#f6f6f6", color="{GREY}", fontcolor="#a0a0a0"')
    return (f'{n["id"]} [label="{lab}", style="{style}", {colours}'
            f'{", penwidth=2.2" if lit is True and n.get("_focus") else ""}];')


def edge(m, e, pairs, lit=True):
    a, b = e["from"], e["to"]
    la, lb = m["byid"][a]["level"], m["byid"][b]["level"]
    k = EDGE[e["kind"]]
    style = "dashed" if e.get("status") == "proposed" and k["style"] == "solid" else k["style"]
    col = k["color"] if lit else GREY
    attrs = [f'color="{col}"', f'fontcolor="{col}"', f"style={style}", f'label="{esc(e["label"])}"']
    if la > lb:
        # write upward edges top-down and draw them backwards, so ranks come from the hierarchy
        a, b = b, a
        attrs.append("dir=back")
    if frozenset((e["from"], e["to"])) in pairs:
        # STPA convention: control down the left, feedback up the right (every edge is
        # written top-down by now, so the tail is always the upper node)
        if e["kind"] == "control":
            attrs += ["tailport=sw", "headport=nw"]
        else:
            attrs += ["tailport=se", "headport=ne"]
    if la == lb:
        attrs.append("constraint=false")
    return f'{a} -> {b} [{", ".join(attrs)}];'


def emit(m, view=None):
    pairs = loop_pairs(m)
    focus = set(view["focus"]) if view else None
    lit_e = {id(e) for e in m["edges"] if focus is None or {e["from"], e["to"]} & focus}
    lit_n = None if focus is None else focus | {x for e in m["edges"] if id(e) in lit_e for x in (e["from"], e["to"])}
    for n in m["nodes"]:
        n["_focus"] = bool(focus and n["id"] in focus)
    title = m["title"] + (f' — {view["title"]}' if view else "")
    L = ["digraph G {",
         '  graph [rankdir=TB, newrank=true, nodesep=0.45, ranksep=0.6, splines=spline, pad=0.25, '
         f'bgcolor="#ffffff", fontname="Helvetica", fontsize=13, labelloc=t, label="{esc(title)}"];',
         '  node [shape=box, fontname="Helvetica", fontsize=11, margin="0.15,0.08", color="#333333", fontcolor="#111111"];',
         '  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7];']
    for n in m["nodes"]:
        if not n.get("group"):
            L.append("  " + node(n, lit_n is None or n["id"] in lit_n))
    for g in m["groups"]:
        L.append(f'  subgraph cluster_{g["id"]} {{ label="{esc(g["label"])}"; style="dashed"; color="#999999"; '
                 'fontsize=10; fontcolor="#555555";')
        L += ["    " + node(n, lit_n is None or n["id"] in lit_n) for n in m["nodes"] if n.get("group") == g["id"]]
        L.append("  }")
    by_level = {}
    for n in m["nodes"]:
        by_level.setdefault(n["level"], []).append(n["id"])
    for ids in by_level.values():
        L.append(f'  {{ rank=same; {"; ".join(ids)}; }}')
        L += [f"  {a} -> {b} [style=invis];" for a, b in zip(ids, ids[1:])]
    L += ["  " + edge(m, e, pairs, id(e) in lit_e) for e in m["edges"]]
    L.append("}")
    return "\n".join(L) + "\n"


def legend():
    L = ["digraph L {",
         '  graph [rankdir=LR, nodesep=0.15, ranksep=0.5, pad=0.2, bgcolor="#ffffff", fontname="Helvetica"];',
         '  node [shape=box, fontname="Helvetica", fontsize=10, margin="0.12,0.06", color="#333333", fontcolor="#111111"];',
         '  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7];']
    for i, (kind, k) in enumerate(EDGE.items()):
        L.append(f'  a{i} [shape=point, width=0.05, color="#ffffff"]; b{i} [shape=point, width=0.05, color="#ffffff"];')
        L.append(f'  a{i} -> b{i} [color="{k["color"]}", fontcolor="{k["color"]}", style={k["style"]}, label="{kind}"];')
    for kind, label in [("authority", "public authority"), ("entity", "legal entity or operator"),
                        ("commons", "shared commons"), ("org", "group or organisation")]:
        L.append(f'  k_{kind} [label="{label}", style="rounded,filled", fillcolor="{NODE[kind]}"];')
    L.append('  k_proposed [label="proposed\\n(does not exist yet)", style="rounded,filled,dashed", fillcolor="#ffffff"];')
    L.append("}")
    return "\n".join(L) + "\n"


def dot(src, out):
    subprocess.run(["dot", "-Tsvg", "-o", str(out)], input=src.encode(), check=True)


def main(paths):
    OUT.mkdir(parents=True, exist_ok=True)
    for p in paths or sorted((HERE.parents[1] / "structure-diagrams" / "inputs").glob("*.yaml")):
        m = load(p)
        dot(emit(m), OUT / (Path(p).stem + ".svg"))
        print(OUT / (Path(p).stem + ".svg"))
        for v in m.get("views", []):
            dot(emit(m, v), OUT / f'{Path(p).stem}--{v["id"]}.svg')
            print(OUT / f'{Path(p).stem}--{v["id"]}.svg')
    dot(legend(), OUT / "legend.svg")


if __name__ == "__main__":
    main(sys.argv[1:])
