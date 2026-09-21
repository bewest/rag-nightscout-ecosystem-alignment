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

> If you have ever edited a subject through the admin page, a readable copy
> of that subject's API access token is sitting in your database. Upgrading
> does not remove it - it clears for a subject only when you next save that
> subject through the admin page, and clearing the copy does not retire the
> token. There are exactly TWO ways to retire an exposed token: delete and
> recreate the subject, or change API_SECRET. RENAMING THE SUBJECT IS NOT
> ONE OF THEM, even though the token's appearance changes. Anyone who has
> had read access to your database since the first edit could have used that
> token.

## Who should review this, and why

maintainer, plus the security reviewer who takes P0-C

## What was measured

**`node tools/queue/gates/bf17-remediation-note.js`** &nbsp;·&nbsp; kind: `static`

17 checks. The deliverable here is PROSE, and prose was exactly what went
wrong: the 15.0.9 release notes listed "rename the user" as one of three ways
to change an exposed token, and so did report 2.3, which they were written
from. A rename is cosmetic - checkToken keeps the LAST dash-segment of the
presented token and matches it against subject.digest, which is
getSubjectHash(subject._id); the name reaches only the abbrev at the front,
which is never read back. An operator who renamed and stopped would believe a
leaked credential was retired while it still authenticated. The gate pins the
CODE property on origin/dev AND the bf/auth worktree, so the prose cannot
drift from it in either direction, then checks each of the four documents for
what must be said and for the retracted sentences. NON-VACUITY, reproduced
2026-09-16 before the gate was committed: restoring the rename row to the
release notes -> 1 failing; restoring the PR body's "discarded when Nightscout
next loads it" -> 2 failing; restoring the rename option to report 2.3 -> 1
failing; empty QUEUE_GATE_ROOT -> 17 failing.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- NO DETECTOR SCRIPT, BY DECISION (maintainer, 2026-09-16). The earlier
  marker here asked for a script reporting how many subject rows carry a
  non-derived accessToken. It was not written and will not be. The
  reasoning, recorded so it is not rediscovered as a gap: a count is not
  remediation - remediation is rotation, and rotation is an operator
  decision no script can take. The per-operator form of the same question is
  one query, and it is already written out in the PR body ("look in your
  auth_subjects collection for any document with an accessToken,
  accessTokenDigest or digest field"). A fleet-wide count has no consumer.
  THE RESIDUAL THIS LEAVES, STATED PLAINLY: an operator who never re-saves a
  previously-edited subject keeps a plaintext row indefinitely and nothing
  prompts them. The release notes now say so in as many words.
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

SETTLED 2026-09-16. This item was not-started for as long as it existed, on
the strength of one sentence in the register's BF-17 row - "existing rows
still hold tokens, see the report" - which nothing acted on. It is now closed
as TEXT rather than tooling: the maintainer decided against a detector script
and against a migration, on the ground that the notes carry the operator's
actual decision and a script does not. WHAT THE REVIEW TURNED UP WHILE CLOSING
IT, and the reason the item was not simply deleted: the notes were WRONG. Two
operator documents told people that renaming a subject retires its token. It
does not - measured at lib/authorization/storage.js:326 on bf/auth and :288 on
origin/dev, the matcher is name-independent - and a third document, the report
those notes were written from, is where the error came from. A fourth claim,
that the upgrade discards the stored copy on load, was also wrong: reload()
deletes the derived fields from the IN-MEMORY record only, and the row clears
when the subject is next saved through the admin path. All four are corrected
and the gate above is the regression guard. THE LESSON IS THE ITEM'S REAL
OUTPUT: "the deliverable is a note" is not a reason to leave it ungated. The
note was the defect.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-C-REMEDIATE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `74fc6619`.*
