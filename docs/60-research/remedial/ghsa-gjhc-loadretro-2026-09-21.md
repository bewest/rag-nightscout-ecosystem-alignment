# GHSA-gjhc — `loadRetro` serves the retained devicestatus window to any socket

> **Snapshot — research as of 2026-09-21, measured against `dev 59430336` and `v15.0.8` (`92d08342`). Status: fix merged to dev in PR #8744 (BF-79), unreleased — the defect is still live on 15.0.8. Contributor-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

> **DISCLOSURE FIRST. Read this paragraph before quoting the rest anywhere public.** This is a
> **live unauthenticated disclosure of medical-device telemetry on the shipping release**
> (`v15.0.8` = `origin/master`) and on `dev`, with no patched version, and **this repository is
> public**. The mechanism is stated below because an operator cannot act on a defect they cannot
> recognise and because the fix is a handful of lines they can read. **The working probes, the
> seeding script and the harness are held outside version control**, in the session scratchpad lab
> directory, and are not reproduced here. All data in this document is synthetic and carries a lab
> canary string; no user, donor or community data was used at any point.

**Date:** 2026-09-21. **Agent:** RETRO. **Advisory:** GHSA-gjhc-pc29-r3m6 (draft, high, CWE-200 +
CWE-862, package `nightscout`, vulnerable range `>0.8.1`, no patched version, **no CVSS vector
set**). **Register entry:** BF-79.

**Refs measured:** `v15.0.8` (= `origin/master`, what operators run today), `v15.0.7`, `dev`
`59430336` (15.0.9), and `dev` + the fix on `bf/ws-loadretro-auth`. **Storage:** `mongod 7.0.43` in
docker, host port 27061, database `nightscout_advlab`. **Node:** v24.15.0. Every arm booted with
`env -i`, so only the variables named in each row reached the process and no stray
`AUTH_DEFAULT_ROLES` from a shell could change an answer.

---

## 1. The question this was run to answer

The maintainer's framing for this advisory round: *were the correct feature flags enabled when these
advisories were evaluated?* `AUTH_DEFAULT_ROLES` defaults to `readable` (`lib/settings.js:39`), and
`README.md:243` documents that as *"anyone can view Nightscout without a token"*. On that default,
anonymous reads of `devicestatus` are **documented, intended behaviour**: the same
`GET /api/v1/devicestatus.json` the advisory's data would otherwise come from answers **200** to
anybody. A proof that shows anonymous access on a default install has shown the default.

The advisory's PoC section says *"This does not require any specific configuration on the system"*.
That sentence is **true of the reachability and misleading about the impact**, and §5 says what it
should be replaced with.

So the only question that decides whether this advisory is real is: **does `loadRetro` survive
`AUTH_DEFAULT_ROLES=denied`?**

It does. Measured, with the REST lockdown running in the same process, at the same moment, as the
control.

## 2. The mechanism

`lib/server/websocket.js:315` — byte-identical on `v15.0.7`, `v15.0.8` and `dev`:

```js
socket.on('loadRetro', function loadRetro (opts, callback) {
  var reply = onceReply(callback);
  if (reply) reply({ result: 'success' });
  //TODO: use opts to only send delta for retro data
  socket.compress(true).emit('retroUpdate', { devicestatus: lastData.devicestatus });
  console.info('sent retroUpdate', opts);
});
```

Three things about it:

1. It consults **nothing**. Not `socketAuthorization`, not `socketAuthorization.read`, not
   `DataReceivers` membership. Every sibling handler in the same closure — `dbAdd`, `dbUpdate`,
   `dbUpdateUnset`, `dbRemove` — routes through `checkConditions`, which refuses on
   `!socketAuthorization` (`:269`). `loadRetro` is the one read handler and the one that skips it.
2. The authorization it skips **exists and is correct**, 460 lines further down. `socket.on('authorize')`
   (`:775`) calls `verifyAuthorization`, which resolves the socket's credentials through
   `ctx.authorization.resolve` and computes
   `read = ctx.authorization.checkMultiple('api:*:read', result.shiros)`, then joins readers to
   `DataReceivers` and sends them `dataUpdate`. That is the same decision `loadRetro` needed and
   never asked for.
3. **The attacker's move is to not call `authorize` at all.** Measured: `authorize` with a wrong
   secret ends in `socket.disconnect()` and no data. `authorize` is therefore not a gate an
   attacker has to pass; it is a gate they walk around. `loadRetro` is registered at connection
   time and answers immediately.

There is a fourth shape worth stating plainly, because it is the cleanest demonstration that this
is CWE-862 and not a configuration question. A socket that sends `authorize` **with no credentials**
on a `denied` instance is told, by the server, `{"read":false,...}` — and then receives the full
payload from `loadRetro` anyway. The decision is computed, returned to the client, and not honoured.

## 3. The measured matrix

Seed: 1 730 synthetic `devicestatus` records over 72 hours from two devices — one legacy-shaped
(`openaps` + `uploaderBattery`), one modern-shaped (`loop` + `uploader` object, pump manufacturer /
model / pump id) — plus 576 `sgv` entries, one cal and one treatment. Every record carries the
canary string. Anonymous socket, **no `authorize` ever sent**, `loadRetro` emitted once with
`loadedMills` set to one hour ago.

| ref | arm | anon `GET /api/v1/devicestatus.json` | `loadRetro` → `retroUpdate`? | records | canary present |
|---|---|---|---|---|---|
| `v15.0.7` | R — `readable` (shipped default) | **200** | **yes** | 576 | **yes** |
| `v15.0.7` | D — `AUTH_DEFAULT_ROLES=denied` | **401** | **yes** | 576 | **yes** |
| `v15.0.8` (= `origin/master`) | R — `readable` | **200** | **yes** | 576 | **yes** |
| `v15.0.8` | D — `denied` | **401** | **yes** | 576 | **yes** |
| `dev` `59430336` | R — `readable` | **200** | **yes** | 576 | **yes** |
| `dev` `59430336` | D — `denied` | **401** | **yes** | 576 | **yes** |
| `dev` + fix (`bf/ws-loadretro-auth`) | R — `readable` | **200** | **yes** | 576 | **yes** |
| `dev` + fix | D — `denied` | **401** | **no** | 0 | no |

In the D rows, `status.json`, `entries.json`, `devicestatus.json` and `treatments.json` were all
**401** to the same anonymous caller in the same run. That is what makes "and it still leaks" mean
something.

### 3.1 The liveness control — because the fix's evidence is a negative

The result that proves the fix is *the absence of an event*, and **a dead server produces exactly
that**. Lab instances launched from a backgrounded `node server.js` inside a tool call were observed
being reaped minutes later, with logs ending mid-normal-operation and no error line. So every
negative arm in this document was **re-run with the server relaunched under `setsid nohup`** and
with four independent liveness assertions **in the same run as the probe**:

| arm | HTTP before | HTTP after | socket `connect` | events seen | `retroUpdate` |
|---|---|---|---|---|---|
| `v15.0.8`, `denied`, anon (unfixed) | 401 | 401 | yes | `clients`, `retroUpdate` | **572 records** |
| `dev`+fix, `readable`, anon | 200 | 200 | yes | `clients`, `retroUpdate` | **572 records** |
| `dev`+fix, `denied`, anon | **401** | **401** | **yes** | **`clients`** | **none** |
| `dev`+fix, `denied`, `authorize` with no credentials | **401** | **401** | **yes** | **`clients`, `connected`** — server replied `{read:false,…}` | **none** |
| `dev`+fix, `denied`, `authorize` with the admin secret | 401 | 401 | yes | `clients`, `connected`, `dataUpdate`, `retroUpdate` | **570 records** |

Read the two refusal rows against the last one: **the same process, on the same port, seconds
later, served 570 canaried records to an authorized reader.** It was alive, it held the data, and
it declined to give it to the anonymous socket. On a `denied` arm `status.json` is itself 401, so
"alive" means *any* HTTP response; `000` would mean a corpse and none was seen. An independent
no-`loadRetro` control socket ran alongside each row and saw `clients` every time, which is the
socket-layer liveness signal.

(Record counts drift 576 → 572 → 570 across runs because the 24-hour window rolls forward against a
fixed seed. That drift is itself evidence of a live dataloader ticking.)

The **positive** rows of §3 need no such treatment: a dead server cannot emit 576 canaried records.
And the ablation of §7 runs entirely **in-process under mocha**, with the HTTP servers created
inside the test file, so there is no external instance to die; in that run the failing cases fail by
*receiving* data and the two positive cases stay green in the same process.

### 3.2 The isolating control

`probe-control-socket.js` — the **same** unauthenticated socket, on the **same** instance, that
never emits `loadRetro` — saw only the event `clients` (the viewer count) in **all eight** rows
above, within a 6 s window. The disclosure is attributable to the handler, not to the connection.

### 3.3 The `authorize` variants

On `v15.0.8`, arm D, and on the fixed build, arm D:

| what the socket sends first | `authorize` reply | `retroUpdate` on `v15.0.8`/D | on fixed/D |
|---|---|---|---|
| nothing | — | **576 records** | **none** |
| `authorize` with a wrong secret | none — server calls `socket.disconnect()` | none (socket is gone) | none |
| `authorize` with no credentials | `{read:false, write:false, write_treatment:false}` | **576 records** | **none** |
| `authorize` with the admin secret | `{read:true, write:true, write_treatment:true}` | 576 records | 576 records |

Row 2 is the one that matters for how the defect is described: **an attacker who tries to
authenticate and fails is disconnected; an attacker who never tries is served.** Row 3 is the
bypass in one line. Row 4 is the control that the fix does not break legitimate readers.

### 3.4 Is any shipped setting able to stop it?

**No.** Measured on `v15.0.8`, not inferred — although the source agrees: a grep of every `env.*`
reference in `lib/server/websocket.js` finds collection names, `env.version`, `env.enclave` and
`env.settings.enable` (used only to build the `status` payload). **No setting reaches any handler
registration in that file.**

| setting | anon REST `devicestatus` | anon `loadRetro` |
|---|---|---|
| default (`readable`) | 200 | **576 records** |
| `AUTH_DEFAULT_ROLES=denied` | **401** | **576 records** |
| `AUTH_DEFAULT_ROLES=status-only` | **401** | **576 records** |
| `AUTH_DEFAULT_ROLES=denied` + `AUTHENTICATION_PROMPT_ON_LOAD=true` | **401** | **576 records** |
| `AUTH_DEFAULT_ROLES=denied` + `TREATMENTS_AUTH=off` | **401** | **576 records** |
| `AUTH_DEFAULT_ROLES=denied` + `DEVICESTATUS_DAYS=2` | **401** | **1 150 records, 47.8 h** |

`AUTHENTICATION_PROMPT_ON_LOAD` (`authenticationPromptOnLoad`, `lib/settings.js:74`) is read in
`lib/api3/alarmSocket.js:113` and `lib/client/index.js:1166` and **nowhere in
`lib/server/websocket.js`**; the measurement matches. The only configuration knob that touches this
path at all is `DEVICESTATUS_DAYS=2`, and it makes the leak **twice as large**.

### 3.5 How much history, and is `loadedMills` really ignored?

`loadedMills` is ignored: every probe above sent a non-zero `loadedMills` and received the whole
window regardless. But the advisory's *"does not constrain the returned records"* is worth a real
number rather than an adjective, because there **is** a bound and it is not "everything":

- `lastData` is `ctx.ddata.clone()`, refreshed on every `data-processed` tick.
- `ddata.devicestatus` is filled by `loadDeviceStatus` (`lib/data/dataloader.js:454`) out of
  `ctx.cache`, whose `devicestatus` **retention period is `ONE_DAY`**, or `TWO_DAYS` when the
  `DEVICESTATUS_DAYS=2` extended setting is set (`lib/server/cache.js:26-28`).

Measured against a 72-hour seed of 1 730 records: **576 records spanning 23.92 h** by default and
**1 150 records spanning 47.83 h** with `DEVICESTATUS_DAYS=2`. So the real bound is **the rolling
24-hour (or 48-hour) cache window, unbounded in record count**, not the full history. For an AID
user uploading every five minutes from two device types that is the whole of yesterday.

The comparison that makes this a *severity* fact rather than a detail: the **authorized** initial
load does not send this. `authorize` → `dataWithRecentStatuses()` → `recentDeviceStatus()`
(`lib/data/ddata.js:148`) trims to **the 10 most recent records per device-and-type pair**.
Measured on the same instance and seed: an authorized reader's `dataUpdate` carried **20**
devicestatus records; `loadRetro` to a socket that never authorized carried **576**. The
unauthenticated path returns **28.8× more devicestatus than the authenticated one**.

### 3.6 What is in a real-world-shaped record

Synthetic, but shaped like what AID uploaders actually send. Everything below arrived intact at the
unauthenticated socket in arm D, with no field stripped or redacted anywhere on the path:

- **`openaps.suggested`** — `bg`, `eventualBG`, `IOB`, `COB`, `ISF`, `CR`, `TDD`, `insulinReq`,
  `sensitivityRatio`, `current_target`, `threshold`, `rate`, `duration`, and the free-text `reason`
  string, which in production carries the dosing narrative.
- **`loop`** — `version`, `recommendedBolus`, `enacted` (including `bolusVolume`), `iob`, `cob`,
  `predicted.values`, `failureReason`.
- **`pump`** — `clock`, `battery.percent`/`voltage`, `reservoir`, `status.status`,
  `status.bolusing`, `status.suspended`, and **`manufacturer`, `model` and `pumpID`**.
- **`uploader`** — `battery`, `isCharging`, `type`, and **`name`**, which on a real install is the
  phone's name and is very often a person's given name.
- **`device`** — the uploader's device string, which on a real install is frequently a hostname or
  a rig name.

So the answer to "is there anything beyond device telemetry in here" is **yes, identifiers**:
pump serial (`pumpID`), pump make and model, and two free-form name fields that users populate with
personal names. No tokens, secrets or URLs are in the shape — `devicestatus` has no credential
field — and nothing in the payload is a write primitive.

### 3.7 No throttle

One unauthenticated socket emitting `loadRetro` **20 times** on `v15.0.8`/arm D received **20 full
responses, 12.4 MB**, in 12 s. Nothing rate-limits, coalesces or debounces the handler. A ~46-byte
frame elicits ~618 KB, an amplification of roughly **13 400×**. On a `denied` install this is the
only anonymous amplification primitive of that shape; on a `readable` install
`devicestatus.json?count=N` already offers a larger one to the same caller, so it is marginal only
in the hardened arm.

## 4. Severity, in both directions

### 4.1 On the shipped default, the marginal disclosure is zero — measured

This is the part an advisory can get wrong in the expensive direction, so it was measured field by
field rather than argued. On `v15.0.8`, arm R, the same instance and the same seed:

| | anon `GET /api/v1/devicestatus.json?count=2000` | anon `loadRetro` |
|---|---|---|
| records returned | **1 730** (the full 72 h seed) | 574 (the 24 h cache) |
| record `_id`s not also in the REST answer | — | **0** |
| JSON field paths present only here | **1** (`uploaderBattery`, which the runtime rewrites away) | **0** |

The `loadRetro` payload is a **strict subset** of what the anonymous REST route already returns on
a default install: fewer records, no record the REST route does not also return, and **not one
field** the REST route does not also carry. The REST default page size is 10, but `?count=` is
documented and unbounded for an anonymous caller on `readable`.

**On a default install this advisory's marginal confidentiality impact is zero.** There is no
information a caller obtains through `loadRetro` that the same caller cannot obtain, in larger
quantity, through the documented public-read REST surface of the same instance. Reachability
without configuration is real; impact without configuration is not.

Proposed vector for the default configuration:
**`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N` = 0.0.**
A scorer unwilling to publish a 0.0 should say in words that what is being scored is reachability,
not disclosure. The availability amplification of §3.7 does not rescue a non-zero score here
either, because the REST route offers the same caller a larger one.

### 4.2 On a hardened install it is a real CWE-862 bypass

On `AUTH_DEFAULT_ROLES=denied` the operator has made a deliberate, documented choice that reads
require a credential, and every REST read honours it with a 401. `loadRetro` does not. An
unauthenticated remote attacker who knows only the URL retrieves 24 hours of pump, uploader and
loop/openaps telemetry, including pump serial and a user-chosen device name.

- **AV:N** — network, the socket is the public site.
- **AC:L** — one frame, no timing, no race, no preconditions.
- **PR:N** — the attacker holds nothing; trying to authenticate and failing is *worse* for them.
- **UI:N**, **S:U** — nothing to induce, no authority crossed.
- **C:H** — on a `denied` install the entire read surface is supposed to be closed, and this opens
  the highest-value collection in it: continuous, near-real-time health and insulin-delivery data
  about an identifiable individual, plus device identifiers.
- **I:N** — no write primitive; `checkConditions` still guards every write handler.
- **A:N or A:L** — see §3.7.

Proposed vector for the hardened configuration:
**`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N` = 7.5**,
or **`…/A:L` = 8.2** if the unthrottled amplification of §3.7 is counted.

**7.5 is the recommendation.** The confidentiality loss is the finding; the amplification is a
by-product, and 12 MB from 20 frames is not on its own a denial of service.

### 4.3 Which configuration the advisory should be scored under

**The hardened one, `denied`, at 7.5** — with the default case stated in the text rather than in the
vector. A security boundary is only crossed when one has been drawn, and `denied` is where the
operator draws it. Scoring the default at 8.2 (as the sibling advisory GHSA-r3gv-x7fw-j2v5 did)
would, for *this* defect, publish a high score for a payload measured to be a strict subset of the
instance's own documented public output, and would tell thousands of default self-hosters they have
an emergency they do not have. The people who **do** have one are the operators who set `denied`
precisely because they cared — and the advisory should be legible to them.

## 5. The affected range is wrong

The advisory claims `>0.8.1` and *"all versions since 0.8.1 are affected"*.

Measured, per tag, by grepping `lib/` at each tag rather than by reading changelogs:

| tag | `loadRetro` present | `DataReceivers` present | `authDefaultRoles` present |
|---|---|---|---|
| `0.8.1`, `0.8.2`, `0.8.3`, `0.8.4` | **no** | no | no |
| `0.9.0` and later | **yes** (3 files) | yes | yes |

`loadRetro` was introduced by `18aa4295` *"request retro data on demand"* (2016-10-09) and
`2cb597d3` *"only send most recent devicestatus to the client; load the rest when/if user scrolls"*
(2016-10-10); the handler moved to `lib/server/websocket.js` in `05157605` (2017-12-28). The
earliest release tag containing it is **0.9.0**. The handler at `0.9.0:lib/websocket.js:167` is the
same unguarded five lines.

`0.9.0` is also the first release carrying the authorization model this bypasses — `a20f8e28`
*"WS authentication"* and `0f735d0a` *"implement read-access against token, mod default"* both land
in `0.9.0`. So the question "was there anything to bypass at that version" resolves cleanly: the
handler and the thing it fails to consult shipped in the **same release**.

**First genuinely affected version: `0.9.0`.** The range should be `>=0.9.0`, not `>0.8.1`. Three
releases (0.8.2, 0.8.3, 0.8.4) are currently declared vulnerable to a handler that does not exist
in them.

## 6. The fix

Branch `bf/ws-loadretro-auth` off `origin/dev` `59430336`, commit `9765e8cd`. Not pushed.

The requirement is asymmetric and the asymmetry is the whole design: **`denied` must refuse and
`readable` must keep working.** Most Nightscout instances run the documented public-read default,
and a fix that closed `loadRetro` unconditionally would be a regression for the majority of
self-hosters, not a fix.

The codebase already computes exactly the needed decision, and it is reused rather than reinvented.
`verifyAuthorization(message, ip, cb)` (`lib/server/websocket.js:119`) hands
`{api_secret, token, ip}` to `ctx.authorization.resolve` and returns
`read = checkMultiple('api:*:read', shiros)`. Called with an **empty message** it resolves the
anonymous case through `resolve`'s own `if (!authAttempted) → defaultShiros` branch
(`lib/authorization/index.js:161-170`) — i.e. the `AUTH_DEFAULT_ROLES` shiros, the same ones the
REST surface answers with. That is precisely "may an unauthenticated socket read?", already
written, already used by the `authorize` handler on this same namespace.

So:

- a socket that authorized carries `socketAuthorization`, and its `.read` is honoured;
- a socket that never authorized is resolved through `verifyAuthorization({}, remoteIP, …)`;
- on `readable` that is `read:true` and nothing changes for anonymous clients;
- on `denied` that is `read:false` and the handler replies `{result: 'Not permitted'}` and emits
  nothing — the same refusal string `checkConditions` already returns for the write handlers.

The decision the fix needs is already computed in the same file, by the function the `authorize` handler on this namespace calls.

`loadedMills` is **still ignored**. Honouring it is a behaviour change with its own client-side
consequences and belongs in a separate commit; the advisory's remediation section asks for both and
they were deliberately not blended.

## 7. Non-vacuity

**Ablation.** This one runs entirely **in-process under mocha** — the test file creates its own
`http.createServer()` instances — so there is no external server that can quietly die, and the
failing direction is a *receipt* of data rather than an absence. Reverting `lib/server/websocket.js` to the `origin/dev` version — leaving the new test
file in place — turns the two negative cases red **with the original symptom**, not with a generic
error. The assertions are written as one object comparison per case so the failure prints the
symptom itself:

```
expected Object { retroUpdate: true, canary: true, records: 1 }
      to equal Object { retroUpdate: false, canary: false, records: 0 }
```

`retroUpdate: true`, `canary: true`, `records: 1` — devicestatus carrying the canary actually
arrived at a socket the server had resolved as unable to read. In the same ablated run the two
positive cases stayed **green**, which is what distinguishes "the check is real" from "the revert
broke something unrelated".

**Positive control.** The fixed build on the shipped `readable` default still serves `retroUpdate`
to a fully anonymous client: 576 records, canary present, ack `{result:'success'}` (row 7 of §3,
and the fourth test case). The documented public deployment is unchanged. An authorized reader on a
`denied` instance also still gets its records (§3.3 row 4, and §3.1 row 5 re-measured under the
liveness bracket: 570 records to an authorized reader on the same process that had just refused an
anonymous one).

**Suite.** `NODE_ENV=test npm test` in the `dev` worktree, `mongod 7.0.43`:

| | passing | pending | failing |
|---|---|---|---|
| before (`origin/dev` `59430336`) | **2 311** | 3 | 0 |
| after (`bf/ws-loadretro-auth` `9765e8cd`) | **2 315** | 3 | 0 |

2 311 matches what the BF-75 work recorded on the same ref the same day.

**A lab note, not a product finding.** The first attempt at the baseline run died on
`Error connecting to MongoDB`. The container had hit `WT_PANIC: … Too many open files` — running
the full suite twice against one `mongod` with the default `nofile` limit exhausts its descriptors,
because each run creates thousands of collections and indexes. The container was recreated with
`--ulimit nofile=64000`, the seed replaced, and **both** numbers above re-measured on the healthy
instance. Nothing about it implicates Nightscout, but the first, discarded numbers were not real
and are recorded here as discarded.

## 8. What the advisory text should say

1. **Keep** the observation that no configuration is required to *reach* the handler; that is true
   and §3.4 confirms it more strongly than the advisory does — no shipped setting stops it, and the
   one that touches it doubles it.
2. **Replace** the sentence *"This does not require any specific configuration on the system"* with
   something that separates reach from impact, e.g.: *"The handler is reachable on every
   configuration. On the shipped `AUTH_DEFAULT_ROLES=readable` default, where
   `GET /api/v1/devicestatus.json` is already public by design, the data returned is a subset of
   what that endpoint already serves anonymously and there is no additional disclosure. The
   security impact is on instances configured with `AUTH_DEFAULT_ROLES=denied` (or any non-reading
   default), where every REST read returns 401 and this handler returns the last 24 hours of
   device telemetry to an unauthenticated caller."*
3. **Add** the CVSS vector `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N` (7.5), scored on the
   hardened configuration, and say in the text that it is.
4. **Correct** the range to `>=0.9.0` (§5).
5. **State the bound**: the 24-hour rolling cache window, 48 hours with `DEVICESTATUS_DAYS=2` — and
   that this is **more** than the 10-per-device-per-type an *authenticated* reader gets on connect.
6. **Say that the attacker never calls `authorize`**, because a reader who knows only that
   authorization exists on this namespace will look for a flaw in it and not find one.
7. **Patched version:** leave it empty until a release exists. The fix is on an unpushed local
   branch; `dev` (15.0.9) is not released and `origin/master` is 299 commits behind it, so the
   patched field must name the first **tagged release** that carries the fix and must not name
   `dev`, a commit or a PR. Publishing `dev` as "patched" would tell operators running 15.0.8 that
   they have a version to move to, and they do not.

---

*Prepared by agent RETRO, 2026-09-21, for review. Reproduced against `v15.0.7`, `v15.0.8`
(= `origin/master`) and `dev` `59430336` on `mongod 7.0.43`, in both `AUTH_DEFAULT_ROLES=readable`
and `AUTH_DEFAULT_ROLES=denied`, with the REST control in the same run. Not a substitute for
maintainer review.*
