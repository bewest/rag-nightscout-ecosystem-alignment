# Fill a fixture's time gap at restore instead of snapshotting continuations

*Draft for the maintainer, 2026-11-25. Capacity harness only; no product change. Builds on the Codex
continuation work (`codex/c5-fixture-continuation-20261124`, pickup `e76f2b27d7`) and the fixture-clock
finding (no clock shifting; the catch-up after restore is the honest model of a restarted deployment).
Decisions it relies on: [fixture-attestation-witness](multitenancy-decisions.md#fixture-attestation-witness),
[nominal-clinical-write-age](multitenancy-decisions.md#nominal-clinical-write-age).*

## Problem

A capacity fixture is a PostgreSQL snapshot of synthetic history with absolute timestamps. The evaluator,
the clinical deadlines and the 48-hour read windows all use the wall clock. Once a fixture is more than about
24 hours old, the active tenants' recent windows thin out, and a run no longer represents sites that are
uploading. Today the harness handles this by **continuation**:
1. clone the parent;
2. append the missing hours through the deterministic generator;
3. verify;
4. capture and register a new child snapshot;
5. restore the child for the run.

**What it has cost (reproduced, from the C5 campaign records):**
- One fixture refresh before every paid window.
- Two of three continuation clones failed verification. One failure has no established cause.
- Clone and snapshot custody across attempts.
- A paid attempt lost to a deadline that outran the history horizon.

The child snapshot is not used for anything except the next restore.

## Proposal

Fill the gap as part of the run:
- **Restore** the long-lived parent snapshot.
- **Generate** the events between the parent's anchor and the restore time with the same deterministic generator and the same continuation rules Codex built: continued identifiers, existing tenant phase, the extended shapes of the five deep tenants.
- **Insert** them through the bulk path into the restored database.
- **Verify** only the appended rows, by count and content digest. The parent rests on its attestation, as already decided.
- **Then** let the evaluator catch up and start the load.

No child snapshot, no chain of continuations, no separate refresh job. The parent changes only when its
schema or history shape changes, or when the gap exceeds a cap.

| | Continuation (today) | Gap fill at restore |
|---|---|---|
| Snapshots per paid window | one new child | none |
| Verification | parent re-read (now witnesses) plus child digest | appended rows only |
| Staleness | refused after 24 h; refresh needed | filled up to the cap at every restore |
| Failure surface | clone, append, capture, register, custody | one append inside the run, with its own receipt |
| Restore time | unchanged | plus the gap-fill time (in the derived grant) |

## Cost and cap

**Read-derived from the continuation receipt.**
- The four-hour append wrote 480,000 SGVs, 646,442 device statuses and 297,759 treatments: about 1.42M documents, or roughly 35.6 per tenant-hour across 10,000 tenants.
- A 24-hour gap is therefore about 8.5M documents.
- Through the product write path at the original loader's rate (17.6M documents in 9,166 s with three processes, about 1,925 per second), that is about 74 minutes. That is too long for every run.

So:
- **Fill through the bulk path** (COPY into the clinical tables under the restore role, as the restore contract already does), and only for the active-tenant prefix. Its rate is **unmeasured**; measuring it is the first step.
- **Cap the gap** (proposed: 12 hours). Beyond the cap, refresh the parent once, off the paid window.
- **Budget the fill** in the derived work grant and refuse at render if it does not fit. This is the same mechanism as the seed-census grant.

## What it retires and what it keeps

**Retires:**
- the child snapshot capture, registration and custody;
- the per-window refresh job;
- the 24-hour staleness refusal as a routine stop.

**Keeps:**
- the generator and its continuation rules;
- the attestation and witnesses;
- the catch-up gate, so evaluator catch-up over the filled gap stays visible;
- the post-load digest.

## Trade-offs and open questions

- **Bulk path, not product path.** Rows filled through the bulk path skip API admission, like a restore. The evaluator catches up on them as it would after a real restore. The run's own load still uses the product write path, so write-path cost is measured where it matters.
- **Restore time grows with the gap.** The cap bounds it, and the grant prices it.
- **Unmeasured:** the bulk fill rate on the paid PostgreSQL node, and catch-up time after a 12-hour fill at 5k and 10k. Both are first-run measurements.
- **The deep tenants' 90-day history** stays in the parent. Only their recent gap is filled.

## First steps

1. Measure the bulk fill rate locally on a 1k restore for 4 h and 12 h gaps.
2. Implement the fill as a harness stage after restore and before the catch-up gate, with an append-only receipt.
3. Replay the derived grant against the C5 attempts that needed a refresh.
