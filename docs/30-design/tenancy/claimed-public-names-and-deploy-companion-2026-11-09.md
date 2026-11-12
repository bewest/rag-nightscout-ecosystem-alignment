# Claimed public names, the alias registry and the deploy companion: scope split and line of sight

*Contributor-facing decision-preparation note, 2026-11-09, **read-derived**. Anchors: alignment
`main` `9029fb6dd`; cgm-remote-monitor draft #8898 candidate `ed2ced00`; nightscout-roles-gateway
`90840ace`; nightscout-gateway-www `67cbe466`. No service was run for this note. It proposes a
scope split between cgm-remote-monitor, a sibling deployment repository and hoster-private
adapters, and an ordered path to a running staging rehearsal. The sibling repository exists as a local scaffold at `~/src/nightscout-deploy` (also reachable as
`externals/work/nightscout-deploy` in this workspace); it has no remote yet, so the GitHub links in its
README resolve only after the maintainer publishes it. Nothing here is adopted until it
is a row in [release decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md); the
[public-name contract](deployment-bindings-and-public-names.md) and the
[production critical path](production-critical-path.md) keep their canonical roles.*

## 1. The model to carry forward: a claimed public name

The roles gateway already separates the three things the public-name contract asks for, in a
schema that ran unmodified against current Kratos in the
[Ory proof §5](../../60-research/tenancy/ory-proof-2026-10-07.md#5-nightscout-roles-gateway-against-current-ory--probesnrg-portsh-measured).
Read at `90840ace`:

| roles-gateway concept (table / column) | what it is | tenancy vocabulary it maps to |
|---|---|---|
| `registered_sites.expected_name` (unique) | the host label a person **claims** and may publish | permanent public alias, owner-chosen |
| `registered_sites.upstream_origin` | where the edge sends an admitted request | private internal name (a resolution label in the shared cohort, not a URL) |
| `registered_sites.owner_ref` | the identity-provider subject who owns the claim | tenant owner, current OIDC subject |
| `reserved_expected_names`, `reserved_upstream_origin` | names nobody may claim, with a reason and source | project floor plus operator list |
| `nightscout_authenticity_records` | proof that the claimant controls the upstream, checked out of band | implied by provisioning in multitenant; needed only when fronting an independent site |
| `registered_sites.is_enabled`, `require_identities`, `exempt_matching_api_secret` | per-site policy switches | alias policy binding: anonymous allowed, human login required, native device credential path (D17) |
| `group_definitions`, `group_inclusion_specs`, `connection_policies`, `scheduled_policies`, `joined_groups` | who is in a group, what a group may do, when | the group/schedule policy the public-name contract defers to a bounded decision |
| warden route `GET/HEAD /warden/v1/active/backend/for/:expected_name` | one `auth_request` decision returning `x-upstream-origin` and an exchanged token | the edge decision point; in the cohort the decision moves inside the admitted application |

What the model adds beyond the gateway: a **stable tenant ID** that none of these tables has
(`expected_name` is the primary handle throughout), and an explicit **alias kind** with a lifetime.
Two kinds are enough for the first production scope:

- **claimed**: permanent, owner-chosen, checked against the reserved list, safe to publish; knowing
  it confers nothing, current policy decides.
- **ephemeral**: issued by the operator or by an operator's adapter, rotatable or expiring, bound to
  the same tenant; expiry changes reachability, never ownership, and the name carries no capability
  (the public-name contract already says so).

The public contract covers kinds, lifetimes, policy binding, versioned reassignment and cache
invalidation. **How an operator mints, distributes or brands ephemeral names is an adapter behind
that contract**, which is what keeps a hoster's own issuance scheme out of the public repositories
without leaving a hole in the model.

**Default names, built in** (direction given in discussion, 2026-11-09). Every tenant gets a
generated label at provisioning: DNS-safe, lowercase, fixed length, drawn from a CSPRNG, starting
with two letters so it is never confused with a number or an identifier, and checked against the
reserved list. The label is the tenant's internal resolution name and, under the deployment's
base domain, its default permanent primary alias. That is the whole built-in: a deployment with no
issuer and no owner claims still has one working, unguessable name per tenant. The precedent is
the per-site runner's own internal naming, which the maintainer found desirable in operation.

Everything beyond the default is policy a hoster supplies behind core's contract: an **alias
issuer** for ephemeral or additional stable names, and an **alias policy** that decides whether an
owner may claim or choose a name (pattern, length, reserved list, cooling-off on release). An
owner claim goes through the owner API under that policy; on rename the previous label stays as
a stable secondary alias until the owner releases it, so configured uploaders keep working; no timer is involved.

What does not carry forward, from what the port measured and what the tables hold:

- `registered_sites.api_secret` and `nightscout_secrets.api_secret` hold a site's root credential
  in clear, because the gateway verifies authenticity and brokers tokens with it. In the cohort the
  tenant's root lives in the secrets component, and [owner authority](owner-authority.md) treats
  legacy hashes as bearer credentials. The registry stores no credential.
- `upstream_origin` as a URL. A shared cohort has no per-tenant origin; resolution ends at a stable
  tenant ID inside the admitted application (D10, D13, D14).
- The runtime: restify on Node 24 fails at require, the lockfile needs `--legacy-peer-deps`, the
  per-site Hydra client path needs reconfiguration (Ory proof §5). The schema vocabulary, the
  decision chain's cases including its own cross-site denial, and the WWW journeys (what I own, why
  I have access, what I consent to, how I leave) are the inheritance. The code is reference, not a
  dependency.

## 2. Scope split: core, sibling repository, hoster-private

The rule: **core owns anything that defines authority or identity; the sibling owns anything that
varies by hoster or vendor; a hoster owns only adapters behind published interfaces.**

| concern | cgm-remote-monitor | sibling deploy repository (working name `nightscout-deploy`) | hoster-private |
|---|---|---|---|
| Private names: stable tenant ID and internal resolution name | **owns**: migration under the project's runner, operator API on the private plane | consumes snapshots | — |
| Public aliases: host, kind, lifetime, policy binding, reserved names | **owns the record and the decision**: the same migration, the operator API, and a read-only resolution endpoint on the private plane returning tenant ID, policy and a snapshot version | the `auth_request` **facade** that calls that endpoint and caches it, for edges that resolve before proxying; a reference issuer for ephemeral aliases | a replacement facade or issuer behind the same endpoint |
| Resolver | **owns** `lib/tenant-resolution`; adds a snapshot-source interface (the README already says "construct a new resolver to replace the mapping") | registry-backed snapshot source, cache, invalidation signal | — |
| Edge | **owns** the trust predicate contract (peer list) and the fast unknown-host refusal in the app | reference nginx, `auth_request` adapter for edges that need one, trust-record template, spoof/conflict/outage probes | TLS termination, DNS, certificates |
| Alias policy: anonymous vs human-required vs device path | **owns** the binding and the decision point on every exposed path | — | — |
| Group and schedule policy | **later**, after the bounded decision the public-name contract requires | later: the WWW journeys as an adapter over the headless owner API | — |
| Ephemeral alias issuance | the kind, lifetime and reassignment rules | a reference issuer for the Compose and Kubernetes bindings | a hoster's own issuer and distribution |
| Human identity | generic OIDC adapter, conformance cases | provider configuration profiles (Authentik reference, Kratos fallback); **no login UI** | the provider deployment |
| Owner self-service | one thin page over the headless owner API | — | branding, support links |
| Operator lifecycle | headless operator API and lifecycle library (exists at `ed2ced00`) | CLI, console (read-mostly first), runbooks | billing, ticketing |
| Secrets | component contract and the Vault Transit reference provider | cloud key-service providers, service-login adapters, conformance kit | key custody |
| Deployment | the deployment-plan **schema** and the role table | plan renderer; Compose, Kubernetes and DIY single-tenant bindings; `targets` registry with owner and expiry per vendor | derived image with installed providers |
| Observability | readiness and admission endpoints shaped for fleet polling | Grafana mixin, alert rules, runbook skeletons | paging |

Why the alias record is core even though an edge may resolve it first (answered in discussion with
the maintainer, 2026-11-09): the application must refuse an unknown host and apply the alias policy on
every exposed path, sockets included, so it needs the alias record inside its own authority. The
resolver already accepts `X-Resolved-Tenant` only as a consistency check against its own map. An
edge that resolves is therefore a cache in front of core's record, and the sibling ships the demo
facade for it; a hoster can swap the facade without touching authority. Deployments with a plain
edge (Compose, DIY) use the same record in `direct-alias` mode and need no facade.

Two placement rules from operating experience, stated as mechanisms:

1. **Config names a registered provider; it never names a module path.** A module path in config is
   code execution for anyone who can write config and it hides the supply chain from the image
   digest. Providers are installed at image build and registered by name; core refuses unknown names.
2. **The trusted-peer predicate is configuration, not a provider.** It is the one place where a
   wrong adapter silently widens trust.

## 3. Line of sight to a staging rehearsal

Waves show dependency, not dates. Each wave names the gate that ends it. "Rehearsal" means a
synthetic export of a few tenants loaded into the Compose binding on a clean host, served through
a TLS edge with a written trust record, and restored once, with nothing real in it.

| wave | core | sibling | gate |
|---|---|---|---|
| 0 (in flight) | ed2 one-host reference accepted; shared OIDC/owner source accepted natively; Vault service login behind the existing seam | — | [M6 acceptance families](multitenant-delivery-roadmap.md#m5m6-acceptance-families) for identity and secrets |
| 1 | registry migration, operator API, snapshot export; resolver snapshot source; unknown-host refusal before tenant context; reserved-name floor | repository created; plan schema extracted from `deploy/multitenant/config.js`; resolver and secrets conformance kits with red controls | registry CRUD plus alias rename, reassignment and revocation measured on PostgreSQL; a stale snapshot refuses, a fresh one serves |
| 2 | full Mongo→PostgreSQL loader for the admitted collections (CAP-02); operator CLI verbs over the headless API | Compose binding consumes `deploy/multitenant` at a pinned commit; edge reference with probes; trust-record template; `targets` registry empty but checked | loader round-trip on synthetic exports with populated identity and order fidelity; CLI provision/suspend/export/delete/bind-alias against the Compose binding |
| 3 | — | **staging rehearsal** on Compose: TLS edge, provider over HTTPS, Vault service login, backup and restore of the assembled tree, upgrade and rollback | the [deployment admission](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#deployment-admission-probes-and-trust-record) probes pass against the live edge and Vault; one restore rehearsed |
| 4 | thin owner page | Kubernetes binding (one Pod per cohort, private socket volume, no-overlap update); console read-mostly; first two DIY single-tenant targets with expiry dates | binding equivalence table in the [public-name contract](deployment-bindings-and-public-names.md#what-a-kubernetes-binding-must-preserve) |
| 5 | group/schedule policy after its decision packet | WWW journeys over the owner API; connector sync tooling; observability mixin | policy evidence list in the public-name contract |

Priority between the three columns: core first where it defines authority (waves 1 and 2 are
mostly core), the sibling where it lowers the cost of running a deployment (waves 3 and 4), and
hoster-private work only as adapters once the interface they sit behind exists.

## 4. Questions for the maintainer, one topic each

Items marked *answered in discussion* were settled with the maintainer on 2026-11-09 and await
their row in release decisions; the rest are open.

1. **Where `deploy/multitenant` lives during 16.0.0.** *Answered in discussion*: re-running
   acceptance to move a directory is process drag, so the move is not gated on it. Move the tree
   into the sibling now with its history (`git subtree split`), record the source commit, and make
   the sibling's check a byte-identity comparison of the moved tree against that pinned core
   commit plus the existing `demo.sh` smoke. Core keeps a one-paragraph pointer. The ed2 evidence
   keeps its attribution because the files it cites are unchanged, only relocated.
2. **Registry authority.** *Answered in discussion*: private names are core schema. Public aliases
   are also a core record with a read-only private resolution endpoint; the sibling ships the
   `auth_request` facade over it and a hoster may replace the facade. Mechanism in §2.
3. **Default alias kind and label length.** *Answered in discussion*: a simple built-in default (§1).
   The generated label's length is provisional at 10 characters (two letters plus eight from a
   32-symbol lowercase alphabet, about 40 bits) and is **to be measured** against collision at the
   intended tenant counts and against typing and reading comfort before it is fixed. Uploaders, followers and controllers are configured with one hostname
   and do not rotate it, so a tenant needs exactly one **permanent primary alias**. Whether that
   name is owner-chosen or operator-generated (unguessable) is a separate axis from its lifetime.
   Ephemeral aliases are additive and never the only alias; reassignment inherits nothing.
   Recommendation: default one permanent primary alias per tenant, generated unless claimed;
   ephemeral aliases opt-in per tenant under operator policy.
4. **Reserved names as a project floor.** A built-in list (well-known, api, admin, www and the
   like) plus an operator list, in the D22 style. Recommendation: yes.
5. **Roles gateway reuse.** Port or re-implement. Recommendation: re-implement the decision chain
   over core's resolver and current authority, carry the schema vocabulary and the gateway's test
   cases, credit the design; the measured port cost is the runtime and dependency graph.
6. **Strong identity for single and multitenant, and the gateway's disposition.** *Direction
   given in discussion*: both profiles should have strong human identity, and uploaders may move
   toward zero trust over the long term. The adopted generic OIDC adapter already runs in `single`
   under `ENABLE=oidc`, so fronting an independent site with an external gateway is not needed for
   human identity; the gateway is archived as reference once the decision chain and the group and
   schedule vocabulary are carried into core. For uploaders, D17's permanent native credential
   path stays; a later contract can add per-device enrolment through the owner API, with
   short-lived or attested device tokens and the legacy secret as the compatibility path. That is
   a core identity contract; the sibling would hold enrolment tooling only. No change to D17 is
   proposed here.
7. **Retiring sole maintenance of the roles gateway while OIDC lands in both profiles.**
   Feasible, and the order matters more than the effort. Conditions: (i) the gateway serves no
   production users; the maintainer's operator reports a staging-only deployment; (ii) the generic
   OIDC adapter is accepted natively in `single` and multitenant, which is wave 0; (iii) a minimal
   membership record exists in core, a person bound to a tenant with a role and revocable on the
   next operation, so the question the gateway answered, who may act on this site, has a home.
   The identity plan (MT-IDENTITY-PLAN) already names tenant access grants. Groups and schedules
   stay deferred to their bounded decision; nothing in retirement depends on them. Steps: archive
   the repository with a pointer to the alignment note, keep its test cases as the source of the
   resolver and OIDC conformance kits, and port the WWW journeys later as a sibling adapter over
   the owner API. For `single`, *answered in discussion*: an OIDC subject becomes a Nightscout subject by
   explicit binding by the site admin, with an invitation flow later; no auto-provisioning on
   first login. In addition, when OIDC is enabled an environment variable may name the one
   subject that binds to the site's admin at boot, so a fresh site can be claimed without a
   console; the mechanism and its refusal rules (unset, malformed, already bound) need a small
   decision row of their own.
8. **Repository home and licence** for the sibling. *Answered in discussion*: the nightscout
   organisation, as `nightscout-deploy`. Licence recommendation: **AGPL-3.0-only**, matching
   cgm-remote-monitor and nightscout-connect and required anyway by the imported Compose tree,
   with the provider and plan interface contracts published as a small separate **MIT** package
   (the roles gateway's licence) so a hosting operator's private providers are not derivative
   works. The workspace lockfile carries the intended URL; bootstrap reports a failed clone until
   the repository is published, and the local scaffold stands in meanwhile.

*Draft for maintainer review. Decisions taken go into decisions.md as rows; the queue and the
public-name contract move only after the row exists.*
