# xDrip4iOS Nightscout Sync

This document details how xDrip4iOS synchronizes data with Nightscout, including upload/download logic, API paths, timing, and error handling.

---

## Source File

Primary sync logic is in:
```
xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift (~1692 lines)
```

---

## API Endpoints

### Endpoint Paths

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L21-L34
private let nightscoutEntriesPath = "/api/v1/entries"
private let nightscoutTreatmentPath = "/api/v1/treatments"
private let nightscoutDeviceStatusPath = "/api/v1/devicestatus"
private let nightscoutAuthTestPath = "/api/v1/experiments/test"
private let nightscoutProfilePath = "/api/v1/profile"
```

### Follower Entry Endpoint

```swift
// xdrip:xdrip/Managers/Nightscout/Endpoint+Nightscout.swift#L37
"/api/v1/entries/sgv.json"  // With ?count=N&token=T parameters
```

---

## Authentication

### Dual Authentication Support

xDrip4iOS supports both API_SECRET and token-based authentication:

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L1091-L1105

// Token authentication (query parameter)
if let token = UserDefaults.standard.nightscoutToken {
    let queryItems = [URLQueryItem(name: "token", value: token)]
    urlComponents.queryItems = queryItems
}

// API_SECRET authentication (header)
if let apiKey = UserDefaults.standard.nightscoutAPIKey {
    request.setValue(apiKey.sha1(), forHTTPHeaderField: "api-secret")
}
```

### Authentication Check

Before upload, xDrip4iOS validates credentials exist:

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L191-L194
if UserDefaults.standard.nightscoutAPIKey == nil 
   && UserDefaults.standard.nightscoutToken == nil {
    return
}
```

---

## Upload Operations

### BG Reading Upload

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L985-L1048
private func uploadBgReadingsToNightscout(lastConnectionStatusChangeTimeStamp: Date?) {
    // Get readings newer than last upload timestamp
    var timeStamp = Date(timeIntervalSinceNow: 
        TimeInterval(-ConstantsNightscout.maxBgReadingsDaysToUpload))
    
    if let lastUpload = UserDefaults.standard.timeStampLatestNightscoutUploadedBgReading {
        timeStamp = max(lastUpload, timeStamp)
    }
    
    // Add 10 seconds buffer (for Libre smoothing edge cases)
    timeStamp = timeStamp.addingTimeInterval(10.0)
    
    // Filter readings with minimum time gap
    let minimumGap = UserDefaults.standard.storeFrequentReadingsInNightscout 
        ? 1 minute : 5 minutes
    
    var bgReadingsToUpload = bgReadingsAccessor
        .getLatestBgReadings(fromDate: timeStamp)
        .filter(minimumTimeBetweenTwoReadingsInMinutes: minimumGap)
    
    // Limit batch size
    if bgReadingsToUpload.count > ConstantsNightscout.maxReadingsToUpload {
        bgReadingsToUpload = Array(bgReadingsToUpload.prefix(maxReadingsToUpload))
    }
    
    // Map to NS format and upload
    let dictionaries = bgReadingsToUpload.map { 
        $0.dictionaryRepresentationForNightscoutUpload() 
    }
    
    uploadData(dataToUpload: dictionaries, path: nightscoutEntriesPath) {
        UserDefaults.standard.timeStampLatestNightscoutUploadedBgReading = 
            bgReadingsToUpload.first?.timeStamp
        
        // Recursive call if more readings to upload
        if callAgainNeeded {
            self.uploadBgReadingsToNightscout(lastConnectionStatusChangeTimeStamp)
        }
    }
}
```

### Treatment Upload (New)

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L397-L399
// Filter: No ID yet AND not uploaded AND not deleted
let treatmentsToUpload = treatmentsToSync.filter { treatment in 
    treatment.id == TreatmentEntry.EmptyId 
    && !treatment.uploaded 
    && !treatment.treatmentdeleted 
}

uploadTreatmentsToNightscout(treatmentsToUpload: treatmentsToUpload)
```

### Treatment Update (Existing)

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L409
// Filter: Has ID AND not uploaded AND not deleted
let treatmentsToUpdate = treatmentsToSync.filter { treatment in 
    treatment.id != TreatmentEntry.EmptyId 
    && !treatment.uploaded 
    && !treatment.treatmentdeleted 
}

// Update one at a time via PUT
func updateTreatment() {
    if let treatment = treatmentsToUpdate.first {
        updateTreatmentToNightscout(treatmentToUpdate: treatment) { result in
            updateTreatment()  // Process next
        }
    }
}
```

### Treatment Delete

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L452-L456
// Filter: Marked deleted AND not synced
let treatmentsToDelete = treatmentsToSync.filter { treatment in 
    treatment.treatmentdeleted && !treatment.uploaded 
}

// Delete one at a time via DELETE
func deleteTreatment() {
    if let treatment = treatmentsToDelete.first {
        deleteTreatmentAtNightscout(treatmentToDelete: treatment) { result in
            deleteTreatment()  // Process next
        }
    }
}
```

---

## Download Operations

### Treatment Download

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L440
getLatestTreatmentsNSResponses(treatmentsToSync: treatmentsToSync) { result in
    // Parse and create local TreatmentEntry objects
    // Handles deduplication via ID matching
}
```

### Profile Download

```swift
// Profile is fetched and cached locally
// NightscoutProfileResponse → NightscoutProfile transformation
// Stored in UserDefaults via JSON encoding

if let profileData = sharedUserDefaults?.object(forKey: "nightscoutProfile") as? Data,
   let nightscoutProfile = try? JSONDecoder().decode(NightscoutProfile.self, from: profileData) {
    self.profile = nightscoutProfile
}
```

### Follower Mode Download

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutFollowManager.swift#L123-L175
@objc public func download() {
    guard UserDefaults.standard.nightscoutEnabled else { return }
    guard !UserDefaults.standard.isMaster else { return }
    guard UserDefaults.standard.followerDataSourceType == .nightscout else { return }
    
    // Calculate count based on time since last reading
    let count = Int(-timeStampOfFirstBgReadingToDowload.timeIntervalSinceNow / 300 + 1)
    
    // GET /api/v1/entries/sgv.json?count=N&token=T
    let endpoint = Endpoint.getEndpointForLatestNSEntries(
        hostAndScheme: nightscoutUrl,
        count: count,
        token: UserDefaults.standard.nightscoutToken
    )
    
    // Parse response and create BgReading objects
}
```

---

## Sync Timing & Throttling

### Minimum Sync Interval

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L72-73
private let idleNightscoutSyncInterval: TimeInterval = 300  // 5 minutes cooldown

// ConstantsNightscout.minimiumTimeBetweenTwoTreatmentSyncsInSeconds
```

### Sync Debouncing

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L69-78
private var relaunchScheduled: Bool = false
private var lastRelaunchAt: Date = .distantPast
private let relaunchDebounceInterval: TimeInterval = 1.0

private func scheduleNightscoutSyncRelaunch() {
    if relaunchScheduled || Date().timeIntervalSince(lastRelaunchAt) < relaunchDebounceInterval {
        return  // Skip if already scheduled or too recent
    }
    relaunchScheduled = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
        self.syncWithNightscout()
    }
}
```

### Sync State Tracking

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L81-93
private var nightscoutSyncStartTimeStamp: Date?  // nil = no sync running
private let maxDurationNightscoutSync = TimeInterval(minutes: 1)  // Timeout
private var nightscoutSyncRequired = false  // Queued sync flag
private var lastSyncHadChanges: Bool = true  // Affects next interval
```

---

## Sync Flow Sequence

```
1. syncWithNightscout() called
   │
   ├─ Check: Already syncing? → Set nightscoutSyncRequired = true, return
   │
   ├─ Set nightscoutSyncStartTimeStamp = now
   │
   ├─ Step 1: Upload NEW treatments (POST)
   │     │
   │     └─ Filter: id == EmptyId && !uploaded && !deleted
   │
   ├─ Step 2: Update EXISTING treatments (PUT)
   │     │
   │     └─ Process one at a time recursively
   │
   ├─ Step 3: Download treatments from NS (GET)
   │     │
   │     └─ Parse and create/update local entries
   │
   ├─ Step 4: Delete treatments at NS (DELETE)
   │     │
   │     └─ Process one at a time recursively
   │
   ├─ Set nightscoutSyncStartTimeStamp = nil
   │
   └─ If nightscoutSyncRequired → Schedule relaunch
```

---

## Upload vs Master/Follower Mode

### Master Mode Upload Control

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L187-L189
if UserDefaults.standard.isMaster && !UserDefaults.standard.masterUploadDataToNightscout {
    return  // Master mode but upload disabled
}
```

### Follower Mode Upload Control

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L187
// Don't upload if follower source IS Nightscout (would create loop)
if !UserDefaults.standard.isMaster 
   && UserDefaults.standard.followerDataSourceType == .nightscout {
    return
}

// Don't upload if follower upload is disabled
if !UserDefaults.standard.isMaster 
   && !UserDefaults.standard.followerUploadDataToNightscout {
    return
}
```

---

## Schedule Support

xDrip4iOS supports scheduled Nightscout sync windows:

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L196-L203
if UserDefaults.standard.nightscoutUseSchedule {
    if let schedule = UserDefaults.standard.nightscoutSchedule {
        if !schedule.indicatesOn(forWhen: Date()) {
            return  // Outside scheduled window
        }
    }
}
```

---

## Error Handling

### HTTP Response Handling

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L1122-L1124
var nightscoutResult = NightscoutResult.success(0)

// Check HTTP status codes
// Handle authentication errors
// Parse response data
```

### Result Types

```swift
enum NightscoutResult {
    case success(Int)  // Count of items processed
    case failed
    case urlNil
    // etc.
    
    func successFull() -> Bool
    func amountOfNewOrUpdatedTreatments() -> Int
    func description() -> String
}
```

---

## Background/Foreground Handling

### App State Awareness

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L535-L541
private func scheduleNightscoutSyncRelaunch() {
    if UIApplication.shared.applicationState == .background {
        pendingForegroundSync = true
        nightscoutSyncRequired = true
        return  // Defer until active
    }
    // ... proceed with sync
}

@objc private func handleAppDidBecomeActive() {
    if pendingForegroundSync {
        pendingForegroundSync = false
        scheduleNightscoutSyncRelaunch()
    }
}
```

### Background Follower Refresh

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L568-L579
private let backgroundFollowerRefreshCooldown: TimeInterval = 60

private func performBackgroundFollowerRefreshIfNeeded() {
    guard UserDefaults.standard.nightscoutFollowType != .none else { return }
    
    if now.timeIntervalSince(lastBackgroundFollowerRefreshAt) < backgroundFollowerRefreshCooldown {
        return  // Cooldown not elapsed
    }
    // ... perform refresh
}
```

---

## HTTP Request Construction

```swift
// xdrip:xdrip/Managers/Nightscout/NightscoutSyncManager.swift#L1097-L1107
var request = URLRequest(url: url)
request.httpMethod = httpMethod ?? "POST"
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.setValue("application/json", forHTTPHeaderField: "Accept")

if let apiKey = UserDefaults.standard.nightscoutAPIKey {
    request.setValue(apiKey.sha1(), forHTTPHeaderField: "api-secret")
}

let urlSessionUploadTask = URLSession.shared.uploadTask(
    with: request, 
    from: dataToUploadAsJSON
) { data, response, error in
    // Handle response
}
urlSessionUploadTask.resume()
```

---

## Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `maxBgReadingsDaysToUpload` | ~days | Max age of readings to upload |
| `maxReadingsToUpload` | ~count | Batch size limit |
| `minimiumTimeBetweenTwoReadingsInMinutes` | 5 | Gap between uploads (normal) |
| `minimiumTimeBetweenTwoReadingsInMinutesFrequentUploads` | 1 | Gap between uploads (frequent mode) |
| `minimiumTimeBetweenTwoTreatmentSyncsInSeconds` | seconds | Sync throttle |
| `maxTreatmentsToUpload` | count | Treatment batch limit |
| `maxTreatmentsDaysToUpload` | days | Max age of treatments |
