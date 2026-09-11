"""primitives.py — the primitive catalogue, with evidence grading per field.

Five documents in this series *reference* a set of primitives — the
registrations list `decomposesTo: [Bolus, CarbIntake, TempBasal, ...]`, the
sync design decomposes into them, the effects model sits beside them — and
none of them ever said what those primitives are. This generates the
catalogue, and grades every field by what backs it, because "we have
primitives" and "we have evidence for primitives" are different claims and
the difference is the whole question.

Grades, per field:

``measured``
    A wire path in the corpus populates it. The strongest grade: something
    real writes it and we counted how often.
``declared``
    A typed model declares it and no observed wire path matches by name.
    Either the corpus lacks a client that writes it, or it is computed
    server-side, or the name-level match missed. Real, unverified.
``proposed``
    *We* are proposing it, from the dosing-input map, and no shipped model
    has it. Every one of these is a request to somebody.

Field matching against the corpus is **by leaf name**, with the same caveat
as `attribute.py`: a name-level match is evidence, not proof, and generic
names are flagged rather than counted.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import yaml

from . import corpus, nocturne_model

V4_DIR = "externals/nocturne/src/Core/Nocturne.Core.Models/V4"
CORE_DIR = "externals/nocturne/src/Core/Nocturne.Core.Models"

# The primitives the registrations name, grouped by what they represent.
CATALOGUE = {
    "observation": {
        "SensorGlucose": "A CGM reading.",
        "BGCheck": "A fingerstick or meter reading.",
    },
    "delivery": {
        "Bolus": "A discrete insulin dose, manual or algorithm-initiated.",
        "TempBasal": "A temporary basal rate for a bounded interval.",
        "CarbIntake": "A carbohydrate entry.",
    },
    "decision": {
        "ApsSnapshot": "One controller cycle: the state it saw and what it "
                       "decided. The record a replay is checked against.",
    },
    "device": {
        "PumpSnapshot": "Pump state at a point in time.",
        "UploaderSnapshot": "The uploading device's own state.",
        "DeviceEvent": "A site change, sensor start, cartridge change.",
    },
    "settings": {
        "TherapySettings": "The therapy configuration in force.",
        "BasalSchedule": "Scheduled basal rates by time of day.",
        "CarbRatioSchedule": "Carb ratio by time of day.",
        "SensitivitySchedule": "Insulin sensitivity by time of day.",
        "TargetRangeSchedule": "Glucose targets by time of day.",
    },
    "narrative": {
        "Note": "Free text attached to a time.",
    },
    "state": {
        "StateSpan": "A time-ranged state: pump mode, override, data "
                     "exclusion. The state machine, not a point event.",
    },
}

# Nocturne's decomposers state the mapping outright — `Iob = ds.OpenAps.Iob?.Iob`
# — so the strongest evidence for "what populates this field" is its own
# source, not a guess. Parsing those assignments fixes two systematic
# undercounts in name-level matching: V4 deliberately *renames* on the way in
# (`Mgdl` from `sgv`, `Entries` from `basal[]`), which is the model doing its
# job, and a generic name like `programmed` was being suppressed even where
# the corpus plainly carries it.
DECOMPOSERS = (
    "externals/nocturne/src/API/Nocturne.API/Services/V4/DeviceStatusDecomposer.cs",
    "externals/nocturne/src/API/Nocturne.API/Services/V4/TreatmentDecomposer.cs",
    "externals/nocturne/src/API/Nocturne.API/Services/V4/ProfileDecomposer.cs",
    "externals/nocturne/src/API/Nocturne.API/Services/V4/ActivityDecomposer.cs",
    "externals/nocturne/src/API/Nocturne.API/Services/V4/EntryDecomposer.cs",
)

# `Field = ds.Openaps.Iob?.Iob,` / `Field = treatment.Carbs ?? 0,`
_ASSIGN = re.compile(
    r"^\s*(\w+)\s*=\s*"
    r"(?:\w+\()?"                                   # an optional helper call
    r"([A-Za-z_][\w?.]*(?:\.[\w?]+)+)", re.M)


def _decomposer_sources(root: Path):
    """{primitive field name: set of dotted source expressions}"""
    found = {}
    for rel in DECOMPOSERS:
        path = root / rel
        if not path.is_file():
            continue
        for field, expr in _ASSIGN.findall(path.read_text(errors="replace")):
            cleaned = expr.replace("?", "")
            parts = cleaned.split(".")
            # Drop the receiver (ds/treatment/profile) and keep the wire path.
            if len(parts) < 2:
                continue
            found.setdefault(field, set()).add(".".join(parts[1:]))
    return found


# Names too generic for a leaf-name match to mean anything on its own.
GENERIC = frozenset({
    "id", "type", "date", "time", "value", "name", "status", "device", "units",
    "version", "duration", "rate", "percent", "reason", "notes", "start", "end",
    "timestamp", "created", "enabled", "state", "mode", "amount", "source",
    "metadata", "kind", "delivered", "programmed", "active",
})

_PROP = re.compile(
    r'public\s+(?:virtual\s+|override\s+|required\s+|static\s+)*'
    r'([A-Za-z0-9_?<>,\.\[\]]+)\s+(\w+)\s*(?=\{|=>)')

# Bookkeeping every V4 record carries; not domain content.
INFRASTRUCTURE = frozenset({
    "Id", "CorrelationId", "LegacyId", "DataSource", "SyncIdentifier",
    "CreatedAt", "UpdatedAt", "DeviceId", "PatientDeviceId", "ProfileId",
    "OriginalId", "SupersededById", "CanonicalId", "Sources", "IsValid",
})


def _snake(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower().replace("__", "_")


def _leaf_index(root: Path, census_dir="reports/schema-census"):
    """{normalised leaf name: [(collection, path, doc_frequency, sites)]}"""
    index = {}
    for path in sorted((root / census_dir).glob("*.census.json")):
        census = json.loads(path.read_text())
        for field in census["fields"]:
            leaf = field["path"].split(".")[-1].rstrip("[]")
            if not leaf or leaf == "{}":
                continue
            key = leaf.lower().replace("_", "")
            index.setdefault(key, []).append({
                "collection": census["collection"],
                "path": field["path"],
                "doc_frequency": field["doc_frequency"],
                "sites": field["site_count"],
            })
    return index


def _properties(path: Path):
    if not path.is_file():
        return None
    text = path.read_text(errors="replace")
    out = []
    for ctype, name in _PROP.findall(text):
        if name in INFRASTRUCTURE or ctype in ("class", "enum", "record"):
            continue
        out.append({"name": name, "type": ctype.rstrip("?"),
                    "nullable": ctype.endswith("?")})
    return out


def build(root: Path):
    index = _leaf_index(root)
    assignments = _decomposer_sources(root)
    dosing = yaml.safe_load(
        (root / "specs/nsschema/dosing-input-sources.yaml").read_text())
    proposed = {e["input"].split(".")[-1].lower(): e
                for e in dosing["inputs"] if e["kind"] in ("absent", "partial")}

    catalogue = {}
    for group, members in CATALOGUE.items():
        for name, description in members.items():
            source = root / V4_DIR / f"{name}.cs"
            if not source.is_file():
                source = root / CORE_DIR / f"{name}.cs"
            props = _properties(source)
            if props is None:
                catalogue[name] = {"group": group, "description": description,
                                   "typed_by": None, "fields": []}
                continue

            fields = []
            for prop in props:
                key = prop["name"].lower().replace("_", "")
                matches = index.get(key, [])
                generic = key in GENERIC or len(key) < 3
                mapped = sorted(assignments.get(prop["name"], ()))

                # A decomposer assignment naming a path the corpus carries is
                # the strongest evidence available: the model says where the
                # value comes from, and the corpus says it is there.
                mapped_observed = [
                    m for m in mapped
                    if index.get(m.split(".")[-1].lower().replace("_", ""))]
                if mapped_observed:
                    grade = "measured"
                    why = f"decomposer maps it from {mapped_observed[0]}"
                elif matches and not generic:
                    grade = "measured"
                    why = (f"{matches[0]['collection']}.{matches[0]['path']} "
                           f"on {matches[0]['sites']} sites")
                elif matches and generic:
                    grade = "measured"
                    why = ("leaf name matches the corpus but is generic; "
                           "treat as weak evidence")
                elif mapped:
                    grade = "declared"
                    why = (f"decomposer maps it from {mapped[0]}, which this "
                           "corpus does not carry")
                else:
                    grade = "declared"
                    why = "typed model only; no observed path"

                entry = {
                    "name": prop["name"],
                    "wire_name": _snake(prop["name"]) if "_" not in prop["name"]
                    else prop["name"],
                    "type": prop["type"],
                    "nullable": prop["nullable"],
                    "evidence": grade,
                    "why": why,
                }
                if generic and grade == "measured" and not mapped_observed:
                    entry["low_confidence"] = True
                if mapped:
                    entry["mapped_from"] = mapped[:3]
                if matches and not generic:
                    entry["observed"] = matches[:2]
                fields.append(entry)
            catalogue[name] = {
                "group": group, "description": description,
                "typed_by": f"Nocturne V4 {source.name}",
                "fields": fields,
            }

    # Fields we are proposing that no shipped primitive carries.
    covered = {f["name"].lower() for p in catalogue.values() for f in p["fields"]}
    gaps = []
    for key, entry in sorted(proposed.items()):
        if key not in covered:
            gaps.append({
                "field": entry["input"],
                "algorithm": entry.get("algorithm", "oref0"),
                "status_today": entry["kind"],
                "evidence": "proposed",
                "why": entry.get("note", "").strip()[:160] or
                       "a dosing input no controller publishes",
            })
    return catalogue, gaps


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="specs/sync/primitives.yaml", type=Path)
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    catalogue, gaps = build(root)

    grades = Counter()
    for primitive in catalogue.values():
        for field in primitive["fields"]:
            grades[field["evidence"]] += 1

    print(f"{len(catalogue)} primitives, "
          f"{sum(len(p['fields']) for p in catalogue.values())} fields")
    for name, primitive in catalogue.items():
        per = Counter(f["evidence"] for f in primitive["fields"])
        detail = "  ".join(f"{k}={v}" for k, v in sorted(per.items()))
        print(f"  {name:22s} {primitive['group']:12s} "
              f"{len(primitive['fields']):3d} fields   {detail}")
    print(f"\n  grades: " + "  ".join(f"{k}={v}" for k, v in sorted(grades.items())))
    print(f"  proposed fields no primitive carries: {len(gaps)}")

    document = {
        "version": "0.1-draft",
        "generated_by": "tools/nsschema/primitives.py",
        "status": ("Draft. Grades are evidence, not endorsement: `measured` "
                   "means a wire path in this corpus populates the field, "
                   "`declared` that a typed model has it and this corpus does "
                   "not show it, `proposed` that we are asking for it."),
        "grades": dict(grades),
        "primitives": catalogue,
        "proposed_not_carried_by_any_primitive": gaps,
    }
    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(document, sort_keys=False, width=96))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
