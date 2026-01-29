# Progress Archive: 2026-01-29 (Batch 1)
- Trio: Full (push notifications)
- AAPS: None (uses SMS instead)
- xDrip+: None (display only)

**Source Files Analyzed**:
- `ns:lib/api/remotecommands/index.js`
- `ns:lib/server/remotecommands.js`
- `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/*.swift`

---

### Insulin Profiles API Specification (2026-01-29)

OpenAPI 3.0 specification for Insulin Profiles collection based on PR#8261 and cross-project analysis.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **OpenAPI Spec** | `specs/openapi/aid-insulin-2025.yaml` | 576 lines, 5 endpoints, full schema |
| **Gap Updated** | `traceability/aid-algorithms-gaps.md` | GAP-INSULIN-001 marked addressed |
| **Terminology** | `mapping/cross-project/terminology-matrix.md` | Added Insulin Profiles section |

**Key Schema Fields**:
- `name` (string) - Insulin type name (NovoRapid, Fiasp, etc.)
- `dia` (number) - Duration of Insulin Action in hours
- `peak` (integer) - Time to peak activity in minutes
- `curve` (enum) - Activity model (rapid-acting, ultra-rapid, bilinear, etc.)
- `active` (enum) - Bolus or basal designation
- `concentration` (enum) - U100/U200/U300/U500

**Bug Found**: PR#8261 /insulin/basal endpoint calls bolus() function (line 28)

**Controller Support**:
- xDrip+: Full (InsulinInjection.insulin)
- AAPS: Partial (insulinConfiguration not synced)
- nightscout-reporter: Read-only
- Loop/Trio: Not supported

---

### Heart Rate API Specification (2026-01-29)

OpenAPI 3.0 specification for HeartRate collection based on PR#8083 and AAPS entity.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **OpenAPI Spec** | `specs/openapi/aid-heartrate-2025.yaml` | 447 lines, 6 endpoints, full schema |
| **Gap Updated** | `traceability/gaps.md` | GAP-API-HR marked addressed |
| **Requirement** | `traceability/requirements.md` | REQ-PR-001 linked to spec |

**Key Schema Fields**:
- `beatsPerMinute` (double) - HR value in BPM
- `timestamp` (int64) - Epoch milliseconds
- `duration` (int64) - Sampling window
- `device` (string) - Source device
- `identifier` (uuid) - Sync identity

**Controller Support**:
- AAPS: Full (primary source)
- Loop/Trio: None
- xDrip+: Partial (display only)

---

### Statistics API Proposal (2026-01-29)

Comprehensive API specification for server-side glucose statistics with MCP integration.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Proposal** | `docs/sdqctl-proposals/statistics-api-proposal.md` | 480 lines, 6 endpoints, MCP resources |
| **Gaps** | `traceability/gaps.md` | GAP-STATS-001/002/003 added |
| **Requirements** | `traceability/requirements.md` | REQ-STATS-001-005 added |

**Key Features**:
- `/api/v3/stats/daily` - Per-day glucose aggregations
- `/api/v3/stats/summary` - Period summaries with A1C/GMI
- `/api/v3/stats/hourly` - Hourly percentile distributions
- `/api/v3/stats/treatments` - Insulin/carb aggregations
- MCP resources for AI integration

**Benefits**:
- 90% reduction in data transfer for reports
- Server-side caching with MongoDB aggregation
- Standard formulas: A1C (DCCT/IFCC), GMI, GVI, PGS

---

### cgm-remote-monitor PR Analysis (2026-01-29)

Analysis of 68 open PRs for ecosystem impact and project trajectory.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **PR Analysis** | `docs/10-domain/cgm-remote-monitor-pr-analysis.md` | 380 lines, 68 PRs categorized |
| **Gaps** | `traceability/gaps.md` | GAP-API-HR, GAP-INSULIN-001, GAP-REMOTE-CMD, GAP-TZ-001 |
| **Requirements** | `traceability/requirements.md` | REQ-PR-001/002/003/004 added |

**Key Findings**:
- 68 open PRs spanning 2021-2026
- PR#8083 (Heart Rate) blocked AAPS integration for 2.5 years
- PR#8261 (Multi-Insulin) already used by xDrip+/reporter but not merged
- PR#7791 (Remote Commands) critical Loop caregiver feature stalled 3+ years
- Active modernization wave: Lodash, Moment, crypto-browserify removal

**Tier 1 Ecosystem PRs**:
1. #8421 MongoDB 5x (bewest) - 117 files
2. #8083 Heart Rate (buessow) - AAPS blocked
3. #8261 Multi-Insulin (gruoner) - in production
4. #7791 Remote Commands (gestrich) - Loop caregivers

---

### cgm-remote-monitor Frontend Audit (2026-01-29)

Comprehensive analysis of Nightscout's client-side architecture, D3.js charts, and plugin UI.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-frontend-deep-dive.md` | 468 lines, D3, plugins, i18n |
| **Gaps** | `traceability/gaps.md` | GAP-UI-001/002/003 added |
| **Requirements** | `traceability/requirements.md` | REQ-UI-001/002/003 added |

**Key Findings**:
- Webpack bundles: main, clocks, reports
- D3.js dual-view chart: focus (70%) + context (30%) with brush
- Plugin UI: 4 container types (pill-major/minor/status, drawer)
- 33 languages via JSON translation files
- Vanilla JS/jQuery architecture (no component framework)

**Recommendations**:
1. Document frontend architecture for contributors
2. Add chart accessibility (ARIA, keyboard nav)
3. Implement offline data caching

---

### cgm-remote-monitor Authentication Audit (2026-01-29)

Comprehensive analysis of Nightscout's authorization system, Shiro permissions, and token handling.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-auth-deep-dive.md` | 475 lines, Shiro, JWT, roles |
| **Gaps** | `traceability/gaps.md` | GAP-AUTH-003/004/005 added |
| **Requirements** | `traceability/requirements.md` | REQ-AUTH-001/002/003 added |

**Key Findings**:
- Shiro-style hierarchical permissions: `domain:collection:action`
- 7 default roles (admin, readable, careportal, devicestatus-upload, etc.)
- API_SECRET grants full `*` admin access, bypassing RBAC
- JWT tokens: 8-hour lifetime, symmetric key signing
- Rate limiting: 5 seconds per failed attempt, cumulative

**Recommendations**:
1. Document all permission strings
2. Add token revocation mechanism
3. Deprecate API_SECRET for write operations

---

### cgm-remote-monitor Sync/Upload Audit (2026-01-29)

Comprehensive analysis of Nightscout's real-time sync, Socket.IO architecture, and upload handlers.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-sync-deep-dive.md` | 520 lines, WebSocket, sync identity |
| **Gaps** | `traceability/gaps.md` | GAP-SYNC-008/009/010 added |
| **Requirements** | `traceability/requirements.md` | REQ-SYNC-001/002/003 added |

**Key Findings**:
- Socket.IO uses 3 namespaces (`/`, `/alarm`, `/storage`)
- Delta compression: only changes broadcast, 512-byte threshold
- Sync identity: UUID v5 from device+date+eventType
- 3-tier dedup: identifier → _id → fallback fields
- LoadRetro: 24-hour devicestatus history on demand

**Recommendations**:
1. Document WebSocket API with event schemas
2. Backfill identifier field in v1 API uploads
3. Return sync metadata in upload responses

---

### cgm-remote-monitor Plugin System Audit (2026-01-29)

Comprehensive analysis of Nightscout's 38-plugin architecture and data pipeline.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-plugin-deep-dive.md` | 436 lines, IOB/COB, Loop/OpenAPS |
| **Gaps** | `traceability/gaps.md` | GAP-PLUGIN-001/002/003 added |
| **Requirements** | `traceability/requirements.md` | REQ-PLUGIN-001/002/003 added |

**Key Findings**:
- 38 plugins with standardized lifecycle (setProperties, checkNotifications)
- IOB/COB use device-first with treatment fallback calculation
- Loop: single prediction array; OpenAPS: 6 curves (IOB, ZT, COB, aCOB, UAM)
- AAPS uses OpenAPS plugin (no dedicated AAPS plugin)
- Typo tolerance: accepts both `received` and `recieved` fields

**Recommendations**:
1. Document devicestatus schema per controller
2. Normalize prediction format in visualization
3. Document IOB/COB calculation models

---

### cgm-remote-monitor API Layer Audit (2026-01-29)

Comprehensive analysis of Nightscout's v1 and v3 REST API architecture.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/cgm-remote-monitor-api-deep-dive.md` | 397 lines, v1/v3 comparison, dedup logic |
| **Gaps** | `traceability/gaps.md` | GAP-API-006/007/008 added |
| **Requirements** | `traceability/requirements.md` | REQ-API-001/002/003 added |

**Key Findings**:
- v3 API uses UPSERT semantics (duplicates updated, not rejected)
- Dedup keys: treatments use `created_at + eventType`, entries use `date + type`
- Socket.IO broadcasts via `dataUpdate` event to `DataReceivers` room
- Shiro-style permissions: `api:collection:action`

**Recommendations**:
1. Document dedup keys per collection in API spec
2. Generate OpenAPI 3.0 specification for v3
3. Standardize timestamp field names across collections

---

