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

### 1. [P2] Algorithm conformance: Schema + fixture extraction
**Type:** Implementation | **Effort:** Medium
**Repos:** AAPS, oref0
**Focus:** Phase 1 of conformance suite - JSON schema + 50 vectors from AAPS
**Workflow:** `extract-spec.conv`
**Note:** Follow-on from algorithm-conformance-suite.md proposal

### 2. [P2] Deep dive: Authentication flows
**Type:** Analysis | **Effort:** Medium
**Repos:** cgm-remote-monitor
**Focus:** API secret vs tokens vs JWT comparison
**Workflow:** `gap-discovery.conv`

### 3. [P2] Cross-repo fixture extraction
**Type:** Implementation | **Effort:** Medium
**Repos:** AAPS, Loop, xDrip+
**Focus:** Pull test fixtures for integration testing
**Workflow:** `extract-spec.conv`

### 4. [P2] Nightscout APIv3 Collection deep dive
**Type:** Analysis | **Effort:** Medium
**Repos:** cgm-remote-monitor
**Focus:** Document all APIv3 collections, operations, authorization
**Workflow:** `gap-discovery.conv`

### 5. [P2] Device Status collection deep dive
**Type:** Analysis | **Effort:** Medium
**Repos:** cgm-remote-monitor, AAPS, Loop
**Focus:** Document devicestatus structure differences between controllers
**Workflow:** `gap-discovery.conv`

---

## Backlog (Prioritized)

### P0 - Critical

- [x] ~~**cgm-remote-monitor audit**~~ (chunked, using bewest/mongo-5x branch) - ✅ **COMPLETE**
  - [x] ~~Database layer (MongoDB 5.x compat, indexes, schema)~~ - ✅ Completed (455 lines, 3 gaps)
  - [x] ~~API layer (lib/api3/, v1/v2/v3 endpoints, collections)~~ - ✅ Completed (397 lines, 3 gaps)
  - [x] ~~Plugin system (lib/plugins/, 38 plugins, reports)~~ - ✅ Completed (436 lines, 3 gaps)
  - [x] ~~Sync/upload logic (lib/server/, socket.io, data flow)~~ - ✅ Completed (520 lines, 3 gaps)
  - [x] ~~Authentication (lib/authorization/, tokens, roles)~~ - ✅ Completed (475 lines, 3 gaps)
  - [x] ~~Frontend (views/, translations/, client bundles)~~ - ✅ Completed (468 lines, 3 gaps)
  - **Total: 2,751 lines, 18 gaps across 6 deep dives**

### P1 - High Value

- [ ] **PR analysis: cgm-remote-monitor** - Review open PRs for ecosystem impact
- [x] ~~**PR analysis: share2nightscout-bridge**~~ - Completed (242 lines, 3 gaps)
- [x] ~~**Deep dive: Batch operation ordering**~~ - Completed
- [x] ~~**Gap discovery: Prediction array formats**~~ - Completed (319 lines, 3 gaps)
- [x] ~~**Full audit: openaps**~~ - Completed (371 lines, 3 gaps)
- [x] ~~**Algorithm conformance suite**~~ - Proposal created (400+ lines, 3 gaps, 5-phase plan)
- [x] ~~**Full audit: tconnectsync**~~ - Completed (368 lines, 3 gaps)
- [x] ~~**Full audit: nightscout-librelink-up**~~ - Completed (378 lines, 3 gaps)
- [x] ~~**Cross-project testing plan (Trio/Loop on Ubuntu)**~~ - Completed (363 lines, 3 gaps)
- [ ] **Statistics API proposal** - MCP-informed stats endpoints for Nightscout
  - From: LIVE-BACKLOG request
  - Focus: Aggregate endpoints based on reports + zreptil nightscout-reporter needs

### P2 - Normal

- [x] ~~**Compare carb absorption models**~~ - ✅ Completed (471 lines, 3 gaps)
- [x] ~~**Extract Loop sync identity fields**~~ - ✅ Completed (318 lines, 3 gaps)
- [ ] **Algorithm conformance: Schema + fixture extraction** - Phase 1 of conformance suite
  - From: Algorithm conformance suite proposal
  - Deliverables: `conformance-vector-v1.json` schema, 50+ vectors from AAPS
- [ ] **Algorithm conformance: oref0 runner** - Phase 2 of conformance suite
  - From: Algorithm conformance suite proposal
  - Deliverables: `conformance/runners/oref0-runner.js`, Makefile target
- [x] ~~**Map pump communication terminology**~~ - ✅ Completed (~150 lines, 10 tables)
- [x] ~~**Deep dive: Authentication flows**~~ - Promoted to Ready Queue #5
- [x] ~~**Cross-repo fixture extraction**~~ - Promoted to Ready Queue #5
- [x] ~~**Full audit: nightscout-connect**~~ - ✅ Completed (527 lines, 3 gaps)
- [x] ~~**nightscout-connect vendor interop proposal**~~ - ✅ Completed (418 lines, 3 reqs)
- [ ] **Documentation reorganization proposal** - AI vs human comprehension analysis
  - From: LIVE-BACKLOG request
  - Focus: Consolidate duplicate materials, optimize structure for tooling vs projects
- [ ] **Chunk gaps.md into manageable pieces** - Split by domain category
  - From: LIVE-BACKLOG request
  - Focus: CGM, Treatments, Sync, Override, Database, etc.
- [ ] **Large file analysis + chunking proposal** - Identify files hard to reason about
  - From: LIVE-BACKLOG request
  - Focus: Files >500 lines, autonomous workflow optimization

### P3 - Nice to Have

- [ ] **Compare CGM sensor session handling** - Start, stop, calibration
- [ ] **Extract xDrip+ Nightscout fields** - What xDrip+ uploads
- [ ] **Map algorithm terminology** - ISF, CR, DIA, UAM across systems
- [ ] **LSP-based documentation claim verification** - See [tooling backlog](backlogs/tooling.md)
- [ ] **Reporting needs analysis** - Compare nightscout-reporter vs built-in reports
  - Source: `externals/nightscout-reporter/` (zreptil)
  - Focus: Report types, data requirements, export formats, user needs
- [ ] **Full audit: nightscout-roles-gateway** - OAuth 2.0 RBAC controller, 39 lines documented
  - Components: lib/, migrations/, Ory Hydra/Kratos integration
  - Focus: Role-based access control, OAuth flows, API authorization
  - Workflow: `gap-discovery.conv`
- [x] ~~**Playwright adoption proposal for cgm-remote-monitor**~~ - Promoted to Ready Queue #5
- [ ] **sdqctl tools vs custom py tools proposal** - Evaluate tooling consolidation
  - From: LIVE-BACKLOG request
  - Focus: Compare sdqctl capabilities vs tools/*.py, deprecation candidates

---

## Completed

| Date | Item | Outcome |
|------|------|---------|
| 2026-01-29 | Heart Rate API specification | `specs/openapi/aid-heartrate-2025.yaml` - 447 lines, GAP-API-HR addressed, 6 endpoints, AAPS entity mapping |
| 2026-01-29 | Statistics API proposal | `docs/sdqctl-proposals/statistics-api-proposal.md` - 480 lines, 3 gaps (GAP-STATS-001-003), 5 reqs (REQ-STATS-001-005), 6 endpoints, MCP resources |
| 2026-01-29 | PR analysis: cgm-remote-monitor | `docs/10-domain/cgm-remote-monitor-pr-analysis.md` - 380 lines, 4 gaps (GAP-API-HR, GAP-INSULIN-001, GAP-REMOTE-CMD, GAP-TZ-001), 68 PRs categorized, Tier 1 ecosystem PRs identified |
| 2026-01-29 | nightscout-connect vendor interop proposal | `docs/sdqctl-proposals/nightscout-connect-vendor-interop.md` - 418 lines, 3 reqs (REQ-BRIDGE-001-003), v3 API, sync identity |
| 2026-01-29 | Map pump communication terminology | `mapping/cross-project/terminology-matrix.md` - ~150 lines, 10 tables, pump states/bolus/reservoir |
| 2026-01-29 | Compare carb absorption models | `docs/10-domain/carb-absorption-comparison.md` - 471 lines, 3 gaps (GAP-CARB-001-003), Loop vs oref0 paradigms |
| 2026-01-29 | Full audit: nightscout-connect | `docs/10-domain/nightscout-connect-deep-dive.md` - 527 lines, 3 gaps (GAP-CONNECT-001-003), XState machines, 5 sources |
| 2026-01-29 | Interoperability Spec v1 | `specs/interoperability-spec-v1.md` - 316 lines, 3 reqs (REQ-INTEROP-001-003), RFC-style MUST/SHOULD/MAY, synthesizes 6 audits |
| 2026-01-29 | cgm-remote-monitor Frontend audit | `docs/10-domain/cgm-remote-monitor-frontend-deep-dive.md` - 468 lines, 3 gaps (GAP-UI-001-003), D3, plugins, i18n |
| 2026-01-29 | cgm-remote-monitor Authentication audit | `docs/10-domain/cgm-remote-monitor-auth-deep-dive.md` - 475 lines, 3 gaps (GAP-AUTH-003-005), Shiro, JWT, roles |
| 2026-01-29 | cgm-remote-monitor Sync/upload audit | `docs/10-domain/cgm-remote-monitor-sync-deep-dive.md` - 520 lines, 3 gaps (GAP-SYNC-008-010), WebSocket, sync identity |
| 2026-01-29 | cgm-remote-monitor Plugin system audit | `docs/10-domain/cgm-remote-monitor-plugin-deep-dive.md` - 436 lines, 3 gaps (GAP-PLUGIN-001-003), IOB/COB, Loop/OpenAPS |
| 2026-01-29 | cgm-remote-monitor API layer audit | `docs/10-domain/cgm-remote-monitor-api-deep-dive.md` - 397 lines, 3 gaps (GAP-API-006-008), dedup keys, Socket.IO |
| 2026-01-29 | Algorithm conformance suite proposal | `docs/sdqctl-proposals/algorithm-conformance-suite.md` - 400+ lines, 3 gaps (GAP-ALG-001-003), test vector schema, 5-phase plan |
| 2026-01-29 | PR analysis: share2nightscout-bridge | `docs/10-domain/share2nightscout-bridge-pr-analysis.md` - 242 lines, 3 gaps (GAP-BRIDGE-001-003), 1 PR, 13 issues |
| 2026-01-29 | Cross-project testing plan | `docs/sdqctl-proposals/cross-project-testing-plan.md` - 363 lines, 3 gaps (GAP-TEST-001-003), 4 strategies |
| 2026-01-29 | Compare override/profile switch semantics | `docs/10-domain/override-profile-switch-comparison.md` - 416 lines, 3 gaps (GAP-OVERRIDE-005-007), Trio Exercise eventType |
| 2026-01-29 | Playwright adoption proposal | `docs/sdqctl-proposals/playwright-adoption-proposal.md` - 316 lines, 4-phase plan, ~5-8 days effort |
| 2026-01-29 | cgm-remote-monitor database layer audit | `docs/10-domain/cgm-remote-monitor-database-deep-dive.md` - 455 lines, 3 gaps (GAP-DB-001-003), Loop ordering verified |
| 2026-01-29 | Extract Loop sync identity fields | `mapping/loop/sync-identity-fields.md` - 318 lines, 3 gaps (GAP-SYNC-005-007), ObjectIdCache pattern |
| 2026-01-29 | Full audit: nightscout-librelink-up | `docs/10-domain/nightscout-librelink-up-deep-dive.md` - 378 lines, 3 gaps (GAP-LIBRELINK-001-003) |
| 2026-01-29 | Full audit: tconnectsync | `docs/10-domain/tconnectsync-deep-dive.md` - 368 lines, 3 gaps (GAP-TCONNECT-001-003) |
| 2026-01-29 | Full audit: openaps/oref0 | `docs/10-domain/openaps-oref0-deep-dive.md` - 371 lines, 3 gaps (GAP-OREF-001-003) |
| 2026-01-28 | Gap discovery: Prediction array formats | `docs/10-domain/prediction-arrays-comparison.md` - 319 lines, 3 gaps (GAP-PRED-002-004) |
| 2026-01-28 | Deep dive: Batch operation ordering | `docs/10-domain/batch-ordering-deep-dive.md` - 334 lines, 3 requirements |
| 2026-01-28 | Compare override/profile switch semantics | `docs/10-domain/override-profile-switch-comparison.md` - 331 lines, 4 new gaps |
| 2026-01-28 | Compare remote bolus command handling | `docs/10-domain/remote-bolus-comparison.md` - 348 lines, 4 systems, 2 new gaps |
| 2026-01-28 | Extract Nightscout v3 treatments schema | `mapping/nightscout/v3-treatments-schema.md` - 248 lines, 21+ eventTypes |
| 2026-01-28 | Modernization analysis: cgm-remote-monitor vs Nocturne | `docs/sdqctl-proposals/nocturne-modernization-analysis.md` - 350 lines, full comparison |
| 2026-01-28 | Initial audit: share2nightscout-bridge | `docs/10-domain/share2nightscout-bridge-deep-dive.md` - 328 lines, 3 gaps (GAP-SHARE-001-003) |
| 2026-01-28 | Initial audit: nocturne | `docs/10-domain/nocturne-deep-dive.md` - 279 lines, 3 gaps (GAP-NOCTURNE-001-003) |
| 2026-01-28 | Extract AAPS NSClient upload schema | `mapping/aaps/nsclient-schema.md` - 70+ fields, 25 eventTypes |
| 2026-01-28 | Workspace expansion (4 repos) | nocturne, Trio-dev, share2nightscout-bridge, cgm-remote-monitor-official added |
| 2026-01-28 | Cross-project test harness tooling | `test_conversions.py` (20 tests), `mock_nightscout.py` (API v1/v3), Makefile targets |
| 2026-01-28 | Map timezone/DST handling terminology | +150 lines terminology matrix, 4 new gaps (GAP-TZ-004-007), pump DST handling documented |

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
