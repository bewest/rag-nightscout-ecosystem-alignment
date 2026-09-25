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

# Review packet — RT-TRUST-ONE-SOURCE

**Every client-address consumer uses one TRUST_PROXY policy compiled from env**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `rt/trust-one-source` |
| base | `official/bf2/auth-hardening@e549e1a6` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-TRUST-ONE-SOURCE` is the measurement |
| semver | `patch` |

## What this changes

lib/server/client-ip.js, lib/api3/security.js, lib/server/app.js and the five
modules that call createClientIP(env.trustProxy) (authorization/index.js,
api/status.js, server/websocket.js, api3/alarmSocket.js,
api3/storageSocket.js); delaylist.js boot messages; the API v3 key tests in
tests/client-ip.test.js.

## Why that semver

Behaviour-neutral refactor: in production both routes already end in the same
compiled function (measured 2026-09-24 at e549e1a6).

## What an operator would notice

> Nothing changes for site owners. Every part of Nightscout that works out a
> visitor's address reads the TRUST_PROXY setting the same way, so a later
> change cannot make one part (API v3 logins) disagree with the rest.

## Who should review this, and why

maintainer

## What was measured

**`! git -C externals/cgm-remote-monitor-official grep -nE "trust proxy fn|createClientIP\(env|compileTrust\(env"`** &nbsp;·&nbsp; kind: `static`

One source: nothing under lib/ on the branch compiles env.trustProxy itself or
reads Express's 'trust proxy fn'; app.js, the five consumers, the delay list
and api3/security.js all go through trustFor(env) / clientIPFor(env). At
e549e1a6 the same grep matches 10 lines (measured 2026-09-24).

**`! git -C externals/cgm-remote-monitor-official grep -nE "createClientIP|compileTrust|getClientIP" rt/trust-one`** &nbsp;·&nbsp; kind: `static`

One way to do it: outside client-ip.js, no code or test names the old entry
points. client-ip.js exports trustFor and clientIPFor only (e3354218), so new
code copying the tests learns those two. At d0a3d628 the same grep matches 36
lines (measured 2026-09-24).

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor e3354218 official/bf2/auth-hardening`** &nbsp;·&nbsp; kind: `static`

Containment: #8763 was merged into #8754's branch (708af170, 2026-09-24), so
both commits reach dev and 15.0.9 with #8754.

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev rt/trust-one-source >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free (measured at 153e5658). Against
rt/cut4 and origin/chore/nightscout-modernization it conflicts, and in six
files more than e549e1a6 does: the one-line consumer changes in app.js,
websocket.js, authorization/index.js, api3/security.js, alarmSocket.js and
storageSocket.js.

**`TEST=client-ip npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-trust-one-source`

62 passing (60 at e549e1a6: the inherits-from-parent test replaced by the
v3-app-with-its-own-trust test, plus the one-policy-per-env and export-list
tests). Break-it at e3354218, each reverted, 2026-09-24: security.js ignoring
env -> 3 failing; no cache, app.js building its own policy, and a cache that
ignores env.trustProxy changes -> the one-policy test; a third export -> the
export test. Full suite at e3354218, Node 24.15.0, MongoDB 7: 2572 passing, 3
pending, 0 failing (2570 at e549e1a6).

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`BF2-AUTH`

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/rt-trust-one-source.md`](../../reports/phase0-pr-bodies/rt-trust-one-source.md)
- [`docs/30-design/modernization/cut-rehearsal-on-15.0.9-rc-2026-09-23.md`](../../docs/30-design/modernization/cut-rehearsal-on-15.0.9-rc-2026-09-23.md)
- [`reports/phase0-pr-bodies/rt-trust-one-source.md`](../../reports/phase0-pr-bodies/rt-trust-one-source.md)

## Notes carried on the item

Target: cut 1 or cut 2 of the modernization train, or earlier on dev if it
fits this release cycle (maintainer, 2026-09-24). Today two routes deliver the
policy: five modules compile env.trustProxy themselves, and
lib/api3/security.js alone reads the Express setting the v3 app inherits from
app.js. e549e1a6 (on #8754) tests the inherited route and sets the API v3
fixture's parent as app.js does; it does not remove the second route. Cuts 1-3
do not touch client-ip.js or api3/security.js; cut 2 changes
tests/fixtures/api3/instance.js in a different hunk (bound address family,
27da0f8a) and trial-merges with #8754's head without a conflict in these
files. Cuts 4 and 5 carry their own client-ip.js (06c83f2f, 395f3207), already
resolved to the candidate's file (BF-88); cut 5 also sets 'trust proxy' on the
v1 and v3 apps (#8605), which this change makes inert for the client address
as well as for Express. Lowest home is dev (base of the stack); if dev is
frozen for 15.0.9, commit it on cut 1 and merge up. #8763 merged into
bf2/auth-hardening as 708af170 (2026-09-25T01:02Z); it ships with #8754 in
15.0.9. Before that: opened 2026-09-24 as draft #8763, head e3354218, base
bf2/auth-hardening (stacked on #8754); retarget to dev when #8754 merges. Test
CI does not run on it while the base is not dev (only auto-close ran). Real
boot on d0a3d628 and e549e1a6 compared: TRUST_PROXY=loopback refused at boot
with the same error on both, TRUST_PROXY=1 listens on both.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-TRUST-ONE-SOURCE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
