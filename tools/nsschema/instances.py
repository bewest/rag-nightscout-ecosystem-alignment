"""instances.py — reference decision function for definitions and instances (D19).

Execution plan §2.6.2 (D19, maintainer 2026-10-14); queue item
SPEC-REG-INSTANCE; contract in the hub-sync design §3.6; schemas
`specs/sync/controller-instance.schema.json` (the instance document),
`specs/sync/registration-submit.schema.json` (requests, responses, stored
state and the conformance case) and `specs/sync/hub-capabilities.schema.json`
(`instances`). Conformance cases: `specs/sync/conformance/instances/`.

**This is a reference, not a hub**, like `negotiate.py`, which it extends: the
product resource `<submit.href>/<vendor>/<product>` keeps the negotiation
contract (§3.5) unchanged, and this module adds the two resources beside it —
content-addressed definitions at `<product>/definitions/<definitionId>` and
leased instances at `<product>/instances/<instanceId>` — plus the owner's
role transfer and version pins, command routing, read selection, the
projected carrier view for older readers, attribution of writes and
retention. Given a hub's capability document, its stored state and a
request, it computes what the contract requires. It stores nothing, serves
nothing and is never run by a hub.

The hub never decides dosing. Role exclusivity decides only which instance is
the typed source of record for a channel and where a command for that
channel is routed; it never stops, directs or composes dosing.
"""

import copy
import datetime
import hashlib
import re

import jsonschema

from . import corpus, negotiate, quirks_registration

INSTANCE_SCHEMA = "specs/sync/controller-instance.schema.json"
CASES_DIR = "specs/sync/conformance/instances"

API = negotiate.GRAMMAR_API

# Rule 4: an instance id is controller-supplied, opaque and random — the
# UUID version 4 form, 122 random bits — and never derived from a device
# name, model or serial (which a hub cannot check, so the contract says it).
INSTANCE_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

# Rule 7: label keys are `<namespace>/<name>`, the namespace in the reverse-DNS
# form extension namespaces use. `dev.nightscout/` is reserved for the keys
# this specification defines (corrected 2026-10-15 from `nightscout.dev/`).
LABEL_NAMESPACE = r"[a-z][a-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+"
LABEL_KEY = re.compile(rf"^{LABEL_NAMESPACE}/[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
RESERVED_LABEL_PREFIX = "dev.nightscout/"
WELL_KNOWN_LABELS = {
    "dev.nightscout/purpose": ("therapy", "development", "lab", "research"),
    "dev.nightscout/build": ("release", "dev"),
    "dev.nightscout/migration-group": None,  # an opaque string
}

# Rule 5: provenance is closed, for safety; an unknown value is a refused role.
PROVENANCE = ("device", "simulated")
SHARED_ROLES = ("source", "command-sink")

# What the hub records about the free-text devicestatus.device an instance
# writes (reconciliation §3.3): an observed alias, never the identity.
ALIAS_SENSITIVITY = {"level": "identifying", "category": "device"}

# The projected carrier view's marker (rule 8).
PROJECTION_MARKER = "projectedFrom"


# ── small helpers ─────────────────────────────────────────────────────

def _time(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)


def _text(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ident(identity):
    return (identity["vendor"], identity["product"])


def _identity(pair):
    return {"vendor": pair[0], "product": pair[1]}


_reason = negotiate._reason


def _response(status, outcome, **members):
    response = {"apiVersion": API, "kind": "InstanceResponse", "status": status,
                "outcome": outcome}
    response.update({k: v for k, v in members.items() if v is not None})
    return response


def _refused(status, code, path=None, detail=None, **members):
    return _response(status, "rejected", reasons=[_reason(code, path, detail)], **members)


def label_value(key, value):
    """Rule 7. How a reader reads a well-known label: a value the
    specification lists, or `other` for any other value of a key whose
    values are listed. Other keys' values are read as written."""
    allowed = WELL_KNOWN_LABELS.get(key)
    if allowed is not None and value not in allowed:
        return "other"
    return value


# ── state ─────────────────────────────────────────────────────────────

def _instances(hub_state):
    return list((hub_state or {}).get("instances") or [])


def find_instance(hub_state, instance_id):
    for stored in _instances(hub_state):
        if stored["instanceId"] == instance_id:
            return stored
    return None


def live(stored, now):
    """Rule 4: an instance is live while its lease runs; it lapses when it
    stops renewing, with no housekeeping."""
    return _time(stored["leaseExpiresAt"]) > _time(now)


def product_state(hub_state, identity):
    stored = negotiate._find(hub_state, identity)
    if stored is None or stored.get("registration") is None:
        return None
    return stored["state"]


def granted(stored):
    return [{k: r[k] for k in ("channel", "role", "provenance")}
            for r in stored.get("roles") or [] if r["result"] == "granted"]


def instance_etag(body, bound_to, roles_granted):
    """The instance's entity tag: `sha256:` over the RFC 8785 canonical JSON
    of {instance, boundTo, granted}. A renewal that changes nothing keeps it
    (the lease is outside it, so a renewal retried after a lost response
    still matches); a change of content, binding or granted roles — a role
    the instance gains on renewal, or loses or gains by the owner's transfer
    — changes it, so racing owner actions meet 412 and the instance learns of
    the change on its next renewal."""
    key = sorted(roles_granted, key=negotiate.canonical_json)
    digest = hashlib.sha256(negotiate.canonical_json(
        {"instance": body, "boundTo": bound_to, "granted": key})).hexdigest()
    return f"sha256:{digest}"


def _stored_instance(identity, instance_id, body, bound_to, credential_kind, roles, lease,
                     aliases=None):
    out = {"identity": _identity(identity), "instanceId": instance_id,
           "etag": instance_etag(body, bound_to, [
               {k: r[k] for k in ("channel", "role", "provenance")}
               for r in roles if r["result"] == "granted"]),
           "boundTo": bound_to, "credentialKind": credential_kind,
           "leaseExpiresAt": lease, "roles": roles, "instance": body}
    if aliases:
        out["observedAliases"] = aliases
    return out


def _restate(stored, **changes):
    members = {"body": stored["instance"], "bound_to": stored["boundTo"],
               "credential_kind": stored["credentialKind"], "roles": stored["roles"],
               "lease": stored["leaseExpiresAt"], "aliases": stored.get("observedAliases")}
    members.update(changes)
    return _stored_instance(_ident(stored["identity"]), stored["instanceId"], **members)


def _replace_instance(hub_state, stored_after, instance_id):
    state = copy.deepcopy(hub_state or {})
    rest = [i for i in state.get("instances") or [] if i["instanceId"] != instance_id]
    if stored_after is not None:
        rest.append(stored_after)
    state["instances"] = sorted(rest, key=lambda i: i["instanceId"])
    return state


def _summary(stored, now):
    return {"vendor": stored["identity"]["vendor"], "product": stored["identity"]["product"],
            "instanceId": stored["instanceId"], "definitionId": stored["instance"]["definitionId"],
            "etag": stored["etag"], "leaseExpiresAt": stored["leaseExpiresAt"],
            "live": live(stored, now), "boundTo": stored["boundTo"],
            "credentialKind": stored["credentialKind"]}


# ── channels ──────────────────────────────────────────────────────────

def channels(caps, well_known, definition):
    """The channels a definition's roles may name, each with the elements it
    covers and whether one of them accepts hub commands. A stateSpans kind
    that declares a slot (a slot name with no `/`) is the channel named by
    that slot, shared across products on the tenant, so two controllers that
    name the same slot contend for its roles; every other element is the
    channel `<vendor>/<product>/<element id>`. A kind that references a
    well-known kind takes the catalogue kind's slot and acceptsFromHub."""
    meta = definition["metadata"]
    out = {}
    for eid, _path, _defining, node, kind in negotiate.elements(definition):
        source = (negotiate._resolved(caps, well_known, kind, node) or {}) \
            if kind == "stateSpans" else node
        slot = source.get("slot") if kind == "stateSpans" else None
        element_channel = f"{meta['vendor']}/{meta['product']}/{eid}"
        if isinstance(slot, str) and slot and "/" not in slot:
            # D20 rule 2: a declared `sameAs` names the shared slot instead.
            name = quirks_registration.slot_channel(caps, source, element_channel)
        else:
            name = element_channel
        entry = out.setdefault(name, {"elements": [], "commands": False})
        entry["elements"].append(eid)
        accepts = (source.get("acceptsFromHub") or {}).get("channels") or []
        if kind == "stateSpans" and "command" in accepts:
            entry["commands"] = True
    return out


def channel_of(caps, well_known, definition, element):
    for name, entry in channels(caps, well_known, definition).items():
        if element in entry["elements"]:
            return name
    return None


def holder(hub_state, channel, role, now, exclude=None):
    """Rule 6: the one live `device`-provenance instance of an active product
    holding (channel, role) on the tenant, or None. `simulated` roles never
    hold against `device` ones or each other."""
    found = [s["instanceId"] for s in _instances(hub_state)
             if s["instanceId"] != exclude and live(s, now)
             and product_state(hub_state, _ident(s["identity"])) == "active"
             and any(g["channel"] == channel and g["role"] == role and g["provenance"] == "device"
                     for g in granted(s))]
    if len(found) > 1:
        raise ValueError(f"two holders of {channel} {role}: {found}")
    return found[0] if found else None


def _role_key(role):
    return negotiate.canonical_json(role["role"])


def _supported_roles(caps):
    return [negotiate.canonical_json(r) for r in caps["instances"].get("roles") or []]


def evaluate_roles(caps, hub_state, well_known, instance_id, body, definition, now):
    """Per-role results for an instance's claimed roles (rules 5 and 6)."""
    chans = channels(caps, well_known, definition)
    supported = _supported_roles(caps)
    results = []
    for i, claim in enumerate(body.get("roles") or []):
        path = f"roles.{i}"
        reasons = []
        if claim["provenance"] not in PROVENANCE:
            reasons.append(_reason("unknown-provenance", f"{path}.provenance",
                                   "provenance is device or simulated"))
        if _role_key(claim) not in supported:
            reasons.append(_reason("unsupported-role", f"{path}.role",
                                   "the hub does not list this role"))
        if claim["channel"] not in chans:
            reasons.append(_reason("unknown-channel", f"{path}.channel",
                                   "the instance's definition derives no such channel"))
        elif claim["role"] == "command-sink" and not chans[claim["channel"]]["commands"]:
            reasons.append(_reason("not-a-command-channel", f"{path}.channel",
                                   "no kind on this channel accepts hub commands"))
        if not reasons and claim["provenance"] == "device" and \
                holder(hub_state, claim["channel"], claim["role"], now, exclude=instance_id):
            reasons.append(_reason("role-held", path,
                                   "another live device instance holds this role"))
        result = {"channel": claim["channel"], "role": claim["role"],
                  "provenance": claim["provenance"]}
        if reasons:
            result.update(result="refused", reasons=reasons)
        else:
            result["result"] = "granted"
        results.append(result)
    return results


# ── content checks ────────────────────────────────────────────────────

def label_problems(caps, labels):
    limits = (caps.get("instances") or {}).get("labels") or {}
    problems = []
    if limits.get("maxLabels") is not None and len(labels) > limits["maxLabels"]:
        problems.append(("labels", f"{len(labels)} labels exceed maxLabels"))
    for key, value in sorted(labels.items()):
        if not LABEL_KEY.match(key):
            problems.append((f"labels.{key}", "a key is <reverse-DNS namespace>/<name>"))
        elif key.startswith(RESERVED_LABEL_PREFIX) and key not in WELL_KNOWN_LABELS:
            problems.append((f"labels.{key}", "dev.nightscout/ is reserved for well-known keys"))
        if not isinstance(value, str):
            problems.append((f"labels.{key}", "a label value is a string"))
        elif limits.get("maxValueLength") is not None and len(value) > limits["maxValueLength"]:
            problems.append((f"labels.{key}", "value exceeds maxValueLength"))
        if limits.get("maxKeyLength") is not None and len(key) > limits["maxKeyLength"]:
            problems.append((f"labels.{key}", "key exceeds maxKeyLength"))
    return problems


def _schema_errors(body, schema):
    return sorted(jsonschema.Draft202012Validator(schema).iter_errors(body),
                  key=lambda e: [str(p) for p in e.absolute_path])


def _load_instance_schema():
    return negotiate._load(INSTANCE_SCHEMA)


# ── definitions: PUT <product>/definitions/<definitionId> ─────────────

def put_definition(caps, hub_state, submitter, request, body, grammar, well_known):
    """Add a definition to a product, immutably (rules 1 and 2). Authorised by
    the product's binding; it never changes the product resource or its
    etag, so a product's instances never contend on it."""
    identity = _ident(request["identity"])
    stored = negotiate._find(hub_state, identity)
    reject, failed = negotiate._rejecter(stored)
    if request.get("actor", "controller") == "owner":
        return reject(403, "not-authorised", None, "the owner never edits a definition")[0], hub_state
    if not negotiate.permitted(submitter.get("permissions"), negotiate.PERMISSION["submit"]):
        return reject(403, "not-authorised", None, "needs api:registrations:create")[0], hub_state
    if not negotiate._registered(stored):
        return negotiate._response(404, "not-found", reasons=[_reason("not-found")]), hub_state
    # A definition PUT never binds a released product: binding changes the
    # product's etag, which a definition never does.
    if stored.get("boundTo") is None or negotiate.canonical_json(stored["boundTo"]) != \
            negotiate.canonical_json(negotiate.binding_of(submitter)):
        return reject(403, "not-registration-owner", None,
                      "definitions are added by the credential the product is bound to")[0], hub_state
    pre = request.get("preconditions") or {}
    if "ifNoneMatch" not in pre:
        return failed(428, "precondition-required",
                      "a definition is created with If-None-Match: *")[0], hub_state
    if stored["state"] == "blocked":
        return reject(403, "blocked-by-owner")[0], hub_state
    if stored["state"] == "retired":
        return reject(409, "product-retired", None, "reactivate the product first")[0], hub_state
    did = negotiate.definition_id(body)
    if did != request["definitionId"]:
        return reject(422, "definition-id-mismatch", None,
                      "the body's canonical hash is not the path's id")[0], hub_state
    refusal = negotiate.content_refusal(caps, body, identity, grammar, reject)
    if refusal is not None:
        return refusal[0], hub_state
    existing = negotiate.product_definitions(hub_state, identity)
    top, results = negotiate.evaluate(caps, hub_state, submitter, body, grammar, None, well_known)
    outcome = "partial" if any(r["result"] == "rejected" for r in results) else "accepted"
    after = copy.deepcopy(hub_state)
    if did not in existing:
        after.setdefault("definitions", []).append(
            {"identity": _identity(identity), "definitionId": did, "definition": body})
    response = negotiate._response(201 if did not in existing else 200, outcome,
                                   noop=did in existing, definitionId=did,
                                   registration=negotiate._summary(stored, identity),
                                   ignored=top, elements=results)
    return response, after


# ── instances: PUT / DELETE <product>/instances/<instanceId> ──────────

def put_instance(caps, hub_state, submitter, request, body, now, well_known):
    identity = _ident(request["identity"])
    instance_id = request["instanceId"]
    product = negotiate._find(hub_state, identity)
    stored = find_instance(hub_state, instance_id)
    pre = request.get("preconditions") or {}

    def current():
        return {"etag": stored["etag"], "leaseExpiresAt": stored["leaseExpiresAt"]} \
            if stored else None

    # 1. Authorisation.
    if request.get("actor", "controller") != "controller":
        return _refused(403, "not-authorised", None, "the owner never writes an instance"), hub_state
    if not negotiate.permitted(submitter.get("permissions"), negotiate.PERMISSION["submit"]):
        return _refused(403, "not-authorised", None, "needs api:registrations:create"), hub_state
    if not negotiate._registered(product):
        return _response(404, "not-found", reasons=[_reason("not-found")]), hub_state
    if stored is not None and (_ident(stored["identity"]) != identity or
                               negotiate.canonical_json(stored["boundTo"]) !=
                               negotiate.canonical_json(negotiate.binding_of(submitter))):
        return _refused(403, "not-registration-owner", None,
                        "the instance is bound to another credential"), hub_state
    # 2. Preconditions, then the product's state.
    if not pre:
        return _response(428, "precondition-failed",
                         reasons=[_reason("precondition-required")]), hub_state
    if "ifNoneMatch" in pre and stored is not None and stored["instance"] != body:
        return _response(412, "precondition-failed", reasons=[_reason("registration-exists")],
                         current=current()), hub_state
    if "ifMatch" in pre:
        if stored is None:
            return _response(412, "precondition-failed", reasons=[_reason("not-found")]), hub_state
        if pre["ifMatch"] != stored["etag"]:
            return _response(412, "precondition-failed", reasons=[_reason("stale-etag")],
                             current=current()), hub_state
    if product["state"] == "blocked":
        return _refused(403, "blocked-by-owner"), hub_state
    if product["state"] == "retired":
        return _refused(409, "product-retired"), hub_state
    # 3. The instance as a whole.
    if not INSTANCE_ID.match(instance_id):
        return _refused(422, "invalid-instance-id", None,
                        "an instance id is a random UUID version 4"), hub_state
    # Labels first, so a label's key form or type answers invalid-label
    # rather than the schema's general invalid-instance.
    if isinstance(body.get("labels"), dict):
        problems = label_problems(caps, body["labels"])
        if problems:
            return _refused(422, "invalid-label", problems[0][0], problems[0][1]), hub_state
    errors = _schema_errors(body, _load_instance_schema())
    if errors:
        where = ".".join(str(p) for p in errors[0].absolute_path)
        return _refused(422, "invalid-instance", where or None, errors[0].message), hub_state
    keys = [(r["channel"], negotiate.canonical_json(r["role"])) for r in body.get("roles") or []]
    if len(keys) != len(set(keys)):
        return _refused(422, "invalid-instance", "roles",
                        "a (channel, role) is claimed once"), hub_state
    definition = negotiate.product_definitions(hub_state, identity).get(body["definitionId"])
    if definition is None:
        return _refused(422, "unknown-definition", "definitionId",
                        "not a stored definition of this product"), hub_state
    # 4. Roles. A renewal re-evaluates every claim: a role whose holder has
    # lapsed or dropped it is granted now, never before (no auto-assignment).
    roles = evaluate_roles(caps, hub_state, well_known, instance_id, body, definition, now)
    lease = _text(_time(now) + datetime.timedelta(seconds=caps["instances"]["leaseSeconds"]))
    after = _stored_instance(identity, instance_id, body, negotiate.binding_of(submitter),
                             submitter.get("credentialKind"), roles, lease,
                             (stored or {}).get("observedAliases"))
    outcome = "partial" if any(r["result"] == "refused" for r in roles) else "accepted"
    response = _response(201 if stored is None else 200, outcome,
                         noop=stored is not None and stored["etag"] == after["etag"],
                         instance=_summary(after, now), roles=roles)
    return response, _replace_instance(hub_state, after, instance_id)


def delete_instance(caps, hub_state, submitter, request, now):
    """DELETE releases the instance and all its roles. Records it wrote keep
    its id; the definition stays referenced by them (rule 9)."""
    instance_id = request["instanceId"]
    stored = find_instance(hub_state, instance_id)
    pre = request.get("preconditions") or {}
    if not negotiate.permitted(submitter.get("permissions"), negotiate.PERMISSION["retire"]):
        return _refused(403, "not-authorised", None, "needs api:registrations:delete"), hub_state
    if stored is None or _ident(stored["identity"]) != _ident(request["identity"]):
        return _response(404, "not-found", reasons=[_reason("not-found")]), hub_state
    if negotiate.canonical_json(stored["boundTo"]) != \
            negotiate.canonical_json(negotiate.binding_of(submitter)):
        return _refused(403, "not-registration-owner"), hub_state
    if "ifMatch" not in pre:
        return _response(428, "precondition-failed",
                         reasons=[_reason("precondition-required")]), hub_state
    if pre["ifMatch"] != stored["etag"]:
        return _response(412, "precondition-failed", reasons=[_reason("stale-etag")],
                         current={"etag": stored["etag"],
                                  "leaseExpiresAt": stored["leaseExpiresAt"]}), hub_state
    return _response(200, "released", noop=False), _replace_instance(hub_state, None, instance_id)


# ── the owner ─────────────────────────────────────────────────────────

def _owner_refusal(request, submitter):
    if request.get("actor") != "owner" or not negotiate.owner_authorised(request, submitter):
        return _refused(403, "not-authorised", None,
                        "owner actions are on ns-tenant-admin, or API_SECRET in single mode")
    return None


def transfer_role(caps, hub_state, submitter, request, now, well_known):
    """The owner moves one role from the instance that was granted it to
    another live instance that claims it with `device` provenance. The
    precondition is the granted instance's etag; both etags change."""
    refusal = _owner_refusal(request, submitter)
    if refusal:
        return refusal, hub_state
    move = request["transferRole"]
    source = find_instance(hub_state, move["from"])
    target = find_instance(hub_state, move["to"])
    pre = request.get("preconditions") or {}
    if source is None or target is None:
        return _response(404, "not-found", reasons=[_reason("not-found")]), hub_state
    if "ifMatch" not in pre:
        return _response(428, "precondition-failed",
                         reasons=[_reason("precondition-required")]), hub_state
    if pre["ifMatch"] != source["etag"]:
        return _response(412, "precondition-failed", reasons=[_reason("stale-etag")],
                         current={"etag": source["etag"],
                                  "leaseExpiresAt": source["leaseExpiresAt"]}), hub_state
    key = {"channel": move["channel"], "role": move["role"], "provenance": "device"}
    if key not in granted(source):
        return _refused(409, "role-not-granted", None,
                        "the from instance was not granted this role"), hub_state
    claims = [r for r in target["instance"].get("roles") or []
              if r["channel"] == move["channel"] and r["role"] == move["role"]
              and r["provenance"] == "device"]
    if not claims:
        return _refused(409, "role-not-claimed", None,
                        "the to instance does not claim this role with device provenance"), hub_state
    if not live(target, now):
        return _refused(409, "not-live", None, "the to instance's lease has lapsed"), hub_state

    def moved(stored, now_granted):
        roles = []
        for r in stored["roles"]:
            if r["channel"] == move["channel"] and r["role"] == move["role"] and \
                    r["provenance"] == "device":
                r = {k: r[k] for k in ("channel", "role", "provenance")}
                if now_granted:
                    r["result"] = "granted"
                else:
                    r.update(result="refused", reasons=[_reason("role-held", None,
                                                                 "transferred by the owner")])
            roles.append(r)
        return _restate(stored, roles=roles)

    source_after, target_after = moved(source, False), moved(target, True)
    state = _replace_instance(hub_state, source_after, source["instanceId"])
    state = _replace_instance(state, target_after, target["instanceId"])
    return _response(200, "applied", noop=False,
                     instances=[_summary(source_after, now), _summary(target_after, now)]), state


def pins_etag(pins):
    return "sha256:" + hashlib.sha256(negotiate.canonical_json({"pins": pins})).hexdigest()


def _find_pins(hub_state, identity):
    for entry in (hub_state or {}).get("pins") or []:
        if _ident(entry["identity"]) == identity:
            return entry
    return None


def stored_versions(caps, hub_state, well_known, identity, element):
    """Every version of `element` (a stateSpans kind or an extension) the
    product's stored definitions store."""
    out = set()
    for definition in negotiate.product_definitions(hub_state, identity).values():
        for eid, _p, _d, node, kind in negotiate.elements(definition):
            if eid == element and kind in ("stateSpans", "extensions"):
                version = negotiate.stored_version(node)
                if version is not None:
                    out.add(version)
    return out


def pin_version(caps, hub_state, submitter, request, well_known):
    """`pin-version` / `unpin-version` (rule 3): the owner's choice of the
    version a site's default views show. A pin never changes stored data. Pins
    are their own resource with their own etag, so an owner's pin never
    fails the controller's next product update."""
    refusal = _owner_refusal(request, submitter)
    if refusal:
        return refusal, hub_state
    identity = _ident(request["identity"])
    entry = _find_pins(hub_state, identity)
    pre = request.get("preconditions") or {}
    if not pre:
        return _response(428, "precondition-failed",
                         reasons=[_reason("precondition-required")]), hub_state
    if entry is None and "ifNoneMatch" not in pre:
        return _response(412, "precondition-failed", reasons=[_reason("not-found")]), hub_state
    if entry is not None and pre.get("ifMatch") != entry["etag"]:
        return _response(412, "precondition-failed", reasons=[_reason("stale-etag")],
                         current={"etag": entry["etag"]}), hub_state
    pins = dict((entry or {}).get("pins") or {})
    element = request["element"]
    if request["action"] == "pin-version":
        if request["version"] not in stored_versions(caps, hub_state, well_known, identity,
                                                      element):
            return _refused(422, "unknown-version", "version",
                            "no stored definition of this product stores that version"), hub_state
        pins[element] = request["version"]
    else:
        pins.pop(element, None)
    state = copy.deepcopy(hub_state)
    rest = [p for p in state.get("pins") or [] if _ident(p["identity"]) != identity]
    after = {"identity": _identity(identity), "etag": pins_etag(pins), "pins": pins}
    noop = entry is not None and entry["pins"] == pins
    if pins:
        rest.append(after)
    state["pins"] = rest
    return _response(201 if entry is None else 200, "applied", noop=noop, pins=after), state


def overlaps(hub_state, now):
    """Rule 6: each live claimant refused `role-held`, with the role's
    current holder (None when the holder has since lapsed or dropped it: the
    claimant gets the role on its next renewal). Listed until the claimant
    drops the claim or its own lease lapses."""
    out = []
    for stored in _instances(hub_state):
        if not live(stored, now):
            continue
        for r in stored.get("roles") or []:
            if r["result"] == "refused" and r["provenance"] == "device" and \
                    any(x["code"] == "role-held" for x in r.get("reasons") or []):
                out.append({"channel": r["channel"], "role": r["role"],
                            "claimant": stored["instanceId"],
                            "holder": holder(hub_state, r["channel"], r["role"], now,
                                             exclude=stored["instanceId"])})
    return sorted(out, key=negotiate.canonical_json)


def list_instances(caps, hub_state, submitter, request, now):
    """The owner's listing: every stored instance with its roles and labels,
    and the overlaps. An observed alias is identifying and withheld unless
    the owner asks for withheld members (D18 addendum `unlabelledPolicy:
    withhold` style); it is never in the capability document or a default
    export."""
    refusal = _owner_refusal(request, submitter)
    if refusal:
        return refusal, hub_state
    listed = []
    for stored in sorted(_instances(hub_state), key=lambda s: s["instanceId"]):
        entry = _summary(stored, now)
        entry["roles"] = stored["roles"]
        entry["labels"] = stored["instance"].get("labels") or {}
        if request.get("includeWithheld") and stored.get("observedAliases"):
            entry["observedAliases"] = stored["observedAliases"]
        listed.append(entry)
    return _response(200, "listed", instances=listed, overlaps=overlaps(hub_state, now)), hub_state


# ── commands, read selection, projection, writes, retention ───────────

def route_command(caps, hub_state, request, now):
    """Rule 6: a command for a channel goes to the live `device` instance
    holding `command-sink` on it. With no holder the hub refuses the command
    and never routes it to a guess — not to a lapsed former holder, not to a
    `simulated` command sink, not to the product's most recent instance.
    The command API itself is not specified here."""
    destination = holder(hub_state, request["channel"], "command-sink", now)
    if destination is None:
        return _refused(409, "no-command-destination", "channel",
                        "no live device instance holds command-sink on this channel"), hub_state
    stored = find_instance(hub_state, destination)
    return _response(200, "routed", destination={
        "instanceId": destination, "vendor": stored["identity"]["vendor"],
        "product": stored["identity"]["product"],
        "definitionId": stored["instance"]["definitionId"]}), hub_state


def _version_key(version):
    """Newest first by dot-separated parts, numeric parts compared as
    numbers and numeric before text; versions are opaque strings otherwise."""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in str(version).split(".")]


def _accepted_versions(caps, hub_state, well_known, identity, element, grammar):
    """Versions of `element` in stored definitions where the hub, with its
    current capabilities, accepts the element: the operator's limits."""
    out = set()
    for did, definition in negotiate.product_definitions(hub_state, identity).items():
        _top, results = negotiate.evaluate(caps, hub_state, {}, definition, grammar, None,
                                           well_known)
        ok = {r["element"] for r in results if r["result"] in negotiate.ACCEPTED}
        for eid, _p, _d, node, kind in negotiate.elements(definition):
            if eid == element and eid in ok and negotiate.stored_version(node) is not None:
                out.add(negotiate.stored_version(node))
    return out


def _matches(labels, selector):
    return all(labels.get(k) == v for k, v in (selector or {}).items())


def select_versions(caps, hub_state, identity, now, well_known, grammar, selector=None):
    """Rule 3. For each versioned element of the product: the version a view
    shows. The operator's capability document limits what is accepted at
    all; then the owner's pin (default views only); then the newest version
    a live instance with a granted `device` `source` role on the element's
    channel runs; then the newest stored. A view with a label selector uses
    only the live instances that match it, whatever their provenance, and no
    pin. Returns {element: {version, by}}."""
    definitions = negotiate.product_definitions(hub_state, identity)
    element_ids = sorted({eid for d in definitions.values()
                          for eid, _p, _d, node, kind in negotiate.elements(d)
                          if kind in ("stateSpans", "extensions")})
    pins = (_find_pins(hub_state, identity) or {}).get("pins") or {}
    out = {}
    for element in element_ids:
        allowed = _accepted_versions(caps, hub_state, well_known, identity, element, grammar)
        if not allowed:
            out[element] = {"version": None, "by": "none-accepted"}
            continue
        if selector is None and pins.get(element) in allowed:
            out[element] = {"version": pins[element], "by": "owner-pin"}
            continue
        used = set()
        for stored in _instances(hub_state):
            if _ident(stored["identity"]) != identity or not live(stored, now):
                continue
            definition = definitions.get(stored["instance"]["definitionId"])
            if definition is None:
                continue
            node = next((n for eid, _p, _d, n, _k in negotiate.elements(definition)
                         if eid == element), None)
            if node is None:
                continue
            channel = channel_of(caps, well_known, definition, element)
            if selector is not None:
                counts = _matches(stored["instance"].get("labels") or {}, selector)
            else:
                counts = {"channel": channel, "role": "source", "provenance": "device"} \
                    in granted(stored)
            version = negotiate.stored_version(node)
            if counts and version in allowed:
                used.add(version)
        if used:
            out[element] = {"version": max(used, key=_version_key),
                            "by": "label-selector" if selector is not None else "live-device"}
        else:
            out[element] = {"version": max(allowed, key=_version_key), "by": "newest-stored"}
    return out


DURATION_FACTORS = {"seconds": 1, "minutes": 60, "milliseconds": 0.001}


def project(caps, hub_state, record, well_known):
    """Rule 8: the projected carrier document an older reader is served for
    one typed record, or None when the element has no declared mapping. The
    document is labelled with the marker `projectedFrom`, is never stored as
    a source and is read-only; its `identifier` is the typed entity's id.
    *(Changed 2026-10-16, D20 rule 8: on an `objectId` hub its `_id` is the
    ObjectId the hub assigned at the typed write and stored with the
    record; an `opaque` hub may use the typed id for both, as this read
    before.)* Only the wire members the mapping declares are
    filled: the collection, eventType, the start time and the duration in
    the wire's unit (or its indefinite sentinel)."""
    identity = _ident(record["identity"])
    definition = negotiate.product_definitions(hub_state, identity).get(record["definitionId"])
    node = next((n for eid, _p, _d, n, k in negotiate.elements(definition or {"spec": {}})
                 if eid == record["element"] and k == "stateSpans"), None)
    resolved = negotiate._resolved(caps, well_known, "stateSpans", node) if node else None
    wire = (resolved or {}).get("wire")
    if not wire:
        return None
    identifier, _id = quirks_registration.projected_ids(caps, record)
    document = {"identifier": identifier, "_id": _id, "created_at": record["startedAt"]}
    if wire.get("eventType"):
        document["eventType"] = wire["eventType"]
    if wire.get("durationField"):
        seconds = record.get("durationSeconds")
        if seconds is None and isinstance(wire.get("indefinite"), dict):
            document[wire["indefinite"]["field"]] = wire["indefinite"]["value"]
        elif seconds is not None:
            factor = DURATION_FACTORS[wire.get("durationUnit", "seconds")]
            value = seconds / factor
            document[wire["durationField"]] = int(value) if value == int(value) else value
    document[PROJECTION_MARKER] = {"definitionId": record["definitionId"],
                                   "element": record["element"],
                                   "entities": [record["id"]]}
    return {"collection": wire["collection"], "document": document}


def _projected_ids(caps, hub_state, well_known):
    out = {}
    for record in (hub_state or {}).get("records") or []:
        if record.get("as") == "typed" and record.get("carrierView") == "served":
            projected = project(caps, hub_state, record, well_known)
            if projected:
                doc = projected["document"]
                out[(projected["collection"], "identifier", doc["identifier"])] = record["id"]
                # D20 rule 8: a write aimed at the projected `_id` is refused too.
                out[(projected["collection"], "_id", doc["_id"])] = record["id"]
    return out


def write(caps, hub_state, request, now, well_known, assigner=None):
    """One write, as the hub attributes and accepts it (rules 4, 6, 8; the
    four compatibility cells). Carrier writes are never refused for
    exclusivity. Typed writes need a live instance holding `source` on the
    element's channel when the hub advertises `instances`."""
    w = request["write"]
    if not caps:
        # An older hub: today's documents, with nothing negotiated or attributed.
        return _response(200, "written", write={"accepted": True, "as": w["as"]}), hub_state
    identity = _ident(request["identity"]) if request.get("identity") else (None, None)
    instance_id = w.get("instanceId")
    stored = find_instance(hub_state, instance_id) if instance_id else None
    attribution = {"vendor": identity[0], "product": identity[1],
                   "instanceId": instance_id if stored else "unregistered"}
    target = w.get("target")
    key = None
    if target:
        key = ("identifier", target["identifier"]) if "identifier" in target \
            else ("_id", target["_id"])
    if target and (target["collection"],) + key in _projected_ids(caps, hub_state, well_known):
        return _refused(409, "projected-read-only", "target",
                        "a projected document is served, never stored, and is read-only"), hub_state
    if w["as"] == "carrier":
        result = {"accepted": True, "as": "carrier", "attributedTo": attribution}
        after = hub_state
        if stored is not None and w.get("collection") == "devicestatus" and \
                isinstance((w.get("document") or {}).get("device"), str):
            aliases = list(stored.get("observedAliases") or [])
            alias = {"value": w["document"]["device"], "sensitivity": ALIAS_SENSITIVITY}
            if alias not in aliases:
                aliases.append(alias)
                after = _replace_instance(hub_state, _restate(stored, aliases=aliases),
                                          instance_id)
        if w.get("link") and w.get("recordId") is not None:
            result["linkedTo"] = next((r["id"] for r in (hub_state or {}).get("records") or []
                                       if r.get("as") == "typed"
                                       and r.get("instanceId") == attribution["instanceId"]
                                       and r.get("controllerRecordId") == w["recordId"]), None)
        if "sent" in w:
            # D20 rules 5 to 7: both ids, identifier first, the mappings applied.
            members, after = quirks_registration.carrier_write(caps, after, w, assigner)
            result.update(members)
        if "writer" in w:
            # D20 rule 2: the catalogue's mapping for a version before registration.
            mapping, applied = quirks_registration.catalogue_mapping(
                caps, well_known, w["writer"], w["element"])
            if mapping:
                result["slotMapping"] = mapping
            if applied:
                result["quirksApplied"] = result.get("quirksApplied", []) + applied
        return _response(200, "written", write=result), after
    # Typed.
    if not caps.get("instances"):
        return _response(200, "written", write={"accepted": True, "as": "typed",
                                                "attributedTo": attribution}), hub_state
    if instance_id is None:
        return _refused(422, "instance-required", None,
                        "this hub requires an instance id on typed writes"), hub_state
    if stored is None or _ident(stored["identity"]) != identity:
        return _refused(422, "instance-required", None, "no such instance of this product"), hub_state
    if not live(stored, now):
        return _refused(409, "not-live", None, "renew the instance before writing"), hub_state
    definition = negotiate.product_definitions(hub_state, identity)[stored["instance"]["definitionId"]]
    channel = channel_of(caps, well_known, definition, w["element"])
    role = next((g for g in granted(stored) if g["channel"] == channel and g["role"] == "source"),
                None)
    if role is None:
        if holder(hub_state, channel, "source", now, exclude=instance_id):
            return _refused(409, "role-held", None,
                            "another instance is the source of record; write the carrier"), hub_state
        return _refused(409, "role-not-granted", None,
                        "the instance holds no source role on this channel"), hub_state
    result = {"accepted": True, "as": "typed", "attributedTo": attribution,
              "definitionId": stored["instance"]["definitionId"],
              "provenance": role["provenance"]}
    after = hub_state
    node = next((n for eid, _p, _d, n, k in negotiate.elements(definition)
                 if eid == w["element"] and k == "stateSpans"), None)
    source = negotiate._resolved(caps, well_known, "stateSpans", node) if node else None
    if source and "sameAs" in source and channel == source["sameAs"]:
        # D20 rule 3: a channel a declared `sameAs` decided is reported as declared.
        result["slotMapping"] = {"slot": source["slot"], "channel": channel, "by": "declared"}
    if w.get("recordId") is not None:
        # D20 rules 5 and 8: both ids; the hub assigns and stores `_id` now.
        members, after = quirks_registration.typed_write(caps, hub_state, w, stored, assigner)
        result.update(members)
    return _response(200, "written", write=result), after


def retention(caps, hub_state, request, now):
    """Rule 9: a definition may be removed only when no stored record, no
    live instance and not the product resource's current registration
    references it. A definition that is no longer current is not removed
    while anything references it."""
    identity = _ident(request["identity"])
    did = request["definitionId"]
    reasons = []
    if any(r.get("definitionId") == did for r in (hub_state or {}).get("records") or []):
        reasons.append(_reason("definition-referenced", None, "stored records reference it"))
    if any(s["instance"]["definitionId"] == did and live(s, now) for s in _instances(hub_state)):
        reasons.append(_reason("definition-in-use", None, "a live instance runs it"))
    stored = negotiate._find(hub_state, identity)
    if stored and stored.get("registration") is not None and \
            negotiate.definition_id(stored["registration"]) == did:
        reasons.append(_reason("definition-current", None,
                               "it is the product resource's current registration"))
    if reasons:
        return _response(200, "not-eligible", reasons=reasons), hub_state
    return _response(200, "eligible"), hub_state


def after_submit(hub_state, response, stored_after):
    """The hub state after a product PUT (§3.5): the product resource holds
    the new registration, and the registration it replaced stays stored as a
    content-addressed definition (D19 rule 1), so records and instances that
    name it keep their meaning."""
    if response["outcome"] not in ("accepted", "partial") or response.get("noop"):
        return hub_state
    identity = _ident(stored_after["identity"])
    state = copy.deepcopy(hub_state)
    before = negotiate._find(hub_state, identity)
    state["registrations"] = [r for r in state.get("registrations") or []
                              if _ident(r["identity"]) != identity] + [stored_after]
    if before is not None and before.get("registration") is not None:
        old = negotiate.definition_id(before["registration"])
        listed = {d["definitionId"] for d in state.get("definitions") or []}
        if old not in listed and old != negotiate.definition_id(stored_after["registration"]):
            state.setdefault("definitions", []).append(
                {"identity": _identity(identity), "definitionId": old,
                 "definition": before["registration"]})
    return state


# ── the controller's side ─────────────────────────────────────────────

def should_register_instance(caps):
    """A controller creates an instance only when the hub advertises
    `instances` (and `submit`). Otherwise it writes as SPEC-REG-NEGOTIATE
    says, with no instance id."""
    return bool(caps and caps.get("submit") and caps.get("instances"))


def role_plan(plan, response, definition, caps=None, well_known=None):
    """The write plan after an instance PUT: an element on a channel whose
    `source` role was refused `role-held` is written as its carrier (rule 6),
    whatever the definition's negotiation accepted."""
    after = copy.deepcopy(plan)
    refused = {r["channel"] for r in (response or {}).get("roles") or []
               if r["role"] == "source" and r["result"] != "granted"}
    for eid, _p, _d, node, kind in negotiate.elements(definition):
        if channel_of(caps, well_known, definition, eid) in refused and \
                after.get(eid, {}).get("write") in ("typed", "typed-and-carrier"):
            after[eid] = negotiate._not_accepted(kind, node, caps, well_known)
    return after


# ── cases ─────────────────────────────────────────────────────────────

ACTIONS = ("put-definition", "put-instance", "delete-instance", "transfer-role", "pin-version",
           "unpin-version", "list-instances", "route-command", "select-versions", "project",
           "write", "retention-check")


def run_case(case, grammar=None):
    """Everything a case's `expected` states, computed."""
    grammar = grammar or negotiate._load(negotiate.GRAMMAR_SCHEMA)
    caps, state = case["capabilities"], case.get("hubState") or {}
    request, body, now = case["request"], case.get("body"), case["now"]
    submitter = case.get("submitter") or {}
    well_known = case.get("wellKnownRegistrations")
    action = request["action"]
    if action == "submit":
        response, stored_after = negotiate.negotiate(caps, state, submitter, body, request,
                                                     grammar, case.get("carrierViews"),
                                                     well_known)
        after = after_submit(state, response, stored_after)
    elif action == "put-definition":
        response, after = put_definition(caps, state, submitter, request, body, grammar, well_known)
    elif action == "put-instance":
        response, after = put_instance(caps, state, submitter, request, body, now, well_known)
    elif action == "delete-instance":
        response, after = delete_instance(caps, state, submitter, request, now)
    elif action == "transfer-role":
        response, after = transfer_role(caps, state, submitter, request, now, well_known)
    elif action in ("pin-version", "unpin-version"):
        response, after = pin_version(caps, state, submitter, request, well_known)
    elif action == "list-instances":
        response, after = list_instances(caps, state, submitter, request, now)
    elif action == "route-command":
        response, after = route_command(caps, state, request, now)
    elif action == "select-versions":
        selection = select_versions(caps, state, _ident(request["identity"]), now, well_known,
                                    grammar, request.get("selector"))
        response, after = _response(200, "selected", selection=selection), state
    elif action == "project":
        projected = project(caps, state, request["record"], well_known)
        response = _response(200, "projected", projected=projected) if projected else \
            _refused(409, "no-carrier-mapping", None, "the element declares no carrier mapping")
        after = state
    elif action == "write":
        response, after = write(caps, state, request, now, well_known,
                                quirks_registration.Assigner(case.get("assignedIds")))
    elif action == "retention-check":
        response, after = retention(caps, state, request, now)
    else:
        raise ValueError(action)
    result = {"controllerWouldRegister": should_register_instance(caps), "response": response}
    if "stateAfter" in case["expected"]:
        result["stateAfter"] = after
    if "plan" in case:
        result["plan"] = role_plan(case["plan"], response,
                                   negotiate.product_definitions(state, _ident(request["identity"]))
                                   [body["definitionId"]], caps, well_known)
    return result


def load_cases():
    import yaml
    root = corpus.repo_root() / CASES_DIR
    return {p.stem: yaml.safe_load(p.read_text()) for p in sorted(root.glob("*.yaml"))}
