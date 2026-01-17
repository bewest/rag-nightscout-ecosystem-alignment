# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

---

## Completed Work

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

## Candidate Next Cycles

### Priority A: Insulin Activity Curves Comparison

**Value**: Different insulin models affect prediction accuracy and dosing decisions.

**Questions to answer**:
- What insulin activity models does each system use?
- How are DIA (duration of insulin action) settings applied?
- What are the differences between exponential vs bilinear models?

**Deliverables**:
- `docs/10-domain/insulin-curves-deep-dive.md`
- Curve formula comparison

---

### Priority C: Carb Absorption Models Comparison

**Value**: Carb models significantly affect prediction accuracy.

**Questions to answer**:
- Linear vs non-linear absorption models
- How does UAM (Unannounced Meals) detection work?
- Extended carb (eCarb) handling differences

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
