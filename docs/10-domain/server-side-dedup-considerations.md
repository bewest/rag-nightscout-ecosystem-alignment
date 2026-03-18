# Server-Side Deduplication Considerations

**Status**: 📋 Research / Future Planning  
**Priority**: 🟢 P3 (Low)  
**Last Updated**: 2026-03-18

---

## Summary

This document analyzes whether adding server-side deduplication for client identity fields (`syncIdentifier`, `uuid`) would be beneficial, and the tradeoffs involved.

**Current State**: Server does NOT dedupe by `syncIdentifier` or `uuid` - only by `identifier` and `_id`.

**Conclusion**: Not recommended for v15.0.7. Client apps rely on specific behaviors, and adding server-side dedup could have unintended side effects.

---

## Client Identity Fields

| Field | Used By | Current Server Behavior |
|-------|---------|------------------------|
| `_id` | All clients | Primary key, used for upsert |
| `identifier` | AAPS, Loop (UUID _id promoted) | Used for upsert if present |
| `syncIdentifier` | Loop (carbs/doses) | **Preserved, not used for dedup** |
| `uuid` | xDrip+ | **Preserved, not used for dedup** |

---

## Loop's ObjectIdCache Pattern

Loop (carbs/doses) uses a specific workflow:

```
1. POST treatment with syncIdentifier (no _id)
2. Server returns new _id in response
3. Loop caches syncIdentifier → _id mapping (24hr TTL)
4. Future PUT/DELETE use cached _id
```

**Problem**: If cache expires or app reinstalls, Loop loses the _id mapping.

**Current Behavior**: Re-posting creates duplicate (dedup by `created_at + eventType` may prevent if timestamps match).

**Potential Fix**: Server could dedupe by `syncIdentifier`.

### Analysis

| Approach | Pros | Cons |
|----------|------|------|
| **Current (no dedup)** | Simple, predictable | Duplicates on cache loss |
| **Server dedup by syncIdentifier** | Prevents duplicates | Scope creep, may break clients expecting current behavior |
| **Client fix (use identifier)** | Clean separation | Requires Loop code change |

### Recommendation

**Do not add server-side syncIdentifier dedup** for v15.0.7:

1. Loop's ObjectIdCache is a client-side feature - server shouldn't compensate
2. Adding server dedup could mask client bugs that should be fixed
3. Breaking changes to dedup behavior could affect other clients
4. Loop could migrate to using `identifier` field instead

---

## xDrip+ UUID Pattern

xDrip+ uses a `uuid` field for sync identity.

**Current Behavior**: Field preserved, not used for dedup.

**Potential Fix**: Server could dedupe by `uuid`.

### Analysis

Same tradeoffs as syncIdentifier. xDrip+ already has working sync; adding server-side dedup could have unintended effects.

---

## Why Scope Matters

The UUID_HANDLING feature was specifically designed to fix:

1. **Loop overrides**: UUID incorrectly sent to `_id` field
2. **Trio entries**: UUID incorrectly sent to `_id` field

These are bugs where the `_id` field is misused. The server quirk mode handles them.

**Other fields** (`syncIdentifier`, `uuid`) are used correctly - they're separate identity fields that clients manage themselves.

Conflating the two cases would:
- Increase code complexity
- Risk breaking working clients
- Create implicit dependencies between unrelated systems

---

## Future Considerations

If server-side dedup becomes necessary:

### Option A: Explicit Dedup by Field

```javascript
// In upsertQueryFor():
if (obj.identifier) return { identifier: obj.identifier };
if (env.syncIdDedup && obj.syncIdentifier) return { syncIdentifier: obj.syncIdentifier };
if (env.uuidDedup && obj.uuid) return { uuid: obj.uuid };
if (obj._id) return { _id: obj._id };
return { created_at: ..., eventType: ... };
```

**Requires**: New feature flags (`SYNC_ID_DEDUP`, `UUID_DEDUP`).

### Option B: Unified Identifier Promotion

Modify clients to use `identifier` field uniformly:

| Client | Current | Migration |
|--------|---------|-----------|
| Loop (carbs) | `syncIdentifier` | Use `identifier` instead |
| xDrip+ | `uuid` | Use `identifier` instead |

**Requires**: Client code changes.

### Option C: Server-Side Promotion (Rejected)

Have server copy `syncIdentifier`/`uuid` to `identifier`:

```javascript
// NOT RECOMMENDED - scope creep
obj.identifier = obj.identifier || obj.syncIdentifier || obj.uuid;
```

**Why rejected**: 
- Changes meaning of `identifier` field
- Affects existing AAPS records
- Unpredictable side effects

---

## References

- [Client ID Handling Deep Dive](./client-id-handling-deep-dive.md) - Full analysis of client patterns
- [uuid-identifier-lookup.md](../backlogs/uuid-identifier-lookup.md) - UUID_HANDLING implementation
- [GAP-SYNC-005](../../traceability/sync-identity-gaps.md#gap-sync-005) - Loop ObjectIdCache not persistent
- Loop source: `ObjectIdCache.swift`, `SyncCarbObject.swift`
- xDrip+ source: `Treatments.java`

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-18 | Initial analysis - recommend against server-side syncIdentifier/uuid dedup |
