# Coverage Matrix

This matrix tracks which scenarios have been validated against which projects.

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Fully conformant |
| 🟡 | Partial / needs work |
| ❌ | Not conformant |
| ⬜ | Not evaluated |
| N/A | Not applicable |

## Scenarios

| Scenario | Spec Sections | Nightscout | Loop | AAPS | Trio | Notes |
|----------|---------------|------------|------|------|------|-------|
| [Override Supersede](../conformance/scenarios/override-supersede/) | override, eventStatus | 🟡 | ✅ | 🟡 | ✅ | NS lacks supersession tracking |
| Profile Switch | profile | ⬜ | ⬜ | ⬜ | ⬜ | Not yet evaluated |
| Temp Basal | treatment | ⬜ | ⬜ | ⬜ | ⬜ | Not yet evaluated |
| Bolus Delivery | treatment | ⬜ | ⬜ | ⬜ | ⬜ | Not yet evaluated |
| CGM Reading Sync | glucoseReading | ⬜ | ⬜ | ⬜ | ⬜ | Not yet evaluated |

## Summary

| Project | ✅ Full | 🟡 Partial | ❌ Fail | ⬜ Pending | Total |
|---------|---------|------------|---------|------------|-------|
| Nightscout | 0 | 1 | 0 | 4 | 5 |
| Loop | 1 | 0 | 0 | 4 | 5 |
| AAPS | 0 | 1 | 0 | 4 | 5 |
| Trio | 1 | 0 | 0 | 4 | 5 |

## Update Log

| Date | Change | Author |
|------|--------|--------|
| 2024-01-15 | Initial matrix with Override Supersede scenario | — |

## Next Steps

1. Complete evaluation for Override Supersede across all projects
2. Add Profile Switch scenario
3. Document gaps discovered during evaluation in [gaps.md](./gaps.md)
