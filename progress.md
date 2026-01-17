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

---

## Candidate Next Cycles

### Priority A: Algorithm Prediction Comparison (Recommended)

**Value**: Explains *why* systems make different dosing decisions with the same data.

**Current state**: Per-system algorithm docs exist (`mapping/loop/algorithm.md`, `mapping/oref0/algorithm.md`, `mapping/aaps/algorithm.md`, `mapping/trio/algorithm.md`), but no cross-system comparison.

**Questions to answer**:
- How do prediction methodologies differ? (Loop's single combined curve vs oref0's 4 curves: IOB, COB, UAM, ZT)
- How do insulin models differ? (exponential decay, DIA handling)
- How do safety guards compare? (low glucose suspend, max IOB, SMB limits)
- Why does the same CGM data produce different recommendations?

**Deliverables**:
- `docs/10-domain/algorithm-comparison-deep-dive.md`
- Update terminology matrix with Algorithm Concepts section
- Identify gaps (GAP-ALG-001+)
- Suggested specs where protocol is clear

**Source files to leverage**:
- `loop:LoopKit/LoopKit/LoopAlgorithm/LoopAlgorithm.swift`
- `oref0:lib/determine-basal/determine-basal.js`
- `aaps:app/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/`
- `trio:Trio/Sources/APS/OpenAPS/`

---

### Priority B: CGM Data Source Architecture

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

### Priority C: Remote Commands Cross-System Comparison

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

### Priority D: Nightscout API v1 vs v3

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
