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

# Review packet — RT-COUNT-COMPAT

**Reads accept the count shapes oref0 and GluPredKit send; 15.0.9 stays a patch**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/count-client-compat` |
| base | `origin/dev@ddd9b600` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=RT-COUNT-COMPAT` is the measurement |
| semver | `patch` |

## What this changes

The v1 count rule from #8738 as amended by #8748 (lib/server/count.js,
lib/api/index.js validateCount), and the number 15.0.9 ships under.

## Why that semver

Decided 2026-09-24 - the shapes real clients send are read as 15.0.8 read
them, so no input a real client sends is narrowed (section 3.2's test); only
shapes no known client sends stay refused.

## What an operator would notice

> OpenAPS (oref0) and GluPredKit keep working with 15.0.9 as they did with
> 15.0.8. OpenAPS asks for its latest treatment with extra text after the
> number, and 15.0.9 reads the number, as 15.0.8 did. GluPredKit asks for
> "zero" records over a date range meaning "everything in the range", and
> gets everything in the range. Both answers carry a deprecation warning,
> because a future major release may refuse these shapes.

## Who should review this, and why

maintainer - a semver and compatibility decision, with a safety dimension on
the oref0 side

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The branch is local (not pushed), so no gate can read it from a remote.
  Evidence is the count suite (49/49) and the full suite in six cells (Node
  20 / 22 / 24 x mongo 4.4 / 7, 2466/0/3 each), with two break-it controls,
  and the consumer-replay lab's P1 and P2 re-run on the branch in both auth
  modes. Not yet run - a combined run with #8754 and #8758; a real OpenAPS
  rig or GluPredKit install (the lab replays their requests, not the
  programs).

## Evidence

- [`docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)

## Notes carried on the item

PREPARED 2026-09-24 - bf/count-client-compat b4ead206 on dev ddd9b600 (local,
not pushed): lib/server/count.js (leadingCount, hasDateWindow, NO_LIMIT_COUNT)
and lib/api/index.js (validateCount rewrites the two shapes on GET/HEAD before
checking). count=0 inside a two-sided date window becomes a limit of
2147483647, the largest 32-bit limit; outside one it is dropped so the
endpoint default applies (activity has no default, so it reads unbounded
there, as it already does with no count). Deletes are unchanged. Count suite
49/49; full suite 2466/0/3 on Node 20.20.0, 22.23.2 and 24.20.0 x mongo 4.4
and 7 (dev 2453 + 13). Break-it - tolerance off: 18 new tests fail; window
rule alone off: the 2 entries window tests fail (the other collections hold
fewer than their default). -6a's replay lab as slot d, readable and denied -
P1 oref0 200 in hashed and token modes, the cull keeps 1 of 57; P2 GluPredKit
1 / 137 / 576, equal to 15.0.8 and the count=100000 control. DECIDED
2026-09-24 (maintainer, -59) - tolerate the shapes real clients send and keep
15.0.9 a patch. oref0's "N?..." reads N (only digits followed by ?; abc, -3,
2.5, 1e2, 0x10 stay 400, with or without a ?). count=0 on a read was re-
decided the same day, after 15.0.8's code showed it had meant NO limit (a
truthy "0" reached .limit(0)) and the entries default of 10 would cut
GluPredKit's 576 to 10 without an error: no limit when the find bounds one
date field from both sides, the endpoint default otherwise. Both answered with
Deprecation: true and a 299 Warning, logged once per process, without the
value (oref0's contains its credential). 2026-09-23 - REPLAY VERDICTS (-6a
lab; docs/60-research/remedial/consumer-impact-15.0.9-2026-09-23.md). oref0:
15.0.8 200, dev and candidate 400 in both auth modes under readable and
denied; the plain count=1 control is 200 everywhere. Through oref0's own
jq/date pipeline the rig re-uploads 57 treatments per loop instead of 1. NO
DUPLICATES: 137 records after each of three posts, because the
created_at+eventType upsert is idempotent. A Nightscout-side edit to a rig
treatment from the last 24 h is overwritten on the next loop; that replace
also happens on 15.0.8, but only 15.0.9 makes the rig re-post every loop.
GluPredKit: count=0 returns [] for profile, treatments and entries on dev and
the candidate (15.0.8: 1 / 137 / 576 in a 50 h window); the count=100000
control is full on all three. Filed 2026-09-23 from the -6a consumer-impact
survey, on the maintainer instruction to document it as a compatibility and
semver item, not a backfix. oref0 (dev d219baf9, master 88cf032a) sends count
as "1?<credential>" from latest-openaps-treatment; 15.0.8 parseInt read 1,
15.0.9 answers 400. GluPredKit sends count=0 as "no limit"; 15.0.9 answers [].
Under the semver policy rule (section 3.2) both make the narrowing major as
written. Options, in outline - ship as a declared correction naming both
clients; tolerate the shapes real clients send and keep 15.0.9 a patch; or
number the release as a major. The release notes count section carries a
hidden OPEN BEFORE THE TAG note.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-COUNT-COMPAT` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `ddd9b600`.*
