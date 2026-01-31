# Follower/Caregiver Feature Consolidation

> **Date**: 2026-01-31  
> **Status**: Complete  
> **Source**: ios-mobile-platform.md #5  
> **Gap Refs**: GAP-REMOTE-001, GAP-REMOTE-004

---

## Executive Summary

This document compares LoopFollow and LoopCaregiver to identify overlap, unique capabilities, and opportunities for shared component extraction.

### Key Findings

| Aspect | LoopFollow | LoopCaregiver |
|--------|------------|---------------|
| **Primary Purpose** | Multi-source CGM display + alarms | Loop-specific remote control |
| **Data Sources** | Nightscout, Dexcom Share | Nightscout only |
| **Remote Commands** | Trio TRC, Loop APNS | Loop APNS + Nightscout |
| **Watch App** | ❌ No | ✅ Yes (WatchOS 10+) |
| **Widgets** | ❌ No | ✅ Yes (WidgetKit) |
| **Alarms** | ✅ Comprehensive | ❌ Basic |
| **SPM Package** | ❌ No | ✅ LoopCaregiverKit |
| **Files** | 432 Swift | 138 Swift |

### Recommendation

**Extract shared components** into a common package:

1. `NightscoutFollowerKit` - Glucose display, timeline, treatments
2. `RemoteCommandKit` - Unified remote command abstraction
3. `GlucoseAlarmKit` - Reusable alarm infrastructure

---

## 1. App Comparison

### 1.1 LoopFollow

**Maintainer**: Loop and Learn  
**Repository**: `github.com/loopandlearn/LoopFollow`  
**Purpose**: Multi-looper caregiver display with comprehensive alarms

**Key Features**:
- Multiple data sources (Nightscout, Dexcom Share)
- Extensive alarm system (17+ alarm types)
- Graph display with predictions
- Multiple instance support (LoopFollow, LoopFollow_Second, LoopFollow_Third)
- Remote commands via Trio TRC and Loop APNS
- Calendar integration
- Contact image customization

**Architecture**:
- UIKit + SwiftUI hybrid
- CocoaPods dependencies (CryptoSwift, SwiftJWT)
- Core Data for persistence
- No Watch app

### 1.2 LoopCaregiver

**Maintainer**: LoopKit  
**Repository**: `github.com/LoopKit/LoopCaregiver`  
**Purpose**: Loop-specific remote monitoring and control

**Key Features**:
- Nightscout data display
- Remote bolus, carbs, override commands
- OTP (TOTP) authentication
- Apple Watch companion app
- WidgetKit widgets (square, inline, circular)
- Deep link handling
- Multi-looper support ("Looper" entities)

**Architecture**:
- SwiftUI primary
- SPM package (LoopCaregiverKit)
- Dependencies: LoopKit, gestrich/NightscoutKit, OneTimePassword
- Watch + Widget extensions

---

## 2. Feature Matrix

### 2.1 Data Sources

| Source | LoopFollow | LoopCaregiver |
|--------|------------|---------------|
| Nightscout | ✅ | ✅ |
| Dexcom Share | ✅ | ❌ |
| LibreLinkUp | ❌ | ❌ |
| Local CGM | ❌ | ❌ |

**Gap**: Neither supports LibreLinkUp or direct CGM connection.

### 2.2 Display Features

| Feature | LoopFollow | LoopCaregiver |
|---------|------------|---------------|
| Glucose graph | ✅ Rich | ✅ Basic |
| Predictions | ✅ | ✅ |
| IOB/COB | ✅ | ✅ |
| Treatments | ✅ | ✅ |
| Basal rate | ✅ | ✅ |
| Override status | ✅ | ✅ |
| Sensor age | ✅ | ❌ |
| Pump battery | ✅ | ❌ |
| Calendar events | ✅ | ❌ |

### 2.3 Remote Commands

| Command | LoopFollow | LoopCaregiver |
|---------|------------|---------------|
| Bolus | ✅ (Trio TRC, Loop APNS) | ✅ (APNS + NS) |
| Carbs/Meal | ✅ (Trio TRC, Loop APNS) | ✅ |
| Temp Target | ✅ (Trio TRC) | ❌ |
| Override Start | ✅ (Trio TRC, Loop APNS) | ✅ |
| Override Cancel | ✅ (Trio TRC, Loop APNS) | ✅ |
| Autobolus Toggle | ❌ | ✅ |
| Closed Loop Toggle | ❌ | ✅ |

### 2.4 Remote Command Protocols

| Protocol | LoopFollow | LoopCaregiver |
|----------|------------|---------------|
| **Trio TRC** | ✅ AES-GCM encrypted | ❌ |
| **Loop APNS** | ✅ JWT-signed push | ✅ |
| **Nightscout API** | ❌ | ✅ (V1 notes) |
| **OTP Auth** | ❌ | ✅ TOTP |

### 2.5 Alarm System

| Alarm Type | LoopFollow | LoopCaregiver |
|------------|------------|---------------|
| High glucose | ✅ | ❌ |
| Low glucose | ✅ | ❌ |
| Urgent low | ✅ | ❌ |
| Rise rate | ✅ | ❌ |
| Drop rate | ✅ | ❌ |
| Stale data | ✅ | ❌ |
| Pump battery | ✅ | ❌ |
| Sensor age | ✅ | ❌ |
| Override active | ✅ | ❌ |
| Snooze support | ✅ | ❌ |
| Custom sounds | ✅ | ❌ |

**Gap**: LoopCaregiver has minimal alarm capability.

### 2.6 Platform Support

| Platform | LoopFollow | LoopCaregiver |
|----------|------------|---------------|
| iPhone | ✅ iOS 15+ | ✅ iOS 16+ |
| Apple Watch | ❌ | ✅ WatchOS 10+ |
| Widgets | ❌ | ✅ WidgetKit |
| iPad | ✅ | ✅ |
| Mac (Catalyst) | ❌ | ❌ |

---

## 3. Security Analysis

### 3.1 LoopFollow Security

**Trio TRC (Trio Remote Control)**:
```swift
// SecureMessenger.swift
struct SecureMessenger {
    private let sharedKey: [UInt8]
    
    init?(sharedSecret: String) {
        sharedKey = Array(secretData.sha256())
    }
    
    func encrypt<T: Encodable>(_ object: T) throws -> String {
        let nonce = generateSecureRandomBytes(count: 12)
        let gcm = GCM(iv: nonce, mode: .combined)
        let aes = try AES(key: sharedKey, blockMode: gcm, padding: .noPadding)
        // ... AES-256-GCM encryption
    }
}
```

- AES-256-GCM encryption with random nonce
- Shared secret derived from SHA-256
- Push notification delivery

**Loop APNS**:
```swift
// LoopAPNSService.swift
// JWT-signed Apple Push Notification Service
// Requires APNS Key ID, APNS Key, Team ID
```

- JWT authentication to APNS
- Device token from Loop's profile
- Direct push to Loop app

### 3.2 LoopCaregiver Security

**OTP Authentication**:
```swift
// OTPManager.swift
public class OTPManager: ObservableObject {
    public let otpURL: String
    
    private func getOTPCode() throws -> String? {
        let token = try Token(url: URL(string: otpURL)!)
        return token.currentPassword
    }
}
```

- TOTP (Time-based One-Time Password)
- QR code provisioning from Loop
- 30-second code rotation

**Remote Command Payload**:
```swift
// BolusRemoteNotification.swift
public struct BolusRemoteNotification: Codable {
    public let amount: Double
    public let remoteAddress: String
    public let expiration: Date?
    public let otp: String?
    public let enteredBy: String?
}
```

- OTP included in each command
- Expiration timestamp for replay protection
- Remote address for audit trail

### 3.3 Security Comparison

| Security Feature | LoopFollow (TRC) | LoopFollow (APNS) | LoopCaregiver |
|------------------|------------------|-------------------|---------------|
| Encryption | AES-256-GCM | TLS (APNS) | TLS (NS API) |
| Authentication | Shared secret | JWT + Team ID | OTP + API secret |
| Replay protection | ❌ | ❌ | ✅ Expiration |
| Audit trail | ❌ | ❌ | ✅ enteredBy |
| Rate limiting | ❌ | ✅ (APNS) | ❌ |

---

## 4. Architecture Comparison

### 4.1 LoopFollow Structure

```
LoopFollow/
├── Alarm/              # 17+ alarm types
│   ├── AlarmManager.swift
│   ├── AlarmType/
│   └── AlarmCondition/
├── Nightscout/         # NS data fetching
├── Remote/
│   ├── TRC/            # Trio Remote Control
│   │   ├── SecureMessenger.swift
│   │   └── TrioRemoteControlView.swift
│   └── LoopAPNS/       # Loop push notifications
│       └── LoopAPNSService.swift
├── Controllers/
├── ViewControllers/
└── Settings/
```

**Dependencies** (CocoaPods):
- CryptoSwift (encryption)
- SwiftJWT (APNS auth)
- Charts (graphing)

### 4.2 LoopCaregiver Structure

```
LoopCaregiver/
├── LoopCaregiverKit/   # SPM package
│   ├── Sources/
│   │   ├── LoopCaregiverKit/
│   │   │   ├── Nightscout/
│   │   │   │   ├── RemoteCommands/V1/
│   │   │   │   └── OTPManager.swift
│   │   │   └── Models/
│   │   └── LoopCaregiverKitUI/
│   └── Package.swift
├── LoopCaregiverWatchApp/
└── LoopCaregiverWidgetExtension/
```

**Dependencies** (SPM):
- LoopKit (types, utilities)
- gestrich/NightscoutKit (API client)
- OneTimePassword (TOTP)

---

## 5. Shared Component Proposal

### 5.1 Proposed Packages

#### NightscoutFollowerKit

**Purpose**: Common Nightscout data fetching and display

**Components**:
- `GlucoseEntry` - Standardized glucose model
- `TreatmentEntry` - Bolus, carbs, overrides
- `DeviceStatus` - IOB, COB, predictions
- `ProfileSet` - Active profile data
- `NightscoutDataSource` - Unified data provider
- `GlucoseTimelineEntry` - Widget/complication data

**Source Candidates**:
- LoopCaregiverKit `Nightscout/Extensions/`
- LoopFollow `Nightscout/`
- gestrich/NightscoutKit (foundation)

#### RemoteCommandKit

**Purpose**: Unified remote command abstraction

**Components**:
```swift
public protocol RemoteCommandService {
    func sendBolus(units: Double, otp: String?) async throws -> CommandStatus
    func sendCarbs(grams: Double, absorptionTime: TimeInterval?) async throws -> CommandStatus
    func sendOverride(name: String, duration: TimeInterval?) async throws -> CommandStatus
    func cancelOverride() async throws -> CommandStatus
    func sendTempTarget(value: Double, duration: TimeInterval) async throws -> CommandStatus
}

public enum CommandStatus {
    case pending
    case inProgress
    case success
    case error(RemoteCommandError)
}
```

**Implementations**:
- `TrioTRCService` - Encrypted push (from LoopFollow)
- `LoopAPNSService` - JWT push (from LoopFollow)
- `NightscoutRemoteService` - API notes (from LoopCaregiver)

#### GlucoseAlarmKit

**Purpose**: Reusable alarm infrastructure

**Components**:
- `AlarmType` enum (high, low, urgent, stale, etc.)
- `AlarmCondition` protocol
- `AlarmManager` - Evaluation and triggering
- `SnoozeManager` - Snooze state
- `AlarmSound` - Sound file management

**Source**: LoopFollow `Alarm/` (432 lines in AlarmManager.swift alone)

### 5.2 Migration Path

| Phase | Action | Effort |
|-------|--------|--------|
| 1 | Extract NightscoutFollowerKit from LoopCaregiverKit | Medium |
| 2 | Create RemoteCommandKit with protocol abstraction | Medium |
| 3 | Port LoopFollow's AlarmManager to GlucoseAlarmKit | High |
| 4 | Integrate packages into both apps | Medium |
| 5 | Add missing features to each app | High |

### 5.3 Recommended Package Dependencies

```
NightscoutFollowerKit
├── gestrich/NightscoutKit (API client)
└── (no LoopKit dependency - maximize reuse)

RemoteCommandKit
├── NightscoutFollowerKit
├── CryptoSwift (TRC encryption)
└── OneTimePassword (OTP support)

GlucoseAlarmKit
├── NightscoutFollowerKit
└── (pure Swift - no external deps)
```

---

## 6. Remote Command Security Requirements

### REQ-REMOTE-001: Command Authentication

**Statement**: All remote commands MUST include authentication credentials.

**Rationale**: Prevents unauthorized command injection.

**Options**:
| Method | Strength | Complexity |
|--------|----------|------------|
| Shared secret | Medium | Low |
| OTP (TOTP) | High | Medium |
| OAuth 2.0 | High | High |

### REQ-REMOTE-002: Command Expiration

**Statement**: Remote commands SHOULD include expiration timestamps.

**Rationale**: Prevents replay attacks from captured/delayed commands.

**Implementation**:
```swift
struct RemoteCommand {
    let action: Action
    let expiration: Date  // Reject if now > expiration
    let sentAt: Date
}
```

### REQ-REMOTE-003: Audit Trail

**Statement**: Remote commands MUST include sender identification.

**Rationale**: Enables post-hoc review of who sent what command.

**Fields**:
- `enteredBy` - Sender identifier
- `remoteAddress` - Device/app identifier
- `timestamp` - Command creation time

### REQ-REMOTE-004: Encryption in Transit

**Statement**: Remote command payloads SHOULD be encrypted.

**Options**:
| Protocol | Encryption | Notes |
|----------|------------|-------|
| HTTPS/TLS | Transport | Minimum requirement |
| AES-GCM | Payload | Trio TRC approach |
| End-to-end | Full | Requires key exchange |

---

## 7. Gap Analysis

### GAP-FOLLOW-001: No Watch App in LoopFollow

**Description**: LoopFollow lacks Apple Watch support.

**Impact**: Caregivers cannot quickly check glucose from wrist.

**Remediation**: Extract LoopCaregiver's watch components to shared package.

### GAP-FOLLOW-002: No Widgets in LoopFollow

**Description**: LoopFollow lacks WidgetKit support.

**Impact**: No home screen glucose display.

**Remediation**: Port LoopCaregiverKitUI widget views.

### GAP-CAREGIVER-001: Minimal Alarm System

**Description**: LoopCaregiver has no comprehensive alarm system.

**Impact**: Caregivers may miss critical glucose events.

**Remediation**: Integrate GlucoseAlarmKit from LoopFollow.

### GAP-CAREGIVER-002: No Dexcom Share Support

**Description**: LoopCaregiver only supports Nightscout.

**Impact**: Requires Nightscout setup for any monitoring.

**Remediation**: Add Dexcom Share to NightscoutFollowerKit.

### GAP-REMOTE-005: No Unified Command Protocol

**Description**: Three different remote command protocols (TRC, APNS, NS API).

**Impact**: Fragmented implementation, no cross-app compatibility.

**Remediation**: Create RemoteCommandKit with protocol abstraction.

---

## 8. Recommendation Summary

### Short-term (1-2 months)

1. **Create NightscoutFollowerKit** - Extract common display code
2. **Document remote command protocols** - Standardize on wire format
3. **Add LoopFollow alarms to LoopCaregiver** - Port AlarmManager

### Medium-term (3-6 months)

1. **Create RemoteCommandKit** - Unified command abstraction
2. **Add Watch support to LoopFollow** - Port from LoopCaregiver
3. **Add Dexcom Share to LoopCaregiver** - Multi-source support

### Long-term (6-12 months)

1. **Merge apps or create unified follower** - Single app with all features
2. **OAuth 2.0 remote commands** - Identity provider integration
3. **App Store submission** - Display-only version (per app-store-pathway-analysis.md)

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [app-store-pathway-analysis.md](app-store-pathway-analysis.md) | App Store viability |
| [nightscoutkit-swift-sdk-design.md](../sdqctl-proposals/nightscoutkit-swift-sdk-design.md) | SDK design patterns |
| [trusted-identity-providers.md](trusted-identity-providers.md) | OAuth integration |
