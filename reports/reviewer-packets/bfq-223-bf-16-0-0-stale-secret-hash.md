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

# Review packet — BFQ-223 (PR #8885)

**BF-223 - a saved API secret the site refuses blocks a valid ?token= link**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-stale-secret-hash` |
| base | `official/dev@37b2280f` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BFQ-223` is the measurement |
| semver | `patch` |
| register entries | `BF-223` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/client/index.js client.init and lib/client/hashauth.js (main page);
views/clockviews/clock.html and lib/client/clock-client.js (clock views,
second commit in progress). Only a secret the server has refused is removed;
an accepted secret still wins over a token.

## Why that semver

client sign-in behaviour only; no API change

## What an operator would notice

> A follower or caregiver who opens a valid token link on a browser that
> once saved a different API secret is shown the sign-in dialog (or "Not
> authorized" on a clock) instead of the site. With the fix the saved secret
> is removed, the link's token is used, and the dialog says so if that also
> fails. On 15.0.9 and dev.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official fetch -q official pull/8885/head && git -C externals/cgm-remote-m`** &nbsp;·&nbsp; kind: `network`

the local fix branch carries BF-223's main-page fix 9be6a2bc; replace with the
PR head gate once pushed, then official/dev ancestry once merged

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-31: pushed by the maintainer as #8885 (head ecbc9c06, base dev
37b2280f), the 16.0.0 small backfixes PR; BF-224 (f59d7872) follows as a fast-
forward. 2026-10-31: filed by session -d1 with BF-223; same work as UI-STALE-
SECRET-HASH. Head ecbc9c06 (main page and clock views), ready to push; the
clock bundle allowance moves by 43 bytes (maintainer to accept).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-223` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
