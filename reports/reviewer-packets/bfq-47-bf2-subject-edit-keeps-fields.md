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

# Review packet — BFQ-47

**BF-47 - an ordinary subject edit destroys stored fields, on today's release**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf2/subject-edit-keeps-fields` |
| base | `bf2/auth-hardening@29e6430e` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-47` is the measurement |
| semver | `major` |
| register entries | `BF-47` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/authorization/endpoints.js:40 pick(), lib/admin_plugins/subjects.js PUT,
lib/authorization/storage.js save() replaceOne with upsert. The same three
files P0-C already touches.

## Why that semver

The repair on bf/auth narrows the loss rather than introducing it, but it also
introduces an allow-list, so a third-party tool can no longer preserve its own
fields by sending them in its own PUT - which it can do today, because save()
writes the caller's object as given. That is a capability removal on an HTTP
surface.

## What an operator would notice

> Editing a person or device entry (a "subject") through Nightscout's admin
> page already throws away fields that are not shown on that page - notes,
> the date it was created, and anything a third-party tool has stored there.
> It happens silently, there is no error, and it cannot be recovered by
> going back to an older version of Nightscout. This is how today's release
> (15.0.8) behaves.

## Who should review this, and why

maintainer, AND the security reviewer who takes P0-C, together - this is the
one irreversible change in the Phase 0 batch and the question has to be
answered BEFORE merge, not after

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 29e6430e bf2/subject-edit-keeps-fields`** &nbsp;·&nbsp; kind: `static`

Built on bf2/auth-hardening, whose allow-list is the declared schema.

**`cd externals/work/crm-bf47 && TEST=authsubjects npm run test-single`** &nbsp;·&nbsp; kind: `integration`

13 cases, 5 of them new - an admin-page form edit, removing every role, a PUT
omitting notes and created_at, a PUT clearing notes, and the role variants.
Control, re-run by the coordinator 2026-09-23 - with 29e6430e's storage.js the
5 new cases fail and 8 pass.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The admin-page path in a real browser is shown by
  tools/review/probes/subject-edit-keeps-fields-browser.js (passes --expect
  base on 29e6430e, --expect fixed on the branch); a browser run is not a
  queue gate.

## Blocked on

`P0-C`

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf2-subject-edit-keeps-fields.md`](../../reports/phase0-pr-bodies/bf2-subject-edit-keeps-fields.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md`](../../docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md)

## Notes carried on the item

2026-09-23 - the fix, 7103f657, is the last-but-two commit on bf2/auth-
hardening and so is in review as #8754 (head 0ca46d92). Nothing of BFQ-47 is
pushed separately. DESTINATION 15.0.9 (plan section 1a, "backfix 2 scope",
2026-09-23). Evidence - the rc-c integration record, rc/15.0.9-additions-c
b9c9828b, 2508/0/3 on every Node and MongoDB pair; this unit's step added +5
and its three break-its are red. The record recommends folding this branch
into the auth-hardening PR as its last commit; the auth-hardening PR body at
b248bb73 records that as the maintainer's 2026-09-23 decision (see BF2-AUTH).
PREPARED 2026-09-23 - bf2/subject-edit-keeps-fields 7103f657, one commit on
bf2/auth-hardening. REPRODUCED in a real browser, read back from mongo - on
dev an admin-page subject edit sets notes to "" and replaces created_at with
the edit time; on bf2/auth-hardening notes survive but created_at is still
replaced; the role editor keeps both on every base (its GET serves whole
documents), so the admin-page defect is subjects only. Fix is a server-side
fill-in in storage.js save() for notes and created_at only - an absent notes
key keeps the stored value, a present one (even '') is written, so clearing
still works. roles is deliberately NOT filled in - the admin page sends no
roles field when the last role is removed, and filling it would silently keep
access. Suite 2462/0/3 -> 2467/0/3. DECIDED 2026-09-23 (maintainer) - NO
compatibility flag for the subject-field allow-list. The allow-list IS the
declared schema for subjects (name, roles, notes, created_at) and roles (name,
permissions, notes, created_at); fields outside it are not part of the
contract. What remains is the admin-page defect - an edit through the admin
page must keep notes and created_at. DECIDED 2026-09-23 (maintainer) - the
allow-list is intended and stays (option 2). No open-source client in the
corpus depends on storing other subject fields. The loss that remains is the
admin page: it fetches subjects without notes and created_at, then saves the
whole subject back, so an ordinary edit clears both. That is the defect to
fix. A verifier's review of bf/auth established that the field loss already
happens on the current release, not only on the unmerged branch. Keeping the
security goal of BF-17 - the derived token never reaches the database - does
not require the allow-list.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-47` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `4011193e`.*
