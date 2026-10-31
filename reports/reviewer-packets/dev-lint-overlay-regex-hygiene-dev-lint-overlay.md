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

# Review packet — DEV-LINT-OVERLAY-REGEX (PR #8882)

**Development builds show a lint-warning popup on every page:
lib/profilefunctions.js:251's anchored GMT/UTC offset regex trips
security/detect-unsafe-regex (false positive)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `hygiene/dev-lint-overlay` |
| base | `official/dev` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=DEV-LINT-OVERLAY-REGEX` is the measurement |
| semver | `patch` |

## What this changes

lib/profilefunctions.js:251 (`/^(?:GMT|UTC)([+-])(\d{1,2})(?::(\d{2}))?$/i`,
from 79e0155d, 2026-04-25, sub-hour offsets). Under NODE_ENV=development,
webpack/lint-plugin.js reports it as a compilation warning and the HMR overlay
(webpack/webpack.config.js:123) pops it up on every page load; production
builds are not affected.

## Why that semver

lint annotation only, no runtime change

## What an operator would notice

> none (development builds only)

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- not built yet; the fix's gate will be the development build's lint step
  reporting no warning for lib/profilefunctions.js

## Evidence

_None cited in the manifest._

## Notes carried on the item

2026-10-30: fixed in #8882 (04e1bbbc): inline disable with the reason; eslint
lib 21 to 20 warnings, the development build compiles with none. 2026-10-30:
requested by the maintainer while walking the journey lab on #8874 against dev
(relayed by session -7d). Present on dev 305a6533 and #8874 7463e76d.
Assessment (read): a false positive; the pattern is anchored at both ends and
its repeats are capped at two digits. Proposed fix (a): an inline `// eslint-
disable-next-line security/detect-unsafe-regex` with the reason, keeping the
overlay useful for new warnings; alternative (b): overlay warnings off. Small;
can ride in a themed hygiene PR.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=DEV-LINT-OVERLAY-REGEX` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
