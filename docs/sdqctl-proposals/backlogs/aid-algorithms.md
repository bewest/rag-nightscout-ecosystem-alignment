# AID Algorithms Backlog

> **Domain**: Closed-loop algorithms, dosing logic, predictions  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: Loop, AAPS, Trio, oref0/oref1, OpenAPS

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Algorithm conformance: AAPS runner | P2 | High | Phase 3 - Kotlin runner for JS vs KT comparison |
| 2 | Semantic equivalence for Loop | P3 | Medium | Enable Loop comparison with oref |
| 3 | Document AAPS vs oref0 divergence | P3 | Low | 69% output differences found |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Map algorithm terminology | 2026-01-29 | +95 lines, ISF/CR/DIA/UAM/SMB/Autosens |
| Algorithm conformance: oref0 runner | 2026-01-29 | 400+ lines, 26/85 pass (31%), 69% divergence |
| Algorithm conformance: Schema + extraction | 2026-01-29 | 85 vectors, `conformance-vector-v1.json` |
| Compare carb absorption models | 2026-01-29 | 471 lines, Loop vs oref0 paradigms |
| Compare override/profile switch semantics | 2026-01-29 | 416 lines, Trio Exercise eventType |
| Full audit: openaps/oref0 | 2026-01-29 | 371 lines, algorithm origins |
| Gap discovery: Prediction array formats | 2026-01-28 | 319 lines, IOB/COB/UAM/ZT curves |
| Algorithm comparison deep dive | 2026-01-24 | Loop vs oref0 prediction models |
| Insulin curve analysis | 2026-01-23 | ExponentialInsulinModel, Bilinear |

---

## References

- [Algorithm Conformance Suite Proposal](../algorithm-conformance-suite.md)
- [docs/10-domain/algorithm-comparison-deep-dive.md](../../10-domain/algorithm-comparison-deep-dive.md)
- [docs/10-domain/carb-absorption-comparison.md](../../10-domain/carb-absorption-comparison.md)
- `conformance/vectors/` - 85 test vectors
- `conformance/runners/oref0-runner.js` - oref0 test runner
- `conformance/results/oref0-results.json` - test results
