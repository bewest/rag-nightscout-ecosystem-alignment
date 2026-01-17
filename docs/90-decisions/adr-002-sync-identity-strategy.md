# ADR-002: Sync Identity Strategy

**Status:** Proposed  
**Date:** 2026-01-17  
**Deciders:** Nightscout Foundation, AID Controller Maintainers  
**Related:** [GAP-003](../../traceability/gaps.md#gap-003-no-unified-sync-identity-field-across-controllers), [Controller Registration Proposal](../60-research/controller-registration-protocol-proposal.md)

---

## Context

Different AID controllers use different fields and strategies for sync identity and deduplication:

| Controller | Identity Field | Type | Scope |
|------------|----------------|------|-------|
| Trio | `enteredBy: "Trio"` | String filter | Per-controller |
| Loop | `syncIdentifier` | UUID | Per-record |
| AAPS | `identifier` | UUID (API v3) | Per-record |
| xDrip+ | `uuid` | UUID | Per-record |

This creates several problems:
1. **Server-side deduplication is complex** — Must know controller-specific patterns
2. **Cross-controller reconciliation is unreliable** — No common identity field
3. **Duplicates occur** — Loop uses POST-only, retries create duplicates
4. **No deletion tracking** — API v1 cannot detect deletions

We need to decide on a strategy for sync identity that balances interoperability, migration cost, and backward compatibility.

---

## Decision Drivers

1. **Interoperability:** Enable reliable data exchange between controllers
2. **Deduplication:** Prevent duplicate records in Nightscout
3. **Migration cost:** Minimize changes required from existing controllers
4. **Backward compatibility:** Don't break existing integrations
5. **Deletion support:** Enable tracking of deleted records
6. **Authority support:** Enable verified identity for conflict resolution

---

## Options Considered

### Option A: Standardize on Single Field

Define a new standard field (e.g., `syncId`) that all controllers must use.

**Schema:**
```json
{
  "syncId": "550e8400-e29b-41d4-a716-446655440000",
  "eventType": "Correction Bolus",
  "insulin": 2.5
}
```

**Pros:**
- Simple, uniform identity
- Easy server-side deduplication
- Clear specification

**Cons:**
- Requires all controllers to change
- Migration period with mixed fields
- Breaks backward compatibility during transition

**Migration:**
1. Add `syncId` field to Nightscout schema
2. Controllers add `syncId` to uploads (alongside existing fields)
3. Nightscout deduplicates on `syncId` when present
4. Deprecate controller-specific fields after adoption

---

### Option B: Controller Registration with Declared Identity

Controllers register and declare their identity strategy. Nightscout uses the registered strategy for deduplication.

**Registration:**
```yaml
identityStrategy:
  type: "uuid"
  field: "syncIdentifier"
  scope: "per-record"
```

**Pros:**
- No changes required to existing controller data formats
- Explicit documentation of each controller's pattern
- Enables authority verification
- Extensible for future patterns

**Cons:**
- More complex server-side logic
- Requires registration infrastructure
- Still no cross-controller reconciliation

**Migration:**
1. Implement registration protocol
2. Controllers register with identity strategy
3. Nightscout uses registered strategy for deduplication
4. Unregistered controllers use legacy behavior

---

### Option C: Accept Diversity with Documented Mappings

Document the current patterns and provide mapping rules. Do not attempt to standardize.

**Documentation:**
```yaml
sync_identity_mappings:
  - controller: "Loop"
    field: "syncIdentifier"
    type: "uuid"
    dedup_strategy: "exact_match"
    
  - controller: "Trio"
    field: "enteredBy"
    value: "Trio"
    dedup_strategy: "enteredBy_filter"
```

**Pros:**
- No changes required from controllers
- Immediate implementation
- Documents current reality

**Cons:**
- Duplicates continue to occur
- No authority verification
- Each consumer must implement all patterns
- Problem deferred, not solved

---

### Option D: Hybrid — Registration with Standard Fallback

Combine registration with a standard field. Registered controllers use their declared strategy; new controllers must use the standard field.

**Rules:**
1. Registered controllers: Use declared identity strategy
2. New controllers: Must include `syncId` in registration
3. Unregistered controllers: Best-effort matching on common fields

**Pros:**
- Backward compatible for existing controllers
- Clear path for new controllers
- Enables gradual standardization

**Cons:**
- Complexity during transition
- Two "correct" approaches

---

## Decision

**Proposed: Option D — Hybrid with Registration**

This approach provides:
1. **Backward compatibility** for Loop, AAPS, Trio via registration
2. **Clear standard** for new controllers (must use `syncId`)
3. **Path to unification** as controllers migrate to standard field
4. **Authority foundation** via registration for future conflict resolution

### Implementation Phases

**Phase 1: Document (Immediate)**
- Document current controller patterns
- Publish mapping rules for consumers

**Phase 2: Registration (3-6 months)**
- Implement registration protocol
- Existing controllers register with current patterns
- Server uses registered strategy for deduplication

**Phase 3: Standard Field (6-12 months)**
- Require `syncId` for new controller registrations
- Encourage existing controllers to add `syncId`
- Server prefers `syncId` when present

**Phase 4: Deprecation (12-24 months)**
- Legacy identity fields deprecated
- All controllers use `syncId`
- Full interoperability achieved

---

## Consequences

### Positive

1. **No immediate breaking changes** — Existing controllers continue working
2. **Gradual migration** — Controllers can adopt at their own pace
3. **Clear standard for new integrations** — `syncId` is the answer
4. **Authority enabled** — Registration provides verified identity
5. **Documentation improves** — Current patterns become explicit

### Negative

1. **Complexity during transition** — Multiple patterns coexist
2. **Server logic increases** — Must handle registered and unregistered controllers
3. **Deferred full interoperability** — Takes 12-24 months to complete

### Neutral

1. **Registration infrastructure required** — Aligns with authority model needs
2. **Consumer adaptation** — Consumers benefit from registry queries

---

## Compliance

### For Existing Controllers (Loop, AAPS, Trio, xDrip+)

**Required:**
- Register with current identity strategy
- No data format changes required initially

**Recommended:**
- Add `syncId` field to future versions
- Migrate to `syncId` within 24 months

### For New Controllers

**Required:**
- Register before syncing
- Use `syncId` field for all uploads
- Use UUID format for `syncId`

### For Nightscout Server

**Required:**
- Implement registration endpoints (NRG or core)
- Store controller registry
- Use registered strategy for deduplication
- Support `syncId` as primary identity when present

### For Data Consumers

**Recommended:**
- Query registry for controller patterns
- Prefer `syncId` when present
- Fall back to controller-specific field

---

## Standard Field Specification

When using the `syncId` field:

```yaml
syncId:
  type: string
  format: uuid-v4
  required: true (for new controllers)
  description: |
    Universally unique identifier for this record, generated by the 
    uploading client. Used for deduplication and update detection.
    
  rules:
    - Must be stable across retries (same record = same syncId)
    - Must be unique within controller's uploads
    - Should survive app reinstalls (tied to record, not device)
    - Must be valid UUID v4 format
    
  examples:
    - "550e8400-e29b-41d4-a716-446655440000"
    - "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
```

---

## Metrics

Track progress via:

1. **Registration coverage:** % of treatments from registered controllers
2. **`syncId` adoption:** % of treatments with `syncId` field
3. **Duplicate rate:** Duplicates per 1000 treatments (should decrease)
4. **Consumer satisfaction:** Feedback on integration complexity

---

## Open Questions

1. **Timeline flexibility:** Can we accelerate Phase 4 if adoption is fast?
2. **Enforcement:** Should Phase 4 block unregistered controllers?
3. **`syncId` in v1 vs v3:** How does `syncId` relate to v3's `identifier`?
4. **Cross-Nightscout sync:** Does `syncId` help with multi-site scenarios?

---

## Next Steps

- [ ] Review with Loop, AAPS, Trio maintainers
- [ ] Draft `syncId` specification
- [ ] Implement registration prototype
- [ ] Create migration timeline with milestones
- [ ] Define enforcement policy for Phase 4

---

## Related Decisions

- [ADR-001: Override Supersession](adr-001-override-supersession.md)
- [Controller Registration Proposal](../60-research/controller-registration-protocol-proposal.md)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial proposal |
