# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Entries before 2026-01-30 moved to [progress-archive-2026-01-30-batch1.md](docs/archive/progress-archive-2026-01-30-batch1.md)

---

## Completed Work

### Basal Schedule Comparison (2026-01-30)

Compared basal rate schedule handling across Loop, AAPS, Trio, oref0, and Nightscout.

| Metric | Value |
|--------|-------|
| Source files analyzed | 10 |
| Gaps identified | 5 (GAP-PROF-006 to GAP-SYNC-020) |
| Requirements extracted | 3 (REQ-PROF-005 to REQ-PROF-007) |
| Key finding | Time format: "HH:MM" (NS) vs seconds (Loop) vs minutes (oref0) |

**Key Findings**:
- Nightscout uses "HH:MM" strings while all controllers use numeric offsets
- oref0 uses minutes; Loop/Trio/AAPS use seconds from midnight
- Basal rate precision varies: 3 decimal places (oref0) to pump step size (AAPS)
- No standardized event for basal schedule changes

**Deliverables**:
- `docs/10-domain/basal-schedule-comparison.md` (10KB) - Full comparison
- `traceability/aid-algorithms-gaps.md` - 5 new gaps
- `traceability/aid-algorithms-requirements.md` - 3 new requirements
- `mapping/cross-project/terminology-matrix.md` - Basal time format table

---

### sdqctl iterate Effectiveness Analysis (2026-01-30)

Analyzed the effectiveness of a 40-cycle `sdqctl iterate` run.

| Metric | Value |
|--------|-------|
| Run duration | 230 minutes (3.8 hours) |
| Total cost | ~$419 (137M tokens) |
| Commits produced | 49 |
| Lines added | 11,064 |
| ROI multiplier | 14-36x vs manual |

**Key Findings**:
- Cost per commit: $8.55
- Cost per line: $0.038 (~26 lines per dollar)
- Tool success rate: 99.65% (2,014/2,021)
- Quality: Claims verified accurate, 2 duplicate GAPs found

**Deliverables**:
- `docs/sdqctl-proposals/iterate-effectiveness-report.md` (8.1KB)
- 4 new tooling backlog items added

**Recommendations**:
- Implement REFCAT caching (est. 20-40% token reduction)
- Add gap deduplication tool
- Selective repo loading by task keywords

---

### Override/Temporary Target Sync Comparison (2026-01-30)

Compared how Loop overrides and AAPS temp targets sync to Nightscout.

| Metric | Value |
|--------|-------|
| Source files analyzed | 4 |
| Gaps identified | 4 (OVRD-001 to OVRD-004) |
| Key finding | Different eventTypes (Override vs Temporary Target) |

**Key Findings**:
- Loop uses eventType `Override` with `insulinNeedsScaleFactor`
- AAPS uses eventType `Temporary Target` with only target range
- Reason formats differ: Loop free text vs AAPS 6-value enum
- Duration units differ: Loop seconds, AAPS milliseconds
- Both use `duration = 0` for cancellation

**Gaps Added**:
- GAP-OVRD-001: Different eventTypes for target overrides
- GAP-OVRD-002: insulinNeedsScaleFactor not in AAPS
- GAP-OVRD-003: Reason enum vs free text
- GAP-OVRD-004: Duration units differ

**Requirements Added**:
- REQ-OVRD-001: eventType documentation
- REQ-OVRD-002: Insulin adjustment sync
- REQ-OVRD-003: Duration unit normalization

**Deliverables**:
- `docs/10-domain/override-temp-target-sync-comparison.md` (10.2KB)
- `traceability/sync-identity-gaps.md` (+4 gaps)
- `traceability/sync-identity-requirements.md` (+3 requirements)

---

### Target Range Handling Comparison (2026-01-30)

Compared target glucose range handling across Loop and oref0/AAPS.

| Metric | Value |
|--------|-------|
| Source files analyzed | 4 |
| Gaps identified | 4 (TGT-001 to TGT-004) |
| Key finding | Loop dynamic targeting vs oref0 static midpoint |

**Key Findings**:
- Loop uses **dynamic targeting** (suspend threshold → midpoint over insulin effect)
- oref0 uses **static midpoint**: `target_bg = (min_bg + max_bg) / 2`
- oref0 adjusts targets based on autosens ratio; Loop does not
- oref0 ties SMB enable/disable to temp target value; Loop is independent

**Gaps Added**:
- GAP-TGT-001: Different algorithm targeting behavior
- GAP-TGT-002: Autosens target adjustment not in Loop
- GAP-TGT-003: Temp target sensitivity adjustment
- GAP-TGT-004: SMB enable tied to target in oref0

**Requirements Added**:
- REQ-TGT-001: Target range format documentation
- REQ-TGT-002: Target calculation transparency
- REQ-TGT-003: Temp target side effects documentation

**Deliverables**:
- `docs/10-domain/target-range-handling-comparison.md` (10.7KB)
- `traceability/aid-algorithms-gaps.md` (+4 gaps)
- `traceability/aid-algorithms-requirements.md` (+3 requirements)

---

### Insulin Model Comparison (2026-01-30)

Compared exponential and bilinear insulin activity models across Loop and oref0/AAPS.

| Metric | Value |
|--------|-------|
| Source files analyzed | 2 |
| Gaps identified | 4 (INS-005 to INS-008) |
| Key finding | Formula identical (Loop issue #388) |

**Key Findings**:
- Loop and oref0 use **identical exponential formula** from Loop issue #388
- oref0 also supports legacy bilinear model; Loop is exponential-only
- Loop has explicit delay parameter (10 min default); oref0 bakes delay into peak
- oref0 allows custom peak times (50-120 or 35-100 min); Loop uses fixed presets

**Gaps Added**:
- GAP-INS-005: Bilinear model not in Loop
- GAP-INS-006: Delay parameter handling differs
- GAP-INS-007: Custom peak time UX differs
- GAP-INS-008: Identical exponential formula verified

**Requirements Added**:
- REQ-INS-001: Exponential formula consistency
- REQ-INS-002: DIA range validation
- REQ-INS-003: Peak time documentation

**Deliverables**:
- `docs/10-domain/insulin-model-comparison.md` (8.7KB)
- `traceability/aid-algorithms-gaps.md` (+4 gaps)
- `traceability/aid-algorithms-requirements.md` (+3 requirements)

---

