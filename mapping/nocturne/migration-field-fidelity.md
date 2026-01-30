# Nocturne PostgreSQL Migration Field Fidelity

> **Date**: 2026-01-30  
> **OQ-010 Item #15**  
> **Status**: Analysis Complete

This document verifies field mapping between cgm-remote-monitor MongoDB and Nocturne PostgreSQL.

---

## Executive Summary

| Aspect | Status |
|--------|--------|
| **Core Fields** | ✅ Full preservation |
| **Nested Objects** | ✅ JSONB columns |
| **srvModified** | ⚠️ Computed, not stored |
| **Arbitrary Fields** | ✅ `additional_properties` JSONB |
| **Sync Identity** | ✅ `original_id` + UUID primary key |

**Conclusion**: Nocturne preserves field fidelity with a hybrid approach: typed columns for known fields, JSONB for nested objects and arbitrary data.

---

## Collection Mapping

| cgm-remote-monitor | Nocturne PostgreSQL | Notes |
|-------------------|---------------------|-------|
| `entries` | `entries` table | Full field mapping |
| `treatments` | `treatments` table | 60+ typed columns |
| `devicestatus` | `devicestatus` table | Nested objects as JSONB |
| `profile` | `profiles` table | `store_json` for schedules |

---

## Entries Field Mapping

### Preserved Fields

| MongoDB Field | PostgreSQL Column | Type | Notes |
|--------------|-------------------|------|-------|
| `_id` | `original_id` | varchar(24) | MongoDB ObjectId reference |
| `date` | `mills` | bigint | Unix epoch ms |
| `dateString` | `dateString` | varchar(50) | ISO 8601 |
| `sgv` | `sgv` | double | Sensor glucose |
| `mgdl` | `mgdl` | double | mg/dL value |
| `mmol` | `mmol` | double | mmol/L value |
| `direction` | `direction` | varchar(50) | Trend arrow |
| `trend` | `trend` | int | Dexcom trend 1-9 |
| `trendRate` | `trend_rate` | double | Rate of change |
| `device` | `device` | varchar(255) | Device ID |
| `type` | `type` | varchar(50) | sgv, mbg, cal |
| `noise` | `noise` | int | Noise level 0-4 |
| `filtered` | `filtered` | double | Filtered raw |
| `unfiltered` | `unfiltered` | double | Unfiltered raw |
| `rssi` | `rssi` | int | Signal strength |
| `delta` | `delta` | double | Change from prev |
| `slope` | `slope` | double | Calibration |
| `intercept` | `intercept` | double | Calibration |
| `scale` | `scale` | double | Calibration |
| `utcOffset` | `utcOffset` | int | TZ offset minutes |
| `created_at` | `created_at` | varchar(50) | ISO timestamp |
| `sysTime` | `sysTime` | varchar(50) | System time |
| `notes` | `notes` | text | Comments |

### Extended Fields (Nocturne-specific)

| PostgreSQL Column | Type | Purpose |
|-------------------|------|---------|
| `id` | UUID | Primary key (UUIDv7) |
| `is_calibration` | bool | Calibration flag |
| `data_source` | varchar(50) | Origin identifier |
| `meta` | jsonb | Metadata |
| `scaled` | jsonb | Scaled values |
| `additional_properties` | jsonb | **Arbitrary fields** |
| `sys_created_at` | timestamp | PostgreSQL insert time |
| `sys_updated_at` | timestamp | PostgreSQL update time |

### Arbitrary Field Handling

Unknown fields from MongoDB are captured in `additional_properties` JSONB:

```csharp
// EntryEntity.cs:202-203
[Column("additional_properties", TypeName = "jsonb")]
public string? AdditionalPropertiesJson { get; set; }
```

The entity includes a `ParseNotesJson()` method that extracts known fields from JSON in `notes` and stores unknown fields in `additional_properties`.

---

## Treatments Field Mapping

### Preserved Fields (60+ columns)

| MongoDB Field | PostgreSQL Column | Type |
|--------------|-------------------|------|
| `_id` | `original_id` | varchar(24) |
| `eventType` | `eventType` | varchar(255) |
| `created_at` | `created_at` | varchar(50) |
| `mills` | `mills` | bigint |
| `carbs` | `carbs` | double |
| `insulin` | `insulin` | double |
| `protein` | `protein` | double |
| `fat` | `fat` | double |
| `duration` | `duration` | double |
| `percent` | `percent` | double |
| `absolute` | `absolute` | double |
| `rate` | `rate` | double |
| `targetTop` | `targetTop` | double |
| `targetBottom` | `targetBottom` | double |
| `profile` | `profile` | varchar(255) |
| `percentage` | `percentage` | double |
| `timeshift` | `timeshift` | double |
| `insulinNeedsScaleFactor` | `insulinNeedsScaleFactor` | double |
| `enteredBy` | `enteredBy` | varchar(255) |
| `notes` | `notes` | text |
| `reason` | `reason` | text |
| `reasonDisplay` | `reasonDisplay` | varchar(255) |
| `boluscalc` | `boluscalc` | jsonb |
| `profileJson` | `profileJson` | jsonb |

### AAPS-specific Fields

| MongoDB Field | PostgreSQL Column | Notes |
|--------------|-------------------|-------|
| `percentage` | `percentage` | ProfileSwitch scaling |
| `timeshift` | `timeshift` | ProfileSwitch rotation |
| `CircadianPercentageProfile` | `CircadianPercentageProfile` | CPP flag |
| `NSCLIENT_ID` | `NSCLIENT_ID` | AAPS sync ID |

### Loop-specific Fields

| MongoDB Field | PostgreSQL Column | Notes |
|--------------|-------------------|-------|
| `insulinNeedsScaleFactor` | `insulinNeedsScaleFactor` | Override scaling |
| `remoteCarbs` | `remoteCarbs` | Remote command |
| `remoteBolus` | `remoteBolus` | Remote command |
| `remoteAbsorption` | `remoteAbsorption` | Remote command |
| `otp` | `otp` | One-time password |

### Extended Fields (Nocturne-specific)

| PostgreSQL Column | Purpose |
|-------------------|---------|
| `data_source` | Origin identifier |
| `endmills` | Calculated end time |
| `insulin_recommendation_for_carbs` | Bolus calc detail |
| `insulin_recommendation_for_correction` | Bolus calc detail |
| `insulin_programmed` | Programmed amount |
| `insulin_delivered` | Actual delivered |
| `insulin_on_board` | IOB at treatment |
| `blood_glucose_input` | BG for calc |
| `blood_glucose_input_source` | BG source |
| `calculation_type` | Suggested/Manual/Auto |
| `additional_properties` | **Arbitrary fields** |

---

## DeviceStatus Field Mapping

### Approach: JSONB for Nested Objects

cgm-remote-monitor devicestatus contains deeply nested controller-specific objects. Nocturne stores these as JSONB:

| MongoDB Field | PostgreSQL Column | Type |
|--------------|-------------------|------|
| `_id` | `original_id` | varchar(24) |
| `created_at` | `created_at` | varchar(50) |
| `mills` | `mills` | bigint |
| `device` | `device` | varchar(255) |
| `utcOffset` | `utcOffset` | int |
| `uploader` | `uploader` | **jsonb** |
| `pump` | `pump` | **jsonb** |
| `openaps` | `openaps` | **jsonb** |
| `loop` | `loop` | **jsonb** |
| `override` | `override` | **jsonb** |
| `xdripjs` | `xdripjs` | **jsonb** |
| `connect` | `connect` | **jsonb** |
| `radioAdapter` | `radioAdapter` | **jsonb** |
| `cgm` | `cgm` | **jsonb** |
| `meter` | `meter` | **jsonb** |
| `insulinPen` | `insulinPen` | **jsonb** |

### Nested Object Fidelity

**Full preservation** - JSONB columns store the complete nested structure:
- Loop prediction arrays
- OpenAPS suggested/enacted
- Pump reservoir/battery status
- CGM sensor status

```csharp
// DeviceStatusEntity.cs:79
[Column("loop", TypeName = "jsonb")]
public string? LoopJson { get; set; }
```

---

## Profile Field Mapping

### Preserved Fields

| MongoDB Field | PostgreSQL Column | Type |
|--------------|-------------------|------|
| `_id` | `original_id` | varchar(24) |
| `defaultProfile` | `default_profile` | varchar(100) |
| `startDate` | `start_date` | varchar(50) |
| `mills` | `mills` | bigint |
| `created_at` | `created_at` | varchar(50) |
| `units` | `units` | varchar(10) |
| `store` | `store_json` | **text** (JSON) |
| `enteredBy` | `entered_by` | varchar(100) |
| `loopSettings` | `loop_settings_json` | **jsonb** |

### Store JSON Fidelity

The `store_json` column preserves the complete profile store:
- All named profiles
- basal/carbratio/sens schedules
- DIA, target ranges, timezone

---

## srvModified Handling

### Finding: Computed, Not Stored

Nocturne does **not** store `srvModified` in PostgreSQL. Instead, it's computed at query time:

```csharp
// Treatment.cs:30-31
[JsonPropertyName("srvModified")]
public long? SrvModified => Mills > 0 ? Mills : null;
```

**Impact**:
- V3 API returns `srvModified` (computed from `mills`)
- Cannot track actual server modification time separately from event time
- Affects incremental sync strategies that rely on `srvModified > lastSync`

**Gap Reference**: GAP-SYNC-039 (already documented)

---

## Sync Identity Preservation

### OriginalId Strategy

All entities have:
```csharp
[Column("original_id")]
[MaxLength(24)]
public string? OriginalId { get; set; }
```

This preserves the MongoDB ObjectId for:
- Migration reference
- Cross-system sync identity
- Deduplication during import

### Primary Key Strategy

Nocturne uses UUIDv7 for primary keys:
- Time-ordered for efficient indexing
- Globally unique across instances
- Independent of MongoDB ObjectId

**Sufficient for sync identity**: Yes, with `original_id` for backward compatibility.

---

## Gap Analysis

### GAP-MIGRATION-001: srvModified Not Distinct from Mills

**Status**: Confirmed (already GAP-SYNC-039)

Nocturne computes `srvModified` from `mills` rather than tracking independently.

### GAP-MIGRATION-002: No srvCreated Storage

**Description**: Like `srvModified`, `srvCreated` is computed from `mills`.

**Impact**: Cannot distinguish between "when event occurred" and "when server received it."

### GAP-MIGRATION-003: JSONB Query Performance

**Description**: Deeply nested queries on JSONB columns (e.g., `loop->iob`) require careful indexing.

**Status**: Performance consideration, not data loss.

---

## Requirements Verification

### REQ-SYNC-039: Original ID Preservation

**Status**: ✅ Verified

All entities have `original_id` column for MongoDB ObjectId.

### REQ-SYNC-040: Arbitrary Field Preservation

**Status**: ✅ Verified

All entities have `additional_properties` JSONB for unknown fields.

### REQ-SYNC-041: Nested Object Preservation

**Status**: ✅ Verified

devicestatus uses JSONB columns for loop/openaps/pump nested objects.

---

## Conclusion

Nocturne's PostgreSQL migration achieves **full field fidelity** through:

1. **Typed columns** for 60+ known treatment fields
2. **JSONB columns** for nested objects (devicestatus, boluscalc, etc.)
3. **additional_properties JSONB** for arbitrary unknown fields
4. **original_id** for MongoDB ObjectId preservation

**Known limitations**:
- `srvModified`/`srvCreated` computed from `mills` (not stored independently)
- JSONB query performance requires indexing strategy

---

## References

- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/EntryEntity.cs`
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/TreatmentEntity.cs`
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/DeviceStatusEntity.cs`
- `externals/nocturne/src/Infrastructure/Nocturne.Infrastructure.Data/Entities/ProfileEntity.cs`
- [GAP-SYNC-039](../../traceability/sync-identity-gaps.md)
