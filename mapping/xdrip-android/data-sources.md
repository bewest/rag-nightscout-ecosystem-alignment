# xDrip+ Data Sources

This document describes the 20+ data collection types supported by xDrip+ (Android), categorized by connection method.

## Overview

xDrip+ uses the `DexCollectionType` enum to manage all supported CGM data sources. This is significantly more comprehensive than xDrip4iOS, supporting direct Bluetooth, companion apps, cloud followers, WiFi bridges, and manual entry.

## Source File

`utils/DexCollectionType.java` (~392 lines)

## Collection Types

### Direct Bluetooth CGM

These sources connect directly to CGM transmitters via Bluetooth.

| Type | Internal Name | Description |
|------|--------------|-------------|
| `DexcomG5` | "DexcomG5" | Dexcom G5 transmitter |
| `DexcomG6` | "DexcomG6" | Dexcom G6/ONE transmitter |
| `Medtrum` | "Medtrum" | Medtrum A6 CGM |
| `GluPro` | "GluPro" | GluPro CGM sensor |

#### G5/G6 Collection

```java
// Modern OB1 collector for G5/G6/G7
public class Ob1G5CollectionService extends Service {
    // Handles:
    // - Bluetooth LE scanning
    // - Authentication with transmitter
    // - Glucose data extraction
    // - Sensor session management
    // - Backfill of missed readings
}
```

#### G7 Detection

```java
public static boolean isG7() {
    return DexCollectionType.getBestCollectorHardwareName().equals("G7");
}
```

### Bluetooth Bridge Devices

These connect to CGM sensors via Bluetooth bridges (MiaoMiao, Bubble, etc.).

| Type | Internal Name | Description |
|------|--------------|-------------|
| `BluetoothWixel` | "BluetoothWixel" | xBridge/Wixel device |
| `DexbridgeWixel` | "DexbridgeWixel" | xDrip bridge device |
| `LimiTTer` | "LimiTTer" | LimiTTer Libre bridge |

### WiFi/Network Sources

| Type | Internal Name | Description |
|------|--------------|-------------|
| `WifiWixel` | "WifiWixel" | WiFi-only Wixel |
| `WifiBlueToothWixel` | "WifiBlueToothWixel" | Hybrid BT+WiFi |
| `WifiDexBridgeWixel` | "WifiDexbridgeWixel" | WiFi xDrip bridge |
| `LimiTTerWifi` | "LimiTTerWifi" | LimiTTer via WiFi |
| `LibreWifi` | "LibreWifi" | Libre via WiFi bridge |

### Cloud Follower Sources

These download data from cloud services.

| Type | Internal Name | Service | Description |
|------|--------------|---------|-------------|
| `NSFollow` | "NSFollower" | Nightscout | Nightscout follower mode |
| `SHFollow` | "SHFollower" | Dexcom Share | Dexcom Share follower |
| `CLFollow` | "CLFollower" | Medtronic CareLink | CareLink follower |
| `WebFollow` | "WebFollower" | Generic | Custom URL follower |
| `Follower` | "Follower" | Legacy | Legacy follower mode |

#### Nightscout Follower

```java
public class NightscoutFollowService extends ForegroundService {

    private static final long SAMPLE_PERIOD = DEXCOM_PERIOD; // 5 minutes

    public void work(boolean live) {
        // Download entries
        getService().getEntries(secret, count, timestamp)
                .enqueue(entriesCallback);

        // Optionally download treatments
        if (treatmentDownloadEnabled()) {
            getService().getTreatments(secret)
                    .enqueue(treatmentsCallback);
        }
    }
}
```

#### Dexcom Share Follower

```java
public class ShareFollowService extends ForegroundService {
    // Connects to Dexcom Share servers
    // Downloads glucose readings
    // Handles authentication and session management
}
```

#### CareLink Follower

```java
public class CareLinkFollowService extends ForegroundService {
    // Connects to Medtronic CareLink
    // Downloads from 630G/640G/670G pumps
    // Handles OAuth authentication
}
```

### Companion App Sources

These receive data from other apps running on the device.

| Type | Internal Name | Source App | Description |
|------|--------------|------------|-------------|
| `LibreAlarm` | "LibreAlarm" | Libre Alarm | Libre via Alarm app |
| `NSEmulator` | "NSEmulator" | Spike, etc. | NS emulator apps |
| `LibreReceiver` | "LibreReceiver" | OOP/Libre | Libre companion app |
| `AidexReceiver` | "AidexReceiver" | Aidex | Aidex CGM app |
| `UiBased` | "UiBased" | Various | UI extraction method |

#### NSEmulator Receiver

```java
public class NSEmulatorReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        Bundle bundle = intent.getExtras();
        if (bundle != null) {
            // Parse Nightscout-format data from broadcast
            String collection = bundle.getString("collection");
            String data = bundle.getString("data");
            processNightscoutData(collection, data);
        }
    }
}
```

### Manual/Testing

| Type | Internal Name | Description |
|------|--------------|-------------|
| `Manual` | "Manual" | Manual BG entry |
| `Mock` | "Mock" | Testing/development |
| `None` | "None" | No collection |
| `Disabled` | "Disabled" | Collection disabled |

## Collection Type Categories

### Uses Bluetooth

```java
Collections.addAll(usesBluetooth,
    BluetoothWixel, DexcomShare, DexbridgeWixel, LimiTTer,
    WifiBlueToothWixel, DexcomG5, WifiDexBridgeWixel,
    LimiTTerWifi, Medtrum, GluPro
);
```

### Uses WiFi

```java
Collections.addAll(usesWifi,
    WifiBlueToothWixel, WifiWixel, WifiDexBridgeWixel,
    Mock, LimiTTerWifi, LibreWifi
);
```

### Uses Libre Sensors

```java
Collections.addAll(usesLibre,
    LimiTTer, LibreAlarm, LimiTTerWifi, LibreWifi, LibreReceiver
);
```

### Passive Collectors (No Sensor Control)

```java
Collections.addAll(isPassive,
    NSEmulator, NSFollow, SHFollow, WebFollow,
    LibreReceiver, UiBased, CLFollow, AidexReceiver
);
```

### Cannot Start/Stop Sensor or Calibrate

```java
Collections.addAll(canNotStartStopOrCal,
    NSFollow, SHFollow, WebFollow, UiBased, CLFollow, Disabled
);
```

### Uses Dexcom Raw Data

```java
Collections.addAll(usesDexcomRaw,
    BluetoothWixel, DexbridgeWixel, WifiWixel,
    WifiBlueToothWixel, DexcomG5, WifiDexBridgeWixel, Mock
);
```

## Service Mapping

Each collection type maps to a specific Android service:

```java
public static Class<?> getCollectorServiceClass(DexCollectionType type) {
    switch (type) {
        case DexcomG5:
        case DexcomG6:
            return Ob1G5CollectionService.class;

        case NSFollow:
            return NightscoutFollowService.class;

        case SHFollow:
            return ShareFollowService.class;

        case CLFollow:
            return CareLinkFollowService.class;

        case WebFollow:
            return WebFollowService.class;

        case Medtrum:
            return MedtrumCollectionService.class;

        case GluPro:
            return GluProService.class;

        case BluetoothWixel:
        case DexbridgeWixel:
        case LimiTTer:
            return DexCollectionService.class;

        case WifiWixel:
        case WifiBlueToothWixel:
        case LimiTTerWifi:
        case LibreWifi:
            return WifiCollectionService.class;

        case UiBased:
            return UiBasedCollector.class;

        default:
            return DoNothingService.class;
    }
}
```

## Comparison with xDrip4iOS

| Category | xDrip+ (Android) | xDrip4iOS |
|----------|-----------------|-----------|
| **Direct Bluetooth** | G5, G6, G7, Medtrum, GluPro | G5, G6, G7, Libre 2 |
| **Bridge Devices** | 6+ types (Wixel, LimiTTer, etc.) | MiaoMiao, Bubble |
| **Cloud Followers** | NS, Share, CareLink, Web | NS, LibreLinkUp, Share |
| **Companion Apps** | 5+ (LibreAlarm, NSEmulator, etc.) | None |
| **WiFi Sources** | 5 types | None |
| **Total Types** | 20+ | ~6 |

## Configuration

### Setting Collection Type

```java
// Get current type
DexCollectionType current = DexCollectionType.getDexCollectionType();

// Set new type
DexCollectionType.setDexCollectionType(DexCollectionType.NSFollow);

// Restart collection service
CollectionServiceStarter.restartCollectionService(context);
```

### Preference Storage

```java
public static final String DEX_COLLECTION_METHOD = "dex_collection_method";

public static DexCollectionType getDexCollectionType() {
    return getType(Pref.getString(DEX_COLLECTION_METHOD, "BluetoothWixel"));
}
```

## Hardware Detection

```java
public static String getBestCollectorHardwareName() {
    // Check G7 marker
    if (isG7marker()) return "G7";

    // Check transmitter ID format
    String txId = getTransmitterId();
    if (txId != null) {
        if (txId.length() == 6 && shortTxId()) {
            return "G7";
        }
        return "G6";
    }

    return "Unknown";
}
```

---

## Code Citation

```
xdrip-android:com/eveningoutpost/dexdrip/utils/DexCollectionType.java#L31-L59
xdrip-android:com/eveningoutpost/dexdrip/utils/DexCollectionType.java#L84-L105
```
