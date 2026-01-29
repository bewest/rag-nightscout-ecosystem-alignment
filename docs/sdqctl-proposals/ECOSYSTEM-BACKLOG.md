# Ecosystem Alignment Backlog

> **Last Updated**: 2026-01-28  
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

### 1. [P1] Interoperability spec draft
**Type:** Specification | **Effort:** Medium
**Repos:** All
**Focus:** Define minimal viable interoperability spec (OQ-021)
**Workflow:** `extract-spec.conv`

### 2. [P1] PR analysis: cgm-remote-monitor
**Type:** Analysis | **Effort:** Medium
**Source:** `externals/cgm-remote-monitor-official/`
**Focus:** Review open PRs for ecosystem impact
**Workflow:** `gap-discovery.conv`

### 3. [P1] Cross-project testing plan
**Type:** Tooling | **Effort:** Low
**Repos:** Trio, Loop
**Focus:** Define Ubuntu-compatible testing strategies for Swift AID projects
**Workflow:** `tools/`

### 4. [P1] Statistics API proposal
**Type:** Specification | **Effort:** Medium
**Repos:** cgm-remote-monitor
**Focus:** MCP-informed aggregate endpoints based on reports + zreptil needs
**Workflow:** `extract-spec.conv`

### 5. [P2] Algorithm conformance suite
**Type:** Tooling | **Effort:** Medium
**Focus:** Create test vectors for Rust vs JS oref comparison
**Workflow:** `tools/`

---

## Backlog (Prioritized)

### P0 - Critical

- [ ] **cgm-remote-monitor audit** (chunked, using bewest/mongo-5x branch)
  - [x] ~~Database layer (MongoDB 5.x compat, indexes, schema)~~ - ✅ Completed (455 lines, 3 gaps)
  - [ ] API layer (lib/api3/, v1/v2/v3 endpoints, collections)
  - [ ] Plugin system (lib/plugins/, 38 plugins, reports)
  - [ ] Sync/upload logic (lib/server/, socket.io, data flow)
  - [ ] Authentication (lib/authorization/, tokens, roles)
  - [ ] Frontend (views/, translations/, client bundles)

### P1 - High Value

- [ ] **PR analysis: cgm-remote-monitor** - Review open PRs for ecosystem impact
- [ ] **PR analysis: share2nightscout-bridge** - Review open PRs
- [x] ~~**Deep dive: Batch operation ordering**~~ - Completed
- [x] ~~**Gap discovery: Prediction array formats**~~ - Completed (319 lines, 3 gaps)
- [x] ~~**Full audit: openaps**~~ - Completed (371 lines, 3 gaps)
- [ ] **Algorithm conformance suite** - Create test vectors for Rust vs JS oref comparison
  - From: Modernization analysis next steps
- [x] ~~**Full audit: tconnectsync**~~ - Completed (368 lines, 3 gaps)
- [x] ~~**Full audit: nightscout-librelink-up**~~ - Completed (378 lines, 3 gaps)
- [ ] **Cross-project testing plan (Trio/Loop on Ubuntu)** - System requirements for iOS dev/test
  - From: LIVE-BACKLOG request
  - Focus: Define Ubuntu-compatible testing strategies for Swift projects
- [ ] **Statistics API proposal** - MCP-informed stats endpoints for Nightscout
  - From: LIVE-BACKLOG request
  - Focus: Aggregate endpoints based on reports + zreptil nightscout-reporter needs

### P2 - Normal

- [ ] **Compare carb absorption models** - Linear vs nonlinear vs dynamic
- [x] ~~**Extract Loop sync identity fields**~~ - ✅ Completed (318 lines, 3 gaps)
- [ ] **Map pump communication terminology** - Reservoir, cartridge, pod, etc.
- [ ] **Deep dive: Authentication flows** - API secret vs tokens vs JWT
- [ ] **Cross-repo fixture extraction** - Pull test fixtures from AAPS/Loop/xDrip repos
  - Enables: integration testing with real data shapes
  - See: [tooling backlog](backlogs/tooling.md#cross-project-test-harness-in-progress)
- [ ] **Full audit: nightscout-connect** - NS client library (v0.0.12), 22 lines documented
  - Components: lib/, commands/, machines.md (state machine docs)
  - Focus: Cloud platform connectors, sync protocols
  - Workflow: `gap-discovery.conv`
- [ ] **nightscout-connect vendor interop proposal** - Tandem + Libre integration enhancements
  - From: LIVE-BACKLOG request
  - Focus: Apply tconnectsync/librelink-up learnings to nightscout-connect
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
