"""specload.py — flatten an OpenAPI schema object into dotted field paths.

The census speaks in dotted paths (``loopSettings.overridePresets[].name``).
The specs in ``specs/openapi/`` speak in nested OpenAPI schema objects with
``$ref`` indirection. This module renders the second into the first so the
two can be compared field by field.

Only local ``#/components/schemas/...`` refs are resolved; the specs use no
external refs. ``allOf`` is merged; ``oneOf``/``anyOf`` are recorded as a
type union on the branch point and their branches are flattened together,
which is the conservative reading for "what may legally appear here".
"""

from pathlib import Path

import yaml

ROOT_SCHEMA = {
    "entries": ("aid-entries-2025.yaml", "Entry"),
    "treatments": ("aid-treatments-2025.yaml", "Treatment"),
    "devicestatus": ("aid-devicestatus-2025.yaml", "DeviceStatus"),
    "profile": ("aid-profile-2025.yaml", "ProfileDocument"),
}


class Spec:
    def __init__(self, path: Path):
        self.path = path
        self.doc = yaml.safe_load(path.read_text())
        self.schemas = self.doc.get("components", {}).get("schemas", {})

    def resolve(self, node, _seen=()):
        """Follow a local $ref one level; returns the target schema object."""
        if isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            name = ref.rsplit("/", 1)[-1]
            if name in _seen:
                return {"type": "object", "x-recursive": name}
            target = self.schemas.get(name)
            if target is None:
                return {"x-unresolved-ref": ref}
            merged = dict(self.resolve(target, _seen + (name,)))
            merged.setdefault("x-schema-name", name)
            for k, v in node.items():
                if k != "$ref":
                    merged[k] = v
            return merged
        return node

    def merged(self, node, _seen=()):
        """Resolve refs and flatten allOf into a single schema object."""
        node = self.resolve(node, _seen)
        if not isinstance(node, dict):
            return {}
        if "allOf" in node:
            out = {"properties": {}, "required": []}
            for part in node["allOf"]:
                sub = self.merged(part, _seen)
                out["properties"].update(sub.get("properties", {}))
                out["required"].extend(sub.get("required", []))
                for k, v in sub.items():
                    if k not in ("properties", "required"):
                        out.setdefault(k, v)
            for k, v in node.items():
                if k != "allOf":
                    out[k] = v
            return out
        return node

    def flatten(self, name):
        """Return {dotted_path: field_info} for a named root schema."""
        out = {}
        self._flatten(self.merged({"$ref": f"#/components/schemas/{name}"}), "", out, ())
        return out

    def _flatten(self, schema, prefix, out, seen):
        schema = self.merged(schema, seen)
        if not isinstance(schema, dict):
            return

        branches = []
        for key in ("oneOf", "anyOf"):
            branches.extend(schema.get(key, []))
        for branch in branches:
            self._flatten(branch, prefix, out, seen)

        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        for pname, pschema in props.items():
            path = f"{prefix}.{pname}" if prefix else pname
            resolved = self.merged(pschema, seen)
            info = out.setdefault(path, {
                "path": path,
                "types": set(),
                "required": False,
                "enum": None,
                "minimum": None,
                "maximum": None,
                "format": None,
                "description": (resolved.get("description") or "").strip(),
                "schema_name": resolved.get("x-schema-name"),
                "additional_properties": resolved.get("additionalProperties"),
            })
            declared = resolved.get("type")
            if isinstance(declared, list):
                info["types"].update(declared)
            elif declared:
                info["types"].add(declared)
            if pname in required:
                info["required"] = True
            if resolved.get("enum"):
                info["enum"] = sorted(str(v) for v in resolved["enum"])
            for key in ("minimum", "maximum", "format"):
                if resolved.get(key) is not None:
                    info[key] = resolved[key]

            if resolved.get("type") == "array" or "items" in resolved:
                items = self.merged(resolved.get("items") or {}, seen)
                ipath = f"{path}[]"
                iinfo = out.setdefault(ipath, {
                    "path": ipath, "types": set(), "required": False, "enum": None,
                    "minimum": None, "maximum": None, "format": None,
                    "description": (items.get("description") or "").strip(),
                    "schema_name": items.get("x-schema-name"),
                    "additional_properties": items.get("additionalProperties"),
                })
                itype = items.get("type")
                if isinstance(itype, list):
                    iinfo["types"].update(itype)
                elif itype:
                    iinfo["types"].add(itype)
                if items.get("enum"):
                    iinfo["enum"] = sorted(str(v) for v in items["enum"])
                key = items.get("x-schema-name")
                if key is None or key not in seen:
                    self._flatten(items, ipath, out, seen + ((key,) if key else ()))
            elif isinstance(resolved.get("additionalProperties"), dict):
                # A map keyed by user data (a profile document's ``store``).
                # Census notation collapses those keys to ``{}``; match it.
                value_schema = self.merged(resolved["additionalProperties"], seen)
                mpath = f"{path}.{{}}"
                minfo = out.setdefault(mpath, {
                    "path": mpath, "types": set(), "required": False, "enum": None,
                    "minimum": None, "maximum": None, "format": None,
                    "description": (value_schema.get("description") or "").strip(),
                    "schema_name": value_schema.get("x-schema-name"),
                    "additional_properties": value_schema.get("additionalProperties"),
                })
                vtype = value_schema.get("type")
                if isinstance(vtype, list):
                    minfo["types"].update(vtype)
                elif vtype:
                    minfo["types"].add(vtype)
                key = value_schema.get("x-schema-name")
                if key is None or key not in seen:
                    self._flatten(value_schema, mpath, out, seen + ((key,) if key else ()))
            else:
                key = resolved.get("x-schema-name")
                if key is None or key not in seen:
                    self._flatten(resolved, path, out, seen + ((key,) if key else ()))


def load(repo_root: Path, collection: str):
    filename, root = ROOT_SCHEMA[collection]
    spec = Spec(repo_root / "specs" / "openapi" / filename)
    flat = spec.flatten(root)
    for info in flat.values():
        info["types"] = sorted(info["types"])
    return spec, root, flat
