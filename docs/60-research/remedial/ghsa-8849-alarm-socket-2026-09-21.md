# GHSA-8849 — the `/alarm` Socket.IO namespace broadcasts to everyone connected

> **DISCLOSURE FIRST. Read this paragraph before quoting the rest anywhere public.** This is a
> **live unauthenticated disclosure of medical data on the shipping release** (`v15.0.8` =
> `origin/master`) and on `dev`, and **this repository is public**. The mechanism is stated below
> because an operator cannot act on a defect they cannot recognise, and because the fix is a
> three-line change they can read. **The working probes, the seeding script and the harness are
> held outside version control**, in the session scratchpad lab directory, and are not reproduced
> here. The upstream advisory (GHSA-8849-qjp5-vrrj) already carries a complete PoC; nothing here
> adds to it.

**Date:** 2026-09-21. **Agent:** ALARM. **Advisory:** GHSA-8849-qjp5-vrrj (draft, high, CWE-200 +
CWE-862). **Register entries:** BF-75 (the broadcast) and BF-76 (the `ack` path found beside it).

**Refs measured:** `dev` `59430336` (15.0.9) and `v15.0.8` (= `origin/master`, what operators run
today). **Storage:** `mongod 7.0.43` in docker. **Node:** v24.15.0. Every arm booted with `env -i`
so that only the variables named below reached the process.

---

## 1. The question this was run to answer

Ben West's framing for this advisory round: *were the correct feature flags enabled when these
advisories were evaluated?* `AUTH_DEFAULT_ROLES` defaults to `readable` (`lib/settings.js:39`) and
`README.md:243` documents that as "readable by anyone who knows the URL". On that default,
anonymous reads are **documented, intended behaviour**. A proof that shows anonymous access on a
default install has shown the default, not a vulnerability.

So the only question that decides whether this advisory is real is: **does the `/alarm` broadcast
survive `AUTH_DEFAULT_ROLES=denied`?**

It does. Measured, with the REST lockdown running in the same process as the control.

## 2. The mechanism

`lib/api3/alarmSocket.js`, unchanged between `v15.0.8` and `dev`:

- `:37` the namespace accepts every connection. No authorization is consulted at connect time.
- `:67` `self.subscribe` **does** resolve authorization, and computes
  `perms.read = ctx.authorization.checkMultiple('api:*:read', auth.shiros)` — then returns that
  boolean **to the client** and never uses it on the server.
- `:178` `emitNotification` delivers with `self.namespace.emit(...)` — the whole namespace.

Delivery is therefore not conditional on having subscribed, and not conditional on being allowed to
read. The server computes the right answer and discards it.

By contrast the main namespace already does this correctly: `lib/server/websocket.js:791-792`
checks the same `api:*:read` permission and calls `socket.join('DataReceivers')`, and
`:150` emits `dataUpdate` with `io.to('DataReceivers')`. The pattern the alarm socket needed
already existed, twelve hundred lines away, in the same server.

## 3. The measured matrix

Five event classes, each **driven through the real server paths** — no direct `ctx.bus.emit` was
used for any cell in this table. `alarm` / `urgent_alarm` / `clear_alarm` were caused by POSTing
SGV entries across the configured thresholds (`simplealarms`); `notification` and `announcement` by
POSTing treatments to `/api/v1/treatments` with the `api-secret` header (`treatmentnotify`).

Thresholds were set explicitly (`BG_HIGH=260 BG_TARGET_TOP=180 BG_TARGET_BOTTOM=80 BG_LOW=55`)
because `lib/settings.js:251` selects `ar2` rather than `simplealarms` when no threshold was ever
set; this makes the crossing deterministic and does not touch the delivery path, which is
downstream of both plugins at `ctx.bus.on('notification')`.

Socket **A** is the advisory's claim: unauthenticated, **never sends `subscribe`**.

| ref | arm | anon REST (`status`/`entries`/`treatments`/`devicestatus`) | A gets `notification` | `announcement` | `alarm` | `urgent_alarm` | `clear_alarm` |
|---|---|---|---|---|---|---|---|
| `v15.0.8` | R (`readable`, shipped default) | 200 / 200 / 200 / 200 | **yes** | **yes** | **yes** | **yes** | **yes** |
| `v15.0.8` | D (`AUTH_DEFAULT_ROLES=denied`) | **401 / 401 / 401 / 401** | **yes** | **yes** | **yes** | **yes** | **yes** |
| `dev` `59430336` | R | 200 / 200 / 200 / 200 | **yes** | **yes** | **yes** | **yes** | **yes** |
| `dev` `59430336` | D | **401 / 401 / 401 / 401** | **yes** | **yes** | **yes** | **yes** | **yes** |

The 401 column is the control that makes the rest mean something: in arm D the REST surface is
genuinely locked, in the same process, at the same moment, for the same anonymous caller.

Representative payloads, arm D, `dev` (synthetic lab data only):

```
alarm         {"level":1,"title":"Warning LOW","message":"BG Now: 70 → mg/dl",
               "eventName":"low","plugin":{"name":"simplealarms",...},
               "debug":{"lastSGV":70,"thresholds":{"bgHigh":260,"bgTargetTop":180,
                        "bgTargetBottom":80,"bgLow":55}},"group":"default"}
urgent_alarm  {"level":2,"title":"Urgent LOW","message":"BG Now: 50 → mg/dl",...}
clear_alarm   {"clear":true,"title":"All Clear","message":"Auto ack'd alarm(s)","group":"default"}
notification  {"level":0,"title":"Bolus",
               "message":"\nInsulin: 0.35U\nEntered By: LabPump\nNotes: LAB-CANARY-BOLUS",
               "plugin":{"name":"treatmentnotify",...},"notifyhash":"73bcd4…","group":"default"}
announcement  {"level":0,"title":"Announcement","message":"LAB-CANARY-ANNOUNCE",
               "isAnnouncement":true,"group":"Announcement"}
```

### 3a. The server says "no" and delivers anyway

The same runs carried socket **B**: unauthenticated, but it *does* send `subscribe` with an empty
message. Its acknowledgement is the finding in one line.

| ref / arm | B's `subscribe` acknowledgement | events B received |
|---|---|---|
| `dev` / R | `{"success":true,"message":"Subscribed for alarms","read":true,"ack":false}` | all five |
| `dev` / D | `{"success":true,"message":"Subscribed for alarms","read":false,"ack":false}` | **all five** |
| `v15.0.8` / D | `{"success":true,"message":"Subscribed for alarms","read":false,"ack":false}` | **all five** |

`read:false` is the server's own authorization decision, correctly computed from
`AUTH_DEFAULT_ROLES=denied`, transmitted to the client, and then ignored.

## 4. Is there any shipped setting that stops it?

**No.** Measured, not inferred.

| setting | tested as | anon REST | did A still receive? |
|---|---|---|---|
| `AUTH_DEFAULT_ROLES=denied` | arm D above | 401 | **yes — all five** |
| `AUTHENTICATION_PROMPT_ON_LOAD=true` (with `denied`) | `dev`, port isolated | 401 | **yes — all five** |
| `ENABLE=` (careportal off ⇒ `treatmentnotify` off, with `denied`) | `dev` | 401 | **yes — `alarm`, `urgent_alarm`, `clear_alarm`**; `notification` and `announcement` no longer fire at all |

The advisory's claim about `authenticationPromptOnLoad` is **confirmed exactly**: with it enabled,
socket B's subscribe is refused — `{"success":false,"message":"Missing or bad accessToken"}` — the
socket is **not** disconnected, and it receives all five event classes anyway. The setting changes
what `subscribe` answers; it does not change who `emit` reaches, because nothing about delivery
consults `subscribe` at all.

The `ENABLE=` row is included to close the "just turn the feature off" escape. Turning careportal
off removes the treatment-derived subset by removing the notifications themselves — it is a
feature removal, not a control — and the three alarm classes, the ones that reveal a hypo in real
time, still reach an anonymous never-subscribed socket.

Candidates checked and rejected without a run, because the code makes the answer structural:
`lib/api3/index.js:113` constructs the alarm socket unconditionally, and `lib/server/app.js:294`
mounts api3 unconditionally, so there is no flag that removes the namespace. `SHOW_PLUGINS` is a
client-side display list. `PUSHOVER_*` selects an additional *outbound* notifier and cannot
subtract from the socket path. `ALARM_*` / `BG_*` decide whether an alarm fires, not who hears it.

## 5. What does `subscribe` actually gate, then?

**Acknowledgement rights, and nothing on the receive side.** That is the whole of it.

Reading `self.subscribe` (`lib/api3/alarmSocket.js:67-170`), a successful subscribe has exactly two
server-side effects: it registers a `socket.on('ack', …)` handler, and it returns a response object
to the client. In the web-client branch the ack handler is guarded by a captured
`perms.ack = checkMultiple('notifications:*:ack', …)`. `perms.read` is computed in the same
expression, placed in the response, and never referenced again.

So an authorized subscriber gets, over an unauthenticated listener, the ability to **silence**
alarms. It gets nothing extra in what it receives. The defect is exactly the shape that describes:
the authorization decision exists and is correct, and the delivery path never asks for it.

### 5a. A second defect in the same function — the `ack` path

The native-client branch (`:71-95`, entered when the client sends `message.accessToken`) registers
`socket.on('ack', …)` with **no permission check at all**. `resolveAccessToken` fails only when the
subject is unknown, so **any valid access token, of any role, including one with no permissions**,
can call `ctx.notifications.ack(level, group, silenceTime, true)`. `lib/notifications.js:160-173`
takes `silenceTime` straight from the caller with no upper bound and applies it globally:
`alarm.silenceTime = time ? time : THIRTY_MINUTES`.

A read-only token holder can therefore silence every alarm on the instance, for an arbitrary
duration, for every viewer. This is not what the advisory reports, it is in the function the
advisory points at, and it is filed and fixed alongside it as a separate commit.

## 6. The main namespace — checked, and clean for notifications

`lib/server/websocket.js` has no notification delivery of its own: notifications reach clients only
through `/alarm`. Its own broadcasts are `io.to('DataReceivers').emit('dataUpdate', …)` at `:150`,
which is room-scoped behind the `api:*:read` check at `:791`, and `io.emit('clients', n)` at
`:161-163`, which carries an integer count of connected viewers and no patient data.

(`loadRetro`/`retroUpdate` at `:319` is a separate finding under GHSA-gjhc-pc29-r3m6 and is agent
RETRO's; it was not touched here.)

## 7. Marginal disclosure on the shipped default — measured, and it is small

On `AUTH_DEFAULT_ROLES=readable` the same treatments are anonymously readable at
`GET /api/v1/treatments.json` moments later. The honest question is what the push adds. Field by
field, against the REST records fetched from the same instance in the same run:

| field in the `notification` payload | present in anonymous REST on `readable`? |
|---|---|
| `title` (the event type) | yes — `treatments.json` `eventType` |
| `message` → `Insulin: 0.35U` | yes — `treatments.json` `insulin` |
| `message` → `Entered By: LabPump` | yes — `treatments.json` `enteredBy` |
| `message` → `Notes: LAB-CANARY-BOLUS` | yes — `treatments.json` `notes` |
| `notifyhash` / `key` | derived — sha1 over `eventType` + `timestamp`, both already readable |
| `plugin` | static plugin metadata, no patient data |
| `alarm.debug.lastSGV` | yes — `entries.json` |
| `alarm.debug.thresholds` | yes — `status.json` `settings.thresholds` (measured: returns all four) |

**No field in any of the five payloads is absent from the anonymous REST surface of a `readable`
install.** The marginal disclosure on the shipped default is therefore not *what*, it is *when* and
*how cheaply*:

- **Push versus poll.** A passive listener holds one socket and learns of a bolus, a carb entry, an
  override, an automatic SMB or a hypo alarm at the instant it happens, with no polling, no request
  rate to notice, and nothing in an access log to look at. Reconstructing the same timeline by
  polling `treatments.json` needs sustained requests against a specific URL.
- **The alarm classes have no polling equivalent at all.** `alarm` and `urgent_alarm` are the
  server's own judgement that this person is in a hypo or hyper event *right now*. A poller would
  have to re-derive that from `entries.json` plus `status.json`; the socket hands it over, labelled.

On `readable`, then, this is an amplification of a documented exposure, not a new one. That
distinction is what stops it from being graded twice.

## 8. Affected range

`89d7eb6790707f273874191c6ff4f1ae216f9127` — "Alarm sockets for api v3 (#7858)".

```
$ git tag --contains 89d7eb679 | head
15.0.0 15.0.1 15.0.2 15.0.3 15.0.4 15.0.5 15.0.6 15.0.7 15.0.8 v15.0.4 …
```

The earliest tag containing it is **15.0.0**, so the advisory's `>=15.0.0` is **correct as
written**. The first affected *release* is **15.0.0**; the current shipping release `v15.0.8` is
affected, and `dev` `59430336` is affected. There is no patched version.

## 9. Severity, derived twice

The advisory carries a bare "high" with no vector. Deriving one requires deciding which
configuration is being scored, and the two configurations are genuinely different findings.

**On a hardened install (`AUTH_DEFAULT_ROLES=denied`)** — a real CWE-862 authorization bypass. The
operator set the one documented control that denies anonymous reads, the REST surface obeys it
(401, measured), and the alarm stream ignores it. No privileges, no interaction, remote, one
socket.

```
CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N   7.5 High
```

`C:H` is a judgement and is worth stating rather than asserting. The letter of the CVSS 3.1
definition of `Low` — "the attacker does not have control over what information is obtained" — fits
a passive listener. `High` is chosen because the information is identified-individual health data:
the instance URL names the person, and the stream carries their glucose emergencies and their
insulin doses. Anyone re-scoring this to `C:L` (5.3) should say so explicitly rather than let it
drift.

**On the shipped default (`AUTH_DEFAULT_ROLES=readable`)** — the marginal disclosure measured in
§7 is timeliness, not content.

```
CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N   5.3 Medium
```

and a defensible strict reading is `C:N` / **0.0**, since no field is disclosed that
`GET /api/v1/treatments.json` does not already return to the same anonymous caller. `C:L` is
preferred over `C:N` on the strength of the real-time alarm labelling, which has no REST
equivalent.

**The advisory should carry the 7.5.** It describes the defect across all configurations, and the
configuration where it is a boundary violation is the one that decides the class. Note that this is
*derived here and differs from the sibling advisory's 8.2*, which was not copied.

The `ack` defect of §5a is scored separately: it needs a valid token, so
`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:H` — **7.3 High** on the argument that indefinitely
silencing a diabetes alarm is loss of availability of the safety function this software exists to
provide. It is not part of GHSA-8849 as filed.

## 10. The fix

Branch `bf/alarm-socket-scope` off `origin/dev` `59430336`, in the ALARM worktree. Not pushed.

**Commit 1 — scope delivery to entitled sockets.** `lib/api3/alarmSocket.js`:

- add `ROOM = 'AlarmReceivers'`;
- add `applyReadEntitlement(socket, shiros)`, which computes the same
  `checkMultiple('api:*:read', …)` the main namespace uses and calls `socket.join(ROOM)` or
  `socket.leave(ROOM)`;
- call it from **both** `subscribe` branches after authorization resolves, and **once at
  connection time** with the deployment's anonymous default role;
- change all five `self.namespace.emit(...)` calls to `self.namespace.to(ROOM).emit(...)`.

This is deliberately the `DataReceivers` pattern from `lib/server/websocket.js:791`, not a second
mechanism: same permission string, same join-on-authorize shape, same room-scoped emit. The
`leave` on the negative branch is what makes a re-subscribe after logging out take effect.

**The connect-time admission is the shape decision of §12 and is the whole design question.** The
socket is admitted as soon as it connects *if the deployment's anonymous default role already
permits reading* — exactly the entitlement `AUTH_DEFAULT_ROLES` grants the REST surface to the
same anonymous caller — and re-evaluated on every `subscribe`:

```js
ctx.authorization.resolve({ api_secret: null, token: null, ip: remoteIP }
  , function resolvedDefault (err, auth) {
      if (err || !auth || hasSubscribed) { return; }
      applyReadEntitlement(socket, auth.shiros);
    });
```

On `AUTH_DEFAULT_ROLES=denied` the anonymous default permits nothing, so the socket joins no room
and the bypass is closed. On the shipped `readable` default it permits everyone, so a client that
connects and never subscribes receives exactly what it has received since 15.0.0 — **no client
behaviour changes on the majority configuration**. That is measured, not argued: §11, the
`readable` rows.

Two properties of `resolve` were checked in `lib/authorization/index.js` before calling it on
every connection, because both could have made this worse than the defect:

- **It records no failed-request penalty on this path.** With neither secret nor token,
  `authAttempted` is false and `resolve` returns `defaultShiros` from the `!authAttempted` branch
  at `:165`, before `addFailedRequest` at `:210` is reachable. A public instance therefore cannot
  put itself on its own failed-login delay list by accepting connections.
- **It is `async` and consults `shouldDelayRequest(data.ip)` first (`:155`).** When that returns
  false — the ordinary case — no `await` executes, the callback runs synchronously inside the
  connection handler, and nothing about connecting is slower than before. When the IP *is* on the
  delay list, `resolve` awaits `sleep(requestDelay)`. Nothing blocks: the connection handler does
  not await the call, so the handshake completes and the socket is simply admitted late. What it
  means is that an address that recently failed an authentication is not in the delivery room for
  up to `AUTH_FAIL_DELAY` (5 s by default, cumulative per failure). The `hasSubscribed` guard
  above exists for the consequence of that deferral and is discussed in §12c.

**Commit 1 also touches `lib/client/hashauth.js`**, and this is the part that deserves scrutiny
rather than the server change. `client.subscribeForAlarms` is called from exactly one place,
`lib/client/index.js:1179`, the alarm socket's `connect` handler. Nothing re-subscribes after the
user authenticates in the page. Under the old namespace-wide broadcast that did not matter. Under
room-scoped delivery it matters completely, **and it still matters under shape B**, because a
`denied` instance refuses the socket at connect exactly as it would have under shape A: a viewer
who loads the page, gets the prompt and enters the secret would have joined no room and would
receive **no alarms until the socket reconnected**. So `hashauth.updateSocketAuth()` — the
existing "my credentials changed" hook, already called on both authentication paths — now also
re-runs `client.subscribeForAlarms()`. The source already carried the author's own note at
`alarmSocket.js:150`: *"TODO: how will perms get updated after authorizing?"*

**Commit 2 — the `ack` path.** Compute `notifications:*:ack` in the access-token branch too and
guard the handler with it, matching the web-client branch.

## 11. Non-vacuity

**The regression test.** `tests/api3.alarm-socket.security.test.js`, **49 cases**, two instances in
one file (`authDefaultRoles: 'denied'` and `'readable'`), nine sockets, all five event classes
asserted independently so a test that only ever exercised the `INFO` branch cannot pass for the
other four. It emits on `ctx.bus`, which is precisely where `emitNotification` is registered; the
end-to-end plugin paths are covered by the live matrix below and in §3.

The matrix it pins, per event class:

| socket | `readable` (shipped default) | `denied` |
|---|---|---|
| connected, **never subscribed** | **receives** | refused |
| subscribed anonymously (no secret, no token) | receives | refused |
| subscribed with the API secret | receives | **receives** |
| subscribed with a token granting `api:*:read` | — | **receives** |
| subscribed with a token granting only `api:*:create` | — | refused |
| subscribed with a token granting nothing | — | refused |

The last two rows are the distinction that matters and it is easy to get wrong: **"a credential
resolved" is not the question, `api:*:read` is.** A gate that admits anything `resolveAccessToken`
accepts lets a write-only credential hear every alarm on the instance. The test takes the REST
answer for those same tokens in the same run as its control — 200 for the reading token, 403 for
the other two, with `api:entries:read` named in the refusal.

(The anonymous control is *not* taken from API v3, which demands a bearer token unconditionally
in `lib/api3/security.js` and so answers 401 on every value of `AUTH_DEFAULT_ROLES`. For the
anonymous rows the control is the v1 surface, measured on live instances below, and the server's
own `read` boolean in the subscribe acknowledgement.)

The `ack` commit adds `tests/api3.alarm-socket.ack.test.js`, 2 cases.

**Before the fix**, with these 51 cases run against `origin/dev` `59430336`'s
`lib/api3/alarmSocket.js` and `lib/client/hashauth.js`: **29 passing, 22 failing**. The 29 that
pass are the positive-delivery and REST-control assertions — an entitled subscriber already
received all five classes — which is what makes the 22 attributable to the defect rather than to
the harness. **After the fix: 51 passing, 0 failing.**

**Five ablations, because a green ablation has two meanings and they are opposite.** Each one
breaks the fixed tree in exactly one place and runs both alarm test files.

| ablation | what was broken | result | symptom observed |
|---|---|---|---|
| **A1** | the five `self.namespace.to(ROOM).emit(...)` reverted to `self.namespace.emit(...)` | **31 passing, 20 failing** | `expected Array [ Object { event: 'urgent_alarm', message: 'canary-urgent' } ] to be empty` on the **never-subscribed** socket under `denied`, and the same for each of the other four classes and each of the other three refused sockets. The original symptom — a payload arriving where it must not — named in the failure, not "an error". All 25 delivery assertions stayed green |
| **A2** | `applyReadEntitlement`'s `checkMultiple('api:*:read', …)` forced `true` | **30 passing, 21 failing** | the same 20, plus `expected true to be false` on the acknowledgement's `read` field. Under shape B this single check governs both the connect-time admission and the subscribe path, so it is broader than A1 by exactly one case — that is a property of the shape and is why A3 exists |
| **A3** | the entitlement forced `true` **only on the subscribe path**, connect-time admission untouched | **35 passing, 16 failing** | exactly the 15 unauthorized-*subscriber* cases (anonymous, write-only token, no-permission token) plus the acknowledgement case. **The never-subscribed rows stayed green.** This is what isolates the subscribe half from the connect half |
| **A4** | the connect-time admission removed entirely — i.e. the tree reverted to **fix shape A** | **46 passing, 5 failing** | exactly the five `[SHAPE B]` cases, `expected Array [] to have property length of 1 (got 0)`: a never-subscribing client on the shipped `readable` default stops receiving. This is the regression guard for the decision in §12 |
| **A5** | the `notifications:*:ack` guard removed | **49 passing, 2 failing** | `expected 1 to be 0` — the read-only token's ack reached `ctx.notifications.ack` |

A1 and A3 together are the point: the two halves of the fix — *room-scoped delivery* and *the read
entitlement* — are independently load-bearing, and breaking either produces the specific wrong
outcome it is there to prevent, not a generic failure. A4 is the point of §12: it shows the
connect-time admission is load-bearing for the *delivery* property the decision was taken to
protect, and that a future tightening of the room would be caught.

**Live positive control, on the real paths, not the bus.** Three instances against
`mongod 7.0.43`, each booted with `setsid nohup … < /dev/null &` so nothing reaps them mid-run;
all five classes driven through `POST /api/v1/entries` and `POST /api/v1/treatments`. Six probe
sockets per instance in one run.

**Liveness is asserted for every negative cell.** Each probe also holds an unauthenticated socket
on the *main* namespace, which always receives the `clients` event (an integer viewer count, no
patient data). `clients` seen + payload absent = a live server refusing the probe; nothing at all
= a dead server, which answers every negative probe exactly like a fixed one. Every refusal below
carries at least one `clients` event from the same process in the same run.

| probe | v15.0.8, `denied` (control) | fixed, `denied` | fixed, `readable` |
|---|---|---|---|
| anon v1 `entries.json` | 401 | 401 | 200 |
| connected, never subscribes | **all five** | **refused** (liveness 5) | **all five** |
| subscribes anonymously | **all five** (`read:false`) | **refused** (liveness 4, `read:false`) | all five (`read:true`) |
| subscribes with the API secret | all five | **all five** (`read:true, ack:true`) | all five |
| token granting `api:*:read` (v1 REST: 200) | all five | **all five** | all five |
| token granting only `api:*:create` (v1 REST: 401 / 200) | **all five** | **refused** (liveness 6) | all five |
| token granting nothing (v1 REST: 401 / 200) | **all five** | **refused** (liveness 2) | all five |

The shipping-release column is the control that the harness can see delivery at all: on v15.0.8
every one of the six probes received every class while v1 REST answered 401 to three of them.

The two right-hand columns are the fix. On `denied`, only credentials that may *read* receive —
the write-only and no-permission tokens are refused the alarm stream and refused the same data by
REST in the same run. On `readable` **every probe still receives everything**, including the one
that never subscribes: the deployment has granted anonymous read and the socket follows it,
exactly as the REST column does (200 for all four callers). That consistency between the two
surfaces is the whole of shape B.

**Main namespace, re-confirmed independently in this session** on `v15.0.8` with `denied`, while
the same seeding ran: an unauthenticated socket that never sent `authorize` saw exactly one event
in 45 seconds — `clients 1` — and no `dataUpdate` and no notification of any kind.

**Full suite**, `NODE_ENV=test npm test`, `mongod 7.0.43` on a container recreated with
`--ulimit nofile=64000`:

| tree | passing | pending | failing |
|---|---|---|---|
| `origin/dev` `59430336` (derived, see below) | 2311 | 3 | 0 |
| the earlier shape-A branch tip (measured) | **2339** | 3 | 0 |
| `bf/alarm-socket-scope`, shape B (measured) | **2362** | 3 | 0 |

+51 = the reworked delivery-scope file, +2 = the ack file. The 2311 baseline is derived from two
measured runs that agree: 2339 − 28 and 2362 − 51 both give 2311.

**An environment finding that nearly corrupted this result.** The first baseline run reported
2248 passing / 12 failing. It was discarded: the `mongod` container had died mid-run with
`Fatal assertion 50853` after `Location13538: couldn't open [/proc/1/stat] Too many open files`.
The container's soft `RLIMIT_NOFILE` was **1024**, the docker default when none is given, and the
suite's create-and-drop-database pattern exhausts it. Recreated with `--ulimit nofile=64000`, the
same tree ran clean in a third of the wall time. Every number above is from after that. This is a
lab defect, not a Nightscout defect, but it is the kind that produces a confidently wrong "12
failing" baseline, so it is recorded.

## 12. The risk that this fix drops a legitimate alarm — and the shape decision, taken

This deserves its own section, because these events are how a caregiver learns about a hypo, and a
fix that silences one is worse than the defect it closes.

### 12a. The decision

Two shapes were prepared, and each was run against live instances rather than argued about. The
comparison is kept here as the record of what was weighed.

| | **shape A** — subscribed **and** entitled | **shape B** — entitled, admitted at connect |
|---|---|---|
| when a socket joins the delivery room | only on a successful `subscribe` whose resolved shiros include `api:*:read` | at **connection**, if the deployment's anonymous default role already permits reading; re-evaluated on every `subscribe` |
| `denied`, anonymous, never subscribes | refused | refused |
| `denied`, anonymous, subscribes | refused | refused |
| `denied`, token that resolves but cannot read | refused | refused |
| **`readable` (shipped default), never subscribes** | **refused — a behaviour change on the majority configuration** | **receives, exactly as since 15.0.0** |
| the shipped web client | unaffected — it subscribes on connect | unaffected |
| lines of code | fewer | one `resolve` call and a guard |

**The decision is shape B, taken 2026-09-21 by Ben West.** Two reasons, in order:

- **On the shipped default, A buys nothing measurable and costs something unmeasurable.** §7
  measured the marginal content disclosure of the broadcast on `readable`, field by field, and it
  is **zero**: nothing in any of the five payloads is absent from `treatments.json`,
  `entries.json` or `status.json` for the same anonymous caller. Requiring `subscribe` there
  removes no disclosure. What it removes is delivery, to any client that connects and does not
  subscribe.
- **Those clients cannot be enumerated.** The `/alarm` protocol appears in no swagger document and
  in no file under `docs/`. Third-party implementers had only the observed behaviour to work
  from, and for five releases the observed behaviour was that connecting is enough. There is no
  way to count them from inside this repository, and the failure mode if one exists is silent:
  it stops receiving hypo alarms and nothing anywhere says so.

B closes the `AUTH_DEFAULT_ROLES=denied` bypass identically to A. Both were measured doing so, on
live instances, for all five event classes — §11.

**The fact that would have argued for A, recorded because it was set aside deliberately.** Ben
separately judged that the first-party web client is in practice the only consumer of `/alarm` —
and the web client subscribes on connect, so shape A would have broken nothing. **He chose B
anyway, as insurance against that judgement being wrong.** The asymmetry is the argument: if the
judgement is right, B costs a few lines and no security; if it is wrong, A costs somebody an
alarm they needed, silently, and the person who finds out is the person who did not wake up. A
reviewer who shares the judgement would otherwise reasonably ask why the stricter shape was not
taken, so the answer is written down rather than left implicit.

This decision is also what §13 was waiting on: it does not change the advisory's severity or
range, only the patch that will eventually be offered.

### 12b. What shape B costs, measured

One extra `ctx.authorization.resolve({ api_secret: null, token: null, ip })` per `/alarm`
connection. Both of the ways that could have hurt were checked in `lib/authorization/index.js`:

- **No self-inflicted throttling.** With neither secret nor token, `authAttempted` is false and
  `resolve` returns the default shiros from the `!authAttempted` branch at `:165`. It never
  reaches `addFailedRequest` at `:210`, which is the only failure record on that function. A
  public instance therefore cannot put itself on its own failed-login delay list by accepting
  connections, however many it accepts.
- **No new per-connection await in the ordinary case.** `resolve` is `async` and consults
  `shouldDelayRequest(data.ip)` first (`:155`), but when that returns false no `await` executes:
  an async function body runs synchronously up to its first `await`, so the callback fires inside
  the connection handler and connecting is no slower than before. When the IP *is* on the delay
  list, `resolve` awaits `sleep(requestDelay)`. Nothing blocks — the connection handler does not
  await the call, so the handshake completes normally and the socket is merely admitted late.

  **The real consequence is worth stating plainly:** on an address that has recently failed an
  authentication, a `/alarm` socket is outside the delivery room for up to `AUTH_FAIL_DELAY`
  (5 s by default, and cumulative per failure), and any alarm fired in that window is not
  delivered to it. This is a NAT-sharing hazard as much as an attacker one — a household
  uploader misconfigured with a wrong API secret puts the household's public IP on that list, and
  a browser reconnecting from the same address is admitted late. It is **not new to shape B**:
  the subscribe path has always resolved through the same delay, so any room-scoped fix inherits
  it. Shape B widens it from "clients that subscribe" to "all clients". It is recorded here as a
  known cost rather than fixed, because changing the throttle is a separate decision about the
  failed-login control and should not ride along on an authorization fix.

### 12c. The ordering hazard the connect-time admission introduces, and the guard for it

Because the connect-time `resolve` can be deferred, its callback can in principle land *after* a
`subscribe` carrying real credentials has already been answered — and applying the anonymous
default at that point would call `socket.leave(ROOM)` on an authorized viewer. That is the exact
failure this whole section exists to prevent, arriving through the fix rather than the defect.

Read carefully, it is **not reachable today**: every pending delay for an IP wakes at one common,
non-decreasing deadline, in timer-creation order, so a `subscribe` issued after the connect-time
call always resolves after it. But that is an implicit invariant of `lib/authorization/delaylist.js`,
a module the alarm socket does not own, and the cost of not depending on it is one boolean. The
connect-time callback therefore returns early if a `subscribe` has already been seen:
an explicit credential is the more specific answer and the anonymous default must never overwrite
it. Stated here rather than only in the code comment, because "defensive against an invariant we
do not own" is the kind of thing a reviewer should be able to accept or reject on purpose.

### 12d. The client half is still required under B, and this is why

`subscribeForAlarms` is called from exactly one place — `lib/client/index.js:1179`, the alarm
socket's `connect` handler — and nothing re-subscribes when the viewer authenticates in the page.

Shape B does **not** remove this problem, and it would be easy to assume it does. On a `denied`
instance the connect-time admission refuses the socket, because the anonymous default permits
nothing there; that is the point of the fix. So the sequence *load page → server refuses → prompt
→ enter secret* still leaves the socket in no room, receiving nothing, until it happens to
reconnect — a silent, indefinite loss of alarms for the exact user who has just proved they are
entitled to them.

**Measured directly on the fixed `denied` instance**, as the page sequence rather than as an
argument. One socket: connect and send nothing; fire an announcement eight seconds later;
subscribe with the API secret at sixteen seconds, which is what `updateSocketAuth` now does; fire
a bolus at twenty-four.

```
 0.0s  LIVENESS main `clients` = 1
 0.0s  CONNECTED /alarm, sending nothing
       (announcement fired at 8s)          -> received before subscribe: 0
16.0s  user enters the API secret -> re-subscribing
16.0s  subscribe reply: {"success":true,"read":true,"ack":true}
16.9s  <<< announcement   LAB-CANARY-ANNOUNCEMENT
24.0s  <<< notification   Insulin: 0.45U | Entered By: LabPump | LAB-CANARY-BOLUS
```

Nothing before the re-subscribe, everything after it, on a server proven alive throughout by the
main namespace's `clients` event. Without the `hashauth` change there is no re-subscribe and that
socket stays on the first line for as long as the page is open. That is why the fix touches
`hashauth.updateSocketAuth`. Under the old broadcast this bug was invisible; room-scoping
is what makes it matter, under either shape. Anyone reviewing the server change in isolation would
ship it.

### 12e. What the tests catch, and the one thing they cannot

**The test that would catch a dropped alarm** is the one in §11, and its value is entirely in the
rows that assert *delivery*: `readable`-never-subscribed, `readable`-anonymous-subscriber,
`readable`-secret, `denied`-secret and `denied`-reading-token, for each of the five classes
independently. A regression that scoped the room too tightly — wrong permission string, `join` on
the wrong branch, a `leave` that fires when it should not, or simply reverting to shape A — turns
those assertions red; ablation A4 demonstrates precisely that. A suite that only asserted
non-delivery would sail through all of it. That asymmetry is why the file asserts both directions
for every event class rather than checking "an alarm arrives" once.

What the tests **cannot** catch is the client-side half. There is no test that a browser which
authenticates mid-session starts receiving alarms again, because there is no harness that drives
`hashauth` against a live socket. That gap is stated rather than papered over, and it remains the
single thing most worth a human's manual check before this ships: load a `denied` instance,
authenticate at the prompt, force an alarm, confirm it arrives.

### 12f. A note for anyone comparing this with the reporter's proposed patch

The reporter's own proposed fix is evaluated separately and by running it, in
[the reporter-PR evaluation](./ghsa-8849-reporter-pr-evaluation-2026-09-21.md); what follows is
only the shape-level difference a reviewer sees in the two diffs.

A fix for this defect can decline to *deliver* to an unentitled socket, which is what the branch
here does, or it can *disconnect* the socket after a grace period. The tradeoff is worth naming
because it is visible in a diff and its consequences are not. Disconnecting gives an unentitled
client an unambiguous signal instead of silence, which is friendlier to an integrator; but a
Socket.IO client's default behaviour is to reconnect, so on a hardened instance it converts a
quiet refusal into a reconnect loop, and a grace period is a window in which delivery still
happens. Declining to deliver has neither property and needs no timer, at the cost of telling the
client nothing it did not already learn from `read:false` in the subscribe acknowledgement. The
substantive question is not which of the two, though: it is **what the gate keys on**. This branch
keys on `api:*:read` resolved from `AUTH_DEFAULT_ROLES` — the same permission and the same setting
the REST surface obeys — and the `denied` rows of §11 are there to prove it, including the two
token rows where a credential resolves perfectly well and still may not read.

## 13. Recommendation for the advisory

Keep the report, raise its precision, and set the fields it is missing. The finding is real and the
reporter's mechanism is correct in every particular, including the `authenticationPromptOnLoad`
claim, which was tested and behaves exactly as described. Two things should change. **Add the
vector** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N` (7.5) and say in the text that it scores
the hardened configuration, because on the shipped `AUTH_DEFAULT_ROLES=readable` default every
field in every payload is already returned to the same anonymous caller by
`GET /api/v1/{treatments,entries,status}.json` — measured field by field — so what the socket adds
there is real-time push and a server-labelled hypo/hyper signal, not new content. Saying that
plainly makes the advisory *more* credible, not less, and it stops an operator on the default from
concluding they are exposed to something they are not. **And state the boundary being crossed:**
the defect is that `AUTH_DEFAULT_ROLES=denied`, the one documented control that turns off anonymous
access, is honoured by the REST surface and ignored by the alarm stream — that sentence is the
advisory, and the treatment table is its evidence. The affected range `>=15.0.0` is confirmed
against the tags; the first affected release is **15.0.0**.

**Patched version field: leave it empty for now, and do not fill it with a `dev` commit.** There is
no patched release. `origin/master` is `v15.0.8` and is affected; `dev` is affected; the fix in §10
is an unpushed local branch that has not been reviewed. The third-party compatibility question is
no longer open — it was decided on 2026-09-21 in favour of shape B (§12a) — but a decision is not
a release. The field should be set to a real tag when one ships, and the advisory should meanwhile
say "no patched version" explicitly, which it already does.

## 14. What was not done

- Nothing was pushed, merged, tagged or published. The branch is local to the ALARM worktree.
- Nothing in this repository was committed; the doc and the register edit are left in the working
  tree.
- The reporter's own fix lives in the GitHub-created private advisory fork. The fix in §10 was
  written independently of it. It has since been compared against theirs by the coordinating
  session; the shape-level tradeoff is in §12f and the measured comparison is in
  [the reporter-PR evaluation](./ghsa-8849-reporter-pr-evaluation-2026-09-21.md). Nothing in the
  private fork was modified and their pull request was not commented on from here.
- `loadRetro` was not touched; it is agent RETRO's.
