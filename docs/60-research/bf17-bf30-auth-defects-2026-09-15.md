# BF-17 and BF-30 — two authentication defects in shipping `cgm-remote-monitor`

**Date**: 2026-09-15
**Branch**: `bf/auth` in `externals/work/crm-bf-auth`, based on `origin/dev` (`a8888f0d`)
**Commits**: `a26ba416` (BF-30), `64db1f35` (BF-17) — disjoint file sets, each verified to
cherry-pick onto `origin/dev` alone with its own tests passing.
**Environment**: node v24.15.0, MongoDB 7 on port 27031, full suite 2047 passing / 3 pending /
0 failing.

Both defects were previously recorded as *not reproduced against a live instance*. Both are now
reproduced against a running server. One of the two register entries cites the wrong mechanism
for `dev`, and the register's first-choice fix for BF-30 is refuted by measurement. Details in
§1.1 and §2.2.

---

## 1. BF-30 — the auth-failure delay never engages

### 1.1 The register cites `TRUST_PROXY`, which does not exist on `dev`

The register locates the defect at `lib/authorization/delaylist.js` plus "the `TRUST_PROXY`
default in `lib/server/env.js:43`", and describes `data.ip` as coming from
`createClientIP(env.trustProxy)`.

On `origin/dev` there is no `TRUST_PROXY` at all. `grep -rn "TRUST_PROXY\|trustProxy\|createClientIP" lib/`
returns exactly one line, and it is unrelated (`lib/server/app.js:52`, `app.enable('trust proxy')`,
which affects `req.secure`). `lib/server/env.js:43` is `env.debug = {`. `createClientIP` is a
function on the multitenancy seam branch, not on `dev`.

What `dev` actually does is **weaker than the register describes**, not stronger.
`lib/authorization/index.js:9-12`:

```js
function getRemoteIP (req) {
  const address = forwarded(req, req.headers);
  return address.ip;
}
```

`forwarded-for`'s signature is `parse(obj, headers, whitelist)`. The third argument is the proxy
whitelist, and it is not passed — here or in the three other copies of this function
(`lib/api3/security.js`, `lib/server/websocket.js`, `lib/api3/alarmSocket.js`). With no
whitelist, the package returns the first address out of the first of these headers it finds, and
only checks that the values parse as IP addresses:

`fastly-client-ip`, `x-forwarded-for`, `z-forwarded-for`, `forwarded`, `x-real-ip`.

So the address is client-controlled unconditionally — there is no configuration involved, no
default to narrow, and nothing an operator can set to change it. Measured directly against
the module:

```
no header             -> 203.0.113.9     (the real peer)
client sets XFF       -> 198.51.100.1
client sets X-Real-IP -> 198.51.100.2
client sets Fastly    -> 198.51.100.3
```

**This does not refute the defect — it strengthens it, and it moves where the fix goes.** The
register's fix option 3 ("narrow the `TRUST_PROXY` default with a documented migration") is not
available on `dev`, because there is no such default to narrow.

### 1.2 Reproduction

Harness: a real `express` app with `lib/api/` mounted, booted through `lib/server/bootevent`
against MongoDB, driven with `supertest`. `AUTH_FAIL_DELAY` set to 200 ms. Each row is the wall
time of one `GET /api/v1/entries.json` carrying a wrong `api-secret` header.

Against the shipping code:

| scenario | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| A. fixed forwarded address, same wrong secret | 26 ms | 192 ms | 202 ms | 201 ms |
| B. **rotating** forwarded address, same wrong secret | 4 ms | 3 ms | 3 ms | 2 ms |
| C. fixed forwarded address, different secret each time | 3 ms | 201 ms | 200 ms | 200 ms |
| D. rotating address **and** different secret | 3 ms | 2 ms | 3 ms | 2 ms |

A is the control: the throttle works when the caller cooperates. B and D are the defect. D is
what an attacker actually does, and it costs one extra header per request.

**One correction to the register's wording.** It says the penalty "never accumulates". Per key it
does not accumulate even in the control case — row A is flat at ~200 ms, not 200/400/600. The
code is a fixed-rate limiter, not exponential backoff: `addFailedRequest` resets the entry to
`now + DELAY_ON_FAIL` once the previous entry has elapsed. The defect is not that the penalty
fails to *grow*; it is that it never *engages*. For the default `AUTH_FAIL_DELAY` of 5000 ms the
intended control is "one guess per 5 seconds from this source", and rows B and D show that
control is absent.

### 1.3 The register's first-choice fix, evaluated and refuted

The register's preferred fix is to "key the delay list on something the caller does not choose.
The credential being attempted is the obvious candidate." I implemented exactly that — the only
change was to replace `data.ip` with `'cred:' + String(data.api_secret || data.token)` at the
three call sites in `lib/authorization/index.js` — and re-ran the same harness:

| scenario | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| A. fixed address, same wrong secret | 30 ms | 194 ms | 200 ms | 200 ms |
| B. rotating address, same wrong secret | 5 ms | **201 ms** | 200 ms | 200 ms |
| C. fixed address, different secret each time | 5 ms | **4 ms** | **3 ms** | **2 ms** |
| D. rotating address and different secret | 2 ms | **1 ms** | 2 ms | 1 ms |

It fixes B and **breaks C**. A brute force varies the credential by definition, so a counter
keyed only on the credential is fresh on every guess. Under this fix, the fixed-address attacker
that the shipping code *did* throttle is no longer throttled at all, and D — the realistic
attacker — is no better off than before. As the sole fix it is a net regression against the
threat the register names ("unlimited guesses at `API_SECRET` or a token").

The register's reasoning for the fix is sound about one thing and wrong about the other. It is
right that keying on the credential fixes the behind-a-proxy fairness problem. It is wrong that
"the point is to slow repeated guesses at *a secret*" — the point is to slow repeated guesses at
*the secret*, which means many different attempted values.

### 1.4 The fix

The throttle has to be carried by a value with two properties: the caller cannot choose it, and
it does not change from one guess to the next. On an HTTP request there is exactly one such
value, the socket's peer address. So:

1. **`lib/server/peer-address.js`** (new) reads `req.socket.remoteAddress`. This is separate from
   `getRemoteIP`, which is unchanged and still what the operator "failed authentication"
   notification reports — a forged address is a reasonable thing to show a human and not a thing
   to make a decision on.

2. **The delay list is keyed on both** the peer digest and a digest of the attempted credential,
   and `shouldDelayRequest` takes whichever wait is longer. The peer key carries the throttle;
   the credential key covers guessing at one secret from many addresses, and gives a client
   behind a shared proxy a bucket of its own rather than its neighbour's.

3. **The wait moved from the way in to the way out.** This is the load-bearing part, and it is
   what makes (1) safe.

   Behind a platform proxy — Heroku, Railway, Azure, which is most Nightscout deployments — the
   peer address is the proxy's for every client. The shipping code takes the delay *before*
   resolving, on every request carrying the key, so keying on a shared peer would have meant one
   failing uploader adding `AUTH_FAIL_DELAY` to everybody's requests. That is the self-inflicted
   denial of service the register correctly warns about, and it is a real one: `requestSucceeded`
   clears the key, but a request that is *about* to succeed still waits first.

   Taking the delay on the failure path instead means a request that authenticates, or that
   carries no credential at all, is never made to wait for somebody else's failures. Guessing is
   still rate-limited, because a guess is a failure by definition. This is the change that lets
   the throttle key on the only unforgeable value in the request without punishing everyone who
   shares it.

4. **The list is bounded**, and the two namespaces are bounded separately. An attacker can mint
   credential keys at will; if both namespaces shared one bound, flooding the list with made-up
   credentials would evict the peer entry that is throttling the flooder. `tests/authdelay.test.js`
   has that case.

5. **Keys are digests under a per-process salt.** The delay list is a long-lived in-memory map,
   and one whose keys are the secrets people just tried is not a thing this process should hold.

6. The sweep was a `setTimeout`, so it ran once 30 seconds after boot and never again. It is a
   `setInterval` now, `unref`'d so it cannot hold the process open.

Measured after the fix, same harness, same 200 ms: **all four scenarios throttled**, every
attempt after the first at 198-202 ms.

### 1.5 Non-vacuity

`tests/authdelay.test.js`, 11 checks. Against the unmodified `delaylist.js` and
`authorization/index.js` restored from `origin/dev`:

```
1) throttles a wrong secret presented from a rotating forwarded address
   AssertionError: expected 2 to be above or equal 120
2) throttles a guess even when both the secret and the forwarded address change
3) throttles one wrong secret arriving from many addresses
   ✔ does not delay a request that authenticates while the peer is throttled
   ✔ does not delay a request that presents no credential at all
4-9) the delay-list unit checks
2 passing, 9 failing
```

The three behavioural checks fail with the delay measured at 2 ms against a 120 ms floor —
i.e. they fail for the defect's own reason, not because a helper is missing.

The two that pass against the old code are deliberate controls, not filler: they pin the
anti-DoS property from §1.4(3), which the old code also had (by not keying on a shared value)
and which the fix must not lose. If either the peer keying or the move to the failure path were
wrong, one of them would fail. Verified by inspection of the run above: they pass before *and*
after.

---

## 2. BF-17 — a subject edit writes the access token to the database

### 2.1 Reproduction

Against a running instance, through the stock endpoints only. The register's chain holds link
for link on `dev`.

```
1. after create, the stored document is:
   {"_id":"…","name":"bf17-probe","roles":["readable"],
    "notes":"insulin pump in the kitchen","created_at":"…"}

2. GET /subjects hands the UI:
   {"_id":"…","name":"bf17-probe","accessToken":"bf17probe-6fb29884a9a6c6fb","roles":["readable"]}

3. after ONE edit, the stored document is:
   {"_id":"…","name":"bf17-probe","accessToken":"bf17probe-6fb29884a9a6c6fb",
    "roles":["readable"],"notes":"","created_at":"…"}

   accessToken now on disk in plaintext: true
   notes were "insulin pump in the kitchen", now: ""

4. using the token read straight from the database: 200 it authenticates
```

Step 4 is the consequence stated plainly: after one edit, a reader of the collection has a
working credential. `accessTokenDigest` and `digest` are confirmed *not* round-tripped, as the
register predicted — `GET /subjects` does not serve them. The exposure is `accessToken` alone,
and `accessToken` is what `authorize()` accepts.

The `notes` erasure reproduces too, in the same single edit.

**One thing the register does not mention**, visible in the transcript above: `created_at` is
also not served by `GET /subjects`, so an edit gives the document a brand-new `created_at`. Data
loss, not a security problem. Not fixed here; recorded in the register.

### 2.2 The fix

The register offers two shapes and prefers the durable one: have `save` write only the fields a
subject document owns. That is what is implemented, in `lib/authorization/storage.js`:

- `create` and `save` both take the list of owned fields (`name`, `roles`/`permissions`, `notes`,
  `created_at`) and build the document from those, rather than writing the request body. This
  covers the edit path, and also means a client cannot choose a subject's `accessToken` or
  `digest` by posting one, and cannot add fields of its own to an auth document. Applied to roles
  as well as subjects — `save` is shared and the same wholesale replacement applies to both.
- `reload()` deletes the three derived fields off a stored document before deriving them.

The register's claim that the durable fix "fixes the token and the notes together" does not hold:
the client sends `notes: ''` because `GET` never gave it one, and a field whitelist faithfully
writes that empty string. The notes fix has to be at the other end of the round-trip, so
`GET /subjects` now serves `notes`. The admin UI already has a column and an input for it; the
column has simply always rendered blank.

### 2.3 What this means for data already written

**A code fix alone leaves existing plaintext tokens on disk.** Any subject an operator has ever
edited through the admin UI has its bearer token stored in `auth_subjects`, and that token
remains valid: it is derived from `_id`, `name` and the enclave key, none of which the fix
changes.

The `reload()` change is the part of remediation that writes nothing. It matters in one specific
case: with no enclave key configured, `reload()` derives nothing, so before this change a stored
`accessTokenDigest` would have been left in place and `findSubject` would have matched against
it — a value chosen by whoever last wrote the collection. After the change those fields are
absent, `findSubject` cannot match, and nothing authenticates.

**No migration is included, and none should be run without being asked for.** Remediation of
operator data would require, in order:

1. Clearing the stored fields:
   `db.auth_subjects.updateMany({}, { $unset: { accessToken: "", accessTokenDigest: "", digest: "" } })`
   — safe in itself, since all three are recomputed on the next reload.
2. Recognising that step 1 is **not sufficient**. The token is deterministic in `_id`, `name` and
   the enclave key. Anyone who already read the collection, or a backup or snapshot taken while
   the token was in it, still holds a working credential after the field is cleared. Clearing the
   field closes future disclosure, not past.
3. Actual remediation is therefore **rotation**, and there are exactly **two** ways to do it:
   delete and recreate the subject (which mints a new `_id`), or rotate `API_SECRET` (which
   invalidates every subject's token at once, and requires reconfiguring every device). Which is
   appropriate depends on what the operator's exposure was, and it is their decision.

   > **CORRECTED 2026-09-16.** This list previously opened with a third option, "change the
   > subject's name (which changes the derived token)". **That is wrong, and it was wrong in the
   > direction that matters** — it tells an operator an exposed credential has been retired when
   > it has not. `storage.findSubject` → `checkToken` splits the presented token on `-`, takes
   > the **last** segment as `prefix`, and matches
   > `subject.accessTokenDigest.indexOf(accessToken) === 0 || subject.digest.indexOf(prefix) === 0`.
   > The second arm is the one that carries: `subject.digest` is
   > `enclave.getSubjectHash(subject._id)`, a function of `_id` and the enclave key **only**. The
   > name contributes nothing but the `abbrev` prefix at the front, which `checkToken` never
   > reads. So a rename changes what the token *looks like* and leaves the old token
   > **authenticating**. Measured on `bf/auth` `lib/authorization/storage.js:326` and identically
   > on `origin/dev` `:288` — this is not a branch artifact, it is how the shipping matcher works.
   > The error propagated from here into `releases/cgm-remote-monitor-15.0.9/release-notes.md`,
   > where it had become an operator instruction; both are corrected, and
   > `tools/queue/gates/bf17-remediation-note.js` now guards against it returning.
4. Backups, replicas and support exports taken since the first subject edit should be treated as
   containing live credentials.
5. **What the code fix does to rows already written, precisely.** `reload()` deletes the derived
   fields from the **in-memory** subject before re-deriving them, so a stored copy can never be
   served or matched against — but it does **not** write, and the row on disk is unchanged. The
   stored copy is removed only when that subject is next saved through the admin path, because
   `save` now writes `ownedFields(obj, SUBJECT_FIELDS)` through `replaceOne`. So there is a
   self-healing path and it is **operator-driven, not automatic on upgrade**: re-saving each
   previously-edited subject clears the copies. That closes future disclosure and retires nothing.

This belongs in a release note, not in a migration script. **Decision, 2026-09-16 (maintainer):**
no detector script and no migration will be written. The remediation ships as operator-facing text
in the release notes and the `bf/auth` PR body, plus the manual `auth_subjects` check already in
the PR body. Recorded on queue item `P0-C-REMEDIATE`.

### 2.4 Non-vacuity

`tests/authsubjects.test.js`, 8 checks. Against `lib/authorization/storage.js` and
`endpoints.js` restored from `origin/dev`: **7 failing, 1 passing.**

The one that passes is the positive control — "derives over a stored token when there is an
enclave key" — which pins behaviour that must not change and is expected to pass on both sides.

Two of the failures are worth naming because they are the defect itself rather than a
consequence of it:

- "does not write the access token to the database when a subject is edited" — the check reads
  the raw collection after one PUT built the way `lib/admin_plugins/subjects.js` builds it.
- "keeps the token derivable only with the enclave key, not readable from the collection" fails
  with the token quoted in the assertion message:
  `expected '{"_id":"…","name":"…","accessToken":"authsubjec-9fe8febf443ebcc6",…}' not to contain 'authsubjec-9fe8febf443ebcc6'`

The "drops a stored token when there is no enclave key" check is a unit test against a stubbed
collection rather than an integration test, specifically so it can exercise the unset-key branch
described in §2.3. An earlier integration version of that check passed against the unfixed code —
it was vacuous, because `reload()` recomputes over the stale value whenever a key *is* set — and
was replaced for that reason.

---

## 3. The enclave

Not touched. `lib/server/enclave.js` holds `API_SECRET` and its digests in a closure under
`Symbol` keys, `setAPISecret()` deletes `API_SECRET` from `process.env`, and the delay-list
change deliberately does not route credentials through the enclave: it uses an independent
per-process salt in `delaylist.js` so that throttling has no reason to ask the enclave for
anything. Nothing here widens what the enclave exposes.

---

## 4. BF-24 and the `TRUST_PROXY` default

BF-24 is on the multitenancy seam branch and was not chased. One implication of §1.1 for it:

BF-24 is about `TRUST_PROXY=false` defeating the guard that refuses a non-`host`
`TENANT_HOST_HEADER`. The work here did **not** change the `TRUST_PROXY` default, and could not
have — `dev` has no such default. But the shape of the finding transfers:

- On the seam branch the forwarded address is at least *gated* on `TRUST_PROXY`. On `dev` it is
  not gated on anything, in four separate copies of `getRemoteIP`. Whatever the seam branch
  decides about `TRUST_PROXY`, `dev` is the weaker baseline and the fix landing here does not
  depend on the seam's decision.
- The general rule this work supports: **`TRUST_PROXY` is the wrong axis for a security control.**
  Whichever way the default goes, it is a statement about whose network the server is on, and a
  control that must hold regardless of deployment should not be keyed on a value that statement
  governs. That argues for fixing BF-24 by having the tenant guard depend on something other than
  the trust marker, rather than by changing the marker's default — the same move made in §1.4.
- §1.4(3) is directly reusable: if the seam needs a control keyed on an unforgeable value that is
  shared behind a proxy, the way to make that safe is to apply its cost only on the failure path.

---

## 5. Honest limits

- **The delay is still per-request, not per-connection or global.** Neither the shipping code nor
  this fix serialises concurrent attempts. An attacker who opens many connections at once still
  gets many guesses in flight, each individually delayed. The throttle raises the cost of
  *sequential* guessing by roughly four orders of magnitude at the default `AUTH_FAIL_DELAY`; it
  is not a concurrency limit and this change does not make it one. Fixing that is a different
  control (a semaphore or a token bucket) and a different change.
- **The peer address is unforgeable, not scarce.** An attacker with a pool of source addresses —
  IPv6 in particular, where a /64 is routine — gets a fresh peer key per address. The credential
  key does not help, because a brute force varies the credential. This fix removes a bypass that
  costs one HTTP header; it does not remove one that costs a botnet. A control that survives that
  would have to be global or per-account, with its own denial-of-service trade-off.
- **`AUTH_FAIL_DELAY=0` disables the throttle entirely**, and `tests/fixtures/api3/instance.js`
  sets it to 0. That is correct for tests and is worth knowing about as an operator setting: the
  fix makes the throttle work, it does not make it mandatory.
- **The timing assertions in `tests/authdelay.test.js` are wall-clock**, with a 150 ms configured
  delay and a 120 ms threshold. The band is wide and the observed values sit at 2 ms and 200 ms,
  but this is a timing test and a sufficiently loaded machine could flake it. It is the honest
  way to assert "the request actually waited"; the alternative is reaching into the delay list,
  which would assert the implementation rather than the behaviour.
- **BF-17's `created_at` reset is unfixed** (§2.1). One more field would round-trip it; it is
  cosmetic data loss rather than a security issue and it was left out to keep the commit to the
  defect.
- **The four copies of `getRemoteIP` were not consolidated.** Each call site got the peer address
  added; the duplication is pre-existing and deduplicating it would have widened the diff across
  the websocket and API v3 paths for no behavioural gain.
- **`lib/admin_plugins/subjects.js` was not changed.** The register names it as one of the three
  links, and it is — `data: subject` sends the whole object back. It is fixed at the server, which
  is the right place: the server should not store what a client sends it regardless of which
  client is sending. A browser-side fix alone would leave the API open.
- **Neither defect's fix was exercised against PostgreSQL storage or the multitenancy seam.**
  Both are on `dev` only.
- **No third defect is claimed.** Nothing beyond the `created_at` observation surfaced that looks
  like a distinct security issue; the `forwarded-for` no-whitelist finding is BF-30's own root
  cause rather than a separate one, and it is recorded that way.

---

*Not a security advisory and not a disclosure. This is engineering notes on a branch, for review
by the project's maintainers before anything here is relied upon or published.*
