"""settings_schema.py — generate the ControllerSettings document schema.

Phase 1 of the roadmap is "agree a schema for the `settings` collection
cgm-remote-monitor already enables". Five documents in this series asked for
it and none of them wrote it. This does.

The field list is not invented: it is every entry in
`specs/nsschema/dosing-input-sources.yaml` that is a *configuration* input —
the values a controller holds and a replay needs — plus the identity and
effective-dating a settings document needs to be usable at all.

Types cannot be derived from a name list, so they are declared here with the
source they were read from: Loop's from `AlgorithmInput.swift`, the oref0
family's from oref0's own profile handling and AAPS's preference keys. Each
carries `x-source` so a reviewer can check it rather than trust it.

A settings document answers one question: **at this moment, what was the
controller configured to do?** Everything in it is therefore
effective-dated and build-versioned, because a setting that changed
mid-history invalidates a replay that assumed one value.
"""

import argparse
import json
from pathlib import Path

import yaml

from . import corpus

# (json type, unit, source) for every configuration input. `None` unit means
# dimensionless. The source is what a reviewer should check.
LOOP_SRC = "LoopAlgorithm/Sources/LoopAlgorithm/AlgorithmInput.swift"
OREF_SRC = "oref0 profile / AAPS preference keys"

FIELD_TYPES = {
    # Loop, from the AlgorithmInput protocol.
    "maxBolus": ("number", "U", LOOP_SRC),
    "maxBasalRate": ("number", "U/hr", LOOP_SRC),
    "suspendThreshold": ("number", "mg/dL", LOOP_SRC),
    "maxActiveInsulinMultiplier": ("number", None, LOOP_SRC),
    "automaticBolusApplicationFactor": ("number", None, LOOP_SRC),
    "carbAbsorptionModel": ("string", None, LOOP_SRC),
    "recommendationInsulinModel": ("string", None, LOOP_SRC),
    "recommendationType": ("string", None, LOOP_SRC),
    "useIntegralRetrospectiveCorrection": ("boolean", None, LOOP_SRC),
    "includePositiveVelocityAndRC": ("boolean", None, LOOP_SRC),
    "useMidAbsorptionISF": ("boolean", None, LOOP_SRC),
    "gradualTransitionsThreshold": ("number", None, LOOP_SRC),
    # oref0 family.
    "maxIob": ("number", "U", OREF_SRC),
    "maxBasal": ("number", "U/hr", OREF_SRC),
    "maxDailyBasal": ("number", "U/hr", OREF_SRC),
    "dia": ("number", "hours", OREF_SRC),
    "microBolusAllowed": ("boolean", None, OREF_SRC),
    "dosingStrategy": ("string", None, OREF_SRC),
    "units": ("string", None, OREF_SRC),
}

# Inputs that are per-cycle state, not configuration. They belong in an
# ApsSnapshot, not in a settings document, and listing why keeps the
# boundary from drifting.
NOT_CONFIGURATION = {
    "flatBGsDetected": "a per-cycle observation",
    "mealData.mealCOB": "per-cycle meal state",
    "mealData.slopeFromMaxDeviation": "per-cycle meal-detection state",
    "mealData.slopeFromMinDeviation": "per-cycle meal-detection state",
    "iob.bolusSnooze": "per-cycle IOB component",
    "iob.iobWithZeroTemp.bolussnooze": "per-cycle IOB component",
    "profile.basalRate": "the scheduled value lives in BasalSchedule",
    "profile.sensitivity": "the effective value is per-cycle; the schedule is SensitivitySchedule",
    "profile.carbRatio": "likewise CarbRatioSchedule",
    "profile.targetLow": "likewise TargetRangeSchedule",
    "profile.targetHigh": "likewise TargetRangeSchedule",
}


def build(root: Path):
    dosing = yaml.safe_load(
        (root / "specs/nsschema/dosing-input-sources.yaml").read_text())

    properties, unmapped, excluded = {}, [], []
    for entry in dosing["inputs"]:
        name = entry["input"]
        if name in NOT_CONFIGURATION:
            excluded.append({"input": name, "why": NOT_CONFIGURATION[name]})
            continue
        leaf = name.split(".")[-1]
        spec = FIELD_TYPES.get(leaf)
        if spec is None:
            continue
        json_type, unit, source = spec
        prop = {
            "type": json_type,
            "description": (entry.get("note") or "").strip() or
                           f"{leaf}, a {entry['algorithm']} dosing input.",
            "x-source": source,
            "x-status-today": entry["kind"],
            "x-algorithm": entry["algorithm"],
        }
        if unit:
            prop["x-unit"] = unit
        if json_type == "number":
            prop["minimum"] = 0
        # Already-published settings name where they are found today.
        if entry["kind"] in ("recorded", "partial") and entry.get("sources"):
            prop["x-published-today-as"] = entry["sources"][0]
        properties.setdefault(leaf, prop)

    for leaf in FIELD_TYPES:
        if leaf not in properties:
            unmapped.append(leaf)

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://nightscout.dev/schemas/sync/controller-settings.json",
        "title": "ControllerSettings",
        "description": (
            "What a controller was configured to do, at a moment in time. "
            "Written to the `settings` collection, which cgm-remote-monitor "
            "already enables on v3 — so this needs no new endpoint. Publish on "
            "change, not per cycle. Everything here is effective-dated and "
            "build-versioned, because a setting that changed mid-history "
            "invalidates a replay that assumed one value."),
        "type": "object",
        "required": ["effectiveFrom", "controller", "settings"],
        "additionalProperties": False,
        "properties": {
            "effectiveFrom": {
                "type": "string", "format": "date-time",
                "description": "When these settings took effect. Not when the "
                               "document was written.",
            },
            "effectiveUntil": {
                "type": ["string", "null"], "format": "date-time",
                "description": "Null while current.",
            },
            "controller": {
                "type": "object",
                "required": ["product", "version"],
                "additionalProperties": False,
                "properties": {
                    "vendor": {"type": "string"},
                    "product": {"type": "string"},
                    "version": {
                        "type": "string",
                        "description": "The build. Algorithm behaviour changes "
                                       "between releases, so a setting without "
                                       "one cannot be replayed against the "
                                       "right code.",
                    },
                    "algorithmFamily": {"enum": ["oref0", "loop", "other"]},
                },
            },
            "settings": {
                "type": "object",
                "description": ("Every member optional: a controller publishes "
                                "what it has. Absent means not published, which "
                                "is different from a default — and is exactly "
                                "what a replay needs to know."),
                "additionalProperties": True,
                "properties": dict(sorted(properties.items())),
            },
            "x-aid-extensions": {
                "type": "object",
                "description": "Vendor settings with no agreed name yet.",
                "additionalProperties": True,
            },
        },
    }
    return schema, unmapped, excluded


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="specs/sync/controller-settings.schema.json",
                    type=Path)
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    schema, unmapped, excluded = build(root)
    properties = schema["properties"]["settings"]["properties"]

    by_status = {}
    for name, prop in properties.items():
        by_status.setdefault(prop["x-status-today"], []).append(name)

    print(f"ControllerSettings: {len(properties)} settings")
    for status in ("recorded", "partial", "derivable", "absent"):
        names = by_status.get(status, [])
        if names:
            print(f"  {status:10s} {len(names):2d}  {', '.join(sorted(names))}")
    print(f"\n  excluded as per-cycle state, not configuration: {len(excluded)}")
    if unmapped:
        print(f"  typed here but not in the dosing map: {unmapped}")

    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(schema, indent=1) + "\n")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
