# Mapping: Nightscout - Authorization

This document maps Nightscout's authorization model to alignment workspace concepts.

---

## Authentication Methods

### Current Implementation

| Method | API Version | Description |
|--------|-------------|-------------|
| API_SECRET | v1 | SHA-1/SHA-512 hash comparison |
| Access Tokens | v1/v2 | Pre-shared tokens for subjects |
| JWT | v2/v3 | Signed tokens with expiration |

### Alignment Mapping

| Nightscout | Alignment Concept | Notes |
|------------|-------------------|-------|
| API_SECRET | `admin_credential` | Full admin access |
| Access Token | `subject_token` | Limited access per subject |
| JWT | `bearer_token` | Standard OAuth2 pattern |
| Subject | `actor` | Identity performing action |

---

## Permission Model (Shiro)

Nightscout uses Apache Shiro-style permission strings.

### Permission Format

```
api:{collection}:{action}
```

| Component | Values |
|-----------|--------|
| `api` | Fixed prefix |
| `collection` | `entries`, `treatments`, `profile`, `devicestatus`, `food` |
| `action` | `create`, `read`, `update`, `delete` |

### Permission Examples

| Permission | Description |
|------------|-------------|
| `api:entries:read` | Read glucose entries |
| `api:treatments:create` | Create treatments |
| `api:profile:update` | Modify profiles |
| `*` | Admin (all permissions) |

### Alignment Mapping

| Shiro Permission | Alignment Scope |
|------------------|-----------------|
| `api:entries:read` | `read:entries` |
| `api:treatments:create` | `write:treatments` |
| `*` | `admin` |

---

## Gateway Authorization (NRG)

The Nightscout Roles Gateway adds identity-aware access control.

### Access Modes

| Mode | Description | Nightscout Equivalent |
|------|-------------|----------------------|
| Mode A | Anonymous/Public | `AUTH_DEFAULT_ROLES` with readable |
| Mode B | Identity-Mapped | New (no equivalent) |
| Mode C | API Secret Bypass | Standard API_SECRET auth |

### Policy Types

| NRG Policy | Behavior |
|------------|----------|
| `default` | Standard allow/deny |
| `nsjwt` | Exchange for Nightscout JWT |

---

## Actor Identity

### Current State (Gaps)

| Field | Status | Notes |
|-------|--------|-------|
| `enteredBy` | Implemented | Free-form, unverified |
| Verified identity | Not implemented | Proposed via OIDC |
| Authority level | Not implemented | Proposed in conflict-resolution.md |

### OIDC Proposal

The OIDC Actor Identity proposal adds verified identity:

```yaml
actor:
  issuer: "https://hydra.example.com"
  subject: "user-12345"
  name: "Jane Doe"
  email: "jane@example.com"
  authority: "primary"
```

---

## Authority Levels (Proposed)

| Level | Actor Type | Permissions |
|-------|------------|-------------|
| 100 | Human (Primary) | All |
| 80 | Human (Caregiver) | Delegated subset |
| 50 | Agent | Delegated subset |
| 30 | Controller | Algorithm actions only |
| 10 | System | Read-only + sync |

---

## Code References

| Purpose | Location |
|---------|----------|
| Auth initialization | `crm:lib/authorization/index.js` |
| Shiro trie | `crm:lib/authorization/authorization.js` |
| JWT handling | `crm:lib/server/enclave.js` |
| Brute-force protection | `crm:lib/authorization/delaylist.js` |
| NRG policy decision | `ns-gateway:lib/policies/index.js` |

---

## Gaps Identified

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-AUTH-001 | `enteredBy` is unverified | Cannot audit who made changes |
| GAP-AUTH-002 | No authority hierarchy | All writes treated equally |
| GAP-AUTH-003 | No delegation grants | Cannot limit caregiver/agent access |
| GAP-AUTH-004 | No rate limiting | DoS vulnerability |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial mapping from security-audit.md and NRG docs |
