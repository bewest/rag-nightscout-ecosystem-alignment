# cgm-remote-monitor: Authorization System

**Source**: `externals/cgm-remote-monitor` (wip/bewest/mongodb-5x)  
**Verified**: 2026-01-20

## Authentication Methods

### 1. API-SECRET (Legacy)

Per `lib/server/enclave.js:32-52`:

```javascript
// Hash generation
function genHash(data) {
  return crypto.createHash('sha1').update(data).digest('hex');
}

// Validation accepts both SHA1 and SHA512
function isApiKey(secret) {
  return secret === sha1Hash || secret === sha512Hash;
}
```

**Transmission**:
- Header: `API-SECRET` or `api-secret`
- Query: `?secret=...`
- Body: `{ secret: "..." }`

### 2. JWT Bearer Token

Per `lib/server/enclave.js:58-69`:

```javascript
// Signing (default 8 hour lifetime)
function signJWT(token, lifetime) {
  return jwt.sign(token, jwtSecret, { expiresIn: lifetime || '8h' });
}

// Verification
function verifyJWT(tokenString) {
  return jwt.verify(tokenString, jwtSecret);
}
```

**Transmission**:
- Header: `Authorization: Bearer <token>`
- Query: `?token=...`

### 3. Access Token → JWT Exchange

Per `lib/authorization/index.js:284-313`:

```javascript
function authorize(accessToken) {
  const subject = storage.findSubject(accessToken);
  const jwt = enclave.signJWT({ subject: subject.name, accessToken });
  return { token: jwt, sub: subject.name, ... };
}
```

## Permission Model

### Shiro-Trie Permissions

Format: `resource:action:scope`

Examples:
- `api:entries:read` - Read entries
- `api:treatments:create` - Create treatments
- `*:*:read` - Read all resources

### Default Roles

Per `lib/authorization/storage.js:117-125`:

| Role | Permissions |
|------|-------------|
| `admin` | `['*']` - Full access |
| `denied` | `[]` - No access |
| `status-only` | `['api:status:read']` |
| `readable` | `['*:*:read']` |
| `careportal` | `['api:treatments:create']` |
| `devicestatus-upload` | `['api:devicestatus:create']` |
| `activity` | `['api:activity:create']` |

## Token Management

### Access Token Format

Per `lib/authorization/storage.js:167-176`:

```javascript
// Format: {abbrev}-{digest_prefix}
// Example: "myapp-a1b2c3d4e5f6g7h8"

function generateAccessToken(subject) {
  const abbrev = subject.name.substring(0, 8);
  const random = crypto.randomBytes(16).toString('hex');
  const digest = crypto.createHash('sha1').update(random).digest('hex');
  return abbrev + '-' + digest.substring(0, 16);
}
```

### Token Storage

Per `lib/authorization/storage.js:172`:

Tokens are stored as SHA1 digests, not plain text.

## Authorization Flow

Per `lib/authorization/index.js:144-220`:

```
1. extractJWTfromRequest() - Check for Bearer token
   ↓ Found?
2. verifyJWT() - Validate signature
   ↓ Valid?
3. Return subject + permissions
   ↓ Not found?
4. apiSecretFromRequest() - Check for API-SECRET
   ↓ Found?
5. isApiKey() - Validate against stored hash
   ↓ Valid?
6. Return admin permissions
   ↓ Not valid?
7. Rate limit check (delaylist)
   ↓
8. Return denied
```

## Rate Limiting

Per `lib/authorization/delaylist.js`:

- Tracks failed auth attempts by IP
- Default delay: 5 seconds
- Applied during `resolve()` at lines 157-161

## Endpoints

Per `lib/authorization/endpoints.js`:

| Endpoint | Method | Permission |
|----------|--------|------------|
| `/request/:accessToken` | GET | None (public) |
| `/subjects` | GET | `admin:api:subjects:read` |
| `/subjects` | POST | `admin:api:subjects:create` |
| `/subjects` | PUT | `admin:api:subjects:update` |
| `/subjects/:_id` | DELETE | `admin:api:subjects:delete` |
| `/roles` | GET | `admin:api:roles:list` |
| `/roles` | POST | `admin:api:roles:create` |
| `/permissions` | GET | `admin:api:permissions:read` |

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-NS-AUTH-001 | Must accept SHA1-hashed API-SECRET | `enclave.js:50-52` |
| REQ-NS-AUTH-002 | Must support JWT Bearer tokens | `enclave.js:58-69` |
| REQ-NS-AUTH-003 | JWT default lifetime must be 8 hours | `enclave.js:59` |
| REQ-NS-AUTH-004 | Must rate limit failed auth attempts | `delaylist.js` |
| REQ-NS-AUTH-005 | Access tokens must be stored as hashes | `storage.js:172` |

## Gaps Identified

| ID | Gap | Impact |
|----|-----|--------|
| GAP-AUTH-001 | `enteredBy` field is unverified | Any client can claim any identity |
| GAP-AUTH-002 | No authority hierarchy | All valid tokens have equal trust |
