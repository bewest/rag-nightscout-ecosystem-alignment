"""vacuity.py — run every gate's NEGATIVE CONTROL and report which gates cannot fail.

    python3 tools/queue/vacuity.py                  # static controls
    python3 tools/queue/vacuity.py --id P0-E
    python3 tools/queue/vacuity.py --slow           # ALSO the ablation controls
    python3 tools/queue/vacuity.py --integration --network
    python3 tools/queue/vacuity.py --self-test      # prove THIS instrument works
    python3 tools/queue/vacuity.py --list-uncontrolled

WHY THIS FILE EXISTS

`status.py` answers "did the gates pass?". It cannot answer "would they have
failed if the property were false?", and a completeness critic proved on
2026-09-15 that for at least two items the answer was no:

  * P0-C's absence gate grepped for `console.log('Loading', opts)` while the
    code reads `console.log('Loading',opts)` with no space. The pattern never
    matched, the gate reported PASS, and the property it asserted was FALSE.
  * P0-E's only content gate was `git log --format=%H bf/reads | grep -q .`.
    It passed against origin/dev, origin/master and bf/alarms alike.

Both were GREEN. Neither was measuring anything. A queue whose gates are
assertions wearing the costume of measurements is worse than no queue, because
it launders the assertion.

THE RULE, which is the run/no-gate rule applied one level up

Every runnable gate carries, in `queue/gate-controls.yaml`, either a CONTROL —
a command that applies the same instrument to a state where the property is
FALSE, and which must therefore exit NON-ZERO — or an explicit `control-exempt`
with a reason. A gate with neither is UNCONTROLLED, and UNCONTROLLED is
reported as a failure of this instrument, never as a pass.

The control is keyed by the gate's exact command text. That is deliberate: edit
a gate and its control stops matching, so the edit forces the control to be
re-authored rather than silently inherited.

THE OUTCOME TAXONOMY

  NON-VACUOUS    the control ran and the gate refused to pass. The gate works.
  VACUOUS        the control ran and the gate PASSED on a known-negative.
  STUCK-RED      a positive control ran and the gate refused to pass on a
                 known-POSITIVE. A gate that can never go green is as useless
                 as one that can never go red, and it is the failure mode you
                 get from fixing vacuity carelessly.
  CONTROL-ERROR  the control could not be set up (it printed CONTROL-INVALID).
                 NOT a pass and NOT a vacuous gate: nobody measured anything.
  EXEMPT         an explicit control-exempt marker with a recorded reason.
  UNCONTROLLED   no entry for this gate at all.
  SKIP           a control this invocation chose not to run.

Provenance note, rule 3: an entry in gate-controls.yaml is a CLAIM until this
runner executes it. Everything this file prints is REPRODUCED, never read.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("queue: PyYAML is required\n")
    raise

CONTROLS_PATH = os.path.join(manifest.REPO_ROOT, "queue", "gate-controls.yaml")

NON_VACUOUS = "NON-VACUOUS"
VACUOUS = "VACUOUS"
STUCK_RED = "STUCK-RED"
CONTROL_ERROR = "CONTROL-ERROR"
EXEMPT = "EXEMPT"
UNCONTROLLED = "UNCONTROLLED"
SKIP = "SKIP"

BAD = (VACUOUS, STUCK_RED, CONTROL_ERROR, UNCONTROLLED)
DEFAULT_KINDS = {"static", "unit"}
INVALID_MARKER = "CONTROL-INVALID"


def normalise(command):
    return " ".join((command or "").split())


def load_controls(path=CONTROLS_PATH):
    """Return {(command, cwd): entry}. A missing file is not an error here —
    it is reported as every gate being UNCONTROLLED, which is the truth."""
    if not os.path.exists(path):
        return {}, ["%s does not exist; every gate is UNCONTROLLED" % path]
    with open(path, "r", encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}
    problems = []
    table = {}
    for index, entry in enumerate(doc.get("controls") or []):
        if not isinstance(entry, dict):
            problems.append("controls[%d] is not a mapping" % index)
            continue
        gate = normalise(entry.get("gate"))
        cwd = entry.get("cwd") or "."
        if not gate:
            problems.append("controls[%d] has no `gate`" % index)
            continue
        has_control = bool(normalise(entry.get("control")))
        has_exempt = bool((entry.get("control-exempt") or "").strip())
        if has_control and has_exempt:
            problems.append("controls[%d] (%s) carries both `control` and "
                            "`control-exempt`; pick one" % (index, gate[:60]))
        if not has_control and not has_exempt:
            problems.append("controls[%d] (%s) has neither `control` nor "
                            "`control-exempt`" % (index, gate[:60]))
        if has_control and not (entry.get("proves") or "").strip():
            problems.append("controls[%d] (%s) has no `proves`; a control "
                            "nobody can read is a control nobody will keep "
                            "honest" % (index, gate[:60]))
        if (gate, cwd) in table:
            problems.append("controls[%d] duplicates an earlier entry for %s"
                            % (index, gate[:60]))
        table[(gate, cwd)] = entry
    return table, problems


def run(command, cwd, timeout):
    full = os.path.join(manifest.REPO_ROOT, cwd or ".")
    if not os.path.isdir(full):
        return (127, "%s: cwd %s does not exist" % (INVALID_MARKER, cwd))
    try:
        done = subprocess.run(["bash", "-c", command], cwd=full,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return (124, "%s: timed out after %ds" % (INVALID_MARKER, timeout))
    except Exception as error:  # noqa: BLE001
        return (126, "%s: %s" % (INVALID_MARKER, error))
    return (done.returncode, (done.stdout or "") + (done.stderr or ""))


def evaluate(entry, enabled_kinds, timeout):
    """Return (outcome, detail, output)."""
    if not entry:
        return (UNCONTROLLED, "no control declared for this gate", "")
    exempt = (entry.get("control-exempt") or "").strip()
    if exempt:
        return (EXEMPT, " ".join(exempt.split()), "")

    kind = entry.get("control-kind") or "static"
    if kind not in enabled_kinds:
        return (SKIP, "control kind `%s` not enabled (use --%s)" % (kind, kind), "")

    where = entry.get("control-cwd") or entry.get("cwd") or "."
    code, output = run(normalise(entry["control"]), where, timeout)
    if INVALID_MARKER in output:
        return (CONTROL_ERROR, "the control could not be set up", output)
    if code == 0:
        return (VACUOUS, "the gate PASSED against its known-negative control", output)

    positive = normalise(entry.get("positive-control"))
    if positive:
        pkind = entry.get("positive-kind") or kind
        if pkind in enabled_kinds:
            pcode, poutput = run(positive, where, timeout)
            if INVALID_MARKER in poutput:
                return (CONTROL_ERROR, "the positive control could not be set up", poutput)
            if pcode != 0:
                return (STUCK_RED,
                        "the gate refused to pass against a known-POSITIVE control "
                        "(exit %d)" % pcode, poutput)
            return (NON_VACUOUS, "fails on the negative (exit %d), passes on the "
                                 "positive" % code, output)
    return (NON_VACUOUS, "the gate correctly refused to pass (exit %d)" % code, output)


SELF_TEST_GATES = [
    # (label, gate command, control command, what SHOULD be reported)
    ("a deliberately vacuous gate — the P0-E shape, an assertion that the "
     "branch has commits",
     "git -C externals/cgm-remote-monitor-official log --format=%H bf/reads | grep -q .",
     "git -C externals/cgm-remote-monitor-official log --format=%H origin/dev | grep -q .",
     VACUOUS),
    ("a deliberately vacuous gate — the P0-C shape, a grep whose pattern can "
     "never match",
     "grep -q \"console.log('Loading', opts)\" "
     "externals/work/crm-bf-auth/lib/authorization/storage.js && exit 1 || exit 0",
     "grep -q \"console.log('Loading', opts)\" "
     "externals/work/crm-bf-auth/lib/authorization/storage.js && exit 1 || exit 0",
     VACUOUS),
    ("a real gate, for contrast — the replacement P0-E read contract",
     "node tools/queue/gates/bf-reads-read-contract.js",
     "node tools/queue/gates/bf-reads-read-contract.js --rev origin/dev",
     NON_VACUOUS),
    ("a control that cannot be set up",
     "true",
     "tools/queue/gates/ablate.sh /nope bf/nope origin/dev /nope nope",
     CONTROL_ERROR),
]


def self_test(timeout):
    print("vacuity --self-test: running this instrument against gates whose")
    print("answer is known in advance. If any line says UNEXPECTED, the")
    print("instrument is broken and nothing else it prints means anything.")
    print("")
    failures = 0
    for label, gate, control, expected in SELF_TEST_GATES:
        entry = {"gate": gate, "control": control, "proves": "self-test",
                 "control-kind": "static"}
        outcome, detail, _ = evaluate(entry, {"static"}, timeout)
        ok = outcome == expected
        failures += 0 if ok else 1
        print("  %-13s %s" % (outcome, label))
        print("  %-13s expected %s -> %s" % ("", expected, "ok" if ok else "UNEXPECTED"))
        print("  %-13s %s" % ("", detail))
        print("")
    print("self-test: %d of %d as expected" % (len(SELF_TEST_GATES) - failures,
                                               len(SELF_TEST_GATES)))
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="run each gate's negative control and report vacuous gates")
    parser.add_argument("--manifest", default=manifest.MANIFEST_PATH)
    parser.add_argument("--controls", default=CONTROLS_PATH)
    parser.add_argument("--id", action="append", default=[], dest="ids")
    parser.add_argument("--parcel", action="append", default=[], dest="parcels")
    parser.add_argument("--slow", action="store_true",
                        help="ALSO run ablation controls: they build a throwaway "
                             "worktree and run a test suite, minutes each")
    parser.add_argument("--integration", action="store_true")
    parser.add_argument("--network", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--list-uncontrolled", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test(args.timeout)

    doc = manifest.load(args.manifest)
    controls, problems = load_controls(args.controls)
    if problems:
        print("queue-vacuity: queue/gate-controls.yaml has problems:")
        for problem in problems:
            print("  FAIL  %s" % problem)
        print("")

    enabled = set(DEFAULT_KINDS)
    if args.slow:
        enabled.add("slow")
    if args.integration:
        enabled.add("integration")
    if args.network:
        enabled.add("network")

    # One row per DISTINCT gate command, with the items that declare it. Two
    # items sharing a command share a property, and running the control twice
    # would measure the same thing twice.
    gates = {}
    for item in doc["items"]:
        if args.ids and item.get("id") not in args.ids:
            continue
        if args.parcels and item.get("parcel") not in args.parcels:
            continue
        for gate in item.get("gates") or []:
            kind, payload = manifest.classify_gate(gate)
            if kind != "run":
                continue
            key = (normalise(payload["run"]), payload.get("cwd") or ".")
            gates.setdefault(key, []).append(item["id"])

    if args.list_uncontrolled:
        missing = [k for k in sorted(gates) if k not in controls]
        for command, cwd in missing:
            print("UNCONTROLLED  [%s]  %s" % (cwd, command))
        print("")
        print("%d of %d distinct gate(s) have no control entry"
              % (len(missing), len(gates)))
        return 1 if missing else 0

    print("queue-vacuity  %d distinct gate(s)  control kinds=%s"
          % (len(gates), ",".join(sorted(enabled))))
    print("              a control must exit NON-ZERO: it applies the gate to a")
    print("              state where the property it asserts is FALSE.")
    print("")

    tallies = {}
    for (command, cwd) in sorted(gates):
        outcome, detail, output = evaluate(controls.get((command, cwd)),
                                           enabled, args.timeout)
        tallies[outcome] = tallies.get(outcome, 0) + 1
        owners = ",".join(sorted(set(gates[(command, cwd)])))
        print("%-13s %-22s %s" % (outcome, owners[:22],
                                  (command if cwd == "." else "[%s] %s" % (cwd, command))[:110]))
        if outcome in BAD or args.verbose:
            print("%14s%s" % ("", detail))
            entry = controls.get((command, cwd)) or {}
            if entry.get("proves") and args.verbose:
                print("%14sproves: %s" % ("", " ".join(entry["proves"].split())[:150]))
            if output.strip() and (outcome in BAD or args.verbose):
                for line in output.strip().splitlines()[-6:]:
                    print("%14s| %s" % ("", line))

    print("")
    print("summary: " + "  ".join("%s=%d" % (k, v) for k, v in sorted(tallies.items())))
    print("")
    print("VACUOUS and UNCONTROLLED are FAILURES of this instrument's subject.")
    print("EXEMPT carries a recorded reason. SKIP measured nothing and is never")
    print("read as green.")
    return 1 if any(tallies.get(k) for k in BAD) else 0


if __name__ == "__main__":
    raise SystemExit(main())
