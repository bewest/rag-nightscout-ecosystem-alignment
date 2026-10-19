"""Spans over time: records land one by one, and the instances a hub derives change as each lands.

Rules A5-A8 of docs/30-design/platform/spec/state-intent.md §6.1, one conformance case each (the
cases tools/diagrams/active_state_rules.py draws, loaded with its code). After each record, the
instances are what the reference decision function tools/nsschema/active_state.py derives from the
records received so far; after the last record they must equal the case's `expected` block, which
the static figures draw, or the scene refuses to render. The "active at" cursor then visits each of
the case's expected queries. Ends on a frame with the four cases' final states.

    manim -qm --format webm --media_dir <scratch> tools/animations/active_state_spans.py ActiveStateSpans
"""
import sys
from datetime import timedelta
from pathlib import Path

from manim import FadeIn, FadeOut, GrowFromEdge, LEFT, Line, ReplacementTransform, Scene, VGroup, linear

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (PX, P, BAD, BLUE, BLUE_T, FAINT, INK, MUTED, RULE, TimeAxis, at, bar, box, cell, cross, dot,
                    fit, hline, text_block, tri_right, vdash, T, width_px)
import active_state_rules as asr
from nsschema import active_state
from sources import SPAN_CASES, rule_names

SPEC = "state and intent §6.1"


def order(rows):
    return sorted(rows, key=lambda r: (r["product"], r["kind"], r["layer"], r["start"], r["key"]))


def steps(case):
    """The instances after each record, from the reference; the last must be the case's expected."""
    out = [active_state.summary(dict(case, records=case["records"][:k]))
           for k in range(1, len(case["records"]) + 1)]
    if out[-1] != order(case["expected"]["instances"]):
        raise SystemExit(f"{case['id']}: reference instances differ from the case's expected block")
    for q in case["expected"]["activeAt"]:
        if active_state.active_at(case, q["at"]) != order(q["active"]):
            raise SystemExit(f"{case['id']}: reference active set at {q['at']} differs from expected")
    return out


def axis_for(case):
    times = [asr.iso(asr.record_time(case, r)) for r in case["records"] if asr.record_time(case, r)]
    times += [asr.iso(r["receivedAt"]) for r in case["records"] if r.get("receivedAt")]
    times += [asr.iso(i["start"]) for i in case["expected"]["instances"]]
    times += [asr.iso(i["end"]) for i in case["expected"]["instances"] if i["end"]]
    times += [asr.iso(a["at"]) for a in case["expected"]["activeAt"]]
    base = min(times)
    base = base.replace(minute=(base.minute // 30) * 30, second=0)
    hi = max((t - base).total_seconds() / 60 for t in times) + 20
    hi = 30 * -(-hi // 30)
    return base, hi


def hm(base, m):
    return (base + timedelta(minutes=m)).strftime("%H:%M")


class Layout:
    def __init__(self, case, x0, x1, label_x, size=16, right=None, left=None):
        self.case, self.size, self.label_x = case, size, label_x
        self.right = right or x1 + 40
        self.left = left or label_x + 120
        self.base, hi = axis_for(case)
        self.ax = TimeAxis(0, hi, x0, x1)

    def m(self, s):
        return (asr.iso(s) - self.base).total_seconds() / 60

    def record_row(self, i, rec, y):
        case, ax, sz = self.case, self.ax, self.size
        g = VGroup(at(T(f"#{i + 1} {rec['op']}", sz), self.label_x, y))
        desc = asr.describe(case, rec)
        if rec["op"] == "delete":
            x = ax.x(self.m(rec["receivedAt"]))
            g.add(cross(x, y))
            s = f"delete received {asr.iso(rec['receivedAt']).strftime('%H:%M')} of {desc}"
        else:
            t = asr.record_time(case, rec)
            x = ax.x(self.m(t))
            g.add(dot(x, y))
            s = f"{rec['doc'].get('eventType', '')} {asr.iso(t).strftime('%H:%M')}, {desc}"
        t = T(s, sz)
        if width_px(t) > self.right - x - 14 and width_px(t) <= x - 14 - self.left:
            g.add(at(t, x - 14, y, "right"))
        else:
            g.add(at(fit(s, sz, self.right - x - 14), x + 14, y))
        return g

    def instance(self, inst, y, h=20):
        ax, sz = self.ax, self.size
        name = asr.short_key(inst["key"])
        s = self.m(inst["start"])
        xs = ax.x(s)
        if inst["endReason"] == "deletedBeforeStart":
            return VGroup(cross(xs, y), at(T(f"{name}, deletedBeforeStart", sz), xs + 14, y))
        e = self.m(inst["end"]) if inst["end"] else None
        xe = ax.x(min(e, ax.hi)) if e is not None else ax.x(ax.hi)
        g = VGroup(bar(xs, xe, y, h, BLUE_T, BLUE))
        bits = [name, f"{hm(self.base, s)}–{hm(self.base, e) if e is not None else 'open-ended'}"]
        if inst["endReason"]:
            bits.append(inst["endReason"])
        if e is None:
            g.add(tri_right(xe, y, BLUE))
        lbl = T(", ".join(bits), sz)
        if width_px(lbl) + 12 <= xe - xs:
            g.add(at(lbl, xs + 6, y))
        elif xe + 14 + width_px(lbl) <= self.right:
            g.add(at(lbl, xe + 14, y))
        else:
            g.add(at(lbl, xs - 8, y, "right"))
        return g

    def axis(self, y):
        ax = self.ax
        g = VGroup(hline(ax.x0, ax.x1, y, MUTED))
        for t in ax.ticks(30):
            g.add(Line(P(ax.x(t), y), P(ax.x(t), y + 5), color=MUTED, stroke_width=1))
            g.add(at(T(hm(self.base, t), 14, MUTED), ax.x(t), y + 16, "center"))
        g.add(at(T("UTC", 14, MUTED), self.label_x, y + 16))
        return g

    def active_cells(self, y, x_min, x_max):
        """One cell per expected query, as the static figure writes them; sub-rows where they touch."""
        cells, placed = [], []
        for q in self.case["expected"]["activeAt"]:
            names = [asr.short_key(a["key"]) + (" (overlap)" if a.get("overlap") else "") for a in q["active"]]
            c = cell(" + ".join(names) if names else "none", self.ax.x(self.m(q["at"])), y, max_left=x_min,
                     max_right=x_max, edge=BLUE, size=16 if self.size >= 18 else 14)
            lane = 0
            while any(l == lane and not (c.get_right()[0] < o.get_left()[0] or c.get_left()[0] > o.get_right()[0])
                      for l, o in placed):
                lane += 1
            c.shift([0, -lane * 30 * PX, 0])
            placed.append((lane, c))
            cells.append((q, c))
        return cells


class ActiveStateSpans(Scene):
    def construct(self):
        cases = {cid: asr.load(cid) for _, cid in SPAN_CASES}
        spec = (asr.REPO / "docs/30-design/platform/spec/state-intent.md").read_text()
        names = dict(n.split(" ", 1) for n in rule_names(spec, [r for r, _ in SPAN_CASES]))
        derived = {cid: steps(c) for cid, c in cases.items()}

        foot = ("Synthetic conformance cases, specs/sync/conformance/active-state/. Instances after each record: "
                "the reference decision function tools/nsschema/active_state.py; after the last record they equal "
                "the case's expected block (the static figures active-state-a5 to a8).")
        footer, _ = text_block(foot, 40, 668, 14, 1200, color=MUTED, italic=True)
        self.add(footer)

        for rule, cid in SPAN_CASES:
            case = cases[cid]
            L = Layout(case, 330, 1150, 40, size=18)
            head = VGroup(at(T(f"{rule} · {names[rule].rstrip('.')}", 24, bold=True), 40, 34),
                          at(T(f"proposed rule, {SPEC}", 14, MUTED), 1240, 34, "right"))
            sub, y = text_block(f"{cid}: {case['title']}", 40, 70, 18, 1200, color=INK)
            head.add(sub)
            rows_top = y + 4
            keys = []
            for st in derived[cid]:
                for inst in st:
                    if inst["key"] not in keys:
                        keys.append(inst["key"])
            final_keys = [i["key"] for i in derived[cid][-1]]
            keys = final_keys + [k for k in keys if k not in final_keys]
            lanes = len({round(c.get_center()[1], 3) for _, c in L.active_cells(0, 300, 1240)})
            nrec = len(case["records"])
            # rows: section label + records, section label + instances, active lanes, axis
            R = min(56, (640 - rows_top - 3 * 30 - 40) / (nrec + len(keys) + lanes))
            sec1 = at(T("records, in the order the hub received them", 16, MUTED), 40, rows_top + 22)
            ry = [rows_top + 44 + R / 2 + i * R for i in range(nrec)]
            y2 = ry[-1] + R / 2 + 22
            sec2 = at(T("instances the hub derives from the records received so far", 16, MUTED), 40, y2)
            iy = {k: y2 + 22 + R / 2 + j * R for j, k in enumerate(keys)}
            ay = y2 + 22 + len(keys) * R + 34
            axis_y = ay + 30 * lanes + 20
            frame = VGroup(box(28, rows_top, 1252, axis_y + 36, FAINT), sec1, sec2,
                           hline(40, 1240, y2 - 18), hline(40, 1240, ay - 30),
                           at(T("instance", 18, BLUE), 40, iy[keys[0]]) if keys else VGroup(),
                           at(T("active at", 18), 40, ay), L.axis(axis_y))
            self.add(head, frame)
            self.wait(0.7)

            shown = {}
            for k, rec in enumerate(case["records"]):
                row = L.record_row(k, rec, ry[k])
                self.play(FadeIn(row, shift=LEFT * 0.2), run_time=0.35)
                anims = []
                new = {i["key"]: L.instance(i, iy[i["key"]], h=min(26, R * 0.55)) for i in derived[cid][k]}
                for key, g in new.items():
                    if key not in shown:
                        anims.append(GrowFromEdge(g, LEFT))
                    else:
                        anims.append(ReplacementTransform(shown[key], g))
                for key in [k_ for k_ in shown if k_ not in new]:
                    anims.append(FadeOut(shown[key]))
                shown = new
                if anims:
                    self.play(*anims, run_time=0.5)
                self.wait(0.85)

            cursor_x = L.ax.x(0)
            cursor = vdash(cursor_x, rows_top + 6, axis_y)
            self.add(cursor)
            marks = VGroup()
            for q, c in L.active_cells(ay, 300, 1240):
                x = L.ax.x(L.m(q["at"]))
                self.play(cursor.animate.move_to([P(x, 0)[0], cursor.get_center()[1], 0]),
                          run_time=0.4, rate_func=linear)
                mark = vdash(x, rows_top + 6, axis_y, color=RULE)
                marks.add(mark)
                self.add(mark)
                self.play(FadeIn(c), run_time=0.25)
                marks.add(c)
                self.wait(0.6)
            self.wait(0.4)
            self.remove(*[m for m in self.mobjects if m is not footer])

        self.remove(footer)
        self.summary(cases, names, derived)

    def summary(self, cases, names, derived):
        """The poster: each case after its last record, with what is active at each query."""
        g = VGroup(at(T("Rules A5–A8: instances after the last record, and what is active at each query", 20,
                        bold=True), 40, 28))
        boxes = [(28, 52, 636, 362), (644, 52, 1252, 362), (28, 370, 636, 680), (644, 370, 1252, 680)]
        for (rule, cid), (x0, y0, x1, y1) in zip(SPAN_CASES, boxes):
            case = cases[cid]
            L = Layout(case, x0 + 84, x1 - 24, x0 + 12, size=14, right=x1 - 8, left=x0 + 8)
            g.add(box(x0, y0, x1, y1, FAINT))
            g.add(at(T(f"{rule} · {names[rule].rstrip('.')}", 16, bold=True), x0 + 12, y0 + 20))
            g.add(at(fit(cid, 14, x1 - x0 - 24, color=MUTED), x0 + 12, y0 + 44))
            y = y0 + 76
            for i, rec in enumerate(case["records"]):
                r = L.record_row(i, rec, y)
                r.remove(r[0])       # no row label: the panel is narrow
                g.add(r)
                y += 30
            g.add(hline(x0 + 12, x1 - 12, y - 10))
            y += 8
            for inst in derived[cid][-1]:
                g.add(L.instance(inst, y, h=18))
                y += 30
            g.add(hline(x0 + 12, x1 - 12, y - 10))
            y += 10
            cells = L.active_cells(y, x0 + 8, x1 - 8)
            low = min(c.get_bottom()[1] for _, c in cells) if cells else None
            ya = y + 30 if low is None else (720 / 2 - low / PX) + 14
            for q, c in cells:
                x = L.ax.x(L.m(q["at"]))
                g.add(vdash(x, y0 + 62, ya, color="#9a9a9a"))
                g.add(c)
            g.add(L.axis(ya))
        g.add(at(T("Synthetic cases; reference decision function tools/nsschema/active_state.py; "
                   "final state = each case's expected block.", 14, MUTED, italic=True), 40, 700))
        self.add(g)
        self.wait(3)
