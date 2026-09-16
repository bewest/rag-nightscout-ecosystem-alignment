"""emit.py — generate queue/QUEUE.md from queue/work-queue.yaml.

    python3 tools/queue/emit.py            # write queue/QUEUE.md
    python3 tools/queue/emit.py --check    # exit 1 if the file on disk is stale
    python3 tools/queue/emit.py --stdout   # print, write nothing

The sixth emitter beside jsonschema_emit, mongoose_emit, zod_emit,
pyarrow_emit, coercion_emit, fieldref_emit and postgres_emit, and it follows
the house rule those established: EMIT, THEN CHECK THE EMISSION. `--check` is
what makes `make queue` more than a suggestion -- CI or a pre-commit hook can
prove the generated view has not drifted from its source.

WHAT IT DELIBERATELY DOES NOT DO

It does not carry a `state` column that a human can edit. The state in the
YAML is a CLAIM; `queue-status` is the measurement. So every state printed
here is stamped "claimed" and the reader is pointed at the runner. Writing the
measured result into this file would make it stale the moment a branch moves,
and a stale measurement is worse than an honest claim.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import manifest  # noqa: E402

HEADER = """<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit.py   (make queue)
  Staleness check:  python3 tools/queue/emit.py --check

  Every edit to this file will be destroyed by the next `make queue`. Edit the
  YAML instead. The reason this file is generated at all is that a
  hand-maintained `state` column is an ASSERTION, and this programme has been
  bitten repeatedly by assertions that read like measurements.

  Even here, `state` is only a CLAIM about what the gates will say. The
  measurement is `make queue-status`, which runs them.
  ============================================================================
-->
"""


def _flow(text, width=78, indent=""):
    """Collapse a YAML folded block into wrapped prose."""
    if text is None:
        return ""
    body = " ".join(str(text).split())
    if not body:
        return ""
    return "\n".join(textwrap.wrap(body, width=width,
                                   initial_indent=indent,
                                   subsequent_indent=indent))


def render(doc):
    meta = doc.get("meta") or {}
    parcels = doc.get("parcels") or {}
    items = doc["items"]

    lines = [HEADER, "# Work queue", ""]
    lines.append("Generated from `queue/work-queue.yaml` by `tools/queue/emit.py`. "
                 "**Do not hand-edit.**")
    lines.append("")
    measured_against = meta.get("measured_against") or {}
    lines.append("- Manifest schema version: `%s`" % meta.get("schema_version"))
    lines.append("- Measured at: %s" % meta.get("measured_at"))
    for name, value in measured_against.items():
        lines.append("- Measured against %s: `%s`" % (name, value))
    lines.append("")
    lines.append("One queue spans every programme on purpose, so that a tenancy task "
                 "colliding with a release train is visible in one place. The `parcel` "
                 "field does the separating.")
    lines.append("")

    # --- totals -------------------------------------------------------------
    runnable = sum(manifest.gate_counts(i)[0] for i in items)
    absent = sum(manifest.gate_counts(i)[1] for i in items)
    lines.append("## Totals")
    lines.append("")
    lines.append("| | count |")
    lines.append("|---|---|")
    lines.append("| items | %d |" % len(items))
    lines.append("| runnable gates | %d |" % runnable)
    lines.append("| explicit `no-gate:` markers | %d |" % absent)
    lines.append("")
    lines.append("A `no-gate:` marker is not a gap in the bookkeeping; it is the "
                 "bookkeeping. It records that nobody has yet built a way to measure "
                 "the property, and it carries the reason. %d of the %d gate slots in "
                 "this queue are in that state, which is the honest shape of the "
                 "programme today." % (absent, runnable + absent))
    lines.append("")

    # --- state summary ------------------------------------------------------
    by_state = {}
    for item in items:
        by_state.setdefault(item.get("state"), []).append(item["id"])
    lines.append("### Claimed state (NOT a measurement -- run `make queue-status`)")
    lines.append("")
    lines.append("| state | n | ids |")
    lines.append("|---|---|---|")
    states_doc = meta.get("states") or {}
    for state in list(states_doc.keys()) + [s for s in by_state if s not in states_doc]:
        if state not in by_state:
            continue
        ids = by_state[state]
        lines.append("| `%s` | %d | %s |" % (state, len(ids), ", ".join(ids)))
    lines.append("")

    # --- operator exposure --------------------------------------------------
    ships = [i for i in items if i.get("ships_to_operators_today") is True]
    if ships:
        lines.append("### Reaches an operator on today's release")
        lines.append("")
        lines.append("The register's `§1` vs `§1b` distinction, carried as "
                     "`ships_to_operators_today`. Preserving it is the only thing "
                     "that makes the register mean anything.")
        lines.append("")
        for item in ships:
            lines.append("- **%s** %s" % (item["id"], item["title"]))
        lines.append("")

    # --- per parcel ---------------------------------------------------------
    for parcel_id, parcel in parcels.items():
        members = [i for i in items if i.get("parcel") == parcel_id]
        if not members:
            continue
        lines.append("---")
        lines.append("")
        lines.append("## %s" % parcel.get("title", parcel_id))
        lines.append("")
        lines.append("`parcel: %s` &mdash; %d items" % (parcel_id, len(members)))
        lines.append("")
        summary = _flow(parcel.get("summary"))
        if summary:
            lines.append(summary)
            lines.append("")

        lines.append("| id | title | state | branch | semver | gates |")
        lines.append("|---|---|---|---|---|---|")
        for item in members:
            run_count, no_gate_count = manifest.gate_counts(item)
            gate_cell = "%d run" % run_count
            if no_gate_count:
                gate_cell += " + %d no-gate" % no_gate_count
            lines.append("| `%s` | %s | `%s` | `%s` | %s | %s |" % (
                item["id"],
                str(item.get("title", "")).replace("|", "\\|"),
                item.get("state"),
                item.get("branch") or "-",
                item.get("semver"),
                gate_cell,
            ))
        lines.append("")

        for item in members:
            lines.extend(_render_item(item))

    lines.append("---")
    lines.append("")
    lines.append("*End of generated view. Source: `queue/work-queue.yaml`.*")
    lines.append("")
    return "\n".join(lines)


def _render_item(item):
    lines = ["### `%s` &mdash; %s" % (item["id"], item.get("title", "")), ""]

    facts = [
        ("state (claimed)", "`%s`" % item.get("state")),
        ("repo", "`%s`" % item.get("repo")),
        ("branch", "`%s`" % (item.get("branch") or "-")),
        ("base", "`%s`" % (item.get("base") or "-")),
        ("worktree", "`%s`" % (item.get("worktree") or "-")),
        ("semver", "`%s`" % item.get("semver")),
        ("review", str(item.get("review") or "-")),
    ]
    if "ships_to_operators_today" in item:
        facts.append(("ships to operators today",
                      "**yes**" if item["ships_to_operators_today"] else "no (pre-release)"))
    if item.get("register"):
        facts.append(("register", ", ".join("`%s`" % r for r in item["register"])))
    if item.get("blocks_on"):
        facts.append(("blocks on", ", ".join("`%s`" % b for b in item["blocks_on"])))

    lines.append("| | |")
    lines.append("|---|---|")
    for label, value in facts:
        lines.append("| %s | %s |" % (label, " ".join(str(value).split())))
    lines.append("")

    blast = _flow(item.get("blast_radius"))
    if blast:
        lines.append("**Blast radius.** " + " ".join(blast.split()))
        lines.append("")

    operator = " ".join(str(item.get("operator_visible") or "").split())
    lines.append("**What an operator sees.** " +
                 (operator if operator else "_Nothing. No operator-visible change._"))
    lines.append("")

    reason = _flow(item.get("semver_reason"))
    if reason:
        lines.append("**Why `%s`.** %s" % (item.get("semver"), " ".join(reason.split())))
        lines.append("")

    lines.append("**Gates.**")
    lines.append("")
    for gate in item.get("gates") or []:
        kind, payload = manifest.classify_gate(gate)
        if kind == "run":
            cwd = payload.get("cwd")
            where = " _(cwd: `%s`)_" % cwd if cwd else ""
            lines.append("- `[%s]`%s `%s`" % (payload.get("kind"), where,
                                              " ".join(payload["run"].split())))
            describe = " ".join(str(payload.get("describe") or "").split())
            if describe:
                lines.append("  - %s" % describe)
        elif kind == "no-gate":
            lines.append("- **NO GATE** &mdash; %s" % " ".join(payload.split()))
        else:
            lines.append("- **INVALID GATE** &mdash; %s" % payload)
    lines.append("")

    if item.get("evidence"):
        lines.append("**Evidence.**")
        lines.append("")
        for path in item["evidence"]:
            lines.append("- `%s`" % path)
        lines.append("")

    notes = _flow(item.get("notes"))
    if notes:
        lines.append("**Notes.** " + " ".join(notes.split()))
        lines.append("")

    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="emit queue/QUEUE.md")
    parser.add_argument("--manifest", default=manifest.MANIFEST_PATH)
    parser.add_argument("--out", default=manifest.GENERATED_VIEW)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the file on disk differs from the emission")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args(argv)

    doc = manifest.load(args.manifest)
    problems = manifest.validate(doc)
    if problems:
        print("queue-emit: refusing to emit from an invalid manifest:")
        for problem in problems:
            print("  FAIL  %s" % problem)
        return 1

    text = render(doc)

    if args.stdout:
        sys.stdout.write(text)
        return 0

    if args.check:
        if not os.path.exists(args.out):
            print("STALE  %s does not exist; run `make queue`" % args.out)
            return 1
        with open(args.out, "r", encoding="utf-8") as handle:
            current = handle.read()
        if current != text:
            print("STALE  %s differs from the manifest; run `make queue`" % args.out)
            return 1
        print("OK     %s is current" % os.path.relpath(args.out, manifest.REPO_ROOT))
        return 0

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(text)
    print("emitted %s  (%d items, %d bytes)"
          % (os.path.relpath(args.out, manifest.REPO_ROOT), len(doc["items"]), len(text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
