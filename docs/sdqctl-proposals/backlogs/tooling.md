# Tooling Backlog

> **Domain**: sdqctl enhancements, workflow improvements, automation  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-31

Covers: sdqctl directives, plugins, LSP integration, agentic automation

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Algorithm conformance runners | P2 | High | oref0-runner.js ✅, aaps-runner.kt pending |
| 2 | sdqctl VERIFY .conv directive (Phase 2) | P3 | Medium | CLI complete, directive parsing pending |
| 3 | LSP-based claim verification (Phase 2+) | P3 | Medium | JS/TS LSP integration deferred |
| 24 | ~~**Create `tools/lsp_query.py` for tsserver**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - symbols/type/definition/references queries via tsserver |
| 25 | ~~**Install tree-sitter-cli + parsers**~~ | ~~P2~~ | ~~Low~~ | ✅ COMPLETE - v0.26.3 via npm, 5 languages (JS/TS/Swift/Java + Kotlin manual) |
| 26 | ~~**Create tree-sitter query library**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `tools/tree_sitter_queries.py` (functions/classes/imports extraction) |
| 27 | **Implement aaps-runner.kt** | P2 | 2 days | Cross-language validation ([REQ-VERIFY-002](../../../traceability/connectors-requirements.md)) |
| 28 | ~~**Create accuracy_dashboard.py**~~ | ~~P2~~ | ~~1 day~~ | ✅ COMPLETE - Unified accuracy reporting (refs/coverage/assertions) |
| 4 | ~~**Mapping coverage tool**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `tools/verify_mapping_coverage.py` |
| 5 | ~~**Gap freshness checker tool**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `tools/verify_gap_freshness.py` |
| 6 | ~~**Terminology sample tool**~~ | ~~P3~~ | ~~Low~~ | ✅ COMPLETE - `tools/sample_terminology.py` |
| 7 | ~~**Gap deduplication tool**~~ | ~~P1~~ | ~~Low~~ | ✅ COMPLETE - `tools/find_gap_duplicates.py` |
| 8 | ~~**REFCAT caching proposal**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `docs/sdqctl-proposals/refcat-caching-proposal.md` |
| 9 | ~~**Token efficiency dashboard**~~ | ~~P3~~ | ~~Low~~ | ✅ COMPLETE - `tools/efficiency_dashboard.py` |
| 10 | ~~**Selective repo loading**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `docs/sdqctl-proposals/selective-repo-loading-proposal.md` |
| 11 | ~~**Deprecate redundant tools**~~ | ~~P3~~ | ~~Low~~ | ✅ COMPLETE - Migration eval done, 7 tools identified for deprecation |
| 12 | ~~**Unit tests for kept tools**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `tools/test_verify_tools_unit.py` (17 tests) |
| 13 | ~~**sdqctl usage documentation**~~ | ~~P3~~ | ~~Low~~ | ✅ COMPLETE - `docs/TOOLING-GUIDE.md` (+60 lines) |
| 14 | **backlog-cycle-v3.conv** | P3 | Medium | Leverage ELIDE, mixed tools, cyclic prompts ([LIVE-BACKLOG](../../../LIVE-BACKLOG.md)) |
| 15 | ~~**Idiomatic sdqctl workflow integration**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `docs/10-domain/sdqctl-workflow-integration.md` |
| 16 | ~~**LSP verification setup research**~~ | ~~P2~~ | ~~High~~ | ✅ COMPLETE - `docs/10-domain/lsp-verification-setup-requirements.md` |
| 17 | ~~**Nightscout PR coherence review protocol**~~ | ~~P2~~ | ~~Medium~~ | ✅ COMPLETE - `docs/10-domain/nightscout-pr-review-protocol.md` |
| 18 | ~~**Tool coverage audit**~~ | ~~P1~~ | ~~Medium~~ | ✅ COMPLETE - `docs/10-domain/tool-coverage-audit.md` |
| 19 | ~~**Documentation parse audit**~~ | ~~P1~~ | ~~Medium~~ | ✅ COMPLETE - `docs/10-domain/documentation-parse-audit.md` (30 uncovered, 91%→99% after fixes) |
| 20 | ~~**Known vs unknown dashboard**~~ | ~~P2~~ | ~~Low~~ | ✅ COMPLETE - `tools/known_unknown_dashboard.py` |
| 21 | ~~**Fix verify_coverage.py**~~ | ~~P1~~ | ~~Low~~ | ✅ COMPLETE - Fixed glob patterns + REQ-DOMAIN-NNN regex (0→242 reqs, 0→289 gaps) |
| 22 | ~~**Extend verify_refs scope**~~ | ~~P2~~ | ~~Low~~ | ✅ COMPLETE - Added traceability/, conformance/ (300→353 files, 441 refs validated) |
| 23 | ~~**Extend verify_assertions scope**~~ | ~~P3~~ | ~~Low~~ | ✅ COMPLETE - Now scans conformance/**/*.yaml (4→12 files, 25 assertion groups) |

---

## sdqctl Migration Evaluation

**Date**: 2026-01-30  
**Source**: [tools-comparison-proposal.md](../tools-comparison-proposal.md)

| Action | Count | Tools |
|--------|-------|-------|
| **Deprecate** | 7 | verify_refs, verify_terminology, linkcheck, verify_hello, run_workflow, phase_nav, project_seq |
| **Integrate** | 3 | queue_stats, backlog_hygiene, doc_chunker → sdqctl plugins |
| **Keep** | 27 | Domain-specific with no sdqctl equivalent |

**Overlap with sdqctl verify**:

| Custom Tool | sdqctl Equivalent | Status |
|-------------|-------------------|--------|
| `verify_refs.py` | `sdqctl verify refs` | Deprecate |
| `verify_terminology.py` | `sdqctl verify terminology` | Deprecate |
| `linkcheck.py` | `sdqctl verify links` | Deprecate |
| `verify_hello.py` | `sdqctl verify plugin` | Deprecate (test artifact) |
| `verify_assertions.py` | `sdqctl verify assertions` | Keep (different purpose) |
| `verify_coverage.py` | `sdqctl verify coverage` | Keep (different purpose) |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| sdqctl usage documentation | 2026-01-30 | `docs/TOOLING-GUIDE.md` - +60 lines, comprehensive guide |
| Unit tests for verify tools | 2026-01-30 | `tools/test_verify_tools_unit.py` - 17 tests, 6 tools covered |
| sdqctl migration evaluation | 2026-01-30 | 7 deprecate, 3 integrate, 27 keep |
| Token efficiency dashboard | 2026-01-30 | `tools/efficiency_dashboard.py`, `make efficiency-dashboard` |
| Mapping coverage tool | 2026-01-30 | `tools/verify_mapping_coverage.py`, `make verify-mapping-coverage` |
| Gap freshness checker tool | 2026-01-30 | `tools/verify_gap_freshness.py`, `make verify-gap-freshness` |
| Terminology sample tool | 2026-01-30 | `tools/sample_terminology.py`, `make verify-terminology` |
| Gap deduplication tool | 2026-01-30 | `tools/find_gap_duplicates.py`, `make verify-gap-duplicates` |
| sdqctl VERIFY CLI | 2026-01-29 | CLI already existed, added Make targets |
| Conformance CI Integration | 2026-01-29 | CI job + Makefile targets + README |
| Gap-to-Requirement Generator | 2026-01-29 | Manual process, 28 connector REQs generated |
| Assertion→Requirement coverage validator | 2026-01-29 | Enhanced verify_assertions.py: multi-file, scenario inheritance |
| Integration test runner | 2026-01-29 | `tools/conformance_suite.py` - orchestrator + reports |
| LSP claim verification Phase 1 | 2026-01-29 | Line anchor validation, 99.3% valid |
| Transformation pipeline tester | 2026-01-29 | `tools/test_transforms.py` + 28 test cases |
| Hygiene tooling suite | 2026-01-29 | queue_stats.py, backlog_hygiene.py, doc_chunker.py verified |
| Conformance schema + vector extraction | 2026-01-29 | `conformance-vector-v1.json` + 85 vectors from AAPS |
| Algorithm conformance suite proposal | 2026-01-29 | `docs/sdqctl-proposals/algorithm-conformance-suite.md` - 510 lines, 5-phase plan |
| Unit conversion test suite | 2026-01-28 | `tools/test_conversions.py` + 20 test cases |
| Mock Nightscout server | 2026-01-28 | `tools/mock_nightscout.py` v1/v3 API |
| Plugin system validation | 2026-01-28 | All 5 plugins work |
| backlog-cycle.conv workflow | 2026-01-28 | Orchestration pattern |

---

## Cross-Project Test Harness (In Progress)

| Component | Status | File | Description |
|-----------|--------|------|-------------|
| Unit conversions | ✅ Done | `tools/test_conversions.py` | Time/glucose/insulin precision |
| Mock server | ✅ Done | `tools/mock_nightscout.py` | HTTP mock for API v1/v3 |
| Conformance schema | ✅ Done | `conformance/schemas/conformance-vector-v1.json` | Test vector format |
| Vector extractor | ✅ Done | `tools/extract_vectors.py` | Pull from AAPS replay tests |
| Test vectors | ✅ Done | `conformance/vectors/` | 85 vectors (77 basal, 8 LGS) |
| Conformance runners | 📋 Proposed | `conformance/runners/` | oref0, AAPS, Loop runners |
| Transform tester | ✅ Done | `tools/test_transforms.py` | Field mapping validation (28 tests) |

---

## sdqctl Enhancement Requests

| Priority | Enhancement | Proposal | Notes |
|----------|-------------|----------|-------|
| P2 | HELP-INLINE directive | [sdqctl/HELP-INLINE.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/HELP-INLINE.md) | Allow HELP anywhere in workflow |
| P2 | REFCAT glob support | [sdqctl/REFCAT-DESIGN.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/REFCAT-DESIGN.md) | `@externals/**/*Treatment*.swift` |
| P2 | Plugin System | [sdqctl/PLUGIN-SYSTEM.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/PLUGIN-SYSTEM.md) | Custom directives for ecosystem |
| P2 | LSP Integration | [lsp-integration-proposal.md](../lsp-integration-proposal.md) | Semantic code queries (4-phase plan) |
| P3 | Ecosystem help topics | New | gap-ids, 5-facet, stpa, conformance |
| P3 | VERIFY stpa-hazards | New | Check STPA hazard traceability |
| P3 | RUN-CONFORMANCE | New | Execute conformance test scenarios |
| P3 | STPA Deep Integration | [sdqctl/STPA-DEEP-INTEGRATION.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/STPA-DEEP-INTEGRATION.md) | Usage guide + predictions |

---

## Agentic Automation (R&D)

| Priority | Enhancement | Proposal | Notes |
|----------|-------------|----------|-------|
| P3 | `sdqctl agent analyze` | [AGENTIC-ANALYSIS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/AGENTIC-ANALYSIS.md) | Autonomous multi-cycle |
| P3 | `sdqctl watch` | [CONTINUOUS-MONITORING.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/CONTINUOUS-MONITORING.md) | Monitor for changes |
| P3 | `sdqctl drift` | [CONTINUOUS-MONITORING.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/CONTINUOUS-MONITORING.md) | Drift detection |
| P3 | `sdqctl delegate` | [UPSTREAM-CONTRIBUTIONS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/UPSTREAM-CONTRIBUTIONS.md) | Draft upstream fixes |
| P3 | `sdqctl upstream status` | [UPSTREAM-CONTRIBUTIONS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/UPSTREAM-CONTRIBUTIONS.md) | Track contributions |

---

## backlog-cycle-v3 Proposal Scope

**Status**: Research Phase  
**Source**: [LIVE-BACKLOG](../../../LIVE-BACKLOG.md)

### Goals

1. **Leverage ELIDE** - Use ELIDE directive more idiomatically for RUN output compression
2. **Mixed tool patterns** - Combine python tools + sdqctl verify in single workflow
3. **Cyclic prompt efficiency** - Reduce redundant context between iterations
4. **Cross-backlog coordination** - Single workflow that can process items across domains

### Design Questions

| Question | Options | Notes |
|----------|---------|-------|
| Queue selection | Single backlog vs cross-domain | v2 uses Ready Queue centrally |
| sdqctl verify integration | Pre-phase check vs phase 0 | Hygiene first? |
| ELIDE granularity | Per-RUN vs per-phase | Performance vs readability |
| Commit frequency | Per-cycle vs batch | Git hygiene vs efficiency |

### Research Items

- [ ] Analyze v2 cycle efficiency (tokens per task completion)
- [ ] Document sdqctl verify patterns that replace custom python tools
- [ ] Design cross-backlog task selection algorithm
- [ ] Propose ELIDE placement strategy

### LSP Environment Items (from 2026-01-31 check)

| Item | Priority | Effort | Status |
|------|----------|--------|--------|
| Create `tools/lsp_query.py` for tsserver | P2 | Medium | Ready (JS/TS available) |
| Add swiftly env.sh to shell init | P3 | Low | Swift 6.2.3 installed |
| Install pyright for tools/ | P3 | Low | `pip install pyright` |
| Install tree-sitter-cli | P2 | Low | `cargo install tree-sitter-cli` |
| Create tree-sitter query library | P2 | Medium | After CLI install |
| Install kotlin-language-server | P3 | Medium | For AAPS verification |

**Report**: [lsp-environment-check.md](../../10-domain/lsp-environment-check.md)

---

## LSP Verification Setup Research

**Status**: Research Phase  
**Source**: [lsp-integration-proposal.md](../lsp-integration-proposal.md)

### Phase 1: Line Validation (No LSP) - Ready for implementation

Already partially implemented in `verify_refs.py`. Full implementation:
- Validate `#L<N>` anchors against actual line counts
- Validate `#L<start>-L<end>` ranges
- Report line count mismatches

**Effort**: 2 hours

### Phase 2: JS/TS LSP Setup Requirements

| Prerequisite | Command | Notes |
|--------------|---------|-------|
| Node.js 18+ | `node --version` | Already available |
| typescript | `npm install -g typescript` | tsserver for JS/TS |
| typescript-language-server | `npm install -g typescript-language-server` | LSP wrapper |
| jsconfig.json in externals/ | Manual creation | Tells tsserver project roots |

**Verification targets**:
- `externals/cgm-remote-monitor/lib/` - ~500 JS files
- `externals/oref0/lib/` - ~50 JS files

**Implementation**:
1. Create `tools/lsp_query.py` wrapper for tsserver
2. Add `--lsp` flag to `verify_refs.py`
3. Test with 10 cgm-remote-monitor refs

**Effort**: 1 day

### Phase 3: Kotlin/Java LSP Setup Requirements

| Prerequisite | Command | Notes |
|--------------|---------|-------|
| JDK 11+ | `java --version` | Android projects need 11 |
| Gradle wrapper | `./gradlew` in repo | AAPS has it |
| kotlin-language-server | Download from GitHub | Kotlin IDE support |
| eclipse.jdt.ls | Download from Eclipse | Java IDE support |

**Verification targets**:
- `externals/AndroidAPS/` - ~3000 Kotlin files
- `externals/xDrip/` - ~500 Java files

**Challenge**: Gradle sync required before LSP works (slow, ~2-5 min first time)

**Effort**: 1-2 days

### Phase 4: Swift LSP Limitations

| Constraint | Impact |
|------------|--------|
| macOS only | No iOS frameworks on Linux |
| Xcode required | sourcekit-lsp bundled with Xcode |
| CI cost | macOS runners 10x expensive |

**Recommendation**: Defer Swift LSP to CI-only verification on macOS runners. Use line-only validation locally.

---

## Nightscout PR Coherence Review Protocol

**Status**: Proposed  
**Scope**: cgm-remote-monitor, Trio, AAPS, LoopWorkspace

### Purpose

Ensure PR analysis aligns with:
1. Existing gap documentation (GAP-* ids)
2. Existing requirement documentation (REQ-* ids)  
3. Active proposals in docs/sdqctl-proposals/
4. Domain backlog items

### Review Checklist

| Step | Action | Tool |
|------|--------|------|
| 1 | Identify PR alignment impact | Manual from PR title/description |
| 2 | Cross-ref with gaps.md | `grep GAP-XXX traceability/*-gaps.md` |
| 3 | Cross-ref with requirements.md | `grep REQ-XXX traceability/*-requirements.md` |
| 4 | Check for related proposals | `grep <keyword> docs/sdqctl-proposals/*.md` |
| 5 | Update PR analysis doc | `docs/analysis/ecosystem-pr-analysis-*.md` |
| 6 | Add backlog items if needed | Domain backlog files |

### Priority PRs for Review

From [ecosystem-pr-analysis-2026-01-29.md](../../analysis/ecosystem-pr-analysis-2026-01-29.md):

| PR | Repo | Alignment Topic | Related Gaps |
|----|------|-----------------|--------------|
| #8422 | cgm-remote-monitor | API v3 limit fix | GAP-API-* |
| #8421 | cgm-remote-monitor | MongoDB 5.x+ | Infrastructure |
| #8405 | cgm-remote-monitor | Timezone display | GAP-TZ-* |
| #4512 | AndroidAPS | Multi-insulin | REQ-MI-* |
| #951 | Trio | FPU refactoring | GAP-ALG-* |
| #935 | Trio | mmol/L delta | REQ-030, GAP-UNIT-* |

---

## References

- [.sdqctl/directives.yaml](../../../.sdqctl/directives.yaml) - Plugin manifest
- [workflows/orchestration/](../../../workflows/orchestration/) - Backlog workflows
- [lsp-integration-proposal.md](../lsp-integration-proposal.md) - Full LSP proposal
- [ecosystem-pr-analysis-2026-01-29.md](../../analysis/ecosystem-pr-analysis-2026-01-29.md) - PR inventory
