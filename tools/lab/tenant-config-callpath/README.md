# Tenant-configuration call-path lab

*Contributor-facing. Lab approved by the maintainer on 2026-10-27 to inform the open question in
[execution plan §2.13](../../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)
(D22, "Not decided"): how does a hosted owner dashboard reach the tenant-owner listener? The lab
informs that decision. It does not make it. Synthetic tenants, owners and credentials only.*

Marks: **[M]** means the lab measured it, in the run recorded in `results.json`. **[R]** means it
is reasoned from the code or the design documents and was not measured.

## What it compares

A *tenant* is one Nightscout site on a shared host. Its *owner* is the person whose site it is.
The *operator* runs the host.

| design | how an owner's edit travels |
|---|---|
| **A**, owner token end to end | The dashboard logs the owner in at the identity provider, then trades that login for an *owner token*: a short-lived token signed with that tenant's own key (D14). Nightscout mints it after checking the login (D17). The dashboard sends the edit straight to the tenant-owner listener (`ns-tenant-admin`, D16) with that token. |
| **B0**, trusted orchestrator, no identity | The dashboard forwards the owner's login to an internal *orchestrator*. The orchestrator checks ownership itself, then writes the tenant's configuration through an internal API. Internal calls carry no identity and name the site in the URL. |
| **B1**, trusted orchestrator, service tokens | As B0, but every internal call carries a *service token* (a credential that names a component, not a person): dashboard to orchestrator, operator console to orchestrator, orchestrator to listener and to the secrets service. |
| **C**, split by audience | Owner edits travel as in A. Provisioning and suspension go through an orchestrator that lives only on the operator plane (D7) and that the dashboard cannot reach. |

## What runs

Six Node processes per deployment, plain `http`, each bound to 127.0.0.1. Ports 47410 to 47418
were free when the lab was built (checked with `ss -ltn`).

| process | port(s) | role |
|---|---|---|
| `roles/idp.js` | 47410 | identity provider stub: password in, signed assertion naming the human out |
| `roles/dashboard.js` | 47411 | owner dashboard backend |
| `roles/tenant-admin.js` | 47412 public, 47413 internal | `ns-tenant-admin`: token exchange, owner API (A, C), service API (B); policy and floors |
| `roles/ns-admin.js` | 47414 | platform operator plane (D7): no credential; tenants, suspension, operator policy |
| `roles/orchestrator.js` | 47415 | B: owner and operator routes. C: operator routes only. Not started in A |
| `roles/secrets.js` | 47416 public, 47417 internal, 47418 operator | secrets: AES-256-GCM at rest, consume, logged reveal; the operator port provisions and never reveals |

`lib/policy.js` implements D22 over seven census names: `AUTH_DEFAULT_ROLES` (bounded list),
`WRITE_VALIDATION` (floor `log`, owner may tighten), `CONNECT_SOURCE_ENDPOINT` (driver host
allow-list), `API3_AUTOPRUNE_ENTRIES` (bounded 30 to 3650 days, confirmation and export offer),
`DISPLAY_UNITS` (open), `TRUST_PROXY` (pinned) and `DEBUG_LOGGING` (pinned to its floor).
Effective value: code default, then operator default, then owner value if the mode and constraint
allow it, then operator pin.

### Network separation is a model, not isolation

Every listener is on 127.0.0.1, so any local process *could* reach any port. The lab encodes the
intended network as a reachability matrix (`lib/net.js`). It is enforced twice: the client refuses
to dial a port its zone may not reach, and each server refuses a request whose declared zone may
not reach it. The attack harness declares its zone truthfully. The `open-matrix` control shows the
matrix is doing the work.

## How to run

```sh
node harness.js --scratch /some/dir/outside/the/repo   # about 2 minutes; writes results.json
node harness.js --scratch DIR --only A,C                # a subset
```

Each run makes throwaway keys under `DIR/runs/<n>-<design>-<label>/keys`, starts every process with
`setsid nohup`, records the PIDs, and stops them by those PIDs only. Each measured run checks that
every process is alive, owns its ports and answers its health check, at the start and at the end.
The harness refuses a scratch directory inside the git tree. `results.json` holds no key, token,
password or revealed value.

## The five measures

1. **Blast radius.** For each compromised component, which tenants can be read, written (owner
   value), changed by operator action (a pin), or have their connector credential revealed. The
   attacker acts from that component's network position and from the internet, with exactly the
   credentials it holds. Success is judged against the store and the stored secret, not by the
   response code.
2. **Audit.** What the log records for an owner's edit, an attacker's edit, and an operator edit.
3. **Policy.** Where the policy and floors are enforced, and whether a crafted request gets round
   them.
4. **Cross-tenant confusion.** Whether tenant 1's owner can change tenant 2, and what stops it.
5. **Effort.** Calls and credentials per edit, and what the owner sees.

Every check has a **control**: the same deployment with one protection removed. A control
*reports* when the check it targets changes. All 33 controls reported, and the liveness check
failed when one process was killed by its PID [M].

## Results

### 1. Blast radius [M]

Cells: tenants affected, as read / write / operator action / reveal. "all" is t1, t2 and t3.
Only owner-1 had a live dashboard session during the compromise.

| compromised | A | B0 | B1 | C |
|---|---|---|---|---|
| dashboard backend | t1 / t1 / none / t1 | t1 / t1 / **all** / t1 | t1 / t1 / none / t1 | t1 / t1 / none / t1 |
| orchestrator | (none exists) | **all / all / all / all** | **all / all / all / all** | all / none / all / none |
| tenant 1's owner credential | t1 / t1 / none / t1 | t1 / t1 / none / t1 | t1 / t1 / none / t1 | t1 / t1 / none / t1 |
| secrets API caller | all / all / none / all | all / all / all / all | all / all / all / all | all / all / none / all |
| operator plane | all / none / all / none | all / none / all / none | all / none / all / none | all / none / all / none |
| identity provider | all / all / none / all | all / all / none / all | all / all / none / all | all / all / none / all |

- *Tenant 1's owner credential* is the per-tenant owner token in A and C. B issues nothing
  tenant-scoped, so the owner's identity-provider assertion stands in.
- *Secrets API caller* is the non-human credential the secrets service accepts for other people's
  secrets. In A and C that is the tenant-owner listener's credential for fetching signing keys:
  with every tenant's key, an attacker mints owner tokens for every tenant. In B0 and B1 it is the
  orchestrator (B0: its network position; B1: its service token).
- B0's dashboard reaches every tenant through the orchestrator's operator routes, which take no
  identity.
- The operator plane can pin any setting for any tenant within the floors, and reveals nothing.

Controls: `no-sig-verify` (A, C) took the dashboard and owner-credential writes from t1 to all
tenants. `no-ownership-check` (B0, B1) did the same for B. `open-matrix` gave A's and C's dashboard
operator action on all tenants. In B0 it let the dashboard write and reveal for all tenants
through the internal APIs, which take no identity. In B1 it gave operator action on all tenants
(by reaching `ns-admin` directly), but the internal APIs still refused writes and reveals without
the orchestrator's token. `b1-no-service-token` gave B1's
dashboard operator action on all tenants, as in B0. `operator-reveal` let the operator plane reveal
all tenants' secrets. `reveal-no-auth` (A, C) let tenant 1's token reveal every tenant's secret.

### 2. Audit [M]

| edit | A, C | B0 | B1 |
|---|---|---|---|
| owner's edit | names owner-1, verified by the tenant key's signature | no identity; owner-1 only as the orchestrator asserts it | the orchestrator, plus owner-1 as it asserts |
| attacker's edit | stolen t1 token, body claims `owner-9`: log names owner-1, verified. It names the credential's owner, so theft looks like the owner | compromised orchestrator writes t2 naming owner-2: no identity, plus a human the attacker chose | the orchestrator, plus a human the attacker chose |
| operator edit | the operator plane, no identity (all designs; D7 has no credential) | same | same |

Control: `actor-from-body` (A, C) made the listener take the name from the request body; the
attacker's edit was then logged as `owner-9`.

### 3. Policy [M]

Policy and floors are enforced in `ns-tenant-admin` for every owner write, in all four designs.
Floors are enforced again in `ns-admin` for every operator policy write. The dashboard's own check
(hidden keys) is a convenience; every crafted request below skipped it.

| attempt | A | B0 | B1 | C |
|---|---|---|---|---|
| pinned `TRUST_PROXY` through the dashboard | refused, dashboard | refused, dashboard | refused, dashboard | refused, dashboard |
| same, crafted request skipping the dashboard | refused, `pinned` | refused, `pinned` | refused, `pinned` | refused, `pinned` |
| owner floors: `WRITE_VALIDATION=off`, anonymous-write role, link-local connector host | refused, floor | refused, floor | refused, floor | refused, floor |
| owner outside the operator's bound (`status-only`; autoprune 7 days) | refused, constraint | same | same | same |
| autoprune 90 days without, then with, the confirmation phrase | 409, then accepted | same | same | same |
| open and tightening edits (`DISPLAY_UNITS`, `WRITE_VALIDATION=reject`) | accepted | accepted | accepted | accepted |
| re-pin `TRUST_PROXY` from the dashboard's network position | unreachable | **accepted** | refused, caller token | unreachable |
| operator plane pins an anonymous-write role, a link-local host, `WRITE_VALIDATION=off` | refused, floor | same | same | same |

Controls: `no-policy` let the crafted pinned write and the out-of-bound writes through.
`no-floors` let the owner and operator floor breaches through. `no-confirmation` let autoprune
through without the phrase. `open-matrix` and `b1-no-service-token` let the dashboard re-pin.

Also measured: dev's code defaults break two floors. `WRITE_VALIDATION` defaults to `off`, and
`TRUST_PROXY` to empty. Under multi, the operator policy has to set both, or the tenant is refused at
provisioning [M, policy engine]. The `WRITE_VALIDATION` default is read from a dev-based checkout
(`lib/server/env.js:129`); the empty `TRUST_PROXY` default is taken from the census, §3 item 5 [R].

### 4. Cross-tenant confusion [M]

| attempt against t2 | A, C | B0, B1 |
|---|---|---|
| t1's token replayed | refused, **signature** | n/a: no tenant-scoped token |
| forged claim (tenant t2), t1's signature kept | refused, **signature** | n/a |
| t2 token signed with t1's key | refused, **signature** | n/a |
| owner-1's session edits t2 | n/a | refused, **membership**: the orchestrator's claim check |

Controls: `install-wide-key` (one key for every tenant, as C.4 row 2) turned the replay into a
*claim* refusal and let the t1-key-signed t2 token through. `no-sig-verify` let the forged claim
through. `no-ownership-check` let owner-1 edit t2 in B0 and B1.

### 5. Effort for the dashboard [M, except where marked]

| | A, C | B0 | B1 |
|---|---|---|---|
| dashboard calls, first edit to a tenant | 2 (token exchange, write) | 1 | 1 |
| dashboard calls, later edits | 1 | 1 | 1 |
| calls in the whole system, later edit | 1 | 3 | 3 |
| credentials the dashboard handles [R] | 2: assertion, plus one owner token per tenant | 1: assertion | 2: assertion, service token |
| reveal, session policy (D22's initial policy) | no owner step | no owner step | no owner step |
| reveal, fresh re-authentication (D22's target) | owner re-enters password once; 5 dashboard calls | once; 3 calls | once; 3 calls |

In B the secrets service never sees the human, so the freshness check is the orchestrator's alone
[M: the compromised orchestrator revealed every tenant's secret without any login].

Control: `no-token-cache` (A, C) raised later edits from 1 dashboard call to 2.

## What the lab does not model

- **Real network isolation.** One host, one loopback address, a matrix in code.
- **A real identity provider.** Passwords and an Ed25519 assertion; no sessions, MFA, recovery,
  or federation.
- **Real key management.** The key-encryption key is a file in scratch that only the secrets
  process reads, and every process runs as the same user. No rotation, no versioning (C.3, E.3),
  no hardware or cloud key service.
- **The database.** One JSON file stands in for PostgreSQL. There is no row-level security. A
  compromised `ns-tenant-admin` can write every tenant's row directly [R].
- **Performance, scale, concurrency and availability.**
- **The connector process.** The secret's consumer is named, not run.

## Notes on the controls

Some controls changed more than their target. These side effects are expected, and the full
`changed` list for each control is in `results.json`:

- `install-wide-key` also emptied the "secrets API caller" row. In that control the key sits in a
  file beside the listener, not in the secrets service. This is an artifact of the control, not a
  protection.
- `no-ownership-check` also cut one call from B's edit, because it skips the membership lookup.
