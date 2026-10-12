"""negotiate.py — reference decision function for registration negotiation.

D18 addendum rule 6 (execution plan §2.6.1; queue item SPEC-REG-NEGOTIATE;
contract in the hub-sync design §3.5, schemas
`specs/sync/hub-capabilities.schema.json` and
`specs/sync/registration-submit.schema.json`).

**This is a reference, not a hub.** It exists to show that the conformance
cases under `specs/sync/conformance/` are self-consistent: given a hub's
capability document, its stored registrations, a submitter and a request, it
computes the response the contract requires, and given that response it
computes the controller's write plan (the fallback). It stores nothing,
serves nothing and is never run by a hub. A hub implements the contract in
its own code and is tested against the same cases.

The same computation is what a controller can do before submitting: the
capability document carries everything the response depends on except the
tenant's stored state and the submitter's grants.
"""

import copy
import hashlib
import json

import jsonschema

from . import corpus, sync_model

GRAMMAR_SCHEMA = "specs/sync/controller-state-model.schema.json"
CAPABILITIES_SCHEMA = "specs/sync/hub-capabilities.schema.json"
SUBMIT_SCHEMA = "specs/sync/registration-submit.schema.json"
CONFORMANCE_DIR = "specs/sync/conformance"

GRAMMAR_API = "nightscout.dev/sync/v1"

# Members the submit contract itself reads; a hub must interpret them.
REQUIRED_MEMBERS = (
    "apiVersion", "kind", "metadata.vendor", "metadata.product", "metadata.tier",
    "spec.cadence", "spec.documents.*.collection", "spec.documents.*.decomposesTo",
)

# Map-valued members: their keys are names, not grammar members, and are
# written `*` in an `interprets` path.
def _is_map(norm):
    return norm == "spec.extensions" or norm.endswith(".vocabularies")


PERMISSION = {"submit": "api:registrations:create", "retire": "api:registrations:delete"}

# `description` is an annotation: it constrains nothing, so it is never a
# reason to reject a type.
_ANNOTATIONS = {"description"}


def _load(rel):
    return json.loads((corpus.repo_root() / rel).read_text())


def canonical_json(value):
    """RFC 8785 canonical form, for the values the cases use (strings,
    integers, booleans, null and short decimals, where Python's shortest
    round-trip float repr matches ECMAScript's)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def etag(registration, state):
    digest = hashlib.sha256(canonical_json(
        {"registration": registration, "state": state})).hexdigest()
    return f"sha256:{digest}"


# ── the capability document ───────────────────────────────────────────

def _covers(entry, norm):
    return norm == entry or norm.startswith(entry + ".")


def interpreted(caps, norm):
    """Whether the hub interprets the member at normalised path `norm`
    (covered by an entry, or an ancestor of one)."""
    entries = caps["grammar"]["interprets"]
    return any(_covers(e, norm) for e in entries)


def _ancestor_of_entry(caps, norm):
    return any(e.startswith(norm + ".") for e in caps["grammar"]["interprets"])


def capability_problems(caps):
    """What JSON Schema cannot check about a capability document."""
    problems = []
    for member in REQUIRED_MEMBERS:
        if not interpreted(caps, member):
            problems.append(f"required member not interpreted: {member}")
    for version in caps["grammar"]["versions"]:
        if version["apiVersion"] != f"nightscout.dev/sync/v{version['major']}":
            problems.append(f"apiVersion and major disagree: {version}")
    return problems


def _horizon_classes(caps):
    return set((caps.get("horizons") or {}).get("classes") or [])


def _availability(caps):
    return set((caps.get("horizons") or {}).get("availability") or ["released"])


# ── rule 1: what the hub ignores ──────────────────────────────────────

def _uncovered(caps, node, path, norm, out):
    for key, value in node.items():
        p = f"{path}.{key}" if path else key
        n = (f"{norm}.{'*' if _is_map(norm) else key}") if norm else key
        if interpreted(caps, n):
            continue
        if not _ancestor_of_entry(caps, n):
            out.add(p)
            continue
        if isinstance(value, dict):
            _uncovered(caps, value, p, n, out)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    _uncovered(caps, item, f"{p}.{i}", f"{n}.*", out)


def _under(path, ancestor):
    return path == ancestor or path.startswith(ancestor + ".")


def ignored_members(caps, registration, grammar, unknown_in=None):
    """Rule 1 as a hub with these capabilities applies it: members the
    grammar does not define (`sync_model.unknown_grammar_fields`, computed
    over `unknown_in` when given) plus members it defines that the hub does
    not interpret. A path whose ancestor is already ignored is not listed
    again."""
    found = set(sync_model.unknown_grammar_fields(
        registration if unknown_in is None else unknown_in, grammar))
    _uncovered(caps, registration, "", "", found)
    return sorted(p for p in found
                  if not any(q != p and _under(p, q) for q in found))


# ── elements ──────────────────────────────────────────────────────────

def _typed(field):
    return isinstance(field, dict) and ("type" in field or "typeRef" in field)


def elements(registration):
    """The elements of a registration, in response order: (id, path,
    defining member paths, node, kind)."""
    spec = registration.get("spec") or {}
    out = []
    for i, span in enumerate(spec.get("stateSpans") or []):
        name = span.get("kind") or span.get("category")
        path = f"spec.stateSpans.{i}"
        out.append((f"stateSpans/{name}", path, [f"{path}.category"], span, "stateSpans"))
    for ns, ext in (spec.get("extensions") or {}).items():
        path = f"spec.extensions.{ns}"
        defining = [f"{path}.fields"]
        defining += [f"{path}.{k}" for k in ("version", "versions") if k in ext]
        for j, field in enumerate(ext.get("fields") or []):
            if isinstance(field, dict):
                defining += [f"{path}.fields.{j}.{k}" for k in ("name", "type", "typeRef")
                             if k in field]
        out.append((f"extensions/{ns}", path, defining, ext, "extensions"))
    for i, field in enumerate((spec.get("settings") or {}).get("fields") or []):
        if _typed(field):
            path = f"spec.settings.fields.{i}"
            defining = [f"{path}.{k}" for k in ("name", "type", "typeRef") if k in field]
            out.append((f"settings.fields/{field['name']}", path, defining, field, "settings"))
    for i, row in enumerate(spec.get("replayInputs") or []):
        if _typed(row):
            path = f"spec.replayInputs.{i}"
            defining = [f"{path}.{k}" for k in ("input", "type", "typeRef") if k in row]
            out.append((f"replayInputs/{row['input']}", path, defining, row, "replayInputs"))
    return out


def _fragment_of(field):
    if "type" in field:
        return field["type"]
    definition = sync_model.resolve_type_ref(corpus.repo_root(), field["typeRef"])
    return {k: v for k, v in definition.items() if not k.startswith("x-")}


def _keyword_problems(caps, fragment, path):
    subset = set(caps.get("typeFragment", {}).get("keywords") or ["type"])
    formats = caps.get("typeFragment", {}).get("formats")
    problems = []
    for key, value in fragment.items():
        if key in _ANNOTATIONS:
            continue
        if key not in subset:
            problems.append((f"{path}.{key}", f"keyword {key!r} is outside the hub's subset"))
        elif key == "format" and formats is not None and value not in formats:
            problems.append((f"{path}.format", f"format {value!r} is outside the hub's subset"))
    if isinstance(fragment.get("items"), dict):
        problems += _keyword_problems(caps, fragment["items"], f"{path}.items")
    for name, sub in (fragment.get("properties") or {}).items():
        if isinstance(sub, dict):
            problems += _keyword_problems(caps, sub, f"{path}.properties.{name}")
    return problems


def type_depth(fragment):
    if isinstance(fragment.get("items"), dict):
        return 1 + type_depth(fragment["items"])
    props = [p for p in (fragment.get("properties") or {}).values() if isinstance(p, dict)]
    return 1 + (max(type_depth(p) for p in props) if props else 0)


def _owns(roots, namespace):
    return any(r == "*" or namespace == r or namespace.startswith(r + ".") for r in roots)


def _claimed_elsewhere(hub_state, identity, namespace):
    for stored in (hub_state or {}).get("registrations") or []:
        meta = stored["registration"]["metadata"]
        if (meta["vendor"], meta["product"]) == identity:
            continue
        if namespace in ((stored["registration"].get("spec") or {}).get("extensions") or {}):
            return f"{meta['vendor']}/{meta['product']}"
    return None


def _reason(code, path=None, detail=None):
    reason = {"code": code}
    if path is not None:
        reason["path"] = path
    if detail is not None:
        reason["detail"] = detail
    return reason


def _field_checks(caps, field, path):
    reasons = []
    try:
        fragment = _fragment_of(field)
    except KeyError:
        return [_reason("invalid-element", f"{path}.typeRef", "typeRef does not resolve")]
    for where, detail in _keyword_problems(caps, fragment, f"{path}.{'type' if 'type' in field else 'typeRef'}"):
        reasons.append(_reason("unsupported-type-keyword", where, detail))
    limit = (caps.get("limits") or {}).get("maxTypeDepth")
    if limit is not None and type_depth(fragment) > limit:
        reasons.append(_reason("limit-exceeded", path,
                               f"type depth {type_depth(fragment)} exceeds maxTypeDepth {limit}"))
    return reasons


def _declared_checks(caps, node, path, ignored):
    """Availability and horizon, checked only where declared and not
    ignored: a member the hub ignores is not a reason to reject."""
    reasons = []

    def live(member):
        return member in node and not any(_under(f"{path}.{member}", q) for q in ignored)

    if live("availability") and node["availability"] not in _availability(caps):
        reasons.append(_reason("unsupported-availability", f"{path}.availability",
                               f"availability {node['availability']!r} is not supported"))
    if live("horizon") and isinstance(node["horizon"], dict) and \
            node["horizon"].get("class") not in _horizon_classes(caps):
        reasons.append(_reason("unsupported-horizon", f"{path}.horizon",
                               f"horizon class {node['horizon'].get('class')!r} is not supported"))
    return reasons


def evaluate(caps, hub_state, submitter, registration, grammar):
    """The per-element results and registration-level ignored members for a
    registration that passed the registration-level checks."""
    meta = registration["metadata"]
    identity = (meta["vendor"], meta["product"])
    roots = submitter.get("namespaceRoots") or []
    limits = caps.get("limits") or {}
    extension_schema = jsonschema.Draft202012Validator(
        {"$ref": "#/$defs/extension", "$defs": grammar["$defs"]})
    namespace_schema = jsonschema.Draft202012Validator(
        {"$ref": "#/$defs/namespace", "$defs": grammar["$defs"]})

    # Pass 1: element checks that do not depend on what is ignored.
    pre = {}
    for eid, path, _defining, node, kind in elements(registration):
        reasons = []
        if kind == "extensions":
            ns = eid.split("/", 1)[1]
            if not _owns(roots, ns):
                reasons.append(_reason("namespace-not-owned", path,
                                       "the submitting credential holds no root covering this namespace"))
            owner = _claimed_elsewhere(hub_state, identity, ns)
            if owner:
                reasons.append(_reason("namespace-claimed", path,
                                       f"claimed on this tenant by {owner}"))
            fields = node.get("fields") if isinstance(node.get("fields"), list) else []
            for j, field in enumerate(fields):
                if not _typed(field):
                    reasons.append(_reason("untyped-extension", f"{path}.fields.{j}",
                                           "an extension field without type or typeRef"))
            for j, field in enumerate(fields):
                if _typed(field):
                    reasons += _field_checks(caps, field, f"{path}.fields.{j}")
            limit = limits.get("maxFieldsPerExtension")
            if limit is not None and len(fields) > limit:
                reasons.append(_reason("limit-exceeded", f"{path}.fields",
                                       f"{len(fields)} fields exceed maxFieldsPerExtension {limit}"))
            if not reasons:
                errors = list(namespace_schema.iter_errors(ns)) + \
                    sorted(extension_schema.iter_errors(node), key=lambda e: list(e.path))
                if errors:
                    reasons.append(_reason("invalid-element", path, errors[0].message))
        elif kind in ("settings", "replayInputs"):
            reasons += _field_checks(caps, node, path)
        if not reasons and kind in ("stateSpans", "extensions"):
            try:
                sync_model.version_plan(node)
            except (ValueError, KeyError, TypeError) as error:
                reasons.append(_reason("version-plan-invalid", path, str(error)))
        pre[eid] = reasons

    # Pass 2: what the hub ignores. Members the grammar does not define are
    # found by validation, so they are computed with the extensions that
    # failed pass 1 removed (an invalid subschema would report its own
    # members as unknown); uninterpreted members over the whole registration.
    clean = copy.deepcopy(registration)
    for eid, reasons in pre.items():
        if reasons and eid.startswith("extensions/"):
            clean["spec"]["extensions"].pop(eid.split("/", 1)[1])
    ignored = ignored_members(caps, registration, grammar, unknown_in=clean)

    results = []
    prefixes = []
    for eid, path, defining, node, kind in elements(registration):
        prefixes.append(path)
        not_interpreted = sorted({q for q in ignored for d in defining if _under(d, q)})
        if not_interpreted:
            results.append({"element": eid, "result": "rejected", "reasons": [
                _reason("not-interpreted", q, "the hub does not interpret this member")
                for q in not_interpreted]})
            continue
        # The first failing group is reported: pass 1's reasons, else the
        # declared availability and horizons.
        reasons = pre[eid]
        if not reasons:
            reasons = _declared_checks(caps, node, path, ignored)
            if kind == "extensions":
                for j, field in enumerate(node.get("fields") or []):
                    reasons += _declared_checks(caps, field, f"{path}.fields.{j}", ignored)
        if reasons:
            results.append({"element": eid, "result": "rejected", "reasons": reasons})
            continue
        inside = [q for q in ignored if q.startswith(path + ".")]
        if inside:
            results.append({"element": eid, "result": "accepted-with-ignored-members",
                            "ignored": inside})
        else:
            results.append({"element": eid, "result": "accepted"})
    top = [q for q in ignored if not any(q.startswith(p + ".") for p in prefixes)]
    return top, results


# ── the request ───────────────────────────────────────────────────────

def permitted(grants, wanted):
    """Shiro-style implication: `*` matches any part, and a shorter grant
    implies every longer permission under it."""
    want = wanted.split(":")
    for grant in grants or []:
        parts = grant.split(":")
        if all(p == "*" or (i < len(want) and p == want[i]) for i, p in enumerate(parts)) \
                and all(p == "*" for p in parts[len(want):]):
            return True
    return False


def _response(status, outcome, **members):
    response = {"apiVersion": GRAMMAR_API, "kind": "RegistrationResponse",
                "status": status, "outcome": outcome}
    response.update({k: v for k, v in members.items() if v is not None})
    return response


def _summary(stored):
    meta = stored["registration"]["metadata"]
    summary = {"vendor": meta["vendor"], "product": meta["product"]}
    if "versionRange" in meta:
        summary["versionRange"] = meta["versionRange"]
    summary.update({"state": stored["state"], "etag": stored["etag"]})
    return summary


def _current(stored):
    return {"state": stored["state"], "etag": stored["etag"]}


def _find(hub_state, identity):
    for stored in (hub_state or {}).get("registrations") or []:
        meta = stored["registration"]["metadata"]
        if (meta["vendor"], meta["product"]) == identity:
            return stored
    return None


def _store(registration, state):
    return {"state": state, "etag": etag(registration, state),
            "registration": registration}


def _accepted(caps, hub_state, submitter, registration, grammar, stored_after, status, noop):
    top, results = evaluate(caps, hub_state, submitter, registration, grammar)
    outcome = "partial" if any(r["result"] == "rejected" for r in results) else "accepted"
    return _response(status, outcome, noop=noop, registration=_summary(stored_after),
                     ignored=top, elements=results), stored_after


def negotiate(caps, hub_state, submitter, registration, request, grammar=None):
    """The response a hub with `caps` and `hub_state` gives `request`, and
    the stored registration afterwards (None when none is stored)."""
    grammar = grammar or _load(GRAMMAR_SCHEMA)
    if not caps or not caps.get("submit"):
        raise ValueError("this hub offers no submit endpoint; nothing is negotiated")
    identity = (request["identity"]["vendor"], request["identity"]["product"])
    stored = _find(hub_state, identity)
    action = request["action"]
    pre = request.get("preconditions") or {}

    def reject(status, code, path=None, detail=None):
        return _response(status, "rejected", reasons=[_reason(code, path, detail)]), stored

    def failed(status, code, detail=None):
        return _response(status, "precondition-failed", reasons=[_reason(code, None, detail)],
                         current=_current(stored) if stored else None), stored

    # 1. Authorisation.
    if not permitted(submitter.get("permissions"), PERMISSION[action]):
        return reject(403, "not-authorised", None, f"needs {PERMISSION[action]}")

    # 2. Preconditions (RFC 9110 §13.2.1: after authorisation, before the content).
    if not pre:
        return failed(428, "precondition-required", "send If-None-Match: * or If-Match")
    if action == "retire":
        if stored is None:
            return _response(404, "not-found", reasons=[_reason("not-found")]), None
        for ns in (stored["registration"].get("spec") or {}).get("extensions") or {}:
            if not _owns(submitter.get("namespaceRoots") or [], ns):
                return reject(403, "not-authorised", f"spec.extensions.{ns}",
                              "the credential does not own every namespace of the registration")
        if "ifMatch" not in pre:
            return failed(412, "registration-exists", "retire needs If-Match")
        if pre["ifMatch"] != stored["etag"]:
            return failed(412, "stale-etag")
        if stored["state"] == "retired":
            return _response(200, "retired", noop=True, registration=_summary(stored),
                             elements=[]), stored
        after = _store(stored["registration"], "retired")
        return _response(200, "retired", noop=False, registration=_summary(after),
                         elements=[]), after

    same = stored is not None and stored["state"] == "active" and \
        canonical_json(stored["registration"]) == canonical_json(registration)
    if "ifNoneMatch" in pre and stored is not None and not same:
        return failed(412, "registration-exists")
    if "ifMatch" in pre:
        if stored is None:
            return failed(412, "not-found")
        if pre["ifMatch"] != stored["etag"] and not same:
            return failed(412, "stale-etag")

    # 3. Registration-level content checks.
    api = registration.get("apiVersion")
    if api not in [v["apiVersion"] for v in caps["grammar"]["versions"]]:
        return reject(422, "unsupported-grammar-major", "apiVersion",
                      f"{api!r} is not among the hub's grammar versions")
    if api != GRAMMAR_API:
        raise NotImplementedError(f"the reference reads {GRAMMAR_API} only")
    if registration.get("kind") != "ControllerStateModel":
        return reject(422, "invalid-registration", "kind")
    meta = registration.get("metadata") or {}
    if (meta.get("vendor"), meta.get("product")) != identity:
        return reject(422, "identity-mismatch", "metadata",
                      "metadata.vendor/product differ from the resource identity")
    if meta.get("tier") != "controller-owned":
        return reject(422, "wrong-tier", "metadata.tier",
                      "only a controller-owned registration may be submitted")
    limits = caps.get("limits") or {}
    size = len(canonical_json(registration))
    if limits.get("maxRegistrationBytes") is not None and size > limits["maxRegistrationBytes"]:
        return reject(413, "limit-exceeded", None,
                      f"{size} bytes exceed maxRegistrationBytes {limits['maxRegistrationBytes']}")
    count = len((registration.get("spec") or {}).get("extensions") or {})
    if limits.get("maxExtensions") is not None and count > limits["maxExtensions"]:
        return reject(422, "limit-exceeded", "spec.extensions",
                      f"{count} extensions exceed maxExtensions {limits['maxExtensions']}")
    core = copy.deepcopy(registration)
    if isinstance(core.get("spec"), dict):
        core["spec"].pop("extensions", None)
    errors = sorted(jsonschema.Draft202012Validator(grammar).iter_errors(core),
                    key=lambda e: [str(p) for p in e.absolute_path])
    if errors:
        where = ".".join(str(p) for p in errors[0].absolute_path)
        return reject(422, "invalid-registration", where or None, errors[0].message)
    ids = [e[0] for e in elements(registration)]
    if len(ids) != len(set(ids)):
        return reject(422, "invalid-registration", "spec",
                      "two elements share an id (stateSpans kind, setting or input name)")

    # 4. Elements.
    if same:
        return _accepted(caps, hub_state, submitter, registration, grammar, stored, 200, True)
    after = _store(registration, "active")
    return _accepted(caps, hub_state, submitter, registration, grammar, after,
                     201 if stored is None else 200, False)


# ── the controller's side ─────────────────────────────────────────────

def should_submit(caps, registration):
    """A controller submits only when the hub publishes capabilities, offers
    a submit endpoint for the controller-owned tier, and reads its grammar
    major."""
    if not caps or not registration or not caps.get("submit"):
        return False
    if "controller-owned" not in caps["submit"].get("tiers", ["controller-owned"]):
        return False
    return registration.get("apiVersion") in [v["apiVersion"] for v in caps["grammar"]["versions"]]


ACCEPTED = ("accepted", "accepted-with-ignored-members")


def fallback(registration, response):
    """The controller's write plan. An element is written through the typed
    API only when the response to *this* registration accepted it; anything
    else — rejected, an unknown result, no response, a rejected or retired
    registration, a failed precondition — falls back to the well-known
    carrier."""
    if not registration:
        return None
    results = {}
    if response and response.get("outcome") in ("accepted", "partial"):
        results = {e["element"]: e.get("result") for e in response.get("elements") or []}
    plan = {}
    for eid, _path, _defining, node, kind in elements(registration):
        if results.get(eid) in ACCEPTED:
            plan[eid] = {"write": "typed"}
        elif kind == "stateSpans":
            wire = node.get("wire")
            plan[eid] = {"write": "carrier", "carrier": wire} if wire else {"write": "none"}
        elif kind == "extensions":
            carrier = node.get("carrier")
            plan[eid] = {"write": "carrier", "carrier": carrier} if carrier else {"write": "none"}
        else:
            plan[eid] = {"write": "untyped"}
    return plan


# ── an older controller against a newer hub ───────────────────────────

def _resolve(document, path):
    node = document
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def _matches(discriminator, document):
    if not discriminator:
        return True
    present, value = _resolve(document, discriminator["path"])
    test = discriminator.get("test")
    if test == "exists":
        return present
    if test == "is-object":
        return present and isinstance(value, dict)
    if test == "equals":
        return present and value == discriminator.get("value")
    return False  # an `other` test is the controller's own; a hub cannot evaluate it


def described_by(caps, well_known, writes):
    """For each write of an older controller: the first well-known
    registration (in the capability document's order) whose document
    discriminator, or a kind's wire carrier, matches it."""
    kinds = ((caps or {}).get("wellKnown") or {}).get("kinds") or []
    out = []
    for i, write in enumerate(writes or []):
        hit = {"write": i, "href": None}
        for kind in kinds:
            reg = (well_known or {}).get(kind["href"])
            if not reg:
                continue
            spec = reg["spec"]
            for span in spec.get("stateSpans") or []:
                wire = span.get("wire")
                if wire and wire.get("collection") == write["collection"] and \
                        wire.get("eventType") in (None, write["document"].get("eventType")) and \
                        _matches(wire.get("discriminator"), write["document"]):
                    hit = {"write": i, "href": kind["href"],
                           "element": f"stateSpans/{span.get('kind') or span['category']}"}
                    break
            if hit["href"]:
                break
            for doc in spec.get("documents") or []:
                if doc["collection"] == write["collection"] and doc.get("discriminator") and \
                        _matches(doc["discriminator"], write["document"]):
                    hit = {"write": i, "href": kind["href"]}
                    break
            if hit["href"]:
                break
        out.append(hit)
    return out


def run_case(case, grammar=None):
    """Everything a conformance case's `expected` states, computed."""
    caps, registration, request = case["capabilities"], case["registration"], case["request"]
    response, stored_after = None, None
    if request is not None:
        response, stored_after = negotiate(caps, case.get("hubState"), case.get("submitter") or {},
                                           registration, request, grammar)
    result = {
        "controllerWouldSubmit": should_submit(caps, registration),
        "response": response,
        "fallback": fallback(registration, response),
    }
    if "writes" in case:
        result["describedBy"] = described_by(caps, case.get("wellKnownRegistrations"),
                                             case["writes"])
    if "storedAfter" in case["expected"]:
        result["storedAfter"] = stored_after
    return result
