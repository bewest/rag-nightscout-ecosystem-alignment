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

# Review packet — BFQ-127

**BF-127 - clock views opened from the menu are blank for a token viewer on a
site that denies anonymous reads (issue #7377)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/clock-token-link` |
| base | `official/dev@74942ec6` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-127` is the measurement |
| semver | `patch` |
| register entries | `BF-127` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

views/index.html clock menu links, or lib/client code that builds them;
possibly views/clockviews/clock.html and lib/client/clock-client.js for a
refused-fetch message.

## Why that semver

a bug fix; the menu links do not work today for token viewers

## What an operator would notice

> If your Nightscout site does not let visitors read data without signing
> in, and you share it with someone by giving them a link with an access
> token in it, the Clock views in the menu open blank for that person. The
> token is not passed on to the clock page. The workaround is to open the
> clock page with the token added to its own address, the same way as the
> main page link. Nothing wrong is shown, but the clock shows nothing at
> all, so keep the alarms on your phone, CGM app or receiver switched on.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official grep -q -E "clockcolorlink|bgclocklink|clocklink" origin/dev -- l`** &nbsp;·&nbsp; kind: `static`

FAILS today: nothing in origin/dev's lib/client touches the Clock menu links,
which is where a token would be carried into them. A presence check only; a
fix made elsewhere (for example in the clock page itself) would leave it red,
so the probe below decides.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by tools/lab/triage-2026-09/clock-token-link.js,
  which needs a cgm-remote-monitor tree with node_modules, and for its
  server arm a booted server with AUTH_DEFAULT_ROLES=denied and a readable
  token, so it is not a queue gate. 2026-09-25: exit 1 on v15.0.8 92d08342
  and dev 4f705217 (menu-opened clock draws nothing; with the token in its
  own URL it draws the value; server 401 without a token and 200 with one).
  Done when the probe exits 0 on the candidate.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/clock-token-link.js`](../../tools/lab/triage-2026-09/clock-token-link.js)

## Notes carried on the item

2026-10-03 (session -d4's agent): bf/clock-token-link 60d5951e = fix 9238fd32
on 74942ec6, merged with dev 68262e86 (no conflicts); 6 files +237/-1: the
Clock menu links (browser-settings.js) and clock-config.html's link carry the
page's own ?token= (URL-encoded once, nothing without a token, no storage);
clock-client.js shows "Not authorized" on a 401 from properties, clock.html
re-checks on a script error; tests/clock-token-link.test.js, 8 tests;
reverting each of the three files fails its own tests. Chromium, denied site,
readable token: dev's Clock, Color and Simple are blank, the branch draws 123,
no token shows the message. Full suite 3560/0/4 on 60d5951e (dev 68262e86 3552
plus 8; api.count-parameter needs an empty database). Not pushed. Pre-
existing, unchanged: curly quotes in the configurator link's target; the main
page sometimes redirects to /profile without the token before the profile
arrives, seen by two agents today (BFQ-124's and this), possibly JL-2's race.
2026-10-02 (maintainer, relayed by session -d4): FIX IN 15.0.9; in RT-0's
blocks_on. Local branch bf/clock-token-link being prepared by -d4's agent in
externals/work/crm-bf127 off dev 74942ec6, not pushed. Approach: the main page
appends its own ?token= to the Clock menu links, and the clock shows a message
on a 401 instead of drawing nothing. Filed 2026-09-25 from the GitHub triage
(issue #7377, opened 2022-03-16). Shares its silence with the #7036 entry: a
clock whose fetch is refused draws nothing and says nothing. Whether to copy a
token into more URLs is a maintainer decision.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-127` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
