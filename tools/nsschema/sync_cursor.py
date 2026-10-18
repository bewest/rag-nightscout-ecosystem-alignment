"""sync_cursor.py — the cursor a hub returns, and what a client receives (SPEC-SYNC-TRANSPORT).

A reference decision function for rules T6, T9 and T10 of
docs/30-design/platform/spec/sync-transport.md: a collection-agnostic history
read with a merged cursor, a low watermark that never passes a write still in
flight, and socket events that carry that watermark so a client that
reconnects reads history from it without a gap. It checks the cases under
specs/sync/conformance/sync-transport/; it is not a hub.

A case is a timeline of numbered steps. Each write takes its `srvModified` at
step `takenAt` and becomes visible at step `committedAt` (equal when the write
is not slow). History pages return records with `srvModified > cursor`.
"""


def _visible(case, step, collection):
    return sorted((w for w in case["writes"]
                   if w["collection"] == collection and w["committedAt"] <= step),
                  key=lambda w: w["srvModified"])


def low_watermark(case, step):
    """T9: the largest cursor the hub may hand out at a step: below every write
    that has taken its srvModified and is not yet visible, and no further than
    the largest value taken so far."""
    taken = [w["srvModified"] for w in case["writes"] if w["takenAt"] <= step]
    if not taken:
        return 0
    inflight = [w["srvModified"] for w in case["writes"]
                if w["takenAt"] <= step < w["committedAt"]]
    ceiling = max(taken)
    if inflight:
        ceiling = min(ceiling, min(inflight) - 1)
    return ceiling


def history(case, step, cursor, limit):
    """T5, T6, T9: one page across every readable collection."""
    readable = case.get("readable", case["collections"])
    page, truncated_at = {}, []
    for collection in case["collections"]:
        if collection not in readable:
            continue
        newer = [w for w in _visible(case, step, collection) if w["srvModified"] > cursor]
        chosen = newer[:limit]
        if chosen:
            page[collection] = [w["id"] for w in chosen]
        if len(newer) > limit:
            truncated_at.append(chosen[-1]["srvModified"])
    watermark = low_watermark(case, step)
    complete = not truncated_at
    next_cursor = min(truncated_at) if truncated_at else watermark
    next_cursor = max(cursor, min(next_cursor, watermark))
    return {"collections": page, "cursor": next_cursor, "complete": complete}


def event_cursor(case, write):
    """T10: a socket event carries the low watermark at the step the record
    became visible, not the record's own srvModified."""
    return low_watermark(case, write["committedAt"])


def run(case):
    """Replay a case's calls in order: history reads and socket events. A
    history call with `cursor: last` reads from the cursor the client last
    held. Returns each call's result and the ids the client received."""
    held = 0
    received = []
    results = []
    by_id = {w["id"]: w for w in case["writes"]}
    for call in case["calls"]:
        if call["kind"] == "event":
            write = by_id[call["id"]]
            held = event_cursor(case, write)
            received.append(write["id"])
            results.append({"kind": "event", "id": write["id"], "cursor": held})
            continue
        start = held if call.get("cursor", "last") == "last" else call["cursor"]
        page = history(case, call["at"], start, call["limit"])
        held = page["cursor"]
        for ids in page["collections"].values():
            received.extend(ids)
        results.append(dict(page, kind="history"))
    return {"calls": results, "received": sorted(set(received))}
