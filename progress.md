# AID Alignment Workspace - Progress Tracker

This document tracks completed documentation cycles and candidates for future work.

> **Archive**: Entries before 2026-01-30 moved to [progress-archive-2026-01-30-batch1.md](docs/archive/progress-archive-2026-01-30-batch1.md)

---

## Completed Work

### PR Adoption Sequencing Proposal (2026-01-30)

Ready Queue Item #1: Prioritized roadmap for 68 open PRs.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Proposal | `docs/10-domain/pr-adoption-sequencing-proposal.md` | 9.5KB, 4-phase plan |

**Phased Timeline**:
| Phase | Timeline | PRs | Focus |
|-------|----------|-----|-------|
| Phase 1 | Feb 2026 | 6 | Quick wins (tests, HR, insulin) |
| Phase 2 | Mar 2026 | 3 | Infrastructure (MongoDB 5x, Node 22) |
| Phase 3 | Apr 2026 | 4 | API features + bridge deprecations |
| Phase 4 | Q2 2026 | 5+ | Long-tail cleanup |

**Key Recommendations**:
- Merge #8419 immediately (low risk, testing baseline)
- Bundle #8421 + modernization for v15.1.0
- Security audit required for #7791 before merge
- Deprecate share2nightscout-bridge and minimed-connect-to-nightscout

**Gaps Closed**: GAP-API-HR, GAP-INSULIN-001, GAP-DB-001, GAP-NODE-001/002, GAP-REMOTE-CMD, GAP-TZ-001

---

### Priority PR Deep-Dives (2026-01-30)

Ready Queue Item #3: Deep analysis of top 5 ecosystem-impacting PRs.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Analysis | `docs/10-domain/priority-pr-deep-dives.md` | 13.4KB, 5 PRs analyzed |

**PRs Analyzed**:
| PR | Title | Age | Recommendation |
|----|-------|-----|----------------|
| #8419 | Push Tests | 15 days | Merge first (low risk) |
| #8083 | Heart Rate | 2.5 years | Merge second |
| #8261 | Multi-Insulin | 1.7 years | Merge third |
| #8421 | MongoDB 5x | 11 days | Merge fourth (infrastructure) |
| #7791 | Remote Commands | 3+ years | Merge last (security audit needed) |

**Recommended Merge Sequence**: #8419 → #8083 → #8261 → #8421 → #7791

**Gaps Addressed by PRs**: GAP-API-HR, GAP-INSULIN-001, GAP-INS-001, GAP-DB-001, GAP-REMOTE-CMD

**Security Finding**: PR#7791 requires OTP enforcement before merge.

---

### Node.js LTS Upgrade Analysis (2026-01-30)

Ready Queue Item #2: Analyze Node.js LTS support across Nightscout ecosystem.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Analysis | `docs/10-domain/node-lts-upgrade-analysis.md` | 9.6KB, 4-phase plan |

**Key Findings**:
- **All JS projects on EOL Node versions** (16/14, EOL 2023)
- **Blocker**: `request` package deprecated 2020
- **Target**: Node 22 LTS (EOL 2027-04-30)
- **Urgent**: Node 20 EOL in 3 months (2026-04-30)

**Upgrade Sequence**:
1. nightscout-connect: add engines field (Low)
2. share2nightscout-bridge: **deprecate** (Low)
3. cgm-remote-monitor: Node 22 + request→axios (High)
4. minimed-connect-to-nightscout: **deprecate** (Low)

**Gaps Identified**: GAP-NODE-001, GAP-NODE-002, GAP-NODE-003

**Requirements Added**: REQ-NODE-001, REQ-NODE-002, REQ-NODE-003

---

### Nocturne Authentication Compatibility Analysis (2026-01-30)

OQ-010 Extended API Item #9: Compare auth mechanisms between implementations.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Analysis | `docs/10-domain/nocturne-auth-compatibility.md` | 320+ lines |

**Key Findings**:
- **FULL COMPATIBILITY** - All auth methods work identically
- API_SECRET header: SHA1 hash, grants admin (*)
- JWT Bearer: HMAC-SHA256, same validation
- Access tokens: Same `{name}-{hash}` format
- Default roles: 7 identical roles

**Gaps Identified**: None - Full parity achieved

**OQ-010 Extended**: API Item #9 of 4 complete (4/4) - **QUEUE COMPLETE!**

---

### Nocturne V2 DData Endpoint Analysis (2026-01-30)

OQ-010 Extended API Item #8: Verify DData combined response matches Loop/AAPS expectations.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Analysis | `docs/10-domain/nocturne-ddata-analysis.md` | 290+ lines |

**Key Findings**:
- **High parity** - All 8 core collections present
- **One gap** - `lastProfileFromSwitch` missing (GAP-API-016)
- **Loop devicestatus** - Full typed model coverage
- **OpenAPS devicestatus** - Full typed model coverage
- **Nocturne bonus** - Pre-filtered treatment lists (8 additional)

**Gaps Identified**: GAP-API-016 (lastProfileFromSwitch missing)

**OQ-010 Extended**: API Item #8 of 4 complete (3/4)

---

### Nocturne eventType Handling Analysis (2026-01-30)

OQ-010 Extended API Item #7: Compare eventType normalization behavior.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Analysis | `docs/10-domain/nocturne-eventtype-handling.md` | 280+ lines |

**Key Findings**:
- **High parity** - Both systems store as string, accept any value
- **Case-sensitive** - Both use exact string matching
- **28 vs ~25 types** - Nocturne enum has more types defined
- **Minor gap** - Immutability not enforced in Nocturne

**Gaps Identified**: GAP-TREAT-010 (immutability), GAP-TREAT-011 (missing TT type)

**OQ-010 Extended**: API Item #7 of 4 complete (2/4)

---

### Nocturne V3 API Parity Analysis (2026-01-30)

OQ-010 Extended API Item #6: Comprehensive V3 API behavioral comparison.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Test Scenarios | `conformance/scenarios/nocturne-v3-parity/` | 3 scenario files |
| README | `nocturne-v3-parity/README.md` | 250+ lines, executive summary |
| Query Tests | `query-parameters.yaml` | 18 scenarios |
| Filter Tests | `filter-operators.yaml` | 22 scenarios |
| History Tests | `history-endpoint.yaml` | 8 scenarios + workarounds |

**Key Findings**:
- **Query parameters**: ✅ Full parity (9 operators, date parsing)
- **History endpoint**: ❌ **MISSING** in Nocturne (GAP-SYNC-041)
- **ETag handling**: Different strategies (timestamp vs content-hash)
- **Pagination**: Nocturne enhanced (X-Total-Count, Link headers)
- **Soft delete**: ❌ Not supported (GAP-SYNC-040)

**Critical Gap**: Missing `/api/v3/{collection}/history/{lastModified}` endpoint
- Primary sync mechanism for AAPS/Loop
- No workaround for soft-delete detection

**Gaps Identified**: GAP-SYNC-041, GAP-API-010, GAP-API-011

**OQ-010 Extended Research Queue**: API Item #6 of 4 complete

---

### Nocturne Deletion Semantics Analysis (2026-01-30)

OQ-010 Extended Item #18: Analyzed soft-delete vs hard-delete behavior differences.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep Dive | `docs/10-domain/nocturne-deletion-semantics.md` | 250+ lines, remediation options |
| Gap Updates | `traceability/sync-identity-gaps.md` | GAP-SYNC-040 updated with analysis |

**Key Findings**:
- **cgm-remote-monitor**: Soft delete (isValid=false), records visible in history
- **Nocturne**: Hard delete (record removed), no history tracking
- **Sync impact**: Clients can't detect server-side deletions
- **Recommendation**: Implement soft delete with isValid field

**Affected Scenarios**:
- Multi-device sync (stale data on other devices)
- Audit trail (no record of deletions)
- Undo capability (deleted data unrecoverable)

**OQ-010 Extended Research Queue**: Item #18 of 18 complete (sync-identity queue done!)

---

### Nocturne srvModified Gap Analysis (2026-01-30)

OQ-010 Extended Item #17: Analyzed srvModified field implementation differences.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Gap Analysis | `docs/10-domain/nocturne-srvmodified-gap-analysis.md` | 200+ lines, full remediation analysis |
| Gap Updates | `traceability/sync-identity-gaps.md` | GAP-MIGRATION-001, GAP-SYNC-039 updated |

**Key Findings**:
- **Per-record srvModified**: Nocturne returns `Mills` (event time), not server modification time
- **LastModified endpoint**: Correctly uses `SysUpdatedAt` for modification tracking
- **Sync impact**: None - AAPS/Loop use endpoint, not per-record field
- **Recommendation**: No remediation required

**Semantic Difference**:
| cgm-remote-monitor | Nocturne |
|-------------------|----------|
| `srvModified` = server modification time | `srvModified` = event time (`Mills`) |
| `/lastModified` uses `srvModified` | `/lastModified` uses `SysUpdatedAt` |

**OQ-010 Extended Research Queue**: Item #17 of 18 complete

---

### Nocturne Connector Coordination Analysis (2026-01-30)

OQ-010 Extended Item #16: Analyzed multi-connector polling architecture and loop-back risks.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep Dive | `docs/10-domain/nocturne-connector-coordination.md` | 300+ lines, architecture diagram |
| Gap Updates | `traceability/connectors-gaps.md` | GAP-CONNECT-010/011/012 |
| Req Updates | `traceability/connectors-requirements.md` | REQ-CONNECT-010/011/012 |

**Key Findings**:
- **Sidecar architecture**: Each connector runs independently with own timer
- **DataSource tagging**: Full provenance tracking via `data_source` field
- **Resilient polling**: 10s fast poll → exponential backoff (30+ failures)
- **Loop-back risk**: No explicit prevention for Nightscout↔Nocturne bidirectional sync (GAP-CONNECT-011)
- **Cross-connector dedup**: Delegated to server-side matching

**Source Files Analyzed**:
- `externals/nocturne/src/Connectors/Nocturne.Connectors.Core/Services/ResilientPollingHostedService.cs`
- `externals/nocturne/src/Connectors/Nocturne.Connectors.Nightscout/Services/NightscoutConnectorService.cs`
- `externals/nocturne/src/Core/Nocturne.Core.Constants/DataSources.cs`

**OQ-010 Extended Research Queue**: Item #16 of 18 complete

---

### PostgreSQL Migration Field Fidelity Analysis (2026-01-30)

OQ-010 Extended Item #15: Verified field mapping between cgm-remote-monitor MongoDB and Nocturne PostgreSQL.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Field Mapping | `mapping/nocturne/migration-field-fidelity.md` | 300+ lines, comprehensive field tables |
| Gap Updates | `traceability/sync-identity-gaps.md` | GAP-MIGRATION-001/002/003 |
| Req Updates | `traceability/sync-identity-requirements.md` | REQ-MIGRATION-001-004 |

**Key Findings**:
- **Full field fidelity** achieved through typed columns + JSONB
- **60+ treatment columns**: All AAPS/Loop fields preserved (percentage, timeshift, insulinNeedsScaleFactor)
- **Nested objects**: DeviceStatus uses JSONB for loop/openaps/pump (no flattening)
- **Arbitrary fields**: `additional_properties` JSONB captures unknown fields
- **srvModified issue**: Computed from `mills`, not stored independently (GAP-MIGRATION-001)
- **original_id**: Preserves MongoDB ObjectId for migration tracking

**Source Files Analyzed**:
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/EntryEntity.cs`
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/TreatmentEntity.cs`
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/DeviceStatusEntity.cs`
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/ProfileEntity.cs`

**OQ-010 Extended Research Queue**: Item #15 of 18 complete

---

### Nocturne SignalR→Socket.IO Bridge Analysis (2026-01-30)

OQ-010 Extended Item #12: Analyzed bridge for event parity, latency, and compatibility.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep Dive | `docs/10-domain/nocturne-signalr-bridge-analysis.md` | 293 lines, event mapping table |
| Gap Update | `traceability/connectors-gaps.md` | GAP-NOCTURNE-003 confirmed (5-10ms latency) |
| New Gaps | Same file | GAP-BRIDGE-001/002 added |

**Key Findings**:
- **Functional parity** for core events: `dataUpdate`, `alarm`, `create/update/delete`
- **Latency**: 5-10ms overhead (acceptable for 5-min CGM intervals)
- **Missing**: `clients` event (GAP-BRIDGE-001), compression (GAP-BRIDGE-002)
- **Event ordering**: Preserved within event types

**Source Files Analyzed**:
- `externals/nocturne/src/Web/packages/bridge/src/lib/signalr-client.ts`
- `externals/nocturne/src/Web/packages/bridge/src/lib/message-translator.ts`
- `externals/nocturne/src/Web/packages/bridge/src/lib/socketio-server.ts`
- `externals/cgm-remote-monitor/lib/server/websocket.js`

**OQ-010 Extended Research Queue**: Item #12 of 18 complete

---

### Terminology Cleanup (2026-01-30)

Fixed deprecated term usage and broken workflow link.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Term fixes | `docs/sdqctl-proposals/RUN-BRANCHING.md` | 5 deprecated terms → "synthesis cycle" |
| Link fix | Same file | Fixed broken workflow link |

**Result**: `sdqctl verify terminology` now shows 0 deprecated (was 5).

---

### Broken Refs Remediation (2026-01-30)

Fixed broken code references in active documentation.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Ref fixes | `docs/10-domain/authentication-flows-deep-dive.md` | 5 refs: `nightscout:` → `crm:` |
| Link fixes | `traceability/nightscout-api-gaps.md`, `treatments-gaps.md` | 5 refs: `ns:` → `crm:`, paths fixed |
| Validation | `traceability/refs-validation.md` | 360/392 valid (92%) |

**Result**: Fixed alias usage and paths. Remaining errors are in archive or auto-generated files.

---

### ADR-004: ProfileSwitch → Override Mapping Rules (2026-01-30)

Drafted architectural decision record resolving OQ-010 based on 6 prior analyses.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| ADR-004 | `docs/90-decisions/adr-004-profile-override-mapping.md` | 222 lines, 5 decisions |

**Key Decisions**:
- **Dual acceptance**: Both Override (Loop/Trio) and ProfileSwitch (AAPS) are valid
- **Semantic equivalence**: `insulinNeedsScaleFactor` ↔ `percentage/100`
- **Percentage requirement**: Servers MUST apply percentage at query time
- **StateSpan recommended**: V4 model for profile activation history
- **Translation rules**: Explicit cross-system query mapping

**Gaps Addressed**: GAP-NOCTURNE-004/005, GAP-OVRD-005/006, GAP-OREF-001

**OQ-010 Research Queue**: Item #11 of 11 complete (7/7 in original scope) ✅ RESOLVED

---

### Nocturne Rust oref Profile Handling Analysis (2026-01-30)

Analyzed how Nocturne's Rust oref implementation consumes profile data and compared with JS oref0.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Analysis doc | `docs/10-domain/nocturne-rust-oref-profile-analysis.md` | 290+ lines, 3 REQs, 3 GAPs |

**Key Findings**:
- **Algorithm Equivalent**: Rust oref parses basal/ISF/CR schedules identically to JS oref0
- **Same Format**: Both use minutes-from-midnight, i-index sorting, 3-decimal rounding
- **CRITICAL GAP**: PredictionService bypasses ProfileService - raw values sent to Rust oref
- **Percentage Ignored**: Active ProfileSwitch percentage/timeshift NOT applied to predictions
- **Single Values**: C# OrefProfile passes only current values, not full schedules

**Gaps Added**: GAP-OREF-001, GAP-OREF-002, GAP-OREF-003

**Requirements Added**: REQ-OREF-001, REQ-OREF-002, REQ-OREF-003

**Source Files Analyzed**:
- `externals/nocturne/src/Core/oref/src/profile/basal.rs`
- `externals/nocturne/src/Core/oref/src/types/profile.rs`
- `externals/nocturne/src/Core/Nocturne.Core.Oref/OrefService.cs`
- `externals/nocturne/src/Core/Nocturne.Core.Oref/Models/OrefModels.cs`
- `externals/nocturne/src/API/Nocturne.API/Services/PredictionService.cs`
- `externals/nocturne/src/API/Nocturne.API/Services/ProfileService.cs`
- `externals/oref0/lib/profile/basal.js`

**OQ-010 Research Queue**: Item #10 of 7 complete (originally 7 items, now extended)

---

### Nocturne V4 ProfileSwitch Extensions Discovery (2026-01-30)

Analyzed Nocturne V4 API extensions for profile and override tracking beyond V3 baseline.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Analysis doc | `docs/10-domain/nocturne-v4-profile-extensions.md` | 240+ lines, 2 REQs, 2 GAPs |

**Key Findings**:
- **StateSpan API**: V4 provides `/api/v4/state-spans/profiles` for profile activation history
- **No V3 Equivalent**: V3 only has profile document CRUD, not activation tracking
- **ChartDataController**: Returns `ProfileSpans` in chart data response for visualization
- **StateSpan Model**: Includes `CanonicalId` for deduplication, `Sources` for multi-source merge
- **9 Categories**: Profile, Override, TempBasal, PumpMode, PumpConnectivity, Sleep, Exercise, Illness, Travel

**Gaps Added**: GAP-V4-001, GAP-V4-002

**Requirements Added**: REQ-V4-001, REQ-V4-002

**Source Files Analyzed**:
- `externals/nocturne/src/API/Nocturne.API/Controllers/V4/StateSpansController.cs`
- `externals/nocturne/src/Core/Nocturne.Core.Models/StateSpan.cs`
- `externals/nocturne/src/Core/Nocturne.Core.Models/StateSpanEnums.cs`
- `externals/nocturne/src/API/Nocturne.API/Controllers/V4/ChartDataController.cs`

**OQ-010 Research Queue**: Item #9 of 7 complete (originally 7 items, now extended)

---

### Nocturne Override/Temporary Target Analysis (2026-01-30)

Analyzed how Nocturne handles Loop Override and AAPS Temporary Target events.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Analysis doc | `docs/10-domain/nocturne-override-temptarget-analysis.md` | 250+ lines, 2 REQs, 3 GAPs |

**Key Findings**:
- **EventType Distinction**: Loop uses `Temporary Override`; AAPS uses `Temporary Target` - no unification
- **Field Semantics**: Override has `insulinNeedsScaleFactor`; TempTarget has `targetTop`/`targetBottom`
- **Supersession**: Neither system tracks override supersession
- **V4 StateSpan**: Provides unified query but no override linking
- **Duration Units**: Presets in seconds; treatments in minutes (conversion required)

**Gaps Added**: GAP-OVRD-005, GAP-OVRD-006, GAP-OVRD-007

**Requirements Added**: REQ-OVRD-004, REQ-OVRD-005

**Source Files Analyzed**:
- `externals/nocturne/src/Core/Nocturne.Core.Models/Treatment.cs`
- `externals/nocturne/src/Core/Nocturne.Core.Models/LoopModels.cs`
- `externals/nocturne/src/API/Nocturne.API/Services/LoopService.cs`
- `externals/cgm-remote-monitor/lib/server/loop.js`

**OQ-010 Research Queue**: Item #8 of 7 complete (originally 7 items, now extended)

---

### Nocturne vs cgm-remote-monitor Profile Sync Comparison (2026-01-30)

Compared profile collection sync behavior between Nocturne and cgm-remote-monitor implementations.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Comparison doc | `docs/10-domain/nocturne-cgm-remote-monitor-profile-sync.md` | 200+ lines, 3 REQs, 3 GAPs |

**Key Findings**:
- **Deduplication**: cgm-remote-monitor uses `identifier` OR `created_at` fallback; Nocturne only uses `Id`/`OriginalId`
- **srvModified**: Missing from Nocturne Profile model; breaks sync polling
- **Delete semantics**: cgm-remote-monitor soft deletes (isValid=false); Nocturne hard deletes

**Gaps Added**: GAP-SYNC-038, GAP-SYNC-039, GAP-SYNC-040

**Requirements Added**: REQ-SYNC-059, REQ-SYNC-060, REQ-SYNC-061

**Source Files Analyzed**:
- `externals/cgm-remote-monitor/lib/api3/generic/setup.js:65-73`
- `externals/cgm-remote-monitor/lib/api3/storage/mongoCollection/utils.js:130-169`
- `externals/nocturne/src/Core/Nocturne.Core.Models/Profile.cs`
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Repositories/ProfileRepository.cs`

**OQ-010 Research Queue**: Item #7 of 7 complete

---

### Nocturne ProfileSwitch Treatment Model Analysis (2026-01-30)

Analyzed how Nocturne handles AAPS ProfileSwitch events, including percentage and timeshift application.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep dive | `docs/10-domain/nocturne-profileswitch-analysis.md` | 300+ lines, 3 REQs, 1 GAP |

**Key Finding**: Nocturne **actively applies** percentage/timeshift adjustments to profile calculations, while cgm-remote-monitor only displays them.

**Fields Analyzed**:
- `profileJson` - Stored as JSONB, preserved through API
- `percentage` - Applied: basal×%, ISF÷%, CR÷%
- `timeshift` - Applied: schedule rotation in hours
- `CircadianPercentageProfile` - Boolean flag triggers application logic

**Source Files**:
- `src/Core/Nocturne.Core.Models/Treatment.cs:413-519`
- `src/API/Nocturne.API/Services/ProfileService.cs:175-241`

**Gaps Added**: GAP-NOCTURNE-004 (percentage application divergence)

**Requirements Added**: REQ-SYNC-054, REQ-SYNC-055, REQ-SYNC-056

---

### sdqctl Usage Documentation (2026-01-30)

Expanded `docs/TOOLING-GUIDE.md` with comprehensive sdqctl integration guide.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Usage guide | `docs/TOOLING-GUIDE.md` | +60 lines, 40 sdqctl references |

**Sections Added**:
- Quick Start commands
- All 9 verify subcommands with options
- Common workflows (CI, targeted, JSON)
- Migration table (4 deprecated tools)
- Unique tools list (6 to keep)
- Drift detection commands
- Workflow execution examples

---

### Unit Tests for Verification Tools (2026-01-30)

Created `tools/test_verify_tools_unit.py` with 17 synthetic fixture tests.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Unit test file | `tools/test_verify_tools_unit.py` | 17 tests, all passing |

**Coverage Added**:

| Tool | Tests | Functions Tested |
|------|-------|------------------|
| verify_assertions.py | 5 | REQ/GAP patterns, YAML parsing |
| verify_coverage.py | 1 | requirement extraction |
| verify_gap_freshness.py | 2 | gap ID patterns, status detection |
| verify_mapping_coverage.py | 2 | field extraction from tables/code blocks |
| validate_json.py | 3 | JSON/YAML loading, ShapeValidator |
| validate_fixtures.py | 3 | infer_shape_type, ValidationError |
| Integration | 1 | extract_assertions with scenario inheritance |

**Total unit tests in workspace**: 45 (28 hygiene + 17 verify)

---

### sdqctl Tool Migration Evaluation (2026-01-30)

Evaluated overlap between 39 custom Python tools and sdqctl CLI.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Updated proposal | `docs/sdqctl-proposals/tools-comparison-proposal.md` | Detailed overlap matrix |

**Findings**:

| Action | Count | Tools |
|--------|-------|-------|
| Deprecate | 7 | verify_refs, verify_terminology, linkcheck, verify_hello, run_workflow, phase_nav, project_seq |
| Integrate | 3 | queue_stats, backlog_hygiene, doc_chunker → sdqctl plugins |
| Keep | 27 | Domain-specific with no sdqctl equivalent |

**Key insight**: `sdqctl verify` already provides idiomatic subcommands for refs, terminology, links, assertions, coverage, traceability. Custom tools for gap freshness, mapping coverage, fixture validation provide unique value.

---

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


### Nocturne Percentage/Timeshift Handling Analysis (2026-01-30)

OQ-010 Item #6: Analysis of how Nocturne applies AAPS-specific percentage and timeshift fields.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Deep Dive | `docs/10-domain/nocturne-percentage-timeshift-handling.md` | Profile API returns raw; internal uses scaled |

**Key Findings**:
- Nocturne Profile API (V1/V3) returns **raw** profile data without scaling
- Scaling only applied internally via `GetValueByTime()` for IOB/COB/bolus
- Loop/Trio fetch raw profiles and are unaware of AAPS percentage/timeshift
- Creates divergence: Nocturne displays use scaled; Loop/Trio algorithms use raw

**Gaps Identified**: GAP-NOCTURNE-005

**Requirements Added**: REQ-SYNC-057, REQ-SYNC-058

**Source Files Analyzed**:
- `externals/nocturne/src/API/Nocturne.API/Controllers/V1/ProfileController.cs`
- `externals/nocturne/src/API/Nocturne.API/Controllers/V3/ProfileController.cs`
- `externals/nocturne/src/API/Nocturne.API/Services/ProfileService.cs:164-245`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/Extensions/ProfileSet.swift`

---

### Nocturne Rust oref Conformance Analysis (2026-01-30)

OQ-010 Item #13: Verification that Nocturne's Rust oref implementation produces equivalent results to JS oref0.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Conformance Analysis | `conformance/scenarios/nocturne-oref/README.md` | ✅ Verified equivalent |
| Test Fixtures | `conformance/scenarios/nocturne-oref/iob-tests.yaml` | 25+ test vectors |

**Key Findings**:
- **IOB Bilinear**: ✅ Same formula, same polynomial coefficients
- **IOB Exponential**: ✅ Same LoopKit #388 formula
- **COB Algorithm**: ✅ Same deviation-based approach
- **Precision**: Both use IEEE 754 f64 (< 1e-15 difference)
- **Minor differences**: Rust enforces DIA minimums (3h bilinear, 5h exponential)

**Gaps Identified**:
- GAP-OREF-CONFORMANCE-001: Peak time validation (defensive, not breaking)
- GAP-OREF-CONFORMANCE-002: Small dose classification (additive feature)
- GAP-OREF-CONFORMANCE-003: ✅ Verified equivalent

**Requirements Added**:
- REQ-OREF-CONFORM-001: IOB equivalence within 0.01 U tolerance
- REQ-OREF-CONFORM-002: Peak time validation bounds
- REQ-OREF-CONFORM-003: COB algorithm equivalence

**Source Files Analyzed**:
- `externals/nocturne/src/Core/oref/src/insulin/calculate.rs` (Rust exponential/bilinear)
- `externals/nocturne/src/Core/oref/src/iob/total.rs` (Rust total IOB)
- `externals/nocturne/src/Core/oref/src/cob/mod.rs` (Rust COB)
- `externals/oref0/lib/iob/calculate.js` (JS reference implementation)

---

### Nocturne V4 StateSpan Standardization Proposal (2026-01-30)

OQ-010 Item #14: Evaluate V4 StateSpan model for ecosystem adoption.

| Deliverable | Location | Key Insights |
|-------------|----------|--------------|
| Standardization Proposal | `docs/sdqctl-proposals/statespan-standardization-proposal.md` | Recommend V3 extension |

**Key Findings**:
- StateSpan provides cleaner abstraction for time-ranged states than treatments
- 9 categories: Profile, Override, TempBasal, PumpMode, PumpConnectivity, Sleep, Exercise, Illness, Travel
- Minimal viable subset: Profile, Override, TempBasal, PumpMode (Phase 1)
- Recommendation: Add as V3 extension for backward compatibility

**Gaps Identified**: GAP-STATESPAN-001, GAP-STATESPAN-002, GAP-STATESPAN-003

**Requirements Added**: REQ-STATESPAN-001 through REQ-STATESPAN-005

**Migration Path**:
1. Phase 1: StateSpan collection + read API
2. Phase 2: Auto-translation from treatments
3. Phase 3: Native StateSpan writes
4. Phase 4: Deprecate treatment-based queries

**Source Files Analyzed**:
- `externals/nocturne/src/Core/Nocturne.Core.Models/StateSpan.cs`
- `externals/nocturne/src/Core/Nocturne.Core.Models/StateSpanEnums.cs`
- `externals/nocturne/src/API/Nocturne.API/Controllers/V4/StateSpansController.cs`
- `externals/cgm-remote-monitor/lib/server/loop.js` (Override handling)

---
