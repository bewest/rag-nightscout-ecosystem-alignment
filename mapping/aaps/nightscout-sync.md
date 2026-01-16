# AAPS Nightscout Sync

This document describes how AAPS synchronizes data with Nightscout via the NSClientV3 plugin.

## Overview

AAPS provides two sync plugins:
- **NSClient** (legacy) - Uses Socket.IO for real-time sync with Nightscout v1 API
- **NSClientV3** (recommended) - Uses REST API with Nightscout v3 API

This document focuses on NSClientV3 as it is the current recommended approach.

## NSClientV3Plugin Architecture

```kotlin
// aaps:plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt
@Singleton
class NSClientV3Plugin @Inject constructor(
    // ... dependencies ...
) : NsClient, Sync, PluginBaseWithPreferences
```

### Key Components

| Component | Purpose |
|-----------|---------|
| `NSClientV3Service` | Background service for continuous sync |
| `DataSyncSelectorV3` | Selects data to sync based on preferences |
| `NSAndroidClient` | HTTP client for NS API calls |
| `StoreDataForDb` | Processes incoming data for local storage |

## Sync Flow

### Upload Flow

```
Local Change → DataSyncSelector → NSClientV3Plugin → NS API
                    │
                    ├── toNSBolus()
                    ├── toNSCarbs()
                    ├── toNSTemporaryBasal()
                    ├── toNSProfileSwitch()
                    ├── toNSDeviceStatus()
                    └── ...
```

### Download Flow

```
NS API → LoadTreatmentsWorker → NsIncomingDataProcessor → Local DB
              │
              ├── ProcessedBoluses
              ├── ProcessedCarbs
              ├── ProcessedTempBasals
              ├── ProcessedProfileSwitches
              └── ...
```

## Extension Functions

AAPS uses extension functions to convert between local entities and NS models:

```kotlin
// aaps:plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/
import app.aaps.plugins.sync.nsclientV3.extensions.toNSBolus
import app.aaps.plugins.sync.nsclientV3.extensions.toNSCarbs
import app.aaps.plugins.sync.nsclientV3.extensions.toNSDeviceStatus
import app.aaps.plugins.sync.nsclientV3.extensions.toNSProfileSwitch
import app.aaps.plugins.sync.nsclientV3.extensions.toNSTemporaryBasal
import app.aaps.plugins.sync.nsclientV3.extensions.toNSTemporaryTarget
import app.aaps.plugins.sync.nsclientV3.extensions.toNSTherapyEvent
// ... more extensions
```

## Workers

NSClientV3 uses Android WorkManager for background tasks:

| Worker | Purpose |
|--------|---------|
| `LoadStatusWorker` | Fetch NS server status |
| `LoadBgWorker` | Download glucose entries |
| `LoadTreatmentsWorker` | Download treatments |
| `LoadProfileStoreWorker` | Download profile stores |
| `LoadDeviceStatusWorker` | Download device statuses |
| `LoadFoodsWorker` | Download food database |
| `DataSyncWorker` | Upload local changes |
| `LoadLastModificationWorker` | Check for new data |

## Sync Identity Management

### Identifier Strategy

AAPS uses multiple identity fields for sync:

```kotlin
// NSTreatment interface
val identifier: String?           // Client-generated UUID
val srvModified: Long?            // Server last modified timestamp
val srvCreated: Long?             // Server creation timestamp
val pumpId: Long?                 // Pump event ID
val pumpType: String?             // Pump driver type
val pumpSerial: String?           // Pump serial number
```

### Deduplication

1. **Primary Key**: `identifier` (client UUID) for updates/deletes
2. **Composite Key**: `pumpId` + `pumpType` + `pumpSerial` for pump events
3. **Timestamp Key**: `srvModified` for change detection

### Local Storage

The local database stores NS identifiers:

```kotlin
// aaps:database/impl/src/main/kotlin/app/aaps/database/entities/embedments/InterfaceIDs.kt
data class InterfaceIDs(
    var nightscoutId: String? = null,      // NS _id
    var pumpId: Long? = null,              // Pump event ID
    var pumpType: String? = null,          // Pump type
    var pumpSerial: String? = null,        // Pump serial
    var temporaryId: Long? = null,         // Temporary local ID
    var endId: Long? = null                // End event ID
)
```

## Sync Preferences

### Upload Settings

| Key | Description |
|-----|-------------|
| `ns_upload` | Enable upload to NS |
| `ns_upload_temp_basal` | Upload temp basals |
| `ns_upload_profile_switch` | Upload profile switches |
| `ns_upload_extended_bolus` | Upload extended boluses |
| `ns_upload_therapy_events` | Upload therapy events |

### Download Settings

| Key | Description |
|-----|-------------|
| `ns_receive_temp_target` | Download temp targets |
| `ns_receive_profile_switch` | Download profile switches |
| `ns_receive_offline_event` | Download offline events |
| `ns_receive_therapy_events` | Download therapy events |

## Last Modified Tracking

NSClientV3 tracks sync state per collection:

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/LastModified.kt
data class LastModified(
    val collections: Collections
) {
    data class Collections(
        var entries: Long = 0,
        var treatments: Long = 0,
        var profile: Long = 0,
        var devicestatus: Long = 0,
        var foods: Long = 0
    )
}
```

The plugin stores:
- `lastLoadedSrvModified` - Last fetched timestamp per collection
- `newestDataOnServer` - Server's newest timestamp per collection
- `firstLoadContinueTimestamp` - Resume point for initial load

## Device Status Upload

AAPS uploads comprehensive device status:

```kotlin
// Device status structure
NSDeviceStatus(
    date = now,
    device = "openaps://phoneModel",
    uploaderBattery = phoneBattery,
    isCharging = isCharging,
    
    pump = Pump(
        clock = pumpTime,
        reservoir = reservoirUnits,
        battery = Battery(percent = pumpBattery)
    ),
    
    openaps = OpenAps(
        suggested = algorithmSuggestion,
        enacted = enactedChanges,
        iob = iobData
    ),
    
    configuration = Configuration(
        pump = pumpDriverName,
        version = aapsVersion,
        aps = "OpenAPSSMB",
        // ...
    )
)
```

## Error Handling

### Exception Types

```kotlin
// aaps:core/nssdk/src/main/kotlin/app/aaps/core/nssdk/exceptions/
NightscoutException                    // Base exception
InvalidAccessTokenException            // Auth failure
DateHeaderOutOfToleranceException      // Time sync issue
InvalidFormatNightscoutException       // Data format error
InvalidParameterNightscoutException    // Bad parameter
UnknownResponseNightscoutException     // Unknown response
UnsuccessfulNightscoutException        // API error
```

### Retry Strategy

- Automatic retry on transient failures
- Exponential backoff for repeated failures
- Manual retry via "Full Sync" in UI

## WebSocket Support

NSClientV3 supports WebSocket for real-time updates:

```kotlin
val status = when {
    preferences.get(BooleanKey.NsClient3UseWs) && 
        nsClientV3Service?.wsConnected == true  -> "WS: Connected"
    preferences.get(BooleanKey.NsClient3UseWs) && 
        nsClientV3Service?.wsConnected == false -> "WS: Not connected"
    // ... polling fallback
}
```

## Sync Modes

### Initial Sync

On first connection, AAPS fetches historical data:
- Up to 500 records per batch (`RECORDS_TO_LOAD`)
- Maximum age: 100 days (`maxAge`)
- Resumes from `firstLoadContinueTimestamp` if interrupted

### Incremental Sync

After initial sync:
1. Check `newestDataOnServer` timestamps
2. Fetch only records with `srvModified > lastLoadedSrvModified`
3. Process in batches
4. Upload local changes via `DataSyncWorker`

### Full Sync

Triggered manually from UI:
- Clears sync state
- Re-fetches all data within age limit
- `fullSyncRequested = true` bypasses preference filters

## Data Flow Examples

### Bolus Upload

```
User delivers bolus
    ↓
Bolus saved to local DB with temporaryId
    ↓
DataSyncSelector detects new bolus
    ↓
bolus.toNSBolus() creates NS model
    ↓
NSAndroidClient.createTreatment(nsBolus)
    ↓
Server returns identifier
    ↓
Update local record with nightscoutId
```

### Profile Switch Download

```
LoadTreatmentsWorker polls NS
    ↓
Receives NSProfileSwitch from server
    ↓
NsIncomingDataProcessor.processProfileSwitches()
    ↓
Check if exists by nightscoutId
    ↓
Insert or update in local DB
    ↓
Trigger profile recalculation
```

## Nightscout Collections Mapped

| AAPS Data | NS Collection | Event Type |
|-----------|---------------|------------|
| Bolus | treatments | SMB, Meal Bolus, Correction Bolus |
| Carbs | treatments | Carb Correction |
| TemporaryBasal | treatments | Temp Basal |
| ProfileSwitch | treatments | Profile Switch |
| TemporaryTarget | treatments | Temporary Target |
| TherapyEvent | treatments | Note, Site Change, etc. |
| GlucoseValue | entries | (sgv field) |
| DeviceStatus | devicestatus | (openaps object) |
| Food | foods | (food database) |

## Gap Analysis

### GAP-003: Sync Identity Field

No unified sync identity exists across controllers:

| Controller | Primary Identity |
|------------|------------------|
| AAPS | `identifier` (client UUID) |
| Loop | `pumpId` + `pumpType` + `pumpSerial` |
| xDrip | `uuid` |
| Nightscout | `_id` (MongoDB ObjectId) |

**Impact**: Reconciling records across systems requires multiple fallback strategies.

### Recommendations

1. **Use identifier consistently** - Always include client UUID for updates
2. **Include pump composite key** - For pump event deduplication
3. **Track srvModified** - For efficient incremental sync
4. **Handle conflicts** - Server timestamp takes precedence
