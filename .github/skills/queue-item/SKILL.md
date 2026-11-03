---
name: queue-item
description: Add or update an item in the single work queue (queue/work-queue.yaml), define a gate that can fail and its negative control, and run the checks that prove the manifest, the generated views and the register coverage are current. Use for any change to an item's state, gates, blockers or register ids, and whenever a new backfix id or branch needs tracking.
---

# Queue item: add, update, measure

The queue is one manifest for every programme. `state` is a **claim** about what the gates will
say; `make queue-status` is the measurement. `queue/README.md` is the full field reference; this
skill is the procedure.

## 1. Before editing

```bash
git status --short queue/work-queue.yaml     # ' M' before your edit = a peer's uncommitted work; ask them to commit first
grep -n "^  - id: <ID>" queue/work-queue.yaml   # does the item already exist?
grep -n "register: \[.*BF-<n>" queue/work-queue.yaml  # is the register id already covered by another item?
```

An id may be covered by **cross-reference** (add it to an existing item's `register:` list) when
that item already tracks it in substance. Do not create a duplicate item, and do not touch anything
else on an item another session owns.

## 2. Write the item

Append to `items:`. Every field below is required unless marked optional.

```yaml
  - id: BFQ-227                           # unique; validate enforces it
    title: "bf/example - one line"        # QUOTE it when it contains '#'
    parcel: register-open                 # must exist in the parcels: block
    repo: cgm-remote-monitor
    branch: bf/example
    base: official/dev@61eb3733           # WHICH commit, never just "dev"
    worktree: externals/work/crm-bf-example
    state: gate-not-met                   # a claim; see states: in meta
    blast_radius: 2 commits, lib/server/example.js, +40/-12.
    review: maintainer, plus one reviewer who has not merged their own work here
    operator_visible: >
      Plain language for people managing diabetes. Empty string if an operator sees nothing.
    semver: patch                         # patch | minor | major | n/a
    semver_reason: >
      Why. Name the surface that moves.
    ships_to_operators_today: true        # register items only: register §1 = true, §1b = false
    register: [BF-227]
    gates:
      - run: node tools/queue/gates/example-gate.js
        kind: static                      # static | unit | integration | network
        describe: what this proves, in one line
      - no-gate: >
          Why no instrument exists and what building one would take.
    blocks_on: []                         # ids in this file; cycles are rejected
    evidence:
      - docs/60-research/remedial/example-2026-11-03.md
    notes: >
      Anything a reader needs that is not a field.
```

YAML traps the validator cannot see: a space then `#` in an unquoted value starts a comment and
silently truncates the value; `no` becomes `False`; `1.20` becomes `1.2`; a repeated key keeps the
last. Quote prose or use `>` block scalars. `make queue-fidelity` measures truncation.

## 3. Write the gate so that it can fail

A gate is a command that exits non-zero when the property does not hold. There is no third shape
besides `run:` and `no-gate:`.

1. Scripts go in `tools/queue/gates/`, Node, read-only: `git show`/`git archive` into scratch, never
   `git checkout` into a worktree. `_gate.js` gives `show(ref, file)`, `git(args)`, `report(name,
   findings)`; `report` exits non-zero on any bad finding **and** on zero findings.
2. **Break it before you trust it.** Revert or damage the property, run the gate, confirm red with
   the expected symptom, restore. A green ablation means either the gate is vacuous or the break
   broke nothing; say which.
3. Declare the control in `queue/gate-controls.yaml`, keyed by the gate's exact command text:
   `control:` (same instrument on a known-false state, must exit non-zero) or `control-exempt:` with
   a reason. Optional `positive-control:` must exit zero. Editing the command text orphans the
   control on purpose; re-author it.

## 4. Run the checks

```bash
make queue-validate                 # schema, ids, blocks_on, gate rule, fidelity
make queue                          # regenerate QUEUE.md (never hand-edit it)
make queue-status ID="BFQ-227"      # run this item's gates; read the verdict words
make queue-vacuity                  # the control must report NON-VACUOUS for your gate
make queue-check                    # register coverage, every generated view current, links
```

Verdicts: `PASS`, `FAIL` (measured negative), `NO-INSTRUMENT` (script missing), `UNMEASURED`
(nothing ran). Only `PASS` is green. Integration and network gates run only with `INTEGRATION=1`
or `--network` and the runner says when it skipped them.

Run the checks **after** `git add`: the link and staleness gates read `git ls-files` and cannot see
an untracked file.

## 5. Commit

Generated views (`queue/QUEUE.md`, the overview blocks, `reports/reviewer-packets/`) are shared.
Regenerate them, check `git diff --cached --name-only` for a peer's paths, and commit by path:

```bash
git commit -- queue/work-queue.yaml queue/QUEUE.md queue/gate-controls.yaml \
  tools/queue/gates/example-gate.js docs/00-overview reports/reviewer-packets
```

Say in the message if the regenerated views carry another session's items. No trailers.
