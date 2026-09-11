"""jsonschema_emit.py — JSON Schema 2020-12 from the reconciled model.

Three strictness policies, because "strict vs permissive" is not one
choice but a choice per boundary:

``permissive``
    ``additionalProperties: true`` everywhere. Types and enums are checked;
    unknown fields pass through untouched. Closest to Nightscout's
    behaviour today, plus type checking.
``tolerant``
    Every field the corpus has *ever* shown, typed at the place it appears —
    vendor fields included, left at the top level where their clients write
    them today. ``additionalProperties: false``, so only genuinely novel
    fields are rejected. The migration-friendly option: nothing that exists
    has to move.
``extension-bag``
    Core fields typed at the top level; weakly-evidenced vendor fields must
    live under ``x-aid-extensions``. ``additionalProperties: false``. This
    is the ``x-aid-extensions`` convention proposal expressed as a
    validator — and because no shipped client writes the bag today, its
    rejection rate is the size of the migration it asks for.
``strict``
    Only what the spec declares, ``additionalProperties: false`` at every
    object. Maximum commitment, and the only policy under which a field's
    absence from the spec is a hard error.

and two profiles, ``write`` (what a client may send) and ``read`` (what a
consumer may rely on receiving) — see ``nsschema.model``.
"""

import json

DIALECT = "https://json-schema.org/draft/2020-12/schema"

STRICTNESS = ("permissive", "tolerant", "extension-bag", "strict")
PROFILES = ("write", "read")

EXTENSION_KEY = "x-aid-extensions"

STRUCTURAL = {"object", "array"}


def _children(node, skip=("[]", "{}")):
    return {k: v for k, v in node.get("children", {}).items() if k not in skip}


def node_schema(node, profile, strictness, include_extensions=True):
    types = list(node["types"])
    if node.get("nullable") and "null" not in types:
        types.append("null")

    schema = {}
    if types:
        schema["type"] = types[0] if len(types) == 1 else sorted(types)

    if node.get("description"):
        schema["description"] = node["description"].strip().split("\n")[0][:300]
    # Sensitivity travels with the field, so a consumer strips by label
    # rather than by a bespoke scrubber. Annotation keywords; validators
    # ignore them.
    if node.get("sensitivity"):
        schema["x-sensitivity"] = node["sensitivity"]
    if node.get("data_category"):
        schema["x-data-category"] = node["data_category"]
    if node.get("observed_values"):
        # Annotation keyword: documents what live data holds without
        # constraining the field. Validators ignore unknown keywords.
        schema["x-observed-values"] = node["observed_values"]
    if node.get("enum"):
        enum = list(node["enum"])
        if node.get("nullable"):
            enum.append(None)
        schema["enum"] = enum
    for key in ("minimum", "maximum"):
        if node.get(key) is not None:
            schema[key] = node[key]
    fmt = node.get("format")
    if fmt in ("date-time", "email", "uri", "uuid"):
        schema["format"] = fmt

    kids = _children(node)
    if strictness == "tolerant":
        # Everything observed is typed where it actually appears.
        core, extension = kids, {}
    elif strictness == "strict":
        # Only what the spec declares survives.
        core = {k: v for k, v in kids.items() if v.get("declared")}
        extension = {}
    else:
        core = {k: v for k, v in kids.items() if v.get("placement") == "core"}
        extension = {k: v for k, v in kids.items() if v.get("placement") != "core"}

    if "object" in types or core:
        props = {}
        required = []
        for name, child in sorted(core.items()):
            props[name] = node_schema(child, profile, strictness, include_extensions)
            if child.get(f"required_{profile}"):
                required.append(name)
        if strictness == "extension-bag" and include_extensions and extension:
            # Undeclared-but-observed fields keep a documented home instead
            # of being silently tolerated or silently rejected.
            props[EXTENSION_KEY] = {
                "type": "object",
                "description": (
                    "Vendor- or client-specific fields not part of the core "
                    "schema. Observed in live data on a minority of sites."
                ),
                "properties": {
                    name: node_schema(child, profile, strictness, include_extensions)
                    for name, child in sorted(extension.items())
                },
                "additionalProperties": False,
            }
        if props:
            schema["properties"] = props
        if required:
            schema["required"] = sorted(required)
        schema["additionalProperties"] = strictness == "permissive"

    if "[]" in node.get("children", {}):
        schema["items"] = node_schema(node["children"]["[]"], profile, strictness,
                                      include_extensions)
    if "{}" in node.get("children", {}):
        schema["additionalProperties"] = node_schema(
            node["children"]["{}"], profile, strictness, include_extensions)

    return schema


def emit(model, profile="write", strictness="permissive", include_extensions=True):
    assert profile in PROFILES, profile
    assert strictness in STRICTNESS, strictness
    collection = model["collection"]
    schema = node_schema(model["root"], profile, strictness, include_extensions)
    schema.update({
        "$schema": DIALECT,
        "$id": f"https://nightscout.dev/schemas/{collection}.{profile}.{strictness}.json",
        "title": f"Nightscout {collection} ({profile}, {strictness})",
        "description": (
            f"Generated by tools/nsschema/emit/jsonschema_emit.py from "
            f"{model['source_spec']} reconciled against {model['census']}. "
            f"Do not edit by hand."
        ),
    })
    # Put the keywords readers look for first.
    ordered = {k: schema[k] for k in ("$schema", "$id", "title", "description") if k in schema}
    ordered.update({k: v for k, v in schema.items() if k not in ordered})
    return ordered


def main(argv=None):
    import argparse
    from pathlib import Path
    from .. import corpus, specload

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default="specs/nsschema", type=Path)
    ap.add_argument("--out", default="specs/jsonschema/generated", type=Path)
    ap.add_argument("--collection", action="append", dest="collections")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    out_dir = root / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    for collection in (args.collections or list(specload.ROOT_SCHEMA)):
        model = json.loads((root / args.model_dir / f"{collection}.model.json").read_text())
        for profile in PROFILES:
            for strictness in STRICTNESS:
                schema = emit(model, profile, strictness)
                dest = out_dir / f"{collection}.{profile}.{strictness}.schema.json"
                dest.write_text(json.dumps(schema, indent=1) + "\n")
        print(f"{collection}: {len(PROFILES) * len(STRICTNESS)} schemas -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
