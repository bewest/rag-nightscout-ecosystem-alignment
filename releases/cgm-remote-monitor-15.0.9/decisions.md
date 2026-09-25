# cgm-remote-monitor 15.0.9 — decisions

*Contributor-facing. Living record of the maintainer's decisions that shape 15.0.9, taken
2026-09-22 to 2026-09-25. Each row states the decision as it stands. Item state is in
`queue/work-queue.yaml`; what 15.0.9 contains and what is still open before the tag is in
[contents.md](contents.md); the test evidence is in the
[15.0.9 integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md).
BF-72 appears by mechanism only: it is live on the shipping release and this repository is public.*

## What 15.0.9 is

| decision | queue | as it stands |
|---|---|---|
| The `dev` → `master` release is numbered **15.0.9**, the number `dev`'s `package.json` carries (2026-09-22). Reads tolerate the `count` shapes oref0 and GluPredKit send, so 15.0.9 stays a patch (2026-09-24) | `RT-VERSION`, `RT-COUNT-COMPAT` | #8761 merged |
| **Backfix 2 ships inside 15.0.9**: `bf2/ops`, `bf2/backports` and `bf2/auth-hardening`, with the subject-edit fix folded into the last (2026-09-23) | `BF2-AUTH` | #8753, #8751, #8754 merged |
| **Records keep their own `_id` across v1, v3 and the websocket** (BF-99 to BF-102): `bf/object-id-consistency` goes in instead of the narrow profile-only fix, with D1–D4 below (2026-09-23) | `BFQ-102` | #8758 open |
| **BF-103 (split drag) goes in if its branch comes back clean**: red on `dev`, green on the branch, a green suite, every break-it red, clean merges with the other 15.0.9 PRs. Otherwise it ships as a known issue (2026-09-23) | `BFQ-103` | clean; #8760 merged |
| **Three outside contributors' PRs are carried into 15.0.9**: #8568 (BF-114), #8419 (tests) and #8530 (a 48-hour chart option) (2026-09-25) | `BFQ-114`, `RT-PR-8419`, `RT-PR-8530` | open |
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
| BF-09: measure first, then decide; the maintainer leans towards zero being a real value. The measurement must show the AAPS rapid-zero-temp display problem (`bec641ca`) does not return | `BFQ-09` |
| BF-41: the stale-data check ignores a future-dated reading and keeps the reading as sent; tolerance configurable, default 5 minutes. Snoozes run on the wall clock; an evaluator may take an "as of" time, but never for live alarms. BF-41 is closed as not reproducing | `BFQ-41`, `A7A-7` |
| BF-52: the age push is sent once, even when the exact check is missed | `BFQ-52` |
| Each cut is renumbered when it is rebased | `RT-VERSION` |
| The cuts are prepared now against the 15.0.9 candidate and ship after 15.0.9. **Open:** separate releases or one combined major | `RT-1` to `RT-5` |
