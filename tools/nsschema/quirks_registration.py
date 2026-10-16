"""quirks_registration.py — reference for version-scoped quirks and the two-id rule (D20).

Execution plan §2.6.3 (D20, maintainer 2026-10-16); queue item
SPEC-REG-QUIRKS; contract in the hub-sync design §3.7. Cases:
`specs/sync/conformance/quirks/`, in the instance case format
(`registration-submit.schema.json#/$defs/instanceCase`), run by
`instances.run_case`, which calls this module for:

- rule 2: the shared slot list, a definition's `sameAs`, and the catalogue
  mappings for versions released before registration (`wellKnown.mappings`);
- rule 3: `quirksApplied`, the record of each mapping applied;
- rules 5 and 6: the legacy id form, the two ids every write reply returns,
  and re-sends matched on `identifier` first;
- rule 7: today's `_id` handling (`UUID_HANDLING`) as the registry entries
  QUIRK-TREATMENTS-006 and QUIRK-ENTRIES-004, behaviour unchanged;
- rule 8: the stored ObjectId of a projected record.

The registry half of rules 1 and 4 (`affects`, version ranges, the
lifecycle) is `quirks.py`. **This is a reference, not a hub**: it stores
nothing and serves nothing.
"""

import copy
import re

from . import negotiate, quirks

OBJECT_ID = re.compile(r"^[0-9a-fA-F]{24}$")
LEGACY_ID_FORMS = ("objectId", "opaque")

# Rule 7: the registry entry that describes today's `_id` handling, per
# collection. cgm-remote-monitor moves a non-ObjectId string `_id` to
# `identifier` on these two collections only (treatments.js:394-411,
# entries.js:267-284 at official a8888f0d); the v1 routes refuse one on the
# others (write contract §2.5), which these cases do not model.
ID_QUIRKS = {"treatments": "QUIRK-TREATMENTS-006", "entries": "QUIRK-ENTRIES-004"}


def legacy_id_form(caps):
    """Rule 6: the hub's declared legacy id form. A capability document
    without `legacyIdForm` is read as `objectId`, the legacy API's rule (a
    choice of this item, §3.7)."""
    return (caps or {}).get("legacyIdForm") or "objectId"


def is_object_id(value):
    return isinstance(value, str) and bool(OBJECT_ID.match(value))


class Assigner:
    """The ObjectIds a case says the hub assigns, in order (`assignedIds`).
    A real hub mints them; the first four bytes are its receipt time."""

    def __init__(self, ids):
        self._ids = list(ids or [])

    def next(self):
        if not self._ids:
            raise ValueError("the case assigns no further ObjectId (assignedIds)")
        return self._ids.pop(0)


# ── rule 2: shared slots ──────────────────────────────────────────────

def slot_channel(caps, node, fallback):
    """The channel a stateSpans entry's slot derives: the shared slot its
    `sameAs` names, when the hub interprets `sameAs` and lists that slot;
    the element channel `fallback` when it does not list it (the element is
    refused `unknown-shared-slot` and goes as its carrier, so it never joins
    a channel by its name instead); else the slot's own name."""
    slot = node.get("slot")
    same = node.get("sameAs")
    if same is None or not negotiate.interpreted(caps, "spec.stateSpans.*.sameAs"):
        return slot
    return same if same in negotiate.shared_slots(caps) else fallback


def catalogue_mapping(caps, well_known, writer, element):
    """Rule 2 for versions released before registration: the slot mapping
    the catalogue applies to an older controller's write described by its
    well-known registration. Returns (slotMapping, quirksApplied). A mapping
    applies only when the writer's version is known and inside the
    mapping's range, and its `sameAs` is a listed shared slot."""
    kinds = ((caps or {}).get("wellKnown") or {}).get("kinds") or []
    span = None
    for entry in kinds:
        if (entry.get("vendor"), entry.get("product")) != (writer["vendor"], writer["product"]):
            continue
        reg = (well_known or {}).get(entry.get("href")) or {}
        for s in (reg.get("spec") or {}).get("stateSpans") or []:
            if f"stateSpans/{s.get('kind') or s.get('category')}" == element:
                span = s
                break
        if span:
            break
    if span is None or not isinstance(span.get("slot"), str):
        return None, []
    slot = span["slot"]
    version = writer.get("version")
    for m in ((caps.get("wellKnown") or {}).get("mappings") or []):
        if (m["vendor"], m["product"], m["slot"]) != (writer["vendor"], writer["product"], slot):
            continue
        if version is None or not quirks.in_range(version, m["versions"]):
            continue
        if m["sameAs"] not in negotiate.shared_slots(caps):
            continue
        return ({"slot": slot, "channel": m["sameAs"], "by": "catalogue", "quirk": m["quirk"]},
                [{"quirk": m["quirk"], "member": "slot", "action": "same-as",
                  "sameAs": m["sameAs"]}])
    return {"slot": slot, "channel": slot, "by": "name"}, []


# ── rules 5 to 7: the two ids ─────────────────────────────────────────

def normalise_sent_id(caps, collection, sent):
    """Rule 1 of the write contract §2.3 on an `objectId` hub, and rule 7:
    returns (_id or None, identifier or None, quirksApplied). `{"$oid": …}`
    and a 24-hex string, either case, are the ObjectId (lower-case hex); an
    empty `_id` is dropped; any other string on treatments or entries moves
    to `identifier` when the client sent none, else it is dropped, and the
    hub assigns `_id` (UUID_HANDLING's default, unchanged). On an `opaque`
    hub a string `_id` is kept as sent."""
    _id = sent.get("_id")
    identifier = sent.get("identifier")
    applied = []
    if isinstance(_id, dict) and isinstance(_id.get("$oid"), str):
        _id = _id["$oid"]
    if _id == "" or _id is None:
        return None, identifier, applied
    if legacy_id_form(caps) == "opaque":
        return _id, identifier, applied
    if is_object_id(_id):
        return _id.lower(), identifier, applied
    if isinstance(_id, str) and collection in ID_QUIRKS:
        if not identifier:
            identifier = _id
            applied.append({"quirk": ID_QUIRKS[collection], "member": "_id",
                            "action": "moved-to-identifier"})
        else:
            applied.append({"quirk": ID_QUIRKS[collection], "member": "_id",
                            "action": "dropped"})
        return None, identifier, applied
    raise ValueError(f"a non-ObjectId _id on {collection} is outside these cases")


def resolve(documents, collection, identifier, _id):
    """Rule 5: a re-send matches a stored document on `identifier` first,
    then on `_id` (the write contract's `keys` order). Returns (document,
    key) or (None, None)."""
    docs = [d for d in documents or [] if d["collection"] == collection]
    if identifier:
        hit = next((d for d in docs if d.get("identifier") == identifier), None)
        if hit:
            return hit, "identifier"
    if _id is not None:
        hit = next((d for d in docs if str(d["_id"]).lower() == str(_id).lower()), None)
        if hit:
            return hit, "_id"
    return None, None


def carrier_write(caps, hub_state, w, assigner):
    """A v1/v3 document write with the id members the client sent
    (`write.sent`): the two ids the reply returns, the key a re-send
    matched by, the mappings applied, and the stored documents after."""
    collection = w["collection"]
    _id, identifier, applied = normalise_sent_id(caps, collection, w.get("sent") or {})
    stored, key = resolve((hub_state or {}).get("documents"), collection, identifier, _id)
    after = hub_state
    if stored is not None:
        ids = {"identifier": stored.get("identifier"), "_id": stored["_id"]}
    else:
        if _id is None:
            _id = assigner.next()
        ids = {"identifier": identifier or None, "_id": _id}
        doc = {"collection": collection, **ids}
        if applied:
            doc["quirksApplied"] = applied
        after = copy.deepcopy(hub_state or {})
        after.setdefault("documents", []).append(doc)
    members = {"ids": ids, "matchedBy": key}
    if applied:
        members["quirksApplied"] = applied
    return members, after


def typed_write(caps, hub_state, w, stored_instance, assigner):
    """Rules 5 and 8 for a typed write that carries the controller's record
    id (`write.recordId`): `identifier` is that id; `_id` is the storage key
    the hub assigns now and stores with the record (an ObjectId on an
    `objectId` hub, the typed id on an `opaque` one). A re-send with the
    same identifier for the same product matches the stored record and
    answers with its ids, so the controller needs no cache of server ids."""
    identity = stored_instance["identity"]
    rid = w["recordId"]
    for record in (hub_state or {}).get("records") or []:
        if record.get("as") == "typed" and record["identity"] == identity and record["id"] == rid:
            return {"ids": {"identifier": rid, "_id": record.get("_id", rid)},
                    "matchedBy": "identifier"}, hub_state
    _id = assigner.next() if legacy_id_form(caps) == "objectId" else rid
    after = copy.deepcopy(hub_state or {})
    after.setdefault("records", []).append({
        "id": rid, "_id": _id, "as": "typed", "identity": copy.deepcopy(identity),
        "instanceId": stored_instance["instanceId"],
        "definitionId": stored_instance["instance"]["definitionId"],
        "element": w["element"]})
    return {"ids": {"identifier": rid, "_id": _id}, "matchedBy": None}, after


def projected_ids(caps, record):
    """Rule 8: (identifier, _id) of the projected document for one typed
    record. On an `objectId` hub `_id` is the ObjectId the hub stored with
    the record at the typed write, so it is the same on every read; a
    record without one is a reference error. An `opaque` hub uses the
    stored key, else the typed id, for both."""
    if legacy_id_form(caps) == "objectId":
        if not is_object_id(record.get("_id")):
            raise ValueError(f"record {record['id']}: an objectId hub stores the ObjectId it "
                             "assigned at the typed write")
        return record["id"], record["_id"]
    return record["id"], record.get("_id", record["id"])
