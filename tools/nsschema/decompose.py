"""decompose.py — can a granular-primitive model express this corpus?

The extensibility question has three candidate answers, and only one of
them has an implementation to measure against:

* an **extension bag** (`x-aid-extensions`) — keep the four fat
  collections, give vendor fields a named home. Its cost is already
  measured: the rejection rates in `reports/schema-census/impact.json`.
* **tenant-registered custom resources**, CRD-style — no implementation
  exists anywhere in the ecosystem, so it can only be reasoned about.
* **granular primitives** — decompose each fat document into small typed
  records (a bolus, a carb intake, a temp basal, a device event) linked by
  a correlation id. **Nocturne's V4 model is this design, built.**

This module replays Nocturne's own treatment routing over the corpus and
counts what it can and cannot place. The residue — documents that reach the
"skipping decomposition" branch — is the measurement the evaluation needs:
the share of real data a granular model cannot express without an escape
hatch of its own.

The routing is transcribed from
``externals/nocturne/src/API/Nocturne.API/Services/V4/TreatmentDecomposer.cs``
and ``Nocturne.Connectors.Core/Constants/TreatmentTypes.cs``. It is a
faithful *simulation*, not a port: it reproduces the branch a treatment
takes, not the records that branch writes. Where Nocturne consults data it
has and this corpus does not — an uploader identity, a resolved profile —
the simulation says so rather than guessing.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from . import corpus

# Transcribed from TreatmentDecomposer.cs. Comparison is case-insensitive
# there, so it is here.
TEMP_BASAL = {"temp basal", "temp basal start", "tempbasal"}

DEVICE_EVENTS = {
    "sensor start", "sensor change", "sensor stop", "site change",
    "insulin change", "pump battery change", "pod change",
    "reservoir change", "cannula change", "transmitter sensor insert",
    "pump suspend", "pump resume",
}

MEAL_BOLUS = {"meal bolus", "snack bolus", "combo bolus"}
CORRECTION_BOLUS = {"correction bolus", "smb", "automatic bolus"}
PLAIN_BOLUS = {"bolus", "external insulin"}

# Branch -> the V4 primitives that branch produces.
BRANCHES = {
    "temp-basal": ["TempBasal"],
    "profile-switch": ["TherapySettings"],
    "override": ["TherapySettings"],
    "temporary-target": ["TherapySettings"],
    "device-event": ["DeviceEvent"],
    "meal-bolus": ["Bolus", "CarbIntake"],
    "correction-bolus": ["Bolus"],
    "plain-bolus": ["Bolus"],
    "carb-correction": ["CarbIntake"],
    "bg-check": ["BGCheck"],
    "announcement": ["Note"],
    "note": ["Note"],
    "bolus-wizard": ["Bolus", "CarbIntake", "BolusCalculation"],
    "data-fallback": ["Bolus", "CarbIntake"],
    "unroutable": [],
}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def has_insulin(treatment):
    return _number(treatment.get("insulin")) and treatment["insulin"] != 0


def has_carbs(treatment):
    return _number(treatment.get("carbs")) and treatment["carbs"] != 0


def classify(treatment):
    """Return (branch, reason) for one legacy treatment document."""
    event = (treatment.get("eventType") or "").strip()
    low = event.lower()

    if low in TEMP_BASAL:
        return "temp-basal", "eventType"
    if low == "profile switch":
        return "profile-switch", "eventType"
    if low == "temporary override":
        return "override", "eventType"
    if low in ("temporary target", "temporary target cancel"):
        return "temporary-target", "eventType"
    if low in DEVICE_EVENTS:
        return "device-event", "eventType"
    if low in MEAL_BOLUS:
        return "meal-bolus", "eventType"
    if low in CORRECTION_BOLUS:
        return "correction-bolus", "eventType"
    if low in PLAIN_BOLUS:
        return "plain-bolus", "eventType"
    if low == "carb correction":
        return "carb-correction", "eventType"
    if low == "bg check":
        return "bg-check", "eventType"
    if low == "announcement":
        return "announcement", "eventType"
    if low in ("note", "exercise"):
        return "note", "eventType"
    if low == "bolus wizard":
        return "bolus-wizard", "eventType"

    # Unrecognised event type: Nocturne falls back to the data present.
    if has_insulin(treatment) or has_carbs(treatment):
        return "data-fallback", "insulin/carbs present"

    # "Unknown event type ... with no insulin/carbs, skipping decomposition"
    return "unroutable", "no recognised event type and no insulin or carbs"


# Fields the V4 primitives carry, so "what is lost" can be separated from
# "what is carried". Derived from the V4 model surface; a field not here is
# not necessarily dropped by Nocturne (ExtensionData catches unknown keys),
# but it has no typed home.
TYPED_FIELDS = {
    "_id", "eventType", "created_at", "timestamp", "mills", "date", "utcOffset",
    "insulin", "carbs", "programmed", "duration", "durationInMilliseconds",
    "absolute", "rate", "percent", "temp", "amount", "unabsorbed", "type",
    "glucose", "glucoseType", "units", "notes", "reason", "enteredBy",
    "syncIdentifier", "identifier", "id", "device", "profile", "profileJson",
    "targetTop", "targetBottom", "correctionRange", "insulinNeedsScaleFactor",
    "insulinType", "automatic", "isSMB", "isValid", "fat", "protein",
    "foodType", "absorptionTime", "preBolus", "splitNow", "splitExt",
}


def run(sources, max_docs=None):
    branches = Counter()
    reasons = Counter()
    per_site = defaultdict(Counter)
    unroutable_event_types = Counter()
    untyped_fields = Counter()
    total = 0

    for src in sources:
        if src.collection != "treatments":
            continue
        seen = 0
        for treatment in corpus.iter_documents(src.path):
            branch, reason = classify(treatment)
            branches[branch] += 1
            reasons[(branch, reason)] += 1
            per_site[src.site][branch] += 1
            total += 1
            if branch == "unroutable":
                unroutable_event_types[(treatment.get("eventType") or "<absent>")] += 1
            for key in treatment:
                if key not in TYPED_FIELDS:
                    untyped_fields[key] += 1
            seen += 1
            if max_docs and seen >= max_docs:
                break

    return {
        "generated_by": "tools/nsschema/decompose.py",
        "source": ("externals/nocturne/src/API/Nocturne.API/Services/V4/"
                   "TreatmentDecomposer.cs"),
        "documents": total,
        "branches": {
            name: {
                "documents": branches[name],
                "share": round(branches[name] / total, 6) if total else 0.0,
                "produces": BRANCHES[name],
            }
            for name in sorted(branches, key=lambda n: -branches[n])
        },
        "routed_by_event_type": sum(
            n for (branch, reason), n in reasons.items() if reason == "eventType"),
        "routed_by_data_fallback": branches["data-fallback"],
        "unroutable": branches["unroutable"],
        "unroutable_share": round(branches["unroutable"] / total, 6) if total else 0.0,
        "unroutable_event_types": dict(unroutable_event_types.most_common(20)),
        "fields_without_a_typed_home": dict(untyped_fields.most_common(30)),
        "per_site": {site: dict(counts) for site, counts in sorted(per_site.items())},
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="reports/schema-census/decomposition.json",
                    type=Path)
    ap.add_argument("--max-docs", type=int, default=None)
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    result = run(corpus.discover(root), args.max_docs)

    print(f"{result['documents']:,} treatments")
    for name, info in result["branches"].items():
        produces = ", ".join(info["produces"]) or "(nothing)"
        print(f"  {name:18s} {info['share']:7.2%}  {info['documents']:>7,}  -> {produces}")
    print(f"\n  routed by eventType : {result['routed_by_event_type']:,}")
    print(f"  routed by data      : {result['routed_by_data_fallback']:,}")
    print(f"  unroutable          : {result['unroutable']:,} "
          f"({result['unroutable_share']:.2%})")
    if result["unroutable_event_types"]:
        print("  unroutable eventTypes:",
              ", ".join(f"{k}={v}" for k, v in
                        list(result["unroutable_event_types"].items())[:8]))

    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=1) + "\n")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
