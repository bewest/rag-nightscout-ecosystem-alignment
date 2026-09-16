# Verification records

**Status: DRAFT tooling and a DRAFT record. Nothing has been tagged, pushed, merged or
published. Requires maintainer review before it is relied upon.**

Audience: contributors and maintainers. This file is fully technical. The operator-facing
half of a release is `release-notes.md`, not this.

## What a verification record is

The quality-system record of **what was actually checked when a release was cut** — and,
just as much, of what was not.

It is not a plan, not a changelog and not a claim. For every item in the release it
carries the branch and the commit SHA that item **resolved to**, every gate and what that
gate **actually said when it was run**, the register entries the release touches with each
entry's **basis**, the test commands with their output summaries, and a mandatory section
naming **what was not verified and why**.

```
releases/<product>-<version>/
  verification-record.json    the record. Machine-readable, the source of truth.
  verification-record.md      generated FROM the json by the generator. Never hand-written.
```

Generator: [`tools/queue/verification-record.py`](../tools/queue/verification-record.py),
the seventh tool under `tools/queue/`, beside `manifest.py`, `validate.py`, `emit.py`,
`status.py` and `vacuity.py`. It reuses `status.py`'s gate executor rather than
reimplementing it, so a gate result in a record is the same measurement `make queue-status`
prints, not a second implementation free to drift from it.

## Why it exists

Three properties of this programme that prose cannot hold:

1. **Rule 3 — read-derived versus reproduced.** Measured across this programme, every
   register claim that had to be retracted was derived from *reading* source; not one that
   began with a *reproduction* has been. So the record classifies every register entry it
   carries by basis, and where an entry's status cell does not say, the record prints
   `unstated` rather than guessing. It will not infer a reproduction from
   measurement-shaped prose: inferring one is exactly the laundering rule 3 exists to stop.
2. **The claimed state and the measured state are different things.** Every item prints
   both — `state (claimed)` from the manifest and `verdict (measured)` from running the
   gates — and every disagreement between them is enumerated in the gaps section.
3. **A gate that was skipped is not a gate that passed.** `SKIP`, `NO-GATE` and `FAIL` are
   three distinct outcomes and none of them renders as a pass anywhere in either half.

## When it is captured, and the rule that it is never edited

**A record is captured once, at release time, from the state that is actually being cut.**

> **A verification record is never edited after it is captured.** If something changes — a
> gate starts passing, a branch moves, a register entry is upgraded from read-derived to
> reproduced, a gap is closed — that is a **new record with a new `captured_at`**, not an
> edit to the old one.

A record that is edited after the fact is not a record. It is a claim about the past that
nothing can check, and it is strictly worse than no record at all, because it reads like
evidence. Both files carry that rule in a header comment. If a record has ever been shared
outside this machine, it is superseded by the new one, never overwritten — the same rule
this repository applies to a tag other people have already fetched.

The `captured_at` timestamp is **passed in as an argument**. Nothing in the generator calls
a clock. That is what lets a record be re-derived and diffed instead of trusted.

## Capturing one

```sh
python3 tools/queue/verification-record.py \
    --release cgm-remote-monitor-15.0.9 \
    --captured-at "$(date +%Y-%m-%dT%H:%M:%S%:z)" \
    --parcel phase0 \
    --out-dir releases/cgm-remote-monitor-15.0.9
```

Selection is by `--id`, `--parcel` or `--state`. By default only `static` and `unit` gates
are run; `--integration` and `--network` opt the other kinds in, and whichever kinds were
**not** run are named in the record's own header and in its gaps section. The default is
deliberately the honest one: on this machine most `integration` gates cannot run at all,
because the worktree mongod ports are not what the briefing says they are.

Verify an existing record, and prove the Markdown really came from the JSON:

```sh
python3 tools/queue/verification-record.py --check --from-json <record.json>
```

## The three invariants the generator enforces

| # | Invariant | How it is enforced |
|---|---|---|
| 1 | **The gaps section may not be empty** | if `not_verified` is empty the generator writes *nothing* and exits 2. There is no override flag, because the flag would be used. |
| 2 | **The timestamp comes from outside** | `--captured-at` is required; the file never reads a clock. |
| 3 | **The Markdown is generated from the JSON** | `render()` takes the record dict and nothing else; `--check` re-renders and diffs. |

Invariants 1 and 3 are proven by execution, not by inspection — see below.

## Rule 2: the generator is proven non-vacuous

A check that has never failed is not yet evidence. `--self-test` takes the real manifest,
finds an item in the selection whose gates all pass, writes a **copy** of the manifest with
one of that item's gates replaced by `exit 7`, captures a second record from the copy, and
asserts six things about it. Nothing is written to the real manifest or the real release
directory.

```sh
python3 tools/queue/verification-record.py --self-test \
    --captured-at 2026-09-15T23:55:00-07:00 --parcel phase0
```

Reproduced, 2026-09-15:

```
BEFORE  P0-B  verdict=PASS  gates 2/2
        gates[0] PASS  git -C externals/... merge-base --is-ancestor origin/dev bf/cache
        register: BF-06=claimed-fixed-gates-pass, BF-07=claimed-fixed-gates-pass
AFTER   P0-B  verdict=FAIL  gates 1/2
        gates[0] FAIL  exit 7
        output tail: ABLATION: this gate is broken on purpose
        register: BF-06=claimed-fixed-but-a-gate-failed, BF-07=claimed-fixed-but-a-gate-failed
  OK   item verdict moved PASS -> FAIL
  OK   the broken gate is recorded as FAIL
  OK   the failing command's own output is in the record
  OK   the Markdown shows the failure, not a pass
  OK   register entries moved off claimed-fixed-gates-pass
  OK   the gaps section grew
```

The failure reaches all four places it must: the gate, the item verdict, the **register
closure state** of both entries that item carries, and the gaps section — and the injected
command's own stderr is quoted in the record, so the failure cannot be mistaken for a
different one. Invariant 1 was ablated separately: a record whose `not_verified` array was
emptied by hand is refused with exit 2 and no file is written.

## How far two captures can be diffed — measured, and narrowed once

Two captures of this release were diffed field by field. **Stable:** resolved SHAs,
commits-ahead counts, every gate outcome, every item verdict, every register closure state
and basis, the counted test summaries, and all 76 gap entries. **Moves:** the gate
transcripts `output_tail`, `output_bytes` and `output_sha256` (25 of 164 transcript fields),
because the commands are not deterministic — mocha prints its own millisecond timings and
node prints its pid.

One field that is a *conclusion* rather than a transcript moves with them, and an earlier
draft of the generator's own docstring implied it did not: `output_summary.last_line`, for
a gate whose last line of output is a benchmark duration. So diff two captures on outcomes,
verdicts, bases and gaps. Do **not** diff them on digests, or on a `last_line` that quotes
a duration. The digest is there to let a reader bind a full log they hold to *this* capture,
not to let two captures be compared byte for byte.

## What a record does not do

It does not ship anything, and it does not assert that a defect has reached an operator. A
fix reaches operators when a human pushes and a maintainer merges, and both of those are
outside the record. Every branch in the current record is local and unpushed; the record
says so per item, and says plainly that the remote was never contacted.

It also does not replace the register, the queue or the release notes. It is the
cross-section of all three at one instant, with the measurements attached.

---

*Draft, 2026-09-15. Prepared locally; nothing was pushed, tagged, merged or published.
Requires maintainer review before it is relied upon. Nightscout is not a medical device and
nothing here is medical advice.*
