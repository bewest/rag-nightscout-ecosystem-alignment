# Connectors Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

---

### GAP-CONNECT-001: v1 API Only for Output

**Description**: The REST output driver only supports Nightscout API v1, missing v3 UPSERT and validation benefits.

**Affected Systems**: nightscout-connect

**Impact**: 
- Duplicate records on re-runs (no UPSERT)
- No identifier-based sync identity
- No server-side validation

**Source Code**: `lib/outputs/nightscout.js:35,48`

**Remediation**: Add v3 output driver using `/api/v3/entries` with identifier field.

---

---

### GAP-CONNECT-002: Inconsistent Source Data Coverage

**Description**: Only Minimed CareLink source uploads all 3 collections (entries, treatments, devicestatus). Other sources only upload 1 collection type.

**Affected Systems**: nightscout-connect

**Coverage Matrix**:
| Source | entries | treatments | devicestatus |
|--------|---------|------------|--------------|
| Dexcom Share | ✅ | ❌ | ❌ |
| LibreLinkUp | ✅ | ❌ | ❌ |
| Nightscout | ✅ | ❌ | ❌ |
| Glooko | ❌ | ✅ | ❌ |
| Minimed | ✅ | ✅ | ✅ |

**Impact**: Incomplete data for most cloud platform sources.

**Remediation**: Extend sources to fetch all available collection types from vendor APIs.

---

---

### GAP-CONNECT-003: No Client-Side Deduplication

**Description**: Output drivers have no sync identity generation or deduplication logic, relying entirely on server-side behavior.

**Affected Systems**: nightscout-connect

**Impact**:
- Re-runs create duplicate records
- No idempotent uploads
- Server-side dedup varies by API version

**Source Code**: `lib/outputs/nightscout.js:77-79`

**Remediation**: Generate UUID v5 identifiers client-side matching Nightscout sync identity spec, use v3 UPSERT.

---

## Carb Absorption Gaps

---

### GAP-NOCTURNE-001: V4 endpoints are Nocturne-specific

**Scenario**: Cross-project API compatibility

**Description**: Nocturne introduces V4 API endpoints (`/api/v4/...`) that provide enhanced functionality not present in cgm-remote-monitor. These endpoints have no cross-project standard.

**Affected Systems**: Nocturne, any clients adopting V4

**Source**: `externals/nocturne/src/API/Nocturne.API/Controllers/V4/`

**Impact**:
- Clients using V4 endpoints won't work with cgm-remote-monitor
- No interoperability guarantee for V4 features
- Potential ecosystem fragmentation

**Possible Solutions**:
1. Document V4 endpoints as optional extensions
2. Propose V4 endpoints as Nightscout RFC
3. Mark V4 as Nocturne-only, maintain V3 parity

**Status**: Under discussion

---

---

### GAP-NOCTURNE-002: Rust oref implementation may diverge

**Scenario**: Algorithm consistency across implementations

**Description**: Nocturne contains a native Rust implementation of oref algorithms (`src/Core/oref/`). This independent implementation may produce different results than the JavaScript oref0/oref1.

**Affected Systems**: Nocturne, any system comparing algorithm outputs

**Source**: `externals/nocturne/src/Core/oref/Cargo.toml`

**Impact**:
- Potential calculation differences (IOB, COB, dosing)
- Difficult to debug cross-implementation issues
- No conformance test suite between implementations

**Possible Solutions**:
1. Create cross-implementation test vectors
2. Document any intentional algorithm differences
3. Generate reference outputs for comparison

**Status**: Under discussion

---

---

### GAP-NOCTURNE-003: SignalR to Socket.IO bridge adds latency

**Scenario**: Real-time data streaming

**Description**: Nocturne uses SignalR for real-time updates, with a bridge to Socket.IO for legacy client compatibility. This adds latency and complexity.

**Affected Systems**: Nocturne, Socket.IO clients (xDrip+, etc.)

**Source**: `externals/nocturne/src/Web/packages/bridge/`

**Impact**:
- Additional latency for real-time glucose updates
- Extra failure point in data pipeline
- Clients must support either SignalR or use bridge

**Possible Solutions**:
1. Maintain parallel Socket.IO and SignalR endpoints
2. Measure and document latency impact
3. Provide native SignalR clients for major platforms

**Status**: Documented - [Detailed analysis](../docs/10-domain/nocturne-signalr-bridge-analysis.md)

**Measured Impact** (2026-01-30): 5-10ms additional latency per message - acceptable for CGM data.

---

### GAP-BRIDGE-001: Missing `clients` Event in Bridge

**Scenario**: Displaying connected client count

**Description**: Nocturne SignalR→Socket.IO bridge does not forward client count updates. cgm-remote-monitor emits `clients` event when watchers join/leave.

**Affected Systems**: Nocturne bridge, legacy web UIs

**Source**: `externals/nocturne/src/Web/packages/bridge/src/lib/socketio-server.ts`

**Impact**:
- Legacy web UI may show incorrect watcher count
- No visibility into connected clients

**Possible Solutions**:
1. Add `clients` event emission to bridge
2. Use SignalR-native client count mechanism

**Status**: Documented

---

### GAP-BRIDGE-002: No Compression in Bridge

**Scenario**: High-bandwidth real-time streaming

**Description**: Nocturne bridge does not enable Socket.IO compression. cgm-remote-monitor uses `.compress(true)` on broadcasts.

**Affected Systems**: Nocturne bridge, mobile clients on metered connections

**Source**: `externals/cgm-remote-monitor/lib/server/websocket.js:136` vs `externals/nocturne/src/Web/packages/bridge/`

**Impact**:
- Higher bandwidth usage
- May affect mobile data consumption

**Possible Solutions**:
1. Enable compression in Socket.IO server config
2. Add `.compress(true)` to broadcast calls

**Status**: Documented

---

### GAP-TCONNECT-001: No API v3 Support

**Scenario**: Syncing Tandem pump data to Nightscout with deduplication

**Description**: tconnectsync uses Nightscout API v1 only. Does not leverage v3 deduplication or identifier fields.

**Source**: `externals/tconnectsync/tconnectsync/nightscout.py`

**Impact**:
- No automatic deduplication on Nightscout side
- Re-syncs may create duplicate treatments
- Missing `identifier` field for sync tracking

**Remediation**: Add v3 API support with proper identifiers.

**Status**: Enhancement candidate

---

---

### GAP-TCONNECT-002: Limited Control-IQ Algorithm Data

**Scenario**: Debugging Control-IQ decisions in Nightscout

**Description**: While pump events are synced, detailed Control-IQ algorithm decisions (predicted glucose, auto-basal adjustments) are not extracted or uploaded to devicestatus.

**Source**: `externals/tconnectsync/tconnectsync/api/controliq.py`

**Impact**:
- Cannot visualize Control-IQ decision-making in Nightscout
- Limited debugging of algorithm behavior
- No prediction curves like AAPS/Loop provide

**Remediation**: Extract and upload to devicestatus if available from API.

**Status**: Enhancement candidate

---

---

### GAP-TCONNECT-003: No Real-Time Sync

**Scenario**: Real-time monitoring of Tandem pump via Nightscout

**Description**: tconnectsync is batch-based; requires manual or cron execution. No push/webhook capability from t:connect cloud.

**Source**: tconnectsync architecture (pull-based)

**Impact**:
- Delay between pump events and Nightscout visibility
- Not suitable for real-time caregiver monitoring
- Must run periodically via cron

**Remediation**: Document as platform limitation; t:connect API doesn't support push.

**Status**: Platform limitation

---

## LibreLink Up Bridge Gaps

---

### GAP-TEST-001: No cross-project test harness for Swift

**Scenario**: Algorithm validation across implementations

**Description**: No mechanism to run Loop/Trio algorithm tests against Nightscout data or compare with AAPS/oref results.

**Evidence**:
- Loop and Trio both have 200+ test files but isolated to their projects
- No shared test fixtures between Swift and JavaScript implementations
- Cannot validate algorithm consistency across implementations

**Impact**:
- Algorithm divergence may go undetected
- No regression testing for cross-system data compatibility
- Cannot verify prediction accuracy across implementations

**Possible Solutions**:
1. Extract algorithm packages with shared test fixtures
2. Create JSON test vectors that all implementations consume
3. Build cross-language comparison harness

**Status**: Documented

**Related**:
- [Cross-project Testing Plan](../docs/sdqctl-proposals/cross-project-testing-plan.md)

---

---

### GAP-TEST-002: LoopKit Package.swift incomplete

**Scenario**: SPM-based cross-platform testing

**Description**: LoopKit Package.swift exists but is explicitly marked as non-functional due to bundle resource issues.

**Evidence**:
```swift
// LoopKit/Package.swift:4-8
// *************** Not complete yet, do not expect this to work! ***********************
// There are issues with how test fixtures are copied into the bundle...
```

**Impact**:
- Cannot use SPM for cross-platform testing
- No Linux/macOS test execution via `swift test`
- Blocks algorithm extraction strategy

**Possible Solutions**:
1. Fix resource copying in Package.swift
2. Extract algorithm-only package without resources
3. Use Xcode-only testing (current state)

**Status**: Documented

**Related**:
- [Cross-project Testing Plan](../docs/sdqctl-proposals/cross-project-testing-plan.md)

---

---

### GAP-TEST-003: Loop uses outdated Travis CI

**Scenario**: Modern CI for Loop tests

**Description**: Loop uses Travis CI with Xcode 12.4 (2021). No GitHub Actions workflow for tests. Trio has modern GitHub Actions.

**Evidence**:
```yaml
# Loop/.travis.yml
osx_image: xcode12.4
```

**Impact**:
- Test infrastructure may be broken or outdated
- Missing modern Xcode/iOS features
- No parity with Trio's CI approach

**Possible Solutions**:
1. Migrate to GitHub Actions with modern Xcode
2. Add unit_tests.yml similar to Trio's workflow
3. Update to current macOS/Xcode versions

**Status**: Documented

**Related**:
- [Cross-project Testing Plan](../docs/sdqctl-proposals/cross-project-testing-plan.md)

---

### GAP-TEST-004: No shared test vectors for algorithm validation

**Scenario**: Cross-project algorithm parity verification

**Description**: No standardized test vector format for validating IOB/COB/determineBasal calculations across oref0, Loop, AAPS, and Trio.

**Current State**:
- oref0 has 85 test vectors in `conformance/runners/oref0-runner.js`
- No equivalent for Swift (Loop, Trio) or Kotlin (AAPS)
- Each project tests in isolation

**Impact**:
- Cannot verify algorithm parity across projects
- No regression detection when forking code
- Algorithm drift goes undetected

**Possible Solutions**:
1. Create YAML-based shared vector format
2. Implement language-specific runners (Swift, Kotlin)
3. Add algorithm parity reports to CI

**Status**: Design complete

**Related**:
- [Cross-Platform Testing Infrastructure Design](../docs/10-domain/cross-platform-testing-infrastructure-design.md)

---

### GAP-TEST-005: No BLE/CGM mock infrastructure

**Scenario**: Hardware-independent testing

**Description**: iOS apps (Loop, Trio, xDrip4iOS) have no protocol-based abstractions for BLE and CGM managers, making unit testing impossible without hardware.

**Current State**:
- All BLE code directly imports CoreBluetooth
- No dependency injection for CGM/pump managers
- Tests require iOS simulator at minimum

**Impact**:
- Cannot run CGM packet parsing tests on Linux
- CI requires expensive macOS runners
- BLE protocol bugs discovered late

**Possible Solutions**:
1. Define `BluetoothManagerProtocol` abstraction
2. Create `MockBluetoothManager` for tests
3. Extract packet parsing to pure Swift modules

**Status**: Design complete

**Related**:
- [Cross-Platform Testing Infrastructure Design](../docs/10-domain/cross-platform-testing-infrastructure-design.md)

---

## nightscout-connect Design Review Gaps

---

### GAP-CONNECT-004: No Test Suite

**Description**: Package has `"test": "echo \"Error: no test specified\" && exit 1"` - no automated tests despite complex XState state machine logic.

**Affected Systems**: nightscout-connect

**Impact**:
- Regressions possible when adding vendors or upgrading XState
- No confidence in refactoring
- Cannot verify behavior across state transitions

**Remediation**: Add `@xstate/test` model-based tests + integration tests for vendor drivers.

**Source**: `package.json:13-14`

---

### GAP-CONNECT-005: No TypeScript Types

**Description**: Pure JavaScript with no type definitions for machine contexts, events, or vendor interfaces.

**Affected Systems**: nightscout-connect

**Impact**:
- Harder to maintain and refactor safely
- No IDE autocomplete for complex machine contexts
- Error-prone vendor implementation

**Remediation**: Add TypeScript or `.d.ts` type definitions for FetchContext, SessionContext, and VendorDriver interfaces.

**Source**: `lib/machines/*.js` (all files)

---

### GAP-CONNECT-006: Brittle Adapter Pattern

**Description**: Per machines.md, "the builder and the adapter preludes at the beginning of the machine sources are brittle."

**Affected Systems**: nightscout-connect

**Impact**:
- Coupling between vendor code and machine configuration
- Inconsistent naming across adapters
- Promises mixed with utilities in impl objects

**Remediation**: Define formal VendorDriver interface contract with validation.

**Source**: `machines.md:163-169`

---

### GAP-TCONNECT-004: No Trend Direction from t:connect

**Description**: The t:connect API does not provide glucose trend direction. CGM entries uploaded to Nightscout via tconnectsync will lack the `direction` field.

**Affected Systems**: tconnectsync, Nightscout

**Impact**:
- No trend arrows for t:connect-sourced CGM data in Nightscout UI
- Reduced situational awareness for users viewing data
- Loop/AAPS algorithms may not receive trend data if sourced from t:connect

**Remediation**: Calculate direction from consecutive readings if needed, or document as limitation.

**Source**: `mapping/tconnectsync/treatments.md`

---

## share2nightscout-bridge Gaps

---

### GAP-SHARE-001: No Nightscout API v3 Support

**Description**: share2nightscout-bridge uses Nightscout API v1 only. Does not set `identifier`, `srvModified`, or other v3 fields.

**Affected Systems**: share2nightscout-bridge, Nightscout

**Impact**:
- No server-side deduplication
- Duplicates possible on bridge restart or overlap
- Cannot track sync state across restarts

**Remediation**: Add v3 API support with proper identifiers.

**Source**: `mapping/share2nightscout-bridge/entries.md`

---

### GAP-SHARE-002: No Backfill/Gap Detection Logic

**Description**: share2nightscout-bridge does not detect gaps in CGM data. If the bridge is offline, missed readings are not backfilled when it comes back online.

**Affected Systems**: share2nightscout-bridge, Nightscout

**Impact**:
- Data gaps during bridge downtime
- No automatic recovery of missed readings
- Users must manually backfill or accept gaps

**Remediation**: Add gap detection and backfill logic using `minutes` parameter.

**Source**: `mapping/share2nightscout-bridge/entries.md`

---

### GAP-SHARE-003: Hardcoded Application ID

**Description**: share2nightscout-bridge uses a hardcoded Dexcom application ID (`d89443d2-327c-4a6f-89e5-496bbb0317db`). If Dexcom revokes or changes this ID, the bridge will break.

**Affected Systems**: share2nightscout-bridge

**Impact**:
- Single point of failure
- No user-configurable alternative
- Dependent on Dexcom not revoking the ID

**Remediation**: Make application ID configurable, or use official Dexcom developer credentials.

**Source**: `mapping/share2nightscout-bridge/api.md`

---

## nightscout-librelink-up Gaps

---

### GAP-LIBRELINK-001: No Nightscout API v3 Support

**Description**: nightscout-librelink-up has a v3 client stub that throws "Not implemented". Only v1 API is functional.

**Affected Systems**: nightscout-librelink-up, Nightscout

**Impact**:
- No server-side deduplication
- No `identifier` field for sync tracking
- Duplicates possible on bridge restart

**Remediation**: Implement v3 client with proper identifiers.

**Source**: `mapping/nightscout-librelink-up/entries.md`

---

### GAP-LIBRELINK-002: No Historical Backfill

**Description**: While GraphResponse interface exists for historical data, only current readings are uploaded. No catch-up mechanism for missed readings.

**Affected Systems**: nightscout-librelink-up, Nightscout

**Impact**:
- Data gaps if bridge is offline
- No automatic recovery of missed readings
- Users must manually backfill

**Remediation**: Add optional historical fetch using graph endpoint.

**Source**: `mapping/nightscout-librelink-up/entries.md`

---

### GAP-LIBRELINK-003: Trend Arrow Limited to 5 Values

**Description**: LibreLink Up provides only 5 trend values (1-5) vs Nightscout's 9. No DoubleUp/DoubleDown available.

**Affected Systems**: nightscout-librelink-up, Nightscout

**Impact**:
- Loss of precision for rapid glucose changes
- Libre sensors may not report extreme trends
- Data consumers may expect full range

**Remediation**: Document as sensor/API limitation; map to closest available direction.

**Source**: `mapping/nightscout-librelink-up/entries.md`

---

## LoopFollow Gaps

---

### GAP-LOOPFOLLOW-001: API v1 Only

**Description**: LoopFollow uses Nightscout API v1 exclusively. No v3 API support implemented.

**Affected Systems**: LoopFollow, Nightscout

**Impact**:
- Cannot leverage v3 features (identifiers, server-side filtering)
- No sync identity awareness
- May miss real-time updates available in v3

**Remediation**: Add v3 API support for improved filtering and real-time features.

**Source**: `docs/10-domain/loopfollow-deep-dive.md`

---

### GAP-LOOPFOLLOW-002: No WebSocket/Server-Sent Events

**Description**: LoopFollow uses polling for data updates. No real-time push support via WebSocket or SSE.

**Affected Systems**: LoopFollow

**Impact**:
- Delays between data availability and display
- Higher battery/network usage from polling
- Not truly real-time monitoring

**Remediation**: Implement WebSocket or SSE listener for real-time updates.

**Source**: `docs/10-domain/loopfollow-deep-dive.md`

---

### GAP-LOOPFOLLOW-003: Treatment eventType Hardcoding

**Description**: Treatment categorization relies on exact string matching of eventTypes. Unknown types logged but not displayed.

**Affected Systems**: LoopFollow

**Impact**:
- New eventTypes from Loop/Trio/AAPS may be missed
- Requires code update for new treatment types
- Silent failures for unrecognized treatments

**Remediation**: Add extensible eventType handling or periodic sync with Nightscout eventType registry.

**Source**: `docs/10-domain/loopfollow-deep-dive.md`

---

## LoopCaregiver Gaps

---

### GAP-LOOPCAREGIVER-001: Loop-Only Support

**Description**: LoopCaregiver only works with Loop. No support for Trio, OpenAPS, or AAPS.

**Affected Systems**: LoopCaregiver, Trio, OpenAPS, AAPS

**Impact**:
- Trio users must use different apps (LoopFollow + TRC)
- No unified caregiver experience across AID systems
- Parallel development of similar features

**Remediation**: Abstract command layer to support multiple AID targets.

**Source**: `docs/10-domain/loopcaregiver-deep-dive.md`

---

### GAP-LOOPCAREGIVER-002: Experimental V2 Commands

**Description**: Remote Commands 2.0 (with status tracking) requires non-mainline branches of both Nightscout and Loop.

**Affected Systems**: LoopCaregiver, Nightscout, Loop

**Impact**:
- Most users don't have command status tracking
- Special deployment complexity
- Branch maintenance burden

**Remediation**: Merge V2 features to mainline branches.

**Source**: `docs/10-domain/loopcaregiver-deep-dive.md`

---

### GAP-LOOPCAREGIVER-003: No Standard Command API

**Description**: Commands use proprietary push notification format, not a standard Nightscout API endpoint.

**Affected Systems**: LoopCaregiver, Nightscout

**Impact**:
- Not interoperable with other systems
- Tightly coupled to Loop implementation
- No command history in standard Nightscout

**Remediation**: Define standard remote command API in Nightscout.

**Source**: `docs/10-domain/loopcaregiver-deep-dive.md`

---

## Nocturne Algorithm Conformance

---

### GAP-OREF-CONFORMANCE-001: Rust oref Peak Time Validation

**Description**: Rust oref implementation accepts peak time as parameter without validation, unlike JS oref0 which validates and clamps per curve type.

**Affected Systems**: Nocturne, oref0

**JS oref0 behavior**:
- Rapid-acting: clamps peak to 50-120 minutes
- Ultra-rapid: clamps peak to 35-100 minutes

**Rust behavior**: Accepts any value passed by caller.

**Impact**:
- Invalid peak times could produce unexpected results
- Caller must validate before passing to Rust

**Remediation**: Add peak time validation to Rust implementation or document caller responsibility.

**Source**: 
- JS: `externals/oref0/lib/iob/calculate.js:86-116`
- Rust: `externals/nocturne/src/Core/oref/src/insulin/calculate.rs:112`

**Status**: Minor divergence (defensive)

---

### GAP-OREF-CONFORMANCE-002: Rust oref Small Dose Classification

**Description**: Rust oref classifies insulin doses < 0.1 U as basal adjustments, providing basal_iob/bolus_iob breakdown. JS oref0 doesn't distinguish.

**Affected Systems**: Nocturne, oref0

**Impact**:
- Additional data available in Rust output
- Not a conformance issue (additive feature)

**Source**: `externals/nocturne/src/Core/oref/src/iob/total.rs:88-94`

**Status**: Enhancement (no conformance issue)

---

### GAP-OREF-CONFORMANCE-003: VERIFIED EQUIVALENT ✅

**Description**: Nocturne Rust oref is algorithmically equivalent to JS oref0.

**Verification**:
| Component | Status |
|-----------|--------|
| Bilinear IOB | ✅ Same formula, coefficients |
| Exponential IOB | ✅ Same LoopKit formula |
| COB deviation | ✅ Same algorithm |
| Precision | ✅ Both IEEE 754 f64 |

**Conformance Tests**: `conformance/scenarios/nocturne-oref/iob-tests.yaml`

**Source**:
- JS: `externals/oref0/lib/iob/calculate.js`
- Rust: `externals/nocturne/src/Core/oref/src/insulin/calculate.rs`

**Status**: ✅ Verified equivalent

---

## Nocturne Connector Coordination Gaps

---

### GAP-CONNECT-010: No Connector Poll Staggering

**Description**: Nocturne connectors poll independently with no startup jitter or coordination. Multiple connectors may poll simultaneously, causing API load spikes.

**Affected Systems**: Nocturne

**Impact**: 
- Burst of outbound requests at startup
- Potential rate-limiting if all connectors hit APIs simultaneously

**Source**: `src/Connectors/Nocturne.Connectors.Core/Services/ResilientPollingHostedService.cs:62`

**Remediation**: Add startup jitter or stagger connector initialization.

**Status**: Open (minor impact for typical 2-3 connectors)

---

### GAP-CONNECT-011: No Explicit Loop-Back Prevention

**Description**: Nightscout connector does not filter out data that originated from Nocturne. Circular sync possible with misconfigured topology.

**Affected Systems**: Nocturne Nightscout connector

**Impact**: 
- Circular sync possible with bidirectional Nocturne↔Nightscout configuration
- Data may accumulate duplicate sources

**Source**: `src/Connectors/Nocturne.Connectors.Nightscout/Services/NightscoutConnectorService.cs`

**Remediation**: 
1. Filter by `device` or `app` field on fetch
2. Add `enteredBy` exclusion (similar to AAPS `enteredBy[$ne]`)
3. Document recommended topology

**Status**: Open

---

### GAP-CONNECT-012: Cross-Connector Deduplication Delegated to Server

**Description**: Same CGM reading from multiple sources (e.g., Dexcom direct + via upstream Nightscout) handled by server-side deduplication, not connectors.

**Affected Systems**: Nocturne

**Impact**: Relies on server-side dedup which may use different matching criteria than expected.

**Source**: By design - connectors use incremental sync via timestamps

**Remediation**: Document expected behavior; consider connector-side pre-dedup for known overlap scenarios.

**Status**: Documented (by design)

---

## Node.js & Dependency Gaps

---

### GAP-NODE-001: EOL Node.js Versions

**Description**: All JavaScript Nightscout projects specify EOL Node.js versions in `engines` field. cgm-remote-monitor targets Node 16/14 (EOL 2023), share2nightscout-bridge supports Node 8-16.

**Affected Systems**: cgm-remote-monitor, share2nightscout-bridge

**Impact**: 
- Security vulnerabilities unpatched
- No upstream bug fixes
- Hosting provider deprecation warnings
- Incompatibility with modern npm packages

**Remediation**: Upgrade to Node 22 LTS (EOL 2027-04-30).

**Source**: `package.json` engines fields

**Status**: Open

**Analysis**: [node-lts-upgrade-analysis.md](../docs/10-domain/node-lts-upgrade-analysis.md)

---

### GAP-NODE-002: Deprecated `request` Package

**Description**: Both cgm-remote-monitor and share2nightscout-bridge depend on the deprecated `request` package (deprecated 2020-02-11).

**Affected Systems**: cgm-remote-monitor, share2nightscout-bridge

**Impact**:
- No security updates since 2020
- Blocks Node.js upgrades
- Known vulnerabilities

**Remediation**: 
- cgm-remote-monitor: Migrate to axios (already in dependencies)
- share2nightscout-bridge: Deprecate in favor of nightscout-connect

**Source**: 
- `externals/cgm-remote-monitor/package.json`: `"request": "^2.88.2"`
- `externals/share2nightscout-bridge/package.json`: `"request": "^2.88.0"`

**Status**: Open

---

### GAP-NODE-003: Missing engines Field

**Description**: nightscout-connect lacks `engines` field in package.json, making Node.js compatibility unclear to users and npm.

**Affected Systems**: nightscout-connect, nightscout-librelink-up

**Impact**: Users may inadvertently run on incompatible Node versions.

**Remediation**: Add `"engines": { "node": ">=18" }` to package.json.

**Source**: `externals/nightscout-connect/package.json`

**Status**: Open

---

## Verification Tooling Gaps

### GAP-VERIFY-001: No iOS Framework Resolution on Linux

**Description**: Swift LSP (sourcekit-lsp) on Linux cannot resolve iOS-specific frameworks (UIKit, HealthKit, LoopKit).

**Affected Systems**: Trio, Loop, xDrip4iOS, DiaBLE verification

**Evidence**:
- `docs/10-domain/lsp-environment-check.md` - Swift 6.2.3 installed but iOS SDK unavailable
- Xcode projects (`.xcodeproj`) not compatible with SPM-based sourcekit-lsp

**Impact**:
- Cannot verify Swift code references to iOS framework symbols on Linux
- Line-number validation works; semantic analysis does not

**Remediation**:
1. ✅ **PARTIAL**: tree-sitter installed (v0.26.3) for syntax-level queries
2. Defer semantic verification to macOS CI runners
3. Accept line-only validation for Swift on Linux

**Status**: ⚠️ Partially mitigated (tree-sitter provides syntax parsing)

---

### GAP-VERIFY-002: No Cross-Language Algorithm Validation

**Description**: Only JavaScript oref0 has a conformance runner. Kotlin AAPS and Swift Trio/Loop implementations lack automated parity testing.

**Affected Systems**: AAPS (Kotlin), Trio (Swift), Loop (Swift)

**Evidence**:
- `conformance/runners/oref0-runner.js` exists (85 vectors, 31% pass)
- `conformance/runners/aaps-runner.kt` build ready (517 lines, `make aaps-runner`)
- AAPS internal tests compare JS vs Kotlin but aren't integrated with workspace

**Impact**:
- Algorithm divergence between implementations goes undetected
- Dosing differences between apps may affect patient safety
- Documentation claims about "equivalent behavior" are unverified

**Remediation**:
1. ~~Implement `aaps-runner.kt` scaffolding~~ ✅ Done (2026-01-31)
2. ~~Build integration (`make aaps-runner`)~~ ✅ Done (2026-01-31)
3. Integrate AAPS core algorithm dependencies for execution
4. Add Swift runners for macOS CI (Trio, Loop)
5. Cross-compare outputs for same test vectors

**Source**: `docs/10-domain/cross-platform-testing-research.md`

**Status**: In Progress - Kotlin build ready, algorithm execution pending (requires AAPS deps)

---

### GAP-VERIFY-003: Stale Conformance Test Vectors

**Description**: Current 85 test vectors extracted from AAPS may not cover recent algorithm changes (Dynamic ISF, SMB scheduling, TDD weighting).

**Affected Systems**: All algorithm implementations

**Evidence**:
- Vectors extracted 2026-01-29 from AAPS 3.x branch
- oref0 shows 31% pass rate (69% divergent behavior)
- No vectors for sigmoid ISF, SMB scheduling, or Trio-specific features

**Impact**:
- Tests pass but don't validate current algorithm behavior
- New features untested
- False confidence in conformance

**Remediation**:
1. Periodic vector refresh from live AAPS/Trio replay tests
2. Add vectors specifically targeting Dynamic ISF, SMB, autotune
3. Document expected divergence (intentional differences) vs bugs

**Source**: `docs/10-domain/cross-platform-testing-research.md`

**Status**: Open

---

### GAP-VERIFY-004: No Unified Accuracy Dashboard

**Description**: No single-command way to see verification accuracy across all claim types (code refs, algorithm behavior, cross-language parity).

**Affected Systems**: Verification tooling

**Evidence**:
- `make verify` runs multiple tools but doesn't aggregate accuracy
- No tracking of accuracy trends over time
- Different tools report in different formats

**Impact**:
- Cannot quickly assess documentation quality
- Hard to prioritize verification improvements
- No regression detection for claim accuracy

**Remediation**:
1. Create `tools/accuracy_dashboard.py` aggregating all verification outputs
2. Add `make verify-accuracy` target
3. Generate accuracy badge for README

**Source**: `docs/10-domain/cross-platform-testing-research.md`

**Status**: ✅ Addressed (2026-01-31) - `tools/accuracy_dashboard.py` implemented

---

## Apple Watch Gaps

### GAP-WATCH-001: Loop Uses Deprecated ClockKit

**Description**: Loop's `ComplicationController.swift` uses ClockKit which is deprecated in watchOS 9+.

**Affected Systems**: Loop

**Evidence**:
- `WatchApp Extension/ComplicationController.swift` implements `CLKComplicationDataSource`
- ClockKit deprecated in watchOS 9, replacement is WidgetKit
- All other apps have migrated to WidgetKit

**Impact**: 
- Future watchOS versions may remove ClockKit support
- New complication families only available in WidgetKit
- Maintenance burden for deprecated API

**Remediation**: 
1. Migrate to WidgetKit `TimelineProvider` pattern
2. Use `accessoryCircular`, `accessoryRectangular` families
3. Match existing glucose chart functionality

**Source**: `docs/10-domain/apple-watch-complications-survey.md`

**Status**: Open

---

### GAP-WATCH-002: Trio Complication is Icon-Only

**Description**: Trio's watch complication only shows the app icon, not glucose data.

**Affected Systems**: Trio

**Evidence**:
- `Trio Watch Complication/TrioWatchComplication.swift` (106 lines)
- Uses `StaticConfiguration` with `policy: .never`
- Only displays "Trio" label and icon asset

**Impact**: 
- Users cannot see glucose on watch face
- Must open watch app to see glucose
- Inconsistent with Loop experience

**Remediation**: 
1. Add `GlucoseComplicationEntry` with real-time data
2. Implement `TimelineProvider` with glucose refresh
3. Use WCSession data already available

**Source**: `docs/10-domain/apple-watch-complications-survey.md`

**Status**: Open

---

### GAP-WATCH-003: LoopCaregiver Has No Complications

**Description**: LoopCaregiver has watch app but no complications.

**Affected Systems**: LoopCaregiver

**Evidence**:
- `LoopCaregiverWatchApp/` contains only watch app views
- No WidgetKit target in project
- `WatchConnectivityService.swift` already syncs glucose data

**Impact**: 
- Caregivers cannot see glucose on watch face
- Must open watch app for glucose
- Missing feature vs Nightguard

**Remediation**: 
1. Add WidgetKit target to LoopCaregiver
2. Create `GlucoseComplicationProvider` using existing sync
3. Support `accessoryRectangular` for multi-looper display

**Source**: `docs/10-domain/apple-watch-complications-survey.md`

**Status**: Open

---

### GAP-WATCH-004: No Shared Watch Components

**Description**: Each app implements watch sync and complications independently.

**Affected Systems**: Loop, Trio, LoopCaregiver, Nightguard, xDrip4iOS

**Evidence**:
- Loop: `WatchDataManager.swift` + `WatchContext.swift`
- Trio: `WatchManager/` + `TrioWatchComplication.swift`
- xDrip4iOS: `ComplicationSharedUserDefaultsModel.swift`
- Different data models, sync patterns, view implementations

**Impact**: 
- Code duplication across 5+ apps
- Inconsistent UX (different complication families)
- Higher maintenance burden

**Remediation**: 
1. Create `GlucoseComplicationKit` SPM package
2. Create `WatchSyncKit` SPM package
3. Adopt in all apps for consistent experience

**Source**: `docs/10-domain/apple-watch-complications-survey.md`

**Status**: Open
