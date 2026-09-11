"""sensitivity.py — label every schema field, and project documents by label.

Sensitivity is a property of a *field*, so it belongs where the field is
declared, not in each consumer's scrubber. Labelled once, it rides along in
every artifact generated from the model — JSON Schema, zod, mongoose, Arrow
field metadata, and the controller registration — and the same policy can be
evaluated in three places that today each improvise:

* on the **controller**, before it serialises, so a field a user has not
  consented to share is never put on the wire
* in the **hub**, before it stores or forwards
* at a **delegate's** boundary, before an agent reads

The labels are **derived, not asserted**. The rules in
`specs/sync/sensitivity.yaml` reuse what this repository already learned the
hard way: the redaction denylist, the credential fragments, and whether the
census was able to publish a field's values after cross-site corroboration.
A field the census could publish is vocabulary; one it withheld as
personal-shaped is quasi-identifying; one whose *name* the denylist rejects
is identifying or secret.

**Unlabelled defaults to `identifying`.** A new field must be argued *down*,
never silently up. The opposite default fails open on the next schema
change, which is the failure this whole line of work has been correcting.
"""

import argparse
import json
import re
from pathlib import Path

import yaml

from . import corpus, redact, scan_pii

VOCABULARY = "specs/sync/sensitivity.yaml"

LEVELS = ("secret", "identifying", "quasi-identifying", "descriptive")
_RANK = {level: i for i, level in enumerate(LEVELS)}

# Categories that are quasi-identifying by their nature, whatever the value
# type. A full-precision epoch timestamp is a classic quasi-identifier, and
# the numeric rule below would otherwise call it descriptive purely because
# it is a number — which is how `entries.date` and `mills` first came out
# as freely publishable.
_QUASI_BY_CATEGORY = frozenset({"temporal", "location"})

# A span is not an instant. `duration`, `absorptionTime` and
# `timeAsSeconds` all contain time words and none of them says *when*
# anything happened, so treating them as temporal made them
# quasi-identifying and stripped them from projections that need them —
# a replay cannot price a temp basal without its duration.
_DURATION_LIKE = re.compile(
    r"duration|absorptiontime|timeasseconds|elapsed|"
    r"(minutes|seconds|hours|days|mins)$|^dia$")

# Category inference from a field's leaf name, applied after the level.
_CATEGORY_PATTERNS = (
    ("credential", r"token|secret|password|apikey|api_key|teamid|privatekey"),
    ("identity", r"^_?id$|identifier|^subject$|enteredby|modifiedby|^name$|^title$"),
    ("device", r"device|pump|serial|transmitter|sensor|uploader|manufacturer|model"),
    # A UTC offset is a timezone by another name, so it goes here rather
    # than with the timestamps: it places a person, coarsely, and
    # `pump.secondsFromGMT` otherwise reached an effect-only projection.
    ("location", r"timezone|latitude|longitude|geo|country|locale|utcoffset|secondsfromgmt"),
    ("temporal", r"date|time|mills|clock|timestamp|created|modified|srv|duration"),
    ("health-measurement", r"^sgv$|^mbg$|^carbs$|^insulin$|glucose|bpm|steps|heartrate|noise|filtered|unfiltered"),
    ("health-derived", r"iob|cob|activity|predicted|eventual|insulinreq|sensitivityratio|delta|trend"),
    ("therapy-setting", r"basal|sens|carbratio|target|dia|insulin|carbs|profile|override|max|min|threshold|ratio|percent|rate|multiplier|factor|scale"),
    ("free-text", r"notes?|reason|symbol|label|comment"),
)


def load_vocabulary(root: Path, rel=VOCABULARY):
    vocab = yaml.safe_load((root / rel).read_text())
    known = {level["id"] for level in vocab["sensitivity_levels"]}
    if known != set(LEVELS):
        raise ValueError(f"level vocabulary drifted: {sorted(known)} vs {list(LEVELS)}")
    return vocab


def category_for(path: str) -> str:
    leaf = path.split(".")[-1].rstrip("[]").lower()
    if _DURATION_LIKE.search(leaf):
        return "therapy-setting"
    for category, pattern in _CATEGORY_PATTERNS:
        if re.search(pattern, leaf):
            return category
    return "vocabulary"


def level_for(path: str, field: dict | None) -> tuple[str, str]:
    """Return (level, why) for a census path, from the derivation rules."""
    lower = path.lower()
    if any(fragment in lower for fragment in scan_pii._CREDENTIAL_FRAGMENTS):
        return "secret", "name matches a credential fragment"
    if redact.is_denied(path):
        return "identifying", "name is on the redaction denylist"

    if field is None:
        return "identifying", "not present in the census; unlabelled defaults to identifying"

    string_info = field.get("string") or {}
    if string_info:
        if string_info.get("distinct_values"):
            return ("descriptive",
                    "values survived cross-site corroboration, so they are shared vocabulary")
        note = string_info.get("value_note", "")
        if "personal-shaped" in note:
            return "quasi-identifying", "values were withheld as personal-shaped"
        if "fewer than" in note:
            return ("quasi-identifying",
                    "values appeared on too few sites to be shared vocabulary")
        return "quasi-identifying", f"values withheld: {note or 'unspecified'}"

    if field.get("numeric") or field.get("boolean"):
        return "descriptive", "numeric or boolean measurement"
    return "descriptive", "structural"


def label(path: str, field: dict | None) -> dict:
    """The full label for one field, level and category together."""
    level, why = level_for(path, field)
    category = category_for(path)
    if category in _QUASI_BY_CATEGORY and _RANK[level] > _RANK["quasi-identifying"]:
        level = "quasi-identifying"
        why = f"{why}; raised to quasi-identifying because it is {category}"
    return {"sensitivity": level, "category": category, "why": why}


def label_census(root: Path, census_dir="reports/schema-census"):
    """{collection: {path: {level, category, why}}} for every censused field."""
    labels = {}
    for path in sorted((root / census_dir).glob("*.census.json")):
        census = json.loads(path.read_text())
        labels[census["collection"]] = {
            f["path"]: label(f["path"], f) for f in census["fields"]
        }
    return labels


def admits(profile: dict, label: dict) -> bool:
    """True if a projection profile admits a field with this label."""
    if _RANK[label["sensitivity"]] < _RANK[profile["max_sensitivity"]]:
        return False
    categories = profile["categories"]
    return categories == ["*"] or label["category"] in categories


def project(document, labels, profile, prefix=""):
    """Drop every field the profile does not admit. Unlabelled is dropped.

    Deliberately a whitelist: a path with no label is not admitted, so a
    field added upstream cannot appear in a projection before someone has
    labelled it.
    """
    if isinstance(document, dict):
        out = {}
        for key, value in document.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, (dict, list)):
                inner = project(value, labels, profile, path)
                if inner not in (None, {}, []):
                    out[key] = inner
                continue
            label = labels.get(path)
            if label and admits(profile, label):
                out[key] = value
        return out
    if isinstance(document, list):
        items = [project(v, labels, profile, prefix + "[]") for v in document]
        return [i for i in items if i not in (None, {}, [])]
    return document


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="reports/schema-census/sensitivity.json", type=Path)
    ap.add_argument("--profile", help="summarise what one profile admits")
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    vocab = load_vocabulary(root)
    labels = label_census(root)

    counts = {}
    for collection, fields in labels.items():
        per = {}
        for label in fields.values():
            per[label["sensitivity"]] = per.get(label["sensitivity"], 0) + 1
        counts[collection] = per
        summary = "  ".join(f"{k}={per[k]}" for k in LEVELS if k in per)
        print(f"  {collection:13s} {len(fields):4d} fields   {summary}")

    profiles = {p["id"]: p for p in vocab["profiles"]}
    print("\n  fields admitted by each projection:")
    admitted = {}
    for pid, profile in profiles.items():
        per = {c: sum(1 for lab in f.values() if admits(profile, lab))
               for c, f in labels.items()}
        admitted[pid] = per
        total = sum(per.values())
        every = sum(len(f) for f in labels.values())
        print(f"    {pid:16s} {total:4d} / {every}   " +
              "  ".join(f"{c}={n}" for c, n in sorted(per.items())))

    report = {
        "generated_by": "tools/nsschema/sensitivity.py",
        "vocabulary": VOCABULARY,
        "levels_by_collection": counts,
        "admitted_by_profile": admitted,
        "labels": labels,
    }
    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=1) + "\n")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
