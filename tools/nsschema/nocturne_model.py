"""nocturne_model.py — what does Nocturne's deserializer actually retain?

Nocturne is the most complete typed model of the Nightscout document set
that exists (``reports/schema-census/attribution.json``: 179 of 247 field
names). "Most complete" is not "complete", and the gap matters: a key that
no class declares, in a class with no ``[JsonExtensionData]``, is silently
dropped on deserialization. Not rejected, not logged — gone.

This parses ``Nocturne.Core.Models`` for the wire contract:

* every class, its ``[JsonPropertyName]`` members, and their declared types
* whether the class carries ``[JsonExtensionData]``, i.e. whether unknown
  keys survive
* the type graph, so a wire path like ``pump.battery.percent`` can be
  resolved from a root model down to a leaf

and then answers, for every path the census observed: **retained**,
**captured** by an extension bag, or **dropped**.

This is source analysis, not a running system. A regex over C# is not a
compiler: it recognises the declaration style this codebase actually uses
(``[JsonPropertyName("x")] public T Y { get; set; }``) and reports what it
could not resolve rather than assuming absence means dropped.
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from . import corpus

MODELS_DIR = "externals/nocturne/src/Core/Nocturne.Core.Models"

# Root wire models, by collection.
ROOTS = {
    "entries": "Entry",
    "treatments": "Treatment",
    "devicestatus": "DeviceStatus",
    "profile": "Profile",
}

# Collection types whose element type is what a path descends into.
_GENERIC = re.compile(r"^(?:List|IList|ICollection|IEnumerable|IReadOnlyList|"
                      r"HashSet|Collection)<(.+)>$")
_DICT = re.compile(r"^(?:Dictionary|IDictionary|IReadOnlyDictionary)<[^,]+,\s*(.+)>$")

_CLASS = re.compile(
    r"public\s+(?:sealed\s+|abstract\s+|partial\s+)*class\s+(\w+)"
    r"(?:\s*:\s*([^\{\n]+))?\s*\{", re.M)

# `[JsonPropertyName("x")] ... public T Name { get` — other attributes may
# sit between them (`[JsonConverter(...)]` is common here), and the property
# may be an auto-property (`{ get; set; }`) or have bodies
# (`{ get => ...; set => ...; }`). An earlier version required `{ get;` and
# so reported Entry.date and Profile.srvModified as undeclared, when both are
# expression-bodied properties — the exact style used for every field with a
# fallback chain, which is to say the most interesting ones.
_PROP = re.compile(
    r'\[JsonPropertyName\(\s*"([^"]+)"\s*\)\]'
    r'(?:\s*\[[^\]]*\])*'          # further attributes, e.g. [JsonConverter(...)]
    r'\s*(?:///[^\n]*\n\s*)*'      # doc comments
    r'public\s+(?:virtual\s+|override\s+|required\s+|new\s+|static\s+)*'
    r'([A-Za-z0-9_?<>,\.\[\]]+(?:\s*<[^>]*>)?)\s+(\w+)\s*'
    r'(?=\{|=>)',                    # auto-property, bodied property, or expression-bodied
    re.S)


def _balanced_body(text, start):
    """Return the body of the brace-delimited block beginning at ``start``."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start:]


def parse_models(models_dir: Path):
    """Return {class_name: {'props': {...}, 'extension': bool, 'base': str}}."""
    classes = {}
    for path in sorted(models_dir.rglob("*.cs")):
        if any(part in ("bin", "obj") for part in path.parts):
            continue
        text = path.read_text(errors="replace")
        for match in _CLASS.finditer(text):
            name = match.group(1)
            bases = (match.group(2) or "").strip()
            body = _balanced_body(text, match.end() - 1)
            props = {}
            for json_name, ctype, prop in _PROP.findall(body):
                props[json_name] = {
                    "property": prop,
                    "type": " ".join(ctype.split()).rstrip("?"),
                    "nullable": ctype.strip().endswith("?"),
                }
            if name in classes:
                # Four class names are defined twice in this codebase. Merging
                # rather than overwriting keeps whichever definition declares a
                # property, and records the ambiguity instead of hiding it.
                classes[name]["props"].update(props)
                classes[name]["extension"] |= "[JsonExtensionData]" in body
                classes[name].setdefault("duplicate_definitions", []).append(
                    str(path.name))
                continue
            classes[name] = {
                "props": props,
                "extension": "[JsonExtensionData]" in body,
                "base": bases.split(",")[0].strip() if bases else None,
                "file": str(path.relative_to(models_dir.parents[3])),
            }
    return classes


def _element_type(ctype):
    """Unwrap List<T> / Dictionary<K,V> to the type a path descends into."""
    for pattern in (_GENERIC, _DICT):
        m = pattern.match(ctype)
        if m:
            return m.group(1).strip().rstrip("?")
    return None


def _inherited_props(classes, name, seen=()):
    """A class's own properties plus everything it inherits."""
    entry = classes.get(name)
    if entry is None or name in seen:
        return {}, False
    props = {}
    base = entry.get("base")
    if base and base in classes:
        inherited, base_ext = _inherited_props(classes, base, seen + (name,))
        props.update(inherited)
    else:
        base_ext = False
    props.update(entry["props"])
    return props, entry["extension"] or base_ext


def resolve(classes, root, path):
    """Classify one census path against the model graph.

    Returns (verdict, detail). Verdicts:
      retained  — every segment is a declared property
      captured  — a segment is unknown but its class keeps unknown keys
      dropped   — a segment is unknown and its class does not
      unknown   — the walk left the parsed model set (an enum, a primitive,
                  a type defined outside Nocturne.Core.Models)
    """
    current = root
    for raw in path.split("."):
        arrays = 0
        segment = raw
        while segment.endswith("[]"):
            segment = segment[:-2]
            arrays += 1

        props, extension = _inherited_props(classes, current)
        if current not in classes:
            return "unknown", f"type {current} not parsed (at {segment})"

        if segment == "{}":
            # A map value: the declared dictionary value type.
            continue

        entry = props.get(segment)
        if entry is None:
            return ("captured" if extension else "dropped",
                    f"{segment} not declared on {current}"
                    + ("; class keeps unknown keys" if extension else ""))

        ctype = entry["type"]
        for _ in range(arrays):
            element = _element_type(ctype)
            if element is None:
                break
            ctype = element
        # Descending further only makes sense into a parsed class.
        inner = _element_type(ctype) or ctype
        current = inner

    return "retained", current


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--census-dir", default="reports/schema-census", type=Path)
    ap.add_argument("--out", default="reports/schema-census/nocturne-coverage.json",
                    type=Path)
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    models_dir = root / MODELS_DIR
    if not models_dir.is_dir():
        print(f"{MODELS_DIR} not present; run make bootstrap")
        return 1

    classes = parse_models(models_dir)
    print(f"parsed {len(classes)} classes, "
          f"{sum(len(c['props']) for c in classes.values())} json-named properties, "
          f"{sum(1 for c in classes.values() if c['extension'])} with extension data")

    report = {
        "generated_by": "tools/nsschema/nocturne_model.py",
        "models_dir": MODELS_DIR,
        "classes_parsed": len(classes),
        "classes_with_extension_data": sorted(
            n for n, c in classes.items() if c["extension"]),
        "collections": {},
    }

    for collection, root_class in ROOTS.items():
        census_path = root / args.census_dir / f"{collection}.census.json"
        if not census_path.is_file():
            continue
        census = json.loads(census_path.read_text())
        verdicts = defaultdict(list)
        weighted = defaultdict(int)
        for field in census["fields"]:
            verdict, detail = resolve(classes, root_class, field["path"])
            verdicts[verdict].append({
                "path": field["path"],
                "doc_frequency": field["doc_frequency"],
                "sites": field["site_count"],
                "detail": detail,
            })
            weighted[verdict] += field["docs_present"]
        total_paths = sum(len(v) for v in verdicts.values())
        report["collections"][collection] = {
            "root_class": root_class,
            "paths": total_paths,
            "summary": {k: len(v) for k, v in sorted(verdicts.items())},
            "documents_by_verdict": dict(weighted),
            "dropped": sorted(verdicts["dropped"],
                              key=lambda f: -f["doc_frequency"]),
            "captured": sorted(verdicts["captured"],
                               key=lambda f: -f["doc_frequency"]),
            "unknown": sorted(verdicts["unknown"],
                              key=lambda f: -f["doc_frequency"])[:40],
        }
        counts = report["collections"][collection]["summary"]
        print(f"  {collection:13s} {total_paths:4d} paths  " +
              "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
