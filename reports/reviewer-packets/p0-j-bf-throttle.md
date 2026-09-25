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

# Review packet — P0-J (PR #8754)

**bf/throttle - BF-30, failed-auth throttling, compatibility default**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/throttle` |
| base | `origin/dev@a8888f0d` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=P0-J` is the measurement |
| semver | `patch` |
| register entries | `BF-30` |

## What this changes

Content: 1 commit at 435419ce, 3 files, +388/-45.
lib/authorization/delaylist.js, lib/authorization/index.js,
tests/authdelay.test.js. Tip a0823c4f is a merge of origin/dev 59430336 into
435419ce (2026-09-21).

## Why that semver

no declared surface moves and no default changes. For any given request the
delay only ever SHRINKS - a successful authentication is no longer delayed at
all - so nothing that worked stops working. An added log line is not a
surface. The secure default is a later and deliberate bump.

## What an operator would notice

> This branch does not ship on its own. The failed-login fixes it started
> are carried in PR #8754 (the BF2-AUTH item), which describes what changes
> for you; they are not yet merged or released. Nothing here changes
> anything you configured. None of this is medical advice.

## Who should review this, and why

maintainer. Split out of bf/auth on 2026-09-16 on the maintainer's
instruction, without the lib/server/peer-address.js plumbing that conflicted
with PR #8605 in five files - that PR replaces the client-address derivation
wholesale with a TRUST_PROXY-driven module. This branch merges CLEAN against
#8605, measured, and the throttle keys on data.ip, which #8605 then makes
trustworthy with no further change here. What a reviewer needs and cannot read
off the diff: THE DEFAULT IS TODAY'S BEHAVIOUR BY DESIGN, an attacker varying
both credential and header is still not throttled, and that gap is asserted by
a test rather than left implied.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/throttle origin/bf2/auth-hardening ||`** &nbsp;·&nbsp; kind: `static`

bf/throttle ships inside PR #8754 (bf2/auth-hardening, queue BF2-AUTH): its
tip is contained in #8754's head, or in origin/dev once #8754 merges. Needs
`git -C externals/cgm-remote-monitor-official fetch origin` first.

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/throttle >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree bf/throttle origin/chore/nightscout-moder`** &nbsp;·&nbsp; kind: `static`

The property this branch exists for - it merges clean with PR #8605. With the
peer-address plumbing included it conflicted in five files (index.js,
storage.js, alarmSocket.js, security.js, websocket.js). Non-vacuity,
reproduced 2026-09-16: the identical command against bf/auth, which narrows
storage.js, CONFLICTS - so this is not passing because merge-tree always
passes.

**`sh -c 'git -C externals/cgm-remote-monitor-official grep -qI peer-address bf/throttle && exit 1 || exit 0'`** &nbsp;·&nbsp; kind: `static`

lib/server/peer-address.js is NOT on this branch and nothing references it. A
tracking gate against the obvious regression - re-adding that module re-
creates the four-file conflict with #8605, and it would look like a harmless
improvement to anyone who had not measured it.

**`TEST=authdelay npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-throttle`

The branch's own test, 11 passing, measured 2026-09-16 and again at a0823c4f
on 2026-09-21. Needs MongoDB - this worktree names 27031. It is in neither
local brace list, so a green `npm run test:unit` is no evidence for any of
this. Ablated: lib/authorization/delaylist.js and lib/authorization/index.js
restored to origin/dev give 3 passing / 8 failing. It includes the test that
PINS THE REMAINING WEAKNESS - `does NOT yet throttle a guess that varies both
the secret and the address` - which asserts the gap rather than pretending it
is closed, and which should be INVERTED into a positive assertion when the
TRUST_PROXY boundary lands. A red here can be mongod having died (BF-10)
rather than the branch; check the server before reading it as a regression.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Nothing measures the boot warning's words. init() logs that the throttle
  is keyed on an address the caller may control, and that restricting access
  at the proxy is what helps today. That text IS the notification half of
  the maintainer's compatibility decision, and it is prose - the same shape
  as P0-C-REMEDIATE, where prose needed a gate to stay correct. A real gate
  would check that the message names no setting that does not exist on this
  branch, and that it never claims the throttle protects against credential
  guessing.
- THE ADDRESS KEY IS STILL CALLER-CONTROLLED, DELIBERATELY. This branch does
  not close BF-30. It makes the control cheap for legitimate clients, bounds
  the list, stops retaining the credentials people tried, adds a second key,
  and says so out loud. An attacker who varies both the credential and the
  forwarded header is throttled by neither key. Closing it needs the
  TRUST_PROXY boundary from PR #8605, after which data.ip is an address the
  caller cannot choose and this file needs no edit. BF-30 MUST NOT BE READ
  AS FIXED on the strength of this item.

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf-throttle.md`](../../reports/phase0-pr-bodies/bf-throttle.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Not shipping on its own. bf/throttle (content 435419ce, tip a0823c4f, a merge
of dev 59430336 made 2026-09-21) is contained by ancestry in bf2/auth-
hardening, PR #8754 (BF2-AUTH), which is what ships the failed-login fixes in
15.0.9. bf/throttle will not be pushed or merged up on its own; its first gate
checks that containment (in #8754's head b5f61f19, measured 2026-09-24). What
ships differs from this branch in one respect. On bf/throttle only the failing
request waits. #8754's head b5f61f19 (pushed 2026-09-24) contains f6f361b1,
which puts the wait back before the credential check, as in earlier releases;
failures are also counted per credential, and the list is bounded and swept on
a schedule. BF2-AUTH describes the shipped behaviour. Decisions: - 2026-09-16
(maintainer): split out of bf/auth, without the lib/server/peer-address.js
plumbing that conflicted with PR #8605 in five files. #8605 does not touch
lib/authorization/delaylist.js, but it replaces the address derivation that
feeds it (lib/server/client-ip.js driven by TRUST_PROXY) in the call sites the
peer-address plumbing also edited. Without peer-address.js the only conflict
with #8605 is storage.js, which belongs to BF-17 (P0-C). - 2026-09-16
(maintainer): compatibility defaults plus notification across this area. The
cost, recorded when it was decided: another release in which an attacker
rotating X-Forwarded-For is not throttled. The 2026-09-21 merge-up had zero
overlap (dev had no commit touching this branch's three files); after it the
branch still merges clean against chore/nightscout-modernization and carries
no peer-address plumbing. TEST=authdelay: 11 passing at 435419ce and at
a0823c4f. `pr: [8754]` is declared explicitly because the review text names
#8605, which is RT-3's PR, not this item's.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-J` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
