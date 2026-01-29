# Connectors Requirements

Domain-specific requirements for connector projects (bridges, sync tools).
See [requirements.md](requirements.md) for the index.

---

## nightscout-connect Requirements

---

### REQ-CONNECT-001: V3 API Output Driver

**Statement**: Connector output drivers MUST support Nightscout API v3 with UPSERT operations.

**Rationale**: V3 API provides deduplication, server-side validation, and identifier-based sync identity that prevents duplicate records.

**Scenarios**:
- Entry upload via v3 UPSERT
- Treatment upload with identifier
- Duplicate prevention on re-run

**Verification**:
- Upload entry via v3 endpoint
- Re-upload same entry
- Verify no duplicate created

**Gap Reference**: GAP-CONNECT-001

---

### REQ-CONNECT-002: Sync Identity Generation

**Statement**: Connectors MUST generate deterministic sync identifiers for uploaded records using source-specific attributes.

**Rationale**: Client-side identifier generation enables idempotent uploads and prevents duplicates without server-side state.

**Scenarios**:
- Entry with UUID v5 identifier
- Treatment with consistent ID across re-runs
- Cross-source identifier uniqueness

**Verification**:
- Generate identifier for entry
- Regenerate from same source data
- Verify identical identifier produced

**Gap Reference**: GAP-CONNECT-003

---

### REQ-CONNECT-003: Multi-Collection Source Coverage

**Statement**: Sources SHOULD upload all available collection types (entries, treatments, devicestatus) when the vendor API provides them.

**Rationale**: Single-collection uploads leave incomplete data in Nightscout, limiting utility for downstream consumers.

**Scenarios**:
- Minimed source: entries + treatments + devicestatus
- Glooko source: treatments only (API limit)
- Dexcom Share: entries only (API limit)

**Verification**:
- Run sync for source with multiple collections
- Verify all available collections uploaded

**Gap Reference**: GAP-CONNECT-002

---

### REQ-CONNECT-004: Automated Test Suite

**Statement**: Connectors MUST have automated tests for state machine transitions and vendor adapter integrations.

**Rationale**: Complex XState machines require test coverage to prevent regressions when adding vendors or upgrading dependencies.

**Scenarios**:
- State machine model tests
- Vendor driver mock tests
- Integration tests with test server

**Verification**:
- Run `npm test`
- Verify state coverage report
- Verify vendor adapter coverage

**Gap Reference**: GAP-CONNECT-004

---

### REQ-CONNECT-005: TypeScript Type Definitions

**Statement**: Connectors SHOULD provide TypeScript type definitions for machine contexts, events, and vendor interfaces.

**Rationale**: Type definitions enable IDE autocomplete, catch errors at compile time, and document the API contract.

**Scenarios**:
- FetchContext type definition
- SessionContext type definition
- VendorDriver interface

**Verification**:
- TypeScript compilation succeeds
- No implicit `any` types in core interfaces

**Gap Reference**: GAP-CONNECT-005

---

### REQ-CONNECT-006: Formal Vendor Driver Interface

**Statement**: Connectors MUST define a formal VendorDriver interface contract with validation.

**Rationale**: Current adapter pattern is brittle with inconsistent naming and mixed concerns.

**Scenarios**:
- New vendor implementation
- Driver interface validation
- Adapter contract enforcement

**Verification**:
- Interface enforces required methods
- Runtime validation catches missing methods
- Consistent naming across adapters

**Gap Reference**: GAP-CONNECT-006

---

## Nocturne Requirements

---

### REQ-NOCTURNE-001: V4 API Compatibility Documentation

**Statement**: Nocturne-specific V4 API endpoints MUST be documented as optional extensions, not core Nightscout API.

**Rationale**: V4 endpoints are Nocturne-specific and clients depending on them won't work with cgm-remote-monitor.

**Scenarios**:
- V4 endpoint discovery
- Feature detection
- Graceful fallback to v3

**Verification**:
- Documentation clearly marks V4 as optional
- Clients detect V4 availability
- Fallback to v3 when V4 unavailable

**Gap Reference**: GAP-NOCTURNE-001

---

### REQ-NOCTURNE-002: Cross-Implementation Algorithm Conformance

**Statement**: Rust oref implementation MUST produce equivalent results to JavaScript oref0/oref1 for the same inputs.

**Rationale**: Multiple algorithm implementations must be verifiable against shared test vectors to prevent divergence.

**Scenarios**:
- IOB calculation parity
- COB calculation parity
- Dosing recommendation parity

**Verification**:
- Run conformance test suite
- Compare outputs for shared fixtures
- Document any intentional differences

**Gap Reference**: GAP-NOCTURNE-002

---

### REQ-NOCTURNE-003: Real-Time Latency Budget

**Statement**: SignalR to Socket.IO bridge latency SHOULD be less than 500ms for glucose update events.

**Rationale**: Bridge adds overhead; must be bounded to maintain acceptable real-time experience.

**Scenarios**:
- SignalR event received
- Bridge translation
- Socket.IO emission

**Verification**:
- Measure end-to-end latency
- Report latency percentiles
- Alert if exceeds budget

**Gap Reference**: GAP-NOCTURNE-003

---

## tconnectsync Requirements

---

### REQ-TCONNECT-001: V3 API Support

**Statement**: tconnectsync MUST support Nightscout API v3 with proper identifiers for deduplication.

**Rationale**: V1-only support causes duplicates on re-sync and lacks sync identity tracking.

**Scenarios**:
- Treatment upload with identifier
- Entry upload with identifier
- Re-sync without duplicates

**Verification**:
- Upload via v3 endpoint
- Re-run sync
- Verify no duplicates created

**Gap Reference**: GAP-TCONNECT-001

---

### REQ-TCONNECT-002: Control-IQ Algorithm Data Export

**Statement**: tconnectsync SHOULD extract and upload available Control-IQ algorithm data to devicestatus when accessible.

**Rationale**: Algorithm decision data enables debugging and visualization of Control-IQ behavior.

**Scenarios**:
- Auto-basal adjustment data
- Predicted glucose curves
- Algorithm decision reasons

**Verification**:
- Check devicestatus for Control-IQ data
- Verify prediction curves if available
- Document API limitations

**Gap Reference**: GAP-TCONNECT-002

---

### REQ-TCONNECT-003: Batch Sync Documentation

**Statement**: tconnectsync documentation MUST clearly state batch-based operation and expected latency.

**Rationale**: Users need to understand this is not real-time and plan accordingly.

**Scenarios**:
- Initial setup documentation
- Cron scheduling guidance
- Latency expectations

**Verification**:
- Documentation explains batch mode
- Cron examples provided
- Expected delay documented

**Gap Reference**: GAP-TCONNECT-003

---

### REQ-TCONNECT-004: Trend Direction Handling

**Statement**: tconnectsync SHOULD either calculate trend direction from consecutive readings or clearly document its absence.

**Rationale**: Missing direction field affects Nightscout UI and downstream algorithm consumers.

**Scenarios**:
- Direction field population
- Fallback calculation from history
- Documentation of limitation

**Verification**:
- Check entries for direction field
- If missing, verify documentation
- Algorithm impact noted

**Gap Reference**: GAP-TCONNECT-004

---

## Testing Infrastructure Requirements

---

### REQ-TEST-001: Cross-Implementation Test Vectors

**Statement**: Algorithm conformance testing MUST use shared JSON test vectors consumable by all implementations.

**Rationale**: Enables verification of algorithm consistency across Swift, JavaScript, and Rust implementations.

**Scenarios**:
- IOB test vectors
- COB test vectors
- Full algorithm test vectors

**Verification**:
- Test vectors exist in common format
- All implementations can load vectors
- Results compared automatically

**Gap Reference**: GAP-TEST-001

---

### REQ-TEST-002: SPM Package Support for Testing

**Statement**: Swift packages SHOULD support `swift test` for cross-platform testing when resource constraints allow.

**Rationale**: SPM enables Linux/macOS testing without Xcode, supporting CI and algorithm extraction.

**Scenarios**:
- swift test on Linux
- swift test on macOS
- GitHub Actions integration

**Verification**:
- Package.swift functional
- Tests pass via `swift test`
- CI workflow uses SPM

**Gap Reference**: GAP-TEST-002

---

### REQ-TEST-003: Modern CI Infrastructure

**Statement**: Projects SHOULD use modern CI (GitHub Actions) with current SDK versions.

**Rationale**: Outdated CI with old SDKs may miss compatibility issues and blocks modern feature adoption.

**Scenarios**:
- GitHub Actions workflow
- Current Xcode version
- Current Node/Python versions

**Verification**:
- Workflow file exists
- SDK version is current
- Tests pass in CI

**Gap Reference**: GAP-TEST-003

---

## share2nightscout-bridge Requirements

---

### REQ-SHARE-001: V3 API Support

**Statement**: share2nightscout-bridge MUST support Nightscout API v3 with proper identifiers.

**Rationale**: V3 deduplication prevents duplicates on bridge restart or polling overlap.

**Scenarios**:
- Entry upload with identifier
- Bridge restart handling
- Polling overlap deduplication

**Verification**:
- Upload via v3 endpoint
- Restart bridge
- Verify no duplicates

**Gap Reference**: GAP-SHARE-001

---

### REQ-SHARE-002: Gap Detection and Backfill

**Statement**: share2nightscout-bridge SHOULD detect data gaps and backfill missed readings on recovery.

**Rationale**: Bridge downtime shouldn't cause permanent data gaps when historical data is available.

**Scenarios**:
- Bridge offline for 1 hour
- Bridge restart and recovery
- Gap detection and backfill

**Verification**:
- Stop bridge for period
- Restart bridge
- Verify historical readings fetched

**Gap Reference**: GAP-SHARE-002

---

### REQ-SHARE-003: Configurable Application ID

**Statement**: share2nightscout-bridge SHOULD allow configurable application ID rather than hardcoding.

**Rationale**: Hardcoded IDs create single point of failure if vendor revokes credentials.

**Scenarios**:
- Custom application ID configuration
- Environment variable override
- Documentation of default

**Verification**:
- Configuration option exists
- Override works as documented
- Default still functional

**Gap Reference**: GAP-SHARE-003

---

## nightscout-librelink-up Requirements

---

### REQ-LIBRELINK-001: V3 API Support

**Statement**: nightscout-librelink-up MUST implement the v3 client stub with proper identifiers.

**Rationale**: V3 client currently throws "Not implemented". Functional v3 support prevents duplicates.

**Scenarios**:
- Entry upload with identifier
- Bridge restart handling
- Deduplication verification

**Verification**:
- V3 client functional
- No "Not implemented" errors
- Duplicates prevented

**Gap Reference**: GAP-LIBRELINK-001

---

### REQ-LIBRELINK-002: Historical Backfill Support

**Statement**: nightscout-librelink-up SHOULD support historical data backfill using the graph endpoint.

**Rationale**: Bridge downtime shouldn't cause permanent data gaps when historical data is available.

**Scenarios**:
- Bridge offline for period
- Recovery and backfill
- Gap detection

**Verification**:
- Graph endpoint used for history
- Gaps detected and filled
- No duplicate historical entries

**Gap Reference**: GAP-LIBRELINK-002

---

### REQ-LIBRELINK-003: Trend Arrow Mapping Documentation

**Statement**: nightscout-librelink-up MUST document the 5-to-9 trend arrow mapping with precision loss.

**Rationale**: LibreLink only provides 5 trend values vs Nightscout's 9, causing precision loss for extreme trends.

**Scenarios**:
- Trend value 1 mapping
- Trend value 5 mapping
- Documentation review

**Verification**:
- Mapping table documented
- Precision loss noted
- No false Double arrows

**Gap Reference**: GAP-LIBRELINK-003

---

## LoopFollow Requirements

---

### REQ-LOOPFOLLOW-001: V3 API Support

**Statement**: LoopFollow SHOULD support Nightscout API v3 for improved filtering and real-time features.

**Rationale**: V3 provides server-side filtering, sync identity, and enhanced query capabilities.

**Scenarios**:
- Entry fetch via v3
- Treatment fetch via v3
- Devicestatus fetch via v3

**Verification**:
- V3 endpoints used
- Filtering via query parameters
- Performance improvement measured

**Gap Reference**: GAP-LOOPFOLLOW-001

---

### REQ-LOOPFOLLOW-002: Real-Time Push Support

**Statement**: LoopFollow SHOULD implement WebSocket or SSE for real-time data updates.

**Rationale**: Polling causes delays and higher resource usage vs push-based updates.

**Scenarios**:
- WebSocket connection
- SSE subscription
- Fallback to polling

**Verification**:
- Push notification received
- Latency vs polling measured
- Battery impact assessed

**Gap Reference**: GAP-LOOPFOLLOW-002

---

### REQ-LOOPFOLLOW-003: Extensible EventType Handling

**Statement**: LoopFollow SHOULD implement extensible eventType handling for unknown treatment types.

**Rationale**: Hardcoded eventType matching silently fails for new treatment types from Loop/Trio/AAPS.

**Scenarios**:
- Unknown eventType received
- Fallback display/handling
- Dynamic category assignment

**Verification**:
- Unknown type logged
- Fallback display rendered
- No silent data loss

**Gap Reference**: GAP-LOOPFOLLOW-003

---

## LoopCaregiver Requirements

---

### REQ-LOOPCAREGIVER-001: Multi-AID Target Support

**Statement**: LoopCaregiver SHOULD abstract the command layer to support multiple AID targets (Loop, Trio, AAPS).

**Rationale**: Loop-only support fragments caregiver experience across AID systems.

**Scenarios**:
- Loop target commands
- Trio target commands
- AAPS target commands

**Verification**:
- Target abstraction exists
- At least 2 targets supported
- Command translation works

**Gap Reference**: GAP-LOOPCAREGIVER-001

---

### REQ-LOOPCAREGIVER-002: V2 Commands Mainline Merge

**Statement**: Remote Commands 2.0 features (status tracking) SHOULD be merged to mainline branches.

**Rationale**: Experimental branches increase deployment complexity and maintenance burden.

**Scenarios**:
- Command status tracking
- Mainline branch support
- No special branch required

**Verification**:
- Features in mainline
- Standard deployment works
- Status tracking functional

**Gap Reference**: GAP-LOOPCAREGIVER-002

---

### REQ-LOOPCAREGIVER-003: Standard Command API

**Statement**: Remote commands SHOULD use a standard Nightscout API endpoint rather than proprietary push notification format.

**Rationale**: Standard API enables interoperability and command history in Nightscout.

**Scenarios**:
- Command via API endpoint
- Command history query
- Cross-system interoperability

**Verification**:
- API endpoint documented
- Command history accessible
- Non-Loop clients can issue commands

**Gap Reference**: GAP-LOOPCAREGIVER-003

---
