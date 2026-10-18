"""How each controller encodes an end: one panel per stateSpans kind of each well-known registration.

Input (read-derived): specs/sync/registrations/{loop,trio,androidaps}.yaml. Each panel draws, on a
schematic time line (no scale), the records a controller writes for one instance of the kind and
the instance a hub derives from them under state and intent A4-A6 and A13:

  ended early            from wire.endedEncoding: amend-duration, delete-and-repost,
                         repost-same-created_at, zero-duration-record, sampled-state
  cancelled before start from wire.cancelBeforeStartEncoding: delete, soft-delete,
                         zero-duration-record
and lists the carrier, identity, duration unit, indefinite sentinel, slot flags and end reasons.
The controller source commits in the footer are the ones the kind's evidence cites.
"""
import re

import yaml

from svgkit import (BAD, BLUE, BLUE_T, CARD, FAINT, FS, FS_SMALL, FS_TITLE, INK, MUTED, REPO, RULE, W,
                    arrow_right, cross, line, rect, svg, text, tick, tw, wrap)

REG = REPO / "specs" / "sync" / "registrations"
CONTROLLERS = ["loop", "trio", "androidaps"]
INPUTS = [REG / f"{c}.yaml" for c in CONTROLLERS]

PAD = 12
LABEL_W = 150
X0, X1 = PAD + LABEL_W, W - PAD - 10
ROW = 20
# schematic times, as fractions of the plot: start, early end, planned end, "now" for before-start
T_START, T_END, T_PLAN = 0.04, 0.24, 0.44


def px(f):
    return X0 + f * (X1 - X0)


def val(v):
    if isinstance(v, dict):
        return f"other: {v.get('controllerTerm')}"
    return v


def bar(out, y, a, b, label, solid=True, ink=INK, fill="#e6e6e6", end_arrow=False):
    out.append(rect(px(a), y + 4, px(b) - px(a), ROW - 8, fill, ink if solid else MUTED, rx=2,
                    dash=None if solid else "4,3"))
    if end_arrow:
        out.append(arrow_right(px(b), y + ROW / 2, ink))
    if label:
        out.append(text(px(b) + (14 if end_arrow else 8), y + 14, label, FS_SMALL, INK))


def row_label(out, y, s, ink=INK):
    out.append(text(PAD + 6, y + 14, s, FS_SMALL, ink))


def ident(wire):
    return " + ".join(wire.get("identity") or []) or "no identity"


def ended_rows(wire):
    """Rows for an instance ended early: [(row label, draw function)]."""
    enc = val(wire.get("endedEncoding")) if wire else None
    idn = ident(wire) if wire else ""
    dur = wire.get("durationField") if wire else None
    rows = []
    if enc == "amend-duration":
        rows.append(("write 1", lambda o, y: bar(o, y, T_START, T_PLAN, f"{idn} = k, {dur} D")))
        rows.append(("write 2 (amend)", lambda o, y: bar(o, y, T_START, T_END, f"same {idn} = k, {dur} shortened")))
    elif enc == "delete-and-repost":
        def deleted(o, y):
            bar(o, y, T_START, T_PLAN, None)
            o.append(cross(px(T_END), y + ROW / 2, BAD))
            o.append(text(px(T_PLAN) + 8, y + 14, "deleted when it ends early", FS_SMALL, INK))
        rows.append(("write 1, then delete", deleted))
        rows.append(("write 2 (re-post)", lambda o, y: bar(o, y, T_START, T_END,
                                                            f"new _id, same {idn}, {dur} shortened")))
    elif enc == "repost-same-created_at":
        rows.append(("write 1", lambda o, y: bar(o, y, T_START, T_PLAN, f"{idn} = k, {dur} D")))
        rows.append(("write 2 (re-post)", lambda o, y: bar(o, y, T_START, T_END,
                                                            f"same {idn} = k, {dur} shortened")))
    elif enc == "zero-duration-record":
        rows.append(("write 1", lambda o, y: bar(o, y, T_START, T_PLAN, f"{dur} D")))

        def marker(o, y):
            o.append(tick(px(T_END), y + ROW / 2, INK))
            o.append(text(px(T_END) + 8, y + 14, f"{dur} 0 (end marker)", FS_SMALL, INK))
        rows.append(("write 2", marker))
    elif enc == "sampled-state":
        path = (wire.get("paths") or ["value"])[0]

        def samples(o, y):
            vals = ["a", "a", "a", "b", "b"]
            for i, v in enumerate(vals):
                f = T_START + i * (T_PLAN - T_START) / (len(vals) - 1)
                o.append(tick(px(f), y + ROW / 2, INK, r=3.5))
                o.append(text(px(f) + 6, y + 14, v, FS_SMALL, INK))
            o.append(text(px(T_PLAN) + 20, y + 14, f"{path} on every record", FS_SMALL, INK))
        rows.append((f"{wire['collection']} records", samples))
    return enc, rows


def instance_row(enc):
    def draw(o, y):
        if enc == "sampled-state":
            step = (T_PLAN - T_START) / 4
            o.append(rect(px(T_START), y + 4, px(T_START + 3 * step) - px(T_START), ROW - 8, BLUE_T, BLUE, rx=2))
            o.append(text(px(T_START) + 4, y + 14, "a", FS_SMALL, INK))
            o.append(rect(px(T_START + 3 * step), y + 4, px(T_PLAN) - px(T_START + 3 * step), ROW - 8, BLUE_T, BLUE,
                          rx=2))
            o.append(arrow_right(px(T_PLAN), y + ROW / 2, BLUE))
            o.append(text(px(T_START + 3 * step) + 4, y + 14, "b", FS_SMALL, INK))
            o.append(text(px(T_PLAN) + 14, y + 14, "each value holds until the next (A13)", FS_SMALL, INK))
        else:
            o.append(rect(px(T_START), y + 4, px(T_END) - px(T_START), ROW - 8, BLUE_T, BLUE, rx=2))
            o.append(line(px(T_END), y + 2, px(T_END), y + ROW - 2, BLUE, 2))
            o.append(text(px(T_END) + 8, y + 14, "ends early: cancelled (A5)", FS_SMALL, INK))
    return draw


def before_start_rows(wire):
    enc = val(wire.get("cancelBeforeStartEncoding")) if wire else None
    now = T_START + 0.04
    if enc not in ("delete", "soft-delete", "zero-duration-record"):
        return enc, []

    def draw(o, y):
        o.append(line(px(now), y, px(now), y + ROW, MUTED, 1, "2,2"))
        bar(o, y, T_END, T_PLAN, None, solid=False, fill=CARD)
        if enc == "zero-duration-record":
            o.append(tick(px(now), y + ROW / 2, INK))
        else:
            o.append(cross(px(now), y + ROW / 2, BAD))
        what = {"delete": "delete received before the start",
                "soft-delete": "soft delete (isValid: false) before the start",
                "zero-duration-record": "zero-duration record before the start"}[enc]
        o.append(text(px(T_PLAN) + 8, y + 14, what, FS_SMALL, INK))
    return enc, [("scheduled, then", draw)]


def facts(k):
    wire = k.get("wire") or {}
    out = []
    if k.get("wire") is not None:
        carrier = wire.get("collection", "")
        if wire.get("eventType"):
            carrier += f", eventType {wire['eventType']}"
        if wire.get("documentIdentifier"):
            carrier += f", document {wire['documentIdentifier']}"
        out.append(f"carrier: {carrier}; identity: {ident(wire)}")
        if wire.get("durationField"):
            d = f"duration: {wire['durationField']} in {wire.get('durationUnit', 'no declared unit')}"
            ind = wire.get("indefinite")
            if ind:
                d += f"; open-ended: {ind['field']} = {ind['value']}"
            out.append(d)
    flags = [f"slot {k['slot']}"] if k.get("slot") else []
    flags += [f for f in ("exclusiveWithinSlot", "supersedes", "overlay") if k.get(f)]
    if k.get("coexistsWith"):
        flags.append("coexists with " + ", ".join(k["coexistsWith"]))
    if k.get("availability"):
        flags.append(k["availability"])
    out.append(" · ".join(flags))
    reasons = []
    for r in k.get("endReasons") or []:
        s = val(r["reason"])
        extra = []
        if r.get("controllerTerm"):
            extra.append(r["controllerTerm"])
        if r.get("triggers"):
            extra.append("triggers " + ", ".join(r["triggers"]))
        reasons.append(s + (f" ({'; '.join(extra)})" if extra else ""))
    out.append("end reasons: " + (", ".join(reasons) if reasons else "not declared"))
    return out


def panel(k, y):
    out = []
    top = y
    wire = k.get("wire")
    title = k["category"] + (f" · {k['kind']}" if k.get("kind") else "")
    out.append(text(PAD + 6, y + 18, title, FS, INK, weight="bold"))
    y += 26
    enc, rows = ended_rows(wire)
    bs_enc, bs_rows = before_start_rows(wire)
    lines = []
    if wire is None:
        lines.append(("on the wire", "wire: null, the controller keeps the intent and publishes no instance record",
                      []))
    elif rows:
        lines.append(("ended early", f"endedEncoding: {enc}", rows + [("instance", instance_row(enc))]))
    else:
        lines.append(("ended early", "endedEncoding: not declared", []))
    if wire is not None and enc != "sampled-state":
        lines.append(("cancelled before start",
                      f"cancelBeforeStartEncoding: {bs_enc}" if bs_enc else "cancelBeforeStartEncoding: not declared",
                      bs_rows + ([("instance", lambda o, yy: (o.append(text(px(T_START), yy + 14,
                                   "ended deletedBeforeStart, never active (A6)", FS_SMALL, INK))))]
                                 if bs_enc in ("delete", "soft-delete") else [])))
    for name, head, rs in lines:
        out.append(text(PAD + 6, y + 14, name, FS_SMALL, MUTED, weight="bold"))
        out.append(text(X0, y + 14, head, FS_SMALL, INK))
        y += ROW
        for lbl, draw in rs:
            row_label(out, y, lbl, BLUE if lbl == "instance" else INK)
            draw(out, y)
            y += ROW
        y += 4
    for f in facts(k):
        for s in wrap(f, W - 2 * PAD - 12, FS_SMALL):
            out.append(text(PAD + 6, y + 13, s, FS_SMALL, MUTED))
            y += 16
    y += 8
    return [rect(PAD, top, W - 2 * PAD, y - top, FAINT, rx=6)] + out, y + 10, enc


def sources(k):
    found = []
    for e in k.get("evidence") or []:
        m = re.match(r"([A-Za-z]+) ([0-9a-f]{7,})\b", str(e.get("source", "")))
        if m and f"{m.group(1)} {m.group(2)}" not in found:
            found.append(f"{m.group(1)} {m.group(2)}")
    return found


def figure(name):
    reg = yaml.safe_load((REG / f"{name}.yaml").read_text())
    product = reg["metadata"]["product"]
    title = f"How {product} encodes an end, per intent kind"
    body = [text(PAD, 24, title, FS_TITLE, INK, weight="bold")]
    sub = wrap("Schematic, not to scale. Black bars are the records the controller writes (dashed: "
               "scheduled, not yet started); the blue bar is the instance a hub derives from them under "
               "the state and intent rules named in brackets. k is one identity value, D a duration.",
               W - 2 * PAD, FS_SMALL)
    for i, s in enumerate(sub):
        body.append(text(PAD, 44 + i * 15, s, FS_SMALL, MUTED))
    y = 44 + 15 * len(sub) + 8
    srcs, desc = [], []
    for k in reg["spec"]["stateSpans"]:
        els, y, enc = panel(k, y)
        body += els
        srcs += [s for s in sources(k) if s not in srcs]
        desc.append(f"{k['category']}: ended " + (enc or ("not on the wire" if k.get('wire') is None
                                                          else "not declared")))
    foot = (f"read-derived, specs/sync/registrations/{name}.yaml; controller source cited by its evidence: "
            + ", ".join(srcs) + ".")
    for s in wrap(foot, W - 2 * PAD, FS_SMALL):
        body.append(text(PAD, y + 4, s, FS_SMALL, MUTED, italic=True))
        y += 15
    return svg(W, y + 8, title, title + ". " + "; ".join(desc) + ". " + foot, body)


def build():
    return {f"end-encoding-{n}.svg": figure(n) for n in CONTROLLERS}
