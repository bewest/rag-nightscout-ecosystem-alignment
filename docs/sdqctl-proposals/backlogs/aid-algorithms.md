# AID Algorithms Backlog

> **Domain**: Closed-loop algorithms, dosing logic, predictions  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-29

Covers: Loop, AAPS, Trio, oref0/oref1, OpenAPS

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Algorithm conformance: oref0 runner | P2 | Medium | Phase 2 - execute vectors against oref0 |
| 2 | Algorithm conformance: AAPS runner | P2 | High | Phase 3 - Kotlin runner for JS vs KT comparison |
| 3 | Map algorithm terminology | P3 | Low | ISF, CR, DIA, UAM across systems |
| 4 | Semantic equivalence for Loop | P3 | Medium | Enable Loop comparison with oref |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
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
