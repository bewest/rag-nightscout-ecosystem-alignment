# Progress Archive: 2026-01-29 (Batch 2)
**Key Findings**:
- 193 files, 74,644 lines across 5 directories
- Structure is fundamentally sound
- Naming conventions are consistent
- Some missing index files identified

**Recommendations**: Add README to docs/10-domain/, add cross-references to profile files.

---

### Profile Collection Deep Dive - Gaps Migration (2026-01-29)

Found existing comprehensive comparison (557 lines). Migrated 4 gaps to traceability.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Comparison Doc** | `docs/60-research/profile-therapy-settings-comparison.md` | 557 lines (pre-existing) |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-PROFILE-001 through 004 |

**Key Findings** (from existing doc):
- Loop uses HealthKit units; Nightscout uses strings
- AAPS uses duration blocks; Nightscout uses start-time arrays
- Loop has no profile naming (single anonymous profile)
- Loop upload-only; Trio download-only; AAPS bidirectional

**Gaps Migrated**:
| Gap ID | Issue |
|--------|-------|
| GAP-PROFILE-001 | Unit representation mismatch (HKQuantity vs string) |
| GAP-PROFILE-002 | Time block vs start-time format |
| GAP-PROFILE-003 | Loop has no profile naming |
| GAP-PROFILE-004 | Loop doesn't download profiles |

---

### Algorithm Terminology Mapping - Already Complete (2026-01-29)

Verified terminology matrix (3024 lines) already has comprehensive coverage:

| Section | Coverage |
|---------|----------|
| ISF/CR/DIA/UAM | Lines 490-500, 1170-1230 |
| Prediction methodology | Lines 1172-1180 |
| Carb absorption models | Lines 1182-1189 |
| Sensitivity mechanisms | Lines 1191-1198 |
| GAP-ALG-001 through 007 | Lines 1202-1210 |

No new work needed - terminology already documented.

---

### Device Status Collection Deep Dive - Gaps Migration (2026-01-29)

Found existing comprehensive deep dive (863 lines). Migrated 4 gaps to traceability.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/devicestatus-deep-dive.md` | 863 lines (pre-existing) |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-DS-001 through 004 |

**Key Findings** (from existing doc):
- Loop uses flat `loop` object; oref0 systems use nested `openaps` object
- Loop: single combined prediction; oref0: 4 curves (IOB, COB, UAM, ZT)
- Duration units differ: Loop=seconds, oref0=minutes
- Loop exposes less algorithm state than oref0

**Gaps Migrated**:
| Gap ID | Issue |
|--------|-------|
| GAP-DS-001 | No effect timelines in Loop |
| GAP-DS-002 | Prediction array incompatibility |
| GAP-DS-003 | Duration unit inconsistency |
| GAP-DS-004 | Missing algorithm transparency in Loop |

---

### nightscout-connect Design Review (2026-01-29)

Comprehensive design review of nightscout-connect XState architecture, vendor extensibility, and refactoring suggestions.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Design Review** | `docs/10-domain/nightscout-connect-design-review.md` | 340 lines, 7 refactoring suggestions |
| **Gaps Added** | `traceability/connectors-gaps.md` | GAP-CONNECT-004 through 006 |

**Key Findings**:
- Excellent XState usage: hierarchical machines, parallel states, service injection
- 5 vendors supported: Nightscout, Dexcom Share, Glooko, LibreLinkUp, Minimed Carelink
- Clean builder pattern for vendor registration
- Uses exponential backoff, schedule alignment, session reuse

**Refactoring Priorities**:
1. Add `@xstate/test` model-based testing (no tests currently)
2. Add API v3 output driver (v1 only)
3. Add TypeScript type definitions

**Gaps Identified**:
| Gap ID | Issue |
|--------|-------|
| GAP-CONNECT-004 | No test suite |
| GAP-CONNECT-005 | No TypeScript types |
| GAP-CONNECT-006 | Brittle adapter pattern |

**Source Files**:
- `externals/nightscout-connect/lib/builder.js`
- `externals/nightscout-connect/lib/machines/*.js`
- `externals/nightscout-connect/machines.md`

---

### Nightscout API v3 Deep Dive (2026-01-29)

Comprehensive analysis of Nightscout API v3 architecture, collections, operations, and sync patterns.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/nightscout-apiv3-deep-dive.md` | 290 lines, 6 collections, 8 operations |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-API3-001 through GAP-API3-003 |
| **Requirements** | `traceability/nightscout-api-requirements.md` | REQ-API3-001 through REQ-API3-003 |

**Key Findings**:
- 6 collections: devicestatus, entries, food, profile, settings, treatments
- 8 operations per collection: SEARCH, CREATE, READ, UPDATE, PATCH, DELETE, HISTORY, plus version endpoints
- shiro-trie permission model: `api:{collection}:{operation}`
- Query operators: eq, ne, gt, gte, lt, lte, in, nin, re
- Deduplication via `identifier` with per-collection fallback fields
- History endpoint returns soft-deleted docs (`isValid=false`) for sync completeness

**Gaps Identified**:
| Gap ID | Issue |
|--------|-------|
| GAP-API3-001 | No batch operations for bulk sync |
| GAP-API3-002 | Offset pagination inefficient for large datasets |
| GAP-API3-003 | Field projection lacks exclusion syntax |

**Source Files**:
- `externals/cgm-remote-monitor/lib/api3/index.js`
- `externals/cgm-remote-monitor/lib/api3/generic/setup.js`
- `externals/cgm-remote-monitor/lib/api3/generic/search/input.js`
- `externals/cgm-remote-monitor/lib/api3/generic/history/operation.js`

---

### Hygiene: Chunk progress.md (2026-01-29)

Maintenance task to reduce progress.md from 1713 to 807 lines (53% reduction).

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Archive** | `docs/archive/progress-archive-2026-01-17-to-23.md` | 916 lines, Jan 17-23 entries |
| **Current** | `progress.md` | 807 lines, Jan 28-29 entries |

**Approach**: Split at date boundary (2026-01-28), archive older entries, add link header.

---

### Authentication Flows Deep Dive (2026-01-29)

Comprehensive analysis of Nightscout authentication and authorization system.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **Deep Dive** | `docs/10-domain/authentication-flows-deep-dive.md` | 362 lines, 3 auth methods, 4 gaps |
| **Gaps Added** | `traceability/nightscout-api-gaps.md` | GAP-AUTH-001 through GAP-AUTH-004 |
| **Terminology** | `mapping/cross-project/terminology-matrix.md` | Added Authentication Concepts section |

**Key Findings**:
- API_SECRET grants full `*` access, bypassing RBAC
- JWT secret stored in node_modules (lost on npm update)
- No account lockout (only delay list)
- enteredBy field unverified
- No token revocation mechanism

**Client Auth Patterns**:
| Client | Method | Transport |
|--------|--------|-----------|
| AAPS | Access Token | WebSocket |
| Loop | API Secret | REST |
| xDrip+ | SHA1 Secret | REST |

---

### Remote Commands API Specification (2026-01-29)

OpenAPI 3.0 specification for Remote Commands collection based on PR#7791 and Loop RemoteCommand protocol.

| Deliverable | Location | Summary |
|-------------|----------|---------|
| **OpenAPI Spec** | `specs/openapi/aid-commands-2025.yaml` | 738 lines, 7 endpoints, full schema |
| **Gap Updated** | `traceability/nightscout-api-gaps.md` | GAP-REMOTE-CMD marked addressed |
| **Terminology** | `mapping/cross-project/terminology-matrix.md` | Added Remote Commands section |

**Key Schema Features**:
- 4 action types: bolus, carbs, override, cancelOverride
- State machine: Pending → In-Progress → Complete/Error
- OTP security validation
- Push notification integration (APNs)

**Controller Support**:
