# Ecosystem Alignment Backlog

Prioritized queue of analysis tasks for the Nightscout AID ecosystem alignment project.
Use this as input for process-oriented workflows.

## How to Use

### Single Item from Ready Queue

Pick items and run with appropriate workflow:

```bash
# For comparison tasks
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: remote bolus commands. Repos: Loop, AAPS, Trio, Nightscout"

# For gap discovery
sdqctl iterate workflows/analysis/gap-discovery.conv \
  --prologue "Repo: cgm-remote-monitor. Focus: API v3, sync, auth"

# For deep dives (multi-cycle)
sdqctl iterate workflows/analysis/deep-dive.conv \
  --prologue "Repo: openaps. Component: algorithm core" \
  -n 5 --session-mode fresh

# For spec extraction
sdqctl iterate workflows/analysis/extract-spec.conv \
  --prologue "Source: externals/AndroidAPS/core/nssdk/. Focus: Nightscout upload fields"
```

### Batch Processing Multiple Items

```bash
# Apply workflow to multiple repos
sdqctl apply workflows/analysis/gap-discovery.conv \
  --components "externals/*/README.md" \
  --progress progress.md

# Apply to specific under-documented repos
for repo in cgm-remote-monitor openaps nightscout-connect; do
  sdqctl iterate workflows/analysis/gap-discovery.conv \
    --prologue "Repo: $repo. Quick audit for backlog scoping."
done
```

### Verification After Changes

```bash
# Run all verification plugins
sdqctl verify plugin ref-integrity
sdqctl verify plugin ecosystem-gaps
sdqctl verify plugin terminology-matrix

# Or use the CI pipeline workflow
sdqctl iterate workflows/integrate/ci-pipeline.conv
```

---

## Ready Queue (3 items)

Items ready for immediate work. Keep this at 3 items.

### 1. [P1] Compare remote bolus command handling
**Type:** Comparison | **Effort:** Medium
**Repos:** Loop, AAPS, Trio, Nightscout
**Focus:** How each system validates and executes remote bolus commands
**Workflow:** `compare-feature.conv`

### 2. [P1] Extract AAPS NSClient upload schema
**Type:** Extraction | **Effort:** Medium
**Source:** `externals/AndroidAPS/core/nssdk/`
**Focus:** Document all fields uploaded to Nightscout
**Workflow:** `extract-spec.conv`

### 3. [P1] Compare override/profile switch semantics
**Type:** Comparison | **Effort:** Medium
**Repos:** Loop, AAPS, Trio
**Focus:** Loop overrides vs AAPS ProfileSwitch vs Trio overrides
**Workflow:** `compare-feature.conv`

---

## Backlog (Prioritized)

### P0 - Critical

- [ ] **Full audit: cgm-remote-monitor** - Central Nightscout server (v15.0.4), only 32 lines documented
  - Components: lib/ (api3, plugins, server), views/, translations/
  - Focus: API v3 collections, sync behavior, authentication, plugin system
  - Workflow: `deep-dive.conv` with multiple cycles

### P1 - High Value

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
- [ ] **LSP-based documentation claim verification** - Use LSP semantic queries to verify:
  - File paths with `...` placeholders (15 broken refs use this pattern)
  - Type signatures claimed in deep-dives match actual code
  - Cross-project terminology claims (e.g., "Loop calls this X, AAPS calls it Y")
  - See: `traceability/refs-validation.md` for current broken refs
- [ ] **Full audit: nightscout-connect** - NS client library (v0.0.12), 22 lines documented
  - Components: lib/, commands/, machines.md (state machine docs)
  - Focus: Cloud platform connectors, sync protocols
  - Workflow: `gap-discovery.conv`

### P3 - Nice to Have

- [ ] **Compare CGM sensor session handling** - Start, stop, calibration
- [ ] **Extract xDrip+ Nightscout fields** - What xDrip+ uploads
- [ ] **Map algorithm terminology** - ISF, CR, DIA, UAM across systems
- [ ] **Full audit: nightscout-roles-gateway** - OAuth 2.0 RBAC controller, 39 lines documented
  - Components: lib/, migrations/, Ory Hydra/Kratos integration
  - Focus: Role-based access control, OAuth flows, API authorization
  - Workflow: `gap-discovery.conv`

---

## Completed

| Date | Item | Outcome |
|------|------|---------|
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
- [docs/OPEN-QUESTIONS.md](../OPEN-QUESTIONS.md) - Blocked items (if exists)
- [progress.md](../../progress.md) - Completion log

---

## sdqctl Enhancement Requests

Track tooling improvements that would help ecosystem alignment workflows.

| Priority | Enhancement | Proposal | Notes |
|----------|-------------|----------|-------|
| P2 | HELP-INLINE directive | [sdqctl/HELP-INLINE.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/HELP-INLINE.md) | Allow HELP anywhere in workflow, not just prologues |
| P2 | REFCAT glob support | [sdqctl/REFCAT-DESIGN.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/REFCAT-DESIGN.md) | Multi-file patterns: `@externals/**/*Treatment*.swift` |
| P2 | Plugin System | [sdqctl/PLUGIN-SYSTEM.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/PLUGIN-SYSTEM.md) | Write custom directives for ecosystem independently |
| P2 | LSP Integration | [sdqctl/LSP-INTEGRATION.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/LSP-INTEGRATION.md) | Semantic code queries: type extraction, cross-project comparison. Key use case: resolve `...` placeholder paths in refs (15 broken). `sdqctl lsp type Treatment --repos Loop,AAPS` |
| P3 | Ecosystem help topics | New | gap-ids, 5-facet, stpa, conformance, nightscout |
| P3 | VERIFY stpa-hazards | New | Check STPA hazard traceability |
| P3 | RUN-CONFORMANCE | New | Execute conformance test scenarios |
| P3 | STPA Deep Integration | [sdqctl/STPA-DEEP-INTEGRATION.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/STPA-DEEP-INTEGRATION.md) | Usage guide + improvement predictions for ecosystem |

---

## Agentic Automation (R&D)

Future tooling for autonomous ecosystem analysis and contribution.

| Priority | Enhancement | Proposal | Notes |
|----------|-------------|----------|-------|
| P3 | `sdqctl agent analyze` | [sdqctl/AGENTIC-ANALYSIS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/AGENTIC-ANALYSIS.md) | Autonomous multi-cycle deep-dive with auto 5-facet updates |
| P3 | `sdqctl watch` | [sdqctl/CONTINUOUS-MONITORING.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/CONTINUOUS-MONITORING.md) | Monitor external repos for alignment-relevant changes |
| P3 | `sdqctl drift` | [sdqctl/CONTINUOUS-MONITORING.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/CONTINUOUS-MONITORING.md) | One-shot drift detection since last analysis |
| P3 | `sdqctl delegate` | [sdqctl/UPSTREAM-CONTRIBUTIONS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/UPSTREAM-CONTRIBUTIONS.md) | Draft upstream fixes for identified gaps |
| P3 | `sdqctl upstream status` | [sdqctl/UPSTREAM-CONTRIBUTIONS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/UPSTREAM-CONTRIBUTIONS.md) | Track contribution status across repos |
