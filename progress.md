# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

---

## Completed Work

### cgm-remote-monitor Database Layer Audit (2026-01-29)

Full audit of Nightscout's MongoDB storage layer for Loop compatibility.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-database-deep-dive.md` | 455 lines, 6 collections, indexes, ordering |
| **Gaps** | `traceability/gaps.md` | GAP-DB-001/002/003 added |

**Key Findings**:
- MongoDB driver 3.6.0 (compatible with MongoDB 5.x)
- Treatment batch ordering preserved via `async.eachSeries`
- Loop's ordering requirement is satisfied
- Entries use `forEach` (unordered) but not critical for Loop
- API v3 uses `identifier` field with fallback deduplication

---

### Loop Sync Identity Fields Extraction (2026-01-29)

Extracted sync identity patterns from Loop/LoopKit for cross-project comparison.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Mapping** | `mapping/loop/sync-identity-fields.md` | 318 lines, syncIdentifier + ObjectIdCache patterns |
| **Gaps** | `traceability/gaps.md` | GAP-SYNC-005/006/007 added |

**Key Findings**:
- Loop uses `syncIdentifier` (pump hex or UUID) as primary identity
- `ObjectIdCache` maps to Nightscout `_id` (24-hour memory-only)
- Uses v1 POST only - no server-side deduplication
- Duplicates possible on app restart due to cache loss

---

### nightscout-librelink-up Deep Dive (2026-01-29)

Full audit of LibreLink Up to Nightscout bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/nightscout-librelink-up-deep-dive.md` | 378 lines |

#### Key Findings

| Component | Purpose | Details |
|-----------|---------|---------|
| LibreLink API | Auth + glucose fetch | 8 regions, stealth mode |
| Interfaces | TypeScript models | GlucoseItem, Connection |
| Nightscout | v1 upload only | v3 stub exists |

| Feature | Status |
|---------|--------|
| Multi-patient | ✅ Supported |
| Historical backfill | ❌ Not implemented |
| API v3 | ❌ Stub only |

**Gaps Identified**: GAP-LIBRELINK-001, GAP-LIBRELINK-002, GAP-LIBRELINK-003

---

### tconnectsync Deep Dive (2026-01-29)

Full audit of Tandem t:connect to Nightscout sync tool.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/tconnectsync-deep-dive.md` | 368 lines |

#### Key Findings

| Component | Purpose | Files |
|-----------|---------|-------|
| API | t:connect OAuth2/OIDC auth | 7 files, 1400+ lines |
| Domain | Bolus, TherapyEvent, Profile | 3 key models |
| Sync | NS v1 API upload | 10+ treatment types |

| Treatment Type | NS eventType |
|----------------|--------------|
| Combo Bolus | `Combo Bolus` |
| Temp Basal | `Temp Basal` |
| Site Change | `Site Change` |
| Exercise/Sleep | `Exercise`, `Sleep` |

**Gaps Identified**: GAP-TCONNECT-001, GAP-TCONNECT-002, GAP-TCONNECT-003

---

### OpenAPS/oref0 Deep Dive (2026-01-29)

Full audit of the foundational OpenAPS ecosystem - the original DIY closed-loop system.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/openaps-oref0-deep-dive.md` | 371 lines, 2 repos |

#### Key Findings

| Component | Purpose | Language |
|-----------|---------|----------|
| openaps | Device toolkit (pump/CGM drivers) | Python |
| oref0 | Reference algorithm (determine-basal) | JavaScript |

| Algorithm File | Lines | Function |
|----------------|-------|----------|
| determine-basal.js | 1192 | Main dosing calculation |
| autosens.js | 454 | Sensitivity detection |
| cob.js | 211 | Carbs on board |
| iob/history.js | 572 | IOB history processing |

**Gaps Identified**: GAP-OREF-001, GAP-OREF-002, GAP-OREF-003

---

### Prediction Array Formats Comparison (2026-01-28)

Cross-system analysis of glucose prediction array formats across Loop, AAPS, and Trio.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/prediction-arrays-comparison.md` | 319 lines, 3 systems |

#### Key Findings

| System | Prediction Model | devicestatus Field |
|--------|------------------|-------------------|
| Loop | Single combined curve | `loop.predicted.values` |
| AAPS | 4 separate curves (IOB/COB/UAM/ZT) | `openaps.suggested.predBGs.*` |
| Trio | 4 separate curves (IOB/COB/UAM/ZT) | `openaps.suggested.predBGs.*` |

**Gaps Identified**: GAP-PRED-002, GAP-PRED-003, GAP-PRED-004

---

### Batch Operation Ordering Deep Dive (2026-01-28)

Analysis of sync order requirements and ID mapping patterns across Loop, AAPS, Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/batch-ordering-deep-dive.md` | 334 lines |

#### Key Findings

| System | Strategy | Order Sensitive |
|--------|----------|-----------------|
| Loop | v1 batch + zip() | ✅ Critical |
| AAPS | Sequential v3 | ❌ N/A |
| NS v3 | Single-doc only | ❌ N/A |

**Key Recommendation**: Parse `identifier` from response, not positional matching.

---

### Override/Profile Switch Comparison (2026-01-28)

Cross-system analysis of therapy adjustment semantics across Loop, AAPS, and Trio.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/override-profile-switch-comparison.md` | 331 lines, 3 systems |

#### Key Findings

| System | Model | NS eventType |
|--------|-------|--------------|
| Loop | TemporaryScheduleOverride | Temporary Override |
| AAPS | ProfileSwitch + TempTarget | Profile Switch + Temporary Target |
| Trio | Override + TempTarget | Temporary Override + Temporary Target |

**Gaps Identified**: GAP-OVERRIDE-001 through GAP-OVERRIDE-004

---

### Remote Bolus Command Comparison (2026-01-28)

Cross-system analysis of remote bolus handling in Loop, AAPS, Trio, and Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/remote-bolus-comparison.md` | 348 lines, 4 systems |

#### Key Findings

| System | Auth | Key Safety Feature |
|--------|------|-------------------|
| Loop | OTP + APNs | 5-min expiration |
| AAPS | SMS passcode | 15-min distance |
| Trio | AES-256 | 20% rule + IOB check |
| Nightscout | API secret | Relay only (no limits) |

**Gaps Identified**: GAP-REMOTE-001 through GAP-REMOTE-004

---

### Nightscout v3 Treatments Schema (2026-01-28)

Extracted authoritative treatments schema from origin Nightscout server.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Schema** | `mapping/nightscout/v3-treatments-schema.md` | 248 lines, 21+ eventTypes |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **eventTypes** | 21+ types (careportal + OpenAPS plugins) |
| **Date formats** | Accepts ms, seconds, or ISO-8601 |
| **Deduplication** | By identifier or `created_at + eventType` |
| **Duration** | Always minutes |

#### NS vs AAPS Comparison
- AAPS has `pumpId`/`pumpSerial` for dedup (NS doesn't)
- AAPS has bolus `type` field (NORMAL/SMB)
- eventTypes mostly compatible (different naming)

---

### Modernization Analysis: cgm-remote-monitor vs Nocturne (2026-01-28)

Comprehensive comparison of original Nightscout server vs Nocturne .NET rewrite.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Analysis** | `docs/sdqctl-proposals/nocturne-modernization-analysis.md` | 350 lines, full comparison |

#### Key Findings

| Aspect | cgm-remote-monitor | Nocturne |
|--------|-------------------|----------|
| Codebase | 35K LOC JS | 334K LOC C# |
| Plugins | 38 | Service-based |
| Connectors | Via bridges | 8 native |
| API Parity | v1/v2/v3 (origin) | v1/v2/v3 + v4 |
| Database | MongoDB | PostgreSQL |

#### Recommendation
Both should be maintained for ecosystem diversity. Nocturne viable for new deployments; migration requires testing.

---

### share2nightscout-bridge Audit (2026-01-28)

Complete audit of Dexcom Share → Nightscout bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/share2nightscout-bridge-deep-dive.md` | 328 lines, full flow |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **Scale** | 447 lines JavaScript, single file |
| **Dexcom API** | Auth + Login + Fetch (US/EU servers) |
| **Output** | Nightscout API v1 `/api/v1/entries.json` only |
| **Poll Interval** | 2.5 minutes default |
| **Trend Mapping** | 10 Dexcom trends → Nightscout directions |

#### Gaps Identified
- GAP-SHARE-001: No Nightscout API v3 support
- GAP-SHARE-002: No backfill/gap detection logic
- GAP-SHARE-003: Hardcoded application ID may break

---

### Nocturne Initial Audit (2026-01-28)

Complete architectural audit of Nocturne - .NET 10 rewrite of Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/nocturne-deep-dive.md` | 279 lines, full architecture |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **Scale** | 927 C# files, 438 Svelte components, ~334K LOC |
| **API Parity** | Full v1/v2/v3 compatibility confirmed |
| **Connectors** | 8 native (Dexcom, Libre, Glooko, MiniMed, MFP, NS, TConnect, Tidepool) |
| **Algorithm** | Native Rust oref with FFI/WASM support |
| **Frontend** | SvelteKit 2 + Svelte 5 + Tailwind CSS 4 |

#### Architecture Comparison

| cgm-remote-monitor | Nocturne |
|-------------------|----------|
| JavaScript/Node.js | C# .NET 10 |
| MongoDB | PostgreSQL |
| Socket.IO | SignalR |
| JS oref | Rust oref |

#### Gaps Identified
- GAP-NOCTURNE-001: V4 endpoints Nocturne-specific
- GAP-NOCTURNE-002: Rust oref may diverge from JS
- GAP-NOCTURNE-003: SignalR→Socket.IO bridge latency

---

### AAPS NSClient Schema Extraction (2026-01-28)

Documented complete Nightscout upload schema from AAPS NSClient SDK.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **NSClient Schema** | `mapping/aaps/nsclient-schema.md` | 70+ fields across 3 collections |
| **README Update** | `mapping/aaps/README.md` | Added to documentation index |

#### Key Findings

| Collection | Fields | Key Types |
|------------|--------|-----------|
| `treatments` | 50+ | Bolus, Carbs, TempBasal, ProfileSwitch, TempTarget |
| `entries` | 15 | SGV with direction, noise, filtered/unfiltered |
| `devicestatus` | 20+ | Pump, OpenAPS (suggested/enacted), Configuration |

#### EventType Enum (25 types)
Site management, CGM, Glucose, Bolus, Carbs, Targets, Profile, Basal, Notes

#### Unit Conventions Documented
- `duration`: minutes (Nightscout) vs milliseconds (AAPS internal)
- `utcOffset`: minutes
- `durationInMilliseconds`: AAPS-specific field

---

### Workspace Expansion (2026-01-28)

Added 4 new repositories from live backlog requests. Workspace now has 20 repos.

| Repo | URL | Branch | Purpose |
|------|-----|--------|---------|
| `nocturne` | nightscout/nocturne | main | Nightscout client app |
| `Trio-dev` | nightscout/Trio | dev | Trio development branch |
| `share2nightscout-bridge` | nightscout/share2nightscout-bridge | dev | Dexcom Share bridge |
| `cgm-remote-monitor-official` | nightscout/cgm-remote-monitor | dev | Official NS server |

---

### Cross-Project Test Harness Tooling (2026-01-28)

Implemented new tooling for cross-project integration testing and unit conversion validation.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Unit Conversion Tests** | `tools/test_conversions.py` | 20 test cases for time/glucose/insulin conversions |
| **Conversion Fixtures** | `conformance/unit-conversions/conversions.yaml` | GAP-TREAT validated conversions |
| **Mock Nightscout Server** | `tools/mock_nightscout.py` | In-memory API v1/v3 mock |
| **Makefile Targets** | `Makefile` | `make conversions`, `make mock-nightscout` |
| **Tooling Backlog** | `docs/sdqctl-proposals/backlogs/tooling.md` | Updated with harness roadmap |

#### Key Features

| Tool | Capability |
|------|------------|
| `test_conversions.py` | Validates time (s/ms/min), glucose (mg/dL↔mmol/L), insulin precision |
| `mock_nightscout.py` | POST/GET/PUT/DELETE for entries, treatments, devicestatus |

#### Conversions Tested

- Loop `absorptionTime` (seconds) → Nightscout (minutes)
- AAPS `duration` (milliseconds) → Nightscout (minutes)
- Glucose mg/dL ↔ mmol/L (factor: 18.0182)
- Insulin/carb precision preservation

---

### Timezone/DST Handling Deep Dive (2026-01-28)

Comprehensive cross-project analysis of timezone and DST handling across the Nightscout ecosystem. Documented how each system stores, interprets, and synchronizes timezone information.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Expanded Timezone Handling section with 7 detailed tables |
| **New Gaps (4)** | `traceability/gaps.md` | GAP-TZ-004 through GAP-TZ-007 |

#### Key Findings

| System | TZ Storage | DST Aware | Key Issue |
|--------|-----------|-----------|-----------|
| **Nightscout** | IANA string in profile | ✅ Yes (moment-tz) | Recalculates utcOffset from dateString |
| **Loop** | `TimeZone` object (fixed offset) | ✅ Yes (Foundation) | Uses non-standard `ETC/GMT` format |
| **AAPS** | `utcOffset: Long` (ms) | ❌ No (fixed at capture) | Cannot reconstruct DST status historically |
| **Trio** | From NS profile | ✅ Yes (via NS) | Inherits NS timezone |
| **oref0** | Uses `moment-timezone` | ✅ Yes | N/A (no profile storage) |

#### Pump DST Support

| Status | Pumps |
|--------|-------|
| **✅ Can handle DST** | Medtrum, Combo v2 |
| **❌ Cannot handle DST** | Medtronic, Omnipod DASH/Eros, Dana RS/R, Equil |

#### New Gaps Documented

| Gap ID | Description |
|--------|-------------|
| **GAP-TZ-004** | utcOffset unit mismatch: Nightscout uses minutes, AAPS uses milliseconds |
| **GAP-TZ-005** | AAPS fixed offset storage breaks historical DST analysis |
| **GAP-TZ-006** | Loop uploads non-standard `ETC/GMT` timezone format (and NS workaround is buggy) |
| **GAP-TZ-007** | Missing timezone fallback uses server local time |

**Source Files Analyzed**:
- `externals/AndroidAPS/database/entities/interfaces/DBEntryWithTime.kt`
- `externals/AndroidAPS/core/data/pump/defs/TimeChangeType.kt`
- `externals/LoopWorkspace/LoopKit/LoopKit/DailyValueSchedule.swift`
- `externals/LoopWorkspace/RileyLinkKit/Common/TimeZone.swift`
- `externals/cgm-remote-monitor/lib/profilefunctions.js`
- `externals/cgm-remote-monitor/lib/api3/generic/collection.js`
- `externals/AndroidAPS/pump/medtrum/src/main/kotlin/.../SetTimeZonePacket.kt`

---

### Gap Discovery & Specification Analysis Session (2026-01-23)

Comprehensive gap analysis across Nightscout ecosystem: searched external repositories for undocumented behaviors, cross-referenced OpenAPI specs with controller implementations, and documented 16 new gaps with 14 corresponding requirements.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Behavioral Gaps (9)** | `traceability/gaps.md` | GAP-BATCH-001-003, GAP-PRED-001, GAP-TZ-001-003, GAP-ERR-001-003 |
| **Specification Gaps (7)** | `traceability/gaps.md` | GAP-SPEC-001-007 |
| **New Requirements (14)** | `traceability/requirements.md` | REQ-BATCH-001-003, REQ-TZ-001-002, REQ-ERR-001-003, REQ-SPEC-001-004 |

#### Batch Operation Gaps (Critical)

| Gap ID | Issue | Impact |
|--------|-------|--------|
| GAP-BATCH-001 | `id` field NOT unique-indexed in MongoDB | Batch inserts can create duplicates |
| GAP-BATCH-002 | Loop requires response order = request order | Wrong syncIdentifier→objectId mappings |
| GAP-BATCH-003 | Deduplicated items must return existing ID | Missing positions corrupt sync state |

**Source**: `cgm-remote-monitor:tests/api.partial-failures.test.js`

#### Timezone/DST Gaps

| Gap ID | Issue | Affected Systems |
|--------|-------|------------------|
| GAP-TZ-001 | Most pumps return `canHandleDST() = false` | Medtronic, Omnipod DASH/Eros, Dana-R |
| GAP-TZ-002 | Medtrum GMT+12 timezone bug workaround | Medtrum pumps |
| GAP-TZ-003 | utcOffset recalculated from dateString | All Nightscout uploads |

#### Error Handling Gaps

| Gap ID | Issue | Risk |
|--------|-------|------|
| GAP-ERR-001 | Empty array creates phantom record | Masks bugs |
| GAP-ERR-002 | Medtronic CRC mismatch ignored | Corrupted data used |
| GAP-ERR-003 | Unknown history entries: 0x2e, 0x3a, 0x51, 0x52, 0x54, 0x55 | Silent data loss |

#### Specification Gaps

| Gap ID | Missing From Spec |
|--------|-------------------|
| GAP-SPEC-001 | Remote command eventTypes (`Temporary Override Cancel`, `Remote Carbs Entry`, `Remote Bolus Entry`) |
| GAP-SPEC-002 | 17+ AAPS fields (`durationInMilliseconds`, `bolusCalculatorResult`, `isSMB`, etc.) |
| GAP-SPEC-003 | `Effective Profile Switch` eventType with `original*` fields |
| GAP-SPEC-004 | BolusCalculatorResult JSON schema (20+ fields) |
| GAP-SPEC-005 | `FAKE_EXTENDED` temp basal type for extended boluses |
| GAP-SPEC-006 | `isValid` soft-delete semantics |
| GAP-SPEC-007 | Deduplication key fields (`created_at` + `eventType`) |

#### Other Gaps

| Gap ID | Issue |
|--------|-------|
| GAP-PRED-001 | Prediction arrays truncated to 12 entries |

**Source Files Analyzed:**
- `externals/cgm-remote-monitor/tests/api.partial-failures.test.js`
- `externals/cgm-remote-monitor/tests/api.v1-batch-operations.test.js`
- `externals/cgm-remote-monitor/lib/server/loop.js`
- `externals/cgm-remote-monitor/lib/api3/swagger.yaml`
- `externals/AndroidAPS/core/nssdk/src/main/kotlin/.../RemoteTreatment.kt`
- `externals/AndroidAPS/pump/medtronic/comm/history/`
- `externals/AndroidAPS/pump/*/driver/*PumpPlugin.kt`

**Total New Gaps**: 16 | **Total New Requirements**: 14

---

### STPA Traceability Framework & Validation Tooling (2026-01-23)

Introduction of FDA-compatible hazard analysis framework and code reference validation tooling.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **STPA Framework Proposal** | `docs/sdqctl-proposals/STPA-TRACEABILITY-FRAMEWORK.md` | 446-line proposal for FDA Design Controls using STPA methodology |
| **Code Reference Validator** | `tools/validate_refs.py` | Python tool to validate `repo:path` code references against externals/ |
| **Validation Report** | `traceability/refs-validation.md` | Markdown report: 302/321 references valid, 19 broken identified |
| **Validation JSON** | `traceability/refs-validation.json` | Machine-readable validation results |

**Key STPA Framework Concepts:**
- Maps AID systems as control loops (Controller → Actuator → Process → Sensor)
- Introduces Unsafe Control Action (UCA) taxonomy: not provided, provided incorrectly, wrong timing, wrong duration
- Links existing GAPs to causal factors for UCAs
- Proposes `traceability/stpa/` directory structure for hazard analysis artifacts
- Addresses FDA 21 CFR 820.30 Design Controls gap

**Validation Tool Features:**
- Parses `repo:path` and `repo:path#Lnn` reference formats
- Supports ellipsis paths (`plugins/.../file.kt`)
- Maps 16 repository aliases to externals/ directories
- Generates both markdown and JSON reports
- Identifies: valid, file not found, path not found, unknown alias, repo missing

**Key Findings from Validation:**
- 94% of code references are valid (302/321)
- 17 "path not found" errors due to ellipsis patterns (expected, for readability)
- 1 file not found (stale reference)
- 1 unknown alias (typo)

**Files with Most Broken References:**
- `mapping/cross-project/terminology-matrix.md` (8 ellipsis patterns)
- `docs/10-domain/insulin-curves-deep-dive.md` (4 ellipsis patterns)
- `docs/CONTINUATION-PROMPTS.md` (3 placeholder paths)

---

### sdqctl Integration (2026-01-22)

Full integration of sdqctl 0.1.1 workflow orchestration into the workspace.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Integration Guide** | `docs/NIGHTSCOUT-SDQCTL-GUIDE.md` | Maps sdqctl to 5-facet methodology |
| **Feedback Report** | `docs/sdqctl-integration-feedback.md` | Documents validation issues and P0 fixes |
| **Continuation Prompts** | `docs/CONTINUATION-PROMPTS.md` | Ready-to-use prompts for workflows |
| **Proposals Reference** | `docs/sdqctl-proposals/` | VERIFICATION-DIRECTIVES and RUN-BRANCHING proposals |
| **Updated Workflows** | `workflows/*.conv` | 9 files updated with VALIDATION-MODE lenient |
| **New Workflow Categories** | `workflows/{discovery,design,iterate,integrate}/` | 14 new structured workflow files |

**Key Updates from sdqctl Team:**
- P0 fixes implemented: `VALIDATION-MODE lenient`, `CONTEXT-OPTIONAL`, glob pattern fixes
- Loop detection with `STOP_FILE` template variable
- SDK integration proposal with 34 event types
- VERIFICATION-DIRECTIVES proposal for built-in verification

**Validation Results:** All 27 workflows now validate successfully with `--allow-missing` flag.

**New Directives Available:**
- `VALIDATION-MODE lenient` - Warn on missing context, don't fail
- `CONTEXT-OPTIONAL @pattern` - Never fails, only warns
- `CONTEXT-EXCLUDE pattern` - Skip from validation entirely

---

### NightscoutKit Response Format Verification (2026-01-19)

Source code verification of actual Loop client response requirements for v1 API.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Impact Assessment Update** | `docs/60-research/mongodb-modernization-impact-assessment.md` | Corrected v1 response format requirements |
| **Readiness Report Update** | `docs/60-research/mongodb-update-readiness-report.md` | Revised risk matrix based on verified requirements |
| **API Comparison Update** | `docs/10-domain/nightscout-api-comparison.md` | Added Section 8.3 documenting client parsing behavior |

**Key Finding:** Loop's NightscoutKit only extracts `_id` from v1 API responses. Fields `ok` and `n` are NOT checked.

**Verified Requirements (from NightscoutKit source):**
- Response must be array with length matching request length
- Each object should have `_id` field (graceful fallback to "NA" if missing)
- Response order must match request order for `syncIdentifier` mapping
- Fields `ok: 1` and `n: 1` are NOT required (previously over-documented)

**Source Reference:** `LoopKit/NightscoutKit/Sources/NightscoutKit/NightscoutClient.swift` - `postToNS` function

**Risk Impact:** Downgraded "Response format breaking change" from HIGH to MEDIUM in readiness report.

---

### CGM Remote Monitor MongoDB Modernization Analysis (2026-01-18)

Deep analysis of the cgm-remote-monitor team's latest work on the `wip/replit/with-mongodb-update` branch.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Analysis Report** | `docs/cgm-remote-monitor-analysis-2026-01-18.md` | Analysis of team's MongoDB modernization work |
| **Documentation Inventory** | `traceability/cgm-remote-monitor-docs-inventory.md` | Inventory of documentation files found in repository |

**Summary** (sources noted per item):
- Team reports Phase 1 complete with 29/30 tests passing (per `mongodb-modernization-implementation-plan.md`)
- 3 new test files with 1,229 lines (verified by line count scan)
- Documentation restructured with new `docs/INDEX.md` hub (75 lines, verified by line count scan)
- New `scripts/flaky-test-runner.js` (513 lines, verified by line count scan)
- WebSocket deduplication analysis (per `websocket-array-deduplication-issue.md`)

**Client Patterns Team Reports as Tested** (per `mongodb-modernization-implementation-plan.md`):
- Loop response ordering (response[i] matches request[i])
- AAPS pumpId+pumpType+pumpSerial deduplication
- Loop syncIdentifier deduplication
- Trio id field deduplication
- Cross-client duplicate isolation

**New Test Files** (verified line counts):
- `tests/api.deduplication.test.js` - 398 lines
- `tests/api.partial-failures.test.js` - 456 lines
- `tests/api.aaps-client.test.js` - 375 lines

**Key Documentation** (verified line counts):
- `externals/cgm-remote-monitor/docs/proposals/mongodb-modernization-implementation-plan.md` (940 lines)
- `externals/cgm-remote-monitor/docs/proposals/websocket-array-deduplication-issue.md` (262 lines)
- `externals/cgm-remote-monitor/docs/INDEX.md` (75 lines)
- `externals/cgm-remote-monitor/scripts/flaky-test-runner.js` (513 lines)

**MongoDB Migration Status** (all status claims per team's `mongodb-modernization-implementation-plan.md`):
- Phase 1: Test Infrastructure - Team reports complete
- Phase 2: Storage Layer Analysis - Team reports as next
- Phase 3: Core Implementation - Team reports as planned
- Phase 4: Testing & Validation - Team reports as planned

---

### Dexcom G7 Protocol Documentation (2026-01-17)

Comprehensive analysis of the Dexcom G7 BLE protocol and J-PAKE authentication, compiled from xDrip Android, DiaBLE, G7SensorKit, and xDrip4iOS source analysis.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **G7 Protocol Specification** | `docs/10-domain/g7-protocol-specification.md` | Complete opcode table (15+ opcodes), BLE characteristics, message formats, authentication state machine, glucose/backfill parsing |
| **J-PAKE Implementation Guide** | `docs/10-domain/g7-jpake-implementation-guide.md` | Algorithm details, xDrip libkeks architecture, Swift porting roadmap, certificate exchange, proof of possession |
| **G7 Cross-Project Comparison** | `mapping/cross-project/g7-implementation-comparison.md` | Feature matrix across 6 projects, authentication phase coverage, blockers and gaps |

**Key Findings**:
- **xDrip Android and Juggluco are the only projects with standalone G7 support** (xDrip via Java `libkeks`, Juggluco via native C++)
- All iOS projects (DiaBLE, G7SensorKit, xDrip4iOS) require Dexcom app running in background
- G7 glucose data appears unencrypted in observed BLE traffic - the J-PAKE authentication is the primary barrier
- J-PAKE uses secp256r1 curve, 160-byte packets, sensor code as password
- Complete 5-phase authentication sequence documented: J-PAKE → Traditional Auth → Certificate Exchange → Proof of Possession → Bonding

**Source Files Analyzed**:
- `xDrip:libkeks/src/main/java/jamorham/keks/` (Calc.java, Context.java, Curve.java, Packet.java, DSAChallenger.java)
- `DiaBLE:DiaBLE/DexcomG7.swift` (BLE traces, opcode definitions)
- `G7SensorKit:G7SensorKit/Messages/` (G7GlucoseMessage.swift, G7BackfillMessage.swift)
- `xDrip4iOS:xdrip/BluetoothTransmitter/CGM/Dexcom/Generic/DexcomG7*.swift`

**Gaps Identified**: GAP-G7-001 (No iOS J-PAKE), GAP-G7-002 (Certificate undocumented), GAP-G7-003 (G7SensorKit minimal), GAP-G7-004 (Party IDs unknown)

---

### Core Collections Trifecta (2026-01-17)

Comprehensive field-by-field mapping of the three main Nightscout data collections:

| Collection | Deep Dive Document | Key Deliverables |
|------------|-------------------|------------------|
| **entries** | `docs/10-domain/entries-deep-dive.md` | SGV field mapping, direction arrow mapping, noise handling, CGM vs meter distinction, xDrip+ local web server |
| **treatments** | `docs/10-domain/treatments-deep-dive.md` | Bolus/carb/temp basal field mapping, unit differences, SMB representation, sync identity |
| **devicestatus** | `docs/10-domain/devicestatus-deep-dive.md` | Loop vs oref0 structure, prediction arrays, enacted vs suggested, duration units |

**Cross-references updated**:
- `mapping/cross-project/terminology-matrix.md` - Added Treatment Data Models and Glucose Data Models sections

**Gaps identified**: GAP-ENTRY-001 through GAP-ENTRY-005, GAP-TREAT-001 through GAP-TREAT-007, GAP-DS-001 through GAP-DS-004

### Supporting Analysis (2026-01-17)

| Document | Location | Purpose |
|----------|----------|---------|
| AID Controller Sync Patterns | `mapping/cross-project/aid-controller-sync-patterns.md` | How Trio/Loop/AAPS sync with Nightscout |
| Profile/Therapy Settings Comparison | `docs/60-research/profile-therapy-settings-comparison.md` | Cross-system profile structure analysis |

### Algorithm Prediction Comparison (2026-01-17)

Comprehensive cross-system comparison explaining why the same CGM data produces different dosing recommendations.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Algorithm Comparison Deep Dive** | `docs/10-domain/algorithm-comparison-deep-dive.md` | Loop vs oref0 prediction methodology, carb absorption models, sensitivity adjustments, safety guards, SMB logic |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added Algorithm Comparison section with prediction methodology, carb models, sensitivity mechanisms |

**Key Findings**:
- Loop uses single combined prediction curve; oref0/AAPS/Trio use 4 separate curves (IOB, COB, UAM, ZT)
- Loop's dynamic carb absorption adapts in real-time; oref0 uses linear decay with UAM backup
- Loop uses Retrospective Correction; oref0/AAPS/Trio use Autosens (AAPS also offers TDD-based Dynamic ISF)
- SMB (Super Micro Bolus) only available in oref0-based systems, not Loop

**Gaps Identified**: GAP-ALG-001 through GAP-ALG-008

---

### CGM Data Source Architecture (2026-01-17)

Comprehensive analysis of how CGM data flows from sensors to Nightscout entries, covering data sources, calibration, and follower modes.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **CGM Data Sources Deep Dive** | `docs/10-domain/cgm-data-sources-deep-dive.md` | xDrip+ 20+ source types, pluggable calibration, follower modes, iOS vs Android differences, data provenance tracking |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added CGM Source Models section with data source types, calibration models, BgReading entity mapping, follower sources |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-050 through REQ-057 for CGM data source integrity |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-CGM-001 through GAP-CGM-006 for data provenance gaps |

**Key Findings**:
- xDrip+ Android is the primary CGM producer with 20+ data source types and pluggable calibration
- xDrip4iOS supports ~6 source types with Native/WebOOP calibration only
- Loop and Trio are CGM consumers (do not upload CGM data to Nightscout)
- AAPS receives CGM data from xDrip+ via broadcast
- Calibration algorithm and sensor provenance are not tracked in Nightscout entries

**Gaps Identified**: GAP-CGM-001 through GAP-CGM-006

---

### Remote Commands Cross-System Comparison (2026-01-17)

Comprehensive security-focused analysis of how caregivers remotely control AID systems across Trio, Loop, and AAPS.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Remote Commands Comparison** | `docs/10-domain/remote-commands-comparison.md` | Security models, command types, safety limits, replay protection |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added Remote Command Security Models section with transport, auth, OTP, and safety tables |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-REMOTE-001 through REQ-REMOTE-006 |
| **Gaps Update** | `traceability/gaps.md` | Expanded GAP-REMOTE-001, added GAP-REMOTE-002 through GAP-REMOTE-004 |

**Key Findings**:
- **Trio**: AES-256-GCM encryption via APNS with SHA256 key derivation, 6 command types, 10-minute timestamp replay protection
- **Loop**: TOTP OTP (SHA1, 6-digit, 30-sec) for bolus/carbs, **but NOT for overrides** (security gap), 4 command types
- **AAPS**: SMS-based with phone whitelist + TOTP + PIN, 13+ command types including loop/pump control
- **Critical Gap**: Loop override commands skip OTP validation (GAP-REMOTE-001)
- **All Systems**: Safety limits enforced at different layers (Trio in handler, Loop downstream, AAPS via ConstraintChecker)

**Source Files Analyzed**:
- `trio:Trio/Sources/Services/RemoteControl/*.swift` (SecureMessenger, TrioRemoteControl)
- `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/` (OTPManager, RemoteCommandValidator)
- `aaps:plugins/main/src/main/kotlin/.../smsCommunicator/` (SmsCommunicatorPlugin, OneTimePassword, AuthRequest)

**Gaps Updated**: GAP-REMOTE-001 (expanded), GAP-REMOTE-002, GAP-REMOTE-003, GAP-REMOTE-004

---

### Nightscout API v1 vs v3 Comparison (2026-01-17)

Comprehensive analysis of the two Nightscout API versions, explaining why AAPS uses v3 exclusively while iOS clients (Loop, Trio) continue with v1.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **API Comparison Deep Dive** | `docs/10-domain/nightscout-api-comparison.md` | Endpoint mapping, auth differences, identifier vs _id, history sync, soft delete |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added API Version Models section with client matrix, identity fields, v3 features |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-API-001 through GAP-API-005 |

**Key Findings**:
- **AAPS is the ONLY v3 client**: All iOS systems (Loop, Trio) and xDrip+ use v1 API
- **Authentication**: v1 uses SHA1-hashed API_SECRET (all-or-nothing); v3 uses JWT Bearer tokens with granular Shiro permissions
- **Document Identity**: v1 uses `_id` (MongoDB ObjectId); v3 uses `identifier` (server-assigned, immutable)
- **Sync Efficiency**: v3 `history/{timestamp}` endpoint enables incremental sync with deletion detection; v1 requires polling with date filters
- **Soft Delete**: v3 marks deletions with `isValid=false` so clients can sync deletions; v1 hard-deletes are invisible to other clients
- **Deduplication**: v3 returns `isDeduplication: true` flag; v1 silently accepts duplicates

**Source Files Analyzed**:
- `cgm-remote-monitor:lib/api/` (v1 endpoints)
- `cgm-remote-monitor:lib/api3/` (v3 generic operations, security, history)
- `AndroidAPS:core/nssdk/` (AAPS v3 SDK implementation)
- `Trio:Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift` (v1 usage)
- `cgm-remote-monitor:docs/requirements/api-v1-compatibility-spec.md`

**Gaps Identified**: GAP-API-001 through GAP-API-005

---

### Pump Communication Protocols (2026-01-17)

Comprehensive analysis of how AID controllers communicate with insulin pumps, covering protocol layers, interface abstractions, and safety patterns.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Pump Communication Deep Dive** | `docs/10-domain/pump-communication-deep-dive.md` | BLE vs RF protocols, PumpManager vs Pump interface, command patterns, timing constraints, encryption |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added Pump Communication Models section with interface mapping, commands, transport protocols, state machines |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-PUMP-001 through REQ-PUMP-006 for pump precision, acknowledgment, progress, history, clock, timeouts |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-PUMP-001 through GAP-PUMP-005 for capability exchange, extended bolus, duration units, error codes, uncertainty |

**Key Findings**:
- **Protocol split**: Omnipod DASH, Dana RS, Insight use BLE; Omnipod Eros, Medtronic use RF via RileyLink bridge
- **Interface design**: Loop uses async completion handlers (`PumpManager`); AAPS uses synchronous interface with async execution (`Pump` returns `PumpEnactResult`)
- **Extended bolus gap**: AAPS supports extended/combo boluses; Loop ecosystem does not (philosophy differs)
- **TBR duration units**: Loop uses seconds; AAPS uses minutes (conversion needed)
- **Acknowledgment patterns**: Loop has `deliveryIsUncertain` flag; AAPS has `PumpEnactResult.success` + retry logic
- **Omnipod DASH encryption**: AES-CCM with LTK exchange during pairing
- **Dana RS error codes**: `0x10` max bolus, `0x20` command error, `0x40` speed error, `0x80` insulin limit
- **History reconciliation**: Loop uses `hasNewPumpEvents` delegate; AAPS uses `PumpSync` with temporary ID pattern

**Source Files Analyzed**:
- `LoopWorkspace/LoopKit/LoopKit/DeviceManager/PumpManager.swift` - Core protocol
- `LoopWorkspace/LoopKit/LoopKit/DeviceManager/PumpManagerStatus.swift` - Status states
- `LoopWorkspace/Loop/Loop/Managers/DoseEnactor.swift` - Command sequencing
- `LoopWorkspace/OmniBLE/OmniBLE/Bluetooth/` - BLE UUIDs, encryption
- `AndroidAPS/core/interfaces/src/main/kotlin/.../pump/Pump.kt` - Core interface
- `AndroidAPS/core/interfaces/src/main/kotlin/.../pump/PumpSync.kt` - History sync
- `AndroidAPS/core/data/src/main/kotlin/.../pump/defs/PumpType.kt` - Pump definitions
- `AndroidAPS/pump/danars/src/main/kotlin/.../DanaRSPlugin.kt` - Dana RS driver
- `AndroidAPS/pump/omnipod/dash/src/main/kotlin/.../OmnipodDashPumpPlugin.kt` - DASH driver

**Gaps Identified**: GAP-PUMP-001 through GAP-PUMP-005

---

### Insulin Activity Curves Deep Dive (2026-01-17)

Comprehensive cross-system analysis of insulin activity curves used by AID systems for IOB calculation.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Insulin Curves Deep Dive** | `docs/10-domain/insulin-curves-deep-dive.md` | Mathematical formulas, cross-system model comparison, DIA enforcement, peak time configuration |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added comprehensive Insulin Curve Models section with implementation details, IOB components, xDrip+ multi-insulin |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-INS-001 through REQ-INS-005 for model consistency, DIA enforcement, peak bounds, activity calculation |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-INS-001 through GAP-INS-004 for metadata sync, multi-insulin, peak capture, model incompatibility |

**Key Findings**:
- **Shared Mathematical Foundation**: All major AID systems (Loop, oref0, AAPS, Trio) use the **same exponential insulin model**. oref0 explicitly credits Loop as the source in `lib/iob/calculate.js#L125`
- **Formula Origin**: Loop developed the exponential model; oref0 copied it with attribution; AAPS ported it to Kotlin; Trio uses oref0 JavaScript
- **xDrip+ Uses Different Model**: Linear trapezoid model with support for 13+ insulin types including long-acting insulins (Lantus, Tresiba, etc.)
- **DIA Enforcement**: All AID systems enforce 5-hour minimum for exponential model; xDrip+ has no minimum
- **Peak Time Customization**: oref0 allows 50-120min (rapid) and 35-100min (ultra-rapid); AAPS has Free Peak plugin; Loop uses fixed presets
- **Multi-Insulin**: xDrip+ uniquely supports multiple insulin types per treatment via `insulinJSON` field
- **Metadata Gap**: No system syncs insulin model metadata (curve, peak, DIA) to Nightscout

**Source Files Analyzed**:
- `oref0:lib/iob/calculate.js` - Core IOB calculation (bilinear + exponential)
- `oref0:lib/iob/total.js` - IOB aggregation and DIA enforcement
- `aaps:plugins/insulin/src/main/kotlin/.../InsulinOrefBasePlugin.kt` - Kotlin port
- `aaps:plugins/insulin/src/main/kotlin/.../InsulinLyumjevPlugin.kt` - Lyumjev model
- `loop:LoopKit/LoopKit/Insulin/ExponentialInsulinModel.swift` - Original exponential formula
- `loop:LoopKit/LoopKit/InsulinKit/InsulinMath.swift` - IOB calculation
- `trio:Trio/Sources/Models/Preferences.swift` - Insulin curve settings
- `xDrip:app/src/main/res/raw/insulin_profiles.json` - 13 insulin type definitions
- `xDrip:insulin/LinearTrapezoidInsulin.java` - Linear trapezoid implementation

**Gaps Identified**: GAP-INS-001 through GAP-INS-004

---

### Cycle 11: Dexcom BLE Protocol Specification (Completed 2026-01-17)

Comprehensive reverse-engineered specification of Dexcom G6 and G7 Bluetooth Low Energy protocols based on open-source implementations.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Dexcom BLE Protocol Deep Dive** | `docs/10-domain/dexcom-ble-protocol-deep-dive.md` | Complete opcode tables, message structures, authentication flows, CRC validation |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added BLE Protocol Models section with UUIDs, G6/G7 differences, opcodes, glucose message structures |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-BLE-001 through REQ-BLE-006 for CRC validation, authentication, glucose extraction, trend conversion |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-BLE-001 through GAP-BLE-005 for J-PAKE spec, certificate chain, Service B purpose, Anubis commands |

**Key Findings**:
- **Complete Opcode Table**: Documented all G6 opcodes (0x01-0x51) with Tx/Rx pairs, message structures, and field offsets
- **G6 vs G7 Protocol Differences**: G6 uses AES-128-ECB challenge-response, G7 uses J-PAKE; G6 has 2 connection slots, G7 has 1 exclusive slot
- **Authentication Hash Function**: All implementations use identical `hash(data, transmitterID)` = `aes128ecb(data+data, "00"+id+"00"+id)[0:8]`
- **CRC-16 Validation**: CRC-16 CCITT (XModem) polynomial 0x1021, initial value 0x0000, little-endian in last 2 bytes
- **Glucose Message Structure**: 12-bit glucose value with display-only flag, signed Int8 trend rate divided by 10
- **Algorithm/Calibration States**: G6 has 18 states (CalibrationState), G7 has 26 states (AlgorithmState) with different reliability semantics
- **Backfill Protocol**: G6 uses 0x50/0x51 with 8-byte entries, G7 uses 0x59 with 9-byte entries (3-byte timestamp)

**Source Files Analyzed**:
- `CGMBLEKit:CGMBLEKit/Opcode.swift` - Complete G6 opcode enumeration
- `CGMBLEKit:CGMBLEKit/Messages/*.swift` - All G6 Tx/Rx message structures
- `CGMBLEKit:CGMBLEKit/BluetoothServices.swift` - BLE UUIDs and characteristics
- `G7SensorKit:G7SensorKit/Messages/G7GlucoseMessage.swift` - G7 glucose message structure
- `G7SensorKit:G7SensorKit/AlgorithmState.swift` - G7 algorithm state enumeration
- `xdrip-js:lib/transmitter.js` - Node.js implementation with authentication and backfill
- `DiaBLE:Dexcom.swift` - Swift implementation with extended opcodes
- `DiaBLE:DexcomG7.swift` - G7-specific protocol including J-PAKE references

**Gaps Identified**: GAP-BLE-001 through GAP-BLE-005

---

### Cycle 13: Pump Protocol Specifications (Completed 2026-01-17)

Comprehensive low-level protocol specification for insulin pump communication across three major pump systems.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Pump Protocols Specification** | `specs/pump-protocols-spec.md` | Complete message structures, opcodes, encryption mechanisms, delivery constants |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added Pump Protocol Models section with transport comparison, message structures, command opcodes |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-PUMP-007 through REQ-PUMP-010 for nonce management, session security, CRC validation, delivery rate |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-PUMP-006 through GAP-PUMP-009 for encryption gaps, Milenage constants, Dana modes, Medtronic sizes |

**Key Findings**:
- **Omnipod DASH**: Uses EAP-AKA with 3GPP Milenage algorithm for session auth (rare in medical devices), AES-128-CCM encryption, X25519 for LTK exchange
- **Dana RS**: Three encryption evolution stages (DEFAULT → RSv3 → BLE5), CRC polynomial varies by mode, multi-layer XOR encryption
- **Medtronic RF**: No encryption (plaintext RF), variable history entry sizes per model, requires RileyLink bridge
- **Security Comparison**: DASH has strongest security (proper crypto), Dana RS has obfuscation, Medtronic has none
- **Delivery Precision**: All pumps use 0.05U or finer steps; Omnipod delivers 0.025 U/s, Dana RS configurable

**Source Files Analyzed**:
- `OmniBLE/Bluetooth/MessagePacket.swift` - DASH packet structure
- `OmniBLE/Bluetooth/Session/SessionEstablisher.swift` - EAP-AKA flow
- `OmniBLE/Bluetooth/Session/Milenage.swift` - Milenage algorithm
- `OmniBLE/OmnipodCommon/MessageBlocks/*.swift` - All DASH command blocks
- `pump/danars/comm/DanaRSPacket.kt` - Dana RS packet structure
- `pump/danars/encryption/BleEncryption.kt` - Dana RS encryption layers
- `pump/medtronic/comm/history/pump/PumpHistoryEntryType.kt` - Medtronic history opcodes

**Gaps Identified**: GAP-PUMP-006 through GAP-PUMP-009

---

### Cycle 12: Carb Absorption Models Comparison (Completed 2026-01-17)

Comprehensive cross-system analysis of carbohydrate absorption models used by AID systems for COB calculation and glucose prediction.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Carb Absorption Deep Dive** | `docs/10-domain/carb-absorption-deep-dive.md` | Mathematical formulas, curve types, dynamic vs static absorption, UAM handling, eCarbs |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added Carb Absorption Models section with curve types, COB calculation, parameters, UAM handling |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-CARB-001 through REQ-CARB-006 for COB granularity, model reporting, eCarbs, CSF formula |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-CARB-001 through GAP-CARB-005 for model sync, dynamic state export, eCarbs portability |

**Key Findings**:
- **Absorption Model Diversity**: Loop/Trio use pluggable curves (Parabolic, Linear, PiecewiseLinear); oref0/AAPS use linear decay with `min_5m_carbimpact` floor
- **Dynamic vs Static**: Loop dynamically adapts absorption rate based on observed glucose effects (`observedTimeline`, `AbsorbedCarbValue`); oref0 infers absorption from deviation
- **PiecewiseLinear Default**: Loop/Trio default to trapezoidal absorption (15% rise, 50% plateau, 35% fall)
- **min_5m_carbimpact**: oref0/AAPS use 3 mg/dL/5m minimum (8 for low-carb) to prevent "zombie carbs"
- **eCarbs Gap**: AAPS uniquely supports extended carbs via `duration` field (milliseconds); iOS apps do not
- **UAM Handling**: oref0 has explicit UAM curve; Loop uses Retrospective Correction implicitly
- **COB Caps**: oref0/AAPS cap at 120g; Loop has no hard cap
- **CSF Formula**: All systems use `CSF = ISF / CR` (mg/dL per gram)

**Source Files Analyzed**:
- `loop:LoopKit/LoopKit/CarbKit/CarbMath.swift` - Absorption models, COB calculation
- `loop:LoopKit/LoopKit/CarbKit/CarbStatus.swift` - Dynamic absorption tracking
- `loop:LoopKit/LoopKit/CarbKit/AbsorbedCarbValue.swift` - Observed/clamped absorption
- `oref0:lib/determine-basal/cob.js` - Deviation-based COB detection
- `oref0:lib/meal/total.js` - Meal COB calculation with stacking
- `oref0:lib/determine-basal/determine-basal.js` - COB/UAM prediction curves
- `aaps:database/entities/Carbs.kt` - eCarbs duration field

**Gaps Identified**: GAP-CARB-001 through GAP-CARB-005

---

### Cycle 14: LoopCaregiver Remote Commands Protocol (Completed 2026-01-17)

Deep dive into LoopCaregiver's Remote 2.0 protocol implementation, documenting QR code linking, OTP generation, command types, and status tracking.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Remote Commands Documentation** | `mapping/loopcaregiver/remote-commands.md` | Command types, payload structure, status lifecycle, Remote 2.0 vs 1.0 |
| **Authentication Documentation** | `mapping/loopcaregiver/authentication.md` | QR code linking, deep link format, OTP generation, credential storage |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added LoopCaregiver Remote 2.0 Models section with command types, status states, auth components |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-REMOTE-007 through REQ-REMOTE-011 for caregiver-specific requirements |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-REMOTE-005 through GAP-REMOTE-007 for caregiver-specific gaps |

**Key Findings**:
- **6 Command Types**: bolus, carbs, override, cancelOverride, autobolus, closedLoop (last 2 are Remote 2.0 only)
- **OTP Protocol**: Standard TOTP (RFC 6238) with SHA1, 6 digits, 30-second period
- **QR Code Linking**: Deep link format `caregiver://createLooper?name=X&nsURL=X&secretKey=X&otpURL=X`
- **Status Lifecycle**: Pending → InProgress → Success/Error (tracked via Nightscout polling)
- **Remote 2.0 Version Flag**: `settings.remoteCommands2Enabled` switches between v1 and v2 protocols
- **Safety Features**: 7-minute recommended bolus expiry, post-bolus recommendation rejection, credential validation
- **Security Gap**: Override commands don't require OTP on Loop side (GAP-REMOTE-001 confirmed)

**Source Files Analyzed**:
- `loopcaregiver:LoopCaregiverKit/Sources/.../Nightscout/OTPManager.swift` - TOTP generation
- `loopcaregiver:LoopCaregiverKit/Sources/.../Nightscout/NightscoutDataSource.swift` - Command upload and status
- `loopcaregiver:LoopCaregiverKit/Sources/.../Nightscout/NightscoutCredentialService.swift` - Credential management
- `loopcaregiver:LoopCaregiverKit/Sources/.../Models/DeepLinkParser.swift` - QR code/deep link parsing
- `loopcaregiver:LoopCaregiverKit/Sources/.../Models/RemoteCommands/Action.swift` - Command action types
- `loopcaregiver:LoopCaregiverKit/Sources/.../Models/RemoteCommands/RemoteCommandStatus.swift` - Status model
- `loopcaregiver:LoopCaregiver/Views/Settings/LooperSetupView.swift` - QR scanning UI

**Gaps Identified**: GAP-REMOTE-005 through GAP-REMOTE-007

---

### Cycle 15: LoopFollow Deep Dive (Completed 2026-01-17)

Comprehensive analysis of LoopFollow's alarm system and remote command mechanisms, documenting all 20 alarm types and 3 remote control protocols.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Alarm System Documentation** | `mapping/loopfollow/alarm-system.md` | 20 alarm types, predictive/persistent conditions, day/night scheduling, snooze behavior |
| **Remote Commands Documentation** | `mapping/loopfollow/remote-commands.md` | Loop APNS (TOTP), TRC (AES-256-GCM), Nightscout API protocols |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added LoopFollow Alarm Models and Remote Command Models sections |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-ALARM-001 through REQ-ALARM-010 for caregiver alarm requirements |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-LF-001 through GAP-LF-009 for LoopFollow-specific gaps |

**Key Findings**:
- **20 Alarm Types**: Low/high BG, fast drop/rise, missed reading, IOB, COB, missed bolus, rec bolus, not looping, build expire, sensor change, pump change, pump volume, battery, battery drop, override start/end, temp target start/end, temporary
- **Alarm Features**: Predictive look-ahead (low BG), persistent duration, delta-based detection, day/night sound/activation scheduling, global snooze
- **3 Remote Protocols**: Loop APNS (TOTP+JWT), TRC (AES-256-GCM+JWT), Nightscout (token only)
- **TRC Commands**: bolus, temp_target, cancel_temp_target, meal (with protein/fat), start_override, cancel_override
- **Security Comparison**: TRC most secure (encryption); Loop APNS uses TOTP; Nightscout least secure (token only)
- **Key Differentiator**: LoopFollow supports both Loop (via APNS) and Trio (via TRC/Nightscout) unlike LoopCaregiver

**Source Files Analyzed**:
- `loopfollow:LoopFollow/Alarm/AlarmType/AlarmType.swift` - 20 alarm types
- `loopfollow:LoopFollow/Alarm/Alarm.swift` - Alarm model with day/night options
- `loopfollow:LoopFollow/Alarm/AlarmManager.swift` - Priority-based evaluation, snooze
- `loopfollow:LoopFollow/Alarm/AlarmCondition/*.swift` - Individual condition implementations
- `loopfollow:LoopFollow/Remote/TRC/PushNotificationManager.swift` - TRC APNS with JWT
- `loopfollow:LoopFollow/Remote/TRC/SecureMessenger.swift` - AES-256-GCM encryption
- `loopfollow:LoopFollow/Remote/LoopAPNS/LoopAPNSService.swift` - Loop APNS commands
- `loopfollow:LoopFollow/Remote/LoopAPNS/TOTPService.swift` - TOTP management
- `loopfollow:LoopFollow/Remote/Nightscout/TrioNightscoutRemoteView.swift` - NS temp target

**Gaps Identified**: GAP-LF-001 through GAP-LF-009

---

### Cycle 16: Progressive Enhancement Framework Integration (Completed 2026-01-17)

Integration of a conceptual capability ladder framework for diabetes technology, derived from community discussions about progressive enhancement and graceful degradation patterns.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| **Progressive Enhancement Framework** | `docs/10-domain/progressive-enhancement-framework.md` | 10-layer capability ladder (L0-L9), design principles, shared vocabulary |
| **Capability Layer Matrix** | `mapping/cross-project/capability-layer-matrix.md` | Commercial vs open-source system mapping, L8/L9 blockers |
| **Requirements Update** | `traceability/requirements.md` | Added REQ-DEGRADE-001 through REQ-DEGRADE-006 for graceful degradation |
| **Gaps Update** | `traceability/gaps.md` | Added GAP-DELEGATE-001 through GAP-DELEGATE-005 for delegation/agent gaps |
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Added Capability Layer Models section |

**Key Concepts Documented**:

**10-Layer Capability Ladder**:
| Layer | Name | Key Capability |
|-------|------|----------------|
| L0 | MDI Baseline | Manual insulin, fingersticks (floor) |
| L1 | Structured MDI | Carb counting, logging |
| L2 | CGM Sensing | Continuous glucose, trends |
| L3 | Pump Therapy | Programmable basal, bolus |
| L4 | Manual Pump+CGM | CGM-informed manual control |
| L5 | Safety Automation | Suspend, bounded corrections |
| L6 | Full AID | Closed-loop control (Loop/AAPS/Trio) |
| L7 | Networked Care | Remote visibility (Nightscout) |
| L8 | Remote Controls | Delegated actions at a distance |
| L9 | Delegate Agents | Autonomous agents with context |

**Core Design Principles**:
- **Progressive Enhancement**: Add capabilities in layers; each layer independently valuable
- **Graceful Degradation**: Every layer has explicit fallback mode; system never leaves user unable to manage
- **Separation of Concerns**: Distinguish therapy intent, delivery, and evidence
- **Explainability via Traceability**: Every decision points to inputs and rules
- **Delegation & Stewardship**: Scoped authorization, audit trails, revocation

**System Layer Mapping**:
| System | L6 (AID) | L7 (Network) | L8 (Remote) | L9 (Agents) |
|--------|----------|--------------|-------------|-------------|
| Tandem Control-IQ | Full | Partial | None | None |
| Omnipod 5 | Full | Partial | None | None |
| Loop | Full | Full | Partial | None |
| AAPS | Full | Full (v3) | Partial | None |
| Trio | Full | Full | Partial | None |

**Key L8/L9 Blockers Identified**:
- GAP-DELEGATE-001: No standardized authorization scoping (all or nothing)
- GAP-DELEGATE-002: No role-based permission model (caregiver vs clinician vs agent)
- GAP-DELEGATE-003: No structured out-of-band signal API (exercise, hormones)
- GAP-DELEGATE-004: No agent authorization framework
- GAP-DELEGATE-005: No propose-authorize-enact pattern

**Graceful Degradation Requirements Added**:
- REQ-DEGRADE-001: Automation disable on CGM loss
- REQ-DEGRADE-002: Pump communication timeout handling
- REQ-DEGRADE-003: Remote control fallback
- REQ-DEGRADE-004: Layer transition logging
- REQ-DEGRADE-005: Safe state documentation
- REQ-DEGRADE-006: Delegate agent fallback

**Relationship to Existing Work**:
- Provides conceptual foundation for existing technical specifications
- L2-L3 state separation maps to OpenAPI specs
- L6 three-state model aligns with profile evolution proposal
- L7 narrative bus concept maps to Nightscout sync patterns
- L8-L9 gaps identify path forward for remote control and agent work

---

## Candidate Next Cycles

### Priority A: AAPS Plugin Architecture

**Value**: Understanding extensibility model for future integrations.

**Questions to answer**:
- Plugin interface contracts
- Dependency injection patterns
- Plugin lifecycle management
- How to add new pump/CGM drivers

### Priority B: Loop Watch Complications & Widgets

**Value**: Understanding how Loop surfaces data to Apple Watch and widgets.

**Questions to answer**:
- Watch complication data flow
- Widget timeline updates
- Shared app group data structures
- Background refresh patterns

### Priority C: Nightscout MongoDB Schema Deep Dive

**Value**: Understanding the actual MongoDB document structures beyond REST API.

**Questions to answer**:
- Index structures for performance
- Aggregation pipelines used
- Data retention and cleanup
- Migration patterns between versions

---

## Iteration Pattern

Each cycle should update:
1. Scenario backlog (if applicable)
2. Requirements snippet (REQ-xxx)
3. Spec delta (schema changes)
4. Mapping notes (per project)
5. Conformance update (when ready)
6. Gap/coverage update (GAP-xxx)

---

## Notes

- Focus on documenting effective protocols and suggesting test specs where protocol is clear
- Conformance tests can be added later when protocol understanding is solidified
- Leverage downloaded source code (`externals/`) for verification
- Keep terminology matrix updated as the rosetta stone for cross-project translation
