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

# Review packet — RT-LOOP-REMOTE-ADDRESS

**Loop remote commands carry the proxy's address as their sender label**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `rt/trust-one-source` |
| base | `official/bf2/auth-hardening@708af170` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=RT-LOOP-REMOTE-ADDRESS` is the measurement |
| semver | `patch` |

## What this changes

lib/api2/notifications-v2.js:34 (passes req.connection.remoteAddress) and the
'remote-address' field lib/server/loop.js puts in every Loop push (overrides,
override cancel, carbs, bolus). Downstream: Loop's NightscoutService decodes
the field as a required String on every V1 remote notification, stores it on a
remote override's enactTrigger, and uploads it back to Nightscout as the
Temporary Override treatment's remoteAddress with enteredBy "Loop (via remote
command)" (LoopWorkspace NightscoutService fe075ef, read 2026-09-24).

## Why that semver

Changes the value of a label in the Loop push payload and in treatments Loop
uploads; no API shape changes, and the key Loop requires is kept.

## What an operator would notice

> When a caregiver sends a remote command to Loop through Nightscout (a
> temporary override, carbs or a bolus), Nightscout tells Loop where the
> command came from, and Loop saves that on the override it records back in
> Nightscout. On most hosted sites that "where" is the address of the
> hosting company's own proxy, not the caregiver's, so it says nothing
> useful. After this change it is the caregiver's address, worked out the
> same way as everywhere else from your TRUST_PROXY setting. That address is
> then saved on each remote override in your Nightscout data, where anyone
> who can read your site's data can see it. Nothing about whether a command
> is accepted depends on it.

## Who should review this, and why

maintainer, and a Loop maintainer for anything that changes the value

## What was measured

**`! git -C externals/cgm-remote-monitor-official grep -nE "req\.(connection|socket)\.remoteAddress" rt/loop-remo`** &nbsp;·&nbsp; kind: `static`

lib/api2 no longer reads the connection's peer as the sender's address;
notifications-v2.js uses clientIPFor(env). At e3354218 the same grep matches
notifications-v2.js:34 (measured 2026-09-24).

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree official/bf2/auth-hardening official/rt/t`** &nbsp;·&nbsp; kind: `static`

The follow-up PR (rt/trust-one-source into bf2/auth-hardening) merges clean;
the merged tree is identical to 71987bb4's, on which the full suite ran
(measured 2026-09-24).

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev rt/loop-remote-address >/dev/n`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free (measured at 153e5658)

**`TEST=notifications-v2 npm run test-single`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-loop-remote-address`

48 passing (43 at e3354218). The address Loop receives for TRUST_PROXY unset,
1, a proxy list and false, and through the real lib/api2 app that
TRUST_PROXY=false comes from the env it is created with. Break-it at 71987bb4,
each reverted, 2026-09-24: the peer address again -> 3 failing (unset, 1,
list); lib/api2 not passing env -> the wiring test. Full suite at 71987bb4,
Node 24.15.0, MongoDB 7: 2577 passing, 3 pending, 0 failing (2572 at
e3354218).

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Decided 2026-09-24 (maintainer): option 2 of the three recorded here -
  route the label through clientIPFor(env) so it follows TRUST_PROXY. Not
  chosen: (1) leave the proxy's address; (3) send a fixed label and no
  address. The accepted cost: the caregiver's public address is stored on
  remote overrides in the treatments collection, readable by anyone with
  read access, including anonymous visitors where AUTH_DEFAULT_ROLES grants
  reading. With TRUST_PROXY unset it is the forwarded-header address the
  caller sent (the endpoint requires notifications:loop:push). Loop decodes
  remote-address as a required String; the value is still a string whenever
  the request has a socket peer, as before.

## Blocked on

`RT-TRUST-ONE-SOURCE`

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/rt-trust-one-source.md`](../../reports/phase0-pr-bodies/rt-trust-one-source.md)
- [`reports/phase0-pr-bodies/rt-loop-remote-address.md`](../../reports/phase0-pr-bodies/rt-loop-remote-address.md)
- [`reports/phase0-pr-bodies/rt-trust-one-source-into-8754.md`](../../reports/phase0-pr-bodies/rt-trust-one-source-into-8754.md)

## Notes carried on the item

Found 2026-09-24 while narrowing client-ip.js (RT-TRUST-ONE-SOURCE): the only
client-address read in lib/ that does not go through client-ip.js. Present
unchanged on origin/dev 153e5658; introduced with the V2 API in 7f05018d
(2023-06-04). req.connection is also a deprecated alias for req.socket. Opened
as #8764 against rt/trust-one-source and merged there (efcd26b1,
2026-09-25T01:04Z), two minutes after rt/trust-one-source had been merged into
bf2/auth-hardening as #8763, so #8754 does not have it. Maintainer,
2026-09-24: it goes into #8754 and ships in 15.0.9, through a PR from
rt/trust-one-source to bf2/auth-hardening (posting copy reports/phase0-pr-
bodies/rt-trust-one-source-into-8754.md; not opened). The 15.0.9 release
notes' TRUST_PROXY section and #8754's posting copy carry the stored-address
notice.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-LOOP-REMOTE-ADDRESS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
