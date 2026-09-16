"""manifest.py — load and schema-check queue/work-queue.yaml.

Shared by ``emit.py`` (generates queue/QUEUE.md), ``status.py`` (runs the
gates) and ``validate.py`` (the schema check). Written in Python rather than
Node for two reasons, both factual rather than stylistic:

  1. **House style.** The five schema emitters under ``tools/nsschema/emit/``
     are Python driven from the Makefile through ``$(PY)``, and this is the
     same shape of tool: read a declarative source, emit a derived view.
  2. **There is no YAML parser for Node on this machine.** ``js-yaml`` is not
     in ``tools/qc/node_modules`` nor anywhere else in the tree, and rule 0
     forbids reaching the network to install one. PyYAML 6.0.3 is present in
     both the system interpreter and ``.venv``.

The *gate scripts* under ``tools/queue/gates/`` are Node, matching the
``tools/qc/*-arm.js`` convention, because several of them have to ``require()``
a shipping module by path to measure it.

THE ONE INVARIANT THIS FILE EXISTS TO ENFORCE

A gate is either a runnable command or an explicit ``no-gate:`` marker with a
reason. There is no third option. An item whose ``gates`` list is missing,
empty, or contains an entry that is neither is a HARD validation error, because
a gate that is silently absent renders exactly like a gate that passed. That is
this programme's characteristic failure mode — an assertion wearing the costume
of a measurement — and the queue exists to make it impossible, not unlikely.
"""

from __future__ import annotations

import os
import sys
from collections import Counter

try:
    import yaml
except ImportError:  # pragma: no cover - environment problem, not a data problem
    sys.stderr.write("queue: PyYAML is required (python3 -m pip install pyyaml)\n")
    raise

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST_PATH = os.path.join(REPO_ROOT, "queue", "work-queue.yaml")
GENERATED_VIEW = os.path.join(REPO_ROOT, "queue", "QUEUE.md")

# Every field the maintainer asked to be representable. `ships_to_operators_today`
# is required only for register-open items, where the §1 / §1b distinction is
# the whole point of the register.
REQUIRED_FIELDS = (
    "id", "title", "parcel", "repo", "branch", "base", "state",
    "blast_radius", "review", "operator_visible", "semver", "gates",
    "blocks_on", "evidence", "notes",
)

VALID_SEMVER = {"patch", "minor", "major", "n/a"}
VALID_GATE_KINDS = {"static", "unit", "integration", "network"}


class ValidationError(Exception):
    """Raised with a list of human-readable problems."""

    def __init__(self, problems):
        self.problems = problems
        super().__init__("%d validation problem(s)" % len(problems))


def load(path=None):
    """Parse the manifest. Raises ValidationError on a malformed document."""
    path = path or MANIFEST_PATH
    with open(path, "r", encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    if not isinstance(doc, dict):
        raise ValidationError(["%s: top level is not a mapping" % path])
    for key in ("meta", "parcels", "items"):
        if key not in doc:
            raise ValidationError(["%s: missing top-level key %r" % (path, key)])
    if not isinstance(doc["items"], list) or not doc["items"]:
        raise ValidationError(["%s: `items` must be a non-empty list" % path])
    return doc


def classify_gate(gate):
    """Return ('run', gate) | ('no-gate', reason) | ('invalid', why)."""
    if not isinstance(gate, dict):
        return ("invalid", "gate is %s, not a mapping" % type(gate).__name__)
    has_run = "run" in gate
    has_marker = "no-gate" in gate
    if has_run and has_marker:
        return ("invalid", "gate carries both `run` and `no-gate`; pick one")
    if has_run:
        command = gate.get("run")
        if not isinstance(command, str) or not command.strip():
            return ("invalid", "`run` is empty; a blank command always succeeds")
        return ("run", gate)
    if has_marker:
        reason = gate.get("no-gate")
        if not isinstance(reason, str) or not reason.strip():
            return ("invalid", "`no-gate` carries no reason; the reason IS the gate")
        return ("no-gate", reason)
    return ("invalid", "gate has neither `run` nor `no-gate` (keys: %s)"
            % ", ".join(sorted(gate.keys())))


def validate(doc):
    """Return a list of problem strings. Empty list means the manifest is sound."""
    problems = []
    items = doc["items"]
    parcels = doc.get("parcels") or {}

    ids = [i.get("id") for i in items if isinstance(i, dict)]
    for dup, count in sorted(Counter(ids).items()):
        if dup is not None and count > 1:
            problems.append("duplicate id %r appears %d times" % (dup, count))
    known_ids = set(ids)

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append("items[%d] is not a mapping" % index)
            continue
        item_id = item.get("id") or "items[%d]" % index

        for field in REQUIRED_FIELDS:
            if field not in item:
                problems.append("%s: missing required field `%s`" % (item_id, field))

        semver = item.get("semver")
        if semver is not None and semver not in VALID_SEMVER:
            problems.append("%s: semver %r is not one of %s"
                            % (item_id, semver, "|".join(sorted(VALID_SEMVER))))

        if item.get("parcel") not in parcels:
            problems.append("%s: parcel %r is not declared in the `parcels` block"
                            % (item_id, item.get("parcel")))

        state = item.get("state")
        states = (doc.get("meta") or {}).get("states") or {}
        if states and state not in states:
            problems.append("%s: state %r is not declared in meta.states"
                            % (item_id, state))

        # operator_visible must be PRESENT. It may be empty (an operator sees
        # nothing), but it may not be forgotten, because "nobody thought about
        # it" and "we checked and the answer is nothing" are different facts.
        if "operator_visible" not in item:
            problems.append("%s: operator_visible is absent; use an empty string "
                            "to mean 'an operator sees nothing'" % item_id)

        blocks_on = item.get("blocks_on")
        if blocks_on is None:
            blocks_on = []
        if not isinstance(blocks_on, list):
            problems.append("%s: blocks_on must be a list" % item_id)
        else:
            for dependency in blocks_on:
                if dependency not in known_ids:
                    problems.append("%s: blocks_on references %r, which is not an "
                                    "id in this manifest" % (item_id, dependency))
                if dependency == item_id:
                    problems.append("%s: blocks_on references itself" % item_id)

        # THE GATE RULE.
        gates = item.get("gates")
        if gates is None or not isinstance(gates, list) or not gates:
            problems.append("%s: `gates` is missing or empty. Every item needs "
                            "either a runnable gate or an explicit `no-gate:` "
                            "marker saying why none exists." % item_id)
        else:
            for position, gate in enumerate(gates):
                kind, payload = classify_gate(gate)
                if kind == "invalid":
                    problems.append("%s: gates[%d] %s" % (item_id, position, payload))
                elif kind == "run":
                    gate_kind = payload.get("kind")
                    if gate_kind not in VALID_GATE_KINDS:
                        problems.append(
                            "%s: gates[%d] kind %r is not one of %s"
                            % (item_id, position, gate_kind,
                               "|".join(sorted(VALID_GATE_KINDS))))
                    if not (payload.get("describe") or "").strip():
                        problems.append("%s: gates[%d] has no `describe`; a gate "
                                        "nobody can read is a gate nobody will "
                                        "fix" % (item_id, position))
                    cwd = payload.get("cwd")
                    if cwd and not os.path.isdir(os.path.join(REPO_ROOT, cwd)):
                        problems.append("%s: gates[%d] cwd %r does not exist"
                                        % (item_id, position, cwd))

    _check_dependency_cycles(items, problems)
    return problems


def _check_dependency_cycles(items, problems):
    graph = {}
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            graph[item["id"]] = [d for d in (item.get("blocks_on") or [])]
    colour = {}

    def visit(node, trail):
        state = colour.get(node)
        if state == "done":
            return
        if state == "open":
            cycle = trail[trail.index(node):] + [node]
            problems.append("blocks_on cycle: %s" % " -> ".join(cycle))
            return
        colour[node] = "open"
        for nxt in graph.get(node, []):
            if nxt in graph:
                visit(nxt, trail + [node])
        colour[node] = "done"

    for node in graph:
        visit(node, [])


def gate_counts(item):
    """(runnable, no_gate) counts for an item."""
    runnable = no_gate = 0
    for gate in item.get("gates") or []:
        kind, _ = classify_gate(gate)
        if kind == "run":
            runnable += 1
        elif kind == "no-gate":
            no_gate += 1
    return runnable, no_gate
