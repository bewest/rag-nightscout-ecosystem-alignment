# The five open security advisories — disposition, and what each one needs from a person

Date: 2026-09-21. Refs measured: `v15.0.7`, **`v15.0.8` = `origin/master` `92d08342`** (the
release operators run), and `origin/dev` `59430336` (15.0.9, unreleased). Storage `mongo:7`
(mongod 7.0.43) throughout. Nothing in this document is read off the source: every cell was
produced by booting the tree and issuing the request, with the control in the same run.

**Disclosure.** Two of the five are unfixed and live on the shipping release. This document
names mechanisms and withholds recipes; the probes are outside version control. The two XSS
advisories are closed in 15.0.8 and are described precisely, because a fixed defect can be.

**Nothing here has been pushed, merged, tagged or published.** Two fix branches exist locally
and unpushed. Publication of the advisories themselves is a human decision and is the point of
this document.

---

## 1. The finding that reframes four of the five

`AUTH_DEFAULT_ROLES` defaults to `readable`; `README.md:243` documents that as "readable by
anyone who knows the URL"; the application raises a persistent *"Nightscout readable by world"*
admin notice at boot. **Anonymous read on a default install is the documented product, not a
defect.** Four of the five advisories argue from anonymous access, so the question that decides
each of them is whether the access survives `AUTH_DEFAULT_ROLES=denied`.

It was measured as a control first: under `denied` every API v1 and v2 data route returns 401,
including `status.json`, identically on `dev` and on v15.0.8 across all 24 paths tested. So the
lockdown is real and "it still worked under `denied`" means something. Full matrix in
[the configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md).

**The answers differ per advisory, which is why asking was worth it.**

## 2. Disposition

| advisory | filed as | verdict | reaches v15.0.8? | register | fix |
|---|---|---|---|---|---|
| `GHSA-gjhc-pc29-r3m6` — `loadRetro` | high, no vector | **real, under `denied` only** | **yes, unfixed** | **BF-79** | `bf/ws-loadretro-auth` `9765e8cd`, local |
| `GHSA-8849-qjp5-vrrj` — `/alarm` | high, no vector | **real, under `denied` only** | **yes, unfixed** | **BF-75** (+ **BF-76** found beside it) | `bf/alarm-socket-scope` `012f1623`, local |
| `GHSA-r3gv-x7fw-j2v5` — operator injection | high, 8.2 | **one of three PoCs stands** | `$where` **yes**, fixed on `dev` only | BF-04, BF-70 (fixed), **BF-71**, **BF-72** | PR #8743, merged to `dev` |
| `GHSA-mjp4-84fw-gj4v` — v3 notes → report | high, no vector | **real, already fixed** | **no** — closed in 15.0.8 | — (**BF-74** found beside it) | shipped |
| `GHSA-5mrq-gpqw-q5v5` — socket `dbAdd` | **critical**, no vector | **real, already fixed; `critical` overstates it** | **no** — closed in 15.0.8 | — | shipped |

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

**Scored twice, deliberately**: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N` = **0.0** on the
shipped default, `…/C:H/I:N/A:N` = **7.5** on a hardened install. The advisory should carry 7.5
and say which configuration it scores. Publishing a high score against the default would alarm
the majority of self-hosters about a payload proven to be a subset of their own public output.

**Affected range is wrong.** `loadRetro` is absent from tags 0.8.1–0.8.4 and first appears in
**0.9.0** — which is also the first tag carrying `DataReceivers` and `authDefaultRoles`. The
handler and the authorization it skips shipped in the same release. `>0.8.1` declares three
releases vulnerable to code they do not contain; it should be `>=0.9.0`.

**The fix** gates the handler on the same `verifyAuthorization` the `authorize` handler already
uses, so an anonymous socket resolves through the ordinary `AUTH_DEFAULT_ROLES` defaults: a
`readable` instance keeps serving anonymous clients, a `denied` one refuses. Verified not to
interact with the failed-login throttle — an empty auth message takes the `!authAttempted`
branch and never records a failure. Ablation reproduces the exact symptom; positive control
confirms the default deployment is intact. Suite 2 311 → 2 315 passing, 0 failing.

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

**The fix's shape was the one genuinely open question in this batch, and it is now decided.**
Two candidates were built and run against live instances. **Shape A** required a successful
`subscribe` *and* read entitlement; measured consequence, on the shipped
`AUTH_DEFAULT_ROLES=readable` default, a client that connects and never subscribes stops
receiving alarms — a behaviour change on the majority configuration. **Shape B** admits the socket
at *connection* time when the deployment's anonymous default role already permits reading, the
same entitlement `AUTH_DEFAULT_ROLES` grants the REST surface, and re-evaluates on `subscribe`.
B closes the `denied` bypass identically and changes nothing on a `readable` install.
**Ben West chose B on 2026-09-21.** The reasons: the marginal content disclosure on the default
was measured at zero, so A removes no disclosure there, only delivery; and the `/alarm` protocol
is in no swagger file and nothing under `docs/`, so its third-party consumers cannot be
enumerated and the failure mode if one exists is a hypo alarm that silently stops arriving. Ben
separately judged the web client to be in practice the only consumer — the fact that would have
argued for A — and chose B anyway as insurance against that judgement being wrong. The branch was
rebuilt on shape B; 51 delivery cases plus 2 ack cases, five ablations, live positive control in
both arms. Full record in
[the GHSA-8849 evidence document](../../60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md) §12.

Two rows of that matrix are worth naming here because they are the easy thing to get wrong: on a
`denied` instance a token that **resolves** but holds no read permission — write-only, or no
permissions at all — must be refused the alarm stream, and is, with the same token's 401 from
`/api/v1/entries.json` recorded in the same run. Gating on "a credential resolved" rather than on
`api:*:read` would let a write-only credential hear every alarm on the instance.

**BF-76 was found while fixing it and is not part of the advisory**: the access-token branch of
`subscribe` registered `socket.on('ack')` with no permission check, so any valid token of any
role could silence every alarm on the instance, with a caller-supplied `silenceTime` that has no
upper bound. That is loss of the safety function the software exists to provide. The
authorization is fixed; the unbounded silence is left open as a product decision.

### 2.3 Operator injection — already reconciled, and partly mis-graded

Of the advisory's three PoCs, **one stands**. `$where` executes anonymously on **v15.0.8**
(measured) and is refused with HTTP 400 on `dev` since PR #8743 (BF-04/BF-70, merged). The
date-window PoC the advisory calls its primary evidence is **not a privilege boundary** — the
allowlisted, documented `find[date][$gte]=0` returns identical records under identical
authorization and every form is 401 under `denied` (**BF-71**, `low`). `$regex` survives as an
**availability** defect rather than the extraction described: one unauthenticated request, 60–71 s
of database CPU against a 22 ms control (**BF-72**).

That advisory also names npm package `cgm-remote-monitor`, which does not exist.

### 2.4 The two XSS advisories — closed in 15.0.8, and the stored-payload question answered

Four write paths across three refs, every "fixed" cell paired with a positive v15.0.7 control
from the same run: `POST /api/v3/treatments`, `PUT`, `PATCH` and socket `dbAdd`/`dbUpdate` all
store the payload verbatim at 15.0.7 and sanitize it at 15.0.8 and `dev`. The fix is broader
than either advisory claims — `PUT /api/v1/treatments/`, `POST /api/v1/food` and
`POST /api/v1/activity` had no purification at 15.0.7 either and now do.

**The question the source could not answer**, and the most useful result of the exercise: a
payload a 15.0.7 server had *already stored* does **not** fire on a patched server. Measured by
inserting it straight into mongo, bypassing every write path, then rendering — the day-to-day
report in real headless Chromium (15.0.7: executes; 15.0.8/`dev`: appears as visible text), and
the dashboard tooltip in a jsdom+d3 harness against each ref's own `renderer.js` (15.0.7: two
`<img onerror>` element nodes; 15.0.8/`dev`: one text node). **So neither advisory needs a
stored-data remediation note — and that is true only because the output-escaping half of the fix
landed alongside the purification half.** Both advisories should say so.

**`critical` on GHSA-5mrq overstates it.** The arithmetic: correcting `UI:P`→`UI:A` moves 9.3 to
9.2, still Critical. What produces Critical is `SC:H/SI:H`, and that is a double count — the
stolen API secret's entire blast radius *is* the Nightscout instance, which is the vulnerable
system and is already counted by `VC:H/VI:H`. There is no subsequent system. Recommended
**high**, `CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N` = **8.4**, matching
GHSA-mjp4, which describes the identical credential theft and is filed `high`.

**The escalation must not be softened.** `lib/client/hashauth.js` stores `sha1(API_SECRET)` in
`localStorage`, and that hash *is* the value the `api-secret` header accepts. Same-origin script
gets admin: all medical data plus treatment writes, on a screen caregivers watch to decide about
insulin. That belongs in `VC:H/VI:H`, which is where it now is.

## 3. What no advisory covers

Four defects were found beside them, none reported by anyone:

- **BF-76** — a read-only token can silence every alarm indefinitely (above).
- **BF-73** — the production error page returns a stack trace with absolute server paths;
  express's `errorhandler` is mounted with its `NODE_ENV === 'development'` guard **commented
  out**, identically at v15.0.7, v15.0.8 and `dev`, and `git log -L` carries those four lines back
  to 2019. Independently reproduced against v15.0.8: the 500 body named six absolute paths and
  the deployment's directory layout. Not reachable unauthenticated by any probe tried.
- **BF-74** — API v3 `settings` writes skip the purifier every other v3 collection gets, on all
  three refs. No first-party sink consumes it, so `low`.
- **BF-77 / BF-78** — two halves of one configuration trap. `TREATMENTS_AUTH=off` silently
  suppresses the "readable by world" warning (exact-string compare against a string the same
  setting appends to) in the one configuration that is both world-readable and anonymously
  writable; and the `careportal` role is inert unless reads are open, because the treatments
  router gates on `api:treatments:read` before the create route. The only configuration in which
  `careportal` works is the only one whose warning is suppressed.

## 3a. The response pack

Everything needed to execute this — the two PR bodies with their `gh pr create` invocations, the
reply to the reporter, and one file per advisory giving the exact metadata changes and the exact
prose to add or replace, plus a dry-runnable script for the metadata patches — is assembled in
[`advisory-response-2026-09/`](./advisory-response-2026-09/README.md).

## 4. What needs a person, in order

1. ~~**Decide the `/alarm` fix's shape.**~~ **Taken 2026-09-21 by Ben West: shape B** — admit at
   *connection* time when the deployment's anonymous default role already permits reading, and
   re-evaluate on `subscribe`. This was the highest-stakes call in the batch — too tight and a
   follower app silently stops receiving hypo alarms, too loose and the bypass stays open — and
   it was deliberately not taken by an agent. Rationale and the A-vs-B comparison are recorded in
   §2.2 above and in the evidence document §12; the branch has been rebuilt on B and the register
   entry updated. **What remains for a person on this item is review of the rebuilt branch**, not
   the shape.
2. **Manually verify the alarm client path.** No automated test drives `hashauth` against a live
   socket. On a `denied` instance: load, authenticate at the prompt, force an alarm, confirm it
   arrives. The fix adds a re-subscribe for exactly this case and it is the one path tests do not
   cover.
3. **Publication sequencing — DECIDED 2026-09-21: the PRs go against `dev`, publicly.** What
   remains is the *ordering*, which still matters: a public PR is itself the disclosure, so the
   advisories should publish at or near the moment the PRs go up, and this repository should be
   pushed after them rather than before. **Patched-version field for both: still empty**, until a
   tagged release carries the fix — naming a `dev` SHA or a PR would tell 15.0.8 operators they
   have somewhere to go, and they do not.
4. **Correct the metadata on all five** — the ranges, the non-existent package name, the blank
   patched field on a closed range, and the severity on GHSA-5mrq. Then decide whether the npm
   coordinates mean anything at all: `nightscout` on npm stops at 14.2.11 (2022), so no 15.x
   range matches a published package, and self-hosters install from git or the Docker image.
5. **Decide BF-73 and BF-78**, both of which are contract questions rather than bugs: whether to
   restore a guard somebody deliberately removed seven years ago, and what `careportal` is for.

*Evidence*:
[configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md) ·
[GHSA-gjhc / loadRetro](../../60-research/remedial/ghsa-gjhc-loadretro-2026-09-21.md) ·
[GHSA-8849 / alarm socket](../../60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md) ·
[XSS pair verification](../../60-research/remedial/ghsa-xss-pair-verification-2026-09-21.md) ·
[BF-04/BF-70 operator allowlist](../../60-research/remedial/bf04-bf70-operator-allowlist-2026-09-18.md) ·
[backfix register](./nightscout-backfix-register.md)
