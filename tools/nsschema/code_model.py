"""code_model.py — models for the collections nobody has ever measured.

``model.py`` builds a model by merging an OpenAPI declaration with a census
of real deployments. Five of the nine collections cgm-remote-monitor opens
have neither. Their only authority is the server's own source, and this
module reads it — with :mod:`nsschema.jsread`, from the record templates,
index lists and default-role literals in the shipping code — rather than
asking anyone to retype a field list into a spec.

Why not write OpenAPI documents for them and let ``model.py`` merge?
Because that would produce files indistinguishable from the evidence-derived
four. An OpenAPI document is an *assertion about intent*; a census is a
*measurement*. Merging a hand-written assertion into the same pipeline, in
the same directory, under the same filename convention, invites every
downstream consumer to read a guess as a measurement. The existing models'
``evidence`` blocks mean "we counted this in real deployments", and five
collections have nothing to count. So these models carry

* ``provenance: "code"`` on every node and ``"code-derived"`` on the
  document, and **no** ``evidence`` block anywhere;
* ``measured: false`` and an ``evidence_note`` saying so in words;
* ``code_sources`` naming the file and symbol each field came from.

Three things this deliberately refuses to do:

**Invent a type it cannot establish.** A food record written by the built-in
editor arrives form-encoded, so every non-string value in the template is
stored as a string; written as JSON it keeps its type. Those fields get the
union of both types and ``type_undetermined``, because picking one would be
the model asserting something the server does not enforce.

**Invent a shape where there is none.** ``activity`` and the ``settings``
collection have no server-imposed schema at all. Their models say
``open_body`` and stop, which is a different claim from "we did not look".

**Argue a field down the sensitivity scale without evidence.** Labels come
from :mod:`nsschema.sensitivity`, whose rule is that an unlabelled field
defaults to ``identifying``. An uncensused collection is *entirely*
unlabelled, so almost everything here is ``identifying`` and the two bearer
credentials are ``secret``. That is the honest reading.
"""

import argparse
import hashlib
import re
import json
import sys
from pathlib import Path

from . import corpus, jsread, model, sensitivity

# Where the server source is read from, in preference order. The first that
# exists wins; --source overrides. Both are checked to agree under
# --cross-check, because a field set that differs between the working branch
# and released upstream is itself a finding.
SOURCE_ROOTS = (
    "externals/work/crm-seam",
    "externals/cgm-remote-monitor-official",
)

# API v3's document envelope, shared by every collection v3 exposes.
# Declared here rather than extracted because it is spread across five
# operation modules as bare assignments; each entry names the file and the
# statement that establishes it, and SOURCE_ASSERTIONS below fails the drift
# check if any of those statements disappears.
V3_ENVELOPE = {
    "identifier": {
        "types": ["string"],
        "required_write": True,
        "source": "lib/api3/generic/create/validate.js (rejects a non-string identifier)",
        "note": "required by API v3 create; API v1 writes never set it",
    },
    "srvCreated": {
        "types": ["number"],
        "source": "lib/api3/generic/create/insert.js (doc.srvCreated = doc.srvModified)",
        "note": "server-assigned epoch milliseconds",
    },
    "srvModified": {
        "types": ["number"],
        "source": "lib/api3/generic/create/insert.js (doc.srvModified = now.getTime())",
        "note": "server-assigned epoch milliseconds",
    },
    "subject": {
        "types": ["string"],
        "source": "lib/api3/generic/create/insert.js (doc.subject = auth.subject.name)",
        "note": "the auth subject's name, written by the server on v3 create",
    },
    "modifiedBy": {
        "types": ["string"],
        "source": "lib/api3/generic/patch/operation.js (doc.modifiedBy = auth.subject.name)",
        "note": "server-assigned on v3 patch and delete",
    },
    "isValid": {
        "types": ["boolean"],
        "source": "lib/api3/generic/read/operation.js (doc.isValid === false hides the document)",
        "note": "false marks a soft-deleted document; v3 reads skip it",
    },
    "isReadOnly": {
        "types": ["boolean"],
        "source": "lib/api3/generic/update/validate.js (isReadOnly || readOnly || readonly)",
        "note": ("three spellings are honoured — isReadOnly, readOnly and "
                 "readonly — so a model that declares only one is incomplete"),
    },
    "app": {
        "types": ["string"],
        "source": "lib/api3/shared/operationTools.js (rejects a blank app)",
        "note": "client-supplied application name; v3 requires it to be non-blank",
    },
}

# Statements whose disappearance means this module's hand-declared claims no
# longer hold. Checked verbatim, so a refactor that moves or renames them
# fails the drift check rather than silently invalidating a model.
SOURCE_ASSERTIONS = (
    ("lib/api3/generic/create/insert.js", "doc.srvModified = now.getTime();"),
    ("lib/api3/generic/create/insert.js", "doc.srvCreated = doc.srvModified;"),
    ("lib/api3/generic/create/insert.js", "doc.subject = auth.subject.name;"),
    ("lib/api3/generic/create/validate.js", "typeof(doc.identifier) !== 'string'"),
    ("lib/api3/generic/patch/operation.js", "doc.modifiedBy = auth.subject.name;"),
    ("lib/api3/generic/read/operation.js", "doc.isValid === false"),
    ("lib/api3/generic/update/validate.js", "storageDoc.isReadOnly === true"),
    ("lib/api3/index.js", "'enabledCollections'"),
    ("lib/server/env.js", "env.food_collection"),
    ("lib/server/env.js", "env.activity_collection"),
    ("lib/server/env.js", "env.settings_collection"),
    ("lib/server/env.js", "env.authentication_collections_prefix"),
    ("lib/api3/generic/search/operation.js", "col.colName === 'settings'"),
    # The food quick-pick list compares `hidden` to the STRING 'false'. This
    # is the anchor for BF-16; if it changes, the food model's
    # type_undetermined note must be revisited. A regex because the storage
    # seam rewrote the filter's form without changing its meaning: released
    # upstream spells it `{ 'hidden' : 'false' }` and the seam branch
    # `cmp('eq', 'hidden', 'false')`. What must hold in both is the quoted
    # 'false'.
    ("lib/server/food.js", re.compile(r"""['"]hidden['"]\s*[,:]\s*['"]false['"]""")),
    ("lib/food/food.js", "record[key] = record[key] === 'true';"),
    # The admin UI round-trips a subject, access token included, straight
    # back into storage. This is why accessToken is modelled as a field of
    # the stored document and not only as a derived one.
    ("lib/authorization/endpoints.js", "pick(subject, ['_id', 'name', 'accessToken', 'roles'])"),
    ("lib/admin_plugins/subjects.js", "data: subject"),
    ("lib/admin_plugins/roles.js", "data: role"),
)

# Where each collection's index list is declared. Extracted rather than
# transcribed: postgres_emit.py's INDEXED_FIELDS had to be copied by hand
# because nothing could read it, and a transcription is a second declaration
# of the same fact. Reading it makes the DDL emitter's index list and this
# model's index list the same list.
INDEX_SOURCES = {
    "entries": ("lib/server/entries.js", "api.indexedFields"),
    "treatments": ("lib/server/treatments.js", "api.indexedFields"),
    "devicestatus": ("lib/server/devicestatus.js", "api.indexedFields"),
    "profile": ("lib/server/profile.js", "api.indexedFields"),
    "food": ("lib/server/food.js", "api.indexedFields"),
    "activity": ("lib/server/activity.js", "api.indexedFields"),
}

# API v3 rewrites three fields on every document it stores, on every
# collection. None of the three is declared by any OpenAPI document and the
# corpus — 369,419 treatments, 702,254 devicestatus and 896,589 entries over
# eleven sites — contains not one document carrying the ones listed as
# missing below, because those sites write through API v1. The indexes exist
# regardless, so the model must describe what the index indexes.
V3_NORMALISED = {
    "date": {
        "types": ["number"],
        "source": "lib/api3/generic/collection.js (parseDate: doc.date = m.valueOf())",
        "note": ("epoch milliseconds, assigned by API v3 on every write from "
                 "the document's own date or created_at. A v1 write never "
                 "sets it, which is why no document in the corpus has one"),
    },
    "created_at": {
        "types": ["string"],
        "format": "date-time",
        "source": "lib/api3/generic/collection.js (parseDate: doc.created_at = m.toISOString())",
        "note": ("ISO 8601, assigned by API v3 when "
                 "API3_CREATED_AT_FALLBACK_ENABLED is set and DELETED when it "
                 "is not — so on a v3 write this field's presence is a "
                 "deployment setting, not a client decision"),
    },
    "utcOffset": {
        "types": ["number"],
        "source": "lib/api3/generic/collection.js (parseDate: doc.utcOffset = m.utcOffset())",
        "note": "minutes, assigned by API v3 when the document does not carry one",
    },
}

# Indexed paths that no spec declares and no census observed, with the reason
# they are nonetheless real. Everything here is `code` provenance; nothing
# here gets an evidence block.
INDEXED_ONLY = {
    "NSCLIENT_ID": {
        "types": ["number", "string"],
        "type_undetermined": True,
        "type_undetermined_why": (
            "the server never generates or validates it — it stores whatever "
            "a client sends and compares it with an equality filter "
            "(lib/server/websocket.js: query = { NSCLIENT_ID: literal(...) }). "
            "AndroidAPS's own documented sample is an epoch-millisecond "
            "number; nothing constrains it to be one."),
        "source": "lib/server/websocket.js (processSingleDbAdd deduplication)",
        "note": ("a client-assigned deduplication key for the websocket write "
                 "path. When present it is the SOLE match key for an exact "
                 "duplicate, ahead of created_at and eventType, so two "
                 "clients that reuse a value collide"),
    },
    "boluscalc.foods[]._id": {
        "types": ["string"],
        "source": "lib/server/treatments.js (indexedFields) + "
                  "lib/report/reportclient.js (?find[boluscalc.foods._id]=)",
        "note": ("indexed as the MongoDB multikey path "
                 "`boluscalc.foods._id`; written as `boluscalc.foods[]._id` "
                 "here because this model spells an array's item node `[]`. "
                 "No document in the corpus carries a `boluscalc` subtree at "
                 "all, so only the path is modelled, not the subtree."),
        "multikey": True,
        "index_path": "boluscalc.foods._id",
    },
}

# Fields whose derived sensitivity label is wrong and must be raised. Only
# ever *up*: the project's rule is that a field is argued down with evidence,
# and there is no evidence here. Each entry says why.
SENSITIVITY_OVERRIDES = {
    # The denylist already makes this `identifying`, which is the right level.
    # The category is not: `nsclient_id` matches none of the category
    # patterns and falls through to `vocabulary`, which reads as "shared
    # ecosystem term" — the opposite of what this is.
    (None, "NSCLIENT_ID"): (
        "identifying", "identity",
        "a client-assigned key, opaque to the server; AndroidAPS's own "
        "documented sample is a full-precision epoch-millisecond timestamp, "
        "which makes it a quasi-identifier as well as an identifier"),
    ("auth_subjects", "digest"): (
        "secret", "credential",
        "the enclave hash of the subject's _id; the access token is built "
        "from its first 16 characters, so it is token material and not a "
        "mere identifier"),
}

# Collections the server opens whose documents no client form-encodes, so the
# type-widening rule below has nothing to widen. Recorded so that the absence
# of a widening note is a decision rather than an oversight.
FORM_ENCODED_WRITERS = {
    "food": "lib/food/food.js ($.ajax with no contentType)",
    "auth_roles": "lib/admin_plugins/roles.js ($.ajax with no contentType)",
    "auth_subjects": "lib/admin_plugins/subjects.js ($.ajax with no contentType)",
}

WIDEN_WHY = (
    "the stored type depends on the request's content type: {writer} posts "
    "without one, so jQuery form-encodes and every value arrives as a string, "
    "while a JSON caller stores the declared type. The server coerces neither."
)

EMPTY_ARRAY_WHY = (
    "an empty array is dropped entirely by form encoding, so this field can "
    "be absent rather than empty when written by {writer}"
)


class Source:
    """The server source tree, read-only."""

    def __init__(self, root: Path):
        self.root = root
        self._cache = {}

    def text(self, rel: str) -> str:
        if rel not in self._cache:
            path = self.root / rel
            if not path.is_file():
                raise FileNotFoundError(f"{self.root}: missing {rel}")
            self._cache[rel] = path.read_text()
        return self._cache[rel]


def find_source(repo_root: Path, override=None) -> Source:
    """Locate a cgm-remote-monitor checkout.

    ``--source``, then ``$NSSCHEMA_SERVER_SOURCE``, then SOURCE_ROOTS under
    the repository. The env var exists because ``externals/`` is not carried
    into a linked checkout, and a drift check that can only run in one place
    is a drift check nobody runs.
    """
    import os
    candidate = override or os.environ.get("NSSCHEMA_SERVER_SOURCE")
    if candidate:
        root = Path(candidate)
        if not root.is_absolute():
            root = repo_root / root
        if not (root / "lib" / "server" / "env.js").is_file():
            raise FileNotFoundError(f"{root} is not a cgm-remote-monitor checkout")
        return Source(root)
    for rel in SOURCE_ROOTS:
        if (repo_root / rel / "lib" / "server" / "env.js").is_file():
            return Source(repo_root / rel)
    raise FileNotFoundError(
        "no cgm-remote-monitor source found; looked for " + ", ".join(SOURCE_ROOTS)
        + ". Set NSSCHEMA_SERVER_SOURCE or pass --source.")


# ── extraction ───────────────────────────────────────────────────────────

def extract(src: Source) -> dict:
    """Everything read out of the source, as plain data.

    Kept separate from model construction so that the drift check can hash
    *this* — the field sets the source actually declares — rather than the
    rendered model, which also moves when this module's own prose changes.
    """
    food_client = src.text("lib/food/food.js")
    food_server = src.text("lib/server/food.js")
    activity = src.text("lib/server/activity.js")
    auth = src.text("lib/authorization/storage.js")
    endpoints = src.text("lib/authorization/endpoints.js")
    roles_ui = src.text("lib/admin_plugins/roles.js")
    subjects_ui = src.text("lib/admin_plugins/subjects.js")
    api3 = src.text("lib/api3/index.js")

    quickpick = jsread.read_literal(food_client, "quickpickrec_template")
    hidden_const = jsread.read_constant(food_client, "HIDDEN")
    quickpick = {
        k: (hidden_const if isinstance(v, jsread.Ident) and v.name == "HIDDEN" else v)
        for k, v in quickpick.items()
    }

    return {
        "food": {
            "templates": {
                "food": jsread.read_literal(food_client, "foodrec_template"),
                "quickpick": quickpick,
            },
            "units": jsread.read_literal(food_client, "foodunits"),
            "indexed": jsread.read_literal(food_server, "api.indexedFields"),
        },
        "activity": {
            "indexed": jsread.read_literal(activity, "api.indexedFields"),
            "query_opts": jsread.read_literal(activity, "storage.queryOpts"),
        },
        # The two auth collections are extracted separately, even though they
        # share storage.js, so that a change to the default roles does not
        # report drift in the subjects model.
        "auth_roles": {
            "default_roles": jsread.read_literal(auth, "storage.defaultRoles"),
            "indexed": jsread.call_argument(auth, "ctx.store.ensureIndexes", 1),
            "saved": jsread.assigned_properties(auth, "obj"),
            "ui": jsread.assigned_properties(roles_ui, "role"),
            "ui_deleted": jsread.deleted_properties(roles_ui, "role"),
        },
        "auth_subjects": {
            "indexed": jsread.call_argument(auth, "ctx.store.ensureIndexes", 1),
            "saved": jsread.assigned_properties(auth, "obj"),
            "derived": jsread.assigned_properties(auth, "subject"),
            "served": jsread.call_argument(endpoints, "pick", 1),
            "ui": jsread.assigned_properties(subjects_ui, "subject"),
        },
        "api3": {
            "enabled_collections": jsread.keyed_call_argument(
                api3, "app.set", "enabledCollections"),
        },
        "indexes": _extract_indexes(src),
    }


def _extract_indexes(src: Source) -> dict:
    """Every collection's index declaration, with the line that declares it."""
    out = {}
    for collection, (rel, symbol) in INDEX_SOURCES.items():
        text = src.text(rel)
        entries = jsread.read_literal(text, symbol)
        line = jsread.literal_line(text, symbol)
        single = [e for e in entries if isinstance(e, str)]
        compound = [e for e in entries if isinstance(e, dict)]
        paths = list(single)
        for spec in compound:
            for key in spec:
                if key not in paths:
                    paths.append(key)
        out[collection] = {
            "declared_by": f"{rel}:{line}",
            "single": single,
            "compound": compound,
            "paths": paths,
        }
    auth = src.text("lib/authorization/storage.js")
    fields = jsread.call_argument(auth, "ctx.store.ensureIndexes", 1)
    line = jsread.call_line(auth, "ctx.store.ensureIndexes")
    for collection in ("auth_roles", "auth_subjects"):
        out[collection] = {
            "declared_by": f"lib/authorization/storage.js:{line}",
            "single": list(fields),
            "compound": [],
            "paths": list(fields),
        }
    return out


# The source files each collection's fields were read out of, for a reader
# who wants to check the model against the code rather than trust it.
SOURCE_FILES = {
    "food": ["lib/food/food.js", "lib/server/food.js", "lib/api/food/index.js",
             "lib/api3/generic/setup.js"],
    "activity": ["lib/server/activity.js", "lib/api/activity/index.js"],
    "settings": ["lib/api3/generic/setup.js", "lib/api3/index.js",
                 "lib/api3/generic/search/operation.js"],
    "auth_roles": ["lib/authorization/storage.js", "lib/authorization/endpoints.js",
                   "lib/admin_plugins/roles.js"],
    "auth_subjects": ["lib/authorization/storage.js", "lib/authorization/endpoints.js",
                      "lib/admin_plugins/subjects.js"],
}

# Which slices of the extraction each collection's model is built from.
# Per-collection rather than one hash over everything, so that renaming a
# food field reports drift in the food model alone. A check that blamed all
# five would be read as noise within a week.
DIGEST_KEYS = {
    "food": ("food", "api3"),
    "activity": ("activity",),
    "settings": ("api3",),
    "server-indexes": ("indexes",),
    "auth_roles": ("auth_roles",),
    "auth_subjects": ("auth_subjects",),
}


def digest(extracted: dict, collection=None) -> str:
    """A stable hash of what the source declares for one collection.

    Over the extracted field sets, not the source bytes: a comment edit in
    lib/server/food.js must not fail the drift check, and a renamed field
    must. ``collection=None`` hashes the whole extraction.
    """
    if collection is not None:
        extracted = {k: extracted[k] for k in DIGEST_KEYS[collection]}
    blob = json.dumps(_hashable(extracted), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


# Keys that record *where* a declaration is, not *what* it declares. A comment
# added above `indexedFields` moves the line and changes nothing about the
# field set, so hashing it would make the drift check cry wolf — and a check
# that cries wolf gets a `|| true` appended to it within a month.
_LOCATION_KEYS = frozenset({"declared_by", "indexed_by"})


def _hashable(value):
    if isinstance(value, dict):
        return {k: _hashable(v) for k, v in value.items()
                if k not in _LOCATION_KEYS}
    if isinstance(value, list):
        return [_hashable(v) for v in value]
    return value


# ── model construction ───────────────────────────────────────────────────

def _node(tree: model.Node, collection: str, name: str, types, source,
          note=None, **kw) -> model.Node:
    node = tree.child(name, name)
    node.code_derived = True
    node.types = sorted(set(node.types) | set(types))
    if source not in node.code_sources:
        node.code_sources.append(source)
    label = sensitivity.label(name, None)
    override = (SENSITIVITY_OVERRIDES.get((collection, name))
                or SENSITIVITY_OVERRIDES.get((None, name)))
    if override:
        node.sensitivity, node.data_category, node.sensitivity_why = override
    else:
        node.sensitivity = label["sensitivity"]
        node.data_category = label["category"]
        node.sensitivity_why = label["why"]
    if note and note not in node.notes:
        node.notes.append(note)
    for key, value in kw.items():
        setattr(node, key, value)
    return node


def _widen(node: model.Node, writer: str):
    """Apply the content-type rule to one node. String-typed fields are safe."""
    declared = [t for t in node.types if t not in ("string", "object")]
    if not declared:
        return
    if "array" in node.types:
        note = EMPTY_ARRAY_WHY.format(writer=writer)
        if note not in node.notes:
            node.notes.append(note)
        if node.types == ["array"]:
            return
    node.types = sorted(set(node.types) | {"string"})
    node.type_undetermined = True
    node.type_undetermined_why = WIDEN_WHY.format(writer=writer)


def _v3_envelope(tree: model.Node, collection: str):
    for name, spec in V3_ENVELOPE.items():
        _node(tree, collection, name, spec["types"], spec["source"],
              note=spec["note"], required_write=spec.get("required_write", False))


def _id_and_created_at(tree: model.Node, collection: str, source: str, note: str):
    _node(tree, collection, "_id", ["string"], source,
          note="server-assigned when absent; a v1 client may supply a "
               "24-character hex string",
          required_read=True)
    _node(tree, collection, "created_at", ["string"], source, note=note,
          format="date-time", required_read=True)


def build_food(ex: dict, collection="food") -> tuple:
    tree = model.Node(token="", path="")
    tree.types = ["object"]
    writer = FORM_ENCODED_WRITERS[collection]
    templates = ex["food"]["templates"]

    for doc_type, template in templates.items():
        origin = f"lib/food/food.js ({'foodrec' if doc_type == 'food' else 'quickpickrec'}_template)"
        for name, value in template.items():
            if name == "_id":
                continue
            js = jsread.js_type(value)
            node = _node(tree, collection, name, [js] if js else [], origin)
            if doc_type not in node.document_types:
                node.document_types.append(doc_type)
            _widen(node, writer)

    tree.children["type"].enum = sorted(templates)
    tree.children["type"].notes.append(
        "the collection holds two document kinds discriminated by `type`; "
        "the enum is closed by the client source, not by the server, which "
        "stores any value")
    tree.children["unit"].enum = sorted(ex["food"]["units"])
    tree.children["unit"].notes.append(
        "closed by `foodunits` in lib/food/food.js; the server does not check it")
    tree.children["position"].notes.append(
        "the quick-pick editor writes 99999 (its HIDDEN constant) for a "
        "hidden pick and the list index otherwise; form-encoded it is stored "
        "as a string, so the `position` index sorts lexicographically")

    # A quick pick embeds whole food records, plus a per-pick portion count.
    foods = tree.children["foods"]
    foods.types = sorted(set(foods.types) | {"array"})
    items = foods.child("[]", "foods[]")
    items.code_derived = True
    items.types = ["object"]
    items.code_sources.append("lib/food/food.js (dropFood: Object.assign({}, fi, {portions: 1}))")
    items.notes.append(
        "a whole `type: 'food'` record copied into the quick pick, plus "
        "`portions`; edits to the source record do not propagate")
    for name, value in templates["food"].items():
        js = jsread.js_type(value)
        child = _node(items, collection, name, [js] if js else [], items.code_sources[0])
        child.path = f"foods[].{name}"
        _widen(child, writer)
    portions = _node(items, collection, "portions", ["number"], items.code_sources[0])
    portions.path = "foods[].portions"
    _widen(portions, writer)

    _id_and_created_at(
        tree, collection, "lib/server/food.js",
        "v1 create() overwrites created_at on every write; save() sets it "
        "only when absent, so an updated record keeps its original value and "
        "a created one does not")
    _v3_envelope(tree, collection)

    meta = {
        "reached_by": ["v1 /api/v1/food", "v3 /api/v3/food"],
        "document_types": sorted(templates),
        "discriminator": "type",
        "indexed_fields": ex["food"]["indexed"],
        "form_encoded_writer": writer,
    }
    return tree, meta


def build_activity(ex: dict, collection="activity") -> tuple:
    tree = model.Node(token="", path="")
    tree.types = ["object"]
    tree.open_body = True
    _id_and_created_at(
        tree, collection, "lib/server/activity.js",
        "set only when absent, so a client may supply its own")
    meta = {
        "reached_by": ["v1 /api/v1/activity"],
        "not_in_v3": ("absent from lib/api3/index.js's enabledCollections, so "
                      "no v3 route reaches it"),
        "indexed_fields": ex["activity"]["indexed"],
        "date_field": ex["activity"]["query_opts"]["dateField"],
        "open_body": ("the server imposes no schema: it sets created_at and "
                      "_id when absent, runs the write purifier, and stores "
                      "the document wholesale"),
    }
    return tree, meta


def build_settings(ex: dict, collection="settings") -> tuple:
    tree = model.Node(token="", path="")
    tree.types = ["object"]
    tree.open_body = True
    _node(tree, collection, "_id", ["string"], "lib/api3/generic/setup.js",
          note="assigned by the storage layer", required_read=True)
    _v3_envelope(tree, collection)
    meta = {
        "reached_by": ["v3 /api/v3/settings"],
        "not_in_v1": "no v1 route opens this collection",
        "permission": ("search and history demand api:settings:admin rather "
                       "than :read (lib/api3/generic/search/operation.js)"),
        "open_body": ("beyond API v3's envelope the server imposes no schema "
                      "and writes no field of its own; nothing in "
                      "cgm-remote-monitor writes a document here at all"),
        "naming_collision": (
            "reports/schema-census/settings.census.json is NOT a census of "
            "this collection — it captures the GET /api/v1/status.json "
            "response. See specs/nsschema/status.model.json."),
        "proposed_contract": (
            "specs/sync/controller-settings.schema.json proposes what a "
            "document here should look like; it is a proposal, not something "
            "any deployment has been observed to write."),
    }
    return tree, meta


def build_auth_roles(ex: dict, collection="auth_roles") -> tuple:
    auth = ex["auth_roles"]
    tree = model.Node(token="", path="")
    tree.types = ["object"]
    writer = FORM_ENCODED_WRITERS[collection]

    _node(tree, collection, "name", ["string"],
          "lib/authorization/storage.js (defaultRoles) + lib/admin_plugins/roles.js",
          note="indexed; roleToShiro() looks a role up by this name")
    permissions = _node(
        tree, collection, "permissions", ["array"],
        "lib/authorization/storage.js (defaultRoles)",
        note="shiro-trie permission strings; `*` is the wildcard and `:` the "
             "hierarchy separator")
    _widen(permissions, writer)
    items = permissions.child("[]", "permissions[]")
    items.code_derived = True
    items.types = ["string"]
    items.code_sources.append("lib/authorization/storage.js (defaultRoles)")
    label = sensitivity.label("permissions[]", None)
    items.sensitivity, items.data_category, items.sensitivity_why = (
        label["sensitivity"], label["category"], label["why"])
    _node(tree, collection, "notes", ["string"], "lib/admin_plugins/roles.js",
          note="free text from the admin dialog")
    _id_and_created_at(
        tree, collection, "lib/authorization/storage.js",
        "set only when absent, by save(); create() sets it the same way")

    built_in = [r["name"] for r in auth["default_roles"]]
    meta = {
        "reached_by": ["/api/v2/authorization/roles (admin)"],
        "collection_name": "<MONGO_AUTHENTICATION_COLLECTIONS_PREFIX>roles, "
                           "default auth_roles",
        "indexed_fields": auth["indexed"],
        "built_in_roles": built_in,
        "built_in_roles_note": (
            "declared in storage.defaultRoles and merged into the in-memory "
            "role list at every reload, so they are served by "
            "GET /roles without existing as documents. They carry no _id and "
            "no created_at, which is how the admin UI tells them apart."),
        "known_absent_fields": {
            name: ("the admin dialog deletes it before saving and nothing in "
                   "cgm-remote-monitor ever sets it; it is a guard against a "
                   "producer this repository cannot see, so it is recorded "
                   "here rather than modelled as a field")
            for name in auth["ui_deleted"]
        },
        "form_encoded_writer": writer,
    }
    return tree, meta


def build_auth_subjects(ex: dict, collection="auth_subjects") -> tuple:
    auth = ex["auth_subjects"]
    tree = model.Node(token="", path="")
    tree.types = ["object"]
    writer = FORM_ENCODED_WRITERS[collection]

    _node(tree, collection, "name", ["string"],
          "lib/admin_plugins/subjects.js + lib/authorization/storage.js",
          note="indexed; also the input to the access token's readable prefix")
    roles = _node(tree, collection, "roles", ["array"],
                  "lib/admin_plugins/subjects.js",
                  note="role names, resolved against auth_roles and the "
                       "built-in defaults at authorization time")
    _widen(roles, writer)
    items = roles.child("[]", "roles[]")
    items.code_derived = True
    items.types = ["string"]
    items.code_sources.append("lib/admin_plugins/subjects.js")
    label = sensitivity.label("roles[]", None)
    items.sensitivity, items.data_category, items.sensitivity_why = (
        label["sensitivity"], label["category"], label["why"])
    _node(tree, collection, "notes", ["string"], "lib/admin_plugins/subjects.js",
          note="free text from the admin dialog. GET /subjects does not "
               "return it, and the dialog writes back whatever the (empty) "
               "input holds, so an edit through the admin UI clears it")
    _id_and_created_at(
        tree, collection, "lib/authorization/storage.js",
        "set only when absent, by save() and create()")

    derived_note = (
        "recomputed in storage.reload() from the subject's _id, its name and "
        "the enclave API key. The server never writes it, so it is absent "
        "from a freshly created document")
    for name in auth["derived"]:
        node = _node(tree, collection, name, ["string"],
                     "lib/authorization/storage.js (reload)", note=derived_note)
        if name in auth["served"]:
            node.notes.append(
                "GET /subjects returns it and the admin UI PUTs the whole "
                "subject back, so it does reach storage in plaintext when a "
                "subject is edited through the admin UI")
        node.placement = "extension"

    meta = {
        "reached_by": ["/api/v2/authorization/subjects (admin)"],
        "collection_name": "<MONGO_AUTHENTICATION_COLLECTIONS_PREFIX>subjects, "
                           "default auth_subjects",
        "indexed_fields": auth["indexed"],
        "served_fields": auth["served"],
        "credential_warning": (
            "accessToken is the bearer credential that authorises API access. "
            "It is derived at read time, but GET /subjects serves it and the "
            "admin UI PUTs the whole subject back, so it is persisted in "
            "plaintext by an ordinary subject edit. Every field labelled "
            "secret here must be redacted before this collection is exported, "
            "logged, replicated to another tenant, or shown to a support "
            "operator."),
        "form_encoded_writer": writer,
    }
    return tree, meta


INDEX_ARTIFACT = "server-indexes.json"


def build_indexes(ex: dict, src: Source, repo_root: Path) -> dict:
    """What the server indexes, and what the code says each indexed path is.

    Emitted as its own artifact rather than folded into each model because an
    index is a property of the deployment, not of the document, and because
    model.py must be able to read it without the server source being present:
    the committed models must not depend on whether ``externals/`` happens to
    be checked out.

    Every indexed path gets an entry. Whether a model already declares it is
    not decided here — model.py inserts a node only where its tree has none,
    which keeps the merge in the one place that can see the tree.
    """
    collections = {}
    for collection, spec in sorted(ex["indexes"].items()):
        paths = []
        for index_path in spec["paths"]:
            canonical = _canonical(index_path)
            entry = {"index_path": index_path, "model_path": canonical}
            known = INDEXED_ONLY.get(canonical) or V3_NORMALISED.get(canonical)
            if known:
                entry.update({k: v for k, v in known.items()
                              if k not in ("index_path",)})
            else:
                entry["types"] = []
                entry["note"] = (
                    "indexed; whatever this field is, it is described by the "
                    "collection's own model rather than by this file")
            override = (SENSITIVITY_OVERRIDES.get((collection, canonical))
                        or SENSITIVITY_OVERRIDES.get((None, canonical)))
            if override:
                (entry["sensitivity"], entry["data_category"],
                 entry["sensitivity_why"]) = override
            entry["indexed_by"] = spec["declared_by"]
            paths.append(entry)
        collections[collection] = {
            "declared_by": spec["declared_by"],
            "single": spec["single"],
            "compound": spec["compound"],
            "paths": paths,
        }
    return {
        "generated_by": "tools/nsschema/code_model.py",
        "provenance": "code-derived",
        "measured": False,
        "note": (
            "Every field cgm-remote-monitor builds a MongoDB index on, read "
            "out of each module's `indexedFields` literal rather than "
            "transcribed. An index reaches fields no OpenAPI document "
            "declares and no census observed; model.py reads this file and "
            "gives each of those a node with provenance `code`, so a DDL "
            "emitter asking the model for an indexed column finds one. "
            "Nothing here carries an evidence block."),
        "source_root": _relative(src.root, repo_root),
        "source_digest": digest(ex, "server-indexes"),
        "collections": collections,
    }


def _canonical(index_path: str) -> str:
    """MongoDB's dotted index path, in this model's array notation."""
    for path, spec in INDEXED_ONLY.items():
        if spec.get("index_path") == index_path:
            return path
    return index_path


BUILDERS = {
    "food": build_food,
    "activity": build_activity,
    "settings": build_settings,
    "auth_roles": build_auth_roles,
    "auth_subjects": build_auth_subjects,
}

_NOT_MEASURED = (
    "NOT MEASURED. Every field here was read out of cgm-remote-monitor's "
    "source, so it records what the server and its built-in clients CAN "
    "write — not what any deployment DOES write, how often, or on how many "
    "sites. No node in this file carries an evidence block, and none may be "
    "given one without a census to back it."
)

# Why there is no census, per collection. The `settings` case is not the same
# as the others and saying so is the point: a reader who sees
# `settings.census.json` on disk and a model that says "not measured" is owed
# an explanation, or they will assume the model is stale.
_NO_CENSUS_BECAUSE = {
    "food": ("absent from tools/nsschema/corpus.py's COLLECTIONS and from "
             "reports/schema-census/; no snapshot ever fetched it."),
    "activity": ("absent from tools/nsschema/corpus.py's COLLECTIONS and from "
                 "reports/schema-census/; no snapshot ever fetched it."),
    "auth_roles": ("never collected. The corpus is built from public REST "
                   "reads, and these collections are reachable only through "
                   "the admin API."),
    "auth_subjects": ("never collected. The corpus is built from public REST "
                      "reads, and these collections are reachable only "
                      "through the admin API — which is correct: a census of "
                      "them would be a census of bearer credentials."),
    "settings": ("reports/schema-census/settings.census.json exists and is "
                 "NOT a census of this collection. corpus.py collects it from "
                 "each snapshot's settings.json, which is a capture of the "
                 "GET /api/v1/status.json response; its twelve top-level "
                 "fields are the `info` object built in lib/api/status.js. "
                 "That evidence is modelled in "
                 "specs/nsschema/status.model.json. This collection itself "
                 "has never been measured."),
}


def evidence_note(collection: str) -> str:
    return _NOT_MEASURED + " " + _NO_CENSUS_BECAUSE[collection]


def build_document(collection: str, ex: dict, src: Source, repo_root: Path) -> dict:
    tree, meta = BUILDERS[collection](ex)
    doc = {
        "collection": collection,
        "generated_by": "tools/nsschema/code_model.py",
        "provenance": "code-derived",
        "measured": False,
        "evidence_note": evidence_note(collection),
        "source_root": _relative(src.root, repo_root),
        "source_files": SOURCE_FILES[collection],
        "source_digest": digest(ex, collection),
    }
    doc.update(meta)
    doc["root"] = model.to_dict(tree)
    return doc


def _relative(path: Path, repo_root: Path) -> str:
    """The repository-relative name of a source checkout.

    A checkout reached through --source or a linked checkout lives outside
    this repository, but it is still *the same tree* as one of SOURCE_ROOTS.
    The committed model must name it the same way either way, or the model's
    identity would depend on who ran the generator.
    """
    resolved = path.resolve()
    for rel in SOURCE_ROOTS:
        if resolved.as_posix().endswith("/" + rel):
            return rel
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return resolved.name


def check_assertions(src: Source):
    """Statements this module's hand-declared claims depend on."""
    missing = []
    for rel, needle in SOURCE_ASSERTIONS:
        try:
            text = src.text(rel)
        except FileNotFoundError:
            missing.append((rel, "<file missing>"))
            continue
        if hasattr(needle, "search"):
            if not needle.search(text):
                missing.append((rel, f"/{needle.pattern}/"))
        elif needle not in text:
            missing.append((rel, needle))
    return missing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="specs/nsschema", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    ap.add_argument("--source", help="cgm-remote-monitor checkout to read")
    ap.add_argument("--check", action="store_true",
                    help="fail if the source no longer matches the committed models")
    ap.add_argument("--cross-check", action="store_true",
                    help="also require every configured source root to agree")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    src = find_source(root, args.source)
    wanted = args.collections or list(BUILDERS)

    try:
        extracted = extract(src)
    except (KeyError, jsread.JsParseError, FileNotFoundError) as err:
        print(f"cannot read the server source at {src.root}: {err}", file=sys.stderr)
        return 2

    missing = check_assertions(src)
    if missing and not args.check:
        for rel, needle in missing:
            print(f"  WARNING  {rel}: no longer contains {needle!r}")

    if args.cross_check:
        base = src.root.resolve().parent.parent
        search = [root / rel for rel in SOURCE_ROOTS]
        search += [base / rel for rel in SOURCE_ROOTS]
        search += [base.parent / rel for rel in SOURCE_ROOTS]
        seen, others = set(), []
        for path in search:
            resolved = path.resolve()
            if (resolved == src.root.resolve() or resolved in seen
                    or not (resolved / "lib" / "server" / "env.js").is_file()):
                continue
            seen.add(resolved)
            others.append(resolved)
        for other in others:
            other_ex = extract(Source(other))
            if digest(other_ex) != digest(extracted):
                for slice_name in sorted(extracted):
                    if _hashable(other_ex[slice_name]) != _hashable(extracted[slice_name]):
                        print(f"  DIFFERS  in `{slice_name}`")
                print(f"  DIFFERS  {_relative(other, root)} declares a different "
                      f"field set from {_relative(src.root, root)}")
                return 1
            print(f"  agrees   {_relative(other, root)}")

    out_dir = root / args.out
    if args.check:
        failures = []
        for rel, needle in missing:
            failures.append(f"SOURCE   {rel}: no longer contains {needle!r}")
        index_dest = out_dir / INDEX_ARTIFACT
        fresh_indexes = build_indexes(extracted, src, root)
        if not index_dest.is_file():
            failures.append(f"MISSING  {index_dest.relative_to(root)}")
        else:
            stored = json.loads(index_dest.read_text())
            if stored.get("source_digest") != fresh_indexes["source_digest"]:
                failures.append(
                    f"DRIFT    server-indexes: the server declares different "
                    f"indexes than {index_dest.relative_to(root)} records\n"
                    f"           stored {stored.get('source_digest')}\n"
                    f"           source {fresh_indexes['source_digest']}")
            elif _comparable(stored) != _comparable(fresh_indexes):
                failures.append(
                    f"STALE    {index_dest.relative_to(root)} differs from "
                    "what code_model.py now generates")

        for collection in wanted:
            dest = out_dir / f"{collection}.model.json"
            fresh = build_document(collection, extracted, src, root)
            if not dest.is_file():
                failures.append(f"MISSING  {dest.relative_to(root)}")
                continue
            stored = json.loads(dest.read_text())
            if stored.get("source_digest") != fresh["source_digest"]:
                failures.append(
                    f"DRIFT    {collection}: the source declares a different "
                    f"field set than {dest.relative_to(root)} records\n"
                    f"           stored {stored.get('source_digest')}\n"
                    f"           source {fresh['source_digest']}")
            elif _comparable(stored) != _comparable(fresh):
                failures.append(
                    f"STALE    {dest.relative_to(root)} differs from what "
                    "code_model.py now generates")
            elif _located(stored) != _located(fresh):
                print(f"  note     {collection}: a source citation moved "
                      "(a line number, not a field); the model is stale only "
                      "in its citations")
            elif stored.get("source_root") != fresh.get("source_root"):
                print(f"  note     {collection} was generated from "
                      f"{stored.get('source_root')}; this check read "
                      f"{fresh.get('source_root')}, which declares the same "
                      "field set")
        if failures:
            print("\n".join(failures))
            sys.stdout.flush()
            print(f"\n{len(failures)} code-derived model(s) no longer match the "
                  "server source. Run: make schema-code-model", file=sys.stderr)
            return 1
        print(f"{len(wanted)} code-derived models match "
              f"{_relative(src.root, root)}")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    index_doc = build_indexes(extracted, src, root)
    index_dest = out_dir / INDEX_ARTIFACT
    index_dest.write_text(json.dumps(index_doc, indent=1) + "\n")
    supplemented = sum(
        1 for c in index_doc["collections"].values()
        for f in c["paths"] if f["types"])
    print(f"indexes: {len(index_doc['collections'])} collections, "
          f"{supplemented} indexed paths the code describes "
          f"-> {index_dest.relative_to(root)}")

    for collection in wanted:
        doc = build_document(collection, extracted, src, root)
        dest = out_dir / f"{collection}.model.json"
        dest.write_text(json.dumps(doc, indent=1) + "\n")
        fields = len(doc["root"].get("children", {}))
        secret = _count_secret(doc["root"])
        flag = f", {secret} secret" if secret else ""
        print(f"{collection}: {fields} top-level fields (code-derived, "
              f"not measured{flag}) -> {dest.relative_to(root)}")
    print(f"source: {_relative(src.root, root)}")
    return 0


def _comparable(doc: dict) -> dict:
    """The model minus where it happened to be read from.

    `source_root` and every `declared_by` are provenance for a reader, not
    part of the claim: the point of --cross-check is that both checkouts
    declare the same field set, and a comment added above `indexedFields`
    moves a line without changing a thing. A check that failed on either
    would be failing on noise.
    """
    return _hashable({k: v for k, v in doc.items() if k != "source_root"})


def _located(doc):
    """Every `declared_by` citation in a document, for reporting only."""
    found = []

    def walk(value, path=""):
        if isinstance(value, dict):
            for key, sub in value.items():
                if key in _LOCATION_KEYS:
                    found.append((path, sub))
                else:
                    walk(sub, f"{path}.{key}")
        elif isinstance(value, list):
            for i, sub in enumerate(value):
                walk(sub, f"{path}[{i}]")

    walk(doc)
    return sorted(found)


def _count_secret(node: dict) -> int:
    total = 1 if node.get("sensitivity") == "secret" else 0
    for child in (node.get("children") or {}).values():
        total += _count_secret(child)
    return total


if __name__ == "__main__":
    raise SystemExit(main())
