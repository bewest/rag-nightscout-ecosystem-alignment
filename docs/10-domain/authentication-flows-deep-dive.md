# Nightscout Authentication Flows Deep Dive

> **Last Updated**: 2026-01-29  
> **Status**: Complete  
> **Gaps Identified**: GAP-AUTH-001, GAP-AUTH-002, GAP-AUTH-003, GAP-AUTH-004

## Overview

Nightscout supports multiple authentication mechanisms for different use cases. This document analyzes the authentication and authorization system in cgm-remote-monitor and how AID clients authenticate.

## Authentication Methods

### 1. API Secret (Admin Access)

The simplest and most powerful authentication method.

**How it works**:
1. Server has `API_SECRET` environment variable
2. Client sends SHA1 hash of secret in `api-secret` header
3. If hash matches, client gets full `*` permissions

**Extraction Priority**:
1. Query parameter: `?secret=<hash>`
2. Header: `api-secret: <hash>`
3. Request body: `{ "secret": "<hash>" }`

**Source**: `lib/authorization/index.js:78-98`

```javascript
function apiSecretFromRequest (req) {
  let secret = req.query && req.query.secret 
    ? req.query.secret 
    : req.header('api-secret');
  // Also checks req.body.secret
}
```

**Security Notes**:
- API_SECRET grants full admin access (`*` permissions)
- Bypasses all role-based access control
- SHA1 hashing is considered weak by modern standards
- No rate limiting on secret attempts (only delay list)

---

### 2. Access Tokens (Role-Based)

Token-based authentication with granular permissions.

**Token Format**: `{subject}-{digest}`
- Example: `myuploader-a1b2c3d4e5f6`
- Subject: Human-readable identifier
- Digest: SHA1 of random bytes (truncated)

**Token Exchange Flow**:
```
1. Create subject with roles via API
   POST /api/v2/authorization/subjects
   
2. Generate access token for subject
   POST /api/v2/authorization/subjects/{id}/token
   
3. Exchange access token for JWT
   GET /api/v2/authorization/request/{accessToken}
   
4. Use JWT in subsequent requests
   Authorization: Bearer <jwt>
```

**Source**: `lib/authorization/storage.js`

---

### 3. JWT Tokens

Signed JSON Web Tokens with embedded permissions.

**JWT Structure**:
```json
{
  "accessToken": "myuploader-a1b2c3d4e5f6",
  "iat": 1704067200,
  "exp": 1704096000
}
```

**Configuration**:
- Signing algorithm: HS256 (HMAC-SHA256)
- Expiration: 8 hours (configurable)
- Secret storage: `node_modules/.cache/.jwt-secret` (problematic!)

**Source**: `lib/authorization/index.js:189-192`

```javascript
const verified = env.enclave.verifyJWT(data.token);
token = verified.accessToken;
```

**JWT Secret Issue** (GAP-AUTH-001):
The JWT secret is stored in `node_modules/.cache/`, which can be deleted during npm updates, invalidating all existing tokens.

---

## Permission Model (Shiro-Trie)

Nightscout uses Apache Shiro-style permissions with a trie data structure.

### Permission Format

```
{domain}:{collection}:{action}
```

Examples:
- `api:entries:read` - Read entries collection
- `api:treatments:create` - Create treatments
- `api:*:read` - Read any collection
- `*` - Full admin access

### Default Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| `admin` | `['*']` | Full access |
| `readable` | `['*:*:read']` | Read-only access |
| `careportal` | `['api:treatments:create']` | Careportal entry |
| `devicestatus-upload` | `['api:devicestatus:create']` | Device status only |
| `denied` | `[]` | No access |
| `status-only` | `['api:status:read']` | Status endpoint only |

**Source**: `lib/authorization/storage.js`

### Permission Resolution

```
1. Check if API_SECRET provided → Full access
2. Check if JWT token provided → Extract accessToken
3. Look up subject by accessToken → Get roles
4. Convert roles to Shiro permissions → Build permission trie
5. Check if trie includes requested permission
```

---

## Client Authentication Patterns

### AAPS (AndroidAPS)

**Method**: Access Token via WebSocket

**Implementation**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/`

```kotlin
// NSClientV3Service.kt
socket.emit("subscribe", JSONObject().apply {
    put("accessToken", accessToken)
})
```

**Features**:
- Uses Socket.IO for real-time sync
- Stores token in preferences: `StringKey.NsClientAccessToken`
- WebSocket endpoints: `/storage`, `/alarm`
- Modern approach with bidirectional communication

---

### Loop

**Method**: API Secret (plain or hashed)

**Implementation**: `NightscoutService/NightscoutServiceKit/`

```swift
// NightscoutService.swift
struct NightscoutService {
    var apiSecret: String?
}

// Creates client with secret
NightscoutClient(siteURL: url, apiSecret: secret)
```

**Features**:
- Simple credential model
- Keychain-based storage via `KeychainManager`
- RESTful HTTP calls
- OTP manager for remote commands

---

### xDrip+

**Method**: SHA1-hashed API Secret

**Implementation**: `app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/`

```java
// NightscoutUploader.java
final String hashedSecret = Hashing.sha1()
    .hashBytes(secret.getBytes(Charsets.UTF_8))
    .toString();
```

**Features**:
- Hashes secret client-side before transmission
- Uses Retrofit with OkHttp3
- Supports REST API v0 (plain) and v1 (hashed)
- Header: `@Header("api-secret")`

---

## Rate Limiting

**Implementation**: `lib/authorization/delaylist.js`

**Behavior**:
- Failed auth attempts are tracked by IP
- Each failed attempt adds 5 seconds delay
- Maximum delay accumulates over time
- Successful auth clears delay

**Weakness** (GAP-AUTH-002):
- Only delays, doesn't block after N failures
- No account lockout mechanism
- No alerting on brute force attempts

---

## Security Analysis

### Gaps Identified

#### GAP-AUTH-001: JWT Secret Storage Location

**Description**: JWT secret stored in `node_modules/.cache/.jwt-secret`, which can be deleted during npm operations.

**Impact**: All JWTs become invalid after npm install/update.

**Remediation**: Store JWT secret in environment variable or persistent config.

---

#### GAP-AUTH-002: No Account Lockout

**Description**: Rate limiting only delays requests, never blocks them. No maximum attempt limit.

**Impact**: Brute force attacks possible with patience.

**Remediation**: Implement lockout after N failed attempts, with admin unlock.

---

#### GAP-AUTH-003: enteredBy Field Unverified

**Description**: The `enteredBy` field in treatments is not verified against authenticated identity.

**Impact**: Any authenticated user can claim any identity in audit logs.

**Remediation**: Auto-populate `enteredBy` from authenticated subject.

---

#### GAP-AUTH-004: No Token Revocation

**Description**: Access tokens can only be revoked by deleting the entire subject. No selective revocation.

**Impact**: Compromised token requires deleting all permissions for subject.

**Remediation**: Implement token revocation list (jti blacklist).

---

## Cross-Project Comparison

| Feature | Nightscout | AAPS | Loop | xDrip+ |
|---------|------------|------|------|--------|
| **Auth Method** | API Secret + JWT | Access Token | API Secret | SHA1 Secret |
| **Transport** | REST + WebSocket | WebSocket | REST | REST |
| **Token Storage** | MongoDB | Preferences | Keychain | Preferences |
| **Hashing** | SHA1/SHA512 | N/A | N/A | SHA1 |
| **Rate Limiting** | Delay list | N/A | N/A | N/A |
| **Permission Model** | Shiro-Trie | N/A | N/A | N/A |

---

## API Endpoints

### Authorization Management (API v2)

| Endpoint | Method | Permission | Purpose |
|----------|--------|------------|---------|
| `/api/v2/authorization/request/{token}` | GET | - | Exchange token for JWT |
| `/api/v2/authorization/subjects` | GET | admin | List subjects |
| `/api/v2/authorization/subjects` | POST | admin | Create subject |
| `/api/v2/authorization/subjects/{id}` | GET | admin | Get subject |
| `/api/v2/authorization/subjects/{id}` | PUT | admin | Update subject |
| `/api/v2/authorization/subjects/{id}` | DELETE | admin | Delete subject |
| `/api/v2/authorization/subjects/{id}/token` | POST | admin | Generate token |
| `/api/v2/authorization/roles` | GET | admin | List roles |

**Source**: `lib/authorization/endpoints.js`

---

## WebSocket Authentication

### Socket.IO Subscribe Message

```json
{
  "accessToken": "myuploader-a1b2c3d4e5f6"
}
```

### WebSocket Namespaces

| Namespace | Purpose | Events |
|-----------|---------|--------|
| `/storage` | Data sync | `data`, `update` |
| `/alarm` | Alarm notifications | `alarm`, `urgent` |

---

## Best Practices

### For Nightscout Operators

1. **Use access tokens** instead of sharing API_SECRET
2. **Create specific roles** for each client (uploader, viewer, caregiver)
3. **Rotate tokens** periodically
4. **Enable HTTPS** - secrets transmitted in headers
5. **Set AUTH_DEFAULT_ROLES** to restrict anonymous access

### For Client Developers

1. **Store secrets securely** (Keychain, EncryptedSharedPreferences)
2. **Use JWT tokens** for session management
3. **Handle token expiration** gracefully
4. **Implement token refresh** before expiration

---

## References

### Source Files

| File | Purpose |
|------|---------|
| `nightscout:lib/authorization/index.js` | Main authorization logic |
| `nightscout:lib/authorization/storage.js` | Subject/role storage |
| `nightscout:lib/authorization/endpoints.js` | REST endpoints |
| `nightscout:lib/authorization/delaylist.js` | Rate limiting |
| `nightscout:lib/server/enclave.js` | Secret hashing, JWT signing |
| `aaps:plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Service.kt` | AAPS auth |
| `loop:NightscoutService/NightscoutServiceKit/NightscoutService.swift` | Loop auth |
| `xdrip:app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java` | xDrip+ auth |

### Related Documentation

- [Nightscout Security Guide](https://nightscout.github.io/nightscout/security/)
- [API v3 Documentation](https://nightscout.github.io/api/)
