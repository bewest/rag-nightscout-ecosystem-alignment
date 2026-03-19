# AAPS _id Handling - Quick Reference

## Key Files & Line Numbers

### Data Models
| File | Line | Purpose |
|------|------|---------|
| `core/data/src/main/kotlin/app/aaps/core/data/model/IDs.kt` | 5-14 | Core IDs data class with `nightscoutId: String?` |
| `database/impl/src/main/kotlin/app/aaps/database/entities/embedments/InterfaceIDs.kt` | 5-7 | Database mapping for InterfaceIDs |

### Incoming Data Handlers

#### SGV (Glucose)
| File | Line | Pattern |
|------|------|---------|
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsShared/NSSgv.kt` | 25-26 | Extracts `_id` field as string |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsShared/NsIncomingDataProcessor.kt` | 85 | Assigns to `IDs(nightscoutId = sgv.id)` |

#### Treatments
| File | Treatment Type | Lines |
|------|---|---|
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/TemporaryBasalExtension.kt` | TB | 46-47, 74 |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/CarbsExtension.kt` | Carbs | 37-38, 54 |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/TherapyEventExtension.kt` | Events | 34-35, 54 |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/BolusCalculatorResultExtension.kt` | BCR | 32-33, 44 |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/ProfileSwitchExtension.kt` | PS | 63-64, 81 |

**Pattern**: All read `"_id"` field, fallback to `"identifier"` field as string

### Outgoing Data Handlers (Upload)

| File | Treatment Type | Line | Pattern |
|------|---|---|---|
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/TemporaryBasalExtension.kt` | TB | 31 | `if (isAdd && ids.nightscoutId != null) it.put("_id", ...)` |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/CarbsExtension.kt` | Carbs | 25 | Same pattern |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/TherapyEventExtension.kt` | Events | 71 | Same pattern |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/BolusCalculatorResultExtension.kt` | BCR | 24 | Same pattern |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/extensions/ProfileSwitchExtension.kt` | PS | 37 | Same pattern |

**Pattern**: All conditionally include `_id` only during ADD operations if `nightscoutId` exists

### ACK Handlers (Response Processing)

| File | Handler | Line | Pattern |
|------|---|---|---|
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/acks/NSAddAck.kt` | ADD Response | 35 | `id = response.getString("_id")` |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/acks/NSUpdateAck.kt` | UPDATE Response | 20 | Constructor param `var _id: String` |

### V3 SDK Models

| File | Type | Lines | Pattern |
|------|------|-------|---------|
| `core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/entry/NSSgvV3.kt` | SGV | 6, 39 | `identifier: String?` field |
| `core/nssdk/src/main/kotlin/app/aaps/core/nssdk/localmodel/treatment/NSBolus.kt` | Bolus | 8, 20 | `identifier: String?` field |
| `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/GlucoseValueExtension.kt` | SGV | 20, 39 | Maps `identifier` → `nightscoutId` |

## _id Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   Nightscout Server                         │
│  (MongoDB 3.x: hex string, 5.x: ObjectId serialized)       │
└────────────────┬────────────────────────────────────────────┘
                 │ API Response JSON: {"_id": "...", ...}
                 ↓
┌─────────────────────────────────────────────────────────────┐
│              AAPS Incoming Data Processor                    │
│  NSSgv.id = JsonHelper.safeGetStringAllowNull(json, "_id")  │
│             ↓                                                │
│  IDs(nightscoutId = id)  [Treated as opaque String]        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────┐
│           AAPS Local SQLite Database                        │
│  InterfaceIDs.nightscoutId: String? = value                │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────────┐
│              AAPS Outgoing Data Formatter                    │
│  if (isAdd && ids.nightscoutId != null)                     │
│      json.put("_id", ids.nightscoutId)  [Send as String]   │
└────────────────┬────────────────────────────────────────────┘
                 │ HTTP POST/PUT: {"_id": "...", ...}
                 ↓
┌─────────────────────────────────────────────────────────────┐
│                   Nightscout Server                         │
└─────────────────────────────────────────────────────────────┘
```

## Critical Characteristics

1. **No Format Validation**: AAPS never checks if _id is hex string, UUID, or ObjectId format
2. **String Storage**: Stored as TEXT in SQLite (unlimited length)
3. **Opaque Handling**: Treated as literal string value, not parsed/decomposed
4. **Fallback Support**: Can read from `identifier` field if `_id` missing
5. **Optional Field**: `nightscoutId?: String` handles missing _id gracefully
6. **Conditional Upload**: Only includes `_id` during ADD operations (not UPDATE)
7. **Null Safety**: Uses Kotlin null-safe operators throughout

## MongoDB 5.x Compatibility Status

| Scenario | Status | Evidence |
|----------|--------|----------|
| ObjectId → String JSON serialization | ✅ Works | Standard JSON library behavior |
| String storage in SQLite | ✅ Works | Unbounded TEXT column type |
| String passthrough to API | ✅ Works | Direct `put()` without validation |
| Format assumption breaks | ❌ None | No format validation anywhere |
| Null handling | ✅ Works | Uses `?.let` and optional fields |

## Test Files

- `/plugins/sync/src/test/kotlin/app/aaps/plugins/sync/nsShared/NsIncomingDataProcessorTest.kt`
- `/plugins/sync/src/test/kotlin/app/aaps/plugins/sync/nsShared/extensions/GVExtensionTest.kt`
- `/plugins/sync/src/test/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/GlucoseValueExtensionKtTest.kt`
- `/plugins/sync/src/test/kotlin/app/aaps/plugins/sync/nsclientV3/DataSyncSelectorV3Test.kt`

All tests use string identifiers with no format-specific assertions.

---

**Risk Level**: 🟡 MEDIUM (API format dependency, not code issues)  
**Code Safety**: ✅ HIGH (String passthrough is proven pattern)  
**MongoDB 5.x Ready**: ✅ YES (with standard JSON serialization)
