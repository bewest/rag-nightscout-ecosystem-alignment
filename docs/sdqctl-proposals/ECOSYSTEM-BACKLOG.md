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

### 2. [P2] Transform pipeline tester
**Type:** Implementation | **Effort:** High
**Repos:** Cross-project
**Focus:** Test field transforms in isolation (time/glucose/insulin)
**Workflow:** `implementation.conv`
**Source:** tooling backlog

### 3. [P2] LSP-based claim verification
**Type:** Implementation | **Effort:** Medium
**Repos:** Cross-project
**Focus:** Implement phase 1-2 of lsp-integration-proposal.md
**Workflow:** `implementation.conv`
**Source:** tooling backlog

### 4. [P3] Algorithm conformance: Loop Swift runner
**Type:** Implementation | **Effort:** High
**Repos:** LoopWorkspace
**Focus:** Swift-based runner for Loop algorithm testing
**Workflow:** `extract-spec.conv`
**Note:** Required for Loop conformance per GAP-ALG-013

### 5. [P3] Integration test runner
**Type:** Implementation | **Effort:** High
**Repos:** Cross-project
**Focus:** Orchestrate full cross-project conformance tests
**Workflow:** `implementation.conv`
**Source:** tooling backlog

---

## Completed Items

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

- [x] ~~**Hygiene tooling suite**~~ - ✅ **COMPLETE** (queue_stats.py, backlog_hygiene.py, doc_chunker.py)
- [x] ~~**cgm-remote-monitor audit**~~ (chunked, using bewest/mongo-5x branch) - ✅ **COMPLETE**
  - [x] ~~Database layer (MongoDB 5.x compat, indexes, schema)~~ - ✅ Completed (455 lines, 3 gaps)
  - [x] ~~API layer (lib/api3/, v1/v2/v3 endpoints, collections)~~ - ✅ Completed (397 lines, 3 gaps)
  - [x] ~~Plugin system (lib/plugins/, 38 plugins, reports)~~ - ✅ Completed (436 lines, 3 gaps)
  - [x] ~~Sync/upload logic (lib/server/, socket.io, data flow)~~ - ✅ Completed (520 lines, 3 gaps)
  - [x] ~~Authentication (lib/authorization/, tokens, roles)~~ - ✅ Completed (475 lines, 3 gaps)
  - [x] ~~Frontend (views/, translations/, client bundles)~~ - ✅ Completed (468 lines, 3 gaps)
  - **Total: 2,751 lines, 18 gaps across 6 deep dives**

### P1 - High Value

- [x] ~~**PR analysis: cgm-remote-monitor**~~ - ✅ **COMPLETE** (388 lines, 68 PRs analyzed)
- [x] ~~**PR analysis: share2nightscout-bridge**~~ - Completed (242 lines, 3 gaps)
- [x] ~~**Deep dive: Batch operation ordering**~~ - Completed
- [x] ~~**Gap discovery: Prediction array formats**~~ - Completed (319 lines, 3 gaps)
- [x] ~~**Full audit: openaps**~~ - Completed (371 lines, 3 gaps)
- [x] ~~**Algorithm conformance suite**~~ - Proposal created (400+ lines, 3 gaps, 5-phase plan)
- [x] ~~**Full audit: tconnectsync**~~ - Completed (368 lines, 3 gaps)
- [x] ~~**Full audit: nightscout-librelink-up**~~ - Completed (378 lines, 3 gaps)
- [x] ~~**Cross-project testing plan (Trio/Loop on Ubuntu)**~~ - Completed (363 lines, 3 gaps)
- [x] ~~**Statistics API proposal**~~ - ✅ Completed (480 lines, 6 endpoints, MCP resources)
  - From: LIVE-BACKLOG request
  - Focus: Aggregate endpoints based on reports + zreptil nightscout-reporter needs

### P2 - Normal

- [x] ~~**Compare carb absorption models**~~ - ✅ Completed (471 lines, 3 gaps)
- [x] ~~**Extract Loop sync identity fields**~~ - ✅ Completed (318 lines, 3 gaps)
- [x] ~~**Algorithm conformance: Schema + fixture extraction**~~ - ✅ Completed (85 vectors)
  - From: Algorithm conformance suite proposal
  - Deliverables: `conformance-vector-v1.json` schema, 85 vectors from AAPS
- [x] ~~**Algorithm conformance: oref0 runner**~~ - ✅ Completed (26/85 pass, 69% divergence)
  - From: Algorithm conformance suite proposal
  - Deliverables: `conformance/runners/oref0-runner.js`, Makefile target
- [x] ~~**Map pump communication terminology**~~ - ✅ Completed (~150 lines, 10 tables)
- [x] ~~**Deep dive: Authentication flows**~~ - Promoted to Ready Queue #5
- [x] ~~**Cross-repo fixture extraction**~~ - Promoted to Ready Queue #5
- [x] ~~**Full audit: nightscout-connect**~~ - ✅ Completed (527 lines, 3 gaps)
- [x] ~~**nightscout-connect vendor interop proposal**~~ - ✅ Completed (418 lines, 3 reqs)
- [x] ~~**Documentation reorganization proposal**~~ - ✅ Complete (223 lines)
  - From: LIVE-BACKLOG request
  - Focus: Consolidate duplicate materials, optimize structure for tooling vs projects
- [x] ~~**Chunk gaps.md into manageable pieces**~~ - ✅ Completed (index + 7 domain files)
  - From: LIVE-BACKLOG request
  - Focus: CGM, Treatments, Sync, Override, Database, etc.
- [x] ~~**Large file analysis + chunking proposal**~~ - ✅ Complete (174 lines, no chunking needed)
  - From: LIVE-BACKLOG request
  - Focus: Files >500 lines, autonomous workflow optimization

### P3 - Nice to Have

- [x] ~~**Create mapping: nocturne**~~ - ✅ **COMPLETE** (702 lines, 4 docs, 3 gaps)
- [x] ~~**Create mapping: tconnectsync**~~ - ✅ **COMPLETE** (607 lines, 4 docs, 1 gap)
- [x] ~~**Create mapping: share2nightscout-bridge**~~ - Promoted to Ready Queue #5
- [x] ~~**Create mapping: nightscout-librelink-up**~~ - Promoted to Ready Queue #5
- [x] ~~**Deep dive: LoopFollow**~~ - Promoted to Ready Queue #5
- [x] ~~**Deep dive: LoopCaregiver**~~ - Promoted to Ready Queue #5
- [x] ~~**Deep dive: openaps toolkit**~~ - Promoted to Ready Queue #5
- [ ] **Deep dive: xdrip-js**
  - Repos: xdrip-js
  - Focus: Node.js Dexcom G5/G6 BLE interface
  - Context: Raspberry Pi CGM receiver use case
  - Workflow: `extract-spec.conv`
- [ ] **Generate requirements: connectors domain**
  - Focus: Extract REQs from 15 GAP-CONNECT-* entries
  - Context: Connectors domain has 15 gaps, 0 requirements
  - Workflow: `gap-discovery.conv`
- [x] ~~**Compare CGM sensor session handling**~~ - ✅ Complete (353 lines, 3 gaps)
- [x] ~~**Extract xDrip+ Nightscout fields**~~ - ✅ Already complete (506 lines in mapping/xdrip-android/nightscout-sync.md)
- [x] ~~**Map algorithm terminology**~~ - ✅ Already complete (3024-line matrix)
- [x] ~~**LSP-based documentation claim verification**~~ - ✅ **COMPLETE** (verify_refs.py exists, fixed 3 refs, 92% valid)
- [x] ~~**Reporting needs analysis**~~ - ✅ Complete (250 lines, 3 gaps)
  - Source: `externals/nightscout-reporter/` (zreptil)
  - Focus: Report types, data requirements, export formats, user needs
- [x] ~~**Full audit: nightscout-roles-gateway**~~ - ✅ **COMPLETE** (260 lines existing, 1 gap, 4 reqs migrated)
  - Components: lib/, migrations/, Ory Hydra/Kratos integration
  - Focus: Role-based access control, OAuth flows, API authorization
  - Workflow: `gap-discovery.conv`
- [x] ~~**Playwright adoption proposal for cgm-remote-monitor**~~ - Promoted to Ready Queue #5
- [x] ~~**sdqctl tools vs custom py tools proposal**~~ - ✅ **COMPLETE** (140 lines, 4 deprecate, 3 integrate, 23 keep)
  - From: LIVE-BACKLOG request
  - Focus: Compare sdqctl capabilities vs tools/*.py, deprecation candidates

---

## Completed (Recent)

*Older items archived to [`archive/2026-01-backlog-archive.md`](archive/2026-01-backlog-archive.md)*

| Date | Item | Outcome |
|------|------|---------|
| 2026-01-29 | Hygiene: Chunk progress.md | 1713→807 lines, archive created |
| 2026-01-29 | Algorithm conformance: oref0 runner | `oref0-runner.js` - 400+ lines, 26/85 pass |
| 2026-01-29 | Algorithm conformance: Schema + fixture extraction | 85 vectors, schema, extraction script |
| 2026-01-29 | Heart Rate API specification | `aid-heartrate-2025.yaml` - 447 lines |
| 2026-01-29 | Statistics API proposal | 480 lines, 3 gaps, 5 reqs |
| 2026-01-29 | PR analysis: cgm-remote-monitor | 380 lines, 68 PRs |
| 2026-01-29 | Interoperability Spec v1 | RFC-style, synthesizes 6 audits |
| 2026-01-29 | cgm-remote-monitor 6-layer audit | 2,751 lines total, 18 gaps |
| 2026-01-29 | Cross-project testing plan | 4 strategies for Swift on Linux |
| 2026-01-29 | Playwright adoption proposal | 4-phase E2E testing plan |

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
