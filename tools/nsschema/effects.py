"""effects.py — can a temporary effect be separated from its motivation?

Every controller has a way to say "for the next N minutes, dose
differently". They do not agree on what that is, where it goes, or what it
carries — and the difference decides two things at once:

* whether a replay can reconstruct the dose (it needs the **effect**: the
  multiplier, the target, the duration)
* whether a record can be shared without disclosing why (it needs the
  effect **without** the motivation: the preset name, the reason, the note)

Those two requirements point the same way, which is the useful part. A
representation that separates the effect from the motivation serves replay
*and* privacy, and the corpus shows the separation already half-exists.

This classifies every temporary-effect record in the corpus as carrying:

``effect+motivation``  both — separable, and the interesting case
``effect-only``        the dose is reconstructible, nothing to redact
``motivation-only``    a label and a duration, and no idea what it did
``neither``            a marker

`motivation-only` is the finding. A record that says "Exercise, 90 minutes"
tells a reviewer why but not what, so it can be neither replayed nor
usefully anonymised — the only thing it carries is the sensitive half.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from . import corpus

# eventTypes that express a temporary dosing effect, across the three
# controllers' vocabularies.
EFFECT_EVENTS = {
    "temporary override", "exercise", "temporary target",
    "temporary target cancel", "profile switch",
}

# Fields that carry the *effect*: what the dose becomes.
EFFECT_FIELDS = (
    "insulinNeedsScaleFactor", "correctionRange", "targetTop", "targetBottom",
    "percentage", "percent", "multiplier", "timeshift", "profile",
)

# Fields that carry the *motivation*: why the user asked for it.
MOTIVATION_FIELDS = ("reason", "notes", "name", "symbol")


def classify(doc, effect_fields=EFFECT_FIELDS, motivation_fields=MOTIVATION_FIELDS):
    has_effect = any(doc.get(f) not in (None, "") for f in effect_fields)
    has_motivation = any(doc.get(f) not in (None, "") for f in motivation_fields)
    if has_effect and has_motivation:
        return "effect+motivation"
    if has_effect:
        return "effect-only"
    if has_motivation:
        return "motivation-only"
    return "neither"


def run(sources):
    treatments = defaultdict(Counter)
    by_event = defaultdict(Counter)
    device_status = defaultdict(Counter)

    for src in sources:
        if src.collection == "treatments":
            for doc in corpus.iter_documents(src.path):
                event = (doc.get("eventType") or "").strip().lower()
                if event not in EFFECT_EVENTS:
                    continue
                verdict = classify(doc)
                treatments[src.site][verdict] += 1
                by_event[event][verdict] += 1
        elif src.collection == "devicestatus":
            for doc in corpus.iter_documents(src.path):
                override = doc.get("override")
                if not isinstance(override, dict) or not override.get("active"):
                    continue
                device_status[src.site][classify(override)] += 1

    totals = Counter()
    for counts in treatments.values():
        totals.update(counts)
    ds_totals = Counter()
    for counts in device_status.values():
        ds_totals.update(counts)

    return {
        "generated_by": "tools/nsschema/effects.py",
        "treatments": {
            "total": sum(totals.values()),
            "by_verdict": dict(totals),
            "by_site": {s: dict(c) for s, c in sorted(treatments.items())},
            "by_event_type": {e: dict(c) for e, c in sorted(by_event.items())},
        },
        "devicestatus_active_overrides": {
            "total": sum(ds_totals.values()),
            "by_verdict": dict(ds_totals),
            "by_site": {s: dict(c) for s, c in sorted(device_status.items())},
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="reports/schema-census/effects.json", type=Path)
    args = ap.parse_args(argv)

    root = corpus.repo_root()
    result = run(corpus.discover(root))

    t = result["treatments"]
    print(f"temporary-effect treatments: {t['total']:,}")
    for verdict, n in sorted(t["by_verdict"].items(), key=lambda kv: -kv[1]):
        print(f"    {verdict:20s} {n:6,}  {n / t['total']:6.1%}")
    print("\n  by eventType:")
    for event, counts in t["by_event_type"].items():
        total = sum(counts.values())
        shape = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"    {event:24s} {total:6,}  {shape}")

    d = result["devicestatus_active_overrides"]
    print(f"\n  active overrides in devicestatus: {d['total']:,}")
    for verdict, n in sorted(d["by_verdict"].items(), key=lambda kv: -kv[1]):
        print(f"    {verdict:20s} {n:7,}  {n / d['total']:6.1%}")

    dest = root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=1) + "\n")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
