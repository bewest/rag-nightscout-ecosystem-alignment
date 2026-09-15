"""postgres_emit.py — ``CREATE TABLE`` DDL for the multitenant backend.

WHAT SHAPE THIS IS, AND WHICH DECISIONS FIXED IT

Decision D3 puts the hosted service on PostgreSQL with row-level security,
and {M} §6.3/§6.7 fixes the storage shape: the document body stays whole in
a ``jsonb`` column, ``tenant_id uuid`` leads every table and every index, and
the fields that MongoDB indexes today become **generated columns** so the
planner has ordinary typed columns to build bounds from.

Decision D11 settles the one question that blocked this emitter. ``devicestatus``
has 182 nodes and the temptation was to decide which of them deserve columns.
That question is **retired, not answered**: the real answer is decomposition
into normalised time series declared by a registered controller description,
which is a separate task *above* the seam. So this emitter takes the same rule
for every collection — a column for what ``indexedFields`` declares, and
nothing else — and ``devicestatus`` gets three indexes rather than a
speculative column list. Widening it here would be building half of a design
that is going somewhere else.

THE GENERATED COLUMNS ARE AN INDEX ACCELERATOR, NOT THE SOURCE OF TRUTH

This is the constraint that matters most in this file, and it is load-bearing
in both directions:

  * **``$exists`` must never read a generated column.** A generated column is
    built from ``->>``, which returns SQL NULL for an absent key *and* for an
    explicit JSON null — it cannot tell them apart. ``doc #> '{path}'`` can:
    jsonb ``'null'`` for the second, SQL NULL for the first. The seam's
    ``toSql`` already reads the document unconditionally for ``exists``
    ({S} §8.3 found this as a live disagreement and fixed it there), so the
    DDL's job is to not imply otherwise. Nothing here is ``NOT NULL`` except
    ``tenant_id``, ``doc`` and the primary key, precisely so no reader can
    mistake a column's nullability for a statement about key presence.
  * **The document is always the record.** Dropping every generated column and
    re-adding it must not change a single answer. That is why each column
    carries a ``jsonb_typeof`` guard rather than a bare cast — see below.

THE ``jsonb_typeof`` GUARD, AND WHY IT IS NOT DEFENSIVE PROGRAMMING

A bare ``(doc ->> 'sgv')::numeric`` has two failure modes on a corpus that is
known to carry mixed types for a single field:

  1. a stored string ``"abc"`` makes the *INSERT* fail, turning a data-quality
     problem into an ingest outage on a CGM path;
  2. a stored string ``"120"`` silently becomes the number 120, which MongoDB
     would **not** match, because MongoDB orders BSON types before it compares
     values.

The guard — ``CASE WHEN jsonb_typeof(doc -> 'sgv') = 'number' THEN … END`` —
fixes both, and it is immutable, which ``GENERATED ALWAYS AS … STORED``
requires. It is also the more faithful translation: a value of the wrong type
is not a match in MongoDB either.

**Read that together with ``toSql``'s jsonb fallback, because they disagree.**
See ``--report``: the guarded column and the unguarded ``(doc #>> …)::numeric``
path give different answers on cross-type values, which means whether a field
has a column can change a query's result. That is flagged, not fixed, here —
``lib/storage/filter.js`` is owned elsewhere and the fix is a query-surface
decision (T2.3), not a DDL one.

WHY COLUMN NAMES ARE THE DOTTED PATH VERBATIM

``toSql(ast, {columns})`` looks a field path up in that set and emits
``"<path>"`` as a quoted identifier when it hits. So a generated column for
``uploader.battery`` must literally be named ``uploader.battery``; a mangled
name would simply never be used and the index would be dead weight. Quoted
identifiers make that safe, and the AST's own field-path grammar (plain
segments, dots between) keeps it within PostgreSQL's 63-byte limit.

WHAT THIS DOES NOT DO

No ``food``, ``activity``, ``settings`` or ``auth_*`` — those have no model
yet (plan T2.2), and inventing one here would be the fifth drift-prone list.
Sort stability and NULLS ordering are not addressed: MongoDB sorts missing
values first ascending, PostgreSQL's btree default is NULLS LAST, and nothing
in this task measured the difference.

USAGE

    python -m tools.nsschema.emit.postgres_emit
    python -m tools.nsschema.emit.postgres_emit --report   # index + coercion reconciliation
    python -m tools.nsschema.emit.postgres_emit --no-rls   # bare tables, for a POC harness
"""

import json
import re

# lib/storage/filter.js's field-path grammar, verbatim.
FIELD_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

# Model type -> column type. `integer` and `number` both become `numeric`, and
# that is deliberate twice over: `numeric` is what the seam's toSql casts a
# jsonb path to, so a predicate means the same thing with or without a column;
# and a `bigint` column would ERROR on a fractional bound where `numeric`
# merely fails to match, which is a worse divergence than the one it fixes.
# (`entries.date` is declared `number` for exactly this reason — 61.5 % of the
# corpus carries a fractional epoch-millisecond value.)
SQL_TYPE = {
    "integer": "numeric",
    "number": "numeric",
    "boolean": "boolean",
    "string": "text",
}

# The JSON type each column type is willing to accept. A value of any other
# type leaves the column NULL rather than being coerced, which is what MongoDB
# does when it orders BSON types before comparing values.
JSON_TYPEOF = {
    "numeric": "number",
    "boolean": "boolean",
    "text": "string",
}

# ``indexedFields``, transcribed from ``chore/nightscout-modernization`` with
# the declaring line, so the comparison is against real code rather than
# against memory. Same convention as coercion_emit's SHIPPING_WALKERS, and for
# the same reason: this list is not in the model, and pretending otherwise
# would hide a real gap. {M} §6.7 counts these: 35 secondary indexes over six
# collections, plus six `_id` indexes, is its 41.
INDEXED_FIELDS = {
    "entries": ("lib/server/entries.js:246", [
        "date", "type", "sgv", "mbg", "sysTime", "dateString", "identifier",
        {"type": 1, "date": -1, "dateString": 1},
        {"date": -1, "identifier": -1, "created_at": -1},
    ]),
    "treatments": ("lib/server/treatments.js:443", [
        "created_at", "eventType", "insulin", "carbs", "glucose", "enteredBy",
        "boluscalc.foods._id", "notes", "NSCLIENT_ID", "percent", "absolute",
        "duration", "identifier",
        {"eventType": 1, "duration": 1, "created_at": 1},
        {"eventType": 1, "created_at": -1, "identifier": -1, "date": -1},
    ]),
    "devicestatus": ("lib/server/devicestatus.js:182", [
        # D11: these three and nothing else. The other 179 nodes stay in jsonb.
        "created_at", "NSCLIENT_ID",
        {"created_at": -1, "identifier": -1, "date": -1},
    ]),
    "profile": ("lib/server/profile.js:269", [
        "startDate", "created_at", "NSCLIENT_ID",
        {"startDate": -1, "_id": -1},
    ]),
}

# Paths that traverse an array. A generated column cannot reproduce MongoDB's
# multikey semantics — `doc #>> '{boluscalc,foods,_id}'` is NULL on an array,
# not one value per element — so no column and no index is emitted, and the
# capability is reported as lost rather than approximated. The live query is
# `?find[boluscalc.foods._id]=…` (lib/report/reportclient.js:294), so this is a
# real feature, not a vestige.
MULTIKEY_PATHS = {"treatments": {"boluscalc.foods._id"}}

TENANT_SETTING = "app.current_tenant_id"
JSONB_COLUMN = "doc"
IDENTIFIER_FIELD = "_id"


def _lookup(model, path):
    """The model node at a dotted path, or None if the model is silent."""
    node = model["root"]
    for segment in path.split("."):
        children = node.get("children", {})
        if segment not in children:
            return None
        node = children[segment]
    return node


def _column_type(node):
    """The column type for a model node, or None if it cannot be typed.

    A field observed as more than one scalar type is left untyped on purpose:
    picking one would make the other shape unqueryable, and the model is
    telling us the ecosystem disagrees about this field.
    """
    if node is None:
        return None
    types = [t for t in node.get("types", []) if t != "null"]
    kinds = {SQL_TYPE[t] for t in types if t in SQL_TYPE}
    return kinds.pop() if len(kinds) == 1 else None


def _path_literal(path):
    # The same grammar lib/storage/filter.js validates field paths against. It
    # is repeated rather than relaxed because it is what makes the '{a,b}' path
    # literal below safe by construction instead of by escaping — and because a
    # path this emitter accepts but the AST rejects would produce a column no
    # query could ever reach.
    if not FIELD_PATH.match(path):
        raise ValueError(f"not a plain dotted field path: {path!r}")
    return "{" + ",".join(path.split(".")) + "}"


def generated_expression(path, column_type):
    """``CASE WHEN jsonb_typeof(…) THEN … END`` for one generated column."""
    literal = _path_literal(path)
    probe = f"{JSONB_COLUMN} #> '{literal}'"
    value = f"{JSONB_COLUMN} #>> '{literal}'"
    cast = "" if column_type == "text" else f"::{column_type}"
    return (f"CASE WHEN jsonb_typeof({probe}) = '{JSON_TYPEOF[column_type]}' "
            f"THEN ({value}){cast} END")


def _index_members(entry):
    """One ``indexedFields`` entry as [(path, 'ASC'|'DESC')]."""
    if isinstance(entry, str):
        # createIndex('x') is ascending. A PostgreSQL btree is scanned in both
        # directions, so the direction of a single-column index is cosmetic;
        # it is preserved anyway so the DDL reads as the declaration does.
        return [(entry, "ASC")]
    return [(path, "ASC" if d > 0 else "DESC") for path, d in entry.items()]


def build(model):
    """Everything the DDL and the reconciliation report need for one table."""
    collection = model["collection"]
    where, declarations = INDEXED_FIELDS[collection]
    multikey = MULTIKEY_PATHS.get(collection, set())

    # `_id` is not an indexedFields entry — MongoDB indexes it implicitly, which
    # is where {M} §6.7's "plus 6 _id indexes" comes from. It is emitted first
    # because it is the primary key, and it is the one column here that is NOT
    # an accelerator: an identifier a row cannot be addressed by is not optional.
    paths = [IDENTIFIER_FIELD]
    for entry in declarations:
        for path, _ in _index_members(entry):
            if path not in paths:
                paths.append(path)

    columns, flagged = {}, []
    for path in paths:
        if path in multikey:
            flagged.append((path, "MULTIKEY",
                            "traverses an array; no column, no index, "
                            "capability lost until decomposition"))
            continue
        node = _lookup(model, path)
        column_type = _column_type(node)
        if column_type is None:
            reason = ("the model does not declare this field"
                      if node is None else
                      f"observed as {', '.join(node['types'])} — not one type")
            flagged.append((path, "UNDECLARED" if node is None else "AMBIGUOUS", reason))
            continue
        columns[path] = {
            "type": column_type,
            "expression": generated_expression(path, column_type),
            "datelike": column_type == "text" and node.get("format") == "date-time",
        }

    indexes = []
    for entry in declarations:
        members = _index_members(entry)
        if any(path in multikey for path, _ in members):
            continue
        indexes.append({
            "name": f"{collection}_tenant_"
                    + "_".join(p.replace(".", "_") for p, _ in members).lower(),
            "members": members,
            "compound": not isinstance(entry, str),
        })

    return {
        "collection": collection,
        "declared_by": where,
        "columns": columns,
        "indexes": indexes,
        "flagged": flagged,
    }


# ------------------------------------------------------------------- DDL


def _index_expression(table, path, direction):
    if path in table["columns"]:
        return f'"{path}" {direction}'
    # No column for this member, so the index carries the raw jsonb path. It
    # can still be scanned for the leading columns, and toSql will never build
    # a predicate that matches this expression, so it is index structure only.
    return f"""({JSONB_COLUMN} #>> '{_path_literal(path)}') {direction}"""


def emit(model, rls=True):
    collection = model["collection"]
    table = build(model)
    if IDENTIFIER_FIELD not in table["columns"]:
        # Refuse rather than emit a table whose rows cannot be addressed. A
        # model that does not declare `_id` is a T2.2 problem, not something
        # this emitter should paper over with a surrogate key.
        raise ValueError(f"{collection}: no usable {IDENTIFIER_FIELD} — cannot key the table")

    lines = [
        f"CREATE TABLE {collection} (",
        "  -- tenant_id leads the table and every index below: under RLS the policy",
        "  -- predicate is an ordinary equality, and the planner can only build index",
        "  -- bounds from it if it is the leading column.",
        "  tenant_id  uuid   NOT NULL,",
        f"  {JSONB_COLUMN}        jsonb  NOT NULL,",
    ]
    width = max([len(p) + 2 for p in table["columns"]] + [10])
    for path in table["columns"]:
        spec = table["columns"][path]
        name = f'"{path}"'.ljust(width)
        null = " NOT NULL" if path == IDENTIFIER_FIELD else ""
        lines.append(f"  {name} {spec['type']}{null}")
        lines.append(f"    GENERATED ALWAYS AS ({spec['expression']}) STORED,")
    lines.append("")
    lines.append("  -- Scoped to the tenant rather than global: two tenants restored from")
    lines.append("  -- different deployments can legitimately carry the same _id, and a")
    lines.append("  -- global unique constraint would make one of them unimportable.")
    lines.append(f'  PRIMARY KEY (tenant_id, "{IDENTIFIER_FIELD}")')
    lines.append(");")
    lines.append("")

    for index in table["indexes"]:
        members = ", ".join(_index_expression(table, p, d) for p, d in index["members"])
        lines.append(f"CREATE INDEX {index['name']}")
        lines.append(f"  ON {collection} (tenant_id, {members});")
    lines.append("")

    if rls:
        lines.extend([
            "-- FORCE is the load-bearing word: without it the table OWNER bypasses the",
            "-- policy. It still does not subject a SUPERUSER — BYPASSRLS is implicit for",
            "-- one — so anything verifying isolation must connect as a role that is",
            "-- NOSUPERUSER NOBYPASSRLS, or it has verified nothing.",
            f"ALTER TABLE {collection} ENABLE ROW LEVEL SECURITY;",
            f"ALTER TABLE {collection} FORCE ROW LEVEL SECURITY;",
            "",
            "-- NULLIF so that an unbound connection yields NULL rather than an empty",
            "-- string, and `tenant_id = NULL` is never true: the fail-closed property",
            "-- D3 is chosen for. WITH CHECK is what extends it to writes, which is the",
            "-- axis MongoDB's role-keyed views cannot cover at all ({M} §6.7).",
            f"CREATE POLICY {collection}_tenant_isolation ON {collection}",
            f"  USING      (tenant_id = NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid)",
            f"  WITH CHECK (tenant_id = NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid);",
        ])

    flagged = "\n".join(
        f"--   {path:24s} {kind:11s} {reason}" for path, kind, reason in table["flagged"]
    ) or "--   (none)"

    header = f"""-- GENERATED FILE — do not edit.
--
-- PostgreSQL DDL for the Nightscout `{collection}` collection, multitenant shape.
--
-- Source:   {model['source_spec']}
-- Evidence: {model['census']}
-- Indexes:  {table['declared_by']} (indexedFields, on chore/nightscout-modernization)
-- Emitter:  tools/nsschema/emit/postgres_emit.py
--
-- Regenerate with: make schema-emit
--
-- THE COLUMNS BELOW ARE AN INDEX ACCELERATOR. THE DOCUMENT IS THE RECORD.
-- Dropping every generated column must not change an answer. In particular an
-- `$exists` check must read `{JSONB_COLUMN} #> '{{path}}'` and never a column: a column is
-- built from `->>`, which returns SQL NULL for an absent key and for an explicit
-- JSON null alike, and cannot tell them apart. lib/storage/filter.js does this
-- correctly; nothing here licenses a hand-written query to do otherwise.
--
-- Indexed fields with no column, and why:
{flagged}
"""
    return header + "\n" + "\n".join(lines) + "\n"


# ----------------------------------------------------------- reconciliation
#
# {M} §6.7 enumerates 41 indexes across six collections. Four have models; the
# report states the arithmetic rather than asserting a number, because the two
# counts are over different collection sets and quietly emitting a different
# total is exactly how a plan rots.

M67_SECONDARY = {"treatments": 15, "entries": 9, "profile": 4, "devicestatus": 3,
                 "food": 3, "activity": 1}


def reconcile(tables):
    rows = []
    for collection, expected in sorted(M67_SECONDARY.items()):
        table = tables.get(collection)
        if table is None:
            rows.append((collection, expected, 0, 0,
                         "no model — plan T2.2, out of scope for T2.1"))
            continue
        emitted = len(table["indexes"])
        dropped = expected - emitted
        note = "matches" if not dropped else \
            f"{dropped} dropped: " + "; ".join(p for p, k, _ in table["flagged"]
                                               if k == "MULTIKEY")
        rows.append((collection, expected, emitted, 1, note))
    return rows


# The divergences worth a maintainer's attention, each stated rather than
# resolved. Resolving any of them means changing lib/storage/filter.js or the
# query surface, neither of which is this task's to change.
COERCION_FLAGS = [
    ("cross-type values",
     "a guarded column is NULL where toSql's `(doc #>> …)::numeric` coerces a "
     "stored string to a number. The column agrees with MongoDB; the jsonb "
     "fallback does not. So whether a field HAS a column can change an answer."),
    ("dirty values",
     "`('abc')::numeric` raises at query time on the jsonb path, where the "
     "guarded column is merely NULL. Same predicate, error vs. no-match."),
    ("numeric field, string bound",
     "`\"date\" >= $1` with an ISO string raises 22P02 where MongoDB silently "
     "matches nothing. This is BF-01's live defect arriving as an error instead "
     "of as an empty page — louder, still a behaviour difference, and the real "
     "fix is T0.5's coercion table above the seam."),
    ("date-like text columns",
     "created_at / startDate / sysTime / dateString are `text`, so a range "
     "predicate is lexicographic. That is chronological only while every writer "
     "emits a UTC-normalised ISO string of constant width. timestamptz would fix "
     "the ordering and break `eq`, and its cast is not immutable so it cannot be "
     "a generated column at all. Left as text, flagged."),
]


def main(argv=None):
    import argparse
    from pathlib import Path
    from .. import corpus, specload

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default="specs/nsschema", type=Path)
    ap.add_argument("--out", default="specs/generated/postgres", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    ap.add_argument("--no-rls", dest="rls", action="store_false",
                    help="omit the policy block (the tables alone are not isolated)")
    ap.add_argument("--report", action="store_true",
                    help="reconcile the emitted index set against {M} §6.7 and list "
                         "the type divergences that are flagged rather than resolved")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = {}
    for collection in (args.collections or list(specload.ROOT_SCHEMA)):
        path = root / args.model_dir / f"{collection}.model.json"
        if not path.is_file():
            print(f"{collection}: no model — skipped")
            continue
        model = json.loads(path.read_text())
        table = build(model)
        tables[collection] = table
        dest = out_dir / f"{collection}.sql"
        dest.write_text(emit(model, rls=args.rls))
        print(f"{collection}: {len(table['columns'])} generated columns, "
              f"{len(table['indexes'])} indexes, {len(table['flagged'])} flagged "
              f"-> {dest.relative_to(root)}")

    # The manifest is what a caller passes to toSql's `columns` option, so the
    # same AST produces a column comparison where one exists and a jsonb
    # traversal where it does not. `exists` ignores it by construction.
    index = out_dir / "index.json"
    index.write_text(json.dumps({
        "generated_by": "tools/nsschema/emit/postgres_emit.py",
        "jsonbColumn": JSONB_COLUMN,
        "tenantSetting": TENANT_SETTING,
        "collections": {
            name: {
                "columns": sorted(t["columns"]),
                "datelike": sorted(p for p, c in t["columns"].items() if c["datelike"]),
                "indexes": [i["name"] for i in t["indexes"]],
                "flagged": [{"path": p, "kind": k, "why": w} for p, k, w in t["flagged"]],
            } for name, t in sorted(tables.items())
        },
    }, indent=1, sort_keys=True) + "\n")

    if args.report:
        rows = reconcile(tables)
        print("\nINDEX RECONCILIATION vs {M} §6.7\n")
        hdr = ("collection", "§6.7", "emitted", "pk", "note")
        data = [(c, str(e), str(m), str(p), n) for c, e, m, p, n in rows]
        widths = [max(len(h), *(len(r[i]) for r in data)) for i, h in enumerate(hdr)]
        line = lambda r: "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r))
        print(line(hdr))
        print("  ".join("-" * w for w in widths))
        for r in data:
            print(line(r))
        secondary = sum(int(r[2]) for r in data)
        pk = sum(int(r[3]) for r in data)
        print(f"\n  §6.7 total:      {sum(M67_SECONDARY.values())} secondary "
              f"+ {len(M67_SECONDARY)} _id = {sum(M67_SECONDARY.values()) + len(M67_SECONDARY)}")
        print(f"  emitted here:    {secondary} secondary + {pk} primary key = {secondary + pk}"
              f"  (four collections; food/activity are T2.2)")

        print("\nTYPE DIVERGENCES — flagged, not resolved\n")
        for title, why in COERCION_FLAGS:
            print(f"  {title}")
            for chunk in _wrap(why, 74):
                print(f"      {chunk}")
        print("\nINDEXED FIELDS WITH NO COLUMN\n")
        for collection, table in sorted(tables.items()):
            for path, kind, why in table["flagged"]:
                print(f"  {collection:13s} {path:22s} {kind:11s} {why}")
    return 0


def _wrap(text, width):
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
