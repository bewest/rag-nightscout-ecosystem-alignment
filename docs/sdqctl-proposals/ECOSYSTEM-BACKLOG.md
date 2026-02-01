# Ecosystem Alignment Backlog

> **Last Updated**: 2026-01-31  
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
| **iOS Mobile Platform** | [backlogs/ios-mobile-platform.md](backlogs/ios-mobile-platform.md) | iOS apps, NightscoutKit SDK, App Store |
| **Documentation Accuracy** | [backlogs/documentation-accuracy.md](backlogs/documentation-accuracy.md) | Bottom-up claim verification |
| Live requests | [../../LIVE-BACKLOG.md](../../LIVE-BACKLOG.md) | Midflight human requests |

---

## Ready Queue (5-10 items)

Items ready for immediate work. Keep 5-10 visible for horizontal work across domains.

> **Last Groomed**: 2026-02-01 (cycle 100) | **Open Items**: 6  
> **Domain Archive**: [domain-backlog-archive-2026-02-01.md](../archive/domain-backlog-archive-2026-02-01.md) (115 items archived)

### 1. [P2] Loop Swift algorithm runner
**Type:** Implementation | **Effort:** High
**Repos:** LoopWorkspace
**Focus:** Swift-based runner for Loop algorithm conformance testing
**Prerequisites:** Swift 6.2.3 available ✅
**Deliverable:** `conformance/runners/loop-runner.swift`
**Source:** aid-algorithms.md #2
**Blocker:** Requires macOS for iOS framework resolution

### 2. [P2] V4 API Integration Phase 2: Nocturne soft delete
**Type:** Implementation | **Effort:** Medium
**Repos:** nocturne
**Focus:** Add soft delete support to align with cgm-remote-monitor behavior
**Source:** nightscout-api.md #25, Phase 2 item
**Gap Reference:** GAP-SYNC-040
**Blocker:** Requires changes to external nocturne repo

### 3. [P2] MongoDB Phase 3: Driver upgrade execution
**Type:** Implementation | **Effort:** Medium
**Focus:** Execute MongoDB driver upgrade from mongodb-legacy to mongodb@6.x
**Prerequisites:** Phase 2 complete ✅ (no Write Result Translator needed)
**Source:** mongodb-update-readiness-report.md Phase 3
**Deliverable:** PR to cgm-remote-monitor with driver upgrade
**Blocker:** Requires changes to external cgm-remote-monitor repo

### 4. [P2] StateSpan V3 extension specification
**Type:** Proposal | **Effort:** High
**Focus:** Draft V3 API extension for StateSpan endpoints
**Prerequisites:** StateSpan standardization proposal ✅
**Source:** sync-identity.md #19
**Deliverable:** `specs/openapi/aid-statespan-2025.yaml`

### 5. [P2] Safety limit assertions
**Type:** Conformance | **Effort:** Medium
**Focus:** Max IOB/basal enforcement, DIA minimum validation, peak time bounds
**Source:** aid-algorithms-matrix.md action item #2 (REQ-ALG-003, REQ-INS-002)
**Deliverable:** `conformance/assertions/safety-limits.yaml`
**Impact:** Cover safety-critical algorithm limits

### 6. [P2] Cross-controller deduplication assertions
**Type:** Conformance | **Effort:** Medium
**Focus:** Multi-controller conflict scenario assertions
**Source:** sync-identity-matrix.md action items (GAP-SYNC-029, GAP-SYNC-030)
**Deliverable:** `conformance/assertions/cross-controller-dedup.yaml`
**Impact:** Address multi-controller coexistence gaps

---

## Recently Completed (2026-02-01)

| Item | Deliverable | Key Finding |
|------|-------------|-------------|
| **Degraded Operation Assertions** | `conformance/assertions/degraded-operation.yaml` | 24 assertions, 6 REQs, safety-critical fallback covered |
| **AID Algorithms Matrix** | `traceability/domain-matrices/aid-algorithms-matrix.md` | 56 REQs, 66 GAPs, 0% coverage, duplicate REQ IDs found |
| **🎉 Interop/Unit Assertions** | `conformance/assertions/interop-unit-requirements.yaml` | 22 assertions, 7 REQs covered, treatments 100% COMPLETE |
| **Remote Command Assertions** | `conformance/assertions/remote-command-requirements.yaml` | 35 assertions, 11 REQs covered, treatments 49%→80% |
| **Alarm Requirements Assertions** | `conformance/assertions/alarm-requirements.yaml` | 28 assertions, 10 REQs covered, treatments 20%→49% |
| **Treatments Domain Matrix** | `traceability/domain-matrices/treatments-matrix.md` | 35 REQs, 9 GAPs; 20% coverage; Alarm/Remote 0% |
| **Sync-Identity REQ Assertions** | `conformance/assertions/sync-identity-reqs.yaml` | 19 assertions, 15 REQs covered, sync-identity 47%→94% |
| **Bridge/Connector Assertions** | `conformance/assertions/bridge-connector.yaml` | 17 assertions, 6 REQs covered, CGM domain 100% complete |
| **Libre Protocol Assertions** | `conformance/assertions/libre-protocol.yaml` | 16 assertions, 6 REQs covered, CGM coverage 33%→67% |
| **CGM BLE Protocol Assertions** | `conformance/assertions/ble-protocol.yaml` | 13 assertions, 6 REQs covered, CGM coverage 0%→33% |
| **CGM Sources Traceability Matrix** | `domain-matrices/cgm-sources-matrix.md` | 18 REQs, 52 GAPs; 0% assertion coverage; BLE/Libre assertions needed |
| **Stale Refs Cleanup** | 6 archive files updated | Added disclaimers for abbreviated paths; refs are historical |
| **Sync-Identity Traceability Matrix** | `domain-matrices/sync-identity-matrix.md` | 32 REQs, 25 GAPs; 47% REQ coverage; 22 uncovered gaps identified |
| **GAP-REQ Bidirectional Trace Links** | 3 gap files updated | 6 reverse links added for Tier 1 interoperability REQs |
| **Orphan Artifact Priority Analysis** | `orphan-artifact-priorities.md` | 88 REQs analyzed, 6 tiers, action items for alarm/pump assertions |
| **Conformance Scenario Expansion** | 3 assertion YAMLs | 11 REQs covered (99→88 uncovered), devicestatus/profile/API assertions |
| **StateSpan V3 Extension Spec** | `specs/openapi/statespan-v3-extension.md` | 4 categories, backward compat, reference only (author prefers V4) |
| **MongoDB Phase 2: Storage Layer** | `mongodb-storage-layer-analysis.md` | No insertMany, all patterns 5.x/6.x compatible, ready for Phase 3 |
| **cgm-remote-monitor V4 Adoption** | `cgm-remote-monitor-v4-adoption-proposal.md` | 7 adoptable features, 4-phase roadmap, no breaking changes |
| **Tandem Integration Inventory** | `docs/10-domain/tandem-integration-inventory.md` | Cloud-bridge only; no open-source AID control; GAP-TANDEM-001 |
| **Tidepool Integration Inventory** | `docs/10-domain/tidepool-integration-inventory.md` | 5/7 apps integrated; 4 gaps, 4 reqs |
| **AAPS Kotlin Runner Documentation** | `conformance/README.md` | JVM 11+, `make aaps-runner`, scaffolding ready |

## Recently Completed (2026-01-31)

| Item | Deliverable | Key Finding |
|------|-------------|-------------|
| **NS Community Identity Provider** | `ns-community-idp-proposal.md` (14.4KB) | Federated OIDC with Hosting Providers Council; 3 gaps, 4 reqs |
| **V4 API Integration Phase 1** | OpenAPI spec + client guide (17.8KB) | V4 documented as Nocturne Extension; feature detection required |
| **🎉 iOS Backlog 100% COMPLETE** | 10 documents, 23 gaps, 22 reqs | All 10 items complete; modular architecture recommended |
| **BLE CGM Library Consolidation** | `docs/10-domain/ble-cgm-library-consolidation.md` | Full consolidation not practical; shared constants package recommended; 5 gaps, 4 reqs |
| **TestFlight Distribution Infrastructure** | `docs/10-domain/testflight-distribution-infrastructure.md` | 5/7 apps browser build; 3 gaps, 3 reqs |
| **WidgetKit Standardization Survey** | `docs/10-domain/widgetkit-standardization-survey.md` | 6 apps surveyed; Loop/Trio missing widgets; 4 gaps, 3 reqs |
| **HealthKit Integration Audit** | `docs/10-domain/healthkit-integration-audit.md` | 5 apps write glucose; high duplicate risk; 3 gaps, 3 reqs |
| **Apple Watch Complications Survey** | `docs/10-domain/apple-watch-complications-survey.md` | 6 apps inventoried; Loop ClockKit deprecated; 2 refresh patterns; 4 gaps, 3 reqs |
| **Follower/Caregiver Feature Consolidation** | `docs/10-domain/follower-caregiver-feature-consolidation.md` | 14 features compared; 3 shared packages proposed; 4 gaps, 4 reqs added |
| **Cross-Platform Testing Infrastructure** | `docs/10-domain/cross-platform-testing-infrastructure-design.md` | xtool for algorithms only; 3-tier CI; 90% cost reduction; protocol mocks |
| **App Store Pathway Analysis** | `docs/10-domain/app-store-pathway-analysis.md` | DiaBLE/Nightguard patterns; 14-feature decision matrix; 3 disclaimer types |
| **Nightscout V4 Integration Proposal** | `nightscout-v4-integration-proposal.md` | P0-P3 recommendations; V4 = Nocturne Extension; sync gaps documented |
| **Swift Package Ecosystem Assessment** | `docs/10-domain/swift-package-ecosystem-assessment.md` | Submodules not SPM; LoopKit Package.swift incomplete; GAP-SPM-001/002 added |
| **StateSpan V4 Preference Update** | `statespan-standardization-proposal.md` | Nocturne author: V4-only, no V3 backport |
| **Trusted Identity Providers Inventory** | `docs/10-domain/trusted-identity-providers.md` | Only Tidepool is true IdP; 3 gaps, 3 reqs added |
| **Identity Provider Backlog** | `backlogs/nightscout-api.md` #23-24 | Queued IDP inventory + community proposal |
| **iOS Mobile Platform Evaluation** | `backlogs/ios-mobile-platform.md` | 8 apps, submodule sharing, modular architecture recommended |
| **NightscoutKit Swift SDK Design** | `nightscoutkit-swift-sdk-design.md` | v3-first, actor-based, builds on gestrich/NightscoutKit |

---

## Recently Completed (2026-01-30)

| Item | Deliverable | Key Finding |
|------|-------------|-------------|
| **PR recommendation packaging** | `docs/10-domain/nightscout-maintainer-recommendations.md` | 4 priority areas: PRs, sync gaps, API completeness, controller output |
| **cgm-remote-monitor analysis depth matrix** | `docs/10-domain/cgm-remote-monitor-analysis-depth-matrix.md` | 57% avg coverage, 2 collections (food, activity) need specs |
| **Classify GAP-SYNC-* by ontology** | `traceability/sync-identity-gaps.md` | 22 gaps classified: 6 Observed, 8 Desired, 2 Control, 6 Cross-category |
| **State ontology definition** | `docs/architecture/state-ontology.md` | Observed/Desired/Control categories defined with sync semantics |
| **Extend verify_assertions scope** | `tools/verify_assertions.py` | 4→12 YAML files, now scans conformance/**/*.yaml |
| **Extend verify_refs scope** | `tools/verify_refs.py` | 300→353 files, now scans traceability/, conformance/ |
| **Documentation parse audit** | `docs/10-domain/documentation-parse-audit.md` | 30 uncovered (8%), 91%→99% after fixes |
| **Trio-dev checkout + analysis** | aid-algorithms.md #5-8, nightscout-api.md #20-22 | 8 integration items queued from structure analysis |
| **Fix verify_coverage.py** | `tools/verify_coverage.py` | 0→242 reqs, 0→289 gaps - tool now functional |
| **Tool coverage audit** | `docs/10-domain/tool-coverage-audit.md` | 89% coverage, verify_coverage.py broken, conformance/*.md uncovered |
| **Progress.md archive hygiene** | `progress-archive-2026-01-30-batch2.md` | 1209→60 lines (95% reduction) |
| **PR #8405 timezone review** | GAP-TZ-001 updated, `ecosystem-pr-analysis` | GAP-TZ-001 addressed by PR, safe to merge |
| **PR #8422 OpenAPI compliance review** | `ecosystem-pr-analysis-2026-01-29.md` | Safe to merge - robustness fix, no interop gap |
| **Tooling deprecation evaluation** | tooling.md #11 | 7 tools identified for deprecation |
| **Aid-algorithms cross-ref completion** | Cross-ref to documentation-accuracy.md #11, #19 | Medium-effort items cleared; high-effort remain |
| **Sync-identity cross-ref completion** | Cross-ref to documentation-accuracy.md #7, #21, #24 | All 4 sync-identity items complete |
| **Devicestatus/entries claims verification** | Cross-ref to documentation-accuracy.md #12-14 | Already verified 100% accurate (2026-01-29) |
| **REQ-API → OpenAPI alignment audit** | `docs/10-domain/req-api-openapi-alignment-audit.md` | 67% full coverage, 33% partial; need x-aid-req annotations |
| **GAP-API freshness verification** | `docs/10-domain/gap-api-freshness-verification.md` | 3 addressed by PR, 2 partial, 11 open |
| **StateSpan client SDK patterns** | `docs/10-domain/statespan-client-sdk-patterns.md` | 4 query patterns, 3 caching strategies, platform SDKs |
| **StateSpan gap remediation mapping** | `docs/10-domain/statespan-gap-remediation-mapping.md` | 12 gaps fully addressed, 8 partial, 27 unaffected |
| **Selective repo loading** | `docs/sdqctl-proposals/selective-repo-loading-proposal.md` | 40-60% token reduction, combined 60-80% |
| **REFCAT caching proposal** | `docs/sdqctl-proposals/refcat-caching-proposal.md` | 20-40% token reduction, 4-phase plan |
| **Bridge deprecation plan** | `docs/10-domain/bridge-deprecation-plan.md` | Full parity in nightscout-connect; archive Mar 31 |
| **PR adoption sequencing proposal** | `docs/10-domain/pr-adoption-sequencing-proposal.md` | 4-phase plan: Feb→Mar→Apr→Q2 |
| **High-value PR deep-dive** | `docs/10-domain/priority-pr-deep-dives.md` | Merge: #8419→#8083→#8261→#8421→#7791 |
| **Node.js LTS impact analysis** | `docs/10-domain/node-lts-upgrade-analysis.md` | All JS on EOL Node 16/14; target Node 22 |
| OQ-010 Extended API #7: eventType | `docs/10-domain/nocturne-eventtype-handling.md` | High parity, immutability gap |
| OQ-010 Extended API #6: V3 parity | `conformance/scenarios/nocturne-v3-parity/` | Missing history endpoint (GAP-SYNC-041) |
| OQ-010 Extended #16: Connector polling | `docs/10-domain/nocturne-connector-coordination.md` | Sidecar arch, loop-back risk |
| OQ-010 Extended #15: PostgreSQL migration | `mapping/nocturne/migration-field-fidelity.md` | Full field fidelity via typed+JSONB |
| OQ-010 Extended #14: StateSpan proposal | `statespan-standardization-proposal.md` | V3 extension recommended |
| OQ-010 Extended #13: Rust oref conformance | `conformance/scenarios/nocturne-oref/` | ✅ Verified equivalent to JS oref0 |
| OQ-010 Extended #12: SignalR bridge | `nocturne-signalr-bridge-analysis.md` | 5-10ms latency, full event parity |
| OQ-010 #11: ADR-004 ProfileSwitch | `adr-004-profile-override-mapping.md` | Dual-representation acceptance |
| OQ-010 #10: Rust oref profile | `nocturne-rust-oref-profile-analysis.md` | PredictionService bypasses ProfileService |
| OQ-010 #9: V4 extensions | `nocturne-v4-profile-extensions.md` | StateSpan API for profile history |
| OQ-010 #8: Override/TempTarget | `nocturne-override-temptarget-analysis.md` | No unified representation |
| OQ-010 #7: Profile sync comparison | `nocturne-cgm-remote-monitor-profile-sync.md` | Dedup/srvModified/delete differ |

---

## Completed Items

### ~~[P3] Token efficiency dashboard~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `tools/efficiency_dashboard.py`
**Key Finding:** 198 commits, +70K lines in 7 days, 39 tools
**Makefile:** `make efficiency-dashboard`

### ~~[P2] Mapping coverage tool~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `tools/verify_mapping_coverage.py`
**Key Finding:** 93 mapping files, 73-88% average coverage
**Makefile:** `make verify-mapping-coverage`

### ~~[P2] Gap freshness checker tool~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `tools/verify_gap_freshness.py`
**Key Finding:** 268 GAP definitions parsed, LIKELY_OPEN/NEEDS_REVIEW status
**Makefile:** `make verify-gap-freshness`

### ~~[P3] Terminology sample tool~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `tools/sample_terminology.py`
**Key Finding:** 354 terms in matrix, 90-100% verified against source
**Makefile:** `make verify-terminology`

### ~~[P2] Fix 26 duplicate GAP definitions~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** Removed/renumbered 26 duplicate GAP IDs
**Key Finding:** 265 unique GAP IDs after cleanup (was 255 with duplicates)
**Renumbered:** AUTH→006-007, DS→005-008, SESSION→004-006, SYNC→029-037

### ~~[P1] Gap deduplication tool~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `tools/find_gap_duplicates.py`
**Key Finding:** 26 duplicates across 255 unique GAP IDs
**Makefile:** `make verify-gap-duplicates`

### ~~[P2] Verify algorithm comparison claims~~ ✅ COMPLETE
**Completed:** 2026-01-29
**Deliverable:** `docs/sdqctl-proposals/backlogs/documentation-accuracy.md#11`
**Key Finding:** 100% accurate - 7 claims verified (oref0 arrays, AAPS Dynamic ISF, Loop RC)

### ~~[P2] Verify sync-identity mapping~~ ✅ COMPLETE
**Completed:** 2026-01-29
**Deliverable:** `docs/sdqctl-proposals/backlogs/documentation-accuracy.md#7`
**Key Finding:** 100% accurate - syncIdentifier, ObjectIdCache, 24h cache lifetime verified

### ~~[P2] API v3 pagination compliance~~ ✅ COMPLETE
**Completed:** 2026-01-29
**Deliverable:** `docs/10-domain/api-v3-pagination-compliance.md`
**Key Finding:** AAPS only client with full API v3; Loop/Trio use v1
**Gaps Added:** GAP-API-010, GAP-API-011, GAP-API-012

### ~~[P3] CGM trend arrow standardization~~ ✅ COMPLETE
**Completed:** 2026-01-29
**Deliverable:** `docs/10-domain/cgm-trend-arrow-standardization.md`
**Key Finding:** Nightscout string format is de facto interchange
**Gaps Added:** GAP-CGM-033, GAP-CGM-034

### ~~[P3] WebSocket event coverage~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `docs/10-domain/websocket-event-coverage.md`
**Key Finding:** APIv3 /storage channel doesn't capture v1 API changes
**Gaps Added:** GAP-API-013, GAP-API-014, GAP-API-015

### ~~[P2] Libre 3 protocol gap analysis~~ ✅ COMPLETE
**Completed:** 2026-01-29
**Deliverable:** `docs/10-domain/libre3-protocol-gap-analysis.md`
**Key Finding:** ECDH encryption blocks direct BLE; only LibreLinkUp API (1-5 min delay)
**Gaps Added:** GAP-CGM-030, GAP-CGM-031, GAP-CGM-032

### ~~[P2] Cross-controller conflict detection~~ ✅ COMPLETE
**Completed:** 2026-01-29
**Deliverable:** `docs/10-domain/cross-controller-conflicts-deep-dive.md`
**Key Finding:** Distinct namespaces (loop vs openaps) prevent collision; enteredBy distinguishes controllers
**Gaps Added:** GAP-SYNC-020, GAP-SYNC-030, GAP-SYNC-031

### ~~[P2] Profile switch sync~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `docs/10-domain/profile-switch-sync-comparison.md`
**Key Finding:** AAPS uses `Profile Switch` treatments; Loop/Trio upload to `profile` collection only
**Gaps Added:** GAP-SYNC-035 to GAP-SYNC-037

### ~~[P2] Basal schedule comparison~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `docs/10-domain/basal-schedule-comparison.md`
**Key Finding:** Time format: "HH:MM" (NS) vs seconds (Loop/AAPS) vs minutes (oref0)
**Gaps Added:** GAP-PROF-006 to GAP-PROF-008, GAP-SYNC-020

### ~~[P2] Override/temporary target sync~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `docs/10-domain/override-temp-target-sync-comparison.md`
**Key Finding:** Loop Override vs AAPS Temporary Target - different eventTypes
**Gaps Added:** GAP-OVRD-001 to GAP-OVRD-004

### ~~[P2] Target range handling comparison~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `docs/10-domain/target-range-handling-comparison.md`
**Key Finding:** Loop dynamic targeting vs oref0 static midpoint
**Gaps Added:** GAP-TGT-001 to GAP-TGT-004

### ~~[P2] Insulin model comparison~~ ✅ COMPLETE
**Completed:** 2026-01-30
**Deliverable:** `docs/10-domain/insulin-model-comparison.md`
**Key Finding:** Loop and oref0 use identical exponential formula (Loop issue #388)
**Gaps Added:** GAP-INS-005 to GAP-INS-008

### ~~[P2] Temp basal vs SMB dosing comparison~~ ✅ COMPLETE
**Status:** Completed 2026-01-30
- Deep dive: `docs/10-domain/temp-basal-vs-smb-comparison.md` (10.4KB)
- Compared Loop temp basal/auto bolus vs oref0 SMB micro-dosing
- 4 gaps identified: GAP-DOSE-001/002/003/004
- 3 requirements added: REQ-DOSE-001/002/003
- Key finding: SMB 3min/50% vs Loop 5min/40%; different safety mechanisms

### ~~[P2] Prediction curve documentation~~ ✅ COMPLETE
**Status:** Completed 2026-01-30
- Deep dive: `docs/10-domain/prediction-curve-documentation.md` (11.7KB)
- Compared Loop single curve vs oref0 4 curves (IOB, COB, UAM, ZT)
- 4 gaps identified: GAP-PRED-001/002/003/004
- 3 requirements added: REQ-PRED-001/002/003
- Key finding: Loop sums effects; oref0 shows separate scenarios

### ~~[P2] Carb absorption model comparison~~ ✅ COMPLETE
**Status:** Completed 2026-01-30
- Deep dive: `docs/10-domain/carb-absorption-model-comparison.md` (9.8KB)
- Compared Loop model-based vs oref0 deviation-based absorption
- 4 gaps identified: GAP-CARB-001/002/003/004
- 3 requirements added: REQ-CARB-001/002/003
- Key finding: Loop uses curves; oref0 uses min_5m_carbimpact + UAM

### ~~[P2] Autosens/Dynamic ISF comparison~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Deep dive: `docs/10-domain/autosens-dynamic-isf-comparison.md` (9.4KB)
- Compared sensitivity algorithms: Autosens vs Retrospective Correction
- 4 gaps identified: GAP-SENS-001/002/003/004
- 3 requirements added: REQ-SENS-001/002/003
- Key finding: Ratio output (0.7-1.3) vs glucose effect; 8-24h vs 30-180min windows

### ~~[P2] Bolus wizard formula comparison~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Deep dive: `docs/10-domain/bolus-wizard-formula-comparison.md` (10.4KB)
- Compared AAPS arithmetic vs Loop prediction-based formulas
- 4 gaps identified: GAP-BOLUS-001/002/003/004
- 3 requirements added: REQ-BOLUS-001/002/003
- Key finding: Loop uses prediction curve; AAPS has SuperBolus, % scaling

### ~~[P2] Profile schema alignment~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Deep dive: `docs/10-domain/profile-schema-alignment.md` (11.6KB)
- Compared profile/therapy settings across Loop, AAPS, Trio, Nightscout
- 5 gaps identified: GAP-PROF-001/002/003/004/005
- 4 requirements added: REQ-PROF-001/002/003/004
- Key finding: Time format mismatch, missing safety limits in Nightscout

### ~~[P2] Nightscout devicestatus schema audit~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Deep dive: `docs/10-domain/nightscout-devicestatus-schema-audit.md` (9.2KB)
- Compared Loop `status.loop` vs oref0 `status.openaps` structures
- 4 gaps identified: GAP-DS-001/002/003/004
- 4 requirements added: REQ-DS-001/002/003/004
- Key finding: Incompatible prediction formats (single vs 4 curves)

### ~~[P2] Sync identity field audit~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Deep dive: `docs/10-domain/sync-identity-field-audit.md` (9.6KB)
- Audited 5 systems: Nightscout, Loop, Trio, AAPS, xDrip+
- 3 gaps identified: GAP-SYNC-032/024/025
- Key finding: Only AAPS properly stores nightscoutId

### ~~[P2] API v3 pagination compliance~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Deep dive: `docs/10-domain/api-v3-pagination-compliance.md` (9.3KB)
- Key finding: Only AAPS uses v3; Loop/Trio/xDrip+ use v1
- 3 gaps identified: GAP-API-010/011/012

### ~~[P2] CGM trend arrow standardization~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Deep dive: `docs/10-domain/cgm-trend-arrow-standardization.md` (9.6KB)
- Mapped 7 projects to unified enum
- 2 gaps identified: GAP-CGM-033 (AAPS triple), GAP-CGM-034 (Libre granularity)

### ~~[P3] sdqctl VERIFY .conv Directive (Phase 2)~~ ✅ ENHANCED
**Status:** Enhanced 2026-01-29
- Proposal: [VERIFICATION-DIRECTIVES.md](VERIFICATION-DIRECTIVES.md) (+171 lines)
- Added 5 real-world usage patterns from 31-item verification
- Added lessons learned, implementation priority (P1/P2/P3)
- Clear request for sdqctl team: parser support for VERIFY directive

### ~~[P2] Level 6: nocturne-modernization-analysis.md coherence~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Coherence: **83%** (10/12 claims verified)
- Exact: 927 C# files, 438 Svelte, PostgreSQL, Aspire, SignalR, Rust oref
- Close: LOC 84%, Connectors 11 vs 8
- Unverified: Redis, V4 endpoints
- **LEVEL 6 COMPLETE (4/4)**

### ~~[P3] Level 6: lsp-integration-proposal.md coherence~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Coherence: **40%** - Proposal is forward-looking (describes what to build)
- Phase 1 partial: verify_refs.py has line anchor parsing
- Not implemented: lsp_query.py, LSP integrations, symbol verification

### ~~[P2] Level 6: statistics-api-proposal.md coherence~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Coherence: **100%** - All 5 REQ-STATS-* requirements addressed
- 4 endpoints defined with full schemas
- MCP integration included (Phase 3)

### ~~[P2] Level 6: algorithm-conformance-suite.md coherence~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- Coherence: **80%** - Phases 1-2 done, 3-5 correctly marked pending
- oref0-runner.js exists (13KB), 85 vectors, 30.6% pass rate
- Minor issue: file tree shows future runners as existing

### ~~[P2] Level 5: REQ-API-* OpenAPI alignment~~ ✅ COMPLETE
**Status:** Completed 2026-01-29 - **LEVEL 5 COMPLETE!**
- 35 requirements audited, **63% have OpenAPI spec** (22/35)
- Covered: REQ-API/API3/SPEC/PLUGIN/ERR/NS-* via 8 specs
- Gaps: REQ-STATS-* (5), REQ-AUTH-* (3), REQ-RG-* (4)

### ~~[P2] Level 5: REQ-CONNECT-* completeness~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 28 GAPs audited, **100% have REQs** (28/28)
- Perfect 1:1 GAP→REQ mapping across all 8 connector categories
- No orphaned gaps

### ~~[P2] Level 5: REQ-TREAT-* traceability~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 7 requirements audited, **100% covered** (7/7)
- All via treatment-sync.yaml: REQ-TREAT-040 to REQ-TREAT-046
- Related gaps: REQ-REMOTE-* (0%), REQ-ALARM-* (0%), REQ-UNIT-* (0%)

### ~~[P2] Level 5: REQ-SYNC-* traceability~~ ✅ COMPLETE
**Status:** Completed 2026-01-29
- 18 requirements audited, **83% covered** (15/18)
- Covered: REQ-SYNC-036 to REQ-SYNC-050 via sync-deduplication.yaml
- Uncovered: REQ-SYNC-001 (docs), REQ-SYNC-002 (v1/v3), REQ-SYNC-003 (status)

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
