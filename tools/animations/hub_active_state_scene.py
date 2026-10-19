"""Two hubs, one record set: the hub-active-state lab results, case by case.

Records land in the order they were written; then the windows cgm-remote-monitor reported and the
spans Nocturne stored appear; then a query cursor visits each query time and shows what each hub
reported as active there, a Nocturne reading that differs from cgm-remote-monitor's in red with "≠".
Loaded with tools/diagrams/hub_active_state.py, the code that draws the static figures
hub-active-state-*.svg, from the same files. Every reading is measured (the lab run named in
results/RESULTS.md); the records were all written before any query, so nothing between query times
is shown. Ends on a table of every reading.

    manim -qm --format webm --media_dir <scratch> tools/animations/hub_active_state_scene.py HubActiveState
"""
import sys
from pathlib import Path

from manim import FadeIn, FadeOut, GrowFromEdge, LEFT, LaggedStart, Scene, VGroup, linear

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BAD, BAD_T, BLUE, BLUE_T, CARD, FAINT, INK, MUTED, ORANGE, ORANGE_T, P, PX, RULE,  # noqa: E402
                    TimeAxis, at, bar, box, cell, dot, fit, hline, text_block, tri_right, vdash, T, width_px)
import hub_active_state as lab  # noqa: E402
from sources import HUB_CASES  # noqa: E402
from svgkit import iso, nice_step, num  # noqa: E402

LABEL_X, X0, X1 = 40, 300, 1200


def readings(case, crm_case, noc_case):
    """[(row name, compare?, {label: key})] as the static figure reads them."""
    ask = case["asks"][0]
    crm_q = {q["label"]: q["answers"][ask]["key"] for q in crm_case["queries"]}
    noc = {q["label"]: q["answers"][ask] for q in noc_case["queries"]}
    rows = [("cgm-remote-monitor", False, crm_q),
            ("Nocturne latest span", True, {k: v["key"] for k, v in noc.items()})]
    if ask in lab.LIST_ASKS:
        rows.append(("Nocturne list read", True, {k: v["keySet"] for k, v in noc.items()}))
    return rows, crm_q


class HubActiveState(Scene):
    def construct(self):
        cases, crm, noc, run = lab.load()
        t0 = iso(cases["t0"])
        by = {c["id"]: c for c in cases["cases"]}
        cr = {c["id"]: c for c in crm["cases"]}
        nc = {c["id"]: c for c in noc["cases"]}
        measured = (f"measured, tools/lab/hub-active-state, run {run['date']}: cgm-remote-monitor {run['crm']} "
                    f"({run['crm_version']}), Nocturne {run['nocturne']}. Synthetic records; T0 = {cases['t0']}.")
        footer, _ = text_block(measured, 40, 690, 14, 1200, color=MUTED, italic=True)
        title = at(T("Two hubs, one record set", 24, bold=True), 40, 30)
        self.add(footer, title)

        table = []
        for cid in HUB_CASES:
            case, crm_case, noc_case = by[cid], cr[cid], nc[cid]
            ask = case["asks"][0]
            qs = [lab.minutes(t0, q["t"]) for q in case["queries"]]
            hi = max(qs) * 1.15
            step = nice_step(hi)
            hi = step * -(-hi // step)
            ax = TimeAxis(0, hi, X0, X1)
            sub, y = text_block(f"{cid} · {case['claim']} — {case['title']}", 40, 62, 16, 1200)
            recs = case["records"]
            derived = [("cgm-remote-monitor", BLUE, BLUE_T, w) for w in lab.crm_windows(crm_case, ask, t0)]
            derived += [("Nocturne span", ORANGE, ORANGE_T, w) for w in lab.noc_spans(noc_case, t0)]
            rows, crm_q = readings(case, crm_case, noc_case)
            top = y + 24
            n = len(recs) + len(derived)
            avail = 640 - top - 28 - len(rows) * 34 - 44
            row = max(22, min(36, avail / max(n, 1)))
            # query labels
            frame = VGroup(box(28, top - 16, 1252, 650, FAINT))
            for q, m in zip(case["queries"], qs):
                frame.add(at(T(q["label"], 14, MUTED), ax.x(m), top, "center"))
            y = top + 22
            rec_rows = []
            for i, r in enumerate(recs):
                d = r["doc"]
                s = lab.minutes(t0, d["created_at"])
                yy = y + i * row
                g = VGroup(at(fit(f"written #{i + 1}  {d['_id']}", 14, X0 - LABEL_X - 16), LABEL_X, yy))
                dur = d.get("duration") if r["collection"] == "treatments" else None
                if isinstance(dur, (int, float)) and dur > 0:
                    g.add(bar(ax.x(s), ax.x(min(s + dur, hi)), yy, row * 0.5, "#e6e6e6", RULE))
                g.add(dot(ax.x(s), yy, r=4.5))
                g.add(at(fit(lab.describe(r), 14, X1 + 40 - ax.x(s) - 12), ax.x(s) + 10, yy))
                rec_rows.append(g)
            y += len(recs) * row + 4
            sep1 = hline(LABEL_X, 1240, y - row / 2 + 2)
            der_rows = []
            for i, (who, ink, tint, (wid, s, e, bits)) in enumerate(derived):
                yy = y + i * row
                g = VGroup(at(fit(f"{who}  {wid}", 14, X0 - LABEL_X - 16, color=ink), LABEL_X, yy))
                xe = ax.x(min(e, hi)) if e is not None else ax.x(hi)
                g.add(bar(ax.x(s), xe, yy, row * 0.55, tint, ink))
                if e is None or e > hi:
                    g.add(tri_right(ax.x(hi), yy, ink))
                bits = list(bits)
                if e is None:
                    bits.append("no end")
                elif e > hi:
                    bits.append(f"ends +{num(e)} min")
                lbl = T(", ".join(bits), 14)
                if width_px(lbl) + 10 <= xe - ax.x(s):
                    g.add(at(lbl, ax.x(s) + 5, yy))
                elif xe + 12 + width_px(lbl) <= X1 + 40:
                    g.add(at(lbl, xe + 12, yy))
                else:
                    g.add(at(lbl, ax.x(s) - 6, yy, "right"))
                der_rows.append(g)
            y += len(derived) * row + 8
            sep2 = hline(LABEL_X, 1240, y - row / 2 + 4)
            ry = [y + 10 + j * 34 for j in range(len(rows))]
            labels = VGroup(*[at(T(name, 14, color=ORANGE if cmp_ else INK), LABEL_X, yy)
                              for (name, cmp_, _), yy in zip(rows, ry)])
            axis_y = ry[-1] + 30
            axis = VGroup(hline(X0, X1, axis_y, MUTED))
            for t in ax.ticks(step):
                axis.add(at(T(f"+{num(t)}", 14, MUTED), ax.x(t), axis_y + 16, "center"))
            axis.add(at(T("minutes after T0", 14, MUTED), LABEL_X, axis_y + 16))

            self.play(FadeIn(sub), FadeIn(frame), FadeIn(axis), run_time=0.4)
            self.play(LaggedStart(*[FadeIn(g, shift=LEFT * 0.2) for g in rec_rows], lag_ratio=0.6 / len(rec_rows) * 2,
                                  run_time=1.2))
            self.wait(0.4)
            self.play(FadeIn(sep1), *[GrowFromEdge(g, LEFT) for g in der_rows], run_time=0.8)
            self.wait(0.8)
            self.play(FadeIn(sep2), FadeIn(labels), run_time=0.3)
            cursor = vdash(ax.x(0), top + 12, axis_y)
            self.play(FadeIn(cursor), run_time=0.2)
            for q, m in zip(case["queries"], qs):
                x = ax.x(m)
                self.play(cursor.animate.move_to([P(x, 0)[0], cursor.get_center()[1], 0]), run_time=0.5,
                          rate_func=linear)
                self.add(vdash(x, top + 12, axis_y, color=RULE))
                cells = []
                trow = [cid, q["label"]]
                for (name, cmp_, vals), yy in zip(rows, ry):
                    k = vals[q["label"]]
                    bad = cmp_ and k != crm_q[q["label"]]
                    s = ("≠ " if bad else "") + lab.show_key(k)
                    cells.append(cell(s, x, yy, edge=BAD if bad else RULE, fill=BAD_T if bad else CARD, bold=bad,
                                      max_left=X0 - 30, max_right=1246))
                    trow.append((s, bad))
                while len(trow) < 5:
                    trow.append(("—", False))
                table.append(trow)
                self.play(*[FadeIn(c) for c in cells], run_time=0.3)
                self.wait(0.9)
            self.wait(0.3)
            self.play(*[FadeOut(m) for m in self.mobjects if m is not footer and m is not title], run_time=0.4)

        self.summary(table, title)

    def summary(self, table, title):
        """The poster: every reading of the three cases, Nocturne's that differ marked ≠."""
        g = VGroup(at(T("Two hubs, one record set: what each reports as active at each query time", 24, bold=True),
                      40, 30))
        cols = [40, 250, 340, 620, 900]
        heads = ["case", "query", "cgm-remote-monitor", "Nocturne latest span", "Nocturne list read"]
        y = 74
        g.add(box(28, 56, 1252, 74 + 26 + 34 * len(table) + 6, FAINT))
        for x, h in zip(cols, heads):
            g.add(at(T(h, 16, bold=True, color=ORANGE if h.startswith("Nocturne") else INK), x, y))
        y += 34
        prev = None
        for r in table:
            if r[0] != prev:
                g.add(hline(40, 1240, y - 17))
                g.add(at(T(r[0], 16), cols[0], y))
                prev = r[0]
            g.add(at(T(r[1], 16, MUTED), cols[1], y))
            for x, (s, bad) in zip(cols[2:], r[2:]):
                c = cell(s, 0, y, edge=BAD if bad else RULE, fill=BAD_T if bad else CARD, bold=bad, size=14)
                c.move_to(P(x, y), aligned_edge=LEFT)
                g.add(c)
            y += 34
        self.play(FadeOut(title), FadeIn(g), run_time=0.6)
        self.wait(2.5)
