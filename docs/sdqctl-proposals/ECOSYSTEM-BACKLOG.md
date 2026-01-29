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

### 1. [P2] Nightscout APIv3 Collection deep dive
**Type:** Analysis | **Effort:** Medium
**Repos:** cgm-remote-monitor
**Focus:** Document all APIv3 collections, operations, authorization
**Workflow:** `gap-discovery.conv`

### 2. [P2] Device Status collection deep dive
**Type:** Analysis | **Effort:** Medium
**Repos:** cgm-remote-monitor, AAPS, Loop
**Focus:** Document devicestatus structure differences between controllers
**Workflow:** `gap-discovery.conv`

### 3. [P2] Profile collection deep dive
**Type:** Analysis | **Effort:** Medium
**Repos:** cgm-remote-monitor, AAPS, Loop, Trio
**Focus:** Document profile structure and sync patterns
**Workflow:** `gap-discovery.conv`

### 4. [P2] Algorithm conformance: AAPS Kotlin runner
**Type:** Implementation | **Effort:** High
**Repos:** AndroidAPS
**Focus:** Phase 3 of conformance suite - Kotlin runner for AAPS
**Workflow:** `extract-spec.conv`
**Note:** Follow-on from oref0 runner (complete)

### 5. [P3] Map algorithm terminology
**Type:** Documentation | **Effort:** Low
**Focus:** ISF, CR, DIA, UAM across oref0/AAPS/Loop/Trio
**Workflow:** `terminology-sync.conv`

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
- [x] ~~**Algorithm conformance: Schema + fixture extraction**~~ - ✅ Completed (85 vectors)
  - From: Algorithm conformance suite proposal
  - Deliverables: `conformance-vector-v1.json` schema, 85 vectors from AAPS
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
