# Kratos session cookie scope: two more designs measured (E and H2)

> **Snapshot — measured 2026-10-12 against Ory Kratos v26.2.0 / Hydra v26.2.0 in Chrome 154.0.8037.57 over http. Status: current — tenancy research, not on a shipping path; input to D17 row 2 (cookie scope), which stays open. Nothing here decides it. Extends [the Ory proof](ory-proof-2026-10-07.md) §4.1.**

**Audience: contributors.** Technical throughout.

| | |
|---|---|
| Lab | [`tools/lab/ory-proof/`](../../../tools/lab/ory-proof/): adds `lib/edge.js` (E), `lib/handoff.js` (H2), `lib/browser.js`, `probes/cookie-edge.js`, `probes/cookie-handoff.js`, `run-variants.sh`; `LAB_MODE=edge\|handoff` in `lab-server.js` |
| Results | [`results/2026-10-12-v26.2.0-cookie-variants/`](../../../tools/lab/ory-proof/results/2026-10-12-v26.2.0-cookie-variants/): one JSON per probe, `summary.txt`, `console.txt` |
| Question | between the three cookie scopes already measured and two hardened designs, what does each one let a tenant host, a script on a tenant origin, or a log reader do at another tenant? |
| Read first | [Ory proof](ory-proof-2026-10-07.md) §1 (the lab), §2 (the `nsjwt` exchange), §4.1 (cookie scope) |

Every claim is marked **[M]** (measured: the check id is given and the result file holds it) or
**[R]** (read or reasoned, not executed). All identities are synthetic (`<label>-<random>@example.test`,
random passwords, created per run). Check ids refer to `cookie-edge.json` (E), `cookie-handoff.json`
(H2), and `cookies-*.json` / `proof.json` (the three earlier shapes and the gate, re-run in the same run).

**Re-run** (from `tools/lab/ory-proof/`, after `npm ci` and `./lab.sh secrets`):

```bash
KRATOS_IMAGE=oryd/kratos:v26.2.0@sha256:2a13bb8d362c7a7ae33bd7c0f5168aee46921f15c916a06346db91c06dc76643 \
HYDRA_IMAGE=oryd/hydra:v26.2.0@sha256:ff67c7fb5f95074fa53374d41151713554960504b340cd3f95b09e65deaea2a9 \
RUN=2026-10-12-v26.2.0-cookie-variants ./run-variants.sh   # exit 1 while H2's two mismatches stand
./lab.sh down
```

---

## 0. Results

1. **Run totals** [M] (`summary.txt`): E 21/21 as predicted. H2 24/26, and the two that differ
   are the brief's own cross-origin prediction (item 4). The earlier shapes were re-measured in
   the same run with the same results as on 2026-10-07: host-only 5/5, apex 8/8,
   content-domain 3/3, gate `proof.js` 23/23. That last figure is also the regression check
   on the `nsjwt` hooks added for E and H2. A run that slipped onto the compose defaults
   (Kratos v1.3.1, Hydra v2.3.0) gave the same figures. It is kept as
   [`results/2026-10-12-v1.3.1-v2.3.0-cookie-variants/`](../../../tools/lab/ory-proof/results/2026-10-12-v1.3.1-v2.3.0-cookie-variants/).
2. **E (apex cookie behind a hardened edge).** Tenant backends never receive the session.
   Both cross-origin probes are refused at the edge. Taking out either defence brings back the
   red result it guards against [M]. The session still reaches the edge on every tenant host,
   so the edge holds every user's cross-tenant credential: a cookie captured there, replayed to
   A by a non-browser client, mints an A token [M, `intact.replay.edge-cookie`].
3. **H2 (host-only cookie plus our own hand-off).** No tenant host ever receives the Kratos
   session. Every code check held, and each break produced the predicted red result [M]. SSO
   across tenants works with no password, at the cost of 3 redirects per tenant [M]. A Kratos
   logout does **not** reach the tenant sessions [M, `intact.logout`].
4. **Mismatch, H2 cross-origin.** The brief predicted that a script on B's origin would have
   "nothing to send, no cookie". That holds only while the browser has no tenant session on A
   [M, `intact.cross-origin.kratos-only`]. Once U has signed in to A, A's own host-only
   tenant-session cookie is sent on B's cross-origin `fetch` and on B's cross-origin form POST,
   and A mints (`via: tenant-session`, Origin = B's origin) [M,
   `intact.cross-origin.with-a-session`, `intact.cross-origin.form-with-a-session`]. The cause
   is that the tenants are same-site: setting the tenant cookie to `SameSite=Strict` changes
   nothing [M, `diag.strict.cross-origin`]. H2 was left as specified. No origin check was added
   to make the probe pass, so H2 as specified does not close cross-origin writes (§3).

---

## 1. The two designs as built

### 1.1 E: apex cookie, edge-hardened ([`lib/edge.js`](../../../tools/lab/ory-proof/lib/edge.js))

Kratos runs with `variants/cookie-apex.yaml`, so the session and CSRF cookies are on
`.apex.test`, `HttpOnly`, `SameSite=Lax` [M, `cookieJar`]. In the lab, the edge is a Node
proxy on :44480 in front of every tenant host, not nginx. The tenant backend (the `nsjwt`
stand-in) listens on its own port, 44481, on 127.0.0.1. For each tenant request the edge does
the following, in order:

1. It resolves the tenant from `Host` with the D10 rule and the `tenants` row. An unknown host
   gets a 404 and nothing is forwarded.
2. Origin check: it refuses any method other than GET, HEAD or OPTIONS unless `Origin` equals
   the tenant's own origin. When `Origin` is absent, `Sec-Fetch-Site` must be `same-origin`.
   When both are absent (a non-browser client), the request is allowed.
3. It validates the Kratos session with `whoami` and attaches **`X-Edge-Identity`**: base64url
   `{sub, sid, tenant, iat, exp = iat+30 s}` plus an HMAC-SHA256 made with a per-process edge
   key that the backend shares in memory. Any `X-Edge-Identity` the client sent is always
   removed first. The backend accepts only an assertion whose HMAC verifies, which has not
   expired, and whose `tenant` is the tenant it resolved. In E mode the backend does not read
   the Kratos cookie at all.
4. It removes `ory_kratos_session` and every `csrf_token_*` from `Cookie` before proxying.

A `GET /` with no valid session is redirected to the Kratos login with `return_to` set to that
URL. `EDGE_BREAK=no-strip|no-origin-check` removes one defence at a time.

### 1.2 H2: host-only cookie plus our own hand-off ([`lib/handoff.js`](../../../tools/lab/ory-proof/lib/handoff.js))

Kratos runs with its default cookie configuration: host-only on `auth.apex.test` [M, `cookieJarW`].

| step | where | what |
|---|---|---|
| 1 | tenant `GET /`, no tenant session | sets a host-only state cookie `ns_handoff_state` and returns a 302 to `auth/exchange?tenant=<slug>&return_to=<tenant>/handoff/callback&state=<nonce>` |
| 2 | auth host `GET /exchange` | checks, in order: tenant resolves (404); state well-formed (400); `return_to`'s origin is **exactly** the tenant's registered origin (400; computed from the slug in the lab); Kratos session from the host-only cookie (if none, a 303 to the Kratos login and back here); `tenant_members` row (403, shown at the auth host with no redirect back). It then issues a code and returns a 302 to `return_to?code=&state=` |
| 3 | code | 32 random bytes, held in memory, bound to {tenant, subject, Kratos session id, state}, 60 s TTL, single use |
| 4 | tenant `GET /handoff/callback` | checks that `state` equals the state cookie (400 `tenant-state-mismatch`), then redeems the code server to server |
| 5 | auth host `POST /exchange/redeem` | authenticated with the tenant's own redeem secret. Checks, in order: code known; unused; unexpired; the code is then **burned**; the code's tenant is the redeemer (`wrong-tenant`); state matches (`state-mismatch`). It then mints the `nsjwt` token with the redeemer's tenant key |
| 6 | tenant | creates its own host-only session cookie `ns_session` (`HttpOnly`, `SameSite=Lax`) and returns a 302 to `/`; `POST /api/nsjwt/exchange` authenticates with that session and then applies `nsjwt`'s membership check |

`HANDOFF_BREAK=no-tenant-binding|no-single-use|no-return-to-check` removes one defence at a time.
`HANDOFF_SESSION_SAMESITE=Strict` exists only for the diagnostic in §0 item 4. The refusal
matrix was sent by a non-browser client, either carrying U's real Kratos cookie taken from the
Chrome context or acting as a tenant backend with that tenant's redeem secret. The secret is
exposed on the lab control host for this purpose only. The flows ran in Chrome.

---

## 2. Comparison across the five shapes

host-only, apex and content-domain are the [proof](ory-proof-2026-10-07.md) §4.1 shapes. All
three were re-measured in this run with unchanged results [M, `cookies-*.json`]. "Credential"
means anything that would get an A Nightscout token minted. U is a member of A only unless a
row says otherwise.

| | host-only | apex | content-domain | **E** apex + edge | **H2** host-only + hand-off |
|---|---|---|---|---|---|
| **Hosts or processes that receive a credential usable at another tenant** | the auth host only; neither tenant host [M, `scope.neither`] | every tenant host's process, and anything in front of it or logging its headers [M, `scope.reaches-both`] | none: no session can be created [M, `login.fails`] | the browser sends it to every tenant host, but only **the edge** (and the auth host) receives it [M, `intact.edge-holds-session`]. Tenant backends get a 30 s assertion bound to their own tenant and no Cookie header at all [M, `intact.backend-receives`] | the auth host only [M, `intact.happy-a` cookie domain]. Tenant backends get a single-use code bound to them, then their own host-only session [M, `intact.backend-receives`: A sees `ns_session`, B sees no cookie] |
| **Replay** | nothing on a tenant host to replay [M, `exchange.a.no-cookie`] | the cookie as received by B, replayed to A, mints an A token [M, `replay.b-cookie-at-a`] | n/a | B's backend received no cookie, so nothing to replay [M, `intact.replay.b-backend-cookie`]. B's assertion replayed to A is removed by the edge (401) or, sent straight to A's backend, fails the tenant binding [M, `intact.replay.b-assertion`]. **A cookie captured at the edge** replayed to A **mints** [M, `intact.replay.edge-cookie`] | A's code redeemed by B: `wrong-tenant` [M, `intact.code-for-a-at-b`]; reused: `code-used` [M, `intact.twice`]; expired: `code-expired` [M, `expiry.expired`]; wrong state: `state-mismatch` [M, `intact.state-mismatch`]; A's `ns_session` at B: no credential [M, `intact.replay.a-session-at-b`] |
| **Cross-origin write** (script or form on B's origin, POST to A with credentials) | nothing to send: the session reaches no tenant host [M, `scope.neither`]; the cross-origin request itself was not sent in this shape [R] | A mints; response withheld from B's script [M, `cross-origin.b-to-a`] | n/a | refused at the edge for both `fetch` and form; A's backend never sees the request [M, `intact.cross-origin.fetch`, `intact.cross-origin.form`] | **A mints** once U has an A tenant session: A's host-only cookie is same-site to B [M, `intact.cross-origin.with-a-session`, `…form-with-a-session`, `diag.strict.cross-origin`]. Before any A session: A answers `no-credential` [M, `intact.cross-origin.kratos-only`] |
| **Redirects the user sees** (cold start on A, then B) | no browser path to a tenant: A has no credential [M, `exchange.a.no-cookie`] | not measured as a flow; the cookie behaves as in E, without the edge's login redirect [R] | login fails [M] | A: 3 redirects in 5 navigations, 1 password entry; B: 0 redirects, no password [M, `intact.flow.cold-a`, `intact.flow.then-b`] | A: 6 redirects in 8 navigations, 1 password entry; B: 3 redirects in 4 navigations, no password [M, same ids] |
| **SSO across tenants** | n/a | yes: U added to B, the same browser mints at B [M, `exchange.b.control`] | n/a | yes [M, `intact.flow.then-b`, `intact.control.b-member`] | yes, through the auth host's session [M, `intact.flow.then-b`, `intact.control.b-member`] |
| **Logout and revocation** | Kratos revocation stops new exchanges; a minted token lives to its `exp` [M, `proof.json` `revoke.*`, with a native session token] | the same mechanism; not measured with the apex cookie [R] | n/a | logout takes effect on the next request everywhere (the edge calls `whoami` on every request): new exchanges 401, A redirects to the login, the old cookie value is dead. A token minted before logout still verifies on A (`exp` 3600 s) [M, `intact.logout`] | logout ends **only** the auth-host session. A's and B's tenant sessions survive, A still mints **new** tokens, and the pre-logout token verifies. Only a tenant with no session yet (C) asks for the password again [M, `intact.logout`] |
| **Components we own** | the `nsjwt` exchange; the browser path needs something more (Hydra, or H2) | the `nsjwt` exchange | — | the edge (tenant resolution, `whoami` per request, cookie strip, origin check, assertion signing), the backend's assertion check, the `nsjwt` exchange | `/exchange` (return_to, membership, code issue), `/exchange/redeem` (redeemer auth, single use, TTL, tenant and state binding), the tenant callback, the state cookie, the tenant session store, the `nsjwt` exchange; not built: a per-tenant origin check and logout propagation (§3) |
| **What must stay correct for isolation to hold** | membership row and per-tenant key (the proof's gate) | the gate, plus nothing that sees B's request headers being hostile, which configuration cannot guarantee | — | the gate, **plus**: every path to a tenant backend goes through the edge; the strip list covers every Kratos cookie name; the origin check covers every state-changing request; the backend is reachable only from the edge and trusts only the edge's key; the edge does not leak cookies (it holds them all) | the gate, **plus**: exact-origin `return_to`, tenant binding, single use, TTL and state binding on every code; per-tenant redeemer credentials; **plus** a tenant-side origin/CSRF check that H2 as specified lacks |

---

## 3. Break-it results

Each break restarts the lab server with one defence removed. Each break phase starts with a
positive request (`*.live`) in the same server run. All of these are [M].

| design | defence removed | predicted red symptom | measured |
|---|---|---|---|
| E | cookie strip (`no-strip`) | B's backend holds U's session and the replay works | B's backend received the session with the same digest as the browser's; replayed to A it minted a `tenant-a` token (`break.no-strip.red`). The origin check still refused cross-origin (`break.no-strip.origin-still-holds`) |
| E | origin check (`no-origin-check`) | the cross-origin request mints | the script on B's origin made A's backend mint from the edge assertion, with Origin = B's origin; the browser withheld the response (`break.no-origin-check.red`). B's backend still received no session (`…strip-still-holds`) |
| H2 | tenant binding (`no-tenant-binding`) | B redeems A's code | B's backend redeemed A's code and got a `tenant-b` token for U, who is not a member of B; B accepted it (`break.no-tenant-binding.red`) |
| H2 | single use (`no-single-use`) | replay works | the same code redeemed three times, each 200 (`break.no-single-use.red`). The tokens were identical because they were minted in the same second with the same claims and HS256 is deterministic |
| H2 | `return_to` check (`no-return-to-check`) | open redirect | the auth host returned a 302 to `evil.test`, and another to sibling tenant B, each carrying a live A code (`break.no-return-to-check.red`) |

H2's intact `return_to` matrix [M, `intact.return-to`]: own origin, first and last, gets a
302. These are refused with `return-to-not-tenant-origin`: sibling tenant, unregistered slug,
foreign host, suffix-append, userinfo (`tenant-a…@evil.test`), other port, `https`, and
scheme-relative. Compare Kratos's own `allowed_return_urls`, where a sibling tenant and an
unregistered slug are allowed ([proof](ory-proof-2026-10-07.md) §4.3).

The H2 cross-origin mismatch is not a break: it is the intact design. What makes it red is
that the tenants share a site. `SameSite` cannot tell them apart [M, `diag.strict.cross-origin`]
for the reason the proof gave for apex: `.test` is not on the Public Suffix List. Whether
listing the content domain on the Public Suffix List would change this is [R], not measured.

---

## 4. What a tenant backend receives [M]

| design | Cookie header | other credential-bearing headers |
|---|---|---|
| apex (no edge) | `ory_kratos_session`, `csrf_token_*` (proof §4.1) | — |
| E | **none**: the header is absent once the Kratos cookies are removed (`intact.backend-receives`; `backendReceives` in `cookie-edge.json` lists the header names) | `X-Edge-Identity` for its own tenant, 30 s lifetime |
| H2 | its own `ns_session` only, and only once the user has signed in to that tenant | none; the code arrives in the callback query string once |

Over http, Chrome sent `Origin` on every browser POST and never sent `Sec-Fetch-Site` [M,
`secFetchSiteSeenByEdge`: `POST origin=present sec-fetch-site=null`]. So the edge's
`Sec-Fetch-Site` branch was never exercised. Chrome sends `Sec-Fetch-*` only to potentially
trustworthy origins (https or localhost) [R].

---

## 5. What each design needs in production

**E, apex plus edge.** All of the following are [R] unless marked.

- **Every path to a tenant backend goes through the edge.** That includes the REST API (v1, v2,
  v3), socket.io's polling transport, socket.io's **WebSocket upgrade**, uploads, and anything
  added later. The lab covered only its own HTTP endpoints through the edge: `/`, `/api/echo`,
  `/api/nsjwt/exchange`, `/api/nsjwt/verify` [M]. **It did not cover socket.io or WebSockets.**
  The lab edge proxies plain HTTP and does not handle `Upgrade`. **It did not cover
  Nightscout's real API**, because no Nightscout runs in the lab.
- **The origin check must cover the WebSocket handshake.** That handshake is a GET carrying
  `Origin`, and the lab's origin check exempts GET. As built, a cross-origin WebSocket opened
  from B to A would get A's edge assertion [R, not measured].
- **The tenant backend's CORS policy must not grant credentialed reads to sibling origins.**
  The edge attaches the identity to cross-origin GETs. Only the browser's CORS check keeps the
  response from B's script [M for the exchange POST; R for GET].
- **The strip list must track Kratos's cookie names.** These are the configurable session
  cookie name and `csrf_token_<hash>`. The edge must not log `Cookie`, because it holds every
  user's session (§0 item 2).
- **The backend must be reachable only from the edge**, and the assertion key must be a managed
  secret or replaced by mTLS. In the lab, a straight-to-backend request with a forged assertion
  failed only because of the HMAC [M, `intact.bypass`].
- **Every other host under the apex receives the cookie too:** Hydra's public host, any docs or
  status subdomain, anything added later [R from cookie scope; M for tenant hosts]. Each of them
  must be the edge, the auth host, or trusted with every session.
- **The maintainer's nginx `auth_request` edge** does not strip `Cookie` [R, per the brief]. To
  match E it needs the cookie removed in `proxy_set_header Cookie` and an origin check on
  state-changing requests and on `Upgrade`. Neither was measured in nginx.
- **Non-browser clients** pass the origin check by omitting `Origin` or by forging it [M,
  `intact.replay.edge-cookie`]. The check defends against cross-origin browser requests only.
  It is not a replay defence.

**H2, host-only plus hand-off.** All of the following are [R] unless marked.

- **A tenant-side cross-origin defence** is required for every state-changing request and for
  WebSocket upgrades. It is the same check E puts at the edge, and it is what the §0 item 4
  mismatch shows is missing [M that it is missing; the fix is not built or measured].
- **Logout propagation.** Tenant sessions survive a Kratos logout [M]. The lab stores the
  Kratos session id with each tenant session but never checks it. Options are a back-channel
  logout, or a periodic or per-request `whoami` on the stored session id. Neither was built.
- **A shared code store** with atomic single use across auth-host replicas. The lab's store is
  one process's memory.
- **Per-tenant redeemer credentials** and **a registered origin per tenant**. The lab computes
  the origin from the slug. In production it would be a column, and it fixes the redirect
  target exactly.
- **Membership is checked at code issue only.** A code issued just before a member is removed
  stays valid for its TTL. The tenant's own exchange re-checks membership on each mint [M,
  `intact.control.b-member`: B's session outlived U's removal; B's exchange refused].
- **More redirects.** A cold start costs 6 redirects and each further tenant costs 3 [M],
  against E's 3 and 0.

---

## 6. What this does not establish

- **https and `Secure`.** Everything ran over http with Kratos `--dev`. No `Secure` cookies,
  no `__Host-` prefix, and no `Sec-Fetch-*` headers were measured.
- **socket.io, WebSockets, and Nightscout's own API** were not run behind either design (§5).
- **nginx.** The lab edge is Node. The maintainer's nginx `auth_request` lab was not touched.
- **Public Suffix List** treatment of the content domain: [R].
- **Multiple replicas** of the edge, auth host or code store; **load**; Hydra in either design.
- **E's assertion after logout.** An assertion captured before logout stays valid for at most
  30 s at the backend; this was not measured.
