# Mapping: Nightscout - Data Collections

This document maps Nightscout data collections to alignment workspace concepts.

---

## Collections Overview

| Nightscout Collection | Alignment Concept | Primary Purpose |
|----------------------|-------------------|-----------------|
| `entries` | Entry | Glucose readings from CGM |
| `treatments` | Treatment | User interventions, events |
| `profile` | Profile | Therapy settings |
| `devicestatus` | DeviceStatus | Controller/pump state |
| `food` | (not mapped) | Food database |
| `activity` | (not mapped) | Activity data |

---

## Entries Collection Mapping

### Core Fields

| Nightscout Field | Alignment Field | Transformation |
|------------------|-----------------|----------------|
| `_id` | `id` | `toString()` |
| `sgv` | `glucose_value` | Direct (check units) |
| `direction` | `trend` | Map direction strings |
| `date` | `timestamp_ms` | Direct |
| `dateString` | `timestamp` | Direct (ISO 8601) |
| `device` | `device_id` | Direct |
| `type` | `entry_type` | `sgv`, `cal`, `mbg` |

### Direction Mapping

| Nightscout Direction | Alignment Trend | Rate Range |
|---------------------|-----------------|------------|
| `DoubleUp` | `rising_rapidly` | > 3 mg/dL/min |
| `SingleUp` | `rising` | 2-3 mg/dL/min |
| `FortyFiveUp` | `rising_slowly` | 1-2 mg/dL/min |
| `Flat` | `stable` | -1 to 1 mg/dL/min |
| `FortyFiveDown` | `falling_slowly` | -1 to -2 mg/dL/min |
| `SingleDown` | `falling` | -2 to -3 mg/dL/min |
| `DoubleDown` | `falling_rapidly` | < -3 mg/dL/min |
| `NOT COMPUTABLE` | `unknown` | N/A |

---

## Treatments Collection Mapping

### Core Fields

| Nightscout Field | Alignment Field | Transformation |
|------------------|-----------------|----------------|
| `_id` | `id` | `toString()` |
| `eventType` | `type` | Map event type |
| `created_at` | `occurred_at` | Direct (ISO 8601) |
| `mills` | `occurred_at_ms` | Direct |
| `enteredBy` | `recorded_by` | Direct (unverified) |
| `notes` | `notes` | Direct |
| `srvCreated` | `received_at` | Direct |
| `srvModified` | `modified_at` | Direct |

### Event Type Mapping

| Nightscout eventType | Alignment Type | Category |
|---------------------|----------------|----------|
| `BG Check` | `glucose_check` | Observation |
| `Meal Bolus` | `meal_bolus` | Insulin |
| `Correction Bolus` | `correction_bolus` | Insulin |
| `Snack Bolus` | `snack_bolus` | Insulin |
| `Carb Correction` | `carb_correction` | Carbs |
| `Combo Bolus` | `combo_bolus` | Insulin |
| `Temp Basal Start` | `temp_basal_start` | Basal |
| `Temp Basal End` | `temp_basal_end` | Basal |
| `Profile Switch` | `profile_switch` | Profile |
| `Temporary Target` | `temporary_target` | Override |
| `Temporary Override` | `override` | Override |
| `Sensor Start` | `sensor_start` | Device |
| `Sensor Change` | `sensor_change` | Device |
| `Site Change` | `site_change` | Device |
| `Note` | `note` | Annotation |
| `Announcement` | `announcement` | Annotation |
| `Exercise` | `exercise` | Activity |

### Insulin Fields

| Nightscout Field | Alignment Field | Notes |
|------------------|-----------------|-------|
| `insulin` | `insulin_units` | Direct |
| `splitNow` | `immediate_percent` | Combo bolus |
| `splitExt` | `extended_percent` | Combo bolus |

### Carb Fields

| Nightscout Field | Alignment Field | Notes |
|------------------|-----------------|-------|
| `carbs` | `carbs_grams` | Direct |
| `protein` | `protein_grams` | Direct |
| `fat` | `fat_grams` | Direct |
| `absorptionTime` | `absorption_minutes` | Direct |

---

## Profile Collection Mapping

### Document Structure

| Nightscout Field | Alignment Field | Transformation |
|------------------|-----------------|----------------|
| `_id` | `id` | `toString()` |
| `defaultProfile` | `active_profile_name` | Direct |
| `startDate` | `effective_from` | Direct (ISO 8601) |
| `store` | `profiles` | Map each named profile |
| `loopSettings` | `controller_settings` | Controller-specific |

### Profile Settings

| Nightscout Field | Alignment Field | Notes |
|------------------|-----------------|-------|
| `basal` | `basal_rates` | Time-value array |
| `sens` | `sensitivity_factors` | Time-value array |
| `carbratio` | `carb_ratios` | Time-value array |
| `target_low` | `target_range_low` | Time-value array |
| `target_high` | `target_range_high` | Time-value array |
| `dia` | `insulin_duration_hours` | Direct |
| `units` | `glucose_units` | `mg/dL` or `mmol/L` |
| `timezone` | `timezone` | IANA format |

### Time-Value Format

Nightscout:
```json
{ "time": "05:30", "timeAsSeconds": 19800, "value": 1.7 }
```

Alignment:
```json
{ "start_time": "05:30", "start_seconds": 19800, "value": 1.7 }
```

---

## DeviceStatus Collection Mapping

### Core Fields

| Nightscout Field | Alignment Field | Notes |
|------------------|-----------------|-------|
| `_id` | `id` | `toString()` |
| `device` | `device_id` | Direct |
| `created_at` | `timestamp` | Direct |
| `loop` | `loop_status` | Loop-specific |
| `openaps` | `openaps_status` | OpenAPS-specific |
| `pump` | `pump_status` | Pump state |
| `uploader` | `uploader_status` | Uploader state |

---

## Sync Identity Mapping

Different controllers use different fields for deduplication:

| Controller | Nightscout Field | Alignment Field |
|------------|------------------|-----------------|
| AAPS | `identifier` | `sync_id` |
| Loop | `pumpId` + `pumpType` + `pumpSerial` | `sync_id` (composite) |
| xDrip | `uuid` | `sync_id` |

**Gap**: No unified sync identity field exists across controllers.

---

## Code References

| Purpose | Location |
|---------|----------|
| Treatment handling | `crm:lib/server/treatments.js` |
| Profile loading | `crm:lib/profilefunctions.js` |
| Entry processing | `crm:lib/data/ddata.js` |
| API v3 CRUD | `crm:lib/api3/generic/` |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Initial mapping from schema documentation |

---

## V4 Extension (Nocturne Only)

> **Note**: V4 endpoints are available only in Nocturne (C#/.NET), not in cgm-remote-monitor (Node.js).
> See: `specs/openapi/nocturne-v4-extension.yaml`

### Feature Detection

Clients MUST check for V4 availability before using V4 endpoints:

```http
GET /api/v4/version
```

- **200**: V4 available (Nocturne)
- **404**: V4 not available (cgm-remote-monitor)

### StateSpan Collections

| V4 Collection | Purpose | cgm-remote-monitor Equivalent |
|---------------|---------|------------------------------|
| `state-spans` | Time-ranged state tracking | None |
| `state-spans/profiles` | Profile activation history | None (partial via treatments) |
| `state-spans/overrides` | Override history | `treatments.eventType=Override` |

### StateSpan Categories

| Category | States | Use Case |
|----------|--------|----------|
| Profile | Active | "What profile was active at time T?" |
| Override | None, Custom | Override duration visualization |
| TempBasal | Active, Cancelled | Temp basal history |
| PumpMode | Automatic, Manual, Suspended | Pump mode tracking |
| PumpConnectivity | Connected, Disconnected | Connection status |
| Sleep, Exercise, Illness, Travel | User-defined | User annotations |

### API Version Matrix

| Version | cgm-remote-monitor | Nocturne | Notes |
|---------|-------------------|----------|-------|
| V1 | ✅ | ✅ | Legacy, deprecated |
| V2 | ✅ | ✅ | Authorization endpoints |
| V3 | ✅ | ✅ | CRUD with identifier |
| **V4** | ❌ | ✅ | StateSpan, ChartData |

### Sync Compatibility Notes

| Behavior | cgm-remote-monitor | Nocturne | Impact |
|----------|-------------------|----------|--------|
| Soft delete | ✅ Default | ❌ Hard delete | Sync detection issues |
| srvModified | ✅ Server time | ⚠️ Alias for date | Limited sync impact |
| History endpoint | ✅ `/history/{ts}` | ❌ Missing | Polling requires workaround |

