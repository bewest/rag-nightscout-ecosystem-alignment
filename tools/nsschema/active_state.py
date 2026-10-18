"""active_state.py — what a hub reports as active at a time (SPEC-ACTIVE-STATE).

A reference decision function for the rules A1-A12 in
docs/30-design/platform/spec/state-intent.md §6. It reads a case's
declarations (stateSpans entries, as a registration states them) and the
records a hub received, in the order it received them, and answers which
instances exist, when each started and ended and why, and which are active at
a time. It checks that the cases under specs/sync/conformance/active-state/
are self-consistent; it is not a hub.

It never combines intents: what several active instances mean together is
the controller's composition (state and intent S1).
"""

import hashlib
from datetime import datetime, timedelta, timezone

from .negotiate import canonical_json

UNIT_SECONDS = {"seconds": 1, "minutes": 60, "milliseconds": 0.001}


def _get(doc, path):
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(when):
    return None if when is None else when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _matches(carrier, record):
    """A record belongs to a carrier by collection, eventType and discriminator."""
    if not carrier or record.get("collection") != carrier.get("collection"):
        return False
    doc = record.get("doc") or {}
    if carrier.get("eventType") and doc.get("eventType") != carrier["eventType"]:
        return False
    disc = carrier.get("discriminator")
    if disc:
        value = _get(doc, disc["path"])
        test = disc["test"]
        if test == "exists" and value is None:
            return False
        if test == "is-object" and not isinstance(value, dict):
            return False
        if test == "equals" and value != disc.get("value"):
            return False
    return True


def _start(carrier, doc):
    """A3: the record's own time, from the declared timeField, else created_at."""
    value = _get(doc, carrier.get("timeField") or "created_at")
    return None if value is None else _time(value)


def _end(carrier, doc, start):
    """A4, A11: the end from the declared duration field in its declared unit;
    None for an open-ended record."""
    indefinite = carrier.get("indefinite")
    if indefinite and _get(doc, indefinite["field"]) == indefinite["value"]:
        return None
    field = carrier.get("durationField")
    raw = None if field is None else _get(doc, field)
    if raw is None:
        return None
    unit = carrier.get("durationUnit")
    if unit not in UNIT_SECONDS:
        raise ValueError("a duration without a declared unit is not read (A11): %s" % field)
    return start + timedelta(seconds=float(raw) * UNIT_SECONDS[unit])


def _units(carrier):
    """A11: the units the carrier declares for its paths, never assumed."""
    out = {}
    for item in carrier.get("paths") or []:
        if isinstance(item, dict) and item.get("unit"):
            out[item["path"]] = item["unit"]
    return out


def _wire_instances(product, span, records):
    """A2, A5, A6: one instance per identity, amended in received order."""
    wire = span["wire"]
    identity = wire.get("identity") or ["_id"]
    encoding = wire.get("endedEncoding")
    history = {}      # key -> list of (op, doc, receivedAt)
    markers = []      # zero-duration end markers (A5)
    order = []
    for record in records:
        if record.get("product") != product or not _matches(wire, record):
            continue
        doc = record.get("doc") or {}
        if (encoding == "zero-duration-record" and record.get("op", "write") == "write"
                and _get(doc, wire.get("durationField") or "duration") == 0):
            markers.append(_start(wire, doc))
            continue
        key = "|".join("%s=%s" % (f, _get(doc, f)) for f in identity)
        if key not in history:
            order.append(key)
        history.setdefault(key, []).append((record.get("op", "write"), doc,
                                            record.get("receivedAt")))
    instances = []
    for key in order:
        writes = [h for h in history[key] if h[0] == "write"]
        last = history[key][-1]
        if last[0] == "delete":
            first = writes[0][1] if writes else {}
            start = _start(wire, first)
            received = last[2] and _time(last[2])
            if start is not None and received is not None and received < start:
                instances.append({"product": product, "kind": span["kind"], "layer": "requested",
                                  "key": key, "start": start, "end": start,
                                  "endReason": "deletedBeforeStart", "content": first})
            continue  # a record withdrawn after its start is not reported
        doc = writes[-1][1]
        start = _start(wire, doc)
        end = _end(wire, doc, start)
        reason = "expired" if end is not None else None
        earlier = [_end(wire, w[1], _start(wire, w[1])) for w in writes[:-1]]
        if end is not None and any(e is None or e > end for e in earlier):
            reason = "cancelled"   # an amendment ended it early (A5)
        instances.append({"product": product, "kind": span["kind"], "layer": "requested",
                          "key": key, "start": start, "end": end, "endReason": reason,
                          "content": doc, "units": _units(wire), "received": len(instances)})
    for at in markers:
        for inst in instances:
            if inst["start"] <= at and (inst["end"] is None or at < inst["end"]):
                inst["end"], inst["endReason"] = at, "cancelled"
    return instances


def _supersede(span, instances):
    """A7, A8: a later-starting instance of the same kind and product ends an
    earlier one (by start, never by arrival); with overlay, a timed instance
    does not end an open-ended one."""
    if not span.get("supersedes"):
        return
    ordered = sorted(instances, key=lambda i: (i["start"], i.get("received", 0)))
    for i, earlier in enumerate(ordered):
        for later in ordered[i + 1:]:
            if span.get("overlay") and earlier["end"] is None and later["end"] is not None:
                continue
            if earlier["end"] is None or later["start"] < earlier["end"]:
                if later["start"] >= earlier["start"]:
                    earlier["end"], earlier["endReason"] = later["start"], "superseded"
                    break


def _applied(product, span, records):
    """A10: each applied record is in effect from its time until its own end or
    the next applied record of the same carrier and product; a record saying
    the intent is not active ends it."""
    carrier = span.get("applied")
    if not carrier:
        return []
    samples = []
    for record in records:
        if record.get("product") == product and _matches(carrier, record):
            doc = record.get("doc") or {}
            samples.append((_start(carrier, doc), doc))
    samples.sort(key=lambda s: s[0])
    active_path = carrier.get("activeField")
    out = []
    for n, (at, doc) in enumerate(samples):
        if active_path and _get(doc, active_path) is False:
            continue
        end = _end(carrier, doc, at)
        nxt = samples[n + 1][0] if n + 1 < len(samples) else None
        if nxt is not None and (end is None or nxt < end):
            end = nxt
        out.append({"product": product, "kind": span["kind"], "layer": "applied",
                    "key": "%s@%s" % (span["kind"], _iso(at)), "start": at, "end": end,
                    "endReason": None, "content": doc, "units": _units(carrier)})
    return out


def instances(case):
    """Every instance the records describe, per product and kind (A1)."""
    out = []
    records = case.get("records") or []
    for decl in case["declarations"]:
        product = decl["product"]
        for span in decl["stateSpans"]:
            found = []
            if span.get("wire"):
                found = _wire_instances(product, span, records)
                _supersede(span, found)
            out.extend(found)
            out.extend(_applied(product, span, records))
    return out


def active_at(case, at):
    """The instances active at a time, each with its layer; overlapping ones
    of an exclusive kind with neither supersedes nor overlay are marked
    `overlap` (A9); an open-ended instance under a timed overlay is not
    active while the timed one is (A8)."""
    when = _time(at)
    spans = {(d["product"], s["kind"]): s for d in case["declarations"] for s in d["stateSpans"]}
    live = [i for i in instances(case)
            if i["start"] <= when and (i["end"] is None or when < i["end"])
            and i.get("endReason") != "deletedBeforeStart"]
    result = []
    for inst in live:
        span = spans[(inst["product"], inst["kind"])]
        peers = [p for p in live if p is not inst and p["product"] == inst["product"]
                 and p["kind"] == inst["kind"] and p["layer"] == inst["layer"]]
        if span.get("overlay") and inst["end"] is None and any(p["end"] is not None for p in peers):
            continue
        row = {"product": inst["product"], "kind": inst["kind"], "layer": inst["layer"],
               "key": inst["key"], "start": _iso(inst["start"]), "end": _iso(inst["end"])}
        if (peers and span.get("exclusiveWithinSlot") and not span.get("supersedes")
                and not span.get("overlay")):
            row["overlap"] = True
        if inst.get("units"):
            row["units"] = inst["units"]
        result.append(row)
    return sorted(result, key=lambda r: (r["product"], r["kind"], r["layer"], r["start"], r["key"]))


def state_version(case, product, at):
    """A12: sha256 of the canonical JSON of a product's active set at a time,
    with each instance's content, so a start, an end or an amendment changes it."""
    contents = {(i["kind"], i["layer"], i["key"]): i["content"] for i in instances(case)
                if i["product"] == product}
    rows = [dict(r, content=contents.get((r["kind"], r["layer"], r["key"])))
            for r in active_at(case, at) if r["product"] == product]
    return "sha256:" + hashlib.sha256(canonical_json(rows)).hexdigest()


def summary(case):
    """Instances as the cases state them."""
    return sorted(({"product": i["product"], "kind": i["kind"], "layer": i["layer"],
                    "key": i["key"], "start": _iso(i["start"]), "end": _iso(i["end"]),
                    "endReason": i["endReason"]} for i in instances(case)),
                  key=lambda r: (r["product"], r["kind"], r["layer"], r["start"], r["key"]))
