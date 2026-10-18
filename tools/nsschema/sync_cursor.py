"""sync_cursor.py — the cursor a hub returns, and what a client receives (SPEC-SYNC-TRANSPORT).

A reference decision function for rules T5, T6, T9 and T10 of
docs/30-design/platform/spec/sync-transport.md: a collection-agnostic history
read with a merged cursor, pages that stop below a write still in flight and
never split equal values, and socket events that deliver records without
moving the cursor. It checks the cases under
specs/sync/conformance/sync-transport/; it is not a hub.

A case is a timeline of numbered steps. Each write takes its `srvModified` at
step `takenAt` and becomes visible at step `committedAt` (equal when the write
is not slow), or fails at `failedAt` and is never visible. History pages
return records with `cursor < srvModified <= low watermark`.
"""


def _visible(case, step, collection):
    """The records a reader sees at a step: for each id, its latest write that
    is visible by then (an update replaces the stored record)."""
    latest = {}
    for w in case["writes"]:
        if (w["collection"] == collection and w.get("committedAt") is not None
                and w["committedAt"] <= step):
            if w["id"] not in latest or w["srvModified"] > latest[w["id"]]["srvModified"]:
                latest[w["id"]] = w
    return sorted(latest.values(), key=lambda w: (w["srvModified"], w["id"]))


def _inflight(w, step):
    """A write is in flight from the step it takes its value until it becomes
    visible, or until it fails, when the value is released (T9)."""
    end = w.get("committedAt")
    if end is None:
        end = w.get("failedAt")
    return w["takenAt"] <= step and (end is None or step < end)


def low_watermark(case, step, collections):
    """T9: the largest cursor the hub may hand out at a step, over the
    collections the reader may read: below every value taken and not yet
    visible, and no further than the largest value taken."""
    mine = [w for w in case["writes"] if w["collection"] in collections]
    taken = [w["srvModified"] for w in mine if w["takenAt"] <= step and not (
        w.get("failedAt") is not None and w["failedAt"] <= step)]
    if not taken:
        return 0
    ceiling = max(taken)
    inflight = [w["srvModified"] for w in mine if _inflight(w, step)]
    if inflight:
        ceiling = min(ceiling, min(inflight) - 1)
    return ceiling


def history(case, step, cursor, limit):
    """T5, T6, T9: one page across every readable collection. A page returns
    no record above the low watermark, and never ends inside a group of
    records with the same srvModified."""
    readable = case.get("readable", case["collections"])
    watermark = low_watermark(case, step, readable)
    page, truncated_at = {}, []
    for collection in case["collections"]:
        if collection not in readable:
            continue
        newer = [w for w in _visible(case, step, collection)
                 if cursor < w["srvModified"] <= watermark]
        chosen = newer[:limit]
        while chosen and len(chosen) < len(newer) and \
                newer[len(chosen)]["srvModified"] == chosen[-1]["srvModified"]:
            chosen.append(newer[len(chosen)])
        if chosen:
            page[collection] = [w["id"] for w in chosen]
        if len(newer) > len(chosen):
            truncated_at.append(chosen[-1]["srvModified"])
    complete = not truncated_at
    next_cursor = min(truncated_at) if truncated_at else watermark
    return {"collections": page, "cursor": max(cursor, next_cursor), "complete": complete}


def run(case):
    """Replay a case's calls in order: history reads and socket events. A
    socket event delivers its record and never moves the cursor (T10); a
    history call with `cursor: last` reads from the cursor the last history
    read returned. Returns each call's result and what the client received,
    once per record version (id@srvModified)."""
    held = 0
    received = []
    results = []
    by_id = {}
    for w in case["writes"]:
        by_id.setdefault(w["id"], []).append(w)

    def take(write):
        version = "%s@%s" % (write["id"], write["srvModified"])
        if version not in received:
            received.append(version)

    for call in case["calls"]:
        if call["kind"] == "event":
            write = max((w for w in by_id[call["id"]] if w.get("committedAt") is not None),
                        key=lambda w: w["srvModified"])
            take(write)
            results.append({"kind": "event", "id": write["id"]})
            continue
        start = held if call.get("cursor", "last") == "last" else call["cursor"]
        page = history(case, call["at"], start, call["limit"])
        held = page["cursor"]
        for collection, ids in page["collections"].items():
            for record in _visible(case, call["at"], collection):
                if record["id"] in ids:
                    take(record)
        results.append(dict(page, kind="history"))
    return {"calls": results, "received": sorted(received)}
