# Ecosystem Alignment Backlog

Prioritized queue of analysis tasks for the Nightscout AID ecosystem alignment project.
Use this as input for process-oriented workflows.

## How to Use

Pick items from the Ready Queue and run with appropriate workflow:

```bash
# For comparison tasks
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: [item from queue]"

# For gap discovery
sdqctl iterate workflows/analysis/gap-discovery.conv \
  --prologue "Area: [item from queue]"

# For deep dives
sdqctl iterate workflows/analysis/deep-dive.conv \
  --prologue "Topic: [item from queue]"
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

*None currently*

### P1 - High Value

- [ ] **Extract Nightscout v3 treatments schema** - Document all supported fields and eventTypes
- [ ] **Deep dive: Batch operation ordering** - Document order-preservation requirements for sync
- [ ] **Gap discovery: Prediction array formats** - IOB/COB/UAM/ZT curve differences

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

### P3 - Nice to Have

- [ ] **Compare CGM sensor session handling** - Start, stop, calibration
- [ ] **Extract xDrip+ Nightscout fields** - What xDrip+ uploads
- [ ] **Map algorithm terminology** - ISF, CR, DIA, UAM across systems

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
