# Authority and identity model

*What this is: a reference (contributor-facing). Read after the [authority
specification](../30-design/platform/spec/authority.md); leads to [agents in the
ecosystem](../30-design/platform/agent-trust-boundaries-2026-10-18.md).* **Status 2026-10-18:
proposed. The rules are in the authority and commands specifications; this page keeps what they
do not carry: why identity is federated rather than stored, and a worked delegation grant.**
Current decisions: [execution plan §1](../30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions).
The page's longer text, with authority levels, conflict scenarios and safety invariants, is in
git: [full text at `85c645c8`](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/85c645c8b003b61dc07ea31f8a7002711493b18a/docs/10-domain/authority-model.md).

## Where each rule is specified

| question | specified in |
|---|---|
| Who is a principal, and how each authenticates | [authority AU1–AU4](../30-design/platform/spec/authority.md#2-principals-and-credentials): devices hold a native per-tenant credential; owners and caregivers are to sign in through Ory Kratos on hosted sites; everything binds to a subject, never a token |
| What a credential may do today | [authority AU5](../30-design/platform/spec/authority.md#2-principals-and-credentials): writes per collection, reading one bit |
| Who started an intent, including an agent | [state and intent S8](../30-design/platform/spec/state-intent.md#2-rules): a value in the controller's own vocabulary; an agent initiator is `{value: other, controllerTerm}`, and no `agent` value is added |
| An agent's role | [registration §9](../30-design/platform/spec/registration.md#9-channels-roles-and-provenance): an `other` role the hub lists |
| Proposing a change, and approving one | [commands CM11–CM16](../30-design/platform/spec/commands.md#6-proposals-and-approvals-proposed): read access confers no propose role (CM12); an approval binds to the payload's hash (CM13); approving is sending (CM14) |
| Who may receive a command | [authority §6](../30-design/platform/spec/authority.md#6-who-may-receive-a-command); [commands §2](../30-design/platform/spec/commands.md#2-where-a-command-goes) |
| Combining overlapping intents | the controller's ([state and intent S1](../30-design/platform/spec/state-intent.md#2-rules)); the hub records the result and ranks no writer above another |
| What delegation must provide | [authority §7, DR1–DR7](../30-design/platform/spec/authority.md#7-delegation-not-decided); the grant's design is open ([authority §9](../30-design/platform/spec/authority.md#9-open) item 6) |
| What is recorded for audit | [authority §8](../30-design/platform/spec/authority.md#8-what-is-recorded-for-audit); [commands CM1](../30-design/platform/spec/commands.md#4-the-command-record-proposed) |

Authority levels, a hierarchy among writers, conflict scenarios and composition invariants are
not hub rules: the controller composes and validates (D18). Where each idea of the earlier draft in
cgm-remote-monitor's `docs/proposals` now lives is in the [control-plane supersession
map](../30-design/tenancy/nightscout-control-plane-reconciliation-2026-09-11.md).

## Why identity is federated

### The credential dilemma

Nightscout does not implement username and password authentication, by choice:

1. **Liability and risk.** Managing custom credentials exposes the project to breach liability.
2. **Informed consent over gatekeeping.** Access is granted by consent, not by proving knowledge
   of a secret.
3. **Several people per site.** A personal site still has several users: the person with
   diabetes, caregivers, school health staff, clinicians, each with their own identity provider.
4. **Observed practice.** People share "mongo strings" in support threads, share passwords with
   apps and caregivers, and accept third-party client credentials. More password flows add to
   this.

The rationale is [ADR-003: No custom credentials](../90-decisions/adr-003-no-custom-credentials.md).

### Zero-trust direction

Nightscout Roles Gateway moves toward:

- every request authenticated through federated identity (Google, Apple, clinic SSO);
- short-lived tokens instead of long-lived passwords;
- explicit consent: a person joins a group by consenting, not by receiving a password;
- policy-driven access: schedules and roles decide access, not possession of a credential.

The gateway's access modes are anonymous (A), identity-mapped through OAuth2/OIDC (B) and
`API_SECRET` for older clients (C); its consent flow is invitation, OAuth2 login, consent to
identity visibility, a `joined_groups` record, then access by policy
([access modes](../../externals/nightscout-roles-gateway/docs/access-modes.md),
[policies and permissions](../../externals/nightscout-roles-gateway/docs/policies-and-permissions.md)).

## Delegation grants

*Proposed; not implemented.* A worked example of a grant meeting [DR1–DR7](../30-design/platform/spec/authority.md#7-delegation-not-decided),
offered as input to the grant's design. A person lets an agent propose exercise and sleep
overrides for four months, within limits:

```json
{
  "grantId": "8e0c3f5a-…",
  "grantedBy": "<the person's subject>",
  "grantedTo": "<the subject of the agent's credential>",
  "permissions": ["api:proposals:create"],
  "roles": [{"channel": "override", "role": {"value": "other", "controllerTerm": "propose"}}],
  "purpose": "suggest activity overrides from the calendar",
  "constraints": {
    "allowedPresets": ["Exercise", "Sleep"],
    "maxDurationMinutes": 240,
    "maxProposalsPerDay": 6,
    "validTimeWindows": [{"start": "06:00", "end": "22:00"}]
  },
  "grantedAt": "2026-10-18T00:00:00Z",
  "expiresAt": "2027-02-18T00:00:00Z"
}
```

- **Subjects, not tokens** ([AU4](../30-design/platform/spec/authority.md#2-principals-and-credentials)):
  rotating the agent's token changes nothing the grant names.
- **Propose, not act.** The grant gives `api:proposals:create` and a propose role, never
  `api:commands:create`, so every change still needs an approval bound to its payload hash
  ([CM12–CM14](../30-design/platform/spec/commands.md#6-proposals-and-approvals-proposed)).
- **Purpose and expiry are fields** (DR3), and revocation is a write to the grant (DR6).
- **`maxProposalsPerDay`** is one answer to proposal volume, which the commands specification
  lists as open ([commands §9](../30-design/platform/spec/commands.md#9-open), UCA-PROP-002).

Before accepting a proposal under a grant, a hub would check that the grant exists, has not
expired or been revoked, names the sender's subject, covers the permission and role, and that the
proposal is within its constraints and time window. Whether the change is safe stays the
controller's own validation (D18).

## Current state (gaps)

Read from cgm-remote-monitor `dev` `fade2299`.

| concept | status | where it is specified |
|---|---|---|
| `enteredBy` | implemented: free text, not verified | an identifying field, never an identity ([authority §8](../30-design/platform/spec/authority.md#8-what-is-recorded-for-audit)) |
| verified identity for owners and caregivers | not implemented | [AU1](../30-design/platform/spec/authority.md#2-principals-and-credentials) (Kratos, adopted in principle and gated) |
| delegation grants | not implemented | [authority §7](../30-design/platform/spec/authority.md#7-delegation-not-decided) (requirements; design open) |
| proposals and approvals | not implemented | [commands §6](../30-design/platform/spec/commands.md#6-proposals-and-approvals-proposed) (proposed) |
| audit | partial: `srvCreated` and `srvModified` on writes; reads not recorded | [authority §8](../30-design/platform/spec/authority.md#8-what-is-recorded-for-audit) |

## Cross-references

- [ADR-003: No custom credentials](../90-decisions/adr-003-no-custom-credentials.md)
- [Trusted identity providers](trusted-identity-providers.md)
- The earlier draft in cgm-remote-monitor's `docs/proposals`:
  [conflict-resolution.md](../../externals/cgm-remote-monitor-official/docs/proposals/conflict-resolution.md),
  [oidc-actor-identity-proposal.md](../../externals/cgm-remote-monitor-official/docs/proposals/oidc-actor-identity-proposal.md)
- [NRG access modes](../../externals/nightscout-roles-gateway/docs/access-modes.md),
  [NRG policies and permissions](../../externals/nightscout-roles-gateway/docs/policies-and-permissions.md)
