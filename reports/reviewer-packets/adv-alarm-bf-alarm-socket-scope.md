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

# Review packet — ADV-ALARM

**GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/alarm-socket-scope` |
| base | `origin/dev@59430336` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=ADV-ALARM` is the measurement |
| semver | `minor` |
| register entries | `BF-75`, `BF-76`, `BF-80` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

REBUILT 2026-09-21 on fix shape B after the maintainer decision; the old
shape-A tip is preserved at refs/backup/alarm-shapeA = 842d81fb in that
worktree and can be deleted once the rebuild is accepted. 2 commits at
012f1623. fd80e6a2 is the broadcast fix as ONE coherent shape-B change plus a
49-case regression test; 012f1623 is the ack-authorization fix plus 2 cases.
There is deliberately no A-then-B pair in the history. lib/api3/alarmSocket.js
(+74/-19), lib/client/hashauth.js (+8), two new test files. The client change
is the part to look at hardest: it re-runs subscribeForAlarms from
hashauth.updateSocketAuth, because client.subscribeForAlarms had exactly ONE
call site - the socket's connect handler - and nothing re-subscribed when a
viewer authenticated in the page. Without it, load -> refused -> prompt ->
enter secret would leave that socket in no room, silently receiving no alarms,
for the one user who had just proved entitlement. The source was already
asking this at alarmSocket.js:150: "TODO: how will perms get updated after
authorizing?".

## Why that semver

It removes reachable behaviour that undocumented third-party clients may
depend on - receiving alarms without subscribing - so it is not a patch by the
project's own reading, whichever variant of the fix is chosen. Not major: no
route removed, no required input added, and the shipped web client is
unaffected because it subscribes.

## What an operator would notice

> Nightscout sends alarms and treatment notifications over a live
> connection. That connection was sending them to everyone attached to it,
> whether or not they had signed in. If you run the default setup your site
> already publishes this information to anyone with the address, so nothing
> new was exposed - what it added was that someone could watch it arrive in
> real time without ever making a request your logs would record. If you had
> turned off unauthorised access, it did matter: carb entries, insulin
> doses, loop activity, and your high and low alarms were still going out to
> anyone who connected. After this change, only viewers your site has
> authorised receive them. If you use a third-party follower app that shows
> Nightscout alarms and it stops showing them after this update, that is
> this change - please report it, because the connection it uses has never
> been documented. Nightscout is not a medical device and this is not
> medical advice; if you rely on these alarms, keep a second way of being
> alerted until you have confirmed yours still works.

## Who should review this, and why

SECURITY. THE SHAPE DECISION IS TAKEN - Ben West, 2026-09-21, SHAPE B: admit
at connection time when the deployment's anonymous default role already
permits reading, re-evaluate on subscribe, and gate delivery on api:*:read. He
separately judged the shipped web client to be the only consumer of /alarm -
the fact that would have argued for the strict shape - and chose B anyway, as
insurance against that judgement being wrong. The paragraph below is kept as
the record of what was weighed. THERE IS A SECOND PR IN PLAY: the advisory's
reporter opened one in GitHub's private fork (nightscout/cgm-remote-monitor-
ghsa-8849-qjp5-vrrj PR #1, based on v15.0.8) on 2026-09-18. Measured, it does
NOT close the bypass: it gates on AUTHENTICATION_PROMPT_ON_LOAD rather than
AUTH_DEFAULT_ROLES, so on a hardened instance with the prompt flag at its
default a never-subscribing socket still receives everything; and even where
it engages it never consults api:*:read, so a token granting only
api:treatments:create hears every alarm while getting 401 on every REST read
in the same run. Any reviewer of this branch should read ghsa-8849-reporter-
pr-evaluation-2026-09-21.md and decide how the two PRs are reconciled and how
the reporter is credited. THE SUPERSEDED SHAPE, FOR THE RECORD: shape A
required SUBSCRIBED AND AUTHORIZED. On the shipped `readable` default,
receiving without subscribing is behaviour third-party clients have observed
for five releases: the /alarm protocol is in no swagger file and nothing under
docs/, so implementers had only the observed behaviour to go on. Measured, the
marginal CONTENT disclosure on that default is zero - every field in all five
payloads is already in treatments.json, entries.json or status.json, and
notifyhash/key are sha1 over already-readable fields. So the strict version
breaks non-subscribing clients for no confidentiality gain on the majority
configuration. A one-line variant - join at CONNECTION time when the anonymous
default role already permits reading, re-evaluate on subscribe - closes the
`denied` bypass identically and changes nothing on a default install. Too
tight and a follower app silently stops delivering hypo alarms; too loose and
the bypass stays open. THAT WAS THE DECISION, AND IT WENT TO B. Second thing
the reviewer should be told: BF-76 is NOT part of the advisory. It was found
while fixing BF-75 - the access-token branch of subscribe registered
socket.on('ack') with no permission check, so any valid token of any role
could silence every alarm on the instance, with a caller-supplied silenceTime
that has no upper bound. Authorization is fixed; the unbounded silence is left
open on purpose, because what a legitimately authorized client may ask for is
a product decision. Third: no automated test drives hashauth against a live
socket. A human must load a `denied` instance, authenticate at the prompt,
force an alarm and confirm it arrives. That is the one path the 28 new cases
do not cover.

## What was measured

**`git -C externals/work/crm-adv-alarm merge-base --is-ancestor origin/dev bf/alarm-socket-scope`** &nbsp;·&nbsp; kind: `static`

The branch is still based on dev's tip; red means rebase before review.

**`test -f externals/work/crm-adv-alarm/tests/api3.alarm-socket.security.test.js -a -f externals/work/crm-adv-ala`** &nbsp;·&nbsp; kind: `static`

Both regression test files exist in the worktree.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- NO GATE RUNS THE SUITE, for the same reason as ADV-RETRO: it needs a
  my.test.env and a dedicated mongod whose nofile limit has been raised.
  Measured by hand on mongod 7.0.43, SHAPE B: 2311 passing / 3 pending / 0
  failing before, 2362 / 3 / 0 after, delta exactly the 51 alarm cases. The
  2311 is derived twice over and agrees: 2339-28 from the superseded shape-A
  run and 2362-51 from this one. Run against UNFIXED dev code the new tests
  go 29 passing / 22 failing, and the 29 that pass are the positive-delivery
  and REST-control assertions - which is what makes the 22 attributable to
  the defect rather than to the harness. FIVE ablations, each breaking one
  thing, each red for its own reason: A1 reverts the five to(ROOM) emits ->
  20 fail, symptom named on the never-subscribed socket, all 25 delivery
  assertions green; A2 forces the read check true -> 21; A3 forces
  entitlement true ONLY on the subscribe path -> exactly the 15
  unauthorized-subscriber cases plus the ack report, never-subscribed rows
  green; A4 removes the connect-time admission, i.e. REVERTS TO SHAPE A ->
  exactly the five [SHAPE B] cases, which is the regression guard for the
  maintainer's decision; A5 removes the ack guard -> 2. A1 and A3 are the
  two independently load-bearing halves. A suite asserting only non-delivery
  would sail through a too-tight room, so the value is in the delivery rows.
  FIVE CASES CHANGED THEIR EXPECTATION FROM SHAPE A and only those five - a
  never-subscribed socket on a readable instance must now RECEIVE. They are
  tagged [SHAPE B] in their names so a reviewer sees them in the runner
  output, and A4 proves they are the ones that go red if anyone re-tightens
  the room. Two cases were DELETED: anonymous REST controls against
  /api/v3/entries, which were wrong - v3 demands a bearer token on every
  value of AUTH_DEFAULT_ROLES, so they measured nothing.
- NO GATE COVERS THE CLIENT HALF. Nothing drives lib/client/hashauth.js
  against a live socket, and the client change is the part that could
  silently drop a real hypo alarm. Human verification required - see the
  review field.

## Evidence

- [`docs/60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md`](../../docs/60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md)
- [`docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md`](../../docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md)
- [`docs/30-design/remedial/security-advisory-disposition-2026-09-21.md`](../../docs/30-design/remedial/security-advisory-disposition-2026-09-21.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

REPRODUCED on v15.0.8 and dev 59430336, both arms, all FIVE event classes
(notification, announcement, alarm, urgent_alarm, clear_alarm), each caused
through the real server path - threshold crossings via POST /api/v1/entries
into simplealarms, treatment writes into treatmentnotify. No ctx.bus.emit was
used for any matrix cell. In every `denied` row the four v1 REST routes
answered 401 in the same process at the same moment; that is the control that
makes it a bypass rather than the documented default. Sharpest datum: under
`denied` the server answers a subscribing anonymous socket
{"success":true,...,"read":false,"ack":false} - it computes the correct
authorization decision, sends it to the client, and delivers everything
anyway. subscribe gates acknowledgement rights and nothing on the receive
side. The advisory's authenticationPromptOnLoad claim is CONFIRMED exactly:
the subscribe is refused, the socket is not disconnected, and it still
receives all five. Range >=15.0.0 is correct; 89d7eb679 is first contained in
tag 15.0.0. Turning careportal off via ENABLE= removes notification and
announcement by removing the feature, and alarm/urgent_alarm/clear_alarm still
arrive - so that is not a mitigation either. BF-80 IS THE COST OF THIS FIX AND
IS FILED AGAINST IT DELIBERATELY. Once delivery depends on a resolved
entitlement it inherits the failed-login delay list: a socket from an address
that recently failed an authentication sits outside the delivery room for the
accumulated penalty, 5 s per failure, and the list is keyed on the remote
address so a household behind one NAT address is one key. Measured on the
fixed build with the alarm fired 2 s after connect: 0 failures -> received at
2.0 s (clean control), 1 -> 4.9 s, 3 -> 10.0 s, 6 -> 15.0 s. A shape
assertion, not a threshold. NO shape of this fix avoids it - the pre-fix code
avoided it only by checking nothing - so it is not a reason to prefer a
different shape. Deliberately NOT fixed here: narrowing a brute-force control
needs its own change and its own review.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ADV-ALARM` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `59430336`.*
