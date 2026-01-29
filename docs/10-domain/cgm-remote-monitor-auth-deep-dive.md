# cgm-remote-monitor Authentication Deep Dive

This document analyzes the authentication and authorization system of cgm-remote-monitor, focusing on the Shiro-style permission model, JWT tokens, API secrets, and role-based access control. The auth layer secures API endpoints and WebSocket connections for the ecosystem.

## Overview

### Key Components

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| Authorization Core | `lib/authorization/index.js` | 321 | Token extraction, permission resolution |
| Storage Layer | `lib/authorization/storage.js` | 272 | Roles, subjects, database ops |
| API Endpoints | `lib/authorization/endpoints.js` | 120 | Subject/role management REST API |
| Rate Limiting | `lib/authorization/delaylist.js` | 59 | IP-based delay after auth failures |
| Enclave | `lib/server/enclave.js` | ~150 | JWT signing, secret hashing |

### Authentication Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Request                               │
│  (Loop, xDrip+, AAPS, Trio, browsers)                               │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Token Extraction                                  │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  1. Authorization: Bearer <JWT>                             │    │
│  │  2. api-secret header                                        │    │
│  │  3. ?secret= query parameter                                 │    │
│  │  4. ?token= query parameter (access token)                   │    │
│  │  5. req.body.secret                                          │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              ┌─────────┐   ┌─────────┐   ┌─────────┐
              │API Secret│   │JWT Token│   │Access   │
              │(admin)   │   │         │   │Token    │
              └────┬─────┘   └────┬────┘   └────┬────┘
                   │              │              │
                   ▼              ▼              ▼
              ┌─────────┐   ┌─────────┐   ┌─────────┐
              │SHA1/512 │   │Verify   │   │Lookup   │
              │Compare  │   │Signature│   │Subject  │
              └────┬────┘   └────┬────┘   └────┬────┘
                   │              │              │
                   ▼              ▼              ▼
              ┌─────────┐   ┌─────────┐   ┌─────────┐
              │Grant *  │   │Extract  │   │Resolve  │
              │(admin)  │   │Claims   │   │Roles    │
              └────┬────┘   └────┬────┘   └────┬────┘
                   │              │              │
                   └──────────────┴──────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Permission Resolution                             │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Roles → Shiro Trie → Check Permission String               │    │
│  │  e.g., "api:treatments:create" matches "*" or "*:*:create"  │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
              ┌─────────┐                 ┌─────────┐
              │Permitted│                 │Denied   │
              │→ next() │                 │→ 401    │
              └─────────┘                 └─────────┘
```

---

## Shiro-Style Permission Model

### Permission String Format

Nightscout uses Apache Shiro-style hierarchical permission strings:

```
[domain]:[collection]:[action]
```

**Examples:**
- `api:treatments:create` - Create treatments
- `api:entries:read` - Read entries
- `admin:api:subjects:delete` - Delete subjects (admin)
- `*` - Full admin access (wildcard)
- `*:*:read` - Read all collections

### Wildcard Matching

| Pattern | Matches |
|---------|---------|
| `*` | Everything |
| `*:*:read` | All read operations |
| `api:*:create` | Create any API resource |
| `api:treatments:*` | All treatment operations |

### Permission Checking

**File**: `lib/authorization/index.js:248-277`

```javascript
authorization.isPermitted = function isPermitted(permission) {
  return async function check(req, res, next) {
    const permissions = await authorization.resolve(data);
    const permitted = authorization.checkMultiple(permission, permissions.shiros);
    if (permitted) {
      next();
    } else {
      res.sendJSONStatus(401, 'Unauthorized');
    }
  };
};
```

**Shiro Trie Library**: Uses `shiro-trie` npm package for efficient hierarchical matching.

---

## Default Roles

**File**: `lib/authorization/storage.js:117-125`

| Role | Permissions | Use Case |
|------|-------------|----------|
| `admin` | `['*']` | Full access |
| `denied` | `[]` | No access |
| `status-only` | `['api:status:read']` | Read status only |
| `readable` | `['*:*:read']` | Read-only access |
| `careportal` | `['api:treatments:create']` | Treatment creation |
| `devicestatus-upload` | `['api:devicestatus:create']` | Device uploads |
| `activity` | `['api:activity:create']` | Activity logs |

### Custom Roles

Custom roles can be created via API:

```
POST /api/v2/authorization/roles
{
  "name": "custom-uploader",
  "permissions": ["api:entries:create", "api:treatments:create"]
}
```

**Requires**: `admin:api:roles:create` permission

---

## API Secret Authentication

### Secret Hashing

**File**: `lib/server/enclave.js`

```javascript
// SHA1 hash (primary)
apiKeySHA1 = crypto.createHash('sha1').update(apiKey).digest('hex');

// SHA512 hash (alternative)
apiKeySHA512 = crypto.createHash('sha512').update(apiKey).digest('hex');

// Verification
isApiKey = function(keyValue) {
  return keyValue.toLowerCase() == secrets[apiKeySHA1] || 
         keyValue == secrets[apiKeySHA512];
};
```

### Secret Extraction

**File**: `lib/authorization/index.js:78-98`

Extraction priority:
1. Query parameter: `?secret=...`
2. HTTP header: `api-secret: ...`
3. Request body: `{ secret: "..." }`

### Admin Bypass

**File**: `lib/authorization/index.js:175-182`

```javascript
if (data.api_secret && authorizeAdminSecret(data.api_secret)) {
  var admin = shiroTrie.new();
  admin.add(['*']);
  return { shiros: [admin] };  // Full admin access
}
```

**Security Note**: API_SECRET grants full admin access, bypassing role-based permissions.

---

## JWT Token System

### Token Generation

**File**: `lib/server/enclave.js`

```javascript
signJWT = function(token, lifetime) {
  return jwt.sign(token, secrets['randomString'], {
    expiresIn: lifetime || '8h'
  });
};
```

**Default Lifetime**: 8 hours

### Token Validation

```javascript
verifyJWT = function(tokenString) {
  try {
    return jwt.verify(tokenString, secrets['randomString']);
  } catch (err) {
    return null;
  }
};
```

### JWT Authorization Flow

**File**: `lib/authorization/endpoints.js`

```
POST /api/v2/authorization/request/:accessToken
                    ↓
          Validate access token
                    ↓
          Load subject and roles
                    ↓
          Generate JWT with permissions
                    ↓
          Return { token, exp, sub }
```

---

## Subject Management

### Subject Structure

```javascript
{
  "_id": ObjectId,
  "name": "my-uploader",
  "roles": ["devicestatus-upload", "careportal"],
  "accessToken": "myuploader-a1b2c3d4e5f6",
  "created_at": ISODate
}
```

### Access Token Format

**File**: `lib/authorization/storage.js`

```
{abbreviated-name}-{digest}
```

- **abbreviated-name**: First 10 chars of subject name (lowercase, alphanumeric)
- **digest**: First 16 chars of SHA1 hash

**Example**: `myuploader-a1b2c3d4e5f6g7h8`

### Subject Creation

```
POST /api/v2/authorization/subjects
{
  "name": "loop-uploader",
  "roles": ["devicestatus-upload", "careportal"]
}
```

**Requires**: `admin:api:subjects:create` permission

### Database Storage

| Collection | Purpose |
|------------|---------|
| `{prefix}subjects` | User/device records with roles |
| `{prefix}roles` | Custom role definitions |

---

## Rate Limiting

### IP-Based Delay

**File**: `lib/authorization/delaylist.js`

```javascript
const DELAY_ON_FAIL = 5000;  // 5 seconds per failure

addDelayForIP(ip) {
  delays[ip] = (delays[ip] || 0) + DELAY_ON_FAIL;
}

shouldDelay(ip) {
  return delays[ip] || 0;
}
```

### Behavior

| Failed Attempts | Delay |
|-----------------|-------|
| 1 | 5 seconds |
| 2 | 10 seconds |
| 3 | 15 seconds |
| N | N × 5 seconds |

**Cleanup**: Entries older than 60 seconds are removed.

---

## API Endpoints

### Authorization Management

| Method | Endpoint | Permission | Purpose |
|--------|----------|------------|---------|
| POST | `/api/v2/authorization/request/:accessToken` | - | Get JWT from access token |
| GET | `/api/v2/authorization/subjects` | `admin:api:subjects:read` | List subjects |
| POST | `/api/v2/authorization/subjects` | `admin:api:subjects:create` | Create subject |
| PUT | `/api/v2/authorization/subjects` | `admin:api:subjects:update` | Update subject |
| DELETE | `/api/v2/authorization/subjects/:_id` | `admin:api:subjects:delete` | Delete subject |
| GET | `/api/v2/authorization/roles` | `admin:api:roles:list` | List roles |
| POST | `/api/v2/authorization/roles` | `admin:api:roles:create` | Create role |

### Data API Permissions

| Operation | Permission | Example Endpoint |
|-----------|------------|------------------|
| Read entries | `api:entries:read` | GET /api/v1/entries |
| Create entries | `api:entries:create` | POST /api/v1/entries |
| Read treatments | `api:treatments:read` | GET /api/v1/treatments |
| Create treatments | `api:treatments:create` | POST /api/v1/treatments |
| Create devicestatus | `api:devicestatus:create` | POST /api/v1/devicestatus |
| Read status | `api:status:read` | GET /api/v1/status |

---

## WebSocket Authentication

**File**: `lib/server/websocket.js`

### Authorize Event

```javascript
socket.on('authorize', function(data, callback) {
  const resolved = await authorization.resolve({
    api_secret: data.secret,
    token: data.token,
    ip: socket.handshake.address
  });
  
  if (resolved.shiros.length > 0) {
    socket.join('DataReceivers');
    socket.emit('connected');
  }
});
```

### Write Permissions

WebSocket write operations check specific permissions:
- `dbAdd` → `api:{collection}:create`
- `dbUpdate` → `api:{collection}:update`
- `dbRemove` → `api:{collection}:delete`

---

## Gap Analysis

### GAP-AUTH-003: API_SECRET Grants Full Admin Access

**Scenario**: Any client with API_SECRET can perform admin operations.

**Issue**: API_SECRET bypasses role-based access control entirely. A compromised secret exposes all administrative functions.

**Affected Systems**: All Nightscout instances.

**Impact**: No granular access control for API_SECRET holders.

**Remediation**: Consider deprecating API_SECRET for write operations; require subject tokens with explicit roles.

---

### GAP-AUTH-004: No Token Revocation Mechanism

**Scenario**: Compromised access token needs to be invalidated.

**Issue**: Access tokens have no revocation endpoint. Deleting a subject is the only way to invalidate a token.

**Affected Systems**: All clients using access tokens.

**Impact**: Compromised tokens remain valid until subject deletion.

**Remediation**: Add token revocation API and blacklist mechanism.

---

### GAP-AUTH-005: JWT Secret Stored in Node Modules

**Scenario**: JWT signing key location.

**Issue**: JWT secret is stored in `node_modules/.cache/_ns_cache/randomString`, which may be cleared during updates.

**Affected Systems**: All Nightscout instances using JWT.

**Impact**: JWT secret loss invalidates all issued tokens.

**Remediation**: Store JWT secret in persistent location (environment variable or database).

---

## Recommendations

### 1. Document Permission Strings

Create comprehensive list of all permission strings used across API endpoints for client developers.

**Priority**: High

### 2. Add Token Revocation

Implement `/api/v2/authorization/revoke` endpoint to invalidate tokens:
```
POST /api/v2/authorization/revoke
{ "accessToken": "..." }
```

**Priority**: High

### 3. Deprecate API_SECRET for Writes

Recommend subject tokens for write operations; API_SECRET for read-only or legacy compatibility.

**Priority**: Medium

### 4. Document Role Requirements per Endpoint

Update OpenAPI spec with required permissions per endpoint using `x-required-permission` extension.

**Priority**: Medium

---

## Source Files Analyzed

| File | Lines | Key Content |
|------|-------|-------------|
| `lib/authorization/index.js` | 321 | Permission resolution, middleware |
| `lib/authorization/storage.js` | 272 | Roles, subjects, database |
| `lib/authorization/endpoints.js` | 120 | REST API for auth management |
| `lib/authorization/delaylist.js` | 59 | Rate limiting |
| `lib/server/enclave.js` | ~150 | JWT signing, secret hashing |
| `lib/server/websocket.js` | 649 | Socket.IO auth |

---

## Cross-References

- **API Layer**: [cgm-remote-monitor-api-deep-dive.md](./cgm-remote-monitor-api-deep-dive.md)
- **Sync Layer**: [cgm-remote-monitor-sync-deep-dive.md](./cgm-remote-monitor-sync-deep-dive.md)
- **Terminology**: [terminology-matrix.md](../../mapping/cross-project/terminology-matrix.md)
