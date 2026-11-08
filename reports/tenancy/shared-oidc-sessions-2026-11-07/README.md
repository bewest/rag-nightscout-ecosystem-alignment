# Shared optional OIDC human sessions: source capability

This is a bounded implementation record, contributor-facing. The adopted
[shared identity](../../../docs/30-design/tenancy/owner-authority.md#shared-oidc-integration)
and [session decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#m6-human-session-effects-2026-11-07)
remain authoritative. This record does not promote M6, admit real identities,
select a production provider or change the current Compose acceptance candidate.

## Source and ownership

Application branch `codex/shared-oidc-sessions-20261107` is local and unpushed:
`b486f6f6ce2d07ec814c3095989970a8eb83e595`, tree
`021296b0a5189130d40abb01d8aaadb6f11a9d52`, based on the original source
integration `151de0248a1e4301c85b5c638185eec3ca8c38e6`. The application source
owner retains original-branch joining and draft PR publication. This independent
lane is for the next coherent batch. The alignment record branch starts at
`fca6459be238ff433ad6e0b6d4e63b30c66b4b06` and changes only its own claim and record.

Lane detail: `externals/work/HANDOFF-shared-oidc-sessions-2026-11-07.md` (local).

## Implemented, fixed on the local branch

The common protocol adapter uses pinned `openid-client` and `jose`, authorization
code/S256 PKCE, state/nonce, mandatory ID-token signature verification, issuer,
audience, authentication time and exact expiry checks. Provider assertions supply
identity only. The common lifecycle engine consumes explicit current local
authority and keeps management access, idle, absolute and sensitive-action clocks
separate. Provider-backed renewal never resets authentication/absolute time or
counts as management activity. Logout commits local invalidation before browser
clear and optional provider logout. Verified provider logout events receive
durable replay handling and mapped session invalidation.

Single MongoDB uses an operator-provisioned human principal aggregate that owns
its current human grants and session state. Atomic revision comparison fences
revocation and renewal without requiring MongoDB multi-document transactions.
These grants are independent of legacy subject credentials; provider login does
not import root or management membership. PostgreSQL uses additive forced-RLS
tables and session-row transactions with current existing tenant, credential,
subject/role and explicit management-actor authority. Serving does not migrate.

Both modes consume the shared HTTP login/callback/renew/logout/session flow.
Default browser transport is Secure/HttpOnly host cookies with origin/CSRF checks;
direct bearer remains available. Data and management cookies are separate, so
entering management does not replace a display's data session. Concurrent provider
flows use distinct state-bound cookies. Existing API authentication and stream
consumers obtain current human authority per operation or delivery. Successful
management responses qualify for idle activity; data polling, stream delivery,
renewal and unsuccessful requests do not. Default-off single boot and existing
headless authentication remain separate.

## Reproduced source checks

On this source, the focused command below passes 76 checks. The protocol fixture
uses synthetic fetch Request/Response transport, the HTTP fixture uses an actual
Express router without a kernel listener, aggregate persistence uses a source
collection double, and stream factories use recording sockets. These are not
actual MongoDB, PostgreSQL, browser, deployed-provider or full-application runs.

```bash
node node_modules/mocha/bin/mocha.js --timeout 10000 \
  tests/human-session-provider.test.js tests/human-session-http.test.js \
  tests/human-session-lifecycle.test.js tests/human-session-integration.test.js \
  tests/human-session-stream.test.js tests/owner-preview.test.js \
  tests/socket-write-handlers.test.js
```

Root re-ran physical source ablations individually. Bypassing durable session
invalidation, access expiry, session idle/absolute expiry, or provider signature
validation makes the intended refusal wrongly authorize: each selected test
fails with `AssertionError: Missing expected rejection`. Bypassing aggregate
revision fencing makes a renewal racing committed logout return a token accepted
by the next protected operation; its test fails with that exact semantic
assertion. These are semantic reds, not setup or dependency failures. Restored
focused checks pass. Captures are local under
`/tmp/oidc-evidence-20261107/controls/` and
`/tmp/oidc-evidence-20261107/restored-source-focused.log`.

The wider queue measurement was not green: `make queue-status` exited nonzero
with 198 PASS, 43 FAIL and 127 UNMEASURED; this item's prior claim had no runnable
instrument. It is moved to `in-progress`, without claiming a green gate.

## Remaining acceptance and next owner

Actual HTTPS synthetic-provider, native MongoDB/PostgreSQL, real browser cookie
and bearer, current-source application compatibility and reference-provider
acceptance are **UNMEASURED**. Explicit native instruments are prepared at
`tests/human-session-http-native.js`, `tests/human-session-mongo-native.js` and
`tests/human-session-postgres-native.js`. Syntax checking an instrument does not
execute it. Runtime is reserved by the acceptance lead; no independent Docker,
database or browser campaign starts while the current campaign owns capacity.

The old Ory proof was inspected, not repeated. Its synthetic Kratos/Hydra source
and immutable artifacts are under `tools/lab/ory-proof/`. Authentik remains the
intended reference **subject to repeating that proof** on this generic adapter;
no Authentik pass is inferred from the synthetic provider. The existing Kratos
proof remains the measured fallback reference, not proof of this new application
adapter. Production deployment, restore/lifecycle admission of the additive
identity tables, operating capacity and real identity admission remain separate
integration criteria.

Next owner is this source lane for bounded runtime acceptance once reserved,
then the application source owner for an original-branch join at the next coherent
batch. The coordinator owns alignment main integration and the acceptance lead
owns final runtime freezing. No cherry-pick copy, publication or current-candidate
mutation has occurred.

Technical sources consulted: the maintained
[openid-client authorization-code checks](https://github.com/panva/openid-client/blob/main/docs/functions/authorizationCodeGrant.md),
[Authentik OIDC documentation](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/),
[Authentik logout documentation](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/frontchannel_and_backchannel_logout/)
and [MongoDB write-concern semantics](https://www.mongodb.com/docs/manual/reference/write-concern/#acknowledgment-behavior).
Provider documentation is a design input, not executed provider acceptance.
