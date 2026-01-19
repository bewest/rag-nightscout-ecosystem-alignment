# Trio Nightscout Synchronization

This document details how Trio synchronizes data with Nightscout, including upload/download flows, data transformations, and field mappings.

## Source Files

| File | Purpose |
|------|---------|
| `trio:Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift` | Sync orchestration |
| `trio:Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift` | HTTP client |
| `trio:Trio/Sources/Models/NightscoutTreatment.swift` | Treatment model |
| `trio:Trio/Sources/Models/NightscoutStatus.swift` | DeviceStatus model |

---

## API Endpoints

Trio uses Nightscout API v1:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/entries/sgv.json` | GET | Fetch glucose readings |
| `/api/v1/entries.json` | POST | Upload glucose readings |
| `/api/v1/treatments.json` | GET/POST/DELETE | Treatments CRUD |
| `/api/v1/devicestatus.json` | POST | Upload loop status |
| `/api/v1/profile.json` | POST | Upload profile |

### Authentication

```swift
// trio:NightscoutAPI.swift#L46-L50
if let secret = secret {
    request.addValue("application/json", forHTTPHeaderField: "Content-Type")
    request.httpMethod = "POST"
    request.addValue(secret.sha1(), forHTTPHeaderField: "api-secret")
}
```

Trio uses SHA-1 hashed API secret in the `api-secret` header.

---

## Upload Flows

### 1. Device Status Upload

> **See Also**: [DeviceStatus Structure Deep Dive](../../docs/10-domain/devicestatus-deep-dive.md) for comprehensive cross-system field mapping between Loop, Trio, and AAPS.

**Trigger**: After each loop cycle
**Endpoint**: `POST /api/v1/devicestatus.json`

```swift
// trio:NightscoutManager.swift#L303-L376
func uploadStatus() {
    let iob = storage.retrieve(OpenAPS.Monitor.iob, as: [IOBEntry].self)
    var suggested = storage.retrieve(OpenAPS.Enact.suggested, as: Suggestion.self)
    var enacted = storage.retrieve(OpenAPS.Enact.enacted, as: Suggestion.self)
    
    // Only include predictions in most recent
    if (suggested?.timestamp ?? .distantPast) > (enacted?.timestamp ?? .distantPast) {
        enacted?.predictions = nil
    } else {
        suggested?.predictions = nil
    }
    
    var openapsStatus = OpenAPSStatus(
        iob: iob?.first,
        suggested: suggested,
        enacted: loopIsClosed ? enacted : nil,
        version: "0.7.1"
    )
    
    let status = NightscoutStatus(
        device: NightscoutTreatment.local,  // "Trio"
        openaps: openapsStatus,
        pump: pump,
        uploader: uploader
    )
    
    nightscout.uploadStatus(status)
}
```

#### DeviceStatus JSON Structure

```json
{
  "device": "Trio",
  "openaps": {
    "iob": {
      "iob": 1.5,
      "basaliob": 0.8,
      "activity": 0.02,
      "time": "2026-01-16T12:00:00Z"
    },
    "suggested": {
      "reason": "COB: 20g; Dev: -15; BGI: -2.5; ISF: 50; ...",
      "units": 0.3,
      "rate": 1.2,
      "duration": 30,
      "IOB": 1.5,
      "COB": 20,
      "eventualBG": 120,
      "predBGs": {
        "IOB": [115, 110, 105, ...],
        "COB": [120, 125, 130, ...],
        "UAM": [115, 108, 102, ...],
        "ZT": [100, 95, 90, ...]
      },
      "deliverAt": "2026-01-16T12:00:00Z"
    },
    "enacted": {
      "rate": 1.2,
      "duration": 30,
      "recieved": true
    },
    "version": "0.7.1"
  },
  "pump": {
    "clock": "2026-01-16T12:00:00Z",
    "battery": { "percent": 75 },
    "reservoir": 150.5,
    "status": { "suspended": false }
  },
  "uploader": {
    "battery": 85
  }
}
```

### 2. Treatment Uploads

**Trigger**: Observer pattern on pump history, carbs, temp targets
**Endpoint**: `POST /api/v1/treatments.json`

```swift
// trio:NightscoutManager.swift#L560-L569
private func uploadPumpHistory() {
    uploadTreatments(pumpHistoryStorage.nightscoutTreatmentsNotUploaded(), 
                     fileToSave: OpenAPS.Nightscout.uploadedPumphistory)
}

private func uploadCarbs() {
    uploadTreatments(carbsStorage.nightscoutTretmentsNotUploaded(), 
                     fileToSave: OpenAPS.Nightscout.uploadedCarbs)
}

private func uploadTempTargets() {
    uploadTreatments(tempTargetsStorage.nightscoutTretmentsNotUploaded(), 
                     fileToSave: OpenAPS.Nightscout.uploadedTempTargets)
}
```

#### Event Type Mappings

| Trio EventType | Nightscout eventType | Fields |
|----------------|---------------------|--------|
| `EventType.bolus` | `Bolus` | `insulin`, `created_at` |
| `EventType.smb` | `SMB` | `insulin`, `created_at` |
| `EventType.mealBolus` | `Meal Bolus` | `insulin`, `created_at` |
| `EventType.correctionBolus` | `Correction Bolus` | `insulin`, `created_at` |
| `EventType.nsTempBasal` | `Temp Basal` | `rate`, `duration`, `absolute` |
| `EventType.nsCarbCorrection` | `Carb Correction` | `carbs`, `created_at` |
| `EventType.nsTempTarget` | `Temporary Target` | `targetTop`, `targetBottom`, `duration` |
| `EventType.nsSiteChange` | `Site Change` | `created_at` |
| `EventType.nsSensorChange` | `Sensor Start` | `created_at` |
| `EventType.nsExternalInsulin` | `External Insulin` | `insulin`, `created_at` |

#### NightscoutTreatment Structure

```swift
// trio:NightscoutTreatment.swift#L12-L30
struct NightscoutTreatment: JSON, Hashable, Equatable {
    var duration: Int?
    var rawDuration: PumpHistoryEvent?
    var rawRate: PumpHistoryEvent?
    var absolute: Decimal?
    var rate: Decimal?
    var eventType: EventType
    var createdAt: Date?
    var enteredBy: String?
    var bolus: PumpHistoryEvent?
    var insulin: Decimal?
    var notes: String?
    var carbs: Decimal?
    var fat: Decimal?
    var protein: Decimal?
    var foodType: String?
    let targetTop: Decimal?
    let targetBottom: Decimal?

    static let local = "Trio"
}
```

### 3. Glucose Upload

**Trigger**: When `uploadGlucose` setting is enabled
**Endpoint**: `POST /api/v1/entries.json`

```swift
// trio:NightscoutManager.swift#L555-L558
func uploadGlucose() {
    uploadGlucose(glucoseStorage.nightscoutGlucoseNotUploaded(), 
                  fileToSave: OpenAPS.Nightscout.uploadedGlucose)
    uploadTreatments(glucoseStorage.nightscoutCGMStateNotUploaded(), 
                     fileToSave: OpenAPS.Nightscout.uploadedCGMState)
}
```

#### BloodGlucose → entries Mapping

| Trio Field | Nightscout Field |
|------------|------------------|
| `sgv` | `sgv` |
| `direction` | `direction` |
| `dateString` | `dateString` |
| `date` | `date` (epoch ms) |
| `_id` | `_id` |
| `noise` | `noise` |
| `filtered` | `filtered` |
| `unfiltered` | `unfiltered` |
| `type` | `type` |

### 4. Profile Upload

**Trigger**: On profile/settings change
**Endpoint**: `POST /api/v1/profile.json`

```swift
// trio:NightscoutManager.swift#L407-L553
func uploadProfileAndSettings(_ force: Bool) {
    // Build NightscoutProfileStore from local settings
    let ps = ScheduledNightscoutProfile(
        dia: settingsManager.pumpSettings.insulinActionCurve,
        carbs_hr: Int(carbs_hr),
        delay: 0,
        timezone: TimeZone.current.identifier,
        target_low: target_low,
        target_high: target_high,
        sens: sens,
        basal: basal,
        carbratio: cr,
        units: nsUnits
    )
    
    let p = NightscoutProfileStore(
        defaultProfile: "default",
        startDate: now,
        mills: Int(now.timeIntervalSince1970) * 1000,
        units: nsUnits,
        enteredBy: NightscoutTreatment.local,
        store: ["default": ps]
    )
}
```

#### Profile Field Mappings

| Trio Source | Nightscout Profile Field |
|-------------|-------------------------|
| `InsulinSensitivities.sensitivities` | `sens[]` |
| `BGTargets.targets` | `target_low[]`, `target_high[]` |
| `CarbRatios.schedule` | `carbratio[]` |
| `basalProfile` | `basal[]` |
| `pumpSettings.insulinActionCurve` | `dia` |
| `settingsManager.settings.units` | `units` |

---

## Download Flows

### 1. Glucose Fetch

```swift
// trio:NightscoutAPI.swift#L60-L98
func fetchLastGlucose(sinceDate: Date? = nil) -> AnyPublisher<[BloodGlucose], Swift.Error> {
    // GET /api/v1/entries/sgv.json?count=1600&find[dateString][$gte]=...
    components.queryItems = [URLQueryItem(name: "count", value: "\(1600)")]
    if let date = sinceDate {
        components.queryItems?.append(
            URLQueryItem(name: "find[dateString][$gte]", 
                        value: Formatter.iso8601withFractionalSeconds.string(from: date))
        )
    }
}
```

### 2. Carbs Fetch

```swift
// trio:NightscoutAPI.swift#L101-L142
func fetchCarbs(sinceDate: Date? = nil) -> AnyPublisher<[CarbsEntry], Swift.Error> {
    // GET /api/v1/treatments.json?find[carbs][$exists]=true
    //     &find[enteredBy][$ne]=Trio (avoid own entries)
    //     &find[created_at][$gt]=...
    components.queryItems = [
        URLQueryItem(name: "find[carbs][$exists]", value: "true"),
        URLQueryItem(name: "find[enteredBy][$ne]", value: CarbsEntry.manual),
        URLQueryItem(name: "find[enteredBy][$ne]", value: NightscoutTreatment.local)
    ]
}
```

**Note**: Trio excludes entries with `enteredBy` matching "Trio" or manual entry identifier to avoid duplicate processing.

### 3. Temp Targets Fetch

```swift
// trio:NightscoutAPI.swift#L202-L244
func fetchTempTargets(sinceDate: Date? = nil) -> AnyPublisher<[TempTarget], Swift.Error> {
    // GET /api/v1/treatments.json?find[eventType]=Temporary+Target
    //     &find[enteredBy][$ne]=Trio
    //     &find[duration][$exists]=true
    components.queryItems = [
        URLQueryItem(name: "find[eventType]", value: "Temporary+Target"),
        URLQueryItem(name: "find[enteredBy][$ne]", value: TempTarget.manual),
        URLQueryItem(name: "find[enteredBy][$ne]", value: NightscoutTreatment.local),
        URLQueryItem(name: "find[duration][$exists]", value: "true")
    ]
}
```

### 4. Remote Commands

**Note (dev branch 0.6.0)**: Remote commands are now handled via the TrioRemoteControl APNS system with encrypted push notifications, replacing the legacy Nightscout Announcement-based system. See [remote-commands.md](remote-commands.md) for the current implementation.

The legacy Announcement fetch API still exists but is deprecated for remote command processing:

---

## Sync Identity

### enteredBy Field

All Trio uploads use a static identifier:

```swift
// trio:NightscoutTreatment.swift#L31
static let local = "Trio"
```

This allows:
1. Identifying Trio-originated entries in Nightscout
2. Filtering out own entries during download to avoid duplicates
3. Distinguishing from other uploaders (Loop, AAPS, xDrip, etc.)

### Deduplication Strategy

| Download Type | Filter Logic |
|---------------|--------------|
| Carbs | `enteredBy != "Trio"` AND `enteredBy != manual` |
| Temp Targets | `enteredBy != "Trio"` AND `enteredBy != manual` |
| Glucose | No filter (always fetches all) |

**Note**: Remote commands are no longer fetched from Nightscout. They are received via encrypted APNS push notifications through the TrioRemoteControl system.

---

## Settings Affecting Sync

| Setting | Location | Effect |
|---------|----------|--------|
| `isUploadEnabled` | TrioSettings | Master upload toggle |
| `isDownloadEnabled` | TrioSettings | Master download toggle |
| `uploadGlucose` | TrioSettings | Enable glucose upload |
| `useLocalGlucoseSource` | TrioSettings | Use local NS instead of remote |
| `localGlucosePort` | TrioSettings | Port for local NS (default 8080) |

---

## Error Handling

Trio uses Combine publishers with retry and error catching:

```swift
// trio:NightscoutAPI.swift#L83-L89
return service.run(request)
    .retry(Config.retryCount)  // 1 retry
    .decode(type: [BloodGlucose].self, decoder: JSONCoding.decoder)
    .catch { error -> AnyPublisher<[BloodGlucose], Swift.Error> in
        warning(.nightscout, "Glucose fetching error: \(error.localizedDescription)")
        return Just([]).setFailureType(to: Swift.Error.self).eraseToAnyPublisher()
    }
```

### Retry Configuration

```swift
// trio:NightscoutAPI.swift#L19-L20
static let retryCount = 1
static let timeout: TimeInterval = 60
```

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Deprecated Announcement-based remote commands, added migration note for APNS TrioRemoteControl |
| 2026-01-16 | Agent | Updated paths to Trio/, updated settings model name to TrioSettings |
| 2026-01-16 | Agent | Initial Nightscout sync documentation from source analysis |
