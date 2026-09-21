# What `AUTH_DEFAULT_ROLES` actually gates — the control every advisory needs, measured

Date: 2026-09-21. Refs: `origin/dev` `59430336` (15.0.9) and `v15.0.8` = `origin/master`
`92d08342`, the release operators run. Storage: `mongo:7` (mongod 7.0) in Docker, one
container per arm. Worktrees `externals/work/crm-advisory` and
`externals/work/crm-adv-shipping`. Every number below was produced by booting the tree and
issuing the request; nothing here is read off the source.

**Disclosure.** Two of the defects described here are live on the shipping release and
unfixed. This document names the *mechanism* and withholds the *recipe*: no payloads, no
runnable probes, no step sequence. The probes live outside version control, in the session
scratchpad. See [BF-70's disclosure note](../../30-design/remedial/nightscout-backfix-register.md)
for why this repository being public changes what may be written in it.

---

## 0. The question

Five security advisories are open as drafts against `nightscout/cgm-remote-monitor`. Four of
the five argue from *anonymous access*. Nightscout ships `AUTH_DEFAULT_ROLES=readable`
(`lib/settings.js:39`), which `README.md:243` documents as making the site "readable by
anyone who knows the URL", and which the application itself flags at boot with a persistent
admin notice titled **"Nightscout readable by world"** (`lib/server/bootevent.js:149-156`).

So anonymous read on a default install is not a finding. It is the documented default, and
the product says so in two places. A demonstration of anonymous access is only a
demonstration of a *defect* if it survives the setting that is supposed to stop it.

**That is the control this document supplies**, and it is the thing to check before grading
any of the five: was the evaluation run with reads actually denied, or only against the
shipped default?

## 1. The control works — the REST surface really does lock down

Anonymous, no token, no `api-secret`, one instance per configuration, all against the same
seeded database. `dev` `59430336`; the shipping release behaves identically on every row.

| request | `readable` (default) | `denied` | `readable`+`careportal` | `denied`+`careportal` | `status-only` |
|---|---|---|---|---|---|
| `GET /api/v1/status.json` | 200 | **401** | 200 | **401** | 200 |
| `GET /api/v1/entries.json` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v1/entries/current.json` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v1/treatments.json` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v1/devicestatus.json` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v1/profile.json` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v1/food.json` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v1/activity.json` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v1/count/entries/where` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v2/properties` | 200 | **401** | 200 | **401** | **401** |
| `GET /pebble` | 200 | **401** | 200 | **401** | **401** |
| `GET /api/v3/entries` | **401** | **401** | **401** | **401** | **401** |
| `GET /api/v3/version` | 200 | 200 | 200 | 200 | 200 |
| `GET /` , `/food`, `/profile` | 200 | 200 | 200 | 200 | 200 |

Three things worth keeping:

- **`denied` is a real lockdown of API v1 and v2.** Every data route answers 401, and so does
  `status.json`. This is what makes "it still returned data under `denied`" mean something.
- **API v3 never honours `readable`.** It is 401 to an anonymous caller on *every*
  configuration including the default. So an advisory whose vector is a v3 route cannot be
  an unauthenticated one, whatever the deployment's `AUTH_DEFAULT_ROLES` says.
- **The HTML pages are always 200.** They are the shell; the data arrives over the API and
  over the socket. A 200 on `/` is not access to anything.

## 2. The socket surface does not lock down at all

Same instances, same run. Two unauthenticated Socket.IO clients per instance: one that emits
`loadRetro` and one that does not, and one `/alarm`-namespace client that never sends
`subscribe`.

| | `readable` | `denied` | `readable`+`careportal` | `denied`+`careportal` | `status-only` |
|---|---|---|---|---|---|
| main namespace, no `loadRetro` (**control**) | only `clients` | only `clients` | only `clients` | only `clients` | only `clients` |
| main namespace, `loadRetro` → `retroUpdate` | **devicestatus** | **devicestatus** | **devicestatus** | **devicestatus** | **devicestatus** |
| `/alarm`, never subscribed → `notification` | **delivered** | **delivered** | **delivered** | **delivered** | **delivered** |

**No documented configuration stops either one.** The `retroUpdate` payload carries the
full device-status document — the loop's suggestion block, pump battery and reservoir,
whether the pump is bolusing or suspended, and the uploader's state — on an instance whose
`GET /api/v1/devicestatus.json` answers 401 in the same second. The `/alarm` notification
carries a treatment's dose, the device that entered it and its free-text notes.

The control row is what makes this attributable. An unauthenticated socket that simply
connects and waits sees one event, `clients`, a viewer count. The disclosure is the
handlers', not the connection's.

### 2.1 Six of the seven main-namespace handlers *are* guarded

The main Socket.IO namespace registers seven handlers on v15.0.8
(`lib/server/websocket.js`): `disconnect`, `authorize`, `loadRetro`, `dbAdd`, `dbUpdate`,
`dbUpdateUnset`, `dbRemove`. An unauthenticated socket was pointed at each of the five that
do anything, on the shipping release, in both arms:

| handler | `readable` | `denied` | landed in the database? |
|---|---|---|---|
| `dbAdd` | `{result: "Not authorized"}` | `{result: "Not authorized"}` | no — 0 records, checked directly in mongo |
| `dbUpdate` | `{result: "Not authorized"}` | `{result: "Not authorized"}` | no |
| `dbUpdateUnset` | `{result: "Not authorized"}` | `{result: "Not authorized"}` | no |
| `dbRemove` | `{result: "Not authorized"}` | `{result: "Not authorized"}` | no |
| **`loadRetro`** | `{result: "success"}` **+ devicestatus** | `{result: "success"}` **+ devicestatus** | n/a — it is a read |

The refusals were confirmed against the collection rather than taken from the reply string, so
"Not authorized" is not merely cosmetic.

This reframes the `loadRetro` advisory, and in a way its own text does not. The socket layer is
not unguarded: the write handlers check, the `authorize` handler establishes the authorization
the data push depends on, and the periodic `dataUpdate` goes to the `DataReceivers` room that
only an authorized reader joins. **`loadRetro` is the one handler on that namespace with no
check of any kind** — a single omission in an otherwise consistent design, which is both why it
is easy to believe and why it is cheap to fix.

**This is the answer to the question in §0 for the two socket advisories: the flag was not the
variable.** Their reporters' claim that no particular configuration is required is correct as
far as it goes — but the useful fact, which neither advisory states, is the stronger one:
*no configuration mitigates them.* An operator who has followed Nightscout's own security
documentation and turned off unauthorised access still has both.

**Extended by the per-advisory reproductions, same day.** The `/alarm` result above was one
event class; all five were then caused through the real server paths — threshold crossings via
`POST /api/v1/entries` into `simplealarms`, treatment writes into `treatmentnotify` — and
`notification`, `announcement`, `alarm`, `urgent_alarm` and `clear_alarm` **all** reach a
never-subscribed anonymous socket, on v15.0.8 and on `dev`, in both arms. Two further settings
were tested and neither helps: `AUTHENTICATION_PROMPT_ON_LOAD=true` refuses the subscribe and
**does not disconnect the socket**, which still receives everything; turning careportal off via
`ENABLE=` removes `notification`/`announcement` by removing the feature, while `alarm`,
`urgent_alarm` and `clear_alarm` still arrive. The namespace itself is mounted unconditionally
(`lib/api3/index.js:113`, `lib/server/app.js:294`) — no flag removes it. Sharpest single datum:
under `denied` the server answers a subscribing anonymous socket `{"success":true,…,"read":false}`
— it computes the correct authorization decision, tells the client, and delivers anyway. Details
in [the GHSA-8849 report](./ghsa-8849-alarm-socket-2026-09-21.md).

Verified on **v15.0.8**, the shipping release, not only on `dev`: the `loadRetro` disclosure and
the `/alarm` delivery were each reproduced against the 15.0.8 tree under
`AUTH_DEFAULT_ROLES=denied`, on an instance whose `GET /api/v1/status.json` answered 401 in the
same run. Every row of §1's table was also re-run against 15.0.8 in both arms and **agrees with
`dev` on all 24 paths**, so the two refs are not being conflated here — they were measured
separately.

## 3. Two configuration defects found while building the control

Neither is an advisory. Both are operator-facing, both reproduced with their controls in the
same run, and they are two halves of one trap.

### 3.1 `TREATMENTS_AUTH=off` silently switches off the "readable by world" warning

`lib/server/env.js:195-197` implements the deprecated `TREATMENTS_AUTH=off` by *appending* to
the setting:

```js
if (!readENVTruthy('TREATMENTS_AUTH', true)) {
  env.settings.authDefaultRoles = env.settings.authDefaultRoles || "";
  env.settings.authDefaultRoles += ' careportal';
}
```

`lib/server/bootevent.js:149` then decides whether to warn with an **exact string compare**:

```js
if (env.settings.authDefaultRoles == 'readable') { … "Nightscout readable by world" … }
```

`"readable careportal"` is not `"readable"`, so the notice is not raised. Measured through
`GET /api/v2/adminnotifies` with an admin credential, all three in one run:

| configuration | resolved `authDefaultRoles` | anonymous read | anonymous treatment write | "readable by world" notice |
|---|---|---|---|---|
| default | `readable` | yes | no | **shown** (positive control) |
| `TREATMENTS_AUTH=off` | `readable careportal` | yes | **yes** | **absent** |
| `AUTH_DEFAULT_ROLES=denied` | `denied` | no | no | absent (correct — negative control) |

Run on `dev` and then repeated on **v15.0.8** with the same three arms and the same result:
`TREATMENTS_AUTH=off` → anonymous read 200, anonymous treatment write 200, `notifyCount` **0**;
default → `notifyCount` 1, title *Nightscout readable by world*. The source is byte-identical on
both refs (`lib/server/bootevent.js:149`, `lib/server/env.js:187-190`).

The one configuration that is both world-readable *and* anonymously writable is the one
configuration whose operator is never told the site is world-readable. The warning fails open
in exactly the case it exists for.

### 3.2 The `careportal` default role is inert unless reads are open

`lib/api/treatments/index.js:26` applies a router-wide gate before any per-route check:

```js
api.use(ctx.authorization.isPermitted('api:treatments:read'));
```

and only then, at `:146`, the create check. The `careportal` role grants exactly one
permission, `api:treatments:create` (`lib/authorization/storage.js:143`). It therefore cannot
reach the POST handler on its own — the read gate refuses first. Measured, anonymous POST to
`/api/v1/treatments`:

| `AUTH_DEFAULT_ROLES` | anonymous write |
|---|---|
| `readable careportal` (what `TREATMENTS_AUTH=off` produces) | **200, record stored** |
| `careportal` | 401 |
| `denied careportal` | 401 |
| `denied` | 401 |

`README.md:243` says the setting takes "any valid role name". `careportal` is a valid role
name, it is one of the five the product ships, and setting it alone does nothing. The
operator intent it most obviously expresses — *close reads, but let the household enter
carbs without a token* — is unreachable through this setting and fails silently.

**The two together.** §3.1 fails open on the warning; §3.2 fails closed on the function. The
only configuration in which `careportal` works is the only configuration in which the warning
is suppressed. An operator chasing the second behaviour lands on the first by construction.

## 4. What this means for grading the five advisories

| advisory | vector | is the anonymous access the documented default? | does it survive `denied`? |
|---|---|---|---|
| `GHSA-gjhc-pc29-r3m6` `loadRetro` | main socket | no — REST equivalent is 401 under `denied` | **yes, measured, on v15.0.8** |
| `GHSA-8849-qjp5-vrrj` `/alarm` | `/alarm` socket | no | **yes, measured** |
| `GHSA-r3gv-x7fw-j2v5` operator injection | API v1 query | **partly — see BF-71** | the `$where` half, by token; see below |
| `GHSA-mjp4-84fw-gj4v` v3 notes → report | API v3 write | n/a, v3 is never anonymous (§1) | requires a write token either way — and **closed in 15.0.8** |
| `GHSA-5mrq-gpqw-q5v5` socket `dbAdd` | main socket write | n/a, requires a write-scoped token | requires a token either way — and **closed in 15.0.8** |

The three that turn on the flag question resolve differently from one another, and that is the
point of asking:

- The two **socket** advisories are real authorization defects and the default is irrelevant
  to them. If anything the existing drafts *understate* the case, because they argue from
  anonymity on a default install when the stronger and more useful statement is that the
  documented hardening does not help.
- The **operator-injection** advisory is the one where the flag question bites. Its headline
  proof-of-concept — dropping the default date window with an operator on the date field —
  was re-measured on 2026-09-21 with its control in the same run and is **not a privilege
  boundary**: the allowlisted, documented `find[date][$gte]=0` returns the identical records
  under the identical authorization, and every form of it is 401 under `denied`. The
  full-history read is what `readable` *means*. That is register entry **BF-71**, filed at
  `low` to correct the record. What survives from that advisory is the `$where` half — server-
  side JavaScript, refused since PR #8743 on `dev` and **still live on v15.0.8** — and an
  availability defect, **BF-72**, where a single unauthenticated request costs the database
  minutes of CPU on the shipped default.
- The two **XSS** advisories never depended on the setting: both need a write-scoped token,
  which is a credential an operator hands to devices and apps. Both were then re-measured
  across v15.0.7 / v15.0.8 / `dev` on four write paths with a real v3 JWT, and **both are closed
  in 15.0.8** — root cause *and* sink, each "fixed" cell paired with a positive v15.0.7 control
  from the same run. The one question that could not be answered from the source was whether a
  payload a 15.0.7 server had *already stored* still fires on a patched server; measured by
  inserting it straight into mongo and then rendering, the answer is **no** — and that is true
  only because the output-escaping half of the fix landed alongside the purification half. See
  [the XSS pair verification](./ghsa-xss-pair-verification-2026-09-21.md).

## 5. There is no operator-side workaround, and the advisories should say so

An advisory that cannot be fixed by the reader in the next hour should tell them what to do
meanwhile. For these two, measured on v15.0.8, the honest answer is *nothing that keeps the
site working*:

- **`AUTH_DEFAULT_ROLES=denied` does not help** (§2). It is the mitigation an operator would
  reach for first, it is the one Nightscout's own security documentation points at, and both
  leaks survive it.
- **A reverse proxy cannot separate the `/alarm` namespace from the main one.** Both multiplex
  over the single `/socket.io/` endpoint; the namespace is a token *inside* the Engine.IO
  payload, not part of the URL. Measured: a handshake taken on `/socket.io/` was joined to
  `/alarm` by POSTing `40/alarm,` to that same URL, and the server acknowledged with an
  `/alarm` session id. A proxy rule would have to parse Socket.IO frames.
- **Blocking `/socket.io/` outright does work and costs the product.** The dashboard's live
  updating, the alarm delivery a caregiver depends on, and the retro view all run over it.
  For a tool whose purpose is watching glucose in real time, that is not a workaround.

So the workaround line in both advisories should read approximately: *none; the fix is the
patch*. That is worth stating explicitly rather than leaving the section blank, because a
blank workarounds section reads as "we did not look".

## 6. Recommendations

1. **Say "no configuration mitigates this" in the two socket advisories.** The sentence "this
   does not require any specific configuration" reads, to an operator, as *the default makes
   it worse*, which invites the mitigation "then I will turn off anonymous reads". Measured,
   that mitigation does not work. The advisory text should say so.
2. **Score the two socket advisories against the hardened install, and say what the default
   costs separately.** For `/alarm` this was then measured field by field: **no field in any of
   the five payloads is absent from the anonymous REST surface of a `readable` install** — the
   dose, device, notes and event type are in `treatments.json`, `debug.lastSGV` in
   `entries.json`, `debug.thresholds` in `status.json`, and `notifyhash`/`key` are sha1 over
   already-readable fields. What the socket adds on a default install is real-time push with no
   request rate and no access-log trace, plus one thing with no REST equivalent: a
   server-labelled "hypo/hyper right now" that a poller would have to re-derive. Saying that in
   the advisory makes it *more* credible, not less, and stops default-install operators
   concluding they are exposed to content they are not. `loadRetro` deserves the same
   field-by-field comparison before its confidentiality impact is stated.
3. **Fix the warning's condition** (§3.1) — test for the `readable` role's presence in the
   resolved list, not string equality with it.
4. **Decide what `careportal` is for** (§3.2) — either give the role the read permission its
   routes require, move the router-wide read gate below the create route, or document that the
   setting only functions alongside `readable`. Failing silently is the one option to rule out.
5. **Do not let `AUTH_DEFAULT_ROLES=readable` be read as consent to everything.** The product
   already calls it a condition to close. Four advisories argue from it; the register's §1 now
   has two entries (BF-71, BF-72) whose whole content is *what that default does and does not
   grant*. That distinction is worth writing down once, in the README next to the setting,
   rather than re-deriving per advisory.

*Evidence*: probes, seeds and raw output outside version control in the session scratchpad
(`lab/`), with the boot harness and the arm-by-arm logs. Register:
[BF-04, BF-70, BF-71, BF-72](../../30-design/remedial/nightscout-backfix-register.md);
[BF-04/BF-70 report](./bf04-bf70-operator-allowlist-2026-09-18.md).

---

## 7. A separate problem: the advisory metadata does not reach the people who run this

Checked against the live registry on 2026-09-21, and against the repository's own
`package.json` (`"name": "nightscout"`).

| advisory | ecosystem | package named | vulnerable range | patched |
|---|---|---|---|---|
| `GHSA-gjhc-pc29-r3m6` | npm | `nightscout` | `>0.8.1` | *(blank)* |
| `GHSA-8849-qjp5-vrrj` | npm | `nightscout` | `≥15.0.0` *(Unicode ≥, not `>=`)* | *(blank)* |
| `GHSA-r3gv-x7fw-j2v5` | npm | **`cgm-remote-monitor`** | `<= 15.0.8` | *(blank)* |
| `GHSA-mjp4-84fw-gj4v` | npm | `nightscout` | `<= 15.0.7` | *(blank, though the range is closed)* |
| `GHSA-5mrq-gpqw-q5v5` | npm | `nightscout` | `<= 15.0.7` | `15.0.8` |

Three defects in that table, none of them about the vulnerabilities:

1. **`cgm-remote-monitor` is not a package on npm.** `registry.npmjs.org/cgm-remote-monitor`
   returns `{"error":"Not found"}`. That advisory names a coordinate that matches nothing in
   any dependency tree anywhere.
2. **`nightscout` on npm stops at 14.2.11**, published 2022, `dist-tags.latest = 14.2.11`, 20
   versions total, none in the 15.x line. Its `repository` field does point at this repo, so
   it is the right package — but every 15.x range on these advisories describes releases that
   were never published there. No `npm audit` run will ever match `<= 15.0.7` or `>= 15.0.0`.
   Only `>0.8.1` overlaps versions that exist.
3. **Two of the ranges are internally inconsistent** — a closed vulnerable range `<= 15.0.7`
   with a blank patched field says "fixed in something" and "fixed in nothing" at once — and
   one is written with a Unicode `≥` rather than `>=`.

**The channel is the finding, not the typos.** Self-hosters install this from git or run the
`nightscout/cgm-remote-monitor` Docker image; a push to `dev` or `master` builds and pushes
that image, which is why publication here is a human decision rather than a branch. Almost
nobody gets Nightscout from npm. So the npm coordinates on these advisories are close to
decorative, and the parts that will actually reach an operator are the repository advisory
page, the release notes, and the image tag they pull.

That argues for two things when these drafts are published: state the affected **git tags and
image tags** in the advisory body, where a reader will see them, rather than relying on the
ecosystem fields; and settle whether the npm package is meant to be a supported distribution
channel at all. If it is, it is four years stale and that is its own operator-facing problem.
If it is not, the advisories should say so rather than implying a package coordinate that
resolves to nothing.
