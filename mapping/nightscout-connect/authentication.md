# nightscout-connect: Authentication Patterns

**Source**: `externals/nightscout-connect`  
**Verified**: 2026-01-20

## Authentication Flow

nightscout-connect implements a multi-step authentication strategy with fallback.

### Step 1: Verify Existing Auth

```javascript
// lib/sources/nightscout.js:40
GET /api/v1/verifyauth
```

If already readable, use existing credentials.

### Step 2: Create Reader Subject (if needed)

```javascript
// lib/sources/nightscout.js:55-68
POST /api/v2/authorization/subjects
Body: { name: "nightscout-connect-reader", role: "readable" }
Header: API-SECRET (SHA1 hashed)
```

### Step 3: Get JWT Bearer Token

```javascript
// lib/sources/nightscout.js:92-104
GET /api/v2/authorization/request/<token>
Returns: JWT with exp/iat claims
```

## Credential Handling

### API Secret Hashing

```javascript
// lib/sources/nightscout.js:10-14
const crypto = require('crypto');
const hash = crypto.createHash('sha1');
hash.update(apiSecret);
const hashedSecret = hash.digest('hex');
```

**Always SHA1 hashed before transmission** in `API-SECRET` header.

### Token Query Parameter

Alternative authentication via URL:
```javascript
// lib/sources/nightscout.js:42
?token=<subject>
```

## Session Management

### Bearer Token Usage

```javascript
// lib/sources/nightscout.js:135-136
Authorization: Bearer <jwt>
```

### Token Refresh

- TTL tracked: `(exp - iat) * 1000` milliseconds
- 28.8-hour refresh cycle
- Automatic re-authentication before expiry

## Security Notes

1. API secrets are **never transmitted in plain text**
2. SHA1 hash is standard across Nightscout ecosystem
3. JWT tokens have limited TTL
4. Subject-based access allows revocation

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-NC-AUTH-001 | API secret must be SHA1 hashed | `lib/sources/nightscout.js:10-14` |
| REQ-NC-AUTH-002 | Must support v2 JWT bearer auth | `lib/sources/nightscout.js:92` |
| REQ-NC-AUTH-003 | Must refresh tokens before expiry | `lib/sources/nightscout.js:161-164` |
