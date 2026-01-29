# Nightscout Api Requirements

Domain-specific requirements extracted from requirements.md.
See [requirements.md](requirements.md) for the index.

---

### REQ-API-001: Document Deduplication Keys Per Collection

**Statement**: The API specification MUST document the deduplication key fields for each collection.

**Rationale**: AID controllers must know which fields trigger dedup to avoid duplicate treatments and ensure proper sync behavior.

**Scenarios**:
- Treatment batch upload from Loop
- Retry after network failure
- AAPS sync with existing data

**Verification**:
- Spec documents `identifier` as primary key
- Spec documents fallback keys per collection
- Spec documents `API3_DEDUP_FALLBACK_ENABLED` behavior

**Gap Reference**: GAP-API-006

---

---

### REQ-API-002: Provide Machine-Readable API Specification

**Statement**: The API SHOULD provide an OpenAPI 3.0 specification for automated client generation.

**Rationale**: Enables SDK generation, request validation, and reduces integration errors.

**Scenarios**:
- New client development
- API version migration
- Automated testing

**Verification**:
- OpenAPI spec exists and validates
- Spec covers all v3 endpoints
- Spec includes request/response schemas

**Gap Reference**: GAP-API-006

---

---

### REQ-API-003: Document Timestamp Field Per Collection

**Statement**: The API specification MUST document the canonical timestamp field name and format for each collection.

**Rationale**: Clients need consistent timestamp handling for cross-collection queries and data correlation.

**Scenarios**:
- Time-range queries across collections
- Data export/import
- Historical analysis

**Verification**:
- Spec documents timestamp field per collection
- Spec documents format (epoch vs ISO-8601)
- Examples show correct field usage

**Gap Reference**: GAP-API-008

---

## Plugin System Requirements

---

### REQ-AUTH-001: Document Permission Strings

**Statement**: The specification MUST document all permission strings used across API endpoints.

**Rationale**: Enables client developers to request appropriate permissions for their use case.

**Scenarios**:
- Client requesting minimal permissions
- Custom role creation
- Permission troubleshooting

**Verification**:
- All endpoints list required permission
- Permission format documented
- Wildcard behavior documented

**Gap Reference**: GAP-API-006

---

---

### REQ-AUTH-002: Token Revocation Capability

**Statement**: The authorization system SHOULD provide a mechanism to revoke access tokens without deleting subjects.

**Rationale**: Enables security response to compromised tokens while preserving audit history.

**Scenarios**:
- Token compromise response
- Device decommissioning
- Permission change enforcement

**Verification**:
- Revocation endpoint exists
- Revoked tokens rejected
- Revocation logged

**Gap Reference**: GAP-AUTH-002

---

---

### REQ-AUTH-003: Document Role Requirements Per Endpoint

**Statement**: The OpenAPI specification SHOULD include required permissions for each endpoint.

**Rationale**: Enables automated permission checking and client-side validation.

**Scenarios**:
- API client development
- Permission audit
- Automated testing

**Verification**:
- `x-required-permission` extension on endpoints
- Role-to-permission mapping documented
- Default roles documented

**Gap Reference**: GAP-AUTH-001

---

## Frontend/UI Requirements

---

### REQ-ERR-001: Empty Array Handling

**Statement**: Batch endpoints SHOULD return an empty success response for empty arrays, NOT create phantom records.

**Rationale**: Creating records from empty input is surprising behavior that masks bugs.

**Scenarios**:
- Empty Batch Upload

**Verification**:
- Submit empty array `[]` to treatments endpoint
- Verify HTTP 200 with empty array response (or 400 error)
- Verify no phantom records created

**Gap Reference**: GAP-ERR-001

---

---

### REQ-ERR-002: CRC Validation Enforcement

**Statement**: Pump drivers SHOULD reject or retry data with invalid CRC, not silently use corrupted data.

**Rationale**: CRC failures indicate data corruption that could affect dosing calculations.

**Scenarios**:
- Pump History Corruption

**Verification**:
- Simulate CRC mismatch in pump history
- Verify retry or rejection behavior
- Verify corrupted data not used for IOB

**Gap Reference**: GAP-ERR-002

---

---

### REQ-ERR-003: Unknown Entry Type Logging

**Statement**: Pump history decoders SHOULD log unknown entry types with full data for community analysis.

**Rationale**: Unknown entries may contain critical dosing information that is being silently discarded.

**Scenarios**:
- New Firmware Entry Types

**Verification**:
- Inject unknown entry type in history
- Verify entry logged with full byte data
- Verify user can report unknown entries

**Gap Reference**: GAP-ERR-003

---

## Specification Requirements

---

### REQ-PLUGIN-001: Document DeviceStatus Schema Per Controller

**Statement**: The API specification MUST document the expected devicestatus fields for each AID controller (Loop, OpenAPS, AAPS, Trio).

**Rationale**: Controllers upload different field structures; plugins must know what to expect.

**Scenarios**:
- Loop devicestatus upload
- AAPS devicestatus upload
- Plugin status display

**Verification**:
- Spec documents Loop `status.loop` structure
- Spec documents OpenAPS `status.openaps` structure
- Spec documents required vs optional fields

**Gap Reference**: GAP-PLUGIN-001, GAP-PLUGIN-003

---

---

### REQ-PLUGIN-002: Normalize Prediction Format

**Statement**: The visualization layer SHOULD normalize prediction data to a common format regardless of source controller.

**Rationale**: Enables consistent prediction display across Loop, OpenAPS, and AAPS.

**Scenarios**:
- Loop single-curve prediction display
- OpenAPS multi-curve prediction display
- Cross-controller comparison

**Verification**:
- Prediction visualization handles both formats
- Documentation describes normalization approach
- Unit tests cover both input formats

**Gap Reference**: GAP-PLUGIN-002

---

---

### REQ-PLUGIN-003: Document IOB/COB Calculation Models

**Statement**: The specification SHOULD document the IOB and COB calculation algorithms used by Nightscout plugins.

**Rationale**: Enables cross-project validation and ensures consistent insulin/carb tracking.

**Scenarios**:
- IOB calculation verification
- COB absorption validation
- Algorithm conformance testing

**Verification**:
- IOB exponential decay model documented
- COB absorption model documented
- Formulas match implementation

**Gap Reference**: GAP-ALG-001

---

## Sync/Upload Requirements

---

### REQ-SPEC-001: Document All Valid eventTypes

**Statement**: The OpenAPI specification MUST enumerate all valid eventType values including remote command types.

**Rationale**: Clients cannot implement correct behavior without knowing valid eventTypes.

**Scenarios**:
- Remote Command Processing
- Treatment Type Validation

**Verification**:
- Compare spec enum to all eventTypes used in Nightscout server code
- Verify all Loop/AAPS/Trio eventTypes are represented
- Verify remote command types are documented

**Gap Reference**: GAP-SPEC-001

---

---

### REQ-SPEC-002: Document Controller-Specific Fields

**Statement**: The treatments schema SHOULD document all fields used by major AID controllers with x-aid-controllers annotations.

**Rationale**: Enables round-trip data preservation and cross-system compatibility.

**Scenarios**:
- AAPS Treatment Sync
- Loop Treatment Sync
- Cross-System Data Analysis

**Verification**:
- Compare AAPS RemoteTreatment model fields to spec
- Compare Loop treatment upload fields to spec
- Verify no data loss on upload/download cycle

**Gap Reference**: GAP-SPEC-002

---

---

### REQ-SPEC-003: Document Deduplication Algorithm

**Statement**: The API specification MUST document the deduplication key fields for each collection.

**Rationale**: Clients need to know which fields to include to prevent duplicates.

**Scenarios**:
- Batch Treatment Upload
- Network Retry Handling

**Verification**:
- Verify spec documents `created_at` + `eventType` key for treatments
- Verify spec documents `date` + `device` + `eventType` key for v3
- Verify behavior when dedup key fields are missing

**Gap Reference**: GAP-SPEC-007

---

---

### REQ-SPEC-004: Define isValid Semantics

**Statement**: The API specification MUST define the semantics of the `isValid` field including default value and deletion behavior.

**Rationale**: Consistent soft-delete handling across clients.

**Scenarios**:
- Treatment Deletion
- Sync History Query

**Verification**:
- Document when isValid should be set to false
- Document default value when field is missing
- Document query behavior for isValid filter

**Gap Reference**: GAP-SPEC-006

---

## Algorithm Conformance Requirements

---

### REQ-STATS-001: Daily Aggregation Endpoint

**Statement**: The system MUST provide a `/api/v3/stats/daily` endpoint returning per-day glucose statistics including mean, median, min, max, stdDev, CV, percentiles, and time-in-range.

**Rationale**: Eliminates client-side computation for daily reports, reduces data transfer by 90%+.

**Scenarios**:
- Daily stats report generation
- nightscout-reporter period analysis
- Mobile app dashboards

**Verification**:
- GET `/api/v3/stats/daily?from=X&to=Y` returns array of daily stats
- Each day includes glucose metrics and percentiles
- Response matches documented schema

**Gap Reference**: GAP-STATS-001

---

---

### REQ-STATS-002: Period Summary Endpoint

**Statement**: The system MUST provide a `/api/v3/stats/summary` endpoint returning aggregated statistics for configurable date ranges.

**Rationale**: Enables efficient period analysis without fetching raw entries.

**Scenarios**:
- 14-day, 30-day, 90-day summaries
- A1C/GMI estimation
- Time-in-range tracking

**Verification**:
- GET `/api/v3/stats/summary?from=X&to=Y` returns period aggregation
- Includes A1C estimates (DCCT, IFCC) and GMI
- GVI and PGS variability metrics included

**Gap Reference**: GAP-STATS-001

---

---

### REQ-STATS-003: Hourly Distribution Endpoint

**Statement**: The system SHOULD provide a `/api/v3/stats/hourly` endpoint returning hourly glucose distributions with percentiles.

**Rationale**: Enables percentile charts and time-of-day analysis without raw data.

**Scenarios**:
- Percentile by time-of-day charts
- Dawn phenomenon analysis
- Post-meal pattern detection

**Verification**:
- GET `/api/v3/stats/hourly` returns 24 hourly buckets
- Each hour includes p10, p25, p50, p75, p90
- Count and mean per hour included

**Gap Reference**: GAP-STATS-002

---

---

### REQ-STATS-004: Treatment Aggregation Endpoint

**Statement**: The system SHOULD provide a `/api/v3/stats/treatments` endpoint returning insulin and carb summaries.

**Rationale**: Enables TDD tracking and insulin/carb ratio analysis.

**Scenarios**:
- Total daily dose (TDD) tracking
- Basal/bolus ratio analysis
- Carb counting review

**Verification**:
- Returns daily averages for insulin (basal, bolus, SMB)
- Returns carb totals and meals per day
- Includes bolus-to-basal ratio

**Gap Reference**: GAP-STATS-002

---

---

### REQ-STATS-005: MCP Resource Provider

**Statement**: The Statistics API SHOULD be exposed as MCP (Model Context Protocol) resources for AI/LLM consumption.

**Rationale**: Enables efficient AI assistant integration for health insights.

**Scenarios**:
- "What was my average glucose this week?"
- "Show me my time-in-range for January"
- Automated health summaries

**Verification**:
- MCP resources defined for daily, summary, current stats
- URI pattern: `nightscout://stats/{type}`
- JSON response compatible with MCP spec

**Gap Reference**: GAP-STATS-003

---

### REQ-UI-001: Document Frontend Architecture

**Statement**: The specification SHOULD include a frontend developer guide covering bundle structure, plugin UI development, and chart customization.

**Rationale**: Enables contributors to extend Nightscout frontend without extensive codebase archaeology.

**Scenarios**:
- New plugin development
- Chart customization
- Translation contribution

**Verification**:
- Developer guide exists
- Build process documented
- Plugin UI API documented

**Gap Reference**: GAP-UI-001

---

---

### REQ-UI-002: Chart Accessibility

**Statement**: The glucose chart SHOULD provide accessible alternatives for visually impaired users.

**Rationale**: Ensures Nightscout is usable by all users regardless of visual ability.

**Scenarios**:
- Screen reader navigation
- Keyboard-only access
- Data table view

**Verification**:
- ARIA labels on chart elements
- Data table alternative available
- Keyboard navigation functional

**Gap Reference**: GAP-UI-002

---

---

### REQ-UI-003: Offline Data Access

**Statement**: The application SHOULD cache recent data for offline viewing.

**Rationale**: Enables glucose monitoring during connectivity interruptions.

**Scenarios**:
- Network disconnection
- Poor mobile signal
- Airplane mode with cached data

**Verification**:
- Recent SGVs cached locally
- Offline indicator displayed
- Data refreshes on reconnection

**Gap Reference**: GAP-UI-003

---

## Interoperability Requirements

---
