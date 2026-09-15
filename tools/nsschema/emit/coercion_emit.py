"""coercion_emit.py — the query-coercion table, emitted from the model.

WHY THIS IS AN EMITTER AND NOT A PATCH TO ``query.js``

``lib/server/query.js`` turns an HTTP query string into a filter, and every
value in a query string arrives as **text**. Deciding that ``find[sgv][$gte]=120``
means the number 120 and not the string "120" requires knowing the field's
type, and Nightscout's answer today is a hand-maintained per-collection
``walker`` dict that is not derived from any schema. It is wrong in three
measurable ways (see the backfix register, BF-02 and BF-03):

  * **over-coercion** — ``insulin`` and ``carbs`` are ``parseInt`` while the
    model declares both ``number``, so a query for boluses >= 1.5 U returns
    boluses of 1.0 U;
  * **under-coercion** — ``devicestatus``, ``activity`` and ``food`` have no
    walker at all, so every numeric filter on them stays a string, matches
    nothing, and returns HTTP 200;
  * **drift** — it is a fourth list beside the OpenAPI spec, ``indexedFields``
    and the nsschema model, with nothing keeping them in agreement.

So the fix is not "correct the walker" but "stop hand-maintaining it". This
emitter is the sixth beside ``mongoose_emit``, ``zod_emit``,
``jsonschema_emit``, ``pyarrow_emit`` and ``fieldref_emit``.

WHAT IT EMITS, AND WHY IT IS A TYPE RATHER THAN A FUNCTION

The table names a **type**, never a coercion function. Two reasons, both
load-bearing:

  1. **It must serve two backends.** Decision D4 makes MongoDB permanent for
     single-tenant while D3 puts the hosted service on PostgreSQL, so coercion
     sits *above* the storage seam and feeds both. A table of ``parseInt``
     references would be a table of one backend's opinions.
  2. **The consumer owns the edge cases.** "number" and "integer" are facts
     about the field; whether a malformed value becomes ``NaN``, a 400, or is
     dropped is a policy decision for the query layer, and baking it in here
     would hide it.

``nullable`` is emitted alongside, and it is not decoration. Three-arm
validation found that comparisons against ``null`` are exactly where the two
backends diverge, so a query layer needs to know that ``null`` is a legitimate
value for a field rather than a failed coercion.

  docs/60-research/seam-filter-ast-three-arm-validation-2026-09-14.md

USAGE

    python -m tools.nsschema.emit.coercion_emit
    python -m tools.nsschema.emit.coercion_emit --drift     # compare vs the shipping walkers
"""

import json

# Model type names -> the coercion kind a query layer needs. Anything not
# listed is left uncoerced ON PURPOSE: an object or array bound in a query
# string is not a shape this table can honestly describe, and guessing is how
# the walker got wrong in the first place.
TYPE_KIND = {
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "string": "string",
}

# Fields whose declared type is a string but which the server treats as a
# moment in time. Kept as an explicit, reviewable list rather than inferred
# from the name, because "date-like name" is a guess and this is the field
# that decides whether a two-day window bounds anything (BF-01).
DATELIKE = {"created_at", "sysTime", "srvModified", "srvCreated", "startDate", "dateString"}


def _flatten(node, prefix=""):
    """Every leaf path in the model, dotted. Array and map wildcards are
    skipped: a query string cannot address them, so a coercion entry for one
    would never be consulted."""
    out = []
    for name, child in sorted(node.get("children", {}).items()):
        if name in ("[]", "{}"):
            continue
        path = f"{prefix}.{name}" if prefix else name
        kids = {k: v for k, v in child.get("children", {}).items() if k not in ("[]", "{}")}
        if kids:
            out.extend(_flatten(child, path))
        else:
            out.append((path, child))
    return out


def build(model):
    collection = model["collection"]
    fields, skipped = {}, {}

    for path, node in _flatten(model["root"]):
        types = [t for t in node.get("types", []) if t != "null"]
        nullable = bool(node.get("nullable")) or "null" in node.get("types", [])

        kinds = {TYPE_KIND[t] for t in types if t in TYPE_KIND}
        if not kinds:
            skipped[path] = types or ["unknown"]
            continue
        if len(kinds) > 1:
            # A field observed as more than one scalar type. Recorded rather
            # than resolved: coercing it either way would make one of the
            # observed shapes unqueryable, and the model is telling us the
            # ecosystem disagrees about this field.
            skipped[path] = sorted(types)
            continue

        kind = kinds.pop()
        entry = {"kind": kind}
        if nullable:
            entry["nullable"] = True
        if kind == "string" and path.split(".")[-1] in DATELIKE:
            entry["datelike"] = True
        fields[path] = entry

    return {
        "collection": collection,
        "generated_by": "tools/nsschema/emit/coercion_emit.py",
        "source_model": f"specs/nsschema/{collection}.model.json",
        "fields": fields,
        "uncoerced": skipped,
    }


# ------------------------------------------------------------------ drift
#
# The shipping walkers, transcribed from `origin/dev` (a8888f0d) so the
# comparison is against real code rather than against memory.
#
# TRANSCRIPTION CORRECTED 2026-09-15. The previous copy of this table recorded
# `entries.rawbg`, and the backfix register's BF-12 was raised from it. The
# string "rawbg" has never appeared in `lib/server/entries.js` in any commit on
# any branch; the entry that is actually there is `rssi`, and `rssi` IS in the
# model as an integer, so it is a correct entry and not a stale one. BF-12 does
# not reproduce. See docs/60-research/t05-schema-driven-coercion-2026-09-15.md.
#
# THIS TABLE DESCRIBES THE SHIPPING BASELINE, NOT THE FIX. T0.5's fix lives on
# cgm-remote-monitor's `bf/coercion` (88d1f8a4) and is not merged, so `--drift`
# still reports the disagreements it closes. When that branch lands, replace
# these entries with the schema-driven wiring and the report should fall to zero
# rows; a `--drift` run unchanged afterwards means the merge did not take, not
# that the measurement is stale.

SHIPPING_WALKERS = {
    "entries": {
        "where": "lib/server/entries.js:186",
        "query_path": True,
        "walker": {"date": "integer", "sgv": "integer", "filtered": "integer",
                   "unfiltered": "integer", "rssi": "integer", "noise": "integer",
                   "mbg": "integer"}},
    "treatments": {
        "where": "lib/server/treatments.js:259",
        "query_path": True,
        "walker": {"insulin": "integer", "carbs": "integer", "glucose": "integer",
                   "notes": "regex", "eventType": "regex", "enteredBy": "regex"}},
    "profile": {
        "where": "lib/server/profile.js:96",
        "query_path": True,
        "walker": {}},
    "devicestatus": {
        "where": "lib/server/devicestatus.js:173",
        "query_path": True,
        "walker": {}},
    "activity": {
        "where": "lib/server/activity.js:146",
        "query_path": True,
        "walker": {}},
    # food reaches no `lib/server/query.js` call at all: `lib/server/food.js`
    # exposes list(fn)/listquickpicks(fn)/listregular(fn), none of which take
    # query options, and `lib/api/food/index.js` passes none. So v1 /food
    # accepts no filters to get wrong. Recorded rather than dropped, because
    # BF-03 names food as an under-coerced collection and it is not one.
    "food": {
        "where": "(no query path)",
        "query_path": False,
        "walker": {}},
}

# The collections whose `queryOpts` the shipped bundle has to serve: exactly
# those with a `lib/server/query.js` call.
QUERY_COLLECTIONS = tuple(sorted(c for c, w in SHIPPING_WALKERS.items() if w["query_path"]))

# The kinds the query layer actually acts on. `string` is identity on a value
# that arrived from a query string, so shipping string entries would be dead
# weight in the served file; `datelike` belongs to BF-01's date-window fix,
# which is a different change.
COERCED_KINDS = ("integer", "number", "boolean")


def modelled_collections(model_dir):
    """Every collection with a model on disk, not just the four in
    ROOT_SCHEMA. activity and food gained models in T2.2 (69e6bc54) after this
    emitter was first written, and iterating ROOT_SCHEMA silently skipped
    them."""
    return sorted(p.name[: -len(".model.json")]
                  for p in model_dir.glob("*.model.json"))


def bundle(tables):
    """The single table the server loads at runtime: collection -> field ->
    kind, restricted to the collections query.js serves and the kinds it acts
    on. Field order is sorted so the file is diffable."""
    out = {}
    for collection in QUERY_COLLECTIONS:
        table = tables.get(collection)
        if table is None:
            continue
        out[collection] = {
            field: entry["kind"]
            for field, entry in sorted(table["fields"].items())
            if entry["kind"] in COERCED_KINDS
        }
    return {
        "_generated_by": "tools/nsschema/emit/coercion_emit.py --bundle",
        "_source_models": "specs/nsschema/<collection>.model.json",
        "_regenerate_with": "make schema-emit",
        "collections": out,
    }


def drift(tables):
    """Rows where the shipping walker disagrees with the model."""
    rows = []
    for collection, spec in sorted(SHIPPING_WALKERS.items()):
        where, walker = spec["where"], spec["walker"]
        table = tables.get(collection)
        if table is None:
            rows.append((collection, where, "\u2014", "NO MODEL", "no model",
                         "cannot be emitted; plan T2.2"))
            continue
        if not spec["query_path"]:
            rows.append((collection, where, "\u2014", "(no filters)", "(no filters)",
                         "NO QUERY PATH \u2014 v1 accepts no filters on this collection"))
            continue
        fields = table["fields"]
        for field, declared in sorted(fields.items()):
            got = walker.get(field)
            want = declared["kind"]
            if got == want:
                continue
            if got is None:
                if want in ("number", "integer", "boolean"):
                    rows.append((collection, where, field, "(none)", want,
                                 "UNDER \u2014 stays a string, matches nothing"))
                continue
            if got == "integer" and want == "number":
                rows.append((collection, where, field, "parseInt", want,
                             "OVER \u2014 fractional bounds truncated"))
            elif got == "regex":
                continue  # a deliberate search affordance, not a type claim
            else:
                rows.append((collection, where, field, got, want, "MISMATCH"))
        for field, got in sorted(walker.items()):
            if field not in fields and got != "regex":
                rows.append((collection, where, field, got, "(not in model)",
                             "ORPHAN \u2014 walker coerces a field the model does not declare"))
    return rows


def main(argv=None):
    import argparse
    from pathlib import Path
    from .. import corpus

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default="specs/nsschema", type=Path)
    ap.add_argument("--out", default="specs/generated/coercion", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    ap.add_argument("--drift", action="store_true",
                    help="report where the shipping walkers disagree with the model")
    ap.add_argument("--bundle", type=Path, default=None, metavar="PATH",
                    help="also write the runtime table query.js loads, to PATH "
                         "(the vendored copy inside a cgm-remote-monitor checkout)")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = {}
    for collection in (args.collections or modelled_collections(root / args.model_dir)):
        path = root / args.model_dir / f"{collection}.model.json"
        if not path.is_file():
            print(f"{collection}: no model — skipped")
            continue
        table = build(json.loads(path.read_text()))
        tables[collection] = table
        dest = out_dir / f"{collection}.coercion.json"
        dest.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n")
        print(f"{collection}: {len(table['fields'])} coercible, "
              f"{len(table['uncoerced'])} left alone -> {dest.relative_to(root)}")

    bundled = bundle(tables)
    dest = out_dir / "query-coercion.json"
    dest.write_text(json.dumps(bundled, indent=1, sort_keys=True) + "\n")
    print(f"bundle: {sum(len(v) for v in bundled['collections'].values())} coercions "
          f"over {len(bundled['collections'])} collections -> {dest.relative_to(root)}")
    if args.bundle:
        args.bundle.parent.mkdir(parents=True, exist_ok=True)
        args.bundle.write_text(json.dumps(bundled, indent=1, sort_keys=True) + "\n")
        print(f"bundle: vendored copy -> {args.bundle}")

    index = out_dir / "index.json"
    index.write_text(json.dumps(
        {"generated_by": "tools/nsschema/emit/coercion_emit.py",
         "collections": sorted(tables)}, indent=1) + "\n")

    if args.drift:
        rows = drift(tables)
        print(f"\nDRIFT vs the shipping walkers: {len(rows)} disagreements\n")
        hdr = ("collection", "field", "walker", "model", "consequence")
        data = [(c, f, g, w, note) for c, _where, f, g, w, note in rows]
        widths = [max(len(h), *(len(str(r[i])) for r in data)) if data else len(h)
                  for i, h in enumerate(hdr)]
        line = lambda r: "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r))
        print(line(hdr))
        print("  ".join("-" * w for w in widths))
        for r in data:
            print(line(r))
        by_note = {}
        for *_, note in rows:
            by_note[note.split(" —")[0]] = by_note.get(note.split(" —")[0], 0) + 1
        print("\nby kind: " + ", ".join(f"{k} {v}" for k, v in sorted(by_note.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
