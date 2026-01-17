# Proposal: Controller Registration Protocol

**Status:** Draft  
**Author:** Agent  
**Date:** 2026-01-17  
**Related:** [GAP-003](../../traceability/gaps.md#gap-003-no-unified-sync-identity-field-across-controllers), [Authority Model](../10-domain/authority-model.md)

---

## Executive Summary

This proposal introduces a **Controller Registration Protocol** that inverts the current relationship between Nightscout and AID controllers. Instead of Nightscout passively accepting whatever data controllers send, controllers would formally register their identity schemas, sync conventions, and capabilities. This enables:

1. **Verified identity** — Controllers authenticate and register, replacing unverified `enteredBy`
2. **Schema commitment** — Controllers declare what fields they use and how
3. **Authority delegation** — Controllers can receive delegated authority from users
4. **Conflict resolution** — Nightscout can enforce authority hierarchy based on registration

---

## Problem Statement

### Current State

Nightscout operates as a "dumb store" that accepts data from any authenticated client:

1. **No identity verification** — `enteredBy` is a free-form string anyone can set
2. **No schema commitment** — Controllers use different fields for the same concepts
3. **No authority model** — All authenticated writes are treated equally
4. **No capability discovery** — Consumers cannot know what a controller uploads

### Impact

- **Duplicate data** — Different controllers use different dedup strategies, causing duplicates
- **Lost semantics** — Override supersession, treatment edits, and deletions aren't tracked consistently
- **Security gaps** — Anyone with API access can impersonate any controller
- **Integration complexity** — Every consumer must handle controller-specific patterns

### Evidence from Gap Analysis

| Gap | Description | Registration Helps |
|-----|-------------|-------------------|
| GAP-003 | No unified sync identity field | Controllers register their identity field |
| GAP-AUTH-001 | `enteredBy` is unverified | Controllers authenticate at registration |
| GAP-AUTH-002 | No authority hierarchy | Authority granted based on registration |
| GAP-SYNC-004 | Override supersession not tracked | Controllers commit to lifecycle events |

---

## Proposed Solution

### Core Concept: Inversion of Control

Instead of Nightscout accepting any data structure:

```
Current:  Controller → (any data) → Nightscout (accepts all)
Proposed: Controller → Register → Nightscout validates → Accept conforming data
```

### Registration Flow

```
┌─────────────┐     1. Register      ┌─────────────────┐
│  Controller │ ──────────────────→  │   Nightscout    │
│   (Loop)    │                      │  Registration   │
└─────────────┘                      │    Endpoint     │
                                     └────────┬────────┘
                                              │
                                     2. Validate & Store
                                              │
                                              ▼
                                     ┌─────────────────┐
                                     │  Controller     │
                                     │  Registry       │
                                     └────────┬────────┘
                                              │
                                     3. Issue Token
                                              │
                                              ▼
┌─────────────┐     4. Use Token     ┌─────────────────┐
│  Controller │ ──────────────────→  │   Nightscout    │
│   (Loop)    │                      │   Data API      │
└─────────────┘                      └─────────────────┘
```

### Registration Document

Controllers submit a registration document describing their identity and conventions:

```yaml
ControllerRegistration:
  # Identity
  controllerId: "loop-ios"
  controllerName: "Loop"
  controllerVersion: "3.4.0"
  platform: "iOS"
  
  # Authentication
  authMethod: "oidc"
  oidcIssuer: "https://auth.loopkit.org"
  oidcClientId: "loop-nightscout-sync"
  
  # Sync Identity
  identityStrategy:
    type: "uuid"
    field: "syncIdentifier"
    scope: "per-record"  # vs "per-device" or "per-user"
  
  # Data Commitments
  uploads:
    treatments:
      eventTypes: ["Correction Bolus", "Meal Bolus", "Temp Basal", "Temporary Override"]
      fields:
        - name: "syncIdentifier"
          type: "uuid"
          required: true
        - name: "automatic"
          type: "boolean"
          required: false
          default: false
      lifecycleEvents:
        supersession: false  # Does not track override supersession
        edits: false         # Does not sync treatment edits
        deletions: false     # Does not sync deletions
    
    devicestatus:
      namespace: "loop"
      predictionFormat: "single-array"  # vs "separate-arrays"
      effectTimelines: false
  
  # Capabilities
  capabilities:
    remoteCommands: true
    remoteOverrides: true
    remoteBolus: true
    remoteCarbs: true
    otpRequired:
      overrides: false
      bolus: true
      carbs: true
  
  # Authority Request
  authorityRequest:
    level: "controller"  # 30 in authority hierarchy
    scopes:
      - "treatments:create"
      - "treatments:update:own"
      - "devicestatus:create"
      - "profile:read"
```

### Registry Benefits

With controller registrations, Nightscout can:

1. **Validate uploads** — Reject data that doesn't match registered schema
2. **Deduplicate intelligently** — Use registered identity field for dedup
3. **Enforce authority** — Check authority level before accepting writes
4. **Provide discovery** — Consumers can query what controllers are registered
5. **Audit accurately** — Verified identity replaces unverified `enteredBy`

---

## Identity Verification

### Current: Unverified `enteredBy`

```json
{
  "eventType": "Temp Basal",
  "enteredBy": "Loop",  // Anyone can claim this
  "rate": 1.5
}
```

### Proposed: Verified Controller Token

```http
POST /api/v3/treatments
Authorization: Bearer eyJ...controller-token...
Content-Type: application/json

{
  "eventType": "Temp Basal",
  "rate": 1.5
}
```

The server:
1. Validates the token against controller registry
2. Injects verified `controllerId` into the document
3. Stores both verified identity and legacy `enteredBy` for compatibility

```json
{
  "eventType": "Temp Basal",
  "rate": 1.5,
  "enteredBy": "Loop",              // Legacy, for display
  "controllerId": "loop-ios",        // Verified, for authority
  "controllerVersion": "3.4.0"
}
```

---

## Schema Commitment

### Problem: Inconsistent Field Usage

| Controller | Bolus insulin field | Duration unit | SMB indicator |
|------------|---------------------|---------------|---------------|
| Loop | `insulin` | seconds | Inferred from `automatic` |
| AAPS | `insulin` | milliseconds | `type: "SMB"` |
| Trio | `insulin` | seconds | `enteredBy` contains "SMB" |

### Solution: Declared Field Mappings

Registration includes explicit field declarations:

```yaml
uploads:
  treatments:
    bolus:
      insulinField: "insulin"
      insulinUnit: "units"
      durationField: "duration"
      durationUnit: "seconds"
      smbIndicator:
        type: "boolean-field"
        field: "automatic"
        value: true
```

Consumers can query the registry to understand how to interpret each controller's data.

---

## Authority Integration

### Delegation Model

Controllers receive authority based on registration:

```yaml
# User grants delegation to Loop controller
DelegationGrant:
  grantId: "uuid"
  grantedBy: "user-oidc-subject"
  grantedTo: "loop-ios"  # Controller ID from registration
  
  scopes:
    - "treatments:create"
    - "override:activate:exercise"
    - "override:activate:sleep"
  
  constraints:
    maxOverrideDuration: 14400
    requireConfirmation: false
    
  expiresAt: "2027-01-01T00:00:00Z"
```

### Authority Enforcement

Before accepting a write:

1. **Verify token** — Confirm controller is registered
2. **Check authority** — Controller (30) vs Human (100) authority
3. **Apply constraints** — Duration limits, rate limiting
4. **Resolve conflicts** — Higher authority wins

---

## Capability Discovery

### Consumer Query

Apps can discover registered controllers:

```http
GET /api/v3/controllers
Authorization: Bearer eyJ...consumer-token...

Response:
{
  "controllers": [
    {
      "controllerId": "loop-ios",
      "controllerName": "Loop",
      "identityStrategy": { "field": "syncIdentifier", "type": "uuid" },
      "capabilities": { "remoteCommands": true },
      "devicestatusNamespace": "loop"
    },
    {
      "controllerId": "aaps-android",
      "controllerName": "AndroidAPS",
      "identityStrategy": { "field": "identifier", "type": "uuid" },
      "capabilities": { "remoteCommands": true },
      "devicestatusNamespace": "openaps"
    }
  ]
}
```

This enables consumers to:
- Know which controllers are active
- Understand how to deduplicate each controller's data
- Parse devicestatus correctly per controller

---

## Migration Path

### Phase 1: Optional Registration (Compatibility)

- Controllers can register voluntarily
- Unregistered controllers continue to work with legacy `enteredBy`
- Registered controllers get verified identity in parallel

### Phase 2: Incentivized Registration

- Registered controllers get priority (e.g., authority enforcement)
- New features require registration (e.g., remote commands with delegation)
- Documentation encourages registration

### Phase 3: Required Registration (Breaking Change)

- All controllers must register
- Unverified `enteredBy` deprecated
- Full authority model enforcement

### Compatibility Layer

During migration, maintain both:

```json
{
  "enteredBy": "Loop",           // Legacy (writable by anyone)
  "controllerId": "loop-ios",    // Verified (from registration)
  "controllerVersion": "3.4.0"   // From registration
}
```

---

## Implementation Considerations

### Where Does Registration Live?

**Option A: Nightscout Core**
- Registration endpoints in cgm-remote-monitor
- Registry stored in MongoDB alongside data
- Pros: Single deployment, atomic with data
- Cons: Every Nightscout instance needs registration

**Option B: Nightscout Roles Gateway (NRG)**
- Registration in NRG proxy layer
- Registry stored in NRG database
- Pros: Centralized, policy enforcement already exists
- Cons: Requires NRG deployment

**Option C: Federated Registry**
- Central registry (e.g., registry.nightscout.org)
- Controllers register once, valid everywhere
- Pros: Single source of truth
- Cons: Dependency on central service

**Recommendation:** Start with Option B (NRG) since it already handles identity and access control. Migrate to Option C for scale.

### Controller Updates

Controllers can update their registration:

```http
PUT /api/v3/controllers/loop-ios
Authorization: Bearer eyJ...controller-admin-token...

{
  "controllerVersion": "3.5.0",
  "uploads": { ... }  // Updated schema
}
```

Versioned registrations allow tracking schema evolution.

---

## Open Questions

1. **Granularity:** Should registration be per-controller-type (Loop) or per-installation (user's Loop instance)?

2. **Revocation:** How do we handle revoked or compromised controller registrations?

3. **Schema enforcement:** Should Nightscout reject uploads that don't match registered schema, or just annotate them?

4. **Backward compatibility:** How long do we support unregistered controllers?

5. **Cross-instance:** Should a Loop registration be valid across all Nightscout instances, or per-instance?

6. **Versioning:** How do we handle breaking schema changes within a controller?

---

## Stakeholder Impact

### AID Controller Developers

- **Must implement:** Registration flow, token management
- **Benefit:** Verified identity, authority delegation, reduced duplicate handling

### Nightscout Maintainers

- **Must implement:** Registration endpoints, registry storage, validation logic
- **Benefit:** Better data quality, reduced support burden from duplicates

### App Developers (Consumers)

- **Can use:** Registry queries to understand controller patterns
- **Benefit:** Simpler integration, reliable deduplication

### End Users

- **Experience:** More reliable sync, proper authority (their overrides respected)
- **Action:** Grant delegation to controllers they trust

---

## Success Metrics

1. **Registration adoption:** % of sync traffic from registered controllers
2. **Duplicate reduction:** Decrease in duplicate treatments
3. **Authority conflicts:** Decrease in human overrides being overwritten
4. **Integration time:** Time for new apps to integrate (should decrease)

---

## Next Steps

- [ ] Gather feedback from Loop, AAPS, and Trio maintainers
- [ ] Draft OpenAPI specification for registration endpoints
- [ ] Prototype registration flow in NRG
- [ ] Define migration timeline with Nightscout Foundation
- [ ] Create reference implementation for one controller (e.g., Loop)
- [ ] Document consumer query patterns

---

## Related Documents

- [Authority Model](../10-domain/authority-model.md)
- [AID Controller Sync Patterns](../../mapping/cross-project/aid-controller-sync-patterns.md)
- [Nightscout API Comparison](../10-domain/nightscout-api-comparison.md)
- [Known Gaps](../../traceability/gaps.md)
- [NRG Access Modes](../../externals/nightscout-roles-gateway/docs/access-modes.md)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial draft |
