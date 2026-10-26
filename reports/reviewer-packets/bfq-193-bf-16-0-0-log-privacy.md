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

# Review packet — BFQ-193 (PR #8856)

**BF-193 - the realtime socket and other write paths log every record written
through them**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-log-privacy` |
| base | `official/dev@47723cda` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-193` is the measurement |
| semver | `patch` |
| register entries | `BF-193` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Log content only. New helper recordForLog in lib/server/log-privacy.js (with
debugLogging(env), credentialSpellings and redactText shared with
errorForLog). Call sites: lib/server/websocket.js (the dbUpdate,
dbUpdateUnset, dbAdd and dbRemove entry lines, the two Got results lines and
nine refusal lines in checkConditions; the per-write line moves after the
request is accepted), lib/api/treatments/index.js (v1 POST, line 146, and
PUT), lib/api/profile/index.js, lib/api/activity/index.js,
lib/server/profile.js, lib/data/treatmenttocurve.js, lib/profilefunctions.js
and the treatmentnotify and loop plugins (through sbx.debugLogging). README's
DEBUG_LOGGING entry. No new setting.

## Why that semver

log content and log line text only; no API, stored data or setting change

## What an operator would notice

> Nightscout's server log no longer contains the records apps send it
> (glucose values, insulin and carbohydrate amounts, notes). Each write is
> logged as a short summary instead. To see the records while
> troubleshooting, set DEBUG_LOGGING=true and restart; debug logs then
> contain health data, so turn it off again afterwards and keep access to
> your hosting logs limited. Anything that reads the old log lines sees a
> new format.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 47723cda bf/16.0.0-log-privacy`** &nbsp;·&nbsp; kind: `static`

The fix branch contains dev 47723cda. Red if the branch is rebased off dev or
deleted.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 8ae43eb4 bf/16.0.0-log-privacy`** &nbsp;·&nbsp; kind: `static`

The fix commit 8ae43eb4 is on the branch. Red if the branch is rewritten
without it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Behaviour is measured outside the queue (the suite needs MongoDB).
  2026-10-26 on 8ae43eb4, Node 22.23.4: npm test 4289 passing, 1 failing, 3
  pending, the failure environmental (tests/development-watch.test.js,
  ENOSPC on file watchers); npm run test:all 4617 / 1 / 3, the same failure.
  The new test fails 6 of 7 cases with the source reverted. Trial merge with
  #8854 fa22d573 clean.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-26, after #8854 merged (dev 7ad3a67f): session -66 merged dev 7ad3a67f
into bf/16.0.0-log-privacy locally as 6b6ad320, no conflicts, not pushed (the
PR head is still 8ae43eb4; the push is the maintainer's). On 6b6ad320: npm
test 4436 passing, 0 failing, 3 pending; test:all 4764 passing, 0 failing, 3
pending. The log lines #8854 adds are console.error(err) on storage errors
(the follow-up below: error objects may contain documents) and the validation
line, which names rules and fields only. #8856 and #8859 merge with each other
cleanly. 2026-10-26, later: draft PR #8856 to dev (bf/16.0.0-log-privacy, head
8ae43eb4), opened by the maintainer. 2026-10-26, later (maintainer): BF-193
stays its own PR, separate from the 16.0.0 re-send and merge bundle.
2026-10-26: decided by the maintainer (session -66): debug-gated payload
logging through one gate, the existing DEBUG_LOGGING (env.debug.logging), no
new setting, using recordForLog in lib/server/log-privacy.js. The summary
(operation, collection, client, ref, eventType or item count) is always
logged; the payload only with debug on; refusal lines are bounded (8192
characters) and redacted. Built as bf/16.0.0-log-privacy 8ae43eb4, one commit
on dev 47723cda, not pushed. Not a pre-tag requirement for 16.0.0 (maintainer,
2026-10-26). Release note: set DEBUG_LOGGING=true to see the records clients
send; debug logs then contain health data. Follow-up, read-derived and
unverified, not filed as an id: storage error lines that log whole MongoDB
error objects (lib/server/treatments.js:173, 284 and 452,
lib/server/entries.js:208 on dev 47723cda) may include the document that
failed to write; the branch does not cover them. Filed 2026-10-26 from a read-
only compatibility audit of dev 47723cda; the socket's counterpart of BF-186,
which #8845 fixed for API v3.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-193` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
