"""validate.py — schema-check queue/work-queue.yaml.

    python3 tools/queue/validate.py            # check, exit 1 on any problem
    python3 tools/queue/validate.py --quiet    # exit code only

Checks, in the order the maintainer asked for them:

  * every id is unique;
  * every `blocks_on` entry resolves to an id in this manifest, and the
    dependency graph has no cycle;
  * every gate is EITHER a runnable command OR an explicit `no-gate:` marker
    carrying a reason -- an item with no gates at all is a hard error;
  * plus the field, enum, parcel and state checks in manifest.py.

It also reports ADVISORIES: a gate whose command invokes a script under
tools/queue/gates/ that does not exist. That is not a schema error -- the
manifest is well-formed -- but it is worth surfacing here as well as in
`queue-status`, because such a gate exits non-zero for a reason that has
nothing to do with the property being measured.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest  # noqa: E402

GATE_SCRIPT = re.compile(r"tools/queue/gates/[\w.-]+")


def advisories(doc):
    out = []
    for item in doc["items"]:
        if not isinstance(item, dict):
            continue
        for position, gate in enumerate(item.get("gates") or []):
            kind, payload = manifest.classify_gate(gate)
            if kind != "run":
                continue
            for reference in GATE_SCRIPT.findall(payload.get("run", "")):
                if not os.path.exists(os.path.join(manifest.REPO_ROOT, reference)):
                    out.append("%s: gates[%d] invokes %s, which does not exist"
                               % (item.get("id"), position, reference))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="schema-check the work queue")
    parser.add_argument("--manifest", default=manifest.MANIFEST_PATH)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        doc = manifest.load(args.manifest)
    except manifest.ValidationError as error:
        for problem in error.problems:
            print("FAIL  %s" % problem)
        return 1
    except Exception as error:  # noqa: BLE001 - a parse error is a validation result
        print("FAIL  %s: %s" % (args.manifest, error))
        return 1

    problems = manifest.validate(doc)
    notes = advisories(doc)

    if not args.quiet:
        items = doc["items"]
        runnable = sum(manifest.gate_counts(i)[0] for i in items)
        absent = sum(manifest.gate_counts(i)[1] for i in items)
        print("queue-validate  %s" % os.path.relpath(args.manifest, manifest.REPO_ROOT))
        print("  %d items, %d parcels, %d runnable gates, %d explicit no-gate markers"
              % (len(items), len(doc.get("parcels") or {}), runnable, absent))
        for note in notes:
            print("ADVISORY  %s" % note)
        for problem in problems:
            print("FAIL  %s" % problem)
        if not problems:
            print("OK    schema, ids, blocks_on and the gate rule all hold")

    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
