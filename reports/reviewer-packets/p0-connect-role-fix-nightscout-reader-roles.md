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

# Review packet — P0-CONNECT-ROLE

**nightscout-connect's nightscout source creates its reader subject with role,
not roles (BF-89)**

| | |
|---|---|
| repository | `nightscout-connect` |
| branch | `fix/nightscout-reader-roles` |
| base | `official/dev@1946beb` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-CONNECT-ROLE` is the measurement |
| semver | `patch` |
| register entries | `BF-89` |

## What this changes

lib/sources/nightscout.js (the subject it POSTs to
/api/v2/authorization/subjects) and a test.

## Why that semver

a bug fix inside the 0.1.0 line before its full release

## What an operator would notice

> If you use nightscout-connect to copy data from one Nightscout site to
> another, it creates an access entry on the source site so that it can
> read. That entry is created without any permission, because the field name
> is misspelled. If the source site does not allow anonymous reading
> (AUTH_DEFAULT_ROLES=denied), copying has never worked - every attempt is
> refused - and on the default setting the mistake is invisible. The fix
> gives the entry read permission as intended. IMPORTANT: an entry already
> created by the old version is reused and stays without permission after
> upgrading. Either give it the "readable" role on the source site's admin
> page, or delete it so the connector recreates it correctly.

## Who should review this, and why

maintainer

## What was measured

**`sh -c 'git -C externals/nightscout-connect show official/dev:lib/sources/nightscout.js | grep -q "role: \[" &&`** &nbsp;·&nbsp; kind: `static`

FAILS while connector dev's nightscout source still sends the misspelled role
field. Red on 2026-09-23 (line 83).

**`sh -c 'git -C externals/nightscout-connect show fix/nightscout-reader-roles:lib/sources/nightscout.js | grep -`** &nbsp;·&nbsp; kind: `static`

The prepared branch sends roles, and no longer sends role.

**`cd externals/work/nc-roles-typo && n exec 22.23.2 node --test test/nightscout-source.test.js`** &nbsp;·&nbsp; kind: `unit`

6 cases. Control, re-run by the coordinator 2026-09-23 - with dev's
lib/sources/nightscout.js the new case fails (actual undefined, expected
['readable']) and the other 5 pass.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

OPENED 2026-09-23 as nightscout/nightscout-connect PR #77 (head dea2bec, base
dev) by the maintainer. The red gate reads official/dev and turns green when
it merges. The one red gate reads official/dev and goes green only when the
fix merges there; both branch gates pass, and the next step is a human push.
PREPARED 2026-09-23 - fix/nightscout-reader-roles dea2bec on official/dev
1946beb, one commit. Measured end to end against Nightscout dev 74fc6619:
under denied the created subject gets no permissions and every poll is 401
with 0 entries copied; with the fix, reads succeed and the entry arrives.
Invisible on readable. Connector suite 290/290 on Node 20, 22 and 24 (dev
289/289). An existing subject is reused by name, so the release notes must
carry the repair step. PR body draft at reports/connector-pr-
bodies/nightscout-reader-roles.md. DECIDED 2026-09-23 (maintainer) - fix in
connector dev before the full 0.1.0 release (P0-TAG). Found while checking
BF-47: Nightscout's subject allow-list stores roles, so this subject is stored
with no roles at all.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-CONNECT-ROLE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
