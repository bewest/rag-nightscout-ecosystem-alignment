# Ecosystem Open PR Analysis

> **Date**: 2026-01-29  
> **Scope**: Key Nightscout ecosystem repositories  
> **Purpose**: Identify interoperability-relevant changes and alignment opportunities

---

## Summary

| Repository | Open PRs | Interop-Relevant | Stale (>6mo) |
|------------|----------|------------------|--------------|
| cgm-remote-monitor | 10 | 4 | 2 |
| Trio | 7 | 3 | 1 |
| AndroidAPS | 10 | 3 | 0 |
| LoopWorkspace | 4 | 2 | 2 |
| oref0 | 10 | 3 | 10 |
| xDrip | 10 | 4 | 3 |
| **Total** | **51** | **19** | **18** |

---

## cgm-remote-monitor (nightscout/cgm-remote-monitor)

### Interoperability-Relevant PRs

| PR | Title | Author | Date | Alignment Impact |
|----|-------|--------|------|------------------|
| #8422 | Fix api3 limit error when limit is string | KelvinKramp | 2026-01-25 | **API v3 bug fix** - affects all clients ✅ Reviewed |
| #8421 | Wip/bewest/mongodb 5x | bewest | 2026-01-19 | **Infrastructure** - MongoDB 5.x+ support |
| #8419 | Add tests for iOS loop push notifications and websockets | je-l | 2026-01-15 | **Loop integration** - push notification testing |
| #8405 | Fix timezone display to show device timezone | ryceg | 2025-11-18 | **GAP-TZ-xxx** - timezone handling |

### PR #8422 Review (2026-01-30)

**Problem**: `API3_MAX_LIMIT` env var as string causes 500 error (parseInt not called)

**Fix**: `parseInt(maxLimitRaw) || apiConst.API3_MAX_LIMIT` - safely parse string to int

**OpenAPI Compliance**:
- Our spec (`aid-entries-2025.yaml`) defines `limit` as `integer`
- Fix makes API tolerant of string input while returning proper integer behavior
- No interoperability gap - this is a robustness fix

**Recommendation**: Safe to merge, improves API stability

### Other Notable PRs

| PR | Title | Notes |
|----|-------|-------|
| #8417 | Multi-build docker build | DevOps improvement |
| #8416 | Update docker-compose.yml for mongo 8.2 | Infrastructure |
| #8410 | Do not nest async inside Promise | Code quality |
| #8402 | Database CSV exports | Research use case |

---

## Trio (nightscout/Trio)

### Interoperability-Relevant PRs

| PR | Title | Author | Date | Alignment Impact |
|----|-------|--------|------|------------------|
| #951 | Refactoring FPU handling | dnzxy | 2026-01-26 | **Algorithm** - Fat/Protein Unit changes |
| #949 | Apple watch carbs to Tidepool and Health | snickerdoodleparent | 2026-01-25 | **Sync** - Tidepool integration |
| #935 | Fix mmol/L delta calculation | bastiaanv | 2026-01-14 | **Unit conversion** - affects REQ-030 |

### Other Notable PRs

| PR | Title | Notes |
|----|-------|-------|
| #944 | Refactor Garmin | Device integration |
| #903 | Fix negative IOB on fresh installs | Algorithm edge case |
| #874 | Barcode scanner for carb entry | UX feature |
| #807 | Implement snooze for notifications | Stale (Oct 2025) |

---

## AndroidAPS (nightscout/AndroidAPS)

### Interoperability-Relevant PRs

| PR | Title | Author | Date | Alignment Impact |
|----|-------|--------|------|------------------|
| #4513 | Expand insulin pump compatibility | hhfcvmars | 2026-01-27 | **Device support** - new pumps |
| #4512 | insulin_concentration_compose | Philoul | 2026-01-26 | **Multi-insulin** - REQ-MI-xxx |
| #4506 | Diaconn G8 firmware 3.58+ support | miyeongkim | 2026-01-22 | **Device support** - Korean pump |

### Other Notable PRs

| PR | Title | Notes |
|----|-------|-------|
| #4509 | Locale-based date formatting in Statistics | UX improvement |
| #4499 | Omnipod Dash Drift resolution | Pump timing fix |
| #4507, #4504, #4503, #4496, #4494 | Dependency bumps | Maintenance |

---

## LoopWorkspace (LoopKit/LoopWorkspace)

### Interoperability-Relevant PRs

| PR | Title | Author | Date | Alignment Impact |
|----|-------|--------|------|------------------|
| #402 | Add support for DanaKit and MedtrumKit | marionbarker | 2026-01-17 | **Device support** - new pump drivers |
| #213 | Tidepool merge | ps2 | 2024-10-28 | **Sync** - Tidepool integration (stale) |

### Other Notable PRs

| PR | Title | Notes |
|----|-------|-------|
| #406 | Add support for multiple bundle IDs | Distribution |
| #263 | Refactor app icon assets | Stale (Apr 2025) |

---

## oref0 (openaps/oref0)

### Status: Maintenance Mode

All 10 open PRs are stale (>6 months old). The algorithm is stable but the JavaScript implementation is not receiving active development.

### Interoperability-Relevant PRs

| PR | Title | Author | Date | Alignment Impact |
|----|-------|--------|------|------------------|
| #1472 | Typescript migration | thomasvargiu | 2024-08-08 | **Modernization** - would enable better tooling |
| #1468 | Make glucose-get-last faster | thomasvargiu | 2024-05-04 | **Performance** |
| #1456 | Don't cancel high temp due to lack of BG | scottleibrand | 2023-08-18 | **Algorithm safety** |

---

## xDrip (NightscoutFoundation/xDrip)

### Interoperability-Relevant PRs

| PR | Title | Author | Date | Alignment Impact |
|----|-------|--------|------|------------------|
| #4365 | Glucose colors on lock screen | Navid200 | 2026-01-28 | **UX** - accessibility |
| #4330 | Upgrade to Carelink v13 API | m0rt4l1n | 2026-01-06 | **CGM source** - Medtronic integration |
| #4291 | More accurate missed reading alert | Navid200 | 2025-12-18 | **Alerting** - reliability |
| #4010 | Use new Bluetooth API for SDK 32+ | NiklasMehner | 2025-05-23 | **BLE** - Android 12+ compatibility |

### Other Notable PRs

| PR | Title | Notes |
|----|-------|-------|
| #4362 | Traditional Chinese language | Localization |
| #4360 | Hard reset UI improvements | UX |
| #4066 | Insulin stock tracking | Feature (stale) |

---

## Key Findings

### 1. Active Development Areas

| Area | Projects | PRs |
|------|----------|-----|
| Pump driver expansion | Loop, AAPS | #402, #4513 |
| Multi-insulin support | AAPS | #4512 |
| Tidepool integration | Trio, Loop | #949, #213 |
| Unit handling fixes | Trio | #935 |
| Timezone handling | cgm-remote-monitor | #8405 |

### 2. Gaps Confirmed

| Gap ID | Evidence |
|--------|----------|
| GAP-TZ-xxx | PR #8405 fixing timezone display |
| GAP-UNIT-xxx | PR #935 fixing mmol/L delta |
| GAP-SYNC-xxx | Tidepool PRs (#949, #213) addressing sync |

### 3. oref0 Stagnation

The oref0 repository has no active development. TypeScript migration PR (#1472) has been open since August 2024. This confirms:
- Algorithm reference is stable but unmaintained
- AAPS/Trio have diverged with their own implementations
- Conformance testing should use AAPS Kotlin as the "living" reference

### 4. Alignment Opportunities

| Opportunity | Affected PRs | Action |
|-------------|--------------|--------|
| **API v3 limit fix** | #8422 | Review for spec compliance |
| **Multi-insulin spec** | #4512 | Validate against REQ-MI-xxx |
| **FPU refactoring** | #951 | Document algorithm change |
| **Timezone fix** | #8405 | Track against GAP-TZ-xxx |

---

## Recommendations

### Immediate (P1)

1. **Review PR #8422** (API v3 limit) - ensure fix aligns with OpenAPI spec
2. **Monitor PR #4512** (insulin concentration) - validate against multi-insulin requirements

### Short-term (P2)

3. **Document oref0 stagnation** - update algorithm backlog to note maintenance-only status
4. **Track Tidepool integration** - PRs #949 and #213 affect sync identity

### Long-term (P3)

5. **Consider AAPS as algorithm reference** - more active than oref0 JavaScript
6. **Coordinate timezone fixes** - PR #8405 and related GAP-TZ issues

---

## References

- [traceability/gaps.md](../../traceability/gaps.md) - Gap index
- [docs/sdqctl-proposals/algorithm-conformance-suite.md](../sdqctl-proposals/algorithm-conformance-suite.md) - Conformance testing
- [mapping/cross-project/terminology-matrix.md](../../mapping/cross-project/terminology-matrix.md) - Term mapping
