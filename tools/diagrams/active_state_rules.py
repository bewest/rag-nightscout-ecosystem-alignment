"""The active-state rules of state and intent §6.1, one figure per rule, drawn from the conformance cases.

Input: specs/sync/conformance/active-state/*.yaml (synthetic, expectations authored by hand). Each
panel is one case:
  records      one row per record in the order the hub received it: a dot at the record's own
               time (the declared timeField, else created_at; a hollow dot at created_at when the
               two differ), a cross at receivedAt for a delete that carries one
  instances    the case's expected instances: a bar from start to end, an arrow when open-ended,
               a cross for one deleted before its start, with the expected end reason
  active at    each expected activeAt query: a dashed line and the instances active there
Nothing here applies a rule: every bar and every reading is the case's `expected` block, so the
figure changes when a case does, and the staleness test catches it.
"""
import yaml

from svgkit import (BAD, BLUE, BLUE_T, CARD, FAINT, FS, FS_SMALL, FS_TITLE, INK, MUTED, REPO, RULE, W,
                    Axis, Lanes, arrow_right, cross, esc, fit, iso, line, num, rect, svg, text, tick, tw,
                    wrap)

CASES = REPO / "specs" / "sync" / "conformance" / "active-state"
SPEC = "docs/30-design/platform/spec/state-intent.md §6.1"

# rule -> (short name, the cases drawn, in order). Each case must cite the rule, or be the control
# of a drawn case that does; build() checks this.
RULES = {
    "A3": ("start is the record's own time", ["applied-duration-in-declared-unit"]),
    "A4": ("end from the declared duration", ["running-mode-original-duration", "running-mode-open-ended",
                                              "permanent-profile-switch-returns"]),
    "A5": ("end encodings", ["zero-duration-ends-instance", "no-end-marker", "marker-at-next-start",
                             "repost-same-identity-amends"]),
    "A6": ("deletion", ["deleted-before-start", "scheduled-not-deleted", "delete-after-start-withdraws",
                        "delete-and-repost-amends", "soft-delete-before-start"]),
    "A7": ("supersession by start", ["backfill-supersedes-by-start", "in-order-same-result",
                                     "equal-start-last-write-wins", "deleted-before-start-does-not-supersede"]),
    "A8": ("overlay", ["overlay-returns-to-open-ended", "supersedes-without-overlay",
                       "permanent-after-temporary-supersedes"]),
    "A9": ("overlap is reported, not resolved", ["exclusive-overlap-reported", "exclusive-supersedes"]),
    "A13": ("sampled state", ["sampled-state-latest-value"]),
}
INPUTS = sorted({CASES / f"{c}.yaml" for _, cs in RULES.values() for c in cs})

PAD = 12
LABEL_W = 132
X0, X1 = PAD + LABEL_W + 8, W - PAD - 30
ROW = 20


def load(cid):
    return yaml.safe_load((CASES / f"{cid}.yaml").read_text())


def get(doc, path):
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def carriers(case, product):
    for d in case["declarations"]:
        if d["product"] != product:
            continue
        for k in d["stateSpans"]:
            for c in ("wire", "requested", "applied"):
                if k.get(c):
                    yield k[c]


def record_time(case, rec):
    for c in carriers(case, rec["product"]):
        if c.get("timeField") and get(rec["doc"], c["timeField"]) is not None:
            return get(rec["doc"], c["timeField"])
    return rec["doc"].get("created_at")


def leaves(doc, prefix=""):
    for k, v in doc.items():
        if isinstance(v, dict):
            yield from leaves(v, prefix + k + ".")
        else:
            yield prefix + k, v


def describe(case, rec):
    bits = []
    for path, v in leaves(rec["doc"]):
        if path in ("created_at", "eventType"):
            continue
        last = path.split(".")[-1]
        if isinstance(v, str) and len(v) == 20 and v[10] == "T":
            v = iso(v).strftime("%H:%M")
        if isinstance(v, bool):
            v = str(v).lower()
        bits.append(f"{last} {v}")
    return ", ".join(bits)


def short_key(key):
    """An instance key for display: ISO times as HH:MM, identity parts joined with a comma."""
    if "@" in key:
        kind, at = key.split("@", 1)
        return f"{kind} @{iso(at).strftime('%H:%M')}"
    parts = []
    for p in key.split("|"):
        f, _, v = p.partition("=")
        if len(v) == 20 and v[10:11] == "T":
            v = iso(v).strftime("%H:%M")
        parts.append(f"{f}={v}")
    return ", ".join(parts)


def hm(m, base):
    from datetime import timedelta
    return (base + timedelta(minutes=m)).strftime("%H:%M")


def panel(case, y, multi_product):
    out = []
    t0s = [iso(record_time(case, r)) for r in case["records"] if record_time(case, r)]
    t0s += [iso(r["receivedAt"]) for r in case["records"] if r.get("receivedAt")]
    t0s += [iso(i["start"]) for i in case["expected"]["instances"]]
    t0s += [iso(a["at"]) for a in case["expected"]["activeAt"]]
    ends = [iso(i["end"]) for i in case["expected"]["instances"] if i["end"]]
    base = min(t0s)
    base = base.replace(minute=(base.minute // 30) * 30, second=0)

    def m(s):
        return (iso(s) - base).total_seconds() / 60
    near = [(t - base).total_seconds() / 60 for t in t0s] + [(t - base).total_seconds() / 60 for t in ends]
    lim = max((t - base).total_seconds() / 60 for t in t0s) + 30
    hi = max([x for x in near if x <= lim * 1.6] + [lim])
    step = 30 if hi <= 240 else 60
    hi = step * -(-(hi + 10) // step)
    ax = Axis(0, hi, X0, X1)
    top = y
    head = wrap(f"{case['id']} — {case['title']}", W - 2 * PAD - 16, FS, bold=True)
    for i, h in enumerate(head):
        out.append(text(PAD + 6, y + 18 + i * 16, h, FS, INK, weight="bold"))
    y += 6 + 16 * len(head)
    meta = "rules " + ", ".join(case["rules"]) + (f" · control: {case['control']}" if case.get("control") else "")
    out.append(text(PAD + 6, y + 14, meta, FS_SMALL, MUTED))
    y += 22
    rows_top = y

    def label(yy, s, ink=INK):
        out.append(text(PAD + 6, yy + 14, fit(s, LABEL_W, FS_SMALL), FS_SMALL, ink))

    def after(x, yy, s, ink=INK):
        room = W - PAD - 6 - x
        if tw(s, FS_SMALL) <= room:
            out.append(text(x, yy + 14, s, FS_SMALL, ink, halo=True))
        else:
            out.append(text(x, yy + 14, fit(s, room, FS_SMALL), FS_SMALL, ink, halo=True))

    for i, r in enumerate(case["records"]):
        yy = y + i * ROW
        who = f" {r['product']}" if multi_product else ""
        label(yy, f"#{i + 1} {r['op']}{who}")
        desc = describe(case, r)
        if r["op"] == "delete":
            if r.get("receivedAt"):
                x = ax.x(m(r["receivedAt"]))
                out.append(cross(x, yy + ROW / 2, BAD))
                after(x + 10, yy, f"delete received {iso(r['receivedAt']).strftime('%H:%M')} of {desc}")
            else:
                after(X0, yy, f"delete of {desc} (no time)")
            continue
        t = record_time(case, r)
        x = ax.x(m(t))
        c = r["doc"].get("created_at")
        if c and c != t:
            out.append(line(ax.x(m(c)), yy + ROW / 2, x, yy + ROW / 2, MUTED, 1, "2,2"))
            out.append(tick(ax.x(m(c)), yy + ROW / 2, INK, filled=False))
        out.append(tick(x, yy + ROW / 2, INK))
        xr = max(x, ax.x(m(c)) if c else x)
        after(xr + 9, yy, desc)
    y += ROW * len(case["records"]) + 4
    out.append(rect(PAD + 6, y, W - 2 * PAD - 12, 1, RULE))
    y += 4

    insts = case["expected"]["instances"]
    layers = len({i["layer"] for i in insts}) > 1
    kinds = len({i["kind"] for i in insts}) > 1
    for j, inst in enumerate(insts):
        yy = y + j * ROW
        extra = ([inst["product"]] if multi_product else []) + ([inst["layer"]] if layers else [])
        label(yy, "instance" + (f" ({', '.join(extra)})" if extra else ""), BLUE)
        name = short_key(inst["key"])
        s = ax.x(m(inst["start"]))
        reason = inst["endReason"]
        if inst["end"] == inst["start"] and reason == "deletedBeforeStart":
            out.append(cross(s, yy + ROW / 2, BAD))
            after(s + 10, yy, f"{name}, {reason}")
            continue
        e = m(inst["end"]) if inst["end"] else None
        xe = ax.x(min(e, hi)) if e is not None else ax.x(hi)
        out.append(rect(s, yy + 4, max(xe - s, 3), ROW - 8, BLUE_T, BLUE, rx=2))
        bits = [name]
        if e is None:
            out.append(arrow_right(ax.x(hi), yy + ROW / 2, BLUE))
            bits.append("open-ended")
        elif e > hi:
            out.append(arrow_right(ax.x(hi), yy + ROW / 2, BLUE))
            bits.append("ends " + iso(inst["end"]).strftime("%d %b %H:%M"))
        if reason:
            bits.append(reason)
        if bits:
            lbl = ", ".join(bits)
            if tw(lbl, FS_SMALL) + 8 <= xe - s:
                out.append(text(s + 4, yy + 14, lbl, FS_SMALL, INK))
            elif e is not None and e <= hi:
                after(xe + 6, yy, lbl)
            else:
                out.append(text(s - 4, yy + 14, lbl, FS_SMALL, INK, anchor="end", halo=True))
    if not insts:
        label(y, "no instances", BLUE)
        insts = [None]
    y += ROW * len(insts) + 4
    out.append(rect(PAD + 6, y, W - 2 * PAD - 12, 1, RULE))
    y += 4

    # active at: one cell per query, stacked into sub-rows where they would touch
    label(y + 2, "active at")
    lanes = Lanes(4)
    cells = []
    for a in case["expected"]["activeAt"]:
        names = []
        for x in a["active"]:
            n = short_key(x["key"])
            if multi_product:
                n += f" ({x['product']})"
            if layers:
                n += f" [{x['layer']}]"
            if x.get("value") is not None:
                n += f" = {x['value']}"
            if x.get("overlap"):
                n += " (overlap)"
            names.append(n)
        s = " + ".join(names) if names else "none"
        cw = tw(s, FS_SMALL) + 12
        cx = min(max(ax.x(m(a["at"])) - cw / 2, X0 - 8), W - PAD - 6 - cw)
        cells.append((a["at"], s, cx, cw, lanes.place(cx, cx + cw)))
    for at, s, cx, cw, k in cells:
        yy = y + k * (ROW + 4)
        out.append(rect(cx, yy + 2, cw, ROW, CARD, BLUE, rx=3))
        out.append(text(cx + cw / 2, yy + 16, s, FS_SMALL, INK, anchor="middle"))
    y += len(lanes.rows) * (ROW + 4) + 2
    for key in ("unreadable", "stateVersion"):
        if key in case["expected"]:
            v = case["expected"][key]
            s = f"{key}: " + (", ".join(str(x) for x in v) if isinstance(v, list) else "expected")
            for line_ in wrap(s, W - 2 * PAD - 12, FS_SMALL):
                out.append(text(PAD + 6, y + 14, line_, FS_SMALL, MUTED))
                y += 16
    lines = [line(ax.x(m(a["at"])), rows_top, ax.x(m(a["at"])), y, "#9a9a9a", 1, "3,3")
             for a in case["expected"]["activeAt"]]
    axis = [line(X0, y + 4, X1, y + 4, RULE)]
    for t in ax.ticks(step):
        axis.append(line(ax.x(t), y + 4, ax.x(t), y + 8, MUTED))
        axis.append(text(ax.x(t), y + 21, hm(t, base), FS_SMALL, MUTED, anchor="middle"))
    axis.append(text(PAD + 6, y + 21, "UTC", FS_SMALL, MUTED))
    y += 30
    return [rect(PAD, top, W - 2 * PAD, y - top, FAINT, rx=6)] + lines + out + axis, y + 10


def rule_text():
    """The rule's sentence from the spec, for the figure's description."""
    import re
    spec = (REPO / "docs/30-design/platform/spec/state-intent.md").read_text()
    out = {}
    for m in re.finditer(r"^\| (A\d+) \| \*\*(.+?)\*\* (.+?) \|$", spec, re.M):
        out[m.group(1)] = (m.group(2), m.group(3))
    return out


def figure(rule, cases):
    name, ids = RULES[rule]
    texts = rule_text()
    if rule not in texts:
        raise SystemExit(f"{rule} not found in {SPEC}")
    heading, sentence = texts[rule]
    title = f"{rule} · {heading.rstrip('.')}"
    body = [text(PAD, 24, title, FS_TITLE, INK, weight="bold")]
    sub = wrap("Each panel is one conformance case: the records in the order the hub received them, the "
               "instances the case expects (blue), and what it expects to be active at each dashed line. A "
               "hollow dot is created_at, where the record's time comes from another declared field.",
               W - 2 * PAD, FS_SMALL)
    for i, s in enumerate(sub):
        body.append(text(PAD, 44 + i * 15, s, FS_SMALL, MUTED))
    y = 44 + 15 * len(sub) + 8
    for cid in ids:
        c = cases[cid]
        multi = len({r["product"] for r in c["records"]}) > 1
        els, y = panel(c, y, multi)
        body += els
    foot = (f"Rule {rule}, {SPEC}; cases from specs/sync/conformance/active-state/ ({', '.join(ids)}). "
            "Synthetic; expectations authored by hand.")
    for s in wrap(foot, W - 2 * PAD, FS_SMALL):
        body.append(text(PAD, y + 4, s, FS_SMALL, MUTED, italic=True))
        y += 15
    import re
    plain = re.sub(r"[`*]", "", sentence)
    desc = f"{title}: {plain} Cases drawn: " + "; ".join(f"{cid}: {cases[cid]['title']}" for cid in ids) + "."
    return svg(W, y + 8, title, desc, body)


def build():
    cases = {}
    for _, ids in RULES.values():
        for cid in ids:
            cases[cid] = load(cid)
    for rule, (_, ids) in RULES.items():
        for cid in ids:
            c = cases[cid]
            if rule in c["rules"]:
                continue
            if not any(cases[o].get("control") == cid and rule in cases[o]["rules"] for o in ids):
                raise SystemExit(f"{cid} is drawn for {rule} but neither cites it nor is the control of a case that does")
    return {f"active-state-{r.lower()}.svg": figure(r, cases) for r in RULES}
