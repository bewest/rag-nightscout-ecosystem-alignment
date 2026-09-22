# PR 1 — loadRetro

> **Record of what was sent — do not re-send.** Opened and merged into `dev` as
> nightscout/cgm-remote-monitor #8744 on 2026-09-21 (merged head `9765e8cd`: the measured commit, unchanged). Not released:
> `v15.0.8` does not carry it. The `## BODY` below is byte-identical to the live PR body
> (checked 2026-09-22). The invocation block is kept as the record of how it was opened; the
> worktree paths and `--body-file` names in it are local to the author's machine.

    repo   nightscout/cgm-remote-monitor
    base   dev
    head   bf/ws-loadretro-auth          (worktree externals/work/crm-adv-retro)
    commit 9765e8cd                      1 commit, 2 files, +242/-4
    closes GHSA-gjhc-pc29-r3m6           register BF-79

    gh pr create --repo nightscout/cgm-remote-monitor --base dev \
      --head bf/ws-loadretro-auth \
      --title "loadRetro answered any socket, including one authorize had just told it could not read" \
      --body-file PR-1-loadretro-dev.body.md

---
## TITLE
loadRetro answered any socket, including one authorize had just told it could not read

## BODY
The main Socket.IO namespace registered `loadRetro` with no authorization check of any kind. It
emitted the cached `devicestatus` array to whoever asked for it.

That namespace has seven handlers and **six of them do check**. `dbAdd`, `dbUpdate`,
`dbUpdateUnset` and `dbRemove` all answer `Not authorized` and write nothing — confirmed against
the collection rather than the reply string. `authorize` establishes the authorization. The
periodic `dataUpdate` goes to the `DataReceivers` room that only an authorized reader joins.
`loadRetro` was the one omission, which is both why it is easy to have missed and why it is
cheap to close.

### Who is affected, and who is not

**On the shipped `AUTH_DEFAULT_ROLES=readable` default: nobody, and this should not alarm anyone
running a default install.** Measured field by field against the same instance, every record id
the socket returned is in the anonymous `GET /api/v1/devicestatus.json` answer, no JSON field
path exists only on the socket, and REST returns *more* — 1730 records against the socket's 574.
The payload is a strict subset of what the site already serves the public by design.

**On an install that has closed anonymous access, it is an authorization bypass.** With
`AUTH_DEFAULT_ROLES=denied`, where `/api/v1/status.json`, `/entries.json`, `/devicestatus.json`
and `/treatments.json` all answered 401 in the same run, an unauthenticated socket that **never
sends `authorize`** received 576 device-status records: the loop suggestion block, pump battery
and reservoir, bolusing and suspended state, `pump.pumpID`, `pump.manufacturer`, `pump.model`,
`uploader.name` — usually a person's given name — and the rig hostname.

Three further measurements worth having in the record:

* **No setting stopped it.** `denied`, `status-only`, `AUTHENTICATION_PROMPT_ON_LOAD=true` and
  `TREATMENTS_AUTH=off` were each tested; all still returned 576. `DEVICESTATUS_DAYS=2` — the
  only knob that touches this path — **doubled** it to 1150.
* **It returned more than an authorized reader gets.** `authorize` trims to ten per
  device-and-type, so a legitimate reader's `dataUpdate` carried 20 records where the
  unauthenticated socket got 576.
* **The caller never invokes `authorize`.** Calling it with bad credentials disconnects the
  socket, so this was a gate to walk around rather than through — which is why auditing
  `authorize` finds nothing.

### What changed

`resolveReadAccess()` gates the handler on the authorization the file already computes.

A socket that authorized keeps the `socketAuthorization.read` it was given. One that never
authorized is resolved through `verifyAuthorization({}, remoteIP, …)` — the same function the
`authorize` handler calls — which takes `authorization.resolve()`'s `!authAttempted` branch and
returns the `AUTH_DEFAULT_ROLES` shiros the REST surface answers with. Refusal replies
`{result: 'Not permitted'}`, the string `checkConditions` already uses.

So an instance on the documented `readable` default keeps serving anonymous clients exactly as
before, and one on `denied` refuses here as it does everywhere else. **No new policy was
invented** — the clean way to ask "may this socket read?" already existed in the same file.

Verified not to interact with the failed-login throttle: an empty auth message takes the
`!authAttempted` branch and never reaches `addFailedRequest`, so a public instance cannot
throttle itself by accepting connections.

`loadedMills` is still ignored. Honouring it is a behaviour change with client-side consequences
and does not belong in a security fix.

### Evidence

`tests/websocket.loadretro-authorization.test.js`, 4 cases.

* **Ablation** — revert `lib/server/websocket.js`, keep the test, and the two negative cases go
  red printing the symptom itself: `expected {retroUpdate: true, canary: true, records: 1} to
  equal {retroUpdate: false, canary: false, records: 0}`. Canaried devicestatus arriving at a
  socket the server had already resolved as unable to read. The two positive cases stay green in
  the same ablated run, so it is red for the right reason.
* **Positive control, live** — on the `readable` default the fixed build still serves an
  anonymous client its 576 canaried records; on `denied`, an authorized reader still gets its
  570, from the same process seconds after it refused an anonymous socket.
* **Liveness** — every negative arm was re-run with the server's aliveness asserted in the same
  invocation, because a dead server answers a negative probe exactly like a fixed one.
* **Suite** — 2311 → 2315 passing, 3 pending, 0 failing. Delta is exactly the four new cases.

Reproduced on v15.0.7, v15.0.8 and `dev`, both authorization arms, against mongod 7.0.43. The
same commit also cherry-picks cleanly onto `v15.0.8` and the suite there goes 1533 → 1588, 0
failing, if a backport is ever wanted.

### Notes for the reviewer

* The advisory's affected range says `>0.8.1`. Measured, `loadRetro` is **absent** from tags
  0.8.1 through 0.8.4 and first appears in **0.9.0** — which is also the first tag carrying
  `DataReceivers` and `authDefaultRoles`, so the handler and the authorization it skips shipped
  in the same release. The advisory metadata is being corrected separately.
* This is independent of the `/alarm` fix in its sibling PR: disjoint files, `git merge-tree`
  clean, either order.
