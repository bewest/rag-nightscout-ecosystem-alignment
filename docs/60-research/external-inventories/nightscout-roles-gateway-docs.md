# Nightscout Roles Gateway Documentation Inventory

**Repo Alias:** `ns-gateway`  
**Source URL:** https://github.com/t1pal/nightscout-roles-gateway.git  
**Ref:** replit  
**Last Inventory:** 2026-01-16

---

## Summary

The Nightscout Roles Gateway (NRG) is a cloud-native RBAC controller that provides scheduled, identity-aware access control for Nightscout instances. Extensive documentation exists for architecture, policies, and access control.

**Total Documentation Files:** 23 markdown files

---

## Documentation Categories

### 1. Architecture & Core Concepts

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| Architecture | `docs/ARCHITECTURE.md` | System design, decision flow, database schema | **Critical** |
| Policies and Permissions | `docs/policies-and-permissions.md` | Group/policy/schedule model | **Critical** |
| Access Modes | `docs/access-modes.md` | Mode A/B/C (anonymous/identity/API secret) | **Critical** |
| Warden Gateway | `docs/warden-gateway.md` | NGINX auth_request integration | High |
| Token Management | `docs/token-management.md` | JWT and token handling | High |

### 2. Identity & Authorization

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| Privy Identity Access | `docs/privy-identity-access.md` | User identity flow | High |
| OAuth Client Lifecycle | `docs/oauth-client-lifecycle.md` | OAuth2/OIDC integration | High |
| Site Registration Workflow | `docs/site-registration-workflow.md` | Onboarding flow | Medium |
| Owner Management API | `docs/owner-management-api.md` | Site owner operations | Medium |
| Criteria System | `docs/criteria-system.md` | BYOD validation pipeline | Medium |

### 3. Proposals

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| OIDC Actor Identity | `docs/proposals/oidc-actor-identity-proposal.md` | Verified identity for data mutations | **Critical** |
| Default Authenticated Permission | `docs/proposals/default-authenticated-permission.md` | Default access levels | High |
| Multi-Secret Authentication | `docs/proposals/multi-secret-authentication.md` | Multiple API secret support | Medium |
| Inclusion Traits | `docs/PROPOSAL-inclusion-traits.md` | Group membership expansion | Medium |

### 4. Operations & Maintenance

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| README | `README.md` | Project overview, use cases | Reference |
| Docs README | `docs/README.md` | Documentation index | Reference |
| Maintenance Guide | `docs/MAINTENANCE-GUIDE.md` | Operational procedures | Low |
| Roadmap | `docs/ROADMAP.md` | Future development plans | Reference |
| Migrations Narrative | `docs/MIGRATIONS-NARRATIVE.md` | Schema evolution history | Reference |
| Use Cases Matrix | `docs/USE-CASES-MATRIX.md` | Scenario coverage | Reference |

### 5. Test Specifications

| File | Path | Description | Integration Priority |
|------|------|-------------|---------------------|
| Test Specs README | `docs/test-specs/README.md` | Test organization | Low |
| Phase 1: Authorization | `docs/test-specs/phase1-authorization.md` | Auth test coverage | Medium |
| Phase 2: Identity Access | `docs/test-specs/phase2-identity-access.md` | Identity tests | Medium |
| Phase 3: Criteria Validation | `docs/test-specs/phase3-criteria-validation.md` | BYOD validation tests | Low |
| Phase 4: Triggers | `docs/test-specs/phase4-triggers.md` | Database trigger tests | Low |

---

## Key Concepts Extracted

### The Three Access Modes

| Mode | Description | Toggle |
|------|-------------|--------|
| **Mode A** | Anonymous/Public - anyone with link can view | `require_identities = false` |
| **Mode B** | Identity-Mapped - visitors must log in, ACL controlled | `require_identities = true` |
| **Mode C** | Legacy Escape - API secret header bypasses identity | `exempt_matching_api_secret = true` |

### Authority Hierarchy (from conflict-resolution)

| Level | Authority | Description |
|-------|-----------|-------------|
| 100 | Human (Primary) | Full control |
| 80 | Human (Caregiver) | Delegated by primary |
| 50 | Agent | Delegated by primary/caregiver |
| 30 | Controller | AID algorithm (Loop/AAPS) |
| 10 | System | Automated |

### Core Database Entities

| Entity | Table | Description |
|--------|-------|-------------|
| Sites | `registered_sites` | Protected Nightscout instances |
| Groups | `group_definitions` | Collections of identities (roles) |
| Inclusion Specs | `group_inclusion_specs` | Group membership rules |
| Connection Policies | `connection_policies` | Group-to-site permission bindings |
| Scheduled Policies | `scheduled_policies` | Time-based access rules |
| Joined Groups | `joined_groups` | Consent records |

### Policy Types

| Type | Behavior |
|------|----------|
| `default` | Standard allow/deny |
| `nsjwt` | Exchange JWT with Nightscout for fine-grained permissions |

---

## Integration Recommendations

### Phase 1: Authorization Model

1. **Map access modes** → `mapping/nightscout/access-control.md`
2. **Document authority levels** → `docs/10-domain/authority-hierarchy.md`
3. **Link to cgm-remote-monitor auth** → Cross-reference with security-audit.md

### Phase 2: Scheduling & Delegation

1. **Extract schedule format** → `specs/jsonschema/nrg-schedule.json`
2. **Document delegation grants** → Align with conflict-resolution.md proposal
3. **Map consent flow** → `mapping/nightscout/consent-model.md`

### Phase 3: Identity Integration

1. **OIDC proposal alignment** → Both NRG and cgm-remote-monitor have parallel proposals
2. **Actor identity spec** → `specs/` alignment schema for verified identity

---

## Cross-References

### Shared Concepts with cgm-remote-monitor

| Concept | Gateway | Core | Notes |
|---------|---------|------|-------|
| API_SECRET | Mode C bypass | Auth method v1 | Same hashing (SHA-1) |
| JWT tokens | nsjwt policy type | API v2/v3 auth | NRG exchanges with NS |
| Shiro permissions | Via nsjwt | Native | Gateway proxies |
| OIDC/OAuth2 | Kratos/Hydra | Proposed plugin | Complementary approaches |

### Gaps Identified

| Gap | Description |
|-----|-------------|
| GAP-NRG-001 | Agent flip-flop prevention not enforced (proposed only) |
| GAP-NRG-002 | Override supersession not tracked in gateway |

---

## Source Files Summary

```
externals/nightscout-roles-gateway/
├── README.md
├── docs/
│   ├── ARCHITECTURE.md              ← CRITICAL
│   ├── policies-and-permissions.md  ← CRITICAL
│   ├── access-modes.md              ← CRITICAL
│   ├── warden-gateway.md
│   ├── token-management.md
│   ├── privy-identity-access.md
│   ├── oauth-client-lifecycle.md
│   ├── site-registration-workflow.md
│   ├── owner-management-api.md
│   ├── criteria-system.md
│   ├── MAINTENANCE-GUIDE.md
│   ├── ROADMAP.md
│   ├── MIGRATIONS-NARRATIVE.md
│   ├── USE-CASES-MATRIX.md
│   ├── PROPOSAL-inclusion-traits.md
│   ├── proposals/
│   │   ├── oidc-actor-identity-proposal.md
│   │   ├── default-authenticated-permission.md
│   │   └── multi-secret-authentication.md
│   └── test-specs/
│       ├── README.md
│       ├── phase1-authorization.md
│       ├── phase2-identity-access.md
│       ├── phase3-criteria-validation.md
│       └── phase4-triggers.md
└── test/quirks/README.md
```

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial inventory |
