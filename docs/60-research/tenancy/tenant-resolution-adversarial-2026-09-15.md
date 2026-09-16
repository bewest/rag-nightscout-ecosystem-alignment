# Attacking tenant resolution — the half of isolation that runs before the database

**Commit under test:** `239f8c25` ("Close the seam between the tenant reader and its writer"),
branch `main` of `externals/work/crm-seam`. Re-checked at the end of the run: head had not moved,
and `git diff 239f8c25..HEAD` over every module measured here is empty.

**Worked in:** a detached worktree, `externals/work/crm-tenant`, created from that commit. Nothing
was written to, committed to, or executed inside `crm-seam`. No database was needed: every probe
below is about what happens *before* a query is issued, so mongo `27022` and postgres `15437` were
never started.

**Harness:** `tools/qc/tenant-resolution-arm.js`, six sections
(`host | path | credential | failclosed | mount | admin | all`).

---

## 0. The property under test, and what is deliberately not tested

Tenant isolation has two halves.

The **database half** is row-level security, and it is already covered by
`tests/postgres-entries-rls.test.js`: a `NOSUPERUSER NOBYPASSRLS` role, transaction-scoped binding,
no binding left behind on a pooled connection, cross-tenant read and write refusal, index bounds —
each with its own non-vacuity case. **Nothing here re-tests any of that.**

The **half before the database** is how an HTTP request becomes a tenant id. RLS then enforces
whatever id it is handed, faithfully and completely. So the failure this work exists to find is not
"RLS leaked"; it is "resolution handed RLS the wrong id, and RLS enforced the wrong tenant
perfectly." One person's CGM data, served to another, with every database-layer assertion green.

Six things were attacked: the Host header and its normalisation; the path-prefix fallback and the
`req.url` rewrite it performs; the configured forwarded-host header; the fail-closed behaviour of
unknown, deleted and disabled tenants; what mounts above and below the middleware; and the admin
plane's claim to be secured by unreachability.

Websockets (T3.5, tenant socket rooms) were skipped: that work is in flight in another session.

### Verdicts

| # | probe | verdict |
|---|---|---|
| H1 | Unicode case folding in `normalizeHost` cannot mint an ASCII slug over HTTP | CONFIRMED-SAFE |
| H2 | Duplicate / absent / empty / malformed Host headers fail closed | CONFIRMED-SAFE |
| H3 | The `TENANT_HOST_HEADER` guard against client-chosen tenants | **DEFECT — BF-24** |
| H4 | The host is read from `req.headers[hostHeader]`, not `req.hostname` | CONFIRMED-SAFE |
| P1 | The path rewrite never routes a request under a slug other than the first segment | CONFIRMED-SAFE |
| P2 | Absolute-form request lines desynchronise resolver and router — in the closed direction | CONFIRMED-SAFE |
| C1 | `TENANT_REQUIRE_TOKEN_CLAIM` vs a credential presented in the request body | **DEFECT — BF-25** |
| F1 | Unknown / deleted / inactive tenant, and an unreachable registry | CONFIRMED-SAFE |
| F2 | A storage call with no binding is refused, not defaulted | CONFIRMED-SAFE |
| M1 | What mounts above the middleware in `lib/server/app.js` | CONFIRMED-SAFE |
| M2 | The HTTP→HTTPS redirect rebuilds the URL from the rewritten `req.url` | **DEFECT — BF-26** |
| A1 | The admin plane is not reachable from the consumer app | CONFIRMED-SAFE |

Every CONFIRMED-SAFE above carries non-vacuity evidence in its own section: the same probe, run
against a deliberately weakened copy of the same module in the QC worktree, going RED. The weakened
copy is written beside the original so its relative requires still resolve, required once, and
deleted in a `finally`; a full run leaves the worktree clean (`git status --porcelain` empty).

**The code is careful, and most of these attacks failed.** Two of the three defects are in the
seams *around* resolution rather than in the resolver itself, and the third is a guard that is
correct for the configuration it was written against and silent for the one next to it.

---

## 1. H1 — CONFIRMED-SAFE. The Kelvin sign is real, and unreachable

`normalizeHost` lowercases with `String.prototype.toLowerCase`, which is Unicode case folding, not
ASCII case folding. A Host header is bytes and need not be ASCII. So: can two distinct Host headers
fold to the same slug?

Exhaustive enumeration of all 1,112,064 code points — the harness does this at run time, not from
memory — gives **exactly one** non-ASCII code point whose `toLowerCase()` lands inside
`^[a-z0-9-]+$`:

```
U+212A KELVIN SIGN  ->  "k"
```

and at the module boundary the collision is real:

```
resolve('kfoo.user-content.apex.org')   -> slug "kfoo"
resolve('Kfoo.user-content.apex.org') -> slug "kfoo"     collide: true
```

**But it cannot be reached over HTTP.** Node decodes header octets as latin1, so the three UTF-8
bytes of U+212A arrive as three separate latin1 characters, and no latin1 character folds into the
slug charset. Measured on a raw socket against a bare `http.createServer`:

```
wire: kelvin-utf8 | status 200 | host codes 66 6f 6f c3 a2 c2 84 c2 aa 2e 75 ... | resolver: NO MATCH
wire: latin1-high | status 200 | host codes 66 6f c3 96 2e 75 73 65 72 ...      | resolver: NO MATCH
```

Verdict: **CONFIRMED-SAFE over HTTP.** The residual is stated rather than hidden: `normalizeHost`
is exported, and a non-HTTP caller (a future socket path, an admin tool, a test) *can* hand it
U+212A and get `k` back. If resolution ever grows a second entry point that does its own decoding —
anything that does `Buffer.toString('utf8')` on a header — this becomes live. A one-line
`if (!/^[\x00-\x7f]*$/.test(host)) return null;` before the `toLowerCase()` would close it
permanently and is cheaper than the analysis above.

### Non-vacuity

`SLUG_CHARS_RE` loosened from `/^[a-z0-9-]+$/` to `/^[a-z0-9-ɏ-]+$/` — the shape an "add
IDN support" patch would take. The *same over-the-wire host* then resolves to slug `"foã"` where it
previously produced NO MATCH. The probe is reading the charset gate, not something upstream of it.

---

## 2. H2 — CONFIRMED-SAFE. Every malformed Host fails closed

Nine shapes, each written onto a raw socket so the bytes are the bytes asked for:

| case | Node's status | `req.headers.host` became | resolver |
|---|---|---|---|
| two `Host:` headers | 200 | `foo.user-content.apex.org` (the **first**) | slug `foo` |
| no Host at all (HTTP/1.0) | 200 | `undefined` | NO MATCH |
| `Host:` (empty) | 200 | `""` | NO MATCH |
| `Host:` (whitespace only) | 200 | `""` | NO MATCH |
| `Host: :8080` (port only) | 200 | `":8080"` | NO MATCH |
| Host containing NUL | **400** | — | never reached |
| 300-character label | 200 | the long host | NO MATCH |
| `Host: [foo.user-content.apex.org]` | 200 | bracketed | NO MATCH |
| `Host: foo.user-content.apex.org.:8443` | 200 | as sent | slug `foo` |

Two things worth stating plainly, because both were candidate attacks:

- **Node does not join duplicate `Host` headers.** `host` is in Node's discard-duplicate set, so
  the first wins and there is no `", "`-joined value for a pattern to mis-read. (A *configured*
  header such as `x-forwarded-host` **is** joined — see H3.)
- **`Host: :8080` normalises to null, not to `""` passed onward.** `normalizeHost` strips at
  `lastIndexOf(':')`, leaving an empty string, and the `return value || null` catches it.

End to end through the middleware, `Host: :8080` returns
`404 {"message":"No Nightscout tenant is served at this address."}` and **storage is never
reached** — the harness's terminal route calls `tenantScope.requireTenant()` and records every
successful binding; over the whole probe the record contains exactly one entry, the control.

The overlong host is rejected by two independent bounds (`MAX_HOST_LENGTH = 253` in
`normalizeHost`, and `MAX_SLUG_LENGTH = 63` in `isSlug`); the probe does not distinguish which
fired, and does not need to.

### Non-vacuity

The `if (!resolved) { refuse(res, 404, …); return; }` branch replaced by a fall-through to a default
tenant — the classic fail-open. The same `Host: :8080` request then returns **200**, bound to
`11111111-…`, and reaches storage. The probe measures the refusal, not an unreachable route.

---

## 3. H3 — **DEFECT. Proposed BF-24: the forwarded-host guard does not fire on `TRUST_PROXY=false`**

`fromEnv` refuses to accept a `TENANT_HOST_HEADER` other than `host` unless `TRUST_PROXY` has been
configured, and the reasoning in the module is exactly right:

> A forwarded host header is only meaningful if something trustworthy set it. Nightscout's default
> trust setting is a compatibility mode that trusts every peer, under which this header is client
> input and the tenant would be chosen by the caller.

The guard is written as `if (trust.legacyForwardedHeaders) throw`. `legacyForwardedHeaders` is a
marker on the *compatibility* trust function only — `compileTrust` returns it for `undefined` and
for `''`. For `'false'` it returns a bare `() => false`, which has no such marker. So:

```
TRUST_PROXY unset      (trusts everyone)   REFUSED — "…so that header is client input…"
TRUST_PROXY=""         (same)              REFUSED — same message
TRUST_PROXY=false      (trust NOBODY)      ACCEPTED        <-- the defect
TRUST_PROXY=10.0.0.0/8 (a real edge)       ACCEPTED        <-- correct
```

`TRUST_PROXY=false` is the setting that says *there is no proxy in front of this deployment*. It is
the case where a forwarded header is **most** obviously client input, and it is the one case the
guard lets through. With it accepted, a client picks its own tenant with a request header —
measured end to end:

```
Host: foo.user-content.apex.org
X-Forwarded-Host: bar.user-content.apex.org
  -> 200  bound 22222222-…  tenant {"slug":"bar"}
```

The request arrives on tenant `foo`'s own hostname and is served, and bound, as tenant `bar`. RLS
then enforces `bar` perfectly. This is the exact failure the resolution boundary exists to prevent.

**Severity: high. Reachability: gated on operator configuration.** It needs a deployment that sets
`TENANT_HOST_HEADER` to something other than `host` *and* sets `TRUST_PROXY=false`. That pairing is
internally contradictory, which is precisely why a guard was written for it — the guard simply
tests the wrong predicate. It is also the pairing an operator reaches by following the guard's own
error message half-way: the message says "Set `TRUST_PROXY` to the proxy addresses in front of this
deployment", and an operator who sets `TRUST_PROXY=false` instead gets silence rather than a second
refusal.

**Suggested fix** (not applied — this session does not own the code): make the guard test for a
*positive* list of trusted proxies rather than for the absence of the compatibility marker. Something
of the shape "refuse unless `compileTrust` produced a `proxy-addr` matcher", i.e. refuse `undefined`,
`''`, `false` and `'false'` alike. A second, independent belt: even with a trusted edge configured,
nothing verifies that the edge actually *overwrites* the header rather than appending to a
client-supplied one. Node joins duplicates of a non-`host` header with `", "`, which under the
README's anchored patterns produces NO MATCH and a 404 — fail-closed today, but only because the
recommended pattern happens to be anchored at both ends. A deployment writing an unanchored rule
would take the first of a joined pair. Worth a sentence in the README beside `TENANT_HOST_HEADER`.

### Non-vacuity

This is a DEFECT, so the evidence is a *differential* across the four settings above, run in one
process against one module: two are refused with the guard's own message, one is accepted for a
deployment that really does have an edge, and one — the dangerous one — is accepted silently. A
probe that always reported "accepted" would not produce two refusals; a probe that never reached
the guard would not produce the guard's message verbatim.

---

## 4. H4 — CONFIRMED-SAFE. `req.hostname` is avoided, and it matters

`Host: foo…` plus `X-Forwarded-Host: bar…`, under Nightscout's default `TRUST_PROXY` (the
compatibility mode that trusts every peer), binds **foo**.

### Non-vacuity

`resolver.resolve(req.headers[hostHeader], req.url)` swapped for `resolver.resolve(req.hostname, …)`
— the one-word change the module's comment warns about. The same request then binds **bar**. The
comment is not decoration; the probe shows the trap is live and the code steps around it.

---

## 5. P1 — CONFIRMED-SAFE. The path rewrite cannot reach another tenant's slug

Pattern `^/([a-z0-9-]+)(?=/|$)` (README's). Fourteen URLs, **written onto a raw socket**, with the
binding and the rewritten `req.url` read back from the terminal route:

| request line | slug | `req.url` after rewrite | status | bound |
|---|---|---|---|---|
| `/foo/api/v1/entries` | `foo` | `/api/v1/entries` | 200 | foo |
| `/foo/../bar/api/v1/entries` | `foo` | `/../bar/api/v1/entries` | 404 | — |
| `/foo/%2e%2e/bar/api/v1/entries` | `foo` | `/%2e%2e/bar/api/v1/entries` | 404 | — |
| `/foo/..%2fbar/api/v1/entries` | `foo` | `/..%2fbar/api/v1/entries` | 404 | — |
| `//foo//api/v1/entries` | — | (no match) | 404 | — |
| `/foo//api/v1/entries` | `foo` | `//api/v1/entries` | 404 | — |
| `/foo%2Fbar/api/v1/entries` | — | (no match) | 404 | — |
| `/foo/./api/v1/entries` | `foo` | `/./api/v1/entries` | 404 | — |
| `/api/v1/entries` | `api` | (no such tenant) | 404 | — |
| `/foo/api/v1/entries?count=10&find[sgv][$gte]=100` | `foo` | `/api/v1/entries?count=10&…` | 200 | foo |
| `/FOO/api/v1/entries` | — | (no match) | 404 | — |
| `/foo`, `/foo/` | `foo` | `/` | 200 | foo |

The property holds: **the slug is always the first path segment, the binding is always that slug's
tenant, and no request was served under any other one.** Dot segments survive the rewrite verbatim
and Express 5 collapses neither `.` nor `..`, so a `..` never walks into a second slug. `//foo//…`,
`/foo%2Fbar/…` and `/FOO/…` produce no match at all and 404.

**Three observations that are not defects but belong in the record:**

1. **In path mode there is no unprefixed API.** `/api/v1/entries` reads `api` *as the slug*.
   `lib/admin/slug.js` names reserved labels as a deliberate non-rule, with a good reason — which
   labels collide is a fact about a deployment's DNS, not about Nightscout. But that reasoning is
   written about the *subdomain* shape (a marketing site at `www`). In **path** mode the collision
   is not a fact about the hoster's DNS, it is a fact about Nightscout's own route table: a tenant
   legitimately named `api`, `admin`, `clock`, `bundle`, `translations` or `pebble` shadows, or is
   shadowed by, a core route for every tenant in the deployment. Worth one line in `slug.js`'s
   "deliberately not a rule" list, so the path-mode consequence is a decision too.
2. `/foo/api/v1/entries/../../../../etc/passwd` binds `foo` and reaches the router with the `..`
   segments intact. Whether anything downstream resolves them is `serve-static`'s question, not
   resolution's; the binding is correct either way.
3. A rule whose match is zero-width (a pure lookahead, `^(?=/([a-z0-9-]+))`) yields
   `consumed: ''`, so nothing is stripped and the prefixed URL reaches the router unchanged — a
   404, not a mis-binding. Fail-closed, but a configuration that silently does nothing.

### A finding about the instrument, which changed a verdict

The first version of this probe used `supertest` and reported `/foo/../bar/api/v1/entries` binding
tenant **bar** — a cross-tenant defect. It was not one. **superagent builds a WHATWG URL, which
collapses `.` and `..` and decodes `%2e` before the bytes leave the client:**

```
supertest sent "/foo/../bar/api/v1/entries"     -> server saw "/bar/api/v1/entries"
supertest sent "/foo/%2e%2e/bar/api/v1/entries" -> server saw "/bar/api/v1/entries"
raw socket  sent the same two                   -> server saw them unchanged
```

So the "defect" was the test client resolving the traversal and then the middleware correctly
resolving `/bar/…` to bar. The harness now sends every path case on a raw socket and prints the
supertest control beside it, so the discrepancy is visible rather than fatal. **This matters beyond
this report:** `tests/tenant-resolution.test.js` is a supertest suite. Its existing cases use plain
paths and are unaffected, but any dot-segment or percent-encoding case added there in future would
measure superagent and pass for the wrong reason.

### Non-vacuity

The `match.index === 0` requirement removed from the resolver. `/api/v1/entries` under pattern
`/v1/([a-z0-9-]+)` then resolves to slug `"entries"` with `consumed: "/v1/entries"` — a slug taken
from the *middle* of the path, whose length would then slice the wrong prefix off `req.url`.
Unweakened, the same call returns `null`. The index check is the thing holding this shut.

---

## 6. P2 — CONFIRMED-SAFE, with a divergence worth writing down

The resolver matches against `req.url` **raw**. Express routes against `parseurl(req).pathname`.
For an absolute-form request line these disagree:

```
GET http://apex.org/foo/api/v1/entries HTTP/1.1
  resolver sees req.url = "http://apex.org/foo/api/v1/entries"  -> null
  Express would route parseurl().pathname = "/foo/api/v1/entries"
```

Over a real socket the request returns **404** and storage is reached **0** times. The `^/` anchor
in the documented path rule is what makes the divergence fail closed rather than open.

It is still a divergence between two views of the same path, in the module whose whole job is to
agree with the router about what the path is. It is safe today because of a property of the
*configured pattern*, not of the code.

### Non-vacuity

The resolver taught to extract a pathname before matching — the "obvious improvement" someone will
propose. The same request line is then *resolved* (it was refused before), and because `consumed`
is sliced off a URL whose prefix is the scheme, the rewritten `req.url` becomes
`"/://apex.org/foo/api/v1/entries"`. The probe is reading the anchor, not an unreachable route.

---

## 7. C1 — **DEFECT. Proposed BF-25: a credential in the request body is invisible to the claim check**

This is the most serious finding in the report.

`lib/server/tenant-middleware.js` documents `TENANT_REQUIRE_TOKEN_CLAIM` as the only thing standing
between two tenants until T3.3 scopes subject resolution:

> `lib/authorization/storage.js` keeps `storage.subjects` as one process-wide array loaded at boot,
> so an access token resolves to its subject no matter which tenant's host it arrived on. Until
> subject resolution is itself tenant-scoped (T3.3), **this check is the only thing standing between
> the two.**

`presentedCredential` reads the `Authorization` header, `?token=`, `?secret=` and the `api-secret`
header. It deliberately does not read `req.body`, because the middleware mounts above the body
parsers — and the module reasons that this is fine:

> That is a gap in coverage, not a gap in the check: an opaque credential is exactly the case the
> `requireTokenClaim` default refuses.

**That reasoning does not hold.** The refusal is gated on `credential.present`, and `present` is
only ever set from places the middleware can see. A credential that exists *only* in the body sets
`present = false`, so the request is classified as **anonymous** and passed straight through.

Measured, one process, one middleware instance, default `requireTokenClaim`, victim host
`bar.user-content.apex.org`:

| what is presented, and where | status |
|---|---|
| tenant foo's JWT as `?token=` | **403** "This credential is for a different Nightscout site." |
| tenant foo's JWT as `Authorization: Bearer` | **403** same |
| an opaque access token as `?token=` | **403** "This credential does not name a Nightscout site." |
| an API secret in the `api-secret` header | **403** same |
| **tenant foo's JWT in the JSON body** | **200**, bound to tenant **bar**, token intact |
| **an opaque access token in the JSON body** | **200**, bound to tenant **bar**, token intact |
| **an API secret in the JSON body** | **200**, bound to tenant **bar**, secret intact |
| **an API secret in a JSON body array** (`[{secret:…}]`) | **200**, bound to tenant **bar**, intact |

The same credential, refused in the query string and accepted in the body, on the same host. An
attacker does not need a new credential — they move the one they have.

The second half of the defect is that the body is not a dead end. `lib/authorization/index.js`
reads exactly those fields:

```js
} else if (req.body.token) {          // extractJWTfromRequest, line 45
  accessToken = req.body.token;
  delete req.body.token;
```

and the array form, and `req.body.secret` / `req.body[0].secret` in `apiSecretFromRequest`. The
extracted token goes to `authorization.authorize()` → `storage.findSubject()` → the **process-wide**
subject array. So tenant A's access token, moved into the body of a `POST /api/v1/entries` on tenant
B's host, resolves to A's subject and grants A's roles — against the tenant the *host* bound, which
is B. Read and write. `lib/api/entries/index.js:43` mounts the body parser for exactly that route.

**Severity: high within `TENANCY_MODE=multi`.** **Reachability: any client, no configuration
needed** — it is the default value of `TENANT_REQUIRE_TOKEN_CLAIM` that is being stepped around.
Tempering it: `fromEnv` prints, at boot, "Do not serve two people's data from this deployment until
T3.3–T3.5 land", so multi mode is not yet declared safe. That makes this a pre-release defect rather
than a live exposure — but it is a hole in the specific control that was shipped to hold the line
*until* T3.3, which is the one thing that control had to do.

**Suggested fixes** (not applied):

- The narrow one: the middleware cannot see the body without consuming it, so it cannot close this
  where it stands. It can be closed *below* — `extractJWTfromRequest` and `apiSecretFromRequest`
  are the two functions that read a body credential, and both could refuse (or re-run the claim
  check) when `req.tenant` is set and the credential carries no matching claim.
- The honest one: this is the same argument the module already makes for the `?token=` case, one
  layer down. Whatever T3.3 does to scope `storage.subjects` per tenant removes the whole class. If
  T3.3 is close, the right record may be "BF-25 is subsumed by T3.3" plus a test that fails until
  it is — but the module comment claiming the body case is already covered should be corrected
  either way, because it is the sentence that would stop someone from looking.

### Non-vacuity

A DEFECT, so the evidence is a **differential**, which is stronger than a weakening: the identical
credential returns 403 as `?token=` and 200 in the body, against the same middleware instance, in
the same process, in the same run. One arm red and one arm green means the probe cannot be passing
because the route is unreachable or because the middleware never ran — both arms would have moved
together.

### Also measured, not a defect

`Authorization: Basic …` on a tenant's **own** host returns **403 "This credential does not name a
Nightscout site."** Any `Authorization` header that is not a verifiable Bearer claim counts as a
presented credential with no claim. That is the rule working as written, but it means a deployment
that puts HTTP basic auth on a reverse proxy — a common self-hoster pattern — will 403 every
request the moment `TENANCY_MODE=multi` is switched on, with a message about Nightscout sites. An
operator will read that as a tenancy bug. Worth a sentence in the README beside
`TENANT_REQUIRE_TOKEN_CLAIM`.

---

## 8. F1, F2 — CONFIRMED-SAFE. Resolution fails closed in every direction tested

Fail-open under an unrecognised host is the highest-severity outcome available at this boundary. It
does not happen.

| host | status | body |
|---|---|---|
| known + active | 200 | bound `1111…` |
| never existed | 404 | "No Nightscout tenant is served at this address." |
| deleted (row gone) | 404 | identical body, identical code |
| registered but **inactive** | 403 | "This Nightscout site is not active." (§2.4, deliberate) |
| matches no rule | 404 | identical to "never existed" |
| apex with a port | 404 | identical |
| registry throws (`42501`) | **503** | "Tenant resolution is unavailable." |

Storage was reached **once** across all seven — the control. In particular the registry failure
does *not* fall through to an unbound request: it refuses where the failure can be named.

F2: with mode `multi` and no scope open, `tenantScope.requireTenant()` **throws**
(`…ran with no tenant bound`). There is no default and no fallback to single-tenant.

### Non-vacuity

- **F1**: the registry stubbed to answer with a default tenant for any unknown slug — the textbook
  fail-open. The same unknown host then returns **200**, bound to `1111…`, and reaches storage.
- **F2**: the identical call under mode `single` returns `Symbol(single-tenant)` instead of
  throwing. So the throw is the multi-mode assertion firing, not the call being impossible to make.

---

## 9. M1 — CONFIRMED-SAFE. Exactly one layer sits above the middleware

Read out of `lib/server/app.js` at run time. `app.use(resolveTenant)` is at line 58; the only thing
registered before it is line 49:

```
app.js:49   require('../middleware/configure-request')(app);
```

which sets the query parser and defaults `req.body` to `{}`. It touches no storage. Everything
else — static files, `/translations`, `/api`, `/api/v1`–`/api/v3`, `/clock`, `/pebble`, swagger,
`/bundle`, the error handler — is registered after. There is no request that can reach a storage
call without having passed the middleware, and F2 shows what happens to one that somehow did.

### Non-vacuity

This assertion is over source order in a file the harness reads at run time, so it moves when the
file moves: if the mount were pushed below a storage-touching layer, the list would grow and the
verdict would flip. The behavioural half is F1/F2 — a request that *does* reach storage without a
binding throws rather than being served. Labelled honestly: this probe's non-vacuity is weaker than
the others', because "nothing is mounted above it" has no natural negative case beyond re-reading
the file.

---

## 10. M2 — **DEFECT. Proposed BF-26: the HTTPS redirect drops the tenant path prefix**

`lib/server/app.js:132`:

```js
res.redirect(307, `https://${req.header('host')}${req.url}`);
```

This layer is mounted **below** the tenant middleware, and `req.url` has by then been rewritten to
remove the tenant prefix. So the redirect target has no tenant in it:

```
path mode : GET /foo/api/v1/entries?count=10  ->  307  Location: https://apex.org/api/v1/entries?count=10
host mode : GET /api/v1/entries?count=10      ->  307  Location: https://foo.user-content.apex.org/api/v1/entries?count=10
```

On the follow-up request the path rule reads `api` as the slug, which is not a tenant, and the
client gets a 404 for the URL it was just told to use. `INSECURE_USE_HTTP` defaults to `false`, so
this layer is **on by default**.

**Severity: low-to-medium — availability, not isolation.** It is not a cross-tenant read: the wrong
slug is refused, not served. It makes path-prefix tenancy unusable over plain HTTP, and it is
purely a consequence of mount order — the middleware is mounted first *because* every later layer
has to see the rewritten URL, and this is the one later layer that needed the original.

**Suggested fix:** the middleware already records what it consumed on `req.tenantPathPrefix`.
Rebuilding the redirect as `` `https://${host}${req.tenantPathPrefix || ''}${req.url}` `` restores
it; so would using `req.originalUrl`, which Express leaves untouched.

### Non-vacuity

The identical layer in **host** mode preserves the URL exactly, because nothing rewrote `req.url`.
One arm red, one green, same code, same process, same run — so the probe is measuring the rewrite
and not the redirect.

---

## 11. A1 — CONFIRMED-SAFE. The admin plane really is unreachable, and that is all that protects it

Verified empirically rather than from the comment, in three parts.

**1. It is not mounted on the consumer app.** No file under `lib/server/` or `lib/api*/` requires
`lib/admin`; the only requirer is `bin/admin.js`, a separate process with a separate listener.
`GET /api/admin/tenants` against the consumer app returns 404.

**2. The bind guard refuses a real non-loopback bind**, by code and not by message:

```
resolveBind(ADMIN_BIND=0.0.0.0)     -> ERR_ADMIN_INSECURE_BIND
resolveBind(ADMIN_BIND=169.254.1.1) -> ERR_ADMIN_INSECURE_BIND     (a routable address on this host)
```

**3. What the refusal is worth.** With `ADMIN_INSECURE_BIND_ACKNOWLEDGED=true`, the same address
binds, and an **unauthenticated** request from that non-loopback address returns the full tenant
list:

```
GET http://169.254.1.1:18337/api/admin/tenants
  -> 200 {"tenants":[{"id":"1111…","slug":"foo","is_active":true}]}
```

No credential of any kind. D7's design is exactly as documented — the port is the whole
authorization story — and the guard is the only thing enforcing it. (The listener was opened with a
stub store, held for one request, and closed.)

The existing `tests/admin-bind-guard.test.js` already covers the classifier and the
refuse-then-bind non-vacuity thoroughly; this probe adds the two things it does not assert — that
no route into the plane exists from the consumer app, and that an unauthenticated caller really is
served everything once it can connect.

### Non-vacuity

The admin router mounted onto the consumer app, below the tenant middleware. The same
unauthenticated `GET /api/admin/tenants` then returns **200** with every tenant on the deployment,
from the consumer port. So the 404 above is the *absence of a mount*, not the absence of a route
that would answer if one existed.

---

## 12. Honest limits

**Not tested, and why.**

- **Websockets.** T3.5 (tenant socket rooms) is in flight in the other session; probing it would
  have collided. Socket.IO attaches to the same HTTP server and does **not** pass through the
  Express middleware stack, so "does a socket connection resolve a tenant at all" is an open
  question this report does not answer.
- **No database was started.** Every probe here concerns what happens before a query. The registry's
  PostgreSQL path (`fromPostgres`) was exercised only through `fromList` and a throwing stub; the
  real `SELECT … WHERE slug = $1` was not run, so nothing here says anything about the registry's
  behaviour against a live table. `tests/tenant-registry-failures.test.js` covers that.
- **The full `lib/server/app.js` was never booted.** It needs `env`, `ctx`, plugins, a store and a
  boot sequence. M1 is therefore a *source-order* assertion plus a faithful reconstruction of the
  top four layers, not a measurement of the assembled app. A layer inserted above the mount by some
  other code path — a plugin, `lib/server/server.js`, a hosting wrapper — would not be visible to
  this probe.
- **The end-to-end consequence of BF-25 was established in two halves**, not one: the middleware
  lets the body credential through (measured, end to end), and `lib/authorization` reads that exact
  field and resolves it against a process-wide subject list (read from source, plus the module's own
  documentation of the gap). A single test that starts the real authorization stack with two tenants'
  subjects loaded and shows A's token reading B's entries was not built — it needs `env.enclave`, a
  subjects collection and a store. That test is the one to write when fixing it.
- **`TENANT_REQUIRE_TOKEN_CLAIM=false`** was not explored as an attack surface; it is a documented
  knob whose whole purpose is to disable the check.
- **Slug-shaped route collisions were enumerated, not swept.** Observation 1 in §5 lists the
  shadowing routes I found by reading `app.js`; I did not machine-generate the full set of
  first-path-segments the app serves.

**Things the instrument could have got wrong, and what was done about them.**

- `supertest` normalises URLs before sending. This produced a false cross-tenant defect on the first
  run; §5 documents it, and every path probe now writes raw bytes onto a socket. If a future reader
  finds a path finding here that they cannot reproduce, check whether their client normalised.
- Node decodes header octets as latin1. H1's whole verdict rests on this; it was measured on a live
  socket rather than assumed, and the byte codes are printed in the harness output.
- The weakened copies are produced by exact string replacement with an anchor check that **throws**
  if the anchor is missing. If one of these modules changes, the harness stops rather than silently
  weakening nothing and reporting a green non-vacuity.
- The QC worktree symlinks `crm-seam/node_modules` rather than installing its own. That is a read of
  the other session's tree, which is permitted, but it means a concurrent `npm install` there could
  perturb a run. Nothing observed.

---

## 13. Reproduction

```bash
git -C externals/work/crm-seam worktree add --detach externals/work/crm-tenant 239f8c25
ln -s ../crm-seam/node_modules externals/work/crm-tenant/node_modules

node tools/qc/tenant-resolution-arm.js all
# or one section:  host | path | credential | failclosed | mount | admin
```

Exit status is 0 in all cases; the verdict block at the end names the DEFECT count (3 at
`239f8c25`). The harness needs no database and no credentials, and writes nothing outside the
worktree except its own temporary weakened copies, which it deletes.

---

## 14. Proposed backfix register entries

| id | what | severity | reachability |
|---|---|---|---|
| **BF-24** | `fromEnv`'s `TENANT_HOST_HEADER` guard tests `trust.legacyForwardedHeaders`, so `TRUST_PROXY=false` — the setting that means *no proxy* — accepts a forwarded host header and lets any client choose its tenant with a request header. | high | operator misconfiguration; no client prerequisite once set |
| **BF-25** | `presentedCredential` cannot see a credential in the request body, so `TENANT_REQUIRE_TOKEN_CLAIM` does not refuse it; `lib/authorization` then reads `req.body.token` / `req.body[0].token` / `req.body.secret` and resolves it against a process-wide subject list. The same credential is refused in the query string and accepted in the body. | high (within `TENANCY_MODE=multi`, which is not yet declared safe) | any client, default configuration |
| **BF-26** | `lib/server/app.js:132` builds the HTTP→HTTPS redirect from the rewritten `req.url`, dropping the tenant path prefix; the client is redirected to a URL that resolves to no tenant. | low–medium (availability) | path-prefix tenancy over plain HTTP, on by default |

Non-defect items recommended for the record rather than the register: the path-mode consequence of
having no reserved-slug list (§5, observation 1); the `Authorization: Basic` 403 (§7); the
resolver/router disagreement about what the path is under absolute-form (§6); the residual
`normalizeHost` folding collision at the module boundary (§1); and the note that supertest
normalises URLs, which belongs beside `tests/tenant-resolution.test.js` (§5).

---

*Draft for review. Findings were produced by adversarial probing of a local checkout the
Foundation owns; no code was modified in `crm-seam` and nothing was committed.*
