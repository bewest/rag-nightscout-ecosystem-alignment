# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Older entries moved to:
> - [progress-archive-2026-01-30-batch1.md](docs/archive/progress-archive-2026-01-30-batch1.md)
> - [progress-archive-2026-01-30-batch2.md](docs/archive/progress-archive-2026-01-30-batch2.md)

---

## Completed Work

### Extend verify_refs Scope (2026-01-30)

Cycle 26: Added traceability/ and conformance/ to verify_refs scan directories.

| Metric | Before | After |
|--------|--------|-------|
| Files scanned | 300 | 353 |
| Total refs | 300 | 441 |
| Valid refs | 253 | 377 |

**Changes**: `tools/verify_refs.py` - added TRACEABILITY_DIR, CONFORMANCE_DIR constants and scan calls.

**tooling.md #22**: ✅ COMPLETE

---

### Documentation Parse Audit (2026-01-30)

Cycle 25: Identified docs with no tool coverage.

| Metric | Value |
|--------|-------|
| Total docs | 352 |
| Covered | 322 (91%) |
| Uncovered | 30 (8%) |

**Uncovered Categories**:
- conformance/*.md: 9 files
- conformance/*.yaml: 8 files (non-assertions)
- specs/*.md: 3 files
- traceability/*.md: 10 files (4 generated)

**Projected After Fixes**: 91% → 99% coverage

**Deliverable**: `docs/10-domain/documentation-parse-audit.md`

**New Item**: tooling.md #23 (extend verify_assertions)

---

### Trio-dev Checkout + Methodical Analysis (2026-01-30)

Cycle 24: Analyzed Trio-dev structure and queued integration work items.

| Component | Path | Size |
|-----------|------|------|
| oref JS engine | `trio-oref/lib/` | 14 files |
| OpenAPS bridge | `OpenAPS.swift` | 37KB |
| APS Manager | `APSManager.swift` | 55KB |
| Nightscout sync | `Services/Network/Nightscout/` | 4 files |

**Backlog Items Queued**: 8 items
- aid-algorithms.md #5-8: oref mapping, Nightscout sync, OpenAPS bridge, APSManager
- nightscout-api.md #20-22: NightscoutManager, API protocol, Treatment model

**Source**: LIVE-BACKLOG human request

---

### Fix verify_coverage.py (2026-01-30)

Cycle 23: Fixed broken verification tool identified in cycle 22 audit.

| Metric | Before | After |
|--------|--------|-------|
| Requirements found | 0 | 242 |
| Gaps found | 0 | 289 |

**Fixes Applied**:
1. Glob patterns: `*-requirements.md` and `*-gaps.md`
2. REQ regex: `REQ-[A-Z]*-?\d{3}` to match `REQ-SYNC-001` etc.
3. Docstring updated

**Source**: tooling.md #21

---

### Tool Coverage Audit (2026-01-30)

Cycle 22: Analyzed what each verification tool parses and identified coverage gaps.

| Metric | Value |
|--------|-------|
| Verification tools | 7 (6 active) |
| Total docs | 351 |
| Docs covered | 313 (89%) |
| Docs uncovered | 38 (11%) |

**Key Findings**:
- `verify_coverage.py` broken - scans wrong file patterns
- `conformance/**/*.md` (9 files) has no tool coverage
- `docs/` only validated for code refs, no semantic checks

**Deliverable**: `docs/10-domain/tool-coverage-audit.md`

**New Items**: tooling.md #21 (fix verify_coverage), #22 (extend verify_refs)

---

### Prioritization & Backlog Restructure (2026-01-30)

Planning session to chunk and prioritize work based on 5 uncertainty areas identified.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| State Ontology Proposal | `docs/sdqctl-proposals/state-ontology-proposal.md` | observed/desired/control framing |
| Ready Queue Update | `ECOSYSTEM-BACKLOG.md` | 8 items, visibility work prioritized |
| Tooling backlog items | `backlogs/tooling.md` | #18, #19, #20 added |
| Nightscout API backlog items | `backlogs/nightscout-api.md` | #18, #19 added |
| Sync-identity backlog item | `backlogs/sync-identity.md` | #22 added |

**Uncertainty Areas Addressed**:
1. Tool effectiveness → Tool coverage audit (#18) and parse audit (#19)
2. Source completeness → cgm-remote-monitor depth matrix (#18)
3. Audience clarity → Nightscout maintainers + AID vendors (resolved)
4. Conceptual framing → State ontology proposal (NEW)
5. Management path → PR recommendation packaging (#19)

**Ready Queue Prioritization**:
- P1: Visibility work (tool audit, parse audit)
- P2: Conceptual work (ontology, depth matrix, packaging)
- PARKED: Algorithm runners (JVM/Swift) until visibility complete

---

### Progress Archive Hygiene (2026-01-30)

Cycle 21 maintenance: Archived progress.md entries to reduce file size.

| Metric | Before | After |
|--------|--------|-------|
| Lines | 1209 | 60 |
| Entries archived | 47 | - |
| Archive file | - | `progress-archive-2026-01-30-batch2.md` |

**Source**: Hygiene task from Ready Queue

---

### PR #8405 Timezone Review (2026-01-30)

Reviewed cgm-remote-monitor PR #8405 for GAP-TZ-* alignment.

| Aspect | Finding |
|--------|---------|
| PR Title | Fix timezone display to show device timezone |
| Problem | Caregivers see browser time, not device time |
| Fix | Fetch profile timezone, display both when different |
| Gap Impact | GAP-TZ-001 ✅ addressed, GAP-TZ-007 ⚠️ partial |

**Recommendation**: Safe to merge - UX improvement for caregivers

**Source**: nightscout-api.md #15

---

### PR #8422 OpenAPI Compliance Review (2026-01-30)

Reviewed cgm-remote-monitor PR #8422 for alignment with OpenAPI specs.

| Aspect | Finding |
|--------|---------|
| PR Title | Fix api3 limit error when limit is string |
| Problem | `API3_MAX_LIMIT` env var as string → 500 error |
| Fix | `parseInt(maxLimitRaw) || default` |
| OpenAPI | `limit` param is `integer` - fix makes API tolerant |
| Gap Impact | None - robustness fix, not interop issue |

**Recommendation**: Safe to merge

**Source**: nightscout-api.md #14

---

### Tooling Deprecation Evaluation (2026-01-30)

tooling #11: Confirm redundant tools identified for deprecation.

| Action | Count | Tools |
|--------|-------|-------|
| Deprecate | 7 | verify_refs, verify_terminology, linkcheck, verify_hello, run_workflow, phase_nav, project_seq |
| Keep | 27 | Domain-specific with no sdqctl equivalent |

**Status**: Migration eval already documented; marked complete.

---

