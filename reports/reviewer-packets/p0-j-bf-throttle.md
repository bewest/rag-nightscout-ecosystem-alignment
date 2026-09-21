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

# Review packet — P0-J (PR #8605)

**bf/throttle - BF-30, failed-auth throttling, compatibility default**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/throttle` |
| base | `origin/dev@a8888f0d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=P0-J` is the measurement |
| semver | `patch` |
| register entries | `BF-30` |

## What this changes

1 commit at 435419ce, 3 files, +388/-45. lib/authorization/delaylist.js,
lib/authorization/index.js, tests/authdelay.test.js.

## Why that semver

no declared surface moves and no default changes. For any given request the
delay only ever SHRINKS - a successful authentication is no longer delayed at
all - so nothing that worked stops working. An added log line is not a
surface. The secure default is a later and deliberate bump.

## What an operator would notice

> Two fixes to the delay Nightscout applies after a failed login, and one
> thing it now tells you. Until now that delay was applied on the way IN to
> every request, so a device presenting the CORRECT password could be made
> to wait for somebody else's failed attempts - and if your Nightscout sits
> behind a proxy or a CDN, where many devices can look like they share one
> address, a single misconfigured uploader could slow everything down. The
> delay now applies only to the request that actually failed. Separately,
> the list of recent failures was not being cleared properly and grew for as
> long as Nightscout kept running. THERE IS ALSO A NEW MESSAGE IN YOUR LOG,
> and it is telling you something true - the protection against password
> guessing is weaker than it looks, because the address it counts against
> can be set by whoever is connecting. Nothing you configured has changed
> and nothing you rely on stops working. Restricting access at your proxy or
> hosting provider is the thing that actually helps today. None of this is
> medical advice.

## Who should review this, and why

maintainer. SPLIT OUT OF bf/auth 2026-09-16 on the maintainer's instruction,
and the split is the point. The earlier draft added lib/server/peer-address.js
and threaded a second address through alarmSocket, security, websocket and
index, which CONFLICTED WITH PR #8605 IN FIVE FILES - that PR replaces the
client-address derivation wholesale with a TRUST_PROXY-driven module. Re-cut
without the peer plumbing this branch merges CLEAN against #8605, measured,
and the throttle keys on data.ip, which #8605 then makes trustworthy with no
further change here. What a reviewer needs and cannot read off the diff: THE
DEFAULT IS TODAY'S BEHAVIOUR BY DESIGN, an attacker varying both credential
and header is still not throttled, and that gap is asserted by a test rather
than left implied.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor origin/dev bf/throttle`** &nbsp;·&nbsp; kind: `static`

bf/throttle has not fallen behind origin/dev. GREEN AGAIN 2026-09-21. It went
red when dev moved 45 commits (fdd08706..59430336) taking the eight sibling
Phase 0 branches with it while this one did not follow, and the remedy was the
`git merge dev` recorded in notes. Unlike the eight merged siblings the
question here is still the right one - this branch is waiting to be pushed, so
falling behind dev is a real defect in it and this gate should go red again if
it happens.

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf/throttle >/dev/null`** &nbsp;·&nbsp; kind: `static`

trial-merge into origin/dev is conflict-free

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree bf/throttle origin/chore/nightscout-moder`** &nbsp;·&nbsp; kind: `static`

THE GATE THIS BRANCH EXISTS FOR - it merges clean with PR #8605. The pre-split
draft conflicted in five files (index.js, storage.js, alarmSocket.js,
security.js, websocket.js) and four of those were the peer plumbing alone.
NON-VACUITY, reproduced 2026-09-16: the identical command against bf/auth,
which still narrows storage.js, CONFLICTS. So this is not passing because
merge-tree always passes.

**`sh -c 'git -C externals/cgm-remote-monitor-official grep -qI peer-address bf/throttle && exit 1 || exit 0'`** &nbsp;·&nbsp; kind: `static`

lib/server/peer-address.js is NOT on this branch and nothing references it. A
TRACKING GATE against the obvious regression - re-adding that module is
exactly what re-creates the four-file conflict with #8605, and it would look
like a harmless improvement to anyone who had not measured it.

**`TEST=authdelay npm run test-single`** &nbsp;·&nbsp; kind: `integration` &nbsp;·&nbsp; cwd: `externals/work/crm-bf-throttle`

THE BRANCH'S OWN TEST, 11 passing, measured 2026-09-16. Needs MongoDB - this
worktree names 27031. It is in NEITHER local brace list, so a green `npm run
test:unit` is no evidence for any of this. ABLATED:
lib/authorization/delaylist.js and lib/authorization/index.js restored to
origin/dev give 3 passing / 8 failing. It includes the test that PINS THE
REMAINING WEAKNESS - `does NOT yet throttle a guess that varies both the
secret and the address` - which asserts the gap rather than pretending it is
closed, and which should be INVERTED into a positive assertion when the
TRUST_PROXY boundary lands.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- NOTHING MEASURES THE BOOT WARNING'S WORDS. init() logs that the throttle
  is keyed on an address the caller may control, and that restricting access
  at the proxy is what helps today. That text IS the notification half of
  the maintainer's compatibility decision, and it is prose - the same shape
  as P0-C-REMEDIATE, whose prose turned out to be wrong twice before a gate
  caught it. A real gate would check that the message names no setting that
  does not exist on this branch, and that it never claims the throttle
  protects against credential guessing.
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

THE SPLIT, AND WHY IT WAS NOT TIDINESS. bf/auth carried BF-17 and BF-30
together. Asked whether the delaylist was already handled in the modernization
work, the measurement said something more useful than yes or no: Andy does not
touch lib/authorization/delaylist.js at all - it is byte-identical to dev on
his branch - but he REPLACES THE IP DERIVATION THAT FEEDS IT, swapping the
forwarded-for package for lib/server/client-ip.js driven by TRUST_PROXY, in
exactly the call sites the BF-30 draft also edited. Both branches were
independently fixing one root cause with two different modules. Dropping peer-
address.js took the conflict from five files to one, and the one that remains
belongs to BF-17. WHAT THE COMPATIBILITY DEFAULT COSTS, recorded because it
was argued and decided rather than assumed: another release in which an
attacker rotating X-Forwarded-For is not throttled. The usual price of turning
it on - one failing client behind a shared proxy slowing others - is ALREADY
PAID FOR by the sleep-timing change in this same commit, because only failing
requests wait. So the compatibility case is weaker here than for the allow-
list on P0-C, and that was said at the time. The maintainer's instruction was
compatibility defaults plus notification across this area, and that is what
shipped. MERGED UP 2026-09-21 ON THE MAINTAINER'S INSTRUCTION, alongside P0-C
and for the same reason. Tip is now a0823c4f, a merge of origin/dev 59430336
into 435419ce. Back to ready-to-push, packet regenerated. ZERO OVERLAP,
MEASURED BEFORE MERGING: dev has no commit touching any of this branch's three
files (lib/authorization/delaylist.js, lib/authorization/index.js,
tests/authdelay.test.js), so unlike P0-C there was no same-file question to
reason about. The two properties the 2026-09-16 re-cut exists to preserve were
both re-checked after the merge and both hold - no conflict against
chore/nightscout-modernization, which is where PR #8605 lives, and no peer-
address plumbing on the branch. TEST=authdelay: 11 passing at 435419ce, 11
passing at a0823c4f. ONE THING WORTH RECORDING BECAUSE IT NEARLY BECAME A
FALSE FINDING. The first post-merge run of this suite reported 6 passing / 1
failing, a "before all" hook timing out after 30 s. It was not a regression:
mongod had fatal-asserted and exited during an unrelated full-suite run, so
the boot had nothing to connect to. That is register entry BF-10, and
reproducing it is what the red actually measured. A red control can be red for
the wrong reason.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-J` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `59430336`.*
