# Tidepool Integration Inventory

> **Research Document** | Created: 2026-02-01
> **Source**: Ready Queue #6 (ECOSYSTEM-BACKLOG.md)
> **Focus**: Document Tidepool integration status across AID ecosystem apps

## Executive Summary

Tidepool integration exists in **5 of 7** major ecosystem apps, with varying levels of maturity:

| App | Status | Lines of Code | Data Types |
|-----|--------|---------------|------------|
| **AAPS** | ✅ Full Integration | ~1,855 | 7 types |
| **Loop** | ✅ Full Integration | ~7,006 | 10+ types |
| **Trio** | ✅ Full Integration | ~7,006 | 10+ types (shared with Loop) |
| **xDrip+** | ✅ Full Integration | ~1,767 | 5 types |
| **Nocturne** | ✅ Connector | ~977 | 5 types |
| **xDrip4iOS** | ❌ Not Implemented | - | - |
| **DiaBLE** | ❌ Not Implemented | - | - |

---

## Integration Details

### AAPS (Android)

**Location**: `plugins/sync/src/main/kotlin/app/aaps/plugins/sync/tidepool/`

**Architecture**: Plugin-based sync with event-driven uploads

**Data Types Uploaded**:
| Type | Element Class | Tidepool Type |
|------|---------------|---------------|
| CGM readings | `SensorGlucoseElement` | `cbg` |
| Fingerstick | `BloodGlucoseElement` | `smbg` |
| Bolus | `BolusElement` | `bolus` |
| Basal | `BasalElement` | `basal` |
| Carbs | `WizardElement` | `wizard` |
| Profile | `ProfileElement` | `pumpSettings` |

**Key Files**:
- `TidepoolPlugin.kt` - Main plugin class
- `TidepoolUploader.kt` - HTTP API client
- `UploadChunk.kt` - Batch upload logic
- `Session.kt` - Authentication session

**Authentication**: Email/password → session token

**Features**:
- ✅ Automatic upload on new BG
- ✅ Rate limiting (prevents API spam)
- ✅ Chunked uploads
- ✅ Dataset management (open/close)
- ✅ Connectivity-aware (respects network settings)

---

### Loop (iOS)

**Location**: `LoopWorkspace/TidepoolService/` (git submodule)

**Architecture**: LoopKit Service plugin using TidepoolKit

**Data Types Uploaded**:
| Type | Extension | Tidepool Type |
|------|-----------|---------------|
| CGM | `StoredGlucoseSample` | `cbg` |
| Carbs | `StoredCarbEntry`, `SyncCarbObject` | `food` |
| Bolus | `DoseEntry` | `bolus` |
| Basal | `DoseEntry` | `basal` |
| Pump events | `PersistedPumpEvent` | various |
| Settings | `StoredSettings` | `pumpSettings` |
| Decisions | `StoredDosingDecision` | `dosingDecision` |
| Alerts | `SyncAlertObject` | `alert` |

**Key Files**:
- `TidepoolService.swift` - Main service class
- `TidepoolServiceKit/Extensions/` - Data type converters

**Authentication**: OAuth2 via TidepoolKit

**Features**:
- ✅ LoopKit Service protocol integration
- ✅ OAuth2 authentication
- ✅ Keychain session storage
- ✅ Dosing decision uploads (unique to Loop)
- ✅ Alert synchronization

**Dependency**: `TidepoolKit` (official SDK)

---

### Trio (iOS)

**Location**: `Trio/TidepoolService/` (git submodule, same as Loop)

**Architecture**: Identical to Loop - uses shared TidepoolService submodule

**Data Types**: Same as Loop (shared codebase)

**Key Difference**: Trio uses `trio` branch of loopandlearn fork

**Features**: Same as Loop

**Note**: TidepoolService is 100% code-shared between Loop and Trio via git submodule.

---

### xDrip+ (Android)

**Location**: `app/src/main/java/com/eveningoutpost/dexdrip/tidepool/`

**Architecture**: Direct HTTP integration (no SDK)

**Data Types Uploaded**:
| Type | Element Class | Tidepool Type |
|------|---------------|---------------|
| CGM | `ESensorGlucose` | `cbg` |
| Fingerstick | `EBloodGlucose` | `smbg` |
| Bolus | `EBolus` | `bolus` |
| Basal | `EBasal` | `basal` |
| Carbs | `EWizard` | `wizard` |

**Key Files**:
- `TidepoolUploader.java` - Main upload class
- `TidepoolEntry.java` - Menu/settings entry
- `UploadChunk.java` - Batch management
- `Session.java` - Auth session

**Authentication**: Email/password → session token

**Features**:
- ✅ Background sync
- ✅ Chunked uploads
- ✅ Dataset management
- ❌ No OAuth2 (uses legacy auth)
- ❌ No dosing decision uploads

---

### Nocturne (Backend)

**Location**: `src/Connectors/Nocturne.Connectors.Tidepool/`

**Architecture**: .NET hosted service connector for bidirectional sync

**Data Types**:
| Type | Model Class | Direction |
|------|-------------|-----------|
| CGM | `TidepoolBgValue` | Read |
| Food | `TidepoolFood` | Read |
| Bolus | `TidepoolBolus` | Read |
| Activity | `TidepoolPhysicalActivity` | Read |

**Key Files**:
- `TidepoolConnectorService.cs` - Main connector
- `TidepoolAuthTokenProvider.cs` - Auth handling
- `TidepoolHostedService.cs` - Background service

**Features**:
- ✅ Reads data FROM Tidepool (not just upload)
- ✅ Normalizes to Nightscout format
- ✅ Background polling
- ✅ Token refresh

**Unique**: Only integration that reads FROM Tidepool (others only upload)

---

## Apps Without Tidepool Integration

### xDrip4iOS

**Status**: ❌ Not implemented

**Reason**: Focus on CGM display, not data aggregation

**Gap**: Users must use separate app (Loop/Trio) for Tidepool uploads

### DiaBLE

**Status**: ❌ Not implemented

**Reason**: Focus on Libre sensor reading, minimal cloud features

**Gap**: No path to Tidepool for DiaBLE-only users

---

## Integration Matrix

| Feature | AAPS | Loop | Trio | xDrip+ | Nocturne |
|---------|------|------|------|--------|----------|
| **Upload CGM** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Upload Bolus** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Upload Basal** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Upload Carbs** | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Upload Profile** | ✅ | ✅ | ✅ | ❌ | ❌ |
| **Upload Decisions** | ❌ | ✅ | ✅ | ❌ | ❌ |
| **Read from Tidepool** | ❌ | ❌ | ❌ | ❌ | ✅ |
| **OAuth2** | ❌ | ✅ | ✅ | ❌ | ✅ |
| **Official SDK** | ❌ | ✅ | ✅ | ❌ | ❌ |

---

## API Patterns

### Authentication

| App | Method | Token Storage |
|-----|--------|---------------|
| AAPS | Email/password | SharedPreferences |
| Loop/Trio | OAuth2 | Keychain |
| xDrip+ | Email/password | SharedPreferences |
| Nocturne | OAuth2 | Memory/Config |

### Upload Patterns

| App | Batch Size | Trigger | Rate Limit |
|-----|------------|---------|------------|
| AAPS | Configurable | New BG event | Yes |
| Loop/Trio | Per-datum | LoopKit delegate | No |
| xDrip+ | Chunked | Background service | Yes |
| Nocturne | N/A (read-only) | Polling interval | N/A |

---

## Gaps Identified

### GAP-TIDEPOOL-001: No iOS-only Tidepool Path

**Description**: xDrip4iOS and DiaBLE users have no direct Tidepool integration.

**Impact**: Users must run Loop/Trio in parallel just for Tidepool sync.

**Remediation**: Consider shared TidepoolKit integration package for iOS CGM apps.

### GAP-TIDEPOOL-002: Legacy Auth in Android Apps

**Description**: AAPS and xDrip+ use deprecated email/password auth instead of OAuth2.

**Impact**: Less secure, may break if Tidepool deprecates legacy auth.

**Remediation**: Migrate to OAuth2 flow (requires Android auth library).

### GAP-TIDEPOOL-003: No Nightscout ↔ Tidepool Bidirectional Sync

**Description**: cgm-remote-monitor has no Tidepool connector. Only Nocturne reads from Tidepool.

**Impact**: Nightscout users can't import historical Tidepool data.

**Remediation**: Port Nocturne connector to cgm-remote-monitor or create nightscout-connect plugin.

### GAP-TIDEPOOL-004: Dosing Decision Upload Inconsistency

**Description**: Only Loop/Trio upload `dosingDecision` data type. AAPS/xDrip+ don't.

**Impact**: Incomplete algorithm analysis for AAPS users in Tidepool.

**Remediation**: Add dosingDecision element to AAPS TidepoolPlugin.

---

## Source Files Analyzed

| App | Path | Lines |
|-----|------|-------|
| AAPS | `externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/tidepool/` | ~1,855 |
| Loop | `externals/LoopWorkspace/TidepoolService/` | ~7,006 |
| Trio | `externals/Trio/TidepoolService/` | ~7,006 (shared) |
| xDrip+ | `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/tidepool/` | ~1,767 |
| Nocturne | `externals/nocturne/src/Connectors/Nocturne.Connectors.Tidepool/` | ~977 |

---

## References

- [Tidepool API Documentation](https://tidepool.org/developers)
- [TidepoolKit Swift SDK](https://github.com/tidepool-org/TidepoolKit)
- [AAPS Documentation - Tidepool](https://androidaps.readthedocs.io/en/latest/Configuration/tidepool.html)
