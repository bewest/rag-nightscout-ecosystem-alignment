# tconnectsync Treatment Mappings

> **Source**: `externals/tconnectsync/tconnectsync/sync/`  
> **Last Updated**: 2026-01-29

Detailed mapping of t:connect events to Nightscout treatment types.

---

## Treatment Type Matrix

| t:connect Event | NS eventType | Processor File | Notes |
|-----------------|--------------|----------------|-------|
| Bolus | `Combo Bolus` | `process_bolus.py` | All boluses mapped to Combo |
| Standard Bolus | `Combo Bolus` | `process_bolus.py` | No carbs, insulin only |
| Extended Bolus | `Combo Bolus` | `process_bolus.py` | `extended_bolus: true` |
| Temp Basal | `Temp Basal` | `process_basal.py` | Control-IQ adjustments |
| Basal Suspension | `Basal Suspension` | `process_basal_suspension.py` | Manual or Basal-IQ |
| Basal Resume | `Basal Resume` | `process_basal_resume.py` | After suspension |
| Site Change | `Site Change` | `process_cartridge.py` | Cartridge replacement |
| Pump Alarm | `Announcement` | `process_alarm.py` | Alarms as notes |
| CGM Alert | `Announcement` | `process_cgm_alert.py` | High/low alerts |
| Sensor Start | `Sensor Start` | `process_cgm_start_join_stop.py` | G6/G7 session start |
| Sensor Stop | `Sensor Stop` | `process_cgm_start_join_stop.py` | Session end |
| Exercise Mode | `Exercise` | `process_user_mode.py` | Activity mode |
| Sleep Mode | `Sleep` | `process_user_mode.py` | Sleep activity |

---

## Detailed Mappings

### Bolus → Combo Bolus

**Processor**: `sync/process_bolus.py`

| t:connect Field | NS Field | Transform |
|-----------------|----------|-----------|
| `insulin` | `insulin` | Direct |
| `carbs` | `carbs` | Direct (0 if none) |
| `bg` | `glucose` | Direct |
| `request_time` | `created_at` | ISO-8601 format |
| `description` | `notes` | Direct |
| `extended_bolus` | - | Sets `splitNow`/`splitExt` if true |
| - | `eventType` | `Combo Bolus` (fixed) |
| - | `enteredBy` | `tconnectsync` |
| - | `pumpId` | Generated from event ID |

**Example Output**:
```json
{
  "eventType": "Combo Bolus",
  "created_at": "2026-01-29T10:30:00Z",
  "insulin": 2.5,
  "carbs": 30,
  "glucose": 145,
  "notes": "Meal bolus",
  "enteredBy": "tconnectsync"
}
```

### Temp Basal → Temp Basal

**Processor**: `sync/process_basal.py`

| t:connect Field | NS Field | Transform |
|-----------------|----------|-----------|
| `rate` | `rate` | Direct (U/hr) |
| `duration` | `duration` | Direct (minutes) |
| `timestamp` | `created_at` | ISO-8601 format |
| `reason` | `notes` | "Control-IQ", "Manual", etc. |
| - | `eventType` | `Temp Basal` |
| - | `absolute` | Same as `rate` |
| - | `enteredBy` | `tconnectsync` |

**Example Output**:
```json
{
  "eventType": "Temp Basal",
  "created_at": "2026-01-29T11:00:00Z",
  "rate": 0.8,
  "absolute": 0.8,
  "duration": 60,
  "notes": "Control-IQ",
  "enteredBy": "tconnectsync"
}
```

### Basal Suspension → Basal Suspension

**Processor**: `sync/process_basal_suspension.py`

| t:connect Field | NS Field | Transform |
|-----------------|----------|-----------|
| `start_time` | `created_at` | ISO-8601 format |
| `duration` | `duration` | Calculated from start/end |
| `reason` | `notes` | "Basal-IQ", "Manual", etc. |
| - | `eventType` | `Basal Suspension` |
| - | `rate` | `0` |

### Site Change → Site Change

**Processor**: `sync/process_cartridge.py`

| t:connect Field | NS Field | Transform |
|-----------------|----------|-----------|
| `timestamp` | `created_at` | ISO-8601 format |
| `cartridge_fill` | `notes` | "Filled X units" |
| - | `eventType` | `Site Change` |

### Activity Modes → Exercise/Sleep

**Processor**: `sync/process_user_mode.py`

| t:connect Mode | NS eventType | Notes |
|----------------|--------------|-------|
| Exercise | `Exercise` | Activity mode on pump |
| Sleep | `Sleep` | Sleep mode on pump |

| t:connect Field | NS Field | Transform |
|-----------------|----------|-----------|
| `start_time` | `created_at` | ISO-8601 format |
| `duration` | `duration` | Minutes |
| `mode_type` | `eventType` | `Exercise` or `Sleep` |

---

## CGM Data → Entries

**Not a treatment, but included for completeness.**

| t:connect Field | NS Field | Transform |
|-----------------|----------|-----------|
| `glucose` | `sgv` | Direct (mg/dL) |
| `timestamp` | `date` | Epoch milliseconds |
| - | `type` | `sgv` |
| - | `device` | `tconnectsync` |
| - | `direction` | Not provided by t:connect |

**Note**: t:connect does not provide trend direction. Nightscout entries will lack `direction` arrow.

---

## Comparison with Other Systems

| Feature | tconnectsync | AAPS | Loop |
|---------|--------------|------|------|
| Bolus eventType | `Combo Bolus` | `Bolus` + others | `Bolus` |
| Extended Bolus | Same treatment, flag | Separate type | Not used |
| Temp Basal | `Temp Basal` | `Temp Basal` | `Temp Basal` |
| Activity Modes | `Exercise`, `Sleep` | `Profile Switch` | `Temporary Override` |
| CGM Direction | ❌ Not provided | ✅ From CGM | ✅ From CGM |

---

## Gaps in Treatment Mapping

### GAP-TCONNECT-004: No Trend Direction

**Description**: t:connect API does not provide glucose trend direction. Entries uploaded to Nightscout will lack the `direction` field.

**Impact**: No trend arrows for t:connect-sourced CGM data in Nightscout UI.

**Remediation**: Calculate direction from consecutive readings if needed.

---

## Cross-References

- [Nightscout Treatment Types](../../specs/openapi/aid-treatments-2025.yaml)
- [AAPS eventTypes](../aaps/nsclient-schema.md)
- [Loop Treatment Types](../loop/sync-identity-fields.md)
