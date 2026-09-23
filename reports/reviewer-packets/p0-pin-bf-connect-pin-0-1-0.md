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

# Review packet — P0-PIN (PR #8752)

**bf/connect-pin - pin dev to the published nightscout-connect 0.1.0**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/connect-pin-0.1.0` |
| base | `origin/dev@74fc6619` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-PIN` is the measurement |
| semver | `patch` |

## What this changes

One line of package.json (the nightscout-connect dependency) plus the lockfile
entry that follows it (P0-LOCK). The branch today holds 0807eb1c, which points
at a v0.0.14 tag tarball that will never exist; the pin replaces it.

## Why that semver

a dependency pin move; the behaviour change is the connector's and is
classified at P0-F.

## What an operator would notice

> Nightscout picks up the new connector (the part that fetches readings from
> a CGM vendor's online service): the fixes that keep CGM vendor credentials
> and personal health data out of the log file, the CareLink "no reading"
> fix that keeps high and low alarms working, cleaner shutdown and the retry
> timing fixes. Not released; waits on the connector's full 0.1.0 release
> (P0-TAG).

## Who should review this, and why

maintainer

## What was measured

**`grep -q '"nightscout-connect": "0.1.0"' package.json`** &nbsp;·&nbsp; kind: `static` &nbsp;·&nbsp; cwd: `externals/work/crm-connect-pin-010`

package.json pins the exact published 0.1.0 from npm. RED until the pin is
written; it waits on P0-TAG.

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/connect-pin-0.1.0`** &nbsp;·&nbsp; kind: `static`

bf/connect-pin has not fallen behind origin/dev. RED: dev at 74fc6619 carries
the Phase 0 merges this branch does not. The remedy is a `git merge dev`; the
trial merge was measured conflict-free on 2026-09-21.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- A cgm-remote-monitor dev branch can pin a prerelease (for example
  "0.1.0-dev.1") to test it; a cgm-remote-monitor release pins only a full
  connector release.

## Blocked on

`P0-TAG`

## Evidence

- [`docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`](../../docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md)

## Notes carried on the item

OPENED 2026-09-23 as nightscout/cgm-remote-monitor #8752 (head adf5120c, base
dev) - exact 0.1.0-dev.2. Whether it merges on dev.2 or moves to exact 0.1.0
after the P0-TAG release first is open. 2026-09-23 - moved to 0.1.0-dev.2:
bf/connect-pin-0.1.0 is now adf5120c (the dev.1 commit 338deb7f amended; never
pushed). Lock moves only the connector entry; installed package carries #77
and #78. Suite 2386/0/3 on Node 20.20.0 and 22.23.2 against mongo:7 with
nofile 64000; debug-logging 23/23, and with a checkout of tag v0.0.13 swapped
in exactly 5 fail. With Docker's default nofile the suite kills mongod
whichever connector is installed (BF-10). The maintainer may open this into
dev now so that dev tests the prerelease; gate 1 stays red until the swap to
exact 0.1.0 for the release. DECIDED 2026-09-23 (maintainer) - this pin swaps
to 0.1.0 only after the prerelease testing P0-TAG now waits on, and after
BF-89 is fixed in connector dev. PREPARED 2026-09-22 - bf/connect-pin-0.1.0 at
338deb7f pins exact 0.1.0-dev.1 from the registry (package.json 1+/1-, lock
4+/4-); full suite 2386/0/3 on both arms; the debug-logging control fails
exactly its five cases on v0.0.13. The swap to 0.1.0 is one token plus lock
regeneration once 0.1.0 is on npm; commands in reports/phase0-pr-
bodies/connect-pin-0.1.0.md. Gate 1 stays red until then, by design. The old
bf/connect-pin (0807eb1c) is superseded and was not modified. This closes the
split GT4 found: neither dev's pin (234d47c) nor cut 4's pin carries both the
logging narrowing and the redaction commits. Master pins connector tag
v0.0.13. Pin the exact version rather than a range, so package.json and not
only the lockfile says which connector ships. COMPATIBILITY MEASURED
2026-09-22 (connector 1946beb = v0.1.0-dev.1 source swapped into cgm-remote-
monitor dev 74fc6619, no dependency change between the two): full suite 2386
passing / 0 failing / 3 pending, identical to the shipped 234d47c arm, against
a private mongo:7. Red control: with v0.0.13 swapped in, tests/debug-
logging.test.js fails exactly its five installed-connector cases (18 pass), so
the suite distinguishes connectors. Connector's own suite 289/289 on Node
20.20.0, 22.23.2 and 24.20.0 (its CI covers only 22 and 24). Evidence:
release-readiness-15.0.9 §5.2.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-PIN` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
