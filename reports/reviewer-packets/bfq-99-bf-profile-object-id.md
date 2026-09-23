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

# Review packet — BFQ-99

**bf/profile-object-id - a profile posted with its own _id is stored as an
ObjectId, and string-_id profiles can be edited and deleted**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/profile-object-id` |
| base | `origin/dev@1f9a9d10` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-99` is the measurement |
| semver | `patch` |
| register entries | `BF-99` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/server/profile.js create, save, remove and the find[_id] path, plus
tests/api.profiles.object-id.test.js (13 tests). One commit, 9b8cc2f9.

## Why that semver

Bug fix; no API or setting moves. Stored _id type changes from string to
ObjectId for new hex _ids, as treatments already do.

## What an operator would notice

> If your Nightscout copies data from another Nightscout, or you restored
> profiles from an export, editing one of those profiles on today's release
> (15.0.8) adds a second profile and keeps the old one, and deleting it does
> not remove the old one. With this fix an edit replaces the profile and a
> delete removes it, including profiles saved before you upgrade. Reports
> that show basal rates or insulin-on-board for past days read the profiles
> that were active then, so a leftover old copy can affect what they show.
> This is not medical advice; if a report looks wrong, check the profile
> against your care team's settings.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The new test file passes on the branch and fails 11 of 13 on dev 1f9a9d10
  and on 15.0.8; a queue gate running it against both trees does not exist
  yet.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-profile-object-id.md`](../../reports/phase0-pr-bodies/bf-profile-object-id.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/profile-object-id-2026-09-23.md`](../../docs/60-research/remedial/profile-object-id-2026-09-23.md)

## Notes carried on the item

PREPARED 2026-09-23 on the maintainer's instruction ("another backfix issue").
Merge-tree clean against every open 15.0.9 PR head and rc/15.0.9-additions-e
1b1977e0; the merged tree with 1b1977e0 passes the profile and count tests
112/0. Destination release not decided. Unblocks the connector's profile
update-on-change (BFQ-97). PR body draft reports/phase0-pr-bodies/bf-profile-
object-id.md. SUPERSEDED BY BFQ-102 (2026-09-23, maintainer): 15.0.9 takes
bf/object-id-consistency; this branch is not pushed. The queue has no
superseded state, so the state is left as measured. Conflicts in
lib/server/profile.js with bf/object-id-consistency (BFQ-102), which carries
the same fix on a shared helper; land one. modernization b1bdaca0 reproduces
it (11 of 13 red on Node 22.23.2 and 24.20.0).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-99` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
