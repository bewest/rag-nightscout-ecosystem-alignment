# xDrip+ Data Models

This document describes the core data models in xDrip+ (Android) and their mapping to Nightscout collections.

## Source Files

| Model | File | Lines |
|-------|------|-------|
| BgReading | `models/BgReading.java` | ~2,394 |
| Treatments | `models/Treatments.java` | ~1,436 |
| Calibration | `models/Calibration.java` | ~1,123 |
| Sensor | `models/Sensor.java` | ~360 |
| BloodTest | `models/BloodTest.java` | ~350 |
| TransmitterData | `models/TransmitterData.java` | ~277 |
| HeartRate | `models/HeartRate.java` | ~180 |
| StepCounter | `models/StepCounter.java` | ~223 |

## BgReading

The core glucose reading entity, significantly more complex than xDrip4iOS's equivalent.

### Database Schema

```java
@Table(name = "BgReadings", id = BaseColumns._ID)
public class BgReading extends Model implements ShareUploadableBg {

    @Column(name = "sensor", index = true)
    public Sensor sensor;

    @Column(name = "calibration", index = true)
    public Calibration calibration;

    @Expose @Column(name = "timestamp", index = true)
    public long timestamp;

    @Expose @Column(name = "time_since_sensor_started")
    public double time_since_sensor_started;

    // Raw sensor values
    @Expose @Column(name = "raw_data")
    public volatile double raw_data;

    @Expose @Column(name = "filtered_data")
    public double filtered_data;

    @Expose @Column(name = "age_adjusted_raw_value")
    public double age_adjusted_raw_value;

    // Calculated glucose values
    @Expose @Column(name = "calculated_value")
    public double calculated_value;

    @Expose @Column(name = "filtered_calculated_value")
    public double filtered_calculated_value;

    @Expose @Column(name = "calculated_value_slope")
    public double calculated_value_slope;

    // Calibration polynomial coefficients
    @Expose @Column(name = "a")
    public double a;
    @Expose @Column(name = "b")
    public double b;
    @Expose @Column(name = "c")
    public double c;
    @Expose @Column(name = "ra")
    public double ra;
    @Expose @Column(name = "rb")
    public double rb;
    @Expose @Column(name = "rc")
    public double rc;

    // Identity
    @Expose @Column(name = "uuid", unique = true)
    public String uuid;

    @Expose @Column(name = "calibration_uuid")
    public String calibration_uuid;

    @Expose @Column(name = "sensor_uuid", index = true)
    public String sensor_uuid;

    // Flags
    @Expose @Column(name = "calibration_flag")
    public boolean calibration_flag;

    @Expose @Column(name = "snyced")  // legacy typo preserved
    public boolean ignoreForStats;

    @Expose @Column(name = "hide_slope")
    public boolean hide_slope;

    // Quality indicators
    @Expose @Column(name = "noise")
    public String noise;

    // Dexcom-specific calculated values
    @Expose @Column(name = "dg_mgdl")
    public double dg_mgdl = 0d;

    @Expose @Column(name = "dg_slope")
    public double dg_slope = 0d;

    @Expose @Column(name = "dg_delta_name")
    public String dg_delta_name;

    // Provenance
    @Expose @Column(name = "source_info")
    public volatile String source_info;

    @Expose @Column(name = "raw_calculated")
    public double raw_calculated;
}
```

### Constants

```java
public static final int BG_READING_ERROR_VALUE = 38;    // Error marker
public static final int BG_READING_MINIMUM_VALUE = 39;  // 39 mg/dL
public static final int BG_READING_MAXIMUM_VALUE = 400; // 400 mg/dL

// Age adjustment for sensor accuracy
public static final double AGE_ADJUSTMENT_TIME = 86400000 * 1.9;      // ~1.9 days
public static final double AGE_ADJUSTMENT_FACTOR = 0.45;
public static final double AGE_ADJUSTMENT_TIME_G6 = 86400000 * 1.9 / 1.8;
public static final double AGE_ADJUSTMENT_FACTOR_G6 = 0.45 / 3;
```

### Mapping to Nightscout `/api/v1/entries`

| BgReading Field | Nightscout Field | Notes |
|-----------------|------------------|-------|
| `timestamp` | `date` | Epoch milliseconds |
| `calculated_value` | `sgv` | mg/dL |
| `dg_slope` or calculated | `direction` | Trend arrow |
| `noise` | `noise` | Signal quality |
| `uuid` | `_id` | Unique identifier |
| `sensor_uuid` | `device` | Sensor/transmitter ID |
| `source_info` | N/A | Local provenance only |

### Direction Mapping

```java
// From Dex_Constants.TREND_ARROW_VALUES
NONE(0),
DOUBLE_UP(1),      // Rising fast (>3 mg/dL/min)
SINGLE_UP(2),      // Rising
FORTY_FIVE_UP(3),  // Rising slowly
FLAT(4),           // Stable
FORTY_FIVE_DOWN(5), // Falling slowly
SINGLE_DOWN(6),    // Falling
DOUBLE_DOWN(7),    // Falling fast (<-3 mg/dL/min)
NOT_COMPUTABLE(8), // Cannot compute
OUT_OF_RANGE(9)    // Sensor error
```

---

## Treatments

The treatment entity with unique multi-insulin support.

### Database Schema

```java
@Table(name = "Treatments", id = BaseColumns._ID)
public class Treatments extends Model {

    public static final String SENSOR_START_EVENT_TYPE = "Sensor Start";
    public static final String SENSOR_STOP_EVENT_TYPE = "Sensor Stop";
    private static final String DEFAULT_EVENT_TYPE = "<none>";
    public final static String XDRIP_TAG = "xdrip";

    @Expose @Column(name = "timestamp", index = true)
    public long timestamp;

    @Expose @Column(name = "eventType")
    public String eventType;

    @Expose @Column(name = "enteredBy")
    public String enteredBy;

    @Expose @Column(name = "notes")
    public String notes;

    @Expose @Column(name = "uuid", unique = true)
    public String uuid;

    @Expose @Column(name = "carbs")
    public double carbs;

    @Expose @Column(name = "insulin")
    public double insulin;

    // UNIQUE: Multi-insulin JSON array
    @Expose @Column(name = "insulinJSON")
    public String insulinJSON;

    @Expose @Column(name = "created_at")
    public String created_at;
}
```

### Multi-Insulin Support (Unique to xDrip+)

xDrip+ can track multiple insulin types per treatment:

```java
// InsulinInjection class
public class InsulinInjection {
    private Insulin profile;  // Insulin type (NovoRapid, Lantus, etc.)
    private double units;     // Units injected

    public boolean isBasal() {
        return profile != null && profile.isBasal();
    }
}

// Example insulinJSON content:
[
    {"profile": "NovoRapid", "units": 5.0},
    {"profile": "Lantus", "units": 20.0}
]
```

### Mapping to Nightscout `/api/v1/treatments`

| Treatments Field | Nightscout Field | Notes |
|------------------|------------------|-------|
| `timestamp` | `date` | Epoch milliseconds |
| `timestamp` | `created_at` | ISO 8601 string |
| `eventType` | `eventType` | Treatment type |
| `enteredBy` | `enteredBy` | "xdrip" |
| `notes` | `notes` | Free text |
| `uuid` | `_id` or `uuid` | Unique identifier |
| `carbs` | `carbs` | Grams |
| `insulin` | `insulin` | Total units (sum) |
| `insulinJSON` | N/A | xDrip+ extension |

### Event Types Comparison

| xDrip+ eventType | Nightscout eventType | Notes |
|------------------|---------------------|-------|
| `"<none>"` | `"Note"` | Default |
| `"Sensor Start"` | `"Sensor Start"` | Direct mapping |
| `"Sensor Stop"` | `"Sensor Stop"` | Direct mapping (xDrip+ extension) |
| `"BG Check"` | `"BG Check"` | Finger stick |
| `"Carb Correction"` | `"Carbs"` | Carb-only entry |
| `"Correction Bolus"` | `"Correction Bolus"` | Insulin-only |
| `"Snack Bolus"` | `"Snack Bolus"` | Carbs + Insulin |
| `"Meal Bolus"` | `"Meal Bolus"` | Carbs + Insulin |
| `"Combo Bolus"` | `"Combo Bolus"` | Extended bolus |
| `"Exercise"` | `"Exercise"` | Activity log |
| `"Note"` | `"Note"` | Annotation |
| `"Question"` | `"Question"` | Query marker |
| `"Announcement"` | `"Announcement"` | System message |

---

## Calibration

Calibration data for sensor glucose calculations.

### Database Schema

```java
@Table(name = "Calibration", id = BaseColumns._ID)
public class Calibration extends Model {

    @Expose @Column(name = "timestamp", index = true)
    public long timestamp;

    @Expose @Column(name = "sensor_age_at_time_of_estimation")
    public double sensor_age_at_time_of_estimation;

    @Column(name = "sensor", index = true)
    public Sensor sensor;

    @Expose @Column(name = "bg")
    public double bg;

    @Expose @Column(name = "raw_value")
    public double raw_value;

    @Expose @Column(name = "adjusted_raw_value")
    public double adjusted_raw_value;

    @Expose @Column(name = "sensor_confidence")
    public double sensor_confidence;

    @Expose @Column(name = "slope_confidence")
    public double slope_confidence;

    @Expose @Column(name = "raw_timestamp")
    public long raw_timestamp;

    // Calibration curve parameters
    @Expose @Column(name = "slope")
    public double slope;

    @Expose @Column(name = "intercept")
    public double intercept;

    @Expose @Column(name = "distance_from_estimate")
    public double distance_from_estimate;

    @Expose @Column(name = "estimate_raw_at_time_of_calibration")
    public double estimate_raw_at_time_of_calibration;

    @Expose @Column(name = "estimate_bg_at_time_of_calibration")
    public double estimate_bg_at_time_of_calibration;

    @Expose @Column(name = "uuid", unique = true)
    public String uuid;

    @Expose @Column(name = "sensor_uuid")
    public String sensor_uuid;

    // Check-in status
    @Expose @Column(name = "check_in")
    public boolean check_in;

    // Algorithm selection
    @Expose @Column(name = "first_decay")
    public double first_decay;

    @Expose @Column(name = "second_decay")
    public double second_decay;

    @Expose @Column(name = "first_slope")
    public double first_slope;

    @Expose @Column(name = "second_slope")
    public double second_slope;

    @Expose @Column(name = "first_intercept")
    public double first_intercept;

    @Expose @Column(name = "second_intercept")
    public double second_intercept;

    @Expose @Column(name = "first_scale")
    public double first_scale;

    @Expose @Column(name = "second_scale")
    public double second_scale;
}
```

### Mapping to Nightscout

Calibrations are uploaded to `/api/v1/entries` with type `"cal"`:

```json
{
    "type": "cal",
    "date": 1705421234567,
    "dateString": "2026-01-16T12:00:34.567Z",
    "slope": 850.5,
    "intercept": 32000.0,
    "scale": 1.0,
    "device": "xDrip-Pixel7"
}
```

---

## Sensor

CGM sensor session tracking.

### Database Schema

```java
@Table(name = "Sensors", id = BaseColumns._ID)
public class Sensor extends Model {

    @Expose @Column(name = "started_at", index = true)
    public long started_at;

    @Expose @Column(name = "stopped_at")
    public long stopped_at;

    @Expose @Column(name = "latest_battery_level")
    public int latest_battery_level;

    @Expose @Column(name = "uuid", unique = true)
    public String uuid;

    @Expose @Column(name = "sensor_location")
    public String sensor_location;
}
```

### Sensor Session Events

```java
// Sensor start treatment
{
    "eventType": "Sensor Start",
    "created_at": "2026-01-16T12:00:00.000Z",
    "enteredBy": "xdrip"
}

// Sensor stop treatment (xDrip+ extension)
{
    "eventType": "Sensor Stop",
    "created_at": "2026-01-26T12:00:00.000Z",
    "enteredBy": "xdrip"
}
```

---

## BloodTest

Finger stick blood glucose tests.

### Database Schema

```java
@Table(name = "BloodTest", id = BaseColumns._ID)
public class BloodTest extends Model {

    @Expose @Column(name = "timestamp", unique = true, index = true)
    public long timestamp;

    @Expose @Column(name = "mgdl")
    public double mgdl;

    @Expose @Column(name = "created_timestamp")
    public long created_timestamp;

    @Expose @Column(name = "state")
    public int state;

    @Expose @Column(name = "uuid")
    public String uuid;

    @Expose @Column(name = "source")
    public String source;  // "User", "Contour Next One", "AccuChek Guide", etc.
}
```

### Mapping to Nightscout

BloodTest entries are uploaded to `/api/v1/treatments`:

```json
{
    "eventType": "BG Check",
    "created_at": "2026-01-16T12:00:00.000Z",
    "glucose": 120,
    "glucoseType": "Finger",
    "units": "mg/dl",
    "enteredBy": "xdrip"
}
```

---

## TransmitterData

Raw data from CGM transmitters (primarily Dexcom).

### Database Schema

```java
@Table(name = "TransmitterData", id = BaseColumns._ID)
public class TransmitterData extends Model {

    @Expose @Column(name = "timestamp", index = true)
    public long timestamp;

    @Expose @Column(name = "raw_data")
    public double raw_data;

    @Expose @Column(name = "filtered_data")
    public double filtered_data;

    @Expose @Column(name = "sensor_battery_level")
    public int sensor_battery_level;

    @Expose @Column(name = "uuid", unique = true)
    public String uuid;
}
```

---

## HeartRate & StepCounter

Health metrics collected from wearables.

### HeartRate

```java
@Table(name = "HeartRate", id = BaseColumns._ID)
public class HeartRate extends Model {

    @Expose @Column(name = "timestamp", index = true)
    public long timestamp;

    @Expose @Column(name = "bpm")
    public int bpm;

    @Expose @Column(name = "accuracy")
    public int accuracy;
}
```

### StepCounter

```java
@Table(name = "StepCounter", id = BaseColumns._ID)
public class StepCounter extends Model {

    @Expose @Column(name = "timestamp", index = true)
    public long timestamp;

    @Expose @Column(name = "metric")
    public int metric;  // Step count
}
```

### Mapping to Nightscout

Activity data can be uploaded to `/api/v1/activity`:

```json
{
    "created_at": "2026-01-16T12:00:00.000Z",
    "steps": 5000,
    "heartRate": 72
}
```

---

## Key Differences from xDrip4iOS

| Aspect | xDrip+ (Android) | xDrip4iOS |
|--------|-----------------|-----------|
| **ORM** | ActiveAndroid | Core Data |
| **BgReading fields** | 25+ fields | ~15 fields |
| **Multi-insulin** | Yes (`insulinJSON`) | No |
| **Calibration polynomials** | Full (a,b,c,ra,rb,rc) | Simplified |
| **Dexcom native** | `dg_mgdl`, `dg_slope` | N/A |
| **Source tracking** | `source_info` field | N/A |
| **Heart/Steps** | Built-in models | N/A |
| **Sensor Stop event** | Yes | No |

---

## Code Citation

```
xdrip-android:com/eveningoutpost/dexdrip/models/BgReading.java#L69-L200
xdrip-android:com/eveningoutpost/dexdrip/models/Treatments.java#L68-L110
xdrip-android:com/eveningoutpost/dexdrip/models/Calibration.java
xdrip-android:com/eveningoutpost/dexdrip/models/Sensor.java
```
