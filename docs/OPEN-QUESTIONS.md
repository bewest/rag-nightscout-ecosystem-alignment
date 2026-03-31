# Open Questions

> **Purpose**: Central registry of unresolved questions that block work or require decisions.  
> **Last Updated**: 2026-01-28  
> **Usage**: Route blocked items here; update when questions are resolved.

---

## Blocking (Need Answer to Proceed)

Questions that directly block active backlog items.

### OQ-001: syncId vs identifier relationship

**Question**: How does the proposed `syncId` field relate to API v3's existing `identifier`?

**Context**: ADR-002 proposes a new `syncId` field for unified sync identity. However, API v3 already uses `identifier` for client-provided document identity. Are these the same concept with different names, or different concepts?

**Options**:
1. Make `syncId` an alias for `identifier` in v3 (same field, two names)
2. Keep them separate - `identifier` for v3 addressing, `syncId` for cross-controller dedup
3. Deprecate `identifier` in favor of `syncId`

**Blocks**: ADR-002 Phase 2/3 implementation, REQ-030 testing

**Owner**: TBD - needs Nightscout maintainer input

**Action**: Queue code analysis to trace `identifier` usage in cgm-remote-monitor API v3 vs `syncIdentifier` in Loop/Trio uploads

**Related**: 
- [ADR-002: Sync Identity Strategy](90-decisions/adr-002-sync-identity-strategy.md)
- [GAP-003](../traceability/gaps.md#gap-003-no-unified-sync-identity-field-across-controllers)
- [GAP-API-002](../traceability/gaps.md#gap-api-002-identifier-vs-_id-addressing-inconsistency)

---

### OQ-002: Batch response order guarantee

**Question**: Should Nightscout guarantee that batch response items are in the same order as request items?

**Context**: Loop maps `syncIdentifier` to `objectId` by position after batch uploads. If server returns items out of order, mappings are corrupted.

**Options**:
1. Server MUST maintain order - add to API spec and test
2. Server returns identifier in each response item - clients match by key
3. Clients should not rely on order - require identifiers

**Resolution**: ✅ **Verified - Nightscout already preserves order.**

Analysis (2026-01-29) confirmed:
- Loop uses positional matching via `zip()` (`NightscoutService.swift:209-214`)
- Nightscout API v1 uses `async.eachSeries()` (`lib/server/treatments.js:21`) - sequential processing preserves order
- Response includes full object with `_id` added

**Requirement Added**: REQ-036 (Batch Response Order Preservation)

**Status**: ✅ Resolved - documented as requirement, no code changes needed

**Owner**: N/A - verified behavior

**Related**:
- [REQ-036](../traceability/requirements.md#req-036-batch-response-order-preservation)
- [GAP-BATCH-002](../traceability/gaps.md#gap-batch-002-response-order-critical-for-loop-syncidentifier-mapping)

---

### OQ-003: Override OTP validation requirement

**Question**: Should override remote commands require OTP validation like bolus/carb commands?

**Context**: Loop's override commands explicitly return `otpValidationRequired() -> Bool { return false }` while bolus/carb commands require OTP. This means anyone with API access can issue override commands without secondary authentication.

**Options**:
1. Require OTP for overrides (consistent with bolus/carb)
2. Keep current behavior (overrides are less dangerous than insulin delivery)
3. Make OTP configurable per command type

**Resolution**: Nightscout already requires API_SECRET or NS JWT/token authorization before any remote commands can be sent. OTP is a *second factor* on top of Nightscout auth. Current behavior (no OTP for overrides) is acceptable given NS auth is required.

**Status**: ✅ Resolved - keep current behavior, document that NS auth is the primary gate

**Owner**: Loop/Trio maintainers

**Related**:
- [GAP-REMOTE-001](../traceability/gaps.md#gap-remote-001-remote-command-authorization-unverified)
- [Authority Model](10-domain/authority-model.md)

---

## Design (Need ADR)

Questions requiring formal architectural decision records.

### OQ-010: ProfileSwitch → Override mapping ✅ RESOLVED + EXTENDED

**Question**: Should AAPS ProfileSwitch be accepted as a valid representation of overrides, or must there be explicit mapping?

**Resolution**: [ADR-004](90-decisions/adr-004-profile-override-mapping.md) - Dual-representation acceptance with explicit mapping rules

**Decision Summary**:
1. Accept both Override (Loop/Trio) and ProfileSwitch (AAPS) as valid
2. Define semantic equivalence rules for cross-system translation
3. Require percentage application at query time (addresses GAP-OREF-001)
4. Recommend StateSpan model for profile history
5. Provide explicit cross-query translation rules

**Analysis Progress** (7/7 complete):
1. ✅ Nocturne ProfileSwitch treatment model ([analysis](10-domain/nocturne-profileswitch-analysis.md))
2. ✅ Nocturne percentage/timeshift handling ([analysis](10-domain/nocturne-percentage-timeshift-handling.md))
3. ✅ Nocturne vs cgm-remote-monitor Profile sync ([comparison](10-domain/nocturne-cgm-remote-monitor-profile-sync.md))
4. ✅ Nocturne Override/Temporary Target representation ([analysis](10-domain/nocturne-override-temptarget-analysis.md))
5. ✅ Nocturne V4 ProfileSwitch extensions ([analysis](10-domain/nocturne-v4-profile-extensions.md))
6. ✅ Nocturne Rust oref profile handling ([analysis](10-domain/nocturne-rust-oref-profile-analysis.md))
7. ✅ ADR-004 draft ([decision](90-decisions/adr-004-profile-override-mapping.md))

**Extended Research** (2026-01-30): 11 additional Nocturne-focused items queued:
- Sync-identity backlog #12-18: SignalR bridge, Rust oref conformance, V4 StateSpan, PostgreSQL migration, connector coordination, srvModified gap, deletion semantics
- Nightscout-API backlog #6-9: V3 parity testing, eventType normalization, DData completeness, auth compatibility

See [Sync Identity Backlog - OQ-010 Extended](sdqctl-proposals/backlogs/sync-identity.md#oq-010-extended-nocturne-systematic-research)

**Gaps Addressed**: GAP-NOCTURNE-004/005, GAP-OVRD-005/006, GAP-OREF-001

**Related**:
- [ADR-004: ProfileSwitch → Override Mapping](90-decisions/adr-004-profile-override-mapping.md)
- [GAP-002](../traceability/gaps.md#gap-002-aaps-profileswitch-vs-override-semantic-mismatch)
- [Sync Identity Backlog](sdqctl-proposals/backlogs/sync-identity.md#oq-010-research-queue-profileswitch--nocturne)

---

### OQ-011: Extended/combo bolus representation

**Question**: What is the standard representation for extended and combo boluses across systems?

**Context**: 
- AAPS: `FAKE_EXTENDED` temp basal type
- Loop: Infers square wave from `duration >= 30min`
- Nightscout: Has `splitNow`/`splitExt` fields

**Options**:
1. Standardize on Nightscout's combo bolus fields
2. Add explicit `bolusType` enum: `EXTENDED`, `COMBO`, `NORMAL`
3. Document semantic mapping without schema change
4. Inversion of control: AID systems declare their entity types

**Action**: Queue code analysis to:
- Integrate all existing docs on this issue
- Analyze semantic meaning across systems
- Develop proposals with impact analysis for:
  - Standardization approach
  - Inversion of control (controllers declare types)

**Needs**: ADR after analysis

**Related**:
- [GAP-TREAT-004](../traceability/gaps.md#gap-treat-004-splitextended-bolus-representation-mismatch)

---

### OQ-012: Override supersession field schema

**Question**: What fields should be added to support override supersession tracking?

**Context**: When override B supersedes override A, we need to track this relationship. ADR-001 proposes a model but specific field names aren't finalized.

**Proposed Fields**:
- `superseded_by`: ID of superseding override
- `superseded_at`: Timestamp of supersession
- `status`: `active` | `completed` | `cancelled` | `superseded`
- `actualEndType`: `natural` | `early` | `deleted` | `superseded`

**Needs**: ADR-001 finalization

**Related**:
- [ADR-001: Override Supersession](90-decisions/adr-001-override-supersession.md)
- [GAP-001](../traceability/gaps.md#gap-001-nightscout-lacks-override-supersession-tracking)
- [GAP-SYNC-004](../traceability/gaps.md#gap-sync-004-override-supersession-not-tracked-in-sync)

---

## Strategic (Steering Direction)

Questions about priorities, scope, and project direction.

### OQ-020: cgm-remote-monitor vs Nocturne modernization path

**Question**: What is the recommended modernization path for Nightscout server?

**Context**: cgm-remote-monitor (v15.x) is mature but has legacy architecture. Nocturne is a newer client. Should we:
- Document gaps and proposals for cgm-remote-monitor evolution?
- Analyze Nocturne as a potential next-generation platform?
- Both?

**Source**: [LIVE-BACKLOG.md](../LIVE-BACKLOG.md) - "modernization plan for cgm-remote-monitor vs adopting Nocturne"

**Resolution**: Both - parallel analysis. Queue:
1. cgm-remote-monitor gap analysis and evolution proposals
2. Nocturne architecture audit
3. Interoperability spec focus (platform-agnostic)

**Owner**: Nightscout Foundation / Community

---

### OQ-021: Minimal viable interoperability spec

**Question**: What is the minimal set of fields and behaviors that ALL AID controllers should support?

**Context**: Current gaps document everything that differs. We need to identify the essential interoperability requirements that would enable reliable data exchange.

**Analysis Complete (2026-01-29)**:

Code analysis across Loop, AAPS, Trio, and Nightscout identified the common ground:

**Treatment Fields**: `created_at`, `eventType`, `enteredBy`, `insulin`, `carbs`
**DeviceStatus Fields**: `device`, `date`/`mills`, `openaps.iob`, `pump.battery.percent`, `pump.reservoir`, `uploader.battery`
**Behaviors**: ISO 8601 UTC timestamps, batch order preservation, dedup by `created_at` + `eventType` + `device`

**Status**: Fields identified. Formal spec creation queued in nightscout-api backlog (Item #11).

**Next Step**: Create `specs/minimal-interop-v1.yaml` (OpenAPI 3.0 format)

**Blocks**: Conformance test prioritization, spec versioning

**Owner**: Cross-maintainer consensus needed

---

### OQ-022: API v3 adoption timeline for iOS

**Question**: What would it take for Loop/Trio to support API v3?

**Context**: AAPS uses API v3 exclusively. Loop/Trio use v1 exclusively. This creates a split in the ecosystem where features like `isValid` deletion tracking aren't available to iOS apps.

**Blocks**: GAP-API-003 resolution, unified sync semantics

**Related**:
- [GAP-API-003](../traceability/gaps.md#gap-api-003-no-api-v3-adoption-path-for-ios-clients)

---

## Implementation (ADR Open Questions)

Questions explicitly listed in existing ADRs.

### From ADR-002: Sync Identity Strategy

| # | Question | Impact |
|---|----------|--------|
| 1 | Can we accelerate Phase 4 if adoption is fast? | Roadmap flexibility |
| 2 | Should Phase 4 block unregistered controllers? | Enforcement policy |
| 3 | How does `syncId` relate to v3's `identifier`? | Schema design (→ OQ-001) |
| 4 | Does `syncId` help with multi-site scenarios? | Scope expansion |

### From ADR-003: No Custom Credentials

| # | Question | Impact |
|---|----------|--------|
| 1 | How many identity providers should NRG support initially? | MVP scope |
| 2 | How to handle extended offline periods for mobile apps? | UX design |
| 3 | When can we deprecate Mode C (API secret)? | Migration timeline |
| 4 | What's the priority for enterprise SSO (SAML)? | Enterprise adoption |

---

## Unit & Format Questions

### OQ-030: Duration unit standardization

**Question**: Should we standardize duration units across the ecosystem?

**Current State**:
- Loop: seconds
- AAPS: milliseconds
- Nightscout: minutes

**Options**:
1. Standardize on minutes (Nightscout convention)
2. Use ISO 8601 durations (`PT30M`)
3. Add explicit unit field
4. Accept diversity - document conversions only

**Action**: Queue impact analysis for each alternative:
- Migration cost per option
- Breaking change assessment
- Implementation complexity
- Cross-system conversion reliability

**Related**:
- [GAP-TREAT-001](../traceability/gaps.md#gap-treat-001-absorption-time-unit-mismatch)
- [GAP-TREAT-002](../traceability/gaps.md#gap-treat-002-duration-unit-inconsistency)

---

### OQ-031: utcOffset unit standardization

**Question**: Should utcOffset be in minutes or milliseconds?

**Current State**:
- Nightscout: minutes
- AAPS internal: milliseconds

**Options**:
1. Standardize on minutes (Nightscout convention)
2. Accept diversity and document mapping

**Action**: Queue impact analysis (combine with OQ-030 duration analysis)

**Related**:
- [GAP-TZ-004](../traceability/gaps.md#gap-tz-004-utcoffset-unit-mismatch-between-nightscout-and-aaps)

---

## Resolved Questions

| ID | Question | Resolution | Date |
|----|----------|------------|------|
| OQ-002 | Batch response order guarantee | Verified - Nightscout preserves order via `async.eachSeries()`. Added REQ-036. | 2026-01-29 |
| OQ-003 | Override OTP validation requirement | Keep current behavior - NS auth is primary gate | 2026-01-28 |

---

## ML Pipeline & Anticipatory Management

### OQ-032: Override event label source

**Question**: Where do we get labeled override events for training the decision classifier (Layer 4)?

**Context**: No model can predict *when* an override should occur without labeled training data. Possible sources include Nightscout `treatments` with override-like `eventType` values, Loop's `overrideStatus`, or manual annotation.

**Options**:
1. Extract from Nightscout treatment logs (`eventType` containing Eating Soon, Exercise, custom notes)
2. Mine Loop `overrideStatus` field from devicestatus collection
3. Manual annotation of CGM traces
4. Combination — noisy automatic extraction refined by manual review

**Blocks**: GAP-ML-003, GAP-ML-005, all Layer 4 decision modeling

**Related**: `traceability/ml-gaps.md` GAP-ML-003

### OQ-033: Population vs personalized ML models

**Question**: Should we build population models first and then personalize, or start with strong single-patient models?

**Context**: cgmencode now trains across 50 diverse patient profiles simultaneously. The Transformer AE generalizes well (2.12 MAE). But real deployment needs per-patient personalization. Trade-off: population models have more data but blur individual physiology.

**Options**:
1. Population pre-train → per-patient fine-tune (standard transfer learning)
2. Meta-learning (MAML) for few-shot adaptation
3. Patient embedding vector as conditioning input

**Related**: Architecture doc sim-to-real principle

### OQ-034: Available context signals beyond glucose-insulin-carbs

**Question**: What contextual signals are actually available from the Nightscout ecosystem today for pattern learning?

**Context**: Advisors recommend calendar, travel, and activity signals. Need to know what's realistically accessible.

**Options**:
1. HealthKit steps/activity (via Loop/Trio)
2. Google Fit data (via AAPS)
3. Manual Nightscout notes
4. Phone location/timezone changes (travel detection)
5. Calendar API integration

**Blocks**: GAP-ML-007

### OQ-035: Workspace boundary for decision modeling (Layer 4)

**Question**: Should decision modeling (override classifiers, policy layer) live in this ecosystem-alignment workspace or in a future mobile-focused workspace?

**Context**: Ecosystem-alignment has the physics engines and validation infrastructure. A mobile workspace would be closer to the inference deployment path. Current R&D benefits from co-location.

**Options**:
1. Keep in ecosystem-alignment during R&D, spin out when stabilized (recommended)
2. Create separate `t1pal-ml` repository now
3. Put in t1pal-mobile-workspace alongside existing app code

**Related**: cgmencode provenance note in `tools/cgmencode/README.md`

---

## How to Use This Document

### Adding Questions

```markdown
### OQ-NNN: Brief title

**Question**: The actual question to be answered.

**Context**: Background and why this matters.

**Options** (if applicable):
1. Option A
2. Option B

**Blocks**: What work items are blocked by this.

**Owner**: Who should answer this (if known).

**Related**: Links to gaps, ADRs, backlog items.
```

### Resolving Questions

1. Move to "Resolved Questions" table
2. Update blocking work items
3. Create ADR if architectural decision
4. Update related gaps with resolution

### ID Conventions

- `OQ-001-009`: Blocking questions
- `OQ-010-019`: Design/ADR questions
- `OQ-020-029`: Strategic questions
- `OQ-030-039`: Format/unit questions

---

## Related Documents

- [traceability/gaps.md](../traceability/gaps.md) - Technical gaps
- [docs/90-decisions/](90-decisions/) - ADRs
- [docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md](sdqctl-proposals/ECOSYSTEM-BACKLOG.md) - Work queue
- [LIVE-BACKLOG.md](../LIVE-BACKLOG.md) - Human requests
