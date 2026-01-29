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

**Status**: Under discussion

---

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
