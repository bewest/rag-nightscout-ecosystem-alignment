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

maintainer, and the security reviewers of #8754 (the maintainer and Andy),
together. This is the one irreversible change in the batch: the allow-list and
the admin-page fill-in were decided on 2026-09-23 (see notes) and are reviewed
as part of #8754.

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
- [`docs/30-design/remedial/rc-15.0.9-integration-record.md`](../../docs/30-design/remedial/rc-15.0.9-integration-record.md)

## Notes carried on the item

In review as part of #8754 (BF2-AUTH): the fix, 7103f657, is a commit on
bf2/auth-hardening and is in #8754's head e32f7a1c (2026-09-24). Nothing of
BFQ-47 is pushed separately. Destination 15.0.9 (backfix-2 plan section 1a,
2026-09-23). Not merged; BF-47 is live on 15.0.8. Decisions: - 2026-09-23
(maintainer): the subject-field allow-list is intended and stays (option 2),
with no compatibility flag. It is the declared schema for subjects (name,
roles, notes, created_at) and roles (name, permissions, notes, created_at);
fields outside it are not part of the contract. No open-source client in the
corpus depends on storing other subject fields. - 2026-09-23 (maintainer):
fold bf2/subject-edit-keeps-fields into the auth-hardening PR as its last
commit (recorded in the PR body at b248bb73). What remains is the admin-page
defect, which this fix addresses. Reproduced in a real browser, read back from
mongo: on dev an admin-page subject edit sets notes to "" and replaces
created_at with the edit time (the page fetches subjects without notes and
created_at, then saves the whole subject back); with the allow-list alone
notes survive but created_at is still replaced; the role editor keeps both on
every base (its GET serves whole documents), so the admin-page defect is
subjects only. The field loss already happens on the current release, not only
with the allow-list. The fix is a server-side fill-in in storage.js save() for
notes and created_at only: an absent notes key keeps the stored value, a
present one (even '') is written, so clearing still works. roles is
deliberately not filled in: the admin page sends no roles field when the last
role is removed, and filling it would silently keep access. Suite 2462/0/3 ->
2467/0/3. Evidence: the rc-c integration record, rc/15.0.9-additions-c
b9c9828b, 2508/0/3 on every Node and MongoDB pair; this unit's step added +5
and its three break-its are red.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-47` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
