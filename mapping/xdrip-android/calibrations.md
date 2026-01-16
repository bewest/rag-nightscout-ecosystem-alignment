# xDrip+ Calibration Algorithms

This document describes xDrip+'s pluggable calibration system, which allows users to choose from multiple algorithms for converting raw CGM data to glucose values.

## Overview

xDrip+ supports multiple calibration algorithms:

1. **xDrip Original** - Classic dual-calibration algorithm
2. **Native** - Use sensor's built-in calibration
3. **Datricsae** - Alternative multi-point algorithm
4. **Fixed Slope** - Development/testing algorithm
5. **Last Seven Unweighted** - Averaging algorithm

This is **unique to xDrip+ Android** - xDrip4iOS only uses native sensor calibration.

## Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `calibrations/CalibrationAbstract.java` | Base class | ~100 |
| `calibrations/PluggableCalibration.java` | Plugin manager | ~150 |
| `calibrations/XDripOriginal.java` | Classic algorithm | ~200 |
| `calibrations/Datricsae.java` | Alternative algorithm | ~180 |
| `calibrations/FixedSlopeExample.java` | Example/testing | ~80 |
| `calibrations/LastSevenUnweightedA.java` | Averaging | ~120 |
| `calibrations/NativeCalibrationPipe.java` | Native passthrough | ~80 |
| `models/Calibration.java` | Calibration entity | ~1,123 |

## CalibrationAbstract Base Class

```java
public abstract class CalibrationAbstract {

    protected String TAG = "CalibrationAbstract";

    // Get display name for settings
    public abstract String getAlgorithmName();

    // Get short code for preferences
    public abstract String getAlgorithmShortCode();

    // Check if algorithm requires calibration
    public abstract boolean requiresCalibration();

    // Calculate glucose from raw value
    public abstract CalibrationData getCalibrationData();

    // Calculate glucose from raw and timestamp
    public double getGlucoseFromRaw(double raw, long timestamp) {
        CalibrationData data = getCalibrationData();
        if (data == null) return -1;

        return (raw * data.slope) + data.intercept;
    }

    // Calculate glucose using sensor-specific logic
    public double getGlucoseFromSensorRaw(double raw, double filtered,
            long timestamp, BgReading last) {
        return getGlucoseFromRaw(raw, timestamp);
    }

    // Data container
    public static class CalibrationData {
        public double slope;
        public double intercept;
        public double scale;
        public boolean valid;
    }
}
```

## Plugin Manager

```java
public class PluggableCalibration {

    public enum Type {
        xDripOriginal,
        Native,
        Datricsae,
        FixedSlope,
        LastSevenUnweighted
    }

    private static final Map<Type, CalibrationAbstract> plugins = new HashMap<>();

    static {
        plugins.put(Type.xDripOriginal, new XDripOriginal());
        plugins.put(Type.Native, new NativeCalibrationPipe());
        plugins.put(Type.Datricsae, new Datricsae());
        plugins.put(Type.FixedSlope, new FixedSlopeExample());
        plugins.put(Type.LastSevenUnweighted, new LastSevenUnweightedA());
    }

    public static CalibrationAbstract getCalibrationPluginFromPreferences() {
        String preference = Pref.getString("calibration_plugin", "xDripOriginal");
        Type type = Type.valueOf(preference);
        return plugins.get(type);
    }

    public static boolean newCloseSensorData() {
        CalibrationAbstract plugin = getCalibrationPluginFromPreferences();
        return plugin != null && !plugin.requiresCalibration();
    }
}
```

## xDrip Original Algorithm

The classic xDrip calibration using weighted linear regression:

```java
public class XDripOriginal extends CalibrationAbstract {

    @Override
    public String getAlgorithmName() {
        return "xDrip Original";
    }

    @Override
    public String getAlgorithmShortCode() {
        return "xDripOriginal";
    }

    @Override
    public boolean requiresCalibration() {
        return true;  // Requires finger stick calibrations
    }

    @Override
    public CalibrationData getCalibrationData() {
        // Get recent calibrations (last 14 days)
        List<Calibration> calibrations = Calibration.latest(10);
        if (calibrations.isEmpty()) {
            return null;
        }

        // Calculate weighted linear regression
        double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0, sumW = 0;

        for (Calibration cal : calibrations) {
            // Weight by age (newer = higher weight)
            double age = JoH.msSince(cal.timestamp);
            double weight = Math.max(0.1, 1.0 - (age / (14 * DAY_IN_MS)));

            double x = cal.raw_value;
            double y = cal.bg;

            sumX += weight * x;
            sumY += weight * y;
            sumXY += weight * x * y;
            sumX2 += weight * x * x;
            sumW += weight;
        }

        // Calculate slope and intercept
        CalibrationData data = new CalibrationData();
        double n = sumW;
        data.slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
        data.intercept = (sumY - data.slope * sumX) / n;
        data.valid = true;

        return data;
    }
}
```

## Native Calibration Pipe

For sensors with factory calibration (Dexcom G6, Libre):

```java
public class NativeCalibrationPipe extends CalibrationAbstract {

    @Override
    public String getAlgorithmName() {
        return "Native Algorithm";
    }

    @Override
    public String getAlgorithmShortCode() {
        return "Native";
    }

    @Override
    public boolean requiresCalibration() {
        return false;  // Uses sensor's native calibration
    }

    @Override
    public CalibrationData getCalibrationData() {
        // Return identity transform
        CalibrationData data = new CalibrationData();
        data.slope = 1.0;
        data.intercept = 0.0;
        data.valid = true;
        return data;
    }

    @Override
    public double getGlucoseFromSensorRaw(double raw, double filtered,
            long timestamp, BgReading last) {
        // Use Dexcom's calculated value directly
        // This is passed through from dg_mgdl field
        return raw;  // Already calibrated
    }
}
```

## Datricsae Algorithm

Alternative calibration using multiple regression techniques:

```java
public class Datricsae extends CalibrationAbstract {

    @Override
    public String getAlgorithmName() {
        return "Datricsae";
    }

    @Override
    public boolean requiresCalibration() {
        return true;
    }

    @Override
    public CalibrationData getCalibrationData() {
        List<Calibration> calibrations = Calibration.allForSensor();

        if (calibrations.size() < 2) {
            return null;
        }

        // Datricsae uses a different weighting scheme
        // emphasizing calibrations closer to current BG range

        CalibrationData data = new CalibrationData();

        // Use robust regression to reduce outlier impact
        double[] result = robustLinearFit(calibrations);
        data.slope = result[0];
        data.intercept = result[1];
        data.valid = true;

        return data;
    }

    private double[] robustLinearFit(List<Calibration> cals) {
        // Iteratively reweighted least squares
        // Reduces impact of outlier calibrations
        // ...
        return new double[] { slope, intercept };
    }
}
```

## Last Seven Unweighted

Simple averaging of last 7 calibrations:

```java
public class LastSevenUnweightedA extends CalibrationAbstract {

    @Override
    public String getAlgorithmName() {
        return "Last 7 Unweighted Average";
    }

    @Override
    public boolean requiresCalibration() {
        return true;
    }

    @Override
    public CalibrationData getCalibrationData() {
        List<Calibration> calibrations = Calibration.latest(7);

        if (calibrations.isEmpty()) {
            return null;
        }

        // Simple unweighted average
        double sumSlope = 0, sumIntercept = 0;

        for (Calibration cal : calibrations) {
            sumSlope += cal.slope;
            sumIntercept += cal.intercept;
        }

        CalibrationData data = new CalibrationData();
        data.slope = sumSlope / calibrations.size();
        data.intercept = sumIntercept / calibrations.size();
        data.valid = true;

        return data;
    }
}
```

## Using Calibrations in BgReading

```java
public class BgReading {

    public static BgReading create(double raw, double filtered, long timestamp) {
        BgReading bg = new BgReading();
        bg.timestamp = timestamp;
        bg.raw_data = raw;
        bg.filtered_data = filtered;

        // Get calibration plugin
        CalibrationAbstract plugin = getCalibrationPluginFromPreferences();

        if (plugin != null) {
            // Use plugin to calculate glucose
            bg.calculated_value = plugin.getGlucoseFromSensorRaw(
                raw, filtered, timestamp, BgReading.last()
            );
        } else {
            // Fall back to standard calibration
            Calibration cal = Calibration.lastValid();
            if (cal != null) {
                bg.calculated_value = (raw * cal.slope) + cal.intercept;
            }
        }

        // Apply bounds
        bg.calculated_value = Math.max(BG_READING_MINIMUM_VALUE,
            Math.min(BG_READING_MAXIMUM_VALUE, bg.calculated_value));

        return bg;
    }
}
```

## Calibration Entity

```java
@Table(name = "Calibration")
public class Calibration extends Model {

    @Column(name = "timestamp", index = true)
    public long timestamp;

    @Column(name = "bg")
    public double bg;                // Finger stick BG (mg/dL)

    @Column(name = "raw_value")
    public double raw_value;         // Raw sensor value at calibration

    @Column(name = "slope")
    public double slope;             // Calculated slope

    @Column(name = "intercept")
    public double intercept;         // Calculated intercept

    @Column(name = "sensor_confidence")
    public double sensor_confidence; // Confidence score (0-1)

    @Column(name = "slope_confidence")
    public double slope_confidence;  // Slope confidence

    @Column(name = "check_in")
    public boolean check_in;         // Submitted to server

    // Dual-phase calibration parameters
    @Column(name = "first_slope")
    public double first_slope;

    @Column(name = "first_intercept")
    public double first_intercept;

    @Column(name = "second_slope")
    public double second_slope;

    @Column(name = "second_intercept")
    public double second_intercept;

    // Static methods
    public static Calibration lastValid() {
        return new Select()
            .from(Calibration.class)
            .where("sensor_confidence > 0")
            .orderBy("timestamp desc")
            .executeSingle();
    }

    public static List<Calibration> latest(int count) {
        return new Select()
            .from(Calibration.class)
            .orderBy("timestamp desc")
            .limit(count)
            .execute();
    }
}
```

## Algorithm Selection in Settings

Users can choose calibration algorithm in:
**Settings > Advanced Calibration > Calibration Plugin**

Options:
- xDrip Original (default)
- Native Algorithm (for G6/Libre)
- Datricsae
- Last 7 Unweighted
- Fixed Slope (testing)

## Comparison with Other Systems

| Feature | xDrip+ | xDrip4iOS | AAPS |
|---------|--------|-----------|------|
| **Pluggable algorithms** | Yes (5+) | No | No |
| **Native calibration** | Yes | Yes | Via xDrip+ |
| **Custom algorithms** | Yes | No | No |
| **Weighted regression** | Yes | N/A | N/A |
| **Calibration entity** | Full model | Simplified | N/A |

---

## Code Citation

```
xdrip-android:com/eveningoutpost/dexdrip/calibrations/CalibrationAbstract.java
xdrip-android:com/eveningoutpost/dexdrip/calibrations/PluggableCalibration.java
xdrip-android:com/eveningoutpost/dexdrip/calibrations/XDripOriginal.java
xdrip-android:com/eveningoutpost/dexdrip/models/Calibration.java
```
