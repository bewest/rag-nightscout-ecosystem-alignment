"""model.py — the reconciled schema model: one source, many consumers.

Builds a single intermediate representation per collection by merging what
``specs/openapi/`` declares with what ``census.py`` observed, under an
explicit, recorded policy. Every emitter (JSON Schema, zod, mongoose,
PyArrow) reads this IR and nothing else, which is what makes "one source of
truth, four generated consumers" (multitenancy discussion §6.4) true rather
than aspirational.

Paths are tokenised so that structure is explicit:

    store.{}.basal[].value  ->  ['store', '{}', 'basal', '[]', 'value']

``[]`` is an array's item node, ``{}`` is a map's value node. The IR is a
trie over those tokens; each node carries its merged type set, provenance,
evidence and policy decisions.

Two *profiles* are produced, because a Nightscout document does not have
one contract:

``write``
    What a client must and may send. ``_id`` and the API v3 server
    metadata are not required — the server assigns them. Required fields
    are only those a document is meaningless without.
``read``
    What a consumer may rely on receiving. Fields observed in essentially
    every document on every site are required here even though a client
    never sends them, because the server always returns them.

Conflating the two is how a validator ends up rejecting legitimate writes
(demanding ``_id``) or letting consumers assume a field that is sometimes
absent.
"""

import json
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Dict, List, Optional

from . import corpus, sensitivity, specload, tiers

# Server-assigned; a client never sends these, every reader receives them.
SERVER_ASSIGNED = frozenset({
    "_id", "identifier", "srvCreated", "srvModified", "subject",
    "isValid", "isReadOnly", "modifiedBy", "app",
})

# Tiers that belong in the typed core schema. Everything weaker is real but
# is not something a generated type should commit to; see docs on the
# x-aid-extensions convention.
CORE_TIERS = frozenset({"universal", "core", "common"})


def tokenize(path: str) -> List[str]:
    """'store.{}.basal[].value' -> ['store','{}','basal','[]','value']"""
    tokens: List[str] = []
    for segment in path.split("."):
        while segment.endswith("[]"):
            segment = segment[:-2]
            tokens.append(None)  # placeholder, filled below
        # placeholders were appended in reverse; rebuild in order
        depth = 0
        while tokens and tokens[-1] is None:
            tokens.pop()
            depth += 1
        tokens.append(segment)
        tokens.extend(["[]"] * depth)
    return tokens


@dataclass
class Node:
    token: str
    path: str = ""
    types: List[str] = dc_field(default_factory=list)
    children: Dict[str, "Node"] = dc_field(default_factory=dict)
    # provenance
    declared: bool = False
    observed: bool = False
    # evidence
    tier: Optional[str] = None
    tier_reason: str = ""
    docs_present: int = 0
    doc_frequency: float = 0.0
    site_count: int = 0
    observed_types: Dict[str, int] = dc_field(default_factory=dict)
    # constraints
    enum: Optional[List[str]] = None
    enum_declared: Optional[List[str]] = None
    enum_observed: Optional[List[str]] = None
    observed_values: Optional[List[str]] = None
    values_withheld: int = 0
    distinct_value_count: int = 0
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    format: Optional[str] = None
    description: str = ""
    nullable: bool = False
    declared_integer: bool = False
    # policy outcome
    sensitivity: Optional[str] = None
    data_category: Optional[str] = None
    sensitivity_why: str = ""
    placement: str = "core"      # core | extension
    required_write: bool = False
    required_read: bool = False
    candidate_required_write: bool = False
    declared_required: bool = False
    notes: List[str] = dc_field(default_factory=list)

    def child(self, token: str, path: str) -> "Node":
        if token not in self.children:
            self.children[token] = Node(token=token, path=path)
        return self.children[token]


def _insert(root: Node, path: str) -> Node:
    node = root
    walked = []
    for token in tokenize(path):
        walked.append(token)
        node = node.child(token, _join(walked))
    return node


def _join(tokens: List[str]) -> str:
    out = ""
    for token in tokens:
        if token == "[]":
            out += "[]"
        elif not out:
            out = token
        else:
            out += "." + token
    return out


def build(census: dict, flat: dict, collection: str) -> Node:
    """Merge census evidence and spec declarations into one IR tree."""
    root = Node(token="", path="")
    root.types = ["object"]

    for record in census["fields"]:
        node = _insert(root, record["path"])
        node.observed = True
        node.observed_types = dict(record["types"])
        node.tier = record["tier"]
        node.tier_reason = record["tier_reason"]
        node.docs_present = record["docs_present"]
        node.doc_frequency = record["doc_frequency"]
        node.site_count = record["site_count"]
        node.nullable = "null" in record["types"]
        label = sensitivity.label(record["path"], record)
        node.sensitivity = label["sensitivity"]
        node.data_category = label["category"]
        node.sensitivity_why = label["why"]
        observed = [t for t in record["types"] if t != "null"]
        node.types = sorted(set(node.types) | set(observed))
        string_info = record.get("string") or {}
        node.values_withheld = string_info.get("values_withheld", 0)
        node.distinct_value_count = string_info.get("distinct_value_count", 0)
        if string_info.get("distinct_values"):
            node.enum_observed = string_info["distinct_values"]
        elif string_info:
            # Values exist but were withheld; record that so the enum policy
            # below can refuse to enforce a constraint it cannot verify.
            node.values_withheld = max(
                node.values_withheld, node.distinct_value_count)

    for path, decl in flat.items():
        node = _insert(root, path)
        node.declared = True
        if node.sensitivity is None:
            # Declared but never observed: unlabelled defaults to identifying.
            label = sensitivity.label(path, None)
            node.sensitivity = label["sensitivity"]
            node.data_category = label["category"]
            node.sensitivity_why = label["why"]
        node.declared_integer = "integer" in decl["types"]
        node.types = sorted(set(node.types) | set(decl["types"]))
        node.declared_required = decl["required"]
        node.enum_declared = decl["enum"]
        node.minimum = decl["minimum"]
        node.maximum = decl["maximum"]
        node.format = decl["format"]
        node.description = decl["description"] or node.description

    _apply_policy(root, len(census["sites"]))
    return root


def _apply_policy(root: Node, total_sites: int):
    for name, node in root.children.items():
        _policy_node(node, name, depth=1)


def _policy_node(node: Node, name: str, depth: int):
    # Type set. JSON Schema `number` already accepts an integer, so a set
    # holding both collapses to `number`. The note fires only when the
    # *spec* said `integer` and the data is fractional — that is the case a
    # generated validator would reject, and the single largest class of
    # spec/data disagreement in this corpus.
    spec_said_integer = node.declared_integer
    fractional = node.observed_types.get("number", 0)
    if "integer" in node.types and "number" in node.types:
        node.types = sorted(set(node.types) - {"integer"})
    if spec_said_integer and fractional:
        node.types = sorted(set(node.types) - {"integer"} | {"number"})
        node.notes.append(
            f"widened integer -> number: the spec declares integer and "
            f"{fractional:,} fractional values were observed"
        )
    if node.nullable:
        node.notes.append("nullable: null observed in live documents")

    # Enum. An enum is a *closed set*, and observation can never establish
    # that a set is closed — the census records at most MAX_DISTINCT values
    # from one corpus, so a field like loop.version would acquire a
    # spurious enum of the eight versions that happened to appear. So an
    # enum exists only where the spec declares one; observation can extend
    # it (the corpus holds values no declared enum lists) but never create
    # it. Observed values are still carried as documentation.
    if node.enum_observed:
        node.observed_values = list(node.enum_observed)
    if node.enum_declared:
        if node.values_withheld:
            # The census saw values it could not publish (privacy: written by
            # too few independent sites to corroborate). We therefore know the
            # observed vocabulary is larger than what we can check the declared
            # enum against — and an enum known to be incomplete is worse than
            # no enum, because it rejects real documents. Drop the constraint
            # and say why; `enum_unverifiable` in the reconciliation carries
            # the same information for a reviewer.
            node.enum = None
            node.notes.append(
                f"declared enum not enforced: {node.values_withheld} of "
                f"{node.distinct_value_count} observed values could not be "
                "published, so the enum cannot be shown to be complete"
            )
        else:
            extra = sorted(set(node.enum_observed or []) - set(node.enum_declared))
            node.enum = sorted(set(node.enum_declared) | set(extra))
            if extra:
                node.notes.append(
                    f"enum extended by observation: {', '.join(extra)} — present in "
                    "live data but absent from the declared enum"
                )

    # Placement. Weak evidence does not earn a typed core field.
    if node.declared:
        node.placement = "core"
    elif node.tier in CORE_TIERS:
        node.placement = "core"
        node.notes.append(f"proposed addition from evidence ({node.tier_reason})")
    else:
        node.placement = "extension"
        node.notes.append(f"extension-bag candidate ({node.tier_reason})")

    # Required. Only at the document's top level; nested required is a
    # separate question this corpus cannot settle for optional subtrees.
    #
    # `required_read` is evidence-based: a consumer may rely on a field the
    # server returns in every document on every site. `required_write` is
    # deliberately *not* evidence-based — this corpus is Loop-dominant
    # (9 of 11 sites), so a field universal here may simply be one Loop
    # always sends. A new write requirement would reject other clients'
    # documents, so it is only asserted where the spec already requires the
    # field and the data agrees. Universal-but-undeclared fields are
    # surfaced as candidates instead of being enforced.
    if depth == 1 and node.tier == "universal":
        node.required_read = True
        if name in SERVER_ASSIGNED:
            node.notes.append("server-assigned: required on read, never on write")
        elif node.declared_required:
            node.required_write = True
        else:
            node.candidate_required_write = True
            node.notes.append(
                "universal in this corpus but not declared required; a write "
                "requirement is not asserted from a Loop-dominant corpus"
            )

    for child_name, child in node.children.items():
        _policy_node(child, child_name, depth + 1)


def to_dict(node: Node) -> dict:
    out = {
        "path": node.path,
        "types": node.types,
        "nullable": node.nullable,
        "declared": node.declared,
        "observed": node.observed,
        "placement": node.placement,
    }
    for key in ("sensitivity", "data_category", "sensitivity_why",
                "tier", "tier_reason", "format", "description"):
        if getattr(node, key):
            out[key] = getattr(node, key)
    if node.observed:
        out["evidence"] = {
            "docs_present": node.docs_present,
            "doc_frequency": node.doc_frequency,
            "site_count": node.site_count,
            "observed_types": node.observed_types,
        }
    if node.enum:
        out["enum"] = node.enum
    if node.observed_values and not node.enum:
        # Documentation, not a constraint: the values this field was seen to
        # take in one corpus, which does not make the set closed.
        out["observed_values"] = node.observed_values
    for key in ("minimum", "maximum"):
        if getattr(node, key) is not None:
            out[key] = getattr(node, key)
    if node.required_read:
        out["required_read"] = True
    if node.required_write:
        out["required_write"] = True
    if node.candidate_required_write:
        out["candidate_required_write"] = True
    if node.notes:
        out["notes"] = node.notes
    if node.children:
        out["children"] = {k: to_dict(v) for k, v in sorted(node.children.items())}
    return out


def load(repo_root: Path, collection: str, census_dir="reports/schema-census") -> Node:
    census_path = repo_root / census_dir / f"{collection}.census.json"
    census = tiers.annotate(json.loads(census_path.read_text()))
    _, _, flat = specload.load(repo_root, collection)
    return build(census, flat, collection)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="specs/nsschema", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    for collection in (args.collections or list(specload.ROOT_SCHEMA)):
        tree = load(root, collection)
        doc = {
            "collection": collection,
            "generated_by": "tools/nsschema/model.py",
            "source_spec": specload.ROOT_SCHEMA[collection][0],
            "census": f"reports/schema-census/{collection}.census.json",
            "root": to_dict(tree),
        }
        dest = out_dir / f"{collection}.model.json"
        dest.write_text(json.dumps(doc, indent=1) + "\n")
        print(f"{collection}: {len(tree.children)} top-level fields -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
