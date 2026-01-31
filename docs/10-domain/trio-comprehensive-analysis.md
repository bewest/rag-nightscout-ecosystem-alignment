# Trio Comprehensive Analysis

> **Purpose**: Complete analysis of Trio's oref integration, Nightscout sync patterns, and APSManager architecture  
> **Parent**: LIVE-BACKLOG.md - Trio analysis items  
> **Last Updated**: 2026-01-31

## Executive Summary

Trio is an iOS AID (Automated Insulin Delivery) system that integrates the oref1 algorithm via embedded JavaScriptCore. This analysis covers three key areas:

1. **trio-oref/lib/** - JavaScript algorithm bundles and their integration
2. **NightscoutManager/NightscoutAPI** - Sync patterns with Nightscout
3. **APSManager vs LoopDataManager** - Architectural comparison with Loop

---

## 1. oref Integration Mapping (trio-oref/lib/)

### 1.1 Directory Structure

```
trio-oref/lib/
├── determine-basal/
│   ├── autosens.js         # Sensitivity detection algorithm
│   ├── cob.js              # Carbs on board calculation
│   └── determine-basal.js  # Main algorithm (~2000 lines)
├── iob/
│   ├── calculate.js        # IOB calculation core
│   ├── history.js          # Pump history processing
│   ├── index.js            # IOB module entry point
│   └── total.js            # IOB aggregation
├── meal/                    # Carb absorption analysis
├── profile/                 # Profile generation
├── autotune/               # Profile optimization
├── autotune-prep/          # Autotune data preparation
├── oref0-setup/            # Configuration helpers
├── basal-set-temp.js       # Temp basal command generation
├── bolus.js                # Bolus calculation
├── round-basal.js          # Rate rounding utilities
├── pump.js                 # Pump state helpers
├── require-utils.js        # CommonJS compatibility
└── temps.js                # Temp basal history helpers
```

### 1.2 Algorithm Entry Points

| JS Function | Swift Caller | Purpose |
|-------------|--------------|---------|
| `iob.generate()` | `OpenAPS.iob()` | Calculate insulin on board |
| `meal.generate()` | `OpenAPS.meal()` | Calculate carb absorption |
| `autosens.generate()` | `OpenAPS.autosense()` | Calculate sensitivity ratio |
| `determine_basal()` | `OpenAPS.determineBasal()` | Main loop decision |
| `profile.generate()` | `OpenAPS.makeProfile()` | Build algorithm profile |

### 1.3 IOB Calculation (iob/index.js)

```javascript
// iob/index.js:7-82
function generate(inputs, currentIOBOnly, treatments) {
    var treatments = find_insulin(inputs);        // Extract from pump history
    var treatmentsWithZeroTemp = find_insulin(inputs, 240);  // Future zero-temp projection
    
    for (var i=0; i<iStop; i+=5) {
        t = new Date(clock.getTime() + i*60000);
        var iob = sum(opts, t);                   // Calculate IOB at time t
        var iobWithZeroTemp = sum(optsWithZeroTemp, t);
        iobArray.push(iob);
        iobArray[iobArray.length-1].iobWithZeroTemp = iobWithZeroTemp;
    }
    
    iobArray[0].lastBolusTime = lastBolusTime;
    iobArray[0].lastTemp = lastTemp;
    return iobArray;
}
```

**Key Insight**: IOB is projected forward in 5-minute increments for 4 hours, with a parallel "zero-temp" projection showing what would happen if all insulin delivery stopped.

### 1.4 Determine-Basal Algorithm (determine-basal.js)

The main algorithm contains Trio-specific customizations:

```javascript
// determine-basal.js:47-70
function enable_smb(profile, microBolusAllowed, meal_data, bg, target_bg, high_bg, trio_custom_variables, time) {
    // Trio-specific: SMB scheduling based on override windows
    if (trio_custom_variables.smbIsScheduledOff) {
        let currentHour = new Date(time.getHours());
        let startTime = trio_custom_variables.start;
        let endTime = trio_custom_variables.end;
        
        if (startTime < endTime && (currentHour >= startTime && currentHour < endTime)) {
            console.error("SMB disabled: current time is in SMB disabled scheduled");
            return false;
        }
    }
    // ... standard oref SMB logic
}
```

**Trio Customizations**:
- `trio_custom_variables.smbIsScheduledOff` - Schedule-based SMB disable
- `trio_custom_variables.start/end` - SMB disable window
- Override percentage integration for ISF/CR scaling

### 1.5 oref0 vs Trio Divergence

| Feature | oref0 Reference | Trio Implementation |
|---------|-----------------|---------------------|
| SMB Scheduling | Not present | `smbIsScheduledOff` with time windows |
| Override Integration | Not present | `oref2_variables.overridePercentage` |
| TDD Tracking | Basic | Enhanced 10-day weighted average |
| Middleware | Not present | Custom JS injection point |

---

## 2. Nightscout Sync Patterns

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Trio Nightscout Sync                      │
├─────────────────────────────────────────────────────────────┤
│  NightscoutManager.swift (Orchestration Layer)               │
│  ├── Upload Pipelines: carbs, pumpHistory, overrides,        │
│  │    tempTargets, glucose, manualGlucose, deviceStatus      │
│  ├── Throttle: 2-second window per pipeline                  │
│  ├── Combine Integration: CoreData change notifications      │
│  └── Background Context: Isolated for network operations     │
├─────────────────────────────────────────────────────────────┤
│  NightscoutAPI.swift (HTTP Client Layer)                     │
│  ├── API v1 Endpoints: entries, treatments, devicestatus     │
│  ├── Authentication: SHA-1 hashed api-secret header          │
│  ├── Retry: 1 retry, 60-second timeout                       │
│  └── Async/Await: Modern Swift concurrency                   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Upload Pipeline System

```swift
// NightscoutManager.swift:55-66
let uploadPipelineInterval: [NightscoutUploadPipeline: TimeInterval] = [
    .carbs: 2, .pumpHistory: 2, .overrides: 2, .tempTargets: 2,
    .glucose: 2, .manualGlucose: 2, .deviceStatus: 2
]

// Combine-based throttling
func setupLanePipelines() {
    for pipeline in NightscoutUploadPipeline.allCases {
        subject
            .receive(on: uploadPipelineQueue)
            .throttle(for: .seconds(window), scheduler: uploadPipelineQueue, latest: false)
            .sink { await self.runUploadPipeline(pipeline) }
            .store(in: &subscriptions)
    }
}
```

**Key Pattern**: Each upload type has its own throttled pipeline, preventing duplicate uploads within 2-second windows while ensuring all data types eventually sync.

### 2.3 NightscoutAPI Endpoints

```swift
// NightscoutAPI.swift:13-21
private enum Config {
    static let entriesPath = "/api/v1/entries/sgv.json"
    static let uploadEntriesPath = "/api/v1/entries.json"
    static let treatmentsPath = "/api/v1/treatments.json"
    static let statusPath = "/api/v1/devicestatus.json"
    static let profilePath = "/api/v1/profile.json"
    static let retryCount = 1
    static let timeout: TimeInterval = 60
}
```

### 2.4 Deduplication Strategy

```swift
// NightscoutAPI.swift:23-29
private let excludedEnteredBy: [String] = [
    NightscoutTreatment.local,    // "Trio"
    "AndroidAPS",
    "openaps://AndroidAPS",
    "iAPS",
    "loop://iPhone"
]
```

**Fetch Filtering**: When downloading treatments, Trio excludes entries from itself and other known AID systems to prevent:
- Re-importing own uploads
- Double-counting treatments from multi-controller setups

### 2.5 DeviceStatus Upload

```swift
// NightscoutManager.swift:390-409
func uploadDeviceStatus() async throws {
    // 1. Fetch last determination (enacted or suggested)
    let lastEnactedDeterminationID = try await determinationStorage
        .fetchLastDeterminationObjectID(predicate: NSPredicate.enactedDetermination)
    
    // 2. Build NightscoutStatus with:
    //    - openaps: { iob, suggested, enacted, version }
    //    - pump: { clock, battery, reservoir, status }
    //    - uploader: { battery }
    
    // 3. Upload to /api/v1/devicestatus.json
    try await nightscoutAPI.uploadDeviceStatus(status)
}
```

### 2.6 Sync Identity

| Field | Value | Purpose |
|-------|-------|---------|
| `enteredBy` | `"Trio"` | Identifies upload source |
| `device` | `"Trio"` | DeviceStatus device field |
| `_id` | UUID | Nightscout document ID |
| `created_at` | ISO8601 | Treatment timestamp |

---

## 3. APSManager vs LoopDataManager Comparison

### 3.1 Architectural Overview

| Aspect | Trio APSManager | Loop LoopDataManager |
|--------|-----------------|----------------------|
| **Algorithm** | Embedded oref1 (JavaScriptCore) | Native Swift (LoopAlgorithm) |
| **Loop Trigger** | `deviceDataManager.recommendsLoop` | NotificationCenter observers |
| **Concurrency** | `DispatchQueue` + async/await | `DispatchQueue` (dataAccessQueue) |
| **State Storage** | CoreData + FileStorage | HealthKit + In-memory cache |
| **Predictions** | 4 curves (IOB, COB, UAM, ZT) | 1 combined curve |

### 3.2 Loop Cycle Comparison

**Trio APSManager**:
```swift
// APSManager.swift:227-260
private func loop() {
    Task {
        guard await canStartNewLoop() else { return }
        var (loopStatRecord, backgroundTask) = await setupLoop()
        
        try await executeLoop(loopStatRecord: &loopStatRecord)
        
        requestNightscoutUpload([.carbs, .pumpHistory, .overrides, .tempTargets])
    }
}

private func executeLoop(loopStatRecord: inout LoopStats) async throws {
    try await determineBasal()                    // Run oref algorithm
    guard settings.closedLoop else { return }     // Open-loop check
    try await enactDetermination()                // Execute temp/SMB
}
```

**Loop LoopDataManager**:
```swift
// LoopDataManager.swift:174-204
// Observer-based trigger
NotificationCenter.default.addObserver(
    forName: CarbStore.carbEntriesDidChange,
    object: self.carbStore
) { _ in
    self.dataAccessQueue.async {
        self.carbEffect = nil
        self.carbsOnBoard = nil
        self.notify(forChange: .carbs)
    }
}
```

### 3.3 Algorithm Integration

**Trio**: JavaScript bridge with JSON serialization
```swift
// OpenAPS.swift:6-7
final class OpenAPS {
    private let jsWorker = JavaScriptWorker()
    
    func determineBasal(currentTemp: TempBasal, clock: Date) async throws -> Determination? {
        // 1. Fetch glucose, carbs, pump history from CoreData
        // 2. Serialize to JSON
        // 3. Call JS determine_basal()
        // 4. Parse JSON result to Determination
    }
}
```

**Loop**: Native Swift algorithm
```swift
// LoopDataManager uses LoopKit's algorithm directly
// No serialization overhead, type-safe throughout
let prediction = loopAlgorithm.predictGlucose(...)
let dose = loopAlgorithm.recommendDose(...)
```

### 3.4 State Management

| Component | Trio | Loop |
|-----------|------|------|
| **Glucose** | CoreData (GlucoseStored) | GlucoseStore (HealthKit) |
| **Insulin** | CoreData (PumpEventStored) | DoseStore (HealthKit) |
| **Carbs** | CoreData (CarbEntryStored) | CarbStore (HealthKit) |
| **Settings** | FileStorage + SettingsManager | LoopSettings (UserDefaults) |
| **Loop State** | @Persisted properties | Locked<LoopSettings> |

### 3.5 Override Handling

**Trio**:
```swift
// Overrides affect algorithm via oref2_variables
let oref2_variables = Oref2_variables(
    useOverride: useOverride,
    overridePercentage: overridePercentage,
    isfAndCr: isfAndCr,
    // ... passed to JS algorithm
)
```

**Loop**:
```swift
// Overrides modify therapy settings schedules
overrideHistory.recordOverride(settings.scheduleOverride)
carbStore.insulinSensitivitySchedule = newValue.insulinSensitivitySchedule
doseStore.basalProfile = newValue.basalRateSchedule
```

### 3.6 Key Differences Summary

| Feature | Trio | Loop |
|---------|------|------|
| SMB Support | Yes (oref1) | No |
| UAM Detection | Yes | Via MealDetectionManager |
| Dynamic ISF | Via autosens | Retrospective Correction |
| Prediction Curves | 4 separate | 1 combined |
| Algorithm Updates | JS bundle replacement | App update required |
| Middleware | Supported | Not supported |

---

## Identified Gaps

### GAP-TRIO-SYNC-001: API v1 Only

**Description**: Trio uses only Nightscout API v1 endpoints, not the newer v3 API.

**Impact**: Missing v3 features like `srvModified` tracking, PATCH updates, and improved pagination.

**Remediation**: Add v3 support as optional backend, with v1 fallback.

### GAP-TRIO-SYNC-002: Limited Deduplication

**Description**: Deduplication relies solely on `enteredBy` field matching.

**Impact**: If `enteredBy` is modified or missing, duplicates can occur.

**Remediation**: Add secondary deduplication on `_id` or `identifier` fields.

### GAP-TRIO-SYNC-003: No Offline Queue

**Description**: Failed uploads are not queued for retry.

**Impact**: Data loss during network outages.

**Remediation**: Implement persistent upload queue with exponential backoff.

### GAP-TRIO-OREF-001: oref Bundle Version Tracking

**Description**: No explicit version tracking of embedded oref JS bundles.

**Impact**: Difficult to trace algorithm behavior to specific oref version.

**Remediation**: Add version file or commit hash to trio-oref/ directory.

---

## Requirements Extracted

### REQ-TRIO-001: SMB Scheduling Support

**Statement**: The system MUST support time-based SMB enable/disable windows.

**Rationale**: Users may want SMBs disabled during sleep or exercise.

**Verification**: Test SMB decisions at boundary times of scheduled windows.

### REQ-TRIO-002: Multi-AID Deduplication

**Statement**: The system MUST filter out treatments from known AID systems during download.

**Rationale**: Prevents double-counting in multi-controller environments.

**Verification**: Import treatments with various `enteredBy` values, verify filtering.

### REQ-TRIO-003: Upload Throttling

**Statement**: The system SHOULD throttle uploads to prevent server overload.

**Rationale**: Rapid loop cycles could generate excessive API calls.

**Verification**: Trigger multiple upload requests within 2 seconds, verify single actual upload.

---

## Source Files Analyzed

| File | Lines | Purpose |
|------|-------|---------|
| `externals/Trio/Trio/Sources/APS/APSManager.swift` | ~900 | Loop orchestration |
| `externals/Trio/Trio/Sources/APS/OpenAPS/OpenAPS.swift` | ~908 | Algorithm bridge |
| `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift` | ~600 | Sync orchestration |
| `externals/Trio/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift` | ~576 | HTTP client |
| `externals/Trio/trio-oref/lib/iob/index.js` | ~85 | IOB calculation |
| `externals/Trio/trio-oref/lib/determine-basal/determine-basal.js` | ~2000 | Main algorithm |
| `externals/LoopWorkspace/Loop/Loop/Managers/LoopDataManager.swift` | ~1200 | Loop comparison |

---

## Cross-References

- [trio-openaps-bridge-analysis.md](trio-openaps-bridge-analysis.md) - JavaScriptCore bridge details
- [mapping/trio/nightscout-sync.md](../../mapping/trio/nightscout-sync.md) - Field mappings
- [mapping/trio/algorithm.md](../../mapping/trio/algorithm.md) - Algorithm flow details
- [mapping/loop/algorithm.md](../../mapping/loop/algorithm.md) - Loop algorithm for comparison

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-31 | Agent | Initial comprehensive analysis covering oref, Nightscout sync, and APSManager comparison |
