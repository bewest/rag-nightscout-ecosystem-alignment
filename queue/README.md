# The work queue

*Contributor-facing. Technical throughout. The `operator_visible` field inside the
manifest is the part written for people managing diabetes, and it has different
rules — see [Writing `operator_visible`](#writing-operator_visible).*

One queue spans **every programme**: Phase 0 backfixes, the modernization release
train, the open backfix-register entries and the multitenancy work, so that a
tenancy task colliding with a release train is visible in one place. The `parcel`
field separates them.

| file | what it is |
|---|---|
| `queue/work-queue.yaml` | **the source of truth.** Hand-edited. |
| `queue/QUEUE.md` | **generated.** Never hand-edit; `make queue` overwrites it. |
| `tools/queue/emit.py` | generates `QUEUE.md` |
| `tools/queue/status.py` | runs the gates |
| `tools/queue/validate.py` | schema-checks the manifest |
| `tools/queue/fidelity.py` | proves every character written into the YAML reaches the data |
| `tools/queue/vacuity.py` | runs every gate's negative control from `queue/gate-controls.yaml` |
| `tools/queue/emit_views.py`, `emit_packets.py` | generate the overview blocks and the reviewer packets |
| `tools/queue/gates/*.js` | one measurement each |

```
make queue                  # regenerate QUEUE.md
make queue-validate         # schema-check the manifest (fidelity included)
make queue-fidelity         # only the fidelity check, or against another file
make queue-status           # run every static + unit gate (~7s)
make queue-coverage         # prove the manifest covers every open register entry
make queue-check            # CI: register coverage FIRST, then staleness of every generated view, then links
make queue-vacuity          # run every gate's negative control

make queue-status PARCEL=phase0
make queue-status ID="P0-A P0-B"        # note the quotes: Make keeps only the last ID=
make queue-status STATE=ready-to-push
make queue-status PARCEL=phase0 INTEGRATION=1 VERBOSE=1
```

## Why this is a manifest and not a Markdown table

A hand-maintained `state` column is an **assertion**. Somebody typed it, and it
stays true-looking forever regardless of what the code does.

So `state` in the YAML is *only a claim about what the gates will say*, and
`make queue-status` is the measurement. The runner prints `CLAIM DIVERGES` when
an item says `ready-to-push` and a gate disagrees. Run it before acting on any
claimed state.

`QUEUE.md` is generated for the same reason: so that nobody can quietly edit a
status into the human-readable view.

## QUEUE.md is generated

It carries a header saying so. If you edit it, the next `make queue` destroys
your edit. `make queue-check` fails when the checked-in `QUEUE.md` no longer
matches the manifest, so a stale view cannot survive CI. It also fails when the
manifest has fallen behind the register — see the next section, which is the
edge that actually costs something.

## The manifest owes the register a covering item

The backfix register is authoritative for **defect facts and ids**. This manifest is authoritative
for **item state**. The register grows independently of the manifest, and a register id that is in
no item is a defect nobody is tracking — possibly one that reaches every operator on the shipping
release. So:

- **every not-fixed register entry must be named in some item's `register:` list**, and
- **`ships_to_operators_today` must agree with the section it sits in** — §1 is `true`, §1b is
  `false`. §1c (`CAP-`) is exempt; it is neither.

`make queue-coverage` measures both, and `make queue-check` runs it **before** the staleness check,
because any manifest edit also makes `QUEUE.md` stale and Make stops at the first failing line — so
with the order reversed the harmless failure masks the one that matters.

An id may be covered by **cross-reference rather than a new item** when an existing item already
tracks it in substance — `RT-D3` runs the gate that *is* BF-54, `RT-5` runs the gate that *is*
BF-61. Add the id to that item's `register:` line rather than creating a duplicate, and do not
touch anything else on someone else's item.

A `fixed` or `merged` entry counts as covered, because the branch carrying the repair is itself an
item. That is **not** a claim that an operator is safe: `fixed` means repaired on a branch and not
merged, `merged` means in `origin/dev` and not released, and `DOC-EXPOSURE` owns saying so.

## How to add an item

Append to the `items:` list in `queue/work-queue.yaml`, then run
`make queue-validate && make queue`.

```yaml
  - id: P0-J                              # unique; validate enforces it
    title: bf/example - one line
    parcel: phase0                        # must exist in the `parcels:` block
    repo: cgm-remote-monitor
    branch: bf/example
    base: origin/dev@a8888f0d             # say WHICH commit, not just "dev"
    worktree: externals/work/crm-bf-example
    state: ready-to-push                  # a CLAIM. the gates are the measurement.
    blast_radius: 2 commits, lib/server/example.js, +40/-12.
    review: maintainer, plus one reviewer who has not merged their own work here
    operator_visible: >
      Plain language. See below. Empty string if an operator sees nothing.
    semver: minor                         # patch | minor | major | n/a
    semver_reason: >
      Why. Name the surface that moves.
    ships_to_operators_today: true        # register items only: §1 vs §1b
    register: [BF-40]
    gates:
      - run: some-command --that-exits-nonzero-when-wrong
        cwd: externals/work/crm-bf-example    # optional; default is the repo root
        kind: static                          # static | unit | integration | network
        describe: what this proves
      - no-gate: >
          Why no instrument exists, and what building one would take.
    blocks_on: [P0-TAG]                   # must resolve to ids in this file
    evidence:
      - docs/60-research/something.md
    notes: >
      Anything a reader needs that is not a field.
```

`make queue-validate` rejects: a duplicate `id`, a `blocks_on` that resolves to
nothing, a `blocks_on` cycle, an unknown `parcel`, an unknown `state`, a `semver`
outside the four values, a gate with neither `run` nor `no-gate`, a gate with
both, an empty `run`, a `no-gate` with no reason, a gate with no `describe`, and
an item whose `gates` list is missing or empty.

### Write prose so the parser cannot eat it

Those checks all take the parsed document as given and ask whether it is
well-formed. One class of defect is invisible to every one of them, because the
result is well-formed: a value that arrives **shorter than it was written**.

In a YAML *plain* (unquoted) scalar, a space followed by `#` starts a comment.
So this, which is the natural way to write a title:

```yaml
    title: T0.1 - PR #8733, the two quadratic treatment scans
```

parses as `T0.1 - PR`. The schema check cannot catch it, because a truncated
string is a perfectly valid string. `make queue-fidelity` measures it, and
`queue-validate` runs it. The rules:

* **Never leave an inline comment after an unquoted value.** Quote the value, or
  put the comment on its own line. After a quoted or block scalar a comment is
  harmless and allowed, because such a scalar ends at its delimiter rather than
  at whitespace-then-`#`. The rule is absolute on purpose: no heuristic for
  "that one looked deliberate" survives contact with the defect it was built for.
* **Quote anything YAML would retype.** `no` is the boolean `False`, not the word;
  `1.20` is `1.2`; `007` is `7`; `12:30` is `750`.
* **Never repeat a key in one mapping.** PyYAML keeps the last and discards the
  other in silence.

Full-line comments are unaffected and always were. The safe spellings for prose:

```yaml
    title: "T0.1 - PR #8733, the two quadratic treatment scans"
    review: >
      Any long prose, folded. A # in here is text.
```

## How to define a gate

**A gate is a command that exits 0 when the property holds and non-zero when it
does not.** Not a description of a check — the check itself.

There are exactly two legal shapes, and the validator enforces it:

```yaml
    gates:
      - run: git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/x >/dev/null
        kind: static
        describe: trial-merge into origin/dev is conflict-free

      - no-gate: >
          Nothing exercises the ENABLE warning through a booted plugin registry.
          Testing it meant hand-reconstructing the plugin-name list, and a
          reconstructed registry is not the registry.
```

**There is no third shape.** An item with no gates at all is a validation error,
because a missing gate renders as blank and blank looks exactly like a passing
gate. `no-gate:` is not an admission of failure — it is the bookkeeping, and a
large share of the queue's gate slots are in that state. `make queue-validate`
prints the current count of runnable gates and `no-gate:` markers.

### Gate kinds

| kind | runs by default? | for |
|---|---|---|
| `static` | yes | cheap, local, read-only |
| `unit` | yes | a local suite needing no database |
| `integration` | **no** — needs `--integration` | needs MongoDB |
| `network` | **no** — needs `--network` | contacts a remote, **read-only** |

Integration gates are off by default because worktrees share this checkout with
other live sessions and the suites are minutes long. The runner **says it
skipped them**; a skip is never counted as a pass.

Rule 0 still applies to a `network` gate: it may read (`git ls-remote`,
`npm ci --dry-run`), and it may never push.

### Writing a gate script

Scripts live in `tools/queue/gates/` and are Node, matching the
`tools/qc/*-arm.js` convention, because several need to `require()` a shipping
module to measure it. `_gate.js` gives you `show(ref, file)`, `git(args)` and
`report(name, findings)`.

They **read only**. `git show` and `git archive` into a scratch directory; never
`git checkout`, never write into a worktree (rule 5 — those worktrees belong to
other sessions).

`report()` exits non-zero if **any** finding is bad, and exits non-zero if there
are **no findings at all**, because a gate that examined nothing must not read as
a pass.

### Make your gate fail on purpose before you trust it

This is rule 2 and it is not optional. A check that has never failed is not yet
evidence. Break the thing under test, confirm the gate goes red, put it back.

Two ways a gate goes vacuous, and only breaking it tells you which:

- **the corpus never exercises the property** — `d3-drag-clamp-covered` exists
  because a 24-passing suite stayed 24-passing with the code deleted;
- **the code never distinguishes the branches** — a `grep` that matches the same
  word in prose and in a status column.

Examples of each from this queue: a `grep -q 'landed' <register>` gate passes on
the legend line and unrelated prose, so `DOC-EXPOSURE` parses the status column
instead; a harness that passes flat env-var names to shims reading
`env.extendedSettings.*` gets `{migrated:false}` from every shape and reports
misreads as outages, so `cut4-total-outage` passes the nested shape.

Where a gate can be fooled in one direction, add a **control** — a case that must
come out the other way. `minimed-deprecation-path` asserts the *Dexcom* path is
still detectable, so a red result means MiniMed is bare rather than that the gate
broke.

### Every gate declares its control, in `queue/gate-controls.yaml`

Two gates in this queue were once green on properties that were false, which
is why a control is a declared artefact rather than a habit:

- **P0-C** grepped for `console.log('Loading', opts)` while the code at
  `lib/authorization/storage.js:113` reads `console.log('Loading',opts)` — no
  space after the comma. The pattern never matched, the `|| exit 0` arm always
  fired, and the item reported **3/3 PASS on a property that is false**.
- **P0-E**'s only content gate was
  `git log --format=%H bf/reads | grep -q .` — an assertion that the branch has
  at least one commit. It passes for `origin/dev`, `origin/master` and
  `bf/alarms` too.

Every runnable gate has an entry in `queue/gate-controls.yaml` carrying either

- `control:` — the same instrument applied to a state where the property is
  **false**, which must therefore exit **non-zero**; or
- `control-exempt:` — a reason why no control can honestly be written.

There is no third option, exactly as there is no third option for `run:` versus
`no-gate:` one level up. An optional `positive-control:` must exit **zero**, and
catches the opposite failure: a gate that can never go green.

Entries are keyed by the gate's exact command text. **Edit a gate and its
control stops matching**, so the edit forces the control to be re-authored
rather than silently inherited.

```
make queue-vacuity                 # static controls
make queue-vacuity SLOW=1          # plus the branch ablations
python3 tools/queue/vacuity.py --list-uncontrolled
python3 tools/queue/vacuity.py --self-test
```

`--self-test` runs the instrument against four gates whose answer is known in
advance, two of them the historical vacuous gates above. If it does not report
`VACUOUS` for those two, nothing else it prints means anything.

Three helpers exist so that a control can be a one-line command:

| helper | what it does |
|---|---|
| `tools/queue/gates/ablate.sh` | throwaway worktree of a branch, shipping code reverted to the base, the branch's own tests re-run. Exits with mocha's status. |
| `tools/queue/gates/empty-root-control.sh` | runs a gate with `QUEUE_GATE_ROOT` pointed at an empty directory. The **weak** form: it proves a gate reads its inputs, not that it reads the right property of them. |
| a gate's own `--rev` mode | `bf-reads-read-contract.js --rev origin/dev` runs the identical assertions against a rev materialised from the object database. The **strong** form. |

`ablate.sh` prints its scope and refuses to run a test if the working tree came
out unchanged, because `git checkout <base> -- <path>` aborts the *whole*
checkout when the branch **added** that path — an ablation that reverts nothing
reports green having broken nothing. It deletes added files instead of restoring
them. The general point: a green ablation may mean the ablation was mis-scoped
rather than that the gate is vacuous, and you have to say which.

Controls are **authored, never derived**. A rule like "a gate is vacuous if it
passes on the base" would have been wrong twice here: `P0-PIN`'s lockfile gate
is *deliberately inverted* and passes against `origin/dev` on purpose, and
`RT-D3`'s suite runs inside the shipping checkout, which no control may modify.

## Writing `operator_visible`

This field is read by people managing their own or a family member's diabetes.
Different rules apply than to the rest of the manifest:

- plain language; define any jargon you cannot avoid;
- preserve every safety caveat — do not compress one away for readability;
- never simplify algorithm behaviour in a way that could mislead someone relying
  on it;
- **never** give individualised insulin dosing advice;
- where relevant, note that it is not medical advice and suggest talking to a
  care team;
- status words mean one thing: merged into `dev` is not released, and nothing
  is described as fixed for someone running Nightscout until it is in a
  released version;
- an **empty string** means "we checked, and an operator sees nothing". Leaving
  the field out entirely is a validation error, because "nobody thought about it"
  and "we checked and the answer is nothing" are different facts.

## What the runner's verdicts mean

| verdict | meaning |
|---|---|
| `PASS` | every gate that ran exited 0 |
| `FAIL` | a gate ran and said no — a measured negative |
| `NO-INSTRUMENT` | a declared gate script does not exist. **Not** a defect; nobody built the instrument. |
| `UNMEASURED` | nothing ran at all. Never read as green. |

And what `make queue-vacuity` says about the gates themselves:

| verdict | meaning |
|---|---|
| `NON-VACUOUS` | the control ran and the gate refused to pass. The gate works. |
| `VACUOUS` | the control ran and the gate **passed** on a known-negative. |
| `STUCK-RED` | a positive control ran and the gate refused to pass on a known-**positive**. As useless as a gate that can never go red, and it is what you get from fixing vacuity carelessly. |
| `CONTROL-ERROR` | the control could not be set up. Not a pass, and not a vacuous gate: nobody measured anything. |
| `EXEMPT` | an explicit `control-exempt` with a recorded reason. |
| `UNCONTROLLED` | no entry for this gate at all. Reported as a failure, never as a pass. |

`NO-INSTRUMENT` is kept separate from `FAIL` on purpose. Collapsing them would
let an unbuilt gate look like a measured defect, and would then let someone
"fix" that defect by writing a script that exits 0.

`UNMEASURED` is printed instead of `0/0 PASS` for the same reason: a 0/0 that
renders green is precisely how an assertion gets laundered into the appearance
of a measurement.
