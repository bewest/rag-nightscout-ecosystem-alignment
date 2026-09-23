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

# Review packet — BF2-AUTH

**bf2/auth-hardening - bf/auth + bf/throttle + the client-ip.js backport behind
TRUST_PROXY**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf2/auth-hardening` |
| base | `origin/dev@74fc6619` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BF2-AUTH` is the measurement |
| semver | `major` |
| register entries | `BF-17`, `BF-30` |

## What this changes

Tip 29e6430e on origin/dev 74fc6619. lib/authorization/{index,delaylist,
storage,endpoints}.js; lib/server/{client-ip,env,app,websocket}.js;
lib/api/{index,status}.js; lib/api3/{index,security,alarmSocket,
storageSocket}.js; package.json and lock (proxy-addr declared, forwarded-for
kept); README and docs/proposals/trusted-proxy-migration.md. Against
chore/nightscout-modernization b1bdaca0 it conflicts in 10 paths, two of them
pre-existing (bootevent.js from dev, storage.js from bf/auth).

## Why that semver

Inherits P0-C's major (the BF-47 allow-list), unless the maintainer's BF-47
decision puts that behind a compatibility flag, which would make this minor (a
new setting, today's behaviour by default).

## What an operator would notice

> Not released. Combines the two login-security fixes already described
> under P0-C and P0-J with a setting that lets you tell Nightscout which
> proxy in front of it to trust. If you change nothing, Nightscout behaves
> as it does today; the stronger protection against password guessing
> applies only once you name your trusted proxy.

## Who should review this, and why

SECURITY - the reviewer P0-C already names; none assigned.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/auth bf2/auth-hardening && git -C ext`** &nbsp;·&nbsp; kind: `static`

Contains both source branches by ancestry, not re-implementation.

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf2/auth-hardening >/dev/null`** &nbsp;·&nbsp; kind: `static`

Merges into origin/dev with no conflict.

**`git -C externals/cgm-remote-monitor-official cat-file -e bf2/auth-hardening:lib/server/client-ip.js`** &nbsp;·&nbsp; kind: `static`

The client-address module is present. Its default being today's behaviour is
asserted by the branch's own tests, not here.

**`cd externals/work/crm-bf2-auth && n exec 20.20.0 npx mocha --timeout 10000 --exit tests/client-ip.test.js`** &nbsp;·&nbsp; kind: `unit`

48 cases, no database. Pins dev's client address, HTTPS detection and hostname
with TRUST_PROXY unset (0, 1 and 2 hops, history dependence). Control, re-run
2026-09-22 - restoring 395f3207's client-ip.js fails exactly 7; flipping the
unset default to trust nothing fails 23.

**`cd externals/work/crm-bf2-auth && TEST=authdelay npm run test-single`** &nbsp;·&nbsp; kind: `integration`

19 cases - default keying, the documented default gap, throttling under a
configured TRUST_PROXY, and the boot message's claims. Flipping the unset
default fails 5; bypassing TRUST_PROXY in authorization/index.js fails 4.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf2-auth-hardening.md`](../../reports/phase0-pr-bodies/bf2-auth-hardening.md)
- [`docs/30-design/remedial/backfix-2-plan-2026-09-22.md`](../../docs/30-design/remedial/backfix-2-plan-2026-09-22.md)

## Notes carried on the item

PREPARED 2026-09-22, held until 15.0.9 is tagged. Commits: merges of bf/auth
and bf/throttle; cherry-pick -x of 06c83f2f and 395f3207 (hunks for files
absent on dev dropped); 1114228d adapts two cherry-picked tests to
bf/throttle's keysFor(); 8b975b41 is a PORT - with TRUST_PROXY unset the
address comes from forwarded-for exactly as on dev, because 395f3207's default
differs in four cases (BF-88); the trusted path is 395f3207's code unchanged.
ONE flag, not two - the throttle keys on data.ip, which now comes from client-
ip.js. Suite on Node 20.20.0 - dev 2386/0/3, branch 2462/0/3, +76 exactly.
Semver stays major for BF-47; a compat flag for BF-47 (sketched in the PR
body) would make it minor. PRs open after 15.0.9 is tagged (plan section 3).
BF-30 is closed only when TRUST_PROXY names a boundary; with the default it
remains open, and the branch must say so in its boot message and PR body.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BF2-AUTH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
