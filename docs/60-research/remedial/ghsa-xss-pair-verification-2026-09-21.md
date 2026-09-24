# GHSA-5mrq-gpqw-q5v5 and GHSA-mjp4-84fw-gj4v — verification against v15.0.7, v15.0.8 and `dev`

> **Snapshot, 2026-09-21, against `v15.0.7`, `v15.0.8` (`92d08342`) and `origin/dev` `59430336`. Current: both advisories (GHSA-5mrq, GHSA-mjp4) are closed in the released v15.0.8, and the two new findings are open (§6.1 = BF-73, §6.2 = BF-74); the advisory metadata corrections are queue item `ADV-XSS-META`. Contributor-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**

*2026-09-21. Both advisories are **closed in v15.0.8**, root cause and sink,
measured with a positive control on v15.0.7 for every negative result. One
question the advisories do not ask is answered here and it is the one that
matters to operators: a payload stored by a pre-patch server **does not fire on
a patched one**. Two new findings are opened; neither is an XSS.*

**Disclosure rule applied per finding.** §1–§5 describe defects that are
**fixed in the shipping release**, so they are described precisely, payloads
included — a fixed defect can and should be written down. §6.1 is an
information-disclosure defect that is **live on the shipping release**: the
mechanism and the one-line remedy are here, the trigger recipe is not, and the
probe is held outside version control. §6.2 is a storage gap with no
first-party sink and is described in full.

Register: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).
Prior internal work: [report-01-stored-xss](../../reports/security-hotfix-eval-2026/report-01-stored-xss.md).

---

## 1. What was run

Three servers, one per ref, each against its own database on one `mongo:7`
(mongod 7.0) instance, booted with `env -i` so no stray environment variable
could change an answer.

| ref | worktree | version | HTTP | database |
|---|---|---|---|---|
| `v15.0.7` | `crm-adv-1507` | 15.0.7 | 3831 | `ns_1507` |
| `v15.0.8` = `origin/master` | `crm-adv-shipping` | 15.0.8 | 3832 | `ns_1508` |
| `origin/dev` `59430336` | `crm-adv-xss` | 15.0.9 | 3833 | `ns_dev` |

API v3 was driven **end to end**, not through a harness: a role
(`api:treatments:create` + `update` + `read`) and a subject were inserted into
`auth_roles` / `auth_subjects`, the server restarted, the subject's access
token derived as `abbrev + '-' + sha1(sha1hex(API_SECRET) + subjectId)[0:16]`
(`lib/authorization/storage.js:186-190`, `lib/server/enclave.js:71-76`), and
exchanged for a JWT at `GET /api/v2/authorization/request/{token}`. All three
refs issued a working JWT. Every row below is a real HTTP or Socket.IO request
followed by a **direct read of the document out of mongo**.

Canary payload: `<img src=x onerror="document.title='XSS-CANARY-7731'">`.
Oracle: does the substring `onerror` survive into storage.

---

## 2. Differential — four write paths × three refs

| write path | v15.0.7 | v15.0.8 | `dev` |
|---|---|---|---|
| **(a)** `POST /api/v1/treatments` | 200 · `<img src="x">` — **sanitized** (DOMPurify) | 200 · `<img src="x" />` — sanitized (sanitize-html) | 200 · `<img src="x" />` — sanitized |
| **(b)** `POST /api/v3/treatments` (JWT) | 201 · **`onerror` SURVIVES** | 201 · `<img src="x" />` — sanitized | 201 · `<img src="x" />` — sanitized |
| **(c1)** `PUT /api/v3/treatments/{id}` | 200 · **`onerror` SURVIVES** | 200 · sanitized | 200 · sanitized |
| **(c2)** `PATCH /api/v3/treatments/{id}` | 200 · **`onerror` SURVIVES** | 200 · sanitized | 200 · sanitized |
| **(d1)** socket `dbAdd` (main namespace) | ok · **`onerror` SURVIVES** | ok · sanitized | ok · sanitized |
| **(d2)** socket `dbUpdate` (main namespace) | ok · **`onerror` SURVIVES** | ok · sanitized | ok · sanitized |

Both `notes` and `enteredBy` behave identically in every cell.

Row (a) is negative on all three refs. That is not a broken probe: v1 purified
at 15.0.7 too — it is the guard the advisories say v3 and the socket bypassed,
and it is the control the GHSA-mjp4 report itself proposes. The *output* still
differs between refs (`<img src="x">` vs `<img src="x" />`), which is the
DOMPurify → `sanitize-html` swap of PR #8517 showing through, so the row is not
vacuous either.

(d2) was **red for the wrong reason on the first run** — `Unable to process
update` on all three refs, because the probe put `_id` inside `data.data` and
mongod refuses `$set` on an immutable field. Fixed and re-run; the corrected
run is the table above, and its v15.0.7 cell is positive.

### 2.1 The same fix reaches four more write paths

Commit `a6835ca3` is broader than either advisory. Measured, same method:

| write path | v15.0.7 | v15.0.8 | `dev` |
|---|---|---|---|
| `PUT /api/v1/treatments/` | **`onerror` SURVIVES** | sanitized | sanitized |
| `POST /api/v1/food` (`name`) | **`onerror` SURVIVES** | sanitized | sanitized |
| `POST /api/v1/activity` | **`onerror` SURVIVES** | sanitized | sanitized |
| `POST /api/v3/settings` | **`onerror` SURVIVES** | **`onerror` SURVIVES** | **`onerror` SURVIVES** |

The `settings` row is §6.2.

### 2.2 Where the fixes are, and that they are all in 15.0.8

| commit | what | contained in |
|---|---|---|
| `a6835ca3` | `purifyObject` on socket `dbAdd`/`dbUpdate`, v1 `PUT /treatments`, `PUT /profile`, all of `food` and `activity` | tags **`15.0.8`, `v15.0.8`** |
| `da548d2a` | `.html()` → `.text()` / escaping across `renderer.js`, `daytoday.js`, `treatments.js`, `boluscalc.js` | tags **`15.0.8`, `v15.0.8`** |
| `72a2257e` | `lib/api3/shared/writePurifier.js` + calls from v3 `create`/`update`/`patch` | tags **`15.0.8`, `v15.0.8`** |

`lib/api3/shared/writePurifier.js` is **absent at v15.0.7** and present at
v15.0.8 and `dev`, as the brief expected.

### 2.3 Is `operation.js` genuinely on `insert.js`'s path, and is there a second v3 write route?

Yes and no, both checked by reading the router and confirmed by the table
above. `lib/api3/generic/collection.js:40-70` maps exactly four write verbs —
`POST`, `PUT`, `PATCH`, `DELETE` — each to its `*/operation.js`. `insert.js`
and `update/replace.js` are only ever called *from* those operations, after
`writePurifier.purifyWritableDocument(opCtx, doc)`, which is why `insert.js`
contains no purify call of its own. `update/operation.js` purifies **twice**:
once on the body and again after copying the route-derived `identifier` into
the document. The only other Socket.IO namespace in `lib/api3/` is
`/storage` (`lib/api3/storageSocket.js`), which is a read-only broadcaster —
its handlers are `subscribe` and `disconnect`; it has no write path.

One residue worth naming: `patch/operation.js` sets `doc.modifiedBy =
auth.subject.name` **after** purification, and `create` similarly stamps
`subject`. Subject names are operator-created through the admin plane, and
`modifiedBy` is not rendered by any first-party sink, so this is noted, not
filed.

---

## 3. Render side — and the question that matters to operators

Storage purification and output escaping are independent barriers. The
interesting question is not "can a new payload be stored" but **"is a payload
that a 15.0.7 server already stored still dangerous once the operator upgrades
to 15.0.8?"** Operators who ran 15.0.7 have live databases.

Method: the malicious record was written **straight into mongo**, bypassing
every write path, then the render path exercised. Two oracles were used and
they are labelled separately because they are not equally end-to-end.

### 3.1 Day-to-day report sink (`lib/report_plugins/daytoday.js`) — real browser

Headless Chromium against each running server: load `/report`, tick the Notes
option, click Show, wait, read `document.title` and the DOM.

| ref | verdict |
|---|---|
| **v15.0.7** | **`document.title` became `XSS-CANARY-7731`; `window.__xss === 1`; three live `img[onerror]` elements in the document. PAYLOAD EXECUTED.** |
| **v15.0.8** | title unchanged, flag 0, zero `img[onerror]`. The strings `onerror` and `XSS-CANARY-7731` appear in `#daytodaycharts`'s **`textContent`** — rendered as visible text. **No execution.** |
| **`dev`** | identical to v15.0.8. **No execution.** |

This is the single most useful measurement in this document: **a pre-existing
malicious record is inert on a patched server at this sink.** The record was
never re-written, never re-purified, and still does not fire, because
`daytoday.js` now uses `.text(htmlUtils.toTextContent(...))` instead of
`.html(...)` at every one of the ten former sinks in that file.

### 3.2 Dashboard treatment tooltip (`lib/client/renderer.js`) — jsdom harness

A full-browser hover proved flaky against the dashboard (the page does not
reach network idle and the tab was lost mid-run), so this sink was measured in
a **jsdom + real-d3 harness** that loads each ref's actual
`lib/client/renderer.js`, calls `renderer.addTreatmentCircles()`, retrieves the
**real** `mouseover` handler d3 bound to `.treatment-dot`, invokes it with the
malicious datum, and inspects the DOM that `client.tooltip.html(...)` produced.
This is a harness result, not an end-to-end one; what it does *not* stub is the
tooltip string builder or the `.html()` sink itself.

| ref | tooltip DOM | verdict |
|---|---|---|
| **v15.0.7** | two `<img src="x" onerror="…">` **element** nodes | **EXECUTES** |
| **v15.0.8** | `&lt;img src=x onerror=…&gt;` — one text node, zero elements | **INERT** |
| **`dev`** | same as v15.0.8 | **INERT** |

Getting the control right needed one correction: v15.0.7 and v15.0.8 bind the
handler d3-v5 style as `function (d)` while `dev` binds `function (event, d)`.
Calling all three with the same arity produced a *blank* tooltip on the two
older refs — a probe failure that would have read as "not vulnerable". Fixed
by dispatching on `handler.length`.

### 3.3 Both sinks, both barriers

| advisory | root cause (write) closed in 15.0.8? | sink (render) closed in 15.0.8? | pre-existing stored payload still dangerous on 15.0.8? |
|---|---|---|---|
| GHSA-5mrq (socket `dbAdd`/`dbUpdate` → tooltip) | **yes** — measured, control positive at 15.0.7 | **yes** — harness, control positive at 15.0.7 | **no** |
| GHSA-mjp4 (API v3 → day-to-day report) | **yes** — measured, control positive at 15.0.7 | **yes** — real browser, control positive at 15.0.7 | **no** |

So neither advisory needs a "remediate your stored data" note. That is worth
stating explicitly in both, because it is the question an operator upgrading
from 15.0.7 will actually have, and the answer is the reassuring one **only
because `da548d2a` did the output-escaping half**. Had only `a6835ca3` and
`72a2257e` landed, the answer would have been the opposite.

---

## 4. Residual-sink audit on `dev` (and on v15.0.8, since that is what operators run)

`.html(` appears **32 times** across `lib/client/`, `lib/report_plugins/`,
`lib/plugins/`, `views/` on `dev`. Classified:

- **constant markup / internal numerics** — `index.js` loading messages,
  `browser-settings.js:259`, `clock-client.js`, `hashauth.js`, `daytoday.js:74`
  and `:171`, `weektoweek.js:178`, `report_plugins/index.js`. Fine.
- **escaped before the sink** — every `renderer.js` tooltip (`e =
  html.textAsHtml`), `adminnotifiesclient.js` (`textAsHtml` on title and
  message), `boluscalc.js:269` (food `name` and `unit`), `calibrations.js:96`,
  `loopalyzer.js:862` (profile names, interval times), `report_plugins/
  profiles.js` (name, units, dia, timezone, all ranges), `daytoday.js:309`.
- **user-controlled free text reaching an unescaped sink** — **none.**

Rather than trust the prior report's four-file sweep, the whole tree was
re-scanned mechanically for string-concatenated markup taking a variable whose
name looks like user free text (`notes`, `enteredBy`, `reason`, `name`,
`profileName`, `device`, `units`, `timezone`, `message`, `title`, `label`,
`text`, `mealAssist`, `food*`), excluding wrappers:

| ref | unescaped free-text interpolations into markup | files |
|---|---|---|
| **v15.0.7** | **25** | `renderer.js`, `boluscalc.js`, `index.js`, `adminnotifiesclient.js`, `daytoday.js`, `report_plugins/treatments.js`, `report_plugins/profiles.js`, `loopalyzer.js`, `pluginbase.js`, `plugins/openaps.js` |
| **v15.0.8** | **0** (15 matches, every one already wrapped in `e(…)`; plus `index.js:618` `info.label`) | — |
| **`dev`** | **0** (same 15, same wrapper) | — |

The prior report named four files. The sweep that actually shipped covers ten,
including four the report does not name (`adminnotifiesclient.js`,
`report_plugins/profiles.js`, `loopalyzer.js`, `plugins/pluginbase.js` /
`plugins/openaps.js`). Its coverage claim is *understated*, not overstated.

**Attribute contexts** were scanned separately, because that is where the
purifier's pre-filter gap (§5.2) would bite. Every `attr="' + var` site on
`dev` takes a hard-coded literal, a numeric index, or a plugin constant —
`info.type` in `lib/client/index.js:614` and `classes` in
`lib/plugins/pluginbase.js:50` are the only non-literals, and both come from
`lib/plugins/{ar2,loop,openaps}.js` string constants. `profileeditor.js`
builds its rows as real DOM nodes and serializes with `outerHTML`, so attribute
values are escaped by the serializer.

**EJS:** every `<%-` in `views/` is an `include(...)` of a partial or an inline
stylesheet, plus `views/error.html:57` (`<%- errors %>`, server-generated) and
one ternary yielding a literal attribute in `clock.html:33`. No user data.

**Plugin pills:** `lib/plugins/pluginbase.js` renders pill label, value and the
info tooltip through `createTextNode(toTextContent(...))`. `plugins/openaps.js`
builds an OpenAPS `reason` / `mealAssist` string that lands there as text.
Inert.

**API v3 `settings` and `profile` render paths:** `profile` is purified on
write and every profile-editor and profile-report sink is escaped (above).
`settings` is **not purified** — see §6.2 — but has **no first-party render
path**: `grep` finds no consumer of the v3 `settings` collection anywhere in
`lib/client/`, `lib/report_plugins/` or `views/`. It is a storage bucket for
third-party apps.

**Conclusion: no new stored-XSS finding.** That is a clean negative with its
control — the same scan on v15.0.7 returns 25 hits and the same jsdom harness
on v15.0.7 returns `EXECUTES`.

---

## 5. The sanitizer swap itself (`lib/server/purifier.js`)

`lib/server/purifier.js` is **byte-identical between v15.0.8 and `dev`**, so
one set of measurements covers both. All of this was run, not read.

### 5.1 The `img` re-addition

`sanitize-html` 2.17.5, defaults plus `img`. Its default
`allowedAttributes.img` is `["src","srcset","alt","title","width","height",
"loading"]`; `allowedSchemes` is `["http","https","ftp","mailto","tel"]`.

| input | output |
|---|---|
| `<img src=x onerror="document.title=1">` | `<img src="x" />` |
| `<IMG SRC=x OnErRoR=alert(1)>` | `<img src="x" />` |
| `<img src=x\nonerror=alert(1)>` | `<img src="x" />` |
| `<img src="javascript:alert(1)">` | `<img />` |
| `<img srcset="x.png 1x, javascript:alert(1) 2x">` | `<img srcset="x.png 1x" />` |
| `<img src="data:image/svg+xml;base64,…<script>…">` | `<img />` |
| `<img src="http://a/b.png" alt title width height loading>` | preserved verbatim |
| `<svg onload=…>`, `<iframe>`, `<style>`, `<form><input onfocus autofocus>` | dropped entirely |
| `<script>alert(1)</script>tail` | `tail` |
| `<noscript><p title="</noscript><img src=x onerror=…>">` | `<p></p>` |
| `<xmp><p title="</xmp><img src=x onerror=…>">` | `<img src="x" />">` — shell kept, handler gone |
| `<b>bold</b> and <a href="https://example.com">link</a>` | preserved |

No attribute-level escape hatch was found. `data:` and `javascript:` are
rejected on both `src` and `srcset`. The widening is exactly what the header
claims: the `<img>` shell survives, everything dangerous about it does not.

### 5.2 The bounds — fail-closed, not a bypass

A string over the sanitizer's size budget is **not** passed through unsanitized. `sanitizeStringWithBudget` **throws `RangeError`**, and the throw
propagates out of every write path as a refusal (the uncaught throw is what BF-73 concerns):

| probe (oversize markup-containing string) | v15.0.7 | v15.0.8 | `dev` |
|---|---|---|---|
| `POST /api/v1/treatments` | 200, stored, but DOMPurify stripped `onerror` | **HTTP 500, not stored** | **HTTP 500, not stored** |
| `POST /api/v3/treatments` | 201, **stored with `onerror`** | **HTTP 500, not stored** | **HTTP 500, not stored** |
| socket `dbAdd` | ok, **stored with `onerror`** | **`[]`, not stored** | **`[]`, not stored** |

Fail-closed, on every path, measured. The length bound is not a bypass.

It does, however, produce an unhandled exception on an ordinary request, which
is how §6.1 was found.

The **aggregate** budget behaves the same way: 40 fields of 2 KiB of markup in
one document also throws, so markup cannot be split across many small fields to
evade the per-string cap.

### 5.3 The `POSSIBLE_HTML_MARKUP` pre-filter — evadable, and it does not matter

`/<[!/?A-Za-z]/` gates the sanitizer; a string that does not match is returned
untouched. Three classes evade it, and all three are stored **verbatim on all
three refs, including `dev`**:

| payload | stored verbatim? | executes at any sink? |
|---|---|---|
| `x" onerror="document.title='…'` (no `<` at all) | yes, all refs | **no** — no first-party sink puts stored text in an attribute context (§4) |
| `&lt;img src=x onerror=…&gt;` | yes, all refs | **no** — `textAsHtml` = `escapeText(decodeHTML(s))` re-encodes it; `.text()` sinks set it as textContent |
| `< img src=x onerror=…>` (space after `<`) | yes, all refs | **no** — HTML's data state does not start a tag on `< ` |

Verified at the sink, not argued: all three payloads were pushed through the
renderer harness on all three refs and every one came back **INERT (text
only)** — including on **v15.0.7**, which is why none of them is a finding.

This is precisely the defence-in-depth argument the purifier's own header
makes, and it now has a measurement behind it: the sanitizer is evadable at the
margin, and it does not matter because the output side is the barrier that
actually holds.

---

## 6. New findings

### 6.1 Unconditional `errorhandler` returns a full stack trace with absolute paths

> **DISCLOSURE. This is live on the shipping release and this repository is
> public.** The mechanism and the fix are one line and are given; the request
> that triggers it is not written down here, and the probe is held outside
> version control.

`lib/server/app.js:388-391` mounts express's `errorhandler` with the
`NODE_ENV === 'development'` guard **commented out**:

```js
// Handle errors with express's errorhandler, to display more readable error messages.
var errorhandler = require('errorhandler');
//if (process.env.NODE_ENV === 'development') {
app.use(errorhandler());
//}
```

Identical at **v15.0.7 (`:343`), v15.0.8 (`:388`) and `dev` (`:388`)** — this is
not a regression, it is long-standing. With `NODE_ENV=production` set, any
exception that escapes to express returns an HTML page containing the error
message and `<ul id="stacktrace">` with **absolute server filesystem paths**
and the internal call chain. Observed frames named `lib/server/purifier.js` and
the deployment's full directory path.

Most v1 errors are caught and returned as JSON (`{"status":500,"message":"Mongo
Error",…}`), so this is not reachable from the unauthenticated read surface by
any of the seven malformed-query probes tried. It **is** reachable by a caller
holding a write credential — and §5.2's `RangeError`, introduced by the very
hardening that closes these two advisories, is a reliable trigger. So the fix
for the XSS pair created an easy path to a pre-existing information leak.

CWE-209. Severity low-to-moderate: paths and module layout, not data or
credentials, and it costs a write token. Remedy: restore the guard, or replace
`errorhandler` with a handler that logs server-side and returns a bare 500.

### 6.2 API v3 `settings` writes are not purified

`PURIFIED_COLLECTIONS` in `lib/api3/shared/writePurifier.js` is
`['devicestatus','entries','food','profile','treatments']`. `settings` is
enabled in `app.set('enabledCollections', …)` (`lib/api3/index.js:67`) and is
the only enabled collection absent from the list. Measured: `POST
/api/v3/settings` stores `<img src=x onerror=…>` verbatim on **v15.0.7,
v15.0.8 and `dev`** alike.

No first-party sink consumes it (§4), so this is not an XSS in Nightscout. It
is an asymmetry: the fix purifies five of six v3 collections and the file
carries no comment saying why the sixth is excluded. Third-party clients that
read `api/v3/settings` and render it are on their own. Whether purification is
even correct for `settings` — which stores UI configuration, where entity
re-encoding could corrupt values — is a decision, not an oversight to be
patched blind, so no fix is proposed.

---

## 7. Recommended advisory metadata

Every score below was **computed**, not estimated: CVSS 3.1 by the published
formula (reproduced by hand and cross-checked against the `cvss` library) and
CVSS 4.0 by the `cvss` library's MacroVector lookup. The intermediate numbers
are shown so the argument can be checked.

### 7.1 The severity argument, once, for both

The two advisories are the **same defect class with the same privilege
requirement and the same escalation**, differing only in sink:

- Both need a token with `api:treatments:create` (or the socket's
  `write_treatment`) — a credential operators hand to pumps, uploaders and
  bridges. Widely held, but held, and revocable. **`PR:L`.**
- Both need a viewer to do something. GHSA-5mrq needs a hover on a *specific*
  treatment dot; GHSA-mjp4 needs the report opened with the Notes option on
  and Show clicked. Neither happens by loading the landing page. **`UI:A`**
  (CVSS 4.0 active) / **`UI:R`** (CVSS 3.1), not `UI:P`.
- **The escalation is real and should not be softened.** `lib/client/
  hashauth.js:335-340` stores `sha1(API_SECRET)` in `localStorage` under
  `apisecrethash`, and that sha1 **is** the credential the `api-secret` header
  accepts — every v1 write in this document was authenticated with exactly
  that value. Same-origin script reads it and has admin: all medical data, and
  write access to treatments, on a screen caregivers watch to decide about
  insulin. **`VC:H/VI:H`** / **`C:H/I:H`**.

**Where `critical` comes from, and why it does not survive.** GHSA-5mrq's
filed vector scores **9.3 Critical**, so the label is arithmetically
consistent with the vector. `UI:P` is not the overstatement —
correcting `UI:P` → `UI:A` moves the score only
9.3 → **9.2**, still Critical. What actually produces the Critical band is
**`SC:H/SI:H`**, and that is the metric that is wrong: it double-counts. The
stolen API secret's entire blast radius *is* the Nightscout instance, and that
instance is the vulnerable system, already fully counted by `VC:H/VI:H`. There
is no third system. Drop `SC`/`SI` to `N` and the same facts give **8.4
High** — which is exactly the shape GHSA-mjp4 proposed for itself, and agrees
with the CVSS 3.1 score of **8.7 High**.

Computed, so the argument can be checked:

| vector | 4.0 score |
|---|---|
| `…/PR:L/UI:P/VC:H/VI:H/VA:N/SC:H/SI:H/SA:N` — **as filed on GHSA-5mrq** | **9.3 Critical** |
| `…/PR:L/UI:A/VC:H/VI:H/VA:N/SC:H/SI:H/SA:N` — UI corrected only | 9.2 Critical |
| `…/PR:L/UI:P/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N` — **as proposed in GHSA-mjp4's text** | 8.5 High |
| `…/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N` — **recommended for both** | **8.4 High** |
| `…/PR:L/UI:A/VC:N/VI:N/VA:N/SC:H/SI:H/SA:N` — escalation counted *only* as subsequent | 6.2 Medium |

The one deployment where `SC` would not be `N` is a site whose API secret is
reused elsewhere, or whose Nightscout origin is shared with another
application. That is an operator-specific aggravation, not a property of the
software, and belongs in the advisory's text rather than its base vector.

### 7.2 GHSA-mjp4-84fw-gj4v — Stored XSS in day-to-day report via API v3 treatment notes

| field | current | recommended |
|---|---|---|
| vulnerable range | `<= 15.0.7` | `<= 15.0.7` — **confirmed**, positive on v15.0.7 on all three v3 verbs |
| patched versions | **blank** | **`15.0.8`** |
| severity | high | **high** — unchanged |
| CVSS 4.0 | none set | **`CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N` = 8.4 High** (the vector its own text proposes, with `UI:P` → `UI:A`) |
| CVSS 3.1 | none | **`CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:N` = 8.7 High** |
| CWE | CWE-79 | CWE-79 — unchanged |

**The blank `patched_versions` against a `<= 15.0.7` range resolves to
`15.0.8`, and 15.0.8 closes both halves.**

- **Root cause:** `72a2257e` adds `lib/api3/shared/writePurifier.js` and calls
  it from all three v3 write operations. Measured: `onerror` survives on
  v15.0.7 and does not on v15.0.8, for `POST`, `PUT` and `PATCH` alike (§2).
- **Sink:** `da548d2a` replaces `.html(treatment.notes)` at
  `daytoday.js:730` and the food-text `.html(text)` at `:719` — and eight more
  `.text()` sites in the same file — with `toTextContent(...)`. Measured in a
  real headless browser: the payload executes on v15.0.7 and does not on
  v15.0.8 (§3.1).

**Add to the advisory text:** a record stored by a 15.0.7 server does **not**
fire on 15.0.8. No stored-data remediation is required after upgrade (§3).

### 7.3 GHSA-5mrq-gpqw-q5v5 — Stored XSS through WebSocket treatment writes

| field | current | recommended |
|---|---|---|
| vulnerable range | `<= 15.0.7` | `<= 15.0.7` — **confirmed**, positive on v15.0.7 for both `dbAdd` and `dbUpdate` |
| patched versions | `15.0.8` | `15.0.8` — **confirmed correct**, root cause and sink |
| severity | **critical** | **high** |
| CVSS 4.0 | `…/UI:P/VC:H/VI:H/VA:N/SC:H/SI:H/SA:N` = 9.3 | **`CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N` = 8.4 High** |
| CVSS 3.1 | none | **`CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:N` = 8.7 High** |
| CWE | CWE-79 | CWE-79 — unchanged |

`a6835ca3` adds `ctx.purifier.purifyObject` to both socket handlers —
measured, positive control on v15.0.7 for `dbAdd` and `dbUpdate` (§2) — and
`da548d2a` wraps `notes` and `enteredBy` in the treatment and announcement
tooltips with `html.textAsHtml` — measured against each ref's real
`renderer.js`, positive control on v15.0.7 (§3.2).

Two corrections to the advisory's own text, both measured:

- Its PoC uses `onload` on a `data:` GIF rather than `onerror`. 15.0.8's
  sanitizer strips `onload` exactly as it strips `onerror`, **and** rejects the
  `data:` scheme on `img src` outright (§5.1) — the PoC as written is closed
  twice over.
- Its "Root cause and affected code" section is right about `websocket.js`
  and `renderer.js` but understates the blast radius. The same commit also
  fixed `PUT /api/v1/treatments/`, `PUT /api/v1/profile/`, and both verbs of
  `food` and `activity`, which had **zero** purification at v15.0.7 — measured
  in §2.1.

**Add to the advisory text:** the same no-remediation-needed note as §7.2.

### 7.4 Both advisories

- `patched_versions` reads **`15.0.8`** on both. All three closing commits
  (`a6835ca3`, `da548d2a`, `72a2257e`) are contained in tags `15.0.8` and
  `v15.0.8`, verified by `git tag --contains`.
- Both should carry the **same** severity and the same vector shape. Whatever
  band is chosen, two advisories describing one escalation must not disagree
  about it — the current state (one `critical` with `SC:H/SI:H`, one `high`
  with `SC:N/SI:N`, for the same credential theft) is the thing that most needs
  fixing.
- Both should state that **no stored-data remediation is needed** after
  upgrading from 15.0.7, and credit the reason: `da548d2a`'s output escaping,
  not the write purifier. Had only `a6835ca3` and `72a2257e` landed, the answer
  would have been the opposite.
