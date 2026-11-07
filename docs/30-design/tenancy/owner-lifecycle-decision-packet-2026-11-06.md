# Owner session and issuer lifecycle: the decision packet (2026-11-06)

*What this is: a **draft decision packet for maintainer review** (contributor-facing), read-derived
unless a row says otherwise, written 2026-11-06 by session `-8c` under the batching plan's §5
assignment. It lets the maintainer decide the five owner-plane questions that the
[milestone promotion review](milestone-promotion-review-2026-11-06.md) lists as unmeasured and
unimplemented (rows "Human management issuer/refresh", "Existing-grant clamping", "Tenant
lifecycle"; ranked item 7). Nothing here is a decision: a decision taken from this packet is one row
in `releases/cgm-remote-monitor-16.0.0/decisions.md`, after which this packet points at it. No code
was written; no gate was run. Companion: [the five critical-path decisions](multitenant-open-decisions-2026-11-06.md),
whose items 1 and 2 overlap Q4 below and are cited rather than re-asked; item 1 was decided on 2026-11-06 after this packet was drafted, and Q4 records that decision.*

**Anchors, read from `git` at the moment of writing.**

| tree | head |
|---|---|
| alignment `main` at the packet's start | `532af97c1b3c3404da5f5323a4e73f08d6768304` |
| alignment `main` at the packet's write | `4833e0b53182936396ed70e12284bde0e447558d` (the head moved three times during the reads: `7cf54d1b1`, `6b8e486f2`, `4833e0b53`; of the files cited here only the batching plan, the roadmap, the dashboard, the integration record (R66–R68 appended, not cited) and the work queue changed in those ranges; every passage cited below was re-read on `4833e0b53` and found unchanged, and the roadmap line numbers were re-taken there; the [open decisions note](multitenant-open-decisions-2026-11-06.md) arrived in the first range and is cited) |
| accepted code head (R62), read-only worktree `externals/work/crm-codex-replay-controls-closure-20261106` | `83582e876dd193f4448f44c28e379fb5464a26c7`, published head of draft #8898, containing `official/dev 4a482627` (R62), CI and CodeQL green there (R64) |

Every `file:line` below is on `83582e87` unless marked otherwise. Figures are quoted from the record
text named beside them, never from memory. **Measured** means a record says a probe or suite ran it;
**read** means it comes from reading code or a document.

---

## 1. What exists today, measured against read

The data-path credential is built and measured; the owner plane has a policy transaction and a
dormant HTTP factory; everything that *issues* a human credential, keeps a session alive, or
changes who owns a tenant does not exist in code.

| capability | mechanism on `83582e87` | measured (record) | state |
|---|---|---|---|
| Native per-tenant **data** token, new format | Ed25519 `ns-access+jwt` verified locally: header `alg/typ/kid` only (`lib/tenant-authorization/access-token.js:36-37`); key resolved by `(tenant, kid)` and must bind issuer and purpose (`:39-41`); claims `iss, aud, tid, purpose, sub, sid, cv, iat, nbf, exp`, lifetime capped by policy (`:47-55`); one PostgreSQL snapshot per operation joins tenant, session, credential generation, key acceptance and roles (`access-postgres.js:44-58`); the token is refused unless the tenant is active, the session is active and its generation equals the credential's, the key is active, `cv` matches, and the session outlives the token (`access-token.js:66-68`). Policy in the preview: purpose `data`, `maxLifetimeSeconds: 28800` (`lib/server/serve/preview-config.js:160`) | **R48**: actual API, 7 new-format cases, A's token on B `TOKEN_SIGNATURE`, next-read revocation across processes, Vault paused: new-token reads continue; controls red at the HTTP assertion | measured, unselected by default (`accessTokens` absent preserves existing behaviour, `access-tokens.md:27`) |
| Legacy per-tenant data credential (root secret, raw subject token, HS256 JWT) | `exchangeLegacyCredential` signs inside the secrets component, exactly 28800 s (`lib/secrets/component.js:121-129`); HS256 with a version `kid` (`:175-177`); root and subject derivation reproduce `enclave.js` (`lib/secrets/legacy-credentials.md:63-67`) | R25/R26 (dashboard rows `7eb76c71`, `81bc71e6`); re-run inside R48's full campaign (7058 / 80 / 0) | measured |
| Management **actor** and selected proposed-grant policy | Actor = `{tenant, principal, consumer}` authenticated by an injected `authenticateManagement` callback (`lib/server/subject-management-app.js:79-83`); the store locks config, operator policy and the actor row `FOR SHARE`, then requires every proposed permission to be in catalogue ∩ ceiling ∩ the actor's `delegable` (`lib/subject-admin/owner-policy.js:81-110`); audit row per mutation (`postgres.js:96-100`). Tables `tenant_owner_policy(catalogue_digest, ceiling)` and `tenant_owner_actors(principal, consumer, active, can_update, delegable)` from migration `0004_owner_policy_fencing` (`lib/tenant-authorization/postgres-candidate.json`) | **R53** on `17f9a457`: 22 real PostgreSQL checks; catalogue, ceiling, delegation and actor controls each 0 passing / 1 assertion with actual HTTP 200 vs 403; full 7127 / 80 / 0 | measured; REST37 subset only (PUT subject); not composed on any listener |
| Optional existing-grant **clamping** (reader side) | Both readers accept `ownerPolicy: { catalogue }`; when set, the snapshot joins the operator ceiling and filters every stored permission group to catalogue ∩ ceiling (`access-postgres.js:18, :24-25, :76`; `owner-policy.js:129-140`); wildcard roles, the `readable` default and non-subject principals refuse (`owner-policy.js:131-137`; `tenant-authorization/postgres.js:136, :178`) | **R62** on `87133959`: owner-reader gate 12 / 0 / 0, intersection ablation admits three protected operations, restored 12; **R63**: oref0 subject-token uploads match the reference; emptied ceiling → 401 no effect; cgmsim root upload → **503** no effect | measured; **unselected**: `preview-api.js:43-46` composes the reader without `ownerPolicy` |
| Dormant owner HTTP factory | `createSubjectManagementApp` returns an Express app and opens no socket (`subject-management-app.js:56-61`; README `:92-95`); routes `PUT /api/v2/authorization/subjects`, `DELETE .../:_id` (`:94-110`) | R42 standalone management gate (dashboard T30-TENANT-ADMIN row) | measured at factory level; no listener |
| Secrets component: sign, verify, reveal | `sign` is tenant-wide minting authority for a trusted issuer (`lib/secrets/README.md:43`); `reveal` is its own permission and audit event, "the eventual owner policy must refuse operator reveal and enforce its selected re-authentication policy" (`:42`); private keys never leave Vault (`:89`) | 34 passing combined secrets/Vault/PG suite (`README.md:406-407`); Vault outage refuses decrypt | measured; no owner route calls `reveal` |
| CLI roles | only `api` is runnable: `multitenant <role>` "run explicit PG/Vault preview api; other roles unavailable" (`lib/cli/index.js:26-29`) | R37/R38 executable boot (dashboard) | measured for `api` only |

**Unimplemented on `83582e87`, each confirmed by reading the tree** (no `lib/` file constructs a
`purpose: 'management'` verifier or signs an `ns-access+jwt`; the only signers of that type are
test fixtures, `tests/fixtures/owner-clamping-acceptance.js` and `tests/fixtures/multitenant-preview-replicas.js`):

| gap | where the records say so | what the code has instead |
|---|---|---|
| human **issuer** (login → management token) | R48 "Complete human/refresh-session issuance ... remain open"; R53 "human issuer/refresh ... unimplemented" | `access-token.js:22-26` accepts a verifier with purpose `management`; nothing composes one; `access_keys.purpose` and `access_sessions.purpose` already admit `'management'` (`access-candidate.json`, migration `0001_access_state`) |
| **refresh / session credential** | owner-authority.md:27 "PostgreSQL session record and one-way verifier; rotation/reuse detection" | `access_sessions(session_id, subject_id, credential_id, generation, expires_at, active, purpose)`: a presence-and-expiry row that `sid` references; **no verifier column, no idle timestamp, no refresh secret**; rows are "explicitly operator-provisioned in this preview" (R48) |
| existing-grant clamping **on** | R62 "All options remain unselected" | the reader option exists; no runtime configuration selects it (`tenant-authorization/README.md:84-86`) |
| **DELETE policy** in selected mode | R53 "DELETE refuses"; dashboard T30-TENANT-ADMIN "DELETE policy ... remain open" | `postgres.js:133` `if (owner) throw failure('SUBJECT_ADMIN_FORBIDDEN')`; unselected remove deletes links, legacy metadata and the subject row with no guard (`:136-141`) |
| production **owner listener** (`ns-tenant-admin`) | R53/R54 "production listener unimplemented"; queue T30-TENANT-ADMIN no-gate: "Full listener admission remains unmeasured" | factory only; decided topology is a second bound socket inside `ns-api` (execution plan §2.9, 2026-10-16). The open-decisions note (item 2) reports an actual two-listener run on candidate `4cd95d06`, which is **not** on `83582e87` and is in its own campaign |
| **ownership transfer, co-owner, last-owner protection** | owner-authority.md:45-48 "sensitive explicit operations; last-owner removal must not orphan the tenant"; subject-admin README `:259-262` | `tenant_owner_actors` is read `FOR SHARE` only (`owner-policy.js:85-87`); no code inserts, transfers or counts actors |
| **lifecycle deletion request / execution split** | roadmap `:648-652` "an owner may export or request deletion; the operator authorizes and executes"; owner-authority.md:40-43 | no request table, no operator command; `nightscout multitenant admin` is not a runnable role |
| **recent-reauthentication** for reveal and ownership changes | owner-authority.md:101 "Within 5 minutes"; D22 §2.13 "Reveal requires explicit authority and recent reauthentication" | no `auth_time` claim in the token (`access-token.js:53` closed claim set), no session column for it |
| owner audit "who took an owner action and when" | platform authority spec §8 "Not recorded"; schema spec maintainer note 2026-10-29 "one audit approach" | `tenant_subject_admin_audit` holds tenant, principal, consumer, target, operation, time for subject mutations only (`postgres.js:97-99`) |

**Single-tenant comparison (read, `83582e87`).** The owner on `single` is whoever holds `API_SECRET`:
a matching secret grants shiro `['*']` (`lib/authorization/index.js:178-185`), and AU2 of the
authority spec records that owner actions on `single` are taken with it. Subject tokens are derived
from the secret (`storage.js:296-299` via `enclave.getSubjectHash`, `enclave.js:71-76`), so the raw
subject token is a non-expiring bearer credential; a JWT is minted from it with an **8 h** default
(`enclave.js:58-61`) and re-minted on demand by `GET /api/v2/authorization/request/:accessToken`
(`endpoints.js:31-39`, `index.js:306-334`) with no session, no refresh credential and no revocation
other than deleting the subject (`index.js:207-209`). The signing key is one per install, read from
`node_modules/.cache/_ns_cache/randomString` (`enclave.js:22-30`). `single` is unchanged by every
option below (D1, D4; owner-authority.md:32-34).

---

## 2. The questions, one topic each, in dependency order

Dependency order: Q3 (who mints, which audience) is needed by Q2 (what a session is) and Q1 (who the
person is); Q4 and Q5 sit on top. They are presented Q1 → Q5 as briefed, with the dependency named in
each.

### Q1. Human identity provider for owners

**Mechanism.** D17 row 2 as adopted in principle (2026-10-12): Kratos, one cohort-wide pool, cookie
scope E, four production conditions, no real identities until the compliance question has an owner.
D17 as amended (2026-10-27): the provider is interchangeable ("bring your own auth": Kratos, Clerk or
another), behind Nightscout's own token exchange, "to keep in-house human-identity security surface
small"; owed: the adapter interface and the provider properties a hoster must supply. The owner
authority contract (owner-authority.md:82-87): "Human authentication uses an interchangeable identity
provider; Nightscout maps verified provider/subject to current tenant access and exchanges it for a
tenant-bound management token. No custom password/recovery system. Provider sessions alone do not
certify current Nightscout grants." The schema spec settles the membership key as `(provider,
subject_id)`, text, no foreign key, per tenant (Q10, Q19; table renamed `tenant_access_grants`, Q18).

**What is measured.** T30-ORY-PROOF (2026-10-07, Kratos v1.3.1/Hydra v2.3.0 and v26.2.0): 23/23 on
both lines; isolation is held entirely by the `nsjwt` exchange (Host-first resolution, membership
row, per-tenant key, client-id check), not by Ory; a minted token lives to its own `exp` (3600 s in
the lab) whatever happens to the Kratos session (§2 revocation rows). Cookie variants (2026-10-12):
E 21/21; H2 24/26 with the two misses being cross-origin writes once a tenant session exists, and a
Kratos logout not reaching tenant sessions (§0 items 2-4). Neither ran over https, through socket.io,
or against Nightscout's real API (§6). **Read, not run:** every claim about Clerk or any provider
other than Kratos; the adapter interface; NRG's pipeline on current Ory beyond §5 of the proof.

**Options.**

- (a) **Generic OIDC adapter behind the exchange; Kratos is the measured reference deployment.**
  Nightscout implements one adapter contract (issuer, audience, subject claim, session-id claim,
  logout back-channel if offered), and ships Kratos's configuration as the reference because E's
  edge conditions were measured for it. Owners sign in at the provider; `ns-tenant-admin` never sees
  a password.
- (b) **Kratos only**, as D17 row 2 before the amendment: one pool, scope E, and Kratos's session
  API as the session of record.
- (c) **Native owner password** in Nightscout (hashing, recovery, MFA in `lib/`), no provider.
- (d) **Defer**: management credentials stay operator-provisioned (the R48 shape) until a provider
  is chosen; owners never log in during the preview.

**Trade-offs by axis.**

| axis | (a) generic adapter, Kratos reference | (b) Kratos only | (c) native password | (d) defer |
|---|---|---|---|---|
| long-term direction | matches D17 as amended; the exchange is the seam the proof showed carries isolation | contradicts the amendment; a cohort pool is "effectively irreversible once identities exist" (§2.9) | contradicts owner-authority.md:85 "No custom password/recovery system" | leaves M6's human-identity criterion without an implementation path |
| architecture | one adapter interface; provider state stays outside the tenant tables | provider-specific session API in the exchange | password store inside the tenant DB; recovery, MFA, lockout all ours | unchanged |
| backward / forward compat | `single` unchanged; provider swap is configuration | a hoster with Clerk or an enterprise IdP cannot use it | none for `single`; every future provider needs a second path | none |
| maintenance | adapter surface small; provider updates are the hoster's | we track Kratos releases (calendar versions, §0 item 6) | highest: password storage and recovery "need updates in the wild" (amendment) | none now, all later |
| reliability | provider outage: existing sessions continue through our session row (Q2); new logins refuse (contract `:141-143`) | same, plus Kratos's cohort-wide session scope hazards (§4.1) | no external dependency; but recovery flows are the usual breach surface | n/a |
| performance | one exchange per login; per-operation cost is ours either way (R48) | same | same | same |

**Who notices.** Owners: under (a)/(b) they sign in at a provider-hosted page and land on their
tenant; under (c) at a Nightscout page; under (d) they cannot sign in at all. Operators: (a)/(b)
require the edge conditions of scope E (strip Kratos and CSRF cookies before any tenant backend,
refuse cross-origin writes including WebSocket upgrades, every path through the edge, measured over
https) or an equivalent for their provider; (c) requires none, and gives them a password database to
protect. **Multitenant only.** `single` keeps `API_SECRET`.

**Recommendation: (a).** Direction: it is D17 as amended, and the proof already showed the
exchange, not the provider, carries isolation. Architecture: the adapter boundary is the only place
provider differences live. Compatibility: `single` untouched; a hoster swaps providers by
configuration. Maintenance: the smallest in-house surface that still works. Reliability: the
session of record is ours (Q2), so a provider outage degrades to "no new logins", which the contract
already specifies. Performance: unchanged from R48. The compliance-owner condition in D17 row 2 is
unchanged by this choice and remains a maintainer gate before any real identity exists.
**Unmeasured:** any provider other than Kratos; the adapter against Nightscout's actual listener;
E's edge over https and through socket.io.

### Q2. Session model and lifetimes

**Mechanism.** The contract's table row (owner-authority.md:27): "Refresh/session credential:
PostgreSQL session record and one-way verifier; rotation/reuse detection or provider-supported
session equivalent." Adopted initial limits (`:97-102`): human management access token **10 min**;
session idle / absolute **30 min / 12 h**; freshness for reveal, ownership changes and privileged
credential issuance **within 5 min**; existing device/client exchange JWT **8 h** preserved. "Idle/absolute
expiry requires current server-side session enforcement. Token expiry is not revocation" (`:105-106`).
In code: `access_sessions` has `expires_at` (absolute) and `active`, nothing else about time; the
verifier refuses a token whose `exp` exceeds the session's `expires_at` (`access-token.js:68`) and
refuses when the session is inactive or its generation lags the credential's (`access-postgres.js:79`).
The serving reader is SELECT-only by contract and startup screen ("must not own tables, bypass RLS
or mutate authority", `access-tokens.md:33-36`; `access-postgres.js:27-36`). The lab token was
3600 s (ORY proof §2); the preview data token is 28800 s (`preview-config.js:160`).

**Measured.** R48: committed session revocation refuses the same token on the next read across
independent processes (controls: removing the session-active check turns a revoked session's GET
from 403 to 200). The November 5 measurement: 16 semantic checks, 4 controls, 2880 timed operations;
local arms make 0 Vault calls per operation. **Read:** everything about refresh, rotation, reuse
detection and idle expiry; none of it exists in code.

**Options.**

- (a) **PostgreSQL session row is the session of record, extended** with a refresh verifier
  (one-way hash of a random refresh secret), `last_refreshed_at`, and a rotation family id.
  Refresh is a write performed only by the issuer (Q3); every refresh rotates the secret; a
  presented secret that is not the current one revokes the whole family (reuse detection). Idle
  expiry is enforced **at refresh**: the issuer refuses a refresh when `now − last_refreshed_at`
  exceeds the idle limit. Data and owner readers stay SELECT-only and keep checking
  `active`, `expires_at` (absolute) and generation per operation.
- (b) **Provider-held sessions**: no refresh of our own; the browser re-exchanges the provider
  session for a new 10-minute token; our `access_sessions` row mirrors the provider's session id.
- (c) **Per-operation idle enforcement** in the readers: each operation updates `last_used_at`.
- (d) **Long-lived management token** (hours) with no refresh, revoked only by session row.

**Trade-offs by axis.**

| axis | (a) PG session + rotating refresh | (b) provider sessions | (c) per-op idle write | (d) long token |
|---|---|---|---|---|
| direction | the contract's first-named form; "provider sessions alone do not certify current grants" (`:85-86`) | the contract's "provider-supported equivalent", conditional on logout propagation, which H2 measured as **absent** (`intact.logout`) | contradicts the read-only reader; R48 measured the reader with no mutation grant | contradicts the 10-minute limit |
| architecture | one writer (issuer), many readers; matches R48's split | exchange depends on provider session API per adapter | turns every data worker into an authority writer | simplest; weakest |
| compat | `single` unchanged; device tokens untouched (8 h preserved) | tied to provider | same as (a) for clients | none |
| maintenance | our table, our rules; one more migration in the access candidate | per-provider session semantics | lock contention paths to characterise | least |
| reliability | provider outage: refresh continues until idle/absolute expire (contract `:141` "Provider/identity outages ... need their own explicit acceptance") | provider outage ends all management sessions at the next 10-minute boundary | write on the hot path under outage | long exposure window of a stolen token |
| performance | one extra UPDATE per 10 min per owner session | one exchange per 10 min per owner | one UPDATE per operation (R48 measured reads at 2.8/2.3 ms p50 combined; a write per op is unmeasured) | none |

**Who notices.** Owners: (a) and (b) both give a silent refresh every 10 minutes and a forced sign-in
after 30 idle minutes or 12 hours; (b) additionally signs them out whenever the provider is down;
(d) keeps them signed in for the token's life even after a revocation that the session row has not
caught. Operators: (a) adds one migration and an issuer role; (c) changes the serving role's grants.
**Multitenant only.**

**Lifetimes.** Those already stated: 10 min / 30 min / 12 h / 5 min / 8 h (owner-authority.md:97-102);
3600 s was a lab value, not a policy; 28800 s is the data cap in code. Values the maintainer must set,
each with a recommended default and its basis:

| value | recommended default | basis |
|---|---|---|
| refresh-secret reuse grace (a second presentation of the just-rotated secret within this window is a retry, not an attack) | 30 s | the cookie-variants record notes E's assertion was valid "for at most 30 s at the backend" (§6); a retry window longer than a network timeout turns reuse detection into a false-positive generator. **Unmeasured** |
| management session absolute lifetime for **headless** management credentials (operator-provisioned, owner-authority.md:89-93) | same 12 h, renewable without a human | the contract says unattended uploaders renew without a human login; headless management should not be looser than human |
| maximum concurrent management sessions per (tenant, subject) | 5 | an owner on a phone, a laptop and a caregiver's browser; bounds the family-revocation blast radius. **Unmeasured** |
| management-token clock skew tolerance | 0 (none) | `access-token.js:51` already refuses `iat > now`; the lab ran in UTC with synchronised clocks; add tolerance only if a measurement shows refusals |

**Recommendation: (a).** Direction: it is the contract's primary form and keeps "provider sessions
do not certify grants" true in code. Architecture: it preserves R48's writer/reader split, which is
what made the read-only serving identity possible. Compatibility: device tokens and `single` are
untouched. Maintenance: one table extension in our own candidate. Reliability: the only outage that
ends a session early is PostgreSQL, which already refuses every protected operation. Performance:
one write per ten minutes per session. **Unmeasured:** the refresh endpoint itself, rotation under
concurrent refreshes, and the idle rule; each is an entry-bar control in §3.

### Q3. Issuer and audience split; key binding and rotation

**Mechanism.** D14: per-tenant signing key, resolved after tenant resolution. D16: three listeners;
`ns-tenant-admin` is a second bound socket inside `ns-api` (decided 2026-10-16). D22 as amended
2026-11-05 and the contract's Vault amendment (owner-authority.md:110-122): private keys stay in
the secrets component; serving workers verify with provisioned public keys; "verification pins
algorithm, issuer, audience, tenant, purpose and key binding ... rejects unknown keys. Key discovery
never follows a request-supplied URL/JWK." In code the verifier already enforces all of that:
`key.tenant`, `key.kid`, `key.issuer`, `key.purpose` must match (`access-token.js:40-41`); `aud`,
`tid`, `purpose` are claims (`:47-48`); `access_keys` is keyed `(tenant_id, kid, purpose)` with
`active` (`access-candidate.json`), and `keyActive` is checked per operation (`access-token.js:66`).
The secrets component's `sign` is "tenant-wide minting authority, reserved for a trusted token
issuer" (`lib/secrets/README.md:43`); the call-path lab decided the owner dashboard calls
`ns-tenant-admin` with an owner token and that "no component on the dashboard's path holds a
credential for every tenant" (execution plan §2.13, call path). The data verifier refuses
management-purpose tokens (`access-tokens.md:48`).

**Measured.** R48: public keys bind issuer, tenant, kid and purpose; unknown keys refuse without
legacy fallback; duplicate key material refuses at boot (`preview-config.js:155-156`). The
secrets suite: rotation creates new provider versions without export; retirement control shows
old ciphertext refuses (`lib/secrets/README.md:318-320`). **Read:** no issuer exists; no management
key has ever been provisioned; rotation of *token* keys (as opposed to ciphertext rewrap) is
described, not run.

**Options.**

- (a) **One issuing role beside the secrets component** (`nightscout multitenant secrets`, or an
  `issuer` role that is the only holder of the `sign` capability), minting **both** audiences with
  **separate keys per (tenant, purpose)**; `ns-tenant-admin` holds public keys only and is a
  verifier, exactly like `ns-api` in R48. The exchange (Q1) and the refresh (Q2) are endpoints of
  this role, reached from `ns-tenant-admin` by an internal request, never from the browser.
- (b) **`ns-tenant-admin` is the issuer**: the owner socket holds the management signing
  capability for every tenant it serves.
- (c) **The provider issues** the management token (Hydra-style): the owner listener verifies the
  provider's token directly.
- (d) **One key per tenant for both purposes**, purpose carried only by `aud`.

**Trade-offs by axis.**

| axis | (a) separate issuer role, per-(tenant,purpose) keys | (b) owner listener mints | (c) provider mints | (d) one key, two audiences |
|---|---|---|---|---|
| direction | the call-path decision and the Vault amendment as written | contradicts "no component on the dashboard's path holds a credential for every tenant" | abandons D14 for the human path (§2.9: "Letting Hydra issue the token instead would abandon D14") | weakens D14's purpose binding |
| architecture | the schema already keys by purpose; verifiers unchanged | the listener gains the one capability R48 kept out of serving processes | provider-specific claims in every verifier | purpose check reduces to a claim check (the proof's `no-claim-check` arm shows a claim check is a second layer, not the first) |
| compat | management tokens refused on the data socket by key *and* claim | same | each provider a different token shape | a compromised management key signs data tokens |
| maintenance | one role to operate; rotation is per (tenant, purpose) | fewer processes | provider's rotation schedule | half the keys |
| reliability | issuer down → no new logins or refreshes; existing tokens verify (R48's Vault-paused result) | listener compromise = minting | provider down = no logins; no refresh of ours | key compromise reach doubles |
| performance | one internal request per login/refresh | none | none | none |

**Who notices.** Owners: nothing between (a), (b), (d); under (c) the token in their browser is the
provider's. Operators: (a) is one more role to run, which D21 already names (`secrets`); (b) is one
fewer. **Multitenant only.**

**Key binding and rotation under (a), proposed for the decision row.** Two `kid`s per (tenant,
purpose) may be active at once; a new `kid` is activated at least one maximum token lifetime
(10 min management, 8 h data) before the old is deactivated, so no live token's key retires under it;
retirement is `UPDATE access_keys SET active = false`, which every verifier observes on its next
snapshot (`access-token.js:66`); the public key reaches verifiers through the provisioned
configuration the preview already uses (`access-tokens.md:8-28`), never from a request. Rotation
period is a value the maintainer must set: recommended **90 days** for management keys and **365
days** for data keys, basis: the longest lifetime a stolen *public* key could be useful is zero and a
stolen private key cannot leave Vault (`lib/secrets/README.md:89`), so the period bounds only the
window of an undetected issuer compromise; **unmeasured**.

**Recommendation: (a).** Direction and architecture: it is what the call-path lab and the Vault
amendment decided, and the schema already carries the `(tenant, kid, purpose)` key. Compatibility:
the R48 verifier needs no change, only a second configured purpose. Maintenance: one issuer, two key
sets. Reliability: issuer outage degrades to "no new sessions"; verification continues. Performance:
one internal hop per login or refresh, not per operation. **Unmeasured:** the issuer role itself,
cross-purpose refusal on the owner socket (the data-side refusal is measured, the owner-side is not),
and rotation overlap.

### Q4. Existing-grant clamping

**Mechanism.** R53's policy constrains **proposed** grants only (`owner-policy.js:77-111`). R62's
optional reader clamps **stored** grants at every snapshot: `effective = owner.clamp(rows, groups)`
filters each group to catalogue ∩ current ceiling (`access-postgres.js:76`; `owner-policy.js:139`).
With the option set, a tenant whose `anonymous_roles` include `readable`, or whose stored roles hold
a wildcard (the shipping defaults `admin: ['*']` and `readable: ['*:*:read']`, `authorization/storage.js:239-242`,
if imported as-is), fails `concretePermissions` and the reader throws `ACCESS_AUTHORITY_INVALID`
(`owner-policy.js:131-137`), which the HTTP layer maps to **503** (`lib/server/tenant-app/index.js:18`);
root and anonymous principals are refused as `TENANT_AUTHORITY_PRINCIPAL_INVALID` (`tenant-authorization/postgres.js:136`).
The contract requires exactly this semantic: "Tightening current policy bounds effective authority
even when an old stored assignment remains" (owner-authority.md:55-56), and "takes effect on the
next protected operation across workers" (`:106-107`). The reader has no delegator lineage: it
bounds "the current tenant ceiling, not the current authority of whichever actor issued an old
grant" (`tenant-authorization/README.md:101-103`).

**Measured.** R62: 12 / 0 / 0 with the intersection ablation admitting three protected operations
(red) and restored 12; R63: oref0 subject-token uploads unchanged, emptied ceiling → 401 with no
effect, cgmsim root upload → 503 with no effect (where the unselected reference gives 200 and a
write). **Read:** the effect on any tenant with wildcard roles; the open-decisions note item 1
recommends mapping the root carrier to **401 with no effect**.

**Options.**

- (a) **Clamp at next use, selected per tenant, after a preflight.** The option stays off by
  default; an operator (or, later, the owner) selects it per tenant; selection runs a preflight
  that lists every stored role or default that would refuse under the reader (wildcards,
  `readable`, root-carrier clients observed in that tenant's recent credentials) and refuses to
  select while any remains, so the first clamped operation can only ever be a 401/403, never a 503.
- (b) **Clamp at a sweep**: when the ceiling narrows, rewrite stored `tenant_authorization_roles`
  and `subject_roles` to the intersection.
- (c) **Never until reissued**: stored grants keep their meaning; only new proposals are bounded
  (today's unselected behaviour).
- (d) **Clamp at next use, selected universally** (the mode on for every tenant).

**Trade-offs by axis.**

| axis | (a) next use, per tenant, preflight | (b) sweep | (c) never | (d) universal |
|---|---|---|---|---|
| direction | the contract's rule, with activation gated as R63 asks | rewrites the owner's stored intent; the reader has no lineage to re-derive it from | contradicts owner-authority.md:55-56 | R63: "Universal selected-mode activation ... does not meet the user's no-unintended-client-impact condition" |
| architecture | the R62 mechanism, unchanged | a second writer that races the proposal transaction (`README.md:249-257` lock order) | n/a | the R62 mechanism |
| compat | per-tenant, so a root-carrier tenant stays unselected until its clients can carry subject tokens (open-decisions item 1(d)) | stored roles diverge from what the owner set; rollback impossible without a copy | full | breaks cgmsim-class clients |
| maintenance | one preflight query | sweep job, its audit, its retries | none | none |
| reliability | a refusal is deterministic per snapshot | partial sweep = inconsistent authority between rows | stale authority after narrowing | 503 storms from retrying clients (open-decisions item 1) |
| performance | one extra LEFT JOIN per snapshot (measured in R62's gate; not isolated) | bulk UPDATE under FOR SHARE contention | none | same as (a) |

**Who notices.** Owners of a selected tenant: a narrowing by the operator is felt by their uploaders
on the next request (401 for a subject whose grant was clamped to nothing, R63). Owners of an
unselected tenant: nothing. Operators: (a) gives them a per-tenant switch and a list of what blocks
it; (d) gives them a cohort-wide incident the first time a wildcard role exists. **Multitenant only.**

**Decided by the maintainer on 2026-11-06, overtaking this question's draft recommendation.** Open-decisions
item 1 is decided as a backward-compatibility rule: a tenant's api-secret keeps **200** on its own tenant
resource, and the subject-reader clamping mode (R62's optional `createOwnerReadPolicy` and its two reader
consumers) is **dropped**, because selecting it anywhere is a compatibility break ("we want backward compat
solutions"); a lane `claude/drop-reader-clamping-20261106` removes it, while the management-side
`createOwnerPolicy` and the proposed-grant catalogue (R53) stay. Against the options above that is **(c) for
stored grants**: new proposals are bounded by catalogue ∩ ceiling ∩ delegation at the management
transaction, and existing credentials keep working. The draft recommendation (a) is kept above as the
analysis record only. If per-subject clamping ever returns, it comes through Q5's lifecycle work in a shape
that keeps existing credentials working (reissuance the owner initiates, not a reader-side refusal), and
never as a 503 to an api-secret client. **Unmeasured:** nothing remains to measure for Q4 as decided;
the R62 and R63 captures stay historical evidence of the dropped mode.

### Q5. Ownership lifecycle

**Mechanism.** The contract (owner-authority.md:38-48): "Owner is an explicit tenant relationship,
separate from legacy data wildcards"; initial capabilities include "export and deletion requests";
"Operator provisioning, suspension, policy changes and execution of lifecycle deletion remain on the
private operator plane"; "Secret reveal is a separate permission with recent reauthentication.
Ownership transfer and adding co-owners are sensitive explicit operations; last-owner removal must
not orphan the tenant. Transactional transfer/recovery details require a bounded implementation
contract, not automatic operator access to owner secrets." The roadmap (`:648-652`): "an owner may
export or request deletion; the operator authorizes and executes lifecycle deletion. A deletion
request is not permission to bypass confirmation, retention or recovery policy." D7: the operator
plane is credential-free by unreachability. In code, the only owner-identity table is
`tenant_owner_actors(principal, consumer, active, can_update, delegable)` (migration 0004), read
`FOR SHARE` and never written by the application; the subject-admin audit records subject mutations
only; the platform authority spec §8 lists "who took an owner action and when" as not recorded.

**Measured.** R53's actor fencing (an inactive or non-matching actor refuses, 0 / 1 control); the
secrets component's `reveal` permission and audit (34-case suite). **Read:** everything else in this
question.

**A contradiction to resolve inside this question.** There are two owner-identity models and no
mapping between them: `tenant_owner_actors` keys an actor by `(principal, consumer)` (0004, built and
measured in R53), while the schema-config lab keys a person by `(provider, subject_id)` in
`tenant_access_grants` (schema spec Q10/Q18, maintainer notes 2026-10-29, "one access-grant contract,
two stores"). Q1's exchange produces a `(provider, subject)`; R53's policy consumes a `(principal,
consumer)`. The decision row for Q5 must say which table is the owner relationship of record and how
the other is derived; the recommendation below takes `tenant_access_grants` as the relationship and
`tenant_owner_actors` as its projection for the management writer.

**Options.**

- (a) **Owner-plane operations on the owner listener, operator execution on the operator plane,
  one transaction each, one audit shape.** Add co-owner = insert an access grant with the owner
  permission set, by an actor whose `delegable` covers it, with reauthentication ≤ 5 min. Transfer =
  two steps: the current owner records an invitation naming a `(provider, subject)`; the invitee's
  own verified session accepts it; the old owner's grant is kept until acceptance and removed in the
  accepting transaction. Remove owner (self or co-owner) = refused in the same transaction when the
  count of remaining active owner grants `FOR UPDATE` would be zero (last-owner invariant). Recovery
  when the only owner is locked out = an **operator-plane** command that writes a fresh owner
  invitation for a named `(provider, subject)` and records who ran it; it never reveals, decrypts or
  reads a secret (contract `:47-48`). Deletion = an owner writes a `tenant_lifecycle_requests` row
  (`requested`, with reauthentication); the operator plane moves it to `scheduled` after the
  retention window and `executed` by the export-then-delete tooling the Batch C lane is building;
  the owner may cancel until `scheduled`. Every step writes the same audit record shape on its plane.
- (b) **Operator-only ownership**: co-owner, transfer, removal and recovery all run on the operator
  plane by ticket; owners request them out of band.
- (c) **Owner-plane everything**, including deletion execution, with a confirmation step.
- (d) **Single owner per tenant**, no co-owners; transfer and recovery are operator-only.

**Trade-offs by axis.**

| axis | (a) split by plane, two-step transfer, last-owner invariant | (b) operator-only | (c) owner executes deletion | (d) single owner |
|---|---|---|---|---|
| direction | the contract and roadmap as written; D7 kept credential-free because the operator never touches a secret | contradicts "initial capabilities cover ... export and deletion requests" and co-owner as an owner operation | contradicts roadmap `:651` "the operator authorizes and executes" | contradicts contract `:46` "adding co-owners" |
| architecture | two writers (owner-plane management writer; operator CLI), one request table, one audit shape (schema spec "one audit approach") | one writer | the owner listener gains destructive authority over tenant data | simplest tables |
| compat | `single` unchanged (its owner is `API_SECRET`) | same | same | same |
| maintenance | invitations, request states, two audit writers to keep aligned | tickets and humans | one fewer plane | least |
| reliability | the last-owner check is a row count inside the mutation transaction, so no partial state | human latency | an owner mistake is irreversible without the operator's retention window | a locked-out single owner is always an operator incident |
| performance | n/a (rare operations) | n/a | n/a | n/a |

**Who notices.** Owners: (a) lets them add a family member, hand over a site, and ask for deletion
from the dashboard, with a fresh sign-in for each; (b) makes each a support request; (c) lets them
delete a site in one sitting; (d) means a lost phone is a support request. Operators: (a) gives them
two commands (`recover-owner`, `execute-deletion`) and a request queue to watch; (b) gives them every
request. **Multitenant only.**

**Values the maintainer must set.** Deletion retention window between `requested` and `scheduled`:
recommended **14 days**, basis: long enough for an owner who did not intend it to notice and cancel,
short enough that R62's populated restore lab (the only recovery instrument) bounds what must be
kept; **unmeasured**, and an operator policy may lengthen it. Invitation validity: recommended
**7 days**, basis: the invitation is a capability bound to a `(provider, subject)`, not a bearer
secret, so its window is a usability choice; **unmeasured**.

**Recommendation: (a).** Direction: it implements the contract's sentences one by one and keeps the
roadmap's audience split. Architecture: the request table and the two-step transfer are what make
"last-owner removal must not orphan the tenant" and "not automatic operator access to owner
secrets" both true at once. Compatibility: `single` untouched. Maintenance: one audit shape, which
the schema spec already asks for before Q5 is built. Reliability: every invariant is a transaction.
**Unmeasured:** all of it; the entry bar is in §3. The DELETE policy for *subjects* (R53's refusal)
follows from the same rule: in selected mode, a remove is authorised like an update to `roles: []`
(the actor must be active with `can_update`) and additionally refused while the subject is the
credential behind any active owner grant; outside that, R53's unselected remove is unchanged.

---

## 3. Entry bar: controls that must go red, and landing order

Every control follows the R48 / R53 / R62 shape: a positive on actual HTTP against owned PostgreSQL,
a break that removes one mechanism and must fail at the named assertion (setup failure is not red),
and a restoration. Predicted results are written before the run.

| question | positive (predicted green) | break-it control (predicted red, exact symptom) |
|---|---|---|
| Q1 provider adapter | an owner's provider session for tenant A exchanges on A's host for a management token with `tid = A`, `purpose = management`; the same session on B's host is 403 `not-a-member`; the A token on B is 401 `TOKEN_SIGNATURE` (the ORY proof's gate re-run against the real `ns-tenant-admin`, not the stand-in) | remove the membership check: B mints for A's owner (200 instead of 403); remove the subject-claim mapping: a token with no `sub` is accepted (200 instead of 401) |
| Q2 session | a refresh within 10 min returns a new token and a new refresh secret; the old secret presented after the grace window revokes the family and the next data or management operation on that session is 403; a session idle 31 min cannot refresh (401) while one idle 29 min can; absolute 12 h refuses regardless | remove rotation: the old secret still refreshes (200 instead of 401); remove the reuse-family revocation: a reused secret leaves the session active (next GET 200 instead of 403); remove the idle rule: the 31-minute session refreshes (200 instead of 401) |
| Q3 issuer | a management token is 401 `TOKEN_KEY` on the data socket and 200 on the owner socket; a data token is 401 on the owner socket; after `access_keys.active = false` on the old `kid`, a token signed under it is 401 on the next operation while a token under the new `kid` is 200; during the overlap both are 200 | remove the purpose check in `resolveKey`: the management token is 200 on the data socket; remove `keyActive` from the snapshot: the retired-key token stays 200 |
| Q4 clamping | **superseded by the 2026-11-06 decision** (reader clamping dropped; api-secret keeps 200): the remaining positive is the R53 shape, a proposal outside catalogue ∩ ceiling ∩ delegation refuses with no effect, and an existing api-secret upload on its own tenant is 200 and stored | remove one R53 fence: the over-ceiling proposal persists (R53's control, HTTP 200 versus 403 with persisted effects); the reader-side controls of R62/R63 are retired with the mode |
| Q5 lifecycle | add co-owner with a 4-minute-old authentication succeeds and with a 6-minute-old one is 403; transfer: the invitee accepts and the old grant is gone in the same transaction; removing the last active owner is 409 with no row change; `recover-owner` on the operator plane writes an invitation and no `reveal` audit row appears; a deletion request is `requested`, the owner can cancel, the operator's `execute-deletion` refuses before the window and succeeds after, and the export exists before the delete | remove the freshness check: the 6-minute case is 200; remove the `FOR UPDATE` count: two concurrent removals leave zero owners; execute deletion from the owner listener: must be 405/403, red if 200; remove the export-before-delete ordering: the delete proceeds with no export (red) |

**Landing order relative to Batch A and C** (batching plan §5; the open-decisions note item 2
recommends homing issuer and lifecycle under M6, which this order is consistent with either way):

1. **Q3 then Q2, in Batch A's tail, as T30-TENANT-ADMIN's composition.** They are the management
   listener's missing half: the issuer role and the session extension. They do not touch the data
   verifier and can run under the same full/browser/corpus campaign as A's freeze. Predicted: the R48
   7 new-format cases and R53's 22 stay green; the new controls above go red and restore.
2. **Q4 needs no lane**: decided 2026-11-06 as (c) with the reader mode removed by `claude/drop-reader-clamping-20261106`; its entry bar collapses to R53's existing control.
3. **Q1, its own lane gated on the compliance owner**, source-only until a provider adapter can be
   run against the real listener; it joins at a batch boundary and never with real identities.
4. **Q5, in Batch C beside the export/delete tooling lane** (`codex/tenant-export-delete-20261106`),
   because deletion execution is that lane's tool and the request table is this packet's. The
   operator commands land with the `admin` role that D21 names and the CLI does not yet run.

---

## 4. What this packet does not decide

- **Real identities, real traffic, real data.** D17 row 2's compliance-owner condition and its
  four edge conditions are untouched; every lifetime and every control above is for synthetic
  identities in owned containers.
- **Numeric bounds the maintainer has not set**: the refresh grace, concurrent-session cap, key
  rotation periods, deletion retention window and invitation validity are named with recommended
  defaults and a basis, and are UNMEASURED; the open-decisions note item 3 carries the general rule
  that thresholds come from a measurement designed to set them.
- **Which M2 bar holds.** Whether issuer, clamping and lifecycle are M2 or M6 criteria is the
  open-decisions note's item 2, not this packet's.
- **The provider list.** Only Kratos has been run; Clerk and others are read. The adapter
  interface is owed by D17 as amended and is not drafted here.
- **Owner UI.** The roadmap defers a first-party owner UI; every operation here is an API on
  `ns-tenant-admin`.
- **Single-tenant login.** The schema spec's maintainer note (2026-10-29) says `single` will need
  the same access-grant contract once a login plugin exists; that is "not yet designed; no plan row
  yet" and stays so.
- **The candidate `4cd95d06`** (owner/evaluator, in its own campaign): its two-listener run is
  reported in the open-decisions note and is not on the head this packet read.

**Contradictions found between documents and code, for the maintainer's attention.**

1. The platform authority spec AU1 still says tenant owners "are to authenticate through one
   cohort-wide Ory Kratos pool"; D17 as amended on 2026-10-27 makes the provider interchangeable.
   AU1's text predates the amendment.
2. owner-authority.md:27 names a "PostgreSQL session record and one-way verifier; rotation/reuse
   detection"; `access_sessions` on `83582e87` has no verifier, no refresh secret and no idle
   timestamp. The contract's idle lifetime cannot be enforced by a SELECT-only reader; Q2(a) places
   the write at the issuer.
3. Two owner-identity keys with no mapping: `tenant_owner_actors(principal, consumer)` (built, R53)
   and `tenant_access_grants(provider, subject_id)` (schema spec, decided 2026-10-29). Q5 names
   the resolution.
4. Execution plan §2.8 says the operator "mints a tenant's initial credential through `bin/admin.js`
   on the unroutable port"; on `83582e87` the CLI runs only the `api` role (`lib/cli/index.js:26-29`).
5. The queue's T30-RESEARCH note records reveal's "initial policy: an owner session; target:
   re-authentication"; the adopted contract (2026-11-05) is "within 5 minutes". The note is the
   older statement.

*Draft requiring maintainer review. Decisions taken go into decisions.md as rows; the queue,
dashboard and roadmap move only after a row exists.*
