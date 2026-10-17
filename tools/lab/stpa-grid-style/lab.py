#!/usr/bin/env python3
"""Render every input with every candidate into results/build/<diagram>/<variant>.svg.

  lab.py [input.yaml ...]   (default: tools/structure-diagrams/inputs/*.yaml and
                             tools/lab/stpa-diagrams/inputs/*.yaml)

Candidates (README has the reasons):
  dot-spline      the renderer published until 2026-10-17, kept here as baseline_dot.py (baseline)
  grid            gridstpa.py, default costs (a side entry costs less than a second bend)
  grid-z          gridstpa.py with side entries made expensive, so edges enter tops and bottoms
  neato-ortho     Graphviz neato -n2: nodes pinned at the grid positions, splines=ortho, xlabels
  elk             elkjs layered, interactive strategies seeded with the grid positions, fixed ports
  avoid           libavoid (libavoid-js): nodes at the grid positions, orthogonal routing with
                  nudging; labels by gridstpa's placer, as libavoid places none
Controls, written here with geometry chosen by construction:
  control-grid    grid positions; same-column and same-level edges straight, every other edge a Z
                  with exactly two bends; loop pairs offset left/right; labels in a column off to
                  the right, clear of every line (positive control, with known bend counts)
  control-random  seeded random positions, random two-waypoint polylines, labels centred on their
                  lines, one forced node overlap (negative control)
"""
import collections
import copy
import importlib.util
import json
import random
import re
import subprocess
import sys
from pathlib import Path

import gridstpa as gs

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OUT = HERE / "results" / "build"
INPUTS = sorted((REPO / "tools" / "structure-diagrams" / "inputs").glob("*.yaml")) + \
    sorted((REPO / "tools" / "lab" / "stpa-diagrams" / "inputs").glob("*.yaml"))


def baseline_module():
    spec = importlib.util.spec_from_file_location("render", HERE / "baseline_dot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = baseline_module()
# the old lab's inputs use node and edge kinds the published renderer does not know; give them its
# defaults here rather than change render.py
R.NODE = collections.defaultdict(lambda: "#ffffff", R.NODE, hub="#e8e8e8")
R.EDGE = dict(R.EDGE, disturbance={"color": "#888888", "style": "dotted"})


def loop_pairs(m):
    ctl = {(e["from"], e["to"]) for e in m["edges"] if e["kind"] == "control"}
    fb = {(e["from"], e["to"]) for e in m["edges"] if e["kind"] == "feedback"}
    return sorted({tuple(sorted(p)) for p in ctl if (p[1], p[0]) in fb})


def model_json(m):
    return {"title": m.get("title"), "nodes": [{k: n.get(k) for k in ("id", "level", "column", "group")} for n in m["nodes"]],
            "edges": [{k: e[k] for k in ("k", "from", "to", "kind")} for e in m["edges"]],
            "groups": m.get("groups", []), "loop_pairs": loop_pairs(m)}


# ---------------------------------------------------------------- Graphviz

def dot_spline(path):
    """The published renderer's dot source, with ids added so nodes and edges can be found."""
    m = R.load(path)
    src = R.emit(m)
    for k in m["nodes"]:
        src = re.sub(rf'^(\s+){k["id"]} \[label=', rf'\1{k["id"]} [id="n_{k["id"]}", label=', src, count=1, flags=re.M)
    lines, k = [], 0
    for line in src.split("\n"):
        if re.match(r"^\s+\w+ -> \w+ \[", line) and "style=invis" not in line:
            line = line.replace("[", f'[id="e_{k}", ', 1)
            k += 1
        lines.append(line)
    return "\n".join(lines)


def neato_ortho(m, G):
    """Nodes pinned at the grid renderer's positions (points = px), routed by Graphviz ortho."""
    H = G.height
    L = ["digraph G {",
         '  graph [splines=ortho, bgcolor="#ffffff", fontname="Helvetica", pad=0.25, '
         f'label="{gs.esc(m.get("title", ""))}", labelloc=t, fontsize=13];',
         '  node [shape=box, style="rounded,filled", fixedsize=true, fontname="Helvetica", fontsize=11, color="#333333"];',
         '  edge [fontname="Helvetica", fontsize=9, arrowsize=0.7];']
    for n in m["nodes"]:
        g = G.N[n["id"]]
        lab = "\\n".join(g["lines"])
        L.append(f'  {n["id"]} [id="n_{n["id"]}", label="{lab}", pos="{g["cx"]:.1f},{H - g["cy"]:.1f}!", '
                 f'width={g["w"] / 72:.3f}, height={g["h"] / 72:.3f}, fillcolor="{gs.NODE.get(n["kind"], "#ffffff")}"'
                 f'{", style=\"rounded,filled,dashed\"" if n.get("status") == "proposed" else ""}];')
    for e in m["edges"]:
        st = R.EDGE.get(e["kind"], R.EDGE["data"])
        lab = e["label"].replace("\n", "\\n")
        L.append(f'  {e["from"]} -> {e["to"]} [id="e_{e["k"]}", color="{st["color"]}", fontcolor="{st["color"]}", '
                 f'style={st["style"]}, xlabel="{lab}"];')
    L.append("}")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- external routers

def neutral_ports(m, G):
    """Ports independent of gridstpa's routing: bottom of the upper box to top of the lower one
    (facing sides on one level), spread evenly, ordered by the far end's x, downward edges first."""
    sides = {}
    ends = {}
    for e in m["edges"]:
        a, b = G.N[e["from"]], G.N[e["to"]]
        if a["r"] == b["r"]:
            sa, sb = ("right", "left") if a["cx"] < b["cx"] else ("left", "right")
        else:
            sa, sb = ("bottom", "top") if a["r"] < b["r"] else ("top", "bottom")
        for nid, side, other, end in ((e["from"], sa, b, "src"), (e["to"], sb, a, "dst")):
            sides.setdefault((nid, side), []).append((other["cx"] if side in ("top", "bottom") else other["cy"],
                                                      0 if G.down(e) else 1, e["k"], end))
    for (nid, side), lst in sides.items():
        lst.sort()
        n = G.N[nid]
        tb = side in ("top", "bottom")
        L = n["w"] if tb else n["h"]
        s = min(gs.PS if tb else gs.PSS, (L - 28) / (len(lst) - 1)) if len(lst) > 1 else 0
        for i, (_, _, k, end) in enumerate(lst):
            off = (i - (len(lst) - 1) / 2) * s
            x = n["cx"] + off if tb else (n["x"] if side == "left" else n["x"] + n["w"])
            y = n["cy"] + off if not tb else (n["y"] if side == "top" else n["y"] + n["h"])
            ends[(k, end)] = {"id": nid, "side": side, "x": x, "y": y}
    return ends


def run_router(engine, m, G):
    ends = neutral_ports(m, G)
    job = {"nodes": [{"id": i, "x": n["x"], "y": n["y"], "w": n["w"], "h": n["h"]} for i, n in G.N.items()],
           "edges": [{"k": e["k"], "src": ends[(e["k"], "src")], "dst": ends[(e["k"], "dst")],
                      "label": {"w": max(gs.tw(s, gs.EFS) for s in e["label"].split("\n")) + 4,
                                "h": len(e["label"].split("\n")) * gs.ELH + 2}} for e in m["edges"]]}
    r = subprocess.run(["node", str(HERE / "route.mjs"), engine], input=json.dumps(job).encode(),
                       capture_output=True, check=True)
    return json.loads(r.stdout)


def adopt_nodes(G, boxes, dy):
    for i, (x, y, w, h) in boxes.items():
        n = G.N[i]
        n.update(x=x, y=y + dy, w=w, h=h, cx=x + w / 2, cy=y + dy + h / 2)
        n["rect"] = (n["x"], n["y"], w, h)
    G.width = max(n["x"] + n["w"] for n in G.N.values()) + 12
    G.height = max(n["y"] + n["h"] for n in G.N.values()) + 12


# ---------------------------------------------------------------- controls

def label_size(e):
    lines = e["label"].split("\n")
    return max(gs.tw(s, gs.EFS) for s in lines) + 4, len(lines) * gs.ELH + 2


def control_grid(m, G):
    pairs = {frozenset(p) for p in loop_pairs(m)}
    P, expected = {}, {}
    for e in m["edges"]:
        a, b = G.N[e["from"]], G.N[e["to"]]
        u, l = (a, b) if (a["r"], a["c"]) <= (b["r"], b["c"]) else (b, a)
        d = (-10 if e["kind"] == "control" else 10) if frozenset((e["from"], e["to"])) in pairs else ((e["k"] % 5) - 2) * 5
        if u["r"] == l["r"]:
            pts = [(u["x"] + u["w"], u["cy"] + d), (l["x"], l["cy"] + d)]
        elif u["c"] == l["c"]:
            pts = [(u["cx"] + d, u["y"] + u["h"]), (l["cx"] + d, l["y"])]
        else:
            yg = sum(G.gap_y(u["r"])) / 2 + (d if l["cx"] > u["cx"] else -d)
            pts = [(u["cx"] + d, u["y"] + u["h"]), (u["cx"] + d, yg), (l["cx"] + d, yg), (l["cx"] + d, l["y"])]
        if e["from"] != u["id"]:
            pts = pts[::-1]
        P[e["k"]] = pts
        expected[e["k"]] = len(pts) - 2
    x0 = max(n["x"] + n["w"] for n in G.N.values()) + 60
    boxes, y = {}, 40
    for e in m["edges"]:
        w, h = label_size(e)
        boxes[e["k"]] = (0, (x0, y, w, h), "right")
        y += h + 8
    G.finish(P, boxes)
    return expected


def control_random(m, G, seed=7):
    rnd = random.Random(seed)
    W, H = G.width, G.height
    ids = list(G.N)
    for i in ids:
        n = G.N[i]
        n["x"], n["y"] = rnd.uniform(0, W - n["w"]), rnd.uniform(40, H - n["h"])
    G.N[ids[1]]["x"], G.N[ids[1]]["y"] = G.N[ids[0]]["x"] + 12, G.N[ids[0]]["y"] + 8   # forced overlap
    for n in G.N.values():
        n.update(cx=n["x"] + n["w"] / 2, cy=n["y"] + n["h"] / 2)
        n["rect"] = (n["x"], n["y"], n["w"], n["h"])
    P, boxes = {}, {}
    for e in m["edges"]:
        a, b = G.N[e["from"]], G.N[e["to"]]
        pts = [(a["cx"], a["cy"]), (rnd.uniform(0, W), rnd.uniform(40, H)), (rnd.uniform(0, W), rnd.uniform(40, H)),
               (b["cx"], b["cy"])]
        P[e["k"]] = pts
        mx, my = (pts[1][0] + pts[2][0]) / 2, (pts[1][1] + pts[2][1]) / 2
        w, h = label_size(e)
        boxes[e["k"]] = (0, (mx - w / 2, my - h / 2, w, h), "center")
    G.finish(P, boxes)


# ---------------------------------------------------------------- driver

def main(paths):
    for path in paths or INPUTS:
        dia = Path(path).stem
        d = OUT / dia
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*"):
            f.unlink()
        m = gs.load(path)
        (d / "model.json").write_text(json.dumps(model_json(m), indent=1))
        (d / "dot-spline.dot").write_text(dot_spline(path))
        subprocess.run(["dot", "-Tsvg", "-o", str(d / "dot-spline.svg"), str(d / "dot-spline.dot")], check=True)
        G = gs.Grid(m)
        (d / "grid.svg").write_text(gs.svg(m, G))
        Gz = gs.Grid(m, side_penalty=40)
        (d / "grid-z.svg").write_text(gs.svg(m, Gz))
        (d / "neato-ortho.dot").write_text(neato_ortho(m, G))
        r = subprocess.run(["neato", "-n2", "-Tsvg", "-o", str(d / "neato-ortho.svg"), str(d / "neato-ortho.dot")],
                           capture_output=True, text=True)
        (d / "neato-ortho.log").write_text(r.stderr)
        # elk: ELK places nodes, routes and labels; drawn with gridstpa's styles
        res = run_router("elk", m, G)
        Ge = copy.deepcopy(G)
        adopt_nodes(Ge, res["nodes"], Ge.title_h)
        P = {int(k): [(x, y + Ge.title_h) for x, y in v] for k, v in res["edges"].items()}
        labels = {int(k): (0, (x, y + Ge.title_h, w, h), "center") for k, (x, y, w, h) in res["labels"].items()}
        Ge.finish(P, labels)
        (d / "elk.svg").write_text(gs.svg(m, Ge))
        # avoid: grid positions, libavoid routes, gridstpa's label placer
        res = run_router("avoid", m, G)
        Ga = copy.deepcopy(G)
        Ga.finish({int(k): [tuple(p) for p in v] for k, v in res["edges"].items()})
        (d / "avoid.svg").write_text(gs.svg(m, Ga))
        Gc = copy.deepcopy(G)
        expected = control_grid(m, Gc)
        (d / "control-grid.svg").write_text(gs.svg(m, Gc))
        (d / "control-grid.expected.json").write_text(json.dumps({"bends": expected}))
        Gr = copy.deepcopy(G)
        control_random(m, Gr)
        (d / "control-random.svg").write_text(gs.svg(m, Gr))
        print(d)


if __name__ == "__main__":
    main(sys.argv[1:])
