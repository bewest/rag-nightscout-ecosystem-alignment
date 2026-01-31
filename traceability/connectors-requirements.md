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

### REQ-BRIDGE-001: Core Event Parity

**Statement**: SignalR→Socket.IO bridges MUST translate all core events: `dataUpdate`, `alarm`, `urgent_alarm`, `clear_alarm`, `announcement`, `notification`, `create`, `update`, `delete`.

**Rationale**: Legacy clients (Loop, AAPS, xDrip+) depend on these events for real-time updates.

**Scenarios**:
- SGV entry created → `create` event received by Socket.IO clients
- Alarm triggered → `alarm` or `urgent_alarm` event received
- Treatment updated → `update` event with colName/doc structure

**Verification**:
- Connect legacy Socket.IO client
- Trigger each event type on server
- Verify client receives correctly formatted event

**Gap Reference**: GAP-NOCTURNE-003, [Analysis](../docs/10-domain/nocturne-signalr-bridge-analysis.md)

---

### REQ-BRIDGE-002: SGV Data Format Translation

**Statement**: Bridges MUST normalize SGV data to include `_id`, `sgv`, `date`, `dateString`, `direction`, `type` fields expected by legacy clients.

**Rationale**: Legacy clients parse specific field names; Nocturne uses different internal field names.

**Scenarios**:
- `id` → `_id`
- `value` → `sgv`
- `timestamp` → `date`
- Missing `dateString` → computed from date

**Verification**:
- Send Nocturne-format SGV via SignalR
- Verify Socket.IO client receives cgm-remote-monitor format

**Gap Reference**: [Analysis](../docs/10-domain/nocturne-signalr-bridge-analysis.md)

---

### REQ-BRIDGE-003: Event Ordering Preservation

**Statement**: Bridges MUST preserve event ordering within each event type.

**Rationale**: Out-of-order glucose readings could confuse trend calculations and displays.

**Scenarios**:
- Multiple `dataUpdate` events sent in sequence
- Bridge delivers in same sequence
- Clients process in order

**Verification**:
- Send 10 sequential SGV readings
- Verify client receives in same order
- No reordering observed

**Gap Reference**: [Analysis](../docs/10-domain/nocturne-signalr-bridge-analysis.md)

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

## Algorithm Conformance Requirements

---

### REQ-OREF-CONFORM-001: Cross-Implementation IOB Equivalence

**Statement**: Rust oref implementations MUST produce IOB values within 0.01 U tolerance of JS oref0 for identical inputs.

**Rationale**: Algorithm drift between implementations causes inconsistent dosing predictions and user confusion.

**Scenarios**:
- Bilinear curve at t=0, t=peak, t=DIA
- Exponential rapid-acting curve
- Exponential ultra-rapid curve

**Verification**:
- Run conformance tests in `conformance/scenarios/nocturne-oref/iob-tests.yaml`
- Compare output values within tolerance
- All test cases pass

**Gap Reference**: GAP-OREF-CONFORMANCE-003

---

### REQ-OREF-CONFORM-002: Peak Time Validation

**Statement**: oref implementations SHOULD validate peak time parameters against curve-specific bounds.

**Rationale**: Invalid peak times can produce unexpected insulin action curves.

**Peak Time Bounds**:
| Curve | Min | Max |
|-------|-----|-----|
| Rapid-acting | 50 min | 120 min |
| Ultra-rapid | 35 min | 100 min |

**Verification**:
- Pass out-of-bounds peak time
- Implementation either clamps or rejects
- No undefined behavior

**Gap Reference**: GAP-OREF-CONFORMANCE-001

---

### REQ-OREF-CONFORM-003: COB Algorithm Equivalence

**Statement**: Rust oref COB calculation MUST match JS oref0 deviation-based algorithm.

**Rationale**: COB drives carb absorption and prediction curves across all oref-based systems.

**Algorithm Steps**:
1. Bucket glucose to 5-minute intervals
2. Calculate BGI from IOB activity
3. Deviation = actual delta - expected BGI
4. Carb impact = max(deviation, min_5m_carbimpact)
5. Absorbed = CI × CR / ISF

**Verification**:
- Provide identical glucose + treatment history
- Compare carbs_absorbed within tolerance
- All deviation calculations match

**Gap Reference**: GAP-OREF-CONFORMANCE-003

---

## Nocturne Connector Coordination Requirements

---

### REQ-CONNECT-010: DataSource Tagging

**Statement**: Connectors MUST tag all submitted data with their `data_source` identifier.

**Rationale**: Enables filtering, auditing, and cleanup by data origin.

**Verification**: Query entries by `data_source`, verify connector attribution.

**Source**: [Connector Coordination Analysis](../docs/10-domain/nocturne-connector-coordination.md)

**Status**: ✅ Implemented

---

### REQ-CONNECT-011: Resilient Polling

**Statement**: Connectors SHOULD implement adaptive polling with fast reconnection and exponential backoff.

**Rationale**: Balances quick recovery with API rate-limit respect.

**Polling Modes**:
| State | Interval | Trigger |
|-------|----------|---------|
| Healthy | 5 min (config) | Success |
| Disconnected | 10 sec | First failure |
| Extended | Backoff to 5 min | 30+ failures |

**Verification**: 
- Disconnect network, verify 10s polling begins
- After 30 failures, verify backoff increases

**Source**: [Connector Coordination Analysis](../docs/10-domain/nocturne-connector-coordination.md)

**Status**: ✅ Implemented

---

### REQ-CONNECT-012: Incremental Sync

**Statement**: Connectors SHOULD track last successful sync timestamp and only fetch new data.

**Rationale**: Reduces API load and bandwidth; enables backfill on reconnection.

**Verification**: 
- Initial sync fetches all data in range
- Subsequent syncs only fetch new records

**Source**: [Connector Coordination Analysis](../docs/10-domain/nocturne-connector-coordination.md)

**Status**: ✅ Implemented

---


## Node.js & Dependency Requirements

---

### REQ-NODE-001: Minimum Node.js LTS

**Statement**: All Nightscout JavaScript projects MUST specify a currently-supported Node.js LTS version in `engines.node`.

**Rationale**: EOL Node.js versions receive no security updates, leaving users vulnerable.

**Current LTS Versions** (2026-01-30):
- Node 24: EOL 2028-04-30
- Node 22: EOL 2027-04-30
- Node 20: EOL 2026-04-30

**Verification**: 
- CI matrix includes minimum and latest LTS
- `engines.node` specifies supported version

**Gap Reference**: GAP-NODE-001

**Source**: [Node.js LTS Upgrade Analysis](../docs/10-domain/node-lts-upgrade-analysis.md)

---

### REQ-NODE-002: No Deprecated Dependencies

**Statement**: Projects SHOULD NOT depend on packages deprecated more than 2 years.

**Rationale**: Deprecated packages receive no security updates and may break on newer Node.js.

**Known Violations**:
- `request` package (deprecated 2020-02-11)

**Verification**: 
- `npm audit` in CI pipeline
- Dependency age check

**Gap Reference**: GAP-NODE-002

**Source**: [Node.js LTS Upgrade Analysis](../docs/10-domain/node-lts-upgrade-analysis.md)

---

### REQ-NODE-003: Engines Field Required

**Statement**: All npm packages MUST include `engines.node` field in package.json.

**Rationale**: Enables npm to warn users of incompatible Node.js versions during install.

**Verification**: 
- package.json lint check
- npm install on unsupported version fails

**Gap Reference**: GAP-NODE-003

**Source**: [Node.js LTS Upgrade Analysis](../docs/10-domain/node-lts-upgrade-analysis.md)


---

### REQ-BRIDGE-001: Bridge Consolidation into nightscout-connect

**Statement**: Legacy bridge packages SHOULD be deprecated in favor of nightscout-connect.

**Rationale**: 
- Reduces maintenance burden (3 packages → 1)
- Eliminates deprecated dependencies (`request` package)
- Provides consistent state machine architecture (xstate)
- Enables feature reuse across vendors

**Affected Packages**:
- share2nightscout-bridge → DEPRECATED
- minimed-connect-to-nightscout → DEPRECATED

**Migration Path**: [Bridge Deprecation Plan](../docs/10-domain/bridge-deprecation-plan.md)

**Verification**: 
- Legacy packages archived on GitHub
- npm deprecation warnings published
- Documentation updated

**Gap Reference**: GAP-NODE-002, GAP-NODE-003

**Source**: [Bridge Deprecation Plan](../docs/10-domain/bridge-deprecation-plan.md)

---

## Verification Tooling Requirements

### REQ-VERIFY-001: Multi-Language Code Reference Validation

**Statement**: The verification system SHOULD support validating code references across Swift, JavaScript, Kotlin, and Java source files.

**Rationale**: The Nightscout ecosystem spans multiple languages; documentation references must be verifiable regardless of language.

**Scenarios**:
- Validate `externals/Trio/...swift:123` line anchor
- Validate `externals/cgm-remote-monitor/...js:456` symbol reference
- Report missing or moved code across languages

**Verification**:
- Run `verify_refs.py` on mixed-language references
- Confirm line validation works for all languages
- Confirm semantic validation works for JS/TS (tsserver available)

**Gap Reference**: GAP-VERIFY-001

**Source**: [lsp-environment-check.md](../docs/10-domain/lsp-environment-check.md)

**Status**: ⚠️ Partial (JS/TS ready, Swift/Kotlin limited)

---

### REQ-VERIFY-002: Cross-Language Algorithm Conformance

**Statement**: Algorithm conformance runners MUST exist for at least 2 implementations to enable cross-language validation.

**Rationale**: Different implementations (JS oref0, Kotlin AAPS, Swift Loop) should produce equivalent outputs for identical inputs; divergence may indicate bugs or undocumented changes.

**Scenarios**:
- Run 85 test vectors through oref0-runner.js and aaps-runner.kt
- Compare outputs for numerical precision (0.01 tolerance)
- Document intentional divergence vs bugs

**Verification**:
- `make conformance-algorithms` runs multiple runners
- Cross-comparison report generated
- >80% match rate for shared feature set

**Gap Reference**: GAP-VERIFY-002

**Source**: [cross-platform-testing-research.md](../docs/10-domain/cross-platform-testing-research.md)

**Status**: ❌ Not implemented (only oref0 runner exists)

---

### REQ-VERIFY-003: Conformance Vector Currency

**Statement**: Conformance test vectors SHOULD be refreshed quarterly to cover new algorithm features.

**Rationale**: Algorithm implementations evolve; test vectors must keep pace with new features (Dynamic ISF, SMB scheduling, sigmoid formulas).

**Scenarios**:
- Extract new vectors from AAPS 3.x replay tests
- Add vectors for Trio-specific features (SMB scheduling, override integration)
- Validate coverage of all documented algorithm features

**Verification**:
- Vector extraction date tracked in `conformance/vectors/README.md`
- Coverage report shows >90% of documented features have vectors
- Quarterly review process documented

**Gap Reference**: GAP-VERIFY-003

**Source**: [cross-platform-testing-research.md](../docs/10-domain/cross-platform-testing-research.md)

**Status**: ⚠️ Partial (vectors exist but dated 2026-01-29)

---

### REQ-VERIFY-004: CI Matrix Coverage

**Statement**: The CI pipeline MUST run static analysis on all PRs and conformance tests on algorithm-related changes.

**Rationale**: Automated verification prevents documentation drift and algorithm regression.

**Scenarios**:
- PR to `docs/` triggers static verification (refs, terminology)
- PR to `conformance/` or algorithm docs triggers full conformance suite
- macOS runner for Swift verification (10x cost but necessary)

**Verification**:
- GitHub Actions workflow with matrix (Linux + macOS)
- CI blocks merges with failing verification
- Badge in README shows verification status

**Gap Reference**: GAP-VERIFY-002, GAP-VERIFY-004

**Source**: [cross-platform-testing-research.md](../docs/10-domain/cross-platform-testing-research.md)

**Status**: ⚠️ Partial (Linux CI exists, macOS not configured)

---

### REQ-VERIFY-005: Accuracy Reporting Dashboard

**Statement**: The verification system SHOULD provide a unified accuracy dashboard showing claim verification status by category.

**Rationale**: Single-command visibility into documentation quality enables prioritization and trend tracking.

**Scenarios**:
- Run `make verify-accuracy` to see breakdown
- Categories: code refs, algorithm claims, cross-language parity
- Historical tracking for regression detection

**Verification**:
- `tools/accuracy_dashboard.py` exists ✅
- Output shows accuracy percentage per claim type ✅
- CI generates accuracy badge (pending CI integration)

**Gap Reference**: GAP-VERIFY-004

**Source**: [cross-platform-testing-research.md](../docs/10-domain/cross-platform-testing-research.md)

**Status**: ✅ Implemented (2026-01-31)
