"""pyarrow_emit.py — a PyArrow schema for the *wire* shape of a collection.

Distinct from ``tools/ns2parquet/schemas.py``, and deliberately so. That
module defines the *analysis* projection: flattened, unit-normalized,
lossy on purpose (durations converted to minutes, vendor subtrees
discarded, ``event_type`` re-labelled). This module defines the shape the
documents actually have on the wire, nested subtrees included.

Having both, generated and hand-written, is only safe if something checks
that the hand-written one does not contradict the measured one — that is
``ns2parquet_drift.py``, not this file.

Union handling is explicit: Arrow columns are typed, JSON fields in this
corpus are sometimes not. Where a field was observed with more than one
scalar type, the emitter widens to the type that can hold all of them and
records the coercion in a comment, rather than silently truncating.
"""

import json

ARROW = {
    "string": "pa.large_string()",
    "number": "pa.float64()",
    "integer": "pa.int64()",
    "boolean": "pa.bool_()",
}

# Widening order: a column typed later can hold everything before it.
WIDEN = ["boolean", "integer", "number", "string"]


def _children(node):
    return {k: v for k, v in node.get("children", {}).items() if k not in ("[]", "{}")}


def arrow_type(node, depth=0):
    types = [t for t in node["types"] if t != "null"]
    kids = _children(node)
    note = None

    if "{}" in node.get("children", {}):
        value, _ = arrow_type(node["children"]["{}"], depth + 1)
        return f"pa.map_(pa.large_string(), {value})", None

    if "array" in types and "[]" in node.get("children", {}):
        item, note = arrow_type(node["children"]["[]"], depth + 1)
        return f"pa.list_({item})", note
    if "array" in types:
        return "pa.list_(pa.large_string())", "array of unknown item type"

    if "object" in types or kids:
        if not kids:
            return "pa.large_string()", "object with no observed fields; stored as JSON text"
        pad = "    " * (depth + 1)
        fields = []
        for name, child in sorted(kids.items()):
            ctype, cnote = arrow_type(child, depth + 1)
            comment = f"  # {cnote}" if cnote else ""
            fields.append(f"{pad}pa.field({json.dumps(name)}, {ctype}),{comment}")
        inner = "\n".join(fields)
        return f"pa.struct([\n{inner}\n{'    ' * depth}])", None

    scalars = [t for t in types if t in ARROW]
    if not scalars:
        return "pa.large_string()", "no scalar type observed"
    if len(scalars) == 1:
        return ARROW[scalars[0]], None
    widest = max(scalars, key=WIDEN.index)
    return ARROW[widest], f"union of {', '.join(sorted(scalars))} widened to {widest}"


def emit(model):
    collection = model["collection"]
    lines = []
    for name, child in sorted(_children(model["root"]).items()):
        ctype, note = arrow_type(child, 1)
        bits = []
        evidence = child.get("evidence")
        if evidence:
            bits.append(f"{evidence['doc_frequency']:.0%} docs, {evidence['site_count']} sites")
        if child.get("tier"):
            bits.append(child["tier"])
        if child.get("nullable"):
            bits.append("null observed")
        if note:
            bits.append(note)
        comment = f"  # {'; '.join(bits)}" if bits else ""
        lines.append(f"    pa.field({json.dumps(name)}, {ctype}),{comment}")
    body = "\n".join(lines)
    const = collection.upper()
    return f'''"""GENERATED FILE — do not edit.

Wire-shape PyArrow schema for the Nightscout ``{collection}`` collection.

Source:   {model['source_spec']}
Evidence: {model['census']}
Emitter:  tools/nsschema/emit/pyarrow_emit.py

Regenerate with: make schema-emit

This is the shape documents have on the wire, not the analysis projection.
For the flattened, unit-normalized analysis schema see
``tools/ns2parquet/schemas.py``; ``tools/nsschema/emit/ns2parquet_drift.py``
checks that the two do not contradict each other.
"""

import pyarrow as pa

{const}_WIRE_SCHEMA = pa.schema([
{body}
])
'''


def main(argv=None):
    import argparse
    from pathlib import Path
    from .. import corpus, specload

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default="specs/nsschema", type=Path)
    ap.add_argument("--out", default="specs/generated/arrow", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "__init__.py").write_text('"""Generated wire-shape PyArrow schemas."""\n')
    for collection in (args.collections or list(specload.ROOT_SCHEMA)):
        model = json.loads((root / args.model_dir / f"{collection}.model.json").read_text())
        dest = out_dir / f"{collection}_wire.py"
        dest.write_text(emit(model))
        print(f"{collection}: -> {dest.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
