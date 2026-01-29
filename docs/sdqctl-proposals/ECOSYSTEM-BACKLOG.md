# Ecosystem Alignment Backlog

> **Last Updated**: 2026-01-29  
> **Purpose**: Track active work items across all domains  
> **Archive**: Completed work → [`archive/`](archive/)

## Domain Backlogs

| Domain | File | Description |
|--------|------|-------------|
| CGM Sources | [backlogs/cgm-sources.md](backlogs/cgm-sources.md) | xDrip+, DiaBLE, Dexcom, Libre protocols |
| AID Algorithms | [backlogs/aid-algorithms.md](backlogs/aid-algorithms.md) | Loop, AAPS, Trio, oref0 comparison |
| Nightscout API | [backlogs/nightscout-api.md](backlogs/nightscout-api.md) | Collections, auth, API v3 |
| Sync & Identity | [backlogs/sync-identity.md](backlogs/sync-identity.md) | Deduplication, timestamps, sync IDs |
| Tooling | [backlogs/tooling.md](backlogs/tooling.md) | sdqctl enhancements, plugins, automation |
| **Documentation Accuracy** | [backlogs/documentation-accuracy.md](backlogs/documentation-accuracy.md) | Bottom-up claim verification |
| Live requests | [../../LIVE-BACKLOG.md](../../LIVE-BACKLOG.md) | Midflight human requests |

---

## Ready Queue (5-10 items)

Items ready for immediate work. Keep 5-10 visible for horizontal work across domains.

### 1. [P2] Algorithm conformance: AAPS Kotlin runner
**Type:** Implementation | **Effort:** High
**Repos:** AndroidAPS
**Focus:** Phase 3 of conformance suite - Kotlin runner for AAPS
**Workflow:** `extract-spec.conv`
**Note:** Follow-on from oref0 runner (complete)

### 2. [P2] Libre 3 protocol gap analysis
**Type:** Analysis | **Effort:** High
**Repos:** DiaBLE, xDrip+, xdripswift
**Focus:** Document "eavesdrop only" limitations for Libre 3
**Source:** CGM sources backlog

### 3. [P2] Cross-controller conflict detection
**Type:** Analysis | **Effort:** Medium
**Focus:** Document actual behavior when Loop+Trio sync to same Nightscout
**Source:** Sync & Identity backlog

### 4. [P2] Level 5: Requirements traceability - REQ-SYNC-*
**Type:** Verification | **Effort:** Medium
**Source:** [documentation-accuracy.md](backlogs/documentation-accuracy.md) #24
**Focus:** Audit REQ-SYNC-* coverage by test scenarios
**Method:** Run `python tools/verify_assertions.py`

### 5. [P3] Algorithm conformance: Loop Swift runner
**Type:** Implementation | **Effort:** High
**Repos:** LoopWorkspace
**Focus:** Swift-based runner for Loop algorithm testing
**Workflow:** `extract-spec.conv`
**Note:** Required for Loop conformance per GAP-ALG-013

### 6. [P3] sdqctl VERIFY .conv Directive (Phase 2)
**Type:** Tooling | **Effort:** Medium
**Proposal:** [VERIFICATION-DIRECTIVES.md](VERIFICATION-DIRECTIVES.md)
**Focus:** Native `VERIFY refs` directive in .conv workflows
**Context:** CLI commands already exist (`sdqctl verify refs`), Phase 2 adds directive support

---

## Completed Items

### ~~[P2] Level 4: GAP-CONNECT-* verification~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 - **LEVEL 4 COMPLETE!**
- 8 claims verified: **100% accurate**
- GAP-CONNECT-001/004: nightscout-connect v1 only, no test suite
- GAP-TCONNECT/SHARE/LIBRELINK: All v1 API only
- GAP-SHARE-003: Hardcoded Dexcom app ID confirmed
- GAP-LOOPFOLLOW/LOOPCAREGIVER-001: v1 only, Loop-only

### ~~[P2] Level 4: GAP-TREAT-* verification~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 11 claims verified: **100% accurate**
- GAP-OVERRIDE-001/002: Loop vs AAPS model, percentage inversion
- GAP-OVERRIDE-004/005/007: Trio settings lost, uses Exercise eventType
- GAP-REMOTE-001/008: Override OTP not required, no server bolus limits
- GAP-TREAT-001/003/005: Absorption units, SMB type field, POST duplicates

### ~~[P2] Level 4: GAP-SYNC-* verification~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 9 claims verified: **100% accurate**
- GAP-SYNC-001/005/006: Loop POST-only, ObjectIdCache 24h expiry, v1 API only
- GAP-SYNC-007: syncIdentifier format varies (no validation)
- GAP-TZ-002/005/006/007: Medtrum workaround, AAPS fixed offset, Nightscout bugs

### ~~[P2] Level 4: GAP-API-* verification~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 6 claims verified: **100% accurate**
- GAP-API-001: v1 cannot detect deletions (v3 has isValid=false)
- GAP-API-002: `_id` vs `identifier` fallback confirmed
- GAP-API-003: No v3 for iOS (AAPS has NSClientV3Plugin, Loop has none)
- GAP-API-004/005: Auth and dedup differences verified

### ~~[P2] Level 4: GAP-ALG-* verification~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 7 claims verified: **100% accurate**
- GAP-ALG-001: oref0 runner exists, 85 AAPS vectors confirmed
- GAP-ALG-002: 30.6% pass rate (69.4% divergence) verified
- GAP-ALG-003: oref0 4 curves vs Loop single curve confirmed
- GAP-CARB-001: Still open

### ~~[P3] Level 3: Pump communication deep dive~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 8 claims verified: **100% accurate**
- Omnipod Eros: 433.91 MHz RF (PodComms.swift:560)
- Medtronic: 916.5/868 MHz (PumpOpsSession.swift:795,797)
- Loop PumpManager: enactBolus, enactTempBasal (PumpManager.swift:170,186)
- AAPS Pump: interface at Pump.kt:19

### ~~[P2] Level 3: Libre protocol deep dive~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 7 claims verified: **100% accurate**
- Libre 1: NFC unencrypted (Libre.swift:91-93)
- Libre 2: Encrypted FRAM + BLE (Libre.swift:86,93, OOP.swift:390)
- Libre 3: ECDH + AES-CCM (Libre3.swift:1011-1012, Crypto.swift:11-19)
- PatchInfo bytes: 0xDF→libre1, 0x9D→libre2 (Libre.swift:11-18)
- NFC 0xA1, IC Manufacturer 0x07/0x7a, 60 min warmup

### ~~[P2] Level 3: Treatments deep dive~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 8 claims verified: **100% accurate**
- Loop: `deliveredUnits`, `syncIdentifier`, `automatic` boolean
- AAPS: `amount`, Bolus.Type enum, `interfaceIDs.nightscoutId`
- xDrip+: `uuid` for sync identity
- SMB: AAPS → eventType "Correction Bolus"

### ~~[P2] Level 3: Entries deep dive~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 8 claims verified: **100% accurate**
- xDrip+: `calculated_value`, `dg_slope` for trend
- Loop: `HKQuantity`, `provenanceIdentifier`, `GlucoseTrend`
- AAPS: `value` field, `trendArrow` enum
- Nightscout: sgv/mbg/cal entry types

### ~~[P2] Level 3: DeviceStatus deep dive~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 8 claims verified: **100% accurate**
- Loop: `loop` top-level, `loop://` device format, overrideStatus field
- Trio: `openaps` top-level, device = "Trio"
- AAPS: `openaps` top-level, `openaps://` device format
- oref0: predBGs with IOB/COB/UAM/ZT arrays

### ~~[P2] Level 3: CGM data sources deep dive~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 8 claims verified: **100% accurate**
- xDrip+: 26 data source types, Ob1 collector, NSFollow/SHFollow
- Loop: CGMBLEKit, G7SensorKit verified
- xDrip4iOS: Dexcom, Libre, Generic CGM types
- LibreLinkUp: /llu/connections endpoint confirmed

### ~~[P2] Level 3: Algorithm comparison deep dive~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 7 claims verified: **100% accurate**
- oref0: 4 prediction arrays, SMB, Autosens verified
- AAPS: Dynamic ISF (TDD-based) verified
- Loop: Retrospective Correction, Automatic Bolus verified
- Trio: JavaScript calls verified

### ~~[P2] Level 2: Terminology matrix sampling~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 15 terms sampled across 6 repos: **100% accurate**
- HeartRate fields, TrendArrow enum, oref0 prediction arrays verified
- **Level 2 Complete**: 5/5 mapping verifications passed

### ~~[P2] Accuracy: Verify Loop + Trio mappings~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- `mapping/loop/sync-identity-fields.md`: **100% accurate**
- `mapping/trio/nightscout-sync.md`: **100% accurate**
- Source files verified: DoseEntry.swift, ObjectIdCache.swift, NightscoutAPI.swift, NightscoutStatus.swift

### ~~[P2] Accuracy: Verify xDrip + AAPS mappings~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- `mapping/xdrip-android/nightscout-sync.md`: **100% accurate**
- `mapping/aaps/nsclient-schema.md`: **100% accurate**
- Source files verified: UploaderQueue.java, NightscoutUploader.java, RemoteTreatment.kt, RemoteEntry.kt, EventType.kt

### ~~[P2] Accuracy: Verify G7 protocol claims~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- G7 protocol specification: **100% accurate**
- All opcodes, UUIDs, curves verified against DiaBLE, xDrip sources
- GAP-BLE-001/002 confirmed still open

### ~~[P2] Playwright E2E PR Submission~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Created `conformance/e2e-nightscout/PR-SUBMISSION.md` (4.6 KB)
- Package ready with 18 tests (10 API, 8 Dashboard)
- Includes PR template, submission steps, CI guidance

### ~~[P2] sdqctl VERIFY Directive Implementation~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Discovered `sdqctl verify` CLI already implemented
- Added `make sdqctl-verify-refs` and `make sdqctl-verify-all` targets
- Updated VERIFICATION-DIRECTIVES.md status to IMPLEMENTED
- Phase 2 (.conv directive) remains as separate item

### ~~[P2] Conformance Test Executor Integration~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Added `make conformance-algorithms` and `make conformance-ci` targets
- Added `algorithm-conformance` job to `.github/workflows/ci.yml`
- Created `conformance/README.md` (148 lines)
- CI uploads results as artifact, uses `continue-on-error` for known divergence

### ~~[P3] Deep dive: xdrip-js Node.js CGM interface~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Created `docs/10-domain/xdrip-js-deep-dive.md` (380 lines)
- 4 gaps identified: GAP-XDRIPJS-001 to 004
- Key findings: No G7 support, deprecated noble BLE library
- Total gaps: 216 → 220

### ~~[P2] Connectors Requirements Generation~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Created `traceability/connectors-requirements.md` with 28 requirements
- 8 REQ prefixes: CONNECT, NOCTURNE, TCONNECT, TEST, SHARE, LIBRELINK, LOOPFOLLOW, LOOPCAREGIVER
- Total requirements: 157 → 185 (180 unique)
- 100% gap-to-REQ coverage for connectors domain

### ~~[P1] Assertion-to-Requirement Linkage Audit~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Linked 23 orphaned assertions to requirements
- Created 27 new REQs (REQ-SYNC-036 to 050, REQ-OVERRIDE-001 to 005, REQ-TREAT-040 to 046)
- Requirement coverage: 0% → 17.4%
- Fixed verify_assertions.py to scan all traceability files

### ~~[P2] Playwright adoption: Implementation~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (591 lines, 4 files)
- playwright.config.js: Multi-browser configuration
- dashboard.spec.js: 8 E2E scenarios
- api.spec.js: 9 API smoke tests
- README.md: Setup instructions and CI integration

### ~~[P3] Semantic equivalence for Loop~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (400 lines, 4 gaps GAP-ALG-013 to 016)
- Direct output comparison NOT feasible (different prediction models)
- Loop needs Swift-based conformance runner
- oref0 vectors cannot be reused (missing raw dose history)

### ~~5. [P2] DiaBLE Libre protocol audit~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (487 lines deep dive, 2 new gaps, GAP-DIABLE-002/003)

### ~~5. [P3] Create mapping: share2nightscout-bridge~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (424 lines, 3 docs, 3 gaps)

### ~~5. [P3] Create mapping: nightscout-librelink-up~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (608 lines, 3 docs, 3 gaps)

### ~~5. [P3] Deep dive: LoopFollow~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (411 lines, 3 gaps)

### ~~5. [P3] Deep dive: LoopCaregiver~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (417 lines, 3 gaps)

### ~~5. [P3] Deep dive: openaps toolkit~~ ✅ COMPLETE
**Status:** Pre-existing documentation covers this (371 lines deep dive at `docs/10-domain/openaps-oref0-deep-dive.md`, 3 gaps)

### ~~6. [P3] Compare CGM sensor session handling~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (407 lines, 4 gaps GAP-SESSION-001 to 004)

### ~~7. [P3] Extract xDrip+ Nightscout fields~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (370 lines, 2 docs, 3 gaps GAP-XDRIP-001 to 003)

### ~~8. [P3] Map algorithm terminology~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (+95 lines terminology, ISF/CR/DIA/UAM/SMB/Autosens mapped)

### ~~9. [P3] Document AAPS vs oref0 divergence~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 (280 lines, 4 gaps GAP-ALG-009 to 012)
- Core oref0 (OpenAPSSMBPlugin): 94% pass rate - effectively identical
- DynamicISF: 18% pass rate - AAPS-specific TDD-based ISF
- AutoISF: 5% pass rate - AAPS-specific sigmoid-adjusted ISF

---

## Backlog (Prioritized)

### P0 - Critical

*All P0 items complete. See Completed (Recent) table.*

### P1 - High Value

*All P1 items complete. See Completed (Recent) table.*

### P2 - Normal

*All P2 items complete. See Completed (Recent) table.*

### P3 - Nice to Have

- [x] ~~**Deep dive: xdrip-js**~~ - ✅ Complete (380 lines, 4 gaps GAP-XDRIPJS-001..004)
  - Repos: xdrip-js
  - Focus: Node.js Dexcom G5/G6 BLE interface
  - Context: Raspberry Pi CGM receiver use case
  - Workflow: `extract-spec.conv`

*Completed P3 items moved to Completed (Recent) table below.*

---

## Completed (Recent)

*Older items archived to [`archive/2026-01-backlog-archive.md`](archive/2026-01-backlog-archive.md)*

| Date | Item | Outcome |
|------|------|---------|
| 2026-01-29 | **Accuracy: G7 protocol verification** | 100% accurate, GAP-BLE-001/002 confirmed |
| 2026-01-29 | **Accuracy: Source refs verification** | 91% valid (356/391), active docs 100% |
| 2026-01-29 | Deep dive: xdrip-js | 380 lines, 4 gaps |
| 2026-01-29 | Hygiene: Chunk progress.md | 1713→807 lines, archive created |
| 2026-01-29 | Algorithm conformance: oref0 runner | `oref0-runner.js` - 400+ lines, 26/85 pass |
| 2026-01-29 | Algorithm conformance: Schema + fixture extraction | 85 vectors, schema, extraction script |
| 2026-01-29 | Heart Rate API specification | `aid-heartrate-2025.yaml` - 447 lines |
| 2026-01-29 | Statistics API proposal | 480 lines, 3 gaps, 5 reqs |
| 2026-01-29 | PR analysis: cgm-remote-monitor | 380 lines, 68 PRs |
| 2026-01-29 | Interoperability Spec v1 | RFC-style, synthesizes 6 audits |
| 2026-01-29 | cgm-remote-monitor 6-layer audit | 2,751 lines total, 18 gaps |
| 2026-01-29 | Cross-project testing plan | 4 strategies for Swift on Linux |
| 2026-01-29 | Playwright adoption (proposal + implementation) | 591 lines, 18 tests, PR ready |

---

## Queue Discipline

1. **Ready Queue**: 5-10 actionable items (visibility for horizontal work)
2. **New discoveries**: Add to appropriate priority level in Backlog
3. **Blocked items**: Move to docs/OPEN-QUESTIONS.md with blocker
4. **Completed items**: Move to Completed table with outcome summary
5. **After each workflow**: Replenish Ready Queue from Backlog

---

## Related Documents

- [traceability/gaps.md](../../traceability/gaps.md) - Identified gaps
- [traceability/requirements.md](../../traceability/requirements.md) - Extracted requirements
- [docs/OPEN-QUESTIONS.md](../OPEN-QUESTIONS.md) - Open questions and blocked items
- [progress.md](../../progress.md) - Completion log

---

## How to Use

### Run from Ready Queue

```bash
# Comparison tasks
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: remote bolus. Repos: Loop, AAPS, Trio"

# Gap discovery
sdqctl iterate workflows/analysis/gap-discovery.conv \
  --prologue "Repo: cgm-remote-monitor. Focus: API v3"

# Full backlog cycle (selects task automatically)
sdqctl iterate workflows/orchestration/backlog-cycle.conv
```

### Verification

```bash
sdqctl verify plugin ref-integrity
sdqctl verify plugin ecosystem-gaps
``` |
