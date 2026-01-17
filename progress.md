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

## Candidate Next Cycles

### Priority A: Nightscout API v1 vs v3 (Recommended Next)

**Value**: AAPS uses v3 while others use v1—understanding differences explains sync gaps.

**Questions to answer**:
- What are the semantic differences between v1 and v3?
- How do authentication mechanisms differ?
- How does `identifier` field work in v3?
- What migration path exists?

**Deliverables**:
- `docs/10-domain/nightscout-api-comparison.md`
- API endpoint mapping table
- Gap identification for cross-client compatibility

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
