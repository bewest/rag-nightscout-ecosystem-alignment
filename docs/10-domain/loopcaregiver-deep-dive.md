# LoopCaregiver Deep Dive

> **Source**: `externals/LoopCaregiver/`  
> **Last Updated**: 2026-01-29  
> **Version**: dev branch (maintained by LoopKit)

## Overview

LoopCaregiver is an iOS/watchOS companion app that enables remote control of Loop AID systems through Nightscout. Unlike LoopFollow which is read-only, LoopCaregiver can send remote commands including bolus, carbs, and override activations.

| Aspect | Details |
|--------|---------|
| **Language** | Swift (iOS/watchOS) |
| **Maintainer** | LoopKit / Bill Gestrich |
| **License** | Open source |
| **Platforms** | iOS 16+, watchOS 10+ |
| **Target AID** | Loop only (not Trio/OpenAPS) |
| **Transport** | Push notifications via Nightscout |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       LoopCaregiver                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐        │
│  │   Looper     │   │  RemoteData  │   │   OTP        │        │
│  │   Models     │   │  Service     │   │   Manager    │        │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘        │
│         │                  │                   │                │
│         ▼                  ▼                   ▼                │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              LoopCaregiverKit                        │       │
│  │  • NightscoutCredentials                             │       │
│  │  • RemoteCommands/V1/                                │       │
│  │  • RemoteCommands/V2/ (experimental)                 │       │
│  └─────────────────────────────────────────────────────┘       │
│                            │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │   Nightscout    │           │   Loop App      │
    │   (V1 API +     │◄─────────►│   (via APNS)    │
    │   notifications)│           │                 │
    └─────────────────┘           └─────────────────┘
```

---

## Directory Structure

```
LoopCaregiver/
├── LoopCaregiver/              # iOS app target
├── LoopCaregiverKit/           # Shared framework
│   └── Sources/LoopCaregiverKit/
│       ├── Models/
│       │   ├── Looper.swift              # Looper profile
│       │   ├── RemoteDataServiceProvider.swift  # API interface
│       │   ├── DeepLinkParser.swift      # QR code handling
│       │   └── ...
│       ├── Nightscout/
│       │   ├── NightscoutCredentials.swift
│       │   ├── OTPManager.swift          # TOTP generation
│       │   ├── RemoteCommands/
│       │   │   ├── V1/                   # Push notification payloads
│       │   │   │   ├── BolusRemoteNotification.swift
│       │   │   │   ├── CarbRemoteNotification.swift
│       │   │   │   ├── OverrideRemoteNotification.swift
│       │   │   │   └── ...
│       │   │   └── NSRemoteCommandPayload.swift  # V2 payloads
│       │   └── Extensions/               # NightscoutKit extensions
│       └── Resources/
└── docs/
```

---

## Looper Management

### NightscoutCredentials

**Source**: `LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutCredentials.swift`

```swift
public struct NightscoutCredentials: Codable, Hashable {
    public let url: URL           // Nightscout URL
    public let secretKey: String  // API secret
    public let otpURL: String     // TOTP secret URL
}
```

### Looper Profile

**Source**: `LoopCaregiverKit/Sources/LoopCaregiverKit/Models/Looper.swift`

```swift
public class Looper: ObservableObject, Codable, Identifiable {
    public var identifier: UUID
    public var name: String
    public var lastSelectedDate: Date
    public let nightscoutCredentials: NightscoutCredentials
}
```

### Deep Link Registration

LoopCaregiver uses deep links to register Loopers via QR code:

**URL Scheme**: `caregiver://createLooper?name={name}&secretKey={secret}&nsURL={url}&otpURL={otp}`

| Parameter | Description |
|-----------|-------------|
| `name` | Looper display name |
| `secretKey` | Nightscout API secret |
| `nsURL` | Nightscout URL (percent-encoded) |
| `otpURL` | TOTP secret URL (percent-encoded) |

---

## OTP (One-Time Password)

**Source**: `LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/OTPManager.swift`

Loop requires TOTP authentication for remote commands:

```swift
public class OTPManager: ObservableObject {
    public let otpURL: String
    @Published public var otpCode: String = ""
    
    private func getOTPCode() throws -> String? {
        let token = try Token(url: URL(string: otpURL)!)
        return token.currentPassword
    }
}
```

- Uses `OneTimePassword` library
- Refreshes every second
- 6-digit TOTP codes
- Shared secret from Loop QR code

---

## Remote Commands

### Command Types (V1)

**Source**: `LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/RemoteCommands/V1/`

| Command | File | Key Field |
|---------|------|-----------|
| Bolus | `BolusRemoteNotification.swift` | `bolus-entry` |
| Carbs | `CarbRemoteNotification.swift` | `carbs-entry` |
| Override | `OverrideRemoteNotification.swift` | `override-name` |
| Cancel Override | `OverrideCancelRemoteNotification.swift` | `cancel-temporary-override` |

### Bolus Payload

```swift
public struct BolusRemoteNotification: Codable {
    public let amount: Double           // "bolus-entry"
    public let remoteAddress: String    // "remote-address"
    public let expiration: Date?        // "expiration"
    public let sentAt: Date?            // "sent-at"
    public let otp: String?             // "otp"
    public let enteredBy: String?       // "entered-by"
}
```

### Carbs Payload

```swift
public struct CarbRemoteNotification: Codable {
    public let amount: Double           // "carbs-entry"
    public let absorptionInHours: Double?  // "absorption-time"
    public let foodType: String?        // "food-type"
    public let startDate: Date?         // "start-time"
    public let remoteAddress: String    // "remote-address"
    public let expiration: Date?
    public let otp: String?
}
```

### Override Payload

```swift
public struct OverrideRemoteNotification: Codable {
    public let name: String             // "override-name"
    public let durationInMinutes: Double?  // "override-duration-minutes"
    public let remoteAddress: String
    public let expiration: Date?
}
```

---

## Remote Commands 2.0 (Experimental)

### Overview

Remote Commands 2.0 adds:
- Command status tracking (Pending → InProgress → Success/Error)
- Nightscout-stored command state
- Bidirectional communication

**Requirements**:
- Special Nightscout branch: `gestrich/cgm-remote-monitor:feature/2023-07/bg/remote-commands`
- Special Loop branch: `LoopKit/LoopWorkspace:feature/2023-10/bg/remote-commands`

### Command Actions (V2)

**Source**: `NSRemoteCommandPayload.swift`

```swift
func toRemoteAction() -> Action {
    switch action {
    case let .bolus(amountInUnits):
        return .bolusEntry(BolusAction(amountInUnits: amountInUnits))
    case let .carbs(amountInGrams, absorptionTime, startDate):
        return .carbsEntry(CarbAction(...))
    case let .override(name, durationTime, remoteAddress):
        return .temporaryScheduleOverride(OverrideAction(...))
    case let .cancelOverride(remoteAddress):
        return .cancelTemporaryOverride(...)
    case let .autobolus(active):
        return .autobolus(AutobolusAction(active: active))
    case let .closedLoop(active):
        return .closedLoop(ClosedLoopAction(active: active))
    }
}
```

### Command Status

```swift
enum NSRemoteCommandState {
    case Pending
    case InProgress
    case Success
    case Error
}
```

---

## Remote Data Service

**Source**: `LoopCaregiverKit/Sources/LoopCaregiverKit/Models/RemoteDataServiceProvider.swift`

```swift
public protocol RemoteDataServiceProvider {
    // Read operations
    func fetchGlucoseSamples() async throws -> [NewGlucoseSample]
    func fetchBolusEntries() async throws -> [BolusNightscoutTreatment]
    func fetchCarbEntries() async throws -> [CarbCorrectionNightscoutTreatment]
    func fetchOverridePresets() async throws -> [OverrideTreatment]
    func fetchLatestDeviceStatus() async throws -> DeviceStatus?
    func fetchCurrentProfile() async throws -> ProfileSet
    
    // Write operations (remote commands)
    func deliverCarbs(amountInGrams: Double, absorptionTime: TimeInterval, consumedDate: Date) async throws
    func deliverBolus(amountInUnits: Double) async throws
    func startOverride(overrideName: String, durationTime: TimeInterval) async throws
    func cancelOverride() async throws
    func activateAutobolus(activate: Bool) async throws
    func activateClosedLoop(activate: Bool) async throws
    
    // Command management (V2)
    func fetchRecentCommands() async throws -> [RemoteCommand]
    func deleteAllCommands() async throws
}
```

---

## NightscoutKit Usage

LoopCaregiver uses `NightscoutKit` (LoopKit dependency) for API access:

| Data Type | NightscoutKit Type |
|-----------|-------------------|
| Glucose | `NewGlucoseSample` |
| Bolus | `BolusNightscoutTreatment` |
| Carbs | `CarbCorrectionNightscoutTreatment` |
| Basals | `TempBasalNightscoutTreatment` |
| Overrides | `OverrideTreatment` |
| Device Status | `DeviceStatus` |
| Profile | `ProfileSet` |

---

## Security Model

### Authentication Layers

| Layer | Mechanism |
|-------|-----------|
| Nightscout API | `secretKey` (API secret) |
| Remote Commands | 6-digit TOTP code |
| Command Expiry | 5-minute default |

### TOTP Flow

1. Loop generates OTP secret (QR code in Settings)
2. Caregiver scans QR, stores `otpURL`
3. OTPManager generates 6-digit code every 30 seconds
4. Remote commands include OTP for validation
5. Loop validates OTP before executing command

### Security Warnings

From README.md:
- Nightscout QR code and API Key should be secured
- Anyone with access can remotely send treatments
- Lost/stolen phone → reset QR code in Loop Settings

---

## Watch Support

LoopCaregiver includes watchOS app:

- Watch configuration via deep links
- Same remote command capabilities
- Glucose display widgets

**Source**: `WatchConnectivityService.swift`, `WatchConfiguration.swift`

---

## Gaps Identified

### GAP-LOOPCAREGIVER-001: Loop-Only Support

**Description**: LoopCaregiver only works with Loop. No support for Trio, OpenAPS, or AAPS.

**Impact**:
- Trio users must use different apps (e.g., LoopFollow + TRC)
- No unified caregiver experience across AID systems

**Source**: Architecture targets Loop-specific APNS integration

### GAP-LOOPCAREGIVER-002: Experimental V2 Commands

**Description**: Remote Commands 2.0 requires non-mainline branches of both Nightscout and Loop.

**Impact**:
- Most users don't have command status tracking
- Special deployment complexity
- Branch maintenance burden

**Source**: README.md Remote Commands 2.0 section

### GAP-LOOPCAREGIVER-003: No Standard Command API

**Description**: Commands use proprietary push notification format, not a standard Nightscout API.

**Impact**:
- Not interoperable with other systems
- Tightly coupled to Loop implementation
- No command history in standard Nightscout

**Source**: V1 remote notification format

---

## Comparison: LoopCaregiver vs LoopFollow

| Feature | LoopCaregiver | LoopFollow |
|---------|---------------|------------|
| **Purpose** | Remote control | Monitoring only |
| **Target AID** | Loop only | Loop, Trio, OpenAPS |
| **Remote Bolus** | ✅ | Via APNS passthrough |
| **Remote Carbs** | ✅ | Via NS treatments |
| **Remote Override** | ✅ | ✅ |
| **Command Status** | ✅ (V2) | ❌ |
| **Multi-Looper** | ✅ | ✅ (3 instances) |
| **Dexcom Share** | ❌ | ✅ |
| **Watch App** | ✅ | ✅ |

---

## Source File Reference

### Core Files
- `LoopCaregiverKit/Sources/LoopCaregiverKit/Models/Looper.swift` - Looper profile
- `LoopCaregiverKit/Sources/LoopCaregiverKit/Models/RemoteDataServiceProvider.swift` - API interface
- `LoopCaregiverKit/Sources/LoopCaregiverKit/Models/DeepLinkParser.swift` - QR code handling

### Nightscout Integration
- `LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutCredentials.swift` - Credentials
- `LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/OTPManager.swift` - TOTP generation
- `LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/RemoteCommands/V1/` - V1 payloads
- `LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/RemoteCommands/NSRemoteCommandPayload.swift` - V2 payloads

---

## Summary

| Aspect | Details |
|--------|---------|
| **Purpose** | Remote control of Loop AID system |
| **Transport** | Push notifications via Nightscout |
| **Commands** | Bolus, Carbs, Override, Autobolus, Closed Loop |
| **Security** | API secret + TOTP + expiration |
| **Multi-Looper** | Supported (unlimited) |
| **Limitations** | Loop-only, V2 requires special branches |

LoopCaregiver demonstrates a secure remote command architecture for AID systems, using TOTP authentication and command expiration to mitigate risks of remote insulin delivery.
