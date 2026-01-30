# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Entries before 2026-01-28 moved to [progress-archive-2026-01-17-to-23.md](docs/archive/progress-archive-2026-01-17-to-23.md)

---

## Completed Work

### Libre 3 Protocol Gap Analysis (2026-01-29)

Analyzed "eavesdrop only" limitations for Libre 3 vs Libre 1/2.

| Metric | Value |
|--------|-------|
| Source files analyzed | 5 |
| Gaps identified | 3 |
| Apps reviewed | DiaBLE, xdripswift, xDrip+ |

**Key Findings**:
- Libre 3 uses ECDH encryption requiring Abbott private keys
- Third-party apps cannot decrypt BLE data directly
- Only legal access: LibreLinkUp API (1-5 min delay)
- xDrip+ has no native Libre 3 support

**Gaps Added**:
- GAP-CGM-030: Direct BLE access blocked
- GAP-CGM-031: NFC limited to activation
- GAP-CGM-032: LibreLinkUp API dependency

**Deliverables**:
- `docs/10-domain/libre3-protocol-gap-analysis.md` (8.8KB)
- `traceability/cgm-sources-gaps.md` (+63 lines, 3 gaps)

---

### Cross-Controller Conflict Detection Analysis (2026-01-29)

Analyzed behavior when Loop + Trio sync to same Nightscout instance.

| Metric | Value |
|--------|-------|
| Source files analyzed | 12 |
| Gaps identified | 3 |
| Risk level | Medium |

**Key Findings**:
- deviceStatus: Loop uses `status.loop`, Trio uses `status.openaps` - no conflict
- enteredBy: Loop `loop://{device}`, Trio `Trio` - distinguishable
- Deduplication: identifier-based only, no cross-controller awareness
- Safe for read-only; caution for bidirectional sync

**Gaps Added**:
- GAP-SYNC-020: No cross-controller deduplication
- GAP-SYNC-021: No controller conflict warning
- GAP-SYNC-022: Profile sync ambiguity

**Deliverables**:
- `docs/10-domain/cross-controller-conflicts-deep-dive.md` (7.4KB)
- `traceability/sync-identity-gaps.md` (+77 lines, 3 gaps)

---

### Level 6: nocturne-modernization-analysis.md Coherence (2026-01-29)

Audited analysis document vs actual nocturne source code.

| Metric | Value |
|--------|-------|
| Claims verified | 10/12 |
| Exact matches | 7 |
| Close matches | 2 |
| Unverified | 2 |
| Coherence | **83%** |

**Verified Claims**:
- 927 C# files ✅ (exact)
- 438 Svelte components ✅ (exact)
- PostgreSQL database ✅ (postgres:17.6)
- .NET Aspire build ✅ (v13.x)
- Svelte 5 frontend ✅ (v5.37.0)
- Rust oref implementation ✅ (src/Core/oref/*.rs)
- Migration tooling ✅ (Migrate/Backup/Recovery commands)
- SignalR real-time ✅ (integration tests)

**Close Matches**:
- LOC: 281K actual vs 334K claimed (84%)
- Connectors: 11 actual vs 8 listed (undercounted)

**Unverified**:
- Redis cache (not in docker-compose)
- V4 endpoints (needs deeper check)

**LEVEL 6 COMPLETE** - All 4/4 items verified

---

### Level 6: lsp-integration-proposal.md Coherence (2026-01-29)

Audited proposal vs actual implementation.

| Metric | Value |
|--------|-------|
| Proposed Phases | 4 |
| Phases Implemented | 1 (partial) |
| Claimed Tools | 3 |
| Actual Tools | 1 (partial) |
| Coherence | 40% |

**Implemented**:
- Phase 1 (partial): `verify_refs.py` has line anchor parsing

**Not Implemented**:
- `lsp_query.py` (not found)
- JS/TS/Kotlin/Swift LSP integration
- Symbol verification

**Note**: Proposal is forward-looking (describes what to build, not claims)

**Accuracy**: 40% ✅ (coherent as proposal)

---

### Level 6: statistics-api-proposal.md Coherence (2026-01-29)

Audited proposal vs REQ-STATS-* requirements.

| Metric | Value |
|--------|-------|
| REQ-STATS-* Requirements | 5 |
| Addressed in Proposal | 5 (100%) |
| Endpoints Defined | 4 |
| Coherence | 100% |

**All requirements covered**:
- REQ-STATS-001: /api/v3/stats/daily ✅
- REQ-STATS-002: /api/v3/stats/summary ✅
- REQ-STATS-003: /api/v3/stats/hourly ✅
- REQ-STATS-004: /api/v3/stats/treatments ✅
- REQ-STATS-005: MCP resources ✅

**Note**: Proposal is source of requirements (self-coherent)

**Accuracy**: 100% ✅

---

### Level 6: algorithm-conformance-suite.md Coherence (2026-01-29)

Audited proposal vs actual implementation.

| Metric | Value |
|--------|-------|
| Proposal Phases | 5 |
| Phases Complete | 2 (40%) |
| Claimed Runners | 4 |
| Actual Runners | 1 (25%) |
| Coherence | 80% |

**Implemented**:
- Phase 1: vectors/ (5 categories, 85 tests)
- Phase 2: oref0-runner.js (13KB, 30.6% pass rate)

**Pending** (correctly documented):
- Phase 3: aaps-runner.kt
- Phase 4: loop-runner.swift
- Phase 5: rust-runner.rs (optional)

**Minor issue**: File tree diagram shows future runners as existing

**Accuracy**: 80% ✅

---

### Level 5: REQ-API-* OpenAPI Alignment (2026-01-29)

Audited API requirements → OpenAPI spec alignment. **LEVEL 5 COMPLETE!**

| Metric | Value |
|--------|-------|
| Total API Requirements | 35 |
| With OpenAPI spec | 22 (63%) |
| Without spec | 10 (29%) |
| Out of scope (UI) | 3 (8%) |

**Covered** (22): REQ-API/API3/SPEC/PLUGIN/ERR/NS-* via 8 OpenAPI specs

**Gaps** (10):
- REQ-STATS-* (5): No dedicated spec (proposed only)
- REQ-AUTH-* (3): No auth spec
- REQ-RG-* (4): Roles-gateway not specced

**Accuracy**: 100% ✅ - **Level 5 Complete: 4/4 (100%)**

---

### Level 5: REQ-CONNECT-* Completeness (2026-01-29)

Audited connector GAP→REQ completeness.

| Metric | Value |
|--------|-------|
| Total Connector GAPs | 28 |
| GAPs with REQs | 28 (100%) |
| Orphaned GAPs | 0 |

**All 8 categories have 1:1 GAP→REQ mapping**:
- GAP-CONNECT-* (6), GAP-NOCTURNE-* (3), GAP-TCONNECT-* (4)
- GAP-TEST-* (3), GAP-SHARE-* (3), GAP-LIBRELINK-* (3)
- GAP-LOOPFOLLOW-* (3), GAP-LOOPCAREGIVER-* (3)

**Accuracy**: 100% ✅

---

### Level 5: REQ-TREAT-* Traceability (2026-01-29)

Audited REQ-TREAT-* requirements for assertion coverage.

| Metric | Value |
|--------|-------|
| Total REQ-TREAT-* | 7 |
| With assertions | 7 (100%) |
| Without coverage | 0 (0%) |

**All covered** via `conformance/assertions/treatment-sync.yaml`:
- REQ-TREAT-040 to REQ-TREAT-046 (bolus, carbs, timestamp, duration, sync)

**Related gaps identified**:
- REQ-REMOTE-*: 11 reqs, 0% coverage
- REQ-ALARM-*: 10 reqs, 0% coverage
- REQ-UNIT-*: 4 reqs, 0% coverage

**Accuracy**: 100% ✅

---

### Level 5: REQ-SYNC-* Traceability (2026-01-29)

Audited REQ-SYNC-* requirements for assertion coverage using `verify_assertions.py`.

| Metric | Value |
|--------|-------|
| Total REQ-SYNC-* | 18 |
| With assertions | 15 (83%) |
| Without coverage | 3 (17%) |

**Covered** (15): REQ-SYNC-036 to REQ-SYNC-050 via `sync-deduplication.yaml`

**Uncovered** (3):
| Requirement | Title | Reason |
|-------------|-------|--------|
| REQ-SYNC-001 | Document WebSocket API | Documentation req (no test) |
| REQ-SYNC-002 | Consistent Sync Identity | Needs v1/v3 integration test |
| REQ-SYNC-003 | Sync Status Response | Needs assertion |

**Accuracy**: 100% ✅ - Tool output matches manual analysis

---

### Level 4: GAP-CONNECT-* Verification (2026-01-29)

Verified connector gap accuracy against source code. **LEVEL 4 COMPLETE!**

| Claim | Evidence | Status |
|-------|----------|--------|
| GAP-CONNECT-001: nightscout-connect v1 only | `nightscout.js:35,48` - `/api/v1/` | ✅ Verified |
| GAP-CONNECT-004: No test suite | `package.json` - `echo "no test"` | ✅ Verified |
| GAP-TCONNECT-001: tconnectsync v1 only | `nightscout.py` - `api/v1/` | ✅ Verified |
| GAP-SHARE-001: share2nightscout-bridge v1 only | `index.js` - `/api/v1/entries.json` | ✅ Verified |
| GAP-SHARE-003: Hardcoded app ID | `d89443d2-327c...` in index.js | ✅ Verified |
| GAP-LIBRELINK-001: v3 stub throws | `apiv3.ts` - `'Not implemented'` | ✅ Verified |
| GAP-LOOPFOLLOW-001: v1 API only | `NightscoutUtils.swift` - `/api/v1/` | ✅ Verified |
| GAP-LOOPCAREGIVER-001: Loop-only | All refs Loop-specific | ✅ Verified |

**Level 4 Complete**: 6/6 items (100%) ✅

---

### Level 4: GAP-TREAT-* Verification (2026-01-29)

Verified treatment gap accuracy against Loop, AAPS, Trio, and Nightscout source code.

| Claim | Evidence | Status |
|-------|----------|--------|
| GAP-OVERRIDE-001: Loop vs AAPS model | Loop `TemporaryOverride`, AAPS `ProfileSwitch` | ✅ Verified |
| GAP-OVERRIDE-002: Percentage inversion | AAPS `percentage`, Loop `insulinNeedsScaleFactor` | ✅ Verified |
| GAP-OVERRIDE-004/007: Trio settings lost | `OverrideStorage.swift` uploads only duration/notes | ✅ Verified |
| GAP-OVERRIDE-005: Trio uses Exercise | `nsExercise = "Exercise"` in helper | ✅ Verified |
| GAP-REMOTE-001: Override OTP not required | `OverrideRemoteNotification.swift:44-46` returns false | ✅ Verified |
| GAP-REMOTE-008: No server bolus limits | `loop.js:96` only checks `> 0.0` | ✅ Verified |
| GAP-TREAT-001: Loop absorption in seconds | `TimeInterval` throughout CarbKit | ✅ Verified |
| GAP-TREAT-003: AAPS SMB type field | `type: "SMB"` in RemoteTreatment.kt | ✅ Verified |
| GAP-TREAT-005: Loop POST duplicates | `DoseEntry.swift` comment confirms | ✅ Verified |

**Level 4 Progress**: 5/6 items complete (83%)

---

### Level 4: GAP-SYNC-* Verification (2026-01-29)

Verified sync identity and timezone gap accuracy against source code.

| Claim | Evidence | Status |
|-------|----------|--------|
| GAP-SYNC-001: Loop POST-only, no upsert | No PUT endpoints in NightscoutService | ✅ Verified |
| GAP-SYNC-002: Effect timelines not uploaded | `LoopAlgorithmEffects` exists but not synced | ✅ Verified |
| GAP-SYNC-005: ObjectIdCache not persistent | 24h expiry, memory-only (`NightscoutService.swift:27`) | ✅ Verified |
| GAP-SYNC-006: Loop v1 API only | `apiSecret` auth, no v3 in NightscoutService | ✅ Verified |
| GAP-SYNC-007: syncIdentifier format varies | No format validation in ObjectIDMapping | ✅ Verified |
| GAP-TZ-002: Medtrum GMT+12 bug | `SetTimeZonePacket.kt:29-34` workaround | ✅ Verified |
| GAP-TZ-005: AAPS fixed offset storage | 40+ entities use `getOffset(timestamp)` | ✅ Verified |
| GAP-TZ-006: Loop ETC timezone format | `profilefunctions.js:179-180` buggy replace | ✅ Verified |
| GAP-TZ-007: Missing TZ uses server local | `profilefunctions.js:108-110` explicit TODO | ✅ Verified |

**Level 4 Progress**: 4/6 items complete (67%)

---

### Level 4: GAP-API-* Verification (2026-01-29)

Verified Nightscout API gap accuracy against cgm-remote-monitor source.

| Claim | Evidence | Status |
|-------|----------|--------|
| GAP-API-001: v1 cannot detect deletions | v3 has `isValid=false`, v1 has no mechanism | ✅ Verified |
| GAP-API-002: `_id` vs `identifier` | `utils.js:15,113-140` fallback logic | ✅ Verified |
| GAP-API-003: No v3 for iOS | Loop no v3 refs, AAPS has `NSClientV3Plugin` | ✅ Verified |
| GAP-API-004: v1 all-or-nothing auth | `api-secret` full access, v3 has `permissionGroups` | ✅ Verified |
| GAP-API-005: Dedup behavior differs | v3 `isDeduplication` field, v1 silent | ✅ Verified |
| v3 srvModified tracking | 50+ refs in v3 code | ✅ Verified |

**Level 4 Progress**: 3/6 items complete (50%)

---

### Level 4: GAP-ALG-* Verification (2026-01-29)

Verified algorithm gap accuracy against source code and conformance suite.

| Claim | Evidence | Status |
|-------|----------|--------|
| GAP-ALG-001: oref0 runner exists | `conformance/runners/oref0-runner.js` | ✅ Verified |
| GAP-ALG-001: 85 AAPS vectors | `androidTest/assets/results/*.json` = 85 files | ✅ Verified |
| GAP-ALG-002: 69% divergence | `conformance-summary.json`: 30.6% pass = 69.4% fail | ✅ Verified |
| GAP-ALG-003: oref0 4 curves | `determine-basal.js:442-445` (IOB/COB/UAM/ZT) | ✅ Verified |
| GAP-ALG-003: Loop single curve | `predictedGlucose` array | ✅ Verified |
| oref0 test files exist | `tests/*.test.js` (5+ files) | ✅ Verified |
| GAP-CARB-001: Still open | No resolution found | ✅ Verified |

**Level 4 Progress**: 2/6 items complete (33%)

---

### Level 3: Pump Communication Deep Dive (2026-01-29)

Verified pump-communication-deep-dive.md claims against source code.

| Claim | Source | Status |
|-------|--------|--------|
| Omnipod Eros 433.91 MHz | `PodComms.swift:560` | ✅ Verified |
| Medtronic 916.5/868 MHz | `PumpOpsSession.swift:795,797` | ✅ Verified |
| RileyLink submodule | `.gitmodules:13-15` | ✅ Verified |
| PumpManager protocol | `PumpManager.swift:67` | ✅ Verified |
| enactBolus method | `PumpManager.swift:170` | ✅ Verified |
| enactTempBasal method | `PumpManager.swift:186` | ✅ Verified |
| BasalDeliveryState/BolusState | `PumpManagerStatus.swift:38-60` | ✅ Verified |
| AAPS Pump interface | `Pump.kt:19` | ✅ Verified |

**Level 3 Progress**: 8/8 items complete (100%) ✅

---

### Level 3: Libre Protocol Deep Dive (2026-01-29)

Verified libre-protocol-deep-dive.md claims against source code.

| Claim | Source | Status |
|-------|--------|--------|
| Libre 1 NFC unencrypted | `Libre.swift:91-93` (encryptedFram empty) | ✅ Verified |
| Libre 2 encrypted FRAM | `Libre.swift:86,93`, `OOP.swift:390` | ✅ Verified |
| Libre 3 ECDH + AES-CCM | `Libre3.swift:1011-1012`, `Crypto.swift:11-19` | ✅ Verified |
| PatchInfo byte mappings | `Libre.swift:11-18` (0xDF→libre1, 0x9D→libre2) | ✅ Verified |
| NFC command 0xA1 | `NFC.swift:55-56,280` | ✅ Verified |
| IC Manufacturer 0x07/0x7a | `Abbott.swift:59`, `Libre2Gen2.swift:131` | ✅ Verified |
| 60 min warmup | `Console.swift:190` | ✅ Verified |

**Level 3 Progress**: 7/8 items complete (87.5%)

---

### Level 3: Treatments Deep Dive (2026-01-29)

Verified treatments-deep-dive.md claims against source code.

| Claim | Source | Status |
|-------|--------|--------|
| Loop `deliveredUnits` | `DoseEntry.swift:40` | ✅ Verified |
| AAPS `amount` for insulin | `Bolus.kt:44` | ✅ Verified |
| AAPS Bolus.Type enum | `Bolus.kt:52-55` (NORMAL, SMB, PRIMING) | ✅ Verified |
| Loop `syncIdentifier` | `DoseEntry.swift:40` | ✅ Verified |
| AAPS `interfaceIDs.nightscoutId` | Transaction files | ✅ Verified |
| Loop `automatic` boolean | `DoseEntry.swift:22`, `UnfinalizedDose.swift:59` | ✅ Verified |
| xDrip+ `uuid` for sync | `Treatments.java:297`, `NightscoutUploader.java:782` | ✅ Verified |
| AAPS SMB eventType | `BolusExtension.kt:28` (Correction Bolus) | ✅ Verified |

**Level 3 Progress**: 6/8 items complete (75%)

---

### Level 3: Entries Deep Dive (2026-01-29)

Verified entries-deep-dive.md claims against source code.

| Claim | Source | Status |
|-------|--------|--------|
| xDrip+ `calculated_value` | `BgReading.java:119-120` | ✅ Verified |
| Loop `HKQuantity` glucose | `NewGlucoseSample.swift` | ✅ Verified |
| AAPS `value` field | `GlucoseValue.kt:40` | ✅ Verified |
| xDrip+ `dg_slope` trend | `BgReading.java:188-189` | ✅ Verified |
| Entry types sgv/mbg/cal | `data-layer-audit.md:73` | ✅ Verified |
| Loop `provenanceIdentifier` | `CachedGlucoseObject+CoreDataProperties.swift:22` | ✅ Verified |
| AAPS `trendArrow` | `GlucoseValue.kt:41` | ✅ Verified |
| Loop `GlucoseTrend` | `GlucoseDisplayable.swift:20` | ✅ Verified |

**Level 3 Progress**: 5/8 items complete (62.5%)

---

### Level 3: DeviceStatus Deep Dive (2026-01-29)

Verified devicestatus-deep-dive.md claims against source code.

| Claim | Source | Status |
|-------|--------|--------|
| Loop uses `loop` top-level | `StoredDosingDecision.swift:150` | ✅ Verified |
| Trio/AAPS use `openaps` top-level | `NightscoutStatus.swift:5`, `NSDeviceStatus.kt:30` | ✅ Verified |
| Loop device format `loop://` | `StoredDosingDecision.swift:146` | ✅ Verified |
| Trio device = `"Trio"` | `NightscoutTreatment.swift:27` | ✅ Verified |
| AAPS device format `openaps://` | `NSDeviceStatus.kt:26` | ✅ Verified |
| oref0 predBGs (IOB/COB/UAM/ZT) | `determine-basal.js:657-690` | ✅ Verified |
| Loop overrideStatus field | `StoredDosingDecision.swift:118,160` | ✅ Verified |
| AAPS pump.reservoir/clock | `NSDeviceStatus.kt:35-36` | ✅ Verified |

**Level 3 Progress**: 4/8 items complete (50%)

---

### Level 3: CGM Data Sources Deep Dive (2026-01-29)

Verified cgm-data-sources-deep-dive.md claims against source code.

| Claim | Source | Status |
|-------|--------|--------|
| xDrip+ 20+ data sources | `DexCollectionType.java` (26 enums) | ✅ Verified |
| xDrip+ Ob1 collector | `Ob1G5StateMachine`, `Ob1G5CollectionService` | ✅ Verified |
| xDrip+ NSFollow/SHFollow | `SourceWizard.java:60-61` | ✅ Verified |
| Loop CGMBLEKit | `LoopWorkspace/CGMBLEKit/` | ✅ Verified |
| Loop G7SensorKit | `LoopWorkspace/G7SensorKit/` | ✅ Verified |
| xDrip4iOS CGM types | `BluetoothTransmitter/CGM/` (3 dirs) | ✅ Verified |
| LibreLinkUp endpoint | `/llu/connections` in tests | ✅ Verified |

**Level 3 Progress**: 3/8 items complete (37.5%)

---

### Level 3: Algorithm Comparison Deep Dive (2026-01-29)

Verified algorithm-comparison-deep-dive.md claims against source code.

| Claim | Source | Status |
|-------|--------|--------|
| oref0: 4 prediction arrays | `determine-basal.js:442-445` | ✅ Verified |
| oref0: SMB function | `determine-basal.js:51` | ✅ Verified |
| oref0: Autosens | `determine-basal.js:128,249` | ✅ Verified |
| AAPS: Dynamic ISF (TDD) | `OpenAPSSMBPlugin.kt:268` | ✅ Verified |
| Loop: Retrospective Correction | `LoopMath.swift:16-17` | ✅ Verified |
| Loop: Automatic Bolus | `LoopDataManager.swift:1819` | ✅ Verified |
| Trio: JavaScript calls | `Script.swift:9` | ✅ Verified |

**Level 3 Progress**: 2/8 items complete (25%)

---

### Accuracy Verification: G7 Protocol + Refs (2026-01-29)

Executed first accuracy verification items from bottom-up queue.

| Item | Result | Method |
|------|--------|--------|
| **#17: G7 protocol claims** | **100% accurate** | Manual grep vs 5 source files |
| **#1-4: Source refs** | **91% valid** (356/391) | `python tools/verify_refs.py` |

**G7 Claims Verified**:
| Claim | Source Evidence |
|-------|-----------------|
| Service UUID `F8083532-...` | `DiaBLE/Dexcom.swift:51` |
| 26 opcodes defined | `DiaBLE/DexcomG7.swift:20-47` |
| secp256r1 curve | `xDrip/libkeks/Curve.java:24` |
| J-PAKE auth flow | `xDrip/libkeks/Calc.java` |
| G7SensorKit files (7) | `LoopWorkspace/G7SensorKit/...` |

**Refs Breakdown**:
- 356 valid refs (91%)
- 35 broken (33 in archive, 2 intentional examples)
- Active docs: 100% valid

---

### Level 2: Mapping Verification (2026-01-29) ✅ COMPLETE

Verified xDrip, AAPS, Loop, Trio mappings and terminology matrix against source code.

| Mapping | Result | Files Checked |
|---------|--------|---------------|
| `mapping/xdrip-android/nightscout-sync.md` | **100% accurate** | `UploaderQueue.java`, `NightscoutUploader.java` |
| `mapping/aaps/nsclient-schema.md` | **100% accurate** | `RemoteTreatment.kt`, `RemoteEntry.kt`, `EventType.kt` |
| `mapping/loop/sync-identity-fields.md` | **100% accurate** | `DoseEntry.swift`, `ObjectIdCache.swift`, `NightscoutService.swift` |
| `mapping/trio/nightscout-sync.md` | **100% accurate** | `NightscoutAPI.swift`, `NightscoutStatus.swift`, `NightscoutManager.swift` |
| `terminology-matrix.md` (10% sample) | **100% accurate** | 15 terms across 6 repos |

**Terminology Sample Verified**:
- AAPS: HeartRate fields, insulinEndTime, TrendArrow enum
- oref0: curve models (rapid-acting), prediction arrays (IOB/COB/UAM/ZT)
- Nightscout: direction values, secp256r1 curve

**Level 2 Complete**: 5/5 items (100%)

---

### Bottom-up Accuracy Review Queue (2026-01-29)

Created systematic verification queue for documentation accuracy, organized from evidence sources through to proposals.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Documentation Accuracy Backlog** | `docs/sdqctl-proposals/backlogs/documentation-accuracy.md` | 31 items across 6 levels |
| **Backlog Updates** | All 5 domain backlogs | Verification items cross-referenced |
| **Ready Queue Additions** | `ECOSYSTEM-BACKLOG.md` | +3 accuracy items (#6-8) |

**6-Level Verification Hierarchy**:
| Level | Focus | Items |
|-------|-------|-------|
| 1 | Evidence Sources | 4 items (code ref verification) |
| 2 | Mappings | 5 items (field coverage) |
| 3 | Deep Dives | 8 items (claim verification) |
| 4 | Gaps | 6 items (freshness check) |
| 5 | Requirements | 4 items (scenario coverage) |
| 6 | Proposals | 4 items (coherence) |

**Tool Proposals for sdqctl Team**:
- `verify_gap_freshness.py` - Check if documented gaps still exist
- `verify_mapping_coverage.py` - Compare mapping docs vs source fields
- `sample_terminology.py` - Random sample verification of terminology

**Current Verification Tooling State**:
| Tool | Status | Coverage |
|------|--------|----------|
| `verify_refs.py` | ✅ Working | 91% valid (356/391 refs) |
| `verify_assertions.py` | ✅ Working | 15% REQ coverage (27/180) |
| `gen_coverage.py` | ✅ Working | Traceability matrix |

---

### Playwright E2E PR Submission (2026-01-29)

Created PR submission guide for Playwright E2E tests to be contributed to cgm-remote-monitor.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **PR Guide** | `conformance/e2e-nightscout/PR-SUBMISSION.md` | 4.6 KB, full PR template |

**Package Contents** (ready for upstream PR):
| File | Tests | Purpose |
|------|-------|---------|
| `api.spec.js` | 10 | API v1/v3 smoke tests |
| `dashboard.spec.js` | 8 | UI, Socket.IO, mobile |
| `playwright.config.js` | - | Multi-browser config |

**Next Step**: Submit PR to `nightscout/cgm-remote-monitor:dev`

---

### sdqctl VERIFY CLI Discovery (2026-01-29)

Discovered that `sdqctl verify` CLI commands are already implemented and functional. Updated proposal status and added Makefile integration targets.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal Update** | `docs/sdqctl-proposals/VERIFICATION-DIRECTIVES.md` | Status → ✅ IMPLEMENTED |
| **Makefile Targets** | `Makefile` | +2 targets: `sdqctl-verify-refs`, `sdqctl-verify-all` |

**Available sdqctl verify Commands**:
| Command | Purpose |
|---------|---------|
| `sdqctl verify refs` | Validate @-references and alias:refs |
| `sdqctl verify all` | Run all verifications |
| `sdqctl verify terminology` | Term consistency |
| `sdqctl verify assertions` | Assertion tracing |

**Key Finding**: The VERIFY CLI was already implemented in sdqctl. Remaining work is Phase 2: native VERIFY directive in .conv files.

---

### Conformance CI Integration (2026-01-29)

Integrated algorithm conformance suite with CI pipeline and added Makefile targets.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Makefile Targets** | `Makefile` | +2 targets: `conformance-algorithms`, `conformance-ci` |
| **CI Workflow** | `.github/workflows/ci.yml` | +38 lines, new `algorithm-conformance` job |
| **Documentation** | `conformance/README.md` | 148 lines, usage guide |

**New Make Targets**:
| Target | Purpose |
|--------|---------|
| `make conformance` | Assertion-based tests (existing) |
| `make conformance-algorithms` | Algorithm conformance suite |
| `make conformance-ci` | Both in CI mode (strict exit codes) |

**CI Features**:
- Node.js 18 setup for oref0 runner
- Bootstrap external repos automatically
- Upload results as artifact
- `continue-on-error: true` for known divergence

---

### xdrip-js Deep Dive (2026-01-29)

Analyzed xdrip-js Node.js CGM interface library for Raspberry Pi-based Dexcom receivers.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/xdrip-js-deep-dive.md` | 380 lines, architecture + integration |
| **Gaps** | `traceability/cgm-sources-gaps.md` | +4 gaps (GAP-XDRIPJS-001 to 004) |
| **Gaps Index** | `traceability/gaps.md` | 216 → 220 total |

**Key Findings**:
- Library-only architecture (no built-in Nightscout upload)
- G5/G6 only (no G7 J-PAKE support)
- Deprecated noble BLE library (2018 fork)
- Trend-to-direction mapping not standardized

**Gaps Identified**:
| Gap | Title |
|-----|-------|
| GAP-XDRIPJS-001 | No G7 Support |
| GAP-XDRIPJS-002 | Deprecated BLE Library (noble) |
| GAP-XDRIPJS-003 | No Direct Nightscout Integration |
| GAP-XDRIPJS-004 | Trend-to-Direction Mapping Not Standardized |

---

### Connectors Requirements Generation (2026-01-29)

Generated 28 requirements from 28 connector gaps, closing the connectors domain requirements gap.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Connectors Requirements** | `traceability/connectors-requirements.md` | 28 REQs covering 8 connector prefixes |
| **Requirements Index** | `traceability/requirements.md` | Updated to 185 (180 unique) |
| **Terminology Matrix** | `mapping/cross-project/terminology-matrix.md` | +14 connector REQ/GAP prefixes |

**Requirements Created by Prefix**:
| Prefix | Count | Focus |
|--------|-------|-------|
| REQ-CONNECT-* | 6 | nightscout-connect core |
| REQ-NOCTURNE-* | 3 | Nocturne-specific |
| REQ-TCONNECT-* | 4 | tconnectsync |
| REQ-TEST-* | 3 | Testing infrastructure |
| REQ-SHARE-* | 3 | share2nightscout-bridge |
| REQ-LIBRELINK-* | 3 | nightscout-librelink-up |
| REQ-LOOPFOLLOW-* | 3 | LoopFollow |
| REQ-LOOPCAREGIVER-* | 3 | LoopCaregiver |

**Metrics**:
| Metric | Before | After |
|--------|--------|-------|
| Total requirements | 157 | 185 (180 unique) |
| Connectors domain | 0 REQs | 28 REQs |
| Gap-to-REQ coverage | 28 gaps / 0 REQs | 28 gaps / 28 REQs |

---

### Assertion-to-Requirement Linkage Audit (2026-01-29)

Linked all 23 orphaned assertions to requirements, improving traceability coverage.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Sync Requirements** | `traceability/sync-identity-requirements.md` | +20 REQs (REQ-SYNC-036 to REQ-SYNC-050, REQ-OVERRIDE-001 to 005) |
| **Treatment Requirements** | `traceability/treatments-requirements.md` | +7 REQs (REQ-TREAT-040 to REQ-TREAT-046) |
| **Sync Gap** | `traceability/sync-identity-gaps.md` | +1 GAP (GAP-SYNC-001) |
| **Updated Assertions** | `conformance/assertions/*.yaml` | 3 files updated with requirement links |
| **Enhanced verify_assertions.py** | `tools/verify_assertions.py` | +20 lines, multi-file loading |

**Before/After**:
| Metric | Before | After |
|--------|--------|-------|
| Orphaned assertions | 23 | 0 |
| Requirements covered | 7 | 27 |
| Known requirements | 0 | 155 |
| Known gaps | 0 | 200 |
| Requirement coverage | 0% | 17.4% |

**Tool Improvements**:
- `verify_assertions.py` now scans all `*-requirements.md` and `*-gaps.md` files
- `verify_assertions.py` merges scenario-level requirements with assertion-level
- `REQ_PATTERN` updated to match domain-prefixed IDs (e.g., `REQ-SYNC-036`)

**Requirements Created**:
- REQ-SYNC-036 to 050: Sync deduplication (identity preservation, queries, timestamps)
- REQ-OVERRIDE-001 to 005: Override supersede behavior
- REQ-TREAT-040 to 046: Treatment sync validation

---

### Backlog Replenishment and Tooling Proposals (2026-01-29)

Comprehensive state check and backlog refresh with new tooling proposals.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Audit Tooling Proposal** | `docs/sdqctl-proposals/audit-verification-tooling-proposal.md` | 6 new tools proposed |
| **Ready Queue** | `docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md` | 7 items refreshed |
| **Domain Backlogs** | `docs/sdqctl-proposals/backlogs/*.md` | 11 new items across 4 domains |

**Key Findings**:
- 23 orphaned assertions with 0% requirement coverage
- 28 connector gaps with 0 requirements → need REQ generation
- 69% algorithm divergence discovered manually → needs CI visibility
- 8% broken refs → need automated refresh

**New Backlog Items Added**:
1. [P1] Assertion-to-Requirement Linkage Audit
2. [P2] Connectors Requirements Generation
3. [P2] sdqctl VERIFY Directive Implementation
4. [P2] Conformance Test Executor Integration
5. [P3] CGM trend arrow standardization
6. [P3] Libre 3 protocol gap analysis
7. [P2] Playwright E2E PR submission

**Tooling Proposals Created**:
- verify_traceability.py - Gap→REQ→Scenario coverage
- link_assertions.py - Orphan linking
- gen_requirements.py - REQ generation from gaps
- run_conformance_ci.py - CI integration
- detect_stale_refs.py - Staleness detection
- ecosystem-audit plugin - Unified audit command

---

### Algorithm Conformance Suite Orchestrator (2026-01-29)

Created unified orchestrator for running algorithm conformance tests.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Orchestrator** | `tools/conformance_suite.py` | 308 lines |
| **JSON Report** | `conformance/results/conformance-summary.json` | Unified results |
| **Markdown Report** | `conformance/results/conformance-summary.md` | Human-readable |

**Features**:
- Runs oref0-runner.js (aaps/loop stubs ready)
- Aggregates results by category
- CI mode with strict exit codes
- `--report-only` for regenerating from cached results

**Current Results** (oref0):
- 85 tests, 26 passed (30.6%)
- basal-adjustment: 77 tests, 31% pass
- low-glucose-suspend: 8 tests, 25% pass

---

### Line Anchor Validation for verify_refs.py (2026-01-29)

Implemented Phase 1 of LSP integration proposal - line anchor validation.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Enhanced verify_refs.py** | `tools/verify_refs.py` | +80 lines (406 → 486) |

**New Capabilities**:
- Validates `#L10` and `#L10-L50` line anchors
- Checks line numbers are within file bounds
- Reports `line_out_of_range`, `invalid_line`, `invalid_range` errors
- Line anchor coverage stats in report

**Validation Results**:
- 390 total refs scanned
- 135 refs with line anchors
- 134 line anchors valid (99.3%)

---

### Field Transform Test Suite (2026-01-29)

Created comprehensive field transform testing infrastructure.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Test Runner** | `tools/test_transforms.py` | 617 lines |
| **Core Transforms** | `conformance/field-transforms/transforms.yaml` | 188 lines |
| **Entry Transforms** | `conformance/field-transforms/entries.yaml` | 139 lines |
| **Treatment Transforms** | `conformance/field-transforms/treatments.yaml` | 323 lines |
| **README** | `conformance/field-transforms/README.md` | 166 lines |

**Transform Types Supported**:
- rename, extract, coerce, default, compute
- Nested field extraction with dot notation
- Array index support (`values[0]`)

**Test Coverage**: 28 passing tests across Loop, AAPS, Trio, xDrip → Nightscout

**Total**: 1,433 lines

---

### Playwright E2E Test Suite for Nightscout (2026-01-29)

Created Playwright E2E test infrastructure for cgm-remote-monitor.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Config** | `conformance/e2e-nightscout/playwright.config.js` | 101 lines |
| **Dashboard Tests** | `conformance/e2e-nightscout/dashboard.spec.js` | 179 lines |
| **API Tests** | `conformance/e2e-nightscout/api.spec.js` | 144 lines |
| **README** | `conformance/e2e-nightscout/README.md` | 167 lines |

**Key Features**:
- Multi-browser support (Chrome, Firefox, Safari, mobile)
- Dashboard smoke tests (8 scenarios)
- API v1/v3 smoke tests (9 scenarios)
- CI integration template for GitHub Actions
- Ready to submit as PR to cgm-remote-monitor

**Total**: 591 lines of test infrastructure

---

### Loop vs oref0 Semantic Equivalence Analysis (2026-01-29)

Analyzed Loop algorithm to determine conformance testing feasibility with oref0 vectors.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/loop-oref0-semantic-equivalence.md` | 400 lines |

**Key Findings**:
- Loop uses single combined prediction curve (vs oref0's 4 curves)
- Loop has no Autosens - uses RetrospectiveCorrection instead
- Loop has no SMB or UAM curve
- Direct output comparison NOT feasible
- Loop needs its own Swift-based conformance runner
- oref0 test vectors cannot be reused (missing raw dose history)

**Gaps Identified**: GAP-ALG-013, GAP-ALG-014, GAP-ALG-015, GAP-ALG-016

---

### AAPS vs oref0 Divergence Analysis (2026-01-29)

Analyzed 69% divergence in conformance testing between AAPS and oref0 algorithm outputs.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/aaps-oref0-divergence-analysis.md` | 280 lines |

**Key Findings**:
- 85 test vectors from AAPS ReplayApsResultsTest fixtures
- OpenAPSSMBPlugin (vanilla oref0): 94% pass rate - effectively identical
- OpenAPSSMBDynamicISFPlugin: 18% pass rate - major divergence
- OpenAPSSMBAutoISFPlugin: 5% pass rate - very high divergence
- Root cause: DynamicISF and AutoISF are AAPS-specific extensions not in oref0
- Core oref0 algorithm is preserved in AAPS Kotlin port

**Gaps Identified**: GAP-ALG-009, GAP-ALG-010, GAP-ALG-011, GAP-ALG-012

---

### Algorithm Core Terminology Mapping (2026-01-29)

Added comprehensive algorithm terminology mapping across Loop, AAPS, Trio, and oref0.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Terminology** | `mapping/cross-project/terminology-matrix.md` | +95 lines |

**Key Findings**:
- ISF: `sens` (oref0/Trio) vs `insulinSensitivity` (Loop) vs `isf/getIsfMgdl()` (AAPS)
- CR: `carb_ratio` (oref0) vs `carbRatio` (Loop) vs `ic/getIc()` (AAPS)
- DIA: Consistent `dia` or `actionDuration` across systems
- UAM: Full support in oref0/AAPS/Trio; notification-only in Loop (`MissedMeal`)
- SMB: Supported in oref0/AAPS/Trio; NOT supported in Loop
- Autosens: Supported in oref0/AAPS/Trio; NOT in Loop (uses `RetrospectiveCorrection`)

**Gaps Referenced**: GAP-ALG-005 (Loop lacks SMB/UAM), GAP-ALG-006 (DynISF differences)

---

### xDrip+ Nightscout Field Mapping (2026-01-29)

Created comprehensive field mapping for xDrip+ Nightscout uploads.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Field Mapping** | `mapping/xdrip/nightscout-fields.md` | 306 lines |
| **README** | `mapping/xdrip/README.md` | 64 lines |

**Key Findings**:
- Uses Nightscout v1 API only (entries, treatments, devicestatus, activity)
- Device string format: `"xDrip-{collection_method}"` with optional source_info
- Treatment sync via UUID field and lookup/delete pattern
- Activity endpoint for heart rate, steps, motion (non-standard)
- Supports 20+ CGM data sources via collection method setting
- GZIP compression support for uploads

**Gaps Identified**: GAP-XDRIP-001, GAP-XDRIP-002, GAP-XDRIP-003

---

### CGM Sensor Session Handling Comparison (2026-01-29)

Created cross-project comparison of CGM sensor session handling across xDrip+, DiaBLE, Loop, and AAPS.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-session-handling-deep-dive.md` | 407 lines |

**Key Findings**:
- xDrip+: Comprehensive CalibrationState enum with 25+ states
- DiaBLE: SensorState enum (notActivated, warmingUp, active, expired, shutdown, failure)
- Loop: CgmEvent model with explicit warmupPeriod property
- AAPS: TherapyEvent types (SENSOR_CHANGE, SENSOR_STARTED, SENSOR_STOPPED)
- No standard Nightscout schema for session events
- Warm-up duration varies by sensor (30min to 2hr) but not uploaded

**Gaps Identified**: GAP-SESSION-001, GAP-SESSION-002, GAP-SESSION-003, GAP-SESSION-004

---

### DiaBLE Deep Dive (2026-01-29)

Created comprehensive deep-dive documentation for DiaBLE iOS/watchOS CGM reader application.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/diable-deep-dive.md` | 487 lines |

**Key Findings**:
- Supports both Abbott Libre (1/2/3) and Dexcom (G6/G7) sensors
- Nightscout integration: v1 API only, SGV entries upload, no treatments
- Libre 3: Partial support (eavesdrop mode, cannot decrypt independently)
- Dexcom G7: App-dependent (no standalone J-PAKE authentication)
- Native Apple Watch app with direct BLE connectivity proof-of-concept
- Temperature-based calibration from LibreLink 2.3 algorithm

**Gaps Identified**: GAP-DIABLE-002, GAP-DIABLE-003 (GAP-CGM-001 previously existed)

---

### LoopCaregiver Deep Dive (2026-01-29)

Created comprehensive deep-dive documentation for LoopCaregiver remote command app.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/loopcaregiver-deep-dive.md` | 417 lines |

**Key Findings**:
- Remote commands: Bolus, Carbs, Override, Autobolus, Closed Loop
- Security: API secret + TOTP + 5-minute expiration
- V1 commands via push notifications
- V2 commands (experimental) add status tracking
- Loop-only support (no Trio/OpenAPS)

**Gaps Identified**: GAP-LOOPCAREGIVER-001, GAP-LOOPCAREGIVER-002, GAP-LOOPCAREGIVER-003

---

### LoopFollow Deep Dive (2026-01-29)

Created comprehensive deep-dive documentation for LoopFollow caregiver monitoring app.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/loopfollow-deep-dive.md` | 411 lines |

**Key Findings**:
- Consumes Nightscout API v1: entries, treatments, devicestatus, profile
- Supports Loop, OpenAPS, and Trio devicestatus formats
- Multi-source: Dexcom Share primary with Nightscout fallback
- Remote commands via APNS (Loop), TRC (Trio), Nightscout
- Multi-instance: 3 concurrent LoopFollow apps supported

**Gaps Identified**: GAP-LOOPFOLLOW-001, GAP-LOOPFOLLOW-002, GAP-LOOPFOLLOW-003

---

### nightscout-librelink-up Field Mapping (2026-01-29)

Created comprehensive field mapping documentation for LibreLink Up bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **README** | `mapping/nightscout-librelink-up/README.md` | 76 lines, index |
| **API** | `mapping/nightscout-librelink-up/api.md` | 258 lines, LibreLink Up API |
| **Entries** | `mapping/nightscout-librelink-up/entries.md` | 274 lines, field mapping |

**Key Findings**:
- 8 API regions (EU, EU2, US, AU, DE, FR, JP, AP)
- Multi-patient support via `LINK_UP_CONNECTION`
- Trend arrow limited to 5 values (no DoubleUp/DoubleDown)
- Uses FactoryTimestamp (sensor time) not local phone time
- v1 API only (v3 stub throws error)

**Gaps Identified**: GAP-LIBRELINK-001, GAP-LIBRELINK-002, GAP-LIBRELINK-003

---

### share2nightscout-bridge Field Mapping (2026-01-29)

Created comprehensive field mapping documentation for Dexcom Share bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **README** | `mapping/share2nightscout-bridge/README.md` | 70 lines, index |
| **API** | `mapping/share2nightscout-bridge/api.md` | 178 lines, Dexcom Share API |
| **Entries** | `mapping/share2nightscout-bridge/entries.md` | 176 lines, field mapping |

**Key Findings**:
- Dexcom timestamp format: `/Date(milliseconds-offset)/` parsed with regex
- Trend values 0-9 map to direction strings
- Device identifier always `"share2"`
- Uses v1 API only (no v3 support - GAP-SHARE-001)
- No backfill logic for missed readings (GAP-SHARE-002)
- Hardcoded applicationId (GAP-SHARE-003)

**Gaps Identified**: GAP-SHARE-001, GAP-SHARE-002, GAP-SHARE-003

---

### tconnectsync Field Mapping (2026-01-29)

Created comprehensive field mapping documentation for Tandem t:connect sync tool.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **README** | `mapping/tconnectsync/README.md` | 79 lines, index |
| **Models** | `mapping/tconnectsync/models.md` | 159 lines, Bolus/TherapyEvent/Profile |
| **API** | `mapping/tconnectsync/api.md` | 198 lines, t:connect endpoints |
| **Treatments** | `mapping/tconnectsync/treatments.md` | 171 lines, 10+ treatment types |

**Key Findings**:
- Maps 10+ t:connect events to Nightscout treatment types
- Uses v1 API only (no v3 support - GAP-TCONNECT-001)
- 3 auth methods: OIDC, Android credentials, web form
- No trend direction in CGM data (GAP-TCONNECT-004)
- Batch sync only, no real-time push

**Gaps Identified**: GAP-TCONNECT-004 (no trend direction)

---

### Nocturne Field Mapping (2026-01-29)

Created comprehensive field mapping documentation for Nocturne .NET rewrite.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **README** | `mapping/nocturne/README.md` | 64 lines, index |
| **Models** | `mapping/nocturne/models.md` | 187 lines, 6 models |
| **Connectors** | `mapping/nocturne/connectors.md` | 244 lines, 8 connectors |
| **API Versions** | `mapping/nocturne/api-versions.md` | 207 lines, v1-v4 coverage |

**Key Findings**:
- Full v1/v2/v3 API parity with cgm-remote-monitor
- 8 native connectors (Dexcom, Libre, Glooko, CareLink, MFP, NS, t:connect, Tidepool)
- V4 endpoints are Nocturne-specific (GAP-NOCTURNE-001)
- Rust oref implementation for algorithm calculations

**Gaps Identified**: GAP-CONNECTOR-001, GAP-CONNECTOR-002, GAP-CONNECTOR-003

---

### Duration/utcOffset Unit Impact Analysis (2026-01-29)

Analyzed unit inconsistencies across AID systems for duration and timezone fields.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Impact Analysis** | `docs/10-domain/duration-utcoffset-unit-analysis.md` | 256 lines |
| **Requirements** | REQ-UNIT-001 to REQ-UNIT-004 | 4 new requirements |

**Key Findings**:
- Duration: NS=minutes, Loop=seconds, AAPS=milliseconds (60x/60000x mismatch)
- utcOffset: NS=minutes, AAPS internal=milliseconds
- 4 standardization alternatives evaluated (recommend Option 1 Enhanced)
- AAPS preserves `durationInMilliseconds` for round-trip accuracy

**Gaps Addressed**: GAP-TREAT-002, GAP-TZ-004, GAP-PUMP-003

---

### Ecosystem Open PR Analysis (2026-01-29)

Analyzed open PRs across 6 key repositories for interoperability impact.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **PR Analysis** | `docs/analysis/ecosystem-pr-analysis-2026-01-29.md` | 180 lines |

| Repository | Open PRs | Interop-Relevant | Stale (>6mo) |
|------------|----------|------------------|--------------|
| cgm-remote-monitor | 10 | 4 | 2 |
| Trio | 7 | 3 | 1 |
| AndroidAPS | 10 | 3 | 0 |
| LoopWorkspace | 4 | 2 | 2 |
| oref0 | 10 | 3 | 10 |
| xDrip | 10 | 4 | 3 |

**Key Findings**:
- 51 open PRs across ecosystem, 19 interoperability-relevant
- oref0 in maintenance mode (all 10 PRs stale >6 months)
- Active development in pump drivers (Loop #402, AAPS #4513)
- Timezone fix PR #8405 confirms GAP-TZ-xxx

---

### LSP Integration Proposal (2026-01-29)

Defined 4-phase plan for Language Server Protocol integration.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/lsp-integration-proposal.md` | 358 lines |

**Phases**:
1. Line validation (no LSP, 2 hours)
2. Symbol existence (LSP queries, 1-2 days)
3. Cross-reference analysis (1 week+)
4. Continuous monitoring (ongoing)

**Platform Constraints**: Swift LSP requires macOS for iOS projects.

---

### Broken References Fix (2026-01-29)

Fixed broken code references in active documentation files.

| Metric | Before | After |
|--------|--------|-------|
| Valid refs | 352 (91.2%) | 355 (92.0%) |
| Broken refs | 34 | 31 |

**Fixed**:
- `trio:Preferences.swift` → full path (2 files)
- `aaps:NSClientV3Service.kt` → correct `/services/` path (1 file)

**Remaining**: 31 broken (archive files, intentional examples)

---

### sdqctl vs Custom Python Tools Comparison (2026-01-29)

Analyzed 32 Python tools against sdqctl capabilities.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/tools-comparison-proposal.md` | 140 lines |

**Key Findings**:
- 4 tools to deprecate (workflow orchestration → use sdqctl)
- 3 tools to integrate as sdqctl plugins (hygiene tools)
- 2 tools to evaluate further (ai_advisor, workspace_cli)
- 23 tools to keep (domain-specific)

---

### Hygiene Tooling Suite Verification (2026-01-29)

Verified all three hygiene tools are implemented and working.

| Tool | Lines | Status |
|------|-------|--------|
| `tools/queue_stats.py` | - | ✅ One-line status output |
| `tools/backlog_hygiene.py` | 413 | ✅ Queue validation |
| `tools/doc_chunker.py` | 1164 | ✅ Size checking |

**Design Doc**: `docs/sdqctl-proposals/hygiene-tooling-design.md` (466 lines)

**Finding**: progress.md needs chunking (1060 lines, 2.1x over threshold)

---

### nightscout-roles-gateway Audit (2026-01-29)

Verified comprehensive existing documentation and migrated gaps/requirements to traceability.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Authorization** | `mapping/nightscout-roles-gateway/authorization.md` | 114 lines (existing) |
| **Integration** | `mapping/nightscout-roles-gateway/integration.md` | 107 lines (existing) |
| **Gap Migration** | `traceability/nightscout-api-gaps.md` | GAP-RG-001 added |
| **Requirements** | `traceability/nightscout-api-requirements.md` | REQ-RG-001-004 added |

**Key Findings**:
- Three-mode access control (anonymous, identity-mapped, API secret bypass)
- Kratos/Hydra OAuth integration
- Time-based scheduled policies for schools/clinics
- HIPAA-adjacent audit trail via consent logging
- Not yet integrated into core Nightscout (requires separate deployment)

**Gaps Added**: GAP-RG-001

---

### Large File Analysis (2026-01-29)

Analyzed 53 files over 500 lines for autonomous workflow optimization.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Analysis** | `docs/sdqctl-proposals/large-file-analysis.md` | 174 lines |

**Key Findings**:
- 53 files over 500 lines, 6 over 1000 lines
- Largest: terminology-matrix.md (3024 lines)
- Traceability already properly chunked (7 domain files)
- Deep dives appropriately sized (single topic each)
- No immediate chunking needed

**Recommendation**: Add TOC to terminology-matrix.md (P3)

---

### Reporting Needs Analysis (2026-01-29)

Comparison of nightscout-reporter vs cgm-remote-monitor built-in reports.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Analysis** | `docs/10-domain/reporting-needs-analysis.md` | 250 lines |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-REPORT-001-003 |

**Key Findings**:
- cgm-remote-monitor: 11 report plugins (4,738 lines), HTML only
- nightscout-reporter: 17 print forms (15,000+ lines), PDF export
- Both compute statistics client-side (duplication)
- nightscout-reporter has superior PDF generation and multi-language

**Gaps Identified**:
| Gap ID | Issue |
|--------|-------|
| GAP-REPORT-001 | No server-side statistics API |
| GAP-REPORT-002 | No PDF export in cgm-remote-monitor |
| GAP-REPORT-003 | Loop analysis fragmented |

---

### CGM Sensor Session Handling Comparison (2026-01-29)

Cross-system analysis of sensor session start/stop and calibration patterns.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/cgm-session-handling-comparison.md` | 353 lines |
| **Gaps Added** | `traceability/cgm-sources-gaps.md` | GAP-SESSION-001-003 |

**Key Findings**:
- xDrip+ uses database entity model with pluggable calibration algorithms
- Loop uses BLE message protocol with 17-state calibration machine
- AAPS delegates session management to CGM source apps
- Only xDrip+ uploads sensor lifecycle events to Nightscout

**Gaps Identified**:
| Gap ID | Issue |
|--------|-------|
| GAP-SESSION-001 | Session events not standardized |
| GAP-SESSION-002 | Calibration state not exposed |
| GAP-SESSION-003 | Pluggable calibration unique to xDrip+ |

---

### Documentation Reorganization Proposal (2026-01-29)

Analyzed documentation structure for AI and human comprehension optimization.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/documentation-reorganization-proposal.md` | 223 lines |


> **Archive**: More 2026-01-29 entries moved to [progress-archive-2026-01-29-batch2.md](docs/archive/progress-archive-2026-01-29-batch2.md)

- Loop: Full (push notifications)

> **Archive**: Earlier 2026-01-29 entries (Statistics API through Algorithm Conformance runners) moved to [progress-archive-2026-01-29-batch1.md](docs/archive/progress-archive-2026-01-29-batch1.md)

### Algorithm Conformance Suite Proposal (2026-01-29)

Proposal for cross-project AID algorithm testing infrastructure.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/algorithm-conformance-suite.md` | 400+ lines, test vector schema, 5-phase plan |
| **Gaps** | `traceability/gaps.md` | GAP-ALG-001/002/003 added |

**Key Findings**:
- oref0: Mocha tests with inline fixtures, ~40 test scenarios
- AAPS: ReplayApsResultsTest with 50+ JSON fixtures, compares JS vs Kotlin
- Loop: XCTest with scattered fixtures in LoopKitTests/Fixtures/
- No cross-project test vectors exist today

**Proposed Architecture**:
1. Unified test vector JSON schema (`conformance-vector-v1.json`)
2. Category-based vectors: basal-adjustment, smb-delivery, safety-limits, etc.
3. Language-specific runners: oref0-runner.js, aaps-runner.kt, loop-runner.swift
4. Cross-language comparison matrix and gap documentation

**Recommendations**:
1. Extract 50+ vectors from AAPS replay test fixtures (ready-made)
2. Create oref0-runner.js as baseline validator
3. Define semantic equivalence for Loop vs oref comparison

---

### share2nightscout-bridge PR Analysis (2026-01-29)

Analyzed open PRs, issues, and WIP branches for ecosystem impact.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **PR Analysis** | `docs/10-domain/share2nightscout-bridge-pr-analysis.md` | 242 lines, 1 PR, 13 issues |
| **Gaps** | `traceability/gaps.md` | GAP-BRIDGE-001/002/003 added |

**Key Findings**:
- PR #59: Security fix for error handling - **merge immediately**
- Issue #61: Node 16+ EOL blocks cgm-remote-monitor upgrade
- Issue #52: Trend string bug already fixed, close issue
- WIP branch `wip/bewest/axios` nearly complete - finish and merge

**Recommendations**:
1. Merge PR #59 (security)
2. Complete axios migration to resolve Node EOL
3. Close stale 2015-era meta issues

---

> **Archive**: Earlier 2026-01-29 entries moved to [progress-archive-2026-01-29-batch3.md](docs/archive/progress-archive-2026-01-29-batch3.md)

---

### LIVE-BACKLOG Hygiene Cycle (2026-01-29)


Processed 3 pending human requests from LIVE-BACKLOG.

| Request | Action | Result |
|---------|--------|--------|
| Fix backlog checkbox format | Audited all backlogs | tooling.md fixed (hygiene suite → completed) |
| Reevaluate sdqctl-proposals | Audited 14 proposals | 2 already in queue, 3 new items identified |
| Chunk docs accuracy review | Queued to documentation | Added systematic review item |

#### Format Issues Fixed

| File | Issue | Fix |
|------|-------|-----|
| `backlogs/tooling.md` | Hygiene suite still in Active | Moved to Completed table |

#### Proposals Audit Summary

| Status | Count | Examples |
|--------|-------|----------|
| Ready for implementation | 2 | playwright-adoption, algorithm-conformance |
| Needs upstream review | 3 | statistics-api, HELP-INLINE, RUN-BRANCHING |
| Research/Draft | 4 | nocturne-modernization, STPA, nightscout-connect |
| Complete | 5 | hygiene-tooling, tools-comparison, etc. |


---

### Sync Requirements Traceability (2026-01-29)

Added detailed requirements REQ-030 through REQ-035 with scenarios and source references.

| Requirement | Title | Scenarios | Gap Refs |
|-------------|-------|-----------|----------|
| REQ-030 | Sync Identity Preservation | 3 | - |
| REQ-031 | Self-Entry Exclusion | 3 | - |
| REQ-032 | Incremental Sync Support | 3 | GAP-API-003 |
| REQ-033 | Server Deduplication | 3 | GAP-SYNC-009 |
| REQ-034 | Cross-Controller Coexistence | 3 | GAP-SYNC-008 |
| REQ-035 | Conflict Detection | 3 | GAP-SYNC-008, REQ-NS-028 |

**Source Files Referenced**:
- `mapping/cross-project/aid-controller-sync-patterns.md`
- `mapping/trio/carb-math.md`
- `mapping/cgm-remote-monitor/api-versions.md`
- `mapping/cgm-remote-monitor/deduplication.md`
- `docs/10-domain/authority-model.md`

**Requirements Total**: 126 (+6)


### sdqctl VERIFY Directive Enhancement (2026-01-29)

Enhanced proposal with real-world usage patterns from 31-item verification.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Proposal Enhancement | `docs/sdqctl-proposals/VERIFICATION-DIRECTIVES.md` | +171 lines |

**Key Additions**:
- 5 real-world usage patterns from verification experience
- Lessons learned from 31-item verification (91% refs valid)
- Implementation priority (P1/P2/P3) for sdqctl team
- Clear request: parser support for VERIFY directive in .conv

**Status**: Phase 1 (CLI) complete, Phase 2 (directives) pending sdqctl core changes

### CGM Trend Arrow Standardization (2026-01-29)

Mapped trend arrow representations across 7 major projects.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Standardization doc | `docs/10-domain/cgm-trend-arrow-standardization.md` | 9.6KB |
| Terminology update | `mapping/cross-project/terminology-matrix.md` | +16 lines |
| Gap additions | `traceability/cgm-sources-gaps.md` | GAP-CGM-033/034 |

**Key Findings**:
- Nightscout DIRECTIONS is canonical (IDs 0-9)
- xDrip+, Loop, Trio: 1:1 compatible
- AAPS: Has TRIPLE_UP/DOWN not in Nightscout
- DiaBLE/Libre: Only 6 levels vs Dexcom's 9

**Gaps Identified**: GAP-CGM-033 (AAPS triple arrows), GAP-CGM-034 (Libre granularity)

**Source Files Analyzed**:
- `externals/cgm-remote-monitor/lib/server/pebble.js:8-19`
- `externals/xDrip/app/.../Dex_Constants.java:86-96`
- `externals/LoopWorkspace/LoopKit/.../GlucoseTrend.swift:12-37`
- `externals/AndroidAPS/core/data/.../TrendArrow.kt:3-14`
- `externals/DiaBLE/DiaBLE/App.swift:94-112`
- `externals/xdripswift/.../BgReading+CoreDataClass.swift:64-81`

### API v3 Pagination Compliance (2026-01-29)

Analyzed srvModified-based pagination across 4 major clients.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Compliance doc | `docs/10-domain/api-v3-pagination-compliance.md` | 9.3KB |
| Gap additions | `traceability/nightscout-api-gaps.md` | GAP-API-010/011/012 |

**Key Findings**:
- AAPS: Only client with full API v3 support
- Loop/Trio: Use API v1, no incremental sync
- xDrip+: Partial (Last-Modified header with v1)
- Server: srvModified-based /history endpoint documented

**Gaps Identified**: GAP-API-010 (Loop), GAP-API-011 (Trio), GAP-API-012 (xDrip+)

**Source Files Analyzed**:
- `externals/cgm-remote-monitor/lib/api3/generic/history/operation.js`
- `externals/AndroidAPS/plugins/sync/.../LoadBgWorker.kt`
- `externals/Trio/.../NightscoutAPI.swift:14-18`
- `externals/xDrip/.../NightscoutUploader.java:410-437`

### Sync Identity Field Audit (2026-01-29)

Audited sync identity fields across 5 systems.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Audit doc | `docs/10-domain/sync-identity-field-audit.md` | 9.6KB |
| Gap additions | `traceability/sync-identity-gaps.md` | GAP-SYNC-023/024/025 |

**Key Findings**:
- Nightscout: UUID v5 from device+date+eventType
- Loop/Trio: syncIdentifier cached locally, NOT sent to NS
- AAPS: Best practice - stores nightscoutId after sync
- xDrip+: uuid column but not sent as identifier

**Gaps Identified**: GAP-SYNC-023 (Loop/Trio), GAP-SYNC-024 (xDrip+), GAP-SYNC-025 (no standard)

**Source Files Analyzed**:
- `externals/cgm-remote-monitor/lib/api3/shared/operationTools.js:97-107`
- `externals/LoopWorkspace/.../ObjectIdCache.swift:56-58`
- `externals/AndroidAPS/.../IDs.kt:1-17`
- `externals/xDrip/.../Treatments.java:95-96`

### Nightscout Devicestatus Schema Audit (2026-01-29)

Audited devicestatus schema differences between Loop and oref0 systems.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Audit doc | `docs/10-domain/nightscout-devicestatus-schema-audit.md` | 9.2KB |
| Gap additions | `traceability/nightscout-api-gaps.md` | GAP-DS-001/002/003/004 |

**Key Findings**:
- Loop: Single `predicted.values` array in `status.loop`
- oref0: Four curves (IOB/COB/UAM/ZT) in `status.openaps.suggested.predBGs`
- Loop missing: eventualBG, basaliob/bolusiob split
- oref0 missing: override status field
- Nightscout handles both via conditional parsing

**Gaps Identified**: GAP-DS-001 (prediction format), GAP-DS-002 (IOB split), GAP-DS-003 (override), GAP-DS-004 (eventualBG)

**Source Files Analyzed**:
- `externals/cgm-remote-monitor/lib/plugins/loop.js:97-145`
- `externals/cgm-remote-monitor/lib/plugins/openaps.js:214-238`
- `externals/LoopWorkspace/.../StoredDosingDecision.swift:145-161`
- `externals/AndroidAPS/.../NSDeviceStatus.kt:13-60`

### Profile Schema Alignment (2026-01-29)

Analyzed profile/therapy settings schemas across Loop, AAPS, Trio, and Nightscout.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep dive | `docs/10-domain/profile-schema-alignment.md` | 11.6KB |
| Gap additions | `traceability/aid-algorithms-gaps.md` | GAP-PROF-001-005 |
| Requirements | `traceability/aid-algorithms-requirements.md` | REQ-PROF-001-004 |

**Key Findings**:
- Time format mismatch: NS "HH:MM" vs Loop/AAPS seconds-from-midnight
- Loop has safety limits (maxBasal, suspendThreshold) not in Nightscout
- AAPS has profile switching (percentage, timeshift) not in Loop
- DIA scalar vs insulin model preset incompatibility

**Gaps Identified**: GAP-PROF-001 (time format), GAP-PROF-002 (safety limits), GAP-PROF-003 (overrides), GAP-PROF-004 (switching), GAP-PROF-005 (DIA model)

**Source Files Analyzed**:
- `externals/cgm-remote-monitor/lib/profile/profileeditor.js:30-70`
- `externals/LoopWorkspace/LoopKit/LoopKit/TherapySettings.swift:11-69`
- `externals/AndroidAPS/core/interfaces/profile/Profile.kt:14-133`
- `externals/AndroidAPS/core/interfaces/profile/PureProfile.kt:9-18`

### Bolus Wizard Formula Comparison (2026-01-29)

Compared bolus calculation formulas across AAPS, Loop, and Trio.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep dive | `docs/10-domain/bolus-wizard-formula-comparison.md` | 10.4KB |
| Gap additions | `traceability/aid-algorithms-gaps.md` | GAP-BOLUS-001-004 |
| Requirements | `traceability/aid-algorithms-requirements.md` | REQ-BOLUS-001-003 |

**Key Findings**:
- AAPS: Traditional arithmetic formula (BG - target) / ISF
- Loop: Prediction-based using entire BG curve and insulin effect modeling
- AAPS has SuperBolus, percentage scaling, separate basal/bolus IOB toggles
- Loop has suspend threshold protection, dynamic targets

**Gaps Identified**: GAP-BOLUS-001 (formula approach), GAP-BOLUS-002 (IOB handling), GAP-BOLUS-003 (SuperBolus), GAP-BOLUS-004 (trend correction)

**Source Files Analyzed**:
- `externals/AndroidAPS/core/objects/wizard/BolusWizard.kt:154-284`
- `externals/LoopWorkspace/LoopKit/LoopAlgorithm/DoseMath.swift:540-575`

### Autosens/Dynamic ISF Comparison (2026-01-29)

Compared sensitivity adjustment algorithms across oref0, AAPS, and Loop.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep dive | `docs/10-domain/autosens-dynamic-isf-comparison.md` | 9.4KB |
| Gap additions | `traceability/aid-algorithms-gaps.md` | GAP-SENS-001-004 |
| Requirements | `traceability/aid-algorithms-requirements.md` | REQ-SENS-001-003 |

**Key Findings**:
- Autosens: Ratio multiplier (0.7-1.3) over 8-24h window
- Loop Standard RC: Proportional controller over 30min
- Loop Integral RC: PID controller over 180min with memory
- Output differs: ratio vs glucose effect

**Gaps Identified**: GAP-SENS-001 (output format), GAP-SENS-002 (window mismatch), GAP-SENS-003 (no Loop Autosens), GAP-SENS-004 (Dynamic ISF)

**Source Files Analyzed**:
- `externals/oref0/lib/determine-basal/autosens.js:11-200`
- `externals/AndroidAPS/plugins/sensitivity/SensitivityOref1Plugin.kt:57-207`
- `externals/LoopWorkspace/.../StandardRetrospectiveCorrection.swift:17-71`
- `externals/LoopWorkspace/.../IntegralRetrospectiveCorrection.swift:18-75`

### Carb Absorption Model Comparison (2026-01-30)

Compared carb absorption algorithms across Loop and oref0/AAPS.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep dive | `docs/10-domain/carb-absorption-model-comparison.md` | 9.8KB |
| Gap additions | `traceability/aid-algorithms-gaps.md` | GAP-CARB-001-004 |
| Requirements | `traceability/aid-algorithms-requirements.md` | REQ-CARB-001-003 |

**Key Findings**:
- Loop: Model-based (parabolic/piecewise curves), observedProgress tracking
- oref0/AAPS: Deviation-based with min_5m_carbimpact floor, UAM detection
- Max duration differs: Loop 10h vs oref0 6h
- Loop has no UAM equivalent; requires explicit carb entry

**Gaps Identified**: GAP-CARB-001 (model incompatibility), GAP-CARB-002 (no min_5m_carbimpact in Loop), GAP-CARB-003 (no UAM in Loop), GAP-CARB-004 (duration mismatch)

**Source Files Analyzed**:
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/CarbMath.swift:1-200`
- `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/AbsorbedCarbValue.swift:1-80`
- `externals/oref0/lib/determine-basal/cob.js:1-200`
- `externals/oref0/lib/determine-basal/determine-basal.js:500-660`
- `externals/AndroidAPS/core/interfaces/src/main/kotlin/app/aaps/core/interfaces/aps/AutosensData.kt`

### Prediction Curve Documentation (2026-01-30)

Documented prediction curve generation across Loop and oref0/AAPS.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep dive | `docs/10-domain/prediction-curve-documentation.md` | 11.7KB |
| Gap additions | `traceability/aid-algorithms-gaps.md` | GAP-PRED-001-004 |
| Requirements | `traceability/aid-algorithms-requirements.md` | REQ-PRED-001-003 |

**Key Findings**:
- Loop: Single combined prediction from summed effects
- oref0: 4 separate curves (IOB, COB, UAM, ZT) for different scenarios
- ZT curve unique to oref0 - shows "pump suspended" scenario
- Nightscout selects COB > UAM > IOB priority for display

**Gaps Identified**: GAP-PRED-001 (structure incompatibility), GAP-PRED-002 (no ZT in Loop), GAP-PRED-003 (momentum difference), GAP-PRED-004 (NS curve selection)

**Source Files Analyzed**:
- `externals/LoopWorkspace/LoopKit/LoopKit/LoopAlgorithm/LoopAlgorithm.swift:74-188`
- `externals/oref0/lib/determine-basal/determine-basal.js:442-720`
- `externals/cgm-remote-monitor/lib/report_plugins/daytoday.js:347-360`
