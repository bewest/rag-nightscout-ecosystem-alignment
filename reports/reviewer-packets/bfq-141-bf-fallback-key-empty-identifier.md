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

# Review packet — BFQ-141

**BF-141 - after #8780, a v1 treatment re-sent with an empty identity
(identifier "") is stored twice**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/fallback-key-empty-identifier` |
| base | `origin/dev@ff93fa94` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-141` is the measurement |
| semver | `patch` |
| register entries | `BF-141` |

## What this changes

One commit at aaf67785. lib/server/treatment-fallback-key.js (the no-identity
clause of fallbackQuery: {$eq: null} becomes {$in: [null, ""]} for
syncIdentifier, id, uuid, NSCLIENT_ID and identifier), used by
lib/server/treatments.js upsertQueryFor and lib/server/websocket.js
processSingleDbAdd; tests/api.same-time-treatments.test.js (71 new tests),
with changed expectations in tests/storage.selector-hardening.test.js and
tests/websocket.input-validation.test.js. API v3 is unchanged. A write with a
non-empty identity is unchanged.

## Why that semver

restores 15.0.8's single record for a re-sent v1 treatment with an empty
identity

## What an operator would notice

> Not in any release. In the development version only, an app that sends a
> treatment with an empty identity field and then sends the same treatment
> again could make Nightscout store it twice, so carbs or insulin could be
> counted twice on the site. No app is known to do this. The fix is ready
> for review for 15.0.9. This is not medical advice.

## Who should review this, and why

maintainer (API semantics)

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official grep -q "query\[field\] = noIdentity()" bf/fallback-key-em`** &nbsp;·&nbsp; kind: `static`

The branch's no-identity clause uses noIdentity(), which matches null and ""
(origin/dev ff93fa94 matches null only and fails this). A presence check only;
tests/api.same-time-treatments.test.js decides (29 of its tests fail on
ff93fa94). Point it at origin/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by booted-server probes that need MongoDB, so
  they are not queue gates. 2026-09-26, Node 22.23.2, MongoDB 7.0.43:
  tools/lab/triage-2026-09/api3-empty-identifier-delete.js re-send arm,
  identifier "" stored 2 on ff93fa94 and 1 on aaf67785 and v15.0.8 92d08342
  (no other line differs between ff93fa94 and aaf67785); same-time-resend-
  shapes.js and same-time-carbs.js give the same table on ff93fa94 and
  aaf67785, exit 0.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/api3-empty-identifier-delete.js`](../../tools/lab/triage-2026-09/api3-empty-identifier-delete.js)
- [`tools/lab/triage-2026-09/same-time-resend-shapes.js`](../../tools/lab/triage-2026-09/same-time-resend-shapes.js)
- [`reports/phase0-pr-bodies/fallback-key-empty-identifier.md`](../../reports/phase0-pr-bodies/fallback-key-empty-identifier.md)

## Notes carried on the item

Filed 2026-09-26 from the review of #8778 (BF-140). The maintainer decided the
same day to fix it for 15.0.9. 2026-09-26 - FIXED on bf/fallback-key-empty-
identifier aaf67785 (local, not pushed), one commit on origin/dev ff93fa94. 29
of 71 new tests fail on ff93fa94 (2 records where 1 was expected); reverting
the query line turns the same 29 red. Full suite 3467/0/3 on a fresh database
(ff93fa94: 3396/0/3). PR body draft: reports/phase0-pr-bodies/fallback-key-
empty-identifier.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-141` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-26, against cgm-remote-monitor-official `ff93fa94`.*
