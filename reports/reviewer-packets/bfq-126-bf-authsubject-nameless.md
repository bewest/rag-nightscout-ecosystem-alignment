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

# Review packet — BFQ-126

**BF-126 - an authorization subject without a name ends the server at every boot
(issue #7110)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/authsubject-nameless` |
| base | `origin/dev@ecb63223` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-126` is the measurement |
| semver | `patch` |
| register entries | `BF-126` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/authorization/storage.js create/save validation and reload(), plus a test
in tests/authsubjects.test.js. A subject or role without a string name is
refused instead of stored; an existing malformed row is skipped with a log
line instead of ending the process.

## Why that semver

a malformed admin write is refused with a 400 instead of stored; valid
requests are unchanged

## What an operator would notice

> If an administrator's tool creates a Nightscout access subject without a
> name, Nightscout stops, and keeps stopping every time it restarts, until
> that record is removed from the database by hand. Only someone with
> administrator rights can cause this. While Nightscout is down, nobody
> following you sees new readings and Nightscout raises no alarms, so keep
> your phone's and devices' own alarms on. The fix is not in any release
> yet.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -q 'NAME_REQUIRED' bf/authsubject-nameless -- lib/authorizat`** &nbsp;·&nbsp; kind: `static`

The branch's storage.js refuses a subject or role without a usable name
(NAME_REQUIRED; origin/dev has none and fails this). A presence check only;
the held probe and tests/authsubjects.test.js decide. Point it at origin/dev
once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by a probe held outside this repository (the
  defect is live on 15.0.8), which boots a cgm-remote-monitor tree against a
  disposable MongoDB and so is not a queue gate. 2026-09-25: exit 1 on
  v15.0.8 92d08342 and dev 4f705217 (process exits, reboot exits, removing
  the row restores it); the named-subject control keeps the server up. Exit
  0 on a scratch copy of dev with a guarded token prefix. The fix is done
  when the probe exits 0 on the candidate.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`a probe held outside this repository (the defect is live on 15.0.8)`](../../a probe held outside this repository (the defect is live on 15.0.8))

## Notes carried on the item

2026-09-25 - FIXED on bf/authsubject-nameless 1942920a (local, not pushed), on
dev ecb63223: create and save refuse a subject or role without a usable name
(400), and reload skips a stored one with a log line, so a site already in
this state boots. Roles had the same fault. 4 new tests (all fail on dev); the
held probe exits 0 on the branch, 1 on dev; full suite 2592/3/0 vs dev
2588/3/0, Node 22.23.2, MongoDB 7.0.43. Filed 2026-09-25 from the GitHub issue
triage (issue #7110, opened 2021-09-21). Admin-only, so not a security defect,
but live on 15.0.8 and persistent across restarts; the register text gives the
mechanism only. The probe file holds the request and is kept out of public
text until the maintainer decides.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-126` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
