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

# Review packet — BFQ-110

**BF-110 - on #8758, deleting a record by its hex id also deletes its twin, and
the PR's advice leads users there**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/object-id-crud` |
| base | `origin/dev@1f9a9d10` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-110` is the measurement |
| semver | `patch` |
| register entries | `BF-110` |

## What this changes

lib/server/object-id-forms.js matchEitherForm through query.js, treatments.js
remove and websocket.js dbRemove; the plain-language copy in the #8758 body
and the 15.0.9 release notes.

## Why that semver

a defect in an unmerged fix, and release-note wording

## What an operator would notice

> Only on the change that is not released yet (#8758). If you edited a
> treatment on 15.0.8 or earlier and it was saved twice, deleting the old
> copy after upgrading would also delete the copy with your edit. Edit the
> record instead: that merges the two into one. If you are unsure which
> treatments are correct, check with your care team.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by tools/lab/object-id (probe P-ID-7). On 6d120fa2 the v1 DELETE
  /treatments/<hex> and the websocket dbRemove of a twin leave n=0 where
  v15.0.8 and dev ddd9b600 leave n=1; find[_id] returns 2 where they return
  1. The v3 permanent DELETE leaves 1 on all three. No queue gate wraps the
  lab yet (OID-LAB).
- Decided 2026-09-24 (maintainer): deleting a record by its hex id removes
  both copies of a twin. That is what #8758's body already says ("Deleting
  such a record now removes it, including a copy left by an earlier edit"),
  so no code changes. What is left is one line of the body's advice, "If you
  see an old copy beside the one you edited, you can now delete it", which
  deletes the edited copy too. Proposed: "If you see an old copy beside the
  one you edited, edit either one: the two become one record with that edit.
  Deleting either one deletes both." The next step is a human edit of the PR
  body and of the 15.0.9 release notes. Both are prepared 2026-09-24:
  reports/phase0-pr-bodies/pr-8758-body.md (upload with gh pr edit) and the
  #8758 section of releases/cgm-remote-monitor-15.0.9/release-notes.md.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-object-id-crud.md`](../../reports/phase0-pr-bodies/bf-object-id-crud.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/object-id/results/object-id-2026-09-24.md`](../../tools/lab/object-id/results/object-id-2026-09-24.md)

## Notes carried on the item

Decided 2026-09-24: behaviour kept (option b). Before the decision it read:
(a) when both forms are stored, a delete by the hex removes only the string
form, or (b) keep the behaviour and change the PR body and the release notes
from "you can now delete it" to "edit the record; do not delete the old copy".
Either way the release-note line "Nothing in your database changes until a
record is edited or deleted" is also wrong for new records, which #8758 stores
as ObjectId (P-ID-4, P-ID-5, P-ID-6); that wording belongs to BFQ-102. Size
depends on how many twins exist (OID-PREVALENCE).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-110` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
