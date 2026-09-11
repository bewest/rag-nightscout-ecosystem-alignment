"""diff.py — reconcile the observed census against specs/openapi/.

Answers four questions per collection, each of which is a decision the
typed-schema work has to make:

``undeclared``
    Observed in real data, absent from the spec. Candidates to add — the
    tier says with how much confidence, and whether the field belongs in
    the core schema or in an ``x-aid-extensions`` bag.
``unobserved``
    Declared in the spec, never seen in the corpus. Either the corpus is
    missing a client that writes it, or the spec documents something that
    does not exist. Both are worth knowing before generating code from it.
``type_conflict``
    The spec's declared JSON type does not cover every type observed. A
    generated validator would reject real documents at exactly these
    fields; ``rejected_documents`` counts how many.
``constraint_violation``
    Declared enum, ``minimum`` or ``maximum`` that live data breaches.

Integer-vs-number is reported, never silently merged: ``type: integer``
in JSON Schema rejects ``1.5``, and this corpus contains fields where a
majority of values are fractional.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from . import corpus, specload, tiers

# JSON Schema type widening: a value of the observed type is accepted by
# these declared types. ``integer`` is deliberately *not* accepted by
# nothing else — a declared ``number`` accepts an observed ``integer``,
# but a declared ``integer`` does not accept an observed ``number``.
# Nightscout API v3 attaches its own metadata envelope to every document.
# The corpus was collected through ``/api/v1/`` (tools/ns2parquet/ns_fetch.py),
# which does not return these fields, so their absence from the census is a
# property of the collection method and NOT evidence that clients never write
# them. They are reported separately from genuinely unobserved fields.
V3_METADATA = frozenset({
    "identifier", "srvCreated", "srvModified", "subject",
    "isValid", "isReadOnly", "modifiedBy", "app",
})

ACCEPTS = {
    "number": {"number", "integer"},
    "integer": {"integer"},
    "string": {"string"},
    "boolean": {"boolean"},
    "object": {"object"},
    "array": {"array"},
    "null": {"null"},
}


def _covers(declared_types, observed_type):
    if not declared_types:
        return True  # untyped schema node accepts anything
    return any(observed_type in ACCEPTS.get(d, {d}) for d in declared_types)


def reconcile(census, flat, collection):
    total_docs = census["documents"]
    observed = {f["path"]: f for f in census["fields"]}

    undeclared, unobserved, type_conflicts, constraint_violations = [], [], [], []
    enum_unverifiable = []

    for path, field in sorted(observed.items()):
        decl = flat.get(path)
        if decl is None:
            undeclared.append({
                "path": path,
                "tier": field["tier"],
                "tier_reason": field["tier_reason"],
                "docs_present": field["docs_present"],
                "doc_frequency": field["doc_frequency"],
                "site_count": field["site_count"],
                "observed_types": field["types"],
                "distinct_values": (field.get("string") or {}).get("distinct_values"),
            })
            continue

        bad = {t: n for t, n in field["types"].items() if not _covers(decl["types"], t)}
        if bad:
            type_conflicts.append({
                "path": path,
                "tier": field["tier"],
                "declared_types": decl["types"],
                "observed_types": field["types"],
                "uncovered_types": bad,
                "uncovered_values": sum(bad.values()),
                "uncovered_fraction_of_values": round(sum(bad.values()) / field["count"], 6),
                "sites_affected": field["site_count"],
            })

        if decl["enum"] is not None:
            string_info = field.get("string") or {}
            seen = string_info.get("distinct_values")
            if seen is None:
                if string_info:
                    # Not a violation: the census withheld the values, either
                    # because the field is high-cardinality or because too few
                    # independent sites wrote each value to publish it. The
                    # enum may still be wrong; this corpus cannot say.
                    enum_unverifiable.append({
                        "path": path,
                        "declared_enum": decl["enum"],
                        "distinct_values_observed": string_info.get("distinct_value_count"),
                        "reason": string_info.get("value_note", "values withheld"),
                    })
            else:
                if string_info.get("values_withheld"):
                    # The enum is checked only against the values the census
                    # could publish; others existed but were written by too
                    # few sites to corroborate.
                    enum_unverifiable.append({
                        "path": path,
                        "declared_enum": decl["enum"],
                        "distinct_values_observed": string_info.get("distinct_value_count"),
                        "values_published": len(seen),
                        "reason": string_info.get("value_note"),
                    })
                extra = [v for v in seen if v not in set(decl["enum"])]
                if extra:
                    constraint_violations.append({
                        "path": path, "kind": "enum",
                        "declared_enum": decl["enum"],
                        "observed_outside_enum": extra,
                        "docs_present": field["docs_present"],
                    })

        num = field.get("numeric")
        if num:
            if decl["minimum"] is not None and num["min"] < decl["minimum"]:
                constraint_violations.append({
                    "path": path, "kind": "minimum",
                    "declared_minimum": decl["minimum"], "observed_min": num["min"],
                })
            if decl["maximum"] is not None and num["max"] > decl["maximum"]:
                constraint_violations.append({
                    "path": path, "kind": "maximum",
                    "declared_maximum": decl["maximum"], "observed_max": num["max"],
                })

    v3_metadata_absent = []
    for path, decl in sorted(flat.items()):
        if path in observed:
            continue
        record = {
            "path": path,
            "declared_types": decl["types"],
            "required": decl["required"],
            "schema_name": decl["schema_name"],
        }
        if path in V3_METADATA:
            record["note"] = "API v3 metadata; not returned by the v1 endpoint the corpus was collected from"
            v3_metadata_absent.append(record)
        else:
            unobserved.append(record)

    required_missing = []
    for path, decl in sorted(flat.items()):
        if not decl["required"]:
            continue
        field = observed.get(path)
        present = field["docs_present"] if field else 0
        if present < total_docs:
            required_missing.append({
                "path": path,
                "documents_missing_it": total_docs - present,
                "fraction_missing": round((total_docs - present) / total_docs, 6) if total_docs else 1.0,
            })

    return {
        "collection": collection,
        "generated_by": "tools/nsschema/diff.py",
        "spec": specload.ROOT_SCHEMA[collection][0],
        "root_schema": specload.ROOT_SCHEMA[collection][1],
        "documents": total_docs,
        "sites": census["sites"],
        "declared_paths": len(flat),
        "observed_paths": len(observed),
        "summary": {
            "undeclared": len(undeclared),
            "undeclared_by_tier": dict(Counter(u["tier"] for u in undeclared)),
            "unobserved": len(unobserved),
            "v3_metadata_absent": len(v3_metadata_absent),
            "type_conflicts": len(type_conflicts),
            "constraint_violations": len(constraint_violations),
            "enum_unverifiable": len(enum_unverifiable),
            "required_fields_missing_somewhere": len(required_missing),
        },
        "type_conflicts": sorted(type_conflicts, key=lambda c: -c["uncovered_values"]),
        "required_missing": sorted(required_missing, key=lambda r: -r["documents_missing_it"]),
        "constraint_violations": constraint_violations,
        "enum_unverifiable": enum_unverifiable,
        "undeclared": sorted(undeclared, key=lambda u: (tiers.ORDER.index(u["tier"]), -u["docs_present"])),
        "unobserved": unobserved,
        "v3_metadata_absent": v3_metadata_absent,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--census", default="reports/schema-census", type=Path)
    ap.add_argument("--out", default="reports/schema-census", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    collections = args.collections or list(specload.ROOT_SCHEMA)
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    for collection in collections:
        census_path = root / args.census / f"{collection}.census.json"
        if not census_path.is_file():
            print(f"{collection}: no census at {census_path}")
            continue
        census = tiers.annotate(json.loads(census_path.read_text()))
        _, _, flat = specload.load(root, collection)
        result = reconcile(census, flat, collection)
        dest = out_dir / f"{collection}.reconcile.json"
        dest.write_text(json.dumps(result, indent=1) + "\n")
        s = result["summary"]
        print(f"{collection}: {result['observed_paths']} observed vs {result['declared_paths']} declared "
              f"| undeclared={s['undeclared']} unobserved={s['unobserved']} "
              f"(+{s['v3_metadata_absent']} v3-only) "
              f"type_conflicts={s['type_conflicts']} constraints={s['constraint_violations']} "
              f"enum_unverifiable={s['enum_unverifiable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
