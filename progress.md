# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Entries before 2026-01-30 moved to [progress-archive-2026-01-30-batch1.md](docs/archive/progress-archive-2026-01-30-batch1.md)

---

## Completed Work

### Efficiency Dashboard Tool (2026-01-30)

Created `tools/efficiency_dashboard.py` to track productivity metrics.

| Metric | Value |
|--------|-------|
| Tool created | `tools/efficiency_dashboard.py` |
| Makefile target | `make efficiency-dashboard` |
| Default range | Last 7 days |
| Sections | Overall, Tools, Types, Daily, Recent |

**Features**:
- Parse git log for commits with stats
- Calculate lines/commit, files/commit averages
- Categorize by conventional commit types
- Daily activity breakdown
- JSON output for CI integration

---

### Mapping Coverage Tool (2026-01-30)

Created `tools/verify_mapping_coverage.py` to verify mapping docs cover source fields.

| Metric | Value |
|--------|-------|
| Tool created | `tools/verify_mapping_coverage.py` |
| Makefile target | `make verify-mapping-coverage` |
| Mapping files found | 93 |
| Default sample | 5 files |
| Coverage thresholds | GOOD ≥80%, REVIEW 50-79%, LOW <50% |

**Features**:
- Parse documented fields from backticks and tables
- Map to external repos via REPO_MAPPING dictionary
- Grep-verify each field against source code
- JSON output for CI integration

---

### Gap Freshness Checker Tool (2026-01-30)

Created `tools/verify_gap_freshness.py` to check if documented gaps are still open.

| Metric | Value |
|--------|-------|
| Tool created | `tools/verify_gap_freshness.py` |
| Makefile target | `make verify-gap-freshness` |
| GAP definitions parsed | 268 |
| Default sample | 10 gaps |
| Status categories | LIKELY_OPEN, NEEDS_REVIEW, NO_TERMS |

**Features**:
- Check specific gap with `--gap GAP-XXX-NNN`
- Random sampling with reproducible seed
- JSON output for CI integration
- Grep-based verification against externals/
- Extracts search terms from title and code references

---

### Terminology Sample Tool (2026-01-30)

Created `tools/sample_terminology.py` to verify terminology matrix entries against source code.

| Metric | Value |
|--------|-------|
| Tool created | `tools/sample_terminology.py` |
| Makefile target | `make verify-terminology` |
| Terms in matrix | 354 |
| Default sample | 15 terms |
| Accuracy achieved | 90-100% |

**Features**:
- Random sampling with reproducible seed
- JSON output for CI integration
- Grep-based verification against externals/
- Exit code 0 if ≥80% verified

---

### Fix 26 Duplicate GAP Definitions (2026-01-30)

Resolved all duplicate GAP IDs found by `find_gap_duplicates.py`.

| Action | Count |
|--------|-------|
| Removed duplicate sections | 16 |
| Renumbered colliding IDs | 17 |
| Cross-references updated | 11 files |
| Net lines removed | 292 |
| Unique GAP IDs after | 265 |

**ID Renumbering**:
- GAP-AUTH-001/002 (later defs) → GAP-AUTH-006/007
- GAP-DS-001-004 (later defs) → GAP-DS-005-008
- GAP-SESSION-001-003 (later defs) → GAP-SESSION-004-006
- GAP-SYNC-020-028 → GAP-SYNC-029-037

**Removed Duplicates**: CARB-001-004, PRED-001-004, AUTH-003-004, LIBRELINK-001-003, SHARE-001-003

---

### Gap Deduplication Tool (2026-01-30)

Created `tools/find_gap_duplicates.py` to detect duplicate GAP-* definitions.

| Metric | Value |
|--------|-------|
| Tool created | `tools/find_gap_duplicates.py` |
| Makefile target | `make verify-gap-duplicates` |
| Unique GAP IDs | 255 |
| **Duplicates found** | 26 |

**Key Finding**: 26 GAP IDs have duplicate definitions across traceability files. Most are in the same file (e.g., nightscout-api-gaps.md has GAP-AUTH-001 twice with different titles). Needs dedup cleanup.

**Deliverables**:
- `tools/find_gap_duplicates.py` (120 lines)
- Makefile integration

---

### Backlog Consolidation (2026-01-30)

Discovered Ready Queue had stale entries pointing to already-completed work. Consolidated.

| Metric | Value |
|--------|-------|
| Stale items removed | 4 |
| Items already complete | CGM arrows, API v3 pagination, algorithm claims, sync-identity |
| Ready Queue after | 2 (High-effort only) |
| Commit | `f2356bd` |

**Key Finding**: Documentation accuracy verification (Levels 1-6) was 100% complete as of 2026-01-29. Ready Queue needs replenishment from new work sources.

---

### WebSocket Event Coverage (2026-01-30)

Mapped Nightscout Socket.IO events vs REST API for real-time sync.

| Metric | Value |
|--------|-------|
| Source files analyzed | 4 |
| Gaps identified | 3 (GAP-API-013 to GAP-API-015) |
| Requirements extracted | 3 (REQ-API-004 to REQ-API-006) |
| Key finding | APIv3 /storage channel doesn't capture v1 API changes |

**Key Findings**:
- Two WebSocket channels: legacy `/` (bidirectional) and APIv3 `/storage` (read-only)
- Controllers use REST; WebSocket primarily for web interface
- APIv3 storage channel only broadcasts v3 API changes (GAP-API-014)
- No alarm state events exposed via WebSocket

**Deliverables**:
- `docs/10-domain/websocket-event-coverage.md` (10KB)
- `traceability/nightscout-api-gaps.md` (+3 gaps)
- `traceability/nightscout-api-requirements.md` (+3 requirements)

---

### Profile Switch Sync Comparison (2026-01-30)

Analyzed how profile switches sync to Nightscout across AAPS, Loop, and Trio.

| Metric | Value |
|--------|-------|
| Source files analyzed | 9 |
| Gaps identified | 3 (GAP-SYNC-035 to GAP-SYNC-037) |
| Requirements extracted | 3 (REQ-SYNC-051 to REQ-SYNC-053) |
| Key finding | AAPS uses `Profile Switch` treatments; Loop/Trio upload to `profile` collection only |

**Key Findings**:
- AAPS creates `Profile Switch` treatment events with embedded profile JSON
- Loop/Trio upload to `profile` collection without treatment events
- AAPS supports `percentage` and `timeshift` not understood by other systems
- Profile change history not visible in NS timeline for Loop/Trio users

**Deliverables**:
- `docs/10-domain/profile-switch-sync-comparison.md` (11KB)
- `traceability/sync-identity-gaps.md` (+3 gaps)
- `traceability/sync-identity-requirements.md` (+3 requirements)
- `mapping/cross-project/terminology-matrix.md` (updated Profile Switch note)

---

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

