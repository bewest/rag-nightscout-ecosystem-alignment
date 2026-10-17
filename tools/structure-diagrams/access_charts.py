#!/usr/bin/env python3
"""The key-custody ladder and the device x path matrix, drawn from access/devices.yaml.

  access_charts.py [-o OUTDIR]

Writes <OUTDIR>/1-access-ladder.svg and <OUTDIR>/1-access-matrix.svg (default OUTDIR:
docs/00-overview/perspective/diagrams/). Same card, font and text measure as render.py.

Matrix cells carry a state (open, conditional, closed, unknown) as a tint, a glyph and the cell's
own text, so the state never rests on colour alone. Tints are the dataviz status steps (good,
warning, critical) mixed with white; ink stays dark on every fill.
"""
import argparse
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from render import DIAGRAMS, FONT, tw  # noqa: E402

DATA = HERE / "access" / "devices.yaml"
INK, MUTED, RULE, CARD = "#111111", "#555555", "#c8c8c8", "#ffffff"
STEP_FILL = ["#eef3fa", "#d6e3f4", "#b9cfec", "#97b7e1"]   # one hue, light to dark: dependence
STATE = {   # tint, stripe, glyph, legend text
    "open": ("#e2f3e2", "#0ca30c", "●", "available without the manufacturer's permission"),
    "cond": ("#fdf0d2", "#c98a00", "◆", "available on conditions or at the manufacturer's discretion"),
    "closed": ("#f7dede", "#d03b3b", "○", "not available to open software"),
    "unknown": ("#eeeeee", "#8a8a8a", "?", "not checked, not read or not collected"),
}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wrap(s, fs, width):
    lines, cur = [], ""
    for w in str(s).split():
        t = (cur + " " + w).strip()
        if cur and tw(t, fs) > width:
            lines.append(cur)
            cur = w
        else:
            cur = t
    return lines + ([cur] if cur else [])


def text(x, y, s, fs=11, fill=INK, anchor="start", weight=None):
    w = f' font-weight="{weight}"' if weight else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs}" fill="{fill}" text-anchor="{anchor}"{w}>{esc(s)}</text>'


def svg(w, h, title, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'font-family="{FONT}">\n<title>{esc(title)}</title>\n'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="{CARD}"/>\n' + "\n".join(body) + "\n</svg>\n")


def ladder(d):
    rungs, devs = d["rungs"], d["devices"]
    colw, gap, m, rise = 222, 14, 18, 34
    w = m * 2 + len(rungs) * colw + (len(rungs) - 1) * gap
    body = [text(w / 2, 26, "1·access-ladder · How much an open app depends on the manufacturer", 14, anchor="middle")]
    cols, tallest = [], 0
    for i, r in enumerate(rungs):
        head = wrap(f'{r["id"]} · {r["title"]}', 11.5, colw - 24)
        need = wrap(r["needs"], 10, colw - 20)
        items = [(x["name"], x["type"]) for x in devs if x["rung"] == r["id"]]
        modes = d.get("modes", {}).get(r["id"], [])
        note = d.get("notes", {}).get(r["id"])
        h = 28 + len(head) * 14 + len(need) * 12 + 10 + sum(22 for _ in items)
        h += sum(len(wrap(x, 10, colw - 28)) * 12 + 10 for x in modes)
        h += (len(wrap(note, 9.5, colw - 20)) * 12 + 8) if note else 0
        cols.append((r, head, need, items, modes, note, h))
        tallest = max(tallest, h + (len(rungs) - 1 - i) * rise)
    top = 52
    base = top + tallest + 14
    for i, (r, head, need, items, modes, note, h) in enumerate(cols):
        x = m + i * (colw + gap)
        y = top + (len(rungs) - 1 - i) * rise
        body.append(f'<rect x="{x}" y="{y}" width="{colw}" height="{base - y}" rx="6" fill="{STEP_FILL[i]}" stroke="{RULE}"/>')
        for j, ln in enumerate(head):
            body.append(text(x + 10, y + 20 + j * 14, ln, 11.5, weight="bold"))
        yy = y + 24 + len(head) * 14
        for ln in need:
            body.append(text(x + 10, yy, ln, 10, MUTED))
            yy += 12
        yy += 6
        for name, kind in items:
            body.append(f'<rect x="{x + 10}" y="{yy}" width="{colw - 20}" height="18" rx="4" fill="{CARD}" stroke="{RULE}"/>')
            body.append(text(x + 16, yy + 13, name, 10.5))
            body.append(text(x + colw - 16, yy + 13, "pump" if kind == "pump" else "CGM", 9, MUTED, "end"))
            yy += 22
        for mo in modes:
            ls = wrap(mo, 10, colw - 28)
            body.append(f'<rect x="{x + 10}" y="{yy}" width="{colw - 20}" height="{len(ls) * 12 + 6}" rx="4" '
                        f'fill="{CARD}" stroke="{RULE}" stroke-dasharray="3,2"/>')
            for j, ln in enumerate(ls):
                body.append(text(x + 16, yy + 13 + j * 12, ln, 10))
            yy += len(ls) * 12 + 10
        if note:
            for ln in wrap(note, 9.5, colw - 20):
                body.append(text(x + 10, yy + 10, ln, 9.5, MUTED))
                yy += 12
    unplaced = [x["name"] + (f' ({x["open_note"]})' if x.get("open_note") else "") for x in devs if x["rung"] is None]
    foot = [
        "Rising steps: more dependence on the manufacturer. Solid boxes are device lines; dashed boxes are modes, used",
        "where no direct implementation is in use. Not placed (custody not determined): " + "; ".join(unplaced) + ".",
        "Sources: device-layer census 2026-09-30 §2–§3; vendor note §1.6 and §5.1. Mechanism level only.",
    ]
    for j, ln in enumerate(foot):
        body.append(text(m, base + 22 + j * 13, ln, 9.5, MUTED))
    return svg(w, int(base + 22 + len(foot) * 13 + 6), "1·access-ladder", body)


def states(x):
    r = {"A": "open", "B": "cond", "C": "closed", "D": "closed", None: "unknown"}[x["rung"]]
    rl = {"A": "A · protocol and what the person has", "B": "B · vendor app alongside",
          "C": "C · issued credential", "D": "D · sealed", None: "not determined"}[x["rung"]]
    o = x["open"]
    op = "open" if o >= 2 else "cond" if o == 1 else "closed"
    ot = f'{o}' + (f' ({x["open_note"]})' if x.get("open_note") else "")

    def cls(v, cond=(), closed=("none found", "none published", "partner-only", "by invitation")):
        if v in ("not checked", "not read", "not stated", "not collected"):
            return "unknown"
        if v in closed:
            return "closed"
        return "cond"
    return [(rl, r), (ot, op), (x["cloud"], cls(x["cloud"])), (x["outside"], cls(x["outside"])),
            (x["realtime"], cls(x["realtime"])), ("not collected", "unknown")]


def matrix(d):
    heads = ["device link", "open implementations", "vendor cloud route\nused by connectors",
             "manufacturer's route\nfor outsiders", "real-time route\nfor outsiders", "supply"]
    cw = [230, 120, 190, 150, 130, 100]
    namew, rh, m, hh = 236, 24, 18, 38
    w = m * 2 + namew + sum(cw)
    body = [text(w / 2, 26, "1·access-matrix · Each device line, path by path", 14, anchor="middle")]
    y0 = 48
    x = m + namew
    for h, c in zip(heads, cw):
        for j, ln in enumerate(h.split("\n")):
            body.append(text(x + 8, y0 + 14 + j * 12, ln, 10, MUTED, weight="bold"))
        x += c
    y = y0 + hh
    last = None
    for dv in d["devices"]:
        if dv["type"] != last:
            body.append(text(m, y + 15, "Pumps" if dv["type"] == "pump" else "CGMs", 10.5, MUTED, weight="bold"))
            y += 22
            last = dv["type"]
        body.append(text(m + 8, y + 16, dv["name"], 10.5))
        x = m + namew
        for (t, st), c in zip(states(dv), cw):
            tint, stripe, glyph, _ = STATE[st]
            body.append(f'<rect x="{x + 1}" y="{y + 1}" width="{c - 2}" height="{rh - 2}" fill="{tint}"/>')
            body.append(f'<rect x="{x + 1}" y="{y + 1}" width="3" height="{rh - 2}" fill="{stripe}"/>')
            body.append(text(x + 10, y + 16, glyph, 10, stripe))
            body.append(text(x + 22, y + 16, t, 10))
            x += c
        y += rh
    y += 16
    for i, (k, (tint, stripe, glyph, desc)) in enumerate(STATE.items()):
        lx = m + (i % 2) * 420
        ly = y + (i // 2) * 18
        body.append(f'<rect x="{lx}" y="{ly}" width="16" height="13" fill="{tint}" stroke="{stripe}"/>')
        body.append(text(lx + 4, ly + 10.5, glyph, 9.5, stripe))
        body.append(text(lx + 24, ly + 10.5, desc, 10))
    y += 52
    foot = ["Sources: device-layer census 2026-09-30 §2–§3; nightscout-connect 04102f9; tconnectsync 7c4b2f4;",
            "vendor note §1 (read 2026-10-17). Open implementation counts are the census's, counting a port as one.",
            "Device link letters are the rungs of 1·access-ladder. Supply dates have not been collected."]
    for j, ln in enumerate(foot):
        body.append(text(m, y + j * 13, ln, 9.5, MUTED))
    return svg(w, int(y + len(foot) * 13 + 6), "1·access-matrix", body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--outdir", type=Path, default=DIAGRAMS)
    a = ap.parse_args()
    d = yaml.safe_load(DATA.read_text())
    for name, fn in (("1-access-ladder", ladder), ("1-access-matrix", matrix)):
        p = a.outdir / f"{name}.svg"
        p.write_text(fn(d))
        print(p)


if __name__ == "__main__":
    main()
