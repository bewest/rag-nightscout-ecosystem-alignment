# The five open security advisories — disposition, and what each one needs from a person

*Contributor-facing. Living document: kept current until all five advisories are closed.*

**State as of 2026-09-22.** Refs: `v15.0.7`; **`v15.0.8` = `origin/master` `92d08342`**, the
release operators run; `origin/dev` `74fc6619` (15.0.9, unreleased — 308 commits ahead of
`master`, `git -C externals/cgm-remote-monitor-official rev-list --count official/master..official/dev`).
The verdicts below were **reproduced** on 2026-09-21 against `v15.0.7`, `v15.0.8` and
`origin/dev` `59430336` (the tree the fix branches were cut from), storage `mongo:7` (mongod
7.0.43) throughout: every cell was produced by booting the tree and issuing the request, with the
control in the same run. None is read-derived.

**Status in one line.** The fixes for the two live advisories **merged into `dev` on 2026-09-21**
(#8744, #8745) and are **not released**: **v15.0.8 is still affected by GHSA-gjhc and
GHSA-8849.** No advisory has been published, none is in triage, no CVE is assigned, and the
reporter replies and metadata corrections are drafted and unsent (§4).

**Disclosure.** GHSA-gjhc, GHSA-8849 and BF-72 are live on the shipping release. This document
names mechanisms and withholds recipes; the probes are outside version control. The two XSS
advisories are closed in 15.0.8 and are described precisely, because a fixed defect can be.

---

## 1. The control that decides four of the five

`AUTH_DEFAULT_ROLES` defaults to `readable`; `README.md:243` documents that as "readable by
anyone who knows the URL"; the application raises a persistent *"Nightscout readable by world"*
admin notice at boot. **Anonymous read on a default install is the documented product, not a
defect.** Four of the five advisories argue from anonymous access, so the question that decides
each of them is whether the access survives `AUTH_DEFAULT_ROLES=denied`.

The control: under `denied` every API v1 and v2 data route returns 401, including
`status.json`, identically on `dev` and on v15.0.8 across all 24 paths tested. API v3 is 401
anonymously on every configuration. So the lockdown is real and "it still worked under `denied`"
means something. Full matrix in
[the configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md).

### Flag control — both arms

| advisory | `AUTH_DEFAULT_ROLES=readable` (shipped default) | `AUTH_DEFAULT_ROLES=denied` (hardened) | defect? |
|---|---|---|---|
| `GHSA-gjhc` `loadRetro` | reachable; **zero marginal disclosure** — payload is a strict subset of the anonymous REST answer. CVSS 0.0 | **576 device-status records** to a socket that never authorized, with every REST read 401 in the same run. CVSS 7.5 | **yes — survives `denied`** |
| `GHSA-8849` `/alarm` | all five event classes delivered; **zero marginal content**, adds real-time push with no request trace. CVSS 5.3 | all five delivered; server replies `read:false` and delivers anyway. CVSS 7.5 | **yes — survives `denied`** |
| `GHSA-r3gv` date-window PoC | full history returned — identical to an ordinary documented date-range query | every form 401 | **no** — not a boundary (BF-71, `low`) |
| `GHSA-r3gv` `$where` | executes anonymously on v15.0.8 | 401 anonymously; reachable with a read token (matrix §4) | yes — merged to `dev` (#8743), not released |
| `GHSA-r3gv` `$regex` | one unauthenticated request costs minutes of database CPU | 401 anonymously, as every v1 read is under `denied` (not separately probed) | yes, as availability (BF-72) — open |
| `GHSA-mjp4`, `GHSA-5mrq` XSS | needs a write-scoped token either way | same | yes — **released** fix in 15.0.8 |

## 2. Disposition

Status words: `open` · `merged` (in `dev`, not released) · `released` (in a tagged release).

| advisory | filed as | verdict | v15.0.8 | register | fix |
|---|---|---|---|---|---|
| `GHSA-gjhc-pc29-r3m6` — `loadRetro` | high, no vector | **real, under `denied` only** | **affected** | **BF-79** | **merged** — PR #8744, 2026-09-21 |
| `GHSA-8849-qjp5-vrrj` — `/alarm` | high, no vector | **real, under `denied` only** | **affected** | **BF-75** (+ **BF-76** beside it) | **merged** — PR #8745, 2026-09-21 |
| `GHSA-r3gv-x7fw-j2v5` — operator injection | high, 8.2 | **one of three PoCs stands, one is availability** | `$where` **affected**; `$regex` **affected** | BF-04, BF-70 (merged), **BF-71**, **BF-72** (open) | `$where`: **merged** — PR #8743; `$regex`: none |
| `GHSA-mjp4-84fw-gj4v` — v3 notes → report | high, no vector | **real, already fixed** | **not affected** | — (**BF-74** beside it) | **released** in 15.0.8 |
| `GHSA-5mrq-gpqw-q5v5` — socket `dbAdd` | **critical**, no vector | **real, already fixed; `critical` overstates it** | **not affected** | — | **released** in 15.0.8 |

### 2.1 `loadRetro` — BF-79

Reproduced on v15.0.7, v15.0.8 and `dev`, both arms. Under `denied`, with every REST read
answering 401 in the same run, an unauthenticated socket that **never sends `authorize`**
receives 576 device-status records — 24 h of loop suggestions, pump battery and reservoir,
bolusing/suspended state, plus `pump.pumpID` (serial), `pump.manufacturer`, `pump.model`,
`uploader.name` (usually a person's given name) and the rig hostname.

Three things the advisory does not say and should:

- **No configuration stops it.** `denied`, `status-only`, `AUTHENTICATION_PROMPT_ON_LOAD=true`
  and `TREATMENTS_AUTH=off` were each tested; all still return 576. The only setting that
  touches the path, `DEVICESTATUS_DAYS=2`, **doubles** the leak to 1 150 records.
- **It returns more than an authorized reader gets.** `authorize` trims to 10 per device-and-type,
  so a legitimate reader's `dataUpdate` carried 20 records where the anonymous socket got 576 —
  **28.8×**. The bound is the cache's 24 h retention, not `loadedMills`, which is ignored.
- **On the `readable` default the marginal disclosure is zero.** Measured field by field: every
  `_id` the socket returned is in the anonymous REST answer, no JSON field path exists only on
  the socket, and REST returns *more* (1 730 vs 574). The payload is a strict subset of what the
  instance already serves the public by design.

**Scored for both arms**: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N` = **0.0** on the
shipped default, `…/C:H/I:N/A:N` = **7.5** on a hardened install. The advisory should carry 7.5
and say which configuration it scores. Publishing a high score against the default would alarm
the majority of self-hosters about a payload proven to be a subset of their own public output.

**Affected range is wrong.** `loadRetro` is absent from tags 0.8.1–0.8.4 and first appears in
**0.9.0** — which is also the first tag carrying `DataReceivers` and `authDefaultRoles`. The
handler and the authorization it skips shipped in the same release. `>0.8.1` declares three
releases vulnerable to code they do not contain; it should be `>=0.9.0`.

**The fix (merged, #8744)** gates the handler on the same `verifyAuthorization` the `authorize`
handler already uses, so an anonymous socket resolves through the ordinary `AUTH_DEFAULT_ROLES`
defaults: a `readable` instance keeps serving anonymous clients, a `denied` one refuses. Verified
not to interact with the failed-login throttle — an empty auth message takes the
`!authAttempted` branch and never records a failure. Ablation reproduces the exact symptom;
positive control confirms the default deployment is intact. Suite 2 311 → 2 315 passing, 0
failing on the branch. The merged head is the measured commit `9765e8cd`, unchanged.

### 2.2 `/alarm` — BF-75, and BF-76 beside it

All five event classes (`notification`, `announcement`, `alarm`, `urgent_alarm`, `clear_alarm`)
reach a never-subscribed anonymous socket, on v15.0.8 and `dev`, in both arms, each caused
through the real server path. Under `denied` the server replies to a subscribing anonymous
socket `{"success":true,…,"read":false}` — **it computes the correct decision, tells the client,
and delivers anyway**. `subscribe` gates acknowledgement rights and nothing on the receive side.

No setting stops it, and the advisory's `authenticationPromptOnLoad` claim is confirmed exactly:
the subscribe is refused, the socket is **not** disconnected, and it still receives everything.

**Marginal disclosure on the `readable` default is zero in content** — every field is in
`treatments.json`, `entries.json` or `status.json`. What it adds there is real-time push with no
request rate and no access-log trace, plus a server-labelled "hypo/hyper right now" a poller
would have to re-derive. Scored `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N` = **7.5** on the
hardened configuration; **5.3** on the default. Range `>=15.0.0` is correct; first affected
release is 15.0.0 (`89d7eb679`, "Alarm sockets for api v3").

**Fix shape: B, decided by the maintainer (Ben West) on 2026-09-21; merged as #8745.** Shape B
admits the socket at *connection* time when the deployment's anonymous default role already
permits reading — the same entitlement `AUTH_DEFAULT_ROLES` grants the REST surface — and
re-evaluates on `subscribe`. It closes the `denied` bypass and changes nothing on a `readable`
install. The alternative, shape A (require a successful `subscribe` *and* read entitlement), was
built and measured: on the shipped `readable` default, a client that connects and never
subscribes stops receiving alarms. B was chosen because the marginal content disclosure on the
default is zero, so A would remove delivery there without removing any disclosure; and because the
`/alarm` protocol is in no swagger file and nothing under `docs/`, so its third-party consumers
cannot be enumerated, and the failure mode if one exists is a hypo alarm that silently stops
arriving. The maintainer judged the web client to be the only consumer in practice and chose B as
insurance against that judgement being wrong. 51 delivery cases plus 2 ack cases, five ablations,
live positive control in both arms. Full record in
[the GHSA-8849 evidence document](../../60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md) §12.
The branch picked up an integration merge of `dev` (`a198e308`) on the way in that was **not**
re-measured.

Two rows of that matrix are the easy thing to get wrong: on a `denied` instance a token that
**resolves** but holds no read permission — write-only, or no permissions at all — must be
refused the alarm stream, and is, with the same token's 401 from `/api/v1/entries.json`
recorded in the same run. Gating on "a credential resolved" rather than on `api:*:read` would
let a write-only credential hear every alarm on the instance.

**BF-76 was found while fixing it and is not part of the advisory**: the access-token branch of
`subscribe` registered `socket.on('ack')` with no permission check, so any valid token of any
role could silence every alarm on the instance, with a caller-supplied `silenceTime` that has no
upper bound. That is loss of the safety function the software exists to provide. The
authorization is **merged** in #8745; the unbounded silence is left open as a product decision.

**BF-80 is the fix's cost, and it is now on `dev`**: once `/alarm` delivery depends on a
resolved entitlement, the failed-login delay list applies to it, so a socket from an address
that recently failed a login — a household shares one public IP — can go silently undelivered
for tens of seconds. Open; not on 15.0.8, because 15.0.8 does not carry the fix.

### 2.3 Operator injection — one PoC stands, one is availability, one is not a boundary

Of the advisory's three PoCs, **one stands as filed**. `$where` executes anonymously on
**v15.0.8** (measured) and is refused with HTTP 400 on `dev` since PR #8743 (BF-04/BF-70,
merged, not released). The date-window PoC the advisory calls its primary evidence is **not a
privilege boundary** — an ordinary, documented date-range query returns identical records under
identical authorization, and every form is 401 under `denied` (**BF-71**, `low`). `$regex`
survives as an **availability** defect rather than the extraction described: one unauthenticated
request, 60–71 s of database CPU against a 22 ms control (**BF-72**, open, live on 15.0.8 and
`dev`, no fix; whether Nightscout's security contact process is invoked is a pending decision,
queue `BFQ-72`). Mechanism only here.

That advisory also names npm package `cgm-remote-monitor`, which does not exist.

### 2.4 The two XSS advisories — closed in 15.0.8, and the stored-payload question answered

Four write paths across three refs, every "fixed" cell paired with a positive v15.0.7 control
from the same run: `POST /api/v3/treatments`, `PUT`, `PATCH` and socket `dbAdd`/`dbUpdate` all
store the payload verbatim at 15.0.7 and sanitize it at 15.0.8 and `dev`. The fix is broader
than either advisory claims — `PUT /api/v1/treatments/`, `POST /api/v1/food` and
`POST /api/v1/activity` had no purification at 15.0.7 either and now do.

**Stored data needs no remediation.** A payload a 15.0.7 server had *already stored* does
**not** fire on a patched server. Measured by inserting it straight into mongo, bypassing every
write path, then rendering — the day-to-day report in real headless Chromium (15.0.7: executes;
15.0.8/`dev`: appears as visible text), and the dashboard tooltip in a jsdom+d3 harness against
each ref's own `renderer.js` (15.0.7: two `<img onerror>` element nodes; 15.0.8/`dev`: one text
node). That is true only because the output-escaping half of the fix landed alongside the
purification half. Both advisories should say so.

**`critical` on GHSA-5mrq overstates it.** Correcting `UI:P`→`UI:A` moves 9.3 to 9.2, still
Critical. What produces Critical is `SC:H/SI:H`, and that is a double count — the stolen API
secret's entire blast radius *is* the Nightscout instance, which is the vulnerable system and is
already counted by `VC:H/VI:H`. There is no subsequent system. Recommended **high**,
`CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N` = **8.4**, matching GHSA-mjp4,
which describes the identical credential theft and is filed `high`.

**The escalation must not be softened.** `lib/client/hashauth.js` stores `sha1(API_SECRET)` in
`localStorage`, and that hash *is* the value the `api-secret` header accepts. Same-origin script
gets admin: all medical data plus treatment writes, on a screen caregivers watch to decide about
insulin. That belongs in `VC:H/VI:H`, which is where it now is.

## 3. What no advisory covers

Found beside them, none reported by anyone. Defect facts live in the
[register](./nightscout-backfix-register.md).

- **BF-76** — any valid token could silence every alarm indefinitely (above). Authorization
  **merged** (#8745); unbounded `silenceTime` open.
- **BF-80** — the `/alarm` fix couples delivery to the failed-login delay list (above). Open.
- **BF-73** — the production error page returns a stack trace with absolute server paths;
  express's `errorhandler` is mounted with its `NODE_ENV === 'development'` guard **commented
  out**, identically at v15.0.7, v15.0.8 and `dev`, and `git log -L` carries those four lines back
  to 2019. Reproduced against v15.0.8: the 500 body named six absolute paths and the deployment's
  directory layout. Not reachable unauthenticated by any probe tried. Open, needs a decision.
- **BF-74** — API v3 `settings` writes skip the purifier every other v3 collection gets, on all
  three refs. No first-party sink consumes it, so `low`. Open, needs a decision.
- **BF-77 / BF-78** — two halves of one configuration trap. `TREATMENTS_AUTH=off` silently
  suppressed the "readable by world" warning (exact-string compare against a string the same
  setting appends to) in the one configuration that is both world-readable and anonymously
  writable — **BF-77 merged** in #8746, with the second notice wording approved by the
  maintainer (merged head `91ed8d95` includes an integration merge of `dev` that was not
  re-measured). And the `careportal` role is inert unless reads are open, because the treatments
  router gates on `api:treatments:read` before the create route — **BF-78 open**, a product
  decision about what `careportal` is for.
- **BF-81** — the shared root: `AUTH_DEFAULT_ROLES` is the access-control boundary,
  `AUTHENTICATION_PROMPT_ON_LOAD` is not, and nothing documents the difference. The GHSA-8849
  reporter's own patch keyed on the wrong one of the two. Open; documentation.

## 3a. The response pack

The PR bodies as sent, the drafted reporter replies, one file per advisory giving the exact
metadata changes and prose, and a dry-run script for the metadata patches are in
[`advisory-response-2026-09/`](./advisory-response-2026-09/README.md).

## 4. What still needs a person

Taken already: the `/alarm` fix shape (B, 2026-09-21); the vehicle (public PRs against `dev`,
2026-09-21); the BF-77 notice wording (merged with #8746). All three PRs are merged. Outstanding,
in order:

1. **Manually verify the alarm client path.** No automated test drives `hashauth` against a live
   socket, and merging did not perform this. On a `denied` instance built from `dev`: load,
   authenticate at the prompt, force an alarm, confirm it arrives. The fix adds a re-subscribe
   for exactly this case and it is the one path tests do not cover — and the path that could
   silently drop a real hypo alarm.
2. **Post the GHSA-gjhc reply** ([draft](./advisory-response-2026-09/advisories/ghsa-gjhc-comment.md))
   — the range correction to `>=0.9.0` and the separation of reachability from impact.
3. **Send the GHSA-8849 reporter reply**
   ([draft](./advisory-response-2026-09/pull-requests/reply-to-reporter-ghsa-8849.md)) on their PR
   in the private advisory fork, and credit them on publication.
4. **Correct the metadata on all five** — the ranges, the non-existent package name, the blank
   patched field on a closed range, and the severity on GHSA-5mrq
   ([per-advisory files](./advisory-response-2026-09/advisories/README.md);
   `apply-metadata.sh` is a dry run by default and never touches `state`). Then decide whether the
   npm coordinates mean anything at all: `nightscout` on npm stops at 14.2.11 (2022), so no 15.x
   range matches a published package, and self-hosters install from git or the Docker image.
   **Patched-version field for GHSA-gjhc, GHSA-8849 and GHSA-r3gv: leave empty** until a tagged
   release carries the fix — naming a `dev` SHA or a PR would tell 15.0.8 operators they have
   somewhere to go, and they do not.
5. **Publication timing.** The fixes are public in `dev` diffs while 15.0.8 is affected, so the
   defects are legible without the advisory that tells operators whether they are affected.
   Publish at or near the release that carries the fixes; a 15.0.8 security release remains
   available — all three commits cherry-pick cleanly onto `v15.0.8` and its suite goes
   1533 → 1588, 0 failing (measured 2026-09-21) — and choosing between that and releasing `dev`
   is the release-train decision (queue `RT-0`).
6. **Decide BF-73, BF-74 and BF-78**: whether to restore a guard somebody deliberately removed
   seven years ago; whether v3 `settings` should be purified; and what `careportal` is for.
7. **BF-72**: decide whether Nightscout's security contact process is invoked (queue `BFQ-72`).
8. **BF-81**: document which setting is the boundary.

*Evidence*:
[configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md) ·
[GHSA-gjhc / loadRetro](../../60-research/remedial/ghsa-gjhc-loadretro-2026-09-21.md) ·
[GHSA-8849 / alarm socket](../../60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md) ·
[XSS pair verification](../../60-research/remedial/ghsa-xss-pair-verification-2026-09-21.md) ·
[BF-04/BF-70 operator allowlist](../../60-research/remedial/bf04-bf70-operator-allowlist-2026-09-18.md) ·
[backfix register](./nightscout-backfix-register.md) ·
[`queue/work-queue.yaml`](../../../queue/work-queue.yaml) items `ADV-RETRO`, `ADV-ALARM`,
`ADV-XSS-META`, `ADV-CONFIG`, `BFQ-72`
