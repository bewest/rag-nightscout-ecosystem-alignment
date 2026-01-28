# Nightscout v3 Treatments Schema

> **Source**: `externals/cgm-remote-monitor/lib/api3/swagger.yaml`  
> **Version**: v15.0.4 @ 3764790e  
> **Last Updated**: 2026-01-28

This document describes the authoritative treatments schema from the origin Nightscout server (cgm-remote-monitor).

---

## Overview

Treatments are T1D compensation actions stored in the `treatments` collection. API v3 provides full CRUD operations with automatic deduplication.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v3/treatments` | Search treatments |
| POST | `/api/v3/treatments` | Create treatment |
| GET | `/api/v3/treatments/{identifier}` | Read single |
| PUT | `/api/v3/treatments/{identifier}` | Update (replace) |
| PATCH | `/api/v3/treatments/{identifier}` | Patch (partial) |
| DELETE | `/api/v3/treatments/{identifier}` | Delete (soft) |
| GET | `/api/v3/treatments/history` | History with deleted |

---

## Base Document Fields

All documents inherit from `DocumentBase`.

**Source**: `lib/api3/swagger.yaml` - DocumentBase schema

### Core Fields

| Field | Type | Mutable | Description |
|-------|------|---------|-------------|
| `identifier` | string | ❌ | Primary key (UUID), server-assigned |
| `date` | integer | ❌ | Timestamp (Unix ms, seconds, or ISO-8601) |
| `utcOffset` | integer | ❌ | UTC offset in minutes (parsed from date) |
| `app` | string | ❌ | Source application |
| `device` | string | ❌ | Source device |
| `_id` | string | ❌ | MongoDB internal ID (internal use) |

### Server-Managed Fields

| Field | Type | Description |
|-------|------|-------------|
| `srvCreated` | integer | Server insert timestamp (Unix ms) |
| `srvModified` | integer | Server modification timestamp (Unix ms) |
| `subject` | string | Security subject (from JWT) |
| `modifiedBy` | string | Last modifier subject |
| `isValid` | boolean | `false` for deleted documents |
| `isReadOnly` | boolean | Locks document permanently |

---

## Treatment-Specific Fields

**Source**: `lib/api3/swagger.yaml` - Treatment schema

| Field | Type | Description | Used By |
|-------|------|-------------|---------|
| `eventType` | string | Treatment type (see enum below) | All |
| `glucose` | string | Current glucose value | BG Check, bolus |
| `glucoseType` | string | `"Sensor"`, `"Finger"`, `"Manual"` | BG Check |
| `units` | string | `"mg/dl"`, `"mmol/l"` | When glucose entered |
| `carbs` | number | Carbohydrates (grams) | Meals, carb correction |
| `protein` | number | Protein (grams) | Extended macros |
| `fat` | number | Fat (grams) | Extended macros |
| `insulin` | number | Insulin (units) | Bolus types |
| `duration` | number | Duration (minutes) | Temp basal, exercise, combo |
| `preBolus` | number | Pre-bolus time (minutes) | Meal bolus |
| `splitNow` | number | Immediate combo % | Combo bolus |
| `splitExt` | number | Extended combo % | Combo bolus |
| `percent` | number | Basal change % | Temp basal |
| `absolute` | number | Basal change (U/hr) | Temp basal |
| `targetTop` | number | Target range top | Temp target |
| `targetBottom` | number | Target range bottom | Temp target |
| `profile` | string | Profile name | Profile switch |
| `reason` | string | Reason/notes | Profile switch, temp target |
| `notes` | string | Free text notes | All |
| `enteredBy` | string | Who entered | All |

---

## eventType Enum

**Source**: `lib/plugins/careportal.js:12-95`, `lib/api3/swagger.yaml`

### Core Types (Careportal)

| eventType | Fields Used | Description |
|-----------|-------------|-------------|
| `BG Check` | bg | Blood glucose check |
| `Snack Bolus` | bg, insulin, carbs, protein, fat, preBolus | Small meal bolus |
| `Meal Bolus` | bg, insulin, carbs, protein, fat, preBolus | Full meal bolus |
| `Correction Bolus` | bg, insulin | Correction without food |
| `Carb Correction` | bg, carbs, protein, fat | Carbs without bolus |
| `Combo Bolus` | bg, insulin, carbs, duration, split | Dual-wave bolus |
| `Announcement` | bg | System announcement |
| `Note` | bg, duration | Free-form note |
| `Question` | bg | Question/reminder |
| `Exercise` | duration | Exercise activity |

### Device Management

| eventType | Fields Used | Description |
|-----------|-------------|-------------|
| `Site Change` | bg, insulin | Pump infusion site change |
| `Sensor Start` | bg, sensor | CGM sensor start |
| `Sensor Change` | bg, sensor | CGM sensor insert |
| `Sensor Stop` | bg | CGM sensor stop |
| `Pump Battery Change` | bg | Pump battery replacement |
| `Insulin Change` | bg | Insulin cartridge change |

### Basal & Profiles

| eventType | Fields Used | Description |
|-----------|-------------|-------------|
| `Temp Basal Start` | bg, duration, percent, absolute | Temporary basal start |
| `Temp Basal End` | bg, duration | Temporary basal end |
| `Profile Switch` | bg, duration, profile | Profile change |

### AID System Types

| eventType | Fields Used | Description |
|-----------|-------------|-------------|
| `Temporary Target` | targetTop, targetBottom, duration, reason | Temp glucose target |
| `OpenAPS Offline` | duration | OpenAPS offline mode |
| `D.A.D. Alert` | bg | Diabetes Alert Dog |
| `Bolus Wizard` | (via plugins) | Bolus calculator result |

### Additional Types (from swagger)

| eventType | Description |
|-----------|-------------|
| `Temp Basal` | Generic temp basal (legacy) |

---

## Deduplication Rules

**Source**: `lib/api3/swagger.yaml` - API3_DEDUP_FALLBACK_ENABLED

### With identifier

Documents with `identifier` field deduplicate by exact identifier match.

### Without identifier (fallback)

Documents without `identifier` deduplicate by:

```
created_at + eventType
```

When a duplicate is detected on POST:
- Operation becomes UPDATE
- Returns `isDeduplication: true`
- Returns `deduplicatedIdentifier: <original_id>`

---

## Comparison: Nightscout vs AAPS

| Field | Nightscout | AAPS NSClient | Notes |
|-------|------------|---------------|-------|
| `identifier` | ✅ | ✅ | Same usage |
| `date` | ✅ (accepts 3 formats) | `date`/`mills`/`timestamp` | NS more flexible |
| `eventType` | 21+ types | 25 EventType enum | Mostly compatible |
| `duration` | minutes | minutes (also `durationInMilliseconds`) | AAPS has both |
| `insulin` | ✅ | ✅ + `type` (NORMAL/SMB) | AAPS has bolus type |
| `pumpId` | ❌ | ✅ | AAPS-specific dedup |
| `pumpSerial` | ❌ | ✅ | AAPS-specific dedup |
| `isValid` | server-managed | client-sent | Deletion semantics differ |

### eventType Mapping

| Nightscout | AAPS (via @SerializedName) |
|------------|---------------------------|
| `Meal Bolus` | `MEAL_BOLUS` |
| `Correction Bolus` | `CORRECTION_BOLUS` |
| `Snack Bolus` | `SNACK_BOLUS` |
| `Combo Bolus` | `COMBO_BOLUS` |
| `Temp Basal` | `TEMPORARY_BASAL` |
| `Temporary Target` | `TEMPORARY_TARGET` |
| `Profile Switch` | `PROFILE_SWITCH` |
| `Site Change` | `CANNULA_CHANGE` |
| `Sensor Start` | `SENSOR_CHANGE` |
| `Insulin Change` | `INSULIN_CHANGE` |

---

## API v3 Query Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `filter` | MongoDB-style query | `filter=eventType$eq=Meal Bolus` |
| `sort` | Sort field | `sort=date` |
| `sort$desc` | Sort descending | `sort$desc=date` |
| `limit` | Max results | `limit=100` |
| `skip` | Offset for pagination | `skip=50` |
| `fields` | Field projection | `fields=date,carbs,insulin` |

---

## Security

| Permission | Operations |
|------------|------------|
| `api:treatments:read` | GET, search |
| `api:treatments:create` | POST |
| `api:treatments:update` | PUT, PATCH |
| `api:treatments:delete` | DELETE |

Authentication via JWT token or hashed API_SECRET.

---

## Related Gaps

| Gap ID | Description |
|--------|-------------|
| GAP-TREAT-001 | Loop uses `absorptionTime` in seconds, NS expects minutes |
| GAP-TREAT-002 | AAPS uses `durationInMilliseconds`, NS expects minutes |
| GAP-SHARE-001 | share2nightscout-bridge uses API v1 only |

---

## Cross-References

- [AAPS NSClient Schema](../aaps/nsclient-schema.md) - AAPS field mapping
- [Treatments Deep Dive](../../docs/10-domain/treatments-deep-dive.md) - Detailed analysis
- [Terminology Matrix](../cross-project/terminology-matrix.md) - Term mappings
- [OpenAPI Spec](../../specs/openapi/aid-treatments-2025.yaml) - Formal schema

---

## Source Files

| Purpose | Path |
|---------|------|
| Swagger spec | `lib/api3/swagger.yaml` |
| Careportal eventTypes | `lib/plugins/careportal.js` |
| OpenAPS eventTypes | `lib/plugins/openaps.js` |
| Generic CRUD | `lib/api3/generic/` |
