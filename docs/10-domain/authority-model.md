# Authority & Identity Model

This document defines the authority hierarchy and identity model used for conflict resolution when multiple actors interact with AID systems.

---

## Overview

In multi-user AID systems, conflicts arise when different actors (humans, caregivers, AI agents, controllers) attempt to modify the same state. This model defines:

1. **Who can make changes** (identity)
2. **What changes they can make** (permissions)
3. **How conflicts are resolved** (authority hierarchy)

---

## Actor Types

### Primary Actors

| Actor Type | Description | Authority Level | Examples |
|------------|-------------|-----------------|----------|
| **Human (Primary)** | Person with diabetes or primary caregiver | 100 (Highest) | User activating exercise override |
| **Human (Caregiver)** | Delegated caregiver with explicit permissions | 80 | Parent adjusting child's settings |
| **Agent** | AI/automated system with delegated authority | 50 | AI suggesting sleep mode |
| **Controller** | AID algorithm on device | 30 | Loop activating temp basal |
| **System** | Automated infrastructure | 10 | Background sync processes |

### Identity Structure

Each actor has a unique identity:

```yaml
IssuerIdentity:
  issuerType: "human" | "controller" | "agent" | "caregiver" | "system"
  issuerId: string          # Unique identifier
  authority: "primary" | "delegated" | "automated"
  delegatedBy: string       # If delegated, who granted authority
  delegationScopes: [string] # What actions are permitted
```

---

## Authority Rules

### Core Principles

1. **Higher authority wins** — Higher authority can always override lower authority
2. **Equal authority uses time** — Same authority level = last write wins
3. **Lower cannot override higher** — Lower authority cannot supersede higher authority actions
4. **Controller respects human** — Controller cannot override active human overrides

### Authority Hierarchy

```
┌─────────────────────────────────────────┐
│           HUMAN (PRIMARY)               │  ← Can do anything
│         Authority Level: 100            │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│          HUMAN (CAREGIVER)              │  ← Delegated by primary
│         Authority Level: 80             │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│              AGENT                      │  ← Delegated by primary/caregiver
│         Authority Level: 50             │
└───────────────────┬─────────────────────┘
                    │
┌───────────────────▼─────────────────────┐
│            CONTROLLER                   │  ← Automated, follows policy
│         Authority Level: 30             │
└─────────────────────────────────────────┘
```

---

## Delegation Model

### Delegation Grants

Humans can delegate authority to agents with constraints:

```javascript
{
  "grantId": "uuid",
  "grantedBy": "human-user-id",
  "grantedTo": "agent-id",
  
  "scopes": [
    "override.activate:exercise",
    "override.activate:sleep",
    "override.suggest:*"
  ],
  
  "constraints": {
    "maxOverrideDuration": 14400,    // 4 hours max
    "allowedOverrideTypes": ["exercise", "sleep", "preMeal"],
    "maxActivationsPerDay": 6,
    "validTimeWindows": [
      { "start": "06:00", "end": "22:00" }
    ]
  },
  
  "grantedAt": "2026-01-01T00:00:00Z",
  "expiresAt": "2026-12-31T23:59:59Z"
}
```

### Delegation Validation

Before executing a delegated action:

1. Check grant exists and is not expired
2. Verify action matches granted scopes
3. Confirm within constraints (time, frequency, duration)
4. Validate within time windows

---

## Conflict Scenarios

### Scenario 1: Override Supersession

**Situation**: Human starts "Exercise" override, then Agent tries to start "High Activity" override.

**Resolution**:
- Compare authority levels
- Human (100) > Agent (50)
- Agent request is blocked unless human explicitly delegates

### Scenario 2: Controller vs Human Override

**Situation**: Human has active override; controller tries to adjust.

**Resolution**:
- Controller respects human override bounds
- Controller can make adjustments **within** the override's limits
- Controller cannot end or modify the human-initiated override

### Scenario 3: Agent Rate Limiting

**Situation**: Agent activates/deactivates same override repeatedly.

**Resolution**:
- Rate limiting prevents flip-flopping
- Max activations per hour: 4
- Cooldown after end: 15 minutes
- Human confirmation required after 2 activations

---

## Nightscout Implementation

### Current State (Gaps)

| Concept | Status | Notes |
|---------|--------|-------|
| `enteredBy` field | Implemented | Free-form nickname, not verified |
| Authority levels | Not implemented | All writes treated equally |
| Delegation grants | Not implemented | Proposed in OIDC RFC |
| Conflict resolution | Not implemented | Last write wins |
| Audit trail | Partial | `srvCreated`/`srvModified` tracked |

### Proposed Enhancements

1. **OIDC Actor Identity** — Replace `enteredBy` with verified identity claims
2. **Authority Enforcement** — Check authority before accepting mutations
3. **Delegation System** — Formal grant/revoke for caregivers and agents
4. **Conflict Audit** — Log conflict resolutions for review

---

## Gateway Implementation

The Nightscout Roles Gateway implements identity-based access control:

### Access Modes

| Mode | Description | Identity Required |
|------|-------------|-------------------|
| Mode A | Anonymous/Public | No |
| Mode B | Identity-Mapped | Yes (via OAuth2/OIDC) |
| Mode C | API Secret Bypass | No (legacy compatibility) |

### Permission Types

| Type | Description |
|------|-------------|
| `default` | Standard allow/deny |
| `nsjwt` | Exchange for Nightscout JWT with Shiro permissions |

### Consent Tracking

Identity-based access requires explicit consent:
1. User receives invitation
2. User logs in via OAuth2
3. User consents to identity visibility
4. `joined_groups` record created
5. Access granted per policy

---

## Safety Invariants

### Never Violated

1. **Human always wins** — Human-initiated action cannot be blocked by lower authority
2. **Safety limits respected** — Composed effects never exceed safety limits
3. **Conservative composition** — When in doubt, choose the safer option
4. **Audit everything** — All conflict resolutions are logged
5. **Explicit revocation** — Delegations must be explicitly revoked

---

## Cross-References

- [Nightscout Conflict Resolution Proposal](../../externals/cgm-remote-monitor/docs/proposals/conflict-resolution.md)
- [NRG Access Modes](../../externals/nightscout-roles-gateway/docs/access-modes.md)
- [NRG Policies and Permissions](../../externals/nightscout-roles-gateway/docs/policies-and-permissions.md)
- [OIDC Actor Identity Proposal](../../externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial extraction from conflict-resolution.md and NRG docs |
