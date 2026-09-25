# Reviewer onboarding — read this first

*Contributor-facing. Written for somebody who has never seen this repository and
is considering reviewing work in it. Prose revised 2026-09-24 against
cgm-remote-monitor `origin/dev` `153e5658` and `origin/master` `92d08342` (tag
`15.0.8`).*

Thank you for looking. What you would be taking on, so you can decide quickly:

> This project has **495 modernization commits by one author** and **100 child pull
> requests merged with zero human reviews**. Confidence in all of it currently rests
> on automated gates and the author's own evidence documents. That is the gap you
> would be filling, and it is the largest risk the programme carries.

## What you are looking at, and what it is not

Nightscout is open-source software that people run themselves to see their own or
a family member's glucose data. The Nightscout Foundation stewards it; it does not
manufacture devices or prescribe therapy. **Users build and run these tools
themselves**, which means a defect here reaches somebody's kitchen table, not a
support queue.

That shapes what review means here. In most codebases the bad outcome is a crash.
Here the bad outcome is **a read that is silently wrong** — a number that renders
plausibly and is not the number in the database, or an alarm that does not fire.
A crash is loud. These are not. So a change that "passes the suite" is the failure
mode to design against, not the evidence to relax on.

**Two repositories, and they have different rules.** This repository
(`rag-nightscout-ecosystem-alignment`) holds tooling, documentation, evidence and
QC harnesses. The shipping application is `cgm-remote-monitor`, and it **stays
pristine** — findings are written up here and referenced from there, never pasted
into its code comments. Harnesses here `require()` the shipping module by path so
the two cannot drift.

---

## The reading path — about an hour

Five documents, in this order. Each row says what that document is *authoritative
for*, which matters because several documents discuss the same facts and only one
of them owns each.

| # | read | ~ | authoritative for |
|---|---|---|---|
| 1 | [PROGRAMME-STATUS.md](PROGRAMME-STATUS.md) | 5 min | the three horizons, and which constraint is actually binding |
| 2 | [`queue/README.md`](../../queue/README.md) | 10 min | how work state is recorded, and why `state` is a claim rather than a fact |
| 3 | [`../30-design/remedial/nightscout-backfix-register.md`](../30-design/remedial/nightscout-backfix-register.md) — §3 and §4 first, then skim §1 | 20 min | **defect facts and `BF-` ids**. Nothing else may contradict it |
| 4 | [`../30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../30-design/remedial/phase0-pr-sequencing-2026-09-15.md) | 15 min | which branches are coupled, and what order they can land in |
| 5 | the packet for whichever PR you take, in `reports/reviewer-packets/` | 10 min | that one change: what it does, what the evidence proves, what it does **not** prove |

If you only read two, read **1** and **3**.

Then, by horizon, when you need it:

- **Modernization** — [`../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)
- **Multitenancy** — [`../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) (decisions D1–D17)
- **Research and measurements** — `../60-research/{remedial,modernization,tenancy}/`, filed by horizon

---

## Five conventions you need, or the documents will read wrong

**1. A claim is not a measurement.** `queue/work-queue.yaml` carries `state:` for
each item. That field is *only a claim about what the gates will say*.
`make queue-status` runs them. The runner prints `CLAIM DIVERGES` when they
disagree. `queue/QUEUE.md` is generated so that nobody can quietly edit a status
into the human-readable view.

**2. `no-gate:` is bookkeeping, not a gap in it.** Every queue item's gate is either
a runnable command or an explicit `no-gate:` marker carrying a reason. There is no
third option, and validation rejects a manifest where the gate list is empty —
because a missing gate that renders as blank looks exactly like a passing one.

**3. A check that has never failed is not yet evidence.** Before a gate counts, the
thing it tests gets broken to confirm the gate notices. Two ways a gate goes
vacuous: the corpus never exercises the property, or the code never distinguishes
the branches. And a green ablation has two opposite meanings — the
check may be vacuous, **or the break may not have broken anything**. Always confirm
the break landed before concluding anything about the test.

**4. Read-derived and reproduced are different grades of claim.** Register entries
are marked as one or the other. Across Phase 0, every claim that failed when run
was read-derived, and two prescribed fixes would have made things worse. Treat any
"the fix is X" as a hypothesis until somebody runs it; if you are reviewing a fix,
that is the thing to be suspicious of.

**5. Neither `fixed` nor `merged` means released.** In the register, `fixed` means
repaired on a branch that has not been merged; `merged` means merged into
`origin/dev` and not released; `released` means in a tagged release operators run.
No programme fix is released: `origin/master` is 345 commits behind `dev`
(2026-09-23) and the shipping tag is 15.0.8. The register's open count is therefore
not "the defects still shipping". As computed from the register's §1 on 2026-09-23,
**73 defects reach every self-hoster on 15.0.8**: of the 75 in §1, 25 are open (two of
them, BF-80 and BF-106, exist only on `dev`), 42 merged, 1 partly merged and 7 fixed on a branch. See [PROGRAMME-STATUS.md](PROGRAMME-STATUS.md#status-words-merged-is-not-released).

---

## Picking something to review

Four entry points, easiest first:

1. **An open pull request.** [NEEDS-A-HUMAN.md](NEEDS-A-HUMAN.md) lists them with a
   one-line description, and `reports/reviewer-packets/` has a bounded packet for
   each item awaiting review. One 15.0.9 pull request is open: #8758 (records keep
   their own `_id` across API v1, v3 and the websocket; a large change to core data
   paths, where careful review is most useful). Twenty-seven others are merged into
   `dev`, including #8754 (login security fixes and `TRUST_PROXY`), none released. The connector's fixes are released as
   `nightscout-connect` `0.1.0` (2026-09-24), which `dev` pins exactly (#8762).
2. **A security or safety item.** #8754 (login security fixes and `TRUST_PROXY`) is
   merged into `dev` but not released; a second pair of eyes on its evidence is still
   welcome before 15.0.9 is tagged. Among safety items, `BFQ-92` (a page with no
   glucose reading presents no server alarm, including device alarms) has no fix yet.
3. **The release.** `RT-0` (release PR #8598, 15.0.9) is open, green on CI, and has no
   approving review. It is 62 first-parent merges (`dev` `4f705217`, 2026-09-25); its
   readiness assessment is
   [`release-readiness-15.0.9-2026-09-22.md`](../30-design/modernization/release-readiness-15.0.9-2026-09-22.md)
   (a 2026-09-22 snapshot), and the latest combined test run is
   [`rc-15.0.9-combined-010-2026-09-24.md`](../30-design/remedial/rc-15.0.9-combined-010-2026-09-24.md).
4. **An `unsettled` item.** `BFQ-09`, `A7A-7` — it is not yet established
   that these are defects at all. Settling one either way is a complete,
   self-contained contribution.

---

## What good review looks like here

- **Check what the gate does not prove.** Every packet has a section for this. A
  gate can pass for the wrong reason.
- **Stop and report a mismatch; never reach for the nearest thing that works.**
  Many real defects here surfaced that way — a dropped `RegExp` that widened a live
  query, a synthesised `acknowledged`, a missing non-upserting replace, an inverted
  `$exists`. In each case a workaround would have kept the suite green.
- **Call out changed test expectations loudly.** If a change edits what a test
  expects, that needs a stated reason, in the diff, where a reviewer will see it.
- **Say when you are not sure.** "I could not tell whether this is right" is a
  useful review outcome and is recorded as such.

## Two rules that are not negotiable

- **Never push, merge, tag or publish.** Prepare work locally and stop. Pushing to
  `dev` or `master` builds and publishes a Docker image — those branches are
  publication events, not branches. A human makes that call deliberately.
- **Treat any user-submitted data as sensitive health data.** CGM traces, Nightscout
  exports, crash and device logs. Do not reproduce names, emails or other
  identifiers in issues, comments, commits or documentation.

---

## Getting set up

```bash
make bootstrap        # clone the external repositories into externals/ (git-ignored)
make queue-status     # run every static + unit gate — this is the measurement
make queue-check      # what CI runs
make queue-vacuity    # ask every gate whether it could actually fail
make views-check      # confirm the generated tables in docs/00-overview are current
```

If you are reviewing a branch, give yourself **your own git worktree and your own
test database**. Worktrees share a MongoDB instance and concurrent runs destroy
each other's data.

`npm run test:unit` is **not** the whole
suite and is **not** database-free. It resolves to 44 of 159 test files, and
without MongoDB it fails six. CI runs all 159. If a packet tells you to run a
specific test, run that one rather than assuming the local script covers it.

---

## Questions, and who to ask

Open an issue in this repository, or comment on the pull request you are reviewing.
If something in these documents contradicts something else, say so: contradictions
are tracked as defects in the `docs-truth` parcel, because readers act on the section
they read. The standard these documents are held to is
[DEFINITION-OF-DONE.md](DEFINITION-OF-DONE.md).

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-24**, against cgm-remote-monitor-official `153e5658` and this repository at `b362302b`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
