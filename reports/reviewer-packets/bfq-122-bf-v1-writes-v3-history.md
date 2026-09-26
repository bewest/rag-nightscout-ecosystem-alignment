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

# Review packet — BFQ-122

**BF-122 - records written, changed or deleted through API v1 never appear in
API v3 history (issue #8244); BF-135 - a record AndroidAPS deletes keeps
counting**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/v1-writes-v3-history` |
| base | `origin/dev@e3adc91d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-122` is the measurement |
| semver | `minor` |
| register entries | `BF-122`, `BF-135` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Three commits at dbc4c5fc (718efddc the fix, then two test commits, d45987f7
and dbc4c5fc). lib/server/srv-dates.js (new) and the v1 storage writes in
treatments.js, entries.js, devicestatus.js, profile.js and food.js (create,
upsert, save); lib/server/websocket.js dbAdd, dbUpdate and dbUpdateUnset; the
v3 handlers take srvModified from the same clock. v1 DELETE and websocket
dbRemove are unchanged (hard delete, decided 2026-09-26). Existing records are
not backfilled. Every v1 uploader's records gain srvModified and srvCreated
fields. For BF-135, lib/server/soft-deleted.js (new), used by the v1 storage
reads, the cache and the websocket dbAdd dedup, so records with isValid false
stop counting outside API v3.

## Why that semver

v1-written records gain srvModified/srvCreated and v3 history returns more
records

## What an operator would notice

> Some apps, including AndroidAPS, keep up to date with Nightscout by asking
> it only for what changed since they last asked. Nightscout does not
> include anything that was added, changed or deleted through its older
> interface (API v1). That older interface is used by the Nightscout
> careportal and bolus wizard, Loop, Trio, xDrip+, xdripswift, OpenAPS and
> the built-in Nightscout Connect data source. So after its first sync,
> AndroidAPS may not receive carbs or insulin you enter in the Nightscout
> careportal, glucose readings uploaded by xDrip+ or Nightscout Connect when
> Nightscout is its glucose source, or an edit or deletion made elsewhere.
> Nothing tells you this has happened. Check that entries made elsewhere
> show up in AndroidAPS. AndroidAPS's full sync option reloads them.
> Separately, a carb or insulin entry you delete in AndroidAPS keeps
> counting in the carbs and insulin on board (COB and IOB) that Nightscout
> shows, because Nightscout keeps using deleted records. A fix for both is
> ready for review for 15.0.9 and is not in any release yet. With the fix,
> new entries and edits made through the older interface reach AndroidAPS,
> and entries deleted in AndroidAPS stop counting on your site. One thing
> stays as it is, by decision: an entry deleted in the Nightscout
> careportal, Loop, Trio or xDrip+ is still not removed from AndroidAPS, so
> delete it in AndroidAPS as well. A looping AndroidAPS phone only takes
> carbs and insulin from Nightscout if "accept carbs" and "accept insulin"
> are switched on in its NSClient settings; both are off unless you turned
> them on. The AAPSClient follower app always takes them. If you enter the
> same meal in both the careportal and AndroidAPS, AndroidAPS may show it
> twice after the fix. This is not medical advice; talk to your care team
> before relying on entries made in one app reaching another.

## Who should review this, and why

maintainer, plus someone who runs AndroidAPS with NSClientV3

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official grep -q srvModified bf/v1-writes-v3-history -- lib/server/`** &nbsp;·&nbsp; kind: `static`

The branch's v1 storage modules stamp srvModified through lib/server/srv-
dates.js (origin/dev has neither and fails this). A presence check; the probe
and tests/api3.v1-writes-history.test.js decide. Point it at origin/dev once
merged. (The origin/dev form of this check was dropped on 2026-09-26, when the
item became ready-to-push: it could only go green by merging.)

**`sh -c 'git -C externals/cgm-remote-monitor-official cat-file -e bf/v1-writes-v3-history:lib/server/soft-delete`** &nbsp;·&nbsp; kind: `static`

BF-135: the branch has lib/server/soft-deleted.js and the cache and treatments
reads use it (origin/dev has no such module and fails this). A presence check;
tests/soft-deleted.jl1.test.js decides (COB 40 g to none after an AAPS v3
delete and after an AAPS v1 socket dbUpdate isValid false).

**`git -C externals/cgm-remote-monitor-official grep -qF "a v1 DELETE still removes the record" bf/v1-writes-v3-h`** &nbsp;·&nbsp; kind: `static`

The maintainer's v1 DELETE decision (2026-09-26, keep hard delete) is pinned
by a test on the branch: "a v1 DELETE still removes the record, and history
does not report it". origin/dev has no such test file and fails this. A
presence check; the test itself decides. Since dbc4c5fc the test's name and
comment record the decision (hard delete kept).

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by
  tools/lab/triage-2026-09/v1-writes-v3-history.js, which boots a server and
  needs MongoDB, so it is not a queue gate. 2026-09-25: exit 1 on v15.0.8
  92d08342, dev 4f705217 and #8758 ab7b22d6 (5 v1 arms absent from history;
  5 controls present). 2026-09-25 on the branch 718efddc: the treatments,
  entries and devicestatus v1 arms and the v1 PUT arm are present; exit 1
  only on the v1 DELETE arm. Since the 2026-09-26 decision that arm measures
  the decided behaviour (a v1 hard delete is not in history), not a pending
  defect, so the expected result on the candidate is exit 1 with every other
  arm present; exit 1 on any other arm is a regression. 2026-09-26 in the
  combined run lab/round1-combined bda225e4: exit 1 on the v1 DELETE arm
  only.
- The AndroidAPS side (LoadTreatmentsRunner.kt, LoadBgRunner.kt) is read,
  not run. A run of AndroidAPS NSClientV3 against a site with a careportal
  entry made after its first load is the missing confirmation.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/v1-writes-v3-history.js`](../../tools/lab/triage-2026-09/v1-writes-v3-history.js)

## Notes carried on the item

Filed 2026-09-25 from the GitHub triage (issue #8244, opened 2024-03-24 as a
feature request by someone copying xDrip+ entries through v3 history). The
consumer survey reports/consumer-impact-15.0.9/clients/android/androidaps.md
S13 records AAPS's history paging but not this gap. 2026-09-25 - PARTLY FIXED
(creates and updates) on bf/v1-writes-v3-history 718efddc (local, not pushed),
one commit on dev e3adc91d: srvModified on every v1, websocket and in-process
write (srvCreated on insert) for every v3-served collection; v1 PUT and
replaceOne keep identifier and srvCreated; one monotonic server clock for all
writers, v3 included. 26 new tests (20 fail on e3adc91d with the original
symptom), 24 break-its, suite 3196/0/3 (Node 22.23.2, MongoDB 7.0.43). Three
existing expectations adjusted (tests/api3.create.test.js two dedup tests,
tests/websocket.input-validation.test.js selectors, tests/storage.selector-
hardening.test.js harness). NEEDS DECISION: v1 DELETE design - (a) keep hard,
(b) all soft, (c) single-record soft, (d) hard plus a minimal tombstone.
Release note: careportal and caregiver carbs now reach AAPS; the same meal
entered in both places may duplicate on the phone. Found, not filed: v3
history can skip a write whose commit lands after a later-stamped write was
read (stamp before commit, a millisecond window, v3 too); after 15.0.9. BF-135
(JL-1, found by the journey lab) is fixed by the same commit: isValid false
counts as deleted everywhere except v3 search and history; COB 40 g to none on
both AAPS delete paths. Maintainer decision 2026-09-25: BF-135 goes into
15.0.9 with BF-122 on this branch. 2026-09-26 - Branch head d45987f7: one test
commit on 718efddc, only tests/soft-deleted.jl1.test.js (a v1 profile search
by date leaves out a deleted profile with the same date, and returns it for
find[isValid]=false). 30 new tests across the two files; suite 3200/0/3 (Node
22.23.2, MongoDB 7.0.43). Still merges cleanly with bf/activity-date-coercion.
2026-09-26 - Combined run: all six round-1 branches (bf/activity-date-coercion
20c197bb, bf/entries-unknown-id f79dc732, bf/maker-level-names 2f50ada9,
bf/profile-switch-percentage 5a895b49, bf/pebble-delta-units aa224c69,
bf/v1-writes-v3-history 718efddc) merged on dev e3adc91d as local
lab/round1-combined bda225e4 (worktree externals/work/crm-round1-combined):
full suite 3292 passing / 0 failing / 3 pending (= 3170 + 122 new tests), Node
22.23.2, MongoDB 7.0.43. All five probes gave their expected exit codes: bf106
gate 0, maker-language 0, profile-switch-percentage 0, pebble-units 0,
v1-writes-v3-history 1 on the v1 DELETE arm only (kept by decision, BFQ-122).
The run carried 718efddc, not the later test commit d45987f7. 2026-09-26 -
Branch head dbc4c5fc: renames the pinned v1 DELETE test and its comment to
record the decision; no other change, so the 3200/0/3 on d45987f7 stands.
BFQ-121's branch conflicts textually with this one and waits for it to merge
first. Decisions: - 2026-09-25 (maintainer): BF-135 into 15.0.9 with BF-122,
on this branch. - 2026-09-26 (maintainer): v1 DELETE, option (a), keep hard
delete. Reason given: people are likely to use AndroidAPS as the controller,
not the careportal; AAPS deletes are soft (isValid false), and with BF-135
they stop counting on the site and reach other AAPS instances through v3
history. Deletes made in the careportal, Loop, Trio or xDrip+ still do not
reach AndroidAPS. "Make sure documentation is accurate." AAPS applies carbs
and insulin from Nightscout, and their deletions, only when NSClient "accept
carbs" / "accept insulin" (ns_receive_carbs, ns_receive_insulin) are on; both
default off (AndroidAPS 7e1d537d49 core/keys BooleanKey.kt:224-225); the
AAPSClient build always accepts them and hides the settings
(showInNsClientMode = false; NsIncomingDataProcessor.kt:163-167,
StoreDataForDbImpl.kt:420-426; read). BFQ-122 moves from needs-decision to
ready-to-push. Known-issue wording for the 15.0.9 release notes, for the
release pass and only once this branch is merged: "An entry you delete in the
Nightscout careportal, Loop, Trio or xDrip+ is not removed from AndroidAPS.
Delete it in AndroidAPS as well. A looping AndroidAPS phone takes carbs and
insulin from Nightscout only if you switched on 'accept carbs' and 'accept
insulin' in its NSClient settings." The release files list only what is on
dev, so the line is not in them yet.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-122` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
