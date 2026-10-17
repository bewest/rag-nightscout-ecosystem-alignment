#!/usr/bin/env python3
"""Deterministic grid renderer for STPA control structures, emitting SVG directly.

  gridstpa.py [-o OUTDIR] [input.yaml ...]   (default: tools/structure-diagrams/inputs/*.yaml)

Reads the same YAML as tools/structure-diagrams/render.py and writes <OUTDIR>/<name>.svg, one
<name>--<view>.svg per view and legend.svg (default OUTDIR: results/grid-render/ next to this file).

Layout, in the order it happens:
  1. Every node sits in the cell (column, level) of a grid; columns and rows are as wide and tall
     as their largest box, so centres line up exactly.
  2. Each edge picks the route with the fewest bends that touches no other box: straight down,
     an L (out of a box side, into the top of the other), a Z (down, across in the gap between
     two rows, down) or round a column gap ("corridor"). Edges between the same two boxes share
     one route shape, so a control/feedback pair runs as two parallel lines.
  3. Ports on each box side and tracks in each gap are ordered, then adjacent swaps are tried
     until no swap removes a crossing. Control (downward) ports sit left of feedback (upward).
  4. Labels go beside a segment, never on it: control labels left of the line, feedback right,
     chosen among candidates by a collision score. If a label cannot be placed cleanly, the gaps
     near it grow and the layout is redone.

Optional YAML additions (all backwards compatible):
  bands:  [{label: "Legal", levels: [0, 1]}, ...]   horizontal bands behind the rows, labelled
  edge `route`: straight | z | l | corridor            restrict the route shape
  edge `via`: N          z: the gap below level N; corridor: the gap left of column N
  edge `label_side`: left | right | above | below
"""
import argparse
import math
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
INPUTS = HERE.parents[1] / "structure-diagrams" / "inputs"

EDGE = {
    "control": {"color": "#1f5fa8", "dash": None, "width": 1.4},
    "feedback": {"color": "#b5541b", "dash": "5,3", "width": 1.4},
    "funding": {"color": "#2e7d32", "dash": None, "width": 2.6},
    "data": {"color": "#555555", "dash": "1.5,3", "width": 1.5},
    "disturbance": {"color": "#888888", "dash": "1.5,3", "width": 1.5},
}
NODE = {"authority": "#dfe7f2", "entity": "#e3f0e3", "org": "#ffffff", "commons": "#f3e7d3",
        "human": "#ffffff", "process": "#e8e8e8", "hub": "#e8e8e8"}
GREY = "#c8c8c8"
FONT = "Helvetica, Arial, sans-serif"
NFS, NLH = 11, 13.5          # node font size, line height
EFS, ELH = 10, 12            # edge label font size, line height
PS = PSS = TS = 16       # one spacing for ports (top/bottom and sides) and gap tracks, so pairs stay parallel

ROW_GAP, COL_GAP, MARGIN = 64, 56, 18
SIDE_PENALTY = 6             # cost of entering or leaving a box through its side
KIND_RANK = {"control": 0, "funding": 1, "data": 2, "disturbance": 2, "feedback": 3}

# Helvetica advance widths (1/1000 em); Liberation Sans and Arial share them
_W = {}
for chars, w in [(" !,./:;I[]\\ft·", 278), ("ijl'’", 222), ("r()-*", 333), ("abdeghnopqu0123456789$#?_Lé–", 556),
                 ("cksvxyzJ", 500), ("mM", 833), ("wCDHNRU", 722), ("ABEKPSVXY&", 667), ("FTZ", 611),
                 ("GOQ", 778), ("W", 944), ("—…", 1000), ("+<>=", 584), ("%", 889), ('"', 355), ("@", 1015)]:
    for c in chars:
        _W[c] = w


def tw(s, fs):
    return sum(_W.get(c, 556) for c in s) * fs / 1000


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------- geometry helpers

def seg_hits_rect(p, q, r, shrink=1.0):
    """Does the axis-aligned segment p-q pass through the interior of rect r = (x, y, w, h)?"""
    x0, y0, x1, y1 = r[0] + shrink, r[1] + shrink, r[0] + r[2] - shrink, r[1] + r[3] - shrink
    if abs(p[0] - q[0]) < 1e-6:
        return x0 < p[0] < x1 and max(p[1], q[1]) > y0 and min(p[1], q[1]) < y1
    if abs(p[1] - q[1]) < 1e-6:
        return y0 < p[1] < y1 and max(p[0], q[0]) > x0 and min(p[0], q[0]) < x1
    # diagonal (never produced here, kept for safety): sample
    return any(x0 < p[0] + t * (q[0] - p[0]) < x1 and y0 < p[1] + t * (q[1] - p[1]) < y1 for t in [i / 20 for i in range(21)])


def seg_cross(a, b, c, d):
    """Proper crossing of two axis-aligned segments (one horizontal, one vertical), 0 or 1."""
    av, cv = abs(a[0] - b[0]) < 1e-6, abs(c[0] - d[0]) < 1e-6
    if av == cv:
        return 0
    if av:
        a, b, c, d = c, d, a, b          # a-b horizontal, c-d vertical
    x, y = c[0], a[1]
    return int(min(a[0], b[0]) + 0.5 < x < max(a[0], b[0]) - 0.5 and min(c[1], d[1]) + 0.5 < y < max(c[1], d[1]) - 0.5)


def seg_overlap(a, b, c, d):
    """Length of collinear overlap of two axis-aligned segments."""
    if abs(a[0] - b[0]) < 1e-6 and abs(c[0] - d[0]) < 1e-6 and abs(a[0] - c[0]) < 2:
        return max(0, min(max(a[1], b[1]), max(c[1], d[1])) - max(min(a[1], b[1]), min(c[1], d[1])))
    if abs(a[1] - b[1]) < 1e-6 and abs(c[1] - d[1]) < 1e-6 and abs(a[1] - c[1]) < 2:
        return max(0, min(max(a[0], b[0]), max(c[0], d[0])) - max(min(a[0], b[0]), min(c[0], d[0])))
    return 0


def rect_overlap(a, b, pad=0):
    return (min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]) > -pad and
            min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]) > -pad)


def segs(pts):
    return list(zip(pts, pts[1:]))


# ---------------------------------------------------------------- model

def load(path):
    m = yaml.safe_load(Path(path).read_text())
    m.setdefault("groups", [])
    m.setdefault("bands", [])
    for k, e in enumerate(m["edges"]):
        e.setdefault("k", k)
    m["byid"] = {n["id"]: n for n in m["nodes"]}
    m["nodes"] = sorted(m["nodes"], key=lambda n: (n["level"], n["column"]))
    return m


def node_lines(n):
    return (n["label"].split("\n") + (["(proposed)"] if n.get("status") == "proposed" else [])
            + ([f'[zoom: {n["zoom"]}]'] if n.get("zoom") else []))


class Grid:
    """Places nodes, routes edges and places labels for one model. Read .nodes, .edges, .size."""

    def __init__(self, m, side_penalty=SIDE_PENALTY):
        self.m = m
        self.side_penalty = side_penalty
        self.levels = sorted({n["level"] for n in m["nodes"]})
        self.cols = sorted({n["column"] for n in m["nodes"]})
        self.R, self.C = len(self.levels), len(self.cols)
        self.N = {}
        for n in m["nodes"]:
            lines = node_lines(n)
            self.N[n["id"]] = {"id": n["id"], "r": self.levels.index(n["level"]), "c": self.cols.index(n["column"]),
                               "lines": lines, "tw": max(tw(s, NFS) for s in lines) + 26, "th": len(lines) * NLH + 14}
        self.E = [dict(e) for e in m["edges"]]
        self.grow_r = {g: 0 for g in range(-1, self.R)}
        self.grow_c = {k: 0 for k in range(self.C + 1)}
        self.bands = m.get("bands") or []
        self.left_strip = 30 if self.bands else 0
        self.title_h = 34 if m.get("title") else 8
        self.layout()

    # ------------------------------------------------------------ sizing and placement
    def place(self):
        for n in self.N.values():
            ntb = max(len(self.side_orders.get((n["id"], s), [])) for s in ("top", "bottom")) if self.routed else 0
            nlr = max(len(self.side_orders.get((n["id"], s), [])) for s in ("left", "right")) if self.routed else 0
            n["w"] = max(n["tw"], 120, (ntb - 1) * PS + 28)
            n["h"] = max(n["th"], (nlr - 1) * PSS + 18)
        cw = [max(n["w"] for n in self.N.values() if n["c"] == c) for c in range(self.C)]
        rh = [max(n["h"] for n in self.N.values() if n["r"] == r) for r in range(self.R)]
        ntr = {}
        for ch, order in (self.chan_orders.items() if self.routed else []):
            ntr[ch] = len(order)
        self.rgap = {g: (MARGIN if g in (-1, self.R - 1) else ROW_GAP) + ntr.get(("gap", g), 0) * TS + self.grow_r[g]
                     for g in range(-1, self.R)}
        self.cgap = {k: (MARGIN if k in (0, self.C) else COL_GAP) + ntr.get(("cg", k), 0) * TS + self.grow_c[k]
                     for k in range(self.C + 1)}
        x = self.left_strip
        self.col_l = []
        for c in range(self.C):
            x += self.cgap[c]
            self.col_l.append(x)
            x += cw[c]
        self.width = x + self.cgap[self.C]
        y = self.title_h + self.rgap[-1]
        self.row_t = []
        for r in range(self.R):
            self.row_t.append(y)
            y += rh[r] + self.rgap[r]
        self.height = y
        self.cw, self.rh = cw, rh
        for n in self.N.values():
            cx = self.col_l[n["c"]] + cw[n["c"]] / 2
            cy = self.row_t[n["r"]] + rh[n["r"]] / 2
            n.update(cx=cx, cy=cy, x=cx - n["w"] / 2, y=cy - n["h"] / 2)
            n["rect"] = (n["x"], n["y"], n["w"], n["h"])

    def gap_y(self, g):  # y range of row gap g (between row g and g+1)
        top = self.row_t[g] + self.rh[g] if g >= 0 else self.title_h
        return top, top + self.rgap[g]

    def cgap_x(self, k):
        right = self.col_l[k] if k < self.C else self.width
        return right - self.cgap[k], right

    # ------------------------------------------------------------ routing
    def candidates(self, e, u, l):
        """Route shapes from u (upper or source) to l: (name, start side, corners, end side)."""
        ru, rl, cu, cl = u["r"], l["r"], u["c"], l["c"]
        out = []
        G = lambda g: ("gap", g)
        K = lambda k: ("cg", k)
        toward = "right" if cl > cu else "left"
        away = "left" if toward == "right" else "right"
        if ru < rl:
            if cu == cl:
                out.append(("straight", "bottom", [], "top"))
            else:
                for g in range(ru, rl):
                    out.append(("z", "bottom", [("S", G(g)), ("E", G(g))], "top", g))
                out.append(("l", toward, [("E", "S")], "top"))
                out.append(("l", "bottom", [("S", "E")], away))
            for k in range(max(0, min(cu, cl) - 1), min(self.C, max(cu, cl) + 2) + 1):
                starts = [("bottom", [("S", G(ru)), (K(k), G(ru))])]
                if k in (cu, cu + 1):
                    starts.append(("left" if k == cu else "right", [(K(k), "S")]))
                ends = [([(K(k), G(rl - 1)), ("E", G(rl - 1))], "top")]
                if k in (cl, cl + 1):
                    ends.append(([(K(k), "E")], "left" if k == cl else "right"))
                for ss, sc in starts:
                    for ec, es in ends:
                        if ss == "bottom" and es == "top" and rl - 1 == ru:
                            continue  # both jogs in one gap: that is a Z
                        out.append(("corridor", ss, sc + ec, es, k))
        else:  # same level
            if abs(cu - cl) >= 1:
                out.append(("straight", toward, [], away))
            for g, side in ((ru, "bottom"), (ru - 1, "top")):
                out.append(("z", side, [("S", G(g)), ("E", G(g))], side, g))
        hint, via = e.get("route"), e.get("via")
        if hint:
            hinted = [c for c in out if c[0] == hint]
            if via is not None:
                # z: the gap below level `via`; corridor: the gap left of column `via`
                vk = (self.levels.index(via) if via in self.levels else via) if hint == "z" else (
                    self.cols.index(via) if via in self.cols else self.C)
                hinted = [c for c in hinted if len(c) > 4 and c[4] == vk] or hinted
            out = hinted or out
        return out

    def nominal(self, cand, u, l):
        name, ss, corners, es = cand[:4]

        def port(n, side):
            return {"top": (n["cx"], n["y"]), "bottom": (n["cx"], n["y"] + n["h"]),
                    "left": (n["x"], n["cy"]), "right": (n["x"] + n["w"], n["cy"])}[side]
        S, E = port(u, ss), port(l, es)
        return self.points(S, E, corners, lambda ref: (sum(self.gap_y(ref[1])) / 2 if ref[0] == "gap"
                                                         else sum(self.cgap_x(ref[1])) / 2))

    @staticmethod
    def points(S, E, corners, resolve):
        pts = [S]
        for xr, yr in corners:
            x = S[0] if xr == "S" else E[0] if xr == "E" else resolve(xr)
            y = S[1] if yr == "S" else E[1] if yr == "E" else resolve(yr)
            pts.append((x, y))
        pts.append(E)
        return pts

    def route_topology(self):
        """Choose a route shape per bundle of edges between the same two nodes."""
        self.routed = False
        self.side_orders, self.chan_orders = {}, {}
        self.place()
        bundles = {}
        for e in self.E:
            bundles.setdefault(frozenset((e["from"], e["to"])), []).append(e)
        order = sorted(bundles.values(), key=lambda b: (-len(b), abs(self.N[b[0]["from"]]["r"] - self.N[b[0]["to"]]["r"])
                                                        + abs(self.N[b[0]["from"]]["c"] - self.N[b[0]["to"]]["c"])))
        done = []
        rects = {i: n["rect"] for i, n in self.N.items()}
        for b in order:
            a, z = self.N[b[0]["from"]], self.N[b[0]["to"]]
            # route from the upper node (or the first edge's source on one level)
            u, l = (a, z) if a["r"] <= z["r"] else (z, a)
            best = None
            for cand in self.candidates(b[0], u, l):
                pts = self.nominal(cand, u, l)
                if any(seg_hits_rect(p, q, r) for i, r in rects.items() for p, q in segs(pts)):
                    continue
                bends = len(pts) - 2
                length = sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in segs(pts))
                cross = sum(seg_cross(p, q, s, t) for d in done for p, q in segs(pts) for s, t in segs(d))
                sides = (cand[1] in ("left", "right")) + (cand[3] in ("left", "right"))
                if cand[0] == "straight" and u["r"] == l["r"]:
                    sides = 0
                cost = 10 * bends + length / 60 + 15 * cross + self.side_penalty * sides
                if best is None or cost < best[0]:
                    best = (cost, cand, pts)
            if best is None:
                raise SystemExit(f"no route for {b[0]['from']} -> {b[0]['to']}")
            done.append(best[2])
            for e in b:
                e["u"], e["l"], e["cand"] = u["id"], l["id"], best[1]
        # initial port and track orders
        for e in self.E:
            name, ss, corners, es = e["cand"][:4]
            nom = self.nominal(e["cand"], self.N[e["u"]], self.N[e["l"]])
            e["nom"] = nom
            self.side_orders.setdefault((e["u"], ss), []).append((e["k"], "S"))
            self.side_orders.setdefault((e["l"], es), []).append((e["k"], "E"))
            for ref in {r for c in corners for r in c if isinstance(r, tuple)}:
                self.chan_orders.setdefault(ref, []).append(e["k"])
        byk = {e["k"]: e for e in self.E}
        for (nid, side), lst in self.side_orders.items():
            horiz = side in ("top", "bottom")

            def key(pk):
                e = byk[pk[0]]
                nom = e["nom"] if pk[1] == "S" else e["nom"][::-1]
                nxt = nom[1] if len(nom) > 2 else nom[-1]
                down = self.down(e)
                return ((nxt[0] if horiz else nxt[1]), 0 if down else 1, KIND_RANK.get(e["kind"], 2))
            lst.sort(key=key)
        for ch, lst in self.chan_orders.items():
            lst.sort(key=lambda k: (min(p[0] for p in byk[k]["nom"]), KIND_RANK.get(byk[k]["kind"], 2)))
        self.routed = True

    def down(self, e):
        a, b = self.N[e["from"]], self.N[e["to"]]
        return (a["r"], a["c"]) < (b["r"], b["c"]) if a["r"] == b["r"] else a["r"] < b["r"]

    def solve_ports(self):
        pos = {}
        spans = {}
        for (nid, side), order in self.side_orders.items():
            n = self.N[nid]
            tb = side in ("top", "bottom")
            L, pad, sp = (n["w"], 14, PS) if tb else (n["h"], 9, PSS)
            c = n["cx"] if tb else n["cy"]
            cnt = len(order)
            s = min(sp, (L - 2 * pad) / (cnt - 1)) if cnt > 1 else 0
            for i, key in enumerate(order):
                pos[key] = c + (i - (cnt - 1) / 2) * s
            spans[(nid, side)] = (c - L / 2 + pad, c + L / 2 - pad, 0.8 * s if cnt > 1 else 0)
        straight = [e for e in self.E if not e["cand"][2]]
        for _ in range(40):
            for e in straight:
                a, b = pos[(e["k"], "S")], pos[(e["k"], "E")]
                pos[(e["k"], "S")] = pos[(e["k"], "E")] = (a + b) / 2
            for sk, order in self.side_orders.items():
                lo, hi, smin = spans[sk]
                for i, key in enumerate(order):
                    pos[key] = max(pos[key], lo if i == 0 else pos[order[i - 1]] + smin)
                for i in range(len(order) - 1, -1, -1):
                    key = order[i]
                    pos[key] = min(pos[key], hi if i == len(order) - 1 else pos[order[i + 1]] - smin)
        for e in straight:   # exact alignment wins over spacing
            a, b = pos[(e["k"], "S")], pos[(e["k"], "E")]
            pos[(e["k"], "S")] = pos[(e["k"], "E")] = (a + b) / 2
        return pos

    def build(self):
        """Polylines for every edge from the current orders. Returns {k: pts} (drawn direction)."""
        self.place()
        pos = self.solve_ports()
        track = {}
        for ch, order in self.chan_orders.items():
            lo, hi = self.gap_y(ch[1]) if ch[0] == "gap" else self.cgap_x(ch[1])
            mid, n = (lo + hi) / 2, len(order)
            for i, k in enumerate(order):
                track[(ch, k)] = mid + (i - (n - 1) / 2) * TS
        out = {}
        for e in self.E:
            u, l = self.N[e["u"]], self.N[e["l"]]
            name, ss, corners, es = e["cand"][:4]

            def port(n, side, end):
                p = pos[(e["k"], end)]
                return {"top": (p, n["y"]), "bottom": (p, n["y"] + n["h"]),
                        "left": (n["x"], p), "right": (n["x"] + n["w"], p)}[side]
            pts = self.points(port(u, ss, "S"), port(l, es, "E"), corners, lambda ref: track[(ref, e["k"])])
            # drop zero-length legs
            clean = [pts[0]]
            for p in pts[1:]:
                if abs(p[0] - clean[-1][0]) > 0.01 or abs(p[1] - clean[-1][1]) > 0.01:
                    clean.append(p)
            if e["from"] != e["u"]:
                clean = clean[::-1]
            out[e["k"]] = clean
        return out

    def badness(self, P):
        ks = list(P)
        cross = over = 0
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                for p, q in segs(P[ks[i]]):
                    for s, t in segs(P[ks[j]]):
                        cross += seg_cross(p, q, s, t)
                        over += seg_overlap(p, q, s, t) > 1
        # pair convention: on a top/bottom side, downward edges left of upward edges between the same nodes
        viol = 0
        byk = {e["k"]: e for e in self.E}
        for (nid, side), order in self.side_orders.items():
            if side not in ("top", "bottom"):
                continue
            for i, a in enumerate(order):
                for b in order[i + 1:]:
                    ea, eb = byk[a[0]], byk[b[0]]
                    if {ea["from"], ea["to"]} == {eb["from"], eb["to"]} and not self.down(ea) and self.down(eb):
                        viol += 1
        through = sum(seg_hits_rect(p, q, n["rect"], 2) for k, pts in P.items() for p, q in segs(pts)
                      for n in self.N.values())
        return 100 * cross + 100 * over + 300 * through + viol

    def improve(self, frozen=()):
        """Adjacent swaps of ports and tracks while they lower the badness."""
        best = self.badness(self.build())
        lists = [l for l in list(self.side_orders.values()) + list(self.chan_orders.values())
                 if not any(l is f for f in frozen)]
        for _ in range(8):
            changed = False
            for lst in lists:
                for i in range(len(lst) - 1):
                    lst[i], lst[i + 1] = lst[i + 1], lst[i]
                    b = self.badness(self.build())
                    if b < best:
                        best, changed = b, True
                    else:
                        lst[i], lst[i + 1] = lst[i + 1], lst[i]
            if not changed:
                break
        return best

    def improve_pairs(self):
        """Local search can trade a crossing for a reversed pair (feedback left of control); for each
        reversed pair, put it right, hold that side fixed and search again. Keep it only if better."""
        best = self.improve()
        byk = {e["k"]: e for e in self.E}
        for (nid, side), lst in list(self.side_orders.items()):
            if side not in ("top", "bottom"):
                continue
            for i in range(len(lst) - 1):
                a, b = byk[lst[i][0]], byk[lst[i + 1][0]]
                if {a["from"], a["to"]} == {b["from"], b["to"]} and not self.down(a) and self.down(b):
                    snap = ({k: list(v) for k, v in self.side_orders.items()}, {k: list(v) for k, v in self.chan_orders.items()})
                    lst[i], lst[i + 1] = lst[i + 1], lst[i]
                    got = self.improve(frozen=(lst,))
                    if got < best:
                        best = got
                    else:
                        for k, v in snap[0].items():
                            self.side_orders[k][:] = v
                        for k, v in snap[1].items():
                            self.chan_orders[k][:] = v
        return best

    # ------------------------------------------------------------ labels
    def place_labels(self, P):
        boxes = {}
        obstacles = [n["rect"] for n in self.N.values()]
        if self.m.get("title"):
            w = tw(self.m["title"], 13)
            obstacles.append((self.width / 2 - w / 2, 6, w, 20))
        for g in self.group_rects():
            obstacles.append(g["label_box"])
        all_segs = [(k, p, q) for k, pts in P.items() for p, q in segs(pts)]
        byk = {e["k"]: e for e in self.E}
        pairs = {k for k, e in byk.items() for f in byk.values()
                 if f is not e and {e["from"], e["to"]} == {f["from"], f["to"]}}

        def cands(e):
            lines = e["label"].split("\n")
            w, h = max(tw(s, EFS) for s in lines) + 4, len(lines) * ELH + 2
            pts = P[e["k"]]
            lmax = max(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in segs(pts))
            down = self.down(e)
            pref = e.get("label_side") or (("left" if down else "right") if e["k"] in pairs else None)
            out = []
            for p, q in segs(pts):
                L = abs(p[0] - q[0]) + abs(p[1] - q[1])
                if L < 6:
                    continue
                vert = abs(p[0] - q[0]) < 0.01
                for t in (0.5, 0.35, 0.65, 0.2, 0.8, 0.1, 0.9):
                    cx, cy = p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])
                    sides = [(("left", (cx - g - w, cy - h / 2)), ("right", (cx + g, cy - h / 2))) if vert else
                             (("above", (cx - w / 2, cy - g + 1 - h)), ("below", (cx - w / 2, cy + g - 1)))
                             for g in (5, 12)]
                    for side, (x, y) in sides[0] + sides[1]:
                        pen = 3 * (1 - L / lmax) + 4 * abs(t - 0.5) + (2 if abs(x - cx) > w + 8 or abs(y - cy) > h + 8 else 0)
                        if pref and side != pref:
                            pen += 50 if e.get("label_side") else 6
                        if vert and (y < min(p[1], q[1]) - 2 or y + h > max(p[1], q[1]) + 2):
                            pen += 2   # sticks out past its segment
                        out.append((pen, (x, y, w, h), side))
            return out

        def score(e, cand):
            pen, r, _ = cand
            s = pen
            s += 1000 * sum(rect_overlap(r, o, 2) for o in obstacles)
            s += 500 * sum(rect_overlap(r, b[1], 2) for k, b in boxes.items() if k != e["k"])
            s += 200 * sum(seg_hits_rect(p, q, r, -2) for k, p, q in all_segs)
            if r[0] < self.left_strip + 2 or r[1] < self.title_h - 4:
                s += 150
            if r[0] + r[2] > self.width - 2 or r[1] + r[3] > self.height - 2:
                s += 20    # widens the canvas
            return s

        order = sorted(self.E, key=lambda e: (e["k"] not in pairs, e["k"]))
        for _ in range(3):
            for e in order:
                boxes.pop(e["k"], None)
                c = min(cands(e), key=lambda c: score(e, c))
                boxes[e["k"]] = (score(e, c), c[1], c[2])
        return boxes

    def group_rects(self):
        out = []
        for g in self.m.get("groups", []):
            mem = [self.N[n["id"]] for n in self.m["nodes"] if n.get("group") == g["id"]]
            if not mem:
                continue
            x0 = min(n["x"] for n in mem) - 14
            y0 = min(n["y"] for n in mem) - 22
            x1 = max(n["x"] + n["w"] for n in mem) + 14
            y1 = max(n["y"] + n["h"] for n in mem) + 12
            lw = tw(g["label"], 10)
            out.append({"id": g["id"], "label": g["label"], "rect": (x0, y0, x1 - x0, y1 - y0),
                        "label_box": (x0 + 6, y0 + 3, lw + 4, 13)})
        return out

    # ------------------------------------------------------------ driver
    def layout(self):
        """Route, then place labels; grow the gaps near any label that cannot be placed cleanly and
        redo, keeping the attempt with the fewest bad labels (then the smallest area)."""
        best, stale = None, 0
        for it in range(12):
            self.route_topology()
            self.improve_pairs()
            P = self.build()
            boxes = self.place_labels(P)
            bad = [(k, b) for k, b in boxes.items() if b[0] >= 150]
            rank = (len(bad), sum(b[0] for _, b in bad), self.width * self.height)
            if best is None or rank < best[0]:
                best, stale = (rank, dict(self.grow_r), dict(self.grow_c)), 0
            else:
                stale += 1
            if not bad or stale >= 3:
                break
            for k, b in bad:
                x, y, w, h = b[1]
                cy, cx = y + h / 2, x + w / 2
                g = min(range(-1, self.R), key=lambda g: abs(sum(self.gap_y(g)) / 2 - cy))
                self.grow_r[g] += 14
                kk = min(range(self.C + 1), key=lambda k: abs(sum(self.cgap_x(k)) / 2 - cx))
                self.grow_c[kk] += 14
        if (len(bad), sum(b[0] for _, b in bad), self.width * self.height) != best[0]:
            self.grow_r, self.grow_c = best[1], best[2]
            self.route_topology()
            self.improve_pairs()
            P = self.build()
            boxes = self.place_labels(P)
        self.finish(P, boxes)

    def finish(self, P, boxes=None):
        """Adopt routes (this layout's, or another router's) and labels, then size the canvas."""
        self.P = P
        self.labels = boxes if boxes is not None else self.place_labels(P)
        boxes = self.labels
        # canvas: include every label and every route
        bx = [(b[1][0], b[1][1], b[1][0] + b[1][2], b[1][1] + b[1][3]) for b in boxes.values()]
        bx += [(x, y, x, y) for pts in P.values() for x, y in pts]
        bx += [(n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"]) for n in self.N.values()]
        self.shift = max(0, -min(b[0] for b in bx) + 6)
        self.yshift = max(0, -min(b[1] for b in bx) + 6)
        self.size = (max([self.width] + [b[2] + 6 for b in bx]) + self.shift,
                     max([self.height] + [b[3] + 6 for b in bx]) + self.yshift)


# ---------------------------------------------------------------- SVG

def svg(m, G, view=None, data_ids=True):
    focus = set(view["focus"]) if view else None
    lit_e = {e["k"] for e in m["edges"] if focus is None or {e["from"], e["to"]} & focus}
    lit_n = None if focus is None else focus | {x for e in m["edges"] if e["k"] in lit_e for x in (e["from"], e["to"])}
    W, H = G.size
    dx = G.shift
    f = lambda v: f"{v:.1f}"
    title = m.get("title", "") + (f' — {view["title"]}' if view else "")
    if title and tw(title, 13) + 30 > W:   # a long view title widens the card; content stays centred
        dx += (tw(title, 13) + 30 - W) / 2
        W = tw(title, 13) + 30
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" '
         f'font-family="{FONT}">']
    o.append(f"<title>{esc(title)}</title>")
    o.append("<defs>")
    for col in sorted({k["color"] for k in EDGE.values()} | {GREY}):
        o.append(f'<marker id="ah{col[1:]}" viewBox="0 0 10 10" refX="10" refY="5" markerUnits="userSpaceOnUse" markerWidth="9" markerHeight="9" '
                 f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>')
    o.append("</defs>")
    o.append(f'<rect x="0" y="0" width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>')
    if title:
        o.append(f'<text x="{W / 2:.1f}" y="22" font-size="13" text-anchor="middle" fill="#111">{esc(title)}</text>')
    o.append(f'<g transform="translate({dx:.1f},{G.yshift:.1f})">')
    # bands
    for i, b in enumerate(G.bands):
        rs = [G.levels.index(v) for v in b["levels"] if v in G.levels]
        if not rs:
            continue
        top = G.gap_y(min(rs) - 1)[0] + (G.rgap[min(rs) - 1] / 2 if min(rs) > 0 else 0)
        bot = G.gap_y(max(rs))[0] + (G.rgap[max(rs)] / 2 if max(rs) < G.R - 1 else G.rgap[max(rs)])
        fill = "#f3f5f8" if i % 2 == 0 else "#fafafa"
        o.append(f'<rect class="band" x="{-dx + 0:.1f}" y="{f(top)}" width="{W:.0f}" height="{f(bot - top)}" fill="{fill}"/>')
        o.append(f'<line x1="{-dx:.1f}" x2="{W:.0f}" y1="{f(top)}" y2="{f(top)}" stroke="#b9c0ca" stroke-width="0.8"/>')
        cy = (top + bot) / 2
        o.append(f'<text class="band" x="{-dx + 16:.1f}" y="{f(cy)}" font-size="10" fill="#555" text-anchor="middle" '
                 f'font-weight="bold" transform="rotate(-90 {-dx + 16:.1f} {f(cy)})">{esc(b["label"])}</text>')
    for g in G.group_rects():
        x, y, w, h = g["rect"]
        o.append(f'<g class="group" data-id="{g["id"]}"><rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}" '
                 f'fill="none" stroke="#999" stroke-dasharray="4,3"/>'
                 f'<text x="{f(x + 8)}" y="{f(y + 13)}" font-size="10" fill="#555">{esc(g["label"])}</text></g>')
    byk = {e["k"]: e for e in m["edges"]}
    for k, pts in G.P.items():
        e = byk[k]
        st = EDGE.get(e["kind"], EDGE["data"])
        col = st["color"] if k in lit_e else GREY
        dash = st["dash"] or ("6,4" if e.get("status") == "proposed" else None)
        d = "M" + " L".join(f"{f(x)},{f(y)}" for x, y in pts)
        dk = f' data-k="{k}"' if data_ids else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        o.append(f'<g class="edge"{dk}><path class="edge"{dk} d="{d}" fill="none" stroke="{col}" '
                 f'stroke-width="{st["width"]}"{da} '
                 f'stroke-linecap="{"round" if e["kind"] in ("data", "disturbance") else "butt"}" '
                 f'marker-end="url(#ah{col[1:]})"/></g>')
    for n in m["nodes"]:
        g = G.N[n["id"]]
        lit = lit_n is None or n["id"] in lit_n
        fill = NODE.get(n["kind"], "#ffffff") if lit else "#f6f6f6"
        stroke = "#333333" if lit else GREY
        sw = 2.2 if (focus and n["id"] in focus) else 1
        dash = ' stroke-dasharray="5,3"' if n.get("status") == "proposed" else ""
        o.append(f'<g class="node" data-id="{n["id"]}"><rect x="{f(g["x"])}" y="{f(g["y"])}" width="{f(g["w"])}" '
                 f'height="{f(g["h"])}" rx="5" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}/>')
        y0 = g["cy"] - (len(g["lines"]) - 1) * NLH / 2 + 4
        for i, s in enumerate(g["lines"]):
            o.append(f'<text x="{f(g["cx"])}" y="{f(y0 + i * NLH)}" font-size="{NFS}" text-anchor="middle" '
                     f'fill="{"#111111" if lit else "#a0a0a0"}">{esc(s)}</text>')
        o.append("</g>")
    for k, (_, (x, y, w, h), side) in sorted(G.labels.items()):
        e = byk[k]
        col = EDGE.get(e["kind"], EDGE["data"])["color"] if k in lit_e else "#a8a8a8"
        lines = e["label"].split("\n")
        anchor, tx = (("end", x + w - 2) if side == "left" else ("start", x + 2) if side == "right"
                      else ("middle", x + w / 2))
        o.append(f'<g class="elabel" data-k="{k}">')
        for i, s in enumerate(lines):
            o.append(f'<text x="{f(tx)}" y="{f(y + 10 + i * ELH)}" font-size="{EFS}" text-anchor="{anchor}" '
                     f'fill="{col}">{esc(s)}</text>')
        o.append("</g>")
    o.append("</g></svg>")
    return "\n".join(o) + "\n"


def legend():
    rows = list(EDGE.items())[:4]
    W, H = 640, 92
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">',
         "<defs>"]
    for _, st in rows:
        o.append(f'<marker id="ah{st["color"][1:]}" viewBox="0 0 10 10" refX="10" refY="5" markerUnits="userSpaceOnUse" markerWidth="9" '
                 f'markerHeight="9" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{st["color"]}"/></marker>')
    o.append(f'</defs><rect width="{W}" height="{H}" fill="#ffffff"/>')
    for i, (kind, st) in enumerate(rows):
        x = 14 + i * 150
        dash = f' stroke-dasharray="{st["dash"]}"' if st["dash"] else ""
        o.append(f'<path d="M{x},20 L{x + 60},20" stroke="{st["color"]}" stroke-width="{st["width"]}"{dash} '
                 f'marker-end="url(#ah{st["color"][1:]})"/><text x="{x + 68}" y="24" font-size="11" fill="{st["color"]}">{kind}</text>')
    for i, (kind, label) in enumerate([("authority", "public authority"), ("entity", "legal entity or operator"),
                                       ("commons", "shared commons"), ("org", "group or organisation"),
                                       (None, "proposed")]):
        x = 14 + i * 124
        w = 116
        dash = ' stroke-dasharray="5,3"' if kind is None else ""
        o.append(f'<rect x="{x}" y="46" width="{w}" height="30" rx="5" fill="{NODE.get(kind, "#ffffff")}" '
                 f'stroke="#333"{dash}/><text x="{x + w / 2}" y="65" font-size="10" text-anchor="middle">{label}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


def render(path, outdir, data_ids=False):
    m = load(path)
    G = Grid(m)
    stem = Path(path).stem
    written = []
    (outdir / f"{stem}.svg").write_text(svg(m, G, data_ids=data_ids))
    written.append(outdir / f"{stem}.svg")
    for v in m.get("views", []):
        (outdir / f'{stem}--{v["id"]}.svg').write_text(svg(m, G, v, data_ids=data_ids))
        written.append(outdir / f'{stem}--{v["id"]}.svg')
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-o", "--outdir", default=str(HERE / "results" / "grid-render"))
    ap.add_argument("inputs", nargs="*")
    a = ap.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    for p in a.inputs or sorted(INPUTS.glob("*.yaml")):
        for w in render(p, out):
            print(w)
    (out / "legend.svg").write_text(legend())


if __name__ == "__main__":
    main()
