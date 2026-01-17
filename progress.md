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

## Candidate Next Cycles

### Priority A: CGM Data Source Architecture (Recommended Next)

**Value**: Completes the glucose data story by tracing *upstream*—how data flows from transmitter to Nightscout entries.

**Questions to answer**:
- How do xDrip+'s 20+ data sources work? (collectors, calibration plugins)
- How do Loop/Trio CGMManager plugins work?
- How do follower modes work? (Dexcom Share, LibreLinkUp, Nightscout)
- How do calibrations flow and affect displayed values?
- What role does xDrip+'s local web server (port 17580) play as alternative path?

**Deliverables**:
- `docs/10-domain/cgm-data-sources-deep-dive.md`
- Update terminology matrix with CGM Source Models section
- Identify gaps in data provenance tracking

**Source files to leverage**:
- `xdrip:app/src/main/java/com/eveningoutpost/dexdrip/services/` (collectors)
- `xdrip:app/src/main/java/com/eveningoutpost/dexdrip/calibrations/` (calibration algorithms)
- `loop:LoopKit/CGMBLEKit/` and `ShareClient/`
- `xdrip4ios:xdrip/Managers/CGM/` (transmitter managers)

---

### Priority B: Remote Commands Cross-System Comparison

**Value**: Security-critical—how caregivers remotely control AID systems.

**Current state**: Trio has detailed docs (`mapping/trio/remote-commands.md`), but Loop Caregiver and AAPS NSClient aren't deeply compared.

**Questions to answer**:
- How do security models differ? (Trio AES-256-GCM vs Loop Caregiver vs AAPS NSClient)
- What command types are supported per system?
- How are safety limits enforced remotely?
- How is replay protection implemented?

**Deliverables**:
- `docs/10-domain/remote-commands-comparison.md`
- Security model comparison matrix
- Gap identification for interoperability

**Source files to leverage**:
- `trio:Trio/Sources/Services/RemoteControl/`
- `loop:LoopCaregiver/` (if available)
- `aaps:plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/`

---

### Priority C: Nightscout API v1 vs v3

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
