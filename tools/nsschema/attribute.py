"""attribute.py — which client writes which field?

The census says a field exists on N sites. It cannot say *which software
put it there*, because a Nightscout document does not carry that
provenance. This closes the gap from the other side: it searches the
ecosystem's source code in ``externals/`` for evidence that a project
serializes a given field name.

Evidence is graded, because a bare quoted string is weak and a
serialization annotation is strong:

``serialized``
    The field appears in an explicit wire-format declaration —
    ``@SerializedName("x")`` (Kotlin/Java), ``case x = "y"`` in a Swift
    ``CodingKeys``, ``[JsonPropertyName("x")]`` (C#). The project
    demonstrably reads or writes that field on the wire.
``keyed``
    The name is used as a dictionary key or a subscript — ``"sgv": sgv`` in
    a Swift literal, ``rawValue["sgv"]`` on the way back in. This is how
    Loop and LoopKit actually serialize Nightscout documents, so without
    this tier Loop looks like it barely touches the schema it defined.
``quoted``
    The name appears as a quoted string literal. Usually a dictionary key
    or a JSON path; sometimes a comment or an unrelated coincidence.
``absent``
    Not found.

What this is **not**: proof of authorship. A project that *reads* a field
matches exactly like one that *writes* it, and a common word like ``type``
or ``date`` matches everywhere. Short and generic names are flagged as
low-confidence rather than silently reported as findings, and the counts
are published so a reader can judge.

Usage::

    python3 -m nsschema.attribute --out reports/schema-census/attribution.json
"""

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from . import corpus, specload

# Project -> (path under externals/, source globs). Ordered so the report
# reads as producers first, then servers and bridges.
PROJECTS = [
    ("Loop", "LoopWorkspace", ("*.swift",)),
    ("Trio", "Trio", ("*.swift",)),
    ("AndroidAPS", "AndroidAPS", ("*.kt", "*.java")),
    ("xDrip4iOS", "xdripswift", ("*.swift",)),
    ("xDrip+", "xDrip", ("*.java",)),
    ("LoopFollow", "LoopFollow", ("*.swift",)),
    ("LoopCaregiver", "LoopCaregiver", ("*.swift",)),
    ("Nightguard", "nightguard", ("*.swift",)),
    ("DiaBLE", "DiaBLE", ("*.swift",)),
    ("NightscoutKit", "NightscoutKit", ("*.swift",)),
    ("oref0", "oref0", ("*.js",)),
    ("openaps", "openaps", ("*.py", "*.js")),
    ("cgm-remote-monitor", "cgm-remote-monitor-official", ("*.js",)),
    ("Nocturne", "nocturne", ("*.cs",)),
    ("nightscout-connect", "nightscout-connect", ("*.js",)),
    ("share2nightscout", "share2nightscout-bridge", ("*.js",)),
    ("minimed-connect", "minimed-connect-to-nightscout", ("*.js",)),
    ("librelink-up", "nightscout-librelink-up", ("*.ts", "*.js")),
    ("tconnectsync", "tconnectsync", ("*.py",)),
    ("nightscout-reporter", "nightscout-reporter", ("*.dart",)),
]

# Directories that hold other people's code or build output.
EXCLUDES = (
    "node_modules", "build", ".build", "Pods", "dist", "vendor",
    "DerivedData", "Carthage", "__pycache__", ".git",
)

# Serialization annotations, by ecosystem. `{}` is the field name.
SERIALIZED_PATTERNS = (
    r'@SerializedName\(\s*"{}"',          # Kotlin / Java (gson)
    r'@Json\w*\(\s*"{}"',                 # Kotlin (moshi / kotlinx)
    r'case\s+\w+\s*=\s*"{}"',             # Swift CodingKeys
    r'\[JsonPropertyName\(\s*"{}"',       # C#
    r'JsonProperty\(\s*"{}"',             # C#
    r'@JsonKey\(\s*name:\s*"{}"',         # Dart
)

# Dictionary-key and subscript use: weaker than an annotation, far stronger
# than a bare quoted string.
KEYED_PATTERNS = (
    r'"{}"\s*:',                          # "sgv": value   (Swift/JS/Dart)
    r'\[\s*"{}"\s*\]',                    # rawValue["sgv"]
    r"'{}'\s*:",                          # 'sgv': value   (JS/Python)
    r"\[\s*'{}'\s*\]",
)

# Names too generic for a source match to mean anything on its own.
GENERIC = frozenset({
    "id", "type", "date", "time", "value", "name", "status", "device",
    "units", "version", "duration", "rate", "percent", "reason", "notes",
    "start", "end", "timestamp", "created", "enabled", "state", "mode",
    "high", "low", "target", "profile", "settings", "store", "battery",
    "clock", "model", "display", "delta", "trend", "direction", "amount",
})
# `sgv`, `mbg`, `cob`, `iob` are three letters and are the most distinctive
# names in the vocabulary. Length is a weak proxy for ambiguity; the GENERIC
# list above is the real filter.
MIN_NAME_LEN = 3


def leaf_names(census_dir: Path, collections):
    """Distinct leaf field names across the censused collections."""
    names = {}
    for collection in collections:
        path = census_dir / f"{collection}.census.json"
        if not path.is_file():
            continue
        data = json.loads(path.read_text())
        for field in data["fields"]:
            leaf = field["path"].split(".")[-1].rstrip("[]")
            if not leaf or leaf == "{}":
                continue
            entry = names.setdefault(leaf, {"collections": set(), "paths": set()})
            entry["collections"].add(collection)
            entry["paths"].add(field["path"])
    return names


def _rg(root: Path, pattern, globs, fixed=False):
    """Count matching files and lines under ``root``; empty on no match."""
    cmd = ["rg", "--no-messages", "--count-matches", "--no-heading"]
    if fixed:
        cmd.append("--fixed-strings")
    for glob in globs:
        cmd += ["--glob", glob]
    for skip in EXCLUDES:
        cmd += ["--glob", f"!**/{skip}/**"]
    cmd += ["--", pattern, str(root)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        return 0, 0
    lines = [ln for ln in result.stdout.splitlines() if ":" in ln]
    hits = sum(int(ln.rsplit(":", 1)[1]) for ln in lines if ln.rsplit(":", 1)[1].isdigit())
    return len(lines), hits


def scan_project(root: Path, globs, names):
    """Return {name: {'evidence':…, 'files':…, 'hits':…}} for one project."""
    out = {}
    escaped = {n: re.escape(n) for n in names}
    for name in names:
        files, hits = _rg(root, f'"{name}"', globs, fixed=True)
        if not hits:
            continue
        evidence = "quoted"
        for tier, patterns in (("serialized", SERIALIZED_PATTERNS),
                               ("keyed", KEYED_PATTERNS)):
            for template in patterns:
                sfiles, shits = _rg(root, template.format(escaped[name]), globs)
                if shits:
                    evidence, files, hits = tier, sfiles, shits
                    break
            if evidence != "quoted":
                break
        out[name] = {"evidence": evidence, "files": files, "hits": hits}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--census-dir", default="reports/schema-census", type=Path)
    ap.add_argument("--out", default="reports/schema-census/attribution.json", type=Path)
    ap.add_argument("--project", action="append", dest="projects")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    collections = list(specload.ROOT_SCHEMA) + ["settings"]
    names = leaf_names(root / args.census_dir, collections)
    print(f"{len(names)} distinct leaf field names from the census")

    projects = [p for p in PROJECTS if not args.projects or p[0] in args.projects]
    by_project = {}
    for label, directory, globs in projects:
        project_root = root / "externals" / directory
        if not project_root.is_dir():
            print(f"  {label}: absent from externals/, skipped")
            continue
        found = scan_project(project_root, globs, names)
        by_project[label] = found
        strong = sum(1 for v in found.values() if v["evidence"] == "serialized")
        keyed = sum(1 for v in found.values() if v["evidence"] == "keyed")
        print(f"  {label:20s} {len(found):4d} matched  {strong:4d} serialized  "
              f"{keyed:4d} keyed")

    by_name = defaultdict(dict)
    for label, found in by_project.items():
        for name, info in found.items():
            by_name[name][label] = info

    fields = []
    for name, entry in sorted(names.items()):
        matches = by_name.get(name, {})
        generic = name.lower() in GENERIC or len(name) < MIN_NAME_LEN
        serialized = sorted(p for p, i in matches.items() if i["evidence"] == "serialized")
        keyed = sorted(p for p, i in matches.items() if i["evidence"] == "keyed")
        quoted = sorted(p for p, i in matches.items() if i["evidence"] == "quoted")
        fields.append({
            "name": name,
            "collections": sorted(entry["collections"]),
            "paths": sorted(entry["paths"])[:8],
            "low_confidence": generic,
            "serialized_by": serialized,
            "keyed_by": keyed,
            "quoted_by": quoted,
            # The projects with evidence strong enough to attribute on.
            "attributed_to": sorted(set(serialized) | set(keyed)),
            "project_count": len(matches),
            "detail": {p: i for p, i in sorted(matches.items())},
        })

    report = {
        "generated_by": "tools/nsschema/attribute.py",
        "projects": [p[0] for p in projects],
        "field_names": len(names),
        "note": ("Source-code evidence that a project serializes a field name. "
                 "A project that reads a field matches identically to one that "
                 "writes it; generic names are flagged low_confidence."),
        "fields": fields,
    }
    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
