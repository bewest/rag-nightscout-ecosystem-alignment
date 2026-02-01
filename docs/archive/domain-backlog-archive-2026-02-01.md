# Domain Backlog Archive - 2026-02-01

> **Purpose**: Archive of completed domain backlog items  
> **Date**: 2026-02-01  
> **Cycle**: 75

---

## Summary

| Domain | Completed Items | Remaining Active |
|--------|-----------------|------------------|
| sync-identity | 6 | 0 |
| cgm-sources | 10 | 0 |
| tooling | 28 | 1 (algorithm runners) |
| ios-mobile-platform | 10 | 0 |
| nightscout-api | 23 | 2 |
| aid-algorithms | 12 | 2 |
| documentation-accuracy | 26 | 0 |
| **Total** | **115** | **5** |

---

## sync-identity.md (6 items → Archive)

All items COMPLETE:
1. Cross-controller conflict detection (2026-01-29)
2. Verify sync-identity mapping (accuracy backlog #7)
3. Verify GAP-SYNC-* freshness (accuracy backlog #21)
4. Audit REQ-SYNC-* scenario coverage (83% covered)
5. Nocturne ProfileSwitch treatment model (2026-01-30)
6. Nocturne percentage/timeshift handling (2026-01-30)

---

## cgm-sources.md (10 items → Archive)

All items COMPLETE:
1. CGM trend arrow standardization
2. Libre 3 protocol gap analysis (2026-01-29)
3. Verify G7 protocol claims (100% accurate)
4. Verify CGM deep dive claims
5. Verify xdrip mapping coverage (91% valid)
6. Deep dive: xdrip-js (380 lines, GAP-XDRIPJS-001..004)
7. Extract xDrip+ Nightscout fields (370 lines)
8. Compare CGM sensor session handling (407 lines)
9. Full audit: DiaBLE Libre protocol (487 lines)
10. Full audit: nightscout-librelink-up (378 lines)

---

## tooling.md (28 items → Archive)

Completed items archived:
- sdqctl VERIFY .conv directive (Phase 2)
- LSP-based claim verification
- Create `tools/lsp_query.py` for tsserver
- Install tree-sitter-cli + parsers
- Create tree-sitter query library
- Implement aaps-runner.kt
- Create accuracy_dashboard.py
- Mapping coverage tool
- Gap freshness checker tool
- Terminology sample tool
- Gap deduplication tool
- REFCAT caching proposal
- Token efficiency dashboard
- Selective repo loading
- Deprecate redundant tools
- Unit tests for kept tools
- sdqctl usage documentation
- backlog-cycle-v3.conv
- Idiomatic sdqctl workflow integration
- LSP verification setup research
- Nightscout PR coherence review protocol
- Tool coverage audit
- Documentation parse audit
- Known vs unknown dashboard
- Fix verify_coverage.py
- Extend verify_refs scope
- Extend verify_assertions scope
- OpenAPSSwift parity testing

**Remaining**: Algorithm conformance runners (AAPS Phase 3, Loop runner)

---

## ios-mobile-platform.md (10 items → Archive)

All items COMPLETE:
1. iOS App Distribution Survey (7 apps analyzed)
2. Code sharing reality assessment
3. WidgetKit survey (6 apps)
4. HealthKit integration comparison
5. Complication/widget analysis
6. TestFlight distribution infrastructure
7. BLE CGM library consolidation
8. App Store deployment pathways
9. Monolithic vs multi-app architecture
10. Cross-platform testing infrastructure

---

## nightscout-api.md (23 items → Archive)

Completed items 1-23, including:
- Nocturne V4 controller analysis (#1-11, OQ-010 extended)
- V3 parity analysis
- StateSpan proposal
- PostgreSQL migration analysis
- SignalR bridge analysis
- Trusted Identity Providers Inventory (#23)

**Remaining**: 
- #24 NS Community Identity Provider Proposal (P3)
- #25 V4 API Integration Implementation (P2, Phase 2-3)

---

## aid-algorithms.md (12 items → Archive)

Completed items:
- Algorithm conformance: oref0 runner (26/85 pass)
- Algorithm conformance: Schema + extraction (85 vectors)
- Document AAPS vs oref0 divergence (4 gaps)
- Semantic equivalence for Loop (4 gaps)
- Trio comprehensive analysis (6 gaps, 3 reqs)
- Trio-dev OpenAPSSwift analysis
- Compare carb absorption models
- Compare override/profile switch semantics
- Full audit: openaps/oref0
- Gap discovery: Prediction array formats
- Algorithm comparison deep dive
- Insulin curve analysis

**Remaining**:
- #1 Algorithm conformance: AAPS runner (Phase 3)
- #2 Algorithm conformance: Loop runner (Swift, macOS CI)

---

## documentation-accuracy.md (26 items → Archive)

All levels COMPLETE:
- Level 1: Evidence Source Verification (91% valid, 356/391)
- Level 2: Mapping Accuracy Verification (5 items, 100% accurate)
- Level 3: Analysis Claims Verification (multiple items)
- Level 4: Gap Claims Verification
- Level 5: Requirements Coverage
- Level 6: Proposal Coherence

---

## Metrics

- **Total archived**: 115 completed items
- **Total remaining**: 5 active items across all domains
- **Completion rate**: 96%

---

## Active Items Summary (5 remaining)

| Domain | Item | Priority | Blocker |
|--------|------|----------|---------|
| aid-algorithms | AAPS runner Phase 3 | P2 | AAPS deps |
| aid-algorithms | Loop runner | P3 | Swift/macOS |
| nightscout-api | NS Community IDP | P3 | Org decision |
| nightscout-api | V4 Integration Phase 2-3 | P2 | External PRs |
| tooling | Algorithm runners | P2 | Above items |
