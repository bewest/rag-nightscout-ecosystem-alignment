# PR 2 — /alarm namespace

    repo   nightscout/cgm-remote-monitor
    base   dev
    head   bf/alarm-socket-scope         (worktree externals/work/crm-adv-alarm)
    commit 012f1623                      2 commits, 4 files, +481/-18
    closes GHSA-8849-qjp5-vrrj           register BF-75, BF-76  (BF-80 filed, not fixed)

    gh pr create --repo nightscout/cgm-remote-monitor --base dev \
      --head bf/alarm-socket-scope \
      --title "Alarm delivery went to the whole namespace, so never subscribing was as good as subscribing" \
      --body-file PR-2-alarm-dev.body.md

---
## TITLE
Alarm delivery went to the whole namespace, so never subscribing was as good as subscribing

## BODY
`lib/api3/alarmSocket.js` `emitNotification()` delivered with `self.namespace.emit(...)` — the
whole namespace. Delivery was conditional on neither having subscribed nor being allowed to read.

`subscribe` *does* resolve authorization and *does* compute `read` from `api:*:read`. It then
used it only for acknowledgement rights. Under `AUTH_DEFAULT_ROLES=denied` the server replies to
an anonymous subscriber `{"success":true,…,"read":false,"ack":false}` and delivered everything
anyway: it computed the correct decision, sent it to the client, and ignored it.

All five classes were affected — `notification`, `announcement`, `alarm`, `urgent_alarm`,
`clear_alarm` — carrying carb entries, boluses, SMBs, temp basals, override changes and manual
glucose corrections.

### Who is affected, and who is not

**On the shipped `readable` default the marginal disclosure is zero in content**, and default
installs should not read this as new exposure. Measured field by field: dose, device, notes and
event type are in `treatments.json`; `debug.lastSGV` in `entries.json`; `debug.thresholds` in
`status.json`; `notifyhash`/`key` are sha1 over already-readable fields. What the socket adds
there is real-time push with no request rate and no access-log trace, plus a server-labelled
"hypo/hyper right now" that a poller would have to re-derive.

**On an install that has closed anonymous access it is an authorization bypass.** Reproduced on
v15.0.8 and `dev`, both arms, all five classes, each caused through the real server path —
threshold crossings via `POST /api/v1/entries` into `simplealarms`, treatment writes into
`treatmentnotify`. In every `denied` run the four v1 REST routes answered 401 in the same
process at the same moment; that is the control that makes it a bypass rather than the
documented default.

**No shipped setting stopped it.** `AUTHENTICATION_PROMPT_ON_LOAD=true` refuses the subscribe and
**does not disconnect the socket**, which still received all five. Turning careportal off via
`ENABLE=` removes `notification` and `announcement` by removing the feature; `alarm`,
`urgent_alarm` and `clear_alarm` still arrived. The namespace is mounted unconditionally, so no
flag removes it.

### What changed, and the shape choice behind it

`ROOM = 'AlarmReceivers'`, deliberately mirroring `DataReceivers` on the main namespace rather
than inventing a second mechanism. `applyReadEntitlement()` runs the same
`checkMultiple('api:*:read', …)` and joins or leaves the room. All five emits become
`self.namespace.to(ROOM).emit(...)`.

**The socket is admitted at connection time when the deployment's anonymous default role already
permits reading** — the same entitlement `AUTH_DEFAULT_ROLES` grants the REST surface — and the
decision is re-evaluated on `subscribe`.

That last part was a deliberate choice between two shapes and is the part most worth reviewing:

| | `readable` (default) | `denied` |
|---|---|---|
| **strict** — require subscribe *and* entitlement | never-subscribing client **stops receiving** | refused |
| **chosen** — admit at connect if the default role permits reading | unchanged, still receives | refused |

Both close the bypass. The `/alarm` protocol appears in no swagger file and nothing under
`docs/`, so any third-party client was written against observed behaviour — and the observed
behaviour is "connect and you get alarms". Since the marginal content disclosure on `readable`
is zero, the strict shape would break such a client for no confidentiality gain on the majority
configuration. The failure mode is a follower app silently not showing a hypo alarm, so the
conservative shape was chosen.

**Also in commit 1, and it is the part that could silently drop a real alarm.**
`client.subscribeForAlarms` had exactly one call site — the socket's `connect` handler — and
nothing re-subscribed when a viewer authenticated in the page. On a `denied` instance,
*load → refused → prompt → enter secret* left that socket in no room, receiving nothing, for the
one user who had just proved entitlement. `lib/client/hashauth.js` now re-runs it from
`updateSocketAuth`. The source was already asking for this at `alarmSocket.js:150`:
`// TODO: how will perms get updated after authorizing?`

Measured end to end on a live `denied` instance: connect and send nothing; announcement fired at
t=8s → nothing; subscribe with the API secret at t=16s → `{"success":true,"read":true}`; the
announcement arrives at t=16.9s and a bolus fired at t=24s arrives immediately. Server proven
alive throughout.

### Commit 2 — a second defect found while fixing the first

The access-token branch of `subscribe` registered `socket.on('ack', …)` with **no permission
check**, while the web-client branch beside it checks `notifications:*:ack`. `resolveAccessToken`
fails only for an unknown subject, so **any valid token of any role** reached
`ctx.notifications.ack(...)`, which silences the alarm for every viewer — with a caller-supplied
`silenceTime` that has no upper bound.

The authorization is fixed here. **The unbounded duration is deliberately left alone**: what a
legitimately authorized client may ask for is a product decision and should not ride along on an
authorization fix. It is recorded as an open item.

### Evidence

`tests/api3.alarm-socket.security.test.js` (49 cases) and `tests/api3.alarm-socket.ack.test.js`
(2). Suite 2311 → 2362 passing, 3 pending, 0 failing. Run against unfixed code the new tests go
29 passing / 22 failing, and the 29 that pass are the positive-delivery and REST-control
assertions — which is what makes the 22 attributable to the defect rather than to the harness.

The matrix the tests pin down, per event class:

| subscriber | `readable` | `denied` |
|---|---|---|
| connected, never subscribed | receives | refused |
| subscribed anonymously | receives | refused |
| subscribed with the API secret | receives | receives |
| token granting `api:*:read` | receives | receives |
| token granting only `api:*:create` | receives | **refused** |
| token granting nothing | receives | **refused** |

The last two rows are the point: a credential resolving is not the question, `api:*:read` is.
Each refusal is paired with a REST control on the same token in the same run — those tokens get
401 on `/api/v1/entries.json` while being refused alarms, so the socket and the REST surface now
say the same thing in both configurations.

**Five ablations, each breaking one thing:**

| | broken | result |
|---|---|---|
| A1 | the five `to(ROOM)` emits reverted to `namespace.emit` | 20 fail, symptom named on the never-subscribed socket; all 25 delivery assertions stay green |
| A2 | the `api:*:read` check forced true | 21 fail |
| A3 | entitlement forced true **only on the subscribe path** | exactly the 15 unauthorized-subscriber cases; never-subscribed rows stay green |
| A4 | connect-time admission removed, i.e. the strict shape | exactly the five cases that protect the default install |
| A5 | the `notifications:*:ack` guard removed | 2 fail, `expected 1 to be 0` |

A1 and A3 are the two independently load-bearing halves. A4 is the regression guard for the
shape choice.

### One known cost, recorded rather than hidden

Once delivery depends on a resolved entitlement it inherits the failed-login delay list. A socket
from an address that recently failed an authentication sits outside the delivery room for the
accumulated penalty — 5 s per failure, cumulative — and the list is keyed on the remote address,
so a household behind one NAT address is one key and a misconfigured uploader with a stale secret
delays the browser someone is watching. Measured on the fixed build with the alarm fired 2 s after
connect: 0 failures → received at 2.0 s, 1 → 4.9 s, 3 → 10.0 s, 6 → 15.0 s. It scales, so it is a
mechanism rather than a coincidence.

**No shape of this fix avoids it** — the pre-fix code avoided it only by checking nothing — so it
is not an argument for a different shape. Not addressed here: narrowing a brute-force control
needs its own change and its own review.

### Notes for the reviewer

* **There is a second fix in play.** The advisory's reporter opened one in GitHub's private
  advisory fork on 2026-09-18. Run against a live instance it does not close the bypass: it gates
  on `AUTHENTICATION_PROMPT_ON_LOAD` rather than `AUTH_DEFAULT_ROLES`, so on a hardened instance
  with the prompt flag at its default a never-subscribing socket still received everything; and
  where it does engage it never consults `api:*:read`, so a token granting only
  `api:treatments:create` heard every alarm while getting 401 on every REST read in the same run.
  **That is not a criticism of the reporter** — they found a real defect nobody here had, reported
  it responsibly and wrote a patch. The mistake is that this product has two
  authorization-shaped settings with adjacent names and only one is the access-control boundary.
  They are being credited on the advisory, and the settings documentation is a separate follow-up.
* One thing their shape does that this one does not: it *disconnects* an unauthenticated socket
  after a grace period rather than declining to deliver. That is a stronger posture and the
  argument is not one-sided; this PR matches the main namespace instead.
* Independent of the `loadRetro` fix in its sibling PR: disjoint files, `git merge-tree` clean,
  either order.
* Cherry-picks cleanly onto `v15.0.8` (suite there 1533 → 1588, 0 failing) if a backport is wanted.
