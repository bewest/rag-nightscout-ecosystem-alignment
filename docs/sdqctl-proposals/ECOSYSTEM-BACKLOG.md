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

## Ready Queue (3 items)

Items ready for immediate work. Keep this at 3 items.

### 1. [P1] Compare remote bolus command handling
**Type:** Comparison | **Effort:** Medium
**Repos:** Loop, AAPS, Trio, Nightscout
**Focus:** How each system validates and executes remote bolus commands
**Workflow:** `compare-feature.conv`

### 2. [P1] Compare override/profile switch semantics
**Type:** Comparison | **Effort:** Medium
**Repos:** Loop, AAPS, Trio
**Focus:** Loop overrides vs AAPS ProfileSwitch vs Trio overrides
**Workflow:** `compare-feature.conv`

### 3. [P1] Modernization analysis: cgm-remote-monitor vs Nocturne
**Type:** Analysis | **Effort:** Large
**Repos:** cgm-remote-monitor, nocturne
**Focus:** Gap/feature/impact analysis, migration paths
**Prereq:** ✅ nocturne audit complete
**Workflow:** `compare-feature.conv`

---

## Backlog (Prioritized)

### P0 - Critical

- [ ] **Full audit: cgm-remote-monitor** - Central Nightscout server (v15.0.4), only 32 lines documented
  - Components: lib/ (api3, plugins, server), views/, translations/
  - Focus: API v3 collections, sync behavior, authentication, plugin system
  - Workflow: `deep-dive.conv` with multiple cycles

### P1 - High Value

- [ ] **PR analysis: cgm-remote-monitor** - Review open PRs for ecosystem impact
- [ ] **PR analysis: share2nightscout-bridge** - Review open PRs
- [ ] **Extract Nightscout v3 treatments schema** - Document all supported fields and eventTypes
- [ ] **Deep dive: Batch operation ordering** - Document order-preservation requirements for sync
- [ ] **Gap discovery: Prediction array formats** - IOB/COB/UAM/ZT curve differences
- [ ] **Full audit: openaps** - Algorithm origins, Python-based (setup.py), 36 lines documented
  - Components: openaps/ module, bin/, Makefile
  - Focus: Historical context, oref0 relationship, device abstractions
  - Workflow: `deep-dive.conv`

### P2 - Normal

- [ ] **Compare carb absorption models** - Linear vs nonlinear vs dynamic
- [ ] **Extract Loop sync identity fields** - What makes a treatment unique in Loop
- [ ] **Map pump communication terminology** - Reservoir, cartridge, pod, etc.
- [ ] **Deep dive: Authentication flows** - API secret vs tokens vs JWT
- [ ] **Cross-repo fixture extraction** - Pull test fixtures from AAPS/Loop/xDrip repos
  - Enables: integration testing with real data shapes
  - See: [tooling backlog](backlogs/tooling.md#cross-project-test-harness-in-progress)
- [ ] **Full audit: nightscout-connect** - NS client library (v0.0.12), 22 lines documented
  - Components: lib/, commands/, machines.md (state machine docs)
  - Focus: Cloud platform connectors, sync protocols
  - Workflow: `gap-discovery.conv`

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

---

## Completed

| Date | Item | Outcome |
|------|------|---------|
| 2026-01-28 | Initial audit: share2nightscout-bridge | `docs/10-domain/share2nightscout-bridge-deep-dive.md` - 328 lines, 3 gaps (GAP-SHARE-001-003) |
| 2026-01-28 | Initial audit: nocturne | `docs/10-domain/nocturne-deep-dive.md` - 279 lines, 3 gaps (GAP-NOCTURNE-001-003) |
| 2026-01-28 | Extract AAPS NSClient upload schema | `mapping/aaps/nsclient-schema.md` - 70+ fields, 25 eventTypes |
| 2026-01-28 | Workspace expansion (4 repos) | nocturne, Trio-dev, share2nightscout-bridge, cgm-remote-monitor-official added |
| 2026-01-28 | Cross-project test harness tooling | `test_conversions.py` (20 tests), `mock_nightscout.py` (API v1/v3), Makefile targets |
| 2026-01-28 | Map timezone/DST handling terminology | +150 lines terminology matrix, 4 new gaps (GAP-TZ-004-007), pump DST handling documented |

---

## Queue Discipline

1. **Ready Queue**: Exactly 3 actionable items
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
