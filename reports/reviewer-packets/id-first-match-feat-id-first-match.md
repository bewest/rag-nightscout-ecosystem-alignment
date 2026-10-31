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

# Review packet — ID-FIRST-MATCH (PR #8879)

**Identifier-first matching on every collection and path, with D-LOOP-ID's rules
(eligible for 16.0.0 through the entry bar)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/id-first-match` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=ID-FIRST-MATCH` is the measurement |
| semver | `minor` |
| register entries | `BF-215`, `BF-216` |

## What this changes

The write step's match rule, applied on: lib/server/entries.js upsertQueryFor
(today sysTime+type unless identifier is present after UUID normalisation);
lib/server/devicestatus.js create (insertMany becomes an upsert on identifier
when one is present); lib/server/websocket.js dbAdd; lib/server/treatments.js
upsertQueryFor gains the adoption rule.

## Why that semver

Re-sends that create a second record today (entries, devicestatus, socket)
become matches; v1 treatments change from "identifier match or fallback key"
to the Q1 rule, so a labelled re-send no longer overwrites a stored record
that carries a different identifier.

## What an operator would notice

> An app that labels each record with its own id can re-send it without
> creating a second copy, for glucose readings, treatments and loop status
> alike. An existing record without such a label can be claimed by the first
> labelled re-send of the same reading or treatment; a record already
> labelled by a different id is never overwritten.

## Who should review this, and why

maintainer, plus a second human - re-send behaviour clients see changes

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Not started. Gate to write: the write-contract matrix extended with
  identifier cells per collection and path: (1) same identifier, re-send ->
  one record; (2) identifier, stored record on the natural key with no
  identifier -> adopted, one record; (3) identifier, stored record on the
  natural key with a different identifier -> a second record, the first
  untouched. Control: drop the identifier clause from one path and cell (1)
  goes red there.

## Blocked on

`WC-STEP-PATCH`, `ID-SIMPLE-MATCH`, `ID-VALIDATE`

## Evidence

- [`docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md`](../../docs/30-design/platform/upstream-asks-loop-identifier/reply.body.md)
- [`docs/30-design/tenancy/write-contract-spec-2026-10-07.md`](../../docs/30-design/tenancy/write-contract-spec-2026-10-07.md)
- [`docs/60-research/tenancy/identifier-duplicates-2026-10-17.md`](../../docs/60-research/tenancy/identifier-duplicates-2026-10-17.md)

## Notes carried on the item

2026-10-31 later (GitHub, about 05:45Z): #8879 at 931e5e60, 0 behind dev
368e6c23: slice 4 (merge on match, treatments replaced on every path) pushed;
CI fails lint (no-useless-assignment, lib/storage/write-intent.js:1450).
Carries BF-215 and BF-216 (slice 2). 2026-10-31: draft #8879 at 5cdd9577 (base
dev): slices 1, 2, 5 (+5b) and 3 built and pushed, dev 368e6c23 merged; slice
4 being rebuilt with treatments replaced on every path (maintainer
2026-10-30); 6 and 6a prepared on prep/id-first-s6 47377fa3. Owner session
-4f. 2026-10-29 (maintainer, D-LOOP-ID; next-gen plan §4.2): the rules this
item builds are decided, and it is eligible for 16.0.0 through the entry bar
(plan §1a), with ID-BATCH-RESULTS and ID-RESEND-SWITCH. Scope is every
collection and path. (1) Merge on match stays the default for a re-send with
changed fields; v3 keeps refusing a changed date, device or eventType; PUT
replaces (ID-V3-IMMUTABLE-DECISION). (2) Merge on match keeps fields the re-
send leaves out (RFC 7386), measured per path first: the census reads replace
on several paths, not yet measured, and every path that changes is listed cell
by cell. (3) A re-send after delete is acknowledged and stays deleted on every
path, with the cell-by-cell impact documented for revert (ID-DELETE-REUSE-
DECISION). (4) Socket dbUpdate, dbUpdateUnset and dbRemove accept identifier
when no _id is given, and activity creates match on identifier; both are
additive and conditional on the extended matrix showing every existing form
unchanged. (5) The identifier format is enforced with or before this item (ID-
VALIDATE, added to blocks_on), because two clients sending the same
placeholder would be merged. (6) Natural keys for re-sends without identifier
are a separate item, ID-NATURAL-KEY. A default changes only in a major: 16.0.0
through the entry bar, otherwise 17.0.0. Q1 rule as proposed in LOOP-ID-REPLY:
an identified write that finds no identifier match may adopt a stored record
with NO identifier on the natural key; never one with a different identifier.
ID-DUP-MEASURE found Loop writing one syncIdentifier to a Suspend Pump and a
Temp Basal at the same instant (9 pairs at one site); if Loop sends
syncIdentifier as identifier (the reply names syncIdentifier as Loop's
treatment identity), matching on it alone would fold those pairs into one
record. The reply draft does not raise this yet. Re-shaped 2026-10-17: the v1
entries and devicestatus identifier match ships first, on dev, as the release-
train item ID-SIMPLE-MATCH (maintainer: after 15.0.9, after cut 1's rebase).
This item keeps the socket dbAdd match and the Q1 adoption rule, and absorbs
ID-SIMPLE-MATCH's rule into the write step once WC-STEP-PATCH exists. The
rewritten Loop reply lists Q1 under "later, only if needed".

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ID-FIRST-MATCH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
