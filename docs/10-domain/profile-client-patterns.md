# Profile Client Patterns

**Status**: Complete  
**Date**: 2026-03-18  
**Related Backlog**: [profile-api-array-regression.md](../backlogs/profile-api-array-regression.md#track-4-client-analysis-optional)

## Overview

This document analyzes how different AID (Automated Insulin Delivery) clients upload therapy profiles to Nightscout. Understanding these patterns ensures API changes maintain compatibility.

## Quick Reference Matrix

| Client | Uploads Profiles? | Endpoint | Data Format | `_id` Generation | Special Fields |
|--------|-------------------|----------|-------------|------------------|----------------|
| **Loop (NightscoutKit)** | ✅ Yes | `POST /api/v1/profile` | **Array** (even single) | Server-generated | `syncIdentifier` (maps to `_id`) |
| **AAPS** | ✅ Yes | `POST /v3/profile` | Single object | Server-generated | `identifier` (v3), `app: "AAPS"` |
| **Trio** | ✅ Yes | `POST /api/v1/profile.json` | Single object | Server-generated | None |
| **xDrip+** | ❌ No | N/A | N/A | N/A | Local profiles only |

## Key Findings

### 1. Loop is the ONLY client that sends arrays

Loop/NightscoutKit wraps even single profiles in an array:
```swift
// NightscoutKit/Sources/NightscoutKit/NightscoutClient.swift:404
postToNS([profileSet.dictionaryRepresentation], url: url, completion: completion)
```

**This is why the array handling fix was critical for Loop users.**

### 2. All clients expect server-generated `_id`

No client generates its own MongoDB ObjectId for profiles:
- Loop: Caches returned `_id` as `syncIdentifier`
- AAPS: Server returns `identifier` in v3 response
- Trio: Does not track `_id` locally

### 3. xDrip+ maintains profiles locally only

xDrip+ stores profiles in SharedPreferences and never syncs them with Nightscout in either direction.

---

## Detailed Analysis

### Loop / NightscoutKit

**Source**: `externals/NightscoutKit/`

#### Handler Classes
- **HTTP Client**: `NightscoutClient` (`Sources/NightscoutKit/NightscoutClient.swift:398-420`)
- **Data Model**: `ProfileSet` struct (`Sources/NightscoutKit/Models/ProfileSet.swift:18-184`)

#### Endpoint & Method
```
POST /api/v1/profile
```

#### Data Format: Array
```swift
// Single profile upload wraps in array (line 404):
postToNS([profileSet.dictionaryRepresentation], url: url, completion: completion)

// Batch upload sends array directly (line 408):
postToNS(profileSets.map { $0.dictionaryRepresentation }, endpoint: .profile, completion: completion)
```

#### Payload Structure
```json
[{
  "defaultProfile": "Default",
  "startDate": "2026-03-18T12:00:00.000Z",
  "mills": "1773871200000",
  "units": "mg/dL",
  "enteredBy": "Loop",
  "loopSettings": {
    "dosingEnabled": true,
    "overridePresets": [],
    "scheduleOverride": null,
    "minimumBGGuard": 80,
    "preMealTargetRange": [80, 80],
    "maximumBasalRatePerHour": 4.0,
    "maximumBolus": 10.0,
    "deviceToken": "...",
    "dosingStrategy": "automaticBolus",
    "bundleIdentifier": "com.loopkit.Loop"
  },
  "store": {
    "Default": {
      "dia": 6,
      "carbs_hr": "0",
      "delay": "0",
      "timezone": "America/New_York",
      "target_low": [{"time": "00:00", "value": 100, "timeAsSeconds": 0}],
      "target_high": [{"time": "00:00", "value": 110, "timeAsSeconds": 0}],
      "sens": [{"time": "00:00", "value": 50, "timeAsSeconds": 0}],
      "basal": [{"time": "00:00", "value": 1.0, "timeAsSeconds": 0}],
      "carbratio": [{"time": "00:00", "value": 10, "timeAsSeconds": 0}],
      "units": "mg/dL"
    }
  }
}]
```

#### ID Handling
- Initial upload: No `_id` sent
- Server response: Returns `_id` (MongoDB ObjectId)
- Loop caches: Stores as `syncIdentifier` (`ProfileSet.swift:171`)
- Updates: Adds `_id` to payload for PUT requests (`NightscoutClient.swift:418`)

---

### AAPS / AndroidAPS

**Source**: `externals/AndroidAPS/`

#### Handler Classes
- **Sync Plugin**: `NSClientV3Plugin` (`plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt:454`)
- **HTTP Service**: `NightscoutRemoteService` (`core/nssdk/src/main/kotlin/app/aaps/core/nssdk/networking/NightscoutRemoteService.kt:102`)
- **Profile Builder**: `ProfilePlugin` (`plugins/main/src/main/kotlin/app/aaps/plugins/main/profile/ProfilePlugin.kt:398-428`)

#### Endpoint & Method
```
POST /v3/profile
```
Note: AAPS uses API v3, not v1.

#### Data Format: Single Object
```kotlin
// NSAndroidClientImpl.kt:438
val response = api.createProfile(JsonParser.parseString(remoteProfileStore.toString()).asJsonObject)
```

#### Payload Structure
```json
{
  "date": 1773871200000,
  "created_at": "2026-03-18T12:00:00.000Z",
  "startDate": "2026-03-18T12:00:00.000Z",
  "defaultProfile": "Default",
  "app": "AAPS",
  "store": {
    "Default": {
      "dia": 5,
      "carbratio": [{"time": "00:00", "timeAsSeconds": 0, "value": 10}],
      "sens": [{"time": "00:00", "timeAsSeconds": 0, "value": 50}],
      "basal": [{"time": "00:00", "timeAsSeconds": 0, "value": 1.0}],
      "target_low": [{"time": "00:00", "timeAsSeconds": 0, "value": 100}],
      "target_high": [{"time": "00:00", "timeAsSeconds": 0, "value": 110}],
      "units": "mg/dl",
      "timezone": "Europe/Berlin"
    }
  }
}
```

#### ID Handling
- No `identifier` sent by client
- Server generates and returns `identifier` in v3 response
- From `RemoteProfileStore.kt:15`:
  > "The client should not create the identifier, the server automatically assigns it when the document is inserted."

---

### Trio

**Source**: `externals/Trio-dev/`

#### Handler Classes
- **Manager**: `BaseNightscoutManager` (`Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift:640`)
- **HTTP Client**: `NightscoutAPI` (`Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:411`)
- **Data Models**: `NightscoutProfileStore`, `ScheduledNightscoutProfile` (`NightscoutStatus.swift:38-64`)

Note: Trio does **NOT** use NightscoutKit - it has its own implementation.

#### Endpoint & Method
```
POST /api/v1/profile.json
```

#### Data Format: Single Object
```swift
// NightscoutAPI.swift:440 - POST single object
request.httpMethod = "POST"
request.httpBody = try JSONCoding.encoder.encode(profile)
```

#### Payload Structure
```json
{
  "defaultProfile": "default",
  "startDate": "2026-03-18T12:00:00.000Z",
  "mills": 1773871200000,
  "units": "mg/dl",
  "enteredBy": "Trio",
  "bundleIdentifier": "org.nightscout.Trio",
  "deviceToken": "...",
  "isAPNSProduction": true,
  "teamID": "...",
  "expirationDate": "2027-03-18T12:00:00.000Z",
  "overridePresets": [],
  "store": {
    "default": {
      "dia": 6,
      "carbs_hr": 20,
      "delay": 0,
      "timezone": "America/New_York",
      "target_low": [{"time": "00:00", "value": 100, "timeAsSeconds": 0}],
      "target_high": [{"time": "00:00", "value": 110, "timeAsSeconds": 0}],
      "sens": [{"time": "00:00", "value": 50, "timeAsSeconds": 0}],
      "basal": [{"time": "00:00", "value": 1.0, "timeAsSeconds": 0}],
      "carbratio": [{"time": "00:00", "value": 10, "timeAsSeconds": 0}],
      "units": "mg/dl"
    }
  }
}
```

#### ID Handling
- `NightscoutProfileStore` has no `_id` field
- Server generates MongoDB ObjectId on insert
- Trio does not track the returned `_id`

---

### xDrip+

**Source**: `externals/xDrip/`

#### Profile Handling
**xDrip+ does NOT upload profiles to Nightscout.**

Profiles are:
- Stored locally in SharedPreferences (`saved_profile_list_json`)
- Edited via `ProfileEditor.java`
- Used for local insulin calculations
- Exported only in local data dumps (`TreatmentsToJson.java:38`)

#### NightscoutUploader Endpoints
The `NightscoutUploader.NightscoutService` interface (`NightscoutUploader.java:127-162`) defines:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `entries` | POST | Glucose entries |
| `devicestatus` | POST | Device status |
| `treatments` | POST/PUT/GET/DELETE | Treatments |
| `activity` | POST | Activity data |

**No `/profile` endpoint is defined.**

---

## Implications for Nightscout API

### Array Handling (Fixed)
The profile API must handle both:
- **Arrays** (Loop sends `[profile]`)
- **Single objects** (AAPS, Trio send `{profile}`)

Fixed in commit `cbb6d061`:
```javascript
// Normalize to array
if (!Array.isArray(data)) { data = [data]; }
```

### API Version Differences
- **v1** (`/api/v1/profile`): Used by Loop, Trio
- **v3** (`/v3/profile`): Used by AAPS

Both must support the same profile schema.

### ID Generation
All clients expect server-generated IDs:
- Never validate client-provided `_id` on profile POST
- Always return generated `_id`/`identifier` in response

---

## Source File References

### Loop/NightscoutKit
- `externals/NightscoutKit/Sources/NightscoutKit/NightscoutClient.swift:398-420`
- `externals/NightscoutKit/Sources/NightscoutKit/Models/ProfileSet.swift:18-184`

### AAPS
- `externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt:454-458`
- `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/networking/NightscoutRemoteService.kt:102`
- `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/NSAndroidClientImpl.kt:436-443`
- `externals/AndroidAPS/plugins/main/src/main/kotlin/app/aaps/plugins/main/profile/ProfilePlugin.kt:398-428`
- `externals/AndroidAPS/core/nssdk/src/main/kotlin/app/aaps/core/nssdk/remotemodel/RemoteProfileStore.kt:15`

### Trio
- `externals/Trio-dev/Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift:640-778`
- `externals/Trio-dev/Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:411-446`
- `externals/Trio-dev/Trio/Sources/Services/Network/Nightscout/NightscoutStatus.swift:38-64`

### xDrip+
- `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java:127-162`
- `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/ui/ProfileEditor.java:336-344`
