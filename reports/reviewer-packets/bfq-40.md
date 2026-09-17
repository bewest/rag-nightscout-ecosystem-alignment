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

# Review packet — BFQ-40

**BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-40` is the measurement |
| semver | `minor` |
| register entries | `BF-40` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

BOOLEAN_OPERANDS / readBooleanOperand in lib/server/query.js, applied over the
built query so it also covers fields the type table does not name. CORRECTED
2026-09-17: this entry previously located the fix at lib/server/query-
coercion.js:90 and asserted the defect survives bf/coercion. Both were read-
derived and both are wrong. The NON_VALUE_OPERATORS exclusion in query-
coercion.js is a different mechanism - it stops the field-domain coercer
mangling the operand - and excluding the operand from THAT is what lets the
boolean reader own it.

## Why that semver

It changes what a documented v1 endpoint returns for a documented query
parameter, in the direction of correctness, which is the same class as BF-02
and BF-03 and needs the same release note.

## What an operator would notice

> If you or a tool you use asks Nightscout for records that do NOT have a
> particular field - for example entries with no "sgv" value - today's
> release gives you back exactly the records that DO have it. The opposite
> of what was asked, with no error. Asking for records that DO have a field
> works correctly. This is repaired on bf/coercion (PR #8737), which has not
> been released.

## Who should review this, and why

maintainer

## What was measured

**`NSREVIEW_ROOT=${NSREVIEW_ROOT:?} node tools/review/probes/pair-reads-coercion.js --base "$NSREVIEW_BASE_URL" -`** &nbsp;·&nbsp; kind: `integration`

The instrument this entry said did not exist. Measured 2026-09-17 on a
582-document seed (577 sgv, 5 mbg): find[mbg][$exists]=false returns 577 on
bf/coercion and 5 on dev. The arm asserts against the seeded expectation,
never against the same build's list endpoint - on bf/reads alone those two
agree at 5 and both are wrong.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

COSTS P0-D SOMETHING BEFORE IT IS PROPOSED. bf/coercion's operator-facing text
says find[sgv][$exists]=true "became $exists: NaN, which MongoDB reads as
false, so the query returned exactly the records you did not ask for". That
sentence is false - $exists=true is answered correctly before and after - and
it tells operators to distrust queries that were right. What the coercion
genuinely broke and the fix genuinely repairs is $regex, a much smaller blast
radius than the one claimed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-40` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
