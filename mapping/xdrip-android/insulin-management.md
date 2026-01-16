# xDrip+ Insulin Management

This document describes xDrip+'s unique multi-insulin tracking system and smart pen integrations, features not available in xDrip4iOS.

## Overview

xDrip+ provides sophisticated insulin tracking that supports:

1. **Multiple insulin types** per treatment (e.g., NovoRapid + Lantus)
2. **Insulin profiles** with customizable action curves
3. **Smart pen integration** (InPen, Pendiq, NovoPen)
4. **Concentration support** (U100 through U500)
5. **IOB calculations** per insulin type

## Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `insulin/Insulin.java` | Base insulin class | ~82 |
| `insulin/InsulinManager.java` | Profile management | ~200 |
| `insulin/InsulinProfileEditor.java` | UI for editing profiles | ~300 |
| `insulin/LinearTrapezoidInsulin.java` | Action curve model | ~150 |
| `insulin/MultipleInsulins.java` | Multi-insulin support | ~100 |
| `models/InsulinInjection.java` | Injection record | ~50 |
| `models/Iob.java` | IOB calculations | ~200 |
| `insulin/inpen/` | InPen integration | ~300 |
| `insulin/pendiq/` | Pendiq integration | ~200 |
| `insulin/opennov/` | NovoPen integration | ~150 |

## Insulin Base Class

```java
public abstract class Insulin {

    private final String name;           // Internal name
    private final String displayName;    // User-visible name
    private final ArrayList<String> pharmacyProductNumber; // NDC codes
    private Boolean enabled;
    protected double concentration;      // 1.0 = U100, 2.0 = U200, etc.
    protected long maxEffect;            // Duration in milliseconds

    public Insulin(String n, String dn, ArrayList<String> ppn,
                   String c, JsonObject curveData) {
        name = n;
        displayName = dn;
        pharmacyProductNumber = ppn;
        maxEffect = 0;
        enabled = true;

        // Parse concentration
        switch (c.toLowerCase()) {
            case "u100": concentration = 1; break;
            case "u200": concentration = 2; break;
            case "u300": concentration = 3; break;
            case "u400": concentration = 4; break;
            case "u500": concentration = 5; break;
        }
    }

    // IOB at time t after injection
    public abstract double calculateIOB(long time);

    // Activity (rate of action) at time t
    public abstract double calculateActivity(long time);
}
```

## Insulin Profiles

### Built-in Profiles

xDrip+ includes default profiles for common insulins:

| Insulin | Type | Peak | Duration |
|---------|------|------|----------|
| NovoRapid | Rapid | 75 min | 5 hr |
| Humalog | Rapid | 75 min | 5 hr |
| Apidra | Rapid | 55 min | 4.5 hr |
| Fiasp | Ultra-Rapid | 55 min | 4.5 hr |
| Lyumjev | Ultra-Rapid | 45 min | 4 hr |
| Lantus | Long-acting | Flat | 24 hr |
| Levemir | Long-acting | Flat | 18 hr |
| Tresiba | Ultra-long | Flat | 42 hr |

### Profile Configuration

```java
public class InsulinManager {

    private static final Map<String, Insulin> profiles = new HashMap<>();

    public static void loadProfiles() {
        // Load from JSON asset
        JsonArray insulins = loadInsulinData();

        for (JsonElement element : insulins) {
            JsonObject obj = element.getAsJsonObject();

            String name = obj.get("name").getAsString();
            String displayName = obj.get("displayName").getAsString();
            String concentration = obj.get("concentration").getAsString();
            JsonObject curve = obj.getAsJsonObject("curve");

            Insulin insulin = new LinearTrapezoidInsulin(
                name, displayName, parseNDCs(obj), concentration, curve
            );
            profiles.put(name, insulin);
        }
    }

    public static Insulin getProfile(String name) {
        return profiles.get(name);
    }

    public static Insulin getBolusProfile() {
        String bolusName = Pref.getString("default_bolus_insulin", "NovoRapid");
        return profiles.get(bolusName);
    }

    public static Insulin getBasalProfile() {
        String basalName = Pref.getString("default_basal_insulin", "Lantus");
        return profiles.get(basalName);
    }
}
```

## Multi-Insulin Treatments

### InsulinInjection Class

```java
public class InsulinInjection {

    @Expose
    private String profileName;  // Insulin profile name

    @Expose
    private double units;        // Units injected

    // Transient - resolved at runtime
    private transient Insulin profile;

    public InsulinInjection(Insulin profile, double units) {
        this.profileName = profile.getName();
        this.profile = profile;
        this.units = units;
    }

    public Insulin getProfile() {
        if (profile == null) {
            profile = InsulinManager.getProfile(profileName);
        }
        return profile;
    }

    public double getUnits() {
        return units;
    }

    public boolean isBasal() {
        return profile != null && profile.isBasal();
    }
}
```

### Treatment with Multiple Insulins

```java
@Table(name = "Treatments")
public class Treatments extends Model {

    @Column(name = "insulin")
    public double insulin;           // Total units (for compatibility)

    @Column(name = "insulinJSON")
    public String insulinJSON;       // JSON array of InsulinInjection

    private List<InsulinInjection> insulinInjections = null;

    // Get all injections
    public List<InsulinInjection> getInsulinInjections() {
        if (insulinInjections == null && insulinJSON != null) {
            insulinInjections = new Gson().fromJson(insulinJSON,
                new TypeToken<ArrayList<InsulinInjection>>(){}.getType());
        }
        return insulinInjections != null ? insulinInjections : new ArrayList<>();
    }

    // Set injections and serialize
    public void setInsulinInjections(List<InsulinInjection> injections) {
        this.insulinInjections = injections;
        this.insulinJSON = new Gson().toJson(injections);

        // Update total for compatibility
        this.insulin = 0;
        for (InsulinInjection inj : injections) {
            this.insulin += inj.getUnits();
        }
    }

    // Check if treatment is basal-only
    public boolean isBasalOnly() {
        List<InsulinInjection> injections = getInsulinInjections();
        if (injections.isEmpty()) return false;

        for (InsulinInjection inj : injections) {
            if (!inj.isBasal()) return false;
        }
        return true;
    }
}
```

### Example insulinJSON

```json
[
    {
        "profileName": "NovoRapid",
        "units": 5.0
    },
    {
        "profileName": "Lantus",
        "units": 20.0
    }
]
```

## IOB Calculations

### Per-Insulin IOB

```java
public class Iob {

    public static double getIobAtTime(long timestamp) {
        double totalIob = 0;
        List<Treatments> treatments = Treatments.latestForGraph(
            1000, timestamp, Constants.DAY_IN_MS
        );

        for (Treatments t : treatments) {
            for (InsulinInjection inj : t.getInsulinInjections()) {
                Insulin profile = inj.getProfile();
                if (profile != null) {
                    long timeSinceInjection = timestamp - t.timestamp;
                    double iobContribution = profile.calculateIOB(timeSinceInjection);
                    totalIob += inj.getUnits() * iobContribution;
                }
            }
        }

        return totalIob;
    }

    // Get IOB breakdown by insulin type
    public static Map<String, Double> getIobBreakdown(long timestamp) {
        Map<String, Double> breakdown = new HashMap<>();

        List<Treatments> treatments = Treatments.latestForGraph(
            1000, timestamp, Constants.DAY_IN_MS
        );

        for (Treatments t : treatments) {
            for (InsulinInjection inj : t.getInsulinInjections()) {
                Insulin profile = inj.getProfile();
                if (profile != null) {
                    long timeSinceInjection = timestamp - t.timestamp;
                    double iob = inj.getUnits() * profile.calculateIOB(timeSinceInjection);

                    String name = profile.getName();
                    breakdown.put(name, breakdown.getOrDefault(name, 0.0) + iob);
                }
            }
        }

        return breakdown;
    }
}
```

## Smart Pen Integrations

### InPen

Companion D insulin smart pen integration.

```java
package com.eveningoutpost.dexdrip.insulin.inpen;

public class InPenEntry {

    public static void processInPenData(String data) {
        // Parse InPen Bluetooth data
        InPenReading reading = parseReading(data);

        // Create treatment
        Treatments treatment = new Treatments();
        treatment.timestamp = reading.timestamp;
        treatment.insulin = reading.units;
        treatment.enteredBy = "InPen";
        treatment.eventType = "Correction Bolus";

        // Set insulin injection with InPen profile
        Insulin inpenInsulin = InsulinManager.getProfile("InPen-Humalog");
        treatment.setInsulinInjections(Arrays.asList(
            new InsulinInjection(inpenInsulin, reading.units)
        ));

        treatment.save();
        UploaderQueue.newEntry("insert", treatment);
    }
}
```

### Pendiq 2.0

Digital insulin pen integration.

```java
package com.eveningoutpost.dexdrip.insulin.pendiq;

public class PendiqService extends BluetoothGattCallback {

    // Bluetooth LE service for Pendiq pen
    // Reads injection history
    // Creates treatment entries

    @Override
    public void onCharacteristicChanged(BluetoothGatt gatt,
            BluetoothGattCharacteristic characteristic) {

        byte[] data = characteristic.getValue();
        PendiqRecord record = PendiqParser.parse(data);

        if (record != null && record.isNewInjection()) {
            createTreatmentFromPendiq(record);
        }
    }
}
```

### NovoPen 6

NFC-based insulin pen data import.

```java
package com.eveningoutpost.dexdrip.insulin.opennov;

public class OpenNovReader {

    public static List<InsulinDose> readFromNFC(Tag tag) {
        // Read NovoPen 6 NFC data
        // Parse injection history
        // Return list of doses

        IsoDep isoDep = IsoDep.get(tag);
        isoDep.connect();

        byte[] response = isoDep.transceive(SELECT_COMMAND);
        // ... parse response

        List<InsulinDose> doses = new ArrayList<>();
        // ... extract dose records

        return doses;
    }

    public static void importDoses(List<InsulinDose> doses) {
        Insulin novopen = InsulinManager.getProfile("NovoRapid");

        for (InsulinDose dose : doses) {
            if (!Treatments.existsForTimestamp(dose.timestamp)) {
                Treatments t = new Treatments();
                t.timestamp = dose.timestamp;
                t.insulin = dose.units;
                t.enteredBy = "NovoPen";
                t.setInsulinInjections(Arrays.asList(
                    new InsulinInjection(novopen, dose.units)
                ));
                t.save();
            }
        }
    }
}
```

## Insulin Action Curves

### Linear Trapezoid Model

```java
public class LinearTrapezoidInsulin extends Insulin {

    private double onset;      // Time to start of action (minutes)
    private double peak;       // Time to peak action (minutes)
    private double duration;   // Total duration (minutes)

    @Override
    public double calculateIOB(long timeMs) {
        double minutes = timeMs / 60000.0;

        if (minutes <= 0) return 1.0;
        if (minutes >= duration) return 0.0;

        // Linear decay after peak
        if (minutes >= peak) {
            return (duration - minutes) / (duration - peak);
        }

        // Ramp up to peak
        return 1.0;
    }

    @Override
    public double calculateActivity(long timeMs) {
        double minutes = timeMs / 60000.0;

        if (minutes <= onset) return 0.0;
        if (minutes >= duration) return 0.0;

        // Peak activity
        if (minutes >= onset && minutes <= peak) {
            return (minutes - onset) / (peak - onset);
        }

        // Decay from peak
        return (duration - minutes) / (duration - peak);
    }
}
```

## Comparison with Other Systems

| Feature | xDrip+ (Android) | xDrip4iOS | AAPS |
|---------|-----------------|-----------|------|
| **Multi-insulin per treatment** | Yes | No | Yes |
| **Insulin profiles** | Customizable | Fixed | oref curves |
| **Smart pen integration** | InPen, Pendiq, NovoPen | No | No |
| **Concentration support** | U100-U500 | U100 only | U100-U200 |
| **IOB per insulin type** | Yes | No | Yes |
| **insulinJSON field** | Yes | No | No (separate) |

## Nightscout Mapping

The `insulinJSON` field is **xDrip+-specific** and not part of the standard Nightscout schema:

| xDrip+ Field | Nightscout Field | Notes |
|--------------|------------------|-------|
| `insulin` | `insulin` | Total units (compatible) |
| `insulinJSON` | N/A | Not uploaded (local only) |

For Nightscout compatibility, xDrip+ uploads the total `insulin` value while preserving the breakdown locally.

---

## Code Citation

```
xdrip-android:com/eveningoutpost/dexdrip/insulin/Insulin.java
xdrip-android:com/eveningoutpost/dexdrip/insulin/InsulinManager.java
xdrip-android:com/eveningoutpost/dexdrip/models/InsulinInjection.java
xdrip-android:com/eveningoutpost/dexdrip/models/Treatments.java#L110-L160
```
