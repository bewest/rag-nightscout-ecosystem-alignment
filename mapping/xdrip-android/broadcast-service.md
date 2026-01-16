# xDrip+ Broadcast Service API

This document describes xDrip+'s Android Intent-based broadcast API for inter-app communication, enabling third-party apps to receive data and send commands.

## Overview

xDrip+ provides a comprehensive broadcast-based API that allows:

1. **Data sharing** - BG readings, treatments, graph data to third-party apps
2. **Command reception** - Snooze alerts, add treatments, change settings
3. **Bidirectional sync** - Real-time data exchange with watchfaces and apps

This is **unique to Android** and leverages the Android broadcast/intent system.

## Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `services/broadcastservice/BroadcastService.java` | Main service | ~569 |
| `services/broadcastservice/BroadcastEntry.java` | Enable/config | ~50 |
| `services/broadcastservice/Const.java` | Constants | ~80 |
| `services/broadcastservice/models/BroadcastModel.java` | App registration | ~100 |
| `services/broadcastservice/models/Settings.java` | Graph settings | ~150 |
| `services/broadcastservice/models/GraphLine.java` | Graph line data | ~50 |
| `utilitymodels/BroadcastGlucose.java` | BG broadcast | ~200 |
| `utilitymodels/Intents.java` | Intent constants | ~100 |

## Broadcast Actions

### Sender (xDrip+ → Apps)

```java
// Main broadcast action for sending data
public static final String ACTION_WATCH_COMMUNICATION_SENDER =
    "com.eveningoutpost.dexdrip.watch.wearintegration.BROADCAST_SERVICE_SENDER";

// Legacy glucose broadcast (widely supported)
public static final String ACTION_NEW_BG_ESTIMATE =
    "com.eveningoutpost.dexdrip.BgEstimate";

// AAPS-compatible broadcast
public static final String ACTION_NEW_BG_ESTIMATE_NO_DATA =
    "com.eveningoutpost.dexdrip.ExternalBroadcast";
```

### Receiver (Apps → xDrip+)

```java
// Main broadcast action for receiving commands
public static final String ACTION_WATCH_COMMUNICATION_RECEIVER =
    "com.eveningoutpost.dexdrip.watch.wearintegration.BROADCAST_SERVICE_RECEIVER";
```

## Command Reference

### Incoming Commands (Apps → xDrip+)

| Command | Const | Description | Required Extras |
|---------|-------|-------------|-----------------|
| Set Settings | `CMD_SET_SETTINGS` | Register app with graph settings | `PACKAGE`, `SETTINGS` |
| Update BG | `CMD_UPDATE_BG_FORCE` | Request immediate BG update | `PACKAGE`, `SETTINGS` |
| Snooze Alert | `CMD_SNOOZE_ALERT` | Snooze active alert | `PACKAGE`, `ALERT_TYPE` |
| Cancel Alarm | `CMD_CANCEL_ALARM` | Cancel alarm | `PACKAGE` |
| Add Treatment | `CMD_ADD_TREATMENT` | Add treatment entry | `PACKAGE`, treatment data |
| Add Blood Test | `CMD_ADD_BLOODTEST` | Add finger stick | `PACKAGE`, `BLOODTEST` |
| Add Steps | `CMD_ADD_STEPS` | Add step count | `PACKAGE`, `STEPS` |
| Add Heart Rate | `CMD_ADD_HEARTRATE` | Add heart rate | `PACKAGE`, `HEARTRATE`, `ACCURACY` |
| External Status | `CMD_EXTERNAL_STATUS` | Update external status line | `PACKAGE`, `STATUS_LINE` |
| Dismiss Phone | `CMD_DISMISS_PHONE` | Dismiss phone-side alert | `PACKAGE`, `DISMISS_PHONE` |

### Intent Extras

```java
// Required for all commands
public static final String INTENT_PACKAGE_KEY = "PACKAGE";
public static final String INTENT_FUNCTION_KEY = "FUNCTION";

// Settings object (Parcelable)
public static final String INTENT_SETTINGS = "SETTINGS";

// Alert type for snooze
public static final String INTENT_ALERT_TYPE = "ALERT_TYPE";  // "high" or "low"

// Blood test value
public static final String INTENT_BLOODTEST = "BLOODTEST";

// Step count
public static final String INTENT_STEPS = "STEPS";

// Heart rate
public static final String INTENT_HEARTRATE = "HEARTRATE";
public static final String INTENT_ACCURACY = "ACCURACY";

// External status line
public static final String INTENT_STATUS_LINE = "STATUS_LINE";

// Reply message
public static final String INTENT_REPLY_MSG = "REPLY_MSG";
public static final String INTENT_REPLY_CODE = "REPLY_CODE";
```

## App Registration

Third-party apps must register with xDrip+ before receiving data:

```java
// Step 1: Create Settings object
Settings settings = new Settings();
settings.graphStart = System.currentTimeMillis() - 3 * 60 * 60 * 1000; // 3 hours ago
settings.graphEnd = System.currentTimeMillis() + 30 * 60 * 1000;       // 30 min future
settings.highMark = 180;
settings.lowMark = 70;
settings.showLowLine = true;
settings.showHighLine = true;

// Step 2: Send registration intent
Intent intent = new Intent(ACTION_WATCH_COMMUNICATION_RECEIVER);
intent.putExtra("PACKAGE", "com.myapp.watchface");
intent.putExtra("FUNCTION", "CMD_SET_SETTINGS");
intent.putExtra("SETTINGS", settings);
context.sendBroadcast(intent);
```

## Settings Parcelable

```java
public class Settings implements Parcelable {

    // Graph time range
    public long graphStart;        // Start timestamp (epoch ms)
    public long graphEnd;          // End timestamp (epoch ms)

    // Thresholds (in user's units)
    public double highMark;        // High threshold
    public double lowMark;         // Low threshold

    // Display options
    public boolean showLowLine;    // Show low threshold line
    public boolean showHighLine;   // Show high threshold line
    public boolean showTreatments; // Include treatment dots

    // Graph appearance
    public int bgColor;            // Background color
    public int gridColor;          // Grid line color
    public int lowColor;           // Low range color
    public int inRangeColor;       // In-range color
    public int highColor;          // High range color

    // Additional options
    public boolean fuzzyTimeAgo;   // Show "5 min ago" vs exact time
    public boolean showDelta;      // Include delta in response
}
```

## Outgoing Data Format

### BG Data Broadcast

```java
public static void sendBroadcast(BgReading bgReading) {
    Intent intent = new Intent(ACTION_NEW_BG_ESTIMATE);

    // Core glucose data
    intent.putExtra("bg", bgReading.calculated_value);
    intent.putExtra("bgDouble", bgReading.calculated_value);
    intent.putExtra("bgMmol", bgReading.calculated_value / 18.0);
    intent.putExtra("bgMgdl", bgReading.calculated_value);

    // Timing
    intent.putExtra("timestamp", bgReading.timestamp);
    intent.putExtra("timestampMs", bgReading.timestamp);

    // Trend
    intent.putExtra("slopeName", bgReading.slopeName());
    intent.putExtra("slopeArrow", getSlopeArrow(bgReading));
    intent.putExtra("slope", bgReading.calculated_value_slope);

    // Delta
    double delta = calculateDelta(bgReading);
    intent.putExtra("delta", delta);
    intent.putExtra("deltaDouble", delta);
    intent.putExtra("deltaMgdl", delta);
    intent.putExtra("deltaMmol", delta / 18.0);

    // Battery
    intent.putExtra("battery", getBatteryLevel());
    intent.putExtra("sensorBattery", getSensorBattery());

    // Raw data
    if (bgReading.raw_data > 0) {
        intent.putExtra("raw", bgReading.raw_data);
        intent.putExtra("filtered", bgReading.filtered_data);
    }

    // Noise
    intent.putExtra("noise", bgReading.noise);
    intent.putExtra("noiseBlock", bgReading.noiseBlock);

    context.sendBroadcast(intent);
}
```

### Graph Data Response

When responding to `CMD_UPDATE_BG_FORCE`:

```java
Intent response = new Intent(ACTION_WATCH_COMMUNICATION_SENDER);
response.putExtra("PACKAGE", packageKey);
response.putExtra("FUNCTION", "BG_DATA");

// BG value
response.putExtra("bg", currentBg.calculated_value);
response.putExtra("timestamp", currentBg.timestamp);
response.putExtra("direction", currentBg.slopeName());

// Graph lines (Parcelable array)
ArrayList<GraphLine> lines = buildGraphLines(settings);
response.putParcelableArrayListExtra("graphLines", lines);

// Treatments
if (settings.showTreatments) {
    ArrayList<TreatmentData> treatments = buildTreatments(settings);
    response.putParcelableArrayListExtra("treatments", treatments);
}

// Statistics
response.putExtra("statsAvg", stats.getAverageBg());
response.putExtra("statsA1c", stats.getEstimatedA1c());
response.putExtra("statsInRange", stats.getTimeInRange());

context.sendBroadcast(response);
```

## AAPS Integration

### CGM Data to AAPS

xDrip+ can broadcast CGM data for AAPS to consume:

```java
// AAPS-compatible broadcast
public static final String ACTION_NEW_BG_ESTIMATE_NO_DATA =
    "com.eveningoutpost.dexdrip.ExternalBroadcast";

public static void broadcastToAAPS(BgReading bg) {
    Intent intent = new Intent(ACTION_NEW_BG_ESTIMATE_NO_DATA);
    intent.addFlags(Intent.FLAG_INCLUDE_STOPPED_PACKAGES);

    Bundle bundle = new Bundle();
    bundle.putDouble("sgv", bg.calculated_value);
    bundle.putLong("timestamp", bg.timestamp);
    bundle.putString("direction", bg.slopeName());
    bundle.putDouble("noise", parseNoise(bg.noise));

    intent.putExtras(bundle);
    context.sendBroadcast(intent);
}
```

### AAPS Device Status

xDrip+ can receive and display AAPS device status:

```java
public class AAPSStatusHandler {

    public static void processDeviceStatus(String json) {
        NSDeviceStatus status = gson.fromJson(json, NSDeviceStatus.class);

        // Extract pump info
        if (status.getPump() != null) {
            Double reservoir = status.getPump().getReservoir();
            if (reservoir != null) {
                PumpStatus.setReservoir(reservoir);
            }

            Integer battery = status.getPump().getBattery().getPercent();
            if (battery != null) {
                PumpStatus.setBattery(battery);
            }
        }

        PumpStatus.syncUpdate();
    }
}
```

## Broadcast Receiver Implementation

### Example: Receiving Commands

```java
public class BroadcastService extends Service {

    private BroadcastReceiver receiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String packageKey = intent.getStringExtra(INTENT_PACKAGE_KEY);
            String function = intent.getStringExtra(INTENT_FUNCTION_KEY);

            // Rate limiting
            if (!JoH.pratelimit(function + "_" + packageKey, 2)) {
                return;
            }

            switch (function) {
                case CMD_SET_SETTINGS:
                    Settings settings = intent.getParcelableExtra(INTENT_SETTINGS);
                    broadcastEntities.put(packageKey, new BroadcastModel(settings));
                    break;

                case CMD_UPDATE_BG_FORCE:
                    Settings s = intent.getParcelableExtra(INTENT_SETTINGS);
                    broadcastEntities.put(packageKey, new BroadcastModel(s));
                    sendBgUpdate(packageKey);
                    break;

                case CMD_SNOOZE_ALERT:
                    String alertType = intent.getStringExtra(INTENT_ALERT_TYPE);
                    snoozeAlert(alertType);
                    break;

                case CMD_ADD_TREATMENT:
                    double carbs = intent.getDoubleExtra("carbs", 0);
                    double insulin = intent.getDoubleExtra("insulin", 0);
                    addTreatment(carbs, insulin);
                    break;

                case CMD_ADD_STEPS:
                    int steps = intent.getIntExtra(INTENT_STEPS, 0);
                    StepCounter.createEfficientRecord(JoH.tsl(), steps);
                    break;

                case CMD_ADD_HEARTRATE:
                    int hr = intent.getIntExtra(INTENT_HEARTRATE, 0);
                    int acc = intent.getIntExtra(INTENT_ACCURACY, 1);
                    HeartRate.create(JoH.tsl(), hr, acc);
                    break;
            }
        }
    };
}
```

## Error Handling

```java
// Reply codes
public static final int INTENT_REPLY_CODE_OK = 0;
public static final int INTENT_REPLY_CODE_PACKAGE_ERROR = 1;
public static final int INTENT_REPLY_CODE_NOT_REGISTERED = 2;
public static final int INTENT_REPLY_CODE_ERROR = 3;

// Send error reply
Intent reply = new Intent(ACTION_WATCH_COMMUNICATION_SENDER);
reply.putExtra("PACKAGE", packageKey);
reply.putExtra("FUNCTION", "CMD_REPLY_MSG");
reply.putExtra("REPLY_MSG", "App not registered");
reply.putExtra("REPLY_CODE", INTENT_REPLY_CODE_NOT_REGISTERED);
context.sendBroadcast(reply);
```

## Compatible Apps

The broadcast API is used by:

1. **Watchfaces** - Android Wear, Garmin, Fitbit
2. **AAPS** - CGM data source
3. **Tasker** - Automation
4. **Custom apps** - Third-party integrations

## Comparison with xDrip4iOS

| Feature | xDrip+ (Android) | xDrip4iOS |
|---------|-----------------|-----------|
| **Broadcast API** | Yes (Intent-based) | No |
| **Third-party data sharing** | Yes | No |
| **Watchface API** | Yes (BroadcastService) | Apple Watch native |
| **AAPS integration** | Deep (bidirectional) | Follower only |
| **Tasker support** | Yes | No (iOS limitation) |
| **External status line** | Yes | No |

---

## Code Citation

```
xdrip-android:com/eveningoutpost/dexdrip/services/broadcastservice/BroadcastService.java#L63-L156
xdrip-android:com/eveningoutpost/dexdrip/services/broadcastservice/Const.java
xdrip-android:com/eveningoutpost/dexdrip/utilitymodels/BroadcastGlucose.java
```
