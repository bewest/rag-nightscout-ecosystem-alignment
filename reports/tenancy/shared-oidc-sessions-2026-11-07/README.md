# Shared optional OIDC human sessions: capability record

The shared optional human-login/session capability is **fixed on a local branch**
and frozen for bounded acceptance. It is not merged or released. Actual signed
MongoDB/PostgreSQL, Vault, HTTPS and browser acceptance remain **UNMEASURED**.
The adopted [shared identity contract](../../../docs/30-design/tenancy/owner-authority.md#shared-oidc-integration)
and [session decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m6-human-session-effects-2026-11-07)
remain authoritative; no policy exception, M6 promotion or production identity
admission follows from source checks.

## Frozen source and ownership

Original application branch `codex/shared-oidc-sessions-20261107`, commit
`eadf41f889e48ab6762724e62d4e6c85d50fb654`, tree
`36bb9aae866712c69c8511498e1ee192ce16c653`, is local and unpushed at
`/tmp/crm-shared-oidc-sessions-20261107`. Its original integration base is
`151de0248a1e4301c85b5c638185eec3ca8c38e6`. The application source owner retains
normal original-branch joining and PR publication; the coordinator owns alignment
main integration. This independent next-batch source has not joined the current
Compose candidate. Lane detail is in
`externals/work/HANDOFF-shared-oidc-sessions-2026-11-07.md` (local).

## Capability and contract repair

The common adapter uses pinned `openid-client` and `jose`, authorization code/S256
PKCE, state/nonce, explicit ID-token signature verification, issuer/audience,
authentication time and exact expiry checks. Provider assertions identify a
person; current local authority supplies permissions. Renewal requires provider
proof and preserves management authentication, idle and absolute clocks.
Successful qualifying foreground management operations alone advance idle;
sensitive operations additionally require current authentication freshness.

The initial opaque-access prototype violated the existing asymmetric contract.
That **read-derived audit finding** was confirmed independently and repaired
without changing policy. Current human access uses actual Ed25519
`ns-access+jwt`, explicit NS issuer/data/management audiences and provisioned
purpose/tenant-bound public keys. Persisted hashes are secondary issuance
bindings. Existing default/multitenant verification remains UUID-strict; the
closed single-human profile accepts exactly `single`, separate from clinical
storage's unchanged single scope. A distinct bound 64-byte Vault Transit signer
performs issuance; the existing 32-byte legacy HMAC API is unchanged. Verification
uses local public keys and current store authority, without a Vault verification
call or expiry grace.

Single Mongo uses one privately provisioned site authority aggregate containing
global current keys, human mappings/grants and sessions. Bounded atomic CAS
retries re-read all current state; a superseded or uncertain write returns no
signed result. PostgreSQL uses additive forced-RLS session/identity tables and
current existing tenant/credential/grant/management-actor/accepted-key state.
Session-row transactions serialize logout and renewal; serving does not migrate
or acquire key-update privileges. Native behavior, capacity and standalone-Mongo
performance remain unmeasured.

Both modes consume login/callback/renew/logout/session HTTP routes, Secure and
HttpOnly cookie default, direct bearer, separate data/management cookies and
state-bound concurrent flow cookies. Current authorization is consumed per HTTP
operation and stream delivery. Recognized human failures cannot fall through to
headless authentication. The existing browser sign-in dialog consumes provider
login and renewal; human mode suppresses dormant legacy credentials. Sign Out
forgets this browser's legacy material, commits local revocation, clears its
cookie, then follows the configured provider logout endpoint when available.
Unconfirmed local revocation remains visible and never becomes a success reload.
Default-off single behavior and headless authentication retain separate paths.

## Reproduced source evidence

The frozen source passes **194 explicit-file checks**, using actual crypto and
application modules with synthetic fetch, request/response, collection and socket
I/O doubles plus a hermetic DOM. Single stream tests use the actual aggregate
adapter over doubled I/O; multitenant stream tests use an explicitly test-only
store, not PostgreSQL. Ten Vault admission cases perform no transport. No native
persistence, browser, full application or deployed-provider result is inferred.
Root capture: `/tmp/oidc-evidence-20261107/signed-frozen-source.log` (local).
The [immutable signed-source summary](signed-eadf41f8.json) owns the capture.

Physical controls on isolated copies of the exact frozen source bypass signature,
current-key, current-authority, durable invalidation, management lifetime, expired
lookup separation and the global CAS fence one at a time. The intended refusal
becomes `AssertionError: Missing expected rejection`; CAS bypass instead returns
a renewed credential accepted by the next protected operation. Those are semantic
reds, followed by byte-exact restoration and passing focused checks. The original
checkout remains clean. Browser-consumer controls separately demonstrate ignored
local logout, ignored provider navigation, false success after uncertain revocation
and delivery after committed logout, with restoration passing. These remain
source/DOM/socket-double evidence.

Independent focused crypto/config audit found no load-bearing mismatch within
its stated source scope. Changed production lint passes with two existing
unsafe-regex warnings; test inventory passes at 596 files / 8 tiers and whitespace
checks pass. Full application/browser/corpus/prcheck belongs to the next coherent
joined candidate and was not run by this leaf.

A broader compatibility selection accidentally loaded the existing native
`authorization-reload-boundary.test.js` setup hook. Its Mongo connection timed
out; that setup failure is retained in `signed-headless-consumers-source.log`,
not credited as native evidence. The process exited; a subsequent process scan
found no matching Node process. The corrected source-double-only selection
passed. Subsequent verification uses an explicit source-file allowlist, not a
name grep that can load native hooks.

The initial wider queue measurement was nonzero: 198 PASS, 43 FAIL and
127 UNMEASURED. `MT-IDENTITY-PLAN` remains in-progress with no runnable complete
acceptance gate; source tests do not make that programme item green.

## Historical prototype capture

The [immutable HTTPS summary](https-275c238c.json) retains the lead-reserved run
on original `275c238c52a0e6204bf1ed7e5279d20309f16820`: 18 actual HTTPS assertions
with synthetic provider/source-store and independently verified resource closure.
It exercised transport on the **nonconforming opaque prototype**. It is not
signed-policy conformance, native database, browser or current-source acceptance.
The single grant was consumed and authorizes no further run. Earlier prototype
source captures are retained locally with their original source attribution.

## Remaining acceptance and next owner

The sole runtime lead must review and reserve the next finite, owned window.
Prepared instruments refuse without explicit reservation/configuration before
connecting or launching. They create only synthetic owned resources and retain
cleanup failures. The proposed batch uses cached Mongo/PostgreSQL/Vault images,
least-privilege PG identities, actual sign-only/nonexportable Vault issuance and
native-store HTTPS consumption, then real cookie/bearer/browser cases if granted.
A Vault pass alone is not a consumed HTTP or browser pass. Parent timeboxing and
physical process/listener/service closure remain part of the reviewed runtime
plan. No current-candidate capacity or idle interval is treated as a grant.

Authentik remains the intended reference subject to the existing Kratos proof;
the historical Ory artifacts were inspected, not repeated on this adapter.
Real reference-provider acceptance and production service-login, deployment,
restore/lifecycle admission and operating capacity remain separate boundaries.
After this lane closes bounded acceptance, the source owner receives the complete
original branch at the next coherent join. No cherry-pick, push or PR mutation
has occurred in this lane.

Technical inputs: maintained
[openid-client authorization-code checks](https://github.com/panva/openid-client/blob/main/docs/functions/authorizationCodeGrant.md),
[Vault Transit signing API](https://developer.hashicorp.com/vault/api-docs/secret/transit#sign-data),
[Authentik OIDC](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/),
[Authentik logout](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/frontchannel_and_backchannel_logout/)
and [Mongo write concern](https://www.mongodb.com/docs/manual/reference/write-concern/#acknowledgment-behavior).
Documentation is a design input, not actual provider acceptance.
