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
reports/reviewer-packets/ (one generated packet per item awaiting review, plus
a README), tools/queue/emit_views.py, tools/queue/emit_packets.py, and four
Makefile targets. No shipping code.

## Why that semver

documentation and repository tooling

## What an operator would notice

> Nothing changes in Nightscout itself. This is a set of pages explaining
> what the project is working on and what is still waiting on a person.

## Who should review this, and why

maintainer, and then ideally a person who has never seen this repository - the
only way to find out whether REVIEWER-ONBOARDING.md works, and this queue
cannot gate it. The reading path claims about an hour.

## What was measured

**`python3 tools/queue/emit_views.py --check`** &nbsp;·&nbsp; kind: `static`

FAILS when a generated block inside docs/00-overview is stale with respect to
the manifest. The overview pages are hybrid: hand-written prose around
generated blocks. Ablated 2026-09-16: editing one row of the horizons table
inside the fence is reported stale and queue-check goes red.

**`python3 tools/queue/emit_packets.py --check`** &nbsp;·&nbsp; kind: `static`

FAILS when a reviewer packet is stale or orphaned. Both ablated 2026-09-16 - a
changed semver row in P0-A's packet, and a spare file added to the directory.
Orphaned matters because a packet left behind for an item that no longer wants
a reviewer points a volunteer at finished work.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Nothing here measures whether the prose is true. The generated blocks are
  checked against the manifest; the hand-written text around them - which
  horizon matters, what a new reviewer should read first, that review
  capacity rather than engineering is the binding constraint - is a dated
  human claim, and it is where DOC-PLAN and DOC-SEQUENCING's class of defect
  can recur.
- The operator-exposure figure in PROGRAMME-STATUS.md (55 §1 defects as of
  2026-09-21) is prose, not a generated block. It was computed by the
  coverage gate's register parser, but nothing re-derives it on the page, so
  it goes stale silently when register statuses change; whoever edits the
  register's §1 statuses must re-derive it.
- Whether REVIEWER-ONBOARDING.md actually onboards anybody is not measurable
  from inside the repository, and it is the only question about this item
  that matters. The evidence would be a first-time reviewer completing a
  packet.

## Evidence

- [`docs/00-overview/PROGRAMME-STATUS.md`](../../docs/00-overview/PROGRAMME-STATUS.md)
- [`docs/00-overview/NEEDS-A-HUMAN.md`](../../docs/00-overview/NEEDS-A-HUMAN.md)
- [`docs/00-overview/REVIEWER-ONBOARDING.md`](../../docs/00-overview/REVIEWER-ONBOARDING.md)
- [`reports/reviewer-packets/README.md`](../../reports/reviewer-packets/README.md)

## Notes carried on the item

Built 2026-09-16 on the maintainer's instruction: a view of progress and a
place where reviewers and teammates can collaborate. Hybrid generation for the
overview pages, full generation for the packets, audience the maintainer plus
reviewers being recruited. The pages are built around the reviewer-load table
(generated in PROGRAMME-STATUS.md): most items route to the maintainer, and
the SECURITY and SAFETY rows name a kind of reviewer with no individual
attached.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=DOC-VIEWS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
