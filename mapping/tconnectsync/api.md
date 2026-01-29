# tconnectsync API Reference

> **Source**: `externals/tconnectsync/tconnectsync/api/`  
> **Last Updated**: 2026-01-29

Documentation of t:connect API endpoints and authentication methods used by tconnectsync.

---

## Authentication Methods

### 1. OIDC/OAuth2 (tandemsource.py)

**File**: `api/tandemsource.py` (455 lines)

| Aspect | Details |
|--------|---------|
| Flow | PKCE Authorization Code |
| Token Type | JWT |
| Regions | US, EU |
| Endpoints | Tandem identity services |

```
Authorization Flow:
1. Generate PKCE code_verifier + code_challenge
2. Redirect to authorize endpoint
3. Exchange code for tokens
4. Validate JWT signature
5. Refresh as needed
```

### 2. Android Credentials (android.py)

**File**: `api/android.py` (175 lines)

| Aspect | Details |
|--------|---------|
| Flow | Password Grant |
| Credentials | Base64 embedded client secret |
| Scope | Cloud settings access |

### 3. Web Form Auth (controliq.py)

**File**: `api/controliq.py` (206 lines)

| Aspect | Details |
|--------|---------|
| Flow | Form POST login |
| Cookie | `UserGUID` extracted |
| Session | Maintained for subsequent requests |

---

## API Endpoints

### Control-IQ APIs

**Base**: `https://tdcservices.tandemdiabetes.com`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/tconnect/controliq/api/therapytimeline/users/{userGuid}` | GET | Therapy timeline events |
| `/tconnect/controliq/api/summary/users/{userGuid}` | GET | Daily summary stats |
| `/tconnect/controliq/api/pumpfeatures/users/{userGuid}` | GET | Control-IQ feature settings |

**Query Parameters**:
- `startDate`: ISO date (YYYY-MM-DD)
- `endDate`: ISO date (YYYY-MM-DD)

### Therapy Events APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/tconnect/therapyevents/api/TherapyEvents/{start}/{end}/false` | GET | Therapy events |

**Query Parameters**:
- `userId`: User GUID

### Cloud Settings APIs (Android)

**Base**: `https://tdccloud.tandemdiabetes.com`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/cloud/usersettings/api/therapythresholds` | GET | Alert thresholds |
| `/cloud/usersettings/api/UserProfile` | GET | User profile |
| `/cloud/account/patient_info` | GET | Patient information |
| `/cloud/upload/getlasteventuploaded` | GET | Last sync timestamp |

**Query Parameters**:
- `userId`: User ID
- `sn`: Pump serial number

### Historical Data APIs (WS2)

**File**: `api/ws2.py` (174 lines)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/therapytimeline2csv/{userGuid}/{start}/{end}` | GET | CSV export |
| `/basalsuspension/{userGuid}/{start}/{end}/{filter}` | GET | Suspension events |
| `/basaliqtech/{userGuid}/{start}/{end}` | GET | Basal-IQ events |

**Query Parameters**:
- `format`: `csv` or `jsonp`

---

## Response Structures

### Therapy Timeline Response

```json
{
  "events": [
    {
      "type": "bolus",
      "timestamp": "2026-01-29T10:30:00Z",
      "data": {
        "requestedUnits": 2.5,
        "deliveredUnits": 2.5,
        "carbsEntered": 30,
        "bgValue": 145
      }
    },
    {
      "type": "basal",
      "timestamp": "2026-01-29T11:00:00Z",
      "data": {
        "rate": 0.8,
        "duration": 60,
        "reason": "Control-IQ"
      }
    }
  ]
}
```

### Profile Response

```json
{
  "activeProfile": "Default",
  "profiles": {
    "Default": {
      "segments": [
        {
          "time": "00:00",
          "basalRate": 0.5,
          "carbRatio": 10,
          "correctionFactor": 50,
          "targetBG": 110
        }
      ]
    }
  }
}
```

---

## Error Handling

| HTTP Code | Meaning | tconnectsync Behavior |
|-----------|---------|----------------------|
| 401 | Unauthorized | Retry with token refresh |
| 403 | Forbidden | Log error, skip |
| 404 | Not Found | Log warning, continue |
| 429 | Rate Limited | Exponential backoff |
| 500+ | Server Error | Retry with delay |

---

## Rate Limits

| API | Limit | Notes |
|-----|-------|-------|
| Control-IQ | Unknown | Undocumented |
| Cloud Settings | Unknown | Undocumented |
| WS2 Export | Unknown | Large date ranges may timeout |

**Best Practice**: Use reasonable date ranges (7-30 days) for batch sync.

---

## Region Support

| Region | Identity URL | API URL |
|--------|--------------|---------|
| US | `identity.tandemdiabetes.com` | `tdcservices.tandemdiabetes.com` |
| EU | `identity-eu.tandemdiabetes.com` | `tdcservices-eu.tandemdiabetes.com` |

---

## Cross-References

- [Nocturne TConnect Connector](../nocturne/connectors.md)
- [tconnectsync Deep Dive](../../docs/10-domain/tconnectsync-deep-dive.md)
