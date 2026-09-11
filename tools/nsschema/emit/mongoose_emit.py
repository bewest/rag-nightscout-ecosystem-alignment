"""mongoose_emit.py — mongoose Schemas generated from the reconciled model.

Multitenancy discussion §6.4 concedes mongoose on exactly one level —
casting and validation correctness inside the MongoDB adapter — and names
the cost precisely: a hand-written mongoose ``Schema`` would be a *fourth*
independent declaration of every field's type, alongside the OpenAPI spec,
the boundary validators, and the Postgres column types. This emitter is the
answer to that: the schema is generated from the same model as the
validators, so the fourth list cannot drift from the first three.

Scope discipline, per §6.4: the output belongs inside
``@nightscout/storage-mongo``. It is never imported by ``@nightscout/core``,
never appears in a domain module's signature, and the Postgres adapter
never loads it.

Type mapping is deliberately conservative:

* ``integer`` and ``number`` both become ``Number`` — BSON doubles, and
  mongoose has no integer type. Integrality, where it matters, is a
  validator concern, not a cast concern.
* An observed union of scalar types becomes ``Schema.Types.Mixed`` with the
  union recorded in a comment, because casting a value whose type varies by
  client is how data gets silently corrupted.
* A map (``store``) becomes ``Map`` of the value schema, preserving
  user-chosen keys instead of turning them into schema structure.
"""

import json

SCALARS = {
    "string": "String",
    "number": "Number",
    "integer": "Number",
    "boolean": "Boolean",
}


def _indent(text, n):
    pad = " " * n
    return "\n".join(pad + line if line else line for line in text.split("\n"))


def _children(node):
    return {k: v for k, v in node.get("children", {}).items() if k not in ("[]", "{}")}


def _scalar_types(node):
    return [t for t in node["types"] if t in SCALARS]


def field_definition(node, profile, strict, depth=1):
    """Render one field's mongoose definition."""
    kids = _children(node)
    types = node["types"]
    notes = []

    if "{}" in node.get("children", {}):
        inner = field_definition(node["children"]["{}"], profile, strict, depth + 1)
        return f"{{ type: Map, of: {inner} }}", notes

    if "array" in types and "[]" in node.get("children", {}):
        inner, sub = field_definition(node["children"]["[]"], profile, strict, depth + 1)
        return f"[{inner}]", notes + sub

    if "object" in types or kids:
        body = object_body(node, profile, strict, depth + 1)
        opts = "" if strict else ", { _id: false, strict: false }"
        return f"new Schema({{\n{body}\n{' ' * (depth * 2)}}}{opts})", notes

    scalars = _scalar_types(node)
    if len(scalars) > 1:
        notes.append(f"union of {', '.join(scalars)} in live data — not cast")
        return "{ type: Schema.Types.Mixed }", notes
    if not scalars:
        return "{ type: Schema.Types.Mixed }", notes

    parts = [f"type: {SCALARS[scalars[0]]}"]
    if node.get("enum"):
        parts.append("enum: " + json.dumps(sorted(node["enum"]) +
                                           ([None] if node.get("nullable") else [])))
    if node.get(f"required_{profile}"):
        parts.append("required: true")
    if node.get("minimum") is not None:
        parts.append(f"min: {node['minimum']}")
    if node.get("maximum") is not None:
        parts.append(f"max: {node['maximum']}")
    return "{ " + ", ".join(parts) + " }", notes


def object_body(node, profile, strict, depth):
    pad = " " * (depth * 2)
    lines = []
    for name, child in sorted(_children(node).items()):
        definition, notes = field_definition(child, profile, strict, depth)
        comment_bits = []
        evidence = child.get("evidence")
        if evidence:
            comment_bits.append(
                f"{evidence['doc_frequency']:.0%} of documents, "
                f"{evidence['site_count']} sites"
            )
        if child.get("tier"):
            comment_bits.append(child["tier"])
        comment_bits.extend(notes)
        if child.get("nullable"):
            comment_bits.append("null observed")
        key = name if name.isidentifier() else json.dumps(name)
        comment = f"  // {'; '.join(comment_bits)}" if comment_bits else ""
        lines.append(f"{pad}{key}: {definition},{comment}")
    return "\n".join(lines)


def emit(model, profile="write", strict=False):
    collection = model["collection"]
    name = collection[0].upper() + collection[1:]
    header = f"""// GENERATED FILE — do not edit.
//
// Source:   {model['source_spec']}
// Evidence: {model['census']}
// Emitter:  tools/nsschema/emit/mongoose_emit.py  (profile: {profile})
//
// Regenerate with: make schema-emit
//
// Scope: this schema belongs to the MongoDB storage adapter only. It is not
// imported by engine-agnostic core code, and the Postgres adapter does not
// load it. See docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md
// §6.4 for why that boundary matters.

'use strict';

const {{ Schema }} = require('mongoose');

const {name}Schema = new Schema({{
{object_body(model['root'], profile, strict, 1)}
}}, {{
  collection: '{collection}',
  // `strict: {str(strict).lower()}` — {'undeclared fields are dropped on write'
     if strict else 'undeclared fields are preserved, matching current behaviour'}.
  strict: {str(strict).lower()},
  minimize: false,
  versionKey: false,
}});

module.exports = {{ {name}Schema }};
"""
    return header


def main(argv=None):
    import argparse
    from pathlib import Path
    from .. import corpus, specload

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default="specs/nsschema", type=Path)
    ap.add_argument("--out", default="specs/generated/mongoose", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    for collection in (args.collections or list(specload.ROOT_SCHEMA)):
        model = json.loads((root / args.model_dir / f"{collection}.model.json").read_text())
        dest = out_dir / f"{collection}.schema.js"
        dest.write_text(emit(model))
        print(f"{collection}: -> {dest.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
