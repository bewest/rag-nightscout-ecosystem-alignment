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

**Blocks**: Loop sync reliability (GAP-BATCH-002), batch testing scenarios

**Owner**: Nightscout API maintainers

**Related**:
- [GAP-BATCH-002](../traceability/gaps.md#gap-batch-002-response-order-critical-for-loop-syncidentifier-mapping)
- [GAP-BATCH-003](../traceability/gaps.md#gap-batch-003-deduplicated-items-must-return-all-positions)

---

### OQ-003: Override OTP validation requirement

**Question**: Should override remote commands require OTP validation like bolus/carb commands?

**Context**: Loop's override commands explicitly return `otpValidationRequired() -> Bool { return false }` while bolus/carb commands require OTP. This means anyone with API access can issue override commands without secondary authentication.

**Options**:
1. Require OTP for overrides (consistent with bolus/carb)
2. Keep current behavior (overrides are less dangerous than insulin delivery)
3. Make OTP configurable per command type

**Blocks**: Remote command security audit, authority model implementation

**Owner**: Loop/Trio maintainers

**Related**:
- [GAP-REMOTE-001](../traceability/gaps.md#gap-remote-001-remote-command-authorization-unverified)
- [Authority Model](10-domain/authority-model.md)

---

## Design (Need ADR)

Questions requiring formal architectural decision records.

### OQ-010: ProfileSwitch → Override mapping

**Question**: Should AAPS ProfileSwitch be accepted as a valid representation of overrides, or must there be explicit mapping?

**Context**: AAPS uses `ProfileSwitch` events with percentage/target modifications rather than explicit overrides. Loop/Trio use explicit override records. Cross-project queries need to understand both.

**Options**:
1. Define explicit mapping rules (ADR-004)
2. Accept both as valid representations with documented differences
3. Create hybrid schema accommodating both patterns

**Needs**: ADR-004

**Related**:
- [GAP-002](../traceability/gaps.md#gap-002-aaps-profileswitch-vs-override-semantic-mismatch)
- [Ready Queue #2: Compare override/profile switch semantics](sdqctl-proposals/ECOSYSTEM-BACKLOG.md)

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

**Needs**: ADR

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

**Blocks**: Long-term roadmap prioritization

**Owner**: Nightscout Foundation / Community

---

### OQ-021: Minimal viable interoperability spec

**Question**: What is the minimal set of fields and behaviors that ALL AID controllers should support?

**Context**: Current gaps document everything that differs. We need to identify the essential interoperability requirements that would enable reliable data exchange.

**Candidates**:
- Timestamp format (REQ-010: UTC ISO 8601)
- Sync identity (syncId/identifier)
- Core treatment fields (insulin, carbs, created_at)
- devicestatus structure

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

**Related**:
- [GAP-TREAT-001](../traceability/gaps.md#gap-treat-001-absorption-time-unit-mismatch)
- [GAP-TREAT-002](../traceability/gaps.md#gap-treat-002-duration-unit-inconsistency)

---

### OQ-031: utcOffset unit standardization

**Question**: Should utcOffset be in minutes or milliseconds?

**Current State**:
- Nightscout: minutes
- AAPS internal: milliseconds

**Related**:
- [GAP-TZ-004](../traceability/gaps.md#gap-tz-004-utcoffset-unit-mismatch-between-nightscout-and-aaps)

---

## Resolved Questions

| ID | Question | Resolution | Date |
|----|----------|------------|------|
| - | - | - | - |

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
