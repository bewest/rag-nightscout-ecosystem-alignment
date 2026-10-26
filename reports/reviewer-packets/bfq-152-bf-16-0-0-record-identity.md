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

# Review packet — BFQ-152 (PR #8845)

**BF-152 - API v3 settings are admin-only through search and history, readable
by identifier with read permission**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-record-identity` |
| base | `official/dev@b29f1bf7` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-152` is the measurement |
| semver | `minor` |
| register entries | `BF-152` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Step 1 (faffe875 in PR #8845, cherry-picked from 06ba6201; pending push): an
opt-in setting API3_SETTINGS_STRICT_READ_ENABLED, default off, that makes API
v3 read by identifier of settings demand api:settings:admin, as search and
history do. Default behaviour unchanged.

## Why that semver

a new opt-in setting, default off; a strict default later would be a separate,
breaking step on the calendar

## What an operator would notice

> Nothing changes unless you turn it on. A new optional setting,
> API3_SETTINGS_STRICT_READ_ENABLED, lets you require full (admin) access
> before an app can read a saved app-settings document from Nightscout. If
> you turn it on, an AndroidAPS 4.0 follower that uses a read-only token can
> no longer load its settings from Nightscout; a token made by the
> AndroidAPS master phone already has the access it needs.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official cat-file -e faffe875^{commit}`** &nbsp;·&nbsp; kind: `static`

step 1's commit (cherry-pick faffe875 on bf/16.0.0-record-identity, PR #8845)
exists in the shared clone; red if it is lost before it is pushed (a rebase
changes the id, and this gate must then name the new one)

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A decision item. Reproduced 2026-10-01 on v15.0.8 and dev 3014f883: search
  and history 403, read by identifier 200, readable and denied. AndroidAPS's
  AAPSClient reads its running configuration by identifier (plugins/sync
  nsclientV3 LoadSettingsRunner).

## Evidence

- [`docs/60-research/remedial/aaps-websocket-delivery-lab-2026-10-25.md`](../../docs/60-research/remedial/aaps-websocket-delivery-lab-2026-10-25.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-25, later: folded into PR #8845 to dev (bf/16.0.0-record-identity) as
cherry-pick faffe875 of 06ba6201, pending push; the branch
bf/16.0.0-v3-settings-read-scope will not be pushed. The setting name
API3_SETTINGS_STRICT_READ_ENABLED is confirmed. 2026-10-25, later: head
06ba6201 confirmed; the setting name API3_SETTINGS_STRICT_READ_ENABLED is
confirmed by the maintainer. Write-up of the AndroidAPS findings:
docs/60-research/remedial/aaps-websocket-delivery-lab-2026-10-25.md section 3.
2026-10-25 (maintainer decision): a staged ladder. (1) an opt-in, admin-only
settings read in 16.x; (2) ask the AndroidAPS developers about a narrower
scope; (3) a strict default later on the calendar. Step 1 is on local branch
bf/16.0.0-v3-settings-read-scope 06ba6201 over dev b29f1bf7, not pushed:
API3_SETTINGS_STRICT_READ_ENABLED, default off; integration 1999/1/0, unit
1218, red controls failed for the right reasons. Step 2 is the combined note
to the AndroidAPS developers (with BF-164), drafted, not sent. Corrections,
measured or read 2026-10-25: AAPSClient's v3 settings read exists only in
AndroidAPS 4.0.0 (beta1, rc1, dev), not in released 3.4.2.6; tokens made by
the AndroidAPS master (role aaps-client) carry api:settings:admin; *:*:read
implies api:settings:read and api:settings:read:<x> under shiro-trie
(measured), so a narrower scope needs a new verb. 2026-10-21: 15.0.9 is
released and RT-0 is removed from blocks_on. Question (for the maintainer,
with the AndroidAPS developers): is API v3 settings meant to be readable with
a follower's read token, or admin-only? 2026-10-02 (maintainer, relayed by
session -d4): DEFERRED until after 15.0.9. Needs more research on AndroidAPS's
use of settings first. 2026-10-02: the private fork of GHSA-25pr has a fix by
Ruben Sutton (code2344, 28d1efa6, on v15.0.8): a shared requiredReadPermission
that makes read by identifier and lastModified demand api:settings:admin, as
search and history do. That is the gating choice, which breaks AAPSClient
followers with read tokens; it is not taken until the AndroidAPS question is
answered. After 15.0.9. The question for the AndroidAPS developers: is
settings meant to be readable by a follower's read token (then search and
history are the inconsistent side), or admin-only (then AAPSClient needs a
token change first)?

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-152` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
