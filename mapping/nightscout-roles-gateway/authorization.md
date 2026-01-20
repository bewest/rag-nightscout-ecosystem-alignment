# nightscout-roles-gateway: Authorization Model

**Source**: `externals/nightscout-roles-gateway`  
**Verified**: 2026-01-20

## Three-Mode Access Control

The gateway implements three orthogonal access modes:

### Mode A: Anonymous Access

- Active when `require_identities=false`
- Public access to site data
- No authentication required

### Mode B: Identity-Mapped Access

- Active when `require_identities=true`
- Users matched against group membership via ACLs
- Requires login via Kratos/Hydra

### Mode C: API Secret Bypass

- Legacy uploader compatibility
- API-SECRET header checked against `nightscout_secrets` table
- Bypass when `exempt_matching_api_secret=true`

## RBAC Components

Per `lib/policies/index.js:5-200`:

### Group Definitions

```javascript
group_definitions: {
  name: "School Health Office",
  // ...
}
```

### Group Inclusion Specs

```javascript
group_inclusion_specs: {
  identity_type: "email" | "anonymous" | "organization",
  identity_spec: "pattern or value"
}
```

### Connection Policies

```javascript
connection_policies: {
  group_id: "...",
  site_id: "...",
  policy_type: "default" | "nsjwt",
  policy_spec: "allow" | "deny"
}
```

### Scheduled Policies

Time-based access with weekly schedules and fill patterns.

## Decision Flow

```javascript
// lib/policies/index.js:55-81

1. Is site enabled? → No → 403 Forbidden
2. Check authenticity (strictly_nightscout mode)
3. Mode C: API-SECRET matches?
   → Yes AND exempt_matching_api_secret=true → ALLOW
4. Mode B: require_identities=true?
   → No → ALLOW (Mode A)
   → Yes → Check unified_active_site_policies view
      └─ ACL with policy_spec='allow'? → ALLOW
      └─ policy_type='nsjwt' AND token? → ALLOW
      └─ No valid ACL → 403 Forbidden
```

## Key Functions

| Function | Purpose | File:Line |
|----------|---------|-----------|
| `decision()` | Final access decision | `lib/policies/index.js:55` |
| `matches_api_secret()` | Hash and lookup API-SECRET | `lib/policies/index.js:83` |
| `get_acl_by_identity_param()` | Query policies by subject | `lib/policies/index.js:150` |
| `deny_site_prefs()` | Early rejection | `lib/policies/index.js:98` |

## Database Tables

| Table | Purpose |
|-------|---------|
| `nightscout_secrets` | Hashed API secrets |
| `unified_active_site_policies` | Combined policy view |
| `joined_groups` | User-group memberships |
| `registered_sites` | Site configurations |

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-RG-001 | Must support three access modes | `docs/ARCHITECTURE.md` |
| REQ-RG-002 | API secrets must be SHA1 hashed in storage | `lib/tokens/index.js` |
| REQ-RG-003 | Must support time-based access policies | `lib/policies/index.js` |
| REQ-RG-004 | Must audit group membership for HIPAA | `lib/routes.js:316-317` |

## Gaps Identified

| ID | Gap | Impact |
|----|-----|--------|
| GAP-RG-001 | No standard Nightscout integration yet | Requires separate deployment |
| GAP-AUTH-002 | Authority hierarchy not in core Nightscout | See `mapping/nightscout/authorization.md` |
