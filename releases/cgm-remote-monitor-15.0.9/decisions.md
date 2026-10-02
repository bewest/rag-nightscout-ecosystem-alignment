# cgm-remote-monitor 15.0.9 — decisions

*Contributor-facing. Living record of the maintainer's decisions that shape 15.0.9, taken
2026-09-22 to 2026-10-02, as of `dev` `ca6fcfaf` (2026-10-02). Each row states the decision as it stands. Item state is in
`queue/work-queue.yaml`; what 15.0.9 contains and what is still open before the tag is in
[contents.md](contents.md); the test evidence is in the
[15.0.9 integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md).
BF-72, BF-73, BF-139, BF-151 and BF-80 appear by mechanism only: all but BF-80 are live on the
shipping release, and this repository is public.*

## What 15.0.9 is

| decision | queue | as it stands |
|---|---|---|
| The `dev` → `master` release is numbered **15.0.9**, the number `dev`'s `package.json` carries (2026-09-22). Reads tolerate the `count` shapes oref0 and GluPredKit send, so 15.0.9 stays a patch (2026-09-24) | `RT-VERSION`, `RT-COUNT-COMPAT` | #8761 merged |
| **The release goes out through #8598** (`dev` → `master`, opened by AndyLow91) | `RT-0` | open, head `ca6fcfaf`, mergeable, `reviewDecision` `APPROVED`; both approvals (the maintainer, 2026-09-26 00:39Z) were given on `e3adc91d`, and re-approval at `ca6fcfaf` is owed; CI on `ca6fcfaf`: 27 checks passed, 3 skipped (2026-10-02) |
| **Backfix 2 ships inside 15.0.9**: `bf2/ops`, `bf2/backports` and `bf2/auth-hardening`, with the subject-edit fix folded into the last (2026-09-23) | `BF2-AUTH` | #8753, #8751, #8754 merged |
| **Records keep their own `_id` across v1, v3 and the websocket** (BF-99 to BF-102): `bf/object-id-consistency` goes in instead of the narrow profile-only fix, with D1–D4 below (2026-09-23) | `BFQ-102` | #8758 merged (`4d9ecc3b`) |
| **BF-103 (split drag) goes in if its branch comes back clean**: red on `dev`, green on the branch, a green suite, every break-it red, clean merges with the other 15.0.9 PRs. Otherwise it ships as a known issue (2026-09-23) | `BFQ-103` | clean; #8760 merged |
| **Outside contributors' PRs carried into 15.0.9**: #8568 (BF-114), #8419 (tests) and #8530 (a 48-hour chart option) (2026-09-25) | `BFQ-114`, `RT-PR-8419`, `RT-PR-8530` | all merged |
| **Crowdin #8730 is held out of 15.0.9**, because its sync reverts translations `dev` corrected (BF-132); a reconciled translations branch is an option (2026-09-25) | `RT-PR-8730` | open, not in 15.0.9 |
| **Five more fixes are in 15.0.9**: BF-118 (mmol/L alarm thresholds converted only when `BG_HIGH` is set), BF-119 (`PUMP_WARN_ON_SUSPEND` never warning), BF-120 (the clock view shows an old reading as current when its fetch fails), BF-126 (a subject without a name stops the server at boot) and BF-134 (each Loop remote command left an APNs connection open) (2026-09-25) | `BFQ-118`, `BFQ-119`, `BFQ-120`, `BFQ-126`, `BFQ-134` | #8766, #8767, #8768, #8769, #8770 merged |
| **Ten more fixes are in 15.0.9**: BF-106 (v1 activity and devicestatus numeric filters, a `dev`-only regression), BF-129 (an unknown entry id answers 500), BF-125 (IFTTT Maker event names translated), BF-123 (AAPS percentage Profile Switch), BF-122 with BF-135 (v1 writes missing from v3 history; AAPS deletes still counted), BF-136 (v3 writes to v1-born records refused), BF-128 with BF-138 and BF-139 (`/pebble` units), BF-80 (the `/alarm` failed-login delay, a `dev`-only regression) and BF-121 (two treatments at the same time stored as one); and #8778 from AndyLow91 (BF-140, a `dev`-only regression in v3 DELETE) (2026-09-26) | `BFQ-106`, `BFQ-129`, `BFQ-125`, `BFQ-123`, `BFQ-122`, `BFQ-136`, `BFQ-128`, `BFQ-80`, `BFQ-121` | #8771–#8780 merged (`ab9c96e6` … `ff93fa94`) |
| **BF-138 and BF-139 ship in 15.0.9, in #8777 with BF-128**; BF-139 is live on 15.0.8, so the public PR describes its mechanism and outcome with no reproduction recipe, as for BF-70 / #8743 (2026-09-26) | `BFQ-128` | #8777 merged |
| **Known issue of 15.0.9, by decision**: the BF-121 × BF-136 re-send duplicate (2026-09-26) | `BFQ-121`, `BFQ-136` | release notes, Known issues |
| **Not selected for 15.0.9, carried as known issues**: BF-124 (the treatment tooltip's BG units, display only) and BF-127 (a clock view opened from the menu is blank for a token viewer on a denied site). On 2026-09-25 the maintainer chose BF-123, BF-125 and BF-128 of the five triage items offered and did not select these two; no explicit decision beyond that is recorded | `BFQ-124`, `BFQ-127` | release notes, Known issues |
| **BF-141 is fixed in 15.0.9** (a v1 treatment re-sent with an empty identity stored twice, a `dev`-only regression from #8780). It shipped in #8781 from AndyLow91, with BF-143 (a re-send rewrote `srvCreated`) and BF-144 (v3 history could miss records written after a restart), both `dev`-only as well; `bf/fallback-key-empty-identifier` and #8782 were closed as superseded (2026-09-26) | `RT-PR-8781`, `BFQ-141` | #8781 merged (`ce7d754a`) |
| **BF-142 ships in 15.0.9 (#8783)**: v3 DELETE reaches records whose identifier is `0` or `false`; a record whose identifier is a list stays undeletable through v3, unlike 15.0.8, because v3 GET shows the list as its identifier. Listed in the release notes as a known difference (2026-09-26) | `BFQ-142` | #8783 merged (`699eb5fa`); release notes, Known issues |
| **BF-146 is fixed in 15.0.9 (#8784), and fixes BF-133 with it**: API v3 treatments enter the server's in-memory copy with `mills`, so a late or edited v3 treatment counts in the treatment-based IOB and COB and the treatments stay in time order ("fix as appropriate", 2026-09-26); extended the same day to device status, for consistency, so a late v3 device status is placed by time in the in-memory v1 read. Entries are left unchanged. The same code is on 15.0.8 | `BFQ-146`, `BFQ-133` | #8784 merged (`ce30a94d`) |
| **#8788 is in 15.0.9** (the Day to Day report draws an event with a duration on every day it covers; awss1i; BF-148, fixes #8223). The maintainer merged it on 2026-09-30 after its review; BF-149, found in that review, is after 15.0.9 and a known issue | `RT-PR-8788`, `BFQ-149` | merged 2026-09-30 as `3014f883` |
| **Real sites count as the 24 to 72 h real-time soak** (2026-09-30); the lab's 72 h soak is not run | `RT-SOAK` | done |
| **BF-108 is in 15.0.9** (a v1 filter listing several dates under the date field answered 500, so xDrip4iOS bulk deletes by timestamp removed nothing) (2026-10-01) | `BFQ-108` | #8791 merged (`50bc1084`) |
| **#8790 is in 15.0.9** (the Food Editor's food list and quick picks scroll by touch on phones; awss1i; BF-150, fixes #8192) (2026-10-01) | `RT-PR-8790` | #8790 merged (`73c9528b`) |
| **BF-151 and BF-73 are fixed for 15.0.9** (2026-10-01): an unbounded request to two little-used API addresses could stop the server responding for seconds, and is now refused (BF-151); error replies outside development mode no longer carry a stack trace or server paths (BF-73). Both are live on 15.0.8 and described by mechanism only | `BFQ-151`, `BFQ-73` | #8795 merged (`25fc41d9`), #8793 merged (`839a1565`) |
| **BF-155 is fixed for 15.0.9** (2026-10-02): a failed database read on `GET /api/v1/activity` or `/api/v1/profile/current` ended the server process, and is now answered with a 500 while the server keeps running. Live on 15.0.8 and described by mechanism only. The same read failure on `/api/v1/food` and `/api/v1/profile`, answered with `null` and a 200 without ending the process, is left for a later change | `BFQ-155` | #8796 merged (`ca6fcfaf`) |
| **BF-153's dependency refresh is taken in on its measured result** (`npm audit` 20 → 8, no highs, production bundle byte-identical); **`moment` stays at 2.30.1**, because no request input reaches `moment.locale` on `dev` and 2.31.0 changes parsing and locale display output (2026-10-01) | `BFQ-153` | #8794 merged (`a143d507`) |
| **BF-152 is after 15.0.9** (API v3 `settings` documents are admin-only through search and history but readable by identifier with read permission): AndroidAPS's follower app reads its settings by identifier, so which side is the intended contract is a question for the AndroidAPS developers (2026-10-01) | `BFQ-152` | open, not in 15.0.9 |
| **BF-145 after 15.0.9**: v3 PATCH and PUT by the id v3 GET shows miss a record stored with identifier `null`, `""` or `0` (PATCH 404, PUT stores a second copy); the same on 15.0.8 (2026-09-26) | `BFQ-145` | release notes, Known issues |
| **Version class of #8772, #8775 and #8780 deferred**: the queue classes #8775 and #8780 as minor and #8772's 500 → 200 is an open question; the maintainer is still collecting data before deciding whether they are recorded as minor-under-patch exceptions (as #8530) or re-classed (2026-09-26) | `BFQ-129`, `BFQ-122`, `BFQ-121` | undecided |
| **BF-09 after 15.0.9** (2026-10-02): the socket duplicate check's zero handling is fixed on #8797 (a zero is a value for `percent`, `absolute` and `duration`, and means none for `insulin` and `carbs`) and ships after 15.0.9. The path it fixes is AndroidAPS NSClient v1 (3.4.2.6; removed from AndroidAPS `master`), the standalone NSClient app and the chart's drag-to-move, and a record is lost only when two of the same type start within 2 s; no field report | `BFQ-09` | #8797 open |
| **After 15.0.9**: BF-137 (several IFTTT Maker keys), and making a v3 or websocket edit of a record stored twice merge the two copies (2026-09-26) | `BFQ-137`, `OID-V3-EDIT-MERGE`, `OID-WS-EDIT-MERGE` | not started |
| **nightscout-connect 0.1.0 is pinned in 15.0.9**, after the prerelease had a lab soak with a seeded source Nightscout syncing into a second one, and the maintainer's judgement (2026-09-22, amended 2026-09-23) | `P0-TAG`, `P0-PIN` | released 2026-09-24; #8762 merged |
| **No separate deprecation release.** The legacy-ingestion notice goes in 15.0.9's release notes (2026-09-23) | `RT-4` | release notes |
| **MongoDB 4.4 is deprecated in 15.0.9**, and dropped in a later release (2026-09-23) | `RT-MONGO-FLOOR` | #8750 merged |
| **The D3 chart migration ships with a manual and an automated browser check** of the treatment drag (2026-09-23) | `RT-D3` | answered 2026-09-24 |
| **The security reviewers for #8754 are the maintainer and Andy** (2026-09-23) | `P0-C` | #8754 merged |

## How specific behaviours are settled

| area | decision | queue |
|---|---|---|
| v1 `?count` | `?count=0` answers an empty list. Malformed counts (`abc`, `-3`, `2.5`, `1e2`, `0x10`, values above `Number.MAX_SAFE_INTEGER`) answer HTTP 400. Saves and updates ignore `count`. **A delete refuses** a count that is not a whole number of 1 or more, `0` included, and deletes nothing: `count` never limits a delete, and "delete zero" must not become "delete everything" | `RT-COUNT0` |
| v1 operator allowlist (#8743) | ships as merged, declared as a correction in the release notes | |
| client address and failed-login delay | one setting, `TRUST_PROXY`, under the compatibility-flag rule ([versioning policy §5.7](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md#57-compatibility-flags)). Unset keeps `dev`'s address resolution | `BF2-AUTH` |
| subject fields (BF-47) | the allow-list is the declared schema for subjects and roles, so it stays with no compatibility flag. The fix is the admin page, which cleared `notes` and `created_at` on every edit. The release notes declare the allow-list as a correction | `BFQ-47` |
| `_id` handling (#8758) | **D1**: devicestatus create gets the hex-`_id` check, so a re-send of a text-stored `_id` collides as on `dev` rather than adding a copy. **D2**: API v3 reaches v1 records with a non-hex `_id`, as `lib/api3/swagger.yaml` documents. **D3**: an entries POST that matches an existing reading answers with the stored `_id`. **D4**: an upper-case hex string stored on disk is found only when asked in upper case; documented, not changed | `BFQ-102` |
| v1 DELETE (BF-122) | **stays a hard delete** (option (a)). AAPS deletes are soft (`isValid: false`); with BF-135 they stop counting on the site and reach other AAPS instances through v3 history. A careportal, Loop, Trio or xDrip+ delete does not reach AAPS; the release notes tell people to delete in AAPS too (2026-09-26) | `BFQ-122` |
| same-time treatments (BF-121) | **option 3**: client identity (`syncIdentifier`, `id`, `uuid`, `NSCLIENT_ID`) must match on v1 and the websocket `dbAdd` exact match; carbs and insulin join the key only for v1 writes without identity; API v3 and the socket's no-identity key unchanged, so an AAPS edit re-sent after a lost reply still updates in place. Left as known issues: AAPS v3 same-millisecond `Meal Bolus` bolus and carbs; careportal same-minute same-amount entries. The BF-121 × BF-136 re-send duplicate is accepted as a known issue (2026-09-26) | `BFQ-121`, `BFQ-136` |
| AAPS Profile Switch (BF-123) | AAPS 3.x percentage and time shift applied as AAPS applies them; the CircadianPercentageProfile (AAPS 2.x) path is left as it is (2026-09-26) | `BFQ-123` |
| `/alarm` and the failed-login delay (BF-80) | a viewer presenting no credential is not held by the delay, at the connect-time admission and on `subscribe` (option 1 in the register); a credential is still checked only after the full delay, so on a denied site a signed-in viewer on a delayed address still waits (2026-09-26) | `BFQ-80`, `ADV-ALARM` |
| IFTTT Maker resend (BF-125) | a failed send is retried at every check, as since 2015; not changed (2026-09-26) | `BFQ-125` |
| Loop remote commands keep the previous profile's device (the journey lab's JL-2) | an ecosystem gap, not a Nightscout defect: `GAP-REMOTE-010` in [`traceability/treatments-gaps.md`](../../traceability/treatments-gaps.md#gap-remote-010-loop-remote-commands-keep-the-previous-profiles-device-after-a-new-profile-upload) (2026-09-26). The mechanism is known: profile writes signal the reload before the write completes, a window of at most about 60 s, the same on 15.0.8. The classification is **open to review** | — |
| Journey-lab findings JL-2 to JL-6 (all also on 15.0.8) | **listed as known issues in the release notes** (maintainer 2026-09-26); not filed in the backfix register; JL-2's classification stays open ([browser record](../../docs/60-research/remedial/journey-lab-browser-15.0.9-2026-09-26.md#findings-by-category)) | — |
| connector profile sync | each poll reads the newest profile and those saved since the last poll; no backfill on first sync; **the source wins**, so a profile edited on the receiving site is overwritten when the source's copy changes. The release notes say the third in plain words ([connector profile sync](../../docs/60-research/remedial/connector-profile-sync.md)) | `BFQ-97` |

## Security advisories

| decision | queue |
|---|---|
| The advisory write-ups and PR descriptions for #8743, #8744 and #8745 stay shortened until a release with the fixes ships and the advisories are published; the full text is at `ef376ecb` | `ADV-*` |
| BF-78 is documented and warned about at boot; no behaviour change | `ADV-CONFIG` |
| All four metadata corrections are applied to the draft advisories by a person running `advisories/apply-metadata.sh --apply`; the advisories stay drafts | `ADV-XSS-META` |
| BF-72's candidate remedies are measured privately and its disposition is held outside version control. Nothing about it goes into a PR, an issue or a tracked file beyond the mechanism in the register | `BFQ-72` |
| Only the dead links in the posted bodies of #8734–#8737 are fixed; #8739's file follows its live body; #8743–#8745 are not touched until release | `FU-PRBODIES` |

## Decided at the same time, outside 15.0.9's contents

| decision | queue |
|---|---|
| BF-09: a zero is a value for `percent`, `absolute` and `duration` and means none for `insulin` and `carbs` (2026-10-02, after the 2026-09-23 measurement); the harness shows every kept temp is drawn exactly, so the AAPS temp-basal display problem (`bec641ca`) does not return. Fixed on #8797, after 15.0.9 | `BFQ-09` |
| BF-41: the stale-data check ignores a future-dated reading and keeps the reading as sent; tolerance configurable, default 5 minutes. Snoozes run on the wall clock; an evaluator may take an "as of" time, but never for live alarms. BF-41 is closed as not reproducing | `BFQ-41`, `A7A-7` |
| BF-52: the age push is sent once, even when the exact check is missed | `BFQ-52` |
| Each cut is renumbered when it is rebased | `RT-VERSION` |
| The cuts are prepared now against the 15.0.9 candidate and ship after 15.0.9. **Open:** separate releases or one combined major | `RT-1` to `RT-5` |
