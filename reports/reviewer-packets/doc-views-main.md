<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — DOC-VIEWS

**A reviewer-facing surface over the queue: three overview pages and a packet
per PR**

| | |
|---|---|
| repository | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@1a10007b` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=DOC-VIEWS` is the measurement |
| semver | `n/a` |

## What this changes

docs/00-overview/{PROGRAMME-STATUS,NEEDS-A-HUMAN,REVIEWER-ONBOARDING}.md,
reports/reviewer-packets/ (17 generated files), tools/queue/emit_views.py,
tools/queue/emit_packets.py, and four Makefile targets. No shipping code.

## Why that semver

documentation and repository tooling

## What an operator would notice

> Nothing changes in Nightscout itself. This is a set of pages explaining
> what the project is working on and what is still waiting on a person.

## Who should review this, and why

maintainer, and then ideally a person who has NEVER seen this repository -
that is the only way to find out whether REVIEWER-ONBOARDING.md works, and
this queue cannot gate it. The reading path claims about an hour.

## What was measured

**`python3 tools/queue/emit_views.py --check`** &nbsp;·&nbsp; kind: `static`

FAILS when a generated block inside docs/00-overview is stale with respect to
the manifest. The overview pages are HYBRID - prose a human writes, wrapped
around blocks a program owns - because a fully generated page cannot carry an
argument and a fully hand-written one becomes the thing the docs-truth parcel
exists to repair. Ablated 2026-09-16: editing one row of the horizons table
inside the fence is reported stale and queue-check goes red.

**`python3 tools/queue/emit_packets.py --check`** &nbsp;·&nbsp; kind: `static`

FAILS when a reviewer packet is stale OR orphaned. Both ablated 2026-09-16 - a
changed semver row in P0-A's packet, and a spare file added to the directory.
ORPHANED IS THE ONE THAT MATTERS: a packet left behind for an item that no
longer wants a reviewer points a volunteer at finished work, which spends the
scarcest resource this programme has on nothing.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- NOTHING HERE MEASURES WHETHER THE PROSE IS TRUE. The generated blocks are
  checked against the manifest; the argument wrapped around them - which
  horizon matters, what a new reviewer should read first, that review
  capacity rather than engineering is the binding constraint - is a human
  claim carrying a date. That is the deliberate half of the hybrid, and it
  is also exactly where DOC-PLAN and DOC-SEQUENCING's defects live. These
  pages are new, so they have not drifted yet; treat that as a fact about
  their age, not their construction.
- The 42-defect operator-exposure figure in PROGRAMME-STATUS.md is counted
  by hand from the register's section 1 (43 rows, less BF-12 which is
  retracted as not reproducing). A gate would need the register to carry
  machine-readable per-entry status, which it does not - the same missing
  field DOC-REGISTER names. Until that exists the number is re-counted by
  whoever edits, and it WILL go stale silently.
- Whether REVIEWER-ONBOARDING.md actually onboards anybody is not measurable
  from inside the repository, and it is the only question about this item
  that matters. The evidence would be a first-time reviewer completing a
  packet - which is also the outcome the whole item exists to produce.

## Evidence

- [`docs/00-overview/PROGRAMME-STATUS.md`](../../docs/00-overview/PROGRAMME-STATUS.md)
- [`docs/00-overview/NEEDS-A-HUMAN.md`](../../docs/00-overview/NEEDS-A-HUMAN.md)
- [`docs/00-overview/REVIEWER-ONBOARDING.md`](../../docs/00-overview/REVIEWER-ONBOARDING.md)
- [`reports/reviewer-packets/README.md`](../../reports/reviewer-packets/README.md)

## Notes carried on the item

Built 2026-09-16 on the maintainer's instruction to produce a fresh
perspective on progress and a place where reviewers and teammates can
collaborate. The shape was chosen explicitly: hybrid generation for the
overview pages, full generation for the packets, and an audience of the
maintainer plus reviewers being recruited. The finding the pages are built
around is the reviewer-load table - 52 of 75 items route to the maintainer,
and the SECURITY and SAFETY rows name a KIND of reviewer with no individual
attached to any of them. P0-C is the sharpest case: gate- passing, and waiting
on a security reviewer who does not exist.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=DOC-VIEWS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `74fc6619`.*
