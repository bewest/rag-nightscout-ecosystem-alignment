"""negotiate.py — reference decision function for registration negotiation.

D18 addendum rule 6 (execution plan §2.6.1; queue items SPEC-REG-NEGOTIATE
and SPEC-REG-DECISIONS; contract in the hub-sync design §3.5, schemas
`specs/sync/hub-capabilities.schema.json` and
`specs/sync/registration-submit.schema.json`).

**This is a reference, not a hub.** It exists to show that the conformance
cases under `specs/sync/conformance/` are self-consistent: given a hub's
capability document, its stored registrations, a submitter and a request, it
computes the response the contract requires, and given that response it
computes the controller's write plan (the fallback) and what the controller
does when a typed write is refused. It stores nothing,
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


def etag(registration, state, bound_to=None):
    """Over {registration, state, boundTo}: a change of content, state or
    binding (decision 4's release and transfer) changes it, so two owner
    actions racing on one registration are detected like any other update.
    Credential kind and freed namespaces are outside it."""
    digest = hashlib.sha256(canonical_json(
        {"registration": registration, "state": state, "boundTo": bound_to})).hexdigest()
    return f"sha256:{digest}"


def definition_id(definition):
    """D19 rule 1 (SPEC-REG-INSTANCE): a definition is content-addressed, its
    id `sha256:` and the hex SHA-256 of the RFC 8785 canonical JSON of the
    definition document as submitted."""
    return f"sha256:{hashlib.sha256(canonical_json(definition)).hexdigest()}"


# ── D19 rule 2: one kind at one version has one meaning ───────────────
#
# The members that give a stateSpans kind, an extension and an extension
# field its meaning. Everything else is not meaning: `description`,
# `evidence` and a carrier's `writtenWhen` (prose, at any depth below a
# meaning member), `availability` (a promise level, not a typing),
# `version`/`versions` (the key, and the plan that serves older versions),
# metadata such as `source`, and members the grammar does not define (rule 1:
# a hub does not interpret them, so they cannot carry meaning to it).
SPAN_MEANING = ("category", "kind", "slot", "exclusiveWithinSlot", "coexistsWith", "overlay",
                "supersedes", "states", "endReasons", "wire", "dualWriteLink", "requested",
                "applied", "initiators", "definitions", "acceptsFromHub", "horizon",
                # D20 rule 2 (SPEC-REG-QUIRKS): which shared slot a slot means
                # decides which instances contend, so it is meaning.
                "sameAs")
EXTENSION_MEANING = ("carrier", "dualWriteLink", "horizon", "fields")
FIELD_MEANING = ("name", "type", "typeRef", "unit", "range", "horizon", "sensitivity")
NOT_MEANING = frozenset({"description", "evidence", "writtenWhen"})
# Map-valued members whose keys are data (paths), never member names.
_MEANING_MAPS = frozenset({"vocabularies", "properties"})
# A stateSpans entry that references a well-known kind carries only these.
REFERENCE_MEMBERS = frozenset({"category", "kind", "wellKnownRef", "availability",
                               "description", "evidence"})


def _path(item):
    """A carrier path declared as {path} with no typing member names the same
    field as the bare path string (prose members are not meaning)."""
    if isinstance(item, dict) and set(item) - NOT_MEANING == {"path"}:
        return item["path"]
    return item


def _norm(value, is_map=False):
    """Order carries no meaning: an array of strings compares as a sorted
    list, an array of objects as a sorted list of their canonical forms."""
    if isinstance(value, dict):
        return {k: _norm([_path(i) for i in v] if k == "paths" and isinstance(v, list) else v,
                         k in _MEANING_MAPS)
                for k, v in value.items() if is_map or k not in NOT_MEANING}
    if isinstance(value, list):
        items = [_norm(v) for v in value]
        if all(isinstance(v, str) for v in items):
            return sorted(items)
        return sorted(items, key=canonical_json)
    return value


def meaning(kind, node):
    """The meaning of a stateSpans entry or an extension (already resolved
    from a well-known reference), as a comparable value."""
    if kind == "stateSpans":
        return _norm({k: node[k] for k in SPAN_MEANING if k in node})
    picked = {k: node[k] for k in EXTENSION_MEANING if k in node and k != "fields"}
    fields = {}
    for field in node.get("fields") or []:
        if isinstance(field, dict) and "name" in field:
            fields[field["name"]] = {k: field[k] for k in FIELD_MEANING if k in field}
    picked["fields"] = fields
    return _norm(picked)


def stored_version(node):
    """The version an entry's meaning is declared at: its stored version, or
    a referenced catalogue kind's version; None when it declares none (an
    unversioned kind is one version for this rule)."""
    if isinstance(node.get("wellKnownRef"), dict):
        return node["wellKnownRef"].get("version")
    if isinstance(node.get("versions"), dict):
        return node["versions"].get("stored")
    return node.get("version")


def _catalogue(caps, well_known):
    """The hub's well-known catalogue: id → registration."""
    out = {}
    for entry in ((caps or {}).get("wellKnown") or {}).get("kinds") or []:
        reg = (well_known or {}).get(entry.get("href"))
        if reg and entry.get("id"):
            out[entry["id"]] = reg
    return out


def resolve_reference(caps, well_known, node):
    """The catalogue stateSpans entry a `wellKnownRef` names, or None. A
    catalogue kind is found by its catalogue id and its `kind` (else
    `category`), and has a version only when it declares one: a reference
    names that kind's stored version. The generated well-known registrations
    declare no kind versions, so none of their kinds can be referenced yet."""
    ref = node.get("wellKnownRef")
    if not isinstance(ref, dict):
        return None
    reg = _catalogue(caps, well_known).get(ref.get("catalogue"))
    if not reg:
        return None
    for span in (reg.get("spec") or {}).get("stateSpans") or []:
        if (span.get("kind") or span.get("category")) != ref.get("kind"):
            continue
        version = stored_version(span)
        if version is not None and version == ref.get("version"):
            return span
    return None


def _resolved(caps, well_known, kind, node):
    """The node whose members give an element its meaning and carrier."""
    if kind == "stateSpans" and isinstance(node.get("wellKnownRef"), dict):
        return resolve_reference(caps, well_known, node)
    return node


def product_definitions(hub_state, identity):
    """Every definition stored for (vendor, product): the definitions added
    at <product>/definitions/<id> and the product resource's current
    registration (every definition the hub accepts is also stored
    content-addressed), keyed by definition id."""
    out = {}
    for entry in (hub_state or {}).get("definitions") or []:
        if (entry["identity"]["vendor"], entry["identity"]["product"]) == identity:
            out[entry["definitionId"]] = entry["definition"]
    stored = _find(hub_state, identity)
    if stored is not None and stored.get("registration") is not None:
        out.setdefault(definition_id(stored["registration"]), stored["registration"])
    return out


def version_conflicts(caps, hub_state, well_known, identity, definition):
    """For each stateSpans kind and extension of `definition`: the stored
    definition of the same product that declares the same element at the
    same version with a different meaning, if any."""
    out = {}
    stored = product_definitions(hub_state, identity)
    mine = definition_id(definition)
    for eid, _path, _defining, node, kind in elements(definition):
        if kind not in ("stateSpans", "extensions"):
            continue
        resolved = _resolved(caps, well_known, kind, node)
        if resolved is None:
            continue
        version, wanted = stored_version(node), meaning(kind, resolved)
        for did, other in sorted(stored.items()):
            if did == mine:
                continue
            for oid, _p, _d, onode, okind in elements(other):
                if oid != eid or stored_version(onode) != version:
                    continue
                oresolved = _resolved(caps, well_known, okind, onode)
                if oresolved is not None and meaning(okind, oresolved) != wanted:
                    out.setdefault(eid, did)
    return out


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
        defining = [f"{path}.category"] + ([f"{path}.wellKnownRef"] if "wellKnownRef" in span else [])
        out.append((f"stateSpans/{name}", path, defining, span, "stateSpans"))
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


def _declared_namespaces(registration):
    return list(((registration or {}).get("spec") or {}).get("extensions") or {})


def product_namespaces(hub_state, identity):
    """The namespaces (vendor, product) declares across all its stored
    definitions (D19 rule 1: namespaces belong to the product)."""
    found = []
    for definition in product_definitions(hub_state, identity).values():
        for ns in _declared_namespaces(definition):
            if ns not in found:
                found.append(ns)
    return found


def _identities(hub_state):
    seen = []
    for stored in (hub_state or {}).get("registrations") or []:
        ident = (stored["identity"]["vendor"], stored["identity"]["product"])
        if ident not in seen:
            seen.append(ident)
    for entry in (hub_state or {}).get("definitions") or []:
        ident = (entry["identity"]["vendor"], entry["identity"]["product"])
        if ident not in seen:
            seen.append(ident)
    return seen


def _claimed_elsewhere(hub_state, identity, namespace):
    """First to claim, per tenant (decisions 1 and 2): another product that
    declares the namespace in any of its stored definitions holds it,
    whatever its state, until the owner frees it on that product's
    registration (decision 5)."""
    for other in _identities(hub_state):
        if other == identity:
            continue
        stored = _find(hub_state, other)
        if namespace in ((stored or {}).get("freedNamespaces") or []):
            continue
        if namespace in product_namespaces(hub_state, other):
            return f"{other[0]}/{other[1]}"
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


def has_carrier_mapping(caps, well_known, kind, node):
    """D19 rule 8: a projected view needs a declared mapping — the
    catalogue's carrier for a referenced well-known kind, the kind's `wire`,
    or an extension's `carrier`. Typed settings and replay inputs declare
    none in grammar v1."""
    if kind == "stateSpans":
        resolved = _resolved(caps, well_known, kind, node)
        return bool(resolved and resolved.get("wire"))
    if kind == "extensions":
        return bool(node.get("carrier"))
    return False


def _reference_checks(caps, well_known, node, path):
    """A stateSpans entry with `wellKnownRef` (D19 rule 1) names a kind the
    hub's catalogue has, at a version that kind declares, and restates none
    of its meaning: it carries only category, kind, the reference and
    non-meaning members, and its category and kind are the catalogue's."""
    target = resolve_reference(caps, well_known, node)
    if target is None:
        return [_reason("unknown-well-known-kind", f"{path}.wellKnownRef",
                        "the hub's catalogue has no such kind at that version")]
    extra = sorted(set(node) - REFERENCE_MEMBERS)
    if extra:
        return [_reason("invalid-element", f"{path}.{extra[0]}",
                        "a reference does not restate the referenced kind")]
    if node.get("category") != target.get("category") or \
            node.get("kind", target.get("kind")) != target.get("kind"):
        return [_reason("invalid-element", path,
                        "category and kind must be the referenced kind's")]
    return []


def shared_slots(caps):
    """D20 rule 2: the names of the hub's shared slot list
    (`wellKnown.slots`), empty when it lists none."""
    return [s["name"] for s in (((caps or {}).get("wellKnown") or {}).get("slots") or [])
            if isinstance(s, dict) and s.get("name")]


def _same_as_checks(caps, registration, node, path):
    """D20 rule 2: a stateSpans entry's `sameAs` names a slot of the hub's
    shared slot list (`unknown-shared-slot` otherwise), needs a `slot` with no
    `/`, cannot remap a slot whose own name is a shared slot, and agrees with
    every other entry of the definition naming the same slot."""
    same, slot = node["sameAs"], node.get("slot")
    if not isinstance(slot, str) or not slot or "/" in slot:
        return [_reason("invalid-element", f"{path}.sameAs",
                        "sameAs names the shared slot that this entry's slot means")]
    listed = shared_slots(caps)
    if slot in listed and slot != same:
        return [_reason("invalid-element", f"{path}.sameAs",
                        "a slot whose own name is a shared slot means only itself")]
    for other in (registration.get("spec") or {}).get("stateSpans") or []:
        if other is not node and other.get("slot") == slot and other.get("sameAs") != same:
            return [_reason("invalid-element", f"{path}.sameAs",
                            "entries naming one slot must agree on its sameAs")]
    if same not in listed:
        return [_reason("unknown-shared-slot", f"{path}.sameAs",
                        "the hub's shared slot list has no such slot")]
    return []


def evaluate(caps, hub_state, submitter, registration, grammar, views=None, well_known=None):
    """The per-element results and registration-level ignored members for a
    registration that passed the registration-level checks. `views`: for
    each element id, whether this hub serves older readers a projected
    carrier view of it (`served`, `not-served`); reported on accepted
    elements only, and `served` only for an element with a declared carrier
    mapping (D19 rule 8; otherwise `not-served`). `well_known`: the
    catalogue's registrations by href, for `wellKnownRef`."""
    meta = registration["metadata"]
    identity = (meta["vendor"], meta["product"])
    conflicts = version_conflicts(caps, hub_state, well_known, identity, registration)
    # Decision 1: a submitter with no stated roots may claim any namespace
    # no other registration on the tenant holds; stated roots (a list, even
    # an empty one) restrict it to them.
    roots = submitter.get("namespaceRoots")
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
            if roots is not None and not _owns(roots, ns):
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
        elif kind == "stateSpans" and "wellKnownRef" in node:
            reasons += _reference_checks(caps, well_known, node, path)
        elif kind == "stateSpans" and "sameAs" in node:
            reasons += _same_as_checks(caps, registration, node, path)
        if not reasons and kind in ("stateSpans", "extensions"):
            try:
                sync_model.version_plan(node)
            except (ValueError, KeyError, TypeError) as error:
                reasons.append(_reason("version-plan-invalid", path, str(error)))
        if not reasons and eid in conflicts:
            reasons.append(_reason("version-conflict", path,
                                   f"typed differently at this version by {conflicts[eid]}"))
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
            result = {"element": eid, "result": "accepted-with-ignored-members",
                      "ignored": inside}
        else:
            result = {"element": eid, "result": "accepted"}
        if eid in (views or {}):
            view = views[eid]
            if view == "served" and not has_carrier_mapping(caps, well_known, kind, node):
                view = "not-served"
            result["carrierView"] = view
        results.append(result)
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


# The controller's actions run on the data listener with the device's
# credential; the owner's on the tenant-owner listener (D16), or with
# API_SECRET in single mode (decisions 3 and 5). The owner never edits a
# registration's content, so `submit` is the controller's alone.
CONTROLLER_ACTIONS = ("submit", "retire")
OWNER_ACTIONS = ("retire", "block", "unblock", "release", "transfer", "free-namespaces")
OWNER_LISTENER = "ns-tenant-admin"


def binding_of(submitter):
    """What a registration written by this credential is bound to (decision
    4): its subject, never its token, so rotating a token changes nothing.
    The shared secret has no subject: any holder of it is the same binding."""
    kind = submitter.get("credentialKind")
    if kind == "api-secret":
        return {"kind": "api-secret"}
    return {"kind": kind, "subject": submitter.get("subject")}


def bound_to(stored, submitter):
    """Whether the credential may act as the registration's controller. A
    released registration (bound to nothing) is open to the next credential
    with the permission, which then binds it."""
    bound = stored.get("boundTo")
    return bound is None or canonical_json(bound) == canonical_json(binding_of(submitter))


def owner_authorised(request, submitter):
    if request.get("listener") == OWNER_LISTENER:
        return True
    return request.get("listener") == "single" and submitter.get("credentialKind") == "api-secret"


def _response(status, outcome, **members):
    response = {"apiVersion": GRAMMAR_API, "kind": "RegistrationResponse",
                "status": status, "outcome": outcome}
    response.update({k: v for k, v in members.items() if v is not None})
    return response


def _summary(stored, identity):
    summary = {"vendor": identity[0], "product": identity[1]}
    meta = (stored.get("registration") or {}).get("metadata") or {}
    if "versionRange" in meta:
        summary["versionRange"] = meta["versionRange"]
    summary.update({"state": stored["state"], "etag": stored["etag"]})
    for key in ("blockedFrom", "boundTo", "credentialKind", "bindingEvent"):
        if key in stored:
            summary[key] = stored[key]
    if stored.get("freedNamespaces"):
        summary["freedNamespaces"] = stored["freedNamespaces"]
    return summary


def _current(stored):
    return {"state": stored["state"], "etag": stored["etag"]}


def _find(hub_state, identity):
    for stored in (hub_state or {}).get("registrations") or []:
        if (stored["identity"]["vendor"], stored["identity"]["product"]) == identity:
            return stored
    return None


def _registered(stored):
    return stored is not None and stored.get("registration") is not None


def _stored(identity, registration, state, *, boundTo=None, credentialKind=None,
            blockedFrom=None, freedNamespaces=None, bindingEvent=None):
    """A stored registration, members in a fixed order. The etag covers the
    binding; credential kind, the binding event and freed namespaces are not
    in it. `bindingEvent` (walk-through row 9, 2026-10-16) records how the
    current binding was made when it was not made by the create:
    `next-writer`, a released registration bound by the next permitted
    writer's update. A release or a transfer clears it."""
    out = {"identity": {"vendor": identity[0], "product": identity[1]},
           "state": state, "etag": etag(registration, state,
                                        boundTo if registration is not None else None)}
    if state == "blocked" and blockedFrom is not None:
        out["blockedFrom"] = blockedFrom
    if registration is not None:
        out["boundTo"] = boundTo
        out["credentialKind"] = credentialKind
        if bindingEvent is not None and boundTo is not None:
            out["bindingEvent"] = bindingEvent
    if freedNamespaces:
        out["freedNamespaces"] = list(freedNamespaces)
    out["registration"] = registration
    return out


def _restate(stored, state=None, **changes):
    members = {k: stored.get(k) for k in ("boundTo", "credentialKind", "blockedFrom",
                                          "freedNamespaces", "bindingEvent")}
    members.update(changes)
    identity = (stored["identity"]["vendor"], stored["identity"]["product"])
    return _stored(identity, stored["registration"], state or stored["state"], **members)


def _accepted(caps, hub_state, submitter, registration, grammar, stored_after, status, noop,
              views, well_known=None):
    top, results = evaluate(caps, hub_state, submitter, registration, grammar, views, well_known)
    outcome = "partial" if any(r["result"] == "rejected" for r in results) else "accepted"
    identity = (stored_after["identity"]["vendor"], stored_after["identity"]["product"])
    # D19 rule 1: the response names the id the hub computed for the
    # definition it stored, so a controller can check its own canonical form.
    return _response(status, outcome, noop=noop, definitionId=definition_id(registration),
                     registration=_summary(stored_after, identity),
                     ignored=top, elements=results), stored_after


def negotiate(caps, hub_state, submitter, registration, request, grammar=None, views=None,
              well_known=None):
    """The response a hub with `caps` and `hub_state` gives `request`, and
    the stored registration afterwards (None when none is stored)."""
    grammar = grammar or _load(GRAMMAR_SCHEMA)
    if not caps or not caps.get("submit"):
        raise ValueError("this hub offers no submit endpoint; nothing is negotiated")
    identity = (request["identity"]["vendor"], request["identity"]["product"])
    stored = _find(hub_state, identity)
    if request.get("actor", "controller") == "owner":
        return _owner(submitter, request, identity, stored, hub_state)
    return _controller(caps, hub_state, submitter, registration, request, grammar, views,
                       identity, stored, well_known)


def _rejecter(stored):
    def reject(status, code, path=None, detail=None):
        return _response(status, "rejected", reasons=[_reason(code, path, detail)]), stored

    def failed(status, code, detail=None):
        return _response(status, "precondition-failed", reasons=[_reason(code, None, detail)],
                         current=_current(stored) if stored else None), stored
    return reject, failed


def _controller(caps, hub_state, submitter, registration, request, grammar, views,
                identity, stored, well_known=None):
    action = request["action"]
    pre = request.get("preconditions") or {}
    reject, failed = _rejecter(stored)
    registered = _registered(stored)

    # 1. Authorisation: the permission, then the binding (decision 4). A
    # different subject, or API_SECRET against a subject-bound registration,
    # is refused before any precondition is evaluated.
    if action not in CONTROLLER_ACTIONS:
        return reject(403, "not-authorised", None, f"only the tenant owner may {action}")
    if not permitted(submitter.get("permissions"), PERMISSION[action]):
        return reject(403, "not-authorised", None, f"needs {PERMISSION[action]}")
    if registered and not bound_to(stored, submitter):
        return reject(403, "not-registration-owner", None,
                      "the registration is bound to another credential")

    # 2. Preconditions (RFC 9110 §13.2.1: after authorisation, before the content).
    if not pre:
        return failed(428, "precondition-required", "send If-None-Match: * or If-Match")
    if action == "retire":
        if not registered:
            return _response(404, "not-found", reasons=[_reason("not-found")]), stored
        if "ifMatch" not in pre:
            return failed(412, "registration-exists", "retire needs If-Match")
        if pre["ifMatch"] != stored["etag"]:
            return failed(412, "stale-etag")
        if stored["state"] == "blocked":
            return reject(403, "blocked-by-owner")
        return _retire(stored, identity)

    same = registered and stored["state"] == "active" and \
        canonical_json(stored["registration"]) == canonical_json(registration)
    if "ifNoneMatch" in pre and registered and not same:
        return failed(412, "registration-exists")
    if "ifMatch" in pre:
        if not registered:
            return failed(412, "not-found")
        if pre["ifMatch"] != stored["etag"] and not same:
            return failed(412, "stale-etag")
    # The owner's block (decision 5), after the preconditions: a controller
    # holding the etag from before the block gets 412 and reads `blocked`.
    # A pre-emptive block stores no registration, so a create's
    # If-None-Match: * passes and the block answers.
    if stored is not None and stored["state"] == "blocked":
        return reject(403, "blocked-by-owner")

    # 3. Registration-level content checks.
    refusal = content_refusal(caps, registration, identity, grammar, reject)
    if refusal is not None:
        return refusal

    # 4. Elements. A write binds an unbound registration to the writer and
    # records the writer's credential kind (decisions 3 and 4).
    if same and stored.get("boundTo") is not None:
        return _accepted(caps, hub_state, submitter, registration, grammar, stored, 200, True,
                         views, well_known)
    # A namespace the owner freed stays freed while another registration
    # holds it; otherwise this registration claims it again.
    freed = [ns for ns in (stored or {}).get("freedNamespaces") or []
             if ns in _declared_namespaces(registration)
             and _claimed_elsewhere(hub_state, identity, ns)]
    # Row 9 (2026-10-16): a released registration is bound by its next
    # permitted writer, and the listing shows that binding event; an update
    # by the same binding keeps the event that made it.
    if registered and stored.get("boundTo") is None:
        event = "next-writer"
    elif registered:
        event = stored.get("bindingEvent")
    else:
        event = None
    after = _stored(identity, registration, "active", boundTo=binding_of(submitter),
                    credentialKind=submitter.get("credentialKind"), freedNamespaces=freed,
                    bindingEvent=event)
    return _accepted(caps, hub_state, submitter, registration, grammar, after,
                     201 if not registered else 200, False, views, well_known)


def content_refusal(caps, registration, identity, grammar, reject):
    """Step (3), the registration as a whole; also applied to a definition
    added at <product>/definitions/<id> (D19). None when it passes."""
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
    return None


def _retire(stored, identity):
    if stored["state"] == "retired":
        return _response(200, "retired", noop=True, registration=_summary(stored, identity),
                         elements=[]), stored
    after = _restate(stored, "retired")
    return _response(200, "retired", noop=False, registration=_summary(after, identity),
                     elements=[]), after


def _owner(submitter, request, identity, stored, hub_state=None):
    """The tenant owner's actions (decision 5): retire, block, unblock,
    release, transfer, and free a retired registration's namespaces; never
    edit content. Each carries exactly one precondition."""
    action = request["action"]
    pre = request.get("preconditions") or {}
    reject, failed = _rejecter(stored)
    registered = _registered(stored)

    def applied(status, after, noop):
        summary = _summary(after, identity) if after is not None else None
        return _response(status, "applied", noop=noop, registration=summary), after

    # 1. Authorisation.
    if action not in OWNER_ACTIONS:
        return reject(403, "not-authorised", None, "the owner never edits a registration")
    if not owner_authorised(request, submitter):
        return reject(403, "not-authorised", None,
                      "owner actions are on ns-tenant-admin, or API_SECRET in single mode")

    # 2. Preconditions.
    if not pre:
        return failed(428, "precondition-required", "send If-None-Match: * or If-Match")
    if action == "block" and stored is None:
        if "ifNoneMatch" not in pre:
            return failed(412, "not-found")
        # A pre-emptive block: nothing is registered, the identity is refused.
        return applied(201, _stored(identity, None, "blocked"), False)
    if stored is None or (not registered and action not in ("block", "unblock")):
        return _response(404, "not-found", reasons=[_reason("not-found")]), stored
    if "ifMatch" not in pre:
        return failed(412, "registration-exists", f"{action} needs If-Match")
    if pre["ifMatch"] != stored["etag"]:
        return failed(412, "stale-etag")

    # 3. The action.
    if action == "block":
        if stored["state"] == "blocked":
            return applied(200, stored, True)
        return applied(200, _restate(stored, "blocked", blockedFrom=stored["state"]), False)
    if action == "unblock":
        if stored["state"] != "blocked":
            return applied(200, stored, True)
        if not registered:
            return applied(200, None, False)
        # Unblocking restores the state the block interrupted: a registration
        # retired before the block stays retired.
        return applied(200, _restate(stored, stored["blockedFrom"], blockedFrom=None), False)
    if action == "retire":
        if stored["state"] == "blocked":
            return reject(409, "blocked-by-owner", None, "unblock before retiring")
        return _retire(stored, identity)
    if action == "release":
        if stored.get("boundTo") is None:
            return applied(200, stored, True)
        return applied(200, _restate(stored, boundTo=None, bindingEvent=None), False)
    if action == "transfer":
        target = request["transferTo"]
        if canonical_json(stored.get("boundTo")) == canonical_json(target):
            return applied(200, stored, True)
        return applied(200, _restate(stored, boundTo=target, bindingEvent=None), False)
    # free-namespaces
    if stored["state"] != "retired":
        return reject(409, "not-retired", None, "only a retired registration's namespaces are freed")
    # Namespaces belong to the product (D19 rule 1): every stored definition's.
    declared = product_namespaces(hub_state or {"registrations": [stored]}, identity)
    if sorted(stored.get("freedNamespaces") or []) == sorted(declared):
        return applied(200, stored, True)
    return applied(200, _restate(stored, freedNamespaces=declared), False)


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
CARRIER_VIEWS = ("served", "not-served")


def _not_accepted(kind, node, caps=None, well_known=None):
    """The element's well-known carrier. A kind that references a well-known
    kind (D19 rule 1) writes the catalogue kind's carrier."""
    if kind == "stateSpans" and "wellKnownRef" in node:
        node = resolve_reference(caps, well_known, node) or {}
    if kind == "stateSpans":
        wire = node.get("wire")
        return {"write": "carrier", "carrier": wire} if wire else {"write": "none"}
    if kind == "extensions":
        carrier = node.get("carrier")
        return {"write": "carrier", "carrier": carrier} if carrier else {"write": "none"}
    return {"write": "untyped"}


def fallback(registration, response, caps=None, well_known=None):
    """The controller's write plan. An element is written through the typed
    API only when the response to *this* registration accepted it; anything
    else — rejected, an unknown result, no response (including a submit
    answered 429 or any 5xx), a rejected, retired or blocked registration, a
    failed precondition — falls back to the well-known carrier.

    An accepted element is written typed only, unless the hub serves no
    projected carrier view of it and it declares a dual-write link: then
    typed and carrier, linked (decision 7). A `carrierView` the controller
    does not know is not accepted (rule 3)."""
    if not registration:
        return None
    results = {}
    if response and response.get("outcome") in ("accepted", "partial"):
        results = {e["element"]: e for e in response.get("elements") or []}
    plan = {}
    for eid, _path, _defining, node, kind in elements(registration):
        result = results.get(eid) or {}
        view = result.get("carrierView", "not-served")
        if result.get("result") not in ACCEPTED or view not in CARRIER_VIEWS:
            plan[eid] = _not_accepted(kind, node, caps, well_known)
            continue
        carrier = _not_accepted(kind, node, caps, well_known)
        if view == "not-served" and node.get("dualWriteLink") and carrier["write"] == "carrier":
            plan[eid] = {"write": "typed-and-carrier", "carrier": carrier["carrier"],
                         "link": node["dualWriteLink"]}
        else:
            plan[eid] = {"write": "typed"}
    return plan


# Decision 8 (amended 2026-10-15; delivery deadline removed 2026-10-16,
# maintainer walk-through row 8). A typed write refused for load — 429 or
# any 5xx, since a server or gateway error says nothing about whether the
# element is accepted — is retried with backoff (after Retry-After when
# sent) until it succeeds; the record is not dropped, the write plan does
# not change, and the record is never re-sent as its carrier, so a write
# the hub stored before failing cannot appear twice. *(Removed 2026-10-16:
# a record still unwritten when its delivery deadline passed was sent as
# its carrier; the deadline was added 2026-10-15 without being asked for.)*
# Any other refusal is definite — blocked-by-owner, a retired or missing
# registration, a typed route answering 404 after a hub rollback, or a 4xx
# the controller does not know (rule 3) — and sends that record as its
# carrier at once; the element is not accepted until the next re-check. A
# refusal never triggers a re-check: the controller re-reads the capability
# document and its registration at launch and after a controller release.
def is_load_refusal(status):
    return status == 429 or 500 <= status <= 599


def typed_write_refused(registration, plan, refusal, caps=None, well_known=None):
    """What the controller does when one typed write for `refusal.element`
    is refused, and its write plan afterwards."""
    eid = refusal["element"]
    if plan.get(eid, {}).get("write") not in ("typed", "typed-and-carrier"):
        raise ValueError(f"{eid} is not written typed; no typed write was refused")
    after = copy.deepcopy(plan)
    if is_load_refusal(refusal["status"]):
        outcome = {"action": "retry-backoff", "recheck": False}
        if "retryAfter" in refusal:
            outcome["retryAfterSeconds"] = refusal["retryAfter"]
    else:
        outcome = {"action": "carrier-this-record", "recheck": False}
        node, kind = next((e[3], e[4]) for e in elements(registration) if e[0] == eid)
        after[eid] = _not_accepted(kind, node, caps, well_known)
    outcome["fallback"] = after
    return outcome


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
                                           registration, request, grammar,
                                           case.get("carrierViews"),
                                           case.get("wellKnownRegistrations"))
    result = {
        "controllerWouldSubmit": should_submit(caps, registration),
        "response": response,
        "fallback": fallback(registration, response, caps, case.get("wellKnownRegistrations")),
    }
    if "typedWrite" in case:
        result["typedWrite"] = typed_write_refused(registration, result["fallback"],
                                                   case["typedWrite"])
    if "writes" in case:
        result["describedBy"] = described_by(caps, case.get("wellKnownRegistrations"),
                                             case["writes"])
    if "storedAfter" in case["expected"]:
        result["storedAfter"] = stored_after
    return result
