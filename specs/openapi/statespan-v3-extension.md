# StateSpan V3 Extension Specification

> **Date**: 2026-02-01  
> **Status**: Draft (Reference Implementation)  
> **Target**: cgm-remote-monitor maintainers  
> **Related**: [statespan-standardization-proposal.md](../docs/sdqctl-proposals/statespan-standardization-proposal.md)

---

## ⚠️ Important Context

**Nocturne author preference**: StateSpan should remain V4-only.

This specification documents a **hypothetical V3 extension** for reference purposes. It is provided for:
1. cgm-remote-monitor maintainers evaluating future additions
2. AID app developers planning client implementations
3. API designers considering time-range state patterns

**This is NOT an official recommendation or approved roadmap.**

---

## Executive Summary

This specification defines how StateSpan functionality could be added to the Nightscout V3 API as a backward-compatible extension, enabling time-ranged state tracking without requiring full V4 adoption.

### Scope

| In Scope | Out of Scope |
|----------|--------------|
| Profile state spans | User activity annotations (Sleep, Exercise) |
| Override/TempTarget spans | Full V4 parity |
| TempBasal spans | Breaking changes to treatments |
| PumpMode spans | Migration tooling |

---

## V3 Extension Endpoints

### Base Path

All StateSpan V3 endpoints use the `/api/v3/state-spans` prefix.

### Feature Detection

Clients MUST detect StateSpan V3 support before use:

```http
GET /api/v3/state-spans/status
```

**Response** (if available):
```json
{
  "status": 200,
  "result": {
    "supported": true,
    "version": "3.1.0",
    "categories": ["Profile", "Override", "TempBasal", "PumpMode"]
  }
}
```

**Response** (if not available):
```json
{
  "status": 404,
  "result": "StateSpan extension not enabled"
}
```

---

## Endpoints

### GET /api/v3/state-spans

Query state spans with filtering.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | No | Filter by category (Profile, Override, etc.) |
| `from` | number | No | Start of time range (epoch ms) |
| `to` | number | No | End of time range (epoch ms) |
| `active` | boolean | No | Only return currently active spans |
| `limit` | number | No | Max results (default: 100) |

**Example Request**:
```http
GET /api/v3/state-spans?category=Profile&from=1706745600000&to=1706832000000
Authorization: Bearer {token}
```

**Response**:
```json
{
  "status": 200,
  "result": [
    {
      "identifier": "uuid-1",
      "category": "Profile",
      "state": "Active",
      "startMills": 1706745600000,
      "endMills": 1706788800000,
      "source": "Loop",
      "metadata": {
        "profileName": "Weekday",
        "percentage": 100,
        "timeshift": 0
      },
      "srvCreated": 1706745600000,
      "srvModified": 1706745600000
    }
  ]
}
```

### GET /api/v3/state-spans/{identifier}

Get a single state span by identifier.

**Response**:
```json
{
  "status": 200,
  "result": {
    "identifier": "uuid-1",
    "category": "Profile",
    "state": "Active",
    "startMills": 1706745600000,
    "endMills": null,
    "source": "Loop",
    "metadata": {
      "profileName": "Active"
    }
  }
}
```

### GET /api/v3/state-spans/active

Get currently active spans (endMills is null or in future).

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | No | Filter by category |

**Example**:
```http
GET /api/v3/state-spans/active?category=Override
```

### POST /api/v3/state-spans

Create a new state span.

**Request Body**:
```json
{
  "category": "Override",
  "state": "Custom",
  "startMills": 1706832000000,
  "endMills": 1706835600000,
  "source": "AAPS",
  "metadata": {
    "insulinNeedsScaleFactor": 0.8,
    "targetTop": 140,
    "targetBottom": 100,
    "reason": "Exercise"
  }
}
```

**Response**:
```json
{
  "status": 201,
  "result": {
    "identifier": "uuid-new",
    "isDeduplication": false
  }
}
```

### PUT /api/v3/state-spans/{identifier}

Update an existing state span (primarily for ending active spans).

**Request Body**:
```json
{
  "endMills": 1706835600000
}
```

### DELETE /api/v3/state-spans/{identifier}

Delete a state span (soft delete by default).

---

## Data Model

### StateSpan Schema

```yaml
StateSpan:
  type: object
  required:
    - category
    - state
    - startMills
    - source
  properties:
    identifier:
      type: string
      description: Unique identifier (UUID)
    category:
      type: string
      enum: [Profile, Override, TempBasal, PumpMode]
      description: StateSpan category
    state:
      type: string
      description: State value within category
    startMills:
      type: integer
      format: int64
      description: Start time in epoch milliseconds
    endMills:
      type: integer
      format: int64
      nullable: true
      description: End time (null = currently active)
    source:
      type: string
      description: Data source identifier
    metadata:
      type: object
      additionalProperties: true
      description: Category-specific data
    syncIdentifier:
      type: string
      description: Client-provided deduplication identifier
    srvCreated:
      type: integer
      format: int64
      description: Server creation timestamp
    srvModified:
      type: integer
      format: int64
      description: Server modification timestamp
```

### Category-Specific Metadata

#### Profile

```json
{
  "profileName": "Weekday",
  "percentage": 100,
  "timeshift": 0
}
```

#### Override

```json
{
  "insulinNeedsScaleFactor": 0.8,
  "targetTop": 140,
  "targetBottom": 100,
  "reason": "Exercise",
  "originalTreatmentId": "treatment-uuid"
}
```

#### TempBasal

```json
{
  "rate": 1.5,
  "percent": 150,
  "durationMins": 60,
  "isAbsolute": true
}
```

#### PumpMode

```json
{
  "mode": "Automatic",
  "controller": "Loop",
  "reason": "User initiated"
}
```

---

## Backward Compatibility

### Treatment Translation

The V3 extension SHOULD auto-translate treatment writes to StateSpans:

| Treatment eventType | StateSpan Category | Translation |
|---------------------|-------------------|-------------|
| `Profile Switch` | `Profile` | Create span, end previous |
| `Temporary Override` | `Override` | Create span with duration |
| `Temporary Override Cancel` | `Override` | End active override span |
| `Temp Basal` | `TempBasal` | Create span with duration |
| `Temporary Target` | `Override` | Create span (AAPS pattern) |
| `OpenAPS Offline` | `PumpMode` | Create span with state=Manual |

### Query Fallback

If a client queries state-spans but the extension is unavailable:
1. Return 404 with clear message
2. Client falls back to treatment queries
3. Client calculates time ranges locally

### Dual Write Pattern

During migration, write to BOTH:
1. Traditional treatments collection (for legacy clients)
2. New state-spans collection (for V3+ clients)

---

## Implementation Notes

### MongoDB Collection

```javascript
db.createCollection("statespans", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["category", "state", "startMills", "source"],
      properties: {
        category: { enum: ["Profile", "Override", "TempBasal", "PumpMode"] },
        startMills: { bsonType: "long" },
        endMills: { bsonType: ["long", "null"] }
      }
    }
  }
});

// Index for time-range queries
db.statespans.createIndex({ category: 1, startMills: -1, endMills: 1 });

// Index for active span queries
db.statespans.createIndex({ category: 1, endMills: 1 });
```

### Express Route Registration

```javascript
// lib/api3/index.js
const stateSpans = require('./state-spans');
app.use('/api/v3/state-spans', stateSpans(env, ctx));
```

---

## Client Implementation Examples

### Swift (NightscoutKit)

```swift
extension NightscoutClient {
    func getStateSpans(
        category: StateSpanCategory,
        from: Date,
        to: Date
    ) async throws -> [StateSpan] {
        // Check V3 extension availability
        guard await supportsStateSpansV3() else {
            // Fall back to treatment-based calculation
            return try await getStateSapnsFromTreatments(category, from, to)
        }
        
        let url = baseURL.appendingPathComponent("api/v3/state-spans")
        var components = URLComponents(url: url, resolvingAgainstBaseURL: true)!
        components.queryItems = [
            URLQueryItem(name: "category", value: category.rawValue),
            URLQueryItem(name: "from", value: String(from.timeIntervalSince1970 * 1000)),
            URLQueryItem(name: "to", value: String(to.timeIntervalSince1970 * 1000))
        ]
        
        return try await fetch(components.url!)
    }
}
```

### Kotlin (AAPS)

```kotlin
interface NightscoutApi {
    @GET("api/v3/state-spans")
    suspend fun getStateSpans(
        @Query("category") category: String,
        @Query("from") from: Long,
        @Query("to") to: Long
    ): Response<List<StateSpan>>
    
    @GET("api/v3/state-spans/status")
    suspend fun getStateSpanStatus(): Response<StateSpanStatus>
}

// Feature detection
suspend fun supportsStateSpansV3(): Boolean {
    return try {
        api.getStateSpanStatus().isSuccessful
    } catch (e: Exception) {
        false
    }
}
```

---

## Migration Path

### Phase 1: Read-Only (Months 1-3)

1. Add `statespans` collection
2. Implement `GET /api/v3/state-spans` endpoints
3. Background job translates existing treatments to spans
4. Clients can query but still write treatments

### Phase 2: Dual Write (Months 4-6)

1. Treatment POST creates corresponding StateSpan
2. StateSpan POST creates corresponding treatment
3. Both collections stay in sync
4. Clients begin testing native StateSpan writes

### Phase 3: StateSpan Primary (Months 7-12)

1. StateSpan becomes primary for time-range queries
2. Treatments remain for backward compatibility
3. New clients use StateSpan exclusively
4. Deprecation warnings on treatment-based queries

### Phase 4: Treatment Sunset (Year 2+)

1. Treatment writes still supported
2. Treatment reads deprecated
3. Migration tooling removes treatment dependency
4. cgm-remote-monitor v16+ removes dual write

---

## Comparison: V3 Extension vs V4 Native

| Aspect | V3 Extension | V4 Native (Nocturne) |
|--------|--------------|----------------------|
| **Availability** | cgm-remote-monitor + Nocturne | Nocturne only |
| **Categories** | 4 core | 9+ including user activities |
| **Backward compat** | Full (treatments continue) | Limited |
| **Response format** | V3 standard | V4 format |
| **Feature detection** | `/api/v3/state-spans/status` | `/api/v4/version` |
| **Implementation** | Community PR | Already done |

---

## Gap References

| Gap ID | Description | Status |
|--------|-------------|--------|
| GAP-V4-001 | StateSpan API not standardized | This spec addresses |
| GAP-V4-002 | Profile history not queryable | Addressed by Profile category |
| GAP-NOCTURNE-001 | V4 endpoints Nocturne-specific | V3 extension provides alternative |

---

## Related Documents

| Document | Relationship |
|----------|--------------|
| [statespan-standardization-proposal.md](../docs/sdqctl-proposals/statespan-standardization-proposal.md) | Parent proposal |
| [nightscout-v4-integration-proposal.md](../docs/sdqctl-proposals/nightscout-v4-integration-proposal.md) | V4 context |
| [nocturne-v4-extension.yaml](nocturne-v4-extension.yaml) | V4 OpenAPI spec |
| [aid-treatments-2025.yaml](aid-treatments-2025.yaml) | Current treatment model |
