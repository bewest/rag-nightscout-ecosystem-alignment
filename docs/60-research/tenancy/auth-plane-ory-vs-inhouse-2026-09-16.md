# The auth plane: Ory Kratos/Hydra against building it ourselves

**Status: RESEARCH, for maintainer decision.** Nothing here is landed work and nothing here
proposes code yet. It exists to answer two questions asked on 2026-09-16 — whether planning on
three separate interfaces is the reversible choice, and whether to lean on Ory rather than build
OAuth2 and IAM controllers ourselves.

**Audience: contributors.** Technical throughout. The operator- and user-facing consequences —
what a tenant owner is asked to do to log in, what a self-hoster must be told changes for them
(nothing, and that is load-bearing) — are named in §7 and are separate work.

| | |
|---|---|
| Measured against | `externals/nightscout-roles-gateway` @ `90840ac`, `externals/nocturne` @ `d9e143097`, `externals/work/crm-seam` @ `81a1f6ce` |
| Decisions it touches | D1, D4, D5, D7, **D13, D14, D15** |
| Decisions it proposes | D16 (three interfaces), D17 (auth split by audience) |
| Web claims | dated 2026-09-16, **not reproduced locally**; see §2 and §8 |

---

## 0. The short version

1. **We have already built the Ory integration once.** `nightscout-roles-gateway` is a working
   Kratos + Hydra + Nightscout RBAC gateway in this very ecosystem. It is not a proposal; it has
   31 migrations, a decision pipeline and six hundred lines of token-management documentation.
   Any build-versus-buy argument that ignores it is starting three years late.
2. **Ory is deployed once for the whole cohort, not once per Nightscout tenant** (maintainer,
   2026-09-16). That is the same shape NRG shipped: **one cohort-wide identity pool, one OAuth
   client per site, tenancy carried in our own tables.** Ory answers "who is this person";
   Nightscout answers "what may they do here".
3. **Which means Ory's missing multi-tenancy never applies to us.** Kratos and Hydra OSS are
   single-tenant and Ory's answer for multi-tenancy is Ory Network or an Enterprise License — but
   we are not asking Ory to model our tenants. The constraint is real and it rules out a design
   nobody wanted; it does not constrain this one. §2 is therefore a *confirmation*, not an
   obstacle.
4. **That splits D13 in two.** "No cohort-wide AUTH" is true of *credentials* and false of
   *identity* under any Ory design. Worth deciding deliberately rather than discovering.
5. **Three interfaces is the reversible choice**, with one prerequisite that has to come first.

---

## 1. The prior art is ours

`externals/nightscout-roles-gateway` — "a cloud native oauth 2.0 rbac controller for Nightscout".
Measured, not summarised from its README:

| what | where |
|---|---|
| Kratos SDK, session resolution | `lib/privy/index.js:20` (`V0alpha2Api`), `:258` `kratos_whoami` → `sdk.toSession(undefined, req.header('Cookie'))` at `:260` |
| Hydra admin SDK, client minting | `lib/clients/index.js:3`, `createOAuth2Client` at `:71`, `deleteOAuth2Client` at `:94` |
| service endpoints | `env.js:7-11` — `KRATOS_API` :4433, `HYDRA_API` :4445 |
| the decision pipeline | `lib/routes.js:327` — one express chain: resolve site → Kratos whoami → ACL by identity → token exchange → policy → API-secret check → decision → upstream header |
| token exchange | `lib/exchanged.js` — `GET /api/v2/authorization/request/<policy_spec>` against the site (`:29`), cached in Keyv, TTL from the token's own `exp - iat`, namespace `gateway-nightscout-token-cache` (`:15-16`) |
| site authenticity | `lib/tokens/index.js` — `SHA1(api_secret)` as the `API-SECRET` header, then `GET /api/v2/authorization/subjects` |
| schema | 31 migrations, 2022-04-30 → 2022-06-12, including `20220529163520_add_oauth2_credentials.js` |

### 1.1 The pattern, which is the finding

NRG does **not** run a Kratos per tenant. It runs:

- **one Kratos identity pool for the whole cohort** — a person has one login across every
  Nightscout site they can reach;
- **one Hydra OAuth client per registered site** — created at site registration, recorded locally
  as a map from `owner_ref` + `expected_name` → `client_id`;
- **tenancy in its own tables** — `registered_sites`, `group_definitions`,
  `group_inclusion_specs`, `connection_policies`, `scheduled_policies`, `joined_groups`.

`joined_groups.subject` is the Kratos identity id. That column is the entire seam between the
identity system and the authorization system, and it is the design's whole trick: **Ory owns
identity, we own authorization.**

### 1.2 Three access modes, and the third one is the one we cannot avoid

| mode | condition | status in NRG |
|---|---|---|
| A · anonymous | public vanity URL, Nightscout's own auth underneath | fully functional |
| B · identity-mapped | Kratos login, consent recorded, group policy, weekly schedule | works for allow/deny |
| C · API secret | `exempt_matching_api_secret` lets a matching secret bypass login entirely | fully functional |

Mode C exists for "uploader devices and legacy apps". **Any auth design we adopt needs a mode C**,
because a CGM uploader is not going to run an OAuth flow, and D1 says the self-hosted deployment
keeps working unchanged forever.

### 1.3 What was never finished

`docs/ROADMAP.md`, read in full: the `nsjwt` policy type — **the token exchange that turns an Ory
identity into a Nightscout JWT** — is *partially* implemented. The decision logic checks for it;
the upstream exchange is not fully wired. Rate limiting is absent. Only `email` and `anonymous`
identity types exist of the four the schema declares.

So the half that is finished is the half Ory gave us, and the half that is unfinished is the half
that is ours to write either way. That is the single most useful fact in this document.

### 1.4 It is stale

`@ory/kratos-client ^0.9.0-alpha.3` and `@ory/hydra-client ^1.11.8` are 2022-era. Hydra is now 2.x
and Kratos 1.x; `V0alpha2Api` no longer exists under that name. Reviving NRG is a port, not a
checkout.

---

## 2. What self-hosted Ory actually gives us, as of 2026-09-16

**Not reproduced locally — read from Ory's documentation and issue tracker on 2026-09-16.**

- **Kratos OSS does not support multi-tenancy.** Ory's own multi-tenancy guide recommends *one
  Kratos instance per tenant (domain)*. Issue [#3129] ("Add support of multiple tenants") and
  discussions [#2403], [#407] are open and long-running; Ory's 2026 community survey reports
  multi-tenancy as the single most-requested capability.
- **Hydra OSS is the same.** Per-tenant issuers and per-tenant signing keys require *multiple
  deployments*. There is no per-client issuer configuration in the OSS server.
- Kratos has an internal `network_id` scoping mechanism, but it is the substrate for **Ory
  Network**, not a supported OSS feature.
- **Multi-tenancy is the paid boundary**: Ory Network (managed) or the Ory Enterprise License.
  The OSS code is Apache-2.0 and self-hostable at no cost — single-tenant.

### 2.1 Why none of that binds the design we want

**The deployment is one Kratos and one Hydra for the whole cohort** — unified auth *for* Nightscout
tenants, not a Kratos tenant *per* Nightscout tenant. Under that shape every limitation above is
out of scope: we never ask Kratos to isolate tenants, because Kratos is not where our tenants live.

It is still worth having measured, for two reasons. First, it closes off the alternative
permanently: "give each tenant its own Kratos" is not a design we can fall back to later at this
scale, so the shared-pool decision is effectively irreversible once identities exist. Second, it
means **we never need Ory Network or an Enterprise License** — the Apache-2.0 self-hosted OSS
servers are sufficient for what we are asking of them, which keeps a commercial dependency and a
third-party data processor out of the path between a person and their glucose data.

D1 is bulk NS-as-a-service. "One Kratos per tenant" would be a per-tenant process, database schema
and TLS certificate — not a deployment model at that scale. Nobody proposed it; this section
records why it stays unproposed.

---

## 3. Where this collides with decisions already made

### 3.1 D13 is about credentials, not about identity — and the distinction has never been written down

**This is the consequence of the one-deployment decision, and it is the one to take seriously.**

D13 says: **no deployment-wide secret in `TENANCY_MODE=multi`, on any interface.** Under a single
cohort-wide Kratos that stays true — there is still no shared *secret*, and each tenant still holds
its own root credential. But the **authentication plane is shared infrastructure by construction**:
one identity, one session, one login, spanning every tenant in the cohort. That is not an accident
of the implementation; it is what "unified auth for Nightscout tenants" means.

It is also a feature, and NRG names the use case: a mobile app can log in once and *select* which
Nightscout it may reach — "no more copy/paste strings". You cannot have that and per-tenant
identity silos at the same time.

That is not a violation of D13. It is a fact D13 does not address, and reading D13 as "nothing is
cohort-wide" would rule out the only workable Ory topology. **The honest statement is: credentials
are per-tenant; identity is per-cohort; authorization is per-tenant.** Isolation then rests on the
authorization layer and on RLS, not on the authn layer.

This wants to be decided out loud, because the failure mode is a cross-tenant identity bug, and
"we assumed the authn plane was isolated" is how that ships.

### 3.2 D14 and Hydra cannot both mint the token

D14 is a **per-tenant JWT signing key**, chosen so cross-tenant token reuse fails as a *signature*
error rather than a claim check. Hydra signs with Hydra's keys and OSS Hydra has one issuer. So
either:

- Hydra issues tokens and D14 is abandoned for the human path; or
- Hydra authenticates and **Nightscout mints its own per-tenant token afterwards** — which is
  precisely NRG's `nsjwt` exchange, the part that was never finished.

The second keeps D14 intact. It is also more work, and the work is ours.

### 3.3 D1 and D4 make this permanent, exactly like the storage seam

A self-hoster must never be required to run Kratos. So Ory can only ever be a **hosted-only**
path, and the native credential path stays first-class forever — the same shape D4 already forced
on storage, where MongoDB is permanent for single-tenant and the seam carries two mature backends
for good. **Adopting Ory means the auth seam carries two backends forever too.** That is the real
cost, and it is not a migration cost; it is a standing maintenance cost. It should be counted
against "so we don't need to build sensitive oauth and iam controllers", because we will still be
maintaining the native one.

### 3.4 D7 against Nocturne

Nocturne puts platform admin on the consumer API behind a role:
`Controllers/V4/PlatformAdmin/TenantController.cs:28-29` — `[Route("api/v4/admin/tenants")]`,
`[Authorize(Roles = "platform_admin")]`. Its tenant-owner surface is
`Controllers/V4/Identity/TenantSettingsController.cs` — `[Route("api/v4/tenant-settings")]`,
`[Authorize]`, plus a `HasScope(Scope.TenantSettings)` check, tenant from the Host header.

**Nocturne uses no Ory at all** — no Kratos, no Hydra anywhere in the tree. It built identity
in-house: `PasskeyCredentialEntity`, `TotpCredentialEntity`, `SubjectOidcIdentityEntity`, and a
per-tenant `OidcProviderAdminController` for federation. So "ORY-style" in D7 describes a
philosophy we adopted, not a dependency either sibling project carries.

Nocturne's settings storage is worth copying regardless of the auth outcome: a `settings` table
keyed `tenant_id` + `key` with a JSON `value`, plus typed side-tables where constraints matter
(`TenantAlertSettingsEntity`, `TenantDataRetentionConfigEntity`). That is the shape of "the
data/schema mirrors the flags typically set via environment variables".

---

## 4. Three interfaces: yes, and one thing has to happen first

**The reversibility argument holds.** Merging two listeners into one later is a routing change.
Splitting one listener into two later means re-deriving which routes were ever safe to expose,
against a codebase where by then something will depend on them sharing a process. Separation also
decouples the auth decision from the data path: a separate listener can be fronted by Ory, by a
native credential, or by nothing-but-unreachability without touching the consumer API. Punting the
auth story behind a port boundary is a legitimate use of a boundary.

**The prerequisite.** Tenant resolution and credential verification would otherwise be implemented
twice. They must be extracted into one module *before* the third listener exists — `lib/server/
tenant-resolver.js` and `tenant-middleware.js` already are that module for the consumer path, and
the admin plane deliberately does not use them because it is cross-tenant. The tenant-owner plane
is the first surface that is **per-tenant and not the data path**, so it is the first real consumer
of that extraction.

| listener | audience | authn | authz | tenancy |
|---|---|---|---|---|
| `ns-api` (+ `single`) | devices, clients, viewers | native per-tenant credential, tokens | shiro | Host → slug → id, RLS |
| `ns-tenant-admin` | the tenant owner | **the open question** | owner role | Host → slug → id, RLS |
| `ns-admin` | the hoster | none, by D7 | none — reachability | cross-tenant by construction |

---

## 5. Recommendation

**Split the auth question by audience rather than by build-versus-buy.** The reason the question
feels hard is that it is three questions wearing one coat.

| audience | recommendation | why |
|---|---|---|
| **devices and uploaders** | native per-tenant credential. Never Ory. | D1. An uploader cannot run an OAuth flow, and NRG needed mode C for exactly this. Non-negotiable. |
| **tenant owners and caregivers** | **Ory Kratos, one cohort-wide pool, hosted-only** | This is the sensitive, high-volume, easy-to-get-wrong part — recovery, MFA, passkeys, session management — and it is precisely what Kratos is. It is also what NRG already integrated. |
| **third-party apps** | Hydra, **later, and only if we want delegated access** | Nothing today needs it. Deferring it costs nothing; adopting it now buys a second service to operate before anyone has asked for consented third-party access. |
| **platform operator** | D7 unchanged | It is built, it is argued, and it is the one surface where having no credential is strictly stronger than having one. |

**The bridge is `nsjwt`, and it is ours either way.** Kratos says who the person is; a policy says
what they may do on this site; Nightscout mints a per-tenant token (D14) that the data path already
understands. That is NRG's design, it keeps D14 intact, and its unfinished half is the half no
vendor was ever going to write for us.

**What "lean on Ory" actually buys**, stated plainly so it can be argued with: we do not write
password hashing, credential recovery, MFA enrolment, session invalidation, or the OIDC federation
handshake. **What it does not buy**: multi-tenancy (§2), the authorization model, the token
exchange, the device path, or freedom from maintaining the native path anyway (§3.3).

---

## 6. Proposed decisions

- **D16 — three interfaces, three listeners.** Consumer/data, tenant-owner config, platform
  operator. Adopted *because* the auth story is unsettled: the boundary is what makes it
  changeable later. Prerequisite: tenant resolution and credential verification extracted to one
  module before the third listener is built.
- **D17 — the auth plane splits by audience.** Native per-tenant credentials for devices and the
  data path, permanently. Ory Kratos for human identity on hosted deployments only, as one
  cohort-wide pool with tenancy in our tables. Hydra deferred. D7 unchanged. D14 preserved by
  minting the Nightscout token ourselves after Kratos authenticates.

Neither is adopted. Both need the maintainer's yes.

---

## 7. What this implies that is not in this document

1. The operator-facing text: what a tenant owner does to sign in, and the explicit statement that
   a self-hoster's login does not change. §3.3 is the reason that statement can be made.
2. The tenant-owner config API's actual route list and schema — that is T30-SCHEMA, and
   `tenant-owner-config-surface-2026-09-15.md` §A already proposes DDL for it.
3. A migration story for NRG's tables if we adopt its model rather than its code.
4. Whether `joined_groups`-style consent recording is in scope for a first hosted release. NRG
   treats it as a feature of the product, not of the auth layer, and the argument is good.

## 8. What this document does not establish

- **Every Ory claim in §2 is read, not run.** No Kratos or Hydra instance was started. The
  programme's own rule — read-derived claims are a hypothesis until executed — applies in full,
  and the register records five entries that did not survive contact with running code. The
  cheapest way to discharge it: stand up Kratos 1.x + Hydra 2.x against two tenants and try to
  make one pool serve both.
- **No cost model.** Ory Network pricing, and the compliance question of a third-party data
  processor adjacent to health data, are not analysed here at all.
- **NRG was not executed.** Its dependencies are 2022-era and it was read, not run. Whether its
  pipeline still works against Kratos 1.x is unknown and is the first thing a port would measure.
- **No measurement of what a shared identity pool costs in isolation risk.** §3.1 names the
  hazard; nothing here bounds it.
