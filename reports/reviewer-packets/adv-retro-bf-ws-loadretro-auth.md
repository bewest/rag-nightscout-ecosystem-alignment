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

# Review packet — ADV-RETRO

**GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/ws-loadretro-auth` |
| base | `origin/dev@59430336` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=ADV-RETRO` is the measurement |
| semver | `patch` |
| register entries | `BF-79` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

1 commit at 9765e8cd. lib/server/websocket.js (+36/-4) and one new test file,
tests/websocket.loadretro-authorization.test.js (210 lines, 4 cases). No other
file. The change adds resolveReadAccess(), which calls the
verifyAuthorization() already in that file with an empty message, so an
anonymous socket resolves through the same AUTH_DEFAULT_ROLES shiros the REST
surface uses. Verified NOT to interact with the failed-login throttle - an
empty auth message takes authorization.resolve()'s !authAttempted branch and
never records a failure.

## Why that semver

No route removed, no input added, no documented contract changed. The only
behaviour that disappears is behaviour nobody was entitled to: on a `readable`
instance an anonymous client still receives retroUpdate, which was confirmed
as a live positive control on the fixed build.

## What an operator would notice

> Nightscout's live connection had one message that answered anybody. If you
> run the default setup, where your site is already readable by anyone with
> the address, this changes nothing you can see and leaked nothing you were
> not already publishing - it returned less than your own web address does.
> If you followed the documentation and turned off unauthorised access, it
> did matter: about a day of pump and loop information - insulin on board,
> reservoir and battery levels, whether the pump was delivering or stopped,
> your pump's serial number and your phone's name - could still be read by
> anyone who knew your address, even though every other way in was refused.
> After this change that message follows the same rule as everything else.
> Nightscout is not a medical device and this is not medical advice.

## Who should review this, and why

SECURITY. The advisory is a GitHub draft with no CVSS vector and a bare
`high`, and three of its statements need correcting before publication. (1)
AFFECTED RANGE IS WRONG. It says >0.8.1; loadRetro is absent from tags 0.8.1
through 0.8.4 and first appears in 0.9.0 - which is also the first tag
carrying DataReceivers and authDefaultRoles, so the handler and the
authorization it skips shipped together. Should be >=0.9.0. (2) "This does not
require any specific configuration on the system" is true of reachability and
false as an impact claim. On the shipped readable default the payload is a
STRICT SUBSET of what GET /api/v1/devicestatus.json already serves anonymously
- measured field by field: 0 socket record _ids absent from the REST answer, 0
JSON field paths present only on the socket, and REST returned 1730 records to
the socket's 574. Marginal disclosure on a default install is zero. (3) It
understates the hardened case. Under AUTH_DEFAULT_ROLES=denied, with every
REST read answering 401 in the same run, the handler returns 576 records -
28.8x MORE than an authorized reader gets on connect, because authorize()
trims to 10 per device-and-type. No setting stops it: denied, status-only,
AUTHENTICATION_PROMPT_ON_LOAD and TREATMENTS_AUTH=off were each measured.
DEVICESTATUS_DAYS=2, the only knob touching the path, DOUBLES it to 1150.
Recommended: score CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N = 7.5 and say
it scores the hardened configuration; the default arm is 0.0 and publishing a
high score against it would alarm the majority of self-hosters about their own
public output. PATCHED-VERSION FIELD: LEAVE EMPTY until a tagged release
carries this. origin/master is 299 commits behind dev and neither carries the
fix.

## What was measured

**`git -C externals/work/crm-adv-retro merge-base --is-ancestor origin/dev bf/ws-loadretro-auth`** &nbsp;·&nbsp; kind: `static`

The branch is still based on dev's tip. Goes red the moment dev moves under
it, which is the signal to rebase before anyone reviews it.

**`test -f externals/work/crm-adv-retro/tests/websocket.loadretro-authorization.test.js`** &nbsp;·&nbsp; kind: `static`

The regression test exists in the worktree. Deliberately a file- existence
check rather than a suite run - see the unit gate below.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- NO GATE RUNS THE SUITE HERE. `npm test` on this tree needs a my.test.env
  and a mongod of its own, and the two sessions that ran it on 2026-09-21
  both had to raise the container's nofile limit first (the default 1024
  exhausts mongod's descriptors part-way through, which is BF-10's failure
  mode arriving in the lab). Measured by hand on a healthy mongod 7.0.43:
  2311 passing / 3 pending / 0 failing before, 2315 / 3 / 0 after, delta
  exactly the four new cases. Ablation - revert lib/server/websocket.js to
  origin/dev, keep the test - turns the two negative cases red printing the
  symptom itself, canaried devicestatus arriving at a socket the server had
  already resolved as unable to read, while the two positive cases stay
  green. Automating this needs a fixture that owns its own mongod.

## Evidence

- [`docs/60-research/remedial/ghsa-gjhc-loadretro-2026-09-21.md`](../../docs/60-research/remedial/ghsa-gjhc-loadretro-2026-09-21.md)
- [`docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md`](../../docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md)
- [`docs/30-design/remedial/security-advisory-disposition-2026-09-21.md`](../../docs/30-design/remedial/security-advisory-disposition-2026-09-21.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

REPRODUCED on v15.0.7, v15.0.8 and dev 59430336, both arms, mongod 7.0.43,
with the isolating control in every run: the same unauthenticated socket that
never emits loadRetro sees only the event `clients`. Six of the seven handlers
on that namespace DO check - dbAdd, dbUpdate, dbUpdateUnset and dbRemove all
answer "Not authorized" and write nothing, confirmed against the collection
rather than the reply string. loadRetro is the single unguarded one, which is
why it is cheap to fix and easy to have missed. The attacker never calls
`authorize`: trying and failing disconnects the socket, so the gate is one to
walk around rather than through.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ADV-RETRO` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `59430336`.*
