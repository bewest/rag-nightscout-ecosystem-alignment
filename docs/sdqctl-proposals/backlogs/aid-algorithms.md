# AID Algorithms Backlog

> **Domain**: Closed-loop algorithms, dosing logic, predictions  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Last Updated**: 2026-01-28

Covers: Loop, AAPS, Trio, oref0/oref1, OpenAPS

---

## Active Items

| # | Item | Priority | Effort | Notes |
|---|------|----------|--------|-------|
| 1 | Compare override/profile switch semantics | P1 | Medium | Loop overrides vs AAPS ProfileSwitch vs Trio |
| 2 | Gap discovery: Prediction array formats | P1 | Medium | IOB/COB/UAM/ZT curve differences |
| 3 | Compare carb absorption models | P2 | Medium | Linear vs nonlinear vs dynamic |
| 4 | Full audit: openaps | P1 | High | Algorithm origins, oref0 relationship |
| 5 | Map algorithm terminology | P3 | Low | ISF, CR, DIA, UAM across systems |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Algorithm comparison deep dive | 2026-01-24 | Loop vs oref0 prediction models |
| Insulin curve analysis | 2026-01-23 | ExponentialInsulinModel, Bilinear |
| Carb absorption deep dive | 2026-01-22 | Dynamic vs linear models |

---

## References

- [docs/10-domain/algorithm-comparison-deep-dive.md](../../10-domain/algorithm-comparison-deep-dive.md)
- [docs/10-domain/insulin-curves-deep-dive.md](../../10-domain/insulin-curves-deep-dive.md)
- [docs/10-domain/carb-absorption-deep-dive.md](../../10-domain/carb-absorption-deep-dive.md)
