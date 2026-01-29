# xDrip+ Nightscout Field Mapping

> **Source**: xDrip+ Android CGM app  
> **Target**: Nightscout REST API v1  
> **Last Updated**: 2026-01-29

## Overview

xDrip+ is the most widely used Android CGM data management app. It uploads glucose readings, treatments, device status, and activity data to Nightscout.

**Key Files**:
- `app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java` - Main uploader
- `app/src/main/java/com/eveningoutpost/dexdrip/models/Treatments.java` - Treatment model
- `app/src/main/java/com/eveningoutpost/dexdrip/models/BgReading.java` - Glucose model

---

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/entries` | POST | Upload SGV/MBG readings |
| `/api/v1/treatments` | POST | Insert treatments |
| `/api/v1/treatments` | PUT | Upsert treatments |
| `/api/v1/treatments.json` | GET | Find treatment by UUID |
| `/api/v1/treatments/{id}` | DELETE | Delete treatment |
| `/api/v1/devicestatus` | POST | Upload device battery status |
| `/api/v1/activity` | POST | Upload heart rate, steps, motion |
| `/api/v1/status.json` | GET | Check Nightscout status |

**Authentication**: `api-secret` header with SHA1 hash of API secret.

---

## Entries Collection (SGV)

**Source**: `NightscoutUploader.java:660-694` (`populateV1APIBGEntry`)

### Field Mapping

| Nightscout Field | xDrip+ Source | Type | Example |
|------------------|---------------|------|---------|
| `device` | `getDeviceString()` | string | `"xDrip-BluetoothWixel"` |
| `date` | `record.timestamp` | long (epoch ms) | `1706500000000` |
| `dateString` | `format.format(record.timestamp)` | ISO 8601 | `"2025-01-29T00:00:00.000-0800"` |
| `sgv` | `record.calculated_value` or `record.getDg_mgdl()` | int | `120` |
| `delta` | `record.currentSlope() * 5 * 60 * 1000` | decimal | `2.5` |
| `direction` | `record.slopeName()` or `record.getDg_deltaName()` | string | `"Flat"` |
| `type` | hardcoded | string | `"sgv"` |
| `filtered` | `record.ageAdjustedFiltered() * 1000` | long | `145000` |
| `unfiltered` | `record.usedRaw() * 1000` | long | `148000` |
| `rssi` | hardcoded | int | `100` |
| `noise` | `record.noiseValue()` | int | `1` |
| `sysTime` | `format.format(record.timestamp)` | ISO 8601 | `"2025-01-29T00:00:00.000-0800"` |

### Device String Format

```java
// NightscoutUploader.java:649-657
String withMethod = "xDrip-" + prefs.getString("dex_collection_method", "BluetoothWixel");
// Optional: append source_info if enabled
return withMethod + " " + record.source_info;
```

**Example device values**:
- `"xDrip-BluetoothWixel"` - Classic Dexcom with Wixel bridge
- `"xDrip-DexcomG5"` - Dexcom G5/G6 direct
- `"xDrip-LibreOOP"` - Libre with out-of-process algorithm
- `"xDrip-Libre2"` - Libre 2 direct
- `"xDrip-DexcomG5 Libre 2"` - With source_info appended

### Trend Direction Values

| Direction | Meaning |
|-----------|---------|
| `"DoubleUp"` | Rising fast (>3 mg/dL/min) |
| `"SingleUp"` | Rising (~2-3 mg/dL/min) |
| `"FortyFiveUp"` | Rising slowly (~1-2 mg/dL/min) |
| `"Flat"` | Stable (<1 mg/dL/min) |
| `"FortyFiveDown"` | Falling slowly |
| `"SingleDown"` | Falling |
| `"DoubleDown"` | Falling fast |
| `"NOT COMPUTABLE"` | Unable to calculate |
| `"RATE OUT OF RANGE"` | Rate exceeds limits |

---

## Entries Collection (MBG - Meter BG / Calibration)

**Source**: `NightscoutUploader.java:708-721` (`populateV1APIMeterReadingEntry`)

### Field Mapping

| Nightscout Field | xDrip+ Source | Type | Example |
|------------------|---------------|------|---------|
| `device` | collection method | string | `"xDrip-BluetoothWixel"` |
| `type` | hardcoded | string | `"mbg"` |
| `date` | `record.timestamp` | long (epoch ms) | `1706500000000` |
| `dateString` | `format.format(record.timestamp)` | ISO 8601 | `"2025-01-29T00:00:00.000-0800"` |
| `mbg` | `record.bg` | double | `120.0` |

---

## Treatments Collection

**Source**: `NightscoutUploader.java:771-791` (`populateV1APITreatmentEntry`)

### Field Mapping

| Nightscout Field | xDrip+ Source | Type | Example |
|------------------|---------------|------|---------|
| `timestamp` | `treatment.timestamp` | long (epoch ms) | `1706500000000` |
| `eventType` | `treatment.eventType` | string | `"Meal Bolus"` |
| `enteredBy` | `treatment.enteredBy` | string | `"xdrip"` |
| `notes` | `treatment.notes` | string | `"Lunch"` |
| `uuid` | `treatment.uuid` | string (UUID) | `"550e8400-e29b-41d4-a716-446655440000"` |
| `carbs` | `treatment.carbs` | double | `45.0` |
| `insulin` | `treatment.insulin` | double | `3.5` |
| `insulinInjections` | `treatment.insulinJSON` | string (JSON) | `[{"insulin":"NovoRapid","units":3.5}]` |
| `created_at` | `treatment.created_at` | ISO 8601 | `"2025-01-29T00:00:00.000Z"` |
| `sysTime` | `format.format(treatment.timestamp)` | ISO 8601 | `"2025-01-29T00:00:00.000-0800"` |

### Event Types

| Event Type | Constant | Description |
|------------|----------|-------------|
| `"Sensor Start"` | `SENSOR_START_EVENT_TYPE` | New CGM sensor inserted |
| `"Sensor Stop"` | `SENSOR_STOP_EVENT_TYPE` | CGM sensor removed |
| `"<none>"` | `DEFAULT_EVENT_TYPE` | Default for carbs/insulin |
| `"Meal Bolus"` | - | Meal with bolus |
| `"Correction Bolus"` | - | Correction without food |
| `"Carb Correction"` | - | Carbs without insulin |
| `"BG Check"` | - | Finger-stick blood glucose |
| `"Temp Basal"` | - | Temporary basal (skipped on import) |

### enteredBy Tag

```java
// Treatments.java:76
public final static String XDRIP_TAG = "xdrip";

// Treatments.java:287-289
treatment.enteredBy = XDRIP_TAG + " pos:" + JoH.qs(position, 2);  // with position
treatment.enteredBy = XDRIP_TAG;  // without position
```

### Sync Identity

xDrip+ uses `uuid` field for treatment identity:
- UUID v4 format: `550e8400-e29b-41d4-a716-446655440000`
- Lookup via `GET /api/v1/treatments.json?find[uuid]=<uuid>`
- Delete by Nightscout `_id` after lookup

**Deduplication**: Treatments with `enteredBy` ending in `@ns` or containing `@ns loader` are not uploaded back to Nightscout.

---

## DeviceStatus Collection

**Source**: `NightscoutUploader.java:1117-1182` (`postDeviceStatus`)

### Field Mapping

| Nightscout Field | xDrip+ Source | Type | Example |
|------------------|---------------|------|---------|
| `device` | `batteryType.getDeviceName()` | string | `"xDrip-phone"` |
| `uploader.battery` | `batteryType.getBatteryLevel()` | int | `75` |
| `uploader.batteryVoltage` | battery voltage (mV) | int | `3783` |
| `uploader.temperature` | system temperature | string | `"+51.0°C"` |

### Device Types

| Enum | Device Name | Description |
|------|-------------|-------------|
| `PHONE` | `"xDrip-phone"` | Android phone |
| `BRIDGE` | `"xDrip-bridge"` | Bluetooth bridge device |
| `PARAKEET` | `"xDrip-parakeet"` | WiFi bridge |
| `DEXCOM_TRANSMITTER` | `"xDrip-dexcom-tx"` | Dexcom transmitter battery |

### Example Payload

```json
{
  "device": "xDrip-phone",
  "uploader": {
    "battery": 75,
    "batteryVoltage": 3783,
    "temperature": "+42.0°C"
  }
}
```

---

## Activity Collection

**Source**: `NightscoutUploader.java:921-1063`

### Heart Rate

**Method**: `postHeartRate()` (lines 921-967)

| Nightscout Field | xDrip+ Source | Type | Example |
|------------------|---------------|------|---------|
| `type` | hardcoded | string | `"hr-bpm"` |
| `timeStamp` | `reading.timestamp` | long (epoch ms) | `1706500000000` |
| `created_at` | `DateUtil.toISOString(reading.timestamp)` | ISO 8601 | `"2025-01-29T00:00:00.000Z"` |
| `bpm` | `reading.bpm` | int | `72` |
| `accuracy` | `reading.accuracy` | int | `1` (omitted if 1) |

### Steps Count

**Method**: `postStepsCount()` (lines 970-1013)

| Nightscout Field | xDrip+ Source | Type | Example |
|------------------|---------------|------|---------|
| `type` | hardcoded | string | `"steps"` |
| `timeStamp` | `reading.timestamp` | long (epoch ms) | `1706500000000` |
| `created_at` | ISO 8601 string | string | `"2025-01-29T00:00:00.000Z"` |
| `steps` | `reading.steps` | int | `1234` |

### Motion Tracking

**Method**: `postMotionTracking()` (lines 1015-1063)

| Nightscout Field | xDrip+ Source | Type | Example |
|------------------|---------------|------|---------|
| `type` | hardcoded | string | `"motion"` |
| `timeStamp` | `reading.timestamp` | long (epoch ms) | `1706500000000` |
| `created_at` | ISO 8601 string | string | `"2025-01-29T00:00:00.000Z"` |
| `activity` | activity type | string | `"WALKING"` |
| `confidence` | detection confidence | int | `85` |

---

## GZIP Support

xDrip+ supports GZIP compression for uploads:

```java
// NightscoutUploader.java:180
if (USE_GZIP) okHttp3Builder.addInterceptor(new GzipRequestInterceptor());
```

Detection via response headers (lines 1066-1102).

---

## Multi-Site Upload

xDrip+ can upload to multiple Nightscout instances:
- Primary site from settings
- Fallback sites from additional configuration
- Each site gets same data in parallel

---

## Comparison with Other Systems

| Field | xDrip+ | DiaBLE | Loop | AAPS |
|-------|--------|--------|------|------|
| `device` format | `"xDrip-{method}"` | Sensor name | `"Loop"` | `"AndroidAPS"` |
| `uuid` field | ✅ | ❌ | ❌ (uses `syncIdentifier`) | ❌ (uses `interfaceIDs`) |
| `insulinInjections` | ✅ | ❌ | ❌ | ✅ |
| Activity upload | ✅ (HR, steps, motion) | ❌ | ❌ | ❌ |
| Sensor Start/Stop | ✅ via treatments | ❌ | ✅ via treatments | ✅ via TherapyEvent |
| `sysTime` field | ✅ | ❌ | ❌ | ❌ |

---

## Gaps Identified

### GAP-XDRIP-001: No Nightscout v3 API Support

**Description**: xDrip+ uses only v1 API endpoints. No support for v3 identifier-based sync.

**Impact**: Relies on UUID lookup for updates/deletes rather than atomic upserts.

### GAP-XDRIP-002: Activity Data Schema Not Standardized

**Description**: Heart rate, steps, and motion uploads use `/api/v1/activity` which is not a core Nightscout collection. Schema is xDrip+-specific.

**Impact**: Activity data may not be visible in all Nightscout frontends.

### GAP-XDRIP-003: Device String Format Not Machine-Parseable

**Description**: Device string format `"xDrip-{method} {source_info}"` mixes app name, collection method, and source info in free-form text.

**Impact**: Difficult to programmatically identify CGM source type from device field.

---

## Source File Reference

| File | Purpose |
|------|---------|
| `utilitymodels/NightscoutUploader.java` | Main uploader class |
| `utilitymodels/NightscoutTreatments.java` | Treatment response handling |
| `utilitymodels/NightscoutBatteryDevice.java` | Device battery enum |
| `utilitymodels/UploaderQueue.java` | Upload queue management |
| `utilitymodels/UploaderTask.java` | Upload scheduling |
| `models/Treatments.java` | Treatment data model |
| `models/BgReading.java` | Glucose reading model |
| `models/Calibration.java` | Calibration data model |
| `models/HeartRate.java` | Heart rate model |
| `models/StepCounter.java` | Step count model |
