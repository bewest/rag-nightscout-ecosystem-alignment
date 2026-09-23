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

# Review packet — BFQ-98

**BF-98 - the connector reuses a reader subject without roles, so the BF-89 fix
does not repair it**

| | |
|---|---|
| repository | `nightscout-connect` |
| branch | `fix/profile-duplicate-stall` |
| base | `official/dev@fbd4e55` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-98` is the measurement |
| semver | `patch` |
| register entries | `BF-98` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Connector lib/sources/nightscout.js reader-subject lookup (v0.0.13 lines
75-77), which takes the accessToken of any subject named nightscout-connect-
reader without checking its roles.

## Why that semver

Adds one log message; no setting or API moves.

## What an operator would notice

> If your Nightscout copies data from another Nightscout site that requires
> sign-in (AUTH_DEFAULT_ROLES=denied), and it has never managed to read from
> it, an access entry named nightscout-connect-reader on the other site was
> probably created without a role. Upgrading the connector does not fix that
> entry. On the other site's admin page, either give nightscout-connect-
> reader the readable role or delete it so the connector creates it again.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Reproduced by the lab soak's control (c), not a queue gate. The warning
  commit is to carry tests for both triggers and for logging once.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`docs/60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md`](../../docs/60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md)

## Notes carried on the item

PREPARED 2026-09-23 - f924de2 on fix/profile-duplicate-stall (not pushed): one
warning per process when the reused nightscout-connect-reader has no roles, or
when a read returns 401, naming the subject and both fixes; no writes to the
source; no token, secret or URL in the message. Exact wording in the evidence
doc for the release notes. DECIDED 2026-09-23 (maintainer) - warn clearly,
don't repair: one plain log message naming the subject and both fixes, no
writes to the source; the release notes carry the same steps. Being built as a
second commit on fix/profile-duplicate-stall (not pushed).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-98` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
