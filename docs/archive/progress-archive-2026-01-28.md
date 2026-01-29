# Progress Archive: 2026-01-28
### Prediction Array Formats Comparison (2026-01-28)

Cross-system analysis of glucose prediction array formats across Loop, AAPS, and Trio.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/prediction-arrays-comparison.md` | 319 lines, 3 systems |

#### Key Findings

| System | Prediction Model | devicestatus Field |
|--------|------------------|-------------------|
| Loop | Single combined curve | `loop.predicted.values` |
| AAPS | 4 separate curves (IOB/COB/UAM/ZT) | `openaps.suggested.predBGs.*` |
| Trio | 4 separate curves (IOB/COB/UAM/ZT) | `openaps.suggested.predBGs.*` |

**Gaps Identified**: GAP-PRED-002, GAP-PRED-003, GAP-PRED-004

---

### Batch Operation Ordering Deep Dive (2026-01-28)

Analysis of sync order requirements and ID mapping patterns across Loop, AAPS, Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/batch-ordering-deep-dive.md` | 334 lines |

#### Key Findings

| System | Strategy | Order Sensitive |
|--------|----------|-----------------|
| Loop | v1 batch + zip() | ✅ Critical |
| AAPS | Sequential v3 | ❌ N/A |
| NS v3 | Single-doc only | ❌ N/A |

**Key Recommendation**: Parse `identifier` from response, not positional matching.

---

### Override/Profile Switch Comparison (2026-01-28)

Cross-system analysis of therapy adjustment semantics across Loop, AAPS, and Trio.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/override-profile-switch-comparison.md` | 331 lines, 3 systems |

#### Key Findings

| System | Model | NS eventType |
|--------|-------|--------------|
| Loop | TemporaryScheduleOverride | Temporary Override |
| AAPS | ProfileSwitch + TempTarget | Profile Switch + Temporary Target |
| Trio | Override + TempTarget | Temporary Override + Temporary Target |

**Gaps Identified**: GAP-OVERRIDE-001 through GAP-OVERRIDE-004

---

### Remote Bolus Command Comparison (2026-01-28)

Cross-system analysis of remote bolus handling in Loop, AAPS, Trio, and Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison** | `docs/10-domain/remote-bolus-comparison.md` | 348 lines, 4 systems |

#### Key Findings

| System | Auth | Key Safety Feature |
|--------|------|-------------------|
| Loop | OTP + APNs | 5-min expiration |
| AAPS | SMS passcode | 15-min distance |
| Trio | AES-256 | 20% rule + IOB check |
| Nightscout | API secret | Relay only (no limits) |

**Gaps Identified**: GAP-REMOTE-001 through GAP-REMOTE-004

---

### Nightscout v3 Treatments Schema (2026-01-28)

Extracted authoritative treatments schema from origin Nightscout server.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Schema** | `mapping/nightscout/v3-treatments-schema.md` | 248 lines, 21+ eventTypes |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **eventTypes** | 21+ types (careportal + OpenAPS plugins) |
| **Date formats** | Accepts ms, seconds, or ISO-8601 |
| **Deduplication** | By identifier or `created_at + eventType` |
| **Duration** | Always minutes |

#### NS vs AAPS Comparison
- AAPS has `pumpId`/`pumpSerial` for dedup (NS doesn't)
- AAPS has bolus `type` field (NORMAL/SMB)
- eventTypes mostly compatible (different naming)

---

### Modernization Analysis: cgm-remote-monitor vs Nocturne (2026-01-28)

Comprehensive comparison of original Nightscout server vs Nocturne .NET rewrite.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Analysis** | `docs/sdqctl-proposals/nocturne-modernization-analysis.md` | 350 lines, full comparison |

#### Key Findings

| Aspect | cgm-remote-monitor | Nocturne |
|--------|-------------------|----------|
| Codebase | 35K LOC JS | 334K LOC C# |
| Plugins | 38 | Service-based |
| Connectors | Via bridges | 8 native |
| API Parity | v1/v2/v3 (origin) | v1/v2/v3 + v4 |
| Database | MongoDB | PostgreSQL |

#### Recommendation
Both should be maintained for ecosystem diversity. Nocturne viable for new deployments; migration requires testing.

---

### share2nightscout-bridge Audit (2026-01-28)

Complete audit of Dexcom Share → Nightscout bridge.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/share2nightscout-bridge-deep-dive.md` | 328 lines, full flow |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **Scale** | 447 lines JavaScript, single file |
| **Dexcom API** | Auth + Login + Fetch (US/EU servers) |
| **Output** | Nightscout API v1 `/api/v1/entries.json` only |
| **Poll Interval** | 2.5 minutes default |
| **Trend Mapping** | 10 Dexcom trends → Nightscout directions |

#### Gaps Identified
- GAP-SHARE-001: No Nightscout API v3 support
- GAP-SHARE-002: No backfill/gap detection logic
- GAP-SHARE-003: Hardcoded application ID may break

---

### Nocturne Initial Audit (2026-01-28)

Complete architectural audit of Nocturne - .NET 10 rewrite of Nightscout.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/nocturne-deep-dive.md` | 279 lines, full architecture |

#### Key Findings

| Aspect | Details |
|--------|---------|
| **Scale** | 927 C# files, 438 Svelte components, ~334K LOC |
| **API Parity** | Full v1/v2/v3 compatibility confirmed |
| **Connectors** | 8 native (Dexcom, Libre, Glooko, MiniMed, MFP, NS, TConnect, Tidepool) |
| **Algorithm** | Native Rust oref with FFI/WASM support |
| **Frontend** | SvelteKit 2 + Svelte 5 + Tailwind CSS 4 |

#### Architecture Comparison

| cgm-remote-monitor | Nocturne |
|-------------------|----------|
| JavaScript/Node.js | C# .NET 10 |
| MongoDB | PostgreSQL |
| Socket.IO | SignalR |
| JS oref | Rust oref |

#### Gaps Identified
- GAP-NOCTURNE-001: V4 endpoints Nocturne-specific
- GAP-NOCTURNE-002: Rust oref may diverge from JS
- GAP-NOCTURNE-003: SignalR→Socket.IO bridge latency

---

### AAPS NSClient Schema Extraction (2026-01-28)

Documented complete Nightscout upload schema from AAPS NSClient SDK.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **NSClient Schema** | `mapping/aaps/nsclient-schema.md` | 70+ fields across 3 collections |
| **README Update** | `mapping/aaps/README.md` | Added to documentation index |

#### Key Findings

| Collection | Fields | Key Types |
|------------|--------|-----------|
| `treatments` | 50+ | Bolus, Carbs, TempBasal, ProfileSwitch, TempTarget |
| `entries` | 15 | SGV with direction, noise, filtered/unfiltered |
| `devicestatus` | 20+ | Pump, OpenAPS (suggested/enacted), Configuration |

#### EventType Enum (25 types)
Site management, CGM, Glucose, Bolus, Carbs, Targets, Profile, Basal, Notes

#### Unit Conventions Documented
- `duration`: minutes (Nightscout) vs milliseconds (AAPS internal)
- `utcOffset`: minutes
- `durationInMilliseconds`: AAPS-specific field

---

### Workspace Expansion (2026-01-28)

Added 4 new repositories from live backlog requests. Workspace now has 20 repos.

| Repo | URL | Branch | Purpose |
|------|-----|--------|---------|
| `nocturne` | nightscout/nocturne | main | Nightscout client app |
| `Trio-dev` | nightscout/Trio | dev | Trio development branch |
| `share2nightscout-bridge` | nightscout/share2nightscout-bridge | dev | Dexcom Share bridge |
| `cgm-remote-monitor-official` | nightscout/cgm-remote-monitor | dev | Official NS server |

---

### Cross-Project Test Harness Tooling (2026-01-28)

Implemented new tooling for cross-project integration testing and unit conversion validation.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Unit Conversion Tests** | `tools/test_conversions.py` | 20 test cases for time/glucose/insulin conversions |
| **Conversion Fixtures** | `conformance/unit-conversions/conversions.yaml` | GAP-TREAT validated conversions |
| **Mock Nightscout Server** | `tools/mock_nightscout.py` | In-memory API v1/v3 mock |
| **Makefile Targets** | `Makefile` | `make conversions`, `make mock-nightscout` |
| **Tooling Backlog** | `docs/sdqctl-proposals/backlogs/tooling.md` | Updated with harness roadmap |

#### Key Features

| Tool | Capability |
|------|------------|
| `test_conversions.py` | Validates time (s/ms/min), glucose (mg/dL↔mmol/L), insulin precision |
| `mock_nightscout.py` | POST/GET/PUT/DELETE for entries, treatments, devicestatus |

#### Conversions Tested

- Loop `absorptionTime` (seconds) → Nightscout (minutes)
- AAPS `duration` (milliseconds) → Nightscout (minutes)
- Glucose mg/dL ↔ mmol/L (factor: 18.0182)
- Insulin/carb precision preservation

---

### Timezone/DST Handling Deep Dive (2026-01-28)

Comprehensive cross-project analysis of timezone and DST handling across the Nightscout ecosystem. Documented how each system stores, interprets, and synchronizes timezone information.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Terminology Matrix Update** | `mapping/cross-project/terminology-matrix.md` | Expanded Timezone Handling section with 7 detailed tables |
| **New Gaps (4)** | `traceability/gaps.md` | GAP-TZ-004 through GAP-TZ-007 |

#### Key Findings

| System | TZ Storage | DST Aware | Key Issue |
|--------|-----------|-----------|-----------|
| **Nightscout** | IANA string in profile | ✅ Yes (moment-tz) | Recalculates utcOffset from dateString |
| **Loop** | `TimeZone` object (fixed offset) | ✅ Yes (Foundation) | Uses non-standard `ETC/GMT` format |
| **AAPS** | `utcOffset: Long` (ms) | ❌ No (fixed at capture) | Cannot reconstruct DST status historically |
| **Trio** | From NS profile | ✅ Yes (via NS) | Inherits NS timezone |
| **oref0** | Uses `moment-timezone` | ✅ Yes | N/A (no profile storage) |

#### Pump DST Support

| Status | Pumps |
|--------|-------|
| **✅ Can handle DST** | Medtrum, Combo v2 |
| **❌ Cannot handle DST** | Medtronic, Omnipod DASH/Eros, Dana RS/R, Equil |

#### New Gaps Documented

| Gap ID | Description |
|--------|-------------|
| **GAP-TZ-004** | utcOffset unit mismatch: Nightscout uses minutes, AAPS uses milliseconds |
| **GAP-TZ-005** | AAPS fixed offset storage breaks historical DST analysis |
| **GAP-TZ-006** | Loop uploads non-standard `ETC/GMT` timezone format (and NS workaround is buggy) |
| **GAP-TZ-007** | Missing timezone fallback uses server local time |

**Source Files Analyzed**:
- `externals/AndroidAPS/database/entities/interfaces/DBEntryWithTime.kt`
- `externals/AndroidAPS/core/data/pump/defs/TimeChangeType.kt`
- `externals/LoopWorkspace/LoopKit/LoopKit/DailyValueSchedule.swift`
- `externals/LoopWorkspace/RileyLinkKit/Common/TimeZone.swift`
- `externals/cgm-remote-monitor/lib/profilefunctions.js`
- `externals/cgm-remote-monitor/lib/api3/generic/collection.js`
- `externals/AndroidAPS/pump/medtrum/src/main/kotlin/.../SetTimeZonePacket.kt`

---
