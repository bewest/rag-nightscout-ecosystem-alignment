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

# Review packet — P0-C-REMEDIATE

**Operator remediation for tokens already stored in plaintext - text, not
tooling**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/dev@a8888f0d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=P0-C-REMEDIATE` is the measurement |
| semver | `n/a` |
| register entries | `BF-17` |

## What this changes

Operator-facing text only, in three documents this repo owns - releases/cgm-
remote-monitor-15.0.9/release-notes.md, reports/phase0-pr-bodies/bf-auth.md
and the report they are written from. No shipping code path, no script, no
migration.

## Why that semver

not a code change to the shipped surface

## What an operator would notice

> If you have ever edited a subject (an access entry on your Nightscout
> admin page), a readable copy of that subject's API access token is sitting
> in your database. Upgrading will not remove it - it clears for a subject
> only when you next save that subject through the admin page, and clearing
> the copy does not retire the token. There are exactly TWO ways to retire
> an exposed token: delete and recreate the subject, or change API_SECRET
> (your site's main admin password). RENAMING THE SUBJECT IS NOT ONE OF
> THEM, even though the token's appearance changes. Anyone who has had read
> access to your database since the first edit could have used that token.

## Who should review this, and why

maintainer, plus the security reviewer who takes P0-C

## What was measured

**`node tools/queue/gates/bf17-remediation-note.js`** &nbsp;·&nbsp; kind: `static`

17 checks. The deliverable is prose, and the prose has to match the code: a
rename is cosmetic - checkToken keeps the LAST dash-segment of the presented
token and matches it against subject.digest, which is
getSubjectHash(subject._id); the name reaches only the abbrev at the front,
which is never read back. An operator who renamed and stopped would believe a
leaked credential was retired while it still authenticated. The gate pins the
CODE property on origin/dev AND the bf/auth worktree, so the prose cannot
drift from it in either direction, then checks each of the four documents for
what must be said and for sentences known to be wrong (rename as a rotation;
the stored copy discarded on load). Non-vacuity, reproduced 2026-09-16:
restoring the rename row to the release notes -> 1 failing; restoring the PR
body's "discarded when Nightscout next loads it" -> 2 failing; restoring the
rename option to report 2.3 -> 1 failing; empty QUEUE_GATE_ROOT -> 17 failing.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- No detector script, by decision (maintainer, 2026-09-16). A count is not
  remediation - remediation is rotation, and rotation is an operator
  decision no script can take. The per-operator form of the question is
  already written out in the PR body ("look in your auth_subjects collection
  for any document with an accessToken, accessTokenDigest or digest field").
  A fleet-wide count has no consumer. THE RESIDUAL THIS LEAVES: an operator
  who never re-saves a previously-edited subject keeps a plaintext row
  indefinitely and nothing prompts them. The release notes say so.
- NOTHING MEASURES WHETHER AN OPERATOR ACTS. This item ships words. No gate
  in this repository can show that a single exposed token was rotated, and
  none should claim to.

## Blocked on

`P0-C`

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/bf17-bf30-auth-defects-2026-09-15.md`](../../docs/60-research/remedial/bf17-bf30-auth-defects-2026-09-15.md)
- [`releases/cgm-remote-monitor-15.0.9/release-notes.md`](../../releases/cgm-remote-monitor-15.0.9/release-notes.md)
- [`reports/phase0-pr-bodies/bf-auth.md`](../../reports/phase0-pr-bodies/bf-auth.md)

## Notes carried on the item

Settled 2026-09-16 as TEXT rather than tooling: the maintainer decided against
a detector script and against a migration, on the ground that the notes carry
the operator's actual decision and a script does not. The two facts the text
must get right, both measured: renaming a subject does not retire its token
(the matcher is name-independent - lib/authorization/storage.js:326 on
bf/auth, :288 on origin/dev); and upgrading does not discard the stored copy
(reload() deletes the derived fields from the IN-MEMORY record only; the row
clears when the subject is next saved through the admin path). The release
notes, the PR body and the source report state both correctly, and the gate
above guards them.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-C-REMEDIATE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `ddd9b600`.*
