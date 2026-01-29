# Progress Archive - 2026-01-29 Batch 3

Entries archived from main progress.md.

---

### Cross-project Testing Plan (2026-01-29)

Proposal for Ubuntu-compatible testing strategies for Swift AID projects.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/cross-project-testing-plan.md` | 363 lines, 4 strategies |
| **Gaps** | `traceability/gaps.md` | GAP-TEST-001/002/003 added |

**Key Findings**:
- Trio: GitHub Actions (macOS-15), 211 test files
- Loop: Travis CI (outdated xcode12.4), 233 test files
- LoopKit Package.swift marked "not complete yet"
- Swift on Linux lacks CoreData/HealthKit/UIKit

**Strategies Proposed**:
1. Extract pure-Swift algorithm packages (Medium effort, High impact)
2. Remote macOS test execution (Low effort)
3. Test fixture extraction (Low effort, High impact)
4. Docker-based Swift testing (Limited scope)

---

### Override/Profile Switch Comparison Update (2026-01-29)

Updated override comparison with deep source code analysis across Loop, AAPS, and Trio.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/override-profile-switch-comparison.md` | 416 lines, enhanced with Trio Exercise eventType |
| **Gaps** | `traceability/gaps.md` | GAP-OVERRIDE-005/006/007 added |

**Key Findings**:
- **Critical**: Trio uses `Exercise` eventType (NOT `Temporary Override`)
- Loop: `Temporary Override` with syncIdentifier (UUID)
- AAPS: `Profile Switch` with interfaceIDs.nightscoutId
- Three incompatible eventTypes for similar user intent
- Trio override upload loses algorithm settings (smbIsOff, percentage, target)

---

### Playwright Adoption Proposal (2026-01-29)

Proposal for E2E testing adoption in cgm-remote-monitor using Playwright.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/playwright-adoption-proposal.md` | 316 lines, 4-phase plan |

**Key Points**:
- Current: 78 Mocha tests, no E2E, browser testing disabled
- Recommendation: Playwright over Cypress (multi-browser, Socket.IO)
- Effort: ~5-8 days initial investment
- Benefits: Safe refactoring, UI regression detection, cross-browser

---

### cgm-remote-monitor Database Layer Audit (2026-01-29)

Full audit of Nightscout's MongoDB storage layer for Loop compatibility.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-database-deep-dive.md` | 455 lines, 6 collections, indexes, ordering |
| **Gaps** | `traceability/gaps.md` | GAP-DB-001/002/003 added |

**Key Findings**:
- MongoDB driver 3.6.0 (compatible with MongoDB 5.x)
- Treatment batch ordering preserved via `async.eachSeries`
- Loop's ordering requirement is satisfied
- Entries use `forEach` (unordered) but not critical for Loop
- API v3 uses `identifier` field with fallback deduplication

---

### Loop Sync Identity Fields Extraction (2026-01-29)

Extracted sync identity patterns from Loop/LoopKit for cross-project comparison.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Mapping** | `mapping/loop/sync-identity-fields.md` | 318 lines, syncIdentifier + ObjectIdCache patterns |
| **Gaps** | `traceability/gaps.md` | GAP-SYNC-005/006/007 added |

**Key Findings**:
- Loop uses `syncIdentifier` (pump hex or UUID) as primary identity
- `ObjectIdCache` maps to Nightscout `_id` (24-hour memory-only)
- Uses v1 POST only - no server-side deduplication
- Duplicates possible on app restart due to cache loss

---

### nightscout-librelink-up Deep Dive (2026-01-29)

Full audit of LibreLink Up to Nightscout bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/nightscout-librelink-up-deep-dive.md` | 378 lines |

#### Key Findings

| Component | Purpose | Details |
|-----------|---------|---------|
| LibreLink API | Auth + glucose fetch | 8 regions, stealth mode |
| Interfaces | TypeScript models | GlucoseItem, Connection |
| Nightscout | v1 upload only | v3 stub exists |

| Feature | Status |
|---------|--------|
| Multi-patient | ✅ Supported |
| Historical backfill | ❌ Not implemented |
| API v3 | ❌ Stub only |

**Gaps Identified**: GAP-LIBRELINK-001, GAP-LIBRELINK-002, GAP-LIBRELINK-003

---

### tconnectsync Deep Dive (2026-01-29)

Full audit of Tandem t:connect to Nightscout sync tool.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/tconnectsync-deep-dive.md` | 368 lines |

#### Key Findings

| Component | Purpose | Files |
|-----------|---------|-------|
| API | t:connect OAuth2/OIDC auth | 7 files, 1400+ lines |
| Domain | Bolus, TherapyEvent, Profile | 3 key models |
| Sync | NS v1 API upload | 10+ treatment types |

| Treatment Type | NS eventType |
|----------------|--------------|
| Combo Bolus | `Combo Bolus` |
| Temp Basal | `Temp Basal` |
| Site Change | `Site Change` |
| Exercise/Sleep | `Exercise`, `Sleep` |

**Gaps Identified**: GAP-TCONNECT-001, GAP-TCONNECT-002, GAP-TCONNECT-003

---

### OpenAPS/oref0 Deep Dive (2026-01-29)

Full audit of the foundational OpenAPS ecosystem - the original DIY closed-loop system.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/openaps-oref0-deep-dive.md` | 371 lines, 2 repos |

#### Key Findings

| Component | Purpose | Language |
|-----------|---------|----------|
| openaps | Device toolkit (pump/CGM drivers) | Python |
| oref0 | Reference algorithm (determine-basal) | JavaScript |

| Algorithm File | Lines | Function |
|----------------|-------|----------|
| determine-basal.js | 1192 | Main dosing calculation |
| autosens.js | 454 | Sensitivity detection |
| cob.js | 211 | Carbs on board |
| iob/history.js | 572 | IOB history processing |

**Gaps Identified**: GAP-OREF-001, GAP-OREF-002, GAP-OREF-003

---


> **Archive**: 2026-01-28 entries moved to [progress-archive-2026-01-28.md](docs/archive/progress-archive-2026-01-28.md)

---
