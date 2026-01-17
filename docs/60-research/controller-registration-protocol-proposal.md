# Proposal: Controller Registration Protocol

**Status:** Draft v2  
**Author:** Agent  
**Date:** 2026-01-17 (Updated)  
**Target Repository:** `nightscout/cgm-remote-monitor` (Nightscout Core)  
**Related:** [GAP-003](../../traceability/gaps.md#gap-003-no-unified-sync-identity-field-across-controllers), [Authority Model](../10-domain/authority-model.md), [CGM Remote Monitor Source Synthesis](./cgm-remote-monitor-source-synthesis.md)

---

## Executive Summary

This proposal introduces a **Controller Registration Protocol** as a formal API contract between Nightscout Core (`cgm-remote-monitor`) and AID controller applications. Instead of Nightscout passively accepting whatever data controllers send, controllers formally register their identity schemas, sync conventions, and capabilities.

**Key Design Decision:** This protocol should live in **Nightscout Core** (`cgm-remote-monitor`), not in the Nightscout Roles Gateway (NRG) or a separate federated registry. This ensures:

1. **Single contract** — One authoritative specification that all teams can reference
2. **Atomic deployment** — Registration and data storage in the same system
3. **Lower barrier** — Works with any Nightscout instance without additional infrastructure
4. **Clear ownership** — Nightscout Foundation maintains the contract with controller teams

The protocol enables:

1. **Verified identity** — Controllers authenticate and register, replacing unverified `enteredBy`
2. **Schema commitment** — Controllers declare what fields they use and how
3. **Authority delegation** — Controllers can receive delegated authority from users
4. **Conflict resolution** — Nightscout can enforce authority hierarchy based on registration

---

## Why Nightscout Core (Not NRG or Federated)

### Stakeholder Alignment

Based on ecosystem feedback, controller teams prefer a solution that:

| Requirement | NRG Approach | Federated Registry | **Nightscout Core** |
|-------------|--------------|-------------------|---------------------|
| Single source of truth | ❌ Requires NRG deployment | ⚠️ Central dependency | ✅ Every NS instance |
| Works with existing NS | ⚠️ Requires proxy layer | ⚠️ Requires network access | ✅ Native |
| Controller teams can test locally | ❌ Complex setup | ❌ Depends on external service | ✅ `npm start` |
| Clear API contract | ⚠️ Separate from data API | ⚠️ Separate service | ✅ Same OpenAPI spec |
| Maintainable by NS Foundation | ⚠️ Different codebase | ⚠️ Additional service | ✅ Same codebase |

### Technical Alignment with Existing API v3

The proposed registration endpoints follow existing patterns in `cgm-remote-monitor`:

| Existing Pattern | Source Location | Registration Analog |
|------------------|-----------------|---------------------|
| Generic collection CRUD | `lib/api3/generic/setup.js` | `/api/v3/controllers` collection |
| Bearer token auth | `lib/api3/security.js` | Controller tokens |
| `subject` field injection | `lib/api3/generic/create/operation.js` | `controllerId` injection |
| Shiro permissions | `lib/authorization/index.js` | `api:controllers:*` permissions |
| Soft delete (`isValid`) | `lib/api3/generic/delete/operation.js` | Controller revocation |

---

## Problem Statement

### Current State

Nightscout operates as a "dumb store" that accepts data from any authenticated client:

1. **No identity verification** — `enteredBy` is a free-form string anyone can set
2. **No schema commitment** — Controllers use different fields for the same concepts
3. **No authority model** — All authenticated writes are treated equally
4. **No capability discovery** — Consumers cannot know what a controller uploads

### Source Code Evidence

**Upsert-by-default (no identity check):**
```javascript
// lib/server/treatments.js:42-46
var query = {
  created_at: results.created_at,
  eventType: obj.eventType
};
api().replaceOne(query, obj, {upsert: true}, ...)
```

**Free-form `enteredBy` (no validation):**
```javascript
// lib/server/treatments.js - enteredBy is indexed but never validated
indexedFields: [
  'created_at', 'eventType', 'insulin', 'carbs',
  'glucose', 'enteredBy', 'boluscalc.foods._id', ...
]
```

**WebSocket dedup relies on unverified fields:**
```javascript
// lib/server/websocket.js - Deduplication uses NSCLIENT_ID or timestamp matching
var query_similiar = {
  created_at: { 
    $gte: new Date(timestamp - 2000).toISOString(), 
    $lte: new Date(timestamp + 2000).toISOString() 
  }
};
// Plus matching: insulin, carbs, percent, absolute, duration, NSCLIENT_ID
```

### Evidence from Gap Analysis

| Gap | Description | Source Evidence | Registration Helps |
|-----|-------------|-----------------|-------------------|
| GAP-003 | No unified sync identity field | Controllers use `syncIdentifier`, `identifier`, `enteredBy`, `uuid` variously | Controllers register their identity field |
| GAP-AUTH-001 | `enteredBy` is unverified | No validation in `treatments.js` | Controllers authenticate at registration |
| GAP-AUTH-002 | No authority hierarchy | All writes treated equally in `websocket.js` | Authority granted based on registration |
| GAP-SYNC-004 | Override supersession not tracked | No `supersedes` field in schema | Controllers commit to lifecycle events |

---

## Current Controller Identity Strategies

Before defining the registration protocol, we must understand how each controller currently identifies its data:

### Identity Strategy Matrix

| Controller | API Version | Primary ID Field | Secondary Fields | Dedup Strategy | Source Reference |
|------------|-------------|------------------|------------------|----------------|------------------|
| **Loop** | v1 | `syncIdentifier` (UUID) | `pumpId`, `pumpType`, `pumpSerial` | Server-side POST | `loop:DoseEntry.swift#L39` |
| **AAPS** | v3 | `identifier` (UUID) | `pumpId` + `pumpType` + `pumpSerial` composite | Client + server | `aaps:InterfaceIDs.kt` |
| **Trio** | v1 | `enteredBy: "Trio"` | None | Server-side POST + `$ne` filter on download | `trio:NightscoutTreatment.swift#L31` |
| **xDrip** | v1 | `uuid` | None | Client-assigned UUID | WebSocket `NSCLIENT_ID` |
| **OpenAPS** | v1 | `enteredBy` | None | Relies on server dedup | Bash scripts |

### DeviceStatus Namespace Patterns

| Controller | `device` Field Format | Devicestatus Namespace | Prediction Format |
|------------|----------------------|------------------------|-------------------|
| **Loop** | `loop://iPhone` | `loop` | Single `predicted.values[]` array |
| **AAPS** | `openaps://phoneModel` | `openaps` | Separate `predBGs.IOB[]`, `COB[]`, `UAM[]`, `ZT[]` |
| **Trio** | `"Trio"` | `openaps` | Separate `predBGs.*` arrays |
| **OpenAPS** | `openaps://hostname` | `openaps` | Separate `predBGs.*` arrays |

### Current Field Usage Inconsistencies

| Concept | Loop | AAPS | Trio |
|---------|------|------|------|
| Bolus insulin | `amount` | `insulin` | `insulin` |
| Duration unit | seconds | minutes | seconds |
| SMB indicator | `automatic: true` | `type: "SMB"` | `enteredBy` contains "SMB" |
| Sync ID field | `syncIdentifier` | `identifier` | (none) |
| Override ID | UUID in `_id` | `identifier` | (none standard) |

---

## Proposed Solution

### Core Concept: Inversion of Control

Instead of Nightscout accepting any data structure:

```
Current:  Controller → (any data) → Nightscout (accepts all)
Proposed: Controller → Register → Nightscout validates → Accept conforming data
```

### Registration as API v3 Collection

Following the existing `lib/api3/generic/setup.js` pattern, add a new `controllers` collection:

```
/api/v3/controllers          # CRUD for controller registrations
/api/v3/controllers/{id}     # Individual controller operations
/api/v3/controllers/history/{timestamp}  # Registration change history
```

### Registration Flow

```
┌─────────────────┐     1. POST Registration    ┌─────────────────┐
│   Controller    │ ─────────────────────────→  │   Nightscout    │
│   (e.g., Loop)  │                             │   /api/v3/      │
└─────────────────┘                             │   controllers   │
                                                └────────┬────────┘
                                                         │
                                                2. Validate & Store
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │   MongoDB       │
                                                │   controllers   │
                                                │   collection    │
                                                └────────┬────────┘
                                                         │
                                                3. Return registration
                                                   with server-assigned
                                                   `identifier`
                                                         │
                                                         ▼
┌─────────────────┐     4. Use existing token   ┌─────────────────┐
│   Controller    │ ─────────────────────────→  │   Nightscout    │
│   (e.g., Loop)  │     with verified identity  │   Data API      │
└─────────────────┘                             └─────────────────┘
```

### Registration Document Schema

Controllers submit a registration document describing their identity and conventions:

```yaml
ControllerRegistration:
  # Server-managed (immutable after creation)
  identifier: "abc123"              # Server-assigned, like other v3 docs
  srvCreated: 1705000000000
  srvModified: 1705000100000
  isValid: true                     # false = revoked
  
  # Controller Identity (client-provided)
  controllerId: "loop-ios"          # Unique controller type identifier
  controllerName: "Loop"            # Human-readable name
  controllerVersion: "3.4.0"        # Semantic version
  platform: "iOS"                   # ios, android, linux, web
  
  # Authentication Binding
  # Links registration to authorization subject
  # Subject resolution uses existing lib/authorization/index.js:
  #   - For JWT: decoded from accessToken claim
  #   - For opaque access tokens: resolved via authorization.resolve()
  #   - For API_SECRET: synthetic subject "api-secret-{sha1-hash-prefix}"
  boundSubject: "loop-user-token-subject"  # From existing auth resolution
  
  # Sync Identity Strategy
  identityStrategy:
    type: "uuid"                    # uuid, composite, timestamp
    field: "syncIdentifier"         # Field name used in uploads
    scope: "per-record"             # per-record, per-device, per-user
    
    # For composite type:
    compositeFields:                # Optional, for type: composite
      - "pumpId"
      - "pumpType"
      - "pumpSerial"
  
  # Data Commitments
  uploads:
    treatments:
      eventTypes:                   # Committed eventType values
        - "Correction Bolus"
        - "Meal Bolus"
        - "Temp Basal"
        - "Temporary Override"
        - "Suspend Pump"
      
      fields:                       # Field schema commitments
        - name: "syncIdentifier"
          type: "uuid"
          required: true
        - name: "automatic"
          type: "boolean"
          required: false
          default: false
        - name: "insulin"
          type: "number"
          unit: "units"
        - name: "duration"
          type: "number"
          unit: "seconds"           # vs milliseconds
      
      lifecycleEvents:
        supersession: false         # Tracks override supersession
        edits: true                 # Syncs treatment edits
        deletions: false            # Syncs deletions (soft delete)
    
    entries:
      enabled: true
      types: ["sgv", "mbg", "cal"]
    
    devicestatus:
      namespace: "loop"             # Top-level key in devicestatus
      predictionFormat: "single-array"  # vs "separate-arrays"
      predictionFields: ["values"]  # vs ["IOB", "COB", "UAM", "ZT"]
      effectTimelines: false        # Uploads insulin/carb effect curves
      
    profile:
      enabled: true
      format: "nightscout-v1"       # Profile schema version
  
  # Capabilities Declaration
  capabilities:
    remoteCommands: true
    remoteOverrides: true
    remoteBolus: true
    remoteCarbs: true
    websocket: false                # Uses WebSocket for real-time
    apiVersion: "v1"                # Primary API version used
    
    otpRequired:                    # OTP requirements for remote commands
      overrides: false
      bolus: true
      carbs: true
  
  # Authority Request
  authorityRequest:
    level: "controller"             # 30 in authority hierarchy
    scopes:                         # Requested Shiro permissions
      - "api:treatments:create"
      - "api:treatments:update"     # Only own documents
      - "api:devicestatus:create"
      - "api:entries:create"
      - "api:profile:read"
```

---

## OpenAPI Schema Extension

Following the patterns in `lib/api3/swagger.yaml`, the registration endpoints would be specified as:

```yaml
# Addition to lib/api3/swagger.yaml

paths:
  /controllers:
    get:
      tags:
        - controllers
      summary: 'SEARCH: List registered controllers'
      operationId: SEARCH_CONTROLLERS
      description: |
        Returns all registered controllers for this Nightscout instance.
        Useful for consumers to discover active controllers and their
        identity strategies for deduplication.
        
        Requires `api:controllers:read` permission.
      
      security:
        - jwtoken: []
      
      responses:
        200:
          description: Array of registered controllers
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/ControllerRegistration'
    
    post:
      tags:
        - controllers
      summary: 'CREATE: Register a new controller'
      operationId: CREATE_CONTROLLER
      description: |
        Registers a new controller with this Nightscout instance.
        The `identifier` is server-assigned. The `boundSubject` links
        the registration to the authenticated token's subject.
        
        Deduplication: If a controller with matching `controllerId` already
        exists for this subject, the operation becomes an UPDATE (returns 200
        with `isDeduplication: true`).
        
        Requires `api:controllers:create` permission.
      
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ControllerRegistrationInput'
      
      security:
        - jwtoken: []
      
      responses:
        201:
          $ref: '#/components/responses/201CreatedLocation'
        200:
          $ref: '#/components/responses/200Deduplication'
        400:
          $ref: '#/components/responses/400BadRequest'
        401:
          $ref: '#/components/responses/401Unauthorized'
        403:
          $ref: '#/components/responses/403Forbidden'

  /controllers/{identifier}:
    parameters:
      - name: identifier
        in: path
        required: true
        schema:
          type: string
    
    get:
      tags:
        - controllers
      summary: 'READ: Get a specific controller registration'
      operationId: READ_CONTROLLER
      security:
        - jwtoken: []
      responses:
        200:
          description: Controller registration document
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ControllerRegistration'
    
    put:
      tags:
        - controllers
      summary: 'UPDATE: Update controller registration'
      operationId: UPDATE_CONTROLLER
      description: |
        Updates an existing controller registration. Only the `boundSubject`
        that created the registration (or admin) can update it.
        
        Immutable fields (cannot be changed): `identifier`, `boundSubject`,
        `srvCreated`, `controllerId`.
      
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ControllerRegistrationInput'
      
      security:
        - jwtoken: []
      
      responses:
        200:
          description: Updated successfully
        400:
          $ref: '#/components/responses/400BadRequest'
        403:
          $ref: '#/components/responses/403Forbidden'
    
    delete:
      tags:
        - controllers
      summary: 'DELETE: Revoke controller registration'
      operationId: DELETE_CONTROLLER
      description: |
        Soft-deletes (revokes) a controller registration by setting
        `isValid: false`. The registration remains in history for audit.
        
        Only the `boundSubject` or admin can revoke.
      
      security:
        - jwtoken: []
      
      responses:
        200:
          description: Revoked successfully

components:
  schemas:
    ControllerRegistration:
      type: object
      required:
        - controllerId
        - controllerName
        - identityStrategy
      properties:
        identifier:
          type: string
          description: Server-assigned unique identifier
          readOnly: true
        controllerId:
          type: string
          description: Controller type identifier (e.g., "loop-ios", "aaps-android")
          example: "loop-ios"
        controllerName:
          type: string
          description: Human-readable controller name
          example: "Loop"
        controllerVersion:
          type: string
          description: Semantic version of the controller
          example: "3.4.0"
        platform:
          type: string
          enum: [ios, android, linux, web, other]
        boundSubject:
          type: string
          description: Subject from authentication token
          readOnly: true
        identityStrategy:
          $ref: '#/components/schemas/IdentityStrategy'
        uploads:
          $ref: '#/components/schemas/UploadCommitments'
        capabilities:
          $ref: '#/components/schemas/ControllerCapabilities'
        authorityRequest:
          $ref: '#/components/schemas/AuthorityRequest'
        srvCreated:
          type: integer
          format: int64
          readOnly: true
        srvModified:
          type: integer
          format: int64
          readOnly: true
        isValid:
          type: boolean
          readOnly: true
          default: true
    
    IdentityStrategy:
      type: object
      required:
        - type
        - field
      properties:
        type:
          type: string
          enum: [uuid, composite, timestamp, enteredBy]
          description: |
            - uuid: Single UUID field for identity
            - composite: Multiple fields combined
            - timestamp: created_at + eventType (legacy)
            - enteredBy: String match on enteredBy field (legacy)
        field:
          type: string
          description: Primary identity field name
          example: "syncIdentifier"
        scope:
          type: string
          enum: [per-record, per-device, per-user]
          default: per-record
        compositeFields:
          type: array
          items:
            type: string
          description: For composite type, list of fields
    
    UploadCommitments:
      type: object
      properties:
        treatments:
          type: object
          properties:
            eventTypes:
              type: array
              items:
                type: string
            fields:
              type: array
              items:
                $ref: '#/components/schemas/FieldCommitment'
            lifecycleEvents:
              type: object
              properties:
                supersession:
                  type: boolean
                edits:
                  type: boolean
                deletions:
                  type: boolean
        entries:
          type: object
          properties:
            enabled:
              type: boolean
            types:
              type: array
              items:
                type: string
        devicestatus:
          type: object
          properties:
            namespace:
              type: string
              example: "loop"
            predictionFormat:
              type: string
              enum: [single-array, separate-arrays]
            effectTimelines:
              type: boolean
    
    FieldCommitment:
      type: object
      properties:
        name:
          type: string
        type:
          type: string
          enum: [string, number, boolean, uuid, timestamp]
        required:
          type: boolean
        unit:
          type: string
          description: For numeric fields, the unit (e.g., "seconds", "units")
    
    ControllerCapabilities:
      type: object
      properties:
        remoteCommands:
          type: boolean
        remoteOverrides:
          type: boolean
        remoteBolus:
          type: boolean
        remoteCarbs:
          type: boolean
        websocket:
          type: boolean
        apiVersion:
          type: string
          enum: [v1, v3]
    
    AuthorityRequest:
      type: object
      properties:
        level:
          type: string
          enum: [controller, agent, human]
          description: Requested authority level
        scopes:
          type: array
          items:
            type: string
          description: Requested Shiro permission strings
```

---

## Identity Verification

### Current: Unverified `enteredBy`

```json
{
  "eventType": "Temp Basal",
  "enteredBy": "Loop",
  "rate": 1.5
}
```

**Source:** No validation in `lib/server/treatments.js`—any client can set any `enteredBy` value.

### Proposed: Verified Controller Binding

The server links uploads to registrations:

```javascript
// Proposed enhancement to lib/api3/generic/create/operation.js

// After authentication, look up controller registration
const registration = await findControllerRegistration(ctx.auth.subject);

if (registration && registration.isValid) {
  // Inject verified controller identity
  doc.controllerId = registration.controllerId;
  doc.controllerVersion = registration.controllerVersion;
  doc.controllerRegistration = registration.identifier;
} else {
  // Unregistered controller - use legacy enteredBy
  // Phase 1: Allow, log warning
  // Phase 3: Reject or require registration
}
```

### Resulting Document

```json
{
  "eventType": "Temp Basal",
  "rate": 1.5,
  "enteredBy": "Loop",
  "controllerId": "loop-ios",
  "controllerVersion": "3.4.0",
  "controllerRegistration": "abc123",
  "subject": "loop-user-token-xyz",
  "srvCreated": 1705000000000,
  "srvModified": 1705000000000
}
```

---

## Migration Path

### API v1 and v3 Bridge Strategy

Since most controllers (Loop, Trio, xDrip) use API v1 while only AAPS uses v3, the registration protocol must work with both:

#### API v3 Controllers (AAPS)

Native support—registration follows existing v3 patterns:

```http
POST /api/v3/controllers
Authorization: Bearer eyJ...access-token...
Content-Type: application/json

{
  "controllerId": "aaps-android",
  "controllerName": "AndroidAPS",
  "identityStrategy": { "type": "uuid", "field": "identifier" },
  ...
}
```

#### API v1 Controllers (Loop, Trio, xDrip)

Add a registration endpoint that works with SHA1 API_SECRET:

```http
POST /api/v1/controllers
api-secret: <sha1-hash>
Content-Type: application/json

{
  "controllerId": "loop-ios",
  "controllerName": "Loop",
  ...
}
```

The v1 endpoint internally creates a v3 registration document, binding to a synthetic subject derived from the API_SECRET hash.

### Leveraging Existing Fallback Patterns

The cgm-remote-monitor already has fallback patterns for cross-API compatibility:

```javascript
// lib/api3/index.js:70-72 - Existing fallback pattern
self.setENVTruthy('API3_DEDUP_FALLBACK_ENABLED', apiConst.API3_DEDUP_FALLBACK_ENABLED);
self.setENVTruthy('API3_CREATED_AT_FALLBACK_ENABLED', apiConst.API3_CREATED_AT_FALLBACK_ENABLED);
```

Similarly, add:

```javascript
self.setENVTruthy('API3_CONTROLLER_REGISTRATION_ENABLED', true);
self.setENVTruthy('API3_CONTROLLER_REGISTRATION_REQUIRED', false);  // Phase 1-2
```

### Phase Timeline

#### Phase 1: Optional Registration (6 months)

- `API3_CONTROLLER_REGISTRATION_ENABLED=true` (default)
- `API3_CONTROLLER_REGISTRATION_REQUIRED=false` (default)
- Controllers can register voluntarily
- Unregistered controllers work exactly as today
- Registered controllers get `controllerId` injected into their documents
- Logging tracks registered vs. unregistered traffic

**Compatibility:**
```json
{
  "enteredBy": "Loop",
  "controllerId": "loop-ios",
  "controllerVersion": "3.4.0"
}
```

#### Phase 2: Incentivized Registration (12 months)

- New features require registration:
  - Remote commands with OTP
  - Authority-based conflict resolution
  - Schema validation warnings
- Documentation emphasizes registration benefits
- Nightscout admin panel shows registered controllers

#### Phase 3: Required Registration (18+ months)

- `API3_CONTROLLER_REGISTRATION_REQUIRED=true`
- Unregistered uploads rejected with 403 and helpful error message
- Grace period with warnings before hard enforcement
- `enteredBy` becomes display-only (not authority)

---

## Resolving Open Questions

Based on source code analysis and cross-project patterns:

### 1. Granularity: Per-controller-type or per-installation?

**Answer: Per-installation (per-user-per-controller)**

**Rationale:**
- The existing `subject` field in API v3 already tracks per-user identity
- AAPS uses `InterfaceIDs.nightscoutId` to track per-installation identity
- Different users may run different controller versions
- Registration binds to `boundSubject` from the authentication token

**Source evidence:**
```kotlin
// aaps:InterfaceIDs.kt - Per-installation tracking
data class InterfaceIDs(
    var nightscoutId: String? = null,  // Per-installation NS ID
    var pumpId: Long? = null,
    ...
)
```

### 2. Revocation: How to handle compromised registrations?

**Answer: Soft delete with `isValid: false`**

**Rationale:**
- Follows existing v3 soft delete pattern (`lib/api3/generic/delete/operation.js`)
- Revoked registrations remain in history for audit
- Controllers receive 403 on subsequent uploads
- Admin can re-enable if revocation was in error

**Implementation:**
```javascript
// DELETE /api/v3/controllers/{identifier}
// Sets isValid: false, appears in history endpoint
```

### 3. Schema enforcement: Reject or annotate non-conforming uploads?

**Answer: Annotate (Phase 1-2), then warn (Phase 2), then optionally reject (Phase 3)**

**Rationale:**
- Breaking strict enforcement would break existing integrations
- Gradual escalation allows controllers to fix issues
- Admin can configure strictness per-instance

**Proposed fields:**
```json
{
  "schemaConformance": "partial",
  "schemaWarnings": ["duration unit mismatch: expected seconds, got milliseconds"]
}
```

### 4. Backward compatibility: How long to support unregistered?

**Answer: 18 months from v1.0 release**

**Rationale:**
- Major AID app release cycles are ~12 months
- Provides buffer for all major controllers to adopt
- Matches typical Nightscout deprecation timelines

### 5. Cross-instance: Registration valid across all instances?

**Answer: Per-instance (each Nightscout has its own registry)**

**Rationale:**
- Nightscout instances are independently operated
- No central authority to validate cross-instance claims
- Users may have different trust relationships per instance
- Simpler security model—no distributed registry needed

**Future consideration:** Signed controller manifests from controller developers could allow portable validation.

### 6. Versioning: How to handle breaking controller schema changes?

**Answer: Version field in registration + semantic versioning**

**Rationale:**
- `controllerVersion` already captures semantic version
- Registration update (`PUT /api/v3/controllers/{id}`) on version change
- Breaking changes require new registration with updated `uploads` schema
- History endpoint tracks schema evolution

**Example:**
```http
PUT /api/v3/controllers/abc123
{
  "controllerVersion": "4.0.0",
  "uploads": { ... }  // Updated schema for v4
}
```

---

## Implementation Roadmap

### Repository: `nightscout/cgm-remote-monitor`

#### PR 1: Controller Collection Infrastructure

**Files to modify/create:**

| File | Changes |
|------|---------|
| `lib/api3/index.js` | Add `controllers` to `enabledCollections` array |
| `lib/api3/generic/setup.js` | Include controllers in generic setup |
| `lib/api3/const.json` | Add controller-related constants |
| `lib/api3/swagger.yaml` | Add `/controllers` endpoints (schema above) |
| `lib/storage/mongo-storage.js` | Add `controllers` collection with indexes |
| `env.js` | Add `API3_CONTROLLER_REGISTRATION_*` env vars |

**New files:**

| File | Purpose |
|------|---------|
| `lib/api3/specific/controllers.js` | Controller-specific logic (beyond generic CRUD) |
| `lib/api3/controllers/validate.js` | Registration validation rules |
| `lib/api3/controllers/immutable.js` | Immutable field enforcement |

**Indexes:**
```javascript
// Unique index on controllerId + boundSubject
{ 'controllerId': 1, 'boundSubject': 1 }, { unique: true, sparse: true }
```

#### PR 2: Identity Injection on Uploads

**Files to modify:**

| File | Changes |
|------|---------|
| `lib/api3/generic/create/operation.js` | Look up registration, inject `controllerId` |
| `lib/api3/generic/update/operation.js` | Same injection logic |
| `lib/server/treatments.js` | v1 compatibility: inject if registration exists |
| `lib/server/websocket.js` | WebSocket `dbAdd` injection |

**Logic:**
```javascript
async function injectControllerIdentity(ctx, doc) {
  if (!app.get('API3_CONTROLLER_REGISTRATION_ENABLED')) return doc;
  
  const registration = await ctx.controllers.findOne({
    boundSubject: ctx.auth.subject,
    isValid: true
  });
  
  if (registration) {
    doc.controllerId = registration.controllerId;
    doc.controllerVersion = registration.controllerVersion;
    doc.controllerRegistration = registration.identifier;
  }
  
  return doc;
}
```

#### PR 3: API v1 Registration Bridge

**Files to modify:**

| File | Changes |
|------|---------|
| `lib/api/index.js` | Add v1 registration endpoint |
| `lib/api/controllers.js` | New file: v1 → v3 bridge |

**Endpoint:**
```
POST /api/v1/controllers
api-secret: <sha1-hash>
```

Creates v3 registration with synthetic subject from API_SECRET hash.

#### PR 4: Admin UI for Controller Discovery

**Files to modify:**

| File | Changes |
|------|---------|
| `views/adminindex.html` | Add "Controllers" section |
| `bundle/bundle.source.js` | Add controller list component |
| `static/admin/js/controllers.js` | New: controller management UI |

**Features:**
- List registered controllers
- Show registration details
- Revoke registration button
- Registration status (active, revoked)

---

## Stakeholder Impact

### AID Controller Developers (Loop, AAPS, Trio, xDrip)

**Must implement:**
- Registration call on first sync
- Handle 403 if registration revoked (Phase 3)
- Include `controllerVersion` in registration

**Benefits:**
- Verified identity—no more impersonation
- Clear dedup contract—no more duplicate guessing
- Authority integration—human overrides respected
- Capability discovery—apps know each other's patterns

**Effort estimate:** ~1-2 days of development per controller

### Nightscout Maintainers

**Must implement:**
- PRs 1-4 above
- Documentation updates
- Migration guide for controller developers

**Benefits:**
- Better data quality
- Reduced duplicate-related support tickets
- Clear contract with controller teams
- Audit trail for uploads

### App Developers (Consumers like Nightguard, Nightscout Reporter)

**Can use:**
- `GET /api/v3/controllers` to discover active controllers
- Query registration to understand identity strategy
- Parse devicestatus based on registered namespace

**Benefits:**
- No more hardcoded controller detection logic
- Reliable deduplication using registered identity field
- Clear prediction format per controller

### End Users

**Experience:**
- More reliable sync (fewer duplicates)
- Human overrides respected by controllers
- Clear visibility of registered controllers in admin

**Action required:**
- None (transparent upgrade)
- Optional: Review registered controllers in admin panel

---

## Success Metrics

| Metric | Baseline | Phase 1 Target | Phase 3 Target |
|--------|----------|----------------|----------------|
| % traffic from registered controllers | 0% | 30% | 95% |
| Duplicate treatments per day | ~5-10% | ~3% | <1% |
| Human override conflicts | ~10% | ~5% | <1% |
| Controller integration time (days) | 5-7 | 3-4 | 1-2 |
| Support tickets about duplicates | ~20/month | ~10/month | ~2/month |

---

## Source Code References

### Nightscout Core (`externals/cgm-remote-monitor/`)

| Document Claim | Evidence Location |
|----------------|-------------------|
| Upsert-by-default pattern | `lib/server/treatments.js:42-46` |
| `enteredBy` is unvalidated | `lib/server/treatments.js` indexedFields |
| WebSocket dedup logic | `lib/server/websocket.js` query_similiar |
| Immutable fields in v3 | `lib/api3/generic/update/validate.js:21-22` |
| `subject` field injection | `lib/api3/generic/create/operation.js` |
| Subject resolution from tokens | `lib/authorization/index.js` resolve() function |
| Shiro permission model | `lib/authorization/index.js` checkMultiple() |
| Soft delete pattern | `lib/api3/generic/delete/operation.js` |
| Fallback env patterns | `lib/api3/index.js:69-72` |
| OpenAPI response schemas | `lib/api3/swagger.yaml:778` (200Deduplication), `:817` (201CreatedLocation) |

### Controller Codebases (via Alignment Workspace Analysis)

Evidence for controller identity strategies is documented in the alignment workspace mapping documents:

| Controller | Identity Evidence | Source Document |
|------------|-------------------|-----------------|
| Loop `syncIdentifier` | `DoseEntry.swift` uses `syncIdentifier: UUID` | [mapping/loop/nightscout-sync.md](../../mapping/loop/nightscout-sync.md) |
| AAPS `identifier` | `InterfaceIDs.kt` stores `nightscoutId` | [mapping/aaps/nightscout-sync.md](../../mapping/aaps/nightscout-sync.md) |
| Trio `enteredBy` filter | `NightscoutAPI.swift` uses `$ne` filter | [mapping/trio/nightscout-sync.md](../../mapping/trio/nightscout-sync.md) |
| xDrip `uuid` | `NSCLIENT_ID` via WebSocket | [mapping/xdrip-android/nightscout-sync.md](../../mapping/xdrip-android/nightscout-sync.md) |

See [AID Controller Sync Patterns](../../mapping/cross-project/aid-controller-sync-patterns.md) for cross-controller comparison with line-level source citations.

---

## Next Steps

- [ ] Gather feedback from Loop, AAPS, Trio, and xDrip maintainers
- [ ] Review with Nightscout Foundation maintainers
- [ ] Create PR 1 (infrastructure) as proof of concept
- [ ] Define migration timeline with consensus
- [ ] Create reference implementation for one controller (suggest: AAPS, already v3)
- [ ] Document consumer query patterns

---

## Related Documents

- [Authority Model](../10-domain/authority-model.md)
- [AID Controller Sync Patterns](../../mapping/cross-project/aid-controller-sync-patterns.md)
- [CGM Remote Monitor Source Synthesis](./cgm-remote-monitor-source-synthesis.md)
- [Nightscout API v1 vs v3 Comparison](../10-domain/nightscout-api-comparison.md)
- [Known Gaps](../../traceability/gaps.md)
- [Nightscout API v3 OpenAPI Spec](../../externals/cgm-remote-monitor/lib/api3/swagger.yaml)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial draft |
| 2026-01-17 | Agent | v2: Repositioned as Nightscout Core contract, added source code evidence, OpenAPI schema, resolved open questions, implementation roadmap |
