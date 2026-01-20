# nightscout-roles-gateway: Nightscout Integration

**Source**: `externals/nightscout-roles-gateway`  
**Verified**: 2026-01-20

## Proxy Architecture

### Request Flow

```
Vanity URL (site.gw.com)
  → Warden endpoint /warden/v1/active/backend/for/:expected_name
  → Policy evaluation pipeline
  → Returns x-upstream-origin header
  → NGINX proxies to actual Nightscout instance
```

### Key Headers

**Request Headers:**
- `API-SECRET` - Legacy auth
- `x-policy-id` - Policy identifier
- `x-group-id` - Group identifier
- `x-email-spec` - Email for identity matching

**Response Headers:**
- `x-upstream-origin` - Target Nightscout URL
- `x-forwarded-host` - Original host
- `X-NSJWT` - JWT token for downstream

## Site Configuration

Per `lib/entities/index.js`:

```javascript
{
  expected_name: "my-site",           // Vanity subdomain
  upstream_origin: "https://...",     // Actual NS URL
  exempt_matching_api_secret: true,   // Mode C bypass
  require_identities: false           // Mode B enforcement
}
```

## JWT Token Exchange

When `policy_type='nsjwt'`:

```javascript
// lib/exchanged.js:56-82
GET /api/v2/authorization/request/{policy_spec}
→ Returns Nightscout JWT
→ Cached for 8 hours (ttl: 28800 * 1000)
→ Set as X-NSJWT response header
```

## Site Validation (BYOD)

Per `lib/criteria/core.js:52-100`:

### Stage 1: Static Checks
- API secret length > 11 characters
- URL syntax validation

### Stage 2: Liveness Check
```javascript
GET /api/v1/status.json
```

### Stage 3: Auth Check
```javascript
GET /api/v1/status.json
Header: API-SECRET (hashed)
```

Results stored in `nightscout_inspection_results` table.

## Consent/Audit Trail

Per `lib/routes.js:316-317`:

```
/api/v1/privy/:identity/groups/joined
```

- Users consent to group membership
- Creates `joined_groups` records
- Links: `subject` (Kratos ID) → `group_id` → `policy_id`
- Supports HIPAA-adjacent audit requirements

## Kratos/Hydra Integration

Per `lib/privy/index.js`:

- `kratos_whoami()` middleware extracts user identity
- OAuth client lifecycle via:
  ```
  /api/v1/owner/:owner_ref/sites/:expected_name/available/clients
  ```

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-RG-INT-001 | Must validate Nightscout liveness before proxying | `lib/criteria/core.js` |
| REQ-RG-INT-002 | Must exchange ACL for Nightscout JWT | `lib/exchanged.js` |
| REQ-RG-INT-003 | Must cache JWT tokens (8 hour TTL) | `lib/exchanged.js:15` |
| REQ-RG-INT-004 | Must log group consent for audit | `lib/routes.js` |
