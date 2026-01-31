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

## WebSocket Requirements

### REQ-API-004: Document WebSocket Capabilities

**Statement**: Nightscout documentation SHOULD clearly describe both WebSocket channels and their limitations.

**Rationale**: Developers need to understand which channel suits their use case.

**Scenarios**:
- Developer choosing between REST and WebSocket
- Client implementing real-time updates
- Understanding v1 vs v3 channel differences

**Verification**:
- Documentation exists for both `/` and `/storage` namespaces
- Supported events listed
- Authentication methods documented

**Gap Reference**: GAP-API-013

---

### REQ-API-005: Cross-Channel Event Propagation

**Statement**: Changes via any entry point (v1 REST, v3 REST, WebSocket v1) SHOULD be broadcast on all WebSocket channels.

**Rationale**: Clients shouldn't need to know which API was used for the original write.

**Scenarios**:
- Loop uploads via v1 REST, follower subscribes to v3 storage
- Web interface uses WebSocket v1, AAPS listens on v3

**Verification**:
- Create treatment via v1 POST
- Verify `/storage` channel receives `create` event

**Gap Reference**: GAP-API-014

---

### REQ-API-006: WebSocket Rate Limiting

**Statement**: WebSocket write operations SHOULD be rate-limited to prevent abuse.

**Rationale**: Prevent DOS attacks via rapid `dbAdd` events.

**Scenarios**:
- Malicious client sends flood of events
- Misbehaving client in tight loop

**Verification**:
- Send 100 `dbAdd` events in 1 second
- Verify rate limit response or throttling

**Gap Reference**: N/A (best practice)

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

## API v3 Sync Requirements

---

### REQ-API3-001: History Endpoint Completeness

**Statement**: The `/history` endpoint MUST return all modified documents including soft-deleted ones (`isValid=false`).

**Rationale**: Clients need delete notifications to achieve full synchronization. Missing delete events cause stale data accumulation.

**Scenarios**:
- Treatment deleted in web UI, Loop must remove from IOB
- Device status pruned, client cache must update
- Entry soft-deleted, all clients must reflect

**Verification**:
- History response includes documents with `isValid: false`
- Deleted documents appear within srvModified window
- No silent document disappearance

**Source**: `lib/api3/generic/history/operation.js`

---

### REQ-API3-002: Deduplication Determinism

**Statement**: Deduplication MUST be deterministic based on `identifier` or collection-specific fallback fields.

**Rationale**: Prevents duplicate documents from sync race conditions. Critical for treatment safety (duplicate boluses).

**Scenarios**:
- Loop retries failed upload - no duplicate treatment
- AAPS uploads same reading twice - no duplicate SGV
- Network timeout causes retry - dedup handles gracefully

**Verification**:
- Identical POST requests don't create duplicates
- Fallback dedup uses documented fields per collection
- `API3_DEDUP_FALLBACK_ENABLED` behavior documented

**Source**: `lib/api3/generic/setup.js:29-93`

---

### REQ-API3-003: srvModified Monotonicity

**Statement**: `srvModified` MUST be monotonically increasing within server timeline for a collection.

**Rationale**: Ensures history sync doesn't miss documents. If srvModified goes backward, incremental sync could skip updates.

**Scenarios**:
- High-frequency updates (multiple per second)
- Server time correction
- Distributed Nightscout deployment

**Verification**:
- Sequential updates produce increasing srvModified values
- Clock adjustment doesn't cause srvModified regression
- History endpoint returns in srvModified order

**Source**: `lib/api3/generic/history/operation.js:115-119`

---

## Roles Gateway Requirements

---

### REQ-RG-001: Three Access Mode Support

**Statement**: The roles gateway MUST support three orthogonal access modes: anonymous, identity-mapped, and API secret bypass.

**Rationale**: Different use cases require different authentication approaches - public dashboards, school/clinic RBAC, and legacy uploader compatibility.

**Scenarios**:
- Public site view (anonymous access)
- School health office with scheduled access (identity-mapped)
- Legacy CGM uploader (API secret bypass)

**Verification**:
- `require_identities=false` allows anonymous access
- `require_identities=true` enforces identity check
- `exempt_matching_api_secret=true` allows API secret bypass

**Source**: `mapping/nightscout-roles-gateway/authorization.md`

---

### REQ-RG-002: API Secret Hashing

**Statement**: API secrets MUST be SHA1 hashed in storage, never stored in plaintext.

**Rationale**: Security requirement to protect credentials in case of database breach.

**Verification**:
- `nightscout_secrets` table stores only hashed values
- Comparison done via hash match

**Source**: `externals/nightscout-roles-gateway/lib/tokens/index.js`

---

### REQ-RG-003: Time-Based Access Policies

**Statement**: The gateway MUST support time-based access policies with weekly schedules.

**Rationale**: School/clinic deployments need access restrictions during off-hours.

**Verification**:
- Policies can specify start/end times
- Weekly schedule with fill patterns
- Scheduled policies applied correctly

**Source**: `externals/nightscout-roles-gateway/lib/policies/index.js`

---

### REQ-RG-004: Group Membership Audit

**Statement**: The gateway MUST log group consent for HIPAA-adjacent audit requirements.

**Rationale**: Healthcare compliance requires audit trail of who accessed what data.

**Verification**:
- `/api/v1/privy/:identity/groups/joined` endpoint records consent
- `joined_groups` table maintains audit trail

**Source**: `externals/nightscout-roles-gateway/lib/routes.js:316-317`

---

## Interoperability Requirements

---

### REQ-NS-025: Ordered Batch Write Guarantee

**Statement**: The Nightscout API MUST preserve insertion order when processing batch uploads.

**Rationale**: Loop and other AID clients depend on chronological ordering for CGM data continuity. Unordered writes can cause gaps in glucose display.

**Scenarios**:
- Loop uploads 100 SGV entries in batch
- AAPS uploads treatments with timestamps

**Verification**:
- Use `bulkWrite({ordered: true})` or equivalent
- Test: upload batch, verify order matches input

**Gap**: GAP-DB-001

**Source**: `docs/10-domain/cgm-remote-monitor-design-review.md`

---

### REQ-NS-026: Token Revocation Support

**Statement**: The Nightscout API SHOULD support token revocation to invalidate compromised credentials.

**Rationale**: Currently no mechanism exists to revoke a compromised JWT or subject token until the subject is deleted.

**Scenarios**:
- User suspects token compromise
- Admin needs to revoke caregiver access

**Verification**:
- Revocation endpoint or admin UI
- Revoked tokens rejected on subsequent requests

**Gap**: GAP-AUTH-004

**Source**: `docs/10-domain/cgm-remote-monitor-design-review.md`

---

### REQ-NS-027: OpenAPI Specification

**Statement**: The Nightscout API SHOULD publish an OpenAPI 3.0 specification for all v3 endpoints.

**Rationale**: Enables SDK generation, automated testing, and documentation accuracy.

**Scenarios**:
- Developer generates TypeScript client
- CI validates request/response formats

**Verification**:
- `swagger/openapi-v3.yaml` exists and validates
- Generated client successfully calls all endpoints

**Gap**: GAP-API-001, GAP-API-006

**Source**: `docs/10-domain/cgm-remote-monitor-design-review.md`

---

### REQ-NS-028: Sync Conflict Detection

**Statement**: The Nightscout API SHOULD detect and report sync conflicts when multiple clients update the same record.

**Rationale**: Current last-write-wins behavior can silently lose data from slower clients.

**Scenarios**:
- Loop and AAPS both update same treatment
- Offline client syncs stale data

**Verification**:
- Version field incremented on updates
- 409 Conflict returned for stale updates

**Gap**: GAP-SYNC-008

**Source**: `docs/10-domain/cgm-remote-monitor-design-review.md`

---

## DeviceStatus Schema Requirements

### REQ-DS-001: Unified Prediction Format

**Statement**: Nightscout SHOULD provide a unified prediction format that normalizes Loop and oref0 prediction arrays.

**Rationale**: Loop uses single `predicted.values` array while oref0 uses 4 separate curves (IOB, COB, UAM, ZT). Third-party tools must implement dual parsers.

**Scenarios**:
- Third-party tool displays predictions from any controller
- Report generates unified prediction chart

**Verification**:
- API endpoint returns normalized prediction structure
- Both Loop and oref0 data parse to same format

**Gap**: GAP-DS-001

**Source**: `docs/10-domain/nightscout-devicestatus-schema-audit.md`

---

### REQ-DS-002: IOB Component Breakdown

**Statement**: All controllers SHOULD report IOB with basal and bolus components.

**Rationale**: Loop reports only total IOB, while oref0 provides `basaliob` and `bolusiob`. This limits analysis capabilities.

**Scenarios**:
- Report shows IOB by source (basal vs bolus)
- Retrospective analysis of insulin delivery

**Verification**:
- devicestatus includes `iob.basaliob` and `iob.bolusiob`
- Reports can chart IOB components separately

**Gap**: GAP-DS-002

**Source**: `docs/10-domain/nightscout-devicestatus-schema-audit.md`

---

### REQ-DS-003: Override Status Reporting

**Statement**: All controllers SHOULD report active override/temporary target status in devicestatus.

**Rationale**: Loop has `status.override` but oref0 uses profile switches, which aren't visible in devicestatus.

**Scenarios**:
- Dashboard shows active override for any controller
- Reports annotate periods with overrides active

**Verification**:
- devicestatus includes override field for all controllers
- Profile switch events linked to devicestatus

**Gap**: GAP-DS-003

**Source**: `docs/10-domain/nightscout-devicestatus-schema-audit.md`

---

### REQ-DS-004: Eventual BG Prediction

**Statement**: All controllers SHOULD report `eventualBG` prediction endpoint.

**Rationale**: oref0 explicitly reports `eventualBG`, Loop does not. This limits prediction visualization.

**Scenarios**:
- Dashboard shows eventual BG for any controller
- Alerts based on eventual BG threshold

**Verification**:
- devicestatus includes `eventualBG` field
- Value represents prediction endpoint (2-6 hours out)

**Gap**: GAP-DS-004

**Source**: `docs/10-domain/nightscout-devicestatus-schema-audit.md`

---

## iOS SDK Requirements (2026-01-31)

---

### REQ-SDK-001: v3 API Support

**Statement**: NightscoutKit Swift SDK MUST support API v3 endpoints as primary interface.

**Rationale**: v3 provides incremental sync, soft-delete detection, and granular permissions.

**Scenarios**:
- Client fetches entries via `/api/v3/entries`
- Client uses `/api/v3/{collection}/history` for incremental sync
- Deleted documents detected via `isValid: false`

**Verification**:
- SDK passes v3 conformance tests
- History sync returns added, updated, and deleted documents

**Gap**: GAP-API-003

**Source**: `docs/sdqctl-proposals/nightscoutkit-swift-sdk-design.md`

---

### REQ-SDK-002: Multiple Authentication Methods

**Statement**: NightscoutKit Swift SDK MUST support API_SECRET, JWT, and Token authentication.

**Rationale**: Different deployment scenarios require different auth methods.

**Scenarios**:
- API_SECRET: Traditional SHA1 header for full access
- JWT: Bearer token for granular permissions
- Token: Query parameter for simple read access

**Verification**:
- All three auth methods authenticate successfully
- JWT permissions respected (read-only token cannot write)

**Gap**: GAP-API-003, GAP-API-004

**Source**: `docs/sdqctl-proposals/nightscoutkit-swift-sdk-design.md`

---

### REQ-SDK-003: Incremental Sync

**Statement**: NightscoutKit Swift SDK MUST provide SyncManager for incremental synchronization.

**Rationale**: Full sync is expensive; incremental sync reduces bandwidth and latency.

**Scenarios**:
- First sync: fetch all documents in date range
- Subsequent sync: fetch only changes since `Last-Modified`
- Deleted documents: return identifiers for local cache eviction

**Verification**:
- SyncManager tracks last-modified per collection
- Second sync returns only new/changed documents

**Gap**: GAP-API-001, GAP-API-003

**Source**: `docs/sdqctl-proposals/nightscoutkit-swift-sdk-design.md`

---

### REQ-SDK-004: Swift Concurrency

**Statement**: NightscoutKit Swift SDK MUST use async/await for all network operations.

**Rationale**: Modern Swift concurrency provides cleaner code and better error handling.

**Scenarios**:
- All fetch/create/update/delete operations are async
- Actor-based client ensures thread safety
- No callback-based APIs in public interface

**Verification**:
- All public methods are marked `async throws`
- Client is declared as `actor`

**Gap**: GAP-API-003

**Source**: `docs/sdqctl-proposals/nightscoutkit-swift-sdk-design.md`


---

## Identity Provider Requirements

### REQ-IDP-001: OIDC Discovery Endpoint

**Statement**: Nightscout instances MAY expose OIDC discovery metadata at `.well-known/openid-configuration`.

**Rationale**: Standard OIDC discovery enables client auto-configuration and federation.

**Scenarios**:
- Client auto-configures from discovery document
- Federation with external IdPs

**Verification**:
- GET `/.well-known/openid-configuration` returns valid OIDC metadata
- Standard claims (issuer, authorization_endpoint, etc.) present

**Gap**: GAP-IDP-001

**Source**: `docs/10-domain/trusted-identity-providers.md`

---

### REQ-IDP-002: Actor Claims in JWT

**Statement**: Identity tokens SHOULD include actor claims identifying the authenticated user.

**Rationale**: Enables care team visibility and audit trails for all data modifications.

**Scenarios**:
- Parent boluses on behalf of child
- School nurse acknowledges alarm
- Automated agent (Loop) enacts temp basal

**Verification**:
- JWT includes `actor_type`, `actor_name`, `act` claims
- Treatments tagged with actor reference

**Gap**: GAP-IDP-001, GAP-AUTH-001

**Source**: `docs/10-domain/trusted-identity-providers.md`, `externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md`

---

### REQ-IDP-003: Care Team Role Support

**Statement**: Nightscout SHOULD support defining care team roles with differentiated permissions.

**Rationale**: Different caregivers need different access levels (parent vs school nurse vs grandparent).

**Scenarios**:
- Parent has full admin access
- School nurse can view and acknowledge alarms
- Grandparent has read-only access
- Permissions can be time-limited

**Verification**:
- Role definitions in database or config
- Permission check respects role assignments
- Time-based access expiration works

**Gap**: GAP-IDP-003, GAP-AUTH-002

**Source**: `docs/10-domain/trusted-identity-providers.md`


---

## Community Identity Provider Requirements

### REQ-IDP-004: OIDC Compliance

**Statement**: Community IdP MUST be fully OIDC-compliant.

**Rationale**: OIDC is the industry standard for identity federation. Non-standard auth creates integration burden.

**Scenarios**: Provider selection, client integration, security audit.

**Verification**: OIDC conformance test suite, discovery endpoint validation.

**Source**: `docs/sdqctl-proposals/ns-community-idp-proposal.md`

---

### REQ-IDP-005: Multi-Provider Federation

**Statement**: Federation MUST support multiple identity providers simultaneously.

**Rationale**: Single IdP creates central point of failure and control. Federation preserves user choice.

**Scenarios**: User selects provider, provider joins federation, provider leaves federation.

**Verification**: Test login via multiple providers, verify claim normalization.

**Source**: `docs/sdqctl-proposals/ns-community-idp-proposal.md`

---

### REQ-IDP-006: Data Sovereignty

**Statement**: User data MUST remain with user's chosen provider.

**Rationale**: GDPR compliance, user trust, regional data residency requirements.

**Scenarios**: EU user chooses NS10BE, US user chooses t1pal.

**Verification**: Verify no cross-provider data replication of PII.

**Source**: `docs/sdqctl-proposals/ns-community-idp-proposal.md`

---

### REQ-IDP-007: Open Source Components

**Statement**: All IdP components MUST be open source.

**Rationale**: Transparency, community trust, auditability, sustainability.

**Scenarios**: Component selection, security audit, community contribution.

**Verification**: All repos public, OSI-approved licenses.

**Source**: `docs/sdqctl-proposals/ns-community-idp-proposal.md`

---
