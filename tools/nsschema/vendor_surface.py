"""vendor_surface.py — what each AID system *can* write to `devicestatus`.

The census says what 11 sites did write. With one AAPS site and one Trio
site, that under-represents both: a field every AAPS install could emit
looks rare, and a field only the newest AAPS emits looks absent. This reads
the vendors' own wire models instead, so "nobody writes this" and "our
corpus has one site of that client" stop being the same observation.

Each source below is a specific file that defines a project's Nightscout
`devicestatus` payload. They are named individually rather than discovered,
because the interesting thing is the *declared contract*, and a repo-wide
grep finds a hundred incidental mentions of `iob` for every declaration.

Three questions get answered by diffing those surfaces against the census
and the spec:

* **under-observed** — a vendor declares it, the corpus never saw it. Either
  our one site of that client does not use the feature, or it is newer than
  the snapshot.
* **undeclared** — the corpus has it and no parsed vendor declares it.
  Usually a vendor we did not parse; occasionally a field nobody documents.
* **unspecified** — observed and/or vendor-declared, absent from
  `specs/openapi/aid-devicestatus-2025.yaml`.
"""

import argparse
import json
import re
from pathlib import Path

from . import corpus, specload

# (label, path under externals/, extraction pattern, note)
SOURCES = [
    ("AndroidAPS",
     "AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/"
     "RemoteDeviceStatus.kt",
     r'@SerializedName\("([^"]+)"\)',
     "AAPS's Nightscout SDK wire model for devicestatus"),
    ("Trio",
     "Trio/Trio/Sources/Models/NightscoutStatus.swift",
     r'^\s*let\s+(\w+)\s*:',
     "Trio's NightscoutStatus and its nested pump/uploader structs",
     # That file also defines Trio's *profile* upload models
     # (ScheduledNightscoutProfile, NightscoutProfileStore,
     # NightscoutPresetOverride). Without this bound, `dia`, `store`,
     # `deviceToken` and `teamID` appear as unobserved devicestatus fields.
     "struct ScheduledNightscoutProfile"),
    ("Trio/determination",
     "Trio/Trio/Sources/Models/Determination.swift",
     "swift-coding-keys",
     "Trio's suggested/enacted determination, the openaps.* payload"),
    ("Trio/iob",
     "Trio/Trio/Sources/Models/IOBEntry.swift",
     "swift-coding-keys",
     "Trio's IOB entry, the openaps.iob payload"),
    ("Loop/NightscoutKit",
     "NightscoutKit/Sources/NightscoutKit/Models/LoopStatus.swift",
     r'rval\["([^"]+)"\]|rawValue\["([^"]+)"\]',
     "Loop's devicestatus `loop` block, via its dictionary representation"),
    ("Loop/NightscoutKit-dose",
     "NightscoutKit/Sources/NightscoutKit/Models/AutomaticDoseRecommendation.swift",
     r'rval\["([^"]+)"\]|rawValue\["([^"]+)"\]',
     "Loop's automatic dose recommendation"),
    ("oref0",
     "oref0/lib/determine-basal/determine-basal.js",
     r'\brT\.(\w+)\s*=',
     "fields oref0's determine-basal sets on its result object"),
    ("oref0/iob",
     "oref0/lib/iob/total.js",
     r'^\s*(?:var\s+)?(\w+)\s*:',
     "fields oref0's IOB total emits"),
]

# Every surface is partial: a project's wire payload is assembled across
# several files, and only the ones named above are read. A field missing
# from a surface means "not in the file we parsed", not "the project never
# writes it".


# A Swift type's wire names live in its CodingKeys enum, not in its property
# declarations: `case tdd = "TDD"` ships as TDD, and a computed property is
# absent from CodingKeys precisely so it is *not* serialized. Reading
# property names instead reported Trio's `tdd` as never-written when the
# corpus carries it as `TDD`, and reported `reasonParts`/`reasonConclusion`
# as wire fields when a comment in that very file says they are excluded so
# the serialized JSON is unchanged.
_CODING_CASE = re.compile(
    r'^\s*case\s+(\w+)(?:\s*=\s*"([^"]+)")?', re.M)


def _swift_coding_keys(text):
    names = set()
    for match in re.finditer(r'enum\s+CodingKeys\b[^{]*\{(.*?)\n\s*\}', text, re.S):
        for prop, wire in _CODING_CASE.findall(match.group(1)):
            names.add(wire or prop)
    return names


def extract(root: Path, rel, pattern, stop_at=None):
    path = root / "externals" / rel
    if not path.is_file():
        return None
    text = path.read_text(errors="replace")
    if stop_at:
        cut = text.find(stop_at)
        if cut > 0:
            text = text[:cut]
    if pattern == "swift-coding-keys":
        keys = _swift_coding_keys(text)
        if keys:
            return sorted(keys)
        # No CodingKeys enum: Swift synthesises Codable from the stored
        # property names, so those are the wire names. Computed properties
        # (`var x: T { ... }`) are not stored and are excluded by requiring
        # a declaration that does not open a block.
        return sorted(set(re.findall(
            r'^\s*(?:let|var)\s+(\w+)\s*:\s*[^{\n]+$', text, re.M)))
    names = set()
    for match in re.finditer(pattern, text, re.M):
        for group in match.groups():
            if group:
                names.add(group)
    return sorted(names)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--census-dir", default="reports/schema-census", type=Path)
    ap.add_argument("--out", default="reports/schema-census/vendor-surface.json",
                    type=Path)
    args = ap.parse_args(argv)

    root = corpus.repo_root()

    census_path = root / args.census_dir / "devicestatus.census.json"
    census = json.loads(census_path.read_text()) if census_path.is_file() else None
    observed_leaves = set()
    observed_freq = {}
    if census:
        for field in census["fields"]:
            leaf = field["path"].split(".")[-1].rstrip("[]")
            observed_leaves.add(leaf)
            observed_freq[leaf] = max(observed_freq.get(leaf, 0.0),
                                      field["doc_frequency"])

    _, _, flat = specload.load(root, "devicestatus")
    declared_leaves = {p.split(".")[-1].rstrip("[]") for p in flat}

    surfaces = {}
    for entry in SOURCES:
        label, rel, pattern, note = entry[:4]
        stop_at = entry[4] if len(entry) > 4 else None
        names = extract(root, rel, pattern, stop_at)
        if names is None:
            print(f"  {label:22s} source not present, skipped")
            continue
        surfaces[label] = {"source": rel, "note": note, "names": names,
                           "truncated_at": stop_at}
        under = sorted(n for n in names if n not in observed_leaves)
        print(f"  {label:22s} {len(names):3d} declared, "
              f"{len(names) - len(under):3d} observed, {len(under):3d} not seen")

    vendor_union = {n for s in surfaces.values() for n in s["names"]}
    report = {
        "generated_by": "tools/nsschema/vendor_surface.py",
        "note": ("Declared wire surfaces, from each project's own model file. "
                 "Names are leaf field names, so a match does not prove the "
                 "same nesting."),
        "surfaces": surfaces,
        "under_observed": {
            label: sorted(n for n in s["names"] if n not in observed_leaves)
            for label, s in surfaces.items()
        },
        "observed_but_undeclared_by_any_parsed_vendor": sorted(
            n for n in observed_leaves if n not in vendor_union),
        "unspecified": sorted(
            (observed_leaves | vendor_union) - declared_leaves),
    }
    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    print(f"\n  observed but no parsed vendor declares it: "
          f"{len(report['observed_but_undeclared_by_any_parsed_vendor'])}")
    print(f"  observed or vendor-declared, absent from the spec: "
          f"{len(report['unspecified'])}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
