# nightscout-roles-gateway (NRG, t1pal) — consumer impact against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/nightscout-roles-gateway
- Ref analysed: `origin/master` **4fdd490 (2023-05-26)**, and `origin/replit` **90840ac (2026-01-15)**.
- **The corpus line "behind=0" is misleading, and the brief's warning is right.** Local HEAD is
  90840ac, which is the tip of `origin/replit`, **142 commits ahead** of `origin/master`
  (`git rev-list --count origin/master..HEAD` = 142; `origin/master` is an ancestor of HEAD).
  The default branch has not moved since 2023; the 2026 work is on `replit`. The `replit` diff
  against `master` under `lib/ server.js env.js` is 5 files, +31/−12 (`criteria/core.js`,
  `policies/index.js`, `privy/index.js`, `storage.js`, `env.js`); the other 130-odd commits are
  docs and tests. **None of the replit code changes touches a Nightscout call** (every Nightscout
  call site below has the same content on both refs, line numbers shift by at most one).
- All claims **read-derived**.

## What this service is (and is not)

NRG is **not the proxy**. It is an authorization-decision service that an NGINX load balancer
calls with `auth_request` (`README.md:5-19` on both refs; `docs/warden-gateway.md`,
`docs/ARCHITECTURE.md:339-341` on replit). The warden routes
`/warden/v1/active/backend/for/:expected_name` and `/warden/v1/portal/:subject/backend/for/:expected_name`
(`lib/routes.js:327-330` @4fdd490) answer 200/403 and set **response** headers for NGINX:
`x-upstream-origin`, `x-forwarded-host` (`lib/policies/index.js:107-115`) and, for `nsjwt` policies,
`X-NSJWT: <Nightscout JWT>` (`lib/exchanged.js:75-82`). **The NGINX configuration that proxies
user traffic to Nightscout — and therefore sets or passes X-Forwarded-For, X-Forwarded-Proto,
the websocket Upgrade, and turns `X-NSJWT` into something Nightscout reads — is not in this repo**
(`git grep -n -i -E "proxy_set_header|auth_request_set|X-Forwarded-For|real_ip|remote_addr|Upgrade" origin/replit -- docs README.md` → nothing;
`Dockerfile:13` on replit only installs nginx). Nightscout itself never reads `X-NSJWT`
(`git grep -i nsjwt` over `lib/` of cgm-remote-monitor 92d08342, ddd9b600, ef3404fd → nothing); it reads
`Authorization: Bearer` (`92d08342 lib/authorization/index.js:36-37`). So the deployment's NGINX
must map it; how it does so cannot be checked from the corpus.

## Positive controls (same grep method)

`git grep -n -i -E "axios|/api/v[123]|authorization/(subjects|roles|request)|API-SECRET" <ref> -- lib`
- `lib/criteria/core.js:119` (`:120` on replit) — `GET /api/v1/status.json` (site inspection, anonymous)
- `lib/criteria/core.js:130-133,166` — same with `API-SECRET: sha1(secret)` header
- `lib/tokens/index.js:17-22,40` — `GET /api/v2/authorization/subjects` with `API-SECRET`
- `lib/exchanged.js:24,29` — `GET /api/v2/authorization/request/<policy_spec>` (token exchange)

These four are the **only** outbound Nightscout calls (all axios; `axios.create` appears only in
these three files).

## Surface table

| S-id | what the client does | anchor (repo@sha path:line) | patterns searched |
|---|---|---|---|
| S1 count | none found. No v1 data read is issued; the entries/treatments/devicestatus/profiles checks listed in the `core.js:25-48` comment block are a plan, not code. | @4fdd490 `lib/criteria/core.js:25-48` (comment only) | `count`, `find\[`, `entries`, `treatments`, `devicestatus`, `profiles` |
| S2 operators | none found. | — | `find\[`, `\$(gte\|lte\|in\|exists\|regex\|expr\|where)`, `pipeline` |
| S3 numeric | none found. | — | as S2 |
| S4 shared/aggregate | `GET /api/v1/status.json`, anonymous (`core.js:119`) and with hashed secret (`core.js:166`); **a non-200 from the anonymous call is a mandatory failure** that marks the site "not ok" (`core.js:91-99`, `describe` `:195-218`). The candidate's `status.js` change is only where the client address comes from (`cgm-remote-monitor@ef3404fd lib/api/status.js`); no auth added, so registration of a `denied` site is unchanged. The commented list names `verifyauth`, `/api/v3/version`, `/api/v1/experiments/test` — not implemented. | @4fdd490 `lib/criteria/core.js:82-171` | `status.json`, `verifyauth`, `api/v3`, `experiments`, `/count/`, `properties` |
| S5 auth — how NRG authenticates | Hashed secret: `API-SECRET: sha1(api_secret)` on inspection and subject listing (`core.js:128-133`, `tokens/index.js:17-22`). Token exchange: `GET /api/v2/authorization/request/<policy_spec>` with no other credential; `policy_spec` is a subject access token stored per policy; the JWT is cached for `exp - iat` in Keyv (`exchanged.js:12-54`). Inbound: NRG compares the caller's `API-SECRET` header with its stored hash to exempt "classic uploaders" (`policies/index.js:83-96`). | @4fdd490 as listed | `API-SECRET`, `api_secret`, `Authorization`, `Bearer`, `token=`, `request/` |
| S5 auth — subjects/roles | **Reads** subjects only: `GET /api/v2/authorization/subjects`, result returned verbatim to the owner UI as `tokens` (`tokens/index.js:29-31,52-57`); relies on `accessToken` being in that response, which the candidate keeps (`ef3404fd lib/authorization/endpoints.js:37-45` picks `_id, name, accessToken, roles, notes` — `notes` is additive). **No create or edit of subjects or roles** on either ref. On replit, `docs/token-management.md:7-15,278-290` marks "Subject Management (Deprivilege)" **PROPOSED**: `POST /api/v2/authorization/subjects` with `name`, `roles` — both within the candidate's `SUBJECT_FIELDS` (`ef3404fd lib/authorization/storage.js` `['name','roles','notes','created_at']`). Note for that proposal: the candidate's `createSubject` also drops a caller-supplied `_id` (it copies only owned fields), and the access token is derived from `_id`, so a tool must read the token back from `GET /subjects` after creating. | @4fdd490 `lib/tokens/index.js:40`; @90840ac `docs/token-management.md:282` | `authorization/subjects`, `authorization/roles`, `(post\|put).{0,40}authorization`, `notes`, `created_at` |
| S5 auth — X-Forwarded-For | **NRG sets no X-Forwarded-For** on its own outbound calls (axios defaults; `exchanged.js:24`, `core.js:84,130`, `tokens/index.js:19`), so Nightscout sees NRG's own address for inspection, listing and exchange. On the proxied user path NRG only emits `x-forwarded-host` as a response header for NGINX (`policies/index.js:111`); X-Forwarded-For/-Proto on that path are whatever the external NGINX config sets. | @4fdd490 as listed | `forward`, `x-real-ip`, `X-Forwarded` |
| S5 auth — failed-auth throttle | NRG is one address performing token exchanges on behalf of every visitor. On 15.0.8 one failed exchange (e.g. a `policy_spec` whose subject was deleted) delayed **every** later request from NRG's address, successful ones included (`92d08342 lib/authorization/index.js`, delay applied before the credential is checked). On the candidate the wait is applied only on a failed attempt, keyed on address and on credential (`ef3404fd lib/authorization/delaylist.js:156-166`, `index.js` failure path) — an improvement for NRG. A failed exchange that is retried waits; axios has no timeout configured (`git grep timeout origin/master -- lib` → nothing), and a failed exchange is not cached (`exchanged.js:27-38`), so each warden decision for that policy re-tries and waits. | @4fdd490 `lib/exchanged.js:27-38` | `timeout`, `catch` |
| S5 — TRUST_PROXY interaction (deployment) | User traffic reaches Nightscout through NGINX. With `TRUST_PROXY` unset, Nightscout keeps 15.0.8's behaviour (left-most forwarded address, `X-Forwarded-Proto` honoured) — `ef3404fd lib/server/client-ip.js` `compatibilityTrust`. If an operator sets `TRUST_PROXY=false` or a list that omits the NGINX address, and NGINX terminates TLS, `req.secure` is false and the https redirect loops (`ef3404fd lib/server/app.js:104-110` now tests only `req.secure`). The NRG exchange calls go direct (not via NGINX) unless `upstream_origin` points back through the balancer — not determinable from the repo. | cgm-remote-monitor@ef3404fd as listed | — |
| S6 websocket | none found in NRG. Websocket proxying is NGINX's job and not in the repo. Candidate consequence for a `denied` site behind NRG: the socket is authorized only by the `authorize` message's token/secret, not by any HTTP header, so an `X-NSJWT`→`Authorization` header mapping (if the NGINX config does that) authorizes REST but **not** the live-update socket; on the candidate the socket then gets no data and `loadRetro` answers "Not permitted" (`ef3404fd lib/server/websocket.js` `resolveReadAccess`). On 15.0.8 the same socket received data anyway. Which behaviour a gateway-fronted site shows depends on whether the Nightscout page itself sends a token. | cgm-remote-monitor@ef3404fd `lib/server/websocket.js` | `socket`, `websocket`, `upgrade`, `ws:` |
| S7 `_id` | none found (no data writes). | — | `_id`, `post(`, `put(` in outbound axios calls |
| S8–S11 | none found. | — | `treatments`, `food`, `profile`, `devicestatus`, `cob`, `iob` |
| S12 query shape | Path-only requests; `policy_spec` is concatenated into the path unencoded (`exchanged.js:29`). No query strings. | @4fdd490 `lib/exchanged.js:29` | `?`, `params` in axios calls |
| S13 v3 | none found (only a comment, `core.js:37`). | — | `api/v3` |
| S14 other | none found. | — | `notifications`, `ack` |
| S15 errors | Inspection: any error or non-200 → `status` undefined/`unreachable` → mandatory failure (`core.js:89-120`, `.catch(analyze_response)`). Subject listing: any error → empty list, silently (`tokens/index.js:25-27,41`). Exchange: error propagates to `next(err)`, so the warden answers with the framework's error, not 403 (`exchanged.js:38,66`). A 401 from `request/<token>` on either release is handled the same way; nothing in the candidate changes that status code. | @4fdd490 as listed | `catch`, `status` |

## Bottom line for the join step

No data-path exposure. The candidate items that touch NRG deployments are all **auth-plane and
deployment-config**: (1) the throttle fix helps NRG's single-address exchange pattern;
(2) `TRUST_PROXY` must be set with the NGINX address, not `false`, if NGINX terminates TLS;
(3) on `denied` sites, socket authorization does not see gateway-injected headers; (4) the subject
field allowlist is compatible with NRG's only (proposed) write. The NGINX config that decides (2)
and (3) is outside the corpus.
