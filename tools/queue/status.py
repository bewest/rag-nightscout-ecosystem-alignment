"""status.py — run each item's gates and report what they actually said.

    python3 tools/queue/status.py                      # every item, static+unit gates
    python3 tools/queue/status.py --id P0-A --id P0-B
    python3 tools/queue/status.py --parcel phase0
    python3 tools/queue/status.py --state ready-to-push
    python3 tools/queue/status.py --integration        # ALSO run database gates
    python3 tools/queue/status.py --network            # ALSO run read-only remote gates
    python3 tools/queue/status.py --verbose            # per-gate lines and output on failure

WHY SUBSET SELECTION IS MANDATORY, NOT A CONVENIENCE

Running every gate in the programme at once is not something anyone will do
twice, so a runner that only does that will be run once and then abandoned,
and an abandoned runner is how a queue silently becomes a Markdown table again.

WHY INTEGRATION GATES ARE OFF BY DEFAULT

They need MongoDB. Other sessions share this checkout and are live right now,
and although GT1 measured that each worktree names its own mongod port, the
suites are still minutes long and destructive of each other's databases where a
port IS shared. Default-off, and the runner SAYS it skipped them rather than
counting them as passes.

THE OUTCOME TAXONOMY, WHICH IS THE POINT OF THE WHOLE FILE

  PASS      the command ran and exited 0
  FAIL      the command ran and exited non-zero -- a measured negative
  MISSING   the command names a gate script that does not exist. NOT a FAIL:
            a FAIL means the property is false, MISSING means nobody has built
            the instrument. Collapsing the two would let an unbuilt gate look
            like a measured defect, and later let someone "fix" the defect by
            writing a script that exits 0.
  SKIP      a real gate that this invocation chose not to run (integration or
            network without the flag)
  NO-GATE   an explicit marker in the manifest: no instrument exists, reason
            recorded

And the rule that all of it exists to serve: an item with ZERO gates that
actually ran is reported UNMEASURED, never `0/0 PASS`. A 0/0 that renders green
is precisely how an assertion gets laundered into the appearance of a
measurement, which is the failure mode this programme keeps rediscovering.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest  # noqa: E402

GATE_SCRIPT = re.compile(r"tools/queue/gates/[\w.-]+")
DEFAULT_KINDS = {"static", "unit"}
DEFAULT_TIMEOUT = 600

PASS, FAIL, MISSING, SKIP, NO_GATE = "PASS", "FAIL", "MISSING", "SKIP", "NO-GATE"


def gate_script_missing(command):
    """Return the first referenced gate script that does not exist, or None."""
    for reference in GATE_SCRIPT.findall(command):
        if not os.path.exists(os.path.join(manifest.REPO_ROOT, reference)):
            return reference
    return None


def run_gate(gate, enabled_kinds, timeout=DEFAULT_TIMEOUT):
    """Execute one runnable gate. Returns (outcome, detail, output)."""
    kind = gate.get("kind")
    command = gate["run"]

    if kind not in enabled_kinds:
        return (SKIP, "kind `%s` not enabled (use --%s)" % (kind, kind), "")

    absent = gate_script_missing(command)
    if absent:
        return (MISSING, "gate script %s does not exist" % absent, "")

    cwd = os.path.join(manifest.REPO_ROOT, gate.get("cwd") or ".")
    if not os.path.isdir(cwd):
        return (MISSING, "cwd %s does not exist" % gate.get("cwd"), "")

    try:
        completed = subprocess.run(
            ["bash", "-c", command],
            cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (FAIL, "timed out after %ds" % timeout, "")
    except Exception as error:  # noqa: BLE001
        return (FAIL, "could not execute: %s" % error, "")

    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode == 0:
        return (PASS, "exit 0", output)
    return (FAIL, "exit %d" % completed.returncode, output)


def evaluate(item, enabled_kinds, timeout=DEFAULT_TIMEOUT):
    results = []
    for gate in item.get("gates") or []:
        kind, payload = manifest.classify_gate(gate)
        if kind == "no-gate":
            results.append({"outcome": NO_GATE, "detail": " ".join(payload.split()),
                            "command": None, "kind": None, "cwd": None, "output": ""})
        elif kind == "run":
            outcome, detail, output = run_gate(payload, enabled_kinds, timeout)
            results.append({"outcome": outcome, "detail": detail,
                            "command": " ".join(payload["run"].split()),
                            "kind": payload.get("kind"), "cwd": payload.get("cwd"),
                            "output": output})
        else:
            results.append({"outcome": FAIL, "detail": "invalid gate: %s" % payload,
                            "command": None, "kind": None, "cwd": None, "output": ""})
    return results


def summarise(results):
    """Return (verdict, ran_pass, ran_total, tallies)."""
    tallies = {PASS: 0, FAIL: 0, MISSING: 0, SKIP: 0, NO_GATE: 0}
    for result in results:
        tallies[result["outcome"]] = tallies.get(result["outcome"], 0) + 1
    ran_total = tallies[PASS] + tallies[FAIL]
    ran_pass = tallies[PASS]

    if tallies[FAIL]:
        verdict = "FAIL"
    elif tallies[MISSING]:
        # An unbuilt instrument is not a pass, and it is not a defect either.
        verdict = "NO-INSTRUMENT"
    elif ran_total == 0:
        verdict = "UNMEASURED"
    else:
        verdict = "PASS"
    return verdict, ran_pass, ran_total, tallies


def select(items, ids, parcels, states):
    if not (ids or parcels or states):
        return list(items)
    chosen = []
    for item in items:
        if ids and item.get("id") in ids:
            chosen.append(item)
        elif parcels and item.get("parcel") in parcels:
            chosen.append(item)
        elif states and item.get("state") in states:
            chosen.append(item)
    return chosen


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="run the work queue's gates and report what they said")
    parser.add_argument("--manifest", default=manifest.MANIFEST_PATH)
    parser.add_argument("--id", action="append", default=[], dest="ids")
    parser.add_argument("--parcel", action="append", default=[], dest="parcels")
    parser.add_argument("--state", action="append", default=[], dest="states")
    parser.add_argument("--integration", action="store_true",
                        help="ALSO run gates that need MongoDB (shared with other "
                             "live sessions -- off by default on purpose)")
    parser.add_argument("--network", action="store_true",
                        help="ALSO run read-only remote gates. Rule 0 still holds: "
                             "a gate may read, never push.")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    doc = manifest.load(args.manifest)
    problems = manifest.validate(doc)
    if problems:
        print("queue-status: the manifest does not validate; fix it first "
              "(`make queue-validate`):")
        for problem in problems:
            print("  FAIL  %s" % problem)
        return 2

    enabled = set(DEFAULT_KINDS)
    if args.integration:
        enabled.add("integration")
    if args.network:
        enabled.add("network")

    chosen = select(doc["items"], set(args.ids), set(args.parcels), set(args.states))
    if not chosen:
        print("queue-status: no items matched the selection")
        return 2

    print("queue-status  %d item(s)  kinds=%s"
          % (len(chosen), ",".join(sorted(enabled))))
    if "integration" not in enabled:
        print("              integration gates are SKIPPED (pass --integration). "
              "They are not counted as passes.")
    print("")

    verdicts = {}
    any_fail = False
    for item in chosen:
        results = evaluate(item, enabled, args.timeout)
        verdict, ran_pass, ran_total, tallies = summarise(results)
        verdicts[item["id"]] = verdict
        if verdict == "FAIL":
            any_fail = True

        extras = []
        if tallies[MISSING]:
            extras.append("%d missing" % tallies[MISSING])
        if tallies[SKIP]:
            extras.append("%d skipped" % tallies[SKIP])
        if tallies[NO_GATE]:
            extras.append("%d no-gate" % tallies[NO_GATE])
        suffix = ("  (%s)" % ", ".join(extras)) if extras else ""

        print("%-16s %-22s %-18s %s/%s %s%s" % (
            item["id"],
            (item.get("branch") or item.get("repo") or "-")[:22],
            item.get("state"),
            ran_pass, ran_total, verdict, suffix))

        # A claimed state that the gates contradict is the single most useful
        # thing this runner can say, so it is never hidden behind --verbose.
        claimed = item.get("state")
        if claimed == "ready-to-push" and verdict != "PASS":
            print("%18sCLAIM DIVERGES: state says ready-to-push, gates say %s"
                  % ("", verdict))
        if claimed == "gate-not-met" and verdict == "PASS":
            # Distinguish "the gate started passing" from "the failing gate was
            # never runnable in the first place". If the item carries no-gate
            # markers, the claim may rest on a recorded measurement that this
            # runner cannot reproduce -- which is a different situation, and
            # saying so is the difference between a useful warning and noise.
            if tallies[NO_GATE]:
                print("%18sCLAIM UNBACKED: state says gate-not-met, but every "
                      "RUNNABLE gate passed and the" % "")
                print("%18sfailing property sits behind %d no-gate marker(s). The "
                      "claim rests on a" % ("", tallies[NO_GATE]))
                print("%18srecorded measurement this runner cannot reproduce."
                      % "")
            else:
                print("%18sCLAIM DIVERGES: state says gate-not-met, every gate "
                      "passed" % "")

        if args.verbose:
            for result in results:
                if result["outcome"] == NO_GATE:
                    print("%18s%-8s %s" % ("", NO_GATE, result["detail"][:150]))
                else:
                    print("%18s%-8s [%s] %s" % ("", result["outcome"],
                                                result["kind"], result["command"]))
                    # cwd is load-bearing: the same grep against two different
                    # trees is two different measurements, and hiding it here
                    # cost one misdiagnosis while this runner was being written.
                    if result.get("cwd"):
                        print("%26sin %s" % ("", result["cwd"]))
                    print("%26s%s" % ("", result["detail"]))
                    if result["outcome"] == FAIL and result["output"].strip():
                        for line in result["output"].strip().splitlines()[-12:]:
                            print("%26s| %s" % ("", line))
            print("")

    print("")
    print("summary: " + "  ".join(
        "%s=%d" % (verdict, list(verdicts.values()).count(verdict))
        for verdict in ("PASS", "FAIL", "NO-INSTRUMENT", "UNMEASURED")
        if list(verdicts.values()).count(verdict)))
    print("")
    print("PASS = every gate that ran exited 0. FAIL = a gate ran and said no.")
    print("NO-INSTRUMENT = a declared gate script does not exist yet; nothing was")
    print("measured for it, and that is NOT the same as a defect.")
    print("UNMEASURED = nothing ran at all. Never read as green.")

    return 1 if any_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
