"""Two hubs, one record set: the hub-active-state lab results drawn as paired timelines.

Inputs (measured): tools/lab/hub-active-state/records/cases.json (the records, in arrival order),
results/crm.json and results/nocturne.json (what each hub reported at each query time, and the
spans Nocturne stored), and results/RESULTS.md (the run date and the two commits).

One panel per case (role "case"; the controls agree on every reading and are not drawn):
  written           one row per record in arrival order: a dot at created_at and, for a treatment
                    with a duration above 0, a grey bar for the written minutes
  Nocturne stored   one row per StateSpan Nocturne stored for the case
  readings          at each query time, cgm-remote-monitor's answer and Nocturne's, each Nocturne
                    cell that differs from cgm-remote-monitor's tinted red and marked "≠"
"""
import json
import re

from svgkit import (BAD, BAD_T, BLUE, BLUE_T, CARD, FAINT, FS, FS_SMALL, FS_TITLE, INK, MUTED, ORANGE, ORANGE_T,
                    REPO, RULE, W, Axis, Lanes, arrow_right, esc, fit, iso, line, nice_step, num,
                    rect, svg, text, tick, tw, wrap)

LAB = REPO / "tools" / "lab" / "hub-active-state"
INPUTS = [LAB / "records" / "cases.json", LAB / "results" / "crm.json", LAB / "results" / "nocturne.json",
          LAB / "results" / "RESULTS.md"]

FIGURES = {   # file name -> (title, cases)
    "hub-active-state-treatments": (
        "Two hubs, one record set: temporary targets and overrides from treatments",
        ["c1-tt-cancel", "c2-ov-cancel", "c6-tt-same-ms", "c7-ov-backfill"]),
    "hub-active-state-devicestatus-profile": (
        "Two hubs, one record set: Loop's devicestatus override and profile switches",
        ["c3-loop-ds-override", "c4-ps-timed-after-permanent", "c5-aaps-timeshift-ms"]),
}

LIST_ASKS = ("tt", "override_tx")   # the asks compare.js reads a Nocturne list for
LABEL_W = 200
X0, X1 = LABEL_W + 14, W - 26
ROW = 20
PAD = 12


def load():
    cases = json.loads(INPUTS[0].read_text())
    crm = json.loads(INPUTS[1].read_text())
    noc = json.loads(INPUTS[2].read_text())
    results = INPUTS[3].read_text()
    date = re.search(r"^# hub-active-state — results, (\d{4}-\d{2}-\d{2})", results, re.M)
    commits = re.search(r"^\| Commit \| `([0-9a-f]{40})`.*?\| `([0-9a-f]{40})` \|", results, re.M)
    if not (date and commits):
        raise SystemExit("RESULTS.md: run date or commit row not found")
    run = {"date": date.group(1), "crm": commits.group(1)[:8], "nocturne": commits.group(2)[:9],
           "crm_version": crm["version"]}
    return cases, crm, noc, run


def minutes(t0, s):
    return (iso(s) - t0).total_seconds() / 60


def show_key(k):
    m = re.fullmatch(r"(\S+) basal=([\d.]+)", k)
    if m:
        return f"{m.group(1)}, basal {m.group(2)}"
    return " + ".join(k.split("+"))


def describe(rec):
    d = rec["doc"]
    if rec["collection"] == "devicestatus":
        o = d.get("override", {})
        return f"devicestatus override, duration {o['duration']}" if o.get("active") else \
            "devicestatus override, active: false"
    bits = [d["eventType"]]
    for f in ("profile", "duration", "durationType", "percentage", "timeshift"):
        if f in d:
            bits.append(f"{f} {d[f]}")
    return ", ".join(bits)


def crm_windows(crm_case, ask, t0):
    """The windows cgm-remote-monitor reported at the query times, once each, in first-seen order."""
    seen, out = set(), []
    for q in crm_case["queries"]:
        a = q["answers"][ask]
        if ask == "tt":
            ws = [(w["id"], w["start"], w["minutes"]) for w in a["processed"]]
        elif ask == "override_tx":
            ws = [(w["id"], w["start"], w["minutes"]) for w in a["detail"]]
        elif ask == "override_ds" and a["detail"].get("active"):
            d = a["detail"]
            ws = [(f"from +{num(minutes(t0, d['fromDevicestatusAt']))}", d["fromDevicestatusAt"],
                   (iso(d["end"]) - iso(d["fromDevicestatusAt"])).total_seconds() / 60 if d["end"] else None)]
        else:
            ws = []
        for wid, start, mins in ws:
            if wid in seen:
                continue
            seen.add(wid)
            s = minutes(t0, start)
            e = s + mins if isinstance(mins, (int, float)) else None
            out.append((wid, s, e, ["window"]))
    return out


def noc_spans(noc_case, t0):
    out = []
    for sp in noc_case["spans"]:
        bits = [sp["state"]] + (["superseded"] if sp["superseded"] else [])
        out.append((sp["originalId"], minutes(t0, sp["start"]),
                    minutes(t0, sp["end"]) if sp["end"] else None, bits))
    return out


def panel(case, crm_case, noc_case, t0, y):
    """Draw one case from y; return (elements, new y, disagreement count, reading count)."""
    out = []
    ask = case["asks"][0]
    qs = [minutes(t0, q["t"]) for q in case["queries"]]
    ends = []
    for r in case["records"]:
        s = minutes(t0, r["doc"]["created_at"])
        ends.append(s)
    hi = max(qs) * 1.15
    step = nice_step(hi)
    hi = step * -(-hi // step)
    ax = Axis(0, hi, X0, X1)

    # header
    head = wrap(f"{case['id']} · {case['claim']} — {case['title']}", W - 2 * PAD - 8, FS, bold=True)
    for i, h in enumerate(head):
        out.append(text(PAD, y + 14 + i * 16, h, FS, INK, weight="bold"))
    y += 14 + 16 * len(head)

    # query labels and axis ticks
    top = y
    for q, m in zip(case["queries"], qs):
        out.append(text(ax.x(m), y + 12, q["label"], FS_SMALL, MUTED, anchor="middle"))
    y += 18
    rows_top = y

    def lane_label(yy, s, color=INK, italic=False):
        out.append(text(PAD, yy + 14, fit(s, LABEL_W - 4, FS_SMALL), FS_SMALL, color, italic=italic))

    # written
    out.append(rect(PAD, y, W - 2 * PAD, 1, RULE))
    for i, r in enumerate(case["records"]):
        d = r["doc"]
        s = minutes(t0, d["created_at"])
        yy = y + 2 + i * ROW
        lane_label(yy, f"written #{i + 1}  {d['_id']}")
        dur = d.get("duration") if r["collection"] == "treatments" else None
        if isinstance(dur, (int, float)) and dur > 0:
            e = s + dur
            out.append(rect(ax.x(s), yy + 5, ax.x(ax.clip(e)) - ax.x(s), ROW - 10, "#e6e6e6", RULE, rx=2))
        out.append(tick(ax.x(s), yy + ROW / 2, INK))
        label = describe(r)
        lx = ax.x(s) + 8
        out.append(text(lx, yy + 14, fit(label, X1 - lx, FS_SMALL), FS_SMALL, INK, halo=True))
    y += 2 + ROW * len(case["records"])

    # derived spans: cgm-remote-monitor's windows as reported at the query times, Nocturne's stored spans
    derived = [("cgm-remote-monitor", BLUE, BLUE_T, w) for w in crm_windows(crm_case, ask, t0)]
    derived += [("Nocturne span", ORANGE, ORANGE_T, w) for w in noc_spans(noc_case, t0)]
    out.append(rect(PAD, y + 2, W - 2 * PAD, 1, RULE))
    y += 4
    for i, (who, ink, tint, (wid, s, e, bits)) in enumerate(derived):
        yy = y + i * ROW
        lane_label(yy, f"{who}  {wid}", ink)
        xe = ax.x(ax.clip(e)) if e is not None else ax.x(hi)
        out.append(rect(ax.x(s), yy + 4, max(xe - ax.x(s), 3), ROW - 8, tint, ink, rx=2))
        if e is None or e > hi:
            out.append(arrow_right(ax.x(hi), yy + ROW / 2, ink))
        bits = list(bits)
        if e is None:
            bits.append("no end")
        elif e > hi:
            bits.append(f"ends +{num(e)} min")
        lbl = ", ".join(bits)
        if not lbl:
            continue
        # label inside the bar when it fits, else after it, else before it
        if tw(lbl, FS_SMALL) + 8 <= xe - ax.x(s):
            out.append(text(ax.x(s) + 4, yy + 14, lbl, FS_SMALL, INK))
        elif xe + 10 + tw(lbl, FS_SMALL) <= X1:
            out.append(text(xe + 10, yy + 14, lbl, FS_SMALL, INK, halo=True))
        else:
            out.append(text(ax.x(s) - 4, yy + 14, fit(lbl, ax.x(s) - X0, FS_SMALL), FS_SMALL, INK,
                            anchor="end", halo=True))
    y += ROW * len(derived)

    # readings
    out.append(rect(PAD, y + 2, W - 2 * PAD, 1, RULE))
    y += 6
    crm_q = {q["label"]: q["answers"][ask] for q in crm_case["queries"]}
    noc_q = {q["label"]: q["answers"][ask] for q in noc_case["queries"]}
    rows = [("cgm-remote-monitor", lambda lab: crm_q[lab]["key"], False),
            ("Nocturne latest span", lambda lab: noc_q[lab]["key"], True)]
    if ask in LIST_ASKS:
        rows.append(("Nocturne list read", lambda lab: noc_q[lab]["keySet"], True))
    differ = total = 0
    for j, (name, get, compare) in enumerate(rows):
        yy = y + j * (ROW + 4)
        lane_label(yy + 1, name, ORANGE if compare else INK)
        placed = []
        for q, m in zip(case["queries"], qs):
            k = get(q["label"])
            bad = compare and k != crm_q[q["label"]]["key"]
            if compare:
                total += 1
                differ += bad
            s = ("≠ " if bad else "") + show_key(k)
            cw = tw(s, FS_SMALL) + 12
            cx = min(max(ax.x(m) - cw / 2, X0 - 6), W - PAD - cw)
            for a, b in placed:
                if not (cx + cw + 3 <= a or cx >= b + 3):
                    raise SystemExit(f"{case['id']}: reading cells overlap in {name!r}")
            placed.append((cx, cx + cw))
            out.append(rect(cx, yy + 2, cw, ROW, BAD_T if bad else CARD, BAD if bad else RULE, rx=3,
                            sw=1.5 if bad else 1))
            out.append(text(cx + cw / 2, yy + 16, s, FS_SMALL, INK, anchor="middle",
                            weight="bold" if bad else None))
    y += len(rows) * (ROW + 4) + 2

    # query lines behind everything below the labels
    lines = [line(ax.x(m), rows_top, ax.x(m), y, "#9a9a9a", 1, "3,3") for m in qs]
    # axis
    axis = [line(X0, y + 4, X1, y + 4, RULE)]
    for t in ax.ticks(step):
        axis.append(line(ax.x(t), y + 4, ax.x(t), y + 8, MUTED))
        axis.append(text(ax.x(t), y + 21, f"+{num(t)}", FS_SMALL, MUTED, anchor="middle"))
    axis.append(text(PAD, y + 21, "minutes after T0", FS_SMALL, MUTED))
    y += 30
    bg = [rect(PAD - 4, top - 34 - 16 * (len(head) - 1), W - 2 * PAD + 8,
               y - top + 38 + 16 * (len(head) - 1), FAINT, rx=6)]
    return bg + lines + out + axis, y + 14, differ, total


def figure(name, title, ids, cases, crm, noc, run):
    t0 = iso(cases["t0"])
    by = {c["id"]: c for c in cases["cases"]}
    cr = {c["id"]: c for c in crm["cases"]}
    nc = {c["id"]: c for c in noc["cases"]}
    body = [text(PAD, 24, title, FS_TITLE, INK, weight="bold")]
    sub = wrap("Each panel: the records as written (arrival order, top to bottom); the windows "
               "cgm-remote-monitor reported at the query times and the spans Nocturne stored; then what each hub reports as active at each query time. A red cell marked ≠ "
               "is a Nocturne reading that differs from cgm-remote-monitor's.", W - 2 * PAD, FS_SMALL)
    for i, s in enumerate(sub):
        body.append(text(PAD, 44 + i * 15, s, FS_SMALL, MUTED))
    y = 44 + 15 * len(sub) + 14
    summary = []
    for cid in ids:
        els, y, differ, total = panel(by[cid], cr[cid], nc.get(cid), t0, y)
        body += els
        summary.append(f"{cid}: {differ} of {total} Nocturne readings differ from cgm-remote-monitor")
    foot = (f"measured, tools/lab/hub-active-state, run {run['date']}: cgm-remote-monitor {run['crm']} "
            f"({run['crm_version']}), Nocturne {run['nocturne']}. Synthetic records; T0 = {cases['t0']}.")
    for i, s in enumerate(wrap(foot, W - 2 * PAD, FS_SMALL)):
        body.append(text(PAD, y + i * 15, s, FS_SMALL, MUTED, italic=True))
    y += 15 * len(wrap(foot, W - 2 * PAD, FS_SMALL)) + 4
    desc = title + ". " + "; ".join(summary) + ". " + foot
    return svg(W, y, title, desc, body)


def build():
    cases, crm, noc, run = load()
    return {f"{name}.svg": figure(name, title, ids, cases, crm, noc, run)
            for name, (title, ids) in FIGURES.items()}
