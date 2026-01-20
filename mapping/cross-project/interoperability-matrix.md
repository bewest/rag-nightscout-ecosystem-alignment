# Cross-Client Interoperability Matrix

**Generated**: 2026-01-20  
**Purpose**: Document Nightscout API compatibility patterns across ecosystem clients

## API Version Usage

| Client | v1 Data | v1 Auth | v2 Auth | v3 | Notes |
|--------|---------|---------|---------|----|----|
| **AndroidAPS** | ✅ | ✅ | ✅ | ❌ | v2 for token refresh |
| **Loop** | ✅ | ✅ | ❌ | ❌ | v1 only |
| **Trio** | ✅ | ✅ | ❌ | ❌ | v1 only, uses LoopKit |
| **xDrip+** | ✅ | ✅ | ❌ | ❌ | v1 only |
| **xDrip4iOS** | ✅ | ✅ | ❌ | ❌ | v1 only |
| **nightscout-connect** | ✅ | ✅ | ✅ | ❌ | v1 data, v2 fallback for auth |
| **OpenAPS** | ✅ | ✅ | ❌ | ❌ | v1 only |

## Authentication Patterns

| Client | API-SECRET | SHA1 Hash | JWT Bearer | Token Query | OAuth |
|--------|------------|-----------|------------|-------------|-------|
| **AndroidAPS** | ✅ | ✅ | ✅ | ❌ | Tidepool, OpenHumans |
| **Loop** | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Trio** | ✅ | ✅ | ❌ | ❌ | Tidepool |
| **xDrip+** | ✅ | ✅ | ❌ | ❌ | Tidepool |
| **xDrip4iOS** | ✅ | ✅ | ❌ | ✅ | ❌ |
| **nightscout-connect** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **cgm-remote-monitor** | ✅ | ✅ | ✅ | ✅ | ❌ |

## Deduplication Strategies

| Client | Primary ID Field | Upsert (PUT) | Upload Method | Download Filter |
|--------|------------------|--------------|---------------|-----------------|
| **AndroidAPS** | `identifier` + pump composite | ✅ | POST/PUT | `nightscoutId` match |
| **Loop** | `syncIdentifier` | ❌ | POST only | Not documented |
| **Trio** | `enteredBy: "Trio"` + `syncIdentifier` | ❌ | POST only | `$ne` on enteredBy |
| **xDrip+** | `uuid` | ✅ | PUT upsert | `$ne` on enteredBy |
| **xDrip4iOS** | `uuid` | ✅ | POST/PUT selective | Implicit via uuid |
| **nightscout-connect** | None (bookmark only) | ❌ | POST only | Timestamp cursor |

## Identity Fields by Data Type

### Treatments

| Client | Field | Format | Example |
|--------|-------|--------|---------|
| AndroidAPS | `identifier` | UUID | `a1b2c3d4-...` |
| AndroidAPS | `pumpId`+`pumpType`+`pumpSerial` | Composite | `123/Omnipod/ABC` |
| Loop | `syncIdentifier` | UUID | `a1b2c3d4-...` |
| Trio | `syncIdentifier` | UUID | `a1b2c3d4-...` |
| xDrip+ | `uuid` | UUID | `a1b2c3d4-...` |
| xDrip4iOS | `uuid` | UUID | `a1b2c3d4-...` |

### Entries (CGM)

| Client | Field | Format |
|--------|-------|--------|
| All | `dateString` + `device` | Composite key |
| Some | `sysTime` | Timestamp |

### DeviceStatus

| Client | Field | Format |
|--------|-------|--------|
| All | `device` + `created_at` | Composite key |

## Device Identifier Formats

| Client | Format | Example |
|--------|--------|---------|
| Loop | `loop://\(UIDevice.current.name)` | `loop://iPhone` |
| Trio | `Trio` (constant) | `Trio` |
| AndroidAPS | `AndroidAPS-\(version)` | `AndroidAPS-3.2.0` |
| xDrip+ | `xdrip` (constant) | `xdrip` |
| xDrip4iOS | `xDrip4iOS` (constant) | `xDrip4iOS` |
| OpenAPS | `openaps://\(hostname)/\(device)` | `openaps://rpi/pump` |

## Conflict Scenarios

### GAP-SYNC-001: Loop POST-Only Pattern

Loop uses POST exclusively, which may create duplicates if:
- Server deduplication doesn't recognize `syncIdentifier`
- Record needs update after initial upload

**Impact**: Medium - Server must handle dedup  
**Mitigation**: Server-side `syncIdentifier` matching

### GAP-NC-001: nightscout-connect No Dedup

nightscout-connect has no client-side deduplication, relying on:
- Bookmark cursor (don't re-read)
- Server-side duplicate detection

**Impact**: Low - Typically operates as relay  
**Mitigation**: Server handles duplicates

### Cross-Client Duplicate Isolation

When multiple AID controllers write to same Nightscout:

| Controller A | Controller B | Conflict Risk |
|--------------|--------------|---------------|
| Loop | Trio | LOW (different syncIdentifier) |
| AAPS | Loop | LOW (different identifier schemes) |
| xDrip+ | AAPS | LOW (different uuid vs identifier) |

**Key Finding**: Different identity field schemes naturally isolate duplicates across controllers.

## Requirements Summary

| ID | Requirement | Clients Affected |
|----|-------------|------------------|
| REQ-COMPAT-001 | API v1 must remain stable | All |
| REQ-COMPAT-002 | API-SECRET SHA1 hash must be supported | All |
| REQ-COMPAT-003 | `syncIdentifier` must be recognized for dedup | Loop, Trio |
| REQ-COMPAT-004 | `identifier` must be recognized for dedup | AAPS |
| REQ-COMPAT-005 | `uuid` must be recognized for dedup | xDrip+, xDrip4iOS |
| REQ-COMPAT-006 | `enteredBy` filter must work for download | Trio, xDrip+ |

## Related Documents

- [mapping/cross-project/aid-controller-sync-patterns.md](../cross-project/aid-controller-sync-patterns.md)
- [mapping/cross-project/terminology-matrix.md](../cross-project/terminology-matrix.md)
- [docs/10-domain/nightscout-api-comparison.md](../../docs/10-domain/nightscout-api-comparison.md)
