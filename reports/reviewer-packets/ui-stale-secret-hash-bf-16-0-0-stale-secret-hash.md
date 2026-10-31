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

# Review packet — UI-STALE-SECRET-HASH (PR #8885)

**A stale API secret hash stored in the browser blocks a valid ?token= link, and
the dialog says only "Wrong API secret"**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-stale-secret-hash` |
| base | `official/dev` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=UI-STALE-SECRET-HASH` is the measurement |
| semver | `patch` |

## What this changes

The browser's stored `apisecrethash` (localStorage) is sent with requests and
takes precedence over a `?token=` in the page URL; the client authorization
code in lib/client (exact file to be located by the fix).

## Why that semver

client sign-in behaviour, no API change

## What an operator would notice

> A follower or caregiver opening a valid token link on a browser that once
> stored a different API secret sees "Wrong API secret" with no hint.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official fetch -q official pull/8885/head && git -C externals/cgm-remote-m`** &nbsp;·&nbsp; kind: `network`

the local fix branch carries BF-223's main-page fix 9be6a2bc (whose browser
test is red on dev and green with it); replace with the PR head gate once
pushed

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-31: pushed by the maintainer as #8885 (head ecbc9c06, base dev
37b2280f), the 16.0.0 small backfixes PR; BF-224 (f59d7872) follows as a fast-
forward. 2026-10-31 later: head ecbc9c06 = 9be6a2bc (main page, the reworded
9b31818e) + dev 37b2280f merge + ecbc9c06 (clock views: clock.html status
script and clock-client.js query; 5 of 7 new tests in tests/clock-token-
link.test.js red on dev, 18 passing after; four break-it controls red for the
right reason). The clock bundle grows 43 gzip bytes (62,968 to 63,011);
tests/page-bundle-budget.test.js moves the clock allowance to 63,043, which
needs the maintainer's explicit acceptance. test:unit 1883/0, test:dom 205,
test:browser 684. Ready to push. 2026-10-31: built by an agent of session -d1
on local bf/16.0.0-stale-secret-hash fbee7345 (fix 9b31818e on dev 368e6c23,
dev 37b2280f merged), not pushed. Registered as BF-223 (BFQ-223). Choice: a
refused saved secret is removed and the page retries with the link's token (or
none) and says why; an accepted secret still wins over a token (existing
contract test). Red on dev: 3 of 5 new tests in tests/browser/status-
bootstrap.test.js; green with the fix; test:browser 684/0, test:unit 1883/0;
break-it: reverting the two lib files fails exactly the 3. In production the
retry waits about 5 s (authFailDelay, keyed on the client address). Clock
views (clock.html, clock-client.js) being added as a second commit.
2026-10-30, journey-lab session (maintainer with session -7d): reproduced
headlessly on dev 305a6533 and #8874 7463e76d; pre-existing. Fix direction,
UNVERIFIED: let an explicit ?token= win over a stored hash for that page, or
clear the stale hash and say why in the dialog.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=UI-STALE-SECRET-HASH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
