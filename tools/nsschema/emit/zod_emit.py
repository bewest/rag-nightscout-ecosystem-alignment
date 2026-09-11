"""zod_emit.py — zod schemas and inferred TypeScript types from the model.

Two artifacts from one source, matching the split the modernization
discussion draws: TypeScript *types* describe what the code believes, zod
*schemas* check what actually arrived. Vendor payloads and uploader traffic
are hostile input; a type annotation validates nothing at runtime, so both
are generated and the types are inferred from the schemas rather than
written separately.

Policy carried over from the model:

* ``.nullable()`` wherever null was observed in live documents — the
  corpus has fields (``treatments.carbs``, ``treatments.insulin``) that are
  null in the majority of documents, and a non-nullable type for them is
  simply wrong.
* ``.optional()`` for everything the profile does not mark required.
* Unions are emitted as ``z.union([...])`` rather than collapsed, so a
  field whose type varies by client stays visibly variable.
* ``.passthrough()`` or ``.strict()`` per the chosen strictness, so the
  runtime behaviour matches the JSON Schema policy of the same name.
"""

import json
import re

SCALARS = {
    "string": "z.string()",
    "number": "z.number()",
    "integer": "z.number().int()",
    "boolean": "z.boolean()",
}

IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def _children(node):
    return {k: v for k, v in node.get("children", {}).items() if k not in ("[]", "{}")}


def expr(node, profile, strictness, depth=1):
    types = [t for t in node["types"] if t != "null"]
    kids = _children(node)
    pad = "  " * depth

    if "{}" in node.get("children", {}):
        inner = expr(node["children"]["{}"], profile, strictness, depth)
        return f"z.record(z.string(), {inner})"

    if "array" in types and "[]" in node.get("children", {}):
        return f"z.array({expr(node['children']['[]'], profile, strictness, depth)})"
    if "array" in types:
        return "z.array(z.unknown())"

    if "object" in types or kids:
        if not kids:
            return "z.record(z.string(), z.unknown())"
        lines = []
        for name, child in sorted(kids.items()):
            key = name if IDENT.match(name) else json.dumps(name)
            value = expr(child, profile, strictness, depth + 1)
            if child.get("nullable"):
                value += ".nullable()"
            if not child.get(f"required_{profile}"):
                value += ".optional()"
            comment = ""
            evidence = child.get("evidence")
            if evidence:
                comment = (f"  // {evidence['doc_frequency']:.0%} of documents, "
                           f"{evidence['site_count']} sites, {child.get('tier','')}")
            lines.append(f"{pad}  {key}: {value},{comment}")
        body = "\n".join(lines)
        suffix = ".passthrough()" if strictness == "permissive" else ".strict()"
        return "z.object({\n" + body + f"\n{pad}}})" + suffix

    if node.get("enum"):
        values = ", ".join(json.dumps(v) for v in sorted(node["enum"]))
        return f"z.enum([{values}])"

    scalars = [SCALARS[t] for t in types if t in SCALARS]
    if len(scalars) == 1:
        return scalars[0]
    if len(scalars) > 1:
        return "z.union([" + ", ".join(scalars) + "])"
    return "z.unknown()"


def emit(model, profile="write", strictness="permissive"):
    collection = model["collection"]
    name = collection[0].upper() + collection[1:]
    schema = expr(model["root"], profile, strictness)
    return f"""// GENERATED FILE — do not edit.
//
// Source:   {model['source_spec']}
// Evidence: {model['census']}
// Emitter:  tools/nsschema/emit/zod_emit.py
//           profile: {profile}   strictness: {strictness}
//
// Regenerate with: make schema-emit
//
// The type is inferred from the schema, not declared alongside it: a
// TypeScript type checks nothing at runtime, and the documents this parses
// arrive from uploaders and vendor bridges that are not under our control.

import {{ z }} from 'zod';

export const {name}Schema = {schema};

export type {name} = z.infer<typeof {name}Schema>;
"""


def main(argv=None):
    import argparse
    from pathlib import Path
    from .. import corpus, specload

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default="specs/nsschema", type=Path)
    ap.add_argument("--out", default="specs/generated/typescript", type=Path)
    ap.add_argument("--profile", default="write")
    ap.add_argument("--strictness", default="permissive")
    ap.add_argument("--collection", action="append", dest="collections")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    for collection in (args.collections or list(specload.ROOT_SCHEMA)):
        model = json.loads((root / args.model_dir / f"{collection}.model.json").read_text())
        dest = out_dir / f"{collection}.ts"
        dest.write_text(emit(model, args.profile, args.strictness))
        print(f"{collection}: -> {dest.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
